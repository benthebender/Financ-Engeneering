# Case 3b - Monte-Carlo 1-year 99% VaR  (full)

25,000 paths x 52 weekly steps. Weekly factor moves ~ multivariate Student-t (dof 5, shrunk correlation), compounded to 1 year, book repriced with the HS engine.

- Total assets EUR 10.00bn | liability PV EUR 6.81bn | economic surplus EUR 3.19bn
- Equity 99% 1y VaR limit (MC): EUR 315m  (6.9% of equity MV)
- Unhedged equity 99% 1y VaR (MC): EUR 1,134m  ->  applied futures short 72.2%

## MC VaR / ES  (1-year, EUR)

| model | Asset VaR | Asset ES | Surplus VaR | Surplus ES |
|---|--:|--:|--:|--:|
| student_t_nu5 | 2,405.1m | 2,533.8m | 1,708.8m | 1,826.2m |
| gaussian | 2,408.7m | 2,536.2m | 1,697.1m | 1,817.5m |

## Method notes

- Student-t (dof 5) gives ~3x the excess kurtosis of a normal and non-zero tail dependence; `gaussian` (dof inf) is the copula-normal / parametric reference.
- Correlation is shrunk 10% toward the mean pairwise correlation (Ledoit-Wolf style) and repaired to the nearest PD matrix.
- Rates simulated as absolute weekly changes, indices as log returns; 1-year move = sum of 52 simulated weeks (no iid-normal sqrt-time scaling).
- Same book, liability and overlay as the HS run in `case3_var.py`; compare the two headline numbers there.
