"""
VANGUARD Trade Schemas
Final output structures - Multi-Scenario Trade Plans
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class EdgeAssessment:
    """
    Edge detection output from Layer 2
    """
    has_edge: bool
    edge_direction: str  # CALL, PUT, NONE
    edge_magnitude: float  # Expected value
    confidence: float  # 0-1 overall confidence
    right_side_score: float  # 0-100 alignment score
    
    # What failed (if no edge)
    failed_gate: Optional[str] = None
    no_edge_reason: Optional[str] = None
    
    # References
    state: Optional['StateVector'] = None
    outcomes: Optional['ActuarialOutcomes'] = None
    auction_verdict: Optional['AuctionVerdict'] = None
    
    rationale: str = ""


@dataclass
class TradeScenario:
    """
    A single trade scenario (Aggressive, Moderate, or Conservative)
    """
    # Identification
    scenario_type: str  # AGGRESSIVE, MODERATE, CONSERVATIVE
    scenario_label: str  # Human-readable label
    
    # Entry
    entry_min: float
    entry_max: float
    entry_optimal: float
    entry_type: str  # IMMEDIATE, LIMIT, CONDITIONAL
    
    # Risk
    stop_price: float
    stop_rationale: str
    max_loss_pct: float
    
    # Targets
    target_1: float
    target_1_prob: float
    target_2: float
    target_2_prob: float
    
    # Probabilities
    win_probability: float  # Overall probability of profit
    drawdown_probability: float  # Probability of >5% drawdown first
    
    # Expected outcomes
    expected_gain_if_win: float
    expected_loss_if_loss: float
    expected_value: float  # EV per share
    risk_reward_ratio: float  # To target 2
    
    # Position sizing
    kelly_fraction: float
    recommended_size_pct: float  # % of capital
    max_size_pct: float
    sizing_rationale: str
    
    # Timing
    optimal_hold_days: int
    max_hold_days: int
    time_stop_date: str
    
    # Status
    status: str  # AVAILABLE_NOW, CONDITIONAL, NOT_FEASIBLE
    
    # Confidence
    confidence: float  # 0-1 confidence in this scenario
    right_side_score: float  # 0-100
    
    # Optional fields with defaults
    entry_trigger: Optional[str] = None  # For conditional entries
    
    # Options strategy
    options_recommendation: Dict = field(default_factory=dict)
    # {direction, strike_type, recommended_strike, dte, expiration_type}


@dataclass
class TradePlan:
    """
    Complete multi-scenario trade plan
    VANGUARD outputs this with ALL scenarios
    """
    # Identification
    ticker: str
    timestamp: str
    current_price: float
    
    # Direction
    direction: str  # CALL, PUT
    
    # Recommendation
    recommended_scenario: str  # AGGRESSIVE, MODERATE, CONSERVATIVE, PYRAMIDING
    recommendation_rationale: str
    
    # Overall metrics
    overall_confidence: float  # 0-1
    overall_right_side_score: float  # 0-100
    
    # Optional fields with defaults
    # All scenarios
    scenario_aggressive: Optional[TradeScenario] = None
    scenario_moderate: Optional[TradeScenario] = None
    scenario_conservative: Optional[TradeScenario] = None
    
    # Pyramiding strategy (optional)
    pyramiding_plan: Optional[Dict] = None
    # {
    #   'initial_size': 25%, 
    #   'add_triggers': ['$100 break', '$102.50 break'],
    #   'add_sizes': [25%, 25%, 25%]
    # }
    
    # Invalidation (applies to all scenarios)
    invalidation_criteria: List[str] = field(default_factory=list)
    
    # Rationale (from edge assessment)
    edge_rationale: str = ""
    
    # References (for debugging/analysis)
    auction_verdict: Optional[Dict] = None
    state_vector: Optional[Dict] = None
    actuarial_outcomes: Optional[Dict] = None


@dataclass
class VanguardSignal:
    """
    Final VANGUARD output signal
    """
    # Identification
    ticker: str
    timestamp: str
    
    # Verdict
    verdict: str  # TRADE, NO_TRADE, NO_EDGE
    final_recommendation: str  # "BUY CALL", "BUY PUT", "PASS"
    
    # Layer outputs
    layer_1_result: Optional[Dict] = None  # AuctionVerdict
    layer_2_result: Optional[Dict] = None  # {state, outcomes, edge}
    layer_3_result: Optional[TradePlan] = None  # Complete trade plan
    
    # Reasoning
    reasoning: str = ""
    
    # Execution plan (if TRADE)
    execution_plan: Optional[TradePlan] = None
    
    # Performance tracking
    signal_id: Optional[str] = None
    signal_quality_score: Optional[float] = None


@dataclass
class DailyReport:
    """
    Daily VANGUARD intelligence report
    """
    report_date: str
    generation_timestamp: str
    
    # Summary statistics
    tickers_analyzed: int
    signals_generated: int
    
    # Market commentary
    market_regime: str  # RISK_ON, RISK_OFF, TRANSITIONAL
    vix_level: float
    spy_trend: str
    
    # Optional fields with defaults
    # Signals by tier
    tier_1_signals: List[VanguardSignal] = field(default_factory=list)  # Both layers aligned
    tier_2_signals: List[VanguardSignal] = field(default_factory=list)  # VANGUARD early signals
    tier_3_signals: List[VanguardSignal] = field(default_factory=list)  # Statistical only
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    # Report path
    pdf_path: Optional[str] = None
    pdf_path: Optional[str] = None
