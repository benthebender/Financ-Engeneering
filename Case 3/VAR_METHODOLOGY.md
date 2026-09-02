# Case 3b - 99% 1-year VaR: methodology and the risk limit

## 1. The risk measure

**99% confidence, 1-year horizon Value at Risk** of the combined book: the loss
level on the 1-year P&L distribution that is exceeded with 1% probability.
Reported on two P&L definitions:

- **Asset VaR** - loss of the asset portfolio alone (mandate monitoring, the
  input to the futures-overlay rule, which acts on the *equity sleeve's* Asset
  VaR).
- **Surplus VaR** - loss of `assets - guaranteed pension liability PV` (the
  economic question: can the insurer still meet its guarantees after a 1-in-100
  year). Under IAS the guaranteed benefit obligation is the liability anchor.

1-year is the right horizon for a life insurer: it matches the solvency
reporting cycle and the rebalancing frequency of a strategic asset allocation;
it is not a trading-desk 1- or 10-day measure.

## 2. Estimation - three pillars

| pillar | role | engine |
|---|---|---|
| **Historical Simulation (HS)** | primary | `case3_var.py` |
| **Monte-Carlo (t-copula)** | tail / forward-looking cross-check | `montecarlo.py` |
| **Parametric (Normal + Cornish-Fisher)** | fast monitor for the frequent overlay recalculation | in `case3_var.py` (`param_var`) |

Each factor's 1-year move is built from **weekly** observations (weekly avoids
the trading-calendar mismatch across 14 global indices + EUR/USD curves).
Rates enter as **absolute** changes, index levels and FX as **log returns**.

### 2.1 Lookback period

**10 years of weekly data (~520 observations).** Justification:

- Covers a full interest-rate cycle (ZIRP -> 2022 hiking shock -> partial
  normalisation), the 2020 COVID crash and the 2018/2025 equity corrections -
  i.e. at least one severe episode per risk factor.
- Long enough that the 99th percentile of ~468 overlapping annual windows is the
  ~5th-worst point (not 2nd-3rd as a 5-year window would give).
- Not longer: pre-2015 EUR rates were structurally different (pre-ZIRP, the euro
  crisis), and >15-year windows dilute the current regime and the current index
  composition. Bloomberg history for several sleeves (rare-earth, some ETFs)
  only starts ~2015 anyway.
- **Stress overlay:** because a 10-year window happens to contain **no severe
  rate-rally year**, HS is complemented by (i) explicit 2008 / deflation
  stress scenarios and (ii) the Monte-Carlo pillar, which does generate
  -250bp rate years. This gap is a headline finding, not a nuisance - see 4.

### 2.2 Volatility estimation

- **HS**: volatility is implicit in the empirical distribution - no estimate
  needed. This is the main number.
- **Monte-Carlo & parametric**: **EWMA covariance, lambda = 0.97 weekly**
  (RiskMetrics-style, ~1-year effective memory). Chosen over the equal-weighted
  sample covariance because the overlay must be *responsive* - when equity
  volatility rises the measured VaR must rise so the hedge is put on. The
  equal-weighted sample covariance is reported as a slow-moving anchor.
- A **GARCH(1,1)** per sleeve is the natural upgrade (vol clustering + mean
  reversion); EWMA is GARCH(1,1) with the persistence pinned, and is enough
  here given the estimation noise from ~520 weeks.

### 2.3 Correlations between the ETFs

- 14 sleeves -> a 14x14 (91-parameter) correlation matrix from ~520 weekly
  points ~ 37 obs per asset: too few for the raw sample matrix to be stable or
  well-conditioned.
- **Ledoit-Wolf-style shrinkage**: `R_hat = (1-d) R_sample + d R_target`, target
  = the average pairwise correlation on the diagonal-preserving matrix,
  `d ~ 0.10`, then projected to the nearest positive-definite matrix
  (`montecarlo._shrunk_corr`). This stabilises the tails of the simulation and
  the parametric VaR.
- **Crisis correlation**: equity-equity correlations rise toward 1 in a
  sell-off. HS captures this automatically (it replays real joint moves); the
  Monte-Carlo t-copula captures it through **tail dependence** (see 2.4); and
  the 2008-replay stress applies an all-equity -45% jointly. A static-correlation
  parametric number understates the tail and is used only as a monitor.
