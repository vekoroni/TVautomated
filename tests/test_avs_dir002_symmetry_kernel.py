"""DIR-002 DSC-01: a break and fail-back must have a true mirror."""

import json
from pathlib import Path

import pandas as pd
import pytest

from WyckoffEngine_3101_v2 import (
    WyckoffEngine_3101_v2,
    phase_c_event_candidate,
    range_break,
)


POLICY = json.loads(
    (Path(__file__).resolve().parents[1] / "config" / "dir002_side_evidence_v1.json").read_text(
        encoding="utf-8"
    )
)


def _bars() -> pd.DataFrame:
    baseline = [
        {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0}
        for _ in range(30)
    ]
    event = {"open": 99.0, "high": 100.0, "low": 95.0, "close": 97.0}
    reclaim = {"open": 99.0, "high": 102.0, "low": 98.0, "close": 101.0}
    return pd.DataFrame(baseline + [event, reclaim])


def test_break_and_failback_are_mirrored_from_the_same_policy() -> None:
    bars = _bars()
    prior_range = {"low": 98.0, "high": 102.0}
    bull = range_break(bars, prior_range, "BULL", POLICY)
    bear = range_break(bars, prior_range, "BEAR", POLICY)

    mirrored = bars.copy()
    mirrored["open"] = 10000.0 / bars["open"]
    mirrored["high"] = 10000.0 / bars["low"]
    mirrored["low"] = 10000.0 / bars["high"]
    mirrored["close"] = 10000.0 / bars["close"]
    mirror_range = {"low": 10000.0 / 102.0, "high": 10000.0 / 98.0}
    mirror_bear = range_break(mirrored, mirror_range, "BEAR", POLICY)

    assert bull == {"break_count": 1, "fail_back_count": 1}
    assert bear == {"break_count": 0, "fail_back_count": 0}
    assert mirror_bear == bull


def test_last_bar_break_has_no_invented_next_bar_failback() -> None:
    bars = _bars().iloc[:-1]
    result = range_break(bars, {"low": 98.0, "high": 102.0}, "BULL", POLICY)
    assert result == {"break_count": 1, "fail_back_count": 0}


def test_invalid_policy_or_side_fails_closed() -> None:
    bars = _bars()
    for side, policy in (("CALL", POLICY), ("BULL", {**POLICY, "break_log_distance": 0})):
        try:
            range_break(bars, {"low": 98.0, "high": 102.0}, side, policy)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid side/policy must not yield structural evidence")


@pytest.mark.parametrize(
    "bad_bar",
    [
        {"high": 94.0, "low": 95.0, "close": 94.5},
        {"high": 100.0, "low": 95.0, "close": 101.0},
        {"high": 100.0, "low": 0.0, "close": 97.0},
        {"high": 100.0, "low": 95.0, "close": float("nan")},
    ],
)
def test_invalid_event_bar_cannot_become_a_measured_break(bad_bar) -> None:
    bars = _bars()
    for field, value in bad_bar.items():
        bars.loc[len(bars) - 2, field] = value
    with pytest.raises(ValueError, match="Invalid DIR-002 bar"):
        range_break(bars, {"low": 98.0, "high": 102.0}, "BULL", POLICY)


def test_wyckoff_publishes_two_shadow_blocks_without_replacing_legacy_counts() -> None:
    bars = _bars()
    bars["volume"] = 1_000_000
    engine = WyckoffEngine_3101_v2()
    prepared = engine._prepare_dataframe(bars.copy())
    features = engine._extract_features(prepared)

    assert features["break_count"] >= 1
    assert features["reclaim_count"] >= 1
    # DIR-002 kernel: the shadow counts come from the side-evidence kernel,
    # which leaves the legacy break/reclaim counts above untouched.
    shadow = engine._side_evidence_fields(bars)
    assert shadow["sym_bull_break_count"] == 1
    assert shadow["sym_bull_fail_back_count"] == 1
    assert shadow["sym_bear_break_count"] == 0
    assert shadow["sym_bear_fail_back_count"] == 0

    result = engine.analyze("TEST", bars)
    assert result["sym_range_break_authority"] == "IMPLEMENTED_FOR_REPLICATION"
    assert result["sym_bull_break_count"] == 1
    assert result["sym_bear_break_count"] == 0


def test_phase_c_candidate_uses_break_location_not_existing_control_vote() -> None:
    assert phase_c_event_candidate(1, 0) == "SPRING_CANDIDATE"
    assert phase_c_event_candidate(0, 1) == "UTAD_CANDIDATE"
    assert phase_c_event_candidate(1, 1) == "AMBIGUOUS_TEST"
    assert phase_c_event_candidate(0, 0) == "NONE"
    assert phase_c_event_candidate(None, 0) == "NOT_EVALUATED"
