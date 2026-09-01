"""
Smoke + sanity tests for the presentation charts (plots.py).

We do not assert on pixels — only that the sensitivity data behind the charts is
shaped right and economically sane, and that every figure renders to a
non-trivial PNG.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import pytest

from plots import compute_sensitivity, dashboard, save_all
from pricer import CallableSpec

VOL = 0.15
KW = dict(mean_reversion=0.03, steps_per_year=12)


def test_compute_sensitivity_shape(upward_rates_pct):
    d = compute_sensitivity(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                            notional=5e8, shifts_bp=range(-200, 201, 50), **KW)
    assert list(d.fine.index) == [-200, -150, -100, -50, 0, 50, 100, 150, 200]
    for col in ("issuer_pnl", "bullet_pnl", "call_value_pts", "par_coupon_bp",
                "bullet_coupon_bp", "call_contribution"):
        assert col in d.fine.columns
    assert len(d.named) >= 8
    assert abs(d.fine.loc[0, "issuer_pnl"]) < 1.0     # base ~ flat


def test_sensitivity_is_economically_sane(upward_rates_pct):
    d = compute_sensitivity(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                            notional=5e8, shifts_bp=range(-200, 201, 50), **KW)
    # rates down -> fixed-coupon liability worth more -> issuer loss; up -> gain
    assert d.fine.loc[-200, "issuer_pnl"] < 0 < d.fine.loc[200, "issuer_pnl"]
    # embedded call richens on a rally, decays on a sell-off
    assert d.fine.loc[-200, "call_value_pts"] > d.fine.loc[0, "call_value_pts"] \
        > d.fine.loc[200, "call_value_pts"]
    # callable always cheaper to the holder than the bullet -> call_value >= 0
    assert (d.fine["call_value_pts"] >= -1e-6).all()


def test_save_all_writes_figures(upward_rates_pct, tmp_path):
    written = save_all(upward_rates_pct, VOL, CallableSpec(7, 2, "bermudan"),
                       tmp_path, notional=5e8, **KW)
    pngs = [p for p in written if p.suffix == ".png"]
    assert len(pngs) == 5
    for p in pngs:
        assert p.exists() and p.stat().st_size > 5_000
    assert (tmp_path / "sweep__7y_NCbrm2.csv").exists()
    assert (tmp_path / "scenarios__7y_NCbrm2.csv").exists()


def test_dashboard_renders(upward_rates_pct):
    d = compute_sensitivity(upward_rates_pct, VOL, CallableSpec(10, 1, "bermudan"),
                            notional=1e9, shifts_bp=range(-150, 151, 50), **KW)
    fig = dashboard(d)
    assert len(fig.axes) >= 4
    import matplotlib.pyplot as plt

    plt.close(fig)
