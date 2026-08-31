# =============================================================================
# VONOVIA SE — INTEREST-RATE VaR
# VERSION 1 — HOLD / DATA PREPARATION TEMPLATE
# =============================================================================
#
# PURPOSE
# -------
# Estimate Vonovia SE's interest-rate Value at Risk from a
# Present Value (PV) perspective.
#
# FINAL METHODS:
#   1. Monte Carlo / covariance simulation
#   2. Delta-Normal VaR
#   3. GARCH-based simulation
#
# FIXED SPECIFICATION:
#   VaR horizon:        10 trading days
#   Confidence level:   95%
#   Simulations:        100,000
#   Reporting currency: EUR
#
# IMPORTANT DATA LIMITATION:
# Bloomberg gives us aggregate Vonovia debt amounts, but not enough
# instrument-level information to reconstruct every bond/loan exactly.
#
# Therefore we do NOT invent:
#   - coupons
#   - maturities
#   - duration
#   - fixed/floating split
#   - derivative positions
#
# Missing information remains explicitly on HOLD.
# =============================================================================


# =============================================================================
# 1. IMPORT LIBRARIES
# =============================================================================

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =============================================================================
# 2. MODEL SETTINGS
# =============================================================================

CONFIDENCE_LEVEL = 0.95

TAIL_PROBABILITY = (
    1 - CONFIDENCE_LEVEL
)

VAR_HORIZON_DAYS = 10

N_SIMULATIONS = 100_000

RANDOM_SEED = 42

REPORTING_CURRENCY = "EUR"


# Random number generator used by Monte Carlo.

rng = np.random.default_rng(
    RANDOM_SEED
)


# =============================================================================
# 3. PROJECT DIRECTORIES
# =============================================================================
#
# The script assumes it is being run from:
#
# Financial Engineering/
#
# It will automatically create:
#
# Financial Engineering/output/
#
# =============================================================================

PROJECT_DIR = Path.cwd()

OUTPUT_DIR = (
    PROJECT_DIR
    / "output"
)

CHART_DIR = (
    OUTPUT_DIR
    / "charts"
)

TABLE_DIR = (
    OUTPUT_DIR
    / "tables"
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
    CHART_DIR,
    TABLE_DIR,
    RESULT_DIR,
    DIAGNOSTIC_DIR

]:

    folder.mkdir(
        parents=True,
        exist_ok=True
    )


print("\n" + "=" * 70)

print(
    "VONOVIA SE — INTEREST-RATE VaR"
)

print("=" * 70)

print(
    "Project directory:",
    PROJECT_DIR
)

print(
    "Confidence level:",
    f"{CONFIDENCE_LEVEL:.0%}"
)

print(
    "VaR horizon:",
    VAR_HORIZON_DAYS,
    "trading days"
)

print(
    "Monte Carlo simulations:",
    f"{N_SIMULATIONS:,}"
)

print(
    "Reporting currency:",
    REPORTING_CURRENCY
)


# =============================================================================
# 4. VONOVIA DEBT DATA AVAILABLE FROM BLOOMBERG
# =============================================================================
#
# Bloomberg Capital Structure screen:
#
# 1st Lien Secured Loans          EUR 3,499.40m
# Senior Unsecured Loans          EUR   150.00m
# Senior Unsecured Bonds          EUR 26,678.46m
# Senior Unsecured Schuldschein   EUR 1,060.00m
#
# Bloomberg reports:
#
# Total Debt Outstanding          EUR 31,387.86m
#
# Small differences between category totals and Bloomberg's displayed total
# can occur because of rounding / Bloomberg aggregation.
#
# =============================================================================

vonovia_debt = pd.DataFrame({

    "Debt Type": [

        "1st Lien Secured Loans",

        "Senior Unsecured Loans",

        "Senior Unsecured Bonds",

        "Senior Unsecured Schuldschein"

    ],

    "Outstanding EUR m": [

        3499.40,

        150.00,

        26678.46,

        1060.00

    ]

})


