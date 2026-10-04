"""Offline end-to-end Lab/Interpreter acceptance with a fake GPT transport."""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask


RUN = "20260922_000106"
SECTIONS = ("macro", "gamma", "liquidity", "thesis", "chart", "options_flow", "risk", "verdict")


def _fixture(tmp_path):
    from pipeline_interpreter.interactive_snapshot import publish_eod_snapshot

    root = tmp_path / RUN
    (root / "intelligence_lab").mkdir(parents=True)
    (root / "final_run_manifest.json").write_text(json.dumps({
        "run_id": RUN, "pipeline_mode": "EOD", "pipeline_technical_health": "PASS",
        "fatal_flags": [], "created_at_utc": "2026-09-22T01:00:00+00:00",
    }))
    (root / "run_meta.json").write_text(json.dumps({
        "canonical_run_id": RUN, "pipeline_mode": "EOD", "run_status": "COMPLETED",
    }))
    (root / "intelligence_lab" / f"final_opportunity_book_{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "candidate_count": 2, "rows": [
            {"run_id": RUN, "ticker": "AAA", "direction": "CALL", "final_action": "GO",
             "thesis_id": "TH-A", "target_price": 110, "invalidation_price": 95,
             "profile_type": "D_SHAPED", "poc": 101, "call_wall": 105,
             "contract_symbol": "AAA261120C00100000"},
            {"run_id": RUN, "ticker": "BBB", "direction": "PUT", "final_action": "BLOCK",
             "thesis_id": "TH-B", "target_price": 90, "invalidation_price": 105,
             "contract_symbol": ""},
        ],
    }))
    publish_eod_snapshot(root)
    return root


class FakeProvider:
    model_id = "FAKE-GPT"
    def __init__(self):
        self.reports = []
        self.questions = []

    def report(self, digest):
        self.reports.append(digest)
        counter_links = [
            key for key in ("sector", "ticker", "thesis", "contract", "morning")
            if digest["confluence"][key]["status"] not in {
                "SUPPORTS", "STRONG_TRIGGER", "EOD_ACTIVE_QUOTE_TRAIT", "THESIS_CONFIRMED"
            }
        ]
        return {
            "executive_summary": "The frozen Evening thesis has a defined target and invalidation.",
            "counter_case": {"links": counter_links,
                             "text": "Opposing or pending evidence requires human review.",
                             "evidence_refs": sorted({
                                 digest["confluence"][key]["evidence_ref"] for key in counter_links
                             })},
            "evidence_chain_review": [
                {"key": key, "status": digest["confluence"][key]["status"],
                 "text": f"{key} assessment accounts for its observed or unknown state.",
                 "evidence_class": "UNKNOWN" if digest["confluence"][key]["status"] == "UNKNOWN" else "DERIVED",
                 "evidence_refs": [digest["confluence"][key]["evidence_ref"]]}
                for key in ("sector", "ticker", "thesis", "contract", "morning")
            ],
            "sections": [
                {"key": key, "text": f"{key} assessment from governed EOD evidence.",
                 "evidence_class": "INFERRED" if key == "liquidity" else "OBSERVED",
                 "evidence_refs": ["EOD_BOOK"]}
                for key in SECTIONS
            ],
            "external_events": [], "unresolved": ["No depth or trade prints were supplied."],
        }

    def answer(self, digest, report, question):
        self.questions.append((digest, report, question))
        return {"answer": "The wall is at 105; hidden orders are not observable from these inputs.",
                "evidence_class": "INFERRED", "evidence_refs": ["EOD_BOOK"],
                "limitations": ["No depth or trade prints were supplied."]}


