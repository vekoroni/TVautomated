"""AVS-SD-LAB-004: compact review is a read model, never a second decision engine."""
from copy import deepcopy
import ast
import importlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def projection():
    return importlib.import_module("contracts.lab_review_projection")


def book():
    return {"run_id": "TEST_RUN", "lab_schema_version": "lab_signal_book_v4",
            "created_at_utc": "2026-10-10T09:00:00Z", "candidate_count": 3, "rows": [
        {"ticker": "AAA", "thesis_id": "TH1", "trade_lane_candidate_id": "CA1",
         "contract_symbol": "AAA270115C00100000", "direction": "CALL", "sector": "Technology",
         "lab_rank": 2, "lab_verdict": "MANUAL_REVIEW", "contract_bid": 4.0, "contract_ask": 4.2,
         "anticipated_value_multiple_q50": 1.24, "planned_hold_sessions": 54,
         "quote_freshness": "AGED_REFERENCE", "thesis_phase": "E",
         "source_payload_json": "DO_NOT_COPY" * 1000, "field_provenance_json": '{"direction":"Discovery"}',
         "ev3_ev": -0.38, "contract_gamma": 0.0238},
        {"ticker": "AAA", "thesis_id": "TH2", "trade_lane_candidate_id": "CA2",
         "contract_symbol": "AAA270115P00100000", "direction": "PUT", "sector": "Technology",
         "lab_rank": 1, "lab_verdict": "FLAG", "anticipated_value_multiple_q50": None,
         "target_price": 999, "priority_score": 100},
        {"ticker": "BBB", "direction": "UNRESOLVED", "sector": None, "lab_rank": 3,
         "lab_verdict": "MANUAL_REVIEW", "contract_symbol": None, "contract_oi": None},
    ]}


def publish(tmp_path, **kwargs):
    return projection().publish_review_projection(book(), tmp_path, **kwargs)


def test_characterises_wide_load_before_slim_and_forecast_before_render():
    tree = ast.parse((ROOT / "intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8"))
    route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "api_run")
    assert "_slim_lab_payload(_load_run(run_id))" in ast.unparse(route)
    js = (ROOT / "intelligence-lab/static/index.html").read_text(encoding="utf-8")
    body = js.split("async function loadRun(runId)", 1)[1].split("async function refreshIf", 1)[0]
    assert body.index("forecast_book/") < body.index("RUN_DATA = data")


def test_preserves_all_rows_exact_facts_and_multiple_same_ticker_theses(tmp_path):
    m = projection(); source = book(); frozen = deepcopy(source)
    receipt = m.publish_review_projection(source, tmp_path)
    result = m.read_review_rows(tmp_path, "TEST_RUN", revision=receipt["revision"])
    assert len(result["rows"]) == result["total_rows"] == 3
    assert len({r["row_key"] for r in result["rows"]}) == 3
    assert [r["lab_rank"] for r in result["rows"]] == [2, 1, 3]  # no new rank or sort
    first = m.read_review_card(tmp_path, "TEST_RUN", result["rows"][0]["row_key"], receipt["revision"])
    assert first["fields"]["planned_hold_sessions"] == 54
    assert first["fields"]["anticipated_value_multiple_q50"] == 1.24
    assert source == frozen


def test_missing_owner_is_not_filled_from_legacy_alias(tmp_path):
    m = projection(); receipt = publish(tmp_path)
    rows = m.read_review_rows(tmp_path, "TEST_RUN")["rows"]
    card = m.read_review_card(tmp_path, "TEST_RUN", rows[1]["row_key"], receipt["revision"])
    assert card["fields"]["anticipated_value_multiple_q50"] is None
    assert card["fields"]["anticipated_level_q50"] is None
    assert card["field_states"]["anticipated_level_q50"] == "NOT_RECORDED"
    assert "target_price" not in card["fields"]
    last = m.read_review_card(tmp_path, "TEST_RUN", rows[2]["row_key"], receipt["revision"])
    assert last["fields"]["thesis_id"] is None
    assert last["identity_state"] == "THESIS_ID_MISSING"


def test_quote_age_discloses_but_never_changes_verdict_or_rank(tmp_path):
    m = projection(); b = book(); one = m.publish_review_projection(b, tmp_path)
    a = m.read_review_rows(tmp_path, "TEST_RUN")["rows"]
    b["rows"][0]["quote_freshness"] = "VERY_OLD_REFERENCE"
    m.publish_review_projection(b, tmp_path)
    c = m.read_review_rows(tmp_path, "TEST_RUN")["rows"]
    assert [(r["direction"], r["lab_verdict"], r["lab_rank"]) for r in a] == [
        (r["direction"], r["lab_verdict"], r["lab_rank"]) for r in c]
    with pytest.raises(m.ReviewRevisionConflict):
        m.read_review_rows(tmp_path, "TEST_RUN", revision=one["revision"])


