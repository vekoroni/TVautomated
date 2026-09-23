"""Offline end-to-end Lab/Interpreter acceptance with a fake GPT transport."""

from __future__ import annotations

import json

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
             "thesis_id": "TH-A", "target_price": 110, "invalidation_spot": 95,
             "profile_type": "D_SHAPED", "poc": 101, "call_wall": 105,
             "contract_symbol": "AAA261120C00100000"},
            {"run_id": RUN, "ticker": "BBB", "direction": "PUT", "final_action": "BLOCK",
             "thesis_id": "TH-B", "target_price": 90, "invalidation_spot": 105,
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
        return {
            "executive_summary": "The frozen Evening thesis has a defined target and invalidation.",
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


def test_large_lab_row_is_bounded_without_discarding_governed_facts():
    from pipeline_interpreter.interactive_desk import compile_evidence_digest

    row = {f"unrelated_field_{index}": "X" * 400 for index in range(634)}
    row.update({"ticker": "PFE", "canonical_direction": "CALL",
                "invalidation_spot": 24.75, "planned_hold_sessions": 10,
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
    assert digest["eod_fields"]["invalidation_spot"] == 24.75
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
            "final_action": "EOD_CANDIDATE_ONLY", "target_price": 110, "invalidation_spot": 95,
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