- The EUR curve block (15 tenors, ~0.95-0.99 correlated) is reduced to **3
  principal components** (level / slope / curvature, ~99% of variance) before
  simulation, so simulated curve shifts stay economically shaped rather than
  picking up spurious tenor-by-tenor noise.

### 2.4 Non-normal returns

Equity 1-year returns are fat-tailed and left-skewed; a Normal VaR understates
the 99% loss by 20-40%. Treatment:

1. **HS** is non-parametric - it inherits the empirical skew/kurtosis directly.
   Primary number.
2. **Monte-Carlo**: innovations from a **multivariate Student-t, dof 5**
   (~3x a Normal's excess kurtosis, plus non-zero tail dependence so sleeves
   crash together). `dof = inf` recovers the Gaussian copula and is run as the
   reference. A **1.25x-worst-observed guardrail** caps each simulated 1-year
   factor move so the t-tails cannot produce curve or index moves beyond
   anything in the data.
3. **Parametric**: a **Cornish-Fisher** quantile expansion adjusts the Normal
   z (2.326) for the sample skew and excess kurtosis - a cheap analytic
   correction for the between-recalculation monitor.

### 2.5 One-year aggregation

Do **not** `sqrt(52)`-scale a weekly VaR (that assumes i.i.d. Normal weekly
returns - false on both counts). Instead:

- **HS**: sum 52 consecutive weekly factor moves -> **overlapping 52-week
  windows** -> ~468 annual scenarios; reprice the book under each.
- **MC**: simulate 52 weekly steps and compound; captures within-year
  autocorrelation only weakly, but the guardrail + stress scenarios cover the
  persistent-trend case.

### 2.6 Repricing

- **Bonds**: modified duration + convexity at each bond's maturity on the
  shifted EUR curve (govvie/SSA spread risk is in the stress tests only - no
  spread history).
- **Liability**: full revaluation of the guaranteed benefit CF (50% lump sum at
  year 15 + 50% mortality-weighted pension, years 16-50) on the shifted EUR zero
  curve.
- **Index sleeves**: own-currency total return (= the EUR-hedged return).
- **FX**: every USD sleeve rolled with a 1-year FX swap - spot-FX risk removed,
  residual = change in the EUR-USD 1-year rate differential. HKD leg of the HK
  ETF ignored.
- **Longevity**: a stress line (+1yr life expectancy ~ +4% liability), not in the
  1-year market-risk distribution.

## 3. The 99% 1-year VaR LIMIT - economic derivation

The limit is **derived from the insurer's balance sheet and risk-bearing
capacity**, not set as an arbitrary percentage. Three anchors, all computed in
`case3_var.derive_var_limit`:

### Balance-sheet inputs (full deployment, valuation 2026-09-02)

| | EUR |
|---|--:|
| Total assets | 10.00bn |
| Guaranteed pension liability PV (IAS, market-discounted) | 6.81bn |
| **Economic surplus** (assets - liability) | **3.19bn** |
| Funding ratio (assets / liability PV) | 1.47 |
| Equity sleeve market value | 4.6bn |
| Non-equity **surplus** 99% 1y VaR (rate mismatch + FX + HY + longevity buffer), HS | ~0.92bn |
| FI-book modified duration ~15y  vs  liability effective duration ~22y | mismatch |

### Anchor A - funding-ratio floor (recommended, binding)

The board sets a **minimum funding ratio that must hold in a 1-in-100 year**.
A floor of **1.20** is defensible: Solvency-II-style calibration puts the
1-in-200 point near a 1.0 ratio, and the insurer wants a margin above that plus
room for the risk margin and a management buffer.

```
max tolerable 1y asset loss  = assets - 1.20 x liability_PV
                             = 10.00bn - 1.20 x 6.81bn  =  1.83bn
equity 99% 1y VaR limit      = 1.83bn - non-equity surplus VaR (0.92bn)
                             ~  0.91bn
```

### Anchor B - surplus-at-risk cap (cross-check)

