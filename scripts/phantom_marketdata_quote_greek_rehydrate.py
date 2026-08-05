"""Repair PHANTOM Greeks from MarketData option quote endpoint.

This is vendor-only repair. It does not calculate or synthesize Greeks. Rows are
updated only when MarketData returns all five Greek fields by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import requests


QUOTE_URL = "https://api.marketdata.app/v1/options/quotes/{option_symbol}/"
GREEK_FIELDS = ["iv", "delta", "gamma", "theta", "vega"]
QUOTE_COLUMNS = (
    "optionSymbol,bid,bidSize,mid,ask,askSize,last,openInterest,volume,"
    "underlyingPrice,inTheMoney,intrinsicValue,extrinsicValue,updated,"
    "iv,delta,gamma,theta,vega"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_db_path(repo_root: Path) -> Path:
    return repo_root / "data" / "phantom" / "phantom_history.db"


def api_token() -> str:
    return (
        os.environ.get("MARKETDATA_API_KEY")
        or os.environ.get("MARKETDATA_TOKEN")
        or os.environ.get("MD_API_KEY")
        or ""
    ).strip()


def present(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        out = float(value)
        return not (math.isnan(out) or math.isinf(out))
    except Exception:
        return False


def to_float(value: Any) -> float | None:
    if not present(value):
        return None
    return float(value)


def first(payload: Dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if isinstance(value, list) and value:
        return value[0]
    return value


def status_from_payload(payload: Dict[str, Any], http_status: int) -> str:
    api_status = str(payload.get("s") or "").lower()
    if api_status:
        return api_status
    if http_status == 404:
        return "no_data"
    return "error"


def audit_key(option_symbol: str, quote_date: str, params: Dict[str, Any]) -> str:
    raw = json.dumps(
        {"option_symbol": option_symbol.upper(), "quote_date": quote_date, "params": params},
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def parse_csv_list(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip().upper() for part in value.replace(",", " ").split() if part.strip()]


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS marketdata_quote_greek_audit (
            audit_key TEXT PRIMARY KEY,
            ticker TEXT,
            quote_date TEXT,
            option_symbol TEXT,
            params_json TEXT,
            http_status INTEGER,
            api_status TEXT,
            status TEXT,
            iv_present INTEGER,
            delta_present INTEGER,
            gamma_present INTEGER,
            theta_present INTEGER,
            vega_present INTEGER,
            response_keys_json TEXT,
            error TEXT,
            started_at_utc TEXT,
            finished_at_utc TEXT
        );

        CREATE TABLE IF NOT EXISTS chain_greek_provenance (
            ticker TEXT NOT NULL,
            quote_date TEXT NOT NULL,
            option_symbol TEXT NOT NULL,
            greek_source TEXT,
            request_audit_key TEXT,
            updated_at_utc TEXT,
            PRIMARY KEY (ticker, quote_date, option_symbol)
        );

        CREATE INDEX IF NOT EXISTS idx_md_quote_greek_status
            ON marketdata_quote_greek_audit(status, ticker, quote_date);
        """
    )


def load_completed_keys(conn: sqlite3.Connection, retry_nonfull: bool, allow_partial: bool) -> set[str]:
    init_schema(conn)
    statuses = ["OK_FULL_GREEKS", "NO_DATA"]
    if not retry_nonfull:
        statuses.append("QUOTE_ONLY")
        if not allow_partial:
            statuses.append("OK_PARTIAL_GREEKS")
    if allow_partial:
        statuses.append("OK_PARTIAL_GREEKS")
    qmarks = ",".join("?" for _ in statuses)
    cur = conn.execute(
        f"SELECT audit_key FROM marketdata_quote_greek_audit WHERE status IN ({qmarks})",
        tuple(statuses),
    )
    return {str(row[0]) for row in cur.fetchall()}


