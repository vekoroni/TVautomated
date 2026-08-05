"""Compute missing PHANTOM historical option Greeks from local MarketData EOD rows."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compute_greeks_bs import compute_greeks_from_row
from options_db_writer import ensure_computed_greeks_schema, hydrate_chain_snapshots, upsert_greek_records, write_run_audit


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_db_path(repo_root: Path) -> Path:
    return repo_root / "data" / "phantom" / "phantom_history.db"


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def normalise_tickers(raw: str) -> List[str]:
    if not raw:
        return []
    out = []
    seen = set()
    for value in raw.replace(",", " ").split():
        ticker = value.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append(ticker)
    return out


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def read_risk_free_rate(macro_path: Path, fallback: float) -> float:
    if not macro_path.exists():
        return fallback
    try:
        payload = json.loads(macro_path.read_text(encoding="utf-8"))
    except Exception:
        return fallback

    key_candidates = {
        "risk_free_rate",
        "riskFreeRate",
        "risk_free",
        "rf_rate",
        "treasury_3m",
        "t_bill_3m",
        "fed_funds_rate",
    }

    def walk(value: Any) -> Optional[float]:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key) in key_candidates:
                    try:
                        out = float(item)
                        if out > 1.0:
                            out /= 100.0
                        if 0.0 <= out <= 0.25:
                            return out
                    except Exception:
                        pass
            for item in value.values():
                found = walk(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item)
                if found is not None:
                    return found
        return None

    found = walk(payload)
    return found if found is not None else fallback


def build_where(args: argparse.Namespace, tickers: Sequence[str], history_table_exists: bool) -> tuple[str, List[Any]]:
    clauses = ["1=1"]
    params: List[Any] = []
    if args.start_date:
        clauses.append("c.quote_date >= ?")
        params.append(args.start_date)
    if args.end_date:
        clauses.append("c.quote_date <= ?")
        params.append(args.end_date)
    if tickers:
        placeholders = ",".join(["?"] * len(tickers))
        clauses.append(f"c.ticker IN ({placeholders})")
        params.extend(tickers)
    if not args.all_rows:
        clauses.append("(c.iv IS NULL OR c.delta IS NULL OR c.gamma IS NULL OR c.theta IS NULL OR c.vega IS NULL)")
    if history_table_exists and not args.recompute:
        if args.retry_failures:
            clauses.append("(g.contract_symbol IS NULL OR g.quality_status != 'OK')")
        else:
            clauses.append("g.contract_symbol IS NULL")
    return " AND ".join(clauses), params


def count_targets(conn: sqlite3.Connection, args: argparse.Namespace, tickers: Sequence[str]) -> int:
    history_exists = table_exists(conn, "options_greeks_history")
    where_sql, params = build_where(args, tickers, history_exists)
    join_sql = ""
    if history_exists:
        join_sql = """
        LEFT JOIN options_greeks_history g
          ON g.ticker=c.ticker
         AND g.snapshot_date=c.quote_date
         AND g.contract_symbol=c.option_symbol
        """
    cur = conn.execute(f"SELECT COUNT(*) FROM chain_snapshots c {join_sql} WHERE {where_sql}", params)
    return int(cur.fetchone()[0] or 0)


def fetch_batch(conn: sqlite3.Connection, args: argparse.Namespace, tickers: Sequence[str], limit: int) -> List[Dict[str, Any]]:
    history_exists = table_exists(conn, "options_greeks_history")
    where_sql, params = build_where(args, tickers, history_exists)
    join_sql = ""
    if history_exists:
        join_sql = """
        LEFT JOIN options_greeks_history g
          ON g.ticker=c.ticker
         AND g.snapshot_date=c.quote_date
         AND g.contract_symbol=c.option_symbol
        """
    sql = f"""
        SELECT
            c.ticker,
            c.quote_date,
            c.option_symbol,
            c.expiration_ts,
            c.side,
            c.strike,
            c.dte,
            c.bid,
            c.ask,
            c.mid,
            c.last,
            c.open_interest,
            c.volume,
            c.underlying_price
        FROM chain_snapshots c
        {join_sql}
        WHERE {where_sql}
        ORDER BY c.quote_date, c.ticker, c.option_symbol
        LIMIT ?
    """
    rows = conn.execute(sql, params + [int(limit)]).fetchall()
    return [row_to_dict(row) for row in rows]


def expiration_date_from_ts(value: Any) -> str:
    try:
        if value is None or value == "":
            return ""
        return datetime.fromtimestamp(int(value), tz=timezone.utc).date().isoformat()
    except Exception:
        return ""


def compute_record(row: Dict[str, Any], risk_free_rate: float) -> Dict[str, Any]:
    result = compute_greeks_from_row(row, risk_free_rate=risk_free_rate)
    payload = result.as_dict()
    return {
        "ticker": str(row.get("ticker") or "").upper(),
        "contract_symbol": str(row.get("option_symbol") or ""),
        "snapshot_date": str(row.get("quote_date") or ""),
        "expiration_ts": row.get("expiration_ts"),
        "expiration_date": expiration_date_from_ts(row.get("expiration_ts")),
        "strike": row.get("strike"),
        "dte": row.get("dte"),
        "side": row.get("side"),
        "bid": row.get("bid"),
        "ask": row.get("ask"),
        "mid": row.get("mid"),
        "last": row.get("last"),
        "open_interest": row.get("open_interest"),
        "volume": row.get("volume"),
        "underlying_price": row.get("underlying_price"),
        "market_price": payload.get("market_price"),
        "risk_free_rate": payload.get("risk_free_rate"),
        "price_source": payload.get("price_source"),
        "iv": payload.get("iv"),
        "delta": payload.get("delta"),
        "gamma": payload.get("gamma"),
        "theta": payload.get("theta"),
        "vega": payload.get("vega"),
        "greeks_source": "COMPUTED_BS",
        "quality_status": payload.get("quality_status"),
        "quality_flags": payload.get("quality_flags"),
        "solver_iterations": payload.get("solver_iterations"),
        "solver_error": payload.get("solver_error"),
    }


def compute_records(rows: List[Dict[str, Any]], risk_free_rate: float, workers: int) -> List[Dict[str, Any]]:
    if workers <= 1 or len(rows) < 1000:
        return [compute_record(row, risk_free_rate) for row in rows]
    with ProcessPoolExecutor(max_workers=int(workers)) as pool:
        return list(pool.map(_compute_record_tuple, [(row, risk_free_rate) for row in rows], chunksize=250))


def _compute_record_tuple(args: tuple[Dict[str, Any], float]) -> Dict[str, Any]:
    row, risk_free_rate = args
    return compute_record(row, risk_free_rate)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute missing PHANTOM historical option Greeks from local EOD rows.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--tickers", default="", help="Optional comma/space separated ticker filter.")
    parser.add_argument("--max-rows", type=int, default=0, help="0 means all currently targetable rows.")
    parser.add_argument("--batch-size", type=int, default=25000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--risk-free-rate", type=float, default=0.045)
    parser.add_argument("--macro-path", default="")
    parser.add_argument("--all-rows", action="store_true", help="Target all chain rows, not only rows missing Greeks.")
    parser.add_argument("--recompute", action="store_true", help="Recompute rows already present in options_greeks_history.")
    parser.add_argument("--retry-failures", action="store_true", help="Retry rows that previously produced a non-OK computed result.")
    parser.add_argument("--overwrite-chain-greeks", action="store_true", help="Overwrite existing chain Greeks instead of filling nulls.")
    parser.add_argument("--no-chain-update", action="store_true", help="Write options_greeks_history only; do not hydrate chain_snapshots.")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    db_path = Path(args.db_path).resolve() if args.db_path else default_db_path(repo_root)
    macro_path = Path(args.macro_path).resolve() if args.macro_path else repo_root / "dropbox" / "macro" / "macro_intelligence_latest.json"
    risk_free_rate = read_risk_free_rate(macro_path, args.risk_free_rate)
    tickers = normalise_tickers(args.tickers)
    started = utc_now()
    run_id = datetime.now(timezone.utc).strftime("computed_greeks_%Y%m%d_%H%M%S")

    if not db_path.exists():
        print(json.dumps({"status": "error", "error": f"DB not found: {db_path}"}, indent=2))
        return 2

    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Large date-bounded maintenance runs can require an ORDER BY working
        # set. Keep it in memory so SQLite does not depend on an inaccessible
        # or capacity-constrained system temp directory mid-run.
        conn.execute("PRAGMA temp_store=MEMORY")
        ensure_computed_greeks_schema(conn)
        conn.commit()

        total_targeted = count_targets(conn, args, tickers)
        requested = total_targeted if args.max_rows <= 0 else min(total_targeted, int(args.max_rows))
        preview = fetch_batch(conn, args, tickers, min(5, max(1, requested))) if requested else []
        plan = {
            "mode": "EXECUTE" if args.execute else "DRY_RUN",
            "runner": "computed_bs_greeks",
            "db_path": str(db_path),
            "start_date": args.start_date or None,
            "end_date": args.end_date or None,
            "tickers": tickers[:20],
            "risk_free_rate": risk_free_rate,
            "rows_targetable": total_targeted,
            "rows_planned": requested,
            "batch_size": args.batch_size,
            "workers": args.workers,
            "chain_snapshots_will_update": not args.no_chain_update,
            "sample": [
                {
                    "ticker": r.get("ticker"),
                    "quote_date": r.get("quote_date"),
                    "option_symbol": r.get("option_symbol"),
                    "side": r.get("side"),
                    "strike": r.get("strike"),
                    "dte": r.get("dte"),
                    "mid": r.get("mid"),
                    "underlying_price": r.get("underlying_price"),
                }
                for r in preview
            ],
        }
        print(json.dumps(plan, indent=2))
        if not args.execute:
            return 0

        processed = 0
        ok = 0
        chain_updated = 0
        status_counts: Counter[str] = Counter()
        while processed < requested:
            remaining = requested - processed
            limit = min(max(1, int(args.batch_size)), remaining)
            rows = fetch_batch(conn, args, tickers, limit)
            if not rows:
                break
            records = compute_records(rows, risk_free_rate, max(1, int(args.workers)))
            upsert_greek_records(conn, records)
            if not args.no_chain_update:
                chain_updated += hydrate_chain_snapshots(conn, records, overwrite=bool(args.overwrite_chain_greeks))
            conn.commit()

            processed += len(records)
            batch_status = Counter(str(rec.get("quality_status") or "UNKNOWN") for rec in records)
            status_counts.update(batch_status)
            ok = sum(count for status, count in status_counts.items() if str(status).startswith("OK"))
            print(
                f"[PHANTOM-GREEKS] processed={processed}/{requested} "
                f"ok={ok} failed={processed-ok} chain_updated={chain_updated} "
                f"last_batch={dict(batch_status)}"
            )

        summary = {
            "run_id": run_id,
            "db_path": str(db_path),
            "start_date": args.start_date or None,
            "end_date": args.end_date or None,
            "tickers": ",".join(tickers),
            "rows_targeted": requested,
            "rows_processed": processed,
            "rows_ok": ok,
            "rows_failed": processed - ok,
            "chain_rows_updated": chain_updated,
            "status_counts": dict(status_counts),
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
        }
        write_run_audit(conn, summary)
        conn.commit()
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
