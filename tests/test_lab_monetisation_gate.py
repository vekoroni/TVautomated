from __future__ import annotations

from contracts.direction_governance import resolve_governed_direction
from contracts.lab_control import opportunity_book_row, resolve_lab_tradeability


def _signal(ev_decision: str, rr: object) -> dict:
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id="RUN1",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )
    return {
        "ticker": "AAA",
        "options_verdict": "EXECUTE",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "thesis_decision": "GO",
        "strike": 100,
        "expiry": "2099-02-01",
        "premium_mid": 1.25,
        "spread_pct": 0.05,
        "instrument": "LONG_CALL",
        "selected_structure": "LONG_SINGLE",
        "selected_structure_hydration_status": "COMPLETE",
        "contract_symbol": "AAA270201C00100000",
        "mv__morning_execution_permission": "GO",
        "mv__execution_permission": "GO",
        "mv__live_validation_state": "CONFIRMED",
        "ev2_decision_hint": ev_decision,
        "rr_options": rr,
        "selected_contract_side": "CALL",
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "TEST_GOVERNED_THESIS",
        **direction,
    }


def _resolve(ev_decision: str, rr: object) -> dict:
    return resolve_lab_tradeability(
        _signal(ev_decision, rr),
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )


def test_execution_gate_is_the_only_morning_lab_permission_authority() -> None:
    expected = {
        "BUY_NOW": ("GO", True),
        "BUY_SMALL": ("GO_LIMIT", True),
        "CONTRACT_REPAIR": ("CONTRACT_REPAIR", False),
        "MANUAL_REVIEW": ("MANUAL_REVIEW", False),
        "BLOCK": ("BLOCKED", False),
    }
    for action, (verdict, tradeable) in expected.items():
        signal = _signal("AVOID", -99)
        signal.update(
            {
                "final_action": action,
                "gate_reason": "TEST_GATE_REASON",
                "monetisability_state": "MONETISABLE",
            }
        )
        result = resolve_lab_tradeability(
            signal,
            {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
        )
        assert result["lab_verdict"] == verdict
        assert result["lab_tradeable"] is tradeable


def test_live_spread_cannot_override_execution_gate_buy_action() -> None:
    signal = _signal("MODERATE", -1)
    signal.update(
        {
            "final_action": "BUY_SMALL",
            "gate_reason": "OK",
            "spread_pct": 99.0,
            "live_contract_spread_pct": 0.7968,
            "monetisability_state": "LIMITED",
        }
    )
    result = resolve_lab_tradeability(
        signal,
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert result["lab_verdict"] == "GO_LIMIT"
    assert result["lab_tradeable"] is True


def test_spread_policy_has_executable_review_and_block_lanes() -> None:
    executable = _signal("MODERATE", 1.5)
    executable["spread_pct"] = 0.18
    result = resolve_lab_tradeability(
        executable,
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert result["lab_verdict"] == "GO"
    assert result["lab_tradeable"] is True
    assert result["spread_policy_state"] == "EXECUTABLE"

    for spread in (0.181, 0.25, 20.0, 25.0):
        review = _signal("MODERATE", 1.5)
        review["spread_pct"] = spread
        result = resolve_lab_tradeability(
            review,
            {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
        )
        assert result["lab_verdict"] == "MANUAL_LIQUIDITY_REVIEW"
        assert result["lab_tradeable"] is False
        assert result["spread_policy_state"] == "MANUAL_LIQUIDITY_REVIEW"
        assert any("MANUAL_LIQUIDITY_REVIEW" in flag for flag in result["conflict_flags"])

    for spread in (0.251, 25.1):
        blocked = _signal("MODERATE", 1.5)
        blocked["spread_pct"] = spread
        result = resolve_lab_tradeability(
            blocked,
            {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
        )
        assert result["lab_verdict"] == "BLOCKED"
        assert result["lab_tradeable"] is False
        assert result["spread_policy_state"] == "BLOCKED_ABOVE_ABSOLUTE_MAX"
        assert "SPREAD_TOO_WIDE" in result["veto_flags"]


def test_only_valid_long_single_contracts_are_executable() -> None:
    valid = resolve_lab_tradeability(
        _signal("MODERATE", 1.5),
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert valid["lab_tradeable"] is True
    assert valid["options_research_route"] == "PRODUCTION_LONG_SINGLE"

    vertical = _signal("MODERATE", 1.5)
    vertical.update(
        {
            "instrument": "BULL_CALL_DEBIT",
            "selected_structure": "BULL_CALL_DEBIT",
            "contract_symbol": (
                "BULL_CALL_DEBIT:AAA270201C00100000/AAA270201C00110000"
            ),
        }
    )
    result = resolve_lab_tradeability(
        vertical,
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert result["lab_verdict"] == "WAIT"
    assert result["lab_tradeable"] is False
    assert result["options_research_route"] == "RESEARCH_ONLY_NON_LONG_SINGLE"
    assert result["options_research_permission"] == "NOT_EXECUTABLE"
    assert any("NON_PRODUCTION_OPTIONS_STRUCTURE" in flag for flag in result["advisory_flags"])

    strangle = _signal("MODERATE", 1.5)
    strangle.update(
        {
            "instrument": "STRANGLE",
            "selected_structure": "STRANGLE",
            "contract_symbol": "AAA270201C00100000/AAA270201P00100000",
        }
    )
    result = resolve_lab_tradeability(
        strangle,
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    assert result["lab_verdict"] == "WAIT"
    assert result["lab_tradeable"] is False
    assert result["options_research_route"] == "RESEARCH_ONLY_NON_LONG_SINGLE"


def test_upstream_quote_snapshot_identity_is_immutable() -> None:
    sig = _signal("MODERATE", 1.5)
    sig.update(
        {
            "lab_verdict": "GO",
            "lab_tradeable": True,
            "selected_quote_snapshot_id": "QUOTE1:0123456789abcdef01234567",
        }
    )
    row = opportunity_book_row(sig, "RUN1", 1)
    assert row["selected_quote_snapshot_id"] == "QUOTE1:0123456789abcdef01234567"

    legacy = _signal("MODERATE", 1.5)
    legacy.update({"lab_verdict": "GO", "lab_tradeable": True})
    generated = opportunity_book_row(legacy, "RUN1", 1)
    assert generated["selected_quote_snapshot_id"].startswith("QUOTE1:")
    assert generated["selected_quote_snapshot_id"]


def test_opportunity_book_preserves_execution_and_monetisability_fields() -> None:
    sig = _signal("AVOID", -1)
    sig.update(
        {
            "final_action": "BUY_NOW",
            "gate_reason": "OK",
            "monetisability_status": "COMPLETE",
            "monetisability_state": "MONETISABLE",
            "monetisability_target_profit_pct": 42.5,
            "monetisability_contract_symbol": sig["contract_symbol"],
        }
    )
    resolved = resolve_lab_tradeability(
        sig,
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )
    sig.update(resolved)
    row = opportunity_book_row(sig, "RUN1", 1)
    assert row["final_action"] == "BUY_NOW"
    assert row["lab_verdict"] == "GO"
    assert row["monetisability_state"] == "MONETISABLE"
    assert row["monetisability_target_profit_pct"] == 42.5
