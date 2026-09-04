"""Attach EV3 decisions to Options Intelligence under governed activation gates.

The overlay is always useful as an audit annotation.  It becomes an EV
eligibility authority only when explicitly enabled *and* every readiness gate
passes.  It can never grant final trade permission; downstream structure,
macro, risk, and live-execution controls still apply.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any
import uuid

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ev3_calibration_report import build_report, write_report


SCHEMA_VERSION = "ev3-authority-overlay-v1"
GOVERNED_FINAL_CACHE = Path(r"C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.parquet")
DEFAULT_RUNS_DIR = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs")
DEFAULT_TRADE_JOURNAL = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\journal\trade_journal.db")
DEFAULT_PHANTOM_DB = Path(r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\phantom\phantom_history.db")
SYSTEM_REASON_CODES = {
    "REJECT_CONTRACT_MULTIPLIER",
    "REJECT_CONTRACT_SYMBOL",
    "REJECT_QUOTE_TIMESTAMP",
    "REJECT_STATE_KEY",
    "REJECT_TICKER",
}


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(f".{path.stem}.{uuid.uuid4().hex}.tmp{path.suffix}")
    try:
        frame.to_csv(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def activation_reasons(
    status: dict[str, Any],
    results: pd.DataFrame,
    input_rows: int,
    *,
    governed_final_cache: Path = GOVERNED_FINAL_CACHE,
) -> list[str]:
    reasons: list[str] = []
    if status.get("technical_health") != "PASS":
        reasons.append("TECHNICAL_HEALTH_NOT_PASS")
    if status.get("health") not in {"PRODUCTION_EVIDENCE_COMPLETE", "SHADOW_COMPLETE"}:
        reasons.append("FUNCTIONAL_HEALTH_NOT_COMPLETE")
    if status.get("evaluation_clock_mode") != "REALTIME_STRICT":
        reasons.append("FUNCTIONAL_TEST_CLOCK_FORBIDDEN")
    if dict(status.get("system_defects", {}) or {}):
        reasons.append("SYSTEM_DEFECTS_PRESENT")
    if dict(status.get("unclassified_rejections", {}) or {}):
        reasons.append("UNCLASSIFIED_REJECTIONS_PRESENT")
    if float(status.get("adjudication_coverage", 0.0) or 0.0) < 0.95:
        reasons.append("ADJUDICATION_COVERAGE_BELOW_95_PERCENT")
    cache_value = status.get("barrier_cache_path")
    if not cache_value or Path(str(cache_value)).resolve() != governed_final_cache.resolve():
        reasons.append("BARRIER_CACHE_NOT_GOVERNED_FINAL")
    if len(results) != input_rows:
        reasons.append("RESULT_ROW_COUNT_MISMATCH")
    if "source_row_index" not in results.columns:
        reasons.append("SOURCE_ROW_INDEX_MISSING")
    else:
        source_index = pd.to_numeric(results["source_row_index"], errors="coerce")
        if source_index.isna().any() or source_index.duplicated().any():
            reasons.append("SOURCE_ROW_INDEX_INVALID")
        elif not source_index.between(0, max(input_rows - 1, 0)).all():
            reasons.append("SOURCE_ROW_INDEX_OUT_OF_RANGE")
    return reasons


def authority_state(row: dict[str, Any]) -> str:
    status = str(row.get("ev3_status", "")).upper()
    absolute = str(row.get("ev3_absolute_state", "")).upper()
    reason = str(row.get("ev3_reason_code", "")).upper()
    if status in {"EVALUATED_PRODUCTION_EVIDENCE", "EVALUATED_SHADOW"}:
        return {
            "POSITIVE_UNVALIDATED": "POSITIVE",
            "INDETERMINATE": "INDETERMINATE",
            "NEGATIVE_EV": "NEGATIVE",
        }.get(absolute, "NOT_EVALUATED_DATA_DEFECT")
    if status == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if status == "REJECTED":
        return (
            "NOT_EVALUATED_DATA_DEFECT"
            if reason in SYSTEM_REASON_CODES
            else "NOT_EVALUATED_MARKET_CONSTRAINT"
        )
    return "NOT_EVALUATED_DATA_DEFECT"


def _permission(state: str, authority_active: bool) -> str:
    if not authority_active:
        return "ADVISORY_ONLY"
    return {
        "POSITIVE": "ELIGIBLE_EV_COMPONENT",
        "INDETERMINATE": "NO_GO_EV_INDETERMINATE",
        "NEGATIVE": "NO_GO_EV_NEGATIVE",
        "NOT_EVALUATED_DATA_DEFECT": "BLOCK_DATA",
        "NOT_EVALUATED_MARKET_CONSTRAINT": "NO_GO_CONTRACT_CONSTRAINT",
        "NOT_APPLICABLE": "ALTERNATIVE_MODEL_REQUIRED",
    }[state]


def apply_overlay(
    input_path: Path,
    results_path: Path,
    status_path: Path,
    output_path: Path,
    *,
    authority_requested: bool = False,
    governed_final_cache: Path = GOVERNED_FINAL_CACHE,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    trade_journal: Path = DEFAULT_TRADE_JOURNAL,
    phantom_db: Path = DEFAULT_PHANTOM_DB,
) -> dict[str, Any]:
    options = pd.read_csv(input_path, low_memory=False)
    results = pd.read_parquet(results_path)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    readiness_reasons = activation_reasons(
        status, results, len(options), governed_final_cache=governed_final_cache,
    )
    # EV authority is retired. Keep readiness diagnostics and all computed EV
    # fields, but never convert them into capital permission.
    authority_active = False
    mode = "PRODUCTION_EVIDENCE_ADVISORY"
    reasons = list(readiness_reasons)
    if authority_requested:
        reasons.insert(0, "EV_AUTHORITY_RETIRED_ADVISORY_ONLY")

    if "source_row_index" not in results.columns:
        raise ValueError("EV3 results have no source_row_index")
    indexed = results.copy()
    indexed["source_row_index"] = pd.to_numeric(indexed["source_row_index"], errors="raise").astype(int)
    if indexed["source_row_index"].duplicated().any():
        raise ValueError("EV3 results contain duplicate source_row_index values")
    indexed = indexed.set_index("source_row_index")
    transferable = [column for column in indexed.columns if column.startswith("ev3_")]
    authority_columns = {
        "ev3_authority_schema_version", "ev3_authority_mode",
        "ev3_authority_active", "ev3_authority_state",
        "ev3_monetisation_permission", "ev3_ev_eligible",
        "ev3_authority_reason",
    }
    # Idempotent re-application: refresh prior result/authority columns while
    # preserving upstream ev3_handoff and barrier-state contract fields.
    options = options.drop(
        columns=[column for column in set(transferable) | authority_columns if column in options.columns],
        errors="ignore",
    )
    overlay = indexed[transferable].reindex(options.index).copy()
    states = [authority_state(indexed.loc[index].to_dict()) for index in options.index]
    overlay["ev3_authority_schema_version"] = SCHEMA_VERSION
    overlay["ev3_authority_mode"] = mode
    overlay["ev3_authority_active"] = authority_active
    overlay["ev3_authority_state"] = states
    overlay["ev3_monetisation_permission"] = [
        _permission(state, authority_active) for state in states
    ]
    overlay["ev3_ev_eligible"] = [
        bool(authority_active and state == "POSITIVE") for state in states
    ]
    overlay["ev3_authority_reason"] = (
        "|".join(reasons) if authority_requested
        else "EV_AUTHORITY_RETIRED_ADVISORY_ONLY"
    )

    options = pd.concat([options, overlay], axis=1).copy()
    backup = input_path.with_name(f"{input_path.stem}_pre_ev3_authority{input_path.suffix}")
    if input_path.resolve() == output_path.resolve() and not backup.exists():
        shutil.copy2(input_path, backup)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_csv(options, output_path)
    overlay_path = status_path.parent / "ev3_authority_overlay.csv"
    _atomic_csv(overlay.reset_index(names="source_row_index"), overlay_path)

    calibration_path = status_path.parent / "ev3_calibration_readiness.json"
    try:
        calibration = build_report(runs_dir, trade_journal, phantom_db)
        write_report(calibration, calibration_path)
    except Exception as exc:
        calibration = {
            "status": "REPORT_FAILED",
            "capital_authority_calibrated": False,
            "activation_reasons": [f"{type(exc).__name__}:{exc}"],
        }
    status.update(
        authority_requested=bool(authority_requested),
        production_authority=authority_active,
        ev_component_authority_enabled=authority_active,
        authority_activation_reasons=reasons,
        authority_mode=mode,
        authority_overlay_path=str(overlay_path.resolve()),
        authority_output_path=str(output_path.resolve()),
        production_evidence=True,
        calibration_status=calibration["status"],
        capital_authority_calibrated=bool(calibration["capital_authority_calibrated"]),
        calibration_report_path=str(calibration_path.resolve()),
        authority_positive_rows=int(sum(state == "POSITIVE" for state in states)),
        authority_blocked_rows=int(sum(state in {"NEGATIVE", "INDETERMINATE"} for state in states)),
        detail=(
            "EV3 production evidence attached downstream; EV cannot grant or deny capital"
        ),
    )
    _atomic_json(status, status_path)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument(
        "--enable-authority",
        action="store_true",
        help="Deprecated compatibility flag; EV remains advisory only.",
    )
    args = parser.parse_args()
    run_dir = args.runs_dir / args.run_id
    options = run_dir / "options" / f"options_intelligence_{args.run_id}.csv"
    ev3_dir = run_dir / "ev3_shadow"
    status = apply_overlay(
        options,
        ev3_dir / "ev3_stage1_shadow_results.parquet",
        ev3_dir / f"ev3_shadow_phase_status_{args.run_id}.json",
        options,
        authority_requested=args.enable_authority,
    )
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
