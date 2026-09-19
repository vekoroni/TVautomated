"""F3: the live volatility regime is labelled the way the actuarial database was labelled (ACK, 19 Sep 2026).

Run 20260918_112522: layer2__vol_regime was NORMAL on 1,580 of 1,580 rows. The live classifier averaged ATR, BB and
IV percentiles, but BB and IV were always 50 (never forwarded / not available before options), so the average could
only reach 33.5-66.5 and never crossed 20/80. Every candidate was therefore matched only against the NORMAL slice of
the 3.8m-row database, whose labels use a different rule: ATR% (14-EWM true range / close) and Bollinger width
(4 x 20-day std / 20-day mean) percentiles over 252 bars; COMPRESSION if both < 30, EXPANSION if either > 70.
The classifier now applies the database's rule to the bars it already holds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import avshunter_db_update as db
from vanguard.layer2_statistical.state_calculator import db_consistent_vol_regime


def _bars(daily_vol: np.ndarray, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, daily_vol)))
    spread = close * daily_vol
    return pd.DataFrame({"date": pd.bdate_range("2025-06-02", periods=len(close)).strftime("%Y-%m-%d"),
                         "open": close, "high": close + spread, "low": close - spread, "close": close,
                         "volume": np.full(len(close), 1e6)})


def _db_label(df: pd.DataFrame) -> str:
    return db._compute_state(db._compute_technicals(df), len(df) - 1)["vol_regime"]


@pytest.mark.parametrize("name,vols", [
    ("compressed tail", np.r_[np.full(260, 0.03), np.full(40, 0.004)]),
    ("expanding tail", np.r_[np.full(260, 0.01), np.full(40, 0.05)]),
    ("steady", np.full(300, 0.015)),
])
def test_the_live_label_equals_the_database_label_on_the_same_bars(name, vols):
    df = _bars(vols)
    live = db_consistent_vol_regime(df)
    assert live["regime"] == _db_label(df), name
    assert live["regime_source"] == "DB_CONSISTENT_ATR_BB_252"


def test_compression_and_expansion_can_now_be_reached():
    assert db_consistent_vol_regime(_bars(np.r_[np.full(260, 0.03), np.full(40, 0.004)]))["regime"] == "COMPRESSION"
    assert db_consistent_vol_regime(_bars(np.r_[np.full(260, 0.01), np.full(40, 0.05)]))["regime"] == "EXPANSION"


def test_too_few_bars_is_reported_not_labelled_normal():
    assert db_consistent_vol_regime(_bars(np.full(40, 0.01))) is None


def test_the_state_calculator_uses_the_database_rule_when_bars_exist():
    from vanguard.layer2_statistical.state_calculator import StateVectorCalculator as StateCalculator
    from vanguard.schemas.input_schema import TechnicalData
    df = _bars(np.r_[np.full(260, 0.03), np.full(40, 0.004)])
    result = StateCalculator()._calculate_volatility_regime(TechnicalData(ohlcv=df, atr_current=1.0))
    assert result["regime"] == "COMPRESSION"
    assert result["regime_source"] == "DB_CONSISTENT_ATR_BB_252"


def test_without_bars_the_legacy_weighted_rule_is_used_and_labelled():
    from vanguard.layer2_statistical.state_calculator import StateVectorCalculator as StateCalculator
    from vanguard.schemas.input_schema import TechnicalData
    result = StateCalculator()._calculate_volatility_regime(TechnicalData(atr_current=1.0))
    assert result["regime_source"] == "LEGACY_WEIGHTED_INPUTS_INCOMPLETE"


# --- Found in the 19 Sep replay: the regime result must keep the IV percentile the edge detector reads ------------
# The database-rule path returned iv_percentile=None; edge_detector compares and formats it (IV spike check), so
# 1,181 of 1,580 packages raised TypeError. The IV input does not exist at this stage: the value is exactly what the
# legacy path supplies (the ticker's IV fields when present, else its 50 placeholder), so edge detection is unchanged.

def test_the_database_rule_keeps_the_legacy_iv_percentile_for_the_edge_detector():
    from vanguard.layer2_statistical.state_calculator import StateVectorCalculator
    from vanguard.schemas.input_schema import TechnicalData
    df = _bars(np.r_[np.full(260, 0.03), np.full(40, 0.004)])
    result = StateVectorCalculator()._calculate_volatility_regime(TechnicalData(ohlcv=df, atr_current=1.0))
    assert result["regime_source"] == "DB_CONSISTENT_ATR_BB_252"
    assert result["iv_percentile"] == 50.0
