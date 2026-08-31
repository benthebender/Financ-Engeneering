"""
var_core.py
===========

Importable, side-effect-free core for the interest-rate VaR work.

The standing report script (``Final version.py``) stays untouched and keeps
running standalone.  This module re-implements only its *reusable numerical
pieces* so the hedge backtest (``hedge_backtest.py``) and, later, the report can
share one source of truth:

    curve_changes()        per-tenor daily rate changes from swap_curves
    horizon_changes()      overlapping h-day curve-change scenarios (historical)
    nearest_psd()          eigenvalue-clipped PSD repair
    cov_matrix()           h-day covariance of the tenor changes (PSD)
    mvn_scenarios()        parametric / plain Monte-Carlo curve-change draws
    pca_ewma_scenarios()   PCA factors x EWMA("GARCH") vol curve-change draws
    var_es()               empirical VaR / ES from a P&L sample
    delta_normal_var()     analytic VaR from a sensitivity (DV01) vector

Conventions
-----------
* ``RISK_NODES`` = 1Y..10Y.
* Rate changes are decimals (0.0001 == 1bp).
* VaR / ES are returned as positive EUR loss numbers.
* Defaults: 95% confidence, 10 business-day horizon.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# make swap_curves importable whether run from the repo root or Data/
_HERE = Path(__file__).resolve().parent
for _d in (_HERE, _HERE / "Data", _HERE.parent / "Data"):
    if (_d / "swap_curves.py").is_file() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from swap_curves import load_swap_curves  # noqa: E402

RISK_NODES = ["1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y"]
CONFIDENCE_LEVEL = 0.95
VAR_HORIZON_DAYS = 10
MAX_CALENDAR_GAP = 4          # Fri->Mon ok; drop changes spanning a longer hole


# --------------------------------------------------------------------------- #
# 1. curve data -> daily changes
# --------------------------------------------------------------------------- #
def curve_levels(path=None) -> pd.DataFrame:
    """Swap curve in **decimal**, columns ``RISK_NODES``, clean DatetimeIndex."""
    df = load_swap_curves(path, as_decimal=True)
    return df[RISK_NODES]


def curve_changes(levels: pd.DataFrame | None = None,
                  max_gap_days: int = MAX_CALENDAR_GAP) -> pd.DataFrame:
    """Per-tenor 1-day rate changes (decimal).

    Computed maturity-by-maturity from each tenor's own observed dates (an
    outer-join ``diff`` would turn a multi-day hole into one "daily" move), and
    changes that span more than ``max_gap_days`` calendar days are dropped.
    """
    levels = curve_levels() if levels is None else levels
    cols = []
    for node in RISK_NODES:
        s = levels[node].dropna()
        gap = s.index.to_series().diff().dt.days
        chg = s.diff().where(gap <= max_gap_days)
        cols.append(chg.rename(node))
    return pd.concat(cols, axis=1).sort_index()[RISK_NODES]


def horizon_changes(changes: pd.DataFrame,
                    horizon: int = VAR_HORIZON_DAYS,
                    overlapping: bool = True) -> pd.DataFrame:
    """h-day curve changes as a rolling (overlapping) sum of daily changes."""
    out = changes[RISK_NODES].rolling(horizon, min_periods=horizon).sum()
    out = out.dropna(how="any")
    return out if overlapping else out.iloc[::horizon]


# --------------------------------------------------------------------------- #
# 2. covariance
# --------------------------------------------------------------------------- #
def nearest_psd(matrix) -> np.ndarray:
    m = np.asarray(matrix, dtype=float)
    m = (m + m.T) / 2.0
    w, v = np.linalg.eigh(m)
    w = np.maximum(w, 1e-16)
    return (v * w) @ v.T


def cov_matrix(changes: pd.DataFrame,
               horizon: int = VAR_HORIZON_DAYS,
               min_periods: int = 100) -> np.ndarray:
    """PSD ``horizon``-day covariance of the tenor changes (EUR-free, decimal^2)."""
    daily = changes[RISK_NODES].cov(min_periods=min_periods).values
    return nearest_psd(daily) * horizon


# --------------------------------------------------------------------------- #
# 3. scenario generators  ->  (n_scenarios, 10) arrays of h-day curve changes
# --------------------------------------------------------------------------- #
def mvn_scenarios(cov_h: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Plain multivariate-normal curve-change draws (parametric / Monte Carlo)."""
    return rng.multivariate_normal(np.zeros(len(cov_h)), cov_h, size=n)


