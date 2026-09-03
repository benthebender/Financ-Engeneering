# Case 3b - Historical-Simulation 1-year 100% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 11 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.00bn  (equity EUR 4.60bn)
- Receive-fixed IRS overlay (par, notional not exchanged, no cash): 15y EUR 2.8bn @ 3.08%, 30y EUR 0.3bn @ 3.18%
- Total assets EUR 10.00bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.47

## Risk-control overlay

- Economic surplus EUR 3.19bn; funding-ratio floor 1.20 => max 1y asset loss EUR 1.83bn
- less non-equity surplus VaR EUR 516m => **equity 99% 1y VaR limit EUR 1,063m** (23.1% of equity MV; binding: surplus-at-risk cap)
- unhedged equity 99% 1y VaR EUR 998m -> pinned at 0% (rule -> 0.0%)
- applied futures short 0.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 3,587.2m | 3,701.9m | 2,864.8m | 1,431.1m | 3,825.0m |
| **Surplus** | 937.1m | 1,066.7m | 1,355.5m | 856.6m | 1,175.7m |

Asset VaR 35.9% of assets | Surplus VaR 13.8% of liability

## Standalone 100% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 3,019.3m |
| fi_bonds | 1,583.5m |
| irs_hedge | 1,008.4m |
| equity | 997.8m |
| fx_hedge_residual | 200.6m |
| rates_credit_idx | 40.3m |
| high_yield | 28.0m |
| futures_overlay | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -1,054.1m | -1,218.5m | 164.5m |
| EUR rates +200bp parallel | -1,890.0m | -2,197.5m | 307.5m |
| EUR rates -100bp parallel | 1,282.1m | 1,527.5m | -245.4m |
| Equity -20% | -940.0m | 0.0m | -940.0m |
| Equity -30% | -1,410.0m | 0.0m | -1,410.0m |
| Equity -40% | -1,880.0m | 0.0m | -1,880.0m |
| HY spread +300bp (~-12%) | -31.2m | 0.0m | -31.2m |
| 2022 replay: rates +250bp, equity -20% | -3,168.8m | -2,614.0m | -554.7m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -167.6m | 2,435.0m | -2,602.7m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
