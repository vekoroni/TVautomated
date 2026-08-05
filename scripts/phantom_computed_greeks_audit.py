"""Audit PHANTOM historical computed-Greek coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from options_db_writer import ensure_computed_greeks_schema


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_db_path(repo_root: Path) -> Path:
    return repo_root / "data" / "phantom" / "phantom_history.db"


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [{k: row[k] for k in row.keys()} for row in rows]


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return cur.fetchone() is not None


def date_filter(alias: str, start_date: str, end_date: str) -> tuple[str, list]:
    clauses = []
    params: list = []
    if start_date:
        clauses.append(f"{alias} >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{alias} <= ?")
        params.append(end_date)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PHANTOM computed Greek coverage.")
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--db-path", default="")
    parser.add_argument("--start-date", default="")
    parser.add_argument("--end-date", default="")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    db_path = Path(args.db_path).resolve() if args.db_path else default_db_path(repo_root)
    if not db_path.exists():
        print(json.dumps({"status": "error", "error": f"DB not found: {db_path}"}, indent=2))
        return 2

    conn = sqlite3.connect(str(db_path), timeout=120)
    conn.row_factory = sqlite3.Row
    try:
        ensure_computed_greeks_schema(conn)
        conn.commit()
        chain_where, chain_params = date_filter("quote_date", args.start_date, args.end_date)
        greek_where, greek_params = date_filter("snapshot_date", args.start_date, args.end_date)

        chain_total = scalar(conn, f"SELECT COUNT(*) FROM chain_snapshots WHERE 1=1{chain_where}", tuple(chain_params))
        chain_full = scalar(
            conn,
            f"""
            SELECT COUNT(*) FROM chain_snapshots
            WHERE iv IS NOT NULL AND delta IS NOT NULL AND gamma IS NOT NULL AND theta IS NOT NULL AND vega IS NOT NULL
            {chain_where}
            """,
            tuple(chain_params),
        )
        chain_missing = chain_total - chain_full
        ticker_count = scalar(conn, f"SELECT COUNT(DISTINCT ticker) FROM chain_snapshots WHERE 1=1{chain_where}", tuple(chain_params))
        date_count = scalar(conn, f"SELECT COUNT(DISTINCT quote_date) FROM chain_snapshots WHERE 1=1{chain_where}", tuple(chain_params))

        status_rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT quality_status, COUNT(*) AS rows
                FROM options_greeks_history
                WHERE 1=1{greek_where}
                GROUP BY quality_status
                ORDER BY rows DESC
                """,
                tuple(greek_params),
            ).fetchall()
        )
        source_rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT greeks_source, COUNT(*) AS rows
                FROM options_greeks_history
                WHERE 1=1{greek_where}
                GROUP BY greeks_source
                ORDER BY rows DESC
                """,
                tuple(greek_params),
            ).fetchall()
        )
        failure_rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT ticker, snapshot_date, contract_symbol, quality_status, quality_flags, solver_error
                FROM options_greeks_history
                WHERE quality_status NOT LIKE 'OK%' {greek_where}
                ORDER BY snapshot_date DESC, ticker, contract_symbol
                LIMIT 10
                """,
                tuple(greek_params),
            ).fetchall()
        )

        summary = {
            "db_path": str(db_path),
            "date_filter": {"start_date": args.start_date or None, "end_date": args.end_date or None},
            "chain_snapshots": {
                "rows_total": chain_total,
                "rows_with_all_greeks": chain_full,
                "rows_missing_any_greek": chain_missing,
                "coverage_pct": round((chain_full / chain_total * 100.0), 2) if chain_total else 0.0,
                "ticker_count": ticker_count,
                "quote_date_count": date_count,
            },
            "computed_greeks_history_by_status": status_rows,
            "computed_greeks_history_by_source": source_rows,
            "sample_failures": failure_rows,
        }
        print(json.dumps(summary, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
