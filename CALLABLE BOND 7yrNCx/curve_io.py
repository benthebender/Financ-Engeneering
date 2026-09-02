"""
curve_io.py
===========

Locate the EUR par-swap curve produced elsewhere in the repo and turn it into a
bootstrapped :class:`DiscountCurve` for the callable-bond engine.

This module is deliberately thin: it reuses ``swap_curves.py`` (the Excel loader)
and ``forward_swap.py`` (the annual bootstrap + log-linear discount curve) that
already live in the project, hunting for them on ``sys.path`` the same way the
other scripts do.

Public API
----------
    load_par_rates(path=None, date=None, tenors=None) -> pd.Series
        Par-swap rates in **percent**, indexed "1Y".."10Y", for one curve date.

    build_discount_curve(par_rates_pct) -> DiscountCurve
        Bootstrap the annual discount curve (delegates to forward_swap).

    max_curve_tenor(curve_or_rates) -> int
        Longest tenor available, in whole years - the hard cap on bond maturity.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# make the existing project modules importable no matter where this folder
# sits relative to them
# --------------------------------------------------------------------------- #
_WANTED = ("swap_curves.py", "forward_swap.py")
_SUBS = (
    "",
    "Data",
    "Financ-Engeneering",
    "Financ-Engeneering/Data",
    "Financ-Engeneering/Financ-Engeneering",
    "Financ-Engeneering/Financ-Engeneering/Data",
)


def _add_project_modules_to_path() -> None:
    here = Path(__file__).resolve()
    for root in (here.parent, *here.parents):
        for sub in _SUBS:
            d = root / sub if sub else root
            if any((d / w).is_file() for w in _WANTED) and str(d) not in sys.path:
                sys.path.insert(0, str(d))


_add_project_modules_to_path()

try:
    from forward_swap import DiscountCurve, bootstrap_discount_curve  # noqa: E402
except Exception as exc:  # pragma: no cover - environment problem, not logic
    raise ImportError(
        "curve_io.py needs 'forward_swap.py' from the project on sys.path; "
        "could not import it. Searched relative to "
        f"{Path(__file__).resolve().parent}."
    ) from exc

try:
    import swap_curves as _swap_curves_mod  # noqa: E402
    from swap_curves import load_swap_curves  # noqa: E402
except Exception:  # pragma: no cover
    _swap_curves_mod = None
    load_swap_curves = None


__all__ = [
    "DiscountCurve",
    "bootstrap_discount_curve",
    "load_par_rates",
    "build_discount_curve",
    "max_curve_tenor",
    "years_of_tenor",
    "resolved_workbook",
]


def resolved_workbook() -> "Path | None":
    """The ``Swap curves.xlsx`` that ``swap_curves.py`` would read, if locatable."""
    if _swap_curves_mod is None:
        return None
    try:
        return _swap_curves_mod._find_workbook()
    except Exception:  # pragma: no cover
        return None


def years_of_tenor(label) -> int:
    """'7Y' / '7y' / 7 / 7.0  ->  7 (int)."""
    if isinstance(label, (int, float)):
        return int(round(label))
    m = re.match(r"\s*(\d+)\s*[Yy]?\s*$", str(label))
    if not m:
        raise ValueError(f"cannot read a tenor in years from {label!r}")
    return int(m.group(1))


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_par_rates(
    path: "str | Path | None" = None,
    *,
    date: "str | pd.Timestamp | None" = None,
    tenors: "list[int] | None" = None,
) -> pd.Series:
    """One curve date's par-swap rates, in **percent**, index ``"1Y".."10Y"``.

    Parameters
    ----------
    path    : location of ``Swap curves.xlsx``; ``None`` -> auto-find.
    date    : curve date to pull. ``None`` -> the latest date on which every
              requested tenor is quoted. A string/Timestamp is matched exactly,
              falling back to the most recent quote on or before it.
    tenors  : subset of maturities (years) to keep; ``None`` -> all (1..10).
    """
    if load_swap_curves is None:  # pragma: no cover
        raise ImportError(
            "swap_curves.py was not found on sys.path; cannot load the curve. "
            "Pass a bootstrapped DiscountCurve directly instead."
        )

    df = load_swap_curves(path, tenors=tenors)  # percent, DatetimeIndex

    if date is None:
        full = df.dropna(how="any")
        row = (full if not full.empty else df.ffill()).iloc[-1]
    else:
        ts = pd.Timestamp(date)
        if ts in df.index:
            row = df.loc[ts]
        else:
            upto = df.loc[:ts]
            if upto.empty:
                raise KeyError(f"no curve quote on or before {ts.date()}")
            row = upto.ffill().iloc[-1]

    curve_ts = row.name  # the Timestamp we actually landed on
    row = row.dropna()
    if row.empty:
        raise ValueError("selected curve date has no usable quotes")
    row.name = "par_swap_rate_pct"
    # provenance: which file / which observation date actually fed the pipeline
    row.attrs["workbook"] = str(path) if path is not None else str(resolved_workbook())
    row.attrs["curve_date"] = str(pd.Timestamp(curve_ts).date())
    return row


def build_discount_curve(par_rates_pct) -> "DiscountCurve":
    """Bootstrap the annual discount curve from percent-quoted par-swap rates."""
    return bootstrap_discount_curve(par_rates_pct, percent=True, freq=1)


def max_curve_tenor(curve_or_rates) -> int:
    """Longest tenor available on the curve, in whole years."""
    if isinstance(curve_or_rates, DiscountCurve):
        return int(round(float(max(curve_or_rates.nodes))))
    return max(years_of_tenor(k) for k in pd.Series(curve_or_rates).index)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # tiny smoke test
    r = load_par_rates()
    print("par-swap rates (percent):")
    print(r.to_string())
    c = build_discount_curve(r)
    print(f"\nmax tenor : {max_curve_tenor(c)}y")
    for m in (2, 5, 7, 10):
        print(f"  {m:2d}y par swap rate from curve : "
              f"{c.forward_swap_rate(0, m) * 100:.4f} %")
