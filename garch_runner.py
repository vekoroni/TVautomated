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

from layer3_forward_variance import (
    FORECAST_FAILED,
    METHOD_NO_FORECAST,
    ForwardVarianceResult,
    compute_forward_variance,
)

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
    try:
        from canonical_data.history_bridge import read_canonical_history
        canonical = read_canonical_history(ticker, bars=bars)
        if canonical is not None and not canonical.empty:
            return canonical
    except Exception as error:
        log.debug(f'[{ticker}] CDS-2 canonical read unavailable: {error}')

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
        df = df.tail(bars).reset_index(drop=True)
        from canonical_data.history_bridge import (
            observe_shadow_history,
            write_through_fetched_history,
        )
        write_through_fetched_history(
            ticker,
            df,
            provider='POLYGON',
            source_kind='GARCH_RUNNER',
            source_run_id=os.getenv('AVSHUNTER_RUN_ID') or None,
        )
        observe_shadow_history(ticker, df, consumer='GARCH')
        return df
    except Exception as e:
        log.debug(f'[{ticker}] fetch error: {e}')
        return None


# ── Macro regime ───────────────────────────────────────────────────────────────

#: Display value when no macro regime could be read. The regime is display-only (CLAUDE.md rule 6);
#: a missing one is said, never invented as TRANSITIONAL (tests/test_layer3_volatility_leftovers.py M1).
MACRO_REGIME_MISSING = 'MACRO_REGIME_MISSING'


def _load_regime(base_dir: Path) -> str:
    """Read regime_state from macro_intelligence_latest.json (display only).

    The canonical field is 'regime_state' (macro_contract_v1_0).
    Legacy aliases 'active_regime' and 'regime' are checked as fallbacks
    for backward compatibility. No file, no readable file or no regime field gives
    MACRO_REGIME_MISSING.
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
                    or MACRO_REGIME_MISSING
                )
            except Exception as exc:
                log.warning('[GARCH] macro file unreadable (%s: %s): %s', type(exc).__name__, exc, p)
    return MACRO_REGIME_MISSING


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

#: Status labels say which model actually produced the forecast (R6). HAR_RV is never
#: reported as GARCH; anything that produced no forecast is FAIL (fix 17 Sep 2026,
#: tests/test_layer3_volatility_integrity.py V4).
FORECAST_METHOD_LABELS = ('HAR_RV', 'GARCH', 'EWMA_FALLBACK', 'ATR_PROXY')
STATUS_FAIL = 'FAIL'
STATUS_LABELS = FORECAST_METHOD_LABELS + (STATUS_FAIL,)


def _format_status_counts(counts: Dict[str, int]) -> str:
    return ' '.join(f'{label}={counts.get(label, 0)}' for label in STATUS_LABELS)


def _failed_row(ticker: str, error: str, regime: str) -> dict:
    """Explicit FORECAST_FAILED row: every numeric field missing, the reason in l3_error."""
    return ForwardVarianceResult(
        ticker=ticker, forward_realised_vol=None, vol_forecast_confidence=None,
        expected_move_1_5d=None, expected_move_6_10d=None, expected_move_11_20d=None,
        iv_tailwind_score=None, jump_risk_flag=None, method=METHOD_NO_FORECAST,
        error=error, forecast_state=FORECAST_FAILED,
        macro_regime_display='' if regime is None else str(regime),
    ).to_dict()


def _process_one_ticker(args: tuple) -> tuple:
    """Process a single ticker. Returns (row_dict, status) where status is the model that
    produced the forecast (HAR_RV / GARCH / EWMA_FALLBACK / ATR_PROXY) or FAIL.

    Every requested ticker gets a row: no price data gives an explicit MISSING_PRICE_HISTORY row
    and an unexpected error a FORECAST_FAILED row with the reason, numeric fields missing — never
    an absent row that merges as an unexplained NaN (R1; tests/test_layer3_volatility_leftovers.py V6).
    """
    ticker, iv, regime = args
    try:
        ohlcv = _fetch_ohlcv(ticker, PRICE_BARS)
        time.sleep(RATE_SLEEP)
        if ohlcv is None or ohlcv.empty:
            log.debug(f'[{ticker}] No price data — explicit MISSING_PRICE_HISTORY row')
            ohlcv = pd.DataFrame()
        result   = compute_forward_variance(ticker, ohlcv, implied_vol=iv, regime=regime)
        row_dict = _audit_garch_result(result.to_dict())
        method   = row_dict.get('l3_method', '')
        status   = method if method in FORECAST_METHOD_LABELS else STATUS_FAIL
        return row_dict, status
    except Exception as e:
        log.warning(f'[{ticker}] Unexpected error: {type(e).__name__}: {e}')
        return _failed_row(ticker, f'{type(e).__name__}: {e}', regime), STATUS_FAIL


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
    log.info(f'[GARCH] Regime={regime} (display only) | IV map: {len(iv_map)} tickers')

    # Batch process — 2 workers (each sleeps RATE_SLEEP between Polygon calls)
    results = []
    counts: Dict[str, int] = {label: 0 for label in STATUS_LABELS}

    log.info('[GARCH] Running with 2 workers (ThreadPoolExecutor)')
    # Missing IV is passed as None (explicit IV_MISSING in layer 3), never 0.0.
    # The regime is passed for display only; layer 3 never uses it in a value.
    worker_args = [(t, iv_map.get(t), regime) for t in tickers]

    with ThreadPoolExecutor(max_workers=2) as executor:
        for i, (row_dict, status) in enumerate(
            executor.map(_process_one_ticker, worker_args), 1
        ):
            if row_dict is not None:
                results.append(row_dict)
            counts[status if status in counts else STATUS_FAIL] += 1
            if i % 50 == 0:
                log.info(f'[GARCH] Progress: {i}/{len(tickers)} | {_format_status_counts(counts)}')

    # Every requested ticker has a row (explicit state when no forecast); written before any
    # failure is raised so downstream merges see the reason rather than an absent row.
    out_df = pd.DataFrame(results)
    out_df.to_csv(out_path, index=False)

    n_forecasts = sum(counts.get(label, 0) for label in FORECAST_METHOD_LABELS)
    log.info(
        f'[GARCH] Complete: {len(results)} tickers | '
        f'{_format_status_counts(counts)} | '
        f'Output: {out_path}'
    )
    if n_forecasts == 0:
        log.error('[GARCH] No forecasts produced — check price history access; rows carry the missing states')
        raise RuntimeError('GARCH batch produced zero forecasts')
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
