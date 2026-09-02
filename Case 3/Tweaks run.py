import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import warnings

warnings.filterwarnings("ignore")


# ============================================================
# ALL-KANNS LIFE INSURANCE
# INTEGRATED MONTE CARLO ASSET-LIABILITY MODEL
# ============================================================
#
# PURPOSE
# -------
# 1. Simulate portfolio returns and asset values
# 2. Show annual and 15-year portfolio performance
# 3. Evaluate 50/50 lump-sum / pension base case
# 4. Sensitivity:
#       0/100
#       25/75
#       50/50
#       75/25
#       100/0
# 5. Measure:
#       - asset growth
#       - annual returns
#       - cumulative return
#       - funding ratio
#       - surplus
#       - probability of underfunding
#       - probability of liquidity shortfall
#       - downside percentiles
#
# IMPORTANT
# ---------
# This model separates:
#
# A. Year-15 TOTAL liability
# B. Year-15 IMMEDIATE lump-sum cash requirement
# C. Remaining pension liability at Year 15
#
# ============================================================


# ============================================================
# 1. RANDOM SETTINGS
# ============================================================

RANDOM_SEED = 42

N_SIMULATIONS = 100_000

HORIZON_YEARS = 15

STUDENT_T_DF = 5

rng = np.random.default_rng(
    RANDOM_SEED
)


# ============================================================
# 2. STARTING BALANCE SHEET
# ============================================================

STARTING_ASSETS = 5_000_000_000

ANNUAL_CONTRIBUTION = 500_000_000

CONTRIBUTION_YEARS = 10


# ============================================================
# 3. ASSET ALLOCATION
# ============================================================
#
# IMPORTANT:
#
# Replace these when your final LMP/RSP strategic split
# has been decided.
#
# They must sum to 100%.
#
# ============================================================

LMP_WEIGHT = 0.70

RSP_WEIGHT = 0.30


if not np.isclose(
    LMP_WEIGHT + RSP_WEIGHT,
    1.0
):

    raise ValueError(
        "LMP_WEIGHT + RSP_WEIGHT must equal 1."
    )


# ============================================================
# 4. RETURN-SEEKING PORTFOLIO
# ============================================================
#
# From your Aggressive Diversified portfolio BEFORE CDX:
#
# Historical annualized return = 12.43%
# Annualized volatility        = 16.46%
# Sharpe                       = 0.63
#
# NOTE:
#
# The 1% CDX hedge was added AFTER optimization.
#
# Therefore 12.43% / 16.46% are technically the
# PRE-CDX historical portfolio statistics.
#
# ============================================================

RSP_EXPECTED_RETURN = 0.1243

RSP_VOLATILITY = 0.1646


# ============================================================
# 5. LIABILITY-MATCHING PORTFOLIO
# ============================================================
#
# THESE REMAIN EXPLICIT ASSUMPTIONS.
#
# Replace them once the final LMP portfolio return and
# volatility have been calculated from its actual holdings.
#
# ============================================================

LMP_EXPECTED_RETURN = 0.035

LMP_VOLATILITY = 0.060


# ============================================================
# 6. LMP / RSP CORRELATION
# ============================================================
#
# Explicit modelling assumption.
#
# Replace with empirical correlation when available.
#
# ============================================================

LMP_RSP_CORRELATION = 0.20


# ============================================================
# 7. LIQUIDITY ASSUMPTIONS
# ============================================================
#
# Instead of pretending ALL assets are instantly liquid,
# assign liquidity factors.
#
# LMP:
# Long-dated bonds are liquid but may require sale.
#
# RSP:
# Most indices are highly liquid, but we use a haircut.
#
# These are assumptions and should be disclosed.
#
# ============================================================

LMP_LIQUIDITY_FACTOR = 0.85

RSP_LIQUIDITY_FACTOR = 0.95


# ============================================================
# 8. LIABILITY SCENARIOS AT YEAR 15
# ============================================================
#
# Taken from your completed mixed-liability analysis.
#
# pension_pv_y15 = value at Year 15 of future pension
# payments after retirement.
#
# lump_sum_y15 = cash payable around retirement.
#
# ============================================================

SCENARIOS = {

    "0% Lump / 100% Pension": {

        "lump_share": 0.00,

        "pension_share": 1.00,

        "lump_sum_y15": 0.000e9,

        "pension_pv_y15": 8.717e9,

        "total_liability_y15": 8.717e9

    },


    "25% Lump / 75% Pension": {

        "lump_share": 0.25,

        "pension_share": 0.75,

        "lump_sum_y15": 2.826e9,

        "pension_pv_y15": 6.538e9,

        "total_liability_y15": 9.364e9

    },


    "50% Lump / 50% Pension": {

        "lump_share": 0.50,

        "pension_share": 0.50,

        "lump_sum_y15": 5.651e9,

        "pension_pv_y15": 4.359e9,

        "total_liability_y15": 10.010e9

    },


    "75% Lump / 25% Pension": {

        "lump_share": 0.75,

        "pension_share": 0.25,

        "lump_sum_y15": 8.477e9,

        "pension_pv_y15": 2.179e9,

        "total_liability_y15": 10.656e9

    },


    "100% Lump / 0% Pension": {

        "lump_share": 1.00,

        "pension_share": 0.00,

        "lump_sum_y15": 11.303e9,

        "pension_pv_y15": 0.000e9,

        "total_liability_y15": 11.303e9

    }

}


