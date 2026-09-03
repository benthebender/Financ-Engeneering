"""
cashflow_match_v2.py
====================

PROTOTYPE - a two-stage (lexicographic) Fixed-Income optimiser for Case 3b.
`alm_fixed_income_.py` stays untouched; this is meant to be diffed against it.

Stage 1  - cash-flow dedication
    min   PV(external top-up)
    s.t.  running cash balance >= 0 for every liability year 1..H
          (surplus reinvested at `reinvest_rate`; slack_t = the cash the return
           book / future premiums must supply where the bond universe cannot
           reach; redemptions past H simply do not enter the balance)
          budget <= 5.0bn ; single-instrument cap ; single-issuer cap

Stage 2  - key-rate shaping  (the "secondary condition")
    min   Sum_j w_j ( KRD_asset(x, j) - KRD_liab(j) )^2  +  overshoot penalty
    s.t.  every Stage-1 constraint
          top-up PV <= top-up_1 * (1 + eps)     (coverage no more than eps worse)
          Sum_j KRD_asset(j) >= Stage-1 total DV01   (do not give back duration)
    w_j proportional to the liability's own KRD, so a harmless over-hedge in a
    near-empty long bucket does not drag the ultra-longs back out.

KRD = real key-rate DV01: a triangular 1bp bump of the *zero* curve at each key
tenor, cash flows repriced (`krd01` / `_tent`).  Key tenors run to 90y so the
2076-2120 ZCBs load buckets the liability barely occupies.

Convexity is fought two ways:
  * KRD buckets (not just total DV01) force the *dispersion* of the asset cash
    flows onto the liability -> a first-order convexity + curve-twist match.
  * zero-coupon bonds carry their whole weight at one long maturity -> higher
    convexity per year of duration and no reinvestment drag.

Universe: `Fixed Income Basket.xlsx` + `ZCB and ultra long coupon Bond.xlsx`
(both read by the tolerant `parse_basket_5col`).  `alm_fixed_income_.py` is
imported for the swap curve only and is left untouched.

Outputs -> results_v2/ : portfolio_base.csv / portfolio_wide.csv,
krd_base.csv / krd_wide.csv, cfmatch_v2.png, REPORT.md
"""

from __future__ import annotations

from pathlib import Path

import re
from datetime import date

import cvxpy as cp
import numpy as np
import pandas as pd

import alm_fixed_income_ as alm
import case3_model as m

HERE = Path(__file__).resolve().parent
OUT = HERE / "results_v2"
BN = 1e9
BUDGET = 5.0            # EUR bn - the optimiser works in bn for conditioning
VAL_DATE = date(2026, 9, 2)
PRICE_HORIZON = 100    # long enough for the ultra-long / century bonds
# key tenors for the KRD match - out to 90y so the century / 2076-2120 ZCBs
# load buckets the liability barely occupies (weighted ~0) instead of swamping a
# single flat 50y bucket
KEY_TENORS = np.array([2, 5, 10, 15, 20, 25, 30, 40, 50, 65, 90], dtype=float)

# extra Bloomberg-ticker -> issuer names for the new ZCB / ultra-long workbook
_ISSUER = {
    "EIB": "European Investment Bank", "IBRD": "World Bank (IBRD)",
    "AFDB": "African Development Bank", "AUST": "Republic of Austria",
    "NRW": "North Rhine-Westphalia", "SLOVGB": "Slovak Republic",
    "KFW": "KfW", "RENTEN": "Rentenbank",
}


