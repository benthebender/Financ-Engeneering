# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 11 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.00bn  (equity EUR 4.60bn)
- Total assets EUR 10.00bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.47

## Risk-control overlay

- Economic surplus EUR 3.19bn; funding-ratio floor 1.20 => max 1y asset loss EUR 1.83bn
- less non-equity surplus VaR EUR 996m => **equity 99% 1y VaR limit EUR 830m** (18.1% of equity MV; binding: funding-ratio floor)
- unhedged equity 99% 1y VaR EUR 964m -> rule: max(0, 1 - 830m / 964m) = 13.8%  [outside +/-10% band - move to 14%]
- applied futures short 13.8% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 2,384.1m | 2,512.8m | 2,060.3m | 1,083.8m | 2,652.9m |
| **Surplus** | 1,194.7m | 1,254.9m | 1,329.3m | 843.7m | 1,399.5m |

Asset VaR 23.8% of assets | Surplus VaR 17.5% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,543.1m |
| equity | 963.6m |
| futures_overlay | 303.9m |
| fx_hedge_residual | 187.1m |
| rates_credit_idx | 39.0m |
| high_yield | 26.7m |
| irs_hedge | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -683.6m | -1,218.5m | 534.9m |
| EUR rates +200bp parallel | -1,201.4m | -2,197.5m | 996.1m |
| EUR rates -100bp parallel | 849.4m | 1,527.5m | -678.1m |
| Equity -20% | -940.0m | 0.0m | -940.0m |
| Equity -30% | -1,410.0m | 0.0m | -1,410.0m |
| Equity -40% | -1,880.0m | 0.0m | -1,880.0m |
| HY spread +300bp (~-12%) | -31.2m | 0.0m | -31.2m |
| 2022 replay: rates +250bp, equity -20% | -2,338.1m | -2,614.0m | 275.9m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -843.7m | 2,435.0m | -3,278.7m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