def load_targets(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    tickers: Sequence[str],
    max_quotes: int,
    completed: set[str],
    force_columns: bool,
) -> List[Tuple[str, str, str, str]]:
    where = ["(iv IS NULL OR delta IS NULL OR gamma IS NULL OR theta IS NULL OR vega IS NULL)"]
    params: List[Any] = []
    if start_date:
        where.append("quote_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("quote_date <= ?")
        params.append(end_date)
    clean_tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if clean_tickers:
        where.append("ticker IN (" + ",".join("?" for _ in clean_tickers) + ")")
        params.extend(clean_tickers)
    limit_sql = ""
    if max_quotes > 0:
        limit_sql = "LIMIT ?"
        params.append(max_quotes * 3)  # over-read so completed rows can be skipped
    sql = f"""
        SELECT ticker, quote_date, option_symbol
        FROM chain_snapshots
        WHERE {" AND ".join(where)}
        ORDER BY quote_date DESC, ticker ASC, option_symbol ASC
        {limit_sql}
    """
    out: List[Tuple[str, str, str, str]] = []
    for ticker, quote_date, option_symbol in conn.execute(sql, tuple(params)).fetchall():
        req_params: Dict[str, Any] = {"date": str(quote_date)}
        if force_columns:
            req_params["columns"] = QUOTE_COLUMNS
        key = audit_key(str(option_symbol), str(quote_date), req_params)
        if key in completed:
            continue
        out.append((str(ticker), str(quote_date), str(option_symbol), key))
        if max_quotes > 0 and len(out) >= max_quotes:
            break
    return out


def fetch_quote_task(task: Dict[str, Any]) -> Dict[str, Any]:
    ticker = task["ticker"]
    quote_date = task["quote_date"]
    option_symbol = task["option_symbol"]
    key = task["audit_key"]
    token = task["token"]
    timeout = int(task["timeout"])
    retries = int(task["retries"])
    sleep = float(task["sleep"])
    force_columns = bool(task["force_columns"])
    params: Dict[str, Any] = {"date": quote_date}
    if force_columns:
        params["columns"] = QUOTE_COLUMNS
    url = QUOTE_URL.format(option_symbol=option_symbol.upper())
    started = utc_now()
    if sleep > 0:
        time.sleep(sleep)
    payload: Dict[str, Any] = {}
    http_status = 0
    last_error = ""
    for attempt in range(max(1, retries + 1)):
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Token {token}"},
                params=params,
                timeout=timeout,
            )
            http_status = int(response.status_code)
            try:
                payload = response.json()
            except Exception:
                payload = {"s": "error", "errmsg": response.text[:500]}
            if http_status == 429 and attempt < retries:
                wait = min(60.0, 10.0 * (attempt + 1))
                last_error = f"HTTP 429 rate limited; waited {wait}s"
                time.sleep(wait)
                continue
            if 500 <= http_status < 600 and attempt < retries:
                wait = min(30.0, 2.0 * (attempt + 1))
                last_error = f"HTTP {http_status}; waited {wait}s"
                time.sleep(wait)
                continue
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(30.0, 2.0 * (attempt + 1)))
                continue
            payload = {"s": "error", "errmsg": last_error}
    api_status = status_from_payload(payload, http_status)
    values = {field: to_float(first(payload, field)) for field in GREEK_FIELDS}
    present_map = {field: values[field] is not None for field in GREEK_FIELDS}
    if api_status == "ok":
        if all(present_map.values()):
            status = "OK_FULL_GREEKS"
        elif any(present_map.values()):
            status = "OK_PARTIAL_GREEKS"
        else:
            status = "QUOTE_ONLY"
    elif api_status == "no_data":
        status = "NO_DATA"
    else:
        status = "ERROR"
    return {
        "audit_key": key,
        "ticker": ticker,
        "quote_date": quote_date,
        "option_symbol": option_symbol,
        "params": params,
        "http_status": http_status,
        "api_status": api_status,
        "status": status,
        "values": values,
        "present_map": present_map,
        "response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "error": payload.get("errmsg", last_error) if isinstance(payload, dict) else last_error,
        "started_at_utc": started,
    }


