"""DIR-002 DSC-02: fail-backs and failed thrusts contribute symmetrically."""

import json
from pathlib import Path

import pandas as pd
import pytest

from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2, symmetric_control_scores


POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "config" / "dir002_side_evidence_v1.json").read_text(
        encoding="utf-8"
    )
)


def _bars():
    return pd.DataFrame({
        "high": [102.0] * 20,
        "low": [98.0] * 20,
        "close": [100.0] * 20,
        "poc": [0.5] * 20,
        "vol_ratio": [1.0] * 20,
        "spread_ratio": [1.0] * 20,
    })


def test_fail_back_control_scores_mirror_and_cap():
    bars = _bars()
    bull = symmetric_control_scores(bars, 20, 0, POLICY)
    bear = symmetric_control_scores(bars, 0, 20, POLICY)
    assert bull["bull_score"] == bear["bear_score"] > 0
    assert bull["bear_score"] == bear["bull_score"] == 0
    assert bull == symmetric_control_scores(bars, 200, 0, POLICY)


def test_failed_upward_thrust_supports_bear_and_mirrors_downward_thrust():
    up = _bars()
    up.loc[17, ["high", "low", "close"]] = [105.0, 99.0, 104.0]
    up.loc[18, ["high", "low", "close"]] = [103.0, 98.0, 99.0]
    down = _bars()
    down.loc[17, ["high", "low", "close"]] = [101.0, 95.0, 96.0]
    down.loc[18, ["high", "low", "close"]] = [102.0, 97.0, 101.0]
    bear = symmetric_control_scores(up, 0, 0, POLICY)
    bull = symmetric_control_scores(down, 0, 0, POLICY)
    assert bear["upward_failed_thrust_count"] == bull["downward_failed_thrust_count"] == 1
    assert bear["bear_score"] == bull["bull_score"] > 0


def test_missing_bar_or_policy_does_not_read_as_zero_evidence():
    bars = _bars()
    bars.loc[18, "close"] = float("nan")
    with pytest.raises(ValueError):
        symmetric_control_scores(bars, 1, 0, POLICY)
    with pytest.raises(ValueError):
        symmetric_control_scores(_bars(), 1, 0, {**POLICY, "control": {}})


def test_wyckoff_emits_side_scores_as_shadow_without_changing_legacy_control():
    bars = pd.concat([_bars(), _bars().iloc[:10]], ignore_index=True)
    bars["open"] = bars["close"]
    bars["volume"] = 1_000_000
    bars.loc[27, ["high", "low", "close"]] = [105.0, 99.0, 104.0]
    bars.loc[28, ["high", "low", "close"]] = [103.0, 98.0, 99.0]
    engine = WyckoffEngine_3101_v2()
    result = engine.analyze("TEST", bars)
    assert result["sym_control_status"] == "AVAILABLE_SHADOW"
    assert result["sym_bear_control_score"] > result["sym_bull_control_score"]
    assert result["control_state"] in {"BUYERS", "SELLERS", "EQUILIBRIUM", "SHIFTING"}
