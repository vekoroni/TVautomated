#!/usr/bin/env python3
"""
Lightweight AVSHUNTER UAT pipeline monitor.

This script watches run-folder artefacts and the orchestrator log without
touching the running pipeline. It is intentionally dependency-free so it can
run in a separate PowerShell window during long UAT runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "output" / "runs"
QA_DIR = ROOT / "data" / "output" / "qa"
ORCHESTRATOR_LOG = ROOT / "logs" / "orchestrator.log"
ACTUARIAL_LOG = Path(r"C:\Users\ACKVerissimo\vanguard\logs\actuarial_cache_builder.log")


@dataclass
class PhaseStatus:
    name: str
    status: str
    file_count: int
    newest_write_utc: str | None
    newest_age_minutes: float | None
    examples: list[str]
    notes: list[str]


PHASES: dict[str, list[str]] = {
    "discovery": ["discovery/discovery_candidates_ultimate_*.csv"],
    "packages": ["packages/*.package.json"],
    "vanguard": [
        "vanguard/vanguard_signals.csv",
        "vanguard/vanguard_run_summary.json",
        "options/vanguard_signals_enriched_*.csv",
    ],
    "options": ["options/options_intelligence_*.csv"],
    "eil": ["superbrain/eil_enriched_*.csv"],
    "execution": ["execution/execution_v3_5_*.csv", "execution/execution_gated_*.csv"],
    "opportunity_book": ["intelligence_lab/final_opportunity_book_*.csv", "intelligence_lab/final_opportunity_book_*.json"],
    "morning_validation": ["morning_validation/morning_validated_trades_*.csv", "morning_validation/morning_validation_packet_*.json"],
    "final_manifest": ["final_run_manifest.json"],
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def latest_run_id() -> str | None:
    if not RUNS_DIR.exists():
        return None
    dirs = [
        path for path in RUNS_DIR.iterdir()
        if path.is_dir() and path.name.lower() != "latest" and path.name[:8].isdigit()
    ]
    if not dirs:
        return None
    dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return dirs[0].name


def iter_files(run_dir: Path, patterns: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path for path in run_dir.glob(pattern) if path.is_file())
    return sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)


def phase_status(run_dir: Path, name: str, patterns: list[str], stall_minutes: float) -> PhaseStatus:
    files = iter_files(run_dir, patterns)
    notes: list[str] = []
    newest: datetime | None = None
    age_minutes: float | None = None

    if files:
        newest = datetime.fromtimestamp(files[0].stat().st_mtime, tz=timezone.utc)
        age_minutes = max(0.0, (utc_now() - newest).total_seconds() / 60.0)

    if not files:
        status = "MISSING"
    elif age_minutes is not None and age_minutes > stall_minutes and name in {"packages", "vanguard"}:
        status = "STALE_PROGRESS"
        notes.append(f"Newest artefact is {age_minutes:.1f} minutes old.")
    else:
        status = "PRESENT"

    if name == "packages" and files:
        notes.append(f"Package files visible: {len(files)}")

    examples = [str(path.relative_to(run_dir)) for path in files[:5]]
    return PhaseStatus(
        name=name,
        status=status,
        file_count=len(files),
        newest_write_utc=iso_utc(newest),
        newest_age_minutes=round(age_minutes, 2) if age_minutes is not None else None,
        examples=examples,
        notes=notes,
    )


def _line_time_utc(line: str) -> datetime | None:
    """Parse the orchestrator's local timestamp prefix into UTC when present."""
    if len(line) < 19:
        return None
    try:
        naive = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    local_tz = datetime.now().astimezone().tzinfo
    return naive.replace(tzinfo=local_tz).astimezone(timezone.utc)


def _run_start_utc(run_dir: Path) -> datetime | None:
    meta = run_dir / "run_meta.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            raw = data.get("pinned_at_utc")
            if raw:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            pass
    if run_dir.exists():
        return datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc)
    return None


