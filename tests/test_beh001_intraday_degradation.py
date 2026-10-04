"""BEH-001 ACK amendment: missing intraday data never fails a ticker or run.

- The completed-intraday index reports NO_INTRADAY_DATA / STALE_INTRADAY /
  INCOMPLETE_SESSIONS / READ_ERROR instead of raising.
- The engine still produces the daily reading and handoff; each missing
  timeframe is NOT_EVALUATED with its reason; daily candidates are warned that
  lower-timeframe confirmation was unavailable.
"""
import copy
from datetime import date

import numpy as np
import pandas as pd

from canonical_data.intraday_bars import CompletedIntradayIndex
from domain.structure_behaviour.engine import analyse_ticker
from domain.structure_behaviour.policy import load_policy
from test_beh001_sequences import TREND_DOWN, zigzag_bars

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20


def five_minute_session(day: str, start_price: float = 100.0, drift: float = -0.0005):
    stamps = pd.date_range(f"{day} 13:30", periods=78, freq="5min", tz="UTC")
    close = start_price * np.exp(np.cumsum(np.full(78, drift) + 0.002 * np.sin(np.arange(78) / 3)))
    open_ = np.concatenate([[start_price], close[:-1]])
    return pd.DataFrame({"timestamp_utc": stamps, "open": open_, "close": close,
                         "high": np.maximum(open_, close) * 1.001, "low": np.minimum(open_, close) * 0.999,
                         "volume": 10_000.0})


def entry(ticker, day, status="COMPLETE", frame=None):
    return {"ticker": ticker, "session_date": date.fromisoformat(day), "completeness": status,
            "interval": "5min", "segment": "REGULAR", "as_of": f"{day}T21:00:00+00:00", "frame": frame}


def index_of(entries, reader=None):
    return CompletedIntradayIndex(entries, reader=reader or (lambda e: e["frame"]))


def test_no_records_is_no_intraday_data():
    frame, status = index_of([]).bars_for("ABC", through_session="2026-09-29", sessions=4)
    assert frame is None and status == "NO_INTRADAY_DATA"


def test_latest_session_before_the_cut_is_flagged_stale_not_dropped():
    idx = index_of([entry("ABC", "2026-09-25", frame=five_minute_session("2026-09-25"))])
    frame, status = idx.bars_for("ABC", through_session="2026-09-29", sessions=4)
    assert frame is not None and status == "STALE_INTRADAY"


def test_partial_sessions_are_excluded_and_reported():
    idx = index_of([entry("ABC", "2026-09-28", status="PARTIAL", frame=five_minute_session("2026-09-28")),
                    entry("ABC", "2026-09-29", frame=five_minute_session("2026-09-29"))])
    frame, status = idx.bars_for("ABC", through_session="2026-09-29", sessions=4,
                                 expected_sessions=["2026-09-28", "2026-09-29"])
    assert status == "INCOMPLETE_SESSIONS"
    assert frame is not None and len(frame) == 78


def test_unreadable_payload_is_reported_never_raised():
    def broken(_):
        raise ValueError("intraday-bar integrity failure")
    idx = index_of([entry("ABC", "2026-09-29", frame=None)], reader=broken)
    frame, status = idx.bars_for("ABC", through_session="2026-09-29", sessions=4)
    assert frame is None and status == "READ_ERROR"


def test_engine_keeps_daily_reading_and_handoff_without_intraday():
    result = analyse_ticker("ABC", zigzag_bars(TREND_DOWN), None, POLICY, intraday_status="NO_INTRADAY_DATA")
    readings = result["readings"]
    assert readings["1d"]["Status"] == "EVALUATED"
    for tf in ("60m", "15m", "5m"):
        assert readings[tf]["Status"] == "NOT_EVALUATED_NO_INTRADAY_DATA"
        assert readings[tf]["candidates"] == []
    assert result["handoff"]["thesis__side"] in {"BULL", "BEAR", "UNASSIGNED"}
    for c in readings["1d"]["candidates"]:
        assert "LOWER_TIMEFRAME_CONFIRMATION_UNAVAILABLE" in c["Warning"]


def test_engine_uses_intraday_when_present_and_survives_bad_intraday():
    sessions = pd.concat([five_minute_session(d, 100 - i) for i, d in enumerate(
        ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29"])])
    ok = analyse_ticker("ABC", zigzag_bars(TREND_DOWN), sessions, POLICY)
    assert ok["readings"]["5m"]["Status"] in {"EVALUATED", "NOT_EVALUATED_INSUFFICIENT_BARS", "NOT_EVALUATED_NO_SWINGS"}
    garbage = sessions.copy()
    garbage["high"] = garbage["low"] * 0.5      # invalid bars
    bad = analyse_ticker("ABC", zigzag_bars(TREND_DOWN), garbage, POLICY)
    assert bad["readings"]["1d"]["Status"] == "EVALUATED"
    assert bad["readings"]["5m"]["Status"].startswith("NOT_EVALUATED")


def test_resampling_builds_session_anchored_bars_without_crossing_sessions():
    from domain.structure_behaviour.engine import resample_intraday
    two = pd.concat([five_minute_session("2026-09-28"), five_minute_session("2026-09-29", 99)])
    hourly = resample_intraday(two, 60)
    assert len(hourly) == 2 * 7                      # 09:30..15:30 buckets per session
    assert hourly["timestamp"].dt.strftime("%H:%M").iloc[0] == "09:30"
    first = two.iloc[:12]
    assert hourly["high"].iloc[0] == first["high"].max() and hourly["volume"].iloc[0] == first["volume"].sum()


def test_intraday_data_status_is_a_field_on_every_candidate_not_only_warning_text():
    """Evening 1 Oct: intraday bars two sessions behind were flagged only inside the
    free-text Warning. Fresh-or-flagged (R12) needs a field downstream can read."""
    import copy
    from domain.structure_behaviour.engine import analyse_ticker
    from domain.structure_behaviour.policy import load_policy
    from test_beh001_sequences import TREND_DOWN, zigzag_bars
    policy = copy.deepcopy(dict(load_policy()))
    policy["timeframes"]["1d"]["min_bars"] = 20
    out = analyse_ticker("TEST", zigzag_bars(TREND_DOWN), None, policy, intraday_status="STALE_INTRADAY")
    assert out["candidates"]
    assert all(c["Data_Status"] == "OK" for c in out["candidates"] if c["Timeframe"] in {"1d", "1w", "1mo"})
