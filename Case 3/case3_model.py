"""
case3_model.py
==============

Case 3b - Asset Manager of a Life Insurance.  ONE self-contained model:
combines the logic of case3_var.py + montecarlo.py + vix.py + futures.py + fx.py.

Investment / cash-flow structure (unchanged)
    t = 0        + EUR 5.0bn  -> entirely into the Fixed-Income (liability-
                                matching) book: 16 EUR gov/SSA bonds, weights
                                from alm_fixed_income_.py -> results/fixed_income_portfolio.csv
    t = 1..10    + EUR 0.5bn / year -> the Return book: 14 indices at the
                                "Aggressive_Diversified" weights from
                                Investment portfolio.py -> portfolio_optimization_final.xlsx
    every USD sleeve is rolled back to EUR with a 1-year FX swap (HKD leg of the
    HK ETF ignored).
    an equity index-futures SHORT overlay is sized by the risk-control rule.

Guaranteed liability (IAS)
    guaranteed accumulated value at year 15
        = n * [ 50k*(1+g)^15 + sum_{t=1..10} 5k*(1+g)^(15-t) ] ,  g = 1%
    benefit CF from now:  50% lump sum at year 15  +  50% mortality-weighted
    pension (pension_liability_results.xlsx, years 16..50).

Risk measure: 1-year 99% VaR.
    * Historical Simulation (primary) - 52-week overlapping windows
    * Monte-Carlo (Student-t copula, PCA curve, Heston stochastic vol + VIX)
    * Parametric (Normal) cross-check
    Reported on ASSET P&L and on SURPLUS P&L = assets - guaranteed liability PV,
    plus deterministic stress tests and a per-driver decomposition.

Repricing
    bonds     : modified duration + convexity at each bond's maturity, shifted
                EUR curve
    liability : full revaluation on the shifted EUR zero curve
    sleeves   : own-currency (= EUR-hedged) total return
    FX hedge  : residual = change in the EUR-USD 1y rate differential
    futures   : short MSCI World proxy, notional = ratio * beta * equity MV

Run
    python case3_model.py            # HS suite (unhedged / rule-overlay / t0) + MC
    python case3_model.py hs full auto
    python case3_model.py mc full 25000
"""

from __future__ import annotations

import math
import re
import sys
import warnings
from dataclasses import dataclass, field, replace
from datetime import date
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
Z = 2.3263479          # standard normal 99% one-sided
_VAL = pd.Timestamp("2026-09-02")
_DATE_LO = pd.Timestamp("1998-01-01")


# ==========================================================================
# 1. CONFIG  (case + model + funding waterfall)
# ==========================================================================
@dataclass(frozen=True)
class Config:
    valuation_date: str = "2026-09-02"
    confidence: float = 0.99
    horizon_weeks: int = 52
    lookback_weeks: int = 520

    # --- investment / funding structure ---
    deployment: str = "full"              # "full" (5bn FI + 5bn return) | "t0"
    fi_book_eur: float = 5.0 * EUR_BN     # t=0 inflow -> Fixed Income
    contribution_per_year_eur: float = 0.5 * EUR_BN
    contribution_years: int = 10          # t=1..10 -> Return book
    return_weight_set: str = "Aggressive_Diversified"
    # return-book size: "sum" = contributions paid in (10 x 0.5bn); "projected"
    # = MV after the semi-annual rebalance + 90/10 profit-sharing path
    # (return_book.py)
    return_book_mode: str = "sum"
    rebalance_per_year: int = 2
    profit_share_policyholder: float = 0.90

    # --- guaranteed liability (IAS) ---
    guaranteed_rate: float = 0.01
    pension_share: float = 0.50
    lump_sum_share: float = 0.50
    n_policyholders: int = 100_000
    initial_value_pp: float = 50_000.0
    contribution_pp: float = 5_000.0
    first_benefit_year: int = 15

    # --- futures overlay / risk-control rule ---
    future_hedge_ratio: "float | None" = None   # None => set by the rule
    equity_beta: float = 1.0
    overlay_buffer: float = 0.10               # no-trade band around the limit
    min_funding_ratio: float = 1.20            # board floor (assets / liability PV)
    var_limit_eur: "float | None" = None       # explicit equity VaR limit; else derived

    # --- currency / sleeve classification ---
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
# 2. DATA LOADING  (Bloomberg-Excel curves / FX / indices, teammate outputs)
# ==========================================================================
def _parse_dates(raw: pd.Series) -> pd.Series:
    dt = pd.to_datetime(raw, errors="coerce")
    bad = pd.to_datetime(raw, errors="coerce", dayfirst=True)
    dt = dt.where((dt >= _DATE_LO) & (dt <= _VAL + pd.Timedelta(days=7)))
    dt = dt.fillna(bad.where((bad >= _DATE_LO) & (bad <= _VAL + pd.Timedelta(days=7))))
    return dt


def load_swap_history(path: Path, tenor_regex: str, raw_divisor: float = 1e7) -> pd.DataFrame:
    """Par swap-rate history; columns = tenor (years), values = decimal.
    Parses the repeating [weekday, date, rate, spacer] block layout."""
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
    return df[~df.index.duplicated(keep="last")].sort_index()


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
    return pw.set_index("Asset")[cfg.return_weight_set] / 100.0


def load_fi_portfolio() -> pd.DataFrame:
    d = pd.read_csv(FI_PORTFOLIO_CSV)
    return d[d["eur_allocation"] > 1.0].reset_index(drop=True)


# ==========================================================================
# 3. CURVE  (annual par-swap bootstrap, log-linear DF, flat-forward > 30y)
# ==========================================================================
def bootstrap_zero_curve(par_rates: pd.Series) -> "tuple[np.ndarray, np.ndarray]":
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
    return grid, -np.log(dfs) / grid


