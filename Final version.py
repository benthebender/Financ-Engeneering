# =============================================================================
# VONOVIA SE — SIMPLIFIED INTEREST-RATE VaR ANALYSIS
# UPDATED FOR IMPROVED "Swap curves.xlsx" DATASET
# =============================================================================
#
# PURPOSE
# -------
# Demonstrate how a corporate client such as Vonovia can assess
# interest-rate risk from a Present Value (PV) perspective using:
#
#   1. Delta-Normal VaR
#   2. Monte Carlo VaR
#   3. PCA + GARCH VaR
#
# IMPORTANT
# ---------
# This is an ILLUSTRATIVE corporate VaR model.
#
# Vonovia's identified debt amount comes from supplied Bloomberg data.
#
# Bloomberg did NOT provide sufficient instrument-level duration,
# maturity, coupon or derivative information.
#
# Therefore the model explicitly assumes:
#
#   Base modified duration = 5 years
#
# and performs sensitivity analysis using:
#
#   Low duration  = 3 years
#   Base duration = 5 years
#   High duration = 7 years
#
# These are MODELLING ASSUMPTIONS, not reported Vonovia durations.
#
# IMPROVED MARKET DATA
# --------------------
# The improved Bloomberg workbook contains separate Date + Rate pairs
# for every maturity from 1Y to 10Y.
#
# Therefore:
#
#   - all ten maturities are used;
#   - 6Y and 9Y are no longer excluded;
#   - each maturity is cleaned independently;
#   - the series are merged by actual date;
#   - no forward filling is required;
#   - changes across unusually large calendar gaps are excluded.
#
# =============================================================================


# =============================================================================
# 1. IMPORTS
# =============================================================================

from pathlib import Path
import math
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")


# =============================================================================
# 2. MODEL SETTINGS
# =============================================================================

CONFIDENCE_LEVEL = 0.95

VAR_HORIZON_DAYS = 10

N_SIMULATIONS = 100_000

RANDOM_SEED = 42

# 95% one-tailed standard-normal critical value
Z_95 = 1.6448536269514722

rng = np.random.default_rng(
    RANDOM_SEED
)


# =============================================================================
# 3. SIMPLIFIED VONOVIA EXPOSURE
# =============================================================================

# Identified Bloomberg debt exposure

TOTAL_DEBT = (
    31_387.86
    * 1_000_000
)


# Duration sensitivity scenarios

DURATION_SCENARIOS = {

    "Low": 3.0,

    "Base": 5.0,

    "High": 7.0

}


BASE_DURATION = (
    DURATION_SCENARIOS[
        "Base"
    ]
)


# =============================================================================
# 4. PROJECT FOLDERS
# =============================================================================

PROJECT_DIR = Path.cwd()


# NEW IMPROVED FILE

RATE_FILE = (
    PROJECT_DIR
    / "Swap curves.xlsx"
)


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

CLEAN_DIR = (
    OUTPUT_DIR
    / "cleaned_data"
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
    CLEAN_DIR,
    RESULT_DIR,
    DIAGNOSTIC_DIR

]:

    folder.mkdir(
        parents=True,
        exist_ok=True
    )


# =============================================================================
# 5. INTRODUCTION
# =============================================================================

print("\n" + "=" * 80)

print(
    "VONOVIA SE — SIMPLIFIED INTEREST-RATE VaR"
)

print("=" * 80)


print(
    f"Debt exposure:       "
    f"EUR {TOTAL_DEBT / 1e9:.3f}bn"
)

print(
    f"Base duration:       "
    f"{BASE_DURATION:.1f} years"
)

print(
    f"VaR horizon:         "
    f"{VAR_HORIZON_DAYS} trading days"
)

print(
    f"Confidence level:    "
    f"{CONFIDENCE_LEVEL:.0%}"
)

print(
    f"Simulations:         "
    f"{N_SIMULATIONS:,}"
)

print(
    f"Market-data file:    "
    f"{RATE_FILE.name}"
)


# =============================================================================
# 6. CHECK IMPROVED BLOOMBERG FILE
# =============================================================================

if not RATE_FILE.exists():

    raise FileNotFoundError(
        f"Could not find: {RATE_FILE}"
    )


# =============================================================================
# 7. LOAD IMPROVED BLOOMBERG WORKBOOK
# =============================================================================

raw = pd.read_excel(

    RATE_FILE,

    sheet_name="Sheet1",

    header=None

)


print("\n")
print("=" * 80)

print(
    "MARKET DATA"
)

print("=" * 80)


print(
    f"Raw Excel dimensions: "
    f"{raw.shape[0]} rows x "
    f"{raw.shape[1]} columns"
)


# =============================================================================
# 8. ACTUAL STRUCTURE OF IMPROVED WORKBOOK
# =============================================================================
#
# Inspection of the new file shows:
#
# Maturity     Date column     Rate column
#
# 10Y               1               2
#  9Y               6               7
#  8Y              11              12
#  7Y              16              17
#  6Y              21              22
#  5Y              25              26
#  4Y              29              30
#  3Y              34              35
#  2Y              39              40
#  1Y              44              45
#
# Each maturity therefore has its OWN date series.
#
# =============================================================================

