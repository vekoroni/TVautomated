from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
from vanguard.core.actuarial_core_v7 import (
    ActuarialCoreContractError,
    build_ticker_observations,
    calculate_core_state,
    compute_technicals,
)
from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine


UPDATER = Path(r"C:\Users\ACKVerissimo\vanguard\avshunter_db_update.py")


def _load_updater():
    spec = importlib.util.spec_from_file_location("actuarial_v7_updater", UPDATER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bars(count: int = 30) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=count, freq="D"),
            "close": [100.0 + i for i in range(count)],
            "high": [101.0 + i for i in range(count)],
            "low": [99.0 + i for i in range(count)],
        }
    )


def _daily_ohlcv(count: int = 90) -> pd.DataFrame:
    close = pd.Series([100.0 + i * 0.4 + (i % 5) * 0.1 for i in range(count)])
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2025-01-02", periods=count),
            "open": close - 0.2,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [1_000_000 + i * 1_000 for i in range(count)],
        }
    )


def test_calendar_key_normalises_timestamp_and_date() -> None:
    updater = _load_updater()
    assert updater.canonical_session_date("2022-01-27") == "2022-01-27"
    assert updater.canonical_session_date("2022-01-27 04:00:00+00:00") == "2022-01-27"


def test_forward_labels_mature_independently() -> None:
    updater = _load_updater()
    bars = _bars()

    five_only = updater._compute_outcomes(bars, 24)
    ten_only = updater._compute_outcomes(bars, 19)
    all_mature = updater._compute_outcomes(bars, 9)
    none_mature = updater._compute_outcomes(bars, 29)

    assert (five_only["mature_5d"], five_only["mature_10d"], five_only["mature_20d"]) == (
        True, False, False
    )
    assert (ten_only["mature_5d"], ten_only["mature_10d"], ten_only["mature_20d"]) == (
        True, True, False
    )
    assert (all_mature["mature_5d"], all_mature["mature_10d"], all_mature["mature_20d"]) == (
        True, True, True
    )
    assert (none_mature["mature_5d"], none_mature["mature_10d"], none_mature["mature_20d"]) == (
        False, False, False
    )


def test_pending_hit_labels_are_null_not_false() -> None:
    updater = _load_updater()
    pending = updater._compute_outcomes(_bars(), 29)
    assert pd.isna(pending["outcome_hit_5pct_up_5d"])
    assert pd.isna(pending["outcome_hit_7pct_up_10d"])
    assert pd.isna(pending["outcome_hit_10pct_up"])


def test_calculation_version_participates_in_new_rows() -> None:
    updater = _load_updater()
    outcome = updater._compute_outcomes(_bars(), 9)
    assert outcome["calculation_version"] == updater.CALCULATION_VERSION


def test_query_uses_horizon_specific_mature_samples() -> None:
    engine = object.__new__(ActuarialQueryEngine)
    engine._has_5d_cols = True
    engine._has_10d_cols = True
    matches = pd.DataFrame(
        {
            "outcome_5d_return": [0.10, -0.10, 0.20],
            "outcome_max_drawdown_5d": [-0.02, -0.03, -0.01],
            "outcome_hit_5pct_up_5d": [True, False, True],
            "outcome_10d_return": [0.20, -0.20, None],
            "outcome_max_drawdown_10d": [-0.03, -0.04, None],
            "outcome_hit_7pct_up_10d": [True, False, None],
            "outcome_20d_return": [0.30, None, None],
            "outcome_max_drawdown_20d": [-0.05, None, None],
            "outcome_hit_10pct_up": [True, None, None],
            "outcome_hit_5pct_down_before_10up": [False, None, None],
            "outcome_days_to_10pct": [5, None, None],
            "outcome_category": ["BIG_WIN", None, None],
        }
    )
    outcomes = engine._calculate_outcomes(matches)
    assert outcomes.n_obs_5d == 3
    assert outcomes.n_obs_10d == 2
    assert outcomes.n_obs_20d == 1
    assert outcomes.n_observations == 1


def test_core_state_has_no_future_lookahead() -> None:
    original = _daily_ohlcv()
    altered = original.copy()
    altered.loc[71:, ["open", "high", "low", "close"]] *= 10
    before = calculate_core_state(compute_technicals(original), 70)
    after = calculate_core_state(compute_technicals(altered), 70)
    assert before == after


def test_duplicate_daily_sessions_fail_closed() -> None:
    duplicated = pd.concat([_daily_ohlcv(), _daily_ohlcv().iloc[[0]]], ignore_index=True)
    try:
        compute_technicals(duplicated)
    except ActuarialCoreContractError:
        return
    raise AssertionError("duplicate session was accepted")


def test_updater_delegates_to_shared_core() -> None:
    updater = _load_updater()
    technicals = compute_technicals(_daily_ohlcv())
    assert updater._compute_state(technicals, 70) == calculate_core_state(technicals, 70)


def test_builder_keeps_recent_rows_with_independent_maturity() -> None:
    observations = build_ticker_observations("test", _daily_ohlcv())
    assert len(observations) == 30
    latest = observations.iloc[-1]
    assert not latest["mature_5d"]
    assert not latest["mature_10d"]
    assert not latest["mature_20d"]
