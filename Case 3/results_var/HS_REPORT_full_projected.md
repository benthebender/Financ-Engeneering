# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 11 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 8.39bn  (equity EUR 7.72bn)
- Total assets EUR 13.39bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.97

## Risk-control overlay

- Economic surplus EUR 6.58bn; funding-ratio floor 1.20 => max 1y asset loss EUR 5.21bn
- less non-equity surplus VaR EUR 975m => **equity 99% 1y VaR limit EUR 2,192m** (28.4% of equity MV; binding: surplus-at-risk cap)
- unhedged equity 99% 1y VaR EUR 1,616m -> pinned at 0% (rule -> 0.0%)
- applied futures short 0.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 3,224.6m | 3,396.7m | 2,920.9m | 1,668.8m | 3,618.2m |
| **Surplus** | 1,424.1m | 1,672.3m | 2,160.1m | 1,416.0m | 1,862.7m |

Asset VaR 24.1% of assets | Surplus VaR 20.9% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| equity | 1,616.4m |
| fi_bonds | 1,543.1m |
| fx_hedge_residual | 313.8m |
| rates_credit_idx | 65.4m |
| high_yield | 44.8m |
| irs_hedge | -0.0m |
| futures_overlay | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -683.6m | -1,218.5m | 534.9m |
| EUR rates +200bp parallel | -1,201.4m | -2,197.5m | 996.1m |
| EUR rates -100bp parallel | 849.4m | 1,527.5m | -678.1m |
| Equity -20% | -1,576.7m | 0.0m | -1,576.7m |
| Equity -30% | -2,365.1m | 0.0m | -2,365.1m |
| Equity -40% | -3,153.5m | 0.0m | -3,153.5m |
| HY spread +300bp (~-12%) | -52.3m | 0.0m | -52.3m |
| 2022 replay: rates +250bp, equity -20% | -2,974.9m | -2,614.0m | -360.8m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -2,320.4m | 2,435.0m | -4,755.4m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
