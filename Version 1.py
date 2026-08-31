import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================================================
# MONTE CARLO INTEREST-RATE VaR
# Case 1B - Vonovia
# ============================================================

CONFIDENCE_LEVEL = 0.95
VAR_HORIZON_DAYS = 10
N_SIMULATIONS = 100_000
RANDOM_SEED = 42

np.random.seed(RANDOM_SEED)


# ============================================================
# 1. LOAD HISTORICAL EUR CURVE DATA
# ============================================================
#
# Expected Excel structure:
#
# Date | 1Y | 2Y | 3Y | 5Y | 7Y | 10Y | 15Y | 20Y | 30Y
#
# Rates should ideally be stored as decimals:
# 2.50% -> 0.025
#
# If Bloomberg gives 2.50 instead, divide columns by 100.

rates = pd.read_excel(
    "EUR_Historical_Curves.xlsx",
    parse_dates=["Date"]
)

rates = rates.sort_values("Date").set_index("Date")

curve_nodes = [
    "1Y", "2Y", "3Y", "5Y", "7Y",
    "10Y", "15Y", "20Y", "30Y"
]

rates = rates[curve_nodes].dropna()


# ============================================================
# 2. CALCULATE HISTORICAL DAILY RATE CHANGES
# ============================================================
#
# IMPORTANT:
# We model ABSOLUTE rate changes:
#
#     Delta r = r(t) - r(t-1)
#
# Example:
# 3.00% -> 3.05%
#
# change = +0.0005 = +5 basis points
#
# This is preferable to percentage returns for interest rates.

daily_changes = rates.diff().dropna()


# ============================================================
# 3. ESTIMATE COVARIANCE AND CORRELATION
# ============================================================

daily_covariance = daily_changes.cov().values
correlation_matrix = daily_changes.corr()

print("\nHistorical correlation matrix:")
print(correlation_matrix.round(3))


# ============================================================
# 4. CONVERT DAILY COVARIANCE TO 10-DAY COVARIANCE
# ============================================================
#
# Simple square-root-of-time framework:
#
# variance scales approximately with time.
#
# Therefore:
#
# Cov_10day = Cov_daily * 10

horizon_covariance = daily_covariance * VAR_HORIZON_DAYS


# ============================================================
# 5. DEFINE TODAY'S EUR CURVE
# ============================================================
#
# Replace these numbers with today's Bloomberg curve.
#
# These are PLACEHOLDERS ONLY.

current_curve = np.array([
    0.0200,   # 1Y
    0.0210,   # 2Y
    0.0220,   # 3Y
    0.0240,   # 5Y
    0.0255,   # 7Y
    0.0270,   # 10Y
    0.0285,   # 15Y
    0.0290,   # 20Y
    0.0295    # 30Y
])

maturities = np.array([
    1, 2, 3, 5, 7, 10, 15, 20, 30
])


# ============================================================
# 6. GENERATE MONTE CARLO RATE SHOCKS
# ============================================================
#
# We assume:
#
# Delta r ~ Multivariate Normal(0, Sigma)
#
# Sigma contains the historical volatility and correlation
# structure of the EUR curve.

mean_shock = np.zeros(len(curve_nodes))

simulated_shocks = np.random.multivariate_normal(
    mean=mean_shock,
    cov=horizon_covariance,
    size=N_SIMULATIONS
)


# ============================================================
# 7. GENERATE 100,000 FUTURE EUR CURVES
# ============================================================

simulated_curves = current_curve + simulated_shocks


# ============================================================
# 8. BOND PRICING FUNCTION
# ============================================================

def bond_price(
    face_value,
    coupon_rate,
    maturity,
    curve,
    maturities,
    coupon_frequency=1
):
    """
    Simplified fixed-rate bond valuation.

    face_value:
        Bond notional

    coupon_rate:
        Annual coupon as decimal
        e.g. 0.04 = 4%

    maturity:
        Remaining maturity in years

    curve:
        Zero/discount rate curve

    maturities:
        Maturities corresponding to curve points

    coupon_frequency:
        Number of coupon payments per year
    """

    periods = int(round(maturity * coupon_frequency))

    payment_times = (
        np.arange(1, periods + 1) / coupon_frequency
    )

    # Linear interpolation of the yield curve
    interpolated_rates = np.interp(
        payment_times,
        maturities,
        curve
    )

    coupon_payment = (
        face_value
        * coupon_rate
        / coupon_frequency
    )

    cashflows = np.full(
        periods,
        coupon_payment,
        dtype=float
    )

    cashflows[-1] += face_value

    # Exponential/continuous discounting
    discount_factors = np.exp(
        -interpolated_rates * payment_times
    )

    price = np.sum(
        cashflows * discount_factors
    )

    return price


