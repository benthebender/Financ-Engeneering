# =============================================================================
# VONOVIA SE — INTEREST-RATE VALUE AT RISK
# MAIN ANALYSIS
# =============================================================================
#
# PURPOSE
# -------
# Analyse Vonovia SE's interest-rate risk from a Present Value (PV)
# perspective using:
#
#   A. Monte Carlo / historical covariance simulation
#   B. Delta-Normal VaR
#   C. PCA + GARCH-based simulation
#
# IMPORTANT DATA PRINCIPLE
# ------------------------
# The model uses supplied Bloomberg / Vonovia data wherever available.
#
# It DOES NOT invent:
#
#   - Vonovia bond maturities
#   - coupons
#   - fixed/floating split
#   - derivatives
#   - duration
#   - DV01
#
# If portfolio sensitivity is unavailable, market-risk calibration is
# completed but monetary Vonovia VaR remains explicitly on HOLD.
#
# =============================================================================


# =============================================================================
# 1. IMPORT LIBRARIES
# =============================================================================

from pathlib import Path
import math
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("default")


# =============================================================================
# 2. MODEL SETTINGS
# =============================================================================

CONFIDENCE_LEVEL = 0.95

VAR_HORIZON_DAYS = 10

N_SIMULATIONS = 100_000

RANDOM_SEED = 42

REPORTING_CURRENCY = "EUR"


# 95% one-tailed standard-normal critical value.
#
# This avoids requiring scipy.

Z_95 = 1.6448536269514722


# Reproducible random-number generator.

rng = np.random.default_rng(
    RANDOM_SEED
)


# =============================================================================
# 3. PROJECT DIRECTORIES
# =============================================================================
#
# The script should be run from:
#
# Financial Engineering/
#
# Example:
#
# Financial Engineering/
#
#     Version 2.py
#     Swap Curve EURIBOR.xlsx
#
#     output/
#
# =============================================================================

PROJECT_DIR = Path.cwd()

OUTPUT_DIR = (
    PROJECT_DIR
    / "output"
)

CLEAN_DIR = (
    OUTPUT_DIR
    / "cleaned_data"
)

TABLE_DIR = (
    OUTPUT_DIR
    / "tables"
)

CHART_DIR = (
    OUTPUT_DIR
    / "charts"
)

RESULT_DIR = (
    OUTPUT_DIR
    / "results"
)

DIAGNOSTIC_DIR = (
    OUTPUT_DIR
    / "diagnostics"
)


for folder in [

    OUTPUT_DIR,
    CLEAN_DIR,
    TABLE_DIR,
    CHART_DIR,
    RESULT_DIR,
    DIAGNOSTIC_DIR

]:

    folder.mkdir(
        parents=True,
        exist_ok=True
    )


# =============================================================================
# 4. FILE LOCATIONS
# =============================================================================

RATE_FILE = (
    PROJECT_DIR
    / "Swap Curve EURIBOR.xlsx"
)


# =============================================================================
# 5. DATA-GAP AND ASSUMPTION REGISTERS
# =============================================================================

data_gaps = []

assumptions = []


def register_gap(
    item,
    reason
):

    data_gaps.append({

        "Missing Information":
            item,

        "Why It Matters":
            reason

    })


def register_assumption(
    item,
    assumption,
    reason
):

    assumptions.append({

        "Item":
            item,

        "Assumption":
            assumption,

        "Reason":
            reason

    })


# =============================================================================
# 6. INTRODUCTION
# =============================================================================

print("\n")
print("=" * 80)

print(
    "VONOVIA SE — INTEREST-RATE VALUE AT RISK"
)

print("=" * 80)


print(
    f"Working folder:       {PROJECT_DIR}"
)

print(
    f"Risk type:            Interest-rate risk — PV perspective"
)

print(
    f"VaR horizon:          {VAR_HORIZON_DAYS} trading days"
)

print(
    f"Confidence level:     {CONFIDENCE_LEVEL:.0%}"
)

print(
    f"Monte Carlo runs:     {N_SIMULATIONS:,}"
)

print(
    f"Reporting currency:   {REPORTING_CURRENCY}"
)


# =============================================================================
# 7. VONOVIA DEBT DATA AVAILABLE
# =============================================================================
#
# Source:
#
# Supplied Bloomberg Capital Structure screenshot.
#
#
# Identified debt:
#
# 1st Lien Secured Loans          EUR 3,499.40m
#
# Senior Unsecured Loans          EUR   150.00m
#
# Senior Unsecured Bonds          EUR 26,678.46m
#
# Senior Unsecured Schuldschein   EUR 1,060.00m
#
#
# IMPORTANT:
#
# These are aggregate debt amounts.
#
# The supplied data do NOT provide enough information to identify:
#
#   individual bond maturities
#
#   individual coupons
#
#   fixed/floating status
#
#   reset frequency
#
#   duration
#
#   DV01
#
#   interest-rate derivative positions
#
# =============================================================================


vonovia_debt = pd.DataFrame({

    "Instrument Type": [

        "1st Lien Secured Loans",

        "Senior Unsecured Loans",

        "Senior Unsecured Bonds",

        "Senior Unsecured Schuldschein"

    ],

    "Side": [

        "Liability",

        "Liability",

        "Liability",

        "Liability"

    ],

    "Outstanding EUR m": [

        3499.40,

        150.00,

        26678.46,

        1060.00

    ],

    "Fixed/Floating": [

        "Unknown",

        "Unknown",

        "Unknown",

        "Unknown"

    ],

    "Maturity": [

        "Unknown",

        "Unknown",

        "Unknown",

        "Unknown"

    ],

    "Coupon/Reference Rate": [

        "Unknown",

        "Unknown",

        "Unknown",

        "Unknown"

    ],

    "Source": [

        "Bloomberg Capital Structure",

        "Bloomberg Capital Structure",

        "Bloomberg Capital Structure",

        "Bloomberg Capital Structure"

    ]

})


vonovia_debt[
    "Outstanding EUR"
] = (

    vonovia_debt[
        "Outstanding EUR m"
    ]

    * 1_000_000

)


TOTAL_DEBT = (

    vonovia_debt[
        "Outstanding EUR"
    ].sum()

)


vonovia_debt[
    "Portfolio Weight"
] = (

    vonovia_debt[
        "Outstanding EUR"
    ]

    / TOTAL_DEBT

)


print("\n")
print("=" * 80)

print(
    "1. VONOVIA IDENTIFIED DEBT"
)

print("=" * 80)


print(

    vonovia_debt[
        [
            "Instrument Type",
            "Outstanding EUR m",
            "Portfolio Weight"
        ]
    ].to_string(
        index=False
    )

)


print(
    f"\nTotal identified debt: "
    f"EUR {TOTAL_DEBT / 1e9:,.3f}bn"
)


vonovia_debt.to_csv(

    TABLE_DIR
    / "vonovia_debt_structure.csv",

    index=False

)


