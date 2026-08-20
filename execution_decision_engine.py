#!/usr/bin/env python3
"""
AVSHUNTER — Execution Decision Engine (EDE)
============================================
Version : 4.1.1
Pipeline position (Evening EOD):
    Actuarial Enrichment (pkg["actuarial"])
            ↓
    Backfill + EIL
            ↓
    SuperBrain (sb_final_verdict, wbs_score)
            ↓
    [THIS MODULE] Execution Decision Engine    ← Phase 9.5
            ↓
    PSE / Enhancement Layer (Phase 9B)
            ↓
    Trade Book Builder (Phase 9C)

Pipeline position (Live / Morning Validation):
    EIL (live mode)
            ↓
    Options Intelligence (live chain)
            ↓
    [THIS MODULE] Execution Decision Engine    ← mode="LIVE"
            ↓
    Execution Gate (Phase 11)
            ↓
    Trade

Design
------
Every signal must answer four mandatory questions before a trade is authorised:

    Q1. Is there edge?          → Actuarial score
    Q2. Is timing acceptable?   → EIL score
    Q3. Is the instrument tradeable? → Options hard gates
    Q4. Is risk acceptable?     → PSE structure / breakeven

Outputs per signal
------------------
    "GO"          — all gates pass, high conviction
    "ARMED"       — edge + actuarial pass, timing/options marginal
    "ARMED_HALF"  — partial pass — can size at 50% PSE
    "BLOCKED"     — hard gate failure or insufficient edge — no trade

Output files
------------
    data/output/runs/{run_id}/decisions/
        ede_decisions_{run_id}.csv      — one row per signal, all scores + verdict
        ede_summary_{run_id}.json       — run-level stats
        ede_top_trades_{run_id}.csv     — ranked shortlist (top N by composite score)

Orchestrator hook
-----------------
    from execution_decision_engine import run_decision_engine
    result = run_decision_engine(run_id=run_id, base_dir=BASE_DIR, mode="EOD")
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("execution_decision_engine")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EDEConfig:
    # ── Unified Decision Engine v4 weights ───────────────────────────────────
    # final_score = 0.40*ev_score + 0.30*trigger_score + 0.20*timing_score + 0.10*options_penalty
    W_EV:              float = 0.40
    W_TRIGGER:         float = 0.30
    W_TIMING:          float = 0.20
    W_OPTIONS:         float = 0.10

    # EV normalisation — ev_10d / EV_NORMALISE = score (1% EV = 1.0)
    EV_NORMALISE:      float = 0.01

    # Final score thresholds
    SCORE_GO_MIN:      float = 0.65   # EV positive + strong trigger + good timing
    SCORE_ARMED_MIN:   float = 0.50   # EV positive + single trigger
    SCORE_HALF_MIN:    float = 0.35   # EV positive + trigger but weak options/timing

    # Options penalty multipliers (never block — only reduce size)
    OPT_SPREAD_PENALTY:     float = 0.70   # spread > 8%
    OPT_IV_PENALTY:         float = 0.80   # IVP > 65%
    OPT_BREAKEVEN_PENALTY:  float = 0.60   # breakeven > expected move
    OPT_SPREAD_SOURCE_DERIVED_PENALTY: float = 0.90   # OI-derived spread, verify at open
    OPT_SPREAD_SOURCE_UNAVAILABLE_PENALTY: float = 0.70   # no usable spread source

    # Actuarial confidence thresholds (sample size based)
    CONF_FULL:     int = 50
    CONF_MEDIUM:   int = 20
    CONF_LOW_VAL:  float = 0.3
    CONF_MED_VAL:  float = 0.6
    CONF_HIGH_VAL: float = 1.0

    # Hard gate thresholds (spread/delta are informational in EOD — not blocking)
    SPREAD_MAX:      float = 0.08
    DELTA_MIN:       float = 0.35
    DELTA_MAX:       float = 0.55

    # EIL thresholds
    EIL_STRONG_MIN:  float = 0.60
    EIL_WEAK_MAX:    float = 0.40

    # Ranking
    TOP_N_TRADES:    int = 5

    # Sizing fractions
    HALF_SIZE_FRACTION: float = 0.50
    ARMED_SIZE_FRACTION: float = 0.70


cfg_ede = EDEConfig()


# ─────────────────────────────────────────────────────────────────────────────
# VERDICT ENUM
# ─────────────────────────────────────────────────────────────────────────────

class Verdict:
    GO          = "GO"
    ARMED       = "ARMED"
    ARMED_HALF  = "ARMED_HALF"
    BLOCKED     = "BLOCKED"
    WAIT        = "WAIT"     # EV positive but no trigger confirmed yet


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EDEResult:
    ticker:              str   = ""
    run_id:              str   = ""
    mode:                str   = "EOD"

    # Scores
    composite_score:     float = 0.0
    actuarial_conf:      float = 0.0
    eil_score:           Optional[float] = None

    # Actuarial inputs used
    win_rate_10d:        float = 0.0
    efficiency_10d:      float = 0.0
    expected_move_10d:   float = 0.0
    risk_10d:            float = 0.0
    penalty_multiplier:  float = 1.0
    actuarial_valid:     bool  = False
    actuarial_depth:     int   = 0
    actuarial_sample:    int   = 0
    actuarial_no_match:  bool  = False

    # Gate outcomes
    gate_spread:         str   = ""
    gate_delta:          str   = ""
    gate_breakeven:      str   = ""
    gate_eil:            str   = ""
    gate_edge:           str   = ""

    # Trigger layer (Phase 8.6)
    trigger_codes:       str   = "NO_TRIGGER_MODULE"
    trigger_count:       int   = 0
    trigger_primary:     str   = "NONE"
    trigger_quality:     str   = "NONE"
    trigger_score:       float = 0.0
    trigger_go_eligible: bool  = False

    # Runtime EV (never stored in database)
    ev_10d:              float = 0.0
    ev_sign:             str   = "ZERO"

    # Unified v4 component scores (audit trail)
    ev_score:            float = 0.0
    timing_score:        float = 0.0
    options_penalty:     float = 1.0
    options_spread_source: str = ""
    final_score:         float = 0.0

    # Sizing hint for PSE
    size_fraction:       float = 1.0

    # Final
    verdict:             str   = Verdict.BLOCKED
    reason:              str   = ""
    conviction:          str   = ""

    # Rank within this run (set during ranking pass)
    rank:                int   = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — COMPOSITE SCORE
# ─────────────────────────────────────────────────────────────────────────────

def compute_composite_score(act: Dict[str, Any]) -> float:
    """
    Legacy compatibility stub. v4.0 uses unified_decision_score() instead.
    Kept to prevent ImportError in any module that imported this directly.
    Returns EV-based score for reference only.
    """
    if not act or act.get("no_match") or not act.get("available", True):
        return 0.0
    wr = float(act.get("win_rate_10d", 0.0) or 0.0)
    em = float(act.get("expected_move_10d", 0.0) or 0.0)
    ev = wr * em
    if ev <= 0:
        return 0.0
    return round(min(1.0, ev / cfg_ede.EV_NORMALISE), 4)


def check_hard_gates(pkg: Dict[str, Any]) -> Tuple[bool, str, Dict[str, str]]:
    """
    Non-negotiable options contract checks.
    Returns (passed, first_failure_reason, gate_detail_dict).

    Gate detail dict has one key per gate with value PASS / FAIL / SKIP.
    SKIP means the field was None and the gate was bypassed (non-blocking in EOD mode).
    """
    opt = pkg.get("options_contract") or {}
    gates: Dict[str, str] = {
        "gate_spread":    "SKIP",
        "gate_delta":     "SKIP",
        "gate_breakeven": "SKIP",
    }

    # Spread gate
    spread = opt.get("spread_pct")
    if spread is not None:
        if spread > cfg_ede.SPREAD_MAX:
            gates["gate_spread"] = "FAIL"
            return False, f"SPREAD_TOO_WIDE ({spread:.1%})", gates
        gates["gate_spread"] = "PASS"

    # Delta gate
    delta = opt.get("delta")
    if delta is not None:
        if not (cfg_ede.DELTA_MIN <= abs(delta) <= cfg_ede.DELTA_MAX):
            gates["gate_delta"] = "FAIL"
            return False, f"DELTA_INVALID ({delta:.2f})", gates
        gates["gate_delta"] = "PASS"

    # Breakeven gate (live only — flag set by morning validation / execution gate)
    bp = pkg.get("breakeven_pass_live")
    if bp is not None:
        if not bp:
            gates["gate_breakeven"] = "FAIL"
            return False, "BREAKEVEN_FAIL", gates
        gates["gate_breakeven"] = "PASS"

    return True, "OK", gates


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — EIL EVALUATION
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_eil(eil_score: Optional[float], mode: str) -> Tuple[bool, str]:
    """
    EIL timing check.

    EOD / DISCOVERY mode:
      EIL scores are advisory only — partial or absent EIL never blocks
      a signal in EOD mode. Weak timing reduces conviction label only.

    LIVE mode:
      EIL score below WEAK threshold → ARMED_HALF (not full block — preserves
      the position for sizing reduction rather than outright removal).
      None (EIL not available) → FALLBACK (treated as neutral, non-blocking).
    """
    if mode in ("EOD", "DISCOVERY"):
        if eil_score is None:
            return True, "EOD_IGNORED"
        if eil_score >= cfg_ede.EIL_STRONG_MIN:
            return True, "STRONG"
        if eil_score >= cfg_ede.EIL_WEAK_MAX:
            return True, "MODERATE"
        return True, "WEAK_EOD"   # non-blocking in EOD — advisory label only

    # LIVE mode
    if eil_score is None:
        return True, "FALLBACK"
    if eil_score < cfg_ede.EIL_WEAK_MAX:
        return False, "WEAK_TIMING"   # → ARMED_HALF (see decision engine)
    if eil_score >= cfg_ede.EIL_STRONG_MIN:
        return True, "STRONG"
    return True, "MODERATE"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — ACTUARIAL CONFIDENCE
# ─────────────────────────────────────────────────────────────────────────────

def actuarial_confidence(act: Dict[str, Any]) -> float:
    """
    Statistical confidence weight based on historical sample size.

    n < 20   → 0.30  (low confidence — large penalty already applied by cache builder)
    20–49    → 0.60  (medium — usable but cautious)
    ≥ 50     → 1.00  (full confidence)

    Returns 0.0 if actuarial block is absent or no_match.
    """
    if not act or act.get("no_match") or not act.get("available", True):
        return 0.0

    n = int(act.get("sample_size") or act.get("actuarial_sample") or 0)

    if n >= cfg_ede.CONF_FULL:
        return cfg_ede.CONF_HIGH_VAL
    if n >= cfg_ede.CONF_MEDIUM:
        return cfg_ede.CONF_MED_VAL
    return cfg_ede.CONF_LOW_VAL


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — CONVICTION LABEL
# ─────────────────────────────────────────────────────────────────────────────

def _conviction_label(score: float, conf: float, eil_reason: str) -> str:
    if score >= cfg_ede.SCORE_GO_MIN and conf >= cfg_ede.CONF_MED_VAL:
        if eil_reason in ("STRONG", "EOD_IGNORED", "FALLBACK", "MODERATE"):
            return "HIGH"
    if score >= cfg_ede.SCORE_ARMED_MIN:
        return "MODERATE"
    return "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# SOVEREIGN EVENT GATE (v4.1 — FINAL)
# ─────────────────────────────────────────────────────────────────────────────

GO_ELIGIBLE_PRIMARIES = {"VOL_COMPRESSION", "RANGE_BREAK_EARLY", "RANGE_BREAK", "TRAP"}

def sovereign_event_gate(result):
    """
    Absolute authority layer.
    Enforces:
        - EV must be positive
        - Trigger must exist
        - Trigger must be valid
        - Primary trigger controls GO eligibility
    """
    if result.ev_10d <= 1e-8:
        return False, "NEGATIVE_EV"

    if result.trigger_count == 0:
        return False, "NO_TRIGGER"

    if result.trigger_quality not in ("STRONG", "SINGLE"):
        return False, "WEAK_TRIGGER"

    if result.trigger_primary not in GO_ELIGIBLE_PRIMARIES:
        return False, "NON_PRIMARY_TRIGGER"

    return True, "PASS"


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — FINAL DECISION ENGINE (core)
# ─────────────────────────────────────────────────────────────────────────────

def decision_engine(
    pkg:    Dict[str, Any],
    run_id: str  = "",
    mode:   str  = "EOD",
) -> EDEResult:
    """
    Unified Decision Engine v4.0 (2026-04-28)

    Authority hierarchy:
        1. TRIGGER LAYER  → decides WHEN  (gatekeeper)
        2. ACTUARIAL EV   → decides IF    (edge quantification)
        3. OPTIONS LAYER  → decides HOW   (execution quality, never blocks)
        4. EIL TIMING     → decides SIZE  (timing confidence)

    Decision stack (strict order):
        Step 1 — Hard block: EV <= 0 → BLOCKED
        Step 2 — Hard wait:  trigger_count == 0 → WAIT
        Step 3 — Compute weighted final_score
        Step 4 — Map score to GO / ARMED / ARMED_HALF / WAIT

    final_score = 0.40*ev_score + 0.30*trigger_score + 0.20*timing_score + 0.10*options_penalty

    Options never block — they reduce the options_penalty component (10% weight).
    A signal with terrible options execution scores 0.90 options_penalty — still
    90% of the options contribution. The trade happens at reduced size.
    """
    result        = EDEResult()
    result.mode   = mode
    result.run_id = run_id

    ticker = str(pkg.get("ticker") or pkg.get("underlying") or "?")
    result.ticker = ticker

    # ── Actuarial block ───────────────────────────────────────────────────────
    act = pkg.get("actuarial", {}) or {}
    result.win_rate_10d       = float(act.get("win_rate_10d")       or 0.0)
    result.efficiency_10d     = float(act.get("efficiency_10d")     or 0.0)
    result.expected_move_10d  = float(act.get("expected_move_10d")  or 0.0)
    result.risk_10d           = float(act.get("risk_10d")           or 0.0)
    result.penalty_multiplier = float(act.get("penalty_multiplier") or 1.0)
    result.actuarial_valid    = bool(act.get("available",    False))
    result.actuarial_depth    = int(act.get("fallback_depth") or 0)
    result.actuarial_sample   = int(act.get("sample_size") or act.get("n_observations") or 0)
    result.actuarial_no_match = bool(act.get("no_match",     False))
    result.actuarial_conf     = actuarial_confidence(act)

    # ── Runtime EV — never stored in database ────────────────────────────────
    ev_10d = result.win_rate_10d * result.expected_move_10d
    result.ev_10d  = round(ev_10d, 8)
    result.ev_sign = (
        "POSITIVE" if ev_10d >  1e-8
        else "NEGATIVE" if ev_10d < -1e-8
        else "ZERO"
    )

    # ── STEP 1: Hard block — negative or zero EV ─────────────────────────────
    # FIX-05: Separate "no actuarial data" (uncertainty) from "confirmed negative EV" (avoid).
    # Missing actuarial record → WAIT: signal preserved for trigger/structure evaluation.
    # Present actuarial + genuinely zero/negative EV → BLOCKED: correct.
    if ev_10d <= 1e-8:
        if result.actuarial_no_match or not result.actuarial_valid:
            # No actuarial record for this state bucket — uncertainty, not negative EV.
            result.gate_edge       = "DATA_WEAK"
            result.verdict         = Verdict.WAIT
            result.reason          = (
                f"ACTUARIAL_NO_MATCH — no historical data for this state bucket. "
                f"Signal preserved for trigger/structure evaluation. "
                f"wr={result.win_rate_10d:.3f} em={result.expected_move_10d:.5f}"
            )
            result.composite_score = 0.20   # alive but uncertain — not zero
            result.final_score     = 0.0
            return result
        else:
            # Actuarial data IS present and EV is genuinely zero/negative.
            result.gate_edge       = "FAIL"
            result.verdict         = Verdict.BLOCKED
            result.reason          = (
                f"NEGATIVE_EV: actuarial data present but ev={ev_10d:.6f} "
                f"wr={result.win_rate_10d:.3f} em={result.expected_move_10d:.5f}"
            )
            result.composite_score = 0.0
            result.final_score     = 0.0
            return result

    result.gate_edge = "PASS"

    # ── Read trigger block (Phase 8.6) ────────────────────────────────────────
    trig = pkg.get("triggers", {}) or {}
    result.trigger_codes       = str(trig.get("codes",        "NO_TRIGGER_MODULE"))
    result.trigger_count       = int(trig.get("count",        0))
    result.trigger_primary     = str(trig.get("primary",      "NONE"))
    result.trigger_quality     = str(trig.get("quality",      "NONE"))
    result.trigger_go_eligible = bool(trig.get("go_eligible", False))
    triggers_deployed          = result.trigger_codes != "NO_TRIGGER_MODULE"

    # ── STEP 2: Sovereign Event Gate — trigger authority checks ──────────────
    # Enforces: NO_TRIGGER → WAIT, WEAK_TRIGGER → WAIT, NON_PRIMARY → ARMED
    # EV already checked in STEP 1 above; gate handles remaining three rules.
    if triggers_deployed:
        gate_pass, gate_reason = sovereign_event_gate(result)
        if not gate_pass:
            if gate_reason == "NO_TRIGGER":
                result.verdict = Verdict.WAIT
                result.reason  = (
                    f"NO_TRIGGER (EV={ev_10d:.5f} positive but no trigger confirmed — "
                    f"signal is ARMED for morning validation)"
                )
                result.composite_score = round(min(1.0, ev_10d / cfg_ede.EV_NORMALISE), 4)
                result.final_score     = 0.0
                return result
            elif gate_reason == "WEAK_TRIGGER":
                result.verdict = Verdict.WAIT
                result.reason  = f"WEAK_TRIGGER (quality={result.trigger_quality})"
                result.final_score     = 0.0
                result.composite_score = 0.0
                return result
            elif gate_reason == "NON_PRIMARY_TRIGGER":
                result.verdict = Verdict.ARMED
                result.reason  = f"NON_PRIMARY_TRIGGER (primary={result.trigger_primary})"
                result.final_score     = 0.0
                result.composite_score = 0.0
                result.size_fraction   = cfg_ede.ARMED_SIZE_FRACTION
                result.conviction      = "MODERATE"
                return result
    elif result.trigger_count == 0:
        # Legacy path: trigger module not deployed, no triggers present
        result.verdict = Verdict.WAIT
        result.reason  = (
            f"NO_TRIGGER (EV={ev_10d:.5f} positive but no trigger confirmed — "
            f"signal is ARMED for morning validation)"
        )
        result.composite_score = round(min(1.0, ev_10d / cfg_ede.EV_NORMALISE), 4)
        result.final_score     = 0.0
        return result

    # ── STEP 3: Compute component scores ─────────────────────────────────────

    # EV score — normalised to [0, 1]
    ev_score = min(1.0, ev_10d / cfg_ede.EV_NORMALISE)
    # Apply actuarial penalty (sample quality from cache builder)
    ev_score = ev_score * result.penalty_multiplier
    result.ev_score = round(ev_score, 4)

    # Trigger score — weighted quality
    trig_weighted = float(trig.get("score", 0.0) or 0.0)
    if result.trigger_quality == "STRONG":
        trigger_score = 1.0
    elif result.trigger_quality == "SINGLE":
        trigger_score = 0.6
    else:
        # trigger module not deployed — treat as neutral
        trigger_score = 0.5 if not triggers_deployed else 0.0
    result.trigger_score = round(trigger_score, 4)

    # Timing score — EIL
    eil = _extract_eil_score(pkg)
    result.eil_score = eil
    eil_pass, eil_reason = evaluate_eil(eil, mode)
    result.gate_eil = "PASS" if eil_pass else "ADVISORY"

    if eil is None:
        timing_score = 0.5    # absent — neutral
    elif eil >= cfg_ede.EIL_STRONG_MIN:
        timing_score = 1.0
    elif eil >= cfg_ede.EIL_WEAK_MAX:
        timing_score = 0.7
    else:
        timing_score = 0.4
    result.timing_score = round(timing_score, 4)

    # Options penalty — reads from pkg options_contract and raw fields
    # NEVER blocks — only reduces the 10% options weight component
    opt = pkg.get("options_contract") or {}
    _raw = pkg.get("_raw") or {}
    options_penalty = 1.0

    spread = opt.get("spread_pct") or float(_raw.get("contract_spread_pct") or 0)
    ivp    = (opt.get("ivp") or
              float(_raw.get("ivp_252d") or _raw.get("iv_percentile") or 0))
    be_pct = float(_raw.get("breakeven_pct") or 0)
    em_pct = abs(result.expected_move_10d) * 100   # convert to pct
    spread_source = str(
        opt.get("spread_source")
        or _raw.get("spread_source")
        or _raw.get("options_spread_source")
        or _raw.get("contract_spread_source")
        or ""
    ).upper().strip()
    result.options_spread_source = spread_source

    if spread and spread > cfg_ede.SPREAD_MAX:
        options_penalty *= cfg_ede.OPT_SPREAD_PENALTY
    if spread_source in {"OI_DERIVED", "SYNTHETIC", "BSM_SYNTHETIC"}:
        options_penalty *= cfg_ede.OPT_SPREAD_SOURCE_DERIVED_PENALTY
    elif spread_source in {"UNAVAILABLE", "MISSING", "NO_QUOTE"}:
        options_penalty *= cfg_ede.OPT_SPREAD_SOURCE_UNAVAILABLE_PENALTY
    if ivp and ivp > 0.65:
        options_penalty *= cfg_ede.OPT_IV_PENALTY
    if be_pct and em_pct and be_pct > em_pct:
        options_penalty *= cfg_ede.OPT_BREAKEVEN_PENALTY

    # Check options_verdict from OI — STAND_DOWN downgrades but does not block
    oi_verdict = str(_raw.get("options_verdict") or "").upper()
    if oi_verdict == "STAND_DOWN":
        options_penalty *= 0.75   # additional downgrade for OI STAND_DOWN

    result.options_penalty = round(options_penalty, 4)

    # Gate results (informational)
    delta = opt.get("delta")
    result.gate_spread    = (
        "PASS" if (not spread or spread <= cfg_ede.SPREAD_MAX) else "SOFT_FAIL"
    )
    result.gate_delta     = (
        "PASS" if (delta is None or cfg_ede.DELTA_MIN <= abs(delta) <= cfg_ede.DELTA_MAX)
        else "SOFT_FAIL"
    )
    result.gate_breakeven = "SKIP"

    # ── STEP 4: Unified final score ───────────────────────────────────────────
    final_score = (
        cfg_ede.W_EV      * ev_score      +
        cfg_ede.W_TRIGGER * trigger_score +
        cfg_ede.W_TIMING  * timing_score  +
        cfg_ede.W_OPTIONS * options_penalty
    )
    result.final_score     = round(final_score, 4)
    result.composite_score = round(final_score, 4)   # alias for downstream compat

    # ── STEP 5: Verdict ───────────────────────────────────────────────────────
    # GO is only valid for primary triggers in GO_ELIGIBLE_PRIMARIES (sovereign gate)
    if result.trigger_primary in GO_ELIGIBLE_PRIMARIES and final_score >= cfg_ede.SCORE_GO_MIN:
        verdict      = Verdict.GO
        size         = 1.0
        conviction   = "HIGH" if final_score >= 0.80 else "MODERATE"
    elif final_score >= cfg_ede.SCORE_ARMED_MIN:
        verdict      = Verdict.ARMED
        size         = cfg_ede.ARMED_SIZE_FRACTION
        conviction   = "MODERATE"
    elif final_score >= cfg_ede.SCORE_HALF_MIN:
        verdict      = Verdict.ARMED_HALF
        size         = cfg_ede.HALF_SIZE_FRACTION
        conviction   = "LOW"
    else:
        verdict      = Verdict.WAIT
        size         = 0.0
        conviction   = ""

    # EIL live downgrade (LIVE mode only — advisory in EOD)
    if verdict == Verdict.GO and not eil_pass and mode == "LIVE":
        verdict    = Verdict.ARMED_HALF
        size       = cfg_ede.HALF_SIZE_FRACTION
        conviction = "LOW"

    result.verdict      = verdict
    result.size_fraction = size
    result.conviction   = conviction
    result.reason       = (
        f"ev={ev_10d:.5f} trigger={result.trigger_codes} "
        f"score={final_score:.3f} "
        f"[ev={ev_score:.2f} trig={trigger_score:.2f} "
        f"timing={timing_score:.2f} opt={options_penalty:.2f}]"
    )

    return result


def _extract_eil_score(pkg: Dict[str, Any]) -> Optional[float]:
    """
    Resolve EIL score from package or flat CSV row.
    Checks multiple field names used across EIL versions.
    """
    for key in ("eil_score", "eil_composite", "eil_v3_score", "eil_final_score",
                "execution_score", "timing_score"):
        v = pkg.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — RANKING
# ─────────────────────────────────────────────────────────────────────────────

def rank_signals(results: List[EDEResult]) -> List[EDEResult]:
    """
    Rank all signals by composite score × actuarial confidence.
    Blocked signals are included but ranked last.

    Prevents dilution: only top N are emitted to the trade book.
    """
    def _sort_key(r: EDEResult) -> float:
        if r.verdict in (Verdict.BLOCKED, Verdict.WAIT):
            return -1.0
        fraction_bonus = {
            Verdict.GO:         1.0,
            Verdict.ARMED:      0.9,
            Verdict.ARMED_HALF: 0.7,
        }.get(r.verdict, 0.5)
        # Use final_score (unified v4) if available, else composite_score
        score = r.final_score if r.final_score > 0 else r.composite_score
        return score * fraction_bonus

    ranked = sorted(results, key=_sort_key, reverse=True)
    for i, r in enumerate(ranked):
        r.rank = i + 1
    return ranked


def select_top_trades(results: List[EDEResult], top_n: int = None) -> List[EDEResult]:
    """Return ranked actionable signals only (GO + ARMED + ARMED_HALF), capped at top_n."""
    n = top_n or cfg_ede.TOP_N_TRADES
    actionable = [r for r in results if r.verdict not in (Verdict.BLOCKED, Verdict.WAIT)]
    return actionable[:n]


# ─────────────────────────────────────────────────────────────────────────────
# CSV + JSON I/O
# ─────────────────────────────────────────────────────────────────────────────

def _load_csv_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k: v.strip() if isinstance(v, str) else v for k, v in row.items()})
    return rows


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL PACKAGE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def _build_signal_pkg(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconstruct a minimal pkg dict from a flat CSV row (EIL/superbrain output).
    Handles both nested (package JSON) and flat (CSV) input formats.
    """
    def _f(k): return _safe_float(row.get(k))

    # ── FIX-EM-FALLBACK (2026-04-29): expected_move_10d is not written to the EIL CSV
    # as a flat column. The GARCH layer (Phase L3) writes l3_expected_move_6_10d and
    # l3_expected_move_1_5d in percentage terms (e.g. 8.3 = 8.3%). Divide by 100 to
    # convert to decimal (e.g. 0.083) so EV = win_rate * expected_move is meaningful.
    # Fallback chain: actuarial_expected_move_10d → expected_move_10d → l3 6-10d → l3 1-5d
    def _em_10d() -> Optional[float]:
        v = _f("actuarial_expected_move_10d") or _f("expected_move_10d")
        if v is not None:
            return v
        # GARCH forecasts are in % — convert to decimal fraction
        l3_6_10 = _f("l3_expected_move_6_10d")
        if l3_6_10 is not None:
            return l3_6_10 / 100.0
        l3_1_5 = _f("l3_expected_move_1_5d")
        if l3_1_5 is not None:
            return l3_1_5 / 100.0
        return None

    # Actuarial block — may be flat-prefixed in CSV
    act = {
        "available":          True,
        "win_rate_10d":       _f("actuarial_win_rate_10d") or _f("win_rate_10d"),
        "efficiency_10d":     _f("actuarial_efficiency_10d") or _f("efficiency_10d"),
        "expected_move_10d":  _em_10d(),
        "risk_10d":           _f("actuarial_risk_10d") or _f("risk_10d"),
        "penalty_multiplier": _f("actuarial_penalty") or _f("penalty_multiplier") or 1.0,
        "valid":              _parse_bool(row.get("actuarial_valid")),
        "fallback_depth":     _safe_int(row.get("actuarial_depth")) or 0,
        "sample_size":        _safe_int(row.get("actuarial_sample")) or 0,
        "no_match":           _parse_bool(row.get("actuarial_no_match")),
    }

    # If no actuarial data columns present, mark unavailable
    if all(v is None for v in [act["win_rate_10d"], act["efficiency_10d"], act["expected_move_10d"]]):
        act["available"] = False
        act["no_match"]  = True

    # Options contract block
    opt = {
        "spread_pct": _f("spread_pct"),
        "delta":      _f("delta"),
        "iv":         _f("iv"),
    }

    # ── FIX-TRIGGER-ABSENT (2026-04-29): trigger_layer.py columns (trigger_codes,
    # trigger_count, trigger_primary, trigger_quality) are NOT written to the EIL CSV
    # when trigger_layer.py has not yet run. In this case the sentinel "NO_TRIGGER_MODULE"
    # is correct — triggers_deployed=False — and the sovereign gate must NOT fire the
    # WAIT path. The decision engine legacy path handles this: EV-positive signals with
    # no trigger module proceed to scoring at neutral trigger_score=0.5.
    # Trigger block — injected by Phase 8.6 (trigger_layer.py)
    # In flat CSV mode, triggers are stored as ede_trigger_* prefixed columns
    _has_trigger_col = any(row.get(c) for c in (
        "trigger_codes", "ede_trigger_codes", "trigger_count", "ede_trigger_count"
    ))
    trigger_codes   = str(row.get("trigger_codes") or row.get("ede_trigger_codes") or "NO_TRIGGER_MODULE")
    trigger_count   = _safe_int(row.get("trigger_count") or row.get("ede_trigger_count")) or 0
    trigger_primary = str(row.get("trigger_primary") or row.get("ede_trigger_primary") or "NONE")
    trigger_quality = str(row.get("trigger_quality") or row.get("ede_trigger_quality") or "NONE")
    trigger_score_v = _safe_float(row.get("trigger_score") or row.get("ede_trigger_score")) or 0.0
    trigger_go_elig = _parse_bool(row.get("trigger_go_eligible") or row.get("ede_trigger_go_eligible"))

    trig = {
        "codes":        trigger_codes,
        "count":        trigger_count,
        "primary":      trigger_primary,
        "quality":      trigger_quality,
        "score":        trigger_score_v or 0.0,
        "go_eligible":  bool(trigger_go_elig) if trigger_go_elig is not None else (trigger_count > 0),
    }

    return {
        "ticker":                row.get("ticker", ""),
        "actuarial":             act,
        "options_contract":      opt,
        "triggers":              trig,
        "breakeven_pass_live":   _parse_bool(row.get("breakeven_pass_live")),
        # EIL scores
        "eil_score":             _f("eil_score") or _f("eil_composite_score"),
        "eil_composite":         _f("eil_composite") or _f("eil_composite_score"),
        "eil_v3_score":          _f("eil_v3_score"),
        # Raw row preserved for pass-through columns
        "_raw": row,
    }


