"""Business rules for the append-only Decision and Outcome Ledger.

This module owns event identity, vocabulary, causal-link invariants and the
ledger's authority ceiling.  It deliberately knows nothing about SQLite,
files, providers, pandas or the Intelligence Lab.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


LEDGER_SCHEMA_VERSION = "decision_outcome_ledger_v2"
LEDGER_AUTHORITY = "OBSERVATION_ONLY"


class LedgerEventType(str, Enum):
    THESIS_CREATED = "THESIS_CREATED"
    CANDIDATE_DECISION = "CANDIDATE_DECISION"
    VALIDATION = "VALIDATION"
    EXECUTION_DECISION = "EXECUTION_DECISION"
    PRESENTATION_DECISION = "PRESENTATION_DECISION"
    FILL_RECORDED = "FILL_RECORDED"
    TRADE_ENTRY = "TRADE_ENTRY"
    OUTCOME_OBSERVATION = "OUTCOME_OBSERVATION"
    OUTCOME = "OUTCOME"
    DATA_EXCEPTION = "DATA_EXCEPTION"


EVENT_TYPES = frozenset(item.value for item in LedgerEventType)


class LedgerInvariantError(ValueError):
    """Raised when an event would corrupt the point-in-time episode history."""


@dataclass(frozen=True, slots=True)
class OutcomePathEvaluation:
    horizon_sessions: int
    data_status: str
    bars_observed: int
    reference_price: float
    directional_return: float | None
    mfe: float | None
    mae: float | None
    path_high: float | None
    path_low: float | None
    target_first_hit_session: int | None
    stop_first_hit_session: int | None
    first_passage_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalise_utc(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise LedgerInvariantError("occurred_at_utc is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerInvariantError("occurred_at_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalise_optional(value: str | None) -> str | None:
    normalised = str(value or "").strip()
    return normalised or None


def _normalise_evidence_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalise_evidence_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalise_evidence_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def govern_ledger_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp the ledger's non-trading authority without changing evidence."""

    governed = _normalise_evidence_value(dict(payload))
    claimed_authority = str(
        governed.get("ledger_authority") or LEDGER_AUTHORITY
    ).strip().upper()
    if claimed_authority != LEDGER_AUTHORITY:
        raise LedgerInvariantError(
            f"ledger authority must be {LEDGER_AUTHORITY}, got {claimed_authority}"
        )
    for field in ("ledger_can_grant_capital", "ledger_can_reverse_direction"):
        value = governed.get(field, False)
        if value is True or str(value).strip().lower() in {"1", "true", "yes", "on"}:
            raise LedgerInvariantError(f"{field} must be false")
    governed["ledger_authority"] = LEDGER_AUTHORITY
    governed["ledger_can_grant_capital"] = False
    governed["ledger_can_reverse_direction"] = False
    return governed


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    event_id: str
    event_type: str
    occurred_at_utc: str
    run_id: str
    ticker: str
    thesis_id: str
    payload: Mapping[str, Any]
    validation_event_id: str | None = None
    previous_event_id: str | None = None
    schema_version: str = LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        event_type = str(self.event_type or "").strip().upper()
        if event_type not in EVENT_TYPES:
            raise LedgerInvariantError(
                f"unsupported ledger event type: {self.event_type}"
            )
        for name in ("event_id", "run_id", "ticker", "thesis_id"):
            if not str(getattr(self, name) or "").strip():
                raise LedgerInvariantError(f"{name} is required")
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "occurred_at_utc", _normalise_utc(self.occurred_at_utc))
        object.__setattr__(self, "run_id", self.run_id.strip())
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "thesis_id", self.thesis_id.strip())
        object.__setattr__(
            self, "validation_event_id", _normalise_optional(self.validation_event_id)
        )
        object.__setattr__(
            self, "previous_event_id", _normalise_optional(self.previous_event_id)
        )
        object.__setattr__(self, "payload", govern_ledger_payload(self.payload))

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(_canonical(dict(self.payload)).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_ledger_event(
    *,
    event_type: str,
    occurred_at_utc: str,
    run_id: str,
    ticker: str,
    thesis_id: str,
    payload: Mapping[str, Any],
    validation_event_id: str | None = None,
    previous_event_id: str | None = None,
) -> LedgerEvent:
    normalised_payload = govern_ledger_payload(payload)
    normalised_type = str(event_type or "").strip().upper()
    validation_identity = _normalise_optional(validation_event_id)
    previous_identity = _normalise_optional(previous_event_id)
    discriminator_fields = {
        LedgerEventType.THESIS_CREATED.value: ("thesis_version", "completed_session"),
        LedgerEventType.CANDIDATE_DECISION.value: ("decision_stage",),
        LedgerEventType.VALIDATION.value: ("validation_event_id", "invocation_id"),
        LedgerEventType.EXECUTION_DECISION.value: ("decision_stage",),
        LedgerEventType.PRESENTATION_DECISION.value: ("preferred_assessment_id", "human_response"),
        LedgerEventType.FILL_RECORDED.value: ("occ_symbol", "fill_timestamp_utc", "side"),
        LedgerEventType.TRADE_ENTRY.value: ("trade_id",),
        LedgerEventType.OUTCOME_OBSERVATION.value: (
            "horizon_sessions", "data_status", "evaluation_session",
        ),
        LedgerEventType.OUTCOME.value: (
            "trade_id", "horizon_sessions", "outcome_horizon_sessions",
            "is_counterfactual",
        ),
        LedgerEventType.DATA_EXCEPTION.value: ("reason", "dataset_id"),
    }
    discriminator = {
        field: normalised_payload.get(field)
        for field in discriminator_fields.get(normalised_type, ())
    }
    if normalised_type == LedgerEventType.VALIDATION.value:
        discriminator["validation_event_id"] = validation_identity
    stable_identity = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "event_type": normalised_type,
        "run_id": str(run_id or "").strip(),
        "ticker": str(ticker or "").strip().upper(),
        "thesis_id": str(thesis_id or "").strip(),
        "validation_event_id": validation_identity,
        "previous_event_id": previous_identity,
        "discriminator": discriminator,
    }
    event_id = "ledger_" + hashlib.sha256(
        _canonical(stable_identity).encode("utf-8")
    ).hexdigest()
    event_fields = {
        "event_type": str(event_type or "").strip().upper(),
        "occurred_at_utc": _normalise_utc(occurred_at_utc),
        "run_id": str(run_id or "").strip(),
        "ticker": str(ticker or "").strip().upper(),
        "thesis_id": str(thesis_id or "").strip(),
        "validation_event_id": validation_identity,
        "previous_event_id": previous_identity,
        "payload": normalised_payload,
    }
    return LedgerEvent(event_id=event_id, **event_fields)


