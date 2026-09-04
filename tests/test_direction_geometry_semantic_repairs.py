from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from contracts.direction_governance import resolve_discovery_thesis_direction
from contracts.lab_control import _semantic_handoff_health
from contracts.thesis_geometry import select_directional_invalidation
from eod_candidate_engine import _first_optional_flt


ROOT = Path(__file__).resolve().parents[1]


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_semantic_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_discovery_uses_structural_intent_when_legacy_hint_is_unresolved() -> None:
    call = resolve_discovery_thesis_direction("NONE", "NONE", "BUY_SETUP", "BULLISH")
    put = resolve_discovery_thesis_direction("NONE", "NONE", "SELL_SETUP", "BEARISH")
    assert call[:2] == ("CALL", "RESOLVED_STRUCTURAL")
    assert put[:2] == ("PUT", "RESOLVED_STRUCTURAL")


def test_discovery_direction_conflict_fails_closed_instead_of_flipping() -> None:
    result = resolve_discovery_thesis_direction("LONG", "NONE", "SELL_SETUP", "BEARISH")
    assert result[0] == "UNRESOLVED"
    assert result[1] == "CONFLICT_REVIEW"
    assert "preliminary=CALL" in result[2]
    assert "structural=PUT" in result[2]


def test_side_aware_invalidation_prefers_wyckoff_validator_for_put() -> None:
    row = {
        "governed_invalidation_spot": None,
        "wyckoff_validation_structural_invalidation_level": 105.0,
        "structural_stop": 95.0,
        "structural_stop_source": "WYCKOFF",
        "stop_loss": 95.0,
    }
    value, source, state = select_directional_invalidation(row, "PUT", 100.0)
    assert value == 105.0
    assert source == "WYCKOFF_VALIDATION"
    assert state == "AVAILABLE"


def test_atr_fallback_is_not_promoted_to_governed_invalidation() -> None:
    row = {
        "structural_stop": 95.0,
        "stop_loss": 95.0,
        "structural_stop_source": "ATR_FALLBACK",
    }
    value, source, state = select_directional_invalidation(row, "CALL", 100.0)
    assert value is None
    assert source == "MISSING_AUTHORITATIVE_STOP"
    assert state == "MISSING"


def test_options_preserves_frozen_discovery_direction_and_rebuilds_put_geometry() -> None:
    from scripts.avshunter_options_intelligence import parse_structural_context

    context = parse_structural_context(pd.Series({
        "ticker": "FROZEN",
        "run_id": "20990101_010101",
        "direction": "PUT",
        "discovery_direction_preliminary": "PUT",
        "direction_authority": "DISCOVERY_GOVERNED",
        "discovery_direction_basis": "test frozen PUT",
        # Deliberately contradictory legacy intent: Options must not flip it.
        "precor_intent": "BUY_SETUP",
        "dominant_trend": "BULLISH",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "wyckoff_validation_structural_invalidation_level": 105.0,
        "structural_target": 90.0,
        "horizon_bucket": "6_10d",
    }))
    assert context["final_direction"] == "PUT"
    assert context["governed_direction_authority"] == "DISCOVERY_GOVERNED"
    assert context["stop"] == 105.0
    assert context["structural_target"] == 90.0
    assert context["preferred_strategy"] == "LONG_PUT"


def test_critical_eod_numeric_missingness_remains_none() -> None:
    assert _first_optional_flt({}, "invalidation_spot") is None
    assert _first_optional_flt({"invalidation_spot": ""}, "invalidation_spot") is None
    assert _first_optional_flt({"invalidation_spot": 105.0}, "invalidation_spot") == 105.0


def test_manifest_semantic_health_cannot_report_100_with_handoff_defects() -> None:
    result = _semantic_handoff_health(
        {"missing_selected_handoff": {"invalidation_spot": 454, "contract_multiplier": 74}},
        1400,
    )
    assert result["semantic_defect_count"] == 454
    assert result["semantic_coverage_score"] == 68
    assert result["pipeline_semantic_health"] == "FAILED"


def test_lab_prefers_governed_horizon_and_hold_over_contract_dte() -> None:
    lab = _load_lab_module()
    row = {
        "time_horizon": "6_10d",
        "hold_period": "3-8 days",
        "contract_dte": 25,
    }
    assert lab._extract_time_horizon(row) == "6-10D"
    assert lab._extract_hold_period(row) == "3-8 days"


def test_lab_uses_planned_hold_sessions_when_label_is_absent() -> None:
    lab = _load_lab_module()
    assert lab._extract_hold_period({"planned_hold_sessions": 10}) == "10 days"