def test_control_does_not_advertise_provider_when_sdk_missing(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    app = Flask(__name__)
    provider = FakeProvider()
    provider.ready = True
    provider.sdk_available = False
    install_interpreter_desk(app, tmp_path, provider=provider)
    response = app.test_client().get("/api/interpreter/control")
    assert response.status_code == 200
    assert response.get_json()["provider_ready"] is False


def test_paid_interpreter_routes_refuse_missing_sdk_before_dispatch(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    app = Flask(__name__)
    provider = FakeProvider()
    provider.ready = True
    provider.sdk_available = False
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    for route in ("/api/interpreter/reports", "/api/interpreter/deep_reports", "/api/interpreter/ask"):
        response = client.post(route, json={"confirmed": True})
        assert response.status_code == 503
    assert provider.reports == []
    assert provider.questions == []


class PricedFakeProvider(FakeProvider):
    def estimate_report_bound(self, input_chars):
        return 0.05


def test_preview_cost_and_paid_question_require_confirmation(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    provider = PricedFakeProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    preview = client.post("/api/interpreter/preview", json={"run_id": RUN, "tickers": ["AAA", "BBB"]})
    assert preview.status_code == 200
    assert preview.json["cost_estimate"] == "CONFIGURED_CONSERVATIVE_BOUND"
    assert preview.json["batch_cost_bound_usd"] == 0.1
    report = client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    }).json["results"][0]
    denied = client.post("/api/interpreter/ask", json={
        "run_id": RUN, "ticker": "AAA", "report_id": report["report_id"],
        "question": "Is the crowd near the wall?",
    })
    assert denied.status_code == 400
    assert provider.questions == []


def test_saved_reports_can_be_listed_and_reopened_without_provider_call(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    root = _fixture(tmp_path)
    app = Flask(__name__)
    provider = FakeProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    assert client.post("/api/interpreter/saved_reports", json={
        "run_id": RUN, "tickers": ["AAA"],
    }).json["reports"] == []

    report = client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    }).json["results"][0]
    assert report["status"] == "COMPLETE"
    folder = root / "interpreter" / "interactive_desk" / "AAA"
    (folder / ("b" * 64 + ".error.json")).write_text("{}", encoding="utf-8")
    (folder / ("c" * 64 + ".json")).write_text(json.dumps({
        "status": "COMPLETE", "run_id": "other", "ticker": "AAA",
        "report_id": "c" * 64,
    }), encoding="utf-8")
    saved = client.post("/api/interpreter/saved_reports", json={
        "run_id": RUN, "tickers": ["AAA", "BBB"],
    })
    assert saved.status_code == 200
    assert saved.json["reports"] == [{
        "run_id": RUN, "ticker": "AAA", "report_id": report["report_id"],
        "phase": report["phase"], "mode": report.get("mode", "STANDARD"),
        "model_id": report["model_id"],
        "provider_retrieved_at_utc": report["provider_retrieved_at_utc"],
    }]
    reopened = client.get(f"/api/interpreter/report/{RUN}/AAA/{report['report_id']}")
    assert reopened.status_code == 200
    assert reopened.json == report
    assert len(provider.reports) == 1


