import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore")


# ============================================================
# ALL-KANNS LIFE INSURANCE
# RETURN-SEEKING PORTFOLIO OPTIMIZATION
# ROBUST VERSION
# ============================================================


# ============================================================
# 1. SETTINGS
# ============================================================

FILE_NAME = "Investment Portfolio.xlsx"

# Data cannot extend beyond this date
AS_OF_DATE = pd.Timestamp("2026-09-02")

LOOKBACK_YEARS = 10

# Use weekly observations to reduce problems caused by
# different trading calendars / holidays across markets.
RETURN_FREQUENCY = "W-FRI"

WEEKS_PER_YEAR = 52

# Risk-free rate for Sharpe ratio
RISK_FREE_RATE = 0.02

# General maximum position
MAX_WEIGHT = 0.20

# Number of Monte Carlo portfolios
N_SIMULATIONS = 30000


# ============================================================
# 2. READ WORKBOOK
# ============================================================

excel_file = pd.ExcelFile(FILE_NAME)

sheet_names = excel_file.sheet_names


print("\n" + "=" * 90)
print("WORKBOOK")
print("=" * 90)

print("\nSheets found:")

for sheet in sheet_names:
    print(" -", sheet.strip())

print(
    f"\nTotal sheets: {len(sheet_names)}"
)


# ============================================================
# 3. CLEAN EACH SHEET
# ============================================================
#
# Workbook structure:
#
# Column 0 = weekday
# Column 1 = date
# Column 2 = price / index level
#
# No header.
#
# IMPORTANT:
# Dates are interpreted DAY FIRST.
# ============================================================

def clean_sheet(file_name, sheet_name):

    asset_name = sheet_name.strip()

    df = pd.read_excel(
        file_name,
        sheet_name=sheet_name,
        header=None
    )

    df = df.dropna(how="all")

    if df.shape[1] < 3:

        raise ValueError(
            f"{asset_name}: fewer than 3 columns."
        )


    # --------------------------------------------------------
    # Keep Date + Price
    # --------------------------------------------------------

    df = df.iloc[:, [1, 2]].copy()

    df.columns = [
        "Date",
        "Price"
    ]


    # ========================================================
    # DATE CLEANING
    # ========================================================

    # Some Excel cells may already be true datetime objects.
    # Others may be strings.
    #
    # dayfirst=True fixes European DD/MM/YYYY formatting.

    df["Date"] = pd.to_datetime(
        df["Date"],
        errors="coerce",
        dayfirst=True
    )


    # Remove invalid dates
    df = df.dropna(
        subset=["Date"]
    )


    # Remove impossible future observations
    future_rows = (
        df["Date"] > AS_OF_DATE
    ).sum()

    if future_rows > 0:

        print(
            f"WARNING: {asset_name}: "
            f"removed {future_rows} observations "
            f"after {AS_OF_DATE.date()}"
        )

    df = df[
        df["Date"] <= AS_OF_DATE
    ]


    # ========================================================
    # PRICE CLEANING
    # ========================================================

    raw_price = df["Price"].copy()


    # First attempt:
    # direct numeric conversion

    numeric_price = pd.to_numeric(
        raw_price,
        errors="coerce"
    )


    # If direct conversion fails badly,
    # try European number formatting.

    if (
        numeric_price.notna().sum()
        <
        0.50 * len(df)
    ):

        text_price = (
            raw_price
            .astype(str)
            .str.strip()
            .str.replace(
                ".",
                "",
                regex=False
            )
            .str.replace(
                ",",
                ".",
                regex=False
            )
        )

        numeric_price = pd.to_numeric(
            text_price,
            errors="coerce"
        )


    df["Price"] = numeric_price


    # Remove invalid prices
    df = df.dropna(
        subset=["Price"]
    )

    df = df[
        df["Price"] > 0
    ]


    # Remove duplicate dates
    df = df.drop_duplicates(
        subset="Date",
        keep="last"
    )


    # Sort chronologically
    df = df.sort_values(
        "Date"
    )


    # Rename price column
    df = df.rename(
        columns={
            "Price": asset_name
        }
    )


    df = df.set_index(
        "Date"
    )


    # ========================================================
    # BASIC SANITY CHECK
    # ========================================================

    if len(df) < 100:

        print(
            f"WARNING: {asset_name} has only "
            f"{len(df)} valid observations."
        )


    print(
        f"{asset_name:<42}"
        f"{len(df):>6} obs | "
        f"{df.index.min().date()} -> "
        f"{df.index.max().date()} | "
        f"Last={df.iloc[-1, 0]:,.4f}"
    )


    return df


