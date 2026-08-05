"""
VANGUARD Configuration
All system parameters, thresholds, and settings
"""

# === SYSTEM SETTINGS ===
VANGUARD_VERSION = "1.0.0"
SYSTEM_NAME = "VANGUARD Intelligence Trading System"

# === DATA PATHS ===
HISTORICAL_DATA_PATH = "/data/vanguard/historical"
ACTUARIAL_DATABASE_PATH = r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet"
CACHE_PATH = "/data/vanguard/cache"
OUTPUT_PATH = "/data/vanguard/outputs"

# === LAYER 1: AUCTION INTELLIGENCE THRESHOLDS ===

# Market Profile
MARKET_PROFILE_CONFIG = {
    'tpo_interval_minutes': 30,  # 30-min TPO periods
    'value_area_percent': 0.70,  # 70% of volume = value area
    'min_bars_for_profile': 13,  # Minimum 6.5 hours of data (13 x 30min)
}

# Value Acceptance Detection
ACCEPTANCE_THRESHOLDS = {
    'volume_high_threshold': 1.5,      # >1.5x avg volume = HIGH acceptance
    'volume_normal_threshold': 0.8,    # >0.8x avg volume = NORMAL acceptance
    'time_extended_bars': 10,          # >10 bars at level = EXTENDED time
    'time_moderate_bars': 5,           # >5 bars at level = MODERATE time
    'flow_balanced_min': 0.45,         # 45-55% buy ratio = BALANCED
    'flow_balanced_max': 0.55,
    'flow_slightly_imbalanced_min': 0.40,
    'flow_slightly_imbalanced_max': 0.60,
    'participants_diverse_threshold': 20,      # >20 unique sizes = DIVERSE
    'participants_moderate_threshold': 10,     # >10 unique sizes = MODERATE
    
    # Acceptance score thresholds
    'acceptance_score_accepted': 75,           # >=75 = ACCEPTED
    'acceptance_score_transitioning': 50,      # >=50 = TRANSITIONING
    # <50 = TOLERATED
}

# Control Identification
CONTROL_THRESHOLDS = {
    'aggression_buyer_threshold': 0.60,        # >60% buy aggression = buyers aggressive
    'aggression_seller_threshold': 0.60,       # >60% sell aggression = sellers aggressive
    'control_strong_threshold': 0.65,          # >65% = strong control
    'control_moderate_threshold': 0.55,        # >55% = moderate control
    'volume_trend_acceleration': 0.20,         # >20% volume increase = accelerating
}

# Value Migration
MIGRATION_THRESHOLDS = {
    'migration_significant_percent': 0.03,     # >3% POC movement = significant
    'migration_fast_daily_percent': 0.01,      # >1% per day = fast migration
    'migration_moderate_daily_percent': 0.005, # >0.5% per day = moderate
}

# Auction Verdict (Synthesizer)
AUCTION_VERDICT_THRESHOLDS = {
    'ready_min_acceptance_score': 50,          # Minimum 50 acceptance score
    'ready_min_control_confidence': 0.65,      # Minimum 65% control confidence
    'ready_allow_choppy_migration': False,     # Block if migration is choppy
}

# === LAYER 2: STATISTICAL EDGE THRESHOLDS ===

# Volatility Regime
VOLATILITY_THRESHOLDS = {
    'compression_percentile': 20,      # <20th percentile = COMPRESSION
    'expansion_percentile': 80,        # >80th percentile = EXPANSION
    'atr_weight': 0.33,                # Weight for ATR in regime calculation
    'bb_weight': 0.33,                 # Weight for BB width
    'iv_weight': 0.34,                 # Weight for IV
}

# Trend Maturity
TREND_THRESHOLDS = {
    'uptrend_adx_min': 25,             # ADX >25 for trend confirmation
    'late_trend_percent_from_extreme': 0.05,   # Within 5% of 52w high/low = LATE
    'early_trend_days_from_extreme': 30,       # <30 days from extreme = EARLY
}

# Structure Quality
STRUCTURE_THRESHOLDS = {
    'strong_quality_score': 75,        # >=75 = STRONG structure
    'neutral_quality_score': 50,       # >=50 = NEUTRAL structure
    # <50 = WEAK structure
}