SERIES_COLUMNS = {

    "10Y": (1, 2),

    "9Y": (6, 7),

    "8Y": (11, 12),

    "7Y": (16, 17),

    "6Y": (21, 22),

    "5Y": (25, 26),

    "4Y": (29, 30),

    "3Y": (34, 35),

    "2Y": (39, 40),

    "1Y": (44, 45)

}


# =============================================================================
# 9. RISK FACTORS
# =============================================================================
#
# The improved file now supports the full 1Y–10Y curve.
#
# =============================================================================

RISK_NODES = [

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


# =============================================================================
# 10. CLEAN EACH MATURITY INDEPENDENTLY
# =============================================================================

clean_series = []


for maturity, (
    date_column,
    rate_column
) in SERIES_COLUMNS.items():

    temp = raw[
        [
            date_column,
            rate_column
        ]
    ].copy()


    temp.columns = [

        "Date",

        maturity

    ]


    # ---------------------------------------------------------
    # Dates
    # ---------------------------------------------------------

    temp["Date"] = pd.to_datetime(

        temp["Date"],

        errors="coerce"

    )


    # ---------------------------------------------------------
    # Rates
    # ---------------------------------------------------------

    temp[maturity] = pd.to_numeric(

        temp[maturity],

        errors="coerce"

    )


    # ---------------------------------------------------------
    # Remove Bloomberg header rows and blank rows
    # ---------------------------------------------------------

    temp = temp.dropna(

        subset=[
            "Date",
            maturity
        ]

    )


    # ---------------------------------------------------------
    # Remove duplicate dates
    # ---------------------------------------------------------

    temp = temp.drop_duplicates(

        subset=[
            "Date"
        ],

        keep="first"

    )


    # ---------------------------------------------------------
    # Bloomberg quotes:
    #
    # 3.25 = 3.25%
    #
    # Convert to decimal:
    #
    # 0.0325
    # ---------------------------------------------------------

    temp[maturity] = (

        temp[maturity]

        / 100

    )


    # ---------------------------------------------------------
    # Set date as index
    # ---------------------------------------------------------

    temp = temp.set_index(
        "Date"
    )


    # ---------------------------------------------------------
    # Sort oldest -> newest
    # ---------------------------------------------------------

    temp = temp.sort_index()


    clean_series.append(
        temp
    )


# =============================================================================
# 11. MERGE ALL MATURITIES BY ACTUAL DATE
# =============================================================================

rates_clean = pd.concat(

    clean_series,

    axis=1,

    join="outer"

)


rates_clean = (

    rates_clean
    .sort_index()
    [RISK_NODES]

)


# =============================================================================
# 12. DATA QUALITY / AVAILABILITY
# =============================================================================

availability = pd.DataFrame({

    "Observations":

        rates_clean.count(),

    "Missing":

        rates_clean.isna().sum(),

    "Coverage %":

        rates_clean
        .notna()
        .mean()
        * 100

})


print("\n")
print("=" * 80)

print(
    "DATA AVAILABILITY BY MATURITY"
)

print("=" * 80)


print(

    availability
    .round(2)
    .to_string()

)


print(
    "\nOverall date range:"
)


print(

    rates_clean.index
    .min()
    .date(),

    "to",

    rates_clean.index
    .max()
    .date()

)


availability.to_csv(

    TABLE_DIR
    / "data_availability.csv"

)


rates_clean.to_csv(

    CLEAN_DIR
    / "clean_swap_curve.csv"

)


# =============================================================================
# 13. CURRENT EUR SWAP CURVE
# =============================================================================
#
# Because each maturity has its own date series, use the latest
# available observation for each maturity.
#
# =============================================================================

current_curve = pd.Series({

    node:

        rates_clean[
            node
        ]
        .dropna()
        .iloc[-1]

    for node in RISK_NODES

})


current_curve_dates = pd.Series({

    node:

        rates_clean[
            node
        ]
        .dropna()
        .index[-1]

    for node in RISK_NODES

})


current_curve_table = pd.DataFrame({

    "Maturity":

        RISK_NODES,

    "Latest Date":

        [
            current_curve_dates[node].date()
            for node in RISK_NODES
        ],

    "Swap Rate %":

        [
            current_curve[node] * 100
            for node in RISK_NODES
        ]

})


print("\n")
print("=" * 80)

print(
    "CURRENT EUR SWAP CURVE"
)

print("=" * 80)


print(

    current_curve_table
    .round(
        {
            "Swap Rate %": 5
        }
    )
    .to_string(
        index=False
    )

)


current_curve_table.to_csv(

    TABLE_DIR
    / "current_swap_curve.csv",

    index=False

)


# =============================================================================
# 14. CURRENT CURVE CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(9, 5)

)


ax.plot(

    RISK_NODES,

    current_curve[
        RISK_NODES
    ].values
    * 100,

    marker="o"

)


ax.set_title(

    "Current EUR Swap Curve"

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
    / "01_current_curve.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 15. HISTORICAL RATE CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(12, 7)

)


for node in RISK_NODES:

    ax.plot(

        rates_clean.index,

        rates_clean[node]
        * 100,

        label=node,

        linewidth=0.8

    )


