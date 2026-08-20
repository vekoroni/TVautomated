"""
AVSHUNTER — Execution Intelligence Layer
Schemas: ExecutionContext (input) and ExecutionVerdict (output)

Version : 1.0.0
Date    : 2026-03-08
Broker  : Tastytrade (live)
Instruments: Equities, Options, ETFs

IMPORTANT — LIVE CAPITAL IN USE
All changes to verdict logic must be reviewed before deploying to the
orchestrator. The EIL is advisory by default (eil_advisory_only=True).
Set to False only after explicit operator sign-off.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


# ── LIQUIDITY WINDOW CONSTANTS ────────────────────────────────────────────────
# Eastern Time boundaries (naive — caller must ensure tz-aware comparison)
OPTIMAL_WINDOW_START_ET  = (10, 15)   # 10:15 AM ET
OPTIMAL_WINDOW_END_ET    = (15, 30)   # 03:30 PM ET
WIDE_SPREAD_OPEN_END_ET  = (10, 15)   # 09:30–10:15 ET
WIDE_SPREAD_CLOSE_START  = (15, 30)   # 03:30–04:00 ET

# ── IV DISTORTION CONSTANTS ───────────────────────────────────────────────────
IV_DISTORTION_THRESHOLD_ABS  = 3.0    # Vol points above mid-IV → flag
IV_DISTORTION_THRESHOLD_REL  = 1.08   # ask_IV / mid_IV ratio → flag (thin names)
IV_THIN_NAME_OI_THRESHOLD    = 500    # OI below this = use relative threshold

# ── OBI CONSTANTS ─────────────────────────────────────────────────────────────
OBI_BULLISH_THRESHOLD = 0.65   # OBI > this → bullish pressure
OBI_BEARISH_THRESHOLD = 0.35   # OBI < this → bearish pressure

# ── POC CONSTANTS ─────────────────────────────────────────────────────────────
POC_AT_THRESHOLD       = 0.005   # Within 0.5% of POC → AT_POC
POC_EXTENDED_THRESHOLD = 0.020   # Beyond 2.0% from POC → EXTENDED

# ── EIL COMPOSITE SCORE THRESHOLDS ───────────────────────────────────────────
SCORE_EXECUTE_NOW        = 85
SCORE_EXECUTE_CAUTION    = 65
SCORE_EXECUTE_DEFER      = 40
# Below SCORE_EXECUTE_DEFER → STAND_DOWN_MICROSTRUCTURE

# ── STRATEGY WEIGHTS (must sum to 1.0) ───────────────────────────────────────
WEIGHT_LIQUIDITY  = 0.30
WEIGHT_IV         = 0.20
WEIGHT_GEX        = 0.20
WEIGHT_OBI        = 0.20
WEIGHT_POC        = 0.10


@dataclass
class ExecutionContext:
    """
    Live microstructure data gathered at execution-check time.
    Populated by the EIL runner immediately before verdict calculation.
    All prices in USD. All timestamps UTC-aware or naive ET (documented per field).

    For Tastytrade live integration:
        - options_bid/ask/mid: from Tastytrade market data WebSocket or
          MarketData.app /v1/options/quotes/{symbol}/
        - iv_bid/iv_ask/iv_mid: from MarketData.app (pre-computed by their model)
        - l2_bid_size/l2_ask_size: from Polygon.io NBBO endpoint (top of book only)
          https://api.polygon.io/v2/last/nbbo/{ticker}
        - gex_by_strike: derived from MarketData.app option chain
          gamma × open_interest per strike
        - poc_price: from AVSHUNTER intraday volume profile (existing pipeline)
        - current_price: from Polygon.io last trade snapshot
    """

    # ── Signal metadata ──────────────────────────────────────────────────────
    ticker: str
    signal_time: datetime          # UTC timestamp when Superbrain emitted verdict
    superbrain_verdict: str        # EXECUTE | EXECUTE_WITH_RISK
    wbs_grade: str                 # IMMINENT | PROBABLE | POSSIBLE | UNLIKELY
    wbs_score: float               # 0–100 from Wall Break Scorer
    signal_direction: str          # LONG | SHORT (from discovery/swing layer)

    # ── Live price ───────────────────────────────────────────────────────────
    current_price: float           # Last trade price at execution check time
    check_time: datetime           # UTC timestamp of this microstructure check

    # ── Options contract data (MarketData.app) ───────────────────────────────
    options_symbol: Optional[str]  = None   # OCC symbol e.g. AAPL260320C00200000
    options_bid: Optional[float]   = None
    options_ask: Optional[float]   = None
    options_mid: Optional[float]   = None
    options_open_interest: Optional[int] = None

    # ── Implied volatility at bid/mid/ask (MarketData.app) ───────────────────
    iv_bid: Optional[float]        = None   # IV computed at bid price
    iv_mid: Optional[float]        = None   # IV computed at mid price
    iv_ask: Optional[float]        = None   # IV computed at ask price

    # ── Top-of-book size (Polygon.io NBBO — single level) ───────────────────
    l2_bid_size: Optional[float]   = None   # Shares at best bid (post Nov-2025: shares not lots)
    l2_ask_size: Optional[float]   = None   # Shares at best ask

    # ── GEX by strike (derived: gamma × OI per strike from MarketData.app) ──
    gex_by_strike: Dict[float, float] = field(default_factory=dict)

    # ── Volume profile POC (from existing AVSHUNTER intraday pipeline) ───────
    poc_price: Optional[float]     = None   # Point of Control from intraday volume profile
    price_vs_poc_existing: Optional[float] = None  # Existing StateVector field (% from POC)

    # ── Advisory flag ────────────────────────────────────────────────────────
    eil_advisory_only: bool        = True   # SAFETY: True = log only, never block fills
                                            # Set False only after operator sign-off


@dataclass
class StrategyResult:
    """
    Output of a single EIL strategy.
    All five strategies return this structure.
    """
    strategy_name: str
    score: float               # 0–100 contribution to composite
    passed: bool               # Did this strategy pass its threshold?
    verdict: str               # Strategy-specific verdict string
    detail: str                # Human-readable explanation
    size_multiplier: float     # 1.0 = full, 0.6 = scaled, 0.0 = blocked
    block: bool = False        # True = hard gate (overrides composite)


@dataclass
class ExecutionVerdict:
    """
    Final output of the Execution Intelligence Layer.
    Appended as additional columns to superbrain_enriched CSV.
    Does NOT modify any existing Superbrain or Vanguard fields.

    Column naming: all fields prefixed eil_ to prevent namespace collision.

    EIL VERDICTS:
        EXECUTE_NOW              — All checks passed. Optimal entry window.
        EXECUTE_WITH_CAUTION     — Minor friction. Proceed with noted conditions.
        EXECUTE_DEFER            — Wait for liquidity window or OBI confirmation.
        STAND_DOWN_MICROSTRUCTURE— Microstructure contra-indicates entry.
        ADVISORY_ONLY            — eil_advisory_only=True. Logged but not blocking.
        INSUFFICIENT_DATA        — Required fields missing. Cannot score.
    """

    # ── Composite verdict ────────────────────────────────────────────────────
    eil_verdict: str                    # See docstring above
    eil_composite_score: float          # 0–100 weighted composite
    eil_advisory_only: bool             # Mirrors ExecutionContext flag

    # ── Strategy sub-verdicts ────────────────────────────────────────────────
    eil_liquidity_window: str           # OPTIMAL_WINDOW | WIDE_SPREAD | CLOSED_AUCTION
    eil_liquidity_score: float
    eil_liquidity_passed: bool

    eil_iv_ask_premium: float           # Vol points above mid-IV at ask
    eil_iv_distortion_flag: bool        # True if premium exceeds threshold
    eil_iv_score: float
    eil_iv_passed: bool

    eil_gex_regime: str                 # AMPLIFYING | DAMPENING | NEUTRAL
    eil_gex_flip_level: Optional[float] # Price where GEX sign changes
    eil_gex_proximity_pct: float        # % distance from current price to flip level
    eil_gex_score: float
    eil_gex_passed: bool

    eil_obi_score_raw: float            # Raw OBI ratio 0.0–1.0
    eil_obi_regime: str                 # BULLISH | BEARISH | NEUTRAL
    eil_obi_score: float                # Normalised 0–100
    eil_obi_passed: bool

    eil_poc_proximity_pct: float        # % distance from POC
    eil_poc_position: str               # AT_POC | ABOVE_POC | BELOW_POC | EXTENDED
    eil_poc_score: float
    eil_poc_passed: bool

    # ── Execution guidance ───────────────────────────────────────────────────
    eil_size_multiplier: float          # Final position size multiplier
    eil_defer_reason: Optional[str]     # Why deferred/blocked (if applicable)
    eil_recommended_entry_window: Optional[str]  # e.g. "10:15 ET" or "OBI > 0.65"
    eil_spread_pct_live: Optional[float]         # Live bid/ask spread % (replaces hardcoded 50.0)

    # ── Audit ────────────────────────────────────────────────────────────────
    eil_check_timestamp: str            # ISO8601 UTC when EIL ran
    eil_schema_version: str = "1.0.0"
