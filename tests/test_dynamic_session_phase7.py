from __future__ import annotations

import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from canonical_data.decision_outcome_ledger import (
    DecisionOutcomeLedger,
    candidate_events_from_rows,
    make_ledger_event,
)
from canonical_data.run_plan import resolve_run_plan
from contracts.interpreter_handoff import HandoffValidationError, validate_handoff_manifest
from contracts.interpreter_handoff_materializer import materialize_interpreter_handoff
from orchestrator.dynamic_validation import (
    FrozenThesis,
    UnderlyingObservation,
    persist_validation_event,
    validate_thesis,
)


RUN_ID = "20260904_220000"
SESSION = date(2026, 9, 4)
CONTRACT = "AAA260918C00100000"


def _plan():
    return resolve_run_plan(
        requested_action="VALIDATE",
        as_of_utc=datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        existing_thesis_id="BOOK-1",
        existing_thesis_session=SESSION,
        authorised_tickers=("AAA",),
        pipeline_run_id=RUN_ID,
    )


def _event(price: float = 102.0):
    thesis = FrozenThesis(
        "THESIS:AAA", "AAA", "CALL", SESSION.isoformat(),
        100.0, 110.0, 95.0, CONTRACT, trigger=101.0, maximum_entry=106.0,
    )
    return validate_thesis(
        _plan(), thesis,
        resolve_underlying=lambda *_: UnderlyingObservation(
            f"UNDERLYING-{price}", "AAA", price,
            "2026-09-08T12:00:00Z", f"DATASET-{price}"
        ),
        resolve_option_quote=lambda *_: {"observation_id": "QUOTE-2"},
        execution_gate=lambda *_: {
            "action": "BUY_SMALL", "capital_authority": "EXECUTION_GATE"
        },
    )


def _row() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "pipeline_mode": "MORNING_VALIDATION",
        "ticker": "AAA",
        "thesis_id": "THESIS:AAA",
        "trade_idea_id": "IDEA:AAA",
        "selected_structure_id": "STRUCT:AAA",
        "selected_contract_symbol": CONTRACT,
        "selected_quote_snapshot_id": "QUOTE-2",
        "governed_direction": "CALL",
        "thesis_state": "TRADEABLE_NOW",
        "olm_guard_disposition": "ELIGIBLE",
        "final_action": "BUY_SMALL",
        "capital_permission": "CAPITAL_LIMITED",
        "current_quote_timestamp_utc": "2026-09-08T12:00:00Z",
        "evidence_session_date": SESSION.isoformat(),
        "completed_close": 100.0,
        "target_spot": 110.0,
        "invalidation_spot": 95.0,
        "planned_hold_sessions": 5,
        "completed_profile_evidence_id": "PROFILE-EOD-1",
    }