def update_row(conn: sqlite3.Connection, result: Dict[str, Any], allow_partial: bool) -> int:
    status = result["status"]
    if status != "OK_FULL_GREEKS" and not (status == "OK_PARTIAL_GREEKS" and allow_partial):
        return 0
    values = result["values"]
    conn.execute(
        """
        UPDATE chain_snapshots
        SET iv=COALESCE(?, iv),
            delta=COALESCE(?, delta),
            gamma=COALESCE(?, gamma),
            theta=COALESCE(?, theta),
            vega=COALESCE(?, vega)
        WHERE ticker=? AND quote_date=? AND option_symbol=?
        """,
        (
            values.get("iv"),
            values.get("delta"),
            values.get("gamma"),
            values.get("theta"),
            values.get("vega"),
            result["ticker"],
            result["quote_date"],
            result["option_symbol"],
        ),
    )
    if conn.total_changes <= 0:
        return 0
    conn.execute(
        """
        INSERT INTO chain_greek_provenance
        (ticker, quote_date, option_symbol, greek_source, request_audit_key, updated_at_utc)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET
            greek_source=excluded.greek_source,
            request_audit_key=excluded.request_audit_key,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            result["ticker"],
            result["quote_date"],
            result["option_symbol"],
            "MARKETDATA_OPTIONS_QUOTES",
            result["audit_key"],
            utc_now(),
        ),
    )
    return 1


def write_audit(conn: sqlite3.Connection, result: Dict[str, Any]) -> None:
    pm = result["present_map"]
    conn.execute(
        """
        INSERT OR REPLACE INTO marketdata_quote_greek_audit
        (audit_key,ticker,quote_date,option_symbol,params_json,http_status,api_status,status,
         iv_present,delta_present,gamma_present,theta_present,vega_present,
         response_keys_json,error,started_at_utc,finished_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            result["audit_key"],
            result["ticker"],
            result["quote_date"],
            result["option_symbol"],
            json.dumps(result["params"], sort_keys=True),
            int(result["http_status"] or 0),
            result["api_status"],
            result["status"],
            1 if pm.get("iv") else 0,
            1 if pm.get("delta") else 0,
            1 if pm.get("gamma") else 0,
            1 if pm.get("theta") else 0,
            1 if pm.get("vega") else 0,
            json.dumps(result["response_keys"]),
            str(result.get("error") or ""),
            result["started_at_utc"],
            utc_now(),
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair PHANTOM DB Greeks from MarketData option quotes.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--tickers", default="")
    parser.add_argument("--max-quotes", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sleep", type=float, default=0.02)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--allow-partial-greeks", action="store_true")
    parser.add_argument("--retry-nonfull", action="store_true", help="Retry prior QUOTE_ONLY or partial-Greek audits.")
    parser.add_argument("--no-force-columns", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root)
    db_path = Path(args.db_path) if args.db_path else default_db_path(repo_root)
    token = api_token()
    if not token:
        print(json.dumps({"status": "error", "error": "MARKETDATA_API_KEY is not set"}, indent=2))
        return 2
    if not db_path.exists():
        print(json.dumps({"status": "error", "error": f"DB not found: {db_path}"}, indent=2))
        return 2

    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_schema(conn)
    completed = load_completed_keys(conn, bool(args.retry_nonfull), bool(args.allow_partial_greeks))
    targets = load_targets(
        conn,
        args.start_date,
        args.end_date,
        parse_csv_list(args.tickers),
        int(args.max_quotes),
        completed,
        force_columns=not bool(args.no_force_columns),
    )

    plan = {
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "db_path": str(db_path),
        "target_quotes": len(targets),
        "workers": int(args.workers),
        "source": "MarketData /v1/options/quotes/{optionSymbol}/",
        "vendor_greek_policy": "FULL_MARKETDATA_GREEKS_ONLY" if not args.allow_partial_greeks else "ALLOW_PARTIAL_MARKETDATA_GREEKS",
        "force_columns": not bool(args.no_force_columns),
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        conn.close()
        return 0

    totals = {
        "requests": 0,
        "ok_full_greeks": 0,
        "ok_partial_greeks": 0,
        "quote_only": 0,
        "no_data": 0,
        "errors": 0,
        "rows_updated": 0,
    }
    try:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
            futures = [
                pool.submit(
                    fetch_quote_task,
                    {
                        "ticker": ticker,
                        "quote_date": quote_date,
                        "option_symbol": option_symbol,
                        "audit_key": key,
                        "token": token,
                        "timeout": int(args.timeout),
                        "retries": int(args.retries),
                        "sleep": float(args.sleep),
                        "force_columns": not bool(args.no_force_columns),
                    },
                )
                for ticker, quote_date, option_symbol, key in targets
            ]
            for idx, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                updated = update_row(conn, result, bool(args.allow_partial_greeks))
                write_audit(conn, result)
                totals["requests"] += 1
                totals["rows_updated"] += updated
                status = result["status"]
                if status == "OK_FULL_GREEKS":
                    totals["ok_full_greeks"] += 1
                elif status == "OK_PARTIAL_GREEKS":
                    totals["ok_partial_greeks"] += 1
                elif status == "QUOTE_ONLY":
                    totals["quote_only"] += 1
                elif status == "NO_DATA":
                    totals["no_data"] += 1
                else:
                    totals["errors"] += 1
                if idx % 100 == 0:
                    conn.commit()
                if idx == 1 or idx % 100 == 0:
                    pm = result["present_map"]
                    print(
                        f"[MD-QUOTE-GREEKS] {idx}/{len(targets)} status={status} updated={updated} "
                        f"iv={int(pm.get('iv', False))} delta={int(pm.get('delta', False))} "
                        f"gamma={int(pm.get('gamma', False))} theta={int(pm.get('theta', False))} "
                        f"vega={int(pm.get('vega', False))}"
                    )
        conn.commit()
    finally:
        conn.close()

    print(json.dumps(totals, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