def test_saved_report_listing_rejects_unsafe_or_oversized_selection(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    install_interpreter_desk(app, tmp_path, provider=FakeProvider())
    client = app.test_client()
    for body in (
        {"run_id": "../other", "tickers": ["AAA"]},
        {"run_id": RUN, "tickers": ["../AAA"]},
        {"run_id": RUN, "tickers": ["AAA"] * 6},
    ):
        assert client.post("/api/interpreter/saved_reports", json=body).status_code == 400


def test_large_lab_row_is_bounded_without_discarding_governed_facts():
    from pipeline_interpreter.interactive_desk import compile_evidence_digest

    row = {f"unrelated_field_{index}": "X" * 400 for index in range(634)}
    row.update({"ticker": "PFE", "canonical_direction": "CALL",
                "invalidation_price": 24.75, "planned_hold_sessions": 10,
                "selected_contract_symbol": "PFE261120C00030000",
                "positive_factors": "Z" * 10000})
    bundle = {"run_id": RUN, "ticker": "PFE", "bundle_id": "eod-id",
              "source_manifest_sha256": "a" * 64, "source_action": "GO",
              "selected_contract_symbol": "PFE261120C00030000"}
    digest = compile_evidence_digest(
        row, bundle, evidence_cutoff_utc="2026-09-22T01:00:00Z",
        eod_technical_health="PASS",
    )
    assert len(json.dumps(digest)) < 20000
    assert digest["eod_fields"]["invalidation_price"] == 24.75
    assert digest["eod_fields"]["planned_hold_sessions"] == 10
    assert "positive_factors:oversize" in digest["omitted_fields"]
    assert digest["available_field_count"] == len(row)


def test_lab_preview_report_and_question_are_advisory_and_ticker_scoped(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    provider = FakeProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    preview = client.post("/api/interpreter/preview", json={"run_id": RUN, "tickers": ["BBB", "AAA"]})
    assert preview.status_code == 200
    assert [r["ticker"] for r in preview.json["entries"]] == ["BBB", "AAA"]
    assert preview.json["entries"][0]["source_action"] == "BLOCK"
    launch = client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["BBB", "AAA"], "confirmed": True,
    })
    assert launch.status_code == 200
    assert len(launch.json["results"]) == 2
    assert len(provider.reports) == 2
    assert all(len(json.dumps(d)) < 20000 for d in provider.reports)
    bbb = launch.json["results"][0]
    assert bbb["ticker"] == "BBB" and bbb["source_action"] == "BLOCK"
    assert bbb["authority"] == "ADVISORY_ONLY"
    assert bbb["selected_contract_symbol"] is None
    assert {s["key"] for s in bbb["sections"]} == set(SECTIONS)
    assert {s["key"] for s in bbb["evidence_chain_review"]} == {
        "sector", "ticker", "thesis", "contract", "morning"
    }
    assert "morning" in bbb["counter_case"]["links"]
    assert client.get(f"/api/interpreter/report/{RUN}/BBB/{bbb['report_id']}").json["eod_bundle_id"] == bbb["eod_bundle_id"]
    repeated = client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["BBB", "AAA"], "confirmed": True,
    })
    assert repeated.status_code == 200 and len(provider.reports) == 2
    asked = client.post("/api/interpreter/ask", json={
        "run_id": RUN, "ticker": "BBB", "report_id": bbb["report_id"],
        "question": "Where are buyers hiding?", "confirmed": True,
    })
    assert asked.status_code == 200
    assert asked.json["evidence_class"] == "INFERRED"
    assert asked.json["limitations"]
    followup = client.post("/api/interpreter/ask", json={
        "run_id": RUN, "ticker": "BBB", "report_id": bbb["report_id"],
        "question": "What would change that view?", "confirmed": True,
    })
    assert followup.status_code == 200
    assert provider.questions[-1][0]["conversation_history"][0]["question"] == "Where are buyers hiding?"
    assert client.post("/api/interpreter/ask", json={
        "run_id": RUN, "ticker": "AAA", "report_id": bbb["report_id"], "question": "Why?", "confirmed": True,
    }).status_code == 409


def test_no_paid_call_without_confirmation_or_with_six_names(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    provider = FakeProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    assert client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": False,
    }).status_code == 400
    assert client.post("/api/interpreter/preview", json={
        "run_id": RUN, "tickers": ["AAA"] * 6,
    }).status_code == 400
    assert not provider.reports


def test_cross_origin_page_cannot_launch_paid_report_or_read_it(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    provider = FakeProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    hostile = {"Origin": "https://unrelated.example"}
    assert client.post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    }, headers=hostile).status_code == 403
    assert client.post("/api/interpreter/ask", json={}, headers=hostile).status_code == 403
    assert provider.reports == []


def test_failed_ticker_does_not_fabricate_or_block_other_report(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    class PartialProvider(FakeProvider):
        def report(self, digest):
            if digest["ticker"] == "AAA":
                raise RuntimeError("controlled provider failure")
            return super().report(digest)
    install_interpreter_desk(app, tmp_path, provider=PartialProvider())
    out = app.test_client().post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA", "BBB"], "confirmed": True,
    })
    assert out.status_code == 200
    # An untyped exception after dispatch could have followed a billable call.
    assert out.json["results"][0]["status"] == "UNKNOWN"
    assert out.json["results"][0]["retry_allowed"] is False
    assert out.json["results"][1]["ticker"] == "BBB"


