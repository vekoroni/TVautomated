"""Business rules for the governed writer of the board universe into the price store (ACK 20 Nov 2026, option B).

Root cause (STALE_UNIVERSE_PRICES_root_cause_2026-11-20.md): 37 universe ETFs had no store writer after 15 May 2026
and RSP/UUP after 20 Aug, so as-of builds read them as STALE and their reads as MISSING. The daily step writes the
completed sessions the store lacks, never revises a stored value, and leaves a long gap whole for the one-time
backfill. A listed split re-fetches the ticker's adjusted history; an unexplained jump is held, never written.
The backfill fetches once (dry run), and an execute writes exactly what was reviewed. No network: a fake transport.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import sqlite3

import pandas as pd
import pytest

from canonical_data.historical_prices import HistoricalPriceDatabase
from macro_board import store_writer as sw

CFG = {"max_daily_gap_sessions": 3, "jump_hold_ratio": 1.45, "seam_tolerance": 0.005, "settle_minutes": 30,
       "history_start": "2026-11-02"}
NOW = datetime(2026, 11, 20, 22, 30, tzinfo=timezone.utc)          # 17:30 ET Friday 20 Nov: 20 Nov is complete


def _bar(c, v=1000.0):
    return {"date": None, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": v}


def _db(tmp_path, data: dict) -> HistoricalPriceDatabase:
    db = HistoricalPriceDatabase(tmp_path / "prices.sqlite")
    db.initialise()
    for ticker, rows in data.items():
        db.ingest(ticker, [{**_bar(c), "date": d} for d, c in rows.items()], provider="POLYGON",
                  source_kind="TEST_SEED", fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    return db


def _rows(db, ticker):
    with sqlite3.connect(db.database_path) as c:
        return {d: (cl, sk) for d, cl, sk in c.execute(
            "SELECT trading_date, close, source_kind FROM ohlcv_daily WHERE ticker=? ORDER BY trading_date", [ticker])}


def _aggs(rows: dict) -> dict:
    """Polygon daily aggregates: t is midnight New York in UTC milliseconds."""
    out = []
    for d, c in rows.items():
        t = pd.Timestamp(d).tz_localize("America/New_York").tz_convert("UTC")
        out.append({"t": int(t.value // 1_000_000), "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 500.0})
    return {"status": "OK", "results": out}


class FakePolygon:
    def __init__(self, *, splits=(), aggs=None, splits_status=200):
        self.splits, self.aggs, self.splits_status, self.calls = list(splits), aggs or {}, splits_status, []

    def __call__(self, url, params):
        self.calls.append(url)
        if "/v3/reference/splits" in url:
            return self.splits_status, ({"results": self.splits} if self.splits_status == 200 else {})
        if "/v2/aggs/ticker/" in url:
            ticker = url.split("/v2/aggs/ticker/")[1].split("/")[0]
            return (200, _aggs(self.aggs[ticker])) if ticker in self.aggs else (404, {})
        raise AssertionError(url)


def _grouped(sessions: dict):
    """{date: {ticker: close}} -> fetcher in the board's grouped bar shape."""
    def fetch(day):
        bars = sessions.get(day.isoformat())
        return None if bars is None else {t: {"o": c, "h": c + 1, "l": c - 1, "c": c, "v": 900.0} for t, c in bars.items()}
    return fetch


# --- plan ------------------------------------------------------------------------------------------------------

def test_the_daily_plan_writes_short_gaps_and_leaves_long_gaps_whole_for_the_backfill():
    state = {"SPY": {"last": date(2026, 11, 20), "rows": 500, "last_close": 1.0},
             "IJR": {"last": date(2026, 11, 18), "rows": 500, "last_close": 1.0},
             "UUP": {"last": date(2026, 8, 20), "rows": 500, "last_close": 1.0},
             "NEW": {"last": None, "rows": 0, "last_close": None}}
    plan = sw.plan_daily(state, last_completed=date(2026, 11, 20), max_gap_sessions=3)
    assert plan["SPY"] == {"action": "UP_TO_DATE", "sessions": []}
    assert plan["IJR"] == {"action": "GROUPED", "sessions": [date(2026, 11, 19), date(2026, 11, 20)]}
    assert plan["UUP"]["action"] == "GAP_TOO_LONG" and plan["UUP"]["sessions"] == []   # never part-filled
    assert plan["UUP"]["missing_sessions"] > 3
    assert plan["NEW"] == {"action": "NEVER_STORED", "sessions": []}


