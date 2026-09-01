# Callable-bond engine — data, formulas, assumptions, limitations

Reference sheet for the par-coupon engine in this folder. Cross-referenced to
the code in `curve_io.py`, `engine.py`, `pricer.py`.

---

## 1. Data used

| input | source | notes |
|-------|--------|-------|
| EUR par swap rates, tenors **1Y–10Y** | `Data/Swap curves.xlsx` (sheet `Sheet1`) via `swap_curves.load_swap_curves()` | quoted in percent; each tenor independently dated; history ≈ 2015-11 → 2026-08 (~2800 rows) |
| curve **date** | one row of that sheet | default = latest date on which **all 10** tenors are quoted (currently 2026-08-31); `--curve-date YYYY-MM-DD` picks any historical date (falls back to the last quote on/before it) |
| **volatility** | **user input**, `--vol` (default `0.15`) | *not* from data — no historical-vol calibration, no swaption surface |
| **mean reversion** `a` | **user input**, `--mean-reversion` (default `0.03`) | not calibrated |
| call structure | `CallableSpec` / CLI / `spec.yaml` | maturity, nc period, single/Bermudan, call price, explicit schedule |

Only the 10 annual nodes are consumed. Nothing else from the workbook (no
EURIBOR sheet, no intraday, no basis).

---

## 2. Formulas

### 2.1 Discount curve (`forward_swap.bootstrap_discount_curve`)

Annual par-swap rates `rₖ` → discount factors by iterative bootstrap (annual
fixed leg, `τ = 1`):

```
DFᵢ = (1 − rᵢ · Σ_{k<i} DFₖ) / (1 + rᵢ)
```

* missing annual nodes ≤ 10Y: **linear interpolation on the par rate** before
  bootstrapping;
* between nodes: **log-linear interpolation of DF** (⇒ piecewise-constant
  instantaneous forward);
* beyond the last node: flat-forward extrapolation (unused here — maturity ≤ 10Y).

### 2.2 Bullet par coupon (`engine.bullet_par_coupon`) — analytic, no model

```
c_bullet(M) = (1 − P(0,M)) / Σₖ τₖ P(0,tₖ)          = the M-year par swap rate
```

### 2.3 Hull-White 1-factor (`engine.HullWhiteEngine`)

Short rate `r(t) = x(t) + α(t)`, `dx = −a·x·dt + σ·dW`. Priced on Hull's
two-stage **trinomial tree**:

* `Δt = 1/steps_per_year` (default 1/12), `Δx = σ·√(3Δt)`, `M = −a·Δt`,
  `j_max = ⌈0.184 / (a·Δt)⌉`;
* branch probabilities — standard Hull formulas, three regimes
  (interior node, top edge `j = j_max`, bottom edge `j = −j_max`), e.g. interior:
  `pᵤ = 1/6 + (j²M² + jM)/2`, `pₘ = 2/3 − j²M²`, `p_d = 1/6 + (j²M² − jM)/2`;
* **stage 2 fit:** `αᵢ` solved by forward induction of Arrow–Debreu prices `Q`
  so that `Σⱼ Q[i,j]·e^{−(αᵢ + jΔx)Δt} = P(0,(i+1)Δt)` for every slice.
  `fit_error = maxₖ |Σⱼ Q[k,j] − P(0,kΔt)|` is asserted `< 1e-8`.

**Vol resolution:**
`vol_type="black"` (default) → `σ_abs = vol · r_ref` with `r_ref` = the
M-year par swap rate (at-the-money normal↔lognormal identity, `σ_N ≈ σ_LN·F`).
`vol_type="normal"` → `σ_abs = vol` directly. `sigma_abs=` pins it.

### 2.4 Callable bond — backward induction (`HullWhiteEngine.price`)

Face 100, annual coupon cash `= c·100·τ`.

```
maturity node :  V = 100 + coupon
roll back     :  V = disc · E[V_next]          (+ coupon on coupon nodes)
call year     :  V = coupon + min(call_price, disc · E[V_next])
t = 0         :  price = disc · E[V₁]
```

`disc` at node `(i,j)` is `e^{−(αᵢ + jΔx)Δt}`; `E[·]` uses the branch
probabilities. The `min(call_price, ·)` is the issuer redeeming whenever the
**ex-coupon continuation value exceeds the call price**.

