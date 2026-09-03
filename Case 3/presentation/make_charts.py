"""
make_charts.py  -  regenerate the deck's figures from the Case 3b result files,
styled in the presentation palette (teal / navy / orange) so they sit cleanly
inside All-Kanns_Asset_Management.pptx.

Sources
    results/cashflow_matching.csv                asset vs liability annual CF
    mixed_liability_scenarios.xlsx               policyholder-election liability split
    results_var/return_book_projection.csv       90/10 profit-share accumulation path
    results_var/HS_REPORT_full_(unhedged|irs).md VaR bridge (hard-coded from reports)
    results_var/stress_tests_full_(unhedged|irs).csv  deterministic stresses
    monte_carlo_ALM_results.xlsx                 15y accumulation MC (year-15 asset dist)
    results_v2/krd_wide.csv                      key-rate DV01 asset vs liability
    portfolio_optimization_final.xlsx            Aggressive_Diversified RSP weights
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CASE = HERE.parent
OUT = HERE / "assets"
OUT.mkdir(exist_ok=True)

NAVY, DTEAL, TEAL, TEALL = "#12323F", "#1F4E5F", "#3B8E9E", "#8FBFC8"
ORANGE, GREEN, RED, GRID, INK = "#C85A2B", "#2E7D4F", "#B4322B", "#DCE4E7", "#333333"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "axes.edgecolor": "#BFCBCF",
    "axes.linewidth": 0.8, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlecolor": NAVY, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "figure.facecolor": "white",
    "axes.facecolor": "white", "savefig.facecolor": "white",
})


def _style(ax):
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("wrote", (OUT / name).relative_to(CASE))


# --------------------------------------------------------------------------- #
def _book_cf():
    d = pd.read_csv(CASE / "results_v2" / "book_cf_wide.csv")   # held two-stage book
    return d[d["year"] <= 50].rename(columns={"year": "projection_year"})


def cf_annual():
    d = _book_cf()
    d = d[d["projection_year"] <= 40]
    x = d["projection_year"].to_numpy()
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    ax.bar(x - 0.2, d["asset_cf_eur"] / 1e9, 0.4, color=TEAL, label="FI book cash flows (coupons + redemptions)")
    ax.bar(x + 0.2, d["liability_cf_eur"] / 1e9, 0.4, color=ORANGE, label="guaranteed liability cash flows")
    ax.axvspan(0.5, 10.5, color=TEALL, alpha=0.20, lw=0)
    ax.text(5.5, ax.get_ylim()[1] * 0.92, "contributions in\n(€0.5bn/yr)", ha="center", va="top",
            fontsize=10, color=DTEAL)
    ax.set_xlabel("projection year")
    ax.set_ylabel("EUR bn")
    ax.set_title("Asset vs. guaranteed-liability cash flows  (50% lump / 50% pension)")
    ax.legend(frameon=False, fontsize=9.5, loc="upper right")
    _style(ax)
    _save(fig, "cf_annual.png")


def cf_cumulative():
    d = _book_cf()
    x = d["projection_year"].to_numpy()
    ca = np.cumsum(d["asset_cf_eur"].to_numpy()) / 1e9
    cl = np.cumsum(d["liability_cf_eur"].to_numpy()) / 1e9
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    ax.plot(x, ca, color=TEAL, lw=2.6, label="cumulative FI-book cash flow")
    ax.plot(x, cl, color=ORANGE, lw=2.6, label="cumulative liability cash flow")
    ax.fill_between(x, ca, cl, color=GRID, alpha=0.7)
    ax.set_xlabel("projection year")
    ax.set_ylabel("EUR bn, cumulative")
    ax.set_title("Cumulative coverage – FI book (undiscounted) vs. guaranteed outflows")
    ax.legend(frameon=False, fontsize=10, loc="upper left")
    _style(ax)
    _save(fig, "cf_cumulative.png")


def cf_match_fi(reinv: float = 0.015):
    """Cash-flow matching of the held (50/50) two-stage FI book:
    annual asset vs liability cash flow, and the running cash balance that
    Stage-1 dedication keeps >= 0 every year (no external top-up).
    Source: results_v2/book_cf_wide.csv (cashflow_match_v2.run())."""
    d = pd.read_csv(CASE / "results_v2" / "book_cf_wide.csv")
    d = d[d["year"] <= 50]
    yr = d["year"].to_numpy()
    a = d["asset_cf_eur"].to_numpy() / 1e9
    l = d["liability_cf_eur"].to_numpy() / 1e9
    bal, run = 0.0, []
    for ai, li in zip(a, l):
        bal = bal * (1.0 + reinv) + ai - li
        run.append(bal)
    run = np.array(run)

    fig, ax = plt.subplots(2, 1, figsize=(9.6, 6.2), sharex=True,
                           gridspec_kw={"height_ratios": [1.35, 1]})
    ax[0].bar(yr - 0.2, a, 0.4, color=TEAL, label="FI book cash flow (coupons + redemptions)")
    ax[0].bar(yr + 0.2, l, 0.4, color=ORANGE, label="guaranteed liability cash flow")
    ax[0].axvspan(0.5, 10.5, color=TEALL, alpha=0.25, lw=0)
    ax[0].annotate(f"year-15 lump  €{l[yr==15][0]:.2f}bn", xy=(15, l[yr == 15][0]),
                   xytext=(19, l[yr == 15][0] * 0.86), fontsize=9, color=INK,
                   arrowprops=dict(arrowstyle="-", color="#8AA0A6", lw=0.9))
    ax[0].set_ylabel("EUR bn / year")
    ax[0].set_title("Fixed-Income cash-flow matching – held book (50 % lump / 50 % pension)")
    ax[0].legend(frameon=False, fontsize=9.5, loc="upper right")
    _style(ax[0])

    ax[1].fill_between(yr, 0, run, color=TEALL, alpha=0.75)
    ax[1].plot(yr, run, color=DTEAL, lw=2.2)
    ax[1].axhline(0, color="#8AA0A6", lw=1)
    touch = yr[run < 0.05]
    ax[1].scatter(touch, run[run < 0.05], color=ORANGE, s=26, zorder=5)
    ax[1].text(1, ax[1].get_ylim()[1] * 0.86,
               "running cash balance stays ≥ 0 every year  →  no external top-up",
               fontsize=9, color=DTEAL)
    ax[1].set_xlabel("projection year")
    ax[1].set_ylabel("running balance (EUR bn)\n1.5 % reinvestment")
    _style(ax[1])
    _save(fig, "cf_match_fi.png")


def election():
    d = pd.read_excel(CASE / "mixed_liability_scenarios.xlsx", sheet_name="Scenario Summary")
    lab = [f"{int(p)}%" for p in d["Lump_Sum_%"]]
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    xs = np.arange(len(d))
    b = ax.bar(xs, d["Lump_Sum_at_Year15"] / 1e9, 0.55, color=DTEAL,
               label="lump-sum cash-out at year 15")
    ax.bar(xs, d["PV_Pension_Today"] / 1e9, 0.55, bottom=d["Lump_Sum_at_Year15"] / 1e9,
           color=TEALL, label="PV today of the pension tail")
    for i, v in enumerate(d["Total_PV_Today"] / 1e9):
        ax.text(i, (d["Lump_Sum_at_Year15"].iloc[i] + d["PV_Pension_Today"].iloc[i]) / 1e9 + 0.15,
                f"PV today\n€{v:.1f}bn", ha="center", fontsize=9, color=INK)
    ax.set_xticks(xs)
    ax.set_xticklabels(lab)
    ax.set_xlabel("share of policyholders electing the lump sum (base case 50%)")
    ax.set_ylabel("EUR bn")
    ax.set_title("Year-15 liquidity need by policyholder election")
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")
    _style(ax)
    _save(fig, "election.png")


def profit_share():
    d = pd.read_csv(CASE / "results_var" / "return_book_projection.csv")
    x = d["t_years"].to_numpy()
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    ax.plot(x, d["mv_total"] / 1e9, color=TEAL, lw=2.6, label="return-book MV (insurer)")
    ax.plot(x, np.cumsum(d["contribution"]) / 1e9, color=INK, lw=1.4, ls=(0, (5, 3)),
            label="cumulative contributions")
    ax.plot(x, d["payout_policyholder_cum"] / 1e9, color=ORANGE, lw=2.6,
            label="cumulative policyholder profit share (90%, yr 15+)")
    ax.plot(x, d["retained_insurer_cum"] / 1e9, color=GREEN, lw=2.6,
            label="insurer retained (10%)")
    ax.axvline(15, color=ORANGE, lw=1.1, ls=":")
    ax.text(15.2, ax.get_ylim()[1] * 0.06, "profit sharing\nstarts (yr 15)", fontsize=8.5,
            color=ORANGE)
    ax.set_xlabel("year")
    ax.set_ylabel("EUR bn")
    ax.set_title("Return portfolio – full compounding to yr 15, then 90 / 10 profit sharing")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    _style(ax)
    _save(fig, "profit_share.png")


def var_bridge():
    # from HS_REPORT_full_unhedged.md / HS_REPORT_full_irs.md  (1y 99% HS VaR, EUR m)
    # FI book = results_v2/portfolio_wide.csv (cash-flow-dedicated two-stage book)
    cats = ["Asset VaR\nunhedged", "Asset VaR\n+ receiver IRS",
            "Surplus VaR\nunhedged", "Surplus VaR\n+ receiver IRS"]
    vals = [2513, 3449, 1214, 845]
    cols = [TEAL, TEAL, ORANGE, ORANGE]
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    bars = ax.bar(cats, vals, 0.6, color=cols)
    bars[1].set_alpha(0.6)
    bars[3].set_alpha(0.6)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 60, f"€{v/1000:.2f}bn", ha="center",
                fontsize=10, color=INK)
    ax.set_ylabel("1-year 99% VaR (EUR m)")
    ax.set_title("Historical-Simulation VaR – the receiver-IRS overlay cuts surplus risk 30%")
    _style(ax)
    _save(fig, "var_bridge.png")


def stress():
    """unhedged  vs  full hedge stack = FX swap + 15y/30y receiver IRS +
    30% equity-index futures short.  (The risk-control rule sets the futures
    ratio to 0% once the IRS is on; 30% is shown as the discretionary maximum.)"""
    u = pd.read_csv(CASE / "results_var" / "stress_tests_full_unhedged.csv").set_index("scenario")
    h = pd.read_csv(CASE / "results_var" / "stress_tests_full_hedged_fut30.csv").set_index("scenario")
    order = ["EUR rates +100bp parallel", "EUR rates -100bp parallel", "Equity -30%",
             "HY spread +300bp (~-12%)", "2022 replay: rates +250bp, equity -20%",
             "2008 replay: equity -45%, rates -150bp, HY -25%",
             "Longevity +1yr life exp (~+4% liability)"]
    short = ["Rates +100bp", "Rates -100bp", "Equity -30%", "HY +300bp",
             "2022 replay", "2008 replay", "Longevity +1yr"]
    su = [u.loc[s, "surplus_pnl"] / 1e9 for s in order]
    sh = [h.loc[s, "surplus_pnl"] / 1e9 for s in order]
    y = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(9.6, 4.4))
    ax.barh(y - 0.2, su, 0.4, color=TEALL, label="unhedged")
    ax.barh(y + 0.2, sh, 0.4, color=DTEAL, label="full hedge  (FX swap + receiver IRS + futures overlay)")
    ax.axvline(0, color="#8AA0A6", lw=1)
    for yi, (a, b) in enumerate(zip(su, sh)):
        ax.text(b - 0.05 if b < 0 else b + 0.05, yi + 0.2, f"{b:+.2f}", va="center",
                ha="right" if b < 0 else "left", fontsize=8, color=DTEAL)
    ax.set_yticks(y)
    ax.set_yticklabels(short)
    ax.invert_yaxis()
    ax.set_xlabel("surplus P&L (EUR bn)   —   ΔAssets − ΔLiability")
    ax.set_title("Deterministic stress tests – unhedged vs. the full hedge stack")
    ax.legend(frameon=False, fontsize=8.6, loc="upper left")
    _style(ax)
    _save(fig, "stress.png")


def mc_year15():
    ap = pd.read_excel(CASE / "monte_carlo_ALM_results.xlsx", sheet_name="Asset Path Percentiles")
    fig, ax = plt.subplots(figsize=(9.6, 4.3))
    yr = ap["Year"].to_numpy()
    ax.fill_between(yr, ap["P0.5"] / 1e9, ap["P95"] / 1e9, color=TEALL, alpha=0.35, label="0.5th–95th pct")
    ax.fill_between(yr, ap["P5"] / 1e9, ap["Median"] / 1e9, color=TEAL, alpha=0.35, label="5th–median")
    ax.plot(yr, ap["Median"] / 1e9, color=DTEAL, lw=2.6, label="median path")
    ax.plot(yr, ap["P5"] / 1e9, color=TEAL, lw=1.4)
    ax.plot(yr, ap["P0.5"] / 1e9, color=TEAL, lw=1.0, ls=(0, (4, 3)))
    ax.axhline(11.303, color=RED, lw=1.8, ls=(0, (5, 3)), label="€11.3bn guaranteed floor (yr 15)")
    ax.set_xlabel("year")
    ax.set_ylabel("total assets (EUR bn)")
    ax.set_title("15-year Monte-Carlo – asset paths vs. the guaranteed floor")
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    _style(ax)
    _save(fig, "mc_year15.png")


def krd():
    d = pd.read_csv(CASE / "results_v2" / "krd_wide.csv")
    x = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    ax.bar(x - 0.2, d["liability"] / 1e6, 0.4, color=ORANGE, label="liability")
    ax.bar(x + 0.2, d["stage2"] / 1e6, 0.4, color=TEAL, label="matched bond book (+ ultra-long / ZCB)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(t)}y" for t in d["key_tenor"]])
    ax.set_xlabel("key rate")
    ax.set_ylabel("key-rate DV01 (EUR m / bp)")
    ax.set_title("Key-rate DV01 match – residual 15y gap closed by the receiver IRS")
    ax.legend(frameon=False, fontsize=10)
    _style(ax)
    _save(fig, "krd.png")


def rsp_weights():
    w = pd.read_excel(CASE / "portfolio_optimization_final.xlsx", sheet_name="Portfolio Weights")
    w = w[["Asset", "Aggressive_Diversified"]].sort_values("Aggressive_Diversified")
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.barh(w["Asset"], w["Aggressive_Diversified"], color=TEAL)
    for i, v in enumerate(w["Aggressive_Diversified"]):
        ax.text(v + 0.3, i, f"{v:.1f}%", va="center", fontsize=9, color=INK)
    ax.set_xlabel("weight (% of return portfolio)")
    ax.set_title("Return portfolio – Aggressive Diversified target weights (14 indices)")
    _style(ax)
    _save(fig, "rsp_weights.png")


if __name__ == "__main__":
    cf_annual()
    cf_cumulative()
    cf_match_fi()
    election()
    profit_share()
    var_bridge()
    stress()
    mc_year15()
    krd()
    rsp_weights()
