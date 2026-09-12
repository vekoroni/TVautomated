"""Read-only MSI production-cycle readiness assessment.

The evening run is allowed to report PENDING_MORNING_GATE.  Once Morning Gate
has produced an accepted atomic handoff, every critical identity, quote,
freshness and Lab/Interpreter parity check must pass.  This module never calls
a provider and never changes capital authority.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.interpreter_handoff import (  # noqa: E402
    HandoffValidationError,
    validate_handoff_manifest,
)
from msi_runtime import MSIRuntimeFlags, active_flags  # noqa: E402
from tools.msi_reconcile import reconcile_handoff  # noqa: E402


READINESS_SCHEMA_VERSION = "msi_production_readiness_v1"
STRUCTURED_FLAGS = (
    "v2_capture",
    "cds_resolver",
    "minute_bars",
    "structure",
    "lab_v3_view",
    "macro_advisory",
    "interpreter_resolver",
)
REQUIRED_BOOK_FIELDS = {
    "lab_schema_version",
    "run_id",
    "ticker",
    "thesis_id",
    "trade_idea_id",
    "selected_structure_id",
    "selected_contract_symbol",
    "selected_quote_snapshot_id",
    "contract_bid_size",
    "contract_ask_size",
    "contract_size_quality",
    "underlying_nbbo_bid",
    "underlying_nbbo_ask",
    "underlying_nbbo_mid",
    "underlying_nbbo_bid_size",
    "underlying_nbbo_ask_size",
    "morning_contract_bid",
    "morning_contract_ask",
    "morning_contract_mid",
    "current_contract_bid",
    "current_contract_ask",
    "current_contract_mid",
    "contract_bid_change",
    "contract_ask_change",
    "contract_mid_change",
    "contract_spread_change_pp",
    "quote_freshness",
    "comparison_status",
}
COMPARISON_STATES = {
    "SAME_CONTRACT",
    "CONTRACT_CHANGED",
    "BASELINE_MISSING",
    "BASELINE_ZERO",
    "CURRENT_MISSING",
    "STALE",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def assess_run(
    run_id: str,
    *,
    runs_dir: Path | str = REPO_ROOT / "data" / "output" / "runs",
    flags: MSIRuntimeFlags | None = None,
) -> dict[str, Any]:
    selected_flags = flags or active_flags()
    run_root = Path(runs_dir) / run_id
    errors: list[str] = []
    warnings: list[str] = []
    disabled = [name for name in STRUCTURED_FLAGS if not getattr(selected_flags, name)]
    if disabled:
        errors.append("STRUCTURED_FLAGS_DISABLED:" + ",".join(disabled))
    if selected_flags.screen_adapter:
        warnings.append("SCREEN_ADAPTER_ACTIVE_SEPARATE_ACCEPTANCE_REQUIRED")
    if not run_root.is_dir():
        errors.append(f"RUN_DIRECTORY_MISSING:{run_root}")
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "FAIL",
            "errors": errors,
            "warnings": warnings,
            "feature_flags": selected_flags.to_dict(),
        }

    meta_path = run_root / "run_meta.json"
    try:
        run_meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        run_meta = {}
        errors.append("RUN_META_MISSING_OR_INVALID")

    manifest_path = run_root / "interpreter" / "handoff_manifest.json"
    if not manifest_path.is_file():
        morning_exists = any(
            (run_root / "morning_validation").glob("morning_validated_trades_*.csv")
        )
        if morning_exists:
            errors.append("HANDOFF_MISSING_AFTER_MORNING_GATE")
            state = "FAIL"
        else:
            state = "PENDING_MORNING_GATE" if not errors else "FAIL"
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "run_id": run_id,
            "status": state,
            "errors": errors,
            "warnings": warnings,
            "feature_flags": selected_flags.to_dict(),
            "run_meta_status": _text(run_meta.get("run_status")) or "MISSING",
            "handoff_manifest": str(manifest_path),
        }

    try:
        handoff = validate_handoff_manifest(manifest_path)
    except HandoffValidationError as error:
        errors.append(f"HANDOFF_VALIDATION:{error}")
        return {
            "schema_version": READINESS_SCHEMA_VERSION,
            "run_id": run_id,
            "status": "FAIL",
            "errors": errors,
            "warnings": warnings,
            "feature_flags": selected_flags.to_dict(),
            "handoff_manifest": str(manifest_path),
        }

    reconciliation = reconcile_handoff(manifest_path)
    if reconciliation.get("status") != "PASS":
        errors.extend(
            "RECONCILIATION:" + item
            for item in reconciliation.get("mismatches", [])
        )

    rows = [dict(row) for row in handoff.book_rows]
    fields = {field for row in rows for field in row}
    missing_fields = sorted(REQUIRED_BOOK_FIELDS - fields)
    if missing_fields:
        errors.append("LAB_V3_FIELDS_MISSING:" + ",".join(missing_fields))

    invalid_rows: list[str] = []
    for row in rows:
        ticker = _text(row.get("ticker")).upper() or "UNKNOWN"
        if _text(row.get("lab_schema_version")) != "lab_signal_book_v3":
            invalid_rows.append(f"{ticker}:LAB_SCHEMA_NOT_V3")
        comparison = _text(row.get("comparison_status")).upper()
        if comparison not in COMPARISON_STATES:
            invalid_rows.append(f"{ticker}:COMPARISON_STATUS:{comparison or 'MISSING'}")
        if comparison == "CURRENT_MISSING":
            warnings.append(f"{ticker}:EXECUTION_QUOTE_{comparison}")
        freshness = _text(row.get("quote_freshness")).upper()
        if freshness in {"MISSING", "INVALID", ""}:
            warnings.append(
                f"{ticker}:VALIDATION_QUOTE_UNAVAILABLE:{freshness or 'MISSING'}"
            )
        size_quality = _text(row.get("contract_size_quality")).upper()
        if not size_quality:
            warnings.append(f"{ticker}:CONTRACT_SIZE_QUALITY_MISSING")
    errors.extend(invalid_rows)

    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "run_id": run_id,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "feature_flags": selected_flags.to_dict(),
        "run_meta_status": _text(run_meta.get("run_status")) or "MISSING",
        "handoff_manifest": str(handoff.manifest_path),
        "book_rows": len(rows),
        "bundle_rows": len(handoff.bundles),
        "reconciliation": reconciliation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess one MSI production run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default=str(REPO_ROOT / "data" / "output" / "runs"))
    parser.add_argument("--output")
    args = parser.parse_args()
    report = assess_run(args.run_id, runs_dir=args.runs_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["status"] in {"PASS", "PENDING_MORNING_GATE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