ax.set_title(

    "Historical EUR Swap Curve Rates"

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
    / "02_historical_rates.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 16. CALCULATE DAILY RATE CHANGES CORRECTLY
# =============================================================================
#
# IMPORTANT:
#
# Because each maturity has its own date series, calculating diff()
# on the merged outer-join dataframe could incorrectly treat a
# multi-day missing interval as one daily observation.
#
# Therefore daily changes are calculated maturity-by-maturity from
# each maturity's own observed dates.
#
# Friday -> Monday is allowed.
#
# Changes spanning more than 4 calendar days are excluded.
#
# =============================================================================

MAX_CALENDAR_GAP = 4

daily_change_series = []


for node in RISK_NODES:

    temp = (

        rates_clean[
            node
        ]
        .dropna()
        .to_frame(
            name=node
        )

    )


    date_gap = (

        temp.index
        .to_series()
        .diff()
        .dt.days

    )


    change = (

        temp[node]
        .diff()

    )


    change = change.where(

        date_gap
        <= MAX_CALENDAR_GAP

    )


    change.name = node


    daily_change_series.append(
        change
    )


# Merge the independently calculated daily changes

daily_changes = pd.concat(

    daily_change_series,

    axis=1,

    join="outer"

)


daily_changes = (

    daily_changes
    .sort_index()
    [RISK_NODES]

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
    / "daily_rate_changes_bp.csv"

)


# =============================================================================
# 17. VALID DAILY CHANGES
# =============================================================================

change_availability = pd.DataFrame({

    "Valid Daily Changes":

        daily_changes.count(),

    "Missing":

        daily_changes.isna().sum()

})


print("\n")
print("=" * 80)

print(
    "VALID DAILY RATE CHANGES"
)

print("=" * 80)


print(

    change_availability
    .to_string()

)


change_availability.to_csv(

    TABLE_DIR
    / "valid_daily_changes.csv"

)


# =============================================================================
# 18. VOLATILITY
# =============================================================================

daily_volatility = (

    daily_changes.std()

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
    "INTEREST-RATE VOLATILITY"
)

print("=" * 80)


print(

    volatility_table
    .round(3)
    .to_string()

)


volatility_table.to_csv(

    TABLE_DIR
    / "volatility.csv"

)


# =============================================================================
# 19. VOLATILITY CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(10, 5)

)


