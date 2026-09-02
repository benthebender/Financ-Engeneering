# Case 3b - combined book & 1-year 99% VaR

Ties the two sub-books into one portfolio and runs **99% 1-year VaR** by
Historical Simulation (primary), Monte-Carlo (t-copula, `montecarlo.py`) and a
parametric check, plus deterministic stress tests and the rule-based futures
overlay. Full methodology + the economic VaR-limit derivation:
**`VAR_METHODOLOGY.md`**.

## Pipeline

```
alm_fixed_income_.py  --> results/fixed_income_portfolio.csv      (16 EUR gov/SSA bonds, EUR 5.0bn)
Investment portfolio.py --> portfolio_optimization_final.xlsx      (14 indices, Aggressive_Diversified)
                              |                    |
                              v                    v
                         case3_var.py  ------------------------> results_var/
   futures.py  (equity index-future pricing, hedge-ratio knob)
   fx.py       (1y FX swap: every USD sleeve hedged to EUR, HKD leg ignored)
```

Run:

```bash
python case3_var.py                 # HS suite: full_unhedged / full_overlay / t0
python case3_var.py full auto       # one HS run, rule-based hedge ratio
python case3_var.py full 0.30       # pin the hedge ratio at 30%
python montecarlo.py full 25000     # Monte-Carlo (Student-t dof 5 + Gaussian), 25k paths
```

## Funding waterfall

| time | flow | into |
|---|---|---|
| t=0 | +EUR 5.0bn | Fixed-Income book (entirely) |
| t=1..10 | +EUR 0.5bn / yr | Return book, deployed at target weights |

`deployment="full"` = 10 x 0.5bn contributions deployed (strategic steady state,
EUR 5.0bn FI + EUR 5.0bn return). `deployment="t0"` = inception, return book ~ 0.

## Method (Historical Simulation)

- Risk factors, weekly: EUR & USD swap curves (1..30y), EURUSD, the 14 index
  levels. ~520 weeks of common history.
- 52-week **overlapping** windows -> 468 annual scenarios. Rates as absolute
  changes; indices / FX as log returns.
- Repricing per scenario:
  - **Bonds** - modified duration + convexity at each bond's maturity, on the
    shifted EUR curve.
  - **Liability** - full revaluation of the guaranteed benefit CF (50% lump sum
    at year 15 + 50% mortality-weighted pension, years 16..50) on the shifted
    EUR zero curve.
  - **Index sleeves** - own-currency total return (= the EUR-hedged return).
  - **FX hedge residual** - EUR value x change in the EUR-USD 1y rate
    differential (spot-FX risk removed by the swap).
  - **Futures overlay** - short MSCI World proxy, notional = ratio x beta x
    equity MV. The ratio is set by the risk-control rule (below); `VIX` data,
    when supplied, will gate the no-trade band width.
- **Asset VaR** = 1% tail of asset P&L. **Surplus VaR** = 1% tail of
  (asset - liability) P&L.
- Parametric VaR = Normal 99% (z = 2.326) on the scenario P&L; Monte-Carlo
  (`montecarlo.py`) is the fat-tail cross-check.
- Longevity is a stress line, not in the 1y HS distribution.

## Risk-control overlay (implemented)

1. unhedged **equity sleeve** 99% 1y VaR (HS, or MC for prudence)
2. vs the **economic VaR limit** derived in `derive_var_limit()` from the
   board's minimum funding ratio (1.20): `limit = assets - 1.20 x liability_PV
   - non_equity_surplus_VaR`  (cross-checked against surplus/3)
3. `HedgeRatio = max(0, 1 - limit / VaR_unhedged)`, clamped `[0,1]`
4. contracts via `Equity_MV x beta x ratio / (future_price x multiplier)`
   (`futures.py::hedge_contracts`)
5. **no-trade band +/-10%** around the limit (rule 9) to damp turnover
6. recalculate quarterly; VaR up -> add, down -> reduce, below limit -> remove
7. risk control, **not** market timing - triggered only by measured VaR vs budget

Full derivation and the recommended EUR 0.9bn limit: `VAR_METHODOLOGY.md`.

## Headline results (99% 1y, valuation 2026-09-02, full deployment EUR 10.0bn)

| | HS (primary) | Monte-Carlo (t, dof 5) |
|---|--:|--:|
| **Asset VaR** | EUR 2.59bn (26% of assets) | EUR 2.40bn |
| **Surplus VaR** | EUR 1.14bn (17% of liability) | EUR 1.71bn |
| Unhedged **equity** 99% 1y VaR | EUR 0.96bn | EUR 1.14bn |
| Derived **equity VaR limit** | EUR 0.91bn | EUR 0.31bn |
| -> futures hedge ratio | ~0% (in no-trade band) | ~73% |
| worst stress (2008 replay, surplus) | ~ -EUR 3.2bn | - |

t0 inception (FI only, EUR 5.0bn): Asset VaR EUR 1.63bn, Surplus VaR EUR 0.96bn.

**Read:** asset VaR is dominated by the long-duration FI book + equity; in
**surplus** terms the FI book and the liability offset on rates, so surplus VaR
< half the asset VaR. The equity sleeve sits **right at its risk limit** under
HS (hedge ~0), but Monte-Carlo picks up a rate-rally tail the 10y HS window
lacks, which eats the risk budget and pushes the derived equity limit down ->
~73% hedge. The real fix is the **15y vs 22y asset/liability duration
mismatch** - see `VAR_METHODOLOGY.md` sec. 3. Killer scenario: 2008 replay
(equity -45%, rates -150bp) -> surplus ~ -EUR 3.2bn.

## Outputs (`results_var/`, one set per variant tag)

`VAR_REPORT_<tag>.md` - full write-up · `scenario_pnl_<tag>.csv` - 468x P&L by
driver · `component_var_<tag>.csv` - standalone 99% loss per driver ·
`stress_tests_<tag>.csv` · `var_charts_<tag>.png` - P&L histogram + driver
tornado + stress tornado + empirical CDF.

## Open / next

- **VIX gating** - when VIX data arrives, use it to widen the no-trade band in
  calm regimes / tighten it on spikes (a `case3_var.applied_hedge_ratio` hook).
- **Asset/liability duration gap (15y vs 22y)** - the main structural finding.
  Extend FI duration or add EUR receiver swaps so the rate tail stops competing
  with the equity risk budget; then HS and MC agree on a ~EUR 1bn equity limit.
- **Credit-spread history** - govvie/SSA and HY spread risk is in the stress
  tests only; a spread time series would let HS/MC pick it up.
- **EWMA / GARCH vol** and a **filtered-HS** variant for a more responsive tail.
