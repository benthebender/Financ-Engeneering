"""
swap_curves.py
==============

Extract the EUR swap curves (1y - 10y) from ``Data/Swap curves.xlsx`` and expose
them as clean, ready-to-use pandas objects for the rest of the repository.

Quick start
-----------
    from swap_curves import swap_curves, swap_10y, load_swap_curves

    swap_curves        # DataFrame: DatetimeIndex x ["1Y", ... , "10Y"]  (percent)
    swap_10y           # Series:    10y history (percent), clean index
    load_swap_curves(as_decimal=True, dropna=True)        # custom load

Raw file layout (sheet "Sheet1", no usable header row)
-----------------------------------------------------
The workbook stores each tenor as its own self-dated block of columns:

    [weekday, date, rate, <spacer>, <spacer>]  repeated for 10y, 9y, ... , 1y

Row 0 carries the tenor label ("10yr", "9yr", ...) in each block's *rate*
column, so the loader locates every block by that label and reads the date from
the column immediately to its left.  Rates are quoted in percent
(e.g. ``3.3463`` == 3.3463 %).  Blank rows separate the weeks.

Because every tenor is dated independently, the curves are correctly aligned
over the full history (~2015-11 .. 2026-08).  The first few days only have the
short tenors populated (the other columns simply start a bit later); pass
``dropna=True`` if you need rows where every requested tenor is present.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
WORKBOOK_NAME = "Swap curves.xlsx"
SHEET_NAME = "Sheet1"

# Places to look for the workbook, relative to this module, so the loader keeps
# working whether it sits in the repo root or in the Data/ folder.
_HERE = Path(__file__).resolve().parent
_SEARCH_DIRS = (_HERE, _HERE / "Data", _HERE.parent / "Data", _HERE.parent)

_TENOR_RE = re.compile(r"^\s*(\d+)\s*yr\s*$", re.IGNORECASE)


def _find_workbook() -> Path:
    for d in _SEARCH_DIRS:
        candidate = d / WORKBOOK_NAME
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Could not find {WORKBOOK_NAME!r} in any of: "
        + ", ".join(str(d) for d in _SEARCH_DIRS)
    )


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #
def load_swap_curves(
    path: str | Path | None = None,
    *,
    tenors: "list[int] | None" = None,
    as_decimal: bool = False,
    dropna: bool = False,
) -> pd.DataFrame:
    """Load the swap curves from the Excel file.

    Parameters
    ----------
    path
        Location of ``Swap curves.xlsx``.  If omitted, the loader looks next to
        this module, in a sibling/child ``Data/`` folder, and one level up.
    tenors
        Which maturities (in years) to keep, e.g. ``[1, 2, 5, 10]``.
        ``None`` keeps every tenor found in the sheet (1..10).
    as_decimal
        If ``True`` divide the quotes by 100 (3.3463 -> 0.033463).  Default
        keeps the original percent quoting.
    dropna
        If ``True`` keep only dates on which *every* requested tenor has a
        quote.  Default keeps every observed date (short tenors have a slightly
        longer history, so the earliest rows carry NaNs for the long end).

    Returns
    -------
    pandas.DataFrame
        Index : ``DatetimeIndex`` named ``"date"``, sorted ascending, unique,
                no ``NaT``, no time-of-day component.
        Columns : ``"1Y", "2Y", ... , "10Y"`` (only the requested tenors),
                  ordered by maturity, dtype ``float64``.
    """
    path = Path(path) if path is not None else _find_workbook()
    if not path.exists():
        raise FileNotFoundError(f"Swap-curve workbook not found: {path}")

    raw = pd.read_excel(path, sheet_name=SHEET_NAME, header=None)

    # --- locate each tenor block via its "<n>yr" label in the first row ----
    #     rate column  = the labelled column
    #     date column  = the column immediately to its left
    rate_cols: dict[int, int] = {}
    for col, val in raw.iloc[0].items():
        if isinstance(val, str):
            m = _TENOR_RE.match(val)
            if m:
                rate_cols[int(m.group(1))] = col
    if not rate_cols:
        raise ValueError("Could not find any '<n>yr' tenor labels in row 0.")

    wanted = sorted(tenors) if tenors is not None else sorted(rate_cols)
    missing = [t for t in wanted if t not in rate_cols]
    if missing:
        raise ValueError(f"Tenors {missing} are not present in the sheet.")

    # --- read every (date, rate) block, then align on the date -------------
    blocks = []
    for t in wanted:
        rc = rate_cols[t]
        dates = pd.to_datetime(raw[rc - 1], errors="coerce").dt.normalize()
        rates = pd.to_numeric(raw[rc], errors="coerce")
        s = pd.Series(rates.to_numpy(), index=dates, name=f"{t}Y")
        s = s[s.index.notna() & s.notna()]
        s = s[~s.index.duplicated(keep="last")]
        blocks.append(s)

    out = pd.concat(blocks, axis=1).sort_index()
    out.index.name = "date"

    if dropna:
        out = out.dropna()

    if as_decimal:
        out = out / 100.0

    # sanity: strictly increasing, unique, complete DatetimeIndex
    assert out.index.is_monotonic_increasing
    assert out.index.is_unique
    assert out.index.notna().all()
    return out


# --------------------------------------------------------------------------- #
# Ready-made module-level variables
# --------------------------------------------------------------------------- #
#: Full swap-curve history, tenors 1Y..10Y, percent quoting, clean DatetimeIndex.
swap_curves: pd.DataFrame = load_swap_curves()

#: 10Y swap rate history (percent), clean DatetimeIndex.
swap_10y: pd.Series = swap_curves["10Y"].dropna().rename("10Y")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("swap_curves")
    print(f"  shape      : {swap_curves.shape}")
    print(f"  date range : {swap_curves.index.min().date()} -> "
          f"{swap_curves.index.max().date()}")
    print(f"  columns    : {list(swap_curves.columns)}")
    print(f"  index clean: monotonic={swap_curves.index.is_monotonic_increasing}, "
          f"unique={swap_curves.index.is_unique}, "
          f"any NaT={swap_curves.index.isna().any()}")
    print(f"  NaNs/col   : {swap_curves.isna().sum().to_dict()}")
    print()
    print(swap_curves.head())
    print("  ...")
    print(swap_curves.tail())
    print()
    print(f"swap_10y : {swap_10y.shape[0]} obs, "
          f"{swap_10y.index.min().date()} -> {swap_10y.index.max().date()}")
