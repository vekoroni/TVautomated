"""
AVSHUNTER — SHORT-SWING MASTER RUNNER v1.0
================================================================================
Single entry point for the entire Short-Swing Module (Scope 2).

Ties together all 5 components:
    1. short_swing_screener.py       — Phase C/E + Crabel + IVP gates
    2. short_swing_contract.py       — 7-14 DTE Polygon contract selection
    3. short_swing_monitor.py        — EOD Crabel trigger + position management
    4. short_swing_outcome_logger.py — Outcome aggregation + actuarial feed

USAGE:
    # Pre-market: check eligibility
    python run_short_swing.py --screen-only

    # Morning: select contracts (run after evening workflow completes)
    python run_short_swing.py --contracts-only

    # EOD: check triggers + update positions (run after 16:05 ET)
    python run_short_swing.py --eod

    # Full sequence (screen + contracts + eod in one call)
    python run_short_swing.py

    # Post-close logging only
    python run_short_swing.py --log-only

    # Verbose
    python run_short_swing.py --eod --verbose

DAILY SEQUENCE (recommended):
    Pre-market  : python run_short_swing.py --screen-only
    After open  : Monitor for Crabel open-range breakout manually
    After close : python run_short_swing.py --eod
    EOD logging : python run_short_swing.py --log-only

REGRESSION GUARANTEE:
    Does not import from Vanguard package.
    Does not modify run.py, --evening, or --premarket workflows.
    Writes only to short_swing/output/
================================================================================
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from short_swing_screener       import run_screener
from short_swing_contract       import process_eligible
from short_swing_monitor        import ShortSwingMonitor
from short_swing_outcome_logger import run_outcome_logger


BANNER = """
╔══════════════════════════════════════════════════════════╗
║         AVSHUNTER — SHORT-SWING MODULE (SCOPE 2)         ║
║         Crabel NR7 + Phase C/E  |  1-3 Day Hold          ║
║         Paper Mode Active — Building to n≥50             ║
╚══════════════════════════════════════════════════════════╝
"""


def setup_logger(verbose: bool) -> logging.Logger:
    logger = logging.getLogger('SS_MASTER')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | SHORT-SWING | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


def run_full(args, logger):
    print(BANNER)
    logger.info(f"Date: {date.today().isoformat()} | Mode: PAPER")
    logger.info("─" * 55)

    # ── 1. Screen ────────────────────────────────────────────
    logger.info("\n[1/4] Running Short-Swing Screener...")
    result = run_screener(
        enriched_path=args.enriched,
        verbose=args.verbose,
        paper=True
    )
    count = result.get('count', 0)
    if count == 0:
        logger.info("No eligible candidates today. Running outcome logger.")
        run_outcome_logger(verbose=args.verbose)
        return
    logger.info(f"    {count} eligible candidate(s)")

    # ── 2. Contracts ─────────────────────────────────────────
    logger.info("\n[2/4] Selecting contracts...")
    api_key = args.api_key or os.getenv('POLYGON_API_KEY')
    contracts = process_eligible(
        api_key=api_key,
        verbose=args.verbose,
        paper=True
    )
    if not contracts:
        logger.info("No contracts selected.")
        run_outcome_logger(verbose=args.verbose)
        return
    logger.info(f"    {len(contracts)} contract(s) selected")

    # ── 3. EOD Monitor ───────────────────────────────────────
    logger.info("\n[3/4] Running EOD check...")
    monitor = ShortSwingMonitor(api_key=api_key, verbose=args.verbose)
    monitor.run_eod_check(contracts)

    # ── 4. Outcome Logger ────────────────────────────────────
    logger.info("\n[4/4] Logging outcomes...")
    run_outcome_logger(verbose=args.verbose)

    logger.info("\n" + "─" * 55)
    logger.info("Short-swing session complete. Review: short_swing/output/")


def run_screen_only(args, logger):
    logger.info("SCREEN-ONLY MODE")
    result = run_screener(
        enriched_path=args.enriched,
        verbose=args.verbose,
        paper=True
    )
    count = result.get('count', 0)
    logger.info(f"\nResult: {count} eligible short-swing candidate(s) today")
    if count > 0:
        logger.info("Run 'python run_short_swing.py --contracts-only' to select contracts.")
        logger.info("Run 'python run_short_swing.py --eod' after close to check triggers.")


def run_contracts_only(args, logger):
    logger.info("CONTRACT SELECTION MODE")
    api_key = args.api_key or os.getenv('POLYGON_API_KEY')
    contracts = process_eligible(
        api_key=api_key,
        verbose=args.verbose,
        paper=True
    )
    logger.info(f"\nContracts selected: {len(contracts)}")


def run_eod(args, logger):
    logger.info("EOD MONITOR MODE")
    api_key = args.api_key or os.getenv('POLYGON_API_KEY')
    monitor   = ShortSwingMonitor(api_key=api_key, verbose=args.verbose)
    contracts = monitor.load_contracts()
    if not contracts:
        logger.info("No contracts loaded — running outcome logger only.")
    else:
        monitor.run_eod_check(contracts)
    run_outcome_logger(verbose=args.verbose)


def run_log_only(args, logger):
    logger.info("LOG-ONLY MODE")
    result   = run_outcome_logger(verbose=args.verbose, feed_actuarial=args.feed_actuarial)
    daily    = result.get('daily', {})
    cumul    = result.get('cumulative', {})
    logger.info(f"\nToday:      {daily.get('trades',0)} trades | P&L ${daily.get('total_pnl',0):+.2f}")
    logger.info(f"Cumulative: {cumul.get('total_trades',0)} trades | "
               f"To n≥50: {cumul.get('trades_to_n50',50)} more")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AVSHUNTER Short-Swing Master Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_short_swing.py --screen-only       Pre-market eligibility check
  python run_short_swing.py --contracts-only    Select contracts after screening
  python run_short_swing.py --eod               EOD trigger check + position update
  python run_short_swing.py --log-only          Post-close outcome logging
  python run_short_swing.py                     Full sequence
  python run_short_swing.py --verbose           Full debug output
        """
    )
    parser.add_argument('--screen-only',    action='store_true')
    parser.add_argument('--contracts-only', action='store_true')
    parser.add_argument('--eod',            action='store_true')
    parser.add_argument('--log-only',       action='store_true')
    parser.add_argument('--feed-actuarial', action='store_true')
    parser.add_argument('--enriched',       type=str, default=None,
                        help='Path to vanguard_signals_enriched CSV')
    parser.add_argument('--api-key',        type=str, default=None)
    parser.add_argument('--verbose', '-v',  action='store_true')

    args   = parser.parse_args()
    logger = setup_logger(args.verbose)

    if args.screen_only:
        run_screen_only(args, logger)
    elif args.contracts_only:
        run_contracts_only(args, logger)
    elif args.eod:
        run_eod(args, logger)
    elif args.log_only:
        run_log_only(args, logger)
    else:
        run_full(args, logger)
