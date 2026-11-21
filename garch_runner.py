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
from datetime import date
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

def _fetch_ohlcv(ticker: str, bars: int = PRICE_BARS, as_of: Optional[date] = None) -> Optional[pd.DataFrame]:
    """
    Fetch daily OHLCV from Polygon /v2/aggs/ticker/{ticker}/range/1/day.
    Returns DataFrame sorted oldest-first, or None on failure.

    VOL-02 (ACK 21 Nov 2026): `as_of` is the run's evidence session. When it is known, no bar after
    it is read, from the canonical store or from the provider, so a replay cannot see the future.
    """
    try:
        from canonical_data.history_bridge import read_canonical_history
        if as_of is not None:
            canonical = read_canonical_history(ticker, bars=bars, end_date=as_of, reference_date=as_of)
        else:
            canonical = read_canonical_history(ticker, bars=bars)
        if canonical is not None and not canonical.empty:
            return canonical
    except Exception as error:
        log.debug(f'[{ticker}] CDS-2 canonical read unavailable: {error}')

    if not POLYGON_API_KEY:
        log.warning(f'[{ticker}] POLYGON_API_KEY not set — cannot fetch price history')
        return None

    from datetime import timedelta
    _end       = as_of or date.today()
    end_date   = _end.strftime('%Y-%m-%d')
    start_date = (_end - timedelta(days=int(bars * 1.5))).strftime('%Y-%m-%d')

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

def _layer3_iv_observation(row: dict) -> dict:
    """Accept only a labelled 30-calendar-day ATM benchmark for comparison."""
    source = row.get("atm_iv_30d_source")
    as_of = row.get("atm_iv_30d_as_of")
    units = {"ANNUALISED_FRACTION": 1.0, "ANNUALISED_PERCENT": 100.0}
    divisor = units.get(row.get("atm_iv_30d_unit"))
    state = "IV_MISSING"
    iv = None
    if pd.notna(row.get("atm_iv_30d")):
        state = "IV_DATA_DEFECT"
        if divisor and isinstance(source, str) and source.strip() and isinstance(as_of, str):
            try:
                date.fromisoformat(as_of)
                candidate = float(row["atm_iv_30d"]) / divisor
                if 0.03 <= candidate <= 3.0:
                    iv = candidate
                    state = "IV_MEASURED"
            except (ValueError, TypeError):
                pass
    return {
        "l3_atm_iv_30d": iv,
        "l3_contract_iv_reported": row.get("contract_iv"),
        "l3_iv_basis": "ATM_30_CALENDAR_DAYS" if iv is not None else None,
        "l3_iv_source": source if iv is not None else None,
        "l3_iv_as_of": as_of if iv is not None else None,
        "l3_iv_unit": "ANNUALISED_FRACTION" if iv is not None else None,
        "l3_iv_input_state": state,
        # VOL-03: why the 30-day benchmark is missing, as published by Options Intelligence.
        "l3_iv_benchmark_state": row.get("atm_iv_30d_state") if pd.notna(row.get("atm_iv_30d_state")) else None,
        "l3_iv_benchmark_reason": row.get("atm_iv_30d_reason") if pd.notna(row.get("atm_iv_30d_reason")) else None,
    }


def _build_iv_map(run_id: str, runs_dir: Path) -> Dict[str, dict]:
    oi_path = runs_dir / run_id / "options" / f"options_intelligence_{run_id}.csv"
    if not oi_path.exists():
        log.warning(f"options_intelligence CSV not found: {oi_path}")
        return {}
    try:
        rows = pd.read_csv(oi_path).to_dict("records")
    except (OSError, ValueError) as error:
        log.warning(f"IV map build failed: {error}")
        return {}
    return {
        row["ticker"].strip().upper(): _layer3_iv_observation(row)
        for row in rows if isinstance(row.get("ticker"), str) and row["ticker"].strip()
    }


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
    ticker, iv, regime = args[:3]
    as_of = args[3] if len(args) > 3 else None
    iv_observation = iv if isinstance(iv, dict) else None
    if iv_observation is None and iv is None:
        # No Options row yet (the forecast can run before Options): missing is stated, never blank.
        iv_observation = _layer3_iv_observation({})
    if iv_observation is not None:
        iv = iv_observation["l3_atm_iv_30d"]
    try:
        # The session cutoff is passed only when the run has one, so a run with no metadata keeps the
        # earlier call exactly.
        ohlcv = _fetch_ohlcv(ticker, PRICE_BARS, as_of=as_of) if as_of is not None else _fetch_ohlcv(ticker, PRICE_BARS)
        time.sleep(RATE_SLEEP)
        if ohlcv is None or ohlcv.empty:
            log.debug(f'[{ticker}] No price data — explicit MISSING_PRICE_HISTORY row')
            ohlcv = pd.DataFrame()
        result   = compute_forward_variance(ticker, ohlcv, implied_vol=iv, regime=regime)
        row_dict = _audit_garch_result(result.to_dict())
        if iv_observation is not None:
            row_dict.update(iv_observation)
        method   = row_dict.get('l3_method', '')
        status   = method if method in FORECAST_METHOD_LABELS else STATUS_FAIL
        return row_dict, status
    except Exception as e:
        log.warning(f'[{ticker}] Unexpected error: {type(e).__name__}: {e}')
        return _failed_row(ticker, f'{type(e).__name__}: {e}', regime), STATUS_FAIL


