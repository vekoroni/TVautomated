"""
VANGUARD Input Schemas
Defines data structures for inputs to VANGUARD system
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd


@dataclass
class CalendarData:
    """
    Time-sensitive catalysts and events
    """
    # Earnings
    next_earnings_date: Optional[datetime] = None
    days_to_earnings: Optional[int] = None
    earnings_time: Optional[str] = None  # BMO, AMC, or specific time
    
    # Company Events
    events: List[Dict] = field(default_factory=list)  # [{type, date, description}]
    
    # Sector Context
    sector: Optional[str] = None
    sector_momentum: Optional[float] = None  # -1 to +1 scale


@dataclass
class OptionsData:
    """
    Options intelligence from existing pipelines
    """
    # UOA (Unusual Options Activity)
    uoa: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: underlying, option_symbol, right, strike, dte, delta, 
    #          oi, volume, notional_buy, notional_sell, notional_net, etc.
    
    # GEX (Gamma Exposure)
    gex_by_strike: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: strike, gex
    
    # IV Data
    iv_term_structure: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: expiration_key, iv_median, dte, n
    
    smile_proxy: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: strike, iv, delta, etc.
    
    # Vanna/Charm
    vanna_charm: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: strike, vanna_proxy, charm_proxy
    
    # Context
    daily_dollar_volume: float = 0.0
    total_options_volume: int = 0


@dataclass
class TechnicalData:
    """
    Price and indicator data across timeframes
    """
    # Price History (for Market Profile and indicators)
    ohlcv: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: timestamp, open, high, low, close, volume
    # Timeframes: 1m, 5m, 15m, 1h, 4h, 1D, 1W
    
    # Current Indicators
    vwap_15m: float = 0.0
    vwap_1h: float = 0.0
    vwap_4h: float = 0.0
    vwap_daily: float = 0.0
    
    ema9: float = 0.0
    ema21: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    
    atr_current: float = 0.0
    atr_history: List[float] = field(default_factory=list)  # Last 90 days for percentile
    
    adx: float = 0.0
    rsi: float = 0.0
    
    # Bollinger Bands
    bb_upper: float = 0.0
    bb_mid: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    bb_width_history: List[float] = field(default_factory=list)  # For percentile
    
    # Keltner Channels
    keltner_upper: float = 0.0
    keltner_mid: float = 0.0
    keltner_lower: float = 0.0
    
    # Volume Profile (for Layer 1 - Auction)
    volume_profile: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: price_level, volume, buys, sells
    
    # Support/Resistance
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    
    # Failed Breakout Tracking
    failed_breakout_count: int = 0
    last_breakout_attempt_date: Optional[datetime] = None
    
    # 52-week high/low
    high_52w: float = 0.0
    low_52w: float = 0.0
    date_52w_high: Optional[datetime] = None
    date_52w_low: Optional[datetime] = None
    
    # Trend length
    trend_length_days: int = 0
    
    # Wyckoff Context (if available from existing analysis)
    wyckoff_phase: Optional[str] = None  # A, B, C, D, E or accumulation/distribution
    wyckoff_events: List[str] = field(default_factory=list)  # PS, SC, AR, ST, Spring, etc.
    
    # Intraday Market Profile (from real-time 5-min data)
    intraday_position: str = 'UNKNOWN'
    volume_profile_context: str = 'BALANCED'
    control_dynamics: str = 'NEUTRAL'
    intraday_support: float = 0.0
    intraday_resistance: float = 0.0


@dataclass
class MicrostructureData:
    """
    Tape and order flow data (if available)
    """
    # NOII (Net Order Imbalance Indicator)
    noii: Dict = field(default_factory=dict)
    # Keys: status, paired_shares, imbalance, direction
    # status: "NO_CROSSING_ELIGIBLE" or "ACTIVE"
    
    # Time & Sales Pattern (from existing analysis or calculated)
    tns: Dict = field(default_factory=dict)
    # Keys: pattern, confidence, interpretation
    # pattern: "ACCUMULATION", "DISTRIBUTION", "PINNING", "SWEEPS", etc.
    
    # Dark Pool (if available)
    dark_pool: Optional[Dict] = None
    # Keys: prints_count, total_size, avg_print_size, sentiment
    
    # Block Trades
    blocks: Optional[List[Dict]] = None
    # List of: {timestamp, size, price, side}
    
    # Time & Sales raw data (for Control Identifier)
    time_and_sales: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Columns: timestamp, price, size, aggressor (BUY/SELL), bid, ask


@dataclass
class MacroData:
    """
    Market-wide context
    """
    vix: float = 0.0
    vix_history: List[float] = field(default_factory=list)  # For percentile
    
    spy_price: float = 0.0
    spy_trend: str = "UNKNOWN"  # UP, DOWN, SIDEWAYS
    
    sector_etf_price: float = 0.0
    sector_relative_strength: float = 0.0  # vs SPY


@dataclass
class VanguardInput:
    """
    Complete input package for VANGUARD analysis
    Assembled by Master Orchestrator
    """
    # === IDENTIFICATION ===
    ticker: str
    analysis_timestamp: datetime
    current_price: float
    
    # === DATA PACKAGES ===
    calendar: CalendarData
    options: OptionsData
    technical: TechnicalData
    microstructure: MicrostructureData
    macro: MacroData
    
    # === METADATA ===
    data_quality_score: float = 1.0  # 0-1, how complete is the data?
    missing_data_fields: List[str] = field(default_factory=list)
    
    # === OPTIONAL: AVSHUNTER OUTPUT (for comparison) ===
    avshunter_signal: Optional[Dict] = None
