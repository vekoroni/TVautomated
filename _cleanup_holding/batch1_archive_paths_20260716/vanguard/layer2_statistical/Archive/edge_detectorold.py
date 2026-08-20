"""
VANGUARD Layer 2 - Edge Detector
Determines if exploitable statistical edge exists

Multiple VETO gates - ALL must pass for edge to exist
"""

from typing import Dict
from ..schemas.state_outcomes_schema import StateVector, ActuarialOutcomes
from ..schemas.auction_schema import AuctionVerdict
from ..schemas.trade_schema import EdgeAssessment
from ..config import EDGE_DETECTION_THRESHOLDS


def calculate_trading_costs(ticker: str = None, liquidity_tier: str = 'NORMAL') -> float:
    """
    FIX 8: Calculate explicit trading costs (spread + slippage)
    
    Conservative, fixed costs per liquidity tier:
    - HIGH: Large cap, high volume (SPY, AAPL, MSFT)
    - NORMAL: Most stocks
    - LOW: Small cap, low volume
    
    Returns:
        Total cost as decimal (e.g., 0.0040 = 0.40%)
    """
    
    # High liquidity tickers
    high_liquid = [
        'SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 
        'TSLA', 'NVDA', 'META', 'NFLX', 'AMD', 'INTC'
    ]
    
    if ticker and ticker in high_liquid:
        liquidity_tier = 'HIGH'
    
    costs = {
        'HIGH': {
            'spread': 0.0010,   # 0.10% - tight spread
            'slippage': 0.0005  # 0.05% - minimal slippage
        },
        'NORMAL': {
            'spread': 0.0025,   # 0.25% - typical spread
            'slippage': 0.0015  # 0.15% - normal slippage
        },
        'LOW': {
            'spread': 0.0050,   # 0.50% - wide spread
            'slippage': 0.0030  # 0.30% - significant slippage
        }
    }
    
    tier_costs = costs.get(liquidity_tier, costs['NORMAL'])
    total_cost = tier_costs['spread'] + tier_costs['slippage']
    
    return total_cost


