#!/usr/bin/env python3
"""Capture an AVSHUNTER run end to end without changing trading outputs.

Use this before an evening/orchestrator rerun when we need one clean evidence
pack showing what appeared, when it appeared, and where the baton was dropped.
The script is intentionally read-mostly. It reuses the existing UAT audit
watcher for deep checks, then adds:

* wait-for-next-run protection so we do not accidentally audit an old run
* artifact first-seen/last-seen timeline
* final QA packet in data/output/qa
* final run-local diagnostics packet when a run folder exists
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
RUNS_DIR = ROOT / "data" / "output" / "runs"
QA_DIR = ROOT / "data" / "output" / "qa"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_live_uat_audit_watch import (  # noqa: E402
    RUN_ARTIFACTS,
    _artifact_map,
    _business_counts,
    _input_contract_status,
    _latest_run_id,
    _run_deep_audits,
    _safe_read_json,
    build_monitor_snapshot,
    sample_once,
)


CAPTURE_VERSION = "e2e_capture_v1"

EXPECTED_AT_END = [
    "phase0_scanner_context",
    "discovery",
    "packages_index",
    "packages",
    "vanguard",
    "vanguard_enriched",
    "options",
    "eil",
    "garch",
    "execution",
    "eod_candidates",
    "dropoff_audit",
    "handoff_contract_audit",
    "uat_audit_report",
    "pipeline_integrity",
]

ROW_CRITICAL_ARTIFACTS = {
    "discovery",
    "vanguard",
    "vanguard_enriched",
    "options",
    "eil",
    "garch",
    "execution",
    "eod_candidates",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    os.replace(tmp, path)


def _sample_fixed_run(run_id: str, stall_minutes: float) -> dict[str, Any]:
    """Build a watcher-compatible payload for a specific run id."""
    run_dir = RUNS_DIR / run_id
    input_status = _input_contract_status()
    artifact_map = _artifact_map(run_dir)
    monitor = build_monitor_snapshot(run_id, stall_minutes)
    audits = _run_deep_audits(run_id, artifact_map)
    business = _business_counts(run_id)

    warnings: list[str] = []
    macro_quality = str(input_status.get("macro_latest", {}).get("macro_data_quality") or "").upper()
    if macro_quality and macro_quality not in {"FULL", "GOOD", "CONFIRMED"}:
        warnings.append(f"Macro quality is {macro_quality}; watch downstream over-penalisation.")

    handoff = audits.get("handoff_contract_audit", {})
    if handoff.get("overall_status") == "FAIL":
        warnings.append(f"Handoff contract audit FAIL: fail_count={handoff.get('fail_count')}")

    return {
        "generated_utc": _iso(),
        "watcher_version": CAPTURE_VERSION,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "overall_status": "WARN" if warnings else "OK",
        "warnings": warnings,
        "input_contract_status": input_status,
        "artifact_map": artifact_map,
        "monitor_status": {
            "overall_status": monitor.get("overall_status"),
            "warnings": monitor.get("warnings", []),
            "errors": monitor.get("errors", []),
            "vanguard_progress": monitor.get("vanguard_progress"),
            "options_progress": monitor.get("options_progress"),
            "actuarial_neutral_prior": monitor.get("actuarial_neutral_prior"),
        },
        "deep_audits": audits,
        "business_counts": business,
    }


def _update_timeline(
    timeline: dict[str, dict[str, Any]],
    artifact_map: dict[str, Any],
    sample_utc: str,
) -> None:
    for stage, block in artifact_map.items():
        if not block.get("present"):
            continue
        entry = timeline.setdefault(
            stage,
            {
                "stage": stage,
                "first_seen_utc": sample_utc,
                "last_seen_utc": sample_utc,
                "latest_write_utc": "",
                "latest_path": "",
                "latest_rows": 0,
                "file_count": 0,
                "ever_present": True,
            },
        )
        entry["last_seen_utc"] = sample_utc
        entry["latest_write_utc"] = block.get("latest_write_utc", "")
        entry["latest_path"] = block.get("latest", "")
        entry["latest_rows"] = int(block.get("latest_rows") or 0)
        entry["file_count"] = int(block.get("count") or 0)
        entry["ever_present"] = True


def _is_evening_complete(payload: dict[str, Any]) -> bool:
    artifacts = payload.get("artifact_map") or {}
    if artifacts.get("final_manifest", {}).get("present"):
        return True
    if (
        artifacts.get("pipeline_integrity", {}).get("present")
        and artifacts.get("eod_candidates", {}).get("present")
        and artifacts.get("execution", {}).get("present")
    ):
        return True
    return False


def _gap_flags(payload: dict[str, Any], timeline: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    artifacts = payload.get("artifact_map") or {}

    for stage in EXPECTED_AT_END:
        block = artifacts.get(stage, {})
        if not block.get("present"):
            flags.append(
                {
                    "severity": "WARN",
                    "stage": stage,
                    "flag": "MISSING_EXPECTED_ARTIFACT",
                    "detail": "Expected artifact was not present at final capture.",
                }
            )
            continue
        if stage in ROW_CRITICAL_ARTIFACTS and str(block.get("latest", "")).lower().endswith(".csv"):
            if int(block.get("latest_rows") or 0) <= 0:
                flags.append(
                    {
                        "severity": "FAIL",
                        "stage": stage,
                        "flag": "ZERO_ROWS",
                        "detail": "Artifact exists but has no data rows.",
                    }
                )

    input_status = payload.get("input_contract_status") or {}
    macro = input_status.get("macro_latest") or {}
    macro_quality = str(macro.get("macro_data_quality") or "").upper()
    if macro_quality and macro_quality not in {"FULL", "GOOD", "CONFIRMED"}:
        flags.append(
            {
                "severity": "WARN",
                "stage": "macro_input",
                "flag": f"MACRO_QUALITY_{macro_quality}",
                "detail": "Macro packet is usable but should be checked for downstream over-penalisation.",
            }
        )

    if not input_status.get("catalyst_calendar_latest_csv", {}).get("present") and not input_status.get(
        "catalyst_calendar_latest_json", {}
    ).get("present"):
        flags.append(
            {
                "severity": "WARN",
                "stage": "phase0_input",
                "flag": "NO_CANONICAL_CATALYST_CALENDAR",
                "detail": "Canonical catalyst calendar was not visible at capture time.",
            }
        )

    handoff = (payload.get("deep_audits") or {}).get("handoff_contract_audit") or {}
    if handoff.get("overall_status") == "FAIL":
        flags.append(
            {
                "severity": "FAIL",
                "stage": "handoff_contract_audit",
                "flag": "HANDOFF_AUDIT_FAIL",
                "detail": f"fail_count={handoff.get('fail_count')} warn_count={handoff.get('warn_count')}",
            }
        )

    monitor = payload.get("monitor_status") or {}
    for error in monitor.get("errors") or []:
        flags.append({"severity": "FAIL", "stage": "monitor", "flag": "MONITOR_ERROR", "detail": str(error)})
    for warning in monitor.get("warnings") or []:
        flags.append({"severity": "WARN", "stage": "monitor", "flag": "MONITOR_WARNING", "detail": str(warning)})

    for stage in RUN_ARTIFACTS:
        if stage not in timeline and stage in EXPECTED_AT_END:
            continue

    return flags


def _final_status(flags: list[dict[str, Any]], completed: bool) -> str:
    if any(flag.get("severity") == "FAIL" for flag in flags):
        return "COMPLETE_WITH_FAILURES" if completed else "INCOMPLETE_WITH_FAILURES"
    if any(flag.get("severity") == "WARN" for flag in flags):
        return "COMPLETE_WITH_WARNINGS" if completed else "INCOMPLETE_WITH_WARNINGS"
    return "COMPLETE_OK" if completed else "INCOMPLETE_OK"


def _write_capture_outputs(
    *,
    run_id: str,
    baseline_run_id: str,
    started_utc: str,
    completed: bool,
    samples: list[dict[str, Any]],
    timeline: dict[str, dict[str, Any]],
    final_payload: dict[str, Any],
    stop_reason: str,
) -> dict[str, str]:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    timeline_rows = [timeline[key] for key in sorted(timeline)]
    flags = _gap_flags(final_payload, timeline)
    status = _final_status(flags, completed)

    dropoff_json = RUNS_DIR / run_id / "diagnostics" / f"dropoff_audit_{run_id}.json"
    dropoff_summary = _safe_read_json(dropoff_json) if dropoff_json.exists() else {}

    packet = {
        "capture_version": CAPTURE_VERSION,
        "capture_status": status,
        "stop_reason": stop_reason,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "started_utc": started_utc,
        "finished_utc": _iso(),
        "completed": completed,
        "sample_count": len(samples),
        "input_contract_status": final_payload.get("input_contract_status", {}),
        "artifact_timeline": timeline_rows,
        "latest_artifact_map": final_payload.get("artifact_map", {}),
        "monitor_status": final_payload.get("monitor_status", {}),
        "deep_audits": final_payload.get("deep_audits", {}),
        "business_counts": final_payload.get("business_counts", {}),
        "dropoff_audit_summary": {
            "rows": dropoff_summary.get("rows"),
            "dropoff_stage_counts": dropoff_summary.get("dropoff_stage_counts"),
            "root_cause_family_counts": dropoff_summary.get("root_cause_family_counts"),
            "top_dropoff_reasons": dropoff_summary.get("top_dropoff_reasons"),
            "audit_severity_counts": dropoff_summary.get("audit_severity_counts"),
        },
        "gap_flags": flags,
    }

    latest_json = QA_DIR / "e2e_run_capture_latest.json"
    run_json = QA_DIR / f"e2e_run_capture_{run_id or 'no_run'}.json"
    run_csv = QA_DIR / f"e2e_artifact_timeline_{run_id or 'no_run'}.csv"
    _write_json_atomic(latest_json, packet)
    _write_json_atomic(run_json, packet)
    _write_csv(
        run_csv,
        timeline_rows,
        [
            "stage",
            "first_seen_utc",
            "last_seen_utc",
            "latest_write_utc",
            "latest_path",
            "latest_rows",
            "file_count",
            "ever_present",
        ],
    )

    md = _markdown_report(packet)
    qa_md = QA_DIR / f"e2e_run_capture_{run_id or 'no_run'}.md"
    _write_text_atomic(qa_md, md)

    run_dir = RUNS_DIR / run_id if run_id else None
    diagnostics_outputs: dict[str, str] = {}
    if run_dir and run_dir.exists():
        diag = run_dir / "diagnostics"
        try:
            diag_json = diag / f"e2e_run_capture_{run_id}.json"
            diag_csv = diag / f"e2e_artifact_timeline_{run_id}.csv"
            diag_md = diag / f"e2e_run_capture_{run_id}.md"
            _write_json_atomic(diag_json, packet)
            _write_csv(
                diag_csv,
                timeline_rows,
                [
                    "stage",
                    "first_seen_utc",
                    "last_seen_utc",
                    "latest_write_utc",
                    "latest_path",
                    "latest_rows",
                    "file_count",
                    "ever_present",
                ],
            )
            _write_text_atomic(diag_md, md)
            diagnostics_outputs = {
                "run_diagnostics_json": str(diag_json),
                "run_diagnostics_csv": str(diag_csv),
                "run_diagnostics_md": str(diag_md),
            }
        except PermissionError:
            packet["diagnostics_write_warning"] = "No permission to write run-local diagnostics from current shell."
            _write_json_atomic(latest_json, packet)
            _write_json_atomic(run_json, packet)

    outputs = {
        "qa_latest_json": str(latest_json),
        "qa_run_json": str(run_json),
        "qa_timeline_csv": str(run_csv),
        "qa_markdown": str(qa_md),
        **diagnostics_outputs,
    }
    packet["outputs"] = outputs
    _write_json_atomic(latest_json, packet)
    _write_json_atomic(run_json, packet)
    return outputs


def _markdown_report(packet: dict[str, Any]) -> str:
    flags = packet.get("gap_flags") or []
    business = packet.get("business_counts") or {}
    deep = packet.get("deep_audits") or {}
    handoff = deep.get("handoff_contract_audit") or {}
    dropoff = packet.get("dropoff_audit_summary") or {}

    lines = [
        f"# AVSHUNTER End-to-End Run Capture - {packet.get('run_id') or 'no run'}",
        "",
        f"- Status: {packet.get('capture_status')}",
        f"- Started UTC: {packet.get('started_utc')}",
        f"- Finished UTC: {packet.get('finished_utc')}",
        f"- Completed: {packet.get('completed')}",
        f"- Stop reason: {packet.get('stop_reason')}",
        f"- Samples: {packet.get('sample_count')}",
        "",
        "## Business Counts",
        "",
        f"- Catalyst Truth rows: {business.get('catalyst_truth_rows')}",
        f"- Execution rows: {business.get('execution_rows')}",
        f"- EOD candidate rows: {business.get('eod_candidate_rows')}",
        f"- Shadow book rows: {business.get('shadow_book_rows')}",
        "",
        "## Audit Status",
        "",
        f"- Handoff: {handoff.get('overall_status')} fail={handoff.get('fail_count')} warn={handoff.get('warn_count')}",
        f"- Drop-off rows: {dropoff.get('rows')}",
        "",
        "## Gap Flags",
        "",
    ]
    if flags:
        for flag in flags[:40]:
            lines.append(
                f"- {flag.get('severity')} | {flag.get('stage')} | {flag.get('flag')} | {flag.get('detail')}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Artifact Timeline", ""])
    for row in packet.get("artifact_timeline") or []:
        lines.append(
            f"- {row.get('stage')}: rows={row.get('latest_rows')} first={row.get('first_seen_utc')} latest={row.get('latest_write_utc')}"
        )
    lines.append("")
    return "\n".join(lines)


def _print_status(payload: dict[str, Any], timeline: dict[str, dict[str, Any]], waiting: bool = False) -> None:
    run_id = payload.get("run_id") or "-"
    status = payload.get("overall_status") or "-"
    artifacts = payload.get("artifact_map") or {}
    present = [name for name, block in artifacts.items() if block.get("present")]
    business = payload.get("business_counts") or {}
    prefix = "WAITING" if waiting else "CAPTURE"
    print(
        f"{_iso()} | {prefix} | run={run_id} | status={status} | "
        f"artifacts={len(present)} | timeline={len(timeline)} | "
        f"exec={business.get('execution_rows')} eod={business.get('eod_candidate_rows')}"
    )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Capture one AVSHUNTER run end to end.")
    parser.add_argument("--run-id", default="", help="Capture an existing run id instead of following latest.")
    parser.add_argument(
        "--wait-for-new-run",
        action="store_true",
        help="Record the current latest run as baseline, then wait until a new run folder appears.",
    )
    parser.add_argument("--interval", type=int, default=120, help="Seconds between samples.")
    parser.add_argument("--timeout-minutes", type=float, default=420.0, help="Maximum capture time.")
    parser.add_argument("--stall-minutes", type=float, default=15.0, help="Passed to existing monitor checks.")
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=180,
        help="Keep sampling this long after completion marker appears so final audits can land.",
    )
    parser.add_argument("--once", action="store_true", help="Take one sample and write a packet.")
    parser.add_argument("--quiet", action="store_true", help="Suppress compact progress lines.")
    args = parser.parse_args()

    started_utc = _iso()
    baseline_run_id = _latest_run_id() if args.wait_for_new_run and not args.run_id else ""
    active_run_id = args.run_id.strip()
    timeline: dict[str, dict[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    completed_at: float | None = None
    final_payload: dict[str, Any] = {}
    stop_reason = "once" if args.once else "timeout"
    end_at = time.time() + max(1.0, args.timeout_minutes) * 60.0

    print(
        json.dumps(
            {
                "capture_version": CAPTURE_VERSION,
                "started_utc": started_utc,
                "baseline_run_id": baseline_run_id,
                "requested_run_id": active_run_id,
                "wait_for_new_run": args.wait_for_new_run,
                "qa_latest_json": str(QA_DIR / "e2e_run_capture_latest.json"),
            },
            indent=2,
        )
    )

    while time.time() <= end_at:
        if not active_run_id:
            current = _latest_run_id()
            if args.wait_for_new_run and current and current == baseline_run_id:
                waiting_payload = sample_once(stall_minutes=args.stall_minutes)
                if not args.quiet:
                    _print_status(waiting_payload, timeline, waiting=True)
                if args.once:
                    final_payload = waiting_payload
                    stop_reason = "waiting_once"
                    break
                time.sleep(max(20, args.interval))
                continue
            active_run_id = current

        if active_run_id:
            if args.run_id:
                payload = _sample_fixed_run(active_run_id, args.stall_minutes)
            else:
                payload = sample_once(stall_minutes=args.stall_minutes)
                latest_seen = str(payload.get("run_id") or "")
                if latest_seen and latest_seen != active_run_id:
                    active_run_id = latest_seen

            sample_utc = str(payload.get("generated_utc") or _iso())
            _update_timeline(timeline, payload.get("artifact_map") or {}, sample_utc)
            samples.append(
                {
                    "generated_utc": sample_utc,
                    "run_id": payload.get("run_id"),
                    "overall_status": payload.get("overall_status"),
                    "business_counts": payload.get("business_counts"),
                    "monitor_status": payload.get("monitor_status"),
                }
            )
            final_payload = payload
            if not args.quiet:
                _print_status(payload, timeline)

            if _is_evening_complete(payload):
                if completed_at is None:
                    completed_at = time.time()
                    stop_reason = "completion_marker_seen"
                elif time.time() - completed_at >= max(0, args.settle_seconds):
                    stop_reason = "completed_and_settled"
                    break

            if args.once:
                stop_reason = "once"
                break
        else:
            final_payload = {
                "generated_utc": _iso(),
                "run_id": "",
                "overall_status": "WAITING_FOR_RUN",
                "input_contract_status": _input_contract_status(),
                "artifact_map": {},
                "business_counts": {},
                "deep_audits": {},
                "monitor_status": {},
            }
            if not args.quiet:
                _print_status(final_payload, timeline, waiting=True)
            if args.once:
                stop_reason = "no_run_once"
                break

        time.sleep(max(20, args.interval))

    run_id = str((final_payload or {}).get("run_id") or active_run_id or "no_run")
    completed = bool(final_payload and _is_evening_complete(final_payload))
    outputs = _write_capture_outputs(
        run_id=run_id,
        baseline_run_id=baseline_run_id,
        started_utc=started_utc,
        completed=completed,
        samples=samples,
        timeline=timeline,
        final_payload=final_payload,
        stop_reason=stop_reason,
    )
    print(json.dumps({"run_id": run_id, "completed": completed, "stop_reason": stop_reason, "outputs": outputs}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
