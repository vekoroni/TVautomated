"""PHANTOM parallel MarketData.app historical options backfill.

Fetches in parallel, writes through one serialized SQLite writer, and preserves
the existing PHANTOM query-key/audit contract so resume remains safe.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import queue
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from phantom_database import PhantomDatabase, normalize_marketdata_chain


MD_CHAIN_URL = "https://api.marketdata.app/v1/options/chain/{ticker}/"
INVALID_TICKERS = {"", "SYM", "SYMBOL", "TICKER", "UNKNOWN", "N/A", "NA", "NULL", "NONE", "NAN"}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
DONE = object()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_ticker(value: Any) -> str:
    ticker = str(value or "").strip().upper()
    if ticker in INVALID_TICKERS:
        return ""
    if not TICKER_RE.match(ticker):
        return ""
    return ticker


def last_weekday_on_or_before(value: date, weekday: int) -> date:
    current = value
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def latest_completed_date(include_today: bool) -> date:
    current = date.today()
    if not include_today:
        current -= timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def daterange_weekly(start: date, end: date, weekday: int, newest_first: bool = True) -> List[date]:
    current = last_weekday_on_or_before(end, weekday)
    out: List[date] = []
    while current >= start:
        out.append(current)
        current -= timedelta(days=7)
    if not newest_first:
        out = sorted(out)
    return out


def load_tickers(repo_root: Path, run_id: str, tickers: str, universe_path: str, max_tickers: int) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []

    def add(value: Any) -> None:
        ticker = clean_ticker(value)
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)

    if tickers:
        for value in tickers.replace(",", " ").split():
            add(value)
            if max_tickers > 0 and len(out) >= max_tickers:
                return out
        return out

    if universe_path:
        path = Path(universe_path)
    else:
        path = repo_root / "data" / "universe" / "polygon_liquid_universe.csv"
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = {str(c).lower(): c for c in (reader.fieldnames or [])}
            col = cols.get("ticker") or cols.get("symbol")
            if col:
                for row in reader:
                    add(row.get(col))
                    if max_tickers > 0 and len(out) >= max_tickers:
                        return out
    if out:
        return out

    # Last-resort compatibility with the serial runner: load tickers from latest run outputs.
    candidates = [
        repo_root / "data" / "output" / "runs" / run_id / "options" / f"options_intelligence_{run_id}.csv",
        repo_root / "data" / "output" / "runs" / run_id / "superbrain" / f"eil_enriched_{run_id}.csv",
        repo_root / "data" / "output" / "runs" / run_id / "execution" / f"execution_v3_5_{run_id}.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = {str(c).lower(): c for c in (reader.fieldnames or [])}
            col = cols.get("ticker") or cols.get("symbol")
            if not col:
                continue
            for row in reader:
                add(row.get(col))
                if max_tickers > 0 and len(out) >= max_tickers:
                    return out
    return out


def query_key(ticker: str, quote_date: str, params: Dict[str, Any]) -> str:
    raw = json.dumps({"ticker": ticker, "date": quote_date, "params": params}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def estimated_credits(row_count: int) -> int:
    return max(1, int(math.ceil(max(1, row_count) / 1000.0)))


def params_for(qd: date, strike_limit: int, min_open_interest: int) -> Dict[str, Any]:
    return {
        "date": qd.isoformat(),
        "from": (qd + timedelta(days=7)).isoformat(),
        "to": (qd + timedelta(days=60)).isoformat(),
        "strikeLimit": int(strike_limit),
        "range": "all",
        "minOpenInterest": int(min_open_interest),
    }


def load_completed_keys(db_path: Path) -> Set[str]:
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        cur = conn.execute("SELECT query_key FROM backfill_audit WHERE status IN ('OK','NO_DATA')")
        return {str(row[0]) for row in cur.fetchall()}
    finally:
        conn.close()


def fetch_chain(session: requests.Session, api_key: str, ticker: str, params: Dict[str, Any], timeout: int, retries: int) -> Dict[str, Any]:
    url = MD_CHAIN_URL.format(ticker=ticker.upper())
    headers = {"Authorization": f"Token {api_key}"}
    last_error = ""
    for attempt in range(max(1, retries + 1)):
        try:
            r = session.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else min(60.0, 10.0 * (attempt + 1))
                time.sleep(wait)
                last_error = f"HTTP 429 rate limited; waited {wait}s"
                continue
            if 500 <= r.status_code < 600 and attempt < retries:
                time.sleep(min(30.0, 2.0 * (attempt + 1)))
                last_error = f"HTTP {r.status_code}: {r.text[:300]}"
                continue
            if not r.ok:
                # PHANTOM_NO_DATA_404_FIX: MarketData can return HTTP 404 with
                # a JSON body of {"s":"no_data"} for missing historical chains.
                # Treat that as permanent NO_DATA, not retryable ERROR.
                try:
                    payload = r.json()
                    if isinstance(payload, dict) and str(payload.get("s", "")).lower() == "no_data":
                        payload.setdefault("errmsg", f"HTTP {r.status_code}: no_data")
                        return payload
                except Exception:
                    pass
                return {"s": "error", "errmsg": f"HTTP {r.status_code}: {r.text[:300]}"}
            return r.json()
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(30.0, 2.0 * (attempt + 1)))
                continue
    return {"s": "error", "errmsg": last_error or "request failed"}


def upsert_chain_rows_conn(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(cols))
    assignments = ",".join([f"{c}=excluded.{c}" for c in cols if c not in {"ticker", "quote_date", "option_symbol"}])
    sql = (
        f"INSERT INTO chain_snapshots({','.join(cols)}) VALUES({placeholders}) "
        f"ON CONFLICT(ticker, quote_date, option_symbol) DO UPDATE SET {assignments}"
    )
    conn.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    return len(rows)


def write_backfill_audit_conn(
    conn: sqlite3.Connection,
    query_key_value: str,
    ticker: str,
    quote_date: str,
    params: Dict[str, Any],
    status: str,
    rows_written: int,
    credits: int,
    error: str,
    started_at_utc: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO backfill_audit
        (query_key,ticker,quote_date,params_json,status,rows_written,estimated_credits,error,started_at_utc,finished_at_utc)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (
            query_key_value,
            ticker.upper(),
            quote_date,
            json.dumps(params, sort_keys=True),
            status,
            int(rows_written or 0),
            int(credits or 0),
            str(error or ""),
            started_at_utc or utc_now(),
            utc_now(),
        ),
    )


def worker(
    ticker: str,
    quote_dates: List[date],
    completed_keys: Set[str],
    out_q: "queue.Queue[object]",
    stop_event: threading.Event,
    api_key: str,
    strike_limit: int,
    min_open_interest: int,
    max_no_data_streak: int,
    timeout: int,
    retries: int,
    sleep: float,
) -> None:
    session = requests.Session()
    fetched = 0
    skipped = 0
    no_data_streak = 0
    try:
        for qd in quote_dates:
            if stop_event.is_set():
                break
            qd_str = qd.isoformat()
            params = params_for(qd, strike_limit, min_open_interest)
            key = query_key(ticker, qd_str, params)
            if key in completed_keys:
                skipped += 1
                continue
            started = utc_now()
            data = fetch_chain(session, api_key, ticker, params, timeout, retries)
            status = str(data.get("s") or "").lower()
            if status == "ok":
                rows = normalize_marketdata_chain(data, ticker, qd_str)
                row_count = len(rows)
                out_q.put({
                    "kind": "result",
                    "query_key": key,
                    "ticker": ticker,
                    "quote_date": qd_str,
                    "params": params,
                    "status": "OK",
                    "rows": rows,
                    "rows_written": row_count,
                    "estimated_credits": estimated_credits(row_count),
                    "error": "",
                    "started_at_utc": started,
                })
                no_data_streak = 0
            elif status == "no_data":
                out_q.put({
                    "kind": "result",
                    "query_key": key,
                    "ticker": ticker,
                    "quote_date": qd_str,
                    "params": params,
                    "status": "NO_DATA",
                    "rows": [],
                    "rows_written": 0,
                    "estimated_credits": 1,
                    "error": data.get("errmsg", ""),
                    "started_at_utc": started,
                })
                no_data_streak += 1
                if no_data_streak >= max_no_data_streak:
                    out_q.put({"kind": "ticker_stop", "ticker": ticker, "reason": f"{no_data_streak} consecutive newest-first NO_DATA"})
                    break
            else:
                # Keep ERROR retryable on future resumes. Do not let transient HTTP
                # or TLS problems masquerade as permanent no-data.
                out_q.put({
                    "kind": "result",
                    "query_key": key,
                    "ticker": ticker,
                    "quote_date": qd_str,
                    "params": params,
                    "status": "ERROR",
                    "rows": [],
                    "rows_written": 0,
                    "estimated_credits": 1,
                    "error": data.get("errmsg", "unknown error"),
                    "started_at_utc": started,
                })
            fetched += 1
            if sleep > 0:
                time.sleep(sleep)
    except Exception as exc:
        out_q.put({"kind": "ticker_error", "ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        out_q.put({"kind": "ticker_done", "ticker": ticker, "fetched": fetched, "skipped": skipped})


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parallel PHANTOM historical options backfill.")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--run-id", default="")
    p.add_argument("--db-path", default="")
    p.add_argument("--universe-path", default="")
    p.add_argument("--end-date", default="", help="Last historical quote date to request, YYYY-MM-DD. Use this when the latest session is not yet published by MarketData.")
    p.add_argument("--data-lag-days", type=int, default=7, help="Safety lag for historical option-chain availability when --end-date is omitted.")
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--max-tickers", type=int, default=0, help="0 means no limit.")
    p.add_argument("--tickers", default="")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--credit-cap", type=int, default=0, help="0 means no cap. In-flight worker results may slightly overshoot.")
    p.add_argument("--strike-limit", type=int, default=40)
    p.add_argument("--min-open-interest", type=int, default=1)
    p.add_argument("--weekday", type=int, choices=[0, 1, 2, 3, 4], default=4)
    p.add_argument("--include-today", action="store_true")
    p.add_argument("--max-no-data-streak", type=int, default=12)
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--sleep", type=float, default=0.0, help="Per-worker sleep between calls.")
    p.add_argument("--commit-every", type=int, default=25)
    p.add_argument("--newest-first", action="store_true", default=True)
    p.add_argument("--oldest-first", action="store_true", help="Compatibility mode; newest-first is safer for newly optionable tickers.")
    p.add_argument("--execute", action="store_true")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    repo_root = Path(args.repo_root)
    db_path = Path(args.db_path) if args.db_path else repo_root / "data" / "phantom" / "phantom_history.db"
    db = PhantomDatabase(db_path=db_path, repo_root=repo_root)
    if args.execute:
        db.initialise()

    run_id = args.run_id
    if not run_id:
        runs_dir = repo_root / "data" / "output" / "runs"
        if runs_dir.exists():
            dirs = sorted([p.name for p in runs_dir.iterdir() if p.is_dir() and p.name != "latest"], reverse=True)
            run_id = dirs[0] if dirs else ""

    tickers = load_tickers(repo_root, run_id, args.tickers, args.universe_path, int(args.max_tickers))
    if not tickers:
        raise SystemExit("No tickers found for PHANTOM parallel backfill.")

    if getattr(args, "end_date", ""):
        end = date.fromisoformat(args.end_date)
    else:
        end = latest_completed_date(bool(args.include_today)) - timedelta(days=max(0, int(getattr(args, "data_lag_days", 7))))
    start = end - timedelta(days=365 * int(args.years))
    quote_dates = daterange_weekly(start, end, int(args.weekday), newest_first=not bool(args.oldest_first))
    completed_keys = load_completed_keys(db_path)

    remaining = 0
    for ticker in tickers:
        for qd in quote_dates:
            key = query_key(ticker, qd.isoformat(), params_for(qd, args.strike_limit, args.min_open_interest))
            if key not in completed_keys:
                remaining += 1

    plan = {
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "runner": "parallel",
        "db_path": str(db_path),
        "run_id": run_id,
        "ticker_count": len(tickers),
        "sample_tickers": tickers[:10],
        "date_count": len(quote_dates),
        "first_quote_date": quote_dates[-1].isoformat() if quote_dates else None,
        "last_quote_date": quote_dates[0].isoformat() if quote_dates else None,
        "date_order": "newest_first" if not args.oldest_first else "oldest_first",
        "planned_queries": len(tickers) * len(quote_dates),
        "already_completed_keys": len(completed_keys),
        "remaining_queries_before_no_data_stops": remaining,
        "workers": int(args.workers),
        "credit_cap": int(args.credit_cap),
        "commit_every": int(args.commit_every),
    }
    print(json.dumps(plan, indent=2), flush=True)
    if not args.execute:
        return 0

    api_key = os.environ.get("MARKETDATA_API_KEY", "").strip()
    if not api_key:
        env_path = repo_root / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("MARKETDATA_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        raise SystemExit("MARKETDATA_API_KEY not found in environment or .env")

    out_q: "queue.Queue[object]" = queue.Queue(maxsize=max(100, args.workers * 20))
    stop_event = threading.Event()
    counters = {
        "tickers_done": 0,
        "results": 0,
        "ok": 0,
        "no_data": 0,
        "error": 0,
        "rows_written": 0,
        "estimated_credits": 0,
        "ticker_errors": 0,
        "ticker_stops": 0,
    }
    last_log = time.monotonic()
    pending_commits = 0

    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as executor:
            for ticker in tickers:
                executor.submit(
                    worker,
                    ticker,
                    quote_dates,
                    completed_keys,
                    out_q,
                    stop_event,
                    api_key,
                    int(args.strike_limit),
                    int(args.min_open_interest),
                    int(args.max_no_data_streak),
                    int(args.timeout),
                    int(args.retries),
                    float(args.sleep),
                )

            while counters["tickers_done"] < len(tickers):
                item = out_q.get()
                if item is DONE:
                    continue
                if not isinstance(item, dict):
                    continue
                kind = item.get("kind")
                if kind == "result":
                    rows = item.get("rows") or []
                    if rows:
                        upsert_chain_rows_conn(conn, rows)
                    write_backfill_audit_conn(
                        conn,
                        str(item["query_key"]),
                        str(item["ticker"]),
                        str(item["quote_date"]),
                        dict(item["params"]),
                        str(item["status"]),
                        int(item.get("rows_written") or 0),
                        int(item.get("estimated_credits") or 0),
                        str(item.get("error") or ""),
                        str(item.get("started_at_utc") or utc_now()),
                    )
                    pending_commits += 1
                    counters["results"] += 1
                    counters["rows_written"] += int(item.get("rows_written") or 0)
                    counters["estimated_credits"] += int(item.get("estimated_credits") or 0)
                    status = str(item.get("status") or "").lower()
                    if status == "ok":
                        counters["ok"] += 1
                    elif status == "no_data":
                        counters["no_data"] += 1
                    else:
                        counters["error"] += 1

                    if pending_commits >= max(1, int(args.commit_every)):
                        conn.commit()
                        pending_commits = 0

                    if args.credit_cap and counters["estimated_credits"] >= int(args.credit_cap):
                        stop_event.set()

                    now = time.monotonic()
                    if now - last_log >= 15:
                        print(
                            "[PHANTOM-P] "
                            f"tickers_done={counters['tickers_done']}/{len(tickers)} "
                            f"results={counters['results']} ok={counters['ok']} no_data={counters['no_data']} "
                            f"errors={counters['error']} rows={counters['rows_written']} "
                            f"credits~{counters['estimated_credits']}",
                            flush=True,
                        )
                        last_log = now
                elif kind == "ticker_done":
                    counters["tickers_done"] += 1
                elif kind == "ticker_error":
                    counters["ticker_errors"] += 1
                    print(f"[PHANTOM-P] ticker_error {item.get('ticker')}: {item.get('error')}", flush=True)
                elif kind == "ticker_stop":
                    counters["ticker_stops"] += 1
                    print(f"[PHANTOM-P] ticker_stop {item.get('ticker')}: {item.get('reason')}", flush=True)

            if pending_commits:
                conn.commit()
    finally:
        conn.commit()
        conn.close()

    print(json.dumps(counters, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
