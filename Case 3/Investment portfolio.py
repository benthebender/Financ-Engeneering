import pandas as pd
import numpy as np
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore")


# ============================================================
# ALL-KANNS LIFE INSURANCE
# RETURN-SEEKING PORTFOLIO OPTIMIZATION
#
# CORRECTED VERSION:
# - fixes corrupted Bloomberg bond dates
# - uses weekly returns
# - uses last 10 years
# - performs sanity checks
# - calculates multiple optimized portfolios
# ============================================================


# ============================================================
# 1. SETTINGS
# ============================================================

FILE_NAME = "Investment Portfolio.xlsx"

AS_OF_DATE = pd.Timestamp("2026-09-02")

LOOKBACK_YEARS = 10

RISK_FREE_RATE = 0.02

MAX_WEIGHT = 0.20

WEEKS_PER_YEAR = 52

N_SIMULATIONS = 30000


# ============================================================
# 2. PROBLEMATIC BLOOMBERG SHEETS
# ============================================================
#
# These sheets contain dates that Excel has already
# misinterpreted.
#
# We therefore reconstruct their dates using:
#
# 1. row order
# 2. weekday column
# 3. latest known date = 2 September 2026
#
# ============================================================

RECONSTRUCT_DATE_SHEETS = [

    "US Corporate High Yield index",

    "Bloomberg Pan-European High Yie",

    "Bloomberg Euro Treasury Bond In"

]


# ============================================================
# 3. WEEKDAY MAPPING
# ============================================================

WEEKDAY_MAP = {

    "Mo": 0,
    "Tu": 1,
    "We": 2,
    "Th": 3,
    "Fr": 4

}


# ============================================================
# 4. READ WORKBOOK
# ============================================================

excel_file = pd.ExcelFile(
    FILE_NAME
)

sheet_names = (
    excel_file.sheet_names
)


print("\n" + "=" * 100)
print("WORKBOOK")
print("=" * 100)

print("\nSheets:")

for sheet in sheet_names:

    print(
        " -",
        sheet.strip()
    )


print(
    f"\nTotal assets: "
    f"{len(sheet_names)}"
)


# ============================================================
# 5. HELPER:
# FIND PREVIOUS DATE WITH REQUIRED WEEKDAY
# ============================================================

def previous_matching_weekday(
    current_date,
    target_weekday
):

    candidate = (
        current_date
        -
        pd.Timedelta(days=1)
    )

    # Search backwards until weekday matches
    while (
        candidate.weekday()
        !=
        target_weekday
    ):

        candidate -= pd.Timedelta(
            days=1
        )

    return candidate


# ============================================================
# 6. RECONSTRUCT BLOOMBERG DATES
# ============================================================
#
# IMPORTANT:
#
# Bloomberg data are stored newest -> oldest.
#
# Example:
#
# We
# Tu
# Mo
# Fr
# Th
#
# If first valid observation = Wednesday 2 Sep 2026,
#
# then:
#
# Tuesday = 1 Sep
# Monday  = 31 Aug
# Friday  = 28 Aug
#
# etc.
#
# We do NOT trust the Excel date column for these sheets.
# ============================================================

def reconstruct_dates(
    df,
    sheet_name
):

    print(
        f"\nReconstructing dates for: "
        f"{sheet_name}"
    )


    reconstructed_dates = []


    current_date = (
        AS_OF_DATE
    )


    for i, row in df.iterrows():

        weekday_text = str(
            row.iloc[0]
        ).strip()


        # ----------------------------------------------------
        # Get expected weekday
        # ----------------------------------------------------

        if (
            weekday_text
            not in
            WEEKDAY_MAP
        ):

            reconstructed_dates.append(
                pd.NaT
            )

            continue


        target_weekday = (
            WEEKDAY_MAP[
                weekday_text
            ]
        )


        # ----------------------------------------------------
        # First row
        # ----------------------------------------------------

        if len(
            reconstructed_dates
        ) == 0:

            # Find latest date <= AS_OF_DATE
            # matching stated weekday

            candidate = (
                AS_OF_DATE
            )

            while (
                candidate.weekday()
                !=
                target_weekday
            ):

                candidate -= (
                    pd.Timedelta(
                        days=1
                    )
                )

            current_date = (
                candidate
            )


        # ----------------------------------------------------
        # Subsequent rows
        # ----------------------------------------------------

        else:

            current_date = (
                previous_matching_weekday(
                    current_date,
                    target_weekday
                )
            )


        reconstructed_dates.append(
            current_date
        )


    return pd.Series(
        reconstructed_dates,
        index=df.index
    )