def test_midpoint_spread_validates_quote_without_gate(tmp_path):
    m = projection(); publish(tmp_path); rows = m.read_review_rows(tmp_path, "TEST_RUN")["rows"]
    assert rows[0]["spread_pct_mid"] == pytest.approx(4.87804878)
    b = book(); b["rows"][0]["contract_bid"] = 5
    m.publish_review_projection(b, tmp_path)
    first = m.read_review_rows(tmp_path, "TEST_RUN")["rows"][0]
    assert first["spread_pct_mid"] is None and first["spread_state"] == "INVALID_QUOTE"
    assert first["lab_verdict"] == "MANUAL_REVIEW"


def test_sector_distribution_keeps_unknown_and_no_contract(tmp_path):
    m = projection(); publish(tmp_path); s = m.read_review_summary(tmp_path, "TEST_RUN")
    sectors = {r["sector"]: r for r in s["sector_distribution"]}
    assert sectors["Information Technology"]["bull_theses"] == 1
    assert sectors["Information Technology"]["bear_theses"] == 1
    assert sectors["UNKNOWN"]["unresolved_theses"] == 1
    assert sectors["UNKNOWN"]["selected_expressions"] == 0
    assert s["sector_context"]["state"] == "NOT_PUBLISHED"
    assert "avg_ev" not in json.dumps(s)


def test_lazy_evidence_is_indexed_and_default_has_no_full_row_copies(tmp_path):
    m = projection(); r = publish(tmp_path); rows = m.read_review_rows(tmp_path, "TEST_RUN")["rows"]
    card = m.read_review_card(tmp_path, "TEST_RUN", rows[0]["row_key"], r["revision"])
    assert "DO_NOT_COPY" not in json.dumps({"rows": rows, "card": card})
    audit = m.read_review_evidence(tmp_path, "TEST_RUN", rows[0]["row_key"], "audit", r["revision"])
    assert audit["fields"]["ev3_ev"] == -0.38
    greeks = m.read_review_evidence(tmp_path, "TEST_RUN", rows[0]["row_key"], "option_risk", r["revision"])
    assert greeks["fields"]["contract_gamma"] == 0.0238
    assert "ev3_ev" not in greeks["fields"]


def test_publication_failure_keeps_previous_generation(tmp_path, monkeypatch):
    m = projection(); receipt = publish(tmp_path); original = m._atomic_manifest
    def fail(*args, **kwargs):
        raise OSError("injected publication failure")
    monkeypatch.setattr(m, "_atomic_manifest", fail)
    with pytest.raises(OSError):
        publish(tmp_path)
    monkeypatch.setattr(m, "_atomic_manifest", original)
    assert m.read_review_summary(tmp_path, "TEST_RUN")["revision"] == receipt["revision"]


def test_bad_population_or_cross_run_row_never_publishes(tmp_path):
    m = projection(); b = book(); b["candidate_count"] = 4
    with pytest.raises(ValueError): m.publish_review_projection(b, tmp_path)
    b = book(); b["rows"][0]["run_id"] = "OTHER"
    with pytest.raises(ValueError): m.publish_review_projection(b, tmp_path)


@pytest.mark.parametrize("run", ["..", "../data", "C:/outside", "a\\b"])
def test_paths_are_not_controlled_by_browser(tmp_path, run):
    with pytest.raises(ValueError): projection().read_review_summary(tmp_path, run)


def test_api_never_calls_the_legacy_loader_and_missing_projection_is_explicit(tmp_path):
    from flask import Flask
    m = projection(); app = Flask(__name__); m.register_review_routes(app, tmp_path)
    client = app.test_client()
    assert client.get("/api/lab/TEST_RUN/summary").status_code == 404
    receipt = publish(tmp_path)
    response = client.get("/api/lab/TEST_RUN/rows?page=1&page_size=1")
    assert response.status_code == 200 and len(response.json["rows"]) == 1
    assert response.json["total_rows"] == 3
    assert client.get("/api/lab/TEST_RUN/rows?revision=wrong").status_code == 409
    assert client.get("/api/lab/TEST_RUN/rows?page_size=100000").status_code == 400
    key = response.json["rows"][0]["row_key"]
    assert client.get(f"/api/lab/TEST_RUN/rows/{key}?revision={receipt['revision']}").status_code == 200
    assert client.get(f"/api/lab/TEST_RUN/rows/{key}/evidence/not_allowed").status_code == 400