BASE_CASE_NAME = (
    "50% Lump / 50% Pension"
)


# ============================================================
# 9. ASSET EXPECTED RETURNS
# ============================================================

expected_returns = np.array([

    LMP_EXPECTED_RETURN,

    RSP_EXPECTED_RETURN

])


volatilities = np.array([

    LMP_VOLATILITY,

    RSP_VOLATILITY

])


portfolio_weights = np.array([

    LMP_WEIGHT,

    RSP_WEIGHT

])


# ============================================================
# 10. CORRELATION MATRIX
# ============================================================

correlation_matrix = np.array([

    [
        1.0,
        LMP_RSP_CORRELATION
    ],

    [
        LMP_RSP_CORRELATION,
        1.0
    ]

])


# ============================================================
# 11. COVARIANCE MATRIX
# ============================================================

covariance_matrix = (

    np.outer(
        volatilities,
        volatilities
    )

    *

    correlation_matrix

)


chol = np.linalg.cholesky(
    covariance_matrix
)


# ============================================================
# 12. THEORETICAL PORTFOLIO STATISTICS
# ============================================================

portfolio_expected_return = float(

    portfolio_weights

    @

    expected_returns

)


portfolio_variance = float(

    portfolio_weights.T

    @

    covariance_matrix

    @

    portfolio_weights

)


portfolio_volatility = np.sqrt(
    portfolio_variance
)


# ============================================================
# 13. PRINT MODEL ASSUMPTIONS
# ============================================================

print("\n" + "=" * 100)

print(
    "ALL-KANNS LIFE INSURANCE"
)

print(
    "INTEGRATED 15-YEAR MONTE CARLO ALM MODEL"
)

print("=" * 100)


print(
    f"\nStarting assets: "
    f"EUR {STARTING_ASSETS / 1e9:.3f}bn"
)


print(
    f"Annual contributions: "
    f"EUR {ANNUAL_CONTRIBUTION / 1e9:.3f}bn"
)


print(
    f"Contribution years: "
    f"{CONTRIBUTION_YEARS}"
)


print(
    f"\nLMP allocation: "
    f"{LMP_WEIGHT * 100:.1f}%"
)


print(
    f"RSP allocation: "
    f"{RSP_WEIGHT * 100:.1f}%"
)


print(
    f"\nLMP expected return: "
    f"{LMP_EXPECTED_RETURN * 100:.2f}%"
)


print(
    f"RSP expected return: "
    f"{RSP_EXPECTED_RETURN * 100:.2f}%"
)


print(
    f"\nExpected total portfolio return: "
    f"{portfolio_expected_return * 100:.2f}%"
)


print(
    f"Expected total portfolio volatility: "
    f"{portfolio_volatility * 100:.2f}%"
)


print(
    f"\nMonte Carlo simulations: "
    f"{N_SIMULATIONS:,}"
)


print(
    f"Student-t degrees of freedom: "
    f"{STUDENT_T_DF}"
)


# ============================================================
# 14. GENERATE FAT-TAILED SHOCKS
# ============================================================

raw_t = rng.standard_t(

    df=STUDENT_T_DF,

    size=(

        N_SIMULATIONS,

        HORIZON_YEARS,

        2

    )

)


# Standardize variance to 1

t_scale = np.sqrt(

    STUDENT_T_DF

    /

    (
        STUDENT_T_DF
        -
        2
    )

)


standardized_t = (

    raw_t

    /

    t_scale

)


# ============================================================
# 15. APPLY COVARIANCE
# ============================================================

asset_shocks = (

    standardized_t

    @

    chol.T

)


# ============================================================
# 16. ASSET RETURNS
# ============================================================

asset_returns = (

    expected_returns

    +

    asset_shocks

)


# Prevent impossible loss >100%

asset_returns = np.maximum(

    asset_returns,

    -0.95

)


# ============================================================
# 17. EXTRACT LMP AND RSP RETURNS
# ============================================================

lmp_returns = (

    asset_returns[
        :,
        :,
        0
    ]

)


rsp_returns = (

    asset_returns[
        :,
        :,
        1
    ]

)


# ============================================================
# 18. TOTAL PORTFOLIO RETURN
# ============================================================
#
# Annual rebalancing assumption.
#
# ============================================================

