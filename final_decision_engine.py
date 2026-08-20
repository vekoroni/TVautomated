# ============================================================
# STATUS: RETIRED / NOT ON ORCHESTRATOR PATH (unreachable)
# Superseded by: no live sizing/decision authority currently calls this
#                module — PSE was its intended caller but PSE is itself
#                retired (see position_sizing_engine.py header)
# Evidence:      make_final_decision is imported at
#                execution_intelligence_runner.py:214 but never called
#                anywhere in that file or elsewhere in the repo (verified
#                via targeted search for direct calls and for getattr-based
#                or registry/config-driven dynamic dispatch — none found,
#                2026-08-19)
# Retired:       UNKNOWN (module docstring's "Date: 2026-04-13" marks its
#                last content revision, not a retirement date)
# Note:          this file's own docstring (line 29) claims PSE calls it
#                "when PSE is available" — that condition never holds (PSE
#                is unconditionally disabled, see position_sizing_engine.py)
#                — so the fallback role the docstring describes does not
#                execute on any live path. decide() (~496-560) still
#                contains real BLOCK / WATCHLIST / EXECUTE_WITH_CAUTION
#                branch logic with size effects.
# Documented:    2026-08-19 (EV audit, Stage 0)
# ============================================================
"""
AVSHUNTER — Final Decision Engine
===================================
Version : 1.1.0
Date    : 2026-04-13

CHANGES FROM v1.0.0
--------------------
FIX-01  sb_veto_adj read as string not bool. Superbrain writes "STAND_DOWN"
        or "NONE" — _b() returned False for both. Now uses explicit string
        membership check against _SB_VETO_TRIGGERS.

FIX-07  EIL_SIZE_MAP expanded to cover all tokens EIL composite engine
        can emit: EXECUTE_NOW, EXECUTE_WITH_CAUTION, EXECUTE_DEFER,
        STAND_DOWN_MICROSTRUCTURE. Previously only BLOCKED and "" matched;
        all others silently defaulted to 1.0 (no penalty).

        Confidence bonus also extended to EXECUTE_NOW (peer of EXECUTE).

Broker  : Tastytrade (live — real capital)

PURPOSE
-------
This module is the legacy Final Decision Engine and compatibility verdict layer.

CURRENT GOVERNANCE — MAY 2026
------------------------------
PositionSizingEngine (PSE), called inside execution_intelligence_runner.py, is
the final sizing and execution authority when PSE is available.

This file is retained for:
    - fd_* backward-compatible output fields consumed by morning validation,
      the Intelligence Lab, and the manifest
    - fallback operation if PSE is unavailable (PSE import failure)
    - audit comparison against PSE verdicts
    - pattern/direction conflict flagging via pattern_direction_alignment()

It must NOT override PSE when PSE is active.

When PSE is active, downstream modules treat:
    pse_execution_mode   — authoritative execution mode
    pse_final_size       — authoritative position size
    pse_block_reason     — authoritative block reason

as the execution fields. fd_* fields are compatibility/audit fields only,
unless the runner explicitly falls back to FinalDecisionEngine because PSE
is unavailable.

HIERARCHY
---------
Inputs consumed (in precedence order):
    1. EVResult.ev_conf_adj         — primary economic signal
    2. EVResult.ev_status           — EV quality classification
    3. EVResult.recommended_size_mult — EV engine size guidance
    4. sb_veto_adj                  — Superbrain active size penalty
    5. mp_hard_block_reason         — Monetisation hard block (contract failure)
    6. eil_v3_verdict               — EIL microstructure verdict

DECISION RULES
--------------
BLOCK if ANY of:
    - mp_hard_block_reason is set AND severity = HARD
    - EVResult.ev_status == FAIL and ev_conf_adj < -0.10
    - EVResult.ev_status == DATA_WEAK and data_quality_score < 40

REDUCE if:
    - EVResult.ev_status == WEAK_PASS
    - OR EIL flags microstructure issue (not hard block)
    - OR Superbrain veto active

EXECUTE if:
    - ev_status in [PASS_SMALL, PASS, PASS_HIGH]
    - AND no hard block active

Size is determined by:
    EVResult.recommended_size_mult
    × Superbrain size penalty (if veto active: × 0.40)
    × EIL size multiplier (microstructure quality)
    × Regime size adjustment

OUTPUT FIELDS (written to row)
-------------------------------
    fd_verdict          EXECUTE | EXECUTE_WITH_CAUTION | REDUCE | BLOCK | WATCHLIST
    fd_size             Final position size (0.0–1.5)
    fd_reason           Primary reason for verdict
    fd_ev_used          ev_conf_adj value used for decision
    fd_confidence       0–100 composite confidence in verdict
    fd_reroute_flag     True if contract_efficiency_flag set (try better contract)
    fd_watchlist_reason If WATCHLIST, why the idea is preserved
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ev_engine_v2 import EVResult


# ─────────────────────────────────────────────────────────────────────────────
# FIX-PATTERN-ALIGN (v1.1): Pattern / Direction Conflict Detection
# ─────────────────────────────────────────────────────────────────────────────
# Wyckoff accumulation patterns are bullish by definition.
# A PUT tagged against WYCKOFF_ACCUMULATION is a structural contradiction
# UNLESS the pattern is a FAILED accumulation (spring failure, upthrust etc.)
# The pipeline cannot determine that distinction from tag alone — flag it.
# Downstream: the Soul-of-Chart read must confirm the contradiction before execution.

_BULLISH_PATTERNS = frozenset({
    "WYCKOFF_ACCUMULATION", "SPRING", "SOS", "LPS",
    "SHAKEOUT", "SECONDARY_TEST", "ACCUMULATION",
})
_BEARISH_PATTERNS = frozenset({
    "DISTRIBUTION", "UPTHRUST", "LPSY", "BREAKDOWN",
    "SOW", "WYCKOFF_DISTRIBUTION", "FAILED_RALLY",
})
_AMBIGUOUS_PATTERNS = frozenset({
    "TRANSITIONAL", "CONSOLIDATION", "COILING", "MIXED",
    "SIDEWAYS_RANGING", "SIDEWAYS_BUILDING",
})


def _normalise_direction(direction: str) -> str:
    """
    ISSUE 4: Normalise pipeline direction labels into CALL / PUT.

    The pipeline uses several aliases depending on the layer that wrote the field:
        LONG_PUT, BEARISH, BUY_PUT  → PUT
        LONG_CALL, BULLISH, BUY_CALL → CALL

    Without this normaliser, LONG_PUT vs WYCKOFF_ACCUMULATION returns
    AMBIGUOUS_REVIEW_REQUIRED instead of CONFLICT_REQUIRES_CHART_REVIEW,
    silently missing the structural contradiction.
    """
    d = str(direction).strip().upper()
    if d in ("CALL", "LONG_CALL", "BULLISH", "BUY_CALL"):
        return "CALL"
    if d in ("PUT", "LONG_PUT", "BEARISH", "BUY_PUT"):
        return "PUT"
    return "UNKNOWN"


def _normalise_pattern(pattern: str) -> str:
    """
    ISSUE 5: Normalise compound and pipe-separated Wyckoff pattern labels.

    Accepts tags such as:
        WYCKOFF_ACCUMULATION|SPRING  → WYCKOFF_ACCUMULATION
        ACCUMULATION_PHASE_D         → WYCKOFF_ACCUMULATION
        DISTRIBUTION_UPTHRUST        → WYCKOFF_DISTRIBUTION

    Without this, compound patterns route to UNKNOWN_REVIEW_REQUIRED
    and the CONFLICT gate never fires even when the contradiction is clear.
    """
    p = str(pattern).strip().upper()
    if not p:
        return "UNKNOWN"

    # Flatten compound labels to token set
    joined = p.replace("|", "_").replace("-", "_").replace(" ", "_")

    if "DISTRIBUTION" in joined:
        return "WYCKOFF_DISTRIBUTION"
    if "ACCUMULATION" in joined:
        return "WYCKOFF_ACCUMULATION"
    if "UPTHRUST" in joined:
        return "UPTHRUST"
    # Exact-match short labels
    tokens = set(joined.split("_"))
    for label in ("SPRING", "SOS", "LPS", "SHAKEOUT", "SECONDARY_TEST",
                  "LPSY", "BREAKDOWN", "SOW", "FAILED_RALLY"):
        if label in tokens:
            return label
    for marker in ("TRANSITIONAL", "CONSOLIDATION", "COILING", "MIXED", "SIDEWAYS"):
        if marker in joined:
            return "TRANSITIONAL"
    return joined


def pattern_direction_alignment(pattern: str, direction: str) -> str:
    """
    FIX-PATTERN-ALIGN (v1.1): Detect Wyckoff pattern vs trade direction conflicts.

    Returns one of:
        ALIGNED                    — pattern and direction are consistent
        CONFLICT_REQUIRES_CHART_REVIEW — structural contradiction, needs human review
        AMBIGUOUS_REVIEW_REQUIRED  — pattern is non-directional, cannot auto-confirm
        UNKNOWN_REVIEW_REQUIRED    — pattern not in known taxonomy

    The manifest must not allow CONFLICT_REQUIRES_CHART_REVIEW to pass
    without explicit operator sign-off.
    """
    # ISSUE 4+5: normalise both pattern and direction before comparison
    p = _normalise_pattern(pattern)
    d = _normalise_direction(direction)

    if p in _BULLISH_PATTERNS:
        if d == "CALL":
            return "ALIGNED"
        elif d == "PUT":
            return "CONFLICT_REQUIRES_CHART_REVIEW"
        return "AMBIGUOUS_REVIEW_REQUIRED"

    if p in _BEARISH_PATTERNS:
        if d == "PUT":
            return "ALIGNED"
        elif d == "CALL":
            return "CONFLICT_REQUIRES_CHART_REVIEW"
        return "AMBIGUOUS_REVIEW_REQUIRED"

    if p in _AMBIGUOUS_PATTERNS:
        return "AMBIGUOUS_REVIEW_REQUIRED"

    return "UNKNOWN_REVIEW_REQUIRED"




# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# EV thresholds for graduated decisions
# FIX RC-9 (2026-04-16): Lowered to match live actuarial EV range (0.002–0.022).
# Prior thresholds (0.10 small, 0.25 full) were calibrated for a different
# EV scale and caused the entire 0.0–0.10 band to route to WATCHLIST/REDUCE.
EV_HARD_BLOCK    = -0.10   # Below this → BLOCK (unchanged — genuine negative EV)
EV_REDUCE        = 0.00    # Below this → REDUCE or EXECUTE_WITH_CAUTION (unchanged)
EV_EXECUTE_SMALL = 0.05    # Below this → EXECUTE small (was 0.10)
EV_EXECUTE       = 0.15    # Above this → EXECUTE full  (was 0.25)

# Superbrain veto size penalty
SB_VETO_SIZE_PENALTY = 0.40

# EIL microstructure multiplier map
# FIX-07: expanded to cover all tokens EIL composite engine (execution_intelligence.py)
# can emit, in addition to the normalised tokens the runner produces after FIX-02.
EIL_SIZE_MAP = {
    # Normalised tokens (produced by runner FIX-02 token map)
    "HIGH_CONVICTION":           1.00,
    "EXECUTE":                   1.00,
    "WATCHLIST":                 0.50,
    "BLOCKED":                   0.25,   # EIL block = size penalty, not kill
    # Raw EIL composite engine tokens (verbatim from execution_intelligence.py)
    "EXECUTE_NOW":               1.00,   # alias for EXECUTE
    "EXECUTE_WITH_CAUTION":      0.60,   # moderate penalty — caution warranted
    "EXECUTE_DEFER":             0.40,   # significant penalty — conditions poor
    "STAND_DOWN_MICROSTRUCTURE": 0.25,   # alias for BLOCKED
    # Default — EIL not run or field absent
    "":                          1.00,
}

# Regime size adjustment
REGIME_SIZE_MAP = {
    "RISK_ON":               1.10,
    "BULLISH":               1.10,
    # ENHANCEMENT 2 (2026-04-16): sub-regime size adjustments
    "TRANSITIONAL_BULLISH":  1.00,   # slight tailwind — standard size
    "TRANSITIONAL_NEUTRAL":  0.90,   # base TRANSITIONAL
    "TRANSITIONAL":          0.90,   # backward compat
    "TRANSITIONAL_BEARISH":  0.75,   # same caution as RISK_OFF
    "NEUTRAL":               0.90,
    "RISK_OFF":              0.75,
    "BEARISH":               0.75,
    "FLIPPED":               0.55,
}


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FinalDecision:
    """
    Single authoritative trade decision.
    Written to output row as fd_* columns.
    """
    fd_verdict:                   str   = "BLOCK"
    fd_size:                      float = 0.0
    fd_reason:                    str   = "UNINITIALISED"
    fd_ev_used:                   float = 0.0
    fd_confidence:                float = 0.0
    fd_reroute_flag:              bool  = False
    fd_watchlist_reason:          Optional[str] = None
    # FIX-PATTERN-ALIGN (v1.1): pattern vs direction conflict flag
    fd_pattern_direction_align:   str   = "UNKNOWN_REVIEW_REQUIRED"
    # v1.1: sector alignment — set from input row fields written by sector_alignment.py
    fd_macro_sector_bias:         str   = "UNKNOWN"
    fd_sector_alignment_flag:     str   = "NEUTRAL"
    fd_sector_alignment_score:    float = 1.00

    def to_row_dict(self) -> dict:
        return {
            "fd_verdict":                  self.fd_verdict,
            "fd_size":                     round(self.fd_size, 4),
            "fd_reason":                   self.fd_reason,
            "fd_ev_used":                  round(self.fd_ev_used, 6),
            "fd_confidence":               round(self.fd_confidence, 1),
            "fd_reroute_flag":             self.fd_reroute_flag,
            "fd_watchlist_reason":         self.fd_watchlist_reason or "",
            "fd_pattern_direction_align":  self.fd_pattern_direction_align,
            "fd_macro_sector_bias":        self.fd_macro_sector_bias,
            "fd_sector_alignment_flag":    self.fd_sector_alignment_flag,
            "fd_sector_alignment_score":   round(self.fd_sector_alignment_score, 4),
        }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

import math as _math


def _safe(v, default=0.0):
    """
    ISSUE 2: Safely parse numeric values from CSV rows.
    Handles: None, "", "nan", "inf", "-inf", invalid strings.
    Returns default for non-finite values — float("inf") now rejected.
    """
    try:
        if v is None:
            return default
        f = float(v)
        if _math.isnan(f) or _math.isinf(f):
            return default
        return f
    except (TypeError, ValueError, OverflowError):
        return default


def _s(v, default=""):
    """
    ISSUE 3: Safe string parser — numpy dependency removed.
    numpy is in the pipeline environment but has no role in this function.
    """
    try:
        if v is None:
            return default
        if isinstance(v, float) and v != v:  # float NaN without numpy
            return default
        s = str(v).strip()
        if s.lower() in ("nan", "none", "null", "na", "n/a", ""):
            return default
        return s
    except (TypeError, ValueError):
        return default


def _b(v, default=False):
    if isinstance(v, bool): return v
    try: return str(v).strip().upper() in ("TRUE", "1", "YES")
    except: return default


# ─────────────────────────────────────────────────────────────────────────────
# FINAL DECISION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class FinalDecisionEngine:
    """
    Arbitrates between all pipeline layers and produces one final verdict.
    Stateless — no side effects.
    """

    def decide(self, row: dict, ev_result: EVResult) -> FinalDecision:
        """
        Produce the final trade decision.

        Args:
            row:        Full signal row dict (contains all upstream layer outputs)
            ev_result:  EVResult from EVEngineV2.evaluate()

        Returns:
            FinalDecision — authoritative verdict with size and reasoning
        """
        ev      = ev_result.ev_conf_adj
        ev_stat = ev_result.ev_status

        # ── FIX-PATTERN-ALIGN (v1.1): Compute pattern/direction alignment early ──
        # Read wyckoff pattern and direction from row. Multiple column aliases
        # supported — pipeline uses different column names across layers.
        _pattern_raw   = _s(
            row.get("wyckoff_phase_bucket") or
            row.get("dominant_pattern") or
            row.get("pattern_tag") or
            row.get("wyckoff_phase") or ""
        ).upper()
        _direction_raw = _s(
            row.get("direction") or
            row.get("trade_direction") or
            row.get("options_direction") or ""
        ).upper()
        _pattern_align = pattern_direction_alignment(_pattern_raw, _direction_raw)
        # ──────────────────────────────────────────────────────────────────────

        # ── Layer signals ─────────────────────────────────────────────────────
        mp_block     = _s(row.get("mp_hard_block_reason", ""))
        _SB_VETO_TRIGGERS = {"STAND_DOWN", "ARMED"}
        _sb_raw  = _s(row.get("sb_veto_adj", "NONE")).upper().split("|")[0].strip()
        sb_veto  = _sb_raw in _SB_VETO_TRIGGERS
        eil_verdict  = _s(row.get("eil_v3_verdict", "")).upper()
        regime       = _s(row.get("regime_state", row.get("regime", "TRANSITIONAL"))).upper().replace(" ", "_")
        data_quality = _safe(row.get("data_quality_score"), 100.0)

        # ── ISSUE 6: Pattern/direction structural conflict gate ────────────────
        # The docstring stated the manifest must not allow CONFLICT to auto-execute
        # without operator sign-off. Previously the conflict was computed but the
        # verdict was never enforced — EXECUTE could still result.
        # Now: CONFLICT → WATCHLIST, size=0, unless pattern_direction_override=True.
        _pattern_override = _b(row.get("pattern_direction_override"), False)
        if _pattern_align == "CONFLICT_REQUIRES_CHART_REVIEW" and not _pattern_override:
            return FinalDecision(
                fd_verdict            = "WATCHLIST",
                fd_size               = 0.0,
                fd_reason             = "PATTERN_DIRECTION_CONFLICT_REQUIRES_CHART_REVIEW",
                fd_ev_used            = ev_result.ev_conf_adj,
                fd_confidence         = 70.0,
                fd_reroute_flag       = ev_result.contract_efficiency_flag,
                fd_watchlist_reason   = "Pattern and option direction conflict. Soul-of-Chart review required.",
                fd_pattern_direction_align = _pattern_align,
            )
        # ──────────────────────────────────────────────────────────────────────

        # ── Hard block checks (ordered by severity) ───────────────────────────

        # 1. Monetisation policy verdict — tiered routing
        # ISSUE 7: old code used `len(mp_block) > 0` so ANY non-empty value
        # produced BLOCK — including DATA_GAP:NO_CONTRACT_PRICE and REVIEW_ONLY.
        # Data gaps and review states should preserve the idea for morning
        # validation, not kill it. Real structural failures remain hard BLOCKs.
        _MP_HARD_BLOCK_STRINGS = {
            # MP free-text hard failures
            "SPREAD TOO WIDE", "DTE TOO LOW FOR MONETISATION",
            "THETA DRAG TOO HIGH", "INSUFFICIENT RUNWAY VS BREAKEVEN",
            "NEGATIVE RR AND NEGATIVE EV", "LIVE IV DISTORTION TOO HIGH",
            "STRUCTURE / THESIS INVALID", "STRUCTURE CONFIDENCE TOO LOW",
            # EV engine coded structural failures
            "BREAKEVEN_FAIL", "SPREAD_UNUSABLE", "ZERO_RUNWAY",
        }
        _MP_DATA_GAP_MARKERS  = ("DATA_GAP", "NO_CONTRACT_PRICE", "REQUIRED DATA MISSING",
                                  "STALE DATA", "MISSING",)
        _MP_REVIEW_MARKERS    = ("REVIEW_ONLY", "CONTEXT_ONLY", "HOLD",)

        if mp_block:
            _mp_upper = mp_block.upper()

            if any(x in _mp_upper for x in _MP_REVIEW_MARKERS):
                return FinalDecision(
                    fd_verdict          = "WATCHLIST",
                    fd_size             = 0.0,
                    fd_reason           = f"MP_REVIEW_ONLY:{mp_block}",
                    fd_ev_used          = ev_result.ev_conf_adj,
                    fd_confidence       = 70.0,
                    fd_reroute_flag     = ev_result.contract_efficiency_flag,
                    fd_watchlist_reason = "Monetisation policy requires review; not a structural rejection.",
                    fd_pattern_direction_align = _pattern_align,
                )

            if any(x in _mp_upper for x in _MP_DATA_GAP_MARKERS):
                return FinalDecision(
                    fd_verdict          = "WATCHLIST",
                    fd_size             = 0.0,
                    fd_reason           = f"MP_DATA_GAP:{mp_block}",
                    fd_ev_used          = ev_result.ev_conf_adj,
                    fd_confidence       = 65.0,
                    fd_reroute_flag     = True,
                    fd_watchlist_reason = "Contract/economic data gap. Preserve for live quote validation.",
                    fd_pattern_direction_align = _pattern_align,
                )

            if any(x in _mp_upper for x in _MP_HARD_BLOCK_STRINGS):
                return FinalDecision(
                    fd_verdict          = "BLOCK",
                    fd_size             = 0.0,
                    fd_reason           = f"MP_HARD:{mp_block}",
                    fd_ev_used          = ev_result.ev_conf_adj,
                    fd_confidence       = 95.0,
                    fd_reroute_flag     = ev_result.contract_efficiency_flag,
                    fd_pattern_direction_align = _pattern_align,
                )

            # Unknown MP reason: fail-safe to WATCHLIST, not BLOCK.
            # Preserves the idea for morning validation rather than silently killing it.
            return FinalDecision(
                fd_verdict          = "WATCHLIST",
                fd_size             = 0.0,
                fd_reason           = f"MP_UNKNOWN_REVIEW:{mp_block}",
                fd_ev_used          = ev_result.ev_conf_adj,
                fd_confidence       = 60.0,
                fd_reroute_flag     = ev_result.contract_efficiency_flag,
                fd_watchlist_reason = "Unknown monetisation policy reason. Manual review required.",
                fd_pattern_direction_align = _pattern_align,
            )

        # 2. EV hard fail
        if ev_stat == "FAIL" and ev < EV_HARD_BLOCK:
            return FinalDecision(
                fd_verdict  = "BLOCK",
                fd_size     = 0.0,
                fd_reason   = f"EV_FAIL:{ev_result.primary_reason}",
                fd_ev_used  = ev,
                fd_confidence = 85.0,
                fd_reroute_flag = ev_result.contract_efficiency_flag,
                fd_watchlist_reason = None,
                fd_pattern_direction_align = _pattern_align,
            )

        # 3. Data quality too low for any decision
        if ev_stat == "DATA_WEAK" and data_quality < 30:
            return FinalDecision(
                fd_verdict  = "BLOCK",
                fd_size     = 0.0,
                fd_reason   = "DATA_WEAK:QUALITY_TOO_LOW",
                fd_ev_used  = ev,
                fd_confidence = 60.0,
                fd_pattern_direction_align = _pattern_align,
            )

        # ── Watchlist: preserve idea even when contract is bad ────────────────
        if ev_result.contract_efficiency_flag and ev > 0:
            # Good directional idea, bad contract — preserve for rerouting
            watchlist_reason = f"GOOD_THESIS_BAD_CONTRACT (eff={ev_result.contract_efficiency:.2f})"
            # Still execute at small size if EV positive
        else:
            watchlist_reason = None

        # ── Graduated verdict ─────────────────────────────────────────────────
        base_size = ev_result.recommended_size_mult

        if ev < EV_REDUCE and ev >= EV_HARD_BLOCK:
            # Marginal — WEAK_PASS or FAIL near boundary
            verdict   = "BLOCK" if ev_stat == "FAIL" else "WATCHLIST"
            base_size = 0.0
            reason    = f"NEAR_ZERO_EV:{ev_result.primary_reason}"
            if verdict == "WATCHLIST":
                watchlist_reason = watchlist_reason or "NEAR_ZERO_EV"

        elif ev < EV_EXECUTE_SMALL:
            # FIX RC-9 (2026-04-16): Allow PASS_SMALL to execute at probe size
            # when EIL explicitly confirms execution quality (score >= 65) and
            # Superbrain has not vetoed. Previously PASS_SMALL → WATCHLIST
            # unconditionally, which meant all ev_conf_adj in 0.0–0.10 range
            # (the majority of real-world signals) produced zero output.
            #
            # Gate: EIL composite score >= 65 acts as the microstructure
            # confirmation required before committing any capital to a weak edge.
            # At 25% max size the risk is contained. Operator can override up.
            _eil_score_raw = float(row.get("eil_composite_score", 0) or 0)
            _eil_confirms  = _eil_score_raw >= 65 and not sb_veto

            if ev_result.ev_status in ("PASS_SMALL", "YES_SMALL") and _eil_confirms:
                verdict   = "EXECUTE_WITH_CAUTION"
                base_size = min(base_size, 0.25)   # probe size — max 25% of standard
                reason    = f"PASS_SMALL_EIL_CONFIRMED:{ev_result.primary_reason}"
            elif ev_result.ev_status in ("PASS_SMALL", "YES_SMALL"):
                verdict   = "WATCHLIST"
                base_size = 0.0
                reason    = f"WEAK_EDGE_WATCHLIST:{ev_result.primary_reason}"
                watchlist_reason = watchlist_reason or f"LOW_POS_EV ({ev:+.4f}) EIL_SCORE={_eil_score_raw:.0f}<65"
            else:
                # Positive EV, not classified as tiny — execute small with caution
                verdict   = "EXECUTE_WITH_CAUTION"
                base_size = min(base_size, 0.50)
                reason    = ev_result.primary_reason

        elif ev < EV_EXECUTE:
            # Good EV — standard execute
            verdict   = "EXECUTE"
            base_size = min(base_size, 1.00)
            reason    = ev_result.primary_reason

        else:
            # Strong EV — full or aggressive execute
            verdict   = "EXECUTE"
            base_size = base_size  # up to 1.25
            reason    = ev_result.primary_reason

        # ── FIX-5: Superbrain veto is now SOVEREIGN ──────────────────────────
        # Previously veto only applied a size penalty. Logs showed SB_VETO+LOW_POS_EV
        # still producing EXECUTE_WITH_CAUTION — veto was advisory, not blocking.
        # Now: SB_VETO + any EXECUTE verdict → WATCHLIST (not just penalty).
        # SB_VETO + already-WATCHLIST → remains WATCHLIST (no double downgrade).
        # Override permitted only if an explicit override_reason field is set
        # AND EIL composite score exceeds 80 (strong execution conditions).
        if sb_veto and verdict not in ("BLOCK", "WATCHLIST"):
            _eil_score = float(row.get("eil_composite_score", 0) or 0)
            _override  = str(row.get("sb_veto_override_reason", "") or "").strip()
            _can_override = bool(_override) and _eil_score >= 80
            if _can_override:
                # Operator explicitly overrode veto with strong EIL confirmation
                base_size *= SB_VETO_SIZE_PENALTY
                reason     = f"SB_VETO_OVERRIDE+{reason}"
                if verdict == "EXECUTE":
                    verdict = "EXECUTE_WITH_CAUTION"
            else:
                # FIX-5: Veto is sovereign — downgrade to WATCHLIST
                verdict          = "WATCHLIST"
                base_size        = 0.0
                reason           = f"SB_VETO_SOVEREIGN:{reason}"
                watchlist_reason = watchlist_reason or "SB_VETO_ACTIVE"

        # ── Apply EIL microstructure multiplier ──────────────────────────────
        # FIX-7 companion: runner already blocks on EIL BLOCKED before reaching FDE.
        # If somehow a BLOCKED row reaches here (e.g. called directly), respect it.
        eil_mult = EIL_SIZE_MAP.get(eil_verdict, 1.0)
        if eil_verdict == "BLOCKED" and verdict not in ("BLOCK", "WATCHLIST"):
            verdict   = "WATCHLIST"   # FIX-7: BLOCKED → WATCHLIST, not execute
            base_size = 0.0
            reason    = f"EIL_BLOCKED:{reason}"
        elif eil_verdict not in ("", "EXECUTE", "EXECUTE_NOW", "HIGH_CONVICTION", "BLOCKED"):
            # Partial penalty for CAUTION / DEFER / WATCHLIST
            base_size *= eil_mult
            reason     = f"EIL_{eil_verdict}+{reason}"

        # ── Apply regime size adjustment ──────────────────────────────────────
        # ISSUE 8: unknown regime → neutral 1.00, not 0.90 penalty.
        # Consistent with ev_engine_v2 drift-status fix — unknown = absent, not bad.
        regime_mult = REGIME_SIZE_MAP.get(regime, 1.00)

        # ── v1.1: Apply sector alignment multiplier (4th multiplier in chain) ─
        # sector_alignment_score is set by sector_alignment.py and written to
        # signal rows by superbrain / options intelligence. Values:
        #   TAILWIND  = 1.10   NEUTRAL = 1.00   MIXED = 0.80
        #   HEADWIND  = 0.55   UNKNOWN = 0.80
        # If sector_alignment_flag == BLOCK AND sb_veto not already active,
        # downgrade to WATCHLIST (high-conviction headwind = hard gate).
        _sector_score = _safe(row.get("sector_alignment_score", 1.00))
        _sector_flag  = _s(row.get("sector_alignment_flag", "NEUTRAL")).upper()
        _sector_bias  = _s(row.get("macro_sector_bias", "NEUTRAL")).upper()

        if _sector_flag == "BLOCK" and verdict not in ("BLOCK", "WATCHLIST"):
            verdict   = "WATCHLIST"
            base_size = 0.0
            reason    = f"SECTOR_HEADWIND_BLOCK({_sector_bias}):{reason}"
        elif _sector_score != 1.00 and _sector_score > 0:
            base_size *= _sector_score
            if _sector_flag in ("REDUCE",):
                reason = f"SECTOR_{_sector_bias}_PENALISED({_sector_score:.2f}):{reason}"
            elif _sector_flag == "BOOST":
                reason = f"SECTOR_{_sector_bias}_BOOSTED({_sector_score:.2f}):{reason}"

        final_size = round(max(0.0, base_size * regime_mult), 4)

        # ── Confidence in verdict ─────────────────────────────────────────────
        conf = _compute_confidence(ev, ev_result, data_quality, eil_verdict)

        return FinalDecision(
            fd_verdict           = verdict,
            fd_size              = final_size,
            fd_reason            = reason,
            fd_ev_used           = round(ev, 6),
            fd_confidence        = conf,
            fd_reroute_flag      = ev_result.contract_efficiency_flag,
            fd_watchlist_reason  = watchlist_reason,
            fd_pattern_direction_align = _pattern_align,
            fd_macro_sector_bias       = _sector_bias,
            fd_sector_alignment_flag   = _sector_flag,
            fd_sector_alignment_score  = round(_sector_score, 4),
        )


def _compute_confidence(
    ev: float,
    ev_result: EVResult,
    data_quality: float,
    eil_verdict: str,
) -> float:
    """
    Composite confidence in the final verdict (0–100).
    Higher confidence = verdict is more trustworthy.
    """
    # Base from EV magnitude
    ev_conf = min(abs(ev) * 200, 50.0)

    # Quality components
    q_conf  = ev_result.quality_score * 0.30
    dq_conf = (data_quality / 100.0) * 20.0

    # EIL alignment bonus — FIX-07: include EXECUTE_NOW as peer of EXECUTE
    eil_bonus = 10.0 if eil_verdict in ("EXECUTE", "HIGH_CONVICTION", "EXECUTE_NOW") else 0.0

    return round(min(ev_conf + q_conf + dq_conf + eil_bonus, 100.0), 1)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL CONVENIENCE FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

_engine = FinalDecisionEngine()


def make_final_decision(row: dict, ev_result: EVResult) -> FinalDecision:
    """
    Convenience function — single call interface for the runner.
    Usage:
        from final_decision_engine import make_final_decision
        fd = make_final_decision(row, ev_result)
        row.update(fd.to_row_dict())
    """
    return _engine.decide(row, ev_result)


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from ev_engine_v2 import EVEngineV2, EVInputs, ev_inputs_from_row

    eng    = EVEngineV2()
    fde    = FinalDecisionEngine()

    cases = [
        ("TERN — good ev, no veto", {
            "ticker": "TERN", "signal_price": 25.0, "composite": 60,
            "win_rate_10d": 0.61,   # ISSUE 9: was 61.0 — correct scale is 0–1
            "expected_move_10d": 0.07,
            "delta": 0.45, "theta": 0.03, "option_mid": 1.20,
            "iv_rank": 0.35, "dte": 18, "spread_pct": 0.06,
            "regime_state": "RISK_ON", "data_quality_score": 85,
            "breakeven_pass_live": True, "runway_pct": 3.5,
            "survival_prob": 0.68, "convexity_score": 0.60,
            "prob_breakout": 0.55, "prob_rejection": 0.25, "prob_drift": 0.20,
            "sb_veto_adj": False, "eil_v3_verdict": "EXECUTE",
        }),
        ("XYZ — zero data, EIL block", {
            "ticker": "XYZ", "signal_price": 50.0, "composite": 20,
            "win_rate_10d": 0.0, "delta": 0.35, "theta": 0.08,
            "option_mid": 1.80, "iv_rank": 0.75, "dte": 5, "spread_pct": 0.25,
            "regime_state": "RISK_OFF", "data_quality_score": 25,
            "breakeven_pass_live": False, "runway_pct": 0.0,
            "sb_veto_adj": True, "eil_v3_verdict": "BLOCKED",
        }),
        ("NVDA — good setup, sb veto active", {
            "ticker": "NVDA", "signal_price": 875.0, "composite": 65,
            "win_rate_10d": 0.61,   # ISSUE 9: was 61.0
            "expected_move_10d": 0.065,
            "delta": 0.42, "theta": 0.05, "option_mid": 12.50,
            "iv_rank": 0.40, "dte": 14, "spread_pct": 0.07,
            "regime_state": "TRANSITIONAL", "data_quality_score": 80,
            "breakeven_pass_live": True, "runway_pct": 2.5,
            "survival_prob": 0.62, "convexity_score": 0.45,
            "prob_breakout": 0.50, "sb_veto_adj": True, "eil_v3_verdict": "EXECUTE",
        }),
    ]

    print("\n══════════════════════════════════════════════════")
    print("  AVSHUNTER Final Decision Engine — Smoke Test")
    print("══════════════════════════════════════════════════\n")

    for label, row in cases:
        ev_in  = ev_inputs_from_row(row)
        ev_res = eng.evaluate(ev_in)
        fd     = fde.decide(row, ev_res)

        print(f"  {label}")
        print(f"    ev_final={ev_res.ev_final:+.4f} | ev_conf_adj={ev_res.ev_conf_adj:+.4f} | ev_status={ev_res.ev_status}")
        print(f"    fd_verdict={fd.fd_verdict} | fd_size={fd.fd_size} | fd_reason={fd.fd_reason}")
        print(f"    fd_confidence={fd.fd_confidence} | reroute={fd.fd_reroute_flag}")
        print()

    # ── ISSUE 10: QA acceptance tests for real risk cases ────────────────────
    print("══════════════════════════════════════════════════")
    print("  Final Decision Engine — QA Acceptance Tests")
    print("══════════════════════════════════════════════════\n")

    def _assert(label, cond, detail=""):
        if not cond:
            raise AssertionError(f"QA FAIL — {label}: {detail}")
        print(f"  ✓ {label}")

    # QA-1: LONG_PUT normalised to PUT and conflicts with accumulation
    _align = pattern_direction_alignment("WYCKOFF_ACCUMULATION", "LONG_PUT")
    _assert(
        "LONG_PUT vs WYCKOFF_ACCUMULATION → CONFLICT",
        _align == "CONFLICT_REQUIRES_CHART_REVIEW",
        f"got={_align}",
    )

    # QA-2: LONG_CALL aligned with accumulation
    _align2 = pattern_direction_alignment("WYCKOFF_ACCUMULATION", "LONG_CALL")
    _assert(
        "LONG_CALL vs WYCKOFF_ACCUMULATION → ALIGNED",
        _align2 == "ALIGNED",
        f"got={_align2}",
    )

    # QA-3: Compound pattern normalises correctly
    _align3 = pattern_direction_alignment("ACCUMULATION_PHASE_D", "PUT")
    _assert(
        "ACCUMULATION_PHASE_D vs PUT → CONFLICT",
        _align3 == "CONFLICT_REQUIRES_CHART_REVIEW",
        f"got={_align3}",
    )

    # QA-4: Pattern conflict routes fd_verdict to WATCHLIST (Issue 6 enforcement)
    _base_row = {
        "ticker": "TEST", "direction": "LONG_PUT",
        "wyckoff_phase_bucket": "WYCKOFF_ACCUMULATION",
        "signal_price": 100, "target_price": 90, "stop_price": 105,
        "win_rate_10d": 0.62, "expected_move_10d": 0.07,
        "option_mid": 2.0, "dte": 20, "spread_pct": 0.05,
        "runway_pct": 3.0, "breakeven_pass_live": True,
        "eil_v3_verdict": "EXECUTE",
    }
    ev_conflict = eng.evaluate(ev_inputs_from_row(_base_row))
    fd_conflict = fde.decide(_base_row, ev_conflict)
    _assert(
        "Pattern conflict → WATCHLIST",
        fd_conflict.fd_verdict == "WATCHLIST",
        f"got={fd_conflict.fd_verdict} reason={fd_conflict.fd_reason}",
    )

    # QA-5: With override flag, conflict is not blocked
    _override_row = {**_base_row, "pattern_direction_override": True}
    ev_ov  = eng.evaluate(ev_inputs_from_row(_override_row))
    fd_ov  = fde.decide(_override_row, ev_ov)
    _assert(
        "Pattern conflict with override=True → not WATCHLIST",
        fd_ov.fd_verdict != "WATCHLIST" or fd_ov.fd_reason != "PATTERN_DIRECTION_CONFLICT_REQUIRES_CHART_REVIEW",
        f"got={fd_ov.fd_verdict}",
    )

    # QA-6: MP DATA_GAP → WATCHLIST not BLOCK (Issue 7)
    _gap_row = {
        "ticker": "GAP", "direction": "CALL",
        "wyckoff_phase_bucket": "WYCKOFF_ACCUMULATION",
        "signal_price": 100, "target_price": 112, "stop_price": 95,
        "win_rate_10d": 0.62, "expected_move_10d": 0.07,
        "option_mid": 2.0, "dte": 20, "spread_pct": 0.05,
        "runway_pct": 3.0, "breakeven_pass_live": True,
        "mp_hard_block_reason": "DATA_GAP:NO_CONTRACT_PRICE",
        "eil_v3_verdict": "EXECUTE",
    }
    ev_gap = eng.evaluate(ev_inputs_from_row(_gap_row))
    fd_gap = fde.decide(_gap_row, ev_gap)
    _assert(
        "MP DATA_GAP → WATCHLIST (not BLOCK)",
        fd_gap.fd_verdict == "WATCHLIST",
        f"got={fd_gap.fd_verdict} reason={fd_gap.fd_reason}",
    )

    # QA-7: MP REVIEW_ONLY → WATCHLIST
    _review_row = {**_gap_row, "mp_hard_block_reason": "REVIEW_ONLY"}
    ev_rev = eng.evaluate(ev_inputs_from_row(_review_row))
    fd_rev = fde.decide(_review_row, ev_rev)
    _assert(
        "MP REVIEW_ONLY → WATCHLIST",
        fd_rev.fd_verdict == "WATCHLIST",
        f"got={fd_rev.fd_verdict}",
    )

    # QA-8: MP structural failure → BLOCK
    _hard_row = {**_gap_row, "mp_hard_block_reason": "SPREAD TOO WIDE"}
    ev_hard = eng.evaluate(ev_inputs_from_row(_hard_row))
    fd_hard = fde.decide(_hard_row, ev_hard)
    _assert(
        "MP SPREAD TOO WIDE → BLOCK",
        fd_hard.fd_verdict == "BLOCK",
        f"got={fd_hard.fd_verdict}",
    )

    # QA-9: _safe("inf") returns default
    _assert(
        "_safe('inf') returns default 0.0",
        _safe("inf", 0.0) == 0.0,
        f"got={_safe('inf', 0.0)}",
    )

    # QA-10: _safe("-inf") returns default
    _assert(
        "_safe('-inf') returns default 0.0",
        _safe("-inf", 0.0) == 0.0,
        f"got={_safe('-inf', 0.0)}",
    )

    # QA-11: SB veto string downgrades to WATCHLIST
    _veto_row = {
        "ticker": "VETO", "direction": "CALL",
        "wyckoff_phase_bucket": "WYCKOFF_ACCUMULATION",
        "signal_price": 100, "target_price": 112, "stop_price": 95,
        "win_rate_10d": 0.62, "expected_move_10d": 0.07,
        "option_mid": 2.0, "dte": 20, "spread_pct": 0.05,
        "runway_pct": 3.0, "breakeven_pass_live": True,
        "sb_veto_adj": "STAND_DOWN|V2_NO_RUNWAY",
        "eil_v3_verdict": "EXECUTE",
    }
    ev_veto = eng.evaluate(ev_inputs_from_row(_veto_row))
    fd_veto = fde.decide(_veto_row, ev_veto)
    _assert(
        "SB veto STAND_DOWN|V2_NO_RUNWAY → WATCHLIST",
        fd_veto.fd_verdict == "WATCHLIST",
        f"got={fd_veto.fd_verdict}",
    )

    print("\nAll FDE QA acceptance tests passed ✓")