# =============================================================================
# 8. OTHER AVAILABLE BALANCE-SHEET INFORMATION
# =============================================================================
#
# Supplied Bloomberg financial analysis:
#
# 2025:
#
# Cash & Near Cash:
#
#       EUR 3,256.9m
#
#
# Other Investments:
#
#       EUR 3,427.2m
#
#
# We DO NOT automatically include these in interest-rate VaR.
#
# Their maturity/duration/instrument composition is not supplied.
#
# =============================================================================


balance_sheet_reference = pd.DataFrame({

    "Item": [

        "Cash & Near Cash",

        "Other Investments"

    ],

    "2025 EUR m": [

        3256.9,

        3427.2

    ],

    "Included in IR VaR": [

        "No",

        "No"

    ],

    "Reason": [

        (
            "Interest-rate sensitivity "
            "not sufficiently identified"
        ),

        (
            "Duration and instrument "
            "composition unavailable"
        )

    ]

})


print("\n")
print("=" * 80)

print(
    "2. OTHER AVAILABLE BALANCE-SHEET INFORMATION"
)

print("=" * 80)


print(

    balance_sheet_reference.to_string(
        index=False
    )

)


balance_sheet_reference.to_csv(

    TABLE_DIR
    / "balance_sheet_reference.csv",

    index=False

)


# =============================================================================
# 9. REGISTER KNOWN VONOVIA DATA GAPS
# =============================================================================


register_gap(

    "Fixed/floating debt split",

    (
        "Fixed and floating debt have "
        "different interest-rate sensitivity."
    )

)


register_gap(

    "Debt maturity profile",

    (
        "Maturity determines duration and "
        "exposure to individual curve nodes."
    )

)


register_gap(

    "Debt coupons",

    (
        "Coupons are required for exact "
        "cash-flow valuation."
    )

)


register_gap(

    "Duration / DV01",

    (
        "Required to translate rate movements "
        "into Vonovia PV movements."
    )

)


register_gap(

    "Interest-rate derivatives",

    (
        "Swaps and other hedges could materially "
        "change net interest-rate exposure."
    )

)


# =============================================================================
# 10. VONOVIA DEBT CHART
# =============================================================================


fig, ax = plt.subplots(

    figsize=(10, 6)

)


ax.bar(

    vonovia_debt[
        "Instrument Type"
    ],

    vonovia_debt[
        "Outstanding EUR m"
    ]

)


ax.set_title(

    "Vonovia Identified Debt Structure"

)


ax.set_ylabel(

    "Outstanding Debt (EUR millions)"

)


