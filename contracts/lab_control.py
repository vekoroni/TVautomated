"""Final control helpers for the AVSHUNTER Intelligence Lab.

This module is deliberately small and deterministic. It does not create
signals; it validates and normalises the committed pipeline baton for the
human execution cockpit.
"""

from __future__ import annotations

import csv
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


LAB_REQUIRED_FIELDS = [
    "lab_verdict",
    "lab_tradeable",
    "lab_execution_status",
    "display_execution_category",
    "display_eod_candidate_status",
    "display_morning_execution_permission",
    "display_morning_execution_route",
    "display_options_research_route",
    "eod_candidate_status",
    "morning_execution_permission",
    "morning_execution_route",
    "options_research_permission",
    "options_research_route",
    "options_research_score",
    "conflict_state",
    "conflict_flags",
    "veto_flags",
    "execution_lock_reason",
    "requires_live_validation",
    "morning_lab_alignment_status",
    "morning_lab_alignment_reason",
    "source_verdicts_json",
]

FINAL_BOOK_FIELDS = [
    "run_id",
    "ticker",
    "trade_idea_id",
    "lab_rank",
    "lab_verdict",
    "lab_tradeable",
    "prep_permission",
    "lab_status",
    "lab_execution_status",
    "execution_category",
    "display_execution_mode",
    "position_size_display",
    "lab_coherence_status",
    "lab_coherence_flags",
    "canonical_direction",
    "morning_execution_permission",
    "morning_execution_route",
    "morning_execution_lane",
    "morning_entry_action",
    "morning_unlock_condition",
    "morning_lab_alignment_status",
    "morning_lab_alignment_reason",
    "conflict_state",
    "conflict_flags",
    "execution_lock_reason",
    "requires_live_validation",
    "direction",
    "instrument",
    "contract_symbol",
    "morning_selected_contract_symbol",
    "contract_repair_status",
    "contract_repair_required",
    "contract_repair_reason",
    "contract_repair_action",
    "contract_repair_live_action",
    "contract_repair_alternative_used",
    "alternative_contract_attempts",
    "alternative_contract_1",
    "alternative_contract_2",
    "alternative_contract_3",
    "strike",
    "expiry",
    "dte",
    "premium_mid",
    "spread_pct",
    "liquidity_score",
    "priority_score",
    "rr_predicted",
    "ev_predicted",
    "win_prob_predicted",
    "actuarial_match_method",
    "actuarial_match_type",
    "actuarial_ev_weight",
    "behaviour_state_key",
    "behaviour_state_hash",
    "catalyst_overlay",
    "actuarial_sample_size",
    "actuarial_confidence",
    "physics_state_id",
    "hidden_state_label",
    "state_transition_label",
    "market_energy_score",
    "compression_energy",
    "directional_force",
    "force_alignment_score",
    "trend_inertia",
    "entropy_score",
    "phase_transition_probability",
    "liquidity_friction_score",
    "macro_regime",
    "sector_tilt",
    "regime_drift_status",
    "eil_signal_verdict",
    "eil_v3_verdict",
    "eil_composite_eod",
    "entry_plan",
    "invalidation_price",
    "target_price",
    "target_in_play",
    "structural_target",
    "underlying_price",
    "signal_price",
    "scanner_price",
    "target_zone",
    "runway_to_target",
    "runway_to_wall_pct",
    "breakeven_price",
    "breakeven_pct",
    "breakeven_feasibility",
    "option_gain_at_target",
    "layer2__raw_prob_target_hit",
    "layer2__adjusted_prob_target_hit",
    "layer2__raw_expected_time_to_target",
    "layer2__outcomes__median_days_to_target",
    "contract_delta",
    "contract_gamma",
    "contract_theta",
    "contract_iv",
    "contract_bid",
    "contract_ask",
    "contract_mid",
    "contract_oi",
    "contract_volume",
    "call_wall",
    "put_wall",
    "gamma_flip",
    "max_pain",
    "pcr_signal",
    "gamma_island_on_path",
    "gamma_island_level",
    "gamma_island_distance_pct",
    "wbs",
    "wbs_grade",
    "wbs_wall_price",
    "wbs_wall_dist_pct",
    "wbs_f5_momentum",
    "wbs_phase_b_trigger",
    "wbs_phase_c_trigger",
    "wbs_entry_guidance",
    "wbs_size_guidance",
    "wbs_wall_stall_rule",
    "wbs_notes",
    "ts_expiry_date",
    "ts_dte_remaining_at_stop",
    "ts_checkpoint_date",
    "ts_checkpoint_rule",
    "ts_dte_used",
    "hold_urgency",
    "scenario_dte_target",
    "hold_window",
    "time_horizon",
    "hold_period",
    "trigger_price",
    "trigger_evidence",
    "trigger_primary",
    "trigger_quality",
    "trigger_score",
    "trigger_codes",
    "pcr_vol_status",
    "pcr_vol_missing_reason",
    "direction_conflict_status",
    "direction_conflict_reason",
    "notes",
    "source_payload_json",
]

# Compact shared handoff consumed by both Intelligence Lab and Pipeline Interpreter.
# It intentionally excludes source_payload_json, which makes final_opportunity_book
# large and unsuitable as an interactive triage source.
LAB_TRIAGE_VIEW_FIELDS = [field for field in FINAL_BOOK_FIELDS if field != "source_payload_json"]

PHASE_REQUIRED_COLUMNS = {
    "discovery": ["ticker"],
    "vanguard": ["ticker"],
    "physics": ["physics_state_id", "state_transition_label"],
    "macro": ["macro_regime_label", "macro_freshness_status"],
    "options": ["ticker"],
    "eil": ["ticker", "eil_v3_verdict"],
    "execution": ["ticker"],
    "v5": ["ticker"],
    "morning_validation": ["ticker"],
}

GO_EXECUTION_STATES = {
    "BUY_NOW",
    "FULL_EXECUTE",
    "LIVE_EXECUTE",
    "EXECUTE",
    "READY_EXECUTE",
    "EXECUTE_NOW",
    "GO_LIMIT",
    "PROBE",
}

EOD_EXECUTION_STATES = {
    "EOD_EXECUTE_CANDIDATE",
    "EOD_CATALYST_EXECUTE_CANDIDATE",
}

EOD_CAUTION_STATES = {
    "EOD_EXECUTE_WITH_CAUTION",
    "EOD_PROBE_CANDIDATE",
    "EOD_THESIS_READY",
    "EOD_THESIS_READY_REPAIR_AT_OPEN",
    "EOD_TRIGGER_READY",
    "EOD_WATCHLIST_MONETISABLE",
    "EOD_DATA_INSUFFICIENT_REVIEW",
}

SOFT_EXECUTION_STATES = {"WAIT_RETEST", "ARMED", "WATCHLIST", "READY_PROBE", "PROBE", "GO_LIMIT", "CONTRACT_REPAIR", "FLAG", "MANUAL_REVIEW"}

