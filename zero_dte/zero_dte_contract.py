"""
AVSHUNTER — 0DTE CONTRACT SELECTOR v1.0
================================================================================
Component 2 of 4 in the 0DTE Day Trade Module

PURPOSE:
    For each ticker passing the screener, fetches the live 0DTE options chain
    via Polygon API and selects the optimal contract for execution.

CONTRACT SELECTION RULES:
    - Direction: from Vanguard precor_intent (BUY_SETUP → CALL, SELL_SETUP → PUT)
    - Expiry:    today's date only (0DTE by definition)
    - Strike:    first OTM within 1% of spot (not ATM — too expensive for 0DTE R:R)
    - Delta:     target 0.35–0.45 (enough sensitivity without overpaying)
    - Min OI:    500 contracts (liquidity gate)
    - Max spread: 10% of mid-price (execution quality gate)

HARD RULES (non-negotiable):
    - Entry window: 9:45–10:15 AM ET only
    - Hard exit: 2:00 PM ET regardless of P&L
    - Stop: 50% of premium paid (exit if premium halves)
    - Max contracts per position: 5 (paper mode caps at 1)

REGRESSION GUARANTEE:
    Uses Polygon REST API directly. Does not import from Vanguard package.
    Zero shared state with the production pipeline.
================================================================================
"""

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

# Contract selection
TARGET_DELTA_MIN = 0.30
TARGET_DELTA_MAX = 0.45
MAX_OTM_PCT = 0.015          # Max 1.5% out of the money
MIN_OPEN_INTEREST = 500      # Minimum OI for liquidity
MAX_SPREAD_PCT = 0.12        # Max spread as % of mid-price
MIN_PREMIUM = 0.05           # Min $0.05 premium (avoid sub-penny)

# Position management
PREMIUM_STOP_PCT = 0.50      # Exit if premium loses 50%
ENTRY_WINDOW_START = (9, 45) # 9:45 AM ET
ENTRY_WINDOW_END = (10, 15)  # 10:15 AM ET
HARD_EXIT_TIME = (14, 0)     # 2:00 PM ET
MAX_CONTRACTS_PAPER = 1      # Paper mode: 1 contract only
MAX_CONTRACTS_LIVE = 5       # Live mode: max 5 contracts

# Polygon API
POLYGON_BASE = 'https://api.polygon.io'


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('0DTE_CONTRACT')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | 0DTE CONTRACT | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── POLYGON CLIENT ──────────────────────────────────────────────────────────