# ============================================================
# 4. CLEAN ALL 14 SERIES
# ============================================================

print("\n" + "=" * 90)
print("CLEANING DATA")
print("=" * 90 + "\n")


price_frames = []


for sheet_name in sheet_names:

    try:

        cleaned = clean_sheet(
            FILE_NAME,
            sheet_name
        )

        if len(cleaned) > 0:

            price_frames.append(
                cleaned
            )

    except Exception as error:

        print(
            f"ERROR: {sheet_name}: {error}"
        )


if len(price_frames) == 0:

    raise ValueError(
        "No usable asset data found."
    )


# ============================================================
# 5. COMBINE PRICE DATA
# ============================================================

prices = pd.concat(
    price_frames,
    axis=1
)

prices = prices.sort_index()


# Final safety filter
prices = prices[
    prices.index <= AS_OF_DATE
]


print("\n" + "=" * 90)
print("RAW DATA CHECK")
print("=" * 90)

print(
    f"\nEarliest observation: "
    f"{prices.index.min().date()}"
)

print(
    f"Latest observation:   "
    f"{prices.index.max().date()}"
)

print(
    f"Number of assets:     "
    f"{prices.shape[1]}"
)


if prices.index.max() > AS_OF_DATE:

    raise ValueError(
        "Future observations remain in dataset."
    )


# ============================================================
# 6. DAILY RETURN SANITY CHECK
# ============================================================
#
# We do NOT optimize on these daily returns.
#
# We use them only to detect obvious bad observations.
# ============================================================

daily_returns_raw = (
    prices
    .ffill(limit=5)
    .pct_change(
        fill_method=None
    )
)


print("\n" + "=" * 90)
print("DAILY RETURN SANITY CHECK")
print("=" * 90)


sanity_rows = []


for asset in prices.columns:

    r = (
        daily_returns_raw[asset]
        .dropna()
    )

    if len(r) == 0:
        continue


    max_up = r.max()

    max_down = r.min()

    suspicious_20 = (
        r.abs() > 0.20
    ).sum()

    suspicious_50 = (
        r.abs() > 0.50
    ).sum()


    sanity_rows.append({

        "Asset": asset,

        "Maximum Daily Gain":
            max_up,

        "Maximum Daily Loss":
            max_down,

        "Days > 20% Move":
            suspicious_20,

        "Days > 50% Move":
            suspicious_50

    })


sanity_table = pd.DataFrame(
    sanity_rows
)


sanity_display = (
    sanity_table.copy()
)


sanity_display[
    "Maximum Daily Gain"
] *= 100

sanity_display[
    "Maximum Daily Loss"
] *= 100


