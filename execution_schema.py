"""
AVSHUNTER — Execution Intelligence Layer Schemas
=================================================
Version : 3.0.0
Date    : 2026-04-12
Broker  : Tastytrade (live)
Instruments: Equities, Options, ETFs

CHANGES FROM v2.0.0
--------------------
- Added ev_v2, ev_net, ev_score, ev_confidence to ExecutionVerdict
  (written by EVEngineV2 — single EV authority)
- Added ev_v2_raw to ExecutionContext for pass-through audit
- _choose_ev() fallback fields DEPRECATED — do not add them back
- schema_version bumped to 3.0.0

IMPORTANT — LIVE CAPITAL IN USE
All changes to verdict logic must be reviewed before deploying to the
orchestrator. The EIL is advisory by default (eil_advisory_only=True).
Set to False only after explicit operator sign-off.
"""

from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional
from datetime import datetime


# ── LIQUIDITY WINDOW CONSTANTS ────────────────────────────────────────────────
OPTIMAL_WINDOW_START_ET  = (10, 15)
OPTIMAL_WINDOW_END_ET    = (15, 30)
WIDE_SPREAD_OPEN_END_ET  = (10, 15)
WIDE_SPREAD_CLOSE_START  = (15, 30)

# ── IV DISTORTION CONSTANTS ───────────────────────────────────────────────────
IV_DISTORTION_THRESHOLD_ABS  = 3.0
IV_DISTORTION_THRESHOLD_REL  = 1.08
IV_THIN_NAME_OI_THRESHOLD    = 500

# ── OBI CONSTANTS ─────────────────────────────────────────────────────────────
OBI_BULLISH_THRESHOLD = 0.65
OBI_BEARISH_THRESHOLD = 0.35

# ── POC CONSTANTS ─────────────────────────────────────────────────────────────
POC_AT_THRESHOLD       = 0.005
POC_EXTENDED_THRESHOLD = 0.020

# ── EIL COMPOSITE SCORE THRESHOLDS ───────────────────────────────────────────
SCORE_EXECUTE_NOW        = 85
SCORE_EXECUTE_CAUTION    = 65
SCORE_EXECUTE_DEFER      = 40

# ── EV ENGINE v2 THRESHOLDS (new in schema v3.0) ─────────────────────────────
EV_BLOCK_HARD       = -0.10   # ev_v2 < this → always BLOCK. Aligned with EVEngineV2
                               # WEAK_PASS/FAIL boundary (PATCH-07). ev_final is now
                               # regime-free so -0.10 is the genuine structural fail line.
EV_SKIP_THRESHOLD   = 0.00    # ev_v2 < this → SKIP (overrideable by percentile gate)
EV_SMALL_THRESHOLD  = 1.00    # ev_v2 < this → SMALL
EV_STANDARD_MAX     = 1.30    # ev_v2 < this → STANDARD; else MAX

# ── STRATEGY WEIGHTS (must sum to 1.0) ───────────────────────────────────────
# POSITIONAL STRATEGY WEIGHTS (1-20 day long calls/puts)
# S1 Liquidity  0.50 — spread at entry is the primary execution risk for positional trades
# S2 IV         0.40 — buying expensive vol destroys EV; critical for long options
# S3 GEX        0.05 — intraday noise; minimal weight, retained to avoid zero-division
# S4 OBI        0.03 — intraday only; near-zero weight
# S5 POC        0.02 — intraday timing; near-zero weight
# Sum = 1.00. To revert to intraday weights: 0.30 / 0.20 / 0.20 / 0.20 / 0.10
WEIGHT_LIQUIDITY  = 0.50
WEIGHT_IV         = 0.40
WEIGHT_GEX        = 0.05
WEIGHT_OBI        = 0.03
WEIGHT_POC        = 0.02