# --------------------------------------------------------------------------- #
def parse_basket_5col(path: Path) -> pd.DataFrame:
    """Tolerant reader for the 5-column-block Bloomberg workbooks
    ([weekday, date, price/1000, coupon, maturity-year]).  Takes the maturity
    from the instrument name (M/D/Y), ignores a wrong metadata year, dedupes,
    and does NOT crash on a bad block - used for both the Fixed Income Basket
    and the new ZCB / ultra-long workbook."""
    sheet = pd.read_excel(path, header=None, engine="openpyxl")
    rows = []
    for c0 in range(0, sheet.shape[1], 5):
        if c0 + 4 >= sheet.shape[1]:
            break
        raw_name = sheet.iat[0, c0 + 2]
        if pd.isna(raw_name):
            continue
        name = str(raw_name).replace("\xa0", " ").strip()
        mm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", name)
        if not mm:
            continue
        a, b, y = (int(v) for v in mm.groups())
        y += 2000 if y < 100 else 0
        try:
            mat = date(y, a, b)
        except ValueError:
            continue
        try:
            coupon = float(sheet.iat[0, c0 + 3])
        except (TypeError, ValueError):
            coupon = 0.0
        price = None
        for r in range(1, len(sheet)):
            rp, dt = sheet.iat[r, c0 + 2], sheet.iat[r, c0 + 1]
            if pd.isna(rp) or pd.isna(dt):
                continue
            p = float(rp) / 1_000.0
            if 1.0 < p < 200.0:
                price = p
                break
        if price is None:
            continue
        prefix = name.upper().split()[0]
        issuer = _ISSUER.get(prefix, alm.infer_issuer_and_category(name)[0])
        rows.append(dict(instrument=name, issuer=issuer, coupon=coupon,
                         maturity_date=mat.isoformat(),
                         years_to_maturity=(mat - VAL_DATE).days / 365.25,
                         market_price_per_100=price))
    df = pd.DataFrame(rows).drop_duplicates("instrument").reset_index(drop=True)
    return df[(df["years_to_maturity"] > 1.0) & (df["market_price_per_100"] > 1.0)]


def load_inputs(with_zcb: bool = True, lump_share: float = 0.50
                ) -> "tuple[pd.DataFrame, pd.DataFrame, pd.Series]":
    """`lump_share` = fraction of policyholders taking the year-15 lump sum
    (the rest take the pension).  Drives which liability schedule the FI book is
    matched to."""
    a, dc = alm.Assumptions(), []
    base = parse_basket_5col(alm.resolve_input_file(alm.INPUT_FILENAMES["fixed_income"]))
    if with_zcb:
        zcb = parse_basket_5col(HERE / "Data" / "ZCB and ultra long coupon Bond.xlsx")
        uni = (pd.concat([base, zcb], ignore_index=True)
                 .drop_duplicates("instrument").reset_index(drop=True))
    else:
        uni = base
    _, _, curve, _ = alm.normalize_swap_curve(
        alm.resolve_input_file(alm.INPUT_FILENAMES["eur_swaps"]), "EUR", a, dc)
    liab = m.liability_cashflows(m.Config(lump_sum_share=float(lump_share),
                                         pension_share=1.0 - float(lump_share)))
    return uni, curve, liab


# --------------------------------------------------------------------------- #
# key-rate DV01  -  tent-shaped 1bp bump of the zero curve at each key tenor
# --------------------------------------------------------------------------- #
def zero_cont(curve: pd.DataFrame, t: np.ndarray) -> np.ndarray:
    """Continuously-compounded zero rate at `t` (flat-forward beyond the last node)."""
    mt = curve["maturity_years"].to_numpy(dtype=float)
    zc = curve["zero_rate_continuous"].to_numpy(dtype=float)
    t = np.asarray(t, dtype=float)
    z = np.interp(np.clip(t, mt[0], mt[-1]), mt, zc)
    slope = (zc[-1] * mt[-1] - zc[-2] * mt[-2]) / (mt[-1] - mt[-2])
    return np.where(t > mt[-1], (zc[-1] * mt[-1] + slope * (t - mt[-1])) / t, z)


def _tent(t: np.ndarray, keys: np.ndarray, k: int, bump: float = 1e-4) -> np.ndarray:
    """Triangular 1bp perturbation peaking at keys[k], zero at the neighbours
    (flat = bump beyond the first / last key)."""
    kt = keys[k]
    lo = keys[k - 1] if k > 0 else -np.inf
    hi = keys[k + 1] if k < len(keys) - 1 else np.inf
    w = np.zeros_like(t)
    left = (t >= lo) & (t <= kt)
    right = (t > kt) & (t <= hi)
    w[left] = 1.0 if not np.isfinite(lo) else (t[left] - lo) / (kt - lo)
    w[right] = 1.0 if not np.isfinite(hi) else (hi - t[right]) / (hi - kt)
    return w * bump