def tail_log(run_id: str, since_utc: datetime | None = None, max_lines: int = 80) -> dict[str, list[str]]:
    if not ORCHESTRATOR_LOG.exists():
        return {"phase_lines": [], "warnings": [], "errors": []}
    try:
        lines = ORCHESTRATOR_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {"phase_lines": [], "warnings": ["Could not read orchestrator.log"], "errors": []}

    relevant = []
    for line in lines[-3000:]:
        line_time = _line_time_utc(line)
        if since_utc and line_time and line_time < since_utc:
            continue
        has_progress = re.search(r"\[\d+\s*/\s*\d+\]", line) is not None
        if run_id in line or has_progress or "PHASE" in line or "▶" in line or "WARNING" in line or "ERROR" in line or "Traceback" in line:
            relevant.append(line)
    phase_lines = [
        line for line in relevant
        if "PHASE" in line or "▶" in line or re.search(r"\[\d+\s*/\s*\d+\]", line)
    ][-max_lines:]
    warnings = [line for line in relevant if "WARNING" in line][-max_lines:]
    candidate_errors = [
        line for line in relevant
        if "→ ERROR:" in line or "-> ERROR:" in line
    ][-max_lines:]
    errors = [
        line for line in relevant
        if ("ERROR" in line or "Traceback" in line)
        and "→ ERROR:" not in line
        and "-> ERROR:" not in line
    ][-max_lines:]
    return {
        "phase_lines": phase_lines,
        "warnings": warnings,
        "errors": errors,
        "candidate_errors": candidate_errors,
    }


def _read_tail_lines(path: Path, max_bytes: int = 5_000_000) -> list[str]:
    """Read the tail of a large log without loading the whole file."""
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()
            raw = fh.read()
        return raw.decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []


def actuarial_neutral_prior_snapshot(since_utc: datetime | None = None) -> dict:
    pattern = "No actuarial match"
    states: dict[str, int] = {}
    count = 0
    latest_time: datetime | None = None
    for line in _read_tail_lines(ACTUARIAL_LOG):
        if pattern not in line:
            continue
        line_time = _line_time_utc(line)
        if since_utc and line_time and line_time < since_utc:
            continue
        count += 1
        if line_time and (latest_time is None or line_time > latest_time):
            latest_time = line_time
        state = line.split("for:", 1)[-1].strip() if "for:" in line else "UNKNOWN"
        states[state] = states.get(state, 0) + 1

    top_states = [
        {"state": state, "count": hits}
        for state, hits in sorted(states.items(), key=lambda item: item[1], reverse=True)[:8]
    ]
    return {
        "count": count,
        "latest_utc": iso_utc(latest_time),
        "top_states": top_states,
        "log_path": str(ACTUARIAL_LOG),
    }


def parse_vanguard_progress(log: dict) -> dict | None:
    progress_re = re.compile(r"\[(\d+)\s*/\s*(\d+)\]\s+(PASS|REJECT|WARN|ERROR)\s+([A-Z0-9.\-]+)")
    latest: dict | None = None
    for line in log.get("phase_lines", []) + log.get("warnings", []) + log.get("errors", []):
        match = progress_re.search(line)
        if not match:
            continue
        done = int(match.group(1))
        total = int(match.group(2))
        latest = {
            "done": done,
            "total": total,
            "pct": round((done / total) * 100.0, 2) if total else None,
            "status": match.group(3),
            "ticker": match.group(4),
            "line_time_utc": iso_utc(_line_time_utc(line)),
            "line": line,
        }
    return latest


def parse_options_progress(log: dict) -> dict | None:
    progress_re = re.compile(r"\[(\d+)\s*/\s*(\d+)\]\s+([A-Z0-9.\-]+)\s+T\d+")
    latest: dict | None = None
    for line in log.get("phase_lines", []) + log.get("warnings", []) + log.get("errors", []):
        match = progress_re.search(line)
        if not match:
            continue
        done = int(match.group(1))
        total = int(match.group(2))
        latest = {
            "done": done,
            "total": total,
            "pct": round((done / total) * 100.0, 2) if total else None,
            "ticker": match.group(3),
            "line_time_utc": iso_utc(_line_time_utc(line)),
            "line": line,
        }
    return latest


def process_snapshot() -> list[dict[str, str]]:
    # Keep this Windows-friendly and dependency-free. We do not need command
    # lines for a health pulse; tasklist is enough to show whether Python is alive.
    try:
        import subprocess

        proc = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python*.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - defensive monitor only
        return [{"error": str(exc)}]

    rows: list[dict[str, str]] = []
    for raw in proc.stdout.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("INFO:"):
            continue
        parts = [part.strip().strip('"') for part in raw.split('","')]
        if len(parts) >= 5:
            rows.append({"image": parts[0], "pid": parts[1], "session": parts[2], "mem": parts[4]})
    return rows


