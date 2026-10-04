"""SOR-001: historical structure features must be knowable at the decision cut."""

import json
import sqlite3

from canonical_data.structure_feature_reader import read_feature_window


def _database(path):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE ohlcv_ingest_batches (
                batch_id TEXT PRIMARY KEY, completed_at TEXT NOT NULL
            );
            CREATE TABLE ohlcv_daily (
                ticker TEXT, trading_date TEXT, adjustment_convention TEXT,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                bar_status TEXT,
                provider TEXT, observed_at TEXT, current_batch_id TEXT
            );
            CREATE TABLE ohlcv_daily_revisions (
                revision_id INTEGER PRIMARY KEY, ticker TEXT, trading_date TEXT,
                adjustment_convention TEXT, previous_values_json TEXT,
                previous_provider TEXT, previous_batch_id TEXT, revised_at TEXT
            );
        """)
    return path


def _bar(connection, day, *, high=105, status="COMPLETE", batch="B1",
         acquired="2026-09-25T21:00:00Z"):
    connection.execute("INSERT OR IGNORE INTO ohlcv_ingest_batches VALUES (?, ?)",
                       (batch, acquired))
    connection.execute(
        "INSERT INTO ohlcv_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("XYZ", day, "POLYGON_SPLIT_ADJUSTED", 100, high, 95, 100, 1000,
         status, "POLYGON", acquired, batch),
    )


def test_feature_window_rewinds_later_revision_and_excludes_future_bar(tmp_path):
    path = _database(tmp_path / "bars.sqlite")
    with sqlite3.connect(path) as connection:
        _bar(connection, "2026-09-24", batch="B0",
             acquired="2026-09-24T21:00:00Z")
        _bar(connection, "2026-09-25", high=120, batch="B2",
             acquired="2026-09-28T21:00:00Z")
        _bar(connection, "2026-09-28", high=130, batch="B3",
             acquired="2026-09-28T21:00:00Z")
        connection.execute("INSERT INTO ohlcv_ingest_batches VALUES (?, ?)",
                           ("B1", "2026-09-25T21:00:00Z"))
        connection.execute(
            "INSERT INTO ohlcv_daily_revisions VALUES (?,?,?,?,?,?,?,?)",
            (1, "XYZ", "2026-09-25", "POLYGON_SPLIT_ADJUSTED",
             json.dumps(dict(open=100, high=106, low=95, close=100, volume=900,
                             bar_status="COMPLETE")),
             "POLYGON", "B1", "2026-09-28T21:00:00Z"),
        )
    before = read_feature_window(
        path, ticker="XYZ", decision_session="2026-09-25", lookback_sessions=2,
        as_of_utc="2026-09-26T12:00:00Z",
    )
    assert [(bar.trading_date, bar.high) for bar in before.bars] == [
        ("2026-09-24", 105), ("2026-09-25", 106),
    ]
    assert before.missing_sessions == ()
    assert before.revision_rewinds == 1
    assert [bar.volume for bar in before.bars] == [1000, 900]
    assert all(bar.trading_date <= before.decision_session for bar in before.bars)


def test_feature_window_reports_late_or_partial_bar_without_filling(tmp_path):
    path = _database(tmp_path / "bars.sqlite")
    with sqlite3.connect(path) as connection:
        _bar(connection, "2026-09-24", status="PARTIAL",
             acquired="2026-09-24T21:00:00Z")
        _bar(connection, "2026-09-25", batch="B2",
             acquired="2026-09-28T21:00:00Z")
    window = read_feature_window(
        path, ticker="XYZ", decision_session="2026-09-25", lookback_sessions=2,
        as_of_utc="2026-09-26T12:00:00Z",
    )
    assert window.bars == ()
    assert window.missing_sessions == ("2026-09-24", "2026-09-25")
    assert window.complete is False
