"""Rehydrate PHANTOM historical option-chain Greeks from MarketData.

This repairs existing quote rows by re-querying MarketData using the documented
expiration + side chain shape:

  /v1/options/chain/{ticker}/?date=YYYY-MM-DD&expiration=YYYY-MM-DD&side=call
  /v1/options/chain/{ticker}/?date=YYYY-MM-DD&expiration=YYYY-MM-DD&side=put

It refuses to silently mark quote-only responses as healthy.
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phantom_database import normalize_marketdata_chain  # noqa: E402


CHAIN_URL = "https://api.marketdata.app/v1/options/chain/{ticker}/"
EXPIRATIONS_URL = "https://api.marketdata.app/v1/options/expirations/{ticker}/"
GREEK_FIELDS = ["iv", "delta", "gamma", "theta", "vega"]
DEFAULT_COLUMNS = (
    "optionSymbol,underlying,expiration,side,strike,firstTraded,dte,updated,"
    "bid,bidSize,mid,ask,askSize,last,openInterest,volume,inTheMoney,"
    "intrinsicValue,extrinsicValue,underlyingPrice,iv,delta,gamma,theta,vega"
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


def is_present(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        out = float(value)
        return not (math.isnan(out) or math.isinf(out))
    except Exception:
        return False


def field_count(payload: Dict[str, Any], key: str) -> int:
    values = payload.get(key)
    if not isinstance(values, list):
        return 0
    return sum(1 for value in values if is_present(value))


def response_status(payload: Dict[str, Any], http_status: int) -> str:
    status = str(payload.get("s") or "").strip().lower()
    if status:
        return status
    if isinstance(payload.get("optionSymbol"), list):
        return "ok"
    if http_status == 404:
        return "no_data"
    return "error"


def audit_key(ticker: str, quote_date: str, expiration: str, side: str, params: Dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "ticker": ticker.upper(),
            "quote_date": quote_date,
            "expiration": expiration,
            "side": side,
            "params": params,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def normalise_expiration_ts(value: Any) -> Optional[str]:
    try:
        ts = int(float(value))
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
    except Exception:
        return None


def init_rehydration_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS greek_rehydration_audit (
            audit_key TEXT PRIMARY KEY,
            ticker TEXT,
            quote_date TEXT,
            expiration TEXT,
            side TEXT,
            params_json TEXT,
            http_status INTEGER,
            api_status TEXT,
            status TEXT,
            row_count INTEGER,
            rows_written INTEGER,
            iv_count INTEGER,
            delta_count INTEGER,
            gamma_count INTEGER,
            theta_count INTEGER,
            vega_count INTEGER,
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

        CREATE INDEX IF NOT EXISTS idx_greek_rehydration_status
            ON greek_rehydration_audit(status, ticker, quote_date);
        """
    )


def load_completed_request_keys(conn: sqlite3.Connection, retry_quotes_only: bool, allow_partial_greeks: bool) -> set[str]:
    init_rehydration_schema(conn)
    statuses = ["OK_FULL_GREEKS", "NO_DATA"]
    if allow_partial_greeks:
        statuses.append("OK_PARTIAL_GREEKS")
    if not retry_quotes_only:
        statuses.append("OK_QUOTES_ONLY")
    qmarks = ",".join("?" for _ in statuses)
    cur = conn.execute(
        f"SELECT audit_key FROM greek_rehydration_audit WHERE status IN ({qmarks})",
        tuple(statuses),
    )
    return {str(row[0]) for row in cur.fetchall()}