portfolio_returns = (

    LMP_WEIGHT
    *
    lmp_returns

    +

    RSP_WEIGHT
    *
    rsp_returns

)


# ============================================================
# 19. PORTFOLIO RETURN STATISTICS
# ============================================================

all_annual_returns = (
    portfolio_returns.flatten()
)


annual_return_statistics = {

    "Mean":
        np.mean(
            all_annual_returns
        ),

    "Median":
        np.median(
            all_annual_returns
        ),

    "0.5th percentile":
        np.percentile(
            all_annual_returns,
            0.5
        ),

    "1st percentile":
        np.percentile(
            all_annual_returns,
            1
        ),

    "5th percentile":
        np.percentile(
            all_annual_returns,
            5
        ),

    "95th percentile":
        np.percentile(
            all_annual_returns,
            95
        ),

    "Probability negative year":
        np.mean(
            all_annual_returns
            <
            0
        )

}


print("\n" + "=" * 100)

print(
    "ANNUAL PORTFOLIO RETURN DISTRIBUTION"
)

print("=" * 100)


for label, value in annual_return_statistics.items():

    print(

        f"{label:<30}"

        f"{value * 100:>10.2f}%"

    )


# ============================================================
# 20. SIMULATE LMP AND RSP SEPARATELY
# ============================================================
#
# This allows us to calculate liquid assets at Year 15
# instead of pretending the whole portfolio is equally liquid.
#
# ============================================================

lmp_paths = np.zeros(

    (
        N_SIMULATIONS,
        HORIZON_YEARS + 1
    )

)


rsp_paths = np.zeros(

    (
        N_SIMULATIONS,
        HORIZON_YEARS + 1
    )

)


# Starting allocation

lmp_paths[:, 0] = (

    STARTING_ASSETS

    *

    LMP_WEIGHT

)


rsp_paths[:, 0] = (

    STARTING_ASSETS

    *

    RSP_WEIGHT

)


# ============================================================
# 21. SIMULATE ASSET EVOLUTION
# ============================================================
#
# Contributions are invested according to strategic
# LMP/RSP weights.
#
# ============================================================

for year in range(
    1,
    HORIZON_YEARS + 1
):

    # Grow LMP

    lmp_paths[
        :,
        year
    ] = (

        lmp_paths[
            :,
            year - 1
        ]

        *

        (
            1
            +
            lmp_returns[
                :,
                year - 1
            ]
        )

    )


    # Grow RSP

    rsp_paths[
        :,
        year
    ] = (

        rsp_paths[
            :,
            year - 1
        ]

        *

        (
            1
            +
            rsp_returns[
                :,
                year - 1
            ]
        )

    )


    # --------------------------------------------------------
    # CONTRIBUTIONS
    # --------------------------------------------------------

    if year <= CONTRIBUTION_YEARS:

        lmp_paths[
            :,
            year
        ] += (

            ANNUAL_CONTRIBUTION

            *

            LMP_WEIGHT

        )


        rsp_paths[
            :,
            year
        ] += (

            ANNUAL_CONTRIBUTION

            *

            RSP_WEIGHT

        )


    # --------------------------------------------------------
    # ANNUAL REBALANCING
    # --------------------------------------------------------
    #
    # Recombine total assets and rebalance to target weights.
    #
    # --------------------------------------------------------

    total_before_rebalance = (

        lmp_paths[
            :,
            year
        ]

        +

        rsp_paths[
            :,
            year
        ]

    )


    lmp_paths[
        :,
        year
    ] = (

        total_before_rebalance

        *

        LMP_WEIGHT

    )


    rsp_paths[
        :,
        year
    ] = (

        total_before_rebalance

        *

        RSP_WEIGHT

    )


# ============================================================
# 22. TOTAL ASSET PATHS
# ============================================================

asset_paths = (

    lmp_paths

    +

    rsp_paths

)


assets_y15 = (

    asset_paths[
        :,
        HORIZON_YEARS
    ]

)


lmp_y15 = (

    lmp_paths[
        :,
        HORIZON_YEARS
    ]

)


rsp_y15 = (

    rsp_paths[
        :,
        HORIZON_YEARS
    ]

)


# ============================================================
# 23. LIQUID ASSETS AT YEAR 15
# ============================================================
#
# Apply liquidity haircuts.
#
# ============================================================

liquid_assets_y15 = (

    LMP_LIQUIDITY_FACTOR
    *
    lmp_y15

    +

    RSP_LIQUIDITY_FACTOR
    *
    rsp_y15

)


# ============================================================
# 24. YEAR-15 ASSET DISTRIBUTION
# ============================================================

