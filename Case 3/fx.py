"""
fx.py
=====

FX forward / FX swap for hedging the USD sleeves of the return book back to EUR.

Case 3b: every USD-denominated index sleeve is rolled with a 1-year FX swap
(sell USD forward / buy EUR forward, rolled annually). The HKD leg of the
Hong Kong ETF is left unhedged and treated as USD.

Covered-interest-parity forward rate (EURUSD quoted as USD per EUR):

    F(T) = S * (1 + r_usd * T) / (1 + r_eur * T)          simple comp
         ~ S * exp((r_usd - r_eur) * T)                    cont. comp

For a sleeve of EUR market value `V_eur` invested in a USD index, the hedge is a
short USD forward on notional `N_usd = V_eur * S`. Once hedged, spot-FX P&L is
removed; the residual risk over the year is the change in the forward points,
i.e. the change in the `(r_usd - r_eur)` differential:

    hedge_pnl ~ -N_usd / S * V_eur ... (kept first order below)
    d(hedge_pnl) ~ -V_eur * T * d(r_usd - r_eur)

`carry` is the deterministic forward-points drag earned/paid over the period.
"""

from __future__ import annotations

import math

__all__ = ["fx_forward_rate", "hedge_carry", "hedge_rate_diff_sensitivity"]


def fx_forward_rate(spot: float, r_dom: float, r_for: float, T: float,
                    continuous: bool = False) -> float:
    """Forward FX rate under covered interest parity.

    `spot` is domestic per foreign (e.g. USD per EUR for EURUSD).
    `r_dom` / `r_for` are the two money-market rates (decimal), `T` in years.
    """
    if continuous:
        return spot * math.exp((r_dom - r_for) * T)
    return spot * (1.0 + r_dom * T) / (1.0 + r_for * T)


def hedge_carry(value_eur: float, r_eur: float, r_usd: float, T: float = 1.0) -> float:
    """Deterministic carry of a rolled 1y EUR/USD hedge on `value_eur`.

    Selling USD forward earns the EUR-USD rate differential: positive when
    EUR rates exceed USD rates. First order: value_eur * (r_eur - r_usd) * T.
    """
    return value_eur * (r_eur - r_usd) * T


def hedge_rate_diff_sensitivity(value_eur: float, T: float = 1.0) -> float:
    """d(hedge P&L) per +1.00 (100%) move in (r_usd - r_eur); scale by the
    actual differential change. Practically: value_eur * T * -d(r_usd - r_eur).
    Returned as the coefficient on -(d r_usd - d r_eur)."""
    return value_eur * T