# Convert EUR millions into actual EUR.

vonovia_debt[
    "Outstanding EUR"
] = (

    vonovia_debt[
        "Outstanding EUR m"
    ]

    * 1_000_000

)


# Calculate total based on the visible categories.

TOTAL_DEBT_CALCULATED = (

    vonovia_debt[
        "Outstanding EUR"
    ].sum()

)


# Bloomberg displayed total.

TOTAL_DEBT_BLOOMBERG = (
    31_387.86
    * 1_000_000
)


# Calculate portfolio weights using visible category totals.

vonovia_debt[
    "Weight"
] = (

    vonovia_debt[
        "Outstanding EUR"
    ]

    / TOTAL_DEBT_CALCULATED

)


# =============================================================================
# 5. PRINT DEBT STRUCTURE
# =============================================================================

print("\n")
print("=" * 70)

print(
    "VONOVIA DEBT STRUCTURE"
)

print("=" * 70)


print(

    vonovia_debt[
        [
            "Debt Type",
            "Outstanding EUR m",
            "Weight"
        ]
    ].to_string(
        index=False
    )

)


print(
    "\nCalculated category total:",
    f"EUR {TOTAL_DEBT_CALCULATED / 1e9:.3f}bn"
)


print(
    "Bloomberg displayed total:",
    f"EUR {TOTAL_DEBT_BLOOMBERG / 1e9:.3f}bn"
)


# Save table.

vonovia_debt.to_csv(

    TABLE_DIR
    / "vonovia_debt_structure.csv",

    index=False

)


# =============================================================================
# 6. PLOT DEBT STRUCTURE
# =============================================================================

plt.figure(
    figsize=(10, 6)
)


plt.bar(

    vonovia_debt[
        "Debt Type"
    ],

    vonovia_debt[
        "Outstanding EUR m"
    ]

)


plt.ylabel(
    "Outstanding Debt (EUR millions)"
)


plt.title(
    "Vonovia Debt Structure"
)


plt.xticks(
    rotation=30,
    ha="right"
)


plt.tight_layout()


plt.savefig(

    CHART_DIR
    / "vonovia_debt_structure.png",

    dpi=200,

    bbox_inches="tight"

)


plt.show()


# =============================================================================
# 7. AVAILABLE BALANCE-SHEET INFORMATION
# =============================================================================
#
# From the supplied Bloomberg financial-analysis data:
#
# 2025:
#
# Cash & Near Cash       EUR 3,256.9m
# Other Investments      EUR 3,427.2m
#
# IMPORTANT:
#
# We do NOT automatically include these in interest-rate VaR.
#
# Why?
#
# We do not know enough about their:
#
#   maturity
#   duration
#   coupon
#   interest-rate sensitivity
#
# Therefore their inclusion would require assumptions.
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

    "Included in VaR": [

        "No",

        "No"

    ],

    "Reason": [

        "Interest-rate sensitivity not sufficiently identified",

        "Duration and instrument composition unavailable"

    ]

})


print("\n")
print("=" * 70)

print(
    "AVAILABLE BALANCE-SHEET REFERENCE DATA"
)

print("=" * 70)


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
# 8. HISTORICAL INTEREST-RATE FILE
# =============================================================================

RATE_FILE = (

    PROJECT_DIR
    / "Swap Curve EURIBOR.xlsx"

)


print("\n")
print("=" * 70)

print(
    "INTEREST-RATE DATA"
)

print("=" * 70)


if RATE_FILE.exists():

    print(
        "Historical interest-rate file found:"
    )

    print(
        RATE_FILE
    )

else:

    print(
        "WARNING:"
    )

    print(
        "Swap Curve EURIBOR.xlsx "
        "was not found in the working directory."
    )