asset_distribution = {

    "0.5%":
        np.percentile(
            assets_y15,
            0.5
        ),

    "1%":
        np.percentile(
            assets_y15,
            1
        ),

    "5%":
        np.percentile(
            assets_y15,
            5
        ),

    "Median":
        np.median(
            assets_y15
        ),

    "Mean":
        np.mean(
            assets_y15
        ),

    "95%":
        np.percentile(
            assets_y15,
            95
        )

}


print("\n" + "=" * 100)

print(
    "YEAR-15 ASSET DISTRIBUTION"
)

print("=" * 100)


for label, value in asset_distribution.items():

    print(

        f"{label:<10}"

        f"EUR "

        f"{value / 1e9:>10.3f}bn"

    )


# ============================================================
# 25. TOTAL CONTRIBUTED CAPITAL
# ============================================================

total_nominal_contributions = (

    STARTING_ASSETS

    +

    (
        ANNUAL_CONTRIBUTION

        *

        CONTRIBUTION_YEARS

    )

)


# ============================================================
# 26. MONEY-WEIGHTED RETURN / IRR FUNCTION
# ============================================================
#
# Cash flows from investor perspective:
#
# t=0    : -5bn
# t=1-10 : -0.5bn
# t=15   : +ending assets
#
# We calculate one IRR for each simulation.
#
# ============================================================

def calculate_path_irr(
    ending_value
):

    cashflows = np.zeros(
        HORIZON_YEARS + 1
    )


    cashflows[0] = (
        -STARTING_ASSETS
    )


    for year in range(
        1,
        CONTRIBUTION_YEARS + 1
    ):

        cashflows[
            year
        ] = (
            -ANNUAL_CONTRIBUTION
        )


    cashflows[
        HORIZON_YEARS
    ] += (
        ending_value
    )


    # --------------------------------------------------------
    # NPV function
    # --------------------------------------------------------

    def npv(rate):

        years = np.arange(
            len(cashflows)
        )

        return np.sum(

            cashflows

            /

            (
                1
                +
                rate
            )
            **
            years

        )


    # --------------------------------------------------------
    # Bisection
    # --------------------------------------------------------

    low = -0.99

    high = 1.00


    npv_low = npv(
        low
    )

    npv_high = npv(
        high
    )


    # Expand upper bound if required

    attempts = 0


    while (

        npv_low
        *
        npv_high
        >
        0

        and

        attempts
        <
        20

    ):

        high *= 2

        npv_high = npv(
            high
        )

        attempts += 1


    if (

        npv_low
        *
        npv_high

        >
        0

    ):

        return np.nan


    for _ in range(
        100
    ):

        mid = (
            low
            +
            high
        ) / 2


        npv_mid = npv(
            mid
        )


        if abs(
            npv_mid
        ) < 1e-5:

            return mid


        if (

            npv_low
            *
            npv_mid

            <=
            0

        ):

            high = mid

            npv_high = (
                npv_mid
            )

        else:

            low = mid

            npv_low = (
                npv_mid
            )


    return (

        low
        +
        high

    ) / 2


# ============================================================
# 27. CALCULATE IRRs
# ============================================================
#
# 100,000 root searches can be slow.
#
# Therefore calculate IRR on a representative sample of
# 10,000 paths.
#
# ============================================================

IRR_SAMPLE_SIZE = min(

    10_000,

    N_SIMULATIONS

)


irr_indices = rng.choice(

    N_SIMULATIONS,

    size=IRR_SAMPLE_SIZE,

    replace=False

)


path_irrs = np.array([

    calculate_path_irr(
        assets_y15[i]
    )

    for i in irr_indices

])


path_irrs = path_irrs[

    np.isfinite(
        path_irrs
    )

]


irr_statistics = {

    "0.5%":
        np.percentile(
            path_irrs,
            0.5
        ),

    "5%":
        np.percentile(
            path_irrs,
            5
        ),

    "Median":
        np.median(
            path_irrs
        ),

    "Mean":
        np.mean(
            path_irrs
        ),

    "95%":
        np.percentile(
            path_irrs,
            95
        )

}


print("\n" + "=" * 100)

print(
    "15-YEAR MONEY-WEIGHTED PORTFOLIO RETURN (IRR)"
)

print("=" * 100)


for label, value in irr_statistics.items():

    print(

        f"{label:<10}"

        f"{value * 100:>10.2f}%"

    )


# ============================================================
# 28. SCENARIO ANALYSIS
# ============================================================

