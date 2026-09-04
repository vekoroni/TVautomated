from __future__ import annotations

from contracts.direction_governance import resolve_governed_direction
from execution_gate import execution_gate


def _row(state: str) -> dict:
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id="20990101_010101",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )
    return {
        "ticker": "AAA",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "contract_symbol": "AAA260918C00100000",
        "live_contract_bid": 4.9,
        "live_contract_ask": 5.0,
        "live_contract_mid": 4.95,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.40,
        "live_iv_rank": 50,
        "signal_price": 100,
        "monetisability_state": state,
        "monetisability_reason": "TEST",
        "monetisability_contract_symbol": "AAA260918C00100000",
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "QUOTE_WITHIN_EXECUTABLE_LIMIT",
        "execution_viability_contract_symbol": "AAA260918C00100000",
        "selected_contract_side": "CALL",
        **direction,
    }


def test_monetisable_contract_can_reach_buy_now() -> None:
    result = execution_gate(_row("MONETISABLE"))
    assert result["final_action"] == "BUY_NOW"


def test_limited_monetisability_is_advisory_to_execution_authority() -> None:
    result = execution_gate(_row("LIMITED"))
    assert result["final_action"] == "BUY_NOW"
    assert result["monetisability_state"] == "LIMITED"


def test_not_monetisable_state_is_preserved_without_overriding_execution() -> None:
    result = execution_gate(_row("NOT_MONETISABLE"))
    assert result["final_action"] == "BUY_NOW"
    assert result["monetisability_state"] == "NOT_MONETISABLE"


def test_monetisability_alternative_does_not_replace_selected_contract() -> None:
    row = _row("NOT_MONETISABLE")
    row["alternative_contract_1"] = "AAA260918C00105000"
    result = execution_gate(row)
    assert result["final_action"] == "BUY_NOW"
    assert result["contract_symbol"] == "AAA260918C00100000"
    assert result["alternative_contract_1"] == "AAA260918C00105000"


def test_missing_advisory_monetisability_does_not_create_a_false_veto() -> None:
    result = execution_gate(_row("DATA_MISSING"))
    assert result["final_action"] == "BUY_NOW"
    assert result["monetisability_state"] == "DATA_MISSING"


def test_missing_execution_viability_fails_closed() -> None:
    row = _row("MONETISABLE")
    row.pop("execution_viability_state")
    result = execution_gate(row)
    assert result["final_action"] == "CONTRACT_REPAIR"
    assert result["gate_reason"] == "EXECUTION_VIABILITY_STATE_MISSING"


def test_unknown_execution_viability_fails_closed() -> None:
    row = _row("MONETISABLE")
    row["execution_viability_state"] = "UNRECOGNISED"
    result = execution_gate(row)
    assert result["final_action"] == "CONTRACT_REPAIR"
    assert result["gate_reason"] == "EXECUTION_VIABILITY_STATE_UNKNOWN:UNRECOGNISED"