def load_targets(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    tickers: Sequence[str],
    max_target_dates: int,
) -> List[Tuple[str, str, int]]:
    where = ["1=1"]
    params: List[Any] = []
    if start_date:
        where.append("quote_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("quote_date <= ?")
        params.append(end_date)
    clean_tickers = [t.strip().upper() for t in tickers if t.strip()]
    if clean_tickers:
        where.append("ticker IN (" + ",".join("?" for _ in clean_tickers) + ")")
        params.extend(clean_tickers)
    limit_sql = ""
    if max_target_dates > 0:
        limit_sql = "LIMIT ?"
        params.append(max_target_dates)
    sql = f"""
        SELECT ticker, quote_date, COUNT(*) AS rows_total,
               SUM(CASE WHEN iv IS NOT NULL THEN 1 ELSE 0 END) AS iv_rows,
               SUM(CASE WHEN delta IS NOT NULL THEN 1 ELSE 0 END) AS delta_rows,
               SUM(CASE WHEN gamma IS NOT NULL THEN 1 ELSE 0 END) AS gamma_rows,
               SUM(CASE WHEN theta IS NOT NULL THEN 1 ELSE 0 END) AS theta_rows,
               SUM(CASE WHEN vega IS NOT NULL THEN 1 ELSE 0 END) AS vega_rows
        FROM chain_snapshots
        WHERE {" AND ".join(where)}
        GROUP BY ticker, quote_date
        HAVING rows_total > 0
           AND (iv_rows < rows_total OR delta_rows < rows_total OR gamma_rows < rows_total
                OR theta_rows < rows_total OR vega_rows < rows_total)
        ORDER BY quote_date DESC, ticker ASC
        {limit_sql}
    """
    return [(str(r[0]), str(r[1]), int(r[2])) for r in conn.execute(sql, tuple(params)).fetchall()]


def load_existing_expiration_sides(
    conn: sqlite3.Connection,
    ticker: str,
    quote_date: str,
    dte_min: int,
    dte_max: int,
) -> List[Tuple[str, str]]:
    cur = conn.execute(
        """
        SELECT DISTINCT expiration_ts, side
        FROM chain_snapshots
        WHERE ticker=? AND quote_date=?
          AND expiration_ts IS NOT NULL
          AND side IN ('call', 'put')
          AND dte BETWEEN ? AND ?
        ORDER BY expiration_ts, side
        """,
        (ticker.upper(), quote_date, float(dte_min), float(dte_max)),
    )
    out: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for expiration_ts, side in cur.fetchall():
        exp = normalise_expiration_ts(expiration_ts)
        if not exp:
            continue
        key = (exp, str(side).lower())
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def fetch_expirations_from_api(
    ticker: str,
    quote_date: str,
    dte_min: int,
    dte_max: int,
    token: str,
    timeout: int,
) -> List[Tuple[str, str]]:
    url = EXPIRATIONS_URL.format(ticker=ticker.upper())
    response = requests.get(
        url,
        headers={"Authorization": f"Token {token}"},
        params={"date": quote_date},
        timeout=timeout,
    )
    try:
        payload = response.json()
    except Exception:
        return []
    expirations = payload.get("expirations")
    if not isinstance(expirations, list):
        return []
    qd = date.fromisoformat(quote_date)
    out: List[Tuple[str, str]] = []
    for exp_value in expirations:
        try:
            exp = date.fromisoformat(str(exp_value)[:10])
        except Exception:
            continue
        dte = (exp - qd).days
        if dte_min <= dte <= dte_max:
            out.append((exp.isoformat(), "call"))
            out.append((exp.isoformat(), "put"))
    return out


def build_chain_params(args: argparse.Namespace, quote_date: str, expiration: str, side: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "date": quote_date,
        "expiration": expiration,
        "side": side,
        "range": "all",
        "minOpenInterest": int(args.min_open_interest),
    }
    if args.strike_limit > 0:
        params["strikeLimit"] = int(args.strike_limit)
    if not args.no_force_columns:
        params["columns"] = DEFAULT_COLUMNS
    return params


def fetch_chain_task(task: Dict[str, Any]) -> Dict[str, Any]:
    ticker = task["ticker"]
    quote_date = task["quote_date"]
    expiration = task["expiration"]
    side = task["side"]
    params = task["params"]
    token = task["token"]
    timeout = int(task["timeout"])
    retries = int(task["retries"])
    sleep = float(task["sleep"])
    key = task["audit_key"]
    url = CHAIN_URL.format(ticker=ticker.upper())
    started = utc_now()
    if sleep > 0:
        time.sleep(sleep)
    last_error = ""
    response_status_code = 0
    payload: Dict[str, Any] = {}
    for attempt in range(max(1, retries + 1)):
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Token {token}"},
                params=params,
                timeout=timeout,
            )
            response_status_code = response.status_code
            try:
                payload = response.json()
            except Exception:
                payload = {"s": "error", "errmsg": response.text[:500]}
            if response.status_code == 429 and attempt < retries:
                wait = min(60.0, 10.0 * (attempt + 1))
                last_error = f"HTTP 429 rate limited; waited {wait}s"
                time.sleep(wait)
                continue
            if 500 <= response.status_code < 600 and attempt < retries:
                wait = min(30.0, 2.0 * (attempt + 1))
                last_error = f"HTTP {response.status_code}"
                time.sleep(wait)
                continue
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(30.0, 2.0 * (attempt + 1)))
                continue
            payload = {"s": "error", "errmsg": last_error}
    api_status = response_status(payload, response_status_code)
    row_count = len(payload.get("optionSymbol", [])) if isinstance(payload.get("optionSymbol"), list) else 0
    counts = {field: field_count(payload, field) for field in GREEK_FIELDS}
    greek_total = sum(counts.values())
    if api_status == "ok" and row_count > 0:
        if all(counts[field] == row_count for field in GREEK_FIELDS):
            status = "OK_FULL_GREEKS"
        elif greek_total > 0:
            status = "OK_PARTIAL_GREEKS"
        else:
            status = "OK_QUOTES_ONLY"
    elif api_status == "no_data":
        status = "NO_DATA"
    else:
        status = "ERROR"
    if api_status == "ok" and "s" not in payload:
        payload["s"] = "ok"
    rows = normalize_marketdata_chain(payload, ticker, quote_date) if api_status == "ok" else []
    for row in rows:
        row["source"] = "marketdata.app.expiration_greeks"
    return {
        "audit_key": key,
        "ticker": ticker,
        "quote_date": quote_date,
        "expiration": expiration,
        "side": side,
        "params": params,
        "http_status": response_status_code,
        "api_status": api_status,
        "status": status,
        "row_count": row_count,
        "counts": counts,
        "response_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "error": payload.get("errmsg", last_error) if isinstance(payload, dict) else last_error,
        "started_at_utc": started,
        "rows": rows,
    }


