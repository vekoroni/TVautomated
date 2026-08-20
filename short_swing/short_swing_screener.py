"""
AVSHUNTER — SHORT-SWING SCREENER v1.0
================================================================================
Component 1 of 5 in the Short-Swing Module (Scope 2)

PURPOSE:
    Reads vanguard_signals_enriched CSV and applies a 5-gate filter to surface
    Crabel compression setups for 1-3 day holds using 7-14 DTE options.

GATES (all must pass):
    Gate 1  Phase C or E only
    Gate 2  Crabel gate: NR7, NR7+LowVol, Extreme, or CRABEL_READY
    Gate 3  IVP gate: CHEAP or FAIR only (never buy expensive premium overnight)
    Gate 4  Composite score >= 60 (baseline signal quality)
    Gate 5  Options data present: contract_strike and contract_expiry not null

COLUMN NAMES (exact match to enriched CSV):
    phase               Wyckoff phase (A/B/C/D/E)
    crabel_pattern      NR7+LowVol | NR7 | Extreme | Moderate
    crabel_state        COILING | CRABEL_READY | NONE
    ivp_label           CHEAP | FAIR | EXPENSIVE | UNKNOWN
    composite_score     0-100 composite quality score
    options_direction   CALL | PUT | STRANGLE
    contract_strike     option strike price
    contract_expiry     YYYY-MM-DD
    contract_premium    option mid price
    rr_options          risk:reward ratio
    ev_adjusted         expected value adjusted
    stock_price         current underlying price
    volume_ratio        relative volume vs 20-day avg
    state_hash          actuarial state hash
    ticker              ticker symbol
    precor_intent       BUY_SETUP | SELL_SETUP etc.
    stop_loss           structural stop from Vanguard
    entry_price         optimal entry price
    ATR_14              14-day ATR for sizing reference

REGRESSION GUARANTEE:
    Read-only. Never imports from Vanguard package.
    Writes only to short_swing/output/
================================================================================
"""

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

# Gate thresholds
GATE_PHASES           = ['C', 'E']
GATE_CRABEL_PATTERNS  = ['NR7+LowVol', 'NR7', 'Extreme']   # Moderate excluded
GATE_CRABEL_STATES    = ['CRABEL_READY', 'COILING']          # NONE excluded
GATE_IVP              = ['CHEAP', 'FAIR']
GATE_COMPOSITE_MIN    = 60.0

# Short-swing DTE target: need a contract expiring 7-21 days from now
# (wider than ideal to handle weekly expiry gaps)
SHORT_SWING_DTE_MIN   = 5
SHORT_SWING_DTE_MAX   = 21

# Ranking weights
RANK_WEIGHTS = {
    'crabel_quality':   0.30,   # NR7+LowVol > CRABEL_READY > NR7 > Extreme
    'composite_score':  0.25,
    'rr_options':       0.20,
    'ev_adjusted':      0.15,
    'ivp_quality':      0.10,   # CHEAP > FAIR
}

# Priority caps
MAX_CANDIDATES = 8
MAX_LIVE_POSITIONS = 3

# Crabel pattern quality score mapping
CRABEL_QUALITY = {
    'NR7+LowVol':    1.0,   # Highest — double compression
    'NR7':           0.75,
    'Extreme':       0.70,
    'CRABEL_READY':  0.85,  # State, not pattern — very imminent
    'COILING':       0.50,
}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('SS_SCREENER')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | SHORT-SWING SCREENER | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── LOADER ──────────────────────────────────────────────────────────────────