def analyse_scenario(
    scenario_name,
    scenario
):

    total_liability = (

        scenario[
            "total_liability_y15"
        ]

    )


    lump_sum = (

        scenario[
            "lump_sum_y15"
        ]

    )


    pension_liability = (

        scenario[
            "pension_pv_y15"
        ]

    )


    # --------------------------------------------------------
    # SURPLUS
    # --------------------------------------------------------

    surplus = (

        assets_y15

        -

        total_liability

    )


    # --------------------------------------------------------
    # FUNDING RATIO
    # --------------------------------------------------------

    funding_ratio = (

        assets_y15

        /

        total_liability

    )


    # --------------------------------------------------------
    # UNDERFUNDING
    # --------------------------------------------------------

    underfunded = (

        assets_y15

        <

        total_liability

    )


    # --------------------------------------------------------
    # LIQUIDITY TEST
    # --------------------------------------------------------
    #
    # Now use LIQUID assets, not total assets.
    #
    # --------------------------------------------------------

    if lump_sum > 0:

        liquidity_shortfall = (

            liquid_assets_y15

            <

            lump_sum

        )

    else:

        liquidity_shortfall = (

            np.zeros(
                N_SIMULATIONS,
                dtype=bool
            )

        )


    # --------------------------------------------------------
    # LIQUIDITY COVERAGE RATIO
    # --------------------------------------------------------

    if lump_sum > 0:

        liquidity_coverage = (

            liquid_assets_y15

            /

            lump_sum

        )

    else:

        liquidity_coverage = (

            np.full(
                N_SIMULATIONS,
                np.inf
            )

        )


    # --------------------------------------------------------
    # SHORTFALL SIZE
    # --------------------------------------------------------

    shortfall = np.maximum(

        total_liability

        -

        assets_y15,

        0

    )


    failed_shortfalls = (

        shortfall[
            shortfall
            >
            0
        ]

    )


    if len(
        failed_shortfalls
    ) > 0:

        expected_shortfall_if_failed = (

            np.mean(
                failed_shortfalls
            )

        )

    else:

        expected_shortfall_if_failed = 0


    return {

        "Scenario":
            scenario_name,

        "Lump_Sum_%":
            scenario[
                "lump_share"
            ]
            *
            100,

        "Pension_%":
            scenario[
                "pension_share"
            ]
            *
            100,

        "Lump_Sum_Y15":
            lump_sum,

        "Pension_PV_Y15":
            pension_liability,

        "Total_Liability_Y15":
            total_liability,

        "Mean_Assets_Y15":
            np.mean(
                assets_y15
            ),

        "Median_Assets_Y15":
            np.median(
                assets_y15
            ),

        "Asset_0.5pct":
            np.percentile(
                assets_y15,
                0.5
            ),

        "Asset_5pct":
            np.percentile(
                assets_y15,
                5
            ),

        "Mean_Surplus":
            np.mean(
                surplus
            ),

        "Median_Surplus":
            np.median(
                surplus
            ),

        "Surplus_0.5pct":
            np.percentile(
                surplus,
                0.5
            ),

        "Surplus_5pct":
            np.percentile(
                surplus,
                5
            ),

        "Mean_Funding_Ratio":
            np.mean(
                funding_ratio
            ),

        "Median_Funding_Ratio":
            np.median(
                funding_ratio
            ),

        "Funding_Ratio_0.5pct":
            np.percentile(
                funding_ratio,
                0.5
            ),

        "Funding_Ratio_5pct":
            np.percentile(
                funding_ratio,
                5
            ),

        "Probability_Underfunded":
            np.mean(
                underfunded
            ),

        "Probability_Liquidity_Shortfall":
            np.mean(
                liquidity_shortfall
            ),

        "Median_Liquidity_Coverage":
            (
                np.median(
                    liquidity_coverage
                )
                if lump_sum > 0
                else np.inf
            ),

        "Liquidity_Coverage_5pct":
            (
                np.percentile(
                    liquidity_coverage,
                    5
                )
                if lump_sum > 0
                else np.inf
            ),

        "Expected_Shortfall_If_Failed":
            expected_shortfall_if_failed

    }


# ============================================================
# 29. RUN ALL SCENARIOS
# ============================================================

scenario_results = []


for (
    scenario_name,
    scenario
) in SCENARIOS.items():

    scenario_results.append(

        analyse_scenario(

            scenario_name,

            scenario

        )

    )


scenario_df = pd.DataFrame(
    scenario_results
)


# ============================================================
# 30. PRESENTATION TABLE
# ============================================================

display_df = (
    scenario_df.copy()
)


eur_columns = [

    "Lump_Sum_Y15",

    "Pension_PV_Y15",

    "Total_Liability_Y15",

    "Mean_Assets_Y15",

    "Median_Assets_Y15",

    "Asset_0.5pct",

    "Asset_5pct",

    "Mean_Surplus",

    "Median_Surplus",

    "Surplus_0.5pct",

    "Surplus_5pct",

    "Expected_Shortfall_If_Failed"

]


for column in eur_columns:

    display_df[
        column
    ] /= 1e9


probability_columns = [

    "Probability_Underfunded",

    "Probability_Liquidity_Shortfall"

]


for column in probability_columns:

    display_df[
        column
    ] *= 100


