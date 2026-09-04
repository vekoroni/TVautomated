"""Canonical, revision-audited daily OHLCV database for CDS-2."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable, Iterator, Mapping, Sequence
from uuid import uuid4

import pandas as pd

from .errors import DatasetValidationError


PRICE_SCHEMA_VERSION = "cds_historical_prices_v1"
REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")
DEFAULT_ADJUSTMENT = "POLYGON_SPLIT_ADJUSTED"


@dataclass(frozen=True, slots=True)
class PriceIngestResult:
    batch_id: str
    ticker: str
    input_rows: int
    valid_rows: int
    inserted_rows: int
    revised_rows: int
    unchanged_rows: int
    duplicate_rows: int
    rejected_rows: int
    first_date: date | None
    last_date: date | None


@dataclass(frozen=True, slots=True)
class PriceCoverage:
    ticker: str
    row_count: int
    first_date: date | None
    last_date: date | None
    partial_rows: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime | None = None) -> str:
    instant = value or _utc_now()
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_hash(values: Sequence[object]) -> str:
    payload = "|".join(str(value) for value in values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalise_daily_ohlcv(
    data: pd.DataFrame | Iterable[Mapping[str, object]],
) -> tuple[pd.DataFrame, int]:
    """Normalize daily bars and reject structurally invalid observations."""
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    input_rows = len(frame)
    if frame.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS), 0
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise DatasetValidationError(
            f"daily OHLCV is missing required columns: {sorted(missing)}"
        )
    frame = frame.loc[:, REQUIRED_COLUMNS].copy()
    parsed_dates = pd.to_datetime(
        frame["date"], format="mixed", errors="coerce", utc=True
    )
    frame["date"] = parsed_dates.dt.tz_convert(None).dt.normalize()
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = frame[list(REQUIRED_COLUMNS)].notna().all(axis=1)
    valid &= (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
    valid &= frame["volume"] >= 0
    tolerance = 1e-8
    valid &= frame["high"] + tolerance >= frame[["open", "close", "low"]].max(axis=1)
    valid &= frame["low"] - tolerance <= frame[["open", "close", "high"]].min(axis=1)
    invalid_rows = input_rows - int(valid.sum())
    frame = frame.loc[valid].sort_values("date")
    valid_rows_before_dedupe = len(frame)
    frame = frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    frame.attrs["duplicate_rows"] = valid_rows_before_dedupe - len(frame)
    return frame, invalid_rows


def _same_price_row(existing: sqlite3.Row, incoming: tuple[object, ...]) -> bool:
    # incoming: date, open, high, low, close, volume, bar_status, row_hash
    for column, value in zip(("open", "high", "low", "close", "volume"), incoming[1:6]):
        current = float(existing[column])
        candidate = float(value)
        tolerance = max(1e-8, abs(current) * 1e-9)
        if abs(current - candidate) > tolerance:
            return False
    return existing["bar_status"] == incoming[6]


class HistoricalPriceDatabase:
    """One current price row plus append-only revisions for every ticker/date."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=60)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 60000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS price_schema_metadata (
                    schema_version TEXT PRIMARY KEY,
                    installed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ohlcv_ingest_batches (
                    batch_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    adjustment_convention TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_run_id TEXT,
                    fetched_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    input_rows INTEGER NOT NULL,
                    valid_rows INTEGER NOT NULL,
                    inserted_rows INTEGER NOT NULL,
                    revised_rows INTEGER NOT NULL,
                    unchanged_rows INTEGER NOT NULL,
                    duplicate_rows INTEGER NOT NULL DEFAULT 0,
                    rejected_rows INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ohlcv_daily (
                    ticker TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    adjustment_convention TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    bar_status TEXT NOT NULL CHECK(bar_status IN ('COMPLETE', 'PARTIAL')),
                    provider TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    source_run_id TEXT,
                    fetched_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    row_hash TEXT NOT NULL,
                    current_batch_id TEXT NOT NULL,
                    PRIMARY KEY(ticker, trading_date, adjustment_convention),
                    FOREIGN KEY(current_batch_id) REFERENCES ohlcv_ingest_batches(batch_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ohlcv_daily_lookup
                    ON ohlcv_daily(ticker, adjustment_convention, trading_date);
                CREATE TABLE IF NOT EXISTS ohlcv_daily_revisions (
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    adjustment_convention TEXT NOT NULL,
                    previous_values_json TEXT NOT NULL,
                    replacement_values_json TEXT NOT NULL,
                    previous_provider TEXT NOT NULL,
                    replacement_provider TEXT NOT NULL,
                    previous_batch_id TEXT NOT NULL,
                    replacement_batch_id TEXT NOT NULL,
                    revision_reason TEXT NOT NULL,
                    revised_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ohlcv_revision_lookup
                    ON ohlcv_daily_revisions(ticker, trading_date, revision_id);
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO price_schema_metadata(schema_version, installed_at)
                VALUES (?, ?)
                """,
                (PRICE_SCHEMA_VERSION, _iso_utc()),
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(ohlcv_ingest_batches)")
            }
            if "duplicate_rows" not in columns:
                connection.execute(
                    "ALTER TABLE ohlcv_ingest_batches "
                    "ADD COLUMN duplicate_rows INTEGER NOT NULL DEFAULT 0"
                )

    def validate_schema(self) -> dict[str, object]:
        required = {
            "price_schema_metadata",
            "ohlcv_ingest_batches",
            "ohlcv_daily",
            "ohlcv_daily_revisions",
        }
        with self.connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            versions = {
                row["schema_version"]
                for row in connection.execute(
                    "SELECT schema_version FROM price_schema_metadata"
                )
            }
            foreign_key_violations = tuple(
                tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
            )
        missing = tuple(sorted(required - tables))
        return {
            "valid": not missing
            and PRICE_SCHEMA_VERSION in versions
            and not foreign_key_violations,
            "schema_version": PRICE_SCHEMA_VERSION,
            "missing_tables": missing,
            "foreign_key_violations": foreign_key_violations,
        }

    def ingest(
        self,
        ticker: str,
        data: pd.DataFrame | Iterable[Mapping[str, object]],
        *,
        provider: str,
        source_kind: str,
        source_run_id: str | None = None,
        adjustment_convention: str = DEFAULT_ADJUSTMENT,
        fetched_at: datetime | None = None,
        partial_dates: Iterable[date | str] = (),
    ) -> PriceIngestResult:
        frame, rejected = normalise_daily_ohlcv(data)
        duplicate_rows = int(frame.attrs.get("duplicate_rows", 0))
        if frame.empty:
            raise DatasetValidationError("daily OHLCV contains no valid rows")
        symbol = ticker.strip().upper()
        if not symbol:
            raise DatasetValidationError("ticker is required")
        provider_name = provider.strip().upper()
        source_name = source_kind.strip().upper()
        if not provider_name or not source_name:
            raise DatasetValidationError("provider and source_kind are required")
        partial = {str(value)[:10] for value in partial_dates}
        fetched = _iso_utc(fetched_at)
        batch_id = str(uuid4())
        rows: list[tuple[object, ...]] = []
        for row in frame.itertuples(index=False):
            trading_date = pd.Timestamp(row.date).date().isoformat()
            status = "PARTIAL" if trading_date in partial else "COMPLETE"
            values = (
                trading_date,
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
                float(row.volume),
                status,
            )
            rows.append((*values, _row_hash(values)))

        inserted: list[tuple[object, ...]] = []
        updated: list[tuple[object, ...]] = []
        revisions: list[tuple[object, ...]] = []
        unchanged = 0
        dates = tuple(row[0] for row in rows)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            placeholders = ",".join("?" for _ in dates)
            existing_rows = connection.execute(
                f"""
                SELECT * FROM ohlcv_daily
                WHERE ticker = ? AND adjustment_convention = ?
                  AND trading_date IN ({placeholders})
                """,
                (symbol, adjustment_convention, *dates),
            ).fetchall()
            existing = {row["trading_date"]: row for row in existing_rows}
            now = _iso_utc()
            for incoming in rows:
                current = existing.get(incoming[0])
                if current is None:
                    inserted.append(incoming)
                    continue
                if _same_price_row(current, incoming):
                    unchanged += 1
                    continue
                previous_values = {
                    key: current[key]
                    for key in ("open", "high", "low", "close", "volume", "bar_status")
                }
                replacement_values = dict(
                    zip(
                        ("open", "high", "low", "close", "volume", "bar_status"),
                        incoming[1:7],
                    )
                )
                revisions.append(
                    (
                        symbol,
                        incoming[0],
                        adjustment_convention,
                        json.dumps(previous_values, sort_keys=True),
                        json.dumps(replacement_values, sort_keys=True),
                        current["provider"],
                        provider_name,
                        current["current_batch_id"],
                        batch_id,
                        "PROVIDER_REVISION_OR_CORPORATE_ACTION",
                        now,
                    )
                )
                updated.append(incoming)

            connection.execute(
                """
                INSERT INTO ohlcv_ingest_batches(
                    batch_id, ticker, provider, adjustment_convention,
                    source_kind, source_run_id, fetched_at, completed_at,
                    input_rows, valid_rows, inserted_rows, revised_rows,
                    unchanged_rows, duplicate_rows, rejected_rows
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id, symbol, provider_name, adjustment_convention,
                    source_name, source_run_id, fetched, now,
                    len(frame) + duplicate_rows + rejected,
                    len(frame), len(inserted), len(updated), unchanged,
                    duplicate_rows, rejected,
                ),
            )
            connection.executemany(
                """
                INSERT INTO ohlcv_daily(
                    ticker, trading_date, adjustment_convention,
                    open, high, low, close, volume, bar_status,
                    provider, source_kind, source_run_id, fetched_at,
                    observed_at, row_hash, current_batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        symbol, incoming[0], adjustment_convention,
                        *incoming[1:7], provider_name, source_name,
                        source_run_id, fetched, now, incoming[7], batch_id,
                    )
                    for incoming in inserted
                ),
            )
            connection.executemany(
                """
                INSERT INTO ohlcv_daily_revisions(
                    ticker, trading_date, adjustment_convention,
                    previous_values_json, replacement_values_json,
                    previous_provider, replacement_provider,
                    previous_batch_id, replacement_batch_id,
                    revision_reason, revised_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                revisions,
            )
            connection.executemany(
                """
                UPDATE ohlcv_daily SET
                    open = ?, high = ?, low = ?, close = ?, volume = ?,
                    bar_status = ?, provider = ?, source_kind = ?,
                    source_run_id = ?, fetched_at = ?, observed_at = ?,
                    row_hash = ?, current_batch_id = ?
                WHERE ticker = ? AND trading_date = ?
                  AND adjustment_convention = ?
                """,
                (
                    (
                        *incoming[1:7], provider_name, source_name, source_run_id,
                        fetched, now, incoming[7], batch_id, symbol,
                        incoming[0], adjustment_convention,
                    )
                    for incoming in updated
                ),
            )

        first_date = pd.Timestamp(frame["date"].iloc[0]).date()
        last_date = pd.Timestamp(frame["date"].iloc[-1]).date()
        return PriceIngestResult(
            batch_id=batch_id,
            ticker=symbol,
            input_rows=len(frame) + duplicate_rows + rejected,
            valid_rows=len(frame),
            inserted_rows=len(inserted),
            revised_rows=len(updated),
            unchanged_rows=unchanged,
            duplicate_rows=duplicate_rows,
            rejected_rows=rejected,
            first_date=first_date,
            last_date=last_date,
        )

    def read(
        self,
        ticker: str,
        *,
        start_date: date | str | None = None,
        end_date: date | str | None = None,
        bars: int | None = None,
        adjustment_convention: str = DEFAULT_ADJUSTMENT,
        completed_only: bool = True,
    ) -> pd.DataFrame:
        sql = """
            SELECT trading_date AS date, open, high, low, close, volume
            FROM ohlcv_daily
            WHERE ticker = ? AND adjustment_convention = ?
        """
        parameters: list[object] = [ticker.strip().upper(), adjustment_convention]
        if completed_only:
            sql += " AND bar_status = 'COMPLETE'"
        if start_date is not None:
            sql += " AND trading_date >= ?"
            parameters.append(str(start_date)[:10])
        if end_date is not None:
            sql += " AND trading_date <= ?"
            parameters.append(str(end_date)[:10])
        sql += " ORDER BY trading_date DESC"
        if bars is not None:
            if bars <= 0:
                raise ValueError("bars must be positive")
            sql += " LIMIT ?"
            parameters.append(bars)
        with self.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        if not rows:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        frame = pd.DataFrame([dict(row) for row in reversed(rows)])
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.loc[:, REQUIRED_COLUMNS]

    def coverage(
        self,
        ticker: str,
        *,
        adjustment_convention: str = DEFAULT_ADJUSTMENT,
    ) -> PriceCoverage:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS row_count, MIN(trading_date) AS first_date,
                       MAX(trading_date) AS last_date,
                       SUM(CASE WHEN bar_status='PARTIAL' THEN 1 ELSE 0 END) AS partial_rows
                FROM ohlcv_daily
                WHERE ticker = ? AND adjustment_convention = ?
                """,
                (ticker.strip().upper(), adjustment_convention),
            ).fetchone()
        return PriceCoverage(
            ticker=ticker.strip().upper(),
            row_count=int(row["row_count"] or 0),
            first_date=date.fromisoformat(row["first_date"]) if row["first_date"] else None,
            last_date=date.fromisoformat(row["last_date"]) if row["last_date"] else None,
            partial_rows=int(row["partial_rows"] or 0),
        )

    def revision_count(self, ticker: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM ohlcv_daily_revisions"
        parameters: tuple[object, ...] = ()
        if ticker is not None:
            sql += " WHERE ticker = ?"
            parameters = (ticker.strip().upper(),)
        with self.connection() as connection:
            return int(connection.execute(sql, parameters).fetchone()[0])

    def health(self) -> dict[str, object]:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,
                       MIN(trading_date) AS first_date, MAX(trading_date) AS last_date,
                       SUM(CASE WHEN bar_status='PARTIAL' THEN 1 ELSE 0 END) AS partial_rows
                FROM ohlcv_daily
                """
            ).fetchone()
            batches = int(connection.execute(
                "SELECT COUNT(*) FROM ohlcv_ingest_batches"
            ).fetchone()[0])
            revisions = int(connection.execute(
                "SELECT COUNT(*) FROM ohlcv_daily_revisions"
            ).fetchone()[0])
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "schema": self.validate_schema(),
            "integrity_check": integrity,
            "rows": int(row["rows"] or 0),
            "tickers": int(row["tickers"] or 0),
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "partial_rows": int(row["partial_rows"] or 0),
            "ingest_batches": batches,
            "revisions": revisions,
        }