# =============================================================================
# 9. INSPECT EXCEL FILE
# =============================================================================
#
# Before cleaning Bloomberg data, inspect:
#
#   sheet names
#   column names
#   rate units
#   date format
#
# We do not guess.
#
# =============================================================================

if RATE_FILE.exists():

    try:

        excel_file = pd.ExcelFile(
            RATE_FILE
        )

        print(
            "\nExcel sheets found:"
        )

        print(
            excel_file.sheet_names
        )

    except Exception as error:

        print(
            "\nCould not inspect Excel file:"
        )

        print(
            error
        )


# =============================================================================
# 10. RATE-DATA CLEANING FUNCTION
# =============================================================================

def standardize_column_names(df):

    """
    Mechanically clean column names.

    This does NOT alter financial values.
    """

    cleaned = df.copy()

    cleaned.columns = (

        cleaned.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(
            " ",
            "_",
            regex=False
        )
        .str.replace(
            "/",
            "_",
            regex=False
        )
        .str.replace(
            "-",
            "_",
            regex=False
        )

    )

    return cleaned


# =============================================================================
# 11. DATA QUALITY REPORT
# =============================================================================

def data_quality_report(
    df,
    dataset_name
):

    report = pd.DataFrame({

        "Dataset": [
            dataset_name
        ],

        "Rows": [
            len(df)
        ],

        "Columns": [
            len(df.columns)
        ],

        "Duplicate Rows": [
            int(
                df.duplicated().sum()
            )
        ],

        "Missing Cells": [
            int(
                df.isna().sum().sum()
            )
        ]

    })


    return report


# =============================================================================
# 12. PREPARE RATE HISTORY
# =============================================================================

def prepare_rate_history(

    df,

    date_column,

    rate_columns

):

    """
    Clean historical interest-rate data.

    IMPORTANT:

    Rate units must be verified before this function
    is used for the final VaR model.

    Example:

    2.50 may mean 2.50%.

    The model ultimately needs decimal rates:

    2.50% = 0.0250
    """

    cleaned = (
        standardize_column_names(
            df
        )
    )


    date_column = (

        date_column
        .lower()
        .replace(
            " ",
            "_"
        )

    )


    rate_columns = [

        column
        .lower()
        .replace(
            " ",
            "_"
        )

        for column
        in rate_columns

    ]


    cleaned[
        date_column
    ] = pd.to_datetime(

        cleaned[
            date_column
        ],

        errors="coerce"

    )


    cleaned = (

        cleaned
        .dropna(
            subset=[
                date_column
            ]
        )
        .drop_duplicates()
        .sort_values(
            date_column
        )
        .set_index(
            date_column
        )

    )


    for column in rate_columns:

        cleaned[
            column
        ] = pd.to_numeric(

            cleaned[
                column
            ],

            errors="coerce"

        )


    return (
        cleaned[
            rate_columns
        ]
    )


# =============================================================================
# 13. RATE CHANGES
# =============================================================================
#
# We use ABSOLUTE interest-rate changes:
#
#       Delta r = r(t) - r(t-1)
#
#
# Example:
#
# 3.00% -> 3.05%
#
# = +0.05 percentage points
#
# = +5 basis points
#
# = +0.0005 in decimal form
#
# =============================================================================

def calculate_rate_changes(
    rates
):

    return (

        rates
        .diff()
        .dropna()

    )


# =============================================================================
# 14. HISTORICAL VOLATILITY
# =============================================================================

def calculate_volatility_bp(
    rate_changes
):

    """
    Convert standard deviation of decimal rate
    changes into basis points.
    """

    return (

        rate_changes.std()

        * 10_000

    )


# =============================================================================
# 15. COVARIANCE
# =============================================================================

def calculate_covariance(
    rate_changes
):

    return (
        rate_changes.cov()
    )


# =============================================================================
# 16. CORRELATION
# =============================================================================

def calculate_correlation(
    rate_changes
):

    return (
        rate_changes.corr()
    )


# =============================================================================
# 17. CORRELATION HEATMAP
# =============================================================================

