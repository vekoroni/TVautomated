"""
AVSHUNTER — 0DTE ELIGIBILITY SCREENER v1.0
================================================================================
Component 1 of 4 in the 0DTE Day Trade Module

PURPOSE:
    Reads the previous evening's vanguard_signals_enriched CSV and applies
    a 4-gate filter to produce a shortlist of 0DTE eligible tickers.

DESIGN PRINCIPLE:
    READ-ONLY consumer of existing pipeline outputs.
    Never modifies, writes to, or interrupts Orchestrator → Vanguard pipeline.

GATES (all must pass):
    Gate 1 — Wyckoff Phase E only (mark-down/mark-up confirmed, fastest phase)
    Gate 2 — Gamma flip proximity < 3% (price near major gamma level)
    Gate 3 — Relative volume > 1.3 at prior close (institutional participation)
    Gate 4 — Composite score >= 55 (minimum signal quality threshold)

USAGE:
    python zero_dte_screener.py
    python zero_dte_screener.py --enriched path/to/vanguard_signals_enriched.csv
    python zero_dte_screener.py --paper  (paper mode, no live orders)

OUTPUT:
    zero_dte/output/zero_dte_eligible_YYYYMMDD.csv
    zero_dte/output/zero_dte_eligible_YYYYMMDD.json

REGRESSION GUARANTEE:
    This module imports nothing from the Vanguard package.
    It reads CSV files only. No shared state, no side effects.
================================================================================
"""

import argparse
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd
import numpy as np

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

# Gate thresholds — tune during paper observation period
GATE_PHASE = ['E']                    # Gate 1: only Phase E
GATE_GAMMA_FLIP_PCT = 0.03            # Gate 2: within 3% of gamma flip
GATE_RELATIVE_VOLUME = 1.3            # Gate 3: volume > 1.3x average
GATE_COMPOSITE_SCORE = 55.0           # Gate 4: minimum composite score

# Hard position limits
MAX_ELIGIBLE_TICKERS = 5              # Never surface more than 5 candidates
MAX_LIVE_POSITIONS = 2                # Hard cap: max 2 0DTE positions per day

# 0DTE entry / exit windows (ET)
ENTRY_WINDOW_OPEN_MINUTES = 15        # 9:45 AM ET (15 min after open)
ENTRY_WINDOW_CLOSE_MINUTES = 45       # 10:15 AM ET (45 min after open)
HARD_EXIT_MINUTES_BEFORE_CLOSE = 120  # 2:00 PM ET (120 min before 4pm close)

# Scoring weights for final ranking
RANK_WEIGHTS = {
    'composite_score':      0.30,
    'rr_options':           0.25,
    'ev_adjusted':          0.20,
    'gamma_flip_proximity': 0.15,  # closer = higher score
    'volume_ratio':         0.10,
}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('0DTE_SCREENER')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | 0DTE SCREENER | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── LOADER ──────────────────────────────────────────────────────────────────

