# Case 1 - Module 3: Interest Rate Risk (Flow View; Cash Flow at Risk)
## Financial Engineering Study Module

---

## 📊 Overview

Cash Flow at Risk (CFaR) focuses on the impact of interest rate changes on future cash flows rather than present values. This is crucial for institutions with ongoing cash flow obligations like banks, insurers, and pension funds.

---

## 🎯 Learning Objectives

By the end of this module, you should be able to:
- Understand the difference between PV-based and flow-based risk measures
- Calculate Cash Flow at Risk for various instruments
- Apply asset-liability management (ALM) principles
- Analyze interest rate risk from an earnings perspective
- Design hedging strategies for cash flow risk

---

## 💰 Cash Flow at Risk (CFaR) Framework

### Definition
CFaR measures the potential adverse impact on future net interest income or cash flows due to interest rate movements over a specific time horizon.

### Key Differences from VaR

| Measure | Focus | Time Horizon | Use Case |
|---------|--------|--------------|----------|
| **VaR** | Present Value | Point-in-time | Trading, market risk |
| **CFaR** | Future Cash Flows | Forward-looking | ALM, business risk |

### Basic CFaR Formula
```
CFaR = Expected Cash Flow - Worst-Case Cash Flow (at confidence level)
```

---

## 📈 Asset-Liability Management (ALM) Context

### Interest Rate Gap Analysis

#### Repricing Gap
```
Gap(t) = Rate-Sensitive Assets(t) - Rate-Sensitive Liabilities(t)
```

#### Cumulative Gap
```
Cumulative Gap(t) = Σ Gap(i) for i = 1 to t
```

#### Gap Risk Exposure
```
ΔNII = Gap × Δr × Time Period
```
Where ΔNII = Change in Net Interest Income

### Duration Gap Analysis
```
Duration Gap = Duration_Assets - (Liabilities/Assets) × Duration_Liabilities
```

#### Equity Duration
```
Duration_Equity = Duration_Assets - (L/A) × Duration_Liabilities
```

---

## 🔢 CFaR Calculation Methodologies

### 1. Repricing Model Approach

#### Step-by-Step Process
1. **Bucket assets and liabilities** by repricing periods
2. **Calculate gap** for each time bucket
3. **Apply rate shocks** to each bucket
4. **Calculate impact** on net interest income

#### Example Calculation
**Bank Balance Sheet** (€ millions):

| Maturity | Assets | Liabilities | Gap |
|----------|--------|-------------|-----|
| 0-3M | 500 | 800 | -300 |
| 3-12M | 400 | 300 | +100 |
| 1-5Y | 600 | 400 | +200 |

**Rate Shock**: +200bp

**Impact on NII** (annual):
```
ΔNII = (-300 × 0.02) + (100 × 0.02) + (200 × 0.02) = €0M
```

### 2. Duration-Based CFaR

#### Net Interest Income Sensitivity
```
ΔNII = -[Duration_Assets × Assets - Duration_Liabilities × Liabilities] × Δr
```

#### Example
**Given**:
- Assets: €1B, Duration = 4.5 years
- Liabilities: €900M, Duration = 2.1 years
- Rate increase: 100bp

**Calculation**:
```
ΔNII = -[(4.5 × 1000) - (2.1 × 900)] × 0.01 = -€26.1M annually
```

### 3. Simulation-Based CFaR

#### Monte Carlo Approach
1. **Generate interest rate scenarios** (1,000+ paths)
2. **Project cash flows** under each scenario
3. **Calculate NII** for each path
4. **Determine percentiles** for CFaR measure

#### Historical Simulation
1. **Apply historical rate changes** to current portfolio
2. **Calculate resulting cash flows**
3. **Rank outcomes** and identify worst-case scenarios

---

## 📊 Earnings-at-Risk (EaR) Analysis

### Definition
EaR measures potential decline in net interest income over a specific period (typically 1 year) due to interest rate movements.

### EaR Calculation
```
EaR_α = Expected NII - NII_α percentile
```

### Key Components

#### Asset Repricing
```
Asset Cash Flow Change = Principal × (New Rate - Old Rate) × Time Factor
```

#### Liability Repricing
```
Liability Cost Change = Principal × (New Rate - Old Rate) × Time Factor
```

#### Net Impact
```
Net EaR Impact = Σ(Asset Changes) - Σ(Liability Changes)
```

---

## 🔄 Dynamic Risk Factors

### Non-Parallel Rate Movements

#### Yield Curve Rotations
- **Bear Steepening**: Long rates rise faster than short rates
- **Bull Flattening**: Short rates fall faster than long rates
- **Parallel Shifts**: All rates move equally

#### Key Rate Impacts
Track sensitivity to specific maturity points:
```
EaR_total = Σ(Key Rate Sensitivity_i × Rate Change_i)
```

### Basis Risk

#### Definition
Risk from imperfect correlation between different rate indices.

#### Examples
- Prime rate vs. SOFR
- Euribor vs. German Bund yields
- Corporate bond spreads vs. government rates

