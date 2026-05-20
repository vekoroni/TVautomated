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
    atr_pct_bucket: str = "MID"          # LOW / MID / HIGH  (from atr_percentile)
    adx_bucket: str = "MODERATE"         # WEAK / MODERATE / STRONG (from adx)
    intraday_rows: int = 0               # Number of intraday rows available
    # DEFECT 3 FIX: wyckoff_phase_bucket must be declared here so actuarial_query
    # Stage 1 getattr(state, "wyckoff_phase_bucket", None) resolves correctly.
    # Without this field, the Wyckoff dimension in the 9-dim hash is silently dead.
    # ACCUMULATION (phases A/B/C) | MARKUP (phases D/E) | DISTRIBUTION | UNKNOWN
    wyckoff_phase_bucket: str = "UNKNOWN"

    # === 9-DIM MATCH DIMENSIONS (added 2026-05-20) ===
    # iv_regime: realized-vol proxy for implied volatility regime.
    # LOW_IV | NORMAL_IV | ELEVATED_IV | HIGH_IV
    # Computed by state_calculator from vol_regime + atr_percentile.
    iv_regime: str = "NORMAL_IV"

    # crabel_state: daily-bar proxy for Crabel inside-bar compression.
    # CRABEL_READY | COILING | NONE
    # Computed by state_calculator; overridden from discovery pipeline when available.
    crabel_state: str = "NONE"

    # volume_bucket: relative volume vs 20-day average.
    # LOW | NORMAL | HIGH | SPIKE
    # Computed by state_calculator from relative_volume field.
    volume_bucket: str = "NORMAL"

    # horizon_bucket: preferred outcome horizon for this setup.
    # SHORT | MEDIUM | LONG
    # Routing-layer label; passed through from discovery pipeline when set.
    horizon_bucket: str = "MEDIUM"

    # === SCHEMA VERSIONING ===
    # Written to every signal row for audit traceability.
    # Allows post-hoc debugging: "did the live schema match the DB schema when this ran?"
    # Increment SCHEMA_VERSION in state_calculator.py when hash dimensions change.
    # Increment BUCKET_SCHEMA_VERSION when ADX/ATR bucket boundaries change.
    schema_version: str = "2.2.0"           # Hash dimension schema (9-dim)
    bucket_schema_version: str = "1.1.0"    # Bucket boundary schema

    # === META ===
    state_hash: str = ""            # Unique identifier for similarity matching
    confidence: float = 1.0        # 0-1, confidence in state measurement

    # =========================================================================
    # STATE V2 FIELDS — Sprint 1/2 (2026-05)
    # Computed by state_calculator.py V2 patch.
    # Used by: actuarial_query Stage 0, edge_detector signal override,
    #          position_sizing_engine signal_type sizing.
    # All fields have safe defaults — fully backward compatible.
    # =========================================================================

    # Phase classification derived from atr_percentile, adx, bb_percentile, rsi
    # EARLY_TRANSITION | CONTINUATION | EXHAUSTION
    phase_v2: str = "EXHAUSTION"

    # Momentum strength bucket derived from (adx × atr_percentile) / 100
    # LOW | MID | HIGH | EXTREME
    momentum_bucket: str = "LOW"

    # Price location relative to 52w range
    # NEAR_HIGH | NEAR_LOW | MID_RANGE | TRANSITION_ZONE
    location_bucket: str = "TRANSITION_ZONE"

    # Raw momentum score stored for DB logging and forward-momentum comparison
    momentum_score: float = 0.0

    # True when phase_v2 == EARLY_TRANSITION — fast boolean for downstream gates
    transition_flag_v2: bool = False

    # Enriched composite hash including V2 dimensions, for actuarial Stage 0 matching
    # Format: "vol_regime|trend_dir|structure|phase_v2|momentum_bucket|location_bucket"
    state_v2: str = ""

    # Pre-participation / before-the-herd candidate flag.
    # Mirrors add_early_candidate.py:
    #   MID momentum + MID_RANGE or NEAR_LOW location + EARLY_TRANSITION phase.
    # Stored as int for CSV/parquet compatibility: 1 = early candidate, 0 = not.
    early_candidate: int = 0

    # Advisory-only positional context used by EdgeDetector rationale.
    # It is not a capital-allocation or sizing gate.
    positional_strategy: bool = True


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

    # ── SPRINT 2: Signal classification ──────────────────────────────────────
    # Set by actuarial_query Stage 0 V2 matching.
    # CONTINUATION | TRANSITION | NO_EDGE
    # Declared here so serialisation, dataclass copying, and EIL consumers
    # all see it without relying on dynamic attribute attachment.
    signal_type: str = "NO_EDGE"

    # Forward momentum confidence (0.0–1.0) — computed from DB momentum_delta
    # distribution of matching rows. Higher = more rows had accelerating momentum.
    # 0.0 when DB lacks forward momentum columns or Stage 0 did not fire.
    forward_momentum_confidence: float = 0.0

    # Momentum tier returned by actuarial_query Stage 0 V2 matching.
    # TIER_1_EXPLOSIVE | TIER_2_SUSTAINING | TIER_3_BUILDING | TIER_4_FLAT
    momentum_tier: str = "TIER_4_FLAT"

    # === MATCH LADDER AUDIT FIELDS ===
    # Carried from ActuarialQueryEngine._tag_match() into Layer 2 output.
    state_match_method: str = "UNKNOWN"
    state_match_stage: str = "UNKNOWN"
    state_match_dimensions: str = ""
    state_match_quality: str = "UNKNOWN"
    state_match_similarity: float = 0.0
    state_match_is_exact: bool = False
    sample_size: int = 0
    sample_confidence_bucket: str = "UNKNOWN"
    confidence_penalty: float = 0.30
    confidence_weight: float = 0.30
    matched_state_key: str = ""
    original_state_key: str = ""
    fallback_reason: str = ""

    # === PROBABILITY CALIBRATION FIELDS ===
    raw_prob_up_5d: float = 0.0
    raw_prob_up_10d: float = 0.0
    raw_prob_up_20d: float = 0.0
    raw_prob_down_5d: float = 0.0
    raw_prob_down_10d: float = 0.0
    raw_prob_down_20d: float = 0.0
    raw_prob_target_hit: float = 0.0
    raw_prob_stop_hit: float = 0.0
    raw_expected_return: float = 0.0
    raw_expected_drawdown: float = 0.0
    raw_expected_time_to_target: float = 0.0
    baseline_probability: float = 0.0
    adjusted_prob_target_hit: float = 0.0
    adjusted_expected_return: float = 0.0
    probability_edge: float = 0.0
    probability_verdict: str = "NO_STAT_EDGE"

    # === V6 FUTURE BUCKET INTELLIGENCE ===
    # Derived from matched historical rows using future_momentum_bucket column.
    # Core v6 bridge: current state_v2/momentum_bucket/location_bucket
    #   -> dominant future_momentum_bucket distribution from DB history.
    future_momentum_bucket: Optional[str] = None
    future_momentum_bucket_distribution: Dict[str, float] = field(default_factory=dict)
    future_momentum_bucket_confidence: float = 0.0
    future_momentum_bucket_sample_size: int = 0

    # === V6 TRANSITION / DELTA DIAGNOSTICS ===
    # Computed from matched rows in _transition_delta_stats().
    # Used by EdgeDetector._bucket_edge_quality() and main.py print block.
    transition_flag_rate_v2: Optional[float] = None
    avg_momentum_delta: Optional[float] = None
    avg_atr_delta: Optional[float] = None
    avg_adx_delta: Optional[float] = None
    early_candidate_rate: Optional[float] = None

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
