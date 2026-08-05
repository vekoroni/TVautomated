"""Audit PHANTOM Greek coverage and Greek rehydration status."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


def default_db_path(repo_root: str) -> Path:
    return Path(repo_root) / "data" / "phantom" / "phantom_history.db"


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Dict[str, Any]:
    conn.row_factory = sqlite3.Row
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PHANTOM Greek coverage.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else default_db_path(args.repo_root)
    if not db_path.exists():
        print(json.dumps({"status": "error", "error": f"DB not found: {db_path}"}, indent=2))
        return 2

    where = []
    params: List[Any] = []
    if args.start_date:
        where.append("quote_date >= ?")
        params.append(args.start_date)
    if args.end_date:
        where.append("quote_date <= ?")
        params.append(args.end_date)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    conn = sqlite3.connect(str(db_path), timeout=60)
    try:
        summary = fetch_one(
            conn,
            f"""
            SELECT
                COUNT(*) AS rows_total,
                COUNT(DISTINCT ticker) AS tickers,
                COUNT(DISTINCT quote_date) AS quote_dates,
                SUM(CASE WHEN iv IS NOT NULL THEN 1 ELSE 0 END) AS iv_rows,
                SUM(CASE WHEN delta IS NOT NULL THEN 1 ELSE 0 END) AS delta_rows,
                SUM(CASE WHEN gamma IS NOT NULL THEN 1 ELSE 0 END) AS gamma_rows,
                SUM(CASE WHEN theta IS NOT NULL THEN 1 ELSE 0 END) AS theta_rows,
                SUM(CASE WHEN vega IS NOT NULL THEN 1 ELSE 0 END) AS vega_rows,
                SUM(CASE WHEN raw_json IS NOT NULL AND raw_json != '' THEN 1 ELSE 0 END) AS raw_json_rows
            FROM chain_snapshots
            {where_sql}
            """,
            tuple(params),
        )
        by_date = fetch_all(
            conn,
            f"""
            SELECT quote_date,
                   COUNT(*) AS rows_total,
                   SUM(CASE WHEN iv IS NOT NULL THEN 1 ELSE 0 END) AS iv_rows,
                   SUM(CASE WHEN delta IS NOT NULL THEN 1 ELSE 0 END) AS delta_rows,
                   SUM(CASE WHEN gamma IS NOT NULL THEN 1 ELSE 0 END) AS gamma_rows,
                   SUM(CASE WHEN theta IS NOT NULL THEN 1 ELSE 0 END) AS theta_rows,
                   SUM(CASE WHEN vega IS NOT NULL THEN 1 ELSE 0 END) AS vega_rows
            FROM chain_snapshots
            {where_sql}
            GROUP BY quote_date
            ORDER BY quote_date DESC
            LIMIT ?
            """,
            tuple(params + [args.top]),
        )
        missing = fetch_all(
            conn,
            f"""
            SELECT ticker, quote_date, COUNT(*) AS rows_total,
                   SUM(CASE WHEN iv IS NOT NULL THEN 1 ELSE 0 END) AS iv_rows,
                   SUM(CASE WHEN delta IS NOT NULL THEN 1 ELSE 0 END) AS delta_rows,
                   SUM(CASE WHEN gamma IS NOT NULL THEN 1 ELSE 0 END) AS gamma_rows,
                   SUM(CASE WHEN theta IS NOT NULL THEN 1 ELSE 0 END) AS theta_rows,
                   SUM(CASE WHEN vega IS NOT NULL THEN 1 ELSE 0 END) AS vega_rows
            FROM chain_snapshots
            {where_sql}
            GROUP BY ticker, quote_date
            HAVING rows_total > 0
               AND (iv_rows < rows_total OR delta_rows < rows_total OR gamma_rows < rows_total
                    OR theta_rows < rows_total OR vega_rows < rows_total)
            ORDER BY rows_total DESC
            LIMIT ?
            """,
            tuple(params + [args.top]),
        )
        rehydration_status = []
        if table_exists(conn, "greek_rehydration_audit"):
            rehydration_status = fetch_all(
                conn,
                """
                SELECT status, COUNT(*) AS requests,
                       SUM(row_count) AS rows_seen,
                       SUM(rows_written) AS rows_written,
                       SUM(iv_count) AS iv_count,
                       SUM(delta_count) AS delta_count,
                       SUM(gamma_count) AS gamma_count,
                       SUM(theta_count) AS theta_count,
                       SUM(vega_count) AS vega_count
                FROM greek_rehydration_audit
                GROUP BY status
                ORDER BY requests DESC
                """,
            )

        print(json.dumps({
            "db_path": str(db_path),
            "date_filter": {"start": args.start_date or None, "end": args.end_date or None},
            "summary": summary,
            "recent_date_coverage": by_date,
            "largest_missing_ticker_dates": missing,
            "rehydration_status": rehydration_status,
        }, indent=2, sort_keys=True))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
