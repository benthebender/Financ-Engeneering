# Case 3b - FI book by policyholder election  (two-stage pipeline rerun)

Full `cashflow_match_v2` two-stage optimise (cash-flow dedication + KRD shaping, +ZCB / ultra-long universe) rerun for each year-15 lump-sum election.  All books spend the EUR 5.0bn budget.

|   lump_pct |   mv_bn |   eff_dur |   convexity |   dv01_asset_m |   dv01_gap_m |   topup_pv_bn |   liab_pv_bn |   liab_dur |   yr15_liab_cf_bn |   yr15_asset_cf_bn |   tail_pv15_bn |
|-----------:|--------:|----------:|------------:|---------------:|-------------:|--------------:|-------------:|-----------:|------------------:|-------------------:|---------------:|
|          0 |       5 |     31.47 |      530.95 |          15.73 |        -0.16 |             0 |         6.14 |      25.4  |              0    |               0.18 |          10.37 |
|         25 |       5 |     30.07 |      426.1  |          15.03 |        -0.85 |             0 |         6.27 |      22.63 |              2.83 |               0.95 |           7.77 |
|         50 |       5 |     29.2  |      331.62 |          14.6  |        -1.8  |             0 |         6.41 |      19.98 |              5.65 |               0.97 |           5.18 |
|         75 |       5 |     60.43 |      365.49 |          30.22 |       -18.8  |             0 |         6.55 |      17.44 |              8.48 |               1.14 |           2.59 |
|        100 |       5 |     97.53 |      462.12 |          48.77 |       -38.74 |             0 |         6.69 |      15    |             11.3  |               1.31 |           0    |

## Holding the 50/50 book into a higher lump-sum election

The book we hold is matched to 50/50 - it delivers EUR 5.65bn at year 15 by dedication (risk-free).  If more than half elect the lump, the bonds it no longer needs for the (now smaller) pension tail are sold at the year-15 market price toward the larger lump; only the remainder must come from the RSP.

| election | year-15 lump demand | dedicated (risk-free) | freed tail PV (sold at mkt) | still needed from the RSP |
|---|--:|--:|--:|--:|
| 0% lump | EUR 0.00bn | EUR 0.00bn | EUR 0.00bn | **EUR 0.00bn** |
| 25% lump | EUR 2.83bn | EUR 2.83bn | EUR 0.00bn | **EUR 0.00bn** |
| 50% lump | EUR 5.65bn | EUR 5.65bn | EUR 0.00bn | **EUR 0.00bn** |
| 75% lump | EUR 8.48bn | EUR 5.65bn | EUR 2.59bn | **EUR 0.23bn** |
| 100% lump | EUR 11.30bn | EUR 5.65bn | EUR 5.18bn | **EUR 0.47bn** |

Freed tail PV is valued at the year-15 curve, so it carries rate risk; the residual is what must come from selling the Return-Seeking Portfolio at market.  `mc_lifecycle.py` uses `dedicated` (EUR 5.65bn) and the freed-tail PV for the year-15 liquidity metric.
