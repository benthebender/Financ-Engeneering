# Case 3b - 1-year 99.0% VaR  (full deployment)

Valuation date 2026-09-02. Historical simulation, 468 overlapping 52-week scenarios from ~520 weeks of factor history.

## Book

- Fixed-income (liability-matching): EUR 5.00bn, 13 bonds
- Return book (14 indices, Aggressive_Diversified): EUR 5.00bn
- Total assets: EUR 10.00bn
- Guaranteed pension liability PV: EUR 6.81bn
- Funding ratio (assets / liability PV): 1.47

## Risk-control overlay  (99% 1-year equity VaR vs economic limit)

- Economic surplus (assets - liability PV): EUR 3.19bn
- Board funding-ratio floor (1-in-100 yr): 1.20  => max tolerable 1y asset loss EUR 1.83bn
- Less non-equity surplus VaR (rates mismatch + FX + HY + longevity buffer): EUR 916m
- **Equity 99% 1y VaR limit** = EUR 911m  (19.8% of equity MV, 28.6% of economic surplus; binding: funding-ratio floor)
- Unhedged equity 99% 1y VaR (HS): EUR 964m
- rule: max(0, 1 - 911m / 964m) = 5.5%   [within +/-10% band - hold 6%]
- Applied futures short: 5.5% of equity MV (beta 1.00); no-trade band +/-10%

## Headline VaR / ES  (1-year, EUR)

| | Historical VaR | Historical ES | Parametric VaR | 1y P&L vol | worst scenario |
|---|--:|--:|--:|--:|--:|
| **Asset VaR** | 2,540.7m | 2,679.9m | 2,189.6m | 1,155.6m | 2,835.1m |
| **Surplus VaR** | 1,129.7m | 1,207.5m | 1,345.3m | 866.8m | 1,360.4m |

Asset VaR as % of assets: 25.41%   |   Surplus VaR as % of assets: 11.30%   |   Surplus VaR as % of liability: 16.59%

## Standalone 99% loss by risk driver  (indicative, not additive)

| driver | 1y 99% loss (EUR) |
|---|--:|
| liability_pnl | 2,919.4m |
| fi_bonds | 1,631.0m |
| equity | 963.6m |
| fx_hedge_residual | 187.1m |
| futures_overlay | 121.1m |
| rates_credit_idx | 39.0m |
| high_yield | 26.7m |

## Deterministic stress tests  (EUR P&L)

| scenario | asset P&L | liability P&L | surplus P&L |
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

## Method & assumptions

- HS: weekly EUR/USD swap-curve, EURUSD and 14 index levels; 52-week overlapping windows; rates as absolute changes, indices/FX as log returns.
- Bonds & liability: EUR curve only. Bonds repriced by modified duration + convexity at each bond's maturity; liability by full revaluation on the shifted zero curve. Govvie/SSA spread risk is in the stress tests only.
- Every USD sleeve is FX-swapped to EUR (rolled 1y); spot-FX risk removed, residual = change in the EUR-USD 1y rate differential. HKD leg ignored.
- Return book = 10 x EUR 0.5bn contributions deployed at target weights (strategic / fully-funded steady state). `deployment=t0` gives the inception snapshot (return book ~ 0).
- Parametric VaR uses a Normal 99% (z = 2.326) on the scenario P&L.
- Longevity is a stress line, not in the 1y HS distribution.
- Overlay: unhedged equity 99% 1y VaR (HS) -> HedgeRatio = max(0, 1 - VaR_limit / VaR_unhedged), clamped [0,1]; contracts via Equity_MV x beta x ratio / (future_price x multiplier) (futures.py). Buffer = no-trade band to damp turnover; overlay is risk control, not market timing.
