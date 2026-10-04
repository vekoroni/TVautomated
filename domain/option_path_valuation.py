"""C8 long-option path valuation; never grants execution or capital authority.

Only a separately certified, point-in-time physical-measure C4 path set may
produce a numeric result. Descriptive C5 packets return a typed non-value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class PathSession:
    number: int
    open: float
    high: float
    low: float
    close: float
    implied_vol: float


@dataclass(frozen=True, slots=True)
class WeightedPath:
    path_id: str
    weight: float
    sessions: tuple[PathSession, ...]


@dataclass(frozen=True, slots=True)
class PhysicalPathSet:
    run_id: str
    thesis_id: str
    ticker: str
    direction: str
    reference_spot: float
    target_spot: float | None
    invalidation_spot: float | None
    c4_packet_id: str
    c4_reliability_state: str
    calibration_state: str
    paths: tuple[WeightedPath, ...]


@dataclass(frozen=True, slots=True)
class LongOptionQuote:
    symbol: str
    right: str
    strike: float
    entry_ask: float
    entry_bid: float
    multiplier: int
    annual_rate: float
    annual_dividend_yield: float
    expiry_sessions: int
    last_exit_session: int
    commission_usd_round_trip: float
    slippage_per_share_each_side: float


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _option_mark(spot: float, strike: float, years: float, iv: float, rate: float, dividend: float, right: str) -> float:
    intrinsic = max(spot - strike, 0.0) if right == "CALL" else max(strike - spot, 0.0)
    if years <= 0 or iv <= 0:
        return intrinsic
    sigma_root = iv * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * iv * iv) * years) / sigma_root
    d2 = d1 - sigma_root
    if right == "CALL":
        return max(spot * math.exp(-dividend * years) * _normal_cdf(d1)
                   - strike * math.exp(-rate * years) * _normal_cdf(d2), intrinsic)
    return max(strike * math.exp(-rate * years) * _normal_cdf(-d2)
               - spot * math.exp(-dividend * years) * _normal_cdf(-d1), intrinsic)


def value_long_option_paths(
    path_set: PhysicalPathSet | None, quote: LongOptionQuote | None,
    *, research_only: bool = False,
) -> dict:
    """Value on common underlying paths; unsupported evidence returns no EV."""
    result = {"valuation_version": "option_path_valuation_v1", "state": "NOT_VALUED_STATISTICAL_SUPPORT",
              "ev_fraction": None, "ev_usd": None, "authority": "RESEARCH_ONLY"}
    if path_set is None:
        return result
    supported = (path_set.c4_reliability_state in {"LOCAL_SUPPORTED", "POOLED_SUPPORTED"}
                 and path_set.calibration_state == "HELD_OUT_VALIDATED")
    uncalibrated_research = (research_only
                             and path_set.c4_reliability_state == "STATISTICALLY_UNRELIABLE"
                             and path_set.calibration_state == "UNCALIBRATED_RESEARCH")
    if not (supported or uncalibrated_research) or not path_set.c4_packet_id:
        return result
    if quote is None:
        return {**result, "state": "NOT_VALUED_DATA"}
    right = str(quote.right).upper()
    if right not in {"CALL", "PUT"} or right != ("CALL" if path_set.direction == "BULL" else "PUT"):
        return {**result, "state": "INVALID_DIRECTION_IDENTITY"}
    barriers_available = path_set.target_spot is not None and path_set.invalidation_spot is not None
    if not barriers_available and not uncalibrated_research:
        return {**result, "state": "NOT_VALUED_DATA"}
    values = (path_set.reference_spot, quote.strike, quote.entry_ask)
    if (not all(math.isfinite(value) and value > 0 for value in values)
            or not math.isfinite(quote.entry_bid) or quote.entry_bid < 0
            or quote.entry_bid > quote.entry_ask or quote.multiplier <= 0
            or quote.commission_usd_round_trip < 0 or quote.slippage_per_share_each_side < 0
            or quote.expiry_sessions < quote.last_exit_session
            or quote.last_exit_session < 1 or not path_set.paths):
        return {**result, "state": "INVALID_CONTRACT_OR_PATH_GEOMETRY"}
    if barriers_available:
        assert path_set.target_spot is not None and path_set.invalidation_spot is not None
        if path_set.direction == "BULL" and not path_set.invalidation_spot < path_set.reference_spot < path_set.target_spot:
            return {**result, "state": "INVALID_CONTRACT_OR_PATH_GEOMETRY"}
        if path_set.direction == "BEAR" and not path_set.target_spot < path_set.reference_spot < path_set.invalidation_spot:
            return {**result, "state": "INVALID_CONTRACT_OR_PATH_GEOMETRY"}
    weights = [path.weight for path in path_set.paths]
    if any(not math.isfinite(weight) or weight <= 0 for weight in weights) or abs(sum(weights) - 1) > 1e-8:
        return {**result, "state": "INVALID_PATH_WEIGHTS"}
    entry_cost = (quote.entry_ask + quote.slippage_per_share_each_side) * quote.multiplier
    entry_cost += quote.commission_usd_round_trip / 2
    if entry_cost <= 0:
        return {**result, "state": "INVALID_CONTRACT_OR_PATH_GEOMETRY"}
    profits: list[tuple[float, float]] = []
    event_weights = {"TARGET_FIRST": 0.0, "STOP_FIRST": 0.0, "FORCED_EXIT": 0.0}
    half_spread = (quote.entry_ask - quote.entry_bid) / 2
    for path in path_set.paths:
        if len(path.sessions) < quote.last_exit_session:
            return {**result, "state": "INCOMPLETE_PATH"}
        exit_bar: PathSession | None = None
        event = "FORCED_EXIT"
        for expected, bar in enumerate(path.sessions[:quote.last_exit_session], start=1):
            if (bar.number != expected or not all(math.isfinite(value) and value > 0 for value in
                    (bar.open, bar.high, bar.low, bar.close, bar.implied_vol))
                    or not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high):
                return {**result, "state": "INVALID_PATH_SESSION"}
            hit_target = (bar.high >= path_set.target_spot if right == "CALL" else bar.low <= path_set.target_spot) if barriers_available else False
            hit_stop = (bar.low <= path_set.invalidation_spot if right == "CALL" else bar.high >= path_set.invalidation_spot) if barriers_available else False
            if hit_target or hit_stop:
                event = "STOP_FIRST" if hit_stop else "TARGET_FIRST"
                exit_bar = bar
                break
            exit_bar = bar
        assert exit_bar is not None
        if event == "STOP_FIRST":
            assert path_set.invalidation_spot is not None
            exit_spot = (min(exit_bar.open, path_set.invalidation_spot) if right == "CALL"
                         else max(exit_bar.open, path_set.invalidation_spot))
        elif event == "TARGET_FIRST":
            assert path_set.target_spot is not None
            exit_spot = (max(exit_bar.open, path_set.target_spot) if right == "CALL"
                         else min(exit_bar.open, path_set.target_spot))
        else:
            exit_spot = exit_bar.close
        remaining_sessions = max(quote.expiry_sessions - exit_bar.number, 0)
        mark = _option_mark(exit_spot, quote.strike, remaining_sessions / 252.0,
                            exit_bar.implied_vol, quote.annual_rate, quote.annual_dividend_yield, right)
        exit_bid_like = max(mark - half_spread - quote.slippage_per_share_each_side, 0.0)
        proceeds = exit_bid_like * quote.multiplier - quote.commission_usd_round_trip / 2
        profits.append((path.weight, proceeds - entry_cost))
        event_weights[event] += path.weight
    expected_profit = sum(weight * profit for weight, profit in profits)
    return {**result, "state": ("RESEARCH_EV_UNCALIBRATED" if uncalibrated_research
                                 else "RESEARCH_ESTIMATE"),
            "ev_fraction": expected_profit / entry_cost,
            "ev_usd": expected_profit, "entry_cost_usd": entry_cost,
            "event_weights": event_weights, "path_count": len(path_set.paths),
            "calibration_state": path_set.calibration_state,
            "exit_policy": ("FIRST_TARGET_STOP_OR_TIME" if barriers_available
                            else "TIME_ONLY_NO_GOVERNED_BARRIERS"),
            "physical_path_source": path_set.c4_packet_id,
            **({"per_path_return_fraction": [profit / entry_cost for _, profit in profits]}
               if uncalibrated_research else {})}
