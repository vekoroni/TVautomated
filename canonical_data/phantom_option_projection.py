"""Idempotent projection of canonical option chains into Phantom history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

import pandas as pd

from domain.data_projection import (
    CanonicalDatasetCommitted,
    PHANTOM_OPTION_CHAIN_PROJECTION,
)

from .contracts import CompletenessStatus, DatasetType
from .option_identity import parse_occ_symbol
from .projection_outbox import ProjectionDeliveryState, ProjectionOutbox
from .registry import CanonicalRegistry


PHANTOM_PROJECTION_SCHEMA_VERSION = "phantom-canonical-option-projection-v1"

_CHAIN_COLUMNS = (
    "ticker", "quote_date", "option_symbol", "underlying", "expiration_ts",
    "side", "strike", "first_traded_ts", "dte", "updated_ts", "bid",
    "bid_size", "mid", "ask", "ask_size", "last", "open_interest",
    "volume", "in_the_money", "intrinsic_value", "extrinsic_value",
    "underlying_price", "iv", "delta", "gamma", "theta", "vega", "source",
    "raw_json", "created_at_utc",
)


@dataclass(frozen=True, slots=True)
class PhantomProjectionResult:
    event_id: str
    dataset_id: str
    ticker: str
    session_date: str
    rows_projected: int
    already_projected: bool


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _finite(value)
    return int(number) if number is not None else None


def _first(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip().upper() not in {"", "NAN", "NONE", "NULL"}:
            return value
    return None


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _epoch_seconds(value: Any) -> int | None:
    number = _finite(value)
    if number is not None:
        absolute = abs(number)
        if absolute >= 1e17:
            number /= 1_000_000_000
        elif absolute >= 1e11:
            number /= 1_000
        return int(number)
    if value is None:
        return None
    try:
        parsed = pd.Timestamp(value)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("UTC")
        else:
            parsed = parsed.tz_convert("UTC")
        return int(parsed.timestamp())
    except Exception:
        return None


def _side(value: Any, *, symbol_side: str) -> str:
    candidate = str(value or symbol_side).strip().upper()
    if candidate in {"C", "CALL"}:
        return "call"
    if candidate in {"P", "PUT"}:
        return "put"
    raise ValueError(f"unsupported option side {value!r}")


def _normalise_row(
    raw: Mapping[str, Any],
    *,
    event: CanonicalDatasetCommitted,
    provider: str,
) -> dict[str, Any]:
    option_symbol = str(_first(raw, "option_symbol", "symbol", "contract_symbol") or "").strip().upper()
    if not option_symbol:
        raise ValueError("canonical option row has no contract symbol")
    identity = parse_occ_symbol(option_symbol)
    ticker = str(_first(raw, "ticker", "underlying") or event.instrument_id).strip().upper()
    if ticker != event.instrument_id:
        raise ValueError(
            f"canonical option row ticker mismatch: {ticker} != {event.instrument_id}"
        )
    expiration = _first(raw, "expiration_ts", "expiration", "expiration_date")
    if expiration is None:
        expiration = datetime(
            identity.expiry.year,
            identity.expiry.month,
            identity.expiry.day,
            tzinfo=timezone.utc,
        )
    quote_time = _first(raw, "updated_ts", "updated", "quote_timestamp_utc")
    canonical_raw = {
        str(key): _json_value(value) for key, value in sorted(raw.items())
    }
    bid = _finite(_first(raw, "bid"))
    ask = _finite(_first(raw, "ask"))
    mid = _finite(_first(raw, "mid"))
    if mid is None and bid is not None and ask is not None and ask >= bid:
        mid = (bid + ask) / 2.0
    row = {
        "ticker": ticker,
        "quote_date": event.session_date.isoformat(),
        "option_symbol": option_symbol,
        "underlying": ticker,
        "expiration_ts": _epoch_seconds(expiration),
        "side": _side(_first(raw, "side", "right"), symbol_side=identity.side),
        "strike": _finite(_first(raw, "strike")) or float(identity.strike),
        "first_traded_ts": _epoch_seconds(_first(raw, "first_traded_ts", "firstTraded")),
        "dte": _finite(_first(raw, "dte")),
        "updated_ts": _epoch_seconds(quote_time),
        "bid": bid,
        "bid_size": _integer(_first(raw, "bid_size", "bidSize")),
        "mid": mid,
        "ask": ask,
        "ask_size": _integer(_first(raw, "ask_size", "askSize")),
        "last": _finite(_first(raw, "last")),
        "open_interest": _integer(_first(raw, "open_interest", "openInterest")),
        "volume": _integer(_first(raw, "volume")),
        "in_the_money": _integer(_first(raw, "in_the_money", "inTheMoney")),
        "intrinsic_value": _finite(_first(raw, "intrinsic_value", "intrinsicValue")),
        "extrinsic_value": _finite(_first(raw, "extrinsic_value", "extrinsicValue")),
        "underlying_price": _finite(_first(raw, "underlying_price", "underlyingPrice")),
        "iv": _finite(_first(raw, "iv", "implied_vol", "impliedVolatility")),
        "delta": _finite(_first(raw, "delta")),
        "gamma": _finite(_first(raw, "gamma")),
        "theta": _finite(_first(raw, "theta")),
        "vega": _finite(_first(raw, "vega")),
        "source": str(_first(raw, "source", "quote_source") or provider),
        "raw_json": json.dumps(canonical_raw, sort_keys=True, separators=(",", ":")),
        "created_at_utc": event.created_at_utc.isoformat(),
    }
    return row


def _ensure_phantom_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS chain_snapshots (
            ticker TEXT NOT NULL,
            quote_date TEXT NOT NULL,
            option_symbol TEXT NOT NULL,
            underlying TEXT,
            expiration_ts INTEGER,
            side TEXT,
            strike REAL,
            first_traded_ts INTEGER,
            dte REAL,
            updated_ts INTEGER,
            bid REAL,
            bid_size INTEGER,
            mid REAL,
            ask REAL,
            ask_size INTEGER,
            last REAL,
            open_interest INTEGER,
            volume INTEGER,
            in_the_money INTEGER,
            intrinsic_value REAL,
            extrinsic_value REAL,
            underlying_price REAL,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            source TEXT,
            raw_json TEXT,
            created_at_utc TEXT,
            PRIMARY KEY (ticker, quote_date, option_symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_chain_ticker_date
            ON chain_snapshots(ticker, quote_date);

        CREATE TABLE IF NOT EXISTS canonical_option_chain_revisions (
            dataset_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quote_date TEXT NOT NULL,
            option_symbol TEXT NOT NULL,
            row_content_hash TEXT NOT NULL,
            row_json TEXT NOT NULL,
            source_run_id TEXT,
            dataset_as_of_utc TEXT NOT NULL,
            projected_at_utc TEXT NOT NULL,
            PRIMARY KEY (dataset_id, option_symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_canonical_chain_revision_lookup
            ON canonical_option_chain_revisions(ticker, quote_date, option_symbol);

        CREATE TABLE IF NOT EXISTS canonical_projection_receipts (
            event_id TEXT PRIMARY KEY,
            projection_name TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            session_date TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            rows_projected INTEGER NOT NULL,
            projected_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS canonical_projection_schema_metadata (
            schema_version TEXT PRIMARY KEY,
            installed_at_utc TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO canonical_projection_schema_metadata"
        "(schema_version, installed_at_utc) VALUES (?, ?)",
        (PHANTOM_PROJECTION_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
    )


class PhantomOptionChainProjector:
    """Project immutable canonical chains into Phantom without losing revisions."""

    def __init__(
        self,
        *,
        registry_path: Path | str,
        phantom_database_path: Path | str,
    ) -> None:
        self.registry = CanonicalRegistry(Path(registry_path))
        self.phantom_database_path = Path(phantom_database_path)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path).to_dict("records")
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("canonical option-chain JSON must contain a row list")
            return [dict(row) for row in payload]
        raise ValueError(f"unsupported canonical option-chain payload: {path.suffix}")

    def project(self, event: CanonicalDatasetCommitted) -> PhantomProjectionResult:
        if event.projection_name != PHANTOM_OPTION_CHAIN_PROJECTION:
            raise ValueError(f"unsupported projection {event.projection_name}")
        if event.dataset_type != DatasetType.OPTION_CHAIN.value:
            raise ValueError("Phantom option projection requires OPTION_CHAIN data")
        record = self.registry.get_dataset(event.dataset_id)
        if record is None:
            raise ValueError(f"canonical dataset not registered: {event.dataset_id}")
        if record.dataset_type is not DatasetType.OPTION_CHAIN:
            raise ValueError("registered dataset is not an option chain")
        if record.completeness_status is not CompletenessStatus.COMPLETE:
            raise ValueError("only complete canonical option chains can enter Phantom")
        if (
            record.instrument_id != event.instrument_id
            or record.session_date != event.session_date
            or record.content_hash != event.content_hash
            or record.storage_uri != event.storage_uri
        ):
            raise ValueError("projection event does not match the canonical registry")
        path = Path(record.storage_uri)
        if not path.is_file() or self._sha256(path) != record.content_hash:
            raise ValueError("canonical option-chain payload failed content-hash verification")
        raw_rows = self._load(path)
        if not raw_rows:
            raise ValueError("canonical option-chain payload is empty")
        rows = [
            _normalise_row(raw, event=event, provider=record.provider)
            for raw in raw_rows
        ]
        symbols = [row["option_symbol"] for row in rows]
        if len(set(symbols)) != len(symbols):
            raise ValueError("canonical option-chain payload contains duplicate contracts")

        self.phantom_database_path.parent.mkdir(parents=True, exist_ok=True)
        projected_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.phantom_database_path, timeout=60) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            _ensure_phantom_schema(connection)
            connection.commit()
            receipt = connection.execute(
                "SELECT dataset_id, rows_projected FROM canonical_projection_receipts WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if receipt is not None:
                if str(receipt[0]) != event.dataset_id:
                    raise ValueError("projection receipt identity conflict")
                return PhantomProjectionResult(
                    event.event_id, event.dataset_id, event.instrument_id,
                    event.session_date.isoformat(), int(receipt[1]), True,
                )
            connection.execute("BEGIN IMMEDIATE")
            try:
                revision_sql = """
                    INSERT INTO canonical_option_chain_revisions(
                        dataset_id, event_id, ticker, quote_date, option_symbol,
                        row_content_hash, row_json, source_run_id,
                        dataset_as_of_utc, projected_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                chain_placeholders = ",".join("?" for _ in _CHAIN_COLUMNS)
                assignments = ",".join(
                    f"{column}=excluded.{column}"
                    for column in _CHAIN_COLUMNS
                    if column not in {"ticker", "quote_date", "option_symbol"}
                )
                chain_sql = (
                    f"INSERT INTO chain_snapshots({','.join(_CHAIN_COLUMNS)}) "
                    f"VALUES({chain_placeholders}) "
                    "ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET "
                    + assignments
                )
                for row in rows:
                    row_json = json.dumps(row, sort_keys=True, separators=(",", ":"))
                    connection.execute(
                        revision_sql,
                        (
                            event.dataset_id, event.event_id, row["ticker"],
                            row["quote_date"], row["option_symbol"],
                            hashlib.sha256(row_json.encode("utf-8")).hexdigest(),
                            row_json, event.source_run_id,
                            event.dataset_as_of_utc.isoformat(), projected_at,
                        ),
                    )
                    connection.execute(
                        chain_sql, tuple(row[column] for column in _CHAIN_COLUMNS)
                    )
                connection.execute(
                    """
                    INSERT INTO canonical_projection_receipts(
                        event_id, projection_name, dataset_id, ticker,
                        session_date, content_hash, rows_projected, projected_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id, event.projection_name, event.dataset_id,
                        event.instrument_id, event.session_date.isoformat(),
                        event.content_hash, len(rows), projected_at,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return PhantomProjectionResult(
            event.event_id, event.dataset_id, event.instrument_id,
            event.session_date.isoformat(), len(rows), False,
        )


def deliver_phantom_option_events(
    *,
    registry_path: Path | str,
    phantom_database_path: Path | str,
    limit: int = 100,
) -> tuple[PhantomProjectionResult, ...]:
    """Deliver pending/retryable Phantom events and retain failures for retry."""

    outbox = ProjectionOutbox(registry_path)
    outbox.requeue_stale_processing()
    projector = PhantomOptionChainProjector(
        registry_path=registry_path,
        phantom_database_path=phantom_database_path,
    )
    results: list[PhantomProjectionResult] = []
    events = outbox.events(
        projection_name=PHANTOM_OPTION_CHAIN_PROJECTION,
        states=(
            ProjectionDeliveryState.PENDING,
            ProjectionDeliveryState.FAILED_RETRYABLE,
        ),
        limit=limit,
    )
    for event in events:
        outbox.mark_processing(event.event_id)
        try:
            result = projector.project(event)
        except Exception as error:
            outbox.mark_failed(event.event_id, f"{type(error).__name__}: {error}")
            continue
        outbox.mark_completed(event.event_id)
        results.append(result)
    return tuple(results)


__all__ = [
    "PHANTOM_PROJECTION_SCHEMA_VERSION",
    "PhantomOptionChainProjector",
    "PhantomProjectionResult",
    "deliver_phantom_option_events",
]
