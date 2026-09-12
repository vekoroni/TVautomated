"""AVS-FIX-002 deterministic scenario economics.

This is a pure advisory model.  It ranks scenario payoffs; it does not predict
probabilities, select direction, delete a thesis, or grant execution authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from statistics import median
from typing import Mapping, Sequence

from .deterministic_option_valuation import dividend_adjusted_black_scholes, ScenarioPoint, ScenarioTiming

ENGINE_VERSION = "scenario_valuation_v2"
FRICTION_VERSION = "friction_model_v1"
UTILITY_VERSION = "deterministic_utility_v2"

@dataclass(frozen=True, slots=True)
class ScenarioEconomics:
    scenario_id: str
    path: str
    timing: str
    iv_stress: str
    spot: float
    theoretical_value_per_share: float
    exit_value_after_friction_per_share: float
    net_return_fraction: float
    remaining_calendar_years: float
    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

@dataclass(frozen=True, slots=True)
class ContractEconomicsV2:
    scenarios: tuple[ScenarioEconomics, ...]
    applicability: str
    applicability_reason: str
    monetisability_state: str
    monetisability_reason: str
    deterministic_utility: float | None
    ranking_score_kind: str
    convexity_score: float | None
    convexity_label: str
    spread_fraction_mid: float | None
    calculation_version: str = ENGINE_VERSION
    friction_version: str = FRICTION_VERSION
    utility_version: str = UTILITY_VERSION
    calendar_version: str = "XNYS_BRIDGE_V1"
    basis: str = "AT_GOVERNED_TIME_STOP"
    calibration_state: str = "NOT_AVAILABLE"
    decision_authority: str = "NONE"
    profit_floor_applied: float | None = None
    profit_floor_approved: bool = False
    profit_floor_approval_id: str | None = None
    monetisability_policy_version: str = "scenario-monetisability-policy-v1"
    def to_dict(self) -> dict:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["scenarios"] = [item.to_dict() for item in self.scenarios]
        return result

def evaluate_contract_economics_v2(
    *, option_side: str, origin_spot: float, strike: float, expiration_utc: datetime,
    base_iv: float | None, entry_bid: float | None, entry_ask: float | None,
    risk_free_rate: float | None, dividend_yield: float | None,
    scenario_points: Sequence[ScenarioPoint], favourable_1sigma: float | None,
    favourable_2sigma: float | None, reachable_spot: float | None,
    structural_target: float | None, invalidation_spot: float | None,
    spread_cap: float = 0.15, max_model_spread: float = 0.30,
    profit_floor: float | None = None, profit_floor_approved: bool = False,
    profit_floor_approval_id: str | None = None,
    w_flat: float = 0.5,
) -> ContractEconomicsV2:
    side = str(option_side).upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("option_side must be CALL or PUT")
    required = (base_iv, entry_bid, entry_ask, risk_free_rate, dividend_yield,
                favourable_1sigma, favourable_2sigma, reachable_spot, invalidation_spot)
    if any(value is None for value in required):
        return ContractEconomicsV2((), "NOT_EVALUATED_DATA_MISSING", "REQUIRED_INPUT_MISSING",
                                   "NOT_EVALUATED_DATA_MISSING", "REQUIRED_INPUT_MISSING", None,
                                   "DETERMINISTIC_UTILITY", None, "NOT_EVALUATED", None)
    bid, ask = float(entry_bid), float(entry_ask)
    if bid < 0 or ask <= 0 or bid >= ask:
        return ContractEconomicsV2((), "DATA_DEFECT", "INVALID_BID_ASK",
                                   "NOT_EVALUATED_DATA_MISSING", "INVALID_BID_ASK", None,
                                   "DETERMINISTIC_UTILITY", None, "NOT_EVALUATED", None)
    spread = (ask - bid) / ((ask + bid) / 2.0)
    if spread > max_model_spread:
        return ContractEconomicsV2((), "FRICTION_OUT_OF_RANGE", "SPREAD_OUTSIDE_MODEL_DOMAIN",
                                   "INDETERMINATE", "FRICTION_OUT_OF_RANGE", None,
                                   "DETERMINISTIC_UTILITY", None, "NOT_EVALUATED", spread)
    points = tuple(scenario_points)
    late = max(points, key=lambda item: item.sessions_elapsed)
    if late.as_of_utc >= expiration_utc.astimezone(timezone.utc):
        return ContractEconomicsV2((), "HORIZON_LIMITED", "CONTRACT_EXPIRES_WITHIN_HOLD",
                                   "INDETERMINATE", "HORIZON_LIMITED", None,
                                   "DETERMINISTIC_UTILITY", None, "NOT_EVALUATED", spread)
    sign = 1.0 if side == "CALL" else -1.0
    paths = {
        "FLAT": float(origin_spot),
        "FAVOURABLE_1SIGMA": float(favourable_1sigma),
        "FAVOURABLE_2SIGMA": float(favourable_2sigma),
        "REACHABLE": float(reachable_spot),
        "ADVERSE_INVALIDATION": float(invalidation_spot),
    }
    if structural_target is not None:
        paths["STRUCTURAL_DISCLOSURE"] = float(structural_target)
    if any(spot <= 0 for spot in paths.values()):
        raise ValueError("scenario spots must be positive")
    if sign * (paths["REACHABLE"] - origin_spot) <= 0:
        raise ValueError("reachable scenario is wrong-sided")
    iv_stress = {"CONTRACTED": .8, "BASE": 1.0, "EXPANDED": 1.2}
    exit_discount = 1.0 - min(spread / 2.0, spread_cap)
    values: list[ScenarioEconomics] = []
    for path, spot in paths.items():
        for point in points:
            years = max(0.0, (expiration_utc.astimezone(timezone.utc) - point.as_of_utc).total_seconds() / (365 * 86400))
            for stress, multiplier in iv_stress.items():
                theoretical = dividend_adjusted_black_scholes(
                    option_side=side, spot=spot, strike=float(strike), time_to_expiry_years=years,
                    risk_free_rate=float(risk_free_rate), dividend_yield=float(dividend_yield),
                    volatility=float(base_iv) * multiplier,
                )
                exit_value = theoretical * exit_discount
                values.append(ScenarioEconomics(
                    f"{path}:{point.timing.value}:{stress}", path, point.timing.value, stress,
                    spot, theoretical, exit_value, (exit_value - ask) / ask, years,
                ))
    def returns(path: str):
        return [v.net_return_fraction for v in values if v.path == path]
    reachable_returns = returns("REACHABLE")
    adverse_returns = returns("ADVERSE_INVALIDATION")
    flat_late = next(v.net_return_fraction for v in values if v.path == "FLAT" and v.timing == "LATE" and v.iv_stress == "BASE")
    utility = median(reachable_returns) + min(adverse_returns) + float(w_flat) * flat_late
    r1 = next(v.net_return_fraction for v in values if v.path == "FAVOURABLE_1SIGMA" and v.timing == "LATE" and v.iv_stress == "BASE")
    r2 = next(v.net_return_fraction for v in values if v.path == "FAVOURABLE_2SIGMA" and v.timing == "LATE" and v.iv_stress == "BASE")
    convexity = r2 - 2.0 * r1 + flat_late
    label = "CONVEX" if convexity > .01 else ("LINEAR" if convexity >= -.01 else "CONCAVE")
    headline = next(v.net_return_fraction for v in values if v.path == "REACHABLE" and v.timing == "LATE" and v.iv_stress == "BASE")
    if not profit_floor_approved or profit_floor is None:
        state, reason = "INDETERMINATE", "PROFIT_FLOOR_NOT_APPROVED"
    elif headline >= float(profit_floor):
        state, reason = "SCENARIO_MONETISABLE", "REACHABLE_LATE_BASE_AT_OR_ABOVE_FLOOR"
    elif headline > 0:
        state, reason = "SCENARIO_LIMITED", "REACHABLE_LATE_BASE_POSITIVE_BELOW_FLOOR"
    else:
        state, reason = "NOT_CURRENTLY_MONETISABLE", "REACHABLE_LATE_BASE_NON_POSITIVE"
    return ContractEconomicsV2(
        tuple(values), "APPLICABLE", "INPUTS_COMPLETE", state, reason,
        utility, "DETERMINISTIC_UTILITY", convexity, label, spread,
        profit_floor_applied=(
            float(profit_floor)
            if profit_floor_approved and profit_floor is not None else None
        ),
        profit_floor_approved=bool(profit_floor_approved),
        profit_floor_approval_id=(
            str(profit_floor_approval_id or "").strip() or None
        ),
    )
