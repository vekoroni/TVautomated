#!/usr/bin/env python3
"""Go-live UAT audit watcher for AVSHUNTER.

This wrapper is intentionally non-invasive: it never changes trading outputs.
It follows the newest run folder, samples pipeline progress, and materializes
the same diagnostic artifacts we review after UAT:

* dropoff_audit_<run_id>.csv/json
* handoff_contract_audit_<run_id>.csv/json
* uat_audit_report_<run_id>.md/json
* data/output/qa/go_live_uat_audit_watch_latest.json

The watcher can be started before the orchestrator. It will switch to the new
run folder as soon as the run appears.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "output" / "runs"
QA_DIR = ROOT / "data" / "output" / "qa"
INPUTS_DIR = ROOT / "dropbox" / "inputs"
MARKET_DATA_DIR = ROOT / "dropbox" / "market_data"
MACRO_DIR = ROOT / "dropbox" / "macro"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from dropoff_audit import build_dropoff_audit  # noqa: E402
from handoff_contract_audit import audit_run as audit_handoff_contract  # noqa: E402
from uat_audit_report import write_uat_audit_report  # noqa: E402
from monitor_uat_pipeline import build_snapshot as build_monitor_snapshot  # noqa: E402


RUN_ARTIFACTS: dict[str, list[str]] = {
    "phase0_scanner_context": ["scanner_context_*.json"],
    "phase0_augmented_universe": ["universe/scanner_augmented_universe_*.csv"],
    "discovery": ["discovery/discovery_candidates_*.csv"],
    "packages_index": ["packages/index.json"],
    "packages": ["packages/*.package.json"],
    "vanguard": ["vanguard/vanguard_signals.csv", "vanguard/vanguard_signals_*.csv"],
    "vanguard_rejects": ["vanguard/vanguard_rejects.csv", "vanguard/vanguard_rejects_*.csv"],
    "vanguard_enriched": ["options/vanguard_signals_enriched_*.csv"],
    "catalyst_truth": ["catalysts/catalyst_truth_*.csv"],
    "catalyst_summary": ["catalysts/catalyst_truth_summary_*.json"],
    "options": ["options/options_intelligence_*.csv"],
    "eil": ["superbrain/eil_enriched_*.csv"],
    "garch": ["qomega/garch_forecasts_*.csv"],
    "execution": ["execution/execution_v3_5_*.csv", "execution/execution_*.csv"],
    "eod_candidates": ["morning_validation/morning_candidates_*.csv"],
    "shadow_book": ["morning_validation/missed_opportunity_shadow_book_*.csv"],
    "morning_validation": ["morning_validation/morning_validated_trades_*.csv"],
    "dropoff_audit": ["diagnostics/dropoff_audit_*.json", "diagnostics/dropoff_audit_*.csv"],
    "handoff_contract_audit": ["diagnostics/handoff_contract_audit_*.json", "diagnostics/handoff_contract_audit_*.csv"],
    "uat_audit_report": ["diagnostics/uat_audit_report_*.json", "diagnostics/uat_audit_report_*.md"],
    "final_manifest": ["final_run_manifest.json"],
    "pipeline_integrity": ["pipeline_integrity_*.json"],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_read_error": str(exc)}


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame()


def _macro_packet_from_json(path: Path) -> dict[str, Any]:
    macro = _safe_read_json(path)
    if not macro:
        return {}
    if "macro_freshness_status" in macro or "macro_data_quality" in macro:
        return macro
    try:
        from scripts.macro_quant_packet import build_macro_quant_packet

        return build_macro_quant_packet(macro, source_path=str(path))
    except Exception:
        return macro


def _latest_run_id() -> str:
    candidates: list[Path] = []
    if RUNS_DIR.exists():
        candidates = [
            path for path in RUNS_DIR.iterdir()
            if path.is_dir() and path.name.lower() != "latest" and path.name[:8].isdigit()
        ]
    if candidates:
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return candidates[0].name

    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        payload = _safe_read_json(latest)
        run_id = str(payload.get("run_id") or payload.get("latest_run_id") or "").strip()
        if run_id:
            return run_id
    return ""


def _glob_latest(run_dir: Path, patterns: list[str]) -> Optional[Path]:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(path for path in run_dir.glob(pattern) if path.exists())
    if not matches:
        return None
    return sorted(matches, key=lambda path: path.stat().st_mtime)[-1]


def _row_count(path: Optional[Path]) -> int:
    if not path or not path.exists() or path.suffix.lower() != ".csv":
        return 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except Exception:
        return 0


def _artifact_map(run_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, patterns in RUN_ARTIFACTS.items():
        files: list[Path] = []
        for pattern in patterns:
            files.extend(path for path in run_dir.glob(pattern) if path.exists())
        files = sorted(set(files), key=lambda path: path.stat().st_mtime)
        latest = files[-1] if files else None
        out[name] = {
            "present": bool(files),
            "count": len(files),
            "latest": str(latest or ""),
            "latest_rows": _row_count(latest),
            "latest_write_utc": (
                datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
                if latest else ""
            ),
        }
    return out


def _input_contract_status() -> dict[str, Any]:
    catalyst_primary = INPUTS_DIR / "catalyst_calendar_latest.csv"
    catalyst_json = INPUTS_DIR / "catalyst_calendar_latest.json"
    catalyst_alternatives: list[Path] = []
    if INPUTS_DIR.exists():
        for pattern in [
            "avshunter_*catalyst*.csv",
            "avshunter_*event*.csv",
            "avshunter_ma_*.csv",
            "avshunter_fda_*.csv",
            "news_catalyst*.csv",
            "fda_catalyst*.csv",
        ]:
            catalyst_alternatives.extend(INPUTS_DIR.glob(pattern))
    catalyst_alternatives = sorted(set(catalyst_alternatives), key=lambda path: path.stat().st_mtime)
    recognized = {path.resolve() for path in catalyst_alternatives}
    unrecognized_catalyst_like: list[Path] = []
    if INPUTS_DIR.exists():
        unrecognized_catalyst_like = sorted(
            [
                path for path in INPUTS_DIR.glob("*catalyst*")
                if path.is_file() and path.resolve() not in recognized
            ],
            key=lambda path: path.stat().st_mtime,
        )

    market_files: list[Path] = []
    if MARKET_DATA_DIR.exists():
        market_files = sorted(
            [path for path in MARKET_DATA_DIR.glob("*") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    manual = INPUTS_DIR / "manual_ticker_upload_latest.csv"
    macro_latest = MACRO_DIR / "macro_intelligence_latest.json"
    macro_payload = _macro_packet_from_json(macro_latest)

    return {
        "catalyst_calendar_latest_csv": {
            "path": str(catalyst_primary),
            "present": catalyst_primary.exists(),
            "rows": _row_count(catalyst_primary),
        },
        "catalyst_calendar_latest_json": {
            "path": str(catalyst_json),
            "present": catalyst_json.exists(),
        },
        "catalyst_alternatives_detected": [
            {
                "name": path.name,
                "path": str(path),
                "rows": _row_count(path),
                "last_write_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            for path in catalyst_alternatives[-10:]
        ],
        "unrecognized_catalyst_like_files": [
            {
                "name": path.name,
                "path": str(path),
                "rows": _row_count(path),
                "last_write_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            for path in unrecognized_catalyst_like[-10:]
        ],
        "manual_ticker_upload_retired": {
            "path": str(manual),
            "present": manual.exists(),
            "status": "IGNORED_BY_ORCHESTRATOR",
        },
        "macro_latest": {
            "path": str(macro_latest),
            "present": macro_latest.exists(),
            "macro_freshness_status": macro_payload.get("macro_freshness_status", ""),
            "macro_data_quality": macro_payload.get("macro_data_quality", ""),
            "macro_active_conflict_flags": macro_payload.get("macro_active_conflict_flags", []),
            "macro_resolved_conflict_flags": macro_payload.get("macro_resolved_conflict_flags", []),
        },
        "market_data_latest_files": [
            {
                "name": path.name,
                "path": str(path),
                "last_write_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "size": path.stat().st_size,
            }
            for path in market_files[:20]
        ],
    }


def _counts_from_csv(path: Optional[Path], columns: list[str]) -> dict[str, dict[str, int]]:
    if not path or not path.exists():
        return {}
    df = _safe_read_csv(path)
    if df.empty:
        return {}
    out: dict[str, dict[str, int]] = {}
    for col in columns:
        if col in df.columns:
            out[col] = {str(k): int(v) for k, v in df[col].fillna("").astype(str).value_counts().head(25).items()}
    return out


def _run_deep_audits(run_id: str, artifact_map: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    run_dir = RUNS_DIR / run_id
    diagnostics = run_dir / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)

    try:
        dropoff_df = build_dropoff_audit(run_id, runs_dir=RUNS_DIR)
        dropoff_json = diagnostics / f"dropoff_audit_{run_id}.json"
        dropoff_payload = _safe_read_json(dropoff_json)
        results["dropoff_audit"] = {
            "status": "OK",
            "rows": int(len(dropoff_df)),
            "output_json": str(dropoff_json),
            "dropoff_stage_counts": dropoff_payload.get("dropoff_stage_counts", {}),
            "root_cause_family_counts": dropoff_payload.get("root_cause_family_counts", {}),
            "top_dropoff_reasons": dropoff_payload.get("top_dropoff_reasons", {}),
        }
    except Exception as exc:
        results["dropoff_audit"] = {"status": "ERROR", "error": str(exc)}

    # Handoff audit is most useful once a material downstream artifact exists.
    downstream_ready = any(
        artifact_map.get(name, {}).get("present")
        for name in ["vanguard", "options", "eil", "execution", "eod_candidates", "shadow_book"]
    )
    if downstream_ready:
        try:
            handoff = audit_handoff_contract(run_id, runs_dir=RUNS_DIR)
            results["handoff_contract_audit"] = {
                "status": "OK",
                "overall_status": handoff.get("overall_status"),
                "fail_count": handoff.get("fail_count"),
                "warn_count": handoff.get("warn_count"),
                "output_json": handoff.get("output_json"),
                "output_csv": handoff.get("output_csv"),
            }
        except Exception as exc:
            results["handoff_contract_audit"] = {"status": "ERROR", "error": str(exc)}
    else:
        results["handoff_contract_audit"] = {"status": "PENDING", "reason": "No downstream artifact yet."}

    if downstream_ready:
        try:
            report = write_uat_audit_report(run_id, runs_dir=RUNS_DIR)
            results["uat_audit_report"] = {"status": "OK", **report}
        except Exception as exc:
            results["uat_audit_report"] = {"status": "ERROR", "error": str(exc)}
    else:
        results["uat_audit_report"] = {"status": "PENDING", "reason": "No downstream artifact yet."}

    return results


def _business_counts(run_id: str) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    eod = _glob_latest(run_dir, ["morning_validation/morning_candidates_*.csv"])
    execution = _glob_latest(run_dir, ["execution/execution_v3_5_*.csv", "execution/execution_*.csv"])
    catalyst = _glob_latest(run_dir, ["catalysts/catalyst_truth_*.csv"])
    shadow = _glob_latest(run_dir, ["morning_validation/missed_opportunity_shadow_book_*.csv"])

    out: dict[str, Any] = {
        "eod_candidate_rows": _row_count(eod),
        "execution_rows": _row_count(execution),
        "catalyst_truth_rows": _row_count(catalyst),
        "shadow_book_rows": _row_count(shadow),
        "eod_counts": _counts_from_csv(eod, ["eod_candidate_status", "structural_tier", "selected_contract_side"]),
        "execution_counts": _counts_from_csv(execution, ["effective_execution_verdict", "capital_permission", "pse_execution_mode"]),
        "catalyst_counts": _counts_from_csv(catalyst, ["catalyst_detected", "catalyst_trade_class", "catalyst_data_quality", "catalyst_alignment_label"]),
        "shadow_counts": _counts_from_csv(shadow, ["shadow_opportunity_label", "root_cause_family", "dropoff_stage"]),
    }
    return out


def _write_latest(payload: dict[str, Any]) -> Path:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = QA_DIR / "go_live_uat_audit_watch_latest.json"
    run_path = QA_DIR / f"go_live_uat_audit_watch_{payload.get('run_id') or 'no_run'}.json"
    text = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    for path in [latest_path, run_path]:
        tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return latest_path


def sample_once(stall_minutes: float = 15.0) -> dict[str, Any]:
    run_id = _latest_run_id()
    input_status = _input_contract_status()
    if not run_id:
        payload = {
            "generated_utc": _iso(),
            "run_id": "",
            "overall_status": "WAITING_FOR_RUN",
            "input_contract_status": input_status,
            "message": "No run folders found yet. Start the orchestrator; watcher will pick up the new run.",
        }
        _write_latest(payload)
        return payload

    run_dir = RUNS_DIR / run_id
    artifact_map = _artifact_map(run_dir)
    monitor = build_monitor_snapshot(run_id, stall_minutes)
    audits = _run_deep_audits(run_id, artifact_map)
    business = _business_counts(run_id)

    warnings: list[str] = []
    if not input_status["catalyst_calendar_latest_csv"]["present"] and not input_status["catalyst_calendar_latest_json"]["present"]:
        if input_status["catalyst_alternatives_detected"]:
            warnings.append("Canonical catalyst_calendar_latest is absent; catalyst engine will only use matching alternative GPT files.")
        elif input_status["unrecognized_catalyst_like_files"]:
            warnings.append("Catalyst-like files exist but are not in a digestible Catalyst Truth filename.")
        else:
            warnings.append("No canonical catalyst calendar or matching catalyst GPT files detected in dropbox/inputs.")
    macro_quality = str(input_status["macro_latest"].get("macro_data_quality") or "").upper()
    if macro_quality and macro_quality not in {"FULL", "GOOD", "CONFIRMED"}:
        warnings.append(f"Macro quality is {macro_quality}; audit will watch downstream over-penalisation.")

    handoff = audits.get("handoff_contract_audit", {})
    if handoff.get("overall_status") == "FAIL":
        warnings.append(f"Handoff contract audit FAIL: fail_count={handoff.get('fail_count')}")
    dropoff = audits.get("dropoff_audit", {})
    p1_p2_counts = {}
    dropoff_json = run_dir / "diagnostics" / f"dropoff_audit_{run_id}.json"
    if dropoff_json.exists():
        payload = _safe_read_json(dropoff_json)
        p1_p2_counts = {
            k: int(v) for k, v in (payload.get("audit_severity_counts") or {}).items()
            if str(k).upper() in {"P0", "P1", "P2"}
        }

    payload = {
        "generated_utc": _iso(),
        "watcher_version": "go_live_uat_audit_watch_v1",
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
        "priority_audit_severity_counts": p1_p2_counts,
    }
    out = _write_latest(payload)
    payload["output_json"] = str(out)
    return payload


def print_compact(payload: dict[str, Any]) -> None:
    print("=" * 90)
    print(f"{payload.get('generated_utc')} | run={payload.get('run_id') or '-'} | status={payload.get('overall_status')}")
    for warning in payload.get("warnings", [])[:6]:
        print(f"  WARN: {warning}")
    artifacts = payload.get("artifact_map", {})
    present = [name for name, block in artifacts.items() if block.get("present")]
    print(f"  artifacts present: {', '.join(present[:18]) or 'none yet'}")
    audits = payload.get("deep_audits", {})
    drop = audits.get("dropoff_audit", {})
    handoff = audits.get("handoff_contract_audit", {})
    print(f"  dropoff: {drop.get('status')} rows={drop.get('rows')}")
    print(f"  handoff: {handoff.get('status')} overall={handoff.get('overall_status')} fail={handoff.get('fail_count')} warn={handoff.get('warn_count')}")
    business = payload.get("business_counts", {})
    print(f"  counts: catalyst={business.get('catalyst_truth_rows')} execution={business.get('execution_rows')} eod={business.get('eod_candidate_rows')} shadow={business.get('shadow_book_rows')}")
    print(f"  report: {payload.get('output_json') or QA_DIR / 'go_live_uat_audit_watch_latest.json'}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Follow the newest AVSHUNTER run and keep UAT audits current.")
    parser.add_argument("--interval", type=int, default=120, help="Seconds between samples.")
    parser.add_argument("--duration-minutes", type=float, default=360.0, help="How long to watch. Use 0 for one pass.")
    parser.add_argument("--stall-minutes", type=float, default=15.0)
    parser.add_argument("--once", action="store_true", help="Take one sample and exit.")
    args = parser.parse_args()

    end_at = time.time() + max(0.0, args.duration_minutes) * 60.0
    while True:
        payload = sample_once(stall_minutes=args.stall_minutes)
        print_compact(payload)
        if args.once or args.duration_minutes <= 0 or time.time() >= end_at:
            return 0 if not payload.get("warnings") else 1
        time.sleep(max(20, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
