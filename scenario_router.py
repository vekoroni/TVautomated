"""
scenario_router.py
==================
AVSHUNTER — Three-Path Scenario Router
Version : 1.0.0
Date    : 2026-05-03

Deploys to: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\scenario_router.py
Imported by: execution_intelligence_runner.py (Phase 9 / EIL)

PURPOSE
-------
Routes each signal into one of three execution scenarios based on the
alignment_score produced by swing_fusion. This replaces the implicit
single-path sizing that previously treated all signals identically.

THREE PATHS
-----------
AGGRESSIVE  — alignment_score >= 80:
    Market structure fully aligned. Phase D/E breakout with buyer control
    and Crabel ready/coiling. Enter at current price or on first retrace.
    Size: up to BASE_RISK × 1.5 (PSE scales up for high-conviction).
    DTE: 21–30 days. Contract: slightly OTM call/put.

MODERATE    — alignment_score 60–79:
    Good structure but partial confirmation. Phase C/D transition or
    COILING without full control confirmation. Wait for first break of
    shelf or volume surge. Enter limit at last test level.
    Size: BASE_RISK × 1.0. DTE: 35–45 days. Contract: ATM or slight OTM.

CONSERVATIVE — alignment_score 40–59:
    Building cause, structure present but not actionable yet. Phase B/C
    with absorption. Low-premium probe only — benefits from compression
    expanding. Enter only on confirmed structure breakout.
    Size: BASE_RISK × 0.50. DTE: 45–60 days. Contract: ATM.

OBSERVE_ONLY — alignment_score < 40 OR intent == OBSERVE_ONLY:
    No actionable path. Signal preserved as WATCH for monitoring.
    Size: 0. No entry.

CONTRACT GUIDANCE PER PATH
--------------------------
All DTE and strike guidance is advisory — OI enrichment picks the actual
contract from the chain. These values inject defaults if OI is unavailable.

OUTPUT FIELDS (written to signal row)
--------------------------------------
    scenario_path           AGGRESSIVE / MODERATE / CONSERVATIVE / OBSERVE_ONLY
    scenario_alignment      alignment_score that drove the routing
    scenario_dte_target     recommended DTE for contract selection
    scenario_size_mult      PSE size multiplier (0.0–1.5)
    scenario_entry_type     IMMEDIATE / LIMIT / CONDITIONAL
    scenario_entry_trigger  human-readable trigger description
    scenario_rationale      why this path was selected
"""

from __future__ import annotations

from typing import Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

AGGRESSIVE_THRESHOLD   = 80.0   # alignment_score >= this → AGGRESSIVE
MODERATE_THRESHOLD     = 60.0   # alignment_score >= this → MODERATE
CONSERVATIVE_THRESHOLD = 40.0   # alignment_score >= this → CONSERVATIVE
# below CONSERVATIVE_THRESHOLD → OBSERVE_ONLY

# Size multipliers (applied on top of PSE base risk)
SIZE_AGGRESSIVE   = 1.50
SIZE_MODERATE     = 1.00
SIZE_CONSERVATIVE = 0.50
SIZE_OBSERVE      = 0.00

# Default DTE targets per path
DTE_AGGRESSIVE   = 25    # short DTE — capitalise on near-term move
DTE_MODERATE     = 40    # medium DTE — allow confirmation time
DTE_CONSERVATIVE = 55    # longer DTE — compression expansion thesis


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC CONTRACT
# ─────────────────────────────────────────────────────────────────────────────

