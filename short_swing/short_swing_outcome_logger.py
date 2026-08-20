"""
AVSHUNTER — SHORT-SWING OUTCOME LOGGER v1.0
================================================================================
Component 4 of 5 in the Short-Swing Module (Scope 2)

PURPOSE:
    Aggregates all paper trade outcomes from the EOD monitor,
    computes performance statistics by Crabel pattern and phase,
    and formats observations ready to feed the main actuarial database
    once Phase C/E Crabel hashes cross n≥50.

ACTUARIAL INTEGRATION:
    Each outcome is tagged with state_hash from the parent Vanguard signal.
    Short-swing observations build a SEPARATE hash accumulation layer to
    the swing (Scope 1) observations — same hash IDs, different trade_type.
    This means the actuarial DB gains both swing AND short-swing base rates
    for the same market states, enabling hold-period optimisation.

KEY STATS TRACKED:
    - Win rate by Crabel pattern (NR7+LowVol vs NR7 vs Extreme vs CRABEL_READY)
    - Win rate by phase (C vs E)
    - Avg P&L by hold day (Day 1 vs Day 2 vs Day 3 exits)
    - Exit reason distribution (target / stop / hard_exit / adverse_close)
    - Profit factor and Sharpe approximation

OUTPUTS:
    short_swing/output/ss_daily_summary_YYYYMMDD.json
    short_swing/output/ss_cumulative_outcomes.csv
    short_swing/output/ss_actuarial_feed_YYYYMMDD.json
    short_swing/output/ss_intel_panel.json
================================================================================
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

ACTUARIAL_THRESHOLD = 50
OUTPUT_DIR = Path('short_swing/output')
CUMULATIVE_PATH = OUTPUT_DIR / 'ss_cumulative_outcomes.csv'


def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('SS_OUTCOMES')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | SS_OUTCOMES | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── LOADERS ─────────────────────────────────────────────────────────────────

def load_todays_outcomes(run_date: Optional[str] = None) -> pd.DataFrame:
    if not run_date:
        run_date = date.today().strftime('%Y%m%d')
    path = OUTPUT_DIR / f'ss_outcomes_{run_date}.csv'
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_cumulative() -> pd.DataFrame:
    if not CUMULATIVE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(CUMULATIVE_PATH)


def load_contracts_today() -> List[Dict]:
    run_date = date.today().strftime('%Y%m%d')
    path = OUTPUT_DIR / f'ss_contracts_{run_date}.json'
    if not path.exists():
        candidates = sorted(OUTPUT_DIR.glob('ss_contracts_*.json'),
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not candidates:
            return []
        path = candidates[0]
    with open(path) as f:
        return json.load(f)


# ─── STATISTICS ───────────────────────────────────────────────────────────────

def compute_daily_stats(outcomes: pd.DataFrame) -> Dict:
    if outcomes.empty:
        return {'date': date.today().isoformat(), 'trades': 0, 'note': 'No trades today'}

    closed = outcomes[outcomes['status'] == 'CLOSED'].copy()
    if closed.empty:
        return {'date': date.today().isoformat(), 'trades': 0, 'note': 'No closed trades'}

    wins   = closed[closed['pnl_dollars'] > 0]
    losses = closed[closed['pnl_dollars'] <= 0]
    gross_profit = wins['pnl_dollars'].sum()
    gross_loss   = abs(losses['pnl_dollars'].sum())

    return {
        'date':         date.today().isoformat(),
        'trades':       len(closed),
        'wins':         len(wins),
        'losses':       len(losses),
        'win_rate':     round(len(wins) / len(closed), 4),
        'total_pnl':    round(closed['pnl_dollars'].sum(), 2),
        'avg_pnl':      round(closed['pnl_dollars'].mean(), 2),
        'avg_win':      round(wins['pnl_dollars'].mean(), 2) if not wins.empty else None,
        'avg_loss':     round(losses['pnl_dollars'].mean(), 2) if not losses.empty else None,
        'profit_factor':round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        'exit_reasons': closed['exit_reason'].value_counts().to_dict() if 'exit_reason' in closed else {},
        'paper_mode':   True,
    }


def compute_cumulative_stats(cumulative: pd.DataFrame) -> Dict:
    if cumulative.empty:
        return {'total_trades': 0, 'trades_to_n50': ACTUARIAL_THRESHOLD}

    closed = cumulative[cumulative['status'] == 'CLOSED'].copy()
    if closed.empty:
        return {'total_trades': 0, 'trades_to_n50': ACTUARIAL_THRESHOLD}

    wins   = closed[closed['pnl_dollars'] > 0]
    losses = closed[closed['pnl_dollars'] <= 0]
    gross_profit = wins['pnl_dollars'].sum()
    gross_loss   = abs(losses['pnl_dollars'].sum())

    # By Crabel pattern
    by_pattern = {}
    if 'crabel_pattern' in closed.columns:
        for pattern, group in closed.groupby('crabel_pattern'):
            w = group[group['pnl_dollars'] > 0]
            by_pattern[str(pattern)] = {
                'count':    len(group),
                'win_rate': round(len(w) / len(group), 3),
                'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
            }

    # By phase
    by_phase = {}
    if 'phase' in closed.columns:
        for ph, group in closed.groupby('phase'):
            w = group[group['pnl_dollars'] > 0]
            by_phase[str(ph)] = {
                'count':    len(group),
                'win_rate': round(len(w) / len(group), 3),
                'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
            }

    # By hold day (day 1, 2, 3 exits)
    by_hold_day = {}
    if 'days_in_trade' in closed.columns:
        for day, group in closed.groupby('days_in_trade'):
            w = group[group['pnl_dollars'] > 0]
            by_hold_day[f'day_{day}'] = {
                'count':    len(group),
                'win_rate': round(len(w) / len(group), 3),
                'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
            }

    # By exit reason
    by_exit = {}
    if 'exit_reason' in closed.columns:
        for reason, group in closed.groupby('exit_reason'):
            w = group[group['pnl_dollars'] > 0]
            by_exit[str(reason)] = {
                'count':    len(group),
                'win_rate': round(len(w) / len(group), 3),
                'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
            }

    total = len(closed)
    return {
        'total_trades':       total,
        'total_wins':         len(wins),
        'total_losses':       len(losses),
        'overall_win_rate':   round(len(wins) / total, 4),
        'total_pnl':          round(closed['pnl_dollars'].sum(), 2),
        'avg_pnl_per_trade':  round(closed['pnl_dollars'].mean(), 2),
        'profit_factor':      round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        'sharpe_approx':      round(closed['pnl_dollars'].mean() / (closed['pnl_dollars'].std() or 1), 3),
        'by_crabel_pattern':  by_pattern,
        'by_phase':           by_phase,
        'by_hold_day':        by_hold_day,
        'by_exit_reason':     by_exit,
        'trades_to_n50':      max(0, ACTUARIAL_THRESHOLD - total),
        'actuarial_ready':    total >= ACTUARIAL_THRESHOLD,
        'paper_mode':         True,
    }


# ─── ACTUARIAL FORMATTER ──────────────────────────────────────────────────────

def format_actuarial_observations(outcomes: pd.DataFrame) -> List[Dict]:
    """
    Format closed outcomes as state hash observations for the main actuarial DB.
    Same schema as Scope 1 swing observations — adds trade_type='SHORT_SWING'
    so the DB can track hold-period performance separately.
    """
    if outcomes.empty:
        return []

    closed = outcomes[outcomes['status'] == 'CLOSED'].copy()
    obs = []
    for _, row in closed.iterrows():
        obs.append({
            'state_hash':    str(row.get('state_hash', 'UNKNOWN')),
            'ticker':        str(row.get('ticker', '')),
            'trade_type':    'SHORT_SWING',
            'scope':         2,
            'crabel_pattern':str(row.get('crabel_pattern', '')),
            'phase':         str(row.get('phase', '')),
            'direction':     str(row.get('direction', '')),
            'dte_entry':     int(row.get('dte', 0)) if 'dte' in row else 0,
            'days_held':     int(row.get('days_in_trade', 0)),
            'entry_premium': float(row.get('entry_premium', 0)),
            'exit_premium':  float(row.get('exit_premium', 0)),
            'pnl_dollars':   float(row.get('pnl_dollars', 0)),
            'pnl_pct':       float(row.get('pnl_pct', 0)),
            'exit_reason':   str(row.get('exit_reason', '')),
            'win':           1 if float(row.get('pnl_dollars', 0)) > 0 else 0,
            'paper':         True,
            'recorded_at':   datetime.utcnow().isoformat(),
        })
    return obs


# ─── INTEL PANEL ─────────────────────────────────────────────────────────────

def build_intel_panel(daily: Dict, cumulative: Dict,
                       today_outcomes: pd.DataFrame,
                       contracts_today: List[Dict]) -> Dict:
    return {
        'generated_at':     datetime.utcnow().isoformat(),
        'date':             date.today().isoformat(),
        'scope':            2,
        'name':             'Short-Swing',
        'paper_mode':       True,
        'hold_window':      '1-3 trading days',
        'entry_rule':       'Crabel open-range breakout at market open',
        'actuarial_status': 'DISCOVERY — Building Phase C/E Crabel observations',
        'trades_to_n50':    cumulative.get('trades_to_n50', ACTUARIAL_THRESHOLD),
        'actuarial_ready':  cumulative.get('actuarial_ready', False),
        'today': {
            'contracts_selected': len(contracts_today),
            'trades_taken':       daily.get('trades', 0),
            'pnl':                daily.get('total_pnl', 0),
            'win_rate':           daily.get('win_rate'),
        },
        'cumulative': {
            'total_trades':  cumulative.get('total_trades', 0),
            'win_rate':      cumulative.get('overall_win_rate'),
            'total_pnl':     cumulative.get('total_pnl', 0),
            'profit_factor': cumulative.get('profit_factor'),
            'by_pattern':    cumulative.get('by_crabel_pattern', {}),
            'by_phase':      cumulative.get('by_phase', {}),
            'by_hold_day':   cumulative.get('by_hold_day', {}),
        },
        'candidates': [
            {
                'ticker':       c.get('ticker', ''),
                'direction':    c.get('direction', ''),
                'phase':        c.get('phase', ''),
                'crabel':       c.get('crabel_pattern', ''),
                'strike':       c.get('strike', 0),
                'dte':          c.get('dte', 0),
                'premium':      c.get('mid', 0),
                'entry_rule':   c.get('entry_rule', ''),
                'hard_exit':    c.get('hard_exit_date', ''),
                'ivp':          c.get('ivp', ''),
            }
            for c in contracts_today
        ],
        'closed_today': (
            today_outcomes[today_outcomes['status'] == 'CLOSED'][[
                'ticker','direction','crabel_pattern','entry_premium',
                'exit_premium','pnl_dollars','pnl_pct','exit_reason','days_in_trade'
            ]].to_dict('records')
            if not today_outcomes.empty and 'status' in today_outcomes.columns else []
        ),
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_outcome_logger(verbose: bool = False, feed_actuarial: bool = False) -> Dict:
    logger   = setup_logger(verbose)
    run_date = date.today().strftime('%Y%m%d')
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("AVSHUNTER — SHORT-SWING OUTCOME LOGGER v1.0")
    logger.info(f"Date: {run_date}")
    logger.info("=" * 60)

    today_outcomes  = load_todays_outcomes(run_date)
    cumulative      = load_cumulative()
    contracts_today = load_contracts_today()

    logger.info(f"Today's outcomes: {len(today_outcomes)} trades")
    logger.info(f"Cumulative outcomes: {len(cumulative)} all-time")

    daily_stats  = compute_daily_stats(today_outcomes)
    cumul_stats  = compute_cumulative_stats(cumulative)

    if daily_stats.get('trades', 0) > 0:
        logger.info(f"\nToday: {daily_stats['trades']} trades | "
                   f"Win rate: {daily_stats.get('win_rate',0)*100:.0f}% | "
                   f"P&L: ${daily_stats.get('total_pnl',0):+.2f}")

    logger.info(f"Cumulative: {cumul_stats.get('total_trades',0)} trades | "
               f"To n≥50: {cumul_stats.get('trades_to_n50', ACTUARIAL_THRESHOLD)} more")

    # Log pattern performance if available
    for pattern, stats in cumul_stats.get('by_crabel_pattern', {}).items():
        logger.info(f"  {pattern:15s}: {stats['count']} trades | "
                   f"WR {stats['win_rate']*100:.0f}% | avg ${stats['avg_pnl']:+.2f}")

    # Append to cumulative
    if not today_outcomes.empty:
        updated = pd.concat([cumulative, today_outcomes], ignore_index=True).drop_duplicates()
        updated.to_csv(CUMULATIVE_PATH, index=False)

    # Actuarial feed
    obs = format_actuarial_observations(today_outcomes)
    if obs:
        obs_path = OUTPUT_DIR / f'ss_actuarial_feed_{run_date}.json'
        with open(obs_path, 'w') as f:
            json.dump(obs, f, indent=2)
        logger.info(f"Actuarial feed: {obs_path} ({len(obs)} observations)")

    if cumul_stats.get('actuarial_ready') and not feed_actuarial:
        logger.info(f"\n⚡ THRESHOLD REACHED: {cumul_stats['total_trades']} trades ≥ {ACTUARIAL_THRESHOLD}")
        logger.info("Run with --feed-actuarial to merge into main actuarial DB.")

    # Intel panel
    panel = build_intel_panel(daily_stats, cumul_stats, today_outcomes, contracts_today)
    panel_path = OUTPUT_DIR / 'ss_intel_panel.json'
    with open(panel_path, 'w') as f:
        json.dump(panel, f, indent=2, default=str)

    # Daily summary
    summary_path = OUTPUT_DIR / f'ss_daily_summary_{run_date}.json'
    with open(summary_path, 'w') as f:
        json.dump({'daily': daily_stats, 'cumulative': cumul_stats}, f, indent=2)

    logger.info(f"\nIntel panel:   {panel_path}")
    logger.info(f"Daily summary: {summary_path}")

    return {'daily': daily_stats, 'cumulative': cumul_stats, 'panel': panel}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--feed-actuarial', action='store_true')
    args = parser.parse_args()
    run_outcome_logger(args.verbose, args.feed_actuarial)
