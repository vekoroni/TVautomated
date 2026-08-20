"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              AVSHUNTER — CATASTROPHE GATE                                    ║
║              Layer 3b · Post-OI · Pre-SuperBrain                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Purpose : Computes seven Catastrophe Theory (CT) derived fields per signal  ║
║            based on René Thom's Cusp/Fold Catastrophe framework. Maps        ║
║            existing greek/structure fields onto CT geometry to detect:       ║
║              1. Bifurcation proximity  (how close to discontinuous jump)     ║
║              2. Divergence set signals (pre-jump hypersensitivity zone)      ║
║              3. Hysteresis stop offset (asymmetric stop for re-test entries) ║
║              4. Position size scalar   (replaces EV haircut — see notes)     ║
║              5. Vanna/charm quadrant   (cusp surface position)               ║
║                                                                              ║
║  SHADOW MODE (default): Computes and logs CT fields but does NOT feed them   ║
║  into SuperBrain sizing or EV decisions. SuperBrain reads ct_enriched CSV    ║
║  for information only. Activate live mode after 30 closed trades.            ║
║                                                                              ║
║  ZERO IMPACT on existing outputs in shadow mode. Writes ct_enriched_{ts}.csv ║
║  alongside existing pipeline files. SuperBrain, OI, and Discovery unchanged. ║
║                                                                              ║
║  Inputs   : options_intelligence_<run_id>.csv  (OI greeks + structure)       ║
║             superbrain_enriched_<run_id>.csv   (SB fields + veto codes)      ║
║             vanguard_signals.csv or             (auction state, EV, conf)    ║
║             vanguard_signals_enriched_<run_id>.csv                           ║
║             discovery_candidates_ultimate_<run_id>.csv  (crabel, atr)        ║
║                                                                              ║
║  Outputs  : ct_enriched_<run_id>.csv  (written to superbrain/ dir)           ║
║             ct_summary_<run_id>.json                                         ║
║                                                                              ║
║  Usage    : python catastrophe_gate.py <oi_csv> <sb_csv> <vg_csv>            ║
║                                         <disc_csv> [run_id] [output_dir]     ║
║                                         [--live]                             ║
║                                                                              ║
║  Called via run_catastrophe_gate(run_id, output_dir) from orchestrator.      ║
║  Insert AFTER run_options_intelligence() BEFORE run_superbrain_layer().      ║
╚══════════════════════════════════════════════════════════════════════════════╝

DESIGN NOTES — READ BEFORE MODIFYING
─────────────────────────────────────────────────────────────────────────────
CT THEORY MAPPING (working hypotheses — not proven laws):

  Gamma flip      → Fold catastrophe boundary
                    Above flip: dealers dampen vol (stable state)
                    Below flip: dealers amplify vol (unstable state)
                    Crossing = discontinuous regime change

  Vanna           → Normal factor (slow control variable of cusp)
                    Negative vanna on PUT = delta accelerates when vol rises
                    Directly drives the vanna cascade that breaks walls

  Charm           → Splitting factor (fast control variable of cusp)
                    Time-decay sensitivity of delta
                    Together with vanna determines cusp surface position

  Phase B→C       → Fold catastrophe (spring/snap event)
  Phase C→D       → Cusp jump (breakout — discontinuous, no middle path)

  Auction state   → System stability near bifurcation
                    TRANSITIONING = approaching fold boundary

  NR7/Crabel      → Energy accumulation on cusp surface before jump

FORMULA NOTES:
  ct_bifurcation_proximity uses NORMALISED weighted blend.
  Each input component is scaled to 0–1 across the run universe before
  blending. This prevents vanna (scale 0–1) from being swamped by
  gamma_flip_gap_pct (scale 0–100+) in the additive formula.

  Data audit on run 20260305_092339 confirmed:
    Old formula: Term2 dominated Term1 by 9.7× → vanna was noise
    Corrected formula: range 0.033–0.684, well-behaved distribution

