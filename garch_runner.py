"""
garch_runner.py
===============
Q-OMEGA Layer 3 — Nightly GARCH Batch Runner

Purpose:
    Runs layer3_forward_variance.compute_forward_variance() for every
    ticker in the current run's superbrain_enriched CSV.
    Writes output to data/output/runs/{run_id}/qomega/garch_forecasts_{run_id}.csv

Position in pipeline:
    Called by intelligent_orchestrator.py as Phase 10a — after SuperBrain
    (Phase 8d) and Wall Break Scorer (Phase 8e), before Q-OMEGA engine.

    Sequence:
        Phase 8d  SuperBrain
        Phase 8e  Wall Break Scorer
        Phase 9   EIL
        Phase 10a GARCH Runner  ← THIS FILE
        Phase 10b Q-OMEGA Engine (layer4_mispricing.py)
        Phase 10c Archive

Usage:
    python garch_runner.py <run_id> [--superbrain_csv path] [--output_dir path]

    If --superbrain_csv not provided, resolves from:
        data/output/runs/{run_id}/superbrain/superbrain_enriched_{run_id}.csv

Data sourcing:
    Price history: fetched from Polygon API (same key as rest of pipeline).
    IV for tailwind score: read from options_intelligence_{run_id}.csv.
    Regime: read from macro_intelligence_latest.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import requests

# ── Path resolution ────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
QOMEGA_DIR = BASE_DIR / 'qomega'
sys.path.insert(0, str(BASE_DIR))

from layer3_forward_variance import compute_forward_variance

logging.basicConfig(
    level   = logging.INFO,
    format  = '%(asctime)s - %(levelname)s - %(message)s',
    handlers= [logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger('garch_runner')

# ── Config ─────────────────────────────────────────────────────────────────────
POLYGON_API_KEY  = os.getenv('POLYGON_API_KEY', '').strip()
DATA_DIR         = BASE_DIR / 'data'
RUNS_DIR         = DATA_DIR / 'output' / 'runs'
PRICE_BARS       = 252    # trading days of history to fetch
POLYGON_TIMEOUT  = 20
RATE_SLEEP       = 0.15   # seconds between Polygon calls (stay under rate limit)


# ── Polygon price fetch ────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, bars: int = PRICE_BARS) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV from Polygon /v2/aggs/ticker/{ticker}/range/1/day.
    Returns DataFrame sorted oldest-first, or None on failure.
    """
    if not POLYGON_API_KEY:
        log.warning(f'[{ticker}] POLYGON_API_KEY not set — cannot fetch price history')
        return None

    from datetime import date, timedelta
    end_date   = date.today().strftime('%Y-%m-%d')
    start_date = (date.today() - timedelta(days=int(bars * 1.5))).strftime('%Y-%m-%d')

    url    = f'https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}'
    params = {'adjusted': 'true', 'sort': 'asc', 'limit': 500}
    headers = {'Authorization': f'Bearer {POLYGON_API_KEY}'}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=POLYGON_TIMEOUT)
        if r.status_code == 429:
            time.sleep(2.0)
            r = requests.get(url, params=params, headers=headers, timeout=POLYGON_TIMEOUT)
        if not r.ok:
            log.debug(f'[{ticker}] Polygon {r.status_code}')
            return None
        data = r.json().get('results', [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df = df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low',
                                 'c': 'close', 'v': 'volume', 't': 'timestamp'})
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].sort_values('date')
        return df.tail(bars).reset_index(drop=True)
    except Exception as e:
        log.debug(f'[{ticker}] fetch error: {e}')
        return None


# ── Macro regime ───────────────────────────────────────────────────────────────

def _load_regime(base_dir: Path) -> str:
    """Read regime_state from macro_intelligence_latest.json.

    The canonical field is 'regime_state' (macro_contract_v1_0).
    Legacy aliases 'active_regime' and 'regime' are checked as fallbacks
    for backward compatibility.
    """
    candidates = [
        # Canonical dropbox location (written by build_macro_json.py)
        base_dir / 'dropbox' / 'macro' / 'macro_intelligence_latest.json',
        # Pipeline data copy (written by build_macro_json.py copy step)
        base_dir / 'data' / 'macro' / 'macro_intelligence_latest.json',
        # Legacy root-level fallback
        base_dir / 'macro_intelligence_latest.json',
        base_dir / 'data' / 'macro_intelligence_latest.json',
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, encoding='utf-8') as f:
                    data = json.load(f)
                # regime_state is the v1_0 contract field; fall back to legacy names
                return str(
                    data.get('regime_state')
                    or data.get('active_regime')
                    or data.get('regime')
                    or 'TRANSITIONAL'
                )
            except Exception:
                pass
    return 'TRANSITIONAL'


