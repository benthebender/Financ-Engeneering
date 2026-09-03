# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 11 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.26bn  (equity EUR 4.84bn)
- Total assets EUR 10.26bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.51

## Risk-control overlay

- Economic surplus EUR 3.45bn; funding-ratio floor 1.20 => max 1y asset loss EUR 2.08bn
- less non-equity surplus VaR EUR 994m => **equity 99% 1y VaR limit EUR 1,089m** (22.5% of equity MV; binding: funding-ratio floor)
- unhedged equity 99% 1y VaR EUR 1,013m -> pinned at 0% (rule -> 0.0%)
- applied futures short 0.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 2,568.0m | 2,702.5m | 2,213.0m | 1,194.9m | 2,864.5m |
| **Surplus** | 1,235.4m | 1,309.9m | 1,458.1m | 944.6m | 1,488.4m |

Asset VaR 25.0% of assets | Surplus VaR 18.1% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,543.1m |
| equity | 1,013.1m |
| fx_hedge_residual | 196.6m |
| rates_credit_idx | 41.0m |
| high_yield | 28.1m |
| irs_hedge | -0.0m |
| futures_overlay | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -683.6m | -1,218.5m | 534.9m |
| EUR rates +200bp parallel | -1,201.4m | -2,197.5m | 996.1m |
| EUR rates -100bp parallel | 849.4m | 1,527.5m | -678.1m |
| Equity -20% | -988.2m | 0.0m | -988.2m |
| Equity -30% | -1,482.3m | 0.0m | -1,482.3m |
| Equity -40% | -1,976.4m | 0.0m | -1,976.4m |
| HY spread +300bp (~-12%) | -32.8m | 0.0m | -32.8m |
| 2022 replay: rates +250bp, equity -20% | -2,386.3m | -2,614.0m | 227.7m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -955.5m | 2,435.0m | -3,390.5m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
