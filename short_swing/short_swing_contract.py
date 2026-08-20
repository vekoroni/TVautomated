"""
AVSHUNTER — SHORT-SWING CONTRACT SELECTOR v1.0
================================================================================
Component 2 of 5 in the Short-Swing Module (Scope 2)

PURPOSE:
    For each eligible ticker, selects the optimal 7-14 DTE contract.
    Strategy: first OTM strike within 2% of spot, targeting delta 0.35-0.50.

LOGIC:
    1. If the evening-run contract is already in 5-21 DTE range → USE it
    2. Otherwise → fetch the live chain from Polygon, find the nearest
       expiry in the 7-21 day window, select optimal strike

CONTRACT SELECTION RULES (short-swing specific):
    - DTE target:   7–21 days (wider than ideal to handle expiry gaps)
    - Strike:       First OTM within 2% of spot (more leeway than 0DTE)
    - Delta target: 0.35–0.50 (slightly more ITM than 0DTE for overnight hold)
    - Min OI:       300 contracts (lower threshold than 0DTE — weekly chains thinner)
    - Max spread:   15% of mid-price
    - Min premium:  $0.10
    - Stop:         30% of premium (less aggressive than 0DTE 50%)
    - Target:       Prior range width (minimum 2x risk)

HOLD RULES:
    - Max hold:     3 trading days from entry date
    - Hard exit:    Day 3 market close regardless of P&L
    - Stop:         30% of premium paid (NOT a structural stop)
    - Target:       First exit at 2x risk, full exit at prior range top

REGRESSION GUARANTEE:
    Standalone Polygon client. No Vanguard package imports.
    Writes only to short_swing/output/
================================================================================
"""

import argparse
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

DTE_MIN          = 5
DTE_MAX          = 21
TARGET_DELTA_MIN = 0.30
TARGET_DELTA_MAX = 0.50
MAX_OTM_PCT      = 0.025     # 2.5% OTM max
MIN_OI           = 300
MAX_SPREAD_PCT   = 0.15
MIN_PREMIUM      = 0.10

PREMIUM_STOP_PCT   = 0.30    # Exit if premium loses 30%
MAX_HOLD_DAYS      = 3
MAX_POSITIONS_PAPER = 1
MAX_POSITIONS_LIVE  = 3

POLYGON_BASE = 'https://api.polygon.io'


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('SS_CONTRACT')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | SS_CONTRACT | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── POLYGON CLIENT ──────────────────────────────────────────────────────────

