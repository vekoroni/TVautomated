"""B4.2 (ACK 12 Oct 2026): every thesis event carries a stable id, a status that develops, and its clocks.

Business rules (design Part B: R1 signal timeline, N2 event life cycle, B1 event status):
- The pipeline identifies data for mining; it does not decide the trade. So the trigger event is published at the
  FIRST close beyond the trigger (OBSERVED) and its status develops run by run: PROVISIONALLY_SUCCESSFUL at a
  provisional accepted break, CONFIRMED at a full acceptance or a held retest, FAILED at a failed break, a failed
  retest or an invalidation (terminal). No crossing yet -> FORMING. Events not measured -> NOT_MEASURED (never neutral).
- The event id is stable across runs for the same thesis, side and trigger level (forming -> confirmed keeps its id);
  a new crossing of the same level is a new entry opportunity under the same event.
- trigger_close_date is the first close beyond the trigger; trigger_age_sessions counts completed sessions after it on
  the session calendar of the bars read; confirmed_at / failed_at / occurred_at come only from bars already closed.
- The ticker row carries the governing thesis's clocks and the source bar's close time; the fields travel
  Discovery -> EOD -> Morning -> Lab through the one thesis field definition.
"""
import copy

import numpy as np
import pandas as pd

from contracts.thesis_record import THESIS_SPINE_FIELDS, event_timeline

SESSIONS = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-09-01", periods=10)]


def _ev(name, i, **extra):
    return {"event": name, "index": i, "date": SESSIONS[i], "level": 102.0, "interval": "1d", **extra}


def _tl(events, side="BULL", status="MEASURED", cid="T|1d|CAMPAIGN|SOS|2026-08-20"):
    return event_timeline(events, side=side, candidate_id=cid, events_status=status, trigger_level=102.0,
                          session_dates=SESSIONS)


def test_no_crossing_is_forming_with_a_stable_id():
    out = _tl([])
    assert out["Event_Status"] == "FORMING" and out["Trigger_Close_Date"] is None
    assert out["Event_ID"] and out["Entry_Opportunity_ID"] is None


def test_first_close_beyond_is_observed_at_that_close():
    out = _tl([_ev("BREAK_ATTEMPT_UP", 7)])
    assert out["Event_Status"] == "OBSERVED"
    assert out["Trigger_Close_Date"] == SESSIONS[7]
    assert out["Trigger_Age_Sessions"] == 2                     # sessions 8 and 9 closed after the trigger close
    assert out["Event_Occurred_At"] == SESSIONS[7]


def test_status_develops_provisional_then_confirmed():
    prov = _tl([_ev("BREAK_ATTEMPT_UP", 5), _ev("BREAK_ACCEPTED_UP", 6, provisional=True)])
    assert prov["Event_Status"] == "PROVISIONALLY_SUCCESSFUL" and prov["Event_Confirmed_At"] is None
    full = _tl([_ev("BREAK_ATTEMPT_UP", 5), _ev("BREAK_ACCEPTED_UP", 8, provisional=False)])
    assert full["Event_Status"] == "CONFIRMED" and full["Event_Confirmed_At"] == SESSIONS[8]
    held = _tl([_ev("BREAK_ATTEMPT_UP", 3), _ev("BREAK_ACCEPTED_UP", 4, provisional=True),
                _ev("RETEST_HELD_UP", 8)])
    assert held["Event_Status"] == "CONFIRMED" and held["Event_Confirmed_At"] == SESSIONS[8]


def test_failure_is_terminal_and_dated():
    out = _tl([_ev("BREAK_ATTEMPT_UP", 5), _ev("FAILED_BREAK_UP", 6), _ev("VWAP_RECLAIM", 8)])
    assert out["Event_Status"] == "FAILED" and out["Event_Failed_At"] == SESSIONS[6]
    inv = _tl([_ev("BREAK_ATTEMPT_UP", 2), _ev("BREAK_ACCEPTED_UP", 3, provisional=False), _ev("INVALIDATED", 7)])
    assert inv["Event_Status"] == "FAILED" and inv["Event_Failed_At"] == SESSIONS[7]


def test_the_id_survives_development_and_the_opportunity_follows_the_crossing():
    forming, observed = _tl([]), _tl([_ev("BREAK_ATTEMPT_UP", 7)])
    confirmed = _tl([_ev("BREAK_ATTEMPT_UP", 7), _ev("BREAK_ACCEPTED_UP", 9, provisional=False)])
    assert forming["Event_ID"] == observed["Event_ID"] == confirmed["Event_ID"]
    assert observed["Entry_Opportunity_ID"] == confirmed["Entry_Opportunity_ID"]
    later = _tl([_ev("BREAK_ATTEMPT_UP", 9)])
    assert later["Entry_Opportunity_ID"] != observed["Entry_Opportunity_ID"]
    other_side = _tl([], side="BEAR")
    assert other_side["Event_ID"] != forming["Event_ID"]