def _safe_float(v) -> Optional[float]:
    if v is None or str(v).strip() in ("", "nan", "None", "N/A"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    if v is None or str(v).strip() in ("", "nan", "None", "N/A"):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_bool(v) -> Optional[bool]:
    if v is None or str(v).strip() == "":
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_decision_engine(
    run_id: str,
    base_dir: Path,
    mode: str = "EOD",
    top_n: int = None,
) -> Dict[str, Any]:
    """
    Called by intelligent_orchestrator.py after EIL and before enhancement layer.

    Resolution order for input CSV (same fallback chain as SuperBrain):
      1. eil_enriched_{run_id}.csv    (EIL output — preferred)
      2. superbrain_enriched_{run_id}.csv  (SuperBrain output — fallback)
      3. vanguard_signals.csv             (Vanguard output — final fallback)

    Returns a summary dict the orchestrator can gate on:
      {
        "success":      bool,
        "go_count":     int,
        "armed_count":  int,
        "blocked_count":int,
        "top_trades":   list[str],   # tickers
        "output_csv":   str,
        "mode":         str,
      }
    """
    runs_dir   = base_dir / "data" / "output" / "runs"
    run_dir    = runs_dir / run_id
    sb_dir     = run_dir / "superbrain"
    vg_dir     = run_dir / "vanguard"
    output_dir = run_dir / "decisions"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Locate input CSV ──────────────────────────────────────────────────────
    input_csv: Optional[Path] = None
    input_source = ""

    eil_csv = sb_dir / f"eil_enriched_{run_id}.csv"
    sb_csv  = sb_dir / f"superbrain_enriched_{run_id}.csv"
    vg_csv  = vg_dir / "vanguard_signals.csv"

    for candidate, label in [
        (eil_csv, "eil_enriched"),
        (sb_csv,  "superbrain_enriched"),
        (vg_csv,  "vanguard_signals"),
    ]:
        if candidate.exists() and candidate.stat().st_size > 200:
            input_csv    = candidate
            input_source = label
            break

    if input_csv is None:
        log.warning("EDE skipped — no input CSV found for run %s", run_id)
        return {"success": False, "reason": "NO_INPUT_CSV"}

    log.info("EDE input : %s (%s)", input_csv.name, input_source)
    log.info("EDE mode  : %s", mode)

    # ── Load rows ─────────────────────────────────────────────────────────────
    rows = _load_csv_rows(input_csv)
    if not rows:
        return {"success": False, "reason": "EMPTY_INPUT_CSV"}

    # ── Run decision engine per signal ────────────────────────────────────────
    # v1.1 HORIZON GATE: Short-circuit 11-20D MONITOR_ONLY and BLOCKED signals
    # before running the full 4-question decision engine. This prevents wasted
    # computation and ensures they never appear in GO/ARMED output.
    results: List[EDEResult] = []
    _monitor_only_count = 0
    _horizon_blocked_count = 0
    for row in rows:
        _hb = str(row.get("horizon_bucket","")).strip().lower()
        _ha = str(row.get("horizon_action","")).strip().upper()
        _hsm = float(row.get("horizon_size_multiplier") or (
            1.0 if _hb == "1_5d" else 0.70 if _hb == "6_10d" else 0.0
        ))

        # MONITOR_ONLY: not executable proactively — output BLOCKED with reason
        if _ha == "MONITOR_ONLY":
            _monitor_only_count += 1
            results.append(EDEResult(
                ticker          = str(row.get("ticker","")).upper(),
                verdict         = Verdict.BLOCKED,
                reason          = "HORIZON_MONITOR_ONLY: explicit router monitor-only action",
                conviction      = 0.0,
                composite_score = 0.0,
                actuarial_conf  = 0.0,
                eil_score       = 0.0,
                size_fraction   = 0.0,
                gate_spread     = False,
                gate_delta      = False,
                gate_breakeven  = False,
                gate_eil        = False,
                gate_edge       = False,
            ))
            continue

        # BLOCKED by horizon router: hard block
        if _hb == "blocked":
            _horizon_blocked_count += 1
            results.append(EDEResult(
                ticker          = str(row.get("ticker","")).upper(),
                verdict         = Verdict.BLOCKED,
                reason          = f"HORIZON_BLOCKED: {row.get('horizon_block_reason','')}",
                conviction      = 0.0,
                composite_score = 0.0,
                actuarial_conf  = 0.0,
                eil_score       = 0.0,
                size_fraction   = 0.0,
                gate_spread     = False,
                gate_delta      = False,
                gate_breakeven  = False,
                gate_eil        = False,
                gate_edge       = False,
            ))
            continue

        # Normal processing for 1-5D and 6-10D signals
        pkg    = _build_signal_pkg(row)
        result = decision_engine(pkg, run_id=run_id, mode=mode)

        # Apply horizon_size_multiplier to size_fraction (6-10D gets 0.70x)
        if _hsm < 1.0 and result.size_fraction is not None:
            result.size_fraction = round(result.size_fraction * _hsm, 4)

        results.append(result)

    if _monitor_only_count:
        log.info("EDE: %d signals short-circuited as HORIZON_MONITOR_ONLY", _monitor_only_count)
    if _horizon_blocked_count:
        log.info("EDE: %d signals short-circuited as HORIZON_BLOCKED", _horizon_blocked_count)

    # ── Rank ──────────────────────────────────────────────────────────────────
    results = rank_signals(results)
    top     = select_top_trades(results, top_n=top_n or cfg_ede.TOP_N_TRADES)

    # ── Build output rows (merge EDE fields into original row) ────────────────
    ticker_to_result = {r.ticker: r for r in results}
    output_rows: List[Dict[str, Any]] = []
    for row in rows:
        ticker = str(row.get("ticker", "")).upper()
        r      = ticker_to_result.get(ticker)
        out    = dict(row)   # preserve all original columns
        if r:
            out.update({
                "ede_verdict":          r.verdict,
                "ede_reason":           r.reason,
                "horizon_bucket":       row.get("horizon_bucket","unrouted"),
                "horizon_action":       row.get("horizon_action","UNKNOWN"),
                "horizon_size_multiplier": row.get("horizon_size_multiplier", 1.0),
                "ede_conviction":       r.conviction,
                "ede_composite_score":  r.composite_score,
                "ede_final_score":      r.final_score,
                "ede_actuarial_conf":   r.actuarial_conf,
                "ede_eil_score":        r.eil_score,
                "ede_size_fraction":    r.size_fraction,
                "ede_rank":             r.rank,
                "ede_gate_spread":      r.gate_spread,
                "ede_gate_delta":       r.gate_delta,
                "ede_gate_breakeven":   r.gate_breakeven,
                "ede_gate_eil":         r.gate_eil,
                "ede_gate_edge":        r.gate_edge,
                "ede_mode":             mode,
                # Unified v4 audit trail
                "ede_ev_10d":           r.ev_10d,
                "ede_ev_sign":          r.ev_sign,
                "ede_ev_score":         r.ev_score,
                "ede_trigger_codes":    r.trigger_codes,
                "ede_trigger_count":    r.trigger_count,
                "ede_trigger_primary":  r.trigger_primary,
                "ede_trigger_quality":  r.trigger_quality,
                "ede_trigger_score":    r.trigger_score,
                "ede_timing_score":     r.timing_score,
                "ede_options_penalty":  r.options_penalty,
            })
        output_rows.append(out)

    # ── Write decisions CSV ───────────────────────────────────────────────────
    decisions_csv = output_dir / f"ede_decisions_{run_id}.csv"
    _write_csv(decisions_csv, output_rows)

    # ── Write top trades CSV ──────────────────────────────────────────────────
    top_tickers = {r.ticker for r in top}
    top_rows    = [r for r in output_rows if r.get("ticker", "").upper() in top_tickers]
    top_csv     = output_dir / f"ede_top_trades_{run_id}.csv"
    _write_csv(top_csv, top_rows)

    # ── Tally ─────────────────────────────────────────────────────────────────
    go_count      = sum(1 for r in results if r.verdict == Verdict.GO)
    armed_count   = sum(1 for r in results if r.verdict == Verdict.ARMED)
    half_count    = sum(1 for r in results if r.verdict == Verdict.ARMED_HALF)
    blocked_count = sum(1 for r in results if r.verdict == Verdict.BLOCKED)

    verdict_breakdown: Dict[str, int] = {}
    reason_breakdown:  Dict[str, int] = {}
    for r in results:
        verdict_breakdown[r.verdict] = verdict_breakdown.get(r.verdict, 0) + 1
        reason_breakdown[r.reason]   = reason_breakdown.get(r.reason,   0) + 1

    summary = {
        "run_id":              run_id,
        "mode":                mode,
        "input_source":        input_source,
        "total_signals":       len(results),
        "go_count":            go_count,
        "monitor_only_count":  _monitor_only_count,
        "horizon_blocked_count": _horizon_blocked_count,
        "armed_count":     armed_count,
        "armed_half_count":half_count,
        "blocked_count":   blocked_count,
        "top_trades":      [r.ticker for r in top],
        "verdict_breakdown": verdict_breakdown,
        "reason_breakdown":  reason_breakdown,
        "output_csv":      str(decisions_csv),
        "top_trades_csv":  str(top_csv),
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "success":         True,
    }

    _write_json(output_dir / f"ede_summary_{run_id}.json", summary)

    log.info(
        "EDE complete — GO=%d | ARMED=%d | ARMED_HALF=%d | BLOCKED=%d | top=%s",
        go_count, armed_count, half_count, blocked_count,
        [r.ticker for r in top],
    )

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR HOOK — drop into intelligent_orchestrator.py
# ─────────────────────────────────────────────────────────────────────────────

def run_ede_from_orchestrator(
    run_id: str,
    base_dir: Path,
    mode: str = "EOD",
) -> Dict[str, Any]:
    """
    Called by intelligent_orchestrator.py Phase 9.5.

    Usage in orchestrator (after EIL, before enhancement layer):

        from execution_decision_engine import run_ede_from_orchestrator
        _ede = run_ede_from_orchestrator(run_id=canonical_run_id,
                                         base_dir=cfg.BASE_DIR,
                                         mode="EOD")
        if _ede.get("go_count", 0) + _ede.get("armed_count", 0) == 0:
            logger.warning("⚠️  EDE: 0 actionable signals — check actuarial cache and EIL output")
    """
    try:
        return run_decision_engine(run_id=run_id, base_dir=base_dir, mode=mode)
    except Exception as e:
        log.error("EDE failed: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    import argparse
    _setup_logging()

    ap = argparse.ArgumentParser(description="AVSHUNTER Execution Decision Engine")
    ap.add_argument("--run-id",  required=True,   help="Run ID e.g. 20260215_020505")
    ap.add_argument("--base-dir", default=".",    help="Repo base directory")
    ap.add_argument("--mode",    default="EOD",
                    choices=["EOD", "LIVE", "DISCOVERY"],
                    help="Pipeline mode — EOD (evening), LIVE (morning), DISCOVERY (pre-EIL)")
    ap.add_argument("--top-n",  type=int, default=5, help="Top N trades shortlist size")
    args = ap.parse_args()

    result = run_decision_engine(
        run_id   = args.run_id,
        base_dir = Path(args.base_dir).resolve(),
        mode     = args.mode,
        top_n    = args.top_n,
    )

    if not result.get("success"):
        log.error("EDE failed: %s", result.get("reason") or result.get("error"))
        return 1

    print("\n=== EDE SUMMARY ===")
    print(f"  Run ID  : {args.run_id}")
    print(f"  Mode    : {args.mode}")
    print(f"  GO      : {result['go_count']}")
    print(f"  ARMED   : {result['armed_count']}")
    print(f"  HALF    : {result['armed_half_count']}")
    print(f"  BLOCKED : {result['blocked_count']}")
    print(f"  Top     : {result['top_trades']}")
    print(f"  Output  : {result['output_csv']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
