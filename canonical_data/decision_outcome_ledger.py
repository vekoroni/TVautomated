"""Append-only point-in-time decision, validation and outcome ledger."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


LEDGER_SCHEMA_VERSION = "decision_outcome_ledger_v1"
EVENT_TYPES = frozenset({"CANDIDATE_DECISION", "VALIDATION", "OUTCOME"})


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_id: str
    event_type: str
    occurred_at_utc: str
    run_id: str
    ticker: str
    thesis_id: str
    payload: Mapping[str, Any]
    validation_event_id: str | None = None
    previous_event_id: str | None = None
    schema_version: str = LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.event_type.strip().upper() not in EVENT_TYPES:
            raise ValueError(f"unsupported ledger event type: {self.event_type}")
        for name in ("event_id", "occurred_at_utc", "run_id", "ticker", "thesis_id"):
            if not str(getattr(self, name) or "").strip():
                raise ValueError(f"{name} is required")
        datetime.fromisoformat(self.occurred_at_utc.replace("Z", "+00:00"))
        object.__setattr__(self, "event_type", self.event_type.strip().upper())
        object.__setattr__(self, "ticker", self.ticker.strip().upper())

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(_canonical(dict(self.payload)).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_ledger_event(
    *,
    event_type: str,
    occurred_at_utc: str,
    run_id: str,
    ticker: str,
    thesis_id: str,
    payload: Mapping[str, Any],
    validation_event_id: str | None = None,
    previous_event_id: str | None = None,
) -> LedgerEvent:
    identity = {
        "event_type": event_type.strip().upper(),
        "occurred_at_utc": occurred_at_utc,
        "run_id": run_id,
        "ticker": ticker.strip().upper(),
        "thesis_id": thesis_id,
        "validation_event_id": validation_event_id or "",
        "previous_event_id": previous_event_id or "",
        "payload": dict(payload),
    }
    event_id = "ledger_" + hashlib.sha256(_canonical(identity).encode("utf-8")).hexdigest()
    return LedgerEvent(event_id=event_id, payload=dict(payload), **{
        key: value for key, value in identity.items() if key != "payload"
    })


class DecisionOutcomeLedger:
    """SQLite ledger protected against UPDATE and DELETE operations."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ledger_events(
                    event_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    validation_event_id TEXT,
                    previous_event_id TEXT,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ledger_thesis_time
                    ON ledger_events(thesis_id, occurred_at_utc, event_id);
                CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
                    BEFORE UPDATE ON ledger_events
                    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
                    BEFORE DELETE ON ledger_events
                    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
                """
            )

    def append(self, event: LedgerEvent) -> bool:
        self.initialise()
        payload_json = _canonical(dict(event.payload))
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT payload_hash, payload_json FROM ledger_events WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if existing:
                if existing != (event.payload_hash, payload_json):
                    raise RuntimeError("ledger event identity has different immutable content")
                return False
            connection.execute(
                """INSERT INTO ledger_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.event_id, event.schema_version, event.event_type,
                    event.occurred_at_utc, datetime.now(timezone.utc).isoformat(),
                    event.run_id, event.ticker, event.thesis_id,
                    event.validation_event_id, event.previous_event_id,
                    event.payload_hash, payload_json,
                ),
            )
        return True

    def append_many(self, events: Iterable[LedgerEvent]) -> int:
        return sum(1 for event in events if self.append(event))

    def latest_validation(self, thesis_id: str) -> LedgerEvent | None:
        self.initialise()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """SELECT event_id,event_type,occurred_at_utc,run_id,ticker,
                          thesis_id,payload_json,validation_event_id,previous_event_id,
                          schema_version
                   FROM ledger_events
                   WHERE thesis_id=? AND event_type='VALIDATION'
                   ORDER BY occurred_at_utc DESC,event_id DESC LIMIT 1""",
                (thesis_id,),
            ).fetchone()
        if not row:
            return None
        values = list(row)
        values[6] = json.loads(values[6])
        return LedgerEvent(*values)


def candidate_events_from_rows(
    rows: Iterable[Mapping[str, Any]], *, run_id: str, occurred_at_utc: str
) -> tuple[LedgerEvent, ...]:
    events: list[LedgerEvent] = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw)
        ticker = str(row.get("ticker") or "").strip().upper()
        thesis_id = str(row.get("thesis_id") or "").strip()
        if not ticker or not thesis_id:
            raise ValueError("candidate ledger rows require ticker and thesis_id")
        key = f"{ticker}|{thesis_id}"
        if key in seen:
            raise ValueError(f"duplicate candidate ledger identity: {key}")
        seen.add(key)
        payload = {
            "direction": row.get("governed_direction") or row.get("direction"),
            "selected_contract_symbol": row.get("selected_contract_symbol"),
            "thesis_state": row.get("thesis_state"),
            "final_action": row.get("final_action"),
            "capital_permission": row.get("capital_permission"),
            "drop_reason": row.get("drop_reason") or row.get("rejection_reason"),
        }
        events.append(make_ledger_event(
            event_type="CANDIDATE_DECISION", occurred_at_utc=occurred_at_utc,
            run_id=run_id, ticker=ticker, thesis_id=thesis_id, payload=payload,
        ))
    return tuple(events)


__all__ = [
    "DecisionOutcomeLedger", "EVENT_TYPES", "LEDGER_SCHEMA_VERSION",
    "LedgerEvent", "candidate_events_from_rows", "make_ledger_event",
]
