"""
AVSHUNTER — 0DTE MASTER RUNNER v1.0
================================================================================
Single entry point for the entire 0DTE Day Trade Module.

Ties together all 4 components in sequence:
    1. zero_dte_screener.py       — Phase E eligibility filter
    2. zero_dte_contract.py       — Polygon 0DTE contract selection
    3. intraday_0dte_trigger.py   — 5-minute bar intraday monitor
    4. zero_dte_outcome_logger.py — Outcome aggregation and actuarial feed

USAGE:
    # Full day workflow (run pre-market, stays alive through session)
    python run_0dte.py

    # Screening only (check eligibility without running intraday)
    python run_0dte.py --screen-only

    # End of day outcome logging only
    python run_0dte.py --log-only

    # Test mode — single scan, no continuous loop
    python run_0dte.py --test

    # Verbose output
    python run_0dte.py --verbose

DAILY SEQUENCE:
    Pre-market  (08:00–09:30 ET):  --screen-only
    Market open (09:00–09:30 ET):  contract selection auto-runs
    Market hours (09:30–14:00 ET): intraday trigger monitor
    Post-close  (16:00+ ET):       --log-only

REGRESSION GUARANTEE:
    Adding --session 0dte to run.py is optional.
    This runner is completely standalone and does not interfere with
    --evening or --premarket workflows.
================================================================================
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

# Add parent to path if running from project root
sys.path.insert(0, str(Path(__file__).parent))

from zero_dte_screener      import run_screener
from zero_dte_contract      import process_eligible_tickers
from intraday_0dte_trigger  import ZeroDTETriggerEngine
from zero_dte_outcome_logger import run_outcome_logger


# ─── CONSTANTS ───────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════╗
║           AVSHUNTER — 0DTE DAY TRADE MODULE              ║
║           Paper Mode Active — Building to n≥50           ║
╚══════════════════════════════════════════════════════════╝
"""


def setup_logger(verbose: bool) -> logging.Logger:
    logger = logging.getLogger('0DTE_MASTER')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | 0DTE | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


def run_full(args, logger):
    """Full day workflow: screen → contracts → monitor → log."""

    print(BANNER)
    logger.info(f"Date: {date.today().isoformat()} | Mode: PAPER")
    logger.info("─" * 55)

    # ── Step 1: Screen ──────────────────────────────────────
    logger.info("\n[1/4] Running 0DTE Eligibility Screener...")
    result = run_screener(
        enriched_path=args.enriched,
        verbose=args.verbose,
        paper=True
    )

    eligible_count = result.get('count', 0)
    if eligible_count == 0:
        logger.info("No eligible 0DTE candidates today. Session complete.")
        run_outcome_logger(verbose=args.verbose)
        return

    logger.info(f"    {eligible_count} eligible candidate(s) found")

    # ── Step 2: Contract Selection ───────────────────────────
    logger.info("\n[2/4] Selecting 0DTE contracts...")
    api_key = args.api_key or os.getenv('POLYGON_API_KEY')
    contracts = process_eligible_tickers(
        api_key=api_key,
        verbose=args.verbose,
        paper=True
    )

    if not contracts:
        logger.info("No contracts selected (0DTE chain may not be available today).")
        logger.info("Note: 0DTE chains exist only on days with weekly/daily expiry (most Fridays, some Wed/Mon).")
        run_outcome_logger(verbose=args.verbose)
        return

    logger.info(f"    {len(contracts)} contract(s) selected")

    # ── Step 3: Intraday Monitor ─────────────────────────────
    logger.info("\n[3/4] Starting intraday trigger monitor...")
    logger.info("    Will monitor until 14:00 ET or market close.")
    logger.info("    Press Ctrl+C to exit early (outcomes will still be logged).")

    engine = ZeroDTETriggerEngine(api_key=api_key, verbose=args.verbose)
    # Override contracts with freshly selected ones
    engine.positions = {}

    try:
        if args.test:
            engine.run_test(contracts)
        else:
            engine.run(contracts, scan_interval_minutes=args.interval)
    except KeyboardInterrupt:
        logger.info("\nMonitor interrupted by user.")

    # ── Step 4: Outcome Logging ──────────────────────────────
    logger.info("\n[4/4] Logging outcomes...")
    run_outcome_logger(verbose=args.verbose)

    logger.info("\n" + "─" * 55)
    logger.info("0DTE session complete.")
    logger.info("Review: zero_dte/output/")


def run_screen_only(args, logger):
    """Screening only — useful pre-market to check eligibility."""
    logger.info("SCREEN-ONLY MODE")
    result = run_screener(
        enriched_path=args.enriched,
        verbose=args.verbose,
        paper=True
    )
    count = result.get('count', 0)
    logger.info(f"\nResult: {count} eligible 0DTE candidate(s) today")
    if count > 0:
        logger.info("Run 'python run_0dte.py' at market open to proceed.")


def run_log_only(args, logger):
    """Outcome logging only — run post-close."""
    logger.info("LOG-ONLY MODE")
    result = run_outcome_logger(
        verbose=args.verbose,
        feed_actuarial=args.feed_actuarial
    )
    daily = result.get('daily', {})
    cumul = result.get('cumulative', {})
    logger.info(
        f"\nToday: {daily.get('trades', 0)} trades | "
        f"P&L ${daily.get('total_pnl', 0):+.2f}"
    )
    logger.info(
        f"Cumulative: {cumul.get('total_trades', 0)} trades | "
        f"To n≥50: {cumul.get('trades_to_n50', 50)} more"
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AVSHUNTER 0DTE Master Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_0dte.py                    Full day workflow
  python run_0dte.py --screen-only      Pre-market eligibility check
  python run_0dte.py --log-only         Post-close outcome logging
  python run_0dte.py --test             Single scan test
  python run_0dte.py --verbose          Full debug output
        """
    )

    parser.add_argument('--screen-only',    action='store_true',
                        help='Run screener only (no intraday monitoring)')
    parser.add_argument('--log-only',       action='store_true',
                        help='Run outcome logger only (post-close)')
    parser.add_argument('--test',           action='store_true',
                        help='Test mode: single scan then exit')
    parser.add_argument('--feed-actuarial', action='store_true',
                        help='Feed outcomes to main actuarial DB (requires n≥50)')
    parser.add_argument('--enriched',       type=str, default=None,
                        help='Path to vanguard_signals_enriched CSV')
    parser.add_argument('--api-key',        type=str, default=None,
                        help='Polygon API key')
    parser.add_argument('--interval',       type=int, default=5,
                        help='Intraday scan interval in minutes (default 5)')
    parser.add_argument('--verbose', '-v',  action='store_true',
                        help='Verbose logging')

    args = parser.parse_args()
    logger = setup_logger(args.verbose)

    if args.screen_only:
        run_screen_only(args, logger)
    elif args.log_only:
        run_log_only(args, logger)
    else:
        run_full(args, logger)