# Edge Detection
EDGE_DETECTION_THRESHOLDS = {
    'min_expected_value': 0.03,        # 3% minimum EV
    'min_probability_target': 0.45,    # 45% minimum win probability
    'min_data_confidence': 0.70,       # 70% minimum confidence in historical data
    'max_drawdown_tolerance': 0.10,    # 10% maximum acceptable drawdown
    'min_sharpe_ratio': 0.5,           # 0.5 minimum Sharpe ratio
    'min_observations': 30,            # Minimum 30 historical observations
    'optimal_observations': 100,       # Optimal 100+ observations
}

# State Matching (for actuarial query)
STATE_MATCHING_TOLERANCE = {
    'default_tolerance': 0.10,         # 10% tolerance for numeric fields
    'wide_tolerance': 0.15,            # 15% tolerance if few matches found
    'min_matches_before_widening': 30, # Widen tolerance if <30 matches
}

# === LAYER 3: EXECUTION INTELLIGENCE ===

# Scenario Probabilities (Multi-Scenario Analysis)
SCENARIO_PROBABILITIES = {
    # Aggressive (pre-confirmation)
    'aggressive_base_probability': 0.45,       # Base 45% if no confirmation
    'aggressive_probability_boost_per_signal': 0.05,  # +5% per supporting signal
    
    # Moderate (partial confirmation)
    'moderate_base_probability': 0.60,         # Base 60% with partial confirmation
    'moderate_probability_boost_per_signal': 0.03,
    
    # Conservative (full confirmation)
    'conservative_base_probability': 0.75,     # Base 75% with full confirmation
    'conservative_probability_boost_per_signal': 0.02,
    
    'max_probability': 0.90,                   # Cap at 90% (never 100%)
}

# Entry Zones
ENTRY_THRESHOLDS = {
    'immediate_entry_tight_range': 0.005,      # ±0.5% for immediate entries
    'immediate_entry_normal_range': 0.01,      # ±1% for immediate entries
    'limit_entry_range': 0.02,                 # ±2% for limit entries
    'conditional_entry_range': 0.005,          # ±0.5% for conditional triggers
}

# Stop Loss
STOP_LOSS_CONFIG = {
    'statistical_stop_multiplier': 1.5,        # 1.5x median max drawdown
    'structural_stop_buffer': 0.01,            # 1% below structural level
    'auction_stop_buffer': 0.015,              # 1.5% below auction level
    'min_stop_distance_percent': 0.02,         # Minimum 2% stop distance
    'max_stop_distance_percent': 0.10,         # Maximum 10% stop distance
}

# Targets
TARGET_CONFIG = {
    'target_1_multiplier': 1.0,                # T1 = median gain if up
    'target_2_multiplier': 1.5,                # T2 = 1.5x median gain
    'min_target_distance_percent': 0.03,       # Minimum 3% target distance
    'scale_out_t1_percent': 0.50,              # Exit 50% at T1
    'scale_out_t2_percent': 0.50,              # Exit 50% at T2
}

# Position Sizing
POSITION_SIZING_CONFIG = {
    'use_half_kelly': True,                    # Use 50% of Kelly for safety
    'kelly_safety_factor': 0.5,                # Kelly multiplier
    'max_position_size': 0.15,                 # Maximum 15% of capital per trade
    'max_position_size_high_confidence': 0.20, # Maximum 20% if very confident
    'min_position_size': 0.05,                 # Minimum 5% to make trade worthwhile
    
    # Scenario-specific sizing adjustments
    'aggressive_sizing_factor': 0.70,          # 70% of calculated Kelly (more risk)
    'moderate_sizing_factor': 1.00,            # 100% of calculated Kelly
    'conservative_sizing_factor': 1.20,        # 120% of calculated Kelly (less risk)
}

# Options Strategy
OPTIONS_CONFIG = {
    'dte_buffer_days': 5,                      # Add 5 days to hold period for buffer
    'dte_weekly_threshold': 7,                 # <=7 days = weekly expiration
    'dte_monthly_threshold': 30,               # <=30 days = monthly expiration
    
    # Strike selection
    'compression_otm_percent': 0.02,           # 2% OTM if in compression
    'normal_atm_range': 0.01,                  # ±1% for ATM selection
    
    # Premium estimation (rough)
    'estimated_premium_percent': 0.03,         # ~3% of stock price
}