def test_ledger_is_idempotent_append_only_and_returns_latest_validation(tmp_path: Path) -> None:
    ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
    event = make_ledger_event(
        event_type="VALIDATION", occurred_at_utc="2026-09-08T12:00:00Z",
        run_id=RUN_ID, ticker="AAA", thesis_id="THESIS:AAA",
        validation_event_id="VALIDATION-1", payload={"transition": "THESIS_CONFIRMED"},
    )
    assert ledger.append(event) is True
    assert ledger.append(event) is False
    latest = ledger.latest_validation("THESIS:AAA")
    assert latest is not None and latest.validation_event_id == "VALIDATION-1"
    with sqlite3.connect(ledger.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE ledger_events SET ticker='BBB'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM ledger_events")


def test_candidate_ledger_records_accepted_and_rejected_rows(tmp_path: Path) -> None:
    rows = [
        _row(),
        {**_row(), "ticker": "BBB", "thesis_id": "THESIS:BBB",
         "final_action": "BLOCK", "rejection_reason": "NO_CURRENT_QUOTE"},
    ]
    events = candidate_events_from_rows(
        rows, run_id=RUN_ID, occurred_at_utc="2026-09-08T12:00:00Z"
    )
    assert len(events) == 2
    assert {event.payload["final_action"] for event in events} == {"BUY_SMALL", "BLOCK"}


def test_validation_file_and_ledger_are_both_idempotent(tmp_path: Path) -> None:
    event = _event()
    path = tmp_path / "events" / f"{event.validation_event_id}.json"
    ledger_path = tmp_path / "ledger.sqlite"
    persist_validation_event(event, path, ledger_path=ledger_path, run_id=RUN_ID)
    persist_validation_event(event, path, ledger_path=ledger_path, run_id=RUN_ID)
    with sqlite3.connect(ledger_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 1


def test_materializer_publishes_frozen_and_current_axes_with_exact_identity(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    event = _event()
    result = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[_row()], run_root=run_root,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-09-08",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        validation_events=[event], require_validation_lineage=True,
    )
    handoff = validate_handoff_manifest(result["handoff_manifest_path"])
    bundle = handoff.bundles[0]
    row = handoff.book_rows[0]
    assert bundle["frozen_thesis"]["completed_session"] == SESSION.isoformat()
    assert bundle["frozen_thesis"]["completed_profile_evidence_id"] == "PROFILE-EOD-1"
    assert bundle["current_validation"]["validation_event_id"] == event.validation_event_id
    assert row["validation_event_id"] == event.validation_event_id
    assert row["lab_status_banner"] == "THESIS CONFIRMED — EXECUTION VIABILITY PASSED"


def test_materializer_fails_closed_on_missing_or_mismatched_validation(tmp_path: Path) -> None:
    common = dict(
        run_id=RUN_ID, rows=[_row()], pipeline_mode="MORNING_VALIDATION",
        session_date="2026-09-08", run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        require_validation_lineage=True,
    )
    with pytest.raises(HandoffValidationError, match="MISSING_VALIDATION_EVENT"):
        materialize_interpreter_handoff(run_root=tmp_path / "missing" / RUN_ID, **common)
    bad = {**_event().to_dict(), "selected_contract": "AAA260918P00100000"}
    with pytest.raises(HandoffValidationError, match="IDENTITY_MISMATCH:selected_contract"):
        materialize_interpreter_handoff(
            run_root=tmp_path / "bad" / RUN_ID, validation_events=[bad], **common
        )


def test_interpreter_resolver_exposes_axes_without_provider_calls(tmp_path: Path) -> None:
    interpreter = Path(__file__).resolve().parents[1] / "pipeline_interpreter"
    if str(interpreter) not in sys.path:
        sys.path.insert(0, str(interpreter))
    from evidence_resolver import IntendedUse, resolve_interpreter_evidence

    run_root = tmp_path / RUN_ID
    event = _event()
    result = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[_row()], run_root=run_root,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-09-08",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        validation_events=[event], require_validation_lineage=True,
    )
    resolved = resolve_interpreter_evidence(
        "AAA", manifest_path=result["handoff_manifest_path"],
        intended_use=IntendedUse.TRAJECTORY, require_current=False,
    )
    assert resolved.frozen_thesis["direction"] == "CALL"
    assert resolved.current_validation["transition"] == "THESIS_CONFIRMED"
    assert resolved.current_validation["can_reverse_direction"] is False


def test_validation_event_change_changes_bundle_identity(tmp_path: Path) -> None:
    first = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[_row()], run_root=tmp_path / "one" / RUN_ID,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-09-08",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        validation_events=[_event(102.0)], require_validation_lineage=True,
    )
    second = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[_row()], run_root=tmp_path / "two" / RUN_ID,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-09-08",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-09-08T12:01:00Z",
        validation_events=[_event(103.0)], require_validation_lineage=True,
    )
    a = validate_handoff_manifest(first["handoff_manifest_path"]).bundles[0]["bundle_id"]
    b = validate_handoff_manifest(second["handoff_manifest_path"]).bundles[0]["bundle_id"]
    assert a != b
