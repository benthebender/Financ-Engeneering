"""
pricer.py
=========

Par-coupon solver for callable bonds, fully parameterised - nothing is
hardcoded to 7y NC2.

The engine takes a structure description (:class:`CallableSpec`), a bootstrapped
discount curve, a volatility and an option engine, and returns the coupon that
makes the bond price at par (100 per 100 face).

Structure knobs
---------------
    maturity   : int years, must be <= the curve's longest tenor
    nc_period  : int years, first date the issuer may call (nc=2 -> earliest t=2)
    call_type  : "single" | "bermudan"
    call_price : float, default 100.0 (a callable ``year -> price`` is accepted
                 by the engine for 101 / step-down schedules; pass it via
                 ``call_price=`` on the functions below)
    call_schedule : explicit list of call years - the escape hatch. When set it
                 *overrides* nc_period/call_type and is treated as a Bermudan
                 over exactly those years (``[5]`` == a one-off single call,
                 ``[3, 5, 7]`` == an irregular schedule).

Derived, never passed in
------------------------
    single-call candidates = range(nc_period, maturity)
    bermudan schedule      = the same set, all exercisable

For ``call_type="single"`` the solver prices *every* candidate date and returns
the one with the highest par coupon, together with the full ladder. The
earliest date wins on an upward-sloping curve but not on a flat or inverted one,
so the ladder is the interesting output.

Public API
----------
    par_coupon(curve, vols, spec, engine="hw", **engine_kw) -> ParCouponResult
    call_ladder(curve, vols, spec, engine="hw", **engine_kw) -> pd.DataFrame
    compare_structures(curve, vols, specs, engine="hw", **engine_kw) -> pd.DataFrame
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from engine import bullet_par_coupon, build_engine

__all__ = [
    "CallableSpec",
    "ParCouponResult",
    "par_coupon",
    "call_ladder",
    "compare_structures",
    "validate_against_curve",
]


# --------------------------------------------------------------------------- #
# structure description
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CallableSpec:
    maturity: int
    nc_period: int
    call_type: Literal["single", "bermudan"]
    call_price: float = 100.0
    call_schedule: "tuple[int, ...] | None" = None  # explicit override

    def __post_init__(self) -> None:
        if not isinstance(self.maturity, int) or isinstance(self.maturity, bool):
            raise TypeError(f"maturity must be an int, got {self.maturity!r}")
        if self.maturity < 2:
            raise ValueError(f"maturity must be >= 2 years, got {self.maturity}")

        if not isinstance(self.nc_period, int) or isinstance(self.nc_period, bool):
            raise TypeError(f"nc_period must be an int, got {self.nc_period!r}")
        if not (1 <= self.nc_period < self.maturity):
            raise ValueError(
                f"nc_period must satisfy 1 <= nc_period < maturity "
                f"(maturity={self.maturity}); got {self.nc_period}"
            )

        if self.call_type not in ("single", "bermudan"):
            raise ValueError(
                f"call_type must be 'single' or 'bermudan', got {self.call_type!r}"
            )
        if not (self.call_price > 0):
            raise ValueError(f"call_price must be > 0, got {self.call_price}")

        if self.call_schedule is not None:
            sched = list(self.call_schedule)
            if not sched:
                raise ValueError("call_schedule, when given, must be non-empty")
            for x in sched:
                if not isinstance(x, int) or isinstance(x, bool):
                    raise TypeError(f"call_schedule entries must be ints, got {x!r}")
                if not (0 < x < self.maturity):
                    raise ValueError(
                        f"call_schedule entries must be strictly inside "
                        f"(0, {self.maturity}); got {sched}"
                    )
            if len(set(sched)) != len(sched):
                raise ValueError(f"call_schedule has duplicates: {sched}")
            object.__setattr__(self, "call_schedule", tuple(sorted(sched)))

    # -- derived views -------------------------------------------------- #
    @property
    def is_single(self) -> bool:
        """A ladder-style single call (no explicit schedule, call_type single)."""
        return self.call_schedule is None and self.call_type == "single"

    def candidate_dates(self) -> tuple[int, ...]:
        """Every call date to price on its own for the ladder."""
        if self.call_schedule is not None:
            return tuple(self.call_schedule)
        return tuple(range(self.nc_period, self.maturity))

    def exercise_set(self) -> set[int]:
        """All years simultaneously exercisable (Bermudan / explicit schedule)."""
        if self.call_schedule is not None:
            return set(self.call_schedule)
        if self.call_type == "bermudan":
            return set(range(self.nc_period, self.maturity))
        raise ValueError("exercise_set() is not defined for a ladder 'single' spec")

    def label(self) -> str:
        if self.call_schedule is not None:
            return f"{self.maturity}y call{list(self.call_schedule)}"
        tag = "NC" if self.call_type == "single" else "NCbrm"
        return f"{self.maturity}y {tag}{self.nc_period}"


# --------------------------------------------------------------------------- #
# result container
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ParCouponResult:
    spec: CallableSpec
    par_coupon: float                  # decimal
    price: float                       # solver check, should be ~100
    bullet_par_coupon: float           # decimal
    spread_over_bullet: float          # decimal (par_coupon - bullet)
    n_exercise_dates: int
    best_call_year: "int | None"       # single only
    call_ladder: "pd.DataFrame | None"
    engine_info: dict = field(default_factory=dict)

    @property
    def spread_bp(self) -> float:
        return self.spread_over_bullet * 1e4

    def as_row(self) -> dict:
        return {
            "structure": self.spec.label(),
            "maturity": self.spec.maturity,
            "nc_period": self.spec.nc_period,
            "call_type": self.spec.call_type,
            "n_call_dates": self.n_exercise_dates,
            "par_coupon_bp": self.par_coupon * 1e4,
            "bullet_bp": self.bullet_par_coupon * 1e4,
            "spread_bp": self.spread_bp,
            "best_call_year": self.best_call_year,
            "price_check": self.price,
        }

    def summary(self) -> str:
        lines = [
            f"{self.spec.label()}",
            f"  bullet par coupon   : {self.bullet_par_coupon * 100:.4f} %",
            f"  callable par coupon : {self.par_coupon * 100:.4f} %",
            f"  spread over bullet  : {self.spread_bp:+.1f} bp",
            f"  call dates priced   : {self.n_exercise_dates}"
            + (f"  (best single = year {self.best_call_year})"
               if self.best_call_year is not None else ""),
            f"  price check         : {self.price:.6f}",
        ]
        if self.call_ladder is not None:
            lines.append("  ladder (par coupon by single call year):")
            for yr, row in self.call_ladder.iterrows():
                lines.append(
                    f"    call {yr:>2}y : {row['par_coupon'] * 100:7.4f} %"
                    f"   ({row['spread_bp']:+6.1f} bp vs bullet)"
                )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# validation that needs the curve
# --------------------------------------------------------------------------- #
def validate_against_curve(spec: CallableSpec, curve) -> None:
    max_tenor = int(round(float(max(curve.nodes))))
    if spec.maturity > max_tenor:
        raise ValueError(
            f"maturity {spec.maturity}y exceeds the curve's longest tenor "
            f"{max_tenor}y - refusing to extrapolate the curve to price the bond"
        )
    if spec.maturity == max_tenor:
        warnings.warn(
            f"maturity ({spec.maturity}y) equals the curve's longest tenor: the "
            f"final forward is built from a single unhedged curve point",
            stacklevel=2,
        )


def _resolve_vol(vols, maturity: int) -> float:
    if isinstance(vols, (int, float)):
        return float(vols)
    s = pd.Series(vols)
    for key in (maturity, f"{maturity}Y", f"{maturity}y", str(maturity)):
        if key in s.index:
            return float(s.loc[key])
    # fall back to interpolation on numeric tenors
    num = {}
    for k, v in s.items():
        try:
            num[float(str(k).rstrip("Yy"))] = float(v)
        except ValueError:
            continue
    if not num:
        raise ValueError(f"could not resolve a vol for maturity {maturity} from {vols!r}")
    xs = sorted(num)
    import numpy as np
    return float(np.interp(maturity, xs, [num[x] for x in xs]))


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def _ladder_df(eng, candidate_dates, call_price, bullet) -> pd.DataFrame:
    rows = []
    for d in candidate_dates:
        c, chk = eng.par_coupon({d}, call_price)
        rows.append({
            "call_year": int(d),
            "par_coupon": c,
            "par_coupon_bp": c * 1e4,
            "bullet_bp": bullet * 1e4,
            "spread_bp": (c - bullet) * 1e4,
            "price_check": chk,
        })
    return pd.DataFrame(rows).set_index("call_year")


def _engine_for(curve, vols, spec, engine, engine_kw):
    validate_against_curve(spec, curve)
    vol = _resolve_vol(vols, spec.maturity)
    return build_engine(engine, curve=curve, maturity=spec.maturity, vol=vol,
                        **engine_kw)


def call_ladder(curve, vols, spec: CallableSpec, engine="hw", **engine_kw) -> pd.DataFrame:
    """Par coupon of a single call at each candidate date, as a DataFrame.

    Works for any spec: an explicit ``call_schedule`` is laddered entry by entry,
    otherwise ``range(nc_period, maturity)`` is used.
    """
    eng = _engine_for(curve, vols, spec, engine, engine_kw)
    bullet = eng.bullet_par_coupon()
    return _ladder_df(eng, spec.candidate_dates(), spec.call_price, bullet)


def par_coupon(curve, vols, spec: CallableSpec, engine="hw", **engine_kw) -> ParCouponResult:
    """Solve for the par coupon of the structure in ``spec``.

    ``call_type="single"`` -> price every candidate date, return the highest par
    coupon plus the ladder. ``call_type="bermudan"`` (or an explicit
    ``call_schedule``) -> one solve over the whole exercise set.
    """
    eng = _engine_for(curve, vols, spec, engine, engine_kw)
    bullet = eng.bullet_par_coupon()

    if spec.is_single:
        ladder = _ladder_df(eng, spec.candidate_dates(), spec.call_price, bullet)
        best_year = int(ladder["par_coupon"].idxmax())
        c = float(ladder.loc[best_year, "par_coupon"])
        chk = float(ladder.loc[best_year, "price_check"])
        return ParCouponResult(
            spec=spec, par_coupon=c, price=chk, bullet_par_coupon=bullet,
            spread_over_bullet=c - bullet, n_exercise_dates=1,
            best_call_year=best_year, call_ladder=ladder, engine_info=eng.info,
        )

    ex = sorted(spec.exercise_set())
    c, chk = eng.par_coupon(set(ex), spec.call_price)
    return ParCouponResult(
        spec=spec, par_coupon=c, price=chk, bullet_par_coupon=bullet,
        spread_over_bullet=c - bullet, n_exercise_dates=len(ex),
        best_call_year=None, call_ladder=None, engine_info=eng.info,
    )


def compare_structures(curve, vols, specs, engine="hw", **engine_kw) -> pd.DataFrame:
    """One row per spec: par coupon, bullet, spread, best single-call year."""
    rows = [par_coupon(curve, vols, s, engine, **engine_kw).as_row() for s in specs]
    return pd.DataFrame(rows)