def route_scenario(row: dict) -> dict:
    """
    Route a signal row into one of three execution scenarios.

    Reads from row:
        fusion_alignment_score   (float, 0–100, from swing_fusion)
        fusion_intent            (str, from swing_fusion)
        fusion_direction         (str, LONG/SHORT/NONE)
        phase                    (str, current Wyckoff phase)
        crabel_pattern           (str, Crabel compression pattern)
        asymmetry_R              (float, structural R:R from asymmetry gate)
        rr_underlying            (float, structural price R:R)
        tier                     (int, discovery tier 0–3)

    Returns dict with scenario_* fields ready to merge into signal row.
    """
    alignment   = _safe_float(row.get('fusion_alignment_score'), 0.0)
    intent      = str(row.get('fusion_intent',    'OBSERVE_ONLY')).upper().strip()
    direction   = str(row.get('fusion_direction', 'NONE')).upper().strip()
    phase       = str(row.get('phase',            'UNKNOWN')).upper().strip()
    crabel_pat  = str(row.get('crabel_pattern',   '')).upper().strip()
    asym_r      = _safe_float(row.get('asymmetry_R'),    0.0)
    rr          = _safe_float(row.get('rr_underlying'),  0.0)
    # Note: tier=0 is falsy so must not use (row.get('tier', 3) or 3)
    _tier_raw = row.get('tier')
    tier      = int(_tier_raw) if _tier_raw is not None else 3

    # SAFE FALLBACK: if fusion fields are absent (pre-DISC-01 signal or fusion import failed),
    # route to MODERATE rather than OBSERVE_ONLY. A signal that reached the EIL runner
    # has already passed Discovery, Vanguard, OI, and SuperBrain — it has structural value.
    # OBSERVE_ONLY is only correct when swing_fusion explicitly computed it from the data.
    _fusion_populated = (
        row.get('fusion_alignment_score') is not None
        or row.get('fusion_intent') is not None
        or row.get('fusion_direction') is not None
    )
    if not _fusion_populated:
        return _result(
            path        = 'MODERATE',
            alignment   = 50.0,
            dte         = DTE_MODERATE,
            size_mult   = SIZE_MODERATE,
            entry_type  = 'LIMIT',
            trigger     = 'fusion fields absent — default MODERATE pass-through',
            rationale   = (
                'MODERATE (default): swing_fusion fields not present in row. '
                'Signal passed upstream gates — preserving at standard size. '
                'Deploy avshunter_discovery_ULTIMATE.py with DISC-01 to enable alignment routing.'
            ),
        )
        return _result(
            path        = 'OBSERVE_ONLY',
            alignment   = alignment,
            dte         = 0,
            size_mult   = SIZE_OBSERVE,
            entry_type  = 'NO_ENTRY',
            trigger     = 'swing_fusion intent=OBSERVE_ONLY or direction=NONE',
            rationale   = (
                f"No actionable path: intent={intent}, direction={direction}. "
                "Signal preserved as WATCH."
            ),
        )

    # Path selection by alignment score
    if alignment >= AGGRESSIVE_THRESHOLD:
        path      = 'AGGRESSIVE'
        dte       = DTE_AGGRESSIVE
        size_mult = SIZE_AGGRESSIVE
        entry_type = 'IMMEDIATE'
        trigger   = (
            f"Enter at market or first retrace to shelf_high. "
            f"Phase {phase}, alignment={alignment:.0f}/100."
        )
        rationale = (
            f"AGGRESSIVE: alignment={alignment:.0f} ≥ {AGGRESSIVE_THRESHOLD}. "
            f"Phase {phase} with full control + Crabel {crabel_pat}. "
            f"Structural R:R={rr:.2f}. Size={SIZE_AGGRESSIVE}×."
        )

    elif alignment >= MODERATE_THRESHOLD:
        path      = 'MODERATE'
        dte       = DTE_MODERATE
        size_mult = SIZE_MODERATE
        entry_type = 'LIMIT'
        trigger   = (
            f"Enter limit at last test level on first volume confirmation. "
            f"Phase {phase}, alignment={alignment:.0f}/100."
        )
        rationale = (
            f"MODERATE: alignment={alignment:.0f} ≥ {MODERATE_THRESHOLD}. "
            f"Structure building, partial confirmation. "
            f"Structural R:R={rr:.2f}. Size={SIZE_MODERATE}×."
        )

    elif alignment >= CONSERVATIVE_THRESHOLD:
        path      = 'CONSERVATIVE'
        dte       = DTE_CONSERVATIVE
        size_mult = SIZE_CONSERVATIVE
        entry_type = 'CONDITIONAL'
        trigger   = (
            f"Enter only on confirmed breakout above shelf_high with volume. "
            f"Phase {phase}, alignment={alignment:.0f}/100."
        )
        rationale = (
            f"CONSERVATIVE: alignment={alignment:.0f} ≥ {CONSERVATIVE_THRESHOLD}. "
            f"Cause building but not actionable. Low-premium probe. "
            f"Structural R:R={rr:.2f}. Size={SIZE_CONSERVATIVE}×."
        )

    else:
        path      = 'OBSERVE_ONLY'
        dte       = 0
        size_mult = SIZE_OBSERVE
        entry_type = 'NO_ENTRY'
        trigger   = f"alignment={alignment:.0f} < {CONSERVATIVE_THRESHOLD} — no path"
        rationale = (
            f"OBSERVE_ONLY: alignment={alignment:.0f} below all thresholds. "
            "No entry. Watch for structural improvement."
        )

    # Tier 0 (early position) always gets Conservative path regardless of alignment
    # — early signals are by definition not yet confirmed
    if tier == 0 and path == 'AGGRESSIVE':
        path       = 'MODERATE'
        size_mult  = SIZE_MODERATE
        entry_type = 'LIMIT'
        rationale  = rationale + ' [TIER_0_DOWNGRADE: early signal capped at MODERATE]'

    # Asymmetry gate veto: if R:R < 1.5 from asymmetry gate and path is AGGRESSIVE
    # downgrade to MODERATE — poor geometry despite high alignment
    if path == 'AGGRESSIVE' and asym_r > 0 and asym_r < 1.5:
        path       = 'MODERATE'
        size_mult  = SIZE_MODERATE
        entry_type = 'LIMIT'
        rationale  = rationale + f' [ASYM_R_DOWNGRADE: R={asym_r:.2f} < 1.5 → MODERATE]'

    return _result(
        path        = path,
        alignment   = alignment,
        dte         = dte,
        size_mult   = size_mult,
        entry_type  = entry_type,
        trigger     = trigger,
        rationale   = rationale,
    )


def apply_scenario_to_row(row: dict) -> dict:
    """
    Convenience wrapper: routes signal and merges scenario fields into a copy
    of the row. Returns the enriched row dict.
    """
    scenario = route_scenario(row)
    enriched = dict(row)
    enriched.update(scenario)
    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _result(
    path: str,
    alignment: float,
    dte: int,
    size_mult: float,
    entry_type: str,
    trigger: str,
    rationale: str,
) -> dict:
    return {
        'scenario_path':          path,
        'scenario_alignment':     round(alignment, 1),
        'scenario_dte_target':    dte,
        'scenario_size_mult':     round(size_mult, 2),
        'scenario_entry_type':    entry_type,
        'scenario_entry_trigger': trigger,
        'scenario_rationale':     rationale,
    }


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default
