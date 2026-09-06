"""SQLite adapter for the domain-owned Decision and Outcome Ledger."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from domain.decision_outcome import (
    EVENT_TYPES,
    LEDGER_AUTHORITY,
    LEDGER_SCHEMA_VERSION,
    LedgerEvent,
    LedgerEventType,
    LedgerInvariantError,
    OutcomePathEvaluation,
    make_ledger_event,
    validate_event_link,
)


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _row_to_event(row: tuple[Any, ...] | None) -> LedgerEvent | None:
    if not row:
        return None
    values = list(row)
    values[6] = json.loads(values[6])
    return LedgerEvent(*values)


class DecisionOutcomeLedger:
    """Append-only persistence; it records decisions and never makes them."""

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
                CREATE INDEX IF NOT EXISTS ix_ledger_run_type
                    ON ledger_events(run_id, event_type, ticker);
                CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
                    BEFORE UPDATE ON ledger_events
                    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
                    BEFORE DELETE ON ledger_events
                    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
                """
            )

    @staticmethod
    def _select_fields() -> str:
        return (
            "event_id,event_type,occurred_at_utc,run_id,ticker,"
            "thesis_id,payload_json,validation_event_id,previous_event_id,"
            "schema_version"
        )

    def get_event(self, event_id: str) -> LedgerEvent | None:
        self.initialise()
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {self._select_fields()} FROM ledger_events WHERE event_id=?",
                (str(event_id or "").strip(),),
            ).fetchone()
        return _row_to_event(row)

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
                    raise RuntimeError(
                        "ledger event identity has different immutable content"
                    )
                return False
            if event.previous_event_id:
                prior_row = connection.execute(
                    f"SELECT {self._select_fields()} FROM ledger_events WHERE event_id=?",
                    (event.previous_event_id,),
                ).fetchone()
                previous = _row_to_event(prior_row)
                if previous is None:
                    raise LedgerInvariantError(
                        "previous_event_id is not present in the ledger"
                    )
                validate_event_link(previous, event)
            connection.execute(
                "INSERT INTO ledger_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.event_id,
                    event.schema_version,
                    event.event_type,
                    event.occurred_at_utc,
                    datetime.now(timezone.utc).isoformat(),
                    event.run_id,
                    event.ticker,
                    event.thesis_id,
                    event.validation_event_id,
                    event.previous_event_id,
                    event.payload_hash,
                    payload_json,
                ),
            )
        return True

    def append_many(self, events: Iterable[LedgerEvent]) -> int:
        return sum(1 for event in events if self.append(event))

    def latest_event(
        self, thesis_id: str, event_type: str | None = None
    ) -> LedgerEvent | None:
        self.initialise()
        params: list[str] = [str(thesis_id or "").strip()]
        predicate = "thesis_id=?"
        if event_type:
            predicate += " AND event_type=?"
            params.append(str(event_type).strip().upper())
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                f"SELECT {self._select_fields()} FROM ledger_events "
                f"WHERE {predicate} "
                "ORDER BY occurred_at_utc DESC,recorded_at_utc DESC,event_id DESC LIMIT 1",
                params,
            ).fetchone()
        return _row_to_event(row)

    def latest_validation(self, thesis_id: str) -> LedgerEvent | None:
        return self.latest_event(thesis_id, LedgerEventType.VALIDATION.value)

    def events_for_thesis(self, thesis_id: str) -> tuple[LedgerEvent, ...]:
        self.initialise()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT {self._select_fields()} FROM ledger_events "
                "WHERE thesis_id=? "
                "ORDER BY occurred_at_utc,recorded_at_utc,event_id",
                (str(thesis_id or "").strip(),),
            ).fetchall()
        return tuple(_row_to_event(row) for row in rows if row)

    def events_by_type(self, event_type: str) -> tuple[LedgerEvent, ...]:
        normalised = str(event_type or "").strip().upper()
        if normalised not in EVENT_TYPES:
            raise LedgerInvariantError(f"unsupported ledger event type: {event_type}")
        self.initialise()
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                f"SELECT {self._select_fields()} FROM ledger_events "
                "WHERE event_type=? "
                "ORDER BY occurred_at_utc,recorded_at_utc,event_id",
                (normalised,),
            ).fetchall()
        return tuple(_row_to_event(row) for row in rows if row)

    def event_counts(self, run_id: str | None = None) -> dict[str, int]:
        self.initialise()
        query = "SELECT event_type,COUNT(*) FROM ledger_events"
        params: tuple[str, ...] = ()
        if run_id:
            query += " WHERE run_id=?"
            params = (str(run_id).strip(),)
        query += " GROUP BY event_type ORDER BY event_type"
        with sqlite3.connect(self.database_path) as connection:
            return {
                str(event_type): int(count)
                for event_type, count in connection.execute(query, params).fetchall()
            }


