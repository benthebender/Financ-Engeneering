# Case 2 - Module 1: Reverse Floater/Leveraged Floater
## Financial Engineering Study Module

---

## 📊 Overview

Reverse floaters and leveraged floaters are structured notes with coupons that move inversely to or with amplified sensitivity to reference rates. These products offer unique risk-return profiles and require sophisticated analysis.

---

## 🎯 Learning Objectives

By the end of this module, you should be able to:
- Understand reverse and leveraged floater mechanics
- Price these instruments using replication portfolios
- Analyze embedded options and convexity features
- Assess investor suitability and risk factors
- Structure custom floater products

---

## 🔄 Reverse Floater Fundamentals

### Definition
A reverse floater is a floating rate note where the coupon rate moves inversely to the reference interest rate.

### Basic Structure
```
Coupon Rate = K - L × Reference Rate
```
Where:
- K = Strike rate (maximum coupon)
- L = Leverage factor (typically 1.0 for simple reverse floater)
- Reference Rate = Market rate (e.g., 3M Euribor)

### Floor Protection
```
Coupon Rate = Max(0, K - L × Reference Rate)
```

### Example: Simple Reverse Floater
**Terms**:
- Notional: €10 million
- Strike Rate (K): 8.0%
- Leverage (L): 1.0
- Reference: 3M Euribor
- Current Euribor: 3.5%

**Current Coupon**:
```
Coupon = Max(0, 8.0% - 1.0 × 3.5%) = 4.5%
```

---

## ⚡ Leveraged Floater Mechanics

### Definition
A leveraged floater has coupons that move with amplified sensitivity to the reference rate.

### Structure
```
Coupon Rate = Spread + L × Reference Rate
```
Where L > 1 (leverage factor > 1)

### Example: 2x Leveraged Floater
**Terms**:
- Notional: €5 million
- Spread: 1.0%
- Leverage: 2.0
- Reference: 6M Euribor
- Current Euribor: 2.5%

**Current Coupon**:
```
Coupon = 1.0% + 2.0 × 2.5% = 6.0%
```

**Rate Sensitivity**:
- 100bp Euribor increase → 200bp coupon increase
- 100bp Euribor decrease → 200bp coupon decrease

---

## 💰 Valuation Methodologies

### 1. Replication Portfolio Approach

#### Reverse Floater Replication
**Components**:
- Long fixed-rate bond (paying K)
- Short floating-rate note (paying reference rate)

```
Reverse Floater = Fixed Rate Bond - Floating Rate Note
```

#### Example Valuation
**Given**:
- 5Y reverse floater: 7% - Euribor
- 5Y fixed bond yielding 7%: Price = 100
- 5Y FRN at Euribor: Price = 100

**Reverse Floater Price**:
```
Price = 100 - 100 = 0 (if rates unchanged)
```

### 2. Present Value of Cash Flows

#### Forward Rate Approach
```
PV = Σ [Max(0, K - L × f_i) × DF_i]
```
Where:
- f_i = Forward rate for period i
- DF_i = Discount factor for period i

#### Monte Carlo Simulation
1. Generate interest rate paths
2. Calculate coupons for each path
3. Discount cash flows
4. Average across simulations

### 3. Option-Adjusted Approach

#### Embedded Floor Option
```
Reverse Floater = Synthetic Bond + Long Floor Option
```

#### Floor Value
```
Floor Value = Σ Max(0, K - L × f_i) × DF_i
```

---

## 📊 Risk Analysis

### Interest Rate Sensitivity

#### Duration Calculation
For reverse floater:
```
Duration = Duration_fixed + Duration_floating × L
```

#### Effective Duration
```
Effective Duration = (P₋ - P₊) / (2 × P₀ × Δy)
```

#### Example: Duration Analysis
**5Y Reverse Floater** (8% - Euribor):
- Fixed bond duration: 4.2 years
- FRN duration: 0.25 years
- **Reverse floater duration**: 4.2 + 0.25 = 4.45 years

### Convexity Features

#### Positive Convexity from Floor
As rates rise and approach the strike level, duration decreases due to floor protection.

#### Convexity Calculation
```
Convexity = (P₊ + P₋ - 2P₀) / (P₀ × (Δy)²)
```

### Price Sensitivity Analysis

| Rate Environment | Reverse Floater Performance |
|------------------|----------------------------|
| **Falling Rates** | Positive (rising coupons) |
| **Rising Rates** | Negative (falling coupons) |
| **Rate at Strike** | Protected by floor |
| **High Volatility** | Benefits from convexity |

---

## 🎲 Leverage and Multiplier Effects

### High Leverage Structures

#### 3x Reverse Floater
```
Coupon = Max(0, 15% - 3.0 × Euribor)
```

**Characteristics**:
- **High sensitivity**: 100bp rate change = 300bp coupon change
- **Greater convexity**: Floor protection more valuable
- **Higher risk**: Greater price volatility

#### Super Floater (Leverage > 1)
```
Coupon = 2.0 × Euribor + 50bp
```

**Risk Profile**:
- **Amplified rate exposure**: 2x sensitivity to rate changes
- **No floor protection**: Unlimited downside
- **Credit risk**: Issuer must pay enhanced coupons

### Cap and Floor Combinations

#### Collared Reverse Floater
```
Coupon = Min(Cap, Max(Floor, K - L × Reference Rate))
```

**Example**:
- Cap: 6.0%
- Floor: 1.0%
- Strike: 8.0%
- Leverage: 1.5

```
Coupon = Min(6.0%, Max(1.0%, 8.0% - 1.5 × Euribor))
```

---

## 🏗️ Structuring Considerations

### Investor Profile

