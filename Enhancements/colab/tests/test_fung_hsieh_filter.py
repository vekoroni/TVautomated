"""Business rules for the Fung-Hsieh weekly macro filter (Colab "Macro Model Rebuild", v1.4).

1. Only finished weeks are used: the current week's bar is in progress, and v1.3 resampled it
   to a FUTURE Friday (6 Oct run: "Week of 2026-10-09").
2. A week whose next week has not happened has no outcome; v1.3 fabricated one
   ((NaN > 0).astype(int) == 0, "SPY fell").
3. The model is tested on the most recent weeks after training on earlier ones; v1.3
   shuffled the weekly series, so future weeks trained the model it then "tested".
No network, no live data.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "avshunter_fung_hsieh_filter_v1_4.py"
TICKERS = ["SPY", "IWM", "UUP", "TLT", "IEF", "GLD", "USO", "HYG"]


def _module():
    spec = importlib.util.spec_from_file_location("fung_hsieh", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # must not fetch, fit or write on import
    return module


def _polygon_weekly(weeks: int, last_week_start: str = "2026-10-04"):
    """Closes as Polygon returns weekly bars: one row per week, stamped at the week's start."""
    starts = pd.date_range(end=last_week_start, periods=weeks, freq="7D")
    rng = np.random.default_rng(7)
    return pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(0, 0.02, weeks))) for t in TICKERS},
                        index=starts)


def test_the_unfinished_current_week_is_not_used():
    m = _module()
    returns = m.complete_weekly_returns(_polygon_weekly(40), today=dt.date(2026, 10, 7))
    assert returns.index.max() == pd.Timestamp("2026-10-02")      # last finished Friday
    assert (returns.index <= pd.Timestamp("2026-10-07")).all()


def test_the_latest_finished_week_has_no_fabricated_outcome():
    m = _module()
    returns = m.complete_weekly_returns(_polygon_weekly(60), today=dt.date(2026, 10, 7))
    X, y = m.build_dataset(returns)
    assert returns.index[-1] not in y.index                      # its next week is unknown
    assert set(y.unique()) <= {0, 1}


def test_the_model_is_tested_on_weeks_after_the_ones_it_learned_from():
    m = _module()
    returns = m.complete_weekly_returns(_polygon_weekly(80), today=dt.date(2026, 10, 7))
    X, y = m.build_dataset(returns)
    X_train, X_test, y_train, y_test = m.chronological_split(X.values, y)
    assert y_train.index.max() < y_test.index.min()
    assert len(y_test) == int(np.ceil(0.2 * len(y)))


def test_a_friday_pre_open_run_does_not_count_the_current_week_as_finished():
    # Friday 9 Oct 2026, 08:40 ET: last completed session Thursday 8 Oct, so the week ending
    # Friday 9 Oct has not finished even though its Friday label equals the run date.
    m = _module()
    data = _polygon_weekly(40, last_week_start="2026-10-04")
    returns = m.complete_weekly_returns(data, today=dt.date(2026, 10, 8))
    assert returns.index.max() == pd.Timestamp("2026-10-02")
