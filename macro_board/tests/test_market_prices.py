"""Business rules for the board's own completed-session prices (ACK 9 Oct 2026).

The pipeline's price store stays the primary source and is never written. When it is behind the
last completed US session, or a ticker has a gap (RSP and UUP stopped on 20 Aug 2026), the board
fills those completed sessions from Polygon's grouped daily bars, kept in its own cache. A fill
never overwrites a value the store has; a session counts only after its close plus a settle
margin; an unavailable session is reported, never invented. No network.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from macro_board import market_prices as mp


def _frames(data: dict) -> dict:
    """{field: wide frame} from {ticker: {date: close}} (o/h/l/v derived for the test)."""
    closes = pd.DataFrame({t: pd.Series({pd.Timestamp(d): c for d, c in rows.items()}) for t, rows in data.items()}).sort_index()
    return {"open": closes - 1, "high": closes + 1, "low": closes - 2, "close": closes, "volume": closes * 0 + 100}


def test_the_last_eligible_session_waits_for_the_close_plus_the_settle_margin():
    before = datetime(2026, 10, 9, 20, 10, tzinfo=timezone.utc)      # 16:10 ET on 9 Oct
    after = datetime(2026, 10, 9, 22, 11, tzinfo=timezone.utc)       # 18:11 ET
    assert mp.last_eligible_session(before, settle_minutes=30) == date(2026, 10, 8)
    assert mp.last_eligible_session(after, settle_minutes=30) == date(2026, 10, 9)
    half_day = datetime(2026, 11, 27, 18, 45, tzinfo=timezone.utc)   # 13:45 ET after a 13:00 close
    assert mp.last_eligible_session(half_day, settle_minutes=30) == date(2026, 11, 27)


def test_the_plan_covers_the_sessions_the_store_lacks_up_to_the_last_completed_one():
    frames = _frames({"SPY": {"2026-10-06": 1.0, "2026-10-07": 1.0, "2026-10-08": 1.0},
                      "RSP": {"2026-08-19": 1.0, "2026-08-20": 1.0}})
    plan, too_long = mp.plan_fill(frames["close"], ["SPY", "RSP", "QQQ"], last_completed=date(2026, 10, 9), max_gap_sessions=60)
    assert plan[date(2026, 10, 9)] == ["RSP", "SPY"]                       # the store's latest session is missing
    assert plan[date(2026, 8, 21)] == ["RSP"] and plan[date(2026, 10, 8)] == ["RSP"]
    assert date(2026, 8, 20) not in plan and date(2026, 9, 7) not in plan  # held / Labor Day
    assert all("QQQ" not in v for v in plan.values())                     # never in the store: not filled here
    assert too_long == {}


def test_a_gap_longer_than_the_limit_is_left_whole_and_reported_never_part_filled():
    # 9 Oct 2026: 37 universe ETFs were last stored on 15 May; filling only the last 60 sessions
    # left a hole that averages, the 252-session range and the evidence would run across.
    frames = _frames({"UUP": {"2026-01-02": 1.0}, "SPY": {"2026-10-08": 1.0}})
    plan, too_long = mp.plan_fill(frames["close"], ["UUP", "SPY"], last_completed=date(2026, 10, 9), max_gap_sessions=5)
    assert plan == {date(2026, 10, 9): ["SPY"]}
    assert too_long == {"UUP": {"last_stored": "2026-01-02", "missing_sessions": 193}}   # XNYS sessions 3 Jan - 9 Oct


def test_filled_bars_never_overwrite_the_store_and_the_fill_is_reported():
    frames = _frames({"SPY": {"2026-10-07": 770.0, "2026-10-08": 773.93}, "RSP": {"2026-10-07": 211.0}})
    grouped = {date(2026, 10, 8): {"SPY": {"o": 1, "h": 1, "l": 1, "c": 999.0, "v": 1},
                                   "RSP": {"o": 211.5, "h": 212.4, "l": 210.9, "c": 211.87, "v": 1000}},
               date(2026, 10, 9): {"SPY": {"o": 774.0, "h": 779.0, "l": 773.0, "c": 778.57, "v": 5},
                                   "RSP": {"o": 212.0, "h": 213.2, "l": 211.9, "c": 213.04, "v": 6}}}
    plan = {date(2026, 10, 8): ["RSP"], date(2026, 10, 9): ["RSP", "SPY"]}
    out, report = mp.apply_fill(frames, grouped, plan)
    assert out["close"].loc["2026-10-08", "SPY"] == 773.93                 # the store's value, not 999
    assert out["close"].loc["2026-10-08", "RSP"] == 211.87
    assert out["close"].loc["2026-10-09", "SPY"] == 778.57 and out["high"].loc["2026-10-09", "SPY"] == 779.0
    assert report["filled"] == {"RSP": ["2026-10-08", "2026-10-09"], "SPY": ["2026-10-09"]}
    assert report["unavailable"] == {}


def test_a_session_polygon_cannot_supply_is_reported_unavailable_not_invented():
    frames = _frames({"SPY": {"2026-10-08": 773.93}})
    out, report = mp.apply_fill(frames, {date(2026, 10, 9): {}}, {date(2026, 10, 9): ["SPY"]})
    assert "2026-10-09" not in [str(d.date()) for d in out["close"]["SPY"].dropna().index]
    assert report["unavailable"] == {"SPY": ["2026-10-09"]}


def test_grouped_bars_are_cached_once_fetched_and_a_failure_is_not_cached(tmp_path):
    calls = []

    def ok(url, params):
        calls.append(url)
        return 200, {"status": "OK", "results": [{"T": "SPY", "o": 774.0, "h": 779.0, "l": 773.0, "c": 778.57, "v": 5}]}

    first = mp.fetch_grouped_daily(date(2026, 10, 9), cache_dir=tmp_path, transport=ok)
    again = mp.fetch_grouped_daily(date(2026, 10, 9), cache_dir=tmp_path, transport=lambda u, p: (500, {}))
    assert first["SPY"]["c"] == 778.57 and again == first and len(calls) == 1

    failing = mp.fetch_grouped_daily(date(2026, 10, 8), cache_dir=tmp_path, transport=lambda u, p: (403, {"status": "NOT_AUTHORIZED"}))
    assert failing is None and not (tmp_path / "grouped_2026-10-08.json").exists()


def test_extra_breadth_closes_are_added_without_replacing_the_store():
    panel = pd.DataFrame({"AAA": [1.0, 2.0], "BBB": [3.0, None]}, index=pd.to_datetime(["2026-10-07", "2026-10-08"]))
    grouped = {date(2026, 10, 8): {"BBB": {"c": 4.0}, "AAA": {"c": 99.0}}, date(2026, 10, 9): {"AAA": {"c": 2.5}, "CCC": {"c": 7.0}}}
    merged = mp.merge_breadth(panel, grouped)
    assert merged.loc["2026-10-08", "AAA"] == 2.0 and merged.loc["2026-10-08", "BBB"] == 4.0
    assert merged.loc["2026-10-09", "AAA"] == 2.5 and "CCC" not in merged.columns    # only the panel's own tickers


# -- latest price: pre-market / intraday / after-hours supersedes the close (ACK 9 Oct 2026) ------------

def test_the_trading_segment_of_a_quote_comes_from_the_exchange_calendar():
    assert mp.segment_of(datetime(2026, 10, 9, 12, 41, tzinfo=timezone.utc)) == "PREMARKET"     # 08:41 ET
    assert mp.segment_of(datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)) == "REGULAR"
    assert mp.segment_of(datetime(2026, 10, 9, 21, 55, tzinfo=timezone.utc)) == "AFTER_HOURS"
    assert mp.segment_of(datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc)) == "AFTER_HOURS"  # after a 13:00 close
    assert mp.segment_of(datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)) == "CLOSED"        # Saturday


def test_a_latest_price_after_the_boards_close_supersedes_it_and_an_older_one_does_not():
    snap = {"QQQ": {"price": 753.10, "time_utc": "2026-10-10T12:40:00Z"},     # pre-market, next session
            "SPY": {"price": 778.38, "time_utc": "2026-10-09T19:59:00Z"}}     # before the 9 Oct close
    closes = {"QQQ": (751.27, "2026-10-09"), "SPY": (778.57, "2026-10-09"), "IWM": (277.0, "2026-10-09")}
    rows = mp.latest_layer(snap, closes, now=datetime(2026, 10, 12, 12, 45, tzinfo=timezone.utc), stale_after_minutes=30)
    q = rows["QQQ"]
    assert q["supersedes_close"] is True and q["current"] == 753.10 and q["segment"] == "CLOSED"   # 10 Oct is Saturday
    assert round(q["change_vs_close_pct"], 4) == round((753.10 / 751.27 - 1) * 100, 4)
    assert q["stale"] is True and q["age_minutes"] == 2 * 24 * 60 + 5            # shown and flagged, still used
    s = rows["SPY"]
    assert s["supersedes_close"] is False and s["current"] == 778.57              # the close stands
    assert rows["IWM"]["supersedes_close"] is False and rows["IWM"]["current"] == 277.0 and rows["IWM"]["price"] is None


def test_the_snapshot_is_one_call_parsed_to_the_latest_minute_and_a_failure_is_stated(tmp_path):
    seen = []

    def ok(url, params):
        seen.append(params["tickers"])
        return 200, {"tickers": [{"ticker": "QQQ", "min": {"c": 751.31, "t": 1791581100000}, "day": {"c": 751.27},
                                  "prevDay": {"c": 747.58}},
                                 {"ticker": "UUP", "min": {}, "day": {"c": 29.02}, "updated": 1791576600000000000}]}
    out = mp.fetch_snapshot(["QQQ", "UUP"], transport=ok)
    assert seen == ["QQQ,UUP"]
    assert out["status"] == "OK" and out["rows"]["QQQ"]["price"] == 751.31
    assert out["rows"]["QQQ"]["time_utc"] == "2026-10-09T21:25:00Z"
    assert out["rows"]["UUP"]["price"] == 29.02                                   # no minute bar: day close, its update time
    failed = mp.fetch_snapshot(["QQQ"], transport=lambda u, p: (403, {"status": "NOT_AUTHORIZED"}))
    assert failed["status"] == "UNAVAILABLE" and failed["rows"] == {}