# ============================================================
# 7. CLEAN NORMAL SHEET
# ============================================================

def clean_normal_sheet(
    file_name,
    sheet_name
):

    asset_name = (
        sheet_name.strip()
    )


    df = pd.read_excel(

        file_name,

        sheet_name=sheet_name,

        header=None

    )


    df = df.dropna(
        how="all"
    )


    df = df.iloc[
        :,
        [1, 2]
    ].copy()


    df.columns = [
        "Date",
        "Price"
    ]


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    df["Date"] = pd.to_datetime(

        df["Date"],

        errors="coerce",

        dayfirst=True

    )


    df = df.dropna(
        subset=["Date"]
    )


    df = df[

        df["Date"]
        <=
        AS_OF_DATE

    ]


    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    df["Price"] = pd.to_numeric(

        df["Price"],

        errors="coerce"

    )


    df = df.dropna(

        subset=[
            "Date",
            "Price"
        ]

    )


    df = df[
        df["Price"] > 0
    ]


    df = df.drop_duplicates(

        subset="Date",

        keep="last"

    )


    df = df.sort_values(
        "Date"
    )


    df = df.rename(

        columns={
            "Price":
                asset_name
        }

    )


    df = df.set_index(
        "Date"
    )


    return df


# ============================================================
# 8. CLEAN RECONSTRUCTED BLOOMBERG SHEET
# ============================================================

def clean_reconstructed_sheet(
    file_name,
    sheet_name
):

    asset_name = (
        sheet_name.strip()
    )


    df = pd.read_excel(

        file_name,

        sheet_name=sheet_name,

        header=None

    )


    df = df.dropna(
        how="all"
    )


    if df.shape[1] < 3:

        raise ValueError(
            f"{asset_name}: "
            f"not enough columns."
        )


    # --------------------------------------------------------
    # Reconstruct dates BEFORE selecting columns
    # --------------------------------------------------------

    df[
        "Reconstructed_Date"
    ] = reconstruct_dates(
        df,
        asset_name
    )


    # --------------------------------------------------------
    # Price = original column 2
    # --------------------------------------------------------

    df[
        "Price"
    ] = pd.to_numeric(

        df.iloc[:, 2],

        errors="coerce"

    )


    clean = pd.DataFrame({

        "Date":
            df[
                "Reconstructed_Date"
            ],

        asset_name:
            df[
                "Price"
            ]

    })


    clean = clean.dropna()


    clean = clean[

        clean[
            asset_name
        ]
        >
        0

    ]


    clean = clean[

        clean["Date"]
        <=
        AS_OF_DATE

    ]


    clean = clean.drop_duplicates(

        subset="Date",

        keep="last"

    )


    clean = clean.sort_values(
        "Date"
    )


    clean = clean.set_index(
        "Date"
    )


    return clean


# ============================================================
# 9. CLEAN ALL ASSETS
# ============================================================

print("\n" + "=" * 100)
print("CLEANING / RECONSTRUCTING DATA")
print("=" * 100)


price_frames = []


for sheet_name in sheet_names:

    asset_name = (
        sheet_name.strip()
    )


    try:

        if (
            asset_name
            in
            RECONSTRUCT_DATE_SHEETS
        ):

            cleaned = (
                clean_reconstructed_sheet(
                    FILE_NAME,
                    sheet_name
                )
            )

        else:

            cleaned = (
                clean_normal_sheet(
                    FILE_NAME,
                    sheet_name
                )
            )


        price_frames.append(
            cleaned
        )


        print(

            f"{asset_name:<42}"

            f"{len(cleaned):>6} obs | "

            f"{cleaned.index.min().date()} -> "

            f"{cleaned.index.max().date()}"

        )


    except Exception as error:

        print(
            f"ERROR: "
            f"{asset_name}: "
            f"{error}"
        )


# ============================================================
# 10. COMBINE PRICE DATA
# ============================================================

prices = pd.concat(

    price_frames,

    axis=1

)


prices = prices.sort_index()


prices = prices[

    prices.index
    <=
    AS_OF_DATE

]


print("\n" + "=" * 100)
print("COMBINED DATA")
print("=" * 100)


print(
    f"\nAssets: "
    f"{prices.shape[1]}"
)


print(
    f"Earliest date: "
    f"{prices.index.min().date()}"
)


print(
    f"Latest date: "
    f"{prices.index.max().date()}"
)


# ============================================================
# 11. DAILY RETURN SANITY CHECK
# ============================================================

daily_prices = (
    prices.ffill(
        limit=5
    )
)