def upsert_chain_rows_conn(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(cols))
    assignments = []
    for col in cols:
        if col in {"ticker", "quote_date", "option_symbol"}:
            continue
        if col in {"iv", "delta", "gamma", "theta", "vega", "underlying_price"}:
            assignments.append(f"{col}=COALESCE(excluded.{col}, chain_snapshots.{col})")
        else:
            assignments.append(f"{col}=excluded.{col}")
    sql = (
        f"INSERT INTO chain_snapshots({','.join(cols)}) VALUES({placeholders}) "
        f"ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET {','.join(assignments)}"
    )
    conn.executemany(sql, [[row.get(col) for col in cols] for row in rows])
    return len(rows)


def upsert_provenance_conn(conn: sqlite3.Connection, rows: List[Dict[str, Any]], request_key: str) -> int:
    eligible = [
        row for row in rows
        if any(row.get(field) is not None for field in GREEK_FIELDS)
    ]
    if not eligible:
        return 0
    conn.executemany(
        """
        INSERT INTO chain_greek_provenance
        (ticker, quote_date, option_symbol, greek_source, request_audit_key, updated_at_utc)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET
            greek_source=excluded.greek_source,
            request_audit_key=excluded.request_audit_key,
            updated_at_utc=excluded.updated_at_utc
        """,
        [
            (
                row["ticker"],
                row["quote_date"],
                row["option_symbol"],
                "MARKETDATA_CHAIN_EXPIRATION",
                request_key,
                utc_now(),
            )
            for row in eligible
        ],
    )
    return len(eligible)


