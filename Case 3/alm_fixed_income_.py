from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
import math
import re
import sys

import cvxpy as cp
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.optimize import brentq

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass


# ==========================================================
# PROJECT PATHS AND BASIC CONSTANTS
# ==========================================================


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "Data"
RESULTS_DIR = PROJECT_ROOT / "results"

# Where input workbooks may live, in priority order. "Data/" is the canonical
# location; the project root and a lower-case "data/" are kept as fallbacks so
# older layouts still resolve.
INPUT_SEARCH_DIRS = (DATA_DIR, PROJECT_ROOT / "data", PROJECT_ROOT)

EUR_BN = 1_000_000_000.0
EUR_MN = 1_000_000.0
BASIS_POINT = 0.0001

INPUT_FILENAMES = {
    "fixed_income": "Fixed Income Basket.xlsx",
    "eur_swaps": "EUR SWAP CURVES 1-30yr.xlsx",
    "pension": "pension_liability_results.xlsx",
    "usd_swaps": "USD SWAP CURVE 1-30yr.xlsx",
    "eurusd": "EUR USD Rates.xlsx",
}

WEEKDAY_TO_INT = {
    "Mo": 0,
    "Tu": 1,
    "We": 2,
    "Th": 3,
    "Fr": 4,
    "Sa": 5,
    "Su": 6,
}


@dataclass(frozen=True)
class Assumptions:
    """Case, modelling and optimization assumptions used by the standalone model."""

    valuation_date: str = "2026-09-02"

    # Case inputs. These are not market data.
    current_available_assets_eur: float = 5.0 * EUR_BN
    policyholders: int = 100_000
    initial_account_value_per_policyholder: float = 50_000.0
    annual_contribution_per_policyholder: float = 5_000.0
    contribution_years: int = 10
    deferral_after_last_contribution_years: int = 5
    guaranteed_rate: float = 0.01

    # Policyholder choice base case. Keep configurable.
    lump_sum_share: float = 0.50
    pension_share: float = 0.50

    # The pension workbook maps pension year 1 to projection year 16,
    # so the liability horizon must extend to at least year 50.
    horizon_years: int = 50
    curve_extrapolation_method: str = "flat_forward"

    # Optimization assumptions. Preserve current model constraints.
    minimum_high_quality_weight: float = 0.60
    maximum_corporate_weight: float = 0.30
    maximum_single_instrument_weight: float = 0.15
    maximum_single_issuer_weight: float = 0.15
    minimum_invested_fraction: float = 0.995

    # Preserve the current QP objective weights.
    gamma_dv01: float = 150.0
    eta_pv: float = 8.0

    # IRS overlay candidates from the liquid EUR swap curve.
    irs_candidate_tenors: tuple[int, ...] = (15, 20, 25, 30)

    @property
    def initial_account_value_eur(self) -> float:
        return self.policyholders * self.initial_account_value_per_policyholder

    @property
    def annual_contribution_eur(self) -> float:
        return self.policyholders * self.annual_contribution_per_policyholder

    @property
    def first_benefit_year(self) -> int:
        return self.contribution_years + self.deferral_after_last_contribution_years


def pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def eur_bn(value: float) -> str:
    return f"EUR {value / EUR_BN:,.3f}bn"


def eur_mn(value: float) -> str:
    return f"EUR {value / EUR_MN:,.2f}m"


def _match_key(name: str) -> str:
    """Loose key for a workbook name: lower-case stem, spaces/underscores
    collapsed, a trailing ' (1)' download-copy suffix removed."""

    stem = Path(name).stem.lower()
    stem = re.sub(r"\s*\(\d+\)\s*$", "", stem)
    stem = re.sub(r"[\s_]+", " ", stem).strip()
    return stem


def resolve_input_file(filename: str) -> Path:
    """Find an input workbook. Looks in Data/ first, then a lower-case data/ and
    the project root. An exact name wins; failing that it matches the name
    case-insensitively and tolerates a trailing ' (1)' copy suffix, so a file
    that was renamed slightly or moved into Data/ still resolves."""

    exact = [directory / filename for directory in INPUT_SEARCH_DIRS]
    for candidate in exact:
        if candidate.exists():
            return candidate

    wanted = _match_key(filename)
    for directory in INPUT_SEARCH_DIRS:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.glob("*.xls*")):
            if _match_key(candidate.name) == wanted:
                return candidate

    raise FileNotFoundError(
        f"Required input file not found: {filename}. Looked (exact then fuzzy) in: "
        + ", ".join(str(directory) for directory in INPUT_SEARCH_DIRS)
    )


def require_valid_shares(assumptions: Assumptions) -> None:
    if assumptions.lump_sum_share < 0 or assumptions.pension_share < 0:
        raise ValueError("Policyholder choice shares must be non-negative.")
    if abs(assumptions.lump_sum_share + assumptions.pension_share - 1.0) > 1e-9:
        raise ValueError("lump_sum_share + pension_share must equal 1.0.")


# EXCEL PARSING AND DATE NORMALIZATION


def excel_serial_to_date(value: float) -> date:
    # Excel's 1900 system is represented by openpyxl/pandas as 1899-12-30.
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()


def normalized_weekday_label(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:2]


def swapped_month_day(candidate: date) -> date | None:
    if candidate.month > 12 or candidate.day > 12:
        return None
    try:
        swapped = date(candidate.year, candidate.day, candidate.month)
    except ValueError:
        return None
    if swapped == candidate:
        return None
    return swapped


def unique_dates(candidates: list[date]) -> list[date]:
    seen: set[date] = set()
    result: list[date] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def date_candidates(raw_value: object) -> tuple[list[date], date | None]:
    """Return possible dates and the initial parse before correction."""

    if raw_value is None or (isinstance(raw_value, float) and math.isnan(raw_value)):
        return [], None

    candidates: list[date] = []
    initial: date | None = None

    if isinstance(raw_value, datetime):
        initial = raw_value.date()
        candidates.append(initial)
    elif isinstance(raw_value, date):
        initial = raw_value
        candidates.append(initial)
    elif isinstance(raw_value, (int, float)):
        initial = excel_serial_to_date(float(raw_value))
        candidates.append(initial)
    else:
        text = str(raw_value).strip()
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                if initial is None:
                    initial = parsed
                candidates.append(parsed)
            except ValueError:
                pass

    for candidate in list(candidates):
        swapped = swapped_month_day(candidate)
        if swapped is not None:
            candidates.append(swapped)

    return unique_dates(candidates), initial


def choose_bloomberg_date(
    raw_value: object,
    weekday_value: object,
    valuation_date: date,
    context: str,
    date_corrections: list[str],
) -> date:
    """Choose the date consistent with Bloomberg weekday labels and valuation date."""

    candidates, initial = date_candidates(raw_value)
    if not candidates:
        raise ValueError(f"Could not parse date for {context}: {raw_value!r}")

    weekday_label = normalized_weekday_label(weekday_value)
    expected_weekday = WEEKDAY_TO_INT.get(weekday_label or "")

    def score(candidate: date) -> tuple[int, int, int]:
        weekday_score = 0
        if expected_weekday is not None:
            weekday_score = 100 if candidate.weekday() == expected_weekday else -100
        valuation_score = 20 if candidate <= valuation_date else -1_000
        closeness = -abs((valuation_date - candidate).days)
        return weekday_score, valuation_score, closeness

    chosen = max(candidates, key=score)

    if expected_weekday is not None and chosen.weekday() != expected_weekday:
        raise ValueError(
            f"Date parsing failed weekday validation for {context}: "
            f"raw={raw_value!r}, weekday={weekday_value!r}, chosen={chosen}"
        )
    if chosen > valuation_date:
        raise ValueError(f"Date parsing produced future date for {context}: {chosen}")

    if initial is not None and chosen != initial:
        date_corrections.append(
            f"{context}: {initial.isoformat()} -> {chosen.isoformat()} "
            f"using weekday {weekday_label}"
        )

    return chosen



# EXCEL MARKET DATA INGESTION



def parse_tenor_years(header: object) -> int | None:
    if header is None:
        return None
    text = str(header).strip()
    if not text:
        return None

    direct = re.search(r"(\d+)\s*yr", text, flags=re.IGNORECASE)
    if direct:
        return int(direct.group(1))

    usd = re.search(r"USOSFR(\d+)", text, flags=re.IGNORECASE)
    if usd:
        return int(usd.group(1))

    return None


def to_float(value: object, context: str) -> float:
    if value is None or pd.isna(value):
        raise ValueError(f"Missing numeric value for {context}.")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip().replace(",", "")
        result = float(text)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite numeric value for {context}: {value!r}")
    return result


def is_missing(value: object) -> bool:
    return value is None or pd.isna(value)


