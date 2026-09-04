"""
VANGUARD Auction Schemas
Output data structures from Layer 1 - Auction Intelligence
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd


@dataclass
class MarketProfile:
    """
    Market Profile output (TPO chart analysis)
    """
    poc: Optional[float]  # Point of Control (highest volume price)
    value_area_high: Optional[float]  # Top of value area (70% volume)
    value_area_low: Optional[float]  # Bottom of value area
    
    profile_type: str  # NORMAL, P_SHAPED, B_SHAPED, TREND
    balance: str  # BALANCED, BUYER_DOMINATED, SELLER_DOMINATED
    
    # TPO counts by price
    tpo_distribution: Dict[float, int] = field(default_factory=dict)
    
    # Metadata
    timestamp: pd.Timestamp = None
    timeframe: str = "1D"  # 1D, 1W, etc.


@dataclass
class VolumeQuality:
    """
    Volume characteristics at a specific price level
    """
    absolute: float  # Actual volume at this level
    relative: float  # Relative to average (1.0 = average)
    quality: str  # HIGH, NORMAL, LOW


@dataclass
class TimeQuality:
    """
    Time spent at a specific price level
    """
    bars_at_level: int  # Number of bars at this price
    quality: str  # EXTENDED, MODERATE, BRIEF


@dataclass
class FlowBalance:
    """
    Buy/Sell flow balance at a price level
    """
    buy_volume: float
    sell_volume: float
    ratio: float  # buy / (buy + sell)
    quality: str  # BALANCED, SLIGHTLY_IMBALANCED, IMBALANCED


@dataclass
class ParticipantQuality:
    """
    Diversity of participants at a price level
    """
    unique_sizes: int  # Proxy for number of different participants
    quality: str  # DIVERSE, MODERATE, CONCENTRATED


@dataclass
class AcceptanceState:
    """
    Whether price is ACCEPTED or TOLERATED
    """
    level: float  # Price level being evaluated
    score: float  # 0-100 acceptance score
    classification: str  # ACCEPTED, TRANSITIONING, TOLERATED
    
    # Component scores
    position_in_profile: str  # INSIDE_VALUE, ABOVE_VALUE, BELOW_VALUE
    volume_quality: VolumeQuality = None
    time_quality: TimeQuality = None
    flow_quality: FlowBalance = None
    participant_quality: ParticipantQuality = None


@dataclass
class AggressionMetrics:
    """
    Who is taking liquidity aggressively?
    """
    buy_aggressive: float  # Volume of aggressive buying
    sell_aggressive: float  # Volume of aggressive selling
    buy_pct: float  # % of aggression that's buying
    sell_pct: float  # % of aggression that's selling
    interpretation: str  # BUYERS_AGGRESSIVE, SELLERS_AGGRESSIVE, BALANCED


@dataclass
class EfficiencyMetrics:
    """
    How efficiently is each side moving price?
    """
    price_change_pct: float  # % price change over period
    volume_used: float  # Volume required to achieve that change
    efficiency_score: float  # Price change per unit volume
    driver: str  # BUYERS, SELLERS, NEUTRAL


@dataclass
class VolumeTrend:
    """
    Is participation accelerating or decelerating?
    """
    buy_trend: float  # % change in buy volume (first half vs second half)
    sell_trend: float  # % change in sell volume
    interpretation: str  # BUYERS_ACCELERATING, SELLERS_ACCELERATING, STABLE


@dataclass
class ControlState:
    """
    Who controls the tape?
    """
    controller: str  # BUYERS, SELLERS, NEUTRAL
    confidence: float  # 0-1 confidence in control assessment
    
    # Component metrics
    aggression: AggressionMetrics = None
    efficiency: EfficiencyMetrics = None
    trend: VolumeTrend = None
    
    interpretation: str = ""  # Human-readable explanation


@dataclass
class MigrationState:
    """
    Is value migrating or holding?
    """
    direction: str  # UP, DOWN, SIDEWAYS
    speed: str  # FAST, MODERATE, SLOW
    consistency: str  # CONSISTENT_UP, CONSISTENT_DOWN, TRENDING, CHOPPY
    magnitude: float  # % change in value area center
    
    interpretation: str = ""


@dataclass
class AuctionVerdict:
    """
    Final synthesis from Layer 1
    Is the market READY to trade?
    """
    ready_to_trade: bool  # Can we trade this?
    confidence: float  # 0-1 confidence in verdict
    auction_state: str  # ALIGNED, SEARCHING, CONTESTED, CONFLICTED
    
    # Component outputs
    profile: MarketProfile = None
    acceptance: AcceptanceState = None
    control: ControlState = None
    migration: MigrationState = None
    
    # Reasoning
    reasoning: str = ""
    
    # For multi-scenario analysis (NEW)
    scenarios: Dict = field(default_factory=dict)
    # scenarios = {
    #     'immediate': {feasible, quality, risk_level, probability_estimate},
    #     'conditional_near': {trigger, probability_estimate},
    #     'conditional_far': {trigger, probability_estimate}
    # }
