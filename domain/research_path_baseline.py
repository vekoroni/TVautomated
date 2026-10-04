"""Unconditional, pre-decision historical price paths for research EV only.

This is deliberately *not* the signed C4 state-conditioned forecast. It uses
non-overlapping completed 20-session windows of the same ticker's price
history, as known by the current decision cutoff. It cannot establish that
today's Wyckoff/compression evidence has a predictive edge.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_data.forecast_path_reader import ADJUSTMENT_CONVENTION
from canonical_data.session_clock import xnys_sessions_between


@dataclass(frozen=True, slots=True)
class ResearchBar:
    session: str
    open: float
    high: float
    low: float
    close: float
    observed_at_utc: str
    batch_id: str


@dataclass(frozen=True, slots=True)
class RelativePath:
    path_id: str
    start_session: str
    end_session: str
    bars: tuple[tuple[float, float, float, float], ...]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("research path timestamps must include timezone")
    return parsed.astimezone(timezone.utc)


def read_current_known_bars(
    connection: sqlite3.Connection, *, ticker: str, evidence_session: str,
    decision_cutoff_utc: str,
) -> tuple[ResearchBar, ...]:
    """Read complete current bar versions acquired before this run's cutoff."""
    cutoff = _utc(decision_cutoff_utc)
    date.fromisoformat(evidence_session)
    rows = connection.execute(
        """SELECT p.trading_date,p.open,p.high,p.low,p.close,p.observed_at,
                  p.current_batch_id,b.completed_at
           FROM ohlcv_daily AS p
           JOIN ohlcv_ingest_batches AS b ON b.batch_id=p.current_batch_id
           WHERE p.ticker=? AND p.adjustment_convention=? AND p.bar_status='COMPLETE'
             AND p.trading_date<? ORDER BY p.trading_date""",
        (ticker, ADJUSTMENT_CONVENTION, evidence_session),
    ).fetchall()
    result = []
    for row in rows:
        if _utc(row["observed_at"]) > cutoff or _utc(row["completed_at"]) > cutoff:
            continue
        values = tuple(float(row[key]) for key in ("open", "high", "low", "close"))
        opened, high, low, close = values
        if (not all(math.isfinite(value) and value > 0 for value in values)
                or not low <= min(opened, close) <= max(opened, close) <= high):
            continue
        result.append(ResearchBar(row["trading_date"], *values,
                                  row["observed_at"], row["current_batch_id"]))
    return tuple(result)


def build_nonoverlapping_relative_paths(
    ticker: str, bars: tuple[ResearchBar, ...], *, horizon: int = 20,
) -> tuple[RelativePath, ...]:
    if not ticker or horizon < 1:
        raise ValueError("ticker and positive path horizon required")
    paths: list[RelativePath] = []
    offset = 0
    while offset + horizon < len(bars):
        window = bars[offset:offset + horizon + 1]
        dates = [date.fromisoformat(bar.session) for bar in window]
        if any(xnys_sessions_between(dates[index - 1], dates[index]) != 1
               for index in range(1, len(dates))):
            offset += 1
            continue
        origin = window[0].close
        relative = tuple((bar.open / origin, bar.high / origin,
                          bar.low / origin, bar.close / origin) for bar in window[1:])
        identity = hashlib.sha256(json.dumps(
            {"ticker": ticker, "start": window[0].session,
             "end": window[-1].session, "batches": [bar.batch_id for bar in window]},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        paths.append(RelativePath(identity, window[0].session, window[-1].session, relative))
        offset += horizon
    return tuple(paths)


def open_research_price_database(path: str | Path) -> sqlite3.Connection:
    database = Path(path).resolve(strict=True)
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection
