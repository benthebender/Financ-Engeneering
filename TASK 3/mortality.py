"""
mortality.py
============

Annual death count and survivor count for a closed pension cohort, using a
**Normal distribution for age at death**.

Cohort (from the brief)
-----------------------
* 100,000 lives, all currently **age 50**
* 50 % male   - mean age at death **79.02**
* 50 % female - mean age at death **83.00**
* age at death  T ~ Normal(mu_sex, sd_sex), conditioned on  T > 50
  (everyone in the cohort is alive today, so we truncate the left tail)

The plan starts paying at **age 65** (15 years from now) and runs to ~120, one
payment per surviving life per year. For every year of age from 65 to `max_age`
this module returns

    l_x   survivors at exact age x    -> number of annuity payments due that year
    d_x   deaths during [x, x+1)      -> the "dying rate per year" (a count)
    q_x   d_x / l_x                   -> the annual mortality rate (a probability)

Feed `survivors_per_year()` (the l_x column) into the next step to build the
expected pension cash flows and match a bond portfolio to them.

Note on the standard deviation
------------------------------
The brief gives only the means. `sd_male` / `sd_female` are therefore explicit
parameters (default **12.0 years** each). Smaller sd -> deaths bunch near the
mean; larger sd -> fatter tails and a longer-lived tail of pensioners. The
`summary()` output prints life expectancy at 65 and the share reaching 65 so you
can calibrate sd to a real mortality table if you have one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

__all__ = [
    "CohortSpec",
    "life_table",
    "mortality_table",
    "deaths_per_year",
    "survivors_per_year",
    "expected_annuity_payments",
    "summary",
]


# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CohortSpec:
    n_total: int = 100_000
    male_fraction: float = 0.50
    mean_male: float = 79.02
    mean_female: float = 83.00
    sd_male: float = 12.0
    sd_female: float = 12.0
    current_age: int = 50           # age of the cohort today
    payout_age: int = 65            # first pension payment
    max_age: int = 120              # table runs to here
    close_out: bool = True          # force every remaining life dead by max_age

    def __post_init__(self) -> None:
        if not 0.0 < self.male_fraction < 1.0:
            raise ValueError("male_fraction must be in (0, 1)")
        if not self.current_age < self.payout_age < self.max_age:
            raise ValueError("need current_age < payout_age < max_age")
        if self.sd_male <= 0 or self.sd_female <= 0:
            raise ValueError("standard deviations must be > 0")

    @property
    def n_male(self) -> int:
        return int(round(self.n_total * self.male_fraction))

    @property
    def n_female(self) -> int:
        return self.n_total - self.n_male


# --------------------------------------------------------------------------- #
def _lx(n: int, mu: float, sd: float, ages: np.ndarray, age0: int) -> np.ndarray:
    """Survivors at each exact age: n * P(T > x | T > age0)."""
    return n * norm.sf(ages, mu, sd) / norm.sf(age0, mu, sd)


def life_table(spec: CohortSpec | None = None) -> pd.DataFrame:
    """Full life table from `current_age` to `max_age`, indexed by exact age.

    Columns (``_male`` / ``_female`` / ``_total``):
        alive_start   survivors at the start of the year of age x  (= l_x)
        deaths        deaths during [x, x+1)                       (= d_x)
        alive_end     survivors at x+1
    plus `t_years_from_now`, `pension_year` (age - payout_age),
    `mortality_rate_qx`, `survival_rate_px`, and per-sex `qx_*`.
    """
    spec = spec or CohortSpec()
    ages = np.arange(spec.current_age, spec.max_age + 1)

    lx_m = _lx(spec.n_male, spec.mean_male, spec.sd_male, ages, spec.current_age)
    lx_f = _lx(spec.n_female, spec.mean_female, spec.sd_female, ages, spec.current_age)

    def deaths(lx: np.ndarray) -> np.ndarray:
        d = lx[:-1] - lx[1:]
        tail = lx[-1] if spec.close_out else 0.0
        return np.append(d, tail)

    dx_m, dx_f = deaths(lx_m), deaths(lx_f)

    end_m = lx_m - dx_m
    end_f = lx_f - dx_f

    df = pd.DataFrame(
        {
            "age": ages,
            "t_years_from_now": ages - spec.current_age,
            "pension_year": ages - spec.payout_age,
            "alive_start_male": lx_m,
            "alive_start_female": lx_f,
            "alive_start_total": lx_m + lx_f,
            "deaths_male": dx_m,
            "deaths_female": dx_f,
            "deaths_total": dx_m + dx_f,
            "alive_end_male": end_m,
            "alive_end_female": end_f,
            "alive_end_total": end_m + end_f,
        }
    ).set_index("age")

    with np.errstate(invalid="ignore", divide="ignore"):
        df["mortality_rate_qx"] = df["deaths_total"] / df["alive_start_total"]
        df["survival_rate_px"] = 1.0 - df["mortality_rate_qx"]
        df["qx_male"] = df["deaths_male"] / df["alive_start_male"]
        df["qx_female"] = df["deaths_female"] / df["alive_start_female"]
    return df


def mortality_table(spec: CohortSpec | None = None) -> pd.DataFrame:
    """`life_table` sliced to the payout window (age `payout_age` .. `max_age`)."""
    spec = spec or CohortSpec()
    return life_table(spec).loc[spec.payout_age :].copy()


def deaths_per_year(spec: CohortSpec | None = None) -> pd.Series:
    """The headline: deaths in each year of age from `payout_age` to `max_age`."""
    s = mortality_table(spec)["deaths_total"].rename("deaths")
    s.index.name = "age"
    return s


def survivors_per_year(spec: CohortSpec | None = None) -> pd.Series:
    """Survivors at the start of each year = annuity payments due that year."""
    s = mortality_table(spec)["alive_start_total"].rename("survivors")
    s.index.name = "age"
    return s


def expected_annuity_payments(
    spec: CohortSpec | None = None,
    amount_per_year: float = 1.0,
    timing: str = "advance",
) -> pd.Series:
    """Expected pension outgo per year (undiscounted).

    ``timing="advance"`` pays every life alive at the start of the year (l_x);
    ``timing="arrears"`` pays every life that survives to the year end (l_x+1).
    Multiply the discounted sum of this series by the annuity factor to size the
    liability; index is exact age, from `payout_age`.
    """
    lt = mortality_table(spec)
    col = "alive_start_total" if timing == "advance" else "alive_end_total"
    return (amount_per_year * lt[col]).rename("expected_payment")


def summary(spec: CohortSpec | None = None) -> dict:
    spec = spec or CohortSpec()
    lt = life_table(spec)
    l_pay = float(lt.loc[spec.payout_age, "alive_start_total"])
    l_pay_m = float(lt.loc[spec.payout_age, "alive_start_male"])
    l_pay_f = float(lt.loc[spec.payout_age, "alive_start_female"])

    # curtate life expectancy at the payout age: sum of survivors beyond it / l
    tail = lt.loc[spec.payout_age + 1 :, "alive_start_total"].sum()
    tail_m = lt.loc[spec.payout_age + 1 :, "alive_start_male"].sum()
    tail_f = lt.loc[spec.payout_age + 1 :, "alive_start_female"].sum()

    deaths = mortality_table(spec)["deaths_total"]
    peak_age = int(deaths.idxmax())

    return {
        "cohort_now": spec.n_total,
        "reach_payout_age_total": l_pay,
        "reach_payout_age_pct": 100.0 * l_pay / spec.n_total,
        "reach_payout_age_pct_male": 100.0 * l_pay_m / spec.n_male,
        "reach_payout_age_pct_female": 100.0 * l_pay_f / spec.n_female,
        "life_expectancy_at_payout_total": tail / l_pay + 0.5,
        "life_expectancy_at_payout_male": tail_m / l_pay_m + 0.5,
        "life_expectancy_at_payout_female": tail_f / l_pay_f + 0.5,
        "expected_annuity_years_per_life": tail / l_pay + 1.0,   # incl. the payout year
        "expected_total_annuity_years": float(
            mortality_table(spec)["alive_start_total"].sum()
        ),
        "peak_death_age": peak_age,
        "peak_death_count": float(deaths.loc[peak_age]),
        "last_survivors_at_max_age": float(
            life_table(spec).loc[spec.max_age, "alive_start_total"]
        ),
    }


# --------------------------------------------------------------------------- #
def plot_mortality(spec: CohortSpec | None = None):
    """Two stacked panels: survivors (line) and deaths per year (stacked bars)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    spec = spec or CohortSpec()
    lt = mortality_table(spec)
    age = lt.index.to_numpy()

    C_M, C_F = "#0072B2", "#E69F00"          # colour-blind-safe (male / female)
    C_INK, C_GRID, C_MUT = "#1A1A1A", "#E6E6E6", "#6B6B6B"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.4), sharex=True)

    ax1.plot(age, lt["alive_start_male"], color=C_M, lw=2.4, label="male")
    ax1.plot(age, lt["alive_start_female"], color=C_F, lw=2.4, label="female")
    ax1.plot(age, lt["alive_start_total"], color=C_INK, lw=1.6, ls=(0, (5, 3)),
             label="total")
    ax1.set_ylabel("survivors at start of year\n(= annuity payments due)")
    ax1.set_title(f"Pension cohort of {spec.n_total:,} lives — survivors and "
                  f"deaths per year, age {spec.payout_age}–{spec.max_age}",
                  fontsize=14, fontweight="bold")
    ax1.legend(frameon=False, loc="upper right")

    ax2.bar(age, lt["deaths_male"], color=C_M, width=0.9, label="male")
    ax2.bar(age, lt["deaths_female"], bottom=lt["deaths_male"], color=C_F,
            width=0.9, label="female")
    ax2.set_ylabel("deaths during the year")
    ax2.set_xlabel("age")
    ax2.legend(frameon=False, loc="upper right")
    for mu, c, lbl, dy in ((spec.mean_male, C_M, "mean M", -12),
                           (spec.mean_female, C_F, "mean F", -26)):
        ax2.axvline(mu, color=c, lw=1, ls=":")
        ax2.annotate(f"{lbl} {mu:g}", xy=(mu, ax2.get_ylim()[1]),
                     xytext=(4, dy), textcoords="offset points",
                     fontsize=9, color=c)

    for ax in (ax1, ax2):
        ax.grid(axis="y", color=C_GRID, lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)

    fig.text(0.01, 0.01,
             f"age at death ~ Normal(mu, sd);  mu = {spec.mean_male:g} (M) / "
             f"{spec.mean_female:g} (F),  sd = {spec.sd_male:g} / {spec.sd_female:g};  "
             f"conditioned on alive at {spec.current_age}",
             fontsize=8.5, color=C_MUT)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


