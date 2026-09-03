# Case 3b - Historical-Simulation 1-year 99% VaR  (full)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 13 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 5.26bn  (equity EUR 4.84bn)
- Total assets EUR 10.26bn | guaranteed liability PV EUR 6.81bn | funding ratio 1.51

## Risk-control overlay

- Economic surplus EUR 3.45bn; funding-ratio floor 1.20 => max 1y asset loss EUR 2.09bn
- less non-equity surplus VaR EUR 914m => **equity 99% 1y VaR limit EUR 1,150m** (23.8% of equity MV; binding: surplus-at-risk cap)
- unhedged equity 99% 1y VaR EUR 1,014m -> pinned at 0% (rule -> 0.0%)
- applied futures short 0.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 2,646.2m | 2,790.8m | 2,281.7m | 1,222.0m | 2,958.1m |
| **Surplus** | 1,147.5m | 1,242.2m | 1,433.5m | 931.6m | 1,409.8m |

Asset VaR 25.8% of assets | Surplus VaR 16.8% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,631.0m |
| equity | 1,014.3m |
| fx_hedge_residual | 196.9m |
| rates_credit_idx | 41.0m |
| high_yield | 28.1m |
| futures_overlay | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -725.3m | -1,218.5m | 493.2m |
| EUR rates +200bp parallel | -1,282.2m | -2,197.5m | 915.3m |
| EUR rates -100bp parallel | 893.7m | 1,527.5m | -633.8m |
| Equity -20% | -989.4m | 0.0m | -989.4m |
| Equity -30% | -1,484.1m | 0.0m | -1,484.1m |
| Equity -40% | -1,978.8m | 0.0m | -1,978.8m |
| HY spread +300bp (~-12%) | -32.8m | 0.0m | -32.8m |
| 2022 replay: rates +250bp, equity -20% | -2,486.9m | -2,614.0m | 127.1m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | -890.9m | 2,435.0m | -3,325.9m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
