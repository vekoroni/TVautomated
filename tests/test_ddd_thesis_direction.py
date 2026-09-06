from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from canonical_data.option_liquidity_lifecycle import ThesisState as PersistenceThesisState
from canonical_data.run_plan import RequestedAction, resolve_run_plan
from contracts.direction_governance import normalise_side, structural_direction
from domain.thesis_direction import (
    DirectionInvariantError,
    FrozenThesis,
    ThesisState,
    assert_direction_continuity,
    evaluate_validation_transition,
)
from orchestrator.dynamic_validation import (
    FrozenThesis as ValidationFrozenThesis,
    UnderlyingObservation,
    validate_thesis,
)


SESSION = date(2026, 9, 3)


def _thesis(direction: str = "CALL") -> FrozenThesis:
    if direction == "PUT":
        return FrozenThesis(
            "THESIS:XYZ", "xyz", direction, SESSION.isoformat(),
            100.0, 90.0, 105.0, "XYZ260918P00100000",
            trigger=99.0, maximum_entry=94.0,
        )
    return FrozenThesis(
        "THESIS:XYZ", "xyz", direction, SESSION.isoformat(),
        100.0, 110.0, 95.0, "XYZ260918C00100000",
        trigger=101.0, maximum_entry=106.0,
    )


def _plan():
    return resolve_run_plan(
        requested_action=RequestedAction.VALIDATE,
        as_of_utc=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        evidence_cutoff_utc=datetime(2026, 9, 4, 12, tzinfo=timezone.utc),
        existing_thesis_id="THESIS:XYZ",
        existing_thesis_session=SESSION,
        authorised_tickers=("XYZ",),
        pipeline_run_id="DDD-PHASE3",
    )


def test_legacy_direction_adapter_preserves_public_vocabulary() -> None:
    assert normalise_side("NON_DIRECTIONAL") == "STRANGLE"
    assert structural_direction("TRANSITION", "MIXED")[0] == "STRANGLE"
    assert structural_direction("BUY_SETUP", "BEARISH")[0] == "CALL"
    assert structural_direction("SELL_SETUP", "BULLISH")[0] == "PUT"


def test_validation_and_persistence_import_one_domain_vocabulary() -> None:
    assert ValidationFrozenThesis is FrozenThesis
    assert PersistenceThesisState is ThesisState


@pytest.mark.parametrize(
    ("direction", "price", "transition"),
    [
        ("CALL", 94.0, "THESIS_INVALIDATED"),
        ("CALL", 107.0, "ENTRY_RUNWAY_EXHAUSTED"),
        ("CALL", 102.0, "THESIS_CONFIRMED"),
        ("PUT", 106.0, "THESIS_INVALIDATED"),
        ("PUT", 93.0, "ENTRY_RUNWAY_EXHAUSTED"),
        ("PUT", 98.0, "THESIS_CONFIRMED"),
    ],
)
def test_transition_policy_is_mirror_symmetric(direction, price, transition) -> None:
    assert evaluate_validation_transition(_thesis(direction), price)[0].value == transition


def test_downstream_evidence_can_confirm_but_cannot_reverse_direction() -> None:
    assert_direction_continuity("CALL", {"option_side": "CALL"}, stage="QUOTE")
    assert_direction_continuity("CALL", {"bid": 1.0, "ask": 1.1}, stage="QUOTE")
    with pytest.raises(DirectionInvariantError, match="CALL->PUT"):
        assert_direction_continuity("CALL", {"option_side": "PUT"}, stage="QUOTE")


def test_validation_fails_closed_before_capital_when_quote_reverses_direction() -> None:
    calls: list[str] = []
    with pytest.raises(DirectionInvariantError, match="OPTION_QUOTE_DIRECTION_REINTERPRETATION"):
        validate_thesis(
            _plan(), _thesis("CALL"),
            resolve_underlying=lambda *_: UnderlyingObservation(
                "OBS-1", "XYZ", 102.0, "2026-09-04T12:00:00Z", "DATASET-1"
            ),
            resolve_option_quote=lambda *_: {
                "observation_id": "QUOTE-1", "option_side": "PUT"
            },
            execution_gate=lambda *_: calls.append("gate"),
        )
    assert calls == []


def test_execution_gate_result_cannot_reverse_frozen_direction() -> None:
    with pytest.raises(DirectionInvariantError, match="EXECUTION_GATE_DIRECTION_REINTERPRETATION"):
        validate_thesis(
            _plan(), _thesis("PUT"),
            resolve_underlying=lambda *_: UnderlyingObservation(
                "OBS-2", "XYZ", 98.0, "2026-09-04T12:00:00Z", "DATASET-2"
            ),
            resolve_option_quote=lambda *_: {
                "observation_id": "QUOTE-2", "option_side": "PUT"
            },
            execution_gate=lambda *_: {"final_direction": "CALL", "action": "BUY_NOW"},
        )

