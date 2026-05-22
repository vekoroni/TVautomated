"""
AVSHUNTER — EOD Candidate Engine (Phase 1)
==========================================
Version : 1.3.0
Date    : 2026-05-05

PURPOSE
-------
Converts the full EIL-enriched pipeline output into a clean, structured
candidate manifest for the Morning Validation Engine.

DESIGN PRINCIPLE (NON-NEGOTIABLE)
----------------------------------
EOD answers ONE question only:  "Is this structurally primed?"
Morning answers ONE question:   "Is this actually tradeable right now?"

NEVER mix these. EOD must not gate on live IV, spread, or drift.
Morning must not reconsider Wyckoff structure — that work is done.

WHAT THIS FILE DOES
--------------------
1. Loads the EIL-enriched CSV (or superbrain_execute as fallback)
2. Merges WBS data (wall break scores) into each candidate row
3. Merges discovery-layer fields (stop_loss, VWAP, crabel, etc.)
4. Applies a structural tier classification (A / B / C / WATCH)
5. Computes a structural conviction score (0–100) from EOD-only signals
6. Tags each candidate with setup_type, expected_move_window, invalidation
7. Writes morning_candidates_{run_id}.csv — the handoff to Phase 2

TIER DEFINITIONS
-----------------
A  — Top-quartile OIS (≥35) + RR ≥ 1.5 + WBS PROBABLE + conv_score ≥ 3
B  — OIS ≥ 25 + RR ≥ 1.0 + WBS POSSIBLE + conv_score ≥ 2
C  — All other signals passing quality floor (OIS ≥ 15, RR > 0)
WATCH — Below quality floor but structurally interesting (no execution)

STRUCTURAL CONVICTION SCORE (SCS) — EOD only, no live data
------------------------------------------------------------
Component               Weight   Source
───────────────────────────────────────────────────────────
Options Intelligence    25%      options_score (0-41 observed max)
R:R Quality             20%      rr (0-3+ range)
Wyckoff/EV Structural   20%      ev2_ev_structural + composite
WBS Wall Strength       15%      wbs (0-60) + wbs_grade
Campaign Quality        10%      sb_conv_score (0-4) + sb_campaign
Superbrain Veto Load    10%      inverse of sb_warnings_count

OUTPUT SCHEMA (morning_candidates_{run_id}.csv)
------------------------------------------------
Required by morning_validation.py:

  ticker, direction, signal_price, strike, expiry, dte, premium
  structural_tier, scs_score, setup_type, expected_move_window
  invalidation_level, wall_price, wall_dist_pct
  rr, options_score, composite, ev2_ev_conf_adj
  sb_instrument_now, sb_campaign, sb_conv_score
  sb_time_stop_date, sb_checkpoint_date, sb_checkpoint_rule
  sb_ladder_summary, sb_position_size_pct
  eil_gex_score, eil_iv_score, eil_obi_score, eil_poc_score
  l3_expected_move_1_5d, l3_expected_move_1_10d
  win_rate_5d, win_rate_10d
  sector, sector_etf
  candidate_status
  signal_type, momentum_tier, pse_ev_mult, pse_final_size  (V2 Sprint 3)
  forward_momentum_conf
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    from scripts.macro_quant_packet import MACRO_QUANT_CSV_FIELDS
except Exception:
    from macro_quant_packet import MACRO_QUANT_CSV_FIELDS  # type: ignore

try:
    from contracts.handoff_contract import (
        PRIORITY_DOWNSTREAM_VALIDATION,
        SCANNER_FIELD_NAMES,
        enrich_dataframe_with_truth_packets,
    )
except Exception:
    from handoff_contract import (  # type: ignore
        PRIORITY_DOWNSTREAM_VALIDATION,
        SCANNER_FIELD_NAMES,
        enrich_dataframe_with_truth_packets,
    )

try:
    from vanguard.physics_state_engine import PHYSICS_FIELDS, ensure_physics_fields
except Exception:
    from physics_state_engine import PHYSICS_FIELDS, ensure_physics_fields  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EOD_ENGINE] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("eod_candidate_engine")

# ─── QUALITY FLOOR (minimum to appear in candidate manifest) ─────────────────
MIN_OPTIONS_SCORE  = 15     # below this → not worth monitoring
MIN_RR             = 0.0    # negative RR excluded
MIN_COMPOSITE      = 40.0   # below this → structurally weak
OPTIONS_RESEARCH_PERMISSION = "MANUAL_REVIEW_REQUIRED"
OPTIONS_BLOCKED_ROUTES = {"OPTIONS_BLOCKED", "OPTIONS_EQUITY_ONLY_BETTER"}
OPTIONS_REVIEWABLE_ROUTES = {"OPTIONS_GO_REVIEW", "OPTIONS_ARMED_HALF", "OPTIONS_PROBE_ONLY"}
OPTIONS_MISSING_TOKENS = {"", "NAN", "NONE", "NULL", "NA", "N/A"}

EOD_CARRY_FORWARD_STATUSES = {
    "EOD_THESIS_READY",
    "EOD_THESIS_READY_REPAIR_AT_OPEN",
    "EOD_TRIGGER_READY",
    "EOD_WATCHLIST_MONETISABLE",
    "EOD_PROBE_CANDIDATE",
    "EOD_DATA_INSUFFICIENT_REVIEW",
    # Backward-compatible legacy statuses still seen in archived payloads.
    "EOD_CATALYST_EXECUTE_CANDIDATE",
    "EOD_EXECUTE_CANDIDATE",
    "EOD_EXECUTE_WITH_CAUTION",
    "EOD_CONTRACT_REPAIR_REQUIRED",
    "EOD_TRIGGER_READY_REVIEW",
    "EOD_CATALYST_WATCH",
}

EOD_STRUCTURAL_BLOCK_STATUSES = {"EOD_STRUCTURAL_BLOCK", "EOD_NO_OPTIONS_ROUTE", "EOD_BLOCK"}

EOD_STRUCTURAL_BLOCK_TOKENS = {
    "INVALIDATION_BROKEN",
    "AT_WALL",
    "NO_RUNWAY",
    "HALTED",
    "NON_TRADEABLE",
    "NON_TRADEABLE_SECURITY",
    "CORPORATE_ACTION",
    "DEEP_NEGATIVE_STRUCTURAL_EV",
    "DATA_CORRUPTION",
    "MISSING_PRICE",
    "NO_UNDERLYING_PRICE",
}

EOD_NO_OPTIONS_ROUTE_TOKENS = {
    "NO_LIQUID_OTM_CONTRACT",
    "NO_OPTIONS_CHAIN",
    "NO_CHAIN",
    "NO_EXPIRY",
    "NO_OPTION_EXPIRY",
    "NO_OPTIONS_ROUTE",
    "NO_CONTRACT_MARKET",
    "NO_EXECUTABLE_MARKET",
    "NO_VIABLE_OPTION_AFTER_SEARCH",
}

EOD_REPAIRABLE_TOKENS = {
    "SPREAD",
    "LOW_OI",
    "OI_",
    "VOLUME",
    "IV",
    "OIS",
    "BSM",
    "SYNTHETIC",
    "QUOTE",
    "MISSING_CRITICAL",
    "MISSING_CONTRACT",
    "NO_CONTRACT_SELECTED",
    "BREAKEVEN",
    "ESTIMATED_R",
    "RR",
    "THETA",
    "NO_EDGE",
    "TIER_4_FLAT",
    "DATA_MISSING",
    "CAMPAIGN",
    "LOW_CONVEXITY",
    "MONITOR_ONLY",
    "DIRECTION_CONFLICT",
}

PHASE2_LAYER2_FIELDS = [
    "layer2__state_match_method",
    "layer2__state_match_stage",
    "layer2__state_match_dimensions",
    "layer2__state_match_quality",
    "layer2__state_match_similarity",
    "layer2__state_match_is_exact",
    "layer2__sample_size",
    "layer2__sample_confidence_bucket",
    "layer2__confidence_penalty",
    "layer2__confidence_weight",
    "layer2__preferred_horizon",
    "layer2__matched_state_key",
    "layer2__original_state_key",
    "layer2__fallback_reason",
    "layer2__raw_prob_up_5d",
    "layer2__raw_prob_up_10d",
    "layer2__raw_prob_up_20d",
    "layer2__raw_prob_down_5d",
    "layer2__raw_prob_down_10d",
    "layer2__raw_prob_down_20d",
    "layer2__raw_prob_target_hit",
    "layer2__raw_prob_stop_hit",
    "layer2__raw_expected_return",
    "layer2__raw_expected_drawdown",
    "layer2__raw_expected_time_to_target",
    "layer2__baseline_probability",
    "layer2__adjusted_prob_target_hit",
    "layer2__adjusted_expected_return",
    "layer2__probability_edge",
    "layer2__probability_verdict",
]

CATALYST_TRUTH_FIELDS = [
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

# ─── TIER THRESHOLDS ─────────────────────────────────────────────────────────
TIER_A = {"options_score": 35, "rr": 1.5, "conv": 3}
TIER_B = {"options_score": 25, "rr": 1.0, "conv": 2}

# ─── EXPECTED MOVE WINDOW ────────────────────────────────────────────────────
def _expected_move_window(dte: float) -> str:
    if dte <= 14:  return "1-5d"
    if dte <= 30:  return "1-10d"
    if dte <= 60:  return "1-20d"
    return "1-30d+"

def _horizon_trade_window(horizon_bucket: str, fallback: str) -> str:
    bucket = str(horizon_bucket or "").strip().lower()
    if bucket == "1_5d":
        return "1-5d"
    if bucket == "6_10d":
        return "6-10d"
    if bucket == "11_20d":
        return "11-20d"
    return fallback

# ─── SETUP TYPE ──────────────────────────────────────────────────────────────
def _setup_type(row: dict) -> str:
    phase   = str(row.get("phase", "")).upper()
    intent  = str(row.get("intent", "")).upper()
    crabel  = str(row.get("crabel_pattern", "")).upper()
    wbs_g   = str(row.get("wbs_grade", "")).upper()

    if "ACCUMULATION" in str(row.get("wyckoff_phase_bucket", "")).upper():
        return "WYCKOFF_ACCUMULATION"
    if "DISTRIBUTION" in str(row.get("wyckoff_phase_bucket", "")).upper():
        return "WYCKOFF_DISTRIBUTION"
    if "NR7" in crabel or "ULTRA" in crabel:
        return "CRABEL_NR7_COMPRESSION"
    if "SELL_SETUP" in intent:
        return "STRUCTURAL_SELL"
    if "BUY_SETUP" in intent:
        return "STRUCTURAL_BUY"
    if "TRANSITION" in intent:
        return "TRANSITION_PLAY"
    return "STRUCTURAL_SETUP"

# ─── INVALIDATION LEVEL ──────────────────────────────────────────────────────
def _invalidation_level(row: dict) -> Optional[float]:
    """
    For puts: invalidation is above entry (price rallies through stop).
    For calls: invalidation is below entry (price falls through stop).
    Uses stop_loss from discovery layer, falls back to signal_price ± ATR.
    """
    signal = _flt(row, "signal_price")
    direction = str(row.get("direction", "")).upper()
    stop = _flt(row, "stop_loss")
    if stop and stop > 0:
        if not signal:
            return round(stop, 2)
        if direction == "PUT" and stop > signal:
            return round(stop, 2)
        if direction != "PUT" and stop < signal:
            return round(stop, 2)

    atr    = _flt(row, "ATR_14")
    if signal and atr:
        if direction == "PUT":
            return round(signal + atr * 1.5, 2)
        return round(signal - atr * 1.5, 2)
    if signal:
        if direction == "PUT":
            return round(signal * 1.03, 2)
        return round(signal * 0.97, 2)
    return None

# ─── FLOAT HELPER ────────────────────────────────────────────────────────────
def _flt(row: dict, key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, default)
        if v is None: return default
        f = float(v)
        return default if (f != f) else f   # nan check
    except (TypeError, ValueError):
        return default

def _str(row: dict, key: str, default: str = "") -> str:
    v = row.get(key, default)
    if v is None or str(v).lower() in ("nan", "none", ""):
        return default
    return str(v).strip()

def _first_str(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = _str(row, key)
        if value:
            return value
    return default

def _first_flt(row: dict, *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = _flt(row, key, default=0.0)
        if value != 0.0:
            return value
    return default

def _flag_text(row: dict, *keys: str) -> str:
    for key in keys:
        value = _str(row, key)
        if value and value.upper() not in OPTIONS_MISSING_TOKENS:
            return value
    return ""

def _options_research_route(row: dict) -> str:
    return _flag_text(row, "final_route", "options_research_route", "options_final_route").upper()

def _options_hard_vetoes(row: dict) -> str:
    return _flag_text(row, "hard_vetoes", "options_hard_vetoes")

# E2E-OPTIONS-LAB-SYNC 2026-05-22: only genuine no-market/binary-event
# conditions block the handoff. Soft contract economics become repair flags.
def _options_genuine_hard_block(row: dict) -> bool:
    blob = " ".join([
        _str(row, "hard_vetoes"),
        _str(row, "options_hard_vetoes"),
        _str(row, "block_code"),
        _str(row, "block_detail"),
        _str(row, "stand_down_reason"),
    ]).upper()
    hard_tokens = {
        "NO_OPTIONS_CHAIN",
        "NO_CHAIN_DATA",
        "NO_CHAIN",
        "NO_OPTIONS_MARKET",
        "NO_CONTRACT_MARKET",
        "HALT_RISK",
        "NON_TRADEABLE",
        "EARNINGS_WITHIN_DTE",
        "FDA_BINARY_EVENT",
        "DTE_NON_POSITIVE",
    }
    soft_tokens = {
        "NO_CONTRACT_PASSED_QUALITY_GATES",
        "ESTIMATED_R_LT_1",
        "ESTIMATED_R_MISSING",
        "SPREAD_GT_25PCT",
        "CONTRACT_DATA_INCOMPLETE",
        "MID_NON_POSITIVE",
    }
    if any(tok in blob for tok in soft_tokens):
        return False
    return any(tok in blob for tok in hard_tokens)

def _options_research_block_reason(row: dict) -> str:
    route = _options_research_route(row)
    vetoes = _options_hard_vetoes(row)
    if route in OPTIONS_BLOCKED_ROUTES:
        if vetoes:
            return f"{route}:{vetoes}"
        return route
    if vetoes:
        return f"OPTIONS_HARD_VETO:{vetoes}"
    return ""

def _options_blocked_for_morning_candidate(row: dict) -> bool:
    """Return True when options research found a contract-level block.

    The structural thesis can still be useful for audit, shadow-book review, or
    a separate contract-repair queue. It must not enter the executable morning
    candidate slate as a normal candidate.
    """
    route = _options_research_route(row)
    severity = _str(row, "block_severity").upper()
    genuine_hard = _options_genuine_hard_block(row)
    return bool(genuine_hard and (route in OPTIONS_BLOCKED_ROUTES or severity == "HARD"))

def _reason_blob(row: dict, *extra: str) -> str:
    parts = [str(x or "") for x in extra if str(x or "").strip()]
    for key in (
        "eod_candidate_reason",
        "eod_dropoff_reason",
        "pse_block_reason",
        "fd_reason",
        "signal_authority_reason",
        "execution_authority_reason",
        "contract_repair_reason",
        "hard_vetoes",
        "options_hard_vetoes",
        "research_route_reason",
    ):
        value = _str(row, key)
        if value:
            parts.append(value)
    return " | ".join(parts).upper()

def _has_any_token(text: str, tokens: set[str]) -> bool:
    text_u = str(text or "").upper()
    return any(token in text_u for token in tokens)

def _eod_failure_class(row: dict, reason: str = "") -> str:
    blob = _reason_blob(row, reason)
    if _has_any_token(blob, EOD_NO_OPTIONS_ROUTE_TOKENS):
        return "NO_OPTIONS_ROUTE"
    if _has_any_token(blob, EOD_STRUCTURAL_BLOCK_TOKENS):
        return "STRUCTURAL_BLOCK"
    if _has_any_token(blob, EOD_REPAIRABLE_TOKENS):
        return "REPAIRABLE_ADVISORY"
    return "NONE"

def _is_structural_eod_failure(row: dict, reason: str = "") -> bool:
    return _eod_failure_class(row, reason) in {"STRUCTURAL_BLOCK", "NO_OPTIONS_ROUTE"}

def _thesis_state_from_eod_status(eod_status: str) -> str:
    status = str(eod_status or "").upper()
    if status == "EOD_THESIS_READY":
        return "VALID_THESIS_READY"
    if status == "EOD_THESIS_READY_REPAIR_AT_OPEN":
        return "VALID_THESIS_REPAIR_AT_OPEN"
    if status == "EOD_TRIGGER_READY":
        return "VALID_THESIS_TRIGGER_PENDING"
    if status == "EOD_WATCHLIST_MONETISABLE":
        return "VALID_THESIS_WATCHLIST"
    if status == "EOD_PROBE_CANDIDATE":
        return "VALID_THESIS_PROBE"
    if status == "EOD_DATA_INSUFFICIENT_REVIEW":
        return "VALID_THESIS_DATA_REVIEW"
    if status == "EOD_NO_OPTIONS_ROUTE":
        return "NO_OPTIONS_ROUTE"
    if status == "EOD_STRUCTURAL_BLOCK":
        return "STRUCTURAL_BLOCK"
    return "VALID_THESIS_REVIEW"

def _morning_tasks_for_status(row: dict, eod_status: str, reason: str = "") -> str:
    tasks = ["confirm thesis live", "check price vs invalidation", "validate preferred contract"]
    status = str(eod_status or "").upper()
    blob = _reason_blob(row, reason)
    if status in {"EOD_THESIS_READY_REPAIR_AT_OPEN", "EOD_DATA_INSUFFICIENT_REVIEW"} or _has_any_token(blob, EOD_REPAIRABLE_TOKENS):
        tasks.append("repair contract if spread/liquidity/breakeven fails")
    if status in {"EOD_TRIGGER_READY", "EOD_PROBE_CANDIDATE"}:
        tasks.append("confirm trigger/tape before entry")
    if "PCR_VOL" in blob:
        tasks.append("confirm live options flow")
    if "DIRECTION_CONFLICT" in blob:
        tasks.append("resolve direction conflict")
    if _str(row, "direction_conflict_gate").upper() == "VWAP_CONFIRMATION_REQUIRED":
        tasks.append("confirm price is on the correct side of VWAP")
    return "; ".join(dict.fromkeys(tasks))

def _candidate_permission_fields(row: dict, eod_status: str) -> dict:
    # FIX 5: PSE retired — default is MANUAL (not NO) so rows are not killed by legacy gate
    live_permission = _str(row, "capital_permission", "MANUAL").upper()
    status = str(eod_status or "").upper()
    if status in EOD_STRUCTURAL_BLOCK_STATUSES:
        candidate_permission = "STRUCTURAL_REVIEW_ONLY"
    elif status == "EOD_THESIS_READY_REPAIR_AT_OPEN":
        candidate_permission = "CONTRACT_REPAIR_REQUIRED"
    elif live_permission == "EOD_CANDIDATE_ONLY" or status in EOD_CARRY_FORWARD_STATUSES:
        candidate_permission = "MORNING_VALIDATION_REQUIRED"
    else:
        candidate_permission = "REVIEW_ONLY"

    manual_required = candidate_permission in {"MORNING_VALIDATION_REQUIRED", "CONTRACT_REPAIR_REQUIRED"}
    return {
        "live_capital_permission": live_permission,
        "eod_candidate_permission": candidate_permission,
        "candidate_size": 0.0,
        "sizing_policy": "ADVISORY_ONLY",
        "candidate_size_status": "MANUAL_SIZE_REQUIRED"
        if manual_required
        else "REVIEW_ONLY_NO_SIZE",
        "candidate_size_source": "HUMAN_REVIEW_REQUIRED"
        if manual_required
        else "REVIEW_ONLY",
        "manual_sizing_required": manual_required,
        "eod_live_capital_permission": "HUMAN_REVIEW_REQUIRED"
        if manual_required
        else live_permission,
    }

def _handoff_lane(eod_status: str) -> str:
    """Operator-facing lane for EOD to morning handoff.

    candidate_status is intentionally stricter than eod_candidate_status:
    repair/watch/trigger names may be carried into morning validation, but
    they must not look execution-ready before live confirmation.
    """
    status = str(eod_status or "").upper()
    if status == "EOD_THESIS_READY":
        return "EXECUTION_READY"
    if status == "EOD_THESIS_READY_REPAIR_AT_OPEN":
        return "REPAIR_AT_OPEN"
    if status == "EOD_TRIGGER_READY":
        return "TRIGGER_REQUIRED"
    if status == "EOD_PROBE_CANDIDATE":
        return "PROBE_REVIEW"
    if status == "EOD_WATCHLIST_MONETISABLE":
        return "WATCH_ONLY"
    if status == "EOD_DATA_INSUFFICIENT_REVIEW":
        return "DATA_REVIEW_REQUIRED"
    if status in EOD_STRUCTURAL_BLOCK_STATUSES:
        return "BLOCKED_REVIEW"
    return "REVIEW_ONLY"

def _candidate_status_for_handoff(eod_status: str) -> str:
    lane = _handoff_lane(eod_status)
    if lane == "EXECUTION_READY":
        return "READY_FOR_VALIDATION"
    return lane

def _true_fatal_block(row: dict) -> bool:
    """
    Treat PSE/FDE fatal labels as advisory unless the row is missing a real
    market/contract/data requirement. A sizing model must not kill a valid
    long-call/long-put thesis by itself.
    """
    pse_mode = _str(row, "pse_execution_mode").upper()
    effective = _str(row, "effective_execution_verdict").upper()
    fd_verdict = _str(row, "fd_verdict").upper()
    has_fatal_label = "FATAL_BLOCK" in {pse_mode, effective} or fd_verdict == "BLOCK"
    if not has_fatal_label:
        return False

    reason_blob = " | ".join(
        _str(row, key)
        for key in (
            "pse_block_reason",
            "fd_reason",
            "signal_authority_reason",
            "execution_authority_reason",
            "contract_repair_reason",
        )
        if _str(row, key)
    ).upper()
    true_fatal_tokens = (
        "DATA_FAILURE",
        "NO_OHLCV",
        "NO_OPTIONS_CHAIN",
        "NO_CHAIN",
        "NO_CONTRACT_MARKET",
        "NO_EXECUTABLE_MARKET",
        "MISSING_PRICE",
        "MISSING_CONTRACT",
    )
    if any(token in reason_blob for token in true_fatal_tokens):
        return True

    signal = _resolved_signal_type(row).upper()
    eil = _str(row, "eil_v3_verdict").upper()
    ois = _flt(row, "options_score")
    rr = _flt(row, "rr_underlying") or _flt(row, "rr")
    if signal in {"CURRENT_EDGE", "FUTURE_EDGE", "STRUCTURAL_MATCH", "TRANSITION"} and eil in {"EXECUTE", "EXECUTE_WITH_CAUTION"} and ois >= MIN_OPTIONS_SCORE and rr >= MIN_RR:
        return False
    return has_fatal_label and fd_verdict == "BLOCK"

def _resolved_signal_type(row: dict) -> str:
    final_signal = _str(row, "signal_type").upper()
    pse_signal = _str(row, "pse_signal_type").upper()
    actuarial_signal = _str(row, "actuarial_signal_type").upper()
    if final_signal and final_signal not in {"NO_EDGE", "DATA_MISSING", "TIER_4_FLAT"}:
        return final_signal
    if pse_signal and pse_signal not in {"NO_EDGE", "DATA_MISSING", "TIER_4_FLAT"}:
        return pse_signal
    return final_signal or pse_signal or actuarial_signal

def _resolved_momentum_tier(row: dict) -> str:
    final_tier = _str(row, "momentum_tier").upper()
    pse_tier = _str(row, "pse_momentum_tier").upper()
    actuarial_tier = _str(row, "actuarial_momentum_tier").upper()
    if final_tier and final_tier not in {"TIER_4_FLAT", "DATA_MISSING"}:
        return final_tier
    if pse_tier and pse_tier not in {"TIER_4_FLAT", "DATA_MISSING"}:
        return pse_tier
    return final_tier or pse_tier or actuarial_tier

def _normalise_current_contract(row: dict) -> dict:
    """Bridge current OI/EIL fields into the historical EOD manifest contract."""
    if _flt(row, "signal_price") == 0.0:
        row["signal_price"] = _first_flt(
            row,
            "underlying_price",
            "current_price",
            "spot_price",
            "close",
            "last_close",
            "price",
            default=0.0,
        )
    if _flt(row, "target_price") == 0.0:
        row["target_price"] = _first_flt(
            row,
            "structural_target",
            "target",
            "take_profit",
            "expected_target",
            default=0.0,
        )
    if not _str(row, "sb_campaign"):
        row["sb_campaign"] = _first_str(
            row,
            "convexity_campaign",
            "campaign",
            "options_campaign",
            default="",
        )
    if _flt(row, "sb_conv_score") == 0.0:
        row["sb_conv_score"] = _first_flt(
            row,
            "convexity_score",
            "convexity_tier",
            "campaign_score",
            default=0.0,
        )
    if _flt(row, "pse_score") == 0.0:
        row["pse_score"] = _first_flt(
            row,
            "pse_edge_score",
            "eil_score",
            "eil_composite_score",
            default=0.0,
        )
    row["resolved_signal_type"] = _resolved_signal_type(row)
    row["resolved_momentum_tier"] = _resolved_momentum_tier(row)
    if _flt(row, "actuarial_forward_momentum_conf") == 0.0:
        row["actuarial_forward_momentum_conf"] = _first_flt(
            row,
            "fwd_momentum_conf",
            "vanguard_fwd_momentum_conf",
            "layer2__forward_momentum_confidence",
            default=0.0,
        )
    return row

def _audit_raw_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().lower() in {"", "nan", "none", "null", "na", "n/a"}

def _audit_has_number(row: dict, *keys: str) -> bool:
    for key in keys:
        value = row.get(key)
        if _audit_raw_blank(value):
            continue
        try:
            parsed = pd.to_numeric(value, errors="coerce")
            if not pd.isna(parsed):
                return True
        except Exception:
            continue
    return False

def _audit_side(value) -> str:
    text = str(value or "").strip().upper()
    if text in {"CALL", "CALLS", "LONG_CALL", "BULL", "BULLISH", "UP", "BUY"}:
        return "CALL"
    if text in {"PUT", "PUTS", "LONG_PUT", "BEAR", "BEARISH", "DOWN", "SELL", "SHORT"}:
        return "PUT"
    return ""

def _direction_arbitration(row: dict) -> dict:
    option_side = _audit_side(_first_str(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "option_direction", "selected_contract_side"))
    vanguard_side = _audit_side(_first_str(row, "vanguard_edge_direction", "layer2__edge_direction", "vanguard_edge_direction_flat", "edge_direction"))
    intent = _str(row, "intent").upper()
    if not option_side:
        return {
            "direction_arbitration_status": "NOT_EVALUATED",
            "direction_arbitration_reason": "No tradeable options direction available",
            "direction_conflict_gate": "NONE",
        }
    if not vanguard_side:
        return {
            "direction_arbitration_status": "NO_PROBABILITY_OPINION",
            "direction_arbitration_reason": f"Structure leads: {intent or 'UNKNOWN'} maps to {option_side}; Vanguard has no directional edge",
            "direction_conflict_gate": "NONE",
        }
    if option_side == vanguard_side:
        return {
            "direction_arbitration_status": "AGREEMENT",
            "direction_arbitration_reason": f"Structure and Vanguard both support {option_side}",
            "direction_conflict_gate": "NONE",
        }
    return {
        "direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS",
        "direction_arbitration_reason": f"Structure maps to {option_side} while Vanguard edge is {vanguard_side}; require live tape confirmation",
        "direction_conflict_gate": "VWAP_CONFIRMATION_REQUIRED",
    }

def _catalyst_direction_conflict(row: dict) -> dict:
    catalyst_side = _audit_side(_first_str(row, "catalyst_direction_bias", "catalyst_trade_bias"))
    option_side = _audit_side(_first_str(row, "canonical_direction", "resolved_direction", "footprint_direction", "direction", "primary_direction", "options_direction", "option_direction", "selected_contract_side"))
    explicit = _str(row, "catalyst_alignment_label").upper() == "DIRECTION_CONFLICT"

    if catalyst_side and option_side and catalyst_side != option_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONFLICT_REQUIRES_CONFIRMATION",
            "catalyst_direction_conflict_reason": f"Catalyst side {catalyst_side} conflicts with thesis side {option_side}",
        }
    if explicit and not catalyst_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONTEXT_REVIEW",
            "catalyst_direction_conflict_reason": "Upstream catalyst label is DIRECTION_CONFLICT but no explicit catalyst side was provided",
        }
    if catalyst_side and option_side and catalyst_side == option_side:
        return {
            "catalyst_direction_conflict_status": "CATALYST_CONFIRMS",
            "catalyst_direction_conflict_reason": f"Catalyst and thesis both support {option_side}",
        }
    return {
        "catalyst_direction_conflict_status": "NO_CATALYST_OPINION",
        "catalyst_direction_conflict_reason": "",
    }


def _normalise_audit_handoff_fields(row: dict) -> dict:
    """Make EOD audit fields explicit even when an upstream path left blanks."""
    pcr_status = _str(row, "pcr_vol_status").upper()
    pcr_signal = _first_str(row, "pcr_signal", "dw_signal").upper()
    verdict = _first_str(row, "options_verdict", "eil_v3_verdict", "fd_verdict").upper()

    if not pcr_status:
        if _audit_has_number(row, "dw_pcr_vol", "pcr_vol"):
            row["pcr_vol_status"] = "OK"
        elif pcr_signal in {"BULLISH", "BEARISH", "NEUTRAL", "STRONGLY_BULLISH", "STRONGLY_BEARISH"}:
            row["pcr_vol_status"] = "OI_ONLY_NO_INTRADAY_VOLUME"
        elif verdict in {"STAND_DOWN", "BLOCK", "BLOCKED"}:
            row["pcr_vol_status"] = "NOT_EVALUATED"
        else:
            row["pcr_vol_status"] = "MISSING"

    if not _str(row, "pcr_vol_missing_reason"):
        status = _str(row, "pcr_vol_status").upper()
        if status == "OI_ONLY_NO_INTRADAY_VOLUME":
            row["pcr_vol_missing_reason"] = "OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE;USING_OPEN_INTEREST_PCR_ONLY"
        elif status == "NOT_EVALUATED":
            row["pcr_vol_missing_reason"] = "NOT_EVALUATED_BEFORE_FLOW_REVIEW"
        elif status == "MISSING":
            row["pcr_vol_missing_reason"] = "NO_PCR_VOLUME_OR_OI_SIGNAL"

    if not _str(row, "pcr_direction_conflict_status") and "PCR" in _str(row, "direction_conflict_reason").upper():
        legacy_status = _str(row, "direction_conflict_status").upper()
        row["pcr_direction_conflict_status"] = (
            "PCR_CONFLICT_REQUIRES_FLOW_CONFIRMATION"
            if legacy_status == "UNRESOLVED"
            else (_str(row, "direction_conflict_status") or "PCR_CONFLICT_REQUIRES_FLOW_CONFIRMATION")
        )
        row["pcr_direction_conflict_reason"] = _str(row, "direction_conflict_reason")
    if not _str(row, "pcr_direction_conflict_status"):
        row["pcr_direction_conflict_status"] = "NOT_EVALUATED" if verdict in {"STAND_DOWN", "BLOCK", "BLOCKED"} else "NO_PCR_CONFLICT"
    if not _str(row, "pcr_direction_conflict_reason"):
        row["pcr_direction_conflict_reason"] = ""

    catalyst_audit = _catalyst_direction_conflict(row)
    for key, value in catalyst_audit.items():
        if not _str(row, key):
            row[key] = value

    arbitration = _direction_arbitration(row)
    for key, value in arbitration.items():
        if not _str(row, key):
            row[key] = value

    structural_conflict = _str(row, "direction_arbitration_status").upper() == "CONFLICT_STRUCTURE_LEADS"
    catalyst_conflict = _str(row, "catalyst_direction_conflict_status").upper() == "CATALYST_CONFLICT_REQUIRES_CONFIRMATION"
    pcr_conflict = "CONFLICT" in _str(row, "pcr_direction_conflict_status").upper()
    if verdict in {"STAND_DOWN", "BLOCK", "BLOCKED"}:
        row["direction_conflict_status"] = "NOT_EVALUATED"
        row["direction_conflict_reason"] = ""
    elif structural_conflict or catalyst_conflict or pcr_conflict:
        row["direction_conflict_status"] = "MITIGATED_REQUIRES_CONFIRMATION"
        if structural_conflict or catalyst_conflict:
            row["direction_conflict_gate"] = "VWAP_CONFIRMATION_REQUIRED"
        parts = []
        if structural_conflict:
            parts.append(_str(row, "direction_arbitration_reason") or "STRUCTURE_PROBABILITY_CONFLICT")
        if catalyst_conflict:
            parts.append(_str(row, "catalyst_direction_conflict_reason") or "CATALYST_DIRECTION_CONFLICT")
        if pcr_conflict:
            parts.append(_str(row, "pcr_direction_conflict_reason") or "PCR_DIRECTION_CONFLICT")
        row["direction_conflict_reason"] = "; ".join(parts)
    else:
        row["direction_conflict_status"] = "NO_CONFLICT"
        row["direction_conflict_reason"] = ""
        if not _str(row, "direction_conflict_gate"):
            row["direction_conflict_gate"] = "NONE"
    if _str(row, "execution_permission").upper() == OPTIONS_RESEARCH_PERMISSION and not _str(row, "options_research_permission"):
        row["options_research_permission"] = OPTIONS_RESEARCH_PERMISSION
    if _options_research_route(row) and not _str(row, "options_research_route"):
        row["options_research_route"] = _options_research_route(row)
    if _options_hard_vetoes(row) and not _str(row, "options_hard_vetoes"):
        row["options_hard_vetoes"] = _options_hard_vetoes(row)

    # put_gate enforcement: gate PUT candidates when macro explicitly blocks PUTs or
    # when the enrichment delta marks do_not_unblock_put_gate on every matched theme.
    _candidate_side = _audit_side(_first_str(
        row, "canonical_direction", "resolved_direction", "direction",
        "primary_direction", "options_direction", "option_direction",
    ))
    if _candidate_side == "PUT":
        _put_perm = _str(row, "macro_enrichment_put_gate_permission").upper()
        _existing_cs = _str(row, "direction_conflict_status").upper()
        _enrichment_confs = _str(row, "macro_enrichment_confirmation_required").upper()
        _needs_gate = (
            _put_perm in {"BLOCKED", "RESTRICTED", "NO_GO"}
            or "PUT_GATE_DELTA_LOCK" in _enrichment_confs
        )
        if _needs_gate and _existing_cs not in {"UNRESOLVED", "NOT_EVALUATED"}:
            row["direction_conflict_status"] = "MITIGATED_REQUIRES_CONFIRMATION"
            _gate_tag = f"PUT_GATE_{_put_perm}" if _put_perm in {"BLOCKED", "RESTRICTED", "NO_GO"} else "PUT_GATE_DELTA_LOCK"
            _existing_reason = _str(row, "direction_conflict_reason")
            row["direction_conflict_reason"] = "; ".join(filter(None, [_existing_reason, _gate_tag]))
            if not _str(row, "direction_conflict_gate") or _str(row, "direction_conflict_gate") == "NONE":
                row["direction_conflict_gate"] = "PUT_GATE_MACRO_REQUIRED"

    return row

def _eod_candidate_status(row: dict, tier: str) -> tuple[str, str]:
    eil_verdict = _str(row, "eil_v3_verdict").upper()
    trigger_quality = _str(row, "trigger_quality").upper()
    trigger_go = _str(row, "trigger_go_eligible").upper() in {"TRUE", "1", "YES"}
    catalyst_class = _str(row, "catalyst_trade_class").upper()
    catalyst_quality = _str(row, "catalyst_data_quality").upper()
    repair_required = _str(row, "contract_repair_required").upper() in {"TRUE", "1", "YES"}
    direction_conflict_status = _str(row, "direction_conflict_status").upper()
    options_block_reason = _options_research_block_reason(row)
    signal = _resolved_signal_type(row).upper()
    momentum_tier = _resolved_momentum_tier(row).upper()
    horizon_bucket = _str(row, "horizon_bucket").lower()

    if options_block_reason:
        failure_class = _eod_failure_class(row, options_block_reason)
        if failure_class == "NO_OPTIONS_ROUTE":
            return "EOD_NO_OPTIONS_ROUTE", f"NO_OPTIONS_ROUTE:{options_block_reason}"
        if failure_class == "STRUCTURAL_BLOCK":
            return "EOD_STRUCTURAL_BLOCK", f"STRUCTURAL_BLOCK:{options_block_reason}"
        # Under the v4 signal-first policy, options economics/score vetoes are
        # advisory unless they prove there is no liquid OTM contract.

    if _true_fatal_block(row):
        reason = _str(row, "signal_authority_reason") or _str(row, "pse_block_reason") or "HARD_BLOCK"
        failure_class = _eod_failure_class(row, reason)
        if failure_class == "NO_OPTIONS_ROUTE":
            return "EOD_NO_OPTIONS_ROUTE", reason
        if failure_class == "STRUCTURAL_BLOCK":
            return "EOD_STRUCTURAL_BLOCK", reason
        return "EOD_DATA_INSUFFICIENT_REVIEW", reason

    if direction_conflict_status == "UNRESOLVED":
        return "EOD_DATA_INSUFFICIENT_REVIEW", _str(row, "direction_conflict_reason") or "DIRECTION_CONFLICT_UNRESOLVED"
    if direction_conflict_status == "MITIGATED_REQUIRES_CONFIRMATION":
        # FIX 1: Promote to passable — direction conflict is a trader note, not a kill.
        return "EOD_TRIGGER_READY", _str(row, "direction_conflict_reason") or "DIRECTION_CONFLICT_MITIGATED_REQUIRES_CONFIRMATION"

    if repair_required:
        return "EOD_THESIS_READY_REPAIR_AT_OPEN", _str(row, "contract_repair_reason") or "CONTRACT_REPAIR_REQUIRED"

    if trigger_go:
        return "EOD_TRIGGER_READY", "TRIGGER_GO_ELIGIBLE"

    if catalyst_class == "DATED_CATALYST_CONFIRMED":
        if eil_verdict in {"EXECUTE", "EXECUTE_WITH_CAUTION"}:
            return "EOD_THESIS_READY", "DATED_CATALYST_CONFIRMED"
        return "EOD_TRIGGER_READY", "DATED_CATALYST_NEEDS_PRICE_TRIGGER"

    if catalyst_class == "EVENT_CONVEXITY_WATCH" or catalyst_quality in {"CONFIRMED", "DATED_REVIEW", "INFERRED_GOOD"}:
        return "EOD_WATCHLIST_MONETISABLE", "CATALYST_OVERLAY_REVIEW"

    if eil_verdict == "EXECUTE":
        return "EOD_THESIS_READY", "EIL_EXECUTE"
    if eil_verdict == "EXECUTE_WITH_CAUTION":
        return "EOD_THESIS_READY_REPAIR_AT_OPEN", "EIL_EXECUTE_WITH_CAUTION"

    if trigger_quality == "STRONG" or trigger_go:
        return "EOD_TRIGGER_READY", "TRIGGER_READY_BUT_EIL_NOT_EXECUTE"

    if signal in {"NO_EDGE", "DATA_MISSING"} or momentum_tier in {"TIER_4_FLAT", "DATA_MISSING"}:
        if horizon_bucket == "11_20d":
            return "EOD_PROBE_CANDIDATE", "SPARSE_ACTUARIAL_LONG_HORIZON_REVIEW"
        return "EOD_DATA_INSUFFICIENT_REVIEW", "SPARSE_OR_FLAT_ACTUARIAL_CONTEXT"

    if tier == "WATCH":
        return "EOD_WATCHLIST_MONETISABLE", "QUALITY_FLOOR_NOT_MET_BUT_THESIS_PRESERVED"

    return "EOD_WATCHLIST_MONETISABLE", "STRUCTURE_VALID_BUT_NOT_EXECUTE"

def _footprint_direction(row: dict) -> str:
    """Resolve the structural Wyckoff/compression footprint side.

    The footprint is the thesis anchor for the expected hold window. Option
    contract side, macro hints, and morning tape can require repair or
    confirmation, but they must not silently invert this side.
    """
    call_score = 0.0
    put_score = 0.0

    def add(side: str, points: float) -> None:
        nonlocal call_score, put_score
        if side == "CALL":
            call_score += points
        elif side == "PUT":
            put_score += points

    for key, points in (
        ("direction", 2.0),
        ("signal_direction", 1.5),
        ("recommended_direction", 1.5),
        ("swing_direction", 2.0),
        ("fusion_direction", 2.0),
        ("vanguard_edge_direction", 1.0),
        ("layer2__edge_direction", 1.0),
    ):
        side = _side_from_text(_str(row, key))
        if side:
            add(side, points)

    phase_text = " ".join(
        _str(row, key).upper()
        for key in (
            "wyckoff_phase_bucket",
            "phase",
            "phase_v2",
            "dominant_event",
            "intent",
            "precor_intent",
            "dominant_trend",
            "control_state",
            "setup_type",
            "crabel_state",
            "crabel_pattern",
        )
    )
    if any(token in phase_text for token in ("ACCUMULATION", "SPRING", "SIGN_OF_STRENGTH", "SOS", "BUY_SETUP", "MARKUP", "BUYERS")):
        add("CALL", 2.0)
    if any(token in phase_text for token in ("DISTRIBUTION", "UPTHRUST", "SIGN_OF_WEAKNESS", "SOW", "SELL_SETUP", "MARKDOWN", "SELLERS")):
        add("PUT", 2.0)

    force = _flt(row, "directional_force")
    if force >= 5:
        add("CALL", 1.0)
    elif force <= -5:
        add("PUT", 1.0)

    signal = _flt(row, "signal_price") or _first_flt(row, "underlying_price", "current_price", "spot_price")
    target = _flt(row, "target_price") or _first_flt(row, "structural_target", "target")
    if signal and target:
        if target > signal * 1.003:
            add("CALL", 1.0)
        elif target < signal * 0.997:
            add("PUT", 1.0)

    if abs(call_score - put_score) < 1.0:
        return ""
    return "CALL" if call_score > put_score else "PUT"


def _major_catalyst_can_break_footprint(row: dict, catalyst_side: str, footprint_side: str) -> bool:
    if not catalyst_side or not footprint_side or catalyst_side == footprint_side:
        return False
    catalyst_class = _str(row, "catalyst_trade_class").upper()
    catalyst_quality = _str(row, "catalyst_data_quality").upper()
    inside_dte = _str(row, "catalyst_inside_dte").upper() in {"TRUE", "1", "YES"}
    event_convexity = _str(row, "event_convexity").upper() in {"TRUE", "1", "YES"}
    return (
        catalyst_class in {"DATED_CATALYST_CONFIRMED", "EVENT_CONVEXITY_WATCH"}
        or catalyst_quality in {"CONFIRMED", "DATED_REVIEW"}
        or inside_dte
        or event_convexity
    )

def _candidate_direction(row: dict) -> str:
    """Resolve the executable CALL/PUT side for the morning handoff."""
    footprint = _footprint_direction(row)
    if footprint in {"CALL", "PUT"}:
        return footprint
    for key in (
        "direction",
        "options_direction",
        "option_direction",
        "signal_direction",
        "recommended_direction",
    ):
        value = _str(row, key).upper()
        if value in {"CALL", "PUT"}:
            return value
        if value == "BULLISH":
            return "CALL"
        if value == "BEARISH":
            return "PUT"

    raw = " ".join(
        _str(row, key).upper()
        for key in (
            "intent",
            "precor_intent",
            "dominant_trend",
            "control_state",
            "options_strategy",
            "recommended_contract",
            "contract_occ_symbol",
        )
    )
    if "SELL_SETUP" in raw or "LONG_PUT" in raw or "BEARISH" in raw or "SELLERS" in raw:
        return "PUT"
    if "BUY_SETUP" in raw or "LONG_CALL" in raw or "BULLISH" in raw or "BUYERS" in raw:
        return "CALL"
    return ""

def _side_from_text(value: str) -> str:
    text = str(value or "").upper()
    if text in {"P", "PUT", "BEAR", "BEARISH", "SHORT", "DOWN", "DOWNSIDE", "SELL"}:
        return "PUT"
    if text in {"C", "CALL", "BULL", "BULLISH", "LONG", "UP", "UPSIDE", "BUY"}:
        return "CALL"
    if "PUT" in text or "BEARISH" in text or "SHORT" in text or "DOWN" in text:
        return "PUT"
    if "CALL" in text or "BULLISH" in text or "LONG" in text or "UP" in text:
        return "CALL"
    return ""

def _contract_side(row: dict) -> str:
    for key in ("recommended_contract", "contract_occ_symbol", "contract_symbol"):
        text = _str(row, key).upper()
        if text:
            if "P0" in text or text.endswith("P") or " PUT" in text:
                return "PUT"
            if "C0" in text or text.endswith("C") or " CALL" in text:
                return "CALL"
    delta = _flt(row, "contract_delta")
    if delta < 0:
        return "PUT"
    if delta > 0:
        return "CALL"
    return ""

def _direction_evidence(row: dict) -> dict:
    """
    Resolve the best trade expression without treating the first selected side
    as gospel. This is conservative: it only reroutes when the current side is
    empty/strangle or when evidence materially contradicts a bad expression.
    """
    primary = _candidate_direction(row)
    footprint = _footprint_direction(row)
    call_score = 0.0
    put_score = 0.0
    reasons: list[str] = []

    def add(side: str, points: float, reason: str) -> None:
        nonlocal call_score, put_score
        if side == "CALL":
            call_score += points
            reasons.append(f"CALL:{reason}+{points:g}")
        elif side == "PUT":
            put_score += points
            reasons.append(f"PUT:{reason}+{points:g}")

    if footprint:
        add(footprint, 4.0, "footprint_anchor")

    opt_dir = _str(row, "options_direction").upper()
    if opt_dir in {"CALL", "PUT"}:
        add(opt_dir, 2.0, "options_direction")
    elif opt_dir == "STRANGLE":
        reasons.append("NEUTRAL:options_direction=STRANGLE")

    for key, points in (
        ("vanguard_edge_direction", 2.0),
        ("layer2__edge_direction", 2.0),
        ("catalyst_direction_bias", 2.5),
        ("iv_direction", 0.5),
    ):
        side = _side_from_text(_str(row, key))
        if side:
            add(side, points, key)

    force = _flt(row, "directional_force")
    if force >= 5:
        add("CALL", 1.5, "directional_force")
    elif force <= -5:
        add("PUT", 1.5, "directional_force")

    signal = _flt(row, "signal_price") or _first_flt(row, "underlying_price", "current_price", "spot_price")
    target = _flt(row, "target_price") or _first_flt(row, "structural_target", "target")
    if signal and target:
        if target > signal * 1.003:
            add("CALL", 1.5, "target_above_signal")
        elif target < signal * 0.997:
            add("PUT", 1.5, "target_below_signal")

    raw = " ".join(
        _str(row, key).upper()
        for key in ("intent", "precor_intent", "wyckoff_phase_bucket", "dominant_trend", "control_state")
    )
    if any(token in raw for token in ("BUY_SETUP", "ACCUMULATION", "MARKUP", "BULL")):
        add("CALL", 1.0, "structure")
    if any(token in raw for token in ("SELL_SETUP", "DISTRIBUTION", "MARKDOWN", "BEAR")):
        add("PUT", 1.0, "structure")

    contract_side = _contract_side(row)
    if contract_side:
        add(contract_side, 0.25 if footprint and contract_side != footprint else 0.5, "selected_contract_side")

    chosen = primary
    margin = abs(call_score - put_score)
    voted = "CALL" if call_score > put_score else "PUT" if put_score > call_score else ""
    rr_options = _flt(row, "rr_options") or _flt(row, "rr_premium_expected")
    gain_at_target = _flt(row, "option_gain_at_target")
    expression_poor = rr_options <= 0 or gain_at_target < 0
    catalyst_side = _side_from_text(_str(row, "catalyst_direction_bias"))

    reroute = "NONE"
    if not chosen and voted:
        chosen = voted
        reroute = "SELECTED_FROM_EVIDENCE"
    elif opt_dir == "STRANGLE" and voted and margin >= 1.5:
        chosen = voted
        reroute = "STRANGLE_TO_DIRECTIONAL"
    elif catalyst_side and catalyst_side != chosen and margin >= 1.0:
        if _major_catalyst_can_break_footprint(row, catalyst_side, footprint):
            chosen = catalyst_side
            reroute = "MAJOR_CATALYST_DIRECTION_OVERRIDE"
        else:
            reroute = "CATALYST_CONFLICT_FOOTPRINT_LOCKED"
    elif voted and chosen and voted != chosen and expression_poor and margin >= 2.0:
        if footprint and chosen == footprint:
            reroute = "FOOTPRINT_LOCKED_EXPRESSION_REPAIR"
        else:
            chosen = voted
            reroute = "PRIMARY_EXPRESSION_FAILED_REROUTED"

    if not chosen:
        chosen = contract_side or voted or ""

    return {
        "primary_direction": primary,
        "resolved_direction": chosen,
        "canonical_direction": chosen,
        "footprint_direction": footprint,
        "footprint_lock_status": "LOCKED_UNTIL_INVALIDATION_OR_MAJOR_CATALYST" if footprint else "UNLOCKED_NO_CLEAR_FOOTPRINT",
        "footprint_lock_reason": "Wyckoff/compression footprint anchors thesis during expected hold window" if footprint else "",
        "direction_reroute_status": reroute,
        "direction_decision_reason": "; ".join(reasons[:12]),
        "direction_call_score": round(call_score, 2),
        "direction_put_score": round(put_score, 2),
        "selected_contract_side": contract_side,
    }

def _spread_pct_from_row(row: dict) -> float:
    spread = _first_flt(row, "contract_spread_pct", "eil_spread_pct_live", default=0.0)
    if spread <= 0:
        return 0.0
    return spread * 100.0 if spread <= 1.0 else spread

def _contract_repair_profile(row: dict, direction_info: dict) -> dict:
    spread = _spread_pct_from_row(row)
    oi = _flt(row, "contract_oi")
    volume = _flt(row, "contract_volume")
    delta = abs(_flt(row, "contract_delta"))
    premium = _first_flt(row, "contract_premium", "premium", "premium_eod", default=0.0)
    rr_options = _flt(row, "rr_options") or _flt(row, "rr_premium_expected")
    gain_at_target = _flt(row, "option_gain_at_target")
    selected_side = direction_info.get("selected_contract_side", "")
    resolved_side = direction_info.get("resolved_direction", "")

    reasons: list[str] = []
    score = 0.0
    if premium > 0:
        score += 5
    else:
        reasons.append("NO_CONTRACT_SELECTED")
    if spread and spread <= 15:
        score += 10
    elif spread and spread <= 25:
        score += 6
        reasons.append("SPREAD_CAUTION")
    elif spread:
        reasons.append("SPREAD_REPAIR_NEEDED")
    else:
        reasons.append("SPREAD_UNKNOWN")
    if oi >= 500:
        score += 8
    elif oi >= 50:
        score += 4
        reasons.append("OI_CAUTION")
    else:
        reasons.append("OI_REPAIR_NEEDED")
    if volume >= 50:
        score += 5
    elif volume >= 10:
        score += 3
        reasons.append("VOLUME_CAUTION")
    else:
        reasons.append("VOLUME_CAUTION")
    if 0 < delta < 0.50:
        score += 7
    elif delta > 0:
        reasons.append("DELTA_REPAIR_NEEDED")
    else:
        reasons.append("DELTA_UNKNOWN")
    if rr_options >= 1.0 or gain_at_target > 0:
        score += 10
    else:
        reasons.append("BREAKEVEN_OR_RR_CAUTION")
    if selected_side and resolved_side and selected_side != resolved_side:
        reasons.append("SIDE_REPAIR_NEEDED")

    severe = any(
        code in reasons
        for code in (
            "NO_CONTRACT_SELECTED",
            "SPREAD_REPAIR_NEEDED",
            "OI_REPAIR_NEEDED",
            "DELTA_REPAIR_NEEDED",
            "DELTA_UNKNOWN",
            "SIDE_REPAIR_NEEDED",
        )
    )
    status = "CONTRACT_REPAIR_REQUIRED" if severe else "CONTRACT_CAUTION" if reasons else "CONTRACT_OK"
    return {
        "contract_quality_score": round(min(45.0, score), 2),
        "contract_repair_status": status,
        "contract_repair_required": severe,
        "contract_repair_reason": "; ".join(dict.fromkeys(reasons)),
        "contract_spread_pct_eod": round(spread, 4) if spread else 0.0,
    }

def _monetisation_fit(row: dict, tier: str, contract_profile: dict, direction_info: dict) -> dict:
    ois = min(20.0, _flt(row, "options_score") / 2.5)
    rr = min(20.0, max(0.0, (_flt(row, "rr_underlying") or _flt(row, "rr") or _flt(row, "rr_options")) * 8.0))
    trigger = 15.0 if _str(row, "trigger_quality").upper() == "STRONG" else 8.0 if _str(row, "trigger_quality").upper() == "SINGLE" else 0.0
    eil = 20.0 if _str(row, "eil_v3_verdict").upper() == "EXECUTE" else 12.0 if _str(row, "eil_v3_verdict").upper() == "EXECUTE_WITH_CAUTION" else 0.0
    catalyst = min(15.0, _flt(row, "catalyst_truth_score") / 3.0)
    contract = min(20.0, float(contract_profile.get("contract_quality_score", 0.0)) / 2.25)
    direction_margin = abs(float(direction_info.get("direction_call_score", 0.0)) - float(direction_info.get("direction_put_score", 0.0)))
    direction = min(10.0, direction_margin * 2.0)
    score = ois + rr + trigger + eil + catalyst + contract + direction
    if tier == "A":
        score += 5
    elif tier == "WATCH":
        score -= 10
    label = "ASYMMETRIC_EXECUTE" if score >= 72 else "ASYMMETRIC_REVIEW" if score >= 55 else "WATCH_ONLY"
    return {"monetisation_fit_score": round(max(0.0, min(100.0, score)), 2), "monetisation_fit_label": label}

def _exit_intelligence_plan(row: dict, direction: str, invalidation: Optional[float], wall_price: float, target_price: float) -> dict:
    direction_u = str(direction or "").upper()
    entry = _flt(row, "signal_price") or _flt(row, "underlying_price") or _flt(row, "current_price")
    target = target_price or _flt(row, "target_price")
    expected_move_pct = (
        _first_flt(row, "l3_expected_move_1_5d", "l3_expected_move_6_10d", "expected_move_pct", "expected_move")
        or 0.0
    )
    wbs_grade = _str(row, "wbs_grade").upper()
    if wbs_grade == "PROBABLE":
        mode = "RIDE_THROUGH_WALL"
        scale = "40/35/25"
    elif wbs_grade == "UNLIKELY":
        mode = "EXIT_BEFORE_WALL"
        scale = "50/35/15"
    else:
        mode = "SCALE_AT_WALL"
        scale = "60/25/15"

    if not target and entry:
        move = abs(expected_move_pct) / 100.0 if abs(expected_move_pct) > 1 else abs(expected_move_pct)
        target = entry * (1 + move) if direction_u == "CALL" else entry * (1 - move)
    if not wall_price:
        wall_price = target

    if direction_u == "CALL":
        t1 = wall_price or target
        t2 = target or wall_price
        t3 = max(x for x in [t1, t2, entry] if x) * 1.03 if any([t1, t2, entry]) else 0.0
    else:
        t1 = wall_price or target
        t2 = target or wall_price
        vals = [x for x in [t1, t2, entry] if x]
        t3 = min(vals) * 0.97 if vals else 0.0

    return {
        "exit_mode": mode,
        "exit_scale_plan": scale,
        "exit_t1": round(float(t1), 4) if t1 else 0.0,
        "exit_t2": round(float(t2), 4) if t2 else 0.0,
        "exit_t3": round(float(t3), 4) if t3 else 0.0,
        "exit_invalidation_price": round(float(invalidation), 4) if invalidation else 0.0,
        "exit_plan_reason": f"WBS={wbs_grade or 'NONE'}; GARCH/expected move={expected_move_pct}",
    }

def _eod_dropoff_reason(row: dict, tier: str, eod_status: str, contract_profile: dict) -> str:
    if eod_status in {"EOD_THESIS_READY", "EOD_TRIGGER_READY"}:
        return "PRESERVED_TO_MORNING_VALIDATION"
    if eod_status == "EOD_THESIS_READY_REPAIR_AT_OPEN":
        return str(contract_profile.get("contract_repair_reason") or "REPAIR_AT_OPEN")
    if eod_status in {"EOD_PROBE_CANDIDATE", "EOD_WATCHLIST_MONETISABLE", "EOD_DATA_INSUFFICIENT_REVIEW"}:
        return eod_status
    if eod_status in {"EOD_NO_OPTIONS_ROUTE", "EOD_STRUCTURAL_BLOCK"}:
        return eod_status
    if eod_status in {"EOD_EXECUTE_CANDIDATE", "EOD_CATALYST_EXECUTE_CANDIDATE"}:
        return "SURVIVED_TO_EOD_EXECUTE"
    options_block_reason = _options_research_block_reason(row)
    if options_block_reason:
        failure_class = _eod_failure_class(row, options_block_reason)
        return f"OPTIONS_{failure_class}:{options_block_reason}"
    if eod_status == "EOD_DIRECTION_CONFLICT_REVIEW":
        return _str(row, "direction_conflict_reason") or "DIRECTION_CONFLICT_UNRESOLVED"
    if eod_status == "EOD_CONTRACT_REPAIR_REQUIRED":
        return str(contract_profile.get("contract_repair_reason") or "CONTRACT_REPAIR_REQUIRED")
    if eod_status in {"EOD_EXECUTE_WITH_CAUTION", "EOD_TRIGGER_READY_REVIEW", "EOD_CONTRACT_REPAIR_REQUIRED"}:
        return eod_status
    if tier == "WATCH":
        gaps = []
        if _flt(row, "options_score") < MIN_OPTIONS_SCORE:
            gaps.append("OPTIONS_SCORE_BELOW_FLOOR")
        if (_flt(row, "rr_underlying") or _flt(row, "rr")) < MIN_RR:
            gaps.append("RR_BELOW_FLOOR")
        if _flt(row, "composite") < MIN_COMPOSITE:
            gaps.append("COMPOSITE_BELOW_FLOOR")
        return ";".join(gaps) or "QUALITY_FLOOR_NOT_MET"
    if contract_profile.get("contract_repair_required"):
        return str(contract_profile.get("contract_repair_reason") or "CONTRACT_REPAIR_REQUIRED")
    if _str(row, "eil_v3_verdict").upper() in {"BLOCKED", "WATCHLIST"}:
        return f"EIL_{_str(row, 'eil_v3_verdict').upper()}"
    if _str(row, "trigger_quality").upper() in {"", "NONE"}:
        return "NO_TRIGGER_CONFIRMATION"
    return "VALID_THESIS_NOT_TOP_SLATE"

def _shadow_opportunity_score(row: dict) -> tuple[float, str, str]:
    """
    Scores rows that did not make the primary slate, but could become expensive
    false negatives in an options book. This is not trade permission; it is the
    pipeline's memory for missed convexity and direction-flip opportunities.
    """
    score = 0.0
    reasons: list[str] = []

    ois = _flt(row, "options_score")
    if ois >= 45:
        score += 25
        reasons.append("HIGH_OPTIONS_SCORE")
    elif ois >= 35:
        score += 18
        reasons.append("GOOD_OPTIONS_SCORE")
    elif ois >= 25:
        score += 10
        reasons.append("OPTIONS_CONTEXT_PRESENT")

    rr = _flt(row, "rr")
    if rr >= 2.0:
        score += 20
        reasons.append("ASYMMETRIC_RR")
    elif rr >= 1.25:
        score += 12
        reasons.append("POSITIVE_RR")

    eil = _str(row, "eil_v3_verdict").upper()
    if eil == "EXECUTE":
        score += 22
        reasons.append("EIL_EXECUTE")
    elif eil == "EXECUTE_WITH_CAUTION":
        score += 14
        reasons.append("EIL_CAUTION")

    trigger = _str(row, "trigger_quality").upper()
    if trigger == "STRONG":
        score += 10
        reasons.append("STRONG_TRIGGER")
    elif trigger == "SINGLE":
        score += 5
        reasons.append("SINGLE_TRIGGER")

    catalyst_class = _str(row, "catalyst_trade_class").upper()
    catalyst_quality = _str(row, "catalyst_data_quality").upper()
    if catalyst_class == "DATED_CATALYST_CONFIRMED":
        score += 15
        reasons.append("DATED_CATALYST")
    elif catalyst_quality in {"CONFIRMED", "DATED_REVIEW", "INFERRED_GOOD"}:
        score += 8
        reasons.append("CATALYST_REVIEW")

    reroute = _str(row, "direction_reroute_status").upper()
    call_score = _flt(row, "direction_call_score")
    put_score = _flt(row, "direction_put_score")
    if reroute not in {"", "NONE"}:
        score += 12
        reasons.append(f"DIRECTION_{reroute}")
    if abs(call_score - put_score) >= 2.0:
        score += 6
        reasons.append("CLEAR_SIDE_EVIDENCE")

    if score >= 70:
        label = "HIGH_FALSE_NEGATIVE_RISK"
    elif score >= 55:
        label = "REVIEW_FALSE_NEGATIVE"
    elif score >= 40:
        label = "WATCH_FOR_REGIME_FLIP"
    else:
        label = "LOW_PRIORITY"
    return round(min(score, 100.0), 1), label, ";".join(reasons) or "NO_SHADOW_EDGE"

# ─── STRUCTURAL CONVICTION SCORE ─────────────────────────────────────────────
def _structural_conviction_score_legacy(row: dict) -> tuple[float, dict]:
    """
    Scores structural quality from EOD-only signals.
    Returns (score_0_to_100, breakdown_dict).

    No live data. No IV. No spread. Pure structure.
    """
    score = 0.0
    bd    = {}

    # ── 1. Options Intelligence (25pts) ──────────────────────────────────────
    ois = _flt(row, "options_score")
    if ois >= 35:
        pts = 25
    elif ois >= 25:
        pts = 18
    elif ois >= 15:
        pts = 10
    else:
        pts = 0
    score += pts
    bd["options_intelligence"] = f"{ois:.0f}/41 → {pts}pts"

    # ── 2. Risk/Reward Quality (20pts) ───────────────────────────────────────
    rr = _flt(row, "rr_underlying") or _flt(row, "rr")
    if rr >= 2.5:
        pts = 20
    elif rr >= 1.5:
        pts = 15
    elif rr >= 1.0:
        pts = 8
    elif rr > 0:
        pts = 3
    else:
        pts = 0
    score += pts
    bd["rr_quality"] = f"{rr:.2f}x → {pts}pts"

    # ── 3. Structural EV + Composite (20pts) ─────────────────────────────────
    ev_struct  = _flt(row, "ev2_ev_structural")
    composite  = _flt(row, "composite")
    ev_pts     = min(10, max(0, ev_struct * 80))   # 0.125 ev_struct → 10pts
    comp_pts   = 10 if composite >= 70 else (7 if composite >= 55 else (4 if composite >= 40 else 0))
    pts = round(ev_pts + comp_pts, 1)
    score += pts
    bd["structural_ev"] = f"ev_struct={ev_struct:.4f} composite={composite:.0f} → {pts}pts"

    # ── 4. Wall Break Score (15pts) ───────────────────────────────────────────
    wbs      = _flt(row, "wbs")
    wbs_g    = _str(row, "wbs_grade")
    if wbs_g == "PROBABLE":
        pts = 15
    elif wbs_g == "POSSIBLE":
        pts = 9
    elif wbs_g == "UNLIKELY":
        pts = 3
    else:
        pts = max(0, min(8, wbs / 8))   # no grade: raw score proportional
    score += pts
    bd["wbs"] = f"wbs={wbs:.1f} grade={wbs_g or 'NONE'} → {pts:.0f}pts"

    # ── 5. Campaign Quality (10pts) ───────────────────────────────────────────
    conv    = _flt(row, "sb_conv_score")
    campaign = _str(row, "sb_campaign")
    if campaign == "CORE_CAMPAIGN" and conv >= 4:
        pts = 10
    elif campaign == "CORE_CAMPAIGN" and conv >= 3:
        pts = 8
    elif campaign == "CORE_CAMPAIGN":
        pts = 5
    elif campaign == "STAGED" and conv >= 3:
        pts = 4
    else:
        pts = 2
    score += pts
    bd["campaign"] = f"{campaign or 'NONE'} conv={conv:.0f} → {pts}pts"

    # ── 6. Superbrain Veto Load (10pts — inverse: fewer vetoes = higher score) ─
    warnings = _flt(row, "sb_warnings_count")
    if warnings == 0:
        pts = 10
    elif warnings == 1:
        pts = 7
    elif warnings == 2:
        pts = 4
    elif warnings == 3:
        pts = 2
    else:
        pts = 0
    score += pts
    bd["veto_load"] = f"{warnings:.0f} vetoes → {pts}pts"

    # ── 7. Actuarial Signal Quality (0-10pts — Sprint 3 V2) ──────────────────
    # Additive component: rewards signals where actuarial Stage 0 classified
    # a genuine CONTINUATION or TRANSITION edge. Backward-compatible: 0pts
    # when V2 fields are absent (pre-Sprint 3 rows or NO_EDGE signals).
    # Does NOT change Tier A/B thresholds — purely additive to SCS.
    _sig_type = _resolved_signal_type(row)
    _mom_tier = _resolved_momentum_tier(row)
    if _sig_type == "CONTINUATION":
        if _mom_tier in ("TIER_1_EXPLOSIVE", "TIER_2_SUSTAINING"):
            pts = 10   # HIGH/EXTREME → EXTREME: maximum actuarial conviction
        elif _mom_tier == "TIER_3_BUILDING":
            pts = 7    # MID → HIGH/EXTREME: building
        else:
            pts = 5    # TIER_4_FLAT or unknown: flat continuation
    elif _sig_type == "TRANSITION":
        if _mom_tier == "TIER_1_ACCELERATING":
            pts = 4    # LOW → HIGH skip: higher-conviction probe
        else:
            pts = 3    # TIER_2_BUILDING: standard probe
    else:
        pts = 0        # NO_EDGE or absent: no actuarial boost
    score += pts
    bd["actuarial_signal"] = f"signal={_sig_type or 'N/A'} tier={_mom_tier or 'N/A'} → {pts}pts"

    return round(min(100, score), 1), bd

def structural_conviction_score(row: dict) -> tuple[float, dict]:
    """
    Scores EOD thesis quality. WBS and position sizing are advisory only;
    they do not add or remove conviction points.
    """
    score = 0.0
    bd = {}

    ois = _flt(row, "options_score")
    if ois >= 35:
        pts = 25
    elif ois >= 25:
        pts = 18
    elif ois >= 15:
        pts = 10
    else:
        pts = 0
    score += pts
    bd["options_intelligence"] = f"{ois:.0f}/41 -> {pts}pts"

    rr = _flt(row, "rr_underlying") or _flt(row, "rr")
    if rr >= 2.5:
        pts = 20
    elif rr >= 1.5:
        pts = 15
    elif rr >= 1.0:
        pts = 8
    elif rr > 0:
        pts = 3
    else:
        pts = 0
    score += pts
    bd["rr_quality"] = f"{rr:.2f}x -> {pts}pts"

    ev_struct = _flt(row, "ev2_ev_structural")
    composite = _flt(row, "composite")
    ev_pts = min(10, max(0, ev_struct * 80))
    comp_pts = 10 if composite >= 70 else (7 if composite >= 55 else (4 if composite >= 40 else 0))
    pts = round(ev_pts + comp_pts, 1)
    score += pts
    bd["structural_ev"] = f"ev_struct={ev_struct:.4f} composite={composite:.0f} -> {pts}pts"

    wbs = _flt(row, "wbs")
    wbs_g = _str(row, "wbs_grade")
    bd["wbs"] = f"wbs={wbs:.1f} grade={wbs_g or 'NONE'} -> advisory only"

    conv = _flt(row, "sb_conv_score")
    campaign = _str(row, "sb_campaign")
    if campaign == "CORE_CAMPAIGN" and conv >= 4:
        pts = 10
    elif campaign == "CORE_CAMPAIGN" and conv >= 3:
        pts = 8
    elif campaign == "CORE_CAMPAIGN":
        pts = 5
    elif campaign == "STAGED" and conv >= 3:
        pts = 4
    else:
        pts = 2
    score += pts
    bd["campaign"] = f"{campaign or 'NONE'} conv={conv:.0f} -> {pts}pts"

    warnings = _flt(row, "sb_warnings_count")
    if warnings == 0:
        pts = 10
    elif warnings == 1:
        pts = 7
    elif warnings == 2:
        pts = 4
    elif warnings == 3:
        pts = 2
    else:
        pts = 0
    score += pts
    bd["veto_load"] = f"{warnings:.0f} vetoes -> {pts}pts"

    sig_type = _resolved_signal_type(row)
    mom_tier = _resolved_momentum_tier(row)
    if sig_type == "CONTINUATION":
        if mom_tier in ("TIER_1_EXPLOSIVE", "TIER_2_SUSTAINING"):
            pts = 10
        elif mom_tier == "TIER_3_BUILDING":
            pts = 7
        else:
            pts = 5
    elif sig_type == "TRANSITION":
        pts = 4 if mom_tier == "TIER_1_ACCELERATING" else 3
    else:
        pts = 0
    score += pts
    bd["actuarial_signal"] = f"signal={sig_type or 'N/A'} tier={mom_tier or 'N/A'} -> {pts}pts"

    return round(min(100, score), 1), bd

# ─── TIER CLASSIFICATION ─────────────────────────────────────────────────────
def classify_tier(row: dict) -> str:
    ois     = _flt(row, "options_score")
    # EOD-01: use rr_underlying (structural price R:R, from FIX-01) — not rr_options
    rr      = _flt(row, "rr_underlying") or _flt(row, "rr")
    conv    = _flt(row, "sb_conv_score")
    comp    = _flt(row, "composite")
    eil_verdict = _str(row, "eil_v3_verdict").upper()
    trigger_quality = _str(row, "trigger_quality").upper()
    trigger_go = _str(row, "trigger_go_eligible").upper() in {"TRUE", "1", "YES"}
    catalyst_class = _str(row, "catalyst_trade_class").upper()
    catalyst_quality = _str(row, "catalyst_data_quality").upper()
    pse_mode = _str(row, "pse_execution_mode").upper()
    effective = _str(row, "effective_execution_verdict").upper()
    fd_verdict = _str(row, "fd_verdict").upper()

    options_block_reason = _options_research_block_reason(row)
    if options_block_reason and _eod_failure_class(row, options_block_reason) in {"NO_OPTIONS_ROUTE", "STRUCTURAL_BLOCK"}:
        return "WATCH"

    if _str(row, "direction_conflict_status").upper() == "UNRESOLVED":
        return "WATCH"

    # Quality floor check
    if ois < MIN_OPTIONS_SCORE or rr < MIN_RR or comp < MIN_COMPOSITE:
        return "WATCH"

    if _true_fatal_block(row):
        return "WATCH"

    execute_like = eil_verdict in {"EXECUTE", "EXECUTE_WITH_CAUTION"}
    trigger_ready = trigger_quality == "STRONG" or trigger_go
    trigger_present = trigger_ready or trigger_quality == "SINGLE"
    catalyst_ready = (
        catalyst_class == "DATED_CATALYST_CONFIRMED"
        or catalyst_quality in {"CONFIRMED", "DATED_REVIEW", "INFERRED_GOOD"}
    )
    campaign_ready = conv >= 2
    options_power = ois >= 45

    # Tier A: capital-grade EOD thesis, not live capital permission.
    # Requires tradability + R/R + one execution clue and one market-behaviour clue.
    if (
        ois >= TIER_A["options_score"]
        and rr >= TIER_A["rr"]
        and comp >= 55
        and (eil_verdict == "EXECUTE" or catalyst_ready)
        and (trigger_ready or campaign_ready or options_power)
    ):
        return "A"

    # Tier B: realistic morning-validation slate. Markets often give tradeable
    # follow-through without every model agreeing, so one strong evidence family
    # can qualify if liquidity/economics are present.
    if (
        ois >= TIER_B["options_score"]
        and rr >= TIER_B["rr"]
        and comp >= 50
        and (execute_like or trigger_present or catalyst_ready or campaign_ready or options_power)
    ):
        return "B"

    # Tier C: passes quality floor
    return "C"

# ─── MAIN TRANSFORMATION ─────────────────────────────────────────────────────
def build_candidate_manifest(
    eil_path: str | Path,
    wbs_path: Optional[str | Path] = None,
    discovery_path: Optional[str | Path] = None,
    vanguard_path: Optional[str | Path] = None,
    output_path: Optional[str | Path] = None,
    run_id: str = "manual",
    max_candidates: int = 0,
    horizon_summary: Optional[dict] = None,
    horizon_1_5d_path: Optional[str | Path] = None,
    horizon_6_10d_path: Optional[str | Path] = None,
) -> pd.DataFrame:
    """
    Build the morning candidate manifest from EOD pipeline outputs.

    Args:
        eil_path           Path to eil_enriched_{run_id}.csv
        wbs_path           Path to wall_break_scores_{run_id}.csv (optional)
        discovery_path     Path to discovery_candidates_ultimate_{run_id}.csv (optional)
        output_path        Where to write morning_candidates_{run_id}.csv
        run_id             Run identifier string
        max_candidates     Optional cap on total candidates written; 0 means no cap
        horizon_summary    Dict from horizon_summary_{run_id}.json (optional)
                           Contains horizon biases, counts, macro conviction.
        horizon_1_5d_path  Path to horizon_1_5d_{run_id}.csv (optional)
                           Used to tag candidates with horizon bucket and action.
        horizon_6_10d_path Path to horizon_6_10d_{run_id}.csv (optional)

    Returns:
        DataFrame of candidates

    v4.1: Horizon context is now stamped onto every candidate row so morning
    validation can apply DTE-appropriate gates and correctly classify 1-5D
    entries vs 6-10D continuations vs 11-20D monitor-only signals.
    """
    log.info(f"Loading EIL enriched data: {eil_path}")
    df = pd.read_csv(eil_path, low_memory=False)
    log.info(f"  {len(df)} rows loaded")

    rows = df.to_dict(orient="records")

    # ── v4.1: Build horizon lookup from Phase 1B router CSVs ─────────────────
    # Maps ticker → {horizon_bucket, horizon_action, horizon_size_multiplier}
    # Supplemented by horizon_bucket already in the EIL enriched CSV (written
    # by EIL runner v4.1 horizon passthrough). Horizon CSV is the authoritative
    # source; EIL CSV is the fallback for any ticker not in the horizon files.
    _horizon_map: dict[str, dict] = {}

    def _load_horizon_csv(path) -> None:
        if path and Path(path).exists():
            try:
                _hdf = pd.read_csv(path, low_memory=False)
                for _, _hr in _hdf.iterrows():
                    _t = str(_hr.get("ticker","")).strip().upper()
                    if _t:
                        _horizon_map[_t] = {
                            "horizon_bucket":           str(_hr.get("horizon_bucket","")).strip(),
                            "horizon_action":           str(_hr.get("horizon_action","")).strip(),
                            "horizon_size_multiplier":  float(_hr.get("horizon_size_multiplier") or 1.0),
                        }
                log.info(f"  Horizon CSV loaded: {len(_hdf)} rows from {Path(path).name}")
            except Exception as _he:
                log.warning(f"  Horizon CSV load failed ({path}): {_he}")

    _load_horizon_csv(horizon_1_5d_path)
    _load_horizon_csv(horizon_6_10d_path)

    # Log macro horizon context if summary provided
    if horizon_summary:
        _hc = horizon_summary.get("horizon_counts", {})
        _hb = horizon_summary.get("horizon_biases", {})
        log.info(
            "  Horizon summary: 1-5D=%d | 6-10D=%d | 11-20D=%d | blocked=%d | "
            "conviction=%.2f | momentum=%.2f",
            _hc.get("1_5d",0), _hc.get("6_10d",0),
            _hc.get("11_20d",0), _hc.get("blocked",0),
            horizon_summary.get("macro_conviction",0),
            horizon_summary.get("macro_momentum_score",0),
        )
    # ── End horizon lookup build ──────────────────────────────────────────────

    # ── Merge WBS ─────────────────────────────────────────────────────────────
    wbs_map: dict[str, dict] = {}
    if wbs_path and Path(wbs_path).exists():
        wbs_df = pd.read_csv(wbs_path, low_memory=False)
        for _, r in wbs_df.iterrows():
            t = str(r.get("ticker", "")).strip().upper()
            if t:
                wbs_map[t] = r.to_dict()
        log.info(f"WBS data merged: {len(wbs_map)} tickers")
    else:
        log.warning("WBS data not found — wbs/wbs_grade will be absent from candidates")

    WBS_MERGE_COLS = [
        "wbs", "wbs_grade", "wbs_wall_price", "wbs_wall_dist_pct",
        "wbs_phase_b_trigger", "wbs_phase_c_trigger", "wbs_rejection_stop",
        "wbs_notes", "runway_to_wall_pct", "pin_risk_score",
        "wbs_size_guidance", "wbs_entry_guidance", "wbs_stop_guidance",
        "wbs_wall_stall_rule",
    ]

    # ── Merge Discovery ───────────────────────────────────────────────────────
    disc_map: dict[str, dict] = {}
    if discovery_path and Path(discovery_path).exists():
        disc_df = pd.read_csv(discovery_path, low_memory=False)
        for _, r in disc_df.iterrows():
            t = str(r.get("ticker", "")).strip().upper()
            if t:
                disc_map[t] = r.to_dict()
        log.info(f"Discovery data merged: {len(disc_map)} tickers")

    DISC_MERGE_COLS = [
        "stop_loss", "entry_price", "VWAP", "vwap_bias",
        "crabel_compression", "crabel_pattern", "crabel_state",
        "phase_evidence_strength", "dominant_event", "ATR_14",
        "wyckoff_phase_bucket", "dominant_trend", "ema_stack",
        "adx_14", "atr_percentile_rank",
    ]

    # ── Merge Vanguard (EOD-02) ───────────────────────────────────────────────
    # rr_underlying, rr_confidence, rr_source are written by vanguard but not
    # propagated into eil_enriched by the EIL runner. Without this merge, all
    # candidates show RR=0.00 in the manifest and Tier A/B gates never fire.
    van_map: dict[str, dict] = {}
    VAN_MERGE_COLS = [
        "rr_underlying", "rr_confidence", "rr_source", "rr", "rr_flag",
        "rr_options", "atr_pct", "vol_regime", "structure_quality",
        "macro_regime", "layer2__vol_regime", "layer2__structure_quality",
        "layer2__trend_maturity",
        *MACRO_QUANT_CSV_FIELDS,
        # V2 Signal Intelligence (Sprint 3) — fallback source if eil_enriched
        # inject_actuarial did not populate these. Primary source is eil_enriched.
        "layer2__signal_type", "layer2__momentum_tier",
        "layer2__forward_momentum_confidence",
        "layer2__phase_v2", "layer2__momentum_bucket",
        *PHASE2_LAYER2_FIELDS,
        *PHYSICS_FIELDS,
        *CATALYST_TRUTH_FIELDS,
        # Flat and actuarial_ prefixed versions (from inject_actuarial pass)
        "signal_type", "momentum_tier", "phase_v2",
        "momentum_bucket", "location_bucket",
        "pse_signal_type", "pse_momentum_tier",
        "actuarial_signal_type", "actuarial_momentum_tier",
        "actuarial_forward_momentum_conf",
    ]
    _van_candidates = []
    if vanguard_path and Path(vanguard_path).exists():
        _van_candidates = [vanguard_path]
    else:
        # Auto-discover vanguard_signals_enriched in options/ or vanguard/ folder
        if eil_path:
            _run_dir = Path(eil_path).parent.parent
            _van_candidates = [
                _run_dir / "options"  / f"vanguard_signals_enriched_{run_id}.csv",
                _run_dir / "vanguard" / f"vanguard_signals_enriched_{run_id}.csv",
                _run_dir / "vanguard" / "vanguard_signals.csv",
            ]
    for _vp in _van_candidates:
        if Path(_vp).exists():
            try:
                _vdf = pd.read_csv(_vp, low_memory=False)
                for _, _vr in _vdf.iterrows():
                    _vt = str(_vr.get("ticker", "")).strip().upper()
                    if _vt:
                        van_map[_vt] = _vr.to_dict()
                log.info(f"Vanguard data merged: {len(van_map)} tickers from {Path(_vp).name}")
                break
            except Exception as _ve:
                log.warning(f"Vanguard CSV load failed ({_vp}): {_ve}")
    if not van_map:
        log.warning("Vanguard data not found — rr_underlying will be 0.00 in manifest")

    # ── Process each row ──────────────────────────────────────────────────────
    candidates = []

    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()

        # Merge WBS fields
        if ticker in wbs_map:
            for col in WBS_MERGE_COLS:
                if col in wbs_map[ticker] and row.get(col) in (None, "", "nan", float("nan")):
                    row[col] = wbs_map[ticker][col]

        # Merge discovery fields
        if ticker in disc_map:
            for col in DISC_MERGE_COLS:
                if col in disc_map[ticker] and row.get(col) in (None, "", "nan", float("nan")):
                    row[col] = disc_map[ticker][col]

        # Merge vanguard fields (EOD-02: rr_underlying and related RR fields)
        if ticker in van_map:
            for col in VAN_MERGE_COLS:
                if col in van_map[ticker] and row.get(col) in (None, "", "nan", float("nan"), 0.0, 0):
                    row[col] = van_map[ticker][col]

        row = _normalise_current_contract(row)

        # Resolve the trade expression before tiering. A failed/ambiguous CALL
        # should be allowed to become a PUT thesis when the evidence says so,
        # and vice versa; only the live/morning step can approve capital.
        direction_info = _direction_evidence(row)
        direction = str(direction_info.get("resolved_direction") or "")
        if direction:
            row["direction"] = direction
        contract_profile = _contract_repair_profile(row, direction_info)
        for _k, _v in {**direction_info, **contract_profile}.items():
            row[_k] = _v
        row = _normalise_audit_handoff_fields(row)

        # Classify tier
        tier = classify_tier(row)

        # Structural conviction score
        scs, scs_bd = structural_conviction_score(row)

        # Derived fields
        dte            = _flt(row, "dte", 30)
        move_window    = _expected_move_window(dte)
        setup_type     = _setup_type(row)
        invalidation   = _invalidation_level(row)
        wall_price     = _flt(row, "wbs_wall_price") or _flt(row, "put_wall") or _flt(row, "call_wall")
        wall_dist      = _flt(row, "wbs_wall_dist_pct") or _flt(row, "runway_to_wall_pct")
        exit_plan      = _exit_intelligence_plan(row, direction, invalidation, wall_price, _flt(row, "target_price"))
        eod_status, eod_reason = _eod_candidate_status(row, tier)
        # FIX 1: detect direction-conflict rows that were promoted to EOD_TRIGGER_READY
        _direction_conflict_flag = (
            eod_status == "EOD_TRIGGER_READY"
            and "DIRECTION_CONFLICT" in (eod_reason or "").upper()
        )
        monetisation = _monetisation_fit(row, tier, contract_profile, direction_info)
        eod_dropoff_reason = _eod_dropoff_reason(row, tier, eod_status, contract_profile)
        permission_fields = _candidate_permission_fields(row, eod_status)
        eod_failure_class = _eod_failure_class(row, eod_reason)
        thesis_state = _thesis_state_from_eod_status(eod_status)
        morning_tasks = _morning_tasks_for_status(row, eod_status, eod_reason)

        # ── v4.1: Resolve horizon context ────────────────────────────────────
        # Priority: Phase 1B horizon CSV > EIL enriched row column > default
        _hctx = _horizon_map.get(ticker, {})
        _cand_hb  = _hctx.get("horizon_bucket") or str(row.get("horizon_bucket","")).strip() or "unrouted"
        _cand_ha  = _hctx.get("horizon_action") or str(row.get("horizon_action","")).strip() or "UNKNOWN"
        _cand_hsm = float(_hctx.get("horizon_size_multiplier") or
                          row.get("horizon_size_multiplier") or
                          1.0)
        move_window = _horizon_trade_window(_cand_hb, move_window)
        # ── End horizon context resolution ───────────────────────────────────

        candidate = {
            # ── Identity ──────────────────────────────────────────────────────
            "run_id":               run_id,
            "ticker":               ticker,
            "direction":            direction,
            "canonical_direction":  direction,
            "resolved_direction":   direction_info.get("resolved_direction", direction),
            "footprint_direction":  direction_info.get("footprint_direction", ""),
            "footprint_lock_status": direction_info.get("footprint_lock_status", ""),
            "footprint_lock_reason": direction_info.get("footprint_lock_reason", ""),
            "options_direction":     _str(row, "options_direction"),
            "signal_price":         _flt(row, "signal_price"),
            "target_price":         _flt(row, "target_price"),
            "sector":               _str(row, "sector"),
            "sector_etf":           _str(row, "sector_etf"),
            "behaviour_state_key":   _str(row, "behaviour_state_key"),
            "behaviour_state_hash":  _str(row, "behaviour_state_hash"),
            "actuarial_match_type":  _str(row, "actuarial_match_type"),
            "actuarial_ev_weight":   _first_flt(row, "actuarial_ev_weight"),
            "catalyst_overlay":      _str(row, "catalyst_overlay"),
            # FIX 7: CATALYST_FIELDS carry-forward — must propagate through every stage
            "catalyst_truth_score":  _str(row, "catalyst_truth_score"),
            "event_convexity_score": _str(row, "event_convexity_score"),
            "catalyst_trade_class":  _str(row, "catalyst_trade_class"),
            "catalyst_date":         _str(row, "catalyst_date"),
            "catalyst_type":         _str(row, "catalyst_type"),
            "cheap_convexity":       _str(row, "cheap_convexity"),
            "catalyst_reason_codes": _str(row, "catalyst_reason_codes"),

            # ── EOD Classification ────────────────────────────────────────────
            "structural_tier":      tier,
            "scs_score":            scs,
            "scs_breakdown":        str(scs_bd),
            "setup_type":           setup_type,
            "expected_move_window": move_window,
            "invalidation_level":   invalidation,
            "candidate_status":     _candidate_status_for_handoff(eod_status),
            "eod_handoff_lane":     _handoff_lane(eod_status),
            "eod_candidate_status": eod_status,
            "eod_candidate_reason": eod_reason,
            "eod_status":           eod_status,
            "eod_failure_class":    eod_failure_class,
            "thesis_state":         thesis_state,
            "thesis_summary":       f"{direction or 'UNKNOWN'} {setup_type} | {move_window} | {eod_status}: {eod_reason}",
            "expected_holding_window": move_window,
            "expected_move":        _first_flt(row, "expected_move_pct", "expected_move", "l3_expected_move_6_10d", "l3_expected_move_1_5d"),
            "target_zone":          _str(row, "target_zone") or _str(row, "target_price") or _str(row, "wbs_wall_price"),
            "exit_mode":            exit_plan["exit_mode"],
            "exit_scale_plan":      exit_plan["exit_scale_plan"],
            "exit_t1":              exit_plan["exit_t1"],
            "exit_t2":              exit_plan["exit_t2"],
            "exit_t3":              exit_plan["exit_t3"],
            "exit_invalidation_price": exit_plan["exit_invalidation_price"],
            "exit_plan_reason":     exit_plan["exit_plan_reason"],
            "runway_to_target":     _flt(row, "runway_to_target_pct") or (
                ((_flt(row, "target_price") - _flt(row, "signal_price")) / _flt(row, "signal_price") * 100.0)
                if _flt(row, "signal_price") and _flt(row, "target_price") else 0.0
            ),
            "runway_to_wall":       wall_dist,
            "preferred_contract":   (_str(row, "recommended_contract") or _str(row, "contract_occ_symbol") or _str(row, "contract_symbol")),
            "alternative_contract_1": _first_str(row, "alternative_contract_1", "alt_contract_1"),
            "alternative_contract_2": _first_str(row, "alternative_contract_2", "alt_contract_2"),
            "alternative_contract_3": _first_str(row, "alternative_contract_3", "alt_contract_3"),
            "contract_expression_score": contract_profile["contract_quality_score"],
            "contract_repair_required_at_open": str(eod_status == "EOD_THESIS_READY_REPAIR_AT_OPEN" or bool(contract_profile["contract_repair_required"])).upper(),
            "morning_validation_tasks": morning_tasks,
            "live_validation_required": str(eod_status in EOD_CARRY_FORWARD_STATUSES).upper(),
            "confidence_score":     monetisation["monetisation_fit_score"],
            "data_quality_flags":   "; ".join(
                x for x in [
                    _first_str(row, "missing_data", "options_missing_data"),
                    _str(row, "pcr_vol_status"),
                    _str(row, "contract_repair_reason"),
                ] if x
            ),
            "notes":                eod_reason,
            # FIX 1: direction-conflict flag — trader must verify at open
            "direction_conflict_flag": _direction_conflict_flag,
            "direction_conflict_note": (
                f"Direction conflict detected: {eod_reason}. Trader to verify at open."
                if _direction_conflict_flag else ""
            ),
            "eod_live_capital_permission": permission_fields["eod_live_capital_permission"],
            "live_capital_permission": permission_fields["live_capital_permission"],
            "eod_candidate_permission": permission_fields["eod_candidate_permission"],
            "candidate_size": permission_fields["candidate_size"],
            "sizing_policy": permission_fields["sizing_policy"],
            "candidate_size_status": permission_fields["candidate_size_status"],
            "candidate_size_source": permission_fields["candidate_size_source"],
            "manual_sizing_required": permission_fields["manual_sizing_required"],
            "effective_execution_verdict": _str(row, "effective_execution_verdict"),
            "fd_verdict": _str(row, "fd_verdict") or _str(row, "eil_v3_verdict"),
            "fd_advisory_verdict": (
                _str(row, "fd_advisory_verdict")
                or _str(row, "fd_verdict")
                or _str(row, "eil_v3_verdict")
            ),
            "final_decision_advisory_verdict": (
                _str(row, "final_decision_advisory_verdict")
                or _str(row, "fd_advisory_verdict")
                or _str(row, "fd_verdict")
                or _str(row, "eil_v3_verdict")
            ),
            "eil_signal_verdict": _str(row, "eil_signal_verdict") or _str(row, "eil_v3_verdict"),
            "capital_authorization_state": _str(row, "capital_authorization_state"),
            "execution_authority_reason": _str(row, "execution_authority_reason"),
            "signal_authority_reason": _str(row, "signal_authority_reason"),
            "direction_arbitration_status": _str(row, "direction_arbitration_status"),
            "direction_arbitration_reason": _str(row, "direction_arbitration_reason"),
            "direction_conflict_gate": _str(row, "direction_conflict_gate"),
            "catalyst_direction_conflict_status": _str(row, "catalyst_direction_conflict_status"),
            "catalyst_direction_conflict_reason": _str(row, "catalyst_direction_conflict_reason"),
            "pcr_direction_conflict_status": _str(row, "pcr_direction_conflict_status"),
            "pcr_direction_conflict_reason": _str(row, "pcr_direction_conflict_reason"),
            "direction_conflict_status": _str(row, "direction_conflict_status"),
            "direction_conflict_reason": _str(row, "direction_conflict_reason"),
            "pcr_vol_status": _str(row, "pcr_vol_status"),
            "pcr_vol_missing_reason": _str(row, "pcr_vol_missing_reason"),
            "options_research_permission": _first_str(row, "options_research_permission", "execution_permission"),
            "final_route": _first_str(row, "final_route", "options_research_route", "options_final_route"),
            "options_research_route": _first_str(row, "options_research_route", "final_route", "options_final_route"),
            "options_research_score": _flt(row, "options_research_score"),
            "options_research_confidence": _flt(row, "confidence_score"),
            "hard_vetoes": _first_str(row, "hard_vetoes", "options_hard_vetoes"),
            "options_hard_vetoes": _first_str(row, "options_hard_vetoes", "hard_vetoes"),
            "missing_data": _first_str(row, "missing_data", "options_missing_data"),
            "options_missing_data": _first_str(row, "options_missing_data", "missing_data"),
            "research_route_reason": _str(row, "research_route_reason"),
            "breakeven_feasibility": _flt(row, "breakeven_feasibility"),
            "estimated_R": _flt(row, "estimated_R"),
            "theta_decay_expected": _flt(row, "theta_decay_expected"),
            "runway_to_wall_pct": _flt(row, "runway_to_wall_pct"),
            "l3_jump_risk_flag": _str(row, "l3_jump_risk_flag") or _str(row, "jump_risk_flag"),
            "jump_risk_review_required": "TRUE"
            if (_str(row, "l3_jump_risk_flag").upper() in {"TRUE", "1", "YES"}
                or _str(row, "jump_risk_flag").upper() in {"TRUE", "1", "YES"})
            else "FALSE",
            "jump_risk_note": "GARCH_JUMP_RISK_REVIEW"
            if (_str(row, "l3_jump_risk_flag").upper() in {"TRUE", "1", "YES"}
                or _str(row, "jump_risk_flag").upper() in {"TRUE", "1", "YES"})
            else "",
            "iv_gex_entry_quality": _flt(row, "iv_gex_entry_quality"),
            "iv_gex_entry_quality_label": _str(row, "iv_gex_entry_quality_label"),
            "iv_gex_entry_quality_narrative": _str(row, "iv_gex_entry_quality_narrative"),
            "gamma_island_on_path": _str(row, "gamma_island_on_path"),
            "gamma_island_label": _str(row, "gamma_island_label"),
            "gamma_island_level": _flt(row, "gamma_island_level"),
            "gamma_island_distance_pct": _flt(row, "gamma_island_distance_pct"),
            "gamma_island_source": _str(row, "gamma_island_source"),
            "gamma_island_note": _str(row, "gamma_island_note"),
            "move_theta_ratio": _flt(row, "move_theta_ratio"),
            "move_theta_margin_label": _str(row, "move_theta_margin_label"),
            "move_theta_narrative": _str(row, "move_theta_narrative"),
            "crowd_arrival_state": _str(row, "crowd_arrival_state"),
            "crowd_arrival_score": _flt(row, "crowd_arrival_score"),
            "crowd_arrival_components": _str(row, "crowd_arrival_components"),
            "crowd_arrival_narrative": _str(row, "crowd_arrival_narrative"),
            "eod_dropoff_reason": eod_dropoff_reason,
            "monetisation_fit_score": monetisation["monetisation_fit_score"],
            "monetisation_fit_label": monetisation["monetisation_fit_label"],
            "primary_direction": direction,
            "raw_primary_direction": direction_info["primary_direction"],
            "direction_reroute_status": direction_info["direction_reroute_status"],
            "direction_decision_reason": direction_info["direction_decision_reason"],
            "direction_call_score": direction_info["direction_call_score"],
            "direction_put_score": direction_info["direction_put_score"],

            # ── Contract ──────────────────────────────────────────────────────
            "strike":               _flt(row, "strike"),
            "expiry":               _str(row, "expiry"),
            "dte":                  dte,
            "premium_eod":          _flt(row, "premium"),
            "instrument":           (_str(row, "sb_instrument_now") or
                                     _str(row, "options_strategy")),
            "contract_symbol":      (_str(row, "recommended_contract") or
                                     _str(row, "contract_occ_symbol") or
                                     _str(row, "contract_symbol")),
            "recommended_contract": (_str(row, "recommended_contract") or
                                     _str(row, "contract_occ_symbol")),
            "options_strategy":     _str(row, "options_strategy"),
            "selected_contract_side": direction_info["selected_contract_side"],
            "contract_quality_score": contract_profile["contract_quality_score"],
            "contract_repair_status": contract_profile["contract_repair_status"],
            "contract_repair_required": str(contract_profile["contract_repair_required"]).upper(),
            "contract_repair_reason": contract_profile["contract_repair_reason"],
            "contract_spread_pct_eod": contract_profile["contract_spread_pct_eod"],
            "contract_oi":           _flt(row, "contract_oi"),
            "contract_volume":       _flt(row, "contract_volume"),
            "contract_delta":        _flt(row, "contract_delta"),
            "contract_gamma":        _flt(row, "contract_gamma"),
            "contract_theta":        _flt(row, "contract_theta"),
            "contract_iv":           _flt(row, "contract_iv"),
            "contract_bid":          _flt(row, "contract_bid"),
            "contract_ask":          _flt(row, "contract_ask"),
            "contract_mid":          _flt(row, "contract_mid"),
            "contract_spread_pct":   _flt(row, "contract_spread_pct"),

            # ── Structural Metrics ────────────────────────────────────────────
            "options_score":        _flt(row, "options_score"),
            # EOD-01 (FIX-02): rr reads rr_underlying first (structural price R:R from FIX-01),
            # falls back to rr for backward compatibility with rows pre-dating FIX-01.
            "rr":                   _flt(row, "rr_underlying") or _flt(row, "rr"),
            "rr_underlying":        _flt(row, "rr_underlying"),
            "rr_flag":              _str(row, "rr_flag") or "RR_OK",
            "rr_confidence":        _str(row, "rr_confidence"),
            # Options-specific R:R fields (written by OI after OI-01 fix)
            "rr_premium_expected":  _flt(row, "rr_premium_expected"),
            "max_convex_r_multiple":_flt(row, "max_convex_r_multiple"),
            "composite":            _flt(row, "composite"),
            "ev_structural":        _flt(row, "ev2_ev_structural"),
            "ev_conf_adj":          _flt(row, "ev2_ev_conf_adj"),
            "ev_status":            _str(row, "ev2_ev_status"),
            "phase":                _str(row, "phase"),
            "intent":               _str(row, "intent"),

            # ── V2 Actuarial Signal Intelligence (Sprint 3) ───────────────────
            # Passed through to morning_candidates CSV for operator context.
            # morning_validation_engine.py and Intelligence Lab can display these
            # so operators know the actuarial classification at decision time.
            "signal_type":          _resolved_signal_type(row),
            "momentum_tier":        _resolved_momentum_tier(row),
            "pse_signal_type":      _str(row, "pse_signal_type"),
            "pse_momentum_tier":    _str(row, "pse_momentum_tier"),
            "phase_v2":             _str(row, "phase_v2"),
            "momentum_bucket":      _str(row, "momentum_bucket"),
            "location_bucket":      _str(row, "location_bucket"),
            "fwd_momentum_conf":    _flt(row, "actuarial_forward_momentum_conf"),

            # ── Wall Break ────────────────────────────────────────────────────
            "wbs_score":            _flt(row, "wbs"),
            "wbs_grade":            _str(row, "wbs_grade"),
            "wall_price":           wall_price,
            "wall_dist_pct":        wall_dist,
            "wbs_stop_guidance":    _str(row, "wbs_stop_guidance"),
            "wbs_entry_guidance":   _str(row, "wbs_entry_guidance"),

            # ── Campaign / Superbrain ─────────────────────────────────────────
            "sb_campaign":          _str(row, "sb_campaign"),
            "sb_conv_score":        _flt(row, "sb_conv_score"),
            "convexity_campaign":   _str(row, "convexity_campaign"),
            "convexity_score":      _flt(row, "convexity_score"),
            "sb_position_size_pct": _flt(row, "sb_position_size_pct"),
            "sb_time_stop_date":    _str(row, "sb_time_stop_date"),
            "sb_checkpoint_date":   _str(row, "sb_checkpoint_date"),
            "sb_checkpoint_rule":   _str(row, "sb_checkpoint_rule"),
            "sb_ladder_summary":    _str(row, "sb_ladder_summary"),
            "sb_warnings_count":    _flt(row, "sb_warnings_count"),
            "sb_veto_codes":        _str(row, "sb_veto_codes"),

            # ── EIL Scores (carry-forward, advisory in morning) ───────────────
            "eil_gex_score":        _flt(row, "eil_gex_score"),
            "eil_iv_score":         _flt(row, "eil_iv_score"),
            "eil_obi_score":        _flt(row, "eil_obi_score"),
            "eil_poc_score":        _flt(row, "eil_poc_score"),
            "eil_composite_eod":    _flt(row, "eil_composite_score"),
            "eil_v3_verdict":       _str(row, "eil_v3_verdict"),
            "pse_execution_mode":   _str(row, "pse_execution_mode"),
            "pse_block_reason":     _str(row, "pse_block_reason"),
            "pse_score":            _flt(row, "pse_score"),
            "pse_edge_score":       _flt(row, "pse_edge_score"),
            "trigger_primary":      _str(row, "trigger_primary"),
            "trigger_quality":      _str(row, "trigger_quality"),
            "trigger_count":        _flt(row, "trigger_count"),
            "trigger_score":        _flt(row, "trigger_score"),
            "trigger_go_eligible":  _str(row, "trigger_go_eligible"),
            "trigger_codes":        _str(row, "trigger_codes"),
            "thesis_decision":      _str(row, "thesis_decision") or _str(row, "fd_verdict"),
            "execution_mode":       _str(row, "execution_mode"),

            # ── Actuarial / Vol ───────────────────────────────────────────────
            "win_rate_5d":          _flt(row, "win_rate_5d"),
            "win_rate_10d":         _flt(row, "win_rate_10d"),
            "expected_move_5d":     _flt(row, "l3_expected_move_1_5d"),
            "expected_move_10d":    _flt(row, "l3_expected_move_6_10d"),
            "vol_forecast":         _flt(row, "l3_forward_realised_vol"),
            "vol_conf":             _flt(row, "l3_vol_forecast_conf"),

            # ── Discovery carry-forwards ──────────────────────────────────────
            "invalidation_eod":     invalidation,
            "vwap_eod":             _flt(row, "VWAP"),
            "vwap_bias_eod":        _str(row, "vwap_bias"),
            "atr_14":               _flt(row, "ATR_14"),
            "crabel_compression":   _flt(row, "crabel_compression"),
            "crabel_pattern":       _str(row, "crabel_pattern"),

            # ── Horizon context (v4.1) ────────────────────────────────────────
            # Stamped here as thesis timing. Morning validation checks whether
            # the thesis remains valid; it must not kill 11-20D purely because
            # the expected payoff window is later.
            "horizon_bucket":       _cand_hb,
            "horizon_action":       _cand_ha,
            "horizon_size_multiplier": _cand_hsm,

            # ── V2 Signal Intelligence (Sprint 3) ─────────────────────────────
            # Carried from pse_* fields in eil_enriched.csv.
            # morning_validation_engine uses these for:
            #   - Operator display (signal classification visible at open)
            #   - CONTINUATION → wider entry window / full PSE size
            #   - TRANSITION   → probe-only flag / reduced live size
            #   - pse_ev_mult  → shows how strongly the edge scored
            "signal_type":          _resolved_signal_type(row),
            "momentum_tier":        _resolved_momentum_tier(row),
            "pse_ev_mult":          _flt(row, "pse_ev_mult"),
            "pse_final_size":       _flt(row, "pse_final_size"),
            "forward_momentum_conf":_flt(row, "actuarial_forward_momentum_conf"),
        }
        for phase2_col in PHASE2_LAYER2_FIELDS:
            candidate[phase2_col] = row.get(phase2_col, "")
        for scanner_col in SCANNER_FIELD_NAMES:
            candidate[scanner_col] = row.get(scanner_col, "")
        for physics_col in PHYSICS_FIELDS:
            candidate[physics_col] = row.get(physics_col, "")
        for macro_col in MACRO_QUANT_CSV_FIELDS:
            candidate[macro_col] = row.get(macro_col, "")
        for catalyst_col in CATALYST_TRUTH_FIELDS:
            candidate[catalyst_col] = row.get(catalyst_col, "")
        candidates.append(candidate)

    out_df = pd.DataFrame(candidates)

    # Sort the EOD slate by execution intent first, then tier and conviction.
    tier_order = {"A": 0, "B": 1, "C": 2, "WATCH": 3}
    status_order = {
        "EOD_THESIS_READY": 0,
        "EOD_THESIS_READY_REPAIR_AT_OPEN": 1,
        "EOD_TRIGGER_READY": 2,
        "EOD_PROBE_CANDIDATE": 3,
        "EOD_WATCHLIST_MONETISABLE": 4,
        "EOD_DATA_INSUFFICIENT_REVIEW": 5,
        "EOD_NO_OPTIONS_ROUTE": 7,
        "EOD_STRUCTURAL_BLOCK": 8,
        "EOD_CATALYST_EXECUTE_CANDIDATE": 0,
        "EOD_EXECUTE_CANDIDATE": 1,
        "EOD_EXECUTE_WITH_CAUTION": 2,
        "EOD_CONTRACT_REPAIR_REQUIRED": 3,
        "EOD_TRIGGER_READY_REVIEW": 4,
        "EOD_CATALYST_WATCH": 5,
        "EOD_DIRECTION_CONFLICT_REVIEW": 6,
        "EOD_WATCH": 7,
        "EOD_BLOCK": 8,
    }
    trigger_order = {"STRONG": 0, "SINGLE": 1, "NONE": 2, "": 3}
    out_df["_tier_sort"] = out_df["structural_tier"].map(tier_order).fillna(4)
    out_df["_status_sort"] = out_df["eod_candidate_status"].map(status_order).fillna(8)
    out_df["_trigger_sort"] = (
        out_df["trigger_quality"].fillna("").astype(str).str.upper().map(trigger_order).fillna(3)
    )
    out_df = out_df.sort_values(
        ["_status_sort", "_tier_sort", "_trigger_sort", "monetisation_fit_score", "scs_score"],
        ascending=[True, True, True, False, False],
    )
    out_df = out_df.drop(columns=["_tier_sort", "_status_sort", "_trigger_sort"])
    full_out_df = out_df.reset_index(drop=True)
    full_out_df["slate_rank"] = range(1, len(full_out_df) + 1)

    # Slate-level direction conflict guard: if > 50% of candidates carry
    # MITIGATED_REQUIRES_CONFIRMATION, the whole slate is directionally suspect —
    # warn and discount all candidate scores by 20%.
    _conflict_mask = (
        full_out_df.get("direction_conflict_status", pd.Series("", index=full_out_df.index))
        .fillna("").astype(str).str.upper()
        == "MITIGATED_REQUIRES_CONFIRMATION"
    )
    _n_total = len(full_out_df)
    _n_conflict = int(_conflict_mask.sum())
    if _n_total > 0 and (_n_conflict / _n_total) > 0.50:
        log.warning(
            "SLATE_DIRECTION_CONFLICT_GUARD: %d/%d candidates (%.0f%%) carry "
            "MITIGATED_REQUIRES_CONFIRMATION — slate direction is broadly contested; "
            "applying 20%% score haircut to all candidates.",
            _n_conflict, _n_total, _n_conflict / _n_total * 100.0,
        )
        for _score_col in ("confidence_score", "monetisation_fit_score", "options_research_score"):
            if _score_col in full_out_df.columns:
                full_out_df[_score_col] = (
                    pd.to_numeric(full_out_df[_score_col], errors="coerce")
                    .fillna(0.0)
                    .mul(0.80)
                    .round(2)
                )

    status_series_all = full_out_df["eod_candidate_status"].fillna("").astype(str)
    trigger_go_series = full_out_df.get("trigger_go_eligible", pd.Series("", index=full_out_df.index)).fillna("").astype(str).str.upper().isin({"TRUE", "1", "YES"})
    hard_block_mask = status_series_all.isin({"EOD_NO_OPTIONS_ROUTE", "EOD_STRUCTURAL_BLOCK", "EOD_BLOCK"})
    options_blocked_mask = full_out_df.apply(
        lambda row: _options_blocked_for_morning_candidate(row.to_dict()),
        axis=1,
    )
    manifest_mask = (
        ~hard_block_mask
        & ~options_blocked_mask
        & (
            trigger_go_series
            | status_series_all.isin(EOD_CARRY_FORWARD_STATUSES)
        )
    )
    full_out_df["phase10_manifest_include"] = manifest_mask.map(lambda x: "TRUE" if bool(x) else "FALSE")
    try:
        included = full_out_df.loc[manifest_mask].copy()
        if not included.empty:
            drift_values = included.get("regime_drift_status", pd.Series("", index=included.index)).fillna("").astype(str).str.upper()
            regime_values = included.get("macro_regime_label", pd.Series("", index=included.index)).fillna("").astype(str).str.upper()
            neutral_macro = drift_values.str.contains("DRIFTING_NEUTRAL|NEUTRAL", regex=True).mean() >= 0.75 and regime_values.str.contains("TRANSITIONAL|NEUTRAL|MIXED|UNKNOWN", regex=True).mean() >= 0.75
            side_counts = included.get("primary_direction", pd.Series("", index=included.index)).fillna("").astype(str).str.upper().value_counts()
            if neutral_macro and len(included) >= 10 and not side_counts.empty:
                dominant_side = str(side_counts.index[0])
                dominant_share = float(side_counts.iloc[0]) / float(len(included))
                if dominant_side in {"CALL", "PUT"} and dominant_share >= 0.75:
                    logger.warning("SLATE_DIRECTION_SKEW_GUARD: %.1f%% %s candidates under neutral/transitional macro; review direction handoff before live capital", dominant_share * 100.0, dominant_side)
    except Exception:
        pass
    full_out_df["phase10_manifest_exclusion_reason"] = ""
    full_out_df.loc[hard_block_mask, "phase10_manifest_exclusion_reason"] = "HARD_BLOCK"
    full_out_df.loc[~hard_block_mask & options_blocked_mask, "phase10_manifest_exclusion_reason"] = "OPTIONS_CONTRACT_BLOCK_REPAIR_OR_SHADOW"
    full_out_df.loc[
        ~hard_block_mask & ~options_blocked_mask & ~manifest_mask,
        "phase10_manifest_exclusion_reason",
    ] = "NO_TRIGGER_OR_EXECUTE_SIGNAL"

    shadow_scores = [
        _shadow_opportunity_score(row)
        for row in full_out_df.to_dict("records")
    ]
    if shadow_scores:
        full_out_df["shadow_opportunity_score"] = [x[0] for x in shadow_scores]
        full_out_df["shadow_opportunity_label"] = [x[1] for x in shadow_scores]
        full_out_df["shadow_opportunity_reason"] = [x[2] for x in shadow_scores]
    else:
        full_out_df["shadow_opportunity_score"] = []
        full_out_df["shadow_opportunity_label"] = []
        full_out_df["shadow_opportunity_reason"] = []

    if output_path:
        audit_cols = [
            "run_id", "ticker", "options_direction", "primary_direction", "direction",
            "direction_reroute_status", "direction_call_score", "direction_put_score",
            "slate_rank", "shadow_opportunity_score", "shadow_opportunity_label",
            "shadow_opportunity_reason",
            "structural_tier", "eod_candidate_status", "eod_candidate_reason",
            "candidate_status", "eod_handoff_lane", "eod_status", "eod_failure_class", "thesis_state", "thesis_summary",
            "expected_holding_window", "expected_move", "target_zone",
            "behaviour_state_key", "behaviour_state_hash", "actuarial_match_type",
            "actuarial_ev_weight", "catalyst_overlay",
            "runway_to_target", "runway_to_wall", "preferred_contract",
            "alternative_contract_1", "alternative_contract_2", "alternative_contract_3",
            "contract_expression_score", "contract_repair_required_at_open",
            "morning_validation_tasks", "live_validation_required", "confidence_score",
            "data_quality_flags", "notes",
            "eod_candidate_permission", "candidate_size", "sizing_policy", "live_capital_permission",
            "eod_live_capital_permission",
            "eod_dropoff_reason", "monetisation_fit_score", "monetisation_fit_label",
            "options_score", "rr", "rr_underlying", "rr_premium_expected", "composite",
            "eil_v3_verdict", "fd_verdict", "fd_advisory_verdict",
            "final_decision_advisory_verdict", "effective_execution_verdict", "pse_execution_mode",
            "eil_signal_verdict", "capital_authorization_state",
            "direction_arbitration_status", "direction_arbitration_reason", "direction_conflict_gate",
            "catalyst_direction_conflict_status", "catalyst_direction_conflict_reason",
            "pcr_direction_conflict_status", "pcr_direction_conflict_reason",
            "direction_conflict_status", "direction_conflict_reason",
            "pcr_vol_status", "pcr_vol_missing_reason",
            "options_research_permission", "final_route", "options_research_route",
            "options_research_score", "hard_vetoes", "options_hard_vetoes",
            "missing_data", "research_route_reason", "breakeven_feasibility",
            "estimated_R", "theta_decay_expected", "runway_to_wall_pct",
            "l3_jump_risk_flag", "jump_risk_review_required", "jump_risk_note",
            "iv_gex_entry_quality", "iv_gex_entry_quality_label",
            "iv_gex_entry_quality_narrative", "gamma_island_on_path",
            "gamma_island_label", "gamma_island_level", "gamma_island_distance_pct",
            "gamma_island_source", "gamma_island_note",
            "move_theta_ratio", "move_theta_margin_label", "move_theta_narrative",
            "crowd_arrival_state", "crowd_arrival_score", "crowd_arrival_components",
            "crowd_arrival_narrative",
            "trigger_quality", "trigger_go_eligible", "catalyst_trade_class",
            "catalyst_data_quality", "contract_repair_status", "contract_repair_reason",
            "contract_quality_score", "contract_spread_pct_eod", "contract_oi",
            "contract_volume", "contract_delta", "contract_gamma", "contract_theta",
            "contract_iv", "contract_bid", "contract_ask", "contract_mid",
            "contract_spread_pct", "contract_symbol",
        ]
        audit_cols = [c for c in audit_cols if c in full_out_df.columns]
        audit_path = Path(output_path).with_name(f"eod_dropoff_audit_{run_id}.csv")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        full_out_df[audit_cols].to_csv(audit_path, index=False)
        log.info(f"  EOD drop-off audit written -> {audit_path}")

        execute_statuses_for_shadow = set(EOD_CARRY_FORWARD_STATUSES)
        status_series = full_out_df.get("eod_candidate_status", pd.Series("", index=full_out_df.index)).fillna("").astype(str)
        rank_series = pd.to_numeric(full_out_df.get("slate_rank", 0), errors="coerce").fillna(0)
        score_series = pd.to_numeric(full_out_df.get("shadow_opportunity_score", 0), errors="coerce").fillna(0)
        cap_applies = bool(max_candidates and max_candidates > 0)
        shadow_mask = (
            (score_series >= 40)
            & (
                ~status_series.isin(execute_statuses_for_shadow)
                | (cap_applies & (rank_series > max_candidates))
            )
        )
        shadow_cols = [
            "run_id", "slate_rank", "ticker", "direction", "primary_direction",
            "direction_reroute_status", "direction_call_score", "direction_put_score",
            "shadow_opportunity_score", "shadow_opportunity_label", "shadow_opportunity_reason",
            "structural_tier", "eod_candidate_status", "eod_dropoff_reason",
            "options_score", "rr", "composite", "eil_v3_verdict", "trigger_quality",
            "catalyst_trade_class", "catalyst_data_quality", "contract_repair_status",
            "direction_arbitration_status", "direction_conflict_gate",
            "direction_conflict_status", "pcr_direction_conflict_status", "pcr_vol_status",
            "final_route", "options_research_route", "hard_vetoes",
            "options_research_score", "breakeven_feasibility", "estimated_R",
            "contract_spread_pct_eod", "contract_oi", "contract_volume",
            "contract_gamma", "contract_theta", "contract_iv", "contract_bid",
            "contract_ask", "contract_mid", "contract_spread_pct",
            "l3_jump_risk_flag", "jump_risk_review_required", "jump_risk_note",
            "iv_gex_entry_quality", "iv_gex_entry_quality_label",
            "iv_gex_entry_quality_narrative", "gamma_island_on_path",
            "gamma_island_label", "gamma_island_level", "gamma_island_distance_pct",
            "gamma_island_source", "gamma_island_note",
            "move_theta_ratio", "move_theta_margin_label", "move_theta_narrative",
            "crowd_arrival_state", "crowd_arrival_score", "crowd_arrival_components",
            "crowd_arrival_narrative",
            "behaviour_state_hash", "actuarial_match_type", "catalyst_overlay",
            "horizon_bucket", "expected_move_window",
        ]
        shadow_cols = [c for c in shadow_cols if c in full_out_df.columns]
        shadow_path = Path(output_path).with_name(f"missed_opportunity_shadow_book_{run_id}.csv")
        full_out_df.loc[shadow_mask, shadow_cols].sort_values(
            ["shadow_opportunity_score", "options_score"],
            ascending=[False, False],
        ).to_csv(shadow_path, index=False)
        log.info(
            "  Missed-opportunity shadow book written -> %s | rows=%d",
            shadow_path,
            int(shadow_mask.sum()),
        )

    # FIX 2: Write regime_watch CSV for WATCH_FOR_REGIME_FLIP rows.
    # These rows route to a rolling watch lane that morning validator reads daily.
    try:
        if "shadow_opportunity_label" in full_out_df.columns:
            _regime_flip_mask = full_out_df["shadow_opportunity_label"].fillna("").astype(str) == "WATCH_FOR_REGIME_FLIP"
            if _regime_flip_mask.any():
                _regime_watch_df = full_out_df.loc[_regime_flip_mask].copy()
                _regime_watch_df["eod_status"] = "REGIME_WATCH"
                _regime_watch_df["watch_since"] = pd.Timestamp.now().strftime("%Y-%m-%d")
                _regime_watch_df["horizon"] = _regime_watch_df.get("horizon_bucket", "6_10d") if "horizon_bucket" in _regime_watch_df.columns else "6_10d"
                _regime_watch_df["watch_condition"] = _regime_watch_df.get("shadow_opportunity_reason", "") if "shadow_opportunity_reason" in _regime_watch_df.columns else ""
                _regime_watch_path = Path(output_path).parent / f"regime_watch_{run_id}.csv"
                _regime_watch_df.to_csv(_regime_watch_path, index=False)
                log.info(
                    "  Regime watch lane written -> %s | rows=%d",
                    _regime_watch_path.name,
                    int(_regime_flip_mask.sum()),
                )
    except Exception as _rw_err:
        log.warning("  Regime watch write failed (non-critical): %s", _rw_err)

    execute_statuses = set(EOD_CARRY_FORWARD_STATUSES)
    execute_like_count = int(full_out_df["eod_candidate_status"].isin(execute_statuses).sum()) if "eod_candidate_status" in full_out_df.columns else 0
    if "eod_candidate_status" in full_out_df.columns:
        full_status_counts = full_out_df["eod_candidate_status"].fillna("").astype(str).value_counts()
        log.info("=== EOD OPPORTUNITY PRESERVATION DIAGNOSTICS ===")
        log.info("  Total tickers processed       : %d", len(full_out_df))
        log.info("  EOD carry-forward rows before cap: %d", execute_like_count)
        for state in [
            "EOD_THESIS_READY",
            "EOD_THESIS_READY_REPAIR_AT_OPEN",
            "EOD_TRIGGER_READY",
            "EOD_WATCHLIST_MONETISABLE",
            "EOD_PROBE_CANDIDATE",
            "EOD_DATA_INSUFFICIENT_REVIEW",
            "EOD_NO_OPTIONS_ROUTE",
            "EOD_STRUCTURAL_BLOCK",
        ]:
            log.info("  %-33s: %d", state, int(full_status_counts.get(state, 0)))
        sig_series = full_out_df.get("signal_type", pd.Series("", index=full_out_df.index)).fillna("").astype(str).str.upper()
        tier_series = full_out_df.get("momentum_tier", pd.Series("", index=full_out_df.index)).fillna("").astype(str).str.upper()
        hb_series = full_out_df.get("horizon_bucket", pd.Series("", index=full_out_df.index)).fillna("").astype(str).str.lower()
        status_series_diag = full_out_df["eod_candidate_status"].fillna("").astype(str)
        preserved_mask = status_series_diag.isin(execute_statuses)
        repair_mask = status_series_diag.eq("EOD_THESIS_READY_REPAIR_AT_OPEN")
        structural_drop_mask = status_series_diag.isin({"EOD_NO_OPTIONS_ROUTE", "EOD_STRUCTURAL_BLOCK"})
        log.info("  Saved from NO_EDGE            : %d", int((preserved_mask & sig_series.eq("NO_EDGE")).sum()))
        log.info("  Saved from TIER_4_FLAT        : %d", int((preserved_mask & tier_series.eq("TIER_4_FLAT")).sum()))
        log.info("  Saved from 11_20d horizon     : %d", int((preserved_mask & hb_series.eq("11_20d")).sum()))
        log.info("  Contract repair at open       : %d", int(repair_mask.sum()))
        log.info("  True structural/no-options drop: %d", int(structural_drop_mask.sum()))
    if len(full_out_df) >= 500 and execute_like_count < 30:
        log.warning(
            "Minimum slate diagnostic: only %d execute-like EOD candidates from %d rows. "
            "Review eod_dropoff_audit_%s.csv before accepting this as market truth.",
            execute_like_count, len(full_out_df), run_id,
        )

    # Apply an optional candidate cap after ranking. A zero/blank cap keeps the
    # full EOD slate available for morning validation and diagnostics.
    manifest_df = full_out_df[manifest_mask].copy()
    if max_candidates and max_candidates > 0:
        out_df = manifest_df.head(max_candidates).reset_index(drop=True)
    else:
        out_df = manifest_df.reset_index(drop=True)
    # B2 FIX: Remove EIL BLOCKED rows from morning candidates manifest
    # BLOCKED tickers are written to a separate audit file for review
    if "eil_v3_verdict" in out_df.columns:
        _blocked_mask = out_df["eil_v3_verdict"].fillna("").str.upper() == "BLOCKED"
        _blocked_count = int(_blocked_mask.sum())
        if _blocked_count > 0:
            _blocked_path = (
                Path(output_path).with_name(f"morning_blocked_review_{run_id}.csv")
                if output_path else None
            )
            if _blocked_path:
                out_df[_blocked_mask].to_csv(_blocked_path, index=False)
            log.info(
                "B2 FILTER: %d BLOCKED tickers removed from candidates "
                "-> morning_blocked_review_%s.csv",
                _blocked_count, run_id,
            )
        out_df = out_df[~_blocked_mask].copy()
    out_df = ensure_physics_fields(out_df)
    if not out_df.empty:
        out_df = enrich_dataframe_with_truth_packets(
            out_df,
            source="EOD_CANDIDATE",
            priority=PRIORITY_DOWNSTREAM_VALIDATION,
            run_id=run_id,
            run_mode="EVENING",
        )
    else:
        # Preserve the schema so diagnostics and final manifest can see that the
        # candidate manifest was intentionally empty instead of crashing with a
        # misleading KeyError.
        for _schema_col in full_out_df.columns:
            if _schema_col not in out_df.columns:
                out_df[_schema_col] = pd.Series(dtype=full_out_df[_schema_col].dtype)

    # ── Summary ───────────────────────────────────────────────────────────────
    for _required_summary_col in ("structural_tier", "candidate_status", "eod_candidate_status"):
        if _required_summary_col not in out_df.columns:
            out_df[_required_summary_col] = ""

    tier_counts = out_df["structural_tier"].value_counts()
    status_counts = out_df["eod_candidate_status"].value_counts() if "eod_candidate_status" in out_df.columns else {}
    log.info("=== CANDIDATE MANIFEST SUMMARY ===")
    log.info(f"  Total candidates : {len(out_df)}")
    for t in ["A", "B", "C", "WATCH"]:
        log.info(f"  Tier {t}           : {tier_counts.get(t, 0)}")
    if len(out_df) > 0 and "eod_candidate_status" in out_df.columns:
        log.info("  EOD slate status:")
        for state, count in status_counts.items():
            log.info(f"    {state:<30}: {count}")

    ready = out_df[out_df["candidate_status"] == "READY_FOR_VALIDATION"]
    log.info(f"  Ready for morning: {len(ready)}")
    log.info(f"  Watch only       : {len(out_df) - len(ready)}")

    if len(out_df) > 0:
        log.info(f"\n  Top 5 candidates:")
        for _, r in out_df.head(5).iterrows():
            log.info(
                f"    {r['ticker']:<6} [{r['structural_tier']}] "
                f"SCS={r['scs_score']:.0f} "
                f"OIS={r['options_score']:.0f} "
                f"RR={r['rr']:.2f} "
                f"WBS={r['wbs_grade'] or 'N/A'} "
                f"STATUS={r.get('eod_candidate_status', 'N/A')} "
                f"→ {r['setup_type']}"
            )

    # ── Write output ──────────────────────────────────────────────────────────
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        out_df.to_csv(output_path, index=False)
        log.info(f"\n  Manifest written → {output_path}")
        try:
            import sys as _ma_sys
            _ma_sys.path.insert(0, r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\pipeline_interpreter")
            from ma_inputs_sync import on_pipeline_complete as _ma_on_pipeline_complete
            _ma_on_pipeline_complete(str(output_path), output_dir=str(Path(output_path).parent))
        except Exception as _ma_sync_err:
            log.warning("MA_Inputs sync skipped for candidate manifest: %s", _ma_sync_err)

    return out_df


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AVSHUNTER EOD Candidate Engine")
    parser.add_argument("--run_id",    required=True)
    parser.add_argument("--base_dir",  default=r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs")
    parser.add_argument("--max_candidates", type=int, default=0, help="Maximum rows to write; 0 means no cap.")
    args = parser.parse_args()

    base   = Path(args.base_dir) / args.run_id
    sb_dir = base / "superbrain"
    mv_dir = base / "morning_validation"
    mv_dir.mkdir(parents=True, exist_ok=True)

    build_candidate_manifest(
        eil_path        = sb_dir / f"eil_enriched_{args.run_id}.csv",
        wbs_path        = base   / f"wall_break_scores_{args.run_id}.csv",
        discovery_path  = base   / "discovery" / f"discovery_candidates_ultimate_{args.run_id}.csv",
        output_path     = mv_dir / f"morning_candidates_{args.run_id}.csv",
        run_id          = args.run_id,
        max_candidates  = args.max_candidates,
    )