_ALLOWED_TRANSITIONS = {
    LedgerEventType.THESIS_CREATED.value: {
        LedgerEventType.CANDIDATE_DECISION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.CANDIDATE_DECISION.value: {
        LedgerEventType.PRESENTATION_DECISION.value,
        LedgerEventType.VALIDATION.value,
        LedgerEventType.EXECUTION_DECISION.value,
        LedgerEventType.OUTCOME.value,
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.VALIDATION.value: {
        LedgerEventType.VALIDATION.value,
        LedgerEventType.EXECUTION_DECISION.value,
        LedgerEventType.OUTCOME.value,
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.EXECUTION_DECISION.value: {
        LedgerEventType.PRESENTATION_DECISION.value,
        LedgerEventType.TRADE_ENTRY.value,
        LedgerEventType.OUTCOME.value,
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.TRADE_ENTRY.value: {
        LedgerEventType.OUTCOME.value,
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.PRESENTATION_DECISION.value: {
        LedgerEventType.FILL_RECORDED.value,
        LedgerEventType.OUTCOME.value,
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.FILL_RECORDED.value: {
        LedgerEventType.OUTCOME.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
    LedgerEventType.OUTCOME.value: {LedgerEventType.OUTCOME.value},
    LedgerEventType.OUTCOME_OBSERVATION.value: {
        LedgerEventType.OUTCOME_OBSERVATION.value,
        LedgerEventType.OUTCOME.value,
    },
    LedgerEventType.DATA_EXCEPTION.value: {
        LedgerEventType.CANDIDATE_DECISION.value,
        LedgerEventType.VALIDATION.value,
        LedgerEventType.EXECUTION_DECISION.value,
        LedgerEventType.OUTCOME.value,
        LedgerEventType.DATA_EXCEPTION.value,
    },
}


def validate_event_link(previous: LedgerEvent, current: LedgerEvent) -> None:
    """Validate a causal link without turning the ledger into an authority."""

    if current.previous_event_id != previous.event_id:
        raise LedgerInvariantError("previous_event_id does not identify prior event")
    if current.thesis_id != previous.thesis_id:
        raise LedgerInvariantError("event chain changed thesis_id")
    if current.ticker != previous.ticker:
        raise LedgerInvariantError("event chain changed ticker")
    previous_time = datetime.fromisoformat(
        previous.occurred_at_utc.replace("Z", "+00:00")
    )
    current_time = datetime.fromisoformat(
        current.occurred_at_utc.replace("Z", "+00:00")
    )
    if current_time < previous_time:
        raise LedgerInvariantError("event chain time moved backwards")
    permitted = _ALLOWED_TRANSITIONS.get(previous.event_type, set())
    if current.event_type not in permitted:
        raise LedgerInvariantError(
            f"invalid ledger transition: {previous.event_type}->{current.event_type}"
        )


def evaluate_outcome_path(
    *,
    direction: str,
    reference_price: float,
    future_bars: Iterable[Mapping[str, Any]],
    horizon_sessions: int,
    target_price: float | None = None,
    invalidation_price: float | None = None,
) -> OutcomePathEvaluation:
    """Evaluate a matured CALL/PUT underlying path at completed sessions.

    Incomplete horizons remain explicitly deferred.  If target and stop are
    touched within the same daily bar, no intraday ordering is invented.
    """

    side = str(direction or "").strip().upper()
    if side not in {"CALL", "PUT"}:
        raise LedgerInvariantError("outcome direction must be CALL or PUT")
    reference = float(reference_price)
    if reference <= 0:
        raise LedgerInvariantError("reference_price must be positive")
    horizon = int(horizon_sessions)
    if horizon <= 0:
        raise LedgerInvariantError("horizon_sessions must be positive")
    bars = [dict(bar) for bar in future_bars]
    if len(bars) < horizon:
        return OutcomePathEvaluation(
            horizon, "DEFERRED_NOT_YET_OBSERVABLE", len(bars), reference,
            None, None, None, None, None, None, None, "NOT_YET_OBSERVABLE",
        )
    observed = bars[:horizon]
    for index, bar in enumerate(observed, 1):
        try:
            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])
        except (KeyError, TypeError, ValueError) as error:
            raise LedgerInvariantError(
                f"outcome bar {index} requires numeric high, low and close"
            ) from error
        if (
            not all(math.isfinite(value) for value in (high, low, close))
            or low <= 0
            or close <= 0
            or high < low
        ):
            raise LedgerInvariantError(f"outcome bar {index} has invalid OHLC geometry")

    sign = 1.0 if side == "CALL" else -1.0
    highs = [float(bar["high"]) for bar in observed]
    lows = [float(bar["low"]) for bar in observed]
    terminal_close = float(observed[-1]["close"])
    favourable = highs if side == "CALL" else lows
    adverse = lows if side == "CALL" else highs
    mfe = max(sign * (price / reference - 1.0) for price in favourable)
    mae = min(sign * (price / reference - 1.0) for price in adverse)

    target_value = float(target_price) if target_price is not None else None
    stop_value = (
        float(invalidation_price) if invalidation_price is not None else None
    )
    for name, value in (("target_price", target_value), ("invalidation_price", stop_value)):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise LedgerInvariantError(f"{name} must be a positive finite number")
    target_hit = None
    stop_hit = None
    for session, (high, low) in enumerate(zip(highs, lows), 1):
        if target_hit is None and target_value is not None:
            if (side == "CALL" and high >= target_value) or (
                side == "PUT" and low <= target_value
            ):
                target_hit = session
        if stop_hit is None and stop_value is not None:
            if (side == "CALL" and low <= stop_value) or (
                side == "PUT" and high >= stop_value
            ):
                stop_hit = session

    if target_hit is not None and stop_hit is not None:
        if target_hit == stop_hit:
            passage = "AMBIGUOUS_SAME_SESSION"
        elif target_hit < stop_hit:
            passage = "TARGET_FIRST"
        else:
            passage = "STOP_FIRST"
    elif target_hit is not None:
        passage = "TARGET_ONLY"
    elif stop_hit is not None:
        passage = "STOP_ONLY"
    else:
        passage = "NEITHER"

    return OutcomePathEvaluation(
        horizon_sessions=horizon,
        data_status="OBSERVED_COMPLETED_SESSIONS",
        bars_observed=horizon,
        reference_price=reference,
        directional_return=sign * (terminal_close / reference - 1.0),
        mfe=mfe,
        mae=mae,
        path_high=max(highs),
        path_low=min(lows),
        target_first_hit_session=target_hit,
        stop_first_hit_session=stop_hit,
        first_passage_state=passage,
    )


__all__ = [
    "EVENT_TYPES",
    "LEDGER_AUTHORITY",
    "LEDGER_SCHEMA_VERSION",
    "LedgerEvent",
    "LedgerEventType",
    "LedgerInvariantError",
    "OutcomePathEvaluation",
    "evaluate_outcome_path",
    "govern_ledger_payload",
    "make_ledger_event",
    "validate_event_link",
]
