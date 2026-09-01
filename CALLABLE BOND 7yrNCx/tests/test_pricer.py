"""
Validation suite for the callable-bond par-coupon engine.

Covers the properties called out in the brief:
  * bullet par coupon == the M-year par swap rate, for every M on the curve
  * callable engine reprices the curve (tree fit) and solves to par
  * bermudan par coupon >= best single-call par coupon, for any (M, nc)
  * nc_period == maturity-1  =>  single and bermudan coincide (one date only)
  * ladder is monotone decreasing in call date -- asserted only when the curve
    actually slopes up (curve-conditional, as specified)
  * construction-time validation raises with a clear message
"""

from __future__ import annotations

import numpy as np
import pytest

from engine import HullWhiteEngine, bullet_par_coupon
from pricer import (
    CallableSpec,
    call_ladder,
    compare_structures,
    par_coupon,
)

VOL = 0.15
ENGINE_KW = dict(mean_reversion=0.03, steps_per_year=12)


# --------------------------------------------------------------------------- #
# bullet == par swap rate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("m", list(range(2, 11)))
def test_bullet_equals_par_swap_rate(upward_curve, m):
    bullet = bullet_par_coupon(upward_curve, m)
    par_swap = upward_curve.forward_swap_rate(0, m)
    assert bullet == pytest.approx(par_swap, abs=1e-12)


def test_bullet_matches_across_curves(flat_curve, inverted_curve):
    for curve in (flat_curve, inverted_curve):
        for m in range(2, 11):
            assert bullet_par_coupon(curve, m) == pytest.approx(
                curve.forward_swap_rate(0, m), abs=1e-12
            )


# --------------------------------------------------------------------------- #
# engine sanity: curve fit + solves to par
# --------------------------------------------------------------------------- #
def test_tree_reprices_curve(upward_curve):
    eng = HullWhiteEngine(curve=upward_curve, maturity=10, vol=VOL, **ENGINE_KW)
    assert eng.fit_error < 1e-8


@pytest.mark.parametrize("call_type", ["single", "bermudan"])
def test_par_coupon_prices_at_par(upward_curve, call_type):
    spec = CallableSpec(7, 2, call_type)
    res = par_coupon(upward_curve, VOL, spec, "hw", **ENGINE_KW)
    assert res.price == pytest.approx(100.0, abs=1e-6)


def test_callable_coupon_above_bullet(upward_curve):
    spec = CallableSpec(7, 2, "bermudan")
    res = par_coupon(upward_curve, VOL, spec, "hw", **ENGINE_KW)
    assert res.par_coupon > res.bullet_par_coupon


# --------------------------------------------------------------------------- #
# bermudan >= best single, for any (M, nc)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("m,nc", [(5, 1), (5, 2), (7, 2), (7, 3), (10, 1), (10, 4)])
@pytest.mark.parametrize("curve_name", ["upward_curve", "flat_curve", "inverted_curve"])
def test_bermudan_ge_best_single(request, curve_name, m, nc):
    curve = request.getfixturevalue(curve_name)
    single = par_coupon(curve, VOL, CallableSpec(m, nc, "single"), "hw", **ENGINE_KW)
    berm = par_coupon(curve, VOL, CallableSpec(m, nc, "bermudan"), "hw", **ENGINE_KW)
    assert berm.par_coupon >= single.par_coupon - 1e-7


# --------------------------------------------------------------------------- #
# nc_period == maturity-1  =>  single == bermudan (only one exercise date)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("m", [3, 5, 7, 10])
def test_single_date_structures_coincide(upward_curve, m):
    single = par_coupon(upward_curve, VOL, CallableSpec(m, m - 1, "single"),
                        "hw", **ENGINE_KW)
    berm = par_coupon(upward_curve, VOL, CallableSpec(m, m - 1, "bermudan"),
                      "hw", **ENGINE_KW)
    assert single.n_exercise_dates == 1
    assert single.par_coupon == pytest.approx(berm.par_coupon, abs=1e-9)


def test_explicit_single_schedule_matches_ladder_entry(upward_curve):
    m, nc, d = 7, 2, 5
    ladder = call_ladder(upward_curve, VOL, CallableSpec(m, nc, "single"),
                         "hw", **ENGINE_KW)
    one_off = par_coupon(upward_curve, VOL,
                         CallableSpec(m, nc, "single", call_schedule=[d]),
                         "hw", **ENGINE_KW)
    assert one_off.par_coupon == pytest.approx(ladder.loc[d, "par_coupon"], abs=1e-9)


# --------------------------------------------------------------------------- #
# ladder monotone decreasing -- only when the curve slopes up, and only from
# the peak outward.  With >=2y of call protection the peak is the earliest
# candidate, so the whole ladder is monotone (this is the brief's assertion).
# With nc==1 the first candidate is ~1y out and carries almost no option
# time-value, so the peak slips to year 2-3; the ladder is still monotone
# *after* the peak.  Both engines agree on this, so it is a real effect, not a
# tree artifact -- see test_ladder_nc1_front_peak below.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("m,nc", [(7, 2), (10, 2), (10, 3), (10, 5)])
def test_ladder_monotone_on_upward_curve(upward_curve, upward_rates_pct, m, nc):
    if upward_rates_pct.iloc[0] >= upward_rates_pct.loc[f"{m}Y"]:
        pytest.skip("curve is not upward-sloping over this maturity")
    ladder = call_ladder(upward_curve, VOL, CallableSpec(m, nc, "single"),
                         "hw", **ENGINE_KW)
    pc = ladder["par_coupon"].to_numpy()
    assert int(np.argmax(pc)) == 0, f"peak not at earliest call: {pc}"
    assert np.all(np.diff(pc) <= 1e-9), f"ladder not decreasing: {pc}"


