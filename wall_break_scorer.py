"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              AVSHUNTER — WALL BREAK SCORER                                   ║
║              Layer 4b · Post-SuperBrain · Pre-Core Intel                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Purpose : Scores every EXECUTE/EXECUTE_WITH_RISK signal against a five-     ║
║            factor Wall Break Score (WBS) to determine whether the option     ║
║            position has sufficient structural energy to push price THROUGH    ║
║            the gamma wall (put_wall / call_wall) to the full structural       ║
║            target — rather than stalling at the wall and leaving R:R on the  ║
║            table.                                                             ║
║                                                                              ║
║  Inputs  : superbrain_enriched_<run_id>.csv (all SB signals)                 ║
║            options_intelligence_<run_id>.csv (OI fields incl. greeks)        ║
║                                                                              ║
║  Outputs : wall_break_scores_<run_id>.csv  (written to superbrain/ dir)      ║
║            — WBS fields appended to every EXECUTE/EWR signal row             ║
║            — POSSIBLE/PROBABLE/IMMINENT signals ranked by WBS desc           ║
║                                                                              ║
║  Grades  : IMMINENT  ≥ 75   full campaign + 25% boost, enter immediately     ║
║            PROBABLE  ≥ 55   full campaign, PATIENT entry, hold through wall  ║
║            POSSIBLE  ≥ 35   50% size, scale 60% AT wall, hold 40% for break  ║
║            UNLIKELY  < 35   take partial at wall only — do not hold for break ║
║                                                                              ║
║  Usage   : python wall_break_scorer.py <sb_enriched_csv> <oi_csv>            ║
║                                        [run_id] [output_dir]                 ║
║                                                                              ║
║  Called via run_wall_break_scorer(run_id, output_dir) from orchestrator      ║
║  Insert AFTER run_superbrain_layer() BEFORE core_intel_exporter()            ║
╚══════════════════════════════════════════════════════════════════════════════╝

CHANGELOG
─────────────────────────────────────────────────────────────────────────────
v1.0  2026-03-06  Initial production release.
                  Five factors: F1 vanna, F2 wall weakness, F3 flip clearance,
                  F4 vol loading, F5 momentum alignment.
                  Grades: IMMINENT/PROBABLE/POSSIBLE/UNLIKELY.
                  Outputs wall_break_scores_{run_id}.csv to superbrain/ dir.
                  Trigger prices: phase_b_trigger, phase_c_trigger,
                  rejection_stop computed per signal.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WBS] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('wall_break_scorer')

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — tune after 30+ closed trades against realised outcomes
# ─────────────────────────────────────────────────────────────────────────────

# Grade thresholds (WBS out of 100)
GRADE_IMMINENT   = 75   # full campaign + 25% boost
GRADE_PROBABLE   = 55   # full campaign, hold through wall
GRADE_POSSIBLE   = 35   # 50% size, scale at wall
# < GRADE_POSSIBLE = UNLIKELY

# Factor weights (each 0–20, total max = 100)
F1_MAX           = 20   # vanna magnitude
F2_MAX           = 20   # wall weakness (inverse gamma_flip_conf)
F3_MAX           = 20   # gamma flip clearance
F4_MAX           = 20   # vol loading (IV vs HV)
F5_MAX           = 20   # momentum alignment (gamma velocity + PCR)

# WBS-01 (FIX-11): Vanna calibration constant.
# ATM vanna for equity options is ~0.01–0.05 (delta per 1% IV change).
# Previous formula: abs(vanna) * 20 → F1=0.2–1.0/20 for real values (1–5% of max).
# Fixed formula: abs(vanna)/VANNA_FULL_SCORE * 20 → F1=4–20/20 at realistic ATM levels.
# VANNA_FULL_SCORE=0.05 means: an ATM vanna of 0.05 earns full F1 score.
VANNA_FULL_SCORE = 0.05

# F3 normalisation denominator — gap_pct at which F3 scores full 20
F3_GAP_NORM      = 50.0

# F4 amplification — cheap vol multiplier (iv_vs_hv < 1.0)
F4_CHEAP_MULT    = 40.0
# F4 decay — expensive vol decay (iv_vs_hv >= 1.0)
F4_EXP_DECAY     = 10.0

