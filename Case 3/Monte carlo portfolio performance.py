import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# ALL-KANNS LIFE INSURANCE
# 15-YEAR MONTE CARLO ALM MODEL
#
# BASE CASE:
# 50% lump sum / 50% pension
#
# SENSITIVITY:
# 0/100
# 25/75
# 50/50
# 75/25
# 100/0
# ============================================================


# ============================================================
# 1. GENERAL SETTINGS
# ============================================================

RANDOM_SEED = 42

N_SIMULATIONS = 100_000

HORIZON_YEARS = 15

STARTING_ASSETS = 5_000_000_000

ANNUAL_CONTRIBUTION = 500_000_000

CONTRIBUTION_YEARS = 10


# ============================================================
# 2. ASSET ALLOCATION BETWEEN TWO PORTFOLIOS
# ============================================================
#
# IMPORTANT:
#
# Change these once your liability-matching allocation
# has been finalized.
#
# They MUST sum to 1.
#
# Example below:
#
# 70% Liability-Matching Portfolio
# 30% Return-Seeking Portfolio
# ============================================================

LMP_WEIGHT = 0.70

RSP_WEIGHT = 0.30


if abs(
    LMP_WEIGHT
    +
    RSP_WEIGHT
    -
    1.0
) > 1e-10:

    raise ValueError(
        "LMP_WEIGHT + RSP_WEIGHT must equal 1."
    )


# ============================================================
# 3. RETURN-SEEKING PORTFOLIO ASSUMPTIONS
# ============================================================
#
# From your Aggressive Diversified optimization:
#
# Expected historical return = 12.43%
# Annualized volatility      = 16.46%
#
# IMPORTANT:
#
# These are historical estimates.
# They are NOT guaranteed future returns.
#
# ============================================================

RSP_EXPECTED_RETURN = 0.1243

RSP_VOLATILITY = 0.1646


# ============================================================
# 4. LIABILITY-MATCHING PORTFOLIO ASSUMPTIONS
# ============================================================
#
# TEMPORARY INPUTS.
#
# Replace these with the expected return / volatility
# calculated from your final liability-matching bond portfolio.
#
# Because this is primarily long-dated EUR government/SSA
# fixed income, we currently use illustrative values.
#
# ============================================================

LMP_EXPECTED_RETURN = 0.035

LMP_VOLATILITY = 0.060


# ============================================================
# 5. CORRELATION BETWEEN LMP AND RSP
# ============================================================
#
# This determines how strongly the two asset buckets move
# together.
#
# 0.20 is currently an explicit assumption.
#
# Replace it with an empirical estimate if available.
# ============================================================

LMP_RSP_CORRELATION = 0.20


# ============================================================
# 6. FAT-TAIL ASSUMPTION
# ============================================================
#
# Instead of assuming normal returns, use Student-t.
#
# Lower degrees of freedom = fatter tails.
#
# 5 is a reasonable stress-oriented assumption.
# ============================================================

STUDENT_T_DF = 5


# ============================================================
# 7. LIABILITY SCENARIOS
# ============================================================
#
# These numbers come from your completed mixed-liability
# scenario analysis.
#
# Values are Year-15 liability values.
#
# ============================================================

SCENARIOS = {

    "0% Lump / 100% Pension": {

        "lump_share": 0.00,

        "pension_share": 1.00,

        "lump_sum_y15":
            0.000e9,

        "pension_pv_y15":
            8.717e9,

        "total_liability_y15":
            8.717e9
    },


    "25% Lump / 75% Pension": {

        "lump_share": 0.25,

        "pension_share": 0.75,

        "lump_sum_y15":
            2.826e9,

        "pension_pv_y15":
            6.538e9,

        "total_liability_y15":
            9.364e9
    },


    "50% Lump / 50% Pension": {

        "lump_share": 0.50,

        "pension_share": 0.50,

        "lump_sum_y15":
            5.651e9,

        "pension_pv_y15":
            4.359e9,

        "total_liability_y15":
            10.010e9
    },


    "75% Lump / 25% Pension": {

        "lump_share": 0.75,

        "pension_share": 0.25,

        "lump_sum_y15":
            8.477e9,

        "pension_pv_y15":
            2.179e9,

        "total_liability_y15":
            10.656e9
    },


    "100% Lump / 0% Pension": {

        "lump_share": 1.00,

        "pension_share": 0.00,

        "lump_sum_y15":
            11.303e9,

        "pension_pv_y15":
            0.000e9,

        "total_liability_y15":
            11.303e9
    }

}