def zero_from_grid(grid: np.ndarray, zero: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    z = np.interp(np.clip(t, grid[0], grid[-1]), grid, zero)
    slope = (zero[-1] * grid[-1] - zero[-2] * grid[-2]) / (grid[-1] - grid[-2])
    return np.where(t > grid[-1], (zero[-1] * grid[-1] + slope * (t - grid[-1])) / t, z)


def discount(grid: np.ndarray, zero: np.ndarray, t: np.ndarray) -> np.ndarray:
    t = np.asarray(t, dtype=float)
    return np.exp(-zero_from_grid(grid, zero, t) * t)


# ==========================================================================
# 4. GUARANTEED LIABILITY  (50% lump @ yr15  +  50% pension yr16..50)
# ==========================================================================
def guaranteed_accumulated_value(cfg: Config) -> float:
    g, n = cfg.guaranteed_rate, cfg.n_policyholders
    init = cfg.initial_value_pp * (1.0 + g) ** cfg.first_benefit_year
    contrib = sum(cfg.contribution_pp * (1.0 + g) ** (cfg.first_benefit_year - t)
                  for t in range(1, cfg.contribution_years + 1))
    return n * (init + contrib)


def liability_cashflows(cfg: Config) -> pd.Series:
    acc = guaranteed_accumulated_value(cfg)
    cf = {cfg.first_benefit_year: cfg.lump_sum_share * acc}
    pen = pd.read_excel(DATA / "pension_liability_results.xlsx", sheet_name="Sheet1")
    pen.columns = [str(c).strip() for c in pen.columns]
    for _, row in pen.iterrows():
        yr = cfg.first_benefit_year + int(row["Year"])
        cf[yr] = cf.get(yr, 0.0) + cfg.pension_share * float(row["Expected_Annual_Pension_Cashflow"])
    s = pd.Series(cf).sort_index()
    s.index.name = "year"
    return s


# ==========================================================================
# 5. BOOK ASSEMBLY  (FI 5bn  +  return book from contributions)
# ==========================================================================
@dataclass
class Book:
    cfg: Config
    fi: pd.DataFrame
    sleeves: pd.DataFrame
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

    @property
    def equity_mv(self) -> float:
        return float(self.sleeves.loc[self.sleeves["kind"] == "EQUITY", "mv_eur"].sum())


def _latest_row(hist: pd.DataFrame) -> pd.Series:
    return hist.loc[:_VAL].ffill().iloc[-1].dropna()


def build_book(cfg: Config) -> Book:
    eur_hist = load_swap_history(DATA / "EUR SWAP CURVES 1-30yr.xlsx", r"(\d+)\s*yr")
    usd_hist = load_swap_history(DATA / "USD SWAP CURVE 1-30yr.xlsx", r"USOSFR(\d+)")
    base_par = _latest_row(eur_hist)
    grid, zero = bootstrap_zero_curve(base_par)

    fi = load_fi_portfolio().copy()                      # t=0: EUR 5.0bn, 16 bonds

    weights = load_return_weights(cfg)
    idx_hist = load_index_history()
    rb = cfg.return_book_eur                             # t=1..10: 10 x 0.5bn
    if cfg.return_book_mode == "projected" and cfg.deployment != "t0":
        from return_book import RBConfig, projected_book_mv
        rb = projected_book_mv(RBConfig(
            contribution_per_year_eur=cfg.contribution_per_year_eur,
            contribution_years=cfg.contribution_years,
            rebalance_per_year=cfg.rebalance_per_year,
            profit_share_policyholder=cfg.profit_share_policyholder,
            weight_set=cfg.return_weight_set))
    rows = []
    for name, w in weights.items():
        if name not in idx_hist.columns:
            continue
        ccy = "EUR" if name in cfg.eur_sleeves else "USD"
        kind = ("HY" if name in cfg.hy_sleeves
                else "EQUITY" if name in cfg.equity_sleeves else "RATES_CREDIT")
        rows.append({"sleeve": name, "weight": float(w), "mv_eur": float(w) * rb,
                     "currency": ccy, "kind": kind})
    sleeves = pd.DataFrame(rows)

    ur = _latest_row(usd_hist)
    return Book(cfg=cfg, fi=fi, sleeves=sleeves,
                liability_cf=liability_cashflows(cfg),
                base_grid=grid, base_zero=zero,
                base_usd_1y=float(ur.get(1, ur.iloc[0])),
                base_eur_1y=float(base_par.get(1, base_par.iloc[0])))


# ==========================================================================
# 6. FX SWAP  (roll every USD sleeve back to EUR; HKD leg ignored)
# ==========================================================================
def fx_forward_rate(spot: float, r_dom: float, r_for: float, T: float,
                    continuous: bool = False) -> float:
    """Covered-interest-parity forward (spot = domestic per foreign, e.g. USD/EUR)."""
    if continuous:
        return spot * math.exp((r_dom - r_for) * T)
    return spot * (1.0 + r_dom * T) / (1.0 + r_for * T)


def fx_hedge_carry(value_eur: float, r_eur: float, r_usd: float, T: float = 1.0) -> float:
    """Deterministic carry of a rolled 1y EUR/USD hedge: value * (r_eur - r_usd) * T."""
    return value_eur * (r_eur - r_usd) * T


def fx_hedge_rate_diff_coeff(value_eur: float, T: float = 1.0) -> float:
    """Coefficient on -(d r_usd - d r_eur) for the hedge-residual P&L."""
    return value_eur * T


# ==========================================================================
# 7. EQUITY-INDEX FUTURE  (pricing + short-hedge sizing for the overlay)
# ==========================================================================
_DAYS_PER_YEAR = 365.0


def year_fraction(start: date, end: date) -> float:
    return max(0.0, (end - start).days / _DAYS_PER_YEAR)


def future_fair_price(spot: float, r: float, tau: float, q: float = 0.0,
                      discrete_div_pv: float = 0.0) -> float:
    """Cost-of-carry: F = S*exp((r-q)*tau), or (S-D)*exp(r*tau) with discrete divs."""
    if discrete_div_pv:
        return (spot - discrete_div_pv) * math.exp(r * tau)
    return spot * math.exp((r - q) * tau)


@dataclass(frozen=True)
class EquityIndexFuture:
    underlying: str
    multiplier: float
    expiry: date
    dividend_yield: float = 0.0
    currency: str = "EUR"

    def tau(self, as_of: date) -> float:
        return year_fraction(as_of, self.expiry)

    def fair_price(self, spot: float, r: float, as_of: date,
                   discrete_div_pv: float = 0.0) -> float:
        return future_fair_price(spot, r, self.tau(as_of), self.dividend_yield,
                                 discrete_div_pv)

    def basis(self, spot: float, r: float, as_of: date, **kw) -> float:
        return self.fair_price(spot, r, as_of, **kw) - spot

    def contract_value(self, price: float) -> float:
        return price * self.multiplier

    def position_notional(self, n_contracts: float, price: float) -> float:
        return n_contracts * self.contract_value(price)

    def mark_to_market(self, n_contracts: float, entry: float, current: float) -> float:
        return n_contracts * self.multiplier * (current - entry)

    def delta_eur_per_index_pct(self, n_contracts: float, spot: float) -> float:
        return n_contracts * self.multiplier * spot * 0.01

    def carry_pnl(self, n_contracts: float, spot: float, r: float, days: float) -> float:
        dt = days / _DAYS_PER_YEAR
        return -(r - self.dividend_yield) * self.position_notional(n_contracts, spot) * dt

    def contracts_for_notional(self, target_notional_eur: float, price: float,
                               whole: bool = True) -> float:
        raw = target_notional_eur / self.contract_value(price)
        return float(round(raw)) if whole else raw


def hedge_contracts(future: EquityIndexFuture, equity_notional_eur: float,
                    price: float, hedge_ratio: float, beta: float = 1.0,
                    whole: bool = True) -> float:
    """Contracts to SHORT (negative) to hedge `hedge_ratio` of a long equity book:
        n = - hedge_ratio * beta * equity_notional_eur / (price * multiplier)."""
    return future.contracts_for_notional(
        -hedge_ratio * beta * equity_notional_eur, price, whole=whole)


# ==========================================================================
# 8. VIX  (Heston stochastic vol; analytic VIX map; leverage)
# ==========================================================================
_TAU_VIX = 30.0 / 365.0


def vix_term_weight(kappa: float, tau: float = _TAU_VIX) -> float:
    """A(tau) = (1 - e^{-kappa tau}) / (kappa tau)."""
    x = kappa * tau
    return (1.0 - np.exp(-x)) / x


@dataclass(frozen=True)
class HestonVIX:
    """dv = kappa(theta - v)dt + xi sqrt(v) dW^v ,  corr(dW^S, dW^v) = rho.
    VIX_t^2 = (A(tau) v_t + (1 - A(tau)) theta) * 100^2  (exact under Heston)."""
    kappa: float = 4.0
    theta: float = 0.028               # ~16.7% long-run vol
    xi: float = 0.65
    rho: float = -0.75                 # leverage
    v0: "float | None" = 0.018         # ~13.4% vol - calm start

    @property
    def feller_ok(self) -> bool:
        return 2.0 * self.kappa * self.theta >= self.xi ** 2

    def vix(self, v) -> np.ndarray:
        A = vix_term_weight(self.kappa)
        return 100.0 * np.sqrt(A * np.asarray(v, dtype=float) + (1.0 - A) * self.theta)

    def simulate_paths(self, equity_market_shock: np.ndarray, dt: float,
                       rng: np.random.Generator) -> dict:
        """Weekly full-truncation Euler for v_t driven by the leverage-correlated
        market shock. Returns v, vix, and vol_mult = sqrt(v_t/theta) to scale
        the equity weekly returns to the regime."""
        z_mkt = np.asarray(equity_market_shock, dtype=float)
        n_paths, n_steps = z_mkt.shape
        z_perp = rng.standard_normal((n_paths, n_steps))
        dWv = self.rho * z_mkt + np.sqrt(1.0 - self.rho ** 2) * z_perp
        v0 = self.theta if self.v0 is None else self.v0
        v = np.empty((n_paths, n_steps + 1))
        v[:, 0] = v0
        sdt = np.sqrt(dt)
        for w in range(n_steps):
            vp = np.maximum(v[:, w], 0.0)
            v[:, w + 1] = np.maximum(
                v[:, w] + self.kappa * (self.theta - vp) * dt
                + self.xi * np.sqrt(vp) * sdt * dWv[:, w], 0.0)
        return {"v": v, "vix": self.vix(v),
                "vol_mult": np.sqrt(np.maximum(v[:, :n_steps], 0.0) / self.theta)}


# ==========================================================================
# 9. RISK-FACTOR PANEL  +  HISTORICAL-SIMULATION SCENARIOS
# ==========================================================================
@dataclass
class Scenarios:
    dates: pd.Index
    eur_rate_chg: pd.DataFrame          # 1y absolute rate change, columns = tenor
    usd_1y_chg: np.ndarray
    eur_1y_chg: np.ndarray
    idx_logret: pd.DataFrame            # 1y log return per index
    n: int


def weekly_changes(cfg: Config) -> dict:
    """Aligned weekly factor moves over the lookback window (shared by HS and MC)."""
    eur_hist = load_swap_history(DATA / "EUR SWAP CURVES 1-30yr.xlsx", r"(\d+)\s*yr")
    usd_hist = load_swap_history(DATA / "USD SWAP CURVE 1-30yr.xlsx", r"USOSFR(\d+)")
    idx_hist = load_index_history()
    master = idx_hist.index[-cfg.lookback_weeks:]
    if len(master) < cfg.horizon_weeks + 30:
        raise RuntimeError(f"only {len(master)} weekly obs - not enough")

    def onto_master(df):
        return df.reindex(df.index.union(master)).ffill().bfill().reindex(master)

    eur, usd = onto_master(eur_hist), onto_master(usd_hist)
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
    h = cfg.horizon_weeks
    ann_eur = wc["d_eur"].rolling(h).sum().dropna()
    ann_usd1 = wc["d_usd1"].rolling(h).sum().dropna()
    ann_eur1 = wc["d_eur1"].rolling(h).sum().dropna()
    ann_idx = wc["r_idx"].rolling(h).sum().dropna()
    dates = ann_idx.index.intersection(ann_eur.index)
    return Scenarios(dates=dates, eur_rate_chg=ann_eur.reindex(dates),
                     usd_1y_chg=ann_usd1.reindex(dates).to_numpy(),
                     eur_1y_chg=ann_eur1.reindex(dates).to_numpy(),
                     idx_logret=ann_idx.reindex(dates), n=len(dates))


# ==========================================================================
# 10. REPRICING ENGINE  (shared by HS and MC)
# ==========================================================================
def reprice(book: Book, sc: Scenarios, cfg: "Config | None" = None) -> pd.DataFrame:
    cfg = cfg or book.cfg
    grid, zero = book.base_grid, book.base_zero
    tenors = sc.eur_rate_chg.columns.to_numpy(dtype=float)
    chg = sc.eur_rate_chg.to_numpy()

    # -- FI bonds: modified duration + convexity at each bond's maturity --
    ytm = book.fi["years_to_maturity"].to_numpy()
    mdur = book.fi["modified_duration"].to_numpy()
    conv = book.fi.get("convexity", pd.Series(np.zeros(len(book.fi)))).to_numpy()
    mv = book.fi["eur_allocation"].to_numpy()
    dy = np.array([np.interp(ytm, tenors, row) for row in chg])
    fi_pnl = (mv * (-mdur * dy + 0.5 * conv * dy ** 2)).sum(axis=1)

    # -- index sleeves (own-currency total return) + FX-hedge residual ----
    by_kind = {"EQUITY": 0.0, "HY": 0.0, "RATES_CREDIT": 0.0}
    fx_resid = np.zeros(sc.n)
    for _, s in book.sleeves.iterrows():
        r = sc.idx_logret[s["sleeve"]].to_numpy()
        by_kind[s["kind"]] = by_kind[s["kind"]] + s["mv_eur"] * (np.exp(r) - 1.0)
        if s["currency"] == "USD":
            fx_resid += -fx_hedge_rate_diff_coeff(s["mv_eur"]) * (sc.usd_1y_chg - sc.eur_1y_chg)

    # -- futures short overlay (broad-equity proxy = MSCI World) ----------
    fut_pnl = np.zeros(sc.n)
    ratio = cfg.future_hedge_ratio or 0.0
    if ratio > 0 and "MSCI World Index" in sc.idx_logret.columns:
        short_notional = ratio * cfg.equity_beta * book.equity_mv
        rw = sc.idx_logret["MSCI World Index"].to_numpy()
        fut_pnl = -short_notional * (np.exp(rw) - 1.0)

    # -- guaranteed liability: full revaluation on the shifted zero curve --
    yrs = book.liability_cf.index.to_numpy(dtype=float)
    cfv = book.liability_cf.to_numpy()
    pv0 = float(np.sum(cfv * discount(grid, zero, yrs)))
    liab_pnl = np.empty(sc.n)
    for k in range(sc.n):
        dzero = np.interp(np.clip(grid, tenors[0], tenors[-1]), tenors, chg[k])
        liab_pnl[k] = float(np.sum(cfv * discount(grid, zero + dzero, yrs))) - pv0

    out = pd.DataFrame({
        "date": sc.dates, "fi_bonds": fi_pnl, "equity": by_kind["EQUITY"],
        "high_yield": by_kind["HY"], "rates_credit_idx": by_kind["RATES_CREDIT"],
        "fx_hedge_residual": fx_resid, "futures_overlay": fut_pnl,
    })
    out["asset_pnl"] = (out["fi_bonds"] + out["equity"] + out["high_yield"]
                        + out["rates_credit_idx"] + out["fx_hedge_residual"]
                        + out["futures_overlay"])
    out["liability_pnl"] = liab_pnl
    out["surplus_pnl"] = out["asset_pnl"] - out["liability_pnl"]
    return out


# ==========================================================================
# 11. VaR STATISTICS
# ==========================================================================
def var_stats(pnl: np.ndarray, conf: float) -> dict:
    pnl = np.asarray(pnl, dtype=float)
    q = np.percentile(pnl, (1.0 - conf) * 100.0)
    tail = pnl[pnl <= q]
    return {"hist_var": -q, "hist_es": -tail.mean() if tail.size else -q,
            "param_var": -(pnl.mean() - Z * pnl.std(ddof=1)),
            "mean_pnl": pnl.mean(), "vol_pnl": pnl.std(ddof=1),
            "worst": -pnl.min(), "n_scen": pnl.size}


# ==========================================================================
# 12. RISK-CONTROL OVERLAY  (economic VaR limit -> hedge ratio -> band)
# ==========================================================================
def derive_var_limit(book: Book, cfg: Config, non_equity_surplus_var: float) -> dict:
    """Equity 99% 1y VaR limit anchored to the board funding-ratio floor:
        loss_budget = assets - min_funding_ratio * liability_PV
        equity_limit = max(0, loss_budget - non_equity_surplus_var)
        cross-check:  limit <= economic_surplus / 3."""
    assets, liab = book.asset_mv, book.liability_pv
    surplus = assets - liab
    eq_mv = book.equity_mv
    loss_budget = assets - cfg.min_funding_ratio * liab
    equity_limit = max(0.0, loss_budget - non_equity_surplus_var)
    sar_cap = surplus / 3.0
    limit = min(equity_limit, sar_cap)
    return {"assets": assets, "liability_pv": liab, "economic_surplus": surplus,
            "equity_mv": eq_mv, "min_funding_ratio": cfg.min_funding_ratio,
            "loss_budget_at_floor": loss_budget,
            "non_equity_surplus_var": non_equity_surplus_var,
            "equity_limit_from_floor": equity_limit, "surplus_at_risk_cap": sar_cap,
            "binding_constraint": ("funding-ratio floor" if equity_limit <= sar_cap
                                   else "surplus-at-risk cap"),
            "var_limit_eur": limit,
            "limit_pct_of_equity_mv": limit / eq_mv if eq_mv else float("nan"),
            "limit_pct_of_surplus": limit / surplus if surplus else float("nan")}


def target_hedge_ratio(var_unhedged: float, var_limit: float) -> float:
    """HedgeRatio = max(0, 1 - VaR_limit / VaR_unhedged), clamped [0, 1]."""
    if var_unhedged <= 0:
        return 0.0
    return float(min(1.0, max(0.0, 1.0 - var_limit / var_unhedged)))


def vix_gated_band(base_buffer: float, vix: "float | None",
                   calm: float = 20.0, spike: float = 40.0,
                   min_frac: float = 0.2) -> float:
    """No-trade band width vs VIX: wide when calm, shrinks calm->spike, floors
    at min_frac*base once VIX >= spike."""
    if vix is None:
        return base_buffer
    frac = np.clip(1.0 - (vix - calm) / (spike - calm), min_frac, 1.0)
    return base_buffer * float(frac)


def applied_hedge_ratio(var_unhedged: float, var_limit: float, current_ratio: float,
                        buffer: float, vix: "float | None" = None) -> "tuple[float, str]":
    band = vix_gated_band(buffer, vix)
    tgt = target_hedge_ratio(var_unhedged, var_limit)
    lo, hi = var_limit * (1 - band), var_limit * (1 + band)
    vtxt = f" (VIX {vix:.0f})" if vix else ""
    if lo <= var_unhedged <= hi:
        return current_ratio, f"within +/-{band:.0%} band{vtxt} - hold {current_ratio:.0%}"
    return tgt, f"outside +/-{band:.0%} band{vtxt} - move to {tgt:.0%}"


def resolve_overlay(book: Book, unhedged_pnl: pd.DataFrame, cfg: Config) -> dict:
    """From an unhedged reprice() output: equity VaR, non-equity surplus VaR,
    economic limit, and the applied hedge ratio (rule or pinned)."""
    conf = cfg.confidence
    eq_var = var_stats(unhedged_pnl["equity"].to_numpy(), conf)["hist_var"]
    non_eq = var_stats((unhedged_pnl["surplus_pnl"] - unhedged_pnl["equity"]).to_numpy(),
                       conf)["hist_var"]
    li = derive_var_limit(book, cfg, non_eq)
    limit = cfg.var_limit_eur if cfg.var_limit_eur is not None else li["var_limit_eur"]
    ok = eq_var > 1e6 and li["economic_surplus"] > 0
    if not ok:
        ratio, note, limit = float(cfg.future_hedge_ratio or 0.0), \
            "overlay N/A (no return book / pre-funding)", float("nan")
    elif cfg.future_hedge_ratio is not None:
        ratio = float(cfg.future_hedge_ratio)
        note = f"pinned at {ratio:.0%} (rule -> {target_hedge_ratio(eq_var, limit):.1%})"
    else:
        ratio = target_hedge_ratio(eq_var, limit)
        _, band = applied_hedge_ratio(eq_var, limit, ratio, cfg.overlay_buffer)
        note = f"rule: max(0, 1 - {limit/1e6:,.0f}m / {eq_var/1e6:,.0f}m) = {ratio:.1%}  [{band}]"
    return {"limit_info": li, "var_limit": limit, "eq_var_unhedged": eq_var,
            "non_equity_surplus_var": non_eq, "ratio": ratio, "note": note}


# ==========================================================================
# 13. DETERMINISTIC STRESS TESTS
# ==========================================================================
def stress_tests(book: Book) -> pd.DataFrame:
    grid, zero = book.base_grid, book.base_zero
    yrs = book.liability_cf.index.to_numpy(dtype=float)
    cfv = book.liability_cf.to_numpy()
    pv0 = float(np.sum(cfv * discount(grid, zero, yrs)))
    ytm = book.fi["years_to_maturity"].to_numpy()
    mdur = book.fi["modified_duration"].to_numpy()
    conv = book.fi.get("convexity", pd.Series(np.zeros(len(book.fi)))).to_numpy()
    mv = book.fi["eur_allocation"].to_numpy()
    eq_mv, hy_mv = book.equity_mv, book.sleeves.loc[book.sleeves["kind"] == "HY", "mv_eur"].sum()
    rc_mv = book.sleeves.loc[book.sleeves["kind"] == "RATES_CREDIT", "mv_eur"].sum()

    def rate_pnl(dy):
        fi = float((mv * (-mdur * dy + 0.5 * conv * dy ** 2)).sum())
        liab = float(np.sum(cfv * discount(grid, zero + dy, yrs))) - pv0
        return fi, liab

    scen = {
        "EUR rates +100bp parallel": dict(dy=0.01),
        "EUR rates +200bp parallel": dict(dy=0.02),
        "EUR rates -100bp parallel": dict(dy=-0.01),
        "Equity -20%": dict(eq=-0.20), "Equity -30%": dict(eq=-0.30),
        "Equity -40%": dict(eq=-0.40),
        "HY spread +300bp (~-12%)": dict(hy=-0.12),
        "2022 replay: rates +250bp, equity -20%": dict(dy=0.025, eq=-0.20),
        "2008 replay: equity -45%, rates -150bp, HY -25%": dict(dy=-0.015, eq=-0.45, hy=-0.25),
        "Longevity +1yr life exp (~+4% liability)": dict(liab_mult=0.04),
    }
    rows = []
    for name, s in scen.items():
        fi_pnl, liab_pnl = rate_pnl(s.get("dy", 0.0))
        eq_pnl, hy_pnl = eq_mv * s.get("eq", 0.0), hy_mv * s.get("hy", 0.0)
        rc_pnl = rc_mv * (0.5 * s.get("eq", 0.0) + 0.3 * s.get("hy", 0.0))
        liab_pnl += s.get("liab_mult", 0.0) * pv0
        asset = fi_pnl + eq_pnl + hy_pnl + rc_pnl
        rows.append({"scenario": name, "fi_bonds": fi_pnl, "equity": eq_pnl,
                     "high_yield": hy_pnl, "rates_credit_idx": rc_pnl,
                     "asset_pnl": asset, "liability_pnl": liab_pnl,
                     "surplus_pnl": asset - liab_pnl})
    return pd.DataFrame(rows).set_index("scenario")


# ==========================================================================
# 14. MONTE CARLO  (Student-t copula + PCA curve + Heston VIX layer)
# ==========================================================================
def _shrunk_corr(X: np.ndarray, delta: float = 0.10) -> np.ndarray:
    R = np.corrcoef(X, rowvar=False)
    off = R[~np.eye(R.shape[0], dtype=bool)].mean()
    target = np.full_like(R, off)
    np.fill_diagonal(target, 1.0)
    S = (1.0 - delta) * R + delta * target
    w, V = np.linalg.eigh((S + S.T) / 2.0)
    S = V @ np.diag(np.clip(w, 1e-8, None)) @ V.T
    d = np.sqrt(np.diag(S))
    return S / np.outer(d, d)


def simulate_mc(cfg: Config, n_paths: int = 20_000, nu: float = 5.0, seed: int = 7,
                n_pc: int = 3, heston: "HestonVIX | None" = None) -> "tuple[Scenarios, dict]":
    """52 weekly multivariate-t innovations, EUR curve via `n_pc` PCs, optional
    Heston market-variance path (leverage rho) that scales equity vol and yields
    a VIX_t path. Returns (Scenarios of 1y moves, vix_info)."""
    wc = weekly_changes(cfg)
    d_eur, d_usd1, d_eur1, r_idx = wc["d_eur"], wc["d_usd1"], wc["d_eur1"], wc["r_idx"]
    tenors, idx_cols, h = wc["eur_tenors"], list(r_idx.columns), cfg.horizon_weeks

    De = d_eur.dropna()
    de_mean = De.mean().to_numpy()
    _, _, Vt = np.linalg.svd(De.to_numpy() - de_mean, full_matrices=False)
    load = Vt[:n_pc]
    pc_df = pd.DataFrame((De.to_numpy() - de_mean) @ load.T, index=De.index,
                         columns=[f"pc{i+1}" for i in range(n_pc)])

    panel = pd.concat([pc_df, d_usd1, d_eur1, r_idx], axis=1).dropna()
    X = panel.to_numpy()
    mu, sd = X.mean(axis=0), X.std(axis=0, ddof=1)
    L = np.linalg.cholesky(_shrunk_corr(X))
    k = X.shape[1]

    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_paths, h, k)) @ L.T
    if np.isfinite(nu):
        gmix = rng.chisquare(nu, size=(n_paths, h, 1)) / nu
        tt = z / np.sqrt(gmix) * np.sqrt((nu - 2.0) / nu)
    else:
        tt = z
    weekly = mu + sd * tt

    eq_pos = [n_pc + 2 + idx_cols.index(s) for s in cfg.equity_sleeves if s in idx_cols]
    mkt_col = n_pc + 2 + idx_cols.index("MSCI World Index")
    vix_info: dict = {}
    if heston is not None:
        hp = heston.simulate_paths(tt[:, :, mkt_col], dt=1.0 / 52.0, rng=rng)
        weekly[:, :, eq_pos] *= hp["vol_mult"][:, :, None]
        worst_wk = np.argmin(weekly[:, :, mkt_col], axis=1)
        rows = np.arange(n_paths)
        vix_info = {"vix_max": hp["vix"].max(axis=1), "vix_terminal": hp["vix"][:, -1],
                    "vix_at_worst_equity_week": hp["vix"][rows, worst_wk + 1],
                    "feller_ok": heston.feller_ok, "A_tau": vix_term_weight(heston.kappa)}

    annual = weekly.sum(axis=1)
    pc_ann, usd1, eur1, idx_ann = (annual[:, :n_pc], annual[:, n_pc],
                                   annual[:, n_pc + 1], annual[:, n_pc + 2:])

    def soft(x, lo, hi):
        x = np.asarray(x, dtype=float)
        x = np.where(x > hi, hi + 0.5 * (x - hi), x)
        return np.where(x < lo, lo + 0.5 * (x - lo), x)

    g = 1.25
    de_ann = d_eur.rolling(h).sum().dropna()
    eur_chg = np.clip(pc_ann @ load, de_ann.min().to_numpy() * g, de_ann.max().to_numpy() * g)
    u1h, e1h = d_usd1.rolling(h).sum().dropna(), d_eur1.rolling(h).sum().dropna()
    usd1 = np.clip(usd1, u1h.min() * g, u1h.max() * g)
    eur1 = np.clip(eur1, e1h.min() * g, e1h.max() * g)
    ih = r_idx.rolling(h).sum().dropna()
    idx_ann = soft(idx_ann, ih.min().to_numpy() * g, ih.max().to_numpy() * g)

    sc = Scenarios(dates=pd.Index(range(n_paths), name="path"),
                   eur_rate_chg=pd.DataFrame(eur_chg, columns=tenors),
                   usd_1y_chg=usd1, eur_1y_chg=eur1,
                   idx_logret=pd.DataFrame(idx_ann, columns=idx_cols), n=n_paths)
    return sc, vix_info


