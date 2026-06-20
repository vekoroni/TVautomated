"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              AVSHUNTER — TRADE JOURNAL                                       ║
║              Layer 7 · Post-Intelligence-Lab · Closed-Loop Feedback          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Purpose : Logs every live trade entry and exit. Auto-populates all signal   ║
║            fields from the run dossier at entry time. At exit, computes      ║
║            realised R:R, P&L, and outcome flags. After every 10 closed       ║
║            trades, generates a calibration report comparing predicted vs      ║
║            realised metrics. Feeds back to CT Gate VARIANCE_SCALAR review.   ║
║                                                                              ║
║  Storage : SQLite — trade_journal.db (single file, zero dependencies)        ║
║            Default location: C:/Users/ACKVerissimo/AVSHUNTER-Intelligence/   ║
║                              data/journal\trade_journal.db                   ║
║                                                                              ║
║  ZERO IMPACT on existing pipeline outputs. Read-only consumer.               ║
║  Does not modify any existing CSV or JSON. Writes only to its own DB.        ║
║                                                                              ║
║  Usage (CLI):                                                                ║
║    python avshunter_trade_journal.py log-entry --ticker T                    ║
║         --run-id 20260305_092339 --premium 0.57 --contracts 1                ║
║                                                                              ║
║    python avshunter_trade_journal.py log-exit --trade-id 1                   ║
║         --exit-premium 0.85 --exit-reason "Phase B wall stall"               ║
║                                                                              ║
║    python avshunter_trade_journal.py status                                  ║
║    python avshunter_trade_journal.py calibration                             ║
║    python avshunter_trade_journal.py list-open                               ║
║    python avshunter_trade_journal.py list-closed                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

CHANGELOG
─────────────────────────────────────────────────────────────────────────────
v1.0  2026-03-06  Initial build.
                  Tables: trades (open), closed_trades (exited).
                  Auto-populates signal snapshot from superbrain_enriched CSV
                  and options_intelligence CSV at entry time.
                  Logs CT fields if catastrophe_gate output is present.
                  Calibration report triggers after every 10 closed trades.

v1.1  2026-03-16  Sector and quality gate integration (SuperBrain v2.1.0).
                  NEW: sector, sector_short, sector_etf, industry columns.
                  NEW: sector_regime_sensitivity column.
                  NEW: ev_gate, rr_gate, composite_gate pass/fail columns.
                  NEW: regime_sensitivity_score column (0-100).
                  NEW: Multi-horizon EV/win_rate fields (5d/10d/20d).
                  NEW: sb_horizon_profile, sb_dte_nudge passthrough.
                  NEW: Sector breakdown in calibration report.
                  NEW: EIL verdict auto-population from eil_enriched CSV.
                  NEW: Sector shown in print_status open position table.
                  NEW: Regime sensitivity warnings in print_status.
                  FIX: build_entry_snapshot now searches eil_enriched CSV.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [JOURNAL] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('trade_journal')

# ── Default paths — adjust to match your local AVSHUNTER-Intelligence layout ──
DEFAULT_PIPELINE_ROOT = Path(
    os.environ.get('AVSHUNTER_ROOT',
                   r'C:\Users\ACKVerissimo\AVSHUNTER-Intelligence')
)
DEFAULT_DB_PATH  = DEFAULT_PIPELINE_ROOT / 'data' / 'journal' / 'trade_journal.db'
DEFAULT_RUNS_DIR = DEFAULT_PIPELINE_ROOT / 'runs'

