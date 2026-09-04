"""Generate the AVSHUNTER Live UAT readiness report."""

from __future__ import annotations

import csv
import glob
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "data" / "output" / "runs"
QA_DIR = ROOT / "data" / "output" / "qa"

try:
    csv.field_size_limit(10_000_000)
except OverflowError:
    csv.field_size_limit(sys.maxsize)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _latest_run_id() -> str:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        payload = json.loads(latest.read_text(encoding="utf-8-sig"))
        if payload.get("run_id"):
            return str(payload["run_id"])
    dirs = sorted([p.name for p in RUNS_DIR.iterdir() if p.is_dir() and p.name != "latest"])
    return dirs[-1]


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _latest(pattern: str) -> Optional[Path]:
    matches = sorted(Path(p) for p in glob.glob(str(QA_DIR / pattern)))
    return matches[-1] if matches else None


def _csv_count(path: Optional[Path]) -> int:
    if not path or not path.exists() or path.suffix.lower() != ".csv":
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return sum(1 for _ in csv.DictReader(fh))


def _run_files(run_id: str) -> Dict[str, str]:
    run = RUNS_DIR / run_id
    def latest(sub: str, pattern: str) -> str:
        folder = run / sub if sub else run
        matches = sorted(folder.glob(pattern)) if folder.exists() else []
        return str(matches[-1]) if matches else ""
    return {
        "intelligent_orchestrator": str(ROOT / "intelligent_orchestrator.py"),
        "intelligence_lab": str(ROOT / "intelligence-lab" / "intelligence_lab.py"),
        "index_html": str(ROOT / "intelligence-lab" / "static" / "index.html"),
        "morning_validator": str(ROOT / "morning_gate.py"),
        "handoff_contract": str(ROOT / "contracts" / "handoff_contract.py"),
        "lab_control": str(ROOT / "contracts" / "lab_control.py"),
        "physics_engine": str(ROOT / "vanguard" / "physics_state_engine.py"),
        "vanguard_runner": str(ROOT / "scripts" / "run_vanguard_from_packages.py"),
        "options_intelligence": str(ROOT / "scripts" / "avshunter_options_intelligence.py"),
        "eil_pse": str(ROOT / "execution_intelligence_runner.py"),
        "trade_journal": str(ROOT / "avshunter_trade_journal.py"),
        "outcome_capture": str(ROOT / "outcome_capture.py"),
        "discovery": latest("discovery", "discovery_candidates_*.csv"),
        "vanguard": latest("options", "vanguard_signals_enriched_*.csv"),
        "eil": latest("superbrain", "eil_enriched_*.csv"),
        "execution": latest("execution", "execution_v3_5_*.csv"),
        "options": latest("options", "options_intelligence_*.csv"),
        "v5": latest("superbrain", "AVSHUNTER_SIGNALS_V5_*.csv"),
        "final_run_manifest": latest("", "final_run_manifest.json"),
        "final_opportunity_book_csv": latest("intelligence_lab", "final_opportunity_book_*.csv"),
        "final_opportunity_book_json": latest("intelligence_lab", "final_opportunity_book_*.json"),
        "morning_validated": latest("morning_validation", "morning_validated_trades_*.csv"),
        "morning_packet": latest("morning_validation", "morning_validation_packet_*.json"),
        "dropoff_audit_csv": latest("diagnostics", f"dropoff_audit_{run_id}.csv"),
        "dropoff_audit_json": latest("diagnostics", f"dropoff_audit_{run_id}.json"),
        "handoff_contract_audit_csv": latest("diagnostics", f"handoff_contract_audit_{run_id}.csv"),
        "handoff_contract_audit_json": latest("diagnostics", f"handoff_contract_audit_{run_id}.json"),
        "trade_journal_db": str(ROOT / "data" / "journal" / "trade_journal.db"),
        "tests_dir": str(ROOT / "tests"),
        "scripts_dir": str(ROOT / "scripts"),
        "runs_dir": str(RUNS_DIR),
    }


