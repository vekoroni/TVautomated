"""
VANGUARD Layer 3 - Multi-Scenario Builder
Generates multiple entry scenarios with different risk/reward profiles

AGGRESSIVE: Enter NOW (pre-confirmation)
MODERATE: Enter on partial confirmation (VWAP reclaim, control shift)
CONSERVATIVE: Enter on full confirmation (breakout)
"""

from typing import Dict, List, Optional
from ..schemas.trade_schema import TradeScenario
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes, ScenarioOutcomes
from ..schemas.auction_schema import AuctionVerdict
from ..config import SCENARIO_PROBABILITIES, POSITION_SIZING_CONFIG


class MultiScenarioBuilder:
    """
    Builds multiple trade scenarios from edge assessment
    
    Each scenario has:
    - Different entry point
    - Different probability
    - Different risk/reward
    - Different position sizing
    """
    
    def __init__(self):
        self.prob_config = SCENARIO_PROBABILITIES
        self.sizing_config = POSITION_SIZING_CONFIG
        
    def build_scenarios(self,
                       ticker: str,
                       current_price: float,
                       direction: str,
                       state: StateVector,
                       outcomes: ActuarialOutcomes,
                       auction: AuctionVerdict) -> Dict[str, TradeScenario]:
        """
        Build all three scenarios
        
        Returns:
            Dict with keys: 'aggressive', 'moderate', 'conservative'
        """
        
        scenarios = {}
        
        # SCENARIO 1: AGGRESSIVE (Enter NOW)
        scenarios['aggressive'] = self._build_aggressive_scenario(
            ticker, current_price, direction, state, outcomes, auction
        )
        
        # SCENARIO 2: MODERATE (Wait for partial confirmation)
        scenarios['moderate'] = self._build_moderate_scenario(
            ticker, current_price, direction, state, outcomes, auction
        )
        
        # SCENARIO 3: CONSERVATIVE (Wait for full confirmation)
        scenarios['conservative'] = self._build_conservative_scenario(
            ticker, current_price, direction, state, outcomes, auction
        )
        
        return scenarios
        
    def _build_aggressive_scenario(self,
                                   ticker: str,
                                   current_price: float,
                                   direction: str,
                                   state: StateVector,
                                   outcomes: ActuarialOutcomes,
                                   auction: AuctionVerdict) -> TradeScenario:
        """
        AGGRESSIVE: Enter immediately at current price
        
        Risk: Higher (no confirmation)
        Reward: Maximum (lowest entry price)
        """
        
        # Entry parameters
        entry_optimal = current_price
        entry_min = current_price * 0.995  # -0.5%
        entry_max = current_price * 1.005  # +0.5%
        
        # Stop loss (wider for aggressive entries)
        if direction == "CALL":
            # Below value area low or POC
            stop_price = min(
                auction.profile.value_area_low * 0.99,
                auction.profile.poc * 0.985
            )
        else:  # PUT
            # Above value area high
            stop_price = auction.profile.value_area_high * 1.01
            
        max_loss_pct = abs(current_price - stop_price) / current_price
        
        # Targets (from actuarial outcomes)
        target_1 = current_price * (1 + outcomes.median_gain_if_up)
        target_2 = current_price * (1 + outcomes.median_gain_if_up * 1.5)
        
        # Probabilities (adjusted down for aggressive entry)
        base_prob = self.prob_config['aggressive_base_probability']
        
        # Boost for supporting factors
        probability = base_prob
        if auction.acceptance.score >= 50:
            probability += 0.05
        if auction.control.confidence > 0.60:
            probability += 0.05
        if state.value_migration_direction != "SIDEWAYS":
            probability += 0.03
            
        win_probability = min(probability, self.prob_config['max_probability'])
        
        # Expected outcomes
        expected_gain = outcomes.median_gain_if_up
        expected_loss = outcomes.median_loss_if_down
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        
        # Risk/Reward
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss != 0 else 0
        
        # Position sizing (Kelly)
        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = (win_probability - (1 - win_probability) / risk_reward_ratio)
            kelly = max(0, min(kelly, 0.25))
        else:
            kelly = 0.0
            
        # Apply aggressive sizing factor
        recommended_size = kelly * self.sizing_config['aggressive_sizing_factor']
        recommended_size = min(recommended_size, self.sizing_config['max_position_size'])
        max_size = min(kelly * 1.2, self.sizing_config['max_position_size'])
        
        # Options recommendation
        options_rec = self._design_options_strategy(
            direction, current_price, state, outcomes, "AGGRESSIVE"
        )
        
        # Confidence and right-side score (lower for aggressive)
        confidence = auction.confidence * 0.7  # Reduced confidence
        right_side_score = 50.0  # Neutral starting point
        
        # Boost right-side score for supporting factors
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
            target_1_prob=win_probability * 0.8,  # Slightly lower
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
            
            optimal_hold_days=int(outcomes.median_days_to_target),
            max_hold_days=outcomes.recommended_hold_days,
            time_stop_date="",  # TODO: Calculate
            
            options_recommendation=options_rec,
            
            status="AVAILABLE_NOW",
            confidence=confidence,
            right_side_score=right_side_score
        )
        
    def _build_moderate_scenario(self,
                                 ticker: str,
                                 current_price: float,
                                 direction: str,
                                 state: StateVector,
                                 outcomes: ActuarialOutcomes,
                                 auction: AuctionVerdict) -> TradeScenario:
        """
        MODERATE: Wait for partial confirmation
        
        Triggers:
        - VWAP reclaim
        - Value area entry
        - Control shift
        """
        
        # Determine trigger and trigger price
        triggers = []
        
        # If below POC, POC reclaim is trigger
        if current_price < auction.profile.poc:
            trigger_price = auction.profile.poc
            triggers.append(f"VWAP/POC reclaim at ${trigger_price:.2f}")
        # If below value area, VA entry is trigger
        elif auction.acceptance.position_in_profile == "BELOW_VALUE":
            trigger_price = auction.profile.value_area_low
            triggers.append(f"Value Area entry at ${trigger_price:.2f}")
        else:
            trigger_price = current_price * 1.02
            triggers.append(f"Price holds above ${trigger_price:.2f}")
            
        trigger = triggers[0] if triggers else "Partial confirmation"
        
        # Entry parameters
        entry_optimal = trigger_price
        entry_min = trigger_price * 0.995
        entry_max = trigger_price * 1.005
        
        # Stop loss (tighter than aggressive)
        if direction == "CALL":
            stop_price = auction.profile.poc * 0.97
        else:
            stop_price = auction.profile.value_area_high * 1.03
            
        max_loss_pct = abs(trigger_price - stop_price) / trigger_price
        
        # Targets (from trigger price)
        target_1 = trigger_price * (1 + outcomes.median_gain_if_up * 0.9)
        target_2 = trigger_price * (1 + outcomes.median_gain_if_up * 1.3)
        
        # Probabilities (moderate - higher than aggressive)
        base_prob = self.prob_config['moderate_base_probability']
        
        probability = base_prob
        if auction.control.confidence > 0.65:
            probability += 0.03
        if state.value_migration_direction != "SIDEWAYS":
            probability += 0.03
            
        win_probability = min(probability, self.prob_config['max_probability'])
        
        # Expected outcomes
        expected_gain = outcomes.median_gain_if_up * 0.9  # Slightly less due to higher entry
        expected_loss = outcomes.median_loss_if_down
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss != 0 else 0
        
        # Position sizing (standard Kelly)
        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = (win_probability - (1 - win_probability) / risk_reward_ratio)
            kelly = max(0, min(kelly, 0.25))
        else:
            kelly = 0.0
            
        recommended_size = kelly * self.sizing_config['moderate_sizing_factor']
        recommended_size = min(recommended_size, self.sizing_config['max_position_size'])
        max_size = min(kelly * 1.3, self.sizing_config['max_position_size'])
        
        # Options
        options_rec = self._design_options_strategy(
            direction, trigger_price, state, outcomes, "MODERATE"
        )
        
        # Confidence (higher than aggressive)
        confidence = auction.confidence * 0.85
        right_side_score = 65.0  # Higher baseline
        
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
            
            optimal_hold_days=int(outcomes.median_days_to_target * 0.9),
            max_hold_days=outcomes.recommended_hold_days,
            time_stop_date="",
            
            options_recommendation=options_rec,
            
            status="CONDITIONAL",
            confidence=confidence,
            right_side_score=right_side_score
        )
        
    def _build_conservative_scenario(self,
                                    ticker: str,
                                    current_price: float,
                                    direction: str,
                                    state: StateVector,
                                    outcomes: ActuarialOutcomes,
                                    auction: AuctionVerdict) -> TradeScenario:
        """
        CONSERVATIVE: Wait for full confirmation (breakout)
        
        Highest probability, lowest profit potential
        """
        
        # Safety: Fallback to current_price if profile data missing
        va_high = auction.profile.value_area_high if auction.profile.value_area_high > 0 else current_price * 1.05
        va_low = auction.profile.value_area_low if auction.profile.value_area_low > 0 else current_price * 0.95
        
        # Trigger: Breakout above value area high
        trigger_price = va_high * 1.02  # 2% above VA high
        trigger = f"Breakout above ${trigger_price:.2f}"
        
        entry_optimal = trigger_price
        entry_min = trigger_price * 0.995
        entry_max = trigger_price * 1.01
        
        # Stop loss (tight - breakout failed)
        if direction == "CALL":
            stop_price = va_high * 0.98
        else:
            stop_price = va_low * 1.02
        
        # Safety: Prevent division by zero
        if trigger_price == 0:
            trigger_price = current_price
        
        max_loss_pct = abs(trigger_price - stop_price) / trigger_price if trigger_price != 0 else 0.02
        
        # Targets (from breakout price)
        target_1 = trigger_price * (1 + outcomes.median_gain_if_up * 0.7)
        target_2 = trigger_price * (1 + outcomes.median_gain_if_up * 1.0)
        
        # Probabilities (highest)
        base_prob = self.prob_config['conservative_base_probability']
        
        probability = base_prob
        if auction.control.confidence > 0.70:
            probability += 0.02
            
        win_probability = min(probability, self.prob_config['max_probability'])
        
        # Expected outcomes
        expected_gain = outcomes.median_gain_if_up * 0.7  # Much less due to late entry
        expected_loss = outcomes.median_loss_if_down * 0.6  # Tighter stop
        expected_value = (win_probability * expected_gain) + ((1 - win_probability) * expected_loss)
        
        risk_reward_ratio = abs(expected_gain / expected_loss) if expected_loss != 0 else 0
        
        # Position sizing (can size larger due to high probability)
        if win_probability > 0 and risk_reward_ratio > 0:
            kelly = (win_probability - (1 - win_probability) / risk_reward_ratio)
            kelly = max(0, min(kelly * 0.5, 0.25))  # Half Kelly for safety
        else:
            kelly = 0.0
            
        recommended_size = kelly * self.sizing_config['conservative_sizing_factor']
        recommended_size = min(recommended_size, self.sizing_config['max_position_size_high_confidence'])
        max_size = min(kelly * 1.5, self.sizing_config['max_position_size_high_confidence'])
        
        # Options
        options_rec = self._design_options_strategy(
            direction, trigger_price, state, outcomes, "CONSERVATIVE"
        )
        
        # Confidence (highest)
        confidence = auction.confidence * 0.95
        right_side_score = 75.0  # High baseline
        
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
            
            optimal_hold_days=int(outcomes.median_days_to_target * 0.8),
            max_hold_days=outcomes.recommended_hold_days - 5,
            time_stop_date="",
            
            options_recommendation=options_rec,
            
            status="CONDITIONAL",
            confidence=confidence,
            right_side_score=right_side_score
        )
        
    def _design_options_strategy(self,
                                direction: str,
                                entry_price: float,
                                state: StateVector,
                                outcomes: ActuarialOutcomes,
                                scenario_type: str) -> Dict:
        """
        Design options strategy for scenario
        """
        
        # DTE based on hold period
        hold_days = int(outcomes.median_days_to_target)
        dte = hold_days + 5  # Buffer
        
        # Adjust for earnings
        if state.catalyst_proximity == "HIGH" and state.days_to_earnings > 0:
            dte = min(dte, state.days_to_earnings - 2)
            
        # Strike selection based on vol regime and scenario
        if state.vol_regime == "COMPRESSION":
            if scenario_type == "AGGRESSIVE":
                strike = entry_price * 1.03  # 3% OTM
                strike_type = "OTM"
            else:
                strike = entry_price * 1.01  # 1% OTM
                strike_type = "Slightly OTM"
        else:
            strike = entry_price  # ATM
            strike_type = "ATM"
            
        return {
            'direction': direction,
            'strike_type': strike_type,
            'recommended_strike': strike,
            'dte': dte,
            'expiration_type': 'Weekly' if dte <= 14 else 'Monthly'
        }
