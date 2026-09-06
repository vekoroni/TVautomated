"""Pure Run Planning domain for AVSHUNTER.

This module owns plan decisions and stable business identities.  It has no
filesystem, SQLite, provider, environment-variable or exchange-calendar
dependency.  Adapters supply the observed session facts and persist the
resulting immutable plan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping

from .session_authority import (
    SessionFacts,
    SessionPhase,
    resolve_session_authority,
)


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


class OperationalContext(str, Enum):
    NO_VALID_THESIS = "NO_VALID_THESIS"
    THESIS_CURRENT = "THESIS_CURRENT"
    THESIS_REFRESH_DUE = "THESIS_REFRESH_DUE"
    VALIDATION_DUE = "VALIDATION_DUE"
    CURRENT_SESSION_FINALISATION_DUE = "CURRENT_SESSION_FINALISATION_DUE"
    REPLAY = "REPLAY"


class PlanningEvidenceState(str, Enum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    DEVELOPING_SESSION = "DEVELOPING_SESSION"
    CURRENT_QUOTE = "CURRENT_QUOTE"


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
        for name in ("cache_exact_hits", "cache_partial_hits", "estimated_physical_requests"):
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
            "pipeline_run_id", "invocation_id", "requested_action", "resolved_action",
            "as_of_utc", "evidence_cutoff_utc", "exchange_calendar", "session_state",
            "last_completed_session", "operational_context", "execution_authority_ceiling",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if self.estimated_physical_requests < 0 or self.estimated_provider_credits < 0:
            raise ValueError("request and credit estimates cannot be negative")
        object.__setattr__(
            self,
            "authorised_ticker_worklists",
            {
                str(stage).strip().upper(): tuple(
                    sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})
                )
                for stage, tickers in self.authorised_ticker_worklists.items()
            },
        )
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


@dataclass(frozen=True, slots=True)
class RunPlanningContext:
    as_of_utc: datetime
    evidence_cutoff_utc: datetime
    session_facts: SessionFacts
    exchange_calendar: str = "XNYS"
    existing_thesis_id: str | None = None
    existing_thesis_session: date | None = None
    authorised_tickers: tuple[str, ...] = ()
    provider_session_finalised: bool = False
    cache_coverage: Mapping[str, int] | None = None
    pipeline_run_id: str | None = None
    retry_of_invocation_id: str | None = None
    supersedes_invocation_id: str | None = None


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"


def thesis_identity(
    *, ticker: str, completed_session: date, governed_direction: str,
    evidence_ids: Iterable[str], model_version: str, thesis_version: int,
) -> str:
    if thesis_version < 1:
        raise ValueError("thesis_version must be positive")
    return _stable_id("thesis", {
        "ticker": ticker.strip().upper(),
        "completed_session": completed_session.isoformat(),
        "governed_direction": governed_direction.strip().upper(),
        "evidence_ids": sorted({value.strip() for value in evidence_ids if value.strip()}),
        "model_version": model_version.strip(),
        "thesis_version": thesis_version,
    })


def validation_event_identity(
    *, thesis_id: str, evidence_cutoff_utc: datetime,
    underlying_observation_id: str, quote_observation_id: str | None = None,
    developing_profile_evidence_id: str | None = None,
) -> str:
    cutoff = _normalise_instant(evidence_cutoff_utc)
    return _stable_id("validation", {
        "thesis_id": thesis_id.strip(),
        "evidence_cutoff_utc": _iso_utc(cutoff),
        "underlying_observation_id": underlying_observation_id.strip(),
        "quote_observation_id": (quote_observation_id or "").strip(),
        "developing_profile_evidence_id": (developing_profile_evidence_id or "").strip(),
    })


def evidence_identity(
    *, evidence_type: str, input_dataset_ids: Iterable[str],
    calculation_version: str, content_hash: str,
) -> str:
    return _stable_id("evidence", {
        "evidence_type": evidence_type.strip().upper(),
        "input_dataset_ids": sorted({value.strip() for value in input_dataset_ids if value.strip()}),
        "calculation_version": calculation_version.strip(),
        "content_hash": content_hash.strip().lower(),
    })


def contract_episode_identity(
    *, thesis_id: str, strategy: str, occ_symbols: Iterable[str]
) -> str:
    return _stable_id("contract", {
        "thesis_id": thesis_id.strip(),
        "strategy": strategy.strip().upper(),
        "occ_symbols": sorted({symbol.strip().upper() for symbol in occ_symbols if symbol.strip()}),
    })


def quote_observation_identity(
    *, contract_episode_id: str, provider_observed_at_utc: datetime,
    content_hash: str,
) -> str:
    return _stable_id("quote", {
        "contract_episode_id": contract_episode_id.strip(),
        "provider_observed_at_utc": _iso_utc(_normalise_instant(provider_observed_at_utc)),
        "content_hash": content_hash.strip().lower(),
    })


def _normalise_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("as_of_utc and evidence_cutoff_utc must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _resolve_action(
    requested: RequestedAction,
    context: RunPlanningContext,
) -> tuple[RequestedAction, OperationalContext]:
    facts = context.session_facts
    if requested is RequestedAction.REPLAY:
        return requested, OperationalContext.REPLAY
    if requested is not RequestedAction.AUTO:
        resolved_context = (
            OperationalContext.NO_VALID_THESIS
            if requested is RequestedAction.BUILD_THESIS and not context.existing_thesis_id
            else OperationalContext.VALIDATION_DUE
            if requested is RequestedAction.VALIDATE
            else OperationalContext.CURRENT_SESSION_FINALISATION_DUE
            if requested is RequestedAction.FINALISE
            else OperationalContext.THESIS_CURRENT
        )
        return requested, resolved_context
    if not context.existing_thesis_id:
        return RequestedAction.BUILD_THESIS, OperationalContext.NO_VALID_THESIS
    if facts.phase is SessionPhase.AFTER_HOURS:
        if context.provider_session_finalised:
            return RequestedAction.FINALISE, OperationalContext.CURRENT_SESSION_FINALISATION_DUE
        return RequestedAction.VALIDATE, OperationalContext.VALIDATION_DUE
    if context.existing_thesis_session != facts.last_completed_session:
        return RequestedAction.BUILD_THESIS, OperationalContext.THESIS_REFRESH_DUE
    if facts.phase in {SessionPhase.PREMARKET, SessionPhase.REGULAR}:
        return RequestedAction.VALIDATE, OperationalContext.VALIDATION_DUE
    return RequestedAction.AUTO, OperationalContext.THESIS_CURRENT


def resolve_plan(
    *,
    requested_action: RequestedAction | str = RequestedAction.AUTO,
    context: RunPlanningContext,
) -> RunPlan:
    """Resolve a deterministic immutable plan from domain facts only."""
    action = RequestedAction(str(getattr(requested_action, "value", requested_action)).upper())
    as_of = _normalise_instant(context.as_of_utc)
    cutoff = _normalise_instant(context.evidence_cutoff_utc)
    if cutoff > as_of:
        raise ValueError("evidence_cutoff_utc cannot be later than as_of_utc")
    if context.exchange_calendar.strip().upper() != "XNYS":
        raise ValueError("only the governed XNYS exchange calendar is supported")

    completed_authority = resolve_session_authority(
        requested_mode="AUTO", facts=context.session_facts
    )
    completed_session = completed_authority.provider_query_end
    resolved, operational_context = _resolve_action(action, context)
    tickers = tuple(sorted({ticker.strip().upper() for ticker in context.authorised_tickers if ticker.strip()}))
    cache = {
        str(key).upper(): max(0, int(value))
        for key, value in (context.cache_coverage or {}).items()
    }

    requirements: list[DatasetRequirement] = []
    if resolved is RequestedAction.BUILD_THESIS:
        stages_run = ("DISCOVERY", "COMPLETED_MARKET_PROFILE", "VANGUARD", "OPTIONS", "PUBLISH_THESIS")
        stages_reuse = ("CANONICAL_COMPLETED_DATA",)
        session_text = completed_session.isoformat()
        requirements = [
            DatasetRequirement("DAILY_OHLCV", session_text, PlanningEvidenceState.COMPLETED_SESSION.value, tickers, estimated_physical_requests=max(0, len(tickers) - cache.get("DAILY_OHLCV", 0))),
            DatasetRequirement("INTRADAY_BAR", session_text, PlanningEvidenceState.COMPLETED_SESSION.value, (), interval_minutes=5, estimated_physical_requests=max(0, len(tickers) - cache.get("INTRADAY_BAR", 0)), worklist_source="DISCOVERY_SURVIVORS", estimate_kind="CEILING"),
            DatasetRequirement("OPTION_CHAIN", session_text, PlanningEvidenceState.COMPLETED_SESSION.value, (), estimated_physical_requests=max(0, len(tickers) - cache.get("OPTION_CHAIN", 0)), worklist_source="DISCOVERY_SURVIVORS", estimate_kind="CEILING"),
        ]
        outputs = ("completed_thesis", "eod_opportunity_book", "decision_events")
        ceiling = AuthorityCeiling.EOD_PREPARED
    elif resolved is RequestedAction.VALIDATE:
        stages_run = ("UNDERLYING_VALIDATION", "SURVIVOR_OPTION_REFRESH")
        if context.session_facts.phase is SessionPhase.REGULAR:
            stages_run += ("DEVELOPING_MARKET_PROFILE",)
        stages_run += ("EXECUTION_GATE", "PUBLISH_VALIDATION")
        stages_reuse = ("COMPLETED_THESIS", "COMPLETED_MARKET_PROFILE")
        session_date = context.session_facts.current_session or completed_session
        requirements = [
            DatasetRequirement("UNDERLYING_NBBO", session_date.isoformat(), PlanningEvidenceState.CURRENT_QUOTE.value, tickers, estimated_physical_requests=max(0, len(tickers) - cache.get("UNDERLYING_NBBO", 0))),
            DatasetRequirement("EXACT_OPTION_QUOTE", session_date.isoformat(), PlanningEvidenceState.CURRENT_QUOTE.value, (), estimated_physical_requests=max(0, len(tickers) - cache.get("EXACT_OPTION_QUOTE", 0)), worklist_source="UNDERLYING_VALIDATION_SURVIVORS", estimate_kind="CEILING"),
        ]
        if context.session_facts.phase is SessionPhase.REGULAR:
            requirements.append(DatasetRequirement("INTRADAY_BAR", session_date.isoformat(), PlanningEvidenceState.DEVELOPING_SESSION.value, (), interval_minutes=5, estimated_physical_requests=max(0, len(tickers) - cache.get("INTRADAY_BAR", 0)), worklist_source="UNDERLYING_VALIDATION_SURVIVORS", estimate_kind="CEILING"))
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
    run_payload = {
        "resolved_action": resolved.value,
        "last_completed_session": completed_session.isoformat(),
        "existing_thesis_id": context.existing_thesis_id,
        "tickers": tickers,
    }
    run_id = context.pipeline_run_id or _stable_id("run", run_payload)
    invocation_id = _stable_id("inv", {
        "pipeline_run_id": run_id,
        "cutoff": _iso_utc(cutoff),
        "session_state": context.session_facts.phase.value,
        "worklists": tickers,
        "resolved_action": resolved.value,
    })
    if resolved is RequestedAction.BUILD_THESIS:
        worklists = {stage: tickers if stage == "DISCOVERY" else () for stage in stages_run}
    elif resolved is RequestedAction.VALIDATE:
        worklists = {stage: tickers if stage == "UNDERLYING_VALIDATION" else () for stage in stages_run}
    else:
        worklists = {stage: tickers for stage in stages_run if tickers}

    return RunPlan(
        pipeline_run_id=run_id,
        invocation_id=invocation_id,
        requested_action=action.value,
        resolved_action=resolved.value,
        as_of_utc=_iso_utc(as_of),
        evidence_cutoff_utc=_iso_utc(cutoff),
        exchange_calendar="XNYS",
        session_state=context.session_facts.phase.value,
        last_completed_session=completed_session.isoformat(),
        current_session=(context.session_facts.current_session.isoformat() if context.session_facts.current_session else None),
        operational_context=operational_context.value,
        existing_thesis_id=context.existing_thesis_id,
        stages_to_run=stages_run,
        stages_to_reuse=stages_reuse,
        datasets_required=tuple(requirements),
        authorised_ticker_worklists=worklists,
        estimated_physical_requests=estimated_requests,
        estimated_provider_credits=estimated_requests,
        expected_outputs=outputs,
        execution_authority_ceiling=ceiling.value,
        retry_of_invocation_id=context.retry_of_invocation_id,
        supersedes_invocation_id=context.supersedes_invocation_id,
    )
