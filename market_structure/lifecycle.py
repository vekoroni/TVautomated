"""Market-structure lifecycle and governed-direction relationship mapping."""

from __future__ import annotations
from domain.market_structure_evidence import (
    market_structure_direction_relationship,
    transition_market_structure_lifecycle,
)
from .params import MSParams, MS_PARAMS_V1


def transition_lifecycle(*, prior: str | None, detected: bool, accepted: bool, repair_pct: float, invalidated: bool = False, params: MSParams = MS_PARAMS_V1) -> str:
    return transition_market_structure_lifecycle(
        prior=prior, detected=detected, accepted=accepted,
        repair_pct=repair_pct, invalidated=invalidated,
        intact_repair=params.intact_repair, failed_repair=params.failed_repair,
    )


def direction_relationship(*, governed_direction: str, structure_direction: str | None, lifecycle: str, quality: str) -> str:
    return market_structure_direction_relationship(
        governed_direction=governed_direction,
        structure_direction=structure_direction,
        lifecycle=lifecycle,
        quality=quality,
    )
