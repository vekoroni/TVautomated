"""Frozen vocabulary and release flags for dynamic session orchestration.

This module is deliberately side-effect free.  The enums describe evidence;
they do not grant execution or capital authority.  Every new feature flag is
disabled by default so Phase 0 cannot change the production trading path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from typing import Mapping


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class OperationalContext(_ValueEnum):
    NO_VALID_THESIS = "NO_VALID_THESIS"
    THESIS_CURRENT = "THESIS_CURRENT"
    THESIS_REFRESH_DUE = "THESIS_REFRESH_DUE"
    VALIDATION_DUE = "VALIDATION_DUE"
    VALIDATION_CURRENT = "VALIDATION_CURRENT"
    CURRENT_SESSION_FINALISATION_DUE = "CURRENT_SESSION_FINALISATION_DUE"
    REPLAY = "REPLAY"


class EvidenceState(_ValueEnum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    DEVELOPING_SESSION = "DEVELOPING_SESSION"
    PENDING_MARKET_OPEN = "PENDING_MARKET_OPEN"
    PARTIAL_SESSION = "PARTIAL_SESSION"
    CURRENT_QUOTE = "CURRENT_QUOTE"
    PRIOR_SESSION_QUOTE = "PRIOR_SESSION_QUOTE"
    DEFERRED_NOT_YET_OBSERVABLE = "DEFERRED_NOT_YET_OBSERVABLE"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    DATA_DEFECT = "DATA_DEFECT"
    SUPERSEDED = "SUPERSEDED"
    NOT_EVALUATED = "NOT_EVALUATED"


class ProfileLifecycleState(_ValueEnum):
    COMPLETED_SESSION = "COMPLETED_SESSION"
    DEVELOPING_SESSION = "DEVELOPING_SESSION"
    PENDING_MARKET_OPEN = "PENDING_MARKET_OPEN"
    PARTIAL_SESSION = "PARTIAL_SESSION"
    NOT_EVALUATED = "NOT_EVALUATED"
    DEFERRED = "DEFERRED"


class ProfileCadence(_ValueEnum):
    ONE_MINUTE = "ONE_MINUTE"
    FIVE_MINUTE = "FIVE_MINUTE"
    FIFTEEN_MINUTE = "FIFTEEN_MINUTE"
    THIRTY_MINUTE = "THIRTY_MINUTE"
    UNKNOWN = "UNKNOWN"


class EvidenceOrigin(_ValueEnum):
    CANONICAL_CACHE = "CANONICAL_CACHE"
    MARKETDATA_API = "MARKETDATA_API"
    REPLAY_FIXTURE = "REPLAY_FIXTURE"
    DERIVED_CANONICAL = "DERIVED_CANONICAL"
    MANUAL_GOVERNED_INPUT = "MANUAL_GOVERNED_INPUT"


class DataExceptionReason(_ValueEnum):
    NOT_YET_OBSERVABLE = "NOT_YET_OBSERVABLE"
    TICKER_INACTIVE = "TICKER_INACTIVE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ENTITLEMENT_DENIED = "ENTITLEMENT_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    INSUFFICIENT_BARS = "INSUFFICIENT_BARS"
    INCOMPLETE_SESSION = "INCOMPLETE_SESSION"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    MISSING_INTERVALS = "MISSING_INTERVALS"
    OHLC_INVALID = "OHLC_INVALID"
    CORPORATE_ACTION_UNRESOLVED = "CORPORATE_ACTION_UNRESOLVED"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    PROVIDER_FAILURE_THRESHOLD = "PROVIDER_FAILURE_THRESHOLD"
    POPULATION_RECONCILIATION_FAILED = "POPULATION_RECONCILIATION_FAILED"
    NON_ATOMIC_PUBLICATION = "NON_ATOMIC_PUBLICATION"


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off", ""}:
        return False
    return default


@dataclass(frozen=True, slots=True)
class DynamicSessionFeatureFlags:
    """Independently reversible switches; all default to disabled."""

    plan_engine: bool = False
    completed_thesis_builder: bool = False
    validation_gate: bool = False
    profile_lifecycle: bool = False
    lab_dynamic_view: bool = False
    interpreter_dynamic_resolver: bool = False
    decision_outcome_ledger: bool = False
    auto_dispatcher: bool = False

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "DynamicSessionFeatureFlags":
        env = os.environ if environment is None else environment
        return cls(
            plan_engine=_as_bool(env.get("AVSHUNTER_DYNAMIC_PLAN_ENABLED")),
            completed_thesis_builder=_as_bool(
                env.get("AVSHUNTER_DYNAMIC_THESIS_ENABLED")
            ),
            validation_gate=_as_bool(
                env.get("AVSHUNTER_DYNAMIC_VALIDATION_ENABLED")
            ),
            profile_lifecycle=_as_bool(
                env.get("AVSHUNTER_PROFILE_LIFECYCLE_ENABLED")
            ),
            lab_dynamic_view=_as_bool(
                env.get("AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED")
            ),
            interpreter_dynamic_resolver=_as_bool(
                env.get("AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED")
            ),
            decision_outcome_ledger=_as_bool(
                env.get("AVSHUNTER_DECISION_LEDGER_ENABLED")
            ),
            auto_dispatcher=_as_bool(
                env.get("AVSHUNTER_DYNAMIC_AUTO_ENABLED")
            ),
        )


FEATURE_FLAG_ENV_VARS = (
    "AVSHUNTER_DYNAMIC_PLAN_ENABLED",
    "AVSHUNTER_DYNAMIC_THESIS_ENABLED",
    "AVSHUNTER_DYNAMIC_VALIDATION_ENABLED",
    "AVSHUNTER_PROFILE_LIFECYCLE_ENABLED",
    "AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED",
    "AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED",
    "AVSHUNTER_DECISION_LEDGER_ENABLED",
    "AVSHUNTER_DYNAMIC_AUTO_ENABLED",
)
