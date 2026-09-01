"""
plots.py
========

Presentation-ready charts for the callable-bond curve sensitivity analysis.

Static PNGs (matplotlib, Agg) sized and styled for slides: large type, thin
recessive gridlines, colour-blind-safe palette, direct series labels + a legend,
a zero reference line, and a one-line source footnote.

Figures
-------
    pnl_vs_shift        issuer P&L on the liability, callable vs bullet, across a
                        parallel rate move  (the headline - shows the callable's
                        asymmetry / negative convexity)
    call_value          value of the embedded call vs the parallel rate move
    scenario_bars       "callable minus bullet" benefit per named scenario
                        (parallel +/-, bull-flattener, bear-steepener, twists,
                        belly) - the impact of different hikes / falls
    par_coupon          funding cost (par coupon) vs the parallel rate move,
                        with the bullet par coupon as reference
    dashboard           all four on one 2x2 slide

CLI: ``python main.py --plots [--out DIR] [--notional N] [--struck-coupon BP]``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scenarios import DEFAULT_SCENARIOS, parallel, scenario_analysis

# --- colour-blind-safe palette (Okabe-Ito); validated with the dataviz script --
C_CALLABLE = "#0072B2"   # blue
C_BULLET = "#E69F00"     # orange  (direct-labelled + markers: contrast relief)
C_BENEFIT = "#009E73"    # bluish green
C_COST = "#D55E00"       # vermilion
C_ZERO = "#333333"
C_GRID = "#E6E6E6"
C_INK = "#1A1A1A"
C_MUTED = "#6B6B6B"

_RC = {
    "figure.dpi": 150,
    "savefig.dpi": 150,
    "font.size": 12,
    "axes.titlesize": 16,
    "axes.titleweight": "bold",
    "axes.labelsize": 13,
    "axes.edgecolor": C_MUTED,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": C_GRID,
    "grid.linewidth": 0.8,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "xtick.color": C_INK,
    "ytick.color": C_INK,
    "text.color": C_INK,
    "axes.labelcolor": C_INK,
    "legend.fontsize": 11,
    "legend.frameon": False,
}


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
@dataclass
class SensitivityData:
    fine: pd.DataFrame            # index = parallel shift in bp
    named: pd.DataFrame           # index = scenario name
    struck_bp: float
    notional: float
    spec_label: str
    curve_date: str
    vol: float

    @property
    def money_unit(self) -> tuple[float, str]:
        n = self.notional
        if n >= 1e8:
            return 1e6, "€m"
        if n >= 1e5:
            return 1e3, "€k"
        return 1.0, "pts"

    def footnote(self) -> str:
        return (f"Hull-White 1F (a=0.03), Black vol {self.vol:.0%} · curve "
                f"{self.curve_date} · {self.spec_label} · struck at par "
                f"{self.struck_bp:.0f} bp · notional "
                f"{self.notional:,.0f}")


def compute_sensitivity(rates_pct, vols, spec, engine="hw", *,
                        notional=500_000_000.0, struck_coupon=None,
                        shifts_bp=None, named_scenarios=None,
                        **engine_kw) -> SensitivityData:
    """Run the sweep (fine parallel grid) and the named scenarios once."""
    shifts = (np.arange(-200, 201, 10) if shifts_bp is None
              else np.asarray(shifts_bp, dtype=int))
    named_scenarios = list(DEFAULT_SCENARIOS if named_scenarios is None
                           else named_scenarios)

    sweep = scenario_analysis(
        rates_pct, vols, spec, engine,
        scenarios=[parallel(int(b)) for b in shifts if b != 0],
        notional=notional, struck_coupon=struck_coupon, **engine_kw,
    )
    struck_bp = float(sweep.attrs["struck_coupon_bp"])
    keep = ["par_coupon_bp", "spread_bp", "callable_mtm", "call_value_pts",
            "d_call_value_pts", "issuer_pnl", "bullet_pnl", "call_contribution"]
    rows = {int(b): (sweep.loc["base"] if b == 0
                     else sweep.loc[f"parallel {b:+.0f}bp"])[keep]
            for b in shifts}
    fine = pd.DataFrame(rows).T.astype(float)
    fine.index = fine.index.astype(int)
    fine.index.name = "shift_bp"
    fine["bullet_coupon_bp"] = fine["par_coupon_bp"] - fine["spread_bp"]

    named = scenario_analysis(
        rates_pct, vols, spec, engine, scenarios=named_scenarios,
        notional=notional, struck_coupon=struck_coupon, **engine_kw,
    )
    named = named.drop(index=[i for i in ("base", "unchanged") if i in named.index])

    return SensitivityData(
        fine=fine, named=named,
        struck_bp=struck_bp, notional=float(notional),
        spec_label=spec.label(),
        curve_date=str(getattr(rates_pct, "attrs", {}).get("curve_date", "n/a")),
        vol=float(vols) if np.isscalar(vols) else float(np.mean(list(vols))),
    )


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", visible=False)


def _footer(fig, text):
    fig.text(0.01, 0.01, text, fontsize=8.5, color=C_MUTED, ha="left", va="bottom")


def _end_label(ax, x, y, text, color, dx=6):
    ax.annotate(text, xy=(x, y), xytext=(dx, 0), textcoords="offset points",
                va="center", ha="left", fontsize=11, fontweight="bold",
                color=color, clip_on=False)


# --------------------------------------------------------------------------- #
# figures
# --------------------------------------------------------------------------- #
def pnl_vs_shift(d: SensitivityData, ax=None):
    div, unit = d.money_unit
    made = ax is None
    if made:
        fig, ax = plt.subplots(figsize=(11, 6.2))
    x = d.fine.index.to_numpy()
    call = d.fine["issuer_pnl"].to_numpy() / div
    bull = d.fine["bullet_pnl"].to_numpy() / div

    ax.axhline(0, color=C_ZERO, lw=1)
    ax.axvline(0, color=C_GRID, lw=1)
    ax.plot(x, bull, color=C_BULLET, lw=2.5, marker="o", ms=5,
            markevery=list(range(0, len(x), 5)), label="Bullet (non-callable)")
    ax.plot(x, call, color=C_CALLABLE, lw=2.5, marker="o", ms=5,
            markevery=list(range(0, len(x), 5)), label="Callable")

    _end_label(ax, x[-1], call[-1], "Callable", C_CALLABLE)
    _end_label(ax, x[-1], bull[-1], "Bullet", C_BULLET)

    # headline callout at -100 bp
    if -100 in d.fine.index:
        yb = d.fine.loc[-100, "bullet_pnl"] / div
        yc = d.fine.loc[-100, "issuer_pnl"] / div
        ax.annotate(
            f"rates −100 bp:\ncallable {yc:+,.1f} vs bullet {yb:+,.1f} {unit}\n"
            f"= {(yc - yb):+,.1f} {unit} better",
            xy=(-100, yc), xytext=(-190, max(call.max(), bull.max()) * 0.42),
            fontsize=10.5, color=C_INK,
            arrowprops=dict(arrowstyle="-", color=C_MUTED, lw=0.8),
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=C_GRID))

    ax.set_title("Issuer P&L on the debt — callable vs bullet")
    ax.set_xlabel("parallel change in the swap curve (bp)")
    ax.set_ylabel(f"P&L on the liability  ({unit})   —   gain ↑")
    ax.legend(loc="upper left")
    ax.margins(x=0.13)
    _style(ax)
    if made:
        _footer(fig, "Positive = the liability is cheaper to carry, a gain to the issuer.  "
                     + d.footnote())
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig
    return ax


def call_value(d: SensitivityData, ax=None):
    made = ax is None
    if made:
        fig, ax = plt.subplots(figsize=(11, 6.2))
    x = d.fine.index.to_numpy()
    cv = d.fine["call_value_pts"].to_numpy()

    ax.axvline(0, color=C_GRID, lw=1)
    ax.fill_between(x, 0, cv, color=C_CALLABLE, alpha=0.12)
    ax.plot(x, cv, color=C_CALLABLE, lw=2.5, marker="o", ms=5,
            markevery=list(range(0, len(x), 5)))
    _end_label(ax, x[-1], cv[-1], "call value", C_CALLABLE)

    base_cv = float(d.fine.loc[0, "call_value_pts"]) if 0 in d.fine.index else cv[len(x) // 2]
    ax.axhline(base_cv, color=C_MUTED, lw=1, ls=(0, (4, 3)))
    ax.annotate(f"today: {base_cv:.2f} pts", xy=(x[0], base_cv),
                xytext=(0, 6), textcoords="offset points", fontsize=10, color=C_MUTED)

    ax.set_title("Value of the embedded call")
    ax.set_xlabel("parallel change in the swap curve (bp)")
    ax.set_ylabel("call value  (points of face)")
    ax.margins(x=0.10)
    ax.set_ylim(bottom=0)
    _style(ax)
    if made:
        _footer(fig, "The issuer's right to redeem early; richens as rates fall "
                     "(refinance cheaper), decays as they rise.  " + d.footnote())
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig
    return ax


def scenario_bars(d: SensitivityData, ax=None):
    div, unit = d.money_unit
    made = ax is None
    if made:
        fig, ax = plt.subplots(figsize=(11, 6.6))

    s = (d.named["call_contribution"] / div).sort_values()
    colors = [C_COST if v < 0 else C_BENEFIT for v in s.to_numpy()]
    y = np.arange(len(s))
    ax.barh(y, s.to_numpy(), color=colors, height=0.66)
    ax.axvline(0, color=C_ZERO, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(s.index)
    for yi, v in zip(y, s.to_numpy()):
        ax.annotate(f"{v:+,.1f}", xy=(v, yi),
                    xytext=(6 if v >= 0 else -6, 0), textcoords="offset points",
                    va="center", ha="left" if v >= 0 else "right",
                    fontsize=10.5, fontweight="bold",
                    color=C_BENEFIT if v >= 0 else C_COST)

    ax.set_title("Callable vs bullet — benefit by rate scenario")
    ax.set_xlabel(f"callable − bullet P&L  ({unit})     (left: cost   right: benefit)")
    ax.margins(x=0.20)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)
    if made:
        _footer(fig, "How much being callable rather than a plain bullet is worth "
                     "in each scenario.  " + d.footnote())
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig
    return ax


def par_coupon(d: SensitivityData, ax=None):
    made = ax is None
    if made:
        fig, ax = plt.subplots(figsize=(11, 6.2))
    x = d.fine.index.to_numpy()
    pc = d.fine["par_coupon_bp"].to_numpy() / 100.0            # -> percent
    bl = d.fine["bullet_coupon_bp"].to_numpy() / 100.0

    ax.axvline(0, color=C_GRID, lw=1)
    ax.plot(x, bl, color=C_BULLET, lw=2.5, ls=(0, (5, 3)), label="Bullet par coupon")
    ax.plot(x, pc, color=C_CALLABLE, lw=2.5, marker="o", ms=5,
            markevery=list(range(0, len(x), 5)), label="Callable par coupon")
    _end_label(ax, x[-1], pc[-1], "callable", C_CALLABLE)
    _end_label(ax, x[-1], bl[-1], "bullet", C_BULLET)

    ax.set_title("Funding cost — par coupon to issue today")
    ax.set_xlabel("parallel change in the swap curve (bp)")
    ax.set_ylabel("par coupon  (%)")
    ax.legend(loc="upper left")
    ax.margins(x=0.13)
    _style(ax)
    if made:
        _footer(fig, "The coupon that prices the bond at par on each shifted curve; "
                     "the gap to the bullet is the cost of the call.  " + d.footnote())
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        return fig
    return ax


def dashboard(d: SensitivityData):
    with plt.rc_context(_RC):
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        pnl_vs_shift(d, axes[0, 0])
        scenario_bars(d, axes[0, 1])
        call_value(d, axes[1, 0])
        par_coupon(d, axes[1, 1])
        fig.suptitle(f"Callable bond — rate sensitivity   ({d.spec_label}, "
                     f"notional {d.notional:,.0f})", fontsize=18, fontweight="bold")
        _footer(fig, d.footnote())
        fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    return fig


# --------------------------------------------------------------------------- #
# save all
# --------------------------------------------------------------------------- #
_FIGS = {
    "pnl_vs_shift": pnl_vs_shift,
    "call_value": call_value,
    "scenario_bars": scenario_bars,
    "par_coupon": par_coupon,
}


def save_all(rates_pct, vols, spec, out_dir, *, engine="hw",
             notional=500_000_000.0, struck_coupon=None, **engine_kw) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    d = compute_sensitivity(rates_pct, vols, spec, engine, notional=notional,
                            struck_coupon=struck_coupon, **engine_kw)

    written = []
    tag = spec.label().replace(" ", "_").replace("[", "").replace("]", "")
    with plt.rc_context(_RC):
        for name, fn in _FIGS.items():
            fig = fn(d)
            p = out_dir / f"{name}__{tag}.png"
            fig.savefig(p, bbox_inches="tight")
            plt.close(fig)
            written.append(p)
        fig = dashboard(d)
        p = out_dir / f"dashboard__{tag}.png"
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        written.append(p)

    # the underlying numbers, for the appendix
    d.fine.to_csv(out_dir / f"sweep__{tag}.csv")
    d.named.to_csv(out_dir / f"scenarios__{tag}.csv")
    return written