def _row_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    ticker = str(row.get("ticker") or "").strip().upper()
    thesis_id = str(row.get("thesis_id") or "").strip()
    if not ticker or not thesis_id:
        raise LedgerInvariantError(
            "decision ledger rows require governed ticker and thesis_id"
        )
    return ticker, thesis_id


def _first_present(row: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def candidate_events_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_id: str,
    occurred_at_utc: str,
    decision_stage: str | None = None,
) -> tuple[LedgerEvent, ...]:
    events: list[LedgerEvent] = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw)
        ticker, thesis_id = _row_identity(row)
        key = f"{ticker}|{thesis_id}"
        if key in seen:
            raise LedgerInvariantError(f"duplicate candidate ledger identity: {key}")
        seen.add(key)
        payload = {
            "decision_stage": str(
                decision_stage or row.get("pipeline_mode") or "UNSPECIFIED"
            ).strip().upper(),
            "direction": row.get("governed_direction") or row.get("direction"),
            "direction_decision_id": row.get("direction_decision_id"),
            "trade_idea_id": row.get("trade_idea_id"),
            "selected_structure_id": row.get("selected_structure_id"),
            "selected_contract_symbol": row.get("selected_contract_symbol"),
            "selected_quote_snapshot_id": row.get("selected_quote_snapshot_id"),
            "thesis_state": row.get("thesis_state"),
            "final_action": row.get("final_action"),
            "execution_eligibility_state": row.get("execution_eligibility_state"),
            "final_capital_permission": (
                row.get("final_capital_permission") or row.get("capital_permission")
            ),
            "drop_reason": row.get("drop_reason") or row.get("rejection_reason"),
            "completed_session": (
                row.get("completed_session") or row.get("evidence_session_date")
            ),
            "reference_price": (
                row.get("completed_close")
                or row.get("signal_price")
                or row.get("underlying_price")
            ),
            "target_price": row.get("target_spot") or row.get("target_price"),
            "invalidation_price": (
                row.get("invalidation_spot") or row.get("invalidation_price")
            ),
            "planned_hold_sessions": row.get("planned_hold_sessions"),
            "evidence_dataset_ids": row.get("evidence_dataset_ids"),
            "formula_version": row.get("calculation_version"),
        }
        events.append(make_ledger_event(
            event_type=LedgerEventType.CANDIDATE_DECISION.value,
            occurred_at_utc=occurred_at_utc,
            run_id=run_id,
            ticker=ticker,
            thesis_id=thesis_id,
            payload=payload,
        ))
    return tuple(events)


def execution_events_from_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_id: str,
    occurred_at_utc: str,
    validation_events_by_ticker: Mapping[str, LedgerEvent] | None = None,
) -> tuple[LedgerEvent, ...]:
    """Record both executable and rejected decisions after the final gate."""

    validation_index = {
        str(key).strip().upper(): value
        for key, value in (validation_events_by_ticker or {}).items()
    }
    events: list[LedgerEvent] = []
    seen: set[str] = set()
    for raw in rows:
        row = dict(raw)
        ticker, thesis_id = _row_identity(row)
        key = f"{ticker}|{thesis_id}"
        if key in seen:
            raise LedgerInvariantError(f"duplicate execution ledger identity: {key}")
        seen.add(key)
        validation = validation_index.get(ticker)
        if validation is not None and validation.thesis_id != thesis_id:
            validation = None
        validation_id = str(
            row.get("validation_event_id")
            or (validation.validation_event_id if validation else "")
            or ""
        ).strip() or None
        payload = {
            "decision_stage": "FINAL_EXECUTION_GATE",
            "direction": row.get("governed_direction") or row.get("direction"),
            "selected_contract_symbol": row.get("selected_contract_symbol"),
            "selected_quote_snapshot_id": row.get("selected_quote_snapshot_id"),
            "final_action": row.get("final_action"),
            "execution_eligibility_state": row.get("execution_eligibility_state"),
            "execution_authority_source": row.get("execution_authority_source"),
            "execution_authority_policy_version": row.get(
                "execution_authority_policy_version"
            ),
            "final_capital_permission": (
                row.get("final_capital_permission") or row.get("capital_permission")
            ),
            "execution_requires_human_approval": row.get(
                "execution_requires_human_approval"
            ),
            "execution_authorized": row.get("execution_authorized"),
            "decision_reason": row.get("gate_reason") or row.get("rejection_reason"),
        }
        events.append(make_ledger_event(
            event_type=LedgerEventType.EXECUTION_DECISION.value,
            occurred_at_utc=occurred_at_utc,
            run_id=run_id,
            ticker=ticker,
            thesis_id=thesis_id,
            validation_event_id=validation_id,
            previous_event_id=validation.event_id if validation else None,
            payload=payload,
        ))
    return tuple(events)