def write_audit_conn(conn: sqlite3.Connection, result: Dict[str, Any], rows_written: int) -> None:
    counts = result["counts"]
    conn.execute(
        """
        INSERT OR REPLACE INTO greek_rehydration_audit
        (audit_key,ticker,quote_date,expiration,side,params_json,http_status,api_status,status,
         row_count,rows_written,iv_count,delta_count,gamma_count,theta_count,vega_count,
         response_keys_json,error,started_at_utc,finished_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            result["audit_key"],
            result["ticker"],
            result["quote_date"],
            result["expiration"],
            result["side"],
            json.dumps(result["params"], sort_keys=True),
            int(result["http_status"] or 0),
            result["api_status"],
            result["status"],
            int(result["row_count"] or 0),
            int(rows_written or 0),
            int(counts.get("iv", 0)),
            int(counts.get("delta", 0)),
            int(counts.get("gamma", 0)),
            int(counts.get("theta", 0)),
            int(counts.get("vega", 0)),
            json.dumps(result["response_keys"]),
            str(result.get("error") or ""),
            result["started_at_utc"],
            utc_now(),
        ),
    )


def parse_csv_list(value: str) -> List[str]:
    if not value:
        return []
    return [part.strip().upper() for part in value.replace(",", " ").split() if part.strip()]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rehydrate PHANTOM Greeks using expiration-specific MarketData chain calls.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--tickers", default="")
    parser.add_argument("--max-target-dates", type=int, default=0, help="Ticker/date groups to inspect. 0 means all.")
    parser.add_argument("--max-requests", type=int, default=0, help="Expiration/side chain requests. 0 means all planned requests.")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.10)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--dte-min", type=int, default=7)
    parser.add_argument("--dte-max", type=int, default=60)
    parser.add_argument("--min-open-interest", type=int, default=1)
    parser.add_argument("--strike-limit", type=int, default=40)
    parser.add_argument("--no-force-columns", action="store_true", help="Do not send explicit Greek column request.")
    parser.add_argument("--discover-expirations-api", action="store_true", help="Use MarketData expirations endpoint when DB expiration list is empty.")
    parser.add_argument("--retry-quotes-only", action="store_true", help="Retry prior OK_QUOTES_ONLY rehydration attempts.")
    parser.add_argument("--allow-partial-greeks", action="store_true", help="Write vendor rows when only some Greek fields are present. Default is full MarketData Greeks only.")
    parser.add_argument("--execute", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
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
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    init_rehydration_schema(conn)
    completed = load_completed_request_keys(conn, bool(args.retry_quotes_only), bool(args.allow_partial_greeks))
    targets = load_targets(
        conn,
        args.start_date,
        args.end_date,
        parse_csv_list(args.tickers),
        int(args.max_target_dates),
    )

    tasks: List[Dict[str, Any]] = []
    for ticker, quote_date, _rows_total in targets:
        expiration_sides = load_existing_expiration_sides(conn, ticker, quote_date, args.dte_min, args.dte_max)
        if not expiration_sides and args.discover_expirations_api:
            expiration_sides = fetch_expirations_from_api(
                ticker, quote_date, args.dte_min, args.dte_max, token, int(args.timeout)
            )
        for expiration, side in expiration_sides:
            params = build_chain_params(args, quote_date, expiration, side)
            key = audit_key(ticker, quote_date, expiration, side, params)
            if key in completed:
                continue
            tasks.append({
                "audit_key": key,
                "ticker": ticker,
                "quote_date": quote_date,
                "expiration": expiration,
                "side": side,
                "params": params,
                "token": token,
                "timeout": int(args.timeout),
                "retries": int(args.retries),
                "sleep": float(args.sleep),
            })
            if args.max_requests > 0 and len(tasks) >= args.max_requests:
                break
        if args.max_requests > 0 and len(tasks) >= args.max_requests:
            break

    plan = {
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "db_path": str(db_path),
        "target_ticker_dates": len(targets),
        "planned_chain_requests": len(tasks),
        "workers": int(args.workers),
        "dte_window": [int(args.dte_min), int(args.dte_max)],
        "request_shape": "date + expiration + side",
        "force_columns": not bool(args.no_force_columns),
        "vendor_greek_policy": "FULL_MARKETDATA_GREEKS_ONLY" if not args.allow_partial_greeks else "ALLOW_PARTIAL_MARKETDATA_GREEKS",
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        conn.close()
        return 0

    totals = {
        "requests": 0,
        "ok_full_greeks": 0,
        "ok_partial_greeks": 0,
        "ok_quotes_only": 0,
        "no_data": 0,
        "errors": 0,
        "rows_seen": 0,
        "rows_written": 0,
        "provenance_rows": 0,
    }

    try:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
            futures = [pool.submit(fetch_chain_task, task) for task in tasks]
            for idx, future in enumerate(as_completed(futures), start=1):
                result = future.result()
                status = result["status"]
                rows = result["rows"]
                write_rows = bool(rows) and (
                    status == "OK_FULL_GREEKS" or
                    (status == "OK_PARTIAL_GREEKS" and bool(args.allow_partial_greeks))
                )
                rows_written = 0
                provenance_rows = 0
                if write_rows:
                    rows_written = upsert_chain_rows_conn(conn, rows)
                    provenance_rows = upsert_provenance_conn(conn, rows, result["audit_key"])
                write_audit_conn(conn, result, rows_written)
                if idx % 25 == 0:
                    conn.commit()
                totals["requests"] += 1
                totals["rows_seen"] += int(result["row_count"] or 0)
                totals["rows_written"] += rows_written
                totals["provenance_rows"] += provenance_rows
                if status == "OK_FULL_GREEKS":
                    totals["ok_full_greeks"] += 1
                elif status == "OK_PARTIAL_GREEKS":
                    totals["ok_partial_greeks"] += 1
                elif status == "OK_QUOTES_ONLY":
                    totals["ok_quotes_only"] += 1
                elif status == "NO_DATA":
                    totals["no_data"] += 1
                else:
                    totals["errors"] += 1
                if idx == 1 or idx % 25 == 0:
                    print(
                        f"[PHANTOM-GREEKS] {idx}/{len(tasks)} status={status} "
                        f"rows={result['row_count']} written={rows_written} "
                        f"iv={result['counts'].get('iv',0)} delta={result['counts'].get('delta',0)} "
                        f"gamma={result['counts'].get('gamma',0)} theta={result['counts'].get('theta',0)} "
                        f"vega={result['counts'].get('vega',0)}"
                    )
        conn.commit()
    finally:
        conn.close()

    print(json.dumps(totals, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