#### Measurement
```
Basis Risk = Position_1 × Δ(Spread_1-2) × Beta_basis
```

---

## 📋 Behavioral Assumptions

### Deposit Modeling

#### Non-Maturity Deposits (NMDs)
- **Core vs. Rate-Sensitive** classification
- **Decay rates** under stress scenarios
- **Effective duration** estimation

#### Price Elasticity
```
Deposit Beta = Δ(Deposit Rate) / Δ(Market Rate)
```

### Prepayment Risk

#### Mortgage Portfolios
```
CPR (Conditional Prepayment Rate) = f(Current Rate, Original Rate, Seasoning)
```

#### Behavioral Duration
```
Effective Duration = Modified Duration × (1 - Prepayment Sensitivity)
```

---

## 🛡️ CFaR Risk Management

### Risk Limits Framework

#### EaR Limits
- **Absolute limits**: Maximum €10M EaR at 95% confidence
- **Relative limits**: EaR ≤ 15% of expected NII
- **Stress limits**: Maximum loss under 300bp shock

#### Duration Limits
```
Asset Duration - Liability Duration ≤ ±2 years
```

### Hedging Strategies

#### Interest Rate Swaps
- **Receive-fixed swaps** to reduce asset sensitivity
- **Pay-fixed swaps** to reduce liability sensitivity

#### Options Strategies
- **Caps and floors** for asymmetric risk management
- **Collars** for cost-effective hedging

#### Forward Rate Agreements (FRAs)
- **Lock in future funding costs**
- **Hedge reinvestment risk**

---

## 📊 Practical ALM Dashboard

### Key Metrics Summary

| Metric | Current | Limit | Status |
|--------|---------|-------|--------|
| 1Y EaR (95%) | €8.2M | €10M | ✅ |
| Duration Gap | +1.8Y | ±2Y | ✅ |
| 3M Rate Gap | -€150M | ±€200M | ✅ |
| CVaR (99%) | €12.5M | €15M | ✅ |

### Scenario Analysis

#### Base Case (+100bp parallel)
- NII Impact: -€15.2M
- Duration contribution: -€18.1M
- Convexity benefit: +€2.9M

#### Stress Scenarios
| Scenario | NII Impact | Recovery Time |
|----------|------------|---------------|
| +300bp Parallel | -€45.6M | 18 months |
| Bear Steepening | -€52.1M | 24 months |
| Recession (-200bp) | +€28.4M | N/A |

---

## 💡 Case Study: Regional Bank ALM

### Bank Profile
- **Assets**: €5B (60% loans, 40% securities)
- **Liabilities**: €4.5B (70% deposits, 30% wholesale)
- **Target NII**: €180M annually

### Current Position Analysis

#### Repricing Profile
| Bucket | Assets | Liabilities | Gap | Cumulative Gap |
|--------|--------|-------------|-----|----------------|
| 0-3M | €1.5B | €3.0B | -€1.5B | -€1.5B |
| 3-12M | €1.0B | €0.8B | +€0.2B | -€1.3B |
| 1-3Y | €1.5B | €0.5B | +€1.0B | -€0.3B |
| 3-10Y | €1.0B | €0.2B | +€0.8B | +€0.5B |

#### Risk Assessment
**100bp Rate Rise Impact**:
```
Year 1 NII Impact = -1.5B × 0.01 × 1.0 = -€15M (-8.3% of target NII)
```

### Hedging Recommendation
1. **Receive-fixed IRS**: €500M notional, 3Y tenor
2. **Interest rate cap**: €200M notional at 4.5% strike
3. **Expected outcome**: Reduce EaR by 60%

---

## 🔍 Advanced Topics

### Economic Value of Equity (EVE)
```
EVE = PV(Assets) - PV(Liabilities)
ΔEVE = -Duration_Gap × Equity × Δr
```

### Option-Adjusted Spread (OAS)
For securities with embedded options:
```
Price = Σ[CF_i / (1 + r_i + OAS)^t_i]
```

### Credit Migration Impact
```
Expected Loss = PD × LGD × EAD
CFaR_credit = Expected CF - Credit-Adjusted CF
```

---

## ⚡ Key Takeaways

1. **CFaR focuses on future earnings** rather than current market values
2. **Gap analysis** provides foundation for flow-based risk measurement
3. **Behavioral assumptions** crucial for accurate modeling
4. **Dynamic hedging** required as portfolio composition changes
5. **Stress testing** essential for extreme scenarios
6. **Integration with PV measures** provides complete risk picture

---

## 🎯 Preparation Tips

### Must-Know Concepts
- Repricing gap calculation
- Duration gap interpretation
- EaR vs. VaR differences
- Basic hedging mechanics

### Presentation Focus
- ALM dashboard format
- Scenario analysis results
- Hedging strategy rationale
- Risk limit monitoring

### Likely Questions
- "How would you hedge negative duration gap?"
- "What drives basis risk in this portfolio?"
- "Why might CFaR increase while VaR decreases?"

---

*Module prepared for Financial Engineering Hell Week*  
*Frankfurt School of Finance & Management - Dr. Thomas Heidorn*

