"""G1 (ACK 17 Sep 2026): compute IV and Greeks locally for backfilled sessions (no API calls).

Drives scripts/phantom_compute_historical_greeks.py per session and per ticker chunk so every
query uses the (ticker, quote_date) index instead of scanning chain_snapshots. Fills nulls only
(no --overwrite-chain-greeks); rows already in options_greeks_history are skipped by the script.

Stop safely: create STOP in this folder; the driver finishes the current chunk and exits.

  venv\\Scripts\\python.exe Enhancements\\phase0\\greeks_backfill\\run_g1_greeks.py [--execute]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
DB = REPO / "data" / "phantom" / "phantom_history.db"
HERE = Path(__file__).resolve().parent
SESSIONS = ["2026-07-24", "2026-08-07", "2026-08-14", "2026-08-21", "2026-08-31", "2026-09-01", "2026-09-02",
            "2026-09-03", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15"]
CHUNK = 300


def tickers_for(session: str) -> list[str]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM backfill_audit WHERE status = 'OK' AND quote_date = ? AND rows_written > 0 "
            "ORDER BY ticker", (session,))]
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    receipt = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "mode": "EXECUTE" if args.execute else "DRY_RUN",
               "sessions": {}}
    log = (HERE / f"g1_{'execute' if args.execute else 'dry_run'}.log").open("a", encoding="utf-8")
    for session in SESSIONS:
        tickers = tickers_for(session)
        planned = 0
        for start in range(0, len(tickers), CHUNK):
            if (HERE / "STOP").exists():
                log.write(f"STOP file found before {session} chunk {start}\n")
                receipt["stopped"] = {"session": session, "chunk_start": start}
                (HERE / "g1_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                return 3
            chunk = tickers[start:start + CHUNK]
            cmd = [sys.executable, str(REPO / "scripts" / "phantom_compute_historical_greeks.py"),
                   "--start-date", session, "--end-date", session, "--tickers", ",".join(chunk),
                   "--workers", str(args.workers), "--batch-size", "25000"]
            if args.execute:
                cmd.append("--execute")
            result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
            log.write(f"== {session} chunk {start // CHUNK} tickers {len(chunk)} exit {result.returncode}\n")
            log.write(result.stdout[-3000:] + "\n")
            if result.returncode != 0:
                log.write(result.stderr[-3000:] + "\n")
                receipt["failed"] = {"session": session, "chunk_start": start, "stderr_tail": result.stderr[-1000:]}
                (HERE / "g1_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
                return result.returncode
            try:
                text = result.stdout
                plan = json.loads(text[text.index("{"):text.index("\n}\n") + 2]) if "\n}\n" in text else {}
                planned += int(plan.get("rows_targetable") or 0)
            except (ValueError, json.JSONDecodeError):
                pass
            log.flush()
        receipt["sessions"][session] = {"tickers": len(tickers), "rows_targetable": planned}
        print(f"{session}: tickers {len(tickers)} rows_targetable {planned}", flush=True)
    receipt["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    (HERE / f"g1_receipt_{'execute' if args.execute else 'dry_run'}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
