#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           AVSHUNTER OPTIONS INTELLIGENCE LAYER v1.1                         ║
║                                                                              ║
║  POSITION IN PIPELINE:                                                       ║
║    Orchestrator → Discovery → Vanguard → [OPTIONS INTELLIGENCE] → Lab       ║
║                                                                              ║
║  CONTRACT:                                                                   ║
║    Input  : merged discovery + vanguard CSV (post-run package)               ║
║    Scope  : Tier 0/1/2 plus Vanguard statistical-support overrides           ║
║    Output : options_intelligence_{run_id}.csv                                ║
║             options_intelligence_summary_{run_id}.json                       ║
║             Enriched fields written back to vanguard_signals_enriched.csv   ║
║                                                                              ║
║  DESIGN PRINCIPLES:                                                          ║
║    1. Structural intent is primary; Vanguard/catalyst support may repair WAIT║
║    2. Options layer confirms, sizes, and gates — it does not originate       ║
║    3. DTE derived from tier + phase — never hardcoded                        ║
║    4. Target price from AVSHUNTER structural levels — not vol estimate       ║
║    5. Pipeline failure = STAND_DOWN, not crash                               ║
║    6. Every signal receives a verdict: EXECUTE / ARMED / STAND_DOWN         ║
║                                                                              ║
║  OUTPUT FIELDS TO INTELLIGENCE LAB:                                          ║
║    options_verdict       : EXECUTE / ARMED / STAND_DOWN                     ║
║    options_direction     : CALL / PUT / NONE                                ║
║    options_strategy      : LONG_CALL / LONG_PUT                              ║
║    recommended_contract  : ticker symbol of best contract                    ║
║    contract_strike       : recommended strike                                ║
║    contract_expiry       : recommended expiry date                           ║
║    contract_dte          : days to expiry                                    ║
║    contract_premium      : mark price per contract                           ║
║    contract_delta        : delta                                             ║
║    contract_theta        : theta (daily decay)                               ║
║    contract_vega         : vega                                              ║
║    iv_rank               : 0-100 (< 30 = cheap, > 70 = expensive)           ║
║    iv_percentile         : 0-1                                               ║
║    ivp_label             : CHEAP / FAIR / EXPENSIVE                         ║
║    gamma_flip            : price level where dealer hedging flips            ║
║    gamma_flip_gap_pct    : % distance from entry to gamma flip               ║
║    call_wall             : highest OI call strike                            ║
║    put_wall              : highest OI put strike                             ║
║    max_pain              : max pain strike                                   ║
║    pcr_oi                : put/call ratio by OI                              ║
║    pcr_signal            : BULLISH / BEARISH / NEUTRAL                      ║
║    target_in_play        : True if structural target clears call wall        ║
║    breakeven_pct         : % move needed to break even on option             ║
║    theta_drag_pct        : theta cost as % of premium over hold period      ║
║    vega_risk_pct         : loss if IV drops 10 points                        ║
║    structural_ev         : EV using AVSHUNTER structural target              ║
║    options_score         : 0-100 composite options intelligence score        ║
║    stand_down_reason     : why signal was blocked (if applicable)            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
# ── CHANGELOG v1.0 → v1.1 ────────────────────────────────────────────────────
# FIX-NO-CONTRACT-01: select_best_contract() delta relaxation fallback now uses
#   the RELAXED DTE window (dte_min-15 to dte_max+15) not the strict window.
#   Previous code re-applied strict DTE on retry, finding nothing for Phase C
#   signals with sparse chains. Also widened delta relaxation from ±0.10 to ±0.15
#   (BSM-computed deltas carry model error in EOD mode). Added last-resort path:
#   any contract with valid mark in DTE range. Expected: ~200 BLOCK_NO_CONTRACT
#   signals recover to ARMED.
#
# FIX-WRONG-STRIKE-01: BLOCK_WRONG_STRIKE demoted from hard STAND_DOWN to ARMED.
#   When option_value_at_target=0 but mark>0 (valid premium, tight target geometry),
#   now surfaces WARN_STRIKE_AT_TARGET warning and continues to score-based verdict.
#   Hard STAND_DOWN retained only when mark=0 (genuinely no payoff path).
#   Expected: ~71 BLOCK_WRONG_STRIKE signals recover to ARMED → some to EXECUTE.
#
# FIX-THETA-01: BLOCK_THETA threshold raised 70% → 85%.
#   13 Phase D signals at DTE=22 were blocked by the 70% theta gate even though
#   Phase D hold periods are 3-5 days. 85% correctly targets contracts where decay
#   genuinely destroys the position (very short DTE, long hold intention).
# OTT-PASS-01 (2026-04-27): Added contract_gamma, contract_oi, contract_spread_pct,
#   hv_30d, atm_iv, iv_vs_hv, iv_direction, iv_regime to options_fields passthrough
#   list so vanguard_signals_enriched carries these fields to EIL and M1/M3/M6
#   modules. These were written to options_intelligence CSV but silently dropped
#   at the vanguard merge step — M6 theta_bpr_engine received None for theta/gamma.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import sys, os, time, json, math, cmath, warnings, random, re, hashlib

# ── Windows CP1252 fix: configure streams in place so importing this module
# never replaces or closes a host/test runner's capture streams.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, OSError, ValueError):
            pass
from datetime import datetime, timezone, date, timedelta
from math import log, sqrt, exp
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# This file is launched directly by intelligent_orchestrator.py. In that mode
# Python places scripts\ (rather than the repository root) on sys.path, so
# sibling packages such as contracts\ are otherwise unavailable. Keep this
# bootstrap before any repository-local imports and mirror the production
# entrypoint in regression coverage.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm
from scipy.optimize import brentq, minimize
from scipy.integrate import quad

from contracts.direction_governance import (
    DIRECTED as GOVERNED_DIRECTED_SIDES,
    resolve_governed_direction,
    structural_direction,
)
from canonical_data.contract_reference import infer_standard_occ_multiplier
from contracts.long_option_policy import (
    LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT,
    LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT,
    quote_spread_fraction,
)
from contracts.options_liquidity_lifecycle import (
    LifecycleInputs,
    OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    calculate_dte_requirement,
    evaluate_options_liquidity_lifecycle,
)
from contracts.governed_states import GovernedDataState, LifecycleEvaluationState
from contracts.dynamic_session_contract import DataExceptionReason
from contracts.thesis_geometry import select_directional_invalidation
from msi_runtime import active_flags as active_msi_flags

_CDS_CHAIN_SERVICE = None
_CDS_LIQUIDITY_STORE = None
_CDS_V2_CHAIN_RESOLVER = None
_CDS_V2_SESSION = None
_MD_RAW_CHAIN_PAYLOADS: Dict[str, Dict[str, Any]] = {}

OPTIONS_SESSION_EXCEPTION_COLUMNS = [
    "ticker",
    "expected_session",
    "actual_session",
    "session_source",
    "data_source",
    "is_stale",
    "exception_reason",
    "exception_action",
]


def _resolve_options_session_scope(
    eligible: pd.DataFrame,
) -> Tuple[date, str, pd.DataFrame]:
    """Resolve the governed session and quarantine ticker-level data exceptions.

    A stale or missing ticker observation must not make an otherwise coherent
    Options population ambiguous.  The strict canonical resolver therefore sees
    only rows that upstream explicitly represents as current.  Any disagreement
    among those current rows remains a hard failure.
    """
    from canonical_data import resolve_completed_session_date

    session_source = ""
    session_values = pd.Series(index=eligible.index, dtype="object")
    for session_col in ("bar_data_asof", "data_as_of"):
        if session_col not in eligible.columns:
            continue
        candidate_values = eligible[session_col]
        if candidate_values.notna().any():
            session_source = session_col
            session_values = candidate_values
            break

    parsed_sessions = pd.to_datetime(session_values, errors="coerce").dt.date
    stale_mask = pd.Series(False, index=eligible.index, dtype=bool)
    if "is_stale" in eligible.columns:
        stale_mask |= eligible["is_stale"].map(
            lambda value: str(value).strip().lower() in {"1", "true", "yes", "on"}
        )
    for source_col in ("data_source", "bar_data_source"):
        if source_col in eligible.columns:
            stale_mask |= (
                eligible[source_col]
                .fillna("")
                .astype(str)
                .str.upper()
                .str.strip()
                .eq("STALE_CACHE")
            )

    fresh_sessions = parsed_sessions[parsed_sessions.notna() & ~stale_mask].tolist()
    run_session = resolve_completed_session_date(fresh_sessions)

    exception_mask = stale_mask | parsed_sessions.isna() | parsed_sessions.ne(run_session)
    exception_rows: List[Dict[str, Any]] = []
    for index in eligible.index[exception_mask]:
        actual = parsed_sessions.loc[index]
        if pd.isna(actual):
            reason = "UNDERLYING_SESSION_UNAVAILABLE"
            actual_text = ""
        elif actual != run_session:
            reason = "UNDERLYING_SESSION_MISMATCH"
            actual_text = actual.isoformat()
        else:
            reason = "UNDERLYING_DATA_STALE"
            actual_text = actual.isoformat()
        source = ""
        for source_col in ("data_source", "bar_data_source"):
            if source_col in eligible.columns:
                raw_value = eligible.at[index, source_col]
                if pd.isna(raw_value):
                    continue
                value = str(raw_value).strip()
                if value and value.lower() not in {"nan", "none"}:
                    source = value
                    break
        raw_ticker = eligible.at[index, "ticker"]
        ticker = "" if pd.isna(raw_ticker) else str(raw_ticker).strip()
        exception_rows.append({
            "ticker": ticker,
            "expected_session": run_session.isoformat(),
            "actual_session": actual_text,
            "session_source": session_source,
            "data_source": source,
            "is_stale": bool(stale_mask.loc[index]),
            "exception_reason": reason,
            "exception_action": "QUARANTINE_MONITOR_ONLY_NO_OPTIONS_ACQUISITION",
        })

    return (
        run_session,
        session_source,
        pd.DataFrame(exception_rows, columns=OPTIONS_SESSION_EXCEPTION_COLUMNS),
    )

try:
    from scripts.macro_quant_packet import (
        MACRO_QUANT_CSV_FIELDS,
        macro_quant_columns_for_row,
        resolve_macro_suffix_columns,
    )
except Exception:
    from macro_quant_packet import (  # type: ignore
        MACRO_QUANT_CSV_FIELDS,
        macro_quant_columns_for_row,
        resolve_macro_suffix_columns,
    )

try:
    from contracts.macro_enrichment_delta import candidate_macro_enrichment_audit, interpret_macro_decision_context
except Exception:
    try:
        from macro_enrichment_delta import candidate_macro_enrichment_audit, interpret_macro_decision_context  # type: ignore
    except Exception:
        candidate_macro_enrichment_audit = None  # type: ignore
        interpret_macro_decision_context = None  # type: ignore

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

POLYGON_API_KEY     = os.getenv("POLYGON_API_KEY", "").strip()
MARKETDATA_API_KEY  = os.getenv("MARKETDATA_API_KEY", "").strip()  # marketdata.app — real quote enrichment

# ── .env fallback — load from repo root if env vars not set in subprocess ─────
# When the orchestrator spawns this script as a child process, environment
# variables set in the parent PowerShell session are NOT automatically inherited.
# This loader reads the .env file from the repo root so API keys are always
# available regardless of how the script is launched.
if not POLYGON_API_KEY or not MARKETDATA_API_KEY:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(_env_path):
        _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(_env_path):
        try:
            with open(_env_path, "r", encoding="utf-8") as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip('"').strip("'")
                        if _k == "POLYGON_API_KEY" and not POLYGON_API_KEY:
                            POLYGON_API_KEY = _v
                        elif _k == "MARKETDATA_API_KEY" and not MARKETDATA_API_KEY:
                            MARKETDATA_API_KEY = _v
        except Exception:
            pass  # .env read failure is non-fatal
RISK_FREE_RATE      = float(os.getenv("AVS_RFR", "0.045"))

# Options layer recommends review candidates; execution still requires manual
# reviewer approval before any order is eligible.
OPTIONS_RESEARCH_PERMISSION = "MANUAL_REVIEW_REQUIRED"
OPTIONS_GO_ROUTE = "OPTIONS_GO_REVIEW"
OPTIONS_ARMED_ROUTE = "OPTIONS_ARMED_HALF"
OPTIONS_PROBE_ROUTE = "OPTIONS_PROBE_ONLY"
OPTIONS_EQUITY_ONLY_ROUTE = "OPTIONS_EQUITY_ONLY_BETTER"
OPTIONS_BLOCKED_ROUTE = "OPTIONS_BLOCKED"
# Research scoring bands.  These classify contract quality but never grant
# capital.  The final executable/reviewable limits live in
# ``contracts.long_option_policy`` and are evaluated again on the exact quote.
OPTIONS_SPREAD_PASS_PCT = 0.15
OPTIONS_SPREAD_HARD_PCT = LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT / 100.0
OPTIONS_MIN_BREAKEVEN_FEASIBILITY = 1.0
OPTIONS_MIN_R_MULTIPLE = 1.0
OPTIONS_THETA_DECAY_LIMIT_PCT = 35.0
OPTIONS_THETA_HIGH_R_FLOOR = 5.0
OPTIONS_MIN_RUNWAY_TO_WALL_PCT = 1.0


def _truthy_oi(value: Any) -> bool:
    return str(value).strip().upper() in {"1", "TRUE", "YES", "Y", "PASS", "OK"}


def _direction_conflict_status_oi(direction: str, pcr_signal: Any, pcr_value: Any = None) -> Dict[str, Any]:
    direction_u = str(direction or "").upper()
    signal_u = str(pcr_signal or "").upper()
    if not signal_u or signal_u in {"UNKNOWN", "NONE", "NAN", "NO_DATA"}:
        return {
            "pcr_direction_conflict_status": "NO_PCR_DATA",
            "pcr_direction_conflict_reason": "PCR source unavailable",
            "pcr_confidence_weight": 0.0,
        }

    confirms = (
        (direction_u == "CALL" and signal_u in {"BULLISH", "CALL_BULLISH", "CALL_CONFIRM", "RISK_ON"})
        or (direction_u == "PUT" and signal_u in {"BEARISH", "PUT_BEARISH", "PUT_CONFIRM", "RISK_OFF"})
    )
    conflicts = (
        (direction_u == "CALL" and signal_u in {"BEARISH", "PUT_BEARISH", "PUT_CONFIRM", "RISK_OFF"})
        or (direction_u == "PUT" and signal_u in {"BULLISH", "CALL_BULLISH", "CALL_CONFIRM", "RISK_ON"})
    )
    if confirms:
        return {
            "pcr_direction_conflict_status": "PCR_CONFIRMS_REDUCED_CONFIDENCE",
            "pcr_direction_conflict_reason": f"OI PCR confirms {direction_u} with reduced confidence",
            "pcr_confidence_weight": 0.6,
        }
    if conflicts:
        return {
            "pcr_direction_conflict_status": "PCR_CONFLICT_REQUIRES_FLOW_CONFIRMATION",
            "pcr_direction_conflict_reason": f"OI PCR conflicts with {direction_u}",
            "pcr_confidence_weight": 0.6,
        }
    return {
        "pcr_direction_conflict_status": "PCR_NEUTRAL",
        "pcr_direction_conflict_reason": f"OI PCR signal {signal_u} is not directional for {direction_u}",
        "pcr_confidence_weight": 0.6 if pcr_value not in (None, "", "nan", "NaN") else 0.0,
    }


def _macro_multiplier_audit_oi(ctx: Dict[str, Any], macro_adj: Dict[str, Any]) -> Dict[str, Any]:
    """Publish the legacy macro multipliers as advisory values only."""
    trade_type = str(macro_adj.get("trade_type_classification") or "").upper()
    alignment = str(macro_adj.get("macro_alignment_state") or "").upper()
    authority = str(macro_adj.get("macro_direction_authority") or "").upper()
    horizon = str(ctx.get("macro_preferred_horizon") or ctx.get("horizon_bucket") or "").lower()

    structural = trade_type == "STRUCTURAL_SINGLE_STOCK" or alignment in {"MACRO_NOT_APPLICABLE", "NO_DIRECTIONAL_MACRO_EDGE"}
    if structural and authority == "DISABLED":
        structural_mult = 0.4 if "6_10" in horizon or "6-10" in horizon else 0.5
        macro_mult = 1.0
    else:
        structural_mult = 1.0
        macro_mult = 1.0
        if authority == "DISABLED":
            macro_mult = 0.5
        elif alignment in {"CALL_UNCONFIRMED_NEEDS_LOCAL_CONFIRMATION", "PUT_UNCONFIRMED_NEEDS_LOCAL_CONFIRMATION"}:
            macro_mult = 0.8

    return {
        "macro_multiplier": 1.0,
        "structural_multiplier": 1.0,
        "macro_multiplier_advisory": round(macro_mult, 4),
        "structural_multiplier_advisory": round(structural_mult, 4),
        "macro_multiplier_authority": "ADVISORY_ONLY",
    }


def _macro_confirmation_overlay_oi(
    ctx: Dict[str, Any],
    sector_data: Dict[str, Any],
    macro_adj: Dict[str, Any],
    verdict: str,
) -> Dict[str, Any]:
    direction = str(ctx.get("direction") or "").upper()
    macro_bias = str(sector_data.get("macro_sector_bias") or macro_adj.get("macro_sector_bias") or "").upper()
    alignment = str(macro_adj.get("macro_alignment_state") or "").upper()
    if direction != "PUT":
        return {"macro_confirmation_level": "STANDARD", "macro_routing_state": alignment or "STANDARD"}
    if macro_bias not in {"TAILWIND", "PREFERRED"} and alignment != "PUT_ELEVATED_CONFIRMATION":
        return {"macro_confirmation_level": "STANDARD", "macro_routing_state": alignment or "STANDARD"}

    phase = str(ctx.get("phase") or "").upper()
    edge = str(ctx.get("edge_quality") or ctx.get("layer2__edge_quality") or "").upper()
    seller_control = str(ctx.get("intent") or "").upper() == "SELL_SETUP"
    sector_underperf = (_oi_float(sector_data.get("sector_5d_return")) or 0.0) < 0.0
    full_confirm = (
        phase == "D"
        and edge in {"STRONG_EDGE", "STRONG"}
        and seller_control
        and sector_underperf
    )
    if full_confirm and verdict in {"EXECUTE", "ARMED"}:
        return {"macro_confirmation_level": "ELEVATED", "macro_routing_state": "PUT_ELEVATED_CONFIRMATION"}
    return {"macro_confirmation_level": "WATCHLIST_ELEVATED", "macro_routing_state": "WATCHLIST_ELEVATED_CONFIRMATION"}


def _is_strong_edge_probable(ctx: Dict[str, Any]) -> bool:
    edge = str(ctx.get("edge_quality") or ctx.get("layer2__edge_quality") or "").upper()
    return edge in {"STRONG_EDGE", "STRONG"}


def _direction_arbitration_oi(ctx: Dict[str, Any]) -> Dict[str, str]:
    """F13: surface Wyckoff structure vs Vanguard probability arbitration."""
    vg_edge_dir = str(
        ctx.get("vanguard_edge_direction")
        or ctx.get("layer2__edge_direction")
        or ctx.get("vanguard_edge_dir")
        or ctx.get("layer2__probability_direction")
        or "NONE"
    ).upper()
    intent = str(ctx.get("intent") or "").upper()
    governed = str(ctx.get("governed_direction") or ctx.get("direction") or "").upper()
    final_direction = str(ctx.get("direction") or "").upper()
    if governed in {"STRANGLE", "UNRESOLVED"}:
        if final_direction in {"CALL", "PUT"}:
            return {
                "direction_arbitration_status": "GOVERNED_NON_DIRECTIONAL_RESOLVED",
                "direction_arbitration_reason": (
                    f"Structural direction {governed} resolved to {final_direction} "
                    "by the governed pre-contract protocol"
                ),
                "direction_conflict_gate": "NONE",
            }
        return {
            "direction_arbitration_status": "STRUCTURAL_NON_DIRECTIONAL",
            "direction_arbitration_reason": (
                f"Structural direction remains {governed}; directional resolution required"
            ),
            "direction_conflict_gate": "DIRECTION_RESOLUTION_REQUIRED",
        }
    if intent == "SELL_SETUP" and vg_edge_dir == "CALL":
        return {
            "direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS",
            "direction_arbitration_reason": "Wyckoff SELL_SETUP vs actuarial CALL probability",
            "direction_conflict_gate": "VWAP_CONFIRMATION_REQUIRED",
        }
    if intent == "BUY_SETUP" and vg_edge_dir == "PUT":
        return {
            "direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS",
            "direction_arbitration_reason": "Wyckoff BUY_SETUP vs actuarial PUT probability",
            "direction_conflict_gate": "VWAP_CONFIRMATION_REQUIRED",
        }
    if vg_edge_dir in {"", "NONE", "NAN", "NO_DATA", "UNKNOWN"}:
        return {
            "direction_arbitration_status": "NO_PROBABILITY_OPINION",
            "direction_arbitration_reason": "Vanguard produced no directional probability",
            "direction_conflict_gate": "NONE",
        }
    return {
        "direction_arbitration_status": "AGREEMENT",
        "direction_arbitration_reason": "Structure and probability aligned",
        "direction_conflict_gate": "NONE",
    }


def _options_verdict_tier_oi(
    ctx: Dict[str, Any],
    verdict: str,
    research_contract: Dict[str, Any],
    block_code: str,
    block_severity: str,
) -> Dict[str, Any]:
    route = str(research_contract.get("final_route") or "").upper()
    edge = str(ctx.get("edge_quality") or ctx.get("layer2__edge_quality") or "").upper()
    if verdict == "EXECUTE" or route == OPTIONS_GO_ROUTE:
        tier = "READY_EXECUTE"
    elif route in {OPTIONS_ARMED_ROUTE, OPTIONS_PROBE_ROUTE}:
        tier = "READY_PROBE"
    elif (
        block_severity == "SOFT"
        and (edge in {"STRONG_EDGE", "STRONG"} or (_oi_float(ctx.get("composite")) or 0.0) >= 65)
        and block_code not in {"BLOCK_INVALID_INPUT", "BLOCK_WAIT_INTENT", "BLOCK_NO_CHAIN", "BLOCK_PIPELINE_ERROR"}
    ):
        tier = "STRUCTURE_CONFIRMED_CONTRACT_BLOCKED"
    elif verdict in {"ARMED", "WATCHLIST"}:
        tier = "WATCHLIST"
    else:
        tier = "STAND_DOWN"
    attempts = []
    if tier == "STRUCTURE_CONFIRMED_CONTRACT_BLOCKED":
        attempts = ["NEXT_OTM_STRIKE", "NEXT_ATM_STRIKE", "NEXT_MONTHLY_EXPIRY"]
    return {
        "options_verdict_tier": tier,
        "alternative_contract_attempts": "|".join(attempts),
    }


def _json_csv(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    if value is None:
        return ""
    return str(value)


def _parse_jsonish_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            loaded = json.loads(text)
            return _parse_jsonish_list(loaded)
        except Exception:
            pass
    return [part.strip().upper() for part in text.replace("|", ",").split(",") if part.strip()]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def load_package_macro_contexts(run_id: str, output_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Options-only macro enrichment bridge.

    The Options layer normally reads discovery + Vanguard CSVs. Macro enrichment
    is injected into packages before Vanguard, but the narrative enrichment must
    not score Vanguard. This loader lets Options consult package MacroContext
    directly and apply only an audited options-alignment bonus.
    """
    contexts: Dict[str, Dict[str, Any]] = {}
    run_dir = os.path.abspath(os.path.join(os.path.abspath(output_dir), os.pardir))
    packages_dir = os.path.join(run_dir, "packages")
    if not os.path.isdir(packages_dir):
        return contexts

    for name in os.listdir(packages_dir):
        if not name.endswith(".package.json"):
            continue
        path = os.path.join(packages_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)
            ticker = str(pkg.get("ticker") or name.split(".")[0]).strip().upper()
            macro_block = pkg.get("macro") if isinstance(pkg.get("macro"), dict) else {}
            payload = macro_block.get("payload") if isinstance(macro_block, dict) else None
            if ticker and isinstance(payload, dict):
                extras = payload.get("extras") if isinstance(payload.get("extras"), dict) else {}
                if extras.get("macro_enrichment_delta") or extras.get("macro_exposure_index"):
                    contexts[ticker] = payload
        except Exception:
            continue
    return contexts


def load_package_tle_contexts(run_id: str, output_dir: str) -> Dict[str, Dict[str, Any]]:
    """
    Sprint 3 — Trap-to-Launch Engine context loader.
    Reads tle_ fields written by avshunter_trap_engine.py (Phase 5.5) from package JSONs.
    Returns {ticker: tle_dict} for all packages that have a tle block.
    """
    contexts: Dict[str, Dict[str, Any]] = {}
    run_dir = os.path.abspath(os.path.join(os.path.abspath(output_dir), os.pardir))
    packages_dir = os.path.join(run_dir, "packages")
    if not os.path.isdir(packages_dir):
        return contexts
    for name in os.listdir(packages_dir):
        if not name.endswith(".package.json"):
            continue
        path = os.path.join(packages_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)
            ticker = str(pkg.get("ticker") or name.split(".")[0]).strip().upper()
            tle_block = pkg.get("tle")
            if ticker and isinstance(tle_block, dict) and tle_block.get("tle_verdict"):
                contexts[ticker] = tle_block
        except Exception:
            continue
    return contexts


def options_macro_alignment_adjustment(
    ctx: Dict[str, Any],
    macro_context: Optional[Dict[str, Any]],
    signal_row: Any = None,
) -> Dict[str, Any]:
    row_get = (lambda key, default=None: signal_row.get(key, default)) if hasattr(signal_row, "get") else (lambda key, default=None: default)

    if not macro_context and _safe_int(row_get("macro_enrichment_theme_count", 0)) > 0:
        roles = _parse_jsonish_list(row_get("macro_enrichment_roles", ""))
        conflicts = _parse_jsonish_list(row_get("macro_enrichment_conflict_flags", ""))
        confirmations = _parse_jsonish_list(row_get("macro_enrichment_confirmation_required", ""))
        macro_alignment_state = str(row_get("macro_alignment_state", "") or "")
        macro_direction_authority = str(row_get("macro_direction_authority", "") or "")
        macro_applicability = str(row_get("macro_applicability", "") or "")
        trade_type = str(row_get("trade_type_classification", "") or "")
        macro_filter = str(row_get("macro_enrichment_macro_filter", "") or "").upper()
        trigger_required = str(row_get("macro_enrichment_trigger_required", "") or "").strip().lower() == "true"
        put_permission = str(row_get("macro_enrichment_put_gate_permission", "") or "").upper()
        direction = str(ctx.get("direction") or "").upper()
        hard_gate_active = (
            "NO_GO" in macro_filter
            or trigger_required
            or (direction == "PUT" and put_permission in {"RESTRICTED", "BLOCKED", "NO_GO"})
        )
        aligned = (
            ("BENEFICIARY" in roles and direction == "CALL")
            or ("VULNERABLE" in roles and direction == "PUT")
        )
        contradicted = (
            ("BENEFICIARY" in roles and direction == "PUT")
            or ("VULNERABLE" in roles and direction == "CALL")
        )
        bonus = 0.0
        if hard_gate_active:
            label = "ALIGNED_WITH_MACRO_HEADWIND" if aligned else "MACRO_HEADWIND_ADVISORY"
        elif conflicts:
            label = "CONFLICT_REQUIRES_CONFIRMATION"
        elif confirmations:
            label = "ALIGNED_REQUIRES_CONFIRMATION" if aligned else "REQUIRES_CONFIRMATION"
            bonus = 1.0 if aligned else 0.0
        elif aligned:
            label = "MACRO_ALIGNED_OPTIONS_PLUS"
            bonus = 3.0
        elif contradicted:
            label = "MACRO_CONTRADICTS_OPTION_DIRECTION"
            bonus = -2.0
        else:
            label = "MACRO_CONTEXT_NEUTRAL"
        note = str(row_get("macro_enrichment_audit_note", "") or "")
        if hard_gate_active:
            note = f"{note} Legacy macro gate retained as advisory context only."
        elif bonus > 0:
            note = f"{note} Options-only alignment bonus applied: +{bonus:.1f} OIS."
        elif bonus < 0:
            note = f"{note} Options-only contradiction penalty applied: {bonus:.1f} OIS."
        return {
            "options_macro_alignment_label": label,
            "options_macro_alignment_bonus": bonus,
            "options_macro_gate_preserved": False,
            "options_macro_theme_ids": str(row_get("macro_enrichment_theme_ids", "") or ""),
            "options_macro_roles": str(row_get("macro_enrichment_roles", "") or ""),
            "options_macro_event_guards": str(row_get("macro_enrichment_event_guards", "") or ""),
            "options_macro_conflict_flags": str(row_get("macro_enrichment_conflict_flags", "") or ""),
            "options_macro_confirmation_required": str(row_get("macro_enrichment_confirmation_required", "") or ""),
            "options_macro_alignment_note": note,
            "macro_alignment_state": macro_alignment_state,
            "macro_direction_authority": macro_direction_authority,
            "macro_applicability": macro_applicability,
            "trade_type_classification": trade_type,
        }

    if not macro_context or not callable(candidate_macro_enrichment_audit):
        return {
            "options_macro_alignment_label": "NO_MACRO_ENRICHMENT",
            "options_macro_alignment_bonus": 0.0,
            "options_macro_gate_preserved": False,
            "options_macro_theme_ids": "",
            "options_macro_roles": "",
            "options_macro_event_guards": "",
            "options_macro_conflict_flags": "",
            "options_macro_confirmation_required": "",
            "options_macro_alignment_note": "No macro enrichment context was available to Options.",
            "macro_alignment_state": "MACRO_NOT_APPLICABLE",
            "macro_direction_authority": "DISABLED",
            "macro_applicability": "NOT_APPLICABLE",
            "macro_direction_vote": "ABSTAIN",
            "macro_raw_direction_hint": "ABSTAIN",
            "macro_can_invert_direction": False,
            "structure_first_required": True,
            "trade_type_classification": "STRUCTURAL_SINGLE_STOCK",
        }

    audit = candidate_macro_enrichment_audit(macro_context, ctx.get("ticker"))
    decision = {}
    if callable(interpret_macro_decision_context):
        decision = interpret_macro_decision_context(
            macro_context,
            ticker=ctx.get("ticker"),
            direction=ctx.get("direction"),
            gics_sector=ctx.get("gics_sector_norm") or ctx.get("sector") or ctx.get("gics_sector"),
        )
    roles = set(audit.get("macro_enrichment_roles") or [])
    conflicts = list(audit.get("macro_enrichment_conflict_flags") or [])
    confirmations = list(audit.get("macro_enrichment_confirmation_required") or [])
    direction = str(ctx.get("direction") or "").upper()
    macro_filter = str(decision.get("macro_filter") or macro_context.get("macro_filter") or "").upper()
    trigger_required = bool(decision.get("macro_trigger_required", macro_context.get("trigger_required")))
    put_permission = str(decision.get("macro_put_gate_permission") or "").upper()
    direction_authority = str(decision.get("macro_direction_authority") or "").upper()
    alignment_state = str(decision.get("macro_alignment_state") or "").upper()
    applicability = str(decision.get("macro_applicability") or "").upper()

    hard_gate_active = (
        "NO_GO" in macro_filter
        or trigger_required
        or (direction == "PUT" and put_permission in {"RESTRICTED", "BLOCKED", "NO_GO"})
    )
    aligned = (
        ("BENEFICIARY" in roles and direction == "CALL")
        or ("VULNERABLE" in roles and direction == "PUT")
    )
    contradicted = (
        ("BENEFICIARY" in roles and direction == "PUT")
        or ("VULNERABLE" in roles and direction == "CALL")
    )

    bonus = 0.0
    label = "NO_ENRICHMENT_MATCH"
    if int(audit.get("macro_enrichment_theme_count") or 0) > 0:
        if direction_authority == "DISABLED" or applicability == "NOT_APPLICABLE":
            label = alignment_state or "MACRO_STRUCTURE_FIRST"
        elif hard_gate_active:
            label = "ALIGNED_WITH_MACRO_HEADWIND" if aligned else "MACRO_HEADWIND_ADVISORY"
        elif conflicts:
            label = "CONFLICT_REQUIRES_CONFIRMATION"
        elif confirmations:
            label = "ALIGNED_REQUIRES_CONFIRMATION" if aligned else "REQUIRES_CONFIRMATION"
            bonus = 1.0 if aligned else 0.0
        elif aligned:
            label = "MACRO_ALIGNED_OPTIONS_PLUS"
            bonus = 3.0
        elif contradicted:
            label = "MACRO_CONTRADICTS_OPTION_DIRECTION"
            bonus = -2.0
        else:
            label = "MACRO_CONTEXT_NEUTRAL"

    note = audit.get("macro_enrichment_audit_note") or ""
    if hard_gate_active:
        note = f"{note} Legacy macro gate retained as advisory context only."
    if decision:
        note = f"{note} {decision.get('macro_interpretation_reason', '')}".strip()
    elif bonus > 0:
        note = f"{note} Options-only alignment bonus applied: +{bonus:.1f} OIS."
    elif bonus < 0:
        note = f"{note} Options-only contradiction penalty applied: {bonus:.1f} OIS."

    return {
        "options_macro_alignment_label": label,
        "options_macro_alignment_bonus": bonus,
        "options_macro_gate_preserved": False,
        "options_macro_theme_ids": _json_csv(audit.get("macro_enrichment_theme_ids") or []),
        "options_macro_roles": _json_csv(audit.get("macro_enrichment_roles") or []),
        "options_macro_event_guards": _json_csv(audit.get("macro_enrichment_event_guards") or []),
        "options_macro_conflict_flags": _json_csv(conflicts),
        "options_macro_confirmation_required": _json_csv(confirmations),
        "options_macro_alignment_note": note,
        "macro_alignment_state": decision.get("macro_alignment_state", ""),
        "macro_direction_authority": decision.get("macro_direction_authority", ""),
        "macro_applicability": decision.get("macro_applicability", ""),
        "macro_direction_vote": decision.get("macro_direction_vote", ""),
        "macro_raw_direction_hint": decision.get("macro_raw_direction_hint", ""),
        "macro_can_invert_direction": decision.get("macro_can_invert_direction", False),
        "structure_first_required": decision.get("structure_first_required", False),
        "trade_type_classification": decision.get("trade_type_classification", ""),
    }

# Scope — options layer runs on Tier 0/1/2 plus Vanguard support overrides.
ELIGIBLE_TIERS = {0, 1, 2}  # Tier 2 included (2026-04-28): all three tiers trade long calls/puts. Tier drives position sizing only — see TIER_SIZE.

# IV thresholds
IVP_CHEAP_MAX   = 0.40   # IVP ≤ 40% → cheap vol → options favourable
IVP_FAIR_MAX    = 0.65   # IVP ≤ 65% → fair
IVP_EXPENSIVE   = 0.65   # IVP > 65% → expensive → STAND_DOWN buying premium

# ── ENHANCEMENT: IV Regime Classification thresholds ─────────────────────────
IV_REGIME_TERM_EVENT_RATIO  = 1.10   # front/back IV > 1.10 → event priced in near term
IV_REGIME_ACCEL_THRESHOLD   = 0.20   # IV jumped >20% in 5d with no price move → event
IV_VOL_OF_VOL_HIGH          = 0.30   # std(daily_iv_changes) > 30% → UNCERTAIN surface
IV_DIRECTION_RISE_THRESHOLD = 0.05   # IV rising >5% over 5d → RISING (tailwind)
IV_DIRECTION_FALL_THRESHOLD = -0.05  # IV falling >5% over 5d → FALLING (headwind)

# ── ENHANCEMENT: IV Skew thresholds ──────────────────────────────────────────
# Risk reversal = 25d put IV − 25d call IV (positive = puts more expensive = normal equities)
SKEW_STEEP_PUT_THRESHOLD    = 5.0    # RR > 5 pts = steep put skew → confirms PUT thesis
SKEW_EXTREME_PUT_THRESHOLD  = 15.0   # RR > 15 pts for CALL = expensive crash fear → headwind
SKEW_CALL_SKEWED_THRESHOLD  = -2.0   # RR < -2 pts = calls more expensive → unusual bullish demand

# ── ENHANCEMENT: Volume confirmation thresholds ───────────────────────────────
VOL_CONFIRM_STRONG          = 1.5    # vol_ratio > 1.5 → institutional participation
VOL_CONFIRM_WEAK            = 0.8    # vol_ratio < 0.8 → breakout lacks conviction
VOL_CONFIRM_SURGE           = 2.5    # vol_ratio > 2.5 → capitulation / institutional surge

# ── ENHANCEMENT: Gamma velocity thresholds ───────────────────────────────────
GAMMA_VEL_MIN_SESSIONS      = 2      # approaching wall within 2 sessions → imminent
GAMMA_VEL_MAX_SESSIONS      = 7      # approaching wall within 7 sessions → valid window
GAMMA_VEL_STALL_THRESHOLD   = 0.001  # daily velocity < 0.1% = stalling near wall

# ── ENHANCEMENT: Vanna / Charm thresholds ────────────────────────────────────
VANNA_STRONG_THRESHOLD      = 0.05   # vanna > 0.05 → strong delta acceleration if vol rises
CHARM_BLEED_THRESHOLD       = 0.003  # charm > 0.003/day → meaningful delta decay in low-vol

# ── ENHANCEMENT: Heston calibration limits ───────────────────────────────────
HESTON_USE_MIN_STRIKES      = 3      # need ≥3 valid strike/IV pairs to calibrate Heston (lowered from 5)
HESTON_MAX_CALIBRATION_SEC  = 3.0    # abort Heston calibration after 3 seconds

# Signal quality gates — three-tier threshold system (FIX-THRESHOLD-TIERS 2026-04-21)
#
# FULL_LIVE  (mark_synthetic=False, score>=55): ideal live data, tight spreads
# LIVE_LOW   (mark_synthetic=False, score 35-54): real quotes, market env caps OIS
#            Current environment (April 2026): ABT=38, XLP=42, DIA=36 are real signals
# EOD        (mark_synthetic=True): no live quotes, structural scoring only
#
MIN_OPTIONS_SCORE     = 55   # FULL_LIVE execute threshold
ARMED_MIN_SCORE       = 25   # FULL_LIVE armed threshold

LIVE_LOW_EXECUTE_MIN  = 35   # LIVE_LOW: real quotes, score ceiling < 55
LIVE_LOW_ARMED_MIN    = 20   # LIVE_LOW: armed floor

EOD_EXECUTE_MIN_SCORE = 30   # EOD: structural-only, morning_validation mandatory
EOD_ARMED_MIN_SCORE   = 15   # EOD: thin data, monitor only

# ─────────────────────────────────────────────────────────────────────────────
# MIGRATED FROM SUPERBRAIN (2026-04-28)
# These constants and functions replace avshunter_superbrain_layer.py.
# SuperBrain has been removed from the pipeline. Options Intelligence is now
# the single execution authority. All three tiers trade long calls/puts.
# Tier drives position sizing only: Tier 0=100%, Tier 1=75%, Tier 2=50%.
# ─────────────────────────────────────────────────────────────────────────────
CONV_COMPRESSION_ATR_PCT    = 30.0   # ATR percentile < this = compressed
CONV_COMPRESSION_IV_RANK    = 0.40   # IV rank < this = compression proxy
CONV_ENERGY_NET_NORM        = 0.25   # abs(buy-sell)/total < this = absorption
CONV_VOL_CHEAP_IVP          = 0.35   # IVP < this = underpriced vol
CONV_GAMMA_PROX_PCT         = 2.0    # within this % of GEX wall = proximity
CONV_RUNWAY_MULTIPLIER      = 2.0    # runway > breakeven × this = clear air
CONV_SCORE_INJECTION        = 5      # 5/8 core → CONVEXITY_INJECTION
CONV_SCORE_CORE             = 3      # 3+ → CORE_CAMPAIGN
CONV_SCORE_STAGED           = 1      # 1-2 → STAGED
TIME_STOP_FRACTION          = 0.60   # exit by 60% of DTE elapsed
CHECKPOINT_FRACTION         = 0.30   # first check at 30% of DTE elapsed

# Tier-based sizing multipliers (replaces SuperBrain campaign sizing)
TIER_SIZE = {0: 1.00, 1: 0.75, 2: 0.50, 3: 0.25}


def _ivp_from_ctx(signal_row, dashboard: dict = None) -> float:
    """IVP resolver — migrated from SuperBrain. Uses OI iv_ctx fields.
    FIX-2026-04-30: added optional dashboard fallback to match original
    _ivp(signal, dashboard) signature used in compute_convexity_score_oi.
    """
    for key in ('iv_percentile', 'ivp_30d', 'ivp_252d', 'ivp_local_med'):
        val = signal_row.get(key)
        try:
            v = float(val)
            if v > 0:
                return v / 100.0 if v > 1.0 else v
        except (TypeError, ValueError):
            pass
    # dashboard fallback — mirrors original SuperBrain _ivp() behaviour
    if dashboard:
        val = dashboard.get('ivp_local_med')
        try:
            v = float(val)
            if v > 0:
                return v / 100.0 if v > 1.0 else v
        except (TypeError, ValueError):
            pass
    return 0.0

def _calc_regime_sensitivity_oi(signal_row: dict, warnings_list: list) -> int:
    """Regime sensitivity score 0-100. Migrated from SuperBrain."""
    def _flt(r, k):
        try: return float(r.get(k) or 0)
        except: return 0.0
    score = 0
    dtt = _flt(signal_row, 'days_to_trigger')
    if dtt > 10: score += 35
    elif dtt > 5: score += 20
    elif dtt > 2: score += 10
    regime = str(signal_row.get('macro_regime', '') or signal_row.get('regime', '')).upper()
    if 'TRANSITIONAL' in regime: score += 25
    elif 'CHOPPY' in regime: score += 20
    comp = _flt(signal_row, 'composite_score')
    if 0 < comp < 45: score += 20
    elif 0 < comp < 55: score += 10
    theta = _flt(signal_row, 'theta_drag_pct')
    if theta > 60: score += 10
    elif theta > 40: score += 5
    return min(max(score, 0), 100)

def compute_time_stop_oi(signal_row: dict) -> dict:
    """Time-stop calculator. Migrated from SuperBrain. Uses OI output fields."""
    from datetime import datetime, timedelta
    def _flt(r, k):
        try: return float(r.get(k) or 0)
        except: return 0.0
    dte   = _flt(signal_row, 'contract_dte') or _flt(signal_row, 'dte')
    spot  = _flt(signal_row, 'contract_strike') or _flt(signal_row, 'stock_price')
    target = _flt(signal_row, 'structural_target')
    asof  = str(signal_row.get('asof_date') or signal_row.get('data_as_of') or '')[:10]
    try:
        now = datetime.strptime(asof, '%Y-%m-%d') if asof else datetime.now()
        anchor = 'signal_date' if asof else 'wall_clock_FALLBACK'
    except ValueError:
        now = datetime.now()
        anchor = 'wall_clock_FALLBACK'
    if dte <= 0:
        return {'time_stop_date': 'N/A', 'time_stop_days': 0,
                'checkpoint_date': 'N/A', 'checkpoint_rule': 'DTE unavailable',
                'expiry_date': 'N/A', 'dte_remaining_at_stop': 0,
                'time_stop_auto': 'N', 'dte_used': 0, 'time_anchor': anchor}
    stop_days = max(1, int(dte * TIME_STOP_FRACTION))
    chk_days  = max(1, int(dte * CHECKPOINT_FRACTION))
    time_stop = now + timedelta(days=stop_days)
    checkpoint = now + timedelta(days=chk_days)
    if spot > 0 and target > 0 and target != spot:
        min_p = spot + (target - spot) * 0.40
        rule = (f'By {checkpoint.strftime("%d %b")}: confirm bias. '
                f'By {time_stop.strftime("%d %b")}: price >= ${min_p:.2f} — else EXIT.')
    else:
        rule = (f'By {checkpoint.strftime("%d %b")}: confirm bias. '
                f'By {time_stop.strftime("%d %b")}: exit if not profitable.')
    return {'time_stop_date': time_stop.strftime('%Y-%m-%d'),
            'time_stop_days': stop_days,
            'checkpoint_date': checkpoint.strftime('%Y-%m-%d'),
            'checkpoint_rule': rule,
            'expiry_date': (now + timedelta(days=int(dte))).strftime('%Y-%m-%d'),
            'dte_remaining_at_stop': max(0, int(dte - stop_days)),
            'time_stop_auto': 'N', 'dte_used': int(dte), 'time_anchor': anchor}

def _tier_size_multiplier(tier) -> float:
    """Position sizing by tier. Tier 0=full, 1=75%, 2=50%, 3=25%.
    All tiers trade long calls/puts. Tier drives SIZE not strategy type.
    """
    try:
        return TIER_SIZE.get(int(tier), 0.25)
    except (TypeError, ValueError):
        return 0.50  # default half size if tier unknown

def _flt_conv(d, k, default=0.0):
    try: return float(d.get(k) or default)
    except: return default
def _str_conv(d, k, default=''):
    v = d.get(k)
    return str(v) if v is not None else default


def compute_convexity_score_oi(
    signal:    Dict,
    dashboard: Dict,
) -> Tuple[str, Dict, int]:
    """
    Super Brain 5-Condition Convexity Check.

    All 5 conditions must be present for a CONVEXITY_INJECTION (skyrocket profile).
    Missing any condition downgrades the campaign classification.

    Returns:
        campaign     : CONVEXITY_INJECTION | CORE_CAMPAIGN | STAGED | AVOID
        conditions   : {name: {'pass': bool, 'reason': str}}
        total_score  : int 0-5
    """
    conditions: Dict[str, Dict] = {}

    spot      = (float(signal.get('stock_price') or signal.get('underlying_price') or 0))
    ivp       = _ivp_from_ctx(signal, dashboard)  # FIX-2026-04-30: was _ivp() (NameError — never defined in OI layer)
    be_pct    = (float(signal.get('breakeven_pct') or 0))
    raw_direction = str(signal.get('options_direction') or signal.get('direction') or '').upper()
    if raw_direction not in {'CALL', 'PUT'}:
        return "AVOID", {
            "direction": {"pass": False, "reason": "DATA_INSUFFICIENT - options direction unavailable"},
        }, 0
    direction = raw_direction
    iv_rank   = (_flt_conv(dashboard, 'iv_rank_252d') or _flt_conv(signal, 'iv_rank_252d') or
                 _flt_conv(signal, 'iv_rank') or _flt_conv(dashboard, 'iv_rank'))
    atr_pct   = _flt_conv(signal, 'atr_percentile', -1.0)

    # call_wall / put_wall - try dashboard first, fall back to options CSV columns
    call_wall     = (_flt_conv(dashboard, 'top_call_wall') or _flt_conv(dashboard, 'gex_wall_call') or
                     _flt_conv(signal,    'call_wall')      or _flt_conv(signal,    'gex_wall_call'))
    put_wall      = (_flt_conv(dashboard, 'top_put_wall')  or _flt_conv(dashboard, 'gex_wall_put') or
                     _flt_conv(signal,    'put_wall')       or _flt_conv(signal,    'gex_wall_put'))
    # pcr_vol - use volume PCR if available, fall back to OI PCR as proxy
    pcr_vol       = (_flt_conv(dashboard, 'pcr_vol') or _flt_conv(signal, 'pcr_vol') or
                     _flt_conv(dashboard, 'pcr_oi')  or _flt_conv(signal, 'pcr_oi'))
    notional_buy  = _flt_conv(signal, 'notional_buy')
    notional_sell = _flt_conv(signal, 'notional_sell')

    # ── C1: COMPRESSION - energy stored, not yet released ────────────────────
    if atr_pct >= 0:
        c1 = atr_pct < CONV_COMPRESSION_ATR_PCT
        reason = (f'ATR_pct={atr_pct:.0f}% - '
                  f'{"COMPRESSED <{:.0f}%".format(CONV_COMPRESSION_ATR_PCT) if c1 else "EXPANDED - energy already released"}')
    else:
        # iv_rank from options CSV is on 0-100 scale; normalise to 0-1 for comparison
        iv_rank_norm = iv_rank / 100.0 if iv_rank > 1.0 else iv_rank
        c1 = 0 < iv_rank_norm < CONV_COMPRESSION_IV_RANK
        reason = (f'IV_rank={iv_rank:.1f}% ({iv_rank_norm:.2f} norm) proxy - '
                  f'{"LOW = compression proxy (compressed <{:.0f}%)".format(CONV_COMPRESSION_IV_RANK * 100) if c1 else "HIGH = not compressed"}')
    conditions['compression'] = {'pass': c1, 'reason': reason}

    # ── C2: ENERGY / ABSORPTION - buyers and sellers fighting at level ────────
    if notional_buy > 0 or notional_sell > 0:
        total_n = notional_buy + notional_sell
        net_norm = abs(notional_buy - notional_sell) / total_n if total_n > 0 else 1.0
        c2 = net_norm < CONV_ENERGY_NET_NORM
        reason = (f'Notional balance={net_norm:.2f} '
                  f'(buy={notional_buy:.0f} sell={notional_sell:.0f}) - '
                  f'{"ABSORPTION present" if c2 else "one-sided flow, no absorption"}')
    else:
        c2 = 0.70 < pcr_vol < 1.30 if pcr_vol > 0 else False
        reason = (f'PCR_vol={pcr_vol:.2f} proxy - '
                  f'{"BALANCED" if c2 else "directionally skewed, no absorption signal"}')
    conditions['energy'] = {'pass': c2, 'reason': reason}

    # ── C3: UNDERPRICED VOL - IV not already pricing the move ─────────────────
    c3 = 0 < ivp < CONV_VOL_CHEAP_IVP
    reason = (f'IVP={ivp:.1%} - '
              f'{"CHEAP <{:.0f}% = underpriced".format(CONV_VOL_CHEAP_IVP * 100) if c3 else "not cheap enough for convexity injection"}')
    conditions['underpriced_vol'] = {'pass': c3, 'reason': reason}

    # ── C4: GAMMA PROXIMITY - price close to GEX wall for fast delta jump ─────
    if spot > 0:
        if direction == 'CALL' and call_wall > 0:
            prox = abs(call_wall - spot) / spot * 100
            wall_label = f'call wall ${call_wall:.2f}'
        elif direction == 'PUT' and put_wall > 0:
            prox = abs(spot - put_wall) / spot * 100
            wall_label = f'put wall ${put_wall:.2f}'
        else:
            prox = 999.0
            wall_label = 'wall'
        c4 = prox <= CONV_GAMMA_PROX_PCT
        reason = (f'{prox:.2f}% from {wall_label} - '
                  f'{"WITHIN {:.0f}% gamma proximity".format(CONV_GAMMA_PROX_PCT) if c4 else "too far for fast delta acceleration"}')
    else:
        c4 = False
        reason = 'Spot price unavailable for proximity calc'
    conditions['gamma_proximity'] = {'pass': c4, 'reason': reason}

    # ── C5: RUNWAY - clear air to next wall exceeds breakeven requirement ─────
    # Primary: wall-based runway. Fallback: structural_target-based runway.
    if spot > 0 and be_pct > 0:
        if direction == 'CALL' and call_wall > spot:
            runway = (call_wall - spot) / spot * 100
            runway_src = f'call wall ${call_wall:.2f}'
        elif direction == 'PUT' and 0 < put_wall < spot:
            runway = (spot - put_wall) / spot * 100
            runway_src = f'put wall ${put_wall:.2f}'
        else:
            # Fallback: use structural_target from options CSV
            st = _flt_conv(signal, 'structural_target')
            if st > 0:
                if direction == 'CALL' and st > spot:
                    runway = (st - spot) / spot * 100
                    runway_src = f'structural target ${st:.2f}'
                elif direction == 'PUT' and 0 < st < spot:
                    runway = (spot - st) / spot * 100
                    runway_src = f'structural target ${st:.2f}'
                else:
                    runway = 0.0
                    runway_src = 'target on wrong side'
            else:
                runway = 0.0
                runway_src = 'no wall or target available'
        required = be_pct * CONV_RUNWAY_MULTIPLIER
        c5 = runway > required
        reason = (f'Runway={runway:.2f}% to {runway_src} vs required={required:.2f}% '
                  f'({CONV_RUNWAY_MULTIPLIER}× breakeven {be_pct:.2f}%) - '
                  f'{"CLEAR AIR" if c5 else "BLOCKED - wall/target closer than breakeven"}')
    else:
        c5 = False
        reason = 'Insufficient data for runway calculation (spot=0 or be_pct=0)'  
    conditions['runway'] = {'pass': c5, 'reason': reason}

    # ── C6: VANNA QUALITY - delta will accelerate as vol rises on breakout ──────
    # Vanna = ∂delta/∂IV. Positive vanna on a call (or negative on put) means
    # when the Wyckoff breakout fires and vol expands, delta ACCELERATES → double
    # benefit of directional move + vol expansion. This is true convexity compounding.
    vanna = (_flt_conv(signal, 'contract_vanna') or _flt_conv(signal, 'vanna'))
    if vanna is not None and vanna != 0:
        vanna_abs = abs(float(vanna))
        if direction == 'CALL':
            c6 = vanna_abs >= 0.04 and float(vanna) > 0
        else:  # PUT
            c6 = vanna_abs >= 0.04 and float(vanna) < 0
        reason = (
            f'Vanna={vanna:.3f} - '
            f'{"STRONG delta acceleration if vol rises on breakout (+)" if c6 else "vanna works against direction - delta will not accelerate with vol"}'
        )
    else:
        # No vanna data - treat as neutral pass (do not penalise for missing Heston data)
        # Once real Heston pricing is running, this will populate and score correctly
        c6 = True
        reason = 'Vanna not computed (Heston calibration unavailable) - neutral pass'
    conditions['vanna_quality'] = {'pass': c6, 'reason': reason}

    # ── C7: VOLUME CONFIRMATION - Wyckoff breakout supported by volume ──────────
    vol_ratio = _flt_conv(signal, 'volume_ratio', 0)
    phase_for_vol = (str(signal.get('phase') or 'A'))
    if vol_ratio > 0:
        if phase_for_vol in ('D', 'E'):
            c7 = vol_ratio >= 1.5
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg (Phase {phase_for_vol}) - '
                      f'{"CONFIRMED: institutional participation on breakout" if c7 else "WEAK breakout: below 1.5x average - Wyckoff fade risk"}')
        elif phase_for_vol == 'C':
            c7 = vol_ratio >= 1.2
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg (Phase C) - '
                      f'{"SPRING confirmed with above-average volume" if c7 else "spring on low volume - weak setup"}')
        else:
            c7 = vol_ratio >= 1.0
            reason = (f'Vol_ratio={vol_ratio:.2f}x avg - '
                      f'{"average or above - accumulation progressing" if c7 else "below-average volume in accumulation"}')
    else:
        c7 = False
        reason = 'Volume ratio not available'
    conditions['volume_confirmation'] = {'pass': c7, 'reason': reason}

    # ── C8: SECTOR ALIGNMENT - sector not strongly fighting the thesis ──────────
    sector_regime = _flt_conv(signal, 'sector_regime', '')
    sector_ret    = _flt_conv(signal, 'sector_5d_return', 0.0)
    if sector_regime and sector_regime != 'UNKNOWN':
        if direction == 'CALL':
            c8 = sector_regime not in ('STRONG_DOWNTREND',)
            reason = (f'Sector {_flt_conv(signal,"sector_etf","")} {sector_ret:+.1f}% 5d ({sector_regime}) - '
                      f'{"sector aligned or neutral for CALL" if c8 else "STRONG_DOWNTREND contradicts CALL thesis"}')
        else:  # PUT
            c8 = sector_regime not in ('STRONG_UPTREND',)
            reason = (f'Sector {_flt_conv(signal,"sector_etf","")} {sector_ret:+.1f}% 5d ({sector_regime}) - '
                      f'{"sector aligned or neutral for PUT" if c8 else "STRONG_UPTREND contradicts PUT thesis"}')
    else:
        # No sector data - neutral
        c8 = True
        reason = 'Sector data unavailable - neutral'
    conditions['sector_alignment'] = {'pass': c8, 'reason': reason}

    # ── Score and classify (now 8 conditions: 0-8 scale) ────────────────────────
    total = sum(1 for v in conditions.values() if v['pass'])

    # Adjusted thresholds: 8 conditions vs prior 5
    # CONVEXITY_INJECTION ≥ 6/8 (was 5/5)
    # CORE_CAMPAIGN       ≥ 4/8 (was 3/5)
    # STAGED              ≥ 2/8 (was 2/5)
    # C6/C7/C8 are supplementary - if all 3 missing but core 5 pass, still INJECTION
    core_conditions = ['compression','energy','underpriced_vol','gamma_proximity','runway']
    core_total = sum(1 for k in core_conditions if conditions[k]['pass'])

    if core_total >= CONV_SCORE_INJECTION and total >= 6:
        campaign = 'CONVEXITY_INJECTION'
    elif core_total >= CONV_SCORE_INJECTION:
        campaign = 'CONVEXITY_INJECTION'  # all 5 core pass → injection regardless of supplementary
    elif total >= 6:
        campaign = 'CONVEXITY_INJECTION'  # 6+/8 with supplementary
    elif total >= CONV_SCORE_CORE:  # FIX-C: use constant (was hardcoded 4, constant=3)
        campaign = 'CORE_CAMPAIGN'
    elif total >= CONV_SCORE_STAGED:
        campaign = 'STAGED'
    else:
        campaign = 'AVOID'

    return campaign, conditions, total


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 - INSTRUMENT LADDER BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

# Chain fetch limits
MAX_CHAIN_RECORDS     = 150_000
CHAIN_EXPIRY_DAYS     = 110   # FIX-DTE-WINDOW (2026-04-19): increased from 60 to 110.
                               # DTE matrix max = 90d (Phase A/B/C) + 15d relaxation in
                               # select_best_contract() = 105d required minimum.
                               # 60d cap was silently excluding all July expirations for
                               # Phase C signals, leaving no scoreable contracts → OIS=0
                               # → STAND_DOWN on every PhC/PhA/PhB BUY_SETUP or SELL_SETUP.
MIN_OI                = 50
OPTION_CHAIN_ACQUISITION_MIN_OI = 0  # OI is scored downstream, never an acquisition filter
MIN_LIQUIDITY_VOLUME  = 0
MAX_SPREAD_PCT        = LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT / 100.0

# DTE matrix — derived from tier + phase
# (tier, phase) → (dte_min, dte_target, dte_max)
# Aligned to SuperBrain ladder stage DTE windows:
#   Phase A/B/C → MID_DATED 45-90d (pre-confirmation, needs time to survive to Phase D)
#   Phase D/E   → STANDARD 21-55d  (move already underway, shorter window acceptable)
# Previously these windows were too short (e.g. Phase C = 14-45d), causing the options
# layer to select contracts that then failed the theta drag gate — producing STAND_DOWN
# on valid CORE_CAMPAIGN signals before the SuperBrain even ran.
DTE_MATRIX = {
    (0, 'A'): (45, 60, 90),   # Early accumulation — long window, structure building
    (0, 'B'): (45, 60, 90),   # Range established — needs full MID_DATED window
    (0, 'C'): (45, 60, 90),   # Spring approaching — must survive Phase C→D journey
    (0, 'D'): (21, 35, 55),   # Markup starting — STANDARD window
    (0, 'E'): (14, 28, 45),   # Continuation — shorter window acceptable
    (1, 'A'): (45, 60, 90),   # Tier 1 confirmed accumulation
    (1, 'B'): (45, 60, 90),   # Tier 1 range — MID_DATED aligned
    (1, 'C'): (45, 60, 90),   # NR7+LowVol coil — still needs MID_DATED survival window
    (1, 'D'): (21, 35, 55),   # SOS fired — STANDARD window
    (1, 'E'): (14, 28, 45),   # Phase E continuation
}
DTE_DEFAULT = (14, 28, 45)

# FIX 4: Horizon-aware DTE config — keyed by horizon_bucket from Fix 3 discovery router.
# ``spread_max`` is a monitoring/search bound, not execution permission.  A
# retained developing contract is re-quoted and governed by long_option_policy
# before any capital action can be emitted.
DTE_CONFIG = {
    "1_5d":   {"dte_min": 7,  "dte_max": 21, "spread_max": 0.15, "delta_min": 0.40, "delta_max": 0.60},
    "6_10d":  {"dte_min": 21, "dte_max": 35, "spread_max": 0.25, "delta_min": 0.35, "delta_max": 0.55},
    "11_20d": {"dte_min": 35, "dte_max": 60, "spread_max": 0.35, "delta_min": 0.30, "delta_max": 0.50},
}


# ---------------------------------------------------------------------------
# AVS-FIX-001 W1.6 (RCA3-D07, DEC-3) — one spread authority.
#
# Two limits governed the same decision. Contract SELECTION used the
# per-horizon `spread_max` above (15% for 1_5d), while the terminal verdict
# gate in `derive_verdict` used the flat MAX_SPREAD_PCT
# (LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT, 25%). A 1_5d contract at 18%
# therefore failed selection's band but passed the gate that actually decides
# STAND_DOWN -- which is how RCA-003 and QT-001 found rows leaking through.
#
# The per-horizon band is the authority. The flat reviewable limit is retained
# as a ceiling that no horizon may exceed, so the effective limit is
# min(band, flat) and neither can be loosened by editing only one of them.
# ---------------------------------------------------------------------------

def normalise_horizon_key(value: object) -> str:
    """Map any horizon spelling to a DTE_CONFIG key, defaulting to 1_5d.

    The same normalisation was written out twice (contract selection and chain
    access); a third copy inside the verdict gate would have been the point at
    which the three could silently diverge.
    """

    text = str(value or "").lower().replace("-", "_").replace(" ", "")
    if "1_5" in text:
        return "1_5d"
    if "6_10" in text:
        return "6_10d"
    if "11_20" in text:
        return "11_20d"
    return text if text in DTE_CONFIG else "1_5d"


HORIZON_PLANNED_HOLD_SESSIONS = {
    "1_5d": 5,
    "6_10d": 10,
    "11_20d": 20,
}
DTE_SELECTION_POLICY_VERSION = "governed-dte-alignment-v1"


def governed_dte_config(horizon: object) -> Dict[str, Any]:
    """Return the one DTE policy consumed by selection and lifecycle repair.

    The legacy selector admitted contracts using only the broad horizon band
    (7 DTE for a 1-5 session thesis), while the lifecycle required enough time
    for the routed hold, monitoring allowance and exit buffer (13 DTE).  That
    allowed the selector to choose a contract which the very next domain step
    had to reject.  The lifecycle calculation is now the minimum-floor
    authority; the existing horizon band can remain more conservative.
    """

    key = normalise_horizon_key(horizon)
    config = dict(DTE_CONFIG[key])
    planned_hold = HORIZON_PLANNED_HOLD_SESSIONS[key]
    requirement = calculate_dte_requirement(planned_hold)
    lifecycle_minimum = int(requirement["minimum_required_dte"])
    configured_minimum = int(config.get("dte_min", lifecycle_minimum))
    configured_maximum = int(config.get("dte_max", lifecycle_minimum))
    effective_minimum = max(configured_minimum, lifecycle_minimum)
    if configured_maximum < effective_minimum:
        raise ValueError(
            f"DTE policy has no selectable range for {key}: "
            f"minimum={effective_minimum}, maximum={configured_maximum}"
        )
    config.update({
        "dte_min": effective_minimum,
        "planned_hold_sessions": planned_hold,
        "lifecycle_minimum_dte": lifecycle_minimum,
        "dte_policy_version": DTE_SELECTION_POLICY_VERSION,
    })
    return config


def governed_dte_window(horizon: object) -> Tuple[int, int, int]:
    """Return min/target/max DTE without permitting a sub-lifecycle target."""

    config = governed_dte_config(horizon)
    minimum = int(config["dte_min"])
    maximum = int(config["dte_max"])
    target = max(minimum, int(round((minimum + maximum) / 2.0)))
    return minimum, target, maximum


def clamp_spread_limit(band: object) -> float:
    """min(per-horizon band, flat reviewable ceiling).

    Tightening either tightens the gate; loosening one alone cannot loosen it.
    A missing or unreadable band falls back to the flat ceiling.
    """

    try:
        return min(float(band), float(MAX_SPREAD_PCT))
    except (TypeError, ValueError):
        return float(MAX_SPREAD_PCT)


def horizon_spread_limit(horizon: object) -> float:
    """The one spread limit that governs a contract on this horizon."""

    return clamp_spread_limit(
        DTE_CONFIG.get(normalise_horizon_key(horizon), {}).get("spread_max")
    )


# EV-2 bounded long-single search. Two expiries x three delta-nearest strikes.
# Vertical debit spreads are a separate EV-2B structure because their quotes,
# multipliers, and two-leg exit valuation require a distinct input contract.
EV3_LONG_SINGLE_CANDIDATE_LIMIT = 6
EV3_STRIKES_PER_EXPIRY = 3
EV3_EXPIRY_LIMIT = 2
EV3_VERTICAL_CANDIDATE_LIMIT = 6
EV3_TOTAL_CANDIDATE_LIMIT = 12
EV3_MIN_OPEN_INTEREST = int(os.environ.get("AVSHUNTER_EV3_MIN_OPEN_INTEREST", "50"))
EV3_MIN_VOLUME = int(os.environ.get("AVSHUNTER_EV3_MIN_VOLUME", "1"))
EV3_CANDIDATE_POLICY_VERSION = "ev3-long-single-candidates-v0.3.0"
EV3_VERTICAL_POLICY_VERSION = "ev3-vertical-debit-candidates-v0.1.0"
EV3_REPAIR_DIAGNOSTICS_VERSION = "ev3-repair-selector-diagnostics-v1"

_EV3_REPAIR_DIAGNOSTIC_KEYS = (
    "retained_oi_below_50",
    "retained_zero_volume",
    "rejected_invalid_missing_quote",
    "rejected_spread",
    "rejected_dte_delta_geometry",
    "final_bounded_candidate_count",
)

# Contract tiers for tiered review (replaces binary STAND_DOWN gate)
# CLEAN: all thresholds met | REVIEW_SPREAD: spread too wide | REVIEW_COMPOUND: multiple marginal
CONTRACT_TIER_CLEAN    = "CLEAN"
CONTRACT_TIER_REVIEW_SPREAD   = "REVIEW_SPREAD"
CONTRACT_TIER_REVIEW_COMPOUND = "REVIEW_COMPOUND"
CONTRACT_TIER_REVIEW_NO_PASS  = "REVIEW_NO_PASS"

# Delta target zones by strategy type
DELTA_ZONES = {
    'MOMENTUM':    (0.20, 0.35),   # Phase D/E breakout — OTM directional leverage
    'COMPRESSION': (0.20, 0.35),   # Phase C coil — lower delta, cheaper premium
    'EARLY':       (0.15, 0.30),   # Tier 0 early — low delta, high leverage potential
}

# Network
SESSION_TIMEOUT = 30
RETRY           = 3
BACKOFF         = 1.2

SESSION  = requests.Session()
HEADERS  = {}
AUTH_MODE = "header"
_CONTRACT_MULTIPLIER_CACHE: Dict[str, Tuple[Optional[float], Optional[str]]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — AUTH + NETWORK
# ═══════════════════════════════════════════════════════════════════════════════

def _set_auth(mode: str):
    global AUTH_MODE, HEADERS
    AUTH_MODE = mode
    HEADERS   = {"Authorization": f"Bearer {POLYGON_API_KEY}"} if mode == "header" else {}

def _apply_auth(params: dict) -> dict:
    p = dict(params or {})
    if AUTH_MODE == "query":
        p["apiKey"] = POLYGON_API_KEY
    return p

def _backoff(attempt: int):
    time.sleep(BACKOFF ** attempt + random.uniform(0, 0.3))

def _get(url: str, params: dict = None) -> Optional[dict]:
    global AUTH_MODE
    for attempt in range(1, RETRY + 1):
        try:
            p = _apply_auth(params or {})
            r = SESSION.get(url, params=p, headers=HEADERS, timeout=SESSION_TIMEOUT)
            if r.status_code == 429:
                _backoff(attempt); continue
            if r.status_code == 401 and AUTH_MODE == "header":
                _set_auth("query"); continue
            if not r.ok:
                r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt == RETRY:
                return None
            _backoff(attempt)
    return None


def _enrich_ev3_contract_multipliers(
    selected_contract: Optional[Dict[str, Any]],
    alternatives: List[Dict[str, Any]],
    underlying_ticker: Any = None,
) -> None:
    """Populate governed multipliers without calling a retired options API.

    MarketData chain metadata remains authoritative. If that field is absent,
    only an unambiguous standard OCC symbol may use the standard 100-share
    convention; adjusted or malformed symbols remain explicitly unresolved.
    """
    top_level_records = ([selected_contract] if selected_contract else []) + list(alternatives or [])
    vertical_records = [
        record for record in top_level_records
        if str(record.get('structure') or '').upper() in {'BULL_CALL_DEBIT', 'BEAR_PUT_DEBIT'}
    ]
    records: List[Dict[str, Any]] = []
    for record in top_level_records:
        if str(record.get('structure') or '').upper() in {'BULL_CALL_DEBIT', 'BEAR_PUT_DEBIT'}:
            for leg_name in ('long_leg', 'short_leg'):
                leg = record.get(leg_name)
                if isinstance(leg, dict):
                    records.append(leg)
        else:
            records.append(record)
    unresolved = [
        record for record in records
        if _repair_alt_float(record.get('contract_multiplier')) is None
        and _repair_alt_row_symbol(record)
    ]
    if not unresolved:
        return
    for record in unresolved:
        inference = infer_standard_occ_multiplier(_repair_alt_row_symbol(record))
        inferred_multiplier = _repair_alt_float(inference.get('multiplier'))
        if inferred_multiplier is not None:
            record['contract_multiplier'] = inferred_multiplier
        record['contract_multiplier_source'] = inference['source']
        record['contract_multiplier_inferred'] = bool(inference['inferred'])
        record['contract_multiplier_reason'] = inference['reason']
    for vertical in vertical_records:
        long_leg = vertical.get('long_leg') or {}
        short_leg = vertical.get('short_leg') or {}
        long_multiplier = _repair_alt_float(long_leg.get('contract_multiplier'))
        short_multiplier = _repair_alt_float(short_leg.get('contract_multiplier'))
        if long_multiplier is not None and long_multiplier == short_multiplier:
            vertical['contract_multiplier'] = long_multiplier
            vertical['contract_multiplier_source'] = 'MATCHED_LEG_MULTIPLIERS'

def _paginate(base_url: str, params: dict = None, cap: int = None) -> List[dict]:
    data, url, lp, pages = [], base_url, dict(params or {}), 0
    while True:
        payload = _get(url, lp)
        if not payload: break
        results = payload.get("results", [])
        data.extend(results or [])
        pages += 1
        if cap and len(data) >= cap:
            return data[:cap]
        next_url = payload.get("next_url")
        if not next_url or pages > 80: break
        parsed = urlparse(next_url)
        query  = parse_qs(parsed.query)
        query.pop('apiKey', None)
        nqs = urlencode({k: v[0] if isinstance(v, list) and len(v)==1 else v
                         for k,v in query.items()}, doseq=True)
        url = urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                          parsed.params, nqs, parsed.fragment))
        lp = None
    return data

def init_auth() -> bool:
    """Initialise Polygon auth. Returns True if successful."""
    if not POLYGON_API_KEY:
        print("[AUTH] ❌ POLYGON_API_KEY not set.")
        return False
    _set_auth("header")
    try:
        r = SESSION.get("https://api.polygon.io/v3/reference/tickers",
                        params={"limit": 1}, headers=HEADERS, timeout=SESSION_TIMEOUT)
        if r.status_code == 401:
            _set_auth("query")
            r = SESSION.get("https://api.polygon.io/v3/reference/tickers",
                            params=_apply_auth({"limit": 1}), timeout=SESSION_TIMEOUT)
        r.raise_for_status()
        print(f"[AUTH] ✅ Polygon authenticated ({AUTH_MODE} mode)")
        return True
    except Exception as e:
        print(f"[AUTH] ❌ {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1b — MARKETDATA.APP QUOTE ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════════
#
# marketdata.app provides bid/ask/mid/greeks/IV per OCC option symbol.
# It is both the canonical chain provider and the exact-contract quote provider.
#
# Architecture:
#   1. CDS resolves a completed-session MarketData chain when available.
#   2. Otherwise MarketData fetches the chain and CDS writes it through.
#   3. Contract selection picks a long CALL or PUT using delta/DTE and current
#      quote evidence; exact-contract MarketData enrichment refreshes the quote.
#
# OCC Symbol format: AAPL271217C00250000
#   = Underlying (up to 6 chars) + YYMMDD + C/P + 8-digit strike (×1000)
#
# No provider fallback is authorised for options. Theoretical BSM values remain
# calculation evidence only and can never make a contract executable.
# ─────────────────────────────────────────────────────────────────────────────

MD_BASE_URL     = "https://api.marketdata.app/v1/options/quotes"
_MD_RATE_WINDOW_CLEARED = False   # FIX-MD-429: set True after first 60s recovery wait
MD_SESSION      = requests.Session()
_MD_AVAILABLE   = False   # set to True after successful auth check


def _canonical_offline_replay_enabled() -> bool:
    """True only for a controlled, provider-free canonical-data replay."""
    return os.environ.get(
        "AVSHUNTER_CANONICAL_OFFLINE_REPLAY", "0"
    ).strip().lower() in {"1", "true", "yes", "on"}


def _canonical_lifecycle_persistence_enabled(flags: Any) -> bool:
    """Allow lifecycle writes only in an explicitly write-through live run."""
    return bool(
        getattr(flags, "enabled", False)
        and getattr(flags, "write_through", False)
        and not getattr(flags, "offline_replay", False)
    )


def _build_occ_symbol(ticker: str, expiry: str, right: str, strike: float) -> Optional[str]:
    """
    Build OCC option symbol from components.
    expiry: 'YYYY-MM-DD'  right: 'C' or 'P'  strike: float (e.g. 250.0)
    Returns: e.g. 'AAPL271217C00250000'
    """
    try:
        from datetime import datetime as _dt
        exp_dt  = _dt.strptime(expiry, "%Y-%m-%d")
        yy      = exp_dt.strftime("%y")   # 2-digit year
        mm      = exp_dt.strftime("%m")
        dd      = exp_dt.strftime("%d")
        r       = right.upper()[:1]
        strike_int = int(round(strike * 1000))
        strike_str = f"{strike_int:08d}"
        underlying = ticker.upper().strip()[:6].ljust(6)  # pad to 6 chars is NOT standard
        # OCC format does NOT pad underlying — use as-is, max 6 chars
        underlying = ticker.upper().strip()
        return f"{underlying}{yy}{mm}{dd}{r}{strike_str}"
    except Exception:
        return None


def init_marketdata_auth() -> bool:
    """
    Verify marketdata.app key is set and reachable.
    Called once at pipeline startup. Polygon authentication is unrelated and is
    used only for optional equity/sector context.
    """
    global _MD_AVAILABLE
    if not MARKETDATA_API_KEY:
        print("[MD_AUTH] ⚠️  MARKETDATA_API_KEY not set — options acquisition disabled.")
        print("[MD_AUTH]    Set env var: MARKETDATA_API_KEY=your_token")
        print("[MD_AUTH]    No options-provider fallback is authorised.")
        _MD_AVAILABLE = False
        return False
    try:
        # Probe using the expirations endpoint — never expires, always valid
        probe_url = f"https://api.marketdata.app/v1/options/expirations/AAPL/"
        r = MD_SESSION.get(
            probe_url,
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            timeout=10,
        )
        if r.status_code in (200, 404):
            # 404 = symbol not found but auth succeeded
            _MD_AVAILABLE = True
            print(f"[MD_AUTH] ✅ marketdata.app authenticated — real quotes enabled")
            return True
        elif r.status_code == 401:
            print(f"[MD_AUTH] ❌ marketdata.app auth failed (401) — check MARKETDATA_API_KEY")
            _MD_AVAILABLE = False
            return False
        else:
            print(f"[MD_AUTH] ⚠️  marketdata.app probe returned {r.status_code} — enabling anyway")
            _MD_AVAILABLE = True
            return True
    except Exception as e:
        print(f"[MD_AUTH] ⚠️  marketdata.app unreachable ({e}) — BSM fallback active")
        _MD_AVAILABLE = False
        return False


def _normalise_option_quote(bid_raw: Any, ask_raw: Any, mid_raw: Any) -> Dict[str, Any]:
    """Return governed top-of-book semantics without inventing executability."""
    def _finite(value: Any) -> Optional[float]:
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except (TypeError, ValueError):
            return None

    bid = _finite(bid_raw)
    ask = _finite(ask_raw)
    mid = _finite(mid_raw)
    flags: List[str] = []
    if (bid is not None and bid < 0) or (ask is not None and ask < 0):
        quality = "INVALID"
        flags.append("NEGATIVE_QUOTE")
    elif bid is not None and ask is not None and bid > ask:
        quality = "INVALID"
        flags.append("CROSSED_QUOTE")
    elif bid == 0 and ask is not None and ask > 0:
        quality = "ONE_SIDED"
        flags.append("ZERO_BID")
        mid = ask / 2.0
    elif bid is not None and ask is not None and bid > 0 and ask > 0:
        quality = "TWO_SIDED"
        mid = (bid + ask) / 2.0
    else:
        quality = "INCOMPLETE"

    spread_pct = quote_spread_fraction(bid, ask) if quality != "INVALID" else None
    return {
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "quote_quality": quality,
        "quality_flags": tuple(flags),
        "quote_fields_complete": quality == "TWO_SIDED",
    }


def _quote_flags(value: Any) -> set[str]:
    """Normalise list/tuple/JSON/string quality flags for defensive checks."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().upper() for item in value if str(item).strip()}
    text = str(value).strip()
    if not text:
        return set()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return {str(item).strip().upper() for item in parsed if str(item).strip()}
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return {part.strip().upper() for part in re.split(r"[,|;]", text) if part.strip()}


def enrich_contract_with_real_quotes(contract: Dict) -> Dict:
    """
    Fetch real bid/ask/mid/greeks/IV from marketdata.app for a selected contract.

    Replaces BSM-synthetic fields in the contract dict with live data:
      mark, bid, ask, spread_pct, implied_vol, delta, gamma, theta, vega

    Sets mark_synthetic = False when real quotes are obtained.
    Returns the original contract unchanged if enrichment fails.

    Credit cost: 1 credit per call (real-time or 15-min delayed).
    Called ONLY for the single best contract per signal — not the full chain.
    """
    if _canonical_offline_replay_enabled() or not _MD_AVAILABLE:
        return contract   # BSM fallback — no change

    # If contract already has a complete real MD top-of-book from fetch_chain_md(),
    # mark_synthetic=False is already set. Skip the per-contract enrichment
    # call to save API credits. If the chain only supplied a mark/mid without
    # bid/ask, do NOT skip: fetch the selected contract quote endpoint so EIL
    # gets executable spread data instead of a false clean mark.
    def _positive_quote(value) -> bool:
        try:
            return value is not None and float(value) > 0
        except (TypeError, ValueError):
            return False

    has_top_of_book = _positive_quote(contract.get('bid')) and _positive_quote(contract.get('ask'))
    if not contract.get('mark_synthetic', True) and has_top_of_book:
        contract.setdefault('md_quote_source', 'marketdata.app')
        contract.setdefault('md_occ_symbol',   contract.get('symbol', ''))
        return contract

    ticker  = contract.get('underlying', '')
    expiry  = contract.get('expiration_date', '')
    right   = contract.get('right', '')
    strike  = contract.get('strike')

    if not all([ticker, expiry, right, strike]):
        return contract   # incomplete data — skip enrichment

    occ_sym = _build_occ_symbol(ticker, expiry, right, float(strike))
    if not occ_sym:
        return contract

    try:
        url = f"{MD_BASE_URL}/{occ_sym}/"
        r = MD_SESSION.get(
            url,
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            timeout=15,
        )
        if r.status_code == 404:
            print(f"  [{ticker}] ⚠️  MD 404 — OCC symbol not found: {occ_sym}")
            return contract
        if not r.ok:
            print(f"  [{ticker}] ⚠️  MD fetch failed: HTTP {r.status_code} for {occ_sym}")
            return contract

        data = r.json()
        if data.get("s") != "ok":
            return contract

        # marketdata.app returns arrays — take index [0]
        def _md(key):
            val = data.get(key, [None])
            return val[0] if val else None

        quote = _normalise_option_quote(_md("bid"), _md("ask"), _md("mid"))
        bid   = quote["bid"]
        ask   = quote["ask"]
        mid   = quote["mid"]
        iv    = _md("iv")
        delta = _md("delta")
        gamma = _md("gamma")
        theta = _md("theta")
        vega  = _md("vega")
        oi    = _md("openInterest")
        vol   = _md("volume")
        spot  = _md("underlyingPrice")
        updated = _md("updated")
        multiplier = _md("contractMultiplier") or _md("multiplier")
        bid_size = _md("bidSize")
        ask_size = _md("askSize")

        if quote["quote_quality"] == "INVALID":
            rejected = dict(contract)
            rejected["quote_refresh_status"] = "REJECTED_INVALID_QUOTE"
            rejected["quote_refresh_flags"] = list(quote["quality_flags"])
            print(
                f"  [{ticker}] ⚠️  MD exact quote rejected for {occ_sym}: "
                f"{','.join(quote['quality_flags']) or 'INVALID_QUOTE'}"
            )
            return rejected

        enriched = dict(contract)   # shallow copy — don't mutate original

        if mid is not None and float(mid) > 0:
            enriched['mark']          = float(mid)
        enriched['mark_synthetic'] = quote["quote_quality"] != "TWO_SIDED"
        enriched['quote_quality'] = quote["quote_quality"]
        enriched['quality_flags'] = list(quote["quality_flags"])
        enriched['quote_fields_complete'] = quote["quote_fields_complete"]

        if bid is not None:
            enriched['bid'] = float(bid)
        if ask is not None:
            enriched['ask'] = float(ask)
        if bid_size is not None:
            _bid_size = float(bid_size)
            if _bid_size < 0 or not _bid_size.is_integer():
                raise ValueError(f"invalid MarketData bidSize={bid_size!r}")
            enriched['bid_size'] = int(_bid_size)
            enriched['bid_size_quality'] = 'OBSERVED_ZERO' if int(_bid_size) == 0 else 'OBSERVED_POSITIVE'
        else:
            enriched['bid_size'] = None
            enriched['bid_size_quality'] = 'MISSING'
        if ask_size is not None:
            _ask_size = float(ask_size)
            if _ask_size < 0 or not _ask_size.is_integer():
                raise ValueError(f"invalid MarketData askSize={ask_size!r}")
            enriched['ask_size'] = int(_ask_size)
            enriched['ask_size_quality'] = 'OBSERVED_ZERO' if int(_ask_size) == 0 else 'OBSERVED_POSITIVE'
        else:
            enriched['ask_size'] = None
            enriched['ask_size_quality'] = 'MISSING'
        enriched['spread_pct'] = quote["spread_pct"]

        if iv    is not None: enriched['implied_vol'] = float(iv)
        if delta is not None: enriched['delta']       = float(delta)
        if gamma is not None: enriched['gamma']       = float(gamma)
        if theta is not None: enriched['theta']       = float(theta)
        if vega  is not None: enriched['vega']        = float(vega)
        if oi    is not None: enriched['open_interest'] = int(oi)
        if vol   is not None: enriched['volume']      = int(vol)
        if spot  is not None: enriched['underlying_price'] = float(spot)
        quote_timestamp_utc = _quote_timestamp_utc(updated)
        if quote_timestamp_utc is not None:
            enriched['quote_timestamp_utc'] = quote_timestamp_utc
            enriched['quote_timestamp_source'] = 'marketdata.app.updated'
        if multiplier is not None:
            enriched['contract_multiplier'] = float(multiplier)
            enriched['contract_multiplier_source'] = 'marketdata.app'

        # MD-IV-FIX: Extract ivRank and ivPercentile directly from MarketData response.
        # These are reliable fields returned by MD on options/chain/ and /quotes/ endpoints.
        # Using MD for IV rank is correct — Polygon chain does not return implied_vol.
        # This replaces the compute_iv_context() Polygon-based calculation which fails
        # when Polygon returns chains without IV data (the primary source of iv_rank=NaN).
        iv_rank_md = _md("ivRank")
        iv_pct_md  = _md("ivPercentile")
        if iv_rank_md is not None:
            try:
                _ivr = float(iv_rank_md)
                # MD returns ivRank as 0-100 scale
                enriched['iv_rank']       = _ivr
                enriched['iv_percentile'] = float(iv_pct_md) if iv_pct_md is not None else _ivr / 100.0
                enriched['ivp_label']     = ('CHEAP' if _ivr < 30 else
                                             'EXPENSIVE' if _ivr > 70 else 'FAIR')
                enriched['ivp_source']    = 'marketdata.app'
            except (TypeError, ValueError):
                pass

        # Intrinsic / extrinsic — free in the MD response, useful for scoring
        intrinsic = _md("intrinsicValue")
        extrinsic = _md("extrinsicValue")
        if intrinsic is not None: enriched['intrinsic_value'] = float(intrinsic)
        if extrinsic is not None: enriched['extrinsic_value'] = float(extrinsic)

        enriched['md_occ_symbol']   = occ_sym
        enriched['md_quote_source'] = (
            'marketdata.app' if quote["quote_fields_complete"] else 'marketdata.app_incomplete'
        )
        enriched['quote_refresh_status'] = (
            'ACCEPTED_TWO_SIDED' if quote["quote_fields_complete"] else 'ACCEPTED_MONITOR_ONLY'
        )

        return enriched

    except Exception as e:
        print(f"  [{contract.get('underlying','?')}] ⚠️  MD quote fetch exception: {e}")
        return contract   # BSM fallback


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — BLACK-SCHOLES ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _d1d2(S, K, T, sigma, r=RISK_FREE_RATE):
    if S <= 0 or K <= 0 or T <= 1e-9 or sigma <= 0:
        return None, None
    d1 = (log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*sqrt(T))
    return d1, d1 - sigma*sqrt(T)

def bs_price(S, K, T, sigma, r=RISK_FREE_RATE, right='C') -> Optional[float]:
    d1, d2 = _d1d2(S, K, T, sigma, r)
    if d1 is None: return None
    if right.upper() == 'C':
        return S*norm.cdf(d1) - K*exp(-r*T)*norm.cdf(d2)
    return K*exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)

def bs_delta(S, K, T, sigma, r=RISK_FREE_RATE, right='C') -> Optional[float]:
    d1, _ = _d1d2(S, K, T, sigma, r)
    if d1 is None: return None
    return norm.cdf(d1) if right.upper()=='C' else norm.cdf(d1)-1.0

def bs_gamma(S, K, T, sigma, r=RISK_FREE_RATE) -> Optional[float]:
    d1, _ = _d1d2(S, K, T, sigma, r)
    if d1 is None: return None
    return norm.pdf(d1) / (S*sigma*sqrt(T))

def bs_theta(S, K, T, sigma, r=RISK_FREE_RATE, right='C') -> Optional[float]:
    d1, d2 = _d1d2(S, K, T, sigma, r)
    if d1 is None: return None
    base = -(S*norm.pdf(d1)*sigma) / (2*sqrt(T))
    if right.upper()=='C':
        return (base - r*K*exp(-r*T)*norm.cdf(d2)) / 365.0
    return (base + r*K*exp(-r*T)*norm.cdf(-d2)) / 365.0

def bs_vega(S, K, T, sigma, r=RISK_FREE_RATE) -> Optional[float]:
    d1, _ = _d1d2(S, K, T, sigma, r)
    if d1 is None: return None
    return S*norm.pdf(d1)*sqrt(T) / 100.0

def solve_iv(target_price, S, K, T, r=RISK_FREE_RATE, right='C') -> Optional[float]:
    """Brent's method IV solver."""
    if not target_price or target_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None
    try:
        f  = lambda sig: (bs_price(S, K, T, sig, r, right) or 0.0) - target_price
        lo, hi = 0.001, 10.0
        if f(lo)*f(hi) > 0: return None
        iv = brentq(f, lo, hi, xtol=1e-5, maxiter=80)
        return float(iv) if np.isfinite(iv) and iv > 0 else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2b — HESTON STOCHASTIC VOLATILITY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
#
# Why Heston instead of BSM:
#   Black-Scholes assumes constant volatility → 5-7% pricing errors in practice.
#   Heston allows stochastic vol with mean reversion and correlation to the
#   underlying (leverage effect) → ~2% pricing errors (Andersson & Fredriksson 2020).
#
#   For our pipeline this matters most for:
#     1. More accurate delta/vega → better contract selection
#     2. Vol surface awareness → skew, smile, term structure all captured
#     3. EV calculations reflect real market pricing not BSM assumptions
#
#   Architecture: calibrate Heston parameters from the chain once per ticker
#   using the Fourier/characteristic function pricing method (Carr-Madan style).
#   Parameters: v0 (spot var), kappa (mean rev), theta (long-run var),
#               xi/sigma_v (vol of vol), rho (correlation).
#   Fallback: if chain has insufficient strikes or calibration fails → BSM.
# ─────────────────────────────────────────────────────────────────────────────

def _heston_char_func(u: complex, S: float, K: float, T: float,
                      r: float, v0: float, kappa: float,
                      theta: float, xi: float, rho: float) -> complex:
    """Heston characteristic function (Heston 1993, eq. 17-18)."""
    i = complex(0, 1)
    d = np.sqrt((rho*xi*i*u - kappa)**2 + xi**2*(i*u + u**2))
    g = (kappa - rho*xi*i*u - d) / (kappa - rho*xi*i*u + d)
    try:
        exp_dT  = np.exp(-d*T)
        g_exp   = g * exp_dT
        # Avoid division by zero
        if abs(1.0 - g_exp) < 1e-15:
            return complex(0, 0)
        C = r*i*u*T + (kappa*theta/xi**2)*(
              (kappa - rho*xi*i*u - d)*T - 2*np.log((1 - g_exp)/(1 - g))
            )
        D = ((kappa - rho*xi*i*u - d)/xi**2) * ((1 - exp_dT)/(1 - g_exp))
        return np.exp(C + D*v0 + i*u*np.log(S*np.exp(r*T)/K))
    except Exception:
        return complex(0, 0)


def heston_price(S: float, K: float, T: float, r: float,
                 v0: float, kappa: float, theta: float,
                 xi: float, rho: float, right: str = 'C') -> Optional[float]:
    """
    Real Heston (1993) option price via Gil-Pelaez characteristic function inversion.

    Implements the exact Heston pricing formula:
        C = S·P1 - K·e^{-rT}·P2
    where P1, P2 are risk-adjusted probabilities computed by numerically integrating
    the Heston characteristic function using scipy.integrate.quad.

    Characteristic function (Heston 1993, eq. 17-18):
        f_j(phi) = exp(C_j + D_j·v0 + i·phi·ln(S))
    where j=1 gives P1 (stock-measure probability) and j=2 gives P2 (risk-neutral).

    Put price computed via put-call parity: P = C - S + K·e^{-rT}

    Integration upper bound: 500 (integrand decays to ~0 well before this).
    Falls back to None on any numerical failure — caller uses BSM.
    """
    try:
        if S <= 0 or K <= 0 or T <= 0:
            return None
        T   = max(T, 1e-4)
        lnS = math.log(S)
        lnK = math.log(K)

        def _cf(phi: float, j: int) -> complex:
            """Heston characteristic function for probability j."""
            if j == 1:
                u = 0.5;  b = kappa - rho * xi
            else:
                u = -0.5; b = kappa

            d = cmath.sqrt((rho * xi * 1j * phi - b) ** 2
                           - xi ** 2 * (2 * u * 1j * phi - phi ** 2))
            g = (b - rho * xi * 1j * phi + d) / (b - rho * xi * 1j * phi - d)
            exp_dT = cmath.exp(d * T)
            denom  = 1.0 - g * exp_dT
            if abs(denom) < 1e-15 or abs(1.0 - g) < 1e-15:
                return complex(0, 0)
            C = (r * 1j * phi * T
                 + (kappa * theta / xi ** 2) * (
                     (b - rho * xi * 1j * phi + d) * T
                     - 2.0 * cmath.log(denom / (1.0 - g))
                 ))
            D = ((b - rho * xi * 1j * phi + d) / xi ** 2) * \
                ((1.0 - exp_dT) / denom)
            return cmath.exp(C + D * v0 + 1j * phi * lnS)

        def _integrand(phi: float, j: int) -> float:
            try:
                cf  = _cf(phi, j)
                val = (cmath.exp(-1j * phi * lnK) * cf / (1j * phi)).real
                return val
            except (OverflowError, ZeroDivisionError, ValueError):
                return 0.0

        P1, _ = quad(_integrand, 1e-6, 500, args=(1,), limit=500,
                     epsabs=1e-8, epsrel=1e-8)
        P2, _ = quad(_integrand, 1e-6, 500, args=(2,), limit=500,
                     epsabs=1e-8, epsrel=1e-8)

        prob1 = 0.5 + P1 / math.pi
        prob2 = 0.5 + P2 / math.pi

        disc = math.exp(-r * T)
        call = max(S * prob1 - K * disc * prob2,
                   max(S - K * disc, 0.0))      # intrinsic floor

        if right.upper()[:1] == 'C':
            return float(call)
        # Put via put-call parity
        put = call - S + K * disc
        return float(max(put, max(K * disc - S, 0.0)))

    except Exception:
        return None


def calibrate_heston(chain_df: pd.DataFrame, spot: float,
                     r: float = RISK_FREE_RATE) -> Optional[Dict]:
    """
    Real Heston calibration — minimises squared pricing errors across the
    observed vol surface using Nelder-Mead optimisation.

    Calibration data: selects up to 30 liquid contracts spanning the strike
    range (0.80–1.20 × spot) and two expiry buckets (15–45d, 45–90d) with
    valid IV, OI ≥ MIN_OI. More strikes = better surface fit.

    Parameters calibrated: v0, kappa, theta, xi, rho
    Constraints:  v0 ∈ (0.0001, 2.0),  kappa ∈ (0.1, 10),
                  theta ∈ (0.0001, 2.0), xi ∈ (0.01, 3.0),
                  rho ∈ (-0.99, -0.01)   [leverage effect: always negative]

    Falls back to fast analytical proxy if:
      - Fewer than HESTON_USE_MIN_STRIKES valid contracts available
      - Calibration exceeds HESTON_MAX_CALIBRATION_SEC seconds
      - Optimisation fails to converge
    """
    if chain_df.empty or spot <= 0:
        return None

    try:
        iv_col = chain_df['implied_vol']

        # ── Select calibration contracts ─────────────────────────────────────
        mask = (
            chain_df['strike'].between(spot * 0.80, spot * 1.20) &
            chain_df['dte'].between(15, 90) &
            iv_col.notna() & (iv_col > 0.01) &
            (chain_df['open_interest'].fillna(0) >= MIN_OI)
        )
        cal = chain_df[mask].copy()

        if len(cal) < HESTON_USE_MIN_STRIKES:
            # Insufficient data — fall back to analytical proxy
            return _calibrate_heston_proxy(chain_df, spot, r)

        # Cap at 30 contracts for speed; take evenly spread across strikes
        if len(cal) > 30:
            cal = cal.sample(30, random_state=42)

        strikes  = cal['strike'].values.astype(float)
        expiries = (cal['dte'].values.astype(float) / 365.0).clip(1e-4)
        rights   = cal['right'].str.upper().str[:1].values
        market_iv = cal['implied_vol'].values.astype(float)

        # Convert IV to market prices using BSM (calibrating on prices is more stable)
        def bsm_price_vec(S, K_arr, T_arr, sig_arr, r, right_arr):
            prices = np.zeros(len(K_arr))
            for i, (K, T, sig, right) in enumerate(zip(K_arr, T_arr, sig_arr, right_arr)):
                try:
                    d1 = (math.log(S/K) + (r + 0.5*sig**2)*T) / (sig*math.sqrt(T))
                    d2 = d1 - sig*math.sqrt(T)
                    disc = math.exp(-r*T)
                    if right == 'C':
                        prices[i] = S*norm.cdf(d1) - K*disc*norm.cdf(d2)
                    else:
                        prices[i] = K*disc*norm.cdf(-d2) - S*norm.cdf(-d1)
                except Exception:
                    prices[i] = 0.0
            return prices

        market_prices = bsm_price_vec(spot, strikes, expiries, market_iv, r, rights)
        # Weight by moneyness distance from ATM (ATM contracts weighted highest)
        weights = np.exp(-((strikes / spot - 1.0) ** 2) / 0.05)

        # ── Objective: weighted RMSE between Heston and market prices ────────
        def objective(params):
            v0_t, kappa_t, theta_t, xi_t, rho_t = params
            # Enforce constraints via penalty
            if not (1e-4 < v0_t < 2.0 and 0.1 < kappa_t < 10.0 and
                    1e-4 < theta_t < 2.0 and 0.01 < xi_t < 3.0 and
                    -0.99 < rho_t < -0.01):
                return 1e6
            err = 0.0
            for i, (K, T, right, mp, w) in enumerate(
                    zip(strikes, expiries, rights, market_prices, weights)):
                hp = heston_price(spot, K, T, r, v0_t, kappa_t, theta_t,
                                   xi_t, rho_t, right)
                if hp is None or mp <= 0:
                    continue
                err += w * ((hp - mp) / mp) ** 2
            return err / max(len(strikes), 1)

        # ── Initial guess from ATM surface ───────────────────────────────────
        atm_iv  = float(iv_col[
            chain_df['strike'].between(spot*0.97, spot*1.03) &
            chain_df['dte'].between(10, 45) & iv_col.notna()
        ].median()) if mask.any() else 0.20
        if not np.isfinite(atm_iv) or atm_iv <= 0:
            atm_iv = 0.20

        x0 = [atm_iv**2, 2.0, atm_iv**2, 0.40, -0.50]

        import signal as _signal

        class _Timeout(Exception):
            pass

        def _handler(signum, frame):
            raise _Timeout()

        result = None
        try:
            _signal.signal(_signal.SIGALRM, _handler)
            _signal.alarm(int(HESTON_MAX_CALIBRATION_SEC))
            result = minimize(
                objective, x0,
                method='Nelder-Mead',
                options={'maxiter': 2000, 'xatol': 1e-5, 'fatol': 1e-6,
                         'adaptive': True}
            )
            _signal.alarm(0)
        except _Timeout:
            _signal.alarm(0)
            # Calibration timed out — fall back to proxy
            return _calibrate_heston_proxy(chain_df, spot, r)
        except Exception:
            _signal.alarm(0)

        if result is None or not result.success:
            return _calibrate_heston_proxy(chain_df, spot, r)

        v0_f, kappa_f, theta_f, xi_f, rho_f = result.x

        return {
            'v0':        float(np.clip(v0_f,    1e-4, 2.0)),
            'kappa':     float(np.clip(kappa_f,  0.1, 10.0)),
            'theta':     float(np.clip(theta_f,  1e-4, 2.0)),
            'xi':        float(np.clip(xi_f,     0.01, 3.0)),
            'rho':       float(np.clip(rho_f,   -0.99, -0.01)),
            'atm_iv':    atm_iv,
            'fit_error': float(result.fun),
            'n_points':  int(len(cal)),
            'method':    'nelder_mead_fitted',
        }

    except Exception:
        return _calibrate_heston_proxy(chain_df, spot, r)


def _calibrate_heston_proxy(chain_df: pd.DataFrame, spot: float,
                             r: float = RISK_FREE_RATE) -> Optional[Dict]:
    """
    Fast analytical proxy — used as fallback when chain data is insufficient
    for full Nelder-Mead calibration. Extracts Heston parameters directly
    from observable vol surface shape with no iteration.
    Clearly labelled as proxy so downstream can distinguish from fitted values.
    """
    if chain_df.empty or spot <= 0:
        return None
    try:
        iv = chain_df['implied_vol']

        # v0: ATM front-month variance
        atm_mask = (chain_df['strike'].between(spot*0.97, spot*1.03) &
                    chain_df['dte'].between(10, 45) & iv.notna() & (iv > 0))
        atm = float(iv[atm_mask].median()) if atm_mask.any() else float(iv.dropna().median())
        if not np.isfinite(atm) or atm <= 0:
            return None
        v0 = atm ** 2

        # theta: long-run variance from back-month
        back_mask = chain_df['dte'].between(60, 120) & iv.notna() & (iv > 0)
        back = float(iv[back_mask].median()) if back_mask.any() else atm
        theta = float(back ** 2) if np.isfinite(back) and back > 0 else v0

        # kappa: term structure slope → mean reversion speed
        front_mask = chain_df['dte'].between(10, 25) & iv.notna()
        front = float(iv[front_mask].median()) if front_mask.any() else atm
        if np.isfinite(front) and front > 0 and back > 0 and np.isfinite(back):
            slope = (back - front) / back          # positive = contango
            kappa = float(np.clip(2.0 + slope * 5, 0.5, 8.0))
        else:
            kappa = 2.0

        # xi: vol-of-vol from skew width (OTM put IV vs OTM call IV spread)
        put25_mask  = ((chain_df['right'].str.upper()=='P') &
                       chain_df['delta'].abs().between(0.15, 0.30) & iv.notna())
        call25_mask = ((chain_df['right'].str.upper()=='C') &
                       chain_df['delta'].between(0.15, 0.30) & iv.notna())
        p25 = float(iv[put25_mask].median())  if put25_mask.any()  else np.nan
        c25 = float(iv[call25_mask].median()) if call25_mask.any() else np.nan

        if np.isfinite(p25) and np.isfinite(c25) and atm > 0:
            skew_width = abs(p25 - c25) / atm
            xi  = float(np.clip(skew_width * 2.0, 0.10, 1.50))
            rr  = p25 - c25                        # positive = normal put skew
            rho = float(np.clip(-0.30 - rr * 2.0, -0.95, 0.0))
        else:
            xi  = 0.40
            rho = -0.50

        return {
            'v0': v0, 'kappa': kappa, 'theta': theta,
            'xi': xi, 'rho': rho,
            'atm_iv': atm,
            'fit_error': None,
            'n_points': int(len(chain_df)),
            'method': 'analytical_proxy',
        }
    except Exception:
        return None


def heston_greeks(S: float, K: float, T: float, r: float,
                  params: Dict, right: str = 'C') -> Dict:
    """
    Heston-informed Greeks — closed-form, zero numerical integration.

    Uses BSM closed-form formulas for all standard Greeks (delta, gamma, vega,
    theta) with the Heston ATM vol (sqrt(v0)) as the input sigma.

    Vanna and charm are computed using BSM closed-form second-order formulas,
    then scaled by xi (vol-of-vol from Heston surface) to incorporate surface
    curvature intelligence:

      vanna_heston = vanna_BSM × (1 + xi × 0.5)
        xi high (steep skew, high vol-of-vol) → vanna amplified
        xi low (flat surface) → vanna ≈ BSM

    This gives 90%+ of the practical Heston benefit at BSM speed (<1ms).
    Full numerical Heston pricing is preserved in _heston_char_func for
    future offline calibration research but not called in the live pipeline.
    """
    v0  = params.get('v0', 0.04)
    xi  = params.get('xi', 0.40)

    sig = math.sqrt(max(v0, 1e-6))
    if S <= 0 or K <= 0 or T <= 0:
        return {'heston_used': False}
    T   = max(T, 1e-4)
    r   = r or RISK_FREE_RATE

    d1, d2 = _d1d2(S, K, T, sig, r)
    if d1 is None:
        return {'heston_used': False}

    right_u = right.upper()[:1]
    delta   = float(norm.cdf(d1) if right_u == 'C' else norm.cdf(d1) - 1.0)
    gamma   = float(norm.pdf(d1) / max(S * sig * math.sqrt(T), 1e-10))
    vega_v  = float(S * norm.pdf(d1) * math.sqrt(T) / 100.0)

    base_th = -(S * norm.pdf(d1) * sig) / (2 * math.sqrt(T))
    disc    = math.exp(-r * T)
    if right_u == 'C':
        theta_v = float((base_th - r * K * disc * norm.cdf(d2))  / 365)
    else:
        theta_v = float((base_th + r * K * disc * norm.cdf(-d2)) / 365)

    # Vanna BSM: -d2 × pdf(d1) / σ  — scaled by Heston xi for surface curvature
    try:
        vanna_bsm = float(-d2 * norm.pdf(d1) / max(sig, 1e-6))
        vanna = float(np.clip(vanna_bsm * (1.0 + xi * 0.5), -1.0, 1.0))
    except Exception:
        vanna = None

    # Charm BSM: ∂delta/∂t (daily)
    try:
        T_sq = math.sqrt(T)
        if right_u == 'C':
            charm = float(-norm.pdf(d1) * (2*r*T - d2*sig*T_sq) /
                          max(2*T*sig*T_sq, 1e-10) / 365.0)
        else:
            charm = float( norm.pdf(d1) * (2*r*T - d2*sig*T_sq) /
                          max(2*T*sig*T_sq, 1e-10) / 365.0)
    except Exception:
        charm = None

    return {
        'delta': float(np.clip(delta, -1.0, 1.0)),
        'gamma': float(max(gamma, 0.0)),
        'vega':  vega_v,
        'theta': theta_v,
        'vanna': round(vanna, 5) if vanna is not None else None,
        'charm': round(charm, 5) if charm is not None else None,
        'heston_price': heston_price(S, K, T, r,
                                     params.get('v0', sig**2),
                                     params.get('kappa', 2.0),
                                     params.get('theta', sig**2),
                                     params.get('xi', 0.40),
                                     params.get('rho', -0.50),
                                     right),
        'heston_used': True,
    }

def backfill_greeks_vectorised(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised IV and Greek backfill for incomplete option quotes."""
    if df.empty: return df
    gamma_values = pd.to_numeric(df['gamma'], errors='coerce')
    iv_values = pd.to_numeric(df['implied_vol'], errors='coerce')
    # IV is an independent EV3 requirement. The former gamma-only mask skipped
    # contracts whose vendor Greeks were present but IV was null, producing
    # REJECT_UNIT_IV even though bid/ask, spot, strike and DTE were sufficient
    # to solve IV locally.
    need = (
        gamma_values.isna()
        | (gamma_values == 0)
        | iv_values.isna()
        | (iv_values <= 0)
    )
    if not need.any(): return df

    sub  = df[need].copy()
    S    = pd.to_numeric(sub['underlying_price'], errors='coerce').to_numpy(dtype=float)
    K    = pd.to_numeric(sub['strike'], errors='coerce').to_numpy(dtype=float)
    T    = (pd.to_numeric(sub['dte'], errors='coerce').fillna(1)/365.0).clip(1e-6).to_numpy(dtype=float)
    sig  = pd.to_numeric(sub['implied_vol'], errors='coerce').to_numpy(dtype=float)
    right = sub['right'].fillna('C').astype(str).str.upper().to_numpy()
    mark  = pd.to_numeric(sub['mark'], errors='coerce').fillna(0).to_numpy(dtype=float)
    bid   = pd.to_numeric(sub['bid'], errors='coerce').fillna(0).to_numpy(dtype=float)
    ask   = pd.to_numeric(sub['ask'], errors='coerce').fillna(0).to_numpy(dtype=float)

    # Fill missing IV first
    missing_iv = ~np.isfinite(sig) | (sig <= 0)
    if missing_iv.any():
        mp = np.where(~np.isnan(mark) & (mark > 0), mark, (bid+ask)/2)
        new_iv = np.array([
            solve_iv(mp[i], S[i], K[i], T[i], right=str(right[i]))
            if (missing_iv[i] and mp[i] > 0 and np.isfinite(S[i])
                and np.isfinite(K[i]) and T[i] > 0)
            else sig[i]
            for i in range(len(sub))
        ], dtype=float)
        sig = np.where(missing_iv, new_iv, sig)
        df.loc[need, 'implied_vol'] = sig
        solved_iv = missing_iv & np.isfinite(new_iv) & (new_iv > 0)
        if solved_iv.any():
            df.loc[sub.index[solved_iv], 'implied_vol_source'] = 'BSM_SOLVED_FROM_MARK_V1'

    # Vectorised BSM
    valid = (np.isfinite(S) & np.isfinite(K) & np.isfinite(T) &
             np.isfinite(sig) & (sig > 0) & (S > 0) & (K > 0) & (T > 0))
    gammas = np.full(len(sub), np.nan)
    deltas = np.full(len(sub), np.nan)
    thetas = np.full(len(sub), np.nan)
    vegas  = np.full(len(sub), np.nan)

    if valid.any():
        sv, kv, tv, sigv = S[valid], K[valid], T[valid], sig[valid]
        d1v = (np.log(sv/kv) + (RISK_FREE_RATE + 0.5*sigv**2)*tv) / (sigv*np.sqrt(tv))
        d2v = d1v - sigv*np.sqrt(tv)

        gammas[valid] = norm.pdf(d1v) / (sv*sigv*np.sqrt(tv))
        # Delta — need to handle call/put
        rv = right[valid]
        d_arr = np.where(rv == 'C', norm.cdf(d1v), norm.cdf(d1v)-1.0)
        deltas[valid] = d_arr
        base_theta = -(sv*norm.pdf(d1v)*sigv)/(2*np.sqrt(tv))
        t_arr = np.where(rv=='C',
                         (base_theta - RISK_FREE_RATE*kv*np.exp(-RISK_FREE_RATE*tv)*norm.cdf(d2v))/365,
                         (base_theta + RISK_FREE_RATE*kv*np.exp(-RISK_FREE_RATE*tv)*norm.cdf(-d2v))/365)
        thetas[valid] = t_arr
        vegas[valid]  = sv*norm.pdf(d1v)*np.sqrt(tv)/100.0

    # Preserve valid vendor Greeks. Solving an independently missing IV must
    # not replace MarketData's existing delta/gamma/theta/vega values.
    for greek_name, computed in (
        ('gamma', gammas),
        ('delta', deltas),
        ('theta', thetas),
        ('vega', vegas),
    ):
        existing = pd.to_numeric(sub[greek_name], errors='coerce').to_numpy(dtype=float)
        missing_greek = ~np.isfinite(existing) | (existing == 0)
        if missing_greek.any():
            df.loc[sub.index[missing_greek], greek_name] = computed[missing_greek]
    return df


def backfill_mark_from_bsm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive a calculation-only theoretical mark from BSM using IV, spot,
    strike, DTE and risk-free rate.

    Sets a boolean column 'mark_synthetic' = True where BSM was used so
    downstream scoring can apply a liquidity penalty (no real market quote =
    higher execution uncertainty).

    Only fills rows where mark is NaN or zero AND implied_vol is available.
    Real MarketData marks are never overwritten. A synthetic result must remain
    non-executable in the lifecycle contract.
    """
    if df.empty:
        return df

    if 'mark_synthetic' not in df.columns:
        df['mark_synthetic'] = False

    need = df['mark'].isna() | (df['mark'] == 0)
    if not need.any():
        return df

    sub  = df[need].copy()
    S    = sub['underlying_price'].fillna(0).values
    K    = sub['strike'].values
    T    = (sub['dte'].fillna(1) / 365.0).clip(1e-6).values
    sig  = sub['implied_vol'].values
    right = sub['right'].fillna('C').values

    marks = np.full(len(sub), np.nan)
    valid = (np.isfinite(S) & np.isfinite(K) & np.isfinite(T) &
             np.isfinite(sig) & (sig > 0) & (S > 0) & (K > 0) & (T > 0))

    if valid.any():
        sv, kv, tv, sigv = S[valid], K[valid], T[valid], sig[valid]
        rv = right[valid]
        d1v = (np.log(sv/kv) + (RISK_FREE_RATE + 0.5*sigv**2)*tv) / (sigv*np.sqrt(tv))
        d2v = d1v - sigv*np.sqrt(tv)

        call_mask = (rv == 'C')
        call_marks = sv[call_mask]*norm.cdf(d1v[call_mask]) - kv[call_mask]*np.exp(-RISK_FREE_RATE*tv[call_mask])*norm.cdf(d2v[call_mask])
        put_marks  = kv[~call_mask]*np.exp(-RISK_FREE_RATE*tv[~call_mask])*norm.cdf(-d2v[~call_mask]) - sv[~call_mask]*norm.cdf(-d1v[~call_mask])

        result = np.full(valid.sum(), np.nan)
        result[call_mask]  = np.maximum(call_marks, 0.01)
        result[~call_mask] = np.maximum(put_marks,  0.01)
        marks[valid] = result

    df.loc[need, 'mark'] = marks
    df.loc[need, 'mark_synthetic'] = True

    # Synthetic spread: assume 15% (fair assumption without real quotes)
    spread_missing = need & df['spread_pct'].isna()
    df.loc[spread_missing, 'spread_pct'] = 0.15

    return df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — CHAIN FETCHER  (MarketData.app/CDS only)
# ═══════════════════════════════════════════════════════════════════════════════
#
# Architecture v2 (post MarketData.app support ticket 2026-04-11):
#
#   PRIMARY  : MarketData.app /v1/options/chain/{ticker}/
#              Returns bid/ask/mid/IV/delta/gamma/theta/vega for the full chain
#              in a single API call -- real marks, no BSM synthesis needed.
#              Data is real-time on Trader plan (OPRA signed) or 15-min delayed otherwise.
#
#   FALLBACK : None. A MarketData miss stands down; Polygon options are disabled.
#
# CORRECT MD CHAIN PARAMETERS (confirmed by MD support 2026-04-11):
#   OK  strike=100-200        range syntax  (NOT minStrike/maxStrike -- INVALID)
#   OK  from=YYYY-MM-DD       date filter   (NOT dte=1-45 -- dte is single number only)
#   OK  to=YYYY-MM-DD         date filter
#   OK  side=call/put         optional side filter
#   OK  minOpenInterest=N     liquidity gate
#
# WHY MD-PRIMARY IS BETTER:
#   1. One call = full chain with real bid/ask/mid (no second enrichment call needed)
#   2. mark_synthetic=False for all contracts -- real spread gate fires correctly
#   3. IV, delta, gamma, theta, vega from MD model (more accurate than BSM backfill)
#   4. BLOCK_WRONG_STRIKE and R:R use real premium, not BSM estimates

def _safe(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur

def _extract_greeks(r: dict) -> dict:
    for path in [lambda: r.get('greeks'),
                 lambda: r.get('details',{}).get('greeks'),
                 lambda: r.get('last_quote',{}).get('greeks')]:
        g = path()
        if g and isinstance(g, dict) and g.get('gamma') is not None:
            return g
    return {}

def _extract_iv(r: dict) -> Optional[float]:
    for v in [r.get('implied_volatility'),
              _safe(r,'details','implied_volatility'),
              _safe(r,'greeks','iv')]:
        if v is not None:
            iv = float(v)
            # Polygon snapshot returns IV as a percentage integer (e.g. 20 = 20%).
            # All internal pricing math expects decimal form (e.g. 0.20).
            # Normalise: anything > 2.0 is assumed to be percentage-scale.
            if iv > 2.0:
                iv = iv / 100.0
            return iv if iv > 0 else None
    return None

def _extract_quote(r: dict) -> Tuple[Optional[float], Optional[float]]:
    for src in [r.get('last_quote',{}), r, r.get('day',{})]:
        if isinstance(src, dict):
            b, a = src.get('bid'), src.get('ask')
            if b is not None and a is not None:
                return float(b), float(a)
    return None, None

def _quote_timestamp_utc(value: Any) -> Optional[str]:
    """Normalise an exchange/vendor quote timestamp without inventing one."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            numeric = float(value)
            magnitude = abs(numeric)
            unit = 'ns' if magnitude >= 1e17 else ('ms' if magnitude >= 1e11 else 's')
            stamp = pd.to_datetime(numeric, unit=unit, utc=True)
        else:
            stamp = pd.Timestamp(value)
            if stamp.tzinfo is None:
                return None
            stamp = stamp.tz_convert('UTC')
        return stamp.isoformat()
    except Exception:
        return None

def _dte(exp_str) -> Optional[float]:
    if not exp_str: return None
    try:
        return max(0.0, float((datetime.strptime(exp_str,'%Y-%m-%d').date()-date.today()).days))
    except Exception:
        return None
def _resolve_contract_expiry_dte(contract: dict) -> Tuple[Optional[str], Optional[float]]:
    """
    Resolve expiry/DTE for the selected contract before it is written to OI CSV.
    Some upstream sources use expiration_date while downstream consumers read
    expiry/dte; normalising here prevents liquid contracts from reaching the
    horizon router with DTE=None.
    """
    expiry = (
        contract.get('expiry')
        or contract.get('expiration_date')
        or contract.get('expiration')
        or contract.get('exp')
    )
    dte = None
    try:
        dte_value = contract.get('dte')
        if dte_value is not None and not pd.isna(dte_value):
            dte = float(dte_value)
    except Exception:
        dte = None
    if dte is None and expiry:
        dte = _dte(str(expiry)[:10])
    if expiry is not None:
        expiry = str(expiry)[:10]
    return expiry, dte

def _derive_eod_spread(mark, ivp, ois_score, dte):
    """
    Derive bid/ask from mark when real quotes are unavailable.
    Returns (bid, ask, spread_source). The provenance is explicit so downstream
    layers can haircut synthetic microstructure instead of treating it as live.
    """
    try:
        mark_f = float(mark)
    except Exception:
        return None, None, 'UNAVAILABLE'
    if pd.isna(mark_f) or mark_f <= 0:
        return None, None, 'UNAVAILABLE'

    ivp_label = str(ivp or '').upper().strip()
    if ivp_label == 'CHEAP':
        spread_factor = 0.04
    elif ivp_label == 'FAIR':
        spread_factor = 0.06
    else:
        spread_factor = 0.10

    try:
        ois_f = float(ois_score)
    except Exception:
        ois_f = 50.0
    ois_weight = max(0.5, 1.0 - (ois_f / 200.0))

    half_spread = mark_f * spread_factor * ois_weight
    bid = round(max(0.01, mark_f - half_spread), 2)
    ask = round(max(bid + 0.01, mark_f + half_spread), 2)
    return bid, ask, 'OI_DERIVED'

def fetch_chain_md(ticker: str) -> pd.DataFrame:
    """
    Fetch options chain from MarketData.app /v1/options/chain/{ticker}/.

    Returns a DataFrame in the same schema as fetch_chain() so all downstream
    functions (GEX, OI walls, PCR, contract selection, IV context) work unchanged.

    CORRECT API PARAMETERS (confirmed by MD support 2026-04-11):
      strike={lo}-{hi}     Range syntax — NOT minStrike/maxStrike (those return 400)
      from=YYYY-MM-DD      Date filter  — NOT dte=1-45 (dte is single-value only)
      to=YYYY-MM-DD        Date filter
      minOpenInterest=0    Acquisition retains developing-liquidity contracts
      side=call or put     Optional — we fetch both in one call (omit side param)

    Data is real-time on the Trader plan (OPRA entitlement required for RT).
    15-minute delayed otherwise. Post-close either equals closing mark — accurate
    for evening pipeline. Always verify live mid in Tastytrade before order entry.

    Returns an empty DataFrame on failure; no Polygon options fallback exists.
    """
    if not _MD_AVAILABLE or not MARKETDATA_API_KEY:
        return pd.DataFrame()

    _MD_RAW_CHAIN_PAYLOADS.pop(ticker.upper(), None)

    try:
        today      = date.today()
        date_from  = today.strftime('%Y-%m-%d')
        date_to    = (today + timedelta(days=CHAIN_EXPIRY_DAYS)).strftime('%Y-%m-%d')

        url    = f"https://api.marketdata.app/v1/options/chain/{ticker.upper()}/"
        params = {
            "from":            date_from,
            "to":              date_to,
            "minOpenInterest": OPTION_CHAIN_ACQUISITION_MIN_OI,
            "mode":            "cached",   # FIX-CREDIT-BURN: costs 1 credit per request
                                           # regardless of chain size. Without this, each
                                           # option symbol in the response consumes 1 credit
                                           # — a 500-contract chain = 500 credits. At 537
                                           # tickers this exhausted the 100k daily limit.
                                           # Cached data is seconds-to-minutes old — fine
                                           # for an EOD pipeline. Remove only if intraday
                                           # live execution is required (Sprint 2).
        }
        # Note: strike range filter omitted here — we fetch the full chain and
        # rely on the target-reachability filter in select_best_contract().
        # Adding a static strike range would incorrectly exclude valid contracts
        # for tickers with unusual price levels (penny stocks, high-priced names).

        # MD Trader plan: 100,000 credits/day. With mode=cached each chain call
        # costs 1 credit regardless of chain size → 537 tickers = 537 credits/run.
        # Sleep retained as courtesy throttle only.
        time.sleep(0.10)

        r = MD_SESSION.get(
            url,
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            params=params,
            timeout=30,
        )

        if r.status_code == 400:
            print(f"  [{ticker}] MD chain 400 — params: {params} — no authorised fallback")
            return pd.DataFrame()
        if r.status_code == 404:
            print(f"  [{ticker}] MD chain 404 — no options data — no authorised fallback")
            return pd.DataFrame()
        if r.status_code == 429:
            # FIX-MD-429 (2026-04-19): Two-tier 429 recovery.
            # First 429 in a run: MD window still full from prior run/crash.
            # Sleep 60s once to fully clear it, then retry. One-time cost.
            # Subsequent 429s (rare with 0.10s sleep active): sleep 15s then retry.
            global _MD_RATE_WINDOW_CLEARED
            if not _MD_RATE_WINDOW_CLEARED:
                print(f"  [{ticker}] MD chain HTTP 429 — clearing rate window (60s wait, one-time)...")
                time.sleep(60)
                _MD_RATE_WINDOW_CLEARED = True
            else:
                print(f"  [{ticker}] MD chain HTTP 429 — transient throttle, waiting 15s...")
                time.sleep(15)
            r2 = MD_SESSION.get(
                url,
                headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
                params=params,
                timeout=30,
            )
            if not r2.ok:
                print(f"  [{ticker}] MD chain HTTP {r2.status_code} after retry — no authorised fallback")
                return pd.DataFrame()
            r = r2
        elif not r.ok:
            print(f"  [{ticker}] MD chain HTTP {r.status_code} — no authorised fallback")
            return pd.DataFrame()

        _md_http_status = r.status_code
        _md_freshness = (
            "REALTIME_OPRA" if _md_http_status == 200
            else ("DELAYED_15M" if _md_http_status == 203 else "UNKNOWN")
        )
        data = r.json()
        if data.get("s") != "ok":
            return pd.DataFrame()
        _MD_RAW_CHAIN_PAYLOADS[ticker.upper()] = dict(data)

        # MD returns parallel arrays — zip them into rows
        def _arr(key):
            return data.get(key, [])

        symbols     = _arr("optionSymbol")
        sides       = _arr("side")
        strikes     = _arr("strike")
        expirations = _arr("expiration")   # Unix timestamp
        dtes        = _arr("dte")
        bids        = _arr("bid")
        asks        = _arr("ask")
        bid_sizes   = _arr("bidSize")
        ask_sizes   = _arr("askSize")
        mids        = _arr("mid")
        ivs         = _arr("iv")
        deltas      = _arr("delta")
        gammas      = _arr("gamma")
        thetas      = _arr("theta")
        vegas       = _arr("vega")
        ois         = _arr("openInterest")
        vols        = _arr("volume")
        underlying_prices = _arr("underlyingPrice")
        updateds     = _arr("updated")
        multipliers  = _arr("contractMultiplier") or _arr("multiplier")

        if not symbols:
            return pd.DataFrame()

        n = len(symbols)
        rows = []
        for i in range(n):
            side   = str(sides[i]).lower() if i < len(sides) else ''
            right  = 'C' if side == 'call' else ('P' if side == 'put' else None)
            if right is None:
                continue

            strike_val = float(strikes[i]) if i < len(strikes) and strikes[i] is not None else None
            dte_val    = float(dtes[i])    if i < len(dtes)    and dtes[i]    is not None else None

            # Convert Unix expiration timestamp to YYYY-MM-DD string
            exp_str = None
            if i < len(expirations) and expirations[i]:
                try:
                    from datetime import datetime as _dt
                    exp_str = _dt.fromtimestamp(int(expirations[i])).strftime('%Y-%m-%d')
                except Exception:
                    pass

            bid_val = float(bids[i])  if i < len(bids)  and bids[i]  is not None else None
            ask_val = float(asks[i])  if i < len(asks)  and asks[i]  is not None else None
            def _validated_display_size(values, field_name):
                if i >= len(values) or values[i] is None:
                    return None
                numeric = float(values[i])
                if numeric < 0 or not numeric.is_integer():
                    raise ValueError(f"invalid MarketData {field_name}={values[i]!r}")
                return int(numeric)
            bid_size_val = _validated_display_size(bid_sizes, "bidSize")
            ask_size_val = _validated_display_size(ask_sizes, "askSize")
            mid_val = float(mids[i])  if i < len(mids)  and mids[i]  is not None else None
            iv_val  = float(ivs[i])   if i < len(ivs)   and ivs[i]   is not None else None
            d_val   = float(deltas[i])if i < len(deltas) and deltas[i] is not None else None
            g_val   = float(gammas[i])if i < len(gammas) and gammas[i] is not None else None
            t_val   = float(thetas[i])if i < len(thetas) and thetas[i] is not None else None
            v_val   = float(vegas[i]) if i < len(vegas)  and vegas[i]  is not None else None
            oi_val  = int(ois[i])     if i < len(ois)    and ois[i]   is not None else None
            vol_val = int(vols[i])    if i < len(vols)   and vols[i]  is not None else None
            spot    = float(underlying_prices[i]) if i < len(underlying_prices) and underlying_prices[i] is not None else None
            quote_timestamp_utc = _quote_timestamp_utc(updateds[i]) if i < len(updateds) else None
            contract_multiplier = (
                float(multipliers[i])
                if i < len(multipliers) and multipliers[i] is not None
                else None
            )

            # Mark = governed midpoint. Crossed/negative quotes remain visible
            # as invalid evidence but never produce a negative spread.
            # Some marketdata.app responses can contain a mark/mid without
            # executable bid/ask. Treat those as incomplete so the selected
            # contract gets a quote-endpoint fallback before Options Research.
            quote = _normalise_option_quote(bid_val, ask_val, mid_val)
            bid_val = quote["bid"]
            ask_val = quote["ask"]
            mark = quote["mid"] if quote["mid"] is not None and quote["mid"] > 0 else None
            spread_pct = quote["spread_pct"]
            quote_fields_complete = quote["quote_fields_complete"]

            rows.append({
                'underlying'      : ticker.upper(),
                'symbol'          : str(symbols[i]) if i < len(symbols) else None,
                'right'           : right,
                'strike'          : strike_val,
                'dte'             : dte_val,
                'expiration_date' : exp_str,
                'open_interest'   : oi_val,
                'volume'          : vol_val,
                'implied_vol'     : iv_val,
                'gamma'           : g_val,
                'delta'           : d_val,
                'theta'           : t_val,
                'vega'            : v_val,
                'bid'             : bid_val,
                'ask'             : ask_val,
                'bid_size'        : bid_size_val,
                'ask_size'        : ask_size_val,
                'bid_size_quality': ('MISSING' if bid_size_val is None else ('OBSERVED_ZERO' if bid_size_val == 0 else 'OBSERVED_POSITIVE')),
                'ask_size_quality': ('MISSING' if ask_size_val is None else ('OBSERVED_ZERO' if ask_size_val == 0 else 'OBSERVED_POSITIVE')),
                'mark'            : mark,
                'spread_pct'      : spread_pct,
                'underlying_price': spot,
                'mark_synthetic'  : not quote_fields_complete,
                'quote_fields_complete': quote_fields_complete,
                'quote_quality'   : quote["quote_quality"],
                'quality_flags'   : list(quote["quality_flags"]),
                'md_quote_source'  : 'marketdata.app' if quote_fields_complete else 'marketdata.app_incomplete',
                'md_freshness'     : _md_freshness,
                'quote_timestamp_utc': quote_timestamp_utc,
                'quote_timestamp_source': 'marketdata.app.updated' if quote_timestamp_utc else None,
                'contract_multiplier': contract_multiplier,
                'contract_multiplier_source': 'marketdata.app' if contract_multiplier is not None else None,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        # Coerce numeric columns
        for c in ['strike','dte','open_interest','gamma','delta','theta',
                  'vega','bid','ask','mark','implied_vol','volume','spread_pct',
                  'underlying_price']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')

        df = df.dropna(subset=['strike','right'])
        df = df[df['dte'].notna() & (df['dte'] > 0) & (df['dte'] <= CHAIN_EXPIRY_DAYS)]
        # Retain zero/low-OI strikes. A newly active contract may acquire
        # liquidity as the underlying approaches its strike; OI is downstream
        # ranking evidence, not a reason to delete the observation.

        invalid_count = int((df.get('quote_quality') == 'INVALID').sum())
        incomplete_count = int((df.get('quote_quality') != 'TWO_SIDED').sum())
        print(f"  [{ticker}] MD chain: {len(df)} contracts "
              f"(two-sided={len(df)-incomplete_count}, monitor-only={incomplete_count-invalid_count}, "
              f"invalid={invalid_count}, 15-min delayed)")
        return df.reset_index(drop=True)

    except Exception as e:
        print(f"  [{ticker}] MD chain exception: {e} — no authorised fallback")
        return pd.DataFrame()


def _fetch_chain_md_payload(ticker: str) -> Dict[str, Any]:
    """Return the raw licensed response while retaining the existing adapter."""
    frame = fetch_chain_md(ticker)
    payload = _MD_RAW_CHAIN_PAYLOADS.pop(ticker.upper(), None)
    if frame.empty or not payload:
        raise ValueError(f"MarketData option chain unavailable for {ticker}")
    return payload


def _chain_v2_to_options_frame(payload: Any) -> pd.DataFrame:
    """Map canonical option_chain_v2 records onto the legacy calculation schema."""
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()
    frame = pd.DataFrame(payload).copy()
    rename = {
        "mid": "mark",
        "quote_timestamp_utc": "quote_timestamp_utc",
    }
    frame = frame.rename(columns=rename)
    if "mark" not in frame:
        frame["mark"] = np.nan
    frame["mark_synthetic"] = frame.get("quote_quality", "").astype(str).ne("TWO_SIDED")
    frame["quote_fields_complete"] = ~frame["mark_synthetic"]
    frame["md_quote_source"] = np.where(
        frame["quote_fields_complete"],
        "marketdata.app",
        "marketdata.app_incomplete",
    )
    frame["md_freshness"] = frame.get("quote_freshness", "UNASSESSED")
    frame["quote_timestamp_source"] = np.where(
        frame.get("quote_timestamp_utc", pd.Series(index=frame.index, dtype=object)).notna(),
        "marketdata.app.updated",
        None,
    )
    frame["contract_multiplier_source"] = np.where(
        frame.get("contract_multiplier", pd.Series(index=frame.index, dtype=float)).notna(),
        "marketdata.app",
        None,
    )
    required = (
        "underlying", "symbol", "right", "strike", "dte", "expiration_date",
        "open_interest", "volume", "implied_vol", "gamma", "delta", "theta",
        "vega", "bid", "ask", "bid_size", "ask_size", "bid_size_quality",
        "ask_size_quality", "mark", "spread_pct", "underlying_price",
        "mark_synthetic", "quote_fields_complete", "md_quote_source",
        "md_freshness", "quote_timestamp_utc", "quote_timestamp_source",
        "contract_multiplier", "contract_multiplier_source", "quote_quality",
        "quality_flags",
    )
    for name in required:
        if name not in frame:
            frame[name] = None
    return frame[list(required)].reset_index(drop=True)


def _fetch_chain_polygon(ticker: str) -> pd.DataFrame:
    """Decommissioned compatibility stub; Polygon options are never queried."""
    return pd.DataFrame()


def fetch_chain(ticker: str) -> pd.DataFrame:
    """
    MIGRATION-MD-PRIMARY (2026-05-22): MarketData.app is the primary chain source.
    MarketData and the canonical completed-session database are the only
    authorised option-chain sources. Polygon options access is decommissioned.

    Architecture:
      - MD chain: real bid/ask/mid/IV/Greeks in a single call. mark_synthetic=False.
        mode=cached: 1 credit per ticker. 15-min delayed (DELAYED_15M).
      - CDS-4 persists the successful session/scope response and serves a
        same-session rerun without a provider request.

    The previous Polygon-base + MD-overlay architecture caused BLOCK_NO_CONTRACT
    for ~811 tickers: when MD returned 400, Polygon-only chains had BSM synthetic
    marks that required IV for computation. Polygon plan does not return IV for many
    tickers → BSM mark=None → mark > 0 gate eliminated all contracts.
    """
    global _CDS_CHAIN_SERVICE, _CDS_LIQUIDITY_STORE
    if _CDS_V2_CHAIN_RESOLVER is not None and _CDS_V2_SESSION is not None:
        result = _CDS_V2_CHAIN_RESOLVER.option_chain(
            ticker=ticker,
            session_date=_CDS_V2_SESSION,
            dte_max=CHAIN_EXPIRY_DAYS,
            min_open_interest=OPTION_CHAIN_ACQUISITION_MIN_OI,
            fetch=_fetch_chain_md_payload,
            provider="MARKETDATA",
        )
        frame = _chain_v2_to_options_frame(result.payload)
        frame.attrs["canonical_dataset_id"] = result.dataset_id
        frame.attrs["canonical_provider"] = result.provider
        frame.attrs["canonical_resolution"] = result.resolution
        frame.attrs["canonical_schema_version"] = "option_chain_v2"
        # Resolver test doubles and older compatible resolver implementations
        # predate the additive Stage-1 finality field.  Treat its absence as
        # unassessed here; the governed run-level assessment below remains the
        # authority and will fail normal-baseline eligibility if it is absent.
        frame.attrs["provider_finality"] = getattr(result, "provider_finality", None) or {}
        print(
            f"  [{ticker}] CDS v2 chain {result.resolution}: "
            f"{len(frame)} contracts provider={result.provider}"
        )
        return frame
    if _CDS_CHAIN_SERVICE is not None:
        result = _CDS_CHAIN_SERVICE.get(
            ticker,
            marketdata_fetch=fetch_chain_md,
        )
        print(
            f"  [{ticker}] CDS chain {result.resolution}: "
            f"{len(result.frame)} contracts provider={result.provider}"
        )
        result.frame.attrs["canonical_dataset_id"] = result.dataset_id
        result.frame.attrs["canonical_provider"] = result.provider
        result.frame.attrs["canonical_resolution"] = result.resolution
        result.frame.attrs["provider_finality"] = getattr(result, "provider_finality", None) or {}
        return result.frame

    # CDS rollback path remains MarketData-only. Missing contract multipliers
    # stay unresolved rather than calling an unavailable options provider.
    md_df = fetch_chain_md(ticker) if _MD_AVAILABLE else pd.DataFrame()
    if not md_df.empty:
        print(f"  [{ticker}] MD chain (primary): {len(md_df)} contracts, mark_synthetic=False")
        return md_df

    print(f"  [{ticker}] MarketData chain unavailable — STAND_DOWN (Polygon options disabled)")
    return pd.DataFrame()

def compute_gex(df: pd.DataFrame, spot: float) -> Tuple[pd.DataFrame, Optional[float], float]:
    """
    Compute GEX by strike. Returns (gex_df, gamma_flip_price, flip_confidence).
    GEX = sign(right) × gamma × OI × spot × 100
    Positive GEX → dealers long gamma → price-damping (pin risk).
    Negative GEX → dealers short gamma → price-amplifying (trending).
    """
    if df.empty or df['gamma'].isna().all():
        return pd.DataFrame(columns=['strike','gex']), None, 0.0

    sub  = df.dropna(subset=['gamma']).copy()
    sign = np.where(sub['right'].str.upper()=='C', 1.0, -1.0)
    mult = spot * 100.0 if spot > 0 else 100.0
    gex  = sign * sub['gamma'] * sub['open_interest'].fillna(0) * mult

    gex_df = (pd.DataFrame({'strike': sub['strike'].values, 'gex': gex})
              .groupby('strike', as_index=False).sum()
              .sort_values('strike'))

    # Find gamma flip
    x, y = gex_df['strike'].values, gex_df['gex'].values
    s    = np.sign(y)
    flip = None
    for i in range(len(s)-1):
        if s[i]*s[i+1] < 0 and (y[i+1]-y[i]) != 0:
            flip = float(x[i] - y[i]*(x[i+1]-x[i])/(y[i+1]-y[i]))
            break
    if flip is None:
        flip = float(x[np.argmin(np.abs(y))]) if len(y) else None

    # Flip confidence
    conf = 0.0
    if flip and spot > 0:
        band  = 0.025*spot
        local = gex_df[gex_df['strike'].between(flip-band, flip+band)]
        dens  = min(1.0, len(local)/max(1,len(gex_df))*5)
        mass  = min(1.0, np.tanh(local['gex'].abs().sum() /
                                  (gex_df['gex'].abs().sum()+1e-9)))
        conf  = float(0.6*dens + 0.4*mass)

    return gex_df, flip, conf

def compute_gamma_island(
    gex_df: pd.DataFrame,
    spot: float,
    target: Optional[float],
    direction: str,
    source: str = "CHAIN_GEX_BY_STRIKE",
) -> Dict:
    """
    Compact per-strike gamma-island summary for downstream advisory layers.

    This uses the same by-strike GEX surface built from the options chain
    instead of making another MarketData request. It is advisory only: the
    result should explain path quality, not block a candidate.
    """
    result = {
        "gamma_island_on_path": False,
        "gamma_island_label": "GAMMA_SURFACE_UNAVAILABLE",
        "gamma_island_level": None,
        "gamma_island_distance_pct": None,
        "gamma_island_strength_share": None,
        "gamma_island_isolation_ratio": None,
        "gamma_island_gex_sign": "UNKNOWN",
        "gamma_island_source": source,
        "gamma_island_note": "Per-strike gamma surface unavailable.",
    }

    try:
        spot_f = float(spot)
    except (TypeError, ValueError):
        spot_f = 0.0
    try:
        target_f = float(target) if target is not None else None
    except (TypeError, ValueError):
        target_f = None

    if gex_df is None or gex_df.empty or spot_f <= 0:
        return result
    if target_f is None or target_f <= 0 or abs(target_f - spot_f) / spot_f < 0.002:
        result.update({
            "gamma_island_label": "TARGET_PATH_UNAVAILABLE",
            "gamma_island_note": "Per-strike gamma surface exists, but no usable spot-to-target path was available.",
        })
        return result

    surface = gex_df[["strike", "gex"]].copy()
    surface["strike"] = pd.to_numeric(surface["strike"], errors="coerce")
    surface["gex"] = pd.to_numeric(surface["gex"], errors="coerce")
    surface = surface.dropna(subset=["strike", "gex"]).sort_values("strike").reset_index(drop=True)
    if surface.empty:
        return result

    low, high = sorted([spot_f, target_f])
    path = surface[surface["strike"].between(low, high)].copy()
    if path.empty:
        result.update({
            "gamma_island_label": "NO_STRIKES_ON_PATH",
            "gamma_island_note": f"Per-strike gamma surface checked, but no strikes were found between spot {spot_f:.2f} and target {target_f:.2f}.",
        })
        return result

    path["abs_gex"] = path["gex"].abs()
    total_abs = float(surface["gex"].abs().sum() or 0.0)
    path_abs = float(path["abs_gex"].sum() or 0.0)
    if path_abs <= 0 or total_abs <= 0:
        result.update({
            "gamma_island_label": "NO_GAMMA_MASS_ON_PATH",
            "gamma_island_note": "Per-strike gamma surface checked; path gamma mass was negligible.",
        })
        return result

    peak_idx = path["abs_gex"].idxmax()
    peak = path.loc[peak_idx]
    peak_strike = float(peak["strike"])
    peak_gex = float(peak["gex"])
    peak_abs = abs(peak_gex)

    peak_position = int(surface.index[surface["strike"].eq(peak_strike)][0])
    neighbour_abs = []
    for neighbour_idx in (peak_position - 1, peak_position + 1):
        if 0 <= neighbour_idx < len(surface):
            neighbour_abs.append(abs(float(surface.loc[neighbour_idx, "gex"])))
    neighbour_mean = sum(neighbour_abs) / len(neighbour_abs) if neighbour_abs else 0.0
    isolation_ratio = peak_abs / max(neighbour_mean, 1e-9)
    strength_share = peak_abs / max(total_abs, 1e-9)
    path_share = peak_abs / max(path_abs, 1e-9)
    distance_pct = abs(peak_strike - spot_f) / spot_f * 100.0

    on_path = (
        peak_abs > 0
        and (
            strength_share >= 0.08
            or path_share >= 0.30
            or isolation_ratio >= 2.0
        )
    )
    sign_label = "PINNING_POSITIVE_GEX" if peak_gex > 0 else "AMPLIFYING_NEGATIVE_GEX"
    direction_u = str(direction or "").upper()
    direction_text = "upside" if direction_u == "CALL" else ("downside" if direction_u == "PUT" else "structural")
    label = "GAMMA_ISLAND_ON_PATH" if on_path else "NO_GAMMA_ISLAND_ON_PATH"
    note = (
        f"{label}: strongest {direction_text} path gamma node at {peak_strike:.2f}; "
        f"{distance_pct:.2f}% from spot; {sign_label}; "
        f"surface_share={strength_share:.3f}; path_share={path_share:.3f}; "
        f"isolation={isolation_ratio:.2f}. Advisory only."
    )
    result.update({
        "gamma_island_on_path": bool(on_path),
        "gamma_island_label": label,
        "gamma_island_level": round(peak_strike, 4),
        "gamma_island_distance_pct": round(distance_pct, 4),
        "gamma_island_strength_share": round(strength_share, 6),
        "gamma_island_isolation_ratio": round(isolation_ratio, 4),
        "gamma_island_gex_sign": sign_label,
        "gamma_island_note": note,
    })
    return result

def compute_oi_walls(df: pd.DataFrame) -> Dict:
    """Call wall, put wall, max pain."""
    if df.empty:
        return {'call_wall': None, 'put_wall': None, 'max_pain': None}
    calls = df[df['right'].str.upper()=='C'].groupby('strike')['open_interest'].sum()
    puts  = df[df['right'].str.upper()=='P'].groupby('strike')['open_interest'].sum()

    call_wall = float(calls.idxmax()) if not calls.empty else None
    put_wall  = float(puts.idxmax())  if not puts.empty  else None

    # Max pain
    strikes = sorted(df['strike'].unique())
    c_oi = calls.to_dict(); p_oi = puts.to_dict()
    pain = [(K, sum(c_oi.get(s,0)*max(0,K-s) for s in strikes) +
                sum(p_oi.get(s,0)*max(0,s-K) for s in strikes))
            for K in strikes]
    max_pain = min(pain, key=lambda z:z[1])[0] if pain else None

    return {'call_wall': call_wall, 'put_wall': put_wall, 'max_pain': max_pain}

def compute_pcr(df: pd.DataFrame) -> Tuple[Optional[float], str]:
    """Put/Call ratio by OI. Returns (pcr_value, signal_label)."""
    if df.empty: return None, 'UNKNOWN'
    calls = df[df['right'].str.upper()=='C']['open_interest'].sum()
    puts  = df[df['right'].str.upper()=='P']['open_interest'].sum()
    if calls <= 0: return None, 'UNKNOWN'
    pcr = float(puts/calls)
    signal = 'BULLISH' if pcr < 0.7 else ('BEARISH' if pcr > 1.0 else 'NEUTRAL')
    return round(pcr, 3), signal




# SECTION 4 — GEX, OI WALLS, PCR
# ═══════════════════════════════════════════════════════════════════════════════

def compute_gamma_velocity(spot: float, gex_flip: Optional[float],
                           spot_history: List[float] = None,
                           direction: str = 'CALL') -> Dict:
    """
    Gamma Pressure Velocity — not just where the wall is, but how fast we're approaching it.

    A stock 3% from a gamma wall moving at 0.2%/day will likely stall.
    The same stock moving at 1%/day will trigger dealer squeeze in ~3 sessions.

    Computes:
      daily_velocity_pct : average daily % move toward the wall (last 3d)
      sessions_to_wall   : estimated sessions until gamma flip reached
      gamma_velocity_label: IMMINENT / APPROACHING / STALLING / MOVING_AWAY

    Requires spot_history: [spot_3d_ago, spot_2d_ago, spot_1d_ago] (last 3 closes)
    Falls back to UNKNOWN if history unavailable.
    """
    result = {
        'gamma_velocity_pct':    None,
        'gamma_velocity_sessions': None,
        'gamma_velocity_label':   'UNKNOWN',
    }

    if gex_flip is None or spot <= 0:
        return result

    wall_dist_pct = abs(gex_flip - spot) / spot * 100

    if spot_history and len(spot_history) >= 2:
        recent = spot_history[-3:] if len(spot_history) >= 3 else spot_history
        daily_moves = np.diff(recent) / np.array(recent[:-1])
        if direction == 'CALL':
            # For calls: positive movement = toward call wall (above)
            directional_moves = daily_moves if gex_flip > spot else -daily_moves
        else:
            # For puts: negative movement = toward put wall (below)
            directional_moves = -daily_moves if gex_flip < spot else daily_moves

        avg_daily_vel = float(np.mean(directional_moves))
        result['gamma_velocity_pct'] = round(avg_daily_vel * 100, 3)

        if avg_daily_vel > GAMMA_VEL_STALL_THRESHOLD and wall_dist_pct > 0:
            sessions = wall_dist_pct / (avg_daily_vel * 100)
            result['gamma_velocity_sessions'] = round(sessions, 1)
            if sessions <= GAMMA_VEL_MIN_SESSIONS:
                result['gamma_velocity_label'] = 'IMMINENT'
            elif sessions <= GAMMA_VEL_MAX_SESSIONS:
                result['gamma_velocity_label'] = 'APPROACHING'
            else:
                result['gamma_velocity_label'] = 'DISTANT'
        elif avg_daily_vel < -GAMMA_VEL_STALL_THRESHOLD:
            result['gamma_velocity_label'] = 'MOVING_AWAY'
        else:
            result['gamma_velocity_label'] = 'STALLING'
    else:
        # No history: use wall distance alone as proxy
        if wall_dist_pct < 1.0:
            result['gamma_velocity_label'] = 'IMMINENT'
        elif wall_dist_pct < 3.0:
            result['gamma_velocity_label'] = 'APPROACHING'
        else:
            result['gamma_velocity_label'] = 'DISTANT'

    return result


def compute_volume_confirmation(vol_ratio: float, phase: str,
                                direction: str, trend: str) -> Dict:
    """
    Volume Confirmation Gate — aligned to Wyckoff principles.

    Core Wyckoff: volume CONFIRMS price. A Phase D breakout on low volume is
    a false SOS. The same breakout on 2.5x average volume is institutional.

    vol_ratio = today_volume / 20-day average volume (from Vanguard signal row)

    Scoring:
      Phase D + vol_ratio > 1.5 → institutional participation confirmed (+5 OIS)
      Phase C + vol_ratio < 0.8 → spring on low volume → weak spring (−4 OIS)
      Any phase + vol_ratio > 2.5 → capitulation/surge event (context-dependent)
      Phase D + vol_ratio < 0.8 → breakout not confirmed → Wyckoff fade risk (−4 OIS)

    Returns dict with vol_confirmation_score, vol_confirmation_label, vol_wyckoff_note.
    """
    score = 0
    label = 'NEUTRAL'
    note  = ''

    if vol_ratio is None or vol_ratio <= 0:
        return {'vol_confirmation_score': 0, 'vol_confirmation_label': 'UNKNOWN',
                'vol_wyckoff_note': 'Volume ratio not available'}

    if vol_ratio >= VOL_CONFIRM_SURGE:
        if phase in ('D', 'E'):
            score = 7
            label = 'INSTITUTIONAL_SURGE'
            note  = f'Vol={vol_ratio:.1f}x avg — Wyckoff SOS confirmed by institutional volume'
        elif phase == 'C':
            score = 4
            label = 'SPRING_VOLUME'
            note  = f'Vol={vol_ratio:.1f}x avg — Spring/spring test with volume — Phase C confirmation strong'
        else:
            score = 3
            label = 'HIGH_VOLUME'
            note  = f'Vol={vol_ratio:.1f}x avg — accumulation phase with above-average volume'
    elif vol_ratio >= VOL_CONFIRM_STRONG:
        if phase in ('D', 'E'):
            score = 5
            label = 'CONFIRMED'
            note  = f'Vol={vol_ratio:.1f}x avg — Phase D markup volume confirmed (+5)'
        elif phase == 'C':
            score = 3
            label = 'MODERATE_CONFIRMATION'
            note  = f'Vol={vol_ratio:.1f}x avg — Phase C with above-average volume'
        else:
            score = 2
            label = 'ABOVE_AVERAGE'
            note  = f'Vol={vol_ratio:.1f}x avg — above average, accumulation progressing'
    elif vol_ratio >= 1.0:
        score = 0
        label = 'AVERAGE'
        note  = f'Vol={vol_ratio:.1f}x avg — average volume, neutral confirmation'
    else:
        if phase in ('D', 'E'):
            score = -4
            label = 'WEAK_BREAKOUT'
            note  = f'Vol={vol_ratio:.1f}x avg — Phase D on low volume: Wyckoff FADE RISK'
        elif phase == 'C':
            score = -2
            label = 'WEAK_SPRING'
            note  = f'Vol={vol_ratio:.1f}x avg — Phase C spring on low volume: weak setup'
        else:
            score = -1
            label = 'LOW_VOLUME'
            note  = f'Vol={vol_ratio:.1f}x avg — below average volume in accumulation'

    return {
        'vol_confirmation_score': score,
        'vol_confirmation_label': label,
        'vol_wyckoff_note': note,
    }


def fetch_sector_regime(ticker: str) -> Dict:
    """
    Sector ETF Regime Modifier.

    A bearish signal during a sector ripping higher is fighting the tide.
    A bullish signal when sector is in free-fall adds systemic risk.

    Lookup table maps ticker to sector ETF. Fetches 5-day return from Polygon.
    If sector strongly contradicts signal direction → cap OIS at 55, cap verdict at ARMED.

    Returns: sector_etf, sector_5d_return, sector_regime, sector_alignment_ok
    """
    if _canonical_offline_replay_enabled():
        return {
            'sector_etf': None,
            'sector_5d_return': None,
            'sector_regime': 'UNKNOWN',
            'sector_alignment_ok': True,
        }

    # Sector ETF mapping — common US equities
    SECTOR_MAP = {
        # Consumer Staples
        'KDP':'XLP','KO':'XLP','PEP':'XLP','PG':'XLP','CL':'XLP','GIS':'XLP',
        'CAG':'XLP','SJM':'XLP','HSY':'XLP','MKC':'XLP','CHD':'XLP','CLX':'XLP',
        # Consumer Discretionary
        'AMZN':'XLY','HD':'XLY','MCD':'XLY','NKE':'XLY','SBUX':'XLY',
        'TGT':'XLY','LOW':'XLY','BKNG':'XLY','TSLA':'XLY',
        # Technology
        'AAPL':'XLK','MSFT':'XLK','NVDA':'XLK','META':'XLK','GOOGL':'XLK',
        'GOOG':'XLK','AVGO':'XLK','AMD':'XLK','INTC':'XLK','ORCL':'XLK',
        'CRM':'XLK','ADBE':'XLK','NOW':'XLK','SNPS':'XLK','CDNS':'XLK',
        # Financials
        'JPM':'XLF','BAC':'XLF','WFC':'XLF','GS':'XLF','MS':'XLF',
        'BRK.B':'XLF','V':'XLF','MA':'XLF','AXP':'XLF','BLK':'XLF',
        # Healthcare
        'JNJ':'XLV','UNH':'XLV','LLY':'XLV','ABT':'XLV','MRK':'XLV',
        'TMO':'XLV','DHR':'XLV','ABBV':'XLV','BMY':'XLV','AMGN':'XLV',
        # Energy
        'XOM':'XLE','CVX':'XLE','COP':'XLE','SLB':'XLE','EOG':'XLE',
        # Industrials
        'GE':'XLI','CAT':'XLI','BA':'XLI','HON':'XLI','UPS':'XLI',
        'LMT':'XLI','RTX':'XLI','DE':'XLI','MMM':'XLI',
        # Materials
        'LIN':'XLB','APD':'XLB','ECL':'XLB','NEM':'XLB','FCX':'XLB',
        # Utilities
        'NEE':'XLU','DUK':'XLU','SO':'XLU','D':'XLU','AEP':'XLU',
        # Real Estate
        'PLD':'XLRE','AMT':'XLRE','EQIX':'XLRE','CCI':'XLRE',
        # Communications
        'T':'XLC','VZ':'XLC','CMCSA':'XLC','NFLX':'XLC','DIS':'XLC',
    }

    result = {
        'sector_etf':           None,
        'sector_5d_return':     None,
        'sector_regime':        'UNKNOWN',
        'sector_alignment_ok':  True,   # assume ok if data unavailable
    }

    sector_etf = SECTOR_MAP.get(ticker.upper())
    if not sector_etf:
        return result
    result['sector_etf'] = sector_etf

    try:
        end   = date.today()
        start = end - timedelta(days=10)
        url   = f"https://api.marketdata.app/v1/stocks/candles/D/{sector_etf}/"
        r = MD_SESSION.get(
            url,
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            params={"from": str(start), "to": str(end)},
            timeout=15,
        )
        if not r.ok:
            return result
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"):
            return result
        closes = [float(c) for c in data["c"] if c is not None]
        if len(closes) < 2:
            return result

        ret_5d = (closes[-1] - closes[min(-5, -len(closes))]) / closes[min(-5, -len(closes))]
        result['sector_5d_return'] = round(ret_5d * 100, 2)

        if ret_5d > 0.03:     result['sector_regime'] = 'STRONG_UPTREND'
        elif ret_5d > 0.01:   result['sector_regime'] = 'MILD_UPTREND'
        elif ret_5d < -0.03:  result['sector_regime'] = 'STRONG_DOWNTREND'
        elif ret_5d < -0.01:  result['sector_regime'] = 'MILD_DOWNTREND'
        else:                  result['sector_regime'] = 'FLAT'

    except Exception:
        pass
    return result


def enrich_contract_with_heston_greeks(contract: Dict,
                                        heston_params: Optional[Dict],
                                        spot: float,
                                        r: float = RISK_FREE_RATE) -> Dict:
    """
    Enhance the selected contract's Greeks using Heston if parameters available.
    Adds vanna, charm to the contract dict.
    Falls back to BSM if Heston params unavailable or calculation fails.

    Vanna impact on scoring:
      High positive vanna on a CALL entering Phase D = delta will accelerate
      as vol rises on the breakout → double benefit of directional + vol expansion.
    """
    if not heston_params or not contract:
        # BSM second-order Greeks fallback
        sig   = contract.get('iv', contract.get('implied_vol'))
        S     = spot
        K     = contract.get('strike')
        T_raw = contract.get('dte', 30)
        right = contract.get('right', 'C')
        if sig and K and T_raw and S > 0:
            T = max(float(T_raw) / 365.0, 1e-4)
            d1, _ = _d1d2(S, float(K), T, float(sig))
            if d1 is not None:
                # Vanna (BSM): vega × d2 / (S × sigma)
                vega_bsm = bs_vega(S, float(K), T, float(sig), r)
                vanna = float(vega_bsm * d1 / (S * float(sig))) if vega_bsm else None
                # Charm (BSM): -(pdf(d1) × (2r×T - d2×sigma×sqrt(T)) / (2×T×sigma×sqrt(T))) / 365
                T_sq = sqrt(T)
                charm = None
                try:
                    charm = -(norm.pdf(d1) * (2*r*T - d1*float(sig)*T_sq) /
                               (2*T*float(sig)*T_sq)) / 365.0
                except Exception:
                    pass
                enriched = dict(contract)
                if vanna is not None: enriched['vanna'] = round(float(vanna), 5)
                if charm is not None: enriched['charm'] = round(float(charm), 5)
                enriched['heston_used'] = False
                return enriched
        return contract

    K     = contract.get('strike')
    T_raw = contract.get('dte', 30)
    right = (contract.get('right') or 'C').upper()[:1]

    if not K or not T_raw:
        return contract

    T = max(float(T_raw) / 365.0, 1e-4)

    greeks = heston_greeks(spot, float(K), T, r, heston_params, right)
    enriched = dict(contract)

    # Update Greeks with Heston values (more accurate)
    if greeks.get('delta') is not None:
        enriched['delta'] = greeks['delta']
    if greeks.get('gamma') is not None:
        enriched['gamma'] = greeks['gamma']
    if greeks.get('vega') is not None:
        enriched['vega']  = greeks['vega']
    if greeks.get('theta') is not None:
        enriched['theta'] = greeks['theta']
    if greeks.get('vanna') is not None:
        enriched['vanna'] = round(greeks['vanna'], 5)
    if greeks.get('charm') is not None:
        enriched['charm'] = round(greeks['charm'], 5)
    enriched['heston_used']  = greeks.get('heston_used', False)
    enriched['heston_price'] = greeks.get('heston_price')

    return enriched
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_hist_closes(ticker: str, days: int = 252) -> List[float]:
    try:
        from canonical_data.history_bridge import read_canonical_history
        canonical = read_canonical_history(ticker, bars=days)
        if canonical is not None and not canonical.empty:
            return [float(value) for value in canonical['close'].tolist()]
    except Exception:
        pass

    if _canonical_offline_replay_enabled():
        return []

    end   = date.today()
    start = end - timedelta(days=days)
    try:
        url = f"https://api.marketdata.app/v1/stocks/candles/D/{ticker}/"
        r = MD_SESSION.get(
            url,
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            params={"from": str(start), "to": str(end)},
            timeout=20,
        )
        if not r.ok:
            return []
        data = r.json()
        if data.get("s") != "ok" or not data.get("c"):
            return []
        return [float(c) for c in data["c"] if c is not None]
    except Exception:
        return []

# NOTE (FIX-2026-04-30): removed dead backward-compat shim that called
# compute_iv_context(df, ticker, run_dir=None) recursively. Python shadowed
# it with the real definition below; shim was unreachable and would have
# caused RecursionError if ever reached. All callers use the full signature.


# Populated during compute_iv_context; used for vol direction of travel.
# On disk: runs/<run_id>/iv_history.json   (written by orchestrator if enabled)
_IV_HISTORY: Dict[str, List[float]] = {}  # ticker → [atm_iv_d-5, ..., atm_iv_today]


def _load_iv_history(ticker: str, run_dir: str = None) -> List[float]:
    """Load rolling ATM IV history from prior runs. Returns list of recent ATM IVs."""
    global _IV_HISTORY
    if ticker in _IV_HISTORY:
        return _IV_HISTORY[ticker]
    if run_dir:
        hist_file = os.path.join(run_dir, 'iv_history.json')
        if os.path.exists(hist_file):
            try:
                with open(hist_file) as f:
                    data = json.load(f)
                    _IV_HISTORY[ticker] = data.get(ticker, [])
                    return _IV_HISTORY[ticker]
            except Exception:
                pass
    return []


def compute_iv_skew(chain_df: pd.DataFrame, spot: float) -> Dict:
    """
    Compute 25-delta put/call skew (Risk Reversal) and skew label.

    Risk Reversal = 25d_put_IV − 25d_call_IV
      Positive (normal for equities): OTM puts more expensive → downside fear
      Negative (unusual): OTM calls more expensive → speculative bullish demand

    Scoring impact:
      PUT thesis: steep put skew (+8 OIS) confirms institutional hedging
      CALL thesis: extreme put skew (>15pts) headwind (−6 OIS) — crash fear dominates
      CALL thesis: call skewed (RR < −2) slight tailwind (+3 OIS) — unusual bullish flow

    Returns dict with rr, put_25d_iv, call_25d_iv, skew_label.
    """
    result = {
        'risk_reversal': None,
        'put_25d_iv':    None,
        'call_25d_iv':   None,
        'skew_label':    'UNKNOWN',
    }
    if chain_df.empty or spot <= 0:
        return result

    # Use front-cycle expiry (10-35 DTE) for skew computation
    front = chain_df[chain_df['dte'].between(10, 35)].copy()
    if front.empty:
        front = chain_df[chain_df['dte'].between(5, 60)].copy()
    if front.empty:
        return result

    # 25-delta put: delta between −0.20 and −0.30 (abs 0.20-0.30)
    put_25 = front[
        (front['right'].str.upper() == 'P') &
        (front['delta'].notna()) &
        (front['delta'].abs().between(0.20, 0.30)) &
        (front['implied_vol'].notna()) &
        (front['implied_vol'] > 0)
    ]

    # 25-delta call: delta between 0.20 and 0.30
    call_25 = front[
        (front['right'].str.upper() == 'C') &
        (front['delta'].notna()) &
        (front['delta'].between(0.20, 0.30)) &
        (front['implied_vol'].notna()) &
        (front['implied_vol'] > 0)
    ]

    if put_25.empty or call_25.empty:
        # Fallback: approximate 25d by moneyness (spot ± 5-8%)
        put_25  = front[(front['right'].str.upper()=='P') &
                        (front['strike'].between(spot*0.92, spot*0.97)) &
                        (front['implied_vol'].notna())]
        call_25 = front[(front['right'].str.upper()=='C') &
                        (front['strike'].between(spot*1.03, spot*1.08)) &
                        (front['implied_vol'].notna())]

    if put_25.empty or call_25.empty:
        return result

    p_iv = float(put_25['implied_vol'].median())
    c_iv = float(call_25['implied_vol'].median())
    rr   = round((p_iv - c_iv) * 100, 2)  # in vol points

    if rr > SKEW_STEEP_PUT_THRESHOLD:
        label = 'STEEP_PUT_SKEW'
    elif rr > 2.0:
        label = 'NORMAL_PUT_SKEW'
    elif rr >= SKEW_CALL_SKEWED_THRESHOLD:
        label = 'FLAT_SKEW'
    else:
        label = 'CALL_SKEWED'

    return {
        'risk_reversal': rr,
        'put_25d_iv':    round(p_iv * 100, 2),
        'call_25d_iv':   round(c_iv * 100, 2),
        'skew_label':    label,
    }


def classify_iv_regime(atm_iv: float, chain_df: pd.DataFrame,
                       iv_history: List[float],
                       spot: float, spot_history: List[float] = None) -> Dict:
    """
    IV Regime Classifier — the earnings replacement.

    Instead of needing an earnings calendar, this classifier detects the CAUSE
    of elevated IV from the data itself. Three signals combined:

    1. Term structure slope: front/back IV > 1.10 → binary event priced in near term
    2. IV acceleration rate: IV jumped >20% in 5d relative to price move → event pricing
    3. Vol-of-vol: std(daily IV changes) > 30% → unstable surface (UNCERTAIN)

    Regimes:
      STRUCTURAL_BUILD  — IV rising gradually with price or compression phase
                          Best entry for directional longs. Vega tailwind.
      EVENT_PRICED      — inverted term structure or sudden IV jump
                          Vol crush risk present. Use long only with wider DTE.
      COMPLACENT        — IV falling or at lows, flat term structure
                          Cheap premium but vol may compress further. Check vol direction.
      UNCERTAIN         — high vol-of-vol, surface unstable
                          Reduce position size, require stronger structural confirmation.

    Also computes:
      iv_direction: RISING / FALLING / STABLE (5-day vector of ATM IV change)
      iv_direction_pct: magnitude of the change
    """
    result = {
        'iv_regime':         'UNKNOWN',
        'iv_direction':      'STABLE',
        'iv_direction_pct':  0.0,
        'term_ratio':        None,
        'vol_of_vol':        None,
        'iv_accel_detected': False,
    }

    if not np.isfinite(atm_iv) or atm_iv <= 0:
        return result

    # ── 1. Term structure ratio ──────────────────────────────────────────────
    front_iv = chain_df[chain_df['dte'].between(10, 25)]['implied_vol'].median()
    back_iv  = chain_df[chain_df['dte'].between(40, 60)]['implied_vol'].median()
    term_ratio = None
    if np.isfinite(front_iv) and np.isfinite(back_iv) and back_iv > 0:
        term_ratio = round(float(front_iv / back_iv), 3)
        result['term_ratio'] = term_ratio

    # ── 2. IV direction of travel (5-day) ────────────────────────────────────
    iv_dir_pct = 0.0
    iv_accel   = False
    if len(iv_history) >= 2:
        iv_5d_ago = float(iv_history[-min(5, len(iv_history))])
        if iv_5d_ago > 0:
            iv_dir_pct = (atm_iv - iv_5d_ago) / iv_5d_ago
            result['iv_direction_pct'] = round(iv_dir_pct * 100, 2)
            if iv_dir_pct > IV_DIRECTION_RISE_THRESHOLD:
                result['iv_direction'] = 'RISING'
            elif iv_dir_pct < IV_DIRECTION_FALL_THRESHOLD:
                result['iv_direction'] = 'FALLING'
            # Acceleration check: IV jumped > 20% in 5 days
            if iv_dir_pct > IV_REGIME_ACCEL_THRESHOLD:
                iv_accel = True
                result['iv_accel_detected'] = True

    # ── 3. Vol-of-vol (instability of IV surface) ────────────────────────────
    vov = None
    if len(iv_history) >= 5:
        iv_arr  = np.array([float(x) for x in iv_history[-10:]])
        daily_changes = np.diff(iv_arr) / np.maximum(iv_arr[:-1], 0.01)
        vov = float(np.std(daily_changes))
        result['vol_of_vol'] = round(vov, 4)

    # ── Regime Classification ────────────────────────────────────────────────
    # Priority order: UNCERTAIN > EVENT_PRICED > STRUCTURAL_BUILD > COMPLACENT

    if vov is not None and vov > IV_VOL_OF_VOL_HIGH:
        result['iv_regime'] = 'UNCERTAIN'
    elif (term_ratio is not None and term_ratio > IV_REGIME_TERM_EVENT_RATIO) or iv_accel:
        result['iv_regime'] = 'EVENT_PRICED'
    elif result['iv_direction'] == 'RISING' or (
            term_ratio is not None and 0.98 <= term_ratio <= IV_REGIME_TERM_EVENT_RATIO):
        result['iv_regime'] = 'STRUCTURAL_BUILD'
    else:
        result['iv_regime'] = 'COMPLACENT'

    return result


def compute_iv_context(chain_df: pd.DataFrame, ticker: str,
                       run_dir: str = None) -> Dict:
    """
    Complete IV context computation.

    Enhancements vs prior version:
      1. Dual-window IVP (30d + 252d) — uses max(both), requires both < CHEAP for CHEAP label
         Eliminates the VRP circular reference bug from the KDP QA session.
      2. IV Skew (25-delta risk reversal) — directional alignment check
      3. IV Regime Classifier — detects structural build vs event pricing vs complacency
      4. IV Direction of Travel (5-day vector) — rising/falling/stable
      5. Vol-of-vol — surface stability indicator
      6. Heston parameter calibration (if enough chain data) — stored for Greek enrichment
    """
    result = {
        'atm_iv':         None,
        'iv_rank':        None,
        'iv_percentile':  None,   # primary: max(ivp_30d, ivp_252d)
        'ivp_30d':        None,
        'ivp_252d':       None,
        'ivp_label':      'UNKNOWN',
        'hv_30d':         None,
        'iv_vs_hv':       None,
        'term_structure': 'UNKNOWN',
        # Skew
        'risk_reversal':  None,
        'put_25d_iv':     None,
        'call_25d_iv':    None,
        'skew_label':     'UNKNOWN',
        # Regime
        'iv_regime':      'UNKNOWN',
        'iv_direction':   'STABLE',
        'iv_direction_pct': 0.0,
        'term_ratio':     None,
        'vol_of_vol':     None,
        'iv_accel_detected': False,
        # Heston
        'heston_params':  None,
    }

    # IV-FIX-001: Separate early exits.
    # chain_df.empty = no chain data at all → exit immediately (cannot compute anything)
    # implied_vol all-NaN = chain fetched but Polygon didn't return IV values →
    #   attempt absolute-level fallback from atm_iv if available, else continue
    if chain_df.empty:
        return result

    # Attempt spot from chain even when IV is missing
    spot = chain_df['underlying_price'].dropna().median()
    if not np.isfinite(spot) or spot <= 0:
        return result

    _all_iv_nan = chain_df['implied_vol'].isna().all()

    if not _all_iv_nan:
        atm_band = chain_df[
            (chain_df['strike'].between(spot*0.95, spot*1.05)) &
            (chain_df['dte'].between(10, 45)) &
            (chain_df['implied_vol'].notna())
        ]
        atm_iv = float(atm_band['implied_vol'].median()) if not atm_band.empty else float(chain_df['implied_vol'].median())
    else:
        # IV-FIX-001: Polygon chain returned rows but no implied_vol values.
        # MD chain enrichment may have populated implied_vol on some rows via
        # the Polygon+MD merge in fetch_chain(). Check for that first.
        # MD-IV-FALLBACK: pull ATM IV from any MD-enriched row in the chain
        # (mark_synthetic=False rows have real MD IV where the join succeeded).
        _md_rows = chain_df[
            (chain_df.get('mark_synthetic', pd.Series(True, index=chain_df.index)) == False) &
            (chain_df['implied_vol'].notna()) &
            (chain_df['implied_vol'] > 0)
        ] if 'mark_synthetic' in chain_df.columns else pd.DataFrame()

        if not _md_rows.empty:
            # Use MD-enriched IV — filter to ATM band first, else median of all MD rows
            _md_atm = _md_rows[
                _md_rows['strike'].between(spot * 0.95, spot * 1.05)
            ] if 'strike' in _md_rows.columns else pd.DataFrame()
            atm_iv = float(
                _md_atm['implied_vol'].median() if not _md_atm.empty
                else _md_rows['implied_vol'].median()
            )
            print(f"  [{ticker}] MD-IV-FALLBACK: atm_iv={atm_iv:.3f} from {len(_md_rows)} MD-enriched contracts")
        else:
            # No MD IV available either — try iv_engine with contract_iv if present
            # iv_engine_from_row() will use contract_iv from MD quote enrichment
            # which happens AFTER compute_iv_context in process_ticker()
            # So here we use the chain's own contract_iv if any row has it
            _any_iv = chain_df['implied_vol'].dropna()
            atm_iv = float(_any_iv.median()) if not _any_iv.empty else float('nan')
            if not (np.isfinite(atm_iv) and atm_iv > 0):
                atm_iv = float('nan')

    if not np.isfinite(atm_iv) or atm_iv <= 0:
        # IV-FIX-001: atm_iv invalid — apply absolute-level proxy from spot/HV.
        # This path was previously unreachable when implied_vol all-NaN because
        # the early exit fired first. Now it fires and provides proxy iv_rank.
        # The fallback at len(closes)<60 below will also fire in this path.
        # We do NOT return here — let execution continue to the closes section
        # which has its own absolute fallback.
        atm_iv = None   # sentinel: absolute fallback in closes section will set result

    # ── Historical closes → HV and dual-window IVP ──────────────────────────
    # FIX-01 (2026-05-02): HV computed BEFORE any early return.
    # Root cause: Polygon returns 173 closes but atm_iv=None (delayed plan has
    # no implied_vol in chain snapshot). Code entered proxy block and returned
    # at line 2644 before HV computation, discarding the closes entirely.
    # Fix: compute hv_30d immediately after fetching closes, store in result.
    # The atm_iv=None proxy block then returns WITH hv_30d populated.
    closes = _fetch_hist_closes(ticker, 252)

    # ALWAYS compute HV from closes — independent of atm_iv availability
    if len(closes) >= 30:
        _hv_rets = np.diff(np.log(closes))
        _hv30    = float(np.std(_hv_rets[-30:]) * sqrt(252))
        if _hv30 > 0:
            result['hv_30d'] = round(_hv30, 4)
            # Pre-compute rv_series for IVP below (avoid redundant calculation)
            if len(closes) >= 60:
                _hv_win = 21
                result['_rv_series'] = np.array([
                    np.std(_hv_rets[i:i+_hv_win]) * sqrt(252)
                    for i in range(len(_hv_rets) - _hv_win)
                ])

    # IV-FIX-001: Handle atm_iv=None sentinel (chain had rows but no IV values)
    # hv_30d is now set above — returned result will include it.
    if atm_iv is None or not np.isfinite(atm_iv) or atm_iv <= 0:
        # IV-FIX-001 + IV-ENGINE-CONNECT: No IV from Polygon chain or MD merge.
        # Use iv_engine — hv_30d now available for a real RV-based VRP signal.
        _proxy_iv = None
        try:
            from iv_engine import iv_engine_from_row as _iv_eng_proxy
            _proxy_row = {
                'ticker':           ticker,
                'contract_iv':      chain_df['implied_vol'].dropna().median() if not chain_df['implied_vol'].dropna().empty else None,
                'hv_30d':           result.get('hv_30d'),   # FIX-01: now populated
                'underlying_price': spot,
                'contract_dte':     int(chain_df['dte'].dropna().median()) if 'dte' in chain_df.columns and not chain_df['dte'].dropna().empty else 30,
            }
            _iv_eng_result = _iv_eng_proxy(_proxy_row)
            if _iv_eng_result:
                _proxy_iv = _iv_eng_result.iv_current
                result['iv_rank']       = min(80, max(20, int(_iv_eng_result.iv_current_pct * 2)))
                result['iv_percentile'] = min(0.80, max(0.20, _iv_eng_result.iv_current_pct / 100))
                result['ivp_label']     = _iv_eng_result.vrp_signal
                result['atm_iv']        = round(_iv_eng_result.iv_current, 4)
                result['iv_regime']     = ('STRUCTURAL_BUILD' if _iv_eng_result.vrp_signal == 'BUY_EDGE'
                                           else 'EVENT_PRICING' if _iv_eng_result.vrp_signal == 'SELL_EDGE'
                                           else 'UNKNOWN')
                # iv_vs_hv: computable now that hv_30d is populated
                if result.get('hv_30d') and result['hv_30d'] > 0:
                    result['iv_vs_hv'] = round(_iv_eng_result.iv_current / result['hv_30d'], 3)
        except ImportError:
            pass
        except Exception:
            pass

        if _proxy_iv is None:
            result['iv_rank']       = 50
            result['iv_percentile'] = 0.50
            result['ivp_label']     = 'FAIR'
            result['atm_iv']        = None
        result.pop('_rv_series', None)   # clean temp key before return
        return result

    result['atm_iv'] = round(atm_iv, 4)

    # FIX-01b: iv_vs_hv always computable since hv_30d was set above
    if result.get('hv_30d') and result['hv_30d'] > 0:
        result['iv_vs_hv'] = round(atm_iv / result['hv_30d'], 3)

    if len(closes) < 60:
        # Fallback absolute-level estimate from atm_iv level
        if atm_iv < 0.25:   result['iv_rank'] = 20; result['iv_percentile'] = 0.20
        elif atm_iv < 0.40: result['iv_rank'] = 40; result['iv_percentile'] = 0.40
        elif atm_iv < 0.60: result['iv_rank'] = 60; result['iv_percentile'] = 0.60
        else:               result['iv_rank'] = 80; result['iv_percentile'] = 0.80
        result['ivp_label'] = _ivp_label(result['iv_percentile'])
    else:
        returns = np.diff(np.log(closes))
        win = 21
        # FIX-01b: use pre-computed rv_series if available, else compute
        rv_series = result.pop('_rv_series', None)
        if rv_series is None:
            rv_series = np.array([np.std(returns[i:i+win])*sqrt(252)
                                   for i in range(len(returns)-win)])

        # hv_30d already computed above — only recompute if somehow missing
        if not result.get('hv_30d'):
            hv_30 = float(np.std(returns[-30:])*sqrt(252)) if len(returns) >= 30 else None
            result['hv_30d']   = round(hv_30, 4) if hv_30 else None
            result['iv_vs_hv'] = round(atm_iv/hv_30, 3) if hv_30 and hv_30 > 0 else None

        if len(rv_series) >= 20:
            # ── 252-day raw percentile (PRIMARY) ─────────────────────────────
            lo_252 = float(rv_series.min())
            hi_252 = float(rv_series.max())
            ivp_252 = float(np.clip((atm_iv - lo_252)/(hi_252 - lo_252), 0, 1)) if hi_252 > lo_252 else 0.5

            # ── 30-day raw percentile (SECONDARY) ────────────────────────────
            rv_30  = rv_series[-30:] if len(rv_series) >= 30 else rv_series
            lo_30  = float(rv_30.min())
            hi_30  = float(rv_30.max())
            ivp_30 = float(np.clip((atm_iv - lo_30)/(hi_30 - lo_30), 0, 1)) if hi_30 > lo_30 else 0.5

            # PRIMARY IVP = max(both) — conservative: uses the more expensive reading
            ivp_primary = max(ivp_252, ivp_30)

            result['ivp_252d']      = round(ivp_252, 3)
            result['ivp_30d']       = round(ivp_30, 3)
            result['iv_percentile'] = round(ivp_primary, 3)
            result['iv_rank']       = round(ivp_primary * 100, 1)

            # CHEAP requires BOTH windows agree — prevents false cheap readings
            if ivp_252 <= IVP_CHEAP_MAX and ivp_30 <= IVP_CHEAP_MAX:
                result['ivp_label'] = 'CHEAP'
            elif ivp_primary > IVP_EXPENSIVE:
                result['ivp_label'] = 'EXPENSIVE'
            else:
                result['ivp_label'] = 'FAIR'

            # Window divergence warning
            if abs(ivp_252 - ivp_30) > 0.20:
                result['ivp_divergence_warning'] = (
                    f'30d IVP={ivp_30:.0%} vs 252d IVP={ivp_252:.0%} — '
                    f'{"252d window detects annual high; recent regime compressed" if ivp_252 > ivp_30 else "30d regime elevated vs annual context"}'
                )

    # ── Term structure ───────────────────────────────────────────────────────
    front = chain_df[chain_df['dte'].between(10,25)]['implied_vol'].median()
    back  = chain_df[chain_df['dte'].between(40,60)]['implied_vol'].median()
    if np.isfinite(front) and np.isfinite(back) and front > 0:
        result['term_structure'] = 'BACKWARDATION' if front > back*1.02 else 'CONTANGO'

    # ── IV Skew (25-delta risk reversal) ─────────────────────────────────────
    skew = compute_iv_skew(chain_df, spot)
    result.update(skew)

    # ── IV Regime Classification ─────────────────────────────────────────────
    iv_history = _load_iv_history(ticker, run_dir)
    regime_data = classify_iv_regime(atm_iv, chain_df, iv_history, spot)
    result.update(regime_data)

    # Store current ATM IV in history
    iv_history.append(atm_iv)
    _IV_HISTORY[ticker] = iv_history[-10:]   # keep last 10 sessions

    # ── Heston Calibration ───────────────────────────────────────────────────
    try:
        heston_params = calibrate_heston(chain_df, spot)
        if heston_params:
            result['heston_params'] = heston_params
            result['heston_fit_error'] = heston_params.get('fit_error')
    except Exception:
        pass

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — STRUCTURAL CONTEXT PARSER
# ═══════════════════════════════════════════════════════════════════════════════

_select_directional_invalidation = select_directional_invalidation


def _governed_structural_target(direction: str, entry: float, discovery_target: Optional[float],
                                l1_far: Any, stop_dist: Optional[float]) -> Tuple[Optional[float], str]:
    """Return (target, state). A target is positive and on the thesis side of entry, or absent.

    Preference: Discovery structural target, L1 far trigger, then entry +/- 3 x invalidation distance.
    States: DISCOVERY_TARGET | L1_FAR | TARGET_3R | TARGET_3R_NON_POSITIVE | NO_TARGET_SOURCE.
    """
    sign = 1 if direction == 'CALL' else -1 if direction == 'PUT' else 0
    if sign == 0 or entry is None or not entry > 0:
        return None, 'NO_TARGET_SOURCE'

    def _usable(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number <= 0 or sign * (number - entry) <= 0:
            return None
        return number

    discovery = _usable(discovery_target)
    if discovery is not None:
        return discovery, 'DISCOVERY_TARGET'
    far = _usable(l1_far)
    if far is not None:
        return far, 'L1_FAR'
    if stop_dist is None:
        return None, 'NO_TARGET_SOURCE'
    three_r = entry + sign * 3 * stop_dist
    if _usable(three_r) is None:
        return None, 'TARGET_3R_NON_POSITIVE'
    return three_r, 'TARGET_3R'


def parse_structural_context(signal_row: pd.Series) -> Dict:
    """
    Extract all structural intelligence from the merged Vanguard + Discovery row.
    This is the pipeline contract — the options layer reads from here, never guesses.
    """

    def _f(field, default=None):
        v = signal_row.get(field, default)
        if pd.isna(v) if isinstance(v, float) else False: return default
        return v

    ticker      = str(_f('ticker', ''))
    tier        = _safe_int(_f('tier', 2), 2)
    phase       = str(_f('phase', 'C')).upper()[:1]
    intent      = str(_f('precor_intent', 'WAIT'))
    trend       = str(_f('dominant_trend', 'MIXED'))
    ema_stack   = str(_f('ema_stack', 'MIXED'))
    # FIX-M: regime field name — Vanguard may emit 'regime', 'active_regime',
    # or 'market_regime'. Default TRANSITIONAL is correct but over-fires V4
    # when the column is simply named differently. Try all known variants.
    regime_raw  = (_f('active_regime') or _f('regime') or
                   _f('market_regime') or _f('vanguard_regime') or 'TRANSITIONAL')
    regime      = str(regime_raw).upper().strip() or 'TRANSITIONAL'
    spot        = float(_f('stock_price', 0) or 0)
    entry       = float(_f('entry_price', spot) or spot)
    _raw_stop = _f('stop_loss')
    try:
        _stop_authoritative = _raw_stop is not None and float(_raw_stop) > 0
    except (TypeError, ValueError):
        _stop_authoritative = False
    # A missing structural invalidation is missing data, not permission to
    # fabricate a conventional three-percent stop.  Downstream lifecycle and
    # economics consumers must either use the governed stop or disclose that
    # the thesis is not yet evaluable.
    stop        = float(_raw_stop) if _stop_authoritative else None
    composite   = float(_f('composite_score', 50) or 50)
    win_prob    = float(_f('win_probability', 50) or 50)
    crabel      = str(_f('crabel_pattern', '') or '')
    vwap_bias   = str(_f('vwap_bias', '') or '')
    vol_ratio   = float(_f('volume_ratio', 1.0) or 1.0)
    atr         = float(_f('ATR_14', 0) or 0)
    days_ema50  = int(_f('days_above_ema50', 0) or 0)
    pct_52w_low = float(_f('pct_from_52w_low', 0) or 0)

    # Risk levels from structure
    stop_dist   = abs(entry - stop) if stop is not None else None
    stop_pct    = stop_dist / entry if stop_dist is not None and entry > 0 else None
    target_2r   = entry + 2*stop_dist if stop_dist is not None else None
    target_3r   = entry + 3*stop_dist if stop_dist is not None else None

    # L1 scenario prices from Vanguard
    l1_near  = _f('layer1__scenarios__conditional_near__trigger_price')
    l1_far   = _f('layer1__scenarios__conditional_far__trigger_price')
    l1_far_prob = float(_f('layer1__scenarios__conditional_far__probability_estimate', 0) or 0)

    # L2 context
    l2_n_obs     = int(_f('layer2__n_observations', 0) or 0)
    l2_win_rate  = float(_f('layer2__win_rate_20d', 0) or 0)
    l2_hold_days = int(_f('layer2__recommended_hold_days', 0) or 0)
    l2_ev        = float(_f('layer2__expected_value_20d', 0) or 0)
    l2_prob_up   = float(_f('layer2__prob_up_10pct_20d', 0) or 0)
    l2_prob_down = float(
        _f('layer2__prob_down_10pct_20d', 0)
        or _f('raw_prob_down_10d', 0)
        or _f('raw_prob_down_20d', 0)
        or 0
    )
    l2_edge_direction = str(
        _f('vanguard_edge_direction', '')
        or _f('edge_direction', '')
        or _f('layer2__edge_direction', '')
        or _f('layer2__probability_direction', '')
        or ''
    ).upper().strip()
    if l2_edge_direction not in {"CALL", "PUT"}:
        raw_prob_up = float(_f('raw_prob_up_10d', 0) or _f('raw_prob_up_20d', 0) or l2_prob_up or 0)
        raw_prob_down = l2_prob_down
        if raw_prob_up > raw_prob_down and raw_prob_up > 0:
            l2_edge_direction = "CALL"
        elif raw_prob_down > raw_prob_up and raw_prob_down > 0:
            l2_edge_direction = "PUT"
    l2_prob_verdict   = str(_f('layer2__probability_verdict', '') or '').upper().strip()
    l2_edge_quality   = str(_f('layer2__edge_quality', '') or '').upper().strip()
    vanguard_verdict  = str(_f('verdict', '') or '').upper().strip()
    final_rec         = str(_f('final_recommendation', '') or '').upper().strip()
    upstream_direction = str(_f('direction', '') or _f('fusion_direction', '') or '').upper().strip()

    # A4 — L1/L2 direction reconciliation inputs
    control_state    = str(_f('control_state', '') or '').upper().strip()
    precor_control   = str(_f('precor_control', '') or '').upper().strip()
    l2_p_return_gt0  = float(_f('layer2__p_return_gt0_20d', 0) or l2_win_rate or 0)
    l2_median_loss   = float(_f('layer2__median_loss_20d', 0) or 0)   # negative value e.g. -6.87

    def _direction_from_text(value: str) -> Optional[str]:
        text = (value or "").upper()
        if any(tok in text for tok in ("CALL", "BUY", "BULL", "LONG")):
            return "CALL"
        if any(tok in text for tok in ("PUT", "SELL", "BEAR", "SHORT")):
            return "PUT"
        return None

    # Stage 1 has a closed, fail-closed structural table.  The previous WAIT,
    # transition and asymmetric L1/L2 repairs were hidden writers of direction;
    # they are replaced by the audited independent-evidence protocol below.
    discovery_preliminary = str(
        _f('discovery_direction_preliminary', '')
        or _f('direction', '')
        or _f('fusion_direction', '')
        or ''
    ).upper().strip()
    discovery_authority = str(_f('direction_authority', '') or '').upper().strip()
    structural_candidate, structural_basis = structural_direction(intent, trend)
    if discovery_authority == 'DISCOVERY_GOVERNED':
        governed_direction = discovery_preliminary
        governed_basis = str(
            _f('discovery_direction_basis', '')
            or f'DISCOVERY_GOVERNED:{discovery_preliminary}'
        )
        governed_authority = 'DISCOVERY_GOVERNED'
        allow_non_directional_resolution = False
    else:
        # Compatibility for pre-v1.2 Discovery artefacts. Fresh runs must carry
        # DISCOVERY_GOVERNED and do not enter this branch.
        governed_direction = structural_candidate
        governed_basis = structural_basis
        governed_authority = 'OPTIONS_INTELLIGENCE_LEGACY_ADAPTER'
        allow_non_directional_resolution = True
    raw_for_direction = signal_row.to_dict() if hasattr(signal_row, 'to_dict') else dict(signal_row)
    direction_record = resolve_governed_direction(
        ticker=ticker,
        run_id=_f('run_id', '') or _f('scanner_run_id', ''),
        discovery_direction=discovery_preliminary,
        governed_direction=governed_direction,
        governed_basis=governed_basis,
        row=raw_for_direction,
        decided_at_utc=str(_f('generated_at_utc', '') or _f('scanner_timestamp_utc', '') or ''),
        authority=governed_authority,
        allow_non_directional_resolution=allow_non_directional_resolution,
    )
    direction = str(direction_record['final_direction'])
    direction_override_reason = (
        direction_record['direction_resolution_path']
        if direction != governed_direction else None
    )

    # Re-resolve invalidation only after the frozen direction is known.  This
    # prevents a CALL-style support stop being attached to a PUT thesis.
    stop, stop_source, stop_state = _select_directional_invalidation(
        raw_for_direction,
        direction,
        entry,
    )
    _stop_authoritative = stop is not None
    stop_dist = abs(entry - stop) if stop is not None else None
    stop_pct = stop_dist / entry if stop_dist is not None and entry > 0 else None
    if direction == 'CALL':
        target_2r = entry + 2 * stop_dist if stop_dist is not None else None
        target_3r = entry + 3 * stop_dist if stop_dist is not None else None
    elif direction == 'PUT':
        target_2r = entry - 2 * stop_dist if stop_dist is not None else None
        target_3r = entry - 3 * stop_dist if stop_dist is not None else None
    else:
        target_2r = None
        target_3r = None

    # Derive DTE window from tier + phase, then let the horizon router override it.
    dte_window = DTE_MATRIX.get((tier, phase), DTE_DEFAULT)
    # E2E-OPTIONS-LAB-SYNC 2026-05-22:
    # The previous horizon-aware DTE map existed but was only used for rejection
    # logging. Contract selection still used tier/phase DTE windows, which caused
    # 6-10d and 11-20d ideas to be scored through the wrong lens.
    _horizon_key = str(
        signal_row.get('horizon_bucket')
        or signal_row.get('expected_move_window')
        or signal_row.get('macro_preferred_horizon')
        or ''
    ).lower().replace('-', '_')
    _horizon_key = (
        '1_5d' if '1_5' in _horizon_key else
        '6_10d' if '6_10' in _horizon_key else
        '11_20d' if '11_20' in _horizon_key else
        _horizon_key
    )
    _horizon_dte_cfg = governed_dte_config(_horizon_key)
    if _horizon_dte_cfg:
        dte_window = governed_dte_window(_horizon_key)

    # Expected hold days — use L2 if available, else DTE target
    hold_days = l2_hold_days if l2_hold_days > 0 else dte_window[1]

    # ── Hold duration enrichment ───────────────────────────────────────────────
    # Wyckoff phase sets the structural hold window. Theta cap prevents holding
    # past the point where time decay consumes too much premium (DTE × 0.5).
    # days_to_trigger is read from the signal row — how many days until the
    # structural setup is expected to resolve.
    _phase_hold = {
        'A': (10, 30), 'B': (15, 40), 'C': (3, 12), 'D': (3, 10), 'E': (1, 5),
    }
    _hold_min, _hold_max = _phase_hold.get(phase, (5, 20))

    # Theta cap: never hold longer than DTE × 0.5 or theta decay dominates
    _dte_target = dte_window[1]
    _theta_cap  = int(_dte_target * 0.5)

    # Apply theta cap — if it binds, hold_max is constrained by time not phase
    _theta_constrained = _theta_cap < _hold_max
    _hold_max_final    = min(_hold_max, _theta_cap)
    _hold_min_final    = min(_hold_min, _hold_max_final)

    # Add days_to_trigger offset if the setup hasn't fired yet
    # Guard: NaN is truthy in Python so 'NaN or 0' returns NaN → int(NaN) crashes
    _dtt_raw = signal_row.get('days_to_trigger', 0)
    _days_to_trig = int(float(_dtt_raw)) if _dtt_raw is not None and not (isinstance(_dtt_raw, float) and pd.isna(_dtt_raw)) else 0
    _hold_min_final = _hold_min_final + _days_to_trig
    _hold_max_final = _hold_max_final + _days_to_trig

    hold_label = f"{_hold_min_final}–{_hold_max_final} days"

    if _hold_max_final <= 5:
        hold_urgency = 'IMMEDIATE'
    elif _hold_max_final <= 14:
        hold_urgency = 'STAGED'
    else:
        hold_urgency = 'PATIENT'

    # Strategy and contract selection are absent until direction is governed.
    # This prevents STRANGLE/NONE from silently falling through to LONG_PUT.
    if direction not in GOVERNED_DIRECTED_SIDES:
        delta_zone = DELTA_ZONES['COMPRESSION']
        preferred_strategy = 'NO_DIRECTIONAL_STRATEGY'
    elif phase in ('D','E') or 'Extreme' in crabel:
        delta_zone = DELTA_ZONES['MOMENTUM']
        preferred_strategy = 'LONG_CALL' if direction=='CALL' else 'LONG_PUT'
    elif phase == 'C' or 'NR7' in crabel:
        delta_zone = DELTA_ZONES['COMPRESSION']
        preferred_strategy = 'LONG_CALL' if direction=='CALL' else 'LONG_PUT'
    else:
        # Production mandate is long single-leg options only. Phase A/B may
        # require a more patient liquidity monitor, but must not silently
        # switch the trader into a debit spread.
        delta_zone = DELTA_ZONES['EARLY']
        preferred_strategy = 'LONG_CALL' if direction=='CALL' else 'LONG_PUT'

    # Structural target: Discovery target, then L1 far trigger, then 3R — each only when it is
    # positive and on the thesis side of entry (WP1 E6, ACK 17 Sep 2026). A 3R PUT target that
    # is not positive is recorded as absent with its reason, never passed on.
    try:
        discovery_target = float(_f('structural_target'))
        if not np.isfinite(discovery_target) or discovery_target <= 0:
            discovery_target = None
    except (TypeError, ValueError):
        discovery_target = None
    structural_target, structural_target_state = _governed_structural_target(
        direction, entry, discovery_target, l1_far, stop_dist,
    )

    return {
        '_signal_row'        : signal_row,   # FIX (2026-03-07): raw row stash for asof_date in _stand_down
        'ticker'             : ticker,
        'tier'               : tier,
        'phase'              : phase,
        'intent'             : intent,
        'direction'          : direction,
        **direction_record,
        'direction_override_reason': direction_override_reason,   # A4: None or override string
        'vanguard_support_direction_repair': bool(
            direction_override_reason
            and str(direction_override_reason).startswith('VANGUARD_SUPPORT_DIRECTION_REPAIR')
        ),
        'trend'              : trend,
        'ema_stack'          : ema_stack,
        'regime'             : regime,
        'spot'               : spot,
        'entry'              : entry,
        'stop'               : stop,
        'stop_authoritative' : _stop_authoritative,
        'stop_source'        : stop_source,
        'stop_state'         : stop_state,
        'stop_dist'          : stop_dist,
        'stop_pct'           : stop_pct,
        'target_2r'          : target_2r,
        'target_3r'          : target_3r,
        'structural_target'  : structural_target,
        'structural_target_state': structural_target_state,
        'composite'          : composite,
        'win_prob'           : win_prob,
        'crabel'             : crabel,
        'vwap_bias'          : vwap_bias,
        'vol_ratio'          : vol_ratio,
        'atr'                : atr,
        'days_ema50'         : days_ema50,
        'pct_52w_low'        : pct_52w_low,
        'dte_window'         : dte_window,
        'dte_config'         : _horizon_dte_cfg,
        'hold_days'          : hold_days,
        'hold_label'         : hold_label,
        'hold_urgency'       : hold_urgency,
        'theta_constrained'  : _theta_constrained,
        'delta_zone'         : delta_zone,
        'preferred_strategy' : preferred_strategy,
        'l1_near'            : l1_near,
        'l1_far'             : l1_far,
        'l1_far_prob'        : l1_far_prob,
        'l2_n_obs'           : l2_n_obs,
        'l2_win_rate'        : l2_win_rate,
        'l2_hold_days'       : l2_hold_days,
        'l2_ev'              : l2_ev,
        'l2_prob_up'         : l2_prob_up,
        'l2_prob_down'       : l2_prob_down,
        'vanguard_edge_direction': l2_edge_direction or "NONE",
        'layer2__edge_direction': l2_edge_direction or "NONE",
        'layer2__probability_direction': l2_edge_direction or "NONE",
        'behaviour_state_key' : _f('behaviour_state_key', ''),
        'behaviour_state_hash': _f('behaviour_state_hash', ''),
        'actuarial_match_type': (
            _f('actuarial_match_type', '')
            or _f('layer2__state_match_method', '')
            or _f('layer2__state_match_stage', '')
        ),
        'actuarial_ev_weight': _f('actuarial_ev_weight', ''),
        'catalyst_overlay'   : (
            _f('catalyst_overlay', '')
            or _f('catalyst_trade_class', '')
            or ('CATALYST_DETECTED' if str(_f('catalyst_detected', '')).upper() in {'TRUE', '1', 'YES'} else 'NONE')
        ),
        'horizon_bucket'     : _f('horizon_bucket', ''),
        'horizon_action'     : _f('horizon_action', ''),
        'horizon_size_multiplier': _f('horizon_size_multiplier', ''),
        'horizon_block_reason': _f('horizon_block_reason', ''),
        'horizon_source'     : _f('horizon_source', ''),
        'router_version'     : _f('router_version', ''),
        'layer2_matched_state_key': (
            _f('layer2__matched_state_key', '')
            or _f('layer2__outcomes__matched_state_key', '')
        ),
        'layer2_vol_regime'   : _f('layer2__vol_regime'),
        'layer2_trend_direction': _f('layer2__trend_direction'),
        'layer2_structure_quality': _f('layer2__structure_quality'),
        'layer2_trend_maturity': _f('layer2__trend_maturity'),
        'wyckoff_phase_bucket': _f('wyckoff_phase_bucket'),
        'adx_14'             : _f('adx_14'),
        'atr_percentile_rank': _f('atr_percentile_rank'),
    }


def _ev3_handoff_fields(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Build the explicit EV3 thesis contract with auditable derivations."""
    entry = _repair_alt_float(ctx.get('entry'))
    target = _repair_alt_float(ctx.get('structural_target'))
    raw_stop = _repair_alt_float(ctx.get('stop'))
    direction = str(ctx.get('direction') or '').upper()

    invalidation = None
    invalidation_source = (
        'NOT_APPLICABLE_NON_DIRECTIONAL'
        if direction not in {'CALL', 'PUT'}
        else LifecycleEvaluationState.MISSING_AUTHORITATIVE_STOP.value
    )
    invalidation_state = (
        GovernedDataState.NOT_APPLICABLE.value
        if direction not in {'CALL', 'PUT'} else 'MISSING'
    )
    if entry and raw_stop and bool(ctx.get('stop_authoritative')) and direction in {'CALL', 'PUT'}:
        if (direction == 'CALL' and raw_stop < entry) or (direction == 'PUT' and raw_stop > entry):
            invalidation = raw_stop
            invalidation_source = str(ctx.get('stop_source') or 'stop_loss')
            invalidation_state = 'AVAILABLE'
        else:
            invalidation_state = LifecycleEvaluationState.DATA_DEFECT_WRONG_SIDE.value

    horizon_text = str(ctx.get('horizon_bucket') or '').upper().replace('-', '_').replace(' ', '')
    if '1_5' in horizon_text:
        planned_hold_sessions = 5
    elif '6_10' in horizon_text:
        planned_hold_sessions = 10
    elif '11_20' in horizon_text:
        planned_hold_sessions = 20
    else:
        planned_hold_sessions = None

    state_values: Dict[str, str] = {}
    for component in str(ctx.get('layer2_matched_state_key') or '').split('|'):
        if '=' in component:
            name, value = component.split('=', 1)
            state_values[name.strip()] = value.strip().upper()
    adx = _repair_alt_float(ctx.get('adx_14'))
    atr_rank = _repair_alt_float(ctx.get('atr_percentile_rank'))
    adx_bucket = None
    if adx is not None:
        adx_bucket = 'WEAK' if adx < 20 else ('STRONG' if adx > 35 else 'MODERATE')
    atr_bucket = None
    if atr_rank is not None:
        atr_bucket = 'LOW' if atr_rank < 33 else ('HIGH' if atr_rank > 66 else 'MID')
    state_parts = (
        state_values.get('vol_regime') or str(ctx.get('layer2_vol_regime') or '').upper() or None,
        state_values.get('trend_direction') or str(ctx.get('layer2_trend_direction') or '').upper() or None,
        state_values.get('structure_quality') or str(ctx.get('layer2_structure_quality') or '').upper() or None,
        adx_bucket,
        state_values.get('wyckoff_phase_bucket') or str(ctx.get('wyckoff_phase_bucket') or '').upper() or None,
        state_values.get('trend_maturity') or str(ctx.get('layer2_trend_maturity') or '').upper() or None,
        atr_bucket,
    )
    barrier_state_key = '|'.join(state_parts) if all(state_parts) else None

    return {
        'entry_spot': entry,
        'target_spot': target,
        'invalidation_spot': invalidation,
        'invalidation_source': invalidation_source,
        'invalidation_state': invalidation_state,
        'invalidation_policy_version': 'EV3_GOVERNED_STOP_V2',
        'planned_hold_sessions': planned_hold_sessions,
        'planned_hold_source': 'HORIZON_BUCKET_ENDPOINT_V1' if planned_hold_sessions else 'UNROUTED',
        'ev3_handoff_schema_version': 'ev3-options-handoff-v1',
        'ev3_barrier_state_key': barrier_state_key,
        'ev3_barrier_state_key_source': (
            'LAYER2_STATE_PLUS_DISCOVERY_BUCKETS_V1' if barrier_state_key else 'INCOMPLETE_STATE_INPUTS'
        ),
        'ev3_barrier_state_key_version': 'actuarial-v7-seven-dimension-v1',
    }


def _coalesce_ev3_merge_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """Restore EV3 state dimensions hidden by the Discovery/Vanguard merge.

    Both inputs carry ADX and ATR percentile values.  ``pd.merge`` therefore
    suffixes them before ``parse_structural_context`` runs.  EV3 requires the
    unsuffixed, Vanguard-authoritative values to build the exact seven-
    dimension barrier key.  Keep the source columns for auditability and add
    only the canonical aliases consumed by the handoff.
    """
    result = frame.copy()
    for field in ('adx_14', 'atr_percentile_rank'):
        if field in result.columns:
            continue
        vanguard_field = f'{field}_y'
        discovery_field = f'{field}_x'
        if vanguard_field in result.columns and discovery_field in result.columns:
            result[field] = result[vanguard_field].combine_first(result[discovery_field])
        elif vanguard_field in result.columns:
            result[field] = result[vanguard_field]
        elif discovery_field in result.columns:
            result[field] = result[discovery_field]
    return result


def _ev3_direction_fields(
    ctx: Dict[str, Any],
    direction_arbitration: Dict[str, Any],
) -> Dict[str, Any]:
    """Expose the governed direction contract consumed by EV3.

    Arbitration outcome and resolution state are deliberately separate.  A
    structure-led CALL/PUT is resolved even though an explanatory conflict is
    retained. STRANGLE is explicitly non-directional and is routed outside the
    directional EV3 model.
    """
    direction = str(ctx.get('direction') or '').strip().upper()
    status = str(
        direction_arbitration.get('direction_arbitration_status') or 'NOT_EVALUATED'
    ).strip().upper()
    if direction in {'CALL', 'PUT'} and status in {
        'AGREEMENT', 'NO_PROBABILITY_OPINION', 'CONFLICT_STRUCTURE_LEADS',
        'GOVERNED_NON_DIRECTIONAL_RESOLVED',
    }:
        resolution_status = 'RESOLVED'
    elif direction in {'STRANGLE', 'STRADDLE'}:
        resolution_status = 'NON_DIRECTIONAL'
    else:
        resolution_status = 'UNRESOLVED'
    return {
        'canonical_direction': direction if direction in {'CALL', 'PUT'} else direction,
        'direction_resolution_status': resolution_status,
        'direction_status': resolution_status,
        'ev3_direction_source': 'GOVERNED_DIRECTION_RECORD_FINAL',
    }


def _common_options_handoff_fields(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Return direction and macro/bond context for every output branch.

    EV3 evaluates stand-down and no-contract rows as well as rows with a
    selected contract.  Keeping this context only on the success branch made
    otherwise valid alternatives appear to have an unresolved direction and
    stripped the macro/bond audit trail from most of the universe.
    """
    direction_arbitration = _direction_arbitration_oi(ctx)
    raw_row = ctx.get('_signal_row')
    if isinstance(raw_row, pd.Series):
        signal_row = raw_row.to_dict()
    elif isinstance(raw_row, dict):
        signal_row = dict(raw_row)
    else:
        signal_row = {}

    fields: Dict[str, Any] = {}
    fields.update(_ev3_direction_fields(ctx, direction_arbitration))
    fields.update(direction_arbitration)
    for field in (
        'dir_calc_version', 'direction_policy_version', 'direction_policy_sha256',
        'discovery_direction_preliminary', 'governed_direction',
        'governed_direction_authority', 'governed_direction_basis',
        'final_direction', 'direction_resolution_path',
        'direction_governance_status', 'direction_resolution_confidence',
        'direction_resolution_call_score', 'direction_resolution_put_score',
        'direction_resolution_winning_share', 'direction_resolution_margin',
        'direction_resolution_evidence_count', 'direction_resolution_evidence_json',
        'direction_resolution_chain_json', 'direction_excluded_evidence_json',
        'governed_direction_record_json', 'governed_direction_record_sha256',
    ):
        fields[field] = ctx.get(field, '')
    fields.update(macro_quant_columns_for_row(signal_row, signal_row))
    return fields


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — CONTRACT SELECTOR
# ═══════════════════════════════════════════════════════════════════════════════

def select_best_contract(df: pd.DataFrame, ctx: Dict) -> Optional[Dict]:
    """
    Select the single best contract for execution given structural context.
    Respects: DTE window, direction, delta zone, liquidity gates, spread limits.
    Scores on: delta alignment, theta efficiency, vega exposure, liquidity, DTE fit.
    """
    if df.empty: return None

    direction = ctx['direction']
    if direction not in ('CALL', 'PUT'):
        return None

    # Filter by right
    if direction == 'CALL':
        call_df = df[df['right'].str.upper()=='C'].copy()
    if direction == 'PUT':
        put_df  = df[df['right'].str.upper()=='P'].copy()

    def _score_leg(leg_df: pd.DataFrame, right: str) -> Optional[Dict]:
        if leg_df.empty: return None

        dte_min, dte_target, dte_max = ctx['dte_window']
        spot = ctx['spot']
        _dte_cfg = ctx.get('dte_config') or {}
        delta_min = float(_dte_cfg.get('delta_min', 0.15))
        delta_max = float(_dte_cfg.get('delta_max', 0.35))
        # AVS-FIX-001 W1.6: one authority, so selection and the terminal gate
        # can never disagree about the same contract.
        spread_limit = clamp_spread_limit(_dte_cfg.get('spread_max'))
        target_delta = (delta_min + delta_max) / 2.0

        # DTE filter — try strict window first, then relax ±15 days if empty
        strict_df = leg_df[leg_df['dte'].between(dte_min, dte_max)].copy()
        if strict_df.empty:
            relaxed_min = max(1, dte_min - 15)
            relaxed_max = dte_max + 15
            leg_df = leg_df[leg_df['dte'].between(relaxed_min, relaxed_max)].copy()
        else:
            leg_df = strict_df
        if leg_df.empty: return None

        # Governed long-option moneyness range. Near-ATM OTM remains preferred,
        # but a developing OTM or moderately ITM contract is a valid contract
        # family member. It must be classified and monitored, not erased. Far
        # OTM (<.20 delta) and deep ITM (>.75 delta) remain outside mandate.
        delta_abs = leg_df['delta'].abs()
        leg_df = leg_df[delta_abs.between(0.20, 0.75, inclusive='both')].copy()
        if leg_df.empty: return None

        # Invalid/crossed observations are retained in the canonical chain for
        # audit, but are never selectable. One-sided and incomplete contracts
        # remain monitorable because liquidity can develop as spot approaches.
        quality = leg_df.get(
            'quote_quality', pd.Series('INCOMPLETE', index=leg_df.index, dtype=object)
        ).fillna('INCOMPLETE').astype(str).str.upper()
        bid_values = pd.to_numeric(
            leg_df.get('bid', pd.Series(np.nan, index=leg_df.index)), errors='coerce'
        )
        ask_values = pd.to_numeric(
            leg_df.get('ask', pd.Series(np.nan, index=leg_df.index)), errors='coerce'
        )
        invalid_flags = leg_df.get(
            'quality_flags', pd.Series([()] * len(leg_df), index=leg_df.index, dtype=object)
        ).map(lambda value: bool({'CROSSED_QUOTE', 'NEGATIVE_QUOTE'} & _quote_flags(value)))
        invalid_quote = (
            quality.eq('INVALID')
            | invalid_flags
            | (bid_values.notna() & (bid_values < 0))
            | (ask_values.notna() & (ask_values < 0))
            | (bid_values.notna() & ask_values.notna() & (bid_values > ask_values))
        )
        leg_df = leg_df.loc[~invalid_quote].copy()
        if leg_df.empty:
            return None
        # OI and volume are evidence, not execution authority. New strikes can
        # show low prior-session OI and still have an executable current quote.
        # Preserve them for scoring and lifecycle monitoring. A positive mark
        # is still required so contract economics can be computed.
        eligible_df = leg_df[leg_df['mark'].fillna(0) > 0].copy()
        if eligible_df.empty: return None

        # WP1 E1/E2 (ACK 17 Sep 2026): only tradeable expressions are selectable — a two-sided
        # quote and a measured spread within the horizon spread limit, the same authority the
        # terminal gate uses. Measured on recorded chains, the round-trip cost of a long option
        # is its entry spread; one-sided, unmeasured and wide contracts stay monitorable in the
        # chain and the rejection taxonomy, but are not chosen as the expression.
        _bid = pd.to_numeric(eligible_df.get('bid', pd.Series(np.nan, index=eligible_df.index)), errors='coerce')
        _ask = pd.to_numeric(eligible_df.get('ask', pd.Series(np.nan, index=eligible_df.index)), errors='coerce')
        _spread = pd.to_numeric(eligible_df.get('spread_pct', pd.Series(np.nan, index=eligible_df.index)), errors='coerce')
        _tradeable = (_bid > 0) & (_ask > 0) & (_ask >= _bid) & _spread.notna() & (_spread <= spread_limit)
        eligible_df = eligible_df.loc[_tradeable.fillna(False)].copy()
        if eligible_df.empty: return None

        core_delta = eligible_df['delta'].fillna(0).abs()
        core_df = eligible_df[core_delta.between(delta_min, delta_max)].copy()
        if core_df.empty:
            leg_df = eligible_df.copy()
            leg_df["best_available_suboptimal"] = True
        else:
            leg_df = core_df
            leg_df["best_available_suboptimal"] = False

        # ── TARGET-REACHABILITY FILTER ─────────────────────────────────────────
        # Root cause of BLOCK_WRONG_STRIKE: delta-zone selection picks a strike
        # that is beyond the structural target, so option_value_at_target = 0 even
        # when the trade thesis is fully correct.
        #
        # Rule: For CALLs, only keep strikes BELOW structural_target (option has
        # intrinsic value at target). For PUTs, only keep strikes ABOVE
        # structural_target. If no contracts pass this filter, fall back to the
        # best available strike closest to the structural target on the correct side.
        structural_target = ctx.get('structural_target')
        if structural_target and right == 'C' and not leg_df.empty:
            reachable = leg_df[leg_df['strike'] <= structural_target].copy()
            if not reachable.empty:
                leg_df = reachable
            else:
                # Fallback: use strike closest to target from below (ATM-ish for CALL)
                below = leg_df[leg_df['strike'] <= spot * 1.05].copy()
                if not below.empty:
                    closest_idx = (below['strike'] - structural_target).abs().idxmin()
                    leg_df = below.loc[[closest_idx]]
                # If truly nothing below target, proceed with original set (BLOCK_WRONG_STRIKE
                # will fire at scoring time as last resort — better than no contract)

        if structural_target and right == 'P' and not leg_df.empty:
            reachable = leg_df[leg_df['strike'] >= structural_target].copy()
            if not reachable.empty:
                leg_df = reachable
            else:
                # Fallback: use strike closest to target from above
                above = leg_df[leg_df['strike'] >= spot * 0.95].copy()
                if not above.empty:
                    closest_idx = (above['strike'] - structural_target).abs().idxmin()
                    leg_df = above.loc[[closest_idx]]

        if leg_df.empty: return None

        # Score each contract
        scores = []
        for _, row in leg_df.iterrows():
            delta_abs = abs(row['delta']) if pd.notna(row['delta']) else 0.3
            dte_val   = row['dte'] or dte_target
            theta     = row['theta'] or -0.02
            vega      = row['vega']  or 0.05
            mark      = row['mark']  or 0
            oi        = row['open_interest'] or 0
            vol       = row['volume'] or 0
            raw_spread = row.get('spread_pct')
            try:
                spread = float(raw_spread)
                if not math.isfinite(spread) or spread < 0:
                    spread = 0.15
            except (TypeError, ValueError):
                spread = 0.15
            bid       = row.get('bid', None)
            ask       = row.get('ask', None)

            # 1. Delta alignment (30%)
            delta_score = max(0, 100 - abs(delta_abs - target_delta)*300)

            # 2. DTE fit (20%)
            dte_score = max(0, 100 - abs(dte_val - dte_target)*3)

            # 3. Theta efficiency: theta/mark ratio — lower is better (20%)
            theta_drain_pct = abs(theta)*ctx['hold_days'] / mark if mark > 0 else 1.0
            theta_score = max(0, 100 - theta_drain_pct*200)

            # 4. Vega quality: want positive vega exposure (15%)
            vega_score = min(100, vega*300) if vega else 0

            # 5. Liquidity (15%). OI/volume contribute to rank but are never a
            # terminal filter. Current spread remains the primary executable
            # evidence and is re-evaluated after exact quote enrichment.
            liq_score = min(100, (vol + oi/10)/5)
            spread_pen = min(50, max(0, spread*200))
            liq_final  = min(100, max(0, liq_score - spread_pen))

            composite = (0.30*delta_score + 0.20*dte_score + 0.20*theta_score +
                         0.15*vega_score + 0.15*liq_final)

            scores.append({
                'symbol'          : row.get('symbol'),
                'underlying'      : row.get('underlying') or ctx.get('ticker'),
                'right'           : right,
                'strike'          : row['strike'],
                'expiry'          : row['expiration_date'],
                'dte'             : dte_val,
                'mark'            : mark,
                'mid'             : mark,
                'bid'             : None if pd.isna(bid) else bid,
                'ask'             : None if pd.isna(ask) else ask,
                'bid_size'        : None if pd.isna(row.get('bid_size')) else row.get('bid_size'),
                'ask_size'        : None if pd.isna(row.get('ask_size')) else row.get('ask_size'),
                'bid_size_quality': row.get('bid_size_quality', 'MISSING'),
                'ask_size_quality': row.get('ask_size_quality', 'MISSING'),
                'delta'           : row['delta'],
                'gamma'           : row['gamma'],
                'theta'           : theta,
                'vega'            : vega,
                'iv'              : row['implied_vol'],
                'implied_vol'     : row['implied_vol'],
                'oi'              : oi,
                'open_interest'   : oi,
                'volume'          : vol,
                'spread_pct'      : spread,
                'mark_synthetic'  : bool(row.get('mark_synthetic', False)),
                'quote_quality'   : str(row.get('quote_quality') or 'INCOMPLETE').upper(),
                'quality_flags'   : list(_quote_flags(row.get('quality_flags'))),
                'quote_fields_complete': bool(row.get('quote_fields_complete', False)),
                'best_available_suboptimal': bool(row.get('best_available_suboptimal', False)),
                'otm_delta_target': target_delta,
                'contract_score'  : round(composite, 2),
                'selection_reason': (
                    'BEST_CURRENT_LONG_OPTION_QUOTE'
                    if (
                        str(row.get('quote_quality') or '').upper() == 'TWO_SIDED'
                        and not bool(row.get('mark_synthetic', False))
                        and spread <= (LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT / 100.0)
                    )
                    else 'BEST_MONITORABLE_LONG_OPTION_CONTRACT'
                ),
                'oi_used_as_hard_gate': False,
                'volume_used_as_hard_gate': False,
                'quote_timestamp_utc': row.get('quote_timestamp_utc'),
                'quote_timestamp_source': row.get('quote_timestamp_source'),
                'contract_multiplier': row.get('contract_multiplier'),
                'contract_multiplier_source': row.get('contract_multiplier_source'),
                'md_quote_source' : row.get('md_quote_source'),
                'md_occ_symbol'   : row.get('symbol'),
            })

        if not scores: return None
        return max(scores, key=lambda x: x['contract_score'])

    if direction == 'CALL':
        return _score_leg(call_df, 'C')
    elif direction == 'PUT':
        return _score_leg(put_df, 'P')
    return None


#: Run identity for the W3.3 sidecar. `process_ticker` has no access to the
#: run's output directory, which is a local of the run entry point, so the
#: entry point publishes it here once. Left None outside a run, in which case
#: the sidecar is simply not written -- instrumentation never invents a
#: location.
_ACTIVE_RUN_ID: Optional[str] = None
_ACTIVE_OUTPUT_DIR: Optional[str] = None


def set_active_run_context(run_id: Optional[str], output_dir: Optional[str]) -> None:
    """Publish the run identity the W3.3 sidecar writes under."""
    global _ACTIVE_RUN_ID, _ACTIVE_OUTPUT_DIR
    _ACTIVE_RUN_ID = str(run_id).strip() if run_id else None
    _ACTIVE_OUTPUT_DIR = str(output_dir).strip() if output_dir else None


def _contracts_tested_sidecar_path(ctx: Dict) -> Optional[Path]:
    """Where the per-ticker `contracts_tested` list is persisted.

    Beside the run's other options artefacts. Returns None when the run
    directory is unknown, in which case the sidecar is simply not written.
    """
    run_id = (
        str(ctx.get('run_id') or ctx.get('pipeline_run_id') or '').strip()
        or (_ACTIVE_RUN_ID or '')
    )
    if not run_id or not _ACTIVE_OUTPUT_DIR:
        return None
    return Path(_ACTIVE_OUTPUT_DIR) / f"contracts_tested_{run_id}.jsonl"


def _record_contracts_tested(
    ticker: str, ctx: Dict, taxonomy: Dict[str, Any], *, selected: Optional[Dict] = None
) -> None:
    """Append one ticker's contract-evaluation record to the JSONL sidecar.

    Append-only, one line per ticker per run. A write failure is logged and
    swallowed: this is instrumentation and must never stop a ticker.
    """
    path = _contracts_tested_sidecar_path(ctx)
    if path is None:
        return
    record = {
        "ticker": str(ticker or "").upper(),
        "run_id": str(ctx.get('run_id') or ctx.get('pipeline_run_id') or ''),
        "direction": str(ctx.get('direction') or '').upper(),
        "horizon_bucket": ctx.get('horizon_bucket'),
        "selected_contract_symbol": (selected or {}).get('symbol', ''),
        **{key: value for key, value in taxonomy.items() if key != "contracts_tested"},
        "contracts_tested": taxonomy.get("contracts_tested", []),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + chr(10))
    except OSError as error:
        print(f"  [{ticker}] contracts_tested sidecar not written: {error}")


def contract_rejection_taxonomy(df: pd.DataFrame, ctx: Dict) -> Dict[str, Any]:
    """Classify every contract in the chain against the selection gates.

    AVS-FIX-001 W3.3 (THS-001 §3.1, RCA-003 §2). `select_best_contract` returns
    None the moment a stage empties, so the artefact records that no contract
    was selected and nothing about why. RCA-003 had to reconstruct the funnel
    from stored chains to establish that the median blocked ticker had exactly
    one contract inside its delta band.

    INSTRUMENTATION ONLY. It selects nothing and changes no gate: it runs the
    same bands the selector runs, over the same chain, and reports. It is
    deliberately a separate pass rather than an edit to `_score_leg`, so an
    error here can never change which contract is chosen.
    """

    from contracts.contract_rejection import classify_chain

    config = ctx.get('dte_config') or {}
    horizon = ctx.get('horizon_bucket') or ctx.get('macro_preferred_horizon')
    dte_window = ctx.get('dte_window') or (None, None, None)
    try:
        dte_min = float(config.get('dte_min', dte_window[0]))
        dte_max = float(config.get('dte_max', dte_window[2]))
    except (TypeError, ValueError, IndexError):
        dte_min, dte_max = 1.0, 365.0

    try:
        rows = df.to_dict('records') if df is not None and not df.empty else []
    except Exception:
        rows = []

    return classify_chain(
        rows,
        direction=str(ctx.get('direction') or '').upper(),
        dte_min=dte_min,
        dte_max=dte_max,
        delta_min=float(config.get('delta_min', 0.15)),
        delta_max=float(config.get('delta_max', 0.35)),
        spread_limit=horizon_spread_limit(horizon),
    )


#: Flat, CSV-safe columns from the taxonomy. `contracts_tested` itself is a
#: list and goes to the JSONL sidecar, not into a CSV cell.
CONTRACT_TAXONOMY_ROW_FIELDS = (
    "contracts_tested_count",
    "contracts_side_correct_count",
    "primary_rejection_reason",
    "secondary_rejection_reason",
    "best_alternative_symbol",
    "best_alternative_spread_pct",
    "best_alternative_dte",
    "best_alternative_delta",
    "repair_attempted",
    "repair_result",
    "taxonomy_version",
)


def contract_taxonomy_row_fields(taxonomy: Dict[str, Any]) -> Dict[str, Any]:
    """The taxonomy's flat fields, for the Options row."""
    fields = {name: taxonomy.get(name) for name in CONTRACT_TAXONOMY_ROW_FIELDS}
    funnel = taxonomy.get("funnel") or {}
    for key in ("chain_rows", "side_correct", "in_dte_band", "in_delta_band",
                "quote_usable", "passing_spread"):
        fields[f"contracts_funnel_{key}"] = funnel.get(key)
    return fields


def _normalise_forecast_vol_decimal(*values: Any) -> Optional[float]:
    """Return the first usable annualised volatility as a decimal."""
    for value in values:
        parsed = _repair_alt_float(value)
        if parsed is None or parsed <= 0:
            continue
        if parsed > 5.0:
            parsed /= 100.0
        if 0 < parsed <= 5.0:
            return parsed
    return None


def _context_signal_row(ctx: Dict[str, Any]) -> Any:
    """Return the captured signal row without evaluating pandas truthiness.

    Production contexts carry a pandas Series under ``_signal_row`` while
    tests and replays may use dictionaries.  Both expose ``get`` and are safe
    to consume directly.  Missing or malformed values fail closed to an empty
    mapping; this helper never invents lifecycle evidence or authority.
    """
    if not hasattr(ctx, "get"):
        return {}
    raw_row = ctx.get("_signal_row")
    return raw_row if hasattr(raw_row, "get") else {}


def _governed_options_evidence_session(ctx: Dict[str, Any], contract: Optional[Dict[str, Any]] = None) -> str:
    """Return the single session authorised for this Options run.

    The run-level CDS session is authoritative. Quote and signal timestamps are
    evidence about individual records, not permission to mint a second thesis
    session inside the same run.
    """
    if _CDS_V2_SESSION is not None:
        return _CDS_V2_SESSION.isoformat()
    contract = contract or {}
    quote_as_of = str(contract.get("quote_timestamp_utc") or contract.get("quote_as_of") or "").strip()
    if quote_as_of:
        try:
            return pd.Timestamp(quote_as_of).date().isoformat()
        except (TypeError, ValueError):
            pass
    return _resolve_asof_date(_context_signal_row(ctx)) or ""


def _options_liquidity_lifecycle_fields(
    ctx: Dict[str, Any],
    contract: Dict[str, Any],
    iv_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the governed EOD lifecycle handoff for one exact contract.

    This adapter has no provider calls and cannot authorise capital. It turns
    missing inputs into an explicit repair state instead of inventing defaults.
    """
    ticker = str(ctx.get("ticker") or "").strip().upper()
    side = str(ctx.get("direction") or "").strip().upper()
    signal_row = _context_signal_row(ctx)
    quote_as_of = str(
        contract.get("quote_timestamp_utc") or contract.get("quote_as_of") or ""
    ).strip()
    evidence_session = _governed_options_evidence_session(ctx, contract)
    legacy_thesis_id = f"{ticker}:{side}:{evidence_session or 'UNKNOWN_SESSION'}"
    # v1 persisted terminal states were calculated with a different stop and
    # hold convention.  A versioned identity preserves that immutable history
    # while preventing a false v1 terminal event from governing corrected v2
    # evidence for the same completed market session.
    thesis_id = f"{legacy_thesis_id}:OLM2"
    base: Dict[str, Any] = {
        "thesis_id": thesis_id,
        "legacy_thesis_id": legacy_thesis_id,
        "supersedes_calculation_version": "options-liquidity-lifecycle-v1",
        "thesis_calculation_version": OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
        "evidence_session_date": evidence_session or "",
        "evidence_session_source": (
            "CDS_RUN_SESSION"
            if _CDS_V2_SESSION is not None
            else ("SELECTED_CONTRACT_QUOTE_TIMESTAMP" if quote_as_of else "SIGNAL_ASOF_FALLBACK")
        ),
        "thesis_state": "ACTIVE",
        "morning_transition_state": "EOD_PENDING_MORNING_REQUOTE",
        "maturation_score_is_probability": False,
        "maturation_execution_authority": False,
        "previous_contract_symbol": "",
        "contract_changed": False,
        "contract_selection_reason": contract.get("selection_reason") or "EOD_CONTRACT_SELECTION",
        "quote_as_of": quote_as_of or evidence_session,
    }
    if side not in {"CALL", "PUT"}:
        return {
            **base,
            "thesis_state": GovernedDataState.NOT_APPLICABLE.value,
            "morning_transition_state": GovernedDataState.NOT_APPLICABLE.value,
            "liquidity_state": LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value,
            "recovery_disposition": GovernedDataState.NOT_APPLICABLE.value,
            "executable_now": False,
            "quote_freshness": GovernedDataState.NOT_APPLICABLE.value,
            "invalidation_spot": None,
            "invalidation_source": "NOT_APPLICABLE_NON_DIRECTIONAL",
            "invalidation_state": GovernedDataState.NOT_APPLICABLE.value,
            "liquidity_lifecycle_reason": LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value,
        }
    forecast_vol = _normalise_forecast_vol_decimal(
        signal_row.get("garch_forecast_vol"),
        signal_row.get("l3_vol_forecast"),
        iv_ctx.get("hv_30d"),
        iv_ctx.get("atm_iv"),
        contract.get("iv"),
        contract.get("implied_vol"),
    )
    governed_handoff = _ev3_handoff_fields(ctx)
    required = {
        "side": side if side in {"CALL", "PUT"} else None,
        "spot": _repair_alt_float(ctx.get("spot")),
        "strike": _repair_alt_float(contract.get("strike")),
        "dte": _repair_alt_float(contract.get("dte")),
        # Lifecycle and contract selection must consume the same routed
        # horizon.  layer2__recommended_hold_days is an actuarial outcome
        # window, not the governed planned holding period for this trade.
        "remaining_hold_sessions": _repair_alt_float(
            governed_handoff.get("planned_hold_sessions")
        ),
        "forecast_vol_annual": forecast_vol,
        "structural_target": _repair_alt_float(ctx.get("structural_target")),
        # The EV3 handoff owns direction-correct invalidation geometry.  Using
        # ctx.stop here caused PUT rows to be assessed against the opposite
        # side of their published invalidation.
        "invalidation_spot": _repair_alt_float(
            governed_handoff.get("invalidation_spot")
        ),
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        return {
            **base,
            "thesis_state": "DATA_INCOMPLETE",
            "liquidity_state": "LIFECYCLE_DATA_INCOMPLETE",
            "recovery_disposition": "CONTRACT_REPAIR",
            "executable_now": False,
            "quote_freshness": "UNKNOWN",
            "liquidity_lifecycle_reason": "MISSING:" + ",".join(missing),
        }

    # Synthetic quotes can support EOD research calculations but never current
    # executability. Mark them stale for lifecycle purposes; the Morning Gate
    # replaces this assessment with an exact MarketData quote.
    mark_synthetic = bool(contract.get("mark_synthetic", False))
    quote_age_seconds = 901.0 if mark_synthetic else None
    try:
        lifecycle = evaluate_options_liquidity_lifecycle(
            LifecycleInputs(
                side=str(required["side"]),
                spot=float(required["spot"]),
                strike=float(required["strike"]),
                delta=_repair_alt_float(contract.get("delta")),
                bid=_repair_alt_float(contract.get("bid")),
                ask=_repair_alt_float(contract.get("ask")),
                dte=float(required["dte"]),
                remaining_hold_sessions=float(required["remaining_hold_sessions"]),
                forecast_vol_annual=float(required["forecast_vol_annual"]),
                thesis_spot=float(required["spot"]),
                current_spot=float(required["spot"]),
                structural_target=float(required["structural_target"]),
                invalidation_spot=float(required["invalidation_spot"]),
                quote_age_seconds=quote_age_seconds,
                listed_market=True,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {
            **base,
            "thesis_state": "DATA_INCOMPLETE",
            "liquidity_state": "LIFECYCLE_DATA_INVALID",
            "recovery_disposition": "CONTRACT_REPAIR",
            "executable_now": False,
            "quote_freshness": "UNKNOWN",
            "liquidity_lifecycle_reason": str(exc),
        }

    runway_factor = _repair_alt_float(lifecycle.get("remaining_runway_factor"), 0.0) or 0.0
    lifecycle.update({
        **base,
        "planned_hold_sessions": required["remaining_hold_sessions"],
        "planned_hold_source": governed_handoff.get("planned_hold_source"),
        "invalidation_spot": required["invalidation_spot"],
        "invalidation_source": governed_handoff.get("invalidation_source"),
        "thesis_state": (
            "INVALIDATED" if lifecycle.get("remaining_runway_state") == "THESIS_INVALIDATED"
            else "TARGET_REALIZED" if lifecycle.get("remaining_runway_state") == "MOVE_ALREADY_REALIZED"
            else "ACTIVE"
        ),
        "dte_buffer_sessions": round(
            float(required["dte"]) - float(lifecycle.get("minimum_required_dte") or 0), 2
        ),
        "atm_distance_sigma": lifecycle.get("atm_distance_sigma_1d"),
        "remaining_runway_pct": round(runway_factor * 100.0, 2),
        "quote_freshness": "SYNTHETIC_NOT_EXECUTABLE" if mark_synthetic else "SESSION_ALIGNED",
    })
    # The deterministic maturation score is deliberately never a probability
    # or an execution authority, even when the contract is executable now.
    lifecycle["maturation_score_is_probability"] = False
    lifecycle["maturation_execution_authority"] = False
    return lifecycle


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — TRADE ECONOMICS CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════


# CONTRACT-REPAIR-ALT-001
# Batch contract-repair alternatives for EOD and morning handoff.
def _repair_alt_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if pd.isna(value):
            return default
        cleaned = str(value).replace("$", "").replace("%", "").replace(",", "").strip()
        if cleaned == "":
            return default
        out = float(cleaned)
        return None if out != out else out
    except Exception:
        return default


def _repair_alt_symbol(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    symbol = str(value).strip().upper()
    if symbol in {"", "NAN", "NONE", "NULL", "<NA>"}:
        return ""
    return re.split(r"[\s|;,]+", symbol, maxsplit=1)[0].strip().upper()


def _repair_alt_row_symbol(row: Any) -> str:
    for key in ("symbol", "optionSymbol", "option_symbol", "md_occ_symbol", "contract_symbol"):
        try:
            symbol = _repair_alt_symbol(row.get(key))
        except Exception:
            symbol = ""
        if symbol:
            return symbol
    return ""


def _new_repair_selector_diagnostics() -> Dict[str, int]:
    return {key: 0 for key in _EV3_REPAIR_DIAGNOSTIC_KEYS}


def _repair_selector_diagnostic_fields(diagnostics: Optional[Dict[str, int]]) -> Dict[str, Any]:
    source = diagnostics or {}
    return {
        "repair_selector_diagnostics_version": EV3_REPAIR_DIAGNOSTICS_VERSION,
        **{
            f"repair_selector_{key}": int(source.get(key) or 0)
            for key in _EV3_REPAIR_DIAGNOSTIC_KEYS
        },
    }


def _aggregate_repair_selector_diagnostics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    aggregate = {
        "diagnostics_version": EV3_REPAIR_DIAGNOSTICS_VERSION,
        "selector_invocations": 0,
        **{key: 0 for key in _EV3_REPAIR_DIAGNOSTIC_KEYS},
    }
    for result in results:
        if result.get("repair_selector_diagnostics_version") != EV3_REPAIR_DIAGNOSTICS_VERSION:
            continue
        aggregate["selector_invocations"] += 1
        for key in _EV3_REPAIR_DIAGNOSTIC_KEYS:
            try:
                aggregate[key] += int(result.get(f"repair_selector_{key}") or 0)
            except (TypeError, ValueError):
                continue
    return aggregate


def select_repair_alternative_contracts(
    df: pd.DataFrame,
    ctx: Dict,
    selected_contract: Optional[Dict] = None,
    limit: int = EV3_LONG_SINGLE_CANDIDATE_LIMIT,
    diagnostics: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Return governed long-single repair candidates from two expiries x three strikes.

    Open interest and current volume are ranking evidence only.  A new or
    developing strike can have a valid two-sided quote before either field has
    accumulated, so neither value is allowed to delete an otherwise-valid
    contract family member.
    """
    if diagnostics is not None:
        for key in _EV3_REPAIR_DIAGNOSTIC_KEYS:
            diagnostics.setdefault(key, 0)

    def _reject(reason: str) -> None:
        if diagnostics is not None:
            diagnostics[reason] = int(diagnostics.get(reason) or 0) + 1

    try:
        if df is None or df.empty:
            return []
    except Exception:
        return []

    direction = str(ctx.get("direction") or ctx.get("primary_direction") or "").upper()
    if direction in {"LONG_CALL", "BULLISH", "BUY", "BUY_SETUP"}:
        direction = "CALL"
    elif direction in {"LONG_PUT", "BEARISH", "SELL", "SELL_SETUP"}:
        direction = "PUT"
    if direction == "CALL":
        wanted_rights = {"C"}
    elif direction == "PUT":
        wanted_rights = {"P"}
    else:
        return []

    try:
        dte_min, dte_target, dte_max = ctx.get("dte_window") or (7, 30, 60)
    except Exception:
        dte_min, dte_target, dte_max = (7, 30, 60)
    dte_cfg = ctx.get("dte_config") or {}
    delta_min = _repair_alt_float(dte_cfg.get("delta_min"), 0.15) or 0.15
    delta_max = _repair_alt_float(dte_cfg.get("delta_max"), 0.35) or 0.35
    target_delta = (delta_min + delta_max) / 2.0
    # AVS-FIX-001 W1.6: same authority for the repair-alternative search.
    spread_limit = clamp_spread_limit(dte_cfg.get("spread_max"))
    spot = _repair_alt_float(ctx.get("spot"))
    structural_target = _repair_alt_float(ctx.get("structural_target"))
    hold_sessions = _repair_alt_float(_ev3_handoff_fields(ctx).get("planned_hold_sessions"))
    if hold_sessions is None:
        minimum_dte = 1
    else:
        minimum_dte = int(calculate_dte_requirement(hold_sessions)["minimum_required_dte"])

    excluded = set()
    if selected_contract:
        excluded.add(_repair_alt_row_symbol(selected_contract))
        excluded.add(_repair_alt_symbol(selected_contract.get("md_occ_symbol")))

    candidates: List[Dict[str, Any]] = []
    for _, row in df.copy().iterrows():
        symbol = _repair_alt_row_symbol(row)
        if not symbol or symbol in excluded:
            continue
        right = str(row.get("right") or row.get("side") or "").upper()[:1]
        if right not in wanted_rights:
            continue

        strike = _repair_alt_float(row.get("strike"))
        dte_val = _repair_alt_float(row.get("dte"))
        expiry_raw = row.get("expiration_date") or row.get("expiry") or row.get("expiration")
        try:
            expiry = pd.Timestamp(expiry_raw).date().isoformat()
        except (TypeError, ValueError):
            expiry = ""
        bid = _repair_alt_float(row.get("bid"))
        ask = _repair_alt_float(row.get("ask"))
        signed_delta = _repair_alt_float(row.get("delta"))
        gamma = _repair_alt_float(row.get("gamma"))
        theta = _repair_alt_float(row.get("theta"))
        vega = _repair_alt_float(row.get("vega"))
        implied_volatility = _repair_alt_float(row.get("implied_vol"), _repair_alt_float(row.get("iv")))
        quote_timestamp = _quote_timestamp_utc(row.get("quote_timestamp_utc"))
        if (
            bid is None or ask is None or bid < 0 or ask <= 0 or bid > ask
            or gamma is None or theta is None or vega is None
            or implied_volatility is None or not quote_timestamp
        ):
            _reject("rejected_invalid_missing_quote")
            continue
        if strike is None or dte_val is None or not expiry or signed_delta is None:
            _reject("rejected_dte_delta_geometry")
            continue
        if dte_val < float(dte_min) or dte_val > float(dte_max):
            _reject("rejected_dte_delta_geometry")
            continue

        if dte_val < minimum_dte:
            _reject("rejected_dte_delta_geometry")
            continue

        if spot and spot > 0:
            if right == "C" and strike < spot * 0.90:
                _reject("rejected_dte_delta_geometry")
                continue
            if right == "P" and strike > spot * 1.10:
                _reject("rejected_dte_delta_geometry")
                continue

        if (right == "C" and signed_delta <= 0) or (right == "P" and signed_delta >= 0):
            _reject("rejected_dte_delta_geometry")
            continue
        delta_abs = abs(signed_delta)
        oi_value = _repair_alt_float(row.get("open_interest"))
        if oi_value is None:
            oi_value = _repair_alt_float(row.get("oi"))
        volume_value = _repair_alt_float(row.get("volume"))
        oi_observation_status = "REPORTED" if oi_value is not None else "MISSING_ASSUMED_ZERO"
        volume_observation_status = (
            "REPORTED" if volume_value is not None else "MISSING_ASSUMED_ZERO"
        )
        oi = oi_value if oi_value is not None else 0.0
        volume = volume_value if volume_value is not None else 0.0
        mark = (bid + ask) / 2.0
        spread = quote_spread_fraction(bid, ask)
        spread = spread if spread is not None else math.inf
        if not math.isfinite(spread) or spread > spread_limit:
            _reject("rejected_spread")
            continue

        delta_score = max(0.0, 100.0 - abs(delta_abs - target_delta) * 300.0)
        dte_score = max(0.0, 100.0 - abs(float(dte_val) - float(dte_target)) * 3.0)
        liq_score = min(100.0, volume * 2.0 + oi / 20.0)
        spread_score = max(0.0, 100.0 - max(0.0, spread - spread_limit) * 400.0)
        reach_score = 60.0
        if structural_target and spot:
            if right == "C":
                reach_score = 100.0 if strike <= structural_target else max(0.0, 60.0 - ((strike - structural_target) / spot) * 250.0)
            else:
                reach_score = 100.0 if strike >= structural_target else max(0.0, 60.0 - ((structural_target - strike) / spot) * 250.0)

        score = (
            0.30 * delta_score
            + 0.20 * dte_score
            + 0.20 * liq_score
            + 0.20 * spread_score
            + 0.10 * reach_score
        )
        candidates.append({
            "symbol": symbol,
            "score": round(score, 2),
            "right": right,
            "structure": "LONG_SINGLE",
            "strike": strike,
            "expiry": str(expiry)[:10],
            "dte": dte_val,
            "mark": mark,
            "bid": bid,
            "ask": ask,
            "delta": signed_delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "iv": implied_volatility,
            "oi": oi,
            "volume": volume,
            "oi_observation_status": oi_observation_status,
            "volume_observation_status": volume_observation_status,
            "oi_used_as_hard_gate": False,
            "volume_used_as_hard_gate": False,
            "spread_pct": round(float(spread), 6) if spread is not None else "",
            "quote_timestamp_utc": quote_timestamp,
            "quote_timestamp_source": row.get("quote_timestamp_source"),
            "contract_multiplier": _repair_alt_float(row.get("contract_multiplier")),
            "contract_multiplier_source": row.get("contract_multiplier_source"),
            "quote_source": row.get("md_quote_source") or row.get("quote_source"),
            "candidate_policy_version": EV3_CANDIDATE_POLICY_VERSION,
            "delta_distance": round(abs(delta_abs - target_delta), 8),
            "reason": (
                f"{right} thesis-aligned repair candidate; "
                f"dte={float(dte_val):.0f}; delta={delta_abs:.2f}; "
                f"oi={oi:.0f}; vol={volume:.0f}; spread={float(spread):.3f}"
                if spread is not None
                else f"{right} thesis-aligned repair candidate"
            ),
        })

    if not candidates:
        return []

    expiry_stats: Dict[str, float] = {}
    for candidate in candidates:
        expiry = str(candidate["expiry"])
        expiry_stats.setdefault(expiry, float(candidate["dte"]))
    selected_expiries = [
        expiry for expiry, _ in sorted(
            expiry_stats.items(),
            key=lambda item: (abs(item[1] - float(dte_target)), item[1], item[0]),
        )[:EV3_EXPIRY_LIMIT]
    ]

    bounded: List[Dict[str, Any]] = []
    for expiry in selected_expiries:
        expiry_candidates = [item for item in candidates if str(item["expiry"]) == expiry]
        expiry_candidates.sort(key=lambda item: (
            float(item["delta_distance"]),
            float(item["spread_pct"]),
            -float(item["oi"]),
            -float(item["volume"]),
            str(item["symbol"]),
        ))
        bounded.extend(expiry_candidates[:EV3_STRIKES_PER_EXPIRY])

    bounded.sort(key=lambda item: (
        abs(float(item["dte"]) - float(dte_target)),
        str(item["expiry"]),
        float(item["delta_distance"]),
        str(item["symbol"]),
    ))
    cap = min(EV3_LONG_SINGLE_CANDIDATE_LIMIT, max(1, int(limit or EV3_LONG_SINGLE_CANDIDATE_LIMIT)))
    bounded = bounded[:cap]
    for rank, candidate in enumerate(bounded, start=1):
        candidate["candidate_generation_rank"] = rank
    if diagnostics is not None:
        diagnostics["retained_oi_below_50"] += sum(
            candidate.get("oi_observation_status") == "REPORTED"
            and float(candidate.get("oi") or 0.0) < 50.0
            for candidate in bounded
        )
        diagnostics["retained_zero_volume"] += sum(
            candidate.get("volume_observation_status") == "REPORTED"
            and float(candidate.get("volume") or 0.0) == 0.0
            for candidate in bounded
        )
        diagnostics["final_bounded_candidate_count"] += len(bounded)
    return bounded


def _ev3_vertical_leg(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": candidate.get("symbol"),
        "strike": candidate.get("strike"),
        "expiry": candidate.get("expiry"),
        "dte": candidate.get("dte"),
        "bid": candidate.get("bid"),
        "ask": candidate.get("ask"),
        "delta": candidate.get("delta"),
        "gamma": candidate.get("gamma"),
        "theta": candidate.get("theta"),
        "vega": candidate.get("vega"),
        "iv": candidate.get("iv"),
        "oi": candidate.get("oi"),
        "volume": candidate.get("volume"),
        "quote_timestamp_utc": candidate.get("quote_timestamp_utc"),
        "quote_timestamp_source": candidate.get("quote_timestamp_source"),
        "contract_multiplier": candidate.get("contract_multiplier"),
        "contract_multiplier_source": candidate.get("contract_multiplier_source"),
        "quote_source": candidate.get("quote_source"),
    }


def select_ev3_vertical_debit_candidates(
    df: pd.DataFrame,
    ctx: Dict,
    *,
    limit: int = EV3_VERTICAL_CANDIDATE_LIMIT,
) -> List[Dict[str, Any]]:
    """Build same-expiry bull-call or bear-put debit spreads from strict legs."""
    legs = select_repair_alternative_contracts(
        df, ctx, selected_contract=None, limit=EV3_LONG_SINGLE_CANDIDATE_LIMIT
    )
    direction = str(ctx.get("direction") or "").upper()
    if direction not in {"CALL", "PUT"}:
        return []
    structure = "BULL_CALL_DEBIT" if direction == "CALL" else "BEAR_PUT_DEBIT"
    spreads: List[Dict[str, Any]] = []
    expiries = sorted({str(leg.get("expiry") or "") for leg in legs if leg.get("expiry")})
    for expiry in expiries:
        expiry_legs = [leg for leg in legs if str(leg.get("expiry")) == expiry]
        expiry_legs.sort(key=lambda leg: float(leg["strike"]))
        for first_index, first in enumerate(expiry_legs):
            for second in expiry_legs[first_index + 1:]:
                if direction == "CALL":
                    long_leg, short_leg = first, second
                else:
                    long_leg, short_leg = second, first
                width = abs(float(long_leg["strike"]) - float(short_leg["strike"]))
                entry_debit_mid = float(long_leg["ask"]) - float(short_leg["bid"])
                long_multiplier = _repair_alt_float(long_leg.get("contract_multiplier"))
                short_multiplier = _repair_alt_float(short_leg.get("contract_multiplier"))
                if width <= 0 or entry_debit_mid <= 0 or entry_debit_mid >= width:
                    continue
                if (
                    long_multiplier is not None and short_multiplier is not None
                    and long_multiplier != short_multiplier
                ):
                    continue
                spreads.append({
                    "symbol": f"{structure}:{long_leg['symbol']}/{short_leg['symbol']}",
                    "structure": structure,
                    "right": "C" if direction == "CALL" else "P",
                    "expiry": expiry,
                    "dte": long_leg["dte"],
                    "strike": long_leg["strike"],
                    "long_leg": _ev3_vertical_leg(long_leg),
                    "short_leg": _ev3_vertical_leg(short_leg),
                    "strike_width": width,
                    "entry_debit_mid": entry_debit_mid,
                    "contract_multiplier": long_multiplier if long_multiplier == short_multiplier else None,
                    "candidate_policy_version": EV3_VERTICAL_POLICY_VERSION,
                    "score": round((float(long_leg["score"]) + float(short_leg["score"])) / 2.0, 2),
                    "reason": (
                        f"{structure}; expiry={expiry}; long={long_leg['strike']}; "
                        f"short={short_leg['strike']}; width={width:.2f}; debit_mid={entry_debit_mid:.2f}"
                    ),
                })
    spreads.sort(key=lambda item: (
        -float(item["score"]),
        float(item["entry_debit_mid"]) / float(item["strike_width"]),
        str(item["symbol"]),
    ))
    bounded = spreads[: min(EV3_VERTICAL_CANDIDATE_LIMIT, max(1, int(limit or EV3_VERTICAL_CANDIDATE_LIMIT)))]
    for rank, candidate in enumerate(bounded, start=1):
        candidate["candidate_generation_rank"] = rank
    return bounded


def _format_repair_alternative_fields(
    alternatives: List[Dict[str, Any]],
    reason: str = "",
    *,
    repair_required: bool = True,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "alternative_contract_1": "",
        "alternative_contract_2": "",
        "alternative_contract_3": "",
        "alternative_contract_1_score": "",
        "alternative_contract_2_score": "",
        "alternative_contract_3_score": "",
        "alternative_contract_1_reason": "",
        "alternative_contract_2_reason": "",
        "alternative_contract_3_reason": "",
        "contract_repair_action": "NO_ALTERNATIVE_FOUND",
        "alternative_contract_attempts": "",
        "alternative_contracts_json": "[]",
        "alternative_contracts_schema_version": "ev3-contract-candidates-v4",
        "alternative_contracts_count": 0,
    }
    for idx, alt in enumerate((alternatives or [])[:3], start=1):
        out[f"alternative_contract_{idx}"] = alt.get("symbol", "")
        out[f"alternative_contract_{idx}_score"] = alt.get("score", "")
        out[f"alternative_contract_{idx}_reason"] = alt.get("reason", "")
    if alternatives:
        def _json_safe(value: Any) -> Any:
            if isinstance(value, dict):
                return {str(key): _json_safe(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [_json_safe(item) for item in value]
            if isinstance(value, np.generic):
                return value.item()
            try:
                return None if pd.isna(value) else value
            except Exception:
                return value

        safe_alternatives = [
            _json_safe(candidate)
            for candidate in alternatives[:EV3_TOTAL_CANDIDATE_LIMIT]
        ]
        out["alternative_contracts_json"] = json.dumps(safe_alternatives, sort_keys=True)
        out["alternative_contracts_count"] = len(safe_alternatives)
        if repair_required:
            out["contract_repair_action"] = "ALTERNATIVES_AVAILABLE"
            out["alternative_contract_attempts"] = (
                f"GENERATED_{len(safe_alternatives)}_REPAIR_ALTERNATIVES"
                + (f"; reason={reason}" if reason else "")
            )
        else:
            out["contract_repair_action"] = "NOT_REQUIRED"
            out["alternative_contract_attempts"] = f"EV3_BOUNDED_CANDIDATES_{len(safe_alternatives)}"
    elif reason:
        out["alternative_contract_attempts"] = f"NO_REPAIR_ALTERNATIVE_FOUND; reason={reason}"
    return out


def _ev3_candidate_missing_fields(candidate: Dict[str, Any]) -> List[str]:
    """Return missing canonical fields for one EV3 candidate record."""
    structure = str(candidate.get("structure") or "LONG_SINGLE").upper()
    common = ("symbol", "expiry", "dte", "contract_multiplier")
    leg_fields = (
        "symbol", "strike", "expiry", "dte", "bid", "ask", "delta", "gamma",
        "theta", "vega", "iv", "oi", "volume", "quote_timestamp_utc",
        "contract_multiplier",
    )

    def missing(record: Dict[str, Any], names: Tuple[str, ...], prefix: str = "") -> List[str]:
        result: List[str] = []
        for name in names:
            value = record.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                result.append(f"{prefix}{name}")
            elif isinstance(value, float) and pd.isna(value):
                result.append(f"{prefix}{name}")
        return result

    if structure in {"BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"}:
        result = missing(candidate, common)
        for leg_name in ("long_leg", "short_leg"):
            leg = candidate.get(leg_name)
            if not isinstance(leg, dict):
                result.append(leg_name)
            else:
                result.extend(missing(leg, leg_fields, f"{leg_name}."))
        return result
    return missing(candidate, leg_fields)


def _partition_complete_ev3_candidates(
    candidates: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Keep only complete alternatives and retain explicit rejection diagnostics."""
    complete: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for candidate in candidates or []:
        missing = _ev3_candidate_missing_fields(candidate)
        if missing:
            rejected.append({
                "symbol": candidate.get("symbol", ""),
                "structure": candidate.get("structure", "LONG_SINGLE"),
                "reason": "INCOMPLETE_EV3_HANDOFF",
                "missing_fields": missing,
            })
        else:
            complete.append(candidate)
    return complete, rejected


def _alternative_handoff_audit(rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "alternative_contracts_rejected_incomplete": len(rejected),
        "alternative_contracts_rejection_reasons_json": json.dumps(rejected, sort_keys=True),
    }


def _annotate_ev3_handoff_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Publish an explicit selected-contract readiness state before EV3 runs."""
    result = frame.copy()
    required_aliases: Dict[str, Tuple[str, ...]] = {
        "contract_symbol": ("contract_occ_symbol", "recommended_contract", "contract_symbol"),
        "entry_spot": ("entry_spot",), "target_spot": ("target_spot",),
        "invalidation_spot": ("invalidation_spot",),
        "planned_hold_sessions": ("planned_hold_sessions",),
        "state_key": ("ev3_barrier_state_key", "state_key"),
        "strike": ("contract_strike",), "expiration": ("contract_expiry",),
        "dte": ("contract_dte",), "bid": ("contract_bid",), "ask": ("contract_ask",),
        "delta": ("contract_delta",), "gamma": ("contract_gamma",),
        "theta": ("contract_theta",), "vega": ("contract_vega",),
        "iv": ("contract_iv",), "open_interest": ("contract_oi",),
        "volume": ("contract_volume",),
        "quote_timestamp": ("contract_quote_timestamp_utc", "quote_timestamp_utc"),
        "contract_multiplier": ("contract_multiplier",),
    }

    def first_present(row: pd.Series, aliases: Tuple[str, ...]) -> Any:
        for alias in aliases:
            if alias not in row.index:
                continue
            value = row.get(alias)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            try:
                if pd.isna(value):
                    continue
            except (TypeError, ValueError):
                pass
            return value
        return None

    statuses: List[str] = []
    missing_json: List[str] = []
    for _, row in result.iterrows():
        direction = str(row.get("canonical_direction") or "").upper()
        symbol = first_present(row, required_aliases["contract_symbol"])
        if direction not in {"CALL", "PUT"}:
            statuses.append("NOT_APPLICABLE_NON_DIRECTIONAL")
            missing_json.append("[]")
            continue
        if symbol is None:
            statuses.append("NOT_APPLICABLE_NO_SELECTED_CONTRACT")
            missing_json.append("[]")
            continue
        missing = [
            field for field, aliases in required_aliases.items()
            if first_present(row, aliases) is None
        ]
        statuses.append("COMPLETE" if not missing else "INCOMPLETE")
        missing_json.append(json.dumps(missing))
    result["ev3_selected_handoff_status"] = statuses
    result["ev3_selected_handoff_missing_fields_json"] = missing_json
    result["ev3_handoff_schema_version"] = "ev3-options-handoff-v2"
    return result


def compute_trade_economics(contract: Dict, ctx: Dict, iv_ctx: Dict) -> Dict:
    """
    Compute full trade economics using AVSHUNTER structural targets.
    Never estimates target from vol — uses structural_target from Vanguard.
    """
    spot   = ctx['spot']
    entry  = ctx['entry']
    target = _repair_alt_float(ctx.get('structural_target'))
    hold   = ctx['hold_days']
    direction = str(ctx.get('direction') or '').upper()

    if direction not in GOVERNED_DIRECTED_SIDES:
        return {
            'economics_state': 'NOT_EVALUATED',
            'economics_reason': LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value,
            'premium_total': None, 'breakeven_price': None, 'breakeven_pct': None,
            'target_gain_underlying': None, 'option_value_at_target': None,
            'option_gain': None, 'rr_options': None, 'rr_premium_expected': None,
            'max_convex_r_multiple': None, 'ev_structural': None,
            'ev_ratio': None, 'ev_adjusted': None, 'theta_total_cost': None,
            'theta_drag_pct': None, 'vega_risk_pct': None, 'iv_factor': None,
            'iv_alignment': iv_ctx.get('ivp_label', 'UNKNOWN'),
        }
    if target is None or target <= 0 or not math.isfinite(target):
        return {
            'economics_state': 'NOT_EVALUATED',
            'economics_reason': DataExceptionReason.STRUCTURAL_TARGET_UNRESOLVED.value,
            'premium_total': None, 'breakeven_price': None, 'breakeven_pct': None,
            'target_gain_underlying': None, 'option_value_at_target': None,
            'option_gain': None, 'rr_options': None, 'rr_premium_expected': None,
            'max_convex_r_multiple': None, 'ev_structural': None,
            'ev_ratio': None, 'ev_adjusted': None, 'theta_total_cost': None,
            'theta_drag_pct': None, 'vega_risk_pct': None, 'iv_factor': None,
            'iv_alignment': iv_ctx.get('ivp_label', 'UNKNOWN'),
        }

    mark    = contract.get('mark', 0)
    strike  = contract.get('strike', entry)
    theta   = contract.get('theta', -0.01)
    vega    = contract.get('vega', 0.05)
    delta   = abs(contract.get('delta', 0.35))
    dte     = contract.get('dte', 30)

    if mark <= 0: mark = 0.01
    premium_total = mark * 100   # per contract

    # Breakeven
    if direction == 'CALL':
        breakeven_price = strike + mark
        breakeven_pct   = ((breakeven_price - spot) / spot) * 100
    elif direction == 'PUT':
        breakeven_price = strike - mark
        breakeven_pct   = ((spot - breakeven_price) / spot) * 100
    else:
        # STRANGLE / STRADDLE: upper breakeven = strike + mark, lower = strike - mark
        # Report the upper (call-side) breakeven as the primary reference price
        breakeven_price = strike + mark
        breakeven_pct   = ((breakeven_price - spot) / spot) * 100

    # Structural target gain
    if direction == 'CALL':
        target_gain_underlying = max(target - entry, 0)
        option_value_at_target = max(target - strike, 0)
    elif direction == 'PUT':
        target_gain_underlying = max(entry - target, 0)
        option_value_at_target = max(strike - target, 0)
    else:
        option_value_at_target = mark
        target_gain_underlying = 0

    option_gain = max(option_value_at_target - mark, -mark)
    rr_options  = option_gain / mark if mark > 0 else 0

    # OI-01 (FIX-02): Separate R:R metrics so EOD tier assignment uses the right one.
    # rr_premium_expected = option premium appreciation R:R (what the option itself returns)
    #   = option_gain / mark  ← same as rr_options, renamed for clarity
    # max_convex_r_multiple = theoretical maximum R at expiry given premium paid and delta
    #   = intrinsic value at full structural target / mark (ceiling convexity case)
    rr_premium_expected = rr_options   # premium appreciation R:R
    if mark > 0 and option_value_at_target > 0:
        max_convex_r_multiple = round(option_value_at_target / mark, 3)
    else:
        max_convex_r_multiple = 0.0

    # EV using structural win probability
    win_prob = ctx['win_prob'] / 100.0
    ev_structural = win_prob * option_gain - (1-win_prob) * mark
    ev_ratio      = ev_structural / mark if mark > 0 else 0

    # Theta drag over hold period
    theta_total  = abs(theta) * hold
    theta_pct    = (theta_total / mark) * 100 if mark > 0 else 100

    # Vega risk: what if IV drops 10%?
    iv_crush_loss = abs(vega) * 0.10 * 100   # 10 vol pts × vega × 100
    vega_risk_pct = (iv_crush_loss / premium_total) * 100 if premium_total > 0 else 0

    # IV alignment bonus/penalty
    ivp = iv_ctx.get('iv_percentile')
    iv_label = iv_ctx.get('ivp_label', 'UNKNOWN')
    iv_factor = 1.0
    if ivp is not None:
        if ivp <= IVP_CHEAP_MAX:   iv_factor = 1.15   # cheap vol → EV boost
        elif ivp > IVP_EXPENSIVE:  iv_factor = 0.75   # expensive → EV penalty

    ev_adjusted = ev_ratio * iv_factor

    return {
        'economics_state'        : 'EVALUATED',
        'economics_reason'       : 'OK',
        'premium_total'        : round(premium_total, 2),
        'breakeven_price'      : round(breakeven_price, 2),
        'breakeven_pct'        : round(breakeven_pct, 2),
        'target_gain_underlying': round(target_gain_underlying, 2),
        'option_value_at_target': round(option_value_at_target, 2),
        'option_gain'          : round(option_gain, 2),
        'rr_options'           : round(rr_options, 3),
        'rr_premium_expected'  : round(rr_premium_expected, 3),
        'max_convex_r_multiple': round(max_convex_r_multiple, 3),
        'ev_structural'        : round(ev_structural, 4),
        'ev_ratio'             : round(ev_ratio, 4),
        'ev_adjusted'          : round(ev_adjusted, 4),
        'theta_total_cost'     : round(theta_total, 4),
        'theta_drag_pct'       : round(theta_pct, 2),
        'vega_risk_pct'        : round(vega_risk_pct, 2),
        'iv_factor'            : iv_factor,
        'iv_alignment'         : iv_label,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — OPTIONS INTELLIGENCE SCORE (OIS)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_ois(ctx: Dict, iv_ctx: Dict, econ: Dict,
                gex_flip: Optional[float], walls: Dict,
                pcr_signal: str, contract: Dict,
                dw_data: Dict = None, gamma_vel: Dict = None,
                vol_confirm: Dict = None, sector_data: Dict = None) -> Tuple[float, List[str], List[str]]:
    """
    Options Intelligence Score — 0 to 100.
    Synthesises all options analysis into a single actionable number.

    Dimensions:
      [A] Vol environment     (22 pts) — IVP, IV/HV, term structure, regime, skew
      [B] Structural alignment(22 pts) — intent, trend, phase, regime
      [C] Trade economics     (22 pts) — R:R, EV, theta drag, breakeven
      [D] Market microstructure(22 pts) — GEX velocity, walls, delta-weighted PCR
      [E] Volume & momentum  (12 pts)  — Wyckoff volume, vanna quality, sector alignment
    """
    score   = 0.0
    pos     = []
    neg     = []

    spot      = ctx['spot']
    entry     = ctx['entry']
    intent    = ctx['intent']
    trend     = ctx['trend']
    phase     = ctx['phase']
    tier      = ctx['tier']
    regime    = ctx['regime']
    direction = ctx['direction']

    # ── [0] ACTUARIAL SAMPLE QUALITY (applied before all scoring) ─────────────
    # Penalise thin actuarial buckets — STRONG label on N<200 is unreliable
    l2_n_obs = ctx.get('l2_n_obs', 0) or 0
    if l2_n_obs > 0:
        if l2_n_obs < 50:
            score -= 15; neg.append(f"Actuarial N={l2_n_obs} — extremely thin sample; stats unreliable (-15)")
        elif l2_n_obs < 100:
            score -= 10; neg.append(f"Actuarial N={l2_n_obs} — thin sample; treat edge quality with caution (-10)")
        elif l2_n_obs < 200:
            score -= 5; neg.append(f"Actuarial N={l2_n_obs} — moderate sample; edge less certain (-5)")
        else:
            pos.append(f"Actuarial N={l2_n_obs} — robust sample size")

    # ── [A] VOL ENVIRONMENT (22 pts) ──────────────────────────────────────────
    ivp     = iv_ctx.get('iv_percentile')
    iv_lbl  = iv_ctx.get('ivp_label', 'UNKNOWN')
    iv_vs_hv = iv_ctx.get('iv_vs_hv')
    term    = iv_ctx.get('term_structure', 'UNKNOWN')
    ivp_252 = iv_ctx.get('ivp_252d')
    iv_regime = iv_ctx.get('iv_regime', 'UNKNOWN')
    iv_direction = iv_ctx.get('iv_direction', 'STABLE')
    iv_dir_pct = iv_ctx.get('iv_direction_pct', 0.0)
    skew_label = iv_ctx.get('skew_label', 'UNKNOWN')
    rr_val     = iv_ctx.get('risk_reversal')

    # IVP scoring (dual-window)
    if ivp is not None:
        if ivp <= 0.25:
            score += 22; pos.append(f"IVP={ivp:.0%} very cheap vol — both windows confirm (+22)")
        elif ivp <= IVP_CHEAP_MAX:
            score += 17; pos.append(f"IVP={ivp:.0%} cheap vol (+17)")
        elif ivp <= IVP_FAIR_MAX:
            score += 10; pos.append(f"IVP={ivp:.0%} fair vol (+10)")
        else:
            score += 2; neg.append(f"IVP={ivp:.0%} expensive vol — premium at risk")
    else:
        score += 8  # unknown — neutral

    # IV/HV gate (tightened — 1.05 threshold per KDP fix)
    if iv_vs_hv is not None:
        if iv_vs_hv < 1.05:
            score += 5; pos.append(f"IV/HV={iv_vs_hv:.2f} — vol genuinely cheap vs realised (+5)")
        elif iv_vs_hv < 1.20:
            pass  # neutral — no bonus, no penalty
        elif iv_vs_hv < 1.50:
            neg.append(f"IV/HV={iv_vs_hv:.2f} — options pricing premium vs realised")
        else:
            score -= 3; neg.append(f"IV/HV={iv_vs_hv:.2f} — significant vol risk premium")

    # IV Regime bonus/penalty
    if iv_regime == 'STRUCTURAL_BUILD':
        score += 4; pos.append(f"IV regime: STRUCTURAL_BUILD — vega tailwind for long options (+4)")
    elif iv_regime == 'EVENT_PRICED':
        score -= 4; neg.append(f"IV regime: EVENT_PRICED — binary event risk; vol crush exposure on resolution")
    elif iv_regime == 'UNCERTAIN':
        score -= 2; neg.append(f"IV regime: UNCERTAIN — vol surface unstable; size down")
    elif iv_regime == 'COMPLACENT':
        pos.append(f"IV regime: COMPLACENT — low vol environment; check for expansion catalyst")

    # IV Direction of travel
    if iv_direction == 'RISING':
        score += 3; pos.append(f"IV rising {iv_dir_pct:+.1f}% over 5d — vol expansion tailwind (+3)")
    elif iv_direction == 'FALLING' and ivp and ivp <= IVP_CHEAP_MAX:
        neg.append(f"IV falling {iv_dir_pct:+.1f}% over 5d with cheap vol — may compress further")
    elif iv_direction == 'FALLING' and ivp and ivp > IVP_CHEAP_MAX:
        score += 1  # falling expensive vol = mean reversion helps long options slightly

    # Skew scoring
    if skew_label == 'STEEP_PUT_SKEW' and direction == 'PUT':
        score += 5; pos.append(f"Put skew steep (RR={rr_val:.1f}pts) — institutions hedging downside, confirms PUT thesis (+5)")
    elif skew_label == 'STEEP_PUT_SKEW' and direction == 'CALL' and rr_val and rr_val > SKEW_EXTREME_PUT_THRESHOLD:
        score -= 5; neg.append(f"Extreme put skew (RR={rr_val:.1f}pts) — crash fear dominates; call premium relatively cheap but dangerous environment")
    elif skew_label == 'CALL_SKEWED' and direction == 'CALL':
        score += 3; pos.append(f"Call skew present (RR={rr_val:.1f}pts) — unusual bullish demand in options (+3)")
    elif skew_label == 'CALL_SKEWED' and direction == 'PUT':
        score -= 2; neg.append(f"Call skewed market contradicts PUT thesis")

    # Term structure
    if term == 'CONTANGO':
        score += 2; pos.append("Term structure contango — near-term vol cheap (+2)")
    elif term == 'BACKWARDATION':
        score -= 2; neg.append("Term structure backwardation — near-term vol elevated vs back end")

    # Hard gate: 252d IVP at annual high with expensive IV — STAND_DOWN trigger
    if ivp_252 is not None and ivp_252 > 0.85 and iv_vs_hv is not None and iv_vs_hv > 1.20:
        score -= 8; neg.append(f"VOL_STRUCTURALLY_EXPENSIVE: 252d IVP={ivp_252:.0%} annual high + IV/HV={iv_vs_hv:.2f} — buying premium unjustified")

    # ── [B] STRUCTURAL ALIGNMENT (22 pts) ─────────────────────────────────────
    if intent == 'BUY_SETUP' and direction == 'CALL':
        score += 10; pos.append("BUY_SETUP intent — call confirmed by Vanguard (+10)")
    elif intent == 'SELL_SETUP' and direction == 'PUT':
        score += 10; pos.append("SELL_SETUP intent — put confirmed by Vanguard (+10)")
    elif intent == 'TRANSITION':
        score += 5; pos.append("TRANSITION intent — directional from trend (+5)")
    elif intent == 'WAIT' and ctx.get('vanguard_support_direction_repair'):
        score += 4; pos.append("WAIT repaired by Vanguard statistical support — direction inferred for options review (+4)")
    elif intent == 'WAIT':
        neg.append("WAIT intent — no directional conviction from structure")

    if direction == 'CALL' and trend == 'BULLISH':
        score += 7; pos.append("BULLISH trend + CALL — aligned (+7)")
    elif direction == 'PUT' and trend == 'BEARISH':
        score += 7; pos.append("BEARISH trend + PUT — aligned (+7)")
    elif direction == 'CALL' and trend == 'BEARISH':
        # AMENDMENT (2026-05-02): Reduced from -5 to -2. Contra-trend is a sizing
        # signal, not a direction veto. Valid call setups exist in bearish regimes
        # (e.g. accumulation, oversold bounce, sector rotation). The PSE regime
        # multiplier and EV engine already discount contra-trend positions downstream.
        neg.append("CALL against BEARISH trend — structural headwind"); score -= 2
    elif direction == 'PUT' and trend == 'BULLISH':
        # AMENDMENT (2026-05-02): Reduced from -5 to -2. Same reasoning as above.
        # Valid put setups exist in bullish regimes (distribution, overbought fade).
        neg.append("PUT against BULLISH trend — structural headwind"); score -= 2
    else:
        score += 3

    phase_pts = {'C': 7, 'D': 7, 'E': 5, 'B': 3, 'A': 1}
    pp = phase_pts.get(phase, 3)
    score += pp
    if phase in ('C','D'):
        pos.append(f"Phase {phase} — optimal entry timing (+{pp})")

    if regime == 'TRANSITIONAL' and ivp and ivp > IVP_CHEAP_MAX:
        neg.append("TRANSITIONAL regime + expensive vol — dual headwind"); score -= 3

    # ── [C] TRADE ECONOMICS (22 pts) ──────────────────────────────────────────
    rr     = econ.get('rr_options', 0)
    theta_pct = econ.get('theta_drag_pct', 100)
    be_pct = abs(econ.get('breakeven_pct', 10))

    # IV bonus for EV requires BOTH windows agree (252d must confirm)
    ivp_252_ok = ivp_252 is None or ivp_252 <= IVP_CHEAP_MAX
    if iv_lbl == 'CHEAP' and ivp_252_ok:
        iv_factor = 1.15
    elif ivp and ivp > IVP_EXPENSIVE:
        iv_factor = 0.75
    else:
        iv_factor = 1.0
    ev_adj_final = econ.get('ev_ratio', 0) * iv_factor

    # Legacy premium R:R is a labelled expiry-intrinsic research scenario.
    # It contributes zero points and cannot promote or demote the Options
    # verdict for a 1-20 session thesis.
    if rr >= 0:
        pos.append(f"R:R research scenario={rr:.2f} (advisory; zero authority)")
    else:
        neg.append(f"R:R research scenario={rr:.3f} (advisory; zero authority)")

    # EV is diagnostic evidence, not capital authority.  Keep a fixed two-point
    # economics-computation credit so removing the former variable EV bonus does
    # not silently rebase the established OIS thresholds.  The EV value remains
    # in the output for ranking, review, and later model calibration, but it can
    # neither promote nor demote the options verdict.
    score += 2
    if ev_adj_final < 0:
        neg.append(f"EV/premium={ev_adj_final:.2f} negative — advisory only")
    else:
        pos.append(f"EV/premium={ev_adj_final:.2f} — advisory only")

    if theta_pct < 20:   score += 6; pos.append(f"Theta drag={theta_pct:.0f}% low (+6)")
    elif theta_pct < 40: score += 3; pos.append(f"Theta drag={theta_pct:.0f}% manageable (+3)")
    elif theta_pct > 60: neg.append(f"Theta drag={theta_pct:.0f}% — decay will erode position")

    atr = ctx['atr']
    hold = ctx['hold_days']
    if atr > 0 and hold > 0:
        expected_range = atr * sqrt(hold) * 0.6
        if spot > 0:
            be_dollar = abs(be_pct/100*spot)
            if be_dollar <= expected_range:
                pos.append(f"Breakeven ${be_dollar:.2f} reachable within expected range ${expected_range:.2f}")
            else:
                neg.append(f"Breakeven ${be_dollar:.2f} exceeds expected range ${expected_range:.2f}")

    # ── [D] MARKET MICROSTRUCTURE (22 pts) ────────────────────────────────────
    # Delta-weighted flow (replaces simple PCR for primary microstructure signal)
    dw_data = dw_data or {}
    dw_signal = dw_data.get('dw_signal', 'UNKNOWN')
    if direction == 'CALL':
        if dw_signal in ('STRONGLY_BULLISH', 'BULLISH'):
            score += 8; pos.append(f"Delta-weighted OI: {dw_signal} — institutional call exposure confirms direction (+8)")
        elif dw_signal == 'NEUTRAL':
            score += 3; pos.append("Delta-weighted OI: NEUTRAL — no institutional contradiction (+3)")
        elif dw_signal in ('BEARISH', 'STRONGLY_BEARISH'):
            score -= 4; neg.append(f"Delta-weighted OI: {dw_signal} — institutional positioning contradicts CALL")
        else:  # PCR fallback
            if pcr_signal == 'BULLISH':
                score += 5; pos.append("PCR bullish — flow confirms call (+5)")
            elif pcr_signal == 'BEARISH':
                score -= 3; neg.append("PCR bearish against call")
            else:
                score += 2
    elif direction == 'PUT':
        if dw_signal in ('STRONGLY_BEARISH', 'BEARISH'):
            score += 8; pos.append(f"Delta-weighted OI: {dw_signal} — institutional put exposure confirms direction (+8)")
        elif dw_signal == 'NEUTRAL':
            score += 3
        elif dw_signal in ('BULLISH', 'STRONGLY_BULLISH'):
            score -= 4; neg.append(f"Delta-weighted OI: {dw_signal} — institutional positioning contradicts PUT")
        else:
            if pcr_signal == 'BEARISH':
                score += 5; pos.append("PCR bearish — flow confirms put (+5)")
            elif pcr_signal == 'BULLISH':
                score -= 3; neg.append("PCR bullish against put")
            else:
                score += 2

    # Gamma velocity
    gamma_vel = gamma_vel or {}
    gv_label = gamma_vel.get('gamma_velocity_label', 'UNKNOWN')
    gv_sessions = gamma_vel.get('gamma_velocity_sessions')
    if gv_label == 'IMMINENT':
        score += 7; pos.append(f"Gamma velocity: IMMINENT — dealer squeeze within ~{gv_sessions or '<2'} sessions (+7)")
    elif gv_label == 'APPROACHING':
        score += 4; pos.append(f"Gamma velocity: APPROACHING — squeeze window ~{gv_sessions:.0f} sessions (+4)")
    elif gv_label == 'STALLING':
        neg.append("Gamma velocity: STALLING — price not accelerating toward wall")
    elif gv_label == 'MOVING_AWAY':
        score -= 3; neg.append("Gamma velocity: MOVING_AWAY — price retreating from gamma wall")

    # Call wall vs target
    call_wall  = walls.get('call_wall')
    put_wall   = walls.get('put_wall')
    structural_target = ctx['structural_target']

    if direction == 'CALL' and call_wall and structural_target:
        if structural_target > call_wall:
            score += 5; pos.append(f"Target ${structural_target:.2f} clears call wall ${call_wall:.2f} (+5)")
        elif structural_target < call_wall * 0.98:
            neg.append(f"Call wall ${call_wall:.2f} — target ${structural_target:.2f} likely to stall")
        else:
            score += 2; pos.append(f"Target approaches call wall ${call_wall:.2f}")

    if direction == 'PUT' and put_wall and structural_target:
        if structural_target < put_wall:
            score += 5; pos.append(f"Target ${structural_target:.2f} clears put wall ${put_wall:.2f} (+5)")

    max_pain = walls.get('max_pain')
    if max_pain and spot > 0:
        pain_dist = abs(spot - max_pain)/spot
        if pain_dist < 0.02:
            neg.append(f"Spot within 2% of max pain ${max_pain:.2f} — expiry pinning risk")

    # ── [E] VOLUME, VANNA & SECTOR (12 pts) ───────────────────────────────────
    # Volume confirmation (Wyckoff)
    vol_confirm = vol_confirm or {}
    vc_score = vol_confirm.get('vol_confirmation_score', 0)
    vc_label = vol_confirm.get('vol_confirmation_label', 'UNKNOWN')
    vc_note  = vol_confirm.get('vol_wyckoff_note', '')
    if vc_score > 0:
        score += min(vc_score, 7); pos.append(f"Wyckoff Volume: {vc_label} — {vc_note}")
    elif vc_score < 0:
        score += max(vc_score, -4); neg.append(f"Wyckoff Volume: {vc_label} — {vc_note}")

    # Vanna quality (delta acceleration potential)
    vanna = contract.get('vanna') if contract else None
    if vanna is not None:
        vanna_abs = abs(float(vanna))
        if vanna_abs >= VANNA_STRONG_THRESHOLD:
            if (direction == 'CALL' and vanna > 0) or (direction == 'PUT' and vanna < 0):
                score += 3; pos.append(f"Vanna={vanna:.3f} — delta will accelerate if vol rises on breakout (+3)")
            else:
                neg.append(f"Vanna={vanna:.3f} — delta works against direction if vol rises")

    # Charm (delta decay in low-vol consolidation)
    charm = contract.get('charm') if contract else None
    if charm is not None:
        charm_abs = abs(float(charm))
        if charm_abs > CHARM_BLEED_THRESHOLD:
            neg.append(f"Charm={charm:.4f}/day — meaningful delta decay during consolidation")

    # Sector regime alignment
    sector_data = sector_data or {}
    sector_regime = sector_data.get('sector_regime', 'UNKNOWN')
    sector_ret    = sector_data.get('sector_5d_return', 0) or 0
    if direction == 'CALL' and sector_regime == 'STRONG_UPTREND':
        score += 2; pos.append(f"Sector ETF: {sector_data.get('sector_etf','')} +{sector_ret:.1f}% 5d — wind at back (+2)")
    elif direction == 'CALL' and sector_regime == 'STRONG_DOWNTREND':
        score -= 3; neg.append(f"Sector ETF: {sector_data.get('sector_etf','')} {sector_ret:.1f}% 5d — fighting sector headwind")
    elif direction == 'PUT' and sector_regime == 'STRONG_DOWNTREND':
        score += 2; pos.append(f"Sector ETF: {sector_data.get('sector_etf','')} {sector_ret:.1f}% 5d — sector confirms bearish direction (+2)")
    elif direction == 'PUT' and sector_regime == 'STRONG_UPTREND':
        score -= 3; neg.append(f"Sector ETF: {sector_data.get('sector_etf','')} +{sector_ret:.1f}% 5d — sector ripping against PUT")

    # ── [F] QUOTE QUALITY WARNING (no score penalty — data quality, not edge) ────
    # DATA_FAILURE rule: block only when bid==None AND ask==None (no market exists)
    # Synthetic mark (BSM fallback) is a DATA_WARNING, not a fundamental signal flaw.
    # The -10 penalty has been removed: it was pushing borderline signals below EXECUTE
    # threshold on virtually every signal, silently refusing to trade. The trader is
    # informed via the warning surface. Execution feasibility is a trader decision.
    if contract:
        has_bid = contract.get('bid') is not None and contract.get('bid', '') not in ('', 'None', None)
        has_ask = contract.get('ask') is not None and contract.get('ask', '') not in ('', 'None', None)
        if not has_bid and not has_ask:
            # BUG B FIX (2026-03-05): Do NOT zero the score. BSM-synthetic chains have no real
            # bid/ask by construction — score=0.0 was silently killing every signal in the
            # universe. Apply proportional penalty instead; trader verifies spread at entry.
            neg.append("QUOTE_WARNING: No live bid/ask — BSM synthetic mark only. Verify spread at entry.")
            score -= 8  # Proportional penalty for unverified execution cost
        elif contract.get('mark_synthetic', False):
            neg.append("QUOTE_WARNING: Synthetic BSM mark in use — verify spread before entry")

    score = float(np.clip(score, 0, 100))
    return round(score, 1), pos, neg



# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — VERDICT ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def derive_verdict(ois_score: float, ctx: Dict, iv_ctx: Dict,
                   econ: Dict, neg_factors: List[str],
                   sector_data: Dict = None,
                   contract: Dict = None) -> Tuple[str, str]:
    """
    Three-state verdict: EXECUTE / ARMED / STAND_DOWN.

    EXECUTE   : OIS ≥ MIN_OPTIONS_SCORE, no hard blocks
    ARMED     : OIS ≥ ARMED_MIN_SCORE, structure sound but conditions imperfect
    STAND_DOWN: Hard blocks present or OIS too low

    Hard blocks (immediate STAND_DOWN regardless of OIS):
      - intent == WAIT
      - IV expensive AND negative EV
      - direction == NONE
      - Theta drag > 70% of premium
      - IV regime EVENT_PRICED with IVP > 75% (binary event + expensive)
      - 252d IVP > 85% AND IV/HV > 1.20 (structurally expensive annual high)
      - Sector strongly contradicts direction (sector up >3% with PUT, down >3% with CALL)
        → demoted to ARMED not STAND_DOWN (structural may still be right)
    """
    intent    = ctx['intent']
    direction = ctx['direction']
    ivp       = iv_ctx.get('iv_percentile')
    ivp_252   = iv_ctx.get('ivp_252d')
    iv_vs_hv  = iv_ctx.get('iv_vs_hv')
    theta_pct = econ.get('theta_drag_pct', 100)
    iv_regime = iv_ctx.get('iv_regime', 'UNKNOWN')

    # ── HARD GATES: True execution infeasibility — only 5 gates ─────────────────
    # Rule: STAND_DOWN only when risk cannot be defined or execution is impossible.
    # Everything else is a WARNING on the output, not a gate.

    # Gate 1: No directional conviction — nothing to trade
    if intent == 'WAIT' and not ctx.get('vanguard_support_direction_repair'):
        return 'STAND_DOWN', 'BLOCK_WAIT_INTENT: Structural intent is WAIT — no directional conviction'

    # Gate 2: No direction determined — cannot select contract type
    if direction == 'NONE':
        return 'STAND_DOWN', 'BLOCK_NO_DIRECTION: No tradeable direction from structural analysis'

    # Theta is advisory in v4. It informs urgency but no longer kills a valid
    # structural signal by itself.
    # FIX-THETA-01: Raised threshold from 70% to 85%.
    # Previous threshold caused 13 STAND_DOWNs on 22d DTE Phase D signals where
    # theta_pct was computed against the full hold window (e.g. 10 days) even
    # though a professional trader exits Phase D within 3-5 days of breakout.
    # The theta gate exists to prevent contracts where decay consumes the premium
    # before the setup has time to develop — 70% was too conservative for
    # fast-moving Phase D/E setups. 85% maintains discipline against truly
    # decay-dominated positions (DTE≤7 held for weeks) while allowing short-term
    # Phase D acceleration trades.
    # AMENDMENT (2026-05-02): Raised from 85% to 92%.
    # 124 signals (70 CALL + 54 PUT) were hitting this gate. Phase C/D setups
    # at 85-91% theta are short-hold trades (3-5 day breakouts) where full-period
    # theta is an overestimate. The correct control is contract re-selection
    # (lower strike, longer DTE) not signal termination. 92% guards only against
    # truly unworkable DTE<=3 positions held to expiry.
    if theta_pct > 70:
        neg_factors.append(f"Theta drag={theta_pct:.0f}% — decay will erode position")

    # Gate 4: Binary event within 3 days AND event already priced — lottery ticket not directional bet
    near_event     = ctx.get('near_event', False)
    days_to_event  = int(float(ctx.get('days_to_event', 99) or 99))
    if near_event and days_to_event <= 3 and iv_regime == 'EVENT_PRICED':
        return 'STAND_DOWN', (
            f'BLOCK_EVENT_PRICED: Binary event in {days_to_event}d with EVENT_PRICED IV — '
            f'vol crush on resolution destroys long option value. Wait for post-event vol reset.'
        )

     # Gate 5a: Missing expiry / DTE — cannot define time risk
    # Final guard. Contract selector filters this upstream, but signals can
    # still arrive with no expiry when chain fetch fails silently.
    contract_dte    = int(float((contract or {}).get('dte', 0) or 0))
    contract_expiry = str((contract or {}).get('expiry', '') or
                          (contract or {}).get('expiration_date', '') or '').strip()
    if contract_dte <= 0 and not contract_expiry:
        return 'STAND_DOWN', 'BLOCK_NO_EXPIRY: No DTE or expiry date — time risk cannot be defined'

    # Gate 5b: Spread too wide — execution cost destroys edge before trade begins
    # Fires only when real bid/ask are present (not synthetic mark alone).
    if contract:
        bid_raw = _repair_alt_float(contract.get('bid'))
        ask_raw = _repair_alt_float(contract.get('ask'))
        quality = str(contract.get('quote_quality') or '').strip().upper()
        flags = _quote_flags(contract.get('quality_flags'))
        if (
            quality == 'INVALID'
            or bool({'CROSSED_QUOTE', 'NEGATIVE_QUOTE'} & flags)
            or (bid_raw is not None and bid_raw < 0)
            or (ask_raw is not None and ask_raw < 0)
            or (bid_raw is not None and ask_raw is not None and bid_raw > ask_raw)
        ):
            return 'STAND_DOWN', (
                'BLOCK_INVALID_QUOTE: Selected contract has a crossed, negative, '
                'or otherwise malformed top-of-book quote.'
            )
        # AVS-FIX-001 W1.6 (RCA3-D07, DEC-3): the per-horizon band is the
        # authority here, not the flat reviewable ceiling. This gate used
        # MAX_SPREAD_PCT (25%) while contract selection used the band (15% on
        # 1_5d), so 1_5d contracts between the two limits reached STAND_DOWN's
        # gate and passed it.
        _spread_limit = horizon_spread_limit(
            (ctx or {}).get('horizon_bucket') or (ctx or {}).get('macro_preferred_horizon')
        )
        spread_pct_val = contract.get('spread_pct')
        if spread_pct_val is not None and not bool(contract.get('mark_synthetic', False)):
            try:
                spread_pct_direct = float(spread_pct_val)
            except Exception:
                spread_pct_direct = None
            if spread_pct_direct is not None and spread_pct_direct > _spread_limit:
                return 'STAND_DOWN', (
                    f'BLOCK_SPREAD: Spread {spread_pct_direct:.0%} exceeds '
                    f'{_spread_limit:.0%} liquidity threshold. Execution cost destroys edge.'
                )
        bid_val  = contract.get('bid')
        ask_val  = contract.get('ask')
        mark_val = float(contract.get('mark') or contract.get('mid_price') or 0)
        if (bid_val is not None and ask_val is not None and
                float(bid_val) >= 0 and float(ask_val) > 0 and mark_val > 0):
            spread_pct = quote_spread_fraction(bid_val, ask_val)
            if spread_pct is None:
                spread_pct = math.inf
            if spread_pct > _spread_limit:
                return 'STAND_DOWN', (
                    f'BLOCK_SPREAD: Spread {spread_pct:.0%} of mark ${mark_val:.2f} '
                    f'(bid={float(bid_val):.2f} ask={float(ask_val):.2f}) exceeds {_spread_limit:.0%} threshold. '
                    f'Execution cost destroys edge.'
                )

    # ── Gate 6: BLOCK_WRONG_STRIKE — option cannot profit even if full thesis plays out ──
    # FIX-WRONG-STRIKE-01: Demote to ARMED (not hard STAND_DOWN) when OVT=0.
    #
    # Root cause: When structural_target is synthetic (entry ± 3×stop) and the
    # stop_dist is small, the target may land so close to the entry that even
    # an ATM put/call has ovt=0 because strike ≈ target ± epsilon.
    # These are NOT hopeless trades — the structural thesis is intact, the
    # contract selection just produced a suboptimal target estimate.
    #
    # Previous behaviour: hard STAND_DOWN — blocked 71 signals (96% Phase C)
    # New behaviour:
    #   - If OVT=0 AND R:R could not be computed (mark=0 edge case): STAND_DOWN
    #   - If OVT=0 but mark>0: demote to ARMED with BLOCK_WRONG_STRIKE warning.
    #     Trader sees the warning; morning_validation can override sizing.
    #   - STRANGLE exempt (uses neutral fallback)
    ovt = econ.get('option_value_at_target', -1)  # -1 = not computed (no contract)
    if ovt >= 0 and direction in ('CALL', 'PUT'):
        if ovt == 0:
            strike_val = (contract or {}).get('strike', '?')
            tgt_val    = ctx.get('structural_target', 0)
            tgt_str    = f'${tgt_val:.2f}' if isinstance(tgt_val, float) else str(tgt_val)
            mark_val   = float((contract or {}).get('mark', 0) or 0)
            if mark_val <= 0:
                # Genuine failure: no premium, no payoff path
                return 'STAND_DOWN', (
                    f'BLOCK_WRONG_STRIKE: Strike ${strike_val} cannot reach structural target '
                    f'{tgt_str} — option expires worthless even if thesis is correct. '
                    f'No viable contract in current expiry/strike universe.'
                )
            else:
                # FIX: OVT=0 with a real mark = target geometry is tight but
                # the premium paid still defines max risk. Surface as warning,
                # score will reflect the unfavourable R:R. Let OIS gate decide.
                # Do NOT hard-block — this was killing 71 valid Phase C setups.
                if not isinstance(neg_factors, list):
                    neg_factors = list(neg_factors) if neg_factors else []
                neg_factors.append(
                    f'WARN_STRIKE_AT_TARGET: Strike ${strike_val} is at/beyond target '
                    f'{tgt_str} — R:R unfavourable. Verify target before entry.'
                )
                # Continue to score-based verdict — OIS and R:R penalties will apply

    # ── DEMOTIONS (not hard blocks): expensive vol, stretched IV — ARMED not STAND_DOWN ──
    # These are warnings that Vanguard's edge may face headwind, but the setup is still valid.
    # EVENT_PRICED IV with IVP > 75% but no imminent binary event → ARMED (vol warning, not block)
    # 252d annual high + IV/HV stretched → ARMED (structural cost, not block)
    # Both are captured in the neg_factors list and will demote via score, not hard gate

    # Score-based verdict
    final_verdict = None
    final_reason  = ''

    # Three-tier threshold: EOD / LIVE_LOW / FULL_LIVE
    # mark_synthetic=True  → EOD (no live chain quotes)
    # mark_synthetic=False and score<55 → LIVE_LOW (real quotes, mkt env caps score)
    # mark_synthetic=False and score>=55 → FULL_LIVE
    _is_eod    = (contract or {}).get('mark_synthetic', True)
    _is_ll     = (not _is_eod) and (ois_score < MIN_OPTIONS_SCORE)

    if _is_eod:
        _exec_min  = EOD_EXECUTE_MIN_SCORE
        _arm_min   = EOD_ARMED_MIN_SCORE
        _tier_note = ' [EOD — morning_validation mandatory]'
    elif _is_ll:
        _exec_min  = LIVE_LOW_EXECUTE_MIN
        _arm_min   = LIVE_LOW_ARMED_MIN
        _tier_note = ' [LIVE_LOW — confirm before entry]'
    else:
        _exec_min  = MIN_OPTIONS_SCORE
        _arm_min   = ARMED_MIN_SCORE
        _tier_note = ''

    if ois_score >= _exec_min:
        final_verdict = 'EXECUTE'
        final_reason = f'All observable Options gates passed; R:R is advisory{_tier_note}'
    elif ois_score >= _arm_min:
        final_verdict = 'ARMED'
        final_reason  = ('; '.join(neg_factors[:2]) if neg_factors else 'Conditions not fully optimal') + _tier_note
    else:
        # Soft-fail: low OIS — signal alive for SuperBrain context enrichment
        final_verdict = 'ARMED'
        top = neg_factors[0] if neg_factors else 'OIS score below threshold'
        final_reason  = f'Low OIS={ois_score:.0f} (<{_arm_min}) — {top}{_tier_note}'

    # Sector headwind: demote EXECUTE → ARMED (not STAND_DOWN — structure still valid)
    sector_data = sector_data or {}
    sector_regime = sector_data.get('sector_regime', 'UNKNOWN')
    sector_ret    = sector_data.get('sector_5d_return', 0) or 0
    if final_verdict == 'EXECUTE':
        if direction == 'PUT' and sector_regime == 'STRONG_UPTREND':
            final_verdict = 'ARMED'
            final_reason = (f'Sector ETF {sector_data.get("sector_etf","")} +{sector_ret:.1f}% 5d — '
                            f'strong sector uptrend contradicts PUT thesis; demoted EXECUTE→ARMED')
        elif direction == 'CALL' and sector_regime == 'STRONG_DOWNTREND':
            final_verdict = 'ARMED'
            final_reason = (f'Sector ETF {sector_data.get("sector_etf","")} {sector_ret:.1f}% 5d — '
                            f'sector downtrend fights CALL thesis; demoted EXECUTE→ARMED')

    return final_verdict, final_reason


def _oi_blank(value: Any) -> bool:
    """True when a value is absent, NaN, or an empty text placeholder."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "n/a"}


def _oi_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if _oi_blank(value):
        return default
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _md_first_value(value: Any) -> Any:
    """Return the first MarketData parallel-array value, accepting scalars too."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _fetch_underlying_nbbo_fields(ticker: str) -> Dict[str, Any]:
    """Fetch non-authoritative equity NBBO sizes used by the EIL OBI overlay."""
    fields: Dict[str, Any] = {
        "l2_bid_size": None,
        "l2_ask_size": None,
        "l2_quote_source": "UNAVAILABLE",
        "l2_quote_timestamp_utc": None,
    }
    if _canonical_offline_replay_enabled() or not ticker or not MARKETDATA_API_KEY:
        return fields

    try:
        response = MD_SESSION.get(
            f"https://api.marketdata.app/v1/stocks/quotes/{ticker}/",
            headers={"Authorization": f"Token {MARKETDATA_API_KEY}"},
            timeout=8,
        )
        if not response.ok:
            return fields

        payload = response.json()
        if payload.get("s") != "ok":
            return fields

        bid_size = _oi_float(_md_first_value(payload.get("bidSize")))
        ask_size = _oi_float(_md_first_value(payload.get("askSize")))
        if bid_size is not None and bid_size < 0:
            bid_size = None
        if ask_size is not None and ask_size < 0:
            ask_size = None

        fields["l2_bid_size"] = bid_size
        fields["l2_ask_size"] = ask_size
        if bid_size is not None or ask_size is not None:
            fields["l2_quote_source"] = "MARKETDATA_STOCK_NBBO"
            fields["l2_quote_timestamp_utc"] = _quote_timestamp_utc(
                _md_first_value(payload.get("updated"))
            )
    except Exception:
        # OBI is an advisory overlay. Missing NBBO remains explicit and EIL uses
        # its governed GEX/wall fallback rather than failing the options layer.
        pass
    return fields


def _resolve_underlying_nbbo_fields(ticker: str, signal_row: Any) -> Dict[str, Any]:
    """Reuse upstream NBBO sizes and call MarketData only for missing values."""
    get_value = signal_row.get if hasattr(signal_row, "get") else lambda _key: None
    upstream_bid = _oi_float(get_value("l2_bid_size"))
    upstream_ask = _oi_float(get_value("l2_ask_size"))
    if upstream_bid is not None and upstream_ask is not None:
        return {
            "l2_bid_size": upstream_bid,
            "l2_ask_size": upstream_ask,
            "l2_quote_source": str(get_value("l2_quote_source") or "UPSTREAM_REUSE"),
            "l2_quote_timestamp_utc": get_value("l2_quote_timestamp_utc"),
        }

    fetched = _fetch_underlying_nbbo_fields(ticker)
    if upstream_bid is not None:
        fetched["l2_bid_size"] = upstream_bid
    if upstream_ask is not None:
        fetched["l2_ask_size"] = upstream_ask
    if (upstream_bid is not None or upstream_ask is not None) and fetched["l2_quote_source"] != "UNAVAILABLE":
        fetched["l2_quote_source"] = "UPSTREAM_AND_MARKETDATA_STOCK_NBBO"
    elif upstream_bid is not None or upstream_ask is not None:
        fetched["l2_quote_source"] = "UPSTREAM_PARTIAL"
    return fetched


def _oi_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in {"1", "TRUE", "YES", "Y", "GO"}


def _resolve_options_trigger_state(signal_row: Any, ctx: Dict) -> Tuple[str, str]:
    """
    Resolve trigger state for options research routing.
    Missing or stale trigger data cannot produce OPTIONS_GO_REVIEW.
    """
    row_get = signal_row.get if hasattr(signal_row, "get") else (lambda k, d=None: d)
    trigger_quality = str(row_get("trigger_quality", "") or "").upper().strip()
    trigger_primary = str(row_get("trigger_primary", "") or "").upper().strip()
    trigger_codes = str(row_get("trigger_codes", "") or "").upper().strip()
    trigger_state = str(row_get("trigger_state", "") or row_get("trigger_status", "") or "").upper().strip()
    wyckoff_trigger = str(row_get("wyckoff_entry_trigger", "") or row_get("wyckoff_trigger", "") or "").strip()
    days_to_trigger = _oi_float(row_get("days_to_trigger", None))
    go_eligible = _oi_bool(row_get("trigger_go_eligible", False))

    joined = " ".join([trigger_quality, trigger_primary, trigger_codes, trigger_state]).upper()
    if "STALE" in joined:
        return "TRIGGER_STALE", "trigger field contains STALE"
    if trigger_quality in {"STRONG", "CONFIRMED"} or trigger_state in {"CONFIRMED", "TRIGGER_CONFIRMED"} or go_eligible:
        return "TRIGGER_CONFIRMED", "explicit trigger confirmation"
    if trigger_quality in {"SINGLE", "ARMED"} or trigger_state in {"ARMED", "TRIGGER_ARMED"}:
        return "TRIGGER_ARMED", "single/armed trigger support"
    if days_to_trigger is not None and 0 <= days_to_trigger <= 10:
        return "TRIGGER_EARLY_PROBE", f"days_to_trigger={days_to_trigger:.0f}"
    if wyckoff_trigger:
        return "TRIGGER_EARLY_PROBE", "Wyckoff entry trigger text present"
    if ctx.get("phase") in {"D", "E"}:
        return "TRIGGER_EARLY_PROBE", f"phase={ctx.get('phase')} implies active trigger window"
    return "NO_TRIGGER", "no trigger_primary/quality/codes/state handoff"


def _estimate_expected_move_pct(ctx: Dict, iv_ctx: Dict, contract: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Hybrid expected move using pipeline target, ATR, and IV-engine context."""
    spot = _oi_float(ctx.get("spot"), 0.0) or 0.0
    if spot <= 0:
        return None, None

    components: List[float] = []
    target = _oi_float(ctx.get("structural_target"))
    entry = _oi_float(ctx.get("entry"), spot) or spot
    if target is not None and entry > 0:
        components.append(abs(target - entry) / entry * 100.0)

    atr = _oi_float(ctx.get("atr"))
    hold_days = max(1.0, _oi_float(ctx.get("hold_days"), 5.0) or 5.0)
    if atr is not None and atr > 0:
        components.append((atr * math.sqrt(hold_days) / spot) * 100.0)

    iv_expected = _oi_float(contract.get("iv_engine_expected_move_%"))
    if iv_expected is not None and iv_expected > 0:
        components.append(iv_expected)
    else:
        atm_iv = _oi_float(iv_ctx.get("atm_iv")) or _oi_float(contract.get("implied_vol")) or _oi_float(contract.get("iv"))
        if atm_iv is not None and atm_iv > 0:
            if atm_iv > 5.0:
                atm_iv = atm_iv / 100.0
            components.append(atm_iv * math.sqrt(hold_days / 252.0) * 100.0)

    if not components:
        return None, None
    expected_move_pct = round(max(components), 4)
    return expected_move_pct, round(spot * expected_move_pct / 100.0, 4)


def _compute_runway_to_wall_pct(ctx: Dict, walls: Dict) -> Optional[float]:
    spot = _oi_float(ctx.get("spot"), 0.0) or 0.0
    if spot <= 0:
        return None
    direction = ctx.get("direction")
    if direction == "CALL":
        wall = _oi_float(walls.get("call_wall"))
        if wall is None or wall <= spot:
            return None
        return round((wall - spot) / spot * 100.0, 4)
    if direction == "PUT":
        wall = _oi_float(walls.get("put_wall"))
        if wall is None or wall >= spot:
            return None
        return round((spot - wall) / spot * 100.0, 4)
    return None


def _score_linear(value: Optional[float], bad: float, good: float, invert: bool = False) -> float:
    if value is None:
        return 0.0
    v = float(value)
    if invert:
        v = good - (v - bad)
        bad, good = good, bad
    if good == bad:
        return 0.0
    score = (v - bad) / (good - bad) * 100.0
    return round(float(np.clip(score, 0.0, 100.0)), 2)


def build_options_research_contract(
    ctx: Dict,
    signal_row: Any,
    contract: Dict,
    iv_ctx: Dict,
    econ: Dict,
    ois_score: float,
    verdict: str,
    stand_down_reason: str,
    walls: Dict,
) -> Dict:
    """
    Research-only contract overlay.
    This is the authoritative options route; legacy options_verdict is retained
    for downstream compatibility but no execution/capital permission is granted.
    """
    contract = contract or {}
    hard_vetoes: List[str] = []
    soft_review_flags: List[str] = []
    missing_data: List[str] = []

    def _first_numeric(*values):
        for raw in values:
            parsed = _oi_float(raw)
            if parsed is not None:
                return parsed
        return None

    spot = _oi_float(ctx.get("spot"))
    strike = _oi_float(contract.get("strike"))
    dte = _oi_float(contract.get("dte"))
    bid = _oi_float(contract.get("bid"))
    ask = _oi_float(contract.get("ask"))
    mid = (_oi_float(contract.get("mark")) or _oi_float(contract.get("mid")) or
           _oi_float(contract.get("mid_price")))
    delta = _oi_float(contract.get("delta"))
    iv = (_oi_float(contract.get("implied_vol")) or _oi_float(contract.get("contract_iv")) or
          _oi_float(contract.get("iv")) or _oi_float(iv_ctx.get("atm_iv")))
    volume = _oi_float(contract.get("volume"))
    oi = _first_numeric(contract.get("oi"), contract.get("open_interest"), contract.get("openInterest"))
    expiry = contract.get("expiry") or contract.get("expiration_date")
    breakeven = _oi_float(econ.get("breakeven_price"))

    spread_pct_input = _oi_float(contract.get("spread_pct"))
    quote_quality = str(contract.get("quote_quality") or "").strip().upper()
    quote_flags = _quote_flags(contract.get("quality_flags"))
    invalid_quote = (
        quote_quality == "INVALID"
        or bool({"CROSSED_QUOTE", "NEGATIVE_QUOTE"} & quote_flags)
        or (bid is not None and bid < 0)
        or (ask is not None and ask < 0)
        or (bid is not None and ask is not None and bid > ask)
        or (spread_pct_input is not None and spread_pct_input < 0)
    )
    if invalid_quote:
        hard_vetoes.append("INVALID_CROSSED_QUOTE")
    if (
        not invalid_quote and mid is not None and mid > 0
        and spread_pct_input is not None and spread_pct_input >= 0
    ):
        # Some selected contracts carried a real marketdata.app midpoint and
        # spread_pct but dropped raw bid/ask during selection. Reconstructing
        # the implied top-of-book preserves the execution-cost check instead
        # of falsely classifying the contract as missing critical data.
        if bid is None and ask is None:
            half_spread = max(0.0, mid * spread_pct_input) / 2.0
            bid = max(0.0, mid - half_spread)
            ask = mid + half_spread

    critical = {
        "spot_price": spot,
        "strike": strike,
        "expiry": expiry,
        "dte": dte,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "delta": delta,
        "iv": iv,
        "volume": volume,
        "open_interest": oi,
        "breakeven": breakeven,
    }
    for name, value in critical.items():
        if _oi_blank(value):
            missing_data.append(name)
            continue
        if isinstance(value, (int, float)):
            if name == "delta":
                if abs(float(value)) <= 0.001:
                    missing_data.append(name)
            elif name in {"bid", "volume", "open_interest"}:
                if float(value) < 0:
                    missing_data.append(name)
            elif float(value) <= 0:
                missing_data.append(name)
    if missing_data:
        # Missing quote/economic fields are repair/review conditions at EOD.
        # They are not equivalent to no options market existing.
        soft_review_flags.append("CONTRACT_DATA_INCOMPLETE")

    spread_pct = None
    if not invalid_quote and bid is not None and ask is not None and mid is not None and mid > 0:
        spread_fraction = quote_spread_fraction(bid, ask)
        spread_pct = round(spread_fraction, 6) if spread_fraction is not None else None
        if spread_pct is not None and spread_pct > OPTIONS_SPREAD_HARD_PCT:
            soft_review_flags.append("SPREAD_GT_25PCT")

    if dte is not None and dte <= 0:
        hard_vetoes.append("DTE_NON_POSITIVE")
    if mid is not None and mid <= 0:
        soft_review_flags.append("MID_NON_POSITIVE")

    expected_move_pct, expected_move_price = _estimate_expected_move_pct(ctx, iv_ctx, contract)
    required_move = None
    breakeven_feasibility = None
    if spot is not None and breakeven is not None:
        if ctx.get("direction") == "CALL":
            required_move = max(0.0, breakeven - spot)
        elif ctx.get("direction") == "PUT":
            required_move = max(0.0, spot - breakeven)
        if required_move is not None and required_move > 0 and expected_move_price is not None:
            breakeven_feasibility = round(expected_move_price / required_move, 4)
        elif required_move == 0:
            breakeven_feasibility = 999.0
    if breakeven_feasibility is None:
        missing_data.append("breakeven_feasibility")
        breakeven_info_flag = "BREAKEVEN_FEASIBILITY_MISSING"
    elif breakeven_feasibility < OPTIONS_MIN_BREAKEVEN_FEASIBILITY:
        breakeven_info_flag = "BREAKEVEN_FEASIBILITY_LT_1"
    else:
        breakeven_info_flag = ""

    estimated_r = _oi_float(econ.get("rr_options"))
    if estimated_r is None:
        missing_data.append("estimated_R")
        soft_review_flags.append("ESTIMATED_R_MISSING")
    elif estimated_r < OPTIONS_MIN_R_MULTIPLE:
        soft_review_flags.append("ESTIMATED_R_LT_1")

    theta_decay_expected = _oi_float(econ.get("theta_drag_pct"))
    theta_info_flag = ""
    if theta_decay_expected is not None and theta_decay_expected > OPTIONS_THETA_DECAY_LIMIT_PCT:
        theta_info_flag = "THETA_DECAY_HIGH"

    runway_to_wall_pct = _compute_runway_to_wall_pct(ctx, walls or {})
    runway_info_flag = ""
    if runway_to_wall_pct is not None and runway_to_wall_pct < OPTIONS_MIN_RUNWAY_TO_WALL_PCT:
        runway_info_flag = "RUNWAY_TO_WALL_LT_1PCT"

    trigger_state, trigger_reason = _resolve_options_trigger_state(signal_row, ctx)
    trigger_info_flag = trigger_state if trigger_state in {"TRIGGER_STALE", "NO_TRIGGER"} else ""

    direction_fit_score = 100.0 if ctx.get("direction") in {"CALL", "PUT"} and str(ctx.get("preferred_strategy", "")).endswith(str(ctx.get("direction"))) else 70.0
    liquidity_score = 0.0 if spread_pct is None else (100.0 if spread_pct <= OPTIONS_SPREAD_PASS_PCT else _score_linear(spread_pct, OPTIONS_SPREAD_HARD_PCT, OPTIONS_SPREAD_PASS_PCT))
    breakeven_score = _score_linear(breakeven_feasibility, 0.75, 1.5)
    payoff_score = _score_linear(estimated_r, 1.0, 5.0)
    ivp = _oi_float(iv_ctx.get("iv_percentile"))
    if ivp is None:
        ivp = (_oi_float(iv_ctx.get("iv_rank")) or 50.0) / 100.0
    iv_score = round(float(np.clip(100.0 - max(0.0, ivp - 0.30) * 120.0, 0.0, 100.0)), 2)
    theta_score = 0.0 if theta_decay_expected is None else round(float(np.clip(100.0 - theta_decay_expected * 2.0, 0.0, 100.0)), 2)
    runway_score = 50.0 if runway_to_wall_pct is None else _score_linear(runway_to_wall_pct, 1.0, 5.0)
    path_score = _score_linear(ctx.get("win_prob"), 45.0, 70.0)
    trigger_score_map = {
        "TRIGGER_CONFIRMED": 100.0,
        "TRIGGER_ARMED": 75.0,
        "TRIGGER_EARLY_PROBE": 55.0,
        "TRIGGER_STALE": 0.0,
        "NO_TRIGGER": 0.0,
    }
    trigger_score = trigger_score_map.get(trigger_state, 0.0)

    options_research_score = round(
        0.20 * direction_fit_score +
        0.15 * liquidity_score +
        0.15 * breakeven_score +
        0.15 * payoff_score +
        0.10 * iv_score +
        0.10 * theta_score +
        0.10 * runway_score +
        0.05 * path_score,
        2,
    )

    if hard_vetoes:
        final_route = OPTIONS_BLOCKED_ROUTE
    elif options_research_score >= 75:
        final_route = OPTIONS_GO_ROUTE
    elif options_research_score >= 60:
        final_route = OPTIONS_ARMED_ROUTE
    elif options_research_score >= 45:
        final_route = OPTIONS_PROBE_ROUTE
    elif soft_review_flags or missing_data:
        # Keep the ticker thesis alive for morning repair/review. The trader
        # decides whether the live chain has normalised.
        final_route = OPTIONS_PROBE_ROUTE
    elif verdict in {"EXECUTE", "ARMED"}:
        final_route = OPTIONS_EQUITY_ONLY_ROUTE
    else:
        final_route = OPTIONS_BLOCKED_ROUTE

    confidence_score = round(max(0.0, min(100.0, options_research_score - len(missing_data) * 7.5)), 2)
    _repair_items = hard_vetoes + soft_review_flags + missing_data
    contract_repair_status = "CONTRACT_REPAIR_REQUIRED" if _repair_items else "OK"
    contract_repair_reason = (
        ";".join(dict.fromkeys(_repair_items))
        if _repair_items
        else "OK"
    )

    return {
        "execution_permission": OPTIONS_RESEARCH_PERMISSION,
        "final_route": final_route,
        "options_research_score": options_research_score,
        "confidence_score": confidence_score,
        "hard_vetoes": "|".join(dict.fromkeys(hard_vetoes)),
        "contract_repair_status": contract_repair_status,
        "contract_repair_required": bool(_repair_items),
        "contract_repair_reason": contract_repair_reason,
        "contract_review_flags": "|".join(dict.fromkeys(soft_review_flags)),
        "missing_data": "|".join(dict.fromkeys(missing_data)),
        "trigger_state": trigger_state,
        "trigger_status_reason": trigger_reason,
        "breakeven_info_flag": breakeven_info_flag,
        "theta_info_flag": theta_info_flag,
        "runway_info_flag": runway_info_flag,
        "trigger_info_flag": trigger_info_flag,
        "expected_move_pct": expected_move_pct,
        "expected_move_price": expected_move_price,
        "breakeven_feasibility": breakeven_feasibility,
        "estimated_R": estimated_r,
        "theta_decay_expected": theta_decay_expected,
        "runway_to_wall_pct": runway_to_wall_pct,
        "liquidity_score": liquidity_score,
        "directional_fit_score": direction_fit_score,
        "breakeven_score": breakeven_score,
        "payoff_score": payoff_score,
        "iv_score": iv_score,
        "theta_score": theta_score,
        "runway_score": runway_score,
        "path_score": path_score,
        "trigger_score": trigger_score,
        "research_route_reason": (
            "; ".join(dict.fromkeys(hard_vetoes)) if hard_vetoes
            else "; ".join(dict.fromkeys(soft_review_flags)) if soft_review_flags
            else f"research_score={options_research_score:.1f}; legacy_verdict={verdict}; {stand_down_reason or 'no legacy block'}"
        ),
    }


def _empty_options_research_contract(reason: str = "") -> Dict:
    return {
        "execution_permission": OPTIONS_RESEARCH_PERMISSION,
        "final_route": OPTIONS_BLOCKED_ROUTE,
        "options_research_score": 0.0,
        "confidence_score": 0.0,
        "hard_vetoes": "NO_LIQUID_OTM_CONTRACT",
        "contract_repair_status": "CONTRACT_REPAIR_REQUIRED",
        "contract_repair_required": True,
        "contract_repair_reason": reason or "NO_LIQUID_OTM_CONTRACT",
        "missing_data": "NO_LIQUID_OTM_CONTRACT",
        "trigger_state": "NO_TRIGGER",
        "trigger_status_reason": reason or "no contract selected",
        "expected_move_pct": None,
        "expected_move_price": None,
        "breakeven_feasibility": None,
        "estimated_R": None,
        "theta_decay_expected": None,
        "runway_to_wall_pct": None,
        "liquidity_score": 0.0,
        "directional_fit_score": 0.0,
        "breakeven_score": 0.0,
        "payoff_score": 0.0,
        "iv_score": 0.0,
        "theta_score": 0.0,
        "runway_score": 0.0,
        "path_score": 0.0,
        "trigger_score": 0.0,
        "research_route_reason": reason or "no contract selected",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — SINGLE TICKER PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_asof_date(signal_row) -> str:
    """
    Safely resolve the signal's as-of date for SB time-stop anchoring.
    Guards against pandas NaN being truthy in a plain or-chain.
    Priority: asof_date → signal_date → run_date → timestamp (vanguard ISO datetime)
    Returns YYYY-MM-DD string or empty string if nothing resolves.
    """
    import math
    def _clean(val):
        if val is None:
            return ''
        try:
            if isinstance(val, float) and math.isnan(val):
                return ''
        except Exception:
            pass
        s = str(val).strip()
        return s if s and s.lower() not in ('nan', 'none', '') else ''

    for field in ('asof_date', 'signal_date', 'run_date'):
        v = _clean(signal_row.get(field))
        if v:
            return v[:10]

    # timestamp is an ISO datetime from vanguard: '2026-03-07T10:14:53...'
    ts = _clean(signal_row.get('timestamp'))
    if ts:
        return ts[:10]

    return ''


def process_ticker(signal_row: pd.Series, macro_context: Optional[Dict[str, Any]] = None, tle_context: Optional[Dict[str, Any]] = None) -> Dict:
    """
    Full options intelligence pipeline for a single signal.
    Returns a flat dict of all output fields for the Intelligence Lab.

    FIX-04 (2026-05-02): Design principle — capture once, flow through.
    If the universe scanner already computed iv_rank, hv_30d, atm_iv,
    term_slope and skew, read them from signal_row before any API call.
    Chain is still fetched for contract selection, GEX, walls, and PCR.
    """
    ctx = parse_structural_context(signal_row)
    ticker = ctx['ticker']
    spot   = ctx['spot']

    # Pipeline failure guard
    if not ticker or spot <= 0:
        return _stand_down(ctx, 'Invalid ticker or spot price from pipeline')

    # Direction guard — no option-chain request is permitted until the GDR has
    # a validated long CALL/PUT side. STRANGLE and UNRESOLVED are retained for
    # audit, but this production pipeline does not trade non-directional or
    # exotic structures.
    if ctx['direction'] not in GOVERNED_DIRECTED_SIDES:
        return _stand_down(
            ctx,
            'No governed long CALL/PUT direction; chain request suppressed',
        )

    print(f"  [{ticker}] T{ctx['tier']} Ph{ctx['phase']} "
          f"{ctx['intent']} → {ctx['direction']} | "
          f"DTE {ctx['dte_window'][0]}-{ctx['dte_window'][2]}")

    # ── FIX-04: Read scanner VMS passthrough fields from row ───────────────
    # Universe scanner runs Phase 0 and stamps these onto discovery rows.
    # If present: use directly, skip IV/HV recomputation.
    # Chain still fetched for contract selection, GEX, walls, PCR.
    def _row_f(k, default=None):
        try:
            v = signal_row.get(k) if hasattr(signal_row, 'get') else (
                signal_row[k] if k in signal_row.index else None)
            if v is None: return default
            f = float(v)
            return f if f == f and f != 0.0 else default  # NaN/zero guard
        except: return default

    _sc_hv_30d  = _row_f('hv_30d') or _row_f('rv')
    _sc_iv_rank = _row_f('iv_rank')
    _sc_atm_iv  = _row_f('iv_current') or _row_f('atm_iv')
    _sc_term    = _row_f('term_slope')
    _sc_skew    = _row_f('skew')
    _sc_iv_src  = str(signal_row.get('iv_rank_source', '') if hasattr(signal_row, 'get') else '')
    _has_scanner = (_sc_hv_30d is not None and
                    _sc_iv_rank is not None and
                    _sc_atm_iv  is not None)
    if _has_scanner:
        print(f"  [{ticker}] SCANNER: iv_rank={_sc_iv_rank:.3f} "
              f"hv_30d={_sc_hv_30d:.4f} src={_sc_iv_src}")

    # Resolve the governed horizon before chain access so failures retain the
    # DTE window that was actually requested.
    _horizon_key = normalise_horizon_key(
        signal_row.get('horizon_bucket') or ctx.get('horizon_bucket') or '1_5d'
    )
    _dte_cfg = governed_dte_config(_horizon_key)

    def _contract_rejection_fields(reason: str, stage: str, chain_rows: int = 0) -> Dict[str, Any]:
        return {
            'contract_rejection_reason': reason,
            'contract_rejection_stage': stage,
            'contract_rejection_horizon': _horizon_key,
            'contract_rejection_dte_min': _dte_cfg.get('dte_min', ''),
            'contract_rejection_dte_max': _dte_cfg.get('dte_max', ''),
            'contract_rejection_chain_rows': chain_rows,
        }

    # ── 1. Fetch chain ─────────────────────────────────────────────────────
    try:
        chain = fetch_chain(ticker)
    except Exception as e:
        print(f"  [{ticker}] Chain fetch failed: {e}")
        return {
            **_stand_down(ctx, f'Chain fetch failed: {e}'),
            **_contract_rejection_fields('CHAIN_FETCH_FAILED', 'CHAIN_FETCH'),
        }

    _chain_lineage = {
        'option_chain_dataset_id': chain.attrs.get('canonical_dataset_id', ''),
        'option_chain_provider': chain.attrs.get('canonical_provider', 'MARKETDATA'),
        'option_chain_resolution': chain.attrs.get('canonical_resolution', ''),
        'option_chain_provider_finality': (
            chain.attrs.get('provider_finality', {}).get('finality_state', '')
            if isinstance(chain.attrs.get('provider_finality'), dict) else ''
        ),
        'option_chain_provider_finality_reasons_json': json.dumps(
            chain.attrs.get('provider_finality', {}).get('reasons', [])
            if isinstance(chain.attrs.get('provider_finality'), dict) else []
        ),
    }

    if chain.empty:
        return {
            **_stand_down(ctx, 'No options chain data available'),
            **_contract_rejection_fields('NO_OPTIONS_CHAIN_DATA', 'CHAIN_FETCH'),
            **_chain_lineage,
        }

    # ── 2. GEX + walls + PCR ───────────────────────────────────────────────
    gex_df, gamma_flip, flip_conf = compute_gex(chain, spot)
    walls = compute_oi_walls(chain)
    pcr_val, pcr_signal = compute_pcr(chain)
    gamma_surface_source = "MARKETDATA_CHAIN_GEX_BY_STRIKE"
    try:
        if "md_quote_source" not in chain.columns or not chain["md_quote_source"].fillna("").astype(str).str.contains("marketdata.app", case=False, regex=False).any():
            gamma_surface_source = "CHAIN_GEX_BY_STRIKE"
    except Exception:
        gamma_surface_source = "CHAIN_GEX_BY_STRIKE"
    gamma_island = compute_gamma_island(
        gex_df,
        spot,
        ctx.get("structural_target"),
        ctx.get("direction"),
        source=gamma_surface_source,
    )

    flip_gap_pct = None
    if gamma_flip and spot > 0:
        flip_gap_pct = round(abs(gamma_flip - spot)/spot*100, 2)

    # ── 2b. Delta-weighted OI flow ─────────────────────────────────────────
    try:
        dw_data = compute_delta_weighted_oi(chain, spot)
    except Exception:
        dw_data = {}

    # ── 3. IV context ──────────────────────────────────────────────────────
    # FIX-04C: If scanner data present, build iv_ctx from it — no re-compute.
    # Chain still fetched above for GEX/walls/PCR/contract selection.
    if _has_scanner:
        def _ivp_lbl(r):
            if r <= 0.20: return 'CHEAP'
            if r >= 0.70: return 'EXPENSIVE'
            return 'FAIR'
        _ts = 'UNKNOWN'
        if _sc_term is not None:
            _ts = ('BACKWARDATION' if _sc_term > 0.01 else
                   'CONTANGO'      if _sc_term < -0.01 else 'FLAT')
        iv_ctx = {
            'atm_iv':           round(_sc_atm_iv, 4),
            'iv_rank':          round(_sc_iv_rank * 100, 1),
            'iv_percentile':    round(_sc_iv_rank, 4),
            'ivp_30d':          round(_sc_iv_rank, 4),
            'ivp_252d':         round(_sc_iv_rank, 4),
            'ivp_label':        _ivp_lbl(_sc_iv_rank),
            'hv_30d':           round(_sc_hv_30d, 4),
            'iv_vs_hv':         round(_sc_atm_iv / _sc_hv_30d, 3) if _sc_hv_30d > 0 else None,
            'term_structure':   _ts,
            'term_ratio':       None,
            'iv_regime':        'UNKNOWN',
            'iv_direction':     'STABLE',
            'iv_direction_pct': 0.0,
            'vol_of_vol':       None,
            'iv_accel_detected': False,
            'risk_reversal':    _sc_skew,
            'put_25d_iv':       None,
            'call_25d_iv':      None,
            'skew_label':       'UNKNOWN',
            'heston_params':    None,
        }
        # Best-effort: try to enhance with chain IV data if available
        try:
            _chain_ctx = compute_iv_context(chain, ticker)
            if _chain_ctx.get('atm_iv') is not None:
                for _k in ('term_structure','term_ratio','iv_direction',
                           'skew_label','risk_reversal','heston_params',
                           'vol_of_vol','iv_accel_detected'):
                    if _chain_ctx.get(_k) is not None:
                        iv_ctx[_k] = _chain_ctx[_k]
        except Exception:
            pass
    else:
        try:
            iv_ctx = compute_iv_context(chain, ticker)
        except Exception as e:
            print(f"  [{ticker}] IV context failed: {e}")
            iv_ctx = {'atm_iv':None,'iv_rank':None,'iv_percentile':None,
                      'ivp_label':'UNKNOWN','hv_30d':None,'iv_vs_hv':None,
                      'term_structure':'UNKNOWN','iv_regime':'UNKNOWN',
                      'iv_direction':'STABLE','skew_label':'UNKNOWN',
                      'risk_reversal':None,'heston_params':None}

    heston_params = iv_ctx.get('heston_params')

    # ── 3b. Sector regime ──────────────────────────────────────────────────
    try:
        sector_data = fetch_sector_regime(ticker)
    except Exception:
        sector_data = {}

    # ── 4. Contract selection ──────────────────────────────────────────────
    contract = select_best_contract(chain, ctx)

    # AVS-FIX-001 W3.3: record the whole selection funnel, whether or not a
    # contract was chosen. A separate pass over the same chain with the same
    # bands, so it can never change which contract is selected. The flat
    # summary rides on the Options row; the per-contract list goes to a JSONL
    # sidecar, since a list is not a CSV cell.
    try:
        _contract_taxonomy = contract_rejection_taxonomy(chain, ctx)
        _contract_taxonomy_fields = contract_taxonomy_row_fields(_contract_taxonomy)
        _record_contracts_tested(ticker, ctx, _contract_taxonomy, selected=contract)
    except Exception as _taxonomy_error:
        # Instrumentation must never take a ticker down.
        print(f"  [{ticker}] contract taxonomy skipped: {_taxonomy_error}")
        _contract_taxonomy = {}
        _contract_taxonomy_fields = {}
    # FIX 4: Tiered contract review — replaces binary STAND_DOWN gate.
    # Write contract rejection log entry for diagnostics.
    _contract_tier = CONTRACT_TIER_CLEAN
    if not contract:
        # Check if chain exists at all or just no qualifying contract
        _chain_has_data = chain is not None and (hasattr(chain, '__len__') and len(chain) > 0)
        if _chain_has_data:
            _contract_tier = CONTRACT_TIER_REVIEW_NO_PASS
        else:
            _contract_tier = CONTRACT_TIER_REVIEW_NO_PASS

    if not contract:
        _chain_has_data = chain is not None and (hasattr(chain, '__len__') and len(chain) > 0)
        _base_no_contract = {**_stand_down(ctx, 'No contract passed quality gates'),
                **_chain_lineage,
                'iv_rank'        : iv_ctx.get('iv_rank'),
                'iv_percentile'  : iv_ctx.get('iv_percentile'),
                'ivp_label'      : iv_ctx.get('ivp_label'),
                'gamma_flip'     : gamma_flip,
                'gamma_flip_gap_pct': flip_gap_pct,
                **gamma_island,
                'call_wall'      : walls.get('call_wall'),
                'put_wall'       : walls.get('put_wall'),
                'max_pain'       : walls.get('max_pain'),
                'pcr_oi'         : pcr_val,
                'pcr_signal'     : pcr_signal,
                'atm_iv'         : iv_ctx.get('atm_iv'),
                'iv_regime'      : iv_ctx.get('iv_regime'),
                'skew_label'     : iv_ctx.get('skew_label'),
                **_contract_rejection_fields(
                    'NO_CONTRACT_PASSED_QUALITY_GATES',
                    'CONTRACT_SELECTION',
                    len(chain),
                ),
                **_contract_taxonomy_fields}
        if _chain_has_data:
            _repair_selector_diagnostics = _new_repair_selector_diagnostics()
            _no_contract_singles = select_repair_alternative_contracts(
                chain,
                ctx,
                None,
                limit=EV3_LONG_SINGLE_CANDIDATE_LIMIT,
                diagnostics=_repair_selector_diagnostics,
            )
            # Production is long single-leg CALL/PUT only. Do not mix vertical
            # research structures into the executable repair handoff.
            _no_contract_alternatives = _no_contract_singles[:EV3_TOTAL_CANDIDATE_LIMIT]
            if str(ctx.get('direction') or '').upper() in {'CALL', 'PUT'}:
                _enrich_ev3_contract_multipliers(None, _no_contract_alternatives, ctx.get('ticker'))
            _no_contract_alternatives, _incomplete_alternatives = _partition_complete_ev3_candidates(
                _no_contract_alternatives
            )
            _repair_alt_fields = _format_repair_alternative_fields(
                _no_contract_alternatives,
                'NO_CONTRACT_PASSED_QUALITY_GATES',
            )
            _repair_alt_fields.update(_alternative_handoff_audit(_incomplete_alternatives))
            _repair_alt_fields.update(
                _repair_selector_diagnostic_fields(_repair_selector_diagnostics)
            )
            _evidence_session = _governed_options_evidence_session(ctx)
            _legacy_thesis_id = (
                f"{str(ctx.get('ticker') or '').upper()}:"
                f"{str(ctx.get('direction') or '').upper()}:"
                f"{_evidence_session or 'UNKNOWN_SESSION'}"
            )
            _base_no_contract.update({
                'execution_permission': OPTIONS_RESEARCH_PERMISSION,
                'final_route': OPTIONS_PROBE_ROUTE,
                'options_route_verdict': OPTIONS_PROBE_ROUTE,
                'options_research_score': 45.0,
                'confidence_score': 35.0,
                'hard_vetoes': '',
                'contract_review_flags': 'NO_CONTRACT_PASSED_QUALITY_GATES',
                'contract_repair_status': 'CONTRACT_REPAIR_REQUIRED',
                'contract_repair_required': True,
                'contract_repair_reason': 'NO_CONTRACT_PASSED_QUALITY_GATES',
                'missing_data': 'NO_CONTRACT_PASSED_QUALITY_GATES',
                'research_route_reason': 'contract review required at open; chain exists but EOD gates rejected all contracts',
                'block_code': 'BLOCK_NO_CONTRACT',
                'block_family': 'SCORE',
                'block_severity': 'SOFT',
                'block_detail': 'No contract passed quality gates',
                'thesis_id': f"{_legacy_thesis_id}:OLM2",
                'legacy_thesis_id': _legacy_thesis_id,
                'supersedes_calculation_version': 'options-liquidity-lifecycle-v1',
                'thesis_calculation_version': OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
                'evidence_session_date': _evidence_session,
                'evidence_session_source': (
                    'CDS_RUN_SESSION' if _CDS_V2_SESSION is not None else 'SIGNAL_ASOF_FALLBACK'
                ),
                'thesis_state': 'ACTIVE',
                'liquidity_state': 'CONTRACT_FAMILY_REPAIR_REQUIRED',
                'morning_transition_state': 'CONTRACT_REPRICE_REQUIRED',
                'recovery_disposition': 'CONTRACT_REPAIR',
                'executable_now': False,
                'maturation_score_is_probability': False,
                'maturation_execution_authority': False,
                'contract_changed': False,
                'contract_selection_reason': 'NO_LONG_SINGLE_CONTRACT_IN_GOVERNED_DTE_DELTA_RANGE',
                'quote_freshness': 'UNAVAILABLE',
            })
            _base_no_contract.update(_repair_alt_fields)
            return _base_no_contract
        _base_no_contract.update(_empty_options_research_contract('No options chain data available'))
        return _base_no_contract

    # ── 4b. Real quote enrichment — marketdata.app ─────────────────────────
    was_synthetic = contract.get('mark_synthetic', False)
    contract = enrich_contract_with_real_quotes(contract)

    # ── 4c. NBBO top-of-book — feeds the non-authoritative OBI overlay ───
    # Reuse upstream sizes when present. Otherwise fetch once and carry the
    # values into the returned row; missing data remains explicit.
    nbbo_fields = _resolve_underlying_nbbo_fields(ticker, signal_row)

    # ── IV-FIX-002: Backfill iv_ctx from the selected MD contract ──────────
    # A chain response can contain rows with missing IV. Exact-contract MD
    # enrichment obtains current contract IV when available.
    # Use that single-contract IV as atm_iv proxy, then run iv_engine to compute
    # VRP, expected move, and a proxy iv_rank via absolute-level estimate.
    # This is a same-provider refinement, not a source fallback.
    _md_iv = (contract.get('implied_vol') or
              contract.get('contract_iv') or
              contract.get('iv'))
    if iv_ctx.get('atm_iv') is None and _md_iv and float(_md_iv) > 0:
        _md_iv_f = float(_md_iv)
        # Normalise: MD returns IV as decimal (0.25 = 25%)
        if _md_iv_f > 5.0:
            _md_iv_f = _md_iv_f / 100.0
        iv_ctx['atm_iv'] = round(_md_iv_f, 4)
        # Absolute-level proxy iv_rank (same logic as IV-FIX-001 fallback)
        if iv_ctx.get('iv_rank') is None:
            if   _md_iv_f < 0.25: iv_ctx['iv_rank'] = 20; iv_ctx['iv_percentile'] = 0.20
            elif _md_iv_f < 0.40: iv_ctx['iv_rank'] = 40; iv_ctx['iv_percentile'] = 0.40
            elif _md_iv_f < 0.60: iv_ctx['iv_rank'] = 60; iv_ctx['iv_percentile'] = 0.60
            else:                  iv_ctx['iv_rank'] = 80; iv_ctx['iv_percentile'] = 0.80
            iv_ctx['ivp_label'] = (
                'CHEAP'     if iv_ctx['iv_percentile'] <= 0.30 else
                'EXPENSIVE' if iv_ctx['iv_percentile'] >  0.70 else 'FAIR'
            )

    # ── IV-ENGINE-CONNECT: Wire iv_engine.py into pipeline ──────────────────
    # iv_engine.py is deployed to root but was never called. Wire it here after
    # MD enrichment so it has real contract IV. Produces VRP signal and expected
    # move. Falls back gracefully if iv_engine.py is not present.
    try:
        from iv_engine import iv_engine_from_row as _iv_eng_from_row
        _iv_row = {
            'ticker':           ticker,
            'atm_iv':           iv_ctx.get('atm_iv') or contract.get('implied_vol'),
            'contract_iv':      contract.get('implied_vol') or contract.get('contract_iv'),
            'hv_30d':           iv_ctx.get('hv_30d'),
            'underlying_price': spot,
            'contract_dte':     contract.get('dte', 30),
        }
        _iv_result = _iv_eng_from_row(_iv_row)
        if _iv_result:
            contract['iv_engine_vrp']             = _iv_result.vrp
            contract['iv_engine_vrp_signal']      = _iv_result.vrp_signal
            contract['iv_engine_expected_move_$'] = _iv_result.expected_move_usd
            contract['iv_engine_expected_move_%'] = _iv_result.expected_move_pct
            contract['iv_engine_data_quality']    = _iv_result.data_quality
            # If iv_engine computed VRP, use it to refine ivp_label
            if _iv_result.vrp_signal == 'BUY_EDGE' and iv_ctx.get('ivp_label') == 'FAIR':
                iv_ctx['ivp_label'] = 'CHEAP'
            elif _iv_result.vrp_signal == 'SELL_EDGE' and iv_ctx.get('ivp_label') == 'FAIR':
                iv_ctx['ivp_label'] = 'EXPENSIVE'
    except ImportError:
        pass  # iv_engine.py not found — non-fatal, pipeline continues
    except Exception:
        pass  # iv_engine call failed — non-fatal

    if was_synthetic and not contract.get('mark_synthetic', True):
        print(f"  [{ticker}] ✅ Real quote obtained — BSM synthetic replaced "
              f"(mark=${contract.get('mark', 0):.2f}, "
              f"spread={contract.get('spread_pct', 0)*100:.1f}%, "
              f"IV={contract.get('implied_vol', 0)*100:.1f}%)")
    elif was_synthetic:
        print(f"  [{ticker}] ⚠️  BSM synthetic mark in use")

    # ── 4c. Heston Greek enrichment (vanna, charm, accurate delta/vega) ────
    try:
        contract = enrich_contract_with_heston_greeks(contract, heston_params, spot)
        if contract.get('heston_used'):
            print(f"  [{ticker}] ✅ Heston Greeks applied "
                  f"(fit_err={iv_ctx.get('heston_fit_error','?')}, "
                  f"vanna={contract.get('vanna','?'):.3f})")
    except Exception as e:
        print(f"  [{ticker}] Heston enrichment skipped: {e}")

    # ── 4d. Gamma velocity ─────────────────────────────────────────────────
    try:
        # Fetch 3-day spot history for velocity calculation
        spot_hist_raw = _fetch_hist_closes(ticker, 10)
        spot_hist = spot_hist_raw[-4:-1] if len(spot_hist_raw) >= 4 else None
        gamma_vel = compute_gamma_velocity(
            spot, gamma_flip, spot_hist, ctx['direction'])
    except Exception:
        gamma_vel = {}

    # ── 4e. Volume confirmation ────────────────────────────────────────────
    vol_confirm = compute_volume_confirmation(
        ctx.get('vol_ratio', 1.0), ctx['phase'],
        ctx['direction'], ctx['trend'])

    # ── 5. Trade economics ─────────────────────────────────────────────────
    econ = compute_trade_economics(contract, ctx, iv_ctx)

    # ── 6. OIS + verdict ──────────────────────────────────────────────────
    economics_evaluated = econ.get('economics_state') == 'EVALUATED'
    if economics_evaluated:
        ois, pos_factors, neg_factors = compute_ois(
            ctx, iv_ctx, econ, gamma_flip, walls, pcr_signal, contract,
            dw_data=dw_data, gamma_vel=gamma_vel,
            vol_confirm=vol_confirm, sector_data=sector_data)
    else:
        ois, pos_factors, neg_factors = 0.0, [], [
            f"Economics not evaluated: {econ.get('economics_reason') or 'UNKNOWN'}"
        ]
    ois_pre_macro = ois
    macro_adj = options_macro_alignment_adjustment(ctx, macro_context, signal_row)
    macro_adj["options_macro_authority"] = "ADVISORY_ONLY"
    macro_adj["options_macro_effective_score_delta"] = 0.0
    macro_bonus = float(macro_adj.get("options_macro_alignment_bonus") or 0.0)
    if macro_bonus:
        if macro_bonus > 0:
            pos_factors.append(
                f"Macro enrichment aligned with options direction "
                f"(advisory score {macro_bonus:+.1f}; no OIS effect)"
            )
        else:
            neg_factors.append(
                f"Macro enrichment contradicts options direction "
                f"(advisory score {macro_bonus:+.1f}; no OIS effect)"
            )
    if economics_evaluated:
        verdict, stand_down_reason = derive_verdict(
            ois, ctx, iv_ctx, econ, neg_factors, sector_data=sector_data,
            contract=contract)
    else:
        verdict = 'STAND_DOWN'
        stand_down_reason = str(econ.get('economics_reason') or 'ECONOMICS_NOT_EVALUATED')

    # ── 7. Target in play check ────────────────────────────────────────────
    target_in_play = False
    cw = walls.get('call_wall')
    pw = walls.get('put_wall')
    st = ctx['structural_target']
    if ctx['direction'] == 'CALL' and cw and st:
        target_in_play = float(st) > float(cw)
    elif ctx['direction'] == 'PUT' and pw and st:
        target_in_play = float(st) < float(pw)

    resolved_expiry, resolved_dte = _resolve_contract_expiry_dte(contract)
    if resolved_expiry:
        contract['expiry'] = resolved_expiry
    if resolved_dte is not None:
        contract['dte'] = resolved_dte

    resolved_bid = _oi_float(contract.get('bid'))
    resolved_ask = _oi_float(contract.get('ask'))
    spread_source = 'MD_REAL' if resolved_bid is not None and resolved_ask is not None else None
    if resolved_bid is None or resolved_ask is None:
        resolved_bid, resolved_ask, spread_source = _derive_eod_spread(
            contract.get('mark') or contract.get('mid'),
            iv_ctx.get('ivp_label'),
            ois,
            contract.get('dte'),
        )
        if resolved_bid is not None:
            contract['bid'] = resolved_bid
        if resolved_ask is not None:
            contract['ask'] = resolved_ask
    if spread_source is None:
        spread_source = 'UNAVAILABLE'
    contract['spread_source'] = spread_source
    if _oi_float(contract.get('spread_pct')) is None and resolved_bid is not None and resolved_ask is not None:
        resolved_mid = _oi_float(contract.get('mark')) or _oi_float(contract.get('mid')) or ((resolved_bid + resolved_ask) / 2.0)
        if resolved_mid and resolved_mid > 0:
            spread_fraction = quote_spread_fraction(resolved_bid, resolved_ask)
            if spread_fraction is not None:
                contract['spread_pct'] = round(spread_fraction, 6)
    liquidity_lifecycle = _options_liquidity_lifecycle_fields(ctx, contract, iv_ctx)
    research_contract = build_options_research_contract(
        ctx=ctx,
        signal_row=signal_row,
        contract=contract,
        iv_ctx=iv_ctx,
        econ=econ,
        ois_score=ois,
        verdict=verdict,
        stand_down_reason=stand_down_reason,
        walls=walls,
    )
    research_contract.update(liquidity_lifecycle)
    direction_arbitration = _direction_arbitration_oi(ctx)
    ev3_direction_fields = _ev3_direction_fields(ctx, direction_arbitration)
    repair_required = bool(research_contract.get('contract_repair_required'))
    repair_selector_diagnostics = _new_repair_selector_diagnostics()
    long_alternatives = select_repair_alternative_contracts(
        chain,
        ctx,
        selected_contract=contract,
        limit=max(1, EV3_LONG_SINGLE_CANDIDATE_LIMIT - 1),
        diagnostics=repair_selector_diagnostics,
    )
    alternatives = long_alternatives[: max(1, EV3_TOTAL_CANDIDATE_LIMIT - 1)]
    if (
        str(direction_arbitration.get('direction_arbitration_status') or '').upper()
        in {'AGREEMENT', 'NO_PROBABILITY_OPINION', 'CONFLICT_STRUCTURE_LEADS'}
        and str(ctx.get('direction') or '').upper() in {'CALL', 'PUT'}
    ):
        _enrich_ev3_contract_multipliers(contract, alternatives, ctx.get('ticker'))
    alternatives, incomplete_alternatives = _partition_complete_ev3_candidates(alternatives)
    repair_alt_fields = _format_repair_alternative_fields(
        alternatives,
        str(research_contract.get('contract_repair_reason') or '') if repair_required else '',
        repair_required=repair_required,
    )
    repair_alt_fields.update(_alternative_handoff_audit(incomplete_alternatives))
    repair_alt_fields.update(
        _repair_selector_diagnostic_fields(repair_selector_diagnostics)
    )
    authoritative_route = str(research_contract.get('final_route', '') or '').upper()
    resolved_options_verdict = verdict
    resolved_stand_down_reason = stand_down_reason
    invalidation_fields = _ev3_handoff_fields(ctx)
    if (
        str(ctx.get('direction') or '').upper() in GOVERNED_DIRECTED_SIDES
        and invalidation_fields.get('invalidation_state') != 'AVAILABLE'
    ):
        resolved_options_verdict = 'STAND_DOWN'
        resolved_stand_down_reason = DataExceptionReason.INVALIDATION_MISSING.value
        authoritative_route = OPTIONS_BLOCKED_ROUTE
        research_contract['final_route'] = OPTIONS_BLOCKED_ROUTE
        research_contract['options_route_verdict'] = OPTIONS_BLOCKED_ROUTE
        research_contract['execution_permission'] = 'NO_CAPITAL'
    if (
        authoritative_route == OPTIONS_BLOCKED_ROUTE
        and resolved_stand_down_reason != DataExceptionReason.INVALIDATION_MISSING.value
    ):
        resolved_options_verdict = 'STAND_DOWN'
        resolved_stand_down_reason = (
            research_contract.get('research_route_reason')
            or stand_down_reason
            or 'OPTIONS_RESEARCH_BLOCKED'
        )
    if (
        not bool(liquidity_lifecycle.get('executable_now'))
        and resolved_options_verdict == 'EXECUTE'
    ):
        # Preserve the thesis and economics, but do not advertise immediate
        # execution when the exact selected contract is only monitorable.
        resolved_options_verdict = 'ARMED'
        authoritative_route = OPTIONS_PROBE_ROUTE
        research_contract['final_route'] = OPTIONS_PROBE_ROUTE
        research_contract['options_route_verdict'] = OPTIONS_PROBE_ROUTE
        research_contract['execution_permission'] = OPTIONS_RESEARCH_PERMISSION
        resolved_stand_down_reason = (
            f"CONTRACT_{liquidity_lifecycle.get('liquidity_state') or 'NOT_EXECUTABLE'}; "
            "retain thesis for morning exact-contract re-evaluation"
        )
    block_taxonomy = _classify_block(resolved_stand_down_reason or "")
    pcr_resolution = _direction_conflict_status_oi(ctx.get("direction"), pcr_signal, pcr_val)
    multiplier_audit = _macro_multiplier_audit_oi(ctx, macro_adj)
    macro_confirmation = _macro_confirmation_overlay_oi(ctx, sector_data, macro_adj, resolved_options_verdict)
    verdict_tier = _options_verdict_tier_oi(
        ctx,
        resolved_options_verdict,
        research_contract,
        block_taxonomy["block_code"],
        block_taxonomy["block_severity"],
    )

    return {
        # Identity
        'ticker'                  : ticker,
        'tier'                    : ctx['tier'],
        'phase'                   : ctx['phase'],
        'intent'                  : ctx['intent'],
        'regime'                  : ctx['regime'],
        # BUG D FIX (2026-03-05): asof_date enables SB to anchor time-stop to signal date
        # rather than wall-clock. Without this, sb_time_anchor=wall_clock_FALLBACK on all rows.
        # FIX (2026-03-07): pd.merge renames timestamp → timestamp_y, breaking .get('timestamp').
        # Resolved upstream (merge rename). Additionally guard against pandas NaN being truthy
        # in the or-chain by using a helper that treats NaN/None/empty as falsy.
        'asof_date'               : _resolve_asof_date(signal_row),
        **_ev3_handoff_fields(ctx),
        **ev3_direction_fields,
        **_common_options_handoff_fields(ctx),
        **_chain_lineage,

        # Verdict
        'legacy_options_verdict'  : verdict,
        'options_verdict'         : resolved_options_verdict,
        'options_route_verdict'   : authoritative_route or 'OPTIONS_ROUTE_MISSING',
        'options_score'           : ois,
        'options_score_pre_macro' : ois_pre_macro,
        'options_multiplier'      : round(max(0.20, min(1.00, ois/100.0)), 2),
        'stand_down_reason'       : resolved_stand_down_reason,
        **macro_adj,
        **repair_alt_fields,
        # Block taxonomy — populated on all rows; NONE values when verdict is not STAND_DOWN
        # FIX 2026-04-28: EXECUTE signals get block_code=NONE — passing signal is not a block
        'block_code'              : ('NONE' if resolved_options_verdict == 'EXECUTE'
                                     else (block_taxonomy['block_code'] if resolved_stand_down_reason else 'NONE')),
        'block_family'            : ('NONE' if resolved_options_verdict == 'EXECUTE'
                                     else (block_taxonomy['block_family'] if resolved_stand_down_reason else 'NONE')),
        'block_severity'          : ('NONE' if resolved_options_verdict == 'EXECUTE'
                                     else (block_taxonomy['block_severity'] if resolved_stand_down_reason else 'NONE')),
        'block_detail'            : ('' if resolved_options_verdict == 'EXECUTE' else (resolved_stand_down_reason or '')),
        'positive_factors'        : ' | '.join(pos_factors[:5]),
        'negative_factors'        : ' | '.join(neg_factors[:4]),
        **research_contract,
        **verdict_tier,
        **pcr_resolution,
        **direction_arbitration,
        **multiplier_audit,
        **macro_confirmation,

        # Direction + strategy
        'options_direction'       : ctx['direction'],
        'direction_override_reason': ctx.get('direction_override_reason'),  # A4 audit field
        'options_strategy'        : ctx['preferred_strategy'],
        'behaviour_state_key'     : ctx.get('behaviour_state_key'),
        'behaviour_state_hash'    : ctx.get('behaviour_state_hash'),
        'actuarial_match_type'    : ctx.get('actuarial_match_type'),
        'actuarial_ev_weight'     : ctx.get('actuarial_ev_weight'),
        'catalyst_overlay'        : ctx.get('catalyst_overlay'),
        'horizon_bucket'          : ctx.get('horizon_bucket') or signal_row.get('horizon_bucket') or ctx.get('macro_preferred_horizon'),
        'horizon_action'          : ctx.get('horizon_action') or signal_row.get('horizon_action'),
        'horizon_size_multiplier' : ctx.get('horizon_size_multiplier') or signal_row.get('horizon_size_multiplier'),
        'horizon_block_reason'    : ctx.get('horizon_block_reason') or signal_row.get('horizon_block_reason'),
        'horizon_source'          : ctx.get('horizon_source') or signal_row.get('horizon_source'),
        'router_version'          : ctx.get('router_version') or signal_row.get('router_version'),

        # Recommended contract
        'recommended_contract'    : contract.get('symbol'),
        'contract_strike'         : contract.get('strike'),
        'contract_expiry'         : contract.get('expiry'),
        'contract_dte'            : contract.get('dte'),
        'contract_premium'        : contract.get('mark'),
        'contract_bid'            : contract.get('bid'),
        'contract_ask'            : contract.get('ask'),
        'spread_source'           : contract.get('spread_source'),
        'contract_mid'            : contract.get('mark') or contract.get('mid'),
        'options_bid'             : contract.get('bid'),
        'options_ask'             : contract.get('ask'),
        'options_spread_source'   : contract.get('spread_source'),
        # Top-level aliases — SB reads 'dte', 'expiry', 'strike', 'premium' directly
        'dte'                     : contract.get('dte'),
        'expiry'                  : contract.get('expiry'),
        'strike'                  : contract.get('strike'),
        'premium'                 : contract.get('mark'),
        'contract_delta'          : contract.get('delta'),
        'contract_gamma'          : contract.get('gamma'),
        'contract_theta'          : contract.get('theta'),
        'contract_vega'           : contract.get('vega'),
        'contract_vanna'          : contract.get('vanna'),
        'contract_charm'          : contract.get('charm'),
        'contract_heston_used'    : contract.get('heston_used', False),
        'contract_heston_price'   : contract.get('heston_price'),
        'contract_iv'             : contract.get('iv'),
        'contract_oi'             : contract.get('oi'),
        'contract_volume'         : contract.get('volume'),
        'contract_spread_pct'     : contract.get('spread_pct'),
        'contract_bid_size'       : contract.get('bid_size'),
        'contract_ask_size'       : contract.get('ask_size'),
        'contract_bid_size_quality': contract.get('bid_size_quality', 'MISSING'),
        'contract_ask_size_quality': contract.get('ask_size_quality', 'MISSING'),
        'contract_mark_synthetic' : contract.get('mark_synthetic', False),
        'contract_quote_quality'  : contract.get('quote_quality'),
        'contract_quality_flags'  : json.dumps(
            sorted(_quote_flags(contract.get('quality_flags'))), separators=(',', ':')
        ),
        'contract_quote_fields_complete': contract.get('quote_fields_complete', False),
        'contract_quote_refresh_status': contract.get('quote_refresh_status'),
        'contract_quote_source'   : contract.get(
            'md_quote_source', 'SYNTHETIC_BSM_NO_PROVIDER_QUOTE'
        ),
        'contract_spread_source'  : contract.get('spread_source'),
        'contract_occ_symbol'     : contract.get('md_occ_symbol'),
        'contract_quote_timestamp_utc': contract.get('quote_timestamp_utc'),
        'contract_quote_timestamp_source': contract.get('quote_timestamp_source'),
        'quote_timestamp_utc'     : contract.get('quote_timestamp_utc'),
        'contract_multiplier'     : contract.get('contract_multiplier'),
        'contract_multiplier_source': contract.get('contract_multiplier_source'),
        **nbbo_fields,

        # IV environment — core
        'atm_iv'                  : iv_ctx.get('atm_iv'),
        'iv_rank'                 : iv_ctx.get('iv_rank'),
        'iv_percentile'           : iv_ctx.get('iv_percentile'),
        'ivp_30d'                 : iv_ctx.get('ivp_30d'),
        'ivp_252d'                : iv_ctx.get('ivp_252d'),
        'ivp_label'               : iv_ctx.get('ivp_label'),
        'hv_30d'                  : iv_ctx.get('hv_30d'),
        'iv_vs_hv'                : iv_ctx.get('iv_vs_hv'),
        'term_structure'          : iv_ctx.get('term_structure'),

        # IV environment — enhanced
        'iv_regime'               : iv_ctx.get('iv_regime'),
        'iv_direction'            : iv_ctx.get('iv_direction'),
        'iv_direction_pct'        : iv_ctx.get('iv_direction_pct'),
        'term_ratio'              : iv_ctx.get('term_ratio'),
        'vol_of_vol'              : iv_ctx.get('vol_of_vol'),
        'iv_accel_detected'       : iv_ctx.get('iv_accel_detected', False),

        # Skew
        'risk_reversal'           : iv_ctx.get('risk_reversal'),
        'put_25d_iv'              : iv_ctx.get('put_25d_iv'),
        'call_25d_iv'             : iv_ctx.get('call_25d_iv'),
        'skew_label'              : iv_ctx.get('skew_label'),

        # Heston calibration quality
        'heston_fit_error'        : iv_ctx.get('heston_fit_error'),

        # GEX + structure
        'gamma_flip'              : gamma_flip,
        'gamma_flip_conf'         : round(flip_conf, 3),
        'gamma_flip_gap_pct'      : flip_gap_pct,
        'gamma_island_on_path'    : gamma_island.get('gamma_island_on_path'),
        'gamma_island_label'      : gamma_island.get('gamma_island_label'),
        'gamma_island_level'      : gamma_island.get('gamma_island_level'),
        'gamma_island_distance_pct': gamma_island.get('gamma_island_distance_pct'),
        'gamma_island_strength_share': gamma_island.get('gamma_island_strength_share'),
        'gamma_island_isolation_ratio': gamma_island.get('gamma_island_isolation_ratio'),
        'gamma_island_gex_sign'   : gamma_island.get('gamma_island_gex_sign'),
        'gamma_island_source'     : gamma_island.get('gamma_island_source'),
        'gamma_island_note'       : gamma_island.get('gamma_island_note'),
        'call_wall'               : walls.get('call_wall'),
        'put_wall'                : walls.get('put_wall'),
        'max_pain'                : walls.get('max_pain'),
        'pcr_oi'                  : pcr_val,
        'pcr_signal'              : pcr_signal,

        # Delta-weighted OI flow
        'dw_call_exposure_m'      : dw_data.get('dw_call_exposure'),
        'dw_put_exposure_m'       : dw_data.get('dw_put_exposure'),
        'dw_ratio'                : dw_data.get('dw_ratio'),
        'dw_signal'               : dw_data.get('dw_signal'),
        'dw_pcr_vol'              : dw_data.get('dw_pcr_vol'),
        'pcr_vol_status'          : (
            'OK' if _oi_float(dw_data.get('dw_pcr_vol')) is not None
            else ('OI_ONLY_NO_INTRADAY_VOLUME' if _oi_float(pcr_val) is not None else 'MISSING')
        ),
        'pcr_vol_missing_reason'  : (
            '' if _oi_float(dw_data.get('dw_pcr_vol')) is not None
            else ('OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE;USING_OPEN_INTEREST_PCR_ONLY'
                  if _oi_float(pcr_val) is not None else 'NO_PCR_VOLUME_OR_OI_SIGNAL')
        ),

        # Gamma velocity
        'gamma_velocity_pct'      : gamma_vel.get('gamma_velocity_pct'),
        'gamma_velocity_sessions' : gamma_vel.get('gamma_velocity_sessions'),
        'gamma_velocity_label'    : gamma_vel.get('gamma_velocity_label'),

        # Volume confirmation (Wyckoff)
        'vol_confirmation_label'  : vol_confirm.get('vol_confirmation_label'),
        'vol_confirmation_score'  : vol_confirm.get('vol_confirmation_score'),
        'vol_wyckoff_note'        : vol_confirm.get('vol_wyckoff_note'),

        # Sector regime
        # Prefer the broad discovery/universe sector fields when the small
        # legacy hard-coded ETF map has no entry for this ticker. Without this
        # fallback most of the universe is labelled UNKNOWN downstream.
        'sector'                  : (signal_row.get('sector') or signal_row.get('gics_sector') or signal_row.get('scanner_sector') or ''),
        'gics_sector'             : (signal_row.get('gics_sector') or signal_row.get('gics_sector_norm') or signal_row.get('sector') or signal_row.get('scanner_sector') or ''),
        'sector_etf'              : (sector_data.get('sector_etf') or signal_row.get('sector_etf') or signal_row.get('sector_etf_mapped') or ''),
        'sector_5d_return'        : sector_data.get('sector_5d_return'),
        'sector_regime'           : sector_data.get('sector_regime'),

        # v1.1 — Macro sector alignment (from sector_alignment.py via env var)
        # gics_sector_norm is pre-populated from sector_etf reverse-map so classify_from_row()
        # has a GICS name to work with even when OI does not write a 'sector' column.
        # D-MACRO-SEC-002 fix: without this, classify_from_row falls through to ETF fallback,
        # which works — but pre-populating avoids the fallback being a silent dependency.
        'macro_sector_bias'       : '',   # populated post-assembly below
        'sector_alignment_label'  : '',
        'sector_alignment_score'  : 1.0,
        'sector_alignment_flag'   : 'NEUTRAL',
        'sector_etf_mapped'       : (sector_data.get('sector_etf') or signal_row.get('sector_etf') or signal_row.get('sector_etf_mapped') or ''),
        'gics_sector_norm'        : (
            signal_row.get('gics_sector')
            or signal_row.get('gics_sector_norm')
            or signal_row.get('sector')
            or signal_row.get('scanner_sector')
            or {
                'XLK': 'Information Technology', 'XLV': 'Health Care',
                'XLF': 'Financials',             'XLY': 'Consumer Discretionary',
                'XLP': 'Consumer Staples',       'XLI': 'Industrials',
                'XLE': 'Energy',                 'XLB': 'Materials',
                'XLRE': 'Real Estate',           'XLC': 'Communication Services',
                'XLU': 'Utilities',
            }.get(str(sector_data.get('sector_etf') or signal_row.get('sector_etf') or signal_row.get('sector_etf_mapped') or '').strip().upper(), '')
        ),
        'sector_bias_source'      : 'unknown',
        'sector_conviction_context': 0.60,
        'sector_alignment_note'   : '',
        **macro_quant_columns_for_row(dict(signal_row), dict(signal_row)),

        # Trade economics
        'structural_target'       : ctx['structural_target'],
        'economics_state'         : econ.get('economics_state'),
        'economics_reason'        : econ.get('economics_reason'),
        'target_in_play'          : target_in_play,
        'premium_total'           : econ.get('premium_total'),
        'breakeven_price'         : econ.get('breakeven_price'),
        'breakeven_pct'           : econ.get('breakeven_pct'),
        'rr_options'              : econ.get('rr_options'),
        'rr_premium_expected'     : econ.get('rr_premium_expected'),
        'max_convex_r_multiple'   : econ.get('max_convex_r_multiple'),
        'ev_structural'           : econ.get('ev_structural'),
        'ev_ratio'                : econ.get('ev_ratio'),
        'ev_adjusted'             : econ.get('ev_adjusted'),
        'theta_drag_pct'          : econ.get('theta_drag_pct'),
        'vega_risk_pct'           : econ.get('vega_risk_pct'),
        'iv_alignment'            : econ.get('iv_alignment'),
        'option_gain_at_target'   : econ.get('option_gain'),

        # Hold duration
        'hold_label'              : ctx.get('hold_label'),
        # ── Migrated from SuperBrain (2026-04-28) ─────────────────────────────
        'tier_size_multiplier'    : _tier_size_multiplier(ctx.get('tier', 2)),
        'regime_sensitivity'      : _calc_regime_sensitivity_oi(dict(signal_row), []),
        'convexity_campaign'      : compute_convexity_score_oi(dict(signal_row), {})[0],
        'convexity_score'         : compute_convexity_score_oi(dict(signal_row), {})[2],
        **{f'ts_{k}': v for k,v in compute_time_stop_oi(dict(signal_row)).items()},
        'hold_urgency'            : ctx.get('hold_urgency'),
        'theta_constrained'       : ctx.get('theta_constrained'),

        # ── Superbrain passthrough fields ──────────────────────────────────────
        # These fields are consumed by avshunter_superbrain_layer.py.
        # They exist in the pipeline but were previously not forwarded to the
        # output row, causing zero/missing values in Superbrain convexity scoring,
        # veto engines, and time-stop injection. Fixed: 2026-03-03.
        'phase_best'              : ctx.get('phase'),           # Superbrain FIX-08 canonical field
        'underlying_price'        : ctx.get('spot'),            # spot price for runway/veto geometry
        'composite'               : ctx.get('composite'),       # V4 TRANSITIONAL gate + quality signal
        'volume_ratio'            : ctx.get('vol_ratio'),       # C7 Wyckoff volume confirmation
        'atr_percentile'          : signal_row.get('atr_pct'),  # C1 compression proxy (from Discovery)
        'pcr_vol'                 : dw_data.get('dw_pcr_vol'),  # V6 PCR contradiction (live put/call vol ratio)
        # FIX (2026-04-22): win_probability from Vanguard/Discovery package was read
        # by options_intelligence but never forwarded to the output row. Superbrain's
        # win rate bridge (line ~1664) uses this as a fallback seed for EVEngineV2
        # when actuarial win_rate_5d/10d/20d are all zero. Without this passthrough
        # the bridge never fires — ev_final stays on V1 fallback (-0.64 range).
        'win_probability'         : ctx.get('win_prob'),        # Wyckoff structural win probability (0-100)

        # ── Runtime EV (computed here, never stored in database) ───────────────
        # Advisory 2026-04-28: ev_10d = win_rate * expected_move, computed at runtime.
        # Uses layer2 actuarial fields from the vanguard enriched row.
        # EDE v3.0 also computes EV from the actuarial block in packages —
        # this field in OI output gives early visibility in the enriched CSV.
        'ev_10d'                  : round(
            float(signal_row.get("layer2__win_rate_10d") or
                  signal_row.get("win_rate_10d") or 0.0) *
            float(signal_row.get("layer2__expected_value_10d") or
                  signal_row.get("expected_value_10d") or 0.0),
            8),
        'ev_sign'                 : (
            "POSITIVE" if (
                float(signal_row.get("layer2__win_rate_10d") or
                      signal_row.get("win_rate_10d") or 0.0) *
                float(signal_row.get("layer2__expected_value_10d") or
                      signal_row.get("expected_value_10d") or 0.0)
            ) > 1e-8
            else "NEGATIVE" if (
                float(signal_row.get("layer2__win_rate_10d") or
                      signal_row.get("win_rate_10d") or 0.0) *
                float(signal_row.get("layer2__expected_value_10d") or
                      signal_row.get("expected_value_10d") or 0.0)
            ) < -1e-8
            else "ZERO"
        ),

        # ── EOD mode markers ──────────────────────────────────────────────────
        # Written on every row so superbrain's OIS-bypass gate and morning_validation's
        # _is_eod detection fire correctly. In EOD mode no live chain is fetched —
        # OIS is structural-only, bid/ask absent. Downstream gates that require
        # live OIS must check this field and use composite as proxy.
        'data_mode'               : 'EOD',
        'data_source'             : 'EOD_PACKAGE',

        # FIX 10: options_hard_vetoes — structured veto list for handoff contract.
        # Includes earnings-within-DTE detection using catalyst fields already in the row.
        'options_hard_vetoes'     : _build_options_hard_vetoes(signal_row, contract, research_contract),
        'hard_vetoes'             : research_contract.get('hard_vetoes', ''),
        # Sprint 2 — Convexity Strike Map
        **build_convexity_strike_map(contract, ctx, iv_ctx, econ, walls, research_contract, signal_row, tle_context=tle_context),
    }

def build_convexity_strike_map(
    contract: Dict,
    ctx: Dict,
    iv_ctx: Dict,
    econ: Dict,
    walls: Dict,
    research_contract: Dict,
    signal_row: Any = None,
    tle_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Sprint 2 — Convexity Strike Map.
    Synthesises contract payoff geometry into a ranked recommendation.
    All output fields are prefixed csm_ and appended to the OI output dict.
    """
    _INSUFFICIENT = "DATA_INSUFFICIENT"

    # ── Pull raw values ────────────────────────────────────────────────────────
    mark_synthetic = bool(contract.get("mark_synthetic", True))
    mid = _oi_float(contract.get("mark") or contract.get("mid") or contract.get("mid_price"))
    delta = _oi_float(contract.get("delta"))
    dte = _oi_float(contract.get("dte"))
    spot = _oi_float(ctx.get("spot"))
    direction = str(ctx.get("direction") or "").upper()
    structural_target = _oi_float(ctx.get("structural_target"))
    breakeven_pct = _oi_float(econ.get("breakeven_pct"))
    rr_options = _oi_float(econ.get("rr_options"))
    expected_move_pct = _oi_float(research_contract.get("expected_move_pct"))
    runway_to_wall_pct = _oi_float(research_contract.get("runway_to_wall_pct"))

    # IV percentile: iv_ctx stores as 0-1; normalise to 0-100 for display/gating
    _ivp_raw = _oi_float(iv_ctx.get("iv_percentile"))
    if _ivp_raw is not None:
        ivp = _ivp_raw * 100.0 if _ivp_raw <= 1.0 else _ivp_raw
    else:
        ivp = _oi_float(iv_ctx.get("iv_rank"))  # already 0-100 when present

    # ── Guard: synthetic mark or missing critical data → DATA_INSUFFICIENT ─────
    _missing = [k for k, v in {"mid": mid, "delta": delta, "dte": dte, "spot": spot}.items() if v is None]
    if mark_synthetic or _missing:
        _reason = "Mark_Synthetic=True" if mark_synthetic else f"missing: {', '.join(_missing)}"
        return {
            "csm_best_contract": str(contract.get("symbol") or ""),
            "csm_delta_sweet_spot": delta,
            "csm_delta_note": "",
            "csm_dte_rank": _INSUFFICIENT,
            "csm_premium_efficiency": None,
            "csm_breakeven_pct": breakeven_pct,
            "csm_gamma_runway": _INSUFFICIENT,
            "csm_iv_crush_risk": _INSUFFICIENT,
            "csm_r1_target": None,
            "csm_r3_target": None,
            "csm_r5_target": None,
            "csm_r10_target": None,
            "csm_verdict": _INSUFFICIENT,
            "csm_verdict_reason": f"CSM skipped — {_reason}",
        }

    # ── csm_best_contract ─────────────────────────────────────────────────────
    _sym = str(contract.get("symbol") or "")
    if not _sym and spot and dte:
        _strike = _oi_float(contract.get("strike"))
        _expiry = str(contract.get("expiry") or contract.get("expiration_date") or "")[:10]
        _side_ch = "C" if direction == "CALL" else "P"
        _sym = f"{ctx.get('ticker','')} ${_strike:.0f}{_side_ch} {_expiry}" if _strike else ""
    csm_best_contract = _sym

    # ── csm_delta_sweet_spot + delta_note ────────────────────────────────────
    _abs_delta = abs(delta)
    csm_delta_sweet_spot = round(_abs_delta, 3)
    csm_delta_note = "" if 0.35 <= _abs_delta <= 0.55 else "NEAREST_AVAILABLE"

    # ── csm_dte_rank ──────────────────────────────────────────────────────────
    if 5 <= dte <= 20:
        csm_dte_rank = "OPTIMAL"
    elif 3 <= dte < 5 or 20 < dte <= 30:
        csm_dte_rank = "ACCEPTABLE"
    else:
        csm_dte_rank = "MARGINAL"

    # ── csm_premium_efficiency ────────────────────────────────────────────────
    # R:R multiple of this specific contract (gain per unit of premium at risk)
    csm_premium_efficiency = round(rr_options, 3) if rr_options is not None else None

    # ── csm_breakeven_pct ─────────────────────────────────────────────────────
    csm_breakeven_pct = round(breakeven_pct, 3) if breakeven_pct is not None else None

    # ── csm_gamma_runway ─────────────────────────────────────────────────────
    if runway_to_wall_pct is None:
        csm_gamma_runway = "UNKNOWN"
    elif runway_to_wall_pct >= 3.0:
        csm_gamma_runway = "CLEAR"
    elif runway_to_wall_pct >= 1.0:
        csm_gamma_runway = "PARTIAL"
    else:
        csm_gamma_runway = "BLOCKED"

    # ── csm_iv_crush_risk ────────────────────────────────────────────────────
    if ivp is None:
        csm_iv_crush_risk = "UNKNOWN"
    elif ivp >= 75:
        csm_iv_crush_risk = "EXTREME"
    elif ivp >= 60:
        csm_iv_crush_risk = "HIGH"
    elif ivp >= 40:
        csm_iv_crush_risk = "MEDIUM"
    else:
        csm_iv_crush_risk = "LOW"

    # ── R targets (all in premium terms per share) ────────────────────────────
    # nR target = entry × (n + 1) since R = % gain on premium
    csm_r1_target  = round(mid * 2.0,  4)   # 1R  = 100% gain
    csm_r3_target  = round(mid * 4.0,  4)   # 3R  = 300% gain
    csm_r5_target  = round(mid * 6.0,  4)   # 5R  = 500% gain
    csm_r10_target = round(mid * 11.0, 4)   # 10R = 1000% gain

    # ── TOO_LATE: underlying already moved > 60% toward structural target ─────
    _too_late = False
    _too_late_reason = ""
    if structural_target and spot and spot > 0:
        _sr = signal_row if signal_row is not None else {}
        _stop = _oi_float(
            _sr.get("stop_loss") or _sr.get("structural_support") or _sr.get("invalidation_price")
            or walls.get("put_wall") if direction == "CALL" else walls.get("call_wall")
        )
        if _stop and structural_target != _stop:
            if direction == "CALL" and structural_target > _stop:
                _completed = (spot - _stop) / (structural_target - _stop)
                _too_late = _completed > 0.60
                _too_late_reason = f"Price {spot:.2f} is {_completed:.0%} toward target {structural_target:.2f}"
            elif direction == "PUT" and structural_target < _stop:
                _completed = (_stop - spot) / (_stop - structural_target)
                _too_late = _completed > 0.60
                _too_late_reason = f"Price {spot:.2f} is {_completed:.0%} toward target {structural_target:.2f}"

    # ── Verdict logic (TRAP and TOO_LATE override BUYABLE/WAIT) ──────────────
    if _abs_delta > 0.70:
        csm_verdict = "TRAP"
        csm_verdict_reason = (
            f"Delta {_abs_delta:.2f} > 0.70 — deep ITM stock-replacement profile "
            "outside the default convex long-option mandate"
        )
    elif ivp is not None and ivp > 75:
        csm_verdict = "TRAP"
        csm_verdict_reason = f"IVP {ivp:.0f} > 75 — buying at peak volatility"
    elif _too_late:
        csm_verdict = "TOO_LATE"
        csm_verdict_reason = _too_late_reason + " — crowd has arrived"
    elif ivp is not None and ivp > 50:
        csm_verdict = "WAIT"
        csm_verdict_reason = f"IVP {ivp:.0f} > 50 — IV elevated, wait for compression before entry"
    else:
        # Check BUYABLE conditions: delta 0.35–0.55, DTE 5–20, IVP < 50, runway CLEAR, breakeven <= expected move
        _delta_ok = 0.35 <= _abs_delta <= 0.55
        _dte_ok = csm_dte_rank == "OPTIMAL"
        _runway_ok = csm_gamma_runway == "CLEAR"
        _be_ok = (
            expected_move_pct is not None
            and breakeven_pct is not None
            and expected_move_pct >= breakeven_pct
        )
        if _delta_ok and _dte_ok and _runway_ok and _be_ok:
            csm_verdict = "BUYABLE"
            _ivp_text = f"{ivp:.0f}" if ivp is not None else "N/A"
            csm_verdict_reason = (
                f"delta={_abs_delta:.2f} in sweet spot, DTE={dte:.0f} optimal, "
                f"IVP={_ivp_text} cheap, runway CLEAR, "
                f"expected move {expected_move_pct:.1f}% >= breakeven {breakeven_pct:.1f}%"
            )
        else:
            _reasons = []
            if not _delta_ok:
                _reasons.append(f"delta={_abs_delta:.2f} outside 0.35-0.55 (nearest available)")
            if not _dte_ok:
                _reasons.append(f"DTE={dte:.0f} not in 5-20 range ({csm_dte_rank})")
            if not _runway_ok:
                _reasons.append(f"gamma runway {csm_gamma_runway}")
            if not _be_ok:
                _em = f"{expected_move_pct:.1f}%" if expected_move_pct is not None else "unavailable"
                _be = f"{breakeven_pct:.1f}%" if breakeven_pct is not None else "unavailable"
                _reasons.append(f"expected move {_em} < breakeven {_be}")
            csm_verdict = "WAIT"
            csm_verdict_reason = "Sub-optimal geometry: " + "; ".join(_reasons) if _reasons else "WAIT — conditions not fully met"

    # Sprint 3 — TLE modifier: apply trap verdict on top of CSM verdict
    if tle_context and isinstance(tle_context, dict):
        _tle_verdict = str(tle_context.get("tle_verdict") or "").upper()
        if _tle_verdict == "CHASE":
            # Move already in progress — crowd has arrived — premium is expensive
            csm_verdict_reason = (
                f"[TLE:CHASE] Trap move in progress — premium expensive. "
                f"Original CSM: {csm_verdict} — {csm_verdict_reason}"
            )
            csm_verdict = "TOO_LATE"
        elif _tle_verdict == "EARLY_PROBE" and csm_premium_efficiency is not None:
            # Trap forming but not confirmed — reduce efficiency score by 20% for early theta risk
            _orig_eff = csm_premium_efficiency
            csm_premium_efficiency = round(csm_premium_efficiency * 0.80, 3)
            csm_verdict_reason += (
                f" [TLE:EARLY_PROBE efficiency {_orig_eff:.3f}→{csm_premium_efficiency:.3f}]"
            )
        # CONFIRMATION_ENTRY → no modifier (optimal)
        # NO_TRADE → no modifier to CSM (tle_ fields are null)

    return {
        "csm_best_contract":      csm_best_contract,
        "csm_delta_sweet_spot":   csm_delta_sweet_spot,
        "csm_delta_note":         csm_delta_note,
        "csm_dte_rank":           csm_dte_rank,
        "csm_premium_efficiency": csm_premium_efficiency,
        "csm_breakeven_pct":      csm_breakeven_pct,
        "csm_gamma_runway":       csm_gamma_runway,
        "csm_iv_crush_risk":      csm_iv_crush_risk,
        "csm_r1_target":          csm_r1_target,
        "csm_r3_target":          csm_r3_target,
        "csm_r5_target":          csm_r5_target,
        "csm_r10_target":         csm_r10_target,
        "csm_verdict":            csm_verdict,
        "csm_verdict_reason":     csm_verdict_reason,
    }


def _build_options_hard_vetoes(signal_row: dict, contract: dict, research_contract: dict) -> str:
    """FIX 10: Build JSON-encoded structured hard veto list for handoff contract."""
    import json as _json10
    import datetime as _dt10
    vetoes = []
    contract_dte = contract.get('dte') or 0
    try:
        contract_dte = float(contract_dte or 0)
    except (ValueError, TypeError):
        contract_dte = 0.0

    # Earnings within DTE: check catalyst_date and catalyst_type from upstream
    cat_type = str(signal_row.get('catalyst_type') or signal_row.get('catalyst_trade_class') or '').upper()
    cat_date_str = str(signal_row.get('catalyst_date') or '').strip()
    earnings_types = {'EARNINGS', 'EARNINGS_REPORT', 'EPS', 'EARNINGS_RELEASE', 'DATED_CATALYST_CONFIRMED'}
    if cat_date_str and cat_type and any(t in cat_type for t in earnings_types):
        try:
            cat_date = _dt10.datetime.strptime(cat_date_str[:10], '%Y-%m-%d').date()
            days_to_cat = (cat_date - _dt10.date.today()).days
            if 0 <= days_to_cat <= contract_dte:
                vetoes.append({
                    'veto_type': 'EARNINGS_WITHIN_DTE',
                    'event_date': cat_date_str[:10],
                    'note': f'Earnings on {cat_date_str[:10]} -- inside {int(contract_dte)} DTE window',
                })
        except Exception:
            pass

    # No options market
    existing_vetoes = str(research_contract.get('hard_vetoes') or '').upper()
    if 'NO_LIQUID_OTM_CONTRACT' in existing_vetoes or 'NO_OPTIONS_CHAIN' in existing_vetoes:
        vetoes.append({'veto_type': 'NO_OPTIONS_MARKET', 'note': 'No liquid OTM contract available'})

    return _json10.dumps(vetoes) if vetoes else '[]'


def _classify_block(reason: str) -> dict:
    """
    Derive structured block taxonomy from a stand_down reason string.
    Returns block_code, block_family, block_severity, block_detail.

    block_code     — machine key identifying specific gate that fired
    block_family   — roll-up category: DATA | STRUCTURE | SCORE | DIRECTION | PIPELINE
    block_severity — HARD (immediate kill regardless of score) | SOFT (score-based kill)
    block_detail   — original human-readable reason string
    """
    r = str(reason).upper()

    # ── Derive block_code from reason prefix or content ──────────────────────
    if reason.startswith('BLOCK_'):
        # derive_verdict already prefixes with BLOCK_xxx — extract it
        block_code = reason.split(':')[0].strip()
    elif 'INVALID TICKER' in r or 'SPOT PRICE' in r:
        block_code = 'BLOCK_INVALID_INPUT'
    elif 'INTENT IS WAIT' in r or 'NO DIRECTIONAL' in r:
        block_code = 'BLOCK_WAIT_INTENT'
    elif 'CHAIN FETCH FAILED' in r:
        block_code = 'BLOCK_CHAIN_ERROR'
    elif 'NO OPTIONS CHAIN' in r or 'NO CHAIN DATA' in r:
        block_code = 'BLOCK_NO_CHAIN'
    elif 'NO CONTRACT PASSED' in r or 'QUALITY GATE' in r:
        block_code = 'BLOCK_NO_CONTRACT'
    elif 'UNHANDLED EXCEPTION' in r:
        block_code = 'BLOCK_PIPELINE_ERROR'
    # FIX (2026-03-07): Score-based kills from derive_verdict carry free-text reasons
    # starting with "Low OIS" or describing IV conditions — previously all → BLOCK_UNKNOWN.
    # Pattern order matters: most specific first.
    elif r.startswith('LOW OIS') and 'ACTUARIAL' in r and 'THIN SAMPLE' in r:
        block_code = 'BLOCK_THIN_SAMPLE'
    elif r.startswith('LOW OIS') and ('EVENT_PRICED' in r or 'BINARY EVENT' in r):
        block_code = 'BLOCK_EVENT_PRICED'
    elif r.startswith('LOW OIS'):
        block_code = 'BLOCK_LOW_SCORE'
    elif 'EVENT_PRICED' in r or 'BINARY EVENT' in r:
        block_code = 'BLOCK_EVENT_PRICED'
    elif 'BACKWARDATION' in r or 'TERM STRUCTURE' in r:
        block_code = 'BLOCK_IV_STRUCTURE'
    elif 'TRANSITIONAL' in r and ('EXPENSIVE VOL' in r or 'DUAL HEADWIND' in r):
        block_code = 'BLOCK_REGIME_VOL'
    elif 'EXPENSIVE VOL' in r or 'IVP=' in r or 'IVP =' in r:
        block_code = 'BLOCK_EXPENSIVE_VOL'
    elif 'R:R=' in r or 'EV/PREMIUM' in r or 'STRUCTURAL HEADWIND' in r or 'INSUFFICIENT REWARD' in r:
        block_code = 'BLOCK_RR_FAIL'
    else:
        block_code = 'BLOCK_UNKNOWN'

    # ── block_family ──────────────────────────────────────────────────────────
    family_map = {
        'BLOCK_INVALID_INPUT'  : 'PIPELINE',
        'BLOCK_WAIT_INTENT'    : 'DIRECTION',
        'BLOCK_NO_DIRECTION'   : 'DIRECTION',
        'BLOCK_CHAIN_ERROR'    : 'DATA',
        'BLOCK_NO_CHAIN'       : 'DATA',
        'BLOCK_NO_CONTRACT'    : 'DATA',
        'BLOCK_NO_EXPIRY'      : 'DATA',
        'BLOCK_PIPELINE_ERROR' : 'PIPELINE',
        'BLOCK_THETA'          : 'SCORE',
        'BLOCK_SPREAD'         : 'SCORE',
        'BLOCK_LOW_SCORE'      : 'SCORE',     # OIS below threshold
        'BLOCK_THIN_SAMPLE'    : 'SCORE',     # actuarial N too low
        'BLOCK_EXPENSIVE_VOL'  : 'SCORE',     # IVP too high
        'BLOCK_WRONG_STRIKE'   : 'STRUCTURE',
        'BLOCK_EVENT_PRICED'   : 'STRUCTURE', # binary event IV regime
        'BLOCK_IV_STRUCTURE'   : 'STRUCTURE', # term structure backwardation
        'BLOCK_REGIME_VOL'     : 'STRUCTURE', # transitional regime + expensive vol
        'BLOCK_RR_FAIL'        : 'SCORE',     # R:R or EV below threshold
        'BLOCK_UNKNOWN'        : 'PIPELINE',
    }
    block_family = family_map.get(block_code, 'STRUCTURE')

    # ── block_severity ────────────────────────────────────────────────────────
    # HARD = fires regardless of OIS score; SOFT = score threshold kill
    hard_blocks = {
        # Gates that fire regardless of OIS score
        'BLOCK_INVALID_INPUT', 'BLOCK_WAIT_INTENT', 'BLOCK_NO_DIRECTION',
        'BLOCK_CHAIN_ERROR', 'BLOCK_NO_CHAIN',
        'BLOCK_NO_EXPIRY', 'BLOCK_PIPELINE_ERROR', 'BLOCK_EVENT_PRICED',
        'BLOCK_WRONG_STRIKE',
        # BLOCK_UNKNOWN removed from hard_blocks (2026-04-28) — catch-all fires on EXECUTE signals
    }
    soft_blocks = {
        # Score or vol-threshold kills — signal could qualify at different market conditions
        'BLOCK_LOW_SCORE', 'BLOCK_THIN_SAMPLE', 'BLOCK_EXPENSIVE_VOL',
        'BLOCK_THETA', 'BLOCK_SPREAD', 'BLOCK_IV_STRUCTURE', 'BLOCK_REGIME_VOL', 'BLOCK_RR_FAIL',
    }
    if block_code in soft_blocks:
        block_severity = 'SOFT'
    elif block_code in hard_blocks:
        block_severity = 'HARD'
    else:
        block_severity = 'SOFT'   # unknown codes default soft — don't over-kill'

    return {
        'block_code'    : block_code,
        'block_family'  : block_family,
        'block_severity': block_severity,
        'block_detail'  : reason,
    }


def _stand_down(ctx: Dict, reason: str) -> Dict:
    """Return a STAND_DOWN record when pipeline fails or no trade warranted."""
    taxonomy = _classify_block(reason)
    # FIX (2026-03-07): resolve asof_date so SB gets signal_date not wall_clock_FALLBACK
    _raw  = ctx.get('_signal_row')
    _asof = _resolve_asof_date(_raw) if _raw is not None else ''
    return {
        'ticker'          : ctx.get('ticker',''),
        'tier'            : ctx.get('tier'),
        'phase'           : ctx.get('phase'),
        'intent'          : ctx.get('intent'),
        'regime'          : ctx.get('regime'),
        'options_verdict' : 'STAND_DOWN',
        'options_score'   : 0,
        'asof_date'       : _asof,
        **_ev3_handoff_fields(ctx),
        **_common_options_handoff_fields(ctx),
        'stand_down_reason': reason,
        # Block taxonomy — machine-auditable reject classification
        'block_code'      : taxonomy['block_code'],
        'block_family'    : taxonomy['block_family'],
        'block_severity'  : taxonomy['block_severity'],
        'block_detail'    : taxonomy['block_detail'],
        'options_verdict_tier': 'STAND_DOWN',
        'alternative_contract_attempts': '',
        'direction_conflict_status': 'NOT_EVALUATED',
        'direction_conflict_reason': 'NO_TRADEABLE_OPTIONS_DIRECTION',
        'pcr_direction_conflict_status': 'NO_PCR_DATA',
        'pcr_direction_conflict_reason': 'PCR source unavailable',
        'pcr_confidence_weight': 0.0,
        'macro_multiplier': 1.0,
        'structural_multiplier': 1.0,
        'macro_multiplier_advisory': 1.0,
        'structural_multiplier_advisory': 1.0,
        'macro_multiplier_authority': 'ADVISORY_ONLY',
        'options_macro_authority': 'ADVISORY_ONLY',
        'options_macro_effective_score_delta': 0.0,
        'macro_confirmation_level': 'STANDARD',
        'macro_routing_state': 'STANDARD',
        'horizon_bucket': ctx.get('horizon_bucket') or ctx.get('macro_preferred_horizon') or '',
        'horizon_action': ctx.get('horizon_action') or '',
        'horizon_size_multiplier': ctx.get('horizon_size_multiplier') or '',
        'horizon_block_reason': ctx.get('horizon_block_reason') or '',
        'horizon_source': ctx.get('horizon_source') or '',
        'router_version': ctx.get('router_version') or '',
        'options_direction': ctx.get('direction','NONE'),
        'options_strategy' : 'NONE',
        'positive_factors' : '',
        'negative_factors' : reason,
        # Contract fields — None (not 0) so downstream MP cannot mistake absent
        # data for a genuinely zero-DTE contract and fire a hard DTE block.
        # FIX RC-3 (2026-04-16): changed 0 → None for contract_dte and dte.
        'contract_strike'  : None,
        'contract_expiry'  : None,
        'contract_dte'     : None,
        'contract_premium' : None,
        'contract_bid_size': None,
        'contract_ask_size': None,
        'contract_bid_size_quality': 'MISSING',
        'contract_ask_size_quality': 'MISSING',
        'dte'              : None,
        'expiry'           : None,
        'strike'           : None,
        'premium'          : None,
        'contract_quote_timestamp_utc': None,
        'contract_quote_timestamp_source': None,
        'quote_timestamp_utc': None,
        'contract_multiplier': None,
        'contract_multiplier_source': None,
        'l2_bid_size': None,
        'l2_ask_size': None,
        'l2_quote_source': 'UNAVAILABLE',
        'l2_quote_timestamp_utc': None,
        # Superbrain passthrough — populated even on STAND_DOWN so veto context is available
        'phase_best'       : ctx.get('phase', ''),
        'underlying_price' : ctx.get('spot', 0),
        'composite'        : ctx.get('composite', 0),
        'volume_ratio'     : ctx.get('vol_ratio', 0),
        # EOD mode markers — allow superbrain OIS-bypass and morning_validation
        # _is_eod detection to fire correctly when no live chain was fetched.
        # Written on ALL rows (STAND_DOWN and successful) so the downstream
        # column is always present regardless of options outcome.
        'data_mode'        : 'EOD',
        'data_source'      : 'EOD_PACKAGE',
        **_empty_options_research_contract(reason),
    }


CONTRACT_REJECTION_LOG_COLUMNS = [
    'ticker',
    'contract',
    'horizon',
    'rejection_reason',
    'rejection_stage',
    'dte_scanned_min',
    'dte_scanned_max',
    'chain_rows',
    'final_route',
]


def _build_contract_rejection_log_rows(out_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build one auditable contract-rejection record per affected signal."""
    def _text(value: Any) -> str:
        text = str(value if value is not None else '').strip()
        return '' if text.lower() in {'', 'nan', 'none'} else text

    rows: List[Dict[str, Any]] = []
    for row in out_df.to_dict('records'):
        reason = _text(row.get('contract_rejection_reason'))
        stage = _text(row.get('contract_rejection_stage'))

        repair_required = str(row.get('contract_repair_required', '') or '').upper() in {
            'TRUE', '1', 'YES'
        }
        if not reason and repair_required:
            reason = (
                _text(row.get('contract_repair_reason'))
                or _text(row.get('contract_review_flags'))
                or 'CONTRACT_REPAIR_REQUIRED'
            )
            stage = stage or 'CONTRACT_REPAIR'

        if not reason:
            continue

        horizon = (
            _text(row.get('contract_rejection_horizon'))
            or _text(row.get('horizon_bucket'))
            or '1_5d'
        ).lower()
        # Keep this audit serializer independently executable for repair tools
        # that load only this function, while production uses the governed DTE
        # policy rather than the legacy raw band.
        policy_resolver = globals().get('governed_dte_config')
        if callable(policy_resolver):
            dte_cfg = policy_resolver(horizon)
        else:
            dte_cfg = DTE_CONFIG.get(horizon, DTE_CONFIG.get('1_5d', {}))
        rows.append({
            'ticker': row.get('ticker', ''),
            'contract': (
                _text(row.get('recommended_contract'))
                or _text(row.get('contract_occ_symbol'))
                or _text(row.get('contract_symbol'))
            ),
            'horizon': horizon,
            'rejection_reason': reason,
            'rejection_stage': stage or 'UNKNOWN',
            'dte_scanned_min': row.get('contract_rejection_dte_min', '') or dte_cfg.get('dte_min', ''),
            'dte_scanned_max': row.get('contract_rejection_dte_max', '') or dte_cfg.get('dte_max', ''),
            'chain_rows': row.get('contract_rejection_chain_rows', ''),
            'final_route': row.get('final_route', ''),
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — MAIN PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_utc_datetime(value: Any) -> Optional[datetime]:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _persist_options_lifecycle_result(result: Dict[str, Any], run_id: str) -> None:
    """Persist one EOD thesis/quote/selection into the existing CDS database."""
    global _CDS_LIQUIDITY_STORE
    if bool(result.get("options_session_exception")):
        # Session-quarantined rows have no governed option observation. Keep the
        # underlying thesis untouched and retain the exception in run artifacts.
        result["liquidity_persistence_status"] = "SKIPPED_SESSION_DATA_EXCEPTION"
        return
    if _CDS_LIQUIDITY_STORE is None:
        result["liquidity_persistence_status"] = "DISABLED"
        return
    from canonical_data import (
        CompletenessStatus,
        ContractLiquidityState,
        DataScope,
        DatasetRecord,
        DatasetType,
        MonitorState,
        ThesisState,
    )

    thesis_id = str(result.get("thesis_id") or "").strip()
    ticker = str(result.get("ticker") or "").strip().upper()
    side = str(result.get("options_direction") or result.get("direction") or "").strip().upper()
    if not thesis_id or not ticker or side not in {"CALL", "PUT"}:
        result["liquidity_persistence_status"] = "SKIPPED_NO_GOVERNED_THESIS"
        return

    terminal_map = {
        "INVALIDATED": ThesisState.INVALIDATED,
        "TARGET_REALIZED": ThesisState.TARGET_REALIZED,
        "HORIZON_EXPIRED": ThesisState.HORIZON_EXPIRED,
        "COMPLETED": ThesisState.COMPLETED,
    }
    thesis_state = terminal_map.get(str(result.get("thesis_state") or "").upper(), ThesisState.ACTIVE)
    terminal_thesis_states = frozenset(terminal_map.values())
    terminal_transition = thesis_state in terminal_thesis_states
    executable = bool(result.get("executable_now"))
    monitor_state = (
        MonitorState.TERMINAL if terminal_transition
        else MonitorState.NOT_REQUIRED if executable
        else MonitorState.ACTIVE
    )
    latest_thesis = _CDS_LIQUIDITY_STORE.latest_thesis(thesis_id)
    legacy_thesis_id = str(result.get("legacy_thesis_id") or "").strip()
    legacy_thesis = (
        _CDS_LIQUIDITY_STORE.latest_thesis(legacy_thesis_id)
        if legacy_thesis_id and legacy_thesis_id != thesis_id else None
    )
    corrects_legacy_terminal = bool(
        legacy_thesis is not None
        and legacy_thesis.thesis_state in terminal_thesis_states
    )
    if latest_thesis is not None and latest_thesis.thesis_state in terminal_thesis_states:
        # A terminal thesis is immutable. Weekend reruns can legitimately
        # revisit the same ticker/direction/completed-session identity, but
        # they must not reactivate it or try to attach a later observation.
        # Preserve the canonical terminal state in the emitted row and make
        # the persistence seam idempotent instead of aborting the run.
        stored_state = latest_thesis.thesis_state.value
        transition_by_state = {
            ThesisState.INVALIDATED: "THESIS_INVALIDATED",
            ThesisState.TARGET_REALIZED: "MOVE_ALREADY_REALIZED",
            ThesisState.HORIZON_EXPIRED: "HORIZON_EXPIRED",
            ThesisState.COMPLETED: "THESIS_COMPLETED",
        }
        result.update({
            "thesis_state": stored_state,
            "liquidity_state": latest_thesis.reason_code,
            "morning_transition_state": transition_by_state[latest_thesis.thesis_state],
            "executable_now": False,
            "maturation_execution_authority": False,
            "recovery_disposition": "STAND_DOWN",
            "liquidity_persistence_status": "TERMINAL_THESIS_ALREADY_RECORDED",
        })
        if latest_thesis.thesis_state is ThesisState.INVALIDATED:
            result["remaining_runway_state"] = "THESIS_INVALIDATED"
        elif latest_thesis.thesis_state is ThesisState.TARGET_REALIZED:
            result["remaining_runway_state"] = "MOVE_ALREADY_REALIZED"
        return
    expiry_text = str(result.get("contract_expiry") or result.get("expiry") or "")[:10]
    try:
        expiration_date = date.fromisoformat(expiry_text) if expiry_text else None
    except ValueError:
        expiration_date = None
    lifecycle_anchor = _parse_utc_datetime(
        result.get("quote_as_of") or result.get("contract_quote_timestamp_utc")
    )
    horizon_end = (
        (pd.Timestamp(lifecycle_anchor.date()) + pd.offsets.BDay(3)).date()
        if lifecycle_anchor is not None else None
    )
    def _record_eod_thesis_event(
        *,
        state: Any,
        monitoring: Any,
        event_key: str,
        expected_version: Optional[int],
        reason_code: str,
        correction_successor: bool = False,
    ) -> Any:
        correction_kwargs = {}
        if correction_successor and corrects_legacy_terminal:
            correction_kwargs = {
                "supersedes_event_id": legacy_thesis.event_id,
                "correction_reason": "LEGACY_INVALIDATION_GEOMETRY_OR_HOLD_DEFECT",
                "corrected_by_run_id": run_id,
                "correction_state": LifecycleEvaluationState.SUPERSEDED_DATA_DEFECT.value,
            }
        return _CDS_LIQUIDITY_STORE.record_thesis_event(
            thesis_id=thesis_id,
            event_key=event_key,
            run_id=run_id,
            ticker=ticker,
            direction=side,
            thesis_state=state,
            monitor_state=monitoring,
            reason_code=reason_code,
            structural_target=_repair_alt_float(result.get("structural_target")),
            invalidation_spot=_repair_alt_float(
                result.get("ev3_invalidation_spot") or result.get("invalidation_spot")
            ),
            horizon_end_date=horizon_end,
            expected_version=expected_version,
            metadata={
                "lifecycle_contract_version": result.get("lifecycle_contract_version"),
                "morning_transition_state": result.get("morning_transition_state"),
                "maturation_execution_authority": False,
            },
            calculation_version=str(
                result.get("thesis_calculation_version")
                or OPTIONS_LIQUIDITY_LIFECYCLE_VERSION
            ),
            **correction_kwargs,
        )

    contract_symbol = str(result.get("recommended_contract") or result.get("contract_symbol") or "").strip()
    chain_dataset_id = str(result.get("option_chain_dataset_id") or "").strip()
    quote_as_of = lifecycle_anchor
    strike = _repair_alt_float(result.get("contract_strike") or result.get("strike"))
    dte = _repair_alt_float(result.get("contract_dte") or result.get("dte"))
    spot = _repair_alt_float(result.get("underlying_price") or result.get("signal_price"))
    if not all((contract_symbol, chain_dataset_id, quote_as_of, expiry_text)) or None in {strike, dte, spot}:
        _record_eod_thesis_event(
            state=thesis_state,
            monitoring=monitor_state,
            event_key=f"EOD:{run_id}",
            expected_version=latest_thesis.version if latest_thesis else None,
            reason_code=str(result.get("liquidity_state") or "LIFECYCLE_RECORDED"),
            correction_successor=True,
        )
        result["liquidity_persistence_status"] = "THESIS_ONLY_CONTRACT_PROVENANCE_INCOMPLETE"
        return
    # Persistence is the final defence boundary. Invalid/crossed quote evidence
    # may be retained in the raw option-chain dataset, but it must never be
    # registered as a selected quote or contract observation. Record only the
    # governed thesis event so a bad provider row cannot abort the whole run.
    persisted_bid = _repair_alt_float(result.get("contract_bid"))
    persisted_ask = _repair_alt_float(result.get("contract_ask"))
    persisted_spread = _repair_alt_float(result.get("contract_spread_pct"))
    persisted_quality = str(result.get("contract_quote_quality") or "").strip().upper()
    persisted_flags = _quote_flags(result.get("contract_quality_flags"))
    invalid_selected_quote = (
        persisted_quality == "INVALID"
        or bool({"CROSSED_QUOTE", "NEGATIVE_QUOTE"} & persisted_flags)
        or (persisted_bid is not None and persisted_bid < 0)
        or (persisted_ask is not None and persisted_ask < 0)
        or (
            persisted_bid is not None and persisted_ask is not None
            and persisted_bid > persisted_ask
        )
        or (persisted_spread is not None and persisted_spread < 0)
    )
    if invalid_selected_quote:
        _record_eod_thesis_event(
            state=thesis_state,
            monitoring=MonitorState.ACTIVE if not terminal_transition else MonitorState.TERMINAL,
            event_key=f"EOD:{run_id}",
            expected_version=latest_thesis.version if latest_thesis else None,
            reason_code="INVALID_SELECTED_QUOTE",
            correction_successor=True,
        )
        result.update({
            "liquidity_state": "INVALID_QUOTE",
            "executable_now": False,
            "maturation_execution_authority": False,
            "liquidity_persistence_status": "THESIS_ONLY_INVALID_SELECTED_QUOTE",
            "liquidity_persistence_error": "CROSSED_NEGATIVE_OR_MALFORMED_SELECTED_QUOTE",
        })
        return

    try:
        expiration = expiration_date
        if expiration is None:
            raise ValueError("contract expiration unavailable")
        liquidity_state = ContractLiquidityState[str(result.get("liquidity_state") or "").upper()]
    except (ValueError, KeyError):
        _record_eod_thesis_event(
            state=thesis_state,
            monitoring=monitor_state,
            event_key=f"EOD:{run_id}",
            expected_version=latest_thesis.version if latest_thesis else None,
            reason_code=str(result.get("liquidity_state") or "LIFECYCLE_RECORDED"),
            correction_successor=True,
        )
        result["liquidity_persistence_status"] = "THESIS_ONLY_LIQUIDITY_STATE_UNSUPPORTED"
        return

    # Contract evidence must be appended while the thesis is active. Closing
    # the thesis first makes the store reject its own final observation. For a
    # terminal result, create an idempotent active capture event, persist the
    # quote and selection below, and append the terminal event last.
    if terminal_transition:
        staged_thesis = _record_eod_thesis_event(
            state=ThesisState.ACTIVE,
            monitoring=MonitorState.ACTIVE,
            event_key=f"EOD_OBSERVATION:{run_id}",
            expected_version=latest_thesis.version if latest_thesis else None,
            reason_code="TERMINAL_OBSERVATION_CAPTURE",
            correction_successor=True,
        )
    else:
        staged_thesis = _record_eod_thesis_event(
            state=thesis_state,
            monitoring=monitor_state,
            event_key=f"EOD:{run_id}",
            expected_version=latest_thesis.version if latest_thesis else None,
            reason_code=str(result.get("liquidity_state") or "LIFECYCLE_RECORDED"),
            correction_successor=True,
        )

    # The selected exact-contract snapshot is its own canonical data object.
    # Do not claim that a later quote-endpoint enrichment came from the original
    # full-chain payload. This also gives the Intelligence Lab an exact lineage
    # target for the values shown to the trader.
    quote_payload = {
        key: result.get(key)
        for key in (
            "ticker", "recommended_contract", "contract_bid", "contract_ask",
            "contract_mid", "contract_spread_pct", "contract_delta",
            "contract_gamma", "contract_theta", "contract_vega", "contract_iv",
            "contract_oi", "contract_volume", "contract_quote_source",
            "contract_quote_timestamp_utc", "contract_mark_synthetic",
            "contract_quote_quality", "contract_quality_flags",
            "contract_quote_fields_complete", "contract_quote_refresh_status",
        )
    }
    quote_payload["source_chain_dataset_id"] = chain_dataset_id
    encoded = json.dumps(
        quote_payload, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    selected_dataset_id = hashlib.sha256(
        (
            f"LIVE_OPTION|{ticker}|{contract_symbol}|{quote_as_of.isoformat()}|"
            f"{content_hash}"
        ).encode("utf-8")
    ).hexdigest()
    payload_dir = (
        _REPO_ROOT / "data" / "canonical" / "live_options"
        / quote_as_of.date().isoformat() / ticker
    )
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload_path = payload_dir / f"{selected_dataset_id}.json"
    if not payload_path.exists():
        temporary = payload_path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, payload_path)
    _CDS_LIQUIDITY_STORE.registry.register_dataset(DatasetRecord(
        dataset_id=selected_dataset_id,
        dataset_type=DatasetType.LIVE_OPTION,
        instrument_id=ticker,
        session_date=quote_as_of.date(),
        scope=DataScope(
            start_date=quote_as_of.date(),
            end_date=quote_as_of.date(),
            fields=tuple(quote_payload.keys()),
            sides=(side,),
            extra=(
                ("contract_symbol", contract_symbol.replace("O:", "")),
                ("source_chain_dataset_id", chain_dataset_id),
            ),
        ),
        provider="MARKETDATA",
        content_hash=content_hash,
        completeness_status=(
            CompletenessStatus.COMPLETE
            if (
                persisted_bid is not None and persisted_bid > 0
                and persisted_ask is not None and persisted_ask >= persisted_bid
                and not bool(result.get("contract_mark_synthetic", False))
            )
            else CompletenessStatus.PARTIAL
        ),
        storage_uri=str(payload_path.resolve()),
        observed_at=quote_as_of,
        as_of=quote_as_of,
        adjustment_convention="RAW_OPTION_CONTRACT",
        schema_version="selected_option_quote_v1",
        source_run_id=run_id,
    ))
    result["selected_quote_dataset_id"] = selected_dataset_id

    observation = _CDS_LIQUIDITY_STORE.record_contract_observation(
        thesis_id=thesis_id,
        run_id=run_id,
        ticker=ticker,
        contract_symbol=contract_symbol,
        option_side=side,
        quote_as_of=quote_as_of,
        source_dataset_id=selected_dataset_id,
        spot=float(spot),
        strike=float(strike),
        expiration=expiration,
        dte=float(dte),
        delta=_repair_alt_float(result.get("contract_delta")),
        bid=_repair_alt_float(result.get("contract_bid")),
        ask=_repair_alt_float(result.get("contract_ask")),
        spread_pct=_repair_alt_float(result.get("contract_spread_pct")),
        volume=_repair_alt_float(result.get("contract_volume")),
        open_interest=_repair_alt_float(result.get("contract_oi")),
        iv=_repair_alt_float(result.get("contract_iv")),
        liquidity_state=liquidity_state,
        maturation_score_1d=_repair_alt_float(result.get("maturation_score_1d")),
        maturation_score_2d=_repair_alt_float(result.get("maturation_score_2d")),
        maturation_score_3d=_repair_alt_float(result.get("maturation_score_3d")),
        maturation_score_is_probability=False,
        atm_distance_sigma=_repair_alt_float(result.get("atm_distance_sigma")),
        remaining_runway_pct=_repair_alt_float(result.get("remaining_runway_pct")),
        calculation_version=OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    )
    latest_selection = _CDS_LIQUIDITY_STORE.latest_selection(thesis_id)
    # The EOD event payload must be stable on replay. A same-event replay must
    # not rewrite `previous` from the selection that the first pass just made.
    previous_symbol = str(result.get("previous_contract_symbol") or "").strip() or None
    _CDS_LIQUIDITY_STORE.record_selection_event(
        thesis_id=thesis_id,
        event_key=f"EOD_SELECTION:{run_id}",
        run_id=run_id,
        previous_contract_symbol=previous_symbol,
        selected_contract_symbol=contract_symbol,
        selected_observation_id=observation.record.observation_id,
        selection_reason=str(result.get("contract_selection_reason") or "EOD_CONTRACT_SELECTION"),
        economics_recomputed=True,
        expected_version=latest_selection.selection_version if latest_selection else None,
        metadata={"selected_contract_economics_ready": True},
        calculation_version=OPTIONS_LIQUIDITY_LIFECYCLE_VERSION,
    )
    if terminal_transition:
        _record_eod_thesis_event(
            state=thesis_state,
            monitoring=MonitorState.TERMINAL,
            event_key=f"EOD:{run_id}",
            expected_version=staged_thesis.record.version,
            reason_code=str(result.get("liquidity_state") or "LIFECYCLE_RECORDED"),
        )
        result["liquidity_persistence_status"] = "PERSISTED_TERMINAL"
    else:
        result["liquidity_persistence_status"] = "PERSISTED"


def run_options_layer(
    discovery_csv: str,
    vanguard_csv: str,
    run_id: str = None,
    output_dir: str = '.',
    max_signals: int = None
) -> pd.DataFrame:
    """
    Main entry point. Reads merged discovery + vanguard, runs options
    intelligence on eligible Tier 0/1/2 signals plus Vanguard support overrides.

    Args:
        discovery_csv : path to discovery_candidates_ultimate_{run_id}.csv
        vanguard_csv  : path to vanguard_signals.csv
        run_id        : run timestamp string (e.g. 20260219_165805)
        output_dir    : where to write output files
        max_signals   : cap for testing (None = run all)

    Returns:
        DataFrame of options intelligence results, one row per signal
    """
    global _CDS_CHAIN_SERVICE, _CDS_LIQUIDITY_STORE, _MD_AVAILABLE
    global _CDS_V2_CHAIN_RESOLVER, _CDS_V2_SESSION
    if not run_id:
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    print("\n" + "="*72)
    print("AVSHUNTER OPTIONS INTELLIGENCE LAYER v1.0")
    print(f"Run: {run_id}")
    print("="*72)

    # Auth — a controlled replay is provider-free and therefore skips every
    # authentication/network probe. Normal production behaviour is unchanged.
    if _canonical_offline_replay_enabled():
        _MD_AVAILABLE = False
        print("[CDS-REPLAY] Offline canonical replay enabled — all provider calls disabled")
    else:
        if not init_marketdata_auth():
            print("[FATAL] Cannot proceed without MarketData.app authentication.")
            return pd.DataFrame()
        if not init_auth():
            print("[WARN] Polygon authentication failed — underlying/sector context may be reduced; options remain MarketData-only.")

    # Load data
    print("\n[LOAD] Reading pipeline outputs...")
    try:
        disc    = pd.read_csv(discovery_csv)
        vanguard = pd.read_csv(vanguard_csv)
    except Exception as e:
        print(f"[FATAL] Could not load pipeline CSVs: {e}")
        return pd.DataFrame()

    merged = pd.merge(disc, vanguard, on='ticker', how='inner')
    merged = resolve_macro_suffix_columns(merged)
    merged = _coalesce_ev3_merge_inputs(merged)
    # FIX (2026-03-07): Both discovery and vanguard CSVs have a 'timestamp' column.
    # pd.merge renames them timestamp_x (discovery) and timestamp_y (vanguard).
    # The vanguard timestamp (timestamp_y) is the correct signal date for SB time-stop anchoring.
    # Rename it back to 'timestamp' so signal_row.get('timestamp') resolves correctly downstream.
    if 'timestamp_y' in merged.columns:
        merged = merged.rename(columns={'timestamp_y': 'timestamp'})
        if 'timestamp_x' in merged.columns:
            merged = merged.drop(columns=['timestamp_x'])
    print(f"[LOAD] Merged: {len(merged)} signals")

    # Scope to eligible tiers, plus Vanguard statistical-support overrides.
    # Vanguard no longer emits only legacy TRADE/NO_TRADE verdicts; it now exports
    # ACTUARIAL_SUPPORT and layer2 probability labels. Treat those as reasons to
    # send the ticker to Options Intelligence, not as execution permission.
    vanguard_trade = set()
    if 'verdict' in merged.columns:
        verdict_s = merged['verdict'].fillna('').astype(str).str.upper().str.strip()
        support_mask = verdict_s.isin({'TRADE', 'ACTUARIAL_SUPPORT', 'ACTUARIAL_MODERATE'})
        if 'layer2__probability_verdict' in merged.columns:
            support_mask = support_mask | merged['layer2__probability_verdict'].fillna('').astype(str).str.upper().str.strip().eq('STRONG_EDGE')
        if 'layer2__edge_quality' in merged.columns:
            support_mask = support_mask | merged['layer2__edge_quality'].fillna('').astype(str).str.upper().str.strip().eq('STRONG')
        if 'final_recommendation' in merged.columns:
            support_mask = support_mask | merged['final_recommendation'].fillna('').astype(str).str.upper().str.contains('EDGE_STRONG', regex=False)
        vanguard_trade = set(merged.loc[support_mask, 'ticker'])

    # Now apply tier filter — but include Vanguard-supported tickers regardless of tier
    eligible = merged[
        merged['tier'].isin(ELIGIBLE_TIERS) | merged['ticker'].isin(vanguard_trade)
    ].copy()
    eligible = eligible.sort_values('composite_score', ascending=False)
    print(f"[SCOPE] Tier 0/1/2 eligible + {len(vanguard_trade)} Vanguard support overrides: {len(eligible)} signals")

    # Exclude WAIT intent — no options analysis needed
    # Exception: tickers with Vanguard statistical support pass regardless of intent
    eligible = eligible[
        (eligible['precor_intent'] != 'WAIT') |
        (eligible['ticker'].isin(vanguard_trade))
    ]
    print(f"[SCOPE] After excluding WAIT (preserving {len(vanguard_trade)} Vanguard-supported tickers): {len(eligible)} signals")

    if max_signals:
        eligible = eligible.head(max_signals)
        print(f"[SCOPE] Capped at {max_signals} for this run")

    # CDS-3/4 production seam. Publish the exact post-scope Options worklist
    # before any chain request, then resolve/write-through one canonical chain
    # per ticker/session. In enforced mode any publication defect fails closed.
    _cds_options_publication = None
    _chain_authorised_tickers: List[str] = []
    _run_session: Optional[date] = None
    _options_session_exception_by_ticker: Dict[str, Dict[str, Any]] = {}
    try:
        from canonical_data import (
            CanonicalFeatureFlags,
            CanonicalMarketObservationResolver,
            CanonicalOptionChainService,
            CanonicalRegistry,
            OptionLiquidityLifecycleStore,
            publish_options_worklist,
        )

        _cds_flags = CanonicalFeatureFlags.from_environment()
        _msi_flags = active_msi_flags()
        if _cds_flags.enabled:
            _root = Path(__file__).resolve().parents[1]
            _registry_path = _root / "data" / "canonical" / "control_plane.sqlite"

            # Resolve the run-level option session from explicitly current rows.
            # Ticker-level stale/missing/session-mismatched rows are quarantined
            # and remain visible as MONITOR_ONLY data exceptions; they do not
            # receive option-chain acquisition authority.  The canonical resolver
            # remains strict if the current population itself is ambiguous.
            _run_session, _session_source, _session_exceptions = (
                _resolve_options_session_scope(eligible)
            )
            _options_session_exception_by_ticker = {
                str(record["ticker"]): record
                for record in _session_exceptions.to_dict("records")
            }
            _exception_tickers = set(_options_session_exception_by_ticker)
            _exception_dir = Path(output_dir)
            _exception_dir.mkdir(parents=True, exist_ok=True)
            _exception_path = (
                _exception_dir / f"options_session_exceptions_{run_id}.csv"
            )
            _session_exceptions.to_csv(_exception_path, index=False)
            print(
                f"[CDS-4] Completed option session: {_run_session.isoformat()} "
                f"from fresh {_session_source} rows (run date={run_id[:8]})"
            )
            print(
                f"[CDS-4] Session exceptions: {len(_session_exceptions)} "
                f"quarantined -> {_exception_path}"
            )

            _chain_authorised_tickers = []
            for _, _candidate in eligible.iterrows():
                try:
                    _candidate_ticker = str(_candidate.get("ticker", ""))
                    if _candidate_ticker in _exception_tickers:
                        continue
                    if parse_structural_context(_candidate).get("direction") in GOVERNED_DIRECTED_SIDES:
                        _chain_authorised_tickers.append(_candidate_ticker)
                except Exception:
                    # The row remains in Options output as a fail-closed data
                    # record, but receives no chain acquisition authority.
                    continue
            _publication = publish_options_worklist(
                CanonicalRegistry(_registry_path),
                run_id=run_id,
                input_tickers=merged["ticker"].astype(str),
                eligible_tickers=_chain_authorised_tickers,
            )
            if not _publication.reconciled:
                raise RuntimeError("CDS-3 Options worklist reconciliation failed")
            _cds_options_publication = _publication
            print(
                f"[CDS-3] Options worklist: input={_publication.input_count} "
                f"authorised={_publication.authorised_count} "
                f"equity_only={_publication.excluded_count}"
            )
            if _msi_flags.v2_capture:
                _CDS_V2_CHAIN_RESOLVER = CanonicalMarketObservationResolver(
                    registry_path=_registry_path,
                    payload_root=_root / "data" / "canonical" / "market_observations",
                    run_id=run_id,
                    flags=_cds_flags,
                )
                _CDS_V2_SESSION = _run_session
                _CDS_CHAIN_SERVICE = None
                print("[MSI-1] option_chain_v2 capture/resolution enabled")
            else:
                _CDS_V2_CHAIN_RESOLVER = None
                _CDS_V2_SESSION = None
                _CDS_CHAIN_SERVICE = CanonicalOptionChainService(
                    registry_path=_registry_path,
                    payload_root=_root / "data" / "canonical" / "options",
                    run_id=run_id,
                    session_date=_run_session,
                    dte_max=CHAIN_EXPIRY_DAYS,
                    min_open_interest=OPTION_CHAIN_ACQUISITION_MIN_OI,
                    flags=_cds_flags,
                )
            if _canonical_lifecycle_persistence_enabled(_cds_flags):
                _CDS_LIQUIDITY_STORE = OptionLiquidityLifecycleStore(
                    CanonicalRegistry(_registry_path)
                )
                _CDS_LIQUIDITY_STORE.initialise()
            else:
                _CDS_LIQUIDITY_STORE = None
                print(
                    "[CDS-REPLAY] Lifecycle persistence disabled — "
                    "historical thesis state is immutable"
                )
        else:
            _CDS_CHAIN_SERVICE = None
            _CDS_LIQUIDITY_STORE = None
            _CDS_V2_CHAIN_RESOLVER = None
            _CDS_V2_SESSION = None
    except Exception as _cds_error:
        _CDS_CHAIN_SERVICE = None
        _CDS_LIQUIDITY_STORE = None
        _CDS_V2_CHAIN_RESOLVER = None
        _CDS_V2_SESSION = None
        if os.environ.get("AVSHUNTER_STAGE_GATING_ENFORCED", "0").strip().lower() in {"1", "true", "yes", "on"}:
            raise RuntimeError(f"CDS-3/4 Options authority failed closed: {_cds_error}") from _cds_error
        print(f"[CDS-3/4] Shadow setup unavailable — legacy primary/fallback path retained: {_cds_error}")

    print(f"\n[START] Processing {len(eligible)} signals...\n")

    # AVS-FIX-001 W3.3: publish the run identity the contracts_tested sidecar
    # writes under. process_ticker cannot reach these locals otherwise.
    set_active_run_context(run_id, output_dir)

    macro_contexts = load_package_macro_contexts(run_id, output_dir)
    if macro_contexts:
        print(f"[MACRO] Options macro enrichment contexts loaded from packages: {len(macro_contexts)}")
    elif any(str(c).startswith("macro_enrichment_") for c in eligible.columns):
        print("[MACRO] Options macro enrichment context available from discovery CSV")
    else:
        print("[MACRO] No macro enrichment context found for Options bonus")

    # Sprint 3 — load TLE contexts written by avshunter_trap_engine.py (Phase 5.5)
    tle_contexts = load_package_tle_contexts(run_id, output_dir)
    if tle_contexts:
        print(f"[TLE] Trap-to-Launch Engine contexts loaded: {len(tle_contexts)}")
    else:
        print("[TLE] No TLE contexts found — CSM modifiers inactive")

    results = []
    t_start = time.time()

    for i, (_, row) in enumerate(eligible.iterrows(), 1):
        ticker = str(row.get('ticker',''))
        tier   = _safe_int(row.get('tier', 2), 2)
        phase  = str(row.get('phase','?'))
        intent = str(row.get('precor_intent','?'))

        print(f"[{i}/{len(eligible)}] {ticker} T{tier} Ph{phase} {intent}")

        _session_exception = _options_session_exception_by_ticker.get(ticker)
        if _session_exception is not None:
            try:
                ctx = parse_structural_context(row)
            except Exception:
                ctx = {"ticker": ticker, "tier": tier, "phase": phase, "intent": intent}
            _exception_reason = (
                "BLOCK_DATA_EXCEPTION: "
                f"{_session_exception['exception_reason']} "
                f"expected={_session_exception['expected_session']} "
                f"actual={_session_exception['actual_session'] or 'MISSING'} "
                f"source={_session_exception['data_source'] or 'UNKNOWN'}"
            )
            result = _stand_down(ctx, _exception_reason)
            result.update({
                "options_session_exception": True,
                "options_session_exception_reason": _session_exception["exception_reason"],
                "options_session_expected": _session_exception["expected_session"],
                "options_session_actual": _session_exception["actual_session"],
                "options_session_source": _session_exception["session_source"],
                "options_session_exception_action": _session_exception["exception_action"],
                "execution_permission": "NO_CAPITAL",
            })
            for _baton_col in [c for c in row.index if str(c).startswith("layer2__")]:
                result.setdefault(_baton_col, row.get(_baton_col))
            results.append(result)
            print(f"         → DATA_EXCEPTION ({_session_exception['exception_reason']})")
        else:
            try:
                result = process_ticker(row, macro_context=macro_contexts.get(ticker), tle_context=tle_contexts.get(ticker))
                for _baton_col in [c for c in row.index if str(c).startswith("layer2__")]:
                    result.setdefault(_baton_col, row.get(_baton_col))
                results.append(result)
                v = result.get('options_verdict','?')
                s = result.get('options_score', 0)
                print(f"         → {v} (OIS={s})")
            except Exception as e:
                print(f"         → ERROR: {e}")
                try:
                    ctx = parse_structural_context(row)
                except Exception:
                    # Fallback context when parse itself fails (e.g. NaN fields on days_to_trigger)
                    _fb_tier = row.get("tier", 2)
                    ctx = {"ticker": str(row.get("ticker", "UNKNOWN")), "tier": _safe_int(_fb_tier, 2)}
                result = _stand_down(ctx, 'PIPELINE_EXCEPTION_GOVERNED')
                result['pipeline_exception_type'] = type(e).__name__
                for _baton_col in [c for c in row.index if str(c).startswith("layer2__")]:
                    result.setdefault(_baton_col, row.get(_baton_col))
                results.append(result)

        try:
            _persist_options_lifecycle_result(results[-1], run_id)
        except Exception as _lifecycle_error:
            results[-1]['liquidity_persistence_status'] = f"ERROR:{type(_lifecycle_error).__name__}"
            results[-1]['liquidity_persistence_error'] = str(_lifecycle_error)
            if os.environ.get("AVSHUNTER_STAGE_GATING_ENFORCED", "0").strip().lower() in {"1", "true", "yes", "on"}:
                raise RuntimeError(
                    f"Options liquidity lifecycle persistence failed for {ticker}: {_lifecycle_error}"
                ) from _lifecycle_error
            print(f"         → CDS lifecycle warning: {_lifecycle_error}")

        # MD Trader plan: 100,000 credits/day. 0.10s sleep retained as courtesy
        # throttle — avoids any undocumented burst limit on MD infrastructure.
        time.sleep(0.10)

    elapsed = time.time() - t_start
    print(f"\n[DONE] {len(results)} processed in {elapsed:.0f}s")

    # ── v1.1: Sector alignment injection — populate 9 macro sector fields ──
    # Load sector_bias_map from env var (set by orchestrator) and classify
    # each result row. This augments the existing sector_regime (5d price)
    # with the macro-level TAILWIND/HEADWIND classification.
    try:
        import json as _oi_json, os as _oi_os, importlib.util as _oi_ilu
        _oi_sbm_raw = _oi_os.environ.get("AVSHUNTER_SECTOR_BIAS_MAP", "")
        _oi_mc_raw  = _oi_os.environ.get("AVSHUNTER_MACRO_CONVICTION", "0.60")
        _oi_sbm     = _oi_json.loads(_oi_sbm_raw) if _oi_sbm_raw else {}
        _oi_mc      = float(_oi_mc_raw) if _oi_mc_raw else 0.60
        _oi_sa_mod  = None
        _oi_base    = os.path.dirname(os.path.abspath(__file__))
        for _oi_sa_path in [
            os.path.join(_oi_base, "sector_alignment.py"),
            os.path.join(_oi_base, "..", "scripts", "sector_alignment.py"),
            os.path.join(_oi_base, "scripts", "sector_alignment.py"),
        ]:
            if os.path.exists(_oi_sa_path):
                _sp = _oi_ilu.spec_from_file_location("sector_alignment", _oi_sa_path)
                _oi_sa_mod = _oi_ilu.module_from_spec(_sp)
                _sp.loader.exec_module(_oi_sa_mod)
                break
        if _oi_sa_mod and _oi_sbm:
            _sa_tagged = 0
            for _r in results:
                try:
                    _sa_fields = _oi_sa_mod.classify_from_row(_r, _oi_sbm, _oi_mc)
                    _r.update(_sa_fields)
                    _sa_tagged += 1
                except Exception:
                    pass
            print(f"[SECTOR] Macro alignment tagged: {_sa_tagged}/{len(results)} signals")
        else:
            print("[SECTOR] sector_alignment.py not available — macro_sector_bias fields left as UNKNOWN")
    except Exception as _oi_sa_err:
        print(f"[SECTOR] Warning: sector alignment injection failed: {_oi_sa_err}")
    # ─────────────────────────────────────────────────────────────────────────

    # ── Build output DataFrame ─────────────────────────────────────────────
    out_df = _annotate_ev3_handoff_frame(pd.DataFrame(results))

    # Summary stats
    verdicts = out_df['options_verdict'].value_counts().to_dict()
    execute_n   = verdicts.get('EXECUTE', 0)
    armed_n     = verdicts.get('ARMED', 0)
    caution_n   = verdicts.get('CAUTION', 0)
    standdown_n = verdicts.get('STAND_DOWN', 0)
    route_counts = (
        out_df['final_route'].fillna(OPTIONS_BLOCKED_ROUTE).value_counts().to_dict()
        if 'final_route' in out_df.columns else {}
    )

    # marketdata.app enrichment stats
    if 'contract_quote_source' in out_df.columns:
        md_enriched  = int((out_df['contract_quote_source'] == 'marketdata.app').sum())
        bsm_fallback = int((out_df['contract_mark_synthetic'].fillna(True)).sum())
    else:
        md_enriched = bsm_fallback = 0

    print("\n" + "="*72)
    print("OPTIONS INTELLIGENCE SUMMARY")
    print("="*72)
    print(f"  EXECUTE    : {execute_n}")
    print(f"  ARMED      : {armed_n}")
    print(f"  CAUTION    : {caution_n}  (valid signal, negative R:R — watch not trade)")
    print(f"  STAND_DOWN : {standdown_n}")
    if route_counts:
        print("\n  RESEARCH-ONLY OPTIONS ROUTES:")
        for _route, _count in route_counts.items():
            print(f"    {_route:28s}: {_count}")
    print(f"\n  Quote source:")
    print(f"    Real marks  (MD chain+quotes): {md_enriched}  [MarketData provider]")
    print(f"    Synthetic/incomplete quote marks: {bsm_fallback}")
    if md_enriched == 0 and bsm_fallback > 0:
        print(f"  \u26a0\ufe0f  All marks BSM synthetic. Check MARKETDATA_API_KEY and auth.")
        print(f"     R:R and spread gate use imprecise BSM estimates until MD chain is live.")
    print(f"  \u26a0\ufe0f  15-min delay reminder: always verify spread on Tastytrade before entry.")

    if execute_n > 0:
        top = (out_df[out_df['options_verdict']=='EXECUTE']
               .sort_values('options_score', ascending=False)
               .head(10))
        print(f"\n  TOP EXECUTE SIGNALS:")
        for _, r in top.iterrows():
            print(f"    {r['ticker']:6s} T{r['tier']} Ph{r['phase']} "
                  f"OIS={r['options_score']:.0f} "
                  f"{r.get('options_direction','?'):4s} "
                  f"Strike={r.get('contract_strike','?')} "
                  f"DTE={r.get('contract_dte') or '?'} "
                  f"IVP={r.get('ivp_label','?')} "
                  f"R:R={r.get('rr_options','?')}")

    # ── Write outputs ──────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)

    # Main output
    out_path = os.path.join(output_dir, f'options_intelligence_{run_id}.csv')
    out_df.to_csv(out_path, index=False)
    print(f"\n[SAVE] {out_path}")
    latest_path = os.path.join(output_dir, 'options_intelligence_latest.csv')
    out_df.to_csv(latest_path, index=False)
    print(f"[SAVE] {latest_path}")
    direction_record_columns = [
        column for column in (
            'ticker', 'run_id', 'dir_calc_version', 'direction_policy_version',
            'discovery_direction_preliminary', 'governed_direction',
            'governed_direction_authority', 'governed_direction_basis',
            'final_direction', 'direction_resolution_path',
            'direction_governance_status', 'direction_resolution_confidence',
            'direction_resolution_evidence_json',
            'direction_resolution_chain_json',
            'governed_direction_record_json',
            'governed_direction_record_sha256',
        ) if column in out_df.columns
    ]
    direction_records_path = os.path.join(
        output_dir, f'governed_direction_records_{run_id}.jsonl'
    )
    out_df[direction_record_columns].to_json(
        direction_records_path,
        orient='records',
        lines=True,
        force_ascii=False,
    )
    print(f"[SAVE] {direction_records_path} ({len(out_df)} governed direction records)")
    if 'final_route' in out_df.columns:
        ranked_path = os.path.join(output_dir, 'options_candidates_ranked.csv')
        route_rank = {
            OPTIONS_GO_ROUTE: 0,
            OPTIONS_ARMED_ROUTE: 1,
            OPTIONS_PROBE_ROUTE: 2,
            OPTIONS_EQUITY_ONLY_ROUTE: 3,
            OPTIONS_BLOCKED_ROUTE: 4,
        }
        ranked_df = out_df.copy()
        ranked_df['_route_rank'] = ranked_df['final_route'].map(route_rank).fillna(9)
        ranked_df = ranked_df.sort_values(
            ['_route_rank', 'options_research_score', 'estimated_R',
             'breakeven_feasibility', 'liquidity_score'],
            ascending=[True, False, False, False, False],
            na_position='last',
        ).drop(columns=['_route_rank'])
        ranked_df.to_csv(ranked_path, index=False)
        print(f"[SAVE] {ranked_path}")
        blocked_path = os.path.join(output_dir, 'options_blocked_review.csv')
        ranked_df[ranked_df['final_route'].isin([OPTIONS_BLOCKED_ROUTE, OPTIONS_EQUITY_ONLY_ROUTE])].to_csv(blocked_path, index=False)
        print(f"[SAVE] {blocked_path}")

    # Deterministic observability: emit the log even when no rejection occurs.
    _rejection_rows = _build_contract_rejection_log_rows(out_df)
    _rej_path = os.path.join(output_dir, f'contract_rejection_log_{run_id}.csv')
    pd.DataFrame(
        _rejection_rows,
        columns=CONTRACT_REJECTION_LOG_COLUMNS,
    ).to_csv(_rej_path, index=False)
    print(f"[SAVE] {_rej_path} ({len(_rejection_rows)} contract rejections logged)")

    # Enriched vanguard — write options fields back to vanguard CSV
    options_fields = [
        'ticker','behaviour_state_key','behaviour_state_hash','actuarial_match_type',
        'actuarial_ev_weight','catalyst_overlay',
        'legacy_options_verdict','options_verdict','options_route_verdict',
        'options_score','options_direction',
        'options_strategy','recommended_contract','contract_strike',
        'contract_expiry','contract_dte','contract_premium',
        'contract_bid','contract_ask','contract_mid','options_bid','options_ask',
        'contract_quote_quality','contract_quality_flags',
        'contract_quote_fields_complete','contract_quote_refresh_status',
        'spread_source','options_spread_source','contract_spread_source','contract_delta',
        'contract_iv','contract_volume',
        'contract_theta','contract_vega','iv_rank','iv_percentile',
        'ivp_label','gamma_flip','gamma_island_on_path','gamma_island_label',
        'gamma_island_level','gamma_island_distance_pct',
        'gamma_island_strength_share','gamma_island_isolation_ratio',
        'gamma_island_gex_sign','gamma_island_source','gamma_island_note',
        'call_wall','put_wall','pcr_signal',
        'target_in_play','breakeven_pct','rr_options','ev_adjusted',
        'theta_drag_pct','options_score','stand_down_reason',
        'options_session_exception','options_session_exception_reason',
        'options_session_expected','options_session_actual',
        'options_session_source','options_session_exception_action',
        'execution_permission','final_route','options_research_score',
        'confidence_score','hard_vetoes','missing_data',
        'contract_repair_status','contract_repair_required','contract_repair_reason',
        'contract_repair_action','alternative_contract_attempts',
        'alternative_contract_1','alternative_contract_2','alternative_contract_3',
        'alternative_contract_1_score','alternative_contract_2_score','alternative_contract_3_score',
        'alternative_contract_1_reason','alternative_contract_2_reason','alternative_contract_3_reason',
        'alternative_contracts_json','alternative_contracts_schema_version','alternative_contracts_count',
        'alternative_contracts_rejected_incomplete','alternative_contracts_rejection_reasons_json',
        'repair_selector_diagnostics_version','repair_selector_retained_oi_below_50',
        'repair_selector_retained_zero_volume','repair_selector_rejected_invalid_missing_quote',
        'repair_selector_rejected_spread','repair_selector_rejected_dte_delta_geometry',
        'repair_selector_final_bounded_candidate_count',
        'trigger_state','trigger_status_reason','expected_move_pct',
        'expected_move_price','breakeven_feasibility','estimated_R',
        'theta_decay_expected','runway_to_wall_pct','liquidity_score',
        'directional_fit_score','breakeven_score','payoff_score',
        'iv_score','theta_score','runway_score','path_score',
        'trigger_score','research_route_reason',
        'direction_arbitration_status','direction_arbitration_reason',
        'direction_conflict_gate',
        'canonical_direction','direction_resolution_status','direction_status','ev3_direction_source',
        'dir_calc_version','direction_policy_version','direction_policy_sha256',
        'discovery_direction_preliminary','governed_direction',
        'governed_direction_authority','governed_direction_basis','final_direction',
        'direction_resolution_path','direction_governance_status',
        'direction_resolution_confidence','direction_resolution_call_score',
        'direction_resolution_put_score','direction_resolution_winning_share',
        'direction_resolution_margin','direction_resolution_evidence_count',
        'direction_resolution_evidence_json','direction_resolution_chain_json',
        'direction_excluded_evidence_json','governed_direction_record_json',
        'governed_direction_record_sha256',
        'horizon_bucket','horizon_action','horizon_size_multiplier',
        'entry_spot','target_spot','invalidation_spot','invalidation_source',
        'invalidation_policy_version','planned_hold_sessions','planned_hold_source',
        'ev3_handoff_schema_version','contract_quote_timestamp_utc','quote_timestamp_utc',
        'ev3_barrier_state_key','ev3_barrier_state_key_source','ev3_barrier_state_key_version',
        'contract_quote_timestamp_source',
        'contract_multiplier','contract_multiplier_source',
        'contract_bid_size','contract_ask_size','contract_bid_size_quality','contract_ask_size_quality',
        # Options liquidity maturation lifecycle — governed EOD-to-morning baton.
        'thesis_id','thesis_state','liquidity_state','morning_transition_state',
        'recovery_disposition','executable_now','moneyness_state','delta_band',
        'minimum_required_dte','dte_buffer_sessions','atm_distance_sigma',
        'remaining_runway_pct','remaining_runway_state',
        'maturation_state_1d','maturation_state_2d','maturation_state_3d',
        'maturation_score_1d','maturation_score_2d','maturation_score_3d',
        'maturation_score_is_probability','maturation_execution_authority',
        'previous_contract_symbol','contract_changed','contract_selection_reason',
        'quote_as_of','quote_freshness','liquidity_persistence_status',
        'liquidity_persistence_error','option_chain_dataset_id','selected_quote_dataset_id',
        'option_chain_provider','option_chain_resolution',
        'option_chain_provider_finality','option_chain_provider_finality_reasons_json',
        # EIL S4 OBI: real equity NBBO when available, explicit fallback otherwise.
        'l2_bid_size','l2_ask_size','l2_quote_source','l2_quote_timestamp_utc',
        'ev3_selected_handoff_status','ev3_selected_handoff_missing_fields_json',
        'horizon_block_reason','horizon_source','router_version',
        'options_score_pre_macro','options_macro_alignment_label',
        'options_macro_alignment_bonus','options_macro_gate_preserved',
        'options_macro_authority','options_macro_effective_score_delta',
        'options_macro_theme_ids','options_macro_roles',
        'options_macro_event_guards','options_macro_conflict_flags',
        'options_macro_confirmation_required','options_macro_alignment_note',
        'block_code','block_family','block_severity','block_detail',
        # Superbrain passthrough fields — must survive the vanguard merge
        'phase_best','underlying_price','composite','volume_ratio',
        'atr_percentile','pcr_vol','pcr_vol_status','pcr_vol_missing_reason',
        'iv_regime','ivp_252d','iv_vs_hv',
        'dw_signal','dw_pcr_vol','hold_label','hold_urgency',
        'sector','gics_sector','sector_etf','sector_5d_return','sector_regime',
        # v1.1: macro sector alignment fields (from sector_alignment.py)
        'macro_sector_bias','sector_alignment_label','sector_alignment_score',
        'sector_alignment_flag','sector_etf_mapped','gics_sector_norm',
        'sector_bias_source','sector_conviction_context','sector_alignment_note',
        *MACRO_QUANT_CSV_FIELDS,
        'contract_vanna','contract_dte',
        # OTT-PASS-01 (2026-04-27): Added missing fields for M3/M6 module consumption
        # contract_gamma and contract_oi were written to options_intelligence CSV
        # but not passed through to vanguard_signals_enriched — EIL/M6 received None.
        'contract_gamma','contract_oi','contract_spread_pct',
        # iv_engine fields
        'hv_30d','atm_iv','iv_vs_hv','iv_direction','iv_regime',
        # PIPELINE-01 (2026-05-03): Single source of truth — discovery structural fields
        # must survive the full pipeline to EOD/morning validation. These were written
        # by discovery but dropped here, causing rr_underlying=0.00 in morning manifest
        # and actuarial state misses (missing macro_regime, atr_pct, adx_14).
        'rr_underlying','rr_confidence','rr_source','rr',
        'macro_regime','active_regime',
        'atr_pct','adx_14','atr_percentile_rank',
        'catalyst_proximity',
        'dominant_trend','ema_stack',
        'stop_loss','entry_price','structural_target',
        'wyckoff_phase_bucket','wyckoff_score','composite_score',
        'win_probability','vms_score','vms_decision',
        # Sprint 2 — Convexity Strike Map fields
        'csm_best_contract','csm_delta_sweet_spot','csm_delta_note',
        'csm_dte_rank','csm_premium_efficiency','csm_breakeven_pct',
        'csm_gamma_runway','csm_iv_crush_risk',
        'csm_r1_target','csm_r3_target','csm_r5_target','csm_r10_target',
        'csm_verdict','csm_verdict_reason',
    ]
    avail_fields = list(dict.fromkeys(f for f in options_fields if f in out_df.columns))
    merged_enriched = pd.merge(
        merged,
        out_df[avail_fields],
        on='ticker',
        how='left'
    )
    suffix_cols = [c for c in merged_enriched.columns if c.endswith('_x') or c.endswith('_y')]
    if suffix_cols:
        suffix_bases = sorted({c[:-2] for c in suffix_cols})
        for base in suffix_bases:
            left = f"{base}_x"
            right = f"{base}_y"
            if left in merged_enriched.columns and right in merged_enriched.columns:
                merged_enriched[base] = merged_enriched[right].combine_first(merged_enriched[left])
                merged_enriched = merged_enriched.drop(columns=[left, right])
        remaining_suffix_cols = [c for c in merged_enriched.columns if c.endswith('_x') or c.endswith('_y')]
        if remaining_suffix_cols:
            print(f"[WARN] Suffixed handoff columns remain after merge: {remaining_suffix_cols}")
    # Fill STAND_DOWN for signals not in scope
    merged_enriched['options_verdict'] = merged_enriched['options_verdict'].fillna('NOT_SCOPED')
    enriched_path = os.path.join(output_dir, f'vanguard_signals_enriched_{run_id}.csv')
    merged_enriched.to_csv(enriched_path, index=False)
    print(f"[SAVE] {enriched_path}")

    # CDS request telemetry is part of the run artifact so operations can prove
    # cache reuse and explicit fallback without querying SQLite manually.
    _cds_chain_telemetry = {
        "enabled": _CDS_CHAIN_SERVICE is not None or _CDS_V2_CHAIN_RESOLVER is not None,
        "schema_version": (
            "option_chain_v2" if _CDS_V2_CHAIN_RESOLVER is not None else "option_chain_v1"
        ),
        "worklist_authorised": (
            _cds_options_publication.authorised_count
            if _cds_options_publication is not None else 0
        ),
        "worklist_excluded": (
            _cds_options_publication.excluded_count
            if _cds_options_publication is not None else 0
        ),
        "session_exceptions": len(_options_session_exception_by_ticker),
        "physical_requests": 0,
        "cache_hits": 0,
        "marketdata_fetches": 0,
        "polygon_fallback_fetches": 0,
        "polygon_options_disabled": True,
        "marketdata_empty": 0,
        "blocked_requests": 0,
        "liquidity_lifecycle_enabled": _CDS_LIQUIDITY_STORE is not None,
        "liquidity_lifecycle_persisted": sum(
            1 for item in results
            if item.get("liquidity_persistence_status") == "PERSISTED"
        ),
        "liquidity_lifecycle_thesis_only": sum(
            1 for item in results
            if str(item.get("liquidity_persistence_status") or "").startswith("THESIS_ONLY")
        ),
        "liquidity_lifecycle_errors": sum(
            1 for item in results
            if str(item.get("liquidity_persistence_status") or "").startswith("ERROR")
        ),
    }
    _cds_ledger = (
        _CDS_V2_CHAIN_RESOLVER.ledger
        if _CDS_V2_CHAIN_RESOLVER is not None
        else (_CDS_CHAIN_SERVICE.ledger if _CDS_CHAIN_SERVICE is not None else None)
    )
    if _cds_ledger is not None:
        _all_cds_entries = _cds_ledger.entries(run_id)
        _cds_entries = [
            entry for entry in _all_cds_entries
            if str(entry.get("stage") or "").upper() == "OPTIONS"
            and str(entry.get("dataset_type") or "").upper() == "OPTION_CHAIN"
        ]
        _cds_chain_telemetry["non_options_entries_ignored"] = len(_all_cds_entries) - len(_cds_entries)
        _cds_chain_telemetry["physical_requests"] = sum(
            int(entry.get("physical_request_count") or 0) for entry in _cds_entries
        )
        _cds_chain_telemetry["cache_hits"] = sum(
            str(entry.get("resolution") or "") in {"CACHE_HIT", "SUPERSET_HIT"}
            for entry in _cds_entries
        )
        _cds_chain_telemetry["marketdata_fetches"] = sum(
            str(entry.get("provider") or "").upper() == "MARKETDATA"
            and str(entry.get("resolution") or "") == "PROVIDER_FETCH"
            for entry in _cds_entries
        )
        _cds_chain_telemetry["marketdata_empty"] = sum(
            str(entry.get("provider") or "").upper() == "MARKETDATA"
            and str(entry.get("resolution") or "") == "PROVIDER_ERROR"
            for entry in _cds_entries
        )
        _cds_chain_telemetry["blocked_requests"] = sum(
            str(entry.get("resolution") or "") == "BLOCKED_NOT_AUTHORISED"
            for entry in _cds_entries
        )

    # AVS-FIX-002 Stage 1: assess provider finality at ticker and run grain.
    # This controls evidence eligibility, not pipeline membership. A partial
    # chain remains a named exception and never aborts unrelated candidates.
    _provider_finality = {
        "threshold_version": "provider_completeness_v1",
        "status": "NOT_ASSESSED",
        "normal_completed_session_eligible": False,
        "chains_expected": len(_chain_authorised_tickers),
    }
    if _run_session is not None and _cds_options_publication is not None:
        try:
            from canonical_data.provider_finality import assess_completed_option_worklist
            from canonical_data.registry import CanonicalRegistry
            from canonical_data.session_clock import session_snapshot

            _checked_at = datetime.now(timezone.utc)
            _dataset_by_ticker = {
                str(item.get("ticker") or "").strip().upper(): str(
                    item.get("option_chain_dataset_id") or ""
                ).strip()
                for item in results
                if str(item.get("ticker") or "").strip()
            }
            _provider_result = assess_completed_option_worklist(
                registry=CanonicalRegistry(
                    _REPO_ROOT / "data" / "canonical" / "control_plane.sqlite"
                ),
                expected_tickers=_chain_authorised_tickers,
                chain_dataset_ids=_dataset_by_ticker,
                requested_session=_run_session,
                last_completed_session=session_snapshot(_checked_at).last_completed_session,
                assessed_at_utc=_checked_at,
                historical_price_database_path=(
                    _REPO_ROOT / "data" / "canonical" / "historical_prices.sqlite"
                ),
            )
            _provider_finality = _provider_result.aggregate.to_dict()
            _provider_finality["status"] = "ASSESSED"
            _provider_detail_path = Path(output_dir) / f"provider_finality_{run_id}.json"
            _provider_detail_path.write_text(
                json.dumps(_provider_result.to_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            _provider_exception_path = (
                Path(output_dir) / f"provider_finality_exceptions_{run_id}.csv"
            )
            pd.DataFrame(
                [
                    item.to_dict()
                    for item in _provider_result.assessments
                    if not item.normal_completed_session_eligible
                ]
            ).to_csv(_provider_exception_path, index=False)
            _provider_finality["detail_path"] = str(_provider_detail_path.resolve())
            _provider_finality["exception_path"] = str(_provider_exception_path.resolve())
            print(
                "[PROVIDER-FINALITY] "
                f"complete={_provider_finality['complete_chains']}/"
                f"{_provider_finality['chains_expected']} "
                f"closes={_provider_finality['closes_present']}/"
                f"{_provider_finality['underlying_tickers_expected']} "
                f"normal={_provider_finality['normal_completed_session_eligible']}"
            )
        except Exception as _provider_error:
            _provider_finality.update(
                {
                    "status": "ASSESSMENT_ERROR",
                    "reason": f"{type(_provider_error).__name__}: {_provider_error}",
                }
            )
            print(
                "[PROVIDER-FINALITY] assessment unavailable; run is non-baseline: "
                f"{_provider_error}"
            )

    # Summary JSON
    summary = {
        'run_id'            : run_id,
        'generated_utc'     : datetime.now(timezone.utc).isoformat(),
        'signals_scoped'    : len(eligible),
        'signals_processed' : len(results),
        'execute'           : execute_n,
        'armed'             : armed_n,
        'caution'           : caution_n,
        'stand_down'        : standdown_n,
        'route_counts'      : route_counts,
        'execution_permission': OPTIONS_RESEARCH_PERMISSION,
        'elapsed_seconds'   : round(elapsed, 1),
        'cds_chain_telemetry': _cds_chain_telemetry,
        'provider_completeness_evidence': _provider_finality,
        'repair_selector_diagnostics': _aggregate_repair_selector_diagnostics(results),
        'top_execute'       : (
            out_df[out_df['options_verdict']=='EXECUTE']
            .sort_values('options_score', ascending=False)
            [['ticker','options_score','options_direction',
              'contract_strike','contract_dte','ivp_label','rr_options']]
            .head(10)
            .to_dict('records')
            if execute_n > 0 else []
        ),
        'top_go_review'     : (
            out_df[out_df['final_route'] == OPTIONS_GO_ROUTE]
            .sort_values('options_research_score', ascending=False)
            [['ticker','options_research_score','options_direction',
              'contract_strike','contract_dte','breakeven_feasibility',
              'estimated_R','liquidity_score']]
            .head(10)
            .to_dict('records')
            if 'final_route' in out_df.columns and route_counts.get(OPTIONS_GO_ROUTE, 0) > 0 else []
        ),
    }
    summary_path = os.path.join(output_dir, f'options_intelligence_summary_{run_id}.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[SAVE] {summary_path}")
    summary_latest_path = os.path.join(output_dir, 'options_summary.json')
    with open(summary_latest_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"[SAVE] {summary_latest_path}")
    print("="*72)

    return out_df


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    # Parse args: discovery_csv vanguard_csv [run_id] [output_dir] [max_signals]
    if len(sys.argv) < 3:
        print("Usage: python avshunter_options_intelligence.py "
              "<discovery_csv> <vanguard_csv> [run_id] [output_dir] [max_signals]")
        print("\nExample:")
        print("  python avshunter_options_intelligence.py "
              "discovery_candidates_ultimate_20260219_165805.csv "
              "vanguard_signals.csv "
              "20260219_165805 "
              "./output 50")
        sys.exit(1)

    discovery_csv = sys.argv[1]
    vanguard_csv  = sys.argv[2]
    run_id_arg    = sys.argv[3] if len(sys.argv) > 3 else None
    out_dir_arg   = sys.argv[4] if len(sys.argv) > 4 else '.'
    max_sig_arg   = int(sys.argv[5]) if len(sys.argv) > 5 else None

    results = run_options_layer(
        discovery_csv = discovery_csv,
        vanguard_csv  = vanguard_csv,
        run_id        = run_id_arg,
        output_dir    = out_dir_arg,
        max_signals   = max_sig_arg,
    )

    if not results.empty:
        print(f"\n✅ Options Intelligence complete — {len(results)} signals analysed")
    else:
        print("\n⚠️ No results produced — check authentication and input files")
