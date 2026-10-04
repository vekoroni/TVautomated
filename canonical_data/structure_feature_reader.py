"""Read-only point-in-time OHLCV window for historical structure replay.

Unlike an outcome path, this window ends at the simulated decision session.
It must not silently replace a missing decision-time bar with today's revised
database value. This module does not classify Wyckoff phase or fit a model.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from avshunter.shared.xnys_calendar import is_xnys_session, session_state

from .forecast_path_reader import ADJUSTMENT_CONVENTION, _instant, _row_at_cutoff


READER_VERSION = "structure_feature_reader_v1"


@dataclass(frozen=True, slots=True)
class HistoricalFeatureBar:
    trading_date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    batch_id: str
    provider: str
    version_fingerprint: str


@dataclass(frozen=True, slots=True)
class CanonicalFeatureWindow:
    ticker: str
    decision_session: str
    as_of_utc: str
    adjustment_convention: str
    bars: tuple[HistoricalFeatureBar, ...]
    missing_sessions: tuple[str, ...]
    revision_rewinds: int
    complete: bool
    read_only: bool = True
    reader_version: str = READER_VERSION


def _window_dates(end: date, count: int) -> tuple[str, ...]:
    dates: list[str] = []
    cursor = end
    while len(dates) < count:
        if is_xnys_session(cursor):
            dates.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(dates))


def read_feature_window(
    database_path: str | Path,
    *,
    ticker: str,
    decision_session: str,
    lookback_sessions: int,
    as_of_utc: str,
    adjustment_convention: str = ADJUSTMENT_CONVENTION,
) -> CanonicalFeatureWindow:
    """Return completed bars knowable at `as_of_utc`, never future bars.

    Missing, partial, late-acquired or unprovable revisions remain missing.
    The caller must reject or explicitly account for incomplete windows.
    """
    symbol = str(ticker).strip().upper()
    if not symbol:
        raise ValueError("ticker is required")
    end = date.fromisoformat(decision_session)
    if not is_xnys_session(end):
        raise ValueError("decision_session must be an XNYS session")
    if isinstance(lookback_sessions, bool) or not isinstance(lookback_sessions, int) or lookback_sessions < 1:
        raise ValueError("lookback_sessions must be a positive integer")
    cutoff = _instant(as_of_utc)
    if session_state(cutoff)[2] < end:
        raise ValueError("decision_session is not completed at as_of_utc")
    expected = _window_dates(end, lookback_sessions)
    path = Path(database_path).resolve(strict=True)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """SELECT ticker, trading_date, adjustment_convention, open, high,
                      low, close, volume, bar_status, provider, observed_at,
                      current_batch_id FROM ohlcv_daily
               WHERE ticker=? AND adjustment_convention=?
                 AND trading_date>=? AND trading_date<=?
               ORDER BY trading_date""",
            (symbol, adjustment_convention, expected[0], expected[-1]),
        ).fetchall()
        allowed = set(expected)
        bars: list[HistoricalFeatureBar] = []
        rewinds = 0
        for row in rows:
            if row["trading_date"] not in allowed:
                continue
            selected = _row_at_cutoff(
                connection, row, cutoff,
                value_columns=("open", "high", "low", "close", "volume", "bar_status"),
            )
            if selected is None:
                continue
            values, batch_id, provider, count = selected
            try:
                volume = float(values["volume"])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(volume) or volume < 0:
                continue
            rewinds += count
            payload = {
                "ticker": symbol, "date": row["trading_date"],
                "adjustment": adjustment_convention, "batch_id": batch_id,
                "values": {key: values[key] for key in ("open", "high", "low", "close", "volume")},
            }
            fingerprint = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            bars.append(HistoricalFeatureBar(
                row["trading_date"],
                *(float(values[key]) for key in ("open", "high", "low", "close")),
                volume,
                batch_id, provider, fingerprint,
            ))
    finally:
        connection.close()
    present = {bar.trading_date for bar in bars}
    missing = tuple(day for day in expected if day not in present)
    return CanonicalFeatureWindow(
        symbol, end.isoformat(), as_of_utc, adjustment_convention,
        tuple(bars), missing, rewinds, not missing,
    )
