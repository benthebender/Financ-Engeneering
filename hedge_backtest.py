"""
hedge_backtest.py
=================

Rolling 10-day / 95% VaR backtest of the floating-rate debt book, **unhedged**
vs **hedged with a single interest-rate swap**, for three VaR methods:

    * Delta-Normal   (analytic, first-order curve sensitivity x covariance)
    * Monte Carlo    (multivariate-normal curve shocks, full swap revaluation)
    * PCA + GARCH    (PCA factors x EWMA conditional vol, full revaluation)

It does **not** touch the standing pipeline (``Final version.py``).  Shared
numerics come from ``var_core.py``; the swap is priced with the same single-curve
30/360 exponential bootstrap as ``Data/forward_swap.py`` (a vectorised copy is
used here so 20k scenarios x hundreds of dates run in seconds; it is checked
against ``forward_swap.forward_swap_pv`` at import).

Book: EUR 14bn of FLOATING-RATE DEBT -- we are the borrower.  Rates rise ->
higher coupons -> LOSS.  The risk-reducing hedge is a PAYER swap (pay fixed /
receive float -> gains when rates rise).  Four payer swaps, struck at fair on the
first backtest date and held:

    irs_pay_5y,  irs_pay_10y     spot payer IRS  (receiver leg priced in A-IRA.py)
    fwd_pay_2y5y, fwd_pay_5y5y   forward-starting payer swap (forward_swap.py)

Debt P&L model (pipeline duration proxy, borrower sign):

    unhedged_pnl = DEBT_SIGN * DEBT_NOTIONAL * DEBT_DURATION * mean(delta_curve)

with ``DEBT_SIGN = -1``.  (Final version.py uses +1, a mark-to-market-of-the-
liability view; that is wrong for floating debt -- see the config comment.)

Outputs
-------
output/charts/12_hedge_var_backtest.png
    one panel per swap; rolling 95% 10-day VaR, 3 methods, unhedged (faint) vs
    hedged (bold).
output/charts/13_hedge_savings.png
    cumulative realised 10-day P&L: unhedged vs hedged with each swap.
output/charts/14_hedged_book_<name>.png  (one per swap)
    per-swap detail: hedged-book VaR (3 methods) + cumulative realised P&L.
output/charts/15_var_method_focus_{unhedged,irs_pay_5y}.png
    3 panels, one per VaR method: all three VaR lines over time with that
    method highlighted -- reads how conservative / loose each method is.
output/charts/16_spot_irs_vs_forward_swap.png
    head-to-head: unhedged vs spot payer IRS vs the two forward payer swaps --
    rolling VaR and cumulative realised P&L.
output/results/hedge_backtest_breaches.csv     exceptions + Kupiec / Christoffersen
output/results/hedge_backtest_savings.csv      what the hedge would have saved
output/results/hedge_backtest_var_timeseries.csv , hedge_backtest_realized_pnl.csv
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

_HERE = Path(__file__).resolve().parent
for _d in (_HERE, _HERE / "Data"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import var_core as vc                       # noqa: E402
from forward_swap import forward_swap_pv    # noqa: E402


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
# EUR 14bn of FLOATING-RATE DEBT -- we are the BORROWER, paying floating coupons.
# Rates rise -> higher interest expense -> LOSS.  So:
#     unhedged_pnl = -DEBT_NOTIONAL * DEBT_DURATION * mean(dcurve)      (DEBT_SIGN = -1)
# The risk-reducing hedge is a PAYER swap (pay fixed / receive float -> gains when
# rates rise, offsetting the debt).  A receiver swap would ADD to the loss.
# (The standing pipeline Final version.py uses +D*dy -- a mark-to-market-of-the-
#  liability view.  That is wrong for floating debt, whose MV barely moves and
#  whose real risk is the coupon.  DEBT_SIGN = -1 is the cash-flow view.)
DEBT_NOTIONAL = 14_000_000_000
DEBT_DURATION = 5.0                         # kept consistent with Final version.py
DEBT_SIGN = -1.0                            # -1: floating borrower, rates up -> loss

HEDGE_NOTIONAL = 14_000_000_000             # per swap; adjust here

ALPHA = 1.0 - vc.CONFIDENCE_LEVEL           # 0.05
HORIZON = vc.VAR_HORIZON_DAYS               # 10 business days

MIN_HISTORY = 750                           # obs before the first VaR estimate
STEP = 5                                    # re-estimate every 5 obs (~weekly)
N_MC = 20_000                               # scenarios per date for MC / PCA
SEED = 42


@dataclass(frozen=True)
class Instrument:
    name: str
    tenor: int                              # swap length in years
    position: str                           # "payer" | "receiver"
    notional: float = HEDGE_NOTIONAL
    start: int = 0                           # forward start in years (0 = spot)

    @property
    def end(self) -> int:
        return self.start + self.tenor

    @property
    def label(self) -> str:
        s = f"{self.start}y{self.tenor}y" if self.start else f"spot {self.tenor}y"
        return f"{s} {self.position}"


# spot-start payer IRS -- the borrower's hedge (pay fixed / receive float).
# (The "A - IRA.py" case sheet prices the receiver leg of the same swap.)
SPOT_IRS = [
    Instrument("irs_pay_5y", 5, "payer", start=0),
    Instrument("irs_pay_10y", 10, "payer", start=0),
]
# "forward swap we set up" (Data/forward_swap.py): forward-starting payer swaps.
FORWARD_SWAPS = [
    Instrument("fwd_pay_2y5y", 5, "payer", start=2),
    Instrument("fwd_pay_5y5y", 5, "payer", start=5),
]
INSTRUMENTS = SPOT_IRS + FORWARD_SWAPS
METHODS = ["Delta-Normal", "Monte Carlo", "PCA + GARCH"]

# the four books compared head-to-head in chart 16
COMPARE_BOOKS = ["unhedged", "irs_pay_5y", "fwd_pay_2y5y", "fwd_pay_5y5y"]


# --------------------------------------------------------------------------- #
# vectorised single-curve swap valuation  (matches Data/forward_swap.py)
# --------------------------------------------------------------------------- #
def _bootstrap_vec(rates: np.ndarray) -> np.ndarray:
    """rates: (n, 10) decimal annual par rates -> (n, 10) discount factors."""
    n, m = rates.shape
    df = np.empty((n, m))
    cum = np.zeros(n)
    for i in range(m):
        r = rates[:, i]
        df[:, i] = (1.0 - r * cum) / (1.0 + r)
        cum = cum + df[:, i]
    return df


def swap_pv_vec(curves_pct: np.ndarray, inst: Instrument, K: float) -> np.ndarray:
    """PV of a (possibly forward-starting) payer/receiver swap, batched.

    curves_pct : (n, 10) par rates in percent.  Returns (n,) PV in EUR.
    Fixed leg pays annually over years start+1 .. start+tenor; float leg is
    valued as DF(start) - DF(end).  Matches Data/forward_swap.py.
    """
    if inst.end > curves_pct.shape[1]:
        raise ValueError(f"{inst.name}: end {inst.end}y exceeds the 10y curve")
    df = _bootstrap_vec(curves_pct / 100.0)               # DF at years 1..10
    df_start = 1.0 if inst.start == 0 else df[:, inst.start - 1]
    df_end = df[:, inst.end - 1]
    annuity = df[:, inst.start:inst.end].sum(axis=1)      # DF at years start+1..end
    unit_payer = (df_start - df_end) - K * annuity
    sign = 1.0 if inst.position == "payer" else -1.0
    return sign * inst.notional * unit_payer


def _check_against_forward_swap() -> None:
    base = vc.curve_levels().iloc[-1].values * 100.0        # percent
    for inst in INSTRUMENTS:
        ref = forward_swap_pv(pd.Series(base, index=vc.RISK_NODES),
                              inst.notional, inst.start, inst.tenor,
                              position=inst.position)
        K = ref["fixed_rate"]
        mine = swap_pv_vec(base[None, :], inst, K)[0]
        assert abs(mine - ref["pv"]) < 1e-6, (inst.name, mine, ref["pv"])


_check_against_forward_swap()


# --------------------------------------------------------------------------- #
# revaluation
# --------------------------------------------------------------------------- #
def reval(base_pct: np.ndarray, dcurves_pct: np.ndarray,
          inst: Instrument | None, K: float | None):
    """P&L over the horizon for a batch of curve changes.

    base_pct    : (10,) current curve in percent
    dcurves_pct : (n, 10) horizon curve changes in percent
    returns (unhedged_pnl, hedged_pnl) each (n,)
    """
    dlevel = dcurves_pct.mean(axis=1) / 100.0
    unhedged = DEBT_SIGN * DEBT_NOTIONAL * DEBT_DURATION * dlevel
    if inst is None:
        return unhedged, unhedged
    scn = base_pct[None, :] + dcurves_pct
    pv_scn = swap_pv_vec(scn, inst, K)
    pv_base = swap_pv_vec(base_pct[None, :], inst, K)[0]
    hedge = pv_scn - pv_base
    return unhedged, unhedged + hedge


def sensitivity(base_pct: np.ndarray, inst: Instrument | None, K: float | None):
    """d(book PV in EUR) / d(rate_i in decimal)  ->  (10,) via 1bp bump-reval."""
    bump = np.eye(10) * 1e-2                          # +1bp on each tenor, percent
    u_up, h_up = reval(base_pct, bump, inst, K)
    u_0, h_0 = reval(base_pct, np.zeros((1, 10)), inst, K)
    book_up = h_up if inst is not None else u_up
    book_0 = (h_0 if inst is not None else u_0)[0]
    return (book_up - book_0) / 1e-4


# --------------------------------------------------------------------------- #
# backtest
# --------------------------------------------------------------------------- #
def run_backtest():
    rng = np.random.default_rng(SEED)

    # gap-filtered daily changes, then a rectangular (no-NaN) curve on the same
    # dates so every backtest step has all 10 tenors to price on
    changes = vc.curve_changes().dropna(how="any")
    levels = vc.curve_levels().reindex(changes.index).dropna(how="any")
    changes = changes.reindex(levels.index)
    levels_pct = levels[vc.RISK_NODES] * 100.0
    dates = levels_pct.index

    # struck rates: fair rate of each instrument on the first backtest date
    t0 = MIN_HISTORY
    base0 = levels_pct.iloc[t0].values
    struck = {}
    for inst in INSTRUMENTS:
        ref = forward_swap_pv(pd.Series(base0, index=vc.RISK_NODES),
                              inst.notional, inst.start, inst.tenor,
                              position=inst.position)
        struck[inst.name] = ref["fixed_rate"]

    eval_idx = range(t0, len(dates) - HORIZON, STEP)
    var_rows, breach_rows = [], []

    for t in eval_idx:
        date = dates[t]
        base_pct = levels_pct.iloc[t].values
        hist = changes.iloc[:t]

        cov_h = vc.cov_matrix(hist, HORIZON)
        mc_d = vc.mvn_scenarios(cov_h, N_MC, rng) * 100.0          # -> percent
        pca_d = vc.pca_ewma_scenarios(hist, N_MC, rng, HORIZON) * 100.0

        # realised horizon change (percent) for the breach test
        real_d = (levels_pct.iloc[t + HORIZON].values - base_pct)[None, :]

        for inst in [None, *INSTRUMENTS]:
            name = "unhedged" if inst is None else inst.name
            K = None if inst is None else struck[inst.name]

            # --- three VaR estimates -------------------------------------- #
            g = sensitivity(base_pct, inst, K)
            dn_var, _ = vc.delta_normal_var(g, cov_h, ALPHA)

            _, mc_pnl = reval(base_pct, mc_d, inst, K)
            mc_var, _ = vc.var_es(mc_pnl, ALPHA)

            _, pca_pnl = reval(base_pct, pca_d, inst, K)
            pca_var, _ = vc.var_es(pca_pnl, ALPHA)

            var_by_method = dict(zip(METHODS, [dn_var, mc_var, pca_var]))
            for m, v in var_by_method.items():
                var_rows.append((date, name, m, v))

            # --- realised P&L + breach flags ---------------------------- #
            _, real_pnl = reval(base_pct, real_d, inst, K)
            loss = -float(real_pnl[0])
            for m, v in var_by_method.items():
                breach_rows.append((date, name, m, loss, v, loss > v))

    var_ts = pd.DataFrame(var_rows, columns=["date", "book", "method", "var"])
    breaches = pd.DataFrame(
        breach_rows,
        columns=["date", "book", "method", "loss", "var", "breach"],
    )
    realized = realized_pnl_path(levels_pct, struck)
    return var_ts, breaches, realized


def realized_pnl_path(levels_pct: pd.DataFrame, struck: dict) -> pd.DataFrame:
    """Non-overlapping 10-day realised P&L, unhedged vs each hedged book.

    This is the "what actually happened" series behind the savings numbers:
    the hedge is struck once at the start and held; each row is the P&L over
    the next ``HORIZON`` business days.
    """
    idx = list(range(MIN_HISTORY, len(levels_pct) - HORIZON, HORIZON))
    rows = []
    for t in idx:
        base_pct = levels_pct.iloc[t].values
        real_d = (levels_pct.iloc[t + HORIZON].values - base_pct)[None, :]
        rec = {"date": levels_pct.index[t + HORIZON]}
        u, _ = reval(base_pct, real_d, None, None)
        rec["unhedged"] = float(u[0])
        for inst in INSTRUMENTS:
            _, h = reval(base_pct, real_d, inst, struck[inst.name])
            rec[inst.name] = float(h[0])
        rows.append(rec)
    out = pd.DataFrame(rows).set_index("date")
    return out


# --------------------------------------------------------------------------- #
# backtest statistics
# --------------------------------------------------------------------------- #
def _kupiec_lr(x: int, n: int, p: float) -> float:
    if n == 0 or x == 0:
        return float("nan")
    pi = x / n
    ll_null = (n - x) * np.log(1 - p) + x * np.log(p)
    ll_alt = (n - x) * np.log(1 - pi) + x * np.log(pi)
    return float(-2.0 * (ll_null - ll_alt))


def _christoffersen_ind_lr(flags: np.ndarray) -> float:
    f = flags.astype(int)
    n00 = n01 = n10 = n11 = 0
    for a, b in zip(f[:-1], f[1:]):
        n00 += (a == 0) & (b == 0)
        n01 += (a == 0) & (b == 1)
        n10 += (a == 1) & (b == 0)
        n11 += (a == 1) & (b == 1)
    if (n01 + n11) == 0 or (n00 + n01) == 0 or (n10 + n11) == 0:
        return float("nan")
    p01 = n01 / (n00 + n01)
    p11 = n11 / (n10 + n11)
    p = (n01 + n11) / (n00 + n01 + n10 + n11)
    ll_null = (n00 + n10) * np.log(1 - p) + (n01 + n11) * np.log(p)
    ll_alt = (n00 * np.log(1 - p01) + n01 * np.log(p01)
              + n10 * np.log(1 - p11) + n11 * np.log(p11))
    return float(-2.0 * (ll_null - ll_alt))


def breach_summary(breaches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (book, method), g in breaches.groupby(["book", "method"]):
        n, x = len(g), int(g.breach.sum())
        rows.append(dict(
            book=book, method=method, n=n, exceptions=x,
            rate=x / n, expected_rate=ALPHA,
            kupiec_LR=_kupiec_lr(x, n, ALPHA),
            kupiec_reject_5pct=_kupiec_lr(x, n, ALPHA) > 3.841,
            christoffersen_ind_LR=_christoffersen_ind_lr(g.breach.values),
        ))
    return pd.DataFrame(rows).sort_values(["book", "method"]).reset_index(drop=True)


def savings_summary(realized: pd.DataFrame, var_ts: pd.DataFrame,
                    breaches: pd.DataFrame) -> pd.DataFrame:
    """What the hedge would have saved over the backtest period, per swap.

    All figures in EUR.  "realised P&L" sums the non-overlapping 10-day P&Ls;
    "hedge contribution" is the extra P&L from holding the swap (= hedged -
    unhedged); "avg 95% VaR" averages across the three methods and dates.
    """
    u = realized["unhedged"]
    var_mean = (var_ts.groupby("book")["var"].mean())
    exc = breaches.groupby("book")["breach"].sum()

    rows = []
    for inst in INSTRUMENTS:
        h = realized[inst.name]
        rows.append(dict(
            swap=inst.name,
            realised_pnl_unhedged=u.sum(),
            realised_pnl_hedged=h.sum(),
            hedge_contribution=h.sum() - u.sum(),
            worst_10d_loss_unhedged=-u.min(),
            worst_10d_loss_hedged=-h.min(),
            worst_loss_reduction=(-u.min()) - (-h.min()),
            pnl_stdev_unhedged=u.std(),
            pnl_stdev_hedged=h.std(),
            avg_var_unhedged=var_mean["unhedged"],
            avg_var_hedged=var_mean[inst.name],
            avg_var_reduction=var_mean["unhedged"] - var_mean[inst.name],
            var_breaches_unhedged=int(exc["unhedged"]),
            var_breaches_hedged=int(exc[inst.name]),
        ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# plots
# --------------------------------------------------------------------------- #
_COL = {"Delta-Normal": "#111111", "Monte Carlo": "#d62728", "PCA + GARCH": "#2ca02c"}
_LS = {"Delta-Normal": (0, (1, 1)), "Monte Carlo": "-", "PCA + GARCH": "-"}
_Z = {"Monte Carlo": 1, "PCA + GARCH": 2, "Delta-Normal": 3}


def plot_var_panels(var_ts: pd.DataFrame, out_path: Path) -> None:
    """One panel per swap: rolling 95% VaR, unhedged (faint) vs hedged (bold)."""
    n = len(INSTRUMENTS)
    ncol = 2 if n > 1 else 1
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(7.5 * ncol, 4.8 * nrow),
                             sharex=True, squeeze=False)
    flat = axes.ravel()
    for ax, inst in zip(flat, INSTRUMENTS):
        un = var_ts[var_ts.book == "unhedged"]
        hd = var_ts[var_ts.book == inst.name]
        for m in METHODS:
            u, h = un[un.method == m], hd[hd.method == m]
            ax.plot(u.date, u["var"] / 1e6, color=_COL[m], ls=_LS[m], lw=1.0,
                    alpha=0.4, zorder=_Z[m], label=f"{m} (unhedged)")
            ax.plot(h.date, h["var"] / 1e6, color=_COL[m], ls=_LS[m], lw=1.7,
                    zorder=_Z[m] + 3, label=f"{m} (hedged)")
        ax.set_title(f"{inst.name}  ({inst.label}, N={inst.notional/1e9:.0f}bn)")
        ax.set_ylabel("95% 10-day VaR  (EUR m)")
        ax.grid(alpha=0.3)
    for ax in flat[n:]:
        ax.set_visible(False)
    flat[0].legend(fontsize=7, ncol=2, loc="upper left")
    fig.suptitle("Rolling 95% / 10-day VaR: unhedged 14bn floating book vs "
                 "single-swap hedge, three methods", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_savings(realized: pd.DataFrame, out_path: Path) -> None:
    """Cumulative realised P&L: unhedged vs hedged with each swap."""
    cum = realized.cumsum() / 1e6
    palette = ["#1f77b4", "#0b3d91", "#2ca02c", "#d62728", "#e6844a", "#9467bd"]
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(cum.index, cum["unhedged"], color="#777777", lw=2.4, label="unhedged")
    for inst, c in zip(INSTRUMENTS, palette):
        ax.plot(cum.index, cum[inst.name], color=c, lw=1.8,
                ls="-" if inst.start == 0 else (0, (4, 1, 1, 1)),
                label=f"hedged with {inst.name}")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_title("Cumulative realised 10-day P&L over the backtest "
                 "(hedge struck at start and held)")
    ax.set_ylabel("cumulative P&L  (EUR m)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_hedged_book(inst: Instrument, var_ts: pd.DataFrame,
                     realized: pd.DataFrame, out_path: Path) -> None:
    """Per-swap detail: hedged-book rolling VaR (3 methods) + cumulative P&L."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True,
                                   height_ratios=[3, 2])

    un = var_ts[var_ts.book == "unhedged"]
    hd = var_ts[var_ts.book == inst.name]
    for m in METHODS:
        ax1.plot(un[un.method == m].date, un[un.method == m]["var"] / 1e6,
                 color=_COL[m], ls=_LS[m], lw=1.0, alpha=0.35,
                 label=f"{m} (unhedged)")
        ax1.plot(hd[hd.method == m].date, hd[hd.method == m]["var"] / 1e6,
                 color=_COL[m], ls=_LS[m], lw=1.8, label=f"{m} (hedged)")
    ax1.set_ylabel("95% 10-day VaR  (EUR m)")
    ax1.set_title(f"Hedged book -- {inst.name}  ({inst.label}, "
                  f"N={inst.notional/1e9:.0f}bn)")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=7, ncol=2)

    cum = realized[["unhedged", inst.name]].cumsum() / 1e6
    ax2.plot(cum.index, cum["unhedged"], color="#777777", lw=2, label="unhedged")
    ax2.plot(cum.index, cum[inst.name], color="#1f77b4", lw=2, label="hedged")
    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_ylabel("cumulative realised P&L  (EUR m)")
    ax2.grid(alpha=0.3)
    ax2.legend()

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_method_focus(var_ts: pd.DataFrame, breaches: pd.DataFrame,
                      book: str, out_path: Path) -> None:
    """One panel per VaR method: all three VaR lines over time, that method
    highlighted, the other two greyed -- so you can read how conservative
    ("expensive") or loose ("free") each method is vs the others.
    """
    d = var_ts[var_ts.book == book]
    br = breaches[breaches.book == book]
    ymax = d["var"].max() / 1e6 * 1.05

    fig, axes = plt.subplots(1, len(METHODS), figsize=(6.5 * len(METHODS), 5.2),
                             sharey=True)
    for ax, focus in zip(np.atleast_1d(axes), METHODS):
        for m in METHODS:
            s = d[d.method == m].sort_values("date")
            if m == focus:
                ax.plot(s.date, s["var"] / 1e6, color=_COL[m], lw=2.1,
                        zorder=5, label=f"{m}  (this panel)")
            else:
                ax.plot(s.date, s["var"] / 1e6, color="#9aa0a6", lw=0.9,
                        alpha=0.7, zorder=2, label=m)
        g = br[br.method == focus]
        mean_var = d[d.method == focus]["var"].mean() / 1e6
        rate = g.breach.mean() if len(g) else float("nan")
        ax.set_title(f"{focus}\navg VaR {mean_var:,.0f} m   |   breaches "
                     f"{int(g.breach.sum())}/{len(g)} ({rate:.1%}, target {ALPHA:.0%})",
                     fontsize=10)
        ax.set_ylim(0, ymax)
        ax.grid(alpha=0.3)
    np.atleast_1d(axes)[0].set_ylabel("95% 10-day VaR  (EUR m)")
    np.atleast_1d(axes)[0].legend(fontsize=8, loc="upper left")
    fig.suptitle(f"VaR by method over time -- {book} book   "
                 f"(each panel highlights one method; grey = the other two)",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def plot_instrument_comparison(var_ts: pd.DataFrame, realized: pd.DataFrame,
                               method: str, out_path: Path) -> None:
    """Direct comparison: unhedged vs the spot 'A-IRS' vs the forward swaps.

    Left  : rolling 95% 10-day VaR over time (one VaR method).
    Right : cumulative realised 10-day P&L.
    Same colour per book on both panels.
    """
    books = [b for b in COMPARE_BOOKS if b in set(var_ts.book)]
    cols = {"unhedged": "#777777", "irs_pay_5y": "#1f77b4",
            "fwd_pay_2y5y": "#2ca02c", "fwd_pay_5y5y": "#d62728"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5.6))

    d = var_ts[var_ts.method == method]
    for b in books:
        s = d[d.book == b].sort_values("date")
        ax1.plot(s.date, s["var"] / 1e6, color=cols.get(b), lw=1.8,
                 label=f"{b}  (avg {s['var'].mean()/1e6:,.0f} m)")
    ax1.set_title(f"Rolling 95% / 10-day VaR  ({method})")
    ax1.set_ylabel("VaR  (EUR m)")
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8)

    cum = realized[books].cumsum() / 1e6
    for b in books:
        ax2.plot(cum.index, cum[b], color=cols.get(b), lw=1.8,
                 label=f"{b}  (end {cum[b].iloc[-1]:,.0f} m)")
    ax2.axhline(0, color="k", lw=0.8)
    ax2.set_title("Cumulative realised 10-day P&L")
    ax2.set_ylabel("cumulative P&L  (EUR m)")
    ax2.grid(alpha=0.3)
    ax2.legend(fontsize=8)

    fig.suptitle("Hedging impact: spot payer IRS vs forward-starting payer swap "
                 "(14bn floating borrower)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    out_dir = _HERE / "output"
    charts, results = out_dir / "charts", out_dir / "results"
    results.mkdir(parents=True, exist_ok=True)

    var_ts, breaches, realized = run_backtest()

    plot_var_panels(var_ts, charts / "12_hedge_var_backtest.png")
    plot_savings(realized, charts / "13_hedge_savings.png")
    for inst in INSTRUMENTS:
        plot_hedged_book(inst, var_ts, realized,
                         charts / f"14_hedged_book_{inst.name}.png")
    for bk in ("unhedged", "irs_pay_5y"):
        plot_method_focus(var_ts, breaches, bk,
                          charts / f"15_var_method_focus_{bk}.png")
    plot_instrument_comparison(var_ts, realized, "Monte Carlo",
                               charts / "16_spot_irs_vs_forward_swap.png")

    var_ts.to_csv(results / "hedge_backtest_var_timeseries.csv", index=False)
    realized.to_csv(results / "hedge_backtest_realized_pnl.csv")
    breach_tbl = breach_summary(breaches)
    breach_tbl.to_csv(results / "hedge_backtest_breaches.csv", index=False)
    save_tbl = savings_summary(realized, var_ts, breaches)
    save_tbl.to_csv(results / "hedge_backtest_savings.csv", index=False)

    fmt = lambda v: f"{v:,.0f}"
    print(f"backtest dates : {var_ts.date.min().date()} -> "
          f"{var_ts.date.max().date()}  ({var_ts.date.nunique()} VaR estimates, "
          f"{len(realized)} non-overlapping 10-day windows)")
    sign_txt = ("rates up -> gain (MV-of-liability view)"
                if DEBT_SIGN > 0 else "rates up -> loss (floating borrower)")
    print(f"horizon / conf : {HORIZON}d / {vc.CONFIDENCE_LEVEL:.0%}")
    print(f"book           : EUR {DEBT_NOTIONAL:,.0f} floating debt, duration "
          f"{DEBT_DURATION:g}, DEBT_SIGN={DEBT_SIGN:+.0f}  [{sign_txt}]")
    print(f"hedge          : {HEDGE_NOTIONAL:,.0f} per payer swap  "
          f"(2 spot IRS + 2 forward-starting)\n")

    print("EXCEPTION SUMMARY (expected rate = 5%)")
    with pd.option_context("display.width", 160,
                           "display.float_format", lambda v: f"{v:,.3f}"):
        print(breach_tbl.to_string(index=False))

    print("\nWHAT THE HEDGE WOULD HAVE SAVED  (EUR, over the whole period)")
    show = save_tbl.set_index("swap").T
    with pd.option_context("display.width", 200,
                           "display.float_format", fmt):
        print(show.to_string())

    print("\nSPOT PAYER IRS vs FORWARD PAYER SWAP  (Monte Carlo VaR / realised P&L)")
    mc = var_ts[var_ts.method == "Monte Carlo"]
    cmp_rows = []
    for b in COMPARE_BOOKS:
        v = mc[mc.book == b]["var"]
        r = realized[b]
        cmp_rows.append(dict(book=b, avg_VaR=v.mean(), max_VaR=v.max(),
                             pnl_stdev=r.std(), worst_10d_loss=-r.min(),
                             realised_pnl_total=r.sum()))
    with pd.option_context("display.width", 200, "display.float_format", fmt):
        print(pd.DataFrame(cmp_rows).set_index("book").to_string())

    print(f"\ncharts -> {charts}/12_hedge_var_backtest.png, 13_hedge_savings.png,")
    print("          14_hedged_book_*.png (4),")
    print("          15_var_method_focus_{unhedged,irs_pay_5y}.png,")
    print("          16_spot_irs_vs_forward_swap.png")
    print(f"tables -> {results}/hedge_backtest_*.csv")

    print(
        "\nnotes:\n"
        "  * DEBT_SIGN=-1: 14bn floating BORROWER, rates up -> loss. The PAYER\n"
        "    swap gains when rates rise -> it offsets the debt (hedged VaR <\n"
        "    unhedged).\n"
        "  * irs_pay_5y PV01 ~ the debt DV01 -> near DV01-neutral, kills most\n"
        "    of the VaR.\n"
        "  * fwd_pay_2y5y / fwd_pay_5y5y (the forward swap): live from day 1\n"
        "    but sensitivity is a 2-7y / 5-10y calendar spread, so at 14bn they\n"
        "    UNDER-hedge -- see chart 16. Scale notional up or use the spot IRS\n"
        "    for a tighter hedge.\n"
        "  * Delta-Normal ~ Monte Carlo: the book is near-linear; the gap is\n"
        "    just swap convexity (a few %).\n"
        "  * Christoffersen independence is rejected because the VaR grid\n"
        "    overlaps (STEP < HORIZON). Savings use non-overlapping windows."
    )
