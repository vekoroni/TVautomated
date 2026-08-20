"""Run EV-1.5 as a governed, non-authoritative pipeline shadow phase.

The phase discovers the Options Intelligence artifact for one canonical run,
publishes input coverage, invokes EV-1, and writes a run-scoped status contract.
It never modifies candidate, GO-list, morning-gate, or execution artifacts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_ev3_shadow import run_shadow  # noqa: E402


EV3_SHADOW_PHASE_VERSION = "ev3-shadow-phase-v0.6.0"
DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"
DEFAULT_BARRIER_CACHE = Path(
    os.environ.get(
        "AVSHUNTER_EV3_BARRIER_CACHE",
        r"C:\Users\ACKVerissimo\vanguard\data\staging\ev3_barrier_outcome_cache.parquet",
    )
)

COVERAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker": ("ticker", "symbol"),
    "direction": ("canonical_direction", "resolved_direction", "options_direction", "direction"),
    "direction_status": ("direction_status", "direction_arbitration_status", "direction_conflict_status"),
    "entry_spot": ("entry_spot", "signal_price", "underlying_price", "current_price"),
    "target_spot": ("target_spot", "target_price", "structural_target", "target_in_play"),
    "invalidation_spot": ("invalidation_spot", "invalidation_price", "invalidation_level"),
    "planned_hold_sessions": ("planned_hold_sessions", "horizon_hold_sessions"),
    "state_key": ("ev3_barrier_state_key", "state_key", "layer2__matched_state_key"),
    "canonical_state_key": ("ev3_barrier_state_key",),
    "contract_symbol": ("contract_occ_symbol", "recommended_contract", "contract_symbol"),
    "quote_timestamp_utc": ("contract_quote_timestamp_utc", "quote_timestamp_utc"),
    "contract_multiplier": ("contract_multiplier", "multiplier"),
}


def _present(series: pd.Series) -> pd.Series:
    if pd.api.types.is_string_dtype(series.dtype) or series.dtype == object:
        return series.notna() & series.astype(str).str.strip().ne("")
    return series.notna()


def _coalesced_presence(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series:
    result = pd.Series(False, index=frame.index, dtype=bool)
    for name in aliases:
        if name in frame.columns:
            result |= _present(frame[name])
    return result


def build_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    """Return stable selected-row handoff coverage without fabricating values."""
    total = int(len(frame))
    selected_mask = _coalesced_presence(frame, COVERAGE_ALIASES["contract_symbol"])
    selected_rows = int(selected_mask.sum()) if total else 0
    fields: dict[str, dict[str, Any]] = {}
    for field, aliases in COVERAGE_ALIASES.items():
        count = int(_coalesced_presence(frame, aliases).sum()) if total else 0
        selected_count = int((_coalesced_presence(frame, aliases) & selected_mask).sum()) if total else 0
        fields[field] = {
            "present": count,
            "missing": total - count,
            "coverage": round(count / total, 6) if total else 0.0,
            "selected_present": selected_count,
            "selected_missing": selected_rows - selected_count,
            "selected_coverage": round(selected_count / selected_rows, 6) if selected_rows else 0.0,
            "aliases_checked": list(aliases),
        }
    complete = selected_mask.copy()
    for aliases in COVERAGE_ALIASES.values():
        complete &= _coalesced_presence(frame, aliases)
    complete_count = int(complete.sum()) if total else 0
    return {
        "rows": total,
        "selected_contract_rows": selected_rows,
        "complete_selected_handoff_rows": complete_count,
        "complete_selected_handoff_coverage": (
            round(complete_count / selected_rows, 6) if selected_rows else 0.0
        ),
        "fields": fields,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _base_status(run_id: str, input_path: Path, barrier_cache: Path) -> dict[str, Any]:
    return {
        "schema_version": EV3_SHADOW_PHASE_VERSION,
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_ONLY",
        "production_authority": False,
        "capital_eligibility_enabled": False,
        "pipeline_blocking": False,
        "technical_health": "NOT_EVALUATED",
        "ev_functional_health": "NOT_RUN",
        "morning_capital_permission": "NOT_EVALUATED_BY_SHADOW",
        "expected_market_rejections": {},
        "expected_contract_rejections": {},
        "unclassified_rejections": {},
        # Coverage health is a statement about EV3's own coverage today --
        # not a verdict on the market, not a trade signal. See run_phase()
        # for the state enumeration and intelligent_orchestrator.py:4947-4948
        # for the "never changes manifest permission" guarantee this must
        # not violate. NO_INPUT is also the correct default for the two
        # early-return branches below (input/barrier-cache missing), since
        # neither ever reaches a rows_received count.
        "ev3_coverage_health": "NO_INPUT",
        "dominant_reason_code": None,
        "dominant_reason_count": None,
        "dominant_reason_share": None,
        "system_defects": {},
        "input_path": str(input_path.resolve()),
        "barrier_cache_path": str(barrier_cache.resolve()),
    }


def run_phase(
    run_id: str,
    *,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    barrier_cache: Path = DEFAULT_BARRIER_CACHE,
    phase: str = "EOD",
    now_utc: str | None = None,
) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    input_path = run_dir / "options" / f"options_intelligence_{run_id}.csv"
    output_dir = run_dir / "ev3_shadow"
    status_path = output_dir / f"ev3_shadow_phase_status_{run_id}.json"
    status = _base_status(run_id, input_path, barrier_cache)
    status.update(
        evaluation_now_utc=now_utc,
        evaluation_clock_mode="FIXED_FUNCTIONAL_TEST" if now_utc else "REALTIME_STRICT",
        functional_test_clock_override=bool(now_utc),
        strict_production_freshness=not bool(now_utc),
    )

    if not input_path.exists() or input_path.stat().st_size == 0:
        status.update(
            health="SKIPPED_INPUT_MISSING",
            technical_health="DEGRADED",
            ev_functional_health="SKIPPED_INPUT_MISSING",
            system_defects={"input_artifact": "OPTIONS_INTELLIGENCE_MISSING_OR_EMPTY"},
            detail="Options Intelligence artifact is missing or empty",
        )
        _atomic_json(status, status_path)
        return status
    if not barrier_cache.exists() or barrier_cache.stat().st_size == 0:
        status.update(
            health="SKIPPED_BARRIER_CACHE_MISSING",
            technical_health="DEGRADED",
            ev_functional_health="SKIPPED_BARRIER_CACHE_MISSING",
            system_defects={"barrier_cache": "MISSING_OR_EMPTY"},
            detail="EV3 barrier cache is missing or empty",
        )
        status["input_sha256"] = _sha256(input_path)
        _atomic_json(status, status_path)
        return status

    frame = pd.read_csv(input_path, low_memory=False)
    status["input_sha256"] = _sha256(input_path)
    status["barrier_cache_sha256"] = _sha256(barrier_cache)
    status["coverage"] = build_coverage(frame)

    audit = run_shadow(
        input_path,
        barrier_cache,
        output_dir,
        phase=phase,
        now_utc=now_utc,
    )
    evaluated = int(audit.get("rows_evaluated", 0))
    received = int(audit.get("rows_received", 0))
    if received == 0:
        health = "DEGRADED_EMPTY_INPUT"
    elif evaluated == 0:
        health = "DEGRADED_NO_EVALUATIONS"
    else:
        health = "SHADOW_COMPLETE"
    reason_counts = audit.get("reason_counts", {})
    expected_rejection_codes = {
        "REJECT_BARRIER_GRID_UNAVAILABLE",
        "REJECT_BARRIER_HORIZON_UNAVAILABLE",
        "REJECT_BARRIER_STATE_UNAVAILABLE",
        "REJECT_DIRECTION_UNRESOLVED",
        "REJECT_DTE",
        "REJECT_DTE_FEASIBILITY",
        "REJECT_LIQUIDITY",
        "REJECT_LIQUIDITY_SPREAD",
        "REJECT_NO_EVALUABLE_CONTRACT",
        "REJECT_QUOTE_STALE",
        "REJECT_RR_ZERO",
        "REJECT_STRUCTURE_UNSUPPORTED",
        "REJECT_UNIT_SPREAD",
    }
    # Row-level classification is a three-way exhaustive partition of every code
    # present in reason_counts: market-expected (below), system/contract (shared
    # with the contract-level classification further down), or unclassified —
    # the genuine complement of both sets, not a third hardcoded list, so a
    # future engine code cannot silently vanish from every row-level field the
    # way REJECT_CONTRACT_SYMBOL previously did. Definition moved earlier (was
    # below expected_contract_rejections) so both levels share one set — same
    # five codes, same meaning, no duplicated literal to drift out of sync.
    system_contract_codes = {
        "REJECT_CONTRACT_MULTIPLIER",
        "REJECT_CONTRACT_SYMBOL",
        "REJECT_QUOTE_TIMESTAMP",
        "REJECT_STATE_KEY",
        "REJECT_TICKER",
    }
    expected_market_rejections = {
        str(code): int(count)
        for code, count in reason_counts.items()
        if str(code) in expected_rejection_codes and int(count or 0) > 0
    }
    row_validation_defects = {
        str(code): int(count)
        for code, count in reason_counts.items()
        if str(code) in system_contract_codes and int(count or 0) > 0
    }
    unclassified_rejections = {
        str(code): int(count)
        for code, count in reason_counts.items()
        if str(code).startswith("REJECT_")
        and str(code) not in expected_rejection_codes
        and str(code) not in system_contract_codes
        and int(count or 0) > 0
    }
    contract_reason_counts = audit.get("contract_evaluation_reason_counts", {})
    expected_contract_rejections = {
        str(code): int(count)
        for code, count in contract_reason_counts.items()
        if str(code).startswith("REJECT_")
        and str(code) not in system_contract_codes
        and int(count or 0) > 0
    }
    coverage = status["coverage"]
    system_defects: dict[str, Any] = {}
    missing_context = {
        field: int(coverage["fields"][field]["missing"])
        for field in ("direction", "direction_status")
        if int(coverage["fields"][field]["missing"]) > 0
    }
    if missing_context:
        system_defects["missing_all_row_context"] = missing_context
    missing_selected = {
        field: int(metrics["selected_missing"])
        for field, metrics in coverage["fields"].items()
        if int(metrics["selected_missing"]) > 0
    }
    if missing_selected:
        system_defects["missing_selected_handoff"] = missing_selected
    if row_validation_defects:
        system_defects["row_validation"] = row_validation_defects
    contract_validation_defects = {
        str(code): int(count)
        for code, count in contract_reason_counts.items()
        if str(code) in system_contract_codes and int(count or 0) > 0
    }
    if contract_validation_defects:
        system_defects["contract_validation"] = contract_validation_defects

    # ev3_coverage_health: a health signal, not an eligibility signal. It
    # reports whether EV3 had anything to say today -- nothing about the
    # market, nothing about any trade. Nothing may branch on this value.
    # ZERO_COVERAGE and NO_INPUT are kept distinct on purpose: the first
    # means EV3 received a full book and rejected all of it (e.g. a Sunday
    # evening run against stale weekend quotes -- see dominant_reason_code
    # below for why, not a calendar check here); the second means nothing
    # reached EV3 at all. Different failures, different owners.
    if received == 0:
        ev3_coverage_health = "NO_INPUT"
    elif evaluated > 0:
        ev3_coverage_health = "EVALUATED"
    else:
        ev3_coverage_health = "ZERO_COVERAGE"

    dominant_reason_code: str | None = None
    dominant_reason_count: int | None = None
    dominant_reason_share: float | None = None
    if ev3_coverage_health in ("ZERO_COVERAGE", "EVALUATED"):
        # Same REJECT_ prefix guard as expected_contract_rejections /
        # unclassified_rejections above -- reason_counts also carries
        # SHADOW_ONLY, the non-rejection success marker, and picking that
        # as a "dominant reason" would be nonsense (Stage 3.1 Check 6).
        rejection_counts = {
            str(code): int(count)
            for code, count in reason_counts.items()
            if str(code).startswith("REJECT_") and int(count or 0) > 0
        }
        if rejection_counts:
            dominant_reason_code = max(rejection_counts, key=rejection_counts.get)
            dominant_reason_count = rejection_counts[dominant_reason_code]
            dominant_reason_share = round(dominant_reason_count / received, 6)

    status.update(
        health=health,
        technical_health="PASS",
        ev_functional_health=health,
        morning_capital_permission="NOT_EVALUATED_BY_SHADOW",
        detail="EV3 remains advisory; no downstream artifact was changed",
        rows_received=received,
        rows_evaluated=evaluated,
        rows_rejected=int(audit.get("rows_rejected", 0)),
        evaluation_coverage=round(evaluated / received, 6) if received else 0.0,
        reason_counts=reason_counts,
        expected_market_rejections=expected_market_rejections,
        expected_contract_rejections=expected_contract_rejections,
        unclassified_rejections=unclassified_rejections,
        ev3_coverage_health=ev3_coverage_health,
        dominant_reason_code=dominant_reason_code,
        dominant_reason_count=dominant_reason_count,
        dominant_reason_share=dominant_reason_share,
        system_defects=system_defects,
        contract_evaluation_reason_counts=contract_reason_counts,
        contract_evaluation_structure_counts=audit.get("contract_evaluation_structure_counts", {}),
        absolute_state_counts=audit.get("absolute_state_counts", {}),
        engine_stage=audit.get("stage", "UNKNOWN"),
        shadow_audit_path=str((output_dir / "ev3_stage1_shadow_audit.json").resolve()),
    )
    _atomic_json(status, status_path)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--barrier-cache", type=Path, default=DEFAULT_BARRIER_CACHE)
    parser.add_argument("--phase", choices=("EOD", "MORNING"), default="EOD")
    parser.add_argument("--now-utc")
    args = parser.parse_args()
    try:
        status = run_phase(
            args.run_id,
            runs_dir=args.runs_dir,
            barrier_cache=args.barrier_cache,
            phase=args.phase,
            now_utc=args.now_utc,
        )
    except Exception as exc:
        run_dir = args.runs_dir / args.run_id / "ev3_shadow"
        status_path = run_dir / f"ev3_shadow_phase_status_{args.run_id}.json"
        status = _base_status(
            args.run_id,
            args.runs_dir / args.run_id / "options" / f"options_intelligence_{args.run_id}.csv",
            args.barrier_cache,
        )
        status.update(
            health="FAILED",
            technical_health="FAILED",
            ev_functional_health="FAILED",
            evaluation_now_utc=args.now_utc,
            evaluation_clock_mode="FIXED_FUNCTIONAL_TEST" if args.now_utc else "REALTIME_STRICT",
            functional_test_clock_override=bool(args.now_utc),
            strict_production_freshness=not bool(args.now_utc),
            system_defects={"phase_exception": f"{type(exc).__name__}: {exc}"},
            detail=f"{type(exc).__name__}: {exc}",
        )
        _atomic_json(status, status_path)
        print(json.dumps(status, indent=2, sort_keys=True))
        return 1
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
