"""DIR-002: a structural reading is not a completed trade plan."""

from contracts.direction_governance import (
    assess_thesis_geometry,
    candidate_geometry_shadow_fields,
)
import pandas as pd
from unittest.mock import patch

import avshunter_discovery_ULTIMATE as discovery
from wyckoff_phase_validator import validate_wyckoff_phase


def test_supported_bull_direction_survives_missing_invalidation() -> None:
    result = assess_thesis_geometry(
        thesis_side="BULL",
        reference_price=100.0,
        invalidation_price=None,
        invalidation_source=None,
        target_price=112.0,
        target_source="WYCKOFF",
    )

    assert result["thesis__side"] == "BULL"
    assert result["geometry_status"] == "INCOMPLETE_GEOMETRY"
    assert result["target_state"] == "LEVEL"
    assert result["geometry_complete"] is False


def test_wrong_side_stop_does_not_flip_or_erase_bear_direction() -> None:
    result = assess_thesis_geometry(
        thesis_side="BEAR",
        reference_price=100.0,
        invalidation_price=95.0,
        invalidation_source="WYCKOFF_VALIDATION",
        target_price=None,
        target_source=None,
    )

    assert result["thesis__side"] == "BEAR"
    assert result["geometry_status"] == "INCOMPLETE_GEOMETRY"
    assert result["invalidation_price"] is None
    assert result["invalidation_reason"] == "WRONG_SIDE"
    assert result["target_state"] == "NONE"
    assert result["geometry_complete"] is False


def test_structural_stop_with_no_target_is_a_complete_geometry() -> None:
    result = assess_thesis_geometry(
        thesis_side="BEAR",
        reference_price=100.0,
        invalidation_price=105.0,
        invalidation_source="WYCKOFF_VALIDATION",
        target_price=None,
        target_source=None,
    )

    assert result["geometry_status"] == "COMPLETE"
    assert result["target_state"] == "NONE"
    assert result["geometry_complete"] is True


def test_unsourced_invalidation_cannot_become_a_trade_stop() -> None:
    result = assess_thesis_geometry(
        thesis_side="BULL",
        reference_price=100.0,
        invalidation_price=95.0,
        invalidation_source="ATR_FALLBACK",
        target_price=110.0,
        target_source="WYCKOFF",
    )

    assert result["thesis__side"] == "BULL"
    assert result["geometry_status"] == "INCOMPLETE_GEOMETRY"
    assert result["invalidation_price"] is None
    assert result["invalidation_reason"] == "UNSOURCED"


def test_missing_reference_is_not_confused_with_weak_direction() -> None:
    result = assess_thesis_geometry(
        thesis_side="BULL",
        reference_price=None,
        invalidation_price=95.0,
        invalidation_source="WYCKOFF_VALIDATION",
        target_price=None,
        target_source=None,
    )

    assert result["thesis__side"] == "BULL"
    assert result["geometry_status"] == "NOT_ASSESSABLE"
    assert result["geometry_complete"] is False


def test_validator_publishes_both_sides_from_prior_completed_range() -> None:
    bars = pd.DataFrame(
        [{"high": 105.0, "low": 95.0, "close": 100.0}] * 40
        + [{"high": 120.0, "low": 80.0, "close": 100.0}]
    )
    result = validate_wyckoff_phase("TEST", bars, {"current_phase": "B"})

    assert result["wyckoff_structure_v2"] == "UNKNOWN"
    assert result["candidate_bull_invalidation"] == 95.0
    assert result["candidate_bear_invalidation"] == 105.0
    assert result["candidate_invalidation_source"] == "WYCKOFF_VALIDATION"
    assert result["candidate_bull_target"] == 105.0
    assert result["candidate_bear_target"] == 95.0
    assert result["candidate_target_source"] == "PRIOR_RANGE_EXTREME"


def test_validator_does_not_invent_range_from_only_the_current_bar() -> None:
    bars = pd.DataFrame([{"high": 105.0, "low": 95.0, "close": 100.0}])
    result = validate_wyckoff_phase("TEST", bars, {"current_phase": "B"})

    assert result["candidate_bull_invalidation"] is None
    assert result["candidate_bear_invalidation"] is None
    assert result["candidate_bull_target"] is None
    assert result["candidate_bear_target"] is None
    assert result["candidate_invalidation_status"] == "INSUFFICIENT_PRIOR_BARS"


def test_prior_range_candidates_mirror_when_prices_are_log_reflected() -> None:
    bars = pd.DataFrame(
        [{"high": 105.0, "low": 95.0, "close": 100.0}] * 40
        + [{"high": 103.0, "low": 97.0, "close": 100.0}]
    )
    mirrored = bars.copy()
    mirrored["high"] = 10000.0 / bars["low"]
    mirrored["low"] = 10000.0 / bars["high"]
    mirrored["close"] = 10000.0 / bars["close"]

    original = validate_wyckoff_phase("TEST", bars, {"current_phase": "B"})
    reflected = validate_wyckoff_phase("TEST", mirrored, {"current_phase": "B"})

    assert abs(reflected["candidate_bull_invalidation"] - 10000.0 / original["candidate_bear_invalidation"]) < 0.0001
    assert abs(reflected["candidate_bear_invalidation"] - 10000.0 / original["candidate_bull_invalidation"]) < 0.0001


def test_malformed_prior_bar_does_not_yield_a_structural_level() -> None:
    bars = pd.DataFrame(
        [{"high": 105.0, "low": 95.0, "close": 100.0}] * 39
        + [{"high": 94.0, "low": 96.0, "close": 95.0}]
        + [{"high": 100.0, "low": 99.0, "close": 99.5}]
    )
    result = validate_wyckoff_phase("TEST", bars, {"current_phase": "B"})

    assert result["candidate_invalidation_status"] == "INVALID_PRIOR_BARS"
    assert result["candidate_bull_invalidation"] is None
    assert result["candidate_bear_invalidation"] is None


