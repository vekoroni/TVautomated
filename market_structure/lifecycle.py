"""Market-structure lifecycle and governed-direction relationship mapping."""

from __future__ import annotations
from .params import MSParams, MS_PARAMS_V1


def transition_lifecycle(*, prior: str | None, detected: bool, accepted: bool, repair_pct: float, invalidated: bool = False, params: MSParams = MS_PARAMS_V1) -> str:
    previous = str(prior or "").upper()
    if previous == "MS_FAILED": return "MS_FAILED"
    if not detected or invalidated or repair_pct > params.failed_repair:
        return "MS_FAILED" if previous else "MS_NONE"
    if previous in {"", "MS_NONE"}: return "MS_ACCEPTED" if accepted else "MS_DEVELOPING"
    if previous == "MS_DEVELOPING": return "MS_ACCEPTED" if accepted else "MS_DEVELOPING"
    if previous == "MS_REPAIRING" and accepted and repair_pct < params.intact_repair: return "MS_CONTINUING"
    if previous in {"MS_ACCEPTED", "MS_CONTINUING"} and accepted and repair_pct < params.intact_repair: return "MS_CONTINUING"
    return "MS_REPAIRING"


def direction_relationship(*, governed_direction: str, structure_direction: str | None, lifecycle: str, quality: str) -> str:
    if quality in {"INSUFFICIENT_DATA", "COARSE_DATA_LOW_CONFIDENCE"} or not structure_direction:
        return "INSUFFICIENT_DATA"
    direction = governed_direction.strip().upper()
    if direction not in {"CALL", "PUT"} or lifecycle not in {"MS_ACCEPTED", "MS_CONTINUING"}: return "NEUTRAL"
    aligned = (direction == "CALL" and structure_direction == "ABOVE") or (direction == "PUT" and structure_direction == "BELOW")
    return "ALIGNED" if aligned else "CONFLICTING"
