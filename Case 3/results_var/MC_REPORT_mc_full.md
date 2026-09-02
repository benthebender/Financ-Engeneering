# Case 3b - Monte-Carlo 1-year 99% VaR  (full)

25,000 paths x 52 weekly Student-t (dof 5) steps, PCA curve, Heston stochastic vol + leverage. Book repriced with the HS engine.

- assets EUR 10.00bn | liability PV EUR 6.81bn | economic surplus EUR 3.19bn
- equity 99% 1y VaR limit EUR 316m | unhedged equity VaR EUR 1,441m -> hedge 78.1%

## MC VaR / ES (1-year, EUR)

| model | Asset VaR | Asset ES | Surplus VaR | Surplus ES |
|---|--:|--:|--:|--:|
| student_t_nu5 | 2,412.9m | 2,564.3m | 1,707.6m | 1,836.3m |
| gaussian | 2,398.6m | 2,556.1m | 1,715.3m | 1,852.0m |

## VIX (Heston kappa 4.0, theta 0.028, xi 0.65, rho -0.75)

VIX_t = 100 sqrt(A(tau) v_t + (1-A) theta), A(tau) = 0.852.

- median VIX terminal / path-max: 13.6 / 27.5  (99th-pct path-max 50.6)
- corr(path-max VIX, 1y equity return): -0.44
- VIX at the crash week: 23.8 (all) vs **42.3** (99% equity tail)
- share of 99%-tail paths with VIX > 40 / > 50 at the crash week: 61% / 19%

=> VIX spikes coincide with the crash paths -> a VIX-gated no-trade band (`vix_gated_band`) is meaningful.
