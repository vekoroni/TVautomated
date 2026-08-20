"""
AVSHUNTER — 0DTE OUTCOME LOGGER & ACTUARIAL FEEDER v1.0
================================================================================
Component 4 of 4 in the 0DTE Day Trade Module

PURPOSE:
    1. Aggregates all paper trade outcomes from the trigger engine
    2. Computes daily performance statistics
    3. Formats outcome data as state hash observations ready to feed into
       the main actuarial database once Phase E hashes cross n≥50
    4. Generates the 0DTE panel data for the Intelligence Lab dashboard

ACTUARIAL READINESS:
    Each outcome is tagged with the state_hash from the parent Vanguard signal.
    This means 0DTE paper outcomes are simultaneously building:
    - 0DTE-specific base rates (win rate, avg P&L per trade)
    - Phase E hash observations for the main actuarial database

    When Phase E hashes cross n≥50, this module can feed outcomes directly
    into the actuarial_database.db using the same schema as swing trade outcomes.

OUTPUTS:
    zero_dte/output/daily_summary_YYYYMMDD.json    — today's stats
    zero_dte/output/cumulative_outcomes.csv         — all-time paper log
    zero_dte/output/actuarial_feed_YYYYMMDD.json   — state hash observations
    zero_dte/output/zero_dte_intel_panel.json       — Intelligence Lab panel data

REGRESSION GUARANTEE:
    Only writes to zero_dte/output/. Never touches the main actuarial database
    until explicitly invoked with --feed-actuarial flag after n≥50 threshold met.
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

ACTUARIAL_READY_THRESHOLD = 50   # n≥50 before feeding main DB
OUTPUT_DIR = Path('zero_dte/output')
CUMULATIVE_PATH = OUTPUT_DIR / 'cumulative_outcomes.csv'


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('0DTE_OUTCOMES')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | 0DTE OUTCOMES | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── OUTCOME LOADER ───────────────────────────────────────────────────────────

def load_todays_outcomes(run_date: Optional[str] = None) -> pd.DataFrame:
    """Load today's paper outcomes from the trigger engine output."""
    if not run_date:
        run_date = date.today().strftime('%Y%m%d')

    path = OUTPUT_DIR / f'paper_outcomes_{run_date}.csv'
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def load_cumulative_outcomes() -> pd.DataFrame:
    """Load all historical paper outcomes."""
    if not CUMULATIVE_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(CUMULATIVE_PATH)


