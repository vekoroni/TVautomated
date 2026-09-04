"""Canonical cross-stage state vocabulary for governed pipeline handoffs.

These values describe data availability and evaluation state.  They do not
grant execution or capital authority.  Producers and consumers must use the
same literal so a state cannot change meaning merely by crossing a CSV/JSON
boundary.
"""

from __future__ import annotations

from enum import Enum


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class GovernedDataState(_ValueEnum):
    AVAILABLE = "AVAILABLE"
    PENDING_MORNING_REFRESH = "PENDING_MORNING_REFRESH"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    DATA_DEFECT = "DATA_DEFECT"
    STALE_ADVISORY = "STALE_ADVISORY"
    CONTRACT_REPAIR_REQUIRED = "CONTRACT_REPAIR_REQUIRED"
    SYNTHETIC_RESEARCH_ONLY = "SYNTHETIC_RESEARCH_ONLY"


class LifecycleEvaluationState(_ValueEnum):
    NOT_EVALUATED_NON_DIRECTIONAL = "NOT_EVALUATED_NON_DIRECTIONAL"
    MISSING_AUTHORITATIVE_STOP = "MISSING_AUTHORITATIVE_STOP"
    DATA_DEFECT_WRONG_SIDE = "DATA_DEFECT_WRONG_SIDE"
    SUPERSEDED_DATA_DEFECT = "SUPERSEDED_DATA_DEFECT"


GOVERNED_DATA_STATE_VALUES = frozenset(item.value for item in GovernedDataState)
LIFECYCLE_EVALUATION_STATE_VALUES = frozenset(
    item.value for item in LifecycleEvaluationState
)

