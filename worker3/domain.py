"""Pure evidence and assessment contracts. No IO, provider SDK or pipeline imports."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re


class ContractError(ValueError):
    pass


class Direction(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"


class ClaimType(str, Enum):
    OBSERVATION = "OBSERVATION"
    INTERPRETATION = "INTERPRETATION"
    HYPOTHESIS = "HYPOTHESIS"


class Section(str, Enum):
    SUMMARY = "SUMMARY"
    COMPANY = "COMPANY"
    CAMPAIGN = "CAMPAIGN"
    BEHAVIOUR = "BEHAVIOUR"
    CONTRACT = "CONTRACT"
    CONTEXT = "CONTEXT"
    SCENARIOS = "SCENARIOS"
    CHANGES = "CHANGES"


def nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{name} must be a nonempty trimmed string")


def sha(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError("expected lowercase SHA256")


def utc(value: str) -> str:
    nonempty(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError("timestamp must have a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def instant(value: str) -> datetime:
    return datetime.fromisoformat(utc(value).replace("Z", "+00:00"))


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Identity:
    run_id: str
    invocation_id: str
    trading_session: str
    ticker: str
    thesis_id: str
    direction: Direction
    planned_hold_sessions: int
    contract_id: str | None = None
    contract_symbol: str | None = None
    selection_version: str | None = None

    def __post_init__(self):
        for field in ("run_id", "invocation_id", "ticker", "thesis_id"):
            nonempty(getattr(self, field), field)
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", self.ticker):
            raise ContractError("ticker must be canonical uppercase")
        if not isinstance(self.direction, Direction):
            raise ContractError("direction must be explicit")
        try:
            if date.fromisoformat(self.trading_session).isoformat() != self.trading_session:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ContractError("trading_session must be YYYY-MM-DD") from exc
        if type(self.planned_hold_sessions) is not int or not 1 <= self.planned_hold_sessions <= 20:
            raise ContractError("planned hold must be 1–20 sessions, not option DTE")
        fields = (self.contract_id, self.contract_symbol, self.selection_version)
        if any(x is not None for x in fields):
            if self.direction == Direction.NON_DIRECTIONAL:
                raise ContractError("long option contract requires CALL or PUT")
            for value in fields:
                nonempty(value, "selected contract identity")


@dataclass(frozen=True, slots=True)
class Observation:
    evidence_id: str
    field: str
    value: str | int | float | bool | None
    unit: str
    source_id: str
    source_hash: str
    observed_at: str
    available_at: str
    status: str = "AVAILABLE"
    scope: str = "TICKER"
    ticker: str | None = None
    contract_id: str | None = None
    calculation_version: str | None = None

    def __post_init__(self):
        for name in ("evidence_id", "field", "unit", "source_id"):
            nonempty(getattr(self, name), name)
        sha(self.source_hash)
        if type(self.value) not in (str, int, float, bool, type(None)):
            raise ContractError("observation value must be an immutable JSON scalar")
        if type(self.value) is float and not math.isfinite(self.value):
            raise ContractError("non-finite evidence rejected, never converted to zero")
        if self.status not in ("AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"):
            raise ContractError("unknown evidence status")
        if (self.status == "AVAILABLE") != (self.value is not None):
            raise ContractError("availability must agree with value")
        if self.scope not in ("TICKER", "CONTRACT", "CONTEXT"):
            raise ContractError("unknown evidence scope")
        if self.scope == "CONTEXT" and (self.ticker is not None or self.contract_id is not None):
            raise ContractError("context scope cannot disguise ticker/contract evidence")
        if self.scope in ("TICKER", "CONTRACT"):
            nonempty(self.ticker, "evidence ticker")
        if self.scope == "CONTRACT":
            nonempty(self.contract_id, "evidence contract")
        elif self.contract_id is not None:
            raise ContractError("contract requires CONTRACT scope")
        if self.calculation_version is not None:
            nonempty(self.calculation_version, "calculation_version")
        object.__setattr__(self, "observed_at", utc(self.observed_at))
        object.__setattr__(self, "available_at", utc(self.available_at))
        if instant(self.available_at) < instant(self.observed_at):
            raise ContractError("availability precedes observation")


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    identity: Identity
    evidence_cutoff_utc: str
    observations: tuple[Observation, ...]
    schema_version: str = "analyst_evidence_v1"

    def __post_init__(self):
        if not isinstance(self.identity, Identity):
            raise ContractError("identity required")
        if self.schema_version != "analyst_evidence_v1":
            raise ContractError("unsupported evidence schema")
        if type(self.observations) is not tuple or not self.observations:
            raise ContractError("nonempty immutable observations required")
        object.__setattr__(self, "evidence_cutoff_utc", utc(self.evidence_cutoff_utc))
        seen = set()
        for obs in self.observations:
            if not isinstance(obs, Observation) or obs.evidence_id in seen:
                raise ContractError("invalid or duplicate observation")
            seen.add(obs.evidence_id)
            if instant(obs.available_at) > instant(self.evidence_cutoff_utc):
                raise ContractError("evidence was unavailable at cutoff")
            if obs.scope != "CONTEXT" and obs.ticker != self.identity.ticker:
                raise ContractError("cross-ticker evidence")
            if obs.scope == "CONTRACT" and obs.contract_id != self.identity.contract_id:
                raise ContractError("cross-contract evidence")

    @property
    def evidence_hash(self) -> str:
        data = asdict(self)
        data["observations"] = sorted(data["observations"], key=lambda x: x["evidence_id"])
        return digest(data)


@dataclass(frozen=True, slots=True)
class WorkerJob:
    bundle: EvidenceBundle
    provider: str
    model: str
    prompt_version: str
    task_type: str = "INITIAL_ASSESSMENT"
    previous_assessment_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.bundle, EvidenceBundle):
            raise ContractError("validated evidence bundle required")
        for name in ("provider", "model", "prompt_version"):
            nonempty(getattr(self, name), name)
        if self.task_type not in ("INITIAL_ASSESSMENT", "REFRESH_ASSESSMENT", "CONTEXT_UPDATE"):
            raise ContractError("unknown task type")
        if self.task_type != "INITIAL_ASSESSMENT":
            nonempty(self.previous_assessment_id, "previous assessment")
        elif self.previous_assessment_id is not None:
            raise ContractError("initial assessment has no predecessor")

    @property
    def job_key(self) -> str:
        return digest({"evidence": self.bundle.evidence_hash, "provider": self.provider,
                       "model": self.model, "prompt": self.prompt_version,
                       "task": self.task_type, "previous": self.previous_assessment_id})