A 1-in-100 year should leave **at least two-thirds of the buffer intact** (so
two consecutive bad years don't breach solvency):

```
limit <= economic_surplus / 3  =  3.19bn / 3  =  1.06bn
```

### Anchor C - guarantee self-funding (sizing sanity)

The guarantee costs 1% p.a. As long as the asset book's 99% 1-year return is
above `-(surplus + guarantee cost)/assets`, the guarantee is covered from
surplus. With surplus 3.19bn and guarantee ~0.07bn/yr, the tolerable 1y asset
loss on this anchor is ~3.3bn - not binding; it confirms A and B are the
constraints.

### Recommended limit

**Equity sleeve: 99% 1-year VaR limit = EUR 0.9bn**
(~20% of equity MV, ~28% of economic surplus, ~50% of the total asset-loss
budget). Anchor A (funding-ratio floor) binds; Anchor B is a comfortable
cross-check. Recalculate quarterly and after any change to the SAA or the
liability assumptions.

### Important caveat from the Monte-Carlo pillar

Under HS the **unhedged equity VaR (0.96bn) is essentially at the 0.9bn limit**
-> hedge ratio ~ 0-6% (inside the no-trade band). Under **Monte-Carlo** the
non-equity surplus VaR is ~1.5bn (it picks up the -250bp rate-rally tail that
the 10-year HS window lacks), which **eats most of the loss budget** and drives
the derived equity limit down to ~0.3bn -> hedge ratio ~ 70%.

The divergence is not a modelling error - it is the **asset/liability duration
mismatch** (15y vs 22y) showing up once you allow a proper rate-rally tail.
**Recommendation:** close the duration gap (extend FI, or add EUR receiver
swaps) so the rate mismatch stops competing with the equity risk budget; then
both HS and MC give an equity limit near EUR 0.9-1.0bn and today's required
hedge is ~zero. Until then, use the more prudent MC-based limit for the overlay.

## 4. The futures overlay (risk-control, not market timing)

1. Compute the **unhedged equity sleeve's 99% 1-year VaR** (HS; MC as the
   prudent alternative).
2. Compare to the limit above.
3. `VaR_unhedged <= limit`  -> no hedge.
4. `VaR_unhedged >  limit`  -> short equity-index futures.
5. `HedgeRatio = max(0, 1 - VaR_limit / VaR_unhedged)`, clamped to `[0, 1]`
   (never a net short).
6. `Number of futures = Equity_Exposure x beta x HedgeRatio /
   (Futures_Price x Contract_Multiplier)`  (`futures.py::hedge_contracts`).
7. Recompute the VaR **quarterly** (and on a vol spike); adjust the short:
   VaR up -> add, VaR down -> reduce, VaR below limit -> remove.
8. **No-trade band: +/-10% around the limit** - if `VaR_unhedged` is within
   0.9x-1.1x of the limit, hold the current position. Prevents churn when VaR
   oscillates around the threshold. (VIX data, when available, can gate the
   band width - widen it in calm regimes, tighten it when VIX spikes.)
9. The overlay never expresses a view on the direction of equities. It is
   triggered only when the *measured* 99% 1-year equity VaR exceeds the
   insurer's predefined budget.

## 5. Governance

- **Recalculation:** quarterly for the limit and the overlay; monthly parametric
  monitor between full runs.
- **Backtesting:** roll a 1-day 99% VaR against realised daily P&L over 250 days;
  Kupiec unconditional-coverage and Christoffersen independence tests. A 1-year
  99% measure cannot be backtested directly (one non-overlapping observation per
  year) - rely on the daily backtest plus the stress-scenario coverage.
- **Model risk:** report HS, MC(t) and parametric side by side every quarter;
  a >30% divergence triggers a methodology review.

## 6. Headline numbers (see `results_var/`)

| | HS (primary) | Monte-Carlo (t, dof 5) |
|---|--:|--:|
| Asset VaR (99%, 1y) | EUR 2.59bn | EUR 2.40bn |
| Surplus VaR (99%, 1y) | EUR 1.14bn | EUR 1.71bn |
| Unhedged equity VaR | EUR 0.96bn | EUR 1.14bn |
| Derived equity VaR limit | EUR 0.91bn | EUR 0.31bn |
| -> futures hedge ratio | ~0% (in band) | ~73% |
| Worst stress (2008 replay, surplus) | ~ -EUR 3.2bn | - |