def test_shadow_geometry_builds_both_sides_without_consulting_direction() -> None:
    candidate_levels = {
        "candidate_bull_invalidation": 95.0,
        "candidate_bear_invalidation": 105.0,
        "candidate_invalidation_source": "WYCKOFF_VALIDATION",
        "candidate_bull_target": 105.0,
        "candidate_bear_target": 95.0,
        "candidate_target_source": "PRIOR_RANGE_EXTREME",
    }
    result = candidate_geometry_shadow_fields(100.0, candidate_levels)

    assert result["sym_bull_geometry_status"] == "COMPLETE"
    assert result["sym_bear_geometry_status"] == "COMPLETE"
    assert result["sym_bull_target_state"] == "LEVEL"
    assert result["sym_bear_target_state"] == "LEVEL"
    assert result["sym_bull_target"] == 105.0
    assert result["sym_bear_target"] == 95.0
    assert "direction" not in result
    assert "stop_loss" not in result


def test_shadow_geometry_rejects_wrong_side_levels_without_reassigning_side() -> None:
    result = candidate_geometry_shadow_fields(
        110.0,
        {
            "candidate_bull_invalidation": 95.0,
            "candidate_bear_invalidation": 105.0,
            "candidate_invalidation_source": "WYCKOFF_VALIDATION",
            "candidate_bull_target": 105.0,
            "candidate_bear_target": 95.0,
            "candidate_target_source": "PRIOR_RANGE_EXTREME",
        },
    )

    assert result["sym_bull_geometry_status"] == "COMPLETE"
    assert result["sym_bull_target_state"] == "NONE"
    assert result["sym_bull_target"] is None
    assert result["sym_bear_geometry_status"] == "INCOMPLETE_GEOMETRY"
    assert result["sym_bear_invalidation"] is None
    assert result["sym_bear_invalidation_reason"] == "WRONG_SIDE"


def test_discovery_emits_both_candidate_geometries_without_changing_live_side() -> None:
    class StubWyckoff:
        def analyze(self, ticker, bars, trend_context):
            return {
                "wyckoff_score": 82.0,
                "current_phase": "B",
                "phase_evidence_strength": 80.0,
                "dominant_event": "ST",
                "event_evidence_strength": 75.0,
                "truth_confidence": 78.0,
                "trade_direction": "LONG",
                "control_state": "BUYERS",
                "stop_loss": 90.0,
                "initial_target": 120.0,
                "sym_range_break_authority": "IMPLEMENTED_FOR_REPLICATION",
                "sym_range_break_status": "AVAILABLE_SHADOW",
                "sym_range_break_policy_version": "dir002_side_evidence_v1",
                "sym_bull_break_count": 2,
                "sym_bull_fail_back_count": 1,
                "sym_bear_break_count": 0,
                "sym_bear_fail_back_count": 0,
                "sym_phase_c_event_candidate": "SPRING_CANDIDATE",
                "sym_control_status": "AVAILABLE_SHADOW",
                "sym_bull_control_score": 0.6,
                "sym_bear_control_score": 0.1,
                "sym_upward_failed_thrust_count": 0,
                "sym_downward_failed_thrust_count": 1,
            }

    bars = pd.DataFrame(
        [
            {
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.0 + (i % 4) * 0.1,
                "volume": 1_000_000,
            }
            for i in range(220)
        ],
        index=pd.date_range("2025-01-01", periods=220, freq="B"),
    )
    # The live side asserted below is the legacy owner's; since ACK's cut-over to beh001_v1
    # (2 Oct 2026) that is the governed rollback, so the test pins it explicitly.
    policy, runtime = discovery._beh001_runtime()
    rollback = (policy, {**runtime, "production_direction_source": "legacy_rollback"})
    with patch.object(discovery, "process_precore_signal", return_value={}), patch.object(
        discovery, "_SWING_FUSION_AVAILABLE", False
    ), patch.object(discovery, "_beh001_runtime", return_value=rollback):
        result = discovery.scan_ticker_ultimate(
            "TEST", bars, discovery.UltimateConfig(tier3_min=0.0), StubWyckoff()
        )
    with patch.object(discovery, "process_precore_signal", return_value={}), patch.object(
        discovery, "_SWING_FUSION_AVAILABLE", False
    ):
        governed = discovery.scan_ticker_ultimate(
            "TEST", bars, discovery.UltimateConfig(tier3_min=0.0), StubWyckoff()
        )
    # Under beh001_v1 the same geometry fields are emitted; the side is BEH-001's own reading
    # (flat bars carry no directional event, so it is not a CALL).
    assert governed is not None and governed["sym_bull_invalidation"] == 95.0
    assert governed["direction"] != "CALL" or governed["thesis__side"] == "BULL"

    assert result is not None
    assert result["sym_bull_invalidation"] == 95.0
    assert result["sym_control_status"] == "AVAILABLE_SHADOW"
    assert result["sym_bull_control_score"] == 0.6
    assert result["sym_bear_control_score"] == 0.1
    assert result["sym_bear_invalidation"] == 105.0
    assert result["sym_bull_target"] == 105.0
    assert result["sym_bear_target"] == 95.0
    assert result["direction"] == "CALL"
    assert result["stop_loss"] == 90.0
    assert result["structural_target"] == 120.0
    assert result["sym_bull_break_count"] == 2
    assert result["sym_bear_break_count"] == 0
    assert result["sym_range_break_policy_version"] == "dir002_side_evidence_v1"
    assert result["sym_phase_c_event_candidate"] == "SPRING_CANDIDATE"