def test_opposite_side_events_do_not_move_the_thesis_event():
    out = _tl([_ev("BREAK_ATTEMPT_DOWN", 6), _ev("FAILED_BREAK_DOWN", 7)])
    assert out["Event_Status"] == "FORMING"


def test_unmeasured_events_are_never_neutral():
    out = _tl([], status="NOT_MEASURED:INSUFFICIENT_BARS")
    assert out["Event_Status"] == "NOT_MEASURED" and out["Trigger_Age_Sessions"] is None


def test_the_thesis_field_definition_carries_the_clocks():
    assert {"thesis__event_id", "thesis__event_status", "thesis__entry_opportunity_id", "thesis__trigger_close_date",
            "thesis__trigger_age_sessions", "thesis__event_occurred_at", "thesis__event_confirmed_at",
            "thesis__event_failed_at", "thesis__policy_qualified_at", "thesis__source_bar_end_at",
            "thesis__discovery_read_at", "thesis__setup_first_detected_at",
            "thesis__setup_first_detected_run"} <= set(THESIS_SPINE_FIELDS)


def test_discovery_attaches_the_clocks_from_its_own_bars():
    import avshunter_discovery_ULTIMATE as disc
    from domain.structure_behaviour.policy import load_policy
    policy = copy.deepcopy(dict(load_policy()))
    policy["timeframes"]["1d"]["min_bars"] = 20
    closes = [100 + 0.5 * np.sin(i) for i in range(30)] + [102.5, 103.5, 104.0, 104.2]
    dates = pd.bdate_range("2026-01-02", periods=len(closes))
    df = pd.DataFrame({"date": dates, "open": closes, "high": np.array(closes) + 0.6,
                       "low": np.array(closes) - 0.6, "close": closes, "volume": 1e6})
    origin = dates[24].strftime("%Y-%m-%d")
    cand = {"Candidate_ID": f"T|1d|CAMPAIGN|SOS -> LPS continuation|{origin}", "Timeframe": "1d",
            "Proposed_Side": "BULL", "Thesis_Side": "BULL", "Adoption_State": "ADOPTED",
            "Trigger_Level": 102.0, "Invalidation_Level": 98.0, "Outcome_Level": 110.0}
    disc._attach_trigger_events({"candidates": [cand], "readings": {}}, df, policy)
    assert cand["Trigger_Close_Date"] == dates[30].strftime("%Y-%m-%d")      # first close beyond 102
    assert cand["Trigger_Age_Sessions"] == 3
    assert cand["Event_Status"] in {"PROVISIONALLY_SUCCESSFUL", "CONFIRMED"} and cand["Event_ID"]


def test_ticker_row_clocks_from_the_governing_thesis():
    import avshunter_discovery_ULTIMATE as disc
    gov = {"Candidate_ID": "T|1d|X|2026-08-20", "Event_ID": "e1", "Event_Status": "OBSERVED",
           "Entry_Opportunity_ID": "o1", "Trigger_Close_Date": "2026-09-10", "Trigger_Age_Sessions": 1,
           "Event_Occurred_At": "2026-09-10", "Event_Confirmed_At": None, "Event_Failed_At": None,
           "Readiness": "WAIT_TRIGGER", "Readiness_Event_Date": None}
    row = disc._event_clock_fields(gov, last_bar_date="2026-09-11", read_at="2026-09-11T22:00:00+00:00")
    assert row["thesis__event_status"] == "OBSERVED" and row["thesis__trigger_close_date"] == "2026-09-10"
    assert row["thesis__policy_qualified_at"] is None                         # legacy policy v0 not met yet
    assert row["thesis__source_bar_end_at"] == "2026-09-11T20:00:00+00:00"   # 16:00 New York (EDT)
    ready = disc._event_clock_fields({**gov, "Readiness": "READY_FOR_HUMAN_REVIEW",
                                      "Readiness_Event_Date": "2026-09-11"}, last_bar_date="2026-01-15",
                                     read_at=None)
    assert ready["thesis__policy_qualified_at"] == "2026-09-11"
    assert ready["thesis__source_bar_end_at"] == "2026-01-15T21:00:00+00:00"  # 16:00 New York (EST)
    none = disc._event_clock_fields({}, last_bar_date="2026-09-11", read_at=None)
    assert none["thesis__event_status"] == "NO_GOVERNING_THESIS"


def test_first_detection_is_filled_from_the_candidate_ledger():
    import avshunter_discovery_ULTIMATE as disc
    rows = [{"ticker": "T", "thesis_trigger_candidate_id": "T|1d|X|2026-08-20"}, {"ticker": "U"}]
    cands = [{"Candidate_ID": "T|1d|X|2026-08-20", "First_Seen_As_Of": "2026-08-21", "First_Seen_Run": "R1"}]
    disc._fill_first_detection(rows, cands)
    assert rows[0]["thesis__setup_first_detected_at"] == "2026-08-21"
    assert rows[0]["thesis__setup_first_detected_run"] == "R1"
    assert rows[1]["thesis__setup_first_detected_at"] is None