def normalize_swap_curve(
    path: Path,
    currency: str,
    assumptions: Assumptions,
    date_corrections: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, date]:
    """Normalize Bloomberg swap quotes and bootstrap annual discount factors."""

    valuation_date = date.fromisoformat(assumptions.valuation_date)
    sheet = pd.read_excel(path, header=None, engine="openpyxl")

    tenor_blocks: list[tuple[int, int]] = []
    for column in range(sheet.shape[1]):
        tenor = parse_tenor_years(sheet.iat[0, column])
        if tenor is not None:
            tenor_blocks.append((column, tenor))

    if not tenor_blocks:
        raise ValueError(f"No swap tenor blocks found in {path.name}.")

    rows: list[dict[str, object]] = []
    for rate_column, tenor in tenor_blocks:
        day_column = rate_column - 2
        date_column = rate_column - 1
        if day_column < 0 or date_column < 0:
            raise ValueError(f"Invalid swap block structure for tenor {tenor} in {path.name}.")

        for row_index in range(1, len(sheet)):
            row_number = row_index + 1
            raw_quote = sheet.iat[row_index, rate_column]
            raw_date = sheet.iat[row_index, date_column]
            weekday = sheet.iat[row_index, day_column]
            if is_missing(raw_quote) or is_missing(raw_date) or is_missing(weekday):
                continue

            raw_quote_float = to_float(raw_quote, f"{currency} swap {tenor}Y row {row_number}")
            rate_decimal = raw_quote_float / 10_000_000.0
            if not (0.0 < rate_decimal < 0.15):
                raise ValueError(
                    f"Unrealistic {currency} swap rate after normalization: "
                    f"tenor={tenor}Y raw={raw_quote_float} decimal={rate_decimal}"
                )

            quote_date = choose_bloomberg_date(
                raw_date,
                weekday,
                valuation_date,
                f"{currency} swap {tenor}Y row {row_number}",
                date_corrections,
            )

            rows.append(
                {
                    "currency": currency,
                    "quote_date": quote_date.isoformat(),
                    "weekday": normalized_weekday_label(weekday),
                    "tenor_years": tenor,
                    "raw_quote": raw_quote_float,
                    "rate_decimal": rate_decimal,
                    "rate_percent": 100.0 * rate_decimal,
                    "normalization": "raw / 10,000,000",
                    "source_file": path.name,
                }
            )
            break

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        raise ValueError(f"No usable swap quotes found in {path.name}.")

    long_df["quote_date_obj"] = pd.to_datetime(long_df["quote_date"]).dt.date
    required_tenors = sorted(long_df["tenor_years"].unique())
    counts = long_df.groupby("quote_date_obj")["tenor_years"].nunique()
    common_dates = [
        quote_date
        for quote_date, count in counts.items()
        if count == len(required_tenors) and quote_date <= valuation_date
    ]
    if not common_dates:
        max_count = int(counts.max())
        common_dates = [
            quote_date
            for quote_date, count in counts.items()
            if count == max_count and quote_date <= valuation_date
        ]
    curve_date = max(common_dates)

    latest = (
        long_df[long_df["quote_date_obj"] == curve_date]
        .sort_values("tenor_years")
        .drop_duplicates("tenor_years", keep="last")
        .reset_index(drop=True)
    )

    annual_curve = build_bootstrapped_curve(
        latest=latest,
        currency=currency,
        curve_date=curve_date,
        assumptions=assumptions,
    )

    return long_df.drop(columns=["quote_date_obj"]), latest.drop(columns=["quote_date_obj"]), annual_curve, curve_date


def build_bootstrapped_curve(
    latest: pd.DataFrame,
    currency: str,
    curve_date: date,
    assumptions: Assumptions,
) -> pd.DataFrame:
    """Bootstrap annual discount factors from annual-pay par swap rates."""

    quoted_tenors = latest["tenor_years"].to_numpy(dtype=float)
    quoted_rates = latest["rate_decimal"].to_numpy(dtype=float)
    annual_tenors = np.arange(1, 31, dtype=int)
    annual_par_rates = np.interp(annual_tenors, quoted_tenors, quoted_rates)

    discount_factors: list[float] = []
    for tenor, par_rate in zip(annual_tenors, annual_par_rates):
        if tenor == 1:
            df_n = 1.0 / (1.0 + par_rate)
        else:
            df_n = (1.0 - par_rate * sum(discount_factors)) / (1.0 + par_rate)
        if df_n <= 0.0 or not math.isfinite(df_n):
            raise ValueError(
                f"Invalid bootstrapped discount factor for {currency} {tenor}Y: {df_n}"
            )
        discount_factors.append(float(df_n))

    discount_array = np.asarray(discount_factors, dtype=float)
    zero_continuous = -np.log(discount_array) / annual_tenors
    zero_annual = discount_array ** (-1.0 / annual_tenors) - 1.0
    quoted_set = {int(x) for x in quoted_tenors}

    return pd.DataFrame(
        {
            "currency": currency,
            "maturity_years": annual_tenors,
            "par_rate": annual_par_rates,
            "discount_factor": discount_array,
            "zero_rate_continuous": zero_continuous,
            "zero_rate_annual": zero_annual,
            "curve_date": curve_date.isoformat(),
            "quoted_input_tenor": [int(t) in quoted_set for t in annual_tenors],
            "curve_method": "annual par swap bootstrap with linear par-rate interpolation",
            "extrapolation_method": assumptions.curve_extrapolation_method,
            "source": "Bloomberg Excel swap curve supplied in project folder",
        }
    )


def normalize_eurusd(
    path: Path,
    assumptions: Assumptions,
    date_corrections: list[str],
) -> tuple[pd.DataFrame, date]:
    """Normalize EURUSD quotes. Loaded for future use; not used in EUR optimizer."""

    valuation_date = date.fromisoformat(assumptions.valuation_date)
    sheet = pd.read_excel(path, header=None, engine="openpyxl")

    rows: list[dict[str, object]] = []
    for row_index in range(len(sheet)):
        row_number = row_index + 1
        weekday = sheet.iat[row_index, 0]
        raw_date = sheet.iat[row_index, 1]
        raw_quote = sheet.iat[row_index, 2]
        if is_missing(weekday) or is_missing(raw_date) or is_missing(raw_quote):
            continue

        raw_quote_float = to_float(raw_quote, f"EURUSD row {row_number}")
        eurusd = raw_quote_float / 10_000.0
        if not (0.5 < eurusd < 2.0):
            raise ValueError(f"Unrealistic EURUSD quote after normalization: {eurusd}")

        quote_date = choose_bloomberg_date(
            raw_date,
            weekday,
            valuation_date,
            f"EURUSD row {row_number}",
            date_corrections,
        )

        rows.append(
            {
                "quote_date": quote_date.isoformat(),
                "weekday": normalized_weekday_label(weekday),
                "raw_quote": raw_quote_float,
                "eurusd": eurusd,
                "normalization": "raw / 10,000",
                "used_in_eur_fixed_income_optimizer": False,
                "source_file": path.name,
            }
        )
        break

    eurusd_df = pd.DataFrame(rows)
    if eurusd_df.empty:
        raise ValueError(f"No usable EURUSD quotes found in {path.name}.")

    eurusd_df["quote_date_obj"] = pd.to_datetime(eurusd_df["quote_date"]).dt.date
    latest_date = max(
        quote_date
        for quote_date in eurusd_df["quote_date_obj"].unique()
        if quote_date <= valuation_date
    )
    return eurusd_df.drop(columns=["quote_date_obj"]), latest_date



# FIXED-INCOME FROM BLOOMBERG-STYLE EXCEL


def clean_instrument_name(value: object) -> str:
    return str(value).replace("\xa0", " ").strip()


