# Case 3b - two-stage Fixed-Income optimiser + key-rate DV01

KRD = real key-rate DV01: a triangular 1bp bump of the zero curve at each key tenor [2, 5, 10, 15, 20, 25, 30, 40, 50, 65, 90], cash flows repriced. Stage 1 minimises the external top-up PV (cash-flow dedication); Stage 2 minimises Sum_j (KRD_asset(j) - KRD_liab(j))^2 with the full EUR 5bn, coverage allowed to slip <= 5%.

Liability PV EUR 6.41bn, duration 20.0y, convexity 472.  Reinvestment credit 1.5%, issuer cap 30%, instrument cap 15%.

## current basket only  (16 bonds, 1 zero-coupon, longest 30y)

| metric | Stage 1 | Stage 2 (+KRD) | liability |
|---|--:|--:|--:|
| effective duration (y, from KRD) | 17.8 | **17.6** | 20.0 |
| convexity | 295 | 296 | 472 |
| asset DV01 (EUR m/bp) | 8.9 | **8.8** | 12.8 |
| **surplus DV01 gap (EUR m/bp)** | 3.9 | **4.0** | - |
| external top-up PV (EUR bn) | 1.08 | 1.14 | - |
| min running cash balance (EUR m) | 0 | 0 | - |

Stage-2 KRD DV01 gap by tenor (EUR m/bp): 2y -0.1, 5y -0.3, 10y -0.8, 15y +2.8, 20y +0.4, 25y -0.5, 30y +0.8, 40y +1.4, 50y +0.2, 65y -0.0, 90y -0.0

Stage-2 holdings: KFW 0.945 12/17/2040 Corp 0.75bn, BGB 4 ¼ 03/28/2041 Corp 0.75bn, LGB 1 ¾ 05/25/2042 0.75bn, EU 4 10/12/2055 0.75bn, ITALY 5.345 01/27/2048 Corp 0.75bn, EU 0.7 07/06/2051 0.60bn, DBR 2.9 08/15/2056 0.30bn, RENTEN 3.676 10/12/2043 0.16bn, DBR 0 08/15/2050 G 0.13bn, BGB 3 ¾ 06/22/2045 0.06bn

## + ZCB & ultra-long workbook  (25 bonds, 7 zero-coupon, longest 94y)

| metric | Stage 1 | Stage 2 (+KRD) | liability |
|---|--:|--:|--:|
| effective duration (y, from KRD) | 54.4 | **29.2** | 20.0 |
| convexity | 771 | 332 | 472 |
| asset DV01 (EUR m/bp) | 26.0 | **14.6** | 12.8 |
| **surplus DV01 gap (EUR m/bp)** | -13.2 | **-1.8** | - |
| external top-up PV (EUR bn) | 0.00 | 0.00 | - |
| min running cash balance (EUR m) | 108 | 0 | - |

Stage-2 KRD DV01 gap by tenor (EUR m/bp): 2y -0.1, 5y -0.4, 10y -1.0, 15y +2.8, 20y -0.3, 25y -0.1, 30y +0.4, 40y +0.3, 50y -0.5, 65y -0.9, 90y -2.0

Stage-2 holdings: KFW 0.945 12/17/2040 Corp 0.75bn, BGB 4 ¼ 03/28/2041 Corp 0.75bn, ITALY 5.345 01/27/2048 Corp 0.75bn, EU 4 10/12/2055 0.75bn, BGB 3 ¾ 06/22/2045 0.75bn, EU 0.7 07/06/2051 0.44bn, RENTEN 3.676 10/12/2043 0.37bn, IBRD 0 11/09/2061 Corp 0.16bn, LGB 1 ¾ 05/25/2042 0.13bn, NRW 2.15 03/21/2119 0.10bn

## Read

- **Stage 2 (mechanism)**: Stage 1 minimises the cash-flow top-up and with the ultra-long ZCBs over-terms hard (effective duration ~54y, DV01 ~2x the liability); Stage 2 then reshapes to the liability KRD while keeping full coverage - a sane, KRD-matched book.
- **Adding the ZCB / ultra-long workbook** (Stage 2): effective duration (from KRD) 17.6 -> **29.2y** (liability 20.0y), surplus DV01 gap +4.0 -> **-1.8 EUR m/bp** (≈ closed), convexity 296 -> **332** (liability 472), and the cash-flow top-up 1.14 -> **0.00 bn PV**.
- **Convexity** is fought by (i) matching KRD *buckets*, not just total DV01 - forces the asset cash-flow dispersion onto the liability; and (ii) the zero-coupon bonds - one cash flow at a long maturity, higher convexity per year of duration, no reinvestment drag.
- **Residual**: whatever KRD gap remains past the longest usable bond, plus the ~EUR 0.0bn PV external top-up (years past the coverage horizon), stays for a small long receiver swap / swaption and the return book + future premiums.