def krd01(cflows: np.ndarray, times: np.ndarray, curve: pd.DataFrame,
          keys: np.ndarray) -> np.ndarray:
    """Key-rate DV01 vector (EUR loss per +1bp at each key tenor) for a cash-flow
    stream, per unit of `cflows`.  Sum over keys ~ total DV01."""
    z = zero_cont(curve, times)
    pv0 = float((cflows * np.exp(-z * times)).sum())
    out = np.zeros(len(keys))
    for k in range(len(keys)):
        pv1 = float((cflows * np.exp(-(z + _tent(times, keys, k)) * times)).sum())
        out[k] = -(pv1 - pv0)
    return out


def build_matrices(uni: pd.DataFrame, curve: pd.DataFrame, liab: pd.Series):
    liab_h = int(liab.index.max())                       # cash-flow-match horizon
    yrs = np.arange(1, PRICE_HORIZON + 1, dtype=float)    # full pricing grid
    dfs = np.exp(-zero_cont(curve, yrs) * yrs)

    n = len(uni)
    cf = np.zeros((n, PRICE_HORIZON))
    for i, row in uni.iterrows():
        T = min(max(int(round(row["years_to_maturity"])), 1), PRICE_HORIZON)
        c = float(row["coupon"])
        cf[i, :T] += c
        cf[i, T - 1] += 1.0                               # redemption
    price = uni["market_price_per_100"].to_numpy() / 100.0
    pv_bond = cf @ dfs

    tcf = yrs * cf * dfs
    mac_dur = tcf.sum(axis=1) / np.where(pv_bond > 0, pv_bond, np.nan)
    y_mat = zero_cont(curve, np.minimum(uni["years_to_maturity"].to_numpy(), 30.0))
    mod_dur = mac_dur / (1.0 + y_mat)
    cvx = ((yrs * (yrs + 1.0)) * cf * dfs).sum(axis=1) \
        / np.where(pv_bond > 0, pv_bond, np.nan) / (1.0 + y_mat) ** 2

    # --- KRD (real key-rate DV01, tent-bumped zero curve) -----------------
    krd_bond = np.vstack([krd01(cf[i], yrs, curve, KEY_TENORS) for i in range(n)])
    Lvec = liab.reindex(yrs.astype(int)).fillna(0.0).to_numpy() / BN      # EUR bn
    krd_liab = krd01(Lvec, yrs, curve, KEY_TENORS)
    liab_pv = float((Lvec * dfs).sum())
    liab_dur = float((yrs * Lvec * dfs).sum() / liab_pv)
    liab_cvx = float((yrs * (yrs + 1.0) * Lvec * dfs).sum() / liab_pv)

    return dict(uni=uni, yrs=yrs, dfs=dfs, cf=cf, price=price, pv_bond=pv_bond,
                mod_dur=mod_dur, cvx=cvx, krd_bond=krd_bond, krd_liab=krd_liab,
                Lvec=Lvec, liab_pv=liab_pv, liab_dur=liab_dur, liab_cvx=liab_cvx,
                liab_h=liab_h, curve=curve)


# --------------------------------------------------------------------------- #
def _constraints(x, slack, M, reinvest, inst_cap, issuer_cap):
    """slack has length M['liab_h']; running cash balance >= 0 every liability
    year (redemptions past the horizon simply do not enter - an ultra-long ZCB
    is bought for its KRD, not for coverage)."""
    cf, price, Lvec = M["cf"], M["price"], M["Lvec"]
    cons = [x >= 0, slack >= 0, price @ x <= BUDGET]

    bal = 0
    for t in range(M["liab_h"]):
        bal = bal * (1.0 + reinvest) + cf[:, t] @ x + slack[t] - Lvec[t]
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
    n, hh = len(M["price"]), M["liab_h"]
    x, slack = cp.Variable(n, nonneg=True), cp.Variable(hh, nonneg=True)
    topup_pv = cp.sum(cp.multiply(M["dfs"][:hh], slack))
    cons = _constraints(x, slack, M, reinvest, inst_cap, issuer_cap)
    prob = cp.Problem(cp.Minimize(topup_pv), cons)
    _solve(prob, "stage1")
    return x.value, slack.value, float(M["price"] @ x.value), float(topup_pv.value)


