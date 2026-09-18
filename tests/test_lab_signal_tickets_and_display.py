"""Intelligence Lab shows what the pipeline decided, as recorded (ACK 18 Sep 2026).

Findings from the 18 Sep review of run 20260918_112522:
- the Lab never showed the signal tickets or the watchlist;
- 554 MANUAL_REVIEW rows were ranked below the 381 BLOCKED rows (lab_verdict order had no MANUAL_REVIEW);
- the 20-session valuation fields and the contract runway / spread-above-limit facts never reached the book;
- the Lab's own re-selection path re-labelled an end-of-day quote as "timestamp unavailable".
All fixes are display only: nothing here ranks, values or decides.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB_PATH = ROOT / "intelligence-lab" / "intelligence_lab.py"


def _lab():
    spec = importlib.util.spec_from_file_location("intelligence_lab_tickets_test", LAB_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- book ordering -------------------------------------------------------------------------------------------

def test_manual_review_rows_are_ranked_above_blocked_rows():
    from contracts.lab_control import build_final_opportunity_book
    signals = [
        {"ticker": "BLK", "final_action": "BLOCK", "lab_verdict": "BLOCKED", "morning_lab_alignment_status": "X",
         "priority_score": 90},
        {"ticker": "REV", "final_action": "MANUAL_REVIEW", "lab_verdict": "MANUAL_REVIEW",
         "morning_lab_alignment_status": "X", "priority_score": 10},
        {"ticker": "GOO", "final_action": "BUY_NOW", "lab_verdict": "GO", "morning_lab_alignment_status": "X",
         "priority_score": 5},
    ]
    rows = build_final_opportunity_book("RUN-T", signals, {"pipeline_mode": "MORNING_VALIDATION"})
    assert [r["ticker"] for r in rows] == ["GOO", "REV", "BLK"]


# --- book fields ---------------------------------------------------------------------------------------------

def test_book_carries_the_valuation_and_contract_runway_facts():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    sig = {"ticker": "ABC", "final_direction": "CALL", "emp_path_r_cautious": 0.088, "emp_path_r_central": 0.103,
           "emp_path_r_upside": 0.11, "emp_path_last_exit_sessions": 20, "emp_path_forced_exit_share": 0.0,
           "emp_path_quality_flag": "OK", "contract_runway_floor_days": 19, "contract_runway_basis": "HORIZON:1_5d",
           "contract_runway_state": "RUNWAY_COVERED", "spread_above_limit": False,
           "anticipated_move_sessions": 5, "anticipated_move_source": "DISCOVERY_THESIS_HORIZON",
           "planned_hold_sessions": 20, "planned_hold_source": "THESIS_WINDOW_D2"}
    row = opportunity_book_row(sig, "RUN-T", 1)
    for field, value in sig.items():
        if field in ("ticker", "final_direction"):
            continue
        assert field in FINAL_BOOK_FIELDS, field
        assert row[field] == value, field


# --- signal tickets and watchlist ----------------------------------------------------------------------------

def _write_tickets(folder: Path, *, watchlist: bool):
    folder.mkdir(parents=True)
    stem = "signal_tickets_RUN-T_2026-09-18"
    fields = ["ticket_id", "rank", "ticker", "direction", "contract_symbol", "scored_entry", "r_cautious"]
    with (folder / f"{stem}.csv").open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=fields)
        w.writeheader()
        w.writerow({"ticket_id": "T1", "rank": 1, "ticker": "UPS", "direction": "CALL",
                    "contract_symbol": "UPS261218C00100000", "scored_entry": 5.36, "r_cautious": 0.088})
    if watchlist:
        with (folder / f"{stem}_watchlist.csv").open("w", newline="", encoding="utf-8") as h:
            w = csv.DictWriter(h, fieldnames=["listing"] + fields)
            w.writeheader()
            w.writerow({"listing": "WATCHLIST_RANKED_NOT_ISSUED", "ticket_id": "T6", "rank": 6, "ticker": "ZZZ",
                        "direction": "PUT", "contract_symbol": "ZZZ261218P00050000", "scored_entry": 1.1,
                        "r_cautious": 0.01})
    (folder / f"{stem}_summary.json").write_text(json.dumps({
        "status": "ISSUED", "run_id": "RUN-T", "issue_session": "2026-09-18", "evidence_session": "2026-09-17",
        "issued": 1, "ranked": 6, "watchlist": 1 if watchlist else 0,
        "rejections": {"FINAL_ACTION_BLOCKED": 3, "RANK_BELOW_DAILY_CAP": 5},
        "csv": str(folder / f"{stem}.csv")}), encoding="utf-8")


def test_lab_serves_tickets_and_watchlist_exactly_as_recorded(tmp_path, monkeypatch):
    lab = _lab()
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    _write_tickets(tmp_path / "RUN-T" / "signals", watchlist=True)
    data = lab.app.test_client().get("/api/signal_tickets/RUN-T").get_json()
    assert data["ok"] is True and data["state"] == "ISSUED"
    assert data["authority"] == "DECISION_SUPPORT_ONLY"
    assert [(t["rank"], t["ticker"]) for t in data["tickets"]] == [("1", "UPS")]           # as written, not re-ranked
    assert [(t["rank"], t["ticker"]) for t in data["watchlist"]] == [("6", "ZZZ")]
    assert data["watchlist_state"] == "PRESENT"
    assert data["summary"]["rejections"]["FINAL_ACTION_BLOCKED"] == 3


def test_missing_watchlist_and_missing_tickets_are_named_not_empty(tmp_path, monkeypatch):
    lab = _lab()
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    _write_tickets(tmp_path / "RUN-T" / "signals", watchlist=False)
    data = lab.app.test_client().get("/api/signal_tickets/RUN-T").get_json()
    assert data["watchlist_state"] == "NOT_PRODUCED" and data["watchlist"] == []
    (tmp_path / "RUN-N").mkdir()
    none = lab.app.test_client().get("/api/signal_tickets/RUN-N").get_json()
    assert none["ok"] is True and none["state"] == "NOT_ISSUED" and none["tickets"] == []


def test_lab_page_has_a_signal_tickets_tab_and_labels_for_the_new_states():
    page = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert "switchLab('tickets'" in page and "renderSignalTickets" in page
    assert "/signal_tickets/" in page
    for label in ("EOD_QUOTE_PENDING_MORNING_REQUOTE", "RUNWAY_SHORT_REVIEW", "MANUAL_REVIEW"):
        assert label in page, label