daily_returns = (

    daily_prices

    .pct_change(
        fill_method=None
    )

)


sanity_results = []


for asset in prices.columns:

    r = (
        daily_returns[
            asset
        ]
        .dropna()
    )


    if len(r) == 0:

        continue


    annual_vol = (

        r.std()

        *

        np.sqrt(252)

    )


    sanity_results.append({

        "Asset":
            asset,

        "Maximum_Daily_Gain":
            r.max(),

        "Maximum_Daily_Loss":
            r.min(),

        "Days_Above_10pct":
            (
                r.abs()
                >
                0.10
            ).sum(),

        "Days_Above_20pct":
            (
                r.abs()
                >
                0.20
            ).sum(),

        "Daily_Annualized_Vol":
            annual_vol

    })


sanity_table = pd.DataFrame(
    sanity_results
)


sanity_display = (
    sanity_table.copy()
)


for column in [

    "Maximum_Daily_Gain",

    "Maximum_Daily_Loss",

    "Daily_Annualized_Vol"

]:

    sanity_display[
        column
    ] *= 100


print("\n" + "=" * 100)
print("POST-RECONSTRUCTION SANITY CHECK")
print("=" * 100)


print(

    sanity_display

    .round(2)

    .to_string(
        index=False
    )

)


# ============================================================
# 12. FLAG REMAINING PROBLEMS
# ============================================================

print("\nSANITY WARNINGS:")


problem_found = False


for _, row in sanity_table.iterrows():

    asset = (
        row["Asset"]
    )


    if (
        row[
            "Days_Above_20pct"
        ]
        >
        0
    ):

        print(

            f"WARNING: {asset}: "

            f"{int(row['Days_Above_20pct'])} "

            f"daily moves >20% remain."

        )

        problem_found = True


    asset_lower = (
        asset.lower()
    )


    if (
        "treasury" in asset_lower
        and
        row[
            "Daily_Annualized_Vol"
        ]
        >
        0.15
    ):

        print(

            f"WARNING: {asset}: "

            f"Treasury volatility still high."

        )

        problem_found = True


# ============================================================
# 13. WEEKLY PRICES
# ============================================================
#
# Use weekly data for optimization.
# ============================================================

weekly_prices = (

    prices

    .resample(
        "W-FRI"
    )

    .last()

)


weekly_prices = (

    weekly_prices

    .ffill(
        limit=1
    )

)


# ============================================================
# 14. COMMON SAMPLE
# ============================================================

weekly_prices = (
    weekly_prices.dropna()
)


sample_end = min(

    weekly_prices.index.max(),

    AS_OF_DATE

)


sample_start = (

    sample_end

    -

    pd.DateOffset(
        years=LOOKBACK_YEARS
    )

)


weekly_prices = weekly_prices[

    (
        weekly_prices.index
        >=
        sample_start
    )

    &

    (
        weekly_prices.index
        <=
        AS_OF_DATE
    )

]


print("\n" + "=" * 100)
print("OPTIMIZATION SAMPLE")
print("=" * 100)


print(
    f"\nStart: "
    f"{weekly_prices.index.min().date()}"
)


print(
    f"End: "
    f"{weekly_prices.index.max().date()}"
)


print(
    f"Weekly observations: "
    f"{len(weekly_prices)}"
)


# ============================================================
# 15. WEEKLY RETURNS
# ============================================================

returns = (

    weekly_prices

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
# 16. EXPECTED RETURNS
# ============================================================

annual_returns = (

    returns.mean()

    *

    WEEKS_PER_YEAR

)


# ============================================================
# 17. CAGR
# ============================================================

years = (

    (
        weekly_prices.index[-1]

        -

        weekly_prices.index[0]

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
        weekly_prices[
            asset
        ].iloc[0]
    )

    end_value = (
        weekly_prices[
            asset
        ].iloc[-1]
    )


    cagr[
        asset
    ] = (

        (
            end_value
            /
            start_value
        )

        **
        (
            1
            /
            years
        )

        -

        1

    )


# ============================================================
# 18. VOLATILITY
# ============================================================

annual_volatility = (

    returns.std()

    *

    np.sqrt(
        WEEKS_PER_YEAR
    )

)


# ============================================================
# 19. COVARIANCE / CORRELATION
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
# 20. ASSET STATISTICS
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
        annual_returns

        -

        RISK_FREE_RATE
    )

    /

    annual_volatility

)


stats_display = (
    asset_statistics.copy()
)


for col in [

    "Arithmetic_Return",

    "CAGR",

    "Volatility"

]:

    stats_display[
        col
    ] *= 100


