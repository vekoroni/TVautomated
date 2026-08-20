"""
swing_fusion.py
===============
Swing Wyckoff × Crabel Fusion Logic — v1.0

Single authority for direction and intent.
Precor/WyckoffEngine feed DATA; this module makes the DECISION.

Contract (per SME spec):
    fuse_wyckoff_crabel(wyckoff, crabel, precor=None) -> FusionResult dict

Output fields:
    direction          : LONG / SHORT / NONE
    intent             : BUY_SETUP / SELL_SETUP / TRANSITION / OBSERVE_ONLY
    alignment_score    : 0–100 (computed, never forced)
    contradictions     : list[str]  (reasons to doubt)
    fusion_rule_fired  : str        (audit — which branch produced the result)
    audit              : dict       (raw inputs captured for traceability)
"""

from __future__ import annotations

from typing import Dict, List, Optional

from enums_structural import (
    ControlState, CrabelState, Direction, Intent, Operator, WyckoffPhase
)


# ---------------------------------------------------------------------------
# Public contract
# ---------------------------------------------------------------------------

def fuse_wyckoff_crabel(
    wyckoff: Dict,
    crabel: Dict,
    precor: Optional[Dict] = None,
) -> Dict:
    """
    Fuse Wyckoff engine output + Crabel result into a single intent package.

    Parameters
    ----------
    wyckoff : dict
        Output of WyckoffEngine_3101_v2.analyze() — AFTER the enum fix is applied.
        Key fields consumed:
            current_phase, operator, control_state,
            truth_confidence, phase_evidence_strength,
            contradictions (list[str] or absent)
    crabel : dict
        Output of crabel_compression() from avshunter_discovery_ULTIMATE.
        Key fields consumed:
            state, score, shelf_high, shelf_low, shelf_width
    precor : dict | None
        Optional output of process_precore_signal().
        Used only for audit enrichment — NEVER overrides fusion decision.

    Returns
    -------
    dict with keys defined in module docstring.
    """

    # --- 1. Normalise inputs -------------------------------------------------
    phase        = WyckoffPhase.normalise(str(wyckoff.get("current_phase",  WyckoffPhase.UNKNOWN)))
    operator     = str(wyckoff.get("operator",     Operator.UNCLEAR)).upper().strip()
    ctrl_raw     = wyckoff.get("control_state",    ControlState.UNKNOWN)
    control      = ControlState.normalise(str(ctrl_raw))
    truth_conf   = float(wyckoff.get("truth_confidence",      0.0))
    evidence     = float(wyckoff.get("phase_evidence_strength", 0.0))

    raw_contradictions: List[str] = wyckoff.get("contradictions", [])
    if not isinstance(raw_contradictions, list):
        raw_contradictions = list(raw_contradictions) if raw_contradictions else []

    crabel_state = CrabelState.normalise(str(crabel.get("state", CrabelState.NONE)))
    crabel_score = float(crabel.get("score", 0.0))

    contradictions: List[str] = list(raw_contradictions)  # may grow below

    # --- 2. Direction --------------------------------------------------------
    direction = _determine_direction(control, operator)

    # --- 3. Alignment score --------------------------------------------------
    alignment_score, align_notes = _compute_alignment_score(
        phase, crabel_state, direction, control, contradictions
    )
    contradictions.extend(align_notes)

    # --- 4. Intent -----------------------------------------------------------
    intent, rule_fired = _determine_intent(
        direction, alignment_score, phase, crabel_state,
        truth_conf, evidence, contradictions
    )

    # --- 5. Audit block ------------------------------------------------------
    audit = {
        "phase_input":          phase,
        "operator_input":       operator,
        "control_raw":          ctrl_raw,
        "control_normalised":   control,
        "truth_confidence":     truth_conf,
        "evidence_strength":    evidence,
        "crabel_state":         crabel_state,
        "crabel_score":         crabel_score,
        "alignment_score":      alignment_score,
        "contradictions_count": len(contradictions),
        "precor_enrichment":    _extract_precor_audit(precor),
    }

    return {
        "direction":         direction,
        "intent":            intent,
        "alignment_score":   round(alignment_score, 1),
        "contradictions":    contradictions,
        "fusion_rule_fired": rule_fired,
        "audit":             audit,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _determine_direction(control: str, operator: str) -> str:
    """
    Direction rule (from spec):
      BUYERS + accumulation/markup  → LONG
      SELLERS + distribution/markdown → SHORT
      Else → NONE
    """
    if control == ControlState.BUYERS and operator in Operator.LONG_OPERATORS:
        return Direction.LONG
    if control == ControlState.SELLERS and operator in Operator.SHORT_OPERATORS:
        return Direction.SHORT
    return Direction.NONE


def _compute_alignment_score(
    phase: str,
    crabel_state: str,
    direction: str,
    control: str,
    contradictions: List[str],
) -> tuple[float, List[str]]:
    """
    Alignment score per spec:
        Start:  50
        +20     if (COILING + phase A/B) OR (READY + phase C/D)
        +10     if direction agrees with control
        -30     if phase UNKNOWN
        -20     if contradictions >= 2
        Clamp:  0–100
    """
    score = 50.0
    notes: List[str] = []

    # Phase × Crabel synergy
    if (
        crabel_state == CrabelState.COILING and phase in WyckoffPhase.RANGE_PHASES
    ) or (
        crabel_state == CrabelState.READY and phase in {WyckoffPhase.C, WyckoffPhase.D}
    ):
        score += 20
    else:
        notes.append(
            f"Crabel({crabel_state}) / phase({phase}) synergy absent — no alignment bonus"
        )

    # Direction × control agreement
    if direction == Direction.LONG  and control == ControlState.BUYERS:
        score += 10
    elif direction == Direction.SHORT and control == ControlState.SELLERS:
        score += 10
    elif direction == Direction.NONE:
        notes.append("Direction NONE — no control-agreement bonus")

    # Phase unknown penalty
    if phase == WyckoffPhase.UNKNOWN:
        score -= 30
        notes.append("Phase UNKNOWN — heavy alignment penalty")

    # Contradiction penalty
    if len(contradictions) >= 2:
        score -= 20
        notes.append(f"{len(contradictions)} contradictions — alignment penalised")

    return max(0.0, min(100.0, score)), notes


def _determine_intent(
    direction: str,
    alignment_score: float,
    phase: str,
    crabel_state: str,
    truth_conf: float,
    evidence: float,
    contradictions: List[str],
) -> tuple[str, str]:
    """
    Intent gate:
      alignment_score < 50              → OBSERVE_ONLY  (fail closed, per spec)
      phase UNKNOWN + GO-like direction → OBSERVE_ONLY
      evidence < 30                     → OBSERVE_ONLY  (weak Wyckoff reading)
      direction NONE                    → OBSERVE_ONLY
      direction LONG  + score >= 50     → BUY_SETUP
      direction SHORT + score >= 50     → SELL_SETUP
    """
    # Fail-closed gate
    if alignment_score < 50:
        return Intent.OBSERVE_ONLY, f"alignment_score={alignment_score:.0f} < 50 — fail closed"

    # Unknown phase blocks GO signals
    if phase == WyckoffPhase.UNKNOWN:
        return Intent.OBSERVE_ONLY, "phase=UNKNOWN blocks actionable intent"

    # Weak evidence gate (prevents confident signals on noisy data)
    if evidence < 30:
        return Intent.OBSERVE_ONLY, f"evidence_strength={evidence:.0f} < 30 — insufficient Wyckoff evidence"

    # No direction
    if direction == Direction.NONE:
        return Intent.OBSERVE_ONLY, "direction=NONE — control/operator mismatch"

    # TRANSITION when close but not clean
    if crabel_state == CrabelState.NONE and phase in WyckoffPhase.RANGE_PHASES and evidence < 50:
        return Intent.TRANSITION, "Wyckoff building cause but no Crabel compression yet"

    # GO signals
    if direction == Direction.LONG:
        return Intent.BUY_SETUP, f"LONG confirmed: alignment={alignment_score:.0f}, phase={phase}, crabel={crabel_state}"

    if direction == Direction.SHORT:
        return Intent.SELL_SETUP, f"SHORT confirmed: alignment={alignment_score:.0f}, phase={phase}, crabel={crabel_state}"

    return Intent.OBSERVE_ONLY, "fallback — no rule matched"


def _extract_precor_audit(precor: Optional[Dict]) -> Dict:
    """Pull key precor fields for audit — never used for decisions."""
    if not precor:
        return {"available": False}
    return {
        "available":        True,
        "precor_phase":     precor.get("wyckoff_phase", ""),
        "precor_intent":    precor.get("intent", ""),
        "precor_control":   precor.get("control_state", ""),
        "precor_event":     precor.get("primary_event", ""),
    }


# ---------------------------------------------------------------------------
# WyckoffPhase helper (must live here to avoid circular imports)
# ---------------------------------------------------------------------------
# Patch WyckoffPhase with a normalise() method if not already present
def _normalise_phase(raw: str) -> str:
    s = str(raw).strip().upper()
    if s in WyckoffPhase.ALL:
        return s
    return WyckoffPhase.UNKNOWN

WyckoffPhase.normalise = staticmethod(_normalise_phase)
