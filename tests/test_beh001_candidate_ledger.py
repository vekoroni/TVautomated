"""BEH-001 C-03 core / RQ-2: candidate identity and life cycle across runs.

Business rules:
- A candidate keeps its identity across runs; its life cycle is an append-only
  history (first seen, state changes, level revisions, no longer detected,
  reappeared). Unchanged readings add nothing.
- A candidate disappears only on evidence: its ticker was read this run and the
  candidate was not produced. An unread ticker closes nothing (missing is never neutral).
- A successor created by a failure names its parent, and the lineage can be followed.
- Recording the ledger never fails Discovery.
"""
import json
import sqlite3

import pytest

from canonical_data.behavioural_candidate_ledger import BehaviouralCandidateLedger


def cand(ticker="AAA", state="DETECTED", trigger=10.0, invalidation=9.0, outcome=12.0,
         kind="Spring Candidate", label="2026-09-01", parent=None, as_of="2026-09-30"):
    return {"Candidate_ID": f"{ticker}|1d|CAMPAIGN|{kind}|{label}", "Ticker": ticker, "Timeframe": "1d",
            "Signal_Type": kind, "Signal_State": state, "Direction": "BULL", "As_Of": as_of,
            "Trigger_Level": trigger, "Invalidation_Level": invalidation, "Outcome_Level": outcome,
            "Parent_Candidate_ID": parent, "Age_Bars": 3}


@pytest.fixture
def ledger(tmp_path):
    return BehaviouralCandidateLedger(tmp_path / "beh_ledger.sqlite")


def events(ledger, candidate_id):
    return [e["event_type"] for e in ledger.history(candidate_id)]


def test_first_run_records_first_seen_and_annotates_candidates(ledger):
    rows = [cand(), cand(ticker="BBB")]
    ledger.record_run("R1", rows, read_tickers={"AAA", "BBB"})
    assert events(ledger, rows[0]["Candidate_ID"]) == ["FIRST_SEEN"]
    assert rows[0]["Lifecycle_Event"] == "FIRST_SEEN"
    assert rows[0]["First_Seen_Run"] == "R1"


def test_unchanged_reading_adds_no_event_and_keeps_first_seen(ledger):
    ledger.record_run("R1", [cand()], read_tickers={"AAA"})
    again = [cand(as_of="2026-10-01")]
    ledger.record_run("R2", again, read_tickers={"AAA"})
    assert events(ledger, again[0]["Candidate_ID"]) == ["FIRST_SEEN"]
    assert again[0]["Lifecycle_Event"] == "UNCHANGED"
    assert again[0]["First_Seen_Run"] == "R1"
    assert again[0]["First_Seen_As_Of"] == "2026-09-30"


def test_state_change_and_level_revision_are_recorded(ledger):
    ledger.record_run("R1", [cand()], read_tickers={"AAA"})
    ledger.record_run("R2", [cand(state="ACTIVATED")], read_tickers={"AAA"})
    ledger.record_run("R3", [cand(state="ACTIVATED", outcome=12.5)], read_tickers={"AAA"})
    history = ledger.history(cand()["Candidate_ID"])
    assert [e["event_type"] for e in history] == ["FIRST_SEEN", "STATE_CHANGED", "LEVELS_REVISED"]
    assert history[1]["previous_state"] == "DETECTED" and history[1]["signal_state"] == "ACTIVATED"


def test_disappearance_needs_the_ticker_to_have_been_read(ledger):
    ledger.record_run("R1", [cand(), cand(ticker="BBB")], read_tickers={"AAA", "BBB"})
    ledger.record_run("R2", [], read_tickers={"AAA"})          # BBB not read this run
    assert events(ledger, cand()["Candidate_ID"]) == ["FIRST_SEEN", "NO_LONGER_DETECTED"]
    assert events(ledger, cand(ticker="BBB")["Candidate_ID"]) == ["FIRST_SEEN"]
    back = [cand()]
    ledger.record_run("R3", back, read_tickers={"AAA"})
    assert events(ledger, cand()["Candidate_ID"])[-1] == "REAPPEARED"
    assert back[0]["Lifecycle_Event"] == "REAPPEARED"


def test_successor_names_its_parent_and_lineage_is_followed(ledger):
    parent = cand()
    ledger.record_run("R1", [parent], read_tickers={"AAA"})
    child = cand(kind="Failed Spring Continuation", parent=parent["Candidate_ID"])
    child["Direction"] = "BEAR"
    ledger.record_run("R2", [cand(state="FAILED"), child], read_tickers={"AAA"})
    assert ledger.history(child["Candidate_ID"])[0]["parent_candidate_id"] == parent["Candidate_ID"]
    assert ledger.lineage(child["Candidate_ID"]) == [child["Candidate_ID"], parent["Candidate_ID"]]
    assert ledger.history(parent["Candidate_ID"])[-1]["signal_state"] == "FAILED"


