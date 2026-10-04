"""SOR-001 structural boundary tests: event bars cannot define their own range."""

import pandas as pd

from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2


def _range_bars(count=30):
    return pd.DataFrame({
        "open": [100.0] * count, "high": [102.0] * count,
        "low": [98.0] * count, "close": [100.0] * count,
        "volume": [1_000_000] * count,
    })


def test_latest_breakout_is_compared_with_prior_range_not_its_own_high():
    engine = WyckoffEngine_3101_v2()
    bars = pd.concat([
        _range_bars(),
        pd.DataFrame([dict(open=100.0, high=105.0, low=99.0,
                           close=104.0, volume=2_000_000)]),
    ], ignore_index=True)
    prepared = engine._prepare_dataframe(bars.copy())
    features = engine._extract_features(prepared)
    assert features["range_high"] == 102.0
    assert features["range_low"] == 98.0
    assert engine._score_phase_d(prepared, features) >= 30


def test_spring_break_and_next_session_reclaim_use_pre_event_boundary():
    engine = WyckoffEngine_3101_v2()
    bars = pd.concat([
        _range_bars(),
        pd.DataFrame([
            dict(open=99.0, high=100.0, low=95.0, close=97.0,
                 volume=2_000_000),
            dict(open=99.0, high=102.0, low=98.0, close=101.0,
                 volume=1_500_000),
        ]),
    ], ignore_index=True)
    prepared = engine._prepare_dataframe(bars.copy())
    features = engine._extract_features(prepared)
    assert features["range_low"] == 98.0
    assert features["break_count"] >= 1
    assert features["reclaim_count"] >= 1


def test_default_production_range_excludes_the_event_bar():
    bars = pd.concat([
        _range_bars(),
        pd.DataFrame([dict(open=100.0, high=105.0, low=99.0,
                           close=104.0, volume=2_000_000)]),
    ], ignore_index=True)
    engine = WyckoffEngine_3101_v2()
    features = engine._extract_features(engine._prepare_dataframe(bars.copy()))
    assert features["range_high"] == 102.0
    assert features["range_anchor_index"] == len(bars) - 1
