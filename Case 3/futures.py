"""
futures.py
==========

Equity-index futures: fair-value pricing, mark-to-market P&L, and contract
sizing for a short-futures overlay on the return book.

The *hedge rule* (how large a short to put on, e.g. a VIX-threshold trigger) is
out of scope here and owned by the strategy team. This module only answers:

    * what is the future worth        -> fair_price(), basis()
    * what is a position worth / P&L  -> contract_value(), mark_to_market()
    * how many contracts for a target -> contracts_for_notional(), hedge_contracts()
    * what does carrying it cost       -> carry_pnl()

Cost-of-carry model (continuous compounding)

    F(t, T) = S(t) * exp( (r - q) * tau )          tau = year fraction to expiry

`r` is the EUR financing rate (the return book is funded/valued in EUR after the
FX swap), `q` is the index dividend yield. Equivalently, with a discrete
dividend PV `D`:  F = (S - D) * exp(r * tau).

For a **short** hedge, pass a negative `n_contracts`; every function is
sign-consistent so P&L, exposure and carry all flip together.

All amounts are in EUR index points * multiplier unless noted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

__all__ = [
    "year_fraction",
    "EquityIndexFuture",
    "fair_price",
    "hedge_contracts",
]

_DAYS_PER_YEAR = 365.0


def year_fraction(start: date, end: date) -> float:
    """ACT/365F year fraction; clamped at 0."""
    return max(0.0, (end - start).days / _DAYS_PER_YEAR)


def fair_price(
    spot: float,
    r: float,
    tau: float,
    q: float = 0.0,
    discrete_div_pv: float = 0.0,
) -> float:
    """Cost-of-carry fair future price.

    spot            : current index level S(t)
    r               : EUR financing rate, continuously compounded (decimal)
    tau             : year fraction to expiry
    q               : continuous dividend yield (decimal); ignored if
                      `discrete_div_pv` is given
    discrete_div_pv : PV of discrete dividends paid before expiry, in index
                      points. If > 0, F = (S - D) * exp(r * tau).
    """
    if discrete_div_pv:
        return (spot - discrete_div_pv) * math.exp(r * tau)
    return spot * math.exp((r - q) * tau)


@dataclass(frozen=True)
class EquityIndexFuture:
    """One listed equity-index future contract.

    underlying        : label, e.g. "MSCI World Index"
    multiplier        : EUR value of one index point per contract (point value)
    expiry            : contract expiry date
    dividend_yield    : continuous q (decimal); 0 if you price with discrete divs
    currency          : contract currency (return book is EUR after the FX swap)
    """

    underlying: str
    multiplier: float
    expiry: date
    dividend_yield: float = 0.0
    currency: str = "EUR"

    # -- pricing -------------------------------------------------------- #
    def tau(self, as_of: date) -> float:
        return year_fraction(as_of, self.expiry)

    def fair_price(
        self,
        spot: float,
        r: float,
        as_of: date,
        discrete_div_pv: float = 0.0,
    ) -> float:
        return fair_price(
            spot, r, self.tau(as_of), self.dividend_yield, discrete_div_pv
        )

    def basis(self, spot: float, r: float, as_of: date, **kw) -> float:
        """Fair future minus spot (index points). Positive when r > q."""
        return self.fair_price(spot, r, as_of, **kw) - spot

    # -- position economics ------------------------------------------- #
    def contract_value(self, price: float) -> float:
        """EUR notional represented by ONE contract at `price`."""
        return price * self.multiplier

    def position_notional(self, n_contracts: float, price: float) -> float:
        """Signed EUR exposure of `n_contracts` (negative = short)."""
        return n_contracts * self.contract_value(price)

    def mark_to_market(
        self, n_contracts: float, entry_price: float, current_price: float
    ) -> float:
        """P&L in EUR of holding `n_contracts` from `entry_price` to
        `current_price` (futures settle to variation margin, so this is the
        realised + unrealised P&L since entry / last mark)."""
        return n_contracts * self.multiplier * (current_price - entry_price)

    def delta_eur_per_index_pct(
        self, n_contracts: float, spot: float
    ) -> float:
        """EUR P&L for a +1% move in the underlying index (first order,
        F ~ S).  Feed this straight into the risk map as the sleeve's futures
        delta."""
        return n_contracts * self.multiplier * spot * 0.01

    def carry_pnl(
        self,
        n_contracts: float,
        spot: float,
        r: float,
        days: float,
    ) -> float:
        """Approximate carry earned/paid over `days` by holding the future
        instead of the funded cash index:  -(r - q) * exposure * dt.
        A short future (n < 0) *earns* positive carry when r > q."""
        dt = days / _DAYS_PER_YEAR
        exposure = self.position_notional(n_contracts, spot)
        return -(r - self.dividend_yield) * exposure * dt

    # -- sizing ------------------------------------------------------- #
    def contracts_for_notional(
        self, target_notional_eur: float, price: float, whole: bool = True
    ) -> float:
        """Contracts whose exposure ~= `target_notional_eur` (signed)."""
        raw = target_notional_eur / self.contract_value(price)
        return float(round(raw)) if whole else raw

    def roll(
        self,
        n_contracts: float,
        old_price: float,
        new_expiry: date,
        new_price: float,
    ) -> "tuple[EquityIndexFuture, float, float]":
        """Roll into the next contract month. Returns (new_future,
        n_contracts_kept_notional_neutral, roll_cost_eur).  Roll cost is the
        calendar spread paid: n * multiplier * (new_price - old_price)."""
        rolled = EquityIndexFuture(
            self.underlying, self.multiplier, new_expiry,
            self.dividend_yield, self.currency,
        )
        roll_cost = n_contracts * self.multiplier * (new_price - old_price)
        return rolled, n_contracts, roll_cost


def hedge_contracts(
    future: EquityIndexFuture,
    equity_notional_eur: float,
    price: float,
    hedge_ratio: float,
    beta: float = 1.0,
    whole: bool = True,
) -> float:
    """Number of contracts to SHORT to hedge `hedge_ratio` of a long equity
    exposure (returns a NEGATIVE number).

        n = - hedge_ratio * beta * equity_notional_eur / (price * multiplier)

    `hedge_ratio` (the "x%") and any regime rule (VIX threshold, ...) are
    supplied by the caller; this only converts a chosen ratio into a lot count.
    """
    target_short = -hedge_ratio * beta * equity_notional_eur
    return future.contracts_for_notional(target_short, price, whole=whole)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    from datetime import date as _d

    fut = EquityIndexFuture(
        underlying="MSCI World Index",
        multiplier=50.0,               # EUR per index point (example)
        expiry=_d(2026, 12, 18),
        dividend_yield=0.018,
    )
    as_of = _d(2026, 9, 2)
    spot = 3_800.0
    r_eur = 0.0331                      # ~ 5y EUR swap, continuous

    F = fut.fair_price(spot, r_eur, as_of)
    print(f"{fut.underlying}: spot {spot:,.1f}  fair future {F:,.2f}  "
          f"basis {fut.basis(spot, r_eur, as_of):+.2f} pts  "
          f"(tau {fut.tau(as_of):.3f}y)")

    # short 60% of a EUR 2.0bn equity sleeve
    eq_notional = 2_000_000_000.0
    n = hedge_contracts(fut, eq_notional, F, hedge_ratio=0.60)
    print(f"short hedge 60%: {n:,.0f} contracts  "
          f"exposure {fut.position_notional(n, F)/1e6:,.1f}m EUR")
    print(f"  P&L if index -10%: "
          f"{fut.mark_to_market(n, F, F*0.90)/1e6:,.2f}m EUR")
    print(f"  10-day carry:      "
          f"{fut.carry_pnl(n, spot, r_eur, 10)/1e3:,.2f}k EUR")
    print(f"  delta (EUR per +1% index): "
          f"{fut.delta_eur_per_index_pct(n, spot)/1e3:,.2f}k EUR")