def parse_maturity_date_from_instrument(instrument: str, maturity_year: int) -> date:
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", instrument)
    if not match:
        raise ValueError(f"Could not parse exact maturity date from instrument: {instrument}")

    month = int(match.group(1))
    day = int(match.group(2))
    raw_year = int(match.group(3))
    if raw_year < 100:
        full_year = (int(maturity_year) // 100) * 100 + raw_year
    else:
        full_year = raw_year

    maturity = date(full_year, month, day)
    if abs(maturity.year - int(maturity_year)) > 1:
        raise ValueError(
            f"Maturity-year validation failed for {instrument}: "
            f"name date={maturity}, metadata year={maturity_year}"
        )
    return maturity


def infer_issuer_and_category(instrument: str) -> tuple[str, str]:
    """Infer issuer/category from the Bloomberg ticker prefix for constraints."""

    prefix = instrument.upper().split()[0]
    mapping = {
        "DBR": ("Federal Republic of Germany", "Gov"),
        "EU": ("European Union", "SSA"),
        "NETHER": ("Kingdom of the Netherlands", "Gov"),
        "RFGB": ("Republic of Finland", "Gov"),
        "RAGB": ("Republic of Austria", "Gov"),
        "ITALY": ("Republic of Italy", "Gov"),
        "BGB": ("Kingdom of Belgium", "Gov"),
        "RENTEN": ("Rentenbank", "SSA"),
        "LGB": ("Grand Duchy of Luxembourg", "Gov"),
        "KFW": ("KfW", "SSA"),
    }
    return mapping.get(prefix, (f"not supplied: {prefix}", "Unknown"))


def parse_fixed_income_basket(
    path: Path,
    assumptions: Assumptions,
    date_corrections: list[str],
) -> pd.DataFrame:
    """Parse repeating 5-column bond blocks from Fixed Income Basket.xlsx."""

    valuation = date.fromisoformat(assumptions.valuation_date)
    sheet = pd.read_excel(path, header=None, engine="openpyxl")

    rows: list[dict[str, object]] = []
    for start_column in range(0, sheet.shape[1], 5):
        instrument_cell = start_column + 2
        coupon_cell = start_column + 3
        maturity_year_cell = start_column + 4
        if maturity_year_cell >= sheet.shape[1]:
            continue

        raw_instrument = sheet.iat[0, instrument_cell]
        if is_missing(raw_instrument):
            continue

        instrument = clean_instrument_name(raw_instrument)
        coupon = to_float(sheet.iat[0, coupon_cell], f"{instrument} coupon")
        maturity_year = int(to_float(sheet.iat[0, maturity_year_cell], f"{instrument} maturity year"))
        maturity_date = parse_maturity_date_from_instrument(instrument, maturity_year)
        years_to_maturity = max(0.0, (maturity_date - valuation).days / 365.25)
        issuer, category = infer_issuer_and_category(instrument)

        latest_price: dict[str, object] | None = None
        usable = True
        exclusion_reason = ""

        for row_index in range(1, len(sheet)):
            row_number = row_index + 1
            weekday = sheet.iat[row_index, start_column]
            raw_date = sheet.iat[row_index, start_column + 1]
            raw_price = sheet.iat[row_index, instrument_cell]
            if is_missing(weekday) or is_missing(raw_date):
                continue
            if is_missing(raw_price):
                continue

            quote_date = choose_bloomberg_date(
                raw_date,
                weekday,
                valuation,
                f"{instrument} price row {row_number}",
                date_corrections,
            )
            if quote_date > valuation:
                continue

            raw_price_float = to_float(raw_price, f"{instrument} price row {row_number}")
            price_per_100 = raw_price_float / 1_000.0
            if not (20.0 < price_per_100 < 200.0):
                usable = False
                exclusion_reason = f"unrealistic normalized price {price_per_100:.3f}"
                continue

            if latest_price is None or quote_date > latest_price["quote_date"]:
                latest_price = {
                    "quote_date": quote_date,
                    "raw_price": raw_price_float,
                    "market_price_per_100": price_per_100,
                }
                break

        if latest_price is None:
            usable = False
            exclusion_reason = "missing usable market price"
            quote_date_text = ""
            raw_price_value = np.nan
            market_price_per_100 = np.nan
            staleness_days = np.nan
        else:
            quote_date_text = latest_price["quote_date"].isoformat()
            raw_price_value = float(latest_price["raw_price"])
            market_price_per_100 = float(latest_price["market_price_per_100"])
            staleness_days = (valuation - latest_price["quote_date"]).days

        rows.append(
            {
                "instrument": instrument,
                "issuer": issuer,
                "category": category,
                "isin": "",
                "rating": "",
                "coupon": coupon,
                "maturity_year_metadata": maturity_year,
                "maturity_date": maturity_date.isoformat(),
                "years_to_maturity": years_to_maturity,
                "quote_date": quote_date_text,
                "raw_price": raw_price_value,
                "market_price_per_100": market_price_per_100,
                "market_price_per_1_nominal": market_price_per_100 / 100.0
                if math.isfinite(float(market_price_per_100))
                else np.nan,
                "staleness_days": staleness_days,
                "usable_for_optimizer": usable,
                "exclusion_reason": exclusion_reason,
                "price_normalization": "raw / 1,000",
                "coupon_normalization": "already decimal in workbook",
                "source_file": path.name,
            }
        )

    universe = pd.DataFrame(rows)
    if universe.empty:
        raise ValueError(f"No fixed-income instruments found in {path.name}.")
    return universe


# CURVE, PV, DURATION AND DV01 FUNCTIONS


def base_discount_factor(curve: pd.DataFrame, maturity_years: float | np.ndarray) -> float | np.ndarray:
    """Interpolate log discount factors and flat-forward extrapolate beyond 30Y."""

    maturity_array = np.asarray(maturity_years, dtype=float)
    curve_maturities = curve["maturity_years"].to_numpy(dtype=float)
    curve_dfs = curve["discount_factor"].to_numpy(dtype=float)

    x = np.concatenate(([0.0], curve_maturities))
    log_df = np.concatenate(([0.0], np.log(curve_dfs)))
    max_maturity = float(curve_maturities.max())
    last_df = float(curve_dfs[-1])
    previous_df = float(curve_dfs[-2])
    last_forward = -math.log(last_df / previous_df)

    clipped = np.clip(maturity_array, 0.0, max_maturity)
    interpolated_log_df = np.interp(clipped, x, log_df)
    result = np.exp(interpolated_log_df)

    beyond = maturity_array > max_maturity
    if np.any(beyond):
        result = np.asarray(result, dtype=float)
        result[beyond] = last_df * np.exp(-last_forward * (maturity_array[beyond] - max_maturity))

    if np.isscalar(maturity_years):
        return float(np.asarray(result))
    return result


def zero_rate(curve: pd.DataFrame, maturity_years: float | np.ndarray) -> float | np.ndarray:
    maturity_array = np.asarray(maturity_years, dtype=float)
    dfs = base_discount_factor(curve, maturity_array)
    rates = np.where(maturity_array > 0.0, -np.log(dfs) / maturity_array, 0.0)
    if np.isscalar(maturity_years):
        return float(np.asarray(rates))
    return rates


def discount_factor(
    curve: pd.DataFrame,
    maturity_years: float | np.ndarray,
    spread: float = 0.0,
    parallel_shift_bps: float = 0.0,
) -> float | np.ndarray:
    maturity_array = np.asarray(maturity_years, dtype=float)
    base_df = base_discount_factor(curve, maturity_array)
    shifted = base_df * np.exp(-(spread + parallel_shift_bps / 10_000.0) * maturity_array)
    if np.isscalar(maturity_years):
        return float(np.asarray(shifted))
    return shifted


def pv(cashflows: np.ndarray, curve: pd.DataFrame, spread: float = 0.0, shift_bps: float = 0.0) -> float:
    years = np.arange(1, len(cashflows) + 1, dtype=float)
    return float(np.sum(cashflows * discount_factor(curve, years, spread, shift_bps)))


def pv_by_year(cashflows: np.ndarray, curve: pd.DataFrame) -> np.ndarray:
    years = np.arange(1, len(cashflows) + 1, dtype=float)
    return cashflows * discount_factor(curve, years)


def macaulay_duration(cashflows: np.ndarray, curve: pd.DataFrame, spread: float = 0.0) -> float:
    years = np.arange(1, len(cashflows) + 1, dtype=float)
    pv_cashflows = cashflows * discount_factor(curve, years, spread)
    total_pv = float(np.sum(pv_cashflows))
    if total_pv <= 0.0:
        return 0.0
    return float(np.sum(years * pv_cashflows) / total_pv)


def dv01(cashflows: np.ndarray, curve: pd.DataFrame, spread: float = 0.0) -> float:
    down = pv(cashflows, curve, spread=spread, shift_bps=-1.0)
    up = pv(cashflows, curve, spread=spread, shift_bps=1.0)
    return float((down - up) / 2.0)


def pv_times(
    times: np.ndarray,
    cashflows: np.ndarray,
    curve: pd.DataFrame,
    spread: float = 0.0,
    shift_bps: float = 0.0,
) -> float:
    return float(np.sum(cashflows * discount_factor(curve, times, spread, shift_bps)))



# BUILD THE LIABILITY CASH FLOWS



def guaranteed_accumulated_value(assumptions: Assumptions) -> float:
    """Guaranteed account value at projection year 15."""

    benefit_year = assumptions.first_benefit_year
    initial_fv = assumptions.initial_account_value_eur * (
        1.0 + assumptions.guaranteed_rate
    ) ** benefit_year

    contribution_fv = 0.0
    for payment_year in range(1, assumptions.contribution_years + 1):
        contribution_fv += assumptions.annual_contribution_eur * (
            1.0 + assumptions.guaranteed_rate
        ) ** (benefit_year - payment_year)

    return float(initial_fv + contribution_fv)


def load_pension_cashflows(path: Path, assumptions: Assumptions) -> pd.DataFrame:
    """Load mortality-weighted pension cash flows from pension_liability_results.xlsx."""

    pension = pd.read_excel(path)
    required = {
        "Year",
        "Age",
        "Male_Alive",
        "Female_Alive",
        "Total_Alive",
        "Total_Deaths",
        "Pension_Units",
        "Expected_Annual_Pension_Cashflow",
        "Discount_Factor",
        "PV_Pension_Cashflow",
    }
    missing = required.difference(pension.columns)
    if missing:
        raise ValueError(f"Missing pension workbook columns: {sorted(missing)}")

    for column in required:
        pension[column] = pd.to_numeric(pension[column], errors="raise")

    pension = pension.sort_values("Year").reset_index(drop=True)
    pension["projection_year"] = assumptions.first_benefit_year + pension["Year"].astype(int)
    pension["base_100pct_pension_cf_eur"] = pension["Expected_Annual_Pension_Cashflow"]
    pension["selected_pension_cf_eur"] = assumptions.pension_share * pension[
        "base_100pct_pension_cf_eur"
    ]
    pension["timing_convention"] = "projection_year = first_benefit_year + pension_year"
    pension["source_file"] = path.name
    return pension


def validate_pension_file(
    pension: pd.DataFrame,
    assumptions: Assumptions,
    accumulated_value: float,
) -> dict[str, float | int | bool]:
    pension_years = int(len(pension))
    first_age = int(pension["Age"].min())
    final_age = int(pension["Age"].max())
    pv_at_retirement = float(pension["PV_Pension_Cashflow"].sum())
    pv_validation_error = pv_at_retirement - accumulated_value

    first_ten_units_ok = bool(
        np.allclose(pension.loc[pension["Year"] <= 10, "Pension_Units"], assumptions.policyholders)
    )
    tail_units = pension.loc[pension["Year"] > 10]
    tail_units_ok = bool(np.allclose(tail_units["Pension_Units"], tail_units["Total_Alive"]))

    if pension_years != 35 or first_age != 65 or final_age != 99:
        raise ValueError(
            f"Unexpected pension workbook coverage: years={pension_years}, ages={first_age}-{final_age}"
        )
    if not first_ten_units_ok:
        raise ValueError("Pension validation failed: years 1-10 should have 100,000 pension units.")
    if not tail_units_ok:
        raise ValueError("Pension validation failed: after year 10 pension units should equal alive lives.")
    if abs(pv_validation_error) > 2_000_000:
        raise ValueError(
            f"Pension PV validation failed: workbook PV={pv_at_retirement}, "
            f"guaranteed account value={accumulated_value}"
        )

    return {
        "pension_years": pension_years,
        "first_age": first_age,
        "final_age": final_age,
        "pv_at_retirement": pv_at_retirement,
        "pv_validation_error": pv_validation_error,
        "first_ten_units_ok": first_ten_units_ok,
        "tail_units_ok": tail_units_ok,
    }


def build_liability_cashflows(
    assumptions: Assumptions,
    pension: pd.DataFrame,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Create lump-sum plus mortality-weighted pension liability cash flows."""

    require_valid_shares(assumptions)
    max_projection_year = int(max(assumptions.horizon_years, pension["projection_year"].max()))
    cashflows = np.zeros(max_projection_year, dtype=float)

    accumulated = guaranteed_accumulated_value(assumptions)
    lump_sum = accumulated * assumptions.lump_sum_share
    cashflows[assumptions.first_benefit_year - 1] += lump_sum

    pension_rows: list[dict[str, object]] = []
    for _, row in pension.iterrows():
        projection_year = int(row["projection_year"])
        pension_cf = float(assumptions.pension_share * row["Expected_Annual_Pension_Cashflow"])
        cashflows[projection_year - 1] += pension_cf
        pension_rows.append(
            {
                "pension_year": int(row["Year"]),
                "age": int(row["Age"]),
                "projection_year": projection_year,
                "expected_annual_pension_cashflow_100pct_eur": float(
                    row["Expected_Annual_Pension_Cashflow"]
                ),
                "selected_pension_cashflow_eur": pension_cf,
            }
        )

    liability_schedule = pd.DataFrame(
        {
            "projection_year": np.arange(1, len(cashflows) + 1, dtype=int),
            "liability_cf_eur": cashflows,
            "lump_sum_cf_eur": 0.0,
            "pension_cf_eur": 0.0,
        }
    )
    liability_schedule.loc[
        liability_schedule["projection_year"] == assumptions.first_benefit_year,
        "lump_sum_cf_eur",
    ] = lump_sum

    pension_detail = pd.DataFrame(pension_rows)
    for _, row in pension_detail.iterrows():
        mask = liability_schedule["projection_year"] == int(row["projection_year"])
        liability_schedule.loc[mask, "pension_cf_eur"] += float(row["selected_pension_cashflow_eur"])

    return cashflows, liability_schedule


def liability_analytics(liability_cf: np.ndarray, curve: pd.DataFrame) -> dict[str, float]:
    years = np.arange(1, len(liability_cf) + 1, dtype=int)
    discounted = pv_by_year(liability_cf, curve)
    pv_total = float(np.sum(discounted))
    pv_inside_30 = float(np.sum(discounted[years <= 30]))
    pv_beyond_30 = float(np.sum(discounted[years > 30]))
    return {
        "pv": pv_total,
        "duration": macaulay_duration(liability_cf, curve),
        "dv01": dv01(liability_cf, curve),
        "pv_inside_30": pv_inside_30,
        "pv_beyond_30": pv_beyond_30,
        "pv_beyond_30_percent": pv_beyond_30 / pv_total if pv_total else 0.0,
    }


def funding_analysis(assumptions: Assumptions, liability_pv: float, curve: pd.DataFrame) -> dict[str, float]:
    premium_cf = np.zeros(assumptions.horizon_years, dtype=float)
    premium_cf[: assumptions.contribution_years] = assumptions.annual_contribution_eur
    pv_future_premiums = pv(premium_cf, curve)
    return {
        "pv_current_assets": assumptions.current_available_assets_eur,
        "pv_future_premiums": pv_future_premiums,
        "pv_benefit_liabilities": liability_pv,
        "net_funding_position": assumptions.current_available_assets_eur
        + pv_future_premiums
        - liability_pv,
    }


def policyholder_choice_scenarios(
    pension: pd.DataFrame,
    curve: pd.DataFrame,
    assumptions: Assumptions,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for lump_share, pension_share in [(1.0, 0.0), (0.70, 0.30), (0.50, 0.50), (0.30, 0.70), (0.0, 1.0)]:
        scenario_assumptions = replace(
            assumptions,
            lump_sum_share=lump_share,
            pension_share=pension_share,
        )
        liability_cf, _ = build_liability_cashflows(scenario_assumptions, pension)
        analytics = liability_analytics(liability_cf, curve)
        rows.append(
            {
                "lump_sum_share": lump_share,
                "pension_share": pension_share,
                "liability_pv_eur": analytics["pv"],
                "liability_duration": analytics["duration"],
                "liability_dv01_eur_per_bp": analytics["dv01"],
                "pv_beyond_30_eur": analytics["pv_beyond_30"],
                "pv_beyond_30_percent": analytics["pv_beyond_30_percent"],
            }
        )
    return pd.DataFrame(rows)


# CALCULATE BOND ANALYTICS FROM OBSERVED MARKET PRICES



def bond_payment_schedule(
    coupon_rate: float,
    maturity_date_text: str,
    valuation_date_text: str,
) -> tuple[np.ndarray, np.ndarray]:
    valuation = date.fromisoformat(valuation_date_text)
    maturity = date.fromisoformat(maturity_date_text)

    payment_dates: list[date] = []
    for year in range(valuation.year, maturity.year + 1):
        try:
            payment_date = date(year, maturity.month, maturity.day)
        except ValueError:
            payment_date = date(year, maturity.month, 28)
        if valuation < payment_date <= maturity:
            payment_dates.append(payment_date)

    if not payment_dates:
        raise ValueError(f"No future payment dates for maturity {maturity_date_text}.")

    times = np.asarray([(payment_date - valuation).days / 365.25 for payment_date in payment_dates])
    cashflows = np.full(len(payment_dates), coupon_rate, dtype=float)
    cashflows[-1] += 1.0
    return times, cashflows


def price_from_curve_times(
    cashflows: np.ndarray,
    times: np.ndarray,
    curve: pd.DataFrame,
    spread: float,
    shift_bps: float = 0.0,
) -> float:
    return pv_times(times, cashflows, curve, spread=spread, shift_bps=shift_bps)


def price_from_ytm_times(cashflows: np.ndarray, times: np.ndarray, ytm: float) -> float:
    return float(np.sum(cashflows / (1.0 + ytm) ** times))


def solve_yield_to_maturity_times(cashflows: np.ndarray, times: np.ndarray, price: float) -> float:
    def objective(yield_rate: float) -> float:
        return price_from_ytm_times(cashflows, times, yield_rate) - price

    return float(brentq(objective, -0.95, 1.0, maxiter=500))


def solve_z_spread(cashflows: np.ndarray, times: np.ndarray, curve: pd.DataFrame, price: float) -> float:
    def objective(spread: float) -> float:
        return price_from_curve_times(cashflows, times, curve, spread) - price

    low = -0.50
    high = 0.50
    f_low = objective(low)
    f_high = objective(high)
    for _ in range(10):
        if f_low * f_high <= 0.0:
            return float(brentq(objective, low, high, maxiter=500))
        low -= 0.50
        high += 0.50
        f_low = objective(low)
        f_high = objective(high)
    raise ValueError("Could not infer z-spread from observed market price.")


def bond_dv01_per_nominal(
    cashflows: np.ndarray,
    times: np.ndarray,
    curve: pd.DataFrame,
    z_spread: float,
) -> float:
    down = price_from_curve_times(cashflows, times, curve, z_spread, shift_bps=-1.0)
    up = price_from_curve_times(cashflows, times, curve, z_spread, shift_bps=1.0)
    return float((down - up) / 2.0)


def bond_yield_dv01_per_nominal(cashflows: np.ndarray, times: np.ndarray, ytm: float) -> float:
    down = price_from_ytm_times(cashflows, times, ytm - BASIS_POINT)
    up = price_from_ytm_times(cashflows, times, ytm + BASIS_POINT)
    return float((down - up) / 2.0)


def bond_convexity(cashflows: np.ndarray, times: np.ndarray, ytm: float, price: float) -> float:
    numerator = np.sum(cashflows * times * (times + 1.0) / (1.0 + ytm) ** (times + 2.0))
    return float(numerator / price)


def cashflows_to_projection_buckets(
    cashflows: np.ndarray,
    times: np.ndarray,
    price_per_1: float,
    horizon_years: int,
) -> np.ndarray:
    buckets = np.zeros(horizon_years, dtype=float)
    for cashflow, time in zip(cashflows, times):
        projection_year = int(math.ceil(float(time)))
        if 1 <= projection_year <= horizon_years:
            buckets[projection_year - 1] += float(cashflow) / price_per_1
    return buckets


def calculate_bond_analytics(
    universe: pd.DataFrame,
    curve: pd.DataFrame,
    assumptions: Assumptions,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Calculate observed-price YTM, curve DV01, convexity and CF schedule."""

    usable = universe[universe["usable_for_optimizer"]].copy().reset_index(drop=True)
    if usable.empty:
        raise ValueError("No usable fixed-income instruments with observed market prices.")

    analytics_rows: list[dict[str, object]] = []
    cashflow_columns: list[np.ndarray] = []

    for _, row in usable.iterrows():
        coupon_rate = float(row["coupon"])
        price_per_1 = float(row["market_price_per_1_nominal"])
        times, cashflows = bond_payment_schedule(
            coupon_rate,
            str(row["maturity_date"]),
            assumptions.valuation_date,
        )

        ytm = solve_yield_to_maturity_times(cashflows, times, price_per_1)
        z_spread = solve_z_spread(cashflows, times, curve, price_per_1)
        pv_cashflows = cashflows * discount_factor(curve, times, z_spread)
        duration = float(np.sum(times * pv_cashflows) / price_per_1)
        modified_duration = duration / (1.0 + ytm)
        curve_dv01_nominal = bond_dv01_per_nominal(cashflows, times, curve, z_spread)
        yield_dv01_nominal = bond_yield_dv01_per_nominal(cashflows, times, ytm)
        convexity = bond_convexity(cashflows, times, ytm, price_per_1)

        cashflow_columns.append(
            cashflows_to_projection_buckets(
                cashflows=cashflows,
                times=times,
                price_per_1=price_per_1,
                horizon_years=assumptions.horizon_years,
            )
        )

        analytics_rows.append(
            {
                "instrument": row["instrument"],
                "issuer": row["issuer"],
                "category": row["category"],
                "isin": row["isin"],
                "rating": row["rating"],
                "maturity_date": row["maturity_date"],
                "years_to_maturity": row["years_to_maturity"],
                "coupon": coupon_rate,
                "quote_date": row["quote_date"],
                "staleness_days": row["staleness_days"],
                "market_price_per_100": row["market_price_per_100"],
                "ytm": ytm,
                "z_spread": z_spread,
                "duration": duration,
                "modified_duration": modified_duration,
                "curve_dv01_per_100_nominal": curve_dv01_nominal * 100.0,
                "yield_dv01_per_100_nominal": yield_dv01_nominal * 100.0,
                "dv01_per_eur_invested": curve_dv01_nominal / price_per_1,
                "dv01_per_eur_1m": curve_dv01_nominal / price_per_1 * EUR_MN,
                "convexity": convexity,
                "pricing_data_label": "observed market price from Fixed Income Basket.xlsx",
                "usable_for_optimizer": True,
            }
        )

    analytics = pd.DataFrame(analytics_rows)
    asset_cf_matrix = np.column_stack(cashflow_columns)
    return analytics, asset_cf_matrix



# BUILD THE ASSET CASH-FLOW MATRIX



def explain_asset_matrix() -> None:
    print("ASSET CASH-FLOW MATRIX")
    print("x_i = EUR amount invested in bond i")
    print("C[t, i] = future cash flow at projection year t generated by EUR 1 invested in bond i")
    print("CF_A[t] = sum_i x_i * C[t, i]\n")



# FIXED-INCOME ALM QUADRATIC OPTIMIZATION



def solve_fixed_income_qp(
    C: np.ndarray,
    liability_cf_eur: np.ndarray,
    analytics: pd.DataFrame,
    assumptions: Assumptions,
    liability_dv01_eur_per_bp: float,
) -> dict[str, object]:
    """Solve the constrained fixed-income ALM QP."""

    n = C.shape[1]
    budget_bn = assumptions.current_available_assets_eur / EUR_BN
    target_investment_bn = assumptions.current_available_assets_eur / EUR_BN

    dv01_vector_mn_per_bn = analytics["dv01_per_eur_invested"].to_numpy(dtype=float) * EUR_BN / EUR_MN
    liability_dv01_mn = liability_dv01_eur_per_bp / EUR_MN

    sector = analytics["category"].to_numpy()
    high_quality_mask = np.isin(sector, ["Gov", "SSA", "Covered"]).astype(float)
    corporate_mask = (sector == "IG").astype(float)
    issuer_masks = [
        (analytics["issuer"].to_numpy() == issuer).astype(float)
        for issuer in sorted(analytics["issuer"].unique())
    ]

    tolerance_grid = [0.05, 0.10, 0.20, 0.25, 0.35, 0.50, 0.75, 1.00]

    for dv01_tolerance in tolerance_grid:
        # Decision variables:
        # x_bn[i] = EUR billions invested in bond i.
        # This is equivalent to x_i = EUR amount invested in bond i, but keeps
        # the QP numerically stable for the solver.
        x_bn = cp.Variable(n, nonneg=True)

        # Asset cash flows:
        # CF_A_t = sum_i x_i * CF_{i,t}
        asset_cf_bn = (C @ (x_bn * EUR_BN)) / EUR_BN

        # Asset DV01:
        # DV01_A = sum_i x_i * DV01_i_per_EUR_invested
        asset_dv01_mn = dv01_vector_mn_per_bn @ x_bn

        portfolio_value_bn = cp.sum(x_bn)

        # Objective:
        # Minimize cash-flow mismatch + DV01 mismatch + small PV/investment-use
        # penalty. All terms are scaled to avoid numerical issues.
        cf_mismatch = cp.sum_squares(asset_cf_bn - liability_cf_eur / EUR_BN)
        dv01_mismatch = cp.square(
            (asset_dv01_mn - liability_dv01_mn) / max(abs(liability_dv01_mn), 1.0)
        )
        pv_use_penalty = cp.square(portfolio_value_bn - target_investment_bn)

        objective = cp.Minimize(
            cf_mismatch
            + assumptions.gamma_dv01 * dv01_mismatch
            + assumptions.eta_pv * pv_use_penalty
        )

        # Constraints, in math:
        # 1. x_i >= 0
        # 2. sum_i x_i <= budget
        # 3. sum_i x_i >= minimum invested fraction * budget
        # 4. Gov + SSA + Covered >= 60% of invested portfolio
        # 5. IG corporate credit <= 30% of invested portfolio
        # 6. each instrument <= 15% of invested portfolio
        # 7. each issuer <= 15% of invested portfolio
        # 8. DV01_A within the tested tolerance band around DV01_L
        total = cp.sum(x_bn)
        constraints = [
            total <= budget_bn,
            total >= assumptions.minimum_invested_fraction * budget_bn,
            high_quality_mask @ x_bn >= assumptions.minimum_high_quality_weight * total,
            corporate_mask @ x_bn <= assumptions.maximum_corporate_weight * total,
            x_bn <= assumptions.maximum_single_instrument_weight * total,
            asset_dv01_mn >= (1.0 - dv01_tolerance) * liability_dv01_mn,
            asset_dv01_mn <= (1.0 + dv01_tolerance) * liability_dv01_mn,
        ]
        constraints.extend(
            issuer_mask @ x_bn <= assumptions.maximum_single_issuer_weight * total
            for issuer_mask in issuer_masks
        )

        # Solver:
        solver = "CLARABEL"
        problem = cp.Problem(objective, constraints)
        problem.solve(solver=cp.CLARABEL, verbose=False)

        if x_bn.value is not None and problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
            allocation_bn = np.maximum(np.asarray(x_bn.value, dtype=float), 0.0)
            allocation_eur = allocation_bn * EUR_BN
            asset_cf_bn_value = (C @ allocation_eur) / EUR_BN
            asset_dv01_mn_value = float(np.dot(dv01_vector_mn_per_bn, allocation_bn))
            cf_component = float(np.sum((asset_cf_bn_value - liability_cf_eur / EUR_BN) ** 2))
            raw_dv01_mismatch = (
                (asset_dv01_mn_value - liability_dv01_mn) / max(abs(liability_dv01_mn), 1.0)
            ) ** 2
            raw_pv_use_penalty = (float(np.sum(allocation_bn)) - target_investment_bn) ** 2
            return {
                "allocation_eur": allocation_eur,
                "status": problem.status,
                "objective_value": float(problem.value),
                "solver": solver,
                "dv01_tolerance": dv01_tolerance,
                "cf_component": cf_component,
                "dv01_component": assumptions.gamma_dv01 * float(raw_dv01_mismatch),
                "investment_use_component": assumptions.eta_pv * float(raw_pv_use_penalty),
                "target_investment_bn": target_investment_bn,
            }

    raise RuntimeError("No feasible solution found for the fixed-income QP.")



# PORTFOLIO AND IRS GAP



def portfolio_table(allocation_eur: np.ndarray, analytics: pd.DataFrame) -> pd.DataFrame:
    invested = float(np.sum(allocation_eur))
    table = analytics.copy()
    table["eur_allocation"] = allocation_eur
    table["eur_allocation_mn"] = table["eur_allocation"] / EUR_MN
    table["portfolio_weight"] = np.where(invested > 0.0, table["eur_allocation"] / invested, 0.0)
    table["dv01_contribution"] = table["eur_allocation"] * table["dv01_per_eur_invested"]
    table["dv01_contribution_mn"] = table["dv01_contribution"] / EUR_MN

    columns = [
        "instrument",
        "issuer",
        "category",
        "isin",
        "rating",
        "maturity_date",
        "years_to_maturity",
        "coupon",
        "quote_date",
        "staleness_days",
        "market_price_per_100",
        "ytm",
        "z_spread",
        "duration",
        "modified_duration",
        "dv01_per_eur_1m",
        "convexity",
        "eur_allocation",
        "eur_allocation_mn",
        "portfolio_weight",
        "dv01_contribution",
        "dv01_contribution_mn",
        "pricing_data_label",
    ]
    return table[columns].sort_values("eur_allocation", ascending=False)


def portfolio_metrics(allocation_eur: np.ndarray, analytics: pd.DataFrame) -> dict[str, float]:
    invested = float(np.sum(allocation_eur))
    weights = allocation_eur / invested if invested > 0.0 else np.zeros_like(allocation_eur)

    return {
        "value": invested,
        "yield": float(np.dot(weights, analytics["ytm"].to_numpy(dtype=float))),
        "duration": float(np.dot(weights, analytics["duration"].to_numpy(dtype=float))),
        "dv01": float(np.dot(allocation_eur, analytics["dv01_per_eur_invested"].to_numpy(dtype=float))),
    }


def par_swap_rate(curve: pd.DataFrame, tenor_years: int) -> float:
    years = np.arange(1, tenor_years + 1, dtype=float)
    dfs = discount_factor(curve, years)
    annuity = float(np.sum(dfs))
    return float((1.0 - dfs[-1]) / annuity)


def receive_fixed_swap_pv_per_eur(
    curve: pd.DataFrame,
    tenor_years: int,
    fixed_rate: float,
    shift_bps: float = 0.0,
) -> float:
    years = np.arange(1, tenor_years + 1, dtype=float)
    dfs = discount_factor(curve, years, parallel_shift_bps=shift_bps)
    fixed_leg = fixed_rate * float(np.sum(dfs))
    floating_leg = 1.0 - float(dfs[-1])
    return fixed_leg - floating_leg


def receive_fixed_swap_dv01_per_eur(curve: pd.DataFrame, tenor_years: int) -> float:
    fixed_rate = par_swap_rate(curve, tenor_years)
    down = receive_fixed_swap_pv_per_eur(curve, tenor_years, fixed_rate, shift_bps=-1.0)
    up = receive_fixed_swap_pv_per_eur(curve, tenor_years, fixed_rate, shift_bps=1.0)
    return float((down - up) / 2.0)


def calculate_irs_gap(
    portfolio_dv01: float,
    liability_dv01: float,
    liability_duration: float,
    curve: pd.DataFrame,
    assumptions: Assumptions,
) -> dict[str, object]:
    # User-facing definition requested:
    # DV01_Gap = DV01_A - DV01_L
    dv01_gap = portfolio_dv01 - liability_dv01
    candidates: list[dict[str, float | int | str]] = []

    for tenor in assumptions.irs_candidate_tenors:
        fixed_rate = par_swap_rate(curve, tenor)
        irs_dv01_per_eur = receive_fixed_swap_dv01_per_eur(curve, tenor)
        if irs_dv01_per_eur <= 0.0:
            continue

        if dv01_gap < 0.0:
            direction = "receive-fixed"
            signed_dv01 = irs_dv01_per_eur
            notional = -dv01_gap / irs_dv01_per_eur
        elif dv01_gap > 0.0:
            direction = "pay-fixed"
            signed_dv01 = -irs_dv01_per_eur
            notional = dv01_gap / irs_dv01_per_eur
        else:
            direction = "none"
            signed_dv01 = 0.0
            notional = 0.0

        residual_after_swap = dv01_gap + notional * signed_dv01
        candidates.append(
            {
                "direction": direction,
                "irs_tenor_years": tenor,
                "irs_par_fixed_rate": fixed_rate,
                "irs_dv01_per_eur": irs_dv01_per_eur,
                "irs_notional": abs(float(notional)),
                "residual_dv01_after_swap": residual_after_swap,
                "tenor_selection_score": abs(float(tenor) - liability_duration),
            }
        )

    if not candidates:
        raise ValueError("No valid IRS hedge candidates could be calculated.")

    best = min(
        candidates,
        key=lambda row: (
            abs(float(row["residual_dv01_after_swap"])),
            float(row["tenor_selection_score"]),
        ),
    )
    best["dv01_gap"] = dv01_gap
    best["candidate_table"] = pd.DataFrame(candidates)
    best["selection_basis"] = "lowest residual total DV01, then closest tenor to liability duration"
    return best



# OUTPUTS, VALIDATION REPORT AND CHARTS



def build_cashflow_matching_table(asset_cf: np.ndarray, liability_cf: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "projection_year": np.arange(1, len(liability_cf) + 1, dtype=int),
            "asset_cf_eur": asset_cf,
            "liability_cf_eur": liability_cf,
            "cashflow_mismatch_eur": asset_cf - liability_cf,
            "cumulative_asset_cf_eur": np.cumsum(asset_cf),
            "cumulative_liability_cf_eur": np.cumsum(liability_cf),
            "cumulative_mismatch_eur": np.cumsum(asset_cf - liability_cf),
        }
    )


def save_charts(cashflow_table: pd.DataFrame, results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(
        cashflow_table["projection_year"] - 0.18,
        cashflow_table["asset_cf_eur"] / EUR_BN,
        width=0.36,
        label="Asset cash flows",
    )
    ax.bar(
        cashflow_table["projection_year"] + 0.18,
        cashflow_table["liability_cf_eur"] / EUR_BN,
        width=0.36,
        label="Liability cash flows",
    )
    ax.set_title("Asset Cash Flows vs Liability Cash Flows")
    ax.set_xlabel("Projection year")
    ax.set_ylabel("EUR bn")
    ax.set_xlim(0, max(51, int(cashflow_table["projection_year"].max()) + 1))
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(results_dir / "asset_vs_liability_cashflows.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(
        cashflow_table["projection_year"],
        cashflow_table["cumulative_asset_cf_eur"] / EUR_BN,
        label="Cumulative asset cash flows",
    )
    ax.plot(
        cashflow_table["projection_year"],
        cashflow_table["cumulative_liability_cf_eur"] / EUR_BN,
        label="Cumulative liabilities",
    )
    ax.set_title("Cumulative Asset Cash Flows vs Cumulative Liabilities")
    ax.set_xlabel("Projection year")
    ax.set_ylabel("EUR bn")
    ax.set_xlim(0, max(51, int(cashflow_table["projection_year"].max()) + 1))
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(results_dir / "cumulative_asset_vs_liability_cashflows.png", dpi=180)
    plt.close(fig)


def build_data_validation_report(
    assumptions: Assumptions,
    input_paths: dict[str, Path],
    eur_latest: pd.DataFrame,
    eur_curve: pd.DataFrame,
    usd_latest: pd.DataFrame,
    eurusd: pd.DataFrame,
    universe: pd.DataFrame,
    pension: pd.DataFrame,
    pension_validation: dict[str, float | int | bool],
    liability: dict[str, float],
    funding: dict[str, float],
    date_corrections: list[str],
) -> str:
    usable = universe[universe["usable_for_optimizer"]]
    excluded = universe[~universe["usable_for_optimizer"]]
    eur_1y = eur_latest[eur_latest["tenor_years"] == 1].iloc[0]
    usd_1y = usd_latest[usd_latest["tenor_years"] == 1].iloc[0]
    fx_latest = eurusd.sort_values("quote_date").iloc[-1]
    dbr = universe[universe["instrument"].str.startswith("DBR 2.9")].iloc[0]

    correction_lines = date_corrections[:25]
    if len(date_corrections) > 25:
        correction_lines.append(f"... {len(date_corrections) - 25} additional date corrections not shown")

    excluded_lines = [
        f"- {row.instrument}: {row.exclusion_reason}"
        for row in excluded.itertuples(index=False)
    ]
    if not excluded_lines:
        excluded_lines = ["- none"]

    files_used = "\n".join(f"- {key}: {path}" for key, path in input_paths.items())
    corrections_text = "\n".join(f"- {line}" for line in correction_lines) if correction_lines else "- none"
    excluded_text = "\n".join(excluded_lines)

    return f"""==================================================
DATA VALIDATION
==================================================

Valuation date: {assumptions.valuation_date}

FILES USED:
{files_used}

NORMALIZATION APPLIED:
- EUR swap rates: raw / 10,000,000
- USD swap rates: raw / 10,000,000
- EURUSD spot: raw / 10,000
- Bond prices: raw / 1,000 to price per 100 nominal
- Bond coupons: already decimal in workbook
- Bond maturity dates: parsed from instrument name, maturity-year cell used as validation

DATE CORRECTIONS:
{corrections_text}

EUR swap curve:
raw 1Y = {float(eur_1y["raw_quote"]):.0f}
normalized = {pct(float(eur_1y["rate_decimal"]))}
latest common EUR curve date = {eur_curve["curve_date"].iloc[0]}
curve method = annual par swap bootstrap with linear par-rate interpolation
long-end extrapolation = {assumptions.curve_extrapolation_method} beyond 30Y

USD curve loaded: YES
USD raw 1Y = {float(usd_1y["raw_quote"]):.0f}
USD normalized 1Y = {pct(float(usd_1y["rate_decimal"]))}
Used in EUR Fixed Income optimization: NO

EURUSD loaded: YES
latest EURUSD = {float(fx_latest["eurusd"]):.4f} on {fx_latest["quote_date"]}
Used in EUR Fixed Income optimization: NO

Fixed Income:
instruments found = {len(universe)}
instruments with usable prices = {len(usable)}
excluded =
{excluded_text}

Example:
DBR 2056
coupon = {pct(float(dbr["coupon"]))}
maturity = {dbr["maturity_date"]}
market price = {float(dbr["market_price_per_100"]):.3f}

Pension:
pension years = {int(pension_validation["pension_years"])}
first age = {int(pension_validation["first_age"])}
final age = {int(pension_validation["final_age"])}
first pension projection year = {int(pension["projection_year"].min())}
final pension projection year = {int(pension["projection_year"].max())}

Pension PV validation at retirement:
{eur_bn(float(pension_validation["pv_at_retirement"]))}
validation difference = {eur_mn(float(pension_validation["pv_validation_error"]))}
Excel discount factors used only for consistency check: YES
Market valuation curve used for ALM: bootstrapped EUR swap curve

Model horizon:
{assumptions.horizon_years} years

Long-tail liability visibility:
Liability PV inside 0-30Y = {eur_bn(liability["pv_inside_30"])}
Liability PV beyond 30Y = {eur_bn(liability["pv_beyond_30"])}
% of liability PV beyond 30Y = {pct(liability["pv_beyond_30_percent"])}

Funding analysis:
PV current assets = {eur_bn(funding["pv_current_assets"])}
PV future premiums = {eur_bn(funding["pv_future_premiums"])}
PV benefit liabilities = {eur_bn(funding["pv_benefit_liabilities"])}
Net funding position = {eur_bn(funding["net_funding_position"])}
==================================================
"""


def build_optimization_summary(
    assumptions: Assumptions,
    curve: pd.DataFrame,
    optimization: dict[str, object],
    liability: dict[str, float],
    funding: dict[str, float],
    portfolio: dict[str, float],
    irs: dict[str, object],
    accumulated_value: float,
) -> str:
    dv01_gap = float(irs["dv01_gap"])
    irs_candidates = irs["candidate_table"]
    if isinstance(irs_candidates, pd.DataFrame):
        candidate_text = irs_candidates[
            [
                "direction",
                "irs_tenor_years",
                "irs_par_fixed_rate",
                "irs_dv01_per_eur",
                "irs_notional",
                "residual_dv01_after_swap",
            ]
        ].to_string(index=False)
    else:
        candidate_text = ""

    return f"""MODEL TYPE:
Constrained Fixed-Income Asset-Liability Matching
Quadratic Optimization

DATA LABELS:
Current assets and policyholder inputs: case/prototype assumptions
Pension cash flows: actuarial Excel file supplied in the project
Yield curve: EUR par swap Excel bootstrapped into discount factors, curve date {curve["curve_date"].iloc[0]}
Bond market data: observed prices from Fixed Income Basket.xlsx
USD curve and EURUSD: normalized but not used in EUR optimizer

DECISION VARIABLES:
EUR invested in each usable bond

OBJECTIVE:
Minimize cash-flow mismatch + DV01 mismatch + small investment-use/PV penalty

FINAL OBJECTIVE ACTUALLY SOLVED:
min_x sum_t(CF_A_t_bn - CF_L_t_bn)^2
    + {assumptions.gamma_dv01:.1f} * ((DV01_A_mn - DV01_L_mn) / DV01_L_mn)^2
    + {assumptions.eta_pv:.1f} * (PortfolioValue_bn - TargetInvestment_bn)^2

OBJECTIVE COMPONENTS:
Cash-flow component: {float(optimization["cf_component"]):.6f}
DV01 component: {float(optimization["dv01_component"]):.6f}
Investment-use component: {float(optimization["investment_use_component"]):.6f}
Total objective: {float(optimization["objective_value"]):.6f}

CONSTRAINTS:
x_i >= 0
sum_i x_i <= {eur_bn(assumptions.current_available_assets_eur)}
sum_i x_i >= {pct(assumptions.minimum_invested_fraction)} of available assets
Gov + SSA + Covered >= {pct(assumptions.minimum_high_quality_weight)} of invested portfolio
IG corporate <= {pct(assumptions.maximum_corporate_weight)} of invested portfolio
single instrument <= {pct(assumptions.maximum_single_instrument_weight)} of invested portfolio
single issuer <= {pct(assumptions.maximum_single_issuer_weight)} of invested portfolio
DV01_A within +/-{pct(float(optimization["dv01_tolerance"]))} of DV01_L

SOLVER:
{optimization["solver"]}

STATUS:
{optimization["status"]}

OBJECTIVE VALUE:
{float(optimization["objective_value"]):.6f}

GUARANTEED ACCUMULATED VALUE AT YEAR 15:
{eur_bn(accumulated_value)}

LIABILITY PV:
{eur_bn(liability["pv"])}

LIABILITY DURATION:
{liability["duration"]:.2f} years

LIABILITY DV01:
{eur_mn(liability["dv01"])} per bp

LIABILITY PV BEYOND 30Y:
{eur_bn(liability["pv_beyond_30"])}

PV CURRENT ASSETS:
{eur_bn(funding["pv_current_assets"])}

PV FUTURE PREMIUMS:
{eur_bn(funding["pv_future_premiums"])}

PV BENEFIT LIABILITIES:
{eur_bn(funding["pv_benefit_liabilities"])}

NET FUNDING POSITION:
{eur_bn(funding["net_funding_position"])}

PORTFOLIO VALUE:
{eur_bn(portfolio["value"])}

PORTFOLIO YIELD:
{pct(portfolio["yield"])}

PORTFOLIO DURATION:
{portfolio["duration"]:.2f} years

PORTFOLIO DV01:
{eur_mn(portfolio["dv01"])} per bp

DV01 GAP:
DV01_A - DV01_L = {eur_mn(dv01_gap)} per bp

IRS HEDGE CANDIDATES:
{candidate_text}

IRS NOTIONAL:
Direction: {irs["direction"]}
Tenor: {irs["irs_tenor_years"]} years
Selection basis: {irs["selection_basis"]}
Par fixed rate: {pct(float(irs["irs_par_fixed_rate"]))}
DV01 per EUR notional: {float(irs["irs_dv01_per_eur"]):.8f}
Required notional: {eur_bn(float(irs["irs_notional"]))}
Residual DV01 after swap: {eur_mn(float(irs["residual_dv01_after_swap"]))} per bp
"""


def save_outputs(
    results_dir: Path,
    portfolio_df: pd.DataFrame,
    cashflow_table: pd.DataFrame,
    liability_schedule: pd.DataFrame,
    summary: str,
) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    portfolio_df.to_csv(results_dir / "fixed_income_portfolio.csv", index=False)
    cashflow_table.to_csv(results_dir / "cashflow_matching.csv", index=False)
    liability_schedule.to_csv(results_dir / "liability_cashflows.csv", index=False)
    (results_dir / "optimization_summary.txt").write_text(summary, encoding="utf-8")
    save_charts(cashflow_table, results_dir)


def print_final_model_output(
    liability: dict[str, float],
    portfolio: dict[str, float],
    irs: dict[str, object],
    portfolio_df: pd.DataFrame,
    optimization: dict[str, object],
) -> None:
    print("\nFIXED-INCOME ALM RESULT\n")
    print(f"Liability PV: {eur_bn(liability['pv'])}")
    print(f"Liability Duration: {liability['duration']:.2f} years")
    print(f"Liability DV01: {eur_mn(liability['dv01'])} per bp")
    print(f"Liability PV beyond 30Y: {eur_bn(liability['pv_beyond_30'])}")

    print("\nOptimal bond allocation:")
    print(
        portfolio_df[
            [
                "instrument",
                "issuer",
                "category",
                "maturity_date",
                "years_to_maturity",
                "coupon",
                "market_price_per_100",
                "quote_date",
                "ytm",
                "duration",
                "dv01_per_eur_1m",
                "eur_allocation_mn",
                "portfolio_weight",
                "dv01_contribution_mn",
            ]
        ].to_string(
            index=False,
            formatters={
                "years_to_maturity": lambda x: f"{float(x):.2f}",
                "coupon": lambda x: pct(float(x)),
                "market_price_per_100": lambda x: f"{float(x):.3f}",
                "ytm": lambda x: pct(float(x)),
                "duration": lambda x: f"{float(x):.2f}",
                "dv01_per_eur_1m": lambda x: f"{float(x):,.2f}",
                "eur_allocation_mn": lambda x: f"{float(x):,.1f}",
                "portfolio_weight": lambda x: pct(float(x)),
                "dv01_contribution_mn": lambda x: f"{float(x):,.2f}",
            },
        )
    )

    print("\nPortfolio Yield:", pct(portfolio["yield"]))
    print("Portfolio Duration:", f"{portfolio['duration']:.2f} years")
    print("Portfolio DV01:", f"{eur_mn(portfolio['dv01'])} per bp")
    print("Initial DV01 gap:", f"{eur_mn(float(irs['dv01_gap']))} per bp")
    print("Optimizer status:", optimization["status"])
    print("Objective value:", f"{float(optimization['objective_value']):.6f}")

    print("\nIRS hedge:")
    print(f"Direction: {irs['direction']}")
    print(f"Tenor: {irs['irs_tenor_years']} years")
    print(f"Par rate: {pct(float(irs['irs_par_fixed_rate']))}")
    print(f"Notional required: {eur_bn(float(irs['irs_notional']))}")
    print(f"Residual DV01 after IRS: {eur_mn(float(irs['residual_dv01_after_swap']))} per bp")



# RUN END TO END



def main() -> None:
    assumptions = Assumptions()
    require_valid_shares(assumptions)

    input_paths = {key: resolve_input_file(filename) for key, filename in INPUT_FILENAMES.items()}
    date_corrections: list[str] = []

    _, eur_swap_latest, eur_curve, _ = normalize_swap_curve(
        input_paths["eur_swaps"],
        "EUR",
        assumptions,
        date_corrections,
    )
    _, usd_swap_latest, usd_curve, _ = normalize_swap_curve(
        input_paths["usd_swaps"],
        "USD",
        assumptions,
        date_corrections,
    )
    eurusd, _ = normalize_eurusd(input_paths["eurusd"], assumptions, date_corrections)
    universe = parse_fixed_income_basket(input_paths["fixed_income"], assumptions, date_corrections)

    accumulated_value = guaranteed_accumulated_value(assumptions)
    pension = load_pension_cashflows(input_paths["pension"], assumptions)
    pension_validation = validate_pension_file(pension, assumptions, accumulated_value)

    liability_cf, liability_schedule = build_liability_cashflows(assumptions, pension)
    if len(liability_cf) > assumptions.horizon_years:
        raise ValueError("Internal error: liability horizon exceeds configured horizon.")
    liability = liability_analytics(liability_cf, eur_curve)
    funding = funding_analysis(assumptions, liability["pv"], eur_curve)
    scenarios = policyholder_choice_scenarios(pension, eur_curve, assumptions)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    eur_curve.to_csv(RESULTS_DIR / "normalized_eur_swap_curve.csv", index=False)
    usd_curve.to_csv(RESULTS_DIR / "normalized_usd_swap_curve.csv", index=False)
    eurusd.to_csv(RESULTS_DIR / "normalized_eurusd.csv", index=False)
    universe.to_csv(RESULTS_DIR / "normalized_fixed_income_universe.csv", index=False)
    pension.to_csv(RESULTS_DIR / "normalized_pension_cashflows.csv", index=False)
    scenarios.to_csv(RESULTS_DIR / "policyholder_choice_scenarios.csv", index=False)

    data_validation_report = build_data_validation_report(
        assumptions=assumptions,
        input_paths=input_paths,
        eur_latest=eur_swap_latest,
        eur_curve=eur_curve,
        usd_latest=usd_swap_latest,
        eurusd=eurusd,
        universe=universe,
        pension=pension,
        pension_validation=pension_validation,
        liability=liability,
        funding=funding,
        date_corrections=date_corrections,
    )
    print(data_validation_report)
    (RESULTS_DIR / "data_validation_report.txt").write_text(data_validation_report, encoding="utf-8")

    analytics, C = calculate_bond_analytics(universe, eur_curve, assumptions)
    explain_asset_matrix()

    optimization = solve_fixed_income_qp(
        C=C,
        liability_cf_eur=liability_cf,
        analytics=analytics,
        assumptions=assumptions,
        liability_dv01_eur_per_bp=liability["dv01"],
    )

    allocation = optimization["allocation_eur"]
    if not isinstance(allocation, np.ndarray):
        raise TypeError("Internal error: allocation is not a numpy array.")

    asset_cf = C @ allocation
    portfolio_df = portfolio_table(allocation, analytics)
    portfolio = portfolio_metrics(allocation, analytics)
    irs = calculate_irs_gap(
        portfolio_dv01=portfolio["dv01"],
        liability_dv01=liability["dv01"],
        liability_duration=liability["duration"],
        curve=eur_curve,
        assumptions=assumptions,
    )
    cashflow_table = build_cashflow_matching_table(asset_cf, liability_cf)

    summary = build_optimization_summary(
        assumptions=assumptions,
        curve=eur_curve,
        optimization=optimization,
        liability=liability,
        funding=funding,
        portfolio=portfolio,
        irs=irs,
        accumulated_value=accumulated_value,
    )
    save_outputs(RESULTS_DIR, portfolio_df, cashflow_table, liability_schedule, summary)
    irs_candidate_table = irs["candidate_table"]
    if isinstance(irs_candidate_table, pd.DataFrame):
        irs_candidate_table.to_csv(RESULTS_DIR / "irs_hedge_candidates.csv", index=False)

    print_final_model_output(
        liability=liability,
        portfolio=portfolio,
        irs=irs,
        portfolio_df=portfolio_df,
        optimization=optimization,
    )

    print("\nOUTPUTS SAVED")
    for filename in [
        "normalized_eur_swap_curve.csv",
        "normalized_usd_swap_curve.csv",
        "normalized_eurusd.csv",
        "normalized_fixed_income_universe.csv",
        "normalized_pension_cashflows.csv",
        "data_validation_report.txt",
        "fixed_income_portfolio.csv",
        "optimization_summary.txt",
        "asset_vs_liability_cashflows.png",
        "cumulative_asset_vs_liability_cashflows.png",
    ]:
        print(f"- {RESULTS_DIR / filename}")


if __name__ == "__main__":
    main()
