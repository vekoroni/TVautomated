"""Read-only, as-of canonical OHLCV path reader for C4 outcome research.

This adapter never fetches prices or mutates the live SQLite database. It
reconstructs a prior version from recorded revisions when a current bar was
changed after the requested label cut-off. It is not a feature-at-decision
reader; future bars are outcome evidence only.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from avshunter.shared.xnys_calendar import is_xnys_session, session_state


ADJUSTMENT_CONVENTION = "POLYGON_SPLIT_ADJUSTED"
READER_VERSION = "canonical_forecast_path_reader_v1"


@dataclass(frozen=True, slots=True)
class HistoricalForecastBar:
    session: int
    trading_date: str
    open: float
    high: float
    low: float
    close: float
    batch_id: str
    provider: str
    version_fingerprint: str

    def to_label_bar(self) -> dict[str, int | float]:
        return {key: getattr(self, key) for key in ("session", "open", "high", "low", "close")}


@dataclass(frozen=True, slots=True)
class CanonicalForecastPath:
    ticker: str
    start_session: str
    horizon_sessions: int
    horizon_end_session: str
    label_cutoff_utc: str
    adjustment_convention: str
    bars: tuple[HistoricalForecastBar, ...]
    missing_sessions: tuple[int, ...]
    horizon_matured: bool
    revision_rewinds: int
    read_only: bool = True
    reader_version: str = READER_VERSION


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return parsed.astimezone(timezone.utc)


def _future_dates(start: date, horizon: int) -> tuple[date, ...]:
    dates = []
    cursor = start
    while len(dates) < horizon:
        cursor += timedelta(days=1)
        if is_xnys_session(cursor):
            dates.append(cursor)
    return tuple(dates)


def _row_at_cutoff(connection: sqlite3.Connection, row: sqlite3.Row,
                   cutoff: datetime, *,
                   value_columns: tuple[str, ...] = ("open", "high", "low", "close", "bar_status"),
                   ) -> tuple[dict, str, str, int] | None:
    values = {key: row[key] for key in value_columns}
    batch_id, provider = row["current_batch_id"], row["provider"]
    rewinds = 0
    revisions = connection.execute(
        """SELECT previous_values_json, previous_provider, previous_batch_id,
                  revised_at FROM ohlcv_daily_revisions
           WHERE ticker=? AND trading_date=? AND adjustment_convention=?
           ORDER BY revision_id DESC""",
        (row["ticker"], row["trading_date"], row["adjustment_convention"]),
    ).fetchall()
    for revision in revisions:
        if _instant(revision["revised_at"]) <= cutoff:
            break
        try:
            values = json.loads(revision["previous_values_json"])
        except (TypeError, ValueError):
            return None
        batch_id, provider = revision["previous_batch_id"], revision["previous_provider"]
        rewinds += 1
    batch = connection.execute(
        "SELECT completed_at FROM ohlcv_ingest_batches WHERE batch_id=?",
        (batch_id,),
    ).fetchone()
    if batch is None or _instant(batch["completed_at"]) > cutoff:
        return None
    if any(key not in values for key in value_columns) or values.get("bar_status") != "COMPLETE":
        return None
    if not rewinds and _instant(row["observed_at"]) > cutoff:
        return None
    return values, batch_id, provider, rewinds


def read_price_path(
    database_path: str | Path,
    *, ticker: str,
    start_session: str,
    horizon_sessions: int,
    label_cutoff_utc: str,
    adjustment_convention: str = ADJUSTMENT_CONVENTION,
) -> CanonicalForecastPath:
    """Read future completed bars as they existed by `label_cutoff_utc`.

    A missing, partial, late-acquired or unproven revision is excluded, never
    filled from a different provider or adjustment convention.
    """
    symbol = str(ticker).strip().upper()
    if not symbol:
        raise ValueError("ticker is required")
    start = date.fromisoformat(start_session)
    if not is_xnys_session(start):
        raise ValueError("start_session must be a completed XNYS session date")
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or not 1 <= horizon_sessions <= 20:
        raise ValueError("horizon_sessions must be an integer from 1 to 20")
    cutoff = _instant(label_cutoff_utc)
    last_completed = session_state(cutoff)[2]
    future_dates = _future_dates(start, horizon_sessions)
    matured = last_completed >= future_dates[-1]
    eligible_dates = {day.isoformat(): index for index, day in enumerate(future_dates, 1)
                      if day <= last_completed}
    path = Path(database_path).resolve(strict=True)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            """SELECT ticker, trading_date, adjustment_convention, open, high,
                      low, close, bar_status, provider, observed_at,
                      current_batch_id FROM ohlcv_daily
               WHERE ticker=? AND adjustment_convention=?
                 AND trading_date>? AND trading_date<=?
               ORDER BY trading_date""",
            (symbol, adjustment_convention, start.isoformat(),
             future_dates[-1].isoformat()),
        ).fetchall()
        bars: list[HistoricalForecastBar] = []
        rewinds = 0
        for row in rows:
            session = eligible_dates.get(row["trading_date"])
            if session is None:
                continue
            selected = _row_at_cutoff(connection, row, cutoff)
            if selected is None:
                continue
            values, batch_id, provider, count = selected
            rewinds += count
            payload = {
                "ticker": symbol, "date": row["trading_date"],
                "adjustment": adjustment_convention, "batch_id": batch_id,
                "values": {key: values[key] for key in ("open", "high", "low", "close")},
            }
            fingerprint = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            bars.append(HistoricalForecastBar(
                session, row["trading_date"],
                *(float(values[key]) for key in ("open", "high", "low", "close")),
                batch_id, provider, fingerprint,
            ))
    finally:
        connection.close()
    present = {bar.session for bar in bars}
    missing = tuple(index for index in eligible_dates.values() if index not in present)
    return CanonicalForecastPath(
        symbol, start.isoformat(), horizon_sessions,
        future_dates[-1].isoformat(), label_cutoff_utc,
        adjustment_convention, tuple(bars), missing, matured, rewinds,
    )