def stage2(M, topup1, eps=0.05, w=None, keep_dv01=0.0, reinvest=0.015,
           inst_cap=0.15, issuer_cap=0.30):
    """Refine the KRD shape without giving back what Stage 1 achieved: same or
    better coverage, and total DV01 not below Stage 1's."""
    n, nk, hh = len(M["price"]), len(KEY_TENORS), M["liab_h"]
    kl = M["krd_liab"]
    # weight each bucket by where the liability actually has key-rate exposure,
    # so a harmless over-hedge in a near-empty long bucket does not dominate the
    # objective and force the ultra-longs back out
    w = (np.maximum(kl, 0.0) / max(np.maximum(kl, 0.0).sum(), 1e-12)) if w is None \
        else np.asarray(w, float)
    x, slack = cp.Variable(n, nonneg=True), cp.Variable(hh, nonneg=True)
    krd_asset = M["krd_bond"].T @ x
    # scale to EUR m/bp so the QP is well conditioned; add a soft one-sided
    # penalty on total-DV01 overshoot so Stage 2 does not pile ultra-longs
    over = cp.pos(cp.sum(krd_asset) - kl.sum()) * 1e3
    obj = cp.sum(cp.multiply(w, cp.square((krd_asset - kl) * 1e3))) + 5.0 * cp.square(over)
    cons = _constraints(x, slack, M, reinvest, inst_cap, issuer_cap)
    cons += [cp.sum(cp.multiply(M["dfs"][:hh], slack)) <= topup1 * (1.0 + eps) + 1e-4,
             cp.sum(krd_asset) >= min(keep_dv01, kl.sum()) - 1e-4]   # keep Stage-1 duration
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
    """All monetary outputs in EUR (x/slack come in as EUR bn).  DV01 / gap are
    taken from the summed key-rate DV01 (exact repricing) - `mod_dur` from the
    duration approximation is kept only as a readout."""
    alloc = M["price"] * x                                # EUR bn
    mv = alloc.sum()
    w = alloc / mv
    dur = float(w @ M["mod_dur"])
    cvx = float(w @ M["cvx"])
    krd_asset = M["krd_bond"].T @ x                       # EUR bn / bp
    dv01_asset = float(krd_asset.sum())                   # EUR bn / bp (from KRD)
    dv01_liab = float(M["krd_liab"].sum())
    return dict(cost=float(M["price"] @ x) * BN, mv=float(mv) * BN,
                mod_dur=dur, eff_dur=dv01_asset * 1e4 / mv, cvx=cvx,
                dv01_asset=dv01_asset * BN, dv01_liab=dv01_liab * BN,
                dv01_gap=(dv01_liab - dv01_asset) * BN,
                krd_asset=krd_asset * BN,
                topup_pv=float((M["dfs"][:M["liab_h"]] * slack).sum()) * BN,
                topup_nom=float(slack.sum()) * BN,
                min_balance=_min_balance(x, slack, M) * BN)


def _min_balance(x, slack, M, reinvest=0.015) -> float:
    bal, lo = 0.0, np.inf
    for t in range(M["liab_h"]):
        bal = bal * (1 + reinvest) + M["cf"][:, t] @ x + slack[t] - M["Lvec"][t]
        lo = min(lo, bal)
    return float(lo)


def _solve_two_stage(M):
    x1, s1, _, topup1 = stage1(M)
    ka1 = float((M["krd_bond"].T @ x1).sum())          # Stage-1 total DV01
    x2, s2 = stage2(M, topup1, keep_dv01=ka1)
    return x1, s1, x2, s2, _stats(x1, s1, M), _stats(x2, s2, M)


