"""
VANGUARD State & Outcomes Schemas
Layer 2 - Statistical Edge data structures
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


@dataclass
class StateVector:
    """
    Complete quantified state of a stock at a moment in time
    Used to query actuarial database
    """
    # === IDENTIFICATION ===
    ticker: str
    timestamp: datetime
    price: float
    
    # === VOLATILITY REGIME ===
    atr_current: float
    atr_percentile: float  # 0-100
    bb_width_percentile: float
    iv_percentile: float
    vol_regime: str  # COMPRESSION, NORMAL, EXPANSION
    vol_regime_score: float  # 0-100
    
    # === TREND MATURITY ===
    distance_from_52w_high: float  # % from high (negative if below)
    distance_from_52w_low: float  # % from low (positive if above)
    days_since_52w_high: int
    trend_length_days: int
    trend_direction: str  # UP, DOWN, SIDEWAYS
    adx: float
    trend_maturity: str  # EARLY, MIDDLE, LATE, EXHAUSTED
    trend_strength_score: float
    
    # === STRUCTURE (Enhanced with Auction data) ===
    price_vs_vwap_1h: float  # % from VWAP
    price_vs_vwap_daily: float
    price_vs_poc: float  # % from Point of Control
    price_position_in_value: str  # ABOVE_VA, IN_VA, BELOW_VA
    value_acceptance_score: float  # From Layer 1 (0-100)
    failed_breakouts_20d: int
    control_state: str  # BUYERS, SELLERS, NEUTRAL (from Layer 1)
    control_confidence: float  # 0-1
    structure_quality: str  # STRONG, NEUTRAL, WEAK
    
    # === LIQUIDITY ===
    relative_volume: float  # vs 20D average
    spread_percentile: float
    liquidity_condition: str  # HIGH, NORMAL, LOW
    
    # === POSITIONING ===
    put_call_ratio: float
    put_call_oi_ratio: float
    options_skew: float  # -1 to +1
    net_gamma_exposure: float
    net_delta_exposure: float
    positioning_bias: str  # NET_LONG, NET_SHORT, NEUTRAL
    
    # === MACRO ===
    vix: float
    vix_percentile: float
    spy_trend: str
    sector_relative_strength: float
    macro_regime: str  # RISK_ON, RISK_OFF, TRANSITIONAL
    
    # === CATALYST ===
    days_to_earnings: int  # -1 if none scheduled
    earnings_window: str  # PRE_30D, PRE_20D, PRE_10D, POST, FAR
    days_since_earnings: int
    catalyst_proximity: str  # HIGH, MEDIUM, LOW, NONE
    
    # === AUCTION INTEGRATION (from Layer 1) ===
    value_migration_direction: str  # UP, DOWN, SIDEWAYS
    value_migration_speed: str  # FAST, MODERATE, SLOW
    auction_state: str  # ALIGNED, SEARCHING, CONTESTED
    
    # === INTRADAY MARKET PROFILE (Real-time context) ===
    intraday_position: str  # AT_SUPPORT, AT_RESISTANCE, NEAR_SUPPORT, IN_VALUE_AREA, OUT_OF_VALUE, UNKNOWN
    volume_profile_context: str  # ACCUMULATION, DISTRIBUTION, BALANCED, INSUFFICIENT_DATA
    control_dynamics: str  # BUYERS_STRENGTHENING, SELLERS_STRENGTHENING, NEUTRAL
    intraday_support: float  # Nearest support from volume profile
    intraday_resistance: float  # Nearest resistance from volume profile
    
    # === META ===
    state_hash: str  # Unique identifier for similarity matching
    confidence: float  # 0-1, confidence in state measurement


@dataclass
class ActuarialOutcomes:
    """
    Historical probability distribution for a given state
    This is what the actuarial query returns
    """
    # === SAMPLE METADATA ===
    n_observations: int  # How many historical instances?
    confidence_level: float  # 0-1 based on sample size
    lookback_period: str  # "3Y", "5Y", "10Y"
    
    # === CORE PROBABILITIES (20-day horizon) ===
    prob_up_10pct_20d: float  # P(+10% within 20 days)
    prob_down_5pct_before_up_10pct: float  # P(drawdown >5% before target)
    prob_trend_continues_20d: float  # P(trend same direction)
    
    # === MAGNITUDE EXPECTATIONS ===
    median_gain_if_up: float  # Median gain when it moves up
    median_loss_if_down: float  # Median loss when it moves down
    median_max_drawdown: float  # Median worst drawdown
    median_days_to_target: float  # Median time to reach +10%
    
    # === RISK-ADJUSTED METRICS ===
    expected_value_20d: float  # Expected value over 20 days
    sharpe_ratio: float  # Risk-adjusted return
    win_rate: float  # % of times return > 0
    avg_win_loss_ratio: float  # Avg win / Avg loss
    
    # === EXECUTION ===
    kelly_fraction: float  # Optimal position size (Kelly criterion)
    recommended_hold_days: int  # Typical hold period
    
    # === DISTRIBUTION ===
    outcome_distribution: Dict[str, float] = field(default_factory=dict)
    # Histogram: {"<-10%": 0.05, "-10 to -5%": 0.10, ...}
    
    # === OPTIONAL FIELDS (with defaults) ===
    prob_breakout_if_compressed: Optional[float] = None  # If in compression
    
    # === EARNINGS-SPECIFIC (if applicable) ===
    prob_drift_into_earnings: Optional[float] = None
    median_earnings_gap: Optional[float] = None
    prob_gap_same_direction: Optional[float] = None
    median_post_earnings_move: Optional[float] = None
    
    # === CONTEXTUAL INSIGHTS ===
    prob_up_if_buyers_control: Optional[float] = None
    prob_down_if_sellers_control: Optional[float] = None
    prob_continues_if_value_migrating_up: Optional[float] = None
    
    # === ERROR HANDLING ===
    insufficient_data_reason: Optional[str] = None


@dataclass
class ScenarioOutcomes:
    """
    Outcomes for a specific entry scenario
    (Aggressive, Moderate, Conservative)
    """
    scenario_type: str  # AGGRESSIVE, MODERATE, CONSERVATIVE
    
    # Entry characteristics
    entry_price: float
    confirmation_level: str  # NONE, PARTIAL, FULL
    
    # Probabilities
    win_probability: float
    drawdown_probability: float
    
    # Expected outcomes
    expected_gain: float
    expected_loss: float
    expected_value: float
    
    # Risk metrics
    risk_reward_ratio: float
    kelly_fraction: float
    
    # Timing
    expected_hold_days: int
