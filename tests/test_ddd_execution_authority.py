from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from domain.execution_authority import (
    EXECUTION_AUTHORITY_POLICY_VERSION,
    action_is_within_execution_ceiling,
    advisory_authority_violations,
    assert_no_unauthorised_capital,
    decide_execution_authority,
    execution_authority_contract_violations,
    govern_execution_result,
    morning_validation_authority_fields,
)
from domain.run_planning import RequestedAction
from domain.thesis_direction import FrozenThesis
from contracts.direction_governance import resolve_governed_direction
from execution_gate import execution_gate
from canonical_data.run_plan import resolve_run_plan
from orchestrator.dynamic_validation import UnderlyingObservation, validate_thesis


def _execution_row(**overrides) -> dict:
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id="DDD-PHASE7",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="TEST",
        row={},
        decided_at_utc="2026-09-04T15:00:00Z",
    )
    row = {
        "ticker": "AAA",
        "pipeline_mode": "MORNING_VALIDATION",
        "governed_direction": "CALL",
        "canonical_direction": "CALL",
        "direction": "CALL",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "contract_symbol": "AAA261016C00100000",
        "morning_selected_contract_symbol": "AAA261016C00100000",
        "selected_contract_side": "CALL",
        "live_contract_bid": 4.90,
        "live_contract_ask": 5.00,
        "live_contract_mid": 4.95,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.40,
        "live_iv_rank": 50,
        "signal_price": 100.0,
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "OK",
        "execution_viability_contract_symbol": "AAA261016C00100000",
        "macro_capital_authority": "ADVISORY_ONLY",
        "ev3_capital_authority": "ADVISORY_ONLY",
        "ms_authority": "ADVISORY_ONLY",
        "monetisability_status": "COMPLETE",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": "AAA261016C00100000",
        "lifecycle_contract_version": "options-liquidity-lifecycle-v2",
        "thesis_state": "ACTIVE",
        "liquidity_state": "EXECUTABLE_NOW",
        "morning_transition_state": "EXECUTABLE_NOW",
        "remaining_runway_state": "THESIS_ACTIVE",
        "executable_now": True,
        "maturation_execution_authority": False,
        **direction,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    ("action", "eligibility", "permission", "human"),
    [
        ("BUY_NOW", "ELIGIBLE_NOW", "HUMAN_APPROVAL_REQUIRED", True),
        ("BUY_SMALL", "ELIGIBLE_LIMITED", "HUMAN_APPROVAL_REQUIRED", True),
        ("MANUAL_REVIEW", "REVIEW_REQUIRED", "REVIEW_ONLY", False),
        ("CONTRACT_REPAIR", "CONTRACT_REPAIR_REQUIRED", "REVIEW_ONLY", False),
        ("BLOCK", "NOT_ELIGIBLE", "NO", False),
        ("SKIP", "NOT_ELIGIBLE", "NO", False),
    ],
)
def test_action_has_one_capital_semantics(action, eligibility, permission, human) -> None:
    decision = decide_execution_authority(action, "TEST")
    assert decision.action == action
    assert decision.eligibility == eligibility
    assert decision.final_capital_permission == permission
    assert decision.human_approval_required is human
    assert decision.execution_authorized is False
    assert decision.can_grant_capital is False


def test_execution_ceiling_is_monotonic() -> None:
    assert action_is_within_execution_ceiling("BUY_SMALL", "BUY_NOW")
    assert action_is_within_execution_ceiling("BLOCK", "BUY_SMALL")
    assert action_is_within_execution_ceiling("CONTRACT_REPAIR", "MANUAL_REVIEW")
    assert not action_is_within_execution_ceiling("BUY_NOW", "BUY_SMALL")
    assert not action_is_within_execution_ceiling("MANUAL_REVIEW", "BLOCK")
    assert not action_is_within_execution_ceiling("UNRECOGNISED", "BUY_NOW")


def test_advisory_subsystem_cannot_claim_capital_authority() -> None:
    evidence = {
        "macro_capital_authority": "CAPITAL_ALLOWED",
        "ev3_capital_authority": "ADVISORY_ONLY",
        "ms_can_grant_capital": True,
    }
    assert advisory_authority_violations(evidence) == (
        "macro_capital_authority=CAPITAL_ALLOWED",
        "ms_can_grant_capital=TRUE",
    )
    result = govern_execution_result(
        evidence, action="BUY_NOW", reason="OK"
    )
    assert result["final_action"] == "BLOCK"
    assert result["execution_eligibility_state"] == "NOT_ELIGIBLE"
    assert result["final_capital_permission"] == "NO"
    assert result["gate_reason"].startswith("ADVISORY_AUTHORITY_VIOLATION")


