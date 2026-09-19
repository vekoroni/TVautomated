"""IV history stays current and every run reports its data readiness (ACK, 19 Sep 2026).

Verify step 19 Sep: Phantom held full-Greek chains for 11 Sep (1,584 tickers) and 17 Sep (1,359), but
iv_surface_history and the IV cache stopped at 4 Sep - the chains were stored, never turned into IV history,
because only the manual weekly finalize step derived it (and selected rows by 'last N appended').
- derive_iv_history(): the finalize calculation for one session, selected by (ticker, quote_date), rewriting only
  the tickers it derives. Used by the one-off catch-up and by the evening run after the Phantom delivery.
- check_data_readiness(): at the start of every run, each source's latest session and lag; STALE/MISSING is
  reported, never blocks (R12).
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from scripts import finalize_phantom_weekly_snapshot as fin

CHAIN_COLS = ("ticker", "quote_date", "option_symbol", "side", "strike", "dte", "bid", "mid", "ask", "open_interest",
              "volume", "underlying_price", "iv", "delta", "gamma", "theta", "vega", "source")


def _phantom(path):
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE chain_snapshots ({', '.join(CHAIN_COLS)})")
    con.execute("CREATE INDEX idx_chain_ticker_date ON chain_snapshots(ticker, quote_date)")
    con.execute("""CREATE TABLE iv_surface_history (ticker TEXT NOT NULL, quote_date TEXT NOT NULL,
        dte_bucket TEXT NOT NULL, side TEXT NOT NULL, contract_count INTEGER, atm_iv REAL, median_iv REAL,
        iv_entropy REAL, skew_25d REAL, put_call_iv_spread REAL, median_spread_pct REAL,
        total_open_interest INTEGER, total_volume INTEGER, created_at_utc TEXT,
        PRIMARY KEY (ticker, quote_date, dte_bucket, side))""")
    return con


def _cache(path):
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE iv_history (ticker TEXT NOT NULL, sample_date TEXT NOT NULL, atm_iv REAL,
        source TEXT DEFAULT 'marketdata', updated_at TEXT DEFAULT (datetime('now')), PRIMARY KEY (ticker, sample_date))""")
    con.execute("CREATE TABLE iv_cache_meta (ticker TEXT PRIMARY KEY, last_full_build TEXT, last_refresh TEXT)")
    con.commit()
    return con


def _chain(con, ticker, session, iv):
    for side, delta in (("call", 0.5), ("put", -0.5), ("call", 0.25), ("put", -0.25)):
        con.execute(f"INSERT INTO chain_snapshots ({', '.join(CHAIN_COLS)}) VALUES ({', '.join('?' * len(CHAIN_COLS))})",
                    (ticker, session, f"{ticker}{side}{delta}", side, 100.0, 30, 1.9, 2.0, 2.1, 100, 10, 100.0, iv,
                     delta, 0.03, -0.03, 0.1, "MARKETDATA"))
    con.commit()


@pytest.fixture
def dbs(tmp_path):
    phantom, cache = _phantom(tmp_path / "phantom.db"), _cache(tmp_path / "cache.db")
    _chain(phantom, "AAA", "2026-09-17", 0.40)
    _chain(phantom, "BBB", "2026-09-17", 0.55)
    phantom.execute("INSERT INTO iv_surface_history (ticker, quote_date, dte_bucket, side) "
                    "VALUES ('ZZZ', '2026-09-17', '8_30', 'call')")        # another ticker's row for the same date
    phantom.commit()
    return tmp_path / "phantom.db", tmp_path / "cache.db"


def test_a_session_is_derived_from_its_stored_chains(dbs):
    phantom, cache = dbs
    report = fin.derive_iv_history(phantom, cache, "2026-09-17", ["AAA", "BBB"], execute=True)
    assert report["tickers_derived"] == 2 and report["executed"] is True
    con = sqlite3.connect(phantom)
    assert con.execute("SELECT COUNT(*) FROM iv_surface_history WHERE ticker IN ('AAA','BBB') "
                       "AND quote_date='2026-09-17'").fetchone()[0] == 4          # 2 tickers x call/put
    atm = dict(sqlite3.connect(cache).execute("SELECT ticker, atm_iv FROM iv_history WHERE sample_date='2026-09-17'"))
    assert atm == {"AAA": pytest.approx(0.40), "BBB": pytest.approx(0.55)}


