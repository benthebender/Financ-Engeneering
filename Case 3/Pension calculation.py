import pandas as pd

# ============================================================
# ALL-KANNS LIFE INSURANCE
# PENSION LIABILITY MODEL
# ============================================================

# ============================================================
# 1. CASE INPUTS
# ============================================================

N_MALE = 50_000
N_FEMALE = 50_000
TOTAL_POLICYHOLDERS = N_MALE + N_FEMALE

CURRENT_AGE = 50
RETIREMENT_AGE = 65
MAX_AGE = 100

# Current accumulated amount per person
INITIAL_CAPITAL_PER_PERSON = 50_000

# Contribution paid at END of each year for 10 years
ANNUAL_CONTRIBUTION = 5_000
CONTRIBUTION_YEARS = 10

# Professor's clarification:
# Policyholders must receive at least 1% annual return
# on contributed capital.
GUARANTEED_RATE = 0.01

# Pension is paid for at least 10 years
GUARANTEE_YEARS_PENSION = 10

# ------------------------------------------------------------
# IMPORTANT:
#
# This is NOT the guaranteed rate.
#
# This is the rate used to calculate the present value
# of pension liabilities after age 65.
#
# For now you can change this for scenario analysis.
# Later, replace this with an appropriate market/EIOPA
# zero-coupon discount curve.
# ------------------------------------------------------------

VALUATION_RATE = 0.025


# ============================================================
# 2. CALCULATE GUARANTEED CAPITAL AT AGE 65
# ============================================================

YEARS_TO_RETIREMENT = (
    RETIREMENT_AGE - CURRENT_AGE
)

# ------------------------------------------------------------
# Existing EUR 50,000 grows for 15 years at 1%
# ------------------------------------------------------------

FV_INITIAL_PER_PERSON = (
    INITIAL_CAPITAL_PER_PERSON
    * (1 + GUARANTEED_RATE) ** YEARS_TO_RETIREMENT
)


# ------------------------------------------------------------
# Future contributions
#
# Contributions are made at END of Years 1-10.
#
# Therefore:
#
# Contribution at end Year 1 grows for 14 years.
# Contribution at end Year 2 grows for 13 years.
# ...
# Contribution at end Year 10 grows for 5 years.
# ------------------------------------------------------------

FV_CONTRIBUTIONS_PER_PERSON = 0

contribution_details = []

for year in range(1, CONTRIBUTION_YEARS + 1):

    years_of_growth = (
        YEARS_TO_RETIREMENT - year
    )

    future_value = (
        ANNUAL_CONTRIBUTION
        * (1 + GUARANTEED_RATE) ** years_of_growth
    )

    FV_CONTRIBUTIONS_PER_PERSON += future_value

    contribution_details.append({
        "Contribution_Year": year,
        "Contribution": ANNUAL_CONTRIBUTION,
        "Years_Growing_at_1pct": years_of_growth,
        "Value_at_65": future_value
    })


# ------------------------------------------------------------
# Total guaranteed capital per person at age 65
# ------------------------------------------------------------

GUARANTEED_CAPITAL_PER_PERSON = (
    FV_INITIAL_PER_PERSON
    + FV_CONTRIBUTIONS_PER_PERSON
)


# ------------------------------------------------------------
# Total guaranteed capital for all 100,000 people
# ------------------------------------------------------------

TOTAL_GUARANTEED_CAPITAL_AT_65 = (
    GUARANTEED_CAPITAL_PER_PERSON
    * TOTAL_POLICYHOLDERS
)


# ============================================================
# 3. LOAD GERMAN MORTALITY DATA
# ============================================================

mortality_input = pd.read_csv(
    "germany_mortality.csv"
)

mortality_input = mortality_input[
    (mortality_input["Age"] >= RETIREMENT_AGE)
    &
    (mortality_input["Age"] < MAX_AGE)
].copy()


# Check for missing ages

required_ages = set(
    range(RETIREMENT_AGE, MAX_AGE)
)

available_ages = set(
    mortality_input["Age"]
)

missing_ages = (
    required_ages - available_ages
)

if missing_ages:

    raise ValueError(
        f"Missing mortality rates for ages: "
        f"{sorted(missing_ages)}"
    )


# ============================================================
# 4. CREATE MORTALITY DICTIONARIES
# ============================================================

