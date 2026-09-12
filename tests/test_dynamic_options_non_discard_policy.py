from __future__ import annotations

from contracts.dynamic_options_policy import (
    DECISION_AUTHORITY_NONE,
    EXECUTION_AUTHORITY_HUMAN,
    advisory_authority_fields,
    apply_advisory_authority,
    eil_advisory_flags,
)
from contracts.handoff_contract import PRIORITY_EIL_PSE, build_truth_packet_from_row
from contracts.lab_control import resolve_lab_tradeability
from eod_candidate_engine import _monetisation_fit, classify_tier


def _quality_row(eil: str) -> dict:
    return {
        "ticker": "AAA",
        "direction": "CALL",
        "options_score": 50,
        "composite": 65,
        "sb_conv_score": 3,
        "trigger_quality": "STRONG",
        "trigger_go_eligible": "TRUE",
        "eil_v3_verdict": eil,
        "rr_underlying": 2.0,
    }


def test_policy_assigns_human_only_execution_authority() -> None:
    fields = advisory_authority_fields()
    assert fields["doi_decision_authority"] == DECISION_AUTHORITY_NONE
    assert fields["execution_authority"] == EXECUTION_AUTHORITY_HUMAN
    assert fields["entry_exit_timing_advisory_only"] is True
    row = apply_advisory_authority({"ticker": "AAA"})
    assert row["opportunity_retention_policy"] == "PRESERVE_AND_DISCLOSE"


def test_eil_block_is_disclosure_not_veto() -> None:
    assert eil_advisory_flags("BLOCKED") == ["EIL_ADVISORY_BLOCKED"]
    resolved = resolve_lab_tradeability(
        {"ticker": "AAA", "eil_v3_verdict": "BLOCKED", "thesis_decision": "GO"},
        {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": ["EOD_MORNING_VALIDATION_PENDING"]},
    )
    assert "EIL_BLOCKED" not in resolved["veto_flags"]
    assert "EIL_ADVISORY_BLOCKED" in resolved["advisory_flags"]
    assert resolved["lab_verdict"] != "BLOCKED"


def test_handoff_preserves_go_with_eil_advisory_block() -> None:
    packet = build_truth_packet_from_row(
        {"run_id": "R1", "ticker": "AAA", "thesis_decision": "GO", "eil_v3_verdict": "BLOCKED"},
        "TEST",
        PRIORITY_EIL_PSE,
        run_id="R1",
        run_mode="EVENING",
    )
    assert packet.packet_status == "PARTIAL"
    assert not packet.errors
    assert "EIL_ADVISORY_BLOCKED" in " ".join(packet.warnings)


def test_eil_verdict_does_not_change_eod_tier_or_score() -> None:
    execute = _quality_row("EXECUTE")
    blocked = _quality_row("BLOCKED")
    assert classify_tier(execute) == classify_tier(blocked)
    contract = {"contract_quality_score": 40.0}
    direction = {"direction_call_score": 4.0, "direction_put_score": 1.0}
    assert _monetisation_fit(execute, "A", contract, direction)["monetisation_fit_score"] == _monetisation_fit(
        blocked, "A", contract, direction
    )["monetisation_fit_score"]

