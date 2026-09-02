# `case3_model.py` - one unified Case 3b model

Merges the logic of `case3_var.py` + `montecarlo.py` + `vix.py` + `futures.py`
+ `fx.py` into a single self-contained file. Consumes the two teammate outputs
(`results/fixed_income_portfolio.csv`, `portfolio_optimization_final.xlsx`) and
does everything downstream.

```bash
python case3_model.py                 # HS suite (unhedged / rule-overlay / t0) + MC
python case3_model.py hs full auto    # one HS run, rule-based hedge
python case3_model.py hs full 0.30    # one HS run, hedge pinned at 30%
python case3_model.py mc full 25000   # Monte-Carlo, 25k paths
```

## Structure (16 sections, top to bottom)

| # | section | what it does |
|--:|---|---|
| 1 | **Config** | case + model params + the **funding waterfall** (t=0: €5.0bn → FI; t=1..10: €0.5bn/yr → return book) |
| 2 | **Data loading** | Bloomberg-Excel EUR/USD swap-curve & EURUSD history (weekday date repair, raw/1e7 & raw/1e4), 14-index weekly history, return weights, FI portfolio CSV |
| 3 | **Curve** | annual par-swap bootstrap → zero curve; log-linear DF; flat-forward beyond 30y |
| 4 | **Guaranteed liability** | accumulated value at yr 15 (`50k·1.01^15 + Σ 5k·1.01^(15-t)`)×100k; CF = **50% lump @ yr15 + 50% pension yr16..50** |
| 5 | **Book assembly** | FI 5.0bn (16 bonds) + return book = 10×€0.5bn at Aggressive_Diversified; sleeve currency/kind tags (EUR vs USD; EQUITY / HY / RATES_CREDIT) |
| 6 | **FX swap** | CIP forward, hedge carry, rate-diff coefficient — every USD sleeve rolled to EUR (HKD leg ignored) |
| 7 | **Equity-index future** | cost-of-carry `F = S·e^{(r−q)τ}`, MTM, carry, `hedge_contracts()` = `−ratio·β·EquityMV/(price·mult)` (short) |
| 8 | **VIX / Heston** | `dv = κ(θ−v)dt + ξ√v dW^v`, `corr(dW^S,dW^v)=ρ`; analytic `VIX_t² = (A(τ)v_t + (1−A)θ)·100²`, `A(τ)=(1−e^{−κτ})/(κτ)`; weekly full-truncation Euler |
| 9 | **Risk-factor panel + HS scenarios** | aligned weekly factor moves → 52-week **overlapping** windows → ~468 annual scenarios |
| 10 | **Repricing engine** | bonds: mod-duration+convexity on shifted curve · liability: full reval · sleeves: own-currency total return · FX: rate-diff residual · futures: short MSCI World proxy |
| 11 | **VaR stats** | historical VaR/ES + parametric (Normal, z=2.326) |
| 12 | **Risk-control overlay** | `derive_var_limit` (funding-ratio floor → economic equity VaR limit) → `target_hedge_ratio = max(0, 1 − limit/VaR)` → `vix_gated_band` no-trade band → `resolve_overlay` |
| 13 | **Stress tests** | rates ±100/200, equity −20/−30/−40, HY +300bp, 2022 & 2008 replays, longevity +1y |
| 14 | **Monte Carlo** | shrunk-correlation multivariate Student-t (dof 5) weekly innovations, EUR curve via 3 PCs, Heston VIX layer, soft/hard tail guardrails, reprice with the same engine |
| 15 | **Reports + charts** | `run_hs()` and `run_mc()` → `HS_REPORT_*.md` / `MC_REPORT_*.md` + `*_charts_*.png` + `scenario_pnl_*.csv` / `component_var_*.csv` / `stress_tests_*.csv` in `results_var/` |
| 16 | **Orchestrator** | `run_all()` = 3 HS variants + 1 MC |

## Reported

- **Asset VaR** (asset P&L) and **Surplus VaR** (assets − guaranteed liability PV), 1-year 99%, HS + MC + parametric
- driver decomposition, deterministic stresses, the overlay decision (limit, unhedged equity VaR, hedge ratio), VIX diagnostics

## Headline (full deployment, €10.0bn, valuation 2026-09-02)

| | HS | MC (Student-t 5 + Heston VIX) |
|---|--:|--:|
| Asset VaR | €2.54bn | €2.40bn |
| Surplus VaR | €1.13bn | €1.71bn |
| equity VaR limit / unhedged equity VaR | €0.91bn / €0.96bn | €0.31bn / €1.41bn |
| → futures hedge ratio | ~6% (in band ⇒ ~0) | ~78% |

The old five modules still work and are unchanged; `case3_model.py` supersedes
them as the single entry point.
