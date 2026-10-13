"""B4.2 part 2 (R3, ACK 12 Oct 2026): the opportunity ledger - every thesis event and entry opportunity, as it develops.

Business rules:
- Append-only (no update, no delete). One row when an event or opportunity is first seen and one each time its status
  changes (FORMING -> OBSERVED -> PROVISIONALLY_SUCCESSFUL -> CONFIRMED / FAILED); an unchanged status adds nothing and
  re-recording the same run adds nothing (idempotent).
- Keyed on event_id and entry_opportunity_id, with the thesis (candidate) id, side, trigger level, the trigger close
  date and the run that saw it. Candidates with no directed trigger are not opportunities.
- Outcome views are measured from the bars, never stored guesses: fill at the next session's open after the trigger
  close; ATR(14) frozen at the trigger close; +1 / +3 / +5 / +10 session returns in ATR on the thesis side; MFE / MAE
  over 10 sessions; the first +-1 ATR barrier (favourable / adverse to the side) with same-bar ambiguity flagged; a view without enough sessions is
  CENSORED (missing is never neutral). Underlying only, gross of costs - context for mining, not a verdict.
"""
import sqlite3

import numpy as np
import pandas as pd
import pytest

from canonical_data.behavioural_candidate_ledger import BehaviouralCandidateLedger
from domain.opportunity_outcomes import opportunity_outcome_views


def _cand(status, opp="o1", cid="T|1d|X|2026-08-20", event="e1", tcd="2026-09-10"):
    return {"Candidate_ID": cid, "Ticker": "T", "Timeframe": "1d", "Thesis_Side": "BULL", "Trigger_Level": 102.0,
            "Event_ID": event, "Event_Status": status, "Entry_Opportunity_ID": opp, "Trigger_Close_Date": tcd,
            "Event_Occurred_At": tcd, "As_Of": "2026-09-11", "Readiness": "WAIT_TRIGGER"}


@pytest.fixture
def ledger(tmp_path):
    led = BehaviouralCandidateLedger(tmp_path / "l.sqlite", level_tolerance=0.001, not_trading_after_sessions=5)
    led.initialise()
    return led


def test_first_sight_and_each_status_change_are_recorded_once(ledger):
    assert ledger.record_opportunities("R1", [_cand("OBSERVED")]) == {"NEW": 1}
    assert ledger.record_opportunities("R1", [_cand("OBSERVED")]) == {}             # same run again: nothing
    assert ledger.record_opportunities("R2", [_cand("OBSERVED")]) == {}             # unchanged: nothing
    assert ledger.record_opportunities("R3", [_cand("CONFIRMED")]) == {"STATUS_CHANGED": 1}
    rows = ledger.opportunity_history("e1")
    assert [r["event_status"] for r in rows] == ["OBSERVED", "CONFIRMED"]
    assert rows[0]["previous_status"] is None and rows[1]["previous_status"] == "OBSERVED"
    assert rows[1]["entry_opportunity_id"] == "o1" and rows[1]["trigger_close_date"] == "2026-09-10"


def test_forming_then_a_crossing_is_a_new_opportunity_under_the_same_event(ledger):
    ledger.record_opportunities("R1", [_cand("FORMING", opp=None, tcd=None)])
    ledger.record_opportunities("R2", [_cand("OBSERVED", opp="o1")])
    rows = ledger.opportunity_history("e1")
    assert [(r["entry_opportunity_id"], r["event_status"]) for r in rows] == [(None, "FORMING"), ("o1", "OBSERVED")]


def test_not_an_opportunity_without_a_directed_trigger(ledger):
    undirected = {**_cand("NO_DIRECTED_TRIGGER"), "Event_ID": None}
    assert ledger.record_opportunities("R1", [undirected, {"Candidate_ID": "U|1d|Y"}]) == {}


def test_the_opportunity_table_is_append_only(ledger):
    ledger.record_opportunities("R1", [_cand("OBSERVED")])
    with sqlite3.connect(ledger.database_path) as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE opportunity_events SET event_status='X'")
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM opportunity_events")


def _bars(closes, opens=None, spread=1.0):
    closes = np.asarray(closes, float)
    opens = closes if opens is None else np.asarray(opens, float)
    dates = pd.bdate_range("2026-08-03", periods=len(closes))
    return pd.DataFrame({"date": dates, "open": opens, "high": np.maximum(opens, closes) + spread,
                         "low": np.minimum(opens, closes) - spread, "close": closes, "volume": 1e6})


def test_outcome_views_fill_at_the_next_open_and_measure_in_atr():
    closes = [100.0] * 20 + [103.0] + [104.0 + i for i in range(10)]      # trigger close at index 20
    bars = _bars(closes)
    tcd = bars["date"].iloc[20].strftime("%Y-%m-%d")
    v = opportunity_outcome_views(bars, trigger_close_date=tcd, side="BULL")
    assert v["fill_date"] == bars["date"].iloc[21].strftime("%Y-%m-%d") and v["fill_price"] == 104.0
    atr = v["atr_at_trigger"]
    assert atr > 0
    assert v["ret_1_atr"] == pytest.approx((104.0 - 104.0) / atr, abs=1e-9)      # +1 = the fill session's close
    assert v["ret_3_atr"] == pytest.approx((106.0 - 104.0) / atr, abs=1e-9)
    assert v["ret_10_atr"] == pytest.approx((113.0 - 104.0) / atr, abs=1e-9)
    assert v["mfe_10_atr"] > 0 and v["first_barrier"] == "FAVOURABLE" and v["views_status"] == "COMPLETE"