def build_snapshot(run_id: str, stall_minutes: float) -> dict:
    run_dir = RUNS_DIR / run_id
    run_start_utc = _run_start_utc(run_dir)
    phases = [phase_status(run_dir, name, patterns, stall_minutes) for name, patterns in PHASES.items()]
    warnings: list[str] = []
    errors: list[str] = []

    if not run_dir.exists():
        errors.append(f"Run directory not found: {run_dir}")

    stalled = [phase.name for phase in phases if phase.status == "STALE_PROGRESS"]
    if stalled:
        warnings.append(f"Potential stale progress: {', '.join(stalled)}")

    missing_core = [
        phase.name
        for phase in phases
        if phase.status == "MISSING" and phase.name in {"discovery", "packages"}
    ]
    if missing_core:
        errors.append(f"Core artefacts missing: {', '.join(missing_core)}")

    log = tail_log(run_id, since_utc=run_start_utc)
    vanguard_progress = parse_vanguard_progress(log)
    options_progress = parse_options_progress(log)
    neutral_prior = actuarial_neutral_prior_snapshot(since_utc=run_start_utc)
    if neutral_prior["count"] > 0:
        warnings.append(f"Actuarial neutral-prior fallbacks detected: {neutral_prior['count']}")
    if vanguard_progress:
        progress_time = None
        progress_age = None
        if vanguard_progress.get("line_time_utc"):
            progress_time = datetime.fromisoformat(vanguard_progress["line_time_utc"].replace("Z", "+00:00"))
            progress_age = max(0.0, (utc_now() - progress_time).total_seconds() / 60.0)
            vanguard_progress["age_minutes"] = round(progress_age, 2)
        for phase in phases:
            if phase.name == "vanguard" and phase.status == "MISSING":
                phase.status = "STALE_PROGRESS" if progress_age and progress_age > stall_minutes else "RUNNING"
                phase.notes.append(
                    f"Vanguard progress {vanguard_progress['done']}/{vanguard_progress['total']} "
                    f"({vanguard_progress['pct']}%) last={vanguard_progress['ticker']}"
                )
                if progress_age and progress_age > stall_minutes:
                    phase.notes.append(f"Latest Vanguard progress line is {progress_age:.1f} minutes old.")
            if phase.name == "packages" and phase.status == "STALE_PROGRESS":
                phase.status = "PRESENT"
                phase.notes.append("Package writes are quiet because Vanguard is now consuming them.")
        warnings = [
            warning for warning in warnings
            if "Potential stale progress: packages" not in warning
        ]
        if progress_age and progress_age > stall_minutes:
            warnings.append(f"Potential stale progress: vanguard ({progress_age:.1f} minutes since last ticker)")
    if options_progress:
        progress_age = None
        if options_progress.get("line_time_utc"):
            progress_time = datetime.fromisoformat(options_progress["line_time_utc"].replace("Z", "+00:00"))
            progress_age = max(0.0, (utc_now() - progress_time).total_seconds() / 60.0)
            options_progress["age_minutes"] = round(progress_age, 2)
        for phase in phases:
            if phase.name == "options" and phase.status == "MISSING":
                phase.status = "STALE_PROGRESS" if progress_age and progress_age > stall_minutes else "RUNNING"
                phase.notes.append(
                    f"Options progress {options_progress['done']}/{options_progress['total']} "
                    f"({options_progress['pct']}%) last={options_progress['ticker']}"
                )
                if progress_age and progress_age > stall_minutes:
                    phase.notes.append(f"Latest Options progress line is {progress_age:.1f} minutes old.")
            if phase.name == "packages" and phase.status == "STALE_PROGRESS":
                phase.status = "PRESENT"
                phase.notes.append("Package writes are quiet because downstream stages are consuming them.")
        warnings = [
            warning for warning in warnings
            if "Potential stale progress: packages" not in warning
        ]
        options_files_present = any(
            phase.name == "options" and phase.file_count > 0
            for phase in phases
        )
        options_complete = (
            options_progress.get("total")
            and options_progress.get("done") == options_progress.get("total")
        )
        if progress_age and progress_age > stall_minutes and not (options_files_present and options_complete):
            warnings.append(f"Potential stale progress: options ({progress_age:.1f} minutes since last ticker)")
    if any(phase.name == "options" and phase.file_count > 0 for phase in phases):
        for phase in phases:
            if phase.name == "vanguard" and phase.status == "STALE_PROGRESS":
                phase.status = "PRESENT"
                phase.notes.append("Vanguard is complete; downstream options output exists.")
        warnings = [
            warning for warning in warnings
            if "Potential stale progress: vanguard" not in warning
        ]
    if log.get("candidate_errors"):
        warnings.append(f"Candidate-level errors detected: {len(log['candidate_errors'])} recent line(s)")
    if log["errors"]:
        errors.append("Recent ERROR/Traceback lines found in orchestrator.log")

    newest_times = [
        datetime.fromisoformat(phase.newest_write_utc.replace("Z", "+00:00"))
        for phase in phases
        if phase.newest_write_utc
    ]
    newest_any = max(newest_times) if newest_times else None
    newest_age_minutes = None
    if newest_any:
        newest_age_minutes = round((utc_now() - newest_any).total_seconds() / 60.0, 2)

    return {
        "timestamp_utc": iso_utc(utc_now()),
        "run_id": run_id,
        "run_dir": str(run_dir),
        "latest_any_write_utc": iso_utc(newest_any),
        "latest_any_write_age_minutes": newest_age_minutes,
        "overall_status": "ERROR" if errors else ("WARN" if warnings else "OK"),
        "warnings": warnings,
        "errors": errors,
        "phases": [asdict(phase) for phase in phases],
        "processes": process_snapshot(),
        "vanguard_progress": vanguard_progress,
        "options_progress": options_progress,
        "actuarial_neutral_prior": neutral_prior,
        "log_tail": log,
    }