class PolygonOptionsClient:
    """
    Minimal Polygon REST client for 0DTE options chain fetching.
    Standalone — does not use the shared Polygon client from the main pipeline.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('POLYGON_API_KEY', '')
        if not self.api_key:
            raise ValueError(
                "Polygon API key required. Set POLYGON_API_KEY environment variable."
            )
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {self.api_key}'
        self._last_call = 0.0
        self._min_interval = 0.25  # 4 calls/second max

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    def get_snapshot(self, ticker: str) -> Optional[float]:
        """Get current spot price from snapshot."""
        self._throttle()
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        try:
            r = self.session.get(url, params={'apiKey': self.api_key}, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data.get('ticker', {}).get('day', {}).get('c') or \
                   data.get('ticker', {}).get('prevDay', {}).get('c')
        except Exception as e:
            return None

    def get_options_chain(self, ticker: str, expiry_date: str) -> pd.DataFrame:
        """
        Fetch options chain for a specific expiry date.
        expiry_date: 'YYYY-MM-DD'
        Returns DataFrame with options data.
        """
        self._throttle()
        url = f"{POLYGON_BASE}/v3/snapshot/options/{ticker}"
        params = {
            'expiration_date': expiry_date,
            'limit': 250,
            'apiKey': self.api_key
        }

        all_results = []
        while True:
            try:
                r = self.session.get(url, params=params, timeout=15)
                r.raise_for_status()
                data = r.json()
                results = data.get('results', [])
                all_results.extend(results)

                next_url = data.get('next_url')
                if not next_url or not results:
                    break
                url = next_url
                params = {'apiKey': self.api_key}
                self._throttle()

            except Exception as e:
                break

        if not all_results:
            return pd.DataFrame()

        rows = []
        for r in all_results:
            d = r.get('details', {})
            g = r.get('greeks', {})
            day = r.get('day', {})
            q = r.get('last_quote', {})

            rows.append({
                'option_symbol':  d.get('ticker', ''),
                'right':          d.get('contract_type', '').upper()[0] if d.get('contract_type') else '',
                'strike':         float(d.get('strike_price', 0)),
                'expiry':         d.get('expiration_date', ''),
                'dte':            0,
                'delta':          float(g.get('delta', 0)) if g else 0,
                'gamma':          float(g.get('gamma', 0)) if g else 0,
                'theta':          float(g.get('theta', 0)) if g else 0,
                'iv':             float(r.get('implied_volatility', 0)),
                'open_interest':  int(r.get('open_interest', 0)),
                'volume':         int(day.get('volume', 0)),
                'bid':            float(q.get('bid', 0)),
                'ask':            float(q.get('ask', 0)),
                'mid':            (float(q.get('bid', 0)) + float(q.get('ask', 0))) / 2,
            })

        return pd.DataFrame(rows)


# ─── CONTRACT SELECTION LOGIC ─────────────────────────────────────────────────

def select_contract(
    chain: pd.DataFrame,
    spot: float,
    direction: str,
    logger: logging.Logger
) -> Optional[Dict]:
    """
    Select optimal 0DTE contract from chain.

    Args:
        chain: Options chain DataFrame
        spot: Current spot price
        direction: 'CALL' or 'PUT'
        logger: Logger instance

    Returns:
        Dict with selected contract details, or None if no suitable contract.
    """
    if chain.empty or spot <= 0:
        return None

    right = 'C' if direction.upper() == 'CALL' else 'P'
    side = chain[chain['right'] == right].copy()

    if side.empty:
        logger.warning(f"No {right} contracts in chain")
        return None

    # Gate A: Minimum liquidity
    side = side[side['open_interest'] >= MIN_OPEN_INTEREST]
    if side.empty:
        logger.warning(f"No contracts with OI ≥ {MIN_OPEN_INTEREST}")
        return None

    # Gate B: Minimum premium
    side = side[side['mid'] >= MIN_PREMIUM]

    # Gate C: Spread quality
    side = side.copy()
    side['spread_pct'] = (side['ask'] - side['bid']) / side['mid'].replace(0, np.nan)
    side = side[side['spread_pct'] <= MAX_SPREAD_PCT]
    if side.empty:
        logger.warning("No contracts within spread threshold")
        return None

    # Gate D: OTM within target range
    if right == 'C':
        # Calls: strike above spot, within 1.5%
        side = side[(side['strike'] > spot) & (side['strike'] <= spot * (1 + MAX_OTM_PCT))]
    else:
        # Puts: strike below spot, within 1.5%
        side = side[(side['strike'] < spot) & (side['strike'] >= spot * (1 - MAX_OTM_PCT))]

    if side.empty:
        logger.warning(f"No OTM contracts within {MAX_OTM_PCT*100:.1f}% of spot ${spot:.2f}")
        # Fallback: nearest OTM regardless of distance
        if right == 'C':
            atm_candidates = chain[
                (chain['right'] == 'C') &
                (chain['strike'] > spot) &
                (chain['open_interest'] >= MIN_OPEN_INTEREST)
            ].sort_values('strike')
        else:
            atm_candidates = chain[
                (chain['right'] == 'P') &
                (chain['strike'] < spot) &
                (chain['open_interest'] >= MIN_OPEN_INTEREST)
            ].sort_values('strike', ascending=False)

        if atm_candidates.empty:
            return None
        side = atm_candidates.head(1)

    # Gate E: Delta in target range
    if right == 'C':
        delta_filtered = side[
            (side['delta'] >= TARGET_DELTA_MIN) &
            (side['delta'] <= TARGET_DELTA_MAX)
        ]
    else:
        delta_filtered = side[
            (side['delta'] >= -TARGET_DELTA_MAX) &
            (side['delta'] <= -TARGET_DELTA_MIN)
        ]

    if not delta_filtered.empty:
        side = delta_filtered

    # Select: prefer closest to spot with best delta
    if right == 'C':
        selected = side.sort_values('strike').iloc[0]
    else:
        selected = side.sort_values('strike', ascending=False).iloc[0]

    # Calculate R:R for 0DTE context
    premium = float(selected['mid'])
    stop_loss = premium * (1 - PREMIUM_STOP_PCT)  # 50% stop
    # Target: 2x the risk (1:2 R:R minimum for 0DTE)
    target_premium = premium + (premium * PREMIUM_STOP_PCT * 2)

    contract = {
        'option_symbol':    str(selected.get('option_symbol', '')),
        'right':            right,
        'direction':        direction.upper(),
        'strike':           float(selected['strike']),
        'expiry':           str(selected.get('expiry', date.today().isoformat())),
        'dte':              0,
        'spot_at_select':   spot,
        'moneyness_pct':    round((float(selected['strike']) - spot) / spot * 100, 3),
        'bid':              float(selected['bid']),
        'ask':              float(selected['ask']),
        'mid':              round(premium, 4),
        'premium':          round(premium, 4),
        'delta':            float(selected['delta']),
        'gamma':            float(selected.get('gamma', 0)),
        'theta':            float(selected.get('theta', 0)),
        'iv':               float(selected.get('iv', 0)),
        'open_interest':    int(selected['open_interest']),
        'volume':           int(selected.get('volume', 0)),
        'spread_pct':       round(float(selected.get('spread_pct', 0)), 4),
        'stop_loss_premium':round(stop_loss, 4),
        'target_premium':   round(target_premium, 4),
        'rr_0dte':          2.0,
        'entry_window_et':  f'{ENTRY_WINDOW_START[0]}:{ENTRY_WINDOW_START[1]:02d}–{ENTRY_WINDOW_END[0]}:{ENTRY_WINDOW_END[1]:02d}',
        'hard_exit_et':     f'{HARD_EXIT_TIME[0]}:{HARD_EXIT_TIME[1]:02d}',
        'max_contracts_paper': MAX_CONTRACTS_PAPER,
        'max_contracts_live':  MAX_CONTRACTS_LIVE,
        'selected_at':      datetime.now(timezone.utc).isoformat(),
    }

    return contract


# ─── MAIN PROCESSOR ──────────────────────────────────────────────────────────

def process_eligible_tickers(
    eligible_path: Optional[str] = None,
    api_key: Optional[str] = None,
    verbose: bool = False,
    paper: bool = True
) -> List[Dict]:
    """
    Main entry point. Reads the screener output and selects contracts.
    """
    logger = setup_logger(verbose)
    run_date = date.today().strftime('%Y%m%d')
    expiry_date = date.today().isoformat()
    output_dir = Path('zero_dte/output')

    logger.info("=" * 60)
    logger.info("AVSHUNTER — 0DTE CONTRACT SELECTOR v1.0")
    logger.info(f"Mode: {'PAPER' if paper else 'LIVE'} | Expiry: {expiry_date}")
    logger.info("=" * 60)

    # Load screener output
    if eligible_path:
        p = Path(eligible_path)
    else:
        candidates = sorted(
            output_dir.glob(f'zero_dte_eligible_*.csv'),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if not candidates:
            logger.error("No screener output found. Run zero_dte_screener.py first.")
            return []
        p = candidates[0]

    eligible_df = pd.read_csv(p)
    logger.info(f"Processing {len(eligible_df)} eligible ticker(s) from: {p}")

    if eligible_df.empty:
        logger.info("No eligible tickers. No contracts to select.")
        return []

    # Initialise Polygon client
    try:
        client = PolygonOptionsClient(api_key)
    except ValueError as e:
        logger.error(str(e))
        return []

    selected_contracts = []

    for _, row in eligible_df.iterrows():
        ticker = str(row.get('ticker', ''))
        direction = str(row.get('options_direction', 'CALL')).upper()
        rank = int(row.get('zero_dte_rank', 0))

        logger.info(f"\n[#{rank}] {ticker} — selecting {direction} contract")

        # Get spot price
        spot = client.get_snapshot(ticker)
        if not spot:
            logger.warning(f"  Could not fetch spot price for {ticker} — skipping")
            continue
        logger.info(f"  Spot: ${spot:.2f}")

        # Fetch 0DTE chain
        chain = client.get_options_chain(ticker, expiry_date)
        if chain.empty:
            logger.warning(f"  No 0DTE chain available for {ticker} on {expiry_date} — skipping")
            logger.info(f"  (Note: 0DTE chains only available on days with weekly expiry)")
            continue
        logger.info(f"  Chain: {len(chain)} contracts fetched")

        # Select contract
        contract = select_contract(chain, spot, direction, logger)
        if not contract:
            logger.warning(f"  No suitable contract found for {ticker}")
            continue

        # Enrich with screener metadata
        contract['ticker'] = ticker
        contract['zero_dte_rank'] = rank
        contract['screener_rr'] = float(row.get('rr_options', 0))
        contract['screener_ev'] = float(row.get('ev_adjusted', 0))
        contract['screener_composite'] = float(row.get('composite_score', 0))
        contract['phase'] = str(row.get('phase', ''))
        contract['intent'] = str(row.get('precor_intent', ''))
        contract['entry_method'] = str(row.get('zero_dte_entry_method', ''))
        contract['paper_mode'] = paper

        logger.info(
            f"  ✓ Selected: {contract['option_symbol']} | "
            f"Strike ${contract['strike']:.2f} | "
            f"Mid ${contract['mid']:.2f} | "
            f"Delta {contract['delta']:.3f} | "
            f"OI {contract['open_interest']:,}"
        )
        logger.info(
            f"    Stop: ${contract['stop_loss_premium']:.2f} | "
            f"Target: ${contract['target_premium']:.2f} | "
            f"R:R {contract['rr_0dte']:.1f}x"
        )

        selected_contracts.append(contract)

    # Save
    if selected_contracts:
        out_path = output_dir / f'zero_dte_contracts_{run_date}.json'
        with open(out_path, 'w') as f:
            json.dump(selected_contracts, f, indent=2, default=str)
        logger.info(f"\nContracts saved: {out_path}")

    logger.info(f"\n{'='*60}")
    logger.info(f"CONTRACTS SELECTED: {len(selected_contracts)}")
    logger.info(f"PAPER POSITIONS TODAY: {min(len(selected_contracts), MAX_CONTRACTS_PAPER)}")
    logger.info(f"Entry: {ENTRY_WINDOW_START[0]}:{ENTRY_WINDOW_START[1]:02d}–{ENTRY_WINDOW_END[0]}:{ENTRY_WINDOW_END[1]:02d} ET")
    logger.info(f"Hard exit: {HARD_EXIT_TIME[0]}:{HARD_EXIT_TIME[1]:02d} ET")
    logger.info(f"Stop: 50% of premium paid")
    logger.info('='*60)

    return selected_contracts


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AVSHUNTER 0DTE Contract Selector')
    parser.add_argument('--eligible', type=str, default=None,
                        help='Path to screener output CSV')
    parser.add_argument('--api-key', type=str, default=None,
                        help='Polygon API key (or set POLYGON_API_KEY env var)')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--paper', action='store_true', default=True)
    args = parser.parse_args()

    process_eligible_tickers(
        eligible_path=args.eligible,
        api_key=args.api_key,
        verbose=args.verbose,
        paper=args.paper
    )
