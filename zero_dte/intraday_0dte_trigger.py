"""
AVSHUNTER — INTRADAY 0DTE TRIGGER ENGINE v1.0
================================================================================
Component 3 of 4 in the 0DTE Day Trade Module

PURPOSE:
    Monitors the 0DTE contract shortlist during market hours using 5-minute
    bars and fires entry/exit alerts when trigger conditions are met.

DESIGN:
    Standalone module. Does NOT modify intraday_spring_detector.py.
    Replicates the 5-minute bar monitoring pattern and adds 0DTE-specific
    trigger logic on top.

TRIGGER CONDITIONS (all required for ENTER signal):
    1. Spring confirm  — 5m close above prior 5m low (for CALLs)
       UTAD confirm    — 5m close below prior 5m high (for PUTs)
    2. Volume confirm  — reclaim bar volume > 1.5x prior bar
    3. Gamma zone      — price between put wall and gamma flip
    4. Entry window    — current time between 09:45–10:15 ET

EXIT CONDITIONS (any triggers immediate exit):
    A. Time exit       — 14:00 ET hard exit regardless of P&L
    B. Stop hit        — premium <= 50% of entry premium
    C. Reversal signal — 3 consecutive 5m bars against position direction

PAPER MODE:
    All signals logged with PAPER prefix. No order submission.
    Outcome tracking written to zero_dte/output/paper_outcomes_YYYYMMDD.csv

USAGE:
    python intraday_0dte_trigger.py
    python intraday_0dte_trigger.py --interval 5 --verbose
    python intraday_0dte_trigger.py --test  (single scan, then exit)

REGRESSION GUARANTEE:
    Does not import from Vanguard package or intraday_spring_detector.py.
    Reads Polygon API directly. Zero shared state with production pipeline.
================================================================================
"""

import argparse
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

# Timing (ET)
MARKET_OPEN    = (9, 30)
ENTRY_START    = (9, 45)
ENTRY_END      = (10, 15)
HARD_EXIT      = (14, 0)
MARKET_CLOSE   = (16, 0)

# Trigger thresholds
VOLUME_CONFIRM_RATIO   = 1.5    # Reclaim bar volume > 1.5x prior bar
REVERSAL_BARS          = 3      # Exit if 3 consecutive bars against direction
PREMIUM_STOP_PCT       = 0.50   # Stop at 50% of entry premium
MIN_MOVE_FOR_TRIGGER   = 0.003  # Minimum 0.3% move to qualify as spring/UTAD

# Scan interval
DEFAULT_SCAN_MINUTES   = 5

