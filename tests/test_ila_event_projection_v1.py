"""Publication-boundary regressions for the governed Lab Morning read model."""
from __future__ import annotations

import sys
import json
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
from morning_handoff_finalizer import (
    _attach_persisted_validation_events, _project_validation_event,
)


def _morning_source() -> dict:
    return {
        "ticker": "AAA", "thesis_id": "AAA:CALL:2099-01-02:OLM2",
        "governed_direction": "CALL", "final_direction": "CALL",
        "morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH",
        "morning_execution_permission": "GO", "final_action": "BUY_NOW",
        "morning_transition_state": "EXECUTABLE_NOW",
        "selected_contract_symbol": "AAA990119C00100000",
        "morning_quote_timestamp_utc": "2099-01-03T14:26:46Z",
        "selected_quote_timestamp_utc": "2099-01-03T14:26:46Z",
        "live_price": 101.0,
    }


def test_morning_event_fields_survive_final_book_publication():
    source = _morning_source()
    event = {
        "invocation_id": "20990102_220000", "ticker": "AAA",
        "thesis_id": source["thesis_id"],
        "selected_contract": source["selected_contract_symbol"],
        "validation_event_id": "validation_aaa", "transition": "THESIS_CONFIRMED",
        "current_price": 101.0, "gap_pct": 1.0,
        "evidence_cutoff_utc": "2099-01-03T14:26:46Z",
        "data_status": "COMPLETE", "reason": "MORNING_GATE_RECORDED",
        "underlying_observation_id": "underlying_aaa",
        "option_quote_observation_id": "quote_aaa",
        "execution_gate_result": {"final_action": "BUY_NOW"},
    }
    _project_validation_event(source, event, run_id="20990102_220000")
    source["pipeline_mode"] = "MORNING_VALIDATION"
    book = opportunity_book_row(source, "20990102_220000", 1)
    for field in (
        "morning_execution_mode", "validation_event_id", "validation_transition",
        "validation_evidence_cutoff_utc", "validation_current_price",
        "validation_gap_pct", "validation_data_status",
    ):
        assert field in FINAL_BOOK_FIELDS
        assert book[field] == source[field]
    assert book["morning_quote_timestamp_utc"] == "2099-01-03T14:26:46Z"
    assert book["lab_projection_integrity_state"] == "COMPLETE"


def test_missing_event_preserves_source_decision_but_marks_lab_incomplete():
    source = _morning_source()
    source["pipeline_mode"] = "MORNING_VALIDATION"
    source["final_action"] = "MANUAL_REVIEW"
    book = opportunity_book_row(source, "20990102_220000", 1)
    assert book["lab_projection_integrity_state"] == "PROJECTION_INCOMPLETE"
    assert book["final_action"] == source["final_action"]


def test_validation_event_cannot_cross_ticker_or_contract():
    source = _morning_source()
    event = {"ticker": "OTHER", "thesis_id": source["thesis_id"],
             "selected_contract": source["selected_contract_symbol"],
             "invocation_id": "20990102_220000", "validation_event_id": "wrong"}
    import pytest
    with pytest.raises(ValueError, match="ticker"):
        _project_validation_event(source, event, run_id="20990102_220000")
    event["ticker"] = "AAA"
    event["selected_contract"] = "AAA990119P00100000"
    with pytest.raises(ValueError, match="contract"):
        _project_validation_event(source, event, run_id="20990102_220000")


def test_event_population_keeps_missing_event_row_visible_but_incomplete(tmp_path):
    rows = [_morning_source(), {**_morning_source(), "ticker": "BBB"}]
    event = {
        "invocation_id": "20990102_220000", "ticker": "AAA",
        "thesis_id": rows[0]["thesis_id"],
        "selected_contract": rows[0]["selected_contract_symbol"],
        "validation_event_id": "validation_aaa", "transition": "THESIS_CONFIRMED",
        "evidence_cutoff_utc": "2099-01-03T14:26:46Z",
    }
    (tmp_path / "validation_aaa.json").write_text(json.dumps(event), encoding="utf-8")
    issues = _attach_persisted_validation_events(rows, tmp_path, run_id="20990102_220000")
    assert rows[0]["validation_event_id"] == "validation_aaa"
    assert rows[1]["validation_data_status"] == "EVENT_MISSING_FROM_PROJECTION"
    assert issues == ["BBB:EVENT_MISSING_FROM_PROJECTION"]