def plot_correlation_heatmap(
    correlation
):

    fig, ax = plt.subplots(
        figsize=(9, 7)
    )


    image = ax.imshow(
        correlation.values,
        aspect="auto"
    )


    ax.set_xticks(
        range(
            len(
                correlation.columns
            )
        )
    )


    ax.set_yticks(
        range(
            len(
                correlation.index
            )
        )
    )


    ax.set_xticklabels(

        correlation.columns,

        rotation=45,

        ha="right"

    )


    ax.set_yticklabels(
        correlation.index
    )


    # Add correlation values
    # inside the heatmap.

    for i in range(
        len(
            correlation.index
        )
    ):

        for j in range(
            len(
                correlation.columns
            )
        ):

            ax.text(

                j,

                i,

                f"{correlation.iloc[i, j]:.2f}",

                ha="center",

                va="center"

            )


    ax.set_title(
        "EUR Interest-Rate Correlation"
    )


    fig.colorbar(
        image,
        ax=ax
    )


    fig.tight_layout()


    fig.savefig(

        CHART_DIR
        / "interest_rate_correlation_heatmap.png",

        dpi=200,

        bbox_inches="tight"

    )


    plt.show()


# =============================================================================
# 18. PORTFOLIO SENSITIVITY LIMITATION
# =============================================================================
#
# We currently know approximately:
#
#       EUR 31.39bn total debt
#
#
# But we do NOT know:
#
#       exact maturities
#
#       exact coupons
#
#       modified duration
#
#       DV01
#
#       fixed/floating split
#
#       derivatives
#
#
# Therefore:
#
# We CANNOT yet uniquely calculate the debt's
# interest-rate sensitivity.
#
#
# The next required input is:
#
#       duration / DV01
#
#
# Preferably sourced from Vonovia.
#
# If unavailable, duration assumptions must be
# explicitly labelled as assumptions.
#
# =============================================================================

PORTFOLIO_MODIFIED_DURATION = None

KEY_RATE_DV01 = None


# =============================================================================
# 19. DV01 FUNCTION
# =============================================================================
#
# Approximation:
#
# DV01
#
# ≈
#
# Portfolio Value
#
# × Modified Duration
#
# × 0.0001
#
#
# DV01 tells us approximately how much PV changes
# for a 1 basis-point change in rates.
#
# =============================================================================

def calculate_dv01(

    portfolio_value,

    modified_duration

):

    return (

        portfolio_value

        * modified_duration

        * 0.0001

    )


# =============================================================================
# 20. DELTA-NORMAL PORTFOLIO VOLATILITY
# =============================================================================
#
# If:
#
# d = sensitivity vector
#
# Sigma = covariance matrix
#
#
# Portfolio variance:
#
#       d' Sigma d
#
#
# =============================================================================

def delta_normal_portfolio_volatility(

    sensitivity_vector,

    daily_covariance,

    horizon_days=VAR_HORIZON_DAYS

):

    sensitivities = np.asarray(

        sensitivity_vector,

        dtype=float

    )


    covariance = np.asarray(

        daily_covariance,

        dtype=float

    )


    # Scale daily covariance
    # to 10 trading days.

    horizon_covariance = (

        covariance

        * horizon_days

    )


    portfolio_variance = (

        sensitivities.T

        @ horizon_covariance

        @ sensitivities

    )


    portfolio_volatility = (

        np.sqrt(
            portfolio_variance
        )

    )


    return float(
        portfolio_volatility
    )


# =============================================================================
# 21. DELTA-NORMAL VaR
# =============================================================================
#
# We removed the SciPy dependency.
#
# For a ONE-TAILED 95% normal VaR:
#
#       z = 1.6448536269514722
#
# =============================================================================

