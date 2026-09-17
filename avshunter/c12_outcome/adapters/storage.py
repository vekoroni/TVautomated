"""Append-only scoring store (``data/canonical/outcome_scoring.sqlite``)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from enum import Enum
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

DEFAULT_STORE = Path(__file__).resolve().parents[3] / "data" / "canonical" / "outcome_scoring.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prediction_records (
  prediction_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL, direction TEXT, direction_text TEXT,
  evidence_session TEXT, evidence_session_source TEXT NOT NULL,
  reference_price REAL, invalidation_price REAL, invalidation_state TEXT NOT NULL,
  target_price REAL, target_state TEXT NOT NULL,
  contract_symbol TEXT, contract_state TEXT NOT NULL,
  first_run_id TEXT NOT NULL, provenance_class TEXT NOT NULL,
  scorer_version TEXT NOT NULL, recorded_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prediction_sightings (
  prediction_id TEXT NOT NULL, run_id TEXT NOT NULL, pipeline_mode TEXT, run_condition TEXT,
  book_path TEXT NOT NULL, book_sha256 TEXT NOT NULL, book_mtime_utc TEXT NOT NULL,
  entry_bid REAL, entry_ask REAL, labels_json TEXT NOT NULL, ingested_at_utc TEXT NOT NULL,
  PRIMARY KEY (prediction_id, run_id, book_sha256)
);
CREATE TABLE IF NOT EXISTS underlying_outcomes (
  prediction_id TEXT NOT NULL, as_of_session TEXT NOT NULL, scorer_version TEXT NOT NULL,
  state TEXT NOT NULL, sessions_observed INTEGER NOT NULL, resolution_session INTEGER,
  exit_session_date TEXT, exit_price REAL, return_to_exit_pct REAL, r_multiple REAL,
  mfe_pct REAL, mae_pct REAL, reason TEXT, terminal INTEGER NOT NULL, config_snapshot_id TEXT NOT NULL,
  scored_at_utc TEXT NOT NULL,
  PRIMARY KEY (prediction_id, as_of_session, scorer_version)
);
CREATE TABLE IF NOT EXISTS scorer_runs (
  scorer_run_id TEXT PRIMARY KEY, command TEXT NOT NULL, as_of_session TEXT, scorer_version TEXT NOT NULL,
  config_snapshot_id TEXT NOT NULL, started_at_utc TEXT NOT NULL, finished_at_utc TEXT, counts_json TEXT
);
CREATE TABLE IF NOT EXISTS base_rate_outcomes (
  prediction_id TEXT NOT NULL, as_of_session TEXT NOT NULL, base_rate_version TEXT NOT NULL,
  state TEXT NOT NULL, observed_sessions INTEGER NOT NULL, target_atr REAL, stop_atr REAL, atr REAL,
  universe INTEGER, excluded INTEGER, target_fractions_json TEXT, stop_fractions_json TEXT,
  config_snapshot_id TEXT NOT NULL, scored_at_utc TEXT NOT NULL,
  PRIMARY KEY (prediction_id, as_of_session, base_rate_version)
);
CREATE VIEW IF NOT EXISTS latest_base_rate_outcomes AS
  SELECT b.* FROM base_rate_outcomes b
  JOIN (SELECT prediction_id, base_rate_version, MAX(as_of_session) AS as_of_session
        FROM base_rate_outcomes GROUP BY prediction_id, base_rate_version) m
    ON m.prediction_id = b.prediction_id AND m.base_rate_version = b.base_rate_version AND m.as_of_session = b.as_of_session;
CREATE TABLE IF NOT EXISTS condition_records (
  prediction_id TEXT NOT NULL, condition_version TEXT NOT NULL,
  macro_source TEXT NOT NULL, macro_run_id TEXT, macro_as_of_utc TEXT, macro_report_date TEXT,
  macro_freshness TEXT NOT NULL, macro_lag_sessions INTEGER,
  regime_label TEXT, regime_state TEXT, regime_probability REAL, macro_conviction REAL,
  risk_on_off_switch TEXT, credit_state TEXT, net_liquidity_score REAL, rates_impulse TEXT,
  ticker_sector TEXT, sector_alignment TEXT NOT NULL,
  market_trend_state TEXT NOT NULL, market_vol_percentile REAL, market_vol_state TEXT NOT NULL,
  market_breadth REAL, market_breadth_state TEXT NOT NULL, market_drawdown_pct REAL,
  config_snapshot_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,
  PRIMARY KEY (prediction_id, condition_version)
);
CREATE TABLE IF NOT EXISTS expression_outcomes (
  prediction_id TEXT NOT NULL, expression_version TEXT NOT NULL, as_of_session TEXT NOT NULL,
  state TEXT NOT NULL, contract_symbol TEXT, expiry TEXT, last_usable_session TEXT,
  exit_session TEXT, exit_reason TEXT, entry_ask REAL, entry_source TEXT, exit_bid REAL,
  pnl_per_contract REAL, return_on_premium REAL, evidence_session_chain_ask REAL,
  underlying_state TEXT, underlying_return_to_exit_pct REAL, reason TEXT,
  config_snapshot_id TEXT NOT NULL, scored_at_utc TEXT NOT NULL,
  PRIMARY KEY (prediction_id, expression_version)
);
CREATE TABLE IF NOT EXISTS hypothesis_events (
  hypothesis_id TEXT NOT NULL, ticker TEXT NOT NULL, event_session TEXT NOT NULL, direction TEXT NOT NULL,
  held TEXT NOT NULL, gap_atr REAL NOT NULL, entry_close REAL NOT NULL, share_spread REAL,
  config_snapshot_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,
  PRIMARY KEY (hypothesis_id, ticker, event_session)
);
CREATE TABLE IF NOT EXISTS hypothesis_outcomes (
  hypothesis_id TEXT NOT NULL, ticker TEXT NOT NULL, event_session TEXT NOT NULL, horizon INTEGER NOT NULL,
  exit_session TEXT NOT NULL, raw_return REAL, universe_median REAL, net_return REAL, state TEXT NOT NULL,
  config_snapshot_id TEXT NOT NULL, scored_at_utc TEXT NOT NULL,
  PRIMARY KEY (hypothesis_id, ticker, event_session, horizon)
);
CREATE TABLE IF NOT EXISTS signal_tickets (
  ticket_id TEXT PRIMARY KEY, signal_version TEXT NOT NULL, run_id TEXT NOT NULL, evidence_session TEXT NOT NULL,
  issue_session TEXT NOT NULL, rank INTEGER NOT NULL, ticker TEXT NOT NULL, direction TEXT NOT NULL,
  expression TEXT NOT NULL, side TEXT NOT NULL, contract_symbol TEXT, expiry TEXT, last_usable_session TEXT,
  limit_price REAL NOT NULL, scored_entry REAL NOT NULL, reference_spot REAL NOT NULL, reference_spot_utc TEXT,
  stop_spot REAL NOT NULL, target_spot REAL NOT NULL, hold_sessions INTEGER NOT NULL, r_cautious REAL NOT NULL,
  r_central REAL, r_upside REAL, p_target_first REAL, p_stop_first REAL, share_spread REAL,
  share_r_cautious REAL, share_r_central REAL, value_model_preference TEXT, quote_bid REAL, quote_ask REAL, quote_timestamp_utc TEXT, quote_state TEXT NOT NULL,
  quote_adjustment_state TEXT NOT NULL, quote_spot_at_quote REAL, quote_delta REAL, quote_shift REAL,
  iv_source TEXT NOT NULL, o4_pcr_oi REAL, o4_percentile REAL, o4_stance TEXT NOT NULL, o2_state TEXT NOT NULL,
  h9r_gap_up_event INTEGER NOT NULL, config_snapshot_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_rejections (
  run_id TEXT NOT NULL, issue_session TEXT NOT NULL, ticker TEXT NOT NULL, signal_version TEXT NOT NULL,
  reason TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,
  PRIMARY KEY (run_id, issue_session, ticker, signal_version)
);
CREATE TABLE IF NOT EXISTS signal_outcomes (
  ticket_id TEXT NOT NULL, signal_version TEXT NOT NULL, as_of_session TEXT NOT NULL, state TEXT NOT NULL,
  exit_session TEXT, exit_reason TEXT, entry_price REAL, exit_price REAL, return_on_capital REAL, pnl_per_unit REAL,
  reason TEXT, config_snapshot_id TEXT NOT NULL, scored_at_utc TEXT NOT NULL,
  PRIMARY KEY (ticket_id, signal_version)
);
CREATE VIEW IF NOT EXISTS latest_underlying_outcomes AS
  SELECT o.* FROM underlying_outcomes o
  JOIN (SELECT prediction_id, scorer_version, MAX(as_of_session) AS as_of_session
        FROM underlying_outcomes GROUP BY prediction_id, scorer_version) m
    ON m.prediction_id = o.prediction_id AND m.scorer_version = o.scorer_version AND m.as_of_session = o.as_of_session;
"""


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def connect(path: Path = DEFAULT_STORE) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.executescript(SCHEMA)
    return connection


def insert_ignore(connection: sqlite3.Connection, table: str, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    columns = list(rows[0])
    sql = f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
    before = connection.total_changes
    connection.executemany(sql, [[_plain(row[c]) for c in columns] for row in rows])
    return connection.total_changes - before


def outcome_row(prediction_id: str, as_of: date, scorer_version: str, outcome, snapshot_id: str, now: datetime) -> dict:
    data = asdict(outcome)
    return {
        "prediction_id": prediction_id,
        "as_of_session": as_of.isoformat(),
        "scorer_version": scorer_version,
        "state": outcome.state.value,
        "sessions_observed": data["sessions_observed"],
        "resolution_session": data["resolution_session"],
        "exit_session_date": _plain(data["exit_session_date"]),
        "exit_price": data["exit_price"],
        "return_to_exit_pct": data["return_to_exit_pct"],
        "r_multiple": data["r_multiple"],
        "mfe_pct": data["mfe_pct"],
        "mae_pct": data["mae_pct"],
        "reason": data["reason"],
        "terminal": int(outcome.state.terminal),
        "config_snapshot_id": snapshot_id,
        "scored_at_utc": now.isoformat(),
    }


def labels_json(labels: dict) -> str:
    return json.dumps(labels, sort_keys=True, default=str)
