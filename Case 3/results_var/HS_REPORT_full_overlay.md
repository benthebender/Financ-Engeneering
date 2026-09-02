# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 13 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.00bn  (equity EUR 4.60bn)
- Total assets EUR 10.00bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.47

## Risk-control overlay

- Economic surplus EUR 3.19bn; funding-ratio floor 1.20 => max 1y asset loss EUR 1.83bn
- less non-equity surplus VaR EUR 916m => **equity 99% 1y VaR limit EUR 911m** (19.8% of equity MV; binding: funding-ratio floor)
- unhedged equity 99% 1y VaR EUR 964m -> rule: max(0, 1 - 911m / 964m) = 5.5%  [within +/-10% band - hold 6%]
- applied futures short 5.5% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 2,540.7m | 2,679.9m | 2,189.6m | 1,155.6m | 2,835.1m |
| **Surplus** | 1,129.7m | 1,207.5m | 1,345.3m | 866.8m | 1,360.4m |

Asset VaR 25.4% of assets | Surplus VaR 16.6% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,631.0m |
| equity | 963.6m |
| fx_hedge_residual | 187.1m |
| futures_overlay | 121.1m |
| rates_credit_idx | 39.0m |
| high_yield | 26.7m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -725.3m | -1,218.5m | 493.2m |
| EUR rates +200bp parallel | -1,282.2m | -2,197.5m | 915.3m |
| EUR rates -100bp parallel | 893.7m | 1,527.5m | -633.8m |
| Equity -20% | -940.0m | 0.0m | -940.0m |
| Equity -30% | -1,410.0m | 0.0m | -1,410.0m |
| Equity -40% | -1,880.0m | 0.0m | -1,880.0m |
| HY spread +300bp (~-12%) | -31.2m | 0.0m | -31.2m |
| 2022 replay: rates +250bp, equity -20% | -2,437.5m | -2,614.0m | 176.5m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -776.3m | 2,435.0m | -3,211.4m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
