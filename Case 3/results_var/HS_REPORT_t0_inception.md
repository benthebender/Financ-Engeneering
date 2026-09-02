# Case 3b - Historical-Simulation 1-year 99% VaR  (t0)

Valuation 2026-09-02. 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book / structure

- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR 5.00bn, 13 bonds
- Return book (t=1..10, 10 x EUR 0.5bn, Aggressive_Diversified): EUR 0.00bn  (equity EUR 0.00bn)
- Total assets EUR 5.00bn | guaranteed liability PV EUR 6.81bn | funding ratio 0.73

## Risk-control overlay

- Economic surplus EUR -1.81bn; funding-ratio floor 1.20 => max 1y asset loss EUR -3.17bn
- less non-equity surplus VaR EUR 959m => **equity 99% 1y VaR limit EUR nanm** (nan% of equity MV; binding: surplus-at-risk cap)
- unhedged equity 99% 1y VaR EUR -0m -> overlay N/A (no return book / pre-funding)
- applied futures short 0.0% of equity MV (beta 1.00)

## Headline VaR / ES (1-year, EUR)

| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |
|---|--:|--:|--:|--:|--:|
| **Asset**   | 1,631.0m | 1,674.3m | 1,693.3m | 684.0m | 1,695.0m |
| **Surplus** | 958.9m | 980.6m | 1,100.4m | 503.3m | 1,030.0m |

Asset VaR 32.6% of assets | Surplus VaR 14.1% of liability

## Standalone 99% 1y loss by driver (indicative)

| driver | loss |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,631.0m |
| equity | -0.0m |
| high_yield | -0.0m |
| rates_credit_idx | -0.0m |
| fx_hedge_residual | -0.0m |
| futures_overlay | -0.0m |

## Stress tests (EUR P&L)

| scenario | asset | liability | surplus |
|---|--:|--:|--:|
| EUR rates +100bp parallel | -725.3m | -1,218.5m | 493.2m |
| EUR rates +200bp parallel | -1,282.2m | -2,197.5m | 915.3m |
| EUR rates -100bp parallel | 893.7m | 1,527.5m | -633.8m |
| Equity -20% | 0.0m | 0.0m | 0.0m |
| Equity -30% | 0.0m | 0.0m | 0.0m |
| Equity -40% | 0.0m | 0.0m | 0.0m |
| HY spread +300bp (~-12%) | 0.0m | 0.0m | 0.0m |
| 2022 replay: rates +250bp, equity -20% | -1,497.5m | -2,614.0m | 1,116.5m |
| 2008 replay: equity -45%, rates -150bp, HY -25% | 1,403.7m | 2,435.0m | -1,031.4m |
| Longevity +1yr life exp (~+4% liability) | 0.0m | 272.4m | -272.4m |
