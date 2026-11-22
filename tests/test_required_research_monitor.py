import json
from contracts.required_research_monitor import required_tickers, disclosure, write_coverage


def test_capr_required_only_during_requested_week():
    assert "CAPR" not in required_tickers("2026-11-22")
    for day in range(23, 28):
        assert "CAPR" in required_tickers(f"2026-11-{day}")
    assert "CAPR" not in required_tickers("2026-11-28")


def test_event_disclosure_does_not_modify_scores_or_permissions():
    row = {"ticker": "CAPR", "options_research_score": 77, "execution_permission": "WAIT"}
    fields = disclosure(row, "2026-11-23")
    assert fields["thesis_reassessment_status"] == "REASSESSMENT_REQUIRED"
    assert fields["monitoring_execution_authority"] == "NONE"
    assert row["execution_permission"] == "WAIT"
    assert "thesis_reassessment_status" not in row
    assert not disclosure(row, "2026-11-20")["thesis_reassessment_status"]


def test_absent_ticker_is_reported_without_fabricated_trade(tmp_path):
    path = write_coverage(tmp_path, [{"ticker": "OTHER"}], as_of="2026-11-23", stage="TEST")
    report = json.loads(path.read_text())
    row = report["rows"][0]
    assert row["ticker"] == "CAPR"
    assert row["coverage_state"] == "ABSENT_REQUIRES_ATTENTION"
    assert row["source_row_count"] == 0
    assert "options_research_score" not in row


def test_saved_review_gets_current_notice_without_changing_decision(tmp_path, monkeypatch):
    import contracts.required_research_monitor as monitor
    from contracts.lab_review_projection import (
        publish_review_projection, read_review_rows, read_review_card, read_review_summary,
    )
    from test_lab_review_projection_v1 import book
    monkeypatch.setattr(monitor, "session_date", lambda as_of=None: "2026-11-23")
    saved = book()
    saved["rows"] = [dict(saved["rows"][0], ticker="CAPR")]
    saved["candidate_count"] = 1
    publish_review_projection(saved, tmp_path)
    rows = read_review_rows(tmp_path, saved["run_id"])["rows"]
    row = rows[0]
    assert row["current_monitoring"]["required_monitoring"]
    assert row["current_monitoring"]["thesis_reassessment_status"] == "REASSESSMENT_REQUIRED"
    card = read_review_card(tmp_path, saved["run_id"], row["row_key"])
    assert card["fields"]["lab_verdict"] == saved["rows"][0]["lab_verdict"]
    assert card["current_monitoring"]["thesis_reassessment_status"] == "REASSESSMENT_REQUIRED"
    summary = read_review_summary(tmp_path, saved["run_id"])
    assert summary["current_required_monitoring"]["rows"][0]["coverage_state"] == "PRESENT"
