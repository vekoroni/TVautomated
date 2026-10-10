"""Output-trust item 10, part 10.2 (C-1; ACK approved 9-10 Oct 2026): forward calibration state per setup.

Business rules:
- The outcome scorer records the setup, its stated rate and the planned hold with every prediction.
- Event: target before invalidation within the planned hold (a TARGET_FIRST resolved within the hold's sessions);
  outcomes still open inside the hold are pending, never counted as misses.
- The stated rate is measured within the setup's hold in bars; the forward check converts it to XNYS sessions. A
  hold longer than the scorer's window cannot be failed by a window TIMEOUT - it is BEYOND_SCORER_WINDOW, not a miss.
- Only matured outcomes count: the full hold (or the scorer window) has elapsed since the evidence session.
  Counting early terminal outcomes would favour fast resolutions (hits and stops land early; timeouts never do).
- Per setup: resolved n, distinct sessions, observed rate with Wilson interval against the mean stated rate.
  UNCALIBRATED_FORWARD until the governed minimum of resolved outcomes over a minimum of sessions; then CALIBRATED
  (stated rate inside the observed interval) or MISCALIBRATED. The card shows the state; it never claims calibration
  it does not have.
"""
from __future__ import annotations

from domain.forward_calibration import forward_calibration


def _row(setup="1d|SOS -> LPS continuation|ACTIVATED|BULL", stated=0.58, hold=10, state="TARGET_FIRST", sessions=4,
         session="2026-10-05", ticker="AAA", observed=None, elapsed=40):
    return {"setup": setup, "stated_rate": stated, "planned_hold_sessions": hold, "state": state,
            "sessions_to_resolution": sessions, "sessions_observed": observed if observed is not None else sessions,
            "evidence_session": session, "ticker": ticker, "sessions_elapsed": elapsed}


POLICY = {"min_resolved": 20, "min_sessions": 5, "scorer_window_sessions": 20,
          "sessions_per_bar": {"1d": 1, "1w": 5, "1mo": 21}}


def test_hits_count_only_within_the_hold_and_open_outcomes_are_pending():
    rows = [_row(), _row(sessions=12), _row(state="STOP_FIRST", sessions=3),
            _row(state="OPEN_CENSORED", sessions=None, observed=6, elapsed=6)]          # still inside the 10-session hold
    out = forward_calibration(rows, policy=POLICY)["setups"]["1d|SOS -> LPS continuation|ACTIVATED|BULL"]
    assert (out["resolved"], out["hits"], out["pending"]) == (3, 1, 1)
    assert out["state"] == "UNCALIBRATED_FORWARD"


def test_enough_outcomes_give_calibrated_or_miscalibrated():
    sessions = [f"2026-10-{d:02d}" for d in range(1, 11)]
    ok = [_row(state="TARGET_FIRST" if i % 5 < 3 else "STOP_FIRST", session=sessions[i % 10], ticker=f"T{i}")
          for i in range(60)]                                                # 60% observed vs 58% stated
    calibrated = forward_calibration(ok, policy=POLICY)["setups"]["1d|SOS -> LPS continuation|ACTIVATED|BULL"]
    assert calibrated["state"] == "CALIBRATED" and calibrated["sessions"] == 10
    bad = [_row(state="TARGET_FIRST" if i % 5 == 0 else "STOP_FIRST", session=sessions[i % 10], ticker=f"T{i}")
           for i in range(60)]                                               # 20% observed vs 58% stated
    assert forward_calibration(bad, policy=POLICY)["setups"]["1d|SOS -> LPS continuation|ACTIVATED|BULL"]["state"] \
        == "MISCALIBRATED"


def test_the_scorer_ingests_setup_stated_rate_and_hold():
    from avshunter.c12_outcome.adapters.books import LABEL_COLUMNS
    assert {"trade_lane_setup", "trade_lane", "planned_hold_sessions", "setup_rate_within_hold",
            "trade_lane_side", "setup_hold_bars"} <= set(LABEL_COLUMNS)


def test_a_hold_beyond_the_scorer_window_is_not_a_miss_and_bars_convert_to_sessions():
    from domain.forward_calibration import hold_sessions
    assert hold_sessions("1w|SOS -> LPS continuation|ACTIVATED", 3, POLICY) == 15
    assert hold_sessions("1d|SOS -> LPS continuation|ACTIVATED", 30, POLICY) == 30
    assert hold_sessions("1h|x|ACTIVATED", 3, POLICY) is None                 # untested timeframe: no forward check
    rows = [_row(hold=30, state="TIMEOUT", sessions=20, observed=20), _row(hold=30, state="TARGET_FIRST", sessions=18),
            _row(hold=10, state="TIMEOUT", sessions=20, observed=20), _row(state="DATA_GAP", sessions=None, observed=3)]
    out = forward_calibration(rows, policy=POLICY)["setups"]["1d|SOS -> LPS continuation|ACTIVATED|BULL"]
    assert (out["resolved"], out["hits"], out["beyond_scorer_window"], out["not_scorable"]) == (2, 1, 1, 1)


