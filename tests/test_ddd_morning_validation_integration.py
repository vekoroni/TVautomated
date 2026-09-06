from __future__ import annotations

import json
from pathlib import Path

from orchestrator.dynamic_validation import (
    persist_morning_validation_events,
    validation_event_from_morning_row,
)


RUN_ID = "20260905_120000"


def _row(**updates):
    row = {
        "ticker": "XYZ",
        "thesis_id": "thesis_xyz",
        "governed_direction": "PUT",
        "selected_contract_symbol": "XYZ260918P00100000",
        "selected_quote_snapshot_id": "quote_xyz_1",
        "current_quote_timestamp_utc": "2026-09-05T12:00:00Z",
        "live_price": 98.0,
        "signal_price": 100.0,
        "morning_transition_state": "LIQUIDITY_STILL_PENDING",
        "final_action": "WATCH",
        "capital_permission": "WATCH_ONLY",
        "executable_now": False,
    }
    row.update(updates)
    return row


def test_morning_result_is_serialised_without_changing_direction_or_contract():
    event = validation_event_from_morning_row(
        _row(), run_id=RUN_ID,
        fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    assert event.direction == "PUT"
    assert event.selected_contract == "XYZ260918P00100000"
    assert event.transition == "PENDING_TRIGGER"
    assert event.current_price == 98.0
    assert event.gap_pct == -2.0
    assert event.execution_gate_result["action"] == "WATCH"
    assert event.execution_gate_result["executable_now"] is False


def test_terminal_and_non_directional_states_map_to_domain_vocabulary():
    invalid = validation_event_from_morning_row(
        _row(morning_transition_state="THESIS_INVALIDATED"),
        run_id=RUN_ID, fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    non_directional = validation_event_from_morning_row(
        _row(governed_direction="NON_DIRECTIONAL", selected_contract_symbol=""),
        run_id=RUN_ID, fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    assert invalid.transition == "THESIS_INVALIDATED"
    assert non_directional.transition == "NOT_EVALUATED_NON_DIRECTIONAL"


def test_morning_event_persistence_is_immutable_and_restart_safe(tmp_path: Path):
    destination = tmp_path / "validation_events"
    first = persist_morning_validation_events(
        [_row()], run_id=RUN_ID, destination_dir=destination,
        fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    second = persist_morning_validation_events(
        [_row()], run_id=RUN_ID, destination_dir=destination,
        fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    files = list(destination.glob("*.json"))
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["reused"] == 1
    assert len(files) == 1
    assert json.loads(files[0].read_text())["thesis_id"] == "thesis_xyz"


def test_newer_quote_produces_new_append_only_validation_event(tmp_path: Path):
    destination = tmp_path / "validation_events"
    persist_morning_validation_events(
        [_row()], run_id=RUN_ID, destination_dir=destination,
        fallback_evidence_cutoff_utc="2026-09-05T12:01:00Z",
    )
    result = persist_morning_validation_events(
        [_row(
            current_quote_timestamp_utc="2026-09-05T12:05:00Z",
            selected_quote_snapshot_id="quote_xyz_2",
            live_price=97.5,
        )],
        run_id=RUN_ID, destination_dir=destination,
        fallback_evidence_cutoff_utc="2026-09-05T12:06:00Z",
    )
    assert result["written"] == 1
    assert len(list(destination.glob("*.json"))) == 2
