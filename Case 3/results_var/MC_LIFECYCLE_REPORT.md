# Case 3b - 15-year accumulation Monte-Carlo (consistent pipeline)

50,000 paths, annual steps, Student-t (df 5).  Funding waterfall: EUR 5.0bn -> cash-flow-dedicated FI book at t=0; EUR 0.5bn/yr -> the 14-index Aggressive Diversified RSP, years 1-10.  FI annual return ~ t(loc 3.9%, dampened duration effect); RSP ~ multivariate t on the sleeves' historical annualised mean/cov.  Profit sharing starts year 15, so it does not bite inside this 0-15 window.

| metric | value |
|---|--:|
| RSP blended assumption | mean 10.4% / vol 16.6% p.a. (historical) |
| median total assets, year 15 | EUR 20.53bn |
| 5th percentile | EUR 11.33bn |
| 0.5th percentile | EUR 7.07bn |
| 50/50 guaranteed liability, year 15 | EUR 10.01bn |
| median funding ratio | 205% |
| median 15-year IRR | 5.89% |
| 5th / 0.5th percentile IRR | 1.02% / -2.83% |
| P(underfunded, 50/50) | 2.53% |
| P(underfunded, 100% lump) | 4.95% |
| mean annual portfolio return | 6.25% |

**Year-15 lump-sum liquidity.**  The FI book is dedicated to the 50/50 schedule - it delivers EUR 5.65bn at year 15 risk-free.  Above 50% the bonds it no longer needs for the shrunk pension tail are sold at the year-15 market price (freed-tail PV from `results_v2/elections/summary.csv`); only the remainder is raised by selling the RSP.
| lump-sum election | excess over dedicated | freed FI tail bonds (median) | residual from RSP | P(shortfall) |
|---|--:|--:|--:|--:|
| <= 50% (matched) | EUR 0.00bn | - | - | 0.00% |
| 75% | EUR 2.83bn | EUR 2.60bn | EUR 0.23bn | 0.76% |
| 100% | EUR 5.65bn | EUR 5.19bn | EUR 0.46bn | 2.08% |

Charts: presentation/assets/lc_01..07_*.png
