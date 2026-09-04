from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from contracts.direction_governance import (
    DIR_CALC_VERSION,
    preliminary_discovery_direction,
    resolve_governed_direction,
    structural_direction,
    validate_direction_record,
)
from eod_candidate_engine import (
    _direction_evidence,
    _invalidate_direction_dependent_contract,
)
from execution_gate import execution_gate
from morning_gate import run_gate
from scripts.avshunter_options_intelligence import (
    _common_options_handoff_fields,
    parse_structural_context,
    process_ticker,
)


def test_options_intelligence_direct_launch_resolves_repository_packages() -> None:
    """Mirror the orchestrator's direct-file launch, not pytest's import path."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "avshunter_options_intelligence.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 1
    assert "Usage: python avshunter_options_intelligence.py" in combined
    assert "ModuleNotFoundError" not in combined


def _record(side: str, **row) -> dict:
    return resolve_governed_direction(
        ticker=row.pop("ticker", "TEST"),
        run_id=row.pop("run_id", "20990101_010101"),
        discovery_direction=row.pop("discovery_direction", side),
        governed_direction=side,
        governed_basis=row.pop("governed_basis", f"test={side}"),
        row=row,
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )


def test_discovery_ambiguity_never_defaults_to_call() -> None:
    assert preliminary_discovery_direction("", "") == "UNRESOLVED"
    assert preliminary_discovery_direction("MIXED", "WAIT") == "UNRESOLVED"


def test_structural_direction_table_is_closed_and_symmetric() -> None:
    assert structural_direction("BUY_SETUP", "BEARISH")[0] == "CALL"
    assert structural_direction("SELL_SETUP", "BULLISH")[0] == "PUT"
    assert structural_direction("TRANSITION", "BULLISH")[0] == "CALL"
    assert structural_direction("TRANSITION", "BEARISH")[0] == "PUT"
    assert structural_direction("TRANSITION", "MIXED")[0] == "STRANGLE"
    assert structural_direction("WAIT", "BULLISH")[0] == "UNRESOLVED"


def test_non_directional_resolution_requires_two_independent_families() -> None:
    one_family = _record("STRANGLE", vanguard_edge_direction="CALL")
    assert one_family["final_direction"] == "STRANGLE"
    assert one_family["direction_resolution_path"] == "UNRESOLVED"

    two_families = _record(
        "STRANGLE",
        vanguard_edge_direction="CALL",
        catalyst_direction_bias="CALL",
        catalyst_detected=True,
        catalyst_data_quality="CONFIRMED",
        catalyst_direction_independent=True,
        catalyst_direction_source="catalyst_calendar",
        catalyst_direction_source_field="catalyst_direction_bias",
    )
    assert two_families["final_direction"] == "CALL"
    assert two_families["direction_resolution_path"] == "DIRECTION_RESOLVED_PRECONTRACT"
    chain = json.loads(two_families["direction_resolution_chain_json"])
    assert {item["family"] for item in chain[0]["evidence"]} == {"ACTUARIAL", "CATALYST"}


def test_resolution_policy_is_mirror_symmetric() -> None:
    call = _record(
        "STRANGLE",
        vanguard_edge_direction="CALL",
        catalyst_direction_bias="CALL",
        catalyst_detected=True,
        catalyst_data_quality="CONFIRMED",
        catalyst_direction_independent=True,
        catalyst_direction_source="catalyst_calendar",
        catalyst_direction_source_field="catalyst_direction_bias",
    )
    put = _record(
        "STRANGLE",
        vanguard_edge_direction="PUT",
        catalyst_direction_bias="PUT",
        catalyst_detected=True,
        catalyst_data_quality="CONFIRMED",
        catalyst_direction_independent=True,
        catalyst_direction_source="catalyst_calendar",
        catalyst_direction_source_field="catalyst_direction_bias",
    )
    assert call["final_direction"] == "CALL"
    assert put["final_direction"] == "PUT"
    assert call["direction_resolution_winning_share"] == put["direction_resolution_winning_share"]
    assert call["direction_resolution_margin"] == put["direction_resolution_margin"]


def test_confirmed_structure_cannot_be_overwritten_by_other_evidence() -> None:
    record = _record(
        "CALL",
        vanguard_edge_direction="PUT",
        catalyst_direction_bias="PUT",
        catalyst_detected=True,
        catalyst_data_quality="CONFIRMED",
    )
    assert record["final_direction"] == "CALL"
    assert record["direction_resolution_path"] == "DIRECTION_CONFIRMED"
    assert json.loads(record["direction_resolution_chain_json"]) == []


def test_no_catalyst_placeholder_bias_is_not_resolution_evidence() -> None:
    record = _record(
        "STRANGLE",
        vanguard_edge_direction="CALL",
        catalyst_direction_bias="CALL",
        catalyst_detected=False,
        catalyst_data_quality="NO_CATALYST",
        catalyst_trade_class="STRUCTURE_ONLY_NO_CATALYST",
    )
    assert record["final_direction"] == "STRANGLE"
    evidence = json.loads(record["direction_resolution_evidence_json"])
    assert [item["family"] for item in evidence] == ["ACTUARIAL"]


def test_catalyst_direction_without_independent_provenance_is_excluded() -> None:
    record = _record(
        "STRANGLE",
        vanguard_edge_direction="CALL",
        catalyst_direction_bias="CALL",
        catalyst_detected=True,
        catalyst_data_quality="CONFIRMED",
    )
    assert record["final_direction"] == "STRANGLE"
    evidence = json.loads(record["direction_resolution_evidence_json"])
    assert [item["family"] for item in evidence] == ["ACTUARIAL"]
    assert "catalyst_direction_without_independent_provenance" in json.loads(
        record["direction_excluded_evidence_json"]
    )


def test_direction_record_hash_and_flat_fields_are_enforced() -> None:
    row = _record("PUT")
    valid, reason = validate_direction_record(row)
    assert valid is True
    assert reason == "DIRECTION_INTEGRITY_CONFIRMED"

    tampered = {**row, "final_direction": "CALL"}
    valid, reason = validate_direction_record(tampered)
    assert valid is False
    assert "FLAT_FIELD_MISMATCH" in reason

    broken_hash = {**row, "governed_direction_record_sha256": "0" * 64}
    valid, reason = validate_direction_record(broken_hash)
    assert valid is False
    assert reason == "DIRECTION_RECORD_HASH_MISMATCH"


def test_options_success_and_stand_down_handoffs_both_publish_direction_lineage() -> None:
    context = parse_structural_context(pd.Series({
        "ticker": "LINEAGE",
        "run_id": "20990101_010101",
        "precor_intent": "BUY_SETUP",
        "dominant_trend": "BULLISH",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "stop_loss": 95.0,
    }))
    fields = _common_options_handoff_fields(context)
    valid, reason = validate_direction_record(fields)
    assert valid is True
    assert reason == "DIRECTION_INTEGRITY_CONFIRMED"

    source = Path(
        "scripts/avshunter_options_intelligence.py"
    ).read_text(encoding="utf-8")
    assert source.count("**_common_options_handoff_fields(ctx)") == 2


def test_direction_record_enforces_target_invalidation_and_contract_side() -> None:
    record = _record("PUT")
    row = {
        **record,
        "signal_price": 100.0,
        "structural_target": 90.0,
        "invalidation_price": 105.0,
        "selected_contract_side": "PUT",
    }
    assert validate_direction_record(row)[0] is True
    assert validate_direction_record({**row, "structural_target": 110.0})[1] == "PUT_TARGET_NOT_BELOW_SIGNAL"
    assert "SELECTED_CONTRACT_DIRECTION_MISMATCH" in validate_direction_record(
        {**row, "selected_contract_side": "CALL"}
    )[1]


def test_options_stage_leaves_wait_unresolved_without_contract_strategy() -> None:
    context = parse_structural_context(pd.Series({
        "ticker": "WAIT",
        "run_id": "20990101_010101",
        "precor_intent": "WAIT",
        "dominant_trend": "MIXED",
        "direction": "CALL",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "vanguard_edge_direction": "CALL",
    }))
    assert context["governed_direction"] == "UNRESOLVED"
    assert context["final_direction"] == "UNRESOLVED"
    assert context["preferred_strategy"] == "NO_DIRECTIONAL_STRATEGY"
    assert context["structural_target"] is None


def test_unresolved_direction_suppresses_option_chain_request() -> None:
    row = pd.Series({
        "ticker": "WAIT",
        "run_id": "20990101_010101",
        "precor_intent": "WAIT",
        "dominant_trend": "MIXED",
        "direction": "CALL",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "vanguard_edge_direction": "CALL",
    })
    with patch(
        "scripts.avshunter_options_intelligence.fetch_chain",
        side_effect=AssertionError("option chain must not be requested"),
    ):
        result = process_ticker(row)
    assert result["options_verdict"] == "STAND_DOWN"
    assert result["final_direction"] == "UNRESOLVED"
    assert "chain request suppressed" in result["stand_down_reason"]


def test_eod_consumes_gdr_and_invalidates_wrong_side_contract() -> None:
    row = {
        "ticker": "ABC",
        "recommended_contract": "ABC260101C00100000",
        "contract_symbol": "ABC260101C00100000",
        "contract_delta": 0.45,
        "contract_mid": 2.0,
        **_record("PUT", ticker="ABC"),
    }
    direction = _direction_evidence(row)
    assert direction["resolved_direction"] == "PUT"
    assert direction["footprint_lock_status"] == "DECOMMISSIONED_GDR_AUTHORITY"
    assert direction["direction_contract_reselection_required"] == "TRUE"
    invalidated = _invalidate_direction_dependent_contract(row, direction)
    assert invalidated["recommended_contract"] == ""
    assert invalidated["direction_invalidated_contract_symbol"] == "ABC260101C00100000"
    assert invalidated["economics_recompute_required"] == "TRUE"


def test_execution_gate_blocks_invalid_direction_before_monetisability() -> None:
    invalid = {
        "ticker": "BAD",
        "morning_execution_permission": "GO",
        "monetisability_state": "MONETISABLE",
    }
    result = execution_gate(invalid)
    assert result["final_action"] == "BLOCK"
    assert result["gate_reason"].startswith("DIRECTION_INTEGRITY_FAILED")


def test_morning_gate_routes_unresolved_direction_to_stand_down() -> None:
    row = {
        "ticker": "WAIT",
        "run_id": "20990101_010101",
        "authority_source_stage": "FINAL_EXECUTION",
        "final_route": "OPTIONS_GO_REVIEW",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": "TRUE",
        **_record("UNRESOLVED", ticker="WAIT"),
    }
    result = run_gate(
        row,
        live_data={},
        current_regime="NEUTRAL",
        spread_threshold=0.15,
    )
    assert result["verdict"] == "BLOCK"
    assert result["morning_execution_permission"] == "NO_GO_DIRECTION"
    assert result["morning_execution_lane"] == "DIRECTION_INTEGRITY_FAILED"


def test_contract_version_is_explicit() -> None:
    assert _record("CALL")["dir_calc_version"] == DIR_CALC_VERSION
