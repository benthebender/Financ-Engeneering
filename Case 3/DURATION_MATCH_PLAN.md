# Case 3b - closing the asset / liability duration gap

## The problem

The guaranteed pension liability has an effective duration of **~20-22 years**
(PV ~ EUR 6.4bn, with 11% of PV beyond 30y). The EUR 5bn Fixed-Income book only
reaches **~15 years** - the near/mid liability cash flows (years 15-30) absorb
the budget and there is nothing in the current 16-bond, 14-30y universe to buy
past 30y. The uncovered piece is a **surplus DV01 of ~EUR 5-6m per bp**:
a rate rally lifts the liability more than the assets, so surplus falls, and the
2008-replay stress (equity -45% with rates -150bp) costs ~ EUR 3.2bn of surplus.

Bolting an IRS onto the whole gap works but brings CSA / variation-margin
liquidity risk, hedge-accounting and counterparty exposure. So first make the
**bond book itself** do as much of the match as it can.

## The fix - ideas 2 and 3

**2. Two-stage (lexicographic) optimiser.** Keep the cash-flow dedication
primary, put duration second:

- *Stage 1* - minimise the PV of the external top-up the bond book cannot
  supply, subject to a non-negative running cash balance every year and the
  EUR 5bn budget + issuer / instrument caps. This is the honest "fix the cash
  flows" step; whatever the universe cannot reach (mostly years 31-50) is
  flagged as the return book's / future premiums' job, not forced onto FI.
- *Stage 2* - **with the full EUR 5bn still available**, buy the bonds that
  best match the liability **key-rate DV01 profile** (`min Sum_j w_j (KRD_a(j) -
  KRD_l(j))^2`), allowing the Stage-1 coverage to slip by at most a small
  epsilon. So: fix the cash flows, then term out the rest into the longest
  bonds that best fit the liability's KRD shape.

Prototype: `cashflow_match_v2.py` (leaves `alm_fixed_income_.py` untouched;
outputs to `results_v2/`).

**3. Widen the long-duration universe** - the real enabler. The optimiser can
only match a KRD bucket if it owns a bond that matures there. Add ultra-long
core / semi-core EGBs, EU / SSA ultra-longs, and especially **government
STRIPS** (zero-coupon). Tighten the single-issuer cap (e.g. 10% for non-AAA)
once the set is deep enough so the caps stop forcing the book off duration.

Prototype result (current 16-bond set vs. the same set + synthetic 35-50y
STRIPS):

| | current universe | + STRIPS 35-50y | liability |
|---|--:|--:|--:|
| modified duration | 14.9y | **16.1y** | 20.0y |
| surplus DV01 gap | 5.4 m/bp | **4.8 m/bp** | - |
| convexity | 290 | **350** | 472 |
| 40y KRD DV01 gap | +1.4 m/bp | **+0.7 m/bp** | - |

Real ultra-long ISINs (OATs to 2072, Bund/OAT/DSL strips, EU/NGEU 2050s,
KfW/EIB/CADES 30y+) plus the tighter caps push this materially further.

## Battling convexity - STRIPS + KRD

Matching duration is not enough: the liability's cash flows are spread across a
long tail, so it has **more convexity** than a bullet-ish long-bond book (472
vs ~290-350 in the prototype). Two levers:

1. **Match key-rate DV01 buckets, not just total DV01.** Forcing
   `KRD_asset(j) ~ KRD_liab(j)` at every tenor j makes the *dispersion* of the
   asset cash flows track the liability - a first-order convexity match. Total
   DV01 can be right while the shape (and therefore convexity and twist
   exposure) is wrong.
2. **Zero-coupon STRIPS.** A single cash flow at a long maturity delivers more
   convexity per year of duration than a coupon bond, and has **no
   reinvestment drag** - the coupon-bond problem where a rate rally (the
   scenario you are hedging) reinvests coupons at low rates. STRIPS let you
   place weight exactly in the 30-50y KRD buckets.

The residual after (2) + (3) - the deep 40y+ shortfall a EUR 5bn cash book
physically cannot reach - is closed with a **small** long-dated receiver-swap
ladder or a receiver swaption. Much smaller notional than hedging the whole
gap, so the CSA / liquidity footprint stays minimal.

## Shopping list (while step 2 is being built)

Into `Data/Fixed Income Basket.xlsx`, same 5-column block format
`[weekday, date, clean price, coupon (decimal), maturity year]`:

- **Ultra-long nominal EGBs (25-50y):** France OAT 3.25% 05/2055, OAT 0.5%
  05/2072, DSL 2.5% 01/2054, RAGB 0.85% 06/2120 (Austria century), Belgium OLO
  2057/2071, Netherlands DSL 2052, Spain SPGB 2052/2071 (spread trade - use
  sparingly), Italy BTP only if you want the spread, not for the core.
- **EU / SSA ultra-longs:** EU / NGEU 2048-2058, KfW / EIB / CADES / Bpifrance
  30y+.
- **Government STRIPS (coupon = 0):** German Bund principal strips and French
  OAT / Dutch DSL strips at ~2035 / 2040 / 2045 / 2050 / 2054. These are the
  KRD-precision + convexity tool - AAA/AA, single cash flow, no reinvestment.
- Keep it **nominal** (the 1% Hoechstrechnungszins guarantee is nominal -
  inflation linkers would add basis).
- Diversify issuers: aim for no single sovereign > ~15% of the EUR 5bn, tighter
  for non-AAA. Green bonds are fine (same risk).
- A recent clean price per line is enough; a short price history column would
  also let the VaR model pick up their spread history later.