def test_polygon_daily_aggregates_land_on_their_new_york_session_date():
    rows = sw.aggs_to_rows(_aggs({"2026-03-06": 10.0, "2026-03-09": 11.0})["results"])   # either side of the DST change
    assert [r["date"] for r in rows] == ["2026-03-06", "2026-03-09"]
    assert rows[1]["close"] == 11.0 and rows[1]["volume"] == 500.0


# --- daily step ----------------------------------------------------------------------------------------------

def test_the_daily_step_inserts_only_the_sessions_the_store_lacks(tmp_path):
    db = _db(tmp_path, {"IJR": {"2026-11-17": 100.0, "2026-11-18": 101.0}, "SPY": {"2026-11-20": 600.0}})
    fake = FakePolygon()
    receipt = sw.run_daily(db, ["IJR", "SPY"], now=NOW, cfg=CFG, transport=fake,
                           grouped_fetch=_grouped({"2026-11-19": {"IJR": 102.0, "SPY": 1.0},
                                                   "2026-11-20": {"IJR": 103.0, "SPY": 2.0}}))
    rows = _rows(db, "IJR")
    assert rows["2026-11-19"] == (102.0, "BOARD_UNIVERSE_DAILY") and rows["2026-11-20"][0] == 103.0
    assert rows["2026-11-18"] == (101.0, "TEST_SEED")
    assert _rows(db, "SPY") == {"2026-11-20": (600.0, "TEST_SEED")}       # a stored value is never revised
    assert receipt["tickers"]["IJR"]["status"] == "WRITTEN" and receipt["tickers"]["IJR"]["inserted"] == 2
    assert receipt["tickers"]["SPY"]["status"] == "UP_TO_DATE"
    assert receipt["exit_code"] == 0
    assert sum("/v3/reference/splits" in u for u in fake.calls) == 1        # one splits call covers the window


def test_a_listed_split_refetches_the_tickers_adjusted_history_and_records_the_old_rows_as_revisions(tmp_path):
    # 19 Nov 2026: BITO doubled on the board's grouped bars (a likely 1-for-2 reverse split).
    db = _db(tmp_path, {"BITO": {"2026-11-17": 8.2, "2026-11-18": 8.31}})
    fake = FakePolygon(splits=[{"ticker": "BITO", "execution_date": "2026-11-19", "split_from": 2, "split_to": 1}],
                       aggs={"BITO": {"2026-11-17": 16.4, "2026-11-18": 16.62, "2026-11-19": 16.48, "2026-11-20": 16.6}})
    receipt = sw.run_daily(db, ["BITO"], now=NOW, cfg=CFG, transport=fake,
                           grouped_fetch=_grouped({"2026-11-19": {"BITO": 16.48}, "2026-11-20": {"BITO": 16.6}}))
    rows = _rows(db, "BITO")
    assert rows["2026-11-18"][0] == 16.62 and rows["2026-11-20"][0] == 16.6
    assert {sk for _, sk in rows.values()} == {"BOARD_UNIVERSE_SPLIT_REFETCH"}
    assert receipt["tickers"]["BITO"]["status"] == "SPLIT_REFETCHED"
    assert receipt["tickers"]["BITO"]["revised"] == 2
    assert db.revision_count("BITO") == 2


def test_an_unexplained_jump_is_held_and_never_written(tmp_path):
    db = _db(tmp_path, {"BITO": {"2026-11-18": 8.31}, "IJR": {"2026-11-18": 100.0}})
    receipt = sw.run_daily(db, ["BITO", "IJR"], now=NOW, cfg=CFG, transport=FakePolygon(),
                           grouped_fetch=_grouped({"2026-11-19": {"BITO": 16.48, "IJR": 101.0},
                                                   "2026-11-20": {"BITO": 16.6, "IJR": 102.0}}))
    assert set(_rows(db, "BITO")) == {"2026-11-18"}
    assert receipt["tickers"]["BITO"]["status"] == "HELD" and receipt["tickers"]["BITO"]["reason"] == "UNEXPLAINED_JUMP"
    assert receipt["tickers"]["IJR"]["status"] == "WRITTEN"
    assert receipt["exit_code"] == 2


