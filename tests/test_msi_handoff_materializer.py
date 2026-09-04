from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from contracts.interpreter_handoff import (
    HandoffValidationError,
    validate_handoff_manifest,
)
from contracts.interpreter_handoff_materializer import (
    materialize_interpreter_handoff,
)
from tools.msi_reconcile import reconcile_handoff
from morning_handoff_finalizer import _publish_msi_handoff


RUN_ID = "20260830_120000"


def _row(ticker: str, contract: str) -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "pipeline_mode": "MORNING_VALIDATION",
        "ticker": ticker,
        "thesis_id": f"THESIS:{ticker}",
        "trade_idea_id": f"IDEA:{ticker}",
        "selected_structure_id": f"STRUCT:{ticker}",
        "selected_contract_symbol": contract,
        "selected_quote_snapshot_id": f"QUOTE:{ticker}",
        "governed_direction": "CALL",
        "thesis_state": "TRADEABLE_NOW",
        "olm_guard_disposition": "ELIGIBLE",
        "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED",
        "quote_freshness": "FRESH",
        "underlying_quote_freshness": "FRESH",
        "ms_freshness": "FRESH",
    }


def test_materializer_publishes_hash_verified_atomic_handoff(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    result = materialize_interpreter_handoff(
        run_id=RUN_ID,
        rows=[
            _row("AAA", "AAA260918C00100000"),
            _row("BBB", "BBB260918C00200000"),
        ],
        run_root=run_root,
        pipeline_mode="MORNING_VALIDATION",
        session_date="2026-08-30",
        run_kind="PRODUCTION",
        run_status="ACCEPTED",
        required_stage_status={
            "EOD": "PASS",
            "MORNING_GATE": "COMPLETED",
            "LAB": "PASS",
        },
        morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
    )

    handoff = validate_handoff_manifest(result["handoff_manifest_path"])
    assert handoff.manifest["ticker_count"] == 2
    assert len(handoff.book_rows) == 2
    assert len(handoff.bundles) == 2
    assert {row["ticker"] for row in handoff.book_rows} == {"AAA", "BBB"}
    reconciliation = json.loads(
        Path(result["reconciliation_path"]).read_text(encoding="utf-8")
    )
    assert reconciliation["status"] == "PASS"
    assert reconciliation["identity_mismatches"] == 0
    independent = reconcile_handoff(result["handoff_manifest_path"])
    assert independent["status"] == "PASS"
    assert independent["mismatch_count"] == 0


def test_materializer_fails_closed_when_exact_identity_is_missing(tmp_path: Path) -> None:
    row = _row("AAA", "AAA260918C00100000")
    row["selected_quote_snapshot_id"] = ""
    with pytest.raises(HandoffValidationError, match="MISSING_IDENTITY"):
        materialize_interpreter_handoff(
            run_id=RUN_ID,
            rows=[row],
            run_root=tmp_path / RUN_ID,
            pipeline_mode="MORNING_VALIDATION",
            session_date="2026-08-30",
            run_kind="PRODUCTION",
            run_status="ACCEPTED",
            required_stage_status={"MORNING_GATE": "COMPLETED"},
            morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
        )


def test_materializer_never_silently_drops_duplicate_tickers(tmp_path: Path) -> None:
    with pytest.raises(HandoffValidationError, match="DUPLICATE_TICKER"):
        materialize_interpreter_handoff(
            run_id=RUN_ID,
            rows=[
                _row("AAA", "AAA260918C00100000"),
                _row("AAA", "AAA260918C00105000"),
            ],
            run_root=tmp_path / RUN_ID,
            pipeline_mode="MORNING_VALIDATION",
            session_date="2026-08-30",
            run_kind="PRODUCTION",
            run_status="ACCEPTED",
            required_stage_status={"MORNING_GATE": "COMPLETED"},
            morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
        )


def test_materializer_rejects_lab_macro_hash_drift(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    packet = run_root / "interpreter" / "interpreter_macro_context.json"
    packet.parent.mkdir(parents=True)
    packet.write_text(
        json.dumps({"packet_id": "MACRO:ONE", "macro_context_state": "NEUTRAL"}),
        encoding="utf-8",
    )
    import hashlib
    packet_hash = hashlib.sha256(packet.read_bytes()).hexdigest()
    reference = {
        "packet_id": "MACRO:ONE",
        "path": str(packet),
        "sha256": packet_hash,
        "as_of_utc": "2026-08-30T12:00:00+00:00",
        "session_date": "2026-08-30",
        "freshness": "FRESH",
        "quality": "COMPLETE",
        "macro_context_state": "NEUTRAL",
    }
    row = _row("AAA", "AAA260918C00100000")
    row.update({"macro_packet_id": "MACRO:ONE", "macro_packet_sha256": "wrong"})
    with pytest.raises(HandoffValidationError, match="MACRO_PACKET_HASH"):
        materialize_interpreter_handoff(
            run_id=RUN_ID,
            rows=[row],
            run_root=run_root,
            pipeline_mode="MORNING_VALIDATION",
            session_date="2026-08-30",
            run_kind="PRODUCTION",
            run_status="ACCEPTED",
            required_stage_status={"MORNING_GATE": "COMPLETED"},
            morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
            macro_reference=reference,
        )


def test_materializer_rejects_macro_reference_hash_drift(tmp_path: Path) -> None:
    run_root = tmp_path / RUN_ID
    packet = run_root / "interpreter" / "interpreter_macro_context.json"
    packet.parent.mkdir(parents=True)
    packet.write_text(
        json.dumps({"packet_id": "MACRO:ONE", "macro_context_state": "NEUTRAL"}),
        encoding="utf-8",
    )
    reference = {
        "packet_id": "MACRO:ONE",
        "path": str(packet),
        "sha256": "0" * 64,
        "as_of_utc": "2026-08-30T12:00:00+00:00",
        "session_date": "2026-08-30",
        "freshness": "FRESH",
        "quality": "COMPLETE",
        "macro_context_state": "NEUTRAL",
    }
    row = _row("AAA", "AAA260918C00100000")
    with pytest.raises(HandoffValidationError, match="MACRO_REFERENCE_HASH_MISMATCH"):
        materialize_interpreter_handoff(
            run_id=RUN_ID,
            rows=[row],
            run_root=run_root,
            pipeline_mode="MORNING_VALIDATION",
            session_date="2026-08-30",
            run_kind="PRODUCTION",
            run_status="ACCEPTED",
            required_stage_status={"MORNING_GATE": "COMPLETED"},
            morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
            macro_reference=reference,
        )


def test_morning_finalizer_publishes_only_actionable_rows_when_flags_are_active(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MSI_LAB_V3_VIEW", "1")
    monkeypatch.setenv("MSI_INTERPRETER_RESOLVER", "1")
    run_root = tmp_path / RUN_ID
    run_root.mkdir(parents=True)
    (run_root / "run_meta.json").write_text(
        json.dumps({"run_kind": "PRODUCTION", "run_status": "COMPLETED"}),
        encoding="utf-8",
    )
    actionable = _row("AAA", "AAA260918C00100000")
    waiting = _row("BBB", "BBB260918C00200000")
    waiting["final_action"] = "BLOCK"

    result = _publish_msi_handoff(
        run_id=RUN_ID,
        run_dir=run_root,
        lab_rows=[actionable, waiting],
        completed_at_utc="2026-08-30T12:30:00+00:00",
    )

    handoff = validate_handoff_manifest(result["handoff_manifest_path"])
    assert handoff.manifest["ticker_count"] == 1
    assert handoff.book_rows[0]["ticker"] == "AAA"
    run_meta = json.loads((run_root / "run_meta.json").read_text(encoding="utf-8"))
    assert run_meta["run_status"] == "ACCEPTED"
    assert run_meta["operator_accepted_by"] == "MORNING_HANDOFF_FINALIZER"


def test_prior_session_quote_is_published_as_manual_requote(tmp_path: Path) -> None:
    row = _row("AAA", "AAA260918C00100000")
    row["current_quote_timestamp_utc"] = "2026-08-29T20:00:00Z"
    row["contract_size_quality"] = ""
    result = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[row], run_root=tmp_path / RUN_ID,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-08-30",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-08-30T13:00:00Z",
    )
    with open(result["book_path"], encoding="utf-8-sig", newline="") as handle:
        published = next(csv.DictReader(handle))
    assert published["model_final_action"] == "BUY_NOW"
    assert published["final_action"] == "MANUAL_REQUOTE_REQUIRED"
    assert published["execution_quote_status"] == "PRIOR_SESSION_MANUAL_REQUOTE"
    assert published["contract_size_quality"] == "MISSING"


def test_same_session_quote_retains_swing_candidate_action(tmp_path: Path) -> None:
    row = _row("AAA", "AAA260918C00100000")
    row["final_action"] = "BUY_SMALL"
    row["current_quote_timestamp_utc"] = "2026-08-30T12:00:00Z"
    result = materialize_interpreter_handoff(
        run_id=RUN_ID, rows=[row], run_root=tmp_path / RUN_ID,
        pipeline_mode="MORNING_VALIDATION", session_date="2026-08-30",
        run_kind="PRODUCTION", run_status="ACCEPTED",
        required_stage_status={"MORNING_GATE": "COMPLETED"},
        morning_gate_completed_utc="2026-08-30T13:00:00Z",
    )
    with open(result["book_path"], encoding="utf-8-sig", newline="") as handle:
        published = next(csv.DictReader(handle))
    assert published["final_action"] == "BUY_SMALL"
    assert published["execution_quote_status"] == "SAME_SESSION_INDICATIVE"
    assert published["execution_quote_human_confirmation_required"] == "True"