# --------------------------------------------------------------------------- #
def _write_outputs(spec: CohortSpec, out_dir) -> None:
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lt = mortality_table(spec)
    lt.round(4).to_csv(out_dir / "mortality_table.csv")
    life_table(spec).round(4).to_csv(out_dir / "life_table_full.csv")

    s = summary(spec)
    lines = ["# Mortality model summary", ""]
    lines += [f"{k:38s} : {v:,.4f}" if isinstance(v, float) else f"{k:38s} : {v}"
              for k, v in s.items()]
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n")

    fig = plot_mortality(spec)
    fig.savefig(out_dir / "mortality_deaths_and_survivors.png", bbox_inches="tight")

    print(f"wrote to {out_dir}/:")
    for f in ("mortality_table.csv", "life_table_full.csv", "summary.txt",
              "mortality_deaths_and_survivors.png"):
        print(f"  {f}")


if __name__ == "__main__":
    from pathlib import Path

    spec = CohortSpec()
    lt = mortality_table(spec)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 80)
    pd.set_option("display.float_format", lambda v: f"{v:,.3f}")

    print(f"Cohort: {spec.n_total:,} lives now aged {spec.current_age} "
          f"({spec.n_male:,} M @ mean {spec.mean_male}, "
          f"{spec.n_female:,} F @ mean {spec.mean_female}); "
          f"sd = {spec.sd_male}/{spec.sd_female}\n")

    print("Summary")
    for k, v in summary(spec).items():
        print(f"  {k:38s} : {v:,.3f}" if isinstance(v, float) else f"  {k:38s} : {v}")

    print("\nMortality table  age 65 .. 120  (head / tail)")
    show = ["pension_year", "alive_start_total", "deaths_total",
            "deaths_male", "deaths_female", "mortality_rate_qx"]
    print(lt[show].head(20).to_string())
    print("  ...")
    print(lt[show].tail(15).to_string())

    _write_outputs(spec, Path(__file__).resolve().parent / "outputs")
