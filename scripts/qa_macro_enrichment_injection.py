#!/usr/bin/env python3
"""
QA probe for macro enrichment package injection.

Creates a disposable one-package run, executes the real injection script, and
verifies the enriched MacroContext is present inside the package exactly where
Vanguard reads it from. The disposable run is removed unless --keep-temp is set.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


REPO = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO / "data" / "output" / "runs"
QA_DIR = REPO / "data" / "output" / "qa"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts.macro_enrichment_delta import (  # noqa: E402
    PROTECTED_MACRO_FIELDS,
    candidate_macro_enrichment_audit,
    find_macro_enrichment_delta,
)
from scripts.macro_quant_packet import build_macro_quant_packet  # noqa: E402


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)


def resolve_path(raw: str | None, fallback: Path) -> Path:
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else (REPO / path).resolve()
    return fallback


def safe_remove_temp_run(path: Path) -> None:
    resolved = path.resolve()
    runs_root = RUNS_DIR.resolve()
    if resolved.parent != runs_root or not resolved.name.startswith("_QA_MACRO_INJECTION_"):
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved}")
    shutil.rmtree(resolved)


def build_probe_package(run_dir: Path, run_id: str, ticker: str) -> Path:
    pkg_path = run_dir / "packages" / f"{ticker}.package.json"
    package = {
        "ticker": ticker,
        "run_id": run_id,
        "discovery": {
            "ticker": ticker,
            "run_id": run_id,
            "source": "QA_MACRO_ENRICHMENT_INJECTION",
        },
    }
    write_json(pkg_path, package)
    return pkg_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify macro enrichment injection into packages.")
    parser.add_argument("--ticker", default="INTC", help="Ticker to use for exposure lookup verification.")
    parser.add_argument(
        "--macro-path",
        default=str(REPO / "dropbox" / "macro" / "macro_intelligence_latest.json"),
        help="Base macro JSON path.",
    )
    parser.add_argument(
        "--enrichment-path",
        default="",
        help=(
            "Macro enrichment delta path. Defaults to dropbox/macro/"
            "macro_enrichment_delta_latest.json when present, otherwise the test fixture."
        ),
    )
    parser.add_argument("--keep-temp", action="store_true", help="Keep the disposable QA run folder.")
    args = parser.parse_args()

    ticker = str(args.ticker or "").strip().upper()
    if not ticker:
        raise SystemExit("ERROR: --ticker is required")

    macro_path = resolve_path(args.macro_path, REPO / "dropbox" / "macro" / "macro_intelligence_latest.json")
    fixture_enrichment = REPO / "tests" / "fixtures" / "macro_enrichment_delta_sample.json"
    discovered_enrichment = find_macro_enrichment_delta(macro_path)
    if args.enrichment_path:
        enrichment_path = resolve_path(args.enrichment_path, REPO / "dropbox" / "macro" / "macro_enrichment_delta_latest.json")
    else:
        enrichment_path = discovered_enrichment or fixture_enrichment

    if not macro_path.exists():
        raise SystemExit(f"ERROR: base macro not found: {macro_path}")
    if not enrichment_path.exists():
        raise SystemExit(f"ERROR: enrichment delta not found: {enrichment_path}")

    QA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"_QA_MACRO_INJECTION_{utc_stamp()}"
    run_dir = RUNS_DIR / run_id
    pkg_path = build_probe_package(run_dir, run_id, ticker)

    report: Dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "FAIL",
        "run_id": run_id,
        "ticker": ticker,
        "macro_path": str(macro_path),
        "enrichment_path": str(enrichment_path),
        "dropbox_enrichment_present": discovered_enrichment is not None,
        "used_fixture_fallback": enrichment_path == fixture_enrichment,
        "package_path": str(pkg_path),
        "checks": {},
    }

    try:
        base_macro = read_json(macro_path)
        expected_macro = dict(base_macro)
        expected_macro["macro_quant_packet"] = build_macro_quant_packet(expected_macro, macro_path)
        protected_before = {
            key: expected_macro.get(key)
            for key in PROTECTED_MACRO_FIELDS
            if key in expected_macro
        }

        cmd = [
            sys.executable,
            str(REPO / "scripts" / "inject_macro_into_packages.py"),
            "--run-id",
            run_id,
            "--macro-path",
            str(macro_path),
        ]
        if args.enrichment_path or discovered_enrichment is None:
            cmd.extend(["--macro-enrichment-delta", str(enrichment_path)])
        proc = subprocess.run(cmd, cwd=str(REPO), text=True, capture_output=True, timeout=120)
        report["inject_stdout"] = proc.stdout.strip()
        report["inject_stderr"] = proc.stderr.strip()
        report["inject_returncode"] = proc.returncode
        if proc.returncode != 0:
            write_json(QA_DIR / f"macro_enrichment_injection_report_{utc_stamp()}.json", report)
            print("FAIL: inject_macro_into_packages returned non-zero")
            print(proc.stdout)
            print(proc.stderr)
            return proc.returncode or 1

        injected_pkg = read_json(pkg_path)
        macro_block = injected_pkg.get("macro") or {}
        payload = macro_block.get("payload") or {}
        extras = payload.get("extras") or {}
        exposure_index = extras.get("macro_exposure_index") or {}
        exposures = exposure_index.get(ticker) or []
        audit = candidate_macro_enrichment_audit(payload, ticker)

        protected_after = {
            key: payload.get(key)
            for key in protected_before
        }
        protected_preserved = protected_after == protected_before

        checks = {
            "macro_block_written": isinstance(macro_block, dict) and bool(macro_block),
            "enrichment_delta_path_written": bool(macro_block.get("enrichment_delta_path")),
            "payload_has_enrichment_namespace": isinstance(extras.get("macro_enrichment_delta"), dict),
            "payload_has_exposure_index": isinstance(exposure_index, dict) and bool(exposure_index),
            "ticker_has_exposure": bool(exposures),
            "candidate_audit_has_theme": int(audit.get("macro_enrichment_theme_count") or 0) > 0,
            "candidate_audit_gate_preserved": audit.get("macro_enrichment_gate_preserved") is True,
            "macro_quant_packet_written": isinstance(injected_pkg.get("macro_quant_packet"), dict),
            "regime_snapshot_written": isinstance(injected_pkg.get("regime_snapshot"), dict),
            "truth_packet_written": isinstance(injected_pkg.get("truth_packet"), dict),
            "protected_fields_preserved": protected_preserved,
        }
        report["checks"] = checks
        report["candidate_audit"] = audit
        report["exposures_for_ticker"] = exposures
        report["protected_fields_compared"] = sorted(protected_before)
        report["status"] = "PASS" if all(checks.values()) else "FAIL"

        report_path = QA_DIR / f"macro_enrichment_injection_report_{utc_stamp()}.json"
        write_json(report_path, report)
        report["report_path"] = str(report_path)

        print(f"{report['status']}: macro enrichment package injection")
        print(f"  ticker: {ticker}")
        print(f"  enrichment: {enrichment_path}")
        print(f"  dropbox enrichment present: {discovered_enrichment is not None}")
        print(f"  fixture fallback used: {enrichment_path == fixture_enrichment}")
        print(f"  exposure matches: {len(exposures)}")
        print(f"  report: {report_path}")
        if report["status"] != "PASS":
            failed = [name for name, ok in checks.items() if not ok]
            print(f"  failed checks: {', '.join(failed)}")
            return 1
        return 0
    finally:
        if not args.keep_temp and run_dir.exists():
            safe_remove_temp_run(run_dir)


if __name__ == "__main__":
    raise SystemExit(main())