class PolygonSSClient:
    """Minimal Polygon client for short-swing contract selection."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('POLYGON_API_KEY', '')
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not set")
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {self.api_key}'
        self._last = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)
        self._last = time.time()

    def get_spot(self, ticker: str) -> Optional[float]:
        self._throttle()
        url = f"{POLYGON_BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
        try:
            r = self.session.get(url, params={'apiKey': self.api_key}, timeout=10)
            r.raise_for_status()
            d = r.json().get('ticker', {})
            return d.get('day', {}).get('c') or d.get('prevDay', {}).get('c')
        except Exception:
            return None

    def get_available_expiries(self, ticker: str) -> List[str]:
        """Get all available expiry dates for the ticker within DTE range."""
        self._throttle()
        today = date.today()
        date_from = (today + timedelta(days=DTE_MIN)).isoformat()
        date_to   = (today + timedelta(days=DTE_MAX)).isoformat()
        url = f"{POLYGON_BASE}/v3/reference/options/{ticker}"
        expiries = set()
        try:
            r = self.session.get(url, params={
                'expiration_date.gte': date_from,
                'expiration_date.lte': date_to,
                'limit': 250,
                'apiKey': self.api_key
            }, timeout=15)
            r.raise_for_status()
            for result in r.json().get('results', []):
                exp = result.get('expiration_date')
                if exp:
                    expiries.add(exp)
        except Exception:
            pass
        return sorted(expiries)

    def get_chain_for_expiry(self, ticker: str, expiry: str) -> pd.DataFrame:
        """Fetch options chain for a specific expiry date."""
        self._throttle()
        url = f"{POLYGON_BASE}/v3/snapshot/options/{ticker}"
        params = {'expiration_date': expiry, 'limit': 250, 'apiKey': self.api_key}
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
            except Exception:
                break

        if not all_results:
            return pd.DataFrame()

        rows = []
        for res in all_results:
            d = res.get('details', {})
            g = res.get('greeks', {}) or {}
            q = res.get('last_quote', {}) or {}
            day = res.get('day', {}) or {}
            rows.append({
                'option_symbol': d.get('ticker', ''),
                'right':         (d.get('contract_type', '') or '').upper()[:1],
                'strike':        float(d.get('strike_price', 0)),
                'expiry':        d.get('expiration_date', expiry),
                'delta':         float(g.get('delta', 0)),
                'gamma':         float(g.get('gamma', 0)),
                'theta':         float(g.get('theta', 0)),
                'iv':            float(res.get('implied_volatility', 0)),
                'open_interest': int(res.get('open_interest', 0)),
                'volume':        int(day.get('volume', 0)),
                'bid':           float(q.get('bid', 0)),
                'ask':           float(q.get('ask', 0)),
                'mid':           (float(q.get('bid', 0)) + float(q.get('ask', 0))) / 2,
            })
        df = pd.DataFrame(rows)
        df['spread_pct'] = (df['ask'] - df['bid']) / df['mid'].replace(0, np.nan)
        return df


# ─── CONTRACT SELECTION ───────────────────────────────────────────────────────

def select_contract(chain: pd.DataFrame, spot: float, direction: str,
                    expiry: str, logger: logging.Logger) -> Optional[Dict]:
    if chain.empty or spot <= 0:
        return None

    right = 'C' if direction.upper() == 'CALL' else 'P'
    side  = chain[chain['right'] == right].copy()

    # Liquidity gates
    side = side[side['open_interest'] >= MIN_OI]
    side = side[side['mid'] >= MIN_PREMIUM]
    side = side[side['spread_pct'] <= MAX_SPREAD_PCT]

    if side.empty:
        logger.debug(f"  No contracts passed liquidity gates for {right}")
        return None

    # OTM within 2.5%
    if right == 'C':
        otm = side[(side['strike'] > spot) & (side['strike'] <= spot * (1 + MAX_OTM_PCT))]
    else:
        otm = side[(side['strike'] < spot) & (side['strike'] >= spot * (1 - MAX_OTM_PCT))]

    if otm.empty:
        # Fallback: nearest OTM
        if right == 'C':
            otm = side[side['strike'] > spot].sort_values('strike')
        else:
            otm = side[side['strike'] < spot].sort_values('strike', ascending=False)
        if otm.empty:
            return None
        otm = otm.head(3)

    # Delta filter
    if right == 'C':
        delta_ok = otm[(otm['delta'] >= TARGET_DELTA_MIN) & (otm['delta'] <= TARGET_DELTA_MAX)]
    else:
        delta_ok = otm[(otm['delta'] >= -TARGET_DELTA_MAX) & (otm['delta'] <= -TARGET_DELTA_MIN)]

    candidates = delta_ok if not delta_ok.empty else otm

    # Pick closest to spot
    selected = (candidates.sort_values('strike') if right == 'C'
                else candidates.sort_values('strike', ascending=False)).iloc[0]

    premium    = float(selected['mid'])
    stop_prem  = round(premium * (1 - PREMIUM_STOP_PCT), 4)
    target_prem = round(premium * (1 + PREMIUM_STOP_PCT * (1 / (1 - PREMIUM_STOP_PCT))), 4)  # 2x risk

    dte = (datetime.strptime(expiry, '%Y-%m-%d').date() - date.today()).days

    return {
        'option_symbol':     str(selected.get('option_symbol', '')),
        'right':             right,
        'direction':         direction.upper(),
        'strike':            float(selected['strike']),
        'expiry':            expiry,
        'dte':               dte,
        'spot_at_select':    spot,
        'moneyness_pct':     round((float(selected['strike']) - spot) / spot * 100, 3),
        'bid':               float(selected['bid']),
        'ask':               float(selected['ask']),
        'mid':               round(premium, 4),
        'premium':           round(premium, 4),
        'delta':             float(selected['delta']),
        'gamma':             float(selected.get('gamma', 0)),
        'theta':             float(selected.get('theta', 0)),
        'iv':                float(selected.get('iv', 0)),
        'open_interest':     int(selected['open_interest']),
        'spread_pct':        round(float(selected.get('spread_pct', 0)), 4),
        'stop_loss_premium': stop_prem,
        'target_premium':    target_prem,
        'stop_pct':          PREMIUM_STOP_PCT,
        'rr_short_swing':    2.0,
        'max_hold_days':     MAX_HOLD_DAYS,
        'hard_exit':         f'Day {MAX_HOLD_DAYS} market close',
        'entry_window':      'Market open +30 min',
        'paper_contracts':   MAX_POSITIONS_PAPER,
        'live_contracts':    MAX_POSITIONS_LIVE,
        'selected_at':       datetime.now(timezone.utc).isoformat(),
    }


# ─── MAIN PROCESSOR ──────────────────────────────────────────────────────────

def process_eligible(
    eligible_path: Optional[str] = None,
    api_key: Optional[str] = None,
    verbose: bool = False,
    paper: bool = True
) -> List[Dict]:
    logger = setup_logger(verbose)
    run_date   = date.today().strftime('%Y%m%d')
    output_dir = Path('short_swing/output')

    logger.info("=" * 60)
    logger.info("AVSHUNTER — SHORT-SWING CONTRACT SELECTOR v1.0")
    logger.info(f"Mode: {'PAPER' if paper else 'LIVE'} | DTE target: {DTE_MIN}-{DTE_MAX}d")
    logger.info("=" * 60)

    # Load screener output
    if eligible_path:
        p = Path(eligible_path)
    else:
        candidates = sorted(output_dir.glob('ss_eligible_*.csv'),
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not candidates:
            logger.error("No screener output found. Run short_swing_screener.py first.")
            return []
        p = candidates[0]

    eligible_df = pd.read_csv(p)
    logger.info(f"Processing {len(eligible_df)} eligible ticker(s)")

    if eligible_df.empty:
        return []

    try:
        client = PolygonSSClient(api_key)
    except ValueError as e:
        logger.error(str(e))
        return []

    selected = []

    for _, row in eligible_df.iterrows():
        ticker    = str(row.get('ticker', ''))
        direction = str(row.get('options_direction', 'CALL')).upper()
        rank      = int(row.get('short_swing_rank', 0))
        use_existing = bool(row.get('use_existing_contract', False))
        existing_dte = int(row.get('existing_dte', -1))

        logger.info(f"\n[#{rank}] {ticker} — {direction} | "
                   f"existing DTE: {existing_dte} | "
                   f"use existing: {use_existing}")

        spot = client.get_spot(ticker)
        if not spot:
            logger.warning(f"  Could not fetch spot for {ticker}")
            continue
        logger.info(f"  Spot: ${spot:.2f}")

        contract = None

        # Try existing contract first if in range
        if use_existing and pd.notna(row.get('contract_strike')) and pd.notna(row.get('contract_expiry')):
            logger.info(f"  Using existing evening-run contract (DTE {existing_dte})")
            premium = float(row.get('contract_premium', 0)) if pd.notna(row.get('contract_premium')) else 0
            if premium > 0:
                contract = {
                    'option_symbol':     f"{ticker}_{row['contract_expiry']}_{direction[0]}{row['contract_strike']}",
                    'right':             direction[0],
                    'direction':         direction,
                    'strike':            float(row['contract_strike']),
                    'expiry':            str(row['contract_expiry']),
                    'dte':               existing_dte,
                    'spot_at_select':    spot,
                    'moneyness_pct':     round((float(row['contract_strike']) - spot) / spot * 100, 3),
                    'bid':               premium * 0.95,
                    'ask':               premium * 1.05,
                    'mid':               round(premium, 4),
                    'premium':           round(premium, 4),
                    'delta':             float(row.get('contract_delta', 0.40) if pd.notna(row.get('contract_delta')) else 0.40),
                    'theta':             float(row.get('contract_theta', 0)) if pd.notna(row.get('contract_theta')) else 0,
                    'iv':                0,
                    'open_interest':     0,
                    'spread_pct':        0.10,
                    'stop_loss_premium': round(premium * (1 - PREMIUM_STOP_PCT), 4),
                    'target_premium':    round(premium * (1 + PREMIUM_STOP_PCT * 2), 4),
                    'stop_pct':          PREMIUM_STOP_PCT,
                    'rr_short_swing':    2.0,
                    'max_hold_days':     MAX_HOLD_DAYS,
                    'hard_exit':         f'Day {MAX_HOLD_DAYS} market close',
                    'entry_window':      'Market open +30 min',
                    'paper_contracts':   MAX_POSITIONS_PAPER,
                    'live_contracts':    MAX_POSITIONS_LIVE,
                    'selected_at':       datetime.now(timezone.utc).isoformat(),
                    'source':            'evening_run',
                }

        # Otherwise fetch fresh short-dated contract
        if not contract:
            logger.info(f"  Fetching {DTE_MIN}-{DTE_MAX}d chain from Polygon...")
            expiries = client.get_available_expiries(ticker)
            if not expiries:
                logger.warning(f"  No expiries found in {DTE_MIN}-{DTE_MAX}d range for {ticker}")
                continue
            logger.info(f"  Available expiries: {expiries}")

            # Try each expiry, pick first that returns a valid contract
            for exp in expiries:
                chain = client.get_chain_for_expiry(ticker, exp)
                if chain.empty:
                    continue
                contract = select_contract(chain, spot, direction, exp, logger)
                if contract:
                    contract['source'] = 'polygon_fresh'
                    break

        if not contract:
            logger.warning(f"  No suitable contract found for {ticker}")
            continue

        # Enrich with screener metadata
        contract.update({
            'ticker':              ticker,
            'short_swing_rank':    rank,
            'phase':               str(row.get('phase', '')),
            'crabel_pattern':      str(row.get('crabel_pattern', '')),
            'crabel_state':        str(row.get('crabel_state', '')),
            'composite_score':     float(row.get('composite_score', 0)),
            'state_hash':          str(row.get('state_hash', '')),
            'entry_rule':          str(row.get('ss_entry_rule', '')),
            'trigger_level':       str(row.get('ss_trigger_level', '')),
            'ivp':                 str(row.get('ivp_label', '')),
            'paper_mode':          paper,
            'entry_date':          date.today().isoformat(),
            'hard_exit_date':      (date.today() + timedelta(days=MAX_HOLD_DAYS)).isoformat(),
        })

        logger.info(
            f"  ✓ {contract['option_symbol']} | "
            f"Strike ${contract['strike']:.2f} | DTE {contract['dte']} | "
            f"Mid ${contract['mid']:.2f} | Delta {contract['delta']:.3f}"
        )
        logger.info(
            f"    Stop ${contract['stop_loss_premium']:.2f} | "
            f"Target ${contract['target_premium']:.2f} | "
            f"Hard exit: {contract['hard_exit_date']}"
        )
        selected.append(contract)

    # Save
    if selected:
        out_path = output_dir / f'ss_contracts_{run_date}.json'
        with open(out_path, 'w') as f:
            json.dump(selected, f, indent=2, default=str)
        logger.info(f"\nContracts saved: {out_path}")

    logger.info(f"\n{'='*60}")
    logger.info(f"CONTRACTS SELECTED: {len(selected)}")
    logger.info(f"ENTRY: Market open +30 min | ENTRY RULE: Crabel open-range breakout")
    logger.info(f"HOLD: Max {MAX_HOLD_DAYS} trading days | STOP: {int(PREMIUM_STOP_PCT*100)}% of premium")
    logger.info('='*60)

    return selected


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Short-Swing Contract Selector')
    parser.add_argument('--eligible', type=str, default=None)
    parser.add_argument('--api-key',  type=str, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--paper', action='store_true', default=True)
    args = parser.parse_args()
    process_eligible(args.eligible, args.api_key, args.verbose, args.paper)