ax.bar(

    RISK_NODES,

    ten_day_volatility_bp[
        RISK_NODES
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
    / "03_volatility.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 20. COVARIANCE AND CORRELATION
# =============================================================================
#
# Pairwise available observations are used.
#
# =============================================================================

daily_covariance = (

    daily_changes[
        RISK_NODES
    ]
    .cov(
        min_periods=100
    )

)


correlation = (

    daily_changes[
        RISK_NODES
    ]
    .corr(
        min_periods=100
    )

)


daily_covariance.to_csv(

    TABLE_DIR
    / "daily_covariance.csv"

)


correlation.to_csv(

    TABLE_DIR
    / "correlation.csv"

)


# =============================================================================
# 21. CORRELATION HEATMAP
# =============================================================================

fig, ax = plt.subplots(

    figsize=(10, 9)

)


image = ax.imshow(

    correlation.values,

    aspect="auto"

)


ax.set_xticks(

    range(
        len(
            RISK_NODES
        )
    )

)


ax.set_yticks(

    range(
        len(
            RISK_NODES
        )
    )

)


ax.set_xticklabels(

    RISK_NODES,

    rotation=45,

    ha="right"

)


ax.set_yticklabels(
    RISK_NODES
)


for i in range(
    len(RISK_NODES)
):

    for j in range(
        len(RISK_NODES)
    ):

        value = correlation.iloc[
            i,
            j
        ]

        if pd.notna(value):

            ax.text(

                j,

                i,

                f"{value:.2f}",

                ha="center",

                va="center",

                fontsize=7

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
    / "04_correlation_heatmap.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 22. DEFINE AGGREGATE EUR CURVE LEVEL FACTOR
# =============================================================================
#
# Vonovia's exact maturity distribution is unavailable.
#
# Therefore the simplified portfolio is represented as exposure to the
# overall EUR curve level.
#
# The daily level factor is the average observed rate movement across
# the ten maturity nodes on each date.
#
# =============================================================================

level_changes = (

    daily_changes[
        RISK_NODES
    ]
    .mean(
        axis=1,
        skipna=True
    )
    .dropna()

)


level_changes_bp = (

    level_changes

    * 10_000

)


daily_level_sigma = (

    level_changes.std()

)


ten_day_level_sigma = (

    daily_level_sigma

    * np.sqrt(
        VAR_HORIZON_DAYS
    )

)


print("\n")
print("=" * 80)

print(
    "AGGREGATE EUR CURVE LEVEL FACTOR"
)

print("=" * 80)


print(

    f"Daily level volatility: "
    f"{level_changes_bp.std():.3f} bp"

)


print(

    f"10-day level volatility: "
    f"{ten_day_level_sigma * 10_000:.3f} bp"

)


# =============================================================================
# 23. PORTFOLIO PV SENSITIVITY
# =============================================================================
#
# Approximate duration relationship:
#
# Asset:
#
#       Delta PV / PV ≈ -D × Delta y
#
#
# Vonovia debt is a liability.
#
# From Vonovia's economic perspective:
#
# rates rise
#
#       ->
#
# market value of debt falls
#
#       ->
#
# liability becomes less negative
#
#       ->
#
# economic gain
#
#
# Therefore:
#
#       P&L ≈ + Debt × Duration × Delta y
#
# =============================================================================

def debt_pnl_from_rate_change(

    rate_change,

    duration

):

    return (

        TOTAL_DEBT

        * duration

        * rate_change

    )


# =============================================================================
# 24. BASE-CASE DV01
# =============================================================================

BASE_DV01 = (

    TOTAL_DEBT

    * BASE_DURATION

    * 0.0001

)


print(

    f"\nBase-case modified duration: "
    f"{BASE_DURATION:.1f}"
)


print(

    f"Approximate debt DV01: "
    f"EUR {BASE_DV01:,.0f} per bp"
)


# =============================================================================
# 25. DELTA-NORMAL VaR
# =============================================================================

delta_pnl_sigma = (

    TOTAL_DEBT

    * BASE_DURATION

    * ten_day_level_sigma

)


DELTA_VAR = (

    Z_95

    * delta_pnl_sigma

)


# =============================================================================
# 26. DELTA-NORMAL EXPECTED SHORTFALL
# =============================================================================

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


DELTA_ES = (

    delta_pnl_sigma

    * normal_density

    /

    (
        1
        - CONFIDENCE_LEVEL
    )

)


# Distribution generated only for visualisation

delta_pnl = rng.normal(

    loc=0,

    scale=delta_pnl_sigma,

    size=N_SIMULATIONS

)


# =============================================================================
# 27. MAKE COVARIANCE MATRIX POSITIVE SEMIDEFINITE
# =============================================================================

def nearest_psd(
    matrix
):

    matrix = np.asarray(

        matrix,

        dtype=float

    )


    matrix = (

        matrix

        + matrix.T

    ) / 2


    eigenvalues, eigenvectors = (

        np.linalg.eigh(
            matrix
        )

    )


    eigenvalues = np.maximum(

        eigenvalues,

        1e-12

    )


    repaired = (

        eigenvectors

        @ np.diag(
            eigenvalues
        )

        @ eigenvectors.T

    )


    return repaired


daily_cov_matrix = (

    nearest_psd(

        daily_covariance
        .loc[
            RISK_NODES,
            RISK_NODES
        ]
        .values

    )

)


ten_day_cov_matrix = (

    daily_cov_matrix

    * VAR_HORIZON_DAYS

)


# =============================================================================
# 28. MONTE CARLO CURVE SHOCKS
# =============================================================================

mc_curve_shocks = (

    rng.multivariate_normal(

        mean=np.zeros(
            len(
                RISK_NODES
            )
        ),

        cov=ten_day_cov_matrix,

        size=N_SIMULATIONS

    )

)


# =============================================================================
# 29. MONTE CARLO LEVEL SHOCK
# =============================================================================

mc_level_shock = (

    mc_curve_shocks.mean(
        axis=1
    )

)


# =============================================================================
# 30. MONTE CARLO PORTFOLIO P&L
# =============================================================================

mc_pnl = (

    TOTAL_DEBT

    * BASE_DURATION

    * mc_level_shock

)


# =============================================================================
# 31. GENERIC VaR + EXPECTED SHORTFALL FUNCTION
# =============================================================================

def calculate_var_es(
    pnl
):

    pnl = np.asarray(
        pnl,
        dtype=float
    )


    cutoff = np.quantile(

        pnl,

        1
        - CONFIDENCE_LEVEL

    )


    var = -cutoff


    tail = pnl[
        pnl <= cutoff
    ]


    es = -tail.mean()


    return (

        var,

        es,

        cutoff

    )


(
    MC_VAR,
    MC_ES,
    MC_CUTOFF

) = calculate_var_es(
    mc_pnl
)


# =============================================================================
# 32. MONTE CARLO CURVE SCENARIO CHART
# =============================================================================

simulated_curves = (

    current_curve[
        RISK_NODES
    ].values

    +

    mc_curve_shocks

)


fig, ax = plt.subplots(

    figsize=(10, 6)

)


x = np.arange(
    len(
        RISK_NODES
    )
)


ax.plot(

    x,

    current_curve[
        RISK_NODES
    ].values
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

        simulated_curves[i]
        * 100,

        linewidth=0.7,

        alpha=0.4

    )


ax.set_xticks(
    x
)


ax.set_xticklabels(
    RISK_NODES
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
    / "05_monte_carlo_curves.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 33. PCA DATASET
# =============================================================================
#
# PCA requires all maturity changes to be available simultaneously.
#
# With the improved dataset this should retain substantially more
# observations than the old workbook.
#
# =============================================================================

pca_changes = (

    daily_changes[
        RISK_NODES
    ]
    .dropna(
        how="any"
    )

)


print("\n")
print("=" * 80)

print(
    "PCA / GARCH CALIBRATION SAMPLE"
)

print("=" * 80)


print(

    f"Common observations: "
    f"{len(pca_changes):,}"
)


# =============================================================================
# 34. PCA FUNCTION
# =============================================================================

def run_pca(

    changes,

    factors=3

):

    X = np.asarray(

        changes,

        dtype=float

    )


    means = X.mean(
        axis=0
    )


    stds = X.std(
        axis=0,
        ddof=1
    )


    if np.any(
        stds == 0
    ):

        raise ValueError(

            "At least one curve node "
            "has zero volatility."

        )


    Z = (

        X - means

    ) / stds


    covariance = np.cov(

        Z,

        rowvar=False

    )


    eigenvalues, eigenvectors = (

        np.linalg.eigh(
            covariance
        )

    )


    order = np.argsort(

        eigenvalues

    )[::-1]


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


    explained = (

        eigenvalues

        / eigenvalues.sum()

    )


    loadings = (

        eigenvectors[
            :,
            :factors
        ]

    )


    scores = (

        Z

        @ loadings

    )


    return {

        "means":
            means,

        "stds":
            stds,

        "explained":
            explained,

        "loadings":
            loadings,

        "scores":
            scores

    }


pca = run_pca(

    pca_changes,

    factors=3

)


# =============================================================================
# 35. PCA RESULTS
# =============================================================================

print("\n")
print("=" * 80)

print(
    "PCA"
)

print("=" * 80)


for i in range(3):

    print(

        f"Factor {i + 1}: "
        f"{pca['explained'][i]:.2%}"

    )


print(

    f"First 3 factors cumulative: "
    f"{pca['explained'][:3].sum():.2%}"

)


# =============================================================================
# 36. PCA TABLE
# =============================================================================

pca_table = pd.DataFrame({

    "Factor": [

        "Factor 1",

        "Factor 2",

        "Factor 3"

    ],

    "Explained Variance %":

        pca[
            "explained"
        ][:3]
        * 100

})


pca_table[
    "Cumulative %"
] = (

    pca_table[
        "Explained Variance %"
    ]
    .cumsum()

)


pca_table.to_csv(

    TABLE_DIR
    / "pca_explained_variance.csv",

    index=False

)


# =============================================================================
# 37. PCA EXPLAINED-VARIANCE CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(8, 5)

)


ax.bar(

    pca_table[
        "Factor"
    ],

    pca_table[
        "Explained Variance %"
    ]

)


ax.set_title(

    "PCA: Variance Explained by EUR Curve Factors"

)


ax.set_ylabel(

    "Explained Variance (%)"

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "06_pca_explained_variance.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 38. PCA LOADINGS TABLE
# =============================================================================

pca_loadings = pd.DataFrame(

    pca[
        "loadings"
    ],

    index=RISK_NODES,

    columns=[

        "Factor 1",

        "Factor 2",

        "Factor 3"

    ]

)


pca_loadings.to_csv(

    TABLE_DIR
    / "pca_loadings.csv"

)


# =============================================================================
# 39. GARCH FUNCTIONS
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


    h = np.empty(
        len(x)
    )


    h[0] = max(

        np.var(
            x,
            ddof=1
        ),

        1e-12

    )


    for t in range(
        1,
        len(x)
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


    return (

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


def fit_garch(
    series
):

    x = np.asarray(

        series,

        dtype=float

    )


    variance = np.var(

        x,

        ddof=1

    )


    best = None


    for alpha in np.linspace(

        0.03,

        0.20,

        8

    ):

        for beta in np.linspace(

            0.70,

            0.96,

            14

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


            ll = garch_loglikelihood(

                x,

                omega,

                alpha,

                beta

            )


            if (

                best is None

                or

                ll
                > best[
                    "ll"
                ]

            ):

                best = {

                    "omega":
                        omega,

                    "alpha":
                        alpha,

                    "beta":
                        beta,

                    "ll":
                        ll

                }


    if best is None:

        raise RuntimeError(

            "GARCH calibration failed."

        )


    h = garch_variance_path(

        x,

        best[
            "omega"
        ],

        best[
            "alpha"
        ],

        best[
            "beta"
        ]

    )


    best[
        "last_variance"
    ] = (

        h[-1]

    )


    return best


# =============================================================================
# 40. FIT THREE GARCH MODELS
# =============================================================================

garch_models = [

    fit_garch(

        pca[
            "scores"
        ][:, i]

    )

    for i in range(
        3
    )

]


garch_table = pd.DataFrame({

    "Factor": [

        "Factor 1",

        "Factor 2",

        "Factor 3"

    ],

    "Omega": [

        model[
            "omega"
        ]

        for model in garch_models

    ],

    "Alpha": [

        model[
            "alpha"
        ]

        for model in garch_models

    ],

    "Beta": [

        model[
            "beta"
        ]

        for model in garch_models

    ],

    "Alpha + Beta": [

        (
            model[
                "alpha"
            ]

            +

            model[
                "beta"
            ]
        )

        for model in garch_models

    ]

})


print("\n")
print("=" * 80)

print(
    "GARCH CALIBRATION"
)

print("=" * 80)


print(

    garch_table
    .round(6)
    .to_string(
        index=False
    )

)


garch_table.to_csv(

    TABLE_DIR
    / "garch_calibration.csv",

    index=False

)


# =============================================================================
# 41. GARCH SIMULATION FUNCTION
# =============================================================================

def simulate_garch_factor(

    model,

    simulations,

    days

):

    variance = np.full(

        simulations,

        model[
            "last_variance"
        ]

    )


    previous_shock = np.zeros(
        simulations
    )


    cumulative = np.zeros(
        simulations
    )


    for _ in range(
        days
    ):

        variance = (

            model[
                "omega"
            ]

            +

            model[
                "alpha"
            ]
            * previous_shock ** 2

            +

            model[
                "beta"
            ]
            * variance

        )


        variance = np.maximum(

            variance,

            1e-12

        )


        shock = (

            np.sqrt(
                variance
            )

            * rng.normal(
                size=simulations
            )

        )


        cumulative += (
            shock
        )


        previous_shock = (
            shock
        )


    return cumulative


# =============================================================================
# 42. GENERATE GARCH FACTOR SHOCKS
# =============================================================================

garch_factor_shocks = np.column_stack([

    simulate_garch_factor(

        model,

        N_SIMULATIONS,

        VAR_HORIZON_DAYS

    )

    for model in garch_models

])


# =============================================================================
# 43. RECONSTRUCT GARCH CURVE SHOCKS
# =============================================================================

standardised_garch_shocks = (

    garch_factor_shocks

    @ pca[
        "loadings"
    ].T

)


garch_curve_shocks = (

    standardised_garch_shocks

    * pca[
        "stds"
    ]

)


# =============================================================================
# 44. GARCH LEVEL SHOCK
# =============================================================================

garch_level_shock = (

    garch_curve_shocks.mean(
        axis=1
    )

)


# =============================================================================
# 45. GARCH PORTFOLIO P&L
# =============================================================================

garch_pnl = (

    TOTAL_DEBT

    * BASE_DURATION

    * garch_level_shock

)


(
    GARCH_VAR,
    GARCH_ES,
    GARCH_CUTOFF

) = calculate_var_es(
    garch_pnl
)


# =============================================================================
# 46. P&L DISTRIBUTION PLOT FUNCTION
# =============================================================================

def plot_distribution(

    pnl,

    var,

    es,

    title,

    filename

):

    pnl_m = (

        np.asarray(
            pnl
        )

        / 1_000_000

    )


    fig, ax = plt.subplots(

        figsize=(10, 6)

    )


    ax.hist(

        pnl_m,

        bins=100

    )


    ax.axvline(

        -var
        / 1_000_000,

        linestyle="--",

        linewidth=2,

        label=(

            f"95% VaR = "
            f"EUR {var / 1e6:.1f}m"

        )

    )


    ax.set_title(
        title
    )


    ax.set_xlabel(

        "10-Day P&L (EUR millions)"

    )


    ax.set_ylabel(

        "Frequency"

    )


    ax.legend()


    plt.tight_layout()


    fig.savefig(

        CHART_DIR
        / filename,

        dpi=200,

        bbox_inches="tight"

    )


    plt.close(fig)


# =============================================================================
# 47. THREE P&L DISTRIBUTIONS
# =============================================================================

plot_distribution(

    delta_pnl,

    DELTA_VAR,

    DELTA_ES,

    "Delta-Normal — Vonovia 10-Day P&L Distribution",

    "07_delta_normal_distribution.png"

)


plot_distribution(

    mc_pnl,

    MC_VAR,

    MC_ES,

    "Monte Carlo — Vonovia 10-Day P&L Distribution",

    "08_monte_carlo_distribution.png"

)


plot_distribution(

    garch_pnl,

    GARCH_VAR,

    GARCH_ES,

    "PCA + GARCH — Vonovia 10-Day P&L Distribution",

    "09_garch_distribution.png"

)


# =============================================================================
# 48. FINAL BASE-CASE RESULTS
# =============================================================================

results = pd.DataFrame({

    "Method": [

        "Delta-Normal",

        "Monte Carlo",

        "PCA + GARCH"

    ],

    "10-Day 95% VaR EUR": [

        DELTA_VAR,

        MC_VAR,

        GARCH_VAR

    ],

    "95% Expected Shortfall EUR": [

        DELTA_ES,

        MC_ES,

        GARCH_ES

    ]

})


results[
    "VaR EUR m"
] = (

    results[
        "10-Day 95% VaR EUR"
    ]

    / 1_000_000

)


results[
    "ES EUR m"
] = (

    results[
        "95% Expected Shortfall EUR"
    ]

    / 1_000_000

)


print("\n")
print("=" * 80)

print(
    "BASE-CASE VaR RESULTS"
)

print("=" * 80)


print(

    results[
        [
            "Method",
            "VaR EUR m",
            "ES EUR m"
        ]
    ]
    .round(2)
    .to_string(
        index=False
    )

)


results.to_csv(

    RESULT_DIR
    / "base_case_var_results.csv",

    index=False

)


# =============================================================================
# 49. VaR METHOD COMPARISON CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(9, 6)

)


ax.bar(

    results[
        "Method"
    ],

    results[
        "VaR EUR m"
    ]

)


ax.set_title(

    "Vonovia 10-Day 95% Interest-Rate VaR"

)


ax.set_ylabel(

    "VaR (EUR millions)"

)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "10_var_method_comparison.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 50. DURATION SENSITIVITY ANALYSIS
# =============================================================================

duration_results = []


for scenario, duration in (

    DURATION_SCENARIOS.items()

):

    # ---------------------------------------------------------
    # Delta-Normal
    # ---------------------------------------------------------

    delta_sigma_d = (

        TOTAL_DEBT

        * duration

        * ten_day_level_sigma

    )


    delta_var_d = (

        Z_95

        * delta_sigma_d

    )


    # ---------------------------------------------------------
    # Monte Carlo
    # ---------------------------------------------------------

    mc_pnl_d = (

        TOTAL_DEBT

        * duration

        * mc_level_shock

    )


    mc_var_d = (

        -np.quantile(

            mc_pnl_d,

            0.05

        )

    )


    # ---------------------------------------------------------
    # GARCH
    # ---------------------------------------------------------

    garch_pnl_d = (

        TOTAL_DEBT

        * duration

        * garch_level_shock

    )


    garch_var_d = (

        -np.quantile(

            garch_pnl_d,

            0.05

        )

    )


    duration_results.append({

        "Scenario":

            scenario,

        "Duration":

            duration,

        "Delta-Normal VaR EUR m":

            delta_var_d
            / 1_000_000,

        "Monte Carlo VaR EUR m":

            mc_var_d
            / 1_000_000,

        "GARCH VaR EUR m":

            garch_var_d
            / 1_000_000

    })


duration_table = pd.DataFrame(

    duration_results

)


print("\n")
print("=" * 80)

print(
    "DURATION SENSITIVITY"
)

print("=" * 80)


print(

    duration_table
    .round(2)
    .to_string(
        index=False
    )

)


duration_table.to_csv(

    RESULT_DIR
    / "duration_sensitivity.csv",

    index=False

)


# =============================================================================
# 51. DURATION SENSITIVITY CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(10, 6)

)


ax.plot(

    duration_table[
        "Duration"
    ],

    duration_table[
        "Delta-Normal VaR EUR m"
    ],

    marker="o",

    linestyle="-",

    label="Delta-Normal"

)


ax.plot(

    duration_table[
        "Duration"
    ],

    duration_table[
        "Monte Carlo VaR EUR m"
    ],

    marker="s",

    linestyle="--",

    label="Monte Carlo"

)


ax.plot(

    duration_table[
        "Duration"
    ],

    duration_table[
        "GARCH VaR EUR m"
    ],

    marker="^",

    linestyle="-.",

    label="PCA + GARCH"

)


ax.set_title(

    "VaR Sensitivity to Assumed Debt Duration"

)


ax.set_xlabel(

    "Assumed Modified Duration"

)


ax.set_ylabel(

    "10-Day 95% VaR (EUR millions)"

)


ax.legend()


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "11_duration_sensitivity.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 52. DATA DIAGNOSTICS
# =============================================================================

diagnostics = pd.DataFrame({

    "Metric": [

        "Total curve nodes",

        "Earliest market-data date",

        "Latest market-data date",

        "Minimum observations at a node",

        "Maximum observations at a node",

        "PCA common observations",

        "PCA first 3 factors cumulative variance",

        "Monte Carlo simulations",

        "Base duration assumption"

    ],

    "Value": [

        len(
            RISK_NODES
        ),

        rates_clean.index
        .min()
        .date(),

        rates_clean.index
        .max()
        .date(),

        int(
            rates_clean.count()
            .min()
        ),

        int(
            rates_clean.count()
            .max()
        ),

        len(
            pca_changes
        ),

        (
            pca[
                "explained"
            ][:3]
            .sum()
        ),

        N_SIMULATIONS,

        BASE_DURATION

    ]

})


diagnostics.to_csv(

    DIAGNOSTIC_DIR
    / "model_diagnostics.csv",

    index=False

)


# =============================================================================
# 53. CREATE CONCLUSION MARKDOWN
# =============================================================================

delta_var_m = (

    DELTA_VAR

    / 1_000_000

)


mc_var_m = (

    MC_VAR

    / 1_000_000

)


garch_var_m = (

    GARCH_VAR

    / 1_000_000

)


delta_es_m = (

    DELTA_ES

    / 1_000_000

)


mc_es_m = (

    MC_ES

    / 1_000_000

)


garch_es_m = (

    GARCH_ES

    / 1_000_000

)


pca_cumulative = (

    pca[
        "explained"
    ][:3]
    .sum()

    * 100

)


conclusion = f"""
# Vonovia SE — Interest-Rate Value at Risk

## Executive Summary

This analysis demonstrates how a corporate client can assess
interest-rate risk using Value at Risk (VaR).

The analysis considers approximately **EUR {TOTAL_DEBT/1e9:.2f} billion**
of identified Vonovia debt.

Because the available Bloomberg information does not provide sufficient
instrument-level duration, maturity, coupon and derivative information,
the analysis uses an **illustrative aggregate modified duration of
{BASE_DURATION:.1f} years**.

The results are therefore illustrative VaR estimates conditional on this
assumption rather than Vonovia's internally reported VaR.

## Market Data and Calibration

The improved Bloomberg dataset provides separate historical observations
for every annual EUR swap maturity from **1Y through 10Y**.

Each maturity was cleaned independently and aligned by actual date before
the historical rate-change statistics were calculated.

The analysis uses:

- **Confidence level:** {CONFIDENCE_LEVEL:.0%}
- **Risk horizon:** {VAR_HORIZON_DAYS} trading days
- **Monte Carlo simulations:** {N_SIMULATIONS:,}
- **Base modified duration assumption:** {BASE_DURATION:.1f} years
- **EUR swap risk factors:** {", ".join(RISK_NODES)}
- **Historical period:** {rates_clean.index.min().date()} to {rates_clean.index.max().date()}

Historical rate movements are used to estimate volatility, covariance,
correlation and common yield-curve factors.

## VaR Results — Base Case

| Method | 10-Day 95% VaR | 95% Expected Shortfall |
|---|---:|---:|
| Delta-Normal | EUR {delta_var_m:,.2f}m | EUR {delta_es_m:,.2f}m |
| Monte Carlo | EUR {mc_var_m:,.2f}m | EUR {mc_es_m:,.2f}m |
| PCA + GARCH | EUR {garch_var_m:,.2f}m | EUR {garch_es_m:,.2f}m |

## Delta-Normal

Delta-Normal VaR uses the historical volatility of the aggregate EUR
curve level together with a linear duration approximation.

### Advantages

- Simple and transparent.
- Computationally efficient.
- Easy to communicate.
- Useful for approximately linear interest-rate exposure.

### Limitations

- Assumes normally distributed P&L.
- Uses a linear duration approximation.
- Does not capture time-varying volatility.

## Monte Carlo

Monte Carlo generates **{N_SIMULATIONS:,} correlated 10-day EUR
yield-curve scenarios** using the historical covariance structure across
the 1Y–10Y swap curve.

### Advantages

- Models multiple yield-curve maturities simultaneously.
- Incorporates historical correlation.
- Produces a full P&L distribution.
- Can be extended to more detailed portfolios.

### Limitations

- Results depend on the assumed distribution of shocks.
- Historical covariance may change through time.
- Portfolio sensitivity remains simplified.

## PCA + GARCH

PCA reduces the ten-dimensional EUR yield curve to three common
statistical factors.

The first three factors explain approximately **{pca_cumulative:.2f}%**
of the standardized historical curve-change variance in this calibration.

GARCH(1,1) models time-varying conditional volatility in each of these
three factors.

### Advantages

- Allows volatility to vary through time.
- Captures volatility clustering.
- Reduces a large yield curve to a smaller set of common factors.

### Limitations

- More complex and model-dependent.
- PCA factors can change over time.
- GARCH parameters depend on the calibration sample.
- Portfolio sensitivity is still based on an assumed duration.

## Why the VaR Estimates Differ

Delta-Normal and covariance Monte Carlo use broadly similar unconditional
volatility information and may therefore produce similar results when
portfolio P&L is linear.

PCA + GARCH additionally allows volatility to evolve through time, so its
VaR may differ materially when current conditional volatility differs
from long-run historical volatility.

This demonstrates **model risk**: VaR depends on methodology and
calibration rather than being a single objective number.

## Duration Sensitivity

The 3-year, 5-year and 7-year duration scenarios demonstrate the
importance of portfolio calibration.

A longer duration produces a larger PV change for the same movement in
interest rates and therefore a larger VaR.

The duration assumption is one of the largest limitations of this
illustrative Vonovia analysis because instrument-level duration data were
not available.

## Expected Shortfall

VaR is not a maximum possible loss.

At 95% confidence, VaR identifies the threshold separating the worst 5%
of modelled outcomes from the remaining 95%.

Expected Shortfall estimates the average loss within that worst 5% tail.

## How a Corporate Client Can Assess Interest-Rate Risk

A corporate treasury can use VaR by:

1. identifying interest-rate-sensitive assets, liabilities and hedges;
2. selecting appropriate market risk factors;
3. calibrating volatility and correlation from historical market data;
4. measuring portfolio sensitivity using duration, DV01 or key-rate DV01;
5. generating a P&L distribution;
6. calculating VaR and Expected Shortfall;
7. comparing results across methodologies;
8. performing scenario, stress and sensitivity analysis.

## Recommended Risk Framework

VaR should be combined with:

- duration and DV01;
- key-rate sensitivities;
- yield-curve scenario analysis;
- stress testing;
- Expected Shortfall;
- hedge-effectiveness analysis.

## Conclusion

VaR gives corporate treasury a common quantitative measure for assessing
interest-rate risk and comparing exposures.

However, VaR depends materially on the risk horizon, confidence level,
historical sample, volatility model, correlation assumptions and the
portfolio's interest-rate sensitivity.

For this reason, VaR should be used as one component of a broader
interest-rate risk-management framework rather than interpreted as a
maximum-loss forecast.

The Vonovia results in this analysis remain illustrative because the
portfolio duration is assumed rather than derived from detailed
instrument-level debt and hedge information.
"""


CONCLUSION_FILE = (

    OUTPUT_DIR
    / "Conclusion.md"

)


CONCLUSION_FILE.write_text(

    conclusion,

    encoding="utf-8"

)


# =============================================================================
# 54. FINAL TERMINAL SUMMARY
# =============================================================================

print("\n")
print("=" * 80)

print(
    "FINAL RESULTS"
)

print("=" * 80)


print(

    results[
        [
            "Method",
            "VaR EUR m",
            "ES EUR m"
        ]
    ]
    .round(2)
    .to_string(
        index=False
    )

)


print("\n")

print(
    "Duration sensitivity:"
)


print(

    duration_table
    .round(2)
    .to_string(
        index=False
    )

)


print("\n")

print(
    "IMPORTANT:"
)


print(

    "These are illustrative VaR estimates conditional on "
    f"an assumed modified duration of {BASE_DURATION:.1f} years."

)


print(

    f"The improved market dataset uses all "
    f"{len(RISK_NODES)} annual EUR swap maturities from 1Y to 10Y."

)


print(

    f"The first three PCA factors explain "
    f"{pca_cumulative:.2f}% of standardized curve-change variance."

)


print("\n")

print(
    "Conclusion written to:"
)


print(
    CONCLUSION_FILE
)


print("\n")

print(
    "Charts written to:"
)


print(
    CHART_DIR
)


print("\n")

print("=" * 80)

print(
    "ANALYSIS COMPLETED SUCCESSFULLY"
)

print("=" * 80)