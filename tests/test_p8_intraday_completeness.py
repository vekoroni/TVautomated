"""Step 1 of the behavioural-stage design (ACK approved F1-F6, 12 Oct 2026): intraday data completeness and accuracy.

Root causes (Enhancements/phase8/INTRADAY_COMPLETENESS_ROOT_CAUSE_20261012.md):
- RC-I3 / RC-I6: a session is stored in pieces (a 09:30-10:15 morning window, a 10:05-15:55 evening fetch of the rest)
  and the index kept one record, so Discovery read a 10:15 snapshot or a day missing its first 35 minutes as "complete";
- RC-I4: a thin name's full-day session (no trades in some bars) was rejected;
- RC-I1: sessions with no Evening after them were never captured; the catch-up fills every missing session in the
  reading window before Discovery;
- RC-I2: "no data" from the provider for a ticker that traded was recorded as TICKER_INACTIVE;
- F5: every session served to the reading reconciles to the daily bar within a governed tolerance.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from canonical_data.intraday_bars import (SESSION_COMPLETE, SESSION_COMPLETE_SPARSE, WINDOW_ONLY,
                                          CompletedIntradayIndex, reconcile_with_daily, requested_covers_session)
from canonical_data.session_clock import session_bounds

DAY = date(2026, 10, 9)
PRIOR = date(2026, 10, 8)


def _bars(day, start_minute=0, end_minute=385, skip=(), close=10.0):
    open_utc, _ = session_bounds(day)
    rows = []
    for m in range(start_minute, end_minute + 1, 5):
        if m in skip:
            continue
        ts = open_utc + timedelta(minutes=m)
        rows.append({"timestamp_utc": ts, "open": close, "high": close + 0.1, "low": close - 0.1, "close": close,
                     "volume": 100.0, "acquired_at_utc": open_utc + timedelta(hours=8)})
    return pd.DataFrame(rows)


def _entry(day, start_minute, end_minute, frame, completeness="COMPLETE", state="COMPLETED_SESSION", ticker="AAA"):
    open_utc, _ = session_bounds(day)
    return {"ticker": ticker, "session_date": day, "completeness": completeness, "interval": "5min",
            "segment": "REGULAR", "as_of": str(open_utc + timedelta(minutes=end_minute)),
            "start_utc": (open_utc + timedelta(minutes=start_minute)).isoformat(),
            "end_utc": (open_utc + timedelta(minutes=end_minute)).isoformat(), "evidence_state": state,
            "record": frame}


def _index(entries):
    return CompletedIntradayIndex(entries, reader=lambda e: e["record"])


def test_a_session_stored_in_pieces_is_served_whole():
    morning = _bars(DAY, 0, 45)                                   # 09:30-10:15, captured by the Morning run
    evening = _bars(DAY, 35, 385)                                 # 10:05-15:55, the Evening fetched the rest
    idx = _index([_entry(DAY, 0, 45, morning, state="DEVELOPING_SESSION"), _entry(DAY, 35, 385, evening)])
    bars, status = idx.bars_for("AAA", through_session=DAY.isoformat(), sessions=1)
    ts = pd.to_datetime(bars["timestamp_utc"], utc=True)
    assert status == "OK" and len(bars) == 78
    assert ts.min() == session_bounds(DAY)[0] and ts.max() == session_bounds(DAY)[1] - timedelta(minutes=5)
    assert idx.coverage("AAA", DAY.isoformat()) == SESSION_COMPLETE


def test_a_morning_snapshot_is_never_served_as_the_completed_session():
    idx = _index([_entry(PRIOR, 0, 385, _bars(PRIOR)),
                  _entry(DAY, 0, 45, _bars(DAY, 0, 45), state="DEVELOPING_SESSION")])
    bars, status = idx.bars_for("AAA", through_session=DAY.isoformat(), sessions=1)
    assert status == "STALE_INTRADAY"                            # the newest full session is the prior day
    assert set(pd.to_datetime(bars["timestamp_utc"], utc=True).dt.tz_convert("America/New_York").dt.date) == {PRIOR}
    assert idx.coverage("AAA", DAY.isoformat()) == WINDOW_ONLY


def test_a_thin_names_full_day_with_no_trade_intervals_is_usable_and_labelled():
    sparse = _bars(DAY, skip=(50, 55, 120, 200))
    idx = _index([_entry(DAY, 0, 385, sparse, completeness="PARTIAL")])
    bars, status = idx.bars_for("AAA", through_session=DAY.isoformat(), sessions=1)
    assert status == "OK" and len(bars) == 74
    assert idx.coverage("AAA", DAY.isoformat()) == SESSION_COMPLETE_SPARSE


def test_requested_windows_decide_whether_a_session_is_covered():
    assert requested_covers_session([_entry(DAY, 0, 45, None), _entry(DAY, 35, 385, None)], DAY)
    assert not requested_covers_session([_entry(DAY, 0, 45, None)], DAY)
    assert not requested_covers_session([_entry(DAY, 10, 385, None)], DAY)


def test_each_served_session_reconciles_to_the_daily_bar():
    bars = pd.concat([_bars(PRIOR, close=10.0), _bars(DAY, close=10.0)], ignore_index=True)
    daily = pd.DataFrame({"date": pd.to_datetime([PRIOR, DAY]), "open": [10.0, 10.0], "high": [10.1, 10.1],
                          "low": [9.9, 9.9], "close": [10.0, 10.5], "volume": [1e6, 1e6]})
    out = reconcile_with_daily(bars, daily, tolerance=0.005)
    assert [d["session"] for d in out] == [DAY.isoformat()]
    assert out[0]["fields"] == ["close"]


def test_discovery_flags_a_reading_whose_intraday_disagrees_with_the_daily_bar():
    import avshunter_discovery_ULTIMATE as disc
    src = inspect.getsource(disc._beh001_reading)
    assert "reconcile_with_daily(" in src and "INTRADAY_DISAGREES_WITH_DAILY" in src


def test_the_catch_up_lists_every_missing_session_of_a_traded_ticker_in_the_window():
    from scripts.intraday_catchup import gap_sessions
    stored = {"AAA": {PRIOR: [_entry(PRIOR, 0, 385, None)], DAY: [_entry(DAY, 0, 45, None)]}}
    traded = {("AAA", PRIOR): True, ("AAA", DAY): True, ("BBB", DAY): True, ("CCC", DAY): False}
    gaps = gap_sessions(["AAA", "BBB", "CCC"], [PRIOR, DAY], stored=stored, traded=traded)
    assert gaps == {"AAA": [DAY], "BBB": [DAY]}                # CCC did not trade: nothing to fetch


def test_the_catch_up_runs_before_discovery_in_the_evening():
    import intelligent_orchestrator as orch
    src = inspect.getsource(orch.evening_workflow)
    assert "run_intraday_catchup(" in src
    assert src.index("run_intraday_catchup(") < src.index("run_discovery(")


def test_no_data_for_a_ticker_that_traded_is_not_called_inactive():
    src = open("scripts/build_completed_market_profiles.py", encoding="utf-8").read()
    assert "PROVIDER_NO_DATA_TICKER_TRADED" in src and "_traded_on(" in src


def test_tolerance_and_window_are_governed():
    import json
    cfg = json.load(open("config/governed_constants_v1.json", encoding="utf-8"))["intraday_completeness"]
    assert cfg["reconciliation_tolerance"] == 0.005 and cfg["catchup_sessions"] == 20


def test_the_catch_up_is_authorised_to_store_what_it_fetches(tmp_path):
    """Live 12 Oct: every ticker was fetched then refused (STAGE_MISMATCH) - the catch-up registered tickers under the
    backfill's stage and wrote under its own. A ticker it registers must be authorised for its own writes."""
    from canonical_data import CanonicalRegistry, DatasetType
    from canonical_data.lifecycle import LifecycleManager
    from scripts.intraday_catchup import STAGE, _register_ticker, catchup_run_id
    registry = CanonicalRegistry(tmp_path / "cp.sqlite"); registry.initialise()
    run_id = catchup_run_id(DAY)
    registry.register_run(run_id, STAGE, DAY, metadata={})
    lifecycle = LifecycleManager(registry)
    _register_ticker(lifecycle, run_id, "AAA")
    assert lifecycle.authorise(run_id, STAGE, "AAA", DatasetType.INTRADAY_BAR).authorised
    assert run_id.startswith("intraday_catchup_20261009_")    # each invocation has its own time-stamped run id


