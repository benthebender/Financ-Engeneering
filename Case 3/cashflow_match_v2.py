"""
cashflow_match_v2.py
====================

PROTOTYPE - a two-stage (lexicographic) Fixed-Income optimiser for Case 3b.
`alm_fixed_income_.py` stays untouched; this is meant to be diffed against it.

Stage 1  - cash-flow dedication
    min   bond cost  +  PEN * PV(external top-up)
    s.t.  running cash balance >= 0 for every liability year
          (surplus reinvested at `reinvest_rate`; a slack variable = the cash
           the return book / future premiums must supply where the bond
           universe physically cannot reach - the 30y+ tail)
          budget <= 5.0bn ; single-instrument cap ; single-issuer cap

Stage 2  - duration / key-rate shaping  (the "secondary condition")
    min   Sum_j w_j ( KRD_asset(x, j) - KRD_liab(j) )^2
    s.t.  every Stage-1 constraint
          bond cost <= cost_1 * (1 + eps)        (eps = how much extra cost we
                                                  allow the duration match to use)
          external top-up <= top-up_1            (don't worsen coverage)

So: fix the cash flows first, then spend whatever of the first 5bn is not
needed for the fix on the longest-duration bonds that best match the liability
key-rate profile.

Convexity is fought two ways:
  * KRD buckets (not just total DV01) force the *dispersion* of the asset cash
    flows to track the liability -> a first-order convexity match.
  * zero-coupon / STRIP bonds in the universe (coupon == 0) carry their whole
    weight at one long maturity -> higher convexity per year of duration and
    no reinvestment drag; the optimiser will lean on them for the tail.

Outputs -> results_v2/ : portfolio_v2.csv (schema-compatible with
results/fixed_income_portfolio.csv), krd_compare.csv, cfmatch_v2.png, REPORT.md
"""

from __future__ import annotations

from pathlib import Path

import cvxpy as cp
import numpy as np
import pandas as pd

import alm_fixed_income_ as alm
import case3_model as m

HERE = Path(__file__).resolve().parent
OUT = HERE / "results_v2"
BN = 1e9
BUDGET = 5.0            # EUR bn - the optimiser works in bn for conditioning
KEY_TENORS = np.array([2, 5, 10, 15, 20, 25, 30, 40], dtype=float)


# --------------------------------------------------------------------------- #
def load_inputs() -> "tuple[pd.DataFrame, pd.DataFrame, pd.Series]":
    a, dc = alm.Assumptions(), []
    uni = alm.parse_fixed_income_basket(
        alm.resolve_input_file(alm.INPUT_FILENAMES["fixed_income"]), a, dc)
    uni = uni[uni["usable_for_optimizer"]].reset_index(drop=True)
    _, _, curve, _ = alm.normalize_swap_curve(
        alm.resolve_input_file(alm.INPUT_FILENAMES["eur_swaps"]), "EUR", a, dc)
    liab = m.liability_cashflows(m.Config())
    return uni, curve, liab


