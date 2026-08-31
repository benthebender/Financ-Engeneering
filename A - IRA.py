"""
Financial Engineering - Case Day 1
Receiver Interest Rate Swap: pricing and scenario risk analysis

Conventions (per case sheet):
  - Single curve approach, annual periods only, no broken dates
  - Bond base (ISDA, 30/360, exponential compounding => DF = 1 / (1 + r)^t)
  - The 1Y swap rate is also the 1Y spot rate
  - Notional 100
"""

import numpy as np
import pandas as pd


# ============================================================
# 1. INPUT DATA
# ============================================================

NOTIONAL = 100

# Base swap curve: 4.00% at 1Y, +15 bp per year
base_curve = np.array([
    0.0400,  # 1Y
    0.0415,  # 2Y
    0.0430,  # 3Y
    0.0445,  # 4Y
    0.0460,  # 5Y
    0.0475,  # 6Y
    0.0490,  # 7Y
    0.0505,  # 8Y
    0.0520,  # 9Y
    0.0535   # 10Y
])

# Fixed rates locked in at inception = par swap rates of the base curve
K_5Y = 0.0460
K_10Y = 0.0535


# ============================================================
# 2. SIX INTEREST-RATE SCENARIOS
# ============================================================

scenarios = {

    "1 (+100 bp)": np.array([
        0.0500, 0.0515, 0.0530, 0.0545, 0.0560,
        0.0575, 0.0590, 0.0605, 0.0620, 0.0635
    ]),

    "2 (-100 bp)": np.array([
        0.0300, 0.0315, 0.0330, 0.0345, 0.0360,
        0.0375, 0.0390, 0.0405, 0.0420, 0.0435
    ]),

    "3 (flatter around 5Y)": np.array([
        0.0480, 0.0475, 0.0470, 0.0465, 0.0460,
        0.0465, 0.0470, 0.0475, 0.0480, 0.0485
    ]),

    "4 (steeper around 5Y)": np.array([
        0.0320, 0.0355, 0.0390, 0.0425, 0.0460,
        0.0485, 0.0510, 0.0535, 0.0560, 0.0585
    ]),

    "5 (flatter from year 2)": np.array([
        0.0400, 0.0395, 0.0390, 0.0385, 0.0380,
        0.0375, 0.0370, 0.0365, 0.0360, 0.0355
    ]),

    "6 (steeper from year 2)": np.array([
        0.0400, 0.0435, 0.0470, 0.0505, 0.0540,
        0.0575, 0.0610, 0.0645, 0.0680, 0.0715
    ])
}


# ============================================================
# 3. BOOTSTRAP DISCOUNT FACTORS
# ============================================================

def bootstrap_discount_factors(swap_curve):
    """
    Convert the par swap curve into discount factors.

    Year 1: the 1Y swap rate is the 1Y spot rate, so
            DF(1) = 1 / (1 + s1)

    Years 2-10: standard annual par-swap bootstrapping. Each DF is
            solved from the par condition

                s_n * sum(DF_1 .. DF_n) + DF_n = 1

            which rearranges to

                DF_n = (1 - s_n * sum(DF_1 .. DF_n-1)) / (1 + s_n)

    Both steps use the same compounding convention, so the curve is
    internally consistent and every par instrument reprices to 100.
    """

    n = len(swap_curve)

    discount_factors = np.zeros(n)

    # Year 1 - discrete (exponential/compound) discounting
    discount_factors[0] = 1.0 / (1.0 + swap_curve[0])

    # Years 2-10
    for i in range(1, n):

        swap_rate = swap_curve[i]

        previous_dfs = np.sum(
            discount_factors[:i]
        )

        discount_factors[i] = (
            1.0 - swap_rate * previous_dfs
        ) / (1.0 + swap_rate)

    return discount_factors


# ============================================================
# 4. IMPLIED 1-YEAR FORWARD RATES
# ============================================================

def calculate_forward_rates(discount_factors):
    """
    1Y forward rate for each period:

        Year 1: 0Y -> 1Y  (equals the 1Y spot rate)
        Year 2: 1Y -> 2Y
        Year 3: 2Y -> 3Y  etc.

        f_i = DF(i-1) / DF(i) - 1
    """

    n = len(discount_factors)

    forward_rates = np.zeros(n)

    df_previous = 1.0

    for i in range(n):

        df_current = discount_factors[i]

        forward_rates[i] = (
            df_previous / df_current
        ) - 1.0

        df_previous = df_current

    return forward_rates