male_qx = dict(
    zip(
        mortality_input["Age"],
        mortality_input["Male_qx"]
    )
)

female_qx = dict(
    zip(
        mortality_input["Age"],
        mortality_input["Female_qx"]
    )
)


# ============================================================
# 5. SURVIVAL MODEL
# ============================================================

def calculate_survival(
    start_population,
    qx_by_age
):

    alive = float(start_population)

    rows = []

    for age in range(
        RETIREMENT_AGE,
        MAX_AGE
    ):

        qx = qx_by_age[age]

        expected_deaths = (
            alive * qx
        )

        alive_next_year = (
            alive - expected_deaths
        )

        rows.append({

            "Age": age,

            "Alive_Start": alive,

            "qx": qx,

            "Expected_Deaths":
                expected_deaths,

            "Alive_Next":
                alive_next_year
        })

        alive = alive_next_year

    return pd.DataFrame(rows)


male = calculate_survival(
    N_MALE,
    male_qx
)

female = calculate_survival(
    N_FEMALE,
    female_qx
)


# ============================================================
# 6. COMBINE MALE AND FEMALE POPULATIONS
# ============================================================

model = pd.DataFrame()

model["Age"] = male["Age"]

model["Year"] = (
    model["Age"]
    - RETIREMENT_AGE
    + 1
)

model["Male_Alive"] = (
    male["Alive_Start"]
)

model["Female_Alive"] = (
    female["Alive_Start"]
)

model["Male_Deaths"] = (
    male["Expected_Deaths"]
)

model["Female_Deaths"] = (
    female["Expected_Deaths"]
)

model["Total_Alive"] = (
    model["Male_Alive"]
    + model["Female_Alive"]
)

model["Total_Deaths"] = (
    model["Male_Deaths"]
    + model["Female_Deaths"]
)


# ============================================================
# 7. NUMBER OF PENSIONS PAID EACH YEAR
# ============================================================
#
# Case says:
#
# Pension is paid for AT LEAST 10 years.
#
# ASSUMPTION:
#
# If somebody dies during the first 10 years,
# guaranteed payments continue to beneficiary/estate.
#
# Therefore Years 1-10:
#
#       100,000 pension payments
#
# After Year 10:
#
#       only surviving pensioners receive payments.
# ============================================================

def pension_units(row):

    if (
        row["Year"]
        <= GUARANTEE_YEARS_PENSION
    ):

        return TOTAL_POLICYHOLDERS

    else:

        return row["Total_Alive"]


model["Pension_Units"] = (
    model.apply(
        pension_units,
        axis=1
    )
)


# ============================================================
# 8. CALCULATE ANNUAL PENSION
# ============================================================
#
# We now need to convert the guaranteed capital at 65
# into a lifetime annual pension.
#
# For this calculation we use the valuation rate.
#
# PV(expected pension payments)
# =
# guaranteed capital available at age 65
#
# ============================================================

model["Discount_Factor"] = (

    1
    /
    (1 + VALUATION_RATE)
    ** model["Year"]

)


# PV at age 65 of EUR 1 pension per pension unit

model["PV_One_Euro"] = (

    model["Pension_Units"]
    *
    model["Discount_Factor"]

)


POOL_ANNUITY_FACTOR = (
    model["PV_One_Euro"].sum()
)


# Annual pension per person

ANNUAL_PENSION_PER_PERSON = (

    TOTAL_GUARANTEED_CAPITAL_AT_65
    /
    POOL_ANNUITY_FACTOR

)


MONTHLY_PENSION_PER_PERSON = (

    ANNUAL_PENSION_PER_PERSON
    / 12

)


# ============================================================
# 9. EXPECTED PENSION CASH FLOWS
# ============================================================

model["Expected_Annual_Pension_Cashflow"] = (

    model["Pension_Units"]
    *
    ANNUAL_PENSION_PER_PERSON

)


# ============================================================
# 10. PRESENT VALUE OF EACH YEAR'S PENSION PAYMENTS
# ============================================================

model["PV_Pension_Cashflow"] = (

    model[
        "Expected_Annual_Pension_Cashflow"
    ]
    *
    model["Discount_Factor"]

)


# ============================================================
# 11. TOTAL PRESENT VALUE OF ALL PENSION PAYMENTS
# ============================================================

PV_ALL_PENSION_PAYMENTS = (

    model[
        "PV_Pension_Cashflow"
    ].sum()

)