def load_enriched_signals_for_hashes(run_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load the enriched signals CSV to get state_hash for each ticker.
    Used to tag outcomes with their actuarial hash.
    """
    # Find most recent enriched file
    candidates = sorted(
        list(Path('.').glob('**/vanguard_signals_enriched_*.csv')),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )
    if not candidates:
        return pd.DataFrame()

    df = pd.read_csv(candidates[0], low_memory=False)
    hash_col = next((c for c in ['layer2__state_hash', 'state_hash'] if c in df.columns), None)
    if not hash_col:
        return pd.DataFrame()

    return df[['ticker', hash_col]].rename(columns={hash_col: 'state_hash'}).drop_duplicates('ticker')


# ─── STATISTICS ───────────────────────────────────────────────────────────────

def compute_daily_stats(outcomes: pd.DataFrame) -> Dict:
    """Compute daily performance statistics."""
    if outcomes.empty:
        return {
            'date': date.today().isoformat(),
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': None,
            'total_pnl': 0.0,
            'avg_pnl': None,
            'avg_win': None,
            'avg_loss': None,
            'profit_factor': None,
            'max_win': None,
            'max_loss': None,
            'note': 'No trades today'
        }

    closed = outcomes[outcomes['status'] == 'CLOSED'].copy()
    if closed.empty:
        return {'date': date.today().isoformat(), 'trades': 0, 'note': 'No closed trades'}

    wins   = closed[closed['pnl_dollars'] > 0]
    losses = closed[closed['pnl_dollars'] <= 0]

    gross_profit = wins['pnl_dollars'].sum()
    gross_loss   = abs(losses['pnl_dollars'].sum())

    stats = {
        'date':            date.today().isoformat(),
        'trades':          len(closed),
        'wins':            len(wins),
        'losses':          len(losses),
        'win_rate':        round(len(wins) / len(closed), 4) if len(closed) > 0 else None,
        'total_pnl':       round(closed['pnl_dollars'].sum(), 2),
        'avg_pnl':         round(closed['pnl_dollars'].mean(), 2),
        'avg_win':         round(wins['pnl_dollars'].mean(), 2) if not wins.empty else None,
        'avg_loss':        round(losses['pnl_dollars'].mean(), 2) if not losses.empty else None,
        'profit_factor':   round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        'max_win':         round(closed['pnl_dollars'].max(), 2),
        'max_loss':        round(closed['pnl_dollars'].min(), 2),
        'exit_reasons':    closed['exit_reason'].value_counts().to_dict(),
        'paper_mode':      True,
        'actuarial_status': 'BUILDING — Phase E hashes pre-n50',
    }

    return stats


def compute_cumulative_stats(cumulative: pd.DataFrame) -> Dict:
    """Compute all-time paper performance statistics."""
    if cumulative.empty:
        return {'total_trades': 0, 'note': 'No paper trade history yet'}

    closed = cumulative[cumulative['status'] == 'CLOSED'].copy()
    if closed.empty:
        return {'total_trades': 0, 'note': 'No closed trades in history'}

    wins   = closed[closed['pnl_dollars'] > 0]
    losses = closed[closed['pnl_dollars'] <= 0]

    # By exit reason
    by_reason = {}
    for reason, group in closed.groupby('exit_reason'):
        by_reason[reason] = {
            'count':    len(group),
            'win_rate': round(len(group[group['pnl_dollars'] > 0]) / len(group), 3),
            'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
        }

    # By direction
    by_direction = {}
    for direction, group in closed.groupby('direction'):
        by_direction[direction] = {
            'count':    len(group),
            'win_rate': round(len(group[group['pnl_dollars'] > 0]) / len(group), 3),
            'avg_pnl':  round(group['pnl_dollars'].mean(), 2),
        }

    gross_profit = wins['pnl_dollars'].sum()
    gross_loss   = abs(losses['pnl_dollars'].sum())

    return {
        'total_trades':        len(closed),
        'total_wins':          len(wins),
        'total_losses':        len(losses),
        'overall_win_rate':    round(len(wins) / len(closed), 4),
        'total_pnl':           round(closed['pnl_dollars'].sum(), 2),
        'avg_pnl_per_trade':   round(closed['pnl_dollars'].mean(), 2),
        'profit_factor':       round(gross_profit / gross_loss, 3) if gross_loss > 0 else None,
        'sharpe_approx':       round(closed['pnl_dollars'].mean() / (closed['pnl_dollars'].std() or 1), 3),
        'max_drawdown_day':    round(closed.groupby(closed.get('entry_time', 'date'))['pnl_dollars'].sum().min() if 'entry_time' in closed.columns else 0, 2),
        'by_exit_reason':      by_reason,
        'by_direction':        by_direction,
        'trades_to_n50':       max(0, ACTUARIAL_READY_THRESHOLD - len(closed)),
        'actuarial_ready':     len(closed) >= ACTUARIAL_READY_THRESHOLD,
        'paper_mode':          True,
    }


# ─── ACTUARIAL FEED FORMATTER ────────────────────────────────────────────────

def format_actuarial_observations(
    outcomes: pd.DataFrame,
    hash_map: pd.DataFrame
) -> List[Dict]:
    """
    Format closed outcomes as state hash observations.
    These can be fed into the main actuarial database when:
    1. The 0DTE module's own Phase E trades reach n≥50, OR
    2. Manually invoked after validation

    Uses same schema as swing trade actuarial observations.
    """
    if outcomes.empty or hash_map.empty:
        return []

    closed = outcomes[outcomes['status'] == 'CLOSED'].copy()
    merged = closed.merge(hash_map, on='ticker', how='left')

    observations = []
    for _, row in merged.iterrows():
        obs = {
            'state_hash':       str(row.get('state_hash', 'UNKNOWN')),
            'ticker':           str(row.get('ticker', '')),
            'trade_type':       '0DTE',
            'direction':        str(row.get('direction', '')),
            'entry_premium':    float(row.get('entry_premium', 0)),
            'exit_premium':     float(row.get('exit_premium', 0)),
            'pnl_dollars':      float(row.get('pnl_dollars', 0)),
            'pnl_pct':          float(row.get('pnl_pct', 0)),
            'exit_reason':      str(row.get('exit_reason', '')),
            'win':              1 if float(row.get('pnl_dollars', 0)) > 0 else 0,
            'hold_hours':       float(row.get('hold_hours', 0)) if 'hold_hours' in row else 0,
            'paper':            True,
            'recorded_at':      datetime.utcnow().isoformat(),
        }
        observations.append(obs)

    return observations


# ─── INTELLIGENCE PANEL DATA ─────────────────────────────────────────────────

def build_intel_panel(
    daily_stats: Dict,
    cumulative_stats: Dict,
    todays_outcomes: pd.DataFrame,
    contracts_today: List[Dict]
) -> Dict:
    """
    Build the data payload for the Intelligence Lab 0DTE panel.
    This is consumed by the dashboard HTML.
    """
    panel = {
        'generated_at':       datetime.utcnow().isoformat(),
        'date':               date.today().isoformat(),
        'paper_mode':         True,
        'actuarial_status':   'DISCOVERY — Building Phase E observations',
        'trades_to_n50':      cumulative_stats.get('trades_to_n50', 50),
        'actuarial_ready':    cumulative_stats.get('actuarial_ready', False),

        # Today
        'today': {
            'eligible_count':  len(contracts_today),
            'trades_taken':    daily_stats.get('trades', 0),
            'wins':            daily_stats.get('wins', 0),
            'losses':          daily_stats.get('losses', 0),
            'pnl':             daily_stats.get('total_pnl', 0),
            'win_rate':        daily_stats.get('win_rate'),
            'entry_window':    '09:45–10:15 ET',
            'hard_exit':       '14:00 ET',
        },

        # Cumulative
        'cumulative': {
            'total_trades':    cumulative_stats.get('total_trades', 0),
            'win_rate':        cumulative_stats.get('overall_win_rate'),
            'total_pnl':       cumulative_stats.get('total_pnl', 0),
            'profit_factor':   cumulative_stats.get('profit_factor'),
            'sharpe':          cumulative_stats.get('sharpe_approx'),
            'by_direction':    cumulative_stats.get('by_direction', {}),
            'by_exit_reason':  cumulative_stats.get('by_exit_reason', {}),
        },

        # Today's candidates
        'candidates': [
            {
                'rank':     c.get('zero_dte_rank', 0),
                'ticker':   c.get('ticker', ''),
                'direction':c.get('direction', ''),
                'strike':   c.get('strike', 0),
                'premium':  c.get('mid', 0),
                'delta':    c.get('delta', 0),
                'entry_method': c.get('entry_method', ''),
                'rr':       c.get('screener_rr', 0),
                'ev':       c.get('screener_ev', 0),
            }
            for c in contracts_today
        ],

        # Today's closed trades
        'closed_trades': (
            todays_outcomes[todays_outcomes['status'] == 'CLOSED'][
                ['ticker', 'direction', 'strike', 'entry_premium',
                 'exit_premium', 'pnl_dollars', 'pnl_pct', 'exit_reason']
            ].to_dict('records')
            if not todays_outcomes.empty else []
        ),
    }

    return panel


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_outcome_logger(
    verbose: bool = False,
    feed_actuarial: bool = False
):
    """
    Main entry point. Aggregates outcomes, computes stats, saves outputs.
    """
    logger = setup_logger(verbose)
    run_date = date.today().strftime('%Y%m%d')
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("AVSHUNTER — 0DTE OUTCOME LOGGER v1.0")
    logger.info(f"Date: {run_date} | Actuarial feed: {feed_actuarial}")
    logger.info("=" * 60)

    # Load data
    todays_outcomes  = load_todays_outcomes(run_date)
    cumulative       = load_cumulative_outcomes()
    hash_map         = load_enriched_signals_for_hashes()

    # Load today's contracts
    contracts_path = OUTPUT_DIR / f'zero_dte_contracts_{run_date}.json'
    contracts_today = []
    if contracts_path.exists():
        with open(contracts_path) as f:
            contracts_today = json.load(f)

    logger.info(f"Today's outcomes: {len(todays_outcomes)} trades")
    logger.info(f"Cumulative outcomes: {len(cumulative)} all-time trades")

    # Compute stats
    daily_stats      = compute_daily_stats(todays_outcomes)
    cumulative_stats = compute_cumulative_stats(cumulative)

    # Log daily summary
    if daily_stats.get('trades', 0) > 0:
        logger.info(f"\nToday: {daily_stats['trades']} trades | "
                   f"Win rate: {daily_stats.get('win_rate', 0)*100:.0f}% | "
                   f"P&L: ${daily_stats.get('total_pnl', 0):+.2f}")
        if daily_stats.get('exit_reasons'):
            logger.info(f"Exit reasons: {daily_stats['exit_reasons']}")

    logger.info(f"\nCumulative: {cumulative_stats.get('total_trades', 0)} trades | "
               f"n≥50 in {cumulative_stats.get('trades_to_n50', 50)} more trades")

    # Append today's outcomes to cumulative
    if not todays_outcomes.empty:
        updated_cumulative = pd.concat([cumulative, todays_outcomes], ignore_index=True).drop_duplicates()
        updated_cumulative.to_csv(CUMULATIVE_PATH, index=False)
        logger.info(f"Cumulative log updated: {CUMULATIVE_PATH}")

    # Format actuarial observations
    actuarial_obs = format_actuarial_observations(todays_outcomes, hash_map)
    if actuarial_obs:
        obs_path = OUTPUT_DIR / f'actuarial_feed_{run_date}.json'
        with open(obs_path, 'w') as f:
            json.dump(actuarial_obs, f, indent=2)
        logger.info(f"Actuarial feed saved: {obs_path} ({len(actuarial_obs)} observations)")

    # Check actuarial readiness
    if cumulative_stats.get('actuarial_ready') and not feed_actuarial:
        logger.info(
            f"\n⚡ ACTUARIAL THRESHOLD REACHED: {cumulative_stats['total_trades']} trades ≥ {ACTUARIAL_READY_THRESHOLD}"
        )
        logger.info(
            "Run with --feed-actuarial to merge 0DTE observations into the main actuarial database."
        )

    if feed_actuarial:
        if cumulative_stats.get('actuarial_ready'):
            logger.info("\n⚡ FEEDING ACTUARIAL DATABASE...")
            logger.info("(Manual merge step — copy actuarial_feed CSV to actuarial DB import path)")
            logger.info(f"Feed file: {OUTPUT_DIR / f'actuarial_feed_{run_date}.json'}")
        else:
            logger.warning(
                f"Not ready to feed actuarial DB. "
                f"Need {cumulative_stats.get('trades_to_n50', 50)} more trades."
            )

    # Build and save Intelligence Lab panel data
    panel = build_intel_panel(daily_stats, cumulative_stats, todays_outcomes, contracts_today)
    panel_path = OUTPUT_DIR / 'zero_dte_intel_panel.json'
    with open(panel_path, 'w') as f:
        json.dump(panel, f, indent=2, default=str)
    logger.info(f"Intel panel saved: {panel_path}")

    # Save daily summary
    summary_path = OUTPUT_DIR / f'daily_summary_{run_date}.json'
    with open(summary_path, 'w') as f:
        json.dump({'daily': daily_stats, 'cumulative': cumulative_stats}, f, indent=2)
    logger.info(f"Daily summary saved: {summary_path}")

    return {
        'daily':      daily_stats,
        'cumulative': cumulative_stats,
        'panel':      panel,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AVSHUNTER 0DTE Outcome Logger')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument(
        '--feed-actuarial',
        action='store_true',
        help='Feed outcomes to main actuarial DB (only when n≥50 reached)'
    )
    args = parser.parse_args()

    run_outcome_logger(
        verbose=args.verbose,
        feed_actuarial=args.feed_actuarial
    )