def test_rerunning_the_same_run_is_idempotent(ledger):
    ledger.record_run("R1", [cand()], read_tickers={"AAA"})
    ledger.record_run("R1", [cand()], read_tickers={"AAA"})
    assert events(ledger, cand()["Candidate_ID"]) == ["FIRST_SEEN"]


def test_ledger_is_append_only(ledger):
    ledger.record_run("R1", [cand()], read_tickers={"AAA"})
    with sqlite3.connect(ledger.database_path) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE candidate_events SET signal_state='X'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM candidate_events")


def test_discovery_ledger_failure_never_fails_the_run(tmp_path):
    import avshunter_discovery_ULTIMATE as discovery
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    rows = [cand()]
    status = discovery._beh001_record_ledger(rows, {"AAA"}, "R1", blocker / "ledger.sqlite")
    assert status.startswith("LEDGER_ERROR:")
    assert rows[0]["Lifecycle_Event"] == "LEDGER_UNAVAILABLE"
    ok = discovery._beh001_record_ledger(rows, {"AAA"}, "R1", tmp_path / "ledger.sqlite")
    assert ok == "RECORDED" and rows[0]["Lifecycle_Event"] == "FIRST_SEEN"


def test_outcome_reached_is_a_stage_change_not_a_closure(ledger):
    ledger.record_run("R1", [cand(state="ACTIVATED")], read_tickers={"AAA"})
    ledger.record_run("R2", [cand(state="OUTCOME_REACHED")], read_tickers={"AAA"})
    again = [cand(state="OUTCOME_REACHED")]
    ledger.record_run("R3", again, read_tickers={"AAA"})
    assert events(ledger, cand()["Candidate_ID"]) == ["FIRST_SEEN", "STATE_CHANGED"]
    assert again[0]["Lifecycle_Event"] == "UNCHANGED"


def test_only_a_ticker_that_stops_trading_ends_its_life_cycle(ledger):
    rows = [cand(), cand(ticker="BBB")]
    ledger.record_run("R1", rows, read_tickers={"AAA", "BBB"},
                      ticker_last_bar={"AAA": "2026-09-30", "BBB": "2026-09-30"})
    stale = [cand(as_of="2026-09-30"), cand(ticker="BBB", as_of="2026-10-20")]
    ledger.record_run("R2", stale, read_tickers={"AAA", "BBB"},
                      ticker_last_bar={"AAA": "2026-09-30", "BBB": "2026-10-20"})
    assert events(ledger, cand()["Candidate_ID"]) == ["FIRST_SEEN", "TICKER_NOT_TRADING"]
    assert stale[0]["Lifecycle_Event"] == "TICKER_NOT_TRADING"
    assert events(ledger, cand(ticker="BBB")["Candidate_ID"]) == ["FIRST_SEEN"]
    back = [cand(as_of="2026-10-21")]
    ledger.record_run("R3", back, read_tickers={"AAA"}, ticker_last_bar={"AAA": "2026-10-21"})
    assert events(ledger, cand()["Candidate_ID"])[-1] == "REAPPEARED"


def test_every_row_is_annotated_even_if_ids_collide(ledger):
    rows = [cand(), cand(trigger=10.5)]
    ledger.record_run("R1", rows, read_tickers={"AAA"})
    assert all(r["Lifecycle_Event"] for r in rows)
    assert rows[1]["Lifecycle_Event"] == "DUPLICATE_ID_IN_RUN"


def test_ledger_payload_keeps_lifecycle_fields_only(ledger):
    """Evening 1 Oct: 90 MB after one run (2.3 KB per event). The payload keeps the
    identity, state, levels and lineage needed to replay the life cycle."""
    row = cand()
    row.update({"Evidence": "x" * 5000, "SOT_State": "y" * 500, "Wyckoff_Phase": "D"})
    ledger.record_run("R1", [row], read_tickers={"AAA"})
    payload = json.loads(ledger.history(row["Candidate_ID"])[0]["payload_json"])
    assert "SOT_State" not in payload and "Evidence" not in payload
    assert payload["Signal_State"] == "DETECTED" and payload["Wyckoff_Phase"] == "D"
    assert len(ledger.history(row["Candidate_ID"])[0]["payload_json"]) < 800
