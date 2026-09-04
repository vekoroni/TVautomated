"""Pure dynamic-session plan resolution and append-only plan persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
import os
import sqlite3
from typing import Any, Iterable, Mapping

from contracts.dynamic_session_contract import EvidenceState, OperationalContext
from .contracts import DatasetType, iso_utc, parse_utc
from .session_clock import SessionSnapshot, SessionState, session_snapshot


class RequestedAction(str, Enum):
    AUTO = "AUTO"
    BUILD_THESIS = "BUILD_THESIS"
    VALIDATE = "VALIDATE"
    FINALISE = "FINALISE"
    REPLAY = "REPLAY"


class AuthorityCeiling(str, Enum):
    EOD_PREPARED = "EOD_PREPARED"
    VALIDATION_ONLY = "VALIDATION_ONLY"
    EXECUTION_GATE_ELIGIBLE = "EXECUTION_GATE_ELIGIBLE"
    REVIEW_ONLY = "REVIEW_ONLY"
    RESEARCH_ONLY = "RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class DatasetRequirement:
    dataset_type: str
    session_date: str
    evidence_state: str
    authorised_tickers: tuple[str, ...] = ()
    interval_minutes: int | None = None
    cache_exact_hits: int = 0
    cache_partial_hits: int = 0
    estimated_physical_requests: int = 0
    worklist_source: str = "PLAN_INPUT"
    estimate_kind: str = "EXACT"

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_type", self.dataset_type.strip().upper())
        object.__setattr__(self, "evidence_state", self.evidence_state.strip().upper())
        object.__setattr__(self, "worklist_source", self.worklist_source.strip().upper())
        object.__setattr__(self, "estimate_kind", self.estimate_kind.strip().upper())
        object.__setattr__(
            self,
            "authorised_tickers",
            tuple(sorted({ticker.strip().upper() for ticker in self.authorised_tickers if ticker.strip()})),
        )
        for name in (
            "cache_exact_hits",
            "cache_partial_hits",
            "estimated_physical_requests",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class RunPlan:
    pipeline_run_id: str
    invocation_id: str
    requested_action: str
    resolved_action: str
    as_of_utc: str
    evidence_cutoff_utc: str
    exchange_calendar: str
    session_state: str
    last_completed_session: str
    current_session: str | None
    operational_context: str
    existing_thesis_id: str | None
    stages_to_run: tuple[str, ...]
    stages_to_reuse: tuple[str, ...]
    datasets_required: tuple[DatasetRequirement, ...]
    authorised_ticker_worklists: Mapping[str, tuple[str, ...]]
    estimated_physical_requests: int
    estimated_provider_credits: int
    expected_outputs: tuple[str, ...]
    execution_authority_ceiling: str
    retry_of_invocation_id: str | None = None
    supersedes_invocation_id: str | None = None
    plan_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "pipeline_run_id",
            "invocation_id",
            "requested_action",
            "resolved_action",
            "as_of_utc",
            "evidence_cutoff_utc",
            "exchange_calendar",
            "session_state",
            "last_completed_session",
            "operational_context",
            "execution_authority_ceiling",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.estimated_physical_requests < 0 or self.estimated_provider_credits < 0:
            raise ValueError("request and credit estimates cannot be negative")
        normalised_worklists = {
            str(stage).strip().upper(): tuple(
                sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})
            )
            for stage, tickers in self.authorised_ticker_worklists.items()
        }
        object.__setattr__(self, "authorised_ticker_worklists", normalised_worklists)
        expected = self.compute_hash()
        if self.plan_hash and self.plan_hash != expected:
            raise ValueError("plan_hash does not match immutable plan content")
        object.__setattr__(self, "plan_hash", expected)

    def _hash_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("plan_hash", None)
        return payload

    def compute_hash(self) -> str:
        encoded = json.dumps(
            self._hash_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"


def thesis_identity(
    *, ticker: str, completed_session: date, governed_direction: str,
    evidence_ids: Iterable[str], model_version: str, thesis_version: int,
) -> str:
    if thesis_version < 1:
        raise ValueError("thesis_version must be positive")
    return _stable_id(
        "thesis",
        {
            "ticker": ticker.strip().upper(),
            "completed_session": completed_session.isoformat(),
            "governed_direction": governed_direction.strip().upper(),
            "evidence_ids": sorted({value.strip() for value in evidence_ids if value.strip()}),
            "model_version": model_version.strip(),
            "thesis_version": thesis_version,
        },
    )


def validation_event_identity(
    *, thesis_id: str, evidence_cutoff_utc: datetime,
    underlying_observation_id: str,
    quote_observation_id: str | None = None,
    developing_profile_evidence_id: str | None = None,
) -> str:
    cutoff = _normalise_instant(evidence_cutoff_utc)
    return _stable_id(
        "validation",
        {
            "thesis_id": thesis_id.strip(),
            "evidence_cutoff_utc": iso_utc(cutoff),
            "underlying_observation_id": underlying_observation_id.strip(),
            "quote_observation_id": (quote_observation_id or "").strip(),
            "developing_profile_evidence_id": (
                developing_profile_evidence_id or ""
            ).strip(),
        },
    )


def evidence_identity(
    *, evidence_type: str, input_dataset_ids: Iterable[str],
    calculation_version: str, content_hash: str,
) -> str:
    return _stable_id(
        "evidence",
        {
            "evidence_type": evidence_type.strip().upper(),
            "input_dataset_ids": sorted(
                {value.strip() for value in input_dataset_ids if value.strip()}
            ),
            "calculation_version": calculation_version.strip(),
            "content_hash": content_hash.strip().lower(),
        },
    )


def contract_episode_identity(
    *, thesis_id: str, strategy: str, occ_symbols: Iterable[str]
) -> str:
    return _stable_id(
        "contract",
        {
            "thesis_id": thesis_id.strip(),
            "strategy": strategy.strip().upper(),
            "occ_symbols": sorted(
                {symbol.strip().upper() for symbol in occ_symbols if symbol.strip()}
            ),
        },
    )


def quote_observation_identity(
    *, contract_episode_id: str, provider_observed_at_utc: datetime,
    content_hash: str,
) -> str:
    return _stable_id(
        "quote",
        {
            "contract_episode_id": contract_episode_id.strip(),
            "provider_observed_at_utc": iso_utc(
                _normalise_instant(provider_observed_at_utc)
            ),
            "content_hash": content_hash.strip().lower(),
        },
    )


def _normalise_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("as_of_utc and evidence_cutoff_utc must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _resolve_action(
    requested: RequestedAction,
    snapshot: SessionSnapshot,
    *,
    existing_thesis_id: str | None,
    existing_thesis_session: date | None,
    provider_session_finalised: bool,
) -> tuple[RequestedAction, OperationalContext]:
    if requested is RequestedAction.REPLAY:
        return requested, OperationalContext.REPLAY
    if requested is not RequestedAction.AUTO:
        context = (
            OperationalContext.NO_VALID_THESIS
            if requested is RequestedAction.BUILD_THESIS and not existing_thesis_id
            else OperationalContext.VALIDATION_DUE
            if requested is RequestedAction.VALIDATE
            else OperationalContext.CURRENT_SESSION_FINALISATION_DUE
            if requested is RequestedAction.FINALISE
            else OperationalContext.THESIS_CURRENT
        )
        return requested, context
    if not existing_thesis_id:
        return RequestedAction.BUILD_THESIS, OperationalContext.NO_VALID_THESIS
    # After the exchange close the shared session clock correctly advances
    # ``last_completed_session``.  The data provider may not have finalised its
    # completed-session files yet, however.  Resolve that state before the
    # generic thesis-session mismatch check so partial evidence cannot be
    # promoted as a completed thesis.
    if snapshot.state is SessionState.AFTER_HOURS:
        if provider_session_finalised:
            return (
                RequestedAction.FINALISE,
                OperationalContext.CURRENT_SESSION_FINALISATION_DUE,
            )
        return RequestedAction.VALIDATE, OperationalContext.VALIDATION_DUE
    if existing_thesis_session != snapshot.last_completed_session:
        return RequestedAction.BUILD_THESIS, OperationalContext.THESIS_REFRESH_DUE
    if snapshot.state in {SessionState.PREMARKET, SessionState.REGULAR}:
        return RequestedAction.VALIDATE, OperationalContext.VALIDATION_DUE
    return RequestedAction.AUTO, OperationalContext.THESIS_CURRENT


def resolve_run_plan(
    *,
    requested_action: RequestedAction | str = RequestedAction.AUTO,
    as_of_utc: datetime,
    evidence_cutoff_utc: datetime | None = None,
    exchange_calendar: str = "XNYS",
    existing_thesis_id: str | None = None,
    existing_thesis_session: date | None = None,
    authorised_tickers: Iterable[str] = (),
    provider_session_finalised: bool = False,
    cache_coverage: Mapping[str, int] | None = None,
    pipeline_run_id: str | None = None,
    retry_of_invocation_id: str | None = None,
    supersedes_invocation_id: str | None = None,
) -> RunPlan:
    """Resolve a deterministic plan without provider calls or filesystem writes."""
    action = RequestedAction(str(getattr(requested_action, "value", requested_action)).upper())
    as_of = _normalise_instant(as_of_utc)
    cutoff = _normalise_instant(evidence_cutoff_utc or as_of)
    if cutoff > as_of:
        raise ValueError("evidence_cutoff_utc cannot be later than as_of_utc")
    if exchange_calendar.strip().upper() != "XNYS":
        raise ValueError("only the governed XNYS exchange calendar is supported")
    snapshot = session_snapshot(as_of)
    resolved, context = _resolve_action(
        action,
        snapshot,
        existing_thesis_id=existing_thesis_id,
        existing_thesis_session=existing_thesis_session,
        provider_session_finalised=provider_session_finalised,
    )
    tickers = tuple(sorted({ticker.strip().upper() for ticker in authorised_tickers if ticker.strip()}))
    cache = {str(key).upper(): max(0, int(value)) for key, value in (cache_coverage or {}).items()}

    stages_run: tuple[str, ...]
    stages_reuse: tuple[str, ...]
    requirements: list[DatasetRequirement] = []
    outputs: tuple[str, ...]
    ceiling: AuthorityCeiling
    if resolved is RequestedAction.BUILD_THESIS:
        stages_run = ("DISCOVERY", "COMPLETED_MARKET_PROFILE", "VANGUARD", "OPTIONS", "PUBLISH_THESIS")
        stages_reuse = ("CANONICAL_COMPLETED_DATA",)
        requirements = [
            DatasetRequirement(DatasetType.DAILY_OHLCV.value, snapshot.last_completed_session.isoformat(), EvidenceState.COMPLETED_SESSION.value, tickers, estimated_physical_requests=max(0, len(tickers) - cache.get("DAILY_OHLCV", 0))),
            DatasetRequirement(DatasetType.INTRADAY_BAR.value, snapshot.last_completed_session.isoformat(), EvidenceState.COMPLETED_SESSION.value, (), interval_minutes=5, estimated_physical_requests=max(0, len(tickers) - cache.get("INTRADAY_BAR", 0)), worklist_source="DISCOVERY_SURVIVORS", estimate_kind="CEILING"),
            DatasetRequirement(DatasetType.OPTION_CHAIN.value, snapshot.last_completed_session.isoformat(), EvidenceState.COMPLETED_SESSION.value, (), estimated_physical_requests=max(0, len(tickers) - cache.get("OPTION_CHAIN", 0)), worklist_source="DISCOVERY_SURVIVORS", estimate_kind="CEILING"),
        ]
        outputs = ("completed_thesis", "eod_opportunity_book", "decision_events")
        ceiling = AuthorityCeiling.EOD_PREPARED
    elif resolved is RequestedAction.VALIDATE:
        stages_run = ("UNDERLYING_VALIDATION", "SURVIVOR_OPTION_REFRESH")
        if snapshot.state is SessionState.REGULAR:
            stages_run += ("DEVELOPING_MARKET_PROFILE",)
        stages_run += ("EXECUTION_GATE", "PUBLISH_VALIDATION")
        stages_reuse = ("COMPLETED_THESIS", "COMPLETED_MARKET_PROFILE")
        session_date = snapshot.session_date or snapshot.last_completed_session
        requirements = [
            DatasetRequirement(DatasetType.UNDERLYING_NBBO.value, session_date.isoformat(), EvidenceState.CURRENT_QUOTE.value, tickers, estimated_physical_requests=max(0, len(tickers) - cache.get("UNDERLYING_NBBO", 0))),
            DatasetRequirement(DatasetType.EXACT_OPTION_QUOTE.value, session_date.isoformat(), EvidenceState.CURRENT_QUOTE.value, (), estimated_physical_requests=max(0, len(tickers) - cache.get("EXACT_OPTION_QUOTE", 0)), worklist_source="UNDERLYING_VALIDATION_SURVIVORS", estimate_kind="CEILING"),
        ]
        if snapshot.state is SessionState.REGULAR:
            requirements.append(DatasetRequirement(DatasetType.INTRADAY_BAR.value, session_date.isoformat(), EvidenceState.DEVELOPING_SESSION.value, (), interval_minutes=5, estimated_physical_requests=max(0, len(tickers) - cache.get("INTRADAY_BAR", 0)), worklist_source="UNDERLYING_VALIDATION_SURVIVORS", estimate_kind="CEILING"))
        outputs = ("validation_event", "execution_gate_result", "governed_handoff")
        ceiling = AuthorityCeiling.EXECUTION_GATE_ELIGIBLE
    elif resolved is RequestedAction.FINALISE:
        stages_run = ("FINALISE_COMPLETED_DATASETS", "BUILD_SUPERSEDING_THESIS")
        stages_reuse = ("DEVELOPING_SESSION_DATA",)
        outputs = ("completed_dataset_ids", "superseding_thesis")
        ceiling = AuthorityCeiling.EOD_PREPARED
    elif resolved is RequestedAction.REPLAY:
        stages_run = ("OFFLINE_REPLAY",)
        stages_reuse = ("CANONICAL_POINT_IN_TIME_DATA",)
        outputs = ("research_replay_result",)
        ceiling = AuthorityCeiling.RESEARCH_ONLY
    else:
        stages_run = ()
        stages_reuse = ("COMPLETED_THESIS",)
        outputs = ("reused_existing_thesis",)
        ceiling = AuthorityCeiling.REVIEW_ONLY

    estimated_requests = sum(item.estimated_physical_requests for item in requirements)
    run_identity_payload = {
        "resolved_action": resolved.value,
        "last_completed_session": snapshot.last_completed_session.isoformat(),
        "existing_thesis_id": existing_thesis_id,
        "tickers": tickers,
    }
    resolved_run_id = pipeline_run_id or _stable_id("run", run_identity_payload)
    invocation_payload = {
        "pipeline_run_id": resolved_run_id,
        "cutoff": iso_utc(cutoff),
        "session_state": snapshot.state.value,
        "worklists": tickers,
        "resolved_action": resolved.value,
    }
    invocation_id = _stable_id("inv", invocation_payload)
    if resolved is RequestedAction.BUILD_THESIS:
        worklists = {
            stage: tickers if stage == "DISCOVERY" else () for stage in stages_run
        }
    elif resolved is RequestedAction.VALIDATE:
        worklists = {
            stage: tickers if stage == "UNDERLYING_VALIDATION" else ()
            for stage in stages_run
        }
    else:
        worklists = {stage: tickers for stage in stages_run if tickers}
    return RunPlan(
        pipeline_run_id=resolved_run_id,
        invocation_id=invocation_id,
        requested_action=action.value,
        resolved_action=resolved.value,
        as_of_utc=iso_utc(as_of) or "",
        evidence_cutoff_utc=iso_utc(cutoff) or "",
        exchange_calendar="XNYS",
        session_state=snapshot.state.value,
        last_completed_session=snapshot.last_completed_session.isoformat(),
        current_session=snapshot.session_date.isoformat() if snapshot.session_date else None,
        operational_context=context.value,
        existing_thesis_id=existing_thesis_id,
        stages_to_run=stages_run,
        stages_to_reuse=stages_reuse,
        datasets_required=tuple(requirements),
        authorised_ticker_worklists=worklists,
        estimated_physical_requests=estimated_requests,
        estimated_provider_credits=estimated_requests,
        expected_outputs=outputs,
        execution_authority_ceiling=ceiling.value,
        retry_of_invocation_id=retry_of_invocation_id,
        supersedes_invocation_id=supersedes_invocation_id,
    )


class RunPlanStore:
    """Append-only SQLite store for immutable plan and invocation identities."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)

    def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS run_plans(
                    plan_hash TEXT PRIMARY KEY,
                    pipeline_run_id TEXT NOT NULL,
                    invocation_id TEXT NOT NULL UNIQUE,
                    evidence_cutoff_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    persisted_at_utc TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def persist(self, plan: RunPlan) -> bool:
        self.initialise()
        payload = json.dumps(plan.to_dict(), sort_keys=True, separators=(",", ":"))
        connection = sqlite3.connect(self.database_path)
        try:
            existing = connection.execute(
                "SELECT plan_hash, payload_json FROM run_plans WHERE invocation_id = ?",
                (plan.invocation_id,),
            ).fetchone()
            if existing:
                if existing[0] != plan.plan_hash or existing[1] != payload:
                    raise ValueError("invocation identity already has different immutable plan content")
                return False
            connection.execute(
                "INSERT INTO run_plans VALUES (?, ?, ?, ?, ?, ?)",
                (
                    plan.plan_hash,
                    plan.pipeline_run_id,
                    plan.invocation_id,
                    plan.evidence_cutoff_utc,
                    payload,
                    iso_utc(datetime.now(timezone.utc)),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return True

    def load(self, invocation_id: str) -> dict[str, Any] | None:
        self.initialise()
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT payload_json FROM run_plans WHERE invocation_id = ?",
                (invocation_id,),
            ).fetchone()
        finally:
            connection.close()
        return json.loads(row[0]) if row else None


def write_plan_atomic(plan: RunPlan, destination: Path | str) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return path
