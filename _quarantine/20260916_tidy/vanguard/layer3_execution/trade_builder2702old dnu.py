"""
VANGUARD Layer 3 - Trade Builder
Assembles complete trade plan with all scenarios and recommendations
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from ..schemas.trade_schema import TradePlan, TradeScenario
from ..schemas.trade_schema import EdgeAssessment
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from .scenario_builder import MultiScenarioBuilder


class TradeBuilder:
    """
    Builds complete trade plan from edge assessment
    
    Outputs:
    - All three scenarios (Aggressive, Moderate, Conservative)
    - Recommended scenario based on user risk profile
    - Pyramiding strategy (optional)
    - Invalidation criteria
    """
    
    def __init__(self):
        self.scenario_builder = MultiScenarioBuilder()
        
    def build_trade_plan(self,
                        ticker: str,
                        current_price: float,
                        edge: EdgeAssessment) -> TradePlan:
        """
        Main entry: Build complete trade plan
        
        Args:
            ticker: Stock symbol
            current_price: Current price
            edge: EdgeAssessment from Layer 2
            
        Returns:
            Complete TradePlan with all scenarios
        """
        
        state = edge.state
        outcomes = edge.outcomes
        auction = edge.auction_verdict
        direction = edge.edge_direction
        
        # Build all scenarios
        scenarios = self.scenario_builder.build_scenarios(
            ticker, current_price, direction, state, outcomes, auction
        )
        
        # Determine recommended scenario
        recommended = self._determine_recommended_scenario(scenarios, auction, state)
        
        # Build pyramiding plan (optional advanced strategy)
        pyramiding = self._build_pyramiding_plan(scenarios, current_price)
        
        # Define invalidation criteria
        invalidation = self._define_invalidation_criteria(
            scenarios, auction, state, outcomes
        )
        
        # Calculate overall metrics
        overall_confidence = self._calculate_overall_confidence(scenarios, edge)
        overall_right_side = self._calculate_overall_right_side_score(scenarios, edge)
        
        # Generate recommendation rationale
        rationale = self._generate_recommendation_rationale(
            recommended, scenarios, auction, state
        )
        
        return TradePlan(
            ticker=ticker,
            timestamp=datetime.now().isoformat(),
            current_price=current_price,
            direction=direction,
            
            scenario_aggressive=scenarios['aggressive'],
            scenario_moderate=scenarios['moderate'],
            scenario_conservative=scenarios['conservative'],
            
            pyramiding_plan=pyramiding,
            
            recommended_scenario=recommended,
            recommendation_rationale=rationale,
            
            invalidation_criteria=invalidation,
            
            overall_confidence=overall_confidence,
            overall_right_side_score=overall_right_side,
            
            edge_rationale=edge.rationale,
            
            # Store for reference
            auction_verdict=self._serialize_auction(auction),
            state_vector=self._serialize_state(state),
            actuarial_outcomes=self._serialize_outcomes(outcomes)
        )
        
    def _determine_recommended_scenario(self,
                                       scenarios: Dict[str, TradeScenario],
                                       auction: AuctionVerdict,
                                       state: StateVector) -> str:
        """
        Determine which scenario to recommend based on:
        - Auction state (how ready is market?)
        - State quality (how strong is setup?)
        - Risk tolerance (default: moderate)
        """
        
        # If auction is ALIGNED and all signals strong → Aggressive viable
        if (auction.auction_state == "ALIGNED" and
            auction.acceptance.score >= 75 and
            auction.control.confidence >= 0.70):
            return "AGGRESSIVE"
            
        # If auction is SEARCHING or weak signals → Conservative only
        if (auction.auction_state == "SEARCHING" or
            auction.acceptance.score < 50 or
            auction.control.confidence < 0.55):
            return "CONSERVATIVE"
            
        # Default: Moderate (balanced approach)
        return "MODERATE"
        
    def _build_pyramiding_plan(self,
                               scenarios: Dict[str, TradeScenario],
                               current_price: float) -> Optional[Dict]:
        """
        Build pyramiding strategy (scale in across scenarios)
        
        Example:
        - 25% NOW (aggressive entry)
        - 25% at $100 (moderate trigger)
        - 25% at $102.50 (conservative trigger)
        - 25% at $105 (momentum confirmation)
        """
        
        aggressive = scenarios['aggressive']
        moderate = scenarios['moderate']
        conservative = scenarios['conservative']
        
        # Only build pyramiding if all scenarios are feasible
        if aggressive.status != "AVAILABLE_NOW":
            return None
            
        return {
            'total_position': '100%',
            'initial_entry': {
                'percent': '25%',
                'price': aggressive.entry_optimal,
                'trigger': 'Immediate (Aggressive)'
            },
            'add_on_1': {
                'percent': '25%',
                'price': moderate.entry_optimal,
                'trigger': moderate.entry_trigger
            },
            'add_on_2': {
                'percent': '25%',
                'price': conservative.entry_optimal,
                'trigger': conservative.entry_trigger
            },
            'add_on_3': {
                'percent': '25%',
                'price': conservative.target_1,
                'trigger': f'Momentum confirmation at {conservative.target_1:.2f}'
            },
            'rationale': 'Scale in as confirmation increases, maximize flexibility'
        }
        
    def _define_invalidation_criteria(self,
                                     scenarios: Dict[str, TradeScenario],
                                     auction: AuctionVerdict,
                                     state: StateVector,
                                     outcomes: ActuarialOutcomes) -> list:
        """
        When is the thesis WRONG and we must exit?
        """
        
        criteria = []
        
        # Price-based (from conservative scenario stop)
        conservative_stop = scenarios['conservative'].stop_price
        criteria.append(f"Close below ${conservative_stop:.2f} (structural breakdown)")
        
        # Time-based
        max_hold = outcomes.recommended_hold_days
        criteria.append(f"No progress toward target within {max_hold} trading days")
        
        # Auction-based
        if auction.control.controller in ["BUYERS", "SELLERS"]:
            opposite = "SELLERS" if auction.control.controller == "BUYERS" else "BUYERS"
            criteria.append(f"Control shifts decisively to {opposite} (>70% confidence)")
            
        # Value migration reversal
        if auction.migration.direction != "SIDEWAYS":
            opposite_dir = "DOWN" if auction.migration.direction == "UP" else "UP"
            criteria.append(f"Value migration reverses to {opposite_dir} consistently")
            
        # Catalyst risk (if applicable)
        if state.catalyst_proximity == "HIGH":
            criteria.append(f"Earnings date moves unexpectedly or company pre-announces")
            
        # Volatility spike
        if state.vol_regime == "COMPRESSION":
            criteria.append("Volatility spikes to >90th percentile without price follow-through")
            
        return criteria
        
    def _calculate_overall_confidence(self,
                                     scenarios: Dict[str, TradeScenario],
                                     edge: EdgeAssessment) -> float:
        """
        Overall confidence across all scenarios
        Weight by expected value
        """
        
        # Weight by EV of each scenario
        agg_ev = scenarios['aggressive'].expected_value
        mod_ev = scenarios['moderate'].expected_value
        con_ev = scenarios['conservative'].expected_value
        
        total_ev = agg_ev + mod_ev + con_ev
        
        if total_ev <= 0:
            return edge.confidence
            
        weighted_confidence = (
            scenarios['aggressive'].confidence * (agg_ev / total_ev) +
            scenarios['moderate'].confidence * (mod_ev / total_ev) +
            scenarios['conservative'].confidence * (con_ev / total_ev)
        )
        
        return weighted_confidence
        
    def _calculate_overall_right_side_score(self,
                                           scenarios: Dict[str, TradeScenario],
                                           edge: EdgeAssessment) -> float:
        """
        Overall right-side score
        """
        
        # Average across scenarios, weighted by confidence
        agg = scenarios['aggressive']
        mod = scenarios['moderate']
        con = scenarios['conservative']
        
        total_conf = agg.confidence + mod.confidence + con.confidence
        
        if total_conf == 0:
            return edge.right_side_score
            
        weighted_score = (
            agg.right_side_score * (agg.confidence / total_conf) +
            mod.right_side_score * (mod.confidence / total_conf) +
            con.right_side_score * (con.confidence / total_conf)
        )
        
        return weighted_score
        
    def _generate_recommendation_rationale(self,
                                          recommended: str,
                                          scenarios: Dict[str, TradeScenario],
                                          auction: AuctionVerdict,
                                          state: StateVector) -> str:
        """
        Explain why this scenario is recommended
        """
        
        scenario = scenarios[recommended.lower()]
        
        parts = []
        
        parts.append(f"RECOMMENDED: {recommended} SCENARIO")
        parts.append("")
        parts.append(f"Entry: {scenario.entry_trigger or 'Immediate'}")
        parts.append(f"Price: ${scenario.entry_optimal:.2f}")
        parts.append(f"Win Probability: {scenario.win_probability:.0%}")
        parts.append(f"Expected Value: {scenario.expected_value:.2%}")
        parts.append(f"Position Size: {scenario.recommended_size_pct:.1%} of capital")
        parts.append("")
        parts.append("RATIONALE:")
        
        if recommended == "AGGRESSIVE":
            parts.append("  • Auction signals are strong (alignment + acceptance)")
            parts.append("  • Risk/reward favors early entry (maximum profit potential)")
            parts.append("  • Control is established, value being accepted")
        elif recommended == "MODERATE":
            parts.append("  • Balanced approach: confirmation + profit potential")
            parts.append("  • Wait for trigger reduces risk without sacrificing too much upside")
            parts.append("  • Recommended for most traders (60%+ probability)")
        else:  # CONSERVATIVE
            parts.append("  • Highest probability setup (75%+ win rate)")
            parts.append("  • Reduced profit potential is acceptable for certainty")
            parts.append("  • Recommended when signals are mixed or uncertain")
            
        return "\n".join(parts)
        
    def _serialize_auction(self, auction: AuctionVerdict) -> Dict:
        """Convert auction verdict to dict"""
        return {
            'state': auction.auction_state,
            'confidence': auction.confidence,
            'acceptance_score': auction.acceptance.score,
            'control': auction.control.controller,
            'control_confidence': auction.control.confidence
        }
        
    def _serialize_state(self, state: StateVector) -> Dict:
        """Convert state vector to dict"""
        return {
            'hash': state.state_hash,
            'vol_regime': state.vol_regime,
            'trend': state.trend_direction,
            'structure': state.structure_quality
        }
        
    def _serialize_outcomes(self, outcomes: ActuarialOutcomes) -> Dict:
        """Convert outcomes to dict"""
        return {
            'n_observations': outcomes.n_observations,
            'win_rate': outcomes.prob_up_10pct_20d,
            'expected_value': outcomes.expected_value_20d,
            'confidence': outcomes.confidence_level
        }
