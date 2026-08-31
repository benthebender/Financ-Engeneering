"""
forward_swap.py
===============

Price a **forward-starting interest-rate swap** off the EUR par-swap curve that
``swap_curves.py`` produces.

Big picture
-----------
The project compares VaR methods on a book of floating-rate debt, hedged vs
unhedged.  The natural hedge for floating-rate debt (which bleeds cash when
rates rise) is a **payer** forward swap: pay fixed / receive float, so it *gains*
value when rates rise and offsets the higher coupons.

This module lets you:

1.  bootstrap a discount curve from the annual par-swap rates (1Y..10Y),
2.  compute the fair forward swap rate for any start / tenor,
3.  mark a forward swap (fixed rate ``K``, adjustable notional) to market on any
    curve - today's curve, or a shocked curve inside a VaR scenario.

Quick start
-----------
    from swap_curves import swap_curves
    from forward_swap import forward_swap_pv

    today = swap_curves.iloc[-1]                 # latest curve, in percent
    res = forward_swap_pv(today, notional=14_000_000_000,
                          start=0, tenor=5, position="payer")
    res["fair_forward_rate"]   # the 5y par swap rate
    res["pv"]                  # ~ 0 when priced at the fair rate
    K = res["fixed_rate"]      # struck rate - keep this for revaluation

This module only prices.  The VaR pipeline owns scenario generation: it builds
each shocked curve (historical / parametric / Monte-Carlo) and calls
``forward_swap_pv(scenario_curve, N, start, tenor, fixed_rate=K, ...)`` once per
scenario to get the P&L distribution.

Conventions & simplifications
-----------------------------
* Fixed leg: annual, 30/360 -> year fraction 1.0 (``freq=1``).  ``freq`` can be
  raised for the valuation schedule, but the bootstrap always uses the annual
  par rates as given.
* Float leg valued as ``DF(start) - DF(end)`` (textbook par float leg, unit
  notional, no tenor/xccy basis).
* Discount factors between the 1Y..10Y nodes: log-linear interpolation
  (piecewise-constant instantaneous forward); flat-forward extrapolation past
  10Y.
* ``rates`` are taken in **percent** by default (matching ``swap_curves``);
  ``fixed_rate`` is ALWAYS a decimal (0.031 == 3.1 %).
* All rates are treated as a single discount/forecast curve (single-curve
  valuation) - fine for a teaching VaR study, not for a trading desk.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# make ``import swap_curves`` work no matter which folder this file is run from
# --------------------------------------------------------------------------- #
def _ensure_swap_curves_importable() -> "Path | None":
    roots = [Path(__file__).resolve().parent, *Path(__file__).resolve().parents[:4],
             Path.cwd()]
    subs = ["", "Data", "Financ-Engeneering", "Financ-Engeneering/Data",
            "Financ-Engeneering/Financ-Engeneering/Data"]
    for root in roots:
        for sub in subs:
            d = root / sub if sub else root
            if (d / "swap_curves.py").is_file():
                if str(d) not in sys.path:
                    sys.path.insert(0, str(d))
                return d
    return None


_ensure_swap_curves_importable()

__all__ = [
    "DiscountCurve",
    "bootstrap_discount_curve",
    "price_forward_swap",
    "forward_swap_pv",
]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _years(x) -> float:
    """Accept 5, 5.0 or '5Y' / '5y' and return 5.0."""
    if isinstance(x, str):
        m = re.match(r"\s*(\d+(?:\.\d+)?)\s*[Yy]?\s*$", x)
        if not m:
            raise ValueError(f"cannot parse tenor {x!r}")
        return float(m.group(1))
    return float(x)


def _prep_rates(rates, percent: bool) -> pd.Series:
    """Normalise the curve input to a decimal Series indexed by year (float)."""
    if isinstance(rates, pd.DataFrame):
        rates = rates.iloc[-1]
    s = pd.Series(rates).dropna()
    s.index = [_years(i) for i in s.index]
    s = s.sort_index()
    if s.empty:
        raise ValueError("no swap rates supplied")
    return s / 100.0 if percent else s.astype(float)


# --------------------------------------------------------------------------- #
# discount curve
# --------------------------------------------------------------------------- #
@dataclass
class DiscountCurve:
    """Discount factors on an annual grid, with interpolation/extrapolation."""

    nodes: np.ndarray   # maturities in years, ascending, > 0
    dfs: np.ndarray      # discount factor at each node

    def __post_init__(self) -> None:
        self.nodes = np.asarray(self.nodes, dtype=float)
        self.dfs = np.asarray(self.dfs, dtype=float)
        self._T = np.concatenate(([0.0], self.nodes))
        self._logdf = np.concatenate(([0.0], np.log(self.dfs)))

    # -- discount factor at arbitrary time(s) ------------------------------- #
    def df(self, t):
        t = np.asarray(t, dtype=float)
        log = np.interp(t, self._T, self._logdf)          # flat outside range
        slope = (self._logdf[-1] - self._logdf[-2]) / (self._T[-1] - self._T[-2])
        log = np.where(t > self._T[-1],
                       self._logdf[-1] + slope * (t - self._T[-1]), log)
        out = np.exp(log)
        return float(out) if out.ndim == 0 else out

    def zero_rate(self, t):
        """Continuously-compounded zero rate for maturity ``t`` (years)."""
        t = np.asarray(t, dtype=float)
        return -np.log(self.df(t)) / np.where(t == 0, np.nan, t)

    # -- swap building blocks -------------------------------------------- #
    def annuity(self, start, end, freq: int = 1) -> float:
        """PV of 1.0 paid every ``1/freq`` year from ``start`` to ``end``."""
        start, end = _years(start), _years(end)
        tau = 1.0 / freq
        n = int(round((end - start) * freq))
        times = start + tau * np.arange(1, n + 1)
        return float(np.sum(tau * self.df(times)))

    def forward_swap_rate(self, start, tenor, freq: int = 1) -> float:
        """Fair (par) fixed rate of the swap starting at ``start`` for ``tenor``."""
        start = _years(start)
        end = start + _years(tenor)
        return (self.df(start) - self.df(end)) / self.annuity(start, end, freq)


def bootstrap_discount_curve(rates, *, percent: bool = True,
                             freq: int = 1) -> DiscountCurve:
    """Bootstrap discount factors from annual par-swap rates.

    ``rates`` : Series / dict / DataFrame(last row) of par rates keyed by tenor
                ("1Y".."10Y" or 1..10).  Missing annual nodes up to the longest
                tenor are linearly interpolated on the par rate.
    """
    s = _prep_rates(rates, percent)
    n_max = int(round(s.index.max()))
    grid = np.arange(1, n_max + 1, dtype=float)
    par = np.interp(grid, s.index.to_numpy(), s.to_numpy())

    dfs = np.empty(n_max)
    cum = 0.0                                   # running sum of discount factors
    for i, r in enumerate(par):                 # tau = 1.0 (annual fixed leg)
        dfs[i] = (1.0 - r * cum) / (1.0 + r)
        cum += dfs[i]
    return DiscountCurve(grid, dfs)


# --------------------------------------------------------------------------- #
# pricing
# --------------------------------------------------------------------------- #
def price_forward_swap(curve: DiscountCurve, notional: float, start, tenor,
                       fixed_rate: "float | None" = None,
                       position: str = "payer", freq: int = 1) -> dict:
    """Mark a forward swap to market on ``curve``.

    Parameters
    ----------
    curve        : bootstrapped ``DiscountCurve``.
    notional     : swap notional (adjustable).  PV scales linearly with it.
    start, tenor : forward start and swap length, in years ("2Y" or 2 both work).
    fixed_rate   : contractual fixed rate as a **decimal**.  ``None`` -> use the
                   fair forward rate (PV is then ~0: use this to "strike" a new
                   hedge, then revalue with that number under each VaR scenario).
    position     : "payer" (pay fixed / receive float - the hedge for floating
                   debt) or "receiver".
    freq         : fixed-leg payments per year for the valuation schedule.

    Returns
    -------
    dict with pv, fair_forward_rate, fixed_rate, annuity, df_start, df_end,
    pv01 (PV change per +1bp on the fixed rate, signed for ``position``), plus
    the echoed inputs.
    """
    start = _years(start)
    tenor = _years(tenor)
    end = start + tenor

    df_s = curve.df(start)
    df_e = curve.df(end)
    annuity = curve.annuity(start, end, freq)
    fair = (df_s - df_e) / annuity

    K = fair if fixed_rate is None else float(fixed_rate)
    pos = position.lower()
    if pos.startswith("pay"):
        sign = 1.0
    elif pos.startswith("rec"):
        sign = -1.0
    else:
        raise ValueError("position must be 'payer' or 'receiver'")

    # value to the fixed-rate payer, per unit notional:
    #   float leg PV - fixed leg PV = (df_s - df_e) - K * annuity = annuity*(fair-K)
    unit_pv = (df_s - df_e) - K * annuity
    pv = sign * notional * unit_pv

    return {
        "pv": pv,
        "fair_forward_rate": fair,
        "fixed_rate": K,
        "annuity": annuity,
        "df_start": df_s,
        "df_end": df_e,
        "pv01": sign * notional * annuity * 1e-4,
        "notional": notional,
        "start": start,
        "end": end,
        "tenor": tenor,
        "position": "payer" if sign > 0 else "receiver",
    }


def forward_swap_pv(rates, notional: float, start, tenor,
                    fixed_rate: "float | None" = None, position: str = "payer",
                    *, percent: bool = True, freq: int = 1) -> dict:
    """One-shot: bootstrap ``rates`` then price the forward swap.

    ``rates`` follows the ``percent`` flag (default True, matching
    ``swap_curves``).  ``fixed_rate`` is always a decimal.  The bootstrapped
    ``DiscountCurve`` is returned under the ``"curve"`` key.
    """
    curve = bootstrap_discount_curve(rates, percent=percent, freq=freq)
    res = price_forward_swap(curve, notional, start, tenor,
                             fixed_rate, position, freq)
    res["curve"] = curve
    return res


# --------------------------------------------------------------------------- #
if __name__ == "__main__":                       # sanity check only
    from swap_curves import swap_curves

    today = swap_curves.iloc[-1]
    NOTIONAL = 14_000_000_000

    print(f"curve date : {swap_curves.index[-1].date()}")
    for tenor in (5, 10):
        r = forward_swap_pv(today, NOTIONAL, start=0, tenor=tenor,
                            position="payer")
        print(f"0y{tenor}y payer  notional {NOTIONAL:,.0f}")
        print(f"  fair rate       : {r['fair_forward_rate'] * 100:.4f} %")
        print(f"  PV @ fair rate  : {r['pv']:,.2f}")
        print(f"  PV01 (per +1bp) : {r['pv01']:,.2f}")
