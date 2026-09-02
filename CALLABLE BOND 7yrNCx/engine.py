"""
engine.py
=========

Option-pricing engines for the callable-bond par-coupon search.

Two engines, one interface
--------------------------
``HullWhiteEngine``  - Hull-White one-factor short-rate model on a fitted
                       trinomial tree (Hull's two-stage construction). Prices
                       *any* exercise set (single date or full Bermudan) by
                       backward induction, so single-call and Bermudan numbers
                       come from the same lattice and stay consistent.

``BlackEngine``      - closed-form European (single-call only) cross-check:
                       callable = straight bond - receiver swaption, receiver
                       swaption by Black's lognormal formula on the forward
                       swap rate. Raises for multi-date exercise.

Both are *bound to one (curve, maturity)*: the lattice depends only on the
curve, the model and the horizon - never on the coupon - so it is built once
and reused across every candidate call date and every root-finder step.

Interface (duck-typed, used by ``pricer.py``)
--------------------------------------------
    eng.bullet_par_coupon() -> float                       # decimal
    eng.par_coupon(exercise_years, call_price) -> (coupon, price_check)
    eng.price(coupon, exercise_years, call_price) -> float # per 100 face
    eng.info -> dict

``exercise_years`` is a set/iterable of integer years on which the issuer may
call (empty / ``None`` -> a plain bullet). ``call_price`` is a float or a
callable ``year -> price`` (step-down schedules). Coupons are annual; the
schedule is a list so semi-annual is a later change of schedule, not of maths.

Conventions
-----------
* Face value 100. Coupon and rates are decimals (0.031 == 3.1 %).
* Curve is a bootstrapped ``DiscountCurve`` (annual nodes, log-linear DF
  interpolation) from ``forward_swap.py``.
* Hull-White vol input is a **Black (lognormal) implied vol** by default; it is
  mapped to the model's absolute short-rate vol via the at-the-money
  normal<->lognormal identity ``sigma_abs ~= vol_black * r_ref`` with
  ``r_ref`` = the maturity-year par swap rate. Pass ``vol_type="normal"`` to
  feed an absolute short-rate vol directly, or ``sigma_abs=`` to pin it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

FACE = 100.0
COUPON_FREQ = 1  # annual only for now (schedule is a list, so this is not baked in)


# --------------------------------------------------------------------------- #
# coupon schedule
# --------------------------------------------------------------------------- #
def coupon_schedule(maturity: int, freq: int = COUPON_FREQ) -> list[tuple[float, float]]:
    """List of ``(payment_time_years, accrual_fraction)`` for the fixed leg.

    Annual, 30/360 -> one payment a year, accrual 1.0. Kept as an explicit list
    so a semi-annual bond is a different schedule, not a rewrite of the pricer.
    """
    if freq != 1:
        raise NotImplementedError(
            "only annual coupons are wired up for now; extend coupon_schedule() "
            "and make sure every call year still lands on a coupon date"
        )
    tau = 1.0 / freq
    n = int(round(maturity * freq))
    return [((k + 1) * tau, tau) for k in range(n)]


# --------------------------------------------------------------------------- #
# analytic bullet par coupon (curve-exact, no model)
# --------------------------------------------------------------------------- #
def bullet_par_coupon(curve, maturity: int, freq: int = COUPON_FREQ) -> float:
    """Par coupon of the non-callable bond = the maturity-year par swap rate."""
    sched = coupon_schedule(maturity, freq)
    annuity = sum(tau * curve.df(t) for t, tau in sched)
    return (1.0 - curve.df(float(maturity))) / annuity


# --------------------------------------------------------------------------- #
# Hull-White trinomial tree
# --------------------------------------------------------------------------- #
@dataclass
class HullWhiteEngine:
    curve: object
    maturity: int
    vol: float = 0.15
    mean_reversion: float = 0.03
    steps_per_year: int = 12
    vol_type: str = "black"          # "black" (lognormal, scaled) | "normal"
    sigma_abs: "float | None" = None  # explicit absolute short-rate vol override
    freq: int = COUPON_FREQ

    # filled in by _build_tree
    _dt: float = field(init=False, repr=False)
    _N: int = field(init=False, repr=False)
    _dx: float = field(init=False, repr=False)
    _j: np.ndarray = field(init=False, repr=False)
    _pu: np.ndarray = field(init=False, repr=False)
    _pm: np.ndarray = field(init=False, repr=False)
    _pd: np.ndarray = field(init=False, repr=False)
    _up: np.ndarray = field(init=False, repr=False)
    _mid: np.ndarray = field(init=False, repr=False)
    _dn: np.ndarray = field(init=False, repr=False)
    _alpha: np.ndarray = field(init=False, repr=False)
    _j0: int = field(init=False, repr=False)
    _sigma: float = field(init=False, repr=False)
    _r_ref: float = field(init=False, repr=False)
    fit_error: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        a = float(self.mean_reversion)
        if a <= 0:
            raise ValueError(f"mean_reversion must be > 0 (got {a}); a=0 makes the "
                             "tree width unbounded")
        if self.steps_per_year < 1:
            raise ValueError("steps_per_year must be >= 1")
        if self.maturity * self.steps_per_year < 2:
            raise ValueError("maturity * steps_per_year must be >= 2")

        self._r_ref = float(self.curve.forward_swap_rate(0, int(self.maturity)))
        if self.sigma_abs is not None:
            self._sigma = float(self.sigma_abs)
        elif self.vol_type == "black":
            # ATM normal<->lognormal vol identity: sigma_N ~= sigma_LN * F
            self._sigma = float(self.vol) * abs(self._r_ref)
        elif self.vol_type == "normal":
            self._sigma = float(self.vol)
        else:
            raise ValueError("vol_type must be 'black' or 'normal'")
        if self._sigma <= 0:
            raise ValueError(f"resolved short-rate vol must be > 0 (got {self._sigma})")
        if self.vol_type == "black" and self._sigma < 1e-4:
            import warnings
            warnings.warn(
                f"resolved short-rate vol is tiny (sigma_abs={self._sigma:.2e}) "
                f"because r_ref={self._r_ref:.4%} is near zero; on a low/negative "
                f"rate curve pass an absolute vol with vol_type='normal' or "
                f"sigma_abs=",
                stacklevel=2,
            )

        self._build_tree(a)

    # -- stage 1 + stage 2 ------------------------------------------------- #
    def _build_tree(self, a: float) -> None:
        dt = 1.0 / self.steps_per_year
        N = int(round(self.maturity * self.steps_per_year))
        sigma = self._sigma
        dx = sigma * math.sqrt(3.0 * dt)
        M = -a * dt
        j_max = int(math.ceil(0.184 / (a * dt)))
        j_max = max(j_max, 1)

        j = np.arange(-j_max, j_max + 1, dtype=float)
        width = j.size
        jM = j * M
        j2M2 = (j * M) ** 2

        pu = np.empty(width); pm = np.empty(width); pd_ = np.empty(width)
        interior = np.abs(j) < j_max
        top = j == j_max
        bot = j == -j_max

        pu[interior] = 1 / 6 + (j2M2[interior] + jM[interior]) / 2
        pm[interior] = 2 / 3 - j2M2[interior]
        pd_[interior] = 1 / 6 + (j2M2[interior] - jM[interior]) / 2

        pu[top] = 7 / 6 + (j2M2[top] + 3 * jM[top]) / 2
        pm[top] = -1 / 3 - j2M2[top] - 2 * jM[top]
        pd_[top] = 1 / 6 + (j2M2[top] + jM[top]) / 2

        pu[bot] = 1 / 6 + (j2M2[bot] - jM[bot]) / 2
        pm[bot] = -1 / 3 - j2M2[bot] + 2 * jM[bot]
        pd_[bot] = 7 / 6 + (j2M2[bot] - 3 * jM[bot]) / 2

        idx = np.arange(width)
        up = idx + 1
        mid = idx.copy()
        dn = idx - 1
        up[-1], mid[-1], dn[-1] = idx[-1], idx[-1] - 1, idx[-1] - 2       # top edge
        up[0], mid[0], dn[0] = 2, 1, 0                                    # bottom edge

        # stage 2: shift the tree by alpha_i so it reprices the curve
        alpha = np.zeros(N)
        Q = np.zeros((N, width))
        j0 = j_max
        Q[0, j0] = 1.0
        disc_j = np.exp(-j * dx * dt)
        for i in range(N):
            s = float(Q[i] @ disc_j)
            P_i1 = float(self.curve.df((i + 1) * dt))
            alpha[i] = (math.log(s) - math.log(P_i1)) / dt
            if i < N - 1:
                w = Q[i] * np.exp(-(alpha[i] + j * dx) * dt)
                np.add.at(Q[i + 1], up, w * pu)
                np.add.at(Q[i + 1], mid, w * pm)
                np.add.at(Q[i + 1], dn, w * pd_)

        # fit diagnostic: sum_j Q[k,j] should equal P(0, k*dt)
        fit = 0.0
        for k in range(1, N):
            fit = max(fit, abs(float(Q[k].sum()) - float(self.curve.df(k * dt))))

        self._dt, self._N, self._dx = dt, N, dx
        self._j, self._pu, self._pm, self._pd = j, pu, pm, pd_
        self._up, self._mid, self._dn = up, mid, dn
        self._alpha, self._j0 = alpha, j0
        self.fit_error = fit

    # -- pricing --------------------------------------------------------- #
    def price(self, coupon: float, exercise_years=None, call_price: float = 100.0) -> float:
        """Value per ``FACE`` of the (optionally callable) bond at t=0."""
        dt, N, dx = self._dt, self._N, self._dx
        alpha, jvec = self._alpha, self._j
        pu, pm, pd_ = self._pu, self._pm, self._pd
        up, mid, dn = self._up, self._mid, self._dn
        spy = self.steps_per_year

        _, tau = coupon_schedule(self.maturity, self.freq)[0]
        cpn_cash = coupon * FACE * tau
        ex = set() if not exercise_years else {int(y) for y in exercise_years}
        cp_fn = call_price if callable(call_price) else (lambda _y: float(call_price))

        # terminal layer: final coupon + redemption at par
        V = np.full(jvec.size, FACE + cpn_cash)
        for i in range(N - 1, 0, -1):
            disc = np.exp(-(alpha[i] + jvec * dx) * dt)
            cont = disc * (pu * V[up] + pm * V[mid] + pd_ * V[dn])
            on_coupon = (i % spy) == 0
            cf = cpn_cash if on_coupon else 0.0
            if on_coupon and (i // spy) in ex:
                V = cf + np.minimum(cp_fn(i // spy), cont)  # issuer caps holder value
            else:
                V = cf + cont

        disc0 = math.exp(-alpha[0] * dt)
        j0 = self._j0
        return disc0 * (pu[j0] * V[up[j0]] + pm[j0] * V[mid[j0]] + pd_[j0] * V[dn[j0]])

    def par_coupon(self, exercise_years=None, call_price: float = 100.0):
        f = lambda c: self.price(c, exercise_years, call_price) - FACE
        # start wide enough for negative-rate curves, then expand if needed
        lo, hi = -0.05, 0.75
        flo, fhi = f(lo), f(hi)
        for _ in range(8):
            if flo <= 0:
                break
            lo -= 0.05
            flo = f(lo)
        for _ in range(8):
            if fhi >= 0:
                break
            hi += 0.5
            fhi = f(hi)
        if flo > 0 or fhi < 0:
            raise RuntimeError(
                f"par coupon not bracketed in ({lo:.3f}, {hi:.3f}); "
                f"f(lo)={flo:.4g}, f(hi)={fhi:.4g}"
            )
        c = brentq(f, lo, hi, xtol=1e-12, rtol=1e-14, maxiter=200)
        return float(c), float(self.price(c, exercise_years, call_price))

    def bullet_par_coupon(self) -> float:
        return bullet_par_coupon(self.curve, self.maturity, self.freq)

    def straight_price(self, coupon: float) -> float:
        """Value per ``FACE`` of the *non-callable* bond with this coupon."""
        sched = coupon_schedule(self.maturity, self.freq)
        ann = sum(tau * self.curve.df(t) for t, tau in sched)
        return coupon * FACE * ann + FACE * self.curve.df(float(self.maturity))

    def call_value(self, coupon: float, exercise_years=None,
                   call_price: float = 100.0) -> float:
        """Value of the issuer's embedded call = straight - callable (>= 0)."""
        return self.straight_price(coupon) - self.price(coupon, exercise_years,
                                                        call_price)

    @property
    def info(self) -> dict:
        return {
            "engine": "hull-white-1f-trinomial",
            "mean_reversion": self.mean_reversion,
            "vol_input": self.vol,
            "vol_type": self.vol_type,
            "sigma_abs": self._sigma,
            "r_ref": self._r_ref,
            "steps_per_year": self.steps_per_year,
            "n_steps": self._N,
            "tree_half_width": self._j0,
            "curve_fit_error": self.fit_error,
        }