# ── GOVERNED TRIGGER HANDOFF (WS2) ──────────────────────────────────────────
# Trigger classification is calculated before EIL and commuted unchanged
# through execution_v3_5, the EOD opportunity book, Morning Gate and the Lab.
# Numeric scores are telemetry; they must never stand in for a categorical
# primary/quality value.
TRIGGER_HANDOFF_SCHEMA_VERSION = "trigger_handoff_v1"
TRIGGER_HANDOFF_FIELDS = (
    "trigger_codes",
    "trigger_count",
    "trigger_primary",
    "trigger_quality",
    "trigger_score",
    "trigger_go_eligible",
    "trigger_stale",
    "trigger_freshness_state",
    "trigger_data_asof",
)
TRIGGER_QUALITY_STATES = frozenset({"STRONG", "SINGLE", "NONE"})
TRIGGER_BOOLEAN_STATES = frozenset({"TRUE", "FALSE", "1", "0", "YES", "NO"})


def _categorical_trigger_value(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be a governed categorical string")
    text = str(value).strip()
    if not text or text.upper() in {"NAN", "NULL", "N/A"}:
        raise ValueError(f"{field} must be populated")
    try:
        float(text)
    except (TypeError, ValueError):
        return text.upper()
    raise ValueError(f"{field} must be categorical, not numeric: {text!r}")


def validate_trigger_handoff_row(row: Mapping[str, object]) -> None:
    """Fail closed when the WS2 trigger block is missing or type-corrupted."""
    missing = [field for field in TRIGGER_HANDOFF_FIELDS if field not in row]
    if missing:
        raise ValueError(f"trigger handoff missing fields: {missing}")

    primary = _categorical_trigger_value(row, "trigger_primary")
    quality = _categorical_trigger_value(row, "trigger_quality")
    _categorical_trigger_value(row, "trigger_codes")
    if quality not in TRIGGER_QUALITY_STATES:
        raise ValueError(f"trigger_quality is outside the governed domain: {quality!r}")
    if primary == "NONE" and quality != "NONE":
        raise ValueError("trigger_primary NONE requires trigger_quality NONE")

    for field in ("trigger_count", "trigger_score"):
        try:
            number = float(row.get(field))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be numeric") from exc
        if number != number:
            raise ValueError(f"{field} must not be NaN")

    for field in ("trigger_go_eligible", "trigger_stale"):
        value = row.get(field)
        if not isinstance(value, bool) and str(value).strip().upper() not in TRIGGER_BOOLEAN_STATES:
            raise ValueError(f"{field} must be boolean")


@dataclass
class ExecutionContext:
    """
    Live microstructure data gathered at execution-check time.
    Populated by the EIL runner immediately before verdict calculation.
    All prices in USD. All timestamps UTC-aware or naive ET (documented per field).
    """

    # ── Signal metadata ──────────────────────────────────────────────────────
    ticker: str
    signal_time: datetime
    superbrain_verdict: str
    wbs_grade: str
    wbs_score: float
    signal_direction: str

    # ── Live price ───────────────────────────────────────────────────────────
    current_price: float
    check_time: datetime

    # ── Options contract data ────────────────────────────────────────────────
    options_symbol: Optional[str]        = None
    options_bid: Optional[float]         = None
    options_ask: Optional[float]         = None
    options_mid: Optional[float]         = None
    options_open_interest: Optional[int] = None

    # ── Implied volatility ───────────────────────────────────────────────────
    iv_bid: Optional[float]              = None
    iv_mid: Optional[float]              = None
    iv_ask: Optional[float]              = None

    # ── Top-of-book size ─────────────────────────────────────────────────────
    l2_bid_size: Optional[float]         = None
    l2_ask_size: Optional[float]         = None

    # ── GEX by strike ────────────────────────────────────────────────────────
    gex_by_strike: Dict[float, float]    = field(default_factory=dict)

    # ── Volume profile POC ───────────────────────────────────────────────────
    poc_price: Optional[float]           = None
    price_vs_poc_existing: Optional[float] = None

    # ── Actuarial / structural context ───────────────────────────────────────
    adx_value: Optional[float]           = None
    expected_move_pct: Optional[float]   = None

    # ── EVEngineV2 outputs (pass-through audit — v3.0) ───────────────────────
    # Set by runner after EVEngineV2.evaluate(); available to strategies
    # that need EV context (e.g. liquidity_gate EV-aware spread gate).
    ev_v2_raw: Optional[float]           = None   # ev_final from EVEngineV2
    ev_net: Optional[float]              = None   # ev after cost deduction
    ev_score: Optional[float]            = None   # normalised 0–100

    # ── Advisory flag ────────────────────────────────────────────────────────
    eil_advisory_only: bool              = True


@dataclass
class StrategyResult:
    """Output of a single EIL strategy."""
    strategy_name: str
    score: float
    passed: bool
    verdict: str
    detail: str
    size_multiplier: float
    block: bool = False


@dataclass
class ExecutionVerdict:
    """
    Final output of the Execution Intelligence Layer.
    Appended as additional columns to superbrain_enriched CSV.
    Does NOT modify any existing Superbrain or Vanguard fields.

    EV FIELDS (new in v3.0 — from EVEngineV2, the single EV authority)
    -------------------------------------------------------------------
    eil_ev_v2          — raw ev_final from EVEngineV2
    eil_ev_net         — ev after trading cost deduction
    eil_ev_score       — normalised 0–100 for human readability
    eil_ev_confidence  — model confidence in EV estimate (0–1)

    DEPRECATED (removed in v3.0 — do NOT re-add)
    ---------------------------------------------
    Any field sourced from: ev / ev_final / ev_option / ev_regime /
    ev_net (old) / expected_value_20d — these were _choose_ev() inputs.
    The runner no longer reads them.
    """

    # ── Composite verdict ────────────────────────────────────────────────────
    eil_verdict: str
    eil_raw_verdict: str
    eil_composite_score: float
    eil_advisory_only: bool

    # ── EVEngineV2 outputs (single EV authority — v3.0) ──────────────────────
    eil_ev_v2: float = 0.0              # Raw ev_final from EVEngineV2
    eil_ev_net: float = 0.0             # After cost deduction
    eil_ev_score: float = 0.0           # Normalised 0–100
    eil_ev_confidence: float = 0.0      # Model confidence 0–1

    # ── Strategy sub-verdicts ────────────────────────────────────────────────
    eil_liquidity_window: str = "UNKNOWN"
    eil_liquidity_score: float = 0.0
    eil_liquidity_passed: bool = False

    eil_iv_ask_premium: float = 0.0
    eil_iv_distortion_flag: bool = False
    eil_iv_score: float = 0.0
    eil_iv_passed: bool = False
    eil_iv_tailwind_score: float = 0.0

    eil_gex_regime: str = "NEUTRAL"
    eil_gex_flip_level: Optional[float] = None
    eil_gex_proximity_pct: float = 0.0
    eil_gex_score: float = 0.0
    eil_gex_passed: bool = False

    eil_obi_score_raw: float = 0.5
    eil_obi_regime: str = "NEUTRAL"
    eil_obi_score: float = 0.0
    eil_obi_passed: bool = False

    eil_poc_proximity_pct: float = 0.0
    eil_poc_position: str = "NO_POC_DATA"
    eil_poc_score: float = 0.0
    eil_poc_passed: bool = False

    # ── Execution guidance ───────────────────────────────────────────────────
    eil_size_multiplier: float = 1.0
    eil_defer_reason: Optional[str] = None
    eil_recommended_entry_window: Optional[str] = None
    eil_spread_pct_live: Optional[float] = None

    # ── Final monetisation decision (from runner — v3.0) ─────────────────────
    eil_final_action: str = "SKIP"      # SKIP | SMALL | STANDARD | MAX
    eil_final_size: float = 0.0         # Position size after all adjustments
    eil_percentile_override: bool = False  # True if top-30% gate released this trade

    # ── Audit ────────────────────────────────────────────────────────────────
    eil_check_timestamp: str = ""
    eil_schema_version: str = "3.0.0"
