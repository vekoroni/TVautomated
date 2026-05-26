"""
PHANTOM database layer.

Stores historical options-chain snapshots, IV-surface summaries, PHANTOM scores,
and audit records in a standalone SQLite database. This database is intentionally
separate from the Vanguard actuarial database.
"""

from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_db_path(repo_root: Optional[Path] = None) -> Path:
    root = Path(repo_root) if repo_root else default_repo_root()
    return root / "data" / "phantom" / "phantom_history.db"


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def _array(data: Dict[str, Any], key: str) -> List[Any]:
    value = data.get(key, [])
    return value if isinstance(value, list) else []


def normalize_marketdata_chain(data: Dict[str, Any], ticker: str, quote_date: str) -> List[Dict[str, Any]]:
    """Convert MarketData.app parallel-array chain response into row dicts."""
    if not isinstance(data, dict) or data.get("s") != "ok":
        return []

    symbols = _array(data, "optionSymbol")
    if not symbols:
        return []

    keys = [
        "underlying", "expiration", "side", "strike", "firstTraded", "dte", "updated",
        "bid", "bidSize", "mid", "ask", "askSize", "last", "openInterest", "volume",
        "inTheMoney", "intrinsicValue", "extrinsicValue", "underlyingPrice",
        "iv", "delta", "gamma", "theta", "vega",
    ]
    arrays = {k: _array(data, k) for k in keys}
    rows: List[Dict[str, Any]] = []

    for i, symbol in enumerate(symbols):
        side = str(arrays["side"][i]).lower() if i < len(arrays["side"]) else ""
        if side not in {"call", "put"}:
            continue

        bid = _to_float(arrays["bid"][i] if i < len(arrays["bid"]) else None)
        ask = _to_float(arrays["ask"][i] if i < len(arrays["ask"]) else None)
        mid = _to_float(arrays["mid"][i] if i < len(arrays["mid"]) else None)
        if mid is None and bid is not None and ask is not None and ask >= bid:
            mid = (bid + ask) / 2.0

        rows.append(
            {
                "ticker": ticker.upper(),
                "quote_date": quote_date,
                "option_symbol": str(symbol),
                "underlying": str(arrays["underlying"][i]).upper() if i < len(arrays["underlying"]) else ticker.upper(),
                "expiration_ts": _to_int(arrays["expiration"][i] if i < len(arrays["expiration"]) else None),
                "side": side,
                "strike": _to_float(arrays["strike"][i] if i < len(arrays["strike"]) else None),
                "first_traded_ts": _to_int(arrays["firstTraded"][i] if i < len(arrays["firstTraded"]) else None),
                "dte": _to_float(arrays["dte"][i] if i < len(arrays["dte"]) else None),
                "updated_ts": _to_int(arrays["updated"][i] if i < len(arrays["updated"]) else None),
                "bid": bid,
                "bid_size": _to_int(arrays["bidSize"][i] if i < len(arrays["bidSize"]) else None),
                "mid": mid,
                "ask": ask,
                "ask_size": _to_int(arrays["askSize"][i] if i < len(arrays["askSize"]) else None),
                "last": _to_float(arrays["last"][i] if i < len(arrays["last"]) else None),
                "open_interest": _to_int(arrays["openInterest"][i] if i < len(arrays["openInterest"]) else None),
                "volume": _to_int(arrays["volume"][i] if i < len(arrays["volume"]) else None),
                "in_the_money": 1 if (i < len(arrays["inTheMoney"]) and bool(arrays["inTheMoney"][i])) else 0,
                "intrinsic_value": _to_float(arrays["intrinsicValue"][i] if i < len(arrays["intrinsicValue"]) else None),
                "extrinsic_value": _to_float(arrays["extrinsicValue"][i] if i < len(arrays["extrinsicValue"]) else None),
                "underlying_price": _to_float(arrays["underlyingPrice"][i] if i < len(arrays["underlyingPrice"]) else None),
                "iv": _to_float(arrays["iv"][i] if i < len(arrays["iv"]) else None),
                "delta": _to_float(arrays["delta"][i] if i < len(arrays["delta"]) else None),
                "gamma": _to_float(arrays["gamma"][i] if i < len(arrays["gamma"]) else None),
                "theta": _to_float(arrays["theta"][i] if i < len(arrays["theta"]) else None),
                "vega": _to_float(arrays["vega"][i] if i < len(arrays["vega"]) else None),
                "source": "marketdata.app",
                "raw_json": "",
                "created_at_utc": utc_now(),
            }
        )
    return rows


