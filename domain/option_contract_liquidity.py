"""Governed lifecycle contract for long CALL and long PUT liquidity.

This module deliberately separates three questions that were previously easy
to conflate:

* whether the underlying thesis remains valid;
* whether one contract is executable now; and
* whether an unexecutable contract is worth monitoring for maturation.

The maturation score is a deterministic, explainable prioritisation score.  It
is *not* a calibrated probability and it has no execution or capital authority.
Only a current exact-contract assessment may return ``EXECUTABLE_NOW``.

The module is provider-agnostic and side-effect free.  It does not fetch quotes,
persist observations, select replacement contracts, or authorise a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from typing import Any, Dict, Mapping, Sequence

from .long_option_execution import quote_spread_percent


OPTIONS_LIQUIDITY_LIFECYCLE_VERSION = "options-liquidity-lifecycle-v2"
MATURATION_SCORE_VERSION = "liquidity-maturation-deterministic-v1"
MATURATION_SCORE_AUTHORITY = "ADVISORY_NON_EXECUTION"


class _ValueEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MonitorState(_ValueEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    TERMINAL = "TERMINAL"


class ContractLiquidityState(_ValueEnum):
    EXECUTABLE_NOW = "EXECUTABLE_NOW"
    REVIEWABLE_SPREAD = "REVIEWABLE_SPREAD"
    LIQUIDITY_PENDING = "LIQUIDITY_PENDING"
    QUOTE_STALE = "QUOTE_STALE"
    QUOTE_TIMESTAMP_UNAVAILABLE = "QUOTE_TIMESTAMP_UNAVAILABLE"
    ZERO_BID = "ZERO_BID"
    NO_DISPLAYED_SIZE = "NO_DISPLAYED_SIZE"
    NO_CURRENT_MARKET = "NO_CURRENT_MARKET"
    DTE_UNSUITABLE = "DTE_UNSUITABLE"
    MONEYNESS_UNSUITABLE = "MONEYNESS_UNSUITABLE"
    THESIS_TARGET_UNREACHABLE = "THESIS_TARGET_UNREACHABLE"
    TERMINAL_REJECT = "TERMINAL_REJECT"
    NO_LISTED_MARKET = "NO_LISTED_MARKET"
    INVALID_QUOTE = "INVALID_QUOTE"


@dataclass(frozen=True, slots=True)
class ContractFetchPolicyDecision:
    should_fetch: bool
    reason: str


def decide_contract_quote_fetch(
    *,
    thesis_state: Any,
    monitor_state: Any,
    horizon_end_date: date | None,
    current_date: date,
    latest_liquidity_state: Any = None,
    latest_quote_age_seconds: float | None = None,
    freshness_seconds: int,
) -> ContractFetchPolicyDecision:
    """Decide whether an adapter may fetch a quote for an active thesis.

    This function has no knowledge of providers or databases. A caller maps a
    positive decision to its governed provider and performs the side effect.
    """

    if freshness_seconds < 0:
        raise ValueError("freshness_seconds cannot be negative")
    thesis = str(getattr(thesis_state, "value", thesis_state) or "").strip().upper()
    monitor = str(getattr(monitor_state, "value", monitor_state) or "").strip().upper()
    latest = str(
        getattr(latest_liquidity_state, "value", latest_liquidity_state) or ""
    ).strip().upper()
    if thesis in {"INVALIDATED", "TARGET_REALIZED", "HORIZON_EXPIRED", "COMPLETED"}:
        return ContractFetchPolicyDecision(False, f"THESIS_{thesis}")
    if monitor != MonitorState.ACTIVE.value:
        return ContractFetchPolicyDecision(False, f"MONITOR_{monitor or 'MISSING'}")
    if horizon_end_date and current_date > horizon_end_date:
        return ContractFetchPolicyDecision(False, "HORIZON_EXPIRED")
    if not latest:
        return ContractFetchPolicyDecision(True, "OBSERVATION_MISSING")
    if latest == ContractLiquidityState.QUOTE_STALE.value:
        return ContractFetchPolicyDecision(True, "QUOTE_MARKED_STALE")
    if latest_quote_age_seconds is None:
        return ContractFetchPolicyDecision(True, "CANONICAL_OBSERVATION_AGE_UNKNOWN")
    if latest_quote_age_seconds <= freshness_seconds:
        if latest == ContractLiquidityState.EXECUTABLE_NOW.value:
            return ContractFetchPolicyDecision(False, "FRESH_EXECUTABLE_CONTRACT")
        return ContractFetchPolicyDecision(False, "FRESH_CANONICAL_OBSERVATION")
    return ContractFetchPolicyDecision(True, "CANONICAL_OBSERVATION_STALE")


def validate_contract_replacement(
    *,
    previous_contract_symbol: Any,
    selected_contract_symbol: Any,
    economics_recomputed: bool,
    observed_contract_symbol: Any = None,
) -> bool:
    """Validate exact-contract replacement and return whether it changed.

    A replacement is a new economic object. It cannot inherit the former
    contract's economics, and the selected quote must identify the exact
    replacement contract.
    """

    previous = str(previous_contract_symbol or "").strip().upper()
    selected = str(selected_contract_symbol or "").strip().upper()
    observed = str(observed_contract_symbol or "").strip().upper()
    if not selected:
        raise ValueError("selected_contract_symbol is required")
    changed = bool(previous and previous != selected)
    if changed and not economics_recomputed:
        raise ValueError("replacement contract requires exact economics recomputation")
    if observed and observed != selected:
        raise ValueError("selected contract does not match selected observation")
    return changed

ALLOWED_SIDES = frozenset({"CALL", "PUT"})
MATURATION_HORIZONS = (1, 2, 3)

DEFAULT_ATM_TOLERANCE_PCT = 0.50
DEFAULT_EXECUTABLE_SPREAD_MAX_PCT = 18.0
DEFAULT_REVIEWABLE_SPREAD_MAX_PCT = 25.0
DEFAULT_QUOTE_FRESHNESS_MAX_SECONDS = 15 * 60
DEFAULT_MONITOR_SESSIONS = 3
DEFAULT_EXIT_BUFFER_SESSIONS = 5
DEFAULT_MIN_REMAINING_RUNWAY_FACTOR = 0.20
GOVERNED_HOLD_SESSIONS = frozenset({5.0, 10.0, 20.0})

EXECUTABLE_STATES = frozenset({"EXECUTABLE_NOW"})
RECOVERABLE_STATES = frozenset(
    {
        "REVIEWABLE_SPREAD",
        "LIQUIDITY_PENDING",
        "QUOTE_STALE",
        "ZERO_BID",
        "NO_DISPLAYED_SIZE",
        "NO_CURRENT_MARKET",
    }
)
CONTRACT_REPAIR_STATES = frozenset({"DTE_UNSUITABLE", "MONEYNESS_UNSUITABLE"})
TERMINAL_STATES = frozenset({"NO_LISTED_MARKET", "INVALID_QUOTE"})

MONEYNESS_TREATMENTS = frozenset(
    {
        "REJECT_FAR_OTM",
        "MONITOR_OTM_MATURATION",
        "PREFERRED_EXECUTION",
        "REVIEW_ITM_STOCK_REPLACEMENT",
        "OUTSIDE_DEFAULT_CONVEXITY_MANDATE",
        "UNKNOWN_DELTA_REPAIR",
    }
)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def canonical_option_side(value: Any) -> str:
    """Return ``CALL`` or ``PUT`` and fail closed for all other strategies."""
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"CALL", "C", "LONG_CALL"}:
        return "CALL"
    if text in {"PUT", "P", "LONG_PUT"}:
        return "PUT"
    raise ValueError(f"unsupported long-option side: {value!r}")


def calculate_dte_requirement(
    remaining_hold_sessions: Any,
    *,
    monitor_sessions: Any = DEFAULT_MONITOR_SESSIONS,
    exit_buffer_sessions: Any = DEFAULT_EXIT_BUFFER_SESSIONS,
) -> Dict[str, Any]:
    """Calculate the DTE needed before waiting for contract liquidity.

    DTE is calendar time whereas the inputs are trading-session allowances.  A
    conservative session sum is used as the minimum contract requirement; the
    integration layer may apply a larger calendar-day conversion if desired.
    """
    hold = _finite_number(remaining_hold_sessions)
    monitor = _finite_number(monitor_sessions)
    exit_buffer = _finite_number(exit_buffer_sessions)
    if hold is None or monitor is None or exit_buffer is None:
        raise ValueError("DTE requirement inputs must be finite numbers")
    if hold < 0 or monitor < 0 or exit_buffer < 0:
        raise ValueError("DTE requirement inputs cannot be negative")
    if hold not in GOVERNED_HOLD_SESSIONS:
        raise ValueError(
            "remaining_hold_sessions must be a governed routed hold in {5, 10, 20}"
        )
    minimum = math.ceil(hold + monitor + exit_buffer)
    return {
        "remaining_hold_sessions": hold,
        "monitor_sessions": monitor,
        "exit_buffer_sessions": exit_buffer,
        "minimum_required_dte": minimum,
        "calculation_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    }


def classify_moneyness(
    side: Any,
    *,
    spot: Any,
    strike: Any,
    delta: Any = None,
    atm_tolerance_pct: float = DEFAULT_ATM_TOLERANCE_PCT,
) -> Dict[str, Any]:
    """Classify price moneyness separately from the governed delta profile."""
    option_side = canonical_option_side(side)
    spot_value = _finite_number(spot)
    strike_value = _finite_number(strike)
    delta_value = _finite_number(delta)
    tolerance = _finite_number(atm_tolerance_pct)
    if spot_value is None or strike_value is None or spot_value <= 0 or strike_value <= 0:
        raise ValueError("spot and strike must be positive finite numbers")
    if tolerance is None or tolerance < 0:
        raise ValueError("atm_tolerance_pct must be a non-negative finite number")

    # Positive means the strike is still ahead in the thesis direction (OTM).
    directional_distance_pct = (
        ((strike_value / spot_value) - 1.0) * 100.0
        if option_side == "CALL"
        else ((spot_value / strike_value) - 1.0) * 100.0
    )
    if directional_distance_pct > tolerance:
        moneyness_state = "OTM"
    elif directional_distance_pct < -tolerance:
        moneyness_state = "ITM"
    else:
        moneyness_state = "ATM"

    absolute_delta = abs(delta_value) if delta_value is not None else None
    if absolute_delta is None:
        delta_band = "UNKNOWN"
        treatment = "UNKNOWN_DELTA_REPAIR"
    elif absolute_delta < 0.20:
        delta_band = "FAR_OTM_LT_020"
        treatment = "REJECT_FAR_OTM"
    elif absolute_delta < 0.35:
        delta_band = "DEVELOPING_OTM_020_035"
        treatment = "MONITOR_OTM_MATURATION"
    elif absolute_delta <= 0.60:
        delta_band = "NEAR_ATM_035_060"
        treatment = "PREFERRED_EXECUTION"
    elif absolute_delta <= 0.75:
        delta_band = "ITM_060_075"
        treatment = "REVIEW_ITM_STOCK_REPLACEMENT"
    else:
        delta_band = "DEEP_ITM_GT_075"
        treatment = "OUTSIDE_DEFAULT_CONVEXITY_MANDATE"

    delta_moneyness_consistent = True
    if absolute_delta is not None:
        delta_moneyness_consistent = not (
            (moneyness_state == "OTM" and absolute_delta > 0.60)
            or (moneyness_state == "ITM" and absolute_delta < 0.35)
        )

    return {
        "side": option_side,
        "moneyness_state": moneyness_state,
        "directional_distance_to_strike_pct": round(directional_distance_pct, 6),
        "absolute_delta": absolute_delta,
        "delta_band": delta_band,
        "moneyness_treatment": treatment,
        "delta_moneyness_consistent": delta_moneyness_consistent,
        "atm_tolerance_pct": tolerance,
        "calculation_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    }


def calculate_expected_move_features(
    side: Any,
    *,
    spot: Any,
    strike: Any,
    forecast_vol_annual: Any,
    horizon_sessions: int,
) -> Dict[str, Any]:
    """Measure directional distance to ATM in forecast-volatility units."""
    option_side = canonical_option_side(side)
    spot_value = _finite_number(spot)
    strike_value = _finite_number(strike)
    forecast_vol = _finite_number(forecast_vol_annual)
    if spot_value is None or strike_value is None or spot_value <= 0 or strike_value <= 0:
        raise ValueError("spot and strike must be positive finite numbers")
    if forecast_vol is None or forecast_vol <= 0:
        raise ValueError("forecast_vol_annual must be a positive decimal")
    if not isinstance(horizon_sessions, int) or horizon_sessions <= 0:
        raise ValueError("horizon_sessions must be a positive integer")

    expected_move_pct = forecast_vol * math.sqrt(horizon_sessions / 252.0)
    expected_move_abs = spot_value * expected_move_pct
    directional_log_distance = (
        math.log(strike_value / spot_value)
        if option_side == "CALL"
        else math.log(spot_value / strike_value)
    )
    # A negative distance means spot has already crossed the strike into ITM.
    distance_still_to_travel = max(0.0, directional_log_distance)
    atm_distance_sigma = distance_still_to_travel / expected_move_pct
    reach_score = _clamp(1.0 - (atm_distance_sigma / 2.0))
    return {
        "side": option_side,
        "horizon_sessions": horizon_sessions,
        "forecast_vol_annual": forecast_vol,
        "expected_move_pct": round(expected_move_pct * 100.0, 6),
        "expected_move_abs": round(expected_move_abs, 6),
        "directional_log_distance": round(directional_log_distance, 9),
        "atm_distance_sigma": round(atm_distance_sigma, 6),
        "strike_reach_score": round(reach_score * 100.0, 2),
        "score_is_probability": False,
        "calculation_version": MATURATION_SCORE_VERSION,
    }


def _liquidity_result(
    state: str,
    disposition: str,
    *,
    executable_now: bool = False,
    reasons: Sequence[str] = (),
    **fields: Any,
) -> Dict[str, Any]:
    return {
        "liquidity_state": state,
        "recovery_disposition": disposition,
        "executable_now": executable_now,
        "liquidity_reasons": list(reasons),
        # Executable describes the exact current quote; it never grants capital
        # authority. Keeping this explicit avoids reviving the retired multi-
        # authority conflict in downstream CSV consumers.
        "current_quote_executable": state == "EXECUTABLE_NOW",
        "execution_authority": False,
        "execution_authority_reason": "QUOTE_STATE_ONLY_NO_CAPITAL_AUTHORITY",
        "calculation_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
        **fields,
    }


def classify_current_executability(
    *,
    bid: Any,
    ask: Any,
    bid_size: Any = None,
    ask_size: Any = None,
    quote_age_seconds: Any = None,
    dte: Any,
    minimum_required_dte: Any,
    moneyness_treatment: str,
    listed_market: bool = True,
    executable_spread_max_pct: float = DEFAULT_EXECUTABLE_SPREAD_MAX_PCT,
    reviewable_spread_max_pct: float = DEFAULT_REVIEWABLE_SPREAD_MAX_PCT,
    quote_freshness_max_seconds: float = DEFAULT_QUOTE_FRESHNESS_MAX_SECONDS,
    require_displayed_size: bool = False,
) -> Dict[str, Any]:
    """Classify the current exact quote without using OI as a hard gate."""
    bid_value = _finite_number(bid)
    ask_value = _finite_number(ask)
    bid_size_value = _finite_number(bid_size)
    ask_size_value = _finite_number(ask_size)
    age = _finite_number(quote_age_seconds)
    dte_value = _finite_number(dte)
    minimum_dte = _finite_number(minimum_required_dte)
    executable_limit = _finite_number(executable_spread_max_pct)
    reviewable_limit = _finite_number(reviewable_spread_max_pct)
    freshness_limit = _finite_number(quote_freshness_max_seconds)

    if not listed_market:
        return _liquidity_result(
            "NO_LISTED_MARKET", "TERMINAL", reasons=("NO_LISTED_OPTIONS_MARKET",)
        )
    if dte_value is None or minimum_dte is None or dte_value < 0 or minimum_dte < 0:
        return _liquidity_result("INVALID_QUOTE", "TERMINAL", reasons=("INVALID_DTE",))
    if dte_value < minimum_dte:
        return _liquidity_result(
            "DTE_UNSUITABLE",
            "CONTRACT_REPAIR",
            reasons=("DTE_BELOW_HOLD_MONITOR_EXIT_REQUIREMENT",),
            dte=dte_value,
            minimum_required_dte=minimum_dte,
        )
    if moneyness_treatment not in MONEYNESS_TREATMENTS:
        return _liquidity_result(
            "INVALID_QUOTE", "TERMINAL", reasons=("UNKNOWN_MONEYNESS_TREATMENT",)
        )
    if moneyness_treatment in {
        "REJECT_FAR_OTM",
        "OUTSIDE_DEFAULT_CONVEXITY_MANDATE",
        "UNKNOWN_DELTA_REPAIR",
    }:
        return _liquidity_result(
            "MONEYNESS_UNSUITABLE",
            "CONTRACT_REPAIR",
            reasons=(moneyness_treatment,),
            dte=dte_value,
            minimum_required_dte=minimum_dte,
        )
    if bid_value is None and ask_value is None:
        return _liquidity_result(
            "NO_CURRENT_MARKET", "MONITOR", reasons=("NO_CURRENT_TWO_SIDED_QUOTE",)
        )
    if bid_value is None or ask_value is None or ask_value <= 0 or bid_value < 0:
        return _liquidity_result(
            "INVALID_QUOTE", "TERMINAL", reasons=("MALFORMED_ONE_SIDED_QUOTE",)
        )
    if bid_value == 0:
        return _liquidity_result(
            "ZERO_BID", "MONITOR", reasons=("ZERO_BID_NOT_EXECUTABLE",)
        )
    if bid_value > ask_value:
        return _liquidity_result(
            "INVALID_QUOTE", "TERMINAL", reasons=("CROSSED_QUOTE",)
        )
    # Structural quote invalidity takes precedence over freshness. A stale
    # crossed quote is still invalid and must never be downgraded to a merely
    # monitorable QUOTE_STALE state.
    if freshness_limit is None or freshness_limit < 0:
        raise ValueError("quote_freshness_max_seconds must be non-negative")
    if age is None:
        return _liquidity_result(
            "QUOTE_TIMESTAMP_UNAVAILABLE",
            "MONITOR",
            reasons=("PROVIDER_QUOTE_TIMESTAMP_REQUIRED",),
        )
    if age > freshness_limit:
        return _liquidity_result(
            "QUOTE_STALE",
            "MONITOR",
            reasons=("QUOTE_OUTSIDE_FRESHNESS_WINDOW",),
            quote_age_seconds=age,
        )
    spread_pct = quote_spread_percent(bid_value, ask_value)
    if spread_pct is None:
        return _liquidity_result(
            "INVALID_QUOTE", "TERMINAL", reasons=("INVALID_SPREAD_GEOMETRY",)
        )
    if executable_limit is None or reviewable_limit is None:
        raise ValueError("spread limits must be finite numbers")
    if executable_limit < 0 or reviewable_limit < executable_limit:
        raise ValueError("spread limits must satisfy 0 <= executable <= reviewable")

    displayed_size_missing = (
        bid_size_value is None
        or ask_size_value is None
        or bid_size_value <= 0
        or ask_size_value <= 0
    )
    common = {
        "bid": bid_value,
        "ask": ask_value,
        "spread_pct": round(spread_pct, 6),
        "quote_age_seconds": age,
        "dte": dte_value,
        "minimum_required_dte": minimum_dte,
        "displayed_size_available": not displayed_size_missing,
    }
    if require_displayed_size and displayed_size_missing:
        return _liquidity_result(
            "NO_DISPLAYED_SIZE",
            "MONITOR",
            reasons=("DISPLAYED_SIZE_REQUIRED_FOR_EXECUTION",),
            **common,
        )
    if spread_pct <= executable_limit:
        return _liquidity_result(
            "EXECUTABLE_NOW", "EXECUTABLE", executable_now=True, **common
        )
    if spread_pct <= reviewable_limit:
        return _liquidity_result(
            "REVIEWABLE_SPREAD",
            "MONITOR",
            reasons=("SPREAD_REQUIRES_MANUAL_REVIEW",),
            **common,
        )
    return _liquidity_result(
        "LIQUIDITY_PENDING",
        "MONITOR",
        reasons=("SPREAD_ABOVE_REVIEWABLE_LIMIT",),
        **common,
    )


def classify_remaining_runway(
    side: Any,
    *,
    thesis_spot: Any,
    current_spot: Any,
    structural_target: Any,
    invalidation_spot: Any,
    one_session_expected_move_abs: Any = None,
    min_remaining_runway_factor: float = DEFAULT_MIN_REMAINING_RUNWAY_FACTOR,
) -> Dict[str, Any]:
    """Classify whether an overnight move leaves enough thesis runway."""
    option_side = canonical_option_side(side)
    origin = _finite_number(thesis_spot)
    current = _finite_number(current_spot)
    target = _finite_number(structural_target)
    invalidation = _finite_number(invalidation_spot)
    expected_move = _finite_number(one_session_expected_move_abs)
    minimum_remaining = _finite_number(min_remaining_runway_factor)
    if any(value is None for value in (origin, current, target, invalidation)):
        raise ValueError("runway prices must be finite numbers")
    assert origin is not None and current is not None and target is not None and invalidation is not None
    if min(origin, current, target, invalidation) <= 0:
        raise ValueError("runway prices must be positive")
    if minimum_remaining is None or not 0 <= minimum_remaining <= 1:
        raise ValueError("min_remaining_runway_factor must be between zero and one")

    direction = 1.0 if option_side == "CALL" else -1.0
    total_move = direction * (target - origin)
    realised_move = direction * (current - origin)
    invalidation_geometry = direction * (origin - invalidation)
    if invalidation_geometry <= 0:
        raise ValueError(
            "invalidation_spot must be beyond thesis_spot opposite the option direction"
        )
    invalidated = direction * (current - invalidation) <= 0
    if total_move <= 0:
        raise ValueError("structural target must be beyond thesis spot in the option direction")

    consumed_factor = realised_move / total_move
    remaining_factor = _clamp(1.0 - consumed_factor)
    favourable_move = realised_move > 0
    gap_abs = abs(current - origin)

    if invalidated:
        state = "THESIS_INVALIDATED"
    elif consumed_factor >= 1.0 or remaining_factor < minimum_remaining:
        state = "MOVE_ALREADY_REALIZED"
    elif favourable_move and expected_move is not None and expected_move > 0 and gap_abs >= expected_move:
        state = "WAIT_FOR_PULLBACK"
    elif favourable_move and consumed_factor >= 0.50:
        state = "GAP_CONFIRMATION_EXTENDED"
    elif favourable_move:
        state = "GAP_CONFIRMATION_WITH_RUNWAY"
    elif realised_move < 0:
        state = "THESIS_UNDER_PRESSURE"
    else:
        state = "THESIS_ACTIVE"

    return {
        "remaining_runway_state": state,
        "thesis_move_total": round(total_move, 6),
        "thesis_move_realised": round(realised_move, 6),
        "thesis_move_consumed_factor": round(consumed_factor, 6),
        "remaining_runway_factor": round(remaining_factor, 6),
        "minimum_remaining_runway_factor": minimum_remaining,
        "calculation_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    }


_LIQUIDITY_MATURATION_FACTOR = {
    "REVIEWABLE_SPREAD": 0.90,
    "LIQUIDITY_PENDING": 0.70,
    "QUOTE_STALE": 0.55,
    "ZERO_BID": 0.35,
    "NO_DISPLAYED_SIZE": 0.55,
    "NO_CURRENT_MARKET": 0.20,
}


def evaluate_maturation_horizons(
    side: Any,
    *,
    spot: Any,
    strike: Any,
    forecast_vol_annual: Any,
    liquidity_assessment: Mapping[str, Any],
    remaining_runway_factor: Any,
    thesis_active: bool,
    neighbouring_contract_liquidity_score: Any = None,
    horizons: Sequence[int] = MATURATION_HORIZONS,
) -> Dict[str, Any]:
    """Return deterministic 1/2/3-session maturation priority scores.

    The scores look probability-like because they are bounded to 0..100, but
    they are not fitted or calibrated probabilities.  The returned authority
    fields are intentionally explicit so no caller can legitimately treat the
    score as permission to trade.
    """
    state = str(liquidity_assessment.get("liquidity_state") or "")
    disposition = str(liquidity_assessment.get("recovery_disposition") or "")
    runway = _finite_number(remaining_runway_factor)
    neighbour = _finite_number(neighbouring_contract_liquidity_score)
    if runway is None or not 0 <= runway <= 1:
        raise ValueError("remaining_runway_factor must be between zero and one")
    if neighbour is not None and not 0 <= neighbour <= 1:
        raise ValueError("neighbouring_contract_liquidity_score must be between zero and one")
    if not horizons or any(not isinstance(value, int) or value <= 0 for value in horizons):
        raise ValueError("maturation horizons must be positive integers")

    result: Dict[str, Any] = {
        "maturation_score_version": MATURATION_SCORE_VERSION,
        "maturation_score_authority": MATURATION_SCORE_AUTHORITY,
        "maturation_score_is_probability": False,
        "maturation_execution_authority": False,
        "maturation_may_authorize_trade": False,
    }
    if state == "EXECUTABLE_NOW":
        eligibility = "ALREADY_EXECUTABLE"
    elif not thesis_active or runway <= 0:
        eligibility = "NOT_ELIGIBLE_THESIS_OR_RUNWAY"
    elif disposition != "MONITOR" or state not in RECOVERABLE_STATES:
        eligibility = "NOT_ELIGIBLE_THIS_CONTRACT"
    else:
        eligibility = "ELIGIBLE_FOR_MONITORING"
    result["maturation_eligibility"] = eligibility

    quote_factor = _LIQUIDITY_MATURATION_FACTOR.get(state, 0.0)
    if neighbour is None:
        execution_proxy = quote_factor
        neighbour_basis = "NOT_SUPPLIED_QUOTE_ONLY"
    else:
        execution_proxy = (0.55 * quote_factor) + (0.45 * neighbour)
        neighbour_basis = "SUPPLIED"
    result["neighbouring_liquidity_basis"] = neighbour_basis

    for horizon in horizons:
        features = calculate_expected_move_features(
            side,
            spot=spot,
            strike=strike,
            forecast_vol_annual=forecast_vol_annual,
            horizon_sessions=horizon,
        )
        if eligibility == "ALREADY_EXECUTABLE":
            score = 100.0
            score_state = "ALREADY_EXECUTABLE"
        elif eligibility != "ELIGIBLE_FOR_MONITORING":
            score = 0.0
            score_state = "NOT_ELIGIBLE"
        else:
            reach_factor = features["strike_reach_score"] / 100.0
            score = round(100.0 * reach_factor * execution_proxy * runway, 2)
            if score >= 60:
                score_state = "LIQUIDITY_PENDING_HIGH"
            elif score >= 35:
                score_state = "LIQUIDITY_PENDING_MEDIUM"
            else:
                score_state = "LIQUIDITY_PENDING_LOW"
        result[f"maturation_score_{horizon}d"] = score
        result[f"maturation_state_{horizon}d"] = score_state
        result[f"atm_distance_sigma_{horizon}d"] = features["atm_distance_sigma"]
        result[f"expected_move_pct_{horizon}d"] = features["expected_move_pct"]
    return result


@dataclass(frozen=True)
class LifecycleInputs:
    """Typed convenience input for the composite evaluator."""

    side: str
    spot: float
    strike: float
    delta: float | None
    bid: float | None
    ask: float | None
    dte: float
    remaining_hold_sessions: float
    forecast_vol_annual: float
    thesis_spot: float
    current_spot: float
    structural_target: float
    invalidation_spot: float
    bid_size: float | None = None
    ask_size: float | None = None
    quote_age_seconds: float | None = None
    listed_market: bool = True
    neighbouring_contract_liquidity_score: float | None = None
    one_session_expected_move_abs: float | None = None


def evaluate_options_liquidity_lifecycle(
    inputs: LifecycleInputs | Mapping[str, Any],
    *,
    monitor_sessions: int = DEFAULT_MONITOR_SESSIONS,
    exit_buffer_sessions: int = DEFAULT_EXIT_BUFFER_SESSIONS,
    require_displayed_size: bool = False,
) -> Dict[str, Any]:
    """Evaluate moneyness, current liquidity, runway and maturation together."""
    values = inputs.__dict__ if isinstance(inputs, LifecycleInputs) else dict(inputs)
    dte_requirement = calculate_dte_requirement(
        values["remaining_hold_sessions"],
        monitor_sessions=monitor_sessions,
        exit_buffer_sessions=exit_buffer_sessions,
    )
    moneyness = classify_moneyness(
        values["side"],
        spot=values["spot"],
        strike=values["strike"],
        delta=values.get("delta"),
    )
    liquidity = classify_current_executability(
        bid=values.get("bid"),
        ask=values.get("ask"),
        bid_size=values.get("bid_size"),
        ask_size=values.get("ask_size"),
        quote_age_seconds=values.get("quote_age_seconds"),
        dte=values["dte"],
        minimum_required_dte=dte_requirement["minimum_required_dte"],
        moneyness_treatment=moneyness["moneyness_treatment"],
        listed_market=bool(values.get("listed_market", True)),
        require_displayed_size=require_displayed_size,
    )
    expected_move = values.get("one_session_expected_move_abs")
    if expected_move is None:
        expected_move = calculate_expected_move_features(
            values["side"],
            spot=values["thesis_spot"],
            strike=values["structural_target"],
            forecast_vol_annual=values["forecast_vol_annual"],
            horizon_sessions=1,
        )["expected_move_abs"]
    runway = classify_remaining_runway(
        values["side"],
        thesis_spot=values["thesis_spot"],
        current_spot=values["current_spot"],
        structural_target=values["structural_target"],
        invalidation_spot=values["invalidation_spot"],
        one_session_expected_move_abs=expected_move,
    )
    thesis_active = runway["remaining_runway_state"] not in {
        "THESIS_INVALIDATED",
        "MOVE_ALREADY_REALIZED",
    }
    maturation = evaluate_maturation_horizons(
        values["side"],
        spot=values["spot"],
        strike=values["strike"],
        forecast_vol_annual=values["forecast_vol_annual"],
        liquidity_assessment=liquidity,
        remaining_runway_factor=runway["remaining_runway_factor"],
        thesis_active=thesis_active,
        neighbouring_contract_liquidity_score=values.get(
            "neighbouring_contract_liquidity_score"
        ),
    )
    return {
        "lifecycle_contract_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
        **dte_requirement,
        **moneyness,
        **liquidity,
        **runway,
        **maturation,
    }