print("\n" + "=" * 100)
print("ASSET STATISTICS")
print("=" * 100)


print(

    stats_display

    .round(2)

    .to_string()

)


# ============================================================
# 21. PORTFOLIO FUNCTIONS
# ============================================================

mu = (
    annual_returns.values
)

sigma = (
    cov_matrix.values
)


def portfolio_return(
    weights
):

    return float(

        weights

        @

        mu

    )


def portfolio_variance(
    weights
):

    return float(

        weights.T

        @

        sigma

        @

        weights

    )


def portfolio_volatility(
    weights
):

    return np.sqrt(

        max(

            portfolio_variance(
                weights
            ),

            0

        )

    )


def portfolio_sharpe(
    weights
):

    vol = (
        portfolio_volatility(
            weights
        )
    )


    if vol == 0:

        return -999


    return (

        portfolio_return(
            weights
        )

        -

        RISK_FREE_RATE

    ) / vol


# ============================================================
# 22. STANDARD CONSTRAINTS
# ============================================================

sum_constraint = {

    "type":
        "eq",

    "fun":
        lambda w:
        np.sum(w) - 1

}


standard_constraints = (
    sum_constraint,
)


bounds = tuple(

    (
        0,
        MAX_WEIGHT
    )

    for _
    in range(
        N_ASSETS
    )

)


initial_weights = (

    np.ones(
        N_ASSETS
    )

    /

    N_ASSETS

)


# ============================================================
# 23. MAXIMUM SHARPE
# ============================================================

max_sharpe_result = minimize(

    lambda w:
        -portfolio_sharpe(w),

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=standard_constraints,

    options={

        "maxiter":
            10000,

        "ftol":
            1e-12

    }

)


max_sharpe_weights = (
    max_sharpe_result.x
)


# ============================================================
# 24. MAXIMUM RETURN
# ============================================================

max_return_result = minimize(

    lambda w:
        -portfolio_return(w),

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=standard_constraints,

    options={

        "maxiter":
            10000,

        "ftol":
            1e-12

    }

)


max_return_weights = (
    max_return_result.x
)


# ============================================================
# 25. MINIMUM VOLATILITY
# ============================================================

min_vol_result = minimize(

    portfolio_volatility,

    initial_weights,

    method="SLSQP",

    bounds=bounds,

    constraints=standard_constraints,

    options={

        "maxiter":
            10000,

        "ftol":
            1e-12

    }

)


min_vol_weights = (
    min_vol_result.x
)


# ============================================================
# 26. AGGRESSIVE DIVERSIFIED
# ============================================================
#
# Seek high returns while maintaining diversification.
# ============================================================

aggressive_bounds = []


for asset in assets:

    name = (
        asset.lower()
    )


    if (
        "rare earth"
        in name
    ):

        aggressive_bounds.append(
            (0.02, 0.075)
        )


    elif (
        "hong kong"
        in name
    ):

        aggressive_bounds.append(
            (0.01, 0.10)
        )


    elif (
        "commodity"
        in name
        or
        "gold"
        in name
    ):

        aggressive_bounds.append(
            (0.02, 0.10)
        )


    elif (
        "high yield"
        in name
    ):

        aggressive_bounds.append(
            (0.02, 0.15)
        )


    elif (
        "asian pacific"
        in name
    ):

        aggressive_bounds.append(
            (0.01, 0.10)
        )


    elif (
        "treasury bond"
        in name
    ):

        aggressive_bounds.append(
            (0.01, 0.08)
        )


    else:

        aggressive_bounds.append(
            (0.02, 0.20)
        )


aggressive_bounds = tuple(
    aggressive_bounds
)


# Maximum 18% annual volatility

