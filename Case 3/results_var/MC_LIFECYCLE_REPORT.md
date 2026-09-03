# Case 3b - 15-year accumulation Monte-Carlo (consistent pipeline)

50,000 paths, annual steps.  Funding waterfall: EUR 5.0bn -> cash-flow-dedicated FI book at t=0; EUR 0.5bn/yr -> the 14-index Aggressive Diversified RSP, years 1-10.  Sleeve + FI annual returns are a **multivariate Student-t (df 5)** in simple-return space, **scaled so the shock covariance equals the historical annualised covariance** (a raw mu + z/sqrt(g) runs df/(df-2) = 1.67x too wide), drift = geometric annual return exp(mean log)-1, floored at -99%.  FI return = 3.9% carry - dampened duration x rate shock.  Profit sharing starts year 15, so it does not bite inside this 0-15 window.

| metric | value |
|---|--:|
| RSP realised in sim | mean ~11.1% / vol ~16.5% p.a. (target: 10.9% / 16.5%) |
| median total assets, year 15 | EUR 21.99bn |
| 5th percentile | EUR 13.81bn |
| 0.5th percentile | EUR 10.24bn |
| 50/50 guaranteed liability, year 15 | EUR 10.01bn |
| median funding ratio | 220% |
| median 15-year IRR | 6.46% |
| 5th / 0.5th percentile IRR | 2.64% / 0.20% |
| P(underfunded, 50/50) | 0.42% |
| P(underfunded, 100% lump) | 1.06% |
| mean annual portfolio return | 6.59% |

**Year-15 lump-sum liquidity.**  The FI book is dedicated to the 50/50 schedule - it delivers EUR 5.65bn at year 15 risk-free.  Above 50% the bonds it no longer needs for the shrunk pension tail are sold at the year-15 market price (freed-tail PV from `results_v2/elections/summary.csv`); only the remainder is raised by selling the RSP.
| lump-sum election | excess over dedicated | freed FI tail bonds (median) | residual from RSP | P(shortfall) |
|---|--:|--:|--:|--:|
| <= 50% (matched) | EUR 0.00bn | - | - | 0.00% |
| 75% | EUR 2.83bn | EUR 2.60bn | EUR 0.23bn | 0.07% |
| 100% | EUR 5.65bn | EUR 5.19bn | EUR 0.46bn | 0.33% |

Charts: presentation/assets/lc_01..07_*.png
