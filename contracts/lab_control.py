"""Final control helpers for the AVSHUNTER Intelligence Lab.

This module is deliberately small and deterministic. It does not create
signals; it validates and normalises the committed pipeline baton for the
human execution cockpit.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from contracts.direction_governance import validate_direction_record
from contracts.dynamic_session_contract import DataExceptionReason
from contracts.options_liquidity_execution_guard import (
    action_is_within_guard,
    evaluate_olm_execution_guard,
)
from contracts.selected_contract_economics import (
    canonical_structure as canonical_selected_structure,
    contract_symbols as selected_contract_symbols_from_value,
    economics_evaluation_id as selected_economics_evaluation_id,
    normalise_occ_symbol as normalise_selected_occ_symbol,
    parse_occ_symbol as parse_selected_occ_symbol,
)
from contracts.long_option_policy import (
    LONG_OPTION_ALLOWED_INSTRUMENTS,
    LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT,
    LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT,
)
from domain.execution_authority import execution_authority_contract_violations


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
    "lab_schema_version",
    "pipeline_mode",
    "run_id",
    "ticker",
    "trade_idea_id",
    "lab_rank",
    "priority_rank",
    "lab_verdict",
    "lab_tradeable",
    "prep_permission",
    "lab_status",
    "lab_execution_status",
    "final_action",
    "gate_reason",
    "gate_warnings",
    "gate_version",
    "execution_eligibility_state",
    "execution_authority_ceiling",
    "execution_authority_source",
    "execution_authority_policy_version",
    "final_capital_permission",
    "execution_requires_human_approval",
    "execution_authorized",
    "execution_can_grant_capital",
    "eod_candidate_status",
    "execution_category",
    "action_category",
    "campaign_verdict",
    "display_execution_mode",
    "position_size_display",
    "lab_coherence_status",
    "lab_coherence_flags",
    "canonical_direction",
    "dir_calc_version",
    "direction_policy_version",
    "direction_policy_sha256",
    "discovery_direction_preliminary",
    "governed_direction",
    "governed_direction_authority",
    "governed_direction_basis",
    "final_direction",
    "direction_resolution_path",
    "direction_governance_status",
    "direction_resolution_confidence",
    "direction_resolution_call_score",
    "direction_resolution_put_score",
    "direction_resolution_winning_share",
    "direction_resolution_margin",
    "direction_resolution_evidence_count",
    "direction_resolution_evidence_json",
    "direction_resolution_chain_json",
    "direction_excluded_evidence_json",
    "governed_direction_record_json",
    "governed_direction_record_sha256",
    "direction_integrity_status",
    "check_direction_integrity_pass",
    "check_direction_integrity_reason",
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
    "phase",
    "intent",
    "tier",
    "regime",
    "composite_score",
    "instrument",
    "contract_symbol",
    "contract_data_state",
    "contract_source",
    "morning_selected_contract_symbol",
    "selected_structure",
    "selected_structure_id",
    "selected_contract_symbols",
    "selected_quote_snapshot_id",
    "selected_quote_timestamp_utc",
    "selected_structure_hydration_status",
    "selected_structure_hydration_reason",
    "selected_structure_hydration_schema_version",
    "selected_legs_json",
    "contract_bid_size",
    "contract_ask_size",
    "contract_size_quality",
    "contract_quote_quality",
    "morning_contract_bid",
    "morning_contract_ask",
    "morning_contract_mid",
    "morning_contract_spread_pct",
    "morning_contract_bid_size",
    "morning_contract_ask_size",
    "morning_quote_dataset_id",
    "morning_quote_timestamp_utc",
    "current_contract_bid",
    "current_contract_ask",
    "current_contract_mid",
    "current_contract_spread_pct",
    "current_contract_bid_size",
    "current_contract_ask_size",
    "current_quote_dataset_id",
    "current_quote_timestamp_utc",
    "contract_bid_change",
    "contract_bid_change_pct",
    "contract_ask_change",
    "contract_ask_change_pct",
    "contract_mid_change",
    "contract_mid_change_pct",
    "contract_spread_change_pp",
    "contract_bid_size_change",
    "contract_ask_size_change",
    "comparison_status",
    "change_status",
    "underlying_nbbo_bid",
    "underlying_nbbo_ask",
    "underlying_nbbo_mid",
    "underlying_nbbo_bid_size",
    "underlying_nbbo_ask_size",
    "underlying_nbbo_timestamp_utc",
    "underlying_nbbo_source",
    "underlying_nbbo_dataset_id",
    "underlying_nbbo_quality",
    "contract_repair_status",
    "contract_repair_required",
    "contract_repair_reason",
    "contract_repair_action",
    "contract_repair_live_action",
    "contract_repair_alternative_used",
    "lifecycle_contract_version",
    "thesis_id",
    "thesis_state",
    "liquidity_state",
    "morning_transition_state",
    "recovery_disposition",
    "executable_now",
    "moneyness_state",
    "delta_band",
    "minimum_required_dte",
    "dte_buffer_sessions",
    "atm_distance_sigma",
    "remaining_runway_pct",
    "remaining_runway_state",
    "maturation_state_1d",
    "maturation_state_2d",
    "maturation_state_3d",
    "maturation_score_1d",
    "maturation_score_2d",
    "maturation_score_3d",
    "maturation_score_is_probability",
    "maturation_execution_authority",
    "olm_guard_version",
    "olm_guard_disposition",
    "olm_guard_reason",
    "olm_guard_pass",
    "olm_guard_state_consistent",
    "previous_contract_symbol",
    "contract_changed",
    "contract_selection_reason",
    "quote_as_of",
    "quote_freshness",
    "bar_data_source",
    "bar_data_asof",
    "bar_data_days_old",
    "bar_evidence_state",
    "bar_evidence_reason",
    "is_stale",
    "option_chain_dataset_id",
    "option_chain_provider",
    "option_chain_resolution",
    "selected_quote_dataset_id",
    "liquidity_persistence_status",
    "morning_liquidity_persistence_status",
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
    "options_research_route",
    "options_research_permission",
    "entry_reason",
    "positive_factors",
    "negative_factors",
    "sector",
    "gics_sector",
    "gics_sector_norm",
    "sector_etf",
    "rr_predicted",
    "rr_underlying",
    "rr_premium_expected",
    "rr_contract_symbol",
    "rr_evaluation_id",
    "rr_recompute_status",
    "rr_recompute_reason",
    "selected_contract_economics_ready",
    "execution_viability_policy_version",
    "execution_viability_state",
    "execution_viability_reason",
    "execution_viability_eligible",
    "execution_viability_reviewable",
    "execution_viability_contract_symbol",
    "execution_viability_bid",
    "execution_viability_ask",
    "execution_viability_spread_pct",
    "execution_viability_spread_denominator",
    "monetisability_status",
    "monetisability_state",
    "monetisability_reason",
    "monetisability_eligible",
    "monetisability_calculation_version",
    "monetisability_contract_symbol",
    "monetisability_evaluation_id",
    "monetisability_entry_ask",
    "monetisability_strike",
    "monetisability_breakeven_spot",
    "monetisability_structural_target_spot",
    "monetisability_target_intrinsic_per_share",
    "monetisability_target_profit_per_share",
    "monetisability_target_profit_pct",
    "monetisability_minimum_profit_pct",
    "monetisability_authority",
    "monetisability_valuation_basis",
    "monetisability_hard_execution_authority",
    "ev3_selected_contract_aligned",
    "rr_calculation_version",
    "rr_entry_debit_per_share",
    "rr_target_value_per_share",
    "ev_predicted",
    "ev3_data_state",
    "ev3_status",
    "ev3_reason_code",
    "ev3_reason_detail",
    "ev3_absolute_state",
    "ev3_shadow_only",
    "ev3_structure",
    "ev3_contract_symbol",
    "ev3_evaluation_id",
    "economics_comparable",
    "economics_mismatch_reason",
    "ev3_state_match_type",
    "ev3_state_similarity",
    "ev3_n_effective",
    "ev3_p_target",
    "ev3_p_stop",
    "ev3_p_timeout",
    "ev3_ev_conservative_return",
    "ev3_ev_lower_bound_return",
    "ev3_uncertainty_total_return",
    "win_prob_predicted",
    "actuarial_match_method",
    "actuarial_match_type",
    "actuarial_ev_weight",
    "behaviour_state_key",
    "behaviour_state_hash",
    "catalyst_overlay",
    "catalyst_type",
    "catalyst_date",
    "catalyst_truth_score",
    "catalyst_direction_bias",
    "catalyst_event_status",
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
    "macro_data_role",
    "macro_packet_id",
    "macro_packet_sha256",
    "macro_source_fingerprint",
    "macro_as_of_utc",
    "macro_session_date",
    "macro_freshness",
    "macro_data_quality",
    "macro_context_state",
    "macro_sector_alignment",
    "macro_ticker_alignment",
    "macro_rates_context",
    "macro_usd_context",
    "macro_volatility_context",
    "macro_liquidity_context",
    "macro_bond_context",
    "macro_auction_risk",
    "macro_active_themes",
    "macro_event_guards",
    "macro_directional_pressure",
    "macro_conflicts",
    "macro_plain_language_advisory",
    "macro_authority",
    "eil_signal_verdict",
    "eil_v3_verdict",
    "eil_composite_eod",
    "entry_plan",
    "invalidation_price",
    "invalidation_state",
    "invalidation_source",
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
    "contract_vega",
    "contract_iv",
    "contract_bid",
    "contract_ask",
    "contract_mid",
    "contract_oi",
    "contract_volume",
    "options_score",
    "iv_rank",
    "ivp_label",
    "atm_iv",
    "hv_30d",
    "iv_vs_hv",
    "term_structure",
    "theta_drag_pct",
    "vega_risk_pct",
    "theta_constrained",
    "contract_mark_synthetic",
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
    "wbs_pcr_volume_state",
    "wbs_data_state",
    "wbs_break_direction",
    "wbs_momentum_alignment_state",
    "convexity_data_state",
    "convexity_score",
    "convexity_campaign",
    "readiness_stage",
    "readiness_label",
    "readiness_enter_now",
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
    "trigger_price_source",
    "trigger_evidence",
    "trigger_primary",
    "trigger_quality",
    "trigger_score",
    "trigger_codes",
    "trigger_data_state",
    "hard_vetoes",
    "options_hard_vetoes",
    "advisory_flags",
    "garch_data_state",
    "garch_method",
    "garch_forecast_vol",
    "garch_iv_tailwind_score",
    "garch_jump_risk_flag",
    "garch_forecast_confidence",
    "garch_expected_move_1_5d",
    "garch_expected_move_6_10d",
    "garch_expected_move_11_20d",
    "garch_price_bars_used",
    "morning_data_state",
    "data_quality_flags",
    "field_provenance_json",
    "pcr_vol_status",
    "pcr_vol_missing_reason",
    "pcr_vol",
    "win_rate_source",
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

# Governed Intelligence Lab execution policy. A quote above the executable
# ceiling is never labelled GO. The Morning Gate's existing 25% absolute
# ceiling remains the boundary between a human liquidity review and a block.
LAB_EXECUTABLE_SPREAD_MAX_PCT = LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT
LAB_ABSOLUTE_SPREAD_MAX_PCT = LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT
LAB_EXECUTABLE_INSTRUMENTS = LONG_OPTION_ALLOWED_INSTRUMENTS

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


def first_trigger_category(
    sig: Dict[str, Any], *keys: str, default: Any = ""
) -> Any:
    """Return a trigger category while preserving the valid ``NONE`` state."""
    for key in keys:
        value = sig.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text.upper() in {"", "NAN", "NULL", "N/A", "NA"}:
            continue
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


def _lab_structure_policy(sig: Dict[str, Any], contract_symbol: Any) -> tuple[str, str, str]:
    """Classify a selected structure under the production long-only mandate.

    Returns ``(state, route, reason)``. Non-production structures remain in the
    Lab as research rows, but they cannot receive executable permission.
    """
    symbols = _contract_symbols(contract_symbol)
    raw_instrument = _u(first(sig, "instrument", "options_strategy", "sb_instrument_now"))
    raw_structure = _u(first(sig, "selected_structure", "options_strategy", "instrument"))
    raw_policy_text = f"{raw_structure}|{raw_instrument}"
    non_long_tokens = (
        "STRANGLE", "STRADDLE", "SPREAD", "VERTICAL", "COMPOSITE",
        "MULTI_LEG", "IRON_", "BUTTERFLY", "CONDOR", "CALENDAR",
    )
    if len(symbols) > 1 or any(token in raw_policy_text for token in non_long_tokens):
        structure = _canonical_structure(raw_structure or raw_instrument, symbols)
        return (
            "RESEARCH_ONLY",
            "RESEARCH_ONLY_NON_LONG_SINGLE",
            f"NON_PRODUCTION_OPTIONS_STRUCTURE:{structure}",
        )
    if not symbols:
        return "NO_SELECTED_CONTRACT", "CONTRACT_REPAIR", "NO_SELECTED_CONTRACT"
    try:
        parsed = parse_selected_occ_symbol(symbols[0])
    except ValueError:
        return "INVALID", "CONTRACT_REPAIR", "INVALID_OCC_CONTRACT_SYMBOL"

    structure = _canonical_structure(raw_structure or raw_instrument, symbols)
    direction_side = _side_from_value(first(sig, "canonical_direction", "direction"))
    instrument_side = _side_from_value(raw_instrument)
    # Canonical direction outranks a stale legacy instrument label. The Lab's
    # materializer already normalises LONG_CALL/LONG_PUT from that direction;
    # execution validity is therefore contract-side vs governed-direction.
    governed_side = direction_side or instrument_side
    governed_instrument = f"LONG_{governed_side}" if governed_side else ""
    if structure != "LONG_SINGLE" or governed_instrument not in LAB_EXECUTABLE_INSTRUMENTS:
        return (
            "RESEARCH_ONLY",
            "RESEARCH_ONLY_NON_LONG_SINGLE",
            f"NON_PRODUCTION_OPTIONS_STRUCTURE:{structure}",
        )
    if parsed["side"] != governed_side:
        return "INVALID", "CONTRACT_REPAIR", "LONG_SINGLE_DIRECTION_SIDE_MISMATCH"

    hydration = _u(sig.get("selected_structure_hydration_status"))
    if hydration and hydration != "COMPLETE":
        return "INVALID", "CONTRACT_REPAIR", "LONG_SINGLE_HYDRATION_INCOMPLETE"
    return "EXECUTABLE", "PRODUCTION_LONG_SINGLE", ""


def _normalise_occ_symbol(value: Any) -> str:
    return normalise_selected_occ_symbol(value)


def _contract_symbols(value: Any) -> List[str]:
    """Return ordered, normalised OCC symbols from single/composite values."""
    return selected_contract_symbols_from_value(value)


def _canonical_structure(value: Any, symbols: List[str]) -> str:
    return canonical_selected_structure(value, symbols)


def _economics_evaluation_id(
    ticker: Any,
    direction: Any,
    structure: Any,
    symbols: List[str],
) -> str:
    return selected_economics_evaluation_id(ticker, direction, structure, symbols)


def _quote_snapshot_id(sig: Dict[str, Any], structure_id: str) -> str:
    if not structure_id:
        return ""
    values = [
        structure_id,
        _s(first(sig, "quote_timestamp", "contract_quote_timestamp", "live_options_fetched_at", "gate_checked_at_utc")),
        _s(first(sig, "contract_bid", "live_contract_bid", "bid")),
        _s(first(sig, "contract_ask", "live_contract_ask", "ask")),
        _s(first(sig, "contract_mid", "premium_mid", "live_contract_mid", "mid")),
        _s(first(sig, "contract_source", "live_options_source", "quote_source")),
    ]
    return f"QUOTE1:{hashlib.sha256('|'.join(values).encode('utf-8')).hexdigest()[:24]}"


def _economics_identity(
    sig: Dict[str, Any],
    selected_contract: Any = "",
    selected_instrument: Any = "",
) -> Dict[str, Any]:
    """Bind selected contract and monetisability to one comparable structure."""
    # The canonical selected contract passed by the materializer must outrank
    # any identity fields copied from an earlier producer.  Otherwise a morning
    # contract replacement can retain the previous contract's identity.
    selected_value = (
        selected_contract
        if not _is_missing(selected_contract)
        else first(sig, "selected_contract_symbols")
    )
    selected_symbols = _contract_symbols(selected_value)
    selected_structure_value = first(sig, "selected_structure")
    if _is_missing(selected_structure_value) and len(selected_symbols) > 1:
        selected_structure_value = _s(selected_value).split(":", 1)[0]
    if _is_missing(selected_structure_value) and not _is_missing(selected_instrument):
        selected_structure_value = selected_instrument
    if _is_missing(selected_structure_value):
        selected_structure_value = first(sig, "options_strategy")
    selected_structure = _canonical_structure(selected_structure_value, selected_symbols)
    selected_id = _economics_evaluation_id(
        sig.get("ticker"), first(sig, "canonical_direction", "direction"),
        selected_structure, selected_symbols,
    )
    monetisability_status = _u(sig.get("monetisability_status"))
    monetisability_contract = first(sig, "monetisability_contract_symbol")
    monetisability_symbols = _contract_symbols(monetisability_contract)
    monetisability_id = _s(sig.get("monetisability_evaluation_id")) or _economics_evaluation_id(
        sig.get("ticker"), first(sig, "canonical_direction", "direction"),
        selected_structure, monetisability_symbols,
    )

    ev_contract = first(sig, "ev3_contract_symbol")
    ev_symbols = _contract_symbols(ev_contract)
    ev_structure = _canonical_structure(sig.get("ev3_structure"), ev_symbols)
    ev_id = _economics_evaluation_id(
        sig.get("ticker"), first(sig, "canonical_direction", "direction"),
        ev_structure, ev_symbols,
    )
    ev_status = _u(sig.get("ev3_status"))
    ev_evaluated = ev_status.startswith("EVALUATED") and not _is_missing(
        sig.get("ev3_ev_conservative_return")
    )

    comparable = False
    ev_aligned = False
    reason = ""
    if not selected_symbols:
        reason = "NO_SELECTED_CONTRACT"
    elif monetisability_status != "COMPLETE":
        reason = "MONETISABILITY_NOT_EVALUATED_FOR_SELECTED_CONTRACT"
    elif not monetisability_symbols:
        reason = "MONETISABILITY_CONTRACT_IDENTITY_MISSING"
    elif selected_symbols != monetisability_symbols:
        reason = "MONETISABILITY_SELECTED_CONTRACT_MISMATCH"
    elif selected_id != monetisability_id:
        reason = "MONETISABILITY_EVALUATION_ID_MISMATCH"
    else:
        comparable = True
    ev_aligned = bool(
        ev_evaluated
        and ev_symbols
        and selected_structure == ev_structure
        and selected_symbols == ev_symbols
        and selected_id == ev_id
    )

    upstream_snapshot_id = _s(sig.get("selected_quote_snapshot_id"))
    return {
        "selected_structure_id": selected_id,
        "selected_contract_symbols": _json_safe(selected_symbols),
        # The producer's quote identifier is immutable lineage. Regenerate it
        # only for legacy rows that arrived without an upstream identity.
        "selected_quote_snapshot_id": upstream_snapshot_id or _quote_snapshot_id(sig, selected_id),
        "monetisability_contract_symbol": monetisability_contract,
        "monetisability_evaluation_id": monetisability_id,
        "ev3_contract_symbol": ev_contract,
        "ev3_evaluation_id": ev_id,
        "economics_comparable": comparable,
        "economics_mismatch_reason": reason,
        "ev3_selected_contract_aligned": ev_aligned,
    }


def _enforce_economics_identity(
    row: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
) -> None:
    upstream_snapshot_id = _s(row.get("selected_quote_snapshot_id"))
    identity = _economics_identity(
        row,
        selected_contract=row.get("contract_symbol"),
        selected_instrument=row.get("instrument"),
    )
    row.update(identity)
    if provenance is not None:
        for field in identity:
            if field == "selected_quote_snapshot_id" and upstream_snapshot_id:
                provenance.setdefault(field, "upstream:selected_quote_snapshot_id")
                continue
            provenance[field] = "governed_materializer:contract_economics_identity"

    if identity["economics_comparable"]:
        if not identity.get("ev3_selected_contract_aligned"):
            row["ev_predicted"] = ""
        return
    # A row without a selected contract is already non-executable and does not
    # need an additional economics lock.  Any selected-contract mismatch or
    # missing evaluation is fail-closed so the Lab cannot imply comparability.
    if not identity["selected_structure_id"]:
        row["ev_predicted"] = ""
        return

    reason = identity["economics_mismatch_reason"]
    row["ev_predicted"] = ""
    row["lab_coherence_status"] = "ECONOMICS_CONTRACT_MISMATCH"
    row["lab_coherence_flags"] = _append_flag(
        row.get("lab_coherence_flags"), "ECONOMICS_CONTRACT_MISMATCH"
    )
    row["execution_lock_reason"] = _append_flag(
        row.get("execution_lock_reason"), reason
    )
    is_tradeable = row.get("lab_tradeable") is True or _u(row.get("lab_tradeable")) in {
        "TRUE", "1", "YES",
    }
    # Morning permission is immutable after the Execution Gate.  Exact
    # reconciliation fails the handoff upstream if this identity is wrong.
    if not _u(row.get("final_action")) and (
        is_tradeable or _u(row.get("lab_verdict")) in {"GO", "GO_LIMIT", "PROBE"}
    ):
        row["lab_tradeable"] = False
        row["lab_verdict"] = "CONTRACT_REPAIR"
        row["lab_status"] = "CONTRACT_REPAIR"
        row["lab_execution_status"] = "CONTRACT_REPAIR"
        row["action_category"] = "CONTRACT_REPAIR"


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
    market_profile = run_dir / "market_profile"
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
        "completed_market_profile": str(
            _glob_latest(market_profile, f"completed_profile_summary_{run_id}.json") or ""
        ),
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


def _semantic_handoff_health(
    system_defects: Dict[str, Any],
    population: int,
) -> Dict[str, Any]:
    """Summarise value-level handoff completeness independently of schema health."""
    missing = dict(system_defects.get("missing_selected_handoff", {}) or {})
    defect_count = max([int(value or 0) for value in missing.values()] or [0])
    denominator = max(int(population or 0), 1)
    score = max(0, min(100, round(100.0 * (1.0 - defect_count / denominator))))
    return {
        "semantic_coverage_score": score,
        "pipeline_semantic_health": (
            "PASS" if defect_count == 0 else "DEGRADED" if score >= 80 else "FAILED"
        ),
        "semantic_defect_count": defect_count,
        "missing_selected_handoff": missing,
    }


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
        "morning_candidates": _read_csv_rows(Path(output_files["morning_candidates"])) if output_files.get("morning_candidates") else [],
    }
    macro_payload = _read_json(Path(output_files["macro"])) if output_files.get("macro") else {}
    profile_payload = _read_json(Path(output_files["completed_market_profile"])) if output_files.get("completed_market_profile") else {}
    run_meta = _read_json(run_dir / "run_meta.json")
    ev3_status_path = run_dir / "ev3_shadow" / f"ev3_shadow_phase_status_{run_id}.json"
    ev3_status = _read_json(ev3_status_path) if ev3_status_path.exists() else {}
    system_defects = dict(ev3_status.get("system_defects", {}) or {})

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
    profile_flag = (run_meta.get("resolved_feature_flags") or {}).get(
        "AVSHUNTER_COMPLETED_PROFILE_STAGE_ENABLED", False
    )
    profile_required = profile_flag is True or _u(profile_flag) in {"1", "TRUE", "YES", "ON"}
    if profile_payload:
        profile_ok = bool(
            profile_payload.get("reconciled")
            and not profile_payload.get("systemic_failure")
            and int(profile_payload.get("completed") or 0) > 0
        )
        phase_status["completed_market_profile"] = "PASS" if profile_ok else "FAIL"
        row_counts["completed_market_profile"] = int(profile_payload.get("completed") or 0)
    else:
        phase_status["completed_market_profile"] = "MISSING" if profile_required else "NOT_REQUIRED"
        row_counts["completed_market_profile"] = 0

    stale_flags: List[str] = []
    conflict_flags: List[str] = []
    fatal_flags: List[str] = []

    if phase_status["eil"] in {"MISSING", "FAIL"}:
        fatal_flags.append("EIL_OUTPUT_MISSING_OR_INVALID")
    if phase_status["options"] == "MISSING":
        stale_flags.append("OPTIONS_OUTPUT_MISSING_EXECUTION_DOWNGRADED")
    if profile_required and phase_status["completed_market_profile"] != "PASS":
        fatal_flags.append("COMPLETED_MARKET_PROFILE_MISSING_OR_UNUSABLE")
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

    # Semantic completeness is separate from file/schema completion.  The EV3
    # phase already publishes selected-handoff defects; surface them in the run
    # health contract instead of allowing a technically complete run to report
    # 100 while hundreds of rows lack usable thesis geometry.
    # Selected-candidate semantic health must be calculated over the actual
    # handoff population, not all Options rows. Upstream defects remain visible
    # in their stage diagnostics but cannot falsely degrade a clean Lab book.
    selected_rows = rows_by_phase.get("morning_candidates", [])
    if selected_rows:
        missing_invalidation = 0
        for row in selected_rows:
            direction = _u(
                row.get("governed_direction")
                or row.get("canonical_direction")
                or row.get("direction")
                or row.get("options_direction")
            )
            invalidation = _f(
                row.get("invalidation_spot")
                if not _is_missing(row.get("invalidation_spot"))
                else row.get("invalidation_price"),
                0.0,
            )
            invalidation_state = _u(row.get("invalidation_state"))
            if direction in {"CALL", "PUT"} and (
                invalidation <= 0.0
                or invalidation_state in {
                    "MISSING", "UNAVAILABLE", "MISSING_AUTHORITATIVE_STOP",
                    "MISSING_GOVERNED_INVALIDATION",
                }
            ):
                missing_invalidation += 1
        selected_missing = dict(system_defects.get("missing_selected_handoff", {}) or {})
        selected_missing["invalidation_spot"] = missing_invalidation
        system_defects["missing_selected_handoff"] = selected_missing
    semantic_population = (
        len(selected_rows)
        if selected_rows
        else max(row_counts.get("options", 0), row_counts.get("eil", 0), 1)
    )
    semantic_health = _semantic_handoff_health(system_defects, semantic_population)
    semantic_defect_count = int(semantic_health["semantic_defect_count"])
    semantic_coverage_score = int(semantic_health["semantic_coverage_score"])
    missing_selected_handoff = dict(semantic_health["missing_selected_handoff"])
    if semantic_defect_count:
        stale_flags.append(
            f"SEMANTIC_HANDOFF_DEFECTS:{semantic_defect_count}"
        )

    health = 100
    health -= 30 * len(fatal_flags)
    health -= 8 * sum(1 for status in phase_status.values() if status == "MISSING")
    health -= 5 * sum(1 for status in phase_status.values() if status == "WARN")
    health -= 3 * len(stale_flags)
    health = max(0, min(100, health))
    health = min(health, semantic_coverage_score)

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
    pipeline_semantic_health = str(semantic_health["pipeline_semantic_health"])

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
        "semantic_coverage_score": semantic_coverage_score,
        "pipeline_semantic_health": pipeline_semantic_health,
        "semantic_defect_count": semantic_defect_count,
        "missing_selected_handoff": missing_selected_handoff,
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
        "system_defects": system_defects,
        "ev3_production_evidence": bool(ev3_status.get("production_evidence", False)),
        "ev3_production_authority": False,
        "v5_colab_decommissioned": True,
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
        "GO": {"GO_LIMIT", "PROBE", "MANUAL_LIQUIDITY_REVIEW", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "GO_LIMIT": {"MANUAL_LIQUIDITY_REVIEW", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "PROBE": {"MANUAL_LIQUIDITY_REVIEW", "ARMED", "CONTRACT_REPAIR", "WAIT", "BLOCKED"},
        "ARMED": {"WAIT", "BLOCKED"},
        "WAIT": {"ARMED", "BLOCKED"},
        "CONTRACT_REPAIR": {"BLOCKED"},
    }
    if lab in allowed_downgrades.get(perm, set()):
        reason = "; ".join(soft[:4]) or "Downstream execution safety gate downgraded the Morning Validator route."
        return "ALIGNED_DOWNGRADED", f"Morning permission={perm}, Lab verdict={lab}. {reason}"

    return "CONFLICT", f"Morning permission={perm} does not align with Lab verdict={lab}."


def _resolve_execution_gate_authority(
    sig: Dict[str, Any],
    source: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Map the governed Execution Gate action without re-adjudicating it.

    EOD rows have no ``final_action`` and continue through the research view
    resolver below. Morning rows must preserve the exact Execution Gate baton.
    """
    action = _u(sig.get("final_action"))
    mapping = {
        "BUY_NOW": ("GO", True),
        "BUY_SMALL": ("GO_LIMIT", True),
        "CONTRACT_REPAIR": ("CONTRACT_REPAIR", False),
        "MANUAL_REVIEW": ("MANUAL_REVIEW", False),
        "BLOCK": ("BLOCKED", False),
        "SKIP": ("BLOCKED", False),
    }
    if action not in mapping:
        return None

    authority_violations = execution_authority_contract_violations(sig)
    if authority_violations:
        action = "BLOCK"
        sig = {
            **sig,
            "final_action": action,
            "gate_reason": "EXECUTION_AUTHORITY_CONTRACT_VIOLATION:"
            + "|".join(authority_violations),
        }

    verdict, tradeable = mapping[action]
    gate_reason = _s(sig.get("gate_reason"))
    warnings = [
        item.strip()
        for item in _s(sig.get("gate_warnings")).split(",")
        if item.strip()
    ]
    monetisability_state = _u(sig.get("monetisability_state"))
    if monetisability_state and monetisability_state != "MONETISABLE":
        warnings.append(f"MONETISABILITY:{monetisability_state}")
    structure_state, route, structure_reason = _lab_structure_policy(
        sig,
        first(
            sig,
            "morning_selected_contract_symbol",
            "contract_symbol",
            "live_contract_symbol",
        ),
    )
    research_permission = (
        "EXECUTABLE_SUBJECT_TO_GATES"
        if structure_state == "EXECUTABLE"
        else "NOT_EXECUTABLE"
    )
    conflict_state = "CLEAN" if tradeable and not warnings else "SOFT_CONFLICT"
    veto_flags = [] if action not in {"BLOCK", "SKIP"} else [gate_reason or "EXECUTION_GATE_BLOCK"]
    lock_reason = "" if tradeable else (gate_reason or action)
    source["final_action"] = action
    source["gate_reason"] = gate_reason
    source["lab_execution_status"] = action
    return {
        "lab_verdict": verdict,
        "lab_tradeable": tradeable,
        "lab_execution_status": action,
        "conflict_state": conflict_state,
        "conflict_flags": [f"SOFT:{item}" for item in warnings],
        "advisory_flags": warnings + ([structure_reason] if structure_reason else []),
        "veto_flags": veto_flags,
        "spread_policy_state": _u(first(sig, "contract_spread_policy_state", "spread_policy_state")),
        "options_research_route": route,
        "options_research_permission": research_permission,
        "execution_lock_reason": lock_reason,
        "requires_live_validation": action in {"CONTRACT_REPAIR", "MANUAL_REVIEW"},
        "prep_permission": "",
        "morning_lab_alignment_status": "ALIGNED_EXECUTION_GATE",
        "morning_lab_alignment_reason": f"Execution Gate final_action={action} mapped to Lab {verdict}.",
        "source_verdicts": source,
    }


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
        "final_action": _u(sig.get("final_action")),
        "gate_reason": _u(sig.get("gate_reason")),
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
    advisory: List[str] = []

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

    if not veto_flags:
        execution_authority = _resolve_execution_gate_authority(sig, source)
        if execution_authority is not None:
            return execution_authority

    contract_symbol = first(sig, "morning_selected_contract_symbol", "live_selected_contract_symbol", "contract_symbol", "live_contract_symbol", "evening_contract_symbol", "option_symbol", "recommended_contract", "preferred_contract", "opt__recommended_contract")
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
    structure_policy_state, options_research_route, structure_policy_reason = _lab_structure_policy(
        sig, contract_symbol
    )
    options_research_permission = (
        "EXECUTABLE_SUBJECT_TO_GATES"
        if structure_policy_state == "EXECUTABLE"
        else "NOT_EXECUTABLE"
    )
    if looks_actionable and structure_policy_state == "RESEARCH_ONLY":
        soft.append("NON_PRODUCTION_OPTIONS_STRUCTURE_RESEARCH_ONLY")
        advisory.append(structure_policy_reason)
    elif looks_actionable and structure_policy_state == "INVALID":
        soft.append("SELECTED_LONG_SINGLE_CONTRACT_REPAIR_REQUIRED")
        flags.append(structure_policy_reason)
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

    spread = _f(first(sig, "live_contract_spread_pct", "live_spread_pct", "contract_spread_pct", "spread_pct", "final_option_spread_pct", "opt__spread_pct_mid", "opt__spread_pct"), -1.0)
    spread_policy_state = "UNAVAILABLE"
    if spread > 0:
        pct = spread * 100 if spread <= 1 else spread
        if pct > LAB_ABSOLUTE_SPREAD_MAX_PCT:
            spread_policy_state = "BLOCKED_ABOVE_ABSOLUTE_MAX"
            flags.append("SPREAD_TOO_WIDE")
            veto_flags.append("SPREAD_TOO_WIDE")
        elif pct > LAB_EXECUTABLE_SPREAD_MAX_PCT:
            spread_policy_state = "MANUAL_LIQUIDITY_REVIEW"
            soft.append("MANUAL_LIQUIDITY_REVIEW")
        else:
            spread_policy_state = "EXECUTABLE"
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
    # R:R is retained only as research telemetry. It does not decide Lab
    # permission; Morning permission comes exclusively from final_action.
    if _f(first(sig, "ev2_ev_conf_adj", "eil_ev_net", "ev"), 0.0) < 0:
        advisory.append("NEGATIVE_EV")
    if source["ev_decision_hint"] == "AVOID" or source["ev_status"] in {"AVOID", "FAIL", "NEGATIVE_EV"}:
        advisory.append("EV_AVOID")
    elif source["ev_decision_hint"] == "WEAK":
        advisory.append("EV_WEAK")
    elif source["ev_decision_hint"] not in {"STRONG", "MODERATE"}:
        advisory.append("EV_NOT_EVALUATED")
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
        "MANUAL_LIQUIDITY_REVIEW",
        "NON_PRODUCTION_OPTIONS_STRUCTURE_RESEARCH_ONLY",
        "SELECTED_LONG_SINGLE_CONTRACT_REPAIR_REQUIRED",
    }
    has_critical_soft = any(item in critical_soft for item in soft)

    if veto_flags:
        verdict = "BLOCKED"
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

    # Explicit Lab-only execution policy overrides. These preserve the row for
    # research and manual review while preventing an executable GO label.
    if not veto_flags and structure_policy_state == "RESEARCH_ONLY":
        verdict = "WAIT"
        tradeable = False
        conflict_state = "SOFT_CONFLICT"
        lock_reason = structure_policy_reason
    elif not veto_flags and structure_policy_state == "INVALID":
        verdict = "CONTRACT_REPAIR"
        tradeable = False
        conflict_state = "SOFT_CONFLICT"
        lock_reason = structure_policy_reason
    elif not veto_flags and spread_policy_state == "MANUAL_LIQUIDITY_REVIEW":
        verdict = "MANUAL_LIQUIDITY_REVIEW"
        tradeable = False
        conflict_state = "SOFT_CONFLICT"
        lock_reason = (
            f"Spread exceeds {LAB_EXECUTABLE_SPREAD_MAX_PCT:.0f}% executable ceiling "
            f"but is within {LAB_ABSOLUTE_SPREAD_MAX_PCT:.0f}% review ceiling."
        )

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
        "advisory_flags": advisory,
        "veto_flags": veto_flags,
        "spread_policy_state": spread_policy_state,
        "options_research_route": options_research_route,
        "options_research_permission": options_research_permission,
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
            "advisory_flags": _json_safe(resolved.get("advisory_flags", [])),
            "veto_flags": _json_safe(resolved["veto_flags"]),
            "spread_policy_state": resolved.get("spread_policy_state", ""),
            "options_research_route": resolved.get("options_research_route", ""),
            "options_research_permission": resolved.get("options_research_permission", ""),
            "execution_lock_reason": resolved["execution_lock_reason"],
            "requires_live_validation": resolved["requires_live_validation"],
            "prep_permission": resolved.get("prep_permission", ""),
            "morning_lab_alignment_status": resolved["morning_lab_alignment_status"],
            "morning_lab_alignment_reason": resolved["morning_lab_alignment_reason"],
            "source_verdicts_json": _json_safe(resolved["source_verdicts"]),
        }
    )
    return sig


