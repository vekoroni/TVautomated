"""
AVSHUNTER — SHORT-SWING EOD MONITOR v1.0
================================================================================
Component 3 of 5 in the Short-Swing Module (Scope 2)

PURPOSE:
    End-of-day position monitor for short-swing paper trades.
    NOT an intraday loop — runs once after close to check entry triggers,
    update open positions, and flag exits.

KEY DIFFERENCE FROM 0DTE:
    0DTE: continuous 5-min intraday loop, same-day exit
    Short-swing: EOD check only, multi-day hold, exit at Day 3 close

DAILY SEQUENCE:
    Morning (pre-open):  Check if any open positions hit their hard exit date
    After open (+30min): Crabel open-range breakout → entry trigger fires
    EOD (16:05 ET):     Run this monitor — updates P&L, checks stops, logs outcomes

ENTRY TRIGGER (Crabel open-range breakout):
    For CALL: Price at open > prior day high → enter
    For PUT:  Price at open < prior day low → enter
    Window:   First 30 minutes of session only
    If not triggered in 30 min → skip today, watch tomorrow (up to Day 3)

EXIT CONDITIONS:
    A. Day 3 hard exit     — close at market regardless of P&L
    B. Stop hit            — premium <= 70% of entry premium (30% stop)
    C. Target hit          — premium >= 2x risk target
    D. Adverse close       — underlying closes strongly against direction on Day 2

REGRESSION GUARANTEE:
    Reads Polygon API for EOD prices and option quotes.
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
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

MAX_HOLD_DAYS      = 3
PREMIUM_STOP_PCT   = 0.30
ENTRY_WINDOW_MINS  = 30          # Crabel window: first 30 min after open
POLYGON_BASE       = 'https://api.polygon.io'

# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('SS_MONITOR')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | SS_MONITOR | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── POLYGON EOD CLIENT ───────────────────────────────────────────────────────

class PolygonEODClient:

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('POLYGON_API_KEY', '')
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY not set")
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'Bearer {self.api_key}'
        self._last = 0.0

    def _throttle(self):
        e = time.time() - self._last
        if e < 0.25:
            time.sleep(0.25 - e)
        self._last = time.time()

    def get_daily_candles(self, ticker: str, n_days: int = 5) -> pd.DataFrame:
        """Get last n_days of daily candles."""
        self._throttle()
        today   = date.today().isoformat()
        n_ago   = (date.today() - timedelta(days=n_days + 7)).isoformat()
        url     = f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{n_ago}/{today}"
        try:
            r = self.session.get(url, params={
                'adjusted': 'true', 'sort': 'asc', 'limit': n_days + 5,
                'apiKey': self.api_key
            }, timeout=10)
            r.raise_for_status()
            results = r.json().get('results', [])
            if not results:
                return pd.DataFrame()
            df = pd.DataFrame(results)
            df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'}, inplace=True)
            df['date'] = pd.to_datetime(df['t'], unit='ms').dt.date
            return df.tail(n_days)
        except Exception:
            return pd.DataFrame()

    def get_option_mid(self, option_symbol: str) -> Optional[float]:
        """Get current mid price for an option contract."""
        self._throttle()
        url = f"{POLYGON_BASE}/v3/snapshot/options/{option_symbol}"
        try:
            r = self.session.get(url, params={'apiKey': self.api_key}, timeout=10)
            r.raise_for_status()
            result = r.json().get('results', {})
            q = result.get('last_quote', {}) or {}
            bid = float(q.get('bid', 0))
            ask = float(q.get('ask', 0))
            if bid + ask > 0:
                return (bid + ask) / 2
            # Fallback to last trade
            lt = result.get('last_trade', {}) or {}
            return float(lt.get('price', 0)) or None
        except Exception:
            return None


# ─── ENTRY TRIGGER ───────────────────────────────────────────────────────────

def check_crabel_trigger(candles: pd.DataFrame, direction: str) -> Tuple[bool, str]:
    """
    Crabel open-range breakout check using daily candles.
    Today's open vs prior day's high/low.
    """
    if len(candles) < 2:
        return False, "Insufficient candle history"

    today     = candles.iloc[-1]
    prior     = candles.iloc[-2]
    today_open  = float(today.get('open', 0))
    prior_high  = float(prior.get('high', 0))
    prior_low   = float(prior.get('low', 0))
    today_close = float(today.get('close', 0))

    if direction.upper() == 'CALL':
        triggered = today_open > prior_high
        reason = (
            f"CALL trigger: today open ${today_open:.2f} > prior high ${prior_high:.2f}"
            if triggered else
            f"No CALL trigger: open ${today_open:.2f} ≤ prior high ${prior_high:.2f}"
        )
    else:
        triggered = today_open < prior_low
        reason = (
            f"PUT trigger: today open ${today_open:.2f} < prior low ${prior_low:.2f}"
            if triggered else
            f"No PUT trigger: open ${today_open:.2f} ≥ prior low ${prior_low:.2f}"
        )

    return triggered, reason


def check_adverse_close(candles: pd.DataFrame, direction: str,
                         entry_price: float) -> Tuple[bool, str]:
    """
    Day 2 adverse close check.
    If underlying closes significantly against direction, flag for review.
    """
    if len(candles) < 1:
        return False, ""

    today = candles.iloc[-1]
    close = float(today.get('close', 0))

    if direction.upper() == 'CALL':
        # Adverse: close > 1.5% below entry price
        drop_pct = (entry_price - close) / entry_price
        if drop_pct > 0.015:
            return True, f"Adverse close: -{ drop_pct*100:.1f}% from entry ${entry_price:.2f}"
    else:
        # Adverse: close > 1.5% above entry price
        rise_pct = (close - entry_price) / entry_price
        if rise_pct > 0.015:
            return True, f"Adverse close: +{rise_pct*100:.1f}% against PUT entry ${entry_price:.2f}"

    return False, ""


# ─── POSITION CLASS ──────────────────────────────────────────────────────────

class ShortSwingPosition:

    def __init__(self, contract: Dict):
        self.ticker          = contract['ticker']
        self.option_symbol   = contract['option_symbol']
        self.direction       = contract['direction']
        self.strike          = contract['strike']
        self.entry_premium   = contract['premium']
        self.stop_premium    = contract['stop_loss_premium']
        self.target_premium  = contract['target_premium']
        self.entry_date      = contract.get('entry_date', date.today().isoformat())
        self.hard_exit_date  = contract.get('hard_exit_date',
                                (date.today() + timedelta(days=MAX_HOLD_DAYS)).isoformat())
        self.entry_price     = contract.get('spot_at_select', 0)
        self.state           = 'WAITING_TRIGGER'   # → OPEN → CLOSED
        self.trigger_date    = None
        self.exit_premium    = None
        self.exit_reason     = None
        self.exit_date       = None
        self.day_number      = 0
        self.contracts       = 1
        self.crabel_pattern  = contract.get('crabel_pattern', '')
        self.state_hash      = contract.get('state_hash', '')

    @property
    def is_past_hard_exit(self) -> bool:
        return date.today().isoformat() >= self.hard_exit_date

    def days_in_trade(self) -> int:
        if not self.trigger_date:
            return 0
        try:
            t = datetime.strptime(self.trigger_date, '%Y-%m-%d').date()
            return (date.today() - t).days
        except Exception:
            return 0

    def pnl(self, current_premium: float) -> float:
        ep = self.entry_premium if self.state == 'OPEN' else (self.exit_premium or self.entry_premium)
        return (current_premium - self.entry_premium) * 100 * self.contracts

    def open_position(self, trigger_date: str, actual_premium: float):
        self.state        = 'OPEN'
        self.trigger_date = trigger_date
        self.entry_premium = actual_premium   # Use actual fill price
        self.stop_premium  = round(actual_premium * (1 - PREMIUM_STOP_PCT), 4)
        self.target_premium = round(actual_premium * (1 + PREMIUM_STOP_PCT * 2), 4)

    def close(self, exit_premium: float, reason: str):
        self.state        = 'CLOSED'
        self.exit_premium = exit_premium
        self.exit_reason  = reason
        self.exit_date    = date.today().isoformat()

    def to_dict(self) -> Dict:
        current = self.exit_premium or self.entry_premium
        return {
            'ticker':           self.ticker,
            'option_symbol':    self.option_symbol,
            'direction':        self.direction,
            'strike':           self.strike,
            'crabel_pattern':   self.crabel_pattern,
            'state_hash':       self.state_hash,
            'entry_premium':    self.entry_premium,
            'stop_premium':     self.stop_premium,
            'target_premium':   self.target_premium,
            'exit_premium':     self.exit_premium,
            'exit_reason':      self.exit_reason,
            'pnl_dollars':      round(self.pnl(current), 2),
            'pnl_pct':          round((current / self.entry_premium - 1) if self.entry_premium else 0, 4),
            'status':           self.state,
            'entry_date':       self.entry_date,
            'trigger_date':     self.trigger_date,
            'exit_date':        self.exit_date,
            'hard_exit_date':   self.hard_exit_date,
            'days_in_trade':    self.days_in_trade(),
            'contracts':        self.contracts,
        }


# ─── MAIN MONITOR ────────────────────────────────────────────────────────────

class ShortSwingMonitor:

    def __init__(self, api_key: Optional[str] = None, verbose: bool = False):
        self.logger     = setup_logger(verbose)
        self.client     = PolygonEODClient(api_key)
        self.output_dir = Path('short_swing/output')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.positions: Dict[str, ShortSwingPosition] = {}

    def load_contracts(self) -> List[Dict]:
        run_date = date.today().strftime('%Y%m%d')
        path = self.output_dir / f'ss_contracts_{run_date}.json'
        if not path.exists():
            candidates = sorted(
                self.output_dir.glob('ss_contracts_*.json'),
                key=lambda x: x.stat().st_mtime, reverse=True
            )
            if not candidates:
                self.logger.error("No contracts file. Run short_swing_contract.py first.")
                return []
            path = candidates[0]
        with open(path) as f:
            return json.load(f)

    def load_open_positions(self) -> Dict[str, ShortSwingPosition]:
        """Load open positions from today's state file."""
        state_path = self.output_dir / 'ss_open_positions.json'
        positions  = {}
        if state_path.exists():
            with open(state_path) as f:
                data = json.load(f)
            for ticker, pos_data in data.items():
                # Reconstruct from dict — create minimal contract dict
                contract = {
                    'ticker':          ticker,
                    'option_symbol':   pos_data.get('option_symbol', ''),
                    'direction':       pos_data.get('direction', 'CALL'),
                    'strike':          pos_data.get('strike', 0),
                    'premium':         pos_data.get('entry_premium', 0),
                    'stop_loss_premium': pos_data.get('stop_premium', 0),
                    'target_premium':  pos_data.get('target_premium', 0),
                    'entry_date':      pos_data.get('entry_date', ''),
                    'hard_exit_date':  pos_data.get('hard_exit_date', ''),
                    'spot_at_select':  0,
                    'crabel_pattern':  pos_data.get('crabel_pattern', ''),
                    'state_hash':      pos_data.get('state_hash', ''),
                }
                pos = ShortSwingPosition(contract)
                pos.state        = pos_data.get('status', 'OPEN')
                pos.trigger_date = pos_data.get('trigger_date')
                if pos.state == 'OPEN':
                    positions[ticker] = pos
        return positions

    def save_open_positions(self):
        state_path = self.output_dir / 'ss_open_positions.json'
        data = {ticker: pos.to_dict() for ticker, pos in self.positions.items()
                if pos.state == 'OPEN'}
        with open(state_path, 'w') as f:
            json.dump(data, f, indent=2)

    def save_outcomes(self, outcomes: List[Dict]):
        today = date.today().strftime('%Y%m%d')
        day_path = self.output_dir / f'ss_outcomes_{today}.csv'
        cumulative_path = self.output_dir / 'ss_cumulative_outcomes.csv'

        new_df = pd.DataFrame(outcomes)
        new_df.to_csv(day_path, index=False)

        if cumulative_path.exists():
            existing = pd.read_csv(cumulative_path)
            combined = pd.concat([existing, new_df], ignore_index=True).drop_duplicates(
                subset=['ticker', 'entry_date', 'option_symbol'])
        else:
            combined = new_df
        combined.to_csv(cumulative_path, index=False)
        self.logger.info(f"Outcomes saved: {day_path}")

    def run_eod_check(self, contracts: List[Dict]) -> Dict:
        """
        Main EOD check. Called once after market close.
        Processes: entry triggers, P&L updates, stop/target checks, hard exits.
        """
        today_str = date.today().isoformat()
        outcomes  = []
        actions   = []

        self.logger.info("=" * 60)
        self.logger.info(f"SHORT-SWING EOD CHECK — {today_str}")
        self.logger.info("=" * 60)

        # ── Load open positions ──────────────────────────────────────────
        self.positions = self.load_open_positions()
        self.logger.info(f"Open positions: {len(self.positions)}")

        # ── Process existing open positions ──────────────────────────────
        for ticker, pos in list(self.positions.items()):
            if pos.state != 'OPEN':
                continue

            candles = self.client.get_daily_candles(ticker, n_days=5)
            current_mid = self.client.get_option_mid(pos.option_symbol)
            if current_mid is None:
                current_mid = pos.entry_premium * 0.9  # Estimate if unavailable

            days_held = pos.days_in_trade()
            self.logger.info(f"\n  {ticker} [{pos.direction}] Day {days_held} | "
                           f"Prem ${current_mid:.2f} (entry ${pos.entry_premium:.2f}) | "
                           f"P&L ${pos.pnl(current_mid):+.2f}")

            # Check hard exit
            if pos.is_past_hard_exit or days_held >= MAX_HOLD_DAYS:
                pos.close(current_mid, f'HARD_EXIT_DAY_{days_held}')
                outcomes.append(pos.to_dict())
                actions.append(f"PAPER EXIT {ticker}: Day {days_held} hard exit | "
                              f"P&L ${pos.pnl(current_mid):+.2f}")
                self.logger.info(f"  ⏰ PAPER EXIT {ticker}: Hard exit Day {days_held} | "
                               f"P&L ${pos.pnl(current_mid):+.2f}")
                continue

            # Check target hit
            if current_mid >= pos.target_premium:
                pos.close(current_mid, 'TARGET_HIT')
                outcomes.append(pos.to_dict())
                actions.append(f"PAPER EXIT {ticker}: TARGET HIT ${current_mid:.2f} | "
                              f"P&L ${pos.pnl(current_mid):+.2f}")
                self.logger.info(f"  🎯 PAPER EXIT {ticker}: Target hit ${current_mid:.2f} | "
                               f"P&L ${pos.pnl(current_mid):+.2f}")
                continue

            # Check stop
            if current_mid <= pos.stop_premium:
                pos.close(current_mid, 'STOP_30PCT')
                outcomes.append(pos.to_dict())
                actions.append(f"PAPER EXIT {ticker}: STOP ${current_mid:.2f} | "
                              f"P&L ${pos.pnl(current_mid):+.2f}")
                self.logger.info(f"  🛑 PAPER EXIT {ticker}: Stop hit ${current_mid:.2f} | "
                               f"P&L ${pos.pnl(current_mid):+.2f}")
                continue

            # Day 2 adverse close check
            if days_held == 2 and not candles.empty:
                adverse, adv_reason = check_adverse_close(candles, pos.direction, pos.entry_price)
                if adverse:
                    pos.close(current_mid, f'ADVERSE_CLOSE_D2: {adv_reason}')
                    outcomes.append(pos.to_dict())
                    self.logger.info(f"  ⚠️ PAPER EXIT {ticker}: Adverse D2 close | "
                                   f"P&L ${pos.pnl(current_mid):+.2f}")
                    continue

            # Position still valid — update log
            self.logger.info(f"  ✓ HOLD {ticker}: Day {days_held} | "
                           f"vs stop ${pos.stop_premium:.2f} / target ${pos.target_premium:.2f}")

        # ── Check for new entry triggers (today's contracts) ──────────────
        self.logger.info(f"\nChecking entry triggers for {len(contracts)} contract(s)...")

        for contract in contracts:
            ticker = contract['ticker']
            if ticker in self.positions and self.positions[ticker].state == 'OPEN':
                self.logger.info(f"  {ticker}: already in position — skipping")
                continue

            direction = contract['direction']
            candles   = self.client.get_daily_candles(ticker, n_days=3)

            if candles.empty:
                self.logger.warning(f"  {ticker}: no candle data")
                continue

            triggered, reason = check_crabel_trigger(candles, direction)
            self.logger.info(f"  {ticker}: {reason}")

            if triggered:
                # Entry triggered — create position
                actual_mid = self.client.get_option_mid(contract['option_symbol'])
                if not actual_mid or actual_mid <= 0:
                    actual_mid = float(contract.get('premium', 0))

                pos = ShortSwingPosition(contract)
                pos.open_position(today_str, actual_mid)
                self.positions[ticker] = pos

                action = (
                    f"PAPER ENTER {ticker} {direction} ${contract['strike']:.2f} | "
                    f"Premium ${actual_mid:.2f} | {contract.get('crabel_pattern','')} | "
                    f"Hard exit: {pos.hard_exit_date}"
                )
                actions.append(action)
                self.logger.info(f"\n  🚨 {action}")

        # ── Save state ────────────────────────────────────────────────────
        self.save_open_positions()
        if outcomes:
            self.save_outcomes(outcomes)

        # ── Summary ───────────────────────────────────────────────────────
        open_count   = sum(1 for p in self.positions.values() if p.state == 'OPEN')
        closed_today = len(outcomes)
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"EOD SUMMARY: {open_count} open | {closed_today} closed today")
        for action in actions:
            self.logger.info(f"  → {action}")
        self.logger.info('='*60)

        return {
            'date':         today_str,
            'open':         open_count,
            'closed_today': closed_today,
            'outcomes':     outcomes,
            'actions':      actions,
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Short-Swing EOD Monitor')
    parser.add_argument('--api-key',  type=str, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    monitor   = ShortSwingMonitor(api_key=args.api_key, verbose=args.verbose)
    contracts = monitor.load_contracts()
    monitor.run_eod_check(contracts)