def test_ui_binds_governed_morning_event_and_role_specific_quote():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "s.validation_event_id" in html
    assert "s.validation_current_price" in html
    assert "s.morning_quote_timestamp_utc" in html
    assert "No morning validation data for this signal. Run morning_validation.py" not in html
    assert "refreshIfLabPublicationChanged" in html
    assert "s.lab_projection_integrity_state === 'PROJECTION_INCOMPLETE'" in html
    assert "s.garch_method || g('method')" in html
    assert "Buying edge exists" not in html
    assert "Aggregate score is supplied, but component evidence is not published" in html
    assert "Current Quote Timestamp (UTC)" in html
    assert "Morning Selected Quote Timestamp (UTC)" in html
    assert "function getMorningThesisState(s)" in html
    assert "getMorningThesisState(s).label" in html
    assert "Evening Thesis Decision — Morning Check Pending" not in html


def test_lab_version_endpoint_changes_when_book_is_republished(tmp_path, monkeypatch):
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_event_version_test", path)
    lab = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lab)
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    book = tmp_path / "RUN-A" / "intelligence_lab" / "final_opportunity_book_RUN-A.json"
    book.parent.mkdir(parents=True)
    book.write_text('{"candidate_count":1}', encoding="utf-8")
    client = lab.app.test_client()
    before = client.get("/api/run/RUN-A/version").get_json()
    assert before["run_id"] == "RUN-A"
    book.write_text('{"candidate_count":2,"updated":true}', encoding="utf-8")
    after = client.get("/api/run/RUN-A/version").get_json()
    assert after["version"] != before["version"]


def test_old_morning_book_can_read_events_without_rewriting_artifacts(tmp_path, monkeypatch):
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_event_compat_test", path)
    lab = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lab)
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    source = tmp_path / "RUN-A" / "morning_validation"
    events = source / "validation_events"
    events.mkdir(parents=True)
    morning = source / "morning_validated_trades_RUN-A.csv"
    morning.write_text(
        "ticker,thesis_id,morning_execution_mode\n"
        "AAA,AAA:CALL:2099-01-02:OLM2,POSTOPEN_CONTRACT_REFRESH\n",
        encoding="utf-8",
    )
    event = {
        "invocation_id": "RUN-A", "ticker": "AAA",
        "thesis_id": "AAA:CALL:2099-01-02:OLM2",
        "selected_contract": "AAA990119C00100000",
        "validation_event_id": "validation_aaa", "transition": "THESIS_CONFIRMED",
        "evidence_cutoff_utc": "2099-01-03T14:26:46Z",
        "execution_gate_result": {"final_action": "BUY_NOW"},
    }
    event_path = events / "validation_aaa.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    row = {
        "ticker": "AAA", "thesis_id": event["thesis_id"],
        "contract_symbol": event["selected_contract"], "final_action": "BUY_NOW",
        "pipeline_mode": "MORNING_VALIDATION",
    }
    original = morning.read_bytes(), event_path.read_bytes()
    lab._overlay_governed_validation_view("RUN-A", [row])
    assert row["validation_event_id"] == "validation_aaa"
    assert row["morning_execution_mode"] == "POSTOPEN_CONTRACT_REFRESH"
    assert row["lab_projection_integrity_state"] == "COMPLETE"
    assert (morning.read_bytes(), event_path.read_bytes()) == original


def test_lab_html_is_not_cached_after_a_governed_projection_change():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_html_cache_test", path)
    lab = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lab)
    response = lab.app.test_client().get("/")
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]


def test_convexity_score_basis_requires_matching_options_evidence():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("lab_convexity_basis_test", path)
    lab = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lab)
    book = {"ticker": "AAA", "contract_symbol": "AAA990119C00100000", "convexity_score": "3.0"}
    options = {"ticker": "AAA", "recommended_contract": book["contract_symbol"], "convexity_score": "3.0"}
    lab._project_convexity_basis(book, options)
    assert book["convexity_score_max"] == 5
    assert book["convexity_score_source"] == "OPTIONS_5_CONDITION"
    mismatched = dict(book, convexity_score_max="", convexity_score_source="")
    lab._project_convexity_basis(mismatched, dict(options, recommended_contract="AAA990119P00100000"))
    assert not mismatched["convexity_score_max"]


def test_convexity_and_breakeven_ui_separates_source_roles():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "function getConvexitySummary(s)" in html
    assert "function getSelectedQuoteAskBreakeven(s)" in html
    assert "function getQuoteFreshnessContext(s)" in html
    assert "Frozen option breakeven" in html
    assert "Selected-quote expiry breakeven" in html
    assert "AT CAPTURE" in html
    assert "PCR volume balanced — smart money flow" not in html