# ── IV lookup ──────────────────────────────────────────────────────────────────

def _build_iv_map(run_id: str, runs_dir: Path) -> Dict[str, float]:
    """
    Build ticker → ATM IV map from options_intelligence CSV.
    IV is read from the 'implied_vol' or 'iv_rank' field.
    Returns decimal annualised vol (e.g. 0.28 for 28%).
    """
    oi_path = runs_dir / run_id / 'options' / f'options_intelligence_{run_id}.csv'
    if not oi_path.exists():
        log.warning(f'options_intelligence CSV not found: {oi_path}')
        return {}
    try:
        df = pd.read_csv(oi_path)
        iv_map = {}
        for _, row in df.iterrows():
            ticker = str(row.get('ticker', '')).strip().upper()
            if not ticker:
                continue
            # Prefer actual IV over IV rank
            iv = row.get('implied_vol') or row.get('contract_iv')
            if iv and float(iv) > 0:
                iv_val = float(iv)
                # Normalise: if > 5 assume it's in percent not decimal
                if iv_val > 5:
                    iv_val /= 100.0
                iv_map[ticker] = iv_val
        return iv_map
    except Exception as e:
        log.warning(f'IV map build failed: {e}')
        return {}


# ── GARCH result audit ────────────────────────────────────────────────────────
# FIX RC-7 CORRECTED (2026-04-16):
#
# ROOT CAUSE (confirmed by reading layer3_forward_variance.py):
# The layer3 module uses HAR-RV as its PRIMARY forecast method, not GARCH(1,1).
# HAR-RV fits OLS regression: RV = a + b1*RV(1d) + b5*RV(5d) + b22*RV(22d)
# The OLS coefficients b1 and (b5+b22) were stored as result['alpha']/result['beta']
# and then written to l3_garch_alpha/l3_garch_beta in the CSV.
#
# HAR-RV OLS coefficients CAN be negative — this is mathematically valid and
# expected when short-term RV is mean-reverting. It does NOT indicate a problem.
# The ann_vol forecast and expected_move fields are computed correctly from
# the OLS forecast, independent of coefficient sign.
#
# The layer3_forward_variance.py fix (applied simultaneously):
#   - _har_rv_forecast() now returns 'har_b1'/'har_b5_b22' keys (not 'alpha'/'beta')
#   - compute_forward_variance() sets method='HAR_RV' and leaves garch_alpha/beta=None
#   - garch_alpha/beta are only populated when EGARCH or GARCH(1,1) actually ran
#
# With that fix in place, l3_garch_alpha/l3_garch_beta will be None for HAR_RV rows
# and no false validity alarms will occur. This function now just provides an audit
# log confirming which method ran — it no longer mutates any values.
#
# PREVIOUS INCORRECT BEHAVIOUR (now removed):
# The prior sanitiser replaced CORRECT HAR-RV expected_moves with INFERIOR EWMA
# estimates whenever alpha or beta were negative. This made forecasts LESS accurate.

def _audit_garch_result(row_dict: dict) -> dict:
    """
    Audit-only: log which forecasting method ran for this ticker.
    Does NOT mutate any values — expected_moves and ann_vol are always correct.

    With the layer3_forward_variance.py fix applied:
      HAR_RV rows:        l3_garch_alpha=None, l3_garch_beta=None  (correct)
      GARCH/EGARCH rows:  l3_garch_alpha>=0,   l3_garch_beta>=0    (valid by construction)
      EWMA_FALLBACK rows: l3_garch_alpha=None, l3_garch_beta=None  (correct)
    """
    ticker = row_dict.get('ticker', '?')
    method = row_dict.get('l3_method', 'UNKNOWN')
    alpha  = row_dict.get('l3_garch_alpha')
    beta   = row_dict.get('l3_garch_beta')

    if method == 'HAR_RV':
        # Primary path — HAR-RV OLS. Alpha/beta will be None (correct).
        log.debug(f'[{ticker}] HAR_RV forecast — expected_moves valid, no GARCH params')
    elif method == 'GARCH' and alpha is not None and beta is not None:
        # True GARCH/EGARCH — parameters should satisfy stationarity by construction
        # (layer3 validates before accepting). Log a warning if somehow violated.
        try:
            a, b = float(alpha), float(beta)
            if not (a >= 0.0 and b >= 0.0 and (a + b) < 1.0):
                log.warning(
                    f'[{ticker}] GARCH path returned invalid params: '
                    f'alpha={a:.4f} beta={b:.4f} — check layer3 GARCH validation'
                )
        except (TypeError, ValueError):
            pass
    elif method == 'EWMA_FALLBACK':
        log.debug(f'[{ticker}] EWMA fallback — insufficient bars for HAR-RV')
    elif method == 'ATR_PROXY':
        log.debug(f'[{ticker}] ATR proxy — minimal price history')
    else:
        log.debug(f'[{ticker}] method={method}')

    return row_dict   # always return unchanged


