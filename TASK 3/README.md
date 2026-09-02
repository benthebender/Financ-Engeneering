# TASK 3 — mortality model for the pension cohort

`mortality.py` turns a **Normal distribution of age at death** into the annual
death count and survivor count of a closed pension cohort — the demographic
input for the next step (expected pension cash flows → matched bond portfolio).

## The cohort (from the brief)

| | |
|---|---|
| lives today | 100,000, all currently **age 50** |
| male | 50 % — mean age at death **79.02** |
| female | 50 % — mean age at death **83.00** |
| age at death | `T ~ Normal(mu_sex, sd_sex)`, conditioned on `T > 50` |
| payout starts | **age 65** (15 years from now) |
| table runs to | age **120** (`close_out=True` ⇒ every remaining life dies in the last year, no tail leakage) |

The brief gives only the means, so **`sd_male` / `sd_female` are explicit
parameters** (default **12.0 years**). Smaller sd ⇒ deaths bunch near the mean;
larger sd ⇒ a longer-lived tail of pensioners. `summary()` prints life
expectancy at 65 and the share reaching 65 so you can calibrate sd to a real
table.

## Run

```bash
python mortality.py        # prints the table + summary, writes outputs/
python -m pytest -q        # 10 sanity checks
```

## API

```python
from mortality import CohortSpec, mortality_table, deaths_per_year, survivors_per_year

spec = CohortSpec(sd_male=12.0, sd_female=12.0)      # tweak as needed
mt   = mortality_table(spec)          # DataFrame, age 65..120, indexed by exact age
deaths_per_year(spec)                 # Series: deaths in each year of age  (the "dying rate")
survivors_per_year(spec)              # Series: lives alive at each age = annuity payments due
expected_annuity_payments(spec, amount_per_year=1.0, timing="advance")
```

`mortality_table` columns (`_male` / `_female` / `_total`):

| column | meaning |
|---|---|
| `pension_year` | age − 65 (0 at first payment) |
| `alive_start_*` | `l_x` — survivors at the start of the year → **payments due that year** |
| `deaths_*` | `d_x` — deaths during `[x, x+1)` → the dying rate per year |
| `alive_end_*` | `l_x+1` |
| `mortality_rate_qx` | `d_x / l_x` — annual probability of death |
| `survival_rate_px` | `1 − q_x` |

## Outputs (`outputs/`)

| file | contents |
|---|---|
| `mortality_table.csv` | the payout-window table, age 65–120 |
| `life_table_full.csv` | the full table from age 50 (includes the 50→65 run-off) |
| `summary.txt` | share reaching 65, life expectancy at 65, peak death age, expected annuity-years |
| `mortality_deaths_and_survivors.png` | survivors (line) + deaths per year (stacked M/F bars) |

## Headline results (default sd = 12)

| | value |
|---|---:|
| reach age 65 | 91,077 (91.1 %) — M 88.6 %, F 93.6 % |
| life expectancy at 65 | 18.3 y total (M 16.8, F 19.7) |
| peak death age | 81 (~3,290 deaths that year) |
| expected total annuity-years (Σ survivors, age 65→120) | ≈ 1,708,490 |

## Next step

Discount `survivors_per_year(spec) × annual_pension` back to today (15-year
deferral + in-payment years), sum to the liability value, then match a bond
portfolio's cash flows / duration to that survivor-weighted schedule.