# ============================================================
# 12. TOTAL NOMINAL EXPECTED PAYMENTS
# ============================================================
#
# This tells us how many euros the insurer expects
# to physically pay over the entire pension period,
# without discounting.
# ============================================================

TOTAL_NOMINAL_PENSION_PAYMENTS = (

    model[
        "Expected_Annual_Pension_Cashflow"
    ].sum()

)


# ============================================================
# 13. PRINT ACCUMULATION RESULTS
# ============================================================

print("\n" + "=" * 70)

print(
    "ALL-KANNS LIFE INSURANCE - "
    "PENSION LIABILITY MODEL"
)

print("=" * 70)


print("\nACCUMULATION PHASE")

print("-" * 70)


print(
    f"Initial capital per person: "
    f"EUR {INITIAL_CAPITAL_PER_PERSON:,.2f}"
)


print(
    f"Guaranteed annual return: "
    f"{GUARANTEED_RATE * 100:.2f}%"
)


print(
    f"Value of initial EUR 50,000 "
    f"at age 65: "
    f"EUR {FV_INITIAL_PER_PERSON:,.2f}"
)


print(
    f"Value at 65 of ten "
    f"EUR 5,000 contributions: "
    f"EUR {FV_CONTRIBUTIONS_PER_PERSON:,.2f}"
)


print(
    f"\nGuaranteed capital per person "
    f"at age 65: "
    f"EUR {GUARANTEED_CAPITAL_PER_PERSON:,.2f}"
)


print(
    f"Total guaranteed capital "
    f"at age 65: "
    f"EUR {TOTAL_GUARANTEED_CAPITAL_AT_65:,.2f}"
)


# ============================================================
# 14. PRINT PENSION RESULTS
# ============================================================

print("\n" + "-" * 70)

print("PENSION PHASE")

print("-" * 70)


print(
    f"Valuation rate used after age 65: "
    f"{VALUATION_RATE * 100:.2f}%"
)


print(
    f"\nAnnual pension per person: "
    f"EUR {ANNUAL_PENSION_PER_PERSON:,.2f}"
)


print(
    f"Monthly pension per person: "
    f"EUR {MONTHLY_PENSION_PER_PERSON:,.2f}"
)


print(
    f"\nPV at age 65 of all expected "
    f"pension payments: "
    f"EUR {PV_ALL_PENSION_PAYMENTS:,.2f}"
)


print(
    f"Total expected nominal pension "
    f"payments over lifetime: "
    f"EUR {TOTAL_NOMINAL_PENSION_PAYMENTS:,.2f}"
)


# ============================================================
# 15. CHECK
# ============================================================

print("\n" + "-" * 70)

print("MODEL CHECK")

print("-" * 70)


print(
    f"Guaranteed capital at age 65: "
    f"EUR {TOTAL_GUARANTEED_CAPITAL_AT_65:,.2f}"
)


print(
    f"PV of pension payments: "
    f"EUR {PV_ALL_PENSION_PAYMENTS:,.2f}"
)


print(
    f"Difference: "
    f"EUR "
    f"{PV_ALL_PENSION_PAYMENTS - TOTAL_GUARANTEED_CAPITAL_AT_65:,.2f}"
)


# ============================================================
# 16. PRINT CASH FLOW TABLE
# ============================================================

output_columns = [

    "Year",

    "Age",

    "Male_Alive",

    "Female_Alive",

    "Total_Alive",

    "Total_Deaths",

    "Pension_Units",

    "Expected_Annual_Pension_Cashflow",

    "Discount_Factor",

    "PV_Pension_Cashflow"

]


print("\n" + "=" * 70)

print(
    "EXPECTED PENSION LIABILITY CASH FLOWS"
)

print("=" * 70 + "\n")


print(

    model[output_columns]

    .round(2)

    .to_string(index=False)

)


# ============================================================
# 17. EXPORT RESULTS TO EXCEL
# ============================================================

model[
    output_columns
].to_excel(

    "pension_liability_results.xlsx",

    index=False

)


pd.DataFrame(
    contribution_details
).to_excel(

    "contribution_accumulation.xlsx",

    index=False

)


print(
    "\nResults saved to:"
)

print(
    "pension_liability_results.xlsx"
)

print(
    "contribution_accumulation.xlsx"
)