funding_columns = [

    "Mean_Funding_Ratio",

    "Median_Funding_Ratio",

    "Funding_Ratio_0.5pct",

    "Funding_Ratio_5pct",

    "Median_Liquidity_Coverage",

    "Liquidity_Coverage_5pct"

]


for column in funding_columns:

    display_df[
        column
    ] *= 100


print("\n" + "=" * 125)

print(
    "POLICYHOLDER CHOICE SENSITIVITY"
)

print("=" * 125)


presentation_columns = [

    "Scenario",

    "Total_Liability_Y15",

    "Mean_Assets_Y15",

    "Median_Assets_Y15",

    "Mean_Surplus",

    "Median_Funding_Ratio",

    "Funding_Ratio_5pct",

    "Probability_Underfunded",

    "Probability_Liquidity_Shortfall"

]


print(

    display_df[
        presentation_columns
    ]

    .round(2)

    .to_string(
        index=False
    )

)


# ============================================================
# 31. BASE CASE
# ============================================================

base_case = scenario_df[

    scenario_df[
        "Scenario"
    ]

    ==

    BASE_CASE_NAME

].iloc[0]


print("\n" + "=" * 100)

print(
    "BASE CASE: 50% LUMP SUM / 50% PENSION"
)

print("=" * 100)


print(

    f"\nTotal Y15 liability: "
    f"EUR "
    f"{base_case['Total_Liability_Y15'] / 1e9:.3f}bn"

)


print(

    f"Immediate lump sum: "
    f"EUR "
    f"{base_case['Lump_Sum_Y15'] / 1e9:.3f}bn"

)


print(

    f"Remaining pension PV: "
    f"EUR "
    f"{base_case['Pension_PV_Y15'] / 1e9:.3f}bn"

)


print(

    f"\nMean Y15 assets: "
    f"EUR "
    f"{base_case['Mean_Assets_Y15'] / 1e9:.3f}bn"

)


print(

    f"Median Y15 assets: "
    f"EUR "
    f"{base_case['Median_Assets_Y15'] / 1e9:.3f}bn"

)


print(

    f"5th percentile assets: "
    f"EUR "
    f"{base_case['Asset_5pct'] / 1e9:.3f}bn"

)


print(

    f"0.5th percentile assets: "
    f"EUR "
    f"{base_case['Asset_0.5pct'] / 1e9:.3f}bn"

)


print(

    f"\nProbability underfunded: "
    f"{base_case['Probability_Underfunded'] * 100:.3f}%"

)


print(

    f"Probability liquidity shortfall: "
    f"{base_case['Probability_Liquidity_Shortfall'] * 100:.3f}%"

)


print(

    f"Median funding ratio: "
    f"{base_case['Median_Funding_Ratio'] * 100:.2f}%"

)


print(

    f"5th percentile funding ratio: "
    f"{base_case['Funding_Ratio_5pct'] * 100:.2f}%"

)


# ============================================================
# 32. PATH PERCENTILES
# ============================================================

years_axis = np.arange(
    HORIZON_YEARS + 1
)


path_p005 = np.percentile(

    asset_paths,

    0.5,

    axis=0

)


path_p05 = np.percentile(

    asset_paths,

    5,

    axis=0

)


path_median = np.percentile(

    asset_paths,

    50,

    axis=0

)


path_mean = np.mean(

    asset_paths,

    axis=0

)


path_p95 = np.percentile(

    asset_paths,

    95,

    axis=0

)


path_percentiles_df = pd.DataFrame({

    "Year":
        years_axis,

    "P0.5":
        path_p005,

    "P5":
        path_p05,

    "Median":
        path_median,

    "Mean":
        path_mean,

    "P95":
        path_p95

})


# ============================================================
# 33. CHART:
# ASSET EVOLUTION
# ============================================================
#
# IMPORTANT FIX:
#
# Do NOT draw the Y15 liability as a horizontal line
# through all 15 years.
#
# Instead show the Y15 liability ONLY at Year 15.
#
# ============================================================

plt.figure(
    figsize=(11, 7)
)


plt.fill_between(

    years_axis,

    path_p05 / 1e9,

    path_p95 / 1e9,

    alpha=0.20,

    label="5th-95th percentile"

)


plt.plot(

    years_axis,

    path_median / 1e9,

    linewidth=2,

    label="Median assets"

)


plt.plot(

    years_axis,

    path_p005 / 1e9,

    linestyle="--",

    label="0.5th percentile assets"

)


plt.scatter(

    [HORIZON_YEARS],

    [
        base_case[
            "Total_Liability_Y15"
        ]
        /
        1e9
    ],

    s=100,

    marker="X",

    label="50/50 Y15 liability"

)


plt.xlabel(
    "Projection Year"
)


plt.ylabel(
    "Assets (EUR bn)"
)


plt.title(
    "Monte Carlo Asset Evolution - 50/50 Base Case"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "01_asset_evolution.png",

    dpi=300

)


