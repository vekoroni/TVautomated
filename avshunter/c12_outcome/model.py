"""Outcome scoring value objects (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Direction(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.BULL else -1


class InvalidationState(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    NON_POSITIVE = "NON_POSITIVE"
    WRONG_SIDE = "WRONG_SIDE"


class TargetState(str, Enum):
    LEVEL = "LEVEL"
    NONE = "NONE"
    INVALID_LEGACY = "INVALID_LEGACY"   # zero, negative or wrong side in a legacy book


class ContractState(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    UNPARSEABLE = "UNPARSEABLE"
    SIDE_MISMATCH = "SIDE_MISMATCH"


class OutcomeState(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    STOP_FIRST = "STOP_FIRST"
    AMBIGUOUS = "AMBIGUOUS"
    OPEN_CENSORED = "OPEN_CENSORED"
    TIMEOUT = "TIMEOUT"
    DATA_GAP = "DATA_GAP"
    NOT_SCORABLE = "NOT_SCORABLE"

    @property
    def terminal(self) -> bool:
        return self not in (OutcomeState.OPEN_CENSORED, OutcomeState.DATA_GAP)


@dataclass(frozen=True, slots=True)
class Bar:
    session: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class Geometry:
    direction: Direction | None
    reference_price: float | None
    invalidation_price: float | None
    invalidation_state: InvalidationState
    target_price: float | None
    target_state: TargetState
    contract_symbol: str | None
    contract_state: ContractState
    direction_text: str

    @property
    def scorable(self) -> bool:
        return (
            self.direction is not None
            and self.reference_price is not None
            and self.invalidation_state is InvalidationState.VALID
        )


@dataclass(frozen=True, slots=True)
class UnderlyingOutcome:
    state: OutcomeState
    sessions_observed: int
    resolution_session: int | None
    exit_session_date: date | None
    exit_price: float | None
    return_to_exit_pct: float | None
    r_multiple: float | None
    mfe_pct: float | None
    mae_pct: float | None
    reason: str = ""
