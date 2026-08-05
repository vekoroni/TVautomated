"""PHANTOM computed options-Greeks database writer.

Creates an auditable computed-Greeks table and hydrates the existing
chain_snapshots Greek columns consumed by PHANTOM IV/gamma mechanisms.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, Iterable, List


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]).lower() == column.lower() for row in cur.fetchall())


def ensure_computed_greeks_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS options_greeks_history (
            ticker TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            expiration_ts INTEGER,
            expiration_date TEXT,
            strike REAL,
            dte REAL,
            side TEXT,
            bid REAL,
            ask REAL,
            mid REAL,
            last REAL,
            open_interest INTEGER,
            volume INTEGER,
            underlying_price REAL,
            market_price REAL,
            risk_free_rate REAL,
            price_source TEXT,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            greeks_source TEXT,
            quality_status TEXT,
            quality_flags TEXT,
            solver_iterations INTEGER,
            solver_error TEXT,
            created_at_utc TEXT,
            updated_at_utc TEXT,
            PRIMARY KEY (ticker, snapshot_date, contract_symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_options_greeks_ticker_date
            ON options_greeks_history(ticker, snapshot_date);
        CREATE INDEX IF NOT EXISTS idx_options_greeks_quality
            ON options_greeks_history(quality_status, greeks_source);
        CREATE INDEX IF NOT EXISTS idx_options_greeks_surface
            ON options_greeks_history(ticker, snapshot_date, side, dte, delta, strike);

        CREATE TABLE IF NOT EXISTS options_greeks_run_audit (
            run_id TEXT PRIMARY KEY,
            db_path TEXT,
            start_date TEXT,
            end_date TEXT,
            tickers TEXT,
            rows_targeted INTEGER,
            rows_processed INTEGER,
            rows_ok INTEGER,
            rows_failed INTEGER,
            chain_rows_updated INTEGER,
            status_counts_json TEXT,
            started_at_utc TEXT,
            finished_at_utc TEXT
        );
        """
    )

    for column, col_type in [
        ("greeks_source", "TEXT"),
        ("greeks_quality", "TEXT"),
        ("greeks_updated_at_utc", "TEXT"),
    ]:
        if not has_column(conn, "chain_snapshots", column):
            conn.execute(f"ALTER TABLE chain_snapshots ADD COLUMN {column} {col_type}")


def upsert_greek_records(conn: sqlite3.Connection, records: List[Dict[str, Any]]) -> int:
    if not records:
        return 0
    now = utc_now()
    rows = []
    for rec in records:
        rows.append(
            (
                rec.get("ticker"),
                rec.get("contract_symbol"),
                rec.get("snapshot_date"),
                rec.get("expiration_ts"),
                rec.get("expiration_date"),
                rec.get("strike"),
                rec.get("dte"),
                rec.get("side"),
                rec.get("bid"),
                rec.get("ask"),
                rec.get("mid"),
                rec.get("last"),
                rec.get("open_interest"),
                rec.get("volume"),
                rec.get("underlying_price"),
                rec.get("market_price"),
                rec.get("risk_free_rate"),
                rec.get("price_source"),
                rec.get("iv"),
                rec.get("delta"),
                rec.get("gamma"),
                rec.get("theta"),
                rec.get("vega"),
                rec.get("greeks_source", "COMPUTED_BS"),
                rec.get("quality_status"),
                rec.get("quality_flags"),
                rec.get("solver_iterations"),
                rec.get("solver_error"),
                rec.get("created_at_utc") or now,
                now,
            )
        )
    conn.executemany(
        """
        INSERT INTO options_greeks_history
        (ticker,contract_symbol,snapshot_date,expiration_ts,expiration_date,strike,dte,side,
         bid,ask,mid,last,open_interest,volume,underlying_price,market_price,risk_free_rate,
         price_source,iv,delta,gamma,theta,vega,greeks_source,quality_status,quality_flags,
         solver_iterations,solver_error,created_at_utc,updated_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ticker, snapshot_date, contract_symbol) DO UPDATE SET
            expiration_ts=excluded.expiration_ts,
            expiration_date=excluded.expiration_date,
            strike=excluded.strike,
            dte=excluded.dte,
            side=excluded.side,
            bid=excluded.bid,
            ask=excluded.ask,
            mid=excluded.mid,
            last=excluded.last,
            open_interest=excluded.open_interest,
            volume=excluded.volume,
            underlying_price=excluded.underlying_price,
            market_price=excluded.market_price,
            risk_free_rate=excluded.risk_free_rate,
            price_source=excluded.price_source,
            iv=excluded.iv,
            delta=excluded.delta,
            gamma=excluded.gamma,
            theta=excluded.theta,
            vega=excluded.vega,
            greeks_source=excluded.greeks_source,
            quality_status=excluded.quality_status,
            quality_flags=excluded.quality_flags,
            solver_iterations=excluded.solver_iterations,
            solver_error=excluded.solver_error,
            updated_at_utc=excluded.updated_at_utc
        """,
        rows,
    )
    return len(rows)


def hydrate_chain_snapshots(conn: sqlite3.Connection, records: Iterable[Dict[str, Any]], overwrite: bool = False) -> int:
    updated = 0
    now = utc_now()
    for rec in records:
        if not str(rec.get("quality_status") or "").startswith("OK"):
            continue
        params = (
            rec.get("iv"),
            rec.get("delta"),
            rec.get("gamma"),
            rec.get("theta"),
            rec.get("vega"),
            rec.get("greeks_source", "COMPUTED_BS"),
            rec.get("quality_status"),
            now,
            rec.get("ticker"),
            rec.get("snapshot_date"),
            rec.get("contract_symbol"),
        )
        if overwrite:
            cur = conn.execute(
                """
                UPDATE chain_snapshots
                SET iv=?, delta=?, gamma=?, theta=?, vega=?,
                    greeks_source=?, greeks_quality=?, greeks_updated_at_utc=?
                WHERE ticker=? AND quote_date=? AND option_symbol=?
                """,
                params,
            )
        else:
            cur = conn.execute(
                """
                UPDATE chain_snapshots
                SET iv=COALESCE(iv, ?),
                    delta=COALESCE(delta, ?),
                    gamma=COALESCE(gamma, ?),
                    theta=COALESCE(theta, ?),
                    vega=COALESCE(vega, ?),
                    greeks_source=COALESCE(greeks_source, ?),
                    greeks_quality=COALESCE(greeks_quality, ?),
                    greeks_updated_at_utc=COALESCE(greeks_updated_at_utc, ?)
                WHERE ticker=? AND quote_date=? AND option_symbol=?
                """,
                params,
            )
        updated += int(cur.rowcount or 0)
    return updated


def write_run_audit(conn: sqlite3.Connection, payload: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO options_greeks_run_audit
        (run_id,db_path,start_date,end_date,tickers,rows_targeted,rows_processed,rows_ok,
         rows_failed,chain_rows_updated,status_counts_json,started_at_utc,finished_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            payload.get("run_id"),
            payload.get("db_path"),
            payload.get("start_date"),
            payload.get("end_date"),
            payload.get("tickers"),
            int(payload.get("rows_targeted") or 0),
            int(payload.get("rows_processed") or 0),
            int(payload.get("rows_ok") or 0),
            int(payload.get("rows_failed") or 0),
            int(payload.get("chain_rows_updated") or 0),
            json.dumps(payload.get("status_counts") or {}, sort_keys=True),
            payload.get("started_at_utc"),
            payload.get("finished_at_utc") or utc_now(),
        ),
    )