def test_only_the_derived_tickers_are_rewritten(dbs):
    phantom, cache = dbs
    fin.derive_iv_history(phantom, cache, "2026-09-17", ["AAA"], execute=True)
    con = sqlite3.connect(phantom)
    assert con.execute("SELECT COUNT(*) FROM iv_surface_history WHERE ticker='ZZZ'").fetchone()[0] == 1


def test_a_dry_run_writes_nothing(dbs):
    phantom, cache = dbs
    report = fin.derive_iv_history(phantom, cache, "2026-09-17", ["AAA", "BBB"], execute=False)
    assert report["surface_rows"] == 4 and report["executed"] is False
    assert sqlite3.connect(cache).execute("SELECT COUNT(*) FROM iv_history").fetchone()[0] == 0


def test_a_session_without_chains_is_reported_not_written(dbs):
    phantom, cache = dbs
    report = fin.derive_iv_history(phantom, cache, "2026-09-18", ["AAA"], execute=True)
    assert report["tickers_derived"] == 0 and report["status"] == "NO_CHAINS_FOR_SESSION"


def test_the_evening_run_refreshes_iv_history_after_the_phantom_delivery():
    import inspect
    import intelligent_orchestrator as orch
    source = inspect.getsource(orch)
    delivery = source.index("_phantom_projection_results = deliver_phantom_option_events(")
    refresh = source.index("refresh_iv_history_after_delivery(canonical_run_id, _evidence_session_date)")
    assert delivery < refresh


# --- readiness ------------------------------------------------------------------------------------------------

def _prices(tmp_path, latest):
    prices = tmp_path / "prices.sqlite"
    con = sqlite3.connect(prices)
    con.execute("CREATE TABLE IF NOT EXISTS ohlcv_daily (ticker TEXT, trading_date TEXT, close REAL)")
    con.execute("INSERT INTO ohlcv_daily VALUES ('SPY', ?, 1.0)", (latest,))
    con.commit()
    return prices


def _readiness(dbs, tmp_path, expected):
    import intelligent_orchestrator as orch
    phantom, cache = dbs
    return orch.check_data_readiness(expected_session=expected, phantom_path=phantom, iv_cache_path=cache,
                                     price_path=_prices(tmp_path, "2026-09-17"), phantom_sample_tickers=("AAA",))


def test_readiness_reports_each_source_its_latest_session_and_lag(dbs, tmp_path):
    report = _readiness(dbs, tmp_path, date(2026, 9, 17))
    assert report["price_store"] == {"state": "FRESH", "latest": "2026-09-17", "lag_sessions": 0}
    assert report["phantom_chains"]["state"] == "FRESH"
    assert report["iv_surface_history"]["state"] == "FRESH"
    assert report["iv_cache"]["state"] == "MISSING"                        # nothing derived into the cache yet


def test_one_session_behind_is_expected_before_the_run_and_more_is_stale(dbs, tmp_path):
    before_run = _readiness(dbs, tmp_path, date(2026, 9, 18))
    assert before_run["price_store"]["state"] == "BEHIND_ONE_SESSION"
    monday = _readiness(dbs, tmp_path, date(2026, 9, 21))
    assert monday["phantom_chains"] == {"state": "STALE", "latest": "2026-09-17", "lag_sessions": 2}


def test_readiness_never_raises_on_a_missing_database(tmp_path):
    import intelligent_orchestrator as orch
    report = orch.check_data_readiness(expected_session=date(2026, 9, 17), phantom_path=tmp_path / "none.db",
                                       iv_cache_path=tmp_path / "none2.db", price_path=tmp_path / "none3.db",
                                       phantom_sample_tickers=("AAA",))
    assert {v["state"] for v in report.values()} == {"MISSING"}