def _vix_diagnostics(vi: dict, pnl: pd.DataFrame, cfg: Config) -> dict:
    if not vi:
        return {}
    er = pnl["equity_ret"].to_numpy()
    vwe = vi["vix_at_worst_equity_week"]
    tail = er <= np.quantile(er, 1.0 - cfg.confidence)
    return {"median_vix_terminal": float(np.median(vi["vix_terminal"])),
            "median_vix_max": float(np.median(vi["vix_max"])),
            "p99_vix_max": float(np.quantile(vi["vix_max"], 0.99)),
            "corr_vixmax_equity_1y_ret": float(np.corrcoef(vi["vix_max"], er)[0, 1]),
            "median_vix_worst_week_all": float(np.median(vwe)),
            "median_vix_worst_week_tail": float(np.median(vwe[tail])),
            "share_vix_gt_50_tail": float((vwe[tail] > 50).mean()),
            "share_vix_gt_40_tail": float((vwe[tail] > 40).mean())}


# ==========================================================================
# 15. REPORTS + CHARTS
# ==========================================================================
def _mn(x):
    return f"{x/1e6:,.1f}m"


def _write(path: Path, lines: list) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_hs(cfg: Config, tag: str | None = None) -> dict:
    """Historical-Simulation 99% 1y VaR + overlay + stress + report."""
    OUT.mkdir(exist_ok=True)
    book = build_book(cfg)
    sc = build_scenarios(cfg)

    ov = resolve_overlay(book, reprice(book, sc, replace(cfg, future_hedge_ratio=0.0)), cfg)
    cfg = replace(cfg, future_hedge_ratio=ov["ratio"], var_limit_eur=ov["var_limit"])
    tag = tag or f"{cfg.deployment}_h{int(round(ov['ratio']*100)):02d}"

    pnl = reprice(book, sc, cfg)
    pnl.to_csv(OUT / f"scenario_pnl_{tag}.csv", index=False)
    asset = var_stats(pnl["asset_pnl"].to_numpy(), cfg.confidence)
    surplus = var_stats(pnl["surplus_pnl"].to_numpy(), cfg.confidence)
    comps = ["fi_bonds", "equity", "high_yield", "rates_credit_idx",
             "fx_hedge_residual", "futures_overlay", "liability_pnl"]
    comp_var = {c: var_stats(pnl[c].to_numpy(), cfg.confidence)["hist_var"] for c in comps}
    pd.Series(comp_var, name="hist_var_eur").to_csv(OUT / f"component_var_{tag}.csv")
    stress = stress_tests(book)
    stress.to_csv(OUT / f"stress_tests_{tag}.csv")
    _hs_chart(pnl, asset, surplus, comp_var, stress, cfg, tag)

    li = ov["limit_info"]
    L, A = [], None
    A = L.append
    A(f"# Case 3b - Historical-Simulation 1-year {cfg.confidence:.0%} VaR  ({cfg.deployment})\n")
    A(f"Valuation {cfg.valuation_date}. {sc.n} overlapping 52-week scenarios "
      f"from ~{cfg.lookback_weeks} weeks of factor history.\n")
    A("## Book / structure\n")
    A(f"- Fixed income (t=0, EUR 5.0bn -> CF-matched): EUR "
      f"{book.fi['eur_allocation'].sum()/1e9:,.2f}bn, {len(book.fi)} bonds")
    A(f"- Return book (t=1..10, 10 x EUR 0.5bn, {cfg.return_weight_set}): EUR "
      f"{book.sleeves['mv_eur'].sum()/1e9:,.2f}bn  (equity EUR {book.equity_mv/1e9:,.2f}bn)")
    A(f"- Total assets EUR {book.asset_mv/1e9:,.2f}bn | guaranteed liability PV "
      f"EUR {book.liability_pv/1e9:,.2f}bn | funding ratio "
      f"{book.asset_mv/book.liability_pv:,.2f}\n")
    A("## Risk-control overlay\n")
    A(f"- Economic surplus EUR {li['economic_surplus']/1e9:,.2f}bn; funding-ratio "
      f"floor {li['min_funding_ratio']:.2f} => max 1y asset loss EUR "
      f"{li['loss_budget_at_floor']/1e9:,.2f}bn")
    A(f"- less non-equity surplus VaR EUR {li['non_equity_surplus_var']/1e6:,.0f}m "
      f"=> **equity 99% 1y VaR limit EUR {ov['var_limit']/1e6:,.0f}m** "
      f"({li['limit_pct_of_equity_mv']:.1%} of equity MV; binding: {li['binding_constraint']})")
    A(f"- unhedged equity 99% 1y VaR EUR {ov['eq_var_unhedged']/1e6:,.0f}m -> {ov['note']}")
    A(f"- applied futures short {cfg.future_hedge_ratio:.1%} of equity MV "
      f"(beta {cfg.equity_beta:.2f})\n")
    A("## Headline VaR / ES (1-year, EUR)\n")
    A("| | Hist VaR | Hist ES | Param VaR | 1y P&L vol | worst |")
    A("|---|--:|--:|--:|--:|--:|")
    A(f"| **Asset**   | {_mn(asset['hist_var'])} | {_mn(asset['hist_es'])} | "
      f"{_mn(asset['param_var'])} | {_mn(asset['vol_pnl'])} | {_mn(asset['worst'])} |")
    A(f"| **Surplus** | {_mn(surplus['hist_var'])} | {_mn(surplus['hist_es'])} | "
      f"{_mn(surplus['param_var'])} | {_mn(surplus['vol_pnl'])} | {_mn(surplus['worst'])} |")
    A(f"\nAsset VaR {asset['hist_var']/book.asset_mv:.1%} of assets | "
      f"Surplus VaR {surplus['hist_var']/book.liability_pv:.1%} of liability\n")
    A(f"## Standalone {cfg.confidence:.0%} 1y loss by driver (indicative)\n")
    A("| driver | loss |")
    A("|---|--:|")
    for c, v in sorted(comp_var.items(), key=lambda kv: -kv[1]):
        A(f"| {c} | {_mn(v)} |")
    A("\n## Stress tests (EUR P&L)\n")
    A("| scenario | asset | liability | surplus |")
    A("|---|--:|--:|--:|")
    for name, row in stress.iterrows():
        A(f"| {name} | {_mn(row['asset_pnl'])} | {_mn(row['liability_pnl'])} | {_mn(row['surplus_pnl'])} |")
    _write(OUT / f"HS_REPORT_{tag}.md", L)
    print("\n".join(L))
    print(f"\nwrote {OUT}/  (tag='{tag}')")
    return {"asset": asset, "surplus": surplus, "book": book, "overlay": ov,
            "comp_var": comp_var, "stress": stress, "pnl": pnl}