# ============================================================
# 5. VALUE THE FIXED SIDE
# ============================================================

def pv_fixed_bond(
    fixed_rate,
    maturity,
    discount_factors,
    notional=100
):
    """
    PV of the fixed side expressed as a bond: annual fixed coupons
    plus a notional repayment at maturity.

    The notional repayment is NOT a swap cash flow. It is added here
    and again on the floating side, where the two cancel in the NPV.
    Decomposing the swap into two bonds is the standard textbook view
    and makes the fixed side directly comparable to a 100 par bond.
    """

    dfs = discount_factors[:maturity]

    fixed_coupon = (
        notional * fixed_rate
    )

    pv_coupons = (
        fixed_coupon * np.sum(dfs)
    )

    pv_notional = (
        notional * dfs[-1]
    )

    return pv_coupons + pv_notional


# ============================================================
# 6. VALUE THE FLOATING SIDE
# ============================================================

def pv_floating_bond(
    maturity,
    discount_factors,
    forward_rates,
    notional=100
):
    """
    PV of the floating side: every floating coupon is projected off
    the implied 1Y forward rate for that period and discounted, plus
    a notional repayment at maturity.

    Note that in a single curve framework this is an identity:

        N * f_i * DF_i = N * (DF_i-1 - DF_i)

    so the coupons telescope to N * (1 - DF_n) and, adding the
    notional N * DF_n, the floating side is worth exactly N = 100
    on every curve. The explicit calculation is kept because the
    cash flow detail is useful for the presentation, but the result
    is par by construction.
    """

    dfs = discount_factors[:maturity]

    forwards = forward_rates[:maturity]

    floating_coupons = (
        notional * forwards
    )

    pv_coupons = np.sum(
        floating_coupons * dfs
    )

    pv_notional = (
        notional * dfs[-1]
    )

    return pv_coupons + pv_notional


# ============================================================
# 7. RECEIVER SWAP VALUATION
# ============================================================

def receiver_swap_npv(
    fixed_rate,
    maturity,
    swap_curve,
    notional=100
):
    """
    Receiver swap:

        RECEIVE FIXED
        PAY FLOATING

        NPV = PV(fixed) - PV(floating)

    Because the floating side is always par, this reduces to

        NPV = PV(fixed bond at K) - 100
    """

    dfs = bootstrap_discount_factors(
        swap_curve
    )

    forwards = calculate_forward_rates(
        dfs
    )

    pv_fixed = pv_fixed_bond(
        fixed_rate,
        maturity,
        dfs,
        notional
    )

    pv_float = pv_floating_bond(
        maturity,
        dfs,
        forwards,
        notional
    )

    # Consistency check: the floating side must come out at par
    assert abs(pv_float - notional) < 1e-9, (
        "Floating leg is not par - the curve is inconsistent."
    )

    npv = pv_fixed - pv_float

    return npv, pv_fixed, pv_float


# ============================================================
# 8. BASE CURVE: DISCOUNT FACTORS AND FORWARD RATES
# ============================================================

base_dfs = bootstrap_discount_factors(
    base_curve
)

base_forwards = calculate_forward_rates(
    base_dfs
)

curve_table = pd.DataFrame({
    "Year": np.arange(1, 11),
    "Swap Rate": base_curve,
    "Discount Factor": base_dfs,
    "1Y Forward Rate": base_forwards
})

print("\nBASE CURVE")
print("=" * 70)

print(
    curve_table.to_string(
        index=False,
        formatters={
            "Swap Rate": "{:.4%}".format,
            "Discount Factor": "{:.6f}".format,
            "1Y Forward Rate": "{:.4%}".format
        }
    )
)


# ============================================================
# 9. BASE VALUATION OF 5Y AND 10Y RECEIVER SWAPS
# ============================================================

npv_5_base, fixed_5_base, float_5_base = receiver_swap_npv(
    fixed_rate=K_5Y,
    maturity=5,
    swap_curve=base_curve,
    notional=NOTIONAL
)

npv_10_base, fixed_10_base, float_10_base = receiver_swap_npv(
    fixed_rate=K_10Y,
    maturity=10,
    swap_curve=base_curve,
    notional=NOTIONAL
)

