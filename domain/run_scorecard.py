"""End-of-line scorecards (output-trust item 10, part 10.4; C-2).

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. Five sections - data, calculation,
structure, calibration, trading performance - each PASS / REVIEW / FAIL / NOT_AVAILABLE with the facts that set it.
Reads what the run already writes (manifest, handoff audit, station reports, tools/avs_verify report, C12 outcome
scoring) and the replay calibration table. Missing evidence is NOT_AVAILABLE, never PASS. Report only: the scorecard
never stops the run (the station inspections do).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_RANK = {"PASS": 0, "NOT_AVAILABLE": 1, "REVIEW": 2, "FAIL": 3}
SETUP_RATES = Path(__file__).resolve().parents[1] / "config" / "setup_rates_v1.json"


def _load(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else None
    except (OSError, ValueError):
        return None


def _section(status: str, **facts: Any) -> Dict[str, Any]:
    return {"status": status, "facts": facts}


def _forward(outcome_store: Optional[Path | str]) -> Dict[str, Any]:
    """Item 10.2: the forward calibration state read from the C12 outcome store; a missing store is NOT_AVAILABLE."""
    if outcome_store is None or not Path(outcome_store).is_file():
        return {"forward_state": "NOT_AVAILABLE", "forward_setups": None, "forward_resolved": None,
                "forward_calibrated": None, "forward_miscalibrated": None, "forward_report": None}
    from domain.forward_calibration import forward_calibration, load_forward_rows
    report = forward_calibration(load_forward_rows(outcome_store))
    states = [s["state"] for s in report["setups"].values()]
    return {"forward_state": report["state"], "forward_setups": len(states),
            "forward_resolved": sum(s["resolved"] for s in report["setups"].values()),
            "forward_calibrated": states.count("CALIBRATED"), "forward_miscalibrated": states.count("MISCALIBRATED"),
            "forward_report": report}


def build_scorecard(run_dir: Path | str, *, run_id: str, phase: str, verify_root: Path | str,
                    outcome_store: Optional[Path | str] = None) -> Dict[str, Any]:
    run = Path(run_dir)
    diag = run / "diagnostics"
    manifest = _load(run / "final_run_manifest.json")
    handoff = _load(diag / f"handoff_contract_audit_{run_id}.json")
    stations = {p.stem.split("_")[1]: _load(p) for p in sorted(diag.glob(f"station_*_{run_id}.json"))}
    verify = _load(Path(verify_root) / run_id / phase / "verify_report.json")
    scoring = _load(diag / f"outcome_scoring_{run_id}.json")
    rates = _load(SETUP_RATES)

    if manifest is None and handoff is None:
        data = _section("NOT_AVAILABLE", reason="no manifest or handoff audit")
    else:
        tech = (manifest or {}).get("pipeline_technical_health")
        fails = int((handoff or {}).get("fail_count") or 0)
        warn = (handoff or {}).get("overall_status") not in (None, "PASS")
        data = _section("FAIL" if tech not in (None, "PASS") or fails else "REVIEW" if warn else "PASS",
                        technical_health=tech, handoff_status=(handoff or {}).get("overall_status"),
                        handoff_fail_count=fails, handoff_warn_count=(handoff or {}).get("warn_count"))

    stop_total = sum(len((s or {}).get("stop_defects") or []) for s in stations.values())
    if verify is None and not stations:
        calc = _section("NOT_AVAILABLE", reason="no verifier report and no station reports")
    else:
        verdict = (verify or {}).get("verdict")
        status = ("FAIL" if stop_total or verdict == "DO_NOT_TRADE" else
                  "REVIEW" if verdict in ("TRUST_WITH_CAVEATS", "UNVERIFIED", None) else "PASS")
        calc = _section(status, verifier_verdict=verdict, verifier_reason=(verify or {}).get("reason"),
                        station_stop_defects=stop_total, stations=sorted(stations))

    if manifest is None:
        structure = _section("NOT_AVAILABLE", reason="no manifest")
    else:
        semantic = manifest.get("pipeline_semantic_health")
        structure = _section("FAIL" if manifest.get("fatal_flags") else "PASS" if semantic == "PASS" else "REVIEW",
                             semantic_health=semantic, semantic_defect_count=manifest.get("semantic_defect_count"),
                             tradeable_label=manifest.get("run_tradeable_label"),
                             fatal_flags=manifest.get("fatal_flags") or [])

    forward = _forward(outcome_store)
    report = forward.pop("forward_report")
    if rates is None:
        calibration = _section("NOT_AVAILABLE", reason="no setup rate table", **forward)
    else:
        cal = rates.get("calibration") or {}
        status = "FAIL" if forward["forward_miscalibrated"] else "REVIEW"
        calibration = _section(status, replay_slope=cal.get("slope"), replay_intercept=cal.get("intercept"),
                               replay_ece=cal.get("ece"), replay_groups=cal.get("groups"), **forward,
                               note="replay calibration measured; forward state per setup from the outcome scorer")

    if scoring is None:
        trading = _section("NOT_AVAILABLE", reason="no outcome scoring for this run")
    else:
        trading = _section("REVIEW", outcome_scoring_status=scoring.get("status"),
                           note="forward trading performance not yet measured on enough resolved outcomes")

    sections = {"data": data, "calculation": calc, "structure": structure, "calibration": calibration,
                "trading_performance": trading}
    overall = max((s["status"] for s in sections.values()), key=lambda s: _RANK[s])
    if all(s["status"] == "NOT_AVAILABLE" for s in sections.values() if s is not calibration):
        overall = "NOT_AVAILABLE"
    return {"run_id": run_id, "phase": phase, "authority": "REPORT_ONLY", "overall": overall, "sections": sections,
            "forward_calibration": report}


def write_scorecard(card: Dict[str, Any], run_dir: Path | str) -> Path:
    path = Path(run_dir) / "diagnostics" / f"scorecard_{card['phase']}_{card['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
    return path