def run_mc(cfg: Config, n_paths: int = 20_000, tag: str | None = None,
           heston: "HestonVIX | None" = None) -> dict:
    OUT.mkdir(exist_ok=True)
    tag = tag or f"mc_{cfg.deployment}"
    heston = heston or HestonVIX()
    book = build_book(cfg)

    sim, _ = simulate_mc(cfg, n_paths=n_paths, nu=5.0, heston=heston)
    ov = resolve_overlay(book, reprice(book, sim, replace(cfg, future_hedge_ratio=0.0)), cfg)
    cfg2 = replace(cfg, future_hedge_ratio=ov["ratio"])

    results, vinfo = {}, None
    for label, nu in (("student_t_nu5", 5.0), ("gaussian", np.inf)):
        s, vi = simulate_mc(cfg, n_paths=n_paths, nu=nu, seed=11, heston=heston)
        pnl = reprice(book, s, cfg2)
        pnl["equity_ret"] = pnl["equity"] / max(book.equity_mv, 1.0)
        pnl.to_csv(OUT / f"{tag}_{label}_pnl.csv", index=False)
        results[label] = {"asset": var_stats(pnl["asset_pnl"].to_numpy(), cfg.confidence),
                          "surplus": var_stats(pnl["surplus_pnl"].to_numpy(), cfg.confidence),
                          "pnl": pnl}
        if label == "student_t_nu5":
            vinfo = vi
    vd = _vix_diagnostics(vinfo, results["student_t_nu5"]["pnl"], cfg)

    L = []
    A = L.append
    A(f"# Case 3b - Monte-Carlo 1-year {cfg.confidence:.0%} VaR  ({cfg.deployment})\n")
    A(f"{n_paths:,} paths x 52 weekly Student-t (dof 5) steps, PCA curve, Heston "
      f"stochastic vol + leverage. Book repriced with the HS engine.\n")
    A(f"- assets EUR {book.asset_mv/1e9:,.2f}bn | liability PV EUR "
      f"{book.liability_pv/1e9:,.2f}bn | economic surplus EUR "
      f"{ov['limit_info']['economic_surplus']/1e9:,.2f}bn")
    A(f"- equity 99% 1y VaR limit EUR {ov['var_limit']/1e6:,.0f}m | unhedged "
      f"equity VaR EUR {ov['eq_var_unhedged']/1e6:,.0f}m -> hedge {ov['ratio']:.1%}\n")
    A("## MC VaR / ES (1-year, EUR)\n")
    A("| model | Asset VaR | Asset ES | Surplus VaR | Surplus ES |")
    A("|---|--:|--:|--:|--:|")
    for lab, r in results.items():
        A(f"| {lab} | {_mn(r['asset']['hist_var'])} | {_mn(r['asset']['hist_es'])} | "
          f"{_mn(r['surplus']['hist_var'])} | {_mn(r['surplus']['hist_es'])} |")
    if vd:
        A("\n## VIX (Heston kappa {:.1f}, theta {:.3f}, xi {:.2f}, rho {:.2f})\n".format(
            heston.kappa, heston.theta, heston.xi, heston.rho))
        A(f"VIX_t = 100 sqrt(A(tau) v_t + (1-A) theta), "
          f"A(tau) = {vinfo.get('A_tau', vix_term_weight(heston.kappa)):.3f}.\n")
        A(f"- median VIX terminal / path-max: {vd['median_vix_terminal']:.1f} / "
          f"{vd['median_vix_max']:.1f}  (99th-pct path-max {vd['p99_vix_max']:.1f})")
        A(f"- corr(path-max VIX, 1y equity return): {vd['corr_vixmax_equity_1y_ret']:+.2f}")
        A(f"- VIX at the crash week: {vd['median_vix_worst_week_all']:.1f} (all) vs "
          f"**{vd['median_vix_worst_week_tail']:.1f}** (99% equity tail)")
        A(f"- share of 99%-tail paths with VIX > 40 / > 50 at the crash week: "
          f"{vd['share_vix_gt_40_tail']:.0%} / {vd['share_vix_gt_50_tail']:.0%}")
        A("\n=> VIX spikes coincide with the crash paths -> a VIX-gated no-trade "
          "band (`vix_gated_band`) is meaningful.")
    _write(OUT / f"MC_REPORT_{tag}.md", L)
    _mc_chart(results, cfg, tag, vinfo)
    print("\n".join(L))
    print(f"\nwrote {OUT}/  (tag='{tag}')")
    return {**results, "overlay": ov, "vix_diag": vd, "vix_info": vinfo}


