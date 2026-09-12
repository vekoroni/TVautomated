#!/usr/bin/env python3
"""Refresh governed macro inputs, local GEX, and the combined macro packet."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.us_money_index_contract import load_us_money_index_sidecar  # noqa: E402
from contracts.macro_file_contract import market_data_directory  # noqa: E402
from scripts.build_local_gex import build_local_gex  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default="latest-completed")
    parser.add_argument("--skip-gex", action="store_true")
    parser.add_argument("--skip-macro-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    session = None if args.session == "latest-completed" else date.fromisoformat(args.session)
    usmi_path = ROOT / "dropbox" / "macro" / "avshunter_us_money_index.json"
    report: dict = {
        "contract_version": "macro_refresh_report_v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_request": args.session,
        "steps": {},
    }

    if usmi_path.is_file():
        try:
            usmi = load_us_money_index_sidecar(usmi_path)
            report["steps"]["us_money_index"] = {
                "status": "VALID_ADVISORY",
                "packet_id": usmi["packet_id"],
                "quality_status": usmi["quality_status"],
            }
        except Exception as error:
            report["steps"]["us_money_index"] = {"status": "INVALID_UNAVAILABLE", "error": str(error)}
    else:
        report["steps"]["us_money_index"] = {"status": "MISSING_OPTIONAL"}

    if not args.skip_gex and not args.dry_run:
        try:
            gex = build_local_gex(
                database_path=ROOT / "data" / "phantom" / "phantom_history.db",
                registry_path=ROOT / "data" / "canonical" / "control_plane.sqlite",
                canonical_root=ROOT / "data" / "canonical" / "gamma_exposure",
                output_dir=market_data_directory(ROOT),
                session=session,
            )
            report["steps"]["local_gex"] = gex
        except Exception as error:
            report["steps"]["local_gex"] = {"status": "FAILED", "error": str(error)}
            print(json.dumps(report, indent=2), file=sys.stderr)
            return 2
    else:
        report["steps"]["local_gex"] = {"status": "SKIPPED"}

    if not args.skip_macro_build:
        command = [sys.executable, str(ROOT / "build_macro_json.py"), "--force"]
        if args.dry_run:
            command.append("--dry-run")
        completed = subprocess.run(command, cwd=ROOT, text=True)
        report["steps"]["macro_build"] = {
            "status": "COMPLETE" if completed.returncode == 0 else "FAILED",
            "returncode": completed.returncode,
        }
        if completed.returncode != 0:
            print(json.dumps(report, indent=2), file=sys.stderr)
            return completed.returncode
    else:
        report["steps"]["macro_build"] = {"status": "SKIPPED"}

    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