print(
    sanity_display
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 7. REMOVE OBVIOUS EXTREME DATA ERRORS
# ============================================================
#
# Rather than silently treating +/-50% daily moves as real,
# replace them with missing values.
#
# This is deliberately conservative.
# ============================================================

daily_returns_clean = (
    daily_returns_raw
    .mask(
        daily_returns_raw.abs() > 0.50
    )
)


# ============================================================
# 8. CONVERT TO WEEKLY PRICES
# ============================================================
#
# Weekly observations help reduce:
#
# - different trading holidays
# - stale daily prices
# - asynchronous global markets
#
# We take the last available price each Friday/week.
# ============================================================

weekly_prices = (
    prices
    .resample(
        RETURN_FREQUENCY
    )
    .last()
)


# Forward fill only one week if necessary
weekly_prices = (
    weekly_prices
    .ffill(
        limit=1
    )
)


# ============================================================
# 9. COMMON WEEKLY SAMPLE
# ============================================================

weekly_prices_common = (
    weekly_prices
    .dropna()
)


if len(weekly_prices_common) == 0:

    raise ValueError(
        "No common weekly price history."
    )


# ============================================================
# 10. LAST 10 YEARS
# ============================================================

sample_end = min(
    weekly_prices_common.index.max(),
    AS_OF_DATE
)

sample_start = (
    sample_end
    -
    pd.DateOffset(
        years=LOOKBACK_YEARS
    )
)


weekly_prices_common = (

    weekly_prices_common[

        (
            weekly_prices_common.index
            >= sample_start
        )

        &

        (
            weekly_prices_common.index
            <= AS_OF_DATE
        )

    ]

)


print("\n" + "=" * 90)
print("FINAL OPTIMIZATION SAMPLE")
print("=" * 90)

print(
    f"\nFrequency: Weekly"
)

print(
    f"Start: {weekly_prices_common.index.min().date()}"
)

print(
    f"End:   {weekly_prices_common.index.max().date()}"
)

print(
    f"Weekly observations: "
    f"{len(weekly_prices_common)}"
)


# ============================================================
# 11. WEEKLY RETURNS
# ============================================================

returns = (
    weekly_prices_common
    .pct_change(
        fill_method=None
    )
    .dropna()
)


assets = list(
    returns.columns
)

N_ASSETS = len(
    assets
)


# ============================================================
# 12. ANNUALIZED ARITHMETIC RETURN
# ============================================================

annual_returns = (

    returns.mean()

    *

    WEEKS_PER_YEAR

)


# ============================================================
# 13. CAGR
# ============================================================
#
# CAGR is useful as a sanity check against the arithmetic
# expected return used by Markowitz.
# ============================================================

years_in_sample = (

    (
        weekly_prices_common.index[-1]
        -
        weekly_prices_common.index[0]
    ).days

    /

    365.25

)


cagr = pd.Series(
    index=assets,
    dtype=float
)


for asset in assets:

    start_value = (
        weekly_prices_common[
            asset
        ].iloc[0]
    )

    end_value = (
        weekly_prices_common[
            asset
        ].iloc[-1]
    )

    cagr[asset] = (

        (
            end_value
            /
            start_value
        )
        **
        (
            1
            /
            years_in_sample
        )

        -

        1

    )


# ============================================================
# 14. ANNUALIZED VOLATILITY
# ============================================================

annual_volatility = (

    returns.std()

    *

    np.sqrt(
        WEEKS_PER_YEAR
    )

)


# ============================================================
# 15. COVARIANCE AND CORRELATION
# ============================================================

cov_matrix = (

    returns.cov()

    *

    WEEKS_PER_YEAR

)


correlation_matrix = (
    returns.corr()
)


# ============================================================
# 16. ASSET STATISTICS
# ============================================================

asset_statistics = pd.DataFrame({

    "Arithmetic_Return":
        annual_returns,

    "CAGR":
        cagr,

    "Volatility":
        annual_volatility

})


asset_statistics[
    "Sharpe"
] = (

    (
        asset_statistics[
            "Arithmetic_Return"
        ]

        -

        RISK_FREE_RATE
    )

    /

    asset_statistics[
        "Volatility"
    ]

)


# ============================================================
# 17. SANITY WARNINGS
# ============================================================

print("\n" + "=" * 90)
print("ASSET STATISTICS - SANITY CHECK")
print("=" * 90)


stats_display = (
    asset_statistics.copy()
)


for col in [
    "Arithmetic_Return",
    "CAGR",
    "Volatility"
]:

    stats_display[col] *= 100


print(
    stats_display
    .round(2)
    .to_string()
)


print("\nWARNINGS:")


for asset in assets:

    vol = annual_volatility[asset]

    ret = annual_returns[asset]

    asset_lower = asset.lower()


    if vol > 0.40:

        print(
            f"WARNING: {asset}: "
            f"volatility = {vol * 100:.1f}%"
        )


    if (
        "treasury" in asset_lower
        and vol > 0.15
    ):

        print(
            f"WARNING: {asset}: "
            f"government bond index volatility "
            f"is unusually high "
            f"({vol * 100:.1f}%). "
            f"Inspect source data."
        )


    if (
        "high yield" in asset_lower
        and vol > 0.25
    ):

        print(
            f"WARNING: {asset}: "
            f"HY volatility looks unusually high "
            f"({vol * 100:.1f}%). "
            f"Inspect source series."
        )


    if abs(ret) > 0.30:

        print(
            f"WARNING: {asset}: "
            f"annualized arithmetic return "
            f"{ret * 100:.1f}% looks extreme."
        )


# ============================================================
# 18. PORTFOLIO FUNCTIONS
# ============================================================

mu = annual_returns.values

sigma = cov_matrix.values


def portfolio_return(weights):

    return float(
        np.dot(
            weights,
            mu
        )
    )


def portfolio_variance(weights):

    return float(

        weights.T

        @

        sigma

        @

        weights

    )


def portfolio_volatility(weights):

    variance = portfolio_variance(
        weights
    )

    return np.sqrt(
        max(
            variance,
            0
        )
    )


def portfolio_sharpe(weights):

    volatility = portfolio_volatility(
        weights
    )

    if volatility <= 0:

        return -999

    return (

        portfolio_return(
            weights
        )

        -

        RISK_FREE_RATE

    ) / volatility


# ============================================================
# 19. GENERAL CONSTRAINTS
# ============================================================

sum_constraint = {

    "type": "eq",

    "fun":
        lambda w:
        np.sum(w) - 1

}


constraints = (
    sum_constraint,
)


bounds = tuple(

    (
        0,
        MAX_WEIGHT
    )

    for _ in range(
        N_ASSETS
    )

)


initial_weights = np.repeat(
    1 / N_ASSETS,
    N_ASSETS
)


# ============================================================
# 20. MAXIMUM SHARPE
# ============================================================

max_sharpe_result = minimize(

    lambda w:
        -portfolio_sharpe(w),

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=constraints,

    options={
        "maxiter": 10000,
        "ftol": 1e-12
    }

)


max_sharpe_weights = (
    max_sharpe_result.x
)


# ============================================================
# 21. MAXIMUM RETURN
# ============================================================
#
# NOTE:
#
# This SHOULD generally put 20% into the five assets
# with highest expected returns.
#
# That is mathematically correct.
# ============================================================

max_return_result = minimize(

    lambda w:
        -portfolio_return(w),

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=constraints,

    options={
        "maxiter": 10000,
        "ftol": 1e-12
    }

)


max_return_weights = (
    max_return_result.x
)


# ============================================================
# 22. MINIMUM VOLATILITY
# ============================================================

min_vol_result = minimize(

    portfolio_volatility,

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=constraints,

    options={
        "maxiter": 10000,
        "ftol": 1e-12
    }

)


min_vol_weights = (
    min_vol_result.x
)


# ============================================================
# 23. AGGRESSIVE DIVERSIFIED PORTFOLIO
# ============================================================
#
# THIS IS THE PORTFOLIO MOST RELEVANT TO YOUR CASE.
#
# Objective:
#
# Maximize expected return
#
# BUT:
#
# - no asset > 20%
# - Rare Earth <= 7.5%
# - no zero-weight concentration solution
# - minimum diversification
# - portfolio volatility <= 18%
#
# This gives the optimizer freedom to seek return while
# preventing a silly five-assets-at-20% solution.
# ============================================================


# ------------------------------------------------------------
# Individual custom bounds
# ------------------------------------------------------------

aggressive_bounds = []


for asset in assets:

    name = asset.lower()


    # Rare earth thematic position
    if "rare earth" in name:

        aggressive_bounds.append(
            (0.02, 0.075)
        )


    # Hong Kong
    elif "hong kong" in name:

        aggressive_bounds.append(
            (0.01, 0.10)
        )


    # Commodity / Gold
    elif (
        "commodity" in name
        or "gold" in name
    ):

        aggressive_bounds.append(
            (0.02, 0.10)
        )


    # High yield
    elif "high yield" in name:

        aggressive_bounds.append(
            (0.02, 0.15)
        )


    # Asian Aggregate
    elif "asian pacific" in name:

        aggressive_bounds.append(
            (0.01, 0.10)
        )


    # Treasury bond index
    elif "treasury bond" in name:

        aggressive_bounds.append(
            (0.01, 0.08)
        )


    # Everything else
    else:

        aggressive_bounds.append(
            (0.02, 0.20)
        )


aggressive_bounds = tuple(
    aggressive_bounds
)


# ------------------------------------------------------------
# Maximum portfolio volatility = 18%
#
# Constraint must be >= 0:
#
# 18% - portfolio volatility >= 0
# ------------------------------------------------------------

volatility_constraint = {

    "type": "ineq",

    "fun":
        lambda w:
        0.18
        -
        portfolio_volatility(w)

}


aggressive_constraints = (

    sum_constraint,

    volatility_constraint

)


# Start from equal weights
aggressive_initial = (
    initial_weights.copy()
)


aggressive_result = minimize(

    lambda w:
        -portfolio_return(w),

    aggressive_initial,

    method="SLSQP",

    bounds=aggressive_bounds,

    constraints=aggressive_constraints,

    options={
        "maxiter": 20000,
        "ftol": 1e-12
    }

)


if not aggressive_result.success:

    print(
        "\nWARNING: Aggressive diversified "
        "optimization did not fully converge:"
    )

    print(
        aggressive_result.message
    )


aggressive_weights = (
    aggressive_result.x
)


# ============================================================
# 24. EQUAL WEIGHT
# ============================================================

equal_weights = np.repeat(
    1 / N_ASSETS,
    N_ASSETS
)


# ============================================================
# 25. PORTFOLIO SUMMARY
# ============================================================

def summarize_portfolio(
    name,
    weights
):

    return {

        "Portfolio":
            name,

        "Expected_Return":
            portfolio_return(weights),

        "Volatility":
            portfolio_volatility(weights),

        "Sharpe":
            portfolio_sharpe(weights)

    }


portfolio_summary = pd.DataFrame([

    summarize_portfolio(
        "Maximum Sharpe",
        max_sharpe_weights
    ),

    summarize_portfolio(
        "Maximum Return",
        max_return_weights
    ),

    summarize_portfolio(
        "Aggressive Diversified",
        aggressive_weights
    ),

    summarize_portfolio(
        "Minimum Volatility",
        min_vol_weights
    ),

    summarize_portfolio(
        "Equal Weight",
        equal_weights
    )

])


portfolio_summary_display = (
    portfolio_summary.copy()
)


portfolio_summary_display[
    "Expected_Return"
] *= 100

portfolio_summary_display[
    "Volatility"
] *= 100


print("\n" + "=" * 90)
print("PORTFOLIO COMPARISON")
print("=" * 90)


print(
    portfolio_summary_display
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 26. WEIGHT TABLE
# ============================================================

weights_table = pd.DataFrame({

    "Asset":
        assets,

    "Maximum_Sharpe":
        max_sharpe_weights * 100,

    "Maximum_Return":
        max_return_weights * 100,

    "Aggressive_Diversified":
        aggressive_weights * 100,

    "Minimum_Volatility":
        min_vol_weights * 100,

    "Equal_Weight":
        equal_weights * 100

})


print("\n" + "=" * 90)
print("PORTFOLIO WEIGHTS (%)")
print("=" * 90)


print(
    weights_table
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 27. AGGRESSIVE PORTFOLIO - SORTED
# ============================================================

print("\n" + "=" * 90)
print("RECOMMENDED AGGRESSIVE DIVERSIFIED PORTFOLIO")
print("=" * 90)


aggressive_output = (

    weights_table[
        [
            "Asset",
            "Aggressive_Diversified"
        ]
    ]

    .sort_values(
        "Aggressive_Diversified",
        ascending=False
    )

)


print(
    aggressive_output
    .round(2)
    .to_string(
        index=False
    )
)


# ============================================================
# 28. MONTE CARLO
# ============================================================

np.random.seed(42)

simulation_results = []


for _ in range(
    N_SIMULATIONS
):

    w = np.random.random(
        N_ASSETS
    )

    w /= w.sum()


    if w.max() > MAX_WEIGHT:
        continue


    simulation_results.append({

        "Return":
            portfolio_return(w),

        "Volatility":
            portfolio_volatility(w),

        "Sharpe":
            portfolio_sharpe(w)

    })


simulation_df = pd.DataFrame(
    simulation_results
)


# ============================================================
# 29. PORTFOLIO MAP
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.scatter(

    simulation_df[
        "Volatility"
    ]
    * 100,

    simulation_df[
        "Return"
    ]
    * 100,

    s=6,

    alpha=0.25

)


portfolio_points = [

    (
        "Maximum Sharpe",
        max_sharpe_weights,
        "*",
        250
    ),

    (
        "Maximum Return",
        max_return_weights,
        "X",
        180
    ),

    (
        "Aggressive Diversified",
        aggressive_weights,
        "P",
        180
    ),

    (
        "Minimum Volatility",
        min_vol_weights,
        "D",
        120
    )

]


for (
    label,
    weights,
    marker,
    size
) in portfolio_points:

    plt.scatter(

        portfolio_volatility(
            weights
        )
        * 100,

        portfolio_return(
            weights
        )
        * 100,

        marker=marker,

        s=size,

        label=label

    )


plt.xlabel(
    "Annualized Volatility (%)"
)

plt.ylabel(
    "Historical Annualized Return (%)"
)

plt.title(
    "All-Kanns Return-Seeking Portfolio"
)

plt.legend()

plt.tight_layout()

plt.savefig(
    "portfolio_map_corrected.png",
    dpi=300
)

plt.show()


# ============================================================
# 30. AGGRESSIVE PORTFOLIO CHART
# ============================================================

aggressive_plot = pd.Series(

    aggressive_weights * 100,

    index=assets

).sort_values(
    ascending=False
)


plt.figure(
    figsize=(11, 7)
)


aggressive_plot.plot(
    kind="bar"
)


plt.ylabel(
    "Weight (%)"
)

plt.title(
    "Aggressive Diversified Return-Seeking Portfolio"
)

plt.xticks(
    rotation=70,
    ha="right"
)

plt.tight_layout()

plt.savefig(
    "aggressive_diversified_weights.png",
    dpi=300
)

plt.show()


# ============================================================
# 31. EXPORT RESULTS
# ============================================================

with pd.ExcelWriter(
    "portfolio_optimization_corrected.xlsx",
    engine="openpyxl"
) as writer:

    prices.to_excel(
        writer,
        sheet_name="Clean Prices"
    )

    weekly_prices_common.to_excel(
        writer,
        sheet_name="Weekly Prices"
    )

    returns.to_excel(
        writer,
        sheet_name="Weekly Returns"
    )

    sanity_table.to_excel(
        writer,
        sheet_name="Data Sanity",
        index=False
    )

    asset_statistics.to_excel(
        writer,
        sheet_name="Asset Statistics"
    )

    correlation_matrix.to_excel(
        writer,
        sheet_name="Correlation"
    )

    cov_matrix.to_excel(
        writer,
        sheet_name="Covariance"
    )

    weights_table.to_excel(
        writer,
        sheet_name="Portfolio Weights",
        index=False
    )

    portfolio_summary.to_excel(
        writer,
        sheet_name="Portfolio Summary",
        index=False
    )

    simulation_df.to_excel(
        writer,
        sheet_name="Monte Carlo",
        index=False
    )


# ============================================================
# 32. FINAL CHECKS
# ============================================================

print("\n" + "=" * 90)
print("FINAL CHECK")
print("=" * 90)


print(
    f"\nMaximum Sharpe weights: "
    f"{max_sharpe_weights.sum() * 100:.4f}%"
)

print(
    f"Maximum Return weights: "
    f"{max_return_weights.sum() * 100:.4f}%"
)

print(
    f"Aggressive Diversified weights: "
    f"{aggressive_weights.sum() * 100:.4f}%"
)

print(
    f"Minimum Volatility weights: "
    f"{min_vol_weights.sum() * 100:.4f}%"
)


print("\nFiles created:")

print(
    "1. portfolio_optimization_corrected.xlsx"
)

print(
    "2. portfolio_map_corrected.png"
)

print(
    "3. aggressive_diversified_weights.png"
)