def test_bear_side_is_signed_and_short_history_is_censored():
    closes = [100.0] * 20 + [97.0, 96.0, 95.0]
    bars = _bars(closes)
    bars.loc[21, "open"] = 97.0                                         # filled at 97, closed at 96
    tcd = bars["date"].iloc[20].strftime("%Y-%m-%d")
    v = opportunity_outcome_views(bars, trigger_close_date=tcd, side="BEAR")
    assert v["ret_1_atr"] is not None and v["ret_1_atr"] > 0               # price fell: good for the bear side
    assert v["ret_5_atr"] is None and v["ret_10_atr"] is None
    assert v["views_status"] == "CENSORED"


def test_no_session_after_the_trigger_close_is_pending():
    bars = _bars([100.0] * 21)
    tcd = bars["date"].iloc[20].strftime("%Y-%m-%d")
    v = opportunity_outcome_views(bars, trigger_close_date=tcd, side="BULL")
    assert v["views_status"] == "PENDING_FILL" and v["fill_price"] is None


def test_same_bar_barrier_ambiguity_is_flagged():
    closes = [100.0] * 20 + [101.0, 101.0]
    bars = _bars(closes, spread=0.4)
    bars.loc[21, ["high", "low"]] = [130.0, 70.0]                        # both barriers inside the fill bar
    tcd = bars["date"].iloc[20].strftime("%Y-%m-%d")
    v = opportunity_outcome_views(bars, trigger_close_date=tcd, side="BULL")
    assert v["first_barrier"] == "AMBIGUOUS_SAME_BAR"


def test_discovery_records_opportunities_beside_the_candidate_ledger(tmp_path):
    import avshunter_discovery_ULTIMATE as disc
    path = tmp_path / "led.sqlite"
    cands = [{**_cand("OBSERVED"), "Signal_State": "DETECTED", "Direction": "BULL"}]
    status = disc._beh001_record_ledger(cands, {"T"}, "R1", path)
    assert status == "RECORDED"
    led = BehaviouralCandidateLedger(path, level_tolerance=0.001, not_trading_after_sessions=5)
    assert [r["event_status"] for r in led.opportunity_history("e1")] == ["OBSERVED"]


def test_cohort_is_one_row_per_opportunity_with_recognition_lag_and_views():
    from domain.opportunity_outcomes import opportunity_cohort
    closes = [100.0] * 20 + [103.0] + [104.0 + i for i in range(10)]
    bars = _bars(closes)
    d = bars["date"].dt.strftime("%Y-%m-%d").tolist()
    rows = [
        {"event_id": "e1", "entry_opportunity_id": None, "event_status": "FORMING", "run_id": "R1", "as_of": d[18],
         "ticker": "T", "candidate_id": "c", "thesis_side": "BULL", "trigger_close_date": None, "timeframe": "1d"},
        {"event_id": "e1", "entry_opportunity_id": "o1", "event_status": "OBSERVED", "run_id": "R3", "as_of": d[22],
         "ticker": "T", "candidate_id": "c", "thesis_side": "BULL", "trigger_close_date": d[20], "timeframe": "1d"},
        {"event_id": "e1", "entry_opportunity_id": "o1", "event_status": "CONFIRMED", "run_id": "R4", "as_of": d[23],
         "ticker": "T", "candidate_id": "c", "thesis_side": "BULL", "trigger_close_date": d[20], "timeframe": "1d"},
    ]
    out = opportunity_cohort(rows, lambda ticker: bars)
    opp = [r for r in out if r["entry_opportunity_id"] == "o1"]
    assert len(opp) == 1 and len(out) == 2
    o = opp[0]
    assert o["first_seen_run"] == "R3" and o["first_seen_status"] == "OBSERVED" and o["latest_status"] == "CONFIRMED"
    assert o["status_path"] == "OBSERVED>CONFIRMED"
    assert o["recognition_lag_sessions"] == 2              # crossed at d[20], first seen on the d[22] bar
    assert o["views_status"] == "COMPLETE" and o["first_barrier"] == "FAVOURABLE"
    forming = [r for r in out if r["entry_opportunity_id"] is None][0]
    assert forming["views_status"] == "NO_CROSSING_YET"


def test_discovery_writes_the_cohort_file_and_never_fails_the_run(tmp_path):
    import avshunter_discovery_ULTIMATE as disc
    path = tmp_path / "led.sqlite"
    disc._beh001_record_ledger([{**_cand("OBSERVED"), "Signal_State": "DETECTED"}], {"T"}, "R1", path)
    closes = [100.0] * 20 + [103.0] + [104.0 + i for i in range(3)]
    bars = _bars(closes)
    out = tmp_path / "cohort.csv"
    status = disc._write_opportunity_cohort(path, out, bars_for=lambda t: bars.assign(
        date=pd.bdate_range("2026-08-14", periods=len(closes))))
    assert status.startswith("WRITTEN:1") and pd.read_csv(out)["event_id"].tolist() == ["e1"]
    assert disc._write_opportunity_cohort(tmp_path / "missing_dir" / "x" / "l.sqlite", tmp_path / "nope" / "c.csv",
                                          bars_for=lambda t: 1 / 0).startswith(("WRITTEN:0", "COHORT_ERROR"))