def test_a_session_one_record_covers_is_read_once():
    """Replay 12 Oct: reading every stored piece of every session took 87 minutes for 2,936 tickers. When one record
    already covers the whole session, only that record is read; pieces are merged only when none does."""
    reads = []
    full = _entry(DAY, 0, 385, _bars(DAY))
    entries = [_entry(DAY, 0, 45, _bars(DAY, 0, 45), state="DEVELOPING_SESSION"), _entry(DAY, 35, 385, _bars(DAY, 35, 385)), full]
    idx = CompletedIntradayIndex(entries, reader=lambda e: (reads.append((e["start_utc"], e["end_utc"])), e["record"])[1])
    bars, status = idx.bars_for("AAA", through_session=DAY.isoformat(), sessions=1)
    assert status == "OK" and len(bars) == 78 and reads == [(full["start_utc"], full["end_utc"])]


def test_calibrated_reconciliation_separates_data_errors_from_the_closing_auction():
    """Calibration (12 Oct, 4,680 sessions): high / low agree with the daily bar on 99% of sessions (a miss is a data
    error, 0.5%); the close is the closing-auction print and differs by design (99th percentile ~1%, so 1.0%).
    Only the trigger-and-response window (last 4 sessions) flags the reading."""
    bars = _bars(DAY, close=10.0)
    near = pd.DataFrame({"date": pd.to_datetime([DAY]), "open": [10.0], "high": [10.1], "low": [9.9], "close": [10.08],
                         "volume": [1e6]})                   # close 0.8% away: auction difference, not an error
    assert reconcile_with_daily(bars, near, high_low_tolerance=0.005, close_tolerance=0.01) == []
    wrong_high = near.assign(high=[10.2])                    # high 1% away: a data error
    assert reconcile_with_daily(bars, wrong_high, high_low_tolerance=0.005, close_tolerance=0.01)[0]["fields"] == ["high"]
    import json
    cfg = json.load(open("config/governed_constants_v1.json", encoding="utf-8"))["intraday_completeness"]
    assert (cfg["high_low_tolerance"], cfg["close_tolerance"], cfg["reconciliation_window_sessions"]) == (0.005, 0.01, 4)
    import inspect
    import avshunter_discovery_ULTIMATE as disc
    assert "reconciliation_window_sessions" in inspect.getsource(disc)