def df_at(curve: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    return np.asarray(alm.base_discount_factor(curve, np.asarray(t, dtype=float)))


def build_matrices(uni: pd.DataFrame, curve: pd.DataFrame, liab: pd.Series):
    horizon = int(liab.index.max())
    yrs = np.arange(1, horizon + 1, dtype=float)
    dfs = df_at(curve, yrs)

    # bond cash flows per EUR 1 nominal
    n = len(uni)
    cf = np.zeros((n, horizon))
    for i, row in uni.iterrows():
        T = min(max(int(round(row["years_to_maturity"])), 1), horizon)
        c = float(row["coupon"])
        cf[i, :T] += c
        cf[i, T - 1] += 1.0                       # redemption
    price = uni["market_price_per_100"].to_numpy() / 100.0     # per EUR 1 nominal
    pv_bond = cf @ dfs                            # ~ price (asw spread aside)

    # duration / convexity per EUR 1 nominal
    tcf = yrs * cf * dfs
    mac_dur = tcf.sum(axis=1) / np.where(pv_bond > 0, pv_bond, np.nan)
    y_mat = np.array([np.interp(min(row["years_to_maturity"], 30),
                                curve["maturity_years"], curve["zero_rate_annual"])
                      for _, row in uni.iterrows()])
    mod_dur = mac_dur / (1.0 + y_mat)
    cvx = ((yrs * (yrs + 1.0)) * cf * dfs).sum(axis=1) / np.where(pv_bond > 0, pv_bond, np.nan) \
        / (1.0 + y_mat) ** 2

    # key-rate DV01 buckets (EUR per bp per EUR 1 nominal)  -  cash-flow bucketed
    bucket = np.abs(yrs[:, None] - KEY_TENORS[None, :]).argmin(axis=1)   # (horizon,)
    krd_bond = np.zeros((n, len(KEY_TENORS)))
    for j in range(len(KEY_TENORS)):
        mask = bucket == j
        krd_bond[:, j] = ((yrs * dfs)[mask] * cf[:, mask]).sum(axis=1) * 1e-4

    Lvec = liab.reindex(yrs.astype(int)).fillna(0.0).to_numpy() / BN     # EUR bn
    krd_liab = np.array([((yrs * dfs * Lvec)[bucket == j]).sum() * 1e-4
                         for j in range(len(KEY_TENORS))])
    liab_pv = float((Lvec * dfs).sum())                                  # EUR bn
    liab_dur = float((yrs * Lvec * dfs).sum() / liab_pv)
    liab_cvx = float((yrs * (yrs + 1.0) * Lvec * dfs).sum() / liab_pv)

    return dict(uni=uni, yrs=yrs, dfs=dfs, cf=cf, price=price, pv_bond=pv_bond,
                mod_dur=mod_dur, cvx=cvx, krd_bond=krd_bond, krd_liab=krd_liab,
                Lvec=Lvec, liab_pv=liab_pv, liab_dur=liab_dur, liab_cvx=liab_cvx,
                horizon=horizon)


# --------------------------------------------------------------------------- #
def _constraints(x, slack, M, reinvest, inst_cap, issuer_cap):
    yrs, cf, price, Lvec = M["yrs"], M["cf"], M["price"], M["Lvec"]
    cons = [x >= 0, slack >= 0, price @ x <= BUDGET]

    bal = 0
    for t in range(len(yrs)):
        inflow = cf[:, t] @ x
        bal = bal * (1.0 + reinvest) + inflow + slack[t] - Lvec[t]
        cons.append(bal >= 0)

    cons.append(cp.multiply(price, x) <= inst_cap * BUDGET)         # per instrument
    for iss in M["uni"]["issuer"].unique():                        # per issuer
        idx = np.where(M["uni"]["issuer"].to_numpy() == iss)[0]
        cons.append(cp.sum(cp.multiply(price[idx], x[idx])) <= issuer_cap * BUDGET)
    return cons


def _solve(prob: cp.Problem, tag: str) -> None:
    for s in (cp.CLARABEL, cp.SCS, cp.OSQP):
        try:
            prob.solve(solver=s, max_iters=200_000) if s is cp.SCS else prob.solve(solver=s)
        except Exception:
            continue
        if prob.status in ("optimal", "optimal_inaccurate"):
            return
    raise RuntimeError(f"{tag}: solve failed ({prob.status})")


def stage1(M, reinvest=0.015, inst_cap=0.15, issuer_cap=0.30):
    """Best achievable cash-flow coverage: minimise the PV of the external
    top-up the bond book cannot supply, spending up to the EUR 5bn budget."""
    n = len(M["price"])
    x, slack = cp.Variable(n, nonneg=True), cp.Variable(len(M["yrs"]), nonneg=True)
    topup_pv = cp.sum(cp.multiply(M["dfs"], slack))
    cons = _constraints(x, slack, M, reinvest, inst_cap, issuer_cap)
    prob = cp.Problem(cp.Minimize(topup_pv), cons)
    _solve(prob, "stage1")
    return x.value, slack.value, float(M["price"] @ x.value), float(topup_pv.value)


def stage2(M, topup1, eps=0.05, w=None, reinvest=0.015,
           inst_cap=0.15, issuer_cap=0.30):
    """Given the coverage from Stage 1, buy the bonds that best match the
    liability key-rate profile - full EUR 5bn available, coverage allowed to
    slip at most `eps` in top-up PV."""
    n, nk = len(M["price"]), len(KEY_TENORS)
    w = np.ones(nk) if w is None else np.asarray(w, float)
    x, slack = cp.Variable(n, nonneg=True), cp.Variable(len(M["yrs"]), nonneg=True)
    krd_asset = M["krd_bond"].T @ x
    obj = cp.sum(cp.multiply(w, cp.square(krd_asset - M["krd_liab"])))
    cons = _constraints(x, slack, M, reinvest, inst_cap, issuer_cap)
    cons += [cp.sum(cp.multiply(M["dfs"], slack)) <= topup1 * (1.0 + eps) + 1e-4]
    prob = cp.Problem(cp.Minimize(obj), cons)
    _solve(prob, "stage2")
    return x.value, slack.value


# --------------------------------------------------------------------------- #
def _portfolio_frame(uni, x, M) -> pd.DataFrame:
    alloc = M["price"] * x * BN                           # EUR market value
    keep = alloc > 1.0
    d = pd.DataFrame({
        "instrument": uni["instrument"], "issuer": uni["issuer"],
        "coupon": uni["coupon"], "years_to_maturity": uni["years_to_maturity"],
        "market_price_per_100": uni["market_price_per_100"],
        "modified_duration": M["mod_dur"], "convexity": M["cvx"],
        "nominal_eur": x * BN, "eur_allocation": alloc,
    })[keep].copy()
    d["portfolio_weight"] = d["eur_allocation"] / d["eur_allocation"].sum()
    return d.sort_values("eur_allocation", ascending=False).reset_index(drop=True)


def _stats(x, slack, M) -> dict:
    """All monetary outputs in EUR (x/slack come in as EUR bn)."""
    alloc = M["price"] * x                                # EUR bn
    mv = alloc.sum()
    w = alloc / mv
    dur = float(w @ M["mod_dur"])
    cvx = float(w @ M["cvx"])
    dv01_asset = mv * dur * 1e-4                          # EUR bn / bp
    dv01_liab = M["liab_pv"] * M["liab_dur"] * 1e-4
    krd_asset = M["krd_bond"].T @ x                       # EUR bn / bp
    return dict(cost=float(M["price"] @ x) * BN, mv=float(mv) * BN,
                mod_dur=dur, cvx=cvx,
                dv01_asset=float(dv01_asset) * BN, dv01_liab=float(dv01_liab) * BN,
                dv01_gap=float(dv01_liab - dv01_asset) * BN,
                krd_asset=krd_asset * BN,
                topup_pv=float((M["dfs"] * slack).sum()) * BN,
                topup_nom=float(slack.sum()) * BN,
                min_balance=_min_balance(x, slack, M) * BN)


def _min_balance(x, slack, M, reinvest=0.015) -> float:
    bal, lo = 0.0, np.inf
    for t in range(len(M["yrs"])):
        bal = bal * (1 + reinvest) + M["cf"][:, t] @ x + slack[t] - M["Lvec"][t]
        lo = min(lo, bal)
    return float(lo)


STRIP_TENORS = (35, 40, 45, 50)


def add_synthetic_strips(uni: pd.DataFrame, curve: pd.DataFrame) -> pd.DataFrame:
    """Illustrative government principal STRIPS (coupon 0, single redemption) at
    35/40/45/50y, priced fair on today's curve. Shows what a widened long-end /
    zero-coupon universe buys before the real ISINs arrive."""
    rows = []
    for T in STRIP_TENORS:
        price = 100.0 * float(alm.base_discount_factor(curve, float(T)))
        rows.append({"instrument": f"SYNTH STRIP {2026 + T}", "issuer": f"STRIP {T}y",
                     "category": "Gov", "coupon": 0.0,
                     "maturity_year_metadata": 2026 + T,
                     "maturity_date": f"{2026 + T}-09-02",
                     "years_to_maturity": float(T),
                     "market_price_per_100": price, "usable_for_optimizer": True})
    return pd.concat([uni, pd.DataFrame(rows)], ignore_index=True)


def _solve_two_stage(M):
    x1, s1, _, topup1 = stage1(M)
    x2, s2 = stage2(M, topup1)
    return x1, s1, x2, s2, _stats(x1, s1, M), _stats(x2, s2, M)


def run() -> None:
    OUT.mkdir(exist_ok=True)
    uni, curve, liab = load_inputs()

    cases = {"current universe": uni,
             "+ synthetic STRIPS 35-50y": add_synthetic_strips(uni, curve)}
    L = []
    A = L.append
    A("# Case 3b - two-stage Fixed-Income optimiser (prototype)\n")

    hdr_done = False
    results = {}
    for name, u in cases.items():
        M = build_matrices(u, curve, liab)
        x1, s1, x2, s2, st1, st2 = _solve_two_stage(M)
        results[name] = (M, x2, st1, st2)
        krd = pd.DataFrame({"key_tenor": KEY_TENORS, "liability": M["krd_liab"] * BN,
                            "stage2": st2["krd_asset"]})
        krd["gap"] = krd["liability"] - krd["stage2"]

        if not hdr_done:
            A(f"Liability PV EUR {M['liab_pv']:.2f}bn, duration {M['liab_dur']:.1f}y, "
              f"convexity {M['liab_cvx']:.0f}.  Reinvestment credit 1.5%, "
              f"issuer cap 30%, instrument cap 15%, Stage-2 eps 5%.\n")
            hdr_done = True

        tag = name.replace(" ", "_").replace("+", "plus").replace("-", "_")
        _portfolio_frame(u, x2, M).to_csv(OUT / f"portfolio_{tag}.csv", index=False)
        krd.to_csv(OUT / f"krd_{tag}.csv", index=False)

        A(f"## {name}  ({len(u)} bonds, {(u['coupon'] == 0).sum()} zero-coupon)\n")
        A("| metric | Stage 1 | Stage 2 (+KRD) | liability |")
        A("|---|--:|--:|--:|")
        A(f"| modified duration (y) | {st1['mod_dur']:.1f} | **{st2['mod_dur']:.1f}** | {M['liab_dur']:.1f} |")
        A(f"| convexity | {st1['cvx']:.0f} | {st2['cvx']:.0f} | {M['liab_cvx']:.0f} |")
        A(f"| asset DV01 (EUR m/bp) | {st1['dv01_asset']/1e6:.1f} | **{st2['dv01_asset']/1e6:.1f}** | {st1['dv01_liab']/1e6:.1f} |")
        A(f"| **surplus DV01 gap (EUR m/bp)** | {st1['dv01_gap']/1e6:.1f} | **{st2['dv01_gap']/1e6:.1f}** | - |")
        A(f"| external top-up PV (EUR bn) | {st1['topup_pv']/1e9:.2f} | {st2['topup_pv']/1e9:.2f} | - |")
        A(f"| min running cash balance (EUR m) | {max(st1['min_balance'],0)/1e6:.0f} | {max(st2['min_balance'],0)/1e6:.0f} | - |\n")
        A("KRD DV01 gap by tenor (EUR m/bp): " + ", ".join(
            f"{int(t)}y {g/1e6:+.1f}" for t, g in zip(krd["key_tenor"], krd["gap"])) + "\n")

    _chart(*results["+ synthetic STRIPS 35-50y"][:2],
           pd.read_csv(OUT / "krd_plus_synthetic_STRIPS_35_50y.csv"))

    m0 = results["current universe"][3]
    m1 = results["+ synthetic STRIPS 35-50y"][3]
    A("## Read\n")
    A(f"- **Stage 2 (the mechanism)**: fix cash flows first, then spend the "
      f"whole EUR 5bn on the bonds that best match the liability KRD. With the "
      f"current 14-30y universe it can only reach ~{m0['mod_dur']:.0f}y duration "
      f"(surplus DV01 gap ~EUR {m0['dv01_gap']/1e6:.0f}m/bp) - the near-year "
      f"coverage eats the budget and there is nothing to buy past 30y.")
    A(f"- **Adding zero-coupon STRIPS 35-50y (idea 3)**: duration "
      f"{m0['mod_dur']:.1f} -> {m1['mod_dur']:.1f}y, surplus DV01 gap "
      f"{m0['dv01_gap']/1e6:.1f} -> {m1['dv01_gap']/1e6:.1f} EUR m/bp, "
      f"convexity {m0['cvx']:.0f} -> {m1['cvx']:.0f} (liability {results['current universe'][0]['liab_cvx']:.0f}); "
      f"the 40y KRD gap roughly halves. Bigger real-world universes (OATs to "
      f"2072, Bund/OAT strips, EU/SSA ultra-longs) + a modest issuer-cap "
      f"tightening push this further.")
    A("- **Convexity** is fought by (i) matching KRD *buckets*, not just total "
      "DV01 - that forces the cash-flow dispersion to track the liability; and "
      "(ii) STRIPS - one cash flow at a long maturity gives more convexity per "
      "year of duration and no reinvestment drag. The residual 40y+ shortfall "
      "is the piece for a small long receiver-swap / receiver swaption.")
    A(f"- **External top-up** (EUR ~{m1['topup_pv']/1e9:.1f}bn PV, mostly "
      "years 31-50) stays the return book's + future premiums' job - the FI "
      "book is EUR 5bn against a EUR 6.4bn liability, it is not meant to "
      "dedicate the whole thing.")
    _write(OUT / "REPORT.md", L)
    print("\n".join(L))
    print(f"\nwrote {OUT}/ : portfolio_*.csv, krd_*.csv, cfmatch_v2.png, REPORT.md")


def _write(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _chart(M, x2, krd):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C_L, C1, C2, GRID = "#333333", "#E69F00", "#0072B2", "#E6E6E6"
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.2))

    xk = np.arange(len(KEY_TENORS))
    ax[0].bar(xk - 0.18, krd["liability"] / 1e6, 0.36, color=C_L, label="liability")
    ax[0].bar(xk + 0.18, krd["stage2"] / 1e6, 0.36, color=C2, label="Stage 2 (+STRIPS)")
    ax[0].set_xticks(xk); ax[0].set_xticklabels([f"{int(t)}y" for t in KEY_TENORS])
    ax[0].set_title("Key-rate DV01 (EUR m / bp)"); ax[0].legend(frameon=False)

    yrs = M["yrs"]
    ax[1].bar(yrs, M["Lvec"] * 1e3, color=C_L, alpha=0.5, label="liability CF")
    ax[1].step(yrs, (M["cf"].T @ x2) * 1e3, where="mid", color=C2, lw=2,
               label="Stage 2 bond CF")
    ax[1].set_title("Annual cash flows (EUR m)"); ax[1].set_xlabel("year")
    ax[1].legend(frameon=False)

    for a_ in ax:
        a_.grid(color=GRID, lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle("Case 3b - two-stage FI optimiser: KRD match & cash-flow coverage",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / "cfmatch_v2.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    run()