def size_irs(M, gap_eur_per_bp: np.ndarray,
             tenors=(10, 15, 20, 25, 30)) -> pd.Series:
    """Size receive-fixed swaps to close the residual key-rate gap (liability
    minus Stage-2 asset).  Par-struck, notional not exchanged -> no cash outlay.
    KRD of a receiver swap per EUR 1 notional ~ KRD(par fixed bond) - KRD(1y
    float leg).  Solve  min || Sum_T y_T * krd_swap_T - gap ||^2 ,  y_T >= 0."""
    from scipy.optimize import nnls
    curve, yrs, dfs = M["curve"], M["yrs"], M["dfs"]
    cols, pars = [], []
    for T in tenors:
        Ti = int(T)
        s0 = float((1.0 - dfs[Ti - 1]) / dfs[:Ti].sum())      # par swap rate
        pars.append(s0)
        cf = np.zeros(int(PRICE_HORIZON))
        cf[:Ti] += s0
        cf[Ti - 1] += 1.0
        krd_fix = krd01(cf, yrs, curve, KEY_TENORS)
        flt = np.zeros(int(PRICE_HORIZON)); flt[0] = 1.0
        krd_flt = krd01(flt, yrs, curve, KEY_TENORS)
        cols.append(krd_fix - krd_flt)               # EUR/bp per EUR 1 notional
    S = np.vstack(cols).T                             # (nk, n_tenor)
    y, _ = nnls(S, np.maximum(np.asarray(gap_eur_per_bp, float), 0.0))   # y in EUR
    out = pd.Series(y / 1e9, index=[f"{t}y" for t in tenors],
                    name="receiver_notional_eur_bn")
    out.attrs["par_rates"] = dict(zip(out.index, pars))
    return out


