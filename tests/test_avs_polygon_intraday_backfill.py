"""Polygon intraday backfill (ACK 4 Oct 2026, step 4 option b).

Only 18 sessions of 5-minute bars exist (4 Sep - 2 Oct 2026); intraday BEH-001 evidence needs an original and a
held-out history like the daily panels. Polygon supplies stock bars (options stay MarketData-only).
Business rules:
- Bars are stored in the existing canonical intraday store through its resolver (no new store), as completed
  regular sessions only: extended-hours bars never enter.
- Sessions already stored are never fetched again (resumable; idempotent).
- A plan-only mode makes no provider call and writes nothing.
"""
from datetime import date, datetime, timezone

import pandas as pd

from scripts import backfill_polygon_intraday as bf


def _bars(day, times):
    return pd.DataFrame({"t": [int(datetime.fromisoformat(f"{day}T{h}:00+00:00").timestamp() * 1000) for h in times],
                         "o": 10.0, "h": 10.5, "l": 9.5, "c": 10.2, "v": 1000, "vw": 10.1, "n": 12})


def test_bars_are_split_into_regular_sessions_only():
    # 2026-09-01: regular session 13:30-20:00 UTC (EDT). 12:00 is premarket, 20:30 after hours.
    raw = _bars("2026-09-01", ["12:00", "13:30", "13:35", "19:55", "20:30"])
    sessions = bf.split_regular_sessions(raw)
    assert list(sessions) == [date(2026, 9, 1)]
    frame = sessions[date(2026, 9, 1)]
    assert list(frame["timestamp_utc"].dt.strftime("%H:%M")) == ["13:30", "13:35", "19:55"]
    assert {"open", "high", "low", "close", "volume"} <= set(frame.columns)


def test_weekend_bars_never_form_a_session():
    assert bf.split_regular_sessions(_bars("2026-09-05", ["14:00"])) == {}


def test_sessions_already_stored_are_not_fetched_again():
    wanted = [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3)]
    assert bf.missing_sessions(wanted, stored={date(2026, 9, 2)}) == [date(2026, 9, 1), date(2026, 9, 3)]
    assert bf.missing_sessions(wanted, stored=set(wanted)) == []


def test_plan_estimates_without_calling_the_provider():
    plan = bf.estimate_plan(tickers=["AAA", "BBB"], sessions=[date(2026, 9, 1), date(2026, 9, 2)],
                            stored={"AAA": {date(2026, 9, 1)}})
    assert plan["tickers"] == 2 and plan["sessions_wanted"] == 4 and plan["sessions_already_stored"] == 1
    assert plan["sessions_to_fetch"] == 3 and plan["tickers_needing_fetch"] == 2
    assert plan["provider_requests_estimate"] >= 2


def test_trading_sessions_follow_the_exchange_calendar():
    days = bf.xnys_sessions(date(2026, 9, 4), date(2026, 9, 8))      # Fri, (Sat, Sun), Mon Labor Day, Tue
    assert days == [date(2026, 9, 4), date(2026, 9, 8)]


def test_backfill_writes_canonical_sessions_end_to_end(tmp_path, monkeypatch):
    # Pilot 4 Oct 2026 failed with "FOREIGN KEY constraint failed": the lifecycle needs the run registered first.
    import json
    from argparse import Namespace
    from canonical_data import CanonicalRegistry, DatasetType
    monkeypatch.setattr(bf, "REGISTRY", tmp_path / "control_plane.sqlite")
    monkeypatch.setattr(bf, "PAYLOADS", tmp_path / "payloads")
    monkeypatch.setattr(bf, "ROOT", tmp_path)
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    # 2026-09-01 regular session 13:30-20:00 UTC: 78 five-minute bars.
    times = pd.date_range("2026-09-01T13:30:00Z", "2026-09-01T19:55:00Z", freq="5min")
    raw = pd.DataFrame({"t": (times.astype("int64") // 10**6), "o": 10.0, "h": 10.5, "l": 9.5, "c": 10.2, "v": 1000})
    monkeypatch.setattr(bf, "fetch_polygon", lambda ticker, start, end, key: raw.copy())
    args = Namespace(tickers="AAA", universe=None, include_scanner=False, start=date(2026, 9, 1),
                     end=date(2026, 9, 1), workers=1, plan_only=False)
    counts = bf.run(args)
    assert counts["ticker_errors"] == 0 and counts["sessions_written"] == 1
    records = CanonicalRegistry(tmp_path / "control_plane.sqlite").list_dataset_records(DatasetType.INTRADAY_BAR)
    assert len(records) == 1 and records[0].provider == "POLYGON" and records[0].completeness_status.value == "COMPLETE"
    again = bf.run(args)                                   # resumable: nothing fetched or written twice
    assert again["sessions_written"] == 0 and again["tickers_done"] == 0


def test_resume_counts_partial_sessions_and_fetched_tickers_as_done(tmp_path, monkeypatch):
    # 5 Oct 2026: 1,785 of 2,242 fetched tickers had PARTIAL sessions (thin names: bars with no trades); the resume
    # counted only COMPLETE sessions, so it re-fetched every one of them.
    from argparse import Namespace
    monkeypatch.setattr(bf, "REGISTRY", tmp_path / "control_plane.sqlite")
    monkeypatch.setattr(bf, "PAYLOADS", tmp_path / "payloads")
    monkeypatch.setattr(bf, "ROOT", tmp_path)
    monkeypatch.setenv("POLYGON_API_KEY", "test-key")
    times = pd.date_range("2026-09-01T13:30:00Z", "2026-09-01T19:55:00Z", freq="5min")[::2]   # half the bars: PARTIAL
    raw = pd.DataFrame({"t": (times.astype("int64") // 10**6), "o": 10.0, "h": 10.5, "l": 9.5, "c": 10.2, "v": 1000})
    calls = []
    monkeypatch.setattr(bf, "fetch_polygon", lambda ticker, start, end, key: calls.append(ticker) or raw.copy())
    args = Namespace(tickers="AAA", universe=None, include_scanner=False, start=date(2026, 9, 1),
                     end=date(2026, 9, 2), workers=1, plan_only=False, shard=None)   # 2 Sep: no bars returned
    first = bf.run(args)
    assert first["sessions_written"] == 1 and first["sessions_no_bars"] == 1 and calls == ["AAA"]
    again = bf.run(args)
    assert again["tickers_done"] == 0 and calls == ["AAA"]          # nothing fetched twice


def test_shards_split_tickers_without_overlap():
    tickers = [f"T{i:03d}" for i in range(10)]
    parts = [bf.shard_tickers(tickers, f"{k}/3") for k in (1, 2, 3)]
    assert sorted(sum(parts, [])) == tickers and all(parts)
    assert bf.shard_tickers(tickers, None) == tickers