plt.show()


# ============================================================
# 34. CHART:
# ANNUAL PORTFOLIO RETURNS
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.hist(

    all_annual_returns
    *
    100,

    bins=150,

    alpha=0.75

)


plt.axvline(

    portfolio_expected_return
    *
    100,

    linestyle="--",

    linewidth=2,

    label="Expected return"

)


plt.axvline(

    0,

    linestyle=":",

    linewidth=2,

    label="0% return"

)


plt.xlabel(
    "Annual Portfolio Return (%)"
)


plt.ylabel(
    "Frequency"
)


plt.title(
    "Simulated Annual Portfolio Return Distribution"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "02_annual_return_distribution.png",

    dpi=300

)


plt.show()


# ============================================================
# 35. CHART:
# IRR DISTRIBUTION
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.hist(

    path_irrs
    *
    100,

    bins=100,

    alpha=0.75

)


plt.xlabel(
    "15-Year Money-Weighted Return / IRR (%)"
)


plt.ylabel(
    "Simulation Count"
)


plt.title(
    "15-Year Portfolio Return Distribution"
)


plt.tight_layout()


plt.savefig(

    "03_15year_IRR_distribution.png",

    dpi=300

)


plt.show()


# ============================================================
# 36. CHART:
# YEAR-15 ASSET DISTRIBUTION
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.hist(

    assets_y15
    /
    1e9,

    bins=100,

    alpha=0.75

)


plt.axvline(

    base_case[
        "Total_Liability_Y15"
    ]
    /
    1e9,

    linestyle="--",

    linewidth=2,

    label="Total Y15 liability"

)


plt.axvline(

    base_case[
        "Lump_Sum_Y15"
    ]
    /
    1e9,

    linestyle=":",

    linewidth=2,

    label="Immediate lump sum"

)


plt.xlabel(
    "Year-15 Assets (EUR bn)"
)


plt.ylabel(
    "Simulation Count"
)


plt.title(
    "Year-15 Asset Distribution - 50/50 Base Case"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "04_year15_asset_distribution.png",

    dpi=300

)


plt.show()


# ============================================================
# 37. CHART:
# FUNDING RATIO
# ============================================================

base_funding_ratio = (

    assets_y15

    /

    base_case[
        "Total_Liability_Y15"
    ]

)


plt.figure(
    figsize=(10, 7)
)


plt.hist(

    base_funding_ratio
    *
    100,

    bins=100,

    alpha=0.75

)


plt.axvline(

    100,

    linestyle="--",

    linewidth=2,

    label="100% funded"

)


plt.xlabel(
    "Funding Ratio (%)"
)


plt.ylabel(
    "Simulation Count"
)


plt.title(
    "Funding Ratio Distribution - 50/50 Base Case"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "05_funding_ratio_distribution.png",

    dpi=300

)


plt.show()


# ============================================================
# 38. CHART:
# POLICYHOLDER SENSITIVITY
# ============================================================

scenario_plot = (

    scenario_df

    .sort_values(
        "Lump_Sum_%"
    )

)


plt.figure(
    figsize=(10, 7)
)


plt.plot(

    scenario_plot[
        "Lump_Sum_%"
    ],

    scenario_plot[
        "Probability_Underfunded"
    ]
    *
    100,

    marker="o",

    label="Underfunding probability"

)


plt.plot(

    scenario_plot[
        "Lump_Sum_%"
    ],

    scenario_plot[
        "Probability_Liquidity_Shortfall"
    ]
    *
    100,

    marker="s",

    label="Liquidity shortfall probability"

)


plt.xlabel(
    "Policyholders Choosing Lump Sum (%)"
)


plt.ylabel(
    "Probability (%)"
)


plt.title(
    "Policyholder Choice Sensitivity"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "06_policyholder_sensitivity.png",

    dpi=300

)


plt.show()


# ============================================================
# 39. CHART:
# ASSET CAPACITY VS LIABILITY
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.plot(

    scenario_plot[
        "Lump_Sum_%"
    ],

    scenario_plot[
        "Total_Liability_Y15"
    ]
    /
    1e9,

    marker="o",

    label="Y15 liability"

)


plt.axhline(

    np.median(
        assets_y15
    )
    /
    1e9,

    linestyle="--",

    label="Median Y15 assets"

)


plt.axhline(

    np.percentile(
        assets_y15,
        5
    )
    /
    1e9,

    linestyle=":",

    label="5th percentile Y15 assets"

)


plt.axhline(

    np.percentile(
        assets_y15,
        0.5
    )
    /
    1e9,

    linestyle="-.",

    label="0.5th percentile Y15 assets"

)


plt.xlabel(
    "Lump-Sum Take-Up (%)"
)


plt.ylabel(
    "EUR bn"
)