def test_without_the_split_check_nothing_is_written(tmp_path):
    db = _db(tmp_path, {"IJR": {"2026-11-18": 100.0}})
    receipt = sw.run_daily(db, ["IJR"], now=NOW, cfg=CFG, transport=FakePolygon(splits_status=500),
                           grouped_fetch=_grouped({"2026-11-19": {"IJR": 101.0}, "2026-11-20": {"IJR": 102.0}}))
    assert set(_rows(db, "IJR")) == {"2026-11-18"}
    assert receipt["tickers"]["IJR"] == {"status": "HELD", "reason": "SPLIT_CHECK_UNAVAILABLE",
                                         "sessions": ["2026-11-19", "2026-11-20"]}
    assert receipt["exit_code"] == 2


def test_a_missing_grouped_session_holds_the_whole_gap(tmp_path):
    db = _db(tmp_path, {"IJR": {"2026-11-18": 100.0}})
    receipt = sw.run_daily(db, ["IJR"], now=NOW, cfg=CFG, transport=FakePolygon(),
                           grouped_fetch=_grouped({"2026-11-20": {"IJR": 102.0}}))
    assert set(_rows(db, "IJR")) == {"2026-11-18"}                            # 20 Nov is not written over a hole
    assert receipt["tickers"]["IJR"]["reason"] == "GROUPED_UNAVAILABLE"
    assert receipt["tickers"]["IJR"]["unavailable"] == ["2026-11-19"]


def test_long_gaps_are_reported_for_the_backfill_and_cost_no_call(tmp_path):
    db = _db(tmp_path, {"UUP": {"2026-11-02": 27.0}})
    fake = FakePolygon()
    receipt = sw.run_daily(db, ["UUP", "GONE"], now=NOW, cfg=CFG, transport=fake, grouped_fetch=_grouped({}))
    assert receipt["tickers"]["UUP"]["status"] == "GAP_TOO_LONG"
    assert receipt["tickers"]["GONE"]["status"] == "NEVER_STORED"
    assert fake.calls == [] and receipt["exit_code"] == 2


# --- one-time backfill ----------------------------------------------------------------------------------------

def test_the_backfill_dry_run_fetches_once_writes_nothing_and_execute_writes_exactly_what_was_reviewed(tmp_path):
    db = _db(tmp_path, {"UUP": {"2026-11-02": 27.0, "2026-11-03": 27.1}, "SPY": {"2026-11-20": 600.0}})
    fake = FakePolygon(aggs={"UUP": {"2026-11-02": 27.0, "2026-11-03": 27.5, "2026-11-04": 27.2, "2026-11-20": 27.3}})
    out = tmp_path / "backfill"
    review = sw.backfill_dry_run(db, ["UUP", "SPY"], now=NOW, cfg=CFG, transport=fake, out_dir=out)
    assert set(_rows(db, "UUP")) == {"2026-11-02", "2026-11-03"}              # dry run: no write
    assert list(review["tickers"]) == ["UUP"]                                # SPY is up to date: not in scope
    u = review["tickers"]["UUP"]
    assert u["status"] == "READY" and u["rows"] == 4 and u["overlap"] == 2
    assert u["overlap_differs"] == 1        # 3 Nov close moves beyond 0.5%
    assert u["will_revise"] == 2            # 2 Nov differs in volume only: still a recorded revision, so counted
    assert u["max_internal_jump_ratio"] < 1.45
    assert (out / "fetched" / "UUP.json").exists()
    fake.aggs["UUP"]["2026-11-20"] = 99.0                                     # the provider changes after review
    receipt = sw.backfill_execute(db, out, backup_dir=tmp_path / "backups")
    rows = _rows(db, "UUP")
    assert rows["2026-11-20"] == (27.3, "BOARD_UNIVERSE_BACKFILL")           # what was reviewed, no second fetch
    assert rows["2026-11-03"][0] == 27.5 and db.revision_count("UUP") == u["will_revise"] == 2
    assert receipt["ingest"]["UUP"]["inserted"] == 2 and receipt["ingest"]["UUP"]["revised"] == 2
    assert list((tmp_path / "backups").glob("*.sqlite"))
    assert sum("/v2/aggs/ticker/" in u for u in fake.calls) == 1