def _enforce_olm_lab_guard(
    row: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
) -> None:
    """Verify the Execution Gate baton without granting positive authority."""

    pipeline_mode = _u(first(row, "pipeline_mode", "run_pipeline_mode"))
    require_contract = pipeline_mode in {"MORNING", "MORNING_VALIDATION", "LIVE"}
    decision = evaluate_olm_execution_guard(row, require_contract=require_contract)
    guard_fields = decision.as_fields()
    row.update(guard_fields)
    if provenance is not None:
        for field in guard_fields:
            provenance[field] = "governed_materializer:olm_execution_guard"

    if decision.disposition == "CONTINUE":
        return

    current_action = _u(row.get("final_action"))
    if not current_action:
        current_action = {
            "BLOCKED": "BLOCK",
            "CONTRACT_REPAIR": "CONTRACT_REPAIR",
            "MANUAL_REVIEW": "MANUAL_REVIEW",
        }.get(_u(row.get("lab_verdict")), "")
    if action_is_within_guard(current_action, decision) and current_action in {
        "BLOCK", "SKIP", "CONTRACT_REPAIR", "MANUAL_REVIEW",
    }:
        safe_action = current_action
    else:
        safe_action = decision.disposition

    if safe_action in {"BLOCK", "SKIP"}:
        verdict = "BLOCKED"
        status = "BLOCKED"
        display_mode = "NO_TRADE"
        size_display = "0% - OLM lifecycle block"
    elif safe_action == "CONTRACT_REPAIR":
        verdict = "CONTRACT_REPAIR"
        status = "CONTRACT_REPAIR"
        display_mode = "REPRICE_REQUIRED"
        size_display = "0% - exact contract economics required"
        row["economics_comparable"] = False
    else:
        safe_action = "MANUAL_REVIEW"
        verdict = "MANUAL_REVIEW"
        status = "MANUAL_REVIEW"
        display_mode = "MONITOR_ONLY"
        size_display = "0% - OLM monitoring only"

    row["lab_tradeable"] = False
    row["lab_verdict"] = verdict
    row["lab_status"] = status
    row["lab_execution_status"] = safe_action
    row["final_action"] = safe_action
    row["execution_category"] = status
    row["action_category"] = status
    row["display_execution_mode"] = display_mode
    row["position_size_display"] = size_display
    row["execution_lock_reason"] = decision.reason


