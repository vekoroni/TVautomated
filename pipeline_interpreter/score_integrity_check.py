"""
AVSHUNTER Score Integrity Check
=================================
Asserts that scs_score values in morning_validated_trades match
what the Intelligence Lab receives. Logs mismatch rate per run.
Writes audit log to data/output/runs/{run_id}/score_integrity_{run_id}.json

A mismatch is defined as: abs(triage_score - lab_score) > 0.01
Decommission threshold: mismatch_rate > 0.05 across 10 consecutive runs.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("score_integrity")

ROOT      = Path(__file__).resolve().parent.parent
RUNS_DIR  = ROOT / "data" / "output" / "runs"
AUDIT_LOG = ROOT / "data" / "output" / "score_integrity_history.json"

MISMATCH_THRESHOLD    = 0.01   # scores within this are equal
DECOMMISSION_RATE     = 0.05   # >5% mismatch triggers decommission flag
DECOMMISSION_RUNS     = 10     # must persist across this many consecutive runs


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value: Any) -> Optional[float]:
    try:
        v = float(str(value).strip())
        return None if v != v else v
    except Exception:
        return None


def _load_run_id() -> Optional[str]:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8-sig"))
            return str(data.get("run_id") or data.get("latest_run_id", "")).strip() or None
        except Exception:
            pass
    if RUNS_DIR.exists():
        dirs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
        return dirs[-1] if dirs else None
    return None


def check_score_integrity(run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Compare scs_score in morning_validated_trades vs lab_signals.
    Returns integrity report dict.
    """
    run_id = run_id or _load_run_id()
    if not run_id:
        return {"error": "Cannot resolve run_id", "integrity_pass": False}

    run_dir = RUNS_DIR / run_id
    mv_dir  = run_dir / "morning_validation"

    # Source 1: morning_validated_trades (canonical pipeline output)
    mv_path = mv_dir / f"morning_validated_trades_{run_id}.csv"
    if not mv_path.exists():
        return {"error": f"morning_validated_trades not found: {mv_path}", "integrity_pass": False}

    mv_rows = _read_csv(mv_path)
    mv_scores: Dict[str, float] = {}
    for row in mv_rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        score  = _f(row.get("scs_score") or row.get("composite") or row.get("score"))
        if ticker and score is not None:
            mv_scores[ticker] = score

    # Source 2: Intelligence Lab signal file
    # Try multiple known Lab output filenames
    lab_candidates = [
        run_dir / f"lab_signals_{run_id}.csv",
        run_dir / f"intelligence_lab_signals_{run_id}.csv",
        run_dir / "morning_validation" / f"lab_signals_{run_id}.csv",
        run_dir / f"superbrain_enriched_{run_id}.csv",
    ]
    lab_path = next((p for p in lab_candidates if p.exists()), None)

    lab_scores: Dict[str, float] = {}
    lab_source = "NOT_FOUND"
    if lab_path:
        lab_source = lab_path.name
        lab_rows = _read_csv(lab_path)
        for row in lab_rows:
            ticker = str(row.get("ticker", "")).strip().upper()
            score  = _f(row.get("scs_score") or row.get("composite") or row.get("score"))
            if ticker and score is not None:
                lab_scores[ticker] = score

    # Compare
    mismatches: List[Dict[str, Any]] = []
    compared = 0
    common_tickers = set(mv_scores.keys()) & set(lab_scores.keys())

    for ticker in sorted(common_tickers):
        mv_s  = mv_scores[ticker]
        lab_s = lab_scores[ticker]
        delta = abs(mv_s - lab_s)
        compared += 1
        if delta > MISMATCH_THRESHOLD:
            mismatches.append({
                "ticker":     ticker,
                "mv_score":   round(mv_s, 4),
                "lab_score":  round(lab_s, 4),
                "delta":      round(delta, 4),
            })

    mismatch_rate = len(mismatches) / compared if compared > 0 else 0.0
    integrity_pass = mismatch_rate <= DECOMMISSION_RATE

    report = {
        "run_id":           run_id,
        "checked_at_utc":   _utc_now(),
        "mv_tickers":       len(mv_scores),
        "lab_tickers":      len(lab_scores),
        "lab_source":       lab_source,
        "compared":         compared,
        "mismatches":       len(mismatches),
        "mismatch_rate":    round(mismatch_rate, 4),
        "integrity_pass":   integrity_pass,
        "decommission_flag": False,
        "mismatch_detail":  mismatches[:20],  # cap detail at 20 rows
    }

    # Write run-level audit
    audit_path = run_dir / f"score_integrity_{run_id}.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Update rolling history and check decommission threshold
    _update_history(run_id, mismatch_rate, report)

    log.info(
        "Score integrity: run=%s compared=%d mismatches=%d rate=%.1f%% pass=%s",
        run_id, compared, len(mismatches),
        mismatch_rate * 100, integrity_pass
    )
    return report


def _update_history(run_id: str, mismatch_rate: float, report: Dict) -> None:
    """Append to rolling history. Flag decommission if threshold breached."""
    history: List[Dict] = []
    if AUDIT_LOG.exists():
        try:
            history = json.loads(AUDIT_LOG.read_text(encoding="utf-8"))
        except Exception:
            history = []

    history.append({
        "run_id":        run_id,
        "checked_at":    report["checked_at_utc"],
        "mismatch_rate": mismatch_rate,
        "compared":      report["compared"],
    })

    # Keep last 20 runs only
    history = history[-20:]

    # Check decommission: last N runs all above threshold
    recent = history[-DECOMMISSION_RUNS:]
    if (
        len(recent) >= DECOMMISSION_RUNS
        and all(r["mismatch_rate"] > DECOMMISSION_RATE for r in recent)
    ):
        report["decommission_flag"] = True
        _write_decommission_notice(history)
        log.warning(
            "DECOMMISSION THRESHOLD BREACHED: mismatch_rate > %.0f%% "
            "across last %d runs. Triage routing should be removed.",
            DECOMMISSION_RATE * 100, DECOMMISSION_RUNS
        )

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_LOG.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _write_decommission_notice(history: List[Dict]) -> None:
    notice_path = ROOT / "data" / "output" / "TRIAGE_DECOMMISSION_NOTICE.json"
    notice = {
        "notice":        "TRIAGE_DECOMMISSION_REQUIRED",
        "reason":        (
            f"scs_score mismatch rate exceeded {DECOMMISSION_RATE*100:.0f}% "
            f"across {DECOMMISSION_RUNS} consecutive runs"
        ),
        "created_at":    _utc_now(),
        "recent_history": history[-DECOMMISSION_RUNS:],
        "action_required": (
            "Remove triage routing from pipeline_interpreter_commands.py. "
            "Intelligence Lab reads directly from morning_validated_trades. "
            "Delete triage-related display code from index.html."
        ),
    }
    notice_path.write_text(json.dumps(notice, indent=2), encoding="utf-8")
    log.warning("Decommission notice written: %s", notice_path)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [INTEGRITY] %(message)s")
    parser = argparse.ArgumentParser(description="AVSHUNTER Score Integrity Check")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    report = check_score_integrity(args.run_id)
    print(json.dumps(report, indent=2))