class PhantomDatabase:
    def __init__(self, db_path: Optional[Path] = None, repo_root: Optional[Path] = None) -> None:
        self.repo_root = Path(repo_root) if repo_root else default_repo_root()
        self.db_path = Path(db_path) if db_path else default_db_path(self.repo_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._iv_cache: Dict[str, List[float]] = {}
        self._chain_cache: Dict[str, List[Dict[str, Any]]] = {}

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=60)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialise(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chain_snapshots (
                    ticker TEXT NOT NULL,
                    quote_date TEXT NOT NULL,
                    option_symbol TEXT NOT NULL,
                    underlying TEXT,
                    expiration_ts INTEGER,
                    side TEXT,
                    strike REAL,
                    first_traded_ts INTEGER,
                    dte REAL,
                    updated_ts INTEGER,
                    bid REAL,
                    bid_size INTEGER,
                    mid REAL,
                    ask REAL,
                    ask_size INTEGER,
                    last REAL,
                    open_interest INTEGER,
                    volume INTEGER,
                    in_the_money INTEGER,
                    intrinsic_value REAL,
                    extrinsic_value REAL,
                    underlying_price REAL,
                    iv REAL,
                    delta REAL,
                    gamma REAL,
                    theta REAL,
                    vega REAL,
                    source TEXT,
                    raw_json TEXT,
                    created_at_utc TEXT,
                    PRIMARY KEY (ticker, quote_date, option_symbol)
                );

                CREATE INDEX IF NOT EXISTS idx_chain_ticker_date
                    ON chain_snapshots(ticker, quote_date);
                CREATE INDEX IF NOT EXISTS idx_chain_surface
                    ON chain_snapshots(ticker, quote_date, side, dte, delta, strike);

                CREATE TABLE IF NOT EXISTS iv_surface_history (
                    ticker TEXT NOT NULL,
                    quote_date TEXT NOT NULL,
                    dte_bucket TEXT NOT NULL,
                    side TEXT NOT NULL,
                    contract_count INTEGER,
                    atm_iv REAL,
                    median_iv REAL,
                    iv_entropy REAL,
                    skew_25d REAL,
                    put_call_iv_spread REAL,
                    median_spread_pct REAL,
                    total_open_interest INTEGER,
                    total_volume INTEGER,
                    created_at_utc TEXT,
                    PRIMARY KEY (ticker, quote_date, dte_bucket, side)
                );

                CREATE TABLE IF NOT EXISTS phantom_scores (
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    score_date TEXT,
                    phantom_score REAL,
                    phantom_decision TEXT,
                    phantom_iv_entropy REAL,
                    phantom_gamma_trajectory REAL,
                    phantom_bayesian_edge REAL,
                    phantom_info_flow REAL,
                    phantom_criticality REAL,
                    phantom_convergence_count INTEGER,
                    phantom_ois_adjustment REAL,
                    phantom_promotion_reason TEXT,
                    phantom_data_quality TEXT,
                    payload_json TEXT,
                    created_at_utc TEXT,
                    PRIMARY KEY (run_id, ticker)
                );

                CREATE TABLE IF NOT EXISTS phantom_outcomes (
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    outcome_date TEXT,
                    trade_outcome TEXT,
                    pnl REAL,
                    notes TEXT,
                    created_at_utc TEXT,
                    PRIMARY KEY (run_id, ticker, outcome_date)
                );

                CREATE TABLE IF NOT EXISTS mechanism_weights (
                    regime TEXT NOT NULL,
                    mechanism_name TEXT NOT NULL,
                    weight REAL NOT NULL,
                    calibration_date TEXT NOT NULL,
                    created_at_utc TEXT,
                    PRIMARY KEY (regime, mechanism_name, calibration_date)
                );

                CREATE TABLE IF NOT EXISTS backfill_audit (
                    query_key TEXT PRIMARY KEY,
                    ticker TEXT,
                    quote_date TEXT,
                    params_json TEXT,
                    status TEXT,
                    rows_written INTEGER,
                    estimated_credits INTEGER,
                    error TEXT,
                    started_at_utc TEXT,
                    finished_at_utc TEXT
                );

                CREATE TABLE IF NOT EXISTS phantom_run_audit (
                    run_id TEXT PRIMARY KEY,
                    input_csv TEXT,
                    output_csv TEXT,
                    rows_processed INTEGER,
                    promoted_count INTEGER,
                    hard_veto_respected_count INTEGER,
                    score_summary_json TEXT,
                    created_at_utc TEXT
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    def upsert_chain_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        cols = list(rows[0].keys())
        placeholders = ",".join(["?"] * len(cols))
        assignments = ",".join([f"{c}=excluded.{c}" for c in cols if c not in {"ticker", "quote_date", "option_symbol"}])
        sql = (
            f"INSERT INTO chain_snapshots({','.join(cols)}) VALUES({placeholders}) "
            f"ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET {assignments}"
        )
        with self.connect() as conn:
            conn.executemany(sql, [[r.get(c) for c in cols] for r in rows])
        return len(rows)

    def write_backfill_audit(self, query_key: str, ticker: str, quote_date: str, params: Dict[str, Any], status: str,
                             rows_written: int = 0, estimated_credits: int = 0, error: str = "",
                             started_at_utc: Optional[str] = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO backfill_audit
                (query_key,ticker,quote_date,params_json,status,rows_written,estimated_credits,error,started_at_utc,finished_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    query_key, ticker.upper(), quote_date, json.dumps(params, sort_keys=True), status,
                    int(rows_written or 0), int(estimated_credits or 0), str(error or ""),
                    started_at_utc or utc_now(), utc_now(),
                ),
            )

    def audit_exists(self, query_key: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM backfill_audit WHERE query_key=? AND status IN ('OK','NO_DATA')",
                (query_key,),
            )
            return cur.fetchone() is not None

    def latest_chain_rows(self, ticker: str, quote_date: Optional[str] = None) -> List[Dict[str, Any]]:
        ticker_up = ticker.upper()
        if not quote_date and ticker_up in self._chain_cache:
            return self._chain_cache[ticker_up]
        with self.connect() as conn:
            if quote_date:
                cur = conn.execute(
                    "SELECT * FROM chain_snapshots WHERE ticker=? AND quote_date=?",
                    (ticker_up, quote_date),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT * FROM chain_snapshots
                    WHERE ticker=? AND quote_date=(SELECT MAX(quote_date) FROM chain_snapshots WHERE ticker=?)
                    """,
                    (ticker_up, ticker_up),
                )
            return [dict(r) for r in cur.fetchall()]

    def historical_iv_values(self, ticker: str, dte_min: float = 7, dte_max: float = 60) -> List[float]:
        ticker_up = ticker.upper()
        if ticker_up in self._iv_cache:
            return self._iv_cache[ticker_up]
        with self.connect() as conn:
            cur = conn.execute(
                """
                SELECT iv FROM chain_snapshots
                WHERE ticker=? AND iv IS NOT NULL AND dte BETWEEN ? AND ?
                """,
                (ticker_up, dte_min, dte_max),
            )
            return [float(r["iv"]) for r in cur.fetchall() if r["iv"] is not None]

    def preload_tickers(self, tickers: List[str], dte_min: float = 7, dte_max: float = 60) -> None:
        """Batch-load IV history and latest chain rows for all tickers in one DB connection."""
        unique = list({t.upper() for t in tickers if t})
        if not unique:
            return
        placeholders = ",".join(["?"] * len(unique))
        with self.connect() as conn:
            cur = conn.execute(
                f"SELECT ticker, iv FROM chain_snapshots"
                f" WHERE ticker IN ({placeholders}) AND iv IS NOT NULL AND dte BETWEEN ? AND ?",
                unique + [dte_min, dte_max],
            )
            for row in cur.fetchall():
                t = row["ticker"].upper()
                self._iv_cache.setdefault(t, []).append(float(row["iv"]))

            cur = conn.execute(
                f"""
                SELECT cs.* FROM chain_snapshots cs
                JOIN (
                    SELECT ticker, MAX(quote_date) AS max_qd
                    FROM chain_snapshots WHERE ticker IN ({placeholders})
                    GROUP BY ticker
                ) t ON cs.ticker=t.ticker AND cs.quote_date=t.max_qd
                """,
                unique,
            )
            for row in cur.fetchall():
                t = row["ticker"].upper()
                self._chain_cache.setdefault(t, []).append(dict(row))

        for t in unique:
            self._iv_cache.setdefault(t, [])
            self._chain_cache.setdefault(t, [])

    def batch_write_phantom_scores(self, run_id: str, scores: List[tuple]) -> None:
        """Write all phantom scores for a run in a single transaction."""
        rows = []
        for ticker, payload in scores:
            rows.append((
                run_id, str(ticker).upper(), payload.get("score_date"),
                payload.get("phantom_score"), payload.get("phantom_decision"),
                payload.get("phantom_iv_entropy"), payload.get("phantom_gamma_trajectory"),
                payload.get("phantom_bayesian_edge"), payload.get("phantom_info_flow"),
                payload.get("phantom_criticality"), payload.get("phantom_convergence_count"),
                payload.get("phantom_ois_adjustment"), payload.get("phantom_promotion_reason"),
                payload.get("phantom_data_quality"),
                json.dumps(payload, sort_keys=True, default=str), utc_now(),
            ))
        if not rows:
            return
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO phantom_scores
                (run_id,ticker,score_date,phantom_score,phantom_decision,phantom_iv_entropy,
                 phantom_gamma_trajectory,phantom_bayesian_edge,phantom_info_flow,phantom_criticality,
                 phantom_convergence_count,phantom_ois_adjustment,phantom_promotion_reason,
                 phantom_data_quality,payload_json,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )

    def write_phantom_score(self, run_id: str, ticker: str, payload: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO phantom_scores
                (run_id,ticker,score_date,phantom_score,phantom_decision,phantom_iv_entropy,
                 phantom_gamma_trajectory,phantom_bayesian_edge,phantom_info_flow,phantom_criticality,
                 phantom_convergence_count,phantom_ois_adjustment,phantom_promotion_reason,
                 phantom_data_quality,payload_json,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_id, ticker.upper(), payload.get("score_date"), payload.get("phantom_score"),
                    payload.get("phantom_decision"), payload.get("phantom_iv_entropy"),
                    payload.get("phantom_gamma_trajectory"), payload.get("phantom_bayesian_edge"),
                    payload.get("phantom_info_flow"), payload.get("phantom_criticality"),
                    payload.get("phantom_convergence_count"), payload.get("phantom_ois_adjustment"),
                    payload.get("phantom_promotion_reason"), payload.get("phantom_data_quality"),
                    json.dumps(payload, sort_keys=True, default=str), utc_now(),
                ),
            )

    def write_run_audit(self, run_id: str, input_csv: str, output_csv: str, rows_processed: int,
                        promoted_count: int, hard_veto_respected_count: int, summary: Dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO phantom_run_audit
                (run_id,input_csv,output_csv,rows_processed,promoted_count,hard_veto_respected_count,score_summary_json,created_at_utc)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    run_id, input_csv, output_csv, int(rows_processed), int(promoted_count),
                    int(hard_veto_respected_count), json.dumps(summary, sort_keys=True, default=str), utc_now(),
                ),
            )