def _git_branch() -> str:
    try:
        proc = subprocess.run(["git", "branch", "--show-current"], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
        return proc.stdout.strip() or "UNKNOWN"
    except Exception:
        return "UNAVAILABLE"


def _journal_counts(db_path: str) -> Dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {"exists": False, "open_count": 0, "closed_count": 0}
    conn = sqlite3.connect(path)
    try:
        open_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        closed_count = conn.execute("SELECT COUNT(*) FROM closed_trades").fetchone()[0]
        return {"exists": True, "open_count": open_count, "closed_count": closed_count}
    finally:
        conn.close()


def _ui_check(path: str) -> Dict[str, Any]:
    html = Path(path).read_text(encoding="utf-8", errors="replace")
    tokens = [
        "Run Health",
        "Execute Brief",
        "Armed Monitor",
        "Open Positions",
        "Exit Ticket",
        "Outcomes",
        "Learning Loop",
        "mv__live_validation_state",
        "lab_verdict",
        "conflict_state",
        "execution_lock_reason",
        "physics_state_id",
        "phase_transition_probability",
        "lab_tradeable",
        "declared_R",
        "requires_live_validation",
        "HARD_CONFLICT",
    ]
    missing = [t for t in tokens if t not in html]
    return {"passed": not missing, "missing_tokens": missing}


def main() -> int:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    run_id = _latest_run_id()
    files = _run_files(run_id)

    baton = _read_json(_latest("baton_integrity_report_*.json"))
    conflict = _read_json(QA_DIR / "qa_conflict_resolver_latest.json")
    morning = _read_json(QA_DIR / "qa_morning_validator_latest.json")
    smoke = _read_json(QA_DIR / "smoke_test_live_uat_pipeline_latest.json")
    manifest = _read_json(Path(files["final_run_manifest"]))
    dropoff_audit = _read_json(Path(files["dropoff_audit_json"])) if files.get("dropoff_audit_json") else {}
    handoff_audit = _read_json(Path(files["handoff_contract_audit_json"])) if files.get("handoff_contract_audit_json") else {}

    row_counts = {k: _csv_count(Path(v)) for k, v in files.items() if v and v.lower().endswith(".csv")}
    ui = _ui_check(files["index_html"])
    journal = _journal_counts(files["trade_journal_db"])

    defects: List[Dict[str, Any]] = []
    warnings: List[str] = []

    def sev(level: int, title: str, detail: Any = None):
        defects.append({"severity": level, "title": title, "detail": detail})

    required_files = [
        "final_run_manifest",
        "final_opportunity_book_csv",
        "final_opportunity_book_json",
        "morning_validated",
        "morning_packet",
        "dropoff_audit_csv",
        "dropoff_audit_json",
        "handoff_contract_audit_csv",
        "handoff_contract_audit_json",
    ]
    for key in required_files:
        if not files.get(key) or not Path(files[key]).exists():
            sev(1, f"Missing required artefact: {key}", files.get(key))

    if not baton.get("passed"):
        sev(1, "Baton integrity QA failed or missing", baton.get("failures"))
    if not conflict.get("passed"):
        sev(1, "Conflict resolver QA failed or missing", conflict.get("results"))
    if not morning.get("passed"):
        sev(1, "Morning validator QA failed or missing", morning.get("results"))
    if not smoke.get("passed"):
        sev(1, "Live UAT API smoke failed or missing", smoke.get("checks"))
    if not dropoff_audit:
        sev(1, "Drop-off audit missing; cannot explain where/why tickers fell off", files.get("dropoff_audit_json"))
    elif int(dropoff_audit.get("rows") or 0) <= 0:
        sev(1, "Drop-off audit has no rows", dropoff_audit)
    if not handoff_audit:
        sev(1, "Handoff contract audit missing; cannot prove receivers recognized upstream fields", files.get("handoff_contract_audit_json"))
    elif handoff_audit.get("overall_status") == "FAIL":
        sev(1, "Handoff contract audit failed", handoff_audit.get("outstanding_fixes"))
    elif handoff_audit.get("overall_status") == "WARN":
        sev(2, "Handoff contract audit has warnings", handoff_audit.get("outstanding_fixes"))
    if not ui.get("passed"):
        sev(2, "UI cockpit contract missing expected tokens", ui)
    if not journal.get("exists"):
        sev(1, "Trade journal DB missing", files["trade_journal_db"])

    if manifest.get("run_tradeable") is False:
        if manifest.get("next_action") == "NEEDS_MORNING_VALIDATION":
            warnings.append("Manifest correctly holds live trading until morning validation completes.")
        elif manifest.get("next_action") == "NEEDS_LIVE_UAT":
            warnings.append("Manifest correctly holds live trading after paper validation; promote to live UAT, not go-live.")
        else:
            sev(2, "Manifest marks run not tradeable", manifest.get("fatal_flags"))
    if manifest.get("next_action") not in {"READY_FOR_LAB", "NEEDS_MORNING_VALIDATION", "NEEDS_LIVE_UAT", "BLOCKED_REPAIR_REQUIRED", "NO_CANDIDATES"}:
        sev(2, "Manifest next_action invalid", manifest.get("next_action"))
    if not files.get("v5"):
        warnings.append("Legacy AVSHUNTER_SIGNALS_V5 output missing; accepted as optional legacy context if Lab fields are populated.")

    sev1 = sum(1 for d in defects if d["severity"] == 1)
    sev2 = sum(1 for d in defects if d["severity"] == 2)
    sev3 = sum(1 for d in defects if d["severity"] >= 3)

    if sev1:
        status = "BLOCKED"
    elif sev2:
        status = "BLOCKED"
    elif warnings:
        status = "PROMOTE_WITH_WARNINGS"
    else:
        status = "PROMOTE_TO_LIVE_UAT"

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_branch": _git_branch(),
        "latest_run_id_tested": run_id,
        "files_audited": files,
        "row_counts": row_counts,
        "schema_pass": bool(baton.get("passed")),
        "baton_integrity_pass": bool(baton.get("passed")),
        "conflict_resolver_pass": bool(conflict.get("passed")),
        "morning_validator_pass": bool(morning.get("passed")),
        "api_smoke_test_pass": bool(smoke.get("passed")),
        "dropoff_audit_pass": bool(dropoff_audit and int(dropoff_audit.get("rows") or 0) > 0),
        "handoff_contract_audit_pass": handoff_audit.get("overall_status") == "PASS",
        "dropoff_behavior": {
            "rows": dropoff_audit.get("rows"),
            "last_stage_counts": dropoff_audit.get("last_stage_counts", {}),
            "dropoff_stage_counts": dropoff_audit.get("dropoff_stage_counts", {}),
            "top_dropoff_reasons": dropoff_audit.get("top_dropoff_reasons", {}),
        },
        "handoff_contract_audit": {
            "overall_status": handoff_audit.get("overall_status"),
            "fail_count": handoff_audit.get("fail_count"),
            "warn_count": handoff_audit.get("warn_count"),
            "output_csv": handoff_audit.get("output_csv"),
        },
        "ui_qa_pass": bool(ui.get("passed")),
        "journal_qa_pass": bool(journal.get("exists")),
        "outcome_loop_pass": bool(smoke.get("passed")),
        "journal": journal,
        "manifest_state": {
            "run_id": manifest.get("run_id"),
            "pipeline_mode": manifest.get("pipeline_mode"),
            "run_health_score": manifest.get("run_health_score"),
            "next_action": manifest.get("next_action"),
            "run_tradeable": manifest.get("run_tradeable"),
            "stale_flags": manifest.get("stale_flags", []),
            "fatal_flags": manifest.get("fatal_flags", []),
        },
        "unresolved_defects": defects,
        "warnings": warnings,
        "severity_breakdown": {"sev1": sev1, "sev2": sev2, "sev3": sev3},
        "live_uat_status": status,
    }

    stamp = _stamp()
    json_path = QA_DIR / f"live_uat_readiness_report_{stamp}.json"
    md_path = QA_DIR / f"live_uat_readiness_report_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    md = [
        f"# AVSHUNTER Live UAT Readiness Report",
        f"",
        f"- Timestamp: `{report['timestamp']}`",
        f"- Latest run: `{run_id}`",
        f"- Status: `{status}`",
        f"- Manifest next action: `{manifest.get('next_action', '')}`",
        f"- Manifest tradeable: `{manifest.get('run_tradeable', '')}`",
        f"- Run health: `{manifest.get('run_health_score', '')}`",
        f"- Baton integrity: `{report['baton_integrity_pass']}`",
        f"- Conflict resolver: `{report['conflict_resolver_pass']}`",
        f"- Morning validator: `{report['morning_validator_pass']}`",
        f"- API smoke: `{report['api_smoke_test_pass']}`",
        f"- Drop-off audit: `{report['dropoff_audit_pass']}`",
        f"- Handoff contract audit: `{report['handoff_contract_audit_pass']}`",
        f"- UI QA: `{report['ui_qa_pass']}`",
        f"- Journal QA: `{report['journal_qa_pass']}`",
        f"",
        "## Defects",
    ]
    if defects:
        md.extend([f"- SEV-{d['severity']}: {d['title']}" for d in defects])
    else:
        md.append("- None")
    if warnings:
        md.append("")
        md.append("## Warnings")
        md.extend([f"- {w}" for w in warnings])
    if dropoff_audit:
        md.append("")
        md.append("## Drop-Off Behaviour")
        md.append(f"- Rows: `{dropoff_audit.get('rows', 0)}`")
        md.append(f"- Stage counts: `{dropoff_audit.get('dropoff_stage_counts', {})}`")
        md.append(f"- Top reasons: `{dropoff_audit.get('top_dropoff_reasons', {})}`")
    if handoff_audit:
        md.append("")
        md.append("## Handoff Contract Audit")
        md.append(f"- Status: `{handoff_audit.get('overall_status', '')}`")
        md.append(f"- Fail: `{handoff_audit.get('fail_count', 0)}`")
        md.append(f"- Warn: `{handoff_audit.get('warn_count', 0)}`")
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"live_uat_status": status, "json": str(json_path), "md": str(md_path), "severity_breakdown": report["severity_breakdown"]}, indent=2))
    return 0 if status != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
