import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from curve_io import build_discount_curve  # noqa: E402


@pytest.fixture(scope="session")
def upward_rates_pct():
    """A clean, strictly upward-sloping synthetic curve, 1Y..10Y, in percent."""
    import pandas as pd

    tenors = np.arange(1, 11)
    rates = 2.0 + 0.15 * tenors  # 2.15 % .. 3.50 %, monotone
    return pd.Series(rates, index=[f"{t}Y" for t in tenors], name="par_swap_rate_pct")


@pytest.fixture(scope="session")
def flat_rates_pct():
    import pandas as pd

    tenors = np.arange(1, 11)
    return pd.Series(np.full(tenors.size, 3.0),
                     index=[f"{t}Y" for t in tenors], name="par_swap_rate_pct")


@pytest.fixture(scope="session")
def inverted_rates_pct():
    import pandas as pd

    tenors = np.arange(1, 11)
    rates = 4.0 - 0.12 * tenors  # 3.88 % .. 2.80 %, monotone down
    return pd.Series(rates, index=[f"{t}Y" for t in tenors], name="par_swap_rate_pct")


@pytest.fixture(scope="session")
def negative_rates_pct():
    """Upward-sloping but through zero, like the EUR curve in early 2020."""
    import pandas as pd

    tenors = np.arange(1, 11)
    rates = -0.55 + 0.05 * tenors  # -0.50 % .. -0.05 %, upward but all negative
    return pd.Series(rates, index=[f"{t}Y" for t in tenors], name="par_swap_rate_pct")


@pytest.fixture(scope="session")
def upward_curve(upward_rates_pct):
    return build_discount_curve(upward_rates_pct)


@pytest.fixture(scope="session")
def negative_curve(negative_rates_pct):
    return build_discount_curve(negative_rates_pct)


@pytest.fixture(scope="session")
def flat_curve(flat_rates_pct):
    return build_discount_curve(flat_rates_pct)


@pytest.fixture(scope="session")
def inverted_curve(inverted_rates_pct):
    return build_discount_curve(inverted_rates_pct)