def _hs_chart(pnl, asset, surplus, comp_var, stress, cfg, tag):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C_A, C_S, C_NEG, C_POS, GRID = "#0072B2", "#D55E00", "#D55E00", "#009E73", "#E6E6E6"
    fig, ax = plt.subplots(2, 2, figsize=(15, 10))
    a, s = pnl["asset_pnl"].to_numpy() / 1e6, pnl["surplus_pnl"].to_numpy() / 1e6
    ax[0, 0].hist(a, bins=40, color=C_A, alpha=0.55, label="asset")
    ax[0, 0].hist(s, bins=40, color=C_S, alpha=0.55, label="surplus")
    ax[0, 0].axvline(-asset["hist_var"] / 1e6, color=C_A, lw=2, ls="--")
    ax[0, 0].axvline(-surplus["hist_var"] / 1e6, color=C_S, lw=2, ls="--")
    ax[0, 0].set_title(f"1-year P&L ({pnl.shape[0]} scenarios)")
    ax[0, 0].set_xlabel("EUR m"); ax[0, 0].legend(frameon=False)
    cv = pd.Series(comp_var).sort_values() / 1e6
    ax[0, 1].barh(cv.index, cv.values, color=C_A)
    ax[0, 1].set_title(f"Standalone 1y {cfg.confidence:.0%} loss by driver (EUR m)")
    st = stress["surplus_pnl"].sort_values() / 1e6
    ax[1, 0].barh(st.index, st.values, color=[C_NEG if v < 0 else C_POS for v in st.values])
    ax[1, 0].axvline(0, color="#333", lw=1)
    ax[1, 0].set_title("Stress tests - surplus P&L (EUR m)")
    ax[1, 1].plot(np.sort(a), np.linspace(0, 1, len(a)), color=C_A, lw=2, label="asset")
    ax[1, 1].plot(np.sort(s), np.linspace(0, 1, len(s)), color=C_S, lw=2, label="surplus")
    ax[1, 1].axhline(1 - cfg.confidence, color="#333", lw=1, ls=":")
    ax[1, 1].set_title("Empirical CDF of 1y P&L"); ax[1, 1].set_xlabel("EUR m")
    ax[1, 1].legend(frameon=False)
    for a_ in ax.flat:
        a_.grid(color=GRID, lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle(f"Case 3b - combined book, 1y {cfg.confidence:.0%} VaR ({cfg.deployment})",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(OUT / f"hs_charts_{tag}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def _mc_chart(results, cfg, tag, vinfo=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C_T, C_G, C_V = "#0072B2", "#E69F00", "#D55E00"
    n = 3 if vinfo else 2
    fig, ax = plt.subplots(1, n, figsize=(6.6 * n, 5.2))
    for label, c in (("student_t_nu5", C_T), ("gaussian", C_G)):
        a = np.sort(results[label]["pnl"]["surplus_pnl"].to_numpy() / 1e6)
        ax[0].plot(a, np.linspace(0, 1, len(a)), color=c, lw=2, label=label)
        ax[0].axvline(-results[label]["surplus"]["hist_var"] / 1e6, color=c, lw=1.5, ls="--")
    ax[0].axhline(1 - cfg.confidence, color="#333", lw=1, ls=":")
    ax[0].set_title("MC surplus P&L - empirical CDF"); ax[0].set_xlabel("EUR m")
    ax[0].legend(frameon=False)
    t = results["student_t_nu5"]["pnl"]["asset_pnl"].to_numpy() / 1e6
    g = results["gaussian"]["pnl"]["asset_pnl"].to_numpy() / 1e6
    ax[1].hist(t, bins=60, color=C_T, alpha=0.55, label="Student-t (5)")
    ax[1].hist(g, bins=60, color=C_G, alpha=0.55, label="Gaussian")
    ax[1].set_title("MC asset P&L distribution"); ax[1].set_xlabel("EUR m")
    ax[1].legend(frameon=False)
    if vinfo:
        er = results["student_t_nu5"]["pnl"]["equity_ret"].to_numpy() * 100.0
        ax[2].scatter(er, vinfo["vix_at_worst_equity_week"], s=5, alpha=0.25, color=C_T)
        ax[2].axhline(50, color=C_V, lw=1.5, ls="--")
        ax[2].axhline(40, color=C_V, lw=1, ls=":")
        ax[2].set_title("VIX at crash week vs 1y equity return")
        ax[2].set_xlabel("1y equity return (%)"); ax[2].set_ylabel("VIX")
    for a_ in ax:
        a_.grid(color="#E6E6E6", lw=0.7); a_.set_axisbelow(True)
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    fig.suptitle(f"Case 3b - Monte-Carlo 1y {cfg.confidence:.0%} VaR ({cfg.deployment})",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(OUT / f"mc_charts_{tag}.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


# ==========================================================================
# 16. ORCHESTRATOR
# ==========================================================================
def run_all(mc_paths: int = 25_000) -> None:
    run_hs(Config(deployment="full", future_hedge_ratio=0.0), tag="full_unhedged")
    run_hs(Config(deployment="full"), tag="full_overlay")
    run_hs(Config(deployment="t0", future_hedge_ratio=0.0), tag="t0_inception")
    run_hs(Config(deployment="full", return_book_mode="projected",
                  future_hedge_ratio=0.0), tag="full_projected")   # semi-annual
    run_mc(Config(deployment="full"), n_paths=mc_paths, tag="mc_full")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        run_all()
    elif a[0] == "hs":
        h = None if len(a) <= 2 or a[2] == "auto" else float(a[2])
        mode = "projected" if "projected" in a[3:] else "sum"
        run_hs(Config(deployment=a[1] if len(a) > 1 else "full",
                      future_hedge_ratio=h, return_book_mode=mode))
    elif a[0] == "mc":
        mode = "projected" if "projected" in a[3:] else "sum"
        run_mc(Config(deployment=a[1] if len(a) > 1 else "full",
                      return_book_mode=mode),
               n_paths=int(a[2]) if len(a) > 2 and a[2].isdigit() else 20_000)
    elif a[0] == "returnbook":
        from return_book import RBConfig, project, _report_and_chart
        _report_and_chart(project(RBConfig()), RBConfig())
    else:
        run_all()