def _enforce_execution_authority_lab_guard(
    row: Dict[str, Any],
    provenance: Optional[Dict[str, str]] = None,
) -> None:
    """Fail closed if a stamped final-gate baton is altered downstream."""

    violations = execution_authority_contract_violations(row)
    if not violations:
        return
    reason = "EXECUTION_AUTHORITY_CONTRACT_VIOLATION:" + "|".join(violations)
    row["lab_tradeable"] = False
    row["lab_verdict"] = "BLOCKED"
    row["lab_status"] = "BLOCKED"
    row["lab_execution_status"] = "BLOCK"
    row["final_action"] = "BLOCK"
    row["execution_category"] = "BLOCKED"
    row["action_category"] = "BLOCKED"
    row["display_execution_mode"] = "NO_TRADE"
    row["position_size_display"] = "0% - authority contract failed"
    row["execution_lock_reason"] = reason
    row["final_capital_permission"] = "NO"
    row["execution_authorized"] = False
    row["execution_can_grant_capital"] = False
    if provenance is not None:
        for field in (
            "lab_tradeable", "lab_verdict", "final_action",
            "execution_lock_reason", "final_capital_permission",
            "execution_authorized", "execution_can_grant_capital",
        ):
            provenance[field] = "governed_materializer:execution_authority_guard"


