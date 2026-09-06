"""Append-only option-thesis and liquidity-monitoring persistence.

This module extends the existing CDS control-plane database.  It deliberately
does not create a second database and it never fetches provider data itself.
Callers use ``should_fetch`` to decide whether the governed MarketData option
chain adapter should be invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import sqlite3
from typing import Any, Mapping

from .contracts import DatasetType, iso_utc, parse_utc, utc_now
from .errors import DatasetValidationError
from .registry import CanonicalRegistry
from domain.thesis_direction import ThesisState, TERMINAL_THESIS_STATES
from domain.option_contract_liquidity import (
    ContractLiquidityState,
    MonitorState,
    decide_contract_quote_fetch,
    validate_contract_replacement,
)


OPTION_LIQUIDITY_SCHEMA_VERSION = "option_liquidity_lifecycle_v2"
LEGACY_OPTION_LIQUIDITY_SCHEMA_VERSION = "option_liquidity_lifecycle_v1"
MARKETDATA_PROVIDER = "MARKETDATA"


class OptionLifecycleError(RuntimeError):
    """Base error for the option-liquidity lifecycle store."""


class OptionLifecycleConflict(OptionLifecycleError):
    """Raised when an immutable event key is reused with different content."""


class OptionLifecycleConcurrencyError(OptionLifecycleError):
    """Raised when a caller appends from a stale lifecycle version."""


MONITORABLE_LIQUIDITY_STATES = frozenset(
    {
        ContractLiquidityState.REVIEWABLE_SPREAD,
        ContractLiquidityState.LIQUIDITY_PENDING,
        ContractLiquidityState.QUOTE_STALE,
        ContractLiquidityState.ZERO_BID,
        ContractLiquidityState.NO_DISPLAYED_SIZE,
        ContractLiquidityState.NO_CURRENT_MARKET,
    }
)
TERMINAL_LIQUIDITY_STATES = frozenset(
    {
        ContractLiquidityState.DTE_UNSUITABLE,
        ContractLiquidityState.MONEYNESS_UNSUITABLE,
        ContractLiquidityState.THESIS_TARGET_UNREACHABLE,
        ContractLiquidityState.TERMINAL_REJECT,
    }
)


@dataclass(frozen=True, slots=True)
class ThesisLifecycleEvent:
    event_id: str
    event_key: str
    thesis_id: str
    run_id: str
    ticker: str
    direction: str
    thesis_state: ThesisState
    monitor_state: MonitorState
    reason_code: str
    structural_target: float | None
    invalidation_spot: float | None
    horizon_end_date: date | None
    version: int
    recorded_at: datetime
    metadata: Mapping[str, Any]
    calculation_version: str
    supersedes_event_id: str | None
    correction_reason: str | None
    corrected_by_run_id: str | None
    correction_state: str | None


@dataclass(frozen=True, slots=True)
class ContractObservation:
    observation_id: str
    thesis_id: str
    run_id: str
    ticker: str
    contract_symbol: str
    option_side: str
    quote_as_of: datetime
    observed_at: datetime
    source_provider: str
    source_dataset_id: str
    spot: float
    strike: float
    expiration: date
    dte: float
    delta: float | None
    bid: float | None
    ask: float | None
    bid_size: float | None
    ask_size: float | None
    spread_pct: float | None
    volume: float | None
    open_interest: float | None
    iv: float | None
    liquidity_state: ContractLiquidityState
    maturation_score_1d: float | None
    maturation_score_2d: float | None
    maturation_score_3d: float | None
    maturation_score_is_probability: bool
    maturation_probability_1d: float | None
    maturation_probability_2d: float | None
    maturation_probability_3d: float | None
    atm_distance_sigma: float | None
    remaining_runway_pct: float | None
    payload_hash: str
    calculation_version: str
    supersedes_event_id: str | None
    correction_reason: str | None
    corrected_by_run_id: str | None
    correction_state: str | None


@dataclass(frozen=True, slots=True)
class ContractSelectionEvent:
    selection_event_id: str
    event_key: str
    thesis_id: str
    run_id: str
    previous_contract_symbol: str | None
    selected_contract_symbol: str
    selected_observation_id: str
    selection_reason: str
    selection_version: int
    economics_recomputed: bool
    selected_at: datetime
    metadata: Mapping[str, Any]
    calculation_version: str
    supersedes_event_id: str | None
    correction_reason: str | None
    corrected_by_run_id: str | None
    correction_state: str | None


@dataclass(frozen=True, slots=True)
class PersistResult:
    record: ThesisLifecycleEvent | ContractObservation | ContractSelectionEvent
    reused_existing: bool


@dataclass(frozen=True, slots=True)
class FetchDecision:
    should_fetch: bool
    reason: str
    provider: str | None
    latest_observation: ContractObservation | None


@dataclass(frozen=True, slots=True)
class MonitorWorkItem:
    thesis: ThesisLifecycleEvent
    latest_observation: ContractObservation | None
    fetch_decision: FetchDecision


def _normalise_token(value: str, field_name: str) -> str:
    token = str(value).strip().upper()
    if not token:
        raise DatasetValidationError(f"{field_name} is required")
    return token


def _required_text(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise DatasetValidationError(f"{field_name} is required")
    return text


def _normalise_direction(value: str) -> str:
    direction = _normalise_token(value, "direction")
    if direction not in {"CALL", "PUT"}:
        raise DatasetValidationError("direction must be CALL or PUT")
    return direction


def _finite_optional(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DatasetValidationError(f"{field_name} must be finite")
    return parsed


def _non_negative_optional(value: float | int | None, field_name: str) -> float | None:
    parsed = _finite_optional(value, field_name)
    if parsed is not None and parsed < 0:
        raise DatasetValidationError(f"{field_name} cannot be negative")
    return parsed


def _probability(value: float | int | None, field_name: str) -> float | None:
    parsed = _finite_optional(value, field_name)
    if parsed is not None and not 0.0 <= parsed <= 1.0:
        raise DatasetValidationError(f"{field_name} must be between 0 and 1")
    return parsed


def _deterministic_score(value: float | int | None, field_name: str) -> float | None:
    """Validate the lifecycle prioritisation scale without calling it probability."""
    parsed = _finite_optional(value, field_name)
    if parsed is not None and not 0.0 <= parsed <= 100.0:
        raise DatasetValidationError(f"{field_name} must be between 0 and 100")
    return parsed


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(*values: str) -> str:
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _correction_lineage(
    *,
    calculation_version: str | None,
    supersedes_event_id: str | None,
    correction_reason: str | None,
    corrected_by_run_id: str | None,
    correction_state: str | None,
) -> tuple[str, str | None, str | None, str | None, str | None]:
    """Normalise an append-only correction link and reject partial lineage."""
    version = _required_text(
        calculation_version or OPTION_LIQUIDITY_SCHEMA_VERSION,
        "calculation_version",
    )
    supersedes = str(supersedes_event_id).strip() if supersedes_event_id else None
    reason = str(correction_reason).strip().upper() if correction_reason else None
    corrected_run = (
        _normalise_token(corrected_by_run_id, "corrected_by_run_id")
        if corrected_by_run_id else None
    )
    state = str(correction_state).strip().upper() if correction_state else None
    correction_values = (supersedes, reason, corrected_run, state)
    if any(correction_values) and not all(correction_values):
        raise DatasetValidationError(
            "supersession requires supersedes_event_id, correction_reason, "
            "corrected_by_run_id and correction_state"
        )
    return version, supersedes, reason, corrected_run, state


class OptionLiquidityLifecycleStore:
    """Append-only liquidity lifecycle using an existing CDS registry."""

    def __init__(self, registry: CanonicalRegistry):
        self.registry = registry

    def initialise(self) -> None:
        self.registry.initialise()
        with self.registry.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS option_thesis_events (
                    event_id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
                    thesis_state TEXT NOT NULL,
                    monitor_state TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    structural_target REAL,
                    invalidation_spot REAL,
                    horizon_end_date TEXT,
                    version INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    calculation_version TEXT NOT NULL DEFAULT 'option_liquidity_lifecycle_v1',
                    supersedes_event_id TEXT,
                    correction_reason TEXT,
                    corrected_by_run_id TEXT,
                    correction_state TEXT,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    UNIQUE(thesis_id, version),
                    UNIQUE(thesis_id, event_key)
                );

                CREATE INDEX IF NOT EXISTS idx_option_thesis_latest
                    ON option_thesis_events(thesis_id, version DESC);
                CREATE INDEX IF NOT EXISTS idx_option_thesis_ticker
                    ON option_thesis_events(ticker, recorded_at DESC);

                CREATE TABLE IF NOT EXISTS option_contract_observations (
                    observation_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    contract_symbol TEXT NOT NULL,
                    option_side TEXT NOT NULL CHECK(option_side IN ('CALL','PUT')),
                    quote_as_of TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    source_provider TEXT NOT NULL CHECK(source_provider = 'MARKETDATA'),
                    source_dataset_id TEXT NOT NULL,
                    spot REAL NOT NULL CHECK(spot > 0),
                    strike REAL NOT NULL CHECK(strike > 0),
                    expiration TEXT NOT NULL,
                    dte REAL NOT NULL CHECK(dte >= 0),
                    delta REAL,
                    bid REAL,
                    ask REAL,
                    bid_size REAL,
                    ask_size REAL,
                    spread_pct REAL,
                    volume REAL,
                    open_interest REAL,
                    iv REAL,
                    liquidity_state TEXT NOT NULL,
                    maturation_score_1d REAL,
                    maturation_score_2d REAL,
                    maturation_score_3d REAL,
                    maturation_score_is_probability INTEGER NOT NULL DEFAULT 0
                        CHECK(maturation_score_is_probability = 0),
                    maturation_probability_1d REAL,
                    maturation_probability_2d REAL,
                    maturation_probability_3d REAL,
                    atm_distance_sigma REAL,
                    remaining_runway_pct REAL,
                    calculation_version TEXT NOT NULL DEFAULT 'option_liquidity_lifecycle_v1',
                    supersedes_event_id TEXT,
                    correction_reason TEXT,
                    corrected_by_run_id TEXT,
                    correction_state TEXT,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(source_dataset_id) REFERENCES dataset_registry(dataset_id),
                    UNIQUE(thesis_id, run_id, contract_symbol, quote_as_of)
                );

                CREATE INDEX IF NOT EXISTS idx_option_observation_latest
                    ON option_contract_observations(
                        thesis_id, quote_as_of DESC, observed_at DESC
                    );
                CREATE INDEX IF NOT EXISTS idx_option_observation_contract
                    ON option_contract_observations(contract_symbol, quote_as_of DESC);

                CREATE TABLE IF NOT EXISTS option_contract_selection_events (
                    selection_event_id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    previous_contract_symbol TEXT,
                    selected_contract_symbol TEXT NOT NULL,
                    selected_observation_id TEXT NOT NULL,
                    selection_reason TEXT NOT NULL,
                    selection_version INTEGER NOT NULL,
                    economics_recomputed INTEGER NOT NULL CHECK(economics_recomputed IN (0,1)),
                    selected_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    calculation_version TEXT NOT NULL DEFAULT 'option_liquidity_lifecycle_v1',
                    supersedes_event_id TEXT,
                    correction_reason TEXT,
                    corrected_by_run_id TEXT,
                    correction_state TEXT,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(selected_observation_id)
                        REFERENCES option_contract_observations(observation_id),
                    UNIQUE(thesis_id, selection_version),
                    UNIQUE(thesis_id, event_key)
                );

                CREATE INDEX IF NOT EXISTS idx_option_selection_latest
                    ON option_contract_selection_events(
                        thesis_id, selection_version DESC
                    );

                CREATE TRIGGER IF NOT EXISTS trg_option_thesis_no_update
                BEFORE UPDATE ON option_thesis_events
                BEGIN
                    SELECT RAISE(ABORT, 'option thesis events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_option_thesis_no_delete
                BEFORE DELETE ON option_thesis_events
                BEGIN
                    SELECT RAISE(ABORT, 'option thesis events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_option_observation_no_update
                BEFORE UPDATE ON option_contract_observations
                BEGIN
                    SELECT RAISE(ABORT, 'option observations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_option_observation_no_delete
                BEFORE DELETE ON option_contract_observations
                BEGIN
                    SELECT RAISE(ABORT, 'option observations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_option_selection_no_update
                BEFORE UPDATE ON option_contract_selection_events
                BEGIN
                    SELECT RAISE(ABORT, 'option selections are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_option_selection_no_delete
                BEFORE DELETE ON option_contract_selection_events
                BEGIN
                    SELECT RAISE(ABORT, 'option selections are append-only');
                END;
                """
            )
            # Existing v1 databases are migrated additively.  No event is
            # updated or deleted; legacy rows retain an explicit v1 version.
            for table in (
                "option_thesis_events",
                "option_contract_observations",
                "option_contract_selection_events",
            ):
                existing_columns = {
                    row["name"]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                additions = {
                    "calculation_version": (
                        "TEXT NOT NULL DEFAULT 'option_liquidity_lifecycle_v1'"
                    ),
                    "supersedes_event_id": "TEXT",
                    "correction_reason": "TEXT",
                    "corrected_by_run_id": "TEXT",
                    "correction_state": "TEXT",
                }
                for column, declaration in additions.items():
                    if column not in existing_columns:
                        connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                        )
            connection.execute(
                "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) "
                "VALUES (?, ?)",
                (OPTION_LIQUIDITY_SCHEMA_VERSION, iso_utc(utc_now())),
            )

    @staticmethod
    def _thesis_from_row(row: sqlite3.Row) -> ThesisLifecycleEvent:
        return ThesisLifecycleEvent(
            event_id=row["event_id"],
            event_key=row["event_key"],
            thesis_id=row["thesis_id"],
            run_id=row["run_id"],
            ticker=row["ticker"],
            direction=row["direction"],
            thesis_state=ThesisState(row["thesis_state"]),
            monitor_state=MonitorState(row["monitor_state"]),
            reason_code=row["reason_code"],
            structural_target=row["structural_target"],
            invalidation_spot=row["invalidation_spot"],
            horizon_end_date=date.fromisoformat(row["horizon_end_date"])
            if row["horizon_end_date"]
            else None,
            version=int(row["version"]),
            recorded_at=parse_utc(row["recorded_at"]),
            metadata=json.loads(row["metadata_json"]),
            calculation_version=row["calculation_version"],
            supersedes_event_id=row["supersedes_event_id"],
            correction_reason=row["correction_reason"],
            corrected_by_run_id=row["corrected_by_run_id"],
            correction_state=row["correction_state"],
        )

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> ContractObservation:
        return ContractObservation(
            observation_id=row["observation_id"],
            thesis_id=row["thesis_id"],
            run_id=row["run_id"],
            ticker=row["ticker"],
            contract_symbol=row["contract_symbol"],
            option_side=row["option_side"],
            quote_as_of=parse_utc(row["quote_as_of"]),
            observed_at=parse_utc(row["observed_at"]),
            source_provider=row["source_provider"],
            source_dataset_id=row["source_dataset_id"],
            spot=float(row["spot"]),
            strike=float(row["strike"]),
            expiration=date.fromisoformat(row["expiration"]),
            dte=float(row["dte"]),
            delta=row["delta"],
            bid=row["bid"],
            ask=row["ask"],
            bid_size=row["bid_size"],
            ask_size=row["ask_size"],
            spread_pct=row["spread_pct"],
            volume=row["volume"],
            open_interest=row["open_interest"],
            iv=row["iv"],
            liquidity_state=ContractLiquidityState(row["liquidity_state"]),
            maturation_score_1d=row["maturation_score_1d"],
            maturation_score_2d=row["maturation_score_2d"],
            maturation_score_3d=row["maturation_score_3d"],
            maturation_score_is_probability=bool(
                row["maturation_score_is_probability"]
            ),
            maturation_probability_1d=row["maturation_probability_1d"],
            maturation_probability_2d=row["maturation_probability_2d"],
            maturation_probability_3d=row["maturation_probability_3d"],
            atm_distance_sigma=row["atm_distance_sigma"],
            remaining_runway_pct=row["remaining_runway_pct"],
            payload_hash=row["payload_hash"],
            calculation_version=row["calculation_version"],
            supersedes_event_id=row["supersedes_event_id"],
            correction_reason=row["correction_reason"],
            corrected_by_run_id=row["corrected_by_run_id"],
            correction_state=row["correction_state"],
        )

    @staticmethod
    def _selection_from_row(row: sqlite3.Row) -> ContractSelectionEvent:
        return ContractSelectionEvent(
            selection_event_id=row["selection_event_id"],
            event_key=row["event_key"],
            thesis_id=row["thesis_id"],
            run_id=row["run_id"],
            previous_contract_symbol=row["previous_contract_symbol"],
            selected_contract_symbol=row["selected_contract_symbol"],
            selected_observation_id=row["selected_observation_id"],
            selection_reason=row["selection_reason"],
            selection_version=int(row["selection_version"]),
            economics_recomputed=bool(row["economics_recomputed"]),
            selected_at=parse_utc(row["selected_at"]),
            metadata=json.loads(row["metadata_json"]),
            calculation_version=row["calculation_version"],
            supersedes_event_id=row["supersedes_event_id"],
            correction_reason=row["correction_reason"],
            corrected_by_run_id=row["corrected_by_run_id"],
            correction_state=row["correction_state"],
        )

    def latest_thesis(self, thesis_id: str) -> ThesisLifecycleEvent | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM option_thesis_events
                WHERE thesis_id = ? ORDER BY version DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._thesis_from_row(row) if row else None

    def latest_observation(self, thesis_id: str) -> ContractObservation | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM option_contract_observations
                WHERE thesis_id = ?
                ORDER BY quote_as_of DESC, observed_at DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._observation_from_row(row) if row else None

    def latest_selection(self, thesis_id: str) -> ContractSelectionEvent | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM option_contract_selection_events
                WHERE thesis_id = ? ORDER BY selection_version DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._selection_from_row(row) if row else None

    def record_thesis_event(
        self,
        *,
        thesis_id: str,
        event_key: str,
        run_id: str,
        ticker: str,
        direction: str,
        thesis_state: ThesisState,
        monitor_state: MonitorState,
        reason_code: str,
        structural_target: float | None = None,
        invalidation_spot: float | None = None,
        horizon_end_date: date | None = None,
        expected_version: int | None = None,
        recorded_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
        calculation_version: str | None = None,
        supersedes_event_id: str | None = None,
        correction_reason: str | None = None,
        corrected_by_run_id: str | None = None,
        correction_state: str | None = None,
    ) -> PersistResult:
        thesis = _normalise_token(thesis_id, "thesis_id")
        key = _normalise_token(event_key, "event_key")
        run = _normalise_token(run_id, "run_id")
        symbol = _normalise_token(ticker, "ticker")
        side = _normalise_direction(direction)
        reason = _normalise_token(reason_code, "reason_code")
        target = _finite_optional(structural_target, "structural_target")
        invalidation = _finite_optional(invalidation_spot, "invalidation_spot")
        instant = parse_utc(recorded_at) or utc_now()
        meta_json = _canonical_json(dict(metadata or {}))
        calc_version, supersedes, correction, corrected_run, correction_status = (
            _correction_lineage(
                calculation_version=calculation_version,
                supersedes_event_id=supersedes_event_id,
                correction_reason=correction_reason,
                corrected_by_run_id=corrected_by_run_id,
                correction_state=correction_state,
            )
        )
        if corrected_run and corrected_run != run:
            raise DatasetValidationError("corrected_by_run_id must equal the writing run_id")
        if thesis_state in TERMINAL_THESIS_STATES and monitor_state is not MonitorState.TERMINAL:
            raise DatasetValidationError("terminal thesis state requires monitor_state TERMINAL")
        if thesis_state not in TERMINAL_THESIS_STATES and monitor_state is MonitorState.TERMINAL:
            raise DatasetValidationError("active thesis cannot have terminal monitoring")

        event_id = _hash("OPTION_THESIS_EVENT_V1", thesis, key)
        payload = {
            "event_id": event_id,
            "event_key": key,
            "thesis_id": thesis,
            "run_id": run,
            "ticker": symbol,
            "direction": side,
            "thesis_state": thesis_state.value,
            "monitor_state": monitor_state.value,
            "reason_code": reason,
            "structural_target": target,
            "invalidation_spot": invalidation,
            "horizon_end_date": horizon_end_date.isoformat() if horizon_end_date else None,
            "recorded_at": iso_utc(instant),
            "metadata_json": meta_json,
            "calculation_version": calc_version,
            "supersedes_event_id": supersedes,
            "correction_reason": correction,
            "corrected_by_run_id": corrected_run,
            "correction_state": correction_status,
        }
        hash_payload = dict(payload)
        hash_payload.pop("recorded_at")
        payload_hash = _hash(
            "OPTION_THESIS_PAYLOAD_V1", _canonical_json(hash_payload)
        )

        with self.registry.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM option_thesis_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict(
                        f"event_key {key} already has different immutable content"
                    )
                return PersistResult(self._thesis_from_row(existing), True)

            latest_row = connection.execute(
                "SELECT * FROM option_thesis_events WHERE thesis_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (thesis,),
            ).fetchone()
            if supersedes:
                superseded_row = connection.execute(
                    "SELECT event_id FROM option_thesis_events WHERE event_id = ?",
                    (supersedes,),
                ).fetchone()
                if superseded_row is None:
                    raise DatasetValidationError("supersedes_event_id does not exist")
                if supersedes == event_id:
                    raise DatasetValidationError("an event cannot supersede itself")
            if latest_row:
                latest = self._thesis_from_row(latest_row)
                if latest.thesis_state in TERMINAL_THESIS_STATES:
                    raise OptionLifecycleConflict("terminal thesis cannot be reactivated")
                if expected_version is None or expected_version != latest.version:
                    raise OptionLifecycleConcurrencyError(
                        f"expected thesis version {expected_version}, found {latest.version}"
                    )
                if latest.ticker != symbol or latest.direction != side:
                    raise OptionLifecycleConflict(
                        "ticker and direction are immutable for an existing thesis"
                    )
                version = latest.version + 1
            else:
                if expected_version not in {None, 0}:
                    raise OptionLifecycleConcurrencyError(
                        f"expected thesis version {expected_version}, found 0"
                    )
                version = 1

            try:
                connection.execute(
                    """
                    INSERT INTO option_thesis_events(
                        event_id, event_key, thesis_id, run_id, ticker, direction,
                        thesis_state, monitor_state, reason_code, structural_target,
                        invalidation_spot, horizon_end_date, version, recorded_at,
                        metadata_json, calculation_version, supersedes_event_id,
                        correction_reason, corrected_by_run_id, correction_state,
                        payload_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id, key, thesis, run, symbol, side,
                        thesis_state.value, monitor_state.value, reason, target,
                        invalidation,
                        horizon_end_date.isoformat() if horizon_end_date else None,
                        version, iso_utc(instant), meta_json, calc_version,
                        supersedes, correction, corrected_run, correction_status,
                        payload_hash,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error

        result = self.latest_thesis(thesis)
        assert result is not None
        return PersistResult(result, False)

    def record_contract_observation(
        self,
        *,
        thesis_id: str,
        run_id: str,
        ticker: str,
        contract_symbol: str,
        option_side: str,
        quote_as_of: datetime,
        source_dataset_id: str,
        spot: float,
        strike: float,
        expiration: date,
        dte: float,
        liquidity_state: ContractLiquidityState,
        source_provider: str = MARKETDATA_PROVIDER,
        observed_at: datetime | None = None,
        delta: float | None = None,
        bid: float | None = None,
        ask: float | None = None,
        bid_size: float | None = None,
        ask_size: float | None = None,
        spread_pct: float | None = None,
        volume: float | None = None,
        open_interest: float | None = None,
        iv: float | None = None,
        maturation_score_1d: float | None = None,
        maturation_score_2d: float | None = None,
        maturation_score_3d: float | None = None,
        maturation_score_is_probability: bool = False,
        maturation_probability_1d: float | None = None,
        maturation_probability_2d: float | None = None,
        maturation_probability_3d: float | None = None,
        atm_distance_sigma: float | None = None,
        remaining_runway_pct: float | None = None,
        calculation_version: str | None = None,
        supersedes_event_id: str | None = None,
        correction_reason: str | None = None,
        corrected_by_run_id: str | None = None,
        correction_state: str | None = None,
    ) -> PersistResult:
        thesis = _normalise_token(thesis_id, "thesis_id")
        run = _normalise_token(run_id, "run_id")
        symbol = _normalise_token(ticker, "ticker")
        contract = _normalise_token(contract_symbol, "contract_symbol")
        side = _normalise_direction(option_side)
        provider = _normalise_token(source_provider, "source_provider")
        dataset_id = _required_text(source_dataset_id, "source_dataset_id")
        if provider != MARKETDATA_PROVIDER:
            raise DatasetValidationError("options provenance must be MARKETDATA")
        if maturation_score_is_probability:
            raise DatasetValidationError(
                "OLM-v1 maturation scores are deterministic, not probabilities"
            )
        if any(
            value is not None
            for value in (
                maturation_probability_1d,
                maturation_probability_2d,
                maturation_probability_3d,
            )
        ):
            raise DatasetValidationError(
                "maturation_probability fields are reserved until a calibrated model exists"
            )
        quote_time = parse_utc(quote_as_of)
        if quote_time is None:
            raise DatasetValidationError("quote_as_of is required")
        observed = parse_utc(observed_at) or utc_now()
        calc_version, supersedes, correction, corrected_run, correction_status = (
            _correction_lineage(
                calculation_version=calculation_version,
                supersedes_event_id=supersedes_event_id,
                correction_reason=correction_reason,
                corrected_by_run_id=corrected_by_run_id,
                correction_state=correction_state,
            )
        )
        if corrected_run and corrected_run != run:
            raise DatasetValidationError("corrected_by_run_id must equal the writing run_id")
        spot_value = _non_negative_optional(spot, "spot")
        strike_value = _non_negative_optional(strike, "strike")
        dte_value = _non_negative_optional(dte, "dte")
        if spot_value in {None, 0} or strike_value in {None, 0}:
            raise DatasetValidationError("spot and strike must be greater than zero")

        values = {
            "delta": _finite_optional(delta, "delta"),
            "bid": _non_negative_optional(bid, "bid"),
            "ask": _non_negative_optional(ask, "ask"),
            "bid_size": _non_negative_optional(bid_size, "bid_size"),
            "ask_size": _non_negative_optional(ask_size, "ask_size"),
            "spread_pct": _non_negative_optional(spread_pct, "spread_pct"),
            "volume": _non_negative_optional(volume, "volume"),
            "open_interest": _non_negative_optional(open_interest, "open_interest"),
            "iv": _non_negative_optional(iv, "iv"),
            "maturation_score_1d": _deterministic_score(
                maturation_score_1d, "maturation_score_1d"
            ),
            "maturation_score_2d": _deterministic_score(
                maturation_score_2d, "maturation_score_2d"
            ),
            "maturation_score_3d": _deterministic_score(
                maturation_score_3d, "maturation_score_3d"
            ),
            "maturation_score_is_probability": False,
            "maturation_probability_1d": None,
            "maturation_probability_2d": None,
            "maturation_probability_3d": None,
            "atm_distance_sigma": _non_negative_optional(
                atm_distance_sigma, "atm_distance_sigma"
            ),
            "remaining_runway_pct": _non_negative_optional(
                remaining_runway_pct, "remaining_runway_pct"
            ),
        }
        if values["bid"] is not None and values["ask"] is not None:
            if values["ask"] < values["bid"]:
                raise DatasetValidationError("ask cannot be below bid")

        latest_thesis = self.latest_thesis(thesis)
        if latest_thesis is None:
            raise DatasetValidationError(f"unknown thesis_id {thesis}")
        if latest_thesis.ticker != symbol or latest_thesis.direction != side:
            raise DatasetValidationError("observation does not match thesis ticker/direction")
        if latest_thesis.thesis_state in TERMINAL_THESIS_STATES:
            raise DatasetValidationError("cannot observe a terminal thesis")

        source_record = self.registry.get_dataset(dataset_id)
        if source_record is None:
            raise DatasetValidationError(f"unknown source_dataset_id {dataset_id}")
        if source_record.dataset_type not in {
            DatasetType.OPTION_CHAIN,
            DatasetType.LIVE_OPTION,
            DatasetType.EXACT_OPTION_QUOTE,
        }:
            raise DatasetValidationError("source dataset is not canonical option data")
        if source_record.provider != MARKETDATA_PROVIDER:
            raise DatasetValidationError("source option-chain dataset is not MARKETDATA")
        if source_record.instrument_id != symbol:
            raise DatasetValidationError("source dataset ticker does not match observation")

        observation_id = _hash(
            "OPTION_CONTRACT_OBSERVATION_V1",
            thesis,
            run,
            contract,
            iso_utc(quote_time) or "",
        )
        payload = {
            "observation_id": observation_id,
            "thesis_id": thesis,
            "run_id": run,
            "ticker": symbol,
            "contract_symbol": contract,
            "option_side": side,
            "quote_as_of": iso_utc(quote_time),
            "observed_at": iso_utc(observed),
            "source_provider": provider,
            "source_dataset_id": dataset_id,
            "spot": spot_value,
            "strike": strike_value,
            "expiration": expiration.isoformat(),
            "dte": dte_value,
            "liquidity_state": liquidity_state.value,
            "calculation_version": calc_version,
            "supersedes_event_id": supersedes,
            "correction_reason": correction,
            "corrected_by_run_id": corrected_run,
            "correction_state": correction_status,
            **values,
        }
        hash_payload = dict(payload)
        hash_payload.pop("observed_at")
        payload_hash = _hash(
            "OPTION_OBSERVATION_PAYLOAD_V1", _canonical_json(hash_payload)
        )

        with self.registry.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM option_contract_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    # A provider may return the same unchanged option quote on a
                    # later Morning pass while the independently captured
                    # underlying spot has moved.  The natural identity of this
                    # table is the provider's contract quote timestamp, so that
                    # is a replay of one market observation, not a second quote.
                    # Reuse it only when all option-quote facts agree.  Any
                    # changed quote content under the same provider timestamp
                    # remains an immutable-content conflict and fails closed.
                    comparable_fields = (
                        # DTE is deliberately excluded: EOD may persist the
                        # provider/trading-session convention while Morning
                        # derives calendar DTE from the same quote timestamp.
                        "strike", "expiration", "delta", "bid", "ask",
                        "bid_size", "ask_size", "spread_pct", "volume",
                        "open_interest", "iv",
                    )

                    def _same_value(left: Any, right: Any) -> bool:
                        if left is None or right is None:
                            return left is None and right is None
                        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                            return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
                        return str(left) == str(right)

                    if all(
                        _same_value(existing[field], payload[field])
                        for field in comparable_fields
                    ):
                        return PersistResult(self._observation_from_row(existing), True)
                    raise OptionLifecycleConflict(
                        "contract quote identity already has different immutable content"
                    )
                return PersistResult(self._observation_from_row(existing), True)
            if supersedes:
                superseded_row = connection.execute(
                    "SELECT observation_id FROM option_contract_observations "
                    "WHERE observation_id = ?",
                    (supersedes,),
                ).fetchone()
                if superseded_row is None:
                    raise DatasetValidationError("supersedes_event_id does not exist")
                if supersedes == observation_id:
                    raise DatasetValidationError("an observation cannot supersede itself")
            try:
                connection.execute(
                    """
                    INSERT INTO option_contract_observations(
                        observation_id, thesis_id, run_id, ticker, contract_symbol,
                        option_side, quote_as_of, observed_at, source_provider,
                        source_dataset_id, spot, strike, expiration, dte, delta,
                        bid, ask, bid_size, ask_size, spread_pct, volume,
                        open_interest, iv, liquidity_state,
                        maturation_score_1d, maturation_score_2d,
                        maturation_score_3d, maturation_score_is_probability,
                        maturation_probability_1d, maturation_probability_2d,
                        maturation_probability_3d, atm_distance_sigma,
                        remaining_runway_pct, calculation_version,
                        supersedes_event_id, correction_reason,
                        corrected_by_run_id, correction_state, payload_hash
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        observation_id, thesis, run, symbol, contract, side,
                        iso_utc(quote_time), iso_utc(observed), provider, dataset_id,
                        spot_value, strike_value, expiration.isoformat(), dte_value,
                        values["delta"], values["bid"], values["ask"],
                        values["bid_size"], values["ask_size"], values["spread_pct"],
                        values["volume"], values["open_interest"], values["iv"],
                        liquidity_state.value,
                        values["maturation_score_1d"],
                        values["maturation_score_2d"],
                        values["maturation_score_3d"],
                        int(values["maturation_score_is_probability"]),
                        values["maturation_probability_1d"],
                        values["maturation_probability_2d"],
                        values["maturation_probability_3d"],
                        values["atm_distance_sigma"], values["remaining_runway_pct"],
                        calc_version, supersedes, correction, corrected_run,
                        correction_status,
                        payload_hash,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error

        result = self.latest_observation(thesis)
        assert result is not None
        return PersistResult(result, False)

    def record_selection_event(
        self,
        *,
        thesis_id: str,
        event_key: str,
        run_id: str,
        selected_contract_symbol: str,
        selected_observation_id: str,
        selection_reason: str,
        previous_contract_symbol: str | None = None,
        economics_recomputed: bool,
        expected_version: int | None = None,
        selected_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
        calculation_version: str | None = None,
        supersedes_event_id: str | None = None,
        correction_reason: str | None = None,
        corrected_by_run_id: str | None = None,
        correction_state: str | None = None,
    ) -> PersistResult:
        thesis = _normalise_token(thesis_id, "thesis_id")
        key = _normalise_token(event_key, "event_key")
        run = _normalise_token(run_id, "run_id")
        selected = _normalise_token(selected_contract_symbol, "selected_contract_symbol")
        observation_id = _required_text(
            selected_observation_id, "selected_observation_id"
        )
        previous = (
            _normalise_token(previous_contract_symbol, "previous_contract_symbol")
            if previous_contract_symbol
            else None
        )
        reason = _normalise_token(selection_reason, "selection_reason")
        instant = parse_utc(selected_at) or utc_now()
        meta_json = _canonical_json(dict(metadata or {}))
        calc_version, supersedes, correction, corrected_run, correction_status = (
            _correction_lineage(
                calculation_version=calculation_version,
                supersedes_event_id=supersedes_event_id,
                correction_reason=correction_reason,
                corrected_by_run_id=corrected_by_run_id,
                correction_state=correction_state,
            )
        )
        if corrected_run and corrected_run != run:
            raise DatasetValidationError("corrected_by_run_id must equal the writing run_id")
        try:
            validate_contract_replacement(
                previous_contract_symbol=previous,
                selected_contract_symbol=selected,
                economics_recomputed=economics_recomputed,
            )
        except ValueError as error:
            raise DatasetValidationError(str(error)) from error

        with self.registry.connection() as connection:
            observation_row = connection.execute(
                "SELECT * FROM option_contract_observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
            if observation_row is None:
                raise DatasetValidationError("selected observation does not exist")
            observation = self._observation_from_row(observation_row)
            if observation.thesis_id != thesis or observation.run_id != run:
                raise DatasetValidationError(
                    "selected observation must belong to the thesis and run"
                )
            try:
                validate_contract_replacement(
                    previous_contract_symbol=previous,
                    selected_contract_symbol=selected,
                    economics_recomputed=economics_recomputed,
                    observed_contract_symbol=observation.contract_symbol,
                )
            except ValueError as error:
                raise DatasetValidationError(str(error)) from error

            selection_event_id = _hash("OPTION_SELECTION_EVENT_V1", thesis, key)
            payload = {
                "selection_event_id": selection_event_id,
                "event_key": key,
                "thesis_id": thesis,
                "run_id": run,
                "previous_contract_symbol": previous,
                "selected_contract_symbol": selected,
                "selected_observation_id": observation_id,
                "selection_reason": reason,
                "economics_recomputed": bool(economics_recomputed),
                "selected_at": iso_utc(instant),
                "metadata_json": meta_json,
                "calculation_version": calc_version,
                "supersedes_event_id": supersedes,
                "correction_reason": correction,
                "corrected_by_run_id": corrected_run,
                "correction_state": correction_status,
            }
            hash_payload = dict(payload)
            hash_payload.pop("selected_at")
            payload_hash = _hash(
                "OPTION_SELECTION_PAYLOAD_V1", _canonical_json(hash_payload)
            )
            existing = connection.execute(
                "SELECT * FROM option_contract_selection_events "
                "WHERE selection_event_id = ?",
                (selection_event_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict(
                        f"selection event_key {key} has different immutable content"
                    )
                return PersistResult(self._selection_from_row(existing), True)
            if supersedes:
                superseded_row = connection.execute(
                    "SELECT selection_event_id FROM option_contract_selection_events "
                    "WHERE selection_event_id = ?",
                    (supersedes,),
                ).fetchone()
                if superseded_row is None:
                    raise DatasetValidationError("supersedes_event_id does not exist")
                if supersedes == selection_event_id:
                    raise DatasetValidationError("a selection cannot supersede itself")

            latest_row = connection.execute(
                "SELECT * FROM option_contract_selection_events "
                "WHERE thesis_id = ? ORDER BY selection_version DESC LIMIT 1",
                (thesis,),
            ).fetchone()
            if latest_row:
                latest = self._selection_from_row(latest_row)
                if expected_version is None or expected_version != latest.selection_version:
                    raise OptionLifecycleConcurrencyError(
                        "expected selection version "
                        f"{expected_version}, found {latest.selection_version}"
                    )
                version = latest.selection_version + 1
            else:
                if expected_version not in {None, 0}:
                    raise OptionLifecycleConcurrencyError(
                        f"expected selection version {expected_version}, found 0"
                    )
                version = 1

            try:
                connection.execute(
                    """
                    INSERT INTO option_contract_selection_events(
                        selection_event_id, event_key, thesis_id, run_id,
                        previous_contract_symbol, selected_contract_symbol,
                        selected_observation_id, selection_reason, selection_version,
                        economics_recomputed, selected_at, metadata_json,
                        calculation_version, supersedes_event_id, correction_reason,
                        corrected_by_run_id, correction_state, payload_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        selection_event_id, key, thesis, run, previous, selected,
                        observation_id, reason, version, int(economics_recomputed),
                        iso_utc(instant), meta_json, calc_version, supersedes,
                        correction, corrected_run, correction_status, payload_hash,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error

        result = self.latest_selection(thesis)
        assert result is not None
        return PersistResult(result, False)

    def should_fetch(
        self,
        thesis_id: str,
        *,
        freshness_seconds: int,
        now: datetime | None = None,
    ) -> FetchDecision:
        if freshness_seconds < 0:
            raise DatasetValidationError("freshness_seconds cannot be negative")
        instant = parse_utc(now) or utc_now()
        thesis = self.latest_thesis(thesis_id)
        if thesis is None:
            return FetchDecision(False, "THESIS_NOT_FOUND", None, None)
        latest = self.latest_observation(thesis.thesis_id)
        age_seconds = (
            (instant - latest.quote_as_of).total_seconds() if latest is not None else None
        )
        try:
            policy = decide_contract_quote_fetch(
                thesis_state=thesis.thesis_state,
                monitor_state=thesis.monitor_state,
                horizon_end_date=thesis.horizon_end_date,
                current_date=instant.date(),
                latest_liquidity_state=(latest.liquidity_state if latest else None),
                latest_quote_age_seconds=age_seconds,
                freshness_seconds=freshness_seconds,
            )
        except ValueError as error:
            raise DatasetValidationError(str(error)) from error
        return FetchDecision(
            policy.should_fetch,
            policy.reason,
            MARKETDATA_PROVIDER if policy.should_fetch else None,
            latest,
        )

    def active_monitor_worklist(
        self,
        *,
        freshness_seconds: int,
        now: datetime | None = None,
    ) -> tuple[MonitorWorkItem, ...]:
        instant = parse_utc(now) or utc_now()
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT event.* FROM option_thesis_events AS event
                JOIN (
                    SELECT thesis_id, MAX(version) AS max_version
                    FROM option_thesis_events GROUP BY thesis_id
                ) AS latest
                  ON latest.thesis_id = event.thesis_id
                 AND latest.max_version = event.version
                WHERE event.monitor_state = ?
                ORDER BY event.ticker, event.thesis_id
                """,
                (MonitorState.ACTIVE.value,),
            ).fetchall()
        items: list[MonitorWorkItem] = []
        for row in rows:
            thesis = self._thesis_from_row(row)
            decision = self.should_fetch(
                thesis.thesis_id, freshness_seconds=freshness_seconds, now=instant
            )
            if thesis.thesis_state in TERMINAL_THESIS_STATES:
                continue
            if thesis.horizon_end_date and instant.date() > thesis.horizon_end_date:
                continue
            if decision.reason == "FRESH_EXECUTABLE_CONTRACT":
                continue
            items.append(
                MonitorWorkItem(
                    thesis=thesis,
                    latest_observation=decision.latest_observation,
                    fetch_decision=decision,
                )
            )
        return tuple(items)
