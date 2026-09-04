"""Ticker lifecycle and stage-worklist authority for fetch suppression."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import sqlite3
from typing import Iterable

from .contracts import DatasetType, iso_utc, parse_utc, utc_now
from .errors import IllegalLifecycleTransition, LifecycleConcurrencyError
from .registry import CanonicalRegistry


class LifecycleState(str, Enum):
    ACTIVE_DISCOVERY = "ACTIVE_DISCOVERY"
    ACTIVE_CORE = "ACTIVE_CORE"
    ACTIVE_OPTIONS = "ACTIVE_OPTIONS"
    ACTIVE_EQUITY_ONLY = "ACTIVE_EQUITY_ONLY"
    ACTIVE_MORNING = "ACTIVE_MORNING"
    DEFERRED_CURRENT_RUN = "DEFERRED_CURRENT_RUN"
    DROPPED_STAGE = "DROPPED_STAGE"
    DROPPED_TERMINAL_DATA = "DROPPED_TERMINAL_DATA"
    DROPPED_TERMINAL_LOGIC = "DROPPED_TERMINAL_LOGIC"
    COMPLETED = "COMPLETED"


class DropClass(str, Enum):
    NONE = "NONE"
    STAGE = "STAGE"
    TERMINAL_DATA = "TERMINAL_DATA"
    TERMINAL_LOGIC = "TERMINAL_LOGIC"
    DEFERRED = "DEFERRED"


ACTIVE_STATES = {
    LifecycleState.ACTIVE_DISCOVERY,
    LifecycleState.ACTIVE_CORE,
    LifecycleState.ACTIVE_OPTIONS,
    LifecycleState.ACTIVE_EQUITY_ONLY,
    LifecycleState.ACTIVE_MORNING,
}
TERMINAL_STATES = {
    LifecycleState.DROPPED_TERMINAL_DATA,
    LifecycleState.DROPPED_TERMINAL_LOGIC,
    LifecycleState.COMPLETED,
}

LEGAL_TRANSITIONS: dict[LifecycleState, set[LifecycleState]] = {
    LifecycleState.ACTIVE_DISCOVERY: {
        LifecycleState.ACTIVE_DISCOVERY,
        LifecycleState.ACTIVE_CORE,
        LifecycleState.DROPPED_STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.DEFERRED_CURRENT_RUN,
        LifecycleState.COMPLETED,
    },
    LifecycleState.ACTIVE_CORE: {
        LifecycleState.ACTIVE_CORE,
        LifecycleState.ACTIVE_OPTIONS,
        LifecycleState.ACTIVE_EQUITY_ONLY,
        LifecycleState.ACTIVE_MORNING,
        LifecycleState.DROPPED_STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.DEFERRED_CURRENT_RUN,
        LifecycleState.COMPLETED,
    },
    LifecycleState.ACTIVE_OPTIONS: {
        LifecycleState.ACTIVE_OPTIONS,
        LifecycleState.ACTIVE_MORNING,
        LifecycleState.DROPPED_STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.DEFERRED_CURRENT_RUN,
        LifecycleState.COMPLETED,
    },
    LifecycleState.ACTIVE_EQUITY_ONLY: {
        LifecycleState.ACTIVE_EQUITY_ONLY,
        LifecycleState.ACTIVE_MORNING,
        LifecycleState.DROPPED_STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.DEFERRED_CURRENT_RUN,
        LifecycleState.COMPLETED,
    },
    LifecycleState.ACTIVE_MORNING: {
        LifecycleState.ACTIVE_MORNING,
        LifecycleState.DROPPED_STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.COMPLETED,
    },
    LifecycleState.DROPPED_STAGE: {
        LifecycleState.ACTIVE_CORE,
        LifecycleState.ACTIVE_OPTIONS,
        LifecycleState.ACTIVE_EQUITY_ONLY,
        LifecycleState.ACTIVE_MORNING,
        LifecycleState.DROPPED_TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC,
        LifecycleState.COMPLETED,
    },
    LifecycleState.DEFERRED_CURRENT_RUN: set(),
    LifecycleState.DROPPED_TERMINAL_DATA: set(),
    LifecycleState.DROPPED_TERMINAL_LOGIC: set(),
    LifecycleState.COMPLETED: set(),
}


@dataclass(frozen=True, slots=True)
class TickerLifecycleEvent:
    run_id: str
    ticker: str
    state: LifecycleState
    drop_class: DropClass
    stage: str
    reason_code: str
    allowed_capabilities: tuple[DatasetType, ...]
    version: int
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class AuthorisationDecision:
    authorised: bool
    reason: str
    event: TickerLifecycleEvent | None


@dataclass(frozen=True, slots=True)
class WorklistReconciliation:
    stage: str
    dataset_type: DatasetType
    expected: tuple[str, ...]
    actual: tuple[str, ...]
    missing: tuple[str, ...]
    unexpected: tuple[str, ...]

    @property
    def reconciled(self) -> bool:
        return not self.missing and not self.unexpected


def _default_drop_class(state: LifecycleState) -> DropClass:
    return {
        LifecycleState.DROPPED_STAGE: DropClass.STAGE,
        LifecycleState.DROPPED_TERMINAL_DATA: DropClass.TERMINAL_DATA,
        LifecycleState.DROPPED_TERMINAL_LOGIC: DropClass.TERMINAL_LOGIC,
        LifecycleState.DEFERRED_CURRENT_RUN: DropClass.DEFERRED,
    }.get(state, DropClass.NONE)


class LifecycleManager:
    def __init__(self, registry: CanonicalRegistry):
        self.registry = registry

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> TickerLifecycleEvent:
        return TickerLifecycleEvent(
            run_id=row["run_id"],
            ticker=row["ticker"],
            state=LifecycleState(row["state"]),
            drop_class=DropClass(row["drop_class"]),
            stage=row["stage"],
            reason_code=row["reason_code"],
            allowed_capabilities=tuple(
                DatasetType(value)
                for value in json.loads(row["allowed_capabilities_json"])
            ),
            version=int(row["version"]),
            recorded_at=parse_utc(row["recorded_at"]),
        )

    def latest(self, run_id: str, ticker: str) -> TickerLifecycleEvent | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM ticker_lifecycle
                WHERE run_id = ? AND ticker = ?
                ORDER BY version DESC LIMIT 1
                """,
                (run_id, ticker.strip().upper()),
            ).fetchone()
        return self._event_from_row(row) if row else None

    def register(
        self,
        run_id: str,
        ticker: str,
        *,
        stage: str = "DISCOVERY",
        allowed_capabilities: Iterable[DatasetType] = (),
    ) -> TickerLifecycleEvent:
        if self.latest(run_id, ticker) is not None:
            raise IllegalLifecycleTransition(f"{ticker} is already registered in {run_id}")
        return self._insert(
            run_id,
            ticker,
            LifecycleState.ACTIVE_DISCOVERY,
            DropClass.NONE,
            stage,
            "REGISTERED",
            tuple(allowed_capabilities),
            1,
        )

    def transition(
        self,
        run_id: str,
        ticker: str,
        new_state: LifecycleState,
        *,
        stage: str,
        reason_code: str = "",
        allowed_capabilities: Iterable[DatasetType] | None = None,
        expected_version: int | None = None,
        explicit_reactivation: bool = False,
    ) -> TickerLifecycleEvent:
        previous = self.latest(run_id, ticker)
        if previous is None:
            raise IllegalLifecycleTransition(f"{ticker} is not registered in {run_id}")
        if expected_version is not None and previous.version != expected_version:
            raise LifecycleConcurrencyError(
                f"expected lifecycle version {expected_version}, found {previous.version}"
            )

        if new_state == LifecycleState.ACTIVE_DISCOVERY and previous.state in (
            TERMINAL_STATES | {LifecycleState.DEFERRED_CURRENT_RUN}
        ):
            if not explicit_reactivation or not reason_code.strip():
                raise IllegalLifecycleTransition(
                    "terminal/deferred ticker requires explicit, reasoned reactivation"
                )
        elif new_state not in LEGAL_TRANSITIONS[previous.state]:
            raise IllegalLifecycleTransition(
                f"illegal transition {previous.state.value} -> {new_state.value}"
            )

        drop_class = _default_drop_class(new_state)
        if drop_class is not DropClass.NONE and not reason_code.strip():
            raise IllegalLifecycleTransition("drop/defer transition requires reason_code")
        capabilities = (
            tuple(allowed_capabilities)
            if allowed_capabilities is not None
            else previous.allowed_capabilities
        )
        return self._insert(
            run_id,
            ticker,
            new_state,
            drop_class,
            stage,
            reason_code,
            capabilities,
            previous.version + 1,
        )

    def _insert(
        self,
        run_id: str,
        ticker: str,
        state: LifecycleState,
        drop_class: DropClass,
        stage: str,
        reason_code: str,
        capabilities: tuple[DatasetType, ...],
        version: int,
    ) -> TickerLifecycleEvent:
        normalised_ticker = ticker.strip().upper()
        recorded_at = utc_now()
        with self.registry.connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO ticker_lifecycle(
                        run_id, ticker, state, drop_class, stage, reason_code,
                        allowed_capabilities_json, version, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        normalised_ticker,
                        state.value,
                        drop_class.value,
                        stage.strip().upper(),
                        reason_code.strip().upper(),
                        json.dumps(sorted(capability.value for capability in capabilities)),
                        version,
                        iso_utc(recorded_at),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise LifecycleConcurrencyError(str(error)) from error
        return self.latest(run_id, normalised_ticker)  # type: ignore[return-value]

    def authorise(
        self, run_id: str, stage: str, ticker: str, dataset_type: DatasetType
    ) -> AuthorisationDecision:
        event = self.latest(run_id, ticker)
        if event is None:
            return AuthorisationDecision(False, "TICKER_NOT_REGISTERED", None)
        if event.state not in ACTIVE_STATES:
            return AuthorisationDecision(
                False, f"STATE_{event.state.value}_BLOCKS_FETCH", event
            )
        requested_stage = stage.strip().upper()
        if event.stage != requested_stage:
            return AuthorisationDecision(
                False, f"STAGE_MISMATCH_CURRENT_{event.stage}", event
            )
        if (
            event.allowed_capabilities
            and dataset_type not in event.allowed_capabilities
        ):
            return AuthorisationDecision(False, "CAPABILITY_NOT_AUTHORISED", event)
        return AuthorisationDecision(True, "AUTHORISED", event)

    def create_worklist(
        self,
        run_id: str,
        stage: str,
        dataset_type: DatasetType,
        tickers: Iterable[str],
    ) -> tuple[str, ...]:
        stage_name = stage.strip().upper()
        authorised = self._authorised_tickers(
            run_id, stage_name, dataset_type, tickers
        )
        now = iso_utc(utc_now())
        with self.registry.connection() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO stage_worklist(
                    run_id, stage, ticker, dataset_type, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    (run_id, stage_name, ticker, dataset_type.value, now)
                    for ticker in authorised
                ),
            )
        return authorised

    def _authorised_tickers(
        self,
        run_id: str,
        stage: str,
        dataset_type: DatasetType,
        tickers: Iterable[str],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    ticker.strip().upper()
                    for ticker in tickers
                    if self.authorise(
                        run_id, stage, ticker, dataset_type
                    ).authorised
                }
            )
        )

    def reconcile_worklist(
        self,
        run_id: str,
        stage: str,
        dataset_type: DatasetType,
        candidate_tickers: Iterable[str],
    ) -> WorklistReconciliation:
        stage_name = stage.strip().upper()
        expected = self._authorised_tickers(
            run_id, stage_name, dataset_type, candidate_tickers
        )
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT ticker FROM stage_worklist
                WHERE run_id = ? AND stage = ? AND dataset_type = ?
                ORDER BY ticker
                """,
                (run_id, stage_name, dataset_type.value),
            ).fetchall()
        actual = tuple(row["ticker"] for row in rows)
        return WorklistReconciliation(
            stage=stage_name,
            dataset_type=dataset_type,
            expected=expected,
            actual=actual,
            missing=tuple(sorted(set(expected) - set(actual))),
            unexpected=tuple(sorted(set(actual) - set(expected))),
        )

    def stage_worklist_tickers(
        self,
        run_id: str,
        stage: str,
        dataset_type: DatasetType,
    ) -> tuple[str, ...]:
        """Return the persisted authority set for one stage/capability."""
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT ticker FROM stage_worklist
                WHERE run_id = ? AND stage = ? AND dataset_type = ?
                ORDER BY ticker
                """,
                (run_id, stage.strip().upper(), dataset_type.value),
            ).fetchall()
        return tuple(row["ticker"] for row in rows)

    def is_worklisted(
        self,
        run_id: str,
        stage: str,
        ticker: str,
        dataset_type: DatasetType,
    ) -> bool:
        """Check persisted worklist membership without weakening lifecycle rules."""
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM stage_worklist
                WHERE run_id = ? AND stage = ? AND ticker = ? AND dataset_type = ?
                LIMIT 1
                """,
                (
                    run_id,
                    stage.strip().upper(),
                    ticker.strip().upper(),
                    dataset_type.value,
                ),
            ).fetchone()
        return row is not None

    def authorise_worklist(
        self,
        run_id: str,
        stage: str,
        ticker: str,
        dataset_type: DatasetType,
    ) -> AuthorisationDecision:
        """Require both current lifecycle authority and persisted membership."""
        decision = self.authorise(run_id, stage, ticker, dataset_type)
        if not decision.authorised:
            return decision
        if not self.is_worklisted(run_id, stage, ticker, dataset_type):
            return AuthorisationDecision(
                False,
                "TICKER_NOT_IN_STAGE_WORKLIST",
                decision.event,
            )
        return decision

    def worklist_counts(self, run_id: str) -> dict[str, int]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT stage, COUNT(*) AS count FROM stage_worklist
                WHERE run_id = ? GROUP BY stage ORDER BY stage
                """,
                (run_id,),
            ).fetchall()
        return {row["stage"]: int(row["count"]) for row in rows}