def outcome_event_from_trade(
    trade: Mapping[str, Any],
    *,
    occurred_at_utc: str,
    previous_event_id: str | None = None,
) -> LedgerEvent:
    """Translate a realised trade result without fabricating absent path data."""

    ticker = str(trade.get("ticker") or "").strip().upper()
    run_id = str(trade.get("run_id") or "").strip()
    thesis_id = str(
        trade.get("thesis_id") or trade.get("trade_idea_id") or ""
    ).strip()
    if not ticker or not run_id or not thesis_id:
        raise LedgerInvariantError(
            "outcome requires ticker, run_id and governed thesis/trade idea identity"
        )
    payload = {
        "trade_id": trade.get("trade_id"),
        "direction": trade.get("governed_direction") or trade.get("options_direction"),
        "contract_symbol": (
            trade.get("selected_contract_symbol") or trade.get("contract_symbol")
        ),
        "entry_date": trade.get("entry_date"),
        "exit_date": trade.get("exit_date"),
        "entry_premium": trade.get("entry_premium"),
        "exit_premium": trade.get("exit_premium"),
        "pnl_usd": trade.get("pnl_usd"),
        "pnl_pct_premium": trade.get("pnl_pct_premium"),
        "pnl_r_multiple": _first_present(trade, "pnl_r_multiple", "rr_realised"),
        "mfe": trade.get("mfe"),
        "mae": trade.get("mae"),
        "days_held": _first_present(trade, "days_held", "hold_days"),
        "target_first_hit_session": trade.get("target_first_hit_session"),
        "stop_first_hit_session": trade.get("stop_first_hit_session"),
        "exit_reason": trade.get("exit_reason"),
        "outcome_class": trade.get("outcome_class"),
        "outcome_horizon_sessions": trade.get("outcome_horizon_sessions"),
        "is_counterfactual": _as_bool(trade.get("is_counterfactual", False)),
        "data_status": trade.get("data_status") or "OBSERVED_TRADE_EXIT",
    }
    return make_ledger_event(
        event_type=LedgerEventType.OUTCOME.value,
        occurred_at_utc=occurred_at_utc,
        run_id=run_id,
        ticker=ticker,
        thesis_id=thesis_id,
        previous_event_id=previous_event_id,
        payload=payload,
    )


def outcome_event_from_candidate(
    candidate: LedgerEvent,
    evaluation: OutcomePathEvaluation,
    *,
    occurred_at_utc: str,
) -> LedgerEvent:
    """Create a comparable outcome for an accepted, deferred or rejected idea."""

    if candidate.event_type != LedgerEventType.CANDIDATE_DECISION.value:
        raise LedgerInvariantError("counterfactual outcome requires a candidate event")
    payload = {
        **evaluation.to_dict(),
        "direction": candidate.payload.get("direction"),
        "original_final_action": candidate.payload.get("final_action"),
        "original_drop_reason": candidate.payload.get("drop_reason"),
        "selected_contract_symbol": candidate.payload.get(
            "selected_contract_symbol"
        ),
        "is_counterfactual": True,
    }
    return make_ledger_event(
        event_type=LedgerEventType.OUTCOME.value,
        occurred_at_utc=occurred_at_utc,
        run_id=candidate.run_id,
        ticker=candidate.ticker,
        thesis_id=candidate.thesis_id,
        previous_event_id=candidate.event_id,
        payload=payload,
    )


__all__ = [
    "DecisionOutcomeLedger",
    "EVENT_TYPES",
    "LEDGER_AUTHORITY",
    "LEDGER_SCHEMA_VERSION",
    "LedgerEvent",
    "LedgerEventType",
    "LedgerInvariantError",
    "candidate_events_from_rows",
    "execution_events_from_rows",
    "make_ledger_event",
    "outcome_event_from_candidate",
    "outcome_event_from_trade",
]