**Par coupon:** `brentq` root of `price(c) − 100 = 0`; the bracket auto-expands
to negative coupons for negative-rate curves.
**Single-call ladder:** price each candidate year `nc … M−1` as its own
one-date exercise set; the reported best is the max par coupon.

### 2.5 Black cross-check (`engine.BlackEngine`) — European, single call only

```
callable(c)      = straight(c) − receiver_swaption(c)
straight(c)      = c·100·Σₖ P(0,tₖ) + 100·P(0,M)
s_fwd            = (P(0,Tc) − P(0,M)) / Σ_{Tc<tₖ≤M} P(0,tₖ)
receiver_swaption = A·100·[ c·Φ(−d₂) − s_fwd·Φ(−d₁) ]
d₁ = [ln(s_fwd/c) + ½σ²Tc] / (σ√Tc),   d₂ = d₁ − σ√Tc
```

Requires `s_fwd > 0` and `c > 0` (lognormal); raises otherwise.

---

## 3. Assumptions embedded

**Cash-flow / structure**
* Annual coupons only — `COUPON_FREQ = 1`; `coupon_schedule()` raises for
  `freq ≠ 1`. 30/360, accrual exactly `1.0`. (`coupon_schedule` is a list so
  semi-annual is a later change of schedule, not of maths.)
* Call dates are **integer years** and a **subset of coupon dates**.
* Call is **cum-coupon**: on a call year the issuer pays that year's coupon
  *and* redeems at the call price.
* Redemption at maturity is **100 (par)**, independent of `call_price`.
* Bond starts today (spot start, `t = 0`); prices are quoted on coupon dates
  (no clean/dirty split beyond the cum-coupon convention).

**Exercise**
* Issuer exercises **optimally and frictionlessly**: no notice period, no
  transaction or refinancing cost, no issuer-behaviour/credit friction. Pure
  "call iff continuation value > call price".
* Bermudan exercise only on the **annual** candidate dates (not continuous).

**Curve / discounting**
* **Single curve** — one curve both discounts and forecasts. No OIS/EURIBOR
  basis. **No issuer credit spread**: the bond is discounted on the swap curve,
  so the "par coupon" is a *swap-equivalent / asset-swap* par coupon, not a real
  new-issue yield.
* Curve interpolation is log-linear in DF ⇒ piecewise-flat forwards, small
  kinks between annual nodes.
* Maturity ≤ longest curve tenor; no extrapolation (warns at exactly 10Y).

**Model**
* Hull-White **1-factor**, **constant** `σ` and **constant** `a`; no term
  structure of vol, no smile/skew, no calibration to traded swaptions.
* Gaussian short rate — rates may go arbitrarily negative in the model.
* `vol_type="black"` applies one at-the-money scaling `σ_abs ≈ vol·r_ref` with a
  **single** `r_ref` (the M-year rate) for the whole tree.
* A vol *term structure* passed as `vols` is linearly interpolated in maturity;
  a scalar is applied to every maturity.

---

## 4. Limitations

* **Not calibrated.** Outputs move with the hand-set `a`, `vol`, `vol_type`;
  they are not marked to traded swaption prices. Treat spreads as
  indicative / comparative, not executable.
* **Discretisation.** Default 12 steps/year. *Same-tree* comparisons are exact
  to root-finder tolerance (Bermudan ≥ best single; `nc = M−1` ⇒ single ≡
  Bermudan; ladder monotonicity on an upward curve). *Cross-engine* HW-vs-Black
  agreement is only ≈ 5–25 bp because the vol mapping is approximate.
* **Ladder front end.** On an upward curve the ladder is monotone decreasing
  *from its peak*; with `nc = 1` the ≈1y first call has negligible option
  time-value, so the peak sits at year 2–3. Both engines agree — it is real,
  not a tree artefact.
* **Negative-rate curves.** HW works (`vol_type="normal"` required; the default
  black scaling collapses near `r_ref ≈ 0` and warns). The Black engine refuses
  (lognormal).
* **Single factor.** No curve-twist / steepener component in the option value;
  one Brownian driver.
* **No calendar / day-count / settlement.** "Years" are exact integers.
* **Performance.** Pure-Python backward induction per root-finder step — fine
  for grids of tens of structures, not for large batch runs.
* `--config` requires PyYAML.
* `pytest` is needed only for the test suite, not for the engine.