def _trade_idea_id(row: Dict[str, Any], run_id: str) -> str:
    ticker = _s(row.get("ticker")).upper() or "UNKNOWN"
    direction = _u(first(row, "final_direction", "canonical_direction", "resolved_direction", "direction", "options_direction", "selected_contract_side", "option_direction")) or "UNKNOWN"
    instrument = _u(first(row, "instrument", "options_strategy", "sb_instrument_now")) or "UNSPECIFIED"
    strike = _s(first(row, "strike", "contract_strike", "opt__contract_strike")) or "NA"
    expiry = _s(first(row, "expiry", "contract_expiry", "opt__contract_expiry")) or "NA"
    return f"{run_id}:{ticker}:{direction}:{instrument}:{strike}:{expiry}"


def opportunity_book_row(sig: Dict[str, Any], run_id: str, rank: int) -> Dict[str, Any]:
    canonical_direction = first(sig, "final_direction", "canonical_direction", "resolved_direction", "direction", "options_direction", "selected_contract_side", "option_direction")
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

    contract_selected = not _is_missing(aligned_contract)
    rr_value = first(sig, "rr_premium_expected", "rr_options", "option_rr")
    explicit_rr_contract = first(sig, "rr_contract_symbol")
    original_contract = first(sig, "contract_symbol_original", "morning_repaired_from_contract")
    repair_flag = _u(first(sig, "contract_repair_resolved_at_open", "morning_contract_repair_used")) in {
        "TRUE", "1", "YES",
    }
    contract_changed = repair_flag or (
        bool(_contract_symbols(original_contract))
        and _contract_symbols(original_contract) != _contract_symbols(aligned_contract)
    )
    governed_rr_contract = explicit_rr_contract or (
        aligned_contract
        if contract_selected and not _is_missing(rr_value) and not contract_changed
        else ""
    )
    pipeline_mode = _u(first(sig, "pipeline_mode", "run_pipeline_mode")) or "UNKNOWN"
    ev3_status = _u(sig.get("ev3_status"))
    trigger_present = not _is_missing(first(sig, "trigger_primary", "trigger_codes"))
    garch_method = first(sig, "garch_method", "l3_method", "garch__l3_method")
    provenance = dict(sig.get("_lab_field_provenance") or {})
    row = {
        "lab_schema_version": "lab_signal_book_v2",
        "pipeline_mode": pipeline_mode,
        "run_id": run_id,
        "ticker": _s(sig.get("ticker")).upper(),
        "trade_idea_id": sig.get("trade_idea_id") or _trade_idea_id(sig, run_id),
        "lab_rank": rank,
        "priority_rank": rank,
        "lab_verdict": sig.get("lab_verdict", "WAIT"),
        "lab_tradeable": bool(sig.get("lab_tradeable")),
        "prep_permission": first(sig, "prep_permission", "run_prep_permission", "eod_prep_permission"),
        "lab_status": sig.get("lab_status") or sig.get("lab_verdict", "WAIT"),
        "lab_execution_status": sig.get("lab_execution_status", ""),
        "final_action": first(sig, "final_action"),
        "gate_reason": first(sig, "gate_reason"),
        "gate_warnings": first(sig, "gate_warnings"),
        "gate_version": first(sig, "gate_version"),
        "execution_eligibility_state": first(sig, "execution_eligibility_state"),
        "execution_authority_ceiling": first(sig, "execution_authority_ceiling"),
        "execution_authority_source": first(sig, "execution_authority_source"),
        "execution_authority_policy_version": first(sig, "execution_authority_policy_version"),
        "final_capital_permission": first(sig, "final_capital_permission"),
        "execution_requires_human_approval": first(sig, "execution_requires_human_approval"),
        "execution_authorized": first(sig, "execution_authorized"),
        "execution_can_grant_capital": first(sig, "execution_can_grant_capital"),
        "eod_candidate_status": first(sig, "eod_candidate_status", "lab_execution_status", "candidate_status"),
        "execution_category": first(sig, "execution_category", "morning_execution_route", "morning_execution_lane", "morning_execution_permission", "execution_permission", "lab_verdict"),
        "action_category": first(sig, "lab_execution_status", "eod_candidate_status", "execution_category", "lab_verdict"),
        "campaign_verdict": first(sig, "campaign_verdict", "sb_campaign", "convexity_campaign"),
        "display_execution_mode": first(sig, "display_execution_mode", "morning_entry_action", "sb_execution_mode", "execution_verdict"),
        "position_size_display": first(sig, "position_size_display", "sb_position_size_display"),
        "lab_coherence_status": lab_coherence_status,
        "lab_coherence_flags": lab_coherence_flags,
        "canonical_direction": canonical_direction,
        "dir_calc_version": first(sig, "dir_calc_version"),
        "direction_policy_version": first(sig, "direction_policy_version"),
        "direction_policy_sha256": first(sig, "direction_policy_sha256"),
        "discovery_direction_preliminary": first(sig, "discovery_direction_preliminary"),
        "governed_direction": first(sig, "governed_direction"),
        "governed_direction_authority": first(sig, "governed_direction_authority"),
        "governed_direction_basis": first(sig, "governed_direction_basis"),
        "final_direction": first(sig, "final_direction", "canonical_direction"),
        "direction_resolution_path": first(sig, "direction_resolution_path"),
        "direction_governance_status": first(sig, "direction_governance_status"),
        "direction_resolution_confidence": first(sig, "direction_resolution_confidence"),
        "direction_resolution_call_score": first(sig, "direction_resolution_call_score"),
        "direction_resolution_put_score": first(sig, "direction_resolution_put_score"),
        "direction_resolution_winning_share": first(sig, "direction_resolution_winning_share"),
        "direction_resolution_margin": first(sig, "direction_resolution_margin"),
        "direction_resolution_evidence_count": first(sig, "direction_resolution_evidence_count"),
        "direction_resolution_evidence_json": first(sig, "direction_resolution_evidence_json"),
        "direction_resolution_chain_json": first(sig, "direction_resolution_chain_json"),
        "direction_excluded_evidence_json": first(sig, "direction_excluded_evidence_json"),
        "governed_direction_record_json": first(sig, "governed_direction_record_json"),
        "governed_direction_record_sha256": first(sig, "governed_direction_record_sha256"),
        "direction_integrity_status": first(sig, "direction_integrity_status"),
        "check_direction_integrity_pass": first(sig, "check_direction_integrity_pass"),
        "check_direction_integrity_reason": first(sig, "check_direction_integrity_reason"),
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
        "phase": first(sig, "phase", "phase_best", "wyckoff_phase"),
        "intent": first(sig, "intent", "precor_intent", "setup_intent"),
        "tier": first(sig, "tier", "tier_label", "structural_tier"),
        "regime": first(sig, "regime", "macro_regime_label", "macro_regime"),
        "composite_score": first(sig, "composite_score", "composite", "options_research_score"),
        "instrument": aligned_instrument,
        "contract_symbol": aligned_contract,
        "contract_data_state": "AVAILABLE" if contract_selected else "NOT_APPLICABLE_NO_SELECTED_CONTRACT",
        "contract_source": first(sig, "contract_source", "contract_quote_source", "contract_quote_timestamp_source"),
        "morning_selected_contract_symbol": first(sig, "morning_selected_contract_symbol", "live_selected_contract_symbol"),
        "selected_structure": first(sig, "selected_structure"),
        "selected_quote_snapshot_id": first(sig, "selected_quote_snapshot_id"),
        "selected_quote_timestamp_utc": first(
            sig,
            "selected_quote_timestamp_utc",
            "contract_quote_timestamp_utc",
            "quote_timestamp_utc",
            "contract_quote_timestamp",
        ),
        "selected_structure_hydration_status": first(sig, "selected_structure_hydration_status"),
        "selected_structure_hydration_reason": first(sig, "selected_structure_hydration_reason"),
        "selected_structure_hydration_schema_version": first(sig, "selected_structure_hydration_schema_version"),
        "selected_legs_json": first(sig, "selected_legs_json"),
        "contract_bid_size": first(sig, "contract_bid_size", "live_contract_bid_size"),
        "contract_ask_size": first(sig, "contract_ask_size", "live_contract_ask_size"),
        "contract_size_quality": first(sig, "contract_size_quality"),
        "contract_quote_quality": first(sig, "contract_quote_quality"),
        "morning_contract_bid": first(sig, "morning_contract_bid"),
        "morning_contract_ask": first(sig, "morning_contract_ask"),
        "morning_contract_mid": first(sig, "morning_contract_mid"),
        "morning_contract_spread_pct": first(sig, "morning_contract_spread_pct"),
        "morning_contract_bid_size": first(sig, "morning_contract_bid_size"),
        "morning_contract_ask_size": first(sig, "morning_contract_ask_size"),
        "morning_quote_dataset_id": first(sig, "morning_quote_dataset_id"),
        "morning_quote_timestamp_utc": first(sig, "morning_quote_timestamp_utc"),
        "current_contract_bid": first(sig, "current_contract_bid", "live_contract_bid"),
        "current_contract_ask": first(sig, "current_contract_ask", "live_contract_ask"),
        "current_contract_mid": first(sig, "current_contract_mid", "live_contract_mid"),
        "current_contract_spread_pct": first(sig, "current_contract_spread_pct", "live_contract_spread_pct"),
        "current_contract_bid_size": first(sig, "current_contract_bid_size", "live_contract_bid_size"),
        "current_contract_ask_size": first(sig, "current_contract_ask_size", "live_contract_ask_size"),
        "current_quote_dataset_id": first(sig, "current_quote_dataset_id", "msi_exact_quote_dataset_id"),
        "current_quote_timestamp_utc": first(sig, "current_quote_timestamp_utc", "live_contract_quote_timestamp"),
        "contract_bid_change": first(sig, "contract_bid_change"),
        "contract_bid_change_pct": first(sig, "contract_bid_change_pct"),
        "contract_ask_change": first(sig, "contract_ask_change"),
        "contract_ask_change_pct": first(sig, "contract_ask_change_pct"),
        "contract_mid_change": first(sig, "contract_mid_change"),
        "contract_mid_change_pct": first(sig, "contract_mid_change_pct"),
        "contract_spread_change_pp": first(sig, "contract_spread_change_pp"),
        "contract_bid_size_change": first(sig, "contract_bid_size_change"),
        "contract_ask_size_change": first(sig, "contract_ask_size_change"),
        "comparison_status": first(sig, "comparison_status"),
        "change_status": first(sig, "change_status"),
        "underlying_nbbo_bid": first(sig, "underlying_nbbo_bid", "underlying_bid"),
        "underlying_nbbo_ask": first(sig, "underlying_nbbo_ask", "underlying_ask"),
        "underlying_nbbo_mid": first(sig, "underlying_nbbo_mid", "underlying_mid"),
        "underlying_nbbo_bid_size": first(sig, "underlying_nbbo_bid_size", "underlying_bid_size"),
        "underlying_nbbo_ask_size": first(sig, "underlying_nbbo_ask_size", "underlying_ask_size"),
        "underlying_nbbo_timestamp_utc": first(sig, "underlying_nbbo_timestamp_utc", "underlying_quote_updated"),
        "underlying_nbbo_source": first(sig, "underlying_nbbo_source"),
        "underlying_nbbo_dataset_id": first(sig, "underlying_nbbo_dataset_id", "msi_underlying_quote_dataset_id"),
        "underlying_nbbo_quality": first(sig, "underlying_nbbo_quality", "underlying_depth_level"),
        "contract_repair_status": first(sig, "contract_repair_status", "opt__contract_repair_status"),
        "contract_repair_required": first(sig, "contract_repair_required", "opt__contract_repair_required"),
        "contract_repair_reason": first(sig, "contract_repair_reason", "opt__contract_repair_reason"),
        "contract_repair_action": first(sig, "contract_repair_action", "opt__contract_repair_action"),
        "contract_repair_live_action": first(sig, "contract_repair_live_action", "mv__contract_repair_live_action"),
        "contract_repair_alternative_used": first(sig, "contract_repair_alternative_used", "mv__contract_repair_alternative_used"),
        "lifecycle_contract_version": first(sig, "lifecycle_contract_version"),
        "thesis_id": first(sig, "thesis_id"),
        "thesis_state": first(sig, "thesis_state"),
        "liquidity_state": first(sig, "liquidity_state"),
        "morning_transition_state": first(sig, "morning_transition_state"),
        "recovery_disposition": first(sig, "recovery_disposition"),
        "executable_now": sig.get("executable_now", False),
        "moneyness_state": first(sig, "moneyness_state"),
        "delta_band": first(sig, "delta_band"),
        "minimum_required_dte": first(sig, "minimum_required_dte"),
        "dte_buffer_sessions": first(sig, "dte_buffer_sessions"),
        "atm_distance_sigma": first(sig, "atm_distance_sigma", "atm_distance_sigma_1d"),
        "remaining_runway_pct": first(sig, "remaining_runway_pct"),
        "remaining_runway_state": first(sig, "remaining_runway_state"),
        "maturation_state_1d": first(sig, "maturation_state_1d"),
        "maturation_state_2d": first(sig, "maturation_state_2d"),
        "maturation_state_3d": first(sig, "maturation_state_3d"),
        "maturation_score_1d": first(sig, "maturation_score_1d"),
        "maturation_score_2d": first(sig, "maturation_score_2d"),
        "maturation_score_3d": first(sig, "maturation_score_3d"),
        "maturation_score_is_probability": sig.get("maturation_score_is_probability", False),
        "maturation_execution_authority": sig.get("maturation_execution_authority", False),
        "olm_guard_version": first(sig, "olm_guard_version"),
        "olm_guard_disposition": first(sig, "olm_guard_disposition"),
        "olm_guard_reason": first(sig, "olm_guard_reason"),
        "olm_guard_pass": sig.get("olm_guard_pass", False),
        "olm_guard_state_consistent": sig.get("olm_guard_state_consistent", False),
        "previous_contract_symbol": first(sig, "previous_contract_symbol", "contract_symbol_original", "morning_repaired_from_contract"),
        "contract_changed": sig.get("contract_changed", contract_changed),
        "contract_selection_reason": first(sig, "contract_selection_reason", "contract_repair_reason"),
        "quote_as_of": first(
            sig,
            "quote_as_of",
            "selected_quote_timestamp_utc",
            "contract_quote_timestamp_utc",
            "quote_timestamp_utc",
            "contract_quote_timestamp",
        ),
        "quote_freshness": first(sig, "quote_freshness", "contract_quote_freshness"),
        "bar_data_source": first(sig, "bar_data_source", "data_source"),
        "bar_data_asof": first(sig, "bar_data_asof", "data_asof"),
        "bar_data_days_old": first(sig, "bar_data_days_old", "data_days_old"),
        "bar_evidence_state": first(sig, "bar_evidence_state"),
        "bar_evidence_reason": first(sig, "bar_evidence_reason"),
        "is_stale": sig.get("is_stale", False),
        "option_chain_dataset_id": first(sig, "option_chain_dataset_id"),
        "option_chain_provider": first(sig, "option_chain_provider"),
        "option_chain_resolution": first(sig, "option_chain_resolution"),
        "selected_quote_dataset_id": first(sig, "selected_quote_dataset_id"),
        "liquidity_persistence_status": first(sig, "liquidity_persistence_status"),
        "morning_liquidity_persistence_status": first(sig, "morning_liquidity_persistence_status"),
        "alternative_contract_attempts": first(sig, "alternative_contract_attempts", "opt__alternative_contract_attempts"),
        "alternative_contract_1": first(sig, "alternative_contract_1", "alt_contract_1"),
        "alternative_contract_2": first(sig, "alternative_contract_2", "alt_contract_2"),
        "alternative_contract_3": first(sig, "alternative_contract_3", "alt_contract_3"),
        "strike": first(sig, "strike", "live_contract_strike", "contract_strike", "opt__contract_strike") if contract_selected else "",
        "expiry": first(sig, "expiry", "contract_expiry", "opt__contract_expiry") if contract_selected else "",
        "dte": first(sig, "dte", "contract_dte", "opt__contract_dte") if contract_selected else "",
        "premium_mid": first(sig, "premium_mid", "contract_mid", "premium_eod", "premium", "entry_premium", "contract_premium", "opt__premium_mid", "opt__contract_premium") if contract_selected else "",
        "spread_pct": first(sig, "live_contract_spread_pct", "live_spread_pct", "contract_spread_pct", "spread_pct", "final_option_spread_pct", "opt__contract_spread_pct", "opt__spread_pct_mid", "opt__spread_pct") if contract_selected else "",
        "liquidity_score": first(sig, "liquidity_score", "eil_liquidity_score", "opt__liquidity_score") if contract_selected else "",
        "priority_score": first(sig, "priority_score", "research_priority_score", "options_research_score", "options_research_confidence"),
        "options_research_route": first(sig, "options_research_route", "final_route", "options_route_verdict"),
        "options_research_permission": first(sig, "options_research_permission", "execution_permission"),
        "entry_reason": first(sig, "entry_reason", "eod_candidate_reason", "execution_authority_reason", "signal_authority_reason", "sb_verdict_reason"),
        "positive_factors": first(sig, "positive_factors", "opt__positive_factors"),
        "negative_factors": first(sig, "negative_factors", "opt__negative_factors"),
        "sector": first(sig, "sector", "gics_sector", "gics_sector_norm", "sector_name"),
        "gics_sector": first(sig, "gics_sector", "gics_sector_norm", "sector"),
        "gics_sector_norm": first(sig, "gics_sector_norm", "gics_sector", "sector"),
        "sector_etf": first(sig, "sector_etf", "sector_etf_mapped", "sector_proxy"),
        "rr_predicted": rr_value if contract_selected else "",
        "rr_underlying": first(sig, "rr_underlying", "rr"),
        "rr_premium_expected": rr_value if contract_selected else "",
        "rr_contract_symbol": governed_rr_contract,
        "rr_recompute_status": first(sig, "rr_recompute_status"),
        "rr_recompute_reason": first(sig, "rr_recompute_reason"),
        "selected_contract_economics_ready": first(sig, "selected_contract_economics_ready"),
        "execution_viability_policy_version": first(sig, "execution_viability_policy_version"),
        "execution_viability_state": first(sig, "execution_viability_state"),
        "execution_viability_reason": first(sig, "execution_viability_reason"),
        "execution_viability_eligible": first(sig, "execution_viability_eligible"),
        "execution_viability_reviewable": first(sig, "execution_viability_reviewable"),
        "execution_viability_contract_symbol": first(sig, "execution_viability_contract_symbol"),
        "execution_viability_bid": first(sig, "execution_viability_bid"),
        "execution_viability_ask": first(sig, "execution_viability_ask"),
        "execution_viability_spread_pct": first(sig, "execution_viability_spread_pct"),
        "execution_viability_spread_denominator": first(sig, "execution_viability_spread_denominator"),
        "monetisability_status": first(sig, "monetisability_status"),
        "monetisability_state": first(sig, "monetisability_state"),
        "monetisability_reason": first(sig, "monetisability_reason"),
        "monetisability_eligible": first(sig, "monetisability_eligible"),
        "monetisability_calculation_version": first(sig, "monetisability_calculation_version"),
        "monetisability_contract_symbol": first(sig, "monetisability_contract_symbol"),
        "monetisability_evaluation_id": first(sig, "monetisability_evaluation_id"),
        "monetisability_entry_ask": first(sig, "monetisability_entry_ask"),
        "monetisability_strike": first(sig, "monetisability_strike"),
        "monetisability_breakeven_spot": first(sig, "monetisability_breakeven_spot"),
        "monetisability_structural_target_spot": first(sig, "monetisability_structural_target_spot"),
        "monetisability_target_intrinsic_per_share": first(sig, "monetisability_target_intrinsic_per_share"),
        "monetisability_target_profit_per_share": first(sig, "monetisability_target_profit_per_share"),
        "monetisability_target_profit_pct": first(sig, "monetisability_target_profit_pct"),
        "monetisability_minimum_profit_pct": first(sig, "monetisability_minimum_profit_pct"),
        "ev3_selected_contract_aligned": first(sig, "ev3_selected_contract_aligned"),
        "rr_calculation_version": first(sig, "rr_calculation_version"),
        "rr_entry_debit_per_share": first(sig, "rr_entry_debit_per_share"),
        "rr_target_value_per_share": first(sig, "rr_target_value_per_share"),
        "ev_predicted": first(sig, "ev3_ev_conservative_return", "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "ev"),
        "ev3_data_state": "AVAILABLE" if ev3_status else "MISSING_DATA_DEFECT",
        "ev3_status": ev3_status,
        "ev3_reason_code": sig.get("ev3_reason_code", ""),
        "ev3_reason_detail": sig.get("ev3_reason_detail", ""),
        "ev3_absolute_state": sig.get("ev3_absolute_state", ""),
        "ev3_shadow_only": sig.get("ev3_shadow_only", ""),
        "ev3_structure": sig.get("ev3_structure", ""),
        "ev3_contract_symbol": sig.get("ev3_contract_symbol", ""),
        "ev3_state_match_type": sig.get("ev3_state_match_type", ""),
        "ev3_state_similarity": sig.get("ev3_state_similarity", ""),
        "ev3_n_effective": sig.get("ev3_n_effective", ""),
        "ev3_p_target": sig.get("ev3_p_target", ""),
        "ev3_p_stop": sig.get("ev3_p_stop", ""),
        "ev3_p_timeout": sig.get("ev3_p_timeout", ""),
        "ev3_ev_conservative_return": sig.get("ev3_ev_conservative_return", ""),
        "ev3_ev_lower_bound_return": sig.get("ev3_ev_lower_bound_return", ""),
        "ev3_uncertainty_total_return": sig.get("ev3_uncertainty_total_return", ""),
        "win_prob_predicted": first(sig, "win_prob_predicted", "ev2_p_win_blended", "win_rate_20d", "win_rate_10d"),
        "actuarial_match_method": first(sig, "actuarial_match_method", "layer2__state_match_method", "vg__layer2__state_match_method"),
        "actuarial_match_type": first(sig, "actuarial_match_type", "vg__actuarial_match_type"),
        "actuarial_ev_weight": first(sig, "actuarial_ev_weight", "vg__actuarial_ev_weight"),
        "behaviour_state_key": first(sig, "behaviour_state_key", "vg__behaviour_state_key"),
        "behaviour_state_hash": first(sig, "behaviour_state_hash", "vg__behaviour_state_hash"),
        "catalyst_overlay": first(sig, "catalyst_overlay", "vg__catalyst_overlay"),
        "catalyst_type": sig.get("catalyst_type", ""),
        "catalyst_date": sig.get("catalyst_date", ""),
        "catalyst_truth_score": sig.get("catalyst_truth_score", ""),
        "catalyst_direction_bias": sig.get("catalyst_direction_bias", ""),
        "catalyst_event_status": sig.get("catalyst_event_status", ""),
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
        "macro_data_role": "ADVISORY_ONLY",
        "macro_packet_id": first(sig, "macro_packet_id"),
        "macro_packet_sha256": first(sig, "macro_packet_sha256"),
        "macro_source_fingerprint": first(sig, "macro_source_fingerprint"),
        "macro_as_of_utc": first(sig, "macro_as_of_utc"),
        "macro_session_date": first(sig, "macro_session_date"),
        "macro_freshness": first(sig, "macro_freshness", "macro_freshness_status"),
        "macro_data_quality": first(sig, "macro_data_quality"),
        "macro_context_state": first(sig, "macro_context_state"),
        "macro_sector_alignment": first(sig, "macro_sector_alignment"),
        "macro_ticker_alignment": first(sig, "macro_ticker_alignment"),
        "macro_rates_context": first(sig, "macro_rates_context"),
        "macro_usd_context": first(sig, "macro_usd_context"),
        "macro_volatility_context": first(sig, "macro_volatility_context"),
        "macro_liquidity_context": first(sig, "macro_liquidity_context"),
        "macro_bond_context": first(sig, "macro_bond_context"),
        "macro_auction_risk": first(sig, "macro_auction_risk"),
        "macro_active_themes": first(sig, "macro_active_themes"),
        "macro_event_guards": first(sig, "macro_event_guards"),
        "macro_directional_pressure": first(sig, "macro_directional_pressure"),
        "macro_conflicts": first(sig, "macro_conflicts"),
        "macro_plain_language_advisory": first(sig, "macro_plain_language_advisory"),
        "macro_authority": first(sig, "macro_authority") or "MACRO_ADVISORY_ONLY",
        "eil_signal_verdict": first(sig, "eil_signal_verdict", "eil_v3_verdict", "fd_advisory_verdict", "fd_verdict"),
        "eil_v3_verdict": first(sig, "eil_v3_verdict", "eil_signal_verdict", "fd_advisory_verdict", "fd_verdict"),
        "eil_composite_eod": first(sig, "eil_composite_eod", "eil_composite_score", "eil__composite_score"),
        "entry_plan": first(sig, "entry_plan", "trigger_primary", "scenario_entry_trigger", "wbs__entry_guidance"),
        "invalidation_price": first(
            sig,
            "invalidation_spot",
            "ev3_invalidation_spot",
            "invalidation_price",
            "invalidation_eod",
            "stop_loss",
        ),
        "invalidation_state": first(sig, "invalidation_state", "ev3_invalidation_state"),
        "invalidation_source": first(sig, "invalidation_source", "ev3_invalidation_source"),
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
        "contract_delta": first(sig, "contract_delta", "opt__contract_delta", "delta") if contract_selected else "",
        "contract_gamma": first(sig, "contract_gamma", "opt__contract_gamma", "gamma") if contract_selected else "",
        "contract_theta": first(sig, "contract_theta", "opt__contract_theta", "theta") if contract_selected else "",
        "contract_vega": first(sig, "contract_vega", "opt__contract_vega", "vega") if contract_selected else "",
        "contract_iv": first(sig, "contract_iv", "opt__contract_iv", "iv") if contract_selected else "",
        "contract_bid": first(sig, "contract_bid", "opt__contract_bid", "bid") if contract_selected else "",
        "contract_ask": first(sig, "contract_ask", "opt__contract_ask", "ask") if contract_selected else "",
        "contract_mid": first(sig, "contract_mid", "opt__contract_mid", "mid", "premium_mid") if contract_selected else "",
        "contract_oi": first(sig, "contract_oi", "opt__contract_oi", "openInterest", "open_interest") if contract_selected else "",
        "contract_volume": first(sig, "contract_volume", "opt__contract_volume", "volume") if contract_selected else "",
        "options_score": first(sig, "options_score", "options_research_score", "opt__options_score"),
        "iv_rank": first(sig, "iv_rank", "ivp", "opt__iv_rank"),
        "ivp_label": first(sig, "ivp_label", "iv_alignment", "opt__ivp_label"),
        "atm_iv": first(sig, "atm_iv", "opt__atm_iv"),
        "hv_30d": first(sig, "hv_30d", "opt__hv_30d"),
        "iv_vs_hv": first(sig, "iv_vs_hv", "opt__iv_vs_hv"),
        "term_structure": first(sig, "term_structure", "opt__term_structure"),
        "theta_drag_pct": first(sig, "theta_drag_pct", "opt__theta_drag_pct"),
        "vega_risk_pct": first(sig, "vega_risk_pct", "opt__vega_risk_pct"),
        "theta_constrained": first(sig, "theta_constrained", "opt__theta_constrained"),
        "contract_mark_synthetic": first(sig, "contract_mark_synthetic", "mark_synthetic", "opt__contract_mark_synthetic"),
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
        "wbs_pcr_volume_state": first(sig, "wbs_pcr_volume_state"),
        "wbs_data_state": "AVAILABLE" if not _is_missing(first(sig, "wbs_grade", "wbs")) else "NOT_APPLICABLE_NOT_SCORED",
        "wbs_break_direction": first(sig, "wbs_break_direction", "break_direction"),
        "wbs_momentum_alignment_state": first(sig, "wbs_momentum_alignment_state", "momentum_alignment_state"),
        "convexity_data_state": "AVAILABLE" if not _is_missing(first(sig, "convexity_score", "sb_conv_score")) else "NOT_GOVERNED",
        "convexity_score": first(sig, "convexity_score", "sb_conv_score"),
        "convexity_campaign": first(sig, "convexity_campaign", "sb_campaign"),
        "readiness_stage": "",
        "readiness_label": "",
        "readiness_enter_now": False,
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
        "trigger_price_source": first(sig, "trigger_price_source"),
        "trigger_evidence": _trigger_evidence(sig),
        "trigger_primary": first_trigger_category(
            sig, "trigger_primary", "trigger_codes", "scenario_entry_trigger"
        ),
        # trigger_quality is a governed categorical value. A numeric score is
        # a different field and must never be displayed as semantic recovery.
        "trigger_quality": first_trigger_category(sig, "trigger_quality"),
        "trigger_score": first(sig, "trigger_score", "trigger_count"),
        "trigger_codes": first_trigger_category(
            sig, "trigger_codes", "trigger_primary", "scenario_entry_trigger"
        ),
        "trigger_data_state": "AVAILABLE" if trigger_present else "NOT_AVAILABLE",
        "hard_vetoes": first(sig, "hard_vetoes", "options_hard_vetoes", "veto_flags"),
        "options_hard_vetoes": first(sig, "options_hard_vetoes", "hard_vetoes"),
        "advisory_flags": first(sig, "advisory_flags"),
        "garch_data_state": "AVAILABLE" if not _is_missing(garch_method) else "MISSING_DATA_DEFECT",
        "garch_method": garch_method,
        "garch_forecast_vol": first(sig, "garch_forecast_vol", "l3_vol_forecast", "garch__l3_vol_forecast"),
        "garch_iv_tailwind_score": first(sig, "garch_iv_tailwind_score", "l3_iv_tailwind_score", "garch__l3_iv_tailwind_score"),
        "garch_jump_risk_flag": first(sig, "garch_jump_risk_flag", "l3_jump_risk_flag", "garch__l3_jump_risk_flag"),
        "garch_forecast_confidence": first(sig, "garch_forecast_confidence", "l3_forecast_confidence", "garch__l3_forecast_confidence"),
        "garch_expected_move_1_5d": first(sig, "garch_expected_move_1_5d", "l3_expected_move_1_5d", "garch__l3_expected_move_1_5d"),
        "garch_expected_move_6_10d": first(sig, "garch_expected_move_6_10d", "l3_expected_move_6_10d", "garch__l3_expected_move_6_10d"),
        "garch_expected_move_11_20d": first(sig, "garch_expected_move_11_20d", "l3_expected_move_11_20d", "garch__l3_expected_move_11_20d"),
        "garch_price_bars_used": first(sig, "garch_price_bars_used", "l3_n_bars", "garch__l3_n_bars"),
        "morning_data_state": "AVAILABLE" if not _is_missing(first(sig, "morning_execution_permission", "mv__morning_execution_permission")) else ("NOT_RUN_EOD" if pipeline_mode in {"EOD", "LIVE_EOD", "INTRADAY_EOD"} else "MISSING_DATA_DEFECT"),
        "data_quality_flags": first(sig, "data_quality_flags"),
        "field_provenance_json": _json_safe(provenance),
        "pcr_vol_status": first(sig, "pcr_vol_status", "opt__pcr_vol_status"),
        "pcr_vol_missing_reason": first(sig, "pcr_vol_missing_reason", "opt__pcr_vol_missing_reason"),
        "pcr_vol": first(sig, "pcr_vol", "opt__pcr_vol"),
        "win_rate_source": first(sig, "win_rate_source"),
        "direction_conflict_status": first(sig, "direction_conflict_status", "opt__direction_conflict_status"),
        "direction_conflict_reason": first(sig, "direction_conflict_reason", "opt__direction_conflict_reason"),
        "notes": first(sig, "notes", "execution_lock_reason", "verdict_coherence_notes", "sb_verdict_reason"),
        "source_payload_json": _json_safe(sig),
    }
    _enforce_economics_identity(row, provenance)
    _enforce_olm_lab_guard(row, provenance)
    _enforce_execution_authority_lab_guard(row, provenance)
    # Liquidity-maturation scores are deterministic monitoring evidence. They
    # must never be reinterpreted as execution or capital authority.
    row["maturation_execution_authority"] = False
    direction_valid, direction_reason = validate_direction_record(row)
    row["check_direction_integrity_pass"] = direction_valid
    row["check_direction_integrity_reason"] = direction_reason
    row["direction_integrity_status"] = "PASS" if direction_valid else "FAIL"
    actionable_direction_claim = (
        bool(row.get("lab_tradeable"))
        or _u(row.get("lab_verdict")) in {"GO", "GO_LIMIT", "PROBE"}
        or _u(row.get("final_action")) in {"BUY_NOW", "BUY_SMALL"}
    )
    if actionable_direction_claim and not direction_valid:
        row["lab_tradeable"] = False
        row["lab_verdict"] = "BLOCKED"
        row["lab_status"] = "BLOCKED"
        row["lab_execution_status"] = "DIRECTION_INTEGRITY_FAILED"
        row["final_action"] = "BLOCK"
        row["execution_category"] = "BLOCKED"
        row["action_category"] = "BLOCKED"
        row["display_execution_mode"] = "NO_TRADE"
        row["position_size_display"] = "0% - direction integrity failed"
        row["execution_lock_reason"] = direction_reason
        row["lab_coherence_status"] = "DIRECTION_INTEGRITY_FAILED"
        row["lab_coherence_flags"] = _append_flag(
            row.get("lab_coherence_flags"), direction_reason
        )
    # A valid directional row may be displayed for research without a
    # governed invalidation, but it must never be presented as executable.
    # Direction integrity takes precedence when both contracts are absent.
    invalidation_state = _u(row.get("invalidation_state"))
    invalidation_price = _f(row.get("invalidation_price"), default=0.0)
    directional = _side_from_value(row.get("canonical_direction")) in {"CALL", "PUT"}
    if direction_valid and directional and (
        invalidation_state != "AVAILABLE" or invalidation_price <= 0.0
    ):
        row["lab_tradeable"] = False
        row["lab_verdict"] = "BLOCKED"
        row["lab_status"] = "BLOCKED"
        row["lab_execution_status"] = DataExceptionReason.INVALIDATION_MISSING.value
        row["final_action"] = "BLOCK"
        row["execution_category"] = "BLOCKED"
        row["action_category"] = "BLOCKED"
        row["display_execution_mode"] = "NO_TRADE"
        row["position_size_display"] = "0% - governed invalidation missing"
        row["options_research_permission"] = "NOT_EXECUTABLE"
        row["execution_lock_reason"] = _append_flag(
            row.get("execution_lock_reason"), DataExceptionReason.INVALIDATION_MISSING.value
        )
        row["lab_coherence_status"] = DataExceptionReason.INVALIDATION_MISSING.value
        row["lab_coherence_flags"] = _append_flag(
            row.get("lab_coherence_flags"), DataExceptionReason.INVALIDATION_MISSING.value
        )
        provenance["lab_tradeable"] = "governed_materializer:invalidation_precondition"
        provenance["final_action"] = "governed_materializer:invalidation_precondition"
    row["field_provenance_json"] = _json_safe(provenance)
    return {key: csv_safe_row(row).get(key, "") for key in FINAL_BOOK_FIELDS}


def build_final_opportunity_book(
    run_id: str,
    signals: Iterable[Dict[str, Any]],
    run_manifest: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    manifest = run_manifest or {}
    enriched = [dict(sig) for sig in signals]
    pipeline_mode = _u(manifest.get("pipeline_mode")) or "UNKNOWN"
    for sig in enriched:
        sig.setdefault("pipeline_mode", pipeline_mode)
        if "lab_verdict" not in sig or "morning_lab_alignment_status" not in sig:
            apply_lab_resolution(sig, manifest)
    order = {"GO": 0, "GO_LIMIT": 1, "PROBE": 2, "MANUAL_LIQUIDITY_REVIEW": 3, "CONTRACT_REPAIR": 4, "MORNING_VALIDATION_REQUIRED": 5, "ARMED": 6, "WAIT": 7, "BLOCKED": 8}
    enriched.sort(
        key=lambda row: (
            order.get(_u(row.get("lab_verdict")), 9),
            -_f(first(row, "priority_score", "research_priority_score", "options_research_score", "options_research_confidence"), 0.0),
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
        run_root / "options" / f"vanguard_signals_enriched_{run_id}.csv",
        run_root / "vanguard" / f"vanguard_signals_enriched_{run_id}.csv",
        run_root / "qomega" / f"garch_forecasts_{run_id}.csv",
        run_root / "morning_validation" / f"morning_candidates_{run_id}.csv",
    ]
    return [path for path in candidates if path.exists()]


def _lab_extract_field_aliases() -> Dict[str, List[str]]:
    return {
        "priority_score": ["priority_score", "research_priority_score", "options_research_score", "options_research_confidence"],
        "eod_candidate_status": ["eod_candidate_status", "lab_execution_status", "candidate_status"],
        "campaign_verdict": ["campaign_verdict", "sb_campaign", "convexity_campaign"],
        "options_research_route": ["options_research_route", "final_route", "options_route_verdict"],
        "options_research_permission": ["options_research_permission", "execution_permission"],
        "entry_reason": ["entry_reason", "eod_candidate_reason", "execution_authority_reason", "signal_authority_reason", "sb_verdict_reason"],
        "positive_factors": ["positive_factors", "opt__positive_factors"],
        "negative_factors": ["negative_factors", "opt__negative_factors"],
        "sector": ["sector", "gics_sector", "gics_sector_norm", "sector_name"],
        "gics_sector": ["gics_sector", "gics_sector_norm", "sector"],
        "gics_sector_norm": ["gics_sector_norm", "gics_sector", "sector"],
        "sector_etf": ["sector_etf", "sector_etf_mapped", "sector_proxy"],
        "phase": ["phase", "phase_best", "wyckoff_phase"],
        "intent": ["intent", "precor_intent", "setup_intent"],
        "tier": ["tier", "tier_label", "structural_tier"],
        "regime": ["regime", "macro_regime_label", "macro_regime"],
        "composite_score": ["composite_score", "composite", "options_research_score"],
        "spread_pct": ["spread_pct", "contract_spread_pct", "final_option_spread_pct", "opt__contract_spread_pct", "opt__spread_pct_mid", "opt__spread_pct"],
        "rr_underlying": ["rr_underlying", "rr"],
        "rr_premium_expected": ["rr_premium_expected", "rr_options", "option_rr"],
        "rr_predicted": ["rr_premium_expected", "rr_options", "option_rr"],
        "ev_predicted": ["ev3_ev_conservative_return", "ev_predicted", "ev2_ev_conf_adj", "eil_ev_net", "ev"],
        "ev3_status": ["ev3_status"],
        "ev3_reason_code": ["ev3_reason_code"],
        "ev3_reason_detail": ["ev3_reason_detail"],
        "ev3_absolute_state": ["ev3_absolute_state"],
        "ev3_shadow_only": ["ev3_shadow_only"],
        "ev3_structure": ["ev3_structure"],
        "ev3_contract_symbol": ["ev3_contract_symbol"],
        "ev3_state_match_type": ["ev3_state_match_type"],
        "ev3_state_similarity": ["ev3_state_similarity"],
        "ev3_n_effective": ["ev3_n_effective"],
        "ev3_p_target": ["ev3_p_target"],
        "ev3_p_stop": ["ev3_p_stop"],
        "ev3_p_timeout": ["ev3_p_timeout"],
        "ev3_ev_conservative_return": ["ev3_ev_conservative_return"],
        "ev3_ev_lower_bound_return": ["ev3_ev_lower_bound_return"],
        "ev3_uncertainty_total_return": ["ev3_uncertainty_total_return"],
        "trigger_primary": ["trigger_primary"],
        "trigger_quality": ["trigger_quality"],
        "trigger_score": ["trigger_score", "trigger_count"],
        "trigger_codes": ["trigger_codes", "trigger_primary"],
        "hard_vetoes": ["hard_vetoes", "options_hard_vetoes"],
        "options_hard_vetoes": ["options_hard_vetoes", "hard_vetoes"],
        "catalyst_overlay": ["catalyst_overlay"],
        "catalyst_type": ["catalyst_type"],
        "catalyst_date": ["catalyst_date"],
        "catalyst_truth_score": ["catalyst_truth_score"],
        "catalyst_direction_bias": ["catalyst_direction_bias"],
        "catalyst_event_status": ["catalyst_event_status"],
        "garch_method": ["garch_method", "l3_method"],
        "garch_forecast_vol": ["garch_forecast_vol", "l3_forward_realised_vol"],
        "garch_iv_tailwind_score": ["garch_iv_tailwind_score", "l3_iv_tailwind_score"],
        "garch_jump_risk_flag": ["garch_jump_risk_flag", "l3_jump_risk_flag"],
        "garch_forecast_confidence": ["garch_forecast_confidence", "l3_vol_forecast_conf"],
        "garch_expected_move_1_5d": ["garch_expected_move_1_5d", "l3_expected_move_1_5d"],
        "garch_expected_move_6_10d": ["garch_expected_move_6_10d", "l3_expected_move_6_10d"],
        "garch_expected_move_11_20d": ["garch_expected_move_11_20d", "l3_expected_move_11_20d"],
        "garch_price_bars_used": ["garch_price_bars_used", "l3_n_bars"],
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
        "contract_vega": ["contract_vega", "opt__contract_vega", "vega"],
        "contract_iv": ["contract_iv", "opt__contract_iv", "iv"],
        "contract_bid": ["contract_bid", "opt__contract_bid", "bid"],
        "contract_ask": ["contract_ask", "opt__contract_ask", "ask"],
        "contract_mid": ["contract_mid", "opt__contract_mid", "mid", "premium_mid"],
        "contract_oi": ["contract_oi", "opt__contract_oi", "openInterest", "open_interest"],
        "contract_volume": ["contract_volume", "opt__contract_volume", "volume"],
        "options_score": ["options_score", "options_research_score", "opt__options_score"],
        "iv_rank": ["iv_rank", "ivp", "opt__iv_rank"],
        "ivp_label": ["ivp_label", "iv_alignment", "opt__ivp_label"],
        "atm_iv": ["atm_iv", "opt__atm_iv"],
        "hv_30d": ["hv_30d", "opt__hv_30d"],
        "iv_vs_hv": ["iv_vs_hv", "opt__iv_vs_hv"],
        "term_structure": ["term_structure", "opt__term_structure"],
        "theta_drag_pct": ["theta_drag_pct", "opt__theta_drag_pct"],
        "vega_risk_pct": ["vega_risk_pct", "opt__vega_risk_pct"],
        "theta_constrained": ["theta_constrained", "opt__theta_constrained"],
        "contract_mark_synthetic": ["contract_mark_synthetic", "mark_synthetic", "opt__contract_mark_synthetic"],
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
        "wbs_pcr_volume_state": ["wbs_pcr_volume_state"],
        "convexity_score": ["convexity_score", "sb_conv_score"],
        "convexity_campaign": ["convexity_campaign", "sb_campaign"],
        "pcr_vol": ["pcr_vol", "opt__pcr_vol"],
        "pcr_vol_status": ["pcr_vol_status", "opt__pcr_vol_status"],
        "pcr_vol_missing_reason": ["pcr_vol_missing_reason", "opt__pcr_vol_missing_reason"],
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


def _lab_field_source_priority(field: str) -> List[str]:
    """Authoritative source order for one normalized Lab field.

    This is intentionally field-level. A globally "richest" CSV is not
    allowed to own unrelated data merely because it carries copied columns.
    """
    if field.startswith("garch_"):
        return ["garch_forecasts"]
    if field.startswith("wbs"):
        return ["wall_break_scores", "eil_enriched", "execution_v3_5"]
    if field.startswith("trigger_"):
        return ["eil_enriched", "execution_v3_5", "morning_validated_trades", "morning_candidates"]
    if field.startswith("ev3_") or field == "ev_predicted":
        return ["options_intelligence", "execution_v3_5", "eil_enriched", "morning_candidates"]
    if field.startswith("catalyst_"):
        return ["options_intelligence", "vanguard_signals_enriched", "eil_enriched", "execution_v3_5"]
    if field in {"sector", "gics_sector", "gics_sector_norm", "sector_etf"}:
        return ["vanguard_signals_enriched", "options_intelligence", "execution_v3_5", "eil_enriched", "morning_candidates"]
    if field in {
        "options_score", "iv_rank", "ivp_label", "atm_iv", "hv_30d",
        "iv_vs_hv", "term_structure", "theta_drag_pct", "vega_risk_pct",
        "theta_constrained", "contract_mark_synthetic", "positive_factors",
        "negative_factors", "pcr_vol", "pcr_vol_status", "pcr_vol_missing_reason",
    }:
        return ["options_intelligence", "execution_v3_5", "eil_enriched", "morning_candidates"]
    if field in {
        "spread_pct", "rr_premium_expected", "rr_predicted", "breakeven_price",
        "breakeven_pct", "breakeven_feasibility", "option_gain_at_target",
        "contract_delta", "contract_gamma", "contract_theta", "contract_vega", "contract_iv",
        "contract_bid", "contract_ask", "contract_mid", "contract_oi",
        "contract_volume", "hard_vetoes", "options_hard_vetoes",
        "call_wall", "put_wall", "gamma_flip", "max_pain", "pcr_signal",
        "gamma_island_on_path", "gamma_island_level", "gamma_island_distance_pct",
    }:
        return ["morning_validated_trades", "options_intelligence", "execution_v3_5", "eil_enriched"]
    if field.startswith("layer2__"):
        return ["vanguard_signals_enriched", "execution_v3_5", "eil_enriched", "options_intelligence"]
    return [
        "morning_validated_trades", "execution_v3_5", "eil_enriched",
        "options_intelligence", "vanguard_signals_enriched", "wall_break_scores",
        "garch_forecasts", "morning_candidates",
    ]


def _recompute_governed_lab_fields(row: Dict[str, Any], provenance: Dict[str, str]) -> None:
    """Recompute display-facing derivatives only after all owned sources merge.

    These fields are direct state/alias derivatives, not new trading models.
    Missing market inputs remain explicit and can never become favourable defaults.
    """
    if _is_missing(row.get("premium_mid")) and not _is_missing(row.get("contract_mid")):
        row["premium_mid"] = row.get("contract_mid")
        provenance["premium_mid"] = provenance.get("contract_mid", "governed_materializer")

    if _is_missing(row.get("entry_plan")) and not _is_missing(row.get("wbs_entry_guidance")):
        row["entry_plan"] = row.get("wbs_entry_guidance")
        provenance["entry_plan"] = provenance.get("wbs_entry_guidance", "wall_break_scores")

    if _is_missing(row.get("trigger_price")):
        if not _is_missing(row.get("wbs_phase_c_trigger")):
            row["trigger_price"] = row.get("wbs_phase_c_trigger")
            row["trigger_price_source"] = "WBS_PHASE_C_CONFIRMED_BREAK"
            provenance["trigger_price"] = provenance.get("wbs_phase_c_trigger", "wall_break_scores")
            provenance["trigger_price_source"] = "governed_materializer"
        elif not _is_missing(row.get("wbs_phase_b_trigger")):
            row["trigger_price"] = row.get("wbs_phase_b_trigger")
            row["trigger_price_source"] = "WBS_PHASE_B_WATCH_ZONE"
            provenance["trigger_price"] = provenance.get("wbs_phase_b_trigger", "wall_break_scores")
            provenance["trigger_price_source"] = "governed_materializer"

    direction = _side_from_value(first(row, "canonical_direction", "direction"))
    pcr_status = _u(row.get("pcr_vol_status"))
    pcr_value = row.get("pcr_vol")
    pcr_unavailable = _is_missing(pcr_value) or any(
        marker in pcr_status for marker in ("OI_ONLY", "NO_INTRADAY", "UNAVAILABLE", "MISSING")
    )
    # WBS files created before the missing-PCR fix silently substituted 1.0.
    # That granted every PUT a five-point momentum bonus.  New producer output
    # declares wbs_pcr_volume_state, so this correction is legacy-only and
    # cannot be applied twice.
    legacy_pcr_state_missing = _is_missing(row.get("wbs_pcr_volume_state"))
    if pcr_unavailable and direction == "PUT" and legacy_pcr_state_missing and not _is_missing(row.get("wbs")):
        corrected_wbs = max(0.0, _f(row.get("wbs"), 0.0) - 5.0)
        row["wbs"] = round(corrected_wbs, 1)
        if not _is_missing(row.get("wbs_f5_momentum")):
            row["wbs_f5_momentum"] = round(max(0.0, _f(row.get("wbs_f5_momentum"), 0.0) - 5.0), 2)
        row["wbs_grade"] = (
            "IMMINENT" if corrected_wbs >= 75 else
            "PROBABLE" if corrected_wbs >= 55 else
            "POSSIBLE" if corrected_wbs >= 35 else
            "UNLIKELY"
        )
        row["wbs_pcr_volume_state"] = "UNAVAILABLE_LEGACY_BONUS_REMOVED"
        existing_notes = _s(row.get("wbs_notes"))
        correction_note = "Legacy missing-PCR momentum bonus removed by governed materializer"
        row["wbs_notes"] = f"{existing_notes} | {correction_note}" if existing_notes else correction_note
        flags = list(row.get("_lab_data_quality_flags") or [])
        flags.append("WBS_LEGACY_MISSING_PCR_BONUS_REMOVED")
        row["_lab_data_quality_flags"] = flags
        for field in ("wbs", "wbs_f5_momentum", "wbs_grade", "wbs_pcr_volume_state", "wbs_notes"):
            provenance[field] = "governed_materializer:wbs_missing_pcr_legacy_correction"
    elif pcr_unavailable and legacy_pcr_state_missing and not _is_missing(row.get("wbs")):
        row["wbs_pcr_volume_state"] = "UNAVAILABLE"
        provenance["wbs_pcr_volume_state"] = "governed_materializer"

    if not _is_missing(row.get("wbs_grade")):
        row["wbs_data_state"] = "AVAILABLE"
        if _is_missing(row.get("wbs_break_direction")) and direction in {"CALL", "PUT"}:
            row["wbs_break_direction"] = "UP" if direction == "CALL" else "DOWN"
            provenance["wbs_break_direction"] = "governed_materializer"
    else:
        row["wbs_data_state"] = (
            "NOT_APPLICABLE_NOT_SCORED"
            if row.get("_wbs_authoritative_source_present")
            else "MISSING_DATA_DEFECT"
        )

    if _u(row.get("wbs_data_state")) == "AVAILABLE":
        if pcr_unavailable:
            row["wbs_momentum_alignment_state"] = "UNAVAILABLE_NO_INTRADAY_PCR"
        else:
            pcr_num = _f(pcr_value, 0.0)
            aligned = (direction == "PUT" and pcr_num > 0.8) or (direction == "CALL" and pcr_num < 0.4)
            row["wbs_momentum_alignment_state"] = "ALIGNED" if aligned else "NOT_ALIGNED"
        provenance["wbs_momentum_alignment_state"] = "governed_materializer"

    if _is_missing(row.get("win_rate_source")):
        if not _is_missing(row.get("actuarial_sample_size")) or not _is_missing(row.get("actuarial_match_method")):
            row["win_rate_source"] = "ACTUARIAL"
        else:
            row["win_rate_source"] = "UNAVAILABLE"
        provenance["win_rate_source"] = "governed_materializer"

    pipeline_mode = _u(row.get("pipeline_mode"))
    morning_state = _u(row.get("morning_data_state"))
    morning_permission = _u(row.get("morning_execution_permission"))
    lab_verdict = _u(row.get("lab_verdict"))
    tradeable = bool(row.get("lab_tradeable"))
    if tradeable and morning_permission in {"GO", "GO_LIMIT", "PROBE"}:
        row["readiness_stage"] = 4
        row["readiness_label"] = "MORNING_VALIDATED_EXECUTION_READY"
        row["readiness_enter_now"] = True
    elif lab_verdict == "BLOCKED":
        row["readiness_stage"] = 0
        row["readiness_label"] = "BLOCKED"
        row["readiness_enter_now"] = False
    elif pipeline_mode in {"EOD", "LIVE_EOD", "INTRADAY_EOD"} or morning_state == "NOT_RUN_EOD":
        row["readiness_stage"] = 3
        row["readiness_label"] = "EOD_PREP_COMPLETE_MORNING_VALIDATION_REQUIRED"
        row["readiness_enter_now"] = False
    else:
        row["readiness_stage"] = 2
        row["readiness_label"] = "MORNING_VALIDATION_PENDING"
        row["readiness_enter_now"] = False
    for field in ("readiness_stage", "readiness_label", "readiness_enter_now", "wbs_data_state"):
        provenance[field] = "governed_materializer"

    # Source enrichment can fill EV3 and contract fields from different stage
    # outputs. Re-run the binding after every merge and fail closed when the
    # selected contract and monetisability do not describe the same structure.
    _enforce_economics_identity(row, provenance)


def _enrich_lab_extract_rows_from_run_sources(rows: List[Dict[str, Any]], runs_dir: Path | str, run_id: str) -> Dict[str, Any]:
    aliases = _lab_extract_field_aliases()
    source_indexes: Dict[str, Dict[str, Dict[str, List[Dict[str, Any]]]]] = {}
    source_manifest: Dict[str, Dict[str, Any]] = {}
    source_errors: List[str] = []
    for path in _lab_extract_source_paths(Path(runs_dir), run_id):
        source_name = path.stem.replace(f"_{run_id}", "")
        try:
            source_row_count = 0
            index = source_indexes.setdefault(source_name, {"ticker": {}, "trade_id": {}})
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                for raw in csv.DictReader(fh):
                    source_row_count += 1
                    ticker = _s(raw.get("ticker")).upper()
                    if not ticker:
                        continue
                    trade_id = _s(raw.get("trade_idea_id")) or _trade_idea_id(raw, run_id)
                    index["ticker"].setdefault(ticker, []).append(raw)
                    index["trade_id"].setdefault(trade_id, []).append(raw)
            digest = hashlib.sha256()
            with path.open("rb") as source_fh:
                for chunk in iter(lambda: source_fh.read(1024 * 1024), b""):
                    digest.update(chunk)
            stat = path.stat()
            source_manifest[source_name] = {
                "path": str(path),
                "rows": source_row_count,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": digest.hexdigest(),
            }
        except Exception as exc:
            source_errors.append(f"{source_name}:{type(exc).__name__}:{exc}")
            for row in rows:
                flags = list(row.get("_lab_data_quality_flags") or [])
                flags.append(f"SOURCE_READ_FAILED:{source_name}:{type(exc).__name__}")
                row["_lab_data_quality_flags"] = flags
            continue

    contract_fields = {
        "spread_pct", "rr_premium_expected", "rr_predicted", "breakeven_price",
        "breakeven_pct", "breakeven_feasibility", "option_gain_at_target",
        "contract_delta", "contract_gamma", "contract_theta", "contract_vega", "contract_iv",
        "contract_bid", "contract_ask", "contract_mid", "contract_oi",
        "contract_volume",
    }
    rr_contract_fields = {"rr_premium_expected", "rr_predicted", "option_gain_at_target"}
    for row in rows:
        ticker = _s(row.get("ticker")).upper()
        trade_id = _s(row.get("trade_idea_id")) or _trade_idea_id(row, run_id)
        row["_wbs_authoritative_source_present"] = "wall_break_scores" in source_indexes
        provenance = {}
        try:
            provenance = json.loads(_s(row.get("field_provenance_json")) or "{}")
        except Exception:
            provenance = {}
        for field in aliases:
            if field in contract_fields and _u(row.get("contract_data_state")) != "AVAILABLE":
                continue
            if field.startswith("wbs"):
                # WBS is producer-owned.  Copied values in later handoff CSVs
                # must never outrank wall_break_scores or make an unscored
                # candidate look scored.
                index = source_indexes.get("wall_break_scores", {})
                exact_rows = (index.get("trade_id") or {}).get(trade_id, [])
                ticker_rows = (index.get("ticker") or {}).get(ticker, [])
                candidates = exact_rows if len(exact_rows) == 1 else ticker_rows if len(ticker_rows) == 1 else []
                if len(exact_rows) > 1 or len(ticker_rows) > 1:
                    flags = list(row.get("_lab_data_quality_flags") or [])
                    flags.append(f"AMBIGUOUS_JOIN:wall_break_scores:{field}")
                    row["_lab_data_quality_flags"] = flags
                value = _lab_extract_first_value(candidates[0], aliases[field]) if candidates else ""
                row[field] = "" if _is_missing(value) else value
                if not _is_missing(value):
                    provenance[field] = "wall_break_scores"
                else:
                    provenance.pop(field, None)
                continue
            if not _is_missing(row.get(field)):
                continue
            for source_name in _lab_field_source_priority(field):
                index = source_indexes.get(source_name, {})
                exact_rows = (index.get("trade_id") or {}).get(trade_id, [])
                ticker_rows = (index.get("ticker") or {}).get(ticker, [])
                # Exact trade-idea matches are preferred. Ticker fallback is
                # permitted only when that source is unambiguously one-to-one.
                candidates = exact_rows if len(exact_rows) == 1 else ticker_rows if len(ticker_rows) == 1 else []
                if not candidates:
                    if len(exact_rows) > 1 or len(ticker_rows) > 1:
                        flags = list(row.get("_lab_data_quality_flags") or [])
                        flags.append(f"AMBIGUOUS_JOIN:{source_name}:{field}")
                        row["_lab_data_quality_flags"] = flags
                    continue
                if field in contract_fields:
                    selected_symbols = _contract_symbols(row.get("contract_symbol"))
                    source_contract = first(
                        candidates[0],
                        "morning_selected_contract_symbol", "live_selected_contract_symbol",
                        "contract_symbol", "live_contract_symbol", "recommended_contract",
                        "preferred_contract", "evening_contract_symbol", "opt__recommended_contract",
                    )
                    source_symbols = _contract_symbols(source_contract)
                    if not selected_symbols or source_symbols != selected_symbols:
                        flags = list(row.get("_lab_data_quality_flags") or [])
                        flag = f"CONTRACT_JOIN_REJECTED:{source_name}:{field}"
                        if flag not in flags:
                            flags.append(flag)
                        row["_lab_data_quality_flags"] = flags
                        continue
                value = _lab_extract_first_value(candidates[0], aliases[field])
                if not _is_missing(value):
                    row[field] = value
                    provenance[field] = source_name
                    if field in rr_contract_fields:
                        row["rr_contract_symbol"] = source_contract
                        provenance["rr_contract_symbol"] = source_name
                    break
        if _is_missing(row.get("structural_target")) and not _is_missing(row.get("target_price")):
            row["structural_target"] = row.get("target_price")
        if not _is_missing(row.get("ev3_status")):
            row["ev3_data_state"] = "AVAILABLE"
        if not _is_missing(first(row, "trigger_primary", "trigger_codes")):
            row["trigger_data_state"] = "AVAILABLE"
            if _is_missing(row.get("trigger_evidence")):
                row["trigger_evidence"] = _trigger_evidence(row)
        if not _is_missing(row.get("garch_method")):
            row["garch_data_state"] = "AVAILABLE"
        _recompute_governed_lab_fields(row, provenance)
        row.pop("_wbs_authoritative_source_present", None)
        row["field_provenance_json"] = _json_safe(provenance)
        row["data_quality_flags"] = _json_safe(row.pop("_lab_data_quality_flags", []))
    return {"sources": source_manifest, "source_errors": source_errors}


def write_final_opportunity_book(
    run_id: str,
    signals: Iterable[Dict[str, Any]],
    run_manifest: Optional[Dict[str, Any]],
    runs_dir: Path | str,
    *,
    sync_interpreter: bool = True,
) -> Dict[str, Any]:
    rows = build_final_opportunity_book(run_id, signals, run_manifest)
    run_root = Path(runs_dir) / run_id
    if (run_root / "morning_validation" / f"morning_validated_trades_{run_id}.csv").exists():
        input_source = "morning_validated_trades"
    elif (run_root / "morning_validation" / f"morning_candidates_{run_id}.csv").exists():
        input_source = "morning_candidates"
    else:
        input_source = "eil_enriched"
    governed_fields = {
        "lab_schema_version", "pipeline_mode", "run_id", "trade_idea_id",
        "lab_rank", "priority_rank", "lab_verdict", "lab_tradeable",
        "lab_status", "morning_data_state", "contract_data_state",
        "ev3_data_state", "trigger_data_state", "garch_data_state",
        "macro_data_role", "field_provenance_json", "source_payload_json",
        "selected_structure_id", "selected_contract_symbols",
        "selected_quote_snapshot_id", "rr_evaluation_id",
        "rr_contract_symbol", "ev3_contract_symbol", "ev3_evaluation_id",
        "economics_comparable", "economics_mismatch_reason",
        "macro_packet_id", "macro_packet_sha256", "macro_source_fingerprint",
        "macro_as_of_utc", "macro_session_date", "macro_freshness",
        "macro_data_quality", "macro_context_state", "macro_sector_alignment",
        "macro_ticker_alignment", "macro_rates_context", "macro_usd_context",
        "macro_volatility_context", "macro_liquidity_context",
        "macro_bond_context", "macro_auction_risk", "macro_active_themes",
        "macro_event_guards", "macro_directional_pressure", "macro_conflicts",
        "macro_plain_language_advisory", "macro_authority",
    }
    for row in rows:
        provenance = {}
        for field in FINAL_BOOK_FIELDS:
            if field in governed_fields or _is_missing(row.get(field)):
                continue
            provenance[field] = input_source
        for field in governed_fields:
            if not _is_missing(row.get(field)) and field not in {"field_provenance_json", "source_payload_json"}:
                provenance[field] = (
                    input_source
                    if field == "selected_quote_snapshot_id"
                    else "governed_materializer"
                )
        row["field_provenance_json"] = _json_safe(provenance)
    assembly = _enrich_lab_extract_rows_from_run_sources(rows, runs_dir, run_id)
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
    if sync_interpreter:
        try:
            import sys as _sys
            _repo_root = Path(runs_dir).parent.parent.parent
            _sys.path.insert(0, str(_repo_root / "pipeline_interpreter"))
            from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
            _ma_on_pipeline_complete(str(triage_csv_path), output_dir=str(out_dir))
        except Exception:
            pass

    payload = {
        "lab_schema_version": "lab_signal_book_v2",
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "candidate_count": len(rows),
        "verdict_counts": {
            verdict: sum(1 for row in rows if row.get("lab_verdict") == verdict)
            for verdict in ("GO", "GO_LIMIT", "PROBE", "MANUAL_LIQUIDITY_REVIEW", "CONTRACT_REPAIR", "MORNING_VALIDATION_REQUIRED", "ARMED", "WAIT", "BLOCKED")
        },
        "rows": rows,
        "source_manifest": assembly.get("sources", {}),
        "source_errors": assembly.get("source_errors", []),
        "reconciliation": {
            "input_rows": len(rows),
            "output_rows": len(rows),
            "unique_trade_idea_ids": len({row.get("trade_idea_id") for row in rows}),
            "duplicate_trade_idea_ids": len(rows) - len({row.get("trade_idea_id") for row in rows}),
            "selected_contract_rows": sum(1 for row in rows if row.get("contract_data_state") == "AVAILABLE"),
            "ev3_state_rows": sum(1 for row in rows if row.get("ev3_data_state") == "AVAILABLE"),
            "trigger_rows": sum(1 for row in rows if row.get("trigger_data_state") == "AVAILABLE"),
            "garch_rows": sum(1 for row in rows if row.get("garch_data_state") == "AVAILABLE"),
            "economics_comparable_rows": sum(
                1 for row in rows if row.get("economics_comparable") is True
            ),
            "economics_mismatch_rows": sum(
                1
                for row in rows
                if row.get("selected_structure_id")
                and row.get("economics_comparable") is not True
            ),
        },
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