#### Reverse Floater Buyers
- **Rate view**: Expect declining rates
- **Risk tolerance**: Moderate to high
- **Yield enhancement**: Seeking higher income
- **Hedging needs**: Liability-driven investors

#### Leveraged Floater Buyers
- **Rate view**: Expect rising rates
- **Risk appetite**: High (leverage amplifies risk)
- **Speculation**: Directional rate bets
- **Duration management**: Extending rate sensitivity

### Issuer Motivation

#### Cost of Funding
- **Arbitrage opportunity**: Issue reverse floater below fair value
- **Hedging**: Natural hedge for issuer's floating obligations
- **Market access**: Tap specific investor segments

#### Example: Bank Issuer Strategy
**Bank Position**:
- Assets: Fixed rate mortgages
- Liabilities: Floating rate deposits

**Solution**: Issue reverse floaters
- **Natural hedge**: Bank pays less when rates rise
- **Cost effective**: Lower funding cost than traditional fixed rate debt

---

## 📈 Market Examples and Case Studies

### Case Study 1: Municipal Reverse Floater

#### Structure
**Issuer**: City of Frankfurt
**Security**: 10-year reverse floater
**Coupon**: 9.0% - 1.2 × 6M Euribor
**Floor**: 0.5%
**Notional**: €50 million

#### Analysis at Different Rate Levels

| 6M Euribor | Coupon Rate | Annual Payment |
|-------------|-------------|----------------|
| 1.0% | 7.8% | €3.9M |
| 3.0% | 5.4% | €2.7M |
| 5.0% | 3.0% | €1.5M |
| 7.0% | 0.6% | €0.3M |
| 8.0% | 0.5% (floor) | €0.25M |

#### Investor Analysis
**Break-even**: Euribor at 7.5% (coupon = 0%)
**Maximum loss**: If rates stay very high
**Maximum gain**: If rates fall to zero (coupon = 9.0%)

### Case Study 2: Corporate Leveraged Floater

#### Structure
**Issuer**: Technology Corporation
**Security**: 5-year 2x leveraged floater
**Coupon**: 1.5% + 2.0 × 3M Euribor
**Cap**: 12.0%
**Notional**: €25 million

#### Risk Scenario Analysis

| 3M Euribor | Coupon Rate | Price Impact |
|-------------|-------------|--------------|
| 0.5% | 2.5% | Base case |
| 2.0% | 5.5% | +200bp rate = +600bp coupon |
| 4.0% | 9.5% | +400bp rate = +700bp coupon |
| 5.25% | 12.0% (cap) | Cap activated |

---

## 🔧 Hedging and Risk Management

### Issuer Hedging Strategies

#### Reverse Floater Hedge
**Issue**: Reverse floater paying 8% - Euribor
**Hedge**: Interest rate swap
- Pay: 8% fixed
- Receive: Euribor
- **Net result**: Floating rate funding at market levels

#### Leveraged Floater Hedge
**Issue**: 2x leveraged floater paying 1% + 2×Euribor
**Hedge**: Ratio swap
- Pay: 1% + 2×Euribor  
- Receive: Fixed rate
- **Alternative**: Use multiple standard swaps

### Investor Hedging

#### Duration Hedging
**Long reverse floater** with duration = 6 years
**Hedge**: Short government bond futures
**Ratio**: Duration-weighted hedge ratio

#### Convexity Hedging
**Challenge**: Reverse floater's positive convexity
**Solution**: Combine with negative convexity instruments (e.g., callable bonds)

---

## 🎯 Valuation Models

### Binomial Tree Model

#### Interest Rate Tree
```
             4.0%
           /
    3.0% <
           \
             2.0%
```

#### Backward Induction
1. Calculate terminal values
2. Work backwards applying coupon formula
3. Discount at each node

### Black-Karasinski Model
```
d ln(r) = [θ(t) - α ln(r)]dt + σ dW
```

#### Calibration to Market
- Match current yield curve
- Fit to cap/floor volatilities
- Ensure no-arbitrage conditions

---

## 💡 Practical Applications

### Portfolio Management

#### Yield Enhancement
- **Strategy**: Replace fixed rate bonds with reverse floaters
- **Benefit**: Higher income if rates decline
- **Risk**: Underperformance if rates rise

#### Duration Management
- **Long duration position**: Add reverse floaters (positive duration)
- **Short duration position**: Add leveraged floaters (amplified rate sensitivity)

### Asset-Liability Matching

#### Insurance Company Example
**Liabilities**: Fixed annuity payments
**Assets**: Mix including reverse floaters
**Rationale**: Reverse floaters provide higher payments when reinvestment rates are low

---

## ⚡ Key Takeaways

1. **Inverse relationship**: Reverse floaters benefit from declining rates
2. **Leverage amplifies**: Both upside and downside sensitivity
3. **Floor protection**: Provides convexity and downside protection
4. **Replication approach**: Useful for valuation and hedging
5. **Issuer hedging**: Typically requires interest rate swaps
6. **Investor suitability**: Requires strong rate views and risk tolerance

---

## 🎯 Preparation Tips

### Must-Know Formulas
- Basic coupon calculation: Max(0, K - L × Rate)
- Duration: Duration_fixed + Duration_floating × L
- Replication: Fixed Bond - Floating Note

### Key Concepts for Presentation
- Interest rate sensitivity analysis
- Convexity benefits from floor
- Investor vs. issuer perspectives
- Hedging requirements

### Likely Questions
- "How would you hedge this reverse floater position?"
- "What happens to duration as rates approach the strike?"
- "Why would an issuer create a leveraged floater?"
- "How do you value the embedded floor option?"

---

*Module prepared for Financial Engineering Hell Week*  
*Frankfurt School of Finance & Management - Dr. Thomas Heidorn*