HARD_EXECUTION_STATES = {
    "BLOCKED",
    "SELL_NOW",
    "NO_TRADE",
    "INVALID",
    "STAND_DOWN",
    "FATAL_BLOCK",
    "REJECT",
    "SKIP",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _u(value: Any) -> str:
    return _s(value).upper()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        text = _s(value).replace("%", "")
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def _is_missing(value: Any) -> bool:
    text = _u(value)
    return text in {"", "NONE", "UNKNOWN", "MISSING", "N/A", "NA", "NAN", "NULL"}


def _json_safe(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    except Exception:
        return json.dumps(str(value), ensure_ascii=True)


def first(sig: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = sig.get(key)
        if not _is_missing(value):
            return value
    return default


def _trigger_price(sig: Dict[str, Any]) -> Any:
    return first(
        sig,
        "trigger_price",
        "entry_trigger_price",
        "trade_trigger_price",
        "scenario_entry_trigger",
        "eod__scenario_entry_trigger",
        "vg__scenario_entry_trigger",
        "wbs_phase_b_trigger",
        "eod__wbs_phase_b_trigger",
        "vg__wbs_phase_b_trigger",
        "wbs_phase_c_trigger",
        "eod__wbs_phase_c_trigger",
        "vg__wbs_phase_c_trigger",
    )


def _trigger_evidence(sig: Dict[str, Any]) -> Any:
    primary = first(sig, "trigger_primary", "trigger_codes")
    quality = first(sig, "trigger_quality")
    score = first(sig, "trigger_score", "trigger_count")
    parts = []
    if not _is_missing(primary):
        parts.append(_s(primary))
    if not _is_missing(quality) and _u(quality) not in {"0", "0.0", "0.00", "FALSE", "NO"}:
        parts.append(_s(quality))
    if not _is_missing(score) and _f(score) > 0:
        parts.append(_s(score))
    return " ".join(parts)


def _side_from_value(value: Any) -> str:
    text = _u(value).replace("-", "_").replace(" ", "_")
    if not text:
        return ""
    if "LONG_CALL" in text or text in {"CALL", "CALLS", "BULL", "BULLISH", "UP", "BUY"}:
        return "CALL"
    if "LONG_PUT" in text or text in {"PUT", "PUTS", "BEAR", "BEARISH", "DOWN", "SELL", "SHORT"}:
        return "PUT"
    if text.endswith("_CALL") or "_CALL_" in text:
        return "CALL"
    if text.endswith("_PUT") or "_PUT_" in text:
        return "PUT"
    return ""


def _instrument_for_direction(direction: Any, current: Any = "") -> str:
    side = _side_from_value(direction)
    current_text = _u(current).replace("-", "_").replace(" ", "_")
    if side not in {"CALL", "PUT"}:
        return _s(current)
    opposite = "PUT" if side == "CALL" else "CALL"
    if not current_text:
        return f"LONG_{side}"
    if "DEBIT_SPREAD" in current_text:
        return current_text.replace(opposite, side)
    if "CREDIT_SPREAD" in current_text:
        return current_text.replace(opposite, side)
    if "VERTICAL" in current_text:
        return current_text.replace(opposite, side)
    if "LONG_" in current_text or current_text in {"CALL", "PUT"} or opposite in current_text:
        return f"LONG_{side}"
    return f"LONG_{side}"


def _contract_side_from_symbol(symbol: Any) -> str:
    text = _u(symbol)
    match = re.search(r"\d{6}([CP])\d{8}", text)
    if not match:
        return ""
    return "CALL" if match.group(1) == "C" else "PUT"


def _contract_for_direction(sig: Dict[str, Any], direction: Any) -> tuple[str, str]:
    side = _side_from_value(direction)
    keys = (
        "morning_selected_contract_symbol",
        "live_selected_contract_symbol",
        "contract_symbol",
        "live_contract_symbol",
        "alternative_contract_1",
        "alternative_contract_2",
        "alternative_contract_3",
        "option_symbol",
        "recommended_contract",
        "preferred_contract",
        "evening_contract_symbol",
        "opt__recommended_contract",
    )
    original = _s(first(sig, *keys))
    if side not in {"CALL", "PUT"}:
        return original, ""
    for key in keys:
        candidate = _s(sig.get(key))
        if candidate and _contract_side_from_symbol(candidate) == side:
            if original and candidate != original:
                return candidate, f"CONTRACT_RESELECTED_FOR_DIRECTION:{original}->{candidate}"
            return candidate, ""
    original_side = _contract_side_from_symbol(original)
    if original and original_side and original_side != side:
        return original, f"CONTRACT_SYMBOL_SIDE_CONFLICT:{original_side}->{side}"
    return original, ""


def _append_flag(existing: Any, flag: str) -> str:
    parts = [p for p in _s(existing).split("|") if p]
    if flag and flag not in parts:
        parts.append(flag)
    return "|".join(parts)


def csv_safe_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (dict, list, tuple)):
            out[key] = _json_safe(value)
        else:
            out[key] = value
    return out


def _read_csv_rows(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path or not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _glob_latest(folder: Path, pattern: str) -> Optional[Path]:
    matches = list(folder.glob(pattern)) if folder.exists() else []
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def _output_files(run_dir: Path, run_id: str) -> Dict[str, str]:
    superbrain = run_dir / "superbrain"
    options = run_dir / "options"
    vanguard = run_dir / "vanguard"
    discovery = run_dir / "discovery"
    morning = run_dir / "morning_validation"
    core = run_dir / "core_intel"
    macro = run_dir / "macro"
    diagnostics = run_dir / "diagnostics"
    morning_validated = _glob_latest(morning, f"morning_validated_trades_{run_id}.csv")
    morning_candidates = _glob_latest(morning, f"morning_candidates_{run_id}.csv")
    morning_packet = _glob_latest(morning, f"morning_validation_packet_{run_id}.json")
    return {
        "discovery": str(
            _glob_latest(discovery, f"*discovery*{run_id}*.csv")
            or _glob_latest(run_dir, f"*discovery*{run_id}*.csv")
            or ""
        ),
        "vanguard": str(
            _glob_latest(options, f"vanguard_signals_enriched_{run_id}.csv")
            or _glob_latest(vanguard, "*.csv")
            or ""
        ),
        "eil": str(_glob_latest(superbrain, f"eil_enriched_{run_id}.csv") or ""),
        "execution": str(
            _glob_latest(run_dir / "execution", f"execution_v3_5_{run_id}.csv")
            or _glob_latest(superbrain, f"execution_v3_5_{run_id}.csv")
            or ""
        ),
        "options": str(_glob_latest(options, f"options_intelligence_{run_id}.csv") or ""),
        "v5": str(_glob_latest(superbrain, "AVSHUNTER_SIGNALS_V5_*.csv") or ""),
        "morning_validation": str(morning_validated or ""),
        "morning_candidates": str(morning_candidates or ""),
        "morning_validation_packet": str(morning_packet or ""),
        "core_intel": str(_glob_latest(core, f"core_intel_dossiers_{run_id}.json") or ""),
        "summary": str(_glob_latest(superbrain, "superbrain_summary_*.json") or ""),
        "dropoff_audit": str(_glob_latest(diagnostics, f"dropoff_audit_{run_id}.csv") or ""),
        "handoff_contract_audit": str(_glob_latest(diagnostics, f"handoff_contract_audit_{run_id}.csv") or ""),
        "macro": str(
            _glob_latest(macro, "*.json")
            or _glob_latest(run_dir, "*macro*.json")
            or ""
        ),
    }


def _phase_status(
    phase: str,
    output_files: Dict[str, str],
    required_columns_present: Dict[str, bool],
    row_counts: Dict[str, int],
    pipeline_mode: str,
) -> str:
    if phase == "morning_validation" and not output_files.get(phase):
        if pipeline_mode == "EOD" and output_files.get("morning_candidates"):
            return "PENDING"
        if pipeline_mode in {"EOD", "LIVE_EOD", "INTRADAY_EOD"}:
            return "NOT_REQUIRED"
        return "MISSING"
    if phase == "physics":
        if not output_files.get("vanguard") and not output_files.get("eil"):
            return "MISSING"
        return "PASS" if required_columns_present.get(phase) else "WARN"
    if phase == "macro":
        if output_files.get("macro"):
            return "PASS"
        return "PASS" if required_columns_present.get(phase) else "WARN"
    if not output_files.get(phase):
        return "MISSING"
    if row_counts.get(phase, 0) == 0:
        return "WARN"
    return "PASS" if required_columns_present.get(phase, True) else "FAIL"


def build_final_run_manifest(
    run_id: str,
    runs_dir: Path | str,
    pipeline_mode: str = "EOD",
) -> Dict[str, Any]:
    runs_dir = Path(runs_dir)
    run_dir = runs_dir / run_id
    mode = _u(pipeline_mode) or "UNKNOWN"
    output_files = _output_files(run_dir, run_id)
    rows_by_phase: Dict[str, List[Dict[str, Any]]] = {
        "discovery": _read_csv_rows(Path(output_files["discovery"])) if output_files.get("discovery") else [],
        "vanguard": _read_csv_rows(Path(output_files["vanguard"])) if output_files.get("vanguard") else [],
        "eil": _read_csv_rows(Path(output_files["eil"])) if output_files.get("eil") else [],
        "execution": _read_csv_rows(Path(output_files["execution"])) if output_files.get("execution") else [],
        "options": _read_csv_rows(Path(output_files["options"])) if output_files.get("options") else [],
        "v5": _read_csv_rows(Path(output_files["v5"])) if output_files.get("v5") else [],
        "morning_validation": _read_csv_rows(Path(output_files["morning_validation"])) if output_files.get("morning_validation") else [],
    }
    macro_payload = _read_json(Path(output_files["macro"])) if output_files.get("macro") else {}
    ev3_status_path = run_dir / "ev3_shadow" / f"ev3_shadow_phase_status_{run_id}.json"
    ev3_status = _read_json(ev3_status_path) if ev3_status_path.exists() else {}

    row_counts = {phase: len(rows) for phase, rows in rows_by_phase.items()}
    required_columns_present: Dict[str, bool] = {}
    missing_columns: Dict[str, List[str]] = {}

    for phase, required in PHASE_REQUIRED_COLUMNS.items():
        if phase == "macro":
            sample = macro_payload or (rows_by_phase["eil"][0] if rows_by_phase["eil"] else {})
        elif phase == "physics":
            sample = (
                rows_by_phase["vanguard"][0]
                if rows_by_phase["vanguard"]
                else rows_by_phase["eil"][0]
                if rows_by_phase["eil"]
                else {}
            )
        else:
            sample = rows_by_phase.get(phase, [{}])[0] if rows_by_phase.get(phase) else {}
        missing = [col for col in required if col not in sample]
        missing_columns[phase] = missing
        required_columns_present[phase] = not missing

    phase_status: Dict[str, str] = {
        phase: _phase_status(phase, output_files, required_columns_present, row_counts, mode)
        for phase in [
            "discovery",
            "vanguard",
            "physics",
            "macro",
            "options",
            "eil",
            "execution",
            "morning_validation",
        ]
    }

    stale_flags: List[str] = []
    conflict_flags: List[str] = []
    fatal_flags: List[str] = []

    if phase_status["eil"] in {"MISSING", "FAIL"}:
        fatal_flags.append("EIL_OUTPUT_MISSING_OR_INVALID")
    if phase_status["options"] == "MISSING":
        stale_flags.append("OPTIONS_OUTPUT_MISSING_EXECUTION_DOWNGRADED")
    if mode == "EOD" and row_counts.get("eil", 0) > 0 and not output_files.get("morning_candidates"):
        fatal_flags.append("EOD_CANDIDATE_MANIFEST_MISSING")
    morning_validation_pending = (
        mode == "EOD"
        and phase_status["morning_validation"] in {"PENDING", "NOT_REQUIRED"}
        and bool(output_files.get("morning_candidates"))
    )
    if morning_validation_pending:
        stale_flags.append("EOD_MORNING_VALIDATION_PENDING")
    morning_validation_paper = any(
        _u(row.get("live_data_mode")) in {"PAPER", "SIMULATED", "REPLAY"}
        for row in rows_by_phase["morning_validation"]
    )
    if morning_validation_paper:
        stale_flags.append("MORNING_VALIDATION_PAPER_MODE")
    if mode in {"LIVE", "MORNING_VALIDATION"} and phase_status["morning_validation"] in {"MISSING", "FAIL"}:
        fatal_flags.append("LIVE_VALIDATION_MISSING")

    eil_rows = rows_by_phase["eil"]
    for row in eil_rows:
        if _u(row.get("eil_v3_verdict")) == "BLOCKED" and _u(row.get("thesis_decision")) == "GO":
            conflict_flags.append(f"EIL_BLOCKED_GO:{row.get('ticker', '')}")
        if _u(row.get("pse_execution_mode")) == "FATAL_BLOCK" and _u(row.get("execution_mode")) in {
            "FULL_EXECUTE",
            "REDUCED_EXECUTE",
            "LIVE_EXECUTE",
        }:
            conflict_flags.append(f"PSE_FATAL_EXEC:{row.get('ticker', '')}")
        if row.get("trigger_primary") in (None, "", "NONE") and _u(row.get("execution_mode")) in {
            "FULL_EXECUTE",
            "LIVE_EXECUTE",
        }:
            conflict_flags.append(f"MISSING_TRIGGER_EXEC:{row.get('ticker', '')}")

    if conflict_flags:
        fatal_flags.append("HARD_CONTRADICTIONS_PRESENT")

    health = 100
    health -= 30 * len(fatal_flags)
    health -= 8 * sum(1 for status in phase_status.values() if status == "MISSING")
    health -= 5 * sum(1 for status in phase_status.values() if status == "WARN")
    health -= 3 * len(stale_flags)
    health = max(0, min(100, health))

    run_tradeable = (
        not fatal_flags
        and not morning_validation_pending
        and not morning_validation_paper
        and phase_status["eil"] == "PASS"
        and row_counts.get("eil", 0) > 0
    )
    if fatal_flags:
        next_action = "BLOCKED_REPAIR_REQUIRED"
    elif row_counts.get("eil", 0) == 0:
        next_action = "NO_CANDIDATES"
    elif mode == "EOD" and "EOD_MORNING_VALIDATION_PENDING" in stale_flags:
        next_action = "NEEDS_MORNING_VALIDATION"
    elif "MORNING_VALIDATION_PAPER_MODE" in stale_flags:
        next_action = "NEEDS_LIVE_UAT"
    else:
        next_action = "READY_FOR_LAB"

    # EOD prep is intentionally not execution-tradeable until live morning
    # validation runs. It is, however, reviewable and should feed the Pipeline
    # Interpreter for battlefield preparation.
    run_execution_permission = "READY_FOR_LAB" if run_tradeable else "BLOCKED_REPAIR_REQUIRED"
    run_prep_permission = "NONE"
    run_tradeable_label = "EXECUTION_READY" if run_tradeable else "NOT_EXECUTION_READY"
    manual_review_enabled = False
    pipeline_interpreter_prep_enabled = False
    if next_action == "NEEDS_MORNING_VALIDATION":
        run_execution_permission = "MORNING_VALIDATION_REQUIRED"
        run_prep_permission = "MANUAL_REVIEW_MORNING_VALIDATION"
        run_tradeable_label = "MANUAL_REVIEW_MORNING_VALIDATION"
        manual_review_enabled = True
        pipeline_interpreter_prep_enabled = True
    elif next_action == "NEEDS_LIVE_UAT":
        run_execution_permission = "LIVE_UAT_REQUIRED"
        run_prep_permission = "REVIEW_ONLY"
        run_tradeable_label = "LIVE_UAT_REQUIRED"
        manual_review_enabled = True

    if fatal_flags:
        pipeline_technical_health = "FAILED"
    elif any(status in {"MISSING", "FAIL", "WARN"} for status in phase_status.values()):
        pipeline_technical_health = "DEGRADED"
    else:
        pipeline_technical_health = "PASS"

    return {
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "pipeline_mode": mode,
        "phase_status": phase_status,
        "output_files": output_files,
        "row_counts": row_counts,
        "required_columns_present": required_columns_present,
        "missing_columns": missing_columns,
        "stale_flags": stale_flags,
        "conflict_flags": conflict_flags,
        "fatal_flags": fatal_flags,
        "run_tradeable": run_tradeable,
        "run_tradeable_label": run_tradeable_label,
        "run_execution_permission": run_execution_permission,
        "run_prep_permission": run_prep_permission,
        "manual_review_enabled": manual_review_enabled,
        "pipeline_interpreter_prep_enabled": pipeline_interpreter_prep_enabled,
        "run_health_score": health,
        "next_action": next_action,
        # Separate operational readiness dimensions. Expected market rejects
        # are not system faults and EV shadow health cannot grant capital use.
        "pipeline_technical_health": pipeline_technical_health,
        "ev_functional_health": str(ev3_status.get("ev_functional_health", "NOT_RUN")),
        "morning_capital_permission": run_execution_permission,
        "expected_market_rejections": dict(
            ev3_status.get("expected_market_rejections", {}) or {}
        ),
        "expected_contract_rejections": dict(
            ev3_status.get("expected_contract_rejections", {}) or {}
        ),
        "system_defects": dict(ev3_status.get("system_defects", {}) or {}),
        "ev3_production_authority": False,
    }


def write_final_run_manifest(
    run_id: str,
    runs_dir: Path | str,
    pipeline_mode: str = "EOD",
) -> Dict[str, Any]:
    manifest = build_final_run_manifest(run_id, runs_dir, pipeline_mode)
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / "final_run_manifest.json"
    target.write_text(_json_safe(manifest), encoding="utf-8")
    return manifest


def load_final_run_manifest(run_id: str, runs_dir: Path | str) -> Dict[str, Any]:
    path = Path(runs_dir) / run_id / "final_run_manifest.json"
    return _read_json(path)


def duplicate_open_trade(sig: Dict[str, Any], open_trades: Optional[Iterable[Dict[str, Any]]]) -> bool:
    if not open_trades:
        return False
    ticker = _u(sig.get("ticker"))
    direction = _u(first(sig, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "selected_contract_side", "option_direction"))
    strike = _s(first(sig, "strike", "contract_strike", "opt__contract_strike"))
    expiry = _s(first(sig, "expiry", "contract_expiry", "opt__contract_expiry"))
    for row in open_trades:
        if _u(row.get("ticker")) != ticker:
            continue
        row_dir = _u(first(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "selected_contract_side", "option_direction"))
        row_strike = _s(first(row, "strike", "contract_strike"))
        row_expiry = _s(first(row, "expiry", "contract_expiry"))
        if row_dir == direction and row_strike == strike and row_expiry == expiry:
            return True
    return False


def _morning_lab_alignment(
    permission: str,
    live_state: str,
    verdict: str,
    conflict_state: str,
    veto_flags: Iterable[str],
    soft_flags: Iterable[str],
) -> tuple[str, str]:
    perm = _u(permission)
    state = _u(live_state)
    lab = _u(verdict)
    conflict = _u(conflict_state)
    veto = [str(item) for item in veto_flags or []]
    soft = [str(item) for item in soft_flags or []]

    if not perm:
        return "NO_MORNING_BATON", "No Morning Validator execution permission was supplied."
    if perm not in {"GO", "GO_LIMIT", "PROBE", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"}:
        return "NO_MORNING_BATON", f"Execution permission={perm} is not a Morning Validator permission."

    if conflict == "HARD_CONFLICT" or veto:
        if lab == "BLOCKED":
            return "ALIGNED_BLOCKED", f"Morning permission={perm}, lab blocked by hard gate."
        return "CONFLICT", f"Hard gate present but Lab verdict={lab}."

    expected = {
        "GO": {"GO"},
        "GO_LIMIT": {"GO_LIMIT"},
        "PROBE": {"PROBE"},
        "CONTRACT_REPAIR": {"CONTRACT_REPAIR"},
        "ARMED": {"ARMED"},
        "WAIT": {"WAIT"},
        "BLOCKED": {"BLOCKED"},
    }
    if perm == "BLOCKED" or state in {"REJECTED", "BLOCKED"}:
        expected_values = {"BLOCKED"}
    else:
        expected_values = expected.get(perm, set())

    if lab in expected_values:
        return "ALIGNED", f"Morning permission={perm} maps to Lab verdict={lab}."

    allowed_downgrades = {
        "GO": {"GO_LIMIT", "PROBE", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "GO_LIMIT": {"ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "PROBE": {"ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "ARMED": {"WAIT", "BLOCKED"},
        "WAIT": {"ARMED", "BLOCKED"},
        "CONTRACT_REPAIR": {"BLOCKED"},
    }
    if lab in allowed_downgrades.get(perm, set()):
        reason = "; ".join(soft[:4]) or "Downstream execution safety gate downgraded the Morning Validator route."
        return "ALIGNED_DOWNGRADED", f"Morning permission={perm}, Lab verdict={lab}. {reason}"

    return "CONFLICT", f"Morning permission={perm} does not align with Lab verdict={lab}."


def resolve_lab_tradeability(
    sig: Dict[str, Any],
    run_manifest: Optional[Dict[str, Any]] = None,
    open_trades: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    source = {
        "lab_execution_status": _u(sig.get("lab_execution_status")),
        "eod_candidate_status": _u(first(sig, "eod_candidate_status", "eod__eod_candidate_status")),
        "candidate_status": _u(first(sig, "candidate_status", "eod__candidate_status")),
        "effective_execution_verdict": _u(first(sig, "effective_execution_verdict", "eod__effective_execution_verdict")),
        "capital_authorization_state": _u(first(sig, "capital_authorization_state", "eod__capital_authorization_state")),
        "capital_permission": _u(first(sig, "capital_permission", "eod__capital_permission")),
        "eod_candidate_permission": _u(first(sig, "eod_candidate_permission", "eod__eod_candidate_permission")),
        "options_verdict": _u(first(sig, "options_verdict", "opt__options_verdict")),
        "campaign_verdict": _u(first(sig, "campaign_verdict", "sb_campaign")),
        "execution_verdict": _u(first(sig, "execution_verdict", "execution_mode", "v5_execution_mode")),
        "thesis_decision": _u(sig.get("thesis_decision")),
        "sb_final_verdict": _u(sig.get("sb_final_verdict")),
        "eil_v3_verdict": _u(first(sig, "eil_v3_verdict", "eil_raw_verdict")),
        "ev_decision_hint": _u(first(sig, "ev2_decision_hint", "ev_decision_hint", "eil__ev2_decision_hint", "eil__ev_decision_hint", "fd_ev_decision_hint")),
        "ev_status": _u(first(sig, "ev_status", "ev2_status", "eil__ev_status")),
        "pse_execution_mode": _u(sig.get("pse_execution_mode")),
        "trigger_primary": _u(sig.get("trigger_primary")),
        "mv_execution_permission": _u(first(sig, "mv__morning_execution_permission", "morning_execution_permission", "mv__execution_permission", "mv_execution_permission", "execution_permission")),
        "mv_live_validation_state": _u(first(sig, "mv__live_validation_state", "mv_live_validation_state", "live_validation_state")),
        "mv_execution_route": _u(first(sig, "mv__morning_execution_route", "morning_execution_route", "mv_morning_execution_route")),
        "mv_execution_lane": _u(first(sig, "mv__morning_execution_lane", "mv_morning_execution_lane", "morning_execution_lane")),
    }
    legacy_mv = _u(first(sig, "mv__verdict", "mv_verdict"))
    if not source["mv_execution_permission"] and legacy_mv:
        source["mv_execution_permission"] = {
            "EXECUTE": "GO",
            "GO": "GO",
            "GO_LIMIT": "GO_LIMIT",
            "CONFIRMED": "GO",
            "STARTER": "PROBE",
            "PROBE": "PROBE",
            "ARMED": "ARMED",
            "CONTRACT_REPAIR": "CONTRACT_REPAIR",
            "FLAG": "WAIT",
            "MANUAL_REVIEW": "WAIT",
            "WATCH": "WAIT",
            "WAIT": "WAIT",
            "WAIT_RETEST": "WAIT",
            "REJECT": "BLOCKED",
            "REJECTED": "BLOCKED",
            "BLOCKED": "BLOCKED",
        }.get(legacy_mv, "")
    source["mv_legacy_verdict"] = legacy_mv
    if not source["lab_execution_status"]:
        source["lab_execution_status"] = (
            source["eod_candidate_status"]
            or source["effective_execution_verdict"]
            or source["execution_verdict"]
            or source["pse_execution_mode"]
            or source["options_verdict"]
        )
    morning_present = source["mv_execution_permission"] in {"GO", "GO_LIMIT", "PROBE", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"}
    flags: List[str] = []
    veto_flags: List[str] = []
    soft: List[str] = []

    manifest = run_manifest or {}
    mode = _u(manifest.get("pipeline_mode")) or "UNKNOWN"
    fatal_manifest_flags = list(manifest.get("fatal_flags") or [])
    if fatal_manifest_flags:
        flags.extend([f"RUN_FATAL:{f}" for f in fatal_manifest_flags])
        veto_flags.extend(fatal_manifest_flags)

    if _is_missing(sig.get("ticker")):
        flags.append("MISSING_TICKER")
        veto_flags.append("MISSING_TICKER")

    if _u(sig.get("schema_status")) in {"INVALID", "ACTUARIAL_SCHEMA_INVALID"}:
        flags.append("SCHEMA_INVALID")
        veto_flags.append("SCHEMA_INVALID")

    contract_symbol = first(sig, "morning_selected_contract_symbol", "live_selected_contract_symbol", "contract_symbol", "live_contract_symbol", "alternative_contract_1", "evening_contract_symbol", "option_symbol", "recommended_contract", "opt__recommended_contract")
    strike = first(sig, "strike", "contract_strike", "opt__contract_strike")
    expiry = first(sig, "expiry", "contract_expiry", "opt__contract_expiry")
    premium = _f(first(sig, "premium_mid", "live_contract_mid", "live_mid", "contract_mid", "entry_premium", "contract_premium", "opt__premium_mid", "opt__contract_premium"), 0.0)
    looks_actionable = any(
        value in {
            "EXECUTE",
            "ARMED",
            "READY_EXECUTE",
            "READY_PROBE",
            "GO",
            "GO_LIMIT",
            "PROBE",
            "CONTRACT_REPAIR",
            "BUY_NOW",
            "FULL_EXECUTE",
            "LIVE_EXECUTE",
            *EOD_EXECUTION_STATES,
            *EOD_CAUTION_STATES,
        }
        for value in source.values()
    )
    if looks_actionable and (_is_missing(strike) or _is_missing(expiry) or premium <= 0):
        if source["mv_execution_permission"] == "CONTRACT_REPAIR":
            soft.append("MORNING_VALIDATION_CONTRACT_REPAIR")
            soft.append("MORNING_CONTRACT_ECONOMICS_REPAIR_REQUIRED")
        elif mode == "EOD" and not morning_present:
            soft.append("EOD_CONTRACT_REPAIR_REQUIRED")
            soft.append("EOD_MISSING_CONTRACT_ECONOMICS")
        else:
            flags.append("OPTIONS_CONTRACT_ECONOMICS_MISSING")
            veto_flags.append("OPTIONS_CONTRACT_ECONOMICS_MISSING")
    if looks_actionable and _is_missing(contract_symbol) and (_is_missing(strike) or _is_missing(expiry)):
        if source["mv_execution_permission"] == "CONTRACT_REPAIR":
            soft.append("MORNING_CONTRACT_SYMBOL_REPAIR_REQUIRED")
        elif mode == "EOD" and not morning_present:
            soft.append("EOD_CONTRACT_REPAIR_REQUIRED")
        else:
            flags.append("OPTIONS_CONTRACT_SYMBOL_MISSING")

    spread = _f(first(sig, "spread_pct", "live_contract_spread_pct", "live_spread_pct", "contract_spread_pct", "final_option_spread_pct", "opt__spread_pct_mid", "opt__spread_pct"), -1.0)
    if spread > 0:
        pct = spread * 100 if spread <= 1 else spread
        if pct > 18:
            flags.append("SPREAD_TOO_WIDE")
            veto_flags.append("SPREAD_TOO_WIDE")
    elif mode == "EOD" and not morning_present:
        soft.append("EOD_MISSING_LIVE_SPREAD")

    if source["mv_execution_permission"] == "BLOCKED" or source["mv_live_validation_state"] in {"REJECTED", "BLOCKED"}:
        flags.append("MORNING_VALIDATION_BLOCKED")
        veto_flags.append("MORNING_VALIDATION_BLOCKED")
    elif source["mv_execution_permission"] == "CONTRACT_REPAIR":
        soft.append("MORNING_VALIDATION_CONTRACT_REPAIR")
    elif source["mv_execution_permission"] == "PROBE":
        soft.append("MORNING_VALIDATION_PROBE")
    elif source["mv_execution_permission"] == "GO_LIMIT":
        soft.append("MORNING_VALIDATION_GO_LIMIT")
    elif source["mv_execution_permission"] == "WAIT":
        soft.append("MORNING_VALIDATION_WAIT")
    elif source["mv_execution_permission"] == "ARMED":
        soft.append("MORNING_VALIDATION_ARMED")
    if source["mv_live_validation_state"] in {"NO_LIVE_DATA", "STALE"}:
        soft.append(f"MORNING_VALIDATION_{source['mv_live_validation_state']}")

    if "BLOCKED" in source["eil_v3_verdict"]:
        flags.append("EIL_BLOCKED")
        veto_flags.append("EIL_BLOCKED")
    if source["execution_verdict"] in HARD_EXECUTION_STATES:
        flags.append(f"EXECUTION_{source['execution_verdict']}")
        veto_flags.append(f"EXECUTION_{source['execution_verdict']}")
    if source["options_verdict"] in HARD_EXECUTION_STATES:
        flags.append(f"OPTIONS_{source['options_verdict']}")
        veto_flags.append(f"OPTIONS_{source['options_verdict']}")
    if source["thesis_decision"] in HARD_EXECUTION_STATES:
        flags.append(f"THESIS_{source['thesis_decision']}")
        veto_flags.append(f"THESIS_{source['thesis_decision']}")
    if source["pse_execution_mode"] == "FATAL_BLOCK":
        flags.append("PSE_FATAL_BLOCK")
        veto_flags.append("PSE_FATAL_BLOCK")

    joined_gate_text = " ".join(
        _s(first(sig, "hard_gate_flags", "veto_flags", "block_code", "block_family", "execution_lock_reason"))
        for _ in [0]
    ).upper()
    if any(token in joined_gate_text for token in ("HARD_BLOCK", "FATAL", "INVALID")):
        flags.append("HARD_GATE_FLAG")
        veto_flags.append("HARD_GATE_FLAG")

    if duplicate_open_trade(sig, open_trades):
        flags.append("DUPLICATE_OPEN_TRADE")
        veto_flags.append("DUPLICATE_OPEN_TRADE")

    if source["sb_final_verdict"] == "EXECUTE" and veto_flags:
        flags.append("LEGACY_EXECUTE_CONFLICTS_WITH_BLOCK")

    if mode == "EOD" and not morning_present and "EOD_MORNING_VALIDATION_PENDING" in (manifest.get("stale_flags") or []):
        soft.append("EOD_MISSING_MORNING_VALIDATION")
    if mode in {"LIVE", "MORNING_VALIDATION"} and not morning_present and _is_missing(first(sig, "mv_verdict", "mv__verdict")):
        flags.append("LIVE_VALIDATION_MISSING")
        veto_flags.append("LIVE_VALIDATION_MISSING")

    if "DELAY" in _u(first(sig, "contract_quote_source", "md_quote_source", "eil_data_mode")):
        soft.append("DELAYED_OPTIONS_DATA")
    if source["execution_verdict"] == "WAIT_RETEST":
        soft.append("EXECUTION_WAIT_RETEST")
    if source["thesis_decision"] == "GO" and source["options_verdict"] in {"ARMED", "WATCHLIST"}:
        soft.append("THESIS_GO_OPTIONS_NOT_EXECUTE")
    if source["thesis_decision"] == "PROBE" and source["execution_verdict"] not in GO_EXECUTION_STATES:
        soft.append("V5_PROBE_WITHOUT_BUY_NOW")
    option_rr_raw = first(sig, "rr_options", "opt__rr_options", "option_rr", "rr")
    option_rr = _f(option_rr_raw, 0.0)
    if _is_missing(option_rr_raw):
        soft.append("RR_MISSING_OR_INVALID")
    elif option_rr < 0:
        flags.append("NEGATIVE_RR")
        veto_flags.append("NEGATIVE_RR")
    elif option_rr == 0:
        soft.append("NON_POSITIVE_RR")
    elif option_rr < 1.0:
        soft.append("WEAK_RR")
    if _f(first(sig, "ev2_ev_conf_adj", "eil_ev_net", "ev"), 0.0) < 0:
        soft.append("NEGATIVE_EV")
    if source["ev_decision_hint"] == "AVOID" or source["ev_status"] in {"AVOID", "FAIL", "NEGATIVE_EV"}:
        soft.append("EV_AVOID")
    elif source["ev_decision_hint"] == "WEAK":
        soft.append("EV_WEAK_NOT_MONETISABLE")
    elif source["ev_decision_hint"] not in {"STRONG", "MODERATE"}:
        soft.append("EV_DECISION_MISSING_OR_INVALID")
    for stale in manifest.get("stale_flags") or []:
        if stale not in soft:
            soft.append(stale)

    critical_soft = {
        "EOD_MISSING_MORNING_VALIDATION",
        "EOD_MISSING_LIVE_SPREAD",
        "MORNING_VALIDATION_PAPER_MODE",
        "MORNING_VALIDATION_NO_LIVE_DATA",
        "MORNING_VALIDATION_STALE",
        "LIVE_VALIDATION_MISSING",
        "EV_AVOID",
        "EV_WEAK_NOT_MONETISABLE",
        "EV_DECISION_MISSING_OR_INVALID",
        "NEGATIVE_EV",
        "NON_POSITIVE_RR",
        "RR_MISSING_OR_INVALID",
    }
    has_critical_soft = any(item in critical_soft for item in soft)

    if veto_flags:
        verdict = "NEGATIVE_RR" if "NEGATIVE_RR" in veto_flags else "BLOCKED"
        tradeable = False
        conflict_state = "HARD_CONFLICT"
        lock_reason = "; ".join(flags[:6])
    else:
        eod_status = source["eod_candidate_status"] or source["lab_execution_status"]
        is_eod_exec = eod_status in EOD_EXECUTION_STATES
        is_eod_caution = eod_status in EOD_CAUTION_STATES
        confirms_buy = source["execution_verdict"] in GO_EXECUTION_STATES or source["campaign_verdict"] == "READY_EXECUTE"
        options_ok = source["options_verdict"] == "EXECUTE"
        thesis_ok = source["thesis_decision"] in {"GO", "READY_EXECUTE"} or source["campaign_verdict"] == "READY_EXECUTE"
        economics_ok = premium > 0 and not _is_missing(expiry) and not _is_missing(strike)
        requires_live_validation = has_critical_soft
        if is_eod_exec:
            verdict = "EOD_CAUTION" if has_critical_soft else "EOD_EXEC"
            tradeable = not requires_live_validation and not soft
            conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
            lock_reason = "; ".join(soft) or "EOD_THESIS_READY"
        elif is_eod_caution:
            verdict = "EOD_CAUTION"
            tradeable = False
            conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
            lock_reason = "; ".join(soft) or "EOD_EXECUTE_WITH_CAUTION"
        elif options_ok and thesis_ok and confirms_buy and economics_ok and not requires_live_validation and not soft:
            verdict = "GO"
            tradeable = True
            conflict_state = "CLEAN"
            lock_reason = ""
        elif options_ok or source["options_verdict"] == "ARMED" or source["campaign_verdict"] in {"READY_EXECUTE", "READY_PROBE"} or source["thesis_decision"] == "GO":
            verdict = "ARMED"
            tradeable = False
            conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
            lock_reason = "; ".join(soft) or "AWAITING_EXECUTION_ALIGNMENT"
        else:
            verdict = "WAIT"
            tradeable = False
            conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
            lock_reason = "; ".join(soft) or "NO_ACTIONABLE_EXECUTION_CONFIRMATION"

        if morning_present:
            if source["mv_execution_permission"] == "GO" and economics_ok:
                if has_critical_soft:
                    verdict = "ARMED"
                    tradeable = False
                    conflict_state = "SOFT_CONFLICT"
                    lock_reason = "; ".join(soft) or "MORNING_VALIDATION_CRITICAL_SOFT_CONFLICT"
                else:
                    verdict = "GO"
                    tradeable = True
                    conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
                    lock_reason = "; ".join(soft) or ""
            elif source["mv_execution_permission"] == "GO_LIMIT" and economics_ok:
                verdict = "ARMED" if has_critical_soft else "GO_LIMIT"
                tradeable = not has_critical_soft
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_LIMIT_ENTRY"
            elif source["mv_execution_permission"] == "PROBE" and economics_ok:
                verdict = "ARMED" if has_critical_soft else "PROBE"
                tradeable = not has_critical_soft
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_PROBE"
            elif source["mv_execution_permission"] == "CONTRACT_REPAIR":
                verdict = "CONTRACT_REPAIR"
                tradeable = False
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_CONTRACT_REPAIR"
            elif source["mv_execution_permission"] == "GO" and economics_ok:
                verdict = "ARMED"
                tradeable = False
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_CONFIRMED_WITH_SOFT_CONFLICT"
            elif source["mv_execution_permission"] == "ARMED":
                verdict = "ARMED"
                tradeable = False
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_ARMED"
            elif source["mv_execution_permission"] == "WAIT":
                verdict = "WAIT"
                tradeable = False
                conflict_state = "SOFT_CONFLICT"
                lock_reason = "; ".join(soft) or "MORNING_VALIDATION_WAIT"

    eod_prep_pending = (
        mode == "EOD"
        and not morning_present
        and "EOD_MISSING_MORNING_VALIDATION" in soft
        and not veto_flags
    )
    if eod_prep_pending:
        verdict = "MORNING_VALIDATION_REQUIRED"
        tradeable = False
        conflict_state = "SOFT_CONFLICT" if soft else "CLEAN"
        lock_reason = "; ".join(soft) or "EOD_PREP_PENDING_MORNING_VALIDATION"

    requires_live = any(flag in soft for flag in ("EOD_MISSING_MORNING_VALIDATION", "EOD_MISSING_LIVE_SPREAD")) or (
        "LIVE_VALIDATION_MISSING" in veto_flags
    ) or (
        morning_present and source["mv_execution_permission"] in {"ARMED", "WAIT", "CONTRACT_REPAIR"}
    )
    prep_permission = "MANUAL_REVIEW_MORNING_VALIDATION" if eod_prep_pending else ""
    conflict_flags = flags + [f"SOFT:{item}" for item in soft]
    alignment_status, alignment_reason = _morning_lab_alignment(
        source["mv_execution_permission"],
        source["mv_live_validation_state"],
        verdict,
        conflict_state,
        veto_flags,
        soft,
    )
    return {
        "lab_verdict": verdict,
        "lab_tradeable": tradeable,
        "lab_execution_status": source["lab_execution_status"],
        "conflict_state": conflict_state,
        "conflict_flags": conflict_flags,
        "veto_flags": veto_flags,
        "execution_lock_reason": lock_reason,
        "requires_live_validation": requires_live,
        "prep_permission": prep_permission,
        "morning_lab_alignment_status": alignment_status,
        "morning_lab_alignment_reason": alignment_reason,
        "source_verdicts": source,
    }


def apply_lab_resolution(
    sig: Dict[str, Any],
    run_manifest: Optional[Dict[str, Any]] = None,
    open_trades: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    resolved = resolve_lab_tradeability(sig, run_manifest, open_trades)
    sig.update(
        {
            "lab_verdict": resolved["lab_verdict"],
            "lab_tradeable": resolved["lab_tradeable"],
            "lab_execution_status": resolved["lab_execution_status"],
            "lab_status": resolved["lab_verdict"],
            "conflict_state": resolved["conflict_state"],
            "conflict_flags": _json_safe(resolved["conflict_flags"]),
            "veto_flags": _json_safe(resolved["veto_flags"]),
            "execution_lock_reason": resolved["execution_lock_reason"],
            "requires_live_validation": resolved["requires_live_validation"],
            "prep_permission": resolved.get("prep_permission", ""),
            "morning_lab_alignment_status": resolved["morning_lab_alignment_status"],
            "morning_lab_alignment_reason": resolved["morning_lab_alignment_reason"],
            "source_verdicts_json": _json_safe(resolved["source_verdicts"]),
        }
    )
    return sig


def _trade_idea_id(row: Dict[str, Any], run_id: str) -> str:
    ticker = _s(row.get("ticker")).upper() or "UNKNOWN"
    direction = _u(first(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "selected_contract_side", "option_direction")) or "UNKNOWN"
    strike = _s(first(row, "strike", "contract_strike", "opt__contract_strike")) or "NA"
    expiry = _s(first(row, "expiry", "contract_expiry", "opt__contract_expiry")) or "NA"
    return f"{run_id}:{ticker}:{direction}:{strike}:{expiry}"


def opportunity_book_row(sig: Dict[str, Any], run_id: str, rank: int) -> Dict[str, Any]:
    canonical_direction = first(sig, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "selected_contract_side", "option_direction")
    aligned_instrument = _instrument_for_direction(
        canonical_direction,
        first(sig, "instrument", "options_strategy", "sb_instrument_now"),
    )
    aligned_contract, contract_alignment_flag = _contract_for_direction(sig, canonical_direction)
    lab_coherence_flags = first(sig, "lab_coherence_flags", "direction_conflict_reason")
    if contract_alignment_flag:
        lab_coherence_flags = _append_flag(lab_coherence_flags, contract_alignment_flag)
    lab_coherence_status = first(sig, "lab_coherence_status", "direction_alignment_status")
    if contract_alignment_flag and not lab_coherence_status:
        lab_coherence_status = "DIRECTION_CONTRACT_REVIEW"

    row = {
        "run_id": run_id,
        "ticker": _s(sig.get("ticker")).upper(),
        "trade_idea_id": sig.get("trade_idea_id") or _trade_idea_id(sig, run_id),
        "lab_rank": rank,
        "lab_verdict": sig.get("lab_verdict", "WAIT"),
        "lab_tradeable": bool(sig.get("lab_tradeable")),
        "prep_permission": first(sig, "prep_permission", "run_prep_permission", "eod_prep_permission"),
        "lab_status": sig.get("lab_status") or sig.get("lab_verdict", "WAIT"),
        "lab_execution_status": sig.get("lab_execution_status", ""),
        "execution_category": first(sig, "execution_category", "morning_execution_route", "morning_execution_lane", "morning_execution_permission", "execution_permission", "lab_verdict"),
        "display_execution_mode": first(sig, "display_execution_mode", "morning_entry_action", "sb_execution_mode", "execution_verdict"),
        "position_size_display": first(sig, "position_size_display", "sb_position_size_display"),
        "lab_coherence_status": lab_coherence_status,
        "lab_coherence_flags": lab_coherence_flags,
        "canonical_direction": canonical_direction,
        "morning_execution_permission": first(
            sig,
            "morning_execution_permission",
            "mv__morning_execution_permission",
            "mv_execution_permission",
            "mv__execution_permission",
            "execution_permission",
        ),
        "morning_execution_route": first(
            sig,
            "morning_execution_route",
            "mv__morning_execution_route",
            "mv_morning_execution_route",
            "morning_execution_lane",
            "mv__morning_execution_lane",
            "execution_permission",
        ),
        "morning_execution_lane": first(sig, "morning_execution_lane", "mv__morning_execution_lane"),
        "morning_entry_action": first(sig, "morning_entry_action", "mv__morning_entry_action"),
        "morning_unlock_condition": first(sig, "morning_unlock_condition", "mv__morning_unlock_condition"),
        "morning_lab_alignment_status": sig.get("morning_lab_alignment_status", ""),
        "morning_lab_alignment_reason": sig.get("morning_lab_alignment_reason", ""),
        "conflict_state": sig.get("conflict_state", "CLEAN"),
        "conflict_flags": sig.get("conflict_flags", "[]"),
        "execution_lock_reason": sig.get("execution_lock_reason", ""),
        "requires_live_validation": bool(sig.get("requires_live_validation")),
        "direction": canonical_direction,
        "instrument": aligned_instrument,
        "contract_symbol": aligned_contract,
        "morning_selected_contract_symbol": first(sig, "morning_selected_contract_symbol", "live_selected_contract_symbol"),
        "contract_repair_status": first(sig, "contract_repair_status", "opt__contract_repair_status"),
        "contract_repair_required": first(sig, "contract_repair_required", "opt__contract_repair_required"),
        "contract_repair_reason": first(sig, "contract_repair_reason", "opt__contract_repair_reason"),
        "contract_repair_action": first(sig, "contract_repair_action", "opt__contract_repair_action"),
        "contract_repair_live_action": first(sig, "contract_repair_live_action", "mv__contract_repair_live_action"),
        "contract_repair_alternative_used": first(sig, "contract_repair_alternative_used", "mv__contract_repair_alternative_used"),
        "alternative_contract_attempts": first(sig, "alternative_contract_attempts", "opt__alternative_contract_attempts"),
        "alternative_contract_1": first(sig, "alternative_contract_1", "alt_contract_1"),
        "alternative_contract_2": first(sig, "alternative_contract_2", "alt_contract_2"),
        "alternative_contract_3": first(sig, "alternative_contract_3", "alt_contract_3"),
        "strike": first(sig, "strike", "live_contract_strike", "contract_strike", "opt__contract_strike"),
        "expiry": first(sig, "expiry", "contract_expiry", "opt__contract_expiry"),
        "dte": first(sig, "dte", "contract_dte", "opt__contract_dte"),
        "premium_mid": first(sig, "premium_mid", "entry_premium", "contract_premium", "opt__premium_mid", "opt__contract_premium"),
        "spread_pct": first(sig, "spread_pct", "final_option_spread_pct", "opt__spread_pct_mid", "opt__spread_pct"),
        "liquidity_score": first(sig, "liquidity_score", "eil_liquidity_score", "opt__liquidity_score"),
        "priority_score": sig.get("priority_score", ""),
        "rr_predicted": first(sig, "rr_predicted", "rr_options", "rr", "option_rr"),
        "ev_predicted": first(sig, "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "ev"),
        "win_prob_predicted": first(sig, "win_prob_predicted", "ev2_p_win_blended", "win_rate_20d", "win_rate_10d"),
        "actuarial_match_method": first(sig, "actuarial_match_method", "layer2__state_match_method", "vg__layer2__state_match_method"),
        "actuarial_match_type": first(sig, "actuarial_match_type", "vg__actuarial_match_type"),
        "actuarial_ev_weight": first(sig, "actuarial_ev_weight", "vg__actuarial_ev_weight"),
        "behaviour_state_key": first(sig, "behaviour_state_key", "vg__behaviour_state_key"),
        "behaviour_state_hash": first(sig, "behaviour_state_hash", "vg__behaviour_state_hash"),
        "catalyst_overlay": first(sig, "catalyst_overlay", "vg__catalyst_overlay"),
        "actuarial_sample_size": first(
            sig,
            "actuarial_sample_size",
            "layer2__sample_size",
            "vg__layer2__sample_size",
            "layer2__future_momentum_bucket_sample_size",
            "vg__layer2__future_momentum_bucket_sample_size",
            "actuarial_sample",
        ),
        "actuarial_confidence": first(sig, "actuarial_confidence", "layer2__sample_confidence_bucket", "vg__layer2__sample_confidence_bucket"),
        "physics_state_id": first(sig, "physics_state_id", "vg__physics_state_id"),
        "hidden_state_label": first(sig, "hidden_state_label", "vg__hidden_state_label"),
        "state_transition_label": first(sig, "state_transition_label", "vg__state_transition_label"),
        "market_energy_score": first(sig, "market_energy_score", "vg__market_energy_score"),
        "compression_energy": first(sig, "compression_energy", "vg__compression_energy"),
        "directional_force": first(sig, "directional_force", "vg__directional_force"),
        "force_alignment_score": first(sig, "force_alignment_score", "vg__force_alignment_score"),
        "trend_inertia": first(sig, "trend_inertia", "vg__trend_inertia"),
        "entropy_score": first(sig, "entropy_score", "vg__entropy_score"),
        "phase_transition_probability": first(sig, "phase_transition_probability", "vg__phase_transition_probability"),
        "liquidity_friction_score": first(sig, "liquidity_friction_score", "vg__liquidity_friction_score"),
        "macro_regime": first(sig, "macro_regime", "macro_regime_label", "vg__macro_regime", "vg__macro_regime_label"),
        "sector_tilt": first(sig, "sector_tilt", "sector_rotation_state", "ticker_sector_alignment", "vg__sector_tilt", "vg__sector_rotation_state", "vg__ticker_sector_alignment"),
        "regime_drift_status": first(sig, "regime_drift_status", "vg__regime_drift_status"),
        "eil_signal_verdict": first(sig, "eil_signal_verdict", "eil_v3_verdict", "fd_advisory_verdict", "fd_verdict"),
        "eil_v3_verdict": first(sig, "eil_v3_verdict", "eil_signal_verdict", "fd_advisory_verdict", "fd_verdict"),
        "eil_composite_eod": first(sig, "eil_composite_eod", "eil_composite_score", "eil__composite_score"),
        "entry_plan": first(sig, "entry_plan", "trigger_primary", "scenario_entry_trigger", "wbs__entry_guidance"),
        "invalidation_price": first(sig, "invalidation_price", "invalidation_eod", "stop_loss"),
        "target_price": first(sig, "target_price", "wbs__wall_price", "structural_target", "opt__structural_target"),
        "target_in_play": first(sig, "target_in_play", "opt__target_in_play"),
        "structural_target": first(sig, "structural_target", "opt__structural_target", "wbs__wall_price", "target_price"),
        "underlying_price": first(sig, "underlying_price", "opt__underlying_price", "live_underlying_price", "current_price", "last_price", "scanner_price", "signal_price"),
        "signal_price": first(sig, "signal_price", "scanner_price", "underlying_price", "opt__underlying_price"),
        "scanner_price": first(sig, "scanner_price", "signal_price", "underlying_price", "opt__underlying_price"),
        "target_zone": first(sig, "target_zone", "wbs__target_zone"),
        "runway_to_target": first(sig, "runway_to_target", "runway_to_wall", "runway_to_wall_pct"),
        "runway_to_wall_pct": first(sig, "runway_to_wall_pct", "runway_to_wall", "runway_to_target"),
        "breakeven_price": first(sig, "breakeven_price", "opt__breakeven_price"),
        "breakeven_pct": first(sig, "breakeven_pct", "csm_breakeven_pct", "opt__breakeven_pct"),
        "breakeven_feasibility": first(sig, "breakeven_feasibility", "opt__breakeven_feasibility"),
        "option_gain_at_target": first(sig, "option_gain_at_target", "opt__option_gain_at_target"),
        "layer2__raw_prob_target_hit": first(sig, "layer2__raw_prob_target_hit", "layer2__outcomes__raw_prob_target_hit", "vg__layer2__raw_prob_target_hit"),
        "layer2__adjusted_prob_target_hit": first(sig, "layer2__adjusted_prob_target_hit", "layer2__outcomes__adjusted_prob_target_hit", "vg__layer2__adjusted_prob_target_hit"),
        "layer2__raw_expected_time_to_target": first(sig, "layer2__raw_expected_time_to_target", "layer2__outcomes__raw_expected_time_to_target", "vg__layer2__raw_expected_time_to_target"),
        "layer2__outcomes__median_days_to_target": first(sig, "layer2__outcomes__median_days_to_target", "layer2__median_days_to_target", "vg__layer2__outcomes__median_days_to_target"),
        "contract_delta": first(sig, "contract_delta", "opt__contract_delta", "delta"),
        "contract_gamma": first(sig, "contract_gamma", "opt__contract_gamma", "gamma"),
        "contract_theta": first(sig, "contract_theta", "opt__contract_theta", "theta"),
        "contract_iv": first(sig, "contract_iv", "opt__contract_iv", "iv"),
        "contract_bid": first(sig, "contract_bid", "opt__contract_bid", "bid"),
        "contract_ask": first(sig, "contract_ask", "opt__contract_ask", "ask"),
        "contract_mid": first(sig, "contract_mid", "opt__contract_mid", "mid", "premium_mid"),
        "contract_oi": first(sig, "contract_oi", "opt__contract_oi", "openInterest", "open_interest"),
        "contract_volume": first(sig, "contract_volume", "opt__contract_volume", "volume"),
        "call_wall": first(sig, "call_wall", "opt__call_wall"),
        "put_wall": first(sig, "put_wall", "opt__put_wall"),
        "gamma_flip": first(sig, "gamma_flip", "opt__gamma_flip"),
        "max_pain": first(sig, "max_pain", "opt__max_pain"),
        "pcr_signal": first(sig, "pcr_signal", "opt__pcr_signal"),
        "gamma_island_on_path": first(sig, "gamma_island_on_path", "opt__gamma_island_on_path"),
        "gamma_island_level": first(sig, "gamma_island_level", "opt__gamma_island_level"),
        "gamma_island_distance_pct": first(sig, "gamma_island_distance_pct", "opt__gamma_island_distance_pct"),
        "wbs": first(sig, "wbs", "wbs_score"),
        "wbs_grade": first(sig, "wbs_grade"),
        "wbs_wall_price": first(sig, "wbs_wall_price"),
        "wbs_wall_dist_pct": first(sig, "wbs_wall_dist_pct"),
        "wbs_f5_momentum": first(sig, "wbs_f5_momentum"),
        "wbs_phase_b_trigger": first(sig, "wbs_phase_b_trigger"),
        "wbs_phase_c_trigger": first(sig, "wbs_phase_c_trigger"),
        "wbs_entry_guidance": first(sig, "wbs_entry_guidance"),
        "wbs_size_guidance": first(sig, "wbs_size_guidance"),
        "wbs_wall_stall_rule": first(sig, "wbs_wall_stall_rule"),
        "wbs_notes": first(sig, "wbs_notes"),
        "ts_expiry_date": first(sig, "ts_expiry_date", "opt__ts_expiry_date"),
        "ts_dte_remaining_at_stop": first(sig, "ts_dte_remaining_at_stop", "opt__ts_dte_remaining_at_stop"),
        "ts_checkpoint_date": first(sig, "ts_checkpoint_date", "opt__ts_checkpoint_date"),
        "ts_checkpoint_rule": first(sig, "ts_checkpoint_rule", "opt__ts_checkpoint_rule"),
        "ts_dte_used": first(sig, "ts_dte_used", "opt__ts_dte_used"),
        "hold_urgency": first(sig, "hold_urgency", "opt__hold_urgency"),
        "scenario_dte_target": first(sig, "scenario_dte_target", "opt__scenario_dte_target"),
        "hold_window": first(sig, "hold_window", "horizon_bucket", "hold_label", "opt__hold_label"),
        "time_horizon": first(sig, "horizon_bucket", "hold_window", "hold_label", "opt__hold_label"),
        "hold_period": first(sig, "hold_period", "hold_days", "hold_label", "hold_window", "horizon_bucket"),
        "trigger_price": _trigger_price(sig),
        "trigger_evidence": _trigger_evidence(sig),
        "trigger_primary": first(sig, "trigger_primary", "trigger_codes", "scenario_entry_trigger"),
        "trigger_quality": first(sig, "trigger_quality", "trigger_score"),
        "trigger_score": first(sig, "trigger_score", "trigger_count"),
        "trigger_codes": first(sig, "trigger_codes", "trigger_primary", "scenario_entry_trigger"),
        "pcr_vol_status": first(sig, "pcr_vol_status", "opt__pcr_vol_status"),
        "pcr_vol_missing_reason": first(sig, "pcr_vol_missing_reason", "opt__pcr_vol_missing_reason"),
        "direction_conflict_status": first(sig, "direction_conflict_status", "opt__direction_conflict_status"),
        "direction_conflict_reason": first(sig, "direction_conflict_reason", "opt__direction_conflict_reason"),
        "notes": first(sig, "notes", "execution_lock_reason", "verdict_coherence_notes", "sb_verdict_reason"),
        "source_payload_json": _json_safe(sig),
    }
    return {key: csv_safe_row(row).get(key, "") for key in FINAL_BOOK_FIELDS}


def build_final_opportunity_book(
    run_id: str,
    signals: Iterable[Dict[str, Any]],
    run_manifest: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    manifest = run_manifest or {}
    enriched = [dict(sig) for sig in signals]
    for sig in enriched:
        if "lab_verdict" not in sig or "morning_lab_alignment_status" not in sig:
            apply_lab_resolution(sig, manifest)
    order = {"GO": 0, "GO_LIMIT": 1, "PROBE": 2, "CONTRACT_REPAIR": 3, "MORNING_VALIDATION_REQUIRED": 4, "ARMED": 5, "WAIT": 6, "BLOCKED": 7}
    enriched.sort(
        key=lambda row: (
            order.get(_u(row.get("lab_verdict")), 9),
            -_f(row.get("priority_score"), 0.0),
            _s(row.get("ticker")),
        )
    )
    return [opportunity_book_row(sig, run_id, rank) for rank, sig in enumerate(enriched, 1)]



def _lab_extract_source_paths(runs_dir: Path, run_id: str) -> List[Path]:
    run_root = Path(runs_dir) / run_id
    candidates = [
        run_root / "morning_validation" / f"morning_validated_trades_{run_id}.csv",
        run_root / "execution" / f"execution_v3_5_{run_id}.csv",
        run_root / "superbrain" / f"eil_enriched_{run_id}.csv",
        run_root / "superbrain" / f"wall_break_scores_{run_id}.csv",
        run_root / "options" / f"options_intelligence_{run_id}.csv",
        run_root / "morning_validation" / f"morning_candidates_{run_id}.csv",
    ]
    return [path for path in candidates if path.exists()]


def _lab_extract_field_aliases() -> Dict[str, List[str]]:
    return {
        "target_in_play": ["target_in_play", "opt__target_in_play"],
        "structural_target": ["structural_target", "opt__structural_target", "target_price", "wbs__wall_price"],
        "underlying_price": ["underlying_price", "opt__underlying_price", "live_underlying_price", "scanner_price", "signal_price"],
        "signal_price": ["signal_price", "scanner_price", "underlying_price", "opt__underlying_price"],
        "scanner_price": ["scanner_price", "signal_price", "underlying_price", "opt__underlying_price"],
        "target_zone": ["target_zone", "wbs__target_zone"],
        "runway_to_target": ["runway_to_target", "runway_to_wall", "runway_to_wall_pct"],
        "runway_to_wall_pct": ["runway_to_wall_pct", "runway_to_wall", "runway_to_target"],
        "breakeven_price": ["breakeven_price", "opt__breakeven_price"],
        "breakeven_pct": ["breakeven_pct", "csm_breakeven_pct", "opt__breakeven_pct"],
        "breakeven_feasibility": ["breakeven_feasibility", "opt__breakeven_feasibility"],
        "option_gain_at_target": ["option_gain_at_target", "opt__option_gain_at_target"],
        "layer2__raw_prob_target_hit": ["layer2__raw_prob_target_hit", "layer2__outcomes__raw_prob_target_hit", "vg__layer2__raw_prob_target_hit"],
        "layer2__adjusted_prob_target_hit": ["layer2__adjusted_prob_target_hit", "layer2__outcomes__adjusted_prob_target_hit", "vg__layer2__adjusted_prob_target_hit"],
        "layer2__raw_expected_time_to_target": ["layer2__raw_expected_time_to_target", "layer2__outcomes__raw_expected_time_to_target", "vg__layer2__raw_expected_time_to_target"],
        "layer2__outcomes__median_days_to_target": ["layer2__outcomes__median_days_to_target", "layer2__median_days_to_target", "vg__layer2__outcomes__median_days_to_target"],
        "contract_delta": ["contract_delta", "opt__contract_delta", "delta"],
        "contract_gamma": ["contract_gamma", "opt__contract_gamma", "gamma"],
        "contract_theta": ["contract_theta", "opt__contract_theta", "theta"],
        "contract_iv": ["contract_iv", "opt__contract_iv", "iv"],
        "contract_bid": ["contract_bid", "opt__contract_bid", "bid"],
        "contract_ask": ["contract_ask", "opt__contract_ask", "ask"],
        "contract_mid": ["contract_mid", "opt__contract_mid", "mid", "premium_mid"],
        "contract_oi": ["contract_oi", "opt__contract_oi", "openInterest", "open_interest"],
        "contract_volume": ["contract_volume", "opt__contract_volume", "volume"],
        "call_wall": ["call_wall", "opt__call_wall"],
        "put_wall": ["put_wall", "opt__put_wall"],
        "gamma_flip": ["gamma_flip", "opt__gamma_flip"],
        "max_pain": ["max_pain", "opt__max_pain"],
        "pcr_signal": ["pcr_signal", "opt__pcr_signal"],
        "gamma_island_on_path": ["gamma_island_on_path", "opt__gamma_island_on_path"],
        "gamma_island_level": ["gamma_island_level", "opt__gamma_island_level"],
        "gamma_island_distance_pct": ["gamma_island_distance_pct", "opt__gamma_island_distance_pct"],
        "wbs": ["wbs", "wbs_score"],
        "wbs_grade": ["wbs_grade"],
        "wbs_wall_price": ["wbs_wall_price"],
        "wbs_wall_dist_pct": ["wbs_wall_dist_pct"],
        "wbs_f5_momentum": ["wbs_f5_momentum"],
        "wbs_phase_b_trigger": ["wbs_phase_b_trigger"],
        "wbs_phase_c_trigger": ["wbs_phase_c_trigger"],
        "wbs_entry_guidance": ["wbs_entry_guidance"],
        "wbs_size_guidance": ["wbs_size_guidance"],
        "wbs_wall_stall_rule": ["wbs_wall_stall_rule"],
        "wbs_notes": ["wbs_notes"],
        "ts_expiry_date": ["ts_expiry_date", "opt__ts_expiry_date"],
        "ts_dte_remaining_at_stop": ["ts_dte_remaining_at_stop", "opt__ts_dte_remaining_at_stop"],
        "ts_checkpoint_date": ["ts_checkpoint_date", "opt__ts_checkpoint_date"],
        "ts_checkpoint_rule": ["ts_checkpoint_rule", "opt__ts_checkpoint_rule"],
        "ts_dte_used": ["ts_dte_used", "opt__ts_dte_used"],
        "hold_urgency": ["hold_urgency", "opt__hold_urgency"],
        "scenario_dte_target": ["scenario_dte_target", "opt__scenario_dte_target"],
    }


def _lab_extract_first_value(row: Dict[str, Any], aliases: List[str]) -> Any:
    for key in aliases:
        value = row.get(key)
        if not _is_missing(value):
            return value
    return ""


def _enrich_lab_extract_rows_from_run_sources(rows: List[Dict[str, Any]], runs_dir: Path | str, run_id: str) -> None:
    aliases = _lab_extract_field_aliases()
    source_by_ticker: Dict[str, Dict[str, Any]] = {}
    for path in _lab_extract_source_paths(Path(runs_dir), run_id):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for raw in csv.DictReader(fh):
                    ticker = _s(raw.get("ticker")).upper()
                    if not ticker:
                        continue
                    slot = source_by_ticker.setdefault(ticker, {})
                    for field, keys in aliases.items():
                        if _is_missing(slot.get(field)):
                            value = _lab_extract_first_value(raw, keys)
                            if not _is_missing(value):
                                slot[field] = value
        except Exception:
            continue

    for row in rows:
        ticker = _s(row.get("ticker")).upper()
        source = source_by_ticker.get(ticker, {})
        for field in aliases:
            if _is_missing(row.get(field)):
                value = source.get(field, "")
                if not _is_missing(value):
                    row[field] = value
        if _is_missing(row.get("structural_target")) and not _is_missing(row.get("target_price")):
            row["structural_target"] = row.get("target_price")


def write_final_opportunity_book(
    run_id: str,
    signals: Iterable[Dict[str, Any]],
    run_manifest: Optional[Dict[str, Any]],
    runs_dir: Path | str,
) -> Dict[str, Any]:
    rows = build_final_opportunity_book(run_id, signals, run_manifest)
    _enrich_lab_extract_rows_from_run_sources(rows, runs_dir, run_id)
    out_dir = Path(runs_dir) / run_id / "intelligence_lab"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"final_opportunity_book_{run_id}.csv"
    json_path = out_dir / f"final_opportunity_book_{run_id}.json"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FINAL_BOOK_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    triage_csv_path = out_dir / f"lab_triage_view_{run_id}.csv"
    with triage_csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LAB_TRIAGE_VIEW_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{k: row.get(k, "") for k in LAB_TRIAGE_VIEW_FIELDS} for row in rows])

    # Keep Pipeline Interpreter in lock-step with the same compact Lab view.
    try:
        import sys as _sys
        _repo_root = Path(runs_dir).parent.parent.parent
        _sys.path.insert(0, str(_repo_root / "pipeline_interpreter"))
        from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
        _ma_on_pipeline_complete(str(triage_csv_path), output_dir=str(out_dir))
    except Exception:
        pass

    payload = {
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "candidate_count": len(rows),
        "verdict_counts": {
            verdict: sum(1 for row in rows if row.get("lab_verdict") == verdict)
            for verdict in ("GO", "GO_LIMIT", "PROBE", "CONTRACT_REPAIR", "MORNING_VALIDATION_REQUIRED", "ARMED", "WAIT", "BLOCKED")
        },
        "rows": rows,
    }
    json_path.write_text(_json_safe(payload), encoding="utf-8")
    return {"csv_path": str(csv_path), "triage_csv_path": str(triage_csv_path), "json_path": str(json_path), **payload}


def read_final_opportunity_book(run_id: str, runs_dir: Path | str) -> Dict[str, Any]:
    path = Path(runs_dir) / run_id / "intelligence_lab" / f"final_opportunity_book_{run_id}.json"
    return _read_json(path)


def learning_feedback_from_closed_trades(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = [dict(row) for row in rows]
    wins = [r for r in items if _f(r.get("pnl_usd"), 0.0) > 0]

    def grouped_rate(key: str) -> List[Dict[str, Any]]:
        buckets: Dict[str, Dict[str, float]] = {}
        for r in items:
            name = _s(r.get(key)) or "UNKNOWN"
            b = buckets.setdefault(name, {"n": 0, "wins": 0, "pnl": 0.0})
            b["n"] += 1
            b["wins"] += 1 if _f(r.get("pnl_usd"), 0.0) > 0 else 0
            b["pnl"] += _f(r.get("pnl_usd"), 0.0)
        out = []
        for name, vals in buckets.items():
            n = vals["n"] or 1
            out.append(
                {
                    "bucket": name,
                    "n": int(vals["n"]),
                    "win_rate": round(vals["wins"] / n, 3),
                    "avg_pnl_usd": round(vals["pnl"] / n, 2),
                }
            )
        return sorted(out, key=lambda x: (x["win_rate"], x["n"]), reverse=True)

    pred_rr = [_f(r.get("rr_predicted"), 0.0) for r in items if not _is_missing(r.get("rr_predicted"))]
    real_rr = [_f(r.get("rr_realised"), 0.0) for r in items if not _is_missing(r.get("rr_realised"))]
    avg_pred = round(sum(pred_rr) / len(pred_rr), 3) if pred_rr else 0.0
    avg_real = round(sum(real_rr) / len(real_rr), 3) if real_rr else 0.0
    calibration = round(1.0 - min(abs(avg_pred - avg_real) / avg_pred, 1.0), 3) if avg_pred else None
    physics_rates = grouped_rate("physics_state_id")
    return {
        "n_trades": len(items),
        "win_rate": round(len(wins) / len(items), 3) if items else 0.0,
        "avg_predicted_rr": avg_pred,
        "avg_realised_rr": avg_real,
        "calibration_score": calibration,
        "top_winning_states": physics_rates[:5],
        "top_losing_states": sorted(physics_rates, key=lambda x: (x["win_rate"], -x["n"]))[:5],
        "win_rate_by_physics_state": physics_rates,
        "win_rate_by_vanguard_match_method": grouped_rate("actuarial_match_method"),
        "win_rate_by_options_verdict": grouped_rate("options_verdict"),
        "average_hold_days": round(
            sum(_f(r.get("hold_days"), 0.0) for r in items) / len(items), 2
        )
        if items
        else 0.0,
        "average_mfe": None,
        "average_mae": None,
        "recommended_threshold_changes": [
            "Review states with negative average P&L after at least 10 closed trades.",
            "Do not loosen execution gates from this feedback endpoint alone.",
        ],
    }

# CONTRACT-REPAIR-ALT-001: Lab handoff preserves repair alternatives.