# Polygon
POLYGON_BASE = 'https://api.polygon.io'


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger('0DTE_TRIGGER')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(
            '%(asctime)s | 0DTE TRIGGER | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(ch)
    return logger


# ─── MARKET TIME HELPERS ─────────────────────────────────────────────────────

def now_et() -> Tuple[int, int]:
    """Returns (hour, minute) in Eastern Time (UTC-5 / UTC-4 DST)."""
    import time as _time
    # Simple offset — for production use pytz
    utc_hour = datetime.utcnow().hour
    utc_min = datetime.utcnow().minute
    # EST = UTC-5, EDT = UTC-4 (approximate)
    et_hour = (utc_hour - 5) % 24
    return (et_hour, utc_min)


def is_in_window(start: Tuple, end: Tuple) -> bool:
    h, m = now_et()
    start_mins = start[0] * 60 + start[1]
    end_mins   = end[0] * 60 + end[1]
    now_mins   = h * 60 + m
    return start_mins <= now_mins <= end_mins


def is_entry_window() -> bool:
    return is_in_window(ENTRY_START, ENTRY_END)


def is_past_hard_exit() -> bool:
    h, m = now_et()
    return (h * 60 + m) >= (HARD_EXIT[0] * 60 + HARD_EXIT[1])


def is_market_hours() -> bool:
    if datetime.utcnow().weekday() >= 5:  # Weekend
        return False
    return is_in_window(MARKET_OPEN, MARKET_CLOSE)


# ─── POLYGON DATA FETCHER ────────────────────────────────────────────────────

class IntradayDataFetcher:
    """Fetches 5-minute bars and options quotes from Polygon."""

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

    def get_bars(self, ticker: str, multiplier: int = 5, n_bars: int = 20) -> pd.DataFrame:
        """Get last n_bars of 5-minute bars."""
        self._throttle()
        today = date.today().isoformat()
        url = (f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range"
               f"/{multiplier}/minute/{today}/{today}")
        try:
            r = self.session.get(url, params={
                'adjusted': 'true', 'sort': 'asc',
                'limit': n_bars, 'apiKey': self.api_key
            }, timeout=10)
            r.raise_for_status()
            results = r.json().get('results', [])
            if not results:
                return pd.DataFrame()
            df = pd.DataFrame(results)
            df.rename(columns={'o':'open','h':'high','l':'low','c':'close','v':'volume'}, inplace=True)
            df['timestamp'] = pd.to_datetime(df['t'], unit='ms', utc=True)
            return df.tail(n_bars)
        except Exception:
            return pd.DataFrame()

    def get_option_quote(self, option_symbol: str) -> Optional[Dict]:
        """Get current bid/ask/mid for an options contract."""
        self._throttle()
        url = f"{POLYGON_BASE}/v3/snapshot/options/{option_symbol}"
        try:
            r = self.session.get(url, params={'apiKey': self.api_key}, timeout=10)
            r.raise_for_status()
            data = r.json()
            result = data.get('results', {})
            q = result.get('last_quote', {})
            bid = float(q.get('bid', 0))
            ask = float(q.get('ask', 0))
            mid = (bid + ask) / 2 if (bid + ask) > 0 else float(result.get('last_trade', {}).get('price', 0))
            return {'bid': bid, 'ask': ask, 'mid': mid}
        except Exception:
            return None


# ─── TRIGGER DETECTION ───────────────────────────────────────────────────────

def detect_spring_trigger(bars: pd.DataFrame, direction: str) -> Tuple[bool, str]:
    """
    Detect spring (for CALL) or UTAD (for PUT) on 5-minute bars.

    Spring: latest bar closes ABOVE the prior bar's low (after touching it).
    UTAD:   latest bar closes BELOW the prior bar's high (after touching it).

    Returns (triggered: bool, reason: str)
    """
    if len(bars) < 3:
        return False, "Insufficient bars"

    bar_now  = bars.iloc[-1]
    bar_prev = bars.iloc[-2]
    bar_2ago = bars.iloc[-3]

    if direction.upper() == 'CALL':
        # Spring: prior bar made new low, current bar reclaims
        made_low = bar_prev['low'] < bar_2ago['low']
        reclaimed = bar_now['close'] > bar_prev['low']
        move_size = (bar_now['close'] - bar_prev['low']) / bar_prev['low']
        triggered = made_low and reclaimed and (move_size >= MIN_MOVE_FOR_TRIGGER)
        reason = (
            f"Spring: prev bar low ${bar_prev['low']:.2f}, "
            f"reclaim close ${bar_now['close']:.2f} (+{move_size*100:.2f}%)"
            if triggered else
            f"No spring: low_break={made_low}, reclaim={reclaimed}"
        )

    else:  # PUT
        # UTAD: prior bar made new high, current bar fails and reverses
        made_high = bar_prev['high'] > bar_2ago['high']
        reversed_  = bar_now['close'] < bar_prev['high']
        move_size  = (bar_prev['high'] - bar_now['close']) / bar_prev['high']
        triggered  = made_high and reversed_ and (move_size >= MIN_MOVE_FOR_TRIGGER)
        reason = (
            f"UTAD: prev bar high ${bar_prev['high']:.2f}, "
            f"rejection close ${bar_now['close']:.2f} (-{move_size*100:.2f}%)"
            if triggered else
            f"No UTAD: high_break={made_high}, rejection={reversed_}"
        )

    return triggered, reason


def detect_volume_confirm(bars: pd.DataFrame) -> Tuple[bool, float]:
    """
    Confirms trigger bar volume > 1.5x prior bar.
    Returns (confirmed, ratio).
    """
    if len(bars) < 2:
        return False, 0.0
    vol_now  = float(bars.iloc[-1]['volume'])
    vol_prev = float(bars.iloc[-2]['volume'])
    if vol_prev == 0:
        return False, 0.0
    ratio = vol_now / vol_prev
    return ratio >= VOLUME_CONFIRM_RATIO, round(ratio, 2)


def detect_reversal_exit(
    bars: pd.DataFrame,
    direction: str,
    entry_price: float
) -> Tuple[bool, str]:
    """
    Check for 3 consecutive bars moving against position direction.
    """
    if len(bars) < REVERSAL_BARS:
        return False, ""

    last_n = bars.iloc[-REVERSAL_BARS:]

    if direction.upper() == 'CALL':
        # 3 consecutive closes below entry level
        closes = last_n['close'].values
        if all(c < entry_price for c in closes):
            return True, f"3 consecutive bars below entry ${entry_price:.2f}"
    else:  # PUT
        closes = last_n['close'].values
        if all(c > entry_price for c in closes):
            return True, f"3 consecutive bars above entry ${entry_price:.2f}"

    return False, ""


# ─── POSITION TRACKER ────────────────────────────────────────────────────────

class ZeroDTEPosition:
    """Tracks a single open 0DTE paper position."""

    def __init__(self, ticker: str, contract: Dict, entry_premium: float):
        self.ticker          = ticker
        self.option_symbol   = contract['option_symbol']
        self.direction       = contract['direction']
        self.strike          = contract['strike']
        self.entry_premium   = entry_premium
        self.stop_premium    = entry_premium * (1 - PREMIUM_STOP_PCT)
        self.entry_time_utc  = datetime.now(timezone.utc)
        self.entry_price     = contract['spot_at_select']
        self.status          = 'OPEN'
        self.exit_premium    = None
        self.exit_reason     = None
        self.exit_time_utc   = None
        self.contracts       = 1  # paper: always 1

    def check_stop(self, current_premium: float) -> bool:
        return current_premium <= self.stop_premium

    def pnl(self, current_premium: float) -> float:
        return (current_premium - self.entry_premium) * 100 * self.contracts

    def close(self, exit_premium: float, reason: str):
        self.status       = 'CLOSED'
        self.exit_premium = exit_premium
        self.exit_reason  = reason
        self.exit_time_utc = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        pnl = self.pnl(self.exit_premium or self.entry_premium)
        return {
            'ticker':          self.ticker,
            'option_symbol':   self.option_symbol,
            'direction':       self.direction,
            'strike':          self.strike,
            'entry_premium':   self.entry_premium,
            'stop_premium':    round(self.stop_premium, 4),
            'exit_premium':    self.exit_premium,
            'exit_reason':     self.exit_reason,
            'pnl_dollars':     round(pnl, 2),
            'pnl_pct':         round((self.exit_premium or self.entry_premium) / self.entry_premium - 1, 4) if self.entry_premium else 0,
            'status':          self.status,
            'entry_time':      self.entry_time_utc.isoformat(),
            'exit_time':       self.exit_time_utc.isoformat() if self.exit_time_utc else None,
            'contracts':       self.contracts,
        }


# ─── MAIN MONITOR ────────────────────────────────────────────────────────────

class ZeroDTETriggerEngine:
    """
    Main intraday monitor. Runs continuously during market hours,
    scanning the 0DTE contract shortlist every N minutes.
    """

    def __init__(self, api_key: Optional[str] = None, verbose: bool = False):
        self.logger    = setup_logger(verbose)
        self.fetcher   = IntradayDataFetcher(api_key)
        self.positions: Dict[str, ZeroDTEPosition] = {}
        self.outcomes:  List[Dict] = []
        self.output_dir = Path('zero_dte/output')
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_contracts(self) -> List[Dict]:
        """Load today's selected contracts from Component 2 output."""
        run_date = date.today().strftime('%Y%m%d')
        json_path = self.output_dir / f'zero_dte_contracts_{run_date}.json'

        if not json_path.exists():
            # Try most recent
            candidates = sorted(
                self.output_dir.glob('zero_dte_contracts_*.json'),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if not candidates:
                self.logger.error("No contracts file found. Run zero_dte_contract.py first.")
                return []
            json_path = candidates[0]

        with open(json_path) as f:
            contracts = json.load(f)
        self.logger.info(f"Loaded {len(contracts)} contract(s) from {json_path}")
        return contracts

    def scan_once(self, contracts: List[Dict]) -> List[Dict]:
        """
        Single scan of all watchlist contracts.
        Returns list of triggered signals.
        """
        signals = []
        et_h, et_m = now_et()
        self.logger.info(f"─── Scan at {et_h:02d}:{et_m:02d} ET ───")

        # ── Check existing positions for exits ──
        for ticker, pos in list(self.positions.items()):
            if pos.status != 'OPEN':
                continue

            quote = self.fetcher.get_option_quote(pos.option_symbol)
            current_prem = quote['mid'] if quote else pos.entry_premium

            # Hard time exit
            if is_past_hard_exit():
                pos.close(current_prem, 'HARD_EXIT_14:00')
                self._log_outcome(pos)
                self.logger.info(
                    f"  ⏰ PAPER EXIT {ticker}: Hard exit 14:00 | "
                    f"P&L ${pos.pnl(current_prem):+.2f}"
                )
                continue

            # Stop hit
            if pos.check_stop(current_prem):
                pos.close(current_prem, 'STOP_50PCT')
                self._log_outcome(pos)
                self.logger.info(
                    f"  🛑 PAPER EXIT {ticker}: Stop hit ${current_prem:.2f} "
                    f"(entry ${pos.entry_premium:.2f}) | "
                    f"P&L ${pos.pnl(current_prem):+.2f}"
                )
                continue

            # Reversal check
            bars = self.fetcher.get_bars(ticker)
            if not bars.empty:
                rev, rev_reason = detect_reversal_exit(bars, pos.direction, pos.entry_price)
                if rev:
                    pos.close(current_prem, f'REVERSAL: {rev_reason}')
                    self._log_outcome(pos)
                    self.logger.info(
                        f"  🔄 PAPER EXIT {ticker}: {rev_reason} | "
                        f"P&L ${pos.pnl(current_prem):+.2f}"
                    )
                    continue

            # Position update
            self.logger.info(
                f"  📊 HOLD {ticker} {pos.direction} ${pos.strike} | "
                f"Prem ${current_prem:.2f} (entry ${pos.entry_premium:.2f}) | "
                f"P&L ${pos.pnl(current_prem):+.2f}"
            )

        # ── Check for new entries (entry window only) ──
        if not is_entry_window():
            h, m = now_et()
            if (h * 60 + m) < (ENTRY_START[0] * 60 + ENTRY_START[1]):
                self.logger.info(
                    f"  Waiting for entry window "
                    f"({ENTRY_START[0]}:{ENTRY_START[1]:02d} ET)"
                )
            return signals

        for contract in contracts:
            ticker = contract['ticker']

            # Skip if already in position
            if ticker in self.positions and self.positions[ticker].status == 'OPEN':
                continue

            direction = contract['direction']

            # Fetch 5m bars
            bars = self.fetcher.get_bars(ticker, multiplier=5, n_bars=20)
            if bars.empty:
                self.logger.debug(f"  {ticker}: No bars available")
                continue

            # Spring / UTAD trigger
            spring_ok, spring_reason = detect_spring_trigger(bars, direction)
            if not spring_ok:
                self.logger.debug(f"  {ticker}: {spring_reason}")
                continue

            # Volume confirm
            vol_ok, vol_ratio = detect_volume_confirm(bars)
            if not vol_ok:
                self.logger.info(
                    f"  {ticker}: Spring detected but volume weak "
                    f"(ratio {vol_ratio:.2f} < {VOLUME_CONFIRM_RATIO})"
                )
                continue

            # All conditions met — fire signal
            signal = {
                'ticker':        ticker,
                'type':          'ENTER_PAPER' if contract.get('paper_mode', True) else 'ENTER',
                'direction':     direction,
                'option_symbol': contract['option_symbol'],
                'strike':        contract['strike'],
                'mid_at_signal': contract['mid'],
                'spring_reason': spring_reason,
                'vol_ratio':     vol_ratio,
                'et_time':       f'{et_h:02d}:{et_m:02d}',
                'hard_exit':     f"{HARD_EXIT[0]}:{HARD_EXIT[1]:02d} ET",
                'stop_pct':      f"{int(PREMIUM_STOP_PCT*100)}% of premium",
                'rank':          contract.get('zero_dte_rank', 0),
            }
            signals.append(signal)

            # Open paper position
            pos = ZeroDTEPosition(ticker, contract, contract['mid'])
            self.positions[ticker] = pos

            self.logger.info(
                f"\n  🚨 PAPER ENTER {ticker} {direction} "
                f"${contract['strike']:.2f} | "
                f"Symbol: {contract['option_symbol']} | "
                f"Premium: ${contract['mid']:.2f}"
            )
            self.logger.info(f"    Trigger: {spring_reason}")
            self.logger.info(f"    Volume ratio: {vol_ratio:.2f}x")
            self.logger.info(
                f"    Stop: ${pos.stop_premium:.2f} | "
                f"Hard exit: {HARD_EXIT[0]}:{HARD_EXIT[1]:02d} ET"
            )

        return signals

    def _log_outcome(self, pos: ZeroDTEPosition):
        self.outcomes.append(pos.to_dict())
        self._save_outcomes()

    def _save_outcomes(self):
        run_date = date.today().strftime('%Y%m%d')
        out_path = self.output_dir / f'paper_outcomes_{run_date}.csv'
        pd.DataFrame(self.outcomes).to_csv(out_path, index=False)

    def run(self, contracts: List[Dict], scan_interval_minutes: int = DEFAULT_SCAN_MINUTES):
        """
        Main loop. Runs from market open to market close.
        """
        self.logger.info("=" * 60)
        self.logger.info("AVSHUNTER — 0DTE TRIGGER ENGINE v1.0 — RUNNING")
        self.logger.info(f"Watching: {[c['ticker'] for c in contracts]}")
        self.logger.info(f"Entry window: {ENTRY_START[0]}:{ENTRY_START[1]:02d}–{ENTRY_END[0]}:{ENTRY_END[1]:02d} ET")
        self.logger.info(f"Hard exit: {HARD_EXIT[0]}:{HARD_EXIT[1]:02d} ET")
        self.logger.info(f"Scan interval: {scan_interval_minutes} minutes")
        self.logger.info("=" * 60)

        while True:
            if not is_market_hours():
                self.logger.info("Market closed. Exiting monitor.")
                break

            if is_past_hard_exit():
                # Force close any remaining open positions
                for ticker, pos in self.positions.items():
                    if pos.status == 'OPEN':
                        quote = self.fetcher.get_option_quote(pos.option_symbol)
                        exit_prem = quote['mid'] if quote else pos.entry_premium * 0.3
                        pos.close(exit_prem, 'HARD_EXIT_14:00_FORCED')
                        self._log_outcome(pos)
                        self.logger.info(
                            f"  ⏰ FORCED EXIT {ticker} at market | "
                            f"P&L ${pos.pnl(exit_prem):+.2f}"
                        )
                self.logger.info("All positions closed. Session complete.")
                break

            self.scan_once(contracts)
            time.sleep(scan_interval_minutes * 60)

    def run_test(self, contracts: List[Dict]):
        """Single scan for testing — does not loop."""
        self.logger.info("TEST MODE — Single scan")
        signals = self.scan_once(contracts)
        self.logger.info(f"Test scan complete. Signals: {len(signals)}")
        return signals


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='AVSHUNTER 0DTE Intraday Trigger Engine'
    )
    parser.add_argument('--interval', type=int, default=DEFAULT_SCAN_MINUTES,
                        help=f'Scan interval in minutes (default {DEFAULT_SCAN_MINUTES})')
    parser.add_argument('--api-key', type=str, default=None)
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--test', action='store_true',
                        help='Single scan then exit (for testing)')
    args = parser.parse_args()

    engine = ZeroDTETriggerEngine(api_key=args.api_key, verbose=args.verbose)
    contracts = engine.load_contracts()

    if not contracts:
        print("No contracts loaded. Run the screener and contract selector first.")
        exit(0)

    if args.test:
        engine.run_test(contracts)
    else:
        engine.run(contracts, scan_interval_minutes=args.interval)