# ============================================================
# 9. DEFINE VONOVIA PORTFOLIO
# ============================================================
#
# Replace this example with Bloomberg's actual bond data.
#
# Example only:

portfolio = [
    {
        "name": "Bond A",
        "face": 500_000_000,
        "coupon": 0.0200,
        "maturity": 3,
        "frequency": 1
    },

    {
        "name": "Bond B",
        "face": 750_000_000,
        "coupon": 0.0250,
        "maturity": 7,
        "frequency": 1
    },

    {
        "name": "Bond C",
        "face": 1_000_000_000,
        "coupon": 0.0300,
        "maturity": 10,
        "frequency": 1
    }
]


# ============================================================
# 10. VALUE PORTFOLIO TODAY
# ============================================================

def portfolio_value(curve):

    total_value = 0.0

    for bond in portfolio:

        value = bond_price(
            face_value=bond["face"],
            coupon_rate=bond["coupon"],
            maturity=bond["maturity"],
            curve=curve,
            maturities=maturities,
            coupon_frequency=bond["frequency"]
        )

        total_value += value

    return total_value


current_portfolio_value = portfolio_value(
    current_curve
)

print(
    "\nCurrent portfolio value:",
    f"EUR {current_portfolio_value:,.2f}"
)


# ============================================================
# 11. REVALUE PORTFOLIO UNDER EVERY SIMULATED CURVE
# ============================================================

simulated_values = np.empty(
    N_SIMULATIONS
)

for i in range(N_SIMULATIONS):

    simulated_values[i] = portfolio_value(
        simulated_curves[i]
    )


# ============================================================
# 12. CALCULATE P&L
# ============================================================
#
# P&L =
#
# simulated portfolio value
# -
# current portfolio value

pnl = (
    simulated_values
    - current_portfolio_value
)


# ============================================================
# 13. CALCULATE 95% VaR
# ============================================================
#
# At 95% confidence we examine the 5th percentile
# of the P&L distribution.

tail_probability = 1 - CONFIDENCE_LEVEL

pnl_cutoff = np.quantile(
    pnl,
    tail_probability
)

VaR_95 = -pnl_cutoff


# ============================================================
# 14. EXPECTED SHORTFALL
# ============================================================
#
# Average loss conditional on being beyond VaR.

tail_losses = pnl[
    pnl <= pnl_cutoff
]

expected_shortfall = -tail_losses.mean()


# ============================================================
# 15. OUTPUT RESULTS
# ============================================================

print("\n------------------------------------")
print("MONTE CARLO INTEREST-RATE RISK")
print("------------------------------------")

print(
    f"Simulations: {N_SIMULATIONS:,}"
)

print(
    f"Horizon: {VAR_HORIZON_DAYS} trading days"
)

print(
    f"Confidence level: "
    f"{CONFIDENCE_LEVEL:.0%}"
)

print(
    f"Current portfolio PV: "
    f"EUR {current_portfolio_value:,.2f}"
)

print(
    f"95% VaR: "
    f"EUR {VaR_95:,.2f}"
)

print(
    f"95% Expected Shortfall: "
    f"EUR {expected_shortfall:,.2f}"
)


# ============================================================
# 16. PLOT P&L DISTRIBUTION
# ============================================================

plt.figure(figsize=(10, 6))

plt.hist(
    pnl / 1_000_000,
    bins=100
)

plt.axvline(
    pnl_cutoff / 1_000_000,
    linestyle="--",
    linewidth=2,
    label=f"95% VaR = EUR {VaR_95/1e6:.2f}m"
)

plt.xlabel("10-Day Portfolio P&L (EUR millions)")
plt.ylabel("Frequency")

plt.title(
    "Monte Carlo Distribution of Vonovia "
    "Interest-Rate P&L"
)

plt.legend()
plt.tight_layout()
plt.show()