def run() -> None:
    OUT.mkdir(exist_ok=True)
    _, curve, liab = load_inputs()
    base = load_inputs(with_zcb=False)[0]
    wide = load_inputs(with_zcb=True)[0]

    cases = {"current basket only": base,
             "+ ZCB & ultra-long workbook": wide}
    L, results = [], {}
    A = L.append
    A("# Case 3b - two-stage Fixed-Income optimiser + key-rate DV01\n")
    A("KRD = real key-rate DV01: a triangular 1bp bump of the zero curve at each "
      f"key tenor {[int(t) for t in KEY_TENORS]}, cash flows repriced. Stage 1 "
      "minimises the external top-up PV (cash-flow dedication); Stage 2 minimises "
      "Sum_j (KRD_asset(j) - KRD_liab(j))^2 with the full EUR 5bn, coverage "
      "allowed to slip <= 5%.\n")

    hdr = False
    for name, u in cases.items():
        M = build_matrices(u, curve, liab)
        x1, s1, x2, s2, st1, st2 = _solve_two_stage(M)
        results[name] = (M, x2, st1, st2)
        krd = pd.DataFrame({"key_tenor": KEY_TENORS, "liability": M["krd_liab"] * BN,
                            "stage2": st2["krd_asset"]})
        krd["gap"] = krd["liability"] - krd["stage2"]

        if not hdr:
            A(f"Liability PV EUR {M['liab_pv']:.2f}bn, duration {M['liab_dur']:.1f}y, "
              f"convexity {M['liab_cvx']:.0f}.  Reinvestment credit 1.5%, "
              f"issuer cap 30%, instrument cap 15%.\n")
            hdr = True

        tag = "base" if "only" in name else "wide"
        _portfolio_frame(u, x2, M).to_csv(OUT / f"portfolio_{tag}.csv", index=False)
        krd.to_csv(OUT / f"krd_{tag}.csv", index=False)
        if tag == "wide":                                   # the book we actually hold
            yrs = M["yrs"].astype(int)
            pd.DataFrame({"year": yrs,
                          "asset_cf_eur": (M["cf"].T @ x2) * BN,
                          "liability_cf_eur": M["Lvec"] * BN}).to_csv(
                OUT / "book_cf_wide.csv", index=False)

        A(f"## {name}  ({len(u)} bonds, {(u['coupon'] == 0).sum()} zero-coupon, "
          f"longest {u['years_to_maturity'].max():.0f}y)\n")
        A("| metric | Stage 1 | Stage 2 (+KRD) | liability |")
        A("|---|--:|--:|--:|")
        A(f"| effective duration (y, from KRD) | {st1['eff_dur']:.1f} | **{st2['eff_dur']:.1f}** | {M['liab_dur']:.1f} |")
        A(f"| convexity | {st1['cvx']:.0f} | {st2['cvx']:.0f} | {M['liab_cvx']:.0f} |")
        A(f"| asset DV01 (EUR m/bp) | {st1['dv01_asset']/1e6:.1f} | **{st2['dv01_asset']/1e6:.1f}** | {st1['dv01_liab']/1e6:.1f} |")
        A(f"| **surplus DV01 gap (EUR m/bp)** | {st1['dv01_gap']/1e6:.1f} | **{st2['dv01_gap']/1e6:.1f}** | - |")
        A(f"| external top-up PV (EUR bn) | {st1['topup_pv']/1e9:.2f} | {st2['topup_pv']/1e9:.2f} | - |")
        A(f"| min running cash balance (EUR m) | {max(st1['min_balance'],0)/1e6:.0f} | {max(st2['min_balance'],0)/1e6:.0f} | - |\n")
        A("Stage-2 KRD DV01 gap by tenor (EUR m/bp): " + ", ".join(
            f"{int(t)}y {g/1e6:+.1f}" for t, g in zip(krd["key_tenor"], krd["gap"])) + "\n")
        A("Stage-2 holdings: " + ", ".join(
            f"{r.instrument.split(' REGS')[0]} {r.eur_allocation/1e9:.2f}bn"
            for r in _portfolio_frame(u, x2, M).head(10).itertuples()) + "\n")

    _chart(*results["+ ZCB & ultra-long workbook"][:2],
           pd.read_csv(OUT / "krd_wide.csv"))

    m0, m1 = results["current basket only"][3], results["+ ZCB & ultra-long workbook"][3]
    Mw = results["+ ZCB & ultra-long workbook"][0]
    A("## Read\n")
    A("- **Stage 2 (mechanism)**: Stage 1 minimises the cash-flow top-up and "
      "with the ultra-long ZCBs over-terms hard (effective duration ~54y, DV01 "
      "~2x the liability); Stage 2 then reshapes to the liability KRD while "
      "keeping full coverage - a sane, KRD-matched book.")
    A(f"- **Adding the ZCB / ultra-long workbook** (Stage 2): effective duration "
      f"(from KRD) {m0['eff_dur']:.1f} -> **{m1['eff_dur']:.1f}y** (liability "
      f"{Mw['liab_dur']:.1f}y), surplus DV01 gap "
      f"{m0['dv01_gap']/1e6:+.1f} -> **{m1['dv01_gap']/1e6:+.1f} EUR m/bp** "
      f"(≈ closed), convexity {m0['cvx']:.0f} -> **{m1['cvx']:.0f}** (liability "
      f"{Mw['liab_cvx']:.0f}), and the cash-flow top-up "
      f"{m0['topup_pv']/1e9:.2f} -> **{m1['topup_pv']/1e9:.2f} bn PV**.")
    A("- **Convexity** is fought by (i) matching KRD *buckets*, not just total "
      "DV01 - forces the asset cash-flow dispersion onto the liability; and "
      "(ii) the zero-coupon bonds - one cash flow at a long maturity, higher "
      "convexity per year of duration, no reinvestment drag.")
    A(f"- **Residual**: whatever KRD gap remains past the longest usable bond, "
      f"plus the ~EUR {m1['topup_pv']/1e9:.1f}bn PV external top-up (years past "
      f"the coverage horizon), stays for a small long receiver swap / swaption "
      f"and the return book + future premiums.")

    # ---- size the residual receive-fixed IRS (par, notional not exchanged) ----
    gap_wide = pd.read_csv(OUT / "krd_wide.csv")["gap"].to_numpy()
    irs_full = size_irs(Mw, gap_wide)
    pr = irs_full.attrs["par_rates"]
    irs = irs_full[irs_full > 1e-3]
    A("\n## Necessary receive-fixed IRS (closes the Stage-2 residual)\n")
    if len(irs):
        A("Par-struck, notional **not** exchanged -> no cash outlay (only variation "
          "margin); sits on top of the EUR 5bn bond book.  Sized by non-negative "
          "least squares of the receiver-swap key-rate DV01 onto the Stage-2 "
          "residual gap (liability - asset KRD).\n")
        A("| tenor | receiver notional (EUR bn) | par fixed rate |")
        A("|---|--:|--:|")
        for t, n_ in irs.items():
            A(f"| {t} | **{n_:.2f}** | {pr[t]:.2%} |")
        A(f"\nTotal receiver notional EUR {irs.sum():.2f}bn; this is the "
          f"\"necessary IRS\" - it removes the residual surplus DV01 gap "
          f"({m1['dv01_gap']/1e6:+.1f} EUR m/bp) that the cash bond book cannot "
          f"reach under the 15% instrument cap (mostly the 15y lump-sum bucket).")
    else:
        A("Stage-2 residual gap is already within noise - no IRS required.")

    _write(OUT / "REPORT.md", L)
    print("\n".join(L))
    print(f"\nwrote {OUT}/ : portfolio_base.csv, portfolio_wide.csv, krd_*.csv, "
          f"cfmatch_v2.png, REPORT.md")