# ── Main batch runner ──────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_evidence_session(run_id: str) -> tuple:
    """The run's evidence session from its own metadata: (date or None, state)."""
    meta_path = RUNS_DIR / run_id / "run_meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None, "RUN_METADATA_UNAVAILABLE"
    raw = (meta.get("dynamic_plan") or {}).get("last_completed_session")
    try:
        return date.fromisoformat(str(raw)[:10]), "FROM_RUN_METADATA"
    except (TypeError, ValueError):
        return None, "SESSION_NOT_IN_RUN_METADATA"


def run_garch_batch(
    run_id:         str,
    superbrain_csv: Optional[Path] = None,
    output_dir:     Optional[Path] = None,
    *,
    worklist_csv:   Optional[Path] = None,
) -> Path:
    """
    Run the volatility forecast for every ticker on the run's worklist.
    Returns path to garch_forecasts_{run_id}.csv.

    VOL-02 (ACK 21 Nov 2026): the worklist is the run's pinned Discovery candidates file, the same
    file Options Intelligence reads, so the forecast needs neither the SuperBrain file nor the
    Options file and can run before Options. There is no fallback to another list: a missing
    worklist stops with its name. `superbrain_csv` is kept as an explicit legacy list and is
    labelled as such in the receipt.
    """
    if worklist_csv is not None:
        worklist, worklist_kind = Path(worklist_csv), "EXPLICIT_WORKLIST"
    elif superbrain_csv is not None:
        worklist, worklist_kind = Path(superbrain_csv), "EXPLICIT_LEGACY_LIST"
    else:
        worklist = RUNS_DIR / run_id / 'discovery' / f'discovery_candidates_ultimate_{run_id}.csv'
        worklist_kind = "DISCOVERY_CANDIDATES"
    if not worklist.exists():
        raise FileNotFoundError(f'Forecast worklist not found ({worklist_kind}): {worklist}')
    superbrain_csv = worklist
    evidence_session, evidence_session_state = _run_evidence_session(run_id)

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
    worker_args = [(t, iv_map.get(t), regime, evidence_session) for t in tickers]

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
    # What this forecast actually consumed, written before any failure is raised.
    receipt = {
        "run_id": run_id,
        "worklist_kind": worklist_kind,
        "worklist_path": str(worklist),
        "worklist_sha256": _sha256_file(worklist),
        "worklist_ticker_count": len(tickers),
        "forecast_row_count": len(results),
        "evidence_session": evidence_session.isoformat() if evidence_session else None,
        "evidence_session_state": evidence_session_state,
        "iv_benchmark_rows_available": sum(
            1 for value in iv_map.values() if (value or {}).get("l3_iv_input_state") == "IV_MEASURED"),
        "status_counts": dict(counts),
    }
    (output_dir / f'garch_forecast_receipt_{run_id}.json').write_text(
        json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")

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
    parser.add_argument('--worklist_csv',   type=Path, default=None,
                        help='Ticker worklist; default is the run pinned Discovery candidates file')
    parser.add_argument('--output_dir',     type=Path, default=None)
    args = parser.parse_args()

    try:
        out = run_garch_batch(
            run_id         = args.run_id,
            superbrain_csv = args.superbrain_csv,
            output_dir     = args.output_dir,
            worklist_csv   = args.worklist_csv,
        )
        log.info(f'[GARCH] Output written: {out}')
        sys.exit(0)
    except Exception as e:
        log.error(f'[GARCH] Fatal: {e}')
        sys.exit(1)
