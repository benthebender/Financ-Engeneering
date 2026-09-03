# `case3_model.py` - one unified Case 3b model

Merges the logic of `case3_var.py` + `montecarlo.py` + `vix.py` + `futures.py`
+ `fx.py` into a single self-contained file. Consumes
`results_v2/portfolio_wide.csv` (the cash-flow-dedicated two-stage FI book from
`cashflow_match_v2.py` - Stage 1 dedicates the cash flows, Stage 2 shapes the
key-rate DV01) and `portfolio_optimization_final.xlsx` (return-book weights), and
does everything downstream.  (The older `results/fixed_income_portfolio.csv` from
`alm_fixed_income_.py` is a soft-CF + DV01 least-squares book, not dedicated.)

```bash
python case3_model.py                 # HS suite (unhedged / overlay / t0 / projected) + MC
python case3_model.py hs full auto    # one HS run, rule-based hedge
python case3_model.py hs full 0.30    # one HS run, hedge pinned at 30%
python case3_model.py hs full auto projected   # return book from the annual profit-share path
python case3_model.py                 # ... also emits the `full_irs` tag (receive-fixed swap overlay)
python case3_model.py mc full 25000   # Monte-Carlo, 25k paths
python case3_model.py returnbook      # annual rebalance + 90/10 profit-share projection
```

## Return book: annual rebalancing + profit sharing (`return_book.py`)

At each year end: grow each sleeve by its yearly return, add the contribution
tranche (EUR 0.5bn, years 1-10), then rebalance to the Aggressive Diversified
weights.  **Profit sharing only from year 15** (`profit_share_start_year`, when
benefits begin): years 1-14 the whole investment return compounds in the book,
un-shared; from year 15 on, 90 % of each year's investment profit (return-driven,
contributions excluded, loss carry-forward) is paid to policyholders - funded by
**selling an equal EUR amount from every one of the 14 sleeves** - and 10 % is
retained and left invested.

- **Deployed return-book size** (what `case3_model` uses when
  `return_book_mode="projected"`): the **year-10, pre-sharing MV = EUR 8.39bn**
  (contributions EUR 5.00bn fully compounded over the accumulation phase).
- Payout phase (years 15-20, deterministic-return projection): cumulative
  policyholder share ~EUR 7.8bn, insurer retained ~EUR 0.9bn, book ~EUR 13.6bn
  at year 20.  The 90 % is a pass-through off the insurer's asset side.
- `Config(return_book_mode="projected")`: assets EUR 10.0 -> **EUR 13.4bn**
  (equity sleeve EUR 7.7bn), HS Asset VaR ~EUR 3.22bn, Surplus VaR ~EUR 1.42bn.
  The default `return_book_mode="sum"` keeps the conservative flat "10 x 0.5bn"
  = EUR 5.0bn return book for the headline VaR.

## Receive-fixed IRS overlay (`Config.irs_receiver`)

`irs_receiver=((15.0, 2.8e9), (30.0, 0.3e9))` bolts a par receive-fixed swap
overlay onto the FI book to close the residual asset/liability duration gap the
cash bond book cannot reach under the 15 % instrument cap (mostly the year-15
lump-sum bucket).  **No cash outlay** - a par swap has PV zero at inception and
the notional is not exchanged, so it sits on top of the fully-invested EUR 5bn
bond book (only variation margin).  `irs_receiver_mtm()` reprices the swap MTM,
`N * (s0 * A - (1 - DF(T)))`, on every HS scenario / MC path / stress curve and
adds it to asset P&L (`irs_hedge` component).  The notional per tenor is sized
by `cashflow_match_v2.size_irs()` (NNLS of receiver-swap key-rate DV01 onto the
Stage-2 residual gap).  Effect (full deployment HS, unhedged equity, on the
cash-flow-dedicated FI book): Surplus VaR EUR 1,214m -> **EUR 845m** (-30 %);
Asset VaR EUR 2,513m -> 3,449m (up, as expected - the swap adds rate duration on
the asset side, which does not threaten the cash-flow match); 2008-replay
surplus EUR -3,279m -> **-2,603m**.  `run_all()` emits it as the `full_irs` tag.

## Structure (16 sections, top to bottom)

| # | section | what it does |
|--:|---|---|
| 1 | **Config** | case + model params + the **funding waterfall** (t=0: €5.0bn → FI; t=1..10: €0.5bn/yr → return book) |
| 2 | **Data loading** | Bloomberg-Excel EUR/USD swap-curve & EURUSD history (weekday date repair, raw/1e7 & raw/1e4), 14-index weekly history, return weights, FI portfolio CSV |
| 3 | **Curve** | annual par-swap bootstrap → zero curve; log-linear DF; flat-forward beyond 30y |
| 4 | **Guaranteed liability** | accumulated value at yr 15 (`50k·1.01^15 + Σ 5k·1.01^(15-t)`)×100k; CF = **50% lump @ yr15 + 50% pension yr16..50** |
| 5 | **Book assembly** | FI 5.0bn (11 bonds, cash-flow-dedicated `results_v2/portfolio_wide.csv`) + return book = 10×€0.5bn at Aggressive_Diversified; sleeve currency/kind tags (EUR vs USD; EQUITY / HY / RATES_CREDIT) |
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
| 16 | **Orchestrator** | `run_all()` = 5 HS variants (unhedged / overlay / t0 / projected return book / **IRS overlay**) + 1 MC |

## Reported

- **Asset VaR** (asset P&L) and **Surplus VaR** (assets − guaranteed liability PV), 1-year 99%, HS + MC + parametric
- driver decomposition, deterministic stresses, the overlay decision (limit, unhedged equity VaR, hedge ratio), VIX diagnostics

## Headline (full deployment, €10.0bn, valuation 2026-09-02, CF-dedicated FI book)

| | HS | MC (Student-t 5 + Heston VIX) |
|---|--:|--:|
| Asset VaR | €2.51bn | €2.29bn |
| Surplus VaR (unhedged) | €1.21bn | €1.81bn |
| Surplus VaR (+ receiver IRS) | €0.85bn | - |
| equity VaR limit / unhedged equity VaR | €0.83bn / €0.96bn | €0.21bn / €1.44bn |
| → futures hedge ratio | ~14% | ~85% |

The old five modules still work and are unchanged; `case3_model.py` supersedes
them as the single entry point.
