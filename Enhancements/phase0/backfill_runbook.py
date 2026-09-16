"""P0-1 history backfill runbook (Enhancements/phase0/PHASE0_PLAN_AND_BACKFILL_DESIGN.md).

Orchestrates the existing, audited scripts/run_phantom_backfill_parallel.py one
session at a time. It never requests a (ticker, session) already present in
Phantom chain_snapshots, so no captured row is overwritten.

Usage:
  python Enhancements/phase0/backfill_runbook.py plan    --sessions 2026-09-15,2026-09-14
  python Enhancements/phase0/backfill_runbook.py execute --sessions ... --credit-cap 30000 --workers 8
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHANTOM = REPO / "data" / "phantom" / "phantom_history.db"
UNIVERSE = REPO / "data" / "universe" / "polygon_liquid_universe.csv"
TOOL = REPO / "scripts" / "run_phantom_backfill_parallel.py"
PYTHON = REPO / "venv" / "Scripts" / "python.exe"
RECEIPTS = Path(__file__).resolve().parent / "backfill_receipts"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_universe() -> list[str]:
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        cols = {c.lower(): c for c in reader.fieldnames or []}
        col = cols.get("ticker") or cols.get("symbol")
        seen: list[str] = []
        for row in reader:
            t = str(row.get(col) or "").strip().upper()
            if t and t not in seen:
                seen.append(t)
    return seen


def session_state(session: str) -> dict:
    con = sqlite3.connect(f"file:{PHANTOM.as_posix()}?mode=ro", uri=True)
    try:
        present = {r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM chain_snapshots WHERE quote_date = ?", (session,))}
        rows = con.execute("SELECT COUNT(*) FROM chain_snapshots WHERE quote_date = ?", (session,)).fetchone()[0]
        audit = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(status='OK'),0), COALESCE(SUM(status='NO_DATA'),0), "
            "COALESCE(SUM(status NOT IN ('OK','NO_DATA')),0), COALESCE(SUM(estimated_credits),0) "
            "FROM backfill_audit WHERE quote_date = ?", (session,)).fetchone()
    finally:
        con.close()
    return {"present_tickers": present, "rows": rows,
            "audit": dict(zip(["requests", "ok", "no_data", "errors", "credits"], audit))}


def plan(sessions: list[str]) -> list[dict]:
    universe = load_universe()
    out = []
    for s in sessions:
        st = session_state(s)
        missing = [t for t in universe if t not in st["present_tickers"]]
        out.append({"session": s, "weekday": date.fromisoformat(s).weekday(),
                    "universe": len(universe), "present": len(st["present_tickers"]),
                    "missing": missing, "rows_before": st["rows"], "audit_before": st["audit"]})
    return out


def run_tool(item: dict, credit_cap: int, workers: int, execute: bool) -> int:
    cmd = [str(PYTHON), str(TOOL), "--end-date", item["session"], "--weekday", str(item["weekday"]),
           "--years", "0", "--workers", str(workers), "--credit-cap", str(credit_cap)]
    if len(item["missing"]) < item["universe"]:
        cmd += ["--tickers", ",".join(item["missing"])]
    if execute:
        cmd.append("--execute")
    return subprocess.call(cmd, cwd=str(REPO))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["plan", "execute"])
    p.add_argument("--sessions", required=True)
    p.add_argument("--credit-cap", type=int, default=30000)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    sessions = [s.strip() for s in a.sessions.split(",") if s.strip()]
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    for item in plan(sessions):
        summary = {k: v for k, v in item.items() if k != "missing"}
        summary["missing_count"] = len(item["missing"])
        print(json.dumps(summary), flush=True)
        if not item["missing"]:
            print(f"SKIP {item['session']}: nothing missing", flush=True)
            continue
        started = utc_now()
        code = run_tool(item, a.credit_cap, a.workers, a.mode == "execute")
        if a.mode != "execute":
            continue
        after = session_state(item["session"])
        receipt = {
            "contract": "phase0-backfill-receipt-v1", "session": item["session"],
            "started_at_utc": started, "finished_at_utc": utc_now(), "tool_exit_code": code,
            "universe": item["universe"], "present_before": item["present"],
            "requested_tickers": len(item["missing"]), "present_after": len(after["present_tickers"]),
            "rows_before": item["rows_before"], "rows_after": after["rows"],
            "audit_before": item["audit_before"], "audit_after": after["audit"],
            "pre_existing_tickers_preserved": item["present"] <= len(after["present_tickers"]),
        }
        (RECEIPTS / f"receipt_{item['session']}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt), flush=True)
        if code != 0:
            print(f"STOP: tool exit code {code} on {item['session']}", flush=True)
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