def test_invalidation_before_any_crossing_fails_and_bar_order_rules():
    out = _tl([_ev("INVALIDATED", 4)])
    assert out["Event_Status"] == "FAILED" and out["Event_Failed_At"] == SESSIONS[4]
    # the detector lists events by kind; an invalidation dated before the crossing still ends the event
    out = _tl([_ev("BREAK_ATTEMPT_UP", 8), _ev("INVALIDATED", 5)])
    assert out["Event_Status"] == "FAILED" and out["Trigger_Close_Date"] is None


def test_the_daily_store_says_when_the_last_bar_arrived(tmp_path):
    # R1 data_received_at: the provider landing time of the last completed bar, as recorded by the store.
    from datetime import datetime, timezone
    from canonical_data import HistoricalPriceDatabase
    db = HistoricalPriceDatabase(tmp_path / "p.sqlite")
    db.initialise()
    bars = pd.DataFrame([{"date": "2026-09-10", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1e3},
                         {"date": "2026-09-11", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 1e3}])
    landed = datetime(2026, 9, 11, 21, 5, tzinfo=timezone.utc)
    db.ingest("AB", bars, provider="POLYGON", source_kind="PROVIDER_FETCH", fetched_at=landed)
    frame = db.read("AB")
    assert list(frame.columns) == ["date", "open", "high", "low", "close", "volume"]   # bar columns unchanged
    assert frame.attrs["last_bar_fetched_at"].startswith("2026-09-11T21:05")
    assert frame.attrs["last_bar_provider"] == "POLYGON"


def test_ticker_row_carries_the_landing_time():
    import avshunter_discovery_ULTIMATE as disc
    row = disc._event_clock_fields({}, last_bar_date="2026-09-11", read_at=None,
                                   data_received_at="2026-09-11T21:05:00+00:00")
    assert row["thesis__data_received_at"] == "2026-09-11T21:05:00+00:00"
    assert "thesis__data_received_at" in THESIS_SPINE_FIELDS


def test_the_lab_card_shows_the_event_status_and_clocks():
    from pathlib import Path
    from contracts.lab_review_projection import CARD_FIELDS, HOME_FIELDS
    assert {"thesis__event_status", "thesis__trigger_age_sessions"} <= set(HOME_FIELDS)
    assert {"thesis__event_status", "thesis__trigger_close_date", "thesis__trigger_age_sessions",
            "thesis__event_confirmed_at", "thesis__event_failed_at", "thesis__setup_first_detected_at",
            "thesis__data_received_at", "thesis__contract_prepared_at", "thesis__last_revalidated_at",
            "thesis__delivered_at"} <= set(CARD_FIELDS)
    js = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "review-app.js").read_text("utf-8")
    assert "Event status" in js and "thesis__event_status" in js and "Event clocks" in js


def test_options_morning_and_publish_stamp_their_own_clocks():
    # R1 (B4.2 part 2): each stage stamps the moment it acted; the stamps travel with the thesis fields to the book.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert {"thesis__contract_prepared_at", "thesis__last_revalidated_at",
            "thesis__delivered_at"} <= set(THESIS_SPINE_FIELDS)
    options = (root / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8-sig")
    assert "'contract_prepared_at_utc'" in options.split("'contract_quote_timestamp_utc': contract.get(", 1)[1][:400]
    allow = options.split("'ev3_handoff_schema_version','contract_quote_timestamp_utc'", 1)[1][:300]
    assert "'contract_prepared_at_utc'" in allow
    eod = (root / "eod_candidate_engine.py").read_text(encoding="utf-8-sig")
    assert 'candidate["thesis__contract_prepared_at"] = row.get("contract_prepared_at_utc")' in eod
    gate = (root / "morning_gate.py").read_text(encoding="utf-8-sig")
    assert 'out["thesis__last_revalidated_at"] = out["gate_checked_at_utc"]' in gate


def test_the_published_book_stamps_delivery_on_every_row():
    from contracts.lab_control import build_final_opportunity_book
    rows = build_final_opportunity_book("RUN", [{"ticker": "X", "signal_price": 100.0},
                                                {"ticker": "Y", "signal_price": 50.0}])
    stamps = {r["thesis__delivered_at"] for r in rows}
    assert len(stamps) == 1 and next(iter(stamps)).startswith("20")


def test_the_evidence_bars_behind_the_status_are_published():
    # N2: the bars that set the status are named (event@bar date), so the label can be checked against the chart.
    out = _tl([_ev("BREAK_ATTEMPT_UP", 3), _ev("VWAP_RECLAIM", 4), _ev("BREAK_ACCEPTED_UP", 5, provisional=False)])
    assert out["Event_Evidence"] == f"BREAK_ATTEMPT_UP@{SESSIONS[3]};BREAK_ACCEPTED_UP@{SESSIONS[5]}"
    assert _tl([])["Event_Evidence"] == ""
    assert "thesis__event_evidence" in THESIS_SPINE_FIELDS
