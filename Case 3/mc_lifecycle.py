"""
mc_lifecycle.py
===============

15-year accumulation Monte-Carlo for Case 3b, on the **consistent pipeline**
(the same books the 1-year VaR model uses):

  * funding waterfall  - t=0: EUR 5.0bn into the cash-flow-dedicated FI book
    (`results_v2/portfolio_wide.csv`);  t=1..10: EUR 0.5bn/yr into the
    Return-Seeking Portfolio (14 indices, Aggressive Diversified weights)
  * FI book annual return   ~ Student-t, loc = book running yield, scale from
    its duration and an annual rate shock (dampened - held to fund cash flows)
  * RSP annual return        ~ multivariate Student-t on the 14 sleeves
    (historical annualised mean + covariance), rebalanced to target weights
  * profit sharing           starts at year 15 (`return_book.profit_share_start_year`)
    - so it does not bite inside this 0..15 window; noted for completeness
  * liability                the guaranteed year-15 book, split lump / pension
    (from `mixed_liability_scenarios.xlsx`)

Reproduces the 7 figures the pre-overlay teammate MC produced
(01..07), now consistent with the rest of the model.  Outputs ->
`presentation/assets/lc_01_*.png ... lc_07_*.png` + `results_var/MC_LIFECYCLE_REPORT.md`.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import case3_model as m

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "presentation" / "assets"
OUT = HERE / "results_var"
ASSETS.mkdir(parents=True, exist_ok=True)

N_SIM = 50_000
HORIZON = 15
DF_T = 5                      # Student-t degrees of freedom
CONTRIB_EUR = 0.5e9
CONTRIB_YEARS = 10
FI_EUR = 5.0e9
SEED = 20260903

# FI book: annual return model  r = carry - D*dy + 0.5*C*dy^2  (dy dampened)
FI_CARRY = 0.039             # running yield of results_v2/portfolio_wide.csv (curve + spread)
FI_RATE_VOL = 0.0075         # annual EUR rate shock, 1 s.d.
FI_MTM_DAMP = 0.45           # held to fund CFs -> only part of the MTM swing is "realised"
FI_RSP_CORR = 0.15

NAVY, DTEAL, TEAL, TEALL = "#12323F", "#1F4E5F", "#3B8E9E", "#8FBFC8"
ORANGE, GREEN, RED, GRID, INK = "#C85A2B", "#2E7D4F", "#B4322B", "#DCE4E7", "#333333"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "axes.edgecolor": "#BFCBCF",
    "axes.linewidth": 0.8, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlecolor": NAVY, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "savefig.facecolor": "white",
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def _style(ax):
    ax.grid(color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(ASSETS / name, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print("wrote", (ASSETS / name).relative_to(HERE))


# --------------------------------------------------------------------------- #
def _inputs():
    px = m.load_index_history()
    w = m.load_return_weights(m.Config())
    wlr = np.log(px).diff().dropna()
    sl = [c for c in w.index if c in wlr.columns]
    tw = (w.reindex(sl) / w.reindex(sl).sum()).to_numpy()
    mu_a = wlr[sl].mean().to_numpy() * 52.0
    cov_a = wlr[sl].cov().to_numpy() * 52.0

    liab = pd.read_excel(HERE / "mixed_liability_scenarios.xlsx", sheet_name="Scenario Summary")
    liab = liab.set_index("Lump_Sum_%")
    return sl, tw, mu_a, cov_a, liab


def simulate():
    sl, tw, mu_a, cov_a, liab = _inputs()
    n = len(sl)
    rng = np.random.default_rng(SEED)

    # ---- build the (n+1)-asset annual mean/cov: 14 sleeves + FI book -------
    mu = np.concatenate([mu_a, [FI_CARRY]])
    fi_vol = FI_MTM_DAMP * (15.33 * FI_RATE_VOL)          # ~ D * dy, dampened
    cov = np.zeros((n + 1, n + 1))
    cov[:n, :n] = cov_a
    cov[n, n] = fi_vol ** 2
    sleeve_vol = np.sqrt(np.diag(cov_a))
    cov[n, :n] = cov[:n, n] = FI_RSP_CORR * fi_vol * sleeve_vol

    # ---- draw all path-years at once: Student-t = Normal / sqrt(chi2/df) --
    L = np.linalg.cholesky(cov + 1e-12 * np.eye(n + 1))
    z = rng.standard_normal((N_SIM, HORIZON, n + 1)) @ L.T
    g = rng.chisquare(DF_T, size=(N_SIM, HORIZON, 1)) / DF_T
    r = mu + z / np.sqrt(g)                               # simple annual returns
    r_sleeves, r_fi = r[:, :, :n], r[:, :, n]
    r_rsp = r_sleeves @ tw                                # rebalanced-to-target each year

    # ---- roll the two sleeves forward -----------------------------------
    lmp = np.full(N_SIM, FI_EUR)
    rsp = np.zeros(N_SIM)
    paths = np.zeros((N_SIM, HORIZON + 1))
    paths[:, 0] = lmp + rsp
    contrib = np.zeros(HORIZON + 1)
    for t in range(1, HORIZON + 1):
        lmp = lmp * (1.0 + r_fi[:, t - 1])
        rsp = rsp * (1.0 + r_rsp[:, t - 1])
        if t <= CONTRIB_YEARS:
            rsp = rsp + CONTRIB_EUR
            contrib[t] = CONTRIB_EUR
        paths[:, t] = lmp + rsp

    # ---- annual portfolio return (contribution-stripped) ---------------
    ann = (paths[:, 1:] - contrib[1:]) / paths[:, :-1] - 1.0

    # ---- 15y money-weighted return (IRR) ------------------------------
    cf = np.zeros(HORIZON + 1)
    cf[0] = -FI_EUR
    cf[1:CONTRIB_YEARS + 1] = -CONTRIB_EUR
    a15 = paths[:, HORIZON]
    irr = _irr_vec(cf, a15, HORIZON)

    return dict(sl=sl, liab=liab, paths=paths, ann=ann, irr=irr, a15=a15,
                r_rsp=r_rsp, r_fi=r_fi)


def _irr_vec(cf_wo_terminal, terminal, T, lo=-0.5, hi=1.0, iters=80):
    """Bisection IRR for cashflow `cf_wo_terminal` (len T+1) + `terminal` at T."""
    t = np.arange(T + 1)
    lo = np.full_like(terminal, lo, dtype=float)
    hi = np.full_like(terminal, hi, dtype=float)

    def npv(rate):
        d = (1.0 + rate)[:, None] ** (-t[None, :])
        base = (cf_wo_terminal[None, :] * d).sum(axis=1)
        return base + terminal * (1.0 + rate) ** (-T)

    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        pos = npv(mid) > 0
        lo = np.where(pos, mid, lo)
        hi = np.where(pos, hi, mid)
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------- #
def charts(res):
    liab = res["liab"]
    paths, ann, irr, a15 = res["paths"], res["ann"], res["irr"], res["a15"]
    L50 = float(liab.loc[50.0, "Total_Liability_Year15"])     # 50/50 base
    yrs = np.arange(HORIZON + 1)
    p = lambda q: np.percentile(paths, q, axis=0) / 1e9

    # 01 - asset evolution -------------------------------------------------
    fig, ax = plt.subplots(figsize=(9.6, 5.0))
    ax.fill_between(yrs, p(5), p(95), color=TEALL, alpha=0.55, label="5th–95th percentile")
    ax.plot(yrs, p(50), color=DTEAL, lw=2.6, label="median assets")
    ax.plot(yrs, p(0.5), color=ORANGE, lw=1.8, ls=(0, (5, 3)), label="0.5th percentile")
    ax.scatter([HORIZON], [L50 / 1e9], color=ORANGE, s=90, marker="X", zorder=5,
               label="50/50 year-15 guaranteed liability")
    ax.set_xlabel("projection year"); ax.set_ylabel("total assets (EUR bn)")
    ax.set_title("Monte-Carlo asset evolution – 50/50 base case (consistent pipeline)")
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")
    _style(ax); _save(fig, "lc_01_asset_evolution.png")

    # 02 - annual return distribution -----------------------------------
    a = ann.ravel() * 100
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.hist(a, bins=120, range=(np.percentile(a, 0.2), np.percentile(a, 99.8)),
            color=TEAL, alpha=0.9)
    ax.axvline(a.mean(), color=DTEAL, lw=2, ls=(0, (5, 3)), label=f"mean {a.mean():.1f}%")
    ax.axvline(0, color=INK, lw=1, ls=":", label="0%")
    ax.set_xlabel("annual portfolio return (%)  – contributions stripped")
    ax.set_ylabel("frequency (path-years)")
    ax.set_title("Simulated annual portfolio return distribution")
    ax.legend(frameon=False, fontsize=10)
    _style(ax); _save(fig, "lc_02_annual_return_distribution.png")

    # 03 - 15y IRR distribution ---------------------------------------
    ir = irr * 100
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.hist(ir, bins=90, range=(np.percentile(ir, 0.1), np.percentile(ir, 99.9)),
            color=TEAL, alpha=0.9)
    for q, c, lab in [(50, DTEAL, "median"), (5, ORANGE, "5th pct"), (0.5, RED, "0.5th pct")]:
        v = np.percentile(ir, q)
        ax.axvline(v, color=c, lw=2, ls=(0, (5, 3)), label=f"{lab} {v:.1f}%")
    ax.set_xlabel("15-year money-weighted return / IRR (%)")
    ax.set_ylabel("simulation count")
    ax.set_title("15-year portfolio return (IRR) distribution")
    ax.legend(frameon=False, fontsize=9.5)
    _style(ax); _save(fig, "lc_03_15year_IRR_distribution.png")

    # 04 - year-15 asset distribution -------------------------------
    a = a15 / 1e9
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.hist(a, bins=100, range=(np.percentile(a, 0.1), np.percentile(a, 99.6)),
            color=TEAL, alpha=0.9)
    ax.axvline(L50 / 1e9, color=ORANGE, lw=2.2, ls=(0, (5, 3)),
               label=f"50/50 liability €{L50/1e9:.1f}bn")
    ax.axvline(np.median(a), color=DTEAL, lw=2, label=f"median €{np.median(a):.1f}bn")
    ax.set_xlabel("total assets at year 15 (EUR bn)")
    ax.set_ylabel("simulation count")
    ax.set_title("Year-15 asset distribution")
    ax.legend(frameon=False, fontsize=9.5)
    _style(ax); _save(fig, "lc_04_year15_asset_distribution.png")

    # 05 - funding ratio distribution ------------------------------
    fr = a15 / L50 * 100
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.hist(fr, bins=100, range=(0, np.percentile(fr, 99.5)), color=TEAL, alpha=0.9)
    ax.axvline(100, color=RED, lw=2, ls=(0, (5, 3)), label="100% funded")
    ax.axvline(np.median(fr), color=DTEAL, lw=2, label=f"median {np.median(fr):.0f}%")
    ax.set_xlabel("funding ratio at year 15 (%)  – assets / 50-50 guaranteed liability")
    ax.set_ylabel("simulation count")
    ax.set_title("Funding-ratio distribution – 50/50 base case")
    ax.legend(frameon=False, fontsize=9.5)
    _style(ax); _save(fig, "lc_05_funding_ratio_distribution.png")

    # 06 - policyholder-choice sensitivity ------------------------
    shares = [0.0, 25.0, 50.0, 75.0, 100.0]
    under, liq = [], []
    for s in shares:
        Ls = float(liab.loc[s, "Total_Liability_Year15"])
        lump = float(liab.loc[s, "Lump_Sum_at_Year15"])
        under.append(np.mean(a15 < Ls) * 100)
        liq.append(np.mean(a15 < lump) * 100)
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.plot(shares, under, color=DTEAL, lw=2.4, marker="o", ms=7, label="underfunding probability")
    ax.plot(shares, liq, color=ORANGE, lw=2.4, marker="s", ms=7, label="liquidity-shortfall probability")
    ax.set_xlabel("policyholders electing the lump sum (%)")
    ax.set_ylabel("probability (%)")
    ax.set_title("Policyholder-choice sensitivity")
    ax.legend(frameon=False, fontsize=10)
    _style(ax); _save(fig, "lc_06_policyholder_sensitivity.png")

    # 07 - asset capacity vs policyholder choice -----------------
    Lline = [float(liab.loc[s, "Total_Liability_Year15"]) / 1e9 for s in shares]
    fig, ax = plt.subplots(figsize=(9.6, 4.6))
    ax.plot(shares, Lline, color=DTEAL, lw=2.4, marker="o", ms=7, label="year-15 liability")
    for q, ls, lab in [(50, "-", "median"), (5, (0, (4, 2)), "5th pct"),
                       (0.5, (0, (1, 2)), "0.5th pct")]:
        ax.axhline(np.percentile(a15, q) / 1e9, color=TEAL, lw=1.8, ls=ls,
                   label=f"{lab} year-15 assets")
    ax.set_xlabel("lump-sum take-up (%)"); ax.set_ylabel("EUR bn")
    ax.set_title("Asset capacity vs policyholder choice")
    ax.legend(frameon=False, fontsize=9)
    _style(ax); _save(fig, "lc_07_asset_vs_liability.png")


def report(res):
    liab, paths, irr, a15, ann = (res["liab"], res["paths"], res["irr"],
                                  res["a15"], res["ann"])
    L50 = float(liab.loc[50.0, "Total_Liability_Year15"])
    q = lambda x, p: float(np.percentile(x, p))
    L = [
        "# Case 3b - 15-year accumulation Monte-Carlo (consistent pipeline)\n",
        f"{N_SIM:,} paths, annual steps, Student-t (df {DF_T}).  Funding waterfall: "
        f"EUR 5.0bn -> cash-flow-dedicated FI book at t=0; EUR 0.5bn/yr -> the "
        f"14-index Aggressive Diversified RSP, years 1-10.  FI annual return "
        f"~ t(loc {FI_CARRY:.1%}, dampened duration effect); RSP ~ multivariate t "
        f"on the sleeves' historical annualised mean/cov.  Profit sharing starts "
        f"year 15, so it does not bite inside this 0-15 window.\n",
        "| metric | value |", "|---|--:|",
        f"| RSP blended assumption | mean 10.4% / vol 16.6% p.a. (historical) |",
        f"| median total assets, year 15 | EUR {q(a15,50)/1e9:.2f}bn |",
        f"| 5th percentile | EUR {q(a15,5)/1e9:.2f}bn |",
        f"| 0.5th percentile | EUR {q(a15,0.5)/1e9:.2f}bn |",
        f"| 50/50 guaranteed liability, year 15 | EUR {L50/1e9:.2f}bn |",
        f"| median funding ratio | {q(a15,50)/L50*100:.0f}% |",
        f"| median 15-year IRR | {q(irr,50)*100:.2f}% |",
        f"| 5th / 0.5th percentile IRR | {q(irr,5)*100:.2f}% / {q(irr,0.5)*100:.2f}% |",
        f"| P(underfunded, 50/50) | {np.mean(a15 < L50)*100:.2f}% |",
        f"| P(underfunded, 100% lump) | {np.mean(a15 < float(liab.loc[100.0,'Total_Liability_Year15']))*100:.2f}% |",
        f"| mean annual portfolio return | {ann.mean()*100:.2f}% |",
        "",
        "Charts: presentation/assets/lc_01..07_*.png",
    ]
    (OUT / "MC_LIFECYCLE_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    res = simulate()
    charts(res)
    report(res)
