"""
VANGUARD State & Outcomes Schemas
Layer 2 - Statistical Edge data structures

UPDATED: Added multi-horizon outcome fields (5d, 10d) for options layer
         compounding strategy. All new fields have defaults so existing
         callers are unaffected.
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
    distance_from_52w_low: float   # % from low (positive if above)
    days_since_52w_high: int
    trend_length_days: int
    trend_direction: str   # UP, DOWN, SIDEWAYS
    adx: float
    trend_maturity: str    # EARLY, MIDDLE, LATE, EXHAUSTED
    trend_strength_score: float

    # === STRUCTURE (Enhanced with Auction data) ===
    price_vs_vwap_1h: float        # % from VWAP
    price_vs_vwap_daily: float
    price_vs_poc: float            # % from Point of Control
    price_position_in_value: str   # ABOVE_VA, IN_VA, BELOW_VA
    value_acceptance_score: float  # From Layer 1 (0-100)
    failed_breakouts_20d: int
    control_state: str             # BUYERS, SELLERS, NEUTRAL (from Layer 1)
    control_confidence: float      # 0-1
    structure_quality: str         # STRONG, NEUTRAL, WEAK

    # === LIQUIDITY ===
    relative_volume: float         # vs 20D average
    spread_percentile: float
    liquidity_condition: str       # HIGH, NORMAL, LOW

    # === POSITIONING ===
    put_call_ratio: float
    put_call_oi_ratio: float
    options_skew: float            # -1 to +1
    net_gamma_exposure: float
    net_delta_exposure: float
    positioning_bias: str          # NET_LONG, NET_SHORT, NEUTRAL

    # === MACRO ===
    vix: float
    vix_percentile: float
    spy_trend: str
    sector_relative_strength: float
    macro_regime: str              # RISK_ON, RISK_OFF, TRANSITIONAL

    # === CATALYST ===
    days_to_earnings: int          # -1 if none scheduled
    earnings_window: str           # PRE_30D, PRE_20D, PRE_10D, POST, FAR
    days_since_earnings: int
    catalyst_proximity: str        # HIGH, MEDIUM, LOW, NONE

    # === AUCTION INTEGRATION (from Layer 1) ===
    value_migration_direction: str  # UP, DOWN, SIDEWAYS
    value_migration_speed: str      # FAST, MODERATE, SLOW
    auction_state: str              # ALIGNED, SEARCHING, CONTESTED

    # === INTRADAY MARKET PROFILE (Real-time context) ===
    intraday_position: str          # AT_SUPPORT, AT_RESISTANCE, NEAR_SUPPORT, IN_VALUE_AREA, OUT_OF_VALUE, UNKNOWN
    volume_profile_context: str     # ACCUMULATION, DISTRIBUTION, BALANCED, INSUFFICIENT_DATA
    control_dynamics: str           # BUYERS_STRENGTHENING, SELLERS_STRENGTHENING, NEUTRAL
    intraday_support: float         # Nearest support from volume profile
    intraday_resistance: float      # Nearest resistance from volume profile

    # === BUCKET DISCRIMINATORS ===
    # Computed by state_calculator, used by actuarial_query Stage 1 filter
    # Must match values stored in actuarial database bucket columns
    atr_pct_bucket: str = "MID"     # LOW / MID / HIGH  (from atr_percentile)
    adx_bucket: str = "MODERATE"    # WEAK / MODERATE / STRONG (from adx)
    intraday_rows: int = 0          # Number of intraday rows available

    # === META ===
    state_hash: str = ""            # Unique identifier for similarity matching
    confidence: float = 1.0        # 0-1, confidence in state measurement


@dataclass
class ActuarialOutcomes:
    """
    Historical probability distribution for a given state.
    Returned by ActuarialQueryEngine.query().

    MULTI-HORIZON: Now includes 5d and 10d outcome fields alongside
    existing 20d fields. Options layer uses the horizon that matches
    the signal's recommended_hold_days for accurate EV calculation.
    """
    # === SAMPLE METADATA ===
    n_observations: int            # How many historical instances?
    confidence_level: float        # 0-1 based on sample size
    lookback_period: str           # "3Y", "5Y", "10Y"

    # === CORE PROBABILITIES — 20-day horizon (original) ===
    prob_up_10pct_20d: float       # P(+10% within 20 days)
    prob_down_5pct_before_up_10pct: float  # P(drawdown >5% before target)
    prob_trend_continues_20d: float        # P(trend same direction)

    # === MAGNITUDE EXPECTATIONS — 20-day horizon (original) ===
    median_gain_if_up: float       # Median gain when it moves up
    median_loss_if_down: float     # Median loss when it moves down
    median_max_drawdown: float     # Median worst drawdown (20d)
    median_days_to_target: float   # Median time to reach +10%

    # === RISK-ADJUSTED METRICS ===
    expected_value_20d: float      # Expected value over 20 days
    sharpe_ratio: float            # Risk-adjusted return
    win_rate: float                # % of times return > 0 (20d)
    avg_win_loss_ratio: float      # Avg win / Avg loss

    # === EXECUTION ===
    kelly_fraction: float          # Optimal position size (Kelly criterion)
    recommended_hold_days: int     # Typical hold period from actuarial data

    # === DISTRIBUTION ===
    outcome_distribution: Dict[str, float] = field(default_factory=dict)

    # ─── NEW: 5-DAY HORIZON ───────────────────────────────────────────────────
    win_rate_5d: float = 0.0               # % of times 5d return > 0
    expected_value_5d: float = 0.0         # EV over 5 days
    prob_up_5pct_5d: float = 0.0           # P(+5% within 5 days)
    median_gain_if_up_5d: float = 0.0      # Median gain (5d winners)
    median_loss_if_down_5d: float = 0.0    # Median loss (5d losers)
    median_max_drawdown_5d: float = 0.0    # Median worst drawdown in 5d
    sharpe_ratio_5d: float = 0.0           # Risk-adjusted return (5d)

    # ─── NEW: 10-DAY HORIZON ──────────────────────────────────────────────────
    win_rate_10d: float = 0.0              # % of times 10d return > 0
    expected_value_10d: float = 0.0        # EV over 10 days
    prob_up_7pct_10d: float = 0.0          # P(+7% within 10 days)
    median_gain_if_up_10d: float = 0.0     # Median gain (10d winners)
    median_loss_if_down_10d: float = 0.0   # Median loss (10d losers)
    median_max_drawdown_10d: float = 0.0   # Median worst drawdown in 10d
    sharpe_ratio_10d: float = 0.0          # Risk-adjusted return (10d)

    # ─── OPTIONAL FIELDS (with defaults) ─────────────────────────────────────
    prob_breakout_if_compressed: Optional[float] = None

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

    # ─── CONVENIENCE: horizon-aware accessors ────────────────────────────────
    def win_rate_for_hold(self, hold_days: int) -> float:
        """Return the most appropriate win rate for a given hold period."""
        if hold_days <= 5:
            return self.win_rate_5d if self.win_rate_5d > 0 else self.win_rate
        elif hold_days <= 10:
            return self.win_rate_10d if self.win_rate_10d > 0 else self.win_rate
        else:
            return self.win_rate

    def expected_value_for_hold(self, hold_days: int) -> float:
        """Return the most appropriate EV for a given hold period."""
        if hold_days <= 5:
            return self.expected_value_5d if self.expected_value_5d != 0 else self.expected_value_20d
        elif hold_days <= 10:
            return self.expected_value_10d if self.expected_value_10d != 0 else self.expected_value_20d
        else:
            return self.expected_value_20d

    def median_gain_for_hold(self, hold_days: int) -> float:
        """Return median gain if up for the closest horizon."""
        if hold_days <= 5:
            return self.median_gain_if_up_5d if self.median_gain_if_up_5d > 0 else self.median_gain_if_up
        elif hold_days <= 10:
            return self.median_gain_if_up_10d if self.median_gain_if_up_10d > 0 else self.median_gain_if_up
        else:
            return self.median_gain_if_up

    def median_loss_for_hold(self, hold_days: int) -> float:
        """Return median loss if down for the closest horizon."""
        if hold_days <= 5:
            return self.median_loss_if_down_5d if self.median_loss_if_down_5d < 0 else self.median_loss_if_down
        elif hold_days <= 10:
            return self.median_loss_if_down_10d if self.median_loss_if_down_10d < 0 else self.median_loss_if_down
        else:
            return self.median_loss_if_down


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
