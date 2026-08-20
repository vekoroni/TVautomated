"""AVSHUNTER UAT drop-off audit.

Tracks each ticker from package/Vanguard through Options Intelligence, EIL,
execution, EOD slate, and morning validation. The output is intentionally
diagnostic: it tells us where a ticker last survived, why it fell off, and what
to inspect next.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "data" / "output" / "runs"


STAGE_ORDER = {
    "UNIVERSE": 1,
    "SCANNER": 2,
    "DISCOVERY": 3,
    "PACKAGE": 4,
    "VANGUARD_REJECT": 5,
    "VANGUARD": 6,
    "OPTIONS_INTELLIGENCE": 7,
    "EIL": 8,
    "EXECUTION": 9,
    "EOD_CANDIDATE": 10,
    "SHADOW_BOOK": 11,
    "MORNING_VALIDATION": 12,
}


def _s(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _u(value: Any) -> str:
    return _s(value).upper()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _first(row: dict, keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = _s(row.get(key))
        if value:
            return value
    return default


def _read(path: Optional[Path], prefix: str, columns: Optional[list[str]] = None) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame(columns=["ticker"])
    df = pd.read_csv(path, low_memory=False)
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df[df["ticker"] != ""].drop_duplicates("ticker", keep="first")
    if columns:
        keep = ["ticker"] + [c for c in columns if c in df.columns]
        df = df[keep]
    rename = {c: f"{prefix}__{c}" for c in df.columns if c != "ticker"}
    return df.rename(columns=rename)


def _read_package_index(path: Optional[Path]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame(columns=["ticker"])
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return pd.DataFrame(columns=["ticker"])
    rows = []
    for item in data.get("packages", []) or []:
        ticker = _s(item.get("ticker")).upper()
        if not ticker:
            continue
        rows.append(
            {
                "ticker": ticker,
                "pkg__status": _s(item.get("status")),
                "pkg__reason": _s(item.get("reason")),
                "pkg__package_path": _s(item.get("package_path")),
                "pkg__actuarial": _s(item.get("actuarial")),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["ticker"])
    return pd.DataFrame(rows).drop_duplicates("ticker", keep="first")


def _read_universe(path: Optional[Path]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame(columns=["ticker"])
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return pd.DataFrame(columns=["ticker"])
    if "ticker" not in df.columns:
        return pd.DataFrame(columns=["ticker"])
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df[df["ticker"] != ""].drop_duplicates("ticker", keep="first")
    return df[["ticker"]].assign(uni__in_universe=True, uni__source=str(path))


def _read_scanner_context(path: Optional[Path]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame(columns=["ticker"])
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return pd.DataFrame(columns=["ticker"])
    rows = []
    for ticker, block in (data.get("tickers") or {}).items():
        t = _s(ticker).upper()
        if not t:
            continue
        block = block or {}
        rows.append(
            {
                "ticker": t,
                "scan__scanner_source": _s(block.get("scanner_source") or data.get("scanner_source")),
                "scan__scanner_run_id": _s(block.get("scanner_run_id") or data.get("scanner_run_id")),
                "scan__scanner_decision": _s(block.get("scanner_decision")),
                "scan__scanner_score": block.get("scanner_score", ""),
                "scan__scanner_confidence": block.get("scanner_confidence", ""),
                "scan__scanner_data_quality": _s(block.get("scanner_data_quality")),
                "scan__scanner_reason_codes": _s(block.get("scanner_reason_codes")),
                "scan__scanner_pattern_tags": _s(block.get("scanner_pattern_tags")),
                "scan__scanner_watchlist_lane": _s(block.get("scanner_watchlist_lane")),
                "scan__scanner_age_hrs": block.get("scanner_age_hrs", data.get("scanner_age_hrs", "")),
                "scan__vms_score": block.get("vms_score", ""),
                "scan__vms_decision": _s(block.get("vms_decision")),
                "scan__direction": _s(block.get("scanner_direction") or block.get("direction")),
                "scan__direction_reason": _s(block.get("scanner_direction_reason") or block.get("direction_reason")),
                "scan__iv_rank": block.get("iv_rank", ""),
                "scan__vol_spread": block.get("vol_spread", ""),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["ticker"])
    return pd.DataFrame(rows).drop_duplicates("ticker", keep="first")


def _find_one(run_dir: Path, patterns: list[str]) -> Optional[Path]:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(run_dir.glob(pattern))
    candidates = [path for path in candidates if path.exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime)[-1]


def _stage_presence(row: dict) -> tuple[str, str]:
    stages = [
        ("MORNING_VALIDATION", "mv__execution_permission"),
        ("EOD_CANDIDATE", "eod__eod_candidate_status"),
        ("SHADOW_BOOK", "shadow__shadow_opportunity_score"),
        ("EXECUTION", "exe__effective_execution_verdict"),
        ("EIL", "eil__eil_v3_verdict"),
        ("OPTIONS_INTELLIGENCE", "oi__options_verdict"),
        ("VANGUARD", "vg__verdict"),
        ("VANGUARD_REJECT", "vgr__reason_code"),
        ("PACKAGE", "pkg__status"),
        ("DISCOVERY", "disc__tier"),
        ("SCANNER", "scan__scanner_decision"),
        ("UNIVERSE", "uni__in_universe"),
    ]
    for stage, marker in stages:
        if _s(row.get(marker)):
            return stage, marker
    return "NOT_SEEN", ""


def _vanguard_weak_signal_reason(row: dict) -> str:
    edge_quality = _u(row.get("vg__layer2__edge_quality"))
    prob_verdict = _u(row.get("vg__layer2__probability_verdict"))
    prob_edge = _f(row.get("vg__layer2__probability_edge"))
    state_quality = _u(row.get("vg__layer2__state_match_quality"))
    match_method = _u(row.get("vg__layer2__state_match_method"))
    bucket = _u(_first(row, ["vg__layer2__future_momentum_bucket", "vg__layer2__outcomes__future_momentum_bucket"]))
    bucket_conf = _f(_first(row, ["vg__layer2__future_momentum_bucket_confidence", "vg__layer2__outcomes__future_momentum_bucket_confidence"]))
    bucket_n = _f(_first(row, ["vg__layer2__future_momentum_bucket_sample_size", "vg__layer2__outcomes__future_momentum_bucket_sample_size"]))
    ev_20d = _f(_first(row, ["vg__expected_value_20d", "vg__layer2__outcomes__expected_value_20d"]))

    if edge_quality and edge_quality != "WEAK":
        return edge_quality
    if prob_verdict in {"STRONG_EDGE", "MODEST_EDGE"} or prob_edge >= 0.05:
        reasons = [f"{prob_verdict or 'POSITIVE_PROB_EDGE'}:{prob_edge:.4f}"]
        if state_quality:
            reasons.append(f"match={match_method or 'UNKNOWN'}/{state_quality}")
        if bucket:
            reasons.append(f"future_bucket={bucket} conf={bucket_conf:.3f} n={bucket_n:.0f}")
        if bucket in {"HIGH", "EXTREME"} and bucket_conf < 0.60:
            reasons.append("WEAK_LABEL_DUE_TO_DISPERSED_FUTURE_BUCKET")
        if ev_20d < 0.015:
            reasons.append("EV20D_BELOW_LEGACY_MODERATE")
        return ";".join(reasons)
    if not prob_verdict:
        return "NO_PROBABILITY_VERDICT"
    return prob_verdict


def _vanguard_support_override(row: dict) -> bool:
    verdict = _u(row.get("vg__verdict"))
    prob_verdict = _u(row.get("vg__layer2__probability_verdict"))
    edge_quality = _u(row.get("vg__layer2__edge_quality"))
    final_recommendation = _u(row.get("vg__final_recommendation"))
    return (
        verdict in {"TRADE", "ACTUARIAL_SUPPORT", "ACTUARIAL_MODERATE"}
        or prob_verdict == "STRONG_EDGE"
        or edge_quality == "STRONG"
        or "EDGE_STRONG" in final_recommendation
    )


def _expected_options_scope(row: dict) -> str:
    """Mirror Options Intelligence scope so the audit can catch handoff drift."""
    try:
        tier = int(float(_s(row.get("disc__tier"))))
    except Exception:
        tier = 999
    intent = _u(row.get("disc__precor_intent") or row.get("disc__intent"))
    if _vanguard_support_override(row):
        return "EXPECTED_BY_VANGUARD_SUPPORT"
    if tier in {0, 1, 2} and intent != "WAIT":
        return "EXPECTED_BY_TIER_AND_INTENT"
    if tier in {0, 1, 2} and intent == "WAIT":
        return "EXCLUDED_WAIT_NO_SUPPORT"
    if tier == 3:
        return "EXCLUDED_TIER3_NO_SUPPORT"
    return "EXCLUDED_BY_SCOPE_RULES"


def _vanguard_contract_contradiction(row: dict) -> str:
    """Detect rows that say both statistical support and active no-edge."""
    support = _vanguard_support_override(row)
    no_edge = _first(row, ["vg__no_edge_reason", "vg__failed_gate"])
    legacy_note = _first(row, ["vg__legacy_no_edge_reason", "vg__statistical_support_note"])
    if support and no_edge:
        return f"ACTIVE_NO_EDGE_WITH_SUPPORT:{no_edge[:120]}"
    if support and legacy_note:
        return "LEGACY_EV_NOTE_SEPARATED"
    return ""


def _reason(row: dict, available: Optional[dict[str, bool]] = None) -> tuple[str, str, str]:
    available = available or {}
    vgr_reason = _first(row, ["vgr__reason_code", "vgr__reason_codes", "vgr__error"])
    vg_verdict = _s(row.get("vg__verdict"))
    vg_weak = _vanguard_weak_signal_reason(row)
    disc_tier = _s(row.get("disc__tier"))
    scan_decision = _s(row.get("scan__scanner_decision"))

    if not disc_tier and scan_decision:
        return "BETWEEN_SCANNER_AND_DISCOVERY", f"SCANNER_TICKER_NOT_SELECTED_BY_DISCOVERY;decision={scan_decision}", "Review discovery selection threshold for scanner-fed tickers"
    if not disc_tier and _s(row.get("uni__in_universe")):
        return "BETWEEN_UNIVERSE_AND_DISCOVERY", "UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY", "Normal funnel drop-off unless ticker should have been catalyst/scanner boosted"
    if disc_tier and not _s(row.get("pkg__status")):
        if not available.get("pkg", False):
            return "PENDING_PACKAGE_BUILD", "PACKAGE_INDEX_NOT_YET_AVAILABLE", "Await package build checkpoint"
        return "BETWEEN_DISCOVERY_AND_PACKAGE", "DISCOVERY_CANDIDATE_NOT_PACKAGED", "Check package builder input and ticker normalization"

    if not vg_verdict and not vgr_reason and _s(row.get("pkg__status")):
        return "BETWEEN_PACKAGE_AND_VANGUARD", "PACKAGE_BUILT_BUT_NO_VANGUARD_PASS_OR_REJECT", "Check Vanguard runner accounting"
    if vgr_reason:
        return "VANGUARD", vgr_reason, "Fix package data contract / OHLCV before options layer"

    oi_score = _f(row.get("oi__options_score"))
    oi_contract = _first(row, ["oi__recommended_contract", "oi__contract_occ_symbol"])
    oi_verdict = _u(row.get("oi__options_verdict"))
    oi_block = _first(row, ["oi__stand_down_reason", "oi__block_detail", "oi__block_code"])

    eil_verdict = _u(row.get("eil__eil_v3_verdict"))
    eil_raw = _u(row.get("eil__eil_raw_verdict"))
    pse_mode = _u(row.get("eil__pse_execution_mode"))
    pse_reason = _first(row, ["eil__pse_block_reason", "eil__execution_authority_reason", "eil__signal_authority_reason"])

    exe_verdict = _u(row.get("exe__effective_execution_verdict"))
    exe_capital = _u(row.get("exe__capital_permission"))
    exe_size = _f(_first(row, ["exe__final_size", "exe__position_size", "exe__size"]))

    eod_status = _u(row.get("eod__eod_candidate_status"))
    eod_reason = _first(row, ["eod__eod_dropoff_reason", "eod__eod_candidate_reason", "eod__contract_repair_reason"])
    shadow_score = _f(row.get("shadow__shadow_opportunity_score"))
    shadow_label = _u(row.get("shadow__shadow_opportunity_label"))
    shadow_reason = _first(row, ["shadow__shadow_opportunity_reason", "shadow__eod_dropoff_reason"])

    mv_perm = _u(row.get("mv__execution_permission"))
    mv_state = _u(row.get("mv__live_validation_state"))
    mv_reason = _first(row, ["mv__rejection_reason", "mv__wait_reason", "mv__upgrade_downgrade_reason"])

    if not _s(row.get("oi__options_verdict")):
        if vg_verdict:
            if not available.get("oi", False):
                return "PENDING_OPTIONS_INTELLIGENCE", f"OPTIONS_OUTPUT_NOT_YET_AVAILABLE;{vg_weak}", "Await Options Intelligence checkpoint"
            return "BETWEEN_VANGUARD_AND_OPTIONS", f"NO_OPTIONS_INTELLIGENCE_ROW;{vg_weak}", "Check Vanguard-to-options handoff and option scanner coverage"
        return "BEFORE_OPTIONS_INTELLIGENCE", "NO_OPTIONS_INTELLIGENCE_ROW", "Check discovery-to-options handoff"
    if oi_score <= 0:
        return "OPTIONS_INTELLIGENCE", oi_block or "OPTIONS_SCORE_ZERO_OR_NO_CONTRACT", "Check option scanner coverage and contract selection"
    if not oi_contract:
        return "OPTIONS_INTELLIGENCE", oi_block or "NO_RECOMMENDED_CONTRACT", "Repair contract selection before EIL"
    if oi_verdict in {"BLOCK", "BLOCKED", "REJECT", "REJECTED"}:
        return "OPTIONS_INTELLIGENCE", oi_block or oi_verdict, "Review OI hard gate"

    if not _s(row.get("eil__eil_v3_verdict")):
        if not available.get("eil", False):
            return "PENDING_EIL", "EIL_OUTPUT_NOT_YET_AVAILABLE", "Await EIL/SuperBrain checkpoint"
        return "BETWEEN_OI_AND_EIL", "OI_SURVIVED_BUT_EIL_ROW_MISSING", "Check EIL merge/index key"
    if eil_verdict == "BLOCKED" and not eod_status:
        return "EIL", pse_reason or f"EIL_{eil_verdict or eil_raw}", "Review EIL block reason and whether it is true live-capital only"

    if _s(row.get("exe__effective_execution_verdict")):
        no_capital = exe_capital in {"NO", "NONE", "FALSE", "0"} or exe_size == 0
        if no_capital and not eod_status:
            return "EXECUTION", "ZERO_CAPITAL_PERMISSION_AFTER_EXECUTION_GATE", "Split EOD thesis from live capital authority"
        if "FATAL" in exe_verdict and not eod_status:
            return "EXECUTION", exe_verdict, "Review hard-veto contract"

    if not eod_status:
        if shadow_score > 0 or shadow_label:
            return (
                "SHADOW_BOOK",
                f"{shadow_label or 'MISSED_OPPORTUNITY_SHADOW'};score={shadow_score:.0f};{shadow_reason}",
                "Review false-negative risk, direction repair, contract repair, and tier floor before next UAT",
            )
        if not available.get("eod", False):
            return "PENDING_EOD_CANDIDATE", "EOD_CANDIDATE_OUTPUT_NOT_YET_AVAILABLE", "Await EOD candidate manifest"
        return "BETWEEN_EIL_AND_EOD", "NO_EOD_CANDIDATE_ROW", "Check EOD quality floor and merge fields"
    if eod_status in {"EOD_BLOCK", "EOD_WATCH"}:
        return "EOD_CANDIDATE", eod_reason or eod_status, "Review EOD tier and drop-off reason"
    if eod_status == "EOD_CONTRACT_REPAIR_REQUIRED":
        return "EOD_CANDIDATE", eod_reason or "CONTRACT_REPAIR_REQUIRED", "Find better liquid contract; thesis may still be valid"

    if not mv_perm:
        return "AFTER_EOD_BEFORE_MORNING", eod_status, "Await morning validation or run morning_thesis_validator"
    if mv_perm == "GO":
        return "SURVIVED", "GO", "Ready subject to operator controls"
    if mv_perm == "ARMED":
        return "MORNING_VALIDATION", mv_reason or "ARMED_WAITING_FOR_RETEST", "Wait for live confirmation/retest"
    if mv_perm == "WAIT":
        return "MORNING_VALIDATION", mv_reason or "WAIT", "Review live confirmation gap"
    if mv_perm == "BLOCKED":
        return "MORNING_VALIDATION", mv_reason or mv_state or "BLOCKED", "Review live veto"
    return "UNKNOWN", "UNCLASSIFIED", "Inspect row manually"


def _audit_classification(row: dict, dropoff_stage: str, dropoff_reason: str) -> dict[str, str]:
    """Classify each row into a fixable audit layer with compact evidence."""
    stage = _u(dropoff_stage)
    reason = _u(dropoff_reason)
    scanner_decision = _u(row.get("scan__scanner_decision"))
    scanner_score = _f(row.get("scan__scanner_score"))
    disc_tier = _s(row.get("disc__tier"))
    disc_stale = _u(row.get("disc__is_stale"))
    disc_macro_quality = _u(row.get("disc__macro_data_quality"))
    vg_prob_verdict = _u(row.get("vg__layer2__probability_verdict"))
    vg_prob_edge = _f(row.get("vg__layer2__probability_edge"))
    vg_edge_quality = _u(row.get("vg__layer2__edge_quality"))
    vg_match_quality = _u(row.get("vg__layer2__state_match_quality"))
    vg_support_override = _vanguard_support_override(row)
    vg_expected_scope = _expected_options_scope(row)
    vg_contract_contradiction = _vanguard_contract_contradiction(row)
    oi_score = _f(row.get("oi__options_score"))
    oi_spread = _f(row.get("oi__contract_spread_pct"))
    oi_oi = _f(row.get("oi__contract_oi"))
    oi_volume = _f(row.get("oi__contract_volume"))
    catalyst_detected = _u(_first(row, ["eod__catalyst_detected", "shadow__catalyst_detected", "mv__catalyst_detected", "eil__catalyst_detected", "disc__catalyst_detected"]))
    catalyst_truth = _f(_first(row, ["eod__catalyst_truth_score", "shadow__catalyst_truth_score", "mv__catalyst_truth_score", "eil__catalyst_truth_score", "disc__catalyst_truth_score"]))
    shadow_score = _f(row.get("shadow__shadow_opportunity_score"))
    shadow_label = _u(row.get("shadow__shadow_opportunity_label"))

    flags: list[str] = []
    if scanner_decision == "GO":
        flags.append("SCANNER_GO")
    elif scanner_decision == "PROBE":
        flags.append("SCANNER_PROBE")
    if disc_stale in {"TRUE", "1", "YES"}:
        flags.append("DISCOVERY_STALE")
    if disc_macro_quality and disc_macro_quality not in {"GOOD", "FULL", "CONFIRMED"}:
        flags.append(f"MACRO_{disc_macro_quality}")
    if vg_prob_verdict in {"STRONG_EDGE", "MODEST_EDGE"} or vg_prob_edge >= 0.05:
        flags.append(f"VANGUARD_{vg_prob_verdict or 'POSITIVE_EDGE'}")
    if vg_support_override:
        flags.append("VANGUARD_SUPPORT_OVERRIDE")
    if vg_expected_scope.startswith("EXPECTED"):
        flags.append(vg_expected_scope)
    if vg_contract_contradiction:
        flags.append("VANGUARD_CONTRACT_CONTRADICTION")
    if vg_edge_quality == "WEAK" and (vg_prob_verdict == "STRONG_EDGE" or vg_prob_edge >= 0.10):
        flags.append("WEAK_LABEL_CONTRADICTS_STRONG_PROB_EDGE")
    if catalyst_detected in {"TRUE", "1", "YES"} or catalyst_truth > 0:
        flags.append("CATALYST_PRESENT")
    else:
        flags.append("NO_CATALYST")
    if oi_score <= 0 and "OPTIONS" in stage:
        flags.append("OI_SCORE_ZERO")
    if oi_spread >= 20:
        flags.append("WIDE_SPREAD")
    if 0 < oi_oi < 100:
        flags.append("LOW_OI")
    if 0 <= oi_volume < 10 and oi_score > 0:
        flags.append("LOW_VOLUME")
    if shadow_label:
        flags.append(f"SHADOW_{shadow_label}")
    if shadow_score >= 70:
        flags.append("HIGH_FALSE_NEGATIVE_RISK")

    layer = "UNKNOWN"
    root = "UNCLASSIFIED"
    severity = "P3"
    behavior = "NEEDS_REVIEW"
    impact = "UNKNOWN"

    if stage.startswith("PENDING"):
        layer, root, severity, behavior, impact = "PIPELINE_PROGRESS", "DOWNSTREAM_PHASE_PENDING", "INFO", "PENDING", "NO_DEFECT_YET"
    elif stage == "SHADOW_BOOK":
        if shadow_score >= 70:
            layer, root, severity, behavior, impact = "FALSE_NEGATIVE_AUDIT", "HIGH_FALSE_NEGATIVE_RISK", "P1", "MISSED_MONETISATION_REVIEW", "POTENTIAL_TRADABLE_THESIS_EXCLUDED_FROM_PRIMARY_SLATE"
        elif shadow_score >= 50:
            layer, root, severity, behavior, impact = "FALSE_NEGATIVE_AUDIT", "REVIEW_FALSE_NEGATIVE", "P2", "MISSED_MONETISATION_REVIEW", "POTENTIAL_REPAIRABLE_THESIS_EXCLUDED_FROM_PRIMARY_SLATE"
        else:
            layer, root, severity, behavior, impact = "FALSE_NEGATIVE_AUDIT", shadow_label or "SHADOW_OPPORTUNITY", "P3", "WATCH_FOR_REGIME_FLIP", "WATCHLIST_DIAGNOSTIC"
    elif stage == "BETWEEN_UNIVERSE_AND_DISCOVERY":
        layer, root, severity, behavior, impact = "ALGO_SELECTION", "DISCOVERY_SELECTION_FILTER", "INFO", "EXPECTED_FUNNEL", "NORMAL_UNIVERSE_REDUCTION"
    elif stage == "BETWEEN_SCANNER_AND_DISCOVERY":
        layer, root = "HANDOFF_LOGIC", "SCANNER_DISCOVERY_DISCONNECT"
        severity = "P1" if scanner_decision == "GO" else "P2"
        behavior = "POTENTIAL_DEFECT"
        impact = "MAY_HIDE_SCANNER_CONFIRMED_TRADE"
    elif stage == "BETWEEN_DISCOVERY_AND_PACKAGE":
        layer, root, severity, behavior, impact = "HANDOFF", "DISCOVERY_PACKAGE_HANDOFF_GAP", "P1", "POTENTIAL_DEFECT", "CANDIDATE_DROPPED_BEFORE_MODEL"
    elif stage == "BETWEEN_PACKAGE_AND_VANGUARD":
        layer, root, severity, behavior, impact = "HANDOFF", "PACKAGE_VANGUARD_ACCOUNTING_GAP", "P1", "POTENTIAL_DEFECT", "MODEL_OUTPUT_MISSING"
    elif stage == "VANGUARD":
        layer, root, severity, behavior, impact = "DATA_INPUT", "VANGUARD_INPUT_DATA_REJECT", "P2", "DATA_DEFECT", "TICKER_CANNOT_REACH_OPTIONS"
    elif stage == "BETWEEN_VANGUARD_AND_OPTIONS":
        if "STRONG_EDGE" in reason or vg_prob_edge >= 0.10 or vg_expected_scope.startswith("EXPECTED"):
            layer, root, severity, behavior, impact = "HANDOFF_OR_COVERAGE", "STRONG_VANGUARD_EDGE_MISSED_BY_OPTIONS", "P1", "POTENTIAL_DEFECT", "MAY_HIDE_TRADE"
        elif "NEGATIVE_EDGE" in reason:
            layer, root, severity, behavior, impact = "MODEL_SCORING", "NEGATIVE_ACTUARIAL_EDGE", "INFO", "EXPECTED_FUNNEL", "LOW_OPPORTUNITY_COST"
        elif "WEAK_EDGE" in reason:
            layer, root, severity, behavior, impact = "MODEL_SCORING", "WEAK_ACTUARIAL_EDGE", "P3", "EXPECTED_OR_REVIEW", "LOW_PRIORITY_REVIEW"
        else:
            layer, root, severity, behavior, impact = "HANDOFF_OR_COVERAGE", "VANGUARD_OPTIONS_MISS", "P2", "NEEDS_REVIEW", "POSSIBLE_COVERAGE_GAP"
    elif stage == "OPTIONS_INTELLIGENCE":
        if "NO CONTRACT" in reason or "CHAIN" in reason or "QUALITY GATES" in reason:
            layer, root, severity, behavior, impact = "OPTIONS_CONTRACT", "NO_USABLE_OPTIONS_CONTRACT", "P2", "MARKET_OR_SCANNER_DATA", "THESIS_MAY_NEED_CONTRACT_REPAIR"
        elif "LOW OIS" in reason or "WIDE" in reason or "SPREAD" in reason:
            layer, root, severity, behavior, impact = "OPTIONS_CONTRACT", "LIQUIDITY_OR_SPREAD_BLOCK", "P2", "MARKET_MICROSTRUCTURE", "REPAIR_OR_REROUTE_CONTRACT"
        else:
            layer, root, severity, behavior, impact = "OPTIONS_LOGIC", "OPTIONS_GATE_BLOCK", "P2", "NEEDS_REVIEW", "MAY_BE_OVERSTRICT"
    elif stage == "BETWEEN_OI_AND_EIL":
        layer, root, severity, behavior, impact = "HANDOFF", "OPTIONS_EIL_MERGE_GAP", "P0", "DEFECT", "EXECUTION_LAYER_BLIND_TO_OPTION_SIGNAL"
    elif stage == "EIL":
        layer, root, severity, behavior, impact = "GATE_LOGIC", "EIL_BLOCK_OR_AUTHORITY_GATE", "P1", "NEEDS_REVIEW", "MAY_BE_OVERSTRICT"
    elif stage == "EXECUTION":
        layer, root, severity, behavior, impact = "CAPITAL_LOGIC", "CAPITAL_PERMISSION_OR_SIZE_GATE", "P1", "NEEDS_REVIEW", "MAY_BLOCK_EOD_MONETISATION"
    elif stage == "BETWEEN_EIL_AND_EOD":
        layer, root, severity, behavior, impact = "HANDOFF", "EIL_EOD_CANDIDATE_GAP", "P0", "DEFECT", "EOD_SLATE_MISSING_THESIS"
    elif stage == "EOD_CANDIDATE":
        layer, root, severity, behavior, impact = "EOD_LOGIC", "EOD_TIER_OR_CONTRACT_GATE", "P1", "NEEDS_REVIEW", "CANDIDATE_SLATE_TOO_STRICT"
    elif stage == "MORNING_VALIDATION":
        layer, root, severity, behavior, impact = "LIVE_VALIDATION", "MORNING_CONFIRMATION_GATE", "P2", "EXPECTED_LIVE_GATE", "THESIS_NEEDS_LIVE_CONFIRMATION"
    elif stage == "SURVIVED":
        layer, root, severity, behavior, impact = "SURVIVED", "SURVIVED_PIPELINE", "INFO", "SURVIVED", "ACTIONABLE"

    evidence = (
        f"scanner={scanner_decision or '-'}:{scanner_score:.0f}; "
        f"disc_tier={disc_tier or '-'}; "
        f"vg={vg_edge_quality or '-'}:{vg_prob_verdict or '-'}:{vg_prob_edge:.4f}:{vg_match_quality or '-'}; "
        f"vg_scope={vg_expected_scope}; "
        f"oi_score={oi_score:.1f},spread={oi_spread:.1f},oi={oi_oi:.0f},vol={oi_volume:.0f}; "
        f"catalyst={catalyst_detected or '-'}:{catalyst_truth:.2f}"
    )

    return {
        "audit_layer": layer,
        "root_cause_family": root,
        "audit_severity": severity,
        "audit_behavior": behavior,
        "business_impact": impact,
        "audit_flags": ";".join(flags),
        "evidence_snapshot": evidence,
    }


def build_dropoff_audit(run_id: str, *, runs_dir: Path = RUNS_DIR, output_path: Optional[Path] = None) -> pd.DataFrame:
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run folder not found: {run_dir}")

    paths = {
        "uni": _find_one(run_dir, [f"universe/scanner_augmented_universe_{run_id}.csv", "universe/scanner_augmented_universe_*.csv"])
        or ROOT / "data" / "universe" / "polygon_liquid_universe.csv",
        "scan": _find_one(run_dir, [f"scanner_context_{run_id}.json", "scanner_context_*.json"]),
        "disc": _find_one(run_dir, [f"discovery/discovery_candidates_ultimate_{run_id}.csv", "discovery/discovery_candidates_*.csv"])
        or _find_one(ROOT / "data" / "output", [f"discovery_candidates_ultimate_{run_id}.csv"]),
        "pkg": _find_one(run_dir, ["packages/index.json"]),
        "vg": _find_one(run_dir, [f"vanguard/vanguard_signals_{run_id}.csv", "vanguard/vanguard_signals.csv", "vanguard/vanguard_signals_*.csv"]),
        "vgr": _find_one(run_dir, [f"vanguard/vanguard_rejects_{run_id}.csv", "vanguard/vanguard_rejects.csv", "vanguard/vanguard_rejects_*.csv"]),
        "oi": _find_one(run_dir, [f"options/options_intelligence_{run_id}.csv", "options/options_intelligence_*.csv"]),
        "eil": _find_one(run_dir, [f"superbrain/eil_enriched_{run_id}.csv", "superbrain/eil_enriched_*.csv"]),
        "exe": _find_one(run_dir, [f"execution/execution_v3_5_{run_id}.csv", "execution/execution_*.csv"]),
        "eod": _find_one(run_dir, [f"morning_validation/morning_candidates_{run_id}.csv", "morning_validation/morning_candidates_*.csv"]),
        "shadow": _find_one(run_dir, [f"morning_validation/missed_opportunity_shadow_book_{run_id}.csv", "morning_validation/missed_opportunity_shadow_book_*.csv"]),
        "mv": _find_one(run_dir, [f"morning_validation/morning_validated_trades_{run_id}.csv", "morning_validation/morning_validated_trades_*.csv"]),
    }
    available = {key: bool(path and path.exists()) for key, path in paths.items()}

    discovery_cols = [
        "tier", "tier_label", "candidate_lane", "precor_intent", "intent", "direction", "fusion_direction",
        "composite_score", "composite_adjusted", "win_probability", "rr", "rr_underlying",
        "data_source", "is_stale", "bar_data_asof", "macro_freshness_status",
        "macro_data_quality", "macro_execution_caution", "vms_score", "vms_decision",
        "scanner_source", "scanner_run_id", "scanner_decision", "scanner_score",
        "scanner_data_quality", "asymmetry_pass", "asymmetry_R", "catalyst_detected",
        "catalyst_type", "catalyst_date", "catalyst_truth_score", "catalyst_data_quality",
        "catalyst_trade_class", "catalyst_reason_codes",
    ]

    vanguard_cols = [
        "verdict", "final_recommendation", "has_edge", "edge_direction", "failed_gate", "no_edge_reason",
        "edge_gate_has_edge", "legacy_failed_gate", "legacy_no_edge_reason", "statistical_support_note",
        "layer2__edge_quality", "layer2__probability_verdict", "layer2__probability_edge",
        "layer2__state_match_method", "layer2__state_match_stage", "layer2__state_match_quality",
        "layer2__sample_size", "layer2__sample_confidence_bucket", "layer2__future_momentum_bucket",
        "layer2__future_momentum_bucket_confidence", "layer2__future_momentum_bucket_sample_size",
        "layer2__outcomes__future_momentum_bucket", "layer2__outcomes__future_momentum_bucket_confidence",
        "layer2__outcomes__future_momentum_bucket_sample_size", "layer2__outcomes__expected_value_20d",
        "expected_value_20d", "win_rate_20d", "physics_data_quality", "macro_data_quality",
        "scanner_data_quality", "vms_decision", "handoff_integrity_status",
    ]
    vanguard_reject_cols = ["reason_code", "reason_codes", "error", "exception_type", "diagnostics", "package_path"]

    oi_cols = [
        "options_verdict", "options_score", "stand_down_reason", "block_code", "block_detail",
        "options_direction", "recommended_contract", "contract_occ_symbol", "contract_spread_pct",
        "contract_oi", "contract_volume", "contract_delta", "rr_options", "rr_premium_expected",
        "option_gain_at_target", "convexity_score", "composite", "trigger_quality",
    ]
    eil_cols = [
        "eil_v3_verdict", "eil_raw_verdict", "pse_execution_mode", "pse_block_reason",
        "effective_execution_verdict", "execution_authority_reason", "signal_authority_reason",
        "capital_permission", "eil_composite_score", "pse_edge_score", "trigger_quality",
        "trigger_go_eligible", "catalyst_trade_class", "catalyst_data_quality",
        "catalyst_detected", "catalyst_type", "catalyst_date", "catalyst_truth_score",
        "catalyst_binary_score", "catalyst_direction_bias", "catalyst_event_status",
        "catalyst_source_tier", "catalyst_source_url", "catalyst_ticker_role",
        "catalyst_expected_impact", "catalyst_failure_risk",
    ]
    exe_cols = [
        "effective_execution_verdict", "execution_verdict", "capital_permission", "final_size",
        "position_size", "size", "candidate_size", "eod_candidate_size", "pse_pre_horizon_size",
        "eod_candidate_permission", "eod_candidate_authorized", "sizing_policy",
        "execution_authority_reason", "signal_authority_reason", "pse_execution_mode", "fd_verdict",
    ]
    eod_cols = [
        "structural_tier", "eod_candidate_status", "eod_candidate_reason", "eod_dropoff_reason",
        "slate_rank", "candidate_status", "eod_candidate_permission", "candidate_size",
        "eod_candidate_size", "pse_pre_horizon_size", "sizing_policy", "horizon_bucket",
        "expected_move_window", "expected_holding_days",
        "monetisation_fit_score", "monetisation_fit_label", "direction", "primary_direction",
        "direction_reroute_status", "direction_decision_reason", "selected_contract_side",
        "direction_call_score", "direction_put_score", "contract_repair_status",
        "contract_repair_required", "contract_repair_reason", "contract_quality_score",
        "contract_spread_pct_eod", "contract_oi", "contract_volume", "contract_delta",
        "options_score", "rr", "scs_score", "eil_v3_verdict", "trigger_quality",
        "trigger_go_eligible", "catalyst_detected", "catalyst_type", "catalyst_date",
        "catalyst_truth_score", "catalyst_binary_score", "catalyst_direction_bias",
        "catalyst_trade_class", "catalyst_data_quality", "catalyst_event_status",
        "catalyst_source_tier", "catalyst_source_url", "catalyst_ticker_role",
        "catalyst_expected_impact", "catalyst_failure_risk",
    ]
    shadow_cols = [
        "shadow_opportunity_score", "shadow_opportunity_label", "shadow_opportunity_reason",
        "slate_rank", "structural_tier", "eod_candidate_status", "eod_candidate_reason",
        "eod_dropoff_reason", "monetisation_fit_score", "monetisation_fit_label",
        "direction", "primary_direction", "selected_contract_side", "direction_reroute_status",
        "direction_decision_reason", "contract_repair_status", "contract_repair_required",
        "contract_repair_reason", "contract_quality_score", "contract_spread_pct_eod",
        "contract_oi", "contract_volume", "options_score", "rr", "scs_score",
        "eil_v3_verdict", "trigger_quality", "trigger_go_eligible",
        "horizon_bucket", "expected_move_window", "expected_holding_days",
        "catalyst_detected", "catalyst_type", "catalyst_date", "catalyst_truth_score",
        "catalyst_trade_class", "catalyst_data_quality",
    ]
    mv_cols = [
        "execution_permission", "live_validation_state", "validation_score", "validation_confidence",
        "rejection_reason", "wait_reason", "upgrade_downgrade_reason", "contract_liquidity_confirmed",
        "spread_confirmed", "breakeven_confirmed", "direction_confirmed", "eod_candidate_status",
        "eod_dropoff_reason", "monetisation_fit_score", "monetisation_fit_label",
        "direction_reroute_status", "selected_contract_side", "contract_repair_status",
        "contract_repair_required", "contract_repair_reason", "catalyst_detected",
        "catalyst_type", "catalyst_date", "catalyst_truth_score", "catalyst_event_status",
        "catalyst_source_tier", "catalyst_source_url",
    ]

    frames = [
        _read_universe(paths["uni"]),
        _read_scanner_context(paths["scan"]),
        _read(paths["disc"], "disc", discovery_cols),
        _read_package_index(paths["pkg"]),
        _read(paths["vg"], "vg", vanguard_cols),
        _read(paths["vgr"], "vgr", vanguard_reject_cols),
        _read(paths["oi"], "oi", oi_cols),
        _read(paths["eil"], "eil", eil_cols),
        _read(paths["exe"], "exe", exe_cols),
        _read(paths["eod"], "eod", eod_cols),
        _read(paths["shadow"], "shadow", shadow_cols),
        _read(paths["mv"], "mv", mv_cols),
    ]
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="ticker", how="outer")

    records = []
    for row in merged.fillna("").to_dict(orient="records"):
        last_stage, _ = _stage_presence(row)
        dropoff_stage, dropoff_reason, next_step = _reason(row, available)
        classification = _audit_classification(row, dropoff_stage, dropoff_reason)
        records.append(
            {
                "run_id": run_id,
                "ticker": row.get("ticker", ""),
                "last_stage_reached": last_stage,
                "dropoff_stage": dropoff_stage,
                "dropoff_reason": dropoff_reason,
                **classification,
                "next_review_action": next_step,
                "universe_source": row.get("uni__source", ""),
                "scanner_decision": row.get("scan__scanner_decision", ""),
                "scanner_score": row.get("scan__scanner_score", ""),
                "scanner_confidence": row.get("scan__scanner_confidence", ""),
                "scanner_data_quality": row.get("scan__scanner_data_quality", ""),
                "scanner_reason_codes": row.get("scan__scanner_reason_codes", ""),
                "scanner_direction": row.get("scan__direction", ""),
                "scanner_direction_reason": row.get("scan__direction_reason", ""),
                "scanner_iv_rank": row.get("scan__iv_rank", ""),
                "scanner_vol_spread": row.get("scan__vol_spread", ""),
                "discovery_tier": row.get("disc__tier", ""),
                "discovery_tier_label": row.get("disc__tier_label", ""),
                "discovery_lane": row.get("disc__candidate_lane", ""),
                "discovery_intent": _first(row, ["disc__precor_intent", "disc__intent"]),
                "discovery_direction": row.get("disc__direction", ""),
                "discovery_composite_score": row.get("disc__composite_score", ""),
                "discovery_composite_adjusted": row.get("disc__composite_adjusted", ""),
                "discovery_win_probability": row.get("disc__win_probability", ""),
                "discovery_rr": _first(row, ["disc__rr", "disc__rr_underlying"]),
                "discovery_data_source": row.get("disc__data_source", ""),
                "discovery_is_stale": row.get("disc__is_stale", ""),
                "discovery_macro_quality": row.get("disc__macro_data_quality", ""),
                "discovery_macro_caution": row.get("disc__macro_execution_caution", ""),
                "discovery_catalyst_detected": row.get("disc__catalyst_detected", ""),
                "discovery_catalyst_type": row.get("disc__catalyst_type", ""),
                "discovery_catalyst_date": row.get("disc__catalyst_date", ""),
                "discovery_catalyst_truth_score": row.get("disc__catalyst_truth_score", ""),
                "discovery_catalyst_data_quality": row.get("disc__catalyst_data_quality", ""),
                "discovery_catalyst_trade_class": row.get("disc__catalyst_trade_class", ""),
                "discovery_catalyst_reason_codes": row.get("disc__catalyst_reason_codes", ""),
                "package_status": row.get("pkg__status", ""),
                "package_reason": row.get("pkg__reason", ""),
                "vanguard_verdict": row.get("vg__verdict", ""),
                "vanguard_reject_reason": _first(row, ["vgr__reason_code", "vgr__reason_codes", "vgr__error"]),
                "vanguard_has_edge": row.get("vg__has_edge", ""),
                "vanguard_edge_direction": row.get("vg__edge_direction", ""),
                "vanguard_edge_quality": row.get("vg__layer2__edge_quality", ""),
                "vanguard_probability_verdict": row.get("vg__layer2__probability_verdict", ""),
                "vanguard_probability_edge": row.get("vg__layer2__probability_edge", ""),
                "vanguard_support_override": _vanguard_support_override(row),
                "vanguard_expected_options_scope": _expected_options_scope(row),
                "vanguard_contract_contradiction": _vanguard_contract_contradiction(row),
                "vanguard_legacy_no_edge_reason": row.get("vg__legacy_no_edge_reason", ""),
                "vanguard_statistical_support_note": row.get("vg__statistical_support_note", ""),
                "vanguard_state_match_method": row.get("vg__layer2__state_match_method", ""),
                "vanguard_state_match_quality": row.get("vg__layer2__state_match_quality", ""),
                "vanguard_sample_size": row.get("vg__layer2__sample_size", ""),
                "vanguard_future_momentum_bucket": _first(row, ["vg__layer2__future_momentum_bucket", "vg__layer2__outcomes__future_momentum_bucket"]),
                "vanguard_future_bucket_confidence": _first(row, ["vg__layer2__future_momentum_bucket_confidence", "vg__layer2__outcomes__future_momentum_bucket_confidence"]),
                "vanguard_weak_signal_reason": _vanguard_weak_signal_reason(row),
                "vanguard_physics_quality": row.get("vg__physics_data_quality", ""),
                "vanguard_macro_quality": row.get("vg__macro_data_quality", ""),
                "vanguard_scanner_quality": row.get("vg__scanner_data_quality", ""),
                "vanguard_vms_decision": row.get("vg__vms_decision", ""),
                "oi_verdict": row.get("oi__options_verdict", ""),
                "oi_options_score": row.get("oi__options_score", ""),
                "oi_direction": row.get("oi__options_direction", ""),
                "oi_contract": _first(row, ["oi__recommended_contract", "oi__contract_occ_symbol"]),
                "oi_spread_pct": row.get("oi__contract_spread_pct", ""),
                "oi_oi": row.get("oi__contract_oi", ""),
                "oi_volume": row.get("oi__contract_volume", ""),
                "oi_rr_options": row.get("oi__rr_options", ""),
                "eil_v3_verdict": row.get("eil__eil_v3_verdict", ""),
                "eil_pse_mode": row.get("eil__pse_execution_mode", ""),
                "execution_effective_verdict": row.get("exe__effective_execution_verdict", ""),
                "execution_capital_permission": row.get("exe__capital_permission", ""),
                "execution_eod_candidate_permission": row.get("exe__eod_candidate_permission", ""),
                "execution_eod_candidate_authorized": row.get("exe__eod_candidate_authorized", ""),
                "execution_candidate_size": _first(row, ["exe__candidate_size", "exe__eod_candidate_size", "exe__pse_pre_horizon_size"]),
                "execution_sizing_policy": row.get("exe__sizing_policy", ""),
                "eod_status": row.get("eod__eod_candidate_status", ""),
                "eod_slate_rank": row.get("eod__slate_rank", ""),
                "eod_candidate_permission": _first(row, ["eod__eod_candidate_permission", "eod__candidate_status"]),
                "eod_candidate_size": _first(row, ["eod__candidate_size", "eod__eod_candidate_size", "eod__pse_pre_horizon_size"]),
                "eod_sizing_policy": row.get("eod__sizing_policy", ""),
                "eod_horizon_bucket": row.get("eod__horizon_bucket", ""),
                "eod_expected_move_window": row.get("eod__expected_move_window", ""),
                "eod_expected_holding_days": row.get("eod__expected_holding_days", ""),
                "eod_tier": row.get("eod__structural_tier", ""),
                "eod_direction": row.get("eod__direction", ""),
                "eod_primary_direction": row.get("eod__primary_direction", ""),
                "eod_selected_contract_side": row.get("eod__selected_contract_side", ""),
                "eod_direction_reroute_status": row.get("eod__direction_reroute_status", ""),
                "eod_direction_decision_reason": row.get("eod__direction_decision_reason", ""),
                "eod_monetisation_fit_score": row.get("eod__monetisation_fit_score", ""),
                "eod_contract_repair_status": row.get("eod__contract_repair_status", ""),
                "eod_contract_repair_required": row.get("eod__contract_repair_required", ""),
                "eod_contract_repair_reason": row.get("eod__contract_repair_reason", ""),
                "eod_contract_quality_score": row.get("eod__contract_quality_score", ""),
                "eod_contract_spread_pct": row.get("eod__contract_spread_pct_eod", ""),
                "eod_contract_oi": row.get("eod__contract_oi", ""),
                "eod_contract_volume": row.get("eod__contract_volume", ""),
                "shadow_opportunity_score": row.get("shadow__shadow_opportunity_score", ""),
                "shadow_opportunity_label": row.get("shadow__shadow_opportunity_label", ""),
                "shadow_opportunity_reason": row.get("shadow__shadow_opportunity_reason", ""),
                "shadow_slate_rank": row.get("shadow__slate_rank", ""),
                "shadow_status": row.get("shadow__eod_candidate_status", ""),
                "shadow_dropoff_reason": row.get("shadow__eod_dropoff_reason", ""),
                "shadow_direction": row.get("shadow__direction", ""),
                "shadow_primary_direction": row.get("shadow__primary_direction", ""),
                "shadow_selected_contract_side": row.get("shadow__selected_contract_side", ""),
                "shadow_contract_repair_status": row.get("shadow__contract_repair_status", ""),
                "shadow_contract_repair_reason": row.get("shadow__contract_repair_reason", ""),
                "catalyst_detected": _first(row, ["eod__catalyst_detected", "shadow__catalyst_detected", "mv__catalyst_detected", "eil__catalyst_detected"]),
                "catalyst_type": _first(row, ["eod__catalyst_type", "shadow__catalyst_type", "mv__catalyst_type", "eil__catalyst_type"]),
                "catalyst_date": _first(row, ["eod__catalyst_date", "shadow__catalyst_date", "mv__catalyst_date", "eil__catalyst_date"]),
                "catalyst_truth_score": _first(row, ["eod__catalyst_truth_score", "shadow__catalyst_truth_score", "mv__catalyst_truth_score", "eil__catalyst_truth_score"]),
                "catalyst_event_status": _first(row, ["eod__catalyst_event_status", "mv__catalyst_event_status", "eil__catalyst_event_status"]),
                "catalyst_source_tier": _first(row, ["eod__catalyst_source_tier", "mv__catalyst_source_tier", "eil__catalyst_source_tier"]),
                "catalyst_source_url": _first(row, ["eod__catalyst_source_url", "mv__catalyst_source_url", "eil__catalyst_source_url"]),
                "catalyst_ticker_role": _first(row, ["eod__catalyst_ticker_role", "eil__catalyst_ticker_role"]),
                "catalyst_expected_impact": _first(row, ["eod__catalyst_expected_impact", "eil__catalyst_expected_impact"]),
                "catalyst_failure_risk": _first(row, ["eod__catalyst_failure_risk", "eil__catalyst_failure_risk"]),
                "morning_permission": row.get("mv__execution_permission", ""),
                "morning_state": row.get("mv__live_validation_state", ""),
                "morning_validation_score": row.get("mv__validation_score", ""),
            }
        )

    out = pd.DataFrame(records)
    if not out.empty:
        out["_stage_sort"] = out["last_stage_reached"].map(STAGE_ORDER).fillna(0)
        out = out.sort_values(["_stage_sort", "dropoff_stage", "ticker"], ascending=[False, True, True]).drop(columns=["_stage_sort"])

    if output_path is None:
        output_path = run_dir / "diagnostics" / f"dropoff_audit_{run_id}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    summary = {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "output_csv": str(output_path),
        "input_paths": {k: str(v) if v else "" for k, v in paths.items()},
        "rows": int(len(out)),
        "last_stage_counts": dict(Counter(out["last_stage_reached"])) if not out.empty else {},
        "dropoff_stage_counts": dict(Counter(out["dropoff_stage"])) if not out.empty else {},
        "audit_layer_counts": dict(Counter(out["audit_layer"])) if not out.empty and "audit_layer" in out.columns else {},
        "root_cause_family_counts": dict(Counter(out["root_cause_family"])) if not out.empty and "root_cause_family" in out.columns else {},
        "audit_severity_counts": dict(Counter(out["audit_severity"])) if not out.empty and "audit_severity" in out.columns else {},
        "audit_behavior_counts": dict(Counter(out["audit_behavior"])) if not out.empty and "audit_behavior" in out.columns else {},
        "shadow_opportunity_label_counts": dict(Counter(out["shadow_opportunity_label"])) if not out.empty and "shadow_opportunity_label" in out.columns else {},
        "vanguard_expected_options_scope_counts": dict(Counter(out["vanguard_expected_options_scope"])) if not out.empty and "vanguard_expected_options_scope" in out.columns else {},
        "vanguard_support_override_count": int(out["vanguard_support_override"].astype(str).str.upper().isin({"TRUE", "1", "YES"}).sum()) if not out.empty and "vanguard_support_override" in out.columns else 0,
        "vanguard_contract_contradiction_counts": dict(Counter(out["vanguard_contract_contradiction"])) if not out.empty and "vanguard_contract_contradiction" in out.columns else {},
        "top_dropoff_reasons": dict(Counter(out["dropoff_reason"]).most_common(20)) if not out.empty else {},
    }
    summary_path = output_path.with_suffix(".json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return out


def _latest_run_id(runs_dir: Path) -> str:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            rid = _s(data.get("run_id"))
            if rid:
                return rid
        except Exception:
            pass
    runs = sorted([p for p in runs_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise FileNotFoundError(f"No run folders found under {runs_dir}")
    return runs[0].name


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AVSHUNTER drop-off audit from OI through final validation.")
    parser.add_argument("--run-id", default="", help="Run id. Defaults to data/output/latest.json or newest run folder.")
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    run_id = args.run_id or _latest_run_id(runs_dir)
    output = Path(args.output) if args.output else None
    df = build_dropoff_audit(run_id, runs_dir=runs_dir, output_path=output)
    print(f"dropoff_audit complete: {len(df)} rows for run {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
