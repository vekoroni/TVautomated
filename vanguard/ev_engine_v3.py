"""AVSHUNTER EV Engine v3, Stage EV-2B production-evidence implementation.

This module compares long CALL/PUT contracts with bull-call/bear-put debit
spreads. Every output is namespaced ``ev3_*`` and is published as governed
production evidence. ``ev3_capital_eligible`` remains false until a separately
calibrated capital policy is approved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from vanguard.ev3_stage0 import EV3ValidationResult, validate_ev3_input


EV3_ENGINE_VERSION = "ev3-stage2b-v0.6.0"
EV3_EVALUATED_STATUS = "EVALUATED_PRODUCTION_EVIDENCE"


@dataclass(frozen=True)
class EV3Policy:
    """Versioned economic and uncertainty policy for the EV3 evidence engine."""

    policy_version: str = "ev3-policy-v0.3.0"
    default_risk_free_rate: float = 0.045
    default_dividend_yield: float = 0.0
    iv_stress_fraction: float = 0.15
    slippage_fraction_of_mid_each_side: float = 0.02
    one_sided_z: float = 1.645
    model_uncertainty_return: float = 0.02
    default_input_uncertainty_return: float = 0.01
    capital_hurdle_return: float = 0.02
    max_contracts_per_thesis: int = 12
    selection_tie_tolerance: float = 0.005
    minimum_open_interest: int = 50
    minimum_volume: int = 1
    maximum_spread_fraction_mid: float = 0.35
    crr_min_steps: int = 40
    crr_max_steps: int = 365


def _rejection(reason: str, detail: str = "", **values: Any) -> dict[str, Any]:
    result = {
        "ev3_engine_version": EV3_ENGINE_VERSION,
        "ev3_status": "REJECTED",
        "ev3_reason_code": reason,
        "ev3_reason_detail": detail,
        "ev3_absolute_state": "UNVALIDATED",
        "ev3_capital_eligible": False,
        "ev3_shadow_only": False,
        "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
    }
    result.update(values)
    return result


def not_applicable_result(reason: str, detail: str = "", **values: Any) -> dict[str, Any]:
    result = {
        "ev3_engine_version": EV3_ENGINE_VERSION,
        "ev3_status": "NOT_APPLICABLE",
        "ev3_reason_code": reason,
        "ev3_reason_detail": detail,
        "ev3_absolute_state": "NOT_APPLICABLE",
        "ev3_capital_eligible": False,
        "ev3_shadow_only": False,
        "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
    }
    result.update(values)
    return result


class EV3BarrierCache:
    """Validated, indexed access to the Stage EV-0 barrier sidecar."""

    KEY = [
        "state_key",
        "direction",
        "horizon_sessions",
        "target_distance_fraction",
        "stop_distance_fraction",
    ]
    EXIT_SESSION_DEFAULT_UNCERTAINTY_RETURN = 0.01
    FALLBACK_MIN_EFFECTIVE_OBSERVATIONS = 30.0
    FALLBACK_PENALTY_RETURN = 0.02

    def __init__(self, frame: pd.DataFrame):
        required = set(self.KEY) | {
            "p_target_first", "p_stop_first", "p_timeout", "n_effective",
            "target_exit_session_mean", "stop_exit_session_mean_conservative",
            "timeout_exit_session", "calculation_version", "schema_version",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"barrier cache missing columns: {missing}")
        if frame.duplicated(self.KEY).any():
            raise ValueError("barrier cache contains duplicate lookup keys")
        sums = frame[["p_target_first", "p_stop_first", "p_timeout"]].sum(axis=1)
        if not np.allclose(sums, 1.0, atol=1e-9):
            raise ValueError("barrier probabilities are not exhaustive")
        self.frame = frame.copy()
        self.frame["state_key"] = self.frame["state_key"].astype(str).str.strip().str.upper()
        self.frame["direction"] = self.frame["direction"].astype(str).str.upper()

    @classmethod
    def load(cls, path: str | Path) -> "EV3BarrierCache":
        return cls(pd.read_parquet(path))

    def lookup(
        self,
        state_key: str,
        direction: str,
        horizon_sessions: int,
        target_distance: float,
        stop_distance: float,
    ) -> tuple[pd.Series | None, str, str]:
        # Stage EV-0 deliberately materialised only exact policy endpoints.
        if horizon_sessions not in {5, 10, 20}:
            return None, "REJECT_BARRIER_HORIZON_UNAVAILABLE", f"hold={horizon_sessions}; available=5,10,20"
        requested_state = str(state_key).strip().upper()
        direction = str(direction).upper()
        horizon_sessions = int(horizon_sessions)
        exact_subset = self.frame[
            (self.frame["state_key"] == requested_state)
            & (self.frame["direction"] == direction)
            & (self.frame["horizon_sessions"] == horizon_sessions)
        ]
        subset = exact_subset
        fallback_match_count: int | None = None
        requested_parts = requested_state.split("|")
        if subset.empty:
            if len(requested_parts) != 7:
                return None, "REJECT_BARRIER_STATE_UNAVAILABLE", (
                    f"state={requested_state}; expected=7 dimensions"
                )
            candidates = self.frame[
                (self.frame["direction"] == direction)
                & (self.frame["horizon_sessions"] == horizon_sessions)
            ].copy()
            if not candidates.empty:
                candidate_parts = candidates["state_key"].str.split("|")
                core_aligned = candidate_parts.map(
                    lambda parts: len(parts) == 7
                    and parts[0] == requested_parts[0]
                    and parts[1] == requested_parts[1]
                )
                candidates = candidates[core_aligned].copy()
                if not candidates.empty:
                    candidates["_state_matches"] = candidates["state_key"].map(
                        lambda key: sum(
                            left == right
                            for left, right in zip(str(key).split("|"), requested_parts)
                        )
                    )
                    fallback_match_count = int(candidates["_state_matches"].max())
                    if fallback_match_count >= 5:
                        subset = candidates[
                            candidates["_state_matches"] == fallback_match_count
                        ].copy()
            if subset.empty:
                return None, "REJECT_BARRIER_STATE_UNAVAILABLE", (
                    f"state={requested_state}, direction={direction}, hold={horizon_sessions}; "
                    "no core-aligned state matched at least 5 of 7 dimensions"
                )
        targets = sorted(subset["target_distance_fraction"].unique())
        stops = sorted(subset["stop_distance_fraction"].unique())
        # Conservative discretisation: target no easier than requested; stop no
        # farther away than requested.
        target_grid = next((x for x in targets if x >= target_distance - 1e-12), None)
        stop_grid = next((x for x in reversed(stops) if x <= stop_distance + 1e-12), None)
        if target_grid is None or stop_grid is None:
            return None, "REJECT_BARRIER_GRID_UNAVAILABLE", (
                f"target={target_distance:.6f}, stop={stop_distance:.6f}; "
                f"target_grid=[{min(targets):.2f},{max(targets):.2f}], stop_grid=[{min(stops):.2f},{max(stops):.2f}]"
            )
        cell = subset[
            np.isclose(subset["target_distance_fraction"], target_grid)
            & np.isclose(subset["stop_distance_fraction"], stop_grid)
        ]
        if fallback_match_count is None and len(cell) != 1:
            return None, "REJECT_BARRIER_LOOKUP", f"matched_rows={len(cell)}"
        if fallback_match_count is None:
            result = cell.iloc[0].copy()
        else:
            weights = pd.to_numeric(cell["n_effective"], errors="coerce").fillna(0.0)
            total_weight = float(weights.sum())
            if total_weight < self.FALLBACK_MIN_EFFECTIVE_OBSERVATIONS:
                return None, "REJECT_BARRIER_STATE_SPARSE", (
                    f"fallback_n_effective={total_weight:.1f}; "
                    f"minimum={self.FALLBACK_MIN_EFFECTIVE_OBSERVATIONS:.0f}"
                )
            result = cell.iloc[0].copy()
            weighted_fields = (
                "p_target_first", "p_stop_first", "p_timeout",
                "target_exit_session_mean", "stop_exit_session_mean_conservative",
                "timeout_exit_session",
            )
            for field in weighted_fields:
                values = pd.to_numeric(cell[field], errors="coerce")
                valid = values.notna() & (weights > 0)
                result[field] = (
                    float(np.average(values[valid], weights=weights[valid]))
                    if valid.any() else math.nan
                )
            probability_sum = sum(float(result[field]) for field in (
                "p_target_first", "p_stop_first", "p_timeout"
            ))
            if not math.isfinite(probability_sum) or probability_sum <= 0:
                return None, "REJECT_BARRIER_LOOKUP", "fallback probabilities invalid"
            for field in ("p_target_first", "p_stop_first", "p_timeout"):
                result[field] = float(result[field]) / probability_sum
            result["n_effective"] = total_weight
            result["state_key"] = requested_state
        result = self._normalise_exit_sessions(result, horizon_sessions)
        source_keys = sorted(cell["state_key"].astype(str).unique().tolist())
        if fallback_match_count is None:
            result["state_match_type"] = "EXACT"
            result["state_similarity"] = 1.0
            result["state_fallback_penalty_return"] = 0.0
        else:
            result["state_match_type"] = f"FALLBACK_{fallback_match_count}_OF_7"
            result["state_similarity"] = fallback_match_count / 7.0
            result["state_fallback_penalty_return"] = self.FALLBACK_PENALTY_RETURN
        result["state_source_count"] = len(source_keys)
        result["state_source_keys_json"] = json.dumps(source_keys)
        return result, "ACCEPTED", ""

    def _normalise_exit_sessions(self, result: pd.Series, horizon_sessions: int) -> pd.Series:
        result = result.copy()
        defaults: list[str] = []
        fallback_values = {
            # Conservative option economics: receive a target benefit late and
            # realise a stop loss early. Timeout always occurs at the hold limit.
            "target_exit_session_mean": float(horizon_sessions),
            "stop_exit_session_mean_conservative": 1.0,
            "timeout_exit_session": float(horizon_sessions),
        }
        for field, fallback in fallback_values.items():
            value = pd.to_numeric(pd.Series([result.get(field)]), errors="coerce").iloc[0]
            if pd.isna(value) or not math.isfinite(float(value)):
                value = fallback
                defaults.append(field)
            result[field] = min(max(float(value), 1.0), float(horizon_sessions))
        result["exit_session_defaulted_fields_json"] = json.dumps(defaults, sort_keys=True)
        result["exit_session_default_penalty_return"] = (
            self.EXIT_SESSION_DEFAULT_UNCERTAINTY_RETURN if defaults else 0.0
        )
        return result

def american_option_price(
    spot: float,
    strike: float,
    years: float,
    rate: float,
    dividend_yield: float,
    volatility: float,
    direction: str,
    *,
    steps: int = 100,
) -> float:
    """Cox-Ross-Rubinstein American option value for a CALL or PUT."""

    is_call = direction.upper() == "CALL"
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if years <= 0 or volatility <= 0 or steps <= 0:
        return intrinsic
    dt = years / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1.0 / up
    denominator = up - down
    if denominator <= 0:
        return intrinsic
    probability = (math.exp((rate - dividend_yield) * dt) - down) / denominator
    probability = min(max(probability, 0.0), 1.0)
    discount = math.exp(-rate * dt)
    indices = np.arange(steps + 1)
    terminal_spots = spot * (up ** (steps - indices)) * (down ** indices)
    values = np.maximum(terminal_spots - strike, 0.0) if is_call else np.maximum(strike - terminal_spots, 0.0)
    for level in range(steps - 1, -1, -1):
        values = discount * (probability * values[:-1] + (1.0 - probability) * values[1:])
        level_indices = np.arange(level + 1)
        level_spots = spot * (up ** (level - level_indices)) * (down ** level_indices)
        exercise = np.maximum(level_spots - strike, 0.0) if is_call else np.maximum(strike - level_spots, 0.0)
        values = np.maximum(values, exercise)
    return float(values[0])


def _anchored_option_mid(
    canonical: Mapping[str, Any],
    *,
    exit_spot: float,
    exit_sessions: float,
    current_volatility: float,
    exit_volatility: float,
    rate: float,
    dividend_yield: float,
    policy: EV3Policy,
) -> float:
    dte = int(canonical["dte_calendar"])
    elapsed_calendar = max(0, math.ceil(float(exit_sessions) * 7.0 / 5.0))
    remaining_days = max(dte - elapsed_calendar, 0)
    steps_now = min(policy.crr_max_steps, max(policy.crr_min_steps, dte))
    steps_exit = min(policy.crr_max_steps, max(policy.crr_min_steps, remaining_days or 1))
    current_model = american_option_price(
        canonical["entry_spot"], canonical["strike"], dte / 365.0, rate,
        dividend_yield, current_volatility, canonical["canonical_direction"], steps=steps_now,
    )
    exit_model = american_option_price(
        exit_spot, canonical["strike"], remaining_days / 365.0, rate,
        dividend_yield, exit_volatility, canonical["canonical_direction"], steps=steps_exit,
    )
    mid = float(canonical["mid"])
    anchored_mid = max(mid + exit_model - current_model, 0.0)
    intrinsic = max(exit_spot - canonical["strike"], 0.0) if canonical["canonical_direction"] == "CALL" else max(canonical["strike"] - exit_spot, 0.0)
    anchored_mid = max(anchored_mid, intrinsic)
    no_arbitrage_cap = exit_spot if canonical["canonical_direction"] == "CALL" else canonical["strike"]
    anchored_mid = min(anchored_mid, float(no_arbitrage_cap))
    return anchored_mid


def _exit_return(
    canonical: Mapping[str, Any],
    *,
    exit_spot: float,
    exit_sessions: float,
    current_volatility: float,
    exit_volatility: float,
    rate: float,
    dividend_yield: float,
    policy: EV3Policy,
) -> tuple[float, float]:
    anchored_mid = _anchored_option_mid(
        canonical,
        exit_spot=exit_spot,
        exit_sessions=exit_sessions,
        current_volatility=current_volatility,
        exit_volatility=exit_volatility,
        rate=rate,
        dividend_yield=dividend_yield,
        policy=policy,
    )
    mid = float(canonical["mid"])
    spread = float(canonical["spread_fraction_mid"])
    exit_credit = max(anchored_mid * (1.0 - spread / 2.0 - policy.slippage_fraction_of_mid_each_side), 0.0)
    entry_debit = float(canonical["ask"]) + mid * policy.slippage_fraction_of_mid_each_side
    return (exit_credit - entry_debit) / entry_debit, anchored_mid


def _vertical_leg_row(row: Mapping[str, Any], leg: Mapping[str, Any]) -> dict[str, Any]:
    mapped = dict(row)
    aliases = {
        "symbol": "contract_symbol", "strike": "contract_strike", "expiry": "contract_expiry",
        "dte": "contract_dte", "bid": "contract_bid", "ask": "contract_ask",
        "delta": "contract_delta", "gamma": "contract_gamma", "theta": "contract_theta",
        "vega": "contract_vega", "iv": "contract_iv", "oi": "contract_oi",
        "volume": "contract_volume", "contract_multiplier": "contract_multiplier",
    }
    for source_name, target_name in aliases.items():
        if source_name in leg:
            mapped[target_name] = leg[source_name]
    if "quote_timestamp_utc" in leg:
        mapped["quote_timestamp_utc"] = leg["quote_timestamp_utc"]
        mapped["contract_quote_timestamp_utc"] = leg["quote_timestamp_utc"]
    mapped["contract_structure"] = "LONG_SINGLE"
    return mapped


def evaluate_vertical_debit(
    row: Mapping[str, Any],
    barrier_cache: EV3BarrierCache,
    *,
    policy: EV3Policy,
    phase: str,
    now_utc: Any,
    max_quote_age_seconds: int | None,
) -> dict[str, Any]:
    structure = str(row.get("contract_structure") or row.get("structure") or "").upper()
    expected_structure = {"CALL": "BULL_CALL_DEBIT", "PUT": "BEAR_PUT_DEBIT"}
    long_leg = row.get("long_leg")
    short_leg = row.get("short_leg")
    if not isinstance(long_leg, Mapping) or not isinstance(short_leg, Mapping):
        return _rejection("REJECT_VERTICAL_LEGS", "long_leg and short_leg records are required")

    validations: list[EV3ValidationResult] = []
    for leg_name, leg in (("LONG", long_leg), ("SHORT", short_leg)):
        validation = validate_ev3_input(
            _vertical_leg_row(row, leg), phase=phase, require_contract=True,
            now_utc=now_utc, max_quote_age_seconds=max_quote_age_seconds,
            minimum_open_interest=policy.minimum_open_interest,
            minimum_volume=policy.minimum_volume,
        )
        if not validation.accepted:
            return _rejection(
                f"REJECT_VERTICAL_{leg_name}_LEG",
                f"{validation.reason_code}: {validation.detail}",
            )
        validations.append(validation)
    long_c, short_c = validations[0].canonical, validations[1].canonical
    direction = long_c["canonical_direction"]
    if structure != expected_structure.get(direction):
        return _rejection("REJECT_VERTICAL_STRUCTURE", f"direction={direction}, structure={structure}")
    if long_c["expiration"] != short_c["expiration"] or long_c["dte_calendar"] != short_c["dte_calendar"]:
        return _rejection("REJECT_VERTICAL_EXPIRY", "legs must have identical expiry and DTE")
    if long_c["contract_multiplier"] != short_c["contract_multiplier"]:
        return _rejection("REJECT_VERTICAL_MULTIPLIER", "leg multipliers do not match")
    if max(long_c["spread_fraction_mid"], short_c["spread_fraction_mid"]) > policy.maximum_spread_fraction_mid:
        return _rejection("REJECT_LIQUIDITY_SPREAD", "one or both vertical legs exceed spread policy")

    long_strike = float(long_c["strike"])
    short_strike = float(short_c["strike"])
    geometry_valid = long_strike < short_strike if direction == "CALL" else long_strike > short_strike
    if not geometry_valid:
        return _rejection(
            "REJECT_VERTICAL_GEOMETRY",
            f"direction={direction}, long_strike={long_strike}, short_strike={short_strike}",
        )
    width = abs(long_strike - short_strike)
    long_entry = float(long_c["ask"]) + float(long_c["mid"]) * policy.slippage_fraction_of_mid_each_side
    short_credit = max(
        float(short_c["bid"]) - float(short_c["mid"]) * policy.slippage_fraction_of_mid_each_side,
        0.0,
    )
    entry_debit = long_entry - short_credit
    if not 0 < entry_debit < width:
        return _rejection(
            "REJECT_VERTICAL_DEBIT",
            f"entry_debit={entry_debit}, strike_width={width}",
        )

    cell, reason, detail = barrier_cache.lookup(
        long_c["state_key"], direction, int(long_c["planned_hold_sessions"]),
        long_c["target_distance_fraction"], long_c["stop_distance_fraction"],
    )
    if cell is None:
        return _rejection(reason, detail, ev3_contract_symbol=str(row.get("contract_symbol") or row.get("symbol") or ""))

    rate_defaulted = long_c.get("risk_free_rate") is None
    dividend_defaulted = long_c.get("dividend_yield") is None
    rate = policy.default_risk_free_rate if rate_defaulted else float(long_c["risk_free_rate"])
    dividend = policy.default_dividend_yield if dividend_defaulted else float(long_c["dividend_yield"])
    exits = {
        "target": (float(long_c["target_spot"]), float(cell["target_exit_session_mean"])),
        "stop": (float(long_c["invalidation_spot"]), float(cell["stop_exit_session_mean_conservative"])),
        "timeout": (float(long_c["entry_spot"]), float(cell["timeout_exit_session"])),
    }
    returns: dict[str, float] = {}
    spread_mids: dict[str, float] = {}
    leg_mids: dict[str, float] = {}
    for scenario, (spot, sessions) in exits.items():
        for label, stress in (("base", 1.0), ("stress", 1.0 - policy.iv_stress_fraction)):
            long_mid = _anchored_option_mid(
                long_c, exit_spot=spot, exit_sessions=sessions,
                current_volatility=float(long_c["implied_volatility"]),
                exit_volatility=float(long_c["implied_volatility"]) * stress,
                rate=rate, dividend_yield=dividend, policy=policy,
            )
            short_mid = _anchored_option_mid(
                short_c, exit_spot=spot, exit_sessions=sessions,
                current_volatility=float(short_c["implied_volatility"]),
                exit_volatility=float(short_c["implied_volatility"]) * stress,
                rate=rate, dividend_yield=dividend, policy=policy,
            )
            long_exit_credit = max(
                long_mid * (1.0 - float(long_c["spread_fraction_mid"]) / 2.0 - policy.slippage_fraction_of_mid_each_side),
                0.0,
            )
            short_exit_debit = short_mid * (
                1.0 + float(short_c["spread_fraction_mid"]) / 2.0 + policy.slippage_fraction_of_mid_each_side
            )
            spread_mid = min(max(long_mid - short_mid, 0.0), width)
            exit_credit = min(max(long_exit_credit - short_exit_debit, 0.0), width)
            returns[f"{scenario}_{label}"] = (exit_credit - entry_debit) / entry_debit
            spread_mids[f"{scenario}_{label}"] = spread_mid
            leg_mids[f"long_{scenario}_{label}"] = long_mid
            leg_mids[f"short_{scenario}_{label}"] = short_mid

    probabilities = np.array([cell["p_target_first"], cell["p_stop_first"], cell["p_timeout"]], dtype=float)
    base_outcomes = np.array([returns["target_base"], returns["stop_base"], returns["timeout_base"]])
    stress_outcomes = np.array([returns["target_stress"], returns["stop_stress"], returns["timeout_stress"]])
    ev_base = float(np.dot(probabilities, base_outcomes))
    ev_stress = float(np.dot(probabilities, stress_outcomes))
    ev_conservative = min(ev_base, ev_stress)
    chosen = base_outcomes if ev_base <= ev_stress else stress_outcomes
    n_effective = max(float(cell["n_effective"]), 1.0)
    variance = float(np.dot(probabilities, (chosen - ev_conservative) ** 2))
    probability_uncertainty = policy.one_sided_z * math.sqrt(max(variance, 0.0) / n_effective)
    max_spread = max(float(long_c["spread_fraction_mid"]), float(short_c["spread_fraction_mid"]))
    liquidity_uncertainty = min(max_spread * 0.10, 0.10)
    max_quote_age = max(float(long_c["quote_age_seconds"]), float(short_c["quote_age_seconds"]))
    freshness_limit = min(float(long_c["quote_freshness_limit_seconds"]), float(short_c["quote_freshness_limit_seconds"]))
    quote_uncertainty = min(max(max_quote_age / max(freshness_limit, 1.0), 0.0) * 0.01, 0.01)
    default_uncertainty = policy.default_input_uncertainty_return * int(rate_defaulted or dividend_defaulted)
    state_fallback_uncertainty = float(cell.get("state_fallback_penalty_return", 0.0))
    exit_session_default_uncertainty = float(cell.get("exit_session_default_penalty_return", 0.0))
    uncertainty_total = (
        probability_uncertainty + policy.model_uncertainty_return + liquidity_uncertainty
        + quote_uncertainty + default_uncertainty + state_fallback_uncertainty
        + exit_session_default_uncertainty
    )
    lower_bound = ev_conservative - uncertainty_total
    absolute_state = "NEGATIVE_EV" if ev_conservative <= 0 else (
        "INDETERMINATE" if lower_bound <= policy.capital_hurdle_return else "POSITIVE_UNVALIDATED"
    )
    multiplier = float(long_c["contract_multiplier"])
    composite_symbol = str(row.get("contract_symbol") or row.get("symbol") or f"{structure}:{long_c['contract_symbol']}/{short_c['contract_symbol']}")
    output: dict[str, Any] = {
        "ev3_engine_version": EV3_ENGINE_VERSION,
        "ev3_policy_version": policy.policy_version,
        "ev3_status": EV3_EVALUATED_STATUS,
        "ev3_reason_code": "PRODUCTION_EVIDENCE_ONLY",
        "ev3_reason_detail": "Production evidence; capital authority is not calibrated",
        "ev3_absolute_state": absolute_state,
        "ev3_capital_eligible": False,
        "ev3_shadow_only": False,
        "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
        "ev3_contract_symbol": composite_symbol,
        "ev3_structure": structure,
        "ev3_direction": direction,
        "ev3_state_key": long_c["state_key"],
        "ev3_horizon_sessions": int(long_c["planned_hold_sessions"]),
        "ev3_expiry": long_c["expiration"],
        "ev3_strike": long_strike,
        "ev3_long_leg_symbol": long_c["contract_symbol"],
        "ev3_short_leg_symbol": short_c["contract_symbol"],
        "ev3_long_strike": long_strike,
        "ev3_short_strike": short_strike,
        "ev3_strike_width": width,
        "ev3_candidate_generation_rank": long_c.get("candidate_generation_rank"),
        "ev3_candidate_policy_version": str(row.get("ev3_candidate_policy_version") or row.get("candidate_policy_version") or ""),
        "ev3_barrier_target_grid": float(cell["target_distance_fraction"]),
        "ev3_barrier_stop_grid": float(cell["stop_distance_fraction"]),
        "ev3_barrier_calculation_version": cell["calculation_version"],
        "ev3_state_match_type": str(cell.get("state_match_type", "EXACT")),
        "ev3_state_similarity": float(cell.get("state_similarity", 1.0)),
        "ev3_state_source_count": int(cell.get("state_source_count", 1)),
        "ev3_state_source_keys_json": str(cell.get("state_source_keys_json", "[]")),
        "ev3_exit_session_defaulted_fields_json": str(cell.get("exit_session_defaulted_fields_json", "[]")),
        "ev3_p_target": float(probabilities[0]),
        "ev3_p_stop": float(probabilities[1]),
        "ev3_p_timeout": float(probabilities[2]),
        "ev3_n_effective": n_effective,
        "ev3_ev_base_return": ev_base,
        "ev3_ev_stress_return": ev_stress,
        "ev3_ev_conservative_return": ev_conservative,
        "ev3_probability_uncertainty_return": probability_uncertainty,
        "ev3_model_uncertainty_return": policy.model_uncertainty_return,
        "ev3_liquidity_uncertainty_return": liquidity_uncertainty,
        "ev3_quote_uncertainty_return": quote_uncertainty,
        "ev3_default_input_uncertainty_return": default_uncertainty,
        "ev3_state_fallback_uncertainty_return": state_fallback_uncertainty,
        "ev3_exit_session_default_uncertainty_return": exit_session_default_uncertainty,
        "ev3_uncertainty_total_return": uncertainty_total,
        "ev3_ev_lower_bound_return": lower_bound,
        "ev3_capital_hurdle_return": policy.capital_hurdle_return,
        "ev3_entry_debit_per_share": entry_debit,
        "ev3_contract_multiplier": multiplier,
        "ev3_risk_unit_premium": entry_debit * multiplier,
        "ev3_max_loss_per_contract": entry_debit * multiplier,
        "ev3_max_profit_per_contract": (width - entry_debit) * multiplier,
        "ev3_short_assignment_risk_modelled": False,
        "ev3_vertical_shadow_limitation": "SHORT_ASSIGNMENT_AND_EX_DIVIDEND_EVENT_RISK_NOT_SEPARATELY_MODELLED",
        "ev3_quote_age_seconds": max_quote_age,
        "ev3_rate_used": rate,
        "ev3_dividend_yield_used": dividend,
        "ev3_rate_defaulted": rate_defaulted,
        "ev3_dividend_yield_defaulted": dividend_defaulted,
    }
    for key, value in returns.items():
        output[f"ev3_return_{key}"] = value
    for key, value in spread_mids.items():
        output[f"ev3_exit_mid_{key}"] = value
    for key, value in leg_mids.items():
        output[f"ev3_exit_mid_{key}"] = value
    return output


def evaluate_contract(
    row: Mapping[str, Any],
    barrier_cache: EV3BarrierCache,
    *,
    policy: EV3Policy | None = None,
    phase: str = "EOD",
    now_utc: Any = None,
    max_quote_age_seconds: int | None = None,
) -> dict[str, Any]:
    """Evaluate one long single or vertical debit candidate in shadow mode."""

    policy = policy or EV3Policy()
    raw_direction = str(
        row.get("canonical_direction")
        or row.get("resolved_direction")
        or row.get("options_direction")
        or row.get("direction")
        or ""
    ).strip().upper()
    if raw_direction in {"STRANGLE", "STRADDLE", "NON_DIRECTIONAL"}:
        return not_applicable_result(
            "NOT_APPLICABLE_NON_DIRECTIONAL",
            f"direction={raw_direction}; directional EV3 supports CALL/PUT only",
        )
    structure = str(row.get("contract_structure") or row.get("structure") or "LONG_SINGLE").strip().upper()
    if structure in {"BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"}:
        return evaluate_vertical_debit(
            row, barrier_cache, policy=policy, phase=phase, now_utc=now_utc,
            max_quote_age_seconds=max_quote_age_seconds,
        )
    validation: EV3ValidationResult = validate_ev3_input(
        row, phase=phase, require_contract=True, now_utc=now_utc,
        max_quote_age_seconds=max_quote_age_seconds,
        minimum_open_interest=policy.minimum_open_interest,
        minimum_volume=policy.minimum_volume,
    )
    if not validation.accepted:
        if validation.reason_code.startswith("NOT_APPLICABLE_"):
            return not_applicable_result(validation.reason_code, validation.detail)
        return _rejection(validation.reason_code, validation.detail)
    c = validation.canonical
    if float(c["spread_fraction_mid"]) > policy.maximum_spread_fraction_mid:
        return _rejection(
            "REJECT_LIQUIDITY_SPREAD",
            f"spread_fraction_mid={c['spread_fraction_mid']}; "
            f"maximum={policy.maximum_spread_fraction_mid}",
            ev3_contract_symbol=c.get("contract_symbol"),
        )
    cell, reason, detail = barrier_cache.lookup(
        c["state_key"], c["canonical_direction"], int(c["planned_hold_sessions"]),
        c["target_distance_fraction"], c["stop_distance_fraction"],
    )
    if cell is None:
        return _rejection(reason, detail, ev3_contract_symbol=c.get("contract_symbol"))

    rate_defaulted = c.get("risk_free_rate") is None
    dividend_defaulted = c.get("dividend_yield") is None
    rate = policy.default_risk_free_rate if rate_defaulted else float(c["risk_free_rate"])
    dividend = policy.default_dividend_yield if dividend_defaulted else float(c["dividend_yield"])
    base_iv = float(c["implied_volatility"])
    stress_iv = base_iv * (1.0 - policy.iv_stress_fraction)
    exits = {
        "target": (float(c["target_spot"]), float(cell["target_exit_session_mean"])),
        "stop": (float(c["invalidation_spot"]), float(cell["stop_exit_session_mean_conservative"])),
        "timeout": (float(c["entry_spot"]), float(cell["timeout_exit_session"])),
    }
    returns: dict[str, float] = {}
    anchored: dict[str, float] = {}
    for scenario, (spot, sessions) in exits.items():
        for label, vol in (("base", base_iv), ("stress", stress_iv)):
            value, exit_mid = _exit_return(
                c, exit_spot=spot, exit_sessions=sessions,
                current_volatility=base_iv, exit_volatility=vol,
                rate=rate, dividend_yield=dividend, policy=policy,
            )
            returns[f"{scenario}_{label}"] = value
            anchored[f"{scenario}_{label}"] = exit_mid

    probabilities = np.array([cell["p_target_first"], cell["p_stop_first"], cell["p_timeout"]], dtype=float)
    base_outcomes = np.array([returns["target_base"], returns["stop_base"], returns["timeout_base"]])
    stress_outcomes = np.array([returns["target_stress"], returns["stop_stress"], returns["timeout_stress"]])
    ev_base = float(np.dot(probabilities, base_outcomes))
    ev_stress = float(np.dot(probabilities, stress_outcomes))
    ev_conservative = min(ev_base, ev_stress)
    chosen_outcomes = base_outcomes if ev_base <= ev_stress else stress_outcomes
    n_effective = max(float(cell["n_effective"]), 1.0)
    outcome_variance = float(np.dot(probabilities, (chosen_outcomes - ev_conservative) ** 2))
    probability_uncertainty = policy.one_sided_z * math.sqrt(max(outcome_variance, 0.0) / n_effective)
    liquidity_uncertainty = min(float(c["spread_fraction_mid"]) * 0.10, 0.10)
    freshness_fraction = float(c["quote_age_seconds"]) / max(float(c["quote_freshness_limit_seconds"]), 1.0)
    quote_uncertainty = min(max(freshness_fraction, 0.0) * 0.01, 0.01)
    default_uncertainty = policy.default_input_uncertainty_return * int(rate_defaulted or dividend_defaulted)
    state_fallback_uncertainty = float(cell.get("state_fallback_penalty_return", 0.0))
    exit_session_default_uncertainty = float(cell.get("exit_session_default_penalty_return", 0.0))
    uncertainty_total = (
        probability_uncertainty + policy.model_uncertainty_return + liquidity_uncertainty
        + quote_uncertainty + default_uncertainty + state_fallback_uncertainty
        + exit_session_default_uncertainty
    )
    lower_bound = ev_conservative - uncertainty_total
    if ev_conservative <= 0:
        absolute_state = "NEGATIVE_EV"
    elif lower_bound <= policy.capital_hurdle_return:
        absolute_state = "INDETERMINATE"
    else:
        absolute_state = "POSITIVE_UNVALIDATED"

    entry_debit_per_share = float(c["ask"]) + float(c["mid"]) * policy.slippage_fraction_of_mid_each_side
    output: dict[str, Any] = {
        "ev3_engine_version": EV3_ENGINE_VERSION,
        "ev3_policy_version": policy.policy_version,
        "ev3_status": EV3_EVALUATED_STATUS,
        "ev3_reason_code": "PRODUCTION_EVIDENCE_ONLY",
        "ev3_reason_detail": "Production evidence; capital authority is not calibrated",
        "ev3_absolute_state": absolute_state,
        "ev3_capital_eligible": False,
        "ev3_shadow_only": False,
        "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
        "ev3_contract_symbol": c["contract_symbol"],
        "ev3_structure": c["contract_structure"],
        "ev3_strike": float(c["strike"]),
        "ev3_expiry": c["expiration"],
        "ev3_candidate_generation_rank": c.get("candidate_generation_rank"),
        "ev3_candidate_policy_version": c.get("candidate_policy_version", ""),
        "ev3_direction": c["canonical_direction"],
        "ev3_state_key": c["state_key"],
        "ev3_horizon_sessions": int(c["planned_hold_sessions"]),
        "ev3_barrier_target_grid": float(cell["target_distance_fraction"]),
        "ev3_barrier_stop_grid": float(cell["stop_distance_fraction"]),
        "ev3_barrier_calculation_version": cell["calculation_version"],
        "ev3_state_match_type": str(cell.get("state_match_type", "EXACT")),
        "ev3_state_similarity": float(cell.get("state_similarity", 1.0)),
        "ev3_state_source_count": int(cell.get("state_source_count", 1)),
        "ev3_state_source_keys_json": str(cell.get("state_source_keys_json", "[]")),
        "ev3_exit_session_defaulted_fields_json": str(cell.get("exit_session_defaulted_fields_json", "[]")),
        "ev3_p_target": float(probabilities[0]),
        "ev3_p_stop": float(probabilities[1]),
        "ev3_p_timeout": float(probabilities[2]),
        "ev3_n_effective": n_effective,
        "ev3_return_target_base": returns["target_base"],
        "ev3_return_stop_base": returns["stop_base"],
        "ev3_return_timeout_base": returns["timeout_base"],
        "ev3_return_target_stress": returns["target_stress"],
        "ev3_return_stop_stress": returns["stop_stress"],
        "ev3_return_timeout_stress": returns["timeout_stress"],
        "ev3_ev_base_return": ev_base,
        "ev3_ev_stress_return": ev_stress,
        "ev3_ev_conservative_return": ev_conservative,
        "ev3_probability_uncertainty_return": probability_uncertainty,
        "ev3_model_uncertainty_return": policy.model_uncertainty_return,
        "ev3_liquidity_uncertainty_return": liquidity_uncertainty,
        "ev3_quote_uncertainty_return": quote_uncertainty,
        "ev3_default_input_uncertainty_return": default_uncertainty,
        "ev3_state_fallback_uncertainty_return": state_fallback_uncertainty,
        "ev3_exit_session_default_uncertainty_return": exit_session_default_uncertainty,
        "ev3_uncertainty_total_return": uncertainty_total,
        "ev3_ev_lower_bound_return": lower_bound,
        "ev3_capital_hurdle_return": policy.capital_hurdle_return,
        "ev3_rate_used": rate,
        "ev3_dividend_yield_used": dividend,
        "ev3_rate_defaulted": rate_defaulted,
        "ev3_dividend_yield_defaulted": dividend_defaulted,
        "ev3_entry_debit_per_share": entry_debit_per_share,
        "ev3_contract_multiplier": float(c["contract_multiplier"]),
        "ev3_risk_unit_premium": entry_debit_per_share * float(c["contract_multiplier"]),
        "ev3_quote_age_seconds": float(c["quote_age_seconds"]),
    }
    for key, value in anchored.items():
        output[f"ev3_exit_mid_{key}"] = value
    return output


def select_contract(
    candidates: Sequence[Mapping[str, Any]],
    barrier_cache: EV3BarrierCache,
    *,
    policy: EV3Policy | None = None,
    phase: str = "EOD",
    now_utc: Any = None,
    max_quote_age_seconds: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate a bounded candidate set and select the robust lower-bound leader."""

    policy = policy or EV3Policy()
    bounded = list(candidates)[: policy.max_contracts_per_thesis]
    evaluations = [
        evaluate_contract(x, barrier_cache, policy=policy, phase=phase, now_utc=now_utc,
                          max_quote_age_seconds=max_quote_age_seconds)
        for x in bounded
    ]
    valid = [x for x in evaluations if x.get("ev3_status") == EV3_EVALUATED_STATUS]
    if not valid:
        not_applicable = [x for x in evaluations if x.get("ev3_status") == "NOT_APPLICABLE"]
        if not_applicable and len(not_applicable) == len(evaluations):
            selected = dict(not_applicable[0])
            selected["ev3_selection_reason"] = "NOT_APPLICABLE_TO_ALL_CANDIDATES"
            selected["ev3_candidates_received"] = len(candidates)
            selected["ev3_candidates_evaluated"] = len(bounded)
            selected["ev3_candidates_valid"] = 0
            return selected, evaluations
        rejection_counts: dict[str, int] = {}
        for evaluation in evaluations:
            reason = str(evaluation.get("ev3_reason_code") or "UNKNOWN")
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        reason_summary = ",".join(
            f"{reason}:{count}" for reason, count in sorted(rejection_counts.items())
        )
        detail = f"candidates={len(bounded)}"
        if reason_summary:
            detail = f"{detail}; child_rejections={reason_summary}"
        return _rejection(
            "REJECT_NO_EVALUABLE_CONTRACT",
            detail,
            ev3_child_rejection_counts_json=json.dumps(rejection_counts, sort_keys=True),
        ), evaluations
    ordered = sorted(valid, key=lambda x: float(x["ev3_ev_lower_bound_return"]), reverse=True)
    best_value = float(ordered[0]["ev3_ev_lower_bound_return"])
    runner_up_value = float(ordered[1]["ev3_ev_lower_bound_return"]) if len(ordered) > 1 else None
    argmax_margin = best_value - runner_up_value if runner_up_value is not None else None
    tied = [x for x in valid if best_value - float(x["ev3_ev_lower_bound_return"]) <= policy.selection_tie_tolerance]
    tied.sort(key=lambda x: (float(x["ev3_quote_age_seconds"]), float(x["ev3_liquidity_uncertainty_return"]), x["ev3_contract_symbol"]))
    selected = dict(tied[0])
    selected["ev3_selection_reason"] = "MAX_LOWER_BOUND" if len(tied) == 1 else "LOWER_BOUND_TIE_FRESHER_TIGHTER"
    selected["ev3_candidates_received"] = len(candidates)
    selected["ev3_candidates_evaluated"] = len(bounded)
    selected["ev3_candidates_valid"] = len(valid)
    selected["ev3_argmax_margin"] = argmax_margin
    selected["ev3_runner_up_lower_bound_return"] = runner_up_value
    return selected, evaluations


def policy_as_dict(policy: EV3Policy | None = None) -> dict[str, Any]:
    return asdict(policy or EV3Policy())
