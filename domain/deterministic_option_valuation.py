"""Pure DOI-5 deterministic option valuation domain service.

The calculations in this module answer a deliberately narrow question: what
would one exact long CALL or PUT be worth under governed target/invalidation,
timing and implied-volatility stresses?  The output is scenario arithmetic,
not a forecast, probability, trade verdict, or capital permission.

Calendar construction and persistence belong to the application layer.  This
module accepts already-governed, timezone-aware scenario instants so it stays
provider, database and exchange-calendar agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from statistics import median
from typing import Any, Mapping, Sequence

from .dynamic_options_intelligence import (
    DOI_DECISION_AUTHORITY,
    ModelApplicabilityState,
)


DOI_SCENARIO_ENGINE_VERSION = "doi-deterministic-scenario-v1"
DOI_VALUATION_MODEL_VERSION = "DIVIDEND_ADJUSTED_EUROPEAN_BS_V1"
DOI_SCENARIO_UTILITY_VERSION = "doi-scenario-utility-uncalibrated-v1"
DOI_SCENARIO_AUTHORITY = "ADVISORY_ARITHMETIC_ONLY"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ScenarioPath(_ValueEnum):
    FAVOURABLE_TARGET = "FAVOURABLE_TARGET"
    ADVERSE_INVALIDATION = "ADVERSE_INVALIDATION"


class ScenarioTiming(_ValueEnum):
    EARLY = "EARLY"
    MID = "MID"
    LATE = "LATE"


class IVStress(_ValueEnum):
    CONTRACTED = "CONTRACTED"
    BASE = "BASE"
    EXPANDED = "EXPANDED"


@dataclass(frozen=True, slots=True)
class ScenarioPoint:
    timing: ScenarioTiming
    sessions_elapsed: int
    as_of_utc: datetime

    def __post_init__(self) -> None:
        timing = self.timing if isinstance(self.timing, ScenarioTiming) else ScenarioTiming(str(self.timing).upper())
        object.__setattr__(self, "timing", timing)
        sessions = int(self.sessions_elapsed)
        if sessions < 1:
            raise ValueError("sessions_elapsed must be positive")
        object.__setattr__(self, "sessions_elapsed", sessions)
        if self.as_of_utc.tzinfo is None:
            raise ValueError("scenario timestamp must be timezone-aware")
        object.__setattr__(self, "as_of_utc", self.as_of_utc.astimezone(timezone.utc))


@dataclass(frozen=True, slots=True)
class ScenarioValuation:
    scenario_id: str
    path: ScenarioPath
    timing: ScenarioTiming
    iv_stress: IVStress
    sessions_elapsed: int
    scenario_as_of_utc: datetime
    scenario_spot: float
    scenario_iv: float
    time_to_expiry_years: float
    theoretical_value: float
    entry_reference: float | None
    entry_cost_after_friction: float | None
    exit_value_after_friction: float
    net_return_fraction: float | None
    valuation_model: str = DOI_VALUATION_MODEL_VERSION
    decision_authority: str = DOI_DECISION_AUTHORITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "path": self.path.value,
            "timing": self.timing.value,
            "iv_stress": self.iv_stress.value,
            "sessions_elapsed": self.sessions_elapsed,
            "scenario_as_of_utc": self.scenario_as_of_utc.isoformat().replace("+00:00", "Z"),
            "scenario_spot": self.scenario_spot,
            "scenario_iv": self.scenario_iv,
            "time_to_expiry_years": self.time_to_expiry_years,
            "theoretical_value": self.theoretical_value,
            "entry_reference": self.entry_reference,
            "entry_cost_after_friction": self.entry_cost_after_friction,
            "exit_value_after_friction": self.exit_value_after_friction,
            "net_return_fraction": self.net_return_fraction,
            "valuation_model": self.valuation_model,
            "decision_authority": self.decision_authority,
        }


@dataclass(frozen=True, slots=True)
class DeterministicContractValuation:
    scenarios: tuple[ScenarioValuation, ...]
    applicability_state: ModelApplicabilityState
    ranking_score_uncalibrated: float | None
    favourable_median_return: float | None
    adverse_worst_return: float | None
    utility_formula: str
    american_exercise_material: bool
    american_exercise_reason: str | None
    disclosures: tuple[str, ...]
    engine_version: str = DOI_SCENARIO_ENGINE_VERSION
    model_version: str = DOI_VALUATION_MODEL_VERSION
    utility_version: str = DOI_SCENARIO_UTILITY_VERSION
    probabilities_calibrated: bool = False
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        if self.probabilities_calibrated:
            raise ValueError("DOI-5 deterministic scenarios cannot be calibrated probabilities")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("deterministic valuation has no decision authority")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarios": [item.to_dict() for item in self.scenarios],
            "scenario_count": len(self.scenarios),
            "applicability_state": self.applicability_state.value,
            "ranking_score_uncalibrated": self.ranking_score_uncalibrated,
            "favourable_median_return": self.favourable_median_return,
            "adverse_worst_return": self.adverse_worst_return,
            "utility_formula": self.utility_formula,
            "american_exercise_material": self.american_exercise_material,
            "american_exercise_reason": self.american_exercise_reason,
            "disclosures": list(self.disclosures),
            "engine_version": self.engine_version,
            "model_version": self.model_version,
            "utility_version": self.utility_version,
            "probabilities_calibrated": self.probabilities_calibrated,
            "decision_authority": self.decision_authority,
        }


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0)))


def dividend_adjusted_black_scholes(
    *,
    option_side: str,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    volatility: float,
) -> float:
    """Return European option value with continuous dividend yield.

    The formula is deterministic and permits negative rates.  At expiry or at
    zero volatility it resolves to the discounted deterministic payoff rather
    than dividing by zero.
    """

    side = str(option_side or "").strip().upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("option_side must be CALL or PUT")
    s = _finite(spot, "spot")
    k = _finite(strike, "strike")
    t = max(0.0, _finite(time_to_expiry_years, "time_to_expiry_years"))
    r = _finite(risk_free_rate, "risk_free_rate")
    q = _finite(dividend_yield, "dividend_yield")
    sigma = _finite(volatility, "volatility")
    if s <= 0 or k <= 0:
        raise ValueError("spot and strike must be positive")
    if q < 0:
        raise ValueError("dividend_yield cannot be negative")
    if sigma < 0:
        raise ValueError("volatility cannot be negative")
    if t == 0:
        return max(0.0, s - k) if side == "CALL" else max(0.0, k - s)
    discounted_spot = s * math.exp(-q * t)
    discounted_strike = k * math.exp(-r * t)
    if sigma == 0:
        deterministic = discounted_spot - discounted_strike
        return max(0.0, deterministic) if side == "CALL" else max(0.0, -deterministic)
    root_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    intrinsic = max(0.0, s - k) if side == "CALL" else max(0.0, k - s)
    if side == "CALL":
        value = discounted_spot * normal_cdf(d1) - discounted_strike * normal_cdf(d2)
        lower, upper = max(intrinsic, discounted_spot - discounted_strike), s
    else:
        value = discounted_strike * normal_cdf(-d2) - discounted_spot * normal_cdf(-d1)
        lower, upper = max(intrinsic, discounted_strike - discounted_spot), k
    return min(upper, max(lower, value))


def assess_american_exercise_materiality(
    *, option_side: str, spot: float, strike: float, dividend_yield: float,
    ex_dividend_within_horizon: bool, risk_free_rate: float = 0.0,
    time_to_expiry_years: float = 0.0, volatility: float = 0.0,
) -> tuple[bool, str | None]:
    """Conservatively flag where European BS is weak for American exercise.

    This is an applicability classifier, not an American-option pricer.  It
    uses the economic inputs that drive early-exercise value rather than a
    fixed moneyness threshold, and leaves the contract visible as OOD.
    """

    side = str(option_side).upper()
    s, k = _finite(spot, "spot"), _finite(strike, "strike")
    r = _finite(risk_free_rate, "risk_free_rate")
    q = _finite(dividend_yield, "dividend_yield")
    t = max(0.0, _finite(time_to_expiry_years, "time_to_expiry_years"))
    sigma = max(0.0, _finite(volatility, "volatility"))
    if s <= 0 or k <= 0:
        raise ValueError("spot and strike must be positive")
    ratio = s / k
    positive_rate_carry = 1.0 - math.exp(-max(r, 0.0) * t)
    volatility_window = sigma * math.sqrt(t) if t > 0 else 0.0
    near_or_itm_put = ratio <= 1.0 + min(0.10, max(0.02, volatility_window * 0.25))
    if side == "PUT" and ratio <= 0.80 and positive_rate_carry >= 0.002:
        return True, "SUFFICIENTLY_ITM_PUT_EARLY_EXERCISE_NOT_MODELLED"
    if side == "PUT" and near_or_itm_put and positive_rate_carry >= 0.005:
        return True, "RATE_AND_HORIZON_PUT_EARLY_EXERCISE_NOT_MODELLED"
    dividend_carry = 1.0 - math.exp(-q * t)
    if side == "CALL" and ratio > 1.0 and ex_dividend_within_horizon and dividend_carry >= 0.001:
        return True, "ITM_DIVIDEND_CALL_EARLY_EXERCISE_NOT_MODELLED"
    return False, None


def evaluate_deterministic_scenarios(
    *,
    option_side: str,
    strike: float,
    expiration_utc: datetime,
    target_spot: float | None,
    invalidation_spot: float | None,
    base_iv: float | None,
    scenario_points: Sequence[ScenarioPoint],
    entry_ask: float | None,
    risk_free_rate: float,
    dividend_yield: float,
    entry_friction_bps: float = 25.0,
    exit_friction_bps: float = 25.0,
    iv_multipliers: Mapping[IVStress | str, float] | None = None,
    ex_dividend_within_horizon: bool = False,
    corporate_action_flag: bool = False,
    dividend_yield_available: bool = True,
) -> DeterministicContractValuation:
    """Value the fixed 2 x 3 x 3 DOI-5 scenario grid."""

    side = str(option_side or "").strip().upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("option_side must be CALL or PUT")
    k = _finite(strike, "strike")
    r = _finite(risk_free_rate, "risk_free_rate")
    q = _finite(dividend_yield, "dividend_yield")
    entry_bps = _finite(entry_friction_bps, "entry_friction_bps")
    exit_bps = _finite(exit_friction_bps, "exit_friction_bps")
    if k <= 0 or q < 0 or entry_bps < 0 or exit_bps < 0 or entry_bps >= 10_000 or exit_bps >= 10_000:
        raise ValueError("invalid strike, dividend yield, or friction")
    if expiration_utc.tzinfo is None:
        raise ValueError("expiration_utc must be timezone-aware")
    expiry = expiration_utc.astimezone(timezone.utc)
    points = tuple(scenario_points)
    if {item.timing for item in points} != set(ScenarioTiming) or len(points) != 3:
        raise ValueError("scenario_points must contain exactly EARLY, MID and LATE")
    ordered_points = sorted(points, key=lambda item: (
        {ScenarioTiming.EARLY: 0, ScenarioTiming.MID: 1, ScenarioTiming.LATE: 2}[item.timing]
    ))
    if [item.sessions_elapsed for item in ordered_points] != sorted(
        item.sessions_elapsed for item in ordered_points
    ) or len({item.sessions_elapsed for item in ordered_points}) != 3:
        raise ValueError("scenario_points sessions must increase EARLY to MID to LATE")
    if [item.as_of_utc for item in ordered_points] != sorted(item.as_of_utc for item in ordered_points):
        raise ValueError("scenario_points timestamps must increase EARLY to MID to LATE")
    if target_spot is None or invalidation_spot is None or base_iv is None:
        return DeterministicContractValuation(
            scenarios=(), applicability_state=ModelApplicabilityState.DATA_INSUFFICIENT,
            ranking_score_uncalibrated=None, favourable_median_return=None,
            adverse_worst_return=None,
            utility_formula="MEDIAN_FAVOURABLE_RETURN_PLUS_WORST_ADVERSE_RETURN",
            american_exercise_material=False, american_exercise_reason=None,
            disclosures=("TARGET_INVALIDATION_OR_IV_MISSING", "NO_PROBABILITY_OUTPUT"),
        )
    target = _finite(target_spot, "target_spot")
    invalidation = _finite(invalidation_spot, "invalidation_spot")
    iv = _finite(base_iv, "base_iv")
    if target <= 0 or invalidation <= 0 or iv <= 0:
        return DeterministicContractValuation(
            scenarios=(), applicability_state=ModelApplicabilityState.DATA_INSUFFICIENT,
            ranking_score_uncalibrated=None, favourable_median_return=None,
            adverse_worst_return=None,
            utility_formula="MEDIAN_FAVOURABLE_RETURN_PLUS_WORST_ADVERSE_RETURN",
            american_exercise_material=False, american_exercise_reason=None,
            disclosures=("TARGET_INVALIDATION_OR_IV_NON_POSITIVE", "NO_PROBABILITY_OUTPUT"),
        )
    if side == "CALL" and not (target > invalidation):
        raise ValueError("CALL target must exceed invalidation")
    if side == "PUT" and not (target < invalidation):
        raise ValueError("PUT target must be below invalidation")

    multipliers = {
        IVStress.CONTRACTED: 0.80,
        IVStress.BASE: 1.00,
        IVStress.EXPANDED: 1.20,
    }
    for key, value in (iv_multipliers or {}).items():
        stress = key if isinstance(key, IVStress) else IVStress(str(key).upper())
        multiplier = _finite(value, f"iv_multiplier_{stress.value}")
        if multiplier <= 0:
            raise ValueError("IV stress multipliers must be positive")
        multipliers[stress] = multiplier

    ask = None if entry_ask is None else _finite(entry_ask, "entry_ask")
    if ask is not None and ask <= 0:
        ask = None
    entry_cost = ask * (1.0 + entry_bps / 10_000.0) if ask is not None else None
    valuations: list[ScenarioValuation] = []
    for path, scenario_spot in (
        (ScenarioPath.FAVOURABLE_TARGET, target),
        (ScenarioPath.ADVERSE_INVALIDATION, invalidation),
    ):
        for point in sorted(points, key=lambda item: item.sessions_elapsed):
            seconds = max(0.0, (expiry - point.as_of_utc).total_seconds())
            time_years = seconds / (365.0 * 24.0 * 60.0 * 60.0)
            for stress in IVStress:
                scenario_iv = iv * multipliers[stress]
                theoretical = dividend_adjusted_black_scholes(
                    option_side=side, spot=scenario_spot, strike=k,
                    time_to_expiry_years=time_years, risk_free_rate=r,
                    dividend_yield=q, volatility=scenario_iv,
                )
                exit_value = theoretical * (1.0 - exit_bps / 10_000.0)
                net_return = None if entry_cost is None else (exit_value - entry_cost) / entry_cost
                valuations.append(ScenarioValuation(
                    scenario_id=f"{path.value}:{point.timing.value}:{stress.value}",
                    path=path, timing=point.timing, iv_stress=stress,
                    sessions_elapsed=point.sessions_elapsed,
                    scenario_as_of_utc=point.as_of_utc,
                    scenario_spot=scenario_spot, scenario_iv=scenario_iv,
                    time_to_expiry_years=time_years,
                    theoretical_value=theoretical, entry_reference=ask,
                    entry_cost_after_friction=entry_cost,
                    exit_value_after_friction=exit_value,
                    net_return_fraction=net_return,
                ))

    latest_time_years = max((item.time_to_expiry_years for item in valuations), default=0.0)
    material, material_reason = assess_american_exercise_materiality(
        option_side=side,
        spot=min(target, invalidation) if side == "PUT" else max(target, invalidation),
        strike=k, dividend_yield=q,
        ex_dividend_within_horizon=ex_dividend_within_horizon,
        risk_free_rate=r, time_to_expiry_years=latest_time_years,
        volatility=iv,
    )
    if entry_cost is None:
        applicability = ModelApplicabilityState.DATA_INSUFFICIENT
        utility = favourable = adverse = None
    else:
        applicability = (
            ModelApplicabilityState.OUT_OF_DISTRIBUTION
            if material or corporate_action_flag or not dividend_yield_available
            else ModelApplicabilityState.DETERMINISTIC_ONLY
        )
        favourable_returns = [
            item.net_return_fraction for item in valuations
            if item.path is ScenarioPath.FAVOURABLE_TARGET and item.net_return_fraction is not None
        ]
        adverse_returns = [
            item.net_return_fraction for item in valuations
            if item.path is ScenarioPath.ADVERSE_INVALIDATION and item.net_return_fraction is not None
        ]
        favourable = median(favourable_returns)
        adverse = min(adverse_returns)
        utility = favourable + adverse

    disclosures = [
        "DETERMINISTIC_SCENARIOS_NOT_FORECASTS",
        "RANKING_SCORE_UNCALIBRATED_NOT_PROBABILITY",
        "EUROPEAN_BLACK_SCHOLES_AMERICAN_EXERCISE_NOT_MODELLED",
        "CONTINUOUS_DIVIDEND_YIELD_ASSUMPTION",
        "FRICTION_IS_PARAMETERISED_NOT_LIVE_EXECUTION_COST",
        "HUMAN_EXECUTION_ONLY",
    ]
    if entry_cost is None:
        disclosures.append("NO_POSITIVE_ASK_NO_RETURN_OR_UTILITY")
    if material_reason:
        disclosures.append(material_reason)
    if corporate_action_flag:
        disclosures.append("CORPORATE_ACTION_MODEL_APPLICABILITY_REDUCED")
    if not dividend_yield_available:
        disclosures.append("DIVIDEND_YIELD_UNAVAILABLE_ASSUMED_ZERO")
    return DeterministicContractValuation(
        scenarios=tuple(valuations), applicability_state=applicability,
        ranking_score_uncalibrated=utility,
        favourable_median_return=favourable, adverse_worst_return=adverse,
        utility_formula="MEDIAN_FAVOURABLE_RETURN_PLUS_WORST_ADVERSE_RETURN",
        american_exercise_material=material,
        american_exercise_reason=material_reason,
        disclosures=tuple(disclosures),
    )


__all__ = [
    "DOI_SCENARIO_ENGINE_VERSION", "DOI_VALUATION_MODEL_VERSION",
    "DOI_SCENARIO_UTILITY_VERSION", "DOI_SCENARIO_AUTHORITY",
    "ScenarioPath", "ScenarioTiming", "IVStress", "ScenarioPoint",
    "ScenarioValuation", "DeterministicContractValuation", "normal_cdf",
    "dividend_adjusted_black_scholes", "assess_american_exercise_materiality",
    "evaluate_deterministic_scenarios",
]
