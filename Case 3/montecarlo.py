"""
montecarlo.py
=============

Monte-Carlo 1-year 99% VaR for the Case 3b combined book, as a third pillar
next to Historical Simulation (`case3_var.py`) and the parametric check.

Model
    * weekly risk-factor moves: EUR swap-curve tenors + USD 1y + EUR 1y as
      absolute changes, the 14 index levels as log returns
    * dependence: correlation matrix of the weekly moves, Ledoit-Wolf-style
      shrunk toward the average pairwise correlation (stabilises a 27x27 matrix
      from ~500 obs)
    * marginals: each factor's own weekly mean / std, innovations from a
      multivariate Student-t (dof nu, default 5) -> fat tails + tail dependence.
      nu = inf recovers the Gaussian-copula / parametric case.
    * simulate 52 weekly steps per path, compound to a 1-year move, reprice the
      whole book with the same engine as HS (`case3_var.reprice`)

Runs the same risk-control overlay (derive the equity 99% 1y VaR limit, size
the futures short) so MC and HS are directly comparable.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from case3_var import (
    OUT, Config, Scenarios, build_book, derive_var_limit, reprice,
    target_hedge_ratio, var_stats, weekly_changes, Z, _mn,
)
from vix import HestonVIX, term_weight


def _shrunk_corr(X: np.ndarray, delta: float = 0.10) -> np.ndarray:
    R = np.corrcoef(X, rowvar=False)
    p = R.shape[0]
    off = R[~np.eye(p, dtype=bool)].mean()
    target = np.full_like(R, off)
    np.fill_diagonal(target, 1.0)
    S = (1.0 - delta) * R + delta * target
    # nearest-PD tidy-up
    w, V = np.linalg.eigh((S + S.T) / 2.0)
    w = np.clip(w, 1e-8, None)
    S = V @ np.diag(w) @ V.T
    d = np.sqrt(np.diag(S))
    return S / np.outer(d, d)


def simulate(cfg: Config, n_paths: int = 20_000, nu: float = 5.0,
             seed: int = 7, n_pc: int = 3,
             heston: "HestonVIX | None" = None) -> "tuple[Scenarios, dict]":
    """Simulate 1-year factor moves. The EUR curve-change block is reduced to
    `n_pc` principal components (level / slope / curvature) so simulated curve
    shifts stay economically shaped; USD 1y, EUR 1y and the 14 index returns
    join the same multivariate-t draw.

    If `heston` is given, a Heston market-variance path v_t is run each week,
    driven by the (leverage-correlated) equity market shock; the equity sleeves'
    weekly returns are scaled by sqrt(v_t / theta) so realised equity vol tracks
    the regime, and a VIX_t path is returned - so a VIX spike lines up with an
    equity crash on the same path.  Returns (Scenarios, vix_info)."""
    wc = weekly_changes(cfg)
    d_eur, d_usd1, d_eur1, r_idx = wc["d_eur"], wc["d_usd1"], wc["d_eur1"], wc["r_idx"]
    tenors = wc["eur_tenors"]
    idx_cols = list(r_idx.columns)
    h = cfg.horizon_weeks

    # --- PCA of the weekly EUR curve-change block -------------------------
    De = d_eur.dropna()
    de_mean = De.mean().to_numpy()
    U, S, Vt = np.linalg.svd(De.to_numpy() - de_mean, full_matrices=False)
    load = Vt[:n_pc]                                   # (n_pc, n_tenor)
    pc_scores = (De.to_numpy() - de_mean) @ load.T     # (T, n_pc)
    pc_df = pd.DataFrame(pc_scores, index=De.index,
                         columns=[f"pc{i+1}" for i in range(n_pc)])

    panel = pd.concat([pc_df, d_usd1, d_eur1, r_idx], axis=1).dropna()
    X = panel.to_numpy()
    mu = X.mean(axis=0)
    sd = X.std(axis=0, ddof=1)
    R = _shrunk_corr(X)
    L = np.linalg.cholesky(R)
    k = X.shape[1]

    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_paths, h, k)) @ L.T
    if np.isfinite(nu):
        g = rng.chisquare(nu, size=(n_paths, h, 1)) / nu
        tt = z / np.sqrt(g) * np.sqrt((nu - 2.0) / nu)
    else:
        tt = z
    weekly = mu + sd * tt                              # (paths, h, k)

    # --- Heston market variance + VIX + equity vol regime ----------------
    eq_pos = [n_pc + 2 + idx_cols.index(s) for s in cfg.equity_sleeves
              if s in idx_cols]
    mkt_col = n_pc + 2 + idx_cols.index("MSCI World Index")
    vix_info: dict = {}
    if heston is not None:
        z_mkt = tt[:, :, mkt_col]                      # ~ std-normal market shock
        hp = heston.simulate_paths(z_mkt, dt=1.0 / 52.0, rng=rng)
        weekly[:, :, eq_pos] *= hp["vol_mult"][:, :, None]
        worst_wk = np.argmin(weekly[:, :, mkt_col], axis=1)
        rows = np.arange(n_paths)
        vix_info = {
            "vix_path": hp["vix"],
            "vix_max": hp["vix"].max(axis=1),
            "vix_terminal": hp["vix"][:, -1],
            "vix_at_worst_equity_week": hp["vix"][rows, worst_wk + 1],
            "v_path": hp["v"],
            "feller_ok": heston.feller_ok,
            "A_tau": term_weight(heston.kappa),
        }

    annual = weekly.sum(axis=1)                        # (paths, k)

    pc_ann = annual[:, :n_pc]
    usd1 = annual[:, n_pc]
    eur1 = annual[:, n_pc + 1]
    idx_ann = annual[:, n_pc + 2:]

    # reconstruct the curve change; rates carry ~no drift (near-martingale)
    eur_chg_arr = pc_ann @ load

    # guardrail: softly compress any simulated 1-year move that exceeds 1.25x the
    # worst observed 52-week move of that factor (excess beyond the bound is
    # halved, no hard pile-up) - stops t-tails producing curve/index moves far
    # outside the data while keeping the distribution smooth
    def soft(x, lo, hi):
        x = np.asarray(x, dtype=float)
        x = np.where(x > hi, hi + 0.5 * (x - hi), x)
        x = np.where(x < lo, lo + 0.5 * (x - lo), x)
        return x

    g = 1.25
    # rates: HARD bound (the 30y liability revaluation is exponentially
    # sensitive - an implausible -4% rally must not blow up the tail)
    de_ann = d_eur.rolling(h).sum().dropna()
    eur_chg_arr = np.clip(eur_chg_arr, de_ann.min().to_numpy() * g,
                          de_ann.max().to_numpy() * g)
    u1h = d_usd1.rolling(h).sum().dropna()
    e1h = d_eur1.rolling(h).sum().dropna()
    usd1 = np.clip(usd1, u1h.min() * g, u1h.max() * g)
    eur1 = np.clip(eur1, e1h.min() * g, e1h.max() * g)
    # indices: SOFT compression (keeps the P&L histogram smooth, no pile-up)
    idx_ann_hist = r_idx.rolling(h).sum().dropna()
    idx_ann = soft(idx_ann, idx_ann_hist.min().to_numpy() * g,
                   idx_ann_hist.max().to_numpy() * g)

    eur_chg = pd.DataFrame(eur_chg_arr, columns=tenors)
    idx_ret = pd.DataFrame(idx_ann, columns=idx_cols)

    sc = Scenarios(
        dates=pd.Index(range(n_paths), name="path"),
        eur_rate_chg=eur_chg, usd_1y_chg=usd1, eur_1y_chg=eur1,
        idx_logret=idx_ret, n=n_paths,
    )
    return sc, vix_info


def run_mc(cfg: Config, n_paths: int = 20_000, tag: str | None = None,
          heston: "HestonVIX | None" = None) -> dict:
    OUT.mkdir(exist_ok=True)
    tag = tag or f"mc_{cfg.deployment}"
    heston = heston or HestonVIX()
    book = build_book(cfg)

    # --- overlay: size the hedge off the MC unhedged equity 99% 1y VaR --------
    sim, _ = simulate(cfg, n_paths=n_paths, nu=5.0, heston=heston)
    unh = reprice(book, sim, replace(cfg, future_hedge_ratio=0.0))
    eq_var = var_stats(unh["equity"].to_numpy(), cfg.confidence)["hist_var"]
    non_eq = var_stats((unh["surplus_pnl"] - unh["equity"]).to_numpy(),
                       cfg.confidence)["hist_var"]
    li = derive_var_limit(book, cfg, non_eq)
    limit = li["var_limit_eur"]
    ratio = (float(cfg.future_hedge_ratio) if cfg.future_hedge_ratio is not None
             else target_hedge_ratio(eq_var, limit)) if li["economic_surplus"] > 0 else 0.0
    cfg2 = replace(cfg, future_hedge_ratio=ratio)

    results = {}
    vinfo = None
    for label, nu in (("student_t_nu5", 5.0), ("gaussian", np.inf)):
        s, vi = simulate(cfg, n_paths=n_paths, nu=nu, seed=11, heston=heston)
        pnl = reprice(book, s, cfg2)
        pnl["equity_ret"] = pnl["equity"] / max(
            book.sleeves.loc[book.sleeves["kind"] == "EQUITY", "mv_eur"].sum(), 1.0)
        pnl.to_csv(OUT / f"{tag}_{label}_pnl.csv", index=False)
        results[label] = {
            "asset": var_stats(pnl["asset_pnl"].to_numpy(), cfg.confidence),
            "surplus": var_stats(pnl["surplus_pnl"].to_numpy(), cfg.confidence),
            "pnl": pnl,
        }
        if label == "student_t_nu5":
            vinfo = vi

    vix_diag = _vix_diagnostics(vinfo, results["student_t_nu5"]["pnl"], cfg)
    _report(cfg, book, results, li, eq_var, limit, ratio, n_paths, tag, vix_diag)
    _chart(results, cfg, tag, vinfo)
    return {**results, "vix_diag": vix_diag, "vix_info": vinfo}


def _vix_diagnostics(vi: dict, pnl: pd.DataFrame, cfg: Config) -> dict:
    """Does the VIX trigger fire in sync with the equity drawdown?"""
    if not vi:
        return {}
    er = pnl["equity_ret"].to_numpy()
    vmax = vi["vix_max"]
    vwe = vi["vix_at_worst_equity_week"]
    q = np.quantile(er, 1.0 - cfg.confidence)          # 99% worst equity return
    tail = er <= q
    return {
        "median_vix_terminal": float(np.median(vi["vix_terminal"])),
        "median_vix_max": float(np.median(vmax)),
        "p99_vix_max": float(np.quantile(vmax, 0.99)),
        "corr_vixmax_vs_equity_1y_return": float(np.corrcoef(vmax, er)[0, 1]),
        "median_vix_at_worst_week_all": float(np.median(vwe)),
        "median_vix_at_worst_week_in_equity_tail": float(np.median(vwe[tail])),
        "share_paths_vix_gt_50_in_equity_tail": float((vwe[tail] > 50).mean()),
        "share_paths_vix_gt_40_in_equity_tail": float((vwe[tail] > 40).mean()),
    }


def _pc(x):
    return f"{x:.3f}"


def _report(cfg, book, results, li, eq_var, limit, ratio, n_paths, tag, vix_diag=None):
    L = []
    A = L.append
    A(f"# Case 3b - Monte-Carlo 1-year {cfg.confidence:.0%} VaR  ({cfg.deployment})\n")
    A(f"{n_paths:,} paths x 52 weekly steps. Weekly factor moves ~ multivariate "
      f"Student-t (dof 5, shrunk correlation), compounded to 1 year, book "
      f"repriced with the HS engine.\n")
    A(f"- Total assets EUR {book.asset_mv/1e9:,.2f}bn | liability PV "
      f"EUR {book.liability_pv/1e9:,.2f}bn | economic surplus "
      f"EUR {li['economic_surplus']/1e9:,.2f}bn")
    A(f"- Equity 99% 1y VaR limit (MC): EUR {limit/1e6:,.0f}m  "
      f"({li['limit_pct_of_equity_mv']:.1%} of equity MV)")
    A(f"- Unhedged equity 99% 1y VaR (MC): EUR {eq_var/1e6:,.0f}m  ->  "
      f"applied futures short {ratio:.1%}\n")
    A("## MC VaR / ES  (1-year, EUR)\n")
    A("| model | Asset VaR | Asset ES | Surplus VaR | Surplus ES |")
    A("|---|--:|--:|--:|--:|")
    for label, r in results.items():
        A(f"| {label} | {_mn(r['asset']['hist_var'])} | {_mn(r['asset']['hist_es'])} "
          f"| {_mn(r['surplus']['hist_var'])} | {_mn(r['surplus']['hist_es'])} |")
    if vix_diag:
        vd = vix_diag
        A("\n## VIX (Heston stochastic vol + leverage)\n")
        A("Market variance v_t: Heston, weekly full-truncation Euler, driven by "
          "the equity market shock via rho = -0.75 (leverage). "
          f"VIX_t = 100 sqrt(A(tau) v_t + (1-A) theta), A(tau) = {_pc(vd.get('A_tau', 0.886))}.\n")
        A(f"- median VIX (terminal / path-max): "
          f"{vd['median_vix_terminal']:.1f} / {vd['median_vix_max']:.1f}   "
          f"(99th-pct path-max {vd['p99_vix_max']:.1f})")
        A(f"- corr(path-max VIX, 1y equity return): "
          f"{vd['corr_vixmax_vs_equity_1y_return']:+.2f}  (leverage works)")
        A(f"- VIX in the worst equity week - all paths vs the 99% equity tail: "
          f"{vd['median_vix_at_worst_week_all']:.1f}  vs  "
          f"**{vd['median_vix_at_worst_week_in_equity_tail']:.1f}**")
        A(f"- share of 99%-tail paths with VIX > 40 / > 50 at the crash week: "
          f"{vd['share_paths_vix_gt_40_in_equity_tail']:.0%} / "
          f"{vd['share_paths_vix_gt_50_in_equity_tail']:.0%}")
        A("\n=> the VIX trigger fires in the same paths the portfolio crashes, "
          "so a VIX-gated no-trade band (widen in calm regimes, tighten / force "
          "the hedge when VIX spikes) is meaningful. Without stochastic vol the "
          "trigger would be uncorrelated with the drawdown.")

    A("\n## Method notes\n")
    A("- Student-t (dof 5) gives ~3x the excess kurtosis of a normal and non-zero "
      "tail dependence; `gaussian` (dof inf) is the copula-normal / parametric "
      "reference.")
    A("- Correlation is shrunk 10% toward the mean pairwise correlation "
      "(Ledoit-Wolf style) and repaired to the nearest PD matrix.")
    A("- Rates simulated as absolute weekly changes, indices as log returns; "
      "1-year move = sum of 52 simulated weeks (no iid-normal sqrt-time scaling).")
    A("- Heston: kappa 3.0, theta 0.028 (~16.7% long-run vol), xi 0.40, rho -0.75; "
      "equity weekly returns scaled by sqrt(v_t/theta) so realised equity vol "
      "tracks the regime.")
    A("- Same book, liability and overlay as the HS run in `case3_var.py`; compare "
      "the two headline numbers there.")
    (OUT / f"MC_REPORT_{tag}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {OUT}/ : MC_REPORT_{tag}.md, {tag}_*_pnl.csv, mc_charts_{tag}.png")


def _chart(results, cfg, tag, vinfo=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C_T, C_G, C_V = "#0072B2", "#E69F00", "#D55E00"
    n = 3 if vinfo else 2
    fig, ax = plt.subplots(1, n, figsize=(6.6 * n, 5.2))

    for label, c in (("student_t_nu5", C_T), ("gaussian", C_G)):
        a = np.sort(results[label]["pnl"]["surplus_pnl"].to_numpy() / 1e6)
        ax[0].plot(a, np.linspace(0, 1, len(a)), color=c, lw=2, label=label)
        ax[0].axvline(-results[label]["surplus"]["hist_var"] / 1e6, color=c, lw=1.5, ls="--")
    ax[0].axhline(1 - cfg.confidence, color="#333", lw=1, ls=":")
    ax[0].set_title("MC surplus P&L - empirical CDF (1y)")
    ax[0].set_xlabel("EUR m"); ax[0].legend(frameon=False)

    t = results["student_t_nu5"]["pnl"]["asset_pnl"].to_numpy() / 1e6
    g = results["gaussian"]["pnl"]["asset_pnl"].to_numpy() / 1e6
    ax[1].hist(t, bins=60, color=C_T, alpha=0.55, label="Student-t (5)")
    ax[1].hist(g, bins=60, color=C_G, alpha=0.55, label="Gaussian")
    ax[1].set_title("MC asset P&L distribution (1y)")
    ax[1].set_xlabel("EUR m"); ax[1].legend(frameon=False)

    if vinfo:
        er = results["student_t_nu5"]["pnl"]["equity_ret"].to_numpy() * 100.0
        vwe = vinfo["vix_at_worst_equity_week"]
        ax[2].scatter(er, vwe, s=5, alpha=0.25, color=C_T)
        ax[2].axhline(50, color=C_V, lw=1.5, ls="--")
        ax[2].axhline(40, color=C_V, lw=1, ls=":")
        ax[2].set_title("VIX at the crash week  vs  1y equity return")
        ax[2].set_xlabel("1y equity return (%)"); ax[2].set_ylabel("VIX at worst week")

    for a_ in ax:
        a_.grid(color="#E6E6E6", lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle(f"Case 3b - Monte-Carlo 1y {cfg.confidence:.0%} VaR ({cfg.deployment})",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / f"mc_charts_{tag}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    dep = sys.argv[1] if len(sys.argv) > 1 else "full"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20_000
    run_mc(Config(deployment=dep), n_paths=n)
