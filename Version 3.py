# =============================================================================
# VONOVIA SE — SIMPLIFIED INTEREST-RATE VaR ANALYSIS
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
# IMPORTANT:
# ----------
# This is an ILLUSTRATIVE corporate VaR model.
#
# Vonovia's identified debt amount comes from the supplied Bloomberg data.
#
# Bloomberg did NOT provide sufficient instrument-level duration,
# maturity, coupon or derivative information.
#
# Therefore the model explicitly assumes:
#
#   Base modified duration = 5 years
#
# and also reports:
#
#   Low duration  = 3 years
#   Base duration = 5 years
#   High duration = 7 years
#
# These are MODELLING ASSUMPTIONS, not reported Vonovia durations.
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

Z_95 = 1.6448536269514722

rng = np.random.default_rng(
    RANDOM_SEED
)


# =============================================================================
# 3. SIMPLIFIED VONOVIA EXPOSURE ASSUMPTIONS
# =============================================================================

# Identified Bloomberg debt exposure

TOTAL_DEBT = (
    31_387.86
    * 1_000_000
)


# Duration sensitivity analysis

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

RATE_FILE = (
    PROJECT_DIR
    / "Swap Curve EURIBOR.xlsx"
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


for folder in [

    OUTPUT_DIR,
    CHART_DIR,
    TABLE_DIR,
    CLEAN_DIR,
    RESULT_DIR

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


# =============================================================================
# 6. LOAD BLOOMBERG EURIBOR SWAP CURVE
# =============================================================================

if not RATE_FILE.exists():

    raise FileNotFoundError(
        RATE_FILE
    )


raw = pd.read_excel(

    RATE_FILE,

    sheet_name="Sheet1",

    header=None

)


# =============================================================================
# 7. EXTRACT ACTUAL BLOOMBERG COLUMNS
# =============================================================================

rates = raw[
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
# 8. CLEAN DATA
# =============================================================================

rates["Date"] = pd.to_datetime(

    rates["Date"],

    errors="coerce"

)


rates = rates.dropna(
    subset=["Date"]
)


ALL_NODES = [

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


for node in ALL_NODES:

    rates[node] = pd.to_numeric(

        rates[node],

        errors="coerce"

    )


rates = (

    rates
    .drop_duplicates(
        subset=["Date"]
    )
    .sort_values("Date")
    .set_index("Date")

)


# =============================================================================
# 9. SELECT ROBUST CURVE NODES
# =============================================================================
#
# 6Y and 9Y are excluded because Bloomberg provides
# very limited historical observations for them.
#
# =============================================================================

RISK_NODES = [

    "1Y",
    "2Y",
    "3Y",
    "4Y",
    "5Y",
    "7Y",
    "8Y",
    "10Y"

]


# Bloomberg rates are percentages:
#
# 3.25 = 3.25%
#
# Convert to decimal.

rates = (

    rates[
        RISK_NODES
    ]

    / 100

)


# =============================================================================
# 10. HANDLE SHORT MISSING DATA GAPS
# =============================================================================
#
# Only very short missing stretches are forward-filled.
#
# We do NOT fill long historical gaps.
#
# =============================================================================

MAX_FILL_GAP = 3


rates_clean = rates.ffill(

    limit=MAX_FILL_GAP

)


rates_clean.to_csv(

    CLEAN_DIR
    / "clean_euribor_curve.csv"

)


# =============================================================================
# 11. CALCULATE DAILY RATE CHANGES
# =============================================================================

daily_changes = (

    rates_clean
    .diff()

)


# =============================================================================
# 12. REMOVE CHANGES ACROSS LARGE CALENDAR GAPS
# =============================================================================

calendar_gap = (

    rates_clean.index
    .to_series()
    .diff()
    .dt.days

)


valid_gap = (
    calendar_gap <= 4
)


daily_changes = (

    daily_changes
    .loc[
        valid_gap
    ]

)


daily_changes_bp = (

    daily_changes

    * 10_000

)


daily_changes_bp.to_csv(

    CLEAN_DIR
    / "daily_rate_changes_bp.csv"

)


# =============================================================================
# 13. DATA AVAILABILITY
# =============================================================================

availability = pd.DataFrame({

    "Valid Daily Changes":

        daily_changes.count(),

    "Missing":

        daily_changes.isna().sum()

})


print("\n")
print("=" * 80)

print(
    "DATA AVAILABILITY"
)

print("=" * 80)


print(
    availability.to_string()
)


availability.to_csv(

    TABLE_DIR
    / "data_availability.csv"

)


# =============================================================================
# 14. VOLATILITY
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
# 15. VOLATILITY CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(9, 5)

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
    / "01_volatility.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 16. COVARIANCE AND CORRELATION
# =============================================================================

daily_covariance = (

    daily_changes.cov(
        min_periods=100
    )

)


correlation = (

    daily_changes.corr(
        min_periods=100
    )

)


daily_covariance.to_csv(

    TABLE_DIR
    / "covariance.csv"

)


correlation.to_csv(

    TABLE_DIR
    / "correlation.csv"

)


# =============================================================================
# 17. CORRELATION HEATMAP
# =============================================================================

fig, ax = plt.subplots(

    figsize=(9, 8)

)


image = ax.imshow(

    correlation.values,

    aspect="auto"

)


ax.set_xticks(
    range(len(RISK_NODES))
)

ax.set_yticks(
    range(len(RISK_NODES))
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

        ax.text(

            j,

            i,

            f"{correlation.iloc[i,j]:.2f}",

            ha="center",

            va="center",

            fontsize=8

        )


ax.set_title(

    "Correlation of EUR Swap-Rate Changes"

)


fig.colorbar(
    image,
    ax=ax
)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "02_correlation_heatmap.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 18. CURRENT EUR CURVE
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


fig, ax = plt.subplots(

    figsize=(9, 5)

)


ax.plot(

    RISK_NODES,

    current_curve.values
    * 100,

    marker="o"

)


ax.set_title(

    "Current EURIBOR Swap Curve"

)


ax.set_xlabel(
    "Maturity"
)

ax.set_ylabel(
    "Swap Rate (%)"
)


plt.tight_layout()


fig.savefig(

    CHART_DIR
    / "03_current_curve.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 19. DEFINE THE AGGREGATE "LEVEL" RISK FACTOR
# =============================================================================
#
# Because Vonovia's exact maturity distribution is unavailable,
# the simplified portfolio is exposed to the overall EUR curve level.
#
# We define the daily level change as the cross-sectional average
# movement across available curve nodes.
#
# This is more transparent than pretending to know Vonovia's exact
# key-rate DV01 allocation.
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
    f"{level_changes_bp.std() * np.sqrt(10):.3f} bp"

)


# =============================================================================
# 20. PORTFOLIO PV SENSITIVITY
# =============================================================================
#
# Approximate duration relationship:
#
# For an ASSET:
#
#       Delta PV / PV ≈ -D × Delta y
#
#
# But Vonovia's debt is a LIABILITY.
#
# From Vonovia's economic perspective:
#
# rates rise
#
#       ↓
#
# market value of debt falls
#
#       ↓
#
# liability becomes less negative
#
#       ↓
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
# 21. BASE-CASE DV01
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
# 22. DELTA-NORMAL VaR
# =============================================================================
#
# Historical daily level volatility:
#
#       sigma_daily
#
#
# 10-day:
#
#       sigma_10
#
#       =
#
#       sigma_daily × sqrt(10)
#
#
# Portfolio P&L volatility:
#
#       sigma_P
#
#       =
#
#       Debt × Duration × sigma_rate
#
#
# =============================================================================

daily_level_sigma = (

    level_changes.std()

)


ten_day_level_sigma = (

    daily_level_sigma

    * np.sqrt(
        VAR_HORIZON_DAYS
    )

)


delta_pnl_sigma = (

    TOTAL_DEBT

    * BASE_DURATION

    * ten_day_level_sigma

)


DELTA_VAR = (

    Z_95

    * delta_pnl_sigma

)


# Normal Expected Shortfall

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


# Generate a distribution for plotting.

delta_pnl = rng.normal(

    loc=0,

    scale=delta_pnl_sigma,

    size=N_SIMULATIONS

)


# =============================================================================
# 23. MONTE CARLO COVARIANCE MATRIX
# =============================================================================
#
# Pairwise covariance may be slightly non-positive-semidefinite.
#
# Repair eigenvalues if necessary.
#
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


    return (

        eigenvectors

        @ np.diag(
            eigenvalues
        )

        @ eigenvectors.T

    )


daily_cov_matrix = (

    nearest_psd(

        daily_covariance[
            RISK_NODES
        ]
        .loc[
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
# 24. MONTE CARLO CURVE SHOCKS
# =============================================================================

mc_curve_shocks = (

    rng.multivariate_normal(

        mean=np.zeros(
            len(RISK_NODES)
        ),

        cov=ten_day_cov_matrix,

        size=N_SIMULATIONS

    )

)


# =============================================================================
# 25. MONTE CARLO LEVEL SHOCK
# =============================================================================
#
# Simplified portfolio responds to the average movement of the curve.
#
# =============================================================================

mc_level_shock = (

    mc_curve_shocks.mean(
        axis=1
    )

)


# =============================================================================
# 26. MONTE CARLO PORTFOLIO P&L
# =============================================================================

mc_pnl = (

    TOTAL_DEBT

    * BASE_DURATION

    * mc_level_shock

)


# =============================================================================
# 27. VaR FUNCTION
# =============================================================================

def calculate_var_es(
    pnl
):

    pnl = np.asarray(
        pnl
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
# 28. PCA DATASET
# =============================================================================
#
# PCA needs a common dataset.
#
# Remaining missing observations are removed only for PCA/GARCH.
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


# =============================================================================
# 29. PCA FUNCTION
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


print("\n")
print("=" * 80)

print(
    "PCA"
)

print("=" * 80)


for i in range(3):

    print(

        f"Factor {i+1}: "
        f"{pca['explained'][i]:.2%}"

    )


# =============================================================================
# 30. PCA EXPLAINED-VARIANCE CHART
# =============================================================================

fig, ax = plt.subplots(

    figsize=(8, 5)

)


ax.bar(

    [
        "Factor 1",
        "Factor 2",
        "Factor 3"
    ],

    pca[
        "explained"
    ][:3]
    * 100

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
    / "04_pca_explained_variance.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 31. GARCH FUNCTIONS
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
            * x[t-1] ** 2

            +

            beta
            * h[t-1]

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

                ll > best["ll"]
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

        best["omega"],

        best["alpha"],

        best["beta"]

    )


    best[
        "last_variance"
    ] = h[-1]


    return best


# =============================================================================
# 32. FIT THREE GARCH MODELS
# =============================================================================

garch_models = [

    fit_garch(

        pca[
            "scores"
        ][:, i]

    )

    for i in range(3)

]


garch_table = pd.DataFrame({

    "Factor": [

        "Factor 1",
        "Factor 2",
        "Factor 3"

    ],

    "Omega": [

        x["omega"]

        for x in garch_models

    ],

    "Alpha": [

        x["alpha"]

        for x in garch_models

    ],

    "Beta": [

        x["beta"]

        for x in garch_models

    ]

})


print("\n")
print("=" * 80)

print(
    "GARCH CALIBRATION"
)

print("=" * 80)


print(

    garch_table.to_string(
        index=False
    )

)


garch_table.to_csv(

    TABLE_DIR
    / "garch_calibration.csv",

    index=False

)


# =============================================================================
# 33. GARCH SIMULATION FUNCTION
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


    for _ in range(days):


        variance = (

            model["omega"]

            +

            model["alpha"]
            * previous_shock ** 2

            +

            model["beta"]
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


        cumulative += shock


        previous_shock = shock


    return cumulative


# =============================================================================
# 34. GENERATE GARCH FACTOR SHOCKS
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
# 35. RECONSTRUCT GARCH CURVE SHOCKS
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
# 36. GARCH LEVEL SHOCK
# =============================================================================

garch_level_shock = (

    garch_curve_shocks.mean(
        axis=1
    )

)


# =============================================================================
# 37. GARCH PORTFOLIO P&L
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
# 38. DISTRIBUTION PLOT FUNCTION
# =============================================================================

def plot_distribution(

    pnl,

    var,

    es,

    title,

    filename

):

    pnl_m = (

        np.asarray(pnl)

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
# 39. THREE VaR DISTRIBUTIONS
# =============================================================================

plot_distribution(

    delta_pnl,

    DELTA_VAR,

    DELTA_ES,

    "Delta-Normal — Vonovia 10-Day P&L Distribution",

    "05_delta_normal_distribution.png"

)


plot_distribution(

    mc_pnl,

    MC_VAR,

    MC_ES,

    "Monte Carlo — Vonovia 10-Day P&L Distribution",

    "06_monte_carlo_distribution.png"

)


plot_distribution(

    garch_pnl,

    GARCH_VAR,

    GARCH_ES,

    "PCA + GARCH — Vonovia 10-Day P&L Distribution",

    "07_garch_distribution.png"

)


# =============================================================================
# 40. FINAL BASE-CASE RESULTS
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
# 41. VaR METHOD COMPARISON CHART
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
    / "08_var_method_comparison.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 42. DURATION SENSITIVITY ANALYSIS
# =============================================================================
#
# VaR is approximately linear in duration under this simplified model.
#
# Recalculate all three methods for:
#
#       Duration = 3
#
#       Duration = 5
#
#       Duration = 7
#
# =============================================================================

duration_results = []


for scenario, duration in (

    DURATION_SCENARIOS.items()

):


    # Delta-Normal

    delta_sigma_d = (

        TOTAL_DEBT

        * duration

        * ten_day_level_sigma

    )


    delta_var_d = (

        Z_95

        * delta_sigma_d

    )


    # Monte Carlo

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


    # GARCH

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
# 43. DURATION SENSITIVITY CHART
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

    label="Delta-Normal"

)


ax.plot(

    duration_table[
        "Duration"
    ],

    duration_table[
        "Monte Carlo VaR EUR m"
    ],

    marker="o",

    label="Monte Carlo"

)


ax.plot(

    duration_table[
        "Duration"
    ],

    duration_table[
        "GARCH VaR EUR m"
    ],

    marker="o",

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
    / "09_duration_sensitivity.png",

    dpi=200,

    bbox_inches="tight"

)


plt.close(fig)


# =============================================================================
# 44. CREATE CONCLUSION MARKDOWN FILE
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

The results must therefore be interpreted as **illustrative VaR estimates
conditional on the stated assumptions**, rather than Vonovia's internally
reported VaR.

## Risk Definition

Interest-rate risk arises because changes in market interest rates change
the present value of future contractual cash flows.

For debt liabilities, a decline in interest rates generally increases the
market value of the liability, producing an adverse change in net PV from
the corporate issuer's perspective.

VaR summarises the potential adverse change in portfolio value over a
specified horizon and confidence level.

This analysis uses:

- **Confidence level:** {CONFIDENCE_LEVEL:.0%}
- **Risk horizon:** {VAR_HORIZON_DAYS} trading days
- **Monte Carlo simulations:** {N_SIMULATIONS:,}
- **Base modified duration assumption:** {BASE_DURATION:.1f} years

## Market Risk Factors

The EUR swap curve is represented by:

**1Y, 2Y, 3Y, 4Y, 5Y, 7Y, 8Y and 10Y**

6Y and 9Y were excluded because the supplied Bloomberg dataset contained
insufficient historical observations at those maturities.

Historical rate movements were used to estimate:

- volatility;
- covariance;
- correlation;
- common yield-curve factors;
- conditional volatility.

## VaR Results — Base Case

| Method | 10-Day 95% VaR | 95% Expected Shortfall |
|---|---:|---:|
| Delta-Normal | EUR {delta_var_m:,.2f}m | EUR {delta_es_m:,.2f}m |
| Monte Carlo | EUR {mc_var_m:,.2f}m | EUR {mc_es_m:,.2f}m |
| PCA + GARCH | EUR {garch_var_m:,.2f}m | EUR {garch_es_m:,.2f}m |

## 1. Delta-Normal VaR

Delta-Normal VaR assumes that portfolio P&L is approximately linear in
interest-rate changes and that rate changes follow a normal distribution.

### Advantages

- Simple and transparent.
- Computationally efficient.
- Easy to communicate to management.
- Useful for portfolios whose risk is approximately linear.

### Limitations

- Assumes normality.
- Uses a linear approximation.
- Can understate nonlinear and extreme tail risk.
- Depends heavily on the chosen sensitivity and volatility calibration.

## 2. Monte Carlo VaR

Monte Carlo simulation generates {N_SIMULATIONS:,} correlated 10-day
yield-curve scenarios using the historical covariance structure.

Each simulated curve movement is translated into a change in Vonovia's
debt PV using the assumed duration.

### Advantages

- Models movements across several yield-curve maturities simultaneously.
- Captures historical correlation between different points on the curve.
- Produces a full P&L distribution.
- Easily extended to more complex portfolios.

### Limitations

- Results depend on the assumed statistical distribution.
- Historical covariance may not remain stable.
- Model quality depends on the quality of portfolio exposure data.

## 3. PCA + GARCH VaR

Principal Component Analysis reduces the yield curve to three common
factors.

GARCH is then used to model time-varying volatility in those factors.

This allows the model to reflect volatility clustering: periods of high
market volatility tend to be followed by further volatile periods.

### Advantages

- Allows volatility to change over time.
- Reduces a large yield curve into a small number of economically useful
  risk factors.
- Potentially more responsive to changing market conditions.

### Limitations

- More complex and model-dependent.
- GARCH parameter estimates can be unstable.
- PCA factors can change through time.
- Still depends on assumptions about the underlying corporate exposure.

## Why the Three VaRs Differ

The models answer the same risk question using different assumptions.

**Delta-Normal** uses an analytical normal approximation.

**Monte Carlo** generates many correlated yield-curve scenarios from the
historical covariance matrix.

**PCA + GARCH** additionally allows volatility to vary through time.

Differences between their VaR estimates therefore demonstrate **model
risk**: VaR is not one objective number independent of methodology.

## Calibration Risk

The duration sensitivity analysis demonstrates that VaR is strongly
dependent on the assumed interest-rate sensitivity of the corporate
portfolio.

A longer duration means a larger change in PV for the same movement in
interest rates and therefore a larger VaR.

This is an important practical lesson for corporate treasury:
accurate exposure measurement is at least as important as the statistical
VaR model itself.

## Expected Shortfall

VaR is **not a maximum possible loss**.

A 95% VaR identifies the loss threshold associated with the worst 5% of
modelled outcomes.

Expected Shortfall complements VaR by estimating the average loss within
that worst 5% tail.

For this reason, a corporate treasury should not use VaR in isolation.

## Recommended Corporate Risk Framework

A corporate client should combine:

1. **VaR** — aggregate probabilistic loss measure.
2. **DV01 / duration / key-rate sensitivities** — identify where the
   interest-rate exposure originates.
3. **Scenario analysis** — examine flattening, steepening and other
   yield-curve movements.
4. **Stress testing** — examine severe but plausible market shocks.
5. **Expected Shortfall** — measure the severity of losses beyond VaR.

## Conclusion

VaR provides corporate treasury with a useful common measure for
quantifying interest-rate risk, comparing exposures and evaluating the
effect of potential hedges.

However, the VaR number depends materially on:

- the confidence level;
- risk horizon;
- historical calibration period;
- volatility model;
- correlation assumptions;
- yield-curve representation;
- and, critically, the underlying portfolio's interest-rate sensitivity.

For this reason, VaR should be treated as **one component of an
interest-rate risk-management framework rather than as a maximum-loss
forecast**.

The Vonovia results presented here are illustrative and conditional on
the stated duration assumption because instrument-level duration and
hedging information were not available in the supplied Bloomberg data.
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
# 45. FINAL TERMINAL SUMMARY
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
    "IMPORTANT:"
)


print(

    "These are illustrative VaR estimates conditional on "
    f"an assumed modified duration of {BASE_DURATION:.1f} years."

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