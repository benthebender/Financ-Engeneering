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
             seed: int = 7, n_pc: int = 3) -> Scenarios:
    """Simulate 1-year factor moves. The EUR curve-change block is reduced to
    `n_pc` principal components (level / slope / curvature) so simulated curve
    shifts stay economically shaped; USD 1y, EUR 1y and the 14 index returns
    join the same multivariate-t draw."""
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
    annual = (mu + sd * tt).sum(axis=1)                # (paths, k)

    pc_ann = annual[:, :n_pc]
    usd1 = annual[:, n_pc]
    eur1 = annual[:, n_pc + 1]
    idx_ann = annual[:, n_pc + 2:]

    # reconstruct the curve change; rates carry ~no drift (near-martingale)
    eur_chg_arr = pc_ann @ load

    # guardrail: clip every simulated 1-year move to 1.25x the worst observed
    # 52-week move of that factor - keeps t-tails from producing curve shifts
    # or index moves beyond anything in the data
    g = 1.25
    de_ann = d_eur.rolling(h).sum().dropna()
    eur_chg_arr = np.clip(eur_chg_arr, de_ann.min().to_numpy() * g,
                          de_ann.max().to_numpy() * g)
    idx_ann_hist = r_idx.rolling(h).sum().dropna()
    idx_ann = np.clip(idx_ann, idx_ann_hist.min().to_numpy() * g,
                      idx_ann_hist.max().to_numpy() * g)
    u1h = d_usd1.rolling(h).sum().dropna()
    e1h = d_eur1.rolling(h).sum().dropna()
    usd1 = np.clip(usd1, u1h.min() * g, u1h.max() * g)
    eur1 = np.clip(eur1, e1h.min() * g, e1h.max() * g)

    eur_chg = pd.DataFrame(eur_chg_arr, columns=tenors)
    idx_ret = pd.DataFrame(idx_ann, columns=idx_cols)

    return Scenarios(
        dates=pd.Index(range(n_paths), name="path"),
        eur_rate_chg=eur_chg, usd_1y_chg=usd1, eur_1y_chg=eur1,
        idx_logret=idx_ret, n=n_paths,
    )


def run_mc(cfg: Config, n_paths: int = 20_000, tag: str | None = None) -> dict:
    OUT.mkdir(exist_ok=True)
    tag = tag or f"mc_{cfg.deployment}"
    book = build_book(cfg)

    # --- overlay: size the hedge off the MC unhedged equity 99% 1y VaR --------
    sim = simulate(cfg, n_paths=n_paths, nu=5.0)
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
    for label, nu in (("student_t_nu5", 5.0), ("gaussian", np.inf)):
        s = simulate(cfg, n_paths=n_paths, nu=nu, seed=11)
        pnl = reprice(book, s, cfg2)
        pnl.to_csv(OUT / f"{tag}_{label}_pnl.csv", index=False)
        results[label] = {
            "asset": var_stats(pnl["asset_pnl"].to_numpy(), cfg.confidence),
            "surplus": var_stats(pnl["surplus_pnl"].to_numpy(), cfg.confidence),
            "pnl": pnl,
        }

    _report(cfg, book, results, li, eq_var, limit, ratio, n_paths, tag)
    _chart(results, cfg, tag)
    return results


def _report(cfg, book, results, li, eq_var, limit, ratio, n_paths, tag):
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
    A("\n## Method notes\n")
    A("- Student-t (dof 5) gives ~3x the excess kurtosis of a normal and non-zero "
      "tail dependence; `gaussian` (dof inf) is the copula-normal / parametric "
      "reference.")
    A("- Correlation is shrunk 10% toward the mean pairwise correlation "
      "(Ledoit-Wolf style) and repaired to the nearest PD matrix.")
    A("- Rates simulated as absolute weekly changes, indices as log returns; "
      "1-year move = sum of 52 simulated weeks (no iid-normal sqrt-time scaling).")
    A("- Same book, liability and overlay as the HS run in `case3_var.py`; compare "
      "the two headline numbers there.")
    (OUT / f"MC_REPORT_{tag}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nwrote {OUT}/ : MC_REPORT_{tag}.md, {tag}_*_pnl.csv, mc_charts_{tag}.png")


def _chart(results, cfg, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C_T, C_G = "#0072B2", "#E69F00"
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.2))

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