EV HAIRCUT DECISION:
  Original architecture proposed ct_ev_adjusted = EV × stability_coeff.
  THIS WAS REMOVED after QA review confirmed:
    High |vanna| signals avg R:R = 1.094 vs Low |vanna| avg R:R = 0.078
    For long options, near-boundary instability is BENEFICIAL (convex payoff)
    An EV haircut would penalise the highest-potential signals
  REPLACEMENT: ct_position_size_scalar reduces capital at risk near boundary
  without touching the EV figure. EV remains as Vanguard computed it.

CALIBRATION:
  VARIANCE_SCALAR initial value = 0.4
  Review after every 10 closed trades using trade_journal calibration report.
  NEVER auto-adjust — human reviews and manually updates the constant below.

─────────────────────────────────────────────────────────────────────────────
CHANGELOG
─────────────────────────────────────────────────────────────────────────────
v1.0  2026-03-06  Initial build. Shadow mode only.
                  Corrected proximity formula (normalised weighted blend).
                  EV haircut replaced by position_size_scalar.
                  Full I/O contract with data quality scoring.
                  Missing field handling: ct_data_quality_score gates output.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [CT-GATE] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('catastrophe_gate')


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS — tune via calibration report after 30 closed trades
# ─────────────────────────────────────────────────────────────────────────────

# Proximity formula weights — must sum to 1.0
W_VANNA    = 0.35   # most mechanically important for wall-break cascade
W_GFC      = 0.30   # wall defence strength
W_GAP      = 0.20   # gamma flip clearance
W_IV       = 0.15   # vol loading (cheap vol = more cascade fuel)

# Divergence set threshold — proximity above this = pre-jump hypersensitivity
DIVERGENCE_SET_THRESHOLD = 0.70

# Position size scalar — reduces deployed capital near fold boundary
# ct_position_size_scalar = 1 − (proximity × VARIANCE_SCALAR)
# Calibrate against closed trade outcomes — do not auto-adjust
VARIANCE_SCALAR = 0.40

# Hysteresis offset — widens stop for re-test (LOWER sheet) entries
BIFURCATION_GAP_SCALAR = 0.30   # stop_offset = proximity × BIFURCATION_GAP_SCALAR × breakeven_pct

# Data quality — minimum score to populate CT fields (avoid scoring on bad data)
MIN_DATA_QUALITY_SCORE = 0.50   # 0–1 scale; below this → ct fields set to None

# Phase-to-catastrophe mapping
CATASTROPHE_PHASE_MAP = {
    'B': 'FOLD_APPROACHING',   # accumulation, near boundary
    'C': 'FOLD_BOUNDARY',      # spring/test — at the fold
    'D': 'CUSP_JUMP',          # breakout — past the discontinuity
    'E': 'POST_JUMP',          # trend mature, far from boundary
    'A': 'PRE_FOLD',           # early base, far from jump
}

# Vanguard column aliases (deep nested names in vanguard_signals.csv)
VG_AUCTION_STATE     = 'layer1__auction_state'
VG_CONTROL_CONF      = 'layer1__control__confidence'
VG_EV_20D            = 'layer2__expected_value_20d'
VG_WIN_RATE          = 'layer2__win_rate_20d'
VG_TREND_MATURITY    = 'layer2__trend_maturity'
VG_VOL_REGIME        = 'layer2__vol_regime'
VG_N_OBS             = 'layer2__n_observations'


# ─────────────────────────────────────────────────────────────────────────────
# SAFE FIELD ACCESSORS
# ─────────────────────────────────────────────────────────────────────────────

def _f(d: dict, key: str, default=None) -> Optional[float]:
    v = d.get(key)
    if v is None or str(v).strip() in ('', 'nan', 'None', 'NaN', 'inf', '-inf'):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _s(d: dict, key: str, default: str = '') -> str:
    v = d.get(key)
    return str(v).strip() if v is not None else default


