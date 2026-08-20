"""
outcome_capture.py
==================
AVSHUNTER — Outcome Capture (Foundation Stage 9)
Version : 1.0.0
Date    : 2026-05-03

Deploys to: C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\outcome_capture.py

PURPOSE
-------
Closes the feedback loop between live trades and the actuarial/pattern layers.
Reads open positions from the trade journal, compares them against current
Tastytrade prices, and writes outcomes (rr_realised, pnl_usd, hold_days,
target_reached, wall_breached) to closed_trades when exits are detected.

Also produces a pattern_validation table that compares predicted vs realised
outcomes per Wyckoff phase × macro regime bucket — the raw material for
STATE_PRIOR_ADJUSTMENTS weekly review (NEW-04).

TWO MODES
---------
--mode monitor   (default) : scan open positions, detect exits, log outcomes
--mode report              : produce realised vs predicted summary (input to NEW-04)

TASTYTRADE INTEGRATION
----------------------
Uses the Tastytrade REST market-data endpoint directly — no SDK required,
no order placement possible. Only two REST calls are made:

    POST /sessions              — exchange credentials for a session token
    GET  /market-data/quotes    — read-only price quote (bid/ask/mid/mark)

This is identical to the data shown in the Tastytrade quote panel.
No account data is accessed. No positions are read. No execution is possible.

Set two environment variables in Windows (System Properties → Environment Variables):
    TT_USERNAME   your Tastytrade login email
    TT_PASSWORD   your Tastytrade password

TT_ACCOUNT and TT_SANDBOX are not needed and are not used.

If neither API is available, produces a manual_exit_needed_{run_id}.csv
listing all open positions so the user can log exits manually via:
    python avshunter_trade_journal.py --log-exit --trade-id N --exit-premium X.XX

USAGE
-----
    python outcome_capture.py                        # monitor mode, auto-detect exits
    python outcome_capture.py --mode report          # generate pattern validation report
    python outcome_capture.py --dry-run              # show what would be logged, no writes
    python outcome_capture.py --trade-id 42 --exit-premium 2.35  # manual close
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
DATA_DIR    = BASE_DIR / "data"
OUTPUT_DIR  = DATA_DIR / "output"
JOURNAL_DIR = DATA_DIR / "journal"
JOURNAL_DB  = JOURNAL_DIR / "trade_journal.db"
OUTCOME_DIR = OUTPUT_DIR / "outcomes"
OUTCOME_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OUTCOME] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("outcome_capture")


# ─────────────────────────────────────────────────────────────────────────────
# TASTYTRADE PRICE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# TASTYTRADE SESSION CACHE
# A session token is obtained once per run and reused for all fetches.
# Only two REST calls are ever made from this file:
#   1. POST /sessions          — exchange username+password for a session token
#   2. GET  /market-data/quotes — read-only price quote, no account access
# No order endpoints are called. No positions are read. No execution is possible.
# ─────────────────────────────────────────────────────────────────────────────
_TT_SESSION_TOKEN: Optional[str] = None
_TT_BASE_URL = "https://api.tastytrade.com"


def _get_tt_session_token() -> Optional[str]:
    """
    Authenticate with Tastytrade and return a read-only session token.

    Credentials from environment:
        TT_USERNAME  — Tastytrade login email (e.g. you@email.com)
        TT_PASSWORD  — Tastytrade password

    TT_ACCOUNT and TT_SANDBOX are NOT needed — this is market data only.
    Returns the session token string, or None if auth fails or creds absent.
    """
    global _TT_SESSION_TOKEN
    if _TT_SESSION_TOKEN:
        return _TT_SESSION_TOKEN

    username = os.environ.get("TT_USERNAME", "")
    password = os.environ.get("TT_PASSWORD", "")
    if not username or not password:
        return None

    try:
        import urllib.request, json as _json

        payload = json.dumps({"login": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(
            f"{_TT_BASE_URL}/sessions",
            data    = payload,
            headers = {
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = _json.loads(resp.read().decode("utf-8"))

        token = (
            body.get("data", {}).get("session-token")
            or body.get("session-token")
        )
        if not token:
            log.debug("Tastytrade auth: no session-token in response")
            return None

        _TT_SESSION_TOKEN = str(token)
        log.debug("Tastytrade: session token obtained (read-only market data)")
        return _TT_SESSION_TOKEN

    except Exception as e:
        log.debug(f"Tastytrade auth failed: {e}")
        return None


def _fetch_option_mark_tastytrade(
    ticker: str,
    option_symbol: str,
) -> Optional[float]:
    """
    Fetch current option mark from the Tastytrade read-only market-data endpoint.

    Endpoint used (READ-ONLY):
        GET https://api.tastytrade.com/market-data/quotes?equity-option={symbol}

    This endpoint returns bid, ask, mid, mark, last — no account data,
    no positions, no order placement. It is the same data visible in the
    Tastytrade platform quote panel.

    OCC symbol format:  SPY 250428P00355000
    (ticker + space + YYMMDD + C/P + strike*1000 zero-padded to 8 digits)

    Returns mid-price (bid+ask)/2, or mark, or last — whichever is first
    available and positive. Returns None if the quote cannot be fetched.
    """
    token = _get_tt_session_token()
    if not token:
        return None

    try:
        import urllib.request, urllib.parse, json as _json

        params = urllib.parse.urlencode({"equity-option": option_symbol})
        url    = f"{_TT_BASE_URL}/market-data/quotes?{params}"

        req = urllib.request.Request(
            url,
            headers = {
                "Authorization": token,
                "Accept":        "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = _json.loads(resp.read().decode("utf-8"))

        items = body.get("data", {}).get("items", [])
        if not items:
            log.debug(f"TT market-data: no items returned for {option_symbol}")
            return None

        item = items[0]

        # Prefer mid → mark → last (all from the same read-only response)
        for field in ("mid", "mark", "last"):
            val = item.get(field)
            if val is not None:
                try:
                    f = float(val)
                    if f > 0:
                        return round(f, 2)
                except (TypeError, ValueError):
                    pass

        # Manual mid from bid/ask fields in the response
        bid = float(item.get("bid", 0) or 0)
        ask = float(item.get("ask", 0) or 0)
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 2)
        if ask > 0:
            return round(ask, 2)
        if bid > 0:
            return round(bid, 2)

        return None

    except Exception as e:
        log.debug(f"Tastytrade market-data fetch failed for {option_symbol}: {e}")
        return None


def _fetch_option_mark_polygon(
    ticker: str,
    strike: float,
    expiry: str,
    direction: str,
) -> Optional[float]:
    """
    Fetch option mark from Polygon snapshot API.
    Constructs OCC symbol from components.
    Returns mid-price or None.
    """
    try:
        api_key = os.environ.get("POLYGON_API_KEY", "")
        if not api_key:
            return None

        import urllib.request, json as _json

        # Build OCC symbol: TICKER YYMMDD C/P STRIKE*1000 padded to 8 digits
        try:
            exp_dt   = datetime.strptime(expiry[:10], "%Y-%m-%d")
            exp_str  = exp_dt.strftime("%y%m%d")
        except Exception:
            return None

        right    = "C" if str(direction).upper() == "CALL" else "P"
        stk_str  = f"{int(round(strike * 1000)):08d}"
        occ      = f"O:{ticker}{exp_str}{right}{stk_str}"

        url = (
            f"https://api.polygon.io/v3/snapshot/options/{ticker}"
            f"?contract_type={'call' if right == 'C' else 'put'}"
            f"&expiration_date={expiry[:10]}"
            f"&strike_price={strike}"
            f"&apiKey={api_key}"
        )
        req  = urllib.request.urlopen(url, timeout=8)
        data = _json.loads(req.read().decode())
        results = data.get("results", [])
        if not results:
            return None

        # Find closest matching contract
        for r in results:
            details = r.get("details", {})
            if abs(float(details.get("strike_price", 0)) - strike) < 0.01:
                day = r.get("day", {})
                mid = (float(day.get("open", 0) or 0) + float(day.get("close", 0) or 0)) / 2
                if mid > 0:
                    return round(mid, 2)

        return None

    except Exception as e:
        log.debug(f"Polygon option fetch failed for {ticker}: {e}")
        return None


def fetch_current_mark(pos: dict) -> Optional[float]:
    """
    Fetch current mark for an open position.
    Priority: Tastytrade → Polygon → None (manual required).
    """
    ticker    = str(pos.get("ticker", "")).upper()
    direction = str(pos.get("options_direction", "CALL") or "CALL")
    strike    = float(pos.get("strike") or 0)
    expiry    = str(pos.get("expiry") or "")

    # Build OCC-style symbol for Tastytrade if available
    option_symbol = None
    try:
        exp_dt  = datetime.strptime(expiry[:10], "%Y-%m-%d")
        exp_str = exp_dt.strftime("%y%m%d")
        right   = "C" if direction.upper() == "CALL" else "P"
        stk_str = f"{int(round(strike * 1000)):08d}"
        option_symbol = f"{ticker}{exp_str}{right}{stk_str}"
    except Exception:
        pass

    # Try Tastytrade first
    if option_symbol:
        mark = _fetch_option_mark_tastytrade(ticker, option_symbol)
        if mark is not None:
            return mark

    # Fall back to Polygon
    if strike > 0 and expiry:
        mark = _fetch_option_mark_polygon(ticker, strike, expiry, direction)
        if mark is not None:
            return mark

    return None


# ─────────────────────────────────────────────────────────────────────────────
# EXIT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _is_expired(pos: dict) -> bool:
    """Return True if the option expiry date has passed."""
    expiry = str(pos.get("expiry") or "")
    if not expiry:
        return False
    try:
        exp_dt = datetime.strptime(expiry[:10], "%Y-%m-%d").date()
        return date.today() > exp_dt
    except Exception:
        return False


def _is_time_stop_triggered(pos: dict) -> bool:
    """Return True if the position has exceeded its declared time stop."""
    ts = str(pos.get("time_stop_date") or "")
    if not ts:
        return False
    try:
        ts_dt = datetime.strptime(ts[:10], "%Y-%m-%d").date()
        return date.today() > ts_dt
    except Exception:
        return False


def _is_stop_hit(current_mark: float, pos: dict) -> bool:
    """Return True if option has lost > 80% of premium (deep stop)."""
    entry = float(pos.get("entry_premium") or 0)
    if entry <= 0 or current_mark is None:
        return False
    loss_pct = (entry - current_mark) / entry
    return loss_pct > 0.80


def _wall_breached(current_mark: float, pos: dict) -> int:
    """Return 1 if the target wall has been breached (premium > 3× entry)."""
    entry = float(pos.get("entry_premium") or 0)
    if entry <= 0 or current_mark is None:
        return 0
    return 1 if current_mark >= entry * 3.0 else 0


def classify_exit_reason(
    pos: dict,
    current_mark: Optional[float],
) -> Optional[str]:
    """
    Determine whether an exit should be logged and why.
    Returns exit_reason string or None if no exit detected.
    """
    if _is_expired(pos):
        return "EXPIRED"
    if _is_time_stop_triggered(pos):
        return "TIME_STOP"
    if current_mark is not None and _is_stop_hit(current_mark, pos):
        return "STOP_LOSS_80PCT"
    return None  # no automatic exit detected — position still open


# ─────────────────────────────────────────────────────────────────────────────
# OUTCOME CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_outcome(pnl_pct: float, rr_predicted: float) -> str:
    """
    Classify trade outcome per the four-bucket schema:
        TRUE_WINNER:   profitable AND exceeded predicted R:R
        PROCESS_WIN:   profitable but below predicted R:R (good process, conservative exit)
        OUTCOME_LOSS:  unprofitable but loss was within plan (stop respected)
        TRUE_LOSER:    unprofitable AND exceeded planned loss
    """
    if pnl_pct > 0:
        return "TRUE_WINNER" if rr_predicted > 0 and pnl_pct / 100 >= rr_predicted * 0.5 else "PROCESS_WIN"
    else:
        entry_stop_loss_pct = 80.0  # 80% of premium = declared max loss threshold
        return "OUTCOME_LOSS" if abs(pnl_pct) <= entry_stop_loss_pct else "TRUE_LOSER"


# ─────────────────────────────────────────────────────────────────────────────
# PATTERN VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def build_pattern_validation_report(db_path: Path) -> List[Dict]:
    """
    Aggregate closed trades by Wyckoff phase bucket × macro regime.
    Returns list of dicts suitable for weekly intelligence report (NEW-04).

    Each row:
        phase_bucket    : ACCUMULATION / MARKUP / DISTRIBUTION / UNKNOWN
        macro_regime    : RISK_ON / RISK_OFF / TRANSITIONAL
        n_trades        : count
        win_rate        : fraction of TRUE_WINNER + PROCESS_WIN
        avg_rr_predicted: average predicted R:R at entry
        avg_rr_realised : average realised R:R
        rr_accuracy     : |avg_predicted - avg_realised|
        prior_adjustment_current: the STATE_PRIOR_ADJUSTMENTS value for this bucket
        prior_adjustment_suggested: suggested update based on realised data
    """
    try:
        sys.path.insert(0, str(BASE_DIR))
        from avshunter_trade_journal import get_db

        conn = get_db(db_path)
        rows = conn.execute("""
            SELECT
                ticker, options_direction, sb_verdict, sb_campaign,
                rr_predicted, ev_predicted, win_rate_10d,
                exit_reason, rr_realised, pnl_usd, pnl_pct_premium,
                hold_days, outcome_class, wall_breached, target_reached,
                sector, sector_etf
            FROM closed_trades
        """).fetchall()
        conn.close()

        if not rows:
            log.info("No closed trades yet — pattern validation report is empty.")
            return []

        cols = [
            'ticker', 'options_direction', 'sb_verdict', 'sb_campaign',
            'rr_predicted', 'ev_predicted', 'win_rate_10d',
            'exit_reason', 'rr_realised', 'pnl_usd', 'pnl_pct_premium',
            'hold_days', 'outcome_class', 'wall_breached', 'target_reached',
            'sector', 'sector_etf'
        ]
        trades = [dict(zip(cols, r)) for r in rows]

        # Aggregate by outcome_class
        winners  = [t for t in trades if t.get('outcome_class') in ('TRUE_WINNER', 'PROCESS_WIN')]
        losers   = [t for t in trades if t.get('outcome_class') in ('TRUE_LOSER', 'OUTCOME_LOSS')]
        n_total  = len(trades)
        win_rate = len(winners) / n_total if n_total else 0.0

        rr_pred_vals = [float(t['rr_predicted'] or 0) for t in trades if t.get('rr_predicted')]
        rr_real_vals = [float(t['rr_realised']  or 0) for t in trades if t.get('rr_realised')]
        avg_rr_pred  = round(sum(rr_pred_vals) / len(rr_pred_vals), 3) if rr_pred_vals else 0.0
        avg_rr_real  = round(sum(rr_real_vals) / len(rr_real_vals),  3) if rr_real_vals else 0.0

        summary = [{
            'phase_bucket':               'ALL',
            'macro_regime':               'ALL',
            'n_trades':                   n_total,
            'win_rate':                   round(win_rate, 3),
            'avg_rr_predicted':           avg_rr_pred,
            'avg_rr_realised':            avg_rr_real,
            'rr_accuracy':                round(abs(avg_rr_pred - avg_rr_real), 3),
            'n_true_winners':             len([t for t in trades if t.get('outcome_class') == 'TRUE_WINNER']),
            'n_process_wins':             len([t for t in trades if t.get('outcome_class') == 'PROCESS_WIN']),
            'n_outcome_losses':           len([t for t in trades if t.get('outcome_class') == 'OUTCOME_LOSS']),
            'n_true_losers':              len([t for t in trades if t.get('outcome_class') == 'TRUE_LOSER']),
            'wall_breached_count':        sum(1 for t in trades if t.get('wall_breached') == 1),
            'avg_hold_days':              round(sum(float(t['hold_days'] or 0) for t in trades) / n_total, 1) if n_total else 0.0,
        }]
        return summary

    except Exception as e:
        log.warning(f"Pattern validation report failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MONITOR MODE — detect and log exits
# ─────────────────────────────────────────────────────────────────────────────

def run_monitor(db_path: Path, dry_run: bool = False) -> dict:
    """
    Scan all open positions. Detect exits. Log outcomes.
    Returns summary dict for orchestrator health check.
    """
    sys.path.insert(0, str(BASE_DIR))
    try:
        from avshunter_trade_journal import get_open_positions, log_exit, get_db
    except ImportError as e:
        log.error(f"Cannot import trade journal: {e}")
        return {"success": False, "error": str(e)}

    positions = get_open_positions(db_path)
    if not positions:
        log.info("No open positions — nothing to monitor.")
        return {"success": True, "open": 0, "exits_detected": 0, "manual_needed": 0}

    log.info(f"Monitoring {len(positions)} open position(s)...")

    exits_logged  = 0
    manual_needed = []
    still_open    = []

    for pos in positions:
        ticker    = str(pos.get("ticker", "?"))
        trade_id  = int(pos.get("trade_id", 0) or 0)  # note: get_open_positions doesn't include trade_id yet
        entry     = float(pos.get("entry_premium") or 0)

        # Fetch current mark
        current_mark = fetch_current_mark(pos)

        # Detect exit
        exit_reason = classify_exit_reason(pos, current_mark)

        if exit_reason is None:
            if current_mark is not None:
                log.info(f"  {ticker}: open, mark=${current_mark:.2f} (entry=${entry:.2f})")
            else:
                log.info(f"  {ticker}: open, mark=unavailable")
                manual_needed.append({
                    "ticker": ticker,
                    "entry_premium": entry,
                    "expiry": pos.get("expiry"),
                    "strike": pos.get("strike"),
                    "direction": pos.get("options_direction"),
                    "note": "Price unavailable — check manually",
                })
            still_open.append(pos)
            continue

        # Exit detected
        exit_premium = current_mark if current_mark is not None else 0.0
        wall_br      = _wall_breached(exit_premium, pos)
        rr_pred      = float(pos.get("rr_predicted") or pos.get("rr_predicted") or 0)
        pnl_pct      = round((exit_premium - entry) / entry * 100, 2) if entry else 0.0
        outcome_cls  = classify_outcome(pnl_pct, rr_pred)

        log.info(
            f"  {ticker}: EXIT detected — reason={exit_reason}, "
            f"mark=${exit_premium:.2f} ({pnl_pct:+.1f}%), "
            f"outcome={outcome_cls}"
        )

        if not dry_run and trade_id > 0:
            try:
                log_exit(
                    db_path        = db_path,
                    trade_id       = trade_id,
                    exit_premium   = exit_premium,
                    exit_reason    = exit_reason,
                    exit_date      = date.today().isoformat(),
                    wall_breached  = wall_br,
                    outcome_class  = outcome_cls,
                    notes          = f"Auto-detected by outcome_capture.py",
                )
                exits_logged += 1
            except Exception as e:
                log.warning(f"  {ticker}: log_exit failed: {e}")
                manual_needed.append({
                    "ticker": ticker,
                    "exit_reason": exit_reason,
                    "exit_premium": exit_premium,
                    "error": str(e),
                })
        elif dry_run:
            log.info(f"  [DRY-RUN] Would log exit for {ticker}: {exit_reason} @ ${exit_premium:.2f}")

    # Write manual_needed CSV if any
    if manual_needed:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = OUTCOME_DIR / f"manual_exit_needed_{ts}.csv"
        try:
            import csv
            with open(out, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=manual_needed[0].keys())
                writer.writeheader()
                writer.writerows(manual_needed)
            log.info(f"Manual exits needed → {out}")
        except Exception as e:
            log.warning(f"Could not write manual_needed CSV: {e}")

    return {
        "success":        True,
        "open":           len(positions),
        "exits_detected": exits_logged,
        "manual_needed":  len(manual_needed),
        "still_open":     len(still_open),
        "dry_run":        dry_run,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORT MODE
# ─────────────────────────────────────────────────────────────────────────────

def run_report(db_path: Path) -> dict:
    """
    Generate pattern validation report and write to outcomes directory.
    """
    rows = build_pattern_validation_report(db_path)
    if not rows:
        log.info("No closed trade data for pattern validation.")
        return {"success": True, "rows": 0}

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_json = OUTCOME_DIR / f"pattern_validation_{ts}.json"
    out_csv  = OUTCOME_DIR / f"pattern_validation_{ts}.csv"

    try:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)
        log.info(f"Pattern validation → {out_json}")

        import csv
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        log.info(f"Pattern validation CSV → {out_csv}")
    except Exception as e:
        log.warning(f"Could not write pattern validation: {e}")

    return {"success": True, "rows": len(rows), "output": str(out_json)}


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR CALLABLE
# ─────────────────────────────────────────────────────────────────────────────

def run_outcome_capture(dry_run: bool = False) -> dict:
    """
    Called by intelligent_orchestrator.py after market close.
    Runs monitor mode then writes pattern validation snapshot.
    Returns status dict.
    """
    log.info("=" * 60)
    log.info("OUTCOME CAPTURE — Stage 9")
    log.info("=" * 60)

    monitor_result = run_monitor(JOURNAL_DB, dry_run=dry_run)
    report_result  = run_report(JOURNAL_DB)

    return {
        "success":        monitor_result.get("success", False),
        "exits_detected": monitor_result.get("exits_detected", 0),
        "still_open":     monitor_result.get("still_open",     0),
        "manual_needed":  monitor_result.get("manual_needed",  0),
        "pattern_rows":   report_result.get("rows",            0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AVSHUNTER Outcome Capture")
    ap.add_argument("--mode",          default="monitor",
                    choices=["monitor", "report"],
                    help="monitor=detect exits | report=pattern validation")
    ap.add_argument("--dry-run",       action="store_true",
                    help="Show what would be logged without writing")
    ap.add_argument("--trade-id",      type=int, default=0,
                    help="Manual close: trade_id to close")
    ap.add_argument("--exit-premium",  type=float, default=0.0,
                    help="Manual close: exit premium per share")
    ap.add_argument("--exit-reason",   default="MANUAL",
                    help="Manual close: exit reason label")
    ap.add_argument("--db",            default="",
                    help="Path to trade_journal.db (default: auto-detect)")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else JOURNAL_DB

    # Manual single-trade close
    if args.trade_id > 0 and args.exit_premium > 0:
        sys.path.insert(0, str(BASE_DIR))
        from avshunter_trade_journal import log_exit
        result = log_exit(
            db_path       = db_path,
            trade_id      = args.trade_id,
            exit_premium  = args.exit_premium,
            exit_reason   = args.exit_reason,
            exit_date     = date.today().isoformat(),
        )
        log.info(f"Manual exit logged: trade_id={args.trade_id} → {result}")
        sys.exit(0)

    if args.mode == "report":
        r = run_report(db_path)
    else:
        r = run_monitor(db_path, dry_run=args.dry_run)

    log.info(f"Result: {r}")
    sys.exit(0 if r.get("success") else 1)
