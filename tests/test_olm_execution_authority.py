from __future__ import annotations

from unittest.mock import patch

import pytest

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import opportunity_book_row
from contracts.options_liquidity_execution_guard import (
    evaluate_olm_execution_guard,
)
from execution_gate import execution_gate, run_execution_gate
from morning_handoff_finalizer import (
    MorningHandoffError,
    _olm_execution_mismatches,
    finalize_morning_handoff,
)


RUN_ID = "20990102_083000"
CONTRACT = "AAA260918C00100000"


def _row(**overrides) -> dict:
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id=RUN_ID,
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-02T08:30:00+00:00",
    )
    row = {
        "run_id": RUN_ID,
        "ticker": "AAA",
        "pipeline_mode": "MORNING_VALIDATION",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "contract_symbol": CONTRACT,
        "morning_selected_contract_symbol": CONTRACT,
        "selected_contract_side": "CALL",
        "live_contract_bid": 4.90,
        "live_contract_ask": 5.00,
        "live_contract_mid": 4.95,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.40,
        "live_iv_rank": 50,
        "contract_bid": 4.90,
        "contract_ask": 5.00,
        "contract_mid": 4.95,
        "contract_delta": 0.45,
        "signal_price": 100.0,
        "strike": 100.0,
        "expiry": "2099-01-19",
        "dte": 17,
        "premium_mid": 4.95,
        "execution_viability_policy_version": "long-option-v1",
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "OK",
        "execution_viability_eligible": True,
        "execution_viability_contract_symbol": CONTRACT,
        "execution_viability_bid": 4.90,
        "execution_viability_ask": 5.00,
        "execution_viability_spread_pct": 0.020202,
        "execution_viability_spread_denominator": "MID",
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "TEST_GOVERNED_THESIS",
        "monetisability_status": "COMPLETE",
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": CONTRACT,
        "lifecycle_contract_version": "options-liquidity-lifecycle-v1",
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
    ("transition", "expected_action"),
    [
        ("THESIS_INVALIDATED", "BLOCK"),
        ("MOVE_ALREADY_REALIZED", "BLOCK"),
        ("CONTRACT_REPRICE_REQUIRED", "CONTRACT_REPAIR"),
        ("WAIT_FOR_PULLBACK", "MANUAL_REVIEW"),
        ("GAP_CONFIRMATION_EXTENDED", "MANUAL_REVIEW"),
        ("LIQUIDITY_STILL_PENDING", "MANUAL_REVIEW"),
        ("EOD_PENDING_MORNING_REQUOTE", "MANUAL_REVIEW"),
        ("LEGACY_LIFECYCLE_NOT_EVALUATED", "MANUAL_REVIEW"),
        ("EXECUTABLE_NOW", "BUY_NOW"),
        ("GAP_CONFIRMATION_WITH_RUNWAY", "BUY_NOW"),
    ],
)
def test_full_morning_transition_matrix(transition: str, expected_action: str) -> None:
    result = execution_gate(_row(morning_transition_state=transition), require_olm=True)
    assert result["final_action"] == expected_action


def test_tc07_invalidated_thesis_cannot_receive_buy_now() -> None:
    result = execution_gate(
        _row(
            thesis_state="INVALIDATED",
            remaining_runway_state="THESIS_INVALIDATED",
            morning_transition_state="THESIS_INVALIDATED",
            executable_now=False,
        ),
        require_olm=True,
    )
    assert result["final_action"] == "BLOCK"
    assert result["gate_reason"] == "OLM_THESIS_INVALIDATED"
    assert result["olm_guard_pass"] is False


def test_corrected_v2_lifecycle_contract_is_supported_by_execution_guard() -> None:
    result = execution_gate(
        _row(lifecycle_contract_version="options-liquidity-lifecycle-v2"),
        require_olm=True,
    )
    assert result["final_action"] == "BUY_NOW"
    assert result["olm_guard_pass"] is True


def test_terminal_thesis_precedes_contradictory_executable_transition() -> None:
    result = execution_gate(
        _row(
            thesis_state="INVALIDATED",
            remaining_runway_state="THESIS_INVALIDATED",
            morning_transition_state="EXECUTABLE_NOW",
        ),
        require_olm=True,
    )
    assert result["final_action"] == "BLOCK"
    assert result["olm_guard_state_consistent"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"liquidity_state": "LIQUIDITY_PENDING"},
        {"executable_now": False},
        {"thesis_state": "DATA_INCOMPLETE"},
        {"lifecycle_contract_version": "unknown-v9"},
    ],
)
def test_executable_transition_requires_consistent_versioned_evidence(overrides: dict) -> None:
    result = execution_gate(_row(**overrides), require_olm=True)
    assert result["final_action"] == "MANUAL_REVIEW"
    assert result["olm_guard_pass"] is False


def test_unknown_transition_fails_closed() -> None:
    result = execution_gate(_row(morning_transition_state="NEW_UNGOVERNED_STATE"), require_olm=True)
    assert result["final_action"] == "BLOCK"
    assert result["gate_reason"].startswith("OLM_TRANSITION_UNRECOGNISED")


