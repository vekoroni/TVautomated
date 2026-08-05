"""
VANGUARD Layer 3 - Multi-Scenario Builder
AMENDED MERGED VERSION (2026-04-12)

Purpose
-------
This version restores the original public interface expected by Vanguard:
    - class MultiScenarioBuilder
    - method build_scenarios(...)

It also preserves the newer probability-fix logic introduced in the
simplified replacement file:
    - composite score clamped to [0, 100]
    - drift probability floor
    - exact normalisation to sum to 1.0
    - rounded outputs for readability

Why this merge exists
---------------------
The prior replacement kept only a helper function and removed the
MultiScenarioBuilder class entirely. That broke imports expecting:

    from vanguard.layer3_execution.scenario_builder import MultiScenarioBuilder

This file restores backward compatibility while retaining the safer
probability maths.
"""

from __future__ import annotations

from typing import Dict

from ..schemas.trade_schema import TradeScenario
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from ..config import SCENARIO_PROBABILITIES, POSITION_SIZING_CONFIG


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_scenario_probabilities(row: dict) -> dict:
    """
    Lightweight probability helper retained from the newer replacement file.

    Args:
        row: dict containing 'composite' key, default 50

    Returns:
        dict with prob_breakout, prob_rejection, prob_drift (sum = 1.0)
    """
    base = float(row.get("composite", 50) or 50)
    base = _clamp(base, 0.0, 100.0)

    prob_breakout = min(0.65, 0.25 + base / 200.0)
    prob_rejection = max(0.10, 0.45 - base / 250.0)
    prob_drift = max(0.05, 1.0 - prob_breakout - prob_rejection)

    total = prob_breakout + prob_rejection + prob_drift
    if total > 0:
        prob_breakout /= total
        prob_rejection /= total
        prob_drift /= total

    return {
        "prob_breakout": round(prob_breakout, 4),
        "prob_rejection": round(prob_rejection, 4),
        "prob_drift": round(prob_drift, 4),
    }