def test_database_tampering_is_not_accepted(tmp_path):
    m = projection(); receipt = publish(tmp_path)
    path = tmp_path / "TEST_RUN" / "intelligence_lab" / "review_projection" / receipt["database_file"]
    with path.open("ab") as f: f.write(b"tampered")
    with pytest.raises(m.ReviewIntegrityError): m.read_review_rows(tmp_path, "TEST_RUN")


def test_existing_writer_publishes_additive_projection_after_full_book(tmp_path, monkeypatch):
    import contracts.lab_control as control
    m = projection(); calls = []
    real = m.publish_review_projection
    def capture(payload, runs_dir, **kw):
        assert (Path(runs_dir) / payload["run_id"] / "intelligence_lab" /
                f"final_opportunity_book_{payload['run_id']}.json").is_file()
        calls.append(payload["candidate_count"])
        return real(payload, runs_dir, **kw)
    monkeypatch.setattr(m, "publish_review_projection", capture)
    result = control.write_final_opportunity_book("TEST_RUN", [{"ticker": "ABC", "direction": "UNRESOLVED"}],
        {}, tmp_path, sync_interpreter=False, contract_quote_lookup=lambda *a: None)
    assert calls == [len(result["rows"])]
    assert result["review_projection"]["publication_state"] == "COMPLETE"
    assert m.read_review_summary(tmp_path, "TEST_RUN")["row_count"] == len(result["rows"])


def test_existing_flask_app_registers_fast_routes_without_using_wide_loader(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("lab004_test_app", ROOT / "intelligence-lab/intelligence_lab.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, "RUNS_DIR", tmp_path)
    def forbid(*a, **kw):
        raise AssertionError("A compact request cannot call the wide loader")
    monkeypatch.setattr(module, "_load_run", forbid)
    publish(tmp_path)
    response = module.app.test_client().get("/api/lab/TEST_RUN/rows")
    assert response.status_code == 200
    assert response.json["total_rows"] == 3


def test_manifest_count_cannot_disagree_with_indexed_population(tmp_path):
    m = projection(); publish(tmp_path)
    path = tmp_path / "TEST_RUN/intelligence_lab/review_projection/manifest.json"
    data = json.loads(path.read_text()); data["row_count"] = 100
    path.write_text(json.dumps(data))
    with pytest.raises(m.ReviewIntegrityError): m.read_review_summary(tmp_path, "TEST_RUN")


def test_concurrent_cold_reads_verify_once_and_share_only_immutable_identity(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    m = projection(); receipt = publish(tmp_path); m._verified_hash.cache_clear()
    real = m._digest; calls = []
    def count(path):
        calls.append(path)
        return real(path)
    monkeypatch.setattr(m, "_digest", count)
    with ThreadPoolExecutor(max_workers=10) as pool:
        result = list(pool.map(lambda _: m.read_review_rows(tmp_path, "TEST_RUN"), range(10)))
    assert len(calls) == 1
    assert {r["revision"] for r in result} == {receipt["revision"]}
    assert all(len(r["rows"]) == 3 for r in result)


def test_source_book_change_is_disclosed_without_rebuilding(tmp_path):
    m = projection(); folder = tmp_path / "TEST_RUN/intelligence_lab"
    folder.mkdir(parents=True)
    path = folder / "final_opportunity_book_TEST_RUN.json"
    path.write_text(json.dumps(book()))
    m.publish_review_projection(book(), tmp_path, source_receipt=m.source_file_receipt(path))
    path.write_text("changed publication")
    with pytest.raises(m.ReviewRevisionConflict): m.read_review_rows(tmp_path, "TEST_RUN")


def test_evidence_storage_is_lossless_and_does_not_repeat_wide_text_on_disk(tmp_path):
    m = projection(); b = book(); text = "repeated provenance and raw evidence " * 20000
    b["rows"][0]["raw_diagnostic"] = text
    receipt = m.publish_review_projection(b, tmp_path)
    row = m.read_review_rows(tmp_path, "TEST_RUN")["rows"][0]
    audit = m.read_review_evidence(tmp_path, "TEST_RUN", row["row_key"], "audit")
    assert audit["fields"]["raw_diagnostic"] == text
    assert receipt["database_bytes"] < len(text.encode()) / 3
