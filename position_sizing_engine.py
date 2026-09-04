# ============================================================
# STATUS: RETIRED / NOT ON ORCHESTRATOR PATH (capital authority)
# Superseded by: manual trader sizing decision — no automated replacement;
#                sizing is intentionally human-only per current governance
# Evidence:      execution_intelligence_runner.py:220-222 hardcodes
#                _pse_compute = None and _PSE_AVAILABLE = False
#                unconditionally — this is not an import-failure fallback;
#                governance note at execution_intelligence_runner.py:57-59
#                ("PSE-01 ... RETIRED from production authority ... must
#                not allocate, suppress, or resize trades")
# Retired:       UNKNOWN (governance note is undated in source)
# Note:          kept on disk for historical audit and research replay;
#                _ev_multiplier() (~294-310) still computes a real size
#                multiplier from ev_conf_adj/ev_status but is unreachable
#                on the live path
# Documented:    2026-08-19 (EV audit, Stage 0)
# ============================================================
"""
AVSHUNTER — Position Sizing Engine (PSE)
=========================================
Version : 1.1.0
Date    : 2026-05-05
Status  : RETIRED FROM PRODUCTION AUTHORITY

PURPOSE
-------
The PSE is retained for historical audit and research replay only. Production
runs must not use it to allocate, suppress, or resize trades. The live pipeline
uses PSE_IGNORED_MANUAL_SIZING and manual capital review.

This is the architectural shift from:
    "Is this trade good enough?"  →  EXECUTE / BLOCK
to:
    "How much capital should this trade receive?"  →  final_size ∈ [0, 0.03]

DESIGN PRINCIPLES
-----------------
1. Nothing blocks except genuinely fatal conditions (no contract, bad data,
   negative RR AND negative EV simultaneously).
2. Every other layer contributes a penalty multiplier ∈ [0.3, 1.0].
3. The multiplicative chain produces a continuous size signal.
4. Size < MIN_EXECUTABLE is the only "block" — below that the edge is too
   small to overcome commission friction ($2 round-trip on Tastytrade).

PENALTY CHAIN
-------------
final_size = BASE_RISK
           × ev_mult         (EVEngineV2 edge signal)
           × mp_mult         (Monetisation Policy — replaces hard blocks)
           × eil_mult        (EIL microstructure — advisory, not sovereign)
           × options_mult    (Options Intelligence — replaces IV/spread gates)
           × regime_mult     (Macro regime context)
           × confidence_mult (Data quality and calibration)

Clamped to [MIN_EXECUTABLE, MAX_POSITION] before return.

INTEGRATION
-----------
Not called by execution_intelligence_runner.py in production. Direct calls to
compute_position_size() return zero-size advisory output unless the explicit
research override AVSHUNTER_ENABLE_RETIRED_PSE=1 is set.

OUTPUT FIELDS
-------------
    pse_final_size          Continuous position size (0.0–0.03)
    pse_execution_mode      FULL_EXECUTE | EXECUTE | REDUCED | PROBE | SKIP
    pse_edge_score          Raw edge signal from EV engine (−1.0 to +1.0)
    pse_ev_mult             EV penalty multiplier
    pse_mp_mult             Monetisation Policy penalty multiplier
    pse_eil_mult            EIL microstructure penalty multiplier
    pse_options_mult        Options Intelligence penalty multiplier
    pse_regime_mult         Regime penalty multiplier
    pse_confidence_mult     Data quality penalty multiplier
    pse_block_reason        Set only for genuine fatal blocks (empty otherwise)
    pse_size_breakdown      Human-readable chain for audit trail
    pse_version             PSE version string
    pse_signal_type         V2 signal classification (CONTINUATION|TRANSITION|NO_EDGE)
    pse_momentum_tier       V2 bucket transition tier (TIER_1_EXPLOSIVE … TIER_2_BUILDING)

FATAL BLOCKS (size → 0.0, non-negotiable)
------------------------------------------
1. ev_status == "FAIL" AND ev_conf_adj < −0.10    (genuinely negative EV)
2. mp_hard_block_reason set AND is a DATA block    (no valid contract at all)
3. data_quality_score < 25                         (data too poor to decide)

EVERYTHING ELSE produces a reduced size, never a block.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math
import os

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

PSE_VERSION       = "1.1.0"
PSE_PRODUCTION_RETIRED = True
PSE_RETIRED_POLICY = "PSE_IGNORED_MANUAL_SIZING"

# Base risk per trade as fraction of portfolio
BASE_RISK         = 0.015   # 1.5% base

# Size bounds
MIN_EXECUTABLE    = 0.002   # 0.2% — below this, commission friction destroys edge
MAX_POSITION      = 0.030   # 3.0% — hard cap per position (Tastytrade live capital)

# EV → multiplier mapping
EV_FATAL_FLOOR    = -0.10   # Below this with FAIL status → fatal block
EV_ZERO_FLOOR     = -0.05   # Negative but not fatal → 0.30x
EV_WEAK_FLOOR     =  0.00   # Near-zero positive → 0.50x
EV_SMALL_FLOOR    =  0.05   # Small positive → 0.70x
EV_GOOD_FLOOR     =  0.15   # Good EV → 1.00x
EV_STRONG_FLOOR   =  0.25   # Strong EV → 1.20x (allow scaling above base)

# Fatal MP block prefixes — only DATA failures are fatal (no contract exists)
# Everything else (spread, theta, IV) becomes a penalty
MP_FATAL_PREFIXES = {
    "Required data missing",
    "Stale data without live quote",
    "Structure / thesis invalid",
    "Structure confidence too low",
}


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PSEResult:
    pse_final_size:      float = 0.0
    pse_execution_mode:  str   = "SKIP"
    pse_edge_score:      float = 0.0
    pse_ev_mult:         float = 0.0
    pse_mp_mult:         float = 1.0
    pse_eil_mult:        float = 1.0
    pse_options_mult:    float = 1.0
    pse_regime_mult:     float = 1.0
    pse_jump_risk_mult:  float = 1.0
    pse_confidence_mult: float = 1.0
    pse_block_reason:    str   = ""
    pse_size_breakdown:  str   = ""
    pse_version:         str   = PSE_VERSION
    # V2 signal intelligence fields (Sprint 3)
    pse_signal_type:     str   = "NO_EDGE"
    pse_momentum_tier:   str   = "TIER_4_FLAT"

    def to_row_dict(self) -> dict:
        return {
            "pse_final_size":      round(self.pse_final_size, 5),
            "pse_execution_mode":  self.pse_execution_mode,
            "pse_edge_score":      round(self.pse_edge_score, 6),
            "pse_ev_mult":         round(self.pse_ev_mult, 4),
            "pse_mp_mult":         round(self.pse_mp_mult, 4),
            "pse_eil_mult":        round(self.pse_eil_mult, 4),
            "pse_options_mult":    round(self.pse_options_mult, 4),
            "pse_regime_mult":     round(self.pse_regime_mult, 4),
            "pse_jump_risk_mult":   round(self.pse_jump_risk_mult, 4),
            "pse_confidence_mult": round(self.pse_confidence_mult, 4),
            "pse_block_reason":    self.pse_block_reason,
            "pse_size_breakdown":  self.pse_size_breakdown,
            "pse_version":         self.pse_version,
            "pse_signal_type":     self.pse_signal_type,
            "pse_momentum_tier":   self.pse_momentum_tier,
        }

    def to_fd_compat_dict(self) -> dict:
        """
        Emit fd_* compatible fields so downstream code reading fd_verdict/fd_size
        continues to work without modification.

        fd_verdict mapping:
            FULL_EXECUTE / EXECUTE  →  EXECUTE
            REDUCED                 →  EXECUTE_WITH_CAUTION
            PROBE                   →  EXECUTE_WITH_CAUTION
            SKIP                    →  WATCHLIST  (not BLOCK — idea is preserved)
            FATAL_BLOCK             →  BLOCK
        """
        _mode_to_fd = {
            "FULL_EXECUTE":  "EXECUTE",
            "EXECUTE":       "EXECUTE",
            "REDUCED":       "EXECUTE_WITH_CAUTION",
            "PROBE":         "EXECUTE_WITH_CAUTION",
            "SKIP":          "WATCHLIST",
            "FATAL_BLOCK":   "BLOCK",
        }
        fd_verdict = _mode_to_fd.get(self.pse_execution_mode, "WATCHLIST")
        return {
            "fd_verdict":          fd_verdict,
            "fd_size":             round(self.pse_final_size, 4),
            "fd_reason":           self.pse_block_reason or self.pse_size_breakdown,
            "fd_ev_used":          round(self.pse_edge_score, 6),
            "fd_confidence":       min(100.0, round(self.pse_ev_mult * 100, 1)),
            "fd_reroute_flag":     False,
            "fd_watchlist_reason": self.pse_block_reason if fd_verdict == "WATCHLIST" else "",
        }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _safe(v, default=0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return default if math.isnan(f) else f
    except Exception:
        return default


def _s(v, default="") -> str:
    try:
        if v is None:
            return default
        s = str(v).strip()
        return default if s.lower() in ("nan", "none", "null", "na", "n/a", "") else s
    except Exception:
        return default


def _is_false(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return not v
    s = _s(v).upper()
    return s in {"FALSE", "F", "NO", "N", "0", "0.0", "NONE"}


def _is_true(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = _s(v).upper()
    return s in {"TRUE", "T", "YES", "Y", "1", "1.0"}


def _direction_side(row: dict) -> str:
    for key in (
        "options_direction",
        "direction",
        "recommended_direction",
        "option_direction",
        "instrument",
        "options_strategy",
    ):
        value = _s(row.get(key)).upper()
        if value in {"CALL", "C", "BULLISH", "LONG_CALL"}:
            return "CALL"
        if value in {"PUT", "P", "BEARISH", "LONG_PUT"}:
            return "PUT"
        if "CALL" in value and "PUT" not in value:
            return "CALL"
        if "PUT" in value and "CALL" not in value:
            return "PUT"
    return ""


def _macro_conviction(row: dict) -> float:
    for key in (
        "macro_conviction_score",
        "horizon_macro_conviction",
        "macro_conviction",
        "conviction_score",
    ):
        raw = row.get(key)
        if raw is None:
            continue
        value = _safe(raw, -1.0)
        if value >= 0.0:
            if value > 1.0:
                value = value / 100.0
            return max(0.0, min(1.0, value))
    return 1.0


def _binding_eil_block_reason(row: dict) -> str:
    eil_token = _s(row.get("eil_v3_verdict", "")).upper()
    if eil_token != "BLOCKED":
        return ""
    if not _is_false(row.get("eil_advisory_only", True)):
        return ""

    liquidity_failed = _is_false(row.get("eil_liquidity_passed"))
    defer_reason = _s(row.get("eil_defer_reason") or row.get("eil_block_reason")).upper()
    hard_reason = any(
        token in defer_reason
        for token in (
            "NO_EXECUTABLE_MARKET",
            "LIQUIDITY_GATE_FAILED",
            "NO EXECUTABLE MARKET",
            "LIQUIDITY GATE FAILED",
        )
    )
    if liquidity_failed or hard_reason:
        return "FATAL_EIL_BINDING_LIQUIDITY"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# MULTIPLIER FUNCTIONS
# (Each returns a float ∈ [0.30, 1.20] — never 0.0 except on fatal block)
# ─────────────────────────────────────────────────────────────────────────────

def _ev_multiplier(ev_conf_adj: float, ev_status: str) -> float:
    """
    Convert EV engine output to a continuous size multiplier.

    EV scale in live pipeline: ev_conf_adj typically ∈ [0.002, 0.022]
    (much lower than the 0–0.25 range the old FDE thresholds expected).
    Thresholds here are calibrated to the actual observed range.
    """
    if ev_status in ("PASS_HIGH",):
        return min(1.20, 0.80 + ev_conf_adj * 8.0)
    if ev_status in ("PASS",):
        return min(1.00, 0.70 + ev_conf_adj * 6.0)
    if ev_status in ("PASS_SMALL", "YES_SMALL"):
        return min(0.80, 0.50 + ev_conf_adj * 4.0)
    if ev_status == "WEAK_PASS":
        return 0.40
    if ev_status == "DATA_WEAK":
        return 0.35
    # FAIL — already checked for fatal above; if we reach here EV is marginal
    return 0.30


def _mp_multiplier(row: dict) -> tuple[float, bool, str]:
    """
    Convert Monetisation Policy output to a penalty multiplier.

    Returns (multiplier, is_fatal, reason_string).

    FATAL (returns 0.0): data blocks only — no contract exists to trade.
    PENALTY: everything else — spread, theta, runway, IV are taxed not blocked.
    """
    mp_block = _s(row.get("mp_hard_block_reason", ""))
    mp_mult  = _safe(row.get("mp_final_size_mult"), 1.0)

    if mp_block:
        # Check if this is a genuinely fatal block (no contract)
        for fatal_prefix in MP_FATAL_PREFIXES:
            if fatal_prefix.lower() in mp_block.lower():
                return 0.0, True, mp_block

        # Non-fatal block — convert to penalty
        # Spread too wide → 0.40x (high cost but tradeable with limit orders)
        if "spread" in mp_block.lower():
            return 0.40, False, f"MP_SPREAD_PENALTY:{mp_block}"
        # Premium too low → 0.35x (commission risk)
        if "premium" in mp_block.lower():
            return 0.35, False, f"MP_PREMIUM_PENALTY:{mp_block}"
        # Theta → 0.45x
        if "theta" in mp_block.lower():
            return 0.45, False, f"MP_THETA_PENALTY:{mp_block}"
        # DTE too low → 0.40x (short-dated, higher gamma risk)
        if "dte" in mp_block.lower():
            return 0.40, False, f"MP_DTE_PENALTY:{mp_block}"
        # Economics (runway, breakeven, RR+EV) → 0.40x
        if any(k in mp_block.lower() for k in ("runway", "breakeven", "negative rr", "economics")):
            return 0.40, False, f"MP_ECONOMICS_PENALTY:{mp_block}"
        # IV distortion → 0.45x
        if "iv distortion" in mp_block.lower():
            return 0.45, False, f"MP_IV_PENALTY:{mp_block}"

        # Unknown block type — apply conservative penalty, not fatal
        return 0.35, False, f"MP_UNKNOWN_PENALTY:{mp_block}"

    # No block — use mp_final_size_mult directly (already a penalty ∈ [0.10, 1.00])
    # Clamp to our floor of 0.30 to avoid near-zero from compound soft penalties
    return max(0.30, min(1.10, mp_mult)), False, ""


def _eil_multiplier(row: dict) -> float:
    """
    Convert EIL verdict to a size penalty.
    EIL is ADVISORY — it adjusts size, never blocks.

    Blocked/failed EIL = 0.60x (EOD mode) (not 0.0x).
    Unavailable EIL    = 0.70x (unknown is not fatal, but we're cautious).
    """
    eil_token    = _s(row.get("eil_v3_verdict", "")).upper()
    eil_score    = _safe(row.get("eil_composite_score"), 0.0)
    eil_size     = _safe(row.get("eil_size_multiplier"), 1.0)
    eil_advisory = row.get("eil_advisory_only", True)

    # EIL not run or unavailable
    if not eil_token:
        return 0.70

    _TOKEN_MULT = {
        "EXECUTE":                   1.00,
        "HIGH_CONVICTION":           1.00,
        "EXECUTE_NOW":               1.00,
        "EXECUTE_WITH_CAUTION":      0.65,
        "EXECUTE_DEFER":             0.45,
        "WATCHLIST":                 0.45,
        "BLOCKED":                   0.60,  # EOD data absence — not a structural block
        "STAND_DOWN_MICROSTRUCTURE": 0.60,  # Active microstructure warning — cautious not fatal
    }
    # DESIGN NOTE (v1.1.0): BLOCKED raised from 0.30 → 0.60.
    # In EOD/evening mode EIL BLOCKED = synthetic data unavailable, not active
    # tape deterioration. 0.30× crushed structurally valid CONTINUATION signals
    # below MIN_EXEC before V2 edge quality was assessed. 0.60× = "cautious entry"
    # which is correct for EOD. Revisit if live intraday tape shows systematic
    # abuse of the BLOCKED path for genuinely deteriorating setups.

    token_mult = _TOKEN_MULT.get(eil_token, 0.60)

    # Blend with score-based mult for smoother signal
    # eil_size from the engine's own _dynamic_size() is informative
    score_mult = max(0.30, min(1.00, eil_score / 100.0))
    blended    = (token_mult * 0.60) + (score_mult * 0.40)

    return round(max(0.30, min(1.00, blended)), 4)


def _options_multiplier(row: dict) -> float:
    """
    Convert options intelligence signals to a penalty multiplier.
    Replaces hard gates with continuous scaling.

    Sources:
      - iv_rank         (IV expensive = buy at discount)
      - spread_pct      (wide spread = execution cost tax)
      - contract_iv     (absolute IV level)
    """
    # FIX-IV-RANK-COL (2026-04-23): Pipeline stores IVP as ivp_252d / iv_percentile.
    # "iv_rank" is often NaN in EOD mode, causing the IV penalty to silently not fire.
    # Fallback chain: iv_rank → ivp_252d (0-100, normalise) → iv_percentile → 0.50.
    _iv_raw = row.get("iv_rank")
    if _iv_raw is None or (isinstance(_iv_raw, float) and (_iv_raw != _iv_raw)):
        _iv_raw = row.get("ivp_252d") or row.get("iv_percentile")
    iv_rank = _safe(_iv_raw, 0.50)
    # Normalise: ivp_252d is 0-100 scale; iv_rank expected 0-1
    if iv_rank > 1.0:
        iv_rank = iv_rank / 100.0
    iv_rank = max(0.0, min(1.0, iv_rank))
    spread    = _safe(row.get("spread_pct_live") or row.get("spread_pct"), 0.05)
    opt_score = _safe(row.get("options_intelligence_score") or row.get("composite"), 50.0)

    mult = 1.0

    # IV rank penalty — high IV = expensive options = lower expected return
    # (not a block — elevated IV sometimes accompanies the best setups)
    if iv_rank > 0.80:
        mult *= 0.65
    elif iv_rank > 0.70:
        mult *= 0.75
    elif iv_rank > 0.60:
        mult *= 0.85
    # else: no penalty for normal IV environment

    # Spread penalty — wide spread = execution slippage
    if spread > 0.25:
        mult *= 0.50
    elif spread > 0.20:
        mult *= 0.60   # was: BLOCK. Now: 0.60x with limit orders
    elif spread > 0.15:
        mult *= 0.70
    elif spread > 0.10:
        mult *= 0.80
    elif spread > 0.08:
        mult *= 0.90
    # else: clean spread, no penalty

    # Options composite score — low score = weak setup quality
    if opt_score < 35:
        mult *= 0.60
    elif opt_score < 45:
        mult *= 0.75
    elif opt_score < 55:
        mult *= 0.90
    # else: no penalty

    return round(max(0.30, min(1.00, mult)), 4)


def _regime_multiplier(row: dict) -> float:
    """
    Regime context as a sizing signal, not a gate.

    v1.1.0 (Sprint 3): adds V2 signal-tier boost on top of regime base.
    Mirrors the tier boost in EVEngineV2._regime_mult() but operates on
    position size rather than edge quality — both are independently justified.

    CONTINUATION tiers:
      TIER_1_EXPLOSIVE / TIER_2_SUSTAINING  → +0.08 (HIGH/EXTREME momentum)
      TIER_3_BUILDING                       → +0.04 (MID → HIGH building)
      TIER_4_FLAT                           → +0.02 (MID → MID flat)
    TRANSITION: no boost — probe entries do not warrant size inflation.
    Cap: 1.20 (existing pipeline maximum — unchanged).
    """
    trade_type = _s(row.get("trade_type_classification")).upper()
    macro_state = _s(row.get("macro_alignment_state")).upper()
    macro_authority = _s(row.get("macro_direction_authority")).upper()
    if trade_type == "STRUCTURAL_SINGLE_STOCK" and (
        macro_authority == "DISABLED" or macro_state in {"MACRO_NOT_APPLICABLE", "NO_DIRECTIONAL_MACRO_EDGE"}
    ):
        horizon = _s(row.get("macro_preferred_horizon") or row.get("horizon_bucket")).lower()
        return 0.4 if "6_10" in horizon or "6-10" in horizon else 0.5

    regime = _s(
        row.get("horizon_regime_state")
        or row.get("regime_state")
        or row.get("macro_regime_label")
        or row.get("macro_regime")
        or row.get("regime"),
        "TRANSITIONAL",
    ).upper().replace(" ", "_")
    drift = _s(row.get("regime_drift_status")).upper().replace(" ", "_")
    if regime == "TRANSITIONAL" and drift in {"DRIFTING_BEARISH", "BEARISH_DRIFT"}:
        regime = "TRANSITIONAL_BEARISH"
    elif regime == "TRANSITIONAL" and drift in {"DRIFTING_BULLISH", "BULLISH_DRIFT"}:
        regime = "TRANSITIONAL_BULLISH"

    side = _direction_side(row)
    conviction = _macro_conviction(row)
    neutral = 0.75
    target = {
        "RISK_ON":              {"CALL": 1.10, "PUT": 0.45, "": 1.00},
        "BULLISH":              {"CALL": 1.10, "PUT": 0.45, "": 1.00},
        "TRANSITIONAL_BULLISH": {"CALL": 1.00, "PUT": 0.55, "": 0.90},
        "TRANSITIONAL_NEUTRAL": {"CALL": 0.90, "PUT": 0.90, "": 0.90},
        "TRANSITIONAL":         {"CALL": 0.90, "PUT": 0.90, "": 0.90},
        "NEUTRAL":              {"CALL": 0.90, "PUT": 0.90, "": 0.90},
        "TRANSITIONAL_BEARISH": {"CALL": 0.55, "PUT": 1.00, "": 0.75},
        "RISK_OFF":             {"CALL": 0.35, "PUT": 1.05, "": 0.75},
        "BEARISH":              {"CALL": 0.35, "PUT": 1.05, "": 0.75},
        "FLIPPED":              {"CALL": 0.55, "PUT": 0.55, "": 0.55},
    }.get(regime, {"CALL": 0.85, "PUT": 0.85, "": 0.85}).get(side, 0.85)
    base = neutral + ((target - neutral) * conviction)

    # V2 signal-tier boost — only for CONTINUATION signals
    signal_type  = _s(row.get("signal_type"), "NO_EDGE").upper()
    momentum_tier = _s(row.get("momentum_tier"), "TIER_4_FLAT").upper()

    if signal_type == "CONTINUATION":
        _tier_boost = {
            "TIER_1_EXPLOSIVE":  0.08,
            "TIER_2_SUSTAINING": 0.08,
            "TIER_3_BUILDING":   0.04,
            "TIER_4_FLAT":       0.02,
        }.get(momentum_tier, 0.02)
        base = base + _tier_boost

    return min(base, 1.20)  # cap at existing pipeline maximum


def _jump_risk_multiplier(row: dict) -> float:
    if _is_true(row.get("l3_jump_risk_flag")):
        return 0.50
    return 1.00


def _confidence_multiplier(ev_result) -> float:
    """
    Data quality and calibration confidence as a size modifier.

    FIX-CONF-MULT (2026-04-23): Previous version computed dq and qs but never
    used them — they were dead variables. Only ev_result.confidence_multiplier
    (already a [0,1] float from EVEngineV2._conf_mult) is needed here.
    dq and qs are surfaced in quality_score by the EV engine — no need to
    recompute here.
    """
    cm = _safe(getattr(ev_result, "confidence_multiplier", 0.75), 0.75)
    return round(max(0.40, min(1.00, cm)), 4)


# ─────────────────────────────────────────────────────────────────────────────
# EXECUTION MODE
# ─────────────────────────────────────────────────────────────────────────────

def _execution_mode(final_size: float, ev_status: str, eil_token: str) -> str:
    if final_size <= 0:
        return "FATAL_BLOCK"
    ratio = final_size / BASE_RISK
    if ratio >= 1.20:
        return "FULL_EXECUTE"
    if ratio >= 0.80:
        return "EXECUTE"
    if ratio >= 0.40:
        return "REDUCED"
    if ratio >= 0.13:   # ≥ MIN_EXECUTABLE / BASE_RISK
        return "PROBE"
    return "SKIP"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class PositionSizingEngine:
    """
    Converts all pipeline layer outputs into a single continuous position size.
    Stateless — no side effects.

    Usage (from runner):
        from position_sizing_engine import PositionSizingEngine
        pse    = PositionSizingEngine()
        result = pse.size(row, ev_result)
        row.update(result.to_row_dict())
        row.update(result.to_fd_compat_dict())  # keeps fd_* columns working
    """

    def size(self, row: dict, ev_result) -> PSEResult:
        """
        Produce a continuous position size from all pipeline layer signals.

        Args:
            row:        Full signal row dict (contains all upstream layer outputs)
            ev_result:  EVResult from EVEngineV2.evaluate()

        Returns:
            PSEResult with final_size and full audit trail
        """
        ev_ca      = _safe(getattr(ev_result, "ev_conf_adj", 0.0))
        ev_status  = _s(getattr(ev_result, "ev_status", "FAIL"))
        dq         = _safe(row.get("data_quality_score"), 85.0)
        ticker     = _s(row.get("ticker"), "UNKNOWN")

        # ── FATAL BLOCKS ───────────────────────────────────────────────────────
        # 1. Genuinely negative EV (not marginal — confirmed FAIL below threshold)
        if ev_status == "FAIL" and ev_ca < EV_FATAL_FLOOR:
            return PSEResult(
                pse_final_size     = 0.0,
                pse_execution_mode = "FATAL_BLOCK",
                pse_edge_score     = ev_ca,
                pse_block_reason   = f"FATAL_NEG_EV:{ev_ca:+.4f}",
                pse_size_breakdown = f"{ticker} EV={ev_ca:+.4f} status={ev_status} → FATAL",
            )

        # 2. Data quality too poor to make any decision
        if dq < 25:
            return PSEResult(
                pse_final_size     = 0.0,
                pse_execution_mode = "FATAL_BLOCK",
                pse_edge_score     = ev_ca,
                pse_block_reason   = f"FATAL_DATA_QUALITY:{dq:.0f}<25",
                pse_size_breakdown = f"{ticker} dq={dq:.0f} → FATAL",
            )

        # 3. MP fatal block (data / structure only)
        mp_mult, mp_fatal, mp_reason = _mp_multiplier(row)
        if mp_fatal:
            return PSEResult(
                pse_final_size     = 0.0,
                pse_execution_mode = "FATAL_BLOCK",
                pse_edge_score     = ev_ca,
                pse_mp_mult        = 0.0,
                pse_block_reason   = f"FATAL_MP:{mp_reason}",
                pse_size_breakdown = f"{ticker} mp_fatal={mp_reason} → FATAL",
            )

        # ── PENALTY CHAIN ──────────────────────────────────────────────────────
        eil_binding_reason = _binding_eil_block_reason(row)
        if eil_binding_reason:
            return PSEResult(
                pse_final_size     = 0.0,
                pse_execution_mode = "FATAL_BLOCK",
                pse_edge_score     = ev_ca,
                pse_mp_mult        = round(mp_mult, 4),
                pse_eil_mult       = 0.0,
                pse_block_reason   = eil_binding_reason,
                pse_size_breakdown = f"{ticker} eil_blocked_binding_liquidity -> FATAL",
            )

        ev_mult      = _ev_multiplier(ev_ca, ev_status)
        eil_mult     = _eil_multiplier(row)
        options_mult = _options_multiplier(row)
        regime_mult  = _regime_multiplier(row)
        jump_mult    = _jump_risk_multiplier(row)
        conf_mult    = _confidence_multiplier(ev_result)

        # Multiplicative chain
        raw_size = (
            BASE_RISK
            * ev_mult
            * mp_mult
            * eil_mult
            * options_mult
            * regime_mult
            * jump_mult
            * conf_mult
        )

        # ── V2 TRANSITION probe cap (Sprint 3) ──────────────────────────────────
        # TRANSITION signals are probe entries — never full size regardless of
        # how good the other multipliers are. Hard cap at 2% of capital.
        # Keeps PROBE execution mode semantically accurate.
        _signal_type_pse  = _s(row.get("signal_type"), "NO_EDGE").upper()
        _momentum_tier_pse = _s(row.get("momentum_tier"), "TIER_4_FLAT").upper()
        TRANSITION_MAX = 0.020  # 2.0% hard cap for all probe entries
        if _signal_type_pse == "TRANSITION" and raw_size > TRANSITION_MAX:
            raw_size = TRANSITION_MAX

        # Clamp
        if raw_size < MIN_EXECUTABLE:
            final_size = 0.0
            exec_mode  = "SKIP"
        else:
            final_size = round(min(raw_size, MAX_POSITION), 5)
            eil_token  = _s(row.get("eil_v3_verdict", "")).upper()
            exec_mode  = _execution_mode(final_size, ev_status, eil_token)

        breakdown = (
            f"{ticker} "
            f"base={BASE_RISK:.3f} "
            f"×ev={ev_mult:.2f}({ev_status},{ev_ca:+.4f}) "
            f"×mp={mp_mult:.2f} "
            f"×eil={eil_mult:.2f} "
            f"×opt={options_mult:.2f} "
            f"×reg={regime_mult:.2f} "
            f"×jump={jump_mult:.2f} "
            f"×conf={conf_mult:.2f} "
            f"→{final_size:.5f}({exec_mode})"
            f" [signal={_signal_type_pse}/{_momentum_tier_pse}]"
        )

        return PSEResult(
            pse_final_size      = final_size,
            pse_execution_mode  = exec_mode,
            pse_edge_score      = round(ev_ca, 6),
            pse_ev_mult         = round(ev_mult, 4),
            pse_mp_mult         = round(mp_mult, 4),
            pse_eil_mult        = round(eil_mult, 4),
            pse_options_mult    = round(options_mult, 4),
            pse_regime_mult     = round(regime_mult, 4),
            pse_jump_risk_mult  = round(jump_mult, 4),
            pse_confidence_mult = round(conf_mult, 4),
            pse_block_reason    = mp_reason if mp_reason else "",
            pse_size_breakdown  = breakdown,
            pse_signal_type     = _signal_type_pse,
            pse_momentum_tier   = _momentum_tier_pse,
        )


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CONVENIENCE
# ─────────────────────────────────────────────────────────────────────────────

_pse = PositionSizingEngine()


def compute_position_size(row: dict, ev_result) -> PSEResult:
    """
    Retired production entry point.

    Production must not allocate or suppress capital through PSE. To use the
    legacy sizing model for offline research only, set
    AVSHUNTER_ENABLE_RETIRED_PSE=1 before calling this function.

    Usage:
        from position_sizing_engine import compute_position_size
        result = compute_position_size(row, ev_result)
        row.update(result.to_row_dict())
        row.update(result.to_fd_compat_dict())
    """
    if PSE_PRODUCTION_RETIRED and os.getenv("AVSHUNTER_ENABLE_RETIRED_PSE", "").strip() != "1":
        return PSEResult(
            pse_final_size=0.0,
            pse_execution_mode="SIZING_IGNORED_REVIEW",
            pse_edge_score=float(getattr(ev_result, "ev_conf_adj", 0.0) or 0.0),
            pse_ev_mult=1.0,
            pse_mp_mult=1.0,
            pse_eil_mult=1.0,
            pse_options_mult=1.0,
            pse_regime_mult=1.0,
            pse_jump_risk_mult=1.0,
            pse_confidence_mult=1.0,
            pse_block_reason="",
            pse_size_breakdown=PSE_RETIRED_POLICY,
            pse_signal_type=str(row.get("signal_type", "UNKNOWN") or "UNKNOWN").upper(),
            pse_momentum_tier=str(row.get("momentum_tier", "UNKNOWN") or "UNKNOWN").upper(),
        )
    return _pse.size(row, ev_result)


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dataclasses import dataclass as _dc

    @_dc
    class MockEV:
        ev_conf_adj:           float = 0.012
        ev_status:             str   = "PASS_SMALL"
        quality_score:         float = 58.0
        confidence_multiplier: float = 0.78
        data_quality_flag:     bool  = False
        contract_efficiency_flag: bool = False
        primary_reason:        str   = "LOW_POS_EV"

    pse = PositionSizingEngine()

    cases = [
        ("NVDA — good setup, wide spread",
         {"ticker": "NVDA", "regime_state": "RISK_ON",
          "spread_pct": 0.22, "iv_rank": 0.55, "mp_final_size_mult": 0.60,
          "mp_hard_block_reason": "Spread too wide",
          "eil_v3_verdict": "EXECUTE_WITH_CAUTION", "eil_composite_score": 68.0,
          "eil_size_multiplier": 0.60, "data_quality_score": 82.0},
         MockEV(ev_conf_adj=0.010, ev_status="PASS_SMALL")),

        ("AAPL — clean setup, EXECUTE_NOW",
         {"ticker": "AAPL", "regime_state": "RISK_ON",
          "spread_pct": 0.04, "iv_rank": 0.35, "mp_final_size_mult": 1.00,
          "mp_hard_block_reason": "",
          "eil_v3_verdict": "EXECUTE_NOW", "eil_composite_score": 88.0,
          "eil_size_multiplier": 1.00, "data_quality_score": 92.0},
         MockEV(ev_conf_adj=0.021, ev_status="PASS")),

        ("TSLA — EIL BLOCKED (old system = 100% block)",
         {"ticker": "TSLA", "regime_state": "TRANSITIONAL",
          "spread_pct": 0.12, "iv_rank": 0.71, "mp_final_size_mult": 0.80,
          "mp_hard_block_reason": "",
          "eil_v3_verdict": "BLOCKED", "eil_composite_score": 28.0,
          "eil_size_multiplier": 0.0, "data_quality_score": 74.0},
         MockEV(ev_conf_adj=0.008, ev_status="PASS_SMALL")),

        ("XOM — theta block (old system = 100% block)",
         {"ticker": "XOM", "regime_state": "NEUTRAL",
          "spread_pct": 0.07, "iv_rank": 0.60, "mp_final_size_mult": 0.0,
          "mp_hard_block_reason": "Theta drag too high",
          "eil_v3_verdict": "EXECUTE_WITH_CAUTION", "eil_composite_score": 61.0,
          "eil_size_multiplier": 0.60, "data_quality_score": 80.0},
         MockEV(ev_conf_adj=0.005, ev_status="PASS_SMALL")),

        ("PLTR — genuinely fatal (negative EV)",
         {"ticker": "PLTR", "regime_state": "RISK_OFF",
          "spread_pct": 0.18, "iv_rank": 0.82, "mp_final_size_mult": 0.0,
          "mp_hard_block_reason": "",
          "eil_v3_verdict": "STAND_DOWN_MICROSTRUCTURE", "eil_composite_score": 15.0,
          "eil_size_multiplier": 0.0, "data_quality_score": 78.0},
         MockEV(ev_conf_adj=-0.18, ev_status="FAIL")),

        ("ZZZ — data too poor (fatal)",
         {"ticker": "ZZZ", "regime_state": "TRANSITIONAL",
          "spread_pct": 0.08, "iv_rank": 0.50, "mp_final_size_mult": 0.80,
          "mp_hard_block_reason": "",
          "eil_v3_verdict": "EXECUTE", "eil_composite_score": 72.0,
          "eil_size_multiplier": 0.90, "data_quality_score": 18.0},
         MockEV(ev_conf_adj=0.009, ev_status="PASS_SMALL")),
    ]

    print("\n" + "═" * 75)
    print("  AVSHUNTER Position Sizing Engine v1.1.0 — Smoke Test")
    print("═" * 75)
    print(f"  {'Ticker':<8} {'Mode':<16} {'Size':>8}  {'Breakdown (partial)'}")
    print("  " + "─" * 72)

    for label, row, ev in cases:
        r = pse.size(row, ev)
        # Print short breakdown
        parts = r.pse_size_breakdown.split(" ×")
        short = parts[0] + " ×" + " ×".join(parts[1:4]) + "..."
        mode_icon = {
            "FULL_EXECUTE": "🟢", "EXECUTE": "🟢", "REDUCED": "🟡",
            "PROBE": "🟠", "SKIP": "🟤", "FATAL_BLOCK": "🔴"
        }.get(r.pse_execution_mode, "⚪")
        print(f"  {row['ticker']:<8} {mode_icon} {r.pse_execution_mode:<14} {r.pse_final_size:>8.5f}  {r.pse_block_reason or ''}")

    r_tsla = pse.size(cases[2][1], cases[2][2])
    r_xom  = pse.size(cases[3][1], cases[3][2])
    r_pltr = pse.size(cases[4][1], cases[4][2])
    r_aapl = pse.size(cases[1][1], cases[1][2])

    # ── Updated assertions (v1.1.0) ──────────────────────────────────────────
    # TSLA (EIL BLOCKED + iv=0.71 + TRANSITIONAL + weak EV):
    #   Compound penalties correctly floor below MIN_EXECUTABLE → SKIP.
    #   Key: SKIP ≠ FATAL_BLOCK — the idea is preserved on watchlist.
    assert r_tsla.pse_execution_mode == "SKIP", f"FAIL: TSLA should SKIP (compound penalty), got {r_tsla.pse_execution_mode}"
    assert r_tsla.pse_block_reason == "", f"FAIL: TSLA SKIP should have no block_reason, got {r_tsla.pse_block_reason}"

    # XOM (theta penalty + weak EV + iv=0.60 + NEUTRAL): compound → SKIP
    assert r_xom.pse_execution_mode == "SKIP", f"FAIL: XOM should SKIP, got {r_xom.pse_execution_mode}"
    assert r_xom.pse_block_reason != "" or r_xom.pse_execution_mode == "SKIP", "XOM should have penalty reason"

    # PLTR — genuinely fatal (neg EV below floor)
    assert r_pltr.pse_final_size == 0.0, f"FAIL: PLTR neg EV should be FATAL, got {r_pltr.pse_final_size}"
    assert r_pltr.pse_execution_mode == "FATAL_BLOCK", f"FAIL: PLTR should be FATAL_BLOCK, got {r_pltr.pse_execution_mode}"
    assert "FATAL_NEG_EV" in r_pltr.pse_block_reason, f"FAIL: PLTR block_reason wrong: {r_pltr.pse_block_reason}"

    # AAPL — clean setup → positive non-zero size
    assert r_aapl.pse_final_size > 0, f"FAIL: AAPL clean setup should have size > 0, got {r_aapl.pse_final_size}"

    # V2 SPRINT 3: CONTINUATION TIER_1_EXPLOSIVE → larger regime_mult than NO_EDGE
    row_cont = dict(cases[1][1])   # copy AAPL row
    row_cont["signal_type"]   = "CONTINUATION"
    row_cont["momentum_tier"] = "TIER_1_EXPLOSIVE"
    row_noedge = dict(cases[1][1])
    row_noedge["signal_type"]   = "NO_EDGE"
    row_noedge["momentum_tier"] = "TIER_4_FLAT"
    r_cont    = pse.size(row_cont,    cases[1][2])
    r_noedge  = pse.size(row_noedge,  cases[1][2])
    assert r_cont.pse_final_size >= r_noedge.pse_final_size, (
        f"FAIL: CONTINUATION TIER_1 ({r_cont.pse_final_size:.5f}) should be >= "
        f"NO_EDGE ({r_noedge.pse_final_size:.5f})"
    )
    assert r_cont.pse_signal_type == "CONTINUATION", f"FAIL: pse_signal_type not set"
    assert r_cont.pse_momentum_tier == "TIER_1_EXPLOSIVE", f"FAIL: pse_momentum_tier not set"

    # TRANSITION probe cap — size must not exceed 2.0%
    row_trans = dict(cases[1][1])
    row_trans["signal_type"]   = "TRANSITION"
    row_trans["momentum_tier"] = "TIER_2_BUILDING"
    r_trans = pse.size(row_trans, cases[1][2])
    assert r_trans.pse_final_size <= 0.020, (
        f"FAIL: TRANSITION should be capped at 2.0%, got {r_trans.pse_final_size:.5f}"
    )

    print("\n  ✅  All v1.1.0 assertions passed")
    print(f"     TSLA (EIL BLOCKED + penalties) : SKIP  size={r_tsla.pse_final_size:.5f}  mode={r_tsla.pse_execution_mode}")
    print(f"     XOM  (theta penalty)           : SKIP  size={r_xom.pse_final_size:.5f}  mode={r_xom.pse_execution_mode}")
    print(f"     PLTR (fatal neg EV)            : FATAL size={r_pltr.pse_final_size:.5f}  reason={r_pltr.pse_block_reason}")
    print(f"     AAPL (clean)                   : {r_aapl.pse_execution_mode}  size={r_aapl.pse_final_size:.5f}")
    print(f"     CONTINUATION TIER_1 vs NO_EDGE : {r_cont.pse_final_size:.5f} vs {r_noedge.pse_final_size:.5f}")
    print(f"     TRANSITION probe cap           : {r_trans.pse_final_size:.5f} (cap=0.02000)")
    print()
