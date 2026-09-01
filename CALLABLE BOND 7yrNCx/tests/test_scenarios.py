"""
Tests for the curve sensitivity / scenario analysis (scenarios.py).

Economic sanity from the issuer's side:
  * par coupon falls as rates fall, rises as they rise (monotone in parallel)
  * the embedded call gains value on a rally, loses it on a sell-off
  * being callable rather than bullet HELPS the issuer when rates fall
    (call_contribution > 0) and costs a little when they rise
  * the callable has shorter effective duration and negative convexity vs the
    bullet
  * the bullet key-rate DV01 sums to its effective DV01 (curve-additivity)
"""

from __future__ import annotations

import numpy as np
import pytest

from pricer import CallableSpec
from scenarios import (
    CurveScenario,
    bull_flattener,
    effective_risk,
    key_rate_dv01,
    parallel,
    scenario_analysis,
    steepener,
)

VOL = 0.15
KW = dict(mean_reversion=0.03, steps_per_year=12)


# --------------------------------------------------------------------------- #
# curve shocks
# --------------------------------------------------------------------------- #
def test_parallel_shift_adds_bp_everywhere(upward_rates_pct):
    shocked = parallel(50).apply(upward_rates_pct)
    assert np.allclose(shocked.to_numpy() - upward_rates_pct.to_numpy(), 0.50)


def test_steepener_lifts_long_end_more(upward_rates_pct):
    s = steepener(60)
    assert s.fn(10) > s.fn(1)
    assert s.fn(1) < 0 < s.fn(10)


def test_base_row_is_flat(upward_rates_pct):
    df = scenario_analysis(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                           scenarios=[parallel(0)], **KW)
    for r in ("base", "unchanged"):
        assert abs(df.loc[r, "d_par_bp"]) < 1e-6
        assert abs(df.loc[r, "issuer_pnl"]) < 1e-6
        assert df.loc[r, "callable_mtm"] == pytest.approx(100.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# monotonicity + call value direction
# --------------------------------------------------------------------------- #
def test_par_coupon_monotone_in_parallel_shift(upward_rates_pct):
    scen = [parallel(b) for b in (-200, -100, -50, 0, 50, 100, 200)]
    df = scenario_analysis(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                           scenarios=scen, **KW)
    pc = [df.loc[s.name, "par_coupon_bp"] for s in scen]
    assert np.all(np.diff(pc) > 0), pc


def test_call_value_rises_on_rally_falls_on_selloff(upward_rates_pct):
    scen = [parallel(b) for b in (-200, -100, 100, 200)]
    df = scenario_analysis(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                           scenarios=scen, **KW)
    assert df.loc["parallel -200bp", "d_call_value_pts"] > \
        df.loc["parallel -100bp", "d_call_value_pts"] > 0
    assert df.loc["parallel +200bp", "d_call_value_pts"] < \
        df.loc["parallel +100bp", "d_call_value_pts"] < 0


def test_callable_helps_issuer_when_rates_fall(upward_rates_pct):
    df = scenario_analysis(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                           scenarios=[parallel(-150), parallel(150),
                                      bull_flattener(100)],
                           notional=1_000_000, **KW)
    assert df.loc["parallel -150bp", "call_contribution"] > 0
    assert df.loc["bull flattener 100bp", "call_contribution"] > 0
    assert df.loc["parallel +150bp", "call_contribution"] < 0
    # issuer_pnl - bullet_pnl is exactly the call contribution
    row = df.loc["parallel -150bp"]
    assert row["call_contribution"] == pytest.approx(
        row["issuer_pnl"] - row["bullet_pnl"], rel=1e-9)


def test_money_columns_scale_with_notional(upward_rates_pct):
    spec = CallableSpec(7, 2, "bermudan")
    a = scenario_analysis(upward_rates_pct, VOL, spec, scenarios=[parallel(-100)],
                          notional=1_000_000, **KW)
    b = scenario_analysis(upward_rates_pct, VOL, spec, scenarios=[parallel(-100)],
                          notional=5_000_000, **KW)
    assert b.loc["parallel -100bp", "issuer_pnl"] == pytest.approx(
        5 * a.loc["parallel -100bp", "issuer_pnl"], rel=1e-9)


# --------------------------------------------------------------------------- #
# effective risk + key-rate additivity
# --------------------------------------------------------------------------- #
def test_callable_shorter_duration_negative_convexity(upward_rates_pct):
    er = effective_risk(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                        **KW)
    assert er.loc["callable", "eff_duration"] < er.loc["bullet", "eff_duration"]
    assert er.loc["callable", "eff_convexity"] < 0 < er.loc["bullet", "eff_convexity"]


def test_bullet_key_rate_sums_to_effective_dv01(upward_rates_pct):
    spec = CallableSpec(7, 2, "bermudan")
    kr = key_rate_dv01(upward_rates_pct, VOL, spec, notional=1_000_000,
                       bump_bp=10.0, **KW)
    er = effective_risk(upward_rates_pct, VOL, spec, notional=1_000_000, **KW)
    assert kr.loc["TOTAL", "bullet_dv01"] == pytest.approx(
        er.loc["bullet", "dv01_money"], rel=0.02)
    # nodes past maturity carry no sensitivity
    for t in ("8Y", "9Y", "10Y"):
        assert abs(kr.loc[t, "callable_dv01"]) < 1e-6