def test_maturation_score_and_conviction_cannot_override_veto() -> None:
    result = execution_gate(
        _row(
            morning_transition_state="WAIT_FOR_PULLBACK",
            maturation_score_1d=100.0,
            pse_final_size=0.05,
            kelly_verdict="SIZE_OK",
        ),
        require_olm=True,
    )
    assert result["final_action"] == "MANUAL_REVIEW"


def test_veto_or_defer_happens_before_any_quote_fetch() -> None:
    row = _row(
        morning_transition_state="LIQUIDITY_STILL_PENDING",
        liquidity_state="LIQUIDITY_PENDING",
        executable_now=False,
    )
    for field in tuple(row):
        if field.startswith("live_contract_") or field in {"contract_bid", "contract_ask", "contract_mid"}:
            row.pop(field, None)
    with patch(
        "execution_gate.get_live_option_data",
        side_effect=AssertionError("OLM-deferred row must not fetch a quote"),
    ):
        result = execution_gate(row, require_olm=True)
    assert result["final_action"] == "MANUAL_REVIEW"


def test_existing_valid_action_and_advisory_monetisability_remain_compatible() -> None:
    assert execution_gate(_row(), require_olm=True)["final_action"] == "BUY_NOW"
    limited = execution_gate(_row(monetisability_state="LIMITED"), require_olm=True)
    assert limited["final_action"] == "BUY_NOW"
    assert limited["monetisability_state"] == "LIMITED"


def test_direct_legacy_caller_remains_compatible_but_production_batch_requires_olm(tmp_path) -> None:
    legacy = _row()
    for field in (
        "lifecycle_contract_version", "thesis_state", "liquidity_state",
        "morning_transition_state", "remaining_runway_state", "executable_now",
    ):
        legacy.pop(field, None)
    assert execution_gate(legacy)["final_action"] == "BUY_NOW"

    rows, summary = run_execution_gate([legacy], RUN_ID, tmp_path)
    assert rows[0]["final_action"] == "MANUAL_REVIEW"
    assert rows[0]["gate_reason"] == "OLM_LIFECYCLE_REQUIRED"
    assert summary["olm_guard_disposition_counts"] == {"MANUAL_REVIEW": 1}


def test_lab_defence_in_depth_blocks_impossible_buy_now() -> None:
    unsafe = _row(
        final_action="BUY_NOW",
        lab_verdict="GO",
        lab_tradeable=True,
        thesis_state="INVALIDATED",
        remaining_runway_state="THESIS_INVALIDATED",
        morning_transition_state="THESIS_INVALIDATED",
        executable_now=False,
    )
    result = opportunity_book_row(unsafe, RUN_ID, 1)
    assert result["lab_tradeable"] is False
    assert result["lab_verdict"] == "BLOCKED"
    assert result["final_action"] == "BLOCK"
    assert result["execution_lock_reason"] == "OLM_THESIS_INVALIDATED"


def test_lab_preserves_valid_execution_gate_action() -> None:
    valid = _row(final_action="BUY_NOW", lab_verdict="GO", lab_tradeable=True)
    result = opportunity_book_row(valid, RUN_ID, 1)
    assert result["lab_tradeable"] is True
    assert result["lab_verdict"] == "GO"
    assert result["final_action"] == "BUY_NOW"
    assert result["olm_guard_pass"] is True


def test_finalizer_invariant_detects_action_above_olm_ceiling() -> None:
    row = _row(
        final_action="BUY_NOW",
        morning_transition_state="WAIT_FOR_PULLBACK",
    )
    decision = evaluate_olm_execution_guard(row, require_contract=True)
    row.update(decision.as_fields())
    mismatches = _olm_execution_mismatches([row])
    assert any("OLM_ACTION_EXCEEDS_MANUAL_REVIEW" in item for item in mismatches)


def test_finalizer_invariant_accepts_matching_guarded_action() -> None:
    row = execution_gate(_row(), require_olm=True)
    assert _olm_execution_mismatches([row]) == []


def test_finalizer_aborts_before_lab_publication_on_olm_authority_breach(tmp_path) -> None:
    unsafe = _row(
        final_action="BUY_NOW",
        morning_transition_state="WAIT_FOR_PULLBACK",
    )
    decision = evaluate_olm_execution_guard(unsafe, require_contract=True)
    unsafe.update(decision.as_fields())
    lab_writer = patch(
        "contracts.lab_control.write_final_opportunity_book",
        side_effect=AssertionError("Lab writer must not run after an OLM invariant breach"),
    )
    with patch(
        "execution_gate.run_execution_gate",
        return_value=([unsafe], {"gated_csv": str(tmp_path / "unused.csv")}),
    ), lab_writer as mocked_lab:
        with pytest.raises(MorningHandoffError, match="OLM Execution Gate invariant failed"):
            finalize_morning_handoff(
                RUN_ID,
                [unsafe],
                runs_dir=tmp_path,
                sync_interpreter=False,
            )
    mocked_lab.assert_not_called()
