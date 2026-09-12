"""Canonical request, scope, dataset, and resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping

from .errors import DatasetValidationError
from domain.market_evidence import (
    MarketEvidenceInvariantError,
    evaluate_evidence_freshness,
    evidence_request_identity,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalise_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


class DatasetType(str, Enum):
    DAILY_OHLCV = "DAILY_OHLCV"
    OPTION_CHAIN = "OPTION_CHAIN"
    CONTRACT_REFERENCE = "CONTRACT_REFERENCE"
    SECTOR_REGIME = "SECTOR_REGIME"
    LIVE_EQUITY = "LIVE_EQUITY"
    LIVE_OPTION = "LIVE_OPTION"
    MACRO_SNAPSHOT = "MACRO_SNAPSHOT"
    EXACT_OPTION_QUOTE = "EXACT_OPTION_QUOTE"
    UNDERLYING_NBBO = "UNDERLYING_NBBO"
    INTRADAY_BAR = "INTRADAY_BAR"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    GAMMA_EXPOSURE = "GAMMA_EXPOSURE"


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class ResolutionKind(str, Enum):
    EXACT_HIT = "EXACT_HIT"
    SUPERSET_HIT = "SUPERSET_HIT"
    PARTIAL_HIT = "PARTIAL_HIT"
    MISS = "MISS"


@dataclass(frozen=True, slots=True)
class DataScope:
    """Normalised, hashable definition of the requested data boundary."""

    start_date: date | None = None
    end_date: date | None = None
    fields: tuple[str, ...] = ()
    dte_min: int | None = None
    dte_max: int | None = None
    sides: tuple[str, ...] = ()
    extra: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", _normalise_strings(self.fields))
        object.__setattr__(self, "sides", _normalise_strings(self.sides))
        object.__setattr__(
            self,
            "extra",
            tuple(sorted((str(key).strip(), str(value).strip()) for key, value in self.extra)),
        )
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise DatasetValidationError("scope start_date is after end_date")
        if self.dte_min is not None and self.dte_min < 0:
            raise DatasetValidationError("dte_min cannot be negative")
        if self.dte_max is not None and self.dte_max < 0:
            raise DatasetValidationError("dte_max cannot be negative")
        if (
            self.dte_min is not None
            and self.dte_max is not None
            and self.dte_min > self.dte_max
        ):
            raise DatasetValidationError("dte_min is greater than dte_max")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "fields": list(self.fields),
            "dte_min": self.dte_min,
            "dte_max": self.dte_max,
            "sides": list(self.sides),
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DataScope":
        return cls(
            start_date=date.fromisoformat(value["start_date"])
            if value.get("start_date")
            else None,
            end_date=date.fromisoformat(value["end_date"])
            if value.get("end_date")
            else None,
            fields=tuple(value.get("fields") or ()),
            dte_min=value.get("dte_min"),
            dte_max=value.get("dte_max"),
            sides=tuple(value.get("sides") or ()),
            extra=tuple((value.get("extra") or {}).items()),
        )

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def covers(self, requested: "DataScope") -> bool:
        """Return whether this stored scope fully covers a requested scope."""
        if requested.start_date and (
            self.start_date is None or self.start_date > requested.start_date
        ):
            return False
        if requested.end_date and (
            self.end_date is None or self.end_date < requested.end_date
        ):
            return False
        if requested.fields and self.fields and not set(requested.fields) <= set(self.fields):
            return False
        if requested.dte_min is not None and (
            self.dte_min is None or self.dte_min > requested.dte_min
        ):
            return False
        if requested.dte_max is not None and (
            self.dte_max is None or self.dte_max < requested.dte_max
        ):
            return False
        if requested.sides and self.sides and not set(requested.sides) <= set(self.sides):
            return False
        return dict(requested.extra).items() <= dict(self.extra).items()

    def overlaps(self, requested: "DataScope") -> bool:
        if self.end_date and requested.start_date and self.end_date < requested.start_date:
            return False
        if requested.end_date and self.start_date and requested.end_date < self.start_date:
            return False
        if self.dte_max is not None and requested.dte_min is not None:
            if self.dte_max < requested.dte_min:
                return False
        if requested.dte_max is not None and self.dte_min is not None:
            if requested.dte_max < self.dte_min:
                return False
        if self.fields and requested.fields and not set(self.fields) & set(requested.fields):
            return False
        if self.sides and requested.sides and not set(self.sides) & set(requested.sides):
            return False
        return True


@dataclass(frozen=True, slots=True)
class DatasetRequest:
    run_id: str
    requesting_stage: str
    dataset_type: DatasetType
    instrument_id: str
    session_date: date
    scope: DataScope = field(default_factory=DataScope)
    freshness_seconds: int | None = None
    accepted_providers: tuple[str, ...] = ()
    adjustment_convention: str = "UNSPECIFIED"
    schema_version: str = "1"
    invocation_id: str | None = None
    evidence_cutoff_utc: datetime | None = None
    exchange_calendar: str = "XNYS"
    evidence_state: str = "COMPLETED_SESSION"

    def __post_init__(self) -> None:
        for name in ("run_id", "requesting_stage", "instrument_id"):
            if not str(getattr(self, name)).strip():
                raise DatasetValidationError(f"{name} is required")
        if self.freshness_seconds is not None and self.freshness_seconds < 0:
            raise DatasetValidationError("freshness_seconds cannot be negative")
        invocation_id = str(self.invocation_id or self.run_id).strip()
        if not invocation_id:
            raise DatasetValidationError("invocation_id is required")
        cutoff = self.evidence_cutoff_utc
        if cutoff is not None and cutoff.tzinfo is None:
            raise DatasetValidationError("evidence_cutoff_utc must be timezone-aware")
        calendar = str(self.exchange_calendar).strip().upper()
        if not calendar:
            raise DatasetValidationError("exchange_calendar is required")
        evidence_state = str(self.evidence_state).strip().upper()
        if not evidence_state:
            raise DatasetValidationError("evidence_state is required")
        object.__setattr__(self, "instrument_id", self.instrument_id.strip().upper())
        object.__setattr__(self, "requesting_stage", self.requesting_stage.strip().upper())
        object.__setattr__(self, "invocation_id", invocation_id)
        object.__setattr__(self, "evidence_cutoff_utc", parse_utc(cutoff))
        object.__setattr__(self, "exchange_calendar", calendar)
        object.__setattr__(self, "evidence_state", evidence_state)
        object.__setattr__(
            self, "accepted_providers", _normalise_strings(self.accepted_providers)
        )

    @property
    def request_fingerprint(self) -> str:
        return evidence_request_identity(
            run_id=self.run_id,
            invocation_id=str(self.invocation_id),
            requesting_stage=self.requesting_stage,
            dataset_type=self.dataset_type.value,
            instrument_id=self.instrument_id,
            session_date=self.session_date,
            scope_fingerprint=self.scope.fingerprint,
            evidence_cutoff_utc=iso_utc(self.evidence_cutoff_utc),
            exchange_calendar=self.exchange_calendar,
            evidence_state=self.evidence_state,
        )


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    dataset_id: str
    dataset_type: DatasetType
    instrument_id: str
    session_date: date
    scope: DataScope
    provider: str
    content_hash: str
    completeness_status: CompletenessStatus
    storage_uri: str
    observed_at: datetime
    as_of: datetime
    expires_at: datetime | None = None
    adjustment_convention: str = "UNSPECIFIED"
    schema_version: str = "1"
    quality_flags: tuple[str, ...] = ()
    parent_dataset_ids: tuple[str, ...] = ()
    source_run_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "dataset_id",
            "instrument_id",
            "provider",
            "content_hash",
            "storage_uri",
        ):
            if not str(getattr(self, name)).strip():
                raise DatasetValidationError(f"{name} is required")
        object.__setattr__(self, "instrument_id", self.instrument_id.strip().upper())
        object.__setattr__(self, "provider", self.provider.strip().upper())
        object.__setattr__(self, "observed_at", parse_utc(self.observed_at))
        object.__setattr__(self, "as_of", parse_utc(self.as_of))
        object.__setattr__(self, "expires_at", parse_utc(self.expires_at))

    def is_fresh(
        self, freshness_seconds: int | None, *, now: datetime | None = None
    ) -> bool:
        instant = parse_utc(now) or utc_now()
        try:
            return evaluate_evidence_freshness(
                as_of=self.as_of,
                now=instant,
                freshness_seconds=freshness_seconds,
                expires_at=self.expires_at,
            ).fresh
        except MarketEvidenceInvariantError as error:
            raise DatasetValidationError(str(error)) from error


@dataclass(frozen=True, slots=True)
class DatasetResolution:
    kind: ResolutionKind
    request: DatasetRequest
    records: tuple[DatasetRecord, ...] = ()
    missing_scope: DataScope | None = None
    reason: str = ""

    @property
    def requires_provider_fetch(self) -> bool:
        return self.kind in {ResolutionKind.PARTIAL_HIT, ResolutionKind.MISS}
