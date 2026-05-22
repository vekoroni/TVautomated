"""Morning Validator upgrade: live thesis confirmation.

This module is intentionally a validator, not a scanner. It consumes the
evening opportunity book or morning candidate manifest, preserves the committed
evening fields, compares them with live morning truth when available, and writes
an auditable validation packet for Intelligence Lab.
"""

from __future__ import annotations

import argparse
import os
import csv
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "data" / "output" / "runs"
LIVE_FETCH_TIMEOUT_SEC = float(os.getenv("AVS_MV_LIVE_TIMEOUT_SEC", "12"))
LIVE_FETCH_WORKERS = max(1, int(os.getenv("AVS_MV_LIVE_WORKERS", "3")))

MACRO_DIR = ROOT / "dropbox" / "macro"
INPUTS_DIR = ROOT / "dropbox" / "inputs"
DEFAULT_MACRO_PATH = MACRO_DIR / "macro_intelligence_latest.json"
DEFAULT_MACRO_ENRICHMENT_PATH = MACRO_DIR / "avshunter_macro_enrichment_delta.json"
DEFAULT_CATALYST_CALENDAR_PATH = INPUTS_DIR / "catalyst_calendar_latest.csv"

VALIDATION_STATES = {"CONFIRMED", "REJECTED", "WAIT_RETEST", "STALE", "NO_LIVE_DATA", "PENDING_LIVE_DATA", "BLOCKED"}
EXECUTION_PERMISSIONS = {"GO", "GO_LIMIT", "PROBE", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"}
OPTIONS_RESEARCH_PERMISSION = "MANUAL_REVIEW_REQUIRED"

EOD_CARRY_FORWARD_STATUSES = {
    "EOD_THESIS_READY",
    "EOD_THESIS_READY_REPAIR_AT_OPEN",
    "EOD_TRIGGER_READY",
    "EOD_WATCHLIST_MONETISABLE",
    "EOD_PROBE_CANDIDATE",
    "EOD_DATA_INSUFFICIENT_REVIEW",
    "EOD_CATALYST_EXECUTE_CANDIDATE",
    "EOD_EXECUTE_CANDIDATE",
    "EOD_EXECUTE_WITH_CAUTION",
    "EOD_CONTRACT_REPAIR_REQUIRED",
    "EOD_TRIGGER_READY_REVIEW",
    "EOD_CATALYST_WATCH",
}

EOD_STRUCTURAL_HARD_STATUSES = {"EOD_STRUCTURAL_BLOCK", "EOD_NO_OPTIONS_ROUTE", "EOD_BLOCK"}
EOD_STRUCTURAL_HARD_TOKENS = {
    "AT_WALL",
    "INVALIDATION_BROKEN",
    "NO_CHAIN",
    "NO_OPTIONS_CHAIN",
    "NO_CONTRACT_MARKET",
    "NO_OPTIONS_ROUTE",
    "NO_EXPIRY",
    "NO_VIABLE_OPTION_AFTER_SEARCH",
    "DEEP_NEGATIVE_STRUCTURAL_EV",
    "HALTED",
    "NON_TRADEABLE",
    "NO_UNDERLYING_PRICE",
    "MISSING_PRICE",
}
EOD_REPAIRABLE_TOKENS = {
    "SPREAD",
    "LOW_OI",
    "VOLUME",
    "IV",
    "OIS",
    "BSM",
    "SYNTHETIC",
    "QUOTE",
    "NO_RESEARCH_CONTRACT",
    "MISSING_CRITICAL",
    "MISSING_CONTRACT",
    "NO_CONTRACT_SELECTED",
    "BREAKEVEN",
    "ESTIMATED_R",
    "RR",
    "NO_EDGE",
    "TIER_4_FLAT",
    "DATA_MISSING",
    "CAMPAIGN",
    "LOW_CONVEXITY",
    "DIRECTION_CONFLICT",
}

LIVE_FIELDS = [
    "live_data_mode",
    "live_price",
    "live_bid",
    "live_ask",
    "live_mid",
    "live_spread_pct",
    "live_volume",
    "live_vwap",
    "live_open",
    "live_high",
    "live_low",
    "live_prev_close",
    "live_gap_pct",
    "live_orb_high",
    "live_orb_low",
    "live_distance_to_vwap_pct",
    "live_contract_bid",
    "live_contract_ask",
    "live_contract_mid",
    "live_contract_spread_pct",
    "live_contract_volume",
    "live_contract_open_interest",
    "live_iv",
    "live_delta",
    "live_gamma",
    "live_theta",
    "live_vega",
    "live_data_timestamp_utc",
    "live_data_age_minutes",
    "live_data_freshness_override",
    "live_equity_data_source",
    "live_options_data_source",
    "live_options_data_freshness",
    "live_options_quote_timestamp_utc",
    "live_options_delay_minutes",
    "live_options_provider_status",
]

EVENING_FIELDS = [
    "run_id",
    "validation_timestamp_utc",
    "ticker",
    "trade_idea_id",
    "evening_lab_verdict",
    "evening_direction",
    "evening_contract_symbol",
    "evening_strike",
    "evening_expiry",
    "evening_dte",
    "evening_premium_mid",
    "evening_target_price",
    "evening_invalidation_price",
    "evening_physics_state_id",
    "evening_hidden_state_label",
    "evening_state_transition_label",
    "evening_phase_transition_probability",
    "evening_priority_score",
    "evening_rr_predicted",
    "evening_ev_predicted",
    "evening_win_prob_predicted",
]

VALIDATION_FIELDS = [
    "live_validation_state",
    "morning_execution_permission",
    "morning_execution_route",
    "execution_permission",
    "eod_thesis_confirmed",
    "physics_transition_confirmed",
    "vwap_confirmed",
    "opening_range_confirmed",
    "direction_confirmed",
    "contract_liquidity_confirmed",
    "spread_confirmed",
    "breakeven_confirmed",
    "invalidation_respected",
    "live_price_drift_ok",
    "live_data_fresh",
    "validation_confidence",
    "validation_score",
    "morning_execution_lane",
    "morning_entry_action",
    "morning_unlock_condition",
    "thesis_validity_state",
    "entry_timing_state",
    "contract_tradability_state",
    "direction_alignment_status",
    "footprint_continuity_state",
    "footprint_continuity_reason",
    "live_delta_alignment_status",
    "live_delta_band_status",
    "rejection_reason",
    "wait_reason",
    "upgrade_downgrade_reason",
    "morning_notes",
]

EOD_RECEIPT_FIELDS = [
    "eod_candidate_status",
    "eod_candidate_reason",
    "eod_dropoff_reason",
    "monetisation_fit_score",
    "monetisation_fit_label",
    "canonical_direction",
    "resolved_direction",
    "footprint_direction",
    "footprint_lock_status",
    "footprint_lock_reason",
    "primary_direction",
    "raw_primary_direction",
    "direction_reroute_status",
    "direction_decision_reason",
    "direction_call_score",
    "direction_put_score",
    "selected_contract_side",
    "direction_arbitration_status",
    "direction_arbitration_reason",
    "direction_conflict_gate",
    "catalyst_direction_conflict_status",
    "catalyst_direction_conflict_reason",
    "pcr_direction_conflict_status",
    "pcr_direction_conflict_reason",
    "direction_conflict_status",
    "direction_conflict_reason",
    "pcr_vol",
    "pcr_vol_status",
    "pcr_vol_missing_reason",
    "options_research_permission",
    "final_route",
    "options_research_route",
    "options_research_score",
    "hard_vetoes",
    "options_hard_vetoes",
    "missing_data",
    "options_missing_data",
    "research_route_reason",
    "breakeven_feasibility",
    "estimated_R",
    "theta_decay_expected",
    "runway_to_wall_pct",
    "horizon_bucket",
    "hold_window",
    "hold_label",
    "exit_mode",
    "exit_scale_plan",
    "exit_t1",
    "exit_t2",
    "exit_t3",
    "exit_invalidation_price",
    "exit_plan_reason",
    "contract_quality_score",
    "contract_repair_status",
    "contract_repair_required",
    "contract_repair_reason",
    "contract_spread_pct_eod",
    "contract_oi",
    "contract_volume",
    "contract_delta",
    "l3_jump_risk_flag",
    "jump_risk_flag",
]

CATALYST_RECEIPT_FIELDS = [
    "catalyst_engine_version",
    "catalyst_detected",
    "catalyst_type",
    "catalyst_date",
    "days_to_catalyst",
    "catalyst_inside_dte",
    "catalyst_truth_score",
    "catalyst_binary_score",
    "catalyst_direction_bias",
    "catalyst_source_count",
    "catalyst_data_quality",
    "catalyst_trade_class",
    "event_convexity_score",
    "cheap_convexity_flag",
    "catalyst_liquidity_ok",
    "catalyst_alignment_label",
    "catalyst_reason_codes",
    "catalyst_source_fields",
    "catalyst_manual_upload",
    "catalyst_requires_live_confirmation",
    "catalyst_event_status",
    "catalyst_source_tier",
    "catalyst_source_url",
    "catalyst_ticker_role",
    "catalyst_expected_impact",
    "catalyst_failure_risk",
]

TRIGGER_RECEIPT_FIELDS = [
    "trigger_primary",
    "trigger_quality",
    "trigger_count",
    "trigger_score",
    "trigger_go_eligible",
    "trigger_codes",
]

BEHAVIOUR_RECEIPT_FIELDS = [
    "behaviour_state_key",
    "behaviour_state_hash",
    "actuarial_match_type",
    "actuarial_ev_weight",
    "catalyst_overlay",
]

MORNING_CONTEXT_FIELDS = [
    "morning_context_refreshed_at_utc",
    "morning_macro_source_path",
    "morning_macro_enrichment_source_path",
    "morning_macro_as_of_utc",
    "morning_macro_normalised_at_utc",
    "morning_macro_age_hours",
    "morning_macro_freshness_status",
    "morning_macro_data_quality",
    "morning_macro_regime_state",
    "morning_macro_dir_bias",
    "morning_macro_vol_mode",
    "morning_macro_risk_switch",
    "morning_macro_filter",
    "morning_macro_trigger_required",
    "morning_macro_horizon_action",
    "morning_macro_horizon_bias",
    "morning_macro_horizon_size_multiplier",
    "morning_macro_alignment_state",
    "morning_macro_direction_authority",
    "morning_macro_direction_vote",
    "morning_macro_confirmation_required",
    "morning_macro_interpretation_reason",
    "morning_macro_put_gate_permission",
    "morning_macro_requires_confirmation",
    "morning_macro_hard_block",
    "morning_macro_block_reason",
    "morning_bond_macro_flag",
    "morning_bond_macro_score",
    "morning_bond_curve_state",
    "morning_bond_zn_rate_regime_signal",
    "morning_bond_credit_warning",
    "morning_bond_auction_spread_risk",
    "morning_bond_breakeven_adjustment_pct",
    "morning_bond_summary",
    "morning_bond_generated_at",
    "morning_catalyst_source_path",
    "morning_catalyst_match",
    "morning_catalyst_status",
    "morning_catalyst_type",
    "morning_catalyst_date",
    "morning_catalyst_days_to_event",
    "morning_catalyst_inside_dte",
    "morning_catalyst_direction_bias",
    "morning_catalyst_execution_permission",
    "morning_catalyst_capital_grade",
    "morning_catalyst_needs_manual_confirmation",
    "morning_catalyst_hard_block",
    "morning_catalyst_block_reason",
    "morning_iv_rank",
    "morning_iv_rank_state",
    "morning_iv_rank_action",
    "morning_iv_rank_reason",
    "morning_iv_rank_source",
    "morning_iv_rank_confidence",
    "morning_iv_rank_score_cap",
    "morning_context_warnings",
    "macro_size_modifier",
    "morning_macro_fh_note",
]

OUTPUT_FIELDS = EVENING_FIELDS + LIVE_FIELDS + VALIDATION_FIELDS + EOD_RECEIPT_FIELDS + CATALYST_RECEIPT_FIELDS + TRIGGER_RECEIPT_FIELDS + BEHAVIOUR_RECEIPT_FIELDS + MORNING_CONTEXT_FIELDS + [
    "source_input_path",
    "source_input_mode",
    "source_payload_json",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _u(value: Any) -> str:
    return _s(value).upper()


def _f(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    text = _s(value).replace("$", "").replace("%", "").replace(",", "")
    if text.upper() in {"", "NONE", "NAN", "NULL", "N/A", "UNKNOWN", "MISSING"}:
        return default
    try:
        return float(text)
    except Exception:
        return default


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().upper() in {"", "NONE", "NAN", "NULL", "N/A", "UNKNOWN", "MISSING"}:
        return True
    return False

def _has_any_token(text: str, tokens: Iterable[str]) -> bool:
    text_u = str(text or "").upper()
    return any(str(token).upper() in text_u for token in tokens)

def _evening_reason_blob(row: Dict[str, Any]) -> str:
    keys = [
        "eod_candidate_status",
        "eod_candidate_reason",
        "eod_failure_class",
        "eod_dropoff_reason",
        "rejection_reason",
        "wait_reason",
        "hard_vetoes",
        "options_hard_vetoes",
        "contract_repair_reason",
        "signal_authority_reason",
        "execution_authority_reason",
    ]
    return " | ".join(_s(row.get(key)) for key in keys if _s(row.get(key))).upper()

def _evening_hard_veto_is_structural(row: Dict[str, Any]) -> bool:
    status = _u(row.get("eod_candidate_status") or row.get("eod_status"))
    blob = _evening_reason_blob(row)
    if status in {"EOD_THESIS_READY", "EOD_THESIS_READY_REPAIR_AT_OPEN", "EOD_TRIGGER_READY", "EOD_WATCHLIST_MONETISABLE", "EOD_PROBE_CANDIDATE", "EOD_DATA_INSUFFICIENT_REVIEW"}:
        return False
    if status in EOD_STRUCTURAL_HARD_STATUSES:
        return True
    if _has_any_token(blob, EOD_STRUCTURAL_HARD_TOKENS):
        return True
    if _has_any_token(blob, EOD_REPAIRABLE_TOKENS):
        return False
    return False


def first(row: Dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and not _is_missing(row.get(key)):
            return row.get(key)
    return default


def _json_safe(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, default=str)


def _parse_ts(value: Any) -> Optional[datetime]:
    text = _s(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _side(row: Dict[str, Any]) -> str:
    # Thesis side must come from the structural/canonical footprint first.
    # Contract side is an expression to repair, not authority to invert thesis.
    for key in (
        "canonical_direction",
        "resolved_direction",
        "footprint_direction",
        "direction",
        "evening_direction",
        "primary_direction",
        "option_direction",
        "options_direction",
        "instrument",
        "signal_type",
    ):
        side = _normalise_side(first(row, key))
        if side in {"CALL", "PUT"}:
            return side
    raw = _s(first(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction")).upper()
    return raw or "UNKNOWN"

def _normalise_side(value: Any) -> str:
    text = _u(value)
    if "PUT" in text or text in {"P", "BEARISH", "SHORT"}:
        return "PUT"
    if "CALL" in text or text in {"C", "BULLISH", "LONG"}:
        return "CALL"
    return ""


def _horizon_bucket(row: Dict[str, Any]) -> str:
    raw = _u(first(row, "horizon_bucket", "time_horizon", "hold_window", "hold_label", "opt__hold_label", "expected_horizon"))
    compact = raw.replace(" ", "").replace("-", "_")
    if any(token in compact for token in ("1_5", "1TO5", "1D_5D", "SHORT")):
        return "1_5D"
    if any(token in compact for token in ("6_10", "6TO10", "6D_10D", "MEDIUM")):
        return "6_10D"
    if any(token in compact for token in ("11_20", "11TO20", "11D_20D", "LONG")):
        return "11_20D"
    return raw or "UNKNOWN"


def _is_short_horizon(bucket: str) -> bool:
    return _u(bucket) in {"1_5D", "1-5D", "1_5", "SHORT", "SHORT_TERM"}


def _summarise_unlock(wait_reasons: Iterable[str], hard_veto: Iterable[str], contract_repair_needed: bool) -> str:
    if hard_veto:
        return "; ".join(hard_veto)
    if contract_repair_needed:
        return "Repair selected option contract, then revalidate spread, side, and breakeven"
    reasons = [r for r in wait_reasons if r]
    if not reasons:
        return "Ready for manual execution review"
    return "; ".join(reasons[:4])


def _lane_metadata(permission: str, *, contract_repair_needed: bool, wait_reasons: Iterable[str], hard_veto: Iterable[str]) -> Dict[str, str]:
    perm = _u(permission)
    lane_map = {
        "GO": ("GO_NOW", "Manual execute allowed now"),
        "GO_LIMIT": ("GO_LIMIT", "Manual limit order allowed; do not chase"),
        "PROBE": ("PROBE", "Manual starter/probe allowed with thesis invalidation respected"),
        "ARMED": ("ARMED_RETEST", "Keep armed; wait for cleaner live trigger"),
        "CONTRACT_REPAIR": ("CONTRACT_REPAIR", "Ticker thesis survives; repair option contract before entry"),
        "WAIT": ("WAIT", "Wait for trigger or cleaner tape"),
        "BLOCKED": ("STAND_DOWN", "Stand down"),
    }
    lane, action = lane_map.get(perm, ("WAIT", "Wait for clearer state"))
    return {
        "morning_execution_lane": lane,
        "morning_entry_action": action,
        "morning_unlock_condition": _summarise_unlock(wait_reasons, hard_veto, contract_repair_needed),
    }


def _preserve_options_research_permission(row: Dict[str, Any]) -> None:
    """Legacy no-op retained for older imports; Morning now writes its own action."""
    return None


def _set_morning_action(row: Dict[str, Any], permission: str, route: str) -> None:
    """Write explicit Morning Validator action fields while preserving legacy readers."""
    row["morning_execution_permission"] = permission
    row["morning_execution_route"] = route
    row["execution_permission"] = permission


def _spread_pct(value: Any, bid: Any = None, ask: Any = None, mid: Any = None) -> Optional[float]:
    spread = _f(value, None)
    if spread is not None and spread > 0:
        return spread * 100.0 if spread <= 1.0 else spread
    bid_f = _f(bid, None)
    ask_f = _f(ask, None)
    mid_f = _f(mid, None)
    if mid_f is None and bid_f is not None and ask_f is not None:
        mid_f = (bid_f + ask_f) / 2.0
    if bid_f is not None and ask_f is not None and mid_f and mid_f > 0 and ask_f >= bid_f:
        return (ask_f - bid_f) / mid_f * 100.0
    return None


def _normalise_iv_rank(value: Any) -> Optional[float]:
    iv_rank = _f(value, None)
    if iv_rank is None:
        return None
    if 0 <= iv_rank <= 1:
        iv_rank *= 100.0
    if iv_rank < 0:
        return None
    if iv_rank > 100:
        return 100.0
    return iv_rank


def _iv_rank_gate(row: Dict[str, Any]) -> Dict[str, Any]:
    iv_rank = _normalise_iv_rank(first(
        row,
        "iv_rank",
        "iv_rank_pct",
        "iv_percentile",
        "iv_percentile_1y",
        "options_iv_rank",
        "opt__iv_rank",
    ))
    source = first(row, "iv_rank_source", "options_iv_rank_source", "opt__iv_rank_source", default="")
    confidence = first(row, "iv_rank_confidence", "options_iv_rank_confidence", "opt__iv_rank_confidence", default="")

    if iv_rank is None:
        live_iv = _f(first(row, "live_iv", "contract_iv", "implied_vol", "opt__iv", default=None), None)
        if live_iv is not None:
            iv_pct = live_iv * 100.0 if 0 <= live_iv <= 3 else live_iv
            if iv_pct >= 85:
                state = "EXPENSIVE"
                action = "CAP_TO_PROBE_OR_ARMED"
                reason = f"IV rank missing; MarketData live IV proxy is expensive ({iv_pct:.1f}%)"
                cap = 72
            elif iv_pct >= 65:
                state = "ELEVATED"
                action = "CAP_GO_TO_LIMIT"
                reason = f"IV rank missing; MarketData live IV proxy is elevated ({iv_pct:.1f}%)"
                cap = 82
            elif iv_pct <= 30:
                state = "CHEAP"
                action = "ALLOW"
                reason = f"IV rank missing; MarketData live IV proxy is cheap/fair ({iv_pct:.1f}%)"
                cap = ""
            else:
                state = "NEUTRAL"
                action = "NO_GATE"
                reason = f"IV rank missing; MarketData live IV proxy is neutral ({iv_pct:.1f}%)"
                cap = ""
            return {
                "morning_iv_rank": "",
                "morning_iv_rank_state": state,
                "morning_iv_rank_action": action,
                "morning_iv_rank_reason": reason,
                "morning_iv_rank_source": source or "MARKETDATA_LIVE_IV_PROXY",
                "morning_iv_rank_confidence": confidence or "PROXY",
                "morning_iv_rank_score_cap": cap,
            }
        return {
            "morning_iv_rank": "",
            "morning_iv_rank_state": "UNKNOWN",
            "morning_iv_rank_action": "NO_GATE",
            "morning_iv_rank_reason": "IV rank missing; no IV-rank execution gate applied",
            "morning_iv_rank_source": source,
            "morning_iv_rank_confidence": confidence,
            "morning_iv_rank_score_cap": "",
        }

    if iv_rank >= 90:
        state = "EXTREME_EXPENSIVE"
        action = "ARMED_OR_REPAIR_ONLY"
        reason = "IV rank extremely expensive; do not chase long premium without contract repair or exceptional live confirmation"
        cap: Any = 69
    elif iv_rank >= 80:
        state = "EXPENSIVE"
        action = "PROBE_OR_ARMED_ONLY"
        reason = "IV rank expensive; cap execution to probe/armed unless premium structure improves"
        cap = 79
    elif iv_rank >= 65:
        state = "ELEVATED"
        action = "LIMIT_OR_PROBE_ONLY"
        reason = "IV rank elevated; require limit discipline and avoid chasing premium"
        cap = ""
    elif iv_rank <= 25:
        state = "CHEAP"
        action = "SUPPORTS_LONG_PREMIUM"
        reason = "IV rank cheap; supports long-premium thesis but does not override live confirmation"
        cap = ""
    else:
        state = "NEUTRAL"
        action = "NO_GATE"
        reason = "IV rank neutral; no execution-route adjustment"
        cap = ""

    return {
        "morning_iv_rank": round(iv_rank, 2),
        "morning_iv_rank_state": state,
        "morning_iv_rank_action": action,
        "morning_iv_rank_reason": reason,
        "morning_iv_rank_source": source,
        "morning_iv_rank_confidence": confidence,
        "morning_iv_rank_score_cap": cap,
    }


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(OUTPUT_FIELDS)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    try:
        import sys as _ma_sys
        _ma_sys.path.insert(0, r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter")
        from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
        _ma_on_pipeline_complete(str(path), output_dir=str(path.parent))
    except Exception as _ma_sync_err:
        log.warning("MA_Inputs sync skipped for %s: %s", path, _ma_sync_err)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")


def _read_json_path(path: Optional[Path]) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if not path or not Path(path).exists():
        return {}, [f"missing_json:{path}"]
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), warnings
    except Exception as exc:
        return {}, [f"json_load_failed:{path}:{type(exc).__name__}"]


def _resolve_context_path(explicit: Optional[str | Path], default_path: Path, pattern: str) -> Optional[Path]:
    if explicit:
        return Path(explicit)
    if default_path.exists():
        return default_path
    folder = default_path.parent
    matches = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
    return matches[0] if matches else default_path


def _boolish(value: Any) -> bool:
    return _u(value) in {"TRUE", "1", "YES", "Y", "BLOCKED", "NO_GO"}


def _date_cell(value: Any):
    text = _s(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _load_catalyst_index(path: Optional[Path]) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    warnings: List[str] = []
    if not path or not Path(path).exists():
        return {}, [f"missing_catalyst_calendar:{path}"]
    try:
        rows = _read_csv(Path(path))
    except Exception as exc:
        return {}, [f"catalyst_load_failed:{path}:{type(exc).__name__}"]
    index: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        ticker = _u(row.get("ticker"))
        if ticker:
            index.setdefault(ticker, []).append(row)
    return index, warnings


def _load_morning_context(
    macro_path: Optional[str | Path] = None,
    macro_enrichment_path: Optional[str | Path] = None,
    catalyst_calendar_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    resolved_macro = _resolve_context_path(macro_path, DEFAULT_MACRO_PATH, "macro_intelligence*.json")
    resolved_enrichment = _resolve_context_path(
        macro_enrichment_path,
        DEFAULT_MACRO_ENRICHMENT_PATH,
        "avshunter_macro_enrichment_delta*.json",
    )
    resolved_catalyst = _resolve_context_path(
        catalyst_calendar_path,
        DEFAULT_CATALYST_CALENDAR_PATH,
        "catalyst_calendar*.csv",
    )

    macro, macro_warnings = _read_json_path(resolved_macro)
    warnings.extend(macro_warnings)
    enrichment, enrichment_warnings = _read_json_path(resolved_enrichment)
    if enrichment:
        try:
            import sys as _ctx_sys

            repo = str(ROOT)
            if repo not in _ctx_sys.path:
                _ctx_sys.path.insert(0, repo)
            from contracts.macro_enrichment_delta import merge_macro_enrichment_delta  # type: ignore

            macro = merge_macro_enrichment_delta(macro, enrichment)
        except Exception as exc:
            warnings.append(f"macro_enrichment_merge_failed:{type(exc).__name__}:{exc}")
    else:
        warnings.extend(enrichment_warnings)

    try:
        import sys as _regime_sys

        repo = str(ROOT)
        if repo not in _regime_sys.path:
            _regime_sys.path.insert(0, repo)
        from contracts.macro_regime_safety import normalise_macro_regime_fields  # type: ignore

        macro = normalise_macro_regime_fields(macro)
    except Exception as exc:
        warnings.append(f"morning_macro_regime_normalise_failed:{type(exc).__name__}:{exc}")

    # Prefer clean split file (MACRO_SESSION_GUARD rows removed) when available
    if resolved_catalyst is not None:
        import logging as _cat_log
        _cat_logger = _cat_log.getLogger("avshunter.morning_validator")
        _clean_candidate = Path(str(resolved_catalyst)).parent / "catalyst_calendar_clean_latest.csv"
        if _clean_candidate.exists():
            _cat_logger.info("[CATALYST] Using clean split file: %s", _clean_candidate)
            resolved_catalyst = _clean_candidate
        else:
            _cat_logger.info("[CATALYST] Clean split not found — using original: %s", resolved_catalyst)
    catalyst_index, catalyst_warnings = _load_catalyst_index(resolved_catalyst)
    warnings.extend(catalyst_warnings)
    return {
        "loaded_at_utc": _utc_now(),
        "macro": macro,
        "macro_path": resolved_macro,
        "macro_enrichment_path": resolved_enrichment if enrichment else None,
        "catalyst_calendar_path": resolved_catalyst,
        "catalyst_index": catalyst_index,
        "warnings": warnings,
    }


def _macro_horizon_key(bucket: str) -> str:
    b = _u(bucket).replace("-", "_")
    if "1_5" in b:
        return "1_5d"
    if "6_10" in b:
        return "6_10d"
    if "11_20" in b:
        return "11_20d"
    return b.lower()


def _json_list_cell(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, default=str)


def _decision_context(macro: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import sys as _ctx_sys

        repo = str(ROOT)
        if repo not in _ctx_sys.path:
            _ctx_sys.path.insert(0, repo)
        from contracts.macro_enrichment_delta import interpret_macro_decision_context  # type: ignore

        return interpret_macro_decision_context(
            macro,
            ticker=_u(row.get("ticker")),
            direction=_side(row),
            gics_sector=_s(first(row, "gics_sector", "sector", "sector_name")),
        )
    except Exception as exc:
        return {
            "macro_alignment_state": "MACRO_CONTEXT_PARSE_FAILED",
            "macro_direction_authority": "DISABLED",
            "macro_direction_vote": "ABSTAIN",
            "macro_confirmation_required": [f"MACRO_CONTEXT_PARSE_FAILED:{type(exc).__name__}"],
            "macro_interpretation_reason": str(exc),
            "macro_filter": _s(macro.get("macro_filter")),
            "macro_trigger_required": bool(macro.get("trigger_required")),
            "macro_put_gate_permission": "",
        }


def _event_direction_side(value: Any) -> str:
    text = _u(value)
    if "PUT" in text or "SHORT" in text or "BEAR" in text or "VULNERABLE" in text:
        return "PUT"
    if "CALL" in text or "LONG" in text or "BULL" in text or "BENEFICIARY" in text:
        return "CALL"
    return ""


def _select_catalyst_event(events: List[Dict[str, Any]], dte: Optional[float]) -> Optional[Dict[str, Any]]:
    if not events:
        return None
    today = datetime.now(timezone.utc).date()

    def sort_key(row: Dict[str, Any]) -> Tuple[int, int]:
        event_date = _date_cell(first(row, "catalyst_date", "event_date", "date"))
        start = _date_cell(row.get("event_window_start")) or event_date
        end = _date_cell(row.get("event_window_end")) or event_date
        active = bool(start and end and start <= today <= end)
        if event_date:
            days = (event_date - today).days
        elif start:
            days = (start - today).days
        else:
            days = 9999
        inside = active or (dte is not None and 0 <= days <= int(dte))
        return (0 if inside else 1, abs(days))

    return sorted(events, key=sort_key)[0]


def _apply_morning_context(row: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    warnings = list(context.get("warnings") or [])
    macro = context.get("macro") or {}
    macro_quant = macro.get("macro_quant_packet") if isinstance(macro.get("macro_quant_packet"), dict) else {}
    ticker = _u(out.get("ticker"))
    side = _side(out)
    horizon_key = _macro_horizon_key(_horizon_bucket(out))
    horizon = macro.get("horizon_routing", {}).get(horizon_key, {}) if isinstance(macro.get("horizon_routing"), dict) else {}
    decision = _decision_context(macro, out) if macro else {}
    confirmations = decision.get("macro_confirmation_required") or []
    alignment = _u(decision.get("macro_alignment_state"))
    authority = _u(decision.get("macro_direction_authority"))
    macro_filter = _u(macro.get("macro_filter") or decision.get("macro_filter"))
    put_gate = _u(decision.get("macro_put_gate_permission"))
    horizon_action = _u(horizon.get("action"))
    trigger_required = bool(macro.get("trigger_required") or decision.get("macro_trigger_required"))
    freshness = _u(macro_quant.get("macro_freshness_status"))
    bond_flag = _u(first(macro, "bond_macro_flag", default=""))
    bond_score = first(macro, "bond_macro_score", default="")
    bond_adj = _f(first(macro, "breakeven_adjustment_pct", default=0.0), 0.0) or 0.0
    bond_adj = max(0.0, min(50.0, bond_adj))
    bond_auction_spread_risk = _u(first(macro, "auction_spread_risk", default="")) in {"1", "TRUE", "YES", "Y"}
    bond_credit_warning = _u(first(macro, "credit_warning", default="")) in {"1", "TRUE", "YES", "Y"}

    # MACRO REDESIGN: Fung-Hsieh is a size modifier only.
    # macro_filter = NO_GO reduces size and abstains direction. Does NOT block.
    _fh_sub_threshold = (macro_filter == "NO_GO")
    if _fh_sub_threshold:
        _macro_size_modifier = round(_f(macro.get("size_multiplier"), 0.5) * 0.7, 4)
        _morning_macro_direction_authority = "ABSTAIN"
        _morning_macro_fh_note = (
            "Fung-Hsieh sub-0.50: size reduced to "
            f"{_macro_size_modifier}x. Direction abstains. "
            "Ticker verdict unaffected."
        )
    else:
        _macro_size_modifier = _f(macro.get("size_multiplier"), 1.0)
        _morning_macro_direction_authority = authority or "ENABLED"
        _morning_macro_fh_note = ""

    hard_reasons: List[str] = []
    requires_confirmation = False
    if "NO_NEW_POSITIONS" in horizon_action or horizon_action in {"BLOCK", "NO_GO"}:
        hard_reasons.append(f"Fresh macro horizon gate blocks {horizon_key}: {horizon.get('action')}")
    if side == "PUT" and put_gate in {"BLOCKED", "NO_GO"}:
        hard_reasons.append("Fresh macro put gate blocks PUT thesis")
    if authority == "ENABLED" and alignment in {"MACRO_CONFLICTS_PUT", "MACRO_CONFLICTS_CALL"}:
        hard_reasons.append(f"Fresh macro direction conflicts with {side} thesis")
    if confirmations or trigger_required:
        requires_confirmation = True
    if freshness == "STALE":
        requires_confirmation = True
        warnings.append("macro_freshness_status:STALE")
    if alignment in {"MACRO_CONFLICTS_PUT", "MACRO_CONFLICTS_CALL", "PUT_ELEVATED_CONFIRMATION", "CALL_ELEVATED_CONFIRMATION"}:
        requires_confirmation = True
    if bond_adj > 0:
        warnings.append(f"bond_macro_breakeven_adjustment_pct:{bond_adj:g}")
    if bond_auction_spread_risk:
        warnings.append("bond_macro_auction_spread_risk")
        requires_confirmation = True
    if bond_credit_warning:
        warnings.append("bond_macro_credit_warning")
        requires_confirmation = True
    if bond_flag in {"BOND_MACRO_WARNING", "BOND_MACRO_ADVERSE"}:
        warnings.append(f"bond_macro_flag:{bond_flag}")
        requires_confirmation = True

    out.update(
        {
            "morning_context_refreshed_at_utc": context.get("loaded_at_utc", ""),
            "morning_macro_source_path": str(context.get("macro_path") or ""),
            "morning_macro_enrichment_source_path": str(context.get("macro_enrichment_path") or ""),
            "morning_macro_as_of_utc": first(macro, "as_of_utc", "report_date", default="") if macro else "",
            "morning_macro_normalised_at_utc": first(macro_quant, "macro_normalised_at_utc", default="") if macro_quant else first(macro, "normalised_at_utc", default=""),
            "morning_macro_age_hours": first(macro_quant, "macro_age_hours", default=""),
            "morning_macro_freshness_status": first(macro_quant, "macro_freshness_status", default=""),
            "morning_macro_data_quality": first(macro_quant, "macro_data_quality", default=""),
            "morning_macro_regime_state": first(macro, "regime_state", "regime_label", default=""),
            "morning_macro_dir_bias": first(macro, "dir_bias", default=""),
            "morning_macro_vol_mode": first(macro, "vol_mode", default=""),
            "morning_macro_risk_switch": first(macro, "risk_on_off_switch", default=""),
            "morning_macro_filter": first(macro, "macro_filter", default=""),
            "morning_macro_trigger_required": "TRUE" if trigger_required else "FALSE",
            "morning_macro_horizon_action": horizon.get("action", "") if isinstance(horizon, dict) else "",
            "morning_macro_horizon_bias": horizon.get("bias", "") if isinstance(horizon, dict) else "",
            "morning_macro_horizon_size_multiplier": horizon.get("size_multiplier", "") if isinstance(horizon, dict) else "",
            "morning_macro_alignment_state": decision.get("macro_alignment_state", ""),
            "morning_macro_direction_authority": _morning_macro_direction_authority,
            "morning_macro_direction_vote": decision.get("macro_direction_vote", ""),
            "morning_macro_confirmation_required": _json_list_cell(confirmations),
            "morning_macro_interpretation_reason": decision.get("macro_interpretation_reason", ""),
            "morning_macro_put_gate_permission": put_gate,
            "morning_macro_requires_confirmation": "TRUE" if requires_confirmation else "FALSE",
            "morning_macro_hard_block": "TRUE" if hard_reasons else "FALSE",
            "morning_macro_block_reason": "; ".join(hard_reasons),
            "morning_bond_macro_flag": bond_flag,
            "morning_bond_macro_score": bond_score,
            "morning_bond_curve_state": _u(first(macro, "curve_state", default="")),
            "morning_bond_zn_rate_regime_signal": _u(first(macro, "zn_rate_regime_signal", default="")),
            "morning_bond_credit_warning": "TRUE" if bond_credit_warning else "FALSE",
            "morning_bond_auction_spread_risk": "TRUE" if bond_auction_spread_risk else "FALSE",
            "morning_bond_breakeven_adjustment_pct": bond_adj,
            "morning_bond_summary": first(macro, "bond_macro_summary", default=""),
            "morning_bond_generated_at": first(macro, "bond_macro_generated_at", default=""),
            "macro_size_modifier": _macro_size_modifier,
            "morning_macro_fh_note": _morning_macro_fh_note,
        }
    )

    catalyst_index = context.get("catalyst_index") or {}
    events = catalyst_index.get(ticker, []) if isinstance(catalyst_index, dict) else []
    dte = _f(first(out, "evening_dte", "dte", "contract_dte", "opt__contract_dte"), None)
    event = _select_catalyst_event(events, dte)
    catalyst_hard: List[str] = []
    if event:
        today = datetime.now(timezone.utc).date()
        event_date = _date_cell(first(event, "catalyst_date", "event_date", "date"))
        start = _date_cell(event.get("event_window_start")) or event_date
        end = _date_cell(event.get("event_window_end")) or event_date
        if event_date:
            days = (event_date - today).days
        elif start:
            days = (start - today).days
        else:
            days = None
        active_window = bool(start and end and start <= today <= end)
        inside_dte = bool(active_window or (dte is not None and days is not None and 0 <= days <= int(dte)))
        catalyst_type = _s(first(event, "catalyst_type", "event_type"))
        event_side = _event_direction_side(first(event, "catalyst_direction_bias", "ticker_role"))
        exec_perm = _u(event.get("execution_permission"))
        capital_grade = _u(event.get("capital_grade"))
        needs_manual = _boolish(event.get("needs_manual_confirmation"))
        if "EARN" in _u(catalyst_type) and inside_dte:
            catalyst_hard.append("Fresh catalyst calendar: earnings inside option DTE window")
        direction_conflict = bool(event_side and side in {"CALL", "PUT"} and event_side != side)
        out.update(
            {
                "morning_catalyst_source_path": str(context.get("catalyst_calendar_path") or ""),
                "morning_catalyst_match": "TRUE",
                "morning_catalyst_status": first(event, "catalyst_status", "event_status", default=""),
                "morning_catalyst_type": catalyst_type,
                "morning_catalyst_date": first(event, "catalyst_date", "event_date", "date", default=""),
                "morning_catalyst_days_to_event": "" if days is None else days,
                "morning_catalyst_inside_dte": "TRUE" if inside_dte else "FALSE",
                "morning_catalyst_direction_bias": first(event, "catalyst_direction_bias", "ticker_role", default=""),
                "morning_catalyst_execution_permission": exec_perm,
                "morning_catalyst_capital_grade": capital_grade,
                "morning_catalyst_needs_manual_confirmation": "TRUE" if needs_manual else "FALSE",
                "morning_catalyst_hard_block": "TRUE" if catalyst_hard else "FALSE",
                "morning_catalyst_block_reason": "; ".join(catalyst_hard),
                "catalyst_detected": "TRUE",
                "catalyst_type": catalyst_type,
                "catalyst_date": first(event, "catalyst_date", "event_date", "date", default=""),
                "days_to_catalyst": "" if days is None else days,
                "catalyst_inside_dte": "TRUE" if inside_dte else "FALSE",
                "catalyst_binary_score": first(event, "catalyst_binary_score", default=out.get("catalyst_binary_score", "")),
                "catalyst_direction_bias": first(event, "catalyst_direction_bias", default=out.get("catalyst_direction_bias", "")),
                "catalyst_source_count": first(event, "source_count", default=out.get("catalyst_source_count", "")),
                "catalyst_data_quality": first(event, "date_quality", default=out.get("catalyst_data_quality", "")),
                "catalyst_source_tier": first(event, "source_tier", default=out.get("catalyst_source_tier", "")),
                "catalyst_source_url": first(event, "source_url", default=out.get("catalyst_source_url", "")),
                "catalyst_ticker_role": first(event, "ticker_role", default=out.get("catalyst_ticker_role", "")),
                "catalyst_failure_risk": first(event, "failure_risk", default=out.get("catalyst_failure_risk", "")),
            }
        )
        soft_warnings = []
        if needs_manual:
            soft_warnings.append("catalyst_requires_manual_confirmation")
        if exec_perm.startswith("NONE") or capital_grade == "NO":
            soft_warnings.append("catalyst_no_capital_grade")
        if direction_conflict:
            soft_warnings.append("catalyst_direction_conflict")
        warnings.extend(soft_warnings)
    else:
        out.update(
            {
                "morning_catalyst_source_path": str(context.get("catalyst_calendar_path") or ""),
                "morning_catalyst_match": "FALSE",
                "morning_catalyst_hard_block": "FALSE",
            }
        )

    out["morning_context_warnings"] = "; ".join(dict.fromkeys(warnings))
    return out


def latest_run_id(runs_dir: Path = RUNS_DIR) -> Optional[str]:
    latest = runs_dir.parent / "latest.json"
    if latest.exists():
        try:
            payload = json.loads(latest.read_text(encoding="utf-8-sig"))
            rid = payload.get("run_id") or payload.get("latest_run_id")
            if rid:
                return str(rid)
        except Exception:
            pass
    if not runs_dir.exists():
        return None
    dirs = [p.name for p in runs_dir.iterdir() if p.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def find_candidate_source(
    run_id: str,
    runs_dir: Path = RUNS_DIR,
    candidates_path: Optional[Path] = None,
) -> Tuple[Optional[Path], str]:
    run_dir = runs_dir / run_id
    final_book = run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv"
    morning_candidates = run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"
    fallbacks = [
        (candidates_path, "EXPLICIT_CANDIDATES") if candidates_path else (None, ""),
        (morning_candidates, "MORNING_CANDIDATES"),
        (final_book, "FINAL_OPPORTUNITY_BOOK"),
        (run_dir / "superbrain" / f"eil_enriched_{run_id}.csv", "EIL_DEGRADED"),
        (run_dir / "execution" / f"execution_v3_5_{run_id}.csv", "EXECUTION_DEGRADED"),
        (run_dir / "options" / f"options_intelligence_{run_id}.csv", "OPTIONS_DEGRADED"),
        (run_dir / "superbrain" / f"AVSHUNTER_SIGNALS_V5_{run_id}.csv", "V5_DEGRADED"),
    ]
    for path, mode in fallbacks:
        if path and Path(path).exists():
            return Path(path), mode
    return None, "MISSING"


def _passes_tier(row: Dict[str, Any], tier_filter: Optional[str]) -> bool:
    if not tier_filter:
        return True
    allowed = {t.strip().upper() for t in str(tier_filter).split(",") if t.strip()}
    if not allowed:
        return True
    tier = _u(first(row, "structural_tier", "tier", "tier_label"))
    return tier in allowed


def _has_blocked_options_route(row: Dict[str, Any]) -> bool:
    route = _u(first(row, "final_route", "options_research_route", "options_final_route"))
    severity = _u(row.get("block_severity"))
    hard_vetoes = _s(first(row, "hard_vetoes", "options_hard_vetoes"))
    return bool(
        route in {"OPTIONS_BLOCKED", "OPTIONS_EQUITY_ONLY_BETTER"}
        or severity == "HARD"
        or hard_vetoes
    )


def select_candidates(
    rows: Iterable[Dict[str, Any]],
    max_signals: int = 0,
    tier_filter: Optional[str] = None,
    include_high_priority_wait: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    status_order = {
        "EOD_THESIS_READY": 0,
        "EOD_THESIS_READY_REPAIR_AT_OPEN": 1,
        "EOD_TRIGGER_READY": 2,
        "EOD_PROBE_CANDIDATE": 3,
        "EOD_WATCHLIST_MONETISABLE": 4,
        "EOD_DATA_INSUFFICIENT_REVIEW": 5,
        "EOD_CATALYST_EXECUTE_CANDIDATE": 0,
        "EOD_EXECUTE_CANDIDATE": 1,
        "EOD_EXECUTE_WITH_CAUTION": 2,
        "EOD_CONTRACT_REPAIR_REQUIRED": 3,
        "EOD_TRIGGER_READY_REVIEW": 4,
        "EOD_CATALYST_WATCH": 5,
        "": 5,
    }
    tier_order = {"A": 0, "B": 1, "C": 2, "WATCH": 3}
    for row in rows:
        if not _passes_tier(row, tier_filter):
            continue
        if _has_blocked_options_route(row):
            continue
        verdict = _u(first(row, "lab_verdict", "evening_lab_verdict", "candidate_status", "morning_status", "thesis_decision"))
        eod_status = _u(row.get("eod_candidate_status"))
        priority = _f(first(row, "priority_score", "evening_priority_score", "scs_score", "composite"), 0.0) or 0.0
        if verdict in {"GO", "ARMED", "READY_FOR_VALIDATION", "READY", "READY_EXECUTE"}:
            out.append(row)
        elif eod_status in status_order and eod_status:
            out.append(row)
        elif include_high_priority_wait and verdict in {"WAIT", "WATCH", "WATCHLIST"} and priority >= 80:
            out.append(row)
    out.sort(
        key=lambda row: (
            status_order.get(_u(row.get("eod_candidate_status")), 9),
            tier_order.get(_u(first(row, "structural_tier", "tier", "tier_label")), 9),
            -(_f(first(row, "priority_score", "evening_priority_score", "scs_score", "composite"), 0.0) or 0.0),
        )
    )
    if max_signals:
        out = out[:max_signals]
    return out


def normalise_evening_candidate(row: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    side = _side(row)
    lab_verdict = _u(first(row, "lab_verdict", "evening_lab_verdict", "candidate_status", "morning_status", "thesis_decision"))
    eod_status = _u(row.get("eod_candidate_status"))
    if lab_verdict in {"READY_FOR_VALIDATION", "READY", "READY_EXECUTE"}:
        lab_verdict = "ARMED"
    if eod_status in {
        *EOD_CARRY_FORWARD_STATUSES,
    } and lab_verdict in {"", "WAIT", "WATCH", "WATCHLIST"}:
        lab_verdict = "ARMED"
    if not lab_verdict:
        lab_verdict = "WAIT"
    ticker = _u(row.get("ticker"))
    strike = first(row, "strike", "contract_strike", "opt__contract_strike", "evening_strike")
    expiry = first(row, "expiry", "contract_expiry", "opt__contract_expiry", "evening_expiry")
    trade_idea_id = first(row, "trade_idea_id", default="")
    if not trade_idea_id:
        trade_idea_id = f"{run_id}:{ticker}:{side}:{_s(strike) or 'NA'}:{_s(expiry) or 'NA'}"
    out = dict(row)
    out.update(
        {
            "run_id": run_id,
            "ticker": ticker,
            "trade_idea_id": trade_idea_id,
            "evening_lab_verdict": lab_verdict,
            "evening_direction": side,
            "evening_contract_symbol": first(row, "contract_symbol", "option_symbol", "recommended_contract", "opt__recommended_contract", "evening_contract_symbol"),
            "evening_strike": strike,
            "evening_expiry": expiry,
            "evening_dte": first(row, "dte", "contract_dte", "opt__contract_dte", "evening_dte"),
            "evening_premium_mid": first(row, "premium_mid", "premium_eod", "contract_premium", "entry_premium", "opt__premium_mid", "opt__contract_premium", "evening_premium_mid"),
            "evening_target_price": first(row, "target_price", "target", "structural_target", "evening_target_price"),
            "evening_invalidation_price": first(row, "invalidation_price", "invalidation_level", "stop_price", "evening_invalidation_price"),
            "evening_physics_state_id": first(row, "physics_state_id", "evening_physics_state_id"),
            "evening_hidden_state_label": first(row, "hidden_state_label", "evening_hidden_state_label"),
            "evening_state_transition_label": first(row, "state_transition_label", "evening_state_transition_label"),
            "evening_phase_transition_probability": first(row, "phase_transition_probability", "evening_phase_transition_probability"),
            "evening_priority_score": first(row, "priority_score", "scs_score", "composite", "evening_priority_score"),
            "evening_rr_predicted": first(row, "rr_predicted", "rr_options", "rr", "option_rr", "evening_rr_predicted"),
            "evening_ev_predicted": first(row, "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "ev", "evening_ev_predicted"),
            "evening_win_prob_predicted": first(row, "win_prob_predicted", "ev2_p_win_blended", "win_rate_20d", "win_rate_10d", "evening_win_prob_predicted"),
        }
    )
    return out


def _paper_live_snapshot(candidate: Dict[str, Any]) -> Dict[str, Any]:
    side = _side(candidate)
    price = _f(first(candidate, "live_price", "current_price", "spot_price", "underlying_price", "signal_price"), None)
    if price is None or price <= 0:
        strike = _f(first(candidate, "evening_strike", "strike", "contract_strike"), None)
        price = strike if strike and strike > 0 else None
    if price is None or price <= 0:
        return {}
    if side == "PUT":
        vwap = price * 1.003
        orb_high = price * 1.008
        orb_low = price * 1.002
    else:
        vwap = price * 0.997
        orb_high = price * 0.998
        orb_low = price * 0.992
    premium = _f(first(candidate, "evening_premium_mid", "premium_mid", "premium_eod", "contract_premium"), 1.0) or 1.0
    bid = max(premium * 0.97, 0.01)
    ask = max(premium * 1.03, bid + 0.01)
    mid = (bid + ask) / 2.0
    return {
        "live_price": price,
        "live_bid": price * 0.999,
        "live_ask": price * 1.001,
        "live_mid": price,
        "live_volume": _f(first(candidate, "volume", "avg_volume"), 100000.0),
        "live_vwap": vwap,
        "live_open": price * 0.996 if side != "PUT" else price * 1.004,
        "live_high": max(price, orb_high) * 1.002,
        "live_low": min(price, orb_low) * 0.998,
        "live_prev_close": price * 0.99 if side != "PUT" else price * 1.01,
        "live_orb_high": orb_high,
        "live_orb_low": orb_low,
        "live_contract_bid": bid,
        "live_contract_ask": ask,
        "live_contract_mid": mid,
        "live_contract_volume": _f(first(candidate, "live_contract_volume", "option_volume"), 100.0),
        "live_contract_open_interest": _f(first(candidate, "live_contract_open_interest", "open_interest"), 500.0),
        "live_iv": first(candidate, "live_iv", "iv", "opt__iv", default=""),
        "live_delta": first(candidate, "live_delta", "delta", "opt__delta", default=""),
        "live_gamma": first(candidate, "live_gamma", "gamma", default=""),
        "live_theta": first(candidate, "live_theta", "theta", default=""),
        "live_data_timestamp_utc": _utc_now(),
    }


def _fetch_live_snapshot(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort live adapter around the existing morning validation helpers."""
    ticker = _u(candidate.get("ticker"))
    if not ticker:
        return {}
    live: Dict[str, Any] = {}
    try:
        from morning_validation import (  # type: ignore
            _build_occ_symbol,
            _marketdata_quote,
            _marketdata_stock_quote,
            _polygon_intraday_bars,
            _polygon_snapshot,
        )
    except ImportError as e:
        log.warning(
            "_fetch_live_snapshot: cannot import options helpers - %s. "
            "Check that morning_validation.py exists in the same directory.",
            e,
        )
        return live
    except Exception as e:
        log.warning("_fetch_live_snapshot: helper import failed unexpectedly - %s", e)
        return live

    try:
        occ_row = {
            "ticker": ticker,
            "direction": candidate.get("evening_direction") or candidate.get("direction"),
            "expiry": candidate.get("evening_expiry") or candidate.get("expiry"),
            "strike": candidate.get("evening_strike") or candidate.get("strike"),
        }
        occ = (
            candidate.get("evening_contract_symbol")
            or candidate.get("contract_occ_symbol")
            or candidate.get("recommended_contract")
            or candidate.get("preferred_contract")
            or candidate.get("contract_symbol")
            or _build_occ_symbol(occ_row)
        )
        results: Dict[str, Any] = {}

        # Fetch equity context first, then price the option contract separately.
        # This keeps MarketData.app option requests from competing with equity quote calls.
        eq_tasks = {}
        with ThreadPoolExecutor(max_workers=3) as eq_executor:
            eq_tasks[eq_executor.submit(_marketdata_stock_quote, ticker)] = "stock"
            eq_tasks[eq_executor.submit(_polygon_snapshot, ticker)] = "prev"
            eq_tasks[eq_executor.submit(_polygon_intraday_bars, ticker, 5, 20)] = "bars"
            done, pending = wait(eq_tasks, timeout=LIVE_FETCH_TIMEOUT_SEC)
            for future in pending:
                future.cancel()
            for future in done:
                key = eq_tasks.get(future, "")
                try:
                    results[key] = future.result() or ([] if key == "bars" else {})
                except Exception:
                    results[key] = [] if key == "bars" else {}

        if occ:
            opt_result = None
            try:
                opt_result = _marketdata_quote(occ)
            except Exception:
                opt_result = None
            if not opt_result:
                time.sleep(1.0)
                try:
                    opt_result = _marketdata_quote(occ)
                except Exception:
                    opt_result = None
            results["option"] = opt_result or {}

        stock = results.get("stock") or {}
        prev = results.get("prev") or {}
        bars = results.get("bars") or []
        opt = results.get("option") or {}
        price = stock.get("price") or stock.get("mid")
        if bars:
            total_vol = sum(_f(b.get("volume"), 0.0) or 0.0 for b in bars)
            weighted = sum((_f(b.get("close"), 0.0) or 0.0) * (_f(b.get("volume"), 0.0) or 0.0) for b in bars)
            vwap = weighted / total_vol if total_vol > 0 else None
            first_three = bars[:3]
            orb_highs = [x for x in (_f(b.get("high"), None) for b in first_three) if x is not None]
            orb_lows = [x for x in (_f(b.get("low"), None) for b in first_three) if x is not None]
            orb_high = max(orb_highs) if orb_highs else None
            orb_low = min(orb_lows) if orb_lows else None
            live.update(
                {
                    "live_open": bars[0].get("open"),
                    "live_high": max((_f(b.get("high"), 0.0) or 0.0 for b in bars), default=""),
                    "live_low": min((_f(b.get("low"), 0.0) or 0.0 for b in bars), default=""),
                    "live_volume": total_vol or stock.get("volume"),
                    "live_vwap": vwap or stock.get("vwap") or prev.get("prev_vwap"),
                    "live_orb_high": orb_high,
                    "live_orb_low": orb_low,
                }
            )
        live.update(
            {
                "live_price": price,
                "live_bid": stock.get("bid"),
                "live_ask": stock.get("ask"),
                "live_mid": stock.get("mid") or price,
                "live_prev_close": prev.get("prev_close"),
                "live_data_timestamp_utc": _utc_now(),
            }
        )
        if opt:
            live.update(
                {
                    "live_contract_bid": opt.get("bid"),
                    "live_contract_ask": opt.get("ask"),
                    "live_contract_mid": opt.get("mid"),
                    "live_contract_volume": opt.get("volume"),
                    "live_contract_open_interest": opt.get("open_interest") or opt.get("openInterest"),
                    "live_iv": opt.get("iv"),
                    "live_delta": opt.get("delta"),
                    "live_gamma": opt.get("gamma"),
                    "live_theta": opt.get("theta"),
                    "live_vega": opt.get("vega"),
                    "live_options_data_source": opt.get("source") or "MARKETDATA_OPTIONS_QUOTE",
                    "live_options_data_freshness": opt.get("freshness") or "LIVE_OR_CACHED",
                    "live_options_quote_timestamp_utc": opt.get("updated") or _utc_now(),
                    "live_options_provider_status": opt.get("http_status") or "",
                }
            )
        live.setdefault("live_equity_data_source", "MARKETDATA_STOCK_QUOTE_PLUS_POLYGON_EQUITY_BARS")
        if occ:
            live.setdefault("live_options_data_source", "MARKETDATA_OPTIONS_QUOTE_MISSING")
            live.setdefault("live_options_data_freshness", "MISSING")
        live.setdefault("live_data_timestamp_utc", _utc_now())
    except Exception as e:
        log.warning("_fetch_live_snapshot: live quote fetch failed for %s - %s", ticker, e)
        return live
    return {k: v for k, v in live.items() if not _is_missing(v)}


def _merge_live_fields(candidate: Dict[str, Any], live_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    live = dict(live_data or {})
    for key in LIVE_FIELDS:
        if key not in live and not _is_missing(candidate.get(key)):
            live[key] = candidate.get(key)
    bid = live.get("live_bid")
    ask = live.get("live_ask")
    mid = live.get("live_mid")
    live["live_spread_pct"] = _spread_pct(live.get("live_spread_pct"), bid, ask, mid)
    cbid = live.get("live_contract_bid")
    cask = live.get("live_contract_ask")
    cmid = live.get("live_contract_mid")
    live["live_contract_spread_pct"] = _spread_pct(live.get("live_contract_spread_pct"), cbid, cask, cmid)
    price = _f(live.get("live_price"), None)
    vwap = _f(live.get("live_vwap"), None)
    if price is not None and vwap and vwap > 0:
        live["live_distance_to_vwap_pct"] = (price - vwap) / vwap * 100.0
    prev = _f(live.get("live_prev_close"), None)
    if price is not None and prev and prev > 0:
        live["live_gap_pct"] = (price - prev) / prev * 100.0
    return live


def _bool_text(value: Any) -> str:
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    return "UNKNOWN"


def _physics_check(label: str, side: str, price: Optional[float], vwap: Optional[float], orb_high: Optional[float], orb_low: Optional[float]) -> Tuple[Any, str]:
    label_u = _u(label)
    if price is None:
        return "UNKNOWN", "No live price for physics comparison"
    midpoint = (orb_high + orb_low) / 2.0 if orb_high is not None and orb_low is not None else None
    if "NO_TRANSITION_EDGE" in label_u or "LOW_ENERGY_NO_EDGE" in label_u:
        return "WAIT", "No evening physics transition edge - live trigger required before capital"
    if "CHOP_CONTINUATION" in label_u or "COMPRESSED_BALANCED" in label_u:
        if side == "CALL" and vwap and orb_high and price > vwap and price > orb_high:
            return True, "Chop continuation confirmed by upside expansion above VWAP and ORB high"
        if side == "PUT" and vwap and orb_low and price < vwap and price < orb_low:
            return True, "Chop continuation confirmed by downside expansion below VWAP and ORB low"
        if side == "CALL" and vwap and price < vwap and (midpoint is None or price < midpoint):
            return False, "Chop continuation failed below VWAP"
        if side == "PUT" and vwap and price > vwap and (midpoint is None or price > midpoint):
            return False, "Chop continuation failed above VWAP"
        return "WAIT", "Chop continuation needs decisive opening expansion"
    if "HIGH_ENTROPY_CHOP" in label_u:
        if side == "CALL" and vwap and orb_high and price > vwap and price > orb_high:
            return True, "High entropy thesis confirmed only by decisive upside expansion"
        if side == "PUT" and vwap and orb_low and price < vwap and price < orb_low:
            return True, "High entropy thesis confirmed only by decisive downside expansion"
        return "WAIT", "High entropy setup requires stronger confirmation"
    if "BALANCE_TO_UPSIDE_EXPANSION" in label_u:
        if vwap and orb_high and price > vwap and price > orb_high:
            return True, "Upside expansion confirmed above VWAP and ORB high"
        if vwap and price < vwap and (midpoint is None or price < midpoint):
            return False, "Upside expansion failed below VWAP"
        return "WAIT", "Upside expansion has not broken yet"
    if "BALANCE_TO_DOWNSIDE_EXPANSION" in label_u:
        if vwap and orb_low and price < vwap and price < orb_low:
            return True, "Downside expansion confirmed below VWAP and ORB low"
        if vwap and price > vwap and (midpoint is None or price > midpoint):
            return False, "Downside expansion failed above VWAP"
        return "WAIT", "Downside expansion has not broken yet"
    if "CONTINUATION_UP" in label_u:
        if vwap and price > vwap:
            return True, "Continuation up still holds above VWAP"
        if vwap and price < vwap and (midpoint is None or price < midpoint):
            return False, "Continuation up failed VWAP"
        return "WAIT", "Continuation up needs retest"
    if "CONTINUATION_DOWN" in label_u:
        if vwap and price < vwap:
            return True, "Continuation down still holds below VWAP"
        if vwap and price > vwap and (midpoint is None or price > midpoint):
            return False, "Continuation down failed VWAP"
        return "WAIT", "Continuation down needs retest"
    return "UNKNOWN", "No explicit physics transition mapping"


def validate_candidate(
    candidate: Dict[str, Any],
    live_data: Optional[Dict[str, Any]] = None,
    *,
    pipeline_mode: str = "MORNING_VALIDATION",
    quote_stale_minutes: int = 15,
) -> Dict[str, Any]:
    validation_ts = _utc_now()
    row = normalise_evening_candidate(candidate, _s(candidate.get("run_id")) or "manual")
    row["validation_timestamp_utc"] = validation_ts

    # FIX 9: Explicitly preserve crowd_arrival and WBS fields from candidate row.
    # normalise_evening_candidate() starts from dict(candidate) so these fields
    # are already present; this block guards against any future reconstruct-from-scratch.
    PRESERVE_FIELDS = [
        "crowd_arrival_components",
        "crowd_arrival_state",
        "crowd_arrival_narrative",
        "wbs_score",
        "wbs_grade",
        "wall_break_score",
    ]
    for _pf in PRESERVE_FIELDS:
        if _pf in candidate and candidate[_pf]:
            row.setdefault(_pf, candidate[_pf])

    live = _merge_live_fields(row, live_data)
    for key in LIVE_FIELDS:
        row[key] = live.get(key, "")

    side = _side(row)
    horizon_bucket = _horizon_bucket(row)
    row["horizon_bucket"] = first(row, "horizon_bucket", default=horizon_bucket) or horizon_bucket
    evening_verdict = _u(row.get("evening_lab_verdict"))
    price = _f(live.get("live_price"), None)
    vwap = _f(live.get("live_vwap"), None)
    orb_high = _f(live.get("live_orb_high"), None)
    orb_low = _f(live.get("live_orb_low"), None)
    target = _f(row.get("evening_target_price"), None)
    invalidation = _f(row.get("evening_invalidation_price"), None)
    premium = _f(first(row, "live_contract_mid", "evening_premium_mid"), None)
    strike = _f(row.get("evening_strike"), None)
    live_contract_spread = _spread_pct(row.get("live_contract_spread_pct"), row.get("live_contract_bid"), row.get("live_contract_ask"), row.get("live_contract_mid"))
    row["live_contract_spread_pct"] = "" if live_contract_spread is None else round(live_contract_spread, 4)
    eod_status = _u(row.get("eod_candidate_status") or row.get("eod_status"))
    contract_repair_required = (
        _u(row.get("contract_repair_required")) in {"TRUE", "1", "YES"}
        or eod_status in {"EOD_CONTRACT_REPAIR_REQUIRED", "EOD_THESIS_READY_REPAIR_AT_OPEN"}
    )
    selected_contract_side = _normalise_side(row.get("selected_contract_side"))
    contract_side_conflict = bool(selected_contract_side and side in {"CALL", "PUT"} and selected_contract_side != side)
    direction_conflict_status = _u(row.get("direction_conflict_status"))
    direction_conflict_gate = _u(row.get("direction_conflict_gate"))
    direction_arbitration_status = _u(row.get("direction_arbitration_status"))
    direction_conflict_unresolved = direction_conflict_status in {"UNRESOLVED", "CONFLICT", "DIRECTION_CONFLICT"}
    direction_conflict_mitigated = (
        direction_conflict_status in {"MITIGATED_REQUIRES_CONFIRMATION", "STRUCTURAL_PROBABILITY_CONFLICT"}
        or direction_arbitration_status == "CONFLICT_STRUCTURE_LEADS"
        or direction_conflict_gate in {"VWAP_CONFIRMATION_REQUIRED", "PHASE_D_REQUIRED"}
    )
    footprint_side = _normalise_side(first(row, "footprint_direction", "canonical_direction", "resolved_direction", "direction"))
    footprint_lock_status = _u(row.get("footprint_lock_status"))
    major_catalyst_present = (
        _boolish(first(row, "morning_catalyst_inside_dte", "catalyst_inside_dte"))
        or _u(first(row, "morning_catalyst_status", "catalyst_trade_class", "catalyst_event_status")) in {
            "DATED_CATALYST_CONFIRMED",
            "EVENT_CONVEXITY_WATCH",
            "INSIDE_DTE",
            "CONFIRMED",
        }
    )
    footprint_continuity_state = (
        "MAJOR_CATALYST_OVERRIDE_ALLOWED" if major_catalyst_present and footprint_side
        else "LOCKED" if footprint_side
        else "UNKNOWN"
    )
    footprint_continuity_reason = (
        "Wyckoff/compression footprint anchors thesis during hold window"
        if footprint_side and not major_catalyst_present
        else "Major catalyst may re-price or invalidate footprint"
        if footprint_side and major_catalyst_present
        else "No clear footprint direction supplied"
    )
    row["footprint_continuity_state"] = footprint_continuity_state
    row["footprint_continuity_reason"] = footprint_continuity_reason

    hard_veto: List[str] = []
    wait_reasons: List[str] = []
    notes: List[str] = []
    score = 0.0
    physics_score_cap: Optional[float] = None
    macro_score_cap: Optional[float] = None
    catalyst_score_cap: Optional[float] = None
    iv_rank_score_cap: Optional[float] = None
    contract_repair_needed = bool(contract_repair_required)
    direction_alignment_status = "ALIGNED"
    live_delta_alignment_status = "UNKNOWN"
    live_delta_band_status = "UNKNOWN"
    physics_wait_is_timing_only = False

    if evening_verdict == "BLOCKED":
        hard_veto.append("Evening candidate was BLOCKED")
    if eod_status in EOD_STRUCTURAL_HARD_STATUSES or _evening_hard_veto_is_structural(row):
        hard_veto.append("Evening structural/no-options veto")
    if footprint_side and side in {"CALL", "PUT"} and footprint_side != side and not major_catalyst_present:
        contract_repair_needed = True
        direction_alignment_status = "FOOTPRINT_SIDE_CONFLICT"
        wait_reasons.append("Current thesis side conflicts with locked Wyckoff/compression footprint")
    if contract_side_conflict:
        contract_repair_needed = True
        direction_alignment_status = "CONTRACT_SIDE_CONFLICT"
        wait_reasons.append("Selected contract side conflicts with thesis direction")
    elif direction_conflict_unresolved:
        direction_alignment_status = "UNRESOLVED_DIRECTION_CONFLICT"
        wait_reasons.append("Direction conflict unresolved - require manual confirmation")
    elif direction_conflict_mitigated:
        direction_alignment_status = "MITIGATED_DIRECTION_CONFLICT"
        wait_reasons.append("Direction conflict mitigated - require live tape confirmation")

    live_delta = _f(row.get("live_delta"), None)
    if live_delta is None:
        live_delta_alignment_status = "MISSING"
        live_delta_band_status = "MISSING"
        notes.append("Live contract delta missing - verify Greeks before execution")
    else:
        abs_delta = abs(live_delta)
        sign_ok = (side == "PUT" and live_delta < 0) or (side == "CALL" and live_delta > 0) or side not in {"CALL", "PUT"}
        live_delta_alignment_status = "ALIGNED" if sign_ok else "SIDE_CONFLICT"
        if not sign_ok:
            contract_repair_needed = True
            direction_alignment_status = "CONTRACT_DELTA_SIDE_CONFLICT"
            wait_reasons.append("Live option delta sign conflicts with thesis direction")
        if abs_delta < 0.20:
            live_delta_band_status = "TOO_LOW"
            contract_repair_needed = True
            wait_reasons.append("Live option delta too low for morning execution")
        elif abs_delta > 0.75:
            live_delta_band_status = "TOO_HIGH"
            contract_repair_needed = True
            wait_reasons.append("Live option delta too high - check assignment/premium efficiency")
        else:
            live_delta_band_status = "OK"
            if 0.30 <= abs_delta <= 0.65:
                score += 5

    bond_breakeven_adjustment_pct = _f(row.get("morning_bond_breakeven_adjustment_pct"), 0.0) or 0.0
    bond_breakeven_adjustment_pct = max(0.0, min(50.0, bond_breakeven_adjustment_pct))
    if bond_breakeven_adjustment_pct > 0:
        notes.append(
            f"Bond macro spread environment applies +{bond_breakeven_adjustment_pct:.1f}% premium/breakeven buffer"
        )

    iv_rank_gate = _iv_rank_gate(row)
    row.update(iv_rank_gate)
    iv_rank_state = _u(iv_rank_gate.get("morning_iv_rank_state"))
    iv_rank_reason = _s(iv_rank_gate.get("morning_iv_rank_reason"))
    iv_rank_cap = _f(iv_rank_gate.get("morning_iv_rank_score_cap"), None)
    if iv_rank_state == "CHEAP":
        score += 3
        notes.append(iv_rank_reason)
    elif iv_rank_state == "ELEVATED":
        wait_reasons.append(iv_rank_reason)
    elif iv_rank_state in {"EXPENSIVE", "EXTREME_EXPENSIVE"}:
        iv_rank_score_cap = iv_rank_cap
        wait_reasons.append(iv_rank_reason)

    if price is None or price <= 0:
        row.update(
            {
                "live_validation_state": "NO_LIVE_DATA",
                "morning_execution_permission": "WAIT",
                "morning_execution_route": "WAIT",
                "execution_permission": "WAIT",
                "eod_thesis_confirmed": "FALSE",
                "physics_transition_confirmed": "UNKNOWN",
                "vwap_confirmed": "UNKNOWN",
                "opening_range_confirmed": "UNKNOWN",
                "direction_confirmed": "UNKNOWN",
                "contract_liquidity_confirmed": "UNKNOWN",
                "spread_confirmed": "UNKNOWN",
                "breakeven_confirmed": "UNKNOWN",
                "invalidation_respected": "UNKNOWN",
                "live_price_drift_ok": "UNKNOWN",
                "live_data_fresh": "FALSE",
                "validation_confidence": 20,
                "validation_score": 0,
                "morning_execution_lane": "WAIT",
                "morning_entry_action": "Wait for live data",
                "morning_unlock_condition": "No live price - cannot confirm evening thesis",
                "thesis_validity_state": "UNKNOWN",
                "entry_timing_state": "PENDING_LIVE_DATA",
                "contract_tradability_state": "UNKNOWN",
                "direction_alignment_status": direction_alignment_status,
                "live_delta_alignment_status": live_delta_alignment_status,
                "live_delta_band_status": live_delta_band_status,
                "rejection_reason": "",
                "wait_reason": "Pending live price - cannot confirm evening thesis yet",
                "upgrade_downgrade_reason": "Downgraded to WAIT because live price is unavailable",
                "morning_notes": "PENDING_LIVE_DATA",
                "manual_review_required": "TRUE",
                "reviewer_approval": "",
                "reviewer_notes": "",
                "review_timestamp": "",
                "approved_size_contracts": "",
                "execution_lifecycle_state": "MANUAL_REVIEW_REQUIRED",
                "automated_execution_eligible": "FALSE",
            }
        )
        return row

    ts = _parse_ts(first(live, "live_data_timestamp_utc", "quote_timestamp_utc", "timestamp"))
    fresh = True
    age_min: Optional[float] = None
    marketdata_quote_seen = "MARKETDATA" in _u(first(live, "live_options_data_source", "live_equity_data_source", default=""))
    if ts is not None:
        age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60.0
        row["live_data_age_minutes"] = round(age_min, 2)
        fresh = age_min <= quote_stale_minutes
        if not fresh and marketdata_quote_seen:
            grace_min = _f(os.getenv("AVS_MV_MARKETDATA_STALE_GRACE_MINUTES", "120"), 120.0) or 120.0
            if age_min <= grace_min:
                fresh = True
                row["live_data_freshness_override"] = "MARKETDATA_DELAYED_ACCEPTED"
                notes.append(
                    "MarketData delayed/cached quote accepted for validation; confirm final bid/ask in broker before entry"
                )
    else:
        row["live_data_age_minutes"] = ""
        if price is not None and price > 0:
            row["live_data_freshness_override"] = "NO_PROVIDER_TIMESTAMP_ACCEPTED"
            fresh = True
    if fresh:
        score += 5
    else:
        wait_reasons.append("Live data stale")

    invalidation_respected = True
    if invalidation and invalidation > 0:
        if side == "CALL" and price <= invalidation:
            invalidation_respected = False
            hard_veto.append("Evening invalidation violated")
        elif side == "PUT" and price >= invalidation:
            invalidation_respected = False
            hard_veto.append("Evening invalidation violated")

    if _u(first(row, "l3_jump_risk_flag", "jump_risk_flag")) in {"TRUE", "1", "YES"}:
        hard_veto.append("Jump risk active")

    if _boolish(row.get("morning_macro_hard_block")):
        hard_veto.append(_s(row.get("morning_macro_block_reason")) or "Fresh macro context hard block")
    elif _boolish(row.get("morning_macro_requires_confirmation")):
        macro_score_cap = 79
        wait_reasons.append(_s(row.get("morning_macro_interpretation_reason")) or "Fresh macro context requires confirmation")

    if _boolish(row.get("morning_catalyst_hard_block")):
        hard_veto.append(_s(row.get("morning_catalyst_block_reason")) or "Fresh catalyst calendar hard block")
    else:
        catalyst_warnings = _u(row.get("morning_context_warnings"))
        if "CATALYST_REQUIRES_MANUAL_CONFIRMATION" in catalyst_warnings:
            catalyst_score_cap = 79
            wait_reasons.append("Fresh catalyst calendar requires manual confirmation")
        if "CATALYST_NO_CAPITAL_GRADE" in catalyst_warnings:
            catalyst_score_cap = min(catalyst_score_cap or 69, 69)
            wait_reasons.append("Fresh catalyst calendar does not grant capital permission")
        if "CATALYST_DIRECTION_CONFLICT" in catalyst_warnings:
            catalyst_score_cap = min(catalyst_score_cap or 79, 79)
            wait_reasons.append("Fresh catalyst direction conflicts with thesis")

    distance_to_vwap = _f(row.get("live_distance_to_vwap_pct"), None)
    too_extended = distance_to_vwap is not None and abs(distance_to_vwap) > 2.5
    midpoint = (orb_high + orb_low) / 2.0 if orb_high is not None and orb_low is not None else None

    vwap_confirmed: Any = "UNKNOWN"
    opening_confirmed: Any = "UNKNOWN"
    direction_confirmed: Any = "UNKNOWN"
    direction_rejected = False

    if vwap and vwap > 0:
        if side == "PUT":
            vwap_confirmed = price < vwap and not too_extended
        else:
            vwap_confirmed = price > vwap and not too_extended
        if vwap_confirmed is True:
            score += 15
        elif too_extended:
            wait_reasons.append("Chasing risk - wait for VWAP retest")
        else:
            notes.append("VWAP not confirmed")

    if midpoint is not None:
        if side == "PUT":
            opening_confirmed = price <= midpoint or (orb_low is not None and price < orb_low)
            direction_confirmed = bool((vwap is None or price < vwap) and opening_confirmed)
            direction_rejected = bool(vwap and price > vwap and orb_high is not None and price > orb_high)
        else:
            opening_confirmed = price >= midpoint or (orb_high is not None and price > orb_high)
            direction_confirmed = bool((vwap is None or price > vwap) and opening_confirmed)
            direction_rejected = bool(vwap and price < vwap and orb_low is not None and price < orb_low)
        if opening_confirmed is True:
            score += 15
    elif vwap_confirmed != "UNKNOWN":
        direction_confirmed = bool(vwap_confirmed)

    if direction_confirmed is True:
        score += 20
    if direction_rejected:
        wait_reasons.append("Live tape rejects thesis direction")
    if direction_conflict_gate == "VWAP_CONFIRMATION_REQUIRED" and vwap_confirmed is not True:
        direction_alignment_status = "VWAP_GATE_PENDING"
        wait_reasons.append("Direction arbitration requires VWAP confirmation")
    elif direction_conflict_gate == "VWAP_CONFIRMATION_REQUIRED" and vwap_confirmed is True:
        direction_alignment_status = "VWAP_GATE_CONFIRMED"
        notes.append("Direction arbitration VWAP gate confirmed")

    physics_label = _s(row.get("evening_state_transition_label") or row.get("evening_hidden_state_label"))
    physics_confirmed, physics_note = _physics_check(
        physics_label,
        side,
        price,
        vwap,
        orb_high,
        orb_low,
    )
    if physics_confirmed is True:
        score += 20
    elif physics_confirmed == "WAIT":
        score += 8
    elif physics_confirmed is False:
        wait_reasons.append(physics_note)
    if physics_confirmed == "WAIT":
        if "HIGH_ENTROPY_CHOP" in _u(physics_label):
            physics_score_cap = 59
        elif _is_short_horizon(horizon_bucket) or "NO_TRANSITION_EDGE" not in _u(physics_label):
            physics_score_cap = 79
            wait_reasons.append(physics_note)
        else:
            physics_wait_is_timing_only = True
            wait_reasons.append(f"Horizon {horizon_bucket}: trigger pending, limit/probe execution allowed if thesis and contract remain valid")
            notes.append(f"Horizon {horizon_bucket}: live trigger is timing guidance, not thesis veto")

    contract_bid = _f(row.get("live_contract_bid"), None)
    contract_ask = _f(row.get("live_contract_ask"), None)
    contract_mid = _f(row.get("live_contract_mid"), None)
    contract_quote_missing = not (contract_bid and contract_ask and contract_mid and contract_mid > 0)
    contract_liquidity_confirmed: Any = "UNKNOWN"
    spread_confirmed: Any = "UNKNOWN"
    if contract_quote_missing:
        contract_repair_needed = True
        if contract_repair_required:
            wait_reasons.append("Contract repair required - select liquid contract before execution")
        elif _u(pipeline_mode) in {"LIVE", "MORNING_VALIDATION"}:
            wait_reasons.append("Live contract quote missing - repair or refresh selected contract")
        else:
            wait_reasons.append("Live contract quote missing - cannot execute yet")
    else:
        contract_liquidity_confirmed = True
        if live_contract_spread is None:
            spread_confirmed = "UNKNOWN"
            wait_reasons.append("Live contract spread unavailable")
        elif live_contract_spread > 25:
            spread_confirmed = False
            contract_liquidity_confirmed = False
            contract_repair_needed = True
            wait_reasons.append("Live contract spread too wide - repair contract, do not kill ticker thesis")
        elif live_contract_spread > 15:
            spread_confirmed = "CAUTION"
            score += 8
            wait_reasons.append("Spread caution - wait for better fill")
        else:
            spread_confirmed = True
            score += 15

    breakeven_confirmed: Any = "UNKNOWN"
    if strike and premium and target:
        raw_breakeven = strike + premium if side != "PUT" else strike - premium
        adjusted_premium = premium * (1.0 + bond_breakeven_adjustment_pct / 100.0)
        breakeven = strike + adjusted_premium if side != "PUT" else strike - adjusted_premium
        row["morning_raw_breakeven"] = round(raw_breakeven, 4)
        row["morning_bond_adjusted_premium"] = round(adjusted_premium, 4)
        row["morning_bond_adjusted_breakeven"] = round(breakeven, 4)
        breakeven_confirmed = target >= breakeven if side != "PUT" else target <= breakeven
        if breakeven_confirmed:
            score += 10
        else:
            contract_repair_needed = True
            raw_confirmed = target >= raw_breakeven if side != "PUT" else target <= raw_breakeven
            if bond_breakeven_adjustment_pct > 0 and raw_confirmed:
                wait_reasons.append("Bond macro spread adjustment makes breakeven too tight")
            else:
                wait_reasons.append("Breakeven no longer sane")
    elif premium and premium > 0:
        breakeven_confirmed = "UNKNOWN"
        score += 4

    ref_price = _f(first(row, "signal_price", "current_price", "spot_price", "underlying_price"), None)
    live_price_drift_ok: Any = "UNKNOWN"
    if ref_price and ref_price > 0:
        drift = (price - ref_price) / ref_price * 100.0
        # ATR-relative drift gate: block if price moved > 1.0 ATR against thesis since EOD.
        # Falls back to ±2.5% when ATR is unavailable (e.g. first-boot morning candidates).
        _atr_raw = _f(first(row, "atr_current", "atr_14", "ATR_14"), None)
        if _atr_raw and _atr_raw > 0:
            _drift_gate = max(_atr_raw / ref_price * 100.0, 0.5)  # floor at 0.5% for low-ATR names
        else:
            _drift_gate = 2.5  # legacy fallback
        if side == "PUT":
            live_price_drift_ok = drift <= _drift_gate
        else:
            live_price_drift_ok = drift >= -_drift_gate
        if not live_price_drift_ok:
            wait_reasons.append(
                f"Adverse live price drift ({abs(drift):.1f}% vs {_drift_gate:.1f}% ATR gate)"
            )
    else:
        live_price_drift_ok = True

    for cap in (physics_score_cap, macro_score_cap, catalyst_score_cap, iv_rank_score_cap):
        if cap is not None:
            score = min(score, cap)

    if not fresh:
        state = "STALE"
        permission = "WAIT"
        score = min(score, 55)
    elif hard_veto:
        state = "REJECTED" if "Evening invalidation violated" in hard_veto else "BLOCKED"
        permission = "BLOCKED"
    elif direction_rejected or physics_confirmed is False:
        state = "REJECTED"
        permission = "BLOCKED" if score < 40 else "WAIT"
    elif contract_repair_needed:
        state = "WAIT_RETEST"
        permission = "CONTRACT_REPAIR"
    elif direction_conflict_unresolved and score >= 70 and direction_confirmed is True and not too_extended:
        state = "WAIT_RETEST"
        permission = "PROBE"
    elif score >= 80 and not too_extended:
        state = "CONFIRMED"
        permission = "GO_LIMIT" if physics_wait_is_timing_only else "GO"
    elif score >= 70 and direction_confirmed is True and not too_extended and not _is_short_horizon(horizon_bucket):
        state = "CONFIRMED"
        permission = "PROBE"
    elif score >= 60:
        state = "WAIT_RETEST"
        permission = "ARMED"
    elif score >= 40:
        state = "WAIT_RETEST"
        permission = "WAIT"
    else:
        state = "WAIT_RETEST"
        permission = "WAIT"

    if spread_confirmed == "CAUTION" and permission == "GO":
        permission = "GO_LIMIT"
        state = "CONFIRMED"
    if too_extended and permission in {"GO", "GO_LIMIT", "PROBE"}:
        permission = "ARMED"
        state = "WAIT_RETEST"
    if direction_conflict_unresolved and permission in {"GO", "GO_LIMIT"}:
        permission = "PROBE" if score >= 75 and direction_confirmed is True else "ARMED"
        state = "WAIT_RETEST"
    if direction_conflict_mitigated and permission in {"GO", "GO_LIMIT"}:
        permission = "PROBE" if direction_confirmed is True and vwap_confirmed is True else "ARMED"
        state = "CONFIRMED" if permission == "PROBE" else "WAIT_RETEST"
    if iv_rank_state == "ELEVATED" and permission == "GO":
        permission = "GO_LIMIT"
        state = "CONFIRMED"
    elif iv_rank_state in {"EXPENSIVE", "EXTREME_EXPENSIVE"} and permission in {"GO", "GO_LIMIT"}:
        permission = "PROBE" if direction_confirmed is True and score >= 70 and not too_extended else "ARMED"
        state = "CONFIRMED" if permission == "PROBE" else "WAIT_RETEST"

    confidence = max(0, min(100, score))
    if state in {"STALE", "NO_LIVE_DATA"}:
        confidence = min(confidence, 35)

    # ── TRF: Transition Risk Factor adjustment ────────────────────────────────
    # Applies the Markov phase transition risk factor to the validation score.
    # score_trf = score x (1 - trf)
    # trf=0.0 no change; trf near 1.0 score significantly reduced.
    # Fails silently (trf=0.0) if matrix file is absent.
    _trf_phase_risk = 0.0
    _trf_source     = "NEUTRAL_FALLBACK"
    _trf_sparse     = False
    try:
        from transition_matrix_consumer import get_consumer as _get_tmc
        _tmc = _get_tmc()
        _phase_val  = str(
            first(row, "phase_v2", "wyckoff_phase_bucket", "crabel_state", default="")
        ).strip().upper()
        _regime_val = str(
            first(row, "macro_regime", "morning_macro_regime_state", "regime_state", default="ALL")
        ).strip().upper()
        _tier_val   = str(
            first(row, "future_momentum_bucket", "tier", default="ALL")
        ).strip().upper()
        if _phase_val:
            _trf_result     = _tmc.adjust_validation_score(
                score=score,
                phase=_phase_val,
                regime=_regime_val,
                tier=_tier_val,
            )
            score           = _trf_result["score_adjusted"]
            confidence      = max(0, min(100, score))
            _trf_phase_risk = _trf_result["trf"]
            _trf_source     = _trf_result["trf_source"]
            _trf_sparse     = _trf_result["sparse"]
            if state in {"STALE", "NO_LIVE_DATA"}:
                confidence = min(confidence, 35)
    except Exception as _trf_exc:
        import logging as _trf_log
        _trf_log.getLogger("avshunter.morning_validator").debug(
            "TRF adjustment failed neutral fallback: %s", _trf_exc
        )

    rejection_reason = "; ".join(hard_veto) if hard_veto else ("; ".join(wait_reasons) if state == "REJECTED" else "")
    wait_reason = "; ".join(wait_reasons) if permission in {"ARMED", "WAIT", "CONTRACT_REPAIR", "PROBE", "GO_LIMIT"} else ""
    upgrade_downgrade = f"Evening {evening_verdict or 'UNKNOWN'} -> {permission} via live validation"
    thesis_confirmed = bool(
        fresh
        and invalidation_respected
        and state not in {"REJECTED", "BLOCKED", "NO_LIVE_DATA", "STALE"}
        and permission not in {"WAIT", "BLOCKED"}
    )
    if permission in {"ARMED"} and score >= 60:
        thesis_confirmed = True
    entry_timing_state = (
        "TRIGGER_CONFIRMED" if permission == "GO"
        else "LIMIT_ENTRY_ALLOWED" if permission == "GO_LIMIT"
        else "PROBE_ALLOWED" if permission == "PROBE"
        else "CONTRACT_REPAIR_REQUIRED" if permission == "CONTRACT_REPAIR"
        else "RETEST_REQUIRED" if permission == "ARMED"
        else "WAITING"
    )
    contract_tradability_state = (
        "REPAIR_REQUIRED" if contract_repair_needed
        else "CAUTION" if spread_confirmed == "CAUTION" or iv_rank_state in {"ELEVATED", "EXPENSIVE", "EXTREME_EXPENSIVE"}
        else "OK" if contract_liquidity_confirmed is True and spread_confirmed is True
        else "UNKNOWN"
    )
    lane_meta = _lane_metadata(
        permission,
        contract_repair_needed=contract_repair_needed,
        wait_reasons=wait_reasons,
        hard_veto=hard_veto,
    )

    row.update(
        {
            "live_validation_state": state,
            "morning_execution_permission": permission,
            "morning_execution_route": lane_meta["morning_execution_lane"],
            "execution_permission": permission,
            "eod_thesis_confirmed": _bool_text(thesis_confirmed),
            "physics_transition_confirmed": _bool_text(physics_confirmed) if physics_confirmed != "WAIT" else "WAIT",
            "vwap_confirmed": _bool_text(vwap_confirmed),
            "opening_range_confirmed": _bool_text(opening_confirmed),
            "direction_confirmed": _bool_text(direction_confirmed),
            "contract_liquidity_confirmed": _bool_text(contract_liquidity_confirmed),
            "spread_confirmed": _bool_text(spread_confirmed) if spread_confirmed != "CAUTION" else "CAUTION",
            "breakeven_confirmed": _bool_text(breakeven_confirmed),
            "invalidation_respected": _bool_text(invalidation_respected),
            "live_price_drift_ok": _bool_text(live_price_drift_ok),
            "live_data_fresh": _bool_text(fresh),
            "validation_confidence": round(confidence, 2),
            "validation_score": round(max(0, min(100, score)), 2),
            "trf_phase_risk": round(_trf_phase_risk, 6),
            "trf_source": _trf_source,
            "trf_sparse": _trf_sparse,
            "morning_execution_lane": lane_meta["morning_execution_lane"],
            "morning_entry_action": lane_meta["morning_entry_action"],
            "morning_unlock_condition": lane_meta["morning_unlock_condition"],
            "thesis_validity_state": "VALID" if thesis_confirmed else ("BROKEN" if hard_veto or state == "REJECTED" else "PENDING"),
            "entry_timing_state": entry_timing_state,
            "contract_tradability_state": contract_tradability_state,
            "direction_alignment_status": direction_alignment_status,
            "footprint_continuity_state": footprint_continuity_state,
            "footprint_continuity_reason": footprint_continuity_reason,
            "live_delta_alignment_status": live_delta_alignment_status,
            "live_delta_band_status": live_delta_band_status,
            "rejection_reason": rejection_reason,
            "wait_reason": wait_reason,
            "upgrade_downgrade_reason": upgrade_downgrade,
            "morning_notes": "; ".join([n for n in notes + [physics_note] if n]),
            "manual_review_required": "TRUE",
            "reviewer_approval": "",
            "reviewer_notes": "",
            "review_timestamp": "",
            "approved_size_contracts": "",
            "execution_lifecycle_state": "MANUAL_REVIEW_REQUIRED",
            "automated_execution_eligible": "FALSE",
        }
    )

    # FIX 6: Horizon-aware thesis fields — required by pipeline interpreter.
    # Derives from validation state; replaces binary BLOCKED/CONTRACT_REPAIR output.
    _hb = _horizon_bucket(row)
    _perm = _u(row.get("execution_permission") or row.get("morning_execution_permission"))
    _macro_regime_changed = _boolish(row.get("macro_state_changed"))
    _new_macro = _u(row.get("morning_regime_state") or "")
    _macro_is_crisis = _new_macro in {"RISK_OFF", "CRISIS", "BEAR"} and _macro_regime_changed

    # compute_morning_verdict: horizon-specific logic
    if _macro_is_crisis:
        _morning_verdict = "DEAD"
    elif _perm in {"GO", "GO_LIMIT"}:
        _morning_verdict = "EXECUTE"
    elif _perm in {"ARMED"}:
        _morning_verdict = "ARMED"
    elif _perm in {"PROBE"}:
        _morning_verdict = "PROBE"
    elif _perm in {"WAIT", "CONTRACT_REPAIR"}:
        _morning_verdict = "WATCH" if _hb in ("6_10d", "11_20d") else "WAIT"
    elif _perm in {"BLOCKED"}:
        _morning_verdict = "DEAD"
    else:
        _morning_verdict = "WAIT"

    _thesis_still_valid = (
        _morning_verdict not in {"DEAD"}
        and not hard_veto
        and state not in {"REJECTED", "BLOCKED"}
    )
    _tradeable_today = _perm in {"GO", "GO_LIMIT", "PROBE"} and not _macro_is_crisis
    _feeds_interpreter = _thesis_still_valid and _morning_verdict not in {"DEAD", "WAIT", "HOLD"}

    _macro_score = 0.5  # neutral default; scoring requires full macro context
    if _new_macro in {"TRENDING_BULL", "RISK_ON", "BULL"}:
        _macro_score = 0.85 if _hb == "1_5d" else 0.75
    elif _new_macro in {"TRENDING_BEAR", "RISK_OFF", "BEAR"}:
        _macro_score = 0.15 if _hb == "1_5d" else 0.25

    row.update({
        # FIX 6 required fields
        "morning_verdict":    _morning_verdict,
        "thesis_still_valid": _thesis_still_valid,
        "thesis_delta":       f"Macro: {_u(row.get('evening_regime_state'))} -> {_new_macro}" if _macro_regime_changed else "",
        "horizon":            _hb,
        "tradeable_today":    _tradeable_today,
        "tradeable_reason":   (
            "Live trigger confirmed" if _morning_verdict == "EXECUTE"
            else "Regime flip armed" if _morning_verdict == "ARMED"
            else "Pending confirmation" if _morning_verdict in ("WATCH", "PROBE")
            else "Thesis invalidated" if _morning_verdict == "DEAD"
            else "Awaiting trigger"
        ),
        "feeds_interpreter":  _feeds_interpreter,
        "macro_score":        round(_macro_score, 2),
    })

    # FIX 10: options_hard_vetoes — read structured veto list and inform trader
    _hard_vetoes_raw = _s(first(row, "options_hard_vetoes", "hard_vetoes"))
    _earnings_veto = False
    if _hard_vetoes_raw and _hard_vetoes_raw not in {"", "[]", "None"}:
        try:
            import json as _json10mv
            _veto_list = _json10mv.loads(_hard_vetoes_raw) if _hard_vetoes_raw.startswith("[") else []
            _earnings_veto = any(v.get("veto_type") == "EARNINGS_WITHIN_DTE" for v in _veto_list if isinstance(v, dict))
            if _earnings_veto:
                _ev_note = "EARNINGS WITHIN DTE WINDOW -- defined-risk structures only"
                row["morning_notes"] = ("; ".join([row.get("morning_notes", ""), _ev_note])).strip("; ")
        except Exception:
            pass
    row["EARNINGS_WITHIN_DTE"] = _earnings_veto

    # FIX 7: EVENT_CONVEXITY_WATCH with cheap_convexity → ARMED verdict
    if _u(row.get("catalyst_trade_class")) == "EVENT_CONVEXITY_WATCH" and _boolish(row.get("cheap_convexity")):
        if permission not in {"GO", "GO_LIMIT"}:
            permission = "ARMED"
            row["execution_permission"] = permission
            row["morning_execution_permission"] = permission
        _ecw_note = "EVENT_CONVEXITY_WATCH with cheap_convexity -- priority review"
        row["morning_notes"] = ("; ".join([row.get("morning_notes", ""), _ecw_note])).strip("; ")

    # FIX 1: direction_conflict_flag — downgrade to PROBE and note for trader review
    if _boolish(row.get("direction_conflict_flag")):
        row["execution_permission"] = "PROBE"
        row["morning_execution_permission"] = "PROBE"
        _conflict_note = _s(row.get("direction_conflict_note")) or "Direction conflict — verify at open"
        row["morning_notes"] = ("; ".join([row.get("morning_notes", ""), _conflict_note])).strip("; ")
        row["upgrade_downgrade_reason"] = "Direction conflict flag: " + _conflict_note
    return row


def build_summary(run_id: str, rows: List[Dict[str, Any]], input_count: int) -> Dict[str, Any]:
    counts = Counter(_u(r.get("morning_execution_permission") or r.get("execution_permission")) for r in rows)
    states = Counter(_u(r.get("live_validation_state")) for r in rows)
    data_modes = Counter(_u(r.get("live_data_mode")) or "UNKNOWN" for r in rows)
    paper_mode = any(mode in {"PAPER", "SIMULATED", "REPLAY"} for mode in data_modes)
    scores = [_f(r.get("validation_score"), None) for r in rows]
    scores_f = [s for s in scores if s is not None]
    rejections = Counter(_s(r.get("rejection_reason")) for r in rows if _s(r.get("rejection_reason")))
    waits = Counter(_s(r.get("wait_reason")) for r in rows if _s(r.get("wait_reason")))
    eod_statuses = Counter(_u(r.get("eod_candidate_status") or r.get("eod_status")) for r in rows)
    repaired = sum(
        1
        for r in rows
        if _u(r.get("morning_execution_permission")) in {"CONTRACT_REPAIR"}
        or "REPAIR" in _u(r.get("morning_execution_route"))
        or "REPAIR" in _u(r.get("contract_repair_status"))
        or _boolish(r.get("contract_repair_required"))
    )
    broken_thesis = sum(1 for r in rows if _u(r.get("thesis_validity_state")) == "BROKEN")
    pending_live = states.get("PENDING_LIVE_DATA", 0) + states.get("NO_LIVE_DATA", 0)
    macro_blocks = sum(1 for r in rows if _boolish(r.get("morning_macro_hard_block")))
    catalyst_blocks = sum(1 for r in rows if _boolish(r.get("morning_catalyst_hard_block")))
    macro_confirmation = sum(1 for r in rows if _boolish(r.get("morning_macro_requires_confirmation")))
    catalyst_manual = sum(1 for r in rows if _boolish(r.get("morning_catalyst_needs_manual_confirmation")))
    iv_rank_states = Counter(_u(r.get("morning_iv_rank_state")) or "UNKNOWN" for r in rows)
    return {
        "run_id": run_id,
        "validated_at_utc": _utc_now(),
        "input_candidates": input_count,
        "validated_count": len(rows),
        "confirmed_count": states.get("CONFIRMED", 0),
        "go_limit_count": counts.get("GO_LIMIT", 0),
        "probe_count": counts.get("PROBE", 0),
        "armed_count": counts.get("ARMED", 0),
        "contract_repair_count": counts.get("CONTRACT_REPAIR", 0),
        "wait_count": counts.get("WAIT", 0),
        "blocked_count": counts.get("BLOCKED", 0),
        "go_count": counts.get("GO", 0),
        "no_live_data_count": states.get("NO_LIVE_DATA", 0),
        "pending_live_data_count": pending_live,
        "stale_count": states.get("STALE", 0),
        "received_eod_status_counts": dict(eod_statuses),
        "broken_thesis_count": broken_thesis,
        "contract_repair_or_reselect_count": repaired,
        "wait_for_live_confirmation_count": counts.get("WAIT", 0) + counts.get("ARMED", 0),
        "live_go_total": counts.get("GO", 0) + counts.get("GO_LIMIT", 0) + counts.get("PROBE", 0),
        "avg_validation_score": round(sum(scores_f) / len(scores_f), 2) if scores_f else 0,
        "top_rejections": [{"reason": k, "count": v} for k, v in rejections.most_common(5)],
        "top_wait_reasons": [{"reason": k, "count": v} for k, v in waits.most_common(5)],
        "live_data_mode_counts": dict(data_modes),
        "fresh_macro_block_count": macro_blocks,
        "fresh_macro_confirmation_count": macro_confirmation,
        "fresh_catalyst_block_count": catalyst_blocks,
        "fresh_catalyst_manual_confirmation_count": catalyst_manual,
        "iv_rank_state_counts": dict(iv_rank_states),
        "iv_rank_expensive_count": iv_rank_states.get("EXPENSIVE", 0) + iv_rank_states.get("EXTREME_EXPENSIVE", 0),
        "iv_rank_elevated_count": iv_rank_states.get("ELEVATED", 0),
        "iv_rank_cheap_count": iv_rank_states.get("CHEAP", 0),
        "paper_mode": paper_mode,
        "ready_for_lab": bool(rows) and not paper_mode,
    }



def _write_morning_live_data_snapshot(
    run_id: str,
    runs_root: Path,
    prepared: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    live_payloads: List[Dict[str, Any]],
) -> Optional[Path]:
    """Write the morning live-data sidecar from already-fetched payloads.

    This deliberately does not call pipeline_interpreter.live_market_reader.
    Polygon remains available for equity tape in _fetch_live_snapshot, but all
    option contract fields in this sidecar come from MarketData quote payloads.
    """
    if not prepared:
        return None
    out_path = runs_root / run_id / "morning_validation" / f"morning_live_data_{run_id}.json"
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "created_at_utc": _utc_now(),
        "provider_policy": "POLYGON_STOCKS_MARKETDATA_OPTIONS",
        "ticker_count": 0,
        "tickers": {},
    }
    for (_, cand), live in zip(prepared, live_payloads):
        ticker = _u(cand.get("ticker"))
        if not ticker:
            continue
        live = dict(live or {})
        payload["tickers"][ticker] = {
            "ticker": ticker,
            "fetched_at_utc": live.get("live_data_timestamp_utc") or _utc_now(),
            "equity_source": live.get("live_equity_data_source") or "MARKETDATA_STOCK_QUOTE_PLUS_POLYGON_EQUITY_BARS",
            "options_source": live.get("live_options_data_source") or "MARKETDATA_OPTIONS_QUOTE",
            "options_freshness": live.get("live_options_data_freshness") or "",
            "live_price": live.get("live_price") or live.get("live_mid"),
            "live_vwap": live.get("live_vwap"),
            "selected_contract": first(cand, "evening_contract_symbol", "contract_occ_symbol", "recommended_contract", "preferred_contract", "contract_symbol"),
            "live_contract_bid": live.get("live_contract_bid"),
            "live_contract_ask": live.get("live_contract_ask"),
            "live_contract_mid": live.get("live_contract_mid"),
            "live_contract_volume": live.get("live_contract_volume"),
            "live_contract_open_interest": live.get("live_contract_open_interest"),
            "live_iv": live.get("live_iv"),
            "live_delta": live.get("live_delta"),
            "live_gamma": live.get("live_gamma"),
            "live_theta": live.get("live_theta"),
            "note": "Morning validator sidecar generated from MarketData option quotes; no Polygon options calls.",
        }
    payload["ticker_count"] = len(payload["tickers"])
    _write_json(out_path, payload)
    try:
        import sys as _ma_sys
        _ma_sys.path.insert(0, str(ROOT / "pipeline_interpreter"))
        from ma_inputs_sync import sync_file as _ma_sync_file
        _ma_sync_file(out_path, verbose=True, force=True)
    except Exception as _sync_exc:
        log.warning("Morning live-data sidecar sync skipped for %s: %s", out_path, _sync_exc)
    print(f"[MV] MarketData options live sidecar written for {payload['ticker_count']} ticker(s) -> {out_path.name}", flush=True)
    return out_path

def run_morning_validation(
    candidates_path: Optional[str | Path] = None,
    output_path: Optional[str | Path] = None,
    run_id: Optional[str] = None,
    max_signals: int = 0,
    tier_filter: Optional[str] = None,
    live_mode: bool = True,
    *,
    runs_dir: str | Path = RUNS_DIR,
    live_data_path: Optional[str | Path] = None,
    paper_mode: bool = False,
    pipeline_mode: str = "MORNING_VALIDATION",
    include_high_priority_wait: bool = False,
    refresh_morning_context: bool = True,
    macro_path: Optional[str | Path] = DEFAULT_MACRO_PATH,
    macro_enrichment_path: Optional[str | Path] = DEFAULT_MACRO_ENRICHMENT_PATH,
    catalyst_calendar_path: Optional[str | Path] = DEFAULT_CATALYST_CALENDAR_PATH,
) -> List[Dict[str, Any]]:
    runs_root = Path(runs_dir)
    rid = run_id or latest_run_id(runs_root)
    if not rid:
        raise FileNotFoundError("No run_id supplied and no latest run could be resolved")

    explicit_path = Path(candidates_path) if candidates_path else None
    source_path, source_mode = find_candidate_source(rid, runs_root, explicit_path)
    if not source_path:
        raise FileNotFoundError(f"No morning validation source found for run {rid}")

    output = Path(output_path) if output_path else runs_root / rid / "morning_validation" / f"morning_validated_trades_{rid}.csv"
    packet_path = output.parent / f"morning_validation_packet_{rid}.json"

    input_rows = _read_csv(source_path)
    selected = select_candidates(
        input_rows,
        max_signals=max_signals,
        tier_filter=tier_filter,
        include_high_priority_wait=include_high_priority_wait,
    )

    morning_context: Dict[str, Any] = {}
    if refresh_morning_context:
        morning_context = _load_morning_context(
            macro_path=macro_path,
            macro_enrichment_path=macro_enrichment_path,
            catalyst_calendar_path=catalyst_calendar_path,
        )
        selected = [_apply_morning_context(row, morning_context) for row in selected]
        print(
            "[MV] Fresh context: "
            f"macro={morning_context.get('macro_path')} | "
            f"enrichment={morning_context.get('macro_enrichment_path')} | "
            f"catalyst={morning_context.get('catalyst_calendar_path')} | "
            f"warnings={len(morning_context.get('warnings') or [])}",
            flush=True,
        )

    # FIX 2: Read regime_watch CSV and add to morning output.
    # WATCH_FOR_REGIME_FLIP rows route here — checked daily for flip confirmation.
    _regime_watch_path = runs_root / rid / "morning_validation" / f"regime_watch_{rid}.csv"
    _regime_watch_rows: List[Dict[str, Any]] = []
    if _regime_watch_path.exists():
        _regime_watch_rows = _read_csv(_regime_watch_path)
        for _rw_row in _regime_watch_rows:
            # Daily flip check: compare current macro state to watch_condition
            _current_regime = morning_context.get("macro", {}).get("regime_state", "") if morning_context else ""
            _watch_cond = str(_rw_row.get("watch_condition") or _rw_row.get("shadow_opportunity_reason") or "")
            _rw_row["eod_status"] = "REGIME_WATCH"
            if _current_regime and _watch_cond and _current_regime.upper() != _watch_cond.upper():
                _rw_row["morning_verdict"] = "ARMED"
                _rw_row["morning_execution_permission"] = "ARMED"
                _rw_row["morning_execution_route"] = "REGIME_WATCH_ARMED"
                _rw_row["execution_permission"] = "ARMED"
                _rw_row["morning_note"] = "Regime flip confirmed -- thesis activated"
                _rw_row["tradeable_today"] = True
            else:
                _rw_row["morning_verdict"] = "WATCH"
                _rw_row["morning_execution_permission"] = "WAIT"
                _rw_row["morning_execution_route"] = "REGIME_WATCH"
                _rw_row["execution_permission"] = "WAIT"
                _rw_row["morning_note"] = "Regime flip not yet confirmed -- carry forward"
                _rw_row["tradeable_today"] = False
            _rw_row["live_data_mode"] = "REGIME_WATCH_NO_LIVE_FETCH"
            _rw_row["live_data_fresh"] = "UNKNOWN"
            _rw_row["thesis_validity_state"] = "PENDING"
        print(f"[MV] Regime watch: {len(_regime_watch_rows)} WATCH_FOR_REGIME_FLIP rows loaded", flush=True)

    # FIX 8: Load evening macro snapshot for state-change detection.
    # Morning validator reads BOTH: macro_snapshot.json (what the evening used)
    # AND macro_intelligence_latest.json (current state). Outputs labelled delta.
    _evening_snapshot_path = runs_root / rid / "macro_snapshot.json"
    _evening_macro: Dict[str, Any] = {}
    if _evening_snapshot_path.exists():
        try:
            import json as _json8
            with open(_evening_snapshot_path, "r", encoding="utf-8") as _f8:
                _evening_macro = _json8.load(_f8)
        except Exception:
            pass
    _morning_macro = morning_context.get("macro", {}) if morning_context else {}
    _evening_regime_state = str(_evening_macro.get("regime_state", "")).strip()
    _morning_regime_state = str(_morning_macro.get("regime_state", "")).strip()
    _macro_state_changed = bool(
        _evening_regime_state and _morning_regime_state
        and _evening_regime_state != _morning_regime_state
    )
    print(
        f"[MV] Macro delta: evening={_evening_regime_state or 'UNKNOWN'} "
        f"morning={_morning_regime_state or 'UNKNOWN'} "
        f"changed={_macro_state_changed}",
        flush=True,
    )

    live_overrides: Dict[str, Dict[str, Any]] = {}
    if live_data_path and Path(live_data_path).exists():
        for live_row in _read_csv(Path(live_data_path)):
            t = _u(live_row.get("ticker"))
            if t:
                live_overrides[t] = live_row

    prepared: List[Tuple[Dict[str, Any], Dict[str, Any]]] = [
        (raw, normalise_evening_candidate(raw, rid)) for raw in selected
    ]

    def _resolve_live_payload(cand: Dict[str, Any]) -> Dict[str, Any]:
        ticker = _u(cand.get("ticker"))
        live_data = live_overrides.get(ticker)
        live_data_mode = "OVERRIDE" if live_data is not None else "LIVE"
        if live_data is None:
            if paper_mode or not live_mode:
                live_data = _paper_live_snapshot(cand)
                live_data_mode = "PAPER"
            else:
                live_data = _fetch_live_snapshot(cand)
                live_data_mode = "LIVE"
        live_data = dict(live_data or {})
        live_data.setdefault("live_data_mode", live_data_mode)
        return live_data

    live_payloads: List[Dict[str, Any]] = [{} for _ in prepared]
    if prepared and live_mode and not paper_mode and not live_overrides:
        print(
            f"[MV] Fetching live data for {len(prepared)} candidates "
            f"(workers={LIVE_FETCH_WORKERS}, timeout={LIVE_FETCH_TIMEOUT_SEC:.0f}s)...",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=LIVE_FETCH_WORKERS) as executor:
            futures = {
                executor.submit(_resolve_live_payload, cand): idx
                for idx, (_, cand) in enumerate(prepared)
            }
            completed = 0
            for future in as_completed(futures):
                idx = futures[future]
                raw, cand = prepared[idx]
                ticker = _u(cand.get("ticker"))
                try:
                    live_payloads[idx] = future.result()
                except Exception as exc:
                    live_payloads[idx] = {"live_data_mode": "LIVE_FETCH_ERROR", "live_fetch_error": type(exc).__name__}
                completed += 1
                mode = live_payloads[idx].get("live_data_mode", "UNKNOWN")
                price = live_payloads[idx].get("live_price") or live_payloads[idx].get("live_mid") or ""
                print(f"[MV] {completed:02d}/{len(prepared)} {ticker:<6} live={mode} price={price}", flush=True)
    else:
        for idx, (_, cand) in enumerate(prepared):
            live_payloads[idx] = _resolve_live_payload(cand)

    # Write a live-data sidecar from the MarketData option quote payloads already fetched above.
    # The previous live_market_reader call used Polygon options snapshots and could stale/block
    # the morning slate. Polygon is now equity-tape only in this path.
    if live_mode and not paper_mode and selected:
        _write_morning_live_data_snapshot(rid, runs_root, prepared, live_payloads)

    rows: List[Dict[str, Any]] = []

    rows: List[Dict[str, Any]] = []
    for (raw, cand), live_data in zip(prepared, live_payloads):
        validated = validate_candidate(cand, live_data, pipeline_mode=pipeline_mode)
        validated["source_input_path"] = str(source_path)
        validated["source_input_mode"] = source_mode
        validated["source_payload_json"] = json.dumps(raw, ensure_ascii=True, default=str)
        # FIX 8: Stamp macro state delta onto every output row.
        validated["evening_regime_state"] = _evening_regime_state
        validated["morning_regime_state"] = _morning_regime_state
        validated["macro_state_changed"] = _macro_state_changed
        validated["macro_snapshot_path"] = str(_evening_snapshot_path) if _evening_snapshot_path.exists() else ""
        rows.append(validated)

    # FIX 2: Append regime_watch rows to morning output
    rows.extend(_regime_watch_rows)

    # Ensure every row has an explicit morning permission/route before Lab and
    # Interpreter consume it. Regime-watch and other appended rows previously
    # carried morning_verdict without execution_permission, which split the UI.
    for _row in rows:
        _perm = _u(_row.get("morning_execution_permission") or _row.get("execution_permission"))
        if not _perm:
            _verdict = _u(_row.get("morning_verdict") or _row.get("live_validation_state"))
            if _verdict in EXECUTION_PERMISSIONS:
                _perm = _verdict
            elif _verdict in {"WATCH", "HOLD", "REASSESS"}:
                _perm = "WAIT"
            else:
                _perm = "WAIT"
            _row["morning_execution_permission"] = _perm
            _row["execution_permission"] = _perm
        _row.setdefault("morning_execution_route", _row.get("morning_execution_lane") or _row.get("morning_execution_permission") or "WAIT")

    _write_csv(output, rows)
    packet = {
        "summary": build_summary(rid, rows, len(selected)),
        "input_source": {
            "path": str(source_path),
            "mode": source_mode,
            "selected_candidates": len(selected),
            "total_source_rows": len(input_rows),
        },
        "morning_context": {
            "enabled": bool(refresh_morning_context),
            "loaded_at_utc": morning_context.get("loaded_at_utc", ""),
            "macro_path": str(morning_context.get("macro_path") or ""),
            "macro_enrichment_path": str(morning_context.get("macro_enrichment_path") or ""),
            "catalyst_calendar_path": str(morning_context.get("catalyst_calendar_path") or ""),
            "warnings": morning_context.get("warnings") or [],
        },
        "rows": rows,
    }
    _write_json(packet_path, packet)
    if not output_path:
        try:
            from contracts.lab_control import write_final_opportunity_book, write_final_run_manifest
            _manifest = write_final_run_manifest(rid, runs_root, pipeline_mode="MORNING_VALIDATION")
            _lab_payload = write_final_opportunity_book(rid, rows, _manifest, runs_root)
            print(
                f"[MV] Lab/Interpreter triage regenerated from morning validation -> "
                f"{Path(_lab_payload.get('triage_csv_path', '')).name}",
                flush=True,
            )
        except Exception as _lab_exc:
            log.warning("Morning Lab/Interpreter handoff regeneration failed: %s", _lab_exc)
    if not output_path:
        try:
            from dropoff_audit import build_dropoff_audit

            build_dropoff_audit(rid, runs_dir=runs_root)
        except Exception:
            pass
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AVSHUNTER Morning Thesis Validator")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--candidates-path", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--max-signals", type=int, default=0, help="Maximum rows to validate; 0 means no cap.")
    parser.add_argument("--tiers", default=None)
    parser.add_argument("--live", action="store_true", default=True, help="Use live market data. This is the production default.")
    parser.add_argument("--paper", action="store_true", help="Use paper/synthetic live snapshots for simulation only.")
    parser.add_argument("--live-data-path", default=None)
    parser.add_argument("--include-high-priority-wait", action="store_true")
    parser.add_argument("--macro-path", default=str(DEFAULT_MACRO_PATH))
    parser.add_argument("--macro-enrichment-path", default=str(DEFAULT_MACRO_ENRICHMENT_PATH))
    parser.add_argument("--catalyst-calendar-path", default=str(DEFAULT_CATALYST_CALENDAR_PATH))
    parser.add_argument("--no-morning-context-refresh", action="store_true")
    args = parser.parse_args()

    rows = run_morning_validation(
        candidates_path=args.candidates_path,
        output_path=args.output_path,
        run_id=args.run_id,
        max_signals=args.max_signals,
        tier_filter=args.tiers,
        live_mode=not args.paper,
        runs_dir=args.runs_dir,
        live_data_path=args.live_data_path,
        paper_mode=args.paper,
        pipeline_mode="EOD_SIMULATION" if args.paper else "MORNING_VALIDATION",
        include_high_priority_wait=args.include_high_priority_wait,
        refresh_morning_context=not args.no_morning_context_refresh,
        macro_path=args.macro_path,
        macro_enrichment_path=args.macro_enrichment_path,
        catalyst_calendar_path=args.catalyst_calendar_path,
    )
    resolved_run_id = rows[0].get("run_id") if rows else (args.run_id or latest_run_id(Path(args.runs_dir)) or "latest")
    summary = build_summary(resolved_run_id, rows, len(rows))
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