def load_enriched_signals(enriched_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load vanguard_signals_enriched CSV.
    If no path given, finds the most recent file in standard output locations.
    """
    if enriched_path:
        p = Path(enriched_path)
    else:
        # Search standard locations
        candidates = sorted(
            list(Path('.').glob('**/vanguard_signals_enriched_*.csv')) +
            list(Path('.').glob('vanguard_signals_enriched*.csv')),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not candidates:
            raise FileNotFoundError(
                "No vanguard_signals_enriched CSV found. "
                "Run the evening workflow first, or pass --enriched <path>."
            )
        p = candidates[0]

    df = pd.read_csv(p, low_memory=False)
    return df, str(p)


# ─── GATE FUNCTIONS ───────────────────────────────────────────────────────────

def gate_1_phase(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 1: Wyckoff Phase E only.
    Phase E = mark-down (distribution complete) or mark-up (accumulation complete).
    These are the fastest-moving phases — ideal for 0DTE.
    """
    if 'phase' not in df.columns:
        logger.warning("Gate 1: 'phase' column not found — skipping phase filter")
        return df

    passed = df[df['phase'].isin(GATE_PHASE)].copy()
    logger.info(f"Gate 1 (Phase E): {len(df)} → {len(passed)} signals")
    return passed


def gate_2_gamma_flip(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 2: Price within 3% of gamma flip level.
    Gamma flip proximity drives the sharpest intraday moves — MMs forced to
    flip hedging direction, accelerating price movement.

    Uses opt__gamma_flip and stock_price columns from enriched CSV.
    """
    required = ['opt__gamma_flip', 'stock_price']
    missing = [c for c in required if c not in df.columns]

    if missing:
        # Try alternative column names
        alt_map = {'opt__gamma_flip': 'gamma_flip', 'stock_price': 'entry_price'}
        for orig, alt in alt_map.items():
            if orig in missing and alt in df.columns:
                df = df.rename(columns={alt: orig})
                missing.remove(orig)

    if missing:
        logger.warning(f"Gate 2: Missing columns {missing} — applying relaxed filter")
        # Can't apply gate, pass all through with flag
        df['gamma_flip_pct'] = np.nan
        df['gamma_flip_gate'] = False
        return df

    df = df.copy()
    df['gamma_flip_pct'] = abs(df['stock_price'] - df['opt__gamma_flip']) / df['stock_price']
    passed = df[df['gamma_flip_pct'] <= GATE_GAMMA_FLIP_PCT].copy()
    logger.info(f"Gate 2 (Gamma Flip <{GATE_GAMMA_FLIP_PCT*100:.0f}%): {len(df)} → {len(passed)} signals")
    return passed


def gate_3_volume(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 3: Relative volume > 1.3 at prior close.
    Confirms institutional participation. Low-volume 0DTE setups lack
    the liquidity needed for clean entries and exits.
    """
    vol_col = None
    for col in ['volume_ratio', 'relative_volume', 'vol_ratio']:
        if col in df.columns:
            vol_col = col
            break

    if vol_col is None:
        logger.warning("Gate 3: No volume ratio column found — skipping volume filter")
        return df

    passed = df[df[vol_col] >= GATE_RELATIVE_VOLUME].copy()
    logger.info(f"Gate 3 (RelVol >{GATE_RELATIVE_VOLUME}): {len(df)} → {len(passed)} signals")
    return passed


def gate_4_composite(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 4: Composite score >= 55.
    Minimum signal quality from the existing Vanguard scoring.
    Ensures 0DTE candidates have baseline structural conviction.
    """
    if 'composite_score' not in df.columns:
        logger.warning("Gate 4: 'composite_score' column not found — skipping quality filter")
        return df

    passed = df[df['composite_score'] >= GATE_COMPOSITE_SCORE].copy()
    logger.info(f"Gate 4 (Composite ≥{GATE_COMPOSITE_SCORE}): {len(df)} → {len(passed)} signals")
    return passed


# ─── RANKING ─────────────────────────────────────────────────────────────────

def rank_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank eligible candidates using weighted scoring.
    Higher score = higher priority for 0DTE entry.
    """
    if df.empty:
        return df

    df = df.copy()
    score = pd.Series(0.0, index=df.index)

    # Composite score (normalised 0-100)
    if 'composite_score' in df.columns:
        score += (df['composite_score'] / 100) * RANK_WEIGHTS['composite_score']

    # R:R (cap at 5x for normalisation)
    if 'rr_options' in df.columns:
        rr_norm = df['rr_options'].clip(0, 5) / 5
        score += rr_norm * RANK_WEIGHTS['rr_options']

    # EV adjusted (normalised, cap at 2.0)
    if 'ev_adjusted' in df.columns:
        ev_norm = (df['ev_adjusted'].clip(-1, 2) + 1) / 3
        score += ev_norm * RANK_WEIGHTS['ev_adjusted']

    # Gamma flip proximity (closer = better; invert the distance)
    if 'gamma_flip_pct' in df.columns:
        flip_score = (GATE_GAMMA_FLIP_PCT - df['gamma_flip_pct'].clip(0, GATE_GAMMA_FLIP_PCT)) / GATE_GAMMA_FLIP_PCT
        score += flip_score * RANK_WEIGHTS['gamma_flip_proximity']

    # Volume ratio (cap at 3x)
    vol_col = next((c for c in ['volume_ratio', 'relative_volume'] if c in df.columns), None)
    if vol_col:
        vol_norm = df[vol_col].clip(0, 3) / 3
        score += vol_norm * RANK_WEIGHTS['volume_ratio']

    df['zero_dte_rank_score'] = score
    df = df.sort_values('zero_dte_rank_score', ascending=False)
    df['zero_dte_rank'] = range(1, len(df) + 1)

    return df.head(MAX_ELIGIBLE_TICKERS)


# ─── ENTRY WINDOW ANNOTATION ─────────────────────────────────────────────────

def annotate_entry_windows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add 0DTE-specific entry window guidance to each signal.
    Based on phase and intent from existing Vanguard data.
    """
    if df.empty:
        return df

    df = df.copy()

    # Entry method based on precor_intent
    def get_entry_method(row):
        intent = str(row.get('precor_intent', '')).upper()
        phase = str(row.get('phase', '')).upper()

        if phase == 'E' and 'BUY' in intent:
            return 'SPRING_CONFIRM'   # Wait for 5m close above breakdown
        elif phase == 'E' and 'SELL' in intent:
            return 'UTAD_CONFIRM'     # Wait for 5m close below prior high
        else:
            return 'OPEN_PLUS_15'     # Enter 15 min after open on confirmation

    # Hard exit time
    df['zero_dte_entry_method'] = df.apply(get_entry_method, axis=1)
    df['zero_dte_entry_window_et'] = '09:45–10:15 ET'
    df['zero_dte_hard_exit_et'] = '14:00 ET'
    df['zero_dte_max_hold_hours'] = 4.25   # 9:45 → 2:00
    df['zero_dte_premium_stop_pct'] = 0.50 # Exit if premium loses 50% of value

    return df


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

def save_outputs(df: pd.DataFrame, output_dir: Path, run_date: str) -> Dict:
    """
    Save CSV and JSON outputs to zero_dte/output/.
    Returns dict of output paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f'zero_dte_eligible_{run_date}.csv'
    json_path = output_dir / f'zero_dte_eligible_{run_date}.json'

    # Select key columns for output
    out_cols = [c for c in [
        'ticker', 'zero_dte_rank', 'zero_dte_rank_score',
        'phase', 'precor_intent', 'composite_score',
        'stock_price', 'opt__gamma_flip', 'gamma_flip_pct',
        'options_direction', 'options_strategy',
        'contract_strike', 'contract_expiry', 'contract_dte',
        'contract_premium', 'contract_delta',
        'rr_options', 'ev_adjusted', 'ivp_label',
        'theta_drag_pct', 'target_in_play',
        'zero_dte_entry_method', 'zero_dte_entry_window_et',
        'zero_dte_hard_exit_et', 'zero_dte_max_hold_hours',
        'zero_dte_premium_stop_pct',
        'options_verdict', 'options_score',
    ] if c in df.columns]

    df[out_cols].to_csv(csv_path, index=False)

    # JSON summary
    summary = {
        'generated_at': datetime.utcnow().isoformat(),
        'run_date': run_date,
        'eligible_count': len(df),
        'max_live_positions': MAX_LIVE_POSITIONS,
        'entry_window_et': '09:45–10:15',
        'hard_exit_et': '14:00',
        'paper_mode': True,   # Always paper during build period
        'actuarial_status': 'DISCOVERY — n<50 across all hashes',
        'candidates': []
    }

    for _, row in df.iterrows():
        candidate = {
            'rank':           int(row.get('zero_dte_rank', 0)),
            'ticker':         str(row.get('ticker', '')),
            'phase':          str(row.get('phase', '')),
            'intent':         str(row.get('precor_intent', '')),
            'direction':      str(row.get('options_direction', '')),
            'strike':         float(row.get('contract_strike', 0)),
            'rank_score':     round(float(row.get('zero_dte_rank_score', 0)), 4),
            'composite':      float(row.get('composite_score', 0)),
            'rr':             float(row.get('rr_options', 0)),
            'ev_adj':         float(row.get('ev_adjusted', 0)),
            'gamma_flip_pct': round(float(row.get('gamma_flip_pct', 0)), 4),
            'entry_method':   str(row.get('zero_dte_entry_method', '')),
            'hard_exit':      str(row.get('zero_dte_hard_exit_et', '14:00 ET')),
        }
        summary['candidates'].append(candidate)

    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)

    return {'csv': str(csv_path), 'json': str(json_path)}


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_screener(enriched_path: Optional[str] = None,
                 verbose: bool = False,
                 paper: bool = True) -> Dict:
    """
    Main screener entry point.
    Returns dict with eligible candidates and output paths.
    """
    logger = setup_logger(verbose)
    run_date = date.today().strftime('%Y%m%d')
    output_dir = Path('zero_dte/output')

    logger.info("=" * 60)
    logger.info("AVSHUNTER — 0DTE ELIGIBILITY SCREENER v1.0")
    logger.info(f"Mode: {'PAPER' if paper else 'LIVE'} | Date: {run_date}")
    logger.info("=" * 60)

    # Load
    try:
        df, source_path = load_enriched_signals(enriched_path)
        logger.info(f"Loaded {len(df)} signals from: {source_path}")
    except FileNotFoundError as e:
        logger.error(str(e))
        return {'eligible': [], 'error': str(e)}

    total_input = len(df)

    # Apply gates sequentially
    df = gate_1_phase(df, logger)
    if df.empty:
        logger.info("No signals passed Gate 1 (Phase E). No 0DTE candidates today.")
        result = {'eligible': [], 'gate_failed': 'GATE_1_PHASE', 'input_count': total_input}
        _save_empty_result(result, output_dir, run_date)
        return result

    df = gate_2_gamma_flip(df, logger)
    df = gate_3_volume(df, logger)
    df = gate_4_composite(df, logger)

    if df.empty:
        logger.info("No signals passed all gates. No 0DTE candidates today.")
        result = {'eligible': [], 'gate_failed': 'GATES_2_3_4', 'input_count': total_input}
        _save_empty_result(result, output_dir, run_date)
        return result

    # Rank and annotate
    df = rank_candidates(df)
    df = annotate_entry_windows(df)

    logger.info("=" * 60)
    logger.info(f"0DTE ELIGIBLE: {len(df)} candidates (max {MAX_ELIGIBLE_TICKERS})")
    logger.info(f"LIVE POSITIONS ALLOWED: {MAX_LIVE_POSITIONS} (paper mode: {paper})")
    logger.info("=" * 60)

    for _, row in df.iterrows():
        logger.info(
            f"  #{int(row.get('zero_dte_rank',0))} {row.get('ticker','?'):6s} "
            f"Ph {row.get('phase','?')} | "
            f"{row.get('options_direction','?'):4s} "
            f"${row.get('contract_strike',0):.2f} | "
            f"R:R {row.get('rr_options',0):.2f}x | "
            f"Entry: {row.get('zero_dte_entry_method','?')}"
        )

    logger.info(f"\nEntry window: 09:45–10:15 ET  |  Hard exit: 14:00 ET")
    logger.info(f"Stop: 50% of premium paid  |  Max positions: {MAX_LIVE_POSITIONS}")

    # Save outputs
    paths = save_outputs(df, output_dir, run_date)
    logger.info(f"\nOutputs saved:")
    logger.info(f"  CSV:  {paths['csv']}")
    logger.info(f"  JSON: {paths['json']}")

    return {
        'eligible': df.to_dict('records'),
        'count': len(df),
        'paths': paths,
        'paper_mode': paper
    }


def _save_empty_result(result: Dict, output_dir: Path, run_date: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f'zero_dte_eligible_{run_date}.json'
    result['generated_at'] = datetime.utcnow().isoformat()
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2)


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AVSHUNTER 0DTE Eligibility Screener'
    )
    parser.add_argument(
        '--enriched',
        type=str,
        default=None,
        help='Path to vanguard_signals_enriched CSV (auto-detects if not given)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose logging'
    )
    parser.add_argument(
        '--paper',
        action='store_true',
        default=True,
        help='Paper mode (default: True during build period)'
    )
    args = parser.parse_args()

    run_screener(
        enriched_path=args.enriched,
        verbose=args.verbose,
        paper=args.paper
    )
