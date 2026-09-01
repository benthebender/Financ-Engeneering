# CALLABLE BOND 7yrNCx

Par-coupon engine for callable bonds. Nothing is hardcoded to 7y NC2 — that is
just the default. Given a swap curve, a volatility and an option engine, it
solves for the coupon that makes the bond price at par (100 per 100 face) and
reports the spread over the equivalent bullet.

## Files

| file | what it is |
|------|------------|
| `curve_io.py` | finds `Swap curves.xlsx` / `swap_curves.py` / `forward_swap.py` in the repo, loads one curve date, bootstraps a `DiscountCurve` |
| `engine.py` | `HullWhiteEngine` (fitted trinomial tree, any exercise set) and `BlackEngine` (closed-form European cross-check, single call only) |
| `pricer.py` | `CallableSpec`, `ParCouponResult`, `par_coupon`, `call_ladder`, `compare_structures` |
| `scenarios.py` | curve sensitivity / scenario analysis — issuer P&L, call value, effective duration & convexity, key-rate DV01 |
| `plots.py` | presentation PNG charts of the sensitivity analysis (matplotlib) |
| `main.py` | CLI over a grid of structures, plus `--config spec.yaml`, `--scenarios`, `--plots` |
| `spec.example.yaml` | example config: a list of `CallableSpec` dicts |
| `tests/` | validation suite (`pip install pytest`, then `pytest`) |
| `ASSUMPTIONS.md` | data / formulas / assumptions / limitations reference |

## Model

A callable bond = straight bond − the issuer's call. The issuer calls on a
call date when the ex-coupon continuation value of the remaining bond exceeds
the call price, so on the lattice

```
V = coupon + min(call_price, discounted E[V_next])      on a call date
V = coupon + discounted E[V_next]                        otherwise
```

with `V = 100 + coupon` at maturity. `par_coupon` root-finds the coupon that
brings `V(0)` to 100.

* **Engine `hw`** — Hull-White one-factor on Hull's two-stage trinomial tree
  (stage 1: symmetric `x`-tree with mean reversion `a`; stage 2: shift each
  time slice by `α_i` so the tree reprices the input discount curve). The tree
  depends only on the curve, `a`, `σ` and the horizon — not the coupon — so it
  is built once and reused across every candidate call date and every
  root-finder step. Prices single-call and Bermudan from the *same* lattice, so
  the two stay consistent.
* **Engine `black`** — `callable = straight − receiver swaption`, the receiver
  swaption by Black's lognormal formula on the forward swap rate. European only
  (single call); raises for Bermudan. Used as an independent cross-check.

### Volatility input

`--vol` is a **Black (lognormal) implied vol** by default (`--vol-type black`).
For Hull-White it is converted to an absolute short-rate vol with the
at-the-money normal↔lognormal identity `σ_abs ≈ vol · r_ref`, where `r_ref` is
the maturity-year par swap rate. Pass `--vol-type normal` to feed an absolute
short-rate vol straight in, or `sigma_abs=` in code to pin it.

## Curve input

The curve is the real one already in the repo. `curve_io.py` locates
`swap_curves.py` on `sys.path` and calls its `load_swap_curves()` — the same
loader (and the same `Data/Swap curves.xlsx`) the rest of the project uses — then
`forward_swap.bootstrap_discount_curve` turns one date's 1Y–10Y par rates into
the `DiscountCurve`. `main.py` prints the resolved workbook path and the exact
observation date it used.

```bash
python main.py                              # latest fully-quoted date
python main.py --curve-date 2020-03-18      # any historical date in the sheet
python main.py --curve-file /path/to/Swap curves.xlsx
```

Negative-rate curves (e.g. EUR in 2020) work: the par-coupon solver brackets
negative coupons. The default `--vol-type black` scaling `σ_abs ≈ vol·r_ref`
collapses when `r_ref` is near zero (it warns) — pass `--vol-type normal` with an
absolute short-rate vol there.

## CLI

```bash
python main.py                                             # 7y NC2, vol 0.15, hw
python main.py --maturities 5 7 10 --nc 1 2 3 --vol 0.15 --engine hw
python main.py --config spec.example.yaml
python main.py --maturities 7 --nc 2 --out results/        # also write CSVs
```

For every `(maturity, nc)` pair it prints the single-call ladder (par coupon for
a one-off call at each candidate year `nc … maturity-1`), the best single call,
the Bermudan (all those years exercisable), and the spread of each over that
maturity's bullet.

## Curve sensitivity / scenario analysis (`scenarios.py`)

Answers "how much does the issuer (Vonovia) benefit / lose if rates fall 100 bp,
rise, flatten, steepen, bulge in the belly …". Every shock is **basis points on
the par swap rate per tenor**, then the curve is re-bootstrapped.

```bash
python main.py --scenarios --maturities 7 --nc 2 --notional 500000000
python main.py --scenarios --struck-coupon 350   # value an existing 3.50% bond
```

Three tables per structure (Bermudan):

* **Scenario table** — for each shock: repriced par coupon and `Δ` vs base, the
  spread over bullet, the mark-to-market of the outstanding liability, the
  embedded **call value**, and

  ```
  issuer_pnl        = base_liability_value − scenario_liability_value   (>0 = gain)
  call_contribution = issuer_pnl − bullet_pnl
                    = how much being callable rather than bullet helped
  ```

  On a **rally** the call moves in the money, `call_value` jumps and
  `call_contribution > 0` — the call caps how far the liability can appreciate.
  On a **sell-off** the call decays and `call_contribution < 0` (the premium
  paid up front is wasted).