print("\n\nBASE SWAP VALUATION")
print("=" * 70)

print("\n5-YEAR RECEIVER SWAP")
print(f"Fixed rate:        {K_5Y:.2%}")
print(f"PV fixed bond:     {fixed_5_base:.6f}")
print(f"PV floating bond:  {float_5_base:.6f}")
print(f"Receiver NPV:      {npv_5_base:.6f}")

print("\n10-YEAR RECEIVER SWAP")
print(f"Fixed rate:        {K_10Y:.2%}")
print(f"PV fixed bond:     {fixed_10_base:.6f}")
print(f"PV floating bond:  {float_10_base:.6f}")
print(f"Receiver NPV:      {npv_10_base:.6f}")

print(
    "\nBoth swaps are struck at the par rate of their own maturity,"
    "\nso the NPV at inception is zero. This is the first check that"
    "\nthe bootstrapped curve is arbitrage free."
)


# ============================================================
# 10. SCENARIO ANALYSIS
# ============================================================

results = []

for scenario_name, shocked_curve in scenarios.items():

    npv_5, fixed_5, float_5 = receiver_swap_npv(
        fixed_rate=K_5Y,
        maturity=5,
        swap_curve=shocked_curve,
        notional=NOTIONAL
    )

    delta_npv_5 = (
        npv_5 - npv_5_base
    )

    npv_10, fixed_10, float_10 = receiver_swap_npv(
        fixed_rate=K_10Y,
        maturity=10,
        swap_curve=shocked_curve,
        notional=NOTIONAL
    )

    delta_npv_10 = (
        npv_10 - npv_10_base
    )

    results.append({
        "Scenario": scenario_name,

        "5Y PV Fixed": fixed_5,
        "5Y PV Float": float_5,
        "5Y NPV": npv_5,
        "5Y NPV Change": delta_npv_5,

        "10Y PV Fixed": fixed_10,
        "10Y PV Float": float_10,
        "10Y NPV": npv_10,
        "10Y NPV Change": delta_npv_10
    })


# ============================================================
# 11. FULL RESULTS
# ============================================================

results_df = pd.DataFrame(results)

print("\n\nFULL SCENARIO VALUATION")
print("=" * 70)

print(
    results_df.round(4).to_string(
        index=False
    )
)


# ============================================================
# 12. FINAL TABLE FOR THE CASE SHEET
# ============================================================

final_table = results_df[
    [
        "Scenario",
        "5Y NPV Change",
        "10Y NPV Change"
    ]
].copy()

final_table.columns = [
    "Scenario",
    "5 Years",
    "10 Years"
]

print("\n\nNPV CHANGES, RECEIVER SWAP, 100 BASE")
print("=" * 70)

print(
    final_table.round(4).to_string(
        index=False
    )
)


# ============================================================
# 13. CASH FLOW DETAIL FOR THE 5Y SWAP (BASE CURVE)
# ============================================================

cashflow_table = pd.DataFrame({
    "Year": np.arange(1, 6),
    "Discount Factor": base_dfs[:5],
    "Fixed Coupon": NOTIONAL * K_5Y * np.ones(5),
    "1Y Forward Rate": base_forwards[:5],
    "Floating Coupon": NOTIONAL * base_forwards[:5],
    "Net Cash Flow":
        NOTIONAL * (K_5Y - base_forwards[:5]),
    "PV Net Cash Flow":
        NOTIONAL * (K_5Y - base_forwards[:5]) * base_dfs[:5]
})

print("\n\n5Y RECEIVER SWAP - CASH FLOW DETAIL (BASE CURVE)")
print("=" * 70)

print(
    cashflow_table.to_string(
        index=False,
        formatters={
            "Discount Factor": "{:.6f}".format,
            "Fixed Coupon": "{:.4f}".format,
            "1Y Forward Rate": "{:.4%}".format,
            "Floating Coupon": "{:.4f}".format,
            "Net Cash Flow": "{:+.4f}".format,
            "PV Net Cash Flow": "{:+.4f}".format
        }
    )
)

print(
    f"\nSum of PV of net cash flows: "
    f"{cashflow_table['PV Net Cash Flow'].sum():+.6f}"
)
print(
    "The receiver is paid above the forward rate in the early years"
    "\nand below it later. On an upward sloping curve the two exactly"
    "\noffset in present value terms, which is what makes the par swap"
    "\nworth zero at inception."
)