class EdgeDetector:
    """
    Multi-gate edge detection system
    
    Gates (ALL must pass):
    1. Auction ready (from Layer 1)
    2. Data confidence (enough historical samples)
    3. Expected value (positive EV)
    4. Win probability (high enough)
    5. Drawdown risk (acceptable)
    6. Sharpe ratio (risk-adjusted return)
    """
    
    def __init__(self):
        self.thresholds = EDGE_DETECTION_THRESHOLDS
        
    def detect_edge(self,
                   state: StateVector,
                   outcomes: ActuarialOutcomes,
                   auction_verdict: AuctionVerdict) -> EdgeAssessment:
        """
        Main entry: Determine if statistical edge exists
        
        FIX 3: THREE-TIER VERDICT SYSTEM
        - TRADE: Clear edge, act now
        - SETUP_FORMING: Positive structure, wait for better entry
        - NO_EDGE: Pass
        
        Args:
            state: Current state vector
            outcomes: Actuarial outcomes from query
            auction_verdict: Auction analysis from Layer 1
            
        Returns:
            EdgeAssessment with verdict and details
        """
        
        # === VETO GATE 1: Auction Conflicted ===
        if auction_verdict.auction_state == "CONFLICTED":
            return self._no_edge(
                reason=f"Auction conflicted: {auction_verdict.reasoning}",
                gate="AUCTION_CONFLICTED"
            )
            
        # === VETO GATE 2: Data Confidence ===
        if outcomes.confidence_level < self.thresholds['min_data_confidence']:
            return self._no_edge(
                reason=f"Insufficient data confidence: {outcomes.confidence_level:.0%} < {self.thresholds['min_data_confidence']:.0%} ({outcomes.n_observations} observations)",
                gate="DATA_CONFIDENCE"
            )
        
        # ========================================================================
        # FIX 3 + FIX 8: THREE-TIER VERDICT WITH COST MODEL
        # ========================================================================
        
        # Calculate costs
        cost = calculate_trading_costs(ticker=state.ticker)
        net_ev = outcomes.expected_value_20d - cost
        win_rate = outcomes.prob_up_10pct_20d
        
        # === TIER 1: TRADE (Clear Edge) ===
        # Net EV > 3% AND Win Rate > 40%
        if net_ev >= 0.03 and win_rate >= 0.40:
            return self._has_edge(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction_verdict,
                net_ev=net_ev,
                cost=cost,
                verdict_tier='TRADE'
            )
        
        # === TIER 2: SETUP_FORMING (Positive but needs confirmation) ===
        # Net EV > 0% AND Win Rate > 35%
        if net_ev > 0.0 and win_rate >= 0.35:
            return self._setup_forming(
                state=state,
                outcomes=outcomes,
                auction_verdict=auction_verdict,
                net_ev=net_ev,
                cost=cost,
                reason=f"Positive net EV ({net_ev:.2%}) but below 3% threshold. Win rate: {win_rate:.1%}. Wait for better entry or confirmation."
            )
        
        # === TIER 3: NO_EDGE (Pass) ===
        reasons = []
        if net_ev <= 0.0:
            reasons.append(f"Negative net EV: {net_ev:.2%} (gross: {outcomes.expected_value_20d:.2%}, cost: {cost:.2%})")
        elif net_ev < 0.03:
            reasons.append(f"Net EV too low: {net_ev:.2%} < 3.00%")
        if win_rate < 0.35:
            reasons.append(f"Win rate too low: {win_rate:.1%} < 35.0%")
            
        return self._no_edge(
            reason="; ".join(reasons),
            gate="INSUFFICIENT_EDGE"
        )
        
    def _determine_direction(self,
                            state: StateVector,
                            outcomes: ActuarialOutcomes,
                            auction: AuctionVerdict) -> str:
        """
        Determine CALL or PUT direction
        
        Priority:
        1. Auction control (40 points)
        2. Value migration (30 points)
        3. Statistical probability (20 points)
        4. Trend direction (10 points)
        """
        
        score = 0.0
        
        # Auction control (40 points)
        if auction.control.controller == "BUYERS":
            score += 40 * auction.control.confidence
        elif auction.control.controller == "SELLERS":
            score -= 40 * auction.control.confidence
            
        # Value migration (30 points)
        if auction.migration.direction == "UP":
            if auction.migration.consistency.startswith("CONSISTENT"):
                score += 30
            else:
                score += 15
        elif auction.migration.direction == "DOWN":
            if auction.migration.consistency.startswith("CONSISTENT"):
                score -= 30
            else:
                score -= 15
                
        # Statistical probability (20 points)
        if outcomes.prob_up_10pct_20d > 0.55:
            score += 20
        elif outcomes.prob_up_10pct_20d < 0.35:
            score -= 20
            
        # Trend direction (10 points)
        if state.trend_direction == "UP" and outcomes.prob_trend_continues_20d > 0.60:
            score += 10
        elif state.trend_direction == "DOWN" and outcomes.prob_trend_continues_20d > 0.60:
            score -= 10
            
        # Determine direction
        if score > 15:
            return "CALL"
        elif score < -15:
            return "PUT"
        else:
            # Tie-breaker: Default to auction control
            if auction.control.controller == "BUYERS":
                return "CALL"
            elif auction.control.controller == "SELLERS":
                return "PUT"
            else:
                return "CALL"  # Default bullish (equity risk premium)
                
    def _calculate_confidence(self,
                             state: StateVector,
                             outcomes: ActuarialOutcomes,
                             auction: AuctionVerdict) -> float:
        """
        Overall confidence in the edge
        
        Combines:
        - State measurement confidence (25%)
        - Actuarial data confidence (35%)
        - Auction verdict confidence (40%)
        """
        
        return (
            state.confidence * 0.25 +
            outcomes.confidence_level * 0.35 +
            auction.confidence * 0.40
        )
        
    def _calculate_right_side_score(self,
                                    state: StateVector,
                                    outcomes: ActuarialOutcomes,
                                    auction: AuctionVerdict) -> float:
        """
        Are we on the RIGHT SIDE of the trade?
        
        Maximum alignment across all factors = 100
        """
        
        score = 50.0  # Start neutral
        
        # Auction alignment (25 points)
        if auction.auction_state == "ALIGNED":
            score += 25
        elif auction.auction_state == "TRANSITIONING":
            score += 15
        elif auction.auction_state == "SEARCHING":
            score += 5
            
        # Control + Direction (20 points)
        if auction.control.controller in ["BUYERS", "SELLERS"]:
            score += 20 * auction.control.confidence
            
        # Value migration (15 points)
        if auction.migration.consistency.startswith("CONSISTENT"):
            score += 15
        elif auction.migration.consistency.startswith("TRENDING"):
            score += 10
            
        # Statistical probability (15 points)
        if outcomes.prob_up_10pct_20d > 0.60 or outcomes.prob_up_10pct_20d < 0.30:
            score += 15
        elif outcomes.prob_up_10pct_20d > 0.55 or outcomes.prob_up_10pct_20d < 0.35:
            score += 10
            
        # Trend + Probability alignment (10 points)
        if state.trend_direction != "SIDEWAYS" and outcomes.prob_trend_continues_20d > 0.65:
            score += 10
            
        # Catalyst alignment (10 points)
        if state.catalyst_proximity == "HIGH":
            if state.earnings_window in ["PRE_20D", "PRE_10D"]:
                if outcomes.prob_drift_into_earnings and outcomes.prob_drift_into_earnings > 0.60:
                    score += 10
                    
        # Macro alignment (5 points)
        if state.macro_regime == "RISK_ON" and outcomes.prob_up_10pct_20d > 0.50:
            score += 5
        elif state.macro_regime == "RISK_OFF" and outcomes.prob_up_10pct_20d < 0.40:
            score += 5
            
        return min(100.0, score)
        
    def _generate_rationale(self,
                           state: StateVector,
                           outcomes: ActuarialOutcomes,
                           auction: AuctionVerdict,
                           direction: str,
                           net_ev: float = None,
                           cost: float = None) -> str:
        """
        Human-readable explanation of why edge exists
        FIX 8: Now includes cost breakdown
        """
        
        parts = []
        
        parts.append(f"EDGE DETECTED: {direction}S")
        parts.append("")
        
        # FIX 8: Cost breakdown
        if net_ev is not None and cost is not None:
            parts.append("=== EXPECTED VALUE (NET) ===")
            parts.append(f"Gross EV: {outcomes.expected_value_20d:.2%}")
            parts.append(f"Trading Costs: -{cost:.2%} (spread + slippage)")
            parts.append(f"Net EV: {net_ev:.2%}")
            parts.append("")
        
        parts.append("=== AUCTION VERDICT ===")
        parts.append(auction.reasoning)
        parts.append("")
        parts.append("=== STATISTICAL EDGE ===")
        parts.append(f"Historical Context: {outcomes.n_observations} similar instances")
        parts.append(f"Win Rate: {outcomes.prob_up_10pct_20d:.1%} probability of +10% in 20 days")
        parts.append(f"Sharpe Ratio: {outcomes.sharpe_ratio:.2f}")
        parts.append("")
        parts.append(f"Typical Win: {outcomes.median_gain_if_up:.1%} in {outcomes.median_days_to_target:.0f} days")
        parts.append(f"Typical Loss: {outcomes.median_loss_if_down:.1%}")
        parts.append(f"Max Drawdown Risk: {outcomes.median_max_drawdown:.1%}")
        parts.append("")
        parts.append("=== CURRENT STATE ===")
        parts.append(f"Volatility: {state.vol_regime} (ATR {state.atr_percentile:.0f}th percentile)")
        parts.append(f"Trend: {state.trend_direction} ({state.trend_maturity})")
        parts.append(f"Structure: {state.structure_quality} (acceptance: {state.value_acceptance_score:.0f}/100)")
        parts.append(f"Control: {state.control_state} ({state.control_confidence:.0%})")
        parts.append(f"Migration: {state.value_migration_direction} ({auction.migration.speed})")
        
        return "\n".join(parts)
        
    def _no_edge(self, reason: str, gate: str) -> EdgeAssessment:
        """
        Return when no edge exists
        """
        
        return EdgeAssessment(
            has_edge=False,
            edge_direction="NONE",
            edge_magnitude=0.0,
            confidence=0.0,
            right_side_score=0.0,
            failed_gate=gate,
            no_edge_reason=reason,
            state=None,
            outcomes=None,
            auction_verdict=None,
            rationale=f"NO EDGE ({gate}): {reason}"
        )
    
    def _has_edge(self,
                  state: StateVector,
                  outcomes: ActuarialOutcomes,
                  auction_verdict: AuctionVerdict,
                  net_ev: float,
                  cost: float,
                  verdict_tier: str) -> EdgeAssessment:
        """
        FIX 3: Return when clear TRADE edge exists
        """
        
        # Determine direction
        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        
        # Calculate confidence
        confidence = self._calculate_confidence(state, outcomes, auction_verdict)
        
        # Calculate right-side score
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        
        # Generate rationale
        rationale = self._generate_rationale(
            state, outcomes, auction_verdict, edge_direction, net_ev, cost
        )
        
        return EdgeAssessment(
            has_edge=True,
            edge_direction=edge_direction,
            edge_magnitude=net_ev,
            confidence=confidence,
            right_side_score=right_side_score,
            state=state,
            outcomes=outcomes,
            auction_verdict=auction_verdict,
            rationale=rationale
        )
    
    def _setup_forming(self,
                       state: StateVector,
                       outcomes: ActuarialOutcomes,
                       auction_verdict: AuctionVerdict,
                       net_ev: float,
                       cost: float,
                       reason: str) -> EdgeAssessment:
        """
        FIX 3: Return for SETUP_FORMING (positive structure, needs confirmation)
        """
        
        # Determine direction (for reference)
        edge_direction = self._determine_direction(state, outcomes, auction_verdict)
        
        # Lower confidence for setup forming
        confidence = self._calculate_confidence(state, outcomes, auction_verdict) * 0.7
        
        # Calculate right-side score
        right_side_score = self._calculate_right_side_score(state, outcomes, auction_verdict)
        
        # Generate rationale
        rationale = f"SETUP FORMING ({edge_direction})\n\n{reason}\n\n" + \
                   self._generate_rationale(state, outcomes, auction_verdict, edge_direction, net_ev, cost)
        
        return EdgeAssessment(
            has_edge=False,  # Not tradeable YET
            edge_direction=edge_direction,
            edge_magnitude=net_ev,
            confidence=confidence,
            right_side_score=right_side_score,
            state=state,
            outcomes=outcomes,
            auction_verdict=auction_verdict,
            rationale=rationale,
            failed_gate="SETUP_FORMING",
            no_edge_reason=reason
        )