* **Effective duration / convexity** — parallel ±25 bp finite differences. The
  callable shows the classic signature: **shorter effective duration** and
  **negative convexity** vs the bullet.
* **Key-rate DV01** — money per +1 bp at each curve node (central difference,
  default 10 bp bump). The bullet profile is smooth and sums to its effective
  DV01; the callable profile is front-loaded and lumpy around the call dates
  (real, but the lattice amplifies it — treat as indicative).

```python
from scenarios import scenario_analysis, effective_risk, key_rate_dv01, parallel, bull_flattener
df = scenario_analysis(rates, 0.15, CallableSpec(7, 2, "bermudan"),
                       scenarios=[parallel(-100), parallel(+100), bull_flattener(100)],
                       notional=500_000_000)
```

Default scenario set: unchanged, parallel ±50/±100/±200, bull-flattener 100,
bear-steepener 100, 2s10s steepener/flattener 50, mid-curve bulge ±50. Build
your own with `parallel`, `twist`, `steepener`, `flattener`, `bull_flattener`,
`bear_steepener`, `belly`, `custom`.

## Charts for a presentation (`plots.py`)

```bash
python main.py --plots --notional 500000000 --out charts
python main.py --plots --struck-coupon 350 --maturities 7 10 --nc 2 1
```

Writes five PNGs (150 dpi, slide-sized, colour-blind-safe) plus the two CSVs
behind them:

| file | shows |
|------|-------|
| `pnl_vs_shift__*.png` | issuer P&L on the liability, callable vs bullet, across a −200…+200 bp parallel move — the asymmetry / negative convexity |
| `call_value__*.png` | value of the embedded call vs the parallel move |
| `scenario_bars__*.png` | "callable − bullet" benefit per named scenario (the impact of different hikes / falls) |
| `par_coupon__*.png` | funding cost (par coupon) vs the parallel move, bullet as reference |
| `dashboard__*.png` | all four on one 2×2 slide |

```python
from plots import compute_sensitivity, pnl_vs_shift, scenario_bars, save_all
d = compute_sensitivity(rates, 0.15, CallableSpec(7, 2, "bermudan"), notional=5e8)
fig = pnl_vs_shift(d); fig.savefig("headline.png", bbox_inches="tight")
```

The struck coupon defaults to the base-curve par coupon (bond assumed issued at
par today), so base P&L is zero and every bar is a clean "vs today" delta.
`charts/` is git-ignored.

## Library use

```python
from curve_io import load_par_rates, build_discount_curve
from pricer import CallableSpec, par_coupon, call_ladder, compare_structures

curve = build_discount_curve(load_par_rates())

res = par_coupon(curve, 0.15, CallableSpec(7, 2, "single"), "hw")
print(res.summary())
res.call_ladder          # DataFrame: par coupon for a single call at each year
res.par_coupon           # best single-call par coupon (decimal)
res.spread_bp            # over the 7y bullet

# escape hatch: an explicit, irregular schedule ignores nc_period/call_type
compare_structures(curve, 0.15, [
    CallableSpec(7, 2, "single"),
    CallableSpec(7, 2, "bermudan"),
    CallableSpec(10, 1, "bermudan", call_price=101.0),
    CallableSpec(10, 1, "single", call_schedule=[3, 5, 7]),
], "hw")
```

`CallableSpec` validates on construction: `1 ≤ nc_period < maturity`,
`call_type ∈ {single, bermudan}`, `call_price > 0`, and `call_schedule` entries
strictly inside `(0, maturity)` with no duplicates. `maturity ≤ longest curve
tenor` is checked when a curve is supplied (it refuses to extrapolate the curve
to price the bond), and `maturity == longest tenor` warns.

## Validated properties (`tests/`)

* bullet par coupon **==** the M-year par swap rate, for every M on the curve
* the tree reprices the input curve (`fit_error < 1e-8`) and every solve returns
  price 100
* **Bermudan par coupon ≥ best single-call par coupon** for any `(M, nc)`, on
  upward / flat / inverted curves
* `nc_period == maturity-1` ⇒ single and Bermudan coincide (one exercise date)
* an explicit `call_schedule=[d]` reproduces the ladder entry at `d`
* a call price above par lowers the coupon
* **ladder monotone decreasing in call date on an upward-sloping curve** —
  asserted curve-conditionally. With ≥ 2y of call protection the peak is the
  earliest call date, so the whole ladder is monotone. With `nc == 1` the first
  candidate is ~1y out and carries almost no option time-value, so the peak
  slips to year 2–3; the ladder is monotone *after* the peak. Both engines agree
  on this, so it is a genuine effect, not a tree artifact.
* construction-time validation raises with clear messages; `maturity > curve`
  raises, `maturity == curve` warns

## Conventions

Annual coupons, 30/360 (accrual 1.0). The coupon schedule is an explicit list
(`engine.coupon_schedule`), so semi-annual is a later change of schedule, not a
rewrite — `freq != 1` currently raises `NotImplementedError` on purpose. Face
100; coupons and rates are decimals. Single-curve valuation (one discount =
forecast curve), fine for a teaching study.
