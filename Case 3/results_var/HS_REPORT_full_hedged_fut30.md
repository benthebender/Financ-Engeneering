# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 11 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.00bn  (equity EUR 4.60bn)
- Receive-fixed IRS overlay (par, notional not exchanged, no cash): 15y EUR 2.8bn @ 3.08%, 30y EUR 0.3bn @ 3.18%
- Total assets EUR 10.00bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.47

## Risk-control overlay

- Economic surplus EUR 3.19bn; funding-ratio floor 1.20 => max 1y asset loss EUR 1.83bn
- less non-equity surplus VaR EUR 501m => **equity 99% 1y VaR limit EUR 1,063m** (23.1% of equity MV; binding: surplus-at-risk cap)
- unhedged equity 99% 1y VaR EUR 964m -> pinned at 30% (rule -> 0.0%)
- applied futures short 30.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 3,185.2m | 3,339.8m | 2,694.8m | 1,289.5m | 3,499.7m |
| **Surplus** | 734.7m | 807.0m | 1,105.1m | 680.3m | 883.3m |

Asset VaR 31.9% of assets | Surplus VaR 10.8% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,543.1m |
| irs_hedge | 976.6m |
| equity | 963.6m |
| futures_overlay | 659.5m |
| fx_hedge_residual | 187.1m |
| rates_credit_idx | 39.0m |
| high_yield | 26.7m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -1,054.1m | -1,218.5m | 164.5m |
| EUR rates +200bp parallel | -1,890.0m | -2,197.5m | 307.5m |
| EUR rates -100bp parallel | 1,282.1m | 1,527.5m | -245.4m |
| Equity -20% | -664.0m | 0.0m | -664.0m |
| Equity -30% | -996.0m | 0.0m | -996.0m |
| Equity -40% | -1,328.0m | 0.0m | -1,328.0m |
| HY spread +300bp (~-12%) | -31.2m | 0.0m | -31.2m |
| 2022 replay: rates +250bp, equity -20% | -2,892.8m | -2,614.0m | -278.7m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | 453.4m | 2,435.0m | -1,981.7m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
