"""Smoke test for Morning Thesis Validator.

This is a local paper/test smoke. It does not place broker orders.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import resolve_lab_tradeability
try:
    from morning_thesis_validator import latest_run_id, run_morning_validation  # type: ignore[import-not-found]
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = True
except ModuleNotFoundError:
    latest_run_id = None
    run_morning_validation = None
    _LEGACY_MORNING_VALIDATOR_AVAILABLE = False


def main() -> int:
    if not _LEGACY_MORNING_VALIDATOR_AVAILABLE:
        print(
            "RETIRED: smoke_test_morning_validator.py targeted the archived validator. "
            "Production smoke coverage is tests/test_morning_gate_authority.py."
        )
        return 2
    runs_dir = ROOT / "data" / "output" / "runs"
    run_id = latest_run_id(runs_dir)
    if not run_id:
        print("FAIL: no latest run_id available")
        return 2

    output_path = runs_dir / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
    packet_path = runs_dir / run_id / "morning_validation" / f"morning_validation_packet_{run_id}.json"

    rows = run_morning_validation(
        run_id=run_id,
        output_path=output_path,
        runs_dir=runs_dir,
        max_signals=20,
        live_mode=False,
        paper_mode=True,
        pipeline_mode="EOD",
    )
    if not output_path.exists() or not packet_path.exists():
        print("FAIL: morning validation outputs were not created")
        return 1

    with output_path.open("r", encoding="utf-8-sig", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    missing = [
        r.get("ticker", "?")
        for r in csv_rows
        if not r.get("live_validation_state") or not r.get("execution_permission")
    ]
    if missing:
        print("FAIL: rows missing validation fields", missing[:20])
        return 1

    blocked_ok = True
    for row in csv_rows:
        if row.get("execution_permission") == "BLOCKED":
            verdict = resolve_lab_tradeability(
                {
                    "ticker": row.get("ticker"),
                    "mv__execution_permission": row.get("execution_permission"),
                    "mv__live_validation_state": row.get("live_validation_state"),
                    "strike": row.get("evening_strike"),
                    "expiry": row.get("evening_expiry"),
                    "premium_mid": row.get("evening_premium_mid"),
                },
                {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
            )
            if verdict["lab_tradeable"]:
                blocked_ok = False
                break
    if not blocked_ok:
        print("FAIL: BLOCKED morning candidate resolved as tradeable")
        return 1

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    summary = packet.get("summary", {})
    print("run_id:", run_id)
    print("validated_rows:", len(rows))
    print("summary:", json.dumps(summary, ensure_ascii=True, sort_keys=True))
    print("csv:", output_path)
    print("packet:", packet_path)
    print("PASS: Morning Validator smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