# ── Per-ticker worker (called by ThreadPoolExecutor) ──────────────────────────

def _process_one_ticker(args: tuple) -> tuple:
    """Process a single ticker. Returns (row_dict_or_None, status_str)."""
    ticker, iv, regime = args
    try:
        ohlcv = _fetch_ohlcv(ticker, PRICE_BARS)
        time.sleep(RATE_SLEEP)
        if ohlcv is None or ohlcv.empty:
            log.debug(f'[{ticker}] No price data — skipping')
            return None, 'fail'
        result   = compute_forward_variance(ticker, ohlcv, implied_vol=iv, regime=regime)
        row_dict = _audit_garch_result(result.to_dict())
        method   = row_dict.get('l3_method', '')
        if method in ('HAR_RV', 'GARCH'):
            status = 'ok'
        elif method in ('EWMA_FALLBACK', 'ATR_PROXY'):
            status = 'warn'
        elif result.error:
            status = 'fail'
        else:
            status = 'warn'
        return row_dict, status
    except Exception as e:
        log.warning(f'[{ticker}] Unexpected error: {e}')
        return None, 'fail'


# ── Main batch runner ──────────────────────────────────────────────────────────

def run_garch_batch(
    run_id:         str,
    superbrain_csv: Optional[Path] = None,
    output_dir:     Optional[Path] = None,
) -> Path:
    """
    Run GARCH forecast for all tickers in superbrain_enriched CSV.
    Returns path to garch_forecasts_{run_id}.csv.
    """
    # Resolve superbrain CSV
    if superbrain_csv is None:
        superbrain_csv = RUNS_DIR / run_id / 'superbrain' / f'superbrain_enriched_{run_id}.csv'
    if not superbrain_csv.exists():
        raise FileNotFoundError(f'SuperBrain CSV not found: {superbrain_csv}')

    # Resolve output dir
    if output_dir is None:
        output_dir = RUNS_DIR / run_id / 'qomega'
    output_dir.mkdir(parents=True, exist_ok=True)

    out_path = output_dir / f'garch_forecasts_{run_id}.csv'

    # Load tickers
    sb_df = pd.read_csv(superbrain_csv)
    tickers = sb_df['ticker'].dropna().str.upper().str.strip().unique().tolist()
    log.info(f'[GARCH] {len(tickers)} tickers to process from {superbrain_csv.name}')

    # Load supporting data
    regime = _load_regime(BASE_DIR)
    iv_map = _build_iv_map(run_id, RUNS_DIR)
    log.info(f'[GARCH] Regime={regime} | IV map: {len(iv_map)} tickers')

    # Batch process — 2 workers (each sleeps RATE_SLEEP between Polygon calls)
    results = []
    ok = warn = fail = 0

    log.info('[GARCH] Running with 2 workers (ThreadPoolExecutor)')
    worker_args = [(t, iv_map.get(t, 0.0), regime) for t in tickers]

    with ThreadPoolExecutor(max_workers=2) as executor:
        for i, (row_dict, status) in enumerate(
            executor.map(_process_one_ticker, worker_args), 1
        ):
            if row_dict is not None:
                results.append(row_dict)
            if status == 'ok':
                ok += 1
            elif status == 'warn':
                warn += 1
            else:
                fail += 1
            if i % 50 == 0:
                log.info(f'[GARCH] Progress: {i}/{len(tickers)} | OK={ok} EWMA={warn} FAIL={fail}')

    if not results:
        log.error('[GARCH] No results produced — check Polygon API key and data access')
        raise RuntimeError('GARCH batch produced zero results')

    out_df = pd.DataFrame(results)
    out_df.to_csv(out_path, index=False)

    log.info(
        f'[GARCH] Complete: {len(results)} tickers | '
        f'GARCH={ok} EWMA={warn} FAIL={fail} | '
        f'Output: {out_path}'
    )
    return out_path


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AVSHUNTER Q-OMEGA GARCH Runner')
    parser.add_argument('run_id',           help='Pipeline run ID (e.g. 20260408_143500)')
    parser.add_argument('--superbrain_csv', type=Path, default=None)
    parser.add_argument('--output_dir',     type=Path, default=None)
    args = parser.parse_args()

    try:
        out = run_garch_batch(
            run_id         = args.run_id,
            superbrain_csv = args.superbrain_csv,
            output_dir     = args.output_dir,
        )
        log.info(f'[GARCH] Output written: {out}')
        sys.exit(0)
    except Exception as e:
        log.error(f'[GARCH] Fatal: {e}')
        sys.exit(1)