def pca_ewma_scenarios(changes: pd.DataFrame,
                       n: int,
                       rng: np.random.Generator,
                       horizon: int = VAR_HORIZON_DAYS,
                       n_factors: int = 3,
                       lam: float = 0.94) -> np.ndarray:
    """PCA factor simulation with an EWMA conditional-vol ("GARCH") proxy.

    A full GARCH MLE per rolling date is slow and fragile, so the factor
    variance is tracked with a RiskMetrics EWMA (``lam=0.94``); the last
    conditional sigma sets the simulation scale.  Keeps the "vol clusters"
    behaviour of GARCH at a fraction of the cost.
    """
    x = changes[RISK_NODES].dropna(how="any").values
    x = x - x.mean(axis=0, keepdims=True)
    cov = nearest_psd(np.cov(x, rowvar=False))
    w, v = np.linalg.eigh(cov)
    order = np.argsort(w)[::-1][:n_factors]
    loadings = v[:, order]                     # (10, k)
    scores = x @ loadings                      # (T, k) historical factor scores

    # EWMA variance path per factor -> last conditional sigma
    sig2 = scores.var(axis=0)
    for t in range(1, len(scores)):
        sig2 = lam * sig2 + (1.0 - lam) * scores[t - 1] ** 2
    sigma_h = np.sqrt(sig2 * horizon)          # (k,)

    z = rng.standard_normal((n, n_factors)) * sigma_h
    return z @ loadings.T                      # (n, 10)


# --------------------------------------------------------------------------- #
# 4. VaR / ES
# --------------------------------------------------------------------------- #
def var_es(pnl, alpha: float = 1.0 - CONFIDENCE_LEVEL):
    """Empirical VaR and ES (positive EUR losses) from a P&L sample."""
    pnl = np.asarray(pnl, dtype=float)
    cutoff = np.quantile(pnl, alpha)
    tail = pnl[pnl <= cutoff]
    return -cutoff, (-tail.mean() if tail.size else -cutoff)


def delta_normal_var(sens: np.ndarray, cov_h: np.ndarray,
                     alpha: float = 1.0 - CONFIDENCE_LEVEL):
    """Analytic VaR / ES from a first-order sensitivity vector.

    ``sens[i]`` = d(book PV in EUR) / d(rate_i in decimal).  Returns positive
    EUR losses using the Gaussian VaR and ES multipliers.
    """
    from scipy.stats import norm  # local import; falls back below if missing

    sigma = float(np.sqrt(sens @ cov_h @ sens))
    z = norm.ppf(1.0 - alpha)
    es_mult = norm.pdf(z) / alpha
    return z * sigma, es_mult * sigma


# graceful fallback if scipy is unavailable
try:  # pragma: no cover
    import scipy.stats  # noqa: F401
except Exception:  # pragma: no cover
    _Z = {0.05: 1.6448536269514722, 0.01: 2.3263478740408408}
    _ESM = {0.05: 2.0627128054041565, 0.01: 2.6652142594983405}

    def delta_normal_var(sens, cov_h, alpha=1.0 - CONFIDENCE_LEVEL):  # noqa: F811
        sigma = float(np.sqrt(np.asarray(sens) @ cov_h @ np.asarray(sens)))
        return _Z.get(round(alpha, 4), 1.6449) * sigma, \
            _ESM.get(round(alpha, 4), 2.0627) * sigma


__all__ = [
    "RISK_NODES", "CONFIDENCE_LEVEL", "VAR_HORIZON_DAYS",
    "curve_levels", "curve_changes", "horizon_changes",
    "nearest_psd", "cov_matrix",
    "mvn_scenarios", "pca_ewma_scenarios",
    "var_es", "delta_normal_var",
]
