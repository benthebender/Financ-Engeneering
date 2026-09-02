# Case 3b - combined book & 1-year 99.5% VaR

Ties the two sub-books into one portfolio and runs Historical-Simulation VaR
(priority 1), plus a parametric cross-check and deterministic stress tests.

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
python case3_var.py                 # full suite: full / t0 / full+50% equity hedge
python case3_var.py full 0.30       # one run: full deployment, 30% futures hedge
python case3_var.py t0              # inception snapshot
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
  - **Futures overlay** - short MSCI World proxy, notional = hedge_ratio x equity
    MV; ratio is a config knob (the VIX/threshold rule lives elsewhere).
- **Asset VaR** = 0.5% tail of asset P&L. **Surplus VaR** = 0.5% tail of
  (asset - liability) P&L.
- Parametric VaR = Normal 99.5% (z = 2.576) on the scenario P&L.
- Longevity is a stress line, not in the 1y HS distribution.

## Headline results (valuation 2026-09-02)

| variant | assets | funding ratio | **Asset VaR** | **Surplus VaR** |
|---|--:|--:|--:|--:|
| full (5bn FI + 5bn return) | EUR 10.0bn | 1.47 | EUR 2,700m  (27% of assets) | EUR 1,185m  (17% of liability) |
| t0 inception (FI only) | EUR 5.0bn | 0.73 | EUR 1,677m  (34%) | EUR 970m |
| full + 50% equity futures hedge | EUR 10.0bn | 1.47 | EUR 2,237m | EUR 1,105m |

Historical ES runs ~3-7% above VaR; parametric surplus VaR is ~35% higher than
HS (fat left tail with only ~470 scenarios - flag this in the deck).

**Read:** asset VaR is dominated by the long-duration FI book and equity; but in
**surplus** terms the FI book and the liability offset on rates, so surplus VaR
(~EUR 1.2bn) is < half the asset VaR and is driven by equity + the imperfect
rate match + FX. The killer scenario is the **2008 replay** (equity -45% with
rates -150bp -> liability balloons): surplus P&L ~ -EUR 3.2bn. A 50% equity
futures hedge cuts asset VaR ~17% but surplus VaR only ~7% (it only touches
equity).

## Outputs (`results_var/`, one set per variant tag)

`VAR_REPORT_<tag>.md` - full write-up · `scenario_pnl_<tag>.csv` - 468x P&L by
driver · `component_var_<tag>.csv` - standalone 99.5% loss per driver ·
`stress_tests_<tag>.csv` · `var_charts_<tag>.png` - P&L histogram + driver
tornado + stress tornado + empirical CDF.

## Open / next

- **Futures hedge rule** - `case3_var.py` takes `future_hedge_ratio`; the
  VIX-threshold logic that sets it is with the strategy team. `futures.py` has
  the pricing + `hedge_contracts()` sizing.
- **Credit-spread history** - govvie/SSA and HY spread risk is in the stress
  tests only; a spread time series would let HS pick it up.
- **Data** - 99.5% / 1y from ~470 overlapping weekly windows is thin in the
  tail; consider a filtered-HS (EWMA vol) or block-bootstrap variant.