# --------------------------------------------------------------------------- #
# Black closed-form European cross-check (single call only)
# --------------------------------------------------------------------------- #
@dataclass
class BlackEngine:
    curve: object
    maturity: int
    vol: float = 0.15          # lognormal swap-rate vol, used as-is
    freq: int = COUPON_FREQ

    def _annuity(self, start: float, end: float) -> float:
        n = int(round(end - start))
        return sum(self.curve.df(start + k) for k in range(1, n + 1))

    def bullet_par_coupon(self) -> float:
        return bullet_par_coupon(self.curve, self.maturity, self.freq)

    def price(self, coupon: float, exercise_years=None, call_price: float = 100.0) -> float:
        ex = sorted({int(y) for y in exercise_years}) if exercise_years else []
        straight = (
            coupon * FACE * self._annuity(0.0, float(self.maturity))
            + FACE * self.curve.df(float(self.maturity))
        )
        if not ex:
            return straight
        if len(ex) > 1:
            raise NotImplementedError(
                "BlackEngine prices single-call (European) structures only; use "
                "the Hull-White engine for Bermudan schedules"
            )
        if abs(call_price - 100.0) > 1e-12:
            raise NotImplementedError("BlackEngine assumes a par (100) call price")
        tc = float(ex[0])
        ann = self._annuity(tc, float(self.maturity))
        fwd = (self.curve.df(tc) - self.curve.df(float(self.maturity))) / ann
        if fwd <= 0 or coupon <= 0:
            raise NotImplementedError(
                "BlackEngine uses a lognormal swap rate and cannot handle a "
                f"non-positive forward ({fwd:.4%}) or coupon ({coupon:.4%}); "
                "use the Hull-White engine for negative-rate curves"
            )
        vol = float(self.vol)
        std = vol * math.sqrt(tc)
        # issuer's call ~ receiver swaption, strike = coupon, on fwd swap rate
        d1 = (math.log(fwd / coupon) + 0.5 * std * std) / std
        d2 = d1 - std
        recv_swaption = ann * FACE * (coupon * norm.cdf(-d2) - fwd * norm.cdf(-d1))
        return straight - recv_swaption

    def par_coupon(self, exercise_years=None, call_price: float = 100.0):
        f = lambda c: self.price(c, exercise_years, call_price) - FACE
        c = brentq(f, 1e-8, 1.0, xtol=1e-12, rtol=1e-14, maxiter=200)
        return float(c), float(self.price(c, exercise_years, call_price))

    @property
    def info(self) -> dict:
        return {"engine": "black-lognormal-european", "vol_input": self.vol,
                "freq": self.freq}


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #
def build_engine(engine, *, curve, maturity: int, vol: float = 0.15, **kw):
    """``engine`` may be an already-built engine object or a name ('hw'/'black')."""
    if not isinstance(engine, str):
        return engine
    name = engine.lower()
    if name in ("hw", "hull-white", "hullwhite"):
        allowed = {"mean_reversion", "steps_per_year", "vol_type", "sigma_abs", "freq"}
        return HullWhiteEngine(curve=curve, maturity=int(maturity), vol=vol,
                               **{k: v for k, v in kw.items() if k in allowed})
    if name == "black":
        return BlackEngine(curve=curve, maturity=int(maturity), vol=vol,
                           **{k: v for k, v in kw.items() if k == "freq"})
    raise ValueError(f"unknown engine {engine!r}; expected 'hw' or 'black'")
