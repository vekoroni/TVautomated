"""End-to-end baton integrity QA for the latest AVSHUNTER run.

Tracks a sample of candidates through source CSVs, final opportunity book, and
the Intelligence Lab payload. Writes JSON and CSV reports under data/output/qa.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RUNS_DIR = ROOT / "data" / "output" / "runs"

FILE_PATTERNS = {
    "discovery": ("discovery", "discovery_candidates_*.csv"),
    "vanguard": ("options", "vanguard_signals_enriched_*.csv"),
    "eil": ("superbrain", "eil_enriched_*.csv"),
    "execution": ("execution", "execution_v3_5_*.csv"),
    "options": ("options", "options_intelligence_*.csv"),
    "v5": ("superbrain", "AVSHUNTER_SIGNALS_V5_*.csv"),
    "manifest": ("", "final_run_manifest.json"),
    "opportunity_book_csv": ("intelligence_lab", "final_opportunity_book_*.csv"),
    "opportunity_book_json": ("intelligence_lab", "final_opportunity_book_*.json"),
    "morning_csv": ("morning_validation", "morning_validated_trades_*.csv"),
    "morning_packet": ("morning_validation", "morning_validation_packet_*.json"),
}

CRITICAL_BOOK_FIELDS = [
    "run_id",
    "ticker",
    "trade_idea_id",
    "direction",
    "contract_symbol",
    "strike",
    "expiry",
    "dte",
    "premium_mid",
    "lab_verdict",
    "lab_tradeable",
    "morning_execution_permission",
    "morning_execution_route",
    "morning_lab_alignment_status",
    "conflict_state",
    "execution_lock_reason",
    "physics_state_id",
    "hidden_state_label",
    "state_transition_label",
    "phase_transition_probability",
    "actuarial_match_method",
    "actuarial_sample_size",
    "priority_score",
    "rr_predicted",
    "ev_predicted",
    "win_prob_predicted",
]

FIELD_GROUPS = {
    "physics": ["physics_state_id", "hidden_state_label", "state_transition_label", "phase_transition_probability"],
    "macro": ["macro_regime", "sector_tilt", "regime_drift_status"],
    "actuarial": ["actuarial_match_method", "actuarial_sample_size", "actuarial_confidence"],
    "options": ["contract_symbol", "strike", "expiry", "dte", "premium_mid", "spread_pct"],
    "morning": ["mv__morning_execution_permission", "mv__execution_permission", "mv__live_validation_state", "mv__validation_score"],
}


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().upper() in {"", "NONE", "NAN", "NULL", "N/A", "UNKNOWN", "MISSING"}


def _read_csv(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _latest_run_id() -> str:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        payload = json.loads(latest.read_text(encoding="utf-8-sig"))
        if payload.get("run_id"):
            return str(payload["run_id"])
    dirs = sorted([p.name for p in RUNS_DIR.iterdir() if p.is_dir() and p.name != "latest"])
    if not dirs:
        raise FileNotFoundError("No run directories found")
    return dirs[-1]


def _glob_latest(run_dir: Path, subdir: str, pattern: str) -> Optional[Path]:
    folder = run_dir / subdir if subdir else run_dir
    matches = sorted(folder.glob(pattern)) if folder.exists() else []
    return matches[-1] if matches else None


def _file_audit(name: str, path: Optional[Path], required: Iterable[str]) -> Dict[str, Any]:
    exists = bool(path and path.exists())
    rows = _read_csv(path) if exists and path.suffix.lower() == ".csv" else []
    columns = list(rows[0].keys()) if rows else []
    missing_cols = [c for c in required if c not in columns]
    key_counts = Counter(str(r.get("ticker", "")).upper() for r in rows if r.get("ticker"))
    duplicates = [k for k, v in key_counts.items() if v > 1]
    null_rates = {}
    for col in required:
        if col in columns and rows:
            null_rates[col] = round(sum(1 for r in rows if _missing(r.get(col))) / len(rows), 4)
    numeric_bad = []
    for col in ["strike", "dte", "premium_mid", "priority_score", "phase_transition_probability", "actuarial_sample_size"]:
        if col in columns:
            bad = 0
            for row in rows[:500]:
                val = row.get(col)
                if _missing(val):
                    continue
                try:
                    float(str(val).replace("%", "").replace("$", ""))
                except Exception:
                    bad += 1
            if bad:
                numeric_bad.append({"column": col, "bad_sample_count": bad})
    return {
        "name": name,
        "exists": exists,
        "path": str(path or ""),
        "row_count": len(rows),
        "required_columns_present": not missing_cols,
        "missing_columns": missing_cols,
        "duplicate_tickers": duplicates[:25],
        "null_rates": null_rates,
        "malformed_numeric_fields": numeric_bad,
    }


def _lab_payload(run_id: str) -> List[Dict[str, Any]]:
    mod_path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = mod._load_run(run_id)
    return payload.get("signals", [])


def _by_ticker(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).upper().strip()
        if ticker and ticker not in out:
            out[ticker] = row
    return out


def main() -> int:
    run_id = _latest_run_id()
    run_dir = RUNS_DIR / run_id
    paths = {name: _glob_latest(run_dir, *spec) for name, spec in FILE_PATTERNS.items()}
    rows = {name: _read_csv(path) for name, path in paths.items() if path and path.suffix.lower() == ".csv"}
    lab_rows = _lab_payload(run_id)
    rows["lab_payload"] = lab_rows

    audits = [
        _file_audit("discovery", paths.get("discovery"), ["ticker"]),
        _file_audit("vanguard", paths.get("vanguard"), ["ticker"]),
        _file_audit("eil", paths.get("eil"), ["ticker"]),
        _file_audit("execution", paths.get("execution"), ["ticker"]),
        _file_audit("options", paths.get("options"), ["ticker"]),
        _file_audit("v5", paths.get("v5"), ["ticker"]),
        _file_audit("final_opportunity_book", paths.get("opportunity_book_csv"), CRITICAL_BOOK_FIELDS),
        _file_audit("morning_validation", paths.get("morning_csv"), ["ticker", "live_validation_state", "morning_execution_permission", "execution_permission"]),
    ]

    book_rows = rows.get("opportunity_book_csv", [])
    sample = [r for r in book_rows if str(r.get("lab_verdict", "")).upper() in {"GO", "ARMED"}][:25] or book_rows[:25]
    source_maps = {name: _by_ticker(source_rows) for name, source_rows in rows.items()}

    sample_checks = []
    failures = []
    for row in sample:
        ticker = str(row.get("ticker", "")).upper().strip()
        lab = source_maps.get("lab_payload", {}).get(ticker, {})
        check = {"ticker": ticker, "issues": []}
        for field in ["run_id", "ticker", "trade_idea_id", "lab_verdict", "lab_tradeable", "conflict_state"]:
            if _missing(row.get(field)):
                check["issues"].append(f"book_missing:{field}")
        if lab:
            for field in ["ticker", "lab_verdict", "lab_tradeable", "conflict_state"]:
                if _missing(lab.get(field)):
                    check["issues"].append(f"lab_missing:{field}")
            for field in FIELD_GROUPS["physics"]:
                if not _missing(row.get(field)) and _missing(lab.get(field)):
                    check["issues"].append(f"lab_dropped:{field}")
            if str(lab.get("conflict_state", "")).upper() == "HARD_CONFLICT" and str(lab.get("lab_tradeable")).lower() in {"true", "1", "yes"}:
                check["issues"].append("hard_conflict_tradeable")
        else:
            check["issues"].append("missing_from_lab_payload")

        vg = source_maps.get("vanguard", {}).get(ticker, {})
        for field in FIELD_GROUPS["physics"]:
            if vg and not _missing(vg.get(field)) and _missing(row.get(field)):
                check["issues"].append(f"book_dropped_vanguard:{field}")
        morning = source_maps.get("morning_csv", {}).get(ticker, {})
        if morning and _missing(lab.get("mv__morning_execution_permission")) and _missing(lab.get("mv__execution_permission")):
            check["issues"].append("lab_dropped_morning_validation")
        if morning:
            if _missing(row.get("morning_execution_permission")):
                check["issues"].append("book_dropped_morning_execution_permission")
            if str(lab.get("morning_lab_alignment_status", "")).upper() == "CONFLICT":
                check["issues"].append("lab_morning_alignment_conflict")
            if str(row.get("morning_lab_alignment_status", "")).upper() == "CONFLICT":
                check["issues"].append("book_morning_alignment_conflict")

        if check["issues"]:
            failures.append(check)
        sample_checks.append(check)

    passed = not failures and all(a["exists"] for a in audits if a["name"] in {"vanguard", "eil", "options", "final_opportunity_book"})
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "passed": passed,
        "paths": {k: str(v or "") for k, v in paths.items()},
        "file_audit": audits,
        "sample_size": len(sample_checks),
        "sample_checks": sample_checks,
        "failure_count": len(failures),
        "failures": failures,
    }

    out_dir = ROOT / "data" / "output" / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    json_path = out_dir / f"baton_integrity_report_{stamp}.json"
    csv_path = out_dir / f"baton_integrity_report_{stamp}.csv"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "passed", "issues"])
        writer.writeheader()
        for check in sample_checks:
            writer.writerow({
                "ticker": check["ticker"],
                "passed": not check["issues"],
                "issues": json.dumps(check["issues"], ensure_ascii=True),
            })

    print(json.dumps({"passed": passed, "run_id": run_id, "json": str(json_path), "csv": str(csv_path), "failure_count": len(failures)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