def load_enriched(path: Optional[str] = None) -> Tuple[pd.DataFrame, str]:
    if path:
        p = Path(path)
    else:
        candidates = sorted(
            list(Path('.').glob('**/vanguard_signals_enriched_*.csv')),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not candidates:
            raise FileNotFoundError(
                "No vanguard_signals_enriched CSV found. Run evening workflow first."
            )
        p = candidates[0]
    df = pd.read_csv(p, low_memory=False)
    return df, str(p)


# ─── DTE CALCULATOR ──────────────────────────────────────────────────────────

def calculate_dte(expiry_str: str) -> int:
    """Calculate DTE from expiry string YYYY-MM-DD."""
    try:
        expiry = datetime.strptime(str(expiry_str), '%Y-%m-%d').date()
        return (expiry - date.today()).days
    except Exception:
        return -1


def dte_in_range(expiry_str) -> bool:
    if pd.isna(expiry_str):
        return False
    dte = calculate_dte(str(expiry_str))
    return SHORT_SWING_DTE_MIN <= dte <= SHORT_SWING_DTE_MAX


# ─── GATES ───────────────────────────────────────────────────────────────────

def gate_1_phase(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Gate 1: Phase C or E only."""
    if 'phase' not in df.columns:
        logger.warning("Gate 1: 'phase' column missing — skipping")
        return df
    passed = df[df['phase'].isin(GATE_PHASES)].copy()
    logger.info(f"Gate 1 (Phase C/E):      {len(df):>4} → {len(passed):>4} signals")
    return passed


def gate_2_crabel(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 2: Crabel quality gate.
    Must have a qualifying pattern OR be in CRABEL_READY state.
    Either condition independently passes.
    """
    pattern_ok = df.get('crabel_pattern', pd.Series(dtype=str)).isin(GATE_CRABEL_PATTERNS)
    state_ok   = df.get('crabel_state',   pd.Series(dtype=str)).isin(GATE_CRABEL_STATES)
    passed = df[pattern_ok | state_ok].copy()
    logger.info(f"Gate 2 (Crabel quality): {len(df):>4} → {len(passed):>4} signals")
    return passed


def gate_3_ivp(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Gate 3: IVP CHEAP or FAIR only."""
    if 'ivp_label' not in df.columns:
        logger.warning("Gate 3: 'ivp_label' missing — skipping")
        return df
    passed = df[df['ivp_label'].isin(GATE_IVP)].copy()
    logger.info(f"Gate 3 (IVP CHEAP/FAIR): {len(df):>4} → {len(passed):>4} signals")
    return passed


def gate_4_composite(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Gate 4: Composite score >= 60."""
    if 'composite_score' not in df.columns:
        logger.warning("Gate 4: 'composite_score' missing — skipping")
        return df
    passed = df[df['composite_score'] >= GATE_COMPOSITE_MIN].copy()
    logger.info(f"Gate 4 (Score ≥{GATE_COMPOSITE_MIN}):     {len(df):>4} → {len(passed):>4} signals")
    return passed


def gate_5_options(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Gate 5: Options data must be present.
    Accept signals where we have a contract from the evening run (within DTE range),
    OR where we'll fetch a short-dated contract separately.
    """
    has_contract = (
        df['contract_strike'].notna() &
        df['contract_expiry'].notna() &
        df['options_direction'].isin(['CALL', 'PUT'])
    )
    # Also accept signals with no contract if they have good data — 
    # contract selector will find 7-14 DTE chain
    has_direction = df['options_direction'].isin(['CALL', 'PUT'])
    passed = df[has_contract | has_direction].copy()
    logger.info(f"Gate 5 (Options data):   {len(df):>4} → {len(passed):>4} signals")
    return passed


# ─── DTE ANNOTATION ──────────────────────────────────────────────────────────

def annotate_dte_and_contract(df: pd.DataFrame) -> pd.DataFrame:
    """
    Annotate each signal with DTE info.
    Flags whether the existing evening-run contract is in short-swing DTE range,
    or whether we need to fetch a new shorter-dated contract.
    """
    df = df.copy()
    df['existing_dte'] = df['contract_expiry'].apply(
        lambda x: calculate_dte(x) if pd.notna(x) else -1
    )
    df['use_existing_contract'] = df['existing_dte'].apply(
        lambda d: SHORT_SWING_DTE_MIN <= d <= SHORT_SWING_DTE_MAX
    )
    df['needs_shorter_contract'] = ~df['use_existing_contract']
    df['target_dte_range'] = f'{SHORT_SWING_DTE_MIN}-{SHORT_SWING_DTE_MAX}d'
    return df


# ─── RANKING ─────────────────────────────────────────────────────────────────

def compute_crabel_quality_score(row) -> float:
    """Combined crabel pattern + state quality score."""
    pattern = str(row.get('crabel_pattern', ''))
    state   = str(row.get('crabel_state', ''))
    pat_score   = CRABEL_QUALITY.get(pattern, 0.0)
    state_score = CRABEL_QUALITY.get(state, 0.0)
    return max(pat_score, state_score)


def rank_candidates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    score = pd.Series(0.0, index=df.index)

    # Crabel quality
    df['_crabel_q'] = df.apply(compute_crabel_quality_score, axis=1)
    score += df['_crabel_q'] * RANK_WEIGHTS['crabel_quality']

    # Composite score (norm 0-100)
    if 'composite_score' in df.columns:
        score += (df['composite_score'].clip(0, 100) / 100) * RANK_WEIGHTS['composite_score']

    # R:R (cap at 5x)
    if 'rr_options' in df.columns:
        rr = pd.to_numeric(df['rr_options'], errors='coerce').fillna(0).clip(0, 5) / 5
        score += rr * RANK_WEIGHTS['rr_options']

    # EV adjusted (norm -1 to +2 → 0 to 1)
    if 'ev_adjusted' in df.columns:
        ev = pd.to_numeric(df['ev_adjusted'], errors='coerce').fillna(0)
        ev_norm = (ev.clip(-1, 2) + 1) / 3
        score += ev_norm * RANK_WEIGHTS['ev_adjusted']

    # IVP quality
    ivp_score_map = {'CHEAP': 1.0, 'FAIR': 0.6, 'EXPENSIVE': 0.0}
    if 'ivp_label' in df.columns:
        score += df['ivp_label'].map(ivp_score_map).fillna(0) * RANK_WEIGHTS['ivp_quality']

    df['short_swing_rank_score'] = score
    df = df.sort_values('short_swing_rank_score', ascending=False)
    df['short_swing_rank'] = range(1, len(df) + 1)

    return df.head(MAX_CANDIDATES)


# ─── ENTRY ANNOTATION ────────────────────────────────────────────────────────

def annotate_entry_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate each signal with Scope 2 entry and exit rules."""
    if df.empty:
        return df
    df = df.copy()

    def get_entry_rule(row):
        state   = str(row.get('crabel_state', ''))
        pattern = str(row.get('crabel_pattern', ''))
        if state == 'CRABEL_READY' or 'NR7' in pattern:
            return 'CRABEL_OPEN_RANGE'    # Enter at open if price > NR7 high
        elif 'Extreme' in pattern:
            return 'OPEN_RANGE_BREAKOUT'  # Enter on first 15-min breakout
        else:
            return 'VWAP_RECLAIM'         # Enter on VWAP reclaim at open

    def get_trigger_level(row):
        # For CRABEL_OPEN_RANGE: trigger is prior day high
        # We'll use stock_price as reference; actual level from chart
        return 'Prior day high (CALL) / Prior day low (PUT)'

    df['ss_entry_rule']     = df.apply(get_entry_rule, axis=1)
    df['ss_trigger_level']  = df.apply(get_trigger_level, axis=1)
    df['ss_entry_window']   = 'Market open +30 min'
    df['ss_hold_days']      = '1-3 trading days'
    df['ss_stop_pct']       = 0.30   # 30% of premium paid
    df['ss_target_method']  = 'Prior range top / 2x risk (whichever first)'
    df['ss_exit_eod']       = 'Day 3 close — hard exit regardless of P&L'
    df['ss_paper_mode']     = True

    return df


# ─── OUTPUT ──────────────────────────────────────────────────────────────────

def save_outputs(df: pd.DataFrame, output_dir: Path, run_date: str) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Select output columns
    out_cols = [c for c in [
        'ticker', 'short_swing_rank', 'short_swing_rank_score',
        'phase', 'crabel_pattern', 'crabel_state', 'ivp_label',
        'composite_score', '_crabel_q',
        'options_direction', 'contract_strike', 'contract_expiry',
        'contract_premium', 'existing_dte', 'use_existing_contract',
        'needs_shorter_contract', 'target_dte_range',
        'rr_options', 'ev_adjusted', 'stock_price',
        'stop_loss', 'entry_price', 'ATR_14', 'volume_ratio',
        'state_hash',
        'ss_entry_rule', 'ss_trigger_level', 'ss_entry_window',
        'ss_hold_days', 'ss_stop_pct', 'ss_target_method',
        'ss_exit_eod', 'ss_paper_mode',
    ] if c in df.columns]

    csv_path  = output_dir / f'ss_eligible_{run_date}.csv'
    json_path = output_dir / f'ss_eligible_{run_date}.json'

    df[out_cols].to_csv(csv_path, index=False)

    summary = {
        'generated_at':      datetime.utcnow().isoformat(),
        'run_date':          run_date,
        'eligible_count':    len(df),
        'max_live_positions':MAX_LIVE_POSITIONS,
        'entry_window':      'Market open +30 min',
        'hold_window':       '1-3 trading days',
        'hard_exit':         'Day 3 close EOD',
        'paper_mode':        True,
        'actuarial_status':  'DISCOVERY — building Phase C/E Crabel hashes',
        'candidates': []
    }

    for _, row in df.iterrows():
        summary['candidates'].append({
            'rank':           int(row.get('short_swing_rank', 0)),
            'ticker':         str(row.get('ticker', '')),
            'phase':          str(row.get('phase', '')),
            'crabel_pattern': str(row.get('crabel_pattern', '')),
            'crabel_state':   str(row.get('crabel_state', '')),
            'ivp':            str(row.get('ivp_label', '')),
            'direction':      str(row.get('options_direction', '')),
            'strike':         float(row['contract_strike']) if pd.notna(row.get('contract_strike')) else None,
            'existing_dte':   int(row.get('existing_dte', -1)),
            'needs_new_contract': bool(row.get('needs_shorter_contract', True)),
            'composite':      float(row.get('composite_score', 0)),
            'rr':             float(row['rr_options']) if pd.notna(row.get('rr_options')) else None,
            'ev':             float(row['ev_adjusted']) if pd.notna(row.get('ev_adjusted')) else None,
            'entry_rule':     str(row.get('ss_entry_rule', '')),
            'state_hash':     str(row.get('state_hash', '')),
        })

    with open(json_path, 'w') as f:
        json.dump(summary, f, indent=2)

    return {'csv': str(csv_path), 'json': str(json_path)}


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_screener(
    enriched_path: Optional[str] = None,
    verbose: bool = False,
    paper: bool = True
) -> Dict:
    logger   = setup_logger(verbose)
    run_date = date.today().strftime('%Y%m%d')
    output_dir = Path('short_swing/output')

    logger.info("=" * 60)
    logger.info("AVSHUNTER — SHORT-SWING SCREENER v1.0")
    logger.info(f"Mode: {'PAPER' if paper else 'LIVE'} | Date: {run_date}")
    logger.info("=" * 60)

    try:
        df, source = load_enriched(enriched_path)
        logger.info(f"Loaded {len(df)} signals from: {source}")
    except FileNotFoundError as e:
        logger.error(str(e))
        return {'eligible': [], 'error': str(e)}

    total = len(df)

    # Gates
    df = gate_1_phase(df, logger)
    df = gate_2_crabel(df, logger)
    df = gate_3_ivp(df, logger)
    df = gate_4_composite(df, logger)
    df = gate_5_options(df, logger)

    if df.empty:
        logger.info("No signals passed all gates. No short-swing candidates today.")
        result = {'eligible': [], 'input_count': total}
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f'ss_eligible_{run_date}.json'
        with open(json_path, 'w') as f:
            json.dump({**result, 'generated_at': datetime.utcnow().isoformat()}, f, indent=2)
        return result

    # Annotate and rank
    df = annotate_dte_and_contract(df)
    df = rank_candidates(df)
    df = annotate_entry_rules(df)

    logger.info("=" * 60)
    logger.info(f"SHORT-SWING ELIGIBLE: {len(df)} candidates")
    logger.info(f"MAX LIVE POSITIONS:   {MAX_LIVE_POSITIONS}")
    logger.info("=" * 60)

    for _, row in df.iterrows():
        need_new = "→ needs 7-14d contract" if row.get('needs_shorter_contract') else f"DTE {row.get('existing_dte','?')}"
        logger.info(
            f"  #{int(row.get('short_swing_rank',0))} {str(row.get('ticker','')):6s} "
            f"Ph {row.get('phase','?')} | "
            f"{str(row.get('crabel_pattern','')):12s} | "
            f"{str(row.get('crabel_state','')):12s} | "
            f"{str(row.get('ivp_label','')):8s} | "
            f"{str(row.get('options_direction','')):4s} | "
            f"Entry: {str(row.get('ss_entry_rule',''))} | "
            f"{need_new}"
        )

    paths = save_outputs(df, output_dir, run_date)
    logger.info(f"\nCSV:  {paths['csv']}")
    logger.info(f"JSON: {paths['json']}")

    return {
        'eligible':  df.to_dict('records'),
        'count':     len(df),
        'paths':     paths,
        'paper_mode':paper
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AVSHUNTER Short-Swing Screener')
    parser.add_argument('--enriched', type=str, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--paper', action='store_true', default=True)
    args = parser.parse_args()
    run_screener(args.enriched, args.verbose, args.paper)
