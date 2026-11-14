"""LAB-004 next slice: verified evidence without a second decision owner."""
import importlib
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from copy import deepcopy
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module():
    return importlib.import_module("contracts.lab_review_sources")


def row(thesis="TH1", contract="ABC270115C00100000"):
    return {"run_id": "RUN", "ticker": "ABC", "thesis_id": thesis,
            "trade_idea_id": "IDEA:" + thesis, "direction": "CALL",
            "selected_contract_symbol": contract, "contract_symbol": contract,
            "lab_verdict": "MANUAL_REVIEW", "lab_rank": 4, "final_action": "REVIEW"}


def book(rows=None):
    rows = rows if rows is not None else [row(), row("TH2")]
    return {"run_id": "RUN", "candidate_count": len(rows), "rows": rows, "lab_schema_version": "lab_signal_book_v4"}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_verified_overlay_matches_exact_thesis_without_ticker_collapse():
    m = module(); source = book(); frozen = deepcopy(source)
    overlay = {**row("TH2"), "ms_reason_code": "PROFILE_CONFIRMED", "lab_verdict": "GO", "lab_rank": 1}
    result, receipt = m.overlay_verified_rows(source["rows"], [overlay])
    assert len(result) == 2 and result[0].get("ms_reason_code") is None
    assert result[1]["ms_reason_code"] == "PROFILE_CONFIRMED"
    assert result[1]["lab_verdict"] == "MANUAL_REVIEW" and result[1]["lab_rank"] == 4
    assert receipt["actionable_rows_overlaid"] == 1
    assert source == frozen


def test_wrong_contract_overlay_is_rejected_not_promoted():
    m = module(); source = [row()]
    result, receipt = m.overlay_verified_rows(source, [{**row(contract="ABC270115P00100000"), "ms_reason_code": "WRONG"}])
    assert receipt["actionable_rows_rejected"] == 1
    assert result[0].get("ms_reason_code") is None and result[0]["direction"] == "CALL"


def test_rejected_handoff_keeps_all_base_rows_and_records_reason(tmp_path):
    m = module(); root = tmp_path / "RUN"; write(root / "interpreter/handoff_manifest.json", {})
    def reject(*args, **kw):
        raise ValueError("HANDOFF_RUN_NOT_ACCEPTED")
    result, context, receipt = m.prepare_review_publication(book(), root, handoff_validator=reject)
    assert len(result["rows"]) == 2
    assert receipt["overlay_state"] == "REJECTED"
    assert "HANDOFF_RUN_NOT_ACCEPTED" in receipt["issues"][0]
    assert result["rows"][0]["lab_verdict"] == "MANUAL_REVIEW"


def test_macro_and_breadth_keep_different_times_and_never_invent_money_flow(tmp_path):
    m = module(); root = tmp_path / "RUN"
    write(root / "macro_snapshot.json", {"as_of_utc": "2026-10-08T20:00:00Z", "regime_state": "MIXED",
        "sector_rotation": {"rotation_signal": "DEFENSIVE_ROTATION", "sector_bias_map": {"Financials": "TAILWIND"}}})
    write(root / "diagnostics/market_breadth_diagnostic_RUN.json", {"run_id": "RUN", "diagnostic": "P10_MARKET_BREADTH_READ_ONLY",
        "generated_at_utc": "2026-10-09T05:00:00Z", "breadth": {"leaders": [{"ticker": "XLF", "name": "Financials", "daily_pct": 1.2, "weekly_pct": -0.4}], "laggards": []}})
    result, context, receipt = m.prepare_review_publication(book(), root)
    assert context["sector"]["rotation_signal"] == "DEFENSIVE_ROTATION"
    sector = context["sector"]["rows"][0]
    assert sector["bias"] == "TAILWIND" and sector["daily_pct"] == 1.2
    assert sector["money_flow"] is None and sector["money_flow_state"] == "NOT_PUBLISHED"
    assert sector["bias_as_of_utc"] != sector["breadth_generated_at_utc"]
    assert result["rows"][0]["lab_rank"] == 4