def test_known_provider_rejection_is_persisted_and_never_retried(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk
    from pipeline_interpreter.openai_desk_provider import ProviderRequestRejected

    root = _fixture(tmp_path)
    app = Flask(__name__)
    class RejectedProvider(FakeProvider):
        def report(self, digest):
            self.reports.append(digest)
            raise ProviderRequestRejected(400, request_id="req_fixture")

    provider = RejectedProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    body = {"run_id": RUN, "tickers": ["AAA"], "confirmed": True}
    first = client.post("/api/interpreter/reports", json=body).json["results"][0]
    assert first["status"] == "FAILED"
    assert first["failure_code"] == "PROVIDER_HTTP_REJECTED"
    assert first["provider_http_status"] == 400
    assert first["provider_request_id"] == "req_fixture"
    assert first["retry_allowed"] is False
    marker = next((root / "interpreter" / "interactive_desk" / "AAA").glob("*.error.json"))
    assert json.loads(marker.read_text(encoding="utf-8")) == first
    assert client.post("/api/interpreter/reports", json=body).json["results"][0] == first
    assert len(provider.reports) == 1


def test_transport_timeout_stays_unknown_without_leaking_or_retrying(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk
    from pipeline_interpreter.openai_desk_provider import ProviderOutcomeUnknown

    root = _fixture(tmp_path)
    app = Flask(__name__)
    class TimeoutProvider(FakeProvider):
        def report(self, digest):
            self.reports.append(digest)
            raise ProviderOutcomeUnknown("private transport detail")

    provider = TimeoutProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    body = {"run_id": RUN, "tickers": ["AAA"], "confirmed": True}
    first = client.post("/api/interpreter/reports", json=body).json["results"][0]
    assert first["status"] == "UNKNOWN"
    assert first["failure_code"] == "PROVIDER_OUTCOME_UNKNOWN"
    assert first["retry_allowed"] is False
    assert "private transport detail" not in json.dumps(first)
    # ACK 24 Sep 2026: an unknown outcome is measured, so a timeout is read from the receipt
    # rather than inferred from file timestamps.
    assert isinstance(first["provider_elapsed_ms"], int) and first["provider_elapsed_ms"] >= 0
    marker = next((root / "interpreter" / "interactive_desk" / "AAA").glob("*.error.json"))
    assert json.loads(marker.read_text(encoding="utf-8")) == first
    assert client.post("/api/interpreter/reports", json=body).json["results"][0] == first
    assert len(provider.reports) == 1


def test_invalid_provider_report_persists_controlled_failure(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    root = _fixture(tmp_path)
    app = Flask(__name__)
    class InvalidProvider(FakeProvider):
        def report(self, digest):
            self.reports.append(digest)
            return {"sections": [], "executive_summary": "invalid", "external_events": [], "unresolved": []}

    provider = InvalidProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    body = {"run_id": RUN, "tickers": ["AAA"], "confirmed": True}
    first = client.post("/api/interpreter/reports", json=body).json["results"][0]
    assert first["status"] == "FAILED"
    assert first["failure_code"] == "REPORT_VALIDATION_FAILED"
    assert first["retry_allowed"] is False
    marker = next((root / "interpreter" / "interactive_desk" / "AAA").glob("*.error.json"))
    assert json.loads(marker.read_text(encoding="utf-8")) == first
    assert client.post("/api/interpreter/reports", json=body).json["results"][0] == first
    assert len(provider.reports) == 1


def test_existing_unknown_marker_is_preserved_without_new_paid_call(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk
    from pipeline_interpreter.openai_desk_provider import ProviderOutcomeUnknown

    root = _fixture(tmp_path)
    app = Flask(__name__)
    class UnknownProvider(FakeProvider):
        def report(self, digest):
            self.reports.append(digest)
            raise ProviderOutcomeUnknown("lost response")

    provider = UnknownProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    body = {"run_id": RUN, "tickers": ["AAA"], "confirmed": True}
    first = client.post("/api/interpreter/reports", json=body).json["results"][0]
    marker = next((root / "interpreter" / "interactive_desk" / "AAA").glob("*.error.json"))
    legacy = {"status": "UNKNOWN", "run_id": RUN, "ticker": "AAA",
              "report_id": first["report_id"],
              "error": "Provider outcome not yet reconciled; do not retry automatically."}
    marker.write_text(json.dumps(legacy), encoding="utf-8")
    assert client.post("/api/interpreter/reports", json=body).json["results"][0] == legacy
    assert json.loads(marker.read_text(encoding="utf-8")) == legacy
    assert len(provider.reports) == 1


def test_future_news_cannot_launder_into_frozen_evening_report(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    class FutureNewsProvider(FakeProvider):
        def report(self, digest):
            result = super().report(digest)
            result["_verified_web_urls"] = ["https://example.com/news"]
            result["external_events"] = [{
                "url": "https://example.com/news", "asof_utc": "2026-09-23T10:00:00Z",
                "summary": "Future event",
            }]
            return result
    install_interpreter_desk(app, tmp_path, provider=FutureNewsProvider())
    out = app.test_client().post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    })
    assert out.json["results"][0]["status"] == "FAILED"


def test_morning_revision_uses_accepted_handoff_without_overwriting_evening(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk
    from pipeline_interpreter.interactive_snapshot import publish_eod_snapshot
    from test_msi_interpreter_handoff import _fixture as morning_fixture

    manifest, morning_bundle, _governed = morning_fixture(tmp_path, freshness="STALE")
    root = manifest.parent.parent
    rid = root.name
    (root / "final_run_manifest.json").write_text(json.dumps({
        "run_id": rid, "pipeline_mode": "EOD", "pipeline_technical_health": "PASS", "fatal_flags": [],
        "created_at_utc": "2026-08-30T01:00:00+00:00",
    }))
    (root / "run_meta.json").write_text(json.dumps({
        "canonical_run_id": rid, "pipeline_mode": "EOD", "run_status": "COMPLETED",
    }))
    (root / "intelligence_lab" / f"final_opportunity_book_{rid}.json").write_text(json.dumps({
        "run_id": rid, "candidate_count": 1, "rows": [{
            "run_id": rid, "ticker": "AAA", "direction": "CALL", "thesis_id": "THESIS-1",
            "final_action": "EOD_CANDIDATE_ONLY", "target_price": 110, "invalidation_price": 95,
        }],
    }))
    receipt = publish_eod_snapshot(root)
    # Same-run mutable files advance to Morning, frozen receipt stays EOD.
    (root / "final_run_manifest.json").write_text('{"pipeline_mode":"MORNING_VALIDATION"}')
    app = Flask(__name__)
    install_interpreter_desk(app, tmp_path, provider=FakeProvider())
    out = app.test_client().post("/api/interpreter/reports", json={
        "run_id": rid, "tickers": ["AAA"], "confirmed": True,
    })
    assert out.status_code == 200
    report = out.json["results"][0]
    assert report["status"] == "COMPLETE"
    assert report["phase"] == "MORNING_DELTA"
    assert report["morning_bundle_id"] == morning_bundle["bundle_id"]
    assert report["evidence_digest"]["eod_manifest_sha256"] == receipt["source_manifest_sha256"]
    assert report["evidence_digest"]["morning_evidence"]["refresh_required"]["trade_thesis_affected"] is False


def test_confluence_reads_six_completed_pit_sessions_and_never_asserts_live_execution(tmp_path):
    import sqlite3
    from pipeline_interpreter.confluence_evidence import build_confluence_evidence

    database = tmp_path / "prices.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE ohlcv_daily (ticker TEXT, trading_date TEXT, "
                       "adjustment_convention TEXT, close REAL, bar_status TEXT, "
                       "fetched_at TEXT, row_hash TEXT)")
    sessions = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"]
    for symbol, start, end in (("SPY", 100, 101), ("XLK", 100, 105), ("AAA", 100, 110)):
        for index, session in enumerate(sessions):
            close = start if index == 0 else end if index == 5 else start + index
            connection.execute("INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?)",
                               (symbol, session, "POLYGON_SPLIT_ADJUSTED", close, "COMPLETE",
                                "2026-09-22T01:00:00Z", symbol + session))
    connection.commit()
    connection.close()
    row = {"ticker": "AAA", "sector_etf": "XLK", "direction": "CALL", "trigger_quality": "STRONG",
           "contract_symbol": "AAA261120C00100000", "contract_bid": 1.0, "contract_ask": 1.1,
           "contract_volume": 15, "contract_bid_size": 20, "contract_ask_size": 30,
           "target_price": 110, "invalidation_price": 95,
           "selected_quote_timestamp_utc": "2026-09-21T20:00:00Z"}
    result = build_confluence_evidence(
        row, session_date=sessions[-1], evidence_cutoff_utc="2026-09-22T02:00:00Z",
        historical_prices_path=database)
    assert result["sector"]["status"] == "SUPPORTS"
    assert result["ticker"]["status"] == "SUPPORTS"
    assert result["thesis"]["status"] == "STRONG_TRIGGER"
    assert result["contract"]["status"] == "EOD_ACTIVE_QUOTE_TRAIT"
    assert result["contract"]["quote_is_live_executable"] is False
    assert result["price_path"]["latest_source_fetch_utc"] <= "2026-09-22T02:00:00+00:00"
    incomplete = dict(row, invalidation_price=None,
                      selected_quote_timestamp_utc="2026-09-23T01:00:00Z")
    incomplete_result = build_confluence_evidence(
        incomplete, session_date=sessions[-1], evidence_cutoff_utc="2026-09-22T02:00:00Z",
        historical_prices_path=database)
    assert incomplete_result["thesis"]["status"] == "GOVERNED_LEVELS_MISSING"
    assert incomplete_result["contract"]["status"] == "QUOTE_TIMESTAMP_UNVERIFIED"

    # A current row revised after the decision may not masquerade as a past observation.
    connection = sqlite3.connect(database)
    connection.execute("UPDATE ohlcv_daily SET fetched_at='2026-09-23T01:00:00Z' "
                       "WHERE ticker='AAA' AND trading_date=?", (sessions[-1],))
    connection.commit()
    connection.close()
    revised = build_confluence_evidence(
        row, session_date=sessions[-1], evidence_cutoff_utc="2026-09-22T02:00:00Z",
        historical_prices_path=database)
    assert revised["ticker"]["status"] == "UNKNOWN"
    assert revised["price_path"]["reason"] == "GAPPED_OR_LATER_REVISED_PRICE_PATH"


def test_report_rejects_confluence_status_invented_by_provider(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    class InventedProvider(FakeProvider):
        def report(self, digest):
            result = super().report(digest)
            result["evidence_chain_review"][0]["status"] = "SUPPORTS"
            return result
    install_interpreter_desk(app, tmp_path, provider=InventedProvider())
    result = app.test_client().post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    }).json["results"][0]
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "REPORT_VALIDATION_FAILED"


def test_report_rejects_missing_counter_case_link(tmp_path):
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    _fixture(tmp_path)
    app = Flask(__name__)
    class SuppressingProvider(FakeProvider):
        def report(self, digest):
            result = super().report(digest)
            result["counter_case"]["links"] = []
            result["counter_case"]["evidence_refs"] = []
            return result
    install_interpreter_desk(app, tmp_path, provider=SuppressingProvider())
    result = app.test_client().post("/api/interpreter/reports", json={
        "run_id": RUN, "tickers": ["AAA"], "confirmed": True,
    }).json["results"][0]
    assert result["status"] == "FAILED"
    assert result["failure_code"] == "REPORT_VALIDATION_FAILED"


def test_openai_prompt_cites_actual_evidence_sources_not_fixed_two_source_list():
    from pipeline_interpreter.openai_desk_provider import OpenAIResponsesProvider

    provider = OpenAIResponsesProvider(
        api_key="offline-test", model_id="offline-test",
        input_usd_per_million=2, output_usd_per_million=12,
        web_search_usd_per_call=0.01, max_ticker_usd=1,
    )
    captured = {}

    def fake_response(**kwargs):
        captured.update(kwargs)
        return {}, set(), {}

    provider._response = fake_response
    provider.report({"evidence_refs": ["EOD_BOOK", "PIT_PRICE_BARS"], "confluence": {}})
    assert "PIT_PRICE_BARS" in captured["instructions"]
    assert "Cite only EOD_BOOK or MORNING_HANDOFF" not in captured["instructions"]


def test_morning_review_uses_latest_accepted_cutoff_for_price_evidence(monkeypatch):
    from pipeline_interpreter import interactive_desk

    observed = {}

    def fake_confluence(row, **kwargs):
        observed.update(kwargs)
        return {"price_path": {"state": "UNKNOWN"}}

    monkeypatch.setattr(interactive_desk, "build_confluence_evidence", fake_confluence)
    frozen = {"meta": {"session_date": "2026-09-22"},
              "receipt": {"evidence_cutoff_utc": "2026-09-22T22:00:00Z"}}
    morning = {"evidence_cutoff_utc": "2026-09-23T14:00:00Z", "fields": {}}
    interactive_desk._confluence_for({"ticker": "AAA"}, frozen, morning)
    assert observed["evidence_cutoff_utc"] == morning["evidence_cutoff_utc"]


def test_morning_review_rejects_a_cutoff_older_than_evening():
    import pytest
    from pipeline_interpreter.interactive_desk import DeskError, _latest_accepted_cutoff

    with pytest.raises(DeskError, match="predates"):
        _latest_accepted_cutoff(
            "2026-09-22T22:00:00Z",
            {"evidence_cutoff_utc": "2026-09-22T21:59:00Z"},
        )


def test_confluence_thesis_reads_governed_invalidation_price_not_producer_alias():
    """AVS-SD-ILA-003 slice 2b: the frozen book column is invalidation_price."""
    from pipeline_interpreter.confluence_evidence import build_confluence_evidence
    row = {"ticker": "AAA", "sector_etf": "XLK", "direction": "CALL", "trigger_quality": "STRONG",
           "target_price": 110, "invalidation_price": 95}
    result = build_confluence_evidence(
        row, session_date="2026-09-22", evidence_cutoff_utc="2026-09-22T16:00:00Z",
        historical_prices_path=Path("missing.sqlite"),
    )
    assert result["thesis"]["status"] == "STRONG_TRIGGER"
    assert result["thesis"]["invalidation_price"] == 95
    alias_only = build_confluence_evidence(
        {**row, "invalidation_price": None, "invalidation_spot": 95},
        session_date="2026-09-22", evidence_cutoff_utc="2026-09-22T16:00:00Z",
        historical_prices_path=Path("missing.sqlite"),
    )
    assert alias_only["thesis"]["status"] == "GOVERNED_LEVELS_MISSING"


def test_confluence_morning_link_uses_governed_validation_transition():
    from pipeline_interpreter.confluence_evidence import build_confluence_evidence
    row = {"ticker": "AAA", "sector_etf": "XLK", "direction": "CALL", "trigger_quality": "STRONG",
           "target_price": 110, "invalidation_price": 95}

    def morning(transition):
        return {"bundle_id": "b-1", "evidence_cutoff_utc": "2026-09-22T15:00:00Z",
                "refresh_required": None,
                "fields": {"validation_transition": transition, "validation_current_price": 101.0,
                           "validation_event_id": "validation_aaa"}}

    def build(m):
        return build_confluence_evidence(
            row, session_date="2026-09-22", evidence_cutoff_utc="2026-09-22T16:00:00Z",
            historical_prices_path=Path("missing.sqlite"), morning=m,
        )["morning"]

    confirmed = build(morning("THESIS_CONFIRMED"))
    assert confirmed["status"] == "THESIS_CONFIRMED"
    assert confirmed["current_price"] == 101.0
    assert confirmed["validation_event_id"] == "validation_aaa"
    assert confirmed["evidence_ref"] == "MORNING_HANDOFF"
    assert build(morning("PENDING_TRIGGER"))["status"] == "PENDING_TRIGGER"
    assert build(morning(None))["status"] == "NOT_RUN_OR_NOT_ACCEPTED"
    assert build(None)["status"] == "NOT_RUN_OR_NOT_ACCEPTED"


def test_morning_evidence_extracts_governed_validation_fields(tmp_path, monkeypatch):
    import pipeline_interpreter.evidence_resolver as resolver
    from pipeline_interpreter.interactive_desk import _morning_evidence
    root = tmp_path / RUN
    (root / "interpreter").mkdir(parents=True)
    (root / "interpreter" / "handoff_manifest.json").write_text("{}")
    governed = {"thesis_state": "ACTIVE", "final_action": "BUY_NOW",
                "validation_transition": "THESIS_CONFIRMED", "validation_reason": "gap within band",
                "validation_current_price": 101.0, "validation_event_id": "validation_aaa",
                "selected_contract_symbol": "AAA261120C00100000"}
    monkeypatch.setattr(resolver, "resolve_interpreter_evidence", lambda *a, **k: type("R", (), {
        "bundle": {"bundle_id": "b-1", "governed_record": governed},
        "manifest": {"morning_gate_completed_utc": "2026-09-22T15:00:00Z"},
        "refresh_required": None,
    })())
    evidence = _morning_evidence(root, "AAA")
    assert evidence["fields"]["validation_transition"] == "THESIS_CONFIRMED"
    assert evidence["fields"]["validation_current_price"] == 101.0
    assert evidence["fields"]["validation_event_id"] == "validation_aaa"
    assert evidence["fields"]["validation_reason"] == "gap within band"
    assert "morning_thesis_result" not in evidence["fields"]


def test_digest_carries_governed_invalidation_price_to_the_model():
    from contracts.interpreter_eod_review import build_eod_review_bundle
    from pipeline_interpreter.interactive_desk import compile_evidence_digest
    row = {"run_id": RUN, "ticker": "AAA", "direction": "CALL", "thesis_id": "TH-A",
           "target_price": 110, "invalidation_price": 95, "contract_symbol": "AAA261120C00100000"}
    bundle = build_eod_review_bundle(run_id=RUN, source_manifest_sha256="a" * 64, row=row,
                                     evidence_refs=[{"dataset_id": "EOD_BOOK", "sha256": "b" * 64}])
    digest = compile_evidence_digest(
        row, bundle, evidence_cutoff_utc="2026-09-22T01:00:00Z", eod_technical_health="PASS",
        confluence={"price_path": {"state": "UNKNOWN"}},
    )
    assert digest["eod_fields"]["invalidation_price"] == 95
    assert "invalidation_spot" not in digest["eod_fields"]


def test_report_counter_case_treats_confirmed_morning_as_supportive_and_pending_as_opposing():
    from pipeline_interpreter.interactive_desk import DeskError, _validate_report
    base_confluence = {
        "sector": {"status": "SUPPORTS", "evidence_ref": "EOD_BOOK"},
        "ticker": {"status": "SUPPORTS", "evidence_ref": "EOD_BOOK"},
        "thesis": {"status": "STRONG_TRIGGER", "evidence_ref": "EOD_BOOK"},
        "contract": {"status": "EOD_ACTIVE_QUOTE_TRAIT", "evidence_ref": "EOD_BOOK"},
    }

    def output(confluence, counter_links):
        return {
            "executive_summary": "summary",
            "sections": [{"key": key, "text": "t", "evidence_class": "OBSERVED", "evidence_refs": ["EOD_BOOK"]}
                         for key in SECTIONS],
            "evidence_chain_review": [
                {"key": key, "status": confluence[key]["status"], "text": "t",
                 "evidence_class": "DERIVED", "evidence_refs": [confluence[key]["evidence_ref"]]}
                for key in ("sector", "ticker", "thesis", "contract", "morning")],
            "counter_case": {"links": counter_links, "text": "t",
                             "evidence_refs": ["EOD_BOOK", "MORNING_HANDOFF"]},
            "external_events": [], "unresolved": [],
        }

    allowed = {"EOD_BOOK", "MORNING_HANDOFF"}
    confirmed = {**base_confluence, "morning": {"status": "THESIS_CONFIRMED", "evidence_ref": "MORNING_HANDOFF"}}
    _validate_report(output(confirmed, []), allowed, "2026-09-22T15:00:00Z", confirmed)
    pending = {**base_confluence, "morning": {"status": "PENDING_TRIGGER", "evidence_ref": "MORNING_HANDOFF"}}
    try:
        _validate_report(output(pending, []), allowed, "2026-09-22T15:00:00Z", pending)
    except DeskError as error:
        assert "counter-case" in str(error)
    else:
        raise AssertionError("PENDING_TRIGGER Morning must be required in the counter-case")


def test_unusable_provider_reply_persists_typed_reason_without_prose(tmp_path):
    """ACK 24 Sep 2026: a controlled failure names its case in typed fields, never provider text."""
    from pipeline_interpreter.desk_provider_common import ProviderReplyUnusable
    from pipeline_interpreter.interactive_desk import install_interpreter_desk

    root = _fixture(tmp_path)
    app = Flask(__name__)
    class UnusableReplyProvider(FakeProvider):
        def report(self, digest):
            self.reports.append(digest)
            raise ProviderReplyUnusable("NO_STRUCTURED_TOOL_CALL", stop_reason="pause_turn",
                                        block_types=["text", "server_tool_use"])

    provider = UnusableReplyProvider()
    install_interpreter_desk(app, tmp_path, provider=provider)
    client = app.test_client()
    body = {"run_id": RUN, "tickers": ["AAA"], "confirmed": True}
    first = client.post("/api/interpreter/reports", json=body).json["results"][0]
    assert first["status"] == "FAILED"
    assert first["failure_code"] == "PROVIDER_CONTROLLED_FAILURE"
    assert first["provider_failure_reason"] == "NO_STRUCTURED_TOOL_CALL"
    assert first["provider_stop_reason"] == "pause_turn"
    assert first["provider_block_types"] == ["text", "server_tool_use"]
    assert first["retry_allowed"] is False
    marker = next((root / "interpreter" / "interactive_desk" / "AAA").glob("*.error.json"))
    assert json.loads(marker.read_text(encoding="utf-8")) == first
    assert client.post("/api/interpreter/reports", json=body).json["results"][0] == first
    assert len(provider.reports) == 1