def print_snapshot(snapshot: dict) -> None:
    print("=" * 90)
    print(
        f"{snapshot['timestamp_utc']} | run={snapshot['run_id']} | "
        f"status={snapshot['overall_status']} | latest_write_age={snapshot['latest_any_write_age_minutes']}m"
    )
    for phase in snapshot["phases"]:
        print(
            f"  {phase['name']:<18} {phase['status']:<14} "
            f"files={phase['file_count']:<5} newest_age={phase['newest_age_minutes']}"
        )
        for note in phase["notes"][:2]:
            print(f"    - {note}")
    if snapshot.get("vanguard_progress"):
        progress = snapshot["vanguard_progress"]
        print(
            f"  Vanguard progress: {progress['done']}/{progress['total']} "
            f"({progress['pct']}%) last={progress['ticker']} age={progress.get('age_minutes')}m"
        )
    if snapshot.get("options_progress"):
        progress = snapshot["options_progress"]
        print(
            f"  Options progress: {progress['done']}/{progress['total']} "
            f"({progress['pct']}%) last={progress['ticker']} age={progress.get('age_minutes')}m"
        )
    neutral = snapshot.get("actuarial_neutral_prior") or {}
    if neutral.get("count"):
        print(f"  Actuarial neutral prior: {neutral['count']} fallback(s)")
        for item in neutral.get("top_states", [])[:3]:
            print(f"    - {item['count']}x {item['state']}")
    if snapshot["warnings"]:
        print("  WARN:", "; ".join(snapshot["warnings"]))
    if snapshot["errors"]:
        print("  ERROR:", "; ".join(snapshot["errors"]))
    if snapshot["log_tail"]["errors"]:
        print("  Recent log errors:")
        for line in snapshot["log_tail"]["errors"][-5:]:
            print(f"    {line}")
    if snapshot["log_tail"].get("candidate_errors"):
        print("  Recent candidate errors:")
        for line in snapshot["log_tail"]["candidate_errors"][-5:]:
            print(f"    {line}")


def write_snapshot(snapshot: dict) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    path = QA_DIR / f"uat_monitor_{snapshot['run_id']}.json"
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Monitor AVSHUNTER UAT run artefacts without touching the pipeline.")
    parser.add_argument("--run-id", default=None, help="Run ID to monitor. Defaults to newest run folder.")
    parser.add_argument("--interval", type=int, default=120, help="Seconds between samples.")
    parser.add_argument("--stall-minutes", type=float, default=15.0, help="Warn when active artefacts stop changing.")
    parser.add_argument("--once", action="store_true", help="Take one sample and exit.")
    args = parser.parse_args()

    run_id = args.run_id or latest_run_id()
    if not run_id:
        print("No run folders found.")
        return 2

    while True:
        snapshot = build_snapshot(run_id, args.stall_minutes)
        print_snapshot(snapshot)
        report_path = write_snapshot(snapshot)
        print(f"  report: {report_path}")
        if args.once:
            return 1 if snapshot["errors"] else 0
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