# F5 gamma velocity scores
F5_GV_SCORES: Dict[str, int] = {
    'IMMINENT':    20,
    'APPROACHING': 15,
    'STALLING':     5,
    'DISTANT':      5,
    'MOVING_AWAY':  2,
}
F5_PCR_BONUS     = 5    # added when PCR confirms direction
F5_PCR_PUT_MIN   = 0.8  # PUT trade: pcr_vol above this = put pressure building
F5_PCR_CALL_MAX  = 0.4  # CALL trade: pcr_vol below this = call pressure building

# Phase B/C trigger offsets
PHASE_B_BUFFER_PCT = 2.0   # 2% inside wall = watching zone
PHASE_C_BUFFER_PCT = 0.5   # 0.5% through wall = confirmed break level
REJECTION_BUFFER   = 0.5   # 0.5% back above wall = rejection confirmed

# WBS is an advisory structural assessment, not an execution authority. A
# completed-session run intentionally has no EXECUTE verdict before Morning
# validation, so route vocabulary is the canonical selection boundary.
ACTIONABLE_VERDICTS = {'EXECUTE', 'EXECUTE_WITH_RISK'}
WBS_ELIGIBLE_ROUTES = {
    'OPTIONS_GO_REVIEW',
    'OPTIONS_ARMED_HALF',
    'OPTIONS_PROBE_ONLY',
}

WBS_OUTPUT_COLUMNS = [
    'wbs', 'wbs_grade', 'wbs_f1_vanna', 'wbs_f2_wall_weakness',
    'wbs_f3_flip_clear', 'wbs_f4_vol_loading', 'wbs_f5_momentum',
    'wbs_pcr_volume_state', 'wbs_wall_price', 'wbs_wall_dist_pct',
    'wbs_phase_b_trigger', 'wbs_phase_c_trigger', 'wbs_rejection_stop',
    'wbs_notes', 'runway_to_wall_pct', 'pin_risk_score',
    'wbs_size_guidance', 'wbs_entry_guidance', 'wbs_phase_b_guidance',
    'wbs_phase_c_guidance', 'wbs_stop_guidance', 'wbs_wall_stall_rule',
]


# ─────────────────────────────────────────────────────────────────────────────
# CORE SCORING FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def _f(d: dict, key: str, default: float = 0.0) -> float:
    """Safe float extraction."""
    try:
        v = d.get(key)
        if v is None or str(v).strip() in ('', 'nan', 'None', 'NaN'):
            return default
        return float(v)
    except (ValueError, TypeError):
        return default


def _s(d: dict, key: str, default: str = '') -> str:
    """Safe string extraction."""
    v = d.get(key)
    if v is None:
        return default
    return str(v).strip()


