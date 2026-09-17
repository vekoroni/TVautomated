"""Read-only access to the canonical daily price store."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
from typing import Iterable

from ..model import Bar

DEFAULT_PRICE_DB = Path(__file__).resolve().parents[3] / "data" / "canonical" / "historical_prices.sqlite"


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.execute("PRAGMA temp_store = MEMORY")
    return connection


def latest_session(path: Path = DEFAULT_PRICE_DB) -> date:
    with _connect(path) as connection:
        value = connection.execute("SELECT MAX(trading_date) FROM ohlcv_daily WHERE bar_status = 'COMPLETE'").fetchone()[0]
    return date.fromisoformat(value)


def load_bars(tickers: Iterable[str], start: date, end: date, path: Path = DEFAULT_PRICE_DB) -> dict[str, list[Bar]]:
    """Complete bars for ``tickers`` with start <= session <= end, sorted by session."""
    wanted = sorted({t.upper() for t in tickers})
    result: dict[str, list[Bar]] = {t: [] for t in wanted}
    if not wanted:
        return result
    with _connect(path) as connection:
        connection.execute("CREATE TEMP TABLE wanted(ticker TEXT PRIMARY KEY)")
        connection.executemany("INSERT INTO wanted VALUES (?)", [(t,) for t in wanted])
        rows = connection.execute(
            """
            SELECT o.ticker, o.trading_date, o.open, o.high, o.low, o.close
            FROM ohlcv_daily o JOIN wanted w ON w.ticker = o.ticker
            WHERE o.bar_status = 'COMPLETE' AND o.trading_date BETWEEN ? AND ?
            ORDER BY o.ticker, o.trading_date
            """,
            (start.isoformat(), end.isoformat()),
        )
        for ticker, session, open_, high, low, close in rows:
            result[ticker].append(Bar(date.fromisoformat(session), open_, high, low, close))
    return result


def all_tickers(path: Path = DEFAULT_PRICE_DB) -> list[str]:
    with _connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT DISTINCT ticker FROM ohlcv_daily ORDER BY ticker")]


def load_all_bars(start: date, end: date, path: Path = DEFAULT_PRICE_DB) -> dict[str, list[Bar]]:
    """Complete bars for every ticker with start <= session <= end."""
    result: dict[str, list[Bar]] = {}
    with _connect(path) as connection:
        rows = connection.execute(
            "SELECT ticker, trading_date, open, high, low, close FROM ohlcv_daily "
            "WHERE bar_status = 'COMPLETE' AND trading_date BETWEEN ? AND ? ORDER BY ticker, trading_date",
            (start.isoformat(), end.isoformat()),
        )
        for ticker, session, open_, high, low, close in rows:
            result.setdefault(ticker, []).append(Bar(date.fromisoformat(session), open_, high, low, close))
    return result