# Common output locations to search when runs_dir is not explicit
_SEARCH_ROOTS = [
    DEFAULT_PIPELINE_ROOT / 'runs',
    DEFAULT_PIPELINE_ROOT / 'data' / 'output' / 'runs',
    DEFAULT_PIPELINE_ROOT / 'output' / 'runs',
    DEFAULT_PIPELINE_ROOT,                         # flat layout fallback
    DEFAULT_PIPELINE_ROOT / 'data' / 'output',    # flat output dir
    Path.cwd(),                                    # current working directory
]


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identity
    ticker              TEXT    NOT NULL,
    run_id              TEXT    NOT NULL,
    entry_date          TEXT    NOT NULL,   -- ISO date YYYY-MM-DD
    entry_time          TEXT,               -- HH:MM
    -- Contract
    options_direction   TEXT,               -- PUT / CALL
    strike              REAL,
    expiry              TEXT,
    dte_at_entry        INTEGER,
    contracts           INTEGER NOT NULL DEFAULT 1,
    entry_premium       REAL    NOT NULL,   -- per share (×100 for contract value)
    entry_contract_value REAL,              -- entry_premium × contracts × 100
    -- Signal snapshot (from superbrain at entry time)
    sb_verdict          TEXT,
    sb_campaign         TEXT,
    sb_conv_score       INTEGER,
    sb_risk_label       TEXT,
    sb_size_pct         INTEGER,
    sb_veto_codes       TEXT,
    rr_predicted        REAL,
    ev_predicted        REAL,
    ivp_at_entry        REAL,
    -- Sector (from clean_universe__with_sector.csv via superbrain v2.1)
    sector              TEXT,
    sector_short        TEXT,
    sector_etf          TEXT,
    industry            TEXT,
    sector_regime_sensitivity TEXT,         -- HIGH / MEDIUM / LOW
    -- Quality gate snapshot (from superbrain v2.1 hard gates)
    ev_gate             TEXT,               -- PASS / FAIL_NEGATIVE_EV
    rr_gate             TEXT,               -- PASS / FAIL_LOW_RR
    composite_gate      TEXT,               -- PASS / FAIL_LOW_COMPOSITE
    regime_sensitivity_score INTEGER,       -- 0-100 macro exposure score
    -- Multi-horizon EV surface (from Vanguard actuarial)
    win_rate_5d         REAL,
    expected_value_5d   REAL,
    win_rate_10d        REAL,
    expected_value_10d  REAL,
    win_rate_20d        REAL,
    expected_value_20d  REAL,
    sharpe_ratio_5d     REAL,
    sharpe_ratio_10d    REAL,
    -- Horizon profile
    sb_horizon_profile  TEXT,               -- BURST / GRIND / STEADY / FLAT
    sb_dte_nudge        TEXT,               -- DTE recommendation from actuarial
    -- EIL snapshot (from execution_intelligence_runner)
    eil_verdict         TEXT,               -- EXECUTE_NOW / EXECUTE_WITH_CAUTION / etc.
    eil_liquidity_grade TEXT,               -- PASS / CAUTION / FAIL
    eil_iv_distortion   TEXT,               -- CLEAN / WATCH / IV_DISTORTED
    eil_gex_flip_proximity TEXT,            -- FAR / APPROACHING / AT_FLIP
    eil_obi_alignment   TEXT,               -- ALIGNED / NEUTRAL / OPPOSED
    eil_poc_timing      TEXT,               -- FAVOURABLE / NEUTRAL / UNFAVOURABLE
    -- Structure
    underlying_price_at_entry  REAL,
    structural_target   REAL,
    breakeven_pct       REAL,
    put_wall            REAL,
    call_wall           REAL,
    theta_drag_pct      REAL,
    -- Dates
    time_stop_date      TEXT,
    checkpoint_date     TEXT,
    -- Greeks snapshot
    vanna_at_entry      REAL,
    charm_at_entry      REAL,
    gamma_flip_conf     REAL,
    gamma_flip_gap_pct  REAL,
    iv_vs_hv_at_entry   REAL,
    gamma_velocity_label TEXT,
    -- CT fields snapshot (populated if catastrophe_gate has run)
    ct_bifurcation_proximity   REAL,
    ct_divergence_set_flag     INTEGER,    -- 0/1
    ct_entry_sheet             TEXT,       -- UPPER / LOWER / UNKNOWN
    ct_stability_coeff         REAL,
    ct_position_size_scalar    REAL,
    ct_data_quality_score      REAL,
    -- Wall Break Score snapshot
    wbs                 REAL,
    wbs_grade           TEXT,
    -- Notes
    entry_notes         TEXT,
    -- Metadata
    created_at          TEXT DEFAULT (datetime('now'))
);
"""

SCHEMA_CLOSED = """
CREATE TABLE IF NOT EXISTS closed_trades (
    trade_id            INTEGER PRIMARY KEY,   -- same ID as trades table
    ticker              TEXT    NOT NULL,
    run_id              TEXT    NOT NULL,
    -- Entry (copied from trades)
    entry_date          TEXT,
    entry_premium       REAL,
    contracts           INTEGER,
    entry_contract_value REAL,
    options_direction   TEXT,
    strike              REAL,
    expiry              TEXT,
    dte_at_entry        INTEGER,
    sb_verdict          TEXT,
    sb_campaign         TEXT,
    sb_conv_score       INTEGER,
    rr_predicted        REAL,
    ev_predicted        REAL,
    structural_target   REAL,
    put_wall            REAL,
    call_wall           REAL,
    underlying_price_at_entry REAL,
    vanna_at_entry      REAL,
    -- Sector (carried from entry)
    sector              TEXT,
    sector_short        TEXT,
    sector_etf          TEXT,
    industry            TEXT,
    sector_regime_sensitivity TEXT,
    regime_sensitivity_score  INTEGER,
    -- Quality gates (carried from entry)
    ev_gate             TEXT,
    rr_gate             TEXT,
    composite_gate      TEXT,
    -- Multi-horizon EV (carried from entry)
    win_rate_5d         REAL,
    expected_value_5d   REAL,
    win_rate_10d        REAL,
    expected_value_10d  REAL,
    win_rate_20d        REAL,
    expected_value_20d  REAL,
    -- EIL verdict (carried from entry)
    eil_verdict         TEXT,
    eil_liquidity_grade TEXT,
    eil_obi_alignment   TEXT,
    -- CT fields
    ct_bifurcation_proximity  REAL,
    ct_divergence_set_flag    INTEGER,
    ct_entry_sheet      TEXT,
    ct_stability_coeff  REAL,
    ct_data_quality_score     REAL,
    wbs                 REAL,
    wbs_grade           TEXT,
    -- Exit
    exit_date           TEXT    NOT NULL,
    exit_time           TEXT,
    exit_premium        REAL    NOT NULL,
    exit_contract_value REAL,
    exit_reason         TEXT,
    -- Computed outcomes
    rr_realised         REAL,
    pnl_usd             REAL,
    pnl_pct_premium     REAL,
    hold_days           INTEGER,
    -- Outcome flags
    wall_breached       INTEGER,
    time_stop_respected INTEGER,
    target_reached      INTEGER,
    -- ML classification (set manually at close)
    outcome_class       TEXT,   -- TRUE_WINNER / TRUE_LOSER / PROCESS_WIN / OUTCOME_LOSS
    -- CT accuracy
    ct_proximity_at_exit REAL,
    ct_prediction_accurate INTEGER,
    -- Notes
    exit_notes          TEXT,
    -- Metadata
    closed_at           TEXT DEFAULT (datetime('now'))
);
"""

SCHEMA_CALIBRATION = """
CREATE TABLE IF NOT EXISTS calibration_reports (
    report_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at        TEXT    NOT NULL,
    trades_analysed     INTEGER,
    -- Win rate
    predicted_win_rate  REAL,
    realised_win_rate   REAL,
    win_rate_accuracy   REAL,              -- |predicted - realised|
    -- R:R
    predicted_rr_avg    REAL,
    realised_rr_avg     REAL,
    rr_accuracy         REAL,
    -- CT
    ct_ev_accuracy      REAL,              -- avg |ct_ev_adjusted - rr_realised|
    ct_divergence_hit_rate REAL,           -- % where divergence flag correctly predicted outcome
    -- Wall
    wall_breach_rate    REAL,              -- % of wall-bound trades that broke through
    wall_breach_rate_probable REAL,        -- same but WBS=PROBABLE signals only
    -- Veto
    veto_hit_rate       REAL,              -- % of trades with vetoes that became losers
    -- VARIANCE_SCALAR recommendation
    variance_scalar_current  REAL,
    variance_scalar_flag     TEXT,         -- OK / REVIEW_UP / REVIEW_DOWN
    report_json         TEXT               -- full detail as JSON
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(SCHEMA_TRADES)
    conn.execute(SCHEMA_CLOSED)
    conn.execute(SCHEMA_CALIBRATION)
    conn.commit()
    # ── Schema migration: add new columns to existing databases ───────────────
    # Safe: ALTER TABLE ADD COLUMN is a no-op if column already exists in SQLite
    # (actually raises OperationalError — we catch and ignore per column)
    _NEW_TRADES_COLS = [
        ('sector',                    'TEXT'),
        ('sector_short',              'TEXT'),
        ('sector_etf',                'TEXT'),
        ('industry',                  'TEXT'),
        ('sector_regime_sensitivity', 'TEXT'),
        ('ev_gate',                   'TEXT'),
        ('rr_gate',                   'TEXT'),
        ('composite_gate',            'TEXT'),
        ('regime_sensitivity_score',  'INTEGER'),
        ('win_rate_5d',               'REAL'),
        ('expected_value_5d',         'REAL'),
        ('win_rate_10d',              'REAL'),
        ('expected_value_10d',        'REAL'),
        ('win_rate_20d',              'REAL'),
        ('expected_value_20d',        'REAL'),
        ('sharpe_ratio_5d',           'REAL'),
        ('sharpe_ratio_10d',          'REAL'),
        ('sb_horizon_profile',        'TEXT'),
        ('sb_dte_nudge',              'TEXT'),
        ('eil_verdict',               'TEXT'),
        ('eil_liquidity_grade',       'TEXT'),
        ('eil_iv_distortion',         'TEXT'),
        ('eil_gex_flip_proximity',    'TEXT'),
        ('eil_obi_alignment',         'TEXT'),
        ('eil_poc_timing',            'TEXT'),
    ]
    _NEW_CLOSED_COLS = [
        ('ml_eligible',               'INTEGER DEFAULT 0'),   # Sprint 4
        ('sector',                    'TEXT'),
        ('sector_short',              'TEXT'),
        ('sector_etf',                'TEXT'),
        ('industry',                  'TEXT'),
        ('sector_regime_sensitivity', 'TEXT'),
        ('regime_sensitivity_score',  'INTEGER'),
        ('ev_gate',                   'TEXT'),
        ('rr_gate',                   'TEXT'),
        ('composite_gate',            'TEXT'),
        ('win_rate_5d',               'REAL'),
        ('expected_value_5d',         'REAL'),
        ('win_rate_10d',              'REAL'),
        ('expected_value_10d',        'REAL'),
        ('win_rate_20d',              'REAL'),
        ('expected_value_20d',        'REAL'),
        ('eil_verdict',               'TEXT'),
        ('eil_liquidity_grade',       'TEXT'),
        ('eil_obi_alignment',         'TEXT'),
        ('outcome_class',             'TEXT'),
    ]
    for col, ctype in _NEW_TRADES_COLS:
        try:
            conn.execute(f'ALTER TABLE trades ADD COLUMN {col} {ctype}')
            conn.commit()
        except sqlite3.OperationalError:
            pass   # column already exists — normal for existing databases
    for col, ctype in _NEW_CLOSED_COLS:
        try:
            conn.execute(f'ALTER TABLE closed_trades ADD COLUMN {col} {ctype}')
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# POSITION LOCK — pipeline integration
# ─────────────────────────────────────────────────────────────────────────────

def get_open_tickers(db_path: Path) -> set:
    """
    Return set of tickers currently in open positions.
    Called by the pipeline to skip re-signalling live trades.
    """
    if not db_path.exists():
        return set()
    try:
        conn = get_db(db_path)
        rows = conn.execute('SELECT ticker FROM trades').fetchall()
        conn.close()
        return {str(r[0]).strip().upper() for r in rows}
    except Exception:
        return set()


def get_open_positions(db_path: Path) -> list:
    """
    TJ-01: Return open positions with contract-level detail.

    Replaces get_open_tickers() for the position lock check so the orchestrator
    can apply intelligent three-branch routing instead of a blunt ticker-level lock:
      (a) same OCC contract → suppress
      (b) same direction + expiry window → ADD_CANDIDATE if profitable
      (c) opposite direction + V2_AT_WALL fired → REVERSAL_CANDIDATE

    Returns list of dicts, one per open position. All columns already exist in
    the trades table — no schema migration required.
    """
    if not db_path.exists():
        return []
    try:
        conn = get_db(db_path)
        rows = conn.execute(
            """SELECT *
               FROM trades
               ORDER BY entry_date DESC, trade_id DESC"""
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def is_position_locked(db_path: Path, ticker: str) -> bool:
    """
    Return True if ticker has an open trade in the journal.
    Use this in SuperBrain or orchestrator to suppress re-signalling.
    """
    return ticker.strip().upper() in get_open_tickers(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL LOOKUP — auto-populate from pipeline CSVs
# ─────────────────────────────────────────────────────────────────────────────

def _find_run_dir(runs_dir: Path, run_id: str) -> Optional[Path]:
    """Locate the run directory."""
    direct = runs_dir / run_id
    if direct.exists():
        return direct
    # Flat layout fallback (files in runs_dir directly)
    return runs_dir if runs_dir.exists() else None


def _glob_csv(directory: Path, pattern: str) -> Optional[Path]:
    """Find first matching CSV in a directory."""
    if not directory or not directory.exists():
        return None
    matches = sorted(directory.glob(pattern), reverse=True)
    return matches[0] if matches else None


def _load_ticker_from_csv(csv_path: Optional[Path], ticker: str) -> dict:
    """Return first row matching ticker from a CSV as dict."""
    if not csv_path or not csv_path.exists():
        return {}
    try:
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if str(row.get('ticker', '')).strip().upper() == ticker.upper():
                    return dict(row)
    except Exception as e:
        log.warning(f'Could not read {csv_path}: {e}')
    return {}


def _f(d: dict, key: str, default=None):
    """Safe cast to float from dict."""
    v = d.get(key)
    if v is None or str(v).strip() in ('', 'nan', 'None', 'NaN', 'inf'):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _s(d: dict, key: str, default: str = '') -> str:
    v = d.get(key)
    return str(v).strip() if v is not None else default


def _i(d: dict, key: str, default=None):
    v = _f(d, key)
    return int(v) if v is not None else default


def build_entry_snapshot(
    ticker: str,
    run_id: str,
    runs_dir: Path,
) -> dict:
    """
    Auto-populate all signal fields for a ticker from the pipeline run outputs.
    Reads: superbrain_enriched, options_intelligence, wall_break_scores, ct_enriched.
    Returns a dict ready to INSERT into the trades table.
    """
    ticker = ticker.upper()
    run_dir = _find_run_dir(runs_dir, run_id)

    log.info(f'Loading signal snapshot for {ticker} from run {run_id}')

    # Try both flat and nested directory layouts
    def find_csv(name_pattern):
        target = name_pattern.replace('*', run_id)
        # 1. Search nested run_dir structure
        if run_dir:
            for sub in ['superbrain', 'options', 'discovery', '.']:
                p = run_dir / sub / target
                if p.exists():
                    return p
        # 2. Search all known root locations
        for root in _SEARCH_ROOTS:
            # Nested: root/<run_id>/subdir/file
            for sub in ['superbrain', 'options', 'discovery', run_id, '.']:
                p = root / sub / target
                if p.exists():
                    return p
            # Flat in root itself
            p = root / target
            if p.exists():
                return p
            # Glob with run_id in filename
            matches = sorted(root.glob(f'*{run_id}*'), reverse=True)
            for m in matches:
                if name_pattern.split('_')[0] in m.name and m.suffix == '.csv':
                    return m
        return None

    sb_csv   = find_csv(f'superbrain_enriched_{run_id}.csv')
    oi_csv   = find_csv(f'options_intelligence_{run_id}.csv')
    wbs_csv  = find_csv(f'wall_break_scores_{run_id}.csv')
    ct_csv   = find_csv(f'ct_enriched_{run_id}.csv')
    eil_csv  = find_csv(f'eil_enriched_{run_id}.csv')

    sb  = _load_ticker_from_csv(sb_csv,  ticker)
    oi  = _load_ticker_from_csv(oi_csv,  ticker)
    wbs = _load_ticker_from_csv(wbs_csv, ticker)
    ct  = _load_ticker_from_csv(ct_csv,  ticker)
    eil = _load_ticker_from_csv(eil_csv, ticker)

    if not sb:
        log.warning(f'No SuperBrain row found for {ticker} in run {run_id}. '
                    f'Fields will be blank — fill manually.')
    if not oi:
        log.warning(f'No OI row found for {ticker} — greek fields will be blank.')

    snapshot = {
        # SuperBrain fields
        'sb_verdict':       _s(sb, 'sb_final_verdict'),
        'sb_campaign':      _s(sb, 'sb_campaign'),
        'sb_conv_score':    _i(sb, 'sb_conv_score'),
        'sb_risk_label':    _s(sb, 'sb_risk_label'),
        'sb_size_pct':      _i(sb, 'sb_size_pct'),
        'sb_veto_codes':    _s(sb, 'sb_veto_codes'),
        'rr_predicted':     _f(sb, 'rr'),
        'ev_predicted':     _f(sb, 'ev'),
        'ivp_at_entry':     _f(sb, 'ivp'),
        'time_stop_date':   _s(sb, 'sb_time_stop_date'),
        'checkpoint_date':  _s(sb, 'sb_checkpoint_date'),
        # Sector fields (from superbrain v2.1 — populated from clean_universe)
        'sector':                    _s(sb, 'sector'),
        'sector_short':              _s(sb, 'sector_short'),
        'sector_etf':                _s(sb, 'sector_etf'),
        'industry':                  _s(sb, 'industry'),
        'sector_regime_sensitivity': _s(sb, 'sector_regime_sensitivity'),
        # Quality gate fields (from superbrain v2.1 hard gates)
        'ev_gate':                   _s(sb, 'ev_gate'),
        'rr_gate':                   _s(sb, 'rr_gate'),
        'composite_gate':            _s(sb, 'composite_gate'),
        'regime_sensitivity_score':  _i(sb, 'regime_sensitivity_score'),
        # Multi-horizon EV surface (Vanguard actuarial)
        'win_rate_5d':          _f(sb, 'win_rate_5d'),
        'expected_value_5d':    _f(sb, 'expected_value_5d'),
        'win_rate_10d':         _f(sb, 'win_rate_10d'),
        'expected_value_10d':   _f(sb, 'expected_value_10d'),
        'win_rate_20d':         _f(sb, 'win_rate_20d'),
        'expected_value_20d':   _f(sb, 'expected_value_20d'),
        'sharpe_ratio_5d':      _f(sb, 'sharpe_ratio_5d'),
        'sharpe_ratio_10d':     _f(sb, 'sharpe_ratio_10d'),
        # Horizon profile
        'sb_horizon_profile':   _s(sb, 'sb_horizon_profile'),
        'sb_dte_nudge':         _s(sb, 'sb_dte_nudge'),
        # EIL fields (from execution_intelligence_runner — advisory mode)
        'eil_verdict':          _s(eil, 'eil_raw_verdict') or _s(eil, 'eil_verdict'),
        'eil_liquidity_grade':  _s(eil, 'eil_liquidity_grade'),
        'eil_iv_distortion':    _s(eil, 'eil_iv_distortion'),
        'eil_gex_flip_proximity': _s(eil, 'eil_gex_flip_proximity'),
        'eil_obi_alignment':    _s(eil, 'eil_obi_alignment'),
        'eil_poc_timing':       _s(eil, 'eil_poc_timing'),
        # OI fields
        'options_direction':    _s(oi, 'options_direction'),
        'strike':               _f(oi, 'strike'),
        'expiry':               _s(oi, 'expiry'),
        'dte_at_entry':         _i(oi, 'dte') or _i(sb, 'dte'),
        'underlying_price_at_entry': _f(oi, 'underlying_price'),
        'structural_target':    _f(oi, 'structural_target'),
        'breakeven_pct':        _f(oi, 'breakeven_pct'),
        'put_wall':             _f(oi, 'put_wall'),
        'call_wall':            _f(oi, 'call_wall'),
        'theta_drag_pct':       _f(oi, 'theta_drag_pct'),
        # Greeks
        'vanna_at_entry':       _f(oi, 'contract_vanna'),
        'charm_at_entry':       _f(oi, 'contract_charm'),
        'gamma_flip_conf':      _f(oi, 'gamma_flip_conf'),
        'gamma_flip_gap_pct':   _f(oi, 'gamma_flip_gap_pct'),
        'iv_vs_hv_at_entry':    _f(oi, 'iv_vs_hv'),
        'gamma_velocity_label': _s(oi, 'gamma_velocity_label'),
        # Wall Break Score
        'wbs':       _f(wbs, 'wbs')       or _f(oi, 'wbs'),
        'wbs_grade': _s(wbs, 'wbs_grade') or _s(oi, 'wbs_grade'),
        # CT fields (shadow mode — populated only if ct_enriched exists)
        'ct_bifurcation_proximity': _f(ct, 'ct_bifurcation_proximity'),
        'ct_divergence_set_flag':   _i(ct, 'ct_divergence_set_flag'),
        'ct_entry_sheet':           _s(ct, 'ct_entry_sheet') or 'UNKNOWN',
        'ct_stability_coeff':       _f(ct, 'ct_stability_coeff'),
        'ct_position_size_scalar':  _f(ct, 'ct_position_size_scalar'),
        'ct_data_quality_score':    _f(ct, 'ct_data_quality_score'),
    }

    found = [k for k, v in snapshot.items() if v not in (None, '', 'UNKNOWN', 0)]
    log.info(f'Snapshot populated: {len(found)}/{len(snapshot)} fields from pipeline CSVs')
    return snapshot


# ─────────────────────────────────────────────────────────────────────────────
# CORE OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def log_entry(
    db_path:    Path,
    runs_dir:   Path,
    ticker:     str,
    run_id:     str,
    entry_premium: float,
    contracts:  int   = 1,
    entry_date: str   = '',
    entry_time: str   = '',
    notes:      str   = '',
    # Allow manual overrides for any field
    **overrides,
) -> int:
    """
    Log a new trade entry.
    Auto-populates signal fields from pipeline CSVs.
    Returns the new trade_id.
    """
    snapshot = build_entry_snapshot(ticker, run_id, runs_dir)
    snapshot.update(overrides)  # manual overrides win

    entry_date = entry_date or date.today().isoformat()
    entry_time = entry_time or datetime.now().strftime('%H:%M')
    contract_value = round(entry_premium * contracts * 100, 2)

    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO trades (
            ticker, run_id, entry_date, entry_time, contracts,
            entry_premium, entry_contract_value,
            options_direction, strike, expiry, dte_at_entry,
            sb_verdict, sb_campaign, sb_conv_score, sb_risk_label,
            sb_size_pct, sb_veto_codes,
            rr_predicted, ev_predicted, ivp_at_entry,
            sector, sector_short, sector_etf, industry,
            sector_regime_sensitivity, ev_gate, rr_gate,
            composite_gate, regime_sensitivity_score,
            win_rate_5d, expected_value_5d,
            win_rate_10d, expected_value_10d,
            win_rate_20d, expected_value_20d,
            sharpe_ratio_5d, sharpe_ratio_10d,
            sb_horizon_profile, sb_dte_nudge,
            eil_verdict, eil_liquidity_grade, eil_iv_distortion,
            eil_gex_flip_proximity, eil_obi_alignment, eil_poc_timing,
            underlying_price_at_entry, structural_target, breakeven_pct,
            put_wall, call_wall, theta_drag_pct,
            time_stop_date, checkpoint_date,
            vanna_at_entry, charm_at_entry, gamma_flip_conf,
            gamma_flip_gap_pct, iv_vs_hv_at_entry, gamma_velocity_label,
            ct_bifurcation_proximity, ct_divergence_set_flag,
            ct_entry_sheet, ct_stability_coeff, ct_position_size_scalar,
            ct_data_quality_score,
            wbs, wbs_grade, entry_notes
        ) VALUES (
            :ticker, :run_id, :entry_date, :entry_time, :contracts,
            :entry_premium, :entry_contract_value,
            :options_direction, :strike, :expiry, :dte_at_entry,
            :sb_verdict, :sb_campaign, :sb_conv_score, :sb_risk_label,
            :sb_size_pct, :sb_veto_codes,
            :rr_predicted, :ev_predicted, :ivp_at_entry,
            :sector, :sector_short, :sector_etf, :industry,
            :sector_regime_sensitivity, :ev_gate, :rr_gate,
            :composite_gate, :regime_sensitivity_score,
            :win_rate_5d, :expected_value_5d,
            :win_rate_10d, :expected_value_10d,
            :win_rate_20d, :expected_value_20d,
            :sharpe_ratio_5d, :sharpe_ratio_10d,
            :sb_horizon_profile, :sb_dte_nudge,
            :eil_verdict, :eil_liquidity_grade, :eil_iv_distortion,
            :eil_gex_flip_proximity, :eil_obi_alignment, :eil_poc_timing,
            :underlying_price_at_entry, :structural_target, :breakeven_pct,
            :put_wall, :call_wall, :theta_drag_pct,
            :time_stop_date, :checkpoint_date,
            :vanna_at_entry, :charm_at_entry, :gamma_flip_conf,
            :gamma_flip_gap_pct, :iv_vs_hv_at_entry, :gamma_velocity_label,
            :ct_bifurcation_proximity, :ct_divergence_set_flag,
            :ct_entry_sheet, :ct_stability_coeff, :ct_position_size_scalar,
            :ct_data_quality_score,
            :wbs, :wbs_grade, :entry_notes
        )
    """, {
        **snapshot,
        'ticker': ticker.upper(),
        'run_id': run_id,
        'entry_date': entry_date,
        'entry_time': entry_time,
        'contracts': contracts,
        'entry_premium': entry_premium,
        'entry_contract_value': contract_value,
        'entry_notes': notes,
    })
    trade_id = cur.lastrowid
    conn.commit()
    conn.close()
    log.info(f'Trade logged: trade_id={trade_id}  {ticker}  '
             f'entry=${entry_premium:.2f}  contracts={contracts}  '
             f'value=${contract_value:.2f}')
    return trade_id


# ── Sprint 4 — ML eligibility gate ────────────────────────────────────────────

def _is_ml_eligible(
    exit_reason: str,
    options_direction: str,
    outcome_class: str,
    entry_premium,
    exit_premium,
) -> int:
    """
    Returns 1 if this closed trade qualifies for ML training, 0 otherwise.
    Eligibility rules per CLAUDE.md Sprint 4 spec:
      - outcome_class not a UAT/data-failure class
      - options_direction is set
      - exit_reason is not LIVE_UAT_SMOKE_FLAT or EXPIRED_WORTHLESS
      - entry_premium > 0
      - exit_premium is not NULL
    """
    er = str(exit_reason or "").upper()
    od = str(options_direction or "").strip()
    oc = str(outcome_class or "").upper()
    ep_in  = float(entry_premium or 0)
    ep_out = exit_premium

    if oc in ("LIVE_UAT_SMOKE_FLAT", "DATA_FAILURE"):
        return 0
    if not od:
        return 0
    if "LIVE_UAT_SMOKE_FLAT" in er:
        return 0
    if er.startswith("EXPIRED_WORTHLESS"):
        return 0
    if ep_in <= 0:
        return 0
    if ep_out is None:
        return 0
    return 1


def update_ml_eligibility(db_path: Path = None) -> int:
    """
    Backfill ml_eligible flag on all existing closed_trades.
    Safe to call repeatedly — idempotent UPDATE.
    Returns count of rows evaluated.
    """
    db_path = db_path or DEFAULT_DB_PATH
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT trade_id, exit_reason, options_direction, outcome_class, "
        "entry_premium, exit_premium FROM closed_trades"
    ).fetchall()
    for row in rows:
        eligible = _is_ml_eligible(row[1], row[2], row[3], row[4], row[5])
        conn.execute(
            "UPDATE closed_trades SET ml_eligible = ? WHERE trade_id = ?",
            (eligible, row[0]),
        )
    conn.commit()
    conn.close()
    return len(rows)


def log_exit(
    db_path:       Path,
    trade_id:      int,
    exit_premium:  float,
    exit_reason:   str  = '',
    exit_date:     str  = '',
    exit_time:     str  = '',
    wall_breached: int  = 0,
    ct_proximity_at_exit: float = None,
    outcome_class: str  = '',   # TRUE_WINNER / TRUE_LOSER / PROCESS_WIN / OUTCOME_LOSS
    notes:         str  = '',
) -> dict:
    """
    Log a trade exit. Computes realised metrics and moves record to closed_trades.
    Returns the outcome dict.
    """
    conn = get_db(db_path)
    row = conn.execute(
        'SELECT * FROM trades WHERE trade_id = ?', (trade_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise ValueError(f'trade_id={trade_id} not found in open trades.')

    t = _row_to_dict(row)
    exit_date = exit_date or date.today().isoformat()
    exit_time = exit_time or datetime.now().strftime('%H:%M')

    entry_prem = float(t.get('entry_premium') or 0)
    contracts  = int(t.get('contracts') or 1)

    # Computed outcomes
    exit_cv      = round(exit_premium * contracts * 100, 2)
    pnl_usd      = round((exit_premium - entry_prem) * contracts * 100, 2)
    pnl_pct      = round((exit_premium - entry_prem) / entry_prem * 100, 2) if entry_prem else 0
    rr_realised  = round(pnl_pct / float(t.get('breakeven_pct') or 1), 3) if t.get('breakeven_pct') else None

    # Hold days
    try:
        from datetime import date as ddate
        entry_d = ddate.fromisoformat(str(t.get('entry_date', exit_date)))
        exit_d  = ddate.fromisoformat(exit_date)
        hold_days = (exit_d - entry_d).days
    except Exception:
        hold_days = None

    # Time stop respected?
    time_stop_ok = 0
    ts_date = t.get('time_stop_date', '')
    if ts_date:
        try:
            from datetime import date as ddate
            time_stop_ok = 1 if ddate.fromisoformat(exit_date) <= ddate.fromisoformat(ts_date) else 0
        except Exception:
            pass

    # Target reached? (rough: exit premium substantially > entry_premium suggests big move)
    # More precisely: if underlying hit structural_target, pnl would be large
    # Conservative flag — user confirms manually via notes if needed
    target_reached = 1 if pnl_pct > 80 else 0

    # CT prediction accuracy
    ct_flag = t.get('ct_divergence_set_flag')
    ct_accurate = None
    if ct_flag is not None and pnl_usd is not None:
        ct_accurate = 1 if (int(ct_flag) == 1 and pnl_usd > 0) or \
                           (int(ct_flag) == 0 and pnl_usd <= 0) else 0

    conn.execute("""
        INSERT INTO closed_trades (
            trade_id, ticker, run_id,
            entry_date, entry_premium, contracts, entry_contract_value,
            options_direction, strike, expiry, dte_at_entry,
            sb_verdict, sb_campaign, sb_conv_score,
            rr_predicted, ev_predicted, structural_target,
            put_wall, call_wall, underlying_price_at_entry,
            vanna_at_entry,
            sector, sector_short, sector_etf, industry,
            sector_regime_sensitivity, regime_sensitivity_score,
            ev_gate, rr_gate, composite_gate,
            win_rate_5d, expected_value_5d,
            win_rate_10d, expected_value_10d,
            win_rate_20d, expected_value_20d,
            eil_verdict, eil_liquidity_grade, eil_obi_alignment,
            ct_bifurcation_proximity, ct_divergence_set_flag,
            ct_entry_sheet, ct_stability_coeff, ct_data_quality_score,
            wbs, wbs_grade,
            exit_date, exit_time, exit_premium, exit_contract_value,
            exit_reason,
            rr_realised, pnl_usd, pnl_pct_premium, hold_days,
            wall_breached, time_stop_respected, target_reached,
            outcome_class,
            ct_proximity_at_exit, ct_prediction_accurate,
            exit_notes, ml_eligible
        ) VALUES (
            :trade_id, :ticker, :run_id,
            :entry_date, :entry_premium, :contracts, :entry_contract_value,
            :options_direction, :strike, :expiry, :dte_at_entry,
            :sb_verdict, :sb_campaign, :sb_conv_score,
            :rr_predicted, :ev_predicted, :structural_target,
            :put_wall, :call_wall, :underlying_price_at_entry,
            :vanna_at_entry,
            :sector, :sector_short, :sector_etf, :industry,
            :sector_regime_sensitivity, :regime_sensitivity_score,
            :ev_gate, :rr_gate, :composite_gate,
            :win_rate_5d, :expected_value_5d,
            :win_rate_10d, :expected_value_10d,
            :win_rate_20d, :expected_value_20d,
            :eil_verdict, :eil_liquidity_grade, :eil_obi_alignment,
            :ct_bifurcation_proximity, :ct_divergence_set_flag,
            :ct_entry_sheet, :ct_stability_coeff, :ct_data_quality_score,
            :wbs, :wbs_grade,
            :exit_date, :exit_time, :exit_premium, :exit_contract_value,
            :exit_reason,
            :rr_realised, :pnl_usd, :pnl_pct_premium, :hold_days,
            :wall_breached, :time_stop_respected, :target_reached,
            :outcome_class,
            :ct_proximity_at_exit, :ct_prediction_accurate,
            :exit_notes, :ml_eligible
        )
    """, {
        **t,
        'exit_date': exit_date,
        'exit_time': exit_time,
        'exit_premium': exit_premium,
        'exit_contract_value': exit_cv,
        'exit_reason': exit_reason,
        'rr_realised': rr_realised,
        'pnl_usd': pnl_usd,
        'pnl_pct_premium': pnl_pct,
        'hold_days': hold_days,
        'wall_breached': wall_breached,
        'time_stop_respected': time_stop_ok,
        'target_reached': target_reached,
        'outcome_class': outcome_class or (
            'TRUE_WINNER' if pnl_usd > 0 and wall_breached else
            'PROCESS_WIN' if pnl_usd > 0 else
            'TRUE_LOSER'
        ),
        'ct_proximity_at_exit': ct_proximity_at_exit,
        'ct_prediction_accurate': ct_accurate,
        'exit_notes': notes,
        'ml_eligible': _is_ml_eligible(
            exit_reason,
            t.get('options_direction', ''),
            outcome_class or ('TRUE_WINNER' if pnl_usd > 0 else 'TRUE_LOSER'),
            t.get('entry_premium'),
            exit_premium,
        ),
    })
    conn.execute('DELETE FROM trades WHERE trade_id = ?', (trade_id,))
    conn.commit()
    conn.close()

    outcome = {
        'trade_id': trade_id,
        'ticker': t['ticker'],
        'pnl_usd': pnl_usd,
        'pnl_pct_premium': pnl_pct,
        'rr_realised': rr_realised,
        'hold_days': hold_days,
        'wall_breached': wall_breached,
        'time_stop_respected': time_stop_ok,
    }
    result_str = '✓ WINNER' if pnl_usd > 0 else '✗ LOSER'
    log.info(f'Trade closed: {result_str}  {t["ticker"]}  '
             f'P&L=${pnl_usd:+.2f}  ({pnl_pct:+.1f}%)  '
             f'R:R realised={rr_realised}  hold={hold_days}d')
    return outcome


# ─────────────────────────────────────────────────────────────────────────────
# CALIBRATION REPORT — triggers after every 10 closed trades
# ─────────────────────────────────────────────────────────────────────────────

def generate_calibration_report(db_path: Path, min_trades: int = 10) -> Optional[dict]:
    """
    Generate a calibration report comparing predicted vs realised metrics.
    Only runs if total closed trades >= min_trades.
    Returns the report dict, or None if insufficient data.
    """
    conn = get_db(db_path)
    rows = conn.execute('SELECT * FROM closed_trades').fetchall()
    conn.close()

    if len(rows) < min_trades:
        log.info(f'Calibration skipped: {len(rows)} closed trades (need {min_trades})')
        return None

    trades = [_row_to_dict(r) for r in rows]

    # Win rate
    winners = [t for t in trades if (t.get('pnl_usd') or 0) > 0]
    realised_wr = len(winners) / len(trades)
    predicted_wrs = [t.get('rr_predicted') for t in trades if t.get('rr_predicted') is not None]
    # Proxy predicted win rate: signals with rr>1.0 are treated as "predicted win"
    predicted_wr = len([r for r in predicted_wrs if r and float(r) > 1.0]) / len(trades) if predicted_wrs else None

    # R:R
    realised_rrs = [float(t['rr_realised']) for t in trades if t.get('rr_realised') is not None]
    predicted_rrs = [float(t['rr_predicted']) for t in trades if t.get('rr_predicted') is not None]
    avg_realised_rr  = sum(realised_rrs) / len(realised_rrs) if realised_rrs else None
    avg_predicted_rr = sum(predicted_rrs) / len(predicted_rrs) if predicted_rrs else None
    rr_accuracy = abs(avg_predicted_rr - avg_realised_rr) if (avg_predicted_rr and avg_realised_rr) else None

    # Wall breach rate
    wall_trades = [t for t in trades if t.get('put_wall') or t.get('call_wall')]
    wall_breach_rate = sum(1 for t in wall_trades if (t.get('wall_breached') or 0) == 1) / len(wall_trades) if wall_trades else None
    probable_wbs = [t for t in wall_trades if t.get('wbs_grade') == 'PROBABLE']
    wall_breach_probable = sum(1 for t in probable_wbs if (t.get('wall_breached') or 0) == 1) / len(probable_wbs) if probable_wbs else None

    # CT accuracy
    ct_trades = [t for t in trades if t.get('ct_prediction_accurate') is not None]
    ct_hit_rate = sum(1 for t in ct_trades if (t.get('ct_prediction_accurate') or 0) == 1) / len(ct_trades) if ct_trades else None

    div_set_trades = [t for t in trades if (t.get('ct_divergence_set_flag') or 0) == 1]
    div_hit_rate = sum(1 for t in div_set_trades if (t.get('pnl_usd') or 0) > 0) / len(div_set_trades) if div_set_trades else None

    # Veto hit rate (trades with vetoes that became losers)
    veto_trades = [t for t in trades if t.get('sb_veto_codes') and t['sb_veto_codes'] not in ('NONE', '')]
    veto_losers = [t for t in veto_trades if (t.get('pnl_usd') or 0) <= 0]
    veto_hit_rate = len(veto_losers) / len(veto_trades) if veto_trades else None

    # ── Sector performance breakdown ──────────────────────────────────────────
    from collections import defaultdict
    sector_buckets: dict = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pnl': 0.0})
    for t in trades:
        sec = t.get('sector_short') or t.get('sector') or 'N/A'
        if (t.get('pnl_usd') or 0) > 0:
            sector_buckets[sec]['wins'] += 1
        else:
            sector_buckets[sec]['losses'] += 1
        sector_buckets[sec]['pnl'] += float(t.get('pnl_usd') or 0)

    sector_performance = {}
    for sec, b in sector_buckets.items():
        total_sec = b['wins'] + b['losses']
        sector_performance[sec] = {
            'trades': total_sec,
            'wins': b['wins'],
            'win_rate': round(b['wins'] / total_sec, 3) if total_sec else 0,
            'total_pnl': round(b['pnl'], 2),
        }

    # ── EIL accuracy (trades with EIL data) ───────────────────────────────────
    eil_trades = [t for t in trades if t.get('eil_verdict') and
                  t['eil_verdict'] not in ('', 'ADVISORY_ONLY', 'UNKNOWN')]
    eil_now_trades = [t for t in eil_trades if t.get('eil_verdict') == 'EXECUTE_NOW']
    eil_now_winners = [t for t in eil_now_trades if (t.get('pnl_usd') or 0) > 0]
    eil_now_win_rate = len(eil_now_winners) / len(eil_now_trades) if eil_now_trades else None

    # Regime sensitivity accuracy
    high_sens = [t for t in trades if (t.get('regime_sensitivity_score') or 0) >= 60]
    high_sens_losers = [t for t in high_sens if (t.get('pnl_usd') or 0) <= 0]
    high_sens_loss_rate = len(high_sens_losers) / len(high_sens) if high_sens else None

    # Gate violation check — any trades entered with FAIL gates (manual overrides)
    gate_fail_trades = [t for t in trades if
                        (t.get('ev_gate') or '').startswith('FAIL') or
                        (t.get('rr_gate') or '').startswith('FAIL')]
    gate_fail_losers = [t for t in gate_fail_trades if (t.get('pnl_usd') or 0) <= 0]
    gate_fail_loss_rate = len(gate_fail_losers) / len(gate_fail_trades) if gate_fail_trades else None

    # VARIANCE_SCALAR recommendation
    var_flag = 'OK'
    if ct_hit_rate is not None:
        if ct_hit_rate < 0.40:
            var_flag = 'REVIEW_UP'
        elif ct_hit_rate > 0.70:
            var_flag = 'REVIEW_DOWN'

    report = {
        'generated_at':            datetime.now().isoformat(),
        'trades_analysed':         len(trades),
        'realised_win_rate':       round(realised_wr, 4),
        'predicted_win_rate':      round(predicted_wr, 4) if predicted_wr else None,
        'win_rate_accuracy':       round(abs((predicted_wr or 0) - realised_wr), 4),
        'avg_realised_rr':         round(avg_realised_rr, 3) if avg_realised_rr else None,
        'avg_predicted_rr':        round(avg_predicted_rr, 3) if avg_predicted_rr else None,
        'rr_accuracy':             round(rr_accuracy, 3) if rr_accuracy else None,
        'wall_breach_rate':        round(wall_breach_rate, 4) if wall_breach_rate else None,
        'wall_breach_rate_probable': round(wall_breach_probable, 4) if wall_breach_probable else None,
        'ct_divergence_hit_rate':  round(div_hit_rate, 4) if div_hit_rate else None,
        'ct_prediction_accuracy':  round(ct_hit_rate, 4) if ct_hit_rate else None,
        'veto_hit_rate':           round(veto_hit_rate, 4) if veto_hit_rate else None,
        'variance_scalar_flag':    var_flag,
        # Sector performance
        'sector_performance':      sector_performance,
        # EIL accuracy
        'eil_execute_now_win_rate': round(eil_now_win_rate, 4) if eil_now_win_rate else None,
        'eil_trades_count':        len(eil_trades),
        # Regime sensitivity
        'high_sensitivity_loss_rate': round(high_sens_loss_rate, 4) if high_sens_loss_rate else None,
        'high_sensitivity_trades': len(high_sens),
        # Gate violation tracking
        'gate_fail_trades':        len(gate_fail_trades),
        'gate_fail_loss_rate':     round(gate_fail_loss_rate, 4) if gate_fail_loss_rate else None,
        'detail': {
            'winners': len(winners),
            'losers':  len(trades) - len(winners),
            'wall_trades': len(wall_trades),
            'veto_trades': len(veto_trades),
            'ct_trades':   len(ct_trades),
            'div_set_trades': len(div_set_trades),
            'eil_now_trades': len(eil_now_trades),
            'high_sens_trades': len(high_sens),
        }
    }

    # Save to DB
    conn = get_db(db_path)
    conn.execute("""
        INSERT INTO calibration_reports (
            generated_at, trades_analysed,
            predicted_win_rate, realised_win_rate, win_rate_accuracy,
            predicted_rr_avg, realised_rr_avg, rr_accuracy,
            ct_ev_accuracy, ct_divergence_hit_rate,
            wall_breach_rate, wall_breach_rate_probable,
            veto_hit_rate,
            variance_scalar_current, variance_scalar_flag,
            report_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        report['generated_at'], report['trades_analysed'],
        report.get('predicted_win_rate'), report['realised_win_rate'], report.get('win_rate_accuracy'),
        report.get('avg_predicted_rr'), report.get('avg_realised_rr'), report.get('rr_accuracy'),
        report.get('ct_prediction_accuracy'), report.get('ct_divergence_hit_rate'),
        report.get('wall_breach_rate'), report.get('wall_breach_rate_probable'),
        report.get('veto_hit_rate'),
        0.4,  # current VARIANCE_SCALAR default
        var_flag,
        json.dumps(report, default=str),
    ))
    conn.commit()
    conn.close()

    log.info(f'Calibration report saved: {len(trades)} trades analysed  '
             f'win_rate={realised_wr:.1%}  '
             f'VARIANCE_SCALAR={var_flag}')
    return report


def _print_calibration(report: dict) -> None:
    print(f'\n{"═"*65}')
    print(f'  CALIBRATION REPORT — {report["trades_analysed"]} closed trades')
    print(f'{"═"*65}')
    print(f'  Win rate:   predicted={report.get("predicted_win_rate", "N/A")}  '
          f'realised={report["realised_win_rate"]:.1%}')
    print(f'  R:R:        predicted={report.get("avg_predicted_rr", "N/A")}  '
          f'realised={report.get("avg_realised_rr", "N/A")}')
    print(f'  Wall breach rate:         {report.get("wall_breach_rate", "N/A")}')
    print(f'  Wall breach (PROBABLE):   {report.get("wall_breach_rate_probable", "N/A")}')
    print(f'  CT divergence hit rate:   {report.get("ct_divergence_hit_rate", "N/A")}')
    print(f'  Veto loser rate:          {report.get("veto_hit_rate", "N/A")}')
    print(f'  VARIANCE_SCALAR flag:     {report["variance_scalar_flag"]}')
    if report['variance_scalar_flag'] != 'OK':
        print(f'  ⚠  Review VARIANCE_SCALAR in catastrophe_gate.py')

    # Sector breakdown
    sector_perf = report.get('sector_performance', {})
    if sector_perf:
        print(f'\n  SECTOR PERFORMANCE:')
        print(f'  {"Sector":6} {"Trades":7} {"Wins":5} {"Win%":7} {"P&L":>10}')
        print(f'  {"─"*6} {"─"*7} {"─"*5} {"─"*7} {"─"*10}')
        for sec, s in sorted(sector_perf.items(),
                              key=lambda x: -x[1]['total_pnl']):
            flag = '✓' if s['total_pnl'] > 0 else '✗'
            print(f'  {sec:6} {s["trades"]:>7} {s["wins"]:>5} '
                  f'{s["win_rate"]:.0%}    '
                  f'{flag} ${s["total_pnl"]:>+8.2f}')

    # EIL accuracy
    eil_wr = report.get('eil_execute_now_win_rate')
    eil_n  = report.get('eil_trades_count', 0)
    if eil_n > 0:
        print(f'\n  EIL ACCURACY ({eil_n} trades with EIL data):')
        if eil_wr is not None:
            print(f'    EXECUTE_NOW win rate: {eil_wr:.1%}')
        else:
            print(f'    EXECUTE_NOW: insufficient data')

    # Regime sensitivity
    hs_loss = report.get('high_sensitivity_loss_rate')
    hs_n    = report.get('high_sensitivity_trades', 0)
    if hs_n > 0:
        print(f'\n  REGIME SENSITIVITY ({hs_n} HIGH sensitivity trades):')
        print(f'    Loss rate: {hs_loss:.1%}' if hs_loss else '    Loss rate: N/A')
        if hs_loss and hs_loss > 0.6:
            print(f'    ⚠  HIGH sensitivity trades underperforming — '
                  f'consider reducing size on regime_sensitivity_score > 60')

    # Gate violations
    gf_n    = report.get('gate_fail_trades', 0)
    gf_loss = report.get('gate_fail_loss_rate')
    if gf_n > 0:
        print(f'\n  GATE VIOLATIONS ({gf_n} trades entered despite FAIL gate):')
        print(f'    Loss rate: {gf_loss:.1%}' if gf_loss else '    Loss rate: N/A')
        if gf_loss and gf_loss > 0.5:
            print(f'    ⚠  Gate violations are losing more than 50% — '
                  f'stop overriding EV and R:R gates')

    print(f'{"═"*65}\n')


# ─────────────────────────────────────────────────────────────────────────────
# STATUS / DISPLAY
# ─────────────────────────────────────────────────────────────────────────────

def print_status(db_path: Path) -> None:
    conn = get_db(db_path)
    open_rows   = conn.execute('SELECT * FROM trades ORDER BY entry_date DESC').fetchall()
    closed_rows = conn.execute('SELECT * FROM closed_trades ORDER BY exit_date DESC').fetchall()
    conn.close()

    print(f'\n{"─"*75}')
    print(f'  AVSHUNTER TRADE JOURNAL  —  {date.today().isoformat()}')
    print(f'{"─"*75}')
    print(f'  Open positions  : {len(open_rows)}')
    print(f'  Closed trades   : {len(closed_rows)}')

    if open_rows:
        print(f'\n  OPEN POSITIONS:')
        print(f'  {"ID":>4}  {"Ticker":8} {"Sec":5} {"Dir":5} {"Strike":8} '
              f'{"Entry $":8} {"Ctrs":5} {"Entry Date":12} {"EIL":15} {"Campaign"}')
        print(f'  {"─"*4}  {"─"*8} {"─"*5} {"─"*5} {"─"*8} '
              f'{"─"*8} {"─"*5} {"─"*12} {"─"*15} {"─"*20}')
        for r in open_rows:
            t = _row_to_dict(r)
            eil_short = (t.get('eil_verdict') or 'N/A')[:14]
            sec_short = (t.get('sector_short') or 'N/A')[:5]
            print(f'  {t["trade_id"]:>4}  {t["ticker"]:8} '
                  f'{sec_short:5} '
                  f'{str(t.get("options_direction",""))[:4]:5} '
                  f'{str(t.get("strike",""))[:7]:8} '
                  f'${float(t.get("entry_premium",0)):6.2f}  '
                  f'{t.get("contracts",1):>5}  '
                  f'{str(t.get("entry_date",""))[:10]:12} '
                  f'{eil_short:15} '
                  f'{str(t.get("sb_campaign",""))}')
            # Regime sensitivity warning
            rss = t.get('regime_sensitivity_score') or 0
            if rss and int(rss) >= 60:
                print(f'         ⚠  Regime sensitivity score: {rss}/100 — '
                      f'high macro exposure. Monitor regime daily.')
            # Gate fail warning
            for gate_field, gate_label in [('ev_gate','EV'), ('rr_gate','R:R')]:
                gv = t.get(gate_field) or ''
                if gv.startswith('FAIL'):
                    print(f'         ⚠  {gate_label} gate: {gv} — '
                          f'this trade was entered despite a hard gate failure. '
                          f'Track separately in calibration.')

    if closed_rows:
        winners = sum(1 for r in closed_rows if (float(_row_to_dict(r).get('pnl_usd') or 0)) > 0)
        total_pnl = sum(float(_row_to_dict(r).get('pnl_usd') or 0) for r in closed_rows)
        print(f'\n  CLOSED TRADES: {len(closed_rows)} total  '
              f'{winners}W / {len(closed_rows)-winners}L  '
              f'Total P&L: ${total_pnl:+.2f}')
        print(f'\n  {"ID":>4}  {"Ticker":8} {"Sec":5} {"Dir":5} {"Entry $":8} '
              f'{"Exit $":8} {"P&L $":8} {"P&L %":7} {"Hold":5} {"Class":14} {"Reason"}')
        print(f'  {"─"*4}  {"─"*8} {"─"*5} {"─"*5} {"─"*8} '
              f'{"─"*8} {"─"*8} {"─"*7} {"─"*5} {"─"*14} {"─"*20}')
        for r in closed_rows[:20]:
            t = _row_to_dict(r)
            pnl = float(t.get('pnl_usd') or 0)
            flag = '✓' if pnl > 0 else '✗'
            sec_short = (t.get('sector_short') or 'N/A')[:5]
            outcome = (t.get('outcome_class') or '')[:13]
            print(f'  {t["trade_id"]:>4}  {t["ticker"]:8} '
                  f'{sec_short:5} '
                  f'{str(t.get("options_direction",""))[:4]:5} '
                  f'${float(t.get("entry_premium",0)):6.2f}  '
                  f'${float(t.get("exit_premium",0)):6.2f}  '
                  f'{flag} ${pnl:+6.2f}  '
                  f'{float(t.get("pnl_pct_premium",0)):+5.1f}%  '
                  f'{str(t.get("hold_days",""))[:4]:5} '
                  f'{outcome:14} '
                  f'{str(t.get("exit_reason",""))[:20]}')
    print(f'{"─"*75}\n')


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='AVSHUNTER Trade Journal — Layer 7',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  log-entry   Log a new trade entry (auto-populates from pipeline CSVs)
  log-exit    Log a trade exit (computes realised P&L and R:R)
  status      Show open positions and closed trade summary
  list-open   List open positions
  list-closed List closed trades
  calibration Run calibration report (requires 10+ closed trades)

Examples:
  # Log T trade entry from run 20260305_092339, 1 contract at $0.57
  python avshunter_trade_journal.py log-entry --ticker T \\
      --run-id 20260305_092339 --premium 0.57 --contracts 1

  # Log exit for trade_id 1 at $0.85 — Phase B partial
  python avshunter_trade_journal.py log-exit --trade-id 1 \\
      --exit-premium 0.85 --exit-reason "Phase B wall stall - 40pct scale"

  # Log exit with wall breach flag
  python avshunter_trade_journal.py log-exit --trade-id 1 \\
      --exit-premium 1.20 --exit-reason "Target hit" --wall-breached

  # Show status
  python avshunter_trade_journal.py status

  # Run calibration
  python avshunter_trade_journal.py calibration
        """
    )
    p.add_argument('--db',       default='', help='Path to trade_journal.db')
    p.add_argument('--runs-dir', default='', help='Path to pipeline runs directory')

    sub = p.add_subparsers(dest='command')

    # log-entry
    e = sub.add_parser('log-entry', help='Log a new trade entry')
    e.add_argument('--ticker',    required=True)
    e.add_argument('--run-id',    required=True)
    e.add_argument('--premium',   required=True, type=float, help='Entry premium per share')
    e.add_argument('--contracts', default=1,     type=int)
    e.add_argument('--date',      default='',    help='Entry date YYYY-MM-DD (default: today)')
    e.add_argument('--time',      default='',    help='Entry time HH:MM (default: now)')
    e.add_argument('--notes',     default='')

    # log-exit
    x = sub.add_parser('log-exit', help='Log a trade exit')
    x.add_argument('--trade-id',     required=True, type=int)
    x.add_argument('--exit-premium', required=True, type=float)
    x.add_argument('--exit-reason',  default='')
    x.add_argument('--date',         default='')
    x.add_argument('--time',         default='')
    x.add_argument('--wall-breached',action='store_true')
    x.add_argument('--ct-proximity', default=None, type=float)
    x.add_argument('--outcome-class', default='',
                   choices=['', 'TRUE_WINNER', 'TRUE_LOSER',
                            'PROCESS_WIN', 'OUTCOME_LOSS'],
                   help='ML classification: TRUE_WINNER / TRUE_LOSER / '
                        'PROCESS_WIN / OUTCOME_LOSS')
    x.add_argument('--notes',        default='')

    sub.add_parser('status',      help='Show open + closed summary')
    sub.add_parser('list-open',   help='List open positions')
    sub.add_parser('list-closed', help='List closed trades')
    sub.add_parser('calibration', help='Run calibration report')

    return p


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Resolve paths
    db_path  = Path(args.db)  if args.db  else DEFAULT_DB_PATH
    runs_dir = Path(args.runs_dir) if args.runs_dir else DEFAULT_RUNS_DIR

    if args.command == 'log-entry':
        trade_id = log_entry(
            db_path       = db_path,
            runs_dir      = runs_dir,
            ticker        = args.ticker,
            run_id        = args.run_id,
            entry_premium = args.premium,
            contracts     = args.contracts,
            entry_date    = args.date,
            entry_time    = args.time,
            notes         = args.notes,
        )
        print(f'\n✓ Entry logged — trade_id={trade_id}  '
              f'{args.ticker}  premium=${args.premium:.2f}  '
              f'contracts={args.contracts}\n')
        # Auto-check calibration trigger
        conn = get_db(db_path)
        n = conn.execute('SELECT COUNT(*) FROM closed_trades').fetchone()[0]
        conn.close()
        if n > 0 and n % 10 == 0:
            log.info(f'{n} closed trades — triggering calibration report')
            report = generate_calibration_report(db_path)
            if report:
                _print_calibration(report)

    elif args.command == 'log-exit':
        outcome = log_exit(
            db_path       = db_path,
            trade_id      = args.trade_id,
            exit_premium  = args.exit_premium,
            exit_reason   = args.exit_reason,
            exit_date     = args.date,
            exit_time     = args.time,
            wall_breached = 1 if args.wall_breached else 0,
            ct_proximity_at_exit = args.ct_proximity,
            notes         = args.notes,
        )
        pnl = outcome['pnl_usd']
        flag = '✓ WINNER' if pnl > 0 else '✗ LOSER'
        print(f'\n{flag}  {outcome["ticker"]}  '
              f'P&L=${pnl:+.2f}  ({outcome["pnl_pct_premium"]:+.1f}%)  '
              f'R:R realised={outcome["rr_realised"]}  '
              f'hold={outcome["hold_days"]}d\n')
        # Auto calibration trigger on multiples of 10
        conn = get_db(db_path)
        n = conn.execute('SELECT COUNT(*) FROM closed_trades').fetchone()[0]
        conn.close()
        if n >= 10 and n % 10 == 0:
            log.info(f'{n} closed trades — triggering calibration report')
            report = generate_calibration_report(db_path)
            if report:
                _print_calibration(report)

    elif args.command in ('status', 'list-open', 'list-closed'):
        print_status(db_path)

    elif args.command == 'calibration':
        report = generate_calibration_report(db_path, min_trades=1)
        if report:
            _print_calibration(report)
        else:
            print('Not enough closed trades for calibration report yet.')


if __name__ == '__main__':
    main()