BASE_CASE_NAME = (
    "50% Lump / 50% Pension"
)


# ============================================================
# 8. RANDOM NUMBER GENERATOR
# ============================================================

rng = np.random.default_rng(
    RANDOM_SEED
)


# ============================================================
# 9. ASSET EXPECTED RETURN VECTOR
# ============================================================

expected_returns = np.array([

    LMP_EXPECTED_RETURN,

    RSP_EXPECTED_RETURN

])


volatilities = np.array([

    LMP_VOLATILITY,

    RSP_VOLATILITY

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


# ============================================================
# 12. CHOLESKY DECOMPOSITION
# ============================================================

chol = np.linalg.cholesky(
    covariance_matrix
)


# ============================================================
# 13. PORTFOLIO WEIGHTS
# ============================================================

portfolio_weights = np.array([

    LMP_WEIGHT,

    RSP_WEIGHT

])


# ============================================================
# 14. THEORETICAL PORTFOLIO STATISTICS
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


print("\n" + "=" * 90)

print(
    "ALL-KANNS LIFE INSURANCE"
)

print(
    "15-YEAR MONTE CARLO ALM MODEL"
)

print("=" * 90)


print(
    f"\nStarting assets: "
    f"EUR {STARTING_ASSETS / 1e9:.3f}bn"
)


print(
    f"Annual contribution: "
    f"EUR {ANNUAL_CONTRIBUTION / 1e9:.3f}bn"
)


print(
    f"Contribution years: "
    f"{CONTRIBUTION_YEARS}"
)


print(
    f"\nLMP weight: "
    f"{LMP_WEIGHT * 100:.1f}%"
)


print(
    f"RSP weight: "
    f"{RSP_WEIGHT * 100:.1f}%"
)


print(
    f"\nExpected portfolio return: "
    f"{portfolio_expected_return * 100:.2f}%"
)


print(
    f"Portfolio volatility: "
    f"{portfolio_volatility * 100:.2f}%"
)


print(
    f"\nMonte Carlo paths: "
    f"{N_SIMULATIONS:,}"
)


print(
    f"Student-t degrees of freedom: "
    f"{STUDENT_T_DF}"
)


# ============================================================
# 15. SIMULATE CORRELATED FAT-TAILED RETURNS
# ============================================================
#
# Generate standardized Student-t shocks.
#
# A Student-t(df) has variance:
#
# df / (df - 2)
#
# So divide by sqrt(df/(df-2))
# to make variance approximately 1.
#
# ============================================================

raw_t = rng.standard_t(

    df=STUDENT_T_DF,

    size=(
        N_SIMULATIONS,
        HORIZON_YEARS,
        2
    )

)


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
# 16. APPLY CORRELATION + VOLATILITY
# ============================================================

asset_shocks = (

    standardized_t

    @

    chol.T

)


# ============================================================
# 17. CREATE ASSET RETURNS
# ============================================================
#
# Return = expected return + shock
#
# We cap return below at -95% because an unlevered asset
# portfolio cannot lose more than 100%.
#
# ============================================================

asset_returns = (

    expected_returns

    +

    asset_shocks

)


asset_returns = np.maximum(

    asset_returns,

    -0.95

)


# ============================================================
# 18. COMBINE INTO TOTAL PORTFOLIO RETURN
# ============================================================
#
# Assumes annual rebalancing back to LMP/RSP target weights.
# ============================================================

portfolio_returns = (

    asset_returns

    @

    portfolio_weights

)


# ============================================================
# 19. SIMULATE ASSET VALUES
# ============================================================
#
# assets[:,0] = today
#
# assets[:,1] = end Year 1
# ...
# assets[:,15] = end Year 15
#
# Contributions are added at END of Years 1-10.
#
# ============================================================

asset_paths = np.zeros(

    (
        N_SIMULATIONS,
        HORIZON_YEARS + 1
    )

)


asset_paths[:, 0] = (
    STARTING_ASSETS
)


for year in range(
    1,
    HORIZON_YEARS + 1
):

    annual_return = (

        portfolio_returns[
            :,
            year - 1
        ]

    )


    # --------------------------------------------------------
    # Grow existing assets
    # --------------------------------------------------------

    asset_paths[
        :,
        year
    ] = (

        asset_paths[
            :,
            year - 1
        ]

        *

        (
            1
            +
            annual_return
        )

    )


    # --------------------------------------------------------
    # Add policyholder contributions at END of Years 1-10
    # --------------------------------------------------------

    if (
        year
        <=
        CONTRIBUTION_YEARS
    ):

        asset_paths[
            :,
            year
        ] += (
            ANNUAL_CONTRIBUTION
        )


# ============================================================
# 20. YEAR-15 ASSET VALUES
# ============================================================

assets_y15 = (

    asset_paths[
        :,
        HORIZON_YEARS
    ]

)


# ============================================================
# 21. GENERAL ASSET DISTRIBUTION STATISTICS
# ============================================================

asset_percentiles = {

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
        np.percentile(
            assets_y15,
            50
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


print("\n" + "=" * 90)

print(
    "YEAR-15 ASSET DISTRIBUTION"
)

print("=" * 90)


for label, value in asset_percentiles.items():

    print(

        f"{label:<10} "

        f"EUR "
        f"{value / 1e9:>10.3f}bn"

    )


# ============================================================
# 22. SCENARIO ANALYSIS FUNCTION
# ============================================================

def analyse_scenario(
    scenario_name,
    scenario_data
):

    total_liability = (

        scenario_data[
            "total_liability_y15"
        ]

    )


    lump_sum_required = (

        scenario_data[
            "lump_sum_y15"
        ]

    )


    pension_liability = (

        scenario_data[
            "pension_pv_y15"
        ]

    )


    # --------------------------------------------------------
    # Surplus
    # --------------------------------------------------------

    surplus = (

        assets_y15

        -

        total_liability

    )


    # --------------------------------------------------------
    # Funding ratio
    # --------------------------------------------------------

    funding_ratio = (

        assets_y15

        /

        total_liability

    )


    # --------------------------------------------------------
    # Underfunding probability
    # --------------------------------------------------------

    probability_underfunded = (

        np.mean(
            assets_y15
            <
            total_liability
        )

    )


    # --------------------------------------------------------
    # Liquidity shortfall
    #
    # Conservative interpretation:
    #
    # Do total assets at Y15 cover the immediate lump sum?
    #
    # Later we can replace this with LIQUID assets only.
    # --------------------------------------------------------

    if lump_sum_required > 0:

        probability_lump_shortfall = (

            np.mean(

                assets_y15

                <

                lump_sum_required

            )

        )

    else:

        probability_lump_shortfall = 0.0


    # --------------------------------------------------------
    # Expected shortfall amount conditional on underfunding
    # --------------------------------------------------------

    shortfalls = (

        total_liability

        -

        assets_y15

    )


    shortfalls = shortfalls[

        shortfalls
        >
        0

    ]


    if len(shortfalls) > 0:

        expected_shortfall_if_failed = (

            np.mean(
                shortfalls
            )

        )

    else:

        expected_shortfall_if_failed = 0.0


    # --------------------------------------------------------
    # Percentile funding ratios
    # --------------------------------------------------------

    funding_ratio_p005 = (

        np.percentile(
            funding_ratio,
            0.5
        )

    )


    funding_ratio_p05 = (

        np.percentile(
            funding_ratio,
            5
        )

    )


    funding_ratio_median = (

        np.percentile(
            funding_ratio,
            50
        )

    )


    funding_ratio_mean = (

        np.mean(
            funding_ratio
        )

    )


    # --------------------------------------------------------
    # Surplus percentiles
    # --------------------------------------------------------

    surplus_p005 = (

        np.percentile(
            surplus,
            0.5
        )

    )


    surplus_p05 = (

        np.percentile(
            surplus,
            5
        )

    )


    surplus_median = (

        np.percentile(
            surplus,
            50
        )

    )


    surplus_mean = (

        np.mean(
            surplus
        )

    )


    return {

        "Scenario":
            scenario_name,

        "Lump_Sum_%":
            scenario_data[
                "lump_share"
            ]
            *
            100,

        "Pension_%":
            scenario_data[
                "pension_share"
            ]
            *
            100,

        "Lump_Sum_Y15":
            lump_sum_required,

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
            surplus_mean,

        "Median_Surplus":
            surplus_median,

        "Surplus_0.5pct":
            surplus_p005,

        "Surplus_5pct":
            surplus_p05,

        "Mean_Funding_Ratio":
            funding_ratio_mean,

        "Median_Funding_Ratio":
            funding_ratio_median,

        "Funding_Ratio_0.5pct":
            funding_ratio_p005,

        "Funding_Ratio_5pct":
            funding_ratio_p05,

        "Probability_Underfunded":
            probability_underfunded,

        "Probability_Lump_Sum_Shortfall":
            probability_lump_shortfall,

        "Expected_Shortfall_If_Failed":
            expected_shortfall_if_failed

    }


# ============================================================
# 23. RUN ALL POLICYHOLDER SCENARIOS
# ============================================================

scenario_results = []


for (
    scenario_name,
    scenario_data
) in SCENARIOS.items():

    result = analyse_scenario(

        scenario_name,

        scenario_data

    )


    scenario_results.append(
        result
    )


scenario_df = pd.DataFrame(
    scenario_results
)


# ============================================================
# 24. PRINT SCENARIO TABLE
# ============================================================

print("\n" + "=" * 120)

print(
    "POLICYHOLDER CHOICE SENSITIVITY"
)

print("=" * 120)


display_df = scenario_df.copy()


# Convert EUR values to billions

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


# Convert probabilities to percentages

probability_columns = [

    "Probability_Underfunded",

    "Probability_Lump_Sum_Shortfall"

]


for column in probability_columns:

    display_df[
        column
    ] *= 100


# Convert funding ratios to percentages

funding_columns = [

    "Mean_Funding_Ratio",

    "Median_Funding_Ratio",

    "Funding_Ratio_0.5pct",

    "Funding_Ratio_5pct"

]


for column in funding_columns:

    display_df[
        column
    ] *= 100


presentation_columns = [

    "Scenario",

    "Total_Liability_Y15",

    "Mean_Assets_Y15",

    "Median_Assets_Y15",

    "Mean_Surplus",

    "Median_Funding_Ratio",

    "Funding_Ratio_5pct",

    "Probability_Underfunded",

    "Probability_Lump_Sum_Shortfall"

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
# 25. BASE CASE RESULTS
# ============================================================

base_case = scenario_df[

    scenario_df[
        "Scenario"
    ]
    ==
    BASE_CASE_NAME

].iloc[0]


print("\n" + "=" * 90)

print(
    "BASE CASE: 50% LUMP SUM / 50% PENSION"
)

print("=" * 90)


print(

    f"\nYear-15 liability: "
    f"EUR "
    f"{base_case['Total_Liability_Y15'] / 1e9:.3f}bn"

)


print(

    f"Lump-sum requirement: "
    f"EUR "
    f"{base_case['Lump_Sum_Y15'] / 1e9:.3f}bn"

)


print(

    f"Pension liability PV: "
    f"EUR "
    f"{base_case['Pension_PV_Y15'] / 1e9:.3f}bn"

)


print(

    f"\nMean assets at Y15: "
    f"EUR "
    f"{base_case['Mean_Assets_Y15'] / 1e9:.3f}bn"

)


print(

    f"Median assets at Y15: "
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
    f"{base_case['Probability_Underfunded'] * 100:.2f}%"

)


print(

    f"Probability lump-sum shortfall: "
    f"{base_case['Probability_Lump_Sum_Shortfall'] * 100:.2f}%"

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
# 26. ASSET PATH PERCENTILES THROUGH TIME
# ============================================================

years_axis = np.arange(
    0,
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
# 27. CHART 1:
# MONTE CARLO ASSET PATHS
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

    label="0.5th percentile"

)


plt.axhline(

    y=(
        base_case[
            "Total_Liability_Y15"
        ]
        /
        1e9
    ),

    linestyle=":",

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

    "monte_carlo_asset_paths.png",

    dpi=300

)


plt.show()


# ============================================================
# 28. CHART 2:
# YEAR-15 ASSET DISTRIBUTION
# ============================================================

plt.figure(
    figsize=(10, 7)
)


plt.hist(

    assets_y15 / 1e9,

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

    label="Total liability"

)


plt.axvline(

    base_case[
        "Lump_Sum_Y15"
    ]
    /
    1e9,

    linestyle=":",

    linewidth=2,

    label="Lump-sum requirement"

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

    "year15_asset_distribution.png",

    dpi=300

)


plt.show()


# ============================================================
# 29. CHART 3:
# BASE CASE FUNDING RATIO DISTRIBUTION
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

    label="Fully funded"

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

    "base_case_funding_ratio.png",

    dpi=300

)


plt.show()


# ============================================================
# 30. CHART 4:
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
        "Probability_Lump_Sum_Shortfall"
    ]
    *
    100,

    marker="s",

    label="Lump-sum liquidity shortfall"

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

    "policyholder_sensitivity.png",

    dpi=300

)


plt.show()


# ============================================================
# 31. CHART 5:
# LIABILITY VS ASSET PERCENTILES
# ============================================================

plt.figure(
    figsize=(10, 7)
)


x = (
    scenario_plot[
        "Lump_Sum_%"
    ]
)


plt.plot(

    x,

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

    "asset_vs_liability_sensitivity.png",

    dpi=300

)


plt.show()


# ============================================================
# 32. EXPORT RESULTS TO EXCEL
# ============================================================

with pd.ExcelWriter(

    "monte_carlo_ALM_results.xlsx",

    engine="openpyxl"

) as writer:


    # Scenario summary

    scenario_df.to_excel(

        writer,

        sheet_name="Scenario Results",

        index=False

    )


    # Presentation version

    display_df.to_excel(

        writer,

        sheet_name="Scenario EUR bn",

        index=False

    )


    # Asset path percentiles

    path_percentiles_df.to_excel(

        writer,

        sheet_name="Asset Path Percentiles",

        index=False

    )


    # Base case simulated values

    base_case_simulations = pd.DataFrame({

        "Assets_Y15":
            assets_y15,

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

        "Lump_Sum_Shortfall":
            (
                assets_y15
                <
                base_case[
                    "Lump_Sum_Y15"
                ]
            )

    })


    base_case_simulations.to_excel(

        writer,

        sheet_name="Base Case Simulations",

        index=False

    )


    # Model assumptions

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

            "Student-t degrees of freedom",

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

            STUDENT_T_DF,

            N_SIMULATIONS

        ]

    })


    assumptions_df.to_excel(

        writer,

        sheet_name="Assumptions",

        index=False

    )


# ============================================================
# 33. FINAL MESSAGE
# ============================================================

print("\n" + "=" * 90)

print(
    "MONTE CARLO COMPLETE"
)

print("=" * 90)


print(
    "\nFiles created:"
)


print(
    "1. monte_carlo_ALM_results.xlsx"
)


print(
    "2. monte_carlo_asset_paths.png"
)


print(
    "3. year15_asset_distribution.png"
)


print(
    "4. base_case_funding_ratio.png"
)


print(
    "5. policyholder_sensitivity.png"
)


print(
    "6. asset_vs_liability_sensitivity.png"
)