from __future__ import annotations

import sqlite3
from datetime import date

from scripts.phantom_path_coverage_plan import audit_decisions


def _db(tmp_path):
    path = tmp_path / "phantom.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE chain_snapshots (ticker TEXT, quote_date TEXT, option_symbol TEXT, bid REAL, ask REAL)")
    conn.executemany(
        "INSERT INTO chain_snapshots VALUES (?,?,?,?,?)",
        [
            ("AAA", "2026-09-24", "AAA270115C00100000", 1.0, 1.1),
            ("AAA", "2026-09-25", "OTHER", 1.0, 1.1),
            ("AAA", "2026-09-28", "AAA270115C00100000", None, 1.1),
        ],
    )
    conn.commit()
    conn.close()
    return path


def _row():
    return {"run_id": "20260924_220000", "ticker": "AAA", "thesis_id": "T1",
            "evidence_session_date": "2026-09-24", "selected_contract_symbol": "AAA270115C00100000"}


def test_coverage_distinguishes_request_from_review_and_future(tmp_path):
    result = audit_decisions([_row()], _db(tmp_path), through_session=date(2026, 9, 29), max_sessions=5)
    states = {r["session_date"]: r["state"] for r in result["observations"]}
    assert states == {"2026-09-24": "TWO_SIDED_QUOTE_OBSERVED",
                      "2026-09-25": "CONTRACT_ABSENT_IN_CHAIN",
                      "2026-09-28": "QUOTE_UNUSABLE",
                      "2026-09-29": "CHAIN_MISSING"}
    assert result["request_candidates"] == [{"ticker": "AAA", "session_date": "2026-09-29",
                                             "reason": "CHAIN_MISSING", "maintenance_lane": "TARGETED_WEEKDAY_GAP",
                                             "affected_contracts": ["AAA270115C00100000"]}]
    assert result["summary"]["future_session_count"] == 1


def test_missing_symbol_never_becomes_provider_request(tmp_path):
    row = _row()
    row["selected_contract_symbol"] = ""
    result = audit_decisions([row], _db(tmp_path), through_session=date(2026, 9, 29), max_sessions=2)
    assert result["request_candidates"] == []
    assert result["summary"]["decisions_without_contract"] == 1


def test_duplicate_decisions_and_chain_rows_do_not_duplicate_requests(tmp_path):
    row = _row()
    result = audit_decisions([row, row], _db(tmp_path), through_session=date(2026, 9, 29), max_sessions=4)
    assert len(result["request_candidates"]) == 1


def test_morning_contract_starts_at_validation_not_evening(tmp_path):
    row = _row()
    row.update(pipeline_mode="MORNING_VALIDATION", validation_event_id="event-1",
               validation_evidence_cutoff_utc="2026-09-28T15:00:00Z")
    result = audit_decisions([row], _db(tmp_path), through_session=date(2026, 9, 29), max_sessions=2)
    assert [r["session_date"] for r in result["observations"]] == ["2026-09-28", "2026-09-29"]
    assert {r["source_mode"] for r in result["observations"]} == {"MORNING_VALIDATION"}


def test_morning_row_without_validation_lineage_cannot_request_data(tmp_path):
    row = _row()
    row["pipeline_mode"] = "MORNING_VALIDATION"
    result = audit_decisions([row], _db(tmp_path), through_session=date(2026, 9, 29), max_sessions=2)
    assert result["request_candidates"] == []
    assert result["summary"]["decisions_missing_validation_lineage"] == 1


def test_missing_friday_routes_to_weekly_baseline(tmp_path):
    row = _row()
    result = audit_decisions([row], _db(tmp_path), through_session=date(2026, 10, 2), max_sessions=7)
    friday = next(r for r in result["request_candidates"] if r["session_date"] == "2026-10-02")
    assert friday["maintenance_lane"] == "WEEKLY_FRIDAY_BASELINE"
