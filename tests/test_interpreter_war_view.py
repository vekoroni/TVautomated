"""Focused WAR view of a saved Interpreter report; no new model workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flask import Flask

from pipeline_interpreter.war_view import build_war_view, install_war_view


RUN = "20260925_061649"
TICKER = "BULL"
REPORT_ID = "a" * 64
SYMBOL = "BULL261120C00007500"


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    runs = root / "data" / "output" / "runs"
    report_dir = runs / RUN / "interpreter" / "interactive_desk" / TICKER
    report_dir.mkdir(parents=True)
    report = {
        "status": "COMPLETE", "report_id": REPORT_ID, "run_id": RUN,
        "ticker": TICKER, "phase": "MORNING_DELTA", "authority": "ADVISORY_ONLY",
        "selected_contract_symbol": SYMBOL, "provider_retrieved_at_utc": "2026-09-25T15:01:07Z",
        "executive_summary": "A cautious thesis", "sections": [
            {"key": "thesis", "text": "The thesis needs confirmation", "evidence_class": "DERIVED",
             "evidence_refs": ["EOD_BOOK"]}],
        "counter_case": {"text": "A move below value weakens the case"},
        "unresolved": ["No verified catalyst"], "external_events": [],
        "evidence_digest": {
            "evidence_cutoff_utc": "2026-09-25T14:12:31Z",
            "eod_manifest_sha256": "b" * 64,
            "eod_fields": {"thesis_id": "BULL:CALL:2026-09-24:OLM2", "canonical_direction": "CALL",
                           "target_price": 8.25, "invalidation_price": 6.93},
            "morning_evidence": {"validation_transition": "VALIDATED"},
        },
    }
    (report_dir / f"{REPORT_ID}.json").write_text(json.dumps(report), encoding="utf-8")
    macro = runs / RUN / "interpreter" / "interpreter_macro_context.json"
    macro.write_text(json.dumps({"as_of_utc": "2026-09-25T05:21:00Z",
                                 "freshness": "FRESH", "quality": "PARTIAL",
                                 "conflicts": ["VIX sources disagree"]}), encoding="utf-8")
    quote_dir = root / "data" / "canonical" / "market_observations" / "exact_option_quote" / "2026-09-25" / TICKER
    quote_dir.mkdir(parents=True)
    quote = {"run_id": RUN, "underlying": TICKER, "symbol": SYMBOL,
             "quote_source": "MARKETDATA", "quote_timestamp_utc": "2026-09-25T13:34:50Z",
             "bid": 0.61, "ask": 0.64, "bid_size": 1, "ask_size": 13,
             "delta": 0.50, "gamma": 0.22, "theta": -0.01, "vega": 0.01}
    (quote_dir / "quote.json").write_text(json.dumps(quote), encoding="utf-8")
    return root, runs


def test_saved_report_build_uses_run_bound_quote_and_preserves_time(tmp_path):
    root, runs = _fixture(tmp_path)
    result = build_war_view(runs / RUN, root, TICKER, REPORT_ID,
                            generated_at_utc="2026-09-25T19:20:45Z")
    assert result["authority"] == "ADVISORY_ONLY"
    assert result["interpreter_report_id"] == REPORT_ID
    assert result["exact_option_quote"]["identity_state"] == "MATCHED"
    assert result["exact_option_quote"]["quote_freshness"] == "STALE"
    assert result["exact_option_quote"]["executable_now"] == "NOT_EXECUTABLE_STALE"
    assert result["evening_thesis"]["target_price"] == 8.25
    assert result["morning_update"]["validation_transition"] == "VALIDATED"
    assert result["macro_context"]["conflicts"] == ["VIX sources disagree"]
    assert "No verified catalyst" in result["coverage_gaps"]


def test_war_route_generates_then_reopens_without_any_provider(tmp_path):
    root, runs = _fixture(tmp_path)
    app = Flask(__name__)
    install_war_view(app, runs, root)
    client = app.test_client()
    body = {"run_id": RUN, "ticker": TICKER, "report_id": REPORT_ID}
    response = client.post("/api/interpreter/war", json=body)
    assert response.status_code == 200
    assert response.json["status"] == "COMPLETE"
    assert response.json["authority"] == "ADVISORY_ONLY"
    saved = runs / RUN / "interpreter" / "war_views" / TICKER / f"{REPORT_ID}.json"
    first_hash = hashlib.sha256(saved.read_bytes()).hexdigest()
    second = client.post("/api/interpreter/war", json=body)
    assert second.status_code == 200
    assert second.json["status"] == "COMPLETE"
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == first_hash
    html = client.get(f"/api/interpreter/war/{RUN}/{TICKER}/{REPORT_ID}.html")
    assert html.status_code == 200
    assert b"A cautious thesis" in html.data
    assert b"NOT_EXECUTABLE_STALE" in html.data


def test_war_route_rejects_cross_run_and_unsafe_identity(tmp_path):
    root, runs = _fixture(tmp_path)
    app = Flask(__name__)
    install_war_view(app, runs, root)
    client = app.test_client()
    assert client.post("/api/interpreter/war", json={"run_id": "../escape", "ticker": TICKER,
                                                     "report_id": REPORT_ID}).status_code == 400
    assert client.post("/api/interpreter/war", json={"run_id": "20260924_085940", "ticker": TICKER,
                                                     "report_id": REPORT_ID}).status_code == 404


def test_war_route_rejects_foreign_origin_and_corrupt_saved_view(tmp_path):
    root, runs = _fixture(tmp_path)
    app = Flask(__name__)
    install_war_view(app, runs, root)
    client = app.test_client()
    body = {"run_id": RUN, "ticker": TICKER, "report_id": REPORT_ID}
    assert client.post("/api/interpreter/war", json=body,
                       headers={"Origin": "https://elsewhere.example"}).status_code == 403
    assert client.post("/api/interpreter/war", json=body).status_code == 200
    saved = runs / RUN / "interpreter" / "war_views" / TICKER / f"{REPORT_ID}.json"
    saved.write_text(json.dumps({"run_id": RUN, "ticker": TICKER,
                                 "interpreter_report_id": REPORT_ID,
                                 "authority": "ADVISORY_ONLY"}), encoding="utf-8")
    assert client.get(f"/api/interpreter/war/{RUN}/{TICKER}/{REPORT_ID}.html").status_code == 409


def test_war_html_escapes_saved_interpreter_text(tmp_path):
    root, runs = _fixture(tmp_path)
    saved_report = runs / RUN / "interpreter" / "interactive_desk" / TICKER / f"{REPORT_ID}.json"
    payload = json.loads(saved_report.read_text(encoding="utf-8"))
    payload["executive_summary"] = "<script>alert('unsafe')</script>"
    saved_report.write_text(json.dumps(payload), encoding="utf-8")
    app = Flask(__name__)
    install_war_view(app, runs, root)
    client = app.test_client()
    assert client.post("/api/interpreter/war", json={"run_id": RUN, "ticker": TICKER,
                                                     "report_id": REPORT_ID}).status_code == 200
    html = client.get(f"/api/interpreter/war/{RUN}/{TICKER}/{REPORT_ID}.html")
    assert html.status_code == 200
    assert b"<script>" not in html.data
    assert b"&lt;script&gt;" in html.data