@pytest.mark.parametrize("m", [7, 10])
def test_ladder_nc1_front_peak(upward_curve, m):
    ladder = call_ladder(upward_curve, VOL, CallableSpec(m, 1, "single"),
                         "hw", **ENGINE_KW)
    pc = ladder["par_coupon"].to_numpy()
    peak = int(np.argmax(pc))
    assert peak <= 2, f"nc=1 peak unexpectedly late: {pc}"
    assert np.all(np.diff(pc[peak:]) <= 1e-9), f"ladder not decreasing past peak: {pc}"


def test_ladder_not_asserted_monotone_when_inverted(inverted_curve):
    # sanity: on an inverted curve the earliest call need NOT be the richest;
    # we only check the ladder is well-formed, not its direction.
    ladder = call_ladder(inverted_curve, VOL, CallableSpec(10, 1, "single"),
                         "hw", **ENGINE_KW)
    assert len(ladder) == 9
    assert ladder["price_check"].sub(100.0).abs().max() < 1e-6


# --------------------------------------------------------------------------- #
# call price > par lowers the coupon (less valuable call for the issuer)
# --------------------------------------------------------------------------- #
def test_higher_call_price_lowers_coupon(upward_curve):
    par100 = par_coupon(upward_curve, VOL, CallableSpec(7, 2, "bermudan"),
                        "hw", **ENGINE_KW)
    par101 = par_coupon(upward_curve, VOL,
                        CallableSpec(7, 2, "bermudan", call_price=101.0),
                        "hw", **ENGINE_KW)
    assert par101.par_coupon < par100.par_coupon
    assert par101.par_coupon >= par100.bullet_par_coupon - 1e-7


# --------------------------------------------------------------------------- #
# compare_structures shape
# --------------------------------------------------------------------------- #
def test_compare_structures_table(upward_curve):
    specs = [
        CallableSpec(7, 2, "single"),
        CallableSpec(7, 2, "bermudan"),
        CallableSpec(10, 1, "bermudan", call_price=101.0),
        CallableSpec(10, 1, "single", call_schedule=[3, 5, 7]),
    ]
    df = compare_structures(upward_curve, VOL, specs, "hw", **ENGINE_KW)
    assert list(df["maturity"]) == [7, 7, 10, 10]
    assert (df["price_check"].sub(100.0).abs() < 1e-6).all()
    # bermudan spread >= single spread for the matched 7y NC2 pair
    assert df.loc[1, "spread_bp"] >= df.loc[0, "spread_bp"] - 1e-4


# --------------------------------------------------------------------------- #
# construction-time validation
# --------------------------------------------------------------------------- #
def test_validation_messages():
    with pytest.raises(ValueError, match="nc_period"):
        CallableSpec(7, 0, "single")
    with pytest.raises(ValueError, match="nc_period"):
        CallableSpec(7, 7, "single")
    with pytest.raises(ValueError, match="maturity must be >= 2"):
        CallableSpec(1, 1, "single")
    with pytest.raises(ValueError, match="call_type"):
        CallableSpec(7, 2, "european")
    with pytest.raises(ValueError, match="call_schedule entries must be strictly"):
        CallableSpec(7, 2, "single", call_schedule=[3, 7])
    with pytest.raises(ValueError, match="duplicates"):
        CallableSpec(7, 2, "single", call_schedule=[3, 3])
    with pytest.raises(ValueError, match="call_price"):
        CallableSpec(7, 2, "single", call_price=0.0)


def test_maturity_beyond_curve_raises(upward_curve):
    spec = CallableSpec(11, 2, "bermudan")
    with pytest.raises(ValueError, match="exceeds the curve"):
        par_coupon(upward_curve, VOL, spec, "hw", **ENGINE_KW)


def test_maturity_equals_curve_end_warns(upward_curve):
    spec = CallableSpec(10, 2, "bermudan")
    with pytest.warns(UserWarning, match="longest tenor"):
        par_coupon(upward_curve, VOL, spec, "hw", **ENGINE_KW)


# --------------------------------------------------------------------------- #
# Black cross-check: same ballpark as Hull-White for a single call
# --------------------------------------------------------------------------- #
def test_negative_rate_curve(negative_curve):
    # bullet still == the par swap rate (now negative), and the solver copes
    # with a negative par coupon
    b7 = bullet_par_coupon(negative_curve, 7)
    assert b7 == pytest.approx(negative_curve.forward_swap_rate(0, 7), abs=1e-12)
    assert b7 < 0
    single = par_coupon(negative_curve, 0.006, CallableSpec(7, 2, "single"),
                        "hw", vol_type="normal", **ENGINE_KW)
    berm = par_coupon(negative_curve, 0.006, CallableSpec(7, 2, "bermudan"),
                      "hw", vol_type="normal", **ENGINE_KW)
    assert single.price == pytest.approx(100.0, abs=1e-6)
    assert single.par_coupon > b7
    assert berm.par_coupon >= single.par_coupon - 1e-7


def test_black_engine_single_call_ballpark(upward_curve):
    spec = CallableSpec(7, 3, "single", call_schedule=[3])
    hw = par_coupon(upward_curve, VOL, spec, "hw", **ENGINE_KW)
    bk = par_coupon(upward_curve, VOL, spec, "black")
    assert bk.par_coupon > bk.bullet_par_coupon           # callable dearer than bullet
    assert abs(hw.par_coupon - bk.par_coupon) < 30e-4     # within 30 bp of each other
