"""Pure thesis-direction and validation lifecycle domain.

This bounded context owns the meanings of a frozen thesis direction and its
permitted validation transitions.  It deliberately has no provider, database,
filesystem, dataframe or UI dependency.  Legacy modules may expose their
existing schemas, but must delegate these business invariants here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class ThesisDirection(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    STRANGLE = "STRANGLE"
    NON_DIRECTIONAL = "NON_DIRECTIONAL"
    UNRESOLVED = "UNRESOLVED"


class ThesisState(str, Enum):
    ACTIVE = "ACTIVE"
    DEVELOPING = "DEVELOPING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    TARGET_REALIZED = "TARGET_REALIZED"
    HORIZON_EXPIRED = "HORIZON_EXPIRED"
    COMPLETED = "COMPLETED"


class ValidationTransition(str, Enum):
    THESIS_CONFIRMED = "THESIS_CONFIRMED"
    PENDING_TRIGGER = "PENDING_TRIGGER"
    ENTRY_RUNWAY_EXHAUSTED = "ENTRY_RUNWAY_EXHAUSTED"
    TARGET_ALREADY_REACHED = "TARGET_ALREADY_REACHED"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    DATA_DEFERRED = "DATA_DEFERRED"
    NOT_EVALUATED_NON_DIRECTIONAL = "NOT_EVALUATED_NON_DIRECTIONAL"


DIRECTED_DIRECTIONS = frozenset(
    {ThesisDirection.CALL.value, ThesisDirection.PUT.value}
)
NON_DIRECTIONAL_DIRECTIONS = frozenset(
    {
        ThesisDirection.STRANGLE.value,
        ThesisDirection.NON_DIRECTIONAL.value,
        ThesisDirection.UNRESOLVED.value,
    }
)
TERMINAL_THESIS_STATES = frozenset(
    {
        ThesisState.INVALIDATED,
        ThesisState.TARGET_REALIZED,
        ThesisState.HORIZON_EXPIRED,
        ThesisState.COMPLETED,
    }
)


class DirectionInvariantError(ValueError):
    """Raised when a downstream component attempts to reinterpret direction."""


def _token(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    text = str(value).strip().upper()
    return "" if text in {"", "NAN", "NONE", "NULL", "N/A"} else text


def normalise_direction(value: Any, *, strangle_for_non_directional: bool = False) -> str:
    """Translate external direction vocabulary without defaulting to CALL.

    ``strangle_for_non_directional`` exists only for the legacy Options
    Intelligence contract, whose public non-directional literal is STRANGLE.
    The domain's validation vocabulary uses NON_DIRECTIONAL.
    """

    text = _token(value)
    if text in {item.value for item in ThesisDirection}:
        if strangle_for_non_directional and text == ThesisDirection.NON_DIRECTIONAL.value:
            return ThesisDirection.STRANGLE.value
        return text
    if any(token in text for token in ("PUT", "SELL", "BEAR", "SHORT")):
        return ThesisDirection.PUT.value
    if any(token in text for token in ("CALL", "BUY", "BULL", "LONG")):
        return ThesisDirection.CALL.value
    if text in {"STRADDLE", "MIXED", "TRANSITION"}:
        return (
            ThesisDirection.STRANGLE.value
            if strangle_for_non_directional
            else ThesisDirection.NON_DIRECTIONAL.value
        )
    return ThesisDirection.UNRESOLVED.value


def resolve_structural_direction(
    precor_intent: Any,
    trend: Any,
    *,
    strangle_for_non_directional: bool = False,
) -> tuple[str, str]:
    """Resolve the closed, mirror-symmetric structural direction table."""

    intent = _token(precor_intent)
    trend_value = _token(trend)
    if intent == "BUY_SETUP":
        return ThesisDirection.CALL.value, "precor_intent=BUY_SETUP"
    if intent == "SELL_SETUP":
        return ThesisDirection.PUT.value, "precor_intent=SELL_SETUP"
    if intent == "TRANSITION":
        if trend_value == "BULLISH":
            return ThesisDirection.CALL.value, "precor_intent=TRANSITION, trend=BULLISH"
        if trend_value == "BEARISH":
            return ThesisDirection.PUT.value, "precor_intent=TRANSITION, trend=BEARISH"
        non_directional = (
            ThesisDirection.STRANGLE.value
            if strangle_for_non_directional
            else ThesisDirection.NON_DIRECTIONAL.value
        )
        return non_directional, f"precor_intent=TRANSITION, trend={trend_value or 'MIXED'}"
    if intent == "WAIT":
        return ThesisDirection.UNRESOLVED.value, "precor_intent=WAIT"
    return ThesisDirection.UNRESOLVED.value, f"precor_intent={intent or 'MISSING'}"


@dataclass(frozen=True, slots=True)
class FrozenThesis:
    """The immutable directional thesis established from completed evidence."""

    thesis_id: str
    ticker: str
    direction: str
    completed_session: str
    completed_close: float
    target: float
    invalidation: float
    selected_contract: str
    trigger: float | None = None
    maximum_entry: float | None = None
    completed_profile_evidence_id: str | None = None

    def __post_init__(self) -> None:
        direction = normalise_direction(self.direction)
        if direction not in {
            ThesisDirection.CALL.value,
            ThesisDirection.PUT.value,
            ThesisDirection.NON_DIRECTIONAL.value,
        }:
            raise ValueError("frozen thesis direction must be CALL, PUT or NON_DIRECTIONAL")
        for name in ("completed_close", "target", "invalidation"):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if (
            direction == ThesisDirection.CALL.value
            and not self.invalidation < self.completed_close < self.target
        ):
            raise ValueError("CALL thesis geometry must be invalidation < close < target")
        if (
            direction == ThesisDirection.PUT.value
            and not self.target < self.completed_close < self.invalidation
        ):
            raise ValueError("PUT thesis geometry must be target < close < invalidation")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "direction", direction)


def evaluate_validation_transition(
    thesis: FrozenThesis,
    current_price: float,
) -> tuple[ValidationTransition, str]:
    """Evaluate current underlying price without changing the frozen direction."""

    price = float(current_price)
    if price <= 0:
        raise ValueError("current_price must be positive")
    if thesis.direction == ThesisDirection.NON_DIRECTIONAL.value:
        return (
            ValidationTransition.NOT_EVALUATED_NON_DIRECTIONAL,
            "Directional validation is not applicable",
        )
    if thesis.direction == ThesisDirection.CALL.value:
        if price <= thesis.invalidation:
            return ValidationTransition.THESIS_INVALIDATED, "CALL invalidation breached"
        if price >= thesis.target:
            return ValidationTransition.TARGET_ALREADY_REACHED, "CALL target already reached"
        if thesis.maximum_entry is not None and price > thesis.maximum_entry:
            return ValidationTransition.ENTRY_RUNWAY_EXHAUSTED, "CALL maximum entry exceeded"
        if thesis.trigger is not None and price < thesis.trigger:
            return ValidationTransition.PENDING_TRIGGER, "CALL trigger not reached"
    else:
        if price >= thesis.invalidation:
            return ValidationTransition.THESIS_INVALIDATED, "PUT invalidation breached"
        if price <= thesis.target:
            return ValidationTransition.TARGET_ALREADY_REACHED, "PUT target already reached"
        if thesis.maximum_entry is not None and price < thesis.maximum_entry:
            return ValidationTransition.ENTRY_RUNWAY_EXHAUSTED, "PUT maximum entry exceeded"
        if thesis.trigger is not None and price > thesis.trigger:
            return ValidationTransition.PENDING_TRIGGER, "PUT trigger not reached"
    return ValidationTransition.THESIS_CONFIRMED, "Frozen thesis remains structurally valid"


def assert_direction_continuity(
    frozen_direction: Any,
    downstream: Mapping[str, Any] | None,
    *,
    stage: str,
) -> None:
    """Reject a downstream CALL/PUT reinterpretation of a frozen thesis.

    Missing direction metadata is tolerated because some data-only payloads do
    not carry it.  Whenever an explicit directional field is present, however,
    it must agree with the frozen direction.  A legitimate reversal requires a
    new thesis identity rather than mutation of the existing thesis.
    """

    if not downstream:
        return
    frozen = normalise_direction(frozen_direction)
    for field in (
        "governed_direction",
        "final_direction",
        "selected_contract_side",
        "option_side",
        "direction",
    ):
        if field not in downstream:
            continue
        raw = downstream.get(field)
        token = _token(raw)
        if not token:
            continue
        observed = normalise_direction(raw)
        if observed not in DIRECTED_DIRECTIONS:
            continue
        if frozen not in DIRECTED_DIRECTIONS or observed != frozen:
            raise DirectionInvariantError(
                f"{stage}_DIRECTION_REINTERPRETATION:{field}:{frozen}->{observed}"
            )