ax.tick_params(

    axis="x",

    rotation=30

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "vonovia_debt_structure.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 11. CHECK INTEREST-RATE FILE
# =============================================================================


print("\n")
print("=" * 80)

print(
    "3. EURIBOR SWAP CURVE DATA"
)

print("=" * 80)


if not RATE_FILE.exists():

    raise FileNotFoundError(

        f"Could not find:\n"
        f"{RATE_FILE}"

    )


print(

    "Historical Bloomberg file found:"

)

print(

    RATE_FILE

)


# =============================================================================
# 12. LOAD ACTUAL BLOOMBERG WORKBOOK
# =============================================================================
#
# ACTUAL FILE STRUCTURE FOUND DURING INSPECTION:
#
#
# Column 0  = weekday
#
# Column 1  = date
#
# Column 2  = 10Y
#
# Column 4  = 9Y
#
# Column 6  = 8Y
#
# Column 8  = 7Y
#
# Column 10 = 6Y
#
# Column 12 = 5Y
#
# Column 14 = 4Y
#
# Column 16 = 3Y
#
# Column 18 = 2Y
#
# Column 20 = 1Y
#
#
# Odd columns 3,5,7,...19 are empty.
#
# =============================================================================


raw_rates = pd.read_excel(

    RATE_FILE,

    sheet_name="Sheet1",

    header=None

)


print(

    "\nRaw Bloomberg dimensions:"

)

print(

    f"{raw_rates.shape[0]} rows x "
    f"{raw_rates.shape[1]} columns"

)


# =============================================================================
# 13. EXTRACT ACTUAL RATE COLUMNS
# =============================================================================


rates = raw_rates[
    [
        1,      # Date

        2,      # 10Y

        4,      # 9Y

        6,      # 8Y

        8,      # 7Y

        10,     # 6Y

        12,     # 5Y

        14,     # 4Y

        16,     # 3Y

        18,     # 2Y

        20      # 1Y
    ]
].copy()


rates.columns = [

    "Date",

    "10Y",

    "9Y",

    "8Y",

    "7Y",

    "6Y",

    "5Y",

    "4Y",

    "3Y",

    "2Y",

    "1Y"

]


# =============================================================================
# 14. CLEAN DATE COLUMN
# =============================================================================
#
# Bloomberg contains:
#
#   - maturity header row
#
#   - blank weekly separator rows
#
# Both disappear when invalid dates are removed.
#
# =============================================================================


rates[
    "Date"
] = pd.to_datetime(

    rates[
        "Date"
    ],

    errors="coerce"

)


rates = rates.dropna(

    subset=[
        "Date"
    ]

)


# =============================================================================
# 15. CONVERT RATE COLUMNS TO NUMERIC
# =============================================================================


ALL_RATE_COLUMNS = [

    "1Y",

    "2Y",

    "3Y",

    "4Y",

    "5Y",

    "6Y",

    "7Y",

    "8Y",

    "9Y",

    "10Y"

]


for column in (

    ALL_RATE_COLUMNS

):

    rates[
        column
    ] = pd.to_numeric(

        rates[
            column
        ],

        errors="coerce"

    )


# =============================================================================
# 16. SORT CHRONOLOGICALLY
# =============================================================================
#
# Bloomberg file is newest first.
#
# We need oldest -> newest before calculating changes.
#
# =============================================================================


rates = (

    rates
    .drop_duplicates(
        subset=[
            "Date"
        ]
    )
    .sort_values(
        "Date"
    )
    .set_index(
        "Date"
    )

)


# =============================================================================
# 17. DATA AVAILABILITY BY MATURITY
# =============================================================================


availability = pd.DataFrame({

    "Observations":

        rates[
            ALL_RATE_COLUMNS
        ].count(),

    "Missing":

        rates[
            ALL_RATE_COLUMNS
        ].isna().sum(),

    "Coverage %":

        (
            rates[
                ALL_RATE_COLUMNS
            ]
            .notna()
            .mean()
            * 100
        )

})


print("\n")
print("=" * 80)

print(
    "4. DATA AVAILABILITY BY MATURITY"
)

print("=" * 80)


print(

    availability.round(
        2
    ).to_string()

)


availability.to_csv(

    TABLE_DIR
    / "rate_data_availability.csv"

)


# =============================================================================
# 18. SELECT ROBUST RISK FACTORS
# =============================================================================
#
# ACTUAL BLOOMBERG AVAILABILITY:
#
# 9Y ~ 258 observations
#
# 6Y ~ 257 observations
#
#
# Most other maturities:
#
# ~2,560 observations
#
#
# Including 6Y and 9Y would destroy most of the 10-year sample.
#
# Therefore exclude:
#
#       6Y
#
#       9Y
#
#
# Main VaR factors:
#
#       1Y
#       2Y
#       3Y
#       4Y
#       5Y
#       7Y
#       8Y
#       10Y
#
# =============================================================================


RISK_FACTOR_NODES = [

    "1Y",

    "2Y",

    "3Y",

    "4Y",

    "5Y",

    "7Y",

    "8Y",

    "10Y"

]


EXCLUDED_NODES = [

    "6Y",

    "9Y"

]


print(

    "\nRisk factors selected:"

)

print(

    RISK_FACTOR_NODES

)


print(

    "\nExcluded sparse maturities:"

)

print(

    EXCLUDED_NODES

)


# =============================================================================
# 19. BUILD CALIBRATION DATASET
# =============================================================================


calibration_rates_percent = (

    rates[
        RISK_FACTOR_NODES
    ]
    .dropna(
        how="any"
    )
    .copy()

)


# =============================================================================
# 20. CONVERT BLOOMBERG RATES TO DECIMAL
# =============================================================================
#
# Bloomberg:
#
#       3.34915
#
# means:
#
#       3.34915%
#
#
# Model:
#
#       0.0334915
#
# =============================================================================


calibration_rates = (

    calibration_rates_percent

    / 100

)


register_assumption(

    "Interest-rate units",

    (
        "Bloomberg swap rates divided by 100"
    ),

    (
        "The supplied Bloomberg workbook "
        "quotes rates in percentage points."
    )

)


# =============================================================================
# 21. SAVE CLEAN RATE DATA
# =============================================================================


calibration_rates_percent.to_csv(

    CLEAN_DIR
    / "euribor_swap_curve_percent.csv"

)


calibration_rates.to_csv(

    CLEAN_DIR
    / "euribor_swap_curve_decimal.csv"

)


# =============================================================================
# 22. CALIBRATION PERIOD
# =============================================================================


START_DATE = (

    calibration_rates
    .index
    .min()

)


END_DATE = (

    calibration_rates
    .index
    .max()

)


NUMBER_OF_OBSERVATIONS = (

    len(
        calibration_rates
    )

)


print("\n")
print("=" * 80)

print(
    "5. CALIBRATION SAMPLE"
)

print("=" * 80)


print(

    f"Start date:       "
    f"{START_DATE.date()}"

)


print(

    f"End date:         "
    f"{END_DATE.date()}"

)


print(

    f"Observations:     "
    f"{NUMBER_OF_OBSERVATIONS:,}"

)


print(

    f"Risk factors:     "
    f"{', '.join(RISK_FACTOR_NODES)}"

)


# =============================================================================
# 23. DATA QUALITY SUMMARY
# =============================================================================


data_quality_summary = pd.DataFrame({

    "Metric": [

        "Raw Excel rows",

        "Valid dated observations",

        "Calibration observations",

        "Calibration start",

        "Calibration end",

        "Risk factors",

        "Excluded sparse maturities"

    ],

    "Value": [

        len(
            raw_rates
        ),

        len(
            rates
        ),

        NUMBER_OF_OBSERVATIONS,

        START_DATE.date(),

        END_DATE.date(),

        ", ".join(
            RISK_FACTOR_NODES
        ),

        ", ".join(
            EXCLUDED_NODES
        )

    ]

})


print("\n")
print(
    data_quality_summary.to_string(
        index=False
    )
)


data_quality_summary.to_csv(

    TABLE_DIR
    / "data_quality_summary.csv",

    index=False

)


# =============================================================================
# 24. CURRENT EURIBOR SWAP CURVE
# =============================================================================
#
# Latest observation in supplied dataset.
#
# =============================================================================


current_curve = (

    calibration_rates
    .iloc[-1]
    .copy()

)


current_curve_percent = (

    current_curve

    * 100

)


current_curve_table = pd.DataFrame({

    "Maturity":

        current_curve.index,

    "Swap Rate %":

        current_curve_percent.values

})


print("\n")
print("=" * 80)

print(
    "6. CURRENT EURIBOR SWAP CURVE"
)

print("=" * 80)


print(

    current_curve_table.to_string(
        index=False
    )

)


current_curve_table.to_csv(

    TABLE_DIR
    / "current_euribor_swap_curve.csv",

    index=False

)


# =============================================================================
# 25. CURRENT CURVE CHART
# =============================================================================


fig, ax = plt.subplots(

    figsize=(9, 5)

)


ax.plot(

    current_curve.index,

    current_curve.values
    * 100,

    marker="o"

)


ax.set_title(

    f"EURIBOR Swap Curve — "
    f"{END_DATE.date()}"

)


ax.set_xlabel(

    "Maturity"

)


ax.set_ylabel(

    "Swap Rate (%)"

)


ax.grid(

    alpha=0.25

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "current_euribor_swap_curve.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 26. CALCULATE DAILY RATE CHANGES
# =============================================================================
#
# Absolute changes:
#
#       Delta r(t)
#
#       =
#
#       r(t)
#
#       -
#
#       r(t-1)
#
#
# Example:
#
# 3.00% -> 3.05%
#
# = +5 basis points
#
# =============================================================================


daily_changes = (

    calibration_rates
    .diff()
    .dropna()

)


daily_changes_bp = (

    daily_changes

    * 10_000

)


daily_changes.to_csv(

    CLEAN_DIR
    / "daily_rate_changes_decimal.csv"

)


daily_changes_bp.to_csv(

    CLEAN_DIR
    / "daily_rate_changes_basis_points.csv"

)


# =============================================================================
# 27. VOLATILITY
# =============================================================================


daily_volatility = (

    daily_changes
    .std()

)


daily_volatility_bp = (

    daily_volatility

    * 10_000

)


ten_day_volatility_bp = (

    daily_volatility_bp

    * np.sqrt(
        VAR_HORIZON_DAYS
    )

)


volatility_table = pd.DataFrame({

    "Daily Volatility bp":

        daily_volatility_bp,

    "10-Day Volatility bp":

        ten_day_volatility_bp

})


print("\n")
print("=" * 80)

print(
    "7. HISTORICAL INTEREST-RATE VOLATILITY"
)

print("=" * 80)


print(

    volatility_table.round(
        3
    ).to_string()

)


volatility_table.to_csv(

    TABLE_DIR
    / "interest_rate_volatility.csv"

)


# =============================================================================
# 28. VOLATILITY CHART
# =============================================================================


fig, ax = plt.subplots(

    figsize=(9, 5)

)


ax.bar(

    volatility_table.index,

    volatility_table[
        "10-Day Volatility bp"
    ]

)


ax.set_title(

    "10-Day EUR Swap-Rate Volatility"

)


ax.set_xlabel(

    "Maturity"

)


ax.set_ylabel(

    "Volatility (basis points)"

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "ten_day_rate_volatility.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 29. COVARIANCE
# =============================================================================


daily_covariance = (

    daily_changes
    .cov()

)


ten_day_covariance = (

    daily_covariance

    * VAR_HORIZON_DAYS

)


daily_covariance.to_csv(

    TABLE_DIR
    / "daily_covariance_matrix.csv"

)


ten_day_covariance.to_csv(

    TABLE_DIR
    / "ten_day_covariance_matrix.csv"

)


# =============================================================================
# 30. CORRELATION
# =============================================================================


correlation = (

    daily_changes
    .corr()

)


print("\n")
print("=" * 80)

print(
    "8. INTEREST-RATE CORRELATION"
)

print("=" * 80)


print(

    correlation.round(
        3
    ).to_string()

)


correlation.to_csv(

    TABLE_DIR
    / "interest_rate_correlation.csv"

)


# =============================================================================
# 31. CORRELATION HEATMAP
# =============================================================================


fig, ax = plt.subplots(

    figsize=(9, 8)

)


image = ax.imshow(

    correlation.values,

    aspect="auto"

)


ax.set_xticks(

    range(
        len(
            RISK_FACTOR_NODES
        )
    )

)


ax.set_yticks(

    range(
        len(
            RISK_FACTOR_NODES
        )
    )

)


ax.set_xticklabels(

    RISK_FACTOR_NODES,

    rotation=45,

    ha="right"

)


ax.set_yticklabels(

    RISK_FACTOR_NODES

)


for i in range(

    len(
        RISK_FACTOR_NODES
    )

):

    for j in range(

        len(
            RISK_FACTOR_NODES
        )

    ):

        ax.text(

            j,

            i,

            f"{correlation.iloc[i, j]:.2f}",

            ha="center",

            va="center",

            fontsize=8

        )


ax.set_title(

    "Correlation of Daily EUR Swap-Rate Changes"

)


fig.colorbar(

    image,

    ax=ax

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "interest_rate_correlation_heatmap.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 32. HISTORICAL RATE CHART
# =============================================================================


fig, ax = plt.subplots(

    figsize=(12, 7)

)


for maturity in (

    RISK_FACTOR_NODES

):

    ax.plot(

        calibration_rates.index,

        calibration_rates[
            maturity
        ]
        * 100,

        label=maturity,

        linewidth=1

    )


ax.set_title(

    "Historical EURIBOR Swap Rates"

)


ax.set_xlabel(

    "Date"

)


ax.set_ylabel(

    "Swap Rate (%)"

)


ax.legend(

    ncol=2

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "historical_euribor_swap_rates.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 33. COVARIANCE DIAGNOSTICS
# =============================================================================


def covariance_diagnostics(
    covariance
):

    matrix = np.asarray(

        covariance,

        dtype=float

    )


    eigenvalues = (

        np.linalg.eigvalsh(
            matrix
        )

    )


    return {

        "Minimum Eigenvalue":

            float(
                eigenvalues.min()
            ),

        "Maximum Eigenvalue":

            float(
                eigenvalues.max()
            ),

        "Positive Semidefinite":

            bool(
                eigenvalues.min()
                >= -1e-12
            ),

        "Condition Number":

            float(
                np.linalg.cond(
                    matrix
                )
            )

    }


covariance_check = (

    covariance_diagnostics(
        daily_covariance
    )

)


covariance_check_df = (

    pd.DataFrame(
        [covariance_check]
    )

)


print("\n")
print("=" * 80)

print(
    "9. COVARIANCE DIAGNOSTICS"
)

print("=" * 80)


print(

    covariance_check_df.to_string(
        index=False
    )

)


covariance_check_df.to_csv(

    DIAGNOSTIC_DIR
    / "covariance_diagnostics.csv",

    index=False

)


# =============================================================================
# 34. MONTE CARLO — GENERATE 100,000 10-DAY CURVE SHOCKS
# =============================================================================
#
# Model:
#
#       Delta r
#
#       ~
#
#       Multivariate Normal(
#
#           0,
#
#           Sigma_10day
#
#       )
#
#
# Historical covariance captures:
#
#   - volatility
#
#   - correlation
#
#   - curve co-movement
#
# =============================================================================


mean_shock = np.zeros(

    len(
        RISK_FACTOR_NODES
    )

)


monte_carlo_shocks = (

    rng.multivariate_normal(

        mean=mean_shock,

        cov=ten_day_covariance.values,

        size=N_SIMULATIONS

    )

)


print("\n")
print("=" * 80)

print(
    "10. MONTE CARLO CURVE SIMULATION"
)

print("=" * 80)


print(

    f"Generated "
    f"{len(monte_carlo_shocks):,} "
    f"correlated 10-day curve shocks."

)


# =============================================================================
# 35. MONTE CARLO DIAGNOSTICS
# =============================================================================


mc_diagnostics = pd.DataFrame({

    "Metric": [

        "Simulations",

        "Risk Factors",

        "NaN Values",

        "Minimum Shock bp",

        "Maximum Shock bp"

    ],

    "Value": [

        len(
            monte_carlo_shocks
        ),

        monte_carlo_shocks.shape[
            1
        ],

        int(
            np.isnan(
                monte_carlo_shocks
            ).sum()
        ),

        (
            monte_carlo_shocks.min()
            * 10_000
        ),

        (
            monte_carlo_shocks.max()
            * 10_000
        )

    ]

})


print(

    mc_diagnostics.to_string(
        index=False
    )

)


mc_diagnostics.to_csv(

    DIAGNOSTIC_DIR
    / "monte_carlo_diagnostics.csv",

    index=False

)


# =============================================================================
# 36. GENERATE MONTE CARLO FUTURE CURVES
# =============================================================================


simulated_curves = (

    current_curve.values

    +

    monte_carlo_shocks

)


# =============================================================================
# 37. MONTE CARLO CURVE PERCENTILES
# =============================================================================


curve_percentiles = pd.DataFrame({

    "Maturity":

        RISK_FACTOR_NODES,

    "Current %":

        current_curve.values
        * 100,

    "5th Percentile %":

        np.quantile(

            simulated_curves,

            0.05,

            axis=0

        )
        * 100,

    "Median %":

        np.quantile(

            simulated_curves,

            0.50,

            axis=0

        )
        * 100,

    "95th Percentile %":

        np.quantile(

            simulated_curves,

            0.95,

            axis=0

        )
        * 100

})


print("\n")
print(
    "Monte Carlo curve percentiles:"
)


print(

    curve_percentiles.round(
        4
    ).to_string(
        index=False
    )

)


curve_percentiles.to_csv(

    TABLE_DIR
    / "monte_carlo_curve_percentiles.csv",

    index=False

)


# =============================================================================
# 38. SAMPLE MONTE CARLO CURVE CHART
# =============================================================================


fig, ax = plt.subplots(

    figsize=(10, 6)

)


x = np.arange(

    len(
        RISK_FACTOR_NODES
    )

)


ax.plot(

    x,

    current_curve.values
    * 100,

    marker="o",

    linewidth=3,

    label="Current curve"

)


for i in range(
    20
):

    ax.plot(

        x,

        simulated_curves[
            i
        ]
        * 100,

        linewidth=0.8,

        alpha=0.45

    )


ax.set_xticks(
    x
)


ax.set_xticklabels(
    RISK_FACTOR_NODES
)


ax.set_title(

    "Example 10-Day Monte Carlo EUR Swap Curves"

)


ax.set_xlabel(

    "Maturity"

)


ax.set_ylabel(

    "Swap Rate (%)"

)


ax.legend()


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "monte_carlo_curve_scenarios.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 39. PCA FOR MULTI-FACTOR YIELD-CURVE MODEL
# =============================================================================
#
# GARCH should NOT be applied to one arbitrary rate.
#
#
# Instead:
#
# historical curve changes
#
#       ↓
#
# standardise
#
#       ↓
#
# PCA
#
#       ↓
#
# common curve factors
#
#
# We retain up to 3 factors.
#
# In yield-curve analysis these often resemble:
#
#   level
#
#   slope
#
#   curvature
#
#
# But we do NOT force those labels.
#
# =============================================================================


def pca_curve_factors(

    rate_changes,

    max_factors=3

):


    X = np.asarray(

        rate_changes,

        dtype=float

    )


    means = (

        X.mean(
            axis=0
        )

    )


    stds = (

        X.std(
            axis=0,
            ddof=1
        )

    )


    stds = np.where(

        stds == 0,

        1,

        stds

    )


    Z = (

        X - means

    ) / stds


    covariance = (

        np.cov(

            Z,

            rowvar=False

        )

    )


    eigenvalues, eigenvectors = (

        np.linalg.eigh(
            covariance
        )

    )


    order = (

        np.argsort(
            eigenvalues
        )[::-1]

    )


    eigenvalues = (

        eigenvalues[
            order
        ]

    )


    eigenvectors = (

        eigenvectors[
            :,
            order
        ]

    )


    explained_variance = (

        eigenvalues

        / eigenvalues.sum()

    )


    n_factors = min(

        max_factors,

        Z.shape[1]

    )


    loadings = (

        eigenvectors[
            :,
            :n_factors
        ]

    )


    scores = (

        Z

        @ loadings

    )


    return {

        "Means":
            means,

        "Stds":
            stds,

        "Eigenvalues":
            eigenvalues,

        "Explained Variance":
            explained_variance,

        "Loadings":
            loadings,

        "Scores":
            scores,

        "Number of Factors":
            n_factors

    }


pca_result = (

    pca_curve_factors(

        daily_changes,

        max_factors=3

    )

)


explained_variance = (

    pca_result[
        "Explained Variance"
    ]

)


print("\n")
print("=" * 80)

print(
    "11. PCA CURVE FACTORS"
)

print("=" * 80)


for i in range(
    pca_result[
        "Number of Factors"
    ]
):

    print(

        f"Factor {i + 1}: "
        f"{explained_variance[i]:.2%} "
        f"of standardized curve-change variance"

    )


# =============================================================================
# 40. PCA EXPLAINED VARIANCE TABLE
# =============================================================================


pca_table = pd.DataFrame({

    "Factor": [

        f"Factor {i + 1}"

        for i in range(
            pca_result[
                "Number of Factors"
            ]
        )

    ],

    "Explained Variance %": [

        explained_variance[i]
        * 100

        for i in range(
            pca_result[
                "Number of Factors"
            ]
        )

    ]

})


pca_table[
    "Cumulative %"
] = (

    pca_table[
        "Explained Variance %"
    ]
    .cumsum()

)


print("\n")
print(

    pca_table.round(
        2
    ).to_string(
        index=False
    )

)


pca_table.to_csv(

    TABLE_DIR
    / "pca_explained_variance.csv",

    index=False

)


# =============================================================================
# 41. PCA LOADING TABLE
# =============================================================================


loading_table = pd.DataFrame(

    pca_result[
        "Loadings"
    ],

    index=RISK_FACTOR_NODES,

    columns=[

        f"Factor {i + 1}"

        for i in range(
            pca_result[
                "Number of Factors"
            ]
        )

    ]

)


loading_table.to_csv(

    TABLE_DIR
    / "pca_factor_loadings.csv"

)


# =============================================================================
# 42. SIMPLE GARCH(1,1)
# =============================================================================
#
# Variance recursion:
#
# h(t)
#
# =
#
# omega
#
# +
#
# alpha × shock(t-1)^2
#
# +
#
# beta × h(t-1)
#
#
# No external "arch" library is required.
#
#
# Parameters are estimated using a simple grid search.
#
# =============================================================================


def garch_variance_path(

    series,

    omega,

    alpha,

    beta

):


    x = np.asarray(

        series,

        dtype=float

    )


    n = len(
        x
    )


    h = np.empty(
        n
    )


    initial_variance = (

        np.var(

            x,

            ddof=1

        )

    )


    h[0] = max(

        initial_variance,

        1e-12

    )


    for t in range(
        1,
        n
    ):

        h[t] = (

            omega

            +

            alpha
            * x[
                t - 1
            ] ** 2

            +

            beta
            * h[
                t - 1
            ]

        )


        h[t] = max(

            h[t],

            1e-12

        )


    return h


# =============================================================================
# 43. GARCH LOG-LIKELIHOOD
# =============================================================================


def garch_loglikelihood(

    series,

    omega,

    alpha,

    beta

):


    x = np.asarray(

        series,

        dtype=float

    )


    h = garch_variance_path(

        x,

        omega,

        alpha,

        beta

    )


    likelihood = (

        -0.5

        * np.sum(

            np.log(

                2
                * np.pi
                * h

            )

            +

            x ** 2
            / h

        )

    )


    return likelihood


# =============================================================================
# 44. FIT GARCH USING GRID SEARCH
# =============================================================================


def fit_simple_garch(
    series
):


    x = np.asarray(

        series,

        dtype=float

    )


    variance = (

        np.var(

            x,

            ddof=1

        )

    )


    best = None


    # Search grid.
    #
    # These are parameter-search ranges,
    # not assumed final parameters.

    alpha_grid = np.linspace(

        0.03,

        0.20,

        8

    )


    beta_grid = np.linspace(

        0.70,

        0.96,

        14

    )


    for alpha in (
        alpha_grid
    ):

        for beta in (
            beta_grid
        ):

            if (

                alpha
                + beta

                >= 0.995

            ):

                continue


            omega = (

                variance

                * (

                    1
                    - alpha
                    - beta

                )

            )


            if omega <= 0:

                continue


            log_likelihood = (

                garch_loglikelihood(

                    x,

                    omega,

                    alpha,

                    beta

                )

            )


            if (

                best is None

                or

                log_likelihood

                >

                best[
                    "LogLikelihood"
                ]

            ):

                best = {

                    "Omega":
                        omega,

                    "Alpha":
                        alpha,

                    "Beta":
                        beta,

                    "LogLikelihood":
                        log_likelihood

                }


    if best is None:

        raise RuntimeError(

            "GARCH calibration failed."

        )


    variance_path = (

        garch_variance_path(

            x,

            best[
                "Omega"
            ],

            best[
                "Alpha"
            ],

            best[
                "Beta"
            ]

        )

    )


    best[
        "Last Variance"
    ] = (

        variance_path[
            -1
        ]

    )


    return best


# =============================================================================
# 45. FIT GARCH TO PCA FACTORS
# =============================================================================


factor_scores = (

    pca_result[
        "Scores"
    ]

)


garch_models = []


for factor_number in range(

    factor_scores.shape[
        1
    ]

):


    factor_series = (

        factor_scores[
            :,
            factor_number
        ]

    )


    try:

        fitted = (

            fit_simple_garch(
                factor_series
            )

        )


        fitted[
            "Factor"
        ] = (

            factor_number
            + 1

        )


        fitted[
            "Converged"
        ] = True


        garch_models.append(
            fitted
        )


    except Exception as error:


        garch_models.append({

            "Factor":

                factor_number
                + 1,

            "Converged":

                False,

            "Error":

                str(
                    error
                )

        })


garch_table = (

    pd.DataFrame(
        garch_models
    )

)


print("\n")
print("=" * 80)

print(
    "12. GARCH CALIBRATION"
)

print("=" * 80)


print(

    garch_table.to_string(
        index=False
    )

)


garch_table.to_csv(

    TABLE_DIR
    / "garch_factor_calibration.csv",

    index=False

)


# =============================================================================
# 46. SIMULATE GARCH FACTOR SHOCKS
# =============================================================================


def simulate_garch_factor_sum(

    fitted_model,

    simulations,

    horizon_days,

    generator

):


    omega = (

        fitted_model[
            "Omega"
        ]

    )


    alpha = (

        fitted_model[
            "Alpha"
        ]

    )


    beta = (

        fitted_model[
            "Beta"
        ]

    )


    current_variance = np.full(

        simulations,

        fitted_model[
            "Last Variance"
        ]

    )


    cumulative_shock = np.zeros(

        simulations

    )


    previous_shock = np.zeros(

        simulations

    )


    for _ in range(

        horizon_days

    ):


        current_variance = (

            omega

            +

            alpha
            * previous_shock ** 2

            +

            beta
            * current_variance

        )


        current_variance = np.maximum(

            current_variance,

            1e-12

        )


        standard_normal = (

            generator.normal(

                size=simulations

            )

        )


        shock = (

            np.sqrt(
                current_variance
            )

            * standard_normal

        )


        cumulative_shock += (
            shock
        )


        previous_shock = (
            shock
        )


    return cumulative_shock


# =============================================================================
# 47. GENERATE MULTI-FACTOR GARCH CURVE SHOCKS
# =============================================================================


all_garch_converged = all(

    model.get(

        "Converged",

        False

    )

    for model in (

        garch_models

    )

)


if all_garch_converged:


    number_of_factors = (

        len(
            garch_models
        )

    )


    simulated_factor_changes = (

        np.zeros(

            (

                N_SIMULATIONS,

                number_of_factors

            )

        )

    )


    for i, model in enumerate(

        garch_models

    ):


        simulated_factor_changes[
            :,
            i
        ] = (

            simulate_garch_factor_sum(

                model,

                N_SIMULATIONS,

                VAR_HORIZON_DAYS,

                rng

            )

        )


    # Reconstruct standardized curve shocks.

    standardized_curve_shocks = (

        simulated_factor_changes

        @

        pca_result[
            "Loadings"
        ].T

    )


    # Convert back to original rate-change scale.

    garch_curve_shocks = (

        standardized_curve_shocks

        *

        pca_result[
            "Stds"
        ]

    )


    print(

        f"\nGenerated "
        f"{len(garch_curve_shocks):,} "
        f"GARCH-based 10-day curve shocks."

    )


else:


    garch_curve_shocks = None


    print(

        "\nWARNING:"

    )


    print(

        "At least one GARCH factor "
        "did not calibrate successfully."

    )


# =============================================================================
# 48. GARCH CURVE DIAGNOSTICS
# =============================================================================


if garch_curve_shocks is not None:


    garch_diagnostics = pd.DataFrame({

        "Metric": [

            "Simulations",

            "Curve Factors",

            "NaN Values",

            "Minimum Shock bp",

            "Maximum Shock bp"

        ],

        "Value": [

            len(
                garch_curve_shocks
            ),

            garch_curve_shocks.shape[
                1
            ],

            int(
                np.isnan(
                    garch_curve_shocks
                ).sum()
            ),

            (
                garch_curve_shocks.min()
                * 10_000
            ),

            (
                garch_curve_shocks.max()
                * 10_000
            )

        ]

    })


    print("\n")
    print(
        garch_diagnostics.to_string(
            index=False
        )
    )


    garch_diagnostics.to_csv(

        DIAGNOSTIC_DIR
        / "garch_simulation_diagnostics.csv",

        index=False

    )


# =============================================================================
# 49. PORTFOLIO SENSITIVITY
# =============================================================================
#
# THIS IS THE ONLY MAJOR UNRESOLVED INPUT.
#
#
# To convert:
#
#       rate shocks
#
# into:
#
#       Vonovia EUR P&L
#
#
# we need:
#
#       Key-rate DV01
#
#
# Example conceptual vector:
#
#       1Y sensitivity
#
#       2Y sensitivity
#
#       ...
#
#       10Y sensitivity
#
#
# The supplied Vonovia data do NOT provide this.
#
#
# Therefore:
#
# KEY_RATE_DV01 remains None.
#
#
# If the group later adopts an explicitly documented sensitivity
# assumption, enter it here.
#
# =============================================================================


KEY_RATE_DV01 = None


# =============================================================================
# 50. OPTIONAL SENSITIVITY INPUT
# =============================================================================
#
# IMPORTANT:
#
# DO NOT activate unless the group explicitly approves the assumptions.
#
#
# Example structure ONLY:
#
#
# KEY_RATE_DV01 = np.array([
#
#     ... EUR per bp at 1Y ...
#
#     ... EUR per bp at 2Y ...
#
#     ... EUR per bp at 3Y ...
#
#     ... EUR per bp at 4Y ...
#
#     ... EUR per bp at 5Y ...
#
#     ... EUR per bp at 7Y ...
#
#     ... EUR per bp at 8Y ...
#
#     ... EUR per bp at 10Y ...
#
# ])
#
#
# The vector MUST follow:
#
# RISK_FACTOR_NODES
#
# =============================================================================


# =============================================================================
# 51. DELTA-NORMAL VaR FUNCTION
# =============================================================================
#
# If:
#
#       d = sensitivity vector
#
#       Sigma = 10-day covariance
#
#
# Portfolio variance:
#
#       d' Sigma d
#
#
# =============================================================================


def delta_normal_var(

    sensitivity_per_decimal,

    covariance

):


    d = np.asarray(

        sensitivity_per_decimal,

        dtype=float

    )


    sigma = np.asarray(

        covariance,

        dtype=float

    )


    variance = (

        d.T

        @ sigma

        @ d

    )


    portfolio_volatility = (

        math.sqrt(

            max(

                variance,

                0

            )

        )

    )


    VaR = (

        Z_95

        * portfolio_volatility

    )


    # Expected Shortfall under normal distribution.

    normal_density = (

        math.exp(

            -0.5
            * Z_95 ** 2

        )

        /

        math.sqrt(

            2
            * math.pi

        )

    )


    expected_shortfall = (

        portfolio_volatility

        * normal_density

        /

        (

            1
            - CONFIDENCE_LEVEL

        )

    )


    return {

        "Portfolio Volatility":

            portfolio_volatility,

        "VaR":

            VaR,

        "Expected Shortfall":

            expected_shortfall

    }


# =============================================================================
# 52. CONVERT RATE SHOCKS TO P&L
# =============================================================================


def shocks_to_pnl(

    shocks,

    sensitivity_per_decimal

):


    shocks = np.asarray(

        shocks,

        dtype=float

    )


    sensitivity = np.asarray(

        sensitivity_per_decimal,

        dtype=float

    )


    return (

        shocks

        @ sensitivity

    )


# =============================================================================
# 53. VaR + EXPECTED SHORTFALL FROM SIMULATED P&L
# =============================================================================


def calculate_var_es(

    pnl,

    confidence=CONFIDENCE_LEVEL

):


    pnl = np.asarray(

        pnl,

        dtype=float

    )


    cutoff = (

        np.quantile(

            pnl,

            1
            - confidence

        )

    )


    VaR = (

        -cutoff

    )


    tail = (

        pnl[
            pnl
            <= cutoff
        ]

    )


    if len(
        tail
    ) == 0:


        expected_shortfall = np.nan


    else:


        expected_shortfall = (

            -tail.mean()

        )


    return {

        "VaR":

            VaR,

        "Expected Shortfall":

            expected_shortfall,

        "P&L Cutoff":

            cutoff

    }


# =============================================================================
# 54. P&L DISTRIBUTION CHART
# =============================================================================


def plot_pnl_distribution(

    pnl,

    result,

    model_name

):


    pnl = np.asarray(

        pnl,

        dtype=float

    )


    fig, ax = plt.subplots(

        figsize=(10, 6)

    )


    ax.hist(

        pnl
        / 1_000_000,

        bins=100

    )


    cutoff_m = (

        result[
            "P&L Cutoff"
        ]

        / 1_000_000

    )


    VaR_m = (

        result[
            "VaR"
        ]

        / 1_000_000

    )


    ax.axvline(

        cutoff_m,

        linestyle="--",

        linewidth=2,

        label=(

            f"95% VaR = "
            f"EUR {VaR_m:,.2f}m"

        )

    )


    ax.set_title(

        f"{model_name}: "
        f"10-Day P&L Distribution"

    )


    ax.set_xlabel(

        "P&L (EUR millions)"

    )


    ax.set_ylabel(

        "Frequency"

    )


    ax.legend()


    plt.tight_layout()


    safe_name = (

        model_name
        .lower()
        .replace(
            " ",
            "_"
        )
        .replace(
            "/",
            "_"
        )

    )


    fig.savefig(

        CHART_DIR
        / f"{safe_name}_pnl_distribution.png",

        dpi=200,

        bbox_inches="tight"

    )


    plt.close(fig)


# =============================================================================
# 55. CALCULATE PORTFOLIO VaR IF SENSITIVITY EXISTS
# =============================================================================


delta_result = None

monte_carlo_result = None

garch_result = None

monte_carlo_pnl = None

garch_pnl = None


if KEY_RATE_DV01 is not None:


    # ---------------------------------------------------------
    # CHECK VECTOR LENGTH
    # ---------------------------------------------------------


    if len(
        KEY_RATE_DV01
    ) != len(
        RISK_FACTOR_NODES
    ):


        raise ValueError(

            "KEY_RATE_DV01 must contain exactly "
            f"{len(RISK_FACTOR_NODES)} values."

        )


    # ---------------------------------------------------------
    # DV01 is normally EUR per 1 basis point.
    #
    # Rate shocks are decimals.
    #
    # Therefore:
    #
    # EUR per decimal
    #
    # =
    #
    # EUR per bp × 10,000
    #
    # ---------------------------------------------------------


    sensitivity_per_decimal = (

        np.asarray(

            KEY_RATE_DV01,

            dtype=float

        )

        * 10_000

    )


    # ---------------------------------------------------------
    # DELTA-NORMAL
    # ---------------------------------------------------------


    delta_result = (

        delta_normal_var(

            sensitivity_per_decimal,

            ten_day_covariance.values

        )

    )


    # ---------------------------------------------------------
    # MONTE CARLO
    # ---------------------------------------------------------


    monte_carlo_pnl = (

        shocks_to_pnl(

            monte_carlo_shocks,

            sensitivity_per_decimal

        )

    )


    monte_carlo_result = (

        calculate_var_es(

            monte_carlo_pnl

        )

    )


    plot_pnl_distribution(

        monte_carlo_pnl,

        monte_carlo_result,

        "Monte Carlo"

    )


    # ---------------------------------------------------------
    # GARCH
    # ---------------------------------------------------------


    if garch_curve_shocks is not None:


        garch_pnl = (

            shocks_to_pnl(

                garch_curve_shocks,

                sensitivity_per_decimal

            )

        )


        garch_result = (

            calculate_var_es(

                garch_pnl

            )

        )


        plot_pnl_distribution(

            garch_pnl,

            garch_result,

            "PCA GARCH"

        )


# =============================================================================
# 56. MODEL COMPARISON
# =============================================================================


comparison_rows = []


# -----------------------------------------------------------------------------
# DELTA NORMAL
# -----------------------------------------------------------------------------


if delta_result is None:


    comparison_rows.append({

        "Methodology":

            "Delta-Normal",

        "10-Day 95% VaR EUR":

            np.nan,

        "95% Expected Shortfall EUR":

            np.nan,

        "Major Assumptions":

            (
                "Linear PV sensitivity; "
                "multivariate-normal rate changes"
            ),

        "Advantages":

            (
                "Simple, transparent and fast"
            ),

        "Limitations":

            (
                "Requires Vonovia key-rate sensitivity; "
                "linear approximation"
            ),

        "Status":

            (
                "HOLD — key-rate DV01 unavailable"
            )

    })


else:


    comparison_rows.append({

        "Methodology":

            "Delta-Normal",

        "10-Day 95% VaR EUR":

            delta_result[
                "VaR"
            ],

        "95% Expected Shortfall EUR":

            delta_result[
                "Expected Shortfall"
            ],

        "Major Assumptions":

            (
                "Linear PV sensitivity; "
                "multivariate-normal rate changes"
            ),

        "Advantages":

            (
                "Simple, transparent and fast"
            ),

        "Limitations":

            (
                "Linear approximation; "
                "normality assumption"
            ),

        "Status":

            "Calculated"

    })


# -----------------------------------------------------------------------------
# MONTE CARLO
# -----------------------------------------------------------------------------


if monte_carlo_result is None:


    comparison_rows.append({

        "Methodology":

            "Monte Carlo / Covariance",

        "10-Day 95% VaR EUR":

            np.nan,

        "95% Expected Shortfall EUR":

            np.nan,

        "Major Assumptions":

            (
                "Historical covariance; "
                "multivariate-normal 10-day curve shocks"
            ),

        "Advantages":

            (
                "Models correlated movements "
                "across eight EUR curve nodes"
            ),

        "Limitations":

            (
                "Portfolio DV01 unavailable; "
                "covariance assumed stable"
            ),

        "Status":

            (
                "100,000 curve simulations complete; "
                "portfolio VaR on HOLD"
            )

    })


else:


    comparison_rows.append({

        "Methodology":

            "Monte Carlo / Covariance",

        "10-Day 95% VaR EUR":

            monte_carlo_result[
                "VaR"
            ],

        "95% Expected Shortfall EUR":

            monte_carlo_result[
                "Expected Shortfall"
            ],

        "Major Assumptions":

            (
                "Historical covariance; "
                "multivariate-normal 10-day curve shocks"
            ),

        "Advantages":

            (
                "Models correlated movements "
                "across eight EUR curve nodes"
            ),

        "Limitations":

            (
                "Covariance assumed stable; "
                "normal-shock assumption"
            ),

        "Status":

            "Calculated"

    })


# -----------------------------------------------------------------------------
# GARCH
# -----------------------------------------------------------------------------


if garch_result is None:


    comparison_rows.append({

        "Methodology":

            "PCA + GARCH",

        "10-Day 95% VaR EUR":

            np.nan,

        "95% Expected Shortfall EUR":

            np.nan,

        "Major Assumptions":

            (
                "Three PCA curve factors; "
                "GARCH(1,1) conditional volatility"
            ),

        "Advantages":

            (
                "Allows volatility to change "
                "through time"
            ),

        "Limitations":

            (
                "Portfolio DV01 unavailable; "
                "factor and GARCH model risk"
            ),

        "Status":

            (
                "Curve calibration/simulation complete; "
                "portfolio VaR on HOLD"
            )

    })


else:


    comparison_rows.append({

        "Methodology":

            "PCA + GARCH",

        "10-Day 95% VaR EUR":

            garch_result[
                "VaR"
            ],

        "95% Expected Shortfall EUR":

            garch_result[
                "Expected Shortfall"
            ],

        "Major Assumptions":

            (
                "Three PCA curve factors; "
                "GARCH(1,1) conditional volatility"
            ),

        "Advantages":

            (
                "Allows volatility to change "
                "through time"
            ),

        "Limitations":

            (
                "Factor selection and "
                "GARCH specification risk"
            ),

        "Status":

            "Calculated"

    })


comparison_table = (

    pd.DataFrame(
        comparison_rows
    )

)


print("\n")
print("=" * 80)

print(
    "13. MODEL COMPARISON"
)

print("=" * 80)


print(

    comparison_table.to_string(
        index=False
    )

)


comparison_table.to_csv(

    RESULT_DIR
    / "var_model_comparison.csv",

    index=False

)


# =============================================================================
# 57. VaR COMPARISON CHART
# =============================================================================


available_var = (

    comparison_table[
        [
            "Methodology",
            "10-Day 95% VaR EUR"
        ]
    ]
    .dropna()

)


if not available_var.empty:


    fig, ax = plt.subplots(

        figsize=(9, 6)

    )


    ax.bar(

        available_var[
            "Methodology"
        ],

        available_var[
            "10-Day 95% VaR EUR"
        ]
        / 1_000_000

    )


    ax.set_title(

        "Vonovia 10-Day 95% Interest-Rate VaR"

    )


    ax.set_ylabel(

        "VaR (EUR millions)"

    )


    ax.tick_params(

        axis="x",

        rotation=25

    )


    plt.tight_layout()


    fig.savefig(

        CHART_DIR
        / "var_model_comparison.png",

        dpi=200,

        bbox_inches="tight"

    )


    plt.close(fig)


# =============================================================================
# 58. SAVE DATA GAPS
# =============================================================================


data_gap_table = pd.DataFrame(

    data_gaps

)


data_gap_table.to_csv(

    DIAGNOSTIC_DIR
    / "unresolved_data_gaps.csv",

    index=False

)


# =============================================================================
# 59. SAVE ASSUMPTIONS
# =============================================================================


assumption_table = pd.DataFrame(

    assumptions

)


assumption_table.to_csv(

    DIAGNOSTIC_DIR
    / "model_assumptions.csv",

    index=False

)


# =============================================================================
# 60. FINAL EXECUTIVE SUMMARY
# =============================================================================


print("\n")
print("=" * 80)

print(
    "EXECUTIVE SUMMARY"
)

print("=" * 80)


print(

    "Client:                 "
    "Vonovia SE"

)


print(

    "Risk measured:          "
    "Interest-rate risk from a PV perspective"

)


print(

    "Identified debt:        "
    f"EUR {TOTAL_DEBT / 1e9:,.3f}bn"

)


print(

    "Historical calibration: "
    f"{START_DATE.date()} "
    f"to "
    f"{END_DATE.date()}"

)


print(

    "Observations:           "
    f"{NUMBER_OF_OBSERVATIONS:,}"

)


print(

    "Risk factors:           "
    f"{', '.join(RISK_FACTOR_NODES)}"

)


print(

    "Excluded nodes:         "
    f"{', '.join(EXCLUDED_NODES)} "
    "(insufficient history)"

)


print(

    "VaR horizon:            "
    f"{VAR_HORIZON_DAYS} trading days"

)


print(

    "Confidence level:       "
    f"{CONFIDENCE_LEVEL:.0%}"

)


print(

    "Monte Carlo scenarios:  "
    f"{N_SIMULATIONS:,}"

)


print("\n")
print(
    "MARKET-RISK CALIBRATION:"
)


print(

    "  [OK] Historical EUR swap curve cleaned"

)


print(

    "  [OK] Daily rate changes calculated"

)


print(

    "  [OK] Daily and 10-day volatility calculated"

)


print(

    "  [OK] Covariance matrix calculated"

)


print(

    "  [OK] Correlation matrix calculated"

)


print(

    "  [OK] 100,000 Monte Carlo curve scenarios generated"

)


print(

    "  [OK] PCA curve factors calculated"

)


if all_garch_converged:


    print(

        "  [OK] GARCH factors calibrated"

    )


    print(

        "  [OK] GARCH curve scenarios generated"

    )


else:


    print(

        "  [WARNING] GARCH calibration incomplete"

    )


print("\n")
print(
    "PORTFOLIO-RISK STATUS:"
)


if KEY_RATE_DV01 is None:


    print(

        "  [HOLD] Vonovia key-rate DV01 unavailable"

    )


    print(

        "  [HOLD] Monetary portfolio VaR cannot yet "
        "be calculated without an explicit sensitivity assumption"

    )


else:


    print(

        "  [OK] Vonovia key-rate sensitivity supplied"

    )


    print(

        "  [OK] Delta-Normal VaR calculated"

    )


    print(

        "  [OK] Monte Carlo VaR calculated"

    )


    if garch_result is not None:


        print(

            "  [OK] GARCH VaR calculated"

        )


print("\n")
print(
    "KEY LIMITATION:"
)


print(

    "The supplied Vonovia information identifies aggregate debt "
    "amounts but does not identify sufficient maturity, coupon, "
    "fixed/floating, derivative or DV01 information to map the "
    "simulated EUR yield-curve movements into a defensible "
    "Vonovia-specific EUR PV distribution without an additional "
    "explicit sensitivity assumption."

)


print("\n")
print(
    "OUTPUT DIRECTORY:"
)


print(

    OUTPUT_DIR

)


print("\n")
print("=" * 80)

print(
    "ANALYSIS COMPLETED SUCCESSFULLY"
)

print("=" * 80)