def score_wall_break(signal: dict, oi: dict) -> dict:
    """
    Compute the Wall Break Score (WBS) for a single signal.

    Parameters
    ----------
    signal : dict   Row from superbrain_enriched CSV
    oi     : dict   Matching row from options_intelligence CSV

    Returns
    -------
    dict with keys: wbs, wbs_grade, wbs_f1_vanna, wbs_f2_wall_weakness,
                    wbs_f3_flip_clear, wbs_f4_vol_loading, wbs_f5_momentum,
                    wbs_wall_price, wbs_wall_distance_pct,
                    wbs_phase_b_trigger, wbs_phase_c_trigger,
                    wbs_rejection_stop, wbs_notes
    """
    direction   = _s(oi, 'options_direction') or _s(signal, 'direction')
    vanna       = _f(oi, 'contract_vanna')
    gfc         = _f(oi, 'gamma_flip_conf',    default=0.5)
    gfg         = _f(oi, 'gamma_flip_gap_pct', default=0.0)
    iv_hv       = _f(oi, 'iv_vs_hv',           default=1.0)
    gv_label    = _s(oi, 'gamma_velocity_label')
    pcr_vol_raw = oi.get('pcr_vol')
    pcr_status  = _s(oi, 'pcr_vol_status').upper()
    pcr_missing = (
        pcr_vol_raw is None
        or str(pcr_vol_raw).strip() in ('', 'nan', 'None', 'NaN')
        or any(marker in pcr_status for marker in ('OI_ONLY', 'NO_INTRADAY', 'UNAVAILABLE', 'MISSING'))
    )
    pcr_vol     = None if pcr_missing else _f(oi, 'pcr_vol', default=0.0)
    spot        = _f(oi, 'underlying_price') or _f(signal, 'underlying_price')
    put_wall    = _f(oi, 'put_wall')
    call_wall   = _f(oi, 'call_wall')
    target      = _f(oi, 'structural_target') or _f(signal, 'structural_target')
    notes: List[str] = []

    # ── F1 — Vanna Acceleration Fuel (0–20) ──────────────────────────────────
    # WBS-01: Normalise by VANNA_FULL_SCORE (0.05) so ATM-range vanna scores meaningfully.
    # |vanna|=0.05 → F1=20, |vanna|=0.02 → F1=8, |vanna|=0.01 → F1=4.
    if direction == 'PUT':
        f1 = min(F1_MAX, abs(min(vanna, 0.0)) / VANNA_FULL_SCORE * F1_MAX)
        if vanna < -0.5:
            notes.append(f'Strong neg vanna ({vanna:.3f}) — high wall-break fuel')
        elif vanna < -0.2:
            notes.append(f'Moderate neg vanna ({vanna:.3f})')
        else:
            notes.append(f'Weak vanna ({vanna:.3f}) — limited cascade potential')
    elif direction == 'CALL':
        f1 = min(F1_MAX, max(vanna, 0.0) / VANNA_FULL_SCORE * F1_MAX)
        if vanna > 0.5:
            notes.append(f'Strong pos vanna ({vanna:.3f}) — high wall-break fuel')
        else:
            notes.append(f'Moderate/weak vanna ({vanna:.3f})')
    else:
        # STRANGLE or unknown — use magnitude
        f1 = min(F1_MAX, abs(vanna) / VANNA_FULL_SCORE * F1_MAX)
        notes.append(f'Non-directional — vanna magnitude used ({abs(vanna):.3f})')

    # ── F2 — Wall Weakness (0–20) ─────────────────────────────────────────────
    # Low gamma_flip_conf = thin dealer OI at wall strike = easier to breach
    gfc_clamped = min(max(gfc, 0.0), 1.0)
    f2 = (1.0 - gfc_clamped) * F2_MAX
    if gfc < 0.1:
        notes.append(f'Wall virtually undefended (conf={gfc:.3f}) — very weak')
    elif gfc < 0.3:
        notes.append(f'Wall lightly defended (conf={gfc:.3f})')
    else:
        notes.append(f'Wall moderately/heavily defended (conf={gfc:.3f})')

    # ── F3 — Gamma Flip Clearance (0–20) ─────────────────────────────────────
    # Large gap = gamma flip is far from the wall = dealers won't switch regime near wall
    f3 = min(F3_MAX, (gfg / F3_GAP_NORM) * F3_MAX)
    if gfg > 40:
        notes.append(f'Gamma flip far ({gfg:.1f}%) — no flip interference near wall')
    elif gfg > 20:
        notes.append(f'Gamma flip moderate distance ({gfg:.1f}%)')
    else:
        notes.append(f'Gamma flip CLOSE ({gfg:.1f}%) — flip may amplify against thesis near wall')

    # ── F4 — Vol Loading (0–20) ───────────────────────────────────────────────
    # Cheap IV (iv_vs_hv < 1.0) → expansion likely → feeds vanna cascade
    if iv_hv < 1.0:
        f4 = min(F4_MAX, (1.0 - iv_hv) * F4_CHEAP_MULT)
        notes.append(f'Vol cheap vs realised (iv/hv={iv_hv:.3f}) — expansion likely')
    else:
        f4 = max(0.0, (2.0 - iv_hv) * F4_EXP_DECAY)
        if iv_hv > 1.5:
            notes.append(f'Vol expensive (iv/hv={iv_hv:.3f}) — expansion unlikely')
        else:
            notes.append(f'Vol near parity (iv/hv={iv_hv:.3f})')

    # ── F5 — Momentum Alignment (0–20) ───────────────────────────────────────
    # Gamma velocity + PCR direction confirmation
    f5 = float(F5_GV_SCORES.get(gv_label, 5))
    if pcr_vol is None:
        notes.append(f'GV={gv_label}; intraday PCR unavailable — no PCR momentum bonus')
    elif direction == 'PUT' and pcr_vol > F5_PCR_PUT_MIN:
        f5 = min(F5_MAX, f5 + F5_PCR_BONUS)
        notes.append(f'GV={gv_label} + PCR_vol={pcr_vol:.2f} confirms PUT pressure')
    elif direction == 'CALL' and pcr_vol < F5_PCR_CALL_MAX:
        f5 = min(F5_MAX, f5 + F5_PCR_BONUS)
        notes.append(f'GV={gv_label} + PCR_vol={pcr_vol:.2f} confirms CALL pressure')
    else:
        notes.append(f'GV={gv_label} (pcr_vol={pcr_vol:.2f} — no PCR bonus)')

    # ── Total + Grade ─────────────────────────────────────────────────────────
    wbs = f1 + f2 + f3 + f4 + f5
    if wbs >= GRADE_IMMINENT:
        grade = 'IMMINENT'
    elif wbs >= GRADE_PROBABLE:
        grade = 'PROBABLE'
    elif wbs >= GRADE_POSSIBLE:
        grade = 'POSSIBLE'
    else:
        grade = 'UNLIKELY'

    # ── Wall Price + Trigger Levels ───────────────────────────────────────────
    if direction == 'PUT' and put_wall and spot:
        wall_price       = put_wall
        wall_dist_pct    = 100.0 * (spot - put_wall) / spot if spot else 0.0
        phase_b_trigger  = put_wall * (1.0 + PHASE_B_BUFFER_PCT / 100.0)  # 2% above wall = watching zone
        phase_c_trigger  = put_wall * (1.0 - PHASE_C_BUFFER_PCT / 100.0)  # 0.5% below wall = confirmed break
        rejection_stop   = put_wall * (1.0 + REJECTION_BUFFER  / 100.0)   # 0.5% back above = rejected
    elif direction == 'CALL' and call_wall and spot:
        wall_price       = call_wall
        wall_dist_pct    = 100.0 * (call_wall - spot) / spot if spot else 0.0
        phase_b_trigger  = call_wall * (1.0 - PHASE_B_BUFFER_PCT / 100.0)
        phase_c_trigger  = call_wall * (1.0 + PHASE_C_BUFFER_PCT / 100.0)
        rejection_stop   = call_wall * (1.0 - REJECTION_BUFFER  / 100.0)
    else:
        wall_price = phase_b_trigger = phase_c_trigger = rejection_stop = 0.0
        wall_dist_pct = 0.0

    return {
        'wbs':                  round(wbs,   1),
        'wbs_grade':            grade,
        'wbs_f1_vanna':         round(f1,    2),
        'wbs_f2_wall_weakness': round(f2,    2),
        'wbs_f3_flip_clear':    round(f3,    2),
        'wbs_f4_vol_loading':   round(f4,    2),
        'wbs_f5_momentum':      round(f5,    2),
        'wbs_pcr_volume_state': 'UNAVAILABLE' if pcr_vol is None else 'AVAILABLE',
        'wbs_wall_price':       round(wall_price,       2) if wall_price else '',
        'wbs_wall_dist_pct':    round(wall_dist_pct,    2) if wall_dist_pct else '',
        'wbs_phase_b_trigger':  round(phase_b_trigger,  2) if phase_b_trigger else '',
        'wbs_phase_c_trigger':  round(phase_c_trigger,  2) if phase_c_trigger else '',
        'wbs_rejection_stop':   round(rejection_stop,   2) if rejection_stop else '',
        'wbs_notes':            ' | '.join(notes),
        # ── D6: Q-OMEGA Layer 7 formalised fields ────────────────────────────
        # runway_to_wall_pct: % distance from current price to the relevant gamma wall.
        # This is the formal Q-OMEGA field — wbs_wall_dist_pct is the same value
        # but kept separately for backward compatibility.
        'runway_to_wall_pct':   round(wall_dist_pct, 2) if wall_dist_pct else 0.0,
        # pin_risk_score: 0-100. High score = price likely to get pinned at wall.
        # Computed as inverse of runway × wall defence strength.
        # Low runway + heavily defended wall = high pin risk.
        # Formula: pin_risk = (1 - min(wall_dist_pct/10, 1)) * gfc_clamped * 100
        # where wall_dist_pct/10 normalises 10% runway to 1.0 (zero pin risk).
        'pin_risk_score':       round(
            max(0.0, (1.0 - min(wall_dist_pct / 10.0, 1.0)) * gfc_clamped * 100)
            if wall_dist_pct is not None and wall_dist_pct >= 0
            else 0.0,
            1
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIZING GUIDANCE — returns plain-English execution guidance per grade
# ─────────────────────────────────────────────────────────────────────────────

GRADE_GUIDANCE: Dict[str, Dict[str, str]] = {
    'IMMINENT': {
        'size':       'Full campaign + 25% boost',
        'entry':      'Enter within 15 min of open (IMMEDIATE)',
        'phase_b':    'Hold 100% — do not scale at wall. Trust the break.',
        'phase_c':    'Add 25% on confirmed break candle.',
        'stop':       '30% premium (wider — break is confirmed).',
        'wall_stall': 'If wall holds 3 sessions: close ALL. Thesis failed.',
    },
    'PROBABLE': {
        'size':       'Full campaign size (no boost)',
        'entry':      'PATIENT — enter 9:45 AM after opening range confirmed',
        'phase_b':    'Scale 40% if stalls 2 candles at wall. Hold 60% for break.',
        'phase_c':    'Hold remaining 60% to structural target.',
        'stop':       '35% premium standard.',
        'wall_stall': 'If wall holds 3 sessions: close 60%, hold 40% max.',
    },
    'POSSIBLE': {
        'size':       '50% of campaign size only',
        'entry':      'PATIENT — requires 2 of 4 intraday triggers confirmed',
        'phase_b':    'Scale 60% at wall. Hold 40% only if break looks imminent.',
        'phase_c':    'Hold remaining 40% — do NOT add at break.',
        'stop':       '35% premium standard.',
        'wall_stall': 'If wall holds 2 sessions: close ALL. Take the partial.',
    },
    'UNLIKELY': {
        'size':       'Do not trade for wall break — take wall as exit target',
        'entry':      'No change to standard entry',
        'phase_b':    'Scale OUT 70-80% AT the wall. Lock the partial.',
        'phase_c':    'Hold 20-30% max — do not add, do not expect break.',
        'stop':       '35% premium standard.',
        'wall_stall': 'Wall is the exit level. Accept partial. Move on.',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_wall_break_scorer(
    sb_enriched_csv:  str,
    oi_csv:           str,
    run_id:           str = '',
    output_dir:       str = '',
) -> Tuple[pd.DataFrame, str]:
    """
    Main entry point. Reads SB and OI CSVs, scores all EXECUTE/EWR signals,
    writes wall_break_scores_{run_id}.csv.

    Returns
    -------
    df_scored  : DataFrame of scored signals (all EXECUTE/EWR)
    output_csv : path to written CSV ('' on failure)
    """
    run_id  = run_id  or datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = output_dir or os.path.dirname(os.path.abspath(sb_enriched_csv))
    os.makedirs(out_dir, exist_ok=True)

    log.info(f'Run ID     : {run_id}')
    log.info(f'SB CSV     : {sb_enriched_csv}')
    log.info(f'OI CSV     : {oi_csv}')
    log.info(f'Output dir : {out_dir}')

    # ── Load inputs ───────────────────────────────────────────────────────────
    try:
        df_sb = pd.read_csv(sb_enriched_csv, dtype=str)
        log.info(f'SB rows loaded   : {len(df_sb)}')
    except Exception as e:
        log.error(f'Failed to load SB CSV: {e}')
        return pd.DataFrame(), ''

    try:
        df_oi = pd.read_csv(oi_csv, dtype=str)
        log.info(f'OI rows loaded   : {len(df_oi)}')
    except Exception as e:
        log.error(f'Failed to load OI CSV: {e}')
        return pd.DataFrame(), ''

    # ── Filter to actionable verdicts ─────────────────────────────────────────
    if 'final_route' in df_sb.columns:
        df_exe = df_sb[df_sb['final_route'].isin(WBS_ELIGIBLE_ROUTES)].copy()
        selection_values = df_exe['final_route'].value_counts().to_dict().keys()
        selection_basis = 'final_route'
    else:
        # Compatibility for historical frames predating Options research routes.
        df_exe = df_sb[df_sb['sb_final_verdict'].isin(ACTIONABLE_VERDICTS)].copy()
        selection_values = df_exe['sb_final_verdict'].value_counts().to_dict().keys()
        selection_basis = 'sb_final_verdict'
    log.info(
        'WBS advisory population: %d | basis=%s | states=%s',
        len(df_exe), selection_basis, ', '.join(selection_values),
    )

    if df_exe.empty:
        log.info('No WBS-eligible research routes — writing valid empty output.')
        out_path = os.path.join(out_dir, f'wall_break_scores_{run_id}.csv')
        output_columns = list(dict.fromkeys([*df_sb.columns, *WBS_OUTPUT_COLUMNS]))
        empty_output = pd.DataFrame(columns=output_columns)
        empty_output.to_csv(out_path, index=False)
        return empty_output, out_path

    # ── Build OI lookup by ticker ─────────────────────────────────────────────
    oi_lookup: Dict[str, dict] = {}
    for _, row in df_oi.iterrows():
        ticker = str(row.get('ticker', '')).strip().upper()
        if ticker:
            oi_lookup[ticker] = row.to_dict()

    # ── Score every signal ────────────────────────────────────────────────────
    scored_rows: List[dict] = []
    missing_oi  = 0

    for _, sb_row in df_exe.iterrows():
        ticker = str(sb_row.get('ticker', '')).strip().upper()
        oi_row = oi_lookup.get(ticker, {})
        if not oi_row:
            missing_oi += 1
            log.debug(f'No OI row for {ticker} — scoring with SB fields only')

        # Merge: SB fields as base, OI fields override for greek/wall data
        merged = {**sb_row.to_dict(), **oi_row}

        wbs_fields = score_wall_break(merged, oi_row if oi_row else merged)

        # Add guidance
        grade     = wbs_fields['wbs_grade']
        guidance  = GRADE_GUIDANCE.get(grade, {})
        wbs_fields['wbs_size_guidance']    = guidance.get('size', '')
        wbs_fields['wbs_entry_guidance']   = guidance.get('entry', '')
        wbs_fields['wbs_phase_b_guidance'] = guidance.get('phase_b', '')
        wbs_fields['wbs_phase_c_guidance'] = guidance.get('phase_c', '')
        wbs_fields['wbs_stop_guidance']    = guidance.get('stop', '')
        wbs_fields['wbs_wall_stall_rule']  = guidance.get('wall_stall', '')

        # Combine into output row — keep all original SB fields + WBS additions
        out_row = {**sb_row.to_dict(), **wbs_fields}
        scored_rows.append(out_row)

    if missing_oi:
        log.warning(f'{missing_oi} signals had no matching OI row — scored from SB fields only')

    # ── Assemble and sort ─────────────────────────────────────────────────────
    df_scored = pd.DataFrame(scored_rows)
    df_scored['wbs'] = pd.to_numeric(df_scored['wbs'], errors='coerce')
    df_scored = df_scored.sort_values('wbs', ascending=False)

    # ── Grade summary ─────────────────────────────────────────────────────────
    grade_counts = df_scored['wbs_grade'].value_counts().to_dict()
    log.info('Wall Break Grade distribution:')
    for g in ['IMMINENT', 'PROBABLE', 'POSSIBLE', 'UNLIKELY']:
        log.info(f'  {g:10s}: {grade_counts.get(g, 0)}')

    avg_wbs  = df_scored['wbs'].mean()
    max_wbs  = df_scored['wbs'].max()
    log.info(f'WBS avg={avg_wbs:.1f}  max={max_wbs:.1f}')

    # ── Write output ──────────────────────────────────────────────────────────
    out_path = os.path.join(out_dir, f'wall_break_scores_{run_id}.csv')
    df_scored.to_csv(out_path, index=False)
    log.info(f'Written: {out_path}  ({len(df_scored)} rows)')

    # ── Write summary JSON ────────────────────────────────────────────────────
    # FIX-06: Guard column selection — rr may be absent; rr_underlying preferred since FIX-01.
    _top_cols = [c for c in ['ticker', 'wbs', 'wbs_grade', 'rr_underlying', 'rr']
                 if c in df_scored.columns]

    # Compute WBS field completeness — % of factor fields deviating from known defaults.
    # Tells downstream modules how much real OI data fed the score vs defaults.
    _factor_defaults = {
        'wbs_f1_vanna':         0.0,
        'wbs_f2_wall_weakness': 10.0,
        'wbs_f3_flip_clear':    0.0,
        'wbs_f4_vol_loading':   0.0,
        'wbs_f5_momentum':      5.0,
    }
    _completeness_scores = []
    for _col, _default in _factor_defaults.items():
        if _col in df_scored.columns:
            _pct_real = float((pd.to_numeric(df_scored[_col], errors='coerce') != _default).mean())
            _completeness_scores.append(_pct_real)
    _wbs_completeness = round(
        float(sum(_completeness_scores) / len(_completeness_scores) * 100)
        if _completeness_scores else 0.0, 1
    )

    summary = {
        'run_id':                     run_id,
        'generated_at':               datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'producer':                   'wall_break_scorer.py v1.0',
        'total_scored':               len(df_scored),
        'grade_counts':               grade_counts,
        'wbs_avg':                    round(avg_wbs, 1),
        'wbs_max':                    round(max_wbs, 1),
        'wbs_valid':                  True,
        'wbs_field_completeness_pct': _wbs_completeness,
        'top_5': df_scored[_top_cols].head(5).to_dict(orient='records'),
    }
    summary_path = os.path.join(out_dir, f'wall_break_summary_{run_id}.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    log.info(f'Summary : {summary_path}')

    return df_scored, out_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='AVSHUNTER Wall Break Scorer — Layer 4b',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python wall_break_scorer.py superbrain_enriched_20260306_090000.csv \\
                              options_intelligence_20260306_090000.csv

  python wall_break_scorer.py superbrain_enriched.csv options_intelligence.csv \\
                              20260306_090000 runs/20260306_090000/superbrain
        """
    )
    p.add_argument('sb_csv',       help='Path to superbrain_enriched_<run_id>.csv')
    p.add_argument('oi_csv',       help='Path to options_intelligence_<run_id>.csv')
    p.add_argument('run_id',       nargs='?', default='',
                   help='Run ID string (default: auto timestamp)')
    p.add_argument('output_dir',   nargs='?', default='',
                   help='Output directory (default: same dir as sb_csv)')
    p.add_argument('--ticker',     default='',
                   help='Score a single ticker and print detail (for testing)')
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if not os.path.isfile(args.sb_csv):
        log.error(f'SB CSV not found: {args.sb_csv}')
        sys.exit(1)
    if not os.path.isfile(args.oi_csv):
        log.error(f'OI CSV not found: {args.oi_csv}')
        sys.exit(1)

    df, out_path = run_wall_break_scorer(
        sb_enriched_csv = args.sb_csv,
        oi_csv          = args.oi_csv,
        run_id          = args.run_id,
        output_dir      = args.output_dir,
    )

    if df.empty:
        if out_path and os.path.isfile(out_path):
            log.info('Valid empty WBS advisory output produced.')
            return
        log.error('No output produced.')
        sys.exit(1)

    # ── Optional: single-ticker detail ───────────────────────────────────────
    if args.ticker:
        t = args.ticker.upper()
        row = df[df['ticker'].str.upper() == t]
        if row.empty:
            log.warning(f'{t} not found in scored output.')
        else:
            r = row.iloc[0]
            print(f'\n{"─"*60}')
            print(f'  WALL BREAK DETAIL — {t}')
            print(f'{"─"*60}')
            print(f'  WBS Total    : {r["wbs"]}  ({r["wbs_grade"]})')
            print(f'  F1 Vanna     : {r["wbs_f1_vanna"]}  / 20')
            print(f'  F2 Wall Weak : {r["wbs_f2_wall_weakness"]}  / 20')
            print(f'  F3 Flip Clear: {r["wbs_f3_flip_clear"]}  / 20')
            print(f'  F4 Vol Load  : {r["wbs_f4_vol_loading"]}  / 20')
            print(f'  F5 Momentum  : {r["wbs_f5_momentum"]}  / 20')
            print(f'  Wall Price   : ${r.get("wbs_wall_price", "n/a")}')
            print(f'  Wall Dist    : {r.get("wbs_wall_dist_pct", "n/a")}%')
            print(f'  Phase B Trig : ${r.get("wbs_phase_b_trigger", "n/a")}  (watching zone)')
            print(f'  Phase C Trig : ${r.get("wbs_phase_c_trigger", "n/a")}  (confirmed break)')
            print(f'  Reject Stop  : ${r.get("wbs_rejection_stop", "n/a")}')
            print(f'  Size         : {r.get("wbs_size_guidance", "")}')
            print(f'  Entry        : {r.get("wbs_entry_guidance", "")}')
            print(f'  Phase B      : {r.get("wbs_phase_b_guidance", "")}')
            print(f'  Phase C      : {r.get("wbs_phase_c_guidance", "")}')
            print(f'  Notes        : {r.get("wbs_notes", "")}')
            print(f'{"─"*60}\n')

    print(f'\nWall Break Scorer complete -> {out_path}\n')


if __name__ == '__main__':
    main()
