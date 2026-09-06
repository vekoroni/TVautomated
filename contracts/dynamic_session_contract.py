"""Frozen vocabulary and release flags for dynamic session orchestration.

This module is deliberately side-effect free.  The enums describe evidence;
they do not grant execution or capital authority.  Every new feature flag is
disabled by default so Phase 0 cannot change the production trading path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
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
    APPROVED_FALLBACK = "APPROVED_FALLBACK"


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
    INVALIDATION_MISSING = "INVALIDATION_MISSING"
    STRUCTURAL_TARGET_UNRESOLVED = "STRUCTURAL_TARGET_UNRESOLVED"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    MISSING_INTERVALS = "MISSING_INTERVALS"
    OHLC_INVALID = "OHLC_INVALID"
    CORPORATE_ACTION_UNRESOLVED = "CORPORATE_ACTION_UNRESOLVED"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    PROVIDER_FAILURE_THRESHOLD = "PROVIDER_FAILURE_THRESHOLD"
    STALE_SOURCE_FALLBACK = "STALE_SOURCE_FALLBACK"
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
    completed_profile_stage: bool = False

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "DynamicSessionFeatureFlags":
        env = os.environ if environment is None else environment
        # An explicit mapping is an isolated/test contract and preserves the
        # Phase-0 all-disabled default. Production entry points call this
        # method without an argument and therefore resolve the checked-in,
        # governed runtime profile below.
        configured = (
            load_governed_runtime_profile()["feature_flags"]
            if environment is None
            else {name: False for name in FEATURE_FLAG_ENV_VARS}
        )
        disable_all = environment is None and _as_bool(
            env.get("AVSHUNTER_DYNAMIC_RELEASE_DISABLE_ALL")
        )
        if disable_all:
            configured = {name: False for name in FEATURE_FLAG_ENV_VARS}

        def resolved(name: str) -> bool:
            if disable_all:
                return False
            default = bool(configured.get(name, False))
            if name not in env:
                return default
            # A malformed override is a safe disable, consistent with the
            # original Phase-0 contract. Typos never inherit an enabled
            # production default.
            requested = _as_bool(env.get(name), default=False)
            # Environment switches may independently disable a governed
            # capability for rollback, but cannot promote a capability that
            # the release profile has deliberately withheld (notably AUTO).
            if environment is None and requested and not default:
                raise RuntimeError(
                    f"{name}=1 would exceed the governed runtime profile"
                )
            return requested

        return cls(
            plan_engine=resolved("AVSHUNTER_DYNAMIC_PLAN_ENABLED"),
            completed_thesis_builder=resolved("AVSHUNTER_DYNAMIC_THESIS_ENABLED"),
            validation_gate=resolved("AVSHUNTER_DYNAMIC_VALIDATION_ENABLED"),
            profile_lifecycle=resolved("AVSHUNTER_PROFILE_LIFECYCLE_ENABLED"),
            lab_dynamic_view=resolved("AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED"),
            interpreter_dynamic_resolver=resolved(
                "AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED"
            ),
            decision_outcome_ledger=resolved(
                "AVSHUNTER_DECISION_LEDGER_ENABLED"
            ),
            auto_dispatcher=resolved("AVSHUNTER_DYNAMIC_AUTO_ENABLED"),
            completed_profile_stage=resolved(
                "AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED"
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
    "AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED",
)


RUNTIME_PROFILE_PATH = Path(__file__).with_name("dynamic_session_runtime_v1.json")
RUNTIME_PROFILE_CONTRACT_ID = "AVS-DDD-RUNTIME-ACTIVATION"
RUNTIME_PROFILE_STATUSES = frozenset(
    {"DISABLED", "CONTROLLED_LIVE_CYCLE", "PRODUCTION"}
)


def _profile_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_governed_runtime_profile(path: Path | str | None = None) -> dict[str, object]:
    """Load and validate the single checked-in DDD runtime activation profile.

    A malformed, incomplete or authority-escalating profile fails startup.  It
    is never interpreted as an instruction to fall back to legacy behaviour.
    """

    profile_path = Path(path) if path is not None else RUNTIME_PROFILE_PATH
    try:
        payload = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"governed DDD runtime profile is unavailable: {profile_path}: {error}"
        ) from error
    if payload.get("contract_id") != RUNTIME_PROFILE_CONTRACT_ID:
        raise RuntimeError("governed DDD runtime profile contract_id mismatch")
    status = str(payload.get("status") or "").strip().upper()
    if status not in RUNTIME_PROFILE_STATUSES:
        raise RuntimeError(f"invalid governed DDD runtime profile status: {status}")
    raw_flags = payload.get("feature_flags")
    if not isinstance(raw_flags, dict) or set(raw_flags) != set(FEATURE_FLAG_ENV_VARS):
        raise RuntimeError("governed DDD runtime profile must define every feature flag exactly once")
    if any(type(value) is not bool for value in raw_flags.values()):
        raise RuntimeError("governed DDD runtime profile feature flags must be booleans")
    flags = {name: bool(raw_flags[name]) for name in FEATURE_FLAG_ENV_VARS}
    if flags["AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED"] != flags[
        "AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED"
    ]:
        raise RuntimeError("Lab and Interpreter dynamic activation must be atomic")
    if status == "DISABLED" and any(flags.values()):
        raise RuntimeError("DISABLED governed DDD runtime profile contains enabled flags")
    if status == "CONTROLLED_LIVE_CYCLE":
        required = set(FEATURE_FLAG_ENV_VARS) - {"AVSHUNTER_DYNAMIC_AUTO_ENABLED"}
        if not all(flags[name] for name in required) or flags[
            "AVSHUNTER_DYNAMIC_AUTO_ENABLED"
        ]:
            raise RuntimeError(
                "CONTROLLED_LIVE_CYCLE must enable explicit DDD services and withhold AUTO"
            )
    if status == "PRODUCTION" and not all(flags.values()):
        raise RuntimeError("PRODUCTION governed DDD runtime profile must enable all flags")
    rollback = payload.get("rollback_feature_flags")
    if not isinstance(rollback, dict) or set(rollback) != set(FEATURE_FLAG_ENV_VARS):
        raise RuntimeError("governed DDD runtime profile requires a complete rollback flag set")
    if any(value is not False for value in rollback.values()):
        raise RuntimeError("governed DDD rollback profile must disable every feature")
    return {
        **payload,
        "status": status,
        "feature_flags": flags,
        "path": str(profile_path.resolve()),
        "sha256": _profile_sha256(profile_path),
    }


def governed_runtime_profile_summary() -> dict[str, object]:
    """Return log/manifest-safe activation metadata without changing state."""

    profile = load_governed_runtime_profile()
    return {
        "contract_id": profile["contract_id"],
        "version": profile.get("version"),
        "release_id": profile.get("release_id"),
        "status": profile["status"],
        "path": profile["path"],
        "sha256": profile["sha256"],
    }
