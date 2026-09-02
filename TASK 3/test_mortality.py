"""Sanity tests for the Normal-distribution mortality model."""

from __future__ import annotations

import numpy as np
import pytest

from mortality import (
    CohortSpec,
    deaths_per_year,
    expected_annuity_payments,
    life_table,
    mortality_table,
    summary,
    survivors_per_year,
)


def test_cohort_starts_whole_at_current_age():
    spec = CohortSpec()
    lt = life_table(spec)
    # conditioning on "alive at current_age" => the cohort is intact at 50
    assert lt.loc[spec.current_age, "alive_start_total"] == pytest.approx(spec.n_total)
    assert lt.loc[spec.current_age, "alive_start_male"] == pytest.approx(spec.n_male)


def test_survivors_monotone_decreasing():
    s = life_table()["alive_start_total"].to_numpy()
    assert np.all(np.diff(s) <= 1e-6)


def test_close_out_conserves_lives():
    spec = CohortSpec()
    lt = mortality_table(spec)
    total_deaths = lt["deaths_total"].sum()
    l_65 = lt.loc[spec.payout_age, "alive_start_total"]
    assert total_deaths == pytest.approx(l_65, rel=1e-9)
    assert lt.loc[spec.max_age, "alive_end_total"] == pytest.approx(0.0, abs=1e-6)


def test_sex_columns_add_up():
    lt = life_table()
    for base in ("alive_start", "deaths", "alive_end"):
        assert np.allclose(lt[f"{base}_total"],
                           lt[f"{base}_male"] + lt[f"{base}_female"])


def test_female_outlives_male():
    lt = life_table()
    spec = CohortSpec()
    frac_m = lt["alive_start_male"] / spec.n_male
    frac_f = lt["alive_start_female"] / spec.n_female
    # higher mean, same sd -> female survival fraction higher at every age > 50
    assert (frac_f.iloc[1:] > frac_m.iloc[1:]).all()


def test_mortality_rate_increases_with_age():
    q = mortality_table()["mortality_rate_qx"].loc[65:115]
    assert np.all(np.diff(q.to_numpy()) > 0)


def test_summary_in_plausible_range():
    s = summary()
    assert 80.0 < s["reach_payout_age_pct"] < 99.0
    assert 12.0 < s["life_expectancy_at_payout_total"] < 25.0
    assert s["life_expectancy_at_payout_female"] > s["life_expectancy_at_payout_male"]
    assert 65 < s["peak_death_age"] < 95


def test_larger_sd_fattens_the_tail_but_conserves_lives():
    base = mortality_table(CohortSpec(sd_male=10.0, sd_female=10.0))
    wide = mortality_table(CohortSpec(sd_male=16.0, sd_female=16.0))
    assert wide.loc[100, "alive_start_total"] > base.loc[100, "alive_start_total"]
    assert wide["deaths_total"].sum() == pytest.approx(
        wide.loc[65, "alive_start_total"], rel=1e-9)


def test_advance_minus_arrears_equals_deaths_in_window():
    spec = CohortSpec()
    adv = expected_annuity_payments(spec, timing="advance").sum()
    arr = expected_annuity_payments(spec, timing="arrears").sum()
    assert adv - arr == pytest.approx(deaths_per_year(spec).sum(), rel=1e-9)


def test_public_series_line_up():
    spec = CohortSpec()
    assert list(deaths_per_year(spec).index) == list(range(spec.payout_age,
                                                           spec.max_age + 1))
    assert survivors_per_year(spec).iloc[0] == pytest.approx(
        summary(spec)["reach_payout_age_total"])
