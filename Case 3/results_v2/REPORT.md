# Case 3b - two-stage Fixed-Income optimiser (prototype)

Liability PV EUR 6.41bn, duration 20.0y, convexity 472.  Reinvestment credit 1.5%, issuer cap 30%, instrument cap 15%, Stage-2 eps 5%.

## current universe  (16 bonds, 1 zero-coupon)

| metric | Stage 1 | Stage 2 (+KRD) | liability |
|---|--:|--:|--:|
| modified duration (y) | 15.1 | **14.9** | 20.0 |
| convexity | 294 | 290 | 472 |
| asset DV01 (EUR m/bp) | 7.5 | **7.4** | 12.8 |
| **surplus DV01 gap (EUR m/bp)** | 5.3 | **5.4** | - |
| external top-up PV (EUR bn) | 1.08 | 1.14 | - |
| min running cash balance (EUR m) | 0 | 0 | - |

KRD DV01 gap by tenor (EUR m/bp): 2y -0.1, 5y -0.3, 10y -0.6, 15y +2.4, 20y +0.4, 25y +0.1, 30y +0.8, 40y +1.4

## + synthetic STRIPS 35-50y  (20 bonds, 5 zero-coupon)

| metric | Stage 1 | Stage 2 (+KRD) | liability |
|---|--:|--:|--:|
| modified duration (y) | 15.8 | **16.1** | 20.0 |
| convexity | 328 | 350 | 472 |
| asset DV01 (EUR m/bp) | 7.9 | **8.0** | 12.8 |
| **surplus DV01 gap (EUR m/bp)** | 4.9 | **4.8** | - |
| external top-up PV (EUR bn) | 1.08 | 1.14 | - |
| min running cash balance (EUR m) | 0 | 0 | - |

KRD DV01 gap by tenor (EUR m/bp): 2y -0.1, 5y -0.3, 10y -0.5, 15y +2.5, 20y +0.5, 25y +0.1, 30y +0.6, 40y +0.7

## Read

- **Stage 2 (the mechanism)**: fix cash flows first, then spend the whole EUR 5bn on the bonds that best match the liability KRD. With the current 14-30y universe it can only reach ~15y duration (surplus DV01 gap ~EUR 5m/bp) - the near-year coverage eats the budget and there is nothing to buy past 30y.
- **Adding zero-coupon STRIPS 35-50y (idea 3)**: duration 14.9 -> 16.1y, surplus DV01 gap 5.4 -> 4.8 EUR m/bp, convexity 290 -> 350 (liability 472); the 40y KRD gap roughly halves. Bigger real-world universes (OATs to 2072, Bund/OAT strips, EU/SSA ultra-longs) + a modest issuer-cap tightening push this further.
- **Convexity** is fought by (i) matching KRD *buckets*, not just total DV01 - that forces the cash-flow dispersion to track the liability; and (ii) STRIPS - one cash flow at a long maturity gives more convexity per year of duration and no reinvestment drag. The residual 40y+ shortfall is the piece for a small long receiver-swap / receiver swaption.
- **External top-up** (EUR ~1.1bn PV, mostly years 31-50) stays the return book's + future premiums' job - the FI book is EUR 5bn against a EUR 6.4bn liability, it is not meant to dedicate the whole thing.
