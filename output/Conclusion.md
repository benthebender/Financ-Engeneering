
# Vonovia SE — Interest-Rate Value at Risk

## Executive Summary

This analysis demonstrates how a corporate client can assess
interest-rate risk using Value at Risk (VaR).

The analysis considers approximately **EUR 31.39 billion**
of identified Vonovia debt.

Because the available Bloomberg information does not provide sufficient
instrument-level duration, maturity, coupon and derivative information,
the analysis uses an **illustrative aggregate modified duration of
5.0 years**.

The results are therefore illustrative VaR estimates conditional on this
assumption rather than Vonovia's internally reported VaR.

## Market Data and Calibration

The improved Bloomberg dataset provides separate historical observations
for every annual EUR swap maturity from **1Y through 10Y**.

Each maturity was cleaned independently and aligned by actual date before
the historical rate-change statistics were calculated.

The analysis uses:

- **Confidence level:** 95%
- **Risk horizon:** 10 trading days
- **Monte Carlo simulations:** 100,000
- **Base modified duration assumption:** 5.0 years
- **EUR swap risk factors:** 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y
- **Historical period:** 2015-11-19 to 2026-08-31

Historical rate movements are used to estimate volatility, covariance,
correlation and common yield-curve factors.

## VaR Results — Base Case

| Method | 10-Day 95% VaR | 95% Expected Shortfall |
|---|---:|---:|
| Delta-Normal | EUR 287.64m | EUR 360.71m |
| Monte Carlo | EUR 288.31m | EUR 362.55m |
| PCA + GARCH | EUR 241.48m | EUR 324.79m |

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

Monte Carlo generates **100,000 correlated 10-day EUR
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

The first three factors explain approximately **99.34%**
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
