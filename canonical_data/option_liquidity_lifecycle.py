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
from domain.dynamic_options_intelligence import (
    ContractAssessment,
    ContractEntryState,
    ContractFamily,
    ModelApplicabilityState,
    PreferredContractDecision,
    UnderlyingThesisRef,
)
from domain.dynamic_options_lifecycle import (
    DOIEvaluationPoint,
    DOILifecycleEvent,
    DOIThesisConditionState,
)
from domain.dynamic_options_outcomes import (
    DOIOutcomeLabel,
    OutcomeDataStatus,
    outcome_label_identity,
)


OPTION_LIQUIDITY_SCHEMA_VERSION = "option_liquidity_lifecycle_v3"
LEGACY_OPTION_LIQUIDITY_SCHEMA_VERSION = "option_liquidity_lifecycle_v1"
DOI_LIFECYCLE_SCHEMA_VERSION = "doi_dynamic_lifecycle_v1"
DOI_OUTCOME_SCHEMA_VERSION = "doi_outcome_labels_v1"
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
    record: (
        ThesisLifecycleEvent
        | ContractObservation
        | ContractSelectionEvent
        | ContractFamily
        | ContractAssessment
        | PreferredContractDecision
        | DOILifecycleEvent
        | DOIOutcomeLabel
    )
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

                CREATE TABLE IF NOT EXISTS doi_contract_families (
                    family_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL,
                    thesis_version INTEGER NOT NULL CHECK(thesis_version >= 1),
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    governed_direction TEXT NOT NULL
                        CHECK(governed_direction IN ('CALL','PUT')),
                    origin_spot REAL NOT NULL CHECK(origin_spot > 0),
                    origin_timestamp_utc TEXT NOT NULL,
                    target_spot REAL,
                    invalidation_spot REAL,
                    planned_hold_sessions INTEGER NOT NULL
                        CHECK(planned_hold_sessions BETWEEN 1 AND 20),
                    planned_hold_source TEXT NOT NULL,
                    thesis_evidence_cutoff_utc TEXT NOT NULL,
                    family_policy_version TEXT NOT NULL,
                    evidence_cutoff_utc TEXT NOT NULL,
                    candidate_symbols_json TEXT NOT NULL DEFAULT '[]',
                    source_dataset_ids_json TEXT NOT NULL DEFAULT '[]',
                    family_state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    can_change_direction INTEGER NOT NULL CHECK(can_change_direction = 0),
                    can_invalidate_thesis INTEGER NOT NULL CHECK(can_invalidate_thesis = 0),
                    can_grant_capital INTEGER NOT NULL CHECK(can_grant_capital = 0),
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    UNIQUE(thesis_id, run_id, family_policy_version, evidence_cutoff_utc)
                );

                CREATE INDEX IF NOT EXISTS idx_doi_family_latest
                    ON doi_contract_families(thesis_id, evidence_cutoff_utc DESC);

                CREATE TABLE IF NOT EXISTS doi_contract_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    contract_symbol TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    entry_state TEXT NOT NULL,
                    applicability_state TEXT NOT NULL,
                    evidence_cutoff_utc TEXT NOT NULL,
                    input_dataset_ids_json TEXT NOT NULL,
                    calculation_version TEXT NOT NULL,
                    feature_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    ranking_score_uncalibrated REAL,
                    p_liquidity_1d REAL,
                    p_liquidity_2d REAL,
                    p_liquidity_3d REAL,
                    p_positive_return_before_horizon REAL,
                    p_return_hurdle_before_horizon REAL,
                    p_target_before_invalidation REAL,
                    expected_net_return REAL,
                    expected_downside REAL,
                    expected_time_to_monetisation REAL,
                    model_uncertainty REAL,
                    probabilities_calibrated INTEGER NOT NULL
                        CHECK(probabilities_calibrated IN (0,1)),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    can_change_direction INTEGER NOT NULL CHECK(can_change_direction = 0),
                    can_invalidate_thesis INTEGER NOT NULL CHECK(can_invalidate_thesis = 0),
                    can_grant_capital INTEGER NOT NULL CHECK(can_grant_capital = 0),
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES doi_contract_families(family_id),
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(observation_id)
                        REFERENCES option_contract_observations(observation_id),
                    UNIQUE(family_id, contract_symbol, observation_id, calculation_version)
                );

                CREATE INDEX IF NOT EXISTS idx_doi_assessment_family
                    ON doi_contract_assessments(family_id, contract_symbol);
                CREATE INDEX IF NOT EXISTS idx_doi_assessment_thesis
                    ON doi_contract_assessments(thesis_id, evidence_cutoff_utc DESC);

                CREATE TABLE IF NOT EXISTS doi_preferred_contract_decisions (
                    decision_id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    selected_contract_symbol TEXT NOT NULL,
                    selected_assessment_id TEXT NOT NULL,
                    selection_reason TEXT NOT NULL,
                    selected_at TEXT NOT NULL,
                    alternative_contract_symbols_json TEXT NOT NULL DEFAULT '[]',
                    previous_contract_symbol TEXT,
                    prior_decision_id TEXT,
                    utility_margin REAL,
                    hysteresis_applied INTEGER NOT NULL CHECK(hysteresis_applied IN (0,1)),
                    economics_recomputed INTEGER NOT NULL CHECK(economics_recomputed IN (0,1)),
                    decision_version INTEGER NOT NULL CHECK(decision_version >= 1),
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    execution_authority TEXT NOT NULL CHECK(execution_authority = 'HUMAN_ONLY'),
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES doi_contract_families(family_id),
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(selected_assessment_id)
                        REFERENCES doi_contract_assessments(assessment_id),
                    FOREIGN KEY(prior_decision_id)
                        REFERENCES doi_preferred_contract_decisions(decision_id),
                    UNIQUE(thesis_id, event_key),
                    UNIQUE(thesis_id, decision_version)
                );

                CREATE INDEX IF NOT EXISTS idx_doi_preferred_latest
                    ON doi_preferred_contract_decisions(
                        thesis_id, decision_version DESC
                    );

                CREATE TABLE IF NOT EXISTS doi_lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    event_key TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    thesis_version INTEGER NOT NULL CHECK(thesis_version >= 1),
                    family_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    evaluation_point TEXT NOT NULL,
                    condition_state TEXT NOT NULL,
                    previous_condition_state TEXT,
                    evidence_cutoff_utc TEXT NOT NULL,
                    current_spot REAL,
                    target_spot REAL,
                    invalidation_spot REAL,
                    horizon_end_date TEXT,
                    material_change INTEGER NOT NULL CHECK(material_change IN (0,1)),
                    material_reasons_json TEXT NOT NULL DEFAULT '[]',
                    recorded_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    retain_opportunity INTEGER NOT NULL CHECK(retain_opportunity = 1),
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    can_change_direction INTEGER NOT NULL CHECK(can_change_direction = 0),
                    can_grant_capital INTEGER NOT NULL CHECK(can_grant_capital = 0),
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(family_id) REFERENCES doi_contract_families(family_id),
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    UNIQUE(thesis_id, event_key)
                );

                CREATE INDEX IF NOT EXISTS idx_doi_lifecycle_latest
                    ON doi_lifecycle_events(thesis_id, evidence_cutoff_utc DESC, recorded_at DESC);

                CREATE TABLE IF NOT EXISTS doi_outcome_labels (
                    label_id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL,
                    family_id TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    contract_symbol TEXT NOT NULL,
                    original_observation_id TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
                    horizon_sessions INTEGER NOT NULL CHECK(horizon_sessions > 0),
                    assessment_cutoff_utc TEXT NOT NULL,
                    outcome_cutoff_utc TEXT NOT NULL,
                    horizon_end_session TEXT,
                    data_status TEXT NOT NULL CHECK(data_status IN (
                        'COMPLETE',
                        'COMPLETE_OPTION_PATH_PARTIAL',
                        'COMPLETE_OPTION_RETURN_UNAVAILABLE',
                        'DEFERRED_NOT_YET_OBSERVABLE',
                        'DATA_EXCEPTION'
                    )),
                    calculation_version TEXT NOT NULL,
                    outcome_kind TEXT NOT NULL CHECK(outcome_kind = 'HYPOTHETICAL_MARKET_PATH'),
                    is_counterfactual INTEGER NOT NULL CHECK(is_counterfactual = 1),
                    uses_realised_fills INTEGER NOT NULL CHECK(uses_realised_fills = 0),
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    can_change_direction INTEGER NOT NULL CHECK(can_change_direction = 0),
                    can_grant_capital INTEGER NOT NULL CHECK(can_grant_capital = 0),
                    can_close_position INTEGER NOT NULL CHECK(can_close_position = 0),
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    FOREIGN KEY(assessment_id) REFERENCES doi_contract_assessments(assessment_id),
                    FOREIGN KEY(family_id) REFERENCES doi_contract_families(family_id),
                    FOREIGN KEY(run_id) REFERENCES run_registry(run_id),
                    FOREIGN KEY(original_observation_id)
                        REFERENCES option_contract_observations(observation_id),
                    UNIQUE(
                        assessment_id, horizon_sessions, outcome_cutoff_utc,
                        calculation_version, data_status
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_doi_outcome_assessment
                    ON doi_outcome_labels(
                        assessment_id, horizon_sessions, outcome_cutoff_utc DESC
                    );
                CREATE INDEX IF NOT EXISTS idx_doi_outcome_cohort
                    ON doi_outcome_labels(
                        data_status, assessment_cutoff_utc, outcome_cutoff_utc
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
                CREATE TRIGGER IF NOT EXISTS trg_doi_family_no_update
                BEFORE UPDATE ON doi_contract_families
                BEGIN
                    SELECT RAISE(ABORT, 'DOI contract families are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_family_no_delete
                BEFORE DELETE ON doi_contract_families
                BEGIN
                    SELECT RAISE(ABORT, 'DOI contract families are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_assessment_no_update
                BEFORE UPDATE ON doi_contract_assessments
                BEGIN
                    SELECT RAISE(ABORT, 'DOI contract assessments are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_assessment_no_delete
                BEFORE DELETE ON doi_contract_assessments
                BEGIN
                    SELECT RAISE(ABORT, 'DOI contract assessments are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_preferred_no_update
                BEFORE UPDATE ON doi_preferred_contract_decisions
                BEGIN
                    SELECT RAISE(ABORT, 'DOI preferred decisions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_preferred_no_delete
                BEFORE DELETE ON doi_preferred_contract_decisions
                BEGIN
                    SELECT RAISE(ABORT, 'DOI preferred decisions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_lifecycle_no_update
                BEFORE UPDATE ON doi_lifecycle_events
                BEGIN
                    SELECT RAISE(ABORT, 'DOI lifecycle events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_lifecycle_no_delete
                BEFORE DELETE ON doi_lifecycle_events
                BEGIN
                    SELECT RAISE(ABORT, 'DOI lifecycle events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_outcome_no_update
                BEFORE UPDATE ON doi_outcome_labels
                BEGIN
                    SELECT RAISE(ABORT, 'DOI outcome labels are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_outcome_no_delete
                BEFORE DELETE ON doi_outcome_labels
                BEGIN
                    SELECT RAISE(ABORT, 'DOI outcome labels are append-only');
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
            connection.execute(
                "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) "
                "VALUES (?, ?)",
                (DOI_LIFECYCLE_SCHEMA_VERSION, iso_utc(utc_now())),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) "
                "VALUES (?, ?)",
                (DOI_OUTCOME_SCHEMA_VERSION, iso_utc(utc_now())),
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

    @staticmethod
    def _doi_family_from_row(row: sqlite3.Row) -> ContractFamily:
        thesis = UnderlyingThesisRef(
            thesis_id=row["thesis_id"],
            thesis_version=int(row["thesis_version"]),
            ticker=row["ticker"],
            governed_direction=row["governed_direction"],
            origin_spot=float(row["origin_spot"]),
            origin_timestamp_utc=parse_utc(row["origin_timestamp_utc"]),
            target_spot=row["target_spot"],
            invalidation_spot=row["invalidation_spot"],
            planned_hold_sessions=int(row["planned_hold_sessions"]),
            planned_hold_source=row["planned_hold_source"],
            evidence_cutoff_utc=parse_utc(row["thesis_evidence_cutoff_utc"]),
        )
        return ContractFamily(
            family_id=row["family_id"],
            thesis=thesis,
            run_id=row["run_id"],
            family_policy_version=row["family_policy_version"],
            evidence_cutoff_utc=parse_utc(row["evidence_cutoff_utc"]),
            candidate_symbols=tuple(json.loads(row["candidate_symbols_json"])),
            source_dataset_ids=tuple(json.loads(row["source_dataset_ids_json"])),
            family_state=ModelApplicabilityState(row["family_state"]),
            created_at=parse_utc(row["created_at"]),
            metadata=json.loads(row["metadata_json"]),
            decision_authority=row["decision_authority"],
            can_change_direction=bool(row["can_change_direction"]),
            can_invalidate_thesis=bool(row["can_invalidate_thesis"]),
            can_grant_capital=bool(row["can_grant_capital"]),
        )

    @staticmethod
    def _doi_assessment_from_row(row: sqlite3.Row) -> ContractAssessment:
        return ContractAssessment(
            assessment_id=row["assessment_id"],
            family_id=row["family_id"],
            thesis_id=row["thesis_id"],
            run_id=row["run_id"],
            contract_symbol=row["contract_symbol"],
            observation_id=row["observation_id"],
            entry_state=ContractEntryState(row["entry_state"]),
            applicability_state=ModelApplicabilityState(row["applicability_state"]),
            evidence_cutoff_utc=parse_utc(row["evidence_cutoff_utc"]),
            input_dataset_ids=tuple(json.loads(row["input_dataset_ids_json"])),
            calculation_version=row["calculation_version"],
            feature_version=row["feature_version"],
            model_version=row["model_version"],
            ranking_score_uncalibrated=row["ranking_score_uncalibrated"],
            p_liquidity_1d=row["p_liquidity_1d"],
            p_liquidity_2d=row["p_liquidity_2d"],
            p_liquidity_3d=row["p_liquidity_3d"],
            p_positive_return_before_horizon=row[
                "p_positive_return_before_horizon"
            ],
            p_return_hurdle_before_horizon=row[
                "p_return_hurdle_before_horizon"
            ],
            p_target_before_invalidation=row["p_target_before_invalidation"],
            expected_net_return=row["expected_net_return"],
            expected_downside=row["expected_downside"],
            expected_time_to_monetisation=row["expected_time_to_monetisation"],
            model_uncertainty=row["model_uncertainty"],
            probabilities_calibrated=bool(row["probabilities_calibrated"]),
            metadata=json.loads(row["metadata_json"]),
            decision_authority=row["decision_authority"],
            can_change_direction=bool(row["can_change_direction"]),
            can_invalidate_thesis=bool(row["can_invalidate_thesis"]),
            can_grant_capital=bool(row["can_grant_capital"]),
        )

    @staticmethod
    def _doi_preferred_from_row(row: sqlite3.Row) -> PreferredContractDecision:
        return PreferredContractDecision(
            decision_id=row["decision_id"],
            event_key=row["event_key"],
            family_id=row["family_id"],
            thesis_id=row["thesis_id"],
            run_id=row["run_id"],
            selected_contract_symbol=row["selected_contract_symbol"],
            selected_assessment_id=row["selected_assessment_id"],
            selection_reason=row["selection_reason"],
            selected_at=parse_utc(row["selected_at"]),
            alternative_contract_symbols=tuple(
                json.loads(row["alternative_contract_symbols_json"])
            ),
            previous_contract_symbol=row["previous_contract_symbol"],
            prior_decision_id=row["prior_decision_id"],
            utility_margin=row["utility_margin"],
            hysteresis_applied=bool(row["hysteresis_applied"]),
            economics_recomputed=bool(row["economics_recomputed"]),
            decision_version=int(row["decision_version"]),
            metadata=json.loads(row["metadata_json"]),
            decision_authority=row["decision_authority"],
            execution_authority=row["execution_authority"],
        )

    @staticmethod
    def _doi_lifecycle_from_row(row: sqlite3.Row) -> DOILifecycleEvent:
        return DOILifecycleEvent(
            event_id=row["event_id"],
            event_key=row["event_key"],
            thesis_id=row["thesis_id"],
            thesis_version=int(row["thesis_version"]),
            family_id=row["family_id"],
            run_id=row["run_id"],
            evaluation_point=DOIEvaluationPoint(row["evaluation_point"]),
            condition_state=DOIThesisConditionState(row["condition_state"]),
            previous_condition_state=(
                DOIThesisConditionState(row["previous_condition_state"])
                if row["previous_condition_state"] else None
            ),
            evidence_cutoff_utc=parse_utc(row["evidence_cutoff_utc"]),
            current_spot=row["current_spot"],
            target_spot=row["target_spot"],
            invalidation_spot=row["invalidation_spot"],
            horizon_end_date=(
                date.fromisoformat(row["horizon_end_date"])
                if row["horizon_end_date"] else None
            ),
            material_change=bool(row["material_change"]),
            material_reasons=tuple(json.loads(row["material_reasons_json"])),
            recorded_at=parse_utc(row["recorded_at"]),
            metadata=json.loads(row["metadata_json"]),
            retain_opportunity=bool(row["retain_opportunity"]),
            decision_authority=row["decision_authority"],
            can_change_direction=bool(row["can_change_direction"]),
            can_grant_capital=bool(row["can_grant_capital"]),
        )

    @staticmethod
    def _doi_outcome_from_row(row: sqlite3.Row) -> DOIOutcomeLabel:
        label = DOIOutcomeLabel.from_dict(json.loads(row["payload_json"]))
        if label.label_id != row["label_id"]:
            raise OptionLifecycleConflict("DOI outcome row identity conflicts with payload")
        return label

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

    def contract_observation(
        self, observation_id: str
    ) -> ContractObservation | None:
        """Return one immutable exact-contract observation by natural identity."""

        with self.registry.connection() as connection:
            row = connection.execute(
                "SELECT * FROM option_contract_observations WHERE observation_id = ?",
                (_required_text(observation_id, "observation_id"),),
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

    def contract_family(self, family_id: str) -> ContractFamily | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (_required_text(family_id, "family_id"),),
            ).fetchone()
        return self._doi_family_from_row(row) if row else None

    def latest_contract_family(self, thesis_id: str) -> ContractFamily | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_contract_families
                WHERE thesis_id = ? ORDER BY evidence_cutoff_utc DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._doi_family_from_row(row) if row else None

    def contract_assessment(self, assessment_id: str) -> ContractAssessment | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                "SELECT * FROM doi_contract_assessments WHERE assessment_id = ?",
                (_required_text(assessment_id, "assessment_id"),),
            ).fetchone()
        return self._doi_assessment_from_row(row) if row else None

    def previous_contract_assessment(
        self,
        *,
        thesis_id: str,
        contract_symbol: str,
        exclude_assessment_id: str | None = None,
    ) -> ContractAssessment | None:
        query = """
            SELECT * FROM doi_contract_assessments
            WHERE thesis_id = ? AND contract_symbol = ?
        """
        parameters: list[Any] = [
            _normalise_token(thesis_id, "thesis_id"),
            _normalise_token(contract_symbol, "contract_symbol"),
        ]
        if exclude_assessment_id:
            query += " AND assessment_id <> ?"
            parameters.append(_required_text(exclude_assessment_id, "exclude_assessment_id"))
        query += " ORDER BY evidence_cutoff_utc DESC, assessment_id DESC LIMIT 1"
        with self.registry.connection() as connection:
            row = connection.execute(query, parameters).fetchone()
        return self._doi_assessment_from_row(row) if row else None

    def assessments_for_family(self, family_id: str) -> tuple[ContractAssessment, ...]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM doi_contract_assessments
                WHERE family_id = ? ORDER BY contract_symbol, assessment_id
                """,
                (_required_text(family_id, "family_id"),),
            ).fetchall()
        return tuple(self._doi_assessment_from_row(row) for row in rows)

    def latest_preferred_contract(
        self, thesis_id: str
    ) -> PreferredContractDecision | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_preferred_contract_decisions
                WHERE thesis_id = ? ORDER BY decision_version DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._doi_preferred_from_row(row) if row else None

    def preferred_contract_decision(
        self, *, thesis_id: str, event_key: str
    ) -> PreferredContractDecision | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_preferred_contract_decisions
                WHERE thesis_id = ? AND event_key = ?
                """,
                (
                    _normalise_token(thesis_id, "thesis_id"),
                    _normalise_token(event_key, "event_key"),
                ),
            ).fetchone()
        return self._doi_preferred_from_row(row) if row else None

    def doi_lifecycle_event(
        self, *, thesis_id: str, event_key: str
    ) -> DOILifecycleEvent | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_lifecycle_events
                WHERE thesis_id = ? AND event_key = ?
                """,
                (
                    _normalise_token(thesis_id, "thesis_id"),
                    _normalise_token(event_key, "event_key"),
                ),
            ).fetchone()
        return self._doi_lifecycle_from_row(row) if row else None

    def latest_doi_lifecycle_event(
        self, thesis_id: str
    ) -> DOILifecycleEvent | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_lifecycle_events
                WHERE thesis_id = ?
                ORDER BY evidence_cutoff_utc DESC, recorded_at DESC LIMIT 1
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchone()
        return self._doi_lifecycle_from_row(row) if row else None

    def doi_lifecycle_events(
        self, thesis_id: str
    ) -> tuple[DOILifecycleEvent, ...]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM doi_lifecycle_events
                WHERE thesis_id = ?
                ORDER BY evidence_cutoff_utc, recorded_at, event_id
                """,
                (_normalise_token(thesis_id, "thesis_id"),),
            ).fetchall()
        return tuple(self._doi_lifecycle_from_row(row) for row in rows)

    def doi_outcome_label(self, label_id: str) -> DOIOutcomeLabel | None:
        with self.registry.connection() as connection:
            row = connection.execute(
                "SELECT * FROM doi_outcome_labels WHERE label_id = ?",
                (_required_text(label_id, "label_id"),),
            ).fetchone()
        return self._doi_outcome_from_row(row) if row else None

    def outcome_labels_for_assessment(
        self, assessment_id: str
    ) -> tuple[DOIOutcomeLabel, ...]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM doi_outcome_labels
                WHERE assessment_id = ?
                ORDER BY horizon_sessions, outcome_cutoff_utc, label_id
                """,
                (_required_text(assessment_id, "assessment_id"),),
            ).fetchall()
        return tuple(self._doi_outcome_from_row(row) for row in rows)

    def latest_outcome_label(
        self, *, assessment_id: str, horizon_sessions: int
    ) -> DOIOutcomeLabel | None:
        if int(horizon_sessions) <= 0:
            raise DatasetValidationError("horizon_sessions must be positive")
        with self.registry.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doi_outcome_labels
                WHERE assessment_id = ? AND horizon_sessions = ?
                ORDER BY outcome_cutoff_utc DESC, label_id DESC LIMIT 1
                """,
                (_required_text(assessment_id, "assessment_id"), int(horizon_sessions)),
            ).fetchone()
        return self._doi_outcome_from_row(row) if row else None

    def doi_outcome_labels(
        self,
        *,
        data_statuses: tuple[OutcomeDataStatus | str, ...] | None = None,
        horizon_sessions: int | None = None,
    ) -> tuple[DOIOutcomeLabel, ...]:
        predicates: list[str] = []
        parameters: list[Any] = []
        if data_statuses:
            values = tuple(
                item.value if isinstance(item, OutcomeDataStatus) else OutcomeDataStatus(str(item)).value
                for item in data_statuses
            )
            predicates.append("data_status IN (" + ",".join("?" for _ in values) + ")")
            parameters.extend(values)
        if horizon_sessions is not None:
            if int(horizon_sessions) <= 0:
                raise DatasetValidationError("horizon_sessions must be positive")
            predicates.append("horizon_sessions = ?")
            parameters.append(int(horizon_sessions))
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        with self.registry.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM doi_outcome_labels" + where
                + " ORDER BY assessment_cutoff_utc, assessment_id, horizon_sessions, outcome_cutoff_utc",
                parameters,
            ).fetchall()
        return tuple(self._doi_outcome_from_row(row) for row in rows)

    def record_doi_outcome_label(self, label: DOIOutcomeLabel) -> PersistResult:
        expected_id = outcome_label_identity(
            assessment_id=label.assessment_id,
            horizon_sessions=label.horizon_sessions,
            outcome_cutoff_utc=label.outcome_cutoff_utc,
            calculation_version=label.calculation_version,
            data_status=label.data_status,
        )
        if label.label_id != expected_id:
            raise DatasetValidationError("label_id does not match DOI outcome identity")
        payload_json = _canonical_json(label.to_dict())
        payload_hash = _hash("DOI_OUTCOME_LABEL_PAYLOAD_V1", payload_json)
        values = {
            "label_id": label.label_id,
            "assessment_id": label.assessment_id,
            "family_id": label.family_id,
            "thesis_id": label.thesis_id,
            "run_id": label.run_id,
            "ticker": label.ticker,
            "contract_symbol": label.contract_symbol,
            "original_observation_id": label.original_observation_id,
            "direction": label.direction,
            "horizon_sessions": label.horizon_sessions,
            "assessment_cutoff_utc": iso_utc(label.assessment_cutoff_utc),
            "outcome_cutoff_utc": iso_utc(label.outcome_cutoff_utc),
            "horizon_end_session": (
                label.horizon_end_session.isoformat()
                if label.horizon_end_session else None
            ),
            "data_status": label.data_status.value,
            "calculation_version": label.calculation_version,
            "outcome_kind": label.outcome_kind,
            "is_counterfactual": int(label.is_counterfactual),
            "uses_realised_fills": int(label.uses_realised_fills),
            "decision_authority": label.decision_authority,
            "can_change_direction": int(label.can_change_direction),
            "can_grant_capital": int(label.can_grant_capital),
            "can_close_position": int(label.can_close_position),
            "payload_json": payload_json,
            "payload_hash": payload_hash,
        }
        with self.registry.connection() as connection:
            assessment_row = connection.execute(
                "SELECT * FROM doi_contract_assessments WHERE assessment_id = ?",
                (label.assessment_id,),
            ).fetchone()
            if assessment_row is None:
                raise DatasetValidationError("DOI outcome assessment does not exist")
            assessment = self._doi_assessment_from_row(assessment_row)
            if (
                assessment.family_id != label.family_id
                or assessment.thesis_id != label.thesis_id
                or assessment.run_id != label.run_id
                or assessment.contract_symbol != label.contract_symbol
                or assessment.observation_id != label.original_observation_id
                or assessment.evidence_cutoff_utc != label.assessment_cutoff_utc
            ):
                raise DatasetValidationError(
                    "DOI outcome conflicts with immutable contract assessment"
                )
            family_row = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (label.family_id,),
            ).fetchone()
            if family_row is None:
                raise DatasetValidationError("DOI outcome family does not exist")
            family = self._doi_family_from_row(family_row)
            if family.thesis.ticker != label.ticker or family.thesis.governed_direction != label.direction:
                raise DatasetValidationError("DOI outcome conflicts with governed thesis")
            observation_row = connection.execute(
                "SELECT * FROM option_contract_observations WHERE observation_id = ?",
                (label.original_observation_id,),
            ).fetchone()
            if observation_row is None:
                raise DatasetValidationError("DOI outcome origin observation does not exist")
            for observation_id in label.source_option_observation_ids:
                future_row = connection.execute(
                    "SELECT contract_symbol, quote_as_of FROM option_contract_observations WHERE observation_id = ?",
                    (observation_id,),
                ).fetchone()
                if future_row is None:
                    raise DatasetValidationError(
                        f"DOI outcome source observation does not exist: {observation_id}"
                    )
                if future_row["contract_symbol"] != label.contract_symbol:
                    raise DatasetValidationError("DOI outcome source changed exact contract")
                if parse_utc(future_row["quote_as_of"]) <= label.assessment_cutoff_utc:
                    raise DatasetValidationError("DOI outcome source is not future evidence")
            existing = connection.execute(
                "SELECT * FROM doi_outcome_labels WHERE label_id = ?",
                (label.label_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict(
                        "DOI outcome identity already has different immutable content"
                    )
                return PersistResult(self._doi_outcome_from_row(existing), True)
            try:
                connection.execute(
                    """
                    INSERT INTO doi_outcome_labels(
                        label_id, assessment_id, family_id, thesis_id, run_id,
                        ticker, contract_symbol, original_observation_id,
                        direction, horizon_sessions, assessment_cutoff_utc,
                        outcome_cutoff_utc, horizon_end_session, data_status,
                        calculation_version, outcome_kind, is_counterfactual,
                        uses_realised_fills, decision_authority,
                        can_change_direction, can_grant_capital,
                        can_close_position, payload_json, payload_hash
                    ) VALUES (
                        :label_id, :assessment_id, :family_id, :thesis_id,
                        :run_id, :ticker, :contract_symbol,
                        :original_observation_id, :direction,
                        :horizon_sessions, :assessment_cutoff_utc,
                        :outcome_cutoff_utc, :horizon_end_session,
                        :data_status, :calculation_version, :outcome_kind,
                        :is_counterfactual, :uses_realised_fills,
                        :decision_authority, :can_change_direction,
                        :can_grant_capital, :can_close_position,
                        :payload_json, :payload_hash
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error
        return PersistResult(label, False)

    def record_doi_lifecycle_event(
        self, event: DOILifecycleEvent
    ) -> PersistResult:
        expected_id = DOILifecycleEvent.create(
            event_key=event.event_key,
            thesis_id=event.thesis_id,
            thesis_version=event.thesis_version,
            family_id=event.family_id,
            run_id=event.run_id,
            evaluation_point=event.evaluation_point,
            condition_state=event.condition_state,
            previous_condition_state=event.previous_condition_state,
            evidence_cutoff_utc=event.evidence_cutoff_utc,
            current_spot=event.current_spot,
            target_spot=event.target_spot,
            invalidation_spot=event.invalidation_spot,
            horizon_end_date=event.horizon_end_date,
            material_change=event.material_change,
            material_reasons=event.material_reasons,
            recorded_at=event.recorded_at,
            metadata=event.metadata,
        ).event_id
        if event.event_id != expected_id:
            raise DatasetValidationError("event_id does not match DOI lifecycle identity")
        values = {
            "event_id": event.event_id,
            "event_key": event.event_key,
            "thesis_id": event.thesis_id,
            "thesis_version": event.thesis_version,
            "family_id": event.family_id,
            "run_id": event.run_id,
            "evaluation_point": event.evaluation_point.value,
            "condition_state": event.condition_state.value,
            "previous_condition_state": (
                event.previous_condition_state.value
                if event.previous_condition_state else None
            ),
            "evidence_cutoff_utc": iso_utc(event.evidence_cutoff_utc),
            "current_spot": event.current_spot,
            "target_spot": event.target_spot,
            "invalidation_spot": event.invalidation_spot,
            "horizon_end_date": (
                event.horizon_end_date.isoformat()
                if event.horizon_end_date else None
            ),
            "material_change": int(event.material_change),
            "material_reasons_json": json.dumps(list(event.material_reasons)),
            "recorded_at": iso_utc(event.recorded_at),
            "metadata_json": _canonical_json(dict(event.metadata)),
            "retain_opportunity": int(event.retain_opportunity),
            "decision_authority": event.decision_authority,
            "can_change_direction": int(event.can_change_direction),
            "can_grant_capital": int(event.can_grant_capital),
        }
        hash_values = dict(values)
        hash_values.pop("recorded_at")
        values["payload_hash"] = _hash(
            "DOI_LIFECYCLE_EVENT_PAYLOAD_V1", _canonical_json(hash_values)
        )
        with self.registry.connection() as connection:
            family_row = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (event.family_id,),
            ).fetchone()
            if family_row is None:
                raise DatasetValidationError("DOI lifecycle family does not exist")
            family = self._doi_family_from_row(family_row)
            if (
                family.thesis.thesis_id != event.thesis_id
                or family.thesis.thesis_version != event.thesis_version
                or family.run_id != event.run_id
            ):
                raise DatasetValidationError(
                    "DOI lifecycle event conflicts with governed family"
                )
            existing = connection.execute(
                "SELECT * FROM doi_lifecycle_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != values["payload_hash"]:
                    raise OptionLifecycleConflict(
                        "DOI lifecycle identity already has different immutable content"
                    )
                return PersistResult(self._doi_lifecycle_from_row(existing), True)
            try:
                connection.execute(
                    """
                    INSERT INTO doi_lifecycle_events(
                        event_id, event_key, thesis_id, thesis_version, family_id,
                        run_id, evaluation_point, condition_state,
                        previous_condition_state, evidence_cutoff_utc,
                        current_spot, target_spot, invalidation_spot,
                        horizon_end_date, material_change, material_reasons_json,
                        recorded_at, metadata_json, retain_opportunity,
                        decision_authority, can_change_direction,
                        can_grant_capital, payload_hash
                    ) VALUES (
                        :event_id, :event_key, :thesis_id, :thesis_version,
                        :family_id, :run_id, :evaluation_point, :condition_state,
                        :previous_condition_state, :evidence_cutoff_utc,
                        :current_spot, :target_spot, :invalidation_spot,
                        :horizon_end_date, :material_change,
                        :material_reasons_json, :recorded_at, :metadata_json,
                        :retain_opportunity, :decision_authority,
                        :can_change_direction, :can_grant_capital, :payload_hash
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error
        return PersistResult(event, False)

    def record_contract_family(self, family: ContractFamily) -> PersistResult:
        expected_identity = ContractFamily.create(
            thesis=family.thesis,
            run_id=family.run_id,
            family_policy_version=family.family_policy_version,
            evidence_cutoff_utc=family.evidence_cutoff_utc,
            candidate_symbols=family.candidate_symbols,
            source_dataset_ids=family.source_dataset_ids,
            family_state=family.family_state,
            created_at=family.created_at,
            metadata=family.metadata,
        ).family_id
        if family.family_id != expected_identity:
            raise DatasetValidationError("family_id does not match DOI family identity")

        values = {
            "family_id": family.family_id,
            "thesis_id": family.thesis.thesis_id,
            "thesis_version": family.thesis.thesis_version,
            "run_id": family.run_id,
            "ticker": family.thesis.ticker,
            "governed_direction": family.thesis.governed_direction,
            "origin_spot": family.thesis.origin_spot,
            "origin_timestamp_utc": iso_utc(family.thesis.origin_timestamp_utc),
            "target_spot": family.thesis.target_spot,
            "invalidation_spot": family.thesis.invalidation_spot,
            "planned_hold_sessions": family.thesis.planned_hold_sessions,
            "planned_hold_source": family.thesis.planned_hold_source,
            "thesis_evidence_cutoff_utc": iso_utc(
                family.thesis.evidence_cutoff_utc
            ),
            "family_policy_version": family.family_policy_version,
            "evidence_cutoff_utc": iso_utc(family.evidence_cutoff_utc),
            "candidate_symbols_json": json.dumps(list(family.candidate_symbols)),
            "source_dataset_ids_json": json.dumps(list(family.source_dataset_ids)),
            "family_state": family.family_state.value,
            "created_at": iso_utc(family.created_at),
            "metadata_json": _canonical_json(dict(family.metadata)),
            "decision_authority": family.decision_authority,
            "can_change_direction": int(family.can_change_direction),
            "can_invalidate_thesis": int(family.can_invalidate_thesis),
            "can_grant_capital": int(family.can_grant_capital),
        }
        hash_values = dict(values)
        hash_values.pop("created_at")
        values["payload_hash"] = _hash(
            "DOI_CONTRACT_FAMILY_PAYLOAD_V1", _canonical_json(hash_values)
        )

        with self.registry.connection() as connection:
            thesis_row = connection.execute(
                """
                SELECT * FROM option_thesis_events
                WHERE thesis_id = ? AND version = ?
                """,
                (family.thesis.thesis_id, family.thesis.thesis_version),
            ).fetchone()
            if thesis_row is None:
                raise DatasetValidationError("referenced thesis version does not exist")
            thesis = self._thesis_from_row(thesis_row)
            if (
                thesis.ticker != family.thesis.ticker
                or thesis.direction != family.thesis.governed_direction
            ):
                raise DatasetValidationError(
                    "contract family conflicts with governed thesis identity"
                )
            for dataset_id in family.source_dataset_ids:
                exists = connection.execute(
                    "SELECT 1 FROM dataset_registry WHERE dataset_id = ?",
                    (dataset_id,),
                ).fetchone()
                if exists is None:
                    raise DatasetValidationError(
                        f"family source dataset does not exist: {dataset_id}"
                    )
            existing = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (family.family_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != values["payload_hash"]:
                    raise OptionLifecycleConflict(
                        "contract family identity already has different immutable content"
                    )
                return PersistResult(self._doi_family_from_row(existing), True)
            try:
                connection.execute(
                    """
                    INSERT INTO doi_contract_families(
                        family_id, thesis_id, thesis_version, run_id, ticker,
                        governed_direction, origin_spot, origin_timestamp_utc,
                        target_spot, invalidation_spot, planned_hold_sessions,
                        planned_hold_source, thesis_evidence_cutoff_utc,
                        family_policy_version, evidence_cutoff_utc,
                        candidate_symbols_json, source_dataset_ids_json,
                        family_state, created_at, metadata_json,
                        decision_authority, can_change_direction,
                        can_invalidate_thesis, can_grant_capital, payload_hash
                    ) VALUES (
                        :family_id, :thesis_id, :thesis_version, :run_id, :ticker,
                        :governed_direction, :origin_spot, :origin_timestamp_utc,
                        :target_spot, :invalidation_spot, :planned_hold_sessions,
                        :planned_hold_source, :thesis_evidence_cutoff_utc,
                        :family_policy_version, :evidence_cutoff_utc,
                        :candidate_symbols_json, :source_dataset_ids_json,
                        :family_state, :created_at, :metadata_json,
                        :decision_authority, :can_change_direction,
                        :can_invalidate_thesis, :can_grant_capital, :payload_hash
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error
        return PersistResult(family, False)

    def record_contract_assessment(
        self, assessment: ContractAssessment
    ) -> PersistResult:
        expected_identity = ContractAssessment.create(
            family_id=assessment.family_id,
            thesis_id=assessment.thesis_id,
            run_id=assessment.run_id,
            contract_symbol=assessment.contract_symbol,
            observation_id=assessment.observation_id,
            entry_state=assessment.entry_state,
            applicability_state=assessment.applicability_state,
            evidence_cutoff_utc=assessment.evidence_cutoff_utc,
            input_dataset_ids=assessment.input_dataset_ids,
            calculation_version=assessment.calculation_version,
            feature_version=assessment.feature_version,
            model_version=assessment.model_version,
            ranking_score_uncalibrated=assessment.ranking_score_uncalibrated,
            p_liquidity_1d=assessment.p_liquidity_1d,
            p_liquidity_2d=assessment.p_liquidity_2d,
            p_liquidity_3d=assessment.p_liquidity_3d,
            p_positive_return_before_horizon=(
                assessment.p_positive_return_before_horizon
            ),
            p_return_hurdle_before_horizon=(
                assessment.p_return_hurdle_before_horizon
            ),
            p_target_before_invalidation=assessment.p_target_before_invalidation,
            expected_net_return=assessment.expected_net_return,
            expected_downside=assessment.expected_downside,
            expected_time_to_monetisation=assessment.expected_time_to_monetisation,
            model_uncertainty=assessment.model_uncertainty,
            probabilities_calibrated=assessment.probabilities_calibrated,
            metadata=assessment.metadata,
        ).assessment_id
        if assessment.assessment_id != expected_identity:
            raise DatasetValidationError(
                "assessment_id does not match DOI assessment identity"
            )
        values = assessment.to_dict()
        values["entry_state"] = assessment.entry_state.value
        values["applicability_state"] = assessment.applicability_state.value
        values["evidence_cutoff_utc"] = iso_utc(assessment.evidence_cutoff_utc)
        values["input_dataset_ids_json"] = json.dumps(
            list(assessment.input_dataset_ids)
        )
        values["probabilities_calibrated"] = int(
            assessment.probabilities_calibrated
        )
        values["metadata_json"] = _canonical_json(dict(assessment.metadata))
        for unused in (
            "input_dataset_ids", "metadata", "domain_version",
        ):
            values.pop(unused, None)
        values["can_change_direction"] = int(assessment.can_change_direction)
        values["can_invalidate_thesis"] = int(assessment.can_invalidate_thesis)
        values["can_grant_capital"] = int(assessment.can_grant_capital)
        hash_values = dict(values)
        values["payload_hash"] = _hash(
            "DOI_CONTRACT_ASSESSMENT_PAYLOAD_V1", _canonical_json(hash_values)
        )

        with self.registry.connection() as connection:
            family_row = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (assessment.family_id,),
            ).fetchone()
            if family_row is None:
                raise DatasetValidationError("assessment family does not exist")
            family = self._doi_family_from_row(family_row)
            if (
                family.thesis.thesis_id != assessment.thesis_id
                or family.run_id != assessment.run_id
                or assessment.contract_symbol not in family.candidate_symbols
            ):
                raise DatasetValidationError(
                    "assessment conflicts with its contract family"
                )
            observation_row = connection.execute(
                "SELECT * FROM option_contract_observations WHERE observation_id = ?",
                (assessment.observation_id,),
            ).fetchone()
            if observation_row is None:
                raise DatasetValidationError("assessment observation does not exist")
            observation = self._observation_from_row(observation_row)
            if (
                observation.thesis_id != assessment.thesis_id
                or observation.contract_symbol != assessment.contract_symbol
            ):
                raise DatasetValidationError(
                    "assessment does not match the exact contract observation"
                )
            if assessment.evidence_cutoff_utc < observation.quote_as_of:
                raise DatasetValidationError(
                    "assessment evidence cutoff predates its contract quote"
                )
            if observation.source_dataset_id not in assessment.input_dataset_ids:
                raise DatasetValidationError(
                    "assessment lineage omits its observation dataset"
                )
            if not set(assessment.input_dataset_ids) <= set(
                family.source_dataset_ids
            ):
                raise DatasetValidationError(
                    "assessment input datasets are outside its family lineage"
                )
            for dataset_id in assessment.input_dataset_ids:
                exists = connection.execute(
                    "SELECT 1 FROM dataset_registry WHERE dataset_id = ?",
                    (dataset_id,),
                ).fetchone()
                if exists is None:
                    raise DatasetValidationError(
                        f"assessment input dataset does not exist: {dataset_id}"
                    )
            existing = connection.execute(
                "SELECT * FROM doi_contract_assessments WHERE assessment_id = ?",
                (assessment.assessment_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != values["payload_hash"]:
                    raise OptionLifecycleConflict(
                        "contract assessment identity has different immutable content"
                    )
                return PersistResult(self._doi_assessment_from_row(existing), True)
            try:
                connection.execute(
                    """
                    INSERT INTO doi_contract_assessments(
                        assessment_id, family_id, thesis_id, run_id,
                        contract_symbol, observation_id, entry_state,
                        applicability_state, evidence_cutoff_utc,
                        input_dataset_ids_json, calculation_version,
                        feature_version, model_version,
                        ranking_score_uncalibrated, p_liquidity_1d,
                        p_liquidity_2d, p_liquidity_3d,
                        p_positive_return_before_horizon,
                        p_return_hurdle_before_horizon,
                        p_target_before_invalidation, expected_net_return,
                        expected_downside, expected_time_to_monetisation,
                        model_uncertainty, probabilities_calibrated,
                        metadata_json, decision_authority,
                        can_change_direction, can_invalidate_thesis,
                        can_grant_capital, payload_hash
                    ) VALUES (
                        :assessment_id, :family_id, :thesis_id, :run_id,
                        :contract_symbol, :observation_id, :entry_state,
                        :applicability_state, :evidence_cutoff_utc,
                        :input_dataset_ids_json, :calculation_version,
                        :feature_version, :model_version,
                        :ranking_score_uncalibrated, :p_liquidity_1d,
                        :p_liquidity_2d, :p_liquidity_3d,
                        :p_positive_return_before_horizon,
                        :p_return_hurdle_before_horizon,
                        :p_target_before_invalidation, :expected_net_return,
                        :expected_downside, :expected_time_to_monetisation,
                        :model_uncertainty, :probabilities_calibrated,
                        :metadata_json, :decision_authority,
                        :can_change_direction, :can_invalidate_thesis,
                        :can_grant_capital, :payload_hash
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error
        return PersistResult(assessment, False)

    def record_preferred_contract_decision(
        self,
        decision: PreferredContractDecision,
        *,
        expected_version: int | None = None,
    ) -> PersistResult:
        base_values = decision.to_dict()
        for unused in ("selected_at", "decision_version", "domain_version"):
            base_values.pop(unused, None)
        payload_hash = _hash(
            "DOI_PREFERRED_CONTRACT_PAYLOAD_V1", _canonical_json(base_values)
        )
        with self.registry.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM doi_preferred_contract_decisions WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict(
                        "preferred decision identity has different immutable content"
                    )
                return PersistResult(self._doi_preferred_from_row(existing), True)
            family_row = connection.execute(
                "SELECT * FROM doi_contract_families WHERE family_id = ?",
                (decision.family_id,),
            ).fetchone()
            if family_row is None:
                raise DatasetValidationError("preferred decision family does not exist")
            family = self._doi_family_from_row(family_row)
            assessment_row = connection.execute(
                "SELECT * FROM doi_contract_assessments WHERE assessment_id = ?",
                (decision.selected_assessment_id,),
            ).fetchone()
            if assessment_row is None:
                raise DatasetValidationError(
                    "preferred decision assessment does not exist"
                )
            assessment = self._doi_assessment_from_row(assessment_row)
            if (
                family.thesis.thesis_id != decision.thesis_id
                or family.run_id != decision.run_id
                or assessment.family_id != decision.family_id
                or assessment.contract_symbol != decision.selected_contract_symbol
            ):
                raise DatasetValidationError(
                    "preferred decision conflicts with family or assessment"
                )
            assessed_symbols = {
                row[0]
                for row in connection.execute(
                    "SELECT contract_symbol FROM doi_contract_assessments "
                    "WHERE family_id = ?",
                    (decision.family_id,),
                ).fetchall()
            }
            if not set(decision.alternative_contract_symbols) <= assessed_symbols:
                raise DatasetValidationError(
                    "preferred alternatives must be assessed family members"
                )
            latest_row = connection.execute(
                "SELECT * FROM doi_preferred_contract_decisions "
                "WHERE thesis_id = ? ORDER BY decision_version DESC LIMIT 1",
                (decision.thesis_id,),
            ).fetchone()
            if latest_row:
                latest = self._doi_preferred_from_row(latest_row)
                if expected_version != latest.decision_version:
                    raise OptionLifecycleConcurrencyError(
                        f"expected preferred version {expected_version}, "
                        f"found {latest.decision_version}"
                    )
                if decision.prior_decision_id != latest.decision_id:
                    raise DatasetValidationError(
                        "preferred decision must link the latest prior decision"
                    )
                if decision.previous_contract_symbol != latest.selected_contract_symbol:
                    raise DatasetValidationError(
                        "previous contract must match the latest preferred contract"
                    )
                version = latest.decision_version + 1
            else:
                if expected_version not in {None, 0}:
                    raise OptionLifecycleConcurrencyError(
                        f"expected preferred version {expected_version}, found 0"
                    )
                if decision.prior_decision_id or decision.previous_contract_symbol:
                    raise DatasetValidationError(
                        "first preferred decision cannot reference a prior decision"
                    )
                version = 1
            persisted = decision.with_version(version)
            values = {
                "decision_id": persisted.decision_id,
                "event_key": persisted.event_key,
                "family_id": persisted.family_id,
                "thesis_id": persisted.thesis_id,
                "run_id": persisted.run_id,
                "selected_contract_symbol": persisted.selected_contract_symbol,
                "selected_assessment_id": persisted.selected_assessment_id,
                "selection_reason": persisted.selection_reason,
                "selected_at": iso_utc(persisted.selected_at),
                "alternative_contract_symbols_json": json.dumps(
                    list(persisted.alternative_contract_symbols)
                ),
                "previous_contract_symbol": persisted.previous_contract_symbol,
                "prior_decision_id": persisted.prior_decision_id,
                "utility_margin": persisted.utility_margin,
                "hysteresis_applied": int(persisted.hysteresis_applied),
                "economics_recomputed": int(persisted.economics_recomputed),
                "decision_version": version,
                "metadata_json": _canonical_json(dict(persisted.metadata)),
                "decision_authority": persisted.decision_authority,
                "execution_authority": persisted.execution_authority,
                "payload_hash": payload_hash,
            }
            try:
                connection.execute(
                    """
                    INSERT INTO doi_preferred_contract_decisions(
                        decision_id, event_key, family_id, thesis_id, run_id,
                        selected_contract_symbol, selected_assessment_id,
                        selection_reason, selected_at,
                        alternative_contract_symbols_json,
                        previous_contract_symbol, prior_decision_id,
                        utility_margin, hysteresis_applied,
                        economics_recomputed, decision_version, metadata_json,
                        decision_authority, execution_authority, payload_hash
                    ) VALUES (
                        :decision_id, :event_key, :family_id, :thesis_id, :run_id,
                        :selected_contract_symbol, :selected_assessment_id,
                        :selection_reason, :selected_at,
                        :alternative_contract_symbols_json,
                        :previous_contract_symbol, :prior_decision_id,
                        :utility_margin, :hysteresis_applied,
                        :economics_recomputed, :decision_version, :metadata_json,
                        :decision_authority, :execution_authority, :payload_hash
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as error:
                raise OptionLifecycleConflict(str(error)) from error
        return PersistResult(persisted, False)

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

        # Several contracts commonly share the same provider quote timestamp.
        # Returning latest_observation(thesis) is therefore order-dependent and
        # can hand the caller a different contract from the one just inserted.
        # Resolve by the immutable natural identity minted above instead.
        result = self.contract_observation(observation_id)
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