def test_bad_breadth_run_is_not_used(tmp_path):
    m = module(); root = tmp_path / "RUN"
    write(root / "diagnostics/market_breadth_diagnostic_RUN.json", {"run_id": "OTHER", "diagnostic": "P10_MARKET_BREADTH_READ_ONLY", "breadth": {}})
    _, context, receipt = m.prepare_review_publication(book(), root)
    assert context["sector"]["state"] == "NOT_PUBLISHED"
    assert any("BREADTH_RUN_MISMATCH" in item for item in receipt["issues"])


def test_validation_event_is_selected_by_run_thesis_and_contract_not_latest_ticker(tmp_path):
    m = module(); root = tmp_path / "RUN"
    for thesis, date in [("TH1", "2026-10-09T15:00:00Z"), ("TH2", "2026-10-09T16:00:00Z")]:
        write(root / f"morning_validation/validation_events/{thesis}.json", {
            "invocation_id": "RUN", "ticker": "ABC", "thesis_id": thesis,
            "selected_contract": row()["contract_symbol"], "execution_gate_result": {"final_action": "REVIEW"},
            "validation_event_id": "EVENT:" + thesis, "evidence_cutoff_utc": date,
            "transition": "THESIS_CONFIRMED", "data_status": "COMPLETE"})
    result, _, receipt = m.prepare_review_publication(book(), root)
    assert [r["validation_event_id"] for r in result["rows"]] == ["EVENT:TH1", "EVENT:TH2"]
    assert receipt["validation_events_applied"] == 2


def test_acceptance_validator_is_required_and_run_is_checked(tmp_path):
    m = module(); root = tmp_path / "RUN"; path = root / "interpreter/handoff_manifest.json"; write(path, {})
    calls = []
    def validate(path, **kw):
        calls.append(kw); return SimpleNamespace(manifest={"run_id": "OTHER"}, book_rows=(row(),), artifacts={})
    result, _, receipt = m.prepare_review_publication(book(), root, handoff_validator=validate)
    assert calls == [{"require_accepted": True}]
    assert receipt["overlay_state"] == "REJECTED" and len(result["rows"]) == 2


def test_review_source_signature_drift_is_disclosed(tmp_path):
    m = module(); root = tmp_path / "RUN"; write(root / "macro_snapshot.json", {"regime_state": "MIXED"})
    prepared, context, receipt = m.prepare_review_publication(book(), root)
    from contracts.lab_review_projection import publish_review_projection, read_review_summary, ReviewRevisionConflict
    publish_review_projection(prepared, tmp_path, context=context, source_receipt=receipt)
    write(root / "macro_snapshot.json", {"regime_state": "CHANGED"})
    with pytest.raises(ReviewRevisionConflict): read_review_summary(tmp_path, "RUN")


def test_morning_projection_waits_for_the_accepted_handoff_and_summary():
    root = Path(__file__).resolve().parents[1]
    text = (root / "morning_handoff_finalizer.py").read_text(encoding="utf-8")
    body = text.split("def finalize_morning_handoff(", 1)[1].split("def main()", 1)[0]
    assert "publish_review=False" in body
    assert body.index("_publish_msi_handoff(") < body.index("publish_review_projection(")
    assert body.index("_atomic_json(summary_path, summary)") < body.index("publish_review_projection(")


def test_review_screen_is_opt_in_and_never_waits_for_forecast_or_legacy_loader():
    root = Path(__file__).resolve().parents[1]
    html = (root / "intelligence-lab/static/review.html").read_text(encoding="utf-8")
    assert "review-app.js" in html and "trade-card.js" not in html
    js = (root / "intelligence-lab/static/review-app.js").read_text(encoding="utf-8")
    assert "/api/lab/" in js and "/forecast_book/" not in js
    assert "/api/interpreter/saved_reports" in js and "/api/interpreter/reports" not in js
    app = (root / "intelligence-lab/intelligence_lab.py").read_text(encoding="utf-8")
    # ACK 13 Oct 2026: the page is served at the root only; the /review alias is retired.
    assert '@app.route("/review")' not in app and '@app.route("/")' in app