def test_a_backfill_that_does_not_reach_the_last_completed_session_or_jumps_is_not_ready(tmp_path):
    db = _db(tmp_path, {"IJR": {"2026-11-02": 100.0}, "XME": {"2026-11-02": 50.0}})
    fake = FakePolygon(aggs={"IJR": {"2026-11-02": 100.0, "2026-11-18": 101.0},
                             "XME": {"2026-11-02": 50.0, "2026-11-19": 99.0, "2026-11-20": 99.5}})
    review = sw.backfill_dry_run(db, ["IJR", "XME"], now=NOW, cfg=CFG, transport=fake, out_dir=tmp_path / "b")
    assert review["tickers"]["IJR"]["status"] == "NOT_READY" and "ENDS_BEFORE_LAST_SESSION" in review["tickers"]["IJR"]["reasons"]
    assert review["tickers"]["XME"]["status"] == "NOT_READY" and "INTERNAL_JUMP" in review["tickers"]["XME"]["reasons"]
    receipt = sw.backfill_execute(db, tmp_path / "b", backup_dir=tmp_path / "bk")
    assert receipt["ingest"] == {} and set(_rows(db, "IJR")) == {"2026-11-02"}


def test_ack_can_release_a_jump_hold_after_checking_it_but_never_a_short_history(tmp_path):
    # 20 Nov 2026 dry run: SOXL/SOXS, BOIL/KOLD were held for real moves (each mirror moved the other way that day).
    db = _db(tmp_path, {"IJR": {"2026-11-02": 100.0}, "XME": {"2026-11-02": 50.0}})
    fake = FakePolygon(aggs={"IJR": {"2026-11-02": 100.0, "2026-11-18": 101.0},
                             "XME": {"2026-11-02": 50.0, "2026-11-19": 99.0, "2026-11-20": 99.5}})
    sw.backfill_dry_run(db, ["IJR", "XME"], now=NOW, cfg=CFG, transport=fake, out_dir=tmp_path / "b")
    receipt = sw.backfill_execute(db, tmp_path / "b", backup_dir=tmp_path / "bk", accept=["xme", "IJR"])
    assert receipt["accepted_by_ack"] == ["XME"] and list(receipt["ingest"]) == ["XME"]
    assert receipt["not_written"] == {"IJR": ["ENDS_BEFORE_LAST_SESSION"]}
    assert _rows(db, "XME")["2026-11-20"] == (99.5, "BOARD_UNIVERSE_BACKFILL")


def test_the_board_universe_is_every_group_ticker_once():
    config = {"universe": [{"tickers": ["SPY", "RSP"]}, {"tickers": ["RSP", "UUP"]}]}
    assert sw.board_universe(config) == ["RSP", "SPY", "UUP"]


def test_execute_refuses_a_different_store_from_the_one_reviewed(tmp_path):
    db = _db(tmp_path, {"UUP": {"2026-11-02": 27.0}})
    fake = FakePolygon(aggs={"UUP": {"2026-11-02": 27.0, "2026-11-20": 27.3}})
    sw.backfill_dry_run(db, ["UUP"], now=NOW, cfg=CFG, transport=fake, out_dir=tmp_path / "b")
    other = HistoricalPriceDatabase(tmp_path / "other.sqlite")
    other.initialise()
    with pytest.raises(ValueError):
        sw.backfill_execute(other, tmp_path / "b", backup_dir=tmp_path / "bk")
    assert not list((tmp_path / "bk").glob("*")) if (tmp_path / "bk").exists() else True


def test_the_command_line_stops_when_the_price_store_is_missing(tmp_path, capsys):
    assert sw.main(["--db", str(tmp_path / "absent.sqlite")]) == 1
    assert not (tmp_path / "absent.sqlite").exists()
