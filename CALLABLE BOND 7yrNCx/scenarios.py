"""
scenarios.py
============

Curve sensitivity / scenario analysis for a callable bond, from the **issuer's**
point of view (the case issuer is Vonovia, a fixed-rate borrower).

Two questions, one table
------------------------
1. *Primary-issuance* view - re-solve the par coupon on each shocked curve:
   "if we issued this callable today under that curve, what coupon would we pay,
   and how big is the call give-up over a bullet?"
2. *Mark-to-market* view - hold the issued coupon fixed and re-price the debt:
   "what is our outstanding callable liability worth, versus the equivalent
   bullet, and how much of the move is the embedded call?"

Issuer benefit in a scenario
----------------------------
The bond is a *liability*. A fall in its value is a gain to the issuer, so

    issuer_pnl              = base_liability_value - scenario_liability_value
    call_contribution       = call_value(scenario) - call_value(base)

`call_value = straight - callable >= 0` is the worth of the embedded call the
issuer holds; it grows when rates rally (the call moves in the money) and decays
when they sell off. `call_contribution` is "how much did being callable rather
than bullet help us in this scenario".

Curve shocks
------------
Every shock is expressed as **basis points added to the par swap rate at each
tenor**, then the curve is re-bootstrapped. Builders: `parallel`, `steepener` /
`flattener` (2s10s twist), `bull_flattener`, `bear_steepener`, `belly`
(mid-curve bulge / butterfly body), `twist` (general linear), `custom`.

Public API
----------
    scenario_analysis(base_rates_pct, vols, spec, engine="hw",
                      scenarios=DEFAULT_SCENARIOS, notional=100.0,
                      struck_coupon=None, **engine_kw) -> pd.DataFrame
    key_rate_dv01(base_rates_pct, vols, spec, struck_coupon, ...) -> pd.DataFrame
    effective_risk(base_rates_pct, vols, spec, struck_coupon, ...) -> pd.DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from curve_io import build_discount_curve, years_of_tenor
from engine import build_engine
from pricer import CallableSpec, _resolve_vol, par_coupon, validate_against_curve

__all__ = [
    "CurveScenario",
    "parallel", "steepener", "flattener", "bull_flattener", "bear_steepener",
    "belly", "twist", "custom",
    "DEFAULT_SCENARIOS",
    "scenario_analysis", "key_rate_dv01", "effective_risk",
]


# --------------------------------------------------------------------------- #
# curve shocks
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CurveScenario:
    name: str
    fn: Callable[[float], float]   # tenor in years -> shift in basis points
    note: str = ""

    def shift_bp(self, tenors_years) -> np.ndarray:
        return np.array([float(self.fn(float(t))) for t in tenors_years])

    def apply(self, base_rates_pct: pd.Series) -> pd.Series:
        t = np.array([years_of_tenor(k) for k in base_rates_pct.index], dtype=float)
        shocked = base_rates_pct.to_numpy() + self.shift_bp(t) / 100.0  # bp -> percent
        return pd.Series(shocked, index=base_rates_pct.index,
                         name=base_rates_pct.name)

    def summary_bp(self, tenors_years=(1, 10)) -> str:
        a, b = (self.fn(tenors_years[0]), self.fn(tenors_years[-1]))
        return f"{a:+.0f}/{b:+.0f}"


def _lin(short_bp: float, long_bp: float, lo: float = 1.0, hi: float = 10.0):
    span = hi - lo
    return lambda t: short_bp + (long_bp - short_bp) * (min(max(t, lo), hi) - lo) / span


def parallel(bp: float) -> CurveScenario:
    tag = "unchanged" if bp == 0 else f"parallel {bp:+.0f}bp"
    return CurveScenario(tag, lambda _t: bp, "whole curve shifts by the same amount")


def twist(short_bp: float, long_bp: float, lo: float = 1.0, hi: float = 10.0,
          name: str | None = None) -> CurveScenario:
    f = _lin(short_bp, long_bp, lo, hi)
    return CurveScenario(name or f"twist {short_bp:+.0f}->{long_bp:+.0f}bp", f,
                         "linear in tenor between the 1y and 10y shifts")


def steepener(bp: float) -> CurveScenario:
    """2s10s steepener of `bp`: front down bp/2, back up bp/2, pivot in the middle."""
    return twist(-bp / 2, +bp / 2, name=f"steepener +{bp:.0f}bp (2s10s)")


def flattener(bp: float) -> CurveScenario:
    return twist(+bp / 2, -bp / 2, name=f"flattener +{bp:.0f}bp (2s10s)")


def bull_flattener(bp: float) -> CurveScenario:
    """Rates rally and the curve flattens: front -bp/2, back -3bp/2."""
    return twist(-0.5 * bp, -1.5 * bp, name=f"bull flattener {bp:.0f}bp")


def bear_steepener(bp: float) -> CurveScenario:
    """Rates sell off and the curve steepens: front +bp/2, back +3bp/2."""
    return twist(+0.5 * bp, +1.5 * bp, name=f"bear steepener {bp:.0f}bp")


def belly(bp: float, center: float = 5.0, halfwidth: float = 3.0,
          name: str | None = None) -> CurveScenario:
    """Tent-shaped bump peaking at `center` (mid-curve bulge / butterfly body).

    +bp cheapens the belly (mid rates up) relative to the wings.
    """
    def f(t: float) -> float:
        return bp * max(0.0, 1.0 - abs(t - center) / halfwidth)
    return CurveScenario(name or f"mid-curve bulge {bp:+.0f}bp @{center:.0f}y", f,
                         "wings unchanged, mid moves")


def custom(shifts_bp: dict, name: str = "custom") -> CurveScenario:
    """Per-tenor bp shifts, e.g. {2: -25, 5: +10, 10: +40}; linear between keys."""
    xs = np.array(sorted(shifts_bp), dtype=float)
    ys = np.array([shifts_bp[k] for k in sorted(shifts_bp)], dtype=float)
    return CurveScenario(name, lambda t: float(np.interp(t, xs, ys)),
                         "linear interpolation of the given tenor shifts")


#: A spread of standard rate scenarios for the issuer.
DEFAULT_SCENARIOS: list[CurveScenario] = [
    parallel(0),
    parallel(-200), parallel(-100), parallel(-50),
    parallel(+50), parallel(+100), parallel(+200),
    bull_flattener(100),
    bear_steepener(100),
    steepener(50),
    flattener(50),
    belly(+50), belly(-50),
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _exercise_set(spec: CallableSpec, res) -> set[int]:
    if spec.is_single:
        return {int(res.best_call_year)}
    return spec.exercise_set()


def _price_one(rates_pct, vols, spec, engine, engine_kw, struck_coupon):
    """Reprice `spec` on one curve; return a dict of metrics (per 100 face)."""
    curve = build_discount_curve(rates_pct)
    validate_against_curve(spec, curve)
    res = par_coupon(curve, vols, spec, engine, **engine_kw)
    exset = _exercise_set(spec, res)

    eng = build_engine(engine, curve=curve, maturity=spec.maturity,
                       vol=_resolve_vol(vols, spec.maturity), **engine_kw)

    c_star = res.par_coupon if struck_coupon is None else float(struck_coupon)
    callable_mtm = eng.price(c_star, exset, spec.call_price)
    bullet_mtm = eng.straight_price(c_star)

    return {
        "par_coupon_bp": res.par_coupon * 1e4,
        "bullet_coupon_bp": res.bullet_par_coupon * 1e4,
        "spread_bp": res.spread_over_bullet * 1e4,
        "best_call_year": res.best_call_year,
        "callable_mtm": callable_mtm,
        "bullet_mtm": bullet_mtm,
        "call_value": bullet_mtm - callable_mtm,
        "_c_star": c_star,
        "_exset": tuple(sorted(exset)),
    }


# --------------------------------------------------------------------------- #
# scenario table
# --------------------------------------------------------------------------- #
def scenario_analysis(base_rates_pct: pd.Series, vols, spec: CallableSpec,
                      engine: str = "hw",
                      scenarios: "list[CurveScenario] | None" = None,
                      notional: float = 100.0,
                      struck_coupon: "float | None" = None,
                      **engine_kw) -> pd.DataFrame:
    """One row per scenario: repriced par coupon, spread, call value, and the
    issuer P&L on the outstanding (fixed-coupon) liability.

    ``struck_coupon`` - the coupon the bond was actually issued at (decimal).
    ``None`` -> use the base-curve par coupon, i.e. assume it was struck at par
    today (base ``callable_mtm`` is then ~100).

    ``notional`` - face amount; money columns scale by ``notional / 100``.
    All ``d_*`` columns are the scenario value minus the base value.
    """
    scenarios = list(DEFAULT_SCENARIOS if scenarios is None else scenarios)
    scale = notional / 100.0

    base = _price_one(base_rates_pct, vols, spec, engine, engine_kw, struck_coupon)
    c_star = base["_c_star"]

    tenors = [years_of_tenor(k) for k in base_rates_pct.index]
    rows = []
    for scen in [None] + scenarios:
        if scen is None:
            name, shift_lbl, m = "base", "0/0", base
        else:
            name = scen.name
            shift_lbl = scen.summary_bp((tenors[0], tenors[-1]))
            m = _price_one(scen.apply(base_rates_pct), vols, spec, engine,
                           engine_kw, c_star)

        issuer_pnl = (base["callable_mtm"] - m["callable_mtm"]) * scale
        bullet_pnl = (base["bullet_mtm"] - m["bullet_mtm"]) * scale
        rows.append({
            "scenario": name,
            "shift_1y/10y_bp": shift_lbl,
            "par_coupon_bp": m["par_coupon_bp"],
            "d_par_bp": m["par_coupon_bp"] - base["par_coupon_bp"],
            "spread_bp": m["spread_bp"],
            "d_spread_bp": m["spread_bp"] - base["spread_bp"],
            "callable_mtm": m["callable_mtm"],
            "call_value_pts": m["call_value"],
            "d_call_value_pts": m["call_value"] - base["call_value"],
            "issuer_pnl": issuer_pnl,
            "bullet_pnl": bullet_pnl,
            "call_contribution": issuer_pnl - bullet_pnl,
        })

    df = pd.DataFrame(rows).set_index("scenario")
    df.attrs["struck_coupon_bp"] = c_star * 1e4
    df.attrs["notional"] = notional
    return df


# --------------------------------------------------------------------------- #
# key-rate (bucketed) DV01
# --------------------------------------------------------------------------- #
def key_rate_dv01(base_rates_pct: pd.Series, vols, spec: CallableSpec,
                  struck_coupon: "float | None" = None, engine: str = "hw",
                  notional: float = 100.0, bump_bp: float = 10.0,
                  **engine_kw) -> pd.DataFrame:
    """Liability value sensitivity per 1bp bump at each curve tenor, in money
    (central difference over +/- ``bump_bp``, then divided back to per-1bp).

    Positive = the liability *falls* (issuer gains) when that node rises.
    The callable profile is lumpy near the call dates and needs a few bp of
    bump to clear the lattice's discretisation noise; ``bump_bp`` defaults to 10.
    """
    scale = notional / 100.0
    base = _price_one(base_rates_pct, vols, spec, engine, engine_kw, struck_coupon)
    c_star, exset = base["_c_star"], set(base["_exset"])
    h = bump_bp / 100.0

    rows = []
    for k in base_rates_pct.index:
        up = base_rates_pct.copy(); up[k] += h
        dn = base_rates_pct.copy(); dn[k] -= h

        def val(r, which):
            eng = build_engine(engine, curve=build_discount_curve(r),
                               maturity=spec.maturity,
                               vol=_resolve_vol(vols, spec.maturity), **engine_kw)
            return (eng.price(c_star, exset, spec.call_price) if which == "call"
                    else eng.straight_price(c_star))

        cu, cd = val(up, "call"), val(dn, "call")
        bu, bd = val(up, "bull"), val(dn, "bull")
        # central difference, normalised to *per 1bp*
        rows.append({
            "tenor": k,
            "callable_dv01": -(cu - cd) / (2 * bump_bp) * scale,
            "bullet_dv01": -(bu - bd) / (2 * bump_bp) * scale,
        })
    df = pd.DataFrame(rows).set_index("tenor")
    df.loc["TOTAL"] = df.sum()
    return df


# --------------------------------------------------------------------------- #
# effective duration / convexity (parallel finite differences)
# --------------------------------------------------------------------------- #
def effective_risk(base_rates_pct: pd.Series, vols, spec: CallableSpec,
                   struck_coupon: "float | None" = None, engine: str = "hw",
                   notional: float = 100.0, dy_bp: float = 25.0,
                   **engine_kw) -> pd.DataFrame:
    """Effective duration and convexity of the callable vs the bullet liability,
    from parallel +/- ``dy_bp`` shifts of the par curve.
    """
    base = _price_one(base_rates_pct, vols, spec, engine, engine_kw, struck_coupon)
    c_star, exset = base["_c_star"], set(base["_exset"])
    dy = dy_bp / 100.0 / 100.0  # bp -> decimal yield

    def prices(shift_bp):
        r = base_rates_pct + shift_bp / 100.0
        eng = build_engine(engine, curve=build_discount_curve(r),
                           maturity=spec.maturity,
                           vol=_resolve_vol(vols, spec.maturity), **engine_kw)
        return (eng.price(c_star, exset, spec.call_price), eng.straight_price(c_star))

    p0 = (base["callable_mtm"], base["bullet_mtm"])
    pu = prices(+dy_bp)
    pd_ = prices(-dy_bp)

    out = {}
    for i, tag in enumerate(("callable", "bullet")):
        eff_dur = -(pu[i] - pd_[i]) / (2 * dy * p0[i])
        eff_cvx = (pu[i] + pd_[i] - 2 * p0[i]) / (p0[i] * dy * dy)
        out[tag] = {
            "price": p0[i],
            "eff_duration": eff_dur,
            "eff_convexity": eff_cvx,
            "dv01_money": eff_dur * p0[i] * 1e-4 * (notional / 100.0),
        }
    df = pd.DataFrame(out).T
    df.attrs["struck_coupon_bp"] = c_star * 1e4
    return df
