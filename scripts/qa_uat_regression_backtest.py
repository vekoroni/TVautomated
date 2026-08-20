#!/usr/bin/env python3
"""Regression backtest for the latest AVSHUNTER UAT run artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from handoff_contract_audit import audit_run  # noqa: E402
from uat_audit_report import write_uat_audit_report  # noqa: E402


RUNS_DIR = ROOT / "data" / "output" / "runs"


def _latest_run_id() -> str:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        payload = json.loads(latest.read_text(encoding="utf-8-sig"))
        run_id = str(payload.get("run_id") or payload.get("latest_run_id") or "").strip()
        if run_id:
            return run_id
    runs = sorted([p for p in RUNS_DIR.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise FileNotFoundError(f"No run folders found under {RUNS_DIR}")
    return runs[0].name


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def run_backtest(run_id: str, *, min_eod_candidates: int = 30) -> dict:
    run_dir = RUNS_DIR / run_id
    diagnostics = run_dir / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)

    handoff = audit_run(run_id, runs_dir=RUNS_DIR)
    report_paths = write_uat_audit_report(run_id, runs_dir=RUNS_DIR)

    eod_path = run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"
    dropoff_json_path = diagnostics / f"dropoff_audit_{run_id}.json"
    eod = _read_csv(eod_path)
    dropoff = json.loads(dropoff_json_path.read_text(encoding="utf-8-sig")) if dropoff_json_path.exists() else {}

    status_counts = (
        eod["eod_candidate_status"].fillna("").astype(str).value_counts().to_dict()
        if "eod_candidate_status" in eod.columns else {}
    )
    execute_count = sum(
        int(v) for k, v in status_counts.items()
        if "EXECUTE" in str(k).upper()
    )
    contradiction_counts = dropoff.get("vanguard_contract_contradiction_counts", {}) or {}
    active_contradictions = {
        str(k): int(v) for k, v in contradiction_counts.items()
        if str(k).strip()
    }
    outstanding = handoff.get("outstanding_fixes", []) or []
    vanguard_legacy_warnings = [
        item for item in outstanding
        if item.get("stage") == "vanguard" and item.get("field_contract") == "legacy_no_edge_note"
    ]
    morning_missing_warnings = [
        item for item in outstanding
        if item.get("stage") == "morning_validation" and item.get("status") == "MISSING_ARTIFACT"
    ]

    checks = {
        "handoff_has_no_failures": int(handoff.get("fail_count", 0) or 0) == 0,
        "vanguard_legacy_note_contract_resolved": not vanguard_legacy_warnings,
        "eod_missing_morning_validation_not_warned": not morning_missing_warnings,
        "eod_candidate_floor_met": len(eod) >= min_eod_candidates,
        "execute_like_candidates_present": execute_count > 0,
        "vanguard_contract_contradictions_clear": not active_contradictions,
        "uat_report_written": bool(report_paths.get("output_markdown") and Path(report_paths["output_markdown"]).exists()),
    }

    result = {
        "run_id": run_id,
        "passed": all(checks.values()),
        "checks": checks,
        "handoff_status": handoff.get("overall_status"),
        "handoff_fail_count": handoff.get("fail_count"),
        "handoff_warn_count": handoff.get("warn_count"),
        "eod_candidate_count": int(len(eod)),
        "execute_like_candidate_count": int(execute_count),
        "candidate_status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "active_vanguard_contract_contradictions": active_contradictions,
        "uat_report": report_paths,
    }
    out = diagnostics / f"uat_regression_backtest_{run_id}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    result["output_json"] = str(out)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest UAT audit fixes against a completed run.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--min-eod-candidates", type=int, default=30)
    args = parser.parse_args()

    result = run_backtest(args.run_id or _latest_run_id(), min_eod_candidates=args.min_eod_candidates)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