# Time Limits
TIME_LIMITS_CONFIG = {
    'earnings_exit_buffer_days': 2,            # Exit 2 days before earnings
    'max_hold_days_default': 20,               # Default 20 days max hold
    'time_stop_no_progress_days': 10,          # Exit if no progress in 10 days
}

# === OUTPUT & REPORTING ===

# Signal Filtering
SIGNAL_FILTERING = {
    'min_right_side_score': 50,                # Minimum 50/100 right side score
    'max_signals_per_day': 20,                 # Top 20 signals max
    'tier_1_min_confidence': 0.80,             # Tier 1: >80% confidence
    'tier_2_min_confidence': 0.65,             # Tier 2: >65% confidence
    'tier_3_min_confidence': 0.50,             # Tier 3: >50% confidence
}

# Report Generation
REPORT_CONFIG = {
    'include_full_analysis': True,
    'include_charts': False,  # Set True when chart generation implemented
    'include_historical_context': True,
    'max_tickers_in_report': 20,
}

# === UNIVERSE & FILTERING ===

# Ticker Universe
UNIVERSE_CONFIG = {
    'min_price': 10.0,                         # Minimum $10 stock price
    'max_price': 500.0,                        # Maximum $500 stock price
    'min_daily_volume': 500000,                # Minimum 500K shares daily volume
    'min_options_volume': 1000,                # Minimum 1K options contracts daily
    'exclude_sectors': [],                     # Sectors to exclude (empty = all included)
    'max_spread_percent': 0.02,                # Maximum 2% bid-ask spread
}

# === PERFORMANCE TRACKING ===

# Metrics
PERFORMANCE_METRICS = {
    'track_win_rate': True,
    'track_avg_win_loss': True,
    'track_expectancy': True,
    'track_sharpe': True,
    'track_max_drawdown': True,
    'track_by_scenario': True,                 # Track each scenario separately
}

# Targets (Success Metrics)
SUCCESS_TARGETS = {
    'target_win_rate': 0.90,                   # 90% win rate goal
    'min_acceptable_win_rate': 0.70,           # 70% minimum acceptable
    'target_sharpe': 2.0,                      # Sharpe >2.0 target
    'max_acceptable_drawdown': 0.15,           # 15% max drawdown tolerance
}

# === DEBUGGING & LOGGING ===

DEBUG_CONFIG = {
    'verbose_logging': True,
    'log_layer_outputs': True,
    'log_veto_gates': True,
    'save_intermediate_states': True,
    'log_level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
}

# === API & DATA SOURCES ===

# Polygon API
POLYGON_CONFIG = {
    'base_url': 'https://api.polygon.io',
    'rate_limit_per_minute': 100,
    'max_retries': 3,
    'timeout_seconds': 30,
}

# === ACTUARIAL DATABASE CONTRACT (v7; v6 field-name compatibility retained) ===
# Required compatibility columns that MUST exist in actuarial_database_v7.parquet.
# VanguardEngine._validate_actuarial_database_contract() checks these at startup.
# If any are missing, the engine refuses to start — prevents silent v5 fallback.

ACTUARIAL_DATABASE_FILENAME = "actuarial_database_v7.parquet"

REQUIRED_ACTUARIAL_V6_COLUMNS = [
    "schema_version",
    "bucket_schema_version",
    "phase_v2",
    "momentum_score",
    "momentum_bucket",
    "location_bucket",
    "state_v2",
    "momentum_next",
    "momentum_delta",
    "atr_next",
    "atr_delta",
    "adx_next",
    "adx_delta",
    "transition_flag_v2",
    "future_momentum_bucket",
    "outcome_5d_return",
    "outcome_10d_return",
    "outcome_20d_return",
    "outcome_max_drawdown_20d",
    "outcome_hit_10pct_up",
    "outcome_hit_5pct_down_before_10up",
    "outcome_days_to_10pct",
]

OPTIONAL_ACTUARIAL_V6_COLUMNS = [
    "early_candidate",  # May be absent if add_early_candidate.py ran before v6 build
]

# === BACKTESTING ===

BACKTEST_CONFIG = {
    'start_date': '2015-01-01',
    'end_date': '2025-12-31',
    'initial_capital': 100000,
    'commission_per_trade': 1.0,               # $1 per contract
    'slippage_percent': 0.001,                 # 0.1% slippage
}