def test_morning_validation_never_grants_capital() -> None:
    go = morning_validation_authority_fields("GO")
    flag = morning_validation_authority_fields("FLAG")
    block = morning_validation_authority_fields("BLOCK")
    assert go["morning_authority_state"] == "MORNING_VALIDATED"
    assert go["final_capital_permission"] == "HUMAN_APPROVAL_REQUIRED"
    assert flag["final_capital_permission"] == "REVIEW_ONLY"
    assert block["final_capital_permission"] == "NO"
    assert all(
        item["execution_authorized"] is False
        and item["morning_can_grant_capital"] is False
        for item in (go, flag, block)
    )


def test_execution_gate_stamps_central_authority_contract() -> None:
    result = execution_gate(_execution_row())
    assert result["final_action"] == "BUY_NOW"
    assert result["execution_eligibility_state"] == "ELIGIBLE_NOW"
    assert result["execution_authority_source"] == "FINAL_EXECUTION_GATE"
    assert result["execution_authority_policy_version"] == EXECUTION_AUTHORITY_POLICY_VERSION
    assert result["final_capital_permission"] == "HUMAN_APPROVAL_REQUIRED"
    assert result["execution_requires_human_approval"] is True
    assert result["execution_authorized"] is False
    assert result["execution_can_grant_capital"] is False


def test_execution_gate_blocks_hostile_advisory_authority() -> None:
    result = execution_gate(
        _execution_row(macro_capital_authority="AUTOMATED_CAPITAL")
    )
    assert result["final_action"] == "BLOCK"
    assert result["final_capital_permission"] == "NO"
    assert "ADVISORY_AUTHORITY_VIOLATION" in result["gate_reason"]


def test_lab_can_validate_a_stamped_baton_without_re_adjudication() -> None:
    valid = execution_gate(_execution_row())
    assert execution_authority_contract_violations(valid) == ()
    forged = {**valid, "execution_authorized": True}
    violations = execution_authority_contract_violations(forged)
    assert any("execution_authorized" in item for item in violations)


def test_lab_defence_blocks_a_forged_capital_baton() -> None:
    from contracts.lab_control import opportunity_book_row

    forged = execution_gate(_execution_row())
    forged["execution_authorized"] = True
    forged["lab_verdict"] = "GO"
    forged["lab_tradeable"] = True
    result = opportunity_book_row(forged, "DDD-PHASE7", 1)
    assert result["lab_verdict"] == "BLOCKED"
    assert result["lab_tradeable"] is False
    assert result["final_action"] == "BLOCK"
    assert result["execution_lock_reason"].startswith(
        "EXECUTION_AUTHORITY_CONTRACT_VIOLATION"
    )


def test_intermediate_validation_callback_cannot_grant_capital() -> None:
    session = date(2026, 9, 3)
    plan = resolve_run_plan(
        requested_action=RequestedAction.VALIDATE,
        as_of_utc=datetime(2026, 9, 4, 15, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 4, 15, tzinfo=timezone.utc),
        existing_thesis_id="THESIS-AAA",
        existing_thesis_session=session,
        authorised_tickers=("AAA",),
        pipeline_run_id="DDD-PHASE7",
    )
    thesis = FrozenThesis(
        "THESIS-AAA", "AAA", "CALL", session.isoformat(),
        100.0, 110.0, 95.0, "AAA261016C00100000",
        trigger=101.0, maximum_entry=106.0,
    )
    observation = UnderlyingObservation(
        "OBS-1", "AAA", 102.0, "2026-09-04T15:00:00Z", "DATASET-1"
    )
    with pytest.raises(ValueError, match="UNAUTHORISED_CAPITAL_GRANT"):
        validate_thesis(
            plan,
            thesis,
            resolve_underlying=lambda *_: observation,
            resolve_option_quote=lambda *_: {"observation_id": "QUOTE-1"},
            execution_gate=lambda *_: {
                "action": "BUY_NOW",
                "execution_authorized": True,
            },
        )


def test_domain_module_has_no_infrastructure_dependency() -> None:
    source = (
        Path(__file__).parents[1] / "domain" / "execution_authority.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "import pandas",
        "import numpy",
        "canonical_data",
        "requests",
        "sqlite3",
        "Path(",
    ):
        assert forbidden not in source


def test_assertion_rejects_only_real_capital_claims() -> None:
    assert_no_unauthorised_capital(
        {
            "action": "ELIGIBLE",
            "execution_authorized": False,
            "macro_capital_authority": "ADVISORY_ONLY",
        }
    )
    with pytest.raises(ValueError, match="execution_can_grant_capital"):
        assert_no_unauthorised_capital({"execution_can_grant_capital": True})
