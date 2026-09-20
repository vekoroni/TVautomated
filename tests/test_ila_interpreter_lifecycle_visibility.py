"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-06 (Interpreter
lifecycle half): "Make Interpreter lifecycle visible: bundle prepared, assessment requested,
completed, failed or not requested" (section 9.2 item 11).

Today the Lab's Interpreter Assessment pane reads only interpreter_assessment_status, an
overlay field (contracts/lab_evidence_overlay.py) written back onto a governed row only once
a separate CLI command runs an actual Interpreter assessment
(pipeline_interpreter/pipeline_interpreter_commands.py). There is no row-level record of the
earlier lifecycle stage - "was an evidence bundle even prepared for this ticker at all" - that
fact previously existed only in interpreter/handoff_manifest.json, a file the browser never
reads (verified real for run 20260918_112522: bundle_count=515 out of 1,499 governed rows).
So the Lab could not distinguish "bundle prepared, assessment not yet run" from "this ticker
was never selected for Interpreter evidence" - both showed the same NOT_ASSESSED fallback.

Fix (design approved by ACK, 20 Sep 2026): reuse the existing, already-production-enabled
overlay mechanism (config/msi_runtime.json: lab_v3_view=true) rather than a new one.
morning_handoff_finalizer.py, right after materialize_interpreter_handoff succeeds and
independent reconciliation passes, writes one PREPARED overlay per bundle to the same
lab_evidence_overlay_v1.jsonl the Lab already loads. The write is advisory-only and
best-effort: a failure here must never break the morning handoff, which has already
succeeded by that point.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_evidence_overlay import (
    OverlayValidationError,
    build_overlay,
    load_overlays,
)
from contracts.interpreter_handoff_materializer import materialize_interpreter_handoff
from morning_handoff_finalizer import _publish_msi_handoff


RUN_ID = "20260830_120000"
INDEX_HTML = ROOT / "intelligence-lab" / "static" / "index.html"


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


def test_overlay_allows_interpreter_bundle_status_fields() -> None:
    overlay = build_overlay(
        run_id=RUN_ID, ticker="AAA", bundle_id="11111111-1111-1111-1111-111111111111",
        fields={
            "interpreter_bundle_status": "PREPARED",
            "interpreter_bundle_prepared_utc": "2026-08-30T12:30:00+00:00",
        },
        source="morning_handoff_finalizer",
    )
    assert overlay["fields"]["interpreter_bundle_status"] == "PREPARED"


def test_overlay_still_rejects_a_genuinely_unknown_field() -> None:
    with pytest.raises(OverlayValidationError, match="OVERLAY_FIELD_NOT_ALLOWED"):
        build_overlay(
            run_id=RUN_ID, ticker="AAA",
            bundle_id="11111111-1111-1111-1111-111111111111",
            fields={"not_a_real_field": "x"}, source="test",
        )


def test_materializer_return_value_exposes_ticker_to_bundle_id_mapping(tmp_path: Path) -> None:
    result = materialize_interpreter_handoff(
        run_id=RUN_ID,
        rows=[_row("AAA", "AAA260918C00100000"), _row("BBB", "BBB260918C00200000")],
        run_root=tmp_path / RUN_ID,
        pipeline_mode="MORNING_VALIDATION",
        session_date="2026-08-30",
        run_kind="PRODUCTION",
        run_status="ACCEPTED",
        required_stage_status={"EOD": "PASS", "MORNING_GATE": "COMPLETED", "LAB": "PASS"},
        morning_gate_completed_utc="2026-08-30T12:30:00+00:00",
    )
    assert {b["ticker"] for b in result["bundles"]} == {"AAA", "BBB"}
    assert all(b["bundle_id"] for b in result["bundles"])


def test_morning_finalizer_writes_bundle_prepared_overlay_for_each_actionable_row(
    tmp_path: Path, monkeypatch,
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
    validation_dir = run_root / "validation"
    validation_dir.mkdir()
    (validation_dir / "AAA.json").write_text(
        json.dumps({
            "validation_event_id": "VALIDATION:AAA",
            "run_id": RUN_ID,
            "ticker": "AAA",
            "thesis_id": "THESIS:AAA",
            "direction": "CALL",
            "selected_contract": "AAA260918C00100000",
            "evidence_cutoff_utc": "2026-08-30T12:29:00+00:00",
            "transition": "THESIS_CONFIRMED",
        }),
        encoding="utf-8",
    )

    _publish_msi_handoff(
        run_id=RUN_ID,
        run_dir=run_root,
        lab_rows=[actionable, waiting],
        completed_at_utc="2026-08-30T12:30:00+00:00",
    )

    overlay_path = run_root / "intelligence_lab" / "lab_evidence_overlay_v1.jsonl"
    overlays = load_overlays(overlay_path)
    assert len(overlays) == 1
    assert overlays[0]["ticker"] == "AAA"
    assert overlays[0]["fields"]["interpreter_bundle_status"] == "PREPARED"
    assert overlays[0]["fields"]["interpreter_bundle_prepared_utc"]


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_interpreter_lifecycle_state_function_covers_the_required_states() -> None:
    html = _html()
    assert "function getInterpreterLifecycleState(s) {" in html
    start = html.index("function getInterpreterLifecycleState(s) {")
    end = html.index("\n}\n", start) + len("\n}")
    source = html[start:end]
    assert "PREPARED" in source
    assert "NOT REQUESTED" in source


def test_assessment_state_field_uses_the_new_lifecycle_function() -> None:
    html = _html()
    assert "getInterpreterLifecycleState(s)" in html