def test_the_store_reader_takes_first_issued_labels_and_latest_outcome(tmp_path):
    import json
    import sqlite3
    from domain.forward_calibration import load_forward_rows
    db = tmp_path / "o.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("create table prediction_records (prediction_id, ticker, evidence_session)")
        c.execute("create table prediction_sightings (prediction_id, labels_json, ingested_at_utc)")
        c.execute("create table underlying_outcomes (prediction_id, as_of_session, state, sessions_observed, resolution_session)")
        c.execute("insert into prediction_records values ('p1', 'AAA', '2026-10-01')")
        labels = {"trade_lane_setup": "1w|SOS -> LPS continuation|ACTIVATED", "trade_lane_side": "BULL",
                  "setup_rate_within_hold": 0.6, "setup_hold_bars": 2}
        c.execute("insert into prediction_sightings values ('p1', ?, '2026-10-01T22:00')", (json.dumps(labels),))
        c.execute("insert into prediction_sightings values ('p1', '{}', '2026-10-02T22:00')")
        c.execute("insert into underlying_outcomes values ('p1', '2026-10-02', 'OPEN_CENSORED', 1, NULL)")
        c.execute("insert into underlying_outcomes values ('p1', '2026-10-06', 'TARGET_FIRST', 3, 3)")
    [row] = load_forward_rows(db, policy=POLICY)
    assert (row["planned_hold_sessions"], row["state"], row["sessions_to_resolution"], row["side"]) == (10, "TARGET_FIRST", 3, "BULL")
    from domain.forward_calibration import forward_label
    report = forward_calibration([row], policy=POLICY)["setups"]["1w|SOS -> LPS continuation|ACTIVATED|BULL"]
    assert row["sessions_elapsed"] == 3                                    # 2 Oct, 3 Oct, 6 Oct: hold of 10 not matured
    assert forward_label(report, POLICY) == "forward: uncalibrated (n 0 of 20)"


def test_the_card_states_the_setup_forward_state_never_a_hard_coded_one(tmp_path, monkeypatch):
    import json
    import subprocess
    from pathlib import Path
    import domain.structure_behaviour.trade_lane as tl
    cand = {"Timeframe": "1d", "Signal_Type": "SOS -> LPS continuation", "Signal_State": "ACTIVATED", "Direction": "BULL"}
    monkeypatch.setattr(tl, "FORWARD_REPORT_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(tl, "_FORWARD", {})
    assert tl.setup_rate_fields(cand)["setup_forward_text"] == "forward: not measured (no forward report)"
    report = tmp_path / "forward.json"
    report.write_text(json.dumps({"policy": {"min_resolved": 100}, "setups": {
        "1d|SOS -> LPS continuation|ACTIVATED|BULL": {"state": "UNCALIBRATED_FORWARD", "resolved": 7}}}), encoding="utf-8")
    monkeypatch.setattr(tl, "FORWARD_REPORT_PATH", report)
    monkeypatch.setattr(tl, "_FORWARD", {})
    f = tl.setup_rate_fields(cand)
    assert (f["setup_forward_state"], f["setup_forward_text"]) == ("UNCALIBRATED_FORWARD", "forward: uncalibrated (n 7 of 100)")
    assert {"setup_forward_state", "setup_forward_text"} <= set(tl.TRADE_LANE_FIELDS)
    card = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "SMCI", "direction": "CALL", "trade_lane": "A", "trade_lane_setup": "1d|SOS -> LPS continuation|ACTIVATED",
           "trade_lane_hit_original": 0.726, "trade_lane_hit_holdout": 0.678, **f}
    js = (card + f"\nconst h = renderTradeCard({json.dumps(row)});"
          "console.log(JSON.stringify([h.includes('forward: uncalibrated (n 7 of 100)'), h.includes('forward: uncalibrated,')]));")
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.stdout.strip().splitlines()[-1] == "[true,false]", out.stderr


def test_the_scorecard_reads_the_forward_state_from_the_outcome_store(tmp_path):
    from domain.run_scorecard import build_scorecard
    card = build_scorecard(tmp_path / "run", run_id="R1", phase="evening", verify_root=tmp_path / "v",
                           outcome_store=tmp_path / "absent.sqlite")
    assert card["sections"]["calibration"]["facts"]["forward_state"] == "NOT_AVAILABLE"
    import sqlite3
    db = tmp_path / "o.sqlite"
    with sqlite3.connect(db) as c:
        c.execute("create table prediction_records (prediction_id, ticker, evidence_session)")
        c.execute("create table prediction_sightings (prediction_id, labels_json, ingested_at_utc)")
        c.execute("create table underlying_outcomes (prediction_id, as_of_session, state, sessions_observed, resolution_session)")
    facts = build_scorecard(tmp_path / "run", run_id="R1", phase="evening", verify_root=tmp_path / "v",
                            outcome_store=db)["sections"]["calibration"]["facts"]
    assert (facts["forward_state"], facts["forward_setups"], facts["forward_resolved"]) == ("UNCALIBRATED_FORWARD", 0, 0)


def test_only_matured_outcomes_count_so_fast_resolutions_do_not_bias_the_rate():
    rows = [_row(sessions=2, elapsed=3), _row(state="STOP_FIRST", sessions=1, elapsed=3), _row(sessions=2, elapsed=10),
            _row(hold=30, state="TARGET_FIRST", sessions=5, elapsed=20)]       # hold beyond window: matures at 20
    out = forward_calibration(rows, policy=POLICY)["setups"]["1d|SOS -> LPS continuation|ACTIVATED|BULL"]
    assert (out["resolved"], out["hits"], out["pending"]) == (2, 2, 2)
