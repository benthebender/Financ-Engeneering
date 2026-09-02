# Case 3b - Monte-Carlo 1-year 99% VaR  (full)

25,000 paths x 52 weekly steps. Weekly factor moves ~ multivariate Student-t (dof 5, shrunk correlation), compounded to 1 year, book repriced with the HS engine.

- Total assets EUR 10.00bn | liability PV EUR 6.81bn | economic surplus EUR 3.19bn
- Equity 99% 1y VaR limit (MC): EUR 316m  (6.9% of equity MV)
- Unhedged equity 99% 1y VaR (MC): EUR 1,441m  ->  applied futures short 78.1%

## MC VaR / ES  (1-year, EUR)

| model | Asset VaR | Asset ES | Surplus VaR | Surplus ES |
|---|--:|--:|--:|--:|
| student_t_nu5 | 2,412.9m | 2,564.3m | 1,707.6m | 1,836.3m |
| gaussian | 2,398.6m | 2,556.1m | 1,715.3m | 1,852.0m |

## VIX (Heston stochastic vol + leverage)

Market variance v_t: Heston, weekly full-truncation Euler, driven by the equity market shock via rho = -0.75 (leverage). VIX_t = 100 sqrt(A(tau) v_t + (1-A) theta), A(tau) = 0.886.

- median VIX (terminal / path-max): 13.6 / 27.5   (99th-pct path-max 50.6)
- corr(path-max VIX, 1y equity return): -0.44  (leverage works)
- VIX in the worst equity week - all paths vs the 99% equity tail: 23.8  vs  **42.3**
- share of 99%-tail paths with VIX > 40 / > 50 at the crash week: 61% / 19%

=> the VIX trigger fires in the same paths the portfolio crashes, so a VIX-gated no-trade band (widen in calm regimes, tighten / force the hedge when VIX spikes) is meaningful. Without stochastic vol the trigger would be uncorrelated with the drawdown.

## Method notes

- Student-t (dof 5) gives ~3x the excess kurtosis of a normal and non-zero tail dependence; `gaussian` (dof inf) is the copula-normal / parametric reference.
- Correlation is shrunk 10% toward the mean pairwise correlation (Ledoit-Wolf style) and repaired to the nearest PD matrix.
- Rates simulated as absolute weekly changes, indices as log returns; 1-year move = sum of 52 simulated weeks (no iid-normal sqrt-time scaling).
- Heston: kappa 3.0, theta 0.028 (~16.7% long-run vol), xi 0.40, rho -0.75; equity weekly returns scaled by sqrt(v_t/theta) so realised equity vol tracks the regime.
- Same book, liability and overlay as the HS run in `case3_var.py`; compare the two headline numbers there.