volatility_constraint = {

    "type":
        "ineq",

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


aggressive_result = minimize(

    lambda w:
        -portfolio_return(w),

    initial_weights,

    method="SLSQP",

    bounds=aggressive_bounds,

    constraints=aggressive_constraints,

    options={

        "maxiter":
            20000,

        "ftol":
            1e-12

    }

)


aggressive_weights = (
    aggressive_result.x
)


# ============================================================
# 27. EQUAL WEIGHT
# ============================================================

equal_weights = (

    np.ones(
        N_ASSETS
    )

    /

    N_ASSETS

)


# ============================================================
# 28. SUMMARY FUNCTION
# ============================================================

def summarize(
    name,
    weights
):

    return {

        "Portfolio":
            name,

        "Expected_Return":
            portfolio_return(
                weights
            ),

        "Volatility":
            portfolio_volatility(
                weights
            ),

        "Sharpe":
            portfolio_sharpe(
                weights
            )

    }


# ============================================================
# 29. PORTFOLIO COMPARISON
# ============================================================

portfolio_summary = pd.DataFrame([

    summarize(
        "Maximum Sharpe",
        max_sharpe_weights
    ),

    summarize(
        "Maximum Return",
        max_return_weights
    ),

    summarize(
        "Aggressive Diversified",
        aggressive_weights
    ),

    summarize(
        "Minimum Volatility",
        min_vol_weights
    ),

    summarize(
        "Equal Weight",
        equal_weights
    )

])


summary_display = (
    portfolio_summary.copy()
)


summary_display[
    "Expected_Return"
] *= 100

summary_display[
    "Volatility"
] *= 100


print("\n" + "=" * 100)
print("PORTFOLIO COMPARISON")
print("=" * 100)


print(

    summary_display

    .round(2)

    .to_string(
        index=False
    )

)


# ============================================================
# 30. WEIGHTS
# ============================================================

weights_table = pd.DataFrame({

    "Asset":
        assets,

    "Maximum_Sharpe":
        max_sharpe_weights
        *
        100,

    "Maximum_Return":
        max_return_weights
        *
        100,

    "Aggressive_Diversified":
        aggressive_weights
        *
        100,

    "Minimum_Volatility":
        min_vol_weights
        *
        100,

    "Equal_Weight":
        equal_weights
        *
        100

})


print("\n" + "=" * 100)
print("PORTFOLIO WEIGHTS (%)")
print("=" * 100)


print(

    weights_table

    .round(2)

    .to_string(
        index=False
    )

)


# ============================================================
# 31. RECOMMENDED PORTFOLIO
# ============================================================

recommended = (

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


print("\n" + "=" * 100)
print("AGGRESSIVE DIVERSIFIED PORTFOLIO")
print("=" * 100)


print(

    recommended

    .round(2)

    .to_string(
        index=False
    )

)


# ============================================================
# 32. MONTE CARLO
# ============================================================

np.random.seed(
    42
)


simulations = []


for _ in range(
    N_SIMULATIONS
):

    w = np.random.random(
        N_ASSETS
    )


    w /= (
        w.sum()
    )


    if (
        w.max()
        >
        MAX_WEIGHT
    ):

        continue


    simulations.append({

        "Return":
            portfolio_return(w),

        "Volatility":
            portfolio_volatility(w),

        "Sharpe":
            portfolio_sharpe(w)

    })


simulation_df = pd.DataFrame(
    simulations
)


# ============================================================
# 33. PORTFOLIO MAP
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.scatter(

    simulation_df[
        "Volatility"
    ]
    *
    100,

    simulation_df[
        "Return"
    ]
    *
    100,

    s=6,

    alpha=0.25

)


points = [

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
) in points:

    plt.scatter(

        portfolio_volatility(
            weights
        )
        *
        100,

        portfolio_return(
            weights
        )
        *
        100,

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
    "portfolio_map_final.png",
    dpi=300
)

plt.show()


# ============================================================
# 34. RECOMMENDED WEIGHTS CHART
# ============================================================

recommended_plot = pd.Series(

    aggressive_weights
    *
    100,

    index=assets

).sort_values(
    ascending=False
)


plt.figure(
    figsize=(11, 7)
)


recommended_plot.plot(
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
    "recommended_weights_final.png",
    dpi=300
)

plt.show()


# ============================================================
# 35. EXPORT
# ============================================================

with pd.ExcelWriter(

    "portfolio_optimization_final.xlsx",

    engine="openpyxl"

) as writer:


    prices.to_excel(

        writer,

        sheet_name="Corrected Prices"

    )


    weekly_prices.to_excel(

        writer,

        sheet_name="Weekly Prices"

    )


    returns.to_excel(

        writer,

        sheet_name="Weekly Returns"

    )


    sanity_table.to_excel(

        writer,

        sheet_name="Sanity Check",

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


# ============================================================
# 36. FINISH
# ============================================================

print("\n" + "=" * 100)
print("COMPLETE")
print("=" * 100)


print(
    "\nFiles created:"
)


print(
    "1. portfolio_optimization_final.xlsx"
)


print(
    "2. portfolio_map_final.png"
)


print(
    "3. recommended_weights_final.png"
)


print(
    "\nIMPORTANT:"
)


if problem_found:

    print(
        "Some sanity warnings remain. "
        "Inspect them before accepting the portfolio."
    )

else:

    print(
        "No major sanity warnings detected."
    )