# ─────────────────────────────────────────────────────────────────────────────
# DATA QUALITY SCORING
# ─────────────────────────────────────────────────────────────────────────────

def compute_data_quality(oi: dict, vg: dict, disc: dict) -> Tuple[float, List[str]]:
    """
    Score data quality 0–1 for this signal's CT computation.
    Returns (quality_score, list_of_missing_fields).
    Quality < MIN_DATA_QUALITY_SCORE → CT fields will not be populated.
    """
    # Required fields with their sources
    required = {
        'contract_vanna':       oi,
        'contract_charm':       oi,
        'gamma_flip_conf':      oi,
        'gamma_flip_gap_pct':   oi,
        'iv_vs_hv':             oi,
        'options_direction':    oi,
        'underlying_price':     oi,
    }
    # Important but not critical
    useful = {
        VG_AUCTION_STATE:    vg,
        VG_CONTROL_CONF:     vg,
        'crabel_score':      disc,
        'atr_pct':           disc,
    }

    missing_required = []
    missing_useful   = []

    for field, source in required.items():
        v = _f(source, field) if field != 'options_direction' else _s(source, field)
        if v is None or v == '':
            missing_required.append(field)

    for field, source in useful.items():
        v = _f(source, field) if field not in ('options_direction', VG_AUCTION_STATE) \
            else _s(source, field)
        if v is None or v == '':
            missing_useful.append(field)

    # Score: required fields = 0.70 total weight, useful = 0.30
    req_score  = (len(required) - len(missing_required)) / len(required) * 0.70
    use_score  = (len(useful)   - len(missing_useful))   / len(useful)   * 0.30
    quality    = round(req_score + use_score, 3)

    all_missing = missing_required + missing_useful
    return quality, all_missing


# ─────────────────────────────────────────────────────────────────────────────
# NORMALISATION — run-level, computed once before scoring
# ─────────────────────────────────────────────────────────────────────────────

def compute_run_normalisation(df_oi: pd.DataFrame) -> dict:
    """
    Compute normalisation parameters from the full OI universe for this run.
    Each proximity component is normalised to 0–1 before blending.
    """
    def safe_range(series: pd.Series):
        s = pd.to_numeric(series, errors='coerce').dropna()
        mn, mx = s.min(), s.max()
        rng = mx - mn
        return float(mn), float(mx), float(rng) if rng > 0 else 1.0

    vanna_min, vanna_max, vanna_rng = safe_range(df_oi.get('contract_vanna', pd.Series()))
    gfc_min, gfc_max, gfc_rng       = safe_range(df_oi.get('gamma_flip_conf', pd.Series()))
    gfg_min, gfg_max, gfg_rng       = safe_range(df_oi.get('gamma_flip_gap_pct', pd.Series()))
    ivhv_min, ivhv_max, ivhv_rng    = safe_range(df_oi.get('iv_vs_hv', pd.Series()))

    log.info(f'Run normalisation — '
             f'vanna=[{vanna_min:.3f},{vanna_max:.3f}]  '
             f'gfc=[{gfc_min:.3f},{gfc_max:.3f}]  '
             f'gfg=[{gfg_min:.1f},{gfg_max:.1f}]  '
             f'iv_hv=[{ivhv_min:.3f},{ivhv_max:.3f}]')

    return {
        'vanna': (vanna_min, vanna_rng),
        'gfc':   (gfc_min,   gfc_rng),
        'gfg':   (gfg_min,   gfg_rng),
        'ivhv':  (ivhv_min,  ivhv_rng),
    }