def delta_normal_var(

    sensitivity_vector,

    daily_covariance,

    horizon_days=VAR_HORIZON_DAYS

):

    portfolio_volatility = (

        delta_normal_portfolio_volatility(

            sensitivity_vector,

            daily_covariance,

            horizon_days

        )

    )


    # 95% one-tailed normal critical value.

    z_95 = (
        1.6448536269514722
    )


    VaR = (

        z_95

        * portfolio_volatility

    )


    return {

        "Portfolio Volatility":
            portfolio_volatility,

        "10-Day 95% VaR":
            VaR

    }


# =============================================================================
# 22. MONTE CARLO RATE SHOCKS
# =============================================================================
#
# Assumption:
#
#       Delta r ~ multivariate normal
#
#
# Covariance captures:
#
#       volatility
#
#       +
#
#       correlation across maturities
#
# =============================================================================

def monte_carlo_rate_shocks(

    daily_covariance,

    n_simulations=N_SIMULATIONS,

    horizon_days=VAR_HORIZON_DAYS

):

    covariance = np.asarray(

        daily_covariance,

        dtype=float

    )


    # Scale covariance from 1 day
    # to 10 trading days.

    horizon_covariance = (

        covariance

        * horizon_days

    )


    number_of_factors = (

        horizon_covariance.shape[0]

    )


    mean_shock = np.zeros(

        number_of_factors

    )


    shocks = (

        rng.multivariate_normal(

            mean=mean_shock,

            cov=horizon_covariance,

            size=n_simulations

        )

    )


    return shocks


# =============================================================================
# 23. TRANSLATE RATE SHOCKS INTO P&L
# =============================================================================
#
# Without exact bond cash flows:
#
#       P&L ≈ sensitivity × rate shock
#
#
# With several maturity factors:
#
#       P&L ≈ shock vector @ sensitivity vector
#
# =============================================================================

def shocks_to_pnl(

    shocks,

    sensitivity_vector

):

    shocks = np.asarray(
        shocks,
        dtype=float
    )


    sensitivities = np.asarray(
        sensitivity_vector,
        dtype=float
    )


    pnl = (

        shocks

        @ sensitivities

    )


    return pnl


# =============================================================================
# 24. VaR AND EXPECTED SHORTFALL
# =============================================================================

def calculate_var_es(

    pnl,

    confidence=CONFIDENCE_LEVEL

):

    pnl = np.asarray(
        pnl,
        dtype=float
    )


    # 5th percentile for 95% VaR.

    cutoff = np.quantile(

        pnl,

        1 - confidence

    )


    VaR = (
        -cutoff
    )


    # Worst 5% observations.

    tail = pnl[
        pnl <= cutoff
    ]


    if len(tail) > 0:

        expected_shortfall = (

            -tail.mean()

        )

    else:

        expected_shortfall = (
            np.nan
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
# 25. PLOT P&L DISTRIBUTION
# =============================================================================

def plot_pnl_distribution(

    pnl,

    var_result,

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

        pnl / 1_000_000,

        bins=80

    )


    cutoff_million = (

        var_result[
            "P&L Cutoff"
        ]

        / 1_000_000

    )


    VaR_million = (

        var_result[
            "VaR"
        ]

        / 1_000_000

    )


    ax.axvline(

        cutoff_million,

        linestyle="--",

        linewidth=2,

        label=(
            f"95% VaR = "
            f"EUR {VaR_million:.2f}m"
        )

    )


    ax.set_title(

        f"{model_name}: "
        "10-Day P&L Distribution"

    )


    ax.set_xlabel(
        "P&L (EUR millions)"
    )


    ax.set_ylabel(
        "Frequency"
    )


    ax.legend()


    fig.tight_layout()


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


    plt.show()


# =============================================================================
# 26. GARCH FRAMEWORK
# =============================================================================
#
# HOLD
#
# We should NOT fit GARCH to one arbitrary rate
# and claim it models the entire yield curve.
#
#
# Planned structure:
#
# Historical curve changes
#
#       ↓
#
# Curve factors
#
#       ↓
#
# GARCH volatility
#
#       ↓
#
# Simulated factor shocks
#
#       ↓
#
# Reconstructed curve shocks
#
#       ↓
#
# Portfolio P&L
#
#
# We will implement this after inspecting
# the historical EURIBOR swap-curve data.
#
# =============================================================================

def garch_framework(
    rate_changes
):

    raise NotImplementedError(

        "HOLD: GARCH model will be "
        "implemented after the historical "
        "EURIBOR curve has been cleaned "
        "and inspected."

    )


# =============================================================================
# 27. COVARIANCE DIAGNOSTICS
# =============================================================================

def covariance_diagnostics(
    covariance
):

    covariance = np.asarray(

        covariance,

        dtype=float

    )


    eigenvalues = (

        np.linalg.eigvalsh(
            covariance
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
                    covariance
                )
            )

    }