def test_live_finalizer_reuses_its_verified_event_receipt_without_reopening_files(tmp_path, monkeypatch):
    m = module(); root = tmp_path / "RUN"; event_dir=root / "morning_validation/validation_events"
    event_dir.mkdir(parents=True);write(event_dir / "invalid.json", {"invalid":"would be rejected if read"})
    original_read=Path.read_text
    def forbid_event_read(path,*args,**kwargs):
        if path.parent==event_dir: raise AssertionError("Verified events must not be reopened")
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,"read_text",forbid_event_read)
    source=book();source["rows"][0]["validation_event_id"]="VERIFIED_EVENT"
    receipt={"status":"PASS","authority":"VALIDATION_ONLY","input_rows":2,"lab_projection_issues":[]}
    prepared,_,out=m.prepare_review_publication(source,root,validation_receipt=receipt)
    assert out["validation_events_applied"]==1
    assert out["validation_unmatched_rows"]==1
    assert out["validation_event_state"]=="UPSTREAM_IDENTITY_VERIFIED_RECEIPT"


def test_invalid_in_memory_receipt_is_not_trusted(tmp_path):
    with pytest.raises(ValueError):
        module().prepare_review_publication(book(),tmp_path / "RUN",validation_receipt={
            "status":"PASS","authority":"VALIDATION_ONLY","input_rows":200,"lab_projection_issues":[]})


def test_compression_uses_discovery_canonical_columns_on_the_exact_setup_timeframe(tmp_path):
    m=module(); root=tmp_path/'RUN'; path=root/'discovery/discovery_candidates_ultimate_RUN.csv'
    path.parent.mkdir(parents=True)
    source={'ticker':'ABC','trade_lane_candidate_id':'CAND1','beh__1w_compression_state':'CONTRACTING',
            'beh__1d_compression_state':'NONE','beh__1w_compression_location':'AT_SUPPORT','crabel_compression':'OLD'}
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(source));writer.writeheader();writer.writerow(source)
    b=book([dict(row(),trade_lane_candidate_id='CAND1',thesis_event_timeframe='1w')])
    prepared,_,receipt=m.prepare_review_publication(b,root)
    assert prepared['rows'][0]['compression_state']=='CONTRACTING'
    assert prepared['rows'][0]['compression_timeframe']=='1w'
    assert prepared['rows'][0]['compression_source']=='DISCOVERY_BEH001_CANONICAL'
    b['rows'][0]['trade_lane_candidate_id']='OTHER'
    rejected,_,_=m.prepare_review_publication(b,root)
    assert rejected['rows'][0].get('compression_state') is None
    assert rejected['rows'][0]['compression_projection_state']=='SETUP_IDENTITY_MISMATCH'


def test_republish_after_macro_appears_preserves_source_and_all_rows(tmp_path, monkeypatch):
    from contracts.lab_review_projection import read_review_summary, read_review_rows, ReviewRevisionConflict
    import requests
    def forbidden(*args, **kwargs):
        raise AssertionError('Display publication must not call providers')
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    m=module(); root=tmp_path/'RUN'
    path=root/'intelligence_lab/final_opportunity_book_RUN.json'
    write(path,book()); original=path.read_bytes()
    old=m.republish_saved_review('RUN',tmp_path)
    write(root/'interpreter/interpreter_macro_context.json',{
        'schema_version':'interpreter_macro_context_v1','regime_state':'PINNED_ADVISORY'})
    with pytest.raises(ReviewRevisionConflict): read_review_summary(tmp_path,'RUN')
    new=m.republish_saved_review('RUN',tmp_path)
    assert new['revision']!=old['revision'] and new['row_count']==2
    assert read_review_summary(tmp_path,'RUN')['macro_context']['regime_state']=='PINNED_ADVISORY'
    assert read_review_rows(tmp_path,'RUN')['total_rows']==2
    assert path.read_bytes()==original
    assert (root/'intelligence_lab/review_projection'/old['database_file']).is_file()
    write(root/'interpreter/interpreter_macro_context.json',{'changed':True})
    with pytest.raises(ReviewRevisionConflict): read_review_summary(tmp_path,'RUN')


def test_eod_review_waits_for_shared_macro_without_worker3():
    root=Path(__file__).resolve().parents[1]
    text=(root/'intelligent_orchestrator.py').read_text(encoding='utf-8')
    start=text.index('_lab_book = write_final_opportunity_book(')
    end=text.index('# AVS-FIX-001 W3.9:',start)
    body=text[start:end]
    assert 'publish_review=False' in body
    assert body.index('materialize_lab_macro_evidence(')<body.index('republish_saved_review(')
    assert 'materialize_worker3_market_environment(' not in body