class MultiScenarioBuilder:
    """
    Restored class-based interface expected by Vanguard imports.

    Provides:
    - build_scenarios(...)  -> original scenario-construction workflow
    - build(row)            -> compatibility helper for lightweight callers
    - compute_probs(row)    -> explicit access to merged probability helper
    """

    def __init__(self):
        self.prob_config = SCENARIO_PROBABILITIES
        self.sizing_config = POSITION_SIZING_CONFIG

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------
    def build(self, row: dict) -> dict:
        """
        Compatibility wrapper for any callers expecting a simple builder API.
        """
        return compute_scenario_probabilities(row)

    def compute_probs(self, row: dict) -> dict:
        """
        Explicit wrapper around the merged probability helper.
        """
        return compute_scenario_probabilities(row)

    # ------------------------------------------------------------------
    # Main scenario-construction interface
    # ------------------------------------------------------------------
    def build_scenarios(
        self,
        ticker: str,
        current_price: float,
        direction: str,
        state: StateVector,
        outcomes: ActuarialOutcomes,
        auction: AuctionVerdict,
    ) -> Dict[str, TradeScenario]:
        """
        Build all three scenarios.

        Returns:
            Dict with keys: 'aggressive', 'moderate', 'conservative'
        """
        return {
            "aggressive": self._build_aggressive_scenario(
                ticker, current_price, direction, state, outcomes, auction
            ),
            "moderate": self._build_moderate_scenario(
                ticker, current_price, direction, state, outcomes, auction
            ),
            "conservative": self._build_conservative_scenario(
                ticker, current_price, direction, state, outcomes, auction
            ),
        }

    @staticmethod
    def _hold_days(outcomes: ActuarialOutcomes, factor: float = 1.0, min_days: int = 1) -> int:
        try:
            base = float(getattr(outcomes, "recommended_hold_days", 20) or 20)
        except Exception:
            base = 20.0
        return max(min_days, int(round(base * factor)))

    @staticmethod
    def _horizon_metrics(outcomes: ActuarialOutcomes, hold_days: int) -> tuple[float, float, float]:
        try:
            win_rate = float(outcomes.win_rate_for_hold(hold_days))
        except Exception:
            win_rate = float(getattr(outcomes, "win_rate", 0.0) or 0.0)
        try:
            median_gain = float(outcomes.median_gain_for_hold(hold_days))
        except Exception:
            median_gain = float(getattr(outcomes, "median_gain_if_up", 0.0) or 0.0)
        try:
            median_loss = float(outcomes.median_loss_for_hold(hold_days))
        except Exception:
            median_loss = float(getattr(outcomes, "median_loss_if_down", 0.0) or 0.0)
        return win_rate, median_gain, median_loss

    def _build_aggressive_scenario(
        self,
        ticker: str,
        current_price: float,
        direction: str,
        state: StateVector,
        outcomes: ActuarialOutcomes,
        auction: AuctionVerdict,
    ) -> TradeScenario:
        """
        AGGRESSIVE: Enter immediately at current price
        """

        hold_days = self._hold_days(outcomes)
        horizon_win_rate, horizon_gain, horizon_loss = self._horizon_metrics(outcomes, hold_days)

        entry_optimal = current_price
        entry_min = current_price * 0.995
        entry_max = current_price * 1.005

        if direction == "CALL":
            stop_price = min(
                auction.profile.value_area_low * 0.99,
                auction.profile.poc * 0.985,
            )
        else:
            stop_price = auction.profile.value_area_high * 1.01

        max_loss_pct = abs(current_price - stop_price) / current_price if current_price else 0.0

        target_1 = current_price * (1 + horizon_gain)
        target_2 = current_price * (1 + horizon_gain * 1.5)

        probability = max(self.prob_config["aggressive_base_probability"], horizon_win_rate)
        if auction.acceptance.score >= 50:
            probability += 0.05
        if auction.control.confidence > 0.60:
            probability += 0.05
        if state.value_migration_direction != "SIDEWAYS":
            probability += 0.03

        win_probability = min(probability, self.prob_config["max_probability"])

        expected_gain = horizon_gain
        expected_loss = horizon_loss
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss else 0.0

        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = win_probability - (1 - win_probability) / risk_reward_ratio
            kelly = _clamp(kelly, 0.0, 0.25)
        else:
            kelly = 0.0

        recommended_size = kelly * self.sizing_config["aggressive_sizing_factor"]
        recommended_size = min(recommended_size, self.sizing_config["max_position_size"])
        max_size = min(kelly * 1.2, self.sizing_config["max_position_size"])

        options_rec = self._design_options_strategy(
            direction, current_price, state, outcomes, "AGGRESSIVE"
        )

        confidence = auction.confidence * 0.7
        right_side_score = 50.0
        if auction.acceptance.score >= 50:
            right_side_score += 15
        if auction.control.confidence > 0.65:
            right_side_score += 15
        if win_probability > 0.50:
            right_side_score += 10

        return TradeScenario(
            scenario_type="AGGRESSIVE",
            scenario_label="Enter NOW (Pre-confirmation)",

            entry_min=entry_min,
            entry_max=entry_max,
            entry_optimal=entry_optimal,
            entry_type="IMMEDIATE",
            entry_trigger=None,

            stop_price=stop_price,
            stop_rationale=f"Below value area/POC at ${stop_price:.2f}",
            max_loss_pct=max_loss_pct,

            target_1=target_1,
            target_1_prob=win_probability * 0.8,
            target_2=target_2,
            target_2_prob=win_probability * 0.5,

            win_probability=win_probability,
            drawdown_probability=outcomes.prob_down_5pct_before_up_10pct,

            expected_gain_if_win=expected_gain,
            expected_loss_if_loss=expected_loss,
            expected_value=expected_value,
            risk_reward_ratio=risk_reward_ratio,

            kelly_fraction=kelly,
            recommended_size_pct=recommended_size,
            max_size_pct=max_size,
            sizing_rationale=f"Aggressive sizing: {recommended_size:.1%} of capital (Kelly: {kelly:.1%} × 0.7)",

            optimal_hold_days=hold_days,
            max_hold_days=hold_days,
            time_stop_date="",

            options_recommendation=options_rec,

            status="AVAILABLE_NOW",
            confidence=confidence,
            right_side_score=right_side_score,
        )

    def _build_moderate_scenario(
        self,
        ticker: str,
        current_price: float,
        direction: str,
        state: StateVector,
        outcomes: ActuarialOutcomes,
        auction: AuctionVerdict,
    ) -> TradeScenario:
        """
        MODERATE: Wait for partial confirmation
        """
        hold_days = self._hold_days(outcomes)
        horizon_win_rate, horizon_gain, horizon_loss = self._horizon_metrics(outcomes, hold_days)

        triggers = []

        if current_price < auction.profile.poc:
            trigger_price = auction.profile.poc
            triggers.append(f"VWAP/POC reclaim at ${trigger_price:.2f}")
        elif auction.acceptance.position_in_profile == "BELOW_VALUE":
            trigger_price = auction.profile.value_area_low
            triggers.append(f"Value Area entry at ${trigger_price:.2f}")
        else:
            trigger_price = current_price * 1.02
            triggers.append(f"Price holds above ${trigger_price:.2f}")

        trigger = triggers[0] if triggers else "Partial confirmation"

        entry_optimal = trigger_price
        entry_min = trigger_price * 0.995
        entry_max = trigger_price * 1.005

        if direction == "CALL":
            stop_price = auction.profile.poc * 0.97
        else:
            stop_price = auction.profile.value_area_high * 1.03

        max_loss_pct = abs(trigger_price - stop_price) / trigger_price if trigger_price else 0.0

        target_1 = trigger_price * (1 + horizon_gain * 0.9)
        target_2 = trigger_price * (1 + horizon_gain * 1.3)

        probability = max(self.prob_config["moderate_base_probability"], horizon_win_rate)
        if auction.control.confidence > 0.65:
            probability += 0.03
        if state.value_migration_direction != "SIDEWAYS":
            probability += 0.03

        win_probability = min(probability, self.prob_config["max_probability"])

        expected_gain = horizon_gain * 0.9
        expected_loss = horizon_loss
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss else 0.0

        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = win_probability - (1 - win_probability) / risk_reward_ratio
            kelly = _clamp(kelly, 0.0, 0.25)
        else:
            kelly = 0.0

        recommended_size = kelly * self.sizing_config["moderate_sizing_factor"]
        recommended_size = min(recommended_size, self.sizing_config["max_position_size"])
        max_size = min(kelly * 1.3, self.sizing_config["max_position_size"])

        options_rec = self._design_options_strategy(
            direction, trigger_price, state, outcomes, "MODERATE"
        )

        confidence = auction.confidence * 0.85
        right_side_score = 65.0
        if auction.control.confidence > 0.70:
            right_side_score += 15
        if win_probability > 0.60:
            right_side_score += 10

        return TradeScenario(
            scenario_type="MODERATE",
            scenario_label="Wait for Confirmation",

            entry_min=entry_min,
            entry_max=entry_max,
            entry_optimal=entry_optimal,
            entry_type="CONDITIONAL",
            entry_trigger=trigger,

            stop_price=stop_price,
            stop_rationale=f"Below confirmation level at ${stop_price:.2f}",
            max_loss_pct=max_loss_pct,

            target_1=target_1,
            target_1_prob=win_probability * 0.85,
            target_2=target_2,
            target_2_prob=win_probability * 0.6,

            win_probability=win_probability,
            drawdown_probability=outcomes.prob_down_5pct_before_up_10pct * 0.7,

            expected_gain_if_win=expected_gain,
            expected_loss_if_loss=expected_loss,
            expected_value=expected_value,
            risk_reward_ratio=risk_reward_ratio,

            kelly_fraction=kelly,
            recommended_size_pct=recommended_size,
            max_size_pct=max_size,
            sizing_rationale=f"Standard sizing: {recommended_size:.1%} of capital (Kelly: {kelly:.1%})",

            optimal_hold_days=hold_days,
            max_hold_days=hold_days,
            time_stop_date="",

            options_recommendation=options_rec,

            status="CONDITIONAL",
            confidence=confidence,
            right_side_score=right_side_score,
        )

    def _build_conservative_scenario(
        self,
        ticker: str,
        current_price: float,
        direction: str,
        state: StateVector,
        outcomes: ActuarialOutcomes,
        auction: AuctionVerdict,
    ) -> TradeScenario:
        """
        CONSERVATIVE: Wait for full confirmation (breakout)
        """
        hold_days = self._hold_days(outcomes)
        horizon_win_rate, horizon_gain, horizon_loss = self._horizon_metrics(outcomes, hold_days)

        va_high = auction.profile.value_area_high if auction.profile.value_area_high > 0 else current_price * 1.05
        va_low = auction.profile.value_area_low if auction.profile.value_area_low > 0 else current_price * 0.95

        trigger_price = va_high * 1.02
        trigger = f"Breakout above ${trigger_price:.2f}"

        entry_optimal = trigger_price
        entry_min = trigger_price * 0.995
        entry_max = trigger_price * 1.01

        if direction == "CALL":
            stop_price = va_high * 0.98
        else:
            stop_price = va_low * 1.02

        if trigger_price == 0:
            trigger_price = current_price

        max_loss_pct = abs(trigger_price - stop_price) / trigger_price if trigger_price else 0.02

        target_1 = trigger_price * (1 + horizon_gain * 0.7)
        target_2 = trigger_price * (1 + horizon_gain * 1.0)

        probability = max(self.prob_config["conservative_base_probability"], horizon_win_rate)
        if auction.control.confidence > 0.70:
            probability += 0.02

        win_probability = min(probability, self.prob_config["max_probability"])

        expected_gain = horizon_gain * 0.7
        expected_loss = horizon_loss * 0.6
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss else 0.0

        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = win_probability - (1 - win_probability) / risk_reward_ratio
            kelly = _clamp(kelly * 0.5, 0.0, 0.25)
        else:
            kelly = 0.0

        recommended_size = kelly * self.sizing_config["conservative_sizing_factor"]
        recommended_size = min(recommended_size, self.sizing_config["max_position_size_high_confidence"])
        max_size = min(kelly * 1.5, self.sizing_config["max_position_size_high_confidence"])

        options_rec = self._design_options_strategy(
            direction, trigger_price, state, outcomes, "CONSERVATIVE"
        )

        confidence = auction.confidence * 0.95
        right_side_score = 75.0
        if win_probability > 0.75:
            right_side_score += 15

        return TradeScenario(
            scenario_type="CONSERVATIVE",
            scenario_label="Wait for Breakout",

            entry_min=entry_min,
            entry_max=entry_max,
            entry_optimal=entry_optimal,
            entry_type="CONDITIONAL",
            entry_trigger=trigger,

            stop_price=stop_price,
            stop_rationale=f"Failed breakout at ${stop_price:.2f}",
            max_loss_pct=max_loss_pct,

            target_1=target_1,
            target_1_prob=win_probability * 0.9,
            target_2=target_2,
            target_2_prob=win_probability * 0.7,

            win_probability=win_probability,
            drawdown_probability=outcomes.prob_down_5pct_before_up_10pct * 0.5,

            expected_gain_if_win=expected_gain,
            expected_loss_if_loss=expected_loss,
            expected_value=expected_value,
            risk_reward_ratio=risk_reward_ratio,

            kelly_fraction=kelly,
            recommended_size_pct=recommended_size,
            max_size_pct=max_size,
            sizing_rationale=f"Conservative sizing: {recommended_size:.1%} of capital (Half-Kelly: {kelly:.1%})",

            optimal_hold_days=hold_days,
            max_hold_days=hold_days,
            time_stop_date="",

            options_recommendation=options_rec,

            status="CONDITIONAL",
            confidence=confidence,
            right_side_score=right_side_score,
        )

    def _design_options_strategy(
        self,
        direction: str,
        entry_price: float,
        state: StateVector,
        outcomes: ActuarialOutcomes,
        scenario_type: str,
    ) -> Dict:
        """
        Design options strategy for scenario.
        """
        hold_days = self._hold_days(outcomes)
        dte = hold_days + 5

        if state.catalyst_proximity == "HIGH" and state.days_to_earnings > 0:
            dte = min(dte, state.days_to_earnings - 2)

        if state.vol_regime == "COMPRESSION":
            if scenario_type == "AGGRESSIVE":
                strike = entry_price * 1.03
                strike_type = "OTM"
            else:
                strike = entry_price * 1.01
                strike_type = "Slightly OTM"
        else:
            strike = entry_price
            strike_type = "ATM"

        return {
            "direction": direction,
            "strike_type": strike_type,
            "recommended_strike": strike,
            "dte": dte,
            "expiration_type": "Weekly" if dte <= 14 else "Monthly",
        }