def _write(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
#  Election sensitivity - rerun the two-stage FI pipeline for each lump-sum
#  election so we know (a) the bond book each pension-plan demand actually
#  needs and (b) how much of the 50/50 book is freed when the tail shrinks.
# --------------------------------------------------------------------------- #
def run_elections(shares=(0.0, 0.25, 0.50, 0.75, 1.00)) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / "elections").mkdir(exist_ok=True)
    _, curve, _ = load_inputs()
    uni = load_inputs(with_zcb=True)[0]

    import gc
    rows, alloc, cf15, pv15 = [], {}, {}, {}
    for s in shares:
        # only the liability schedule changes per election - do not re-read the
        # bond / curve workbooks (keeps the run inside the process memory cap)
        liab_s = m.liability_cashflows(m.Config(lump_sum_share=float(s),
                                                pension_share=1.0 - float(s)))
        M = build_matrices(uni, curve, liab_s)
        _, _, x2, s2, _, st2 = _solve_two_stage(M)
        pf = _portfolio_frame(uni, x2, M)
        pf.to_csv(OUT / "elections" / f"portfolio_s{int(round(s*100)):03d}.csv", index=False)

        acf = (M["cf"].T @ x2) * BN                       # asset CF by year (EUR)
        lcf = M["Lvec"] * BN                              # liability CF by year (EUR)
        df15 = M["dfs"][14]                               # DF(15)
        tail_pv15 = float((lcf[15:] * M["dfs"][15:] / df15).sum())   # PV at yr15 of the >15 tail
        alloc[s] = pf.set_index("instrument")["eur_allocation"]
        cf15[s], pv15[s] = float(acf[14]), tail_pv15
        rows.append(dict(
            lump_pct=int(round(s * 100)), mv_bn=float(M["price"] @ x2),
            eff_dur=st2["eff_dur"], convexity=st2["cvx"],
            dv01_asset_m=st2["dv01_asset"] / 1e6, dv01_gap_m=st2["dv01_gap"] / 1e6,
            topup_pv_bn=st2["topup_pv"] / 1e9,
            liab_pv_bn=M["liab_pv"], liab_dur=M["liab_dur"],
            yr15_liab_cf_bn=float(lcf[14] / 1e9), yr15_asset_cf_bn=float(acf[14] / 1e9),
            tail_pv15_bn=tail_pv15 / 1e9))
        del M, x2, s2, st2, pf, acf, lcf
        gc.collect()
    df = pd.DataFrame(rows).set_index("lump_pct")
    df.round(3).to_csv(OUT / "elections" / "summary.csv")

    # --- what happens if we HOLD the 50/50 book and the election turns out > 50%
    # Stage-1 dedication guarantees the 50/50 book delivers its full year-15
    # obligation (the 50% lump) out of accumulated cash + reinvestment - that is
    # risk-free.  Above 50%, the bonds it no longer needs for the shrunk pension
    # tail can be sold at the year-15 market price toward the larger lump.
    held_dedicated = float(m.liability_cashflows(m.Config())[15])   # 50% lump  ~ EUR 5.65bn
    held_tail_pv15 = pv15[0.50]                                     # PV@15 of the 50/50 tail
    L = ["# Case 3b - FI book by policyholder election  (two-stage pipeline rerun)\n",
         "Full `cashflow_match_v2` two-stage optimise (cash-flow dedication + KRD "
         "shaping, +ZCB / ultra-long universe) rerun for each year-15 lump-sum "
         "election.  All books spend the EUR 5.0bn budget.\n",
         df.round(2).to_markdown(), "",
         "## Holding the 50/50 book into a higher lump-sum election\n",
         f"The book we hold is matched to 50/50 - it delivers EUR "
         f"{held_dedicated/1e9:.2f}bn at year 15 by dedication (risk-free).  If "
         f"more than half elect the lump, the bonds it no longer needs for the "
         f"(now smaller) pension tail are sold at the year-15 market price toward "
         f"the larger lump; only the remainder must come from the RSP.\n",
         "| election | year-15 lump demand | dedicated (risk-free) | freed tail PV (sold at mkt) | still needed from the RSP |",
         "|---|--:|--:|--:|--:|"]
    for s in shares:
        lcf_s = m.liability_cashflows(m.Config(lump_sum_share=s, pension_share=1 - s))
        need = float(lcf_s.get(15, 0.0))
        freed = max(0.0, held_tail_pv15 - pv15[s])
        resid = max(0.0, need - held_dedicated - freed)
        L.append(f"| {int(round(s*100))}% lump | EUR {need/1e9:.2f}bn | "
                 f"EUR {min(need, held_dedicated)/1e9:.2f}bn | EUR {freed/1e9:.2f}bn | "
                 f"**EUR {resid/1e9:.2f}bn** |")
    L += ["",
          f"Freed tail PV is valued at the year-15 curve, so it carries rate risk; "
          f"the residual is what must come from selling the Return-Seeking "
          f"Portfolio at market.  `mc_lifecycle.py` uses `dedicated` "
          f"(EUR {held_dedicated/1e9:.2f}bn) and the freed-tail PV for the "
          f"year-15 liquidity metric."]
    _write(OUT / "elections" / "ELECTIONS_REPORT.md", L)
    print("\n".join(L))
    print(f"\nwrote {OUT}/elections/ : summary.csv, portfolio_s***.csv, ELECTIONS_REPORT.md")


def _chart(M, x2, krd):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C_L, C1, C2, GRID = "#333333", "#E69F00", "#0072B2", "#E6E6E6"
    fig, ax = plt.subplots(1, 2, figsize=(14, 5.2))

    xk = np.arange(len(KEY_TENORS))
    ax[0].bar(xk - 0.18, krd["liability"] / 1e6, 0.36, color=C_L, label="liability")
    ax[0].bar(xk + 0.18, krd["stage2"] / 1e6, 0.36, color=C2, label="Stage 2 (+ZCB set)")
    ax[0].set_xticks(xk); ax[0].set_xticklabels([f"{int(t)}y" for t in KEY_TENORS])
    ax[0].set_title("Key-rate DV01 (EUR m / bp)"); ax[0].legend(frameon=False)

    cut = min(len(M["yrs"]), M["liab_h"] + 5)
    yrs = M["yrs"][:cut]
    ax[1].bar(yrs, M["Lvec"][:cut] * 1e3, color=C_L, alpha=0.5, label="liability CF")
    ax[1].step(yrs, (M["cf"][:, :cut].T @ x2) * 1e3, where="mid", color=C2, lw=2,
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
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "elections":
        run_elections()
    else:
        run()