# =============================================================================
# 28. SIMULATION DIAGNOSTICS
# =============================================================================

def simulation_diagnostics(
    simulated_shocks
):

    data = np.asarray(

        simulated_shocks,

        dtype=float

    )


    return {

        "Number of Simulations":
            int(
                data.shape[0]
            ),

        "NaN Values":
            int(
                np.isnan(
                    data
                ).sum()
            ),

        "Infinite Values":
            int(
                np.isinf(
                    data
                ).sum()
            ),

        "Minimum Shock":
            float(
                np.nanmin(
                    data
                )
            ),

        "Maximum Shock":
            float(
                np.nanmax(
                    data
                )
            )

    }


# =============================================================================
# 29. MODEL COMPARISON TABLE
# =============================================================================

results = pd.DataFrame({

    "Model": [

        "Delta-Normal",

        "Monte Carlo",

        "GARCH"

    ],

    "10-Day 95% VaR": [

        np.nan,

        np.nan,

        np.nan

    ],

    "95% Expected Shortfall": [

        np.nan,

        np.nan,

        np.nan

    ],

    "Status": [

        "HOLD - awaiting duration / DV01",

        "HOLD - awaiting duration / DV01",

        "HOLD - awaiting rate calibration"

    ]

})


print("\n")
print("=" * 70)

print(
    "MODEL COMPARISON"
)

print("=" * 70)


print(

    results.to_string(
        index=False
    )

)


results.to_csv(

    RESULT_DIR
    / "model_comparison_HOLD.csv",

    index=False

)


# =============================================================================
# 30. CURRENT MODEL STATUS
# =============================================================================

print("\n")
print("=" * 70)

print(
    "CURRENT MODEL STATUS"
)

print("=" * 70)


print(

    "Vonovia Bloomberg debt:",

    f"EUR {TOTAL_DEBT_BLOOMBERG / 1e9:.2f}bn"

)


print(

    "Historical rate file:",

    (
        "AVAILABLE"
        if RATE_FILE.exists()
        else "NOT FOUND"
    )

)


print(

    "Exact bond cash flows:",

    "NOT AVAILABLE"

)


print(

    "Portfolio duration:",

    "NOT AVAILABLE"

)


print(

    "Key-rate DV01:",

    "NOT AVAILABLE"

)


print(

    "Fixed / floating debt split:",

    "NOT AVAILABLE"

)


print(

    "Interest-rate derivatives:",

    "NOT AVAILABLE"

)


print("\n")
print(
    "MODELLING DECISION:"
)

print(

    "Use a sensitivity-based interest-rate VaR "
    "framework rather than pretending that exact "
    "bond-by-bond full revaluation is possible."

)


print("\n")
print(
    "NEXT STEP:"
)

print(

    "Inspect and clean Swap Curve EURIBOR.xlsx, "
    "then determine what defensible duration / "
    "DV01 assumptions can be used for the "
    "aggregate Vonovia debt exposure."

)


print("\n" + "=" * 70)

print(
    "SCRIPT COMPLETED SUCCESSFULLY"
)

print("=" * 70)