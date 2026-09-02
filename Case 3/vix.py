"""
vix.py
======

VIX-Bewertung fuer die Monte-Carlo-Simulation der Case-3b-Aktienseite.

Definition
    VIX_t^2 = (1/tau) * E^Q[ integral_t^{t+tau} v_s ds | F_t ] * 100^2 ,  tau = 30/365

Heston-Varianzprozess
    dv_t = kappa (theta - v_t) dt + xi sqrt(v_t) dW_t^v
    d<W^S, W^v>_t = rho dt      (Leverage, rho ~ -0.7 .. -0.8)

Da unter Heston  E^Q[v_s | F_t] = theta + (v_t - theta) e^{-kappa (s-t)} , folgt
*exakt* (keine Naeherung im Modell):

    VIX_t^2 = ( A(tau) v_t + (1 - A(tau)) theta ) * 100^2
    A(tau)  = (1 - e^{-kappa tau}) / (kappa tau)          "term-structure weight"

v_t und theta sind **annualisierte** Varianzen (dezimal^2, z. B. theta = 0.04 fuer
20% Vola). VIX_t kommt in Punkten heraus (z. B. 18).

Der Leverage-Effekt ist zwingend: nur wenn der Marktschock W^S und der
Varianzschock W^v mit rho < 0 gekoppelt sind, schiesst v_t (und damit VIX_t) beim
Crash nach oben - sonst feuert der VIX-Trigger nie im Gleichtakt mit dem
Portfolio-Drawdown.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TAU = 30.0 / 365.0

__all__ = ["HestonVIX", "term_weight"]


def term_weight(kappa: float, tau: float = TAU) -> float:
    """A(tau) = (1 - e^{-kappa tau}) / (kappa tau)."""
    x = kappa * tau
    return (1.0 - np.exp(-x)) / x


@dataclass(frozen=True)
class HestonVIX:
    """Heston stochastic-volatility model for a broad equity 'market' variance,
    with the analytic VIX map.

    kappa : mean-reversion speed of variance (per year), ~2 .. 5
    theta : long-run annualised variance (decimal^2), e.g. 0.028 for ~16.7% vol
    xi    : vol-of-vol (per year), ~0.4 .. 0.8 (higher -> fatter VIX tail)
    rho   : leverage correlation between the equity return shock and dW^v, ~ -0.75
    v0    : current annualised variance (decimal^2); default theta

    Defaults are calibrated so that (i) calm-regime VIX sits mid-teens, (ii) the
    worst ~1% of simulated years see VIX spike past 50 at the crash week -
    consistent with Aug-2015 / Feb-2018 / Mar-2020 / 2022.  Feller (2 kappa
    theta >= xi^2) is intentionally violated; the full-truncation Euler keeps
    v >= 0.
    """

    kappa: float = 4.0
    theta: float = 0.028
    xi: float = 0.65
    rho: float = -0.75
    v0: float | None = 0.018        # ~13.4% vol - a calm starting regime

    @property
    def feller_ok(self) -> bool:
        return 2.0 * self.kappa * self.theta >= self.xi ** 2

    def vix(self, v: np.ndarray | float) -> np.ndarray | float:
        """VIX (points) from the instantaneous annualised variance v_t."""
        A = term_weight(self.kappa)
        return 100.0 * np.sqrt(A * np.asarray(v, dtype=float) + (1.0 - A) * self.theta)

    # -- path simulation ------------------------------------------------- #
    def simulate_paths(
        self,
        equity_market_shock: np.ndarray,   # (n_paths, n_steps), ~ standard normal
        dt: float,
        rng: np.random.Generator,
    ) -> dict:
        """Weekly full-truncation Euler for v_t, driven by the given equity
        market shocks via the leverage correlation.

        Returns
            v     : (n_paths, n_steps+1) annualised variance path
            vix   : (n_paths, n_steps+1) VIX points
            vol_mult : (n_paths, n_steps) instantaneous-to-long-run vol ratio
                       sqrt(v_t / theta) - multiply the equity weekly returns
                       by this so realised equity vol tracks the regime.
        """
        z_mkt = np.asarray(equity_market_shock, dtype=float)
        n_paths, n_steps = z_mkt.shape
        z_perp = rng.standard_normal((n_paths, n_steps))
        dWv = self.rho * z_mkt + np.sqrt(1.0 - self.rho ** 2) * z_perp

        v0 = self.theta if self.v0 is None else self.v0
        v = np.empty((n_paths, n_steps + 1))
        v[:, 0] = v0
        sdt = np.sqrt(dt)
        for w in range(n_steps):
            vt = v[:, w]
            vpos = np.maximum(vt, 0.0)
            v[:, w + 1] = np.maximum(
                vt + self.kappa * (self.theta - vpos) * dt
                + self.xi * np.sqrt(vpos) * sdt * dWv[:, w],
                0.0,
            )
        vix = self.vix(v)
        vol_mult = np.sqrt(np.maximum(v[:, :n_steps], 0.0) / self.theta)
        return {"v": v, "vix": vix, "vol_mult": vol_mult}


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    m = HestonVIX(kappa=3.0, theta=0.028, xi=0.40, rho=-0.75)
    A = term_weight(m.kappa)
    print(f"A(tau) = {A:.4f}   B(tau) = {1 - A:.4f}   Feller ok: {m.feller_ok}")
    for vol in (0.12, 0.167, 0.25, 0.40, 0.55):
        print(f"  inst. vol {vol:5.0%}  ->  v_t = {vol**2:.4f}  ->  VIX = {m.vix(vol**2):5.1f}")

    rng = np.random.default_rng(0)
    # a stylised crash: 8 calm weeks then a -4 sigma market week
    shock = np.zeros((1, 12)); shock[0, 8] = -4.0
    out = m.simulate_paths(shock, dt=1 / 52, rng=rng)
    print("\n VIX path around a -4 sigma equity week:")
    print("  ", np.round(out["vix"][0], 1))
