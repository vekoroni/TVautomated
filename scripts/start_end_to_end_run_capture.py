#!/usr/bin/env python3
"""Start the AVSHUNTER end-to-end run capture as a detached process."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "data" / "output" / "qa"
LOG_DIR = ROOT / "data" / "logs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Detach the AVSHUNTER end-to-end run capture.")
    parser.add_argument("--interval", type=int, default=120)
    parser.add_argument("--timeout-minutes", type=float, default=420.0)
    parser.add_argument("--stall-minutes", type=float, default=15.0)
    parser.add_argument("--settle-seconds", type=int, default=180)
    parser.add_argument("--run-id", default="", help="Optional fixed run id. Otherwise waits for the next run.")
    args = parser.parse_args()

    QA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_log = LOG_DIR / f"e2e_run_capture_{stamp}.out.log"
    err_log = LOG_DIR / f"e2e_run_capture_{stamp}.err.log"
    capture = ROOT / "scripts" / "capture_end_to_end_run.py"

    cmd = [
        sys.executable,
        "-u",
        str(capture),
        "--interval",
        str(args.interval),
        "--timeout-minutes",
        str(args.timeout_minutes),
        "--stall-minutes",
        str(args.stall_minutes),
        "--settle-seconds",
        str(args.settle_seconds),
    ]
    if args.run_id:
        cmd.extend(["--run-id", args.run_id])
    else:
        cmd.append("--wait-for-new-run")

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NO_WINDOW
        )

    out_fh = out_log.open("a", encoding="utf-8", errors="replace")
    err_fh = err_log.open("a", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=out_fh,
        stderr=err_fh,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creationflags,
    )
    out_fh.close()
    err_fh.close()

    receipt = {
        "started_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pid": proc.pid,
        "command": cmd,
        "cwd": str(ROOT),
        "stdout_log": str(out_log),
        "stderr_log": str(err_log),
        "interval_seconds": args.interval,
        "timeout_minutes": args.timeout_minutes,
        "status": "STARTED",
        "latest_capture_report": str(QA_DIR / "e2e_run_capture_latest.json"),
    }
    receipt_path = QA_DIR / "e2e_run_capture_process.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