plt.title(
    "Asset Capacity vs Policyholder Choice"
)


plt.legend()


plt.tight_layout()


plt.savefig(

    "07_asset_vs_liability.png",

    dpi=300

)


plt.show()


# ============================================================
# 40. EXPORT RESULTS
# ============================================================

annual_return_df = pd.DataFrame({

    "Metric":
        list(
            annual_return_statistics.keys()
        ),

    "Value":
        list(
            annual_return_statistics.values()
        )

})


irr_df = pd.DataFrame({

    "Metric":
        list(
            irr_statistics.keys()
        ),

    "IRR":
        list(
            irr_statistics.values()
        )

})


assumptions_df = pd.DataFrame({

    "Parameter": [

        "Starting assets",

        "Annual contribution",

        "Contribution years",

        "Projection horizon",

        "LMP weight",

        "RSP weight",

        "LMP expected return",

        "LMP volatility",

        "RSP expected return",

        "RSP volatility",

        "LMP-RSP correlation",

        "LMP liquidity factor",

        "RSP liquidity factor",

        "Student-t degrees freedom",

        "Number simulations"

    ],

    "Value": [

        STARTING_ASSETS,

        ANNUAL_CONTRIBUTION,

        CONTRIBUTION_YEARS,

        HORIZON_YEARS,

        LMP_WEIGHT,

        RSP_WEIGHT,

        LMP_EXPECTED_RETURN,

        LMP_VOLATILITY,

        RSP_EXPECTED_RETURN,

        RSP_VOLATILITY,

        LMP_RSP_CORRELATION,

        LMP_LIQUIDITY_FACTOR,

        RSP_LIQUIDITY_FACTOR,

        STUDENT_T_DF,

        N_SIMULATIONS

    ]

})


base_case_simulations = pd.DataFrame({

    "Assets_Y15":
        assets_y15,

    "Liquid_Assets_Y15":
        liquid_assets_y15,

    "Surplus_Y15":
        (
            assets_y15

            -

            base_case[
                "Total_Liability_Y15"
            ]
        ),

    "Funding_Ratio":
        base_funding_ratio,

    "Underfunded":
        (
            assets_y15

            <

            base_case[
                "Total_Liability_Y15"
            ]
        ),

    "Liquidity_Shortfall":
        (
            liquid_assets_y15

            <

            base_case[
                "Lump_Sum_Y15"
            ]
        )

})


with pd.ExcelWriter(

    "integrated_monte_carlo_ALM.xlsx",

    engine="openpyxl"

) as writer:


    assumptions_df.to_excel(

        writer,

        sheet_name="Assumptions",

        index=False

    )


    annual_return_df.to_excel(

        writer,

        sheet_name="Annual Returns",

        index=False

    )


    irr_df.to_excel(

        writer,

        sheet_name="15Y IRR",

        index=False

    )


    scenario_df.to_excel(

        writer,

        sheet_name="Scenario Results",

        index=False

    )


    display_df.to_excel(

        writer,

        sheet_name="Presentation Table",

        index=False

    )


    path_percentiles_df.to_excel(

        writer,

        sheet_name="Asset Paths",

        index=False

    )


    base_case_simulations.to_excel(

        writer,

        sheet_name="Base Case Simulations",

        index=False

    )


# ============================================================
# 41. FINAL SUMMARY
# ============================================================

print("\n" + "=" * 100)

print(
    "INTEGRATED MONTE CARLO COMPLETE"
)

print("=" * 100)


print(
    "\nFiles created:"
)


print(
    "1. integrated_monte_carlo_ALM.xlsx"
)


print(
    "2. 01_asset_evolution.png"
)


print(
    "3. 02_annual_return_distribution.png"
)


print(
    "4. 03_15year_IRR_distribution.png"
)


print(
    "5. 04_year15_asset_distribution.png"
)


print(
    "6. 05_funding_ratio_distribution.png"
)


print(
    "7. 06_policyholder_sensitivity.png"
)


print(
    "8. 07_asset_vs_liability.png"
)


print("\n" + "=" * 100)

print(
    "IMPORTANT MODEL LIMITATIONS"
)

print("=" * 100)


print(
    """
1. LMP return and volatility are still assumptions until the
   final liability-matching bond portfolio is fully measured.

2. The 70/30 LMP-RSP allocation is an assumption and should
   be replaced by the final strategic asset allocation.

3. The RSP 12.43% return and 16.46% volatility are historical
   pre-CDX statistics.

4. The model does not yet simulate changing EIOPA curves.

5. Pension liabilities are represented by their Year-15 PV.
   Pension cash flows after Year 15 are not yet individually
   simulated.

6. Liquidity factors are assumptions rather than observed
   bid-ask spreads / liquidation haircuts.

Therefore this model should be presented as a stochastic
ALM sensitivity model, not as a regulatory solvency model.
"""
)