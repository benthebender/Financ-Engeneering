"""
case3_var.py
============

Case 3b - Asset Manager of a Life Insurance.  One-year 99.5% VaR (Historical
Simulation, priority 1) for the combined book:

    * liability-matching Fixed-Income portfolio (16 EUR gov/SSA bonds, EUR 5.0bn
      at t=0), weights from  alm_fixed_income_.py -> results/fixed_income_portfolio.csv
    * return portfolio (14 indices, "Aggressive Diversified" weights) from
      Investment portfolio.py -> portfolio_optimization_final.xlsx
    * every USD sleeve FX-swapped back to EUR (HKD leg of the HK ETF ignored)
    * an equity index-futures short overlay (pricing in futures.py; hedge ratio
      is a config knob, the VIX/threshold rule is set elsewhere)

Funding waterfall
    t=0        +5.0bn cash -> entirely into the FI book
    t=1..10    +0.5bn / year -> return book (deployed at target weights)

Reported
    * ASSET VaR   - P&L of the asset book alone
    * SURPLUS VaR - P&L of (assets - guaranteed pension liability)
    * deterministic stress tests
    * decomposition by sub-book / risk driver

Method (HS): weekly risk-factor history -> 52-week overlapping windows ->
~450 annual scenarios -> reprice the book under each -> 0.5% tail.
Rates repriced by modified duration + convexity; the liability by full
revaluation on the shifted EUR zero curve; index sleeves by their own-currency
total return; the FX hedge by the change in the EUR-USD rate differential.
Parametric (variance-covariance) VaR is reported alongside as a cross-check.
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
DATA = HERE / "Data"
OUT = HERE / "results_var"
FI_PORTFOLIO_CSV = HERE / "results" / "fixed_income_portfolio.csv"
RETURN_XLSX = HERE / "portfolio_optimization_final.xlsx"

EUR_BN = 1e9
Z = 2.3263479  # standard normal 99% one-sided (was 2.5758 for 99.5%)


# ==========================================================================
# CONFIG
# ==========================================================================
@dataclass(frozen=True)
class Config:
    valuation_date: str = "2026-09-02"
    confidence: float = 0.99               # 99% 1-year VaR (insurer risk measure)
    horizon_weeks: int = 52                 # 1-year VaR
    lookback_weeks: int = 520               # ~10y of weekly history
    deployment: str = "full"               # "full" (5bn FI + 5bn return) | "t0"
    fi_book_eur: float = 5.0 * EUR_BN
    contribution_per_year_eur: float = 0.5 * EUR_BN
    contribution_years: int = 10
    return_weight_set: str = "Aggressive_Diversified"
    # futures overlay: None => set by the risk-control rule (derive limit, then
    # HedgeRatio = max(0, 1 - VaR_limit / VaR_unhedged)); a float pins it.
    future_hedge_ratio: "float | None" = None
    equity_beta: float = 1.0               # sleeve beta vs the hedging index
    overlay_buffer: float = 0.10           # no-trade band around the limit (+/-10%)
    min_funding_ratio: float = 1.20        # board floor for assets / liability PV
    var_limit_eur: "float | None" = None   # explicit equity 99% 1y VaR limit; else derived
    guaranteed_rate: float = 0.01
    guaranteed_rate: float = 0.01
    pension_share: float = 0.50
    lump_sum_share: float = 0.50
    n_policyholders: int = 100_000
    initial_value_pp: float = 50_000.0
    contribution_pp: float = 5_000.0
    first_benefit_year: int = 15

    # EUR = home currency; everything else is USD-hedged. HK ETF -> USD.
    eur_sleeves: tuple[str, ...] = (
        "DAX Index", "MSCI Europe Index",
        "Bloomberg Pan-European High Yie", "Bloomberg Euro Treasury Bond In",
    )
    equity_sleeves: tuple[str, ...] = (
        "DAX Index", "NASDAQ", "MSCI World Index", "MSCI Europe Index",
        "Russell 2000 Index", "Dow Jones", "MVIS Global Rare Earth",
        "MSCI World Health Care Index", "iShares MSCI Hong Kong ETF",
    )
    hy_sleeves: tuple[str, ...] = (
        "US Corporate High Yield index", "Bloomberg Pan-European High Yie",
    )

    @property
    def return_book_eur(self) -> float:
        if self.deployment == "t0":
            return 0.0
        return self.contribution_per_year_eur * self.contribution_years


# ==========================================================================
# DATA LOADING
# ==========================================================================
_VAL = pd.Timestamp("2026-09-02")
_DATE_LO = pd.Timestamp("1998-01-01")


def _parse_dates(raw: pd.Series) -> pd.Series:
    """Lenient parse of the mixed Bloomberg date column (datetime objects and
    'MM/DD/YYYY' strings). Anything outside a sane window becomes NaT."""
    dt = pd.to_datetime(raw, errors="coerce")
    bad = pd.to_datetime(raw, errors="coerce", dayfirst=True)
    dt = dt.where((dt >= _DATE_LO) & (dt <= _VAL + pd.Timedelta(days=7)))
    dt = dt.fillna(bad.where((bad >= _DATE_LO) & (bad <= _VAL + pd.Timedelta(days=7))))
    return dt


def load_swap_history(path: Path, tenor_regex: str, raw_divisor: float = 1e7) -> pd.DataFrame:
    """History of par swap rates, columns = tenor in years, decimal.  Parses the
    repeating [weekday, date, rate, spacer] block layout; returned on its own
    (irregular) date index - the scenario builder reindexes it to the weekly
    grid."""
    sheet = pd.read_excel(path, header=None, engine="openpyxl")
    rex = re.compile(tenor_regex, re.IGNORECASE)

    series = {}
    for col in range(sheet.shape[1]):
        m = rex.search(str(sheet.iat[0, col]))
        if not m:
            continue
        tenor = int(m.group(1))
        rate = pd.to_numeric(sheet.iloc[1:, col], errors="coerce") / raw_divisor
        dates = _parse_dates(sheet.iloc[1:, col - 1])
        s = pd.Series(rate.to_numpy(), index=dates).dropna()
        s = s[s.index.notna()]
        s = s[(s > 0.0) & (s < 0.15)]
        s = s[~s.index.duplicated(keep="last")].sort_index()
        series[tenor] = s

    df = pd.DataFrame(series).sort_index(axis=1)
    df = df[df.index.notna()]
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load_eurusd_history(path: Path, raw_divisor: float = 1e4) -> pd.Series:
    sheet = pd.read_excel(path, header=None, engine="openpyxl")
    quote = pd.to_numeric(sheet.iloc[:, 2], errors="coerce") / raw_divisor
    dates = _parse_dates(sheet.iloc[:, 1])
    s = pd.Series(quote.to_numpy(), index=dates).dropna()
    s = s[s.index.notna()]
    s = s[(s > 0.5) & (s < 2.0)]
    return s[~s.index.duplicated(keep="last")].sort_index().rename("EURUSD")


def load_index_history() -> pd.DataFrame:
    w = pd.read_excel(RETURN_XLSX, sheet_name="Weekly Prices", engine="openpyxl")
    w = w.rename(columns={w.columns[0]: "Date"}).set_index("Date")
    w.index = pd.to_datetime(w.index)
    return w.sort_index().dropna(how="all")


def load_return_weights(cfg: Config) -> pd.Series:
    pw = pd.read_excel(RETURN_XLSX, sheet_name="Portfolio Weights", engine="openpyxl")
    pw = pw.set_index("Asset")[cfg.return_weight_set] / 100.0
    return pw


def load_fi_portfolio() -> pd.DataFrame:
    d = pd.read_csv(FI_PORTFOLIO_CSV)
    d = d[d["eur_allocation"] > 1.0].reset_index(drop=True)  # drop the ~0 lines
    return d


# ==========================================================================
# CURVE
# ==========================================================================
def bootstrap_zero_curve(par_rates: pd.Series) -> "tuple[np.ndarray, np.ndarray]":
    """Annual-pay par swap bootstrap -> (tenors 1..N, zero rates cont. comp.)."""
    tenors = par_rates.index.to_numpy(dtype=float)
    rates = par_rates.to_numpy(dtype=float)
    grid = np.arange(1, int(tenors.max()) + 1, dtype=float)
    par = np.interp(grid, tenors, rates)
    dfs, cum = [], 0.0
    for r in par:
        df = (1.0 - r * cum) / (1.0 + r)
        dfs.append(df)
        cum += df
    dfs = np.asarray(dfs)
    zero = -np.log(dfs) / grid
    return grid, zero


def zero_from_grid(grid: np.ndarray, zero: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    z = np.interp(np.clip(t, grid[0], grid[-1]), grid, zero)
    # flat-forward beyond the last node
    slope = (zero[-1] * grid[-1] - zero[-2] * grid[-2]) / (grid[-1] - grid[-2])
    z = np.where(t > grid[-1], (zero[-1] * grid[-1] + slope * (t - grid[-1])) / t, z)
    return z


def discount(grid: np.ndarray, zero: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    return np.exp(-zero_from_grid(grid, zero, t) * t)


# ==========================================================================
# LIABILITY
# ==========================================================================
def guaranteed_accumulated_value(cfg: Config) -> float:
    g = cfg.guaranteed_rate
    n = cfg.n_policyholders
    init = cfg.initial_value_pp * (1.0 + g) ** cfg.first_benefit_year
    contrib = sum(
        cfg.contribution_pp * (1.0 + g) ** (cfg.first_benefit_year - t)
        for t in range(1, cfg.contribution_years + 1)
    )
    return n * (init + contrib)


def liability_cashflows(cfg: Config) -> pd.Series:
    """Guaranteed benefit CF by calendar year from now: 50% lump sum at year 15,
    50% mortality-weighted pension from the pension workbook (years 16..50)."""
    acc = guaranteed_accumulated_value(cfg)
    cf = {cfg.first_benefit_year: cfg.lump_sum_share * acc}

    pen = pd.read_excel(DATA / "pension_liability_results.xlsx", sheet_name="Sheet1")
    pen.columns = [str(c).strip() for c in pen.columns]
    for _, row in pen.iterrows():
        yr = cfg.first_benefit_year + int(row["Year"])
        amt = cfg.pension_share * float(row["Expected_Annual_Pension_Cashflow"])
        cf[yr] = cf.get(yr, 0.0) + amt
    s = pd.Series(cf).sort_index()
    s.index.name = "year"
    return s


# ==========================================================================
# PORTFOLIO
# ==========================================================================
@dataclass
class Book:
    cfg: Config
    fi: pd.DataFrame                    # bond lines with eur MV
    sleeves: pd.DataFrame              # index sleeves with eur MV, currency, kind
    liability_cf: pd.Series
    base_grid: np.ndarray
    base_zero: np.ndarray
    base_usd_1y: float
    base_eur_1y: float

    @property
    def liability_pv(self) -> float:
        yrs = self.liability_cf.index.to_numpy(dtype=float)
        return float(np.sum(self.liability_cf.to_numpy()
                            * discount(self.base_grid, self.base_zero, yrs)))

    @property
    def asset_mv(self) -> float:
        return float(self.fi["eur_allocation"].sum() + self.sleeves["mv_eur"].sum())


def _latest_row(hist: pd.DataFrame) -> pd.Series:
    return hist.loc[:_VAL].ffill().iloc[-1].dropna()


def build_book(cfg: Config) -> Book:
    eur_hist = load_swap_history(DATA / "EUR SWAP CURVES 1-30yr.xlsx", r"(\d+)\s*yr")
    usd_hist = load_swap_history(DATA / "USD SWAP CURVE 1-30yr.xlsx", r"USOSFR(\d+)")

    base_par = _latest_row(eur_hist)
    grid, zero = bootstrap_zero_curve(base_par)

    fi = load_fi_portfolio()
    if cfg.deployment == "t0":
        pass  # FI already at 5bn
    fi = fi.copy()

    weights = load_return_weights(cfg)
    idx_hist = load_index_history()
    rb = cfg.return_book_eur
    rows = []
    for name, w in weights.items():
        if name not in idx_hist.columns:
            continue
        ccy = "EUR" if name in cfg.eur_sleeves else "USD"
        kind = ("HY" if name in cfg.hy_sleeves
                else "EQUITY" if name in cfg.equity_sleeves
                else "RATES_CREDIT")
        rows.append({"sleeve": name, "weight": float(w), "mv_eur": float(w) * rb,
                     "currency": ccy, "kind": kind})
    sleeves = pd.DataFrame(rows)

    return Book(
        cfg=cfg, fi=fi, sleeves=sleeves,
        liability_cf=liability_cashflows(cfg),
        base_grid=grid, base_zero=zero,
        base_usd_1y=float(_latest_row(usd_hist).get(1, _latest_row(usd_hist).iloc[0])),
        base_eur_1y=float(base_par.get(1, base_par.iloc[0])),
    )


# ==========================================================================
# RISK-FACTOR PANEL + SCENARIOS
# ==========================================================================
@dataclass
class Scenarios:
    dates: pd.DatetimeIndex
    eur_rate_chg: pd.DataFrame          # annual abs change, columns = tenor
    usd_1y_chg: np.ndarray
    eur_1y_chg: np.ndarray
    idx_logret: pd.DataFrame            # annual log return per index
    n: int


def weekly_changes(cfg: Config) -> dict:
    """Aligned weekly factor moves over the lookback window:
    d_eur (abs rate change per tenor), d_usd1 / d_eur1 (1y rate change),
    r_idx (log return per index).  Shared by HS and Monte Carlo."""
    eur_hist = load_swap_history(DATA / "EUR SWAP CURVES 1-30yr.xlsx", r"(\d+)\s*yr")
    usd_hist = load_swap_history(DATA / "USD SWAP CURVE 1-30yr.xlsx", r"USOSFR(\d+)")
    idx_hist = load_index_history()

    master = idx_hist.index[-cfg.lookback_weeks:]
    if len(master) < cfg.horizon_weeks + 30:
        raise RuntimeError(f"only {len(master)} weekly index obs - not enough")

    def onto_master(df: pd.DataFrame) -> pd.DataFrame:
        return (df.reindex(df.index.union(master)).ffill().bfill().reindex(master))

    eur = onto_master(eur_hist)
    usd = onto_master(usd_hist)
    idx = idx_hist.reindex(master).ffill().bfill()

    return {
        "d_eur": eur.diff().iloc[1:],
        "d_usd1": usd.iloc[:, 0].diff().iloc[1:].rename("usd_1y"),
        "d_eur1": eur.iloc[:, 0].diff().iloc[1:].rename("eur_1y"),
        "r_idx": np.log(idx).diff().iloc[1:],
        "eur_tenors": eur.columns.to_numpy(dtype=float),
    }


def build_scenarios(cfg: Config) -> Scenarios:
    wc = weekly_changes(cfg)
    d_eur, d_usd1, d_eur1, r_idx = wc["d_eur"], wc["d_usd1"], wc["d_eur1"], wc["r_idx"]

    h = cfg.horizon_weeks
    ann_eur = d_eur.rolling(h).sum().dropna()
    ann_usd1 = d_usd1.rolling(h).sum().dropna()
    ann_eur1 = d_eur1.rolling(h).sum().dropna()
    ann_idx = r_idx.rolling(h).sum().dropna()

    dates = ann_idx.index.intersection(ann_eur.index)
    return Scenarios(
        dates=dates,
        eur_rate_chg=ann_eur.reindex(dates),
        usd_1y_chg=ann_usd1.reindex(dates).to_numpy(),
        eur_1y_chg=ann_eur1.reindex(dates).to_numpy(),
        idx_logret=ann_idx.reindex(dates),
        n=len(dates),
    )


# ==========================================================================
# REPRICING
# ==========================================================================
def reprice(book: Book, sc: Scenarios, cfg: "Config | None" = None) -> pd.DataFrame:
    """P&L (EUR) of every sub-book under every annual scenario."""
    cfg = cfg or book.cfg
    grid, zero = book.base_grid, book.base_zero
    tenors = sc.eur_rate_chg.columns.to_numpy(dtype=float)
    chg = sc.eur_rate_chg.to_numpy()                       # (n_scen, n_tenor)

    # --- FI bonds: modified duration + convexity at each bond's maturity -----
    ytm = book.fi["years_to_maturity"].to_numpy()
    mdur = book.fi["modified_duration"].to_numpy()
    conv = book.fi.get("convexity", pd.Series(np.zeros(len(book.fi)))).to_numpy()
    mv = book.fi["eur_allocation"].to_numpy()
    dy = np.array([np.interp(ytm, tenors, row) for row in chg])   # (n_scen, n_bond)
    fi_pnl = (mv * (-mdur * dy + 0.5 * conv * dy ** 2)).sum(axis=1)

    # --- index sleeves: own-currency total return + FX-hedge residual -------
    sleeve_pnl_by_kind = {"EQUITY": 0.0, "HY": 0.0, "RATES_CREDIT": 0.0}
    fx_resid = np.zeros(sc.n)
    for _, s in book.sleeves.iterrows():
        r = sc.idx_logret[s["sleeve"]].to_numpy()
        pnl = s["mv_eur"] * (np.exp(r) - 1.0)
        sleeve_pnl_by_kind[s["kind"]] = sleeve_pnl_by_kind[s["kind"]] + pnl
        if s["currency"] == "USD":
            # rolled 1y hedge: lose when (USD-EUR) rate gap widens
            fx_resid += -s["mv_eur"] * 1.0 * (sc.usd_1y_chg - sc.eur_1y_chg)

    # --- futures short overlay (broad equity proxy = MSCI World) -----------
    fut_pnl = np.zeros(sc.n)
    ratio = cfg.future_hedge_ratio or 0.0
    if ratio > 0 and "MSCI World Index" in sc.idx_logret.columns:
        eq_mv = book.sleeves.loc[book.sleeves["kind"] == "EQUITY", "mv_eur"].sum()
        short_notional = ratio * cfg.equity_beta * eq_mv
        rw = sc.idx_logret["MSCI World Index"].to_numpy()
        fut_pnl = -short_notional * (np.exp(rw) - 1.0)

    # --- liability full revaluation on the shifted EUR zero curve ----------
    yrs = book.liability_cf.index.to_numpy(dtype=float)
    cfv = book.liability_cf.to_numpy()
    pv0 = float(np.sum(cfv * discount(grid, zero, yrs)))
    liab_pnl = np.empty(sc.n)
    for k in range(sc.n):
        dzero = np.interp(np.clip(grid, tenors[0], tenors[-1]), tenors, chg[k])
        pv = float(np.sum(cfv * discount(grid, zero + dzero, yrs)))
        liab_pnl[k] = pv - pv0

    out = pd.DataFrame({
        "date": sc.dates,
        "fi_bonds": fi_pnl,
        "equity": sleeve_pnl_by_kind["EQUITY"],
        "high_yield": sleeve_pnl_by_kind["HY"],
        "rates_credit_idx": sleeve_pnl_by_kind["RATES_CREDIT"],
        "fx_hedge_residual": fx_resid,
        "futures_overlay": fut_pnl,
    })
    out["asset_pnl"] = (out["fi_bonds"] + out["equity"] + out["high_yield"]
                        + out["rates_credit_idx"] + out["fx_hedge_residual"]
                        + out["futures_overlay"])
    out["liability_pnl"] = liab_pnl
    out["surplus_pnl"] = out["asset_pnl"] - out["liability_pnl"]
    return out


# ==========================================================================
# VaR
# ==========================================================================
def var_stats(pnl: np.ndarray, conf: float) -> dict:
    pnl = np.asarray(pnl, dtype=float)
    q = np.percentile(pnl, (1.0 - conf) * 100.0)
    tail = pnl[pnl <= q]
    return {
        "hist_var": -q,
        "hist_es": -tail.mean() if tail.size else -q,
        "param_var": -(pnl.mean() - Z * pnl.std(ddof=1)),
        "mean_pnl": pnl.mean(),
        "vol_pnl": pnl.std(ddof=1),
        "worst": -pnl.min(),
        "n_scen": pnl.size,
    }


# ==========================================================================
# RISK-CONTROL OVERLAY  (99% 1-year equity VaR vs an economic limit)
# ==========================================================================
def derive_var_limit(book: Book, cfg: Config, non_equity_surplus_var: float) -> dict:
    """Economically-anchored 99% 1-year VaR limit for the equity sleeve.

    Anchor: the board sets a floor on the funding ratio (assets / liability PV)
    that must hold in a 1-in-100 year.  The maximum tolerable total 1y asset
    loss is then

        loss_budget = assets - min_funding_ratio * liability_PV

    The non-equity surplus risk (rate mismatch, FX, HY, longevity buffer) is
    subtracted; what remains is the equity sleeve's 99% 1y VaR limit.  Also
    reported: the limit as a share of equity MV and of economic surplus, plus a
    surplus-at-risk cross-check (limit <= 1/3 of economic surplus).
    """
    assets = book.asset_mv
    liab = book.liability_pv
    surplus = assets - liab
    eq_mv = book.sleeves.loc[book.sleeves["kind"] == "EQUITY", "mv_eur"].sum()

    loss_budget = assets - cfg.min_funding_ratio * liab
    equity_limit = max(0.0, loss_budget - non_equity_surplus_var)
    sar_cap = surplus / 3.0                    # keep >=2/3 of the buffer in a 1-in-100 yr

    binding = "funding-ratio floor" if equity_limit <= sar_cap else "surplus-at-risk cap"
    limit = min(equity_limit, sar_cap)

    return {
        "assets": assets, "liability_pv": liab, "economic_surplus": surplus,
        "equity_mv": eq_mv, "min_funding_ratio": cfg.min_funding_ratio,
        "loss_budget_at_floor": loss_budget,
        "non_equity_surplus_var": non_equity_surplus_var,
        "equity_limit_from_floor": equity_limit,
        "surplus_at_risk_cap": sar_cap,
        "binding_constraint": binding,
        "var_limit_eur": limit,
        "limit_pct_of_equity_mv": limit / eq_mv if eq_mv else float("nan"),
        "limit_pct_of_surplus": limit / surplus if surplus else float("nan"),
    }


def target_hedge_ratio(var_unhedged: float, var_limit: float) -> float:
    """Rule: HedgeRatio = max(0, 1 - VaR_limit / VaR_unhedged), clamped to [0, 1].
    Never a net short (ratio <= 1)."""
    if var_unhedged <= 0:
        return 0.0
    return float(min(1.0, max(0.0, 1.0 - var_limit / var_unhedged)))


def vix_gated_band(base_buffer: float, vix: "float | None",
                   calm: float = 20.0, spike: float = 40.0,
                   min_frac: float = 0.2) -> float:
    """No-trade band width as a function of VIX (rule 9 + VIX gating).

    Wide band (few trades) in a calm regime; the band shrinks linearly from
    `calm` to `spike` and floors at `min_frac * base_buffer` once VIX >= spike,
    so the overlay reacts fast when volatility (and thus the measured 99% equity
    VaR) jumps. VIX is the Heston VIX_t of the current regime (or the last
    observed close once real VIX data is wired in)."""
    if vix is None:
        return base_buffer
    frac = np.clip(1.0 - (vix - calm) / (spike - calm), min_frac, 1.0)
    return base_buffer * float(frac)


def applied_hedge_ratio(var_unhedged: float, var_limit: float,
                        current_ratio: float, buffer: float,
                        vix: "float | None" = None) -> tuple[float, str]:
    """No-trade band (rule 9): only move the hedge if VaR is outside +/- `buffer`
    of the limit; otherwise hold the current ratio. If `vix` is given the band
    is tightened when volatility spikes (`vix_gated_band`)."""
    band = vix_gated_band(buffer, vix)
    tgt = target_hedge_ratio(var_unhedged, var_limit)
    lo, hi = var_limit * (1 - band), var_limit * (1 + band)
    if lo <= var_unhedged <= hi:
        return current_ratio, (f"within +/-{band:.0%} band"
                               + (f" (VIX {vix:.0f})" if vix else "")
                               + f" - hold {current_ratio:.0%}")
    return tgt, (f"outside +/-{band:.0%} band"
                 + (f" (VIX {vix:.0f})" if vix else "") + f" - move to {tgt:.0%}")


def stress_tests(book: Book) -> pd.DataFrame:
    """Deterministic named shocks, repriced on the book."""
    grid, zero = book.base_grid, book.base_zero
    yrs = book.liability_cf.index.to_numpy(dtype=float)
    cfv = book.liability_cf.to_numpy()
    pv0 = float(np.sum(cfv * discount(grid, zero, yrs)))

    ytm = book.fi["years_to_maturity"].to_numpy()
    mdur = book.fi["modified_duration"].to_numpy()
    conv = book.fi.get("convexity", pd.Series(np.zeros(len(book.fi)))).to_numpy()
    mv = book.fi["eur_allocation"].to_numpy()
    eq_mv = book.sleeves.loc[book.sleeves["kind"] == "EQUITY", "mv_eur"].sum()
    hy_mv = book.sleeves.loc[book.sleeves["kind"] == "HY", "mv_eur"].sum()
    rc_mv = book.sleeves.loc[book.sleeves["kind"] == "RATES_CREDIT", "mv_eur"].sum()

    def rate_pnl(dy):
        fi = float((mv * (-mdur * dy + 0.5 * conv * dy ** 2)).sum())
        liab = float(np.sum(cfv * discount(grid, zero + dy, yrs))) - pv0
        return fi, liab

    scen = {
        "EUR rates +100bp parallel": dict(dy=0.01),
        "EUR rates +200bp parallel": dict(dy=0.02),
        "EUR rates -100bp parallel": dict(dy=-0.01),
        "Equity -20%": dict(eq=-0.20),
        "Equity -30%": dict(eq=-0.30),
        "Equity -40%": dict(eq=-0.40),
        "HY spread +300bp (~-12%)": dict(hy=-0.12),
        "2022 replay: rates +250bp, equity -20%": dict(dy=0.025, eq=-0.20),
        "2008 replay: equity -45%, rates -150bp, HY -25%": dict(dy=-0.015, eq=-0.45, hy=-0.25),
        "Longevity +1yr life exp (~+4% liability)": dict(liab_mult=0.04),
    }
    rows = []
    for name, s in scen.items():
        fi_pnl, liab_pnl = rate_pnl(s.get("dy", 0.0))
        eq_pnl = eq_mv * s.get("eq", 0.0)
        hy_pnl = hy_mv * s.get("hy", 0.0)
        rc_pnl = rc_mv * (0.5 * s.get("eq", 0.0) + 0.3 * s.get("hy", 0.0))
        liab_pnl += s.get("liab_mult", 0.0) * pv0
        asset = fi_pnl + eq_pnl + hy_pnl + rc_pnl
        rows.append({
            "scenario": name, "fi_bonds": fi_pnl, "equity": eq_pnl,
            "high_yield": hy_pnl, "rates_credit_idx": rc_pnl,
            "asset_pnl": asset, "liability_pnl": liab_pnl,
            "surplus_pnl": asset - liab_pnl,
        })
    return pd.DataFrame(rows).set_index("scenario")


# ==========================================================================
# REPORT
# ==========================================================================
def _mn(x):
    return f"{x/1e6:,.1f}m"


def run(cfg: Config, tag: str | None = None) -> dict:
    from dataclasses import replace as _replace
    OUT.mkdir(exist_ok=True)
    book = build_book(cfg)
    sc = build_scenarios(cfg)

    # ---- risk-control overlay: size the futures short from the 99% equity VaR ----
    unhedged = reprice(book, sc, _replace(cfg, future_hedge_ratio=0.0))
    eq_var_unhedged = var_stats(unhedged["equity"].to_numpy(), cfg.confidence)["hist_var"]
    non_eq_surplus_var = var_stats(
        (unhedged["surplus_pnl"] - unhedged["equity"]).to_numpy(), cfg.confidence
    )["hist_var"]
    limit_info = derive_var_limit(book, cfg, non_eq_surplus_var)
    var_limit = cfg.var_limit_eur if cfg.var_limit_eur is not None else limit_info["var_limit_eur"]
    overlay_ok = eq_var_unhedged > 1e6 and limit_info["economic_surplus"] > 0

    if not overlay_ok:
        ratio = float(cfg.future_hedge_ratio or 0.0)
        overlay_note = "overlay not applicable (no return book / pre-funding snapshot)"
        var_limit = float("nan")
    elif cfg.future_hedge_ratio is not None:
        ratio = float(cfg.future_hedge_ratio)
        overlay_note = f"hedge ratio pinned at {ratio:.0%} (rule would give " \
                       f"{target_hedge_ratio(eq_var_unhedged, var_limit):.1%})"
    else:
        ratio = target_hedge_ratio(eq_var_unhedged, var_limit)
        _, band = applied_hedge_ratio(eq_var_unhedged, var_limit, ratio, cfg.overlay_buffer)
        overlay_note = (f"rule: max(0, 1 - {var_limit/1e6:,.0f}m / "
                        f"{eq_var_unhedged/1e6:,.0f}m) = {ratio:.1%}   [{band}]")

    cfg = _replace(cfg, future_hedge_ratio=ratio, var_limit_eur=var_limit)
    tag = tag or f"{cfg.deployment}_h{int(round(ratio*100)):02d}"

    pnl = reprice(book, sc, cfg)
    pnl.to_csv(OUT / f"scenario_pnl_{tag}.csv", index=False)

    asset = var_stats(pnl["asset_pnl"].to_numpy(), cfg.confidence)
    surplus = var_stats(pnl["surplus_pnl"].to_numpy(), cfg.confidence)

    # component VaR = each driver's own 99.5% loss (not additive, but indicative)
    comps = ["fi_bonds", "equity", "high_yield", "rates_credit_idx",
             "fx_hedge_residual", "futures_overlay", "liability_pnl"]
    comp_var = {c: var_stats(pnl[c].to_numpy(), cfg.confidence)["hist_var"] for c in comps}
    pd.Series(comp_var, name="hist_var_eur").to_csv(OUT / f"component_var_{tag}.csv")

    stress = stress_tests(book)
    stress.to_csv(OUT / f"stress_tests_{tag}.csv")

    _charts(pnl, asset, surplus, comp_var, stress, cfg, tag)

    lines = []
    L = lines.append
    L(f"# Case 3b - 1-year {cfg.confidence:.1%} VaR  ({cfg.deployment} deployment)\n")
    L(f"Valuation date {cfg.valuation_date}. Historical simulation, "
      f"{sc.n} overlapping 52-week scenarios from ~{cfg.lookback_weeks} weeks "
      f"of factor history.\n")
    L("## Book\n")
    L(f"- Fixed-income (liability-matching): EUR {book.fi['eur_allocation'].sum()/1e9:,.2f}bn, "
      f"{len(book.fi)} bonds")
    L(f"- Return book (14 indices, {cfg.return_weight_set}): EUR "
      f"{book.sleeves['mv_eur'].sum()/1e9:,.2f}bn")
    L(f"- Total assets: EUR {book.asset_mv/1e9:,.2f}bn")
    L(f"- Guaranteed pension liability PV: EUR {book.liability_pv/1e9:,.2f}bn")
    L(f"- Funding ratio (assets / liability PV): {book.asset_mv/book.liability_pv:,.2f}\n")

    li = limit_info
    L("## Risk-control overlay  (99% 1-year equity VaR vs economic limit)\n")
    L(f"- Economic surplus (assets - liability PV): EUR {li['economic_surplus']/1e9:,.2f}bn")
    L(f"- Board funding-ratio floor (1-in-100 yr): {li['min_funding_ratio']:.2f}  "
      f"=> max tolerable 1y asset loss EUR {li['loss_budget_at_floor']/1e9:,.2f}bn")
    L(f"- Less non-equity surplus VaR (rates mismatch + FX + HY + longevity buffer): "
      f"EUR {li['non_equity_surplus_var']/1e6:,.0f}m")
    L(f"- **Equity 99% 1y VaR limit** = EUR {var_limit/1e6:,.0f}m  "
      f"({li['limit_pct_of_equity_mv']:.1%} of equity MV, "
      f"{li['limit_pct_of_surplus']:.1%} of economic surplus; "
      f"binding: {li['binding_constraint']})")
    L(f"- Unhedged equity 99% 1y VaR (HS): EUR {eq_var_unhedged/1e6:,.0f}m")
    L(f"- {overlay_note}")
    L(f"- Applied futures short: {cfg.future_hedge_ratio:.1%} of equity MV "
      f"(beta {cfg.equity_beta:.2f}); no-trade band +/-{cfg.overlay_buffer:.0%}\n")

    L("## Headline VaR / ES  (1-year, EUR)\n")
    L(f"| | Historical VaR | Historical ES | Parametric VaR | 1y P&L vol | worst scenario |")
    L(f"|---|--:|--:|--:|--:|--:|")
    L(f"| **Asset VaR** | {_mn(asset['hist_var'])} | {_mn(asset['hist_es'])} "
      f"| {_mn(asset['param_var'])} | {_mn(asset['vol_pnl'])} | {_mn(asset['worst'])} |")
    L(f"| **Surplus VaR** | {_mn(surplus['hist_var'])} | {_mn(surplus['hist_es'])} "
      f"| {_mn(surplus['param_var'])} | {_mn(surplus['vol_pnl'])} | {_mn(surplus['worst'])} |")
    L(f"\nAsset VaR as % of assets: {asset['hist_var']/book.asset_mv:.2%}   |   "
      f"Surplus VaR as % of assets: {surplus['hist_var']/book.asset_mv:.2%}   |   "
      f"Surplus VaR as % of liability: {surplus['hist_var']/book.liability_pv:.2%}\n")
    L(f"## Standalone {cfg.confidence:.0%} loss by risk driver  (indicative, not additive)\n")
    L(f"| driver | 1y {cfg.confidence:.0%} loss (EUR) |")
    L("|---|--:|")
    for c, v in sorted(comp_var.items(), key=lambda kv: -kv[1]):
        L(f"| {c} | {_mn(v)} |")
    L("\n## Deterministic stress tests  (EUR P&L)\n")
    L("| scenario | asset P&L | liability P&L | surplus P&L |")
    L("|---|--:|--:|--:|")
    for name, row in stress.iterrows():
        L(f"| {name} | {_mn(row['asset_pnl'])} | {_mn(row['liability_pnl'])} "
          f"| {_mn(row['surplus_pnl'])} |")
    L("\n## Method & assumptions\n")
    L("- HS: weekly EUR/USD swap-curve, EURUSD and 14 index levels; 52-week "
      "overlapping windows; rates as absolute changes, indices/FX as log returns.")
    L("- Bonds & liability: EUR curve only. Bonds repriced by modified duration "
      "+ convexity at each bond's maturity; liability by full revaluation on the "
      "shifted zero curve. Govvie/SSA spread risk is in the stress tests only.")
    L("- Every USD sleeve is FX-swapped to EUR (rolled 1y); spot-FX risk removed, "
      "residual = change in the EUR-USD 1y rate differential. HKD leg ignored.")
    L("- Return book = 10 x EUR 0.5bn contributions deployed at target weights "
      "(strategic / fully-funded steady state). `deployment=t0` gives the "
      "inception snapshot (return book ~ 0).")
    L(f"- Parametric VaR uses a Normal {cfg.confidence:.0%} (z = {Z:.3f}) on the scenario P&L.")
    L("- Longevity is a stress line, not in the 1y HS distribution.")
    L("- Overlay: unhedged equity 99% 1y VaR (HS) -> HedgeRatio = max(0, "
      "1 - VaR_limit / VaR_unhedged), clamped [0,1]; contracts via "
      "Equity_MV x beta x ratio / (future_price x multiplier) (futures.py). "
      "Buffer = no-trade band to damp turnover; overlay is risk control, not "
      "market timing.")
    (OUT / f"VAR_REPORT_{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))
    print(f"\nwrote {OUT}/ (tag='{tag}'): VAR_REPORT, scenario_pnl, component_var, "
          f"stress_tests, var_charts")
    return {"asset": asset, "surplus": surplus, "book": book,
            "comp_var": comp_var, "stress": stress}


def _charts(pnl, asset, surplus, comp_var, stress, cfg, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C_A, C_S, C_NEG, C_POS, GRID = "#0072B2", "#D55E00", "#D55E00", "#009E73", "#E6E6E6"
    fig, ax = plt.subplots(2, 2, figsize=(15, 10))

    a = pnl["asset_pnl"].to_numpy() / 1e6
    s = pnl["surplus_pnl"].to_numpy() / 1e6
    ax[0, 0].hist(a, bins=40, color=C_A, alpha=0.55, label="asset P&L")
    ax[0, 0].hist(s, bins=40, color=C_S, alpha=0.55, label="surplus P&L")
    ax[0, 0].axvline(-asset["hist_var"] / 1e6, color=C_A, lw=2, ls="--")
    ax[0, 0].axvline(-surplus["hist_var"] / 1e6, color=C_S, lw=2, ls="--")
    ax[0, 0].set_title(f"1-year P&L distribution ({pnl.shape[0]} scenarios)")
    ax[0, 0].set_xlabel("EUR m"); ax[0, 0].legend(frameon=False)

    cv = pd.Series(comp_var).sort_values() / 1e6
    ax[0, 1].barh(cv.index, cv.values, color=C_A)
    ax[0, 1].set_title("Standalone 1y 99.5% loss by driver (EUR m)")

    st = stress["surplus_pnl"].sort_values() / 1e6
    ax[1, 0].barh(st.index, st.values,
                  color=[C_NEG if v < 0 else C_POS for v in st.values])
    ax[1, 0].axvline(0, color="#333", lw=1)
    ax[1, 0].set_title("Stress tests - surplus P&L (EUR m)")

    cum_a = np.sort(a)
    ax[1, 1].plot(cum_a, np.linspace(0, 1, len(cum_a)), color=C_A, lw=2, label="asset")
    cum_s = np.sort(s)
    ax[1, 1].plot(cum_s, np.linspace(0, 1, len(cum_s)), color=C_S, lw=2, label="surplus")
    ax[1, 1].axhline(1 - cfg.confidence, color="#333", lw=1, ls=":")
    ax[1, 1].set_title("Empirical CDF of 1y P&L"); ax[1, 1].set_xlabel("EUR m")
    ax[1, 1].legend(frameon=False)

    for a_ in ax.flat:
        a_.grid(color=GRID, lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle(f"Case 3b - combined book, 1-year {cfg.confidence:.1%} VaR "
                 f"({cfg.deployment})", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / f"var_charts_{tag}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        h = None if len(sys.argv) <= 2 or sys.argv[2] == "auto" else float(sys.argv[2])
        run(Config(deployment=sys.argv[1], future_hedge_ratio=h))
    else:
        # full suite for the presentation
        run(Config(deployment="full", future_hedge_ratio=0.0), tag="full_unhedged")
        run(Config(deployment="full"), tag="full_overlay")            # rule-based hedge
        run(Config(deployment="t0", future_hedge_ratio=0.0), tag="t0_inception")
