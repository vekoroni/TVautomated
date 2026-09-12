"""Thesis-conditioned reachability, advisory only."""
from __future__ import annotations
from dataclasses import dataclass
from .volatility_budget import VolatilityBudget

REACHABILITY_VERSION = "reachability_v1"

@dataclass(frozen=True, slots=True)
class ReachabilityAssessment:
    direction: str
    origin_spot: float
    structural_target_spot: float | None
    reachable_target_spot: float | None
    structural_distance_fraction: float | None
    volatility_budget_fraction: float | None
    reach_ratio: float | None
    sigma_multiple: float
    validation_state: str
    bias_multiplier_applied: bool
    quality_state: str
    calculation_version: str = REACHABILITY_VERSION
    authority: str = "ADVISORY_ONLY"
    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

def assess_reachability(*, direction: str, origin_spot: float, structural_target_spot: float | None,
                        budget: VolatilityBudget, sigma_multiple: float = 1.5) -> ReachabilityAssessment:
    side = str(direction).upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("direction must be CALL or PUT")
    spot = float(origin_spot)
    if spot <= 0:
        raise ValueError("origin_spot must be positive")
    target = None if structural_target_spot is None else float(structural_target_spot)
    sign = 1.0 if side == "CALL" else -1.0
    if target is not None and sign * (target - spot) <= 0:
        return ReachabilityAssessment(side, spot, target, None, None, budget.expected_move_fraction, None,
                                      sigma_multiple, budget.validation_state, budget.bias_multiplier_applied, "DATA_DEFECT_WRONG_SIDED_TARGET")
    if target is None or budget.expected_move_fraction is None:
        return ReachabilityAssessment(side, spot, target, None, None, budget.expected_move_fraction, None,
                                      sigma_multiple, budget.validation_state, budget.bias_multiplier_applied, "NOT_EVALUATED_DATA_MISSING")
    distance = abs(target - spot) / spot
    reachable = spot * (1.0 + sign * float(sigma_multiple) * budget.expected_move_fraction)
    return ReachabilityAssessment(side, spot, target, reachable, distance, budget.expected_move_fraction,
                                  distance / budget.expected_move_fraction, float(sigma_multiple), budget.validation_state,
                                  budget.bias_multiplier_applied, "PASS" if budget.validation_state == "VALIDATED" else "UNVALIDATED_INPUT")