def _norm(value: float, mn: float, rng: float) -> float:
    """Normalise a value to [0, 1] using min and range."""
    if rng == 0:
        return 0.5
    return float(np.clip((value - mn) / rng, 0.0, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
# CORE CT COMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def compute_ct_fields(
    oi:      dict,
    sb:      dict,
    vg:      dict,
    disc:    dict,
    norms:   dict,
) -> dict:
    """
    Compute all seven CT fields for a single signal.

    Returns dict with keys:
        ct_enabled, ct_data_quality_score, ct_missing_fields,
        ct_bifurcation_proximity, ct_divergence_set_flag,
        ct_entry_sheet, ct_hysteresis_stop_pct,
        ct_position_size_scalar, ct_vanna_charm_quadrant,
        ct_catastrophe_phase, ct_auction_stability,
        ct_reason_codes
    """
    # ── Data quality gate ────────────────────────────────────────────────────
    quality, missing = compute_data_quality(oi, vg, disc)

    base = {
        'ct_enabled':              1,
        'ct_data_quality_score':   quality,
        'ct_missing_fields':       ','.join(missing) if missing else 'NONE',
        'ct_bifurcation_proximity': None,
        'ct_divergence_set_flag':   0,
        'ct_entry_sheet':           'UNKNOWN',
        'ct_hysteresis_stop_pct':   None,
        'ct_position_size_scalar':  1.0,   # default: no adjustment
        'ct_vanna_charm_quadrant':  'UNKNOWN',
        'ct_catastrophe_phase':     'UNKNOWN',
        'ct_auction_stability':     'UNKNOWN',
        'ct_reason_codes':          '',
    }

    if quality < MIN_DATA_QUALITY_SCORE:
        base['ct_enabled']       = 0
        base['ct_reason_codes']  = f'CT_LOW_QUALITY:{quality:.2f} missing={",".join(missing)}'
        return base

    reason_codes: List[str] = []

    # ── Extract fields ────────────────────────────────────────────────────────
    vanna      = _f(oi, 'contract_vanna',    default=0.0)
    charm      = _f(oi, 'contract_charm',    default=0.0)
    gfc        = _f(oi, 'gamma_flip_conf',   default=0.5)
    gfg        = _f(oi, 'gamma_flip_gap_pct',default=25.0)
    iv_hv      = _f(oi, 'iv_vs_hv',         default=1.0)
    direction  = _s(oi, 'options_direction')
    spot       = _f(oi, 'underlying_price',  default=0.0)
    be_pct     = _f(oi, 'breakeven_pct',     default=5.0)
    phase      = _s(sb, 'phase') or _s(disc, 'phase')
    auction    = _s(vg, VG_AUCTION_STATE)
    ctrl_conf  = _f(vg, VG_CONTROL_CONF, default=0.5)
    crabel     = _f(disc, 'crabel_score', default=0.0)

    # ── F1: Vanna component (0→1, direction-aware) ───────────────────────────
    # Negative vanna on PUT = delta accelerates when vol rises = fold-break fuel
    if direction == 'PUT':
        vanna_for_prox = abs(min(vanna, 0.0))    # only negative vanna matters
    elif direction == 'CALL':
        vanna_for_prox = max(vanna, 0.0)
    else:
        vanna_for_prox = abs(vanna)

    vanna_norm = _norm(vanna_for_prox, *norms['vanna'])

    # ── F2: Wall weakness via gamma_flip_conf (low = weak wall = higher prox) ─
    # NOTE: high conf = strong wall = LOWER proximity (dealers will defend)
    gfc_inv    = 1.0 - float(np.clip(gfc, 0, 1))
    gfc_norm   = _norm(gfc_inv, 0.0, 1.0)   # already 0-1

    # ── F3: Gamma flip clearance (large gap = flip far = lower proximity) ─────
    # Inverted: large gap means fold boundary is far → lower proximity
    gfg_inv    = float(np.clip(1.0 - gfg / 100.0, 0.0, 1.0))
    gfg_norm   = _norm(gfg_inv, *norms['gfg'])

    # ── F4: Vol loading (cheap IV = expansion likely = higher proximity) ───────
    # iv_vs_hv < 1.0 → vol underpriced → expansion drives cascade
    iv_prox    = float(np.clip(1.0 - iv_hv, 0.0, 1.0))   # 0 when expensive, 1 when free
    iv_norm    = _norm(iv_prox, 0.0, 1.0)

    # ── Weighted blend ────────────────────────────────────────────────────────
    proximity = (
        W_VANNA * vanna_norm +
        W_GFC   * gfc_norm   +
        W_GAP   * gfg_norm   +
        W_IV    * iv_norm
    )
    proximity = round(float(np.clip(proximity, 0.0, 1.0)), 4)

    # ── Divergence set flag ───────────────────────────────────────────────────
    divergence = int(proximity >= DIVERGENCE_SET_THRESHOLD)
    if divergence:
        reason_codes.append('CT_DIVERGENCE_SET')

    # ── Vanna/Charm quadrant ─────────────────────────────────────────────────
    if vanna is not None and charm is not None:
        v_sign = 'NEG' if vanna < 0 else 'POS'
        c_sign = 'NEG' if charm  < 0 else 'POS'
        quadrant = f'{v_sign}_{c_sign}'
        # From data audit: NEG_NEG = highest avg R:R (1.094) in execute universe
        if quadrant == 'NEG_NEG':
            reason_codes.append('CT_OPTIMAL_QUADRANT')
    else:
        quadrant = 'UNKNOWN'

    # ── Catastrophe phase ─────────────────────────────────────────────────────
    ct_phase = CATASTROPHE_PHASE_MAP.get(str(phase).upper(), 'UNKNOWN')
    if ct_phase == 'FOLD_BOUNDARY':
        reason_codes.append('CT_FOLD_BOUNDARY')

    # ── Auction stability ─────────────────────────────────────────────────────
    if auction == 'TRANSITIONING':
        ct_auction = 'NEAR_BIFURCATION'
        reason_codes.append('CT_AUCTION_TRANSITIONING')
    elif auction == 'ALIGNED':
        ct_auction = 'STABLE'
    else:
        ct_auction = 'UNKNOWN'

    # ── Entry sheet (hysteresis) ──────────────────────────────────────────────
    # UPPER sheet = first breakout attempt (tighter stop)
    # LOWER sheet = price already tested and failed this level (wider stop)
    # Proxy: if gamma_velocity_label is MOVING_AWAY, price has retreated → LOWER
    gv_label = _s(oi, 'gamma_velocity_label')
    if gv_label == 'MOVING_AWAY':
        entry_sheet = 'LOWER'
        reason_codes.append('CT_LOWER_SHEET')
    elif gv_label in ('APPROACHING', 'IMMINENT'):
        entry_sheet = 'UPPER'
    else:
        entry_sheet = 'UPPER'   # conservative default

    # ── Hysteresis stop offset ────────────────────────────────────────────────
    # LOWER sheet entries get a wider stop to account for bifurcation gap
    # UPPER sheet entries use standard stop
    if entry_sheet == 'LOWER' and be_pct and be_pct > 0:
        hysteresis_offset = round(
            proximity * BIFURCATION_GAP_SCALAR * be_pct, 3
        )
    else:
        hysteresis_offset = 0.0

    # ── Position size scalar ──────────────────────────────────────────────────
    # Near fold boundary → outcome variance is higher → reduce size
    # This replaces the original EV haircut (which penalised convex payoffs)
    pos_scalar = round(
        float(np.clip(1.0 - proximity * VARIANCE_SCALAR, 0.5, 1.0)), 3
    )

    return {
        **base,
        'ct_bifurcation_proximity': proximity,
        'ct_divergence_set_flag':   divergence,
        'ct_entry_sheet':           entry_sheet,
        'ct_hysteresis_stop_pct':   hysteresis_offset,
        'ct_position_size_scalar':  pos_scalar,
        'ct_vanna_charm_quadrant':  quadrant,
        'ct_catastrophe_phase':     ct_phase,
        'ct_auction_stability':     ct_auction,
        'ct_reason_codes':          ','.join(reason_codes) if reason_codes else 'NONE',
        # Component breakdown for debugging
        '_ct_vanna_norm':  round(vanna_norm, 4),
        '_ct_gfc_norm':    round(gfc_norm,   4),
        '_ct_gfg_norm':    round(gfg_norm,   4),
        '_ct_iv_norm':     round(iv_norm,    4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_catastrophe_gate(
    oi_csv:    str,
    sb_csv:    str,
    vg_csv:    str,
    disc_csv:  str,
    run_id:    str  = '',
    output_dir:str  = '',
    live_mode: bool = False,   # False = shadow mode (log only, SB ignores CT)
) -> Tuple[pd.DataFrame, str]:
    """
    Main entry point.

    Parameters
    ----------
    live_mode : If False (default), CT fields are written to ct_enriched CSV
                but SuperBrain does NOT consume ct_position_size_scalar.
                Set to True only after 30 closed trades and calibration review.

    Returns
    -------
    df_ct     : DataFrame with all CT fields appended
    output_csv: path to written ct_enriched_{run_id}.csv
    """
    run_id   = run_id   or datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir  = output_dir or os.path.dirname(os.path.abspath(oi_csv))
    os.makedirs(out_dir, exist_ok=True)

    mode_str = 'LIVE' if live_mode else 'SHADOW'
    log.info(f'Run ID      : {run_id}')
    log.info(f'Mode        : {mode_str}')
    log.info(f'OI CSV      : {oi_csv}')
    log.info(f'SB CSV      : {sb_csv}')
    log.info(f'VG CSV      : {vg_csv}')
    log.info(f'Disc CSV    : {disc_csv}')
    log.info(f'Output dir  : {out_dir}')

    # ── Load inputs ───────────────────────────────────────────────────────────
    def load(path, label):
        if not path or not os.path.isfile(path):
            log.warning(f'{label} not found: {path} — CT fields for those inputs will degrade quality score')
            return pd.DataFrame()
        try:
            df = pd.read_csv(path, dtype=str)
            log.info(f'{label}: {len(df)} rows loaded')
            return df
        except Exception as e:
            log.error(f'Failed to load {label}: {e}')
            return pd.DataFrame()

    df_oi   = load(oi_csv,   'OI')
    df_sb   = load(sb_csv,   'SB')
    df_vg   = load(vg_csv,   'VG')
    df_disc = load(disc_csv, 'DISC')

    if df_oi.empty:
        log.error('OI CSV is empty or missing — cannot compute CT fields.')
        return pd.DataFrame(), ''

    # ── Build lookup dicts by ticker ──────────────────────────────────────────
    def to_lookup(df: pd.DataFrame) -> Dict[str, dict]:
        if df.empty or 'ticker' not in df.columns:
            return {}
        return {str(r['ticker']).strip().upper(): r.to_dict()
                for _, r in df.iterrows()}

    sb_lookup   = to_lookup(df_sb)
    vg_lookup   = to_lookup(df_vg)
    disc_lookup = to_lookup(df_disc)

    # ── Compute run-level normalisation from OI universe ─────────────────────
    norms = compute_run_normalisation(df_oi)

    # ── Score every OI row ────────────────────────────────────────────────────
    ct_rows: List[dict] = []
    quality_scores: List[float] = []
    enabled_count = 0

    for _, oi_row in df_oi.iterrows():
        ticker = str(oi_row.get('ticker', '')).strip().upper()
        sb_row   = sb_lookup.get(ticker, {})
        vg_row   = vg_lookup.get(ticker, {})
        disc_row = disc_lookup.get(ticker, {})

        ct = compute_ct_fields(
            oi   = oi_row.to_dict(),
            sb   = sb_row,
            vg   = vg_row,
            disc = disc_row,
            norms= norms,
        )

        # In shadow mode: mark that CT is not live in SB
        ct['ct_shadow_mode'] = 0 if live_mode else 1

        quality_scores.append(ct['ct_data_quality_score'])
        if ct['ct_enabled']:
            enabled_count += 1

        out_row = {**oi_row.to_dict(), **ct}
        ct_rows.append(out_row)

    # ── Assemble output ───────────────────────────────────────────────────────
    df_ct = pd.DataFrame(ct_rows)

    # Summary stats
    prox_col = pd.to_numeric(df_ct['ct_bifurcation_proximity'], errors='coerce').dropna()
    div_count = int((df_ct['ct_divergence_set_flag'] == 1).sum())
    avg_prox  = prox_col.mean() if len(prox_col) else 0
    avg_qual  = sum(quality_scores) / len(quality_scores) if quality_scores else 0

    grade_counts = {}
    for grade, thresh in [('HIGH(>0.6)', 0.6), ('MED(0.4-0.6)', 0.4), ('LOW(<0.4)', 0.0)]:
        if grade == 'HIGH(>0.6)':
            grade_counts[grade] = int((prox_col > 0.6).sum())
        elif grade == 'MED(0.4-0.6)':
            grade_counts[grade] = int(((prox_col >= 0.4) & (prox_col <= 0.6)).sum())
        else:
            grade_counts[grade] = int((prox_col < 0.4).sum())

    log.info(f'CT enabled       : {enabled_count}/{len(df_oi)}')
    log.info(f'Avg proximity    : {avg_prox:.3f}')
    log.info(f'Divergence set   : {div_count}')
    log.info(f'Avg data quality : {avg_qual:.3f}')
    log.info(f'Proximity bands  : {grade_counts}')

    # ── Write output ──────────────────────────────────────────────────────────
    out_path = os.path.join(out_dir, f'ct_enriched_{run_id}.csv')
    df_ct.to_csv(out_path, index=False)
    log.info(f'Written: {out_path}  ({len(df_ct)} rows)')

    # ── Write summary JSON ────────────────────────────────────────────────────
    summary = {
        'run_id':             run_id,
        'generated_at':       datetime.now().isoformat(),
        'producer':           'catastrophe_gate.py v1.0',
        'mode':               mode_str,
        'live_mode':          live_mode,
        'total_rows':         len(df_ct),
        'ct_enabled_count':   enabled_count,
        'avg_proximity':      round(avg_prox, 4),
        'divergence_set_count': div_count,
        'avg_data_quality':   round(avg_qual, 4),
        'proximity_bands':    grade_counts,
        'normalisation_params': {
            k: {'min': round(v[0], 4), 'range': round(v[1], 4)}
            for k, v in norms.items()
        },
        'constants': {
            'VARIANCE_SCALAR':          VARIANCE_SCALAR,
            'BIFURCATION_GAP_SCALAR':   BIFURCATION_GAP_SCALAR,
            'DIVERGENCE_SET_THRESHOLD': DIVERGENCE_SET_THRESHOLD,
            'MIN_DATA_QUALITY_SCORE':   MIN_DATA_QUALITY_SCORE,
            'weights': {'vanna': W_VANNA, 'gfc': W_GFC, 'gap': W_GAP, 'iv': W_IV},
        },
        'top_5_proximity': df_ct.nlargest(5, 'ct_bifurcation_proximity')[
            ['ticker', 'ct_bifurcation_proximity', 'ct_divergence_set_flag',
             'ct_vanna_charm_quadrant', 'ct_data_quality_score']
        ].to_dict(orient='records') if len(df_ct) > 0 else [],
        'shadow_mode_note': (
            'CT fields computed but ct_position_size_scalar NOT applied by SuperBrain. '
            'Activate live_mode=True after 30 closed trades and calibration review.'
            if not live_mode else 'LIVE MODE — ct_position_size_scalar active in SuperBrain'
        ),
    }

    summary_path = os.path.join(out_dir, f'ct_summary_{run_id}.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    log.info(f'Summary : {summary_path}')

    if mode_str == 'SHADOW':
        log.info('SHADOW MODE — CT fields written for observation only.')
        log.info('SuperBrain is NOT consuming ct_position_size_scalar.')
        log.info('Activate live mode after 30 closed trades via --live flag.')

    return df_ct, out_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='AVSHUNTER Catastrophe Gate — Layer 3b',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Shadow mode (default) — safe to run immediately
  python catastrophe_gate.py \\
      options_intelligence_20260305_092339.csv \\
      superbrain_enriched_20260305_092339.csv \\
      vanguard_signals.csv \\
      discovery_candidates_ultimate_20260305_092339.csv \\
      20260305_092339 runs/20260305_092339/superbrain

  # Live mode — only after 30 closed trades + calibration review
  python catastrophe_gate.py ... --live

  # Single ticker debug
  python catastrophe_gate.py ... --ticker T
        """
    )
    p.add_argument('oi_csv')
    p.add_argument('sb_csv')
    p.add_argument('vg_csv')
    p.add_argument('disc_csv')
    p.add_argument('run_id',      nargs='?', default='')
    p.add_argument('output_dir',  nargs='?', default='')
    p.add_argument('--live',      action='store_true',
                   help='Activate live mode (SuperBrain consumes CT size scalar). '
                        'Only use after 30 closed trades + calibration review.')
    p.add_argument('--ticker',    default='',
                   help='Print CT detail for a single ticker after run')
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    for path, label in [(args.oi_csv, 'OI CSV'), (args.sb_csv, 'SB CSV')]:
        if not os.path.isfile(path):
            log.error(f'{label} not found: {path}')
            sys.exit(1)

    df, out_path = run_catastrophe_gate(
        oi_csv     = args.oi_csv,
        sb_csv     = args.sb_csv,
        vg_csv     = args.vg_csv,
        disc_csv   = args.disc_csv,
        run_id     = args.run_id,
        output_dir = args.output_dir,
        live_mode  = args.live,
    )

    if df.empty:
        log.error('No output produced.')
        sys.exit(1)

    if args.ticker:
        t = args.ticker.upper()
        row = df[df['ticker'].str.upper() == t]
        if row.empty:
            log.warning(f'{t} not found.')
        else:
            r = row.iloc[0]
            print(f'\n{"─"*60}')
            print(f'  CT GATE DETAIL — {t}')
            print(f'{"─"*60}')
            print(f'  Data quality      : {r.get("ct_data_quality_score")}')
            print(f'  CT enabled        : {r.get("ct_enabled")}')
            print(f'  Missing fields    : {r.get("ct_missing_fields")}')
            print(f'  Proximity         : {r.get("ct_bifurcation_proximity")}')
            print(f'  Divergence set    : {r.get("ct_divergence_set_flag")}')
            print(f'  Catastrophe phase : {r.get("ct_catastrophe_phase")}')
            print(f'  Entry sheet       : {r.get("ct_entry_sheet")}')
            print(f'  Hysteresis stop   : {r.get("ct_hysteresis_stop_pct")}%')
            print(f'  Size scalar       : {r.get("ct_position_size_scalar")}')
            print(f'  Vanna/charm quad  : {r.get("ct_vanna_charm_quadrant")}')
            print(f'  Auction stability : {r.get("ct_auction_stability")}')
            print(f'  Reason codes      : {r.get("ct_reason_codes")}')
            print(f'  Shadow mode       : {r.get("ct_shadow_mode")}')
            print(f'  --- Component breakdown ---')
            print(f'  vanna_norm        : {r.get("_ct_vanna_norm")}')
            print(f'  gfc_norm          : {r.get("_ct_gfc_norm")}')
            print(f'  gfg_norm          : {r.get("_ct_gfg_norm")}')
            print(f'  iv_norm           : {r.get("_ct_iv_norm")}')
            print(f'{"─"*60}\n')

    print(f'\n✓ Catastrophe Gate complete → {out_path}\n')


if __name__ == '__main__':
    main()
