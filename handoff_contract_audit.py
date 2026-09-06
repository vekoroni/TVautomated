"""AVSHUNTER end-to-end handoff contract audit.

This is the UAT receipt checker. It verifies that the data attributes produced
by upstream stages are present under known aliases in the downstream artifacts,
with fill-rate evidence and a concrete outstanding-fix list.
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

MISSING_TOKENS = {
    "", "NONE", "NAN", "NULL", "N/A", "UNKNOWN", "MISSING",
    "<NA>",  # pandas NA stringified
    "[]",    # serialised empty Python list — options_hard_vetoes with no vetoes
    "{}",    # serialised empty Python dict
}
OPTIONS_RESEARCH_PERMISSION_VALUES = {
    "NONE_OPTIONS_RESEARCH_ONLY",
    "MANUAL_REVIEW_REQUIRED",
    "NO_CAPITAL",
}
OPTIONS_BLOCKED_ROUTES = {"OPTIONS_BLOCKED", "OPTIONS_EQUITY_ONLY_BETTER"}
PSE_RETIRED_POLICY = "PSE_IGNORED_MANUAL_SIZING"
PSE_LEGACY_RETIRED_POLICIES = {
    "ADVISORY_ONLY",
    "POSITION_SIZING_RETIRED_ADVISORY_ONLY",
}
EOD_CARRY_FORWARD_STATUSES = {
    "EOD_THESIS_READY", "EOD_THESIS_READY_REPAIR_AT_OPEN", "EOD_TRIGGER_READY",
    "EOD_WATCHLIST_MONETISABLE", "EOD_PROBE_CANDIDATE",
    "EOD_DATA_INSUFFICIENT_REVIEW", "EOD_CATALYST_EXECUTE_CANDIDATE",
    "EOD_EXECUTE_CANDIDATE", "EOD_EXECUTE_WITH_CAUTION",
    "EOD_CONTRACT_REPAIR_REQUIRED", "EOD_TRIGGER_READY_REVIEW",
    "EOD_CATALYST_WATCH",
}
INTERPRETER_TEXT_PATTERN = (
    r"unsupported operand|traceback|unhandled exception|typeerror|valueerror:|keyerror:"
)

MCMILLAN_FIELD_CONTRACTS = [
    {"name": "iv_gex_entry_quality", "aliases": ["iv_gex_entry_quality"], "severity": "WARN"},
    {"name": "iv_gex_entry_quality_label", "aliases": ["iv_gex_entry_quality_label"], "severity": "WARN"},
    {"name": "iv_gex_entry_quality_narrative", "aliases": ["iv_gex_entry_quality_narrative"], "severity": "WARN"},
    {"name": "gamma_island_on_path", "aliases": ["gamma_island_on_path"], "severity": "WARN"},
    {"name": "gamma_island_label", "aliases": ["gamma_island_label"], "severity": "WARN"},
    {"name": "gamma_island_level", "aliases": ["gamma_island_level"], "severity": "WARN"},
    {"name": "gamma_island_distance_pct", "aliases": ["gamma_island_distance_pct"], "severity": "WARN"},
    {"name": "gamma_island_source", "aliases": ["gamma_island_source"], "severity": "WARN"},
    {"name": "gamma_island_note", "aliases": ["gamma_island_note"], "severity": "WARN"},
    {"name": "move_theta_ratio", "aliases": ["move_theta_ratio"], "severity": "WARN"},
    {"name": "move_theta_margin_label", "aliases": ["move_theta_margin_label"], "severity": "WARN"},
    {"name": "move_theta_narrative", "aliases": ["move_theta_narrative"], "severity": "WARN"},
    {"name": "crowd_arrival_state", "aliases": ["crowd_arrival_state"], "severity": "WARN"},
    {"name": "crowd_arrival_score", "aliases": ["crowd_arrival_score"], "severity": "WARN"},
    {"name": "crowd_arrival_components", "aliases": ["crowd_arrival_components"], "severity": "WARN"},
    {"name": "crowd_arrival_narrative", "aliases": ["crowd_arrival_narrative"], "severity": "WARN"},
]


FIELD_CONTRACTS: dict[str, list[dict[str, Any]]] = {
    "vanguard": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "vanguard_verdict", "aliases": ["verdict"], "severity": "FAIL"},
        {"name": "final_recommendation", "aliases": ["final_recommendation"], "severity": "FAIL"},
        {"name": "statistical_edge_quality", "aliases": ["layer2__edge_quality", "edge_quality"], "severity": "FAIL"},
        {"name": "probability_verdict", "aliases": ["layer2__probability_verdict"], "severity": "FAIL"},
        {"name": "probability_edge", "aliases": ["layer2__probability_edge"], "severity": "WARN"},
        {"name": "edge_direction", "aliases": ["edge_direction"], "severity": "WARN"},
        {"name": "active_no_edge_reason", "aliases": ["no_edge_reason"], "severity": "WARN"},
        {
            "name": "legacy_no_edge_note",
            "aliases": [
                "legacy_no_edge_reason",
                "statistical_support_note",
                "layer2__legacy_no_edge_reason",
                "layer2__statistical_support_note",
            ],
            "severity": "WARN",
        },
    ],
    "options_intelligence": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "option_direction", "aliases": ["options_direction", "option_direction", "direction"], "severity": "FAIL"},
        {"name": "selected_contract", "aliases": ["recommended_contract", "contract_occ_symbol", "contract_symbol", "occ_symbol", "option_symbol"], "severity": "FAIL"},
        {"name": "contract_strike", "aliases": ["contract_strike", "strike"], "severity": "WARN"},
        {"name": "contract_expiry", "aliases": ["contract_expiry", "expiry", "expiration"], "severity": "WARN"},
        {"name": "contract_dte", "aliases": ["contract_dte", "dte"], "severity": "WARN"},
        {"name": "contract_premium", "aliases": ["contract_premium", "premium_mid", "premium", "contract_mid"], "severity": "WARN"},
        {"name": "contract_spread_pct", "aliases": ["contract_spread_pct", "spread_pct_mid", "spread_pct", "options_spread_pct"], "severity": "FAIL"},
        {"name": "contract_open_interest", "aliases": ["contract_oi", "open_interest", "oi"], "severity": "FAIL"},
        {"name": "contract_volume", "aliases": ["contract_volume", "volume"], "severity": "WARN"},
        {"name": "contract_delta", "aliases": ["contract_delta", "delta"], "severity": "WARN"},
        {"name": "options_score", "aliases": ["options_score", "oi_score"], "severity": "FAIL"},
        {"name": "asymmetry_rr", "aliases": ["rr_options", "rr_premium_expected", "rr"], "severity": "FAIL"},
        {"name": "convexity_context", "aliases": ["option_gain_at_target", "convexity_score", "expected_move_pct", "target_move_pct"], "severity": "WARN"},
        {"name": "pcr_volume_status", "aliases": ["pcr_vol_status", "pcr_vol_missing_reason", "dw_pcr_vol"], "severity": "WARN"},
        {"name": "direction_conflict_status", "aliases": ["direction_conflict_status", "direction_conflict_reason"], "severity": "WARN"},
        {"name": "contract_repair_status", "aliases": ["contract_repair_status", "contract_repair_reason", "contract_repair_attempted"], "severity": "WARN"},
        {"name": "options_research_permission", "aliases": ["execution_permission"], "severity": "FAIL"},
        {"name": "options_research_route", "aliases": ["final_route", "options_research_route"], "severity": "FAIL"},
        {"name": "options_research_score", "aliases": ["options_research_score"], "severity": "WARN"},
        {"name": "options_hard_vetoes", "aliases": ["hard_vetoes"], "severity": "WARN"},
    ],
    "eil_enriched": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "eil_verdict", "aliases": ["eil_v3_verdict", "eil_raw_verdict"], "severity": "FAIL"},
        {"name": "execution_mode", "aliases": ["pse_execution_mode", "effective_execution_verdict"], "severity": "FAIL"},
        {"name": "trigger_readiness", "aliases": ["trigger_quality", "trigger_go_eligible", "trigger_primary", "trigger_score"], "severity": "WARN"},
        {"name": "option_direction", "aliases": ["options_direction", "option_direction", "direction"], "severity": "FAIL"},
        {"name": "selected_contract", "aliases": ["recommended_contract", "contract_occ_symbol", "contract_symbol", "occ_symbol", "option_symbol"], "severity": "FAIL"},
        {"name": "contract_spread_pct", "aliases": ["contract_spread_pct", "spread_pct_mid", "spread_pct"], "severity": "WARN"},
        {"name": "contract_open_interest", "aliases": ["contract_oi", "open_interest", "oi"], "severity": "WARN"},
        {"name": "catalyst_truth", "aliases": ["catalyst_truth_score", "catalyst_detected", "catalyst_trade_class"], "severity": "WARN"},
        {"name": "catalyst_event_identity", "aliases": ["catalyst_type", "catalyst_date", "catalyst_event_status", "catalyst_source_tier"], "severity": "WARN"},
        {"name": "pcr_volume_status", "aliases": ["pcr_vol_status", "pcr_vol_missing_reason", "dw_pcr_vol"], "severity": "WARN"},
        {"name": "direction_conflict_status", "aliases": ["direction_conflict_status", "direction_conflict_reason"], "severity": "WARN"},
        {"name": "contract_repair_status", "aliases": ["contract_repair_status", "contract_repair_reason", "contract_repair_attempted"], "severity": "WARN"},
        {"name": "options_research_permission", "aliases": ["execution_permission"], "severity": "FAIL"},
        {"name": "options_research_route", "aliases": ["final_route", "options_research_route"], "severity": "FAIL"},
        {"name": "options_research_score", "aliases": ["options_research_score"], "severity": "WARN"},
        {"name": "options_hard_vetoes", "aliases": ["hard_vetoes"], "severity": "WARN"},
        *MCMILLAN_FIELD_CONTRACTS,
    ],
    "execution": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "execution_verdict", "aliases": ["effective_execution_verdict", "execution_verdict", "fd_verdict"], "severity": "FAIL"},
        {"name": "capital_permission", "aliases": ["capital_permission", "final_size", "position_size", "size"], "severity": "FAIL"},
        {"name": "eod_candidate_permission", "aliases": ["eod_candidate_permission", "eod_candidate_authorized"], "severity": "WARN"},
        {"name": "candidate_size", "aliases": ["candidate_size", "eod_candidate_size", "pse_pre_horizon_size"], "severity": "WARN"},
        {"name": "sizing_policy", "aliases": ["sizing_policy"], "severity": "WARN"},
        {"name": "capital_authorization_state", "aliases": ["capital_authorization_state", "execution_authorized", "eod_candidate_authorized"], "severity": "WARN"},
        {"name": "execution_reason", "aliases": ["execution_authority_reason", "signal_authority_reason", "pse_block_reason"], "severity": "WARN"},
        {"name": "pcr_volume_status", "aliases": ["pcr_vol_status", "pcr_vol_missing_reason"], "severity": "WARN"},
        {"name": "direction_conflict_status", "aliases": ["direction_conflict_status", "direction_conflict_reason"], "severity": "WARN"},
        {"name": "options_research_permission", "aliases": ["execution_permission"], "severity": "FAIL"},
        {"name": "options_research_route", "aliases": ["final_route", "options_research_route"], "severity": "FAIL"},
        {"name": "options_research_score", "aliases": ["options_research_score"], "severity": "WARN"},
        {"name": "options_hard_vetoes", "aliases": ["hard_vetoes"], "severity": "WARN"},
        *MCMILLAN_FIELD_CONTRACTS,
    ],
    "eod_candidates": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "eod_status", "aliases": ["eod_candidate_status"], "severity": "FAIL"},
        {"name": "eod_reason", "aliases": ["eod_candidate_reason", "eod_dropoff_reason"], "severity": "FAIL"},
        {"name": "structural_tier", "aliases": ["structural_tier"], "severity": "FAIL"},
        {"name": "eod_candidate_permission", "aliases": ["eod_candidate_permission", "candidate_status"], "severity": "FAIL"},
        {"name": "candidate_size", "aliases": ["candidate_size", "eod_candidate_size", "pse_pre_horizon_size"], "severity": "WARN"},
        {"name": "sizing_policy", "aliases": ["sizing_policy"], "severity": "WARN"},
        {"name": "monetisation_fit", "aliases": ["monetisation_fit_score", "monetisation_fit_label"], "severity": "FAIL"},
        {"name": "direction_decision", "aliases": ["primary_direction", "selected_contract_side", "direction_reroute_status", "direction_decision_reason"], "severity": "FAIL"},
        {"name": "contract_repair", "aliases": ["contract_quality_score", "contract_repair_status", "contract_repair_required", "contract_repair_reason"], "severity": "FAIL"},
        {"name": "contract_liquidity", "aliases": ["contract_spread_pct_eod", "contract_oi", "contract_volume", "contract_delta"], "severity": "WARN"},
        {"name": "pcr_volume_status", "aliases": ["pcr_vol_status", "pcr_vol_missing_reason"], "severity": "WARN"},
        {"name": "direction_conflict_status", "aliases": ["direction_conflict_status", "direction_conflict_reason"], "severity": "WARN"},
        {"name": "trigger_readiness", "aliases": ["trigger_quality", "trigger_go_eligible", "trigger_primary", "trigger_score"], "severity": "WARN"},
        {"name": "catalyst_truth", "aliases": ["catalyst_truth_score", "catalyst_detected", "catalyst_trade_class"], "severity": "WARN"},
        {"name": "catalyst_event_identity", "aliases": ["catalyst_type", "catalyst_date", "catalyst_event_status", "catalyst_source_tier", "catalyst_source_url"], "severity": "WARN"},
        {"name": "options_research_route", "aliases": ["final_route", "options_research_route"], "severity": "WARN"},
        {"name": "options_hard_vetoes", "aliases": ["hard_vetoes"], "severity": "WARN"},
        *MCMILLAN_FIELD_CONTRACTS,
    ],
    "shadow_book": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "shadow_opportunity_score", "aliases": ["shadow_opportunity_score"], "severity": "FAIL"},
        {"name": "shadow_opportunity_label", "aliases": ["shadow_opportunity_label"], "severity": "WARN"},
        {"name": "shadow_opportunity_reason", "aliases": ["shadow_opportunity_reason", "eod_dropoff_reason"], "severity": "WARN"},
        {"name": "direction_decision", "aliases": ["primary_direction", "selected_contract_side", "direction_reroute_status", "direction_decision_reason"], "severity": "WARN"},
        {"name": "contract_repair", "aliases": ["contract_quality_score", "contract_repair_status", "contract_repair_required", "contract_repair_reason"], "severity": "WARN"},
        {"name": "options_context", "aliases": ["options_score", "rr", "contract_spread_pct_eod", "contract_oi", "contract_volume"], "severity": "WARN"},
        {"name": "trigger_or_catalyst_context", "aliases": ["trigger_quality", "trigger_go_eligible", "catalyst_truth_score", "catalyst_trade_class"], "severity": "WARN"},
        *MCMILLAN_FIELD_CONTRACTS,
    ],
    "morning_validation": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "behaviour_state", "aliases": ["behaviour_state_key", "behaviour_state_hash"], "severity": "WARN"},
        {"name": "actuarial_match_type", "aliases": ["actuarial_match_type", "actuarial_ev_weight"], "severity": "WARN"},
        {"name": "morning_permission", "aliases": ["morning_execution_permission", "morning_execution_route", "execution_permission", "mv_verdict"], "severity": "FAIL"},
        {"name": "morning_state", "aliases": ["live_validation_state", "mv_score"], "severity": "FAIL"},
        {"name": "eod_status", "aliases": ["eod_candidate_status"], "severity": "FAIL"},
        {"name": "eod_reason", "aliases": ["eod_candidate_reason", "eod_dropoff_reason"], "severity": "FAIL"},
        {"name": "monetisation_fit", "aliases": ["monetisation_fit_score", "monetisation_fit_label"], "severity": "WARN"},
        {"name": "direction_decision", "aliases": ["primary_direction", "selected_contract_side", "direction_reroute_status", "direction_decision_reason"], "severity": "WARN"},
        {"name": "contract_repair", "aliases": ["contract_quality_score", "contract_repair_status", "contract_repair_required", "contract_repair_reason"], "severity": "WARN"},
        {"name": "catalyst_truth", "aliases": ["catalyst_truth_score", "catalyst_detected", "catalyst_trade_class"], "severity": "WARN"},
        {"name": "catalyst_event_identity", "aliases": ["catalyst_type", "catalyst_date", "catalyst_event_status", "catalyst_source_tier", "catalyst_source_url"], "severity": "WARN"},
        *MCMILLAN_FIELD_CONTRACTS,
    ],
    "lab": [
        {"name": "ticker", "aliases": ["ticker"], "severity": "FAIL"},
        {"name": "lab_verdict", "aliases": ["lab_verdict", "final_action", "final_verdict"], "severity": "FAIL"},
        {"name": "governed_invalidation", "aliases": ["invalidation_price", "invalidation_spot"], "severity": "WARN"},
        {"name": "direction_lineage", "aliases": ["governed_direction_record_sha256"], "severity": "FAIL"},
    ],
}

ARTIFACT_PATTERNS: dict[str, list[str]] = {
    "vanguard": [r"vanguard/vanguard_signals.csv", r"vanguard/vanguard_signals_{run_id}.csv", r"vanguard/vanguard_signals_*.csv"],
    "options_intelligence": [r"options/options_intelligence_{run_id}.csv", r"options/options_intelligence_*.csv"],
    "eil_enriched": [r"superbrain/eil_enriched_{run_id}.csv", r"superbrain/eil_enriched_*.csv"],
    "execution": [r"execution/execution_v3_5_{run_id}.csv", r"execution/execution_*.csv"],
    "eod_candidates": [r"morning_validation/morning_candidates_{run_id}.csv", r"morning_validation/morning_candidates_*.csv"],
    "shadow_book": [r"morning_validation/missed_opportunity_shadow_book_{run_id}.csv", r"morning_validation/missed_opportunity_shadow_book_*.csv"],
    "morning_validation": [r"morning_validation/morning_validated_trades_{run_id}.csv", r"morning_validation/morning_validated_trades_*.csv"],
    "lab": [r"intelligence_lab/final_opportunity_book_{run_id}.csv", r"intelligence_lab/final_opportunity_book_*.csv"],
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


def _missing(value: Any) -> bool:
    return _s(value).upper() in MISSING_TOKENS


def _latest_run_id(runs_dir: Path) -> str:
    latest = runs_dir.parent / "latest.json"
    if latest.exists():
        try:
            payload = json.loads(latest.read_text(encoding="utf-8-sig"))
            rid = _s(payload.get("run_id") or payload.get("latest_run_id"))
            if rid:
                return rid
        except Exception:
            pass
    runs = sorted([p for p in runs_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not runs:
        raise FileNotFoundError(f"No run folders found under {runs_dir}")
    return runs[0].name


def _find_artifact(run_dir: Path, run_id: str, patterns: Iterable[str]) -> Optional[Path]:
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(run_dir.glob(pattern.format(run_id=run_id)))
    candidates = [path for path in candidates if path.exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: path.stat().st_mtime)[-1]


def _read_csv(path: Optional[Path]) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _fill_rate(df: pd.DataFrame, aliases: list[str]) -> tuple[list[str], int, float]:
    present = [alias for alias in aliases if alias in df.columns]
    if df.empty or not present:
        return present, 0, 0.0
    filled_mask = pd.Series(False, index=df.index)
    for alias in present:
        filled_mask = filled_mask | ~df[alias].map(_missing)
    filled = int(filled_mask.sum())
    return present, filled, round(filled / max(len(df), 1), 4)


def _first_text_series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    series = pd.Series("", index=df.index, dtype=object)
    for alias in aliases:
        if alias not in df.columns:
            continue
        values = df[alias].map(_s)
        series = series.mask(series.map(_missing), values)
    return series.fillna("").astype(str)


def _first_numeric_series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    series = pd.Series(0.0, index=df.index, dtype=float)
    seen = pd.Series(False, index=df.index)
    for alias in aliases:
        if alias not in df.columns:
            continue
        values = pd.to_numeric(df[alias], errors="coerce")
        take = ~seen & values.notna()
        series = series.mask(take, values)
        seen = seen | take
    return series.fillna(0.0)


def _first_nullable_numeric_series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    series = pd.Series(float("nan"), index=df.index, dtype=float)
    seen = pd.Series(False, index=df.index)
    for alias in aliases:
        if alias not in df.columns:
            continue
        values = pd.to_numeric(df[alias], errors="coerce")
        take = ~seen & values.notna()
        series = series.mask(take, values)
        seen = seen | take
    return series


def _truthy_series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series:
    out = pd.Series(False, index=df.index)
    for alias in aliases:
        if alias not in df.columns:
            continue
        text = df[alias].map(lambda value: _s(value).upper())
        out = out | text.isin({"TRUE", "1", "YES", "Y"})
    return out


def _sample_tickers(df: pd.DataFrame, mask: pd.Series, limit: int = 12) -> str:
    if "ticker" not in df.columns:
        return ""
    tickers = [_s(value).upper() for value in df.loc[mask, "ticker"].head(limit).tolist()]
    return ",".join([ticker for ticker in tickers if ticker])


def _semantic_record(
    *,
    stage: str,
    path: str,
    row_count: int,
    field_contract: str,
    severity: str,
    status: str,
    matched_rows: int,
    recommendation: str,
    sample_tickers: str = "",
) -> dict[str, Any]:
    detail = recommendation
    if sample_tickers:
        detail = f"{recommendation} Sample tickers: {sample_tickers}."
    return {
        "stage": stage,
        "artifact_exists": True,
        "artifact_path": path,
        "row_count": row_count,
        "field_contract": field_contract,
        "severity": severity,
        "status": status,
        "present_aliases": "",
        "filled_rows": int(matched_rows),
        "fill_rate": round(float(matched_rows) / max(int(row_count), 1), 4),
        "recommendation": detail,
    }


def _semantic_contract_audit(stage_frames: dict[str, pd.DataFrame], paths: dict[str, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for stage in ("options_intelligence", "eil_enriched", "execution"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        permission = _first_text_series(df, ["execution_permission", "options_execution_permission"]).str.upper()
        route = _first_text_series(df, ["final_route", "options_final_route", "options_research_route"]).str.upper()
        has_research_contract = (permission != "") | (route != "")
        bad_permission = has_research_contract & (permission != "") & (~permission.isin(OPTIONS_RESEARCH_PERMISSION_VALUES))
        if bad_permission.any():
            records.append(_semantic_record(
                stage=stage,
                path=paths.get(stage, ""),
                row_count=len(df),
                field_contract="options_research_permission_semantics",
                severity="FAIL",
                status="OPTIONS_PERMISSION_NOT_RESEARCH_ONLY",
                matched_rows=int(bad_permission.sum()),
                sample_tickers=_sample_tickers(df, bad_permission),
                recommendation=(
                    "Options Intelligence is research-only. Preserve execution_permission="
                    f"{OPTIONS_RESEARCH_PERMISSION_VALUES}; use separate morning/live permission fields downstream."
                ),
            ))

    for stage in ("eil_enriched", "execution", "eod_candidates"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        route = _first_text_series(df, ["final_route", "options_final_route", "options_research_route"]).str.upper()
        hard_vetoes = _first_text_series(df, ["hard_vetoes", "options_hard_vetoes"]).str.upper()
        capital_permission = _first_text_series(df, ["capital_permission", "eod_candidate_permission", "candidate_status"]).str.upper()
        effective_verdict = _first_text_series(df, ["effective_execution_verdict", "eod_candidate_status"]).str.upper()
        eod_auth = _truthy_series(df, ["eod_candidate_authorized"])
        promoted = (
            capital_permission.isin({"EOD_CANDIDATE_ONLY", "MORNING_VALIDATION_REQUIRED", "READY_EXECUTE"})
            | effective_verdict.str.contains("EOD_EXECUTE|MORNING_VALIDATION_REQUIRED", regex=True, na=False)
            | eod_auth
        )
        blocked_options = route.isin(OPTIONS_BLOCKED_ROUTES) | (~hard_vetoes.map(_missing))
        contradiction = blocked_options & promoted
        if contradiction.any():
            records.append(_semantic_record(
                stage=stage,
                path=paths.get(stage, ""),
                row_count=len(df),
                field_contract="options_route_vs_candidate_authority",
                severity="FAIL",
                status="OPTIONS_BLOCKED_PROMOTED_TO_EOD_CANDIDATE",
                matched_rows=int(contradiction.sum()),
                sample_tickers=_sample_tickers(df, contradiction),
                recommendation=(
                    "Do not promote rows with OPTIONS_BLOCKED, OPTIONS_EQUITY_ONLY_BETTER, "
                    "or non-empty hard_vetoes into EOD/morning candidates. Repair the contract first."
                ),
            ))

    for stage in ("execution", "eod_candidates", "eil_enriched"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        sizing_policy = _first_text_series(df, ["sizing_policy"]).str.upper()
        retired = sizing_policy.isin({PSE_RETIRED_POLICY, *PSE_LEGACY_RETIRED_POLICIES})
        size = _first_numeric_series(df, ["pse_final_size", "fd_size", "final_size", "position_size", "size"])
        positive_size = retired & (size > 0.0)
        if positive_size.any():
            records.append(_semantic_record(
                stage=stage,
                path=paths.get(stage, ""),
                row_count=len(df),
                field_contract="retired_pse_size_semantics",
                severity="FAIL",
                status="RETIRED_PSE_EMITTED_POSITIVE_SIZE",
                matched_rows=int(positive_size.sum()),
                sample_tickers=_sample_tickers(df, positive_size),
                recommendation=(
                    "PSE is retired from production authority. Keep live size at zero and route "
                    "eligible rows through EOD_CANDIDATE_ONLY/morning validation for manual sizing."
                ),
            ))

    for stage in ("options_intelligence", "eil_enriched", "execution", "eod_candidates"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        direction = _first_text_series(
            df, ["governed_direction", "final_direction", "canonical_direction", "direction"]
        ).str.upper()
        invalidation_state = _first_text_series(
            df, ["invalidation_state", "ev3_invalidation_state"]
        ).str.upper()
        invalidation = _first_numeric_series(
            df, ["invalidation_spot", "ev3_invalidation_spot", "invalidation_price"]
        )
        capital_permission = _first_text_series(
            df, ["capital_permission", "morning_execution_permission", "eod_candidate_permission"]
        ).str.upper()
        final_action = _first_text_series(
            df, ["final_action", "morning_entry_action", "action_category"]
        ).str.upper()
        promoted = (
            capital_permission.isin({"YES", "GO", "GO_LIMIT", "BUY_NOW", "BUY_SMALL", "READY_EXECUTE"})
            | final_action.isin({"BUY_NOW", "BUY_SMALL", "GO", "GO_LIMIT"})
            | _truthy_series(df, ["capital_authorized", "eod_candidate_authorized", "lab_tradeable"])
        )
        missing_invalidation = direction.isin({"CALL", "PUT"}) & (
            (invalidation_state != "AVAILABLE") | invalidation.isna() | (invalidation <= 0.0)
        )
        contradiction = promoted & missing_invalidation
        if contradiction.any():
            records.append(_semantic_record(
                stage=stage,
                path=paths.get(stage, ""),
                row_count=len(df),
                field_contract="directional_invalidation_authority",
                severity="FAIL",
                status="DIRECTIONAL_TRADE_PROMOTED_WITHOUT_GOVERNED_INVALIDATION",
                matched_rows=int(contradiction.sum()),
                sample_tickers=_sample_tickers(df, contradiction),
                recommendation=(
                    "A directional CALL/PUT requires invalidation_state=AVAILABLE and a positive "
                    "governed invalidation level before any execution or capital permission."
                ),
            ))

    for stage in ("vanguard", "eil_enriched", "execution"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        profile_type = _first_text_series(
            df, ["profile_type", "layer1__profile_type", "vg__profile_type"]
        ).str.upper()
        profile_state = _first_text_series(
            df, ["market_profile_state", "market_profile_data_state", "profile_data_state"]
        ).str.upper()
        poc = _first_numeric_series(df, ["poc", "profile_poc", "layer1__poc", "vg__poc"])
        ready = _truthy_series(df, ["ready_to_trade", "auction_ready_to_trade"])
        auction_state = _first_text_series(df, ["auction_state", "layer1__auction_state"]).str.upper()
        unusable_profile = (
            profile_type.isin({"INSUFFICIENT_DATA", "UNAVAILABLE", "UNKNOWN"})
            | profile_state.isin({"MISSING", "UNAVAILABLE", "INSUFFICIENT_DATA", "PARTIAL"})
            | poc.isna()
            | (poc <= 0.0)
        )
        contradiction = unusable_profile & (ready | auction_state.eq("ALIGNED"))
        if contradiction.any():
            records.append(_semantic_record(
                stage=stage,
                path=paths.get(stage, ""),
                row_count=len(df),
                field_contract="market_profile_authority_semantics",
                severity="FAIL",
                status="UNUSABLE_PROFILE_MARKED_ALIGNED_OR_READY",
                matched_rows=int(contradiction.sum()),
                sample_tickers=_sample_tickers(df, contradiction),
                recommendation=(
                    "An unavailable or non-positive governed profile cannot contribute ALIGNED or "
                    "ready-to-trade evidence. Preserve null levels and report NOT_EVALUATED."
                ),
            ))

    # AVS-SD-003 G-12: explicit semantic rules.  These are intentionally
    # separate records so a known-bad run must fail for each violated contract,
    # rather than hiding several contradictions behind one aggregate status.
    options = stage_frames.get("options_intelligence", pd.DataFrame())
    if not options.empty:
        direction = _first_text_series(
            options, ["governed_direction", "final_direction", "canonical_direction", "direction"]
        ).str.upper()
        verdict = _first_text_series(
            options, ["options_verdict", "verdict", "campaign_verdict"]
        ).str.upper()
        inv_state = _first_text_series(
            options, ["invalidation_state", "ev3_invalidation_state"]
        ).str.upper()
        inv = _first_nullable_numeric_series(
            options, ["invalidation_spot", "ev3_invalidation_spot"]
        )
        bad = direction.isin({"CALL", "PUT"}) & verdict.eq("ARMED") & (
            inv_state.ne("AVAILABLE") | inv.isna() | inv.le(0.0)
        )
        if bad.any():
            records.append(_semantic_record(
                stage="options_intelligence", path=paths.get("options_intelligence", ""),
                row_count=len(options), field_contract="armed_requires_invalidation",
                severity="FAIL", status="ARMED_WITHOUT_GOVERNED_INVALIDATION",
                matched_rows=int(bad.sum()), sample_tickers=_sample_tickers(options, bad),
                recommendation="Stand down directional ARMED rows until governed invalidation is available.",
            ))

    eod = stage_frames.get("eod_candidates", pd.DataFrame())
    if not eod.empty:
        direction = _first_text_series(
            eod, ["governed_direction", "final_direction", "canonical_direction", "direction"]
        ).str.upper()
        status = _first_text_series(eod, ["eod_candidate_status", "eod_status"]).str.upper()
        permission = _first_text_series(
            eod, ["capital_permission", "eod_candidate_permission", "candidate_status"]
        ).str.upper()
        inv_state = _first_text_series(eod, ["invalidation_state", "ev3_invalidation_state"]).str.upper()
        inv = _first_nullable_numeric_series(
            eod, ["invalidation_spot", "ev3_invalidation_spot", "invalidation_level"]
        )
        candidate_like = status.isin(EOD_CARRY_FORWARD_STATUSES) | permission.isin({
            "EOD_CANDIDATE_ONLY", "MORNING_VALIDATION_REQUIRED", "READY_EXECUTE",
        }) | _truthy_series(eod, ["eod_candidate_authorized", "execution_authorized"])
        bad = direction.isin({"CALL", "PUT"}) & candidate_like & (
            inv_state.ne("AVAILABLE") | inv.isna() | inv.le(0.0)
        )
        if bad.any():
            records.append(_semantic_record(
                stage="eod_candidates", path=paths.get("eod_candidates", ""),
                row_count=len(eod), field_contract="eod_candidate_requires_invalidation",
                severity="FAIL", status="EOD_CANDIDATE_WITHOUT_GOVERNED_INVALIDATION",
                matched_rows=int(bad.sum()), sample_tickers=_sample_tickers(eod, bad),
                recommendation="Remove candidate/capital authority until governed invalidation is available.",
            ))

    lab = stage_frames.get("lab", pd.DataFrame())
    if not lab.empty:
        direction = _first_text_series(
            lab, ["governed_direction", "final_direction", "canonical_direction", "direction"]
        ).str.upper()
        action = _first_text_series(
            lab, ["final_action", "lab_verdict", "final_verdict", "action_category"]
        ).str.upper()
        inv_state = _first_text_series(lab, ["invalidation_state", "ev3_invalidation_state"]).str.upper()
        inv = _first_nullable_numeric_series(
            lab, ["invalidation_price", "invalidation_spot", "ev3_invalidation_spot"]
        )
        executable = action.isin({"BUY_NOW", "BUY_SMALL", "GO", "GO_LIMIT", "EXECUTE"}) | _truthy_series(
            lab, ["lab_tradeable", "capital_authorized", "execution_authorized"]
        )
        bad = direction.isin({"CALL", "PUT"}) & executable & (
            inv_state.ne("AVAILABLE") | inv.isna() | inv.le(0.0)
        )
        if bad.any():
            records.append(_semantic_record(
                stage="lab", path=paths.get("lab", ""), row_count=len(lab),
                field_contract="lab_execution_requires_invalidation", severity="FAIL",
                status="LAB_EXECUTABLE_WITHOUT_GOVERNED_INVALIDATION",
                matched_rows=int(bad.sum()), sample_tickers=_sample_tickers(lab, bad),
                recommendation="The Lab must display the row as blocked until governed invalidation is available.",
            ))

    for stage in ("options_intelligence", "eil_enriched", "execution", "eod_candidates", "lab"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        text = _first_text_series(
            df,
            ["stand_down_reason", "trigger_status_reason", "gate_reason", "notes", "eod_candidate_reason"],
        )
        bad = text.str.contains(INTERPRETER_TEXT_PATTERN, case=False, regex=True, na=False)
        if bad.any():
            records.append(_semantic_record(
                stage=stage, path=paths.get(stage, ""), row_count=len(df),
                field_contract="governed_reason_vocabulary", severity="FAIL",
                status="RAW_INTERPRETER_TEXT_PUBLISHED",
                matched_rows=int(bad.sum()), sample_tickers=_sample_tickers(df, bad),
                recommendation="Publish governed reason codes; keep exception class and text in diagnostics only.",
            ))

    vanguard = stage_frames.get("vanguard", pd.DataFrame())
    if not vanguard.empty:
        profile_type = _first_text_series(
            vanguard, ["profile_type", "layer1__profile_type", "vg__profile_type"]
        ).str.upper()
        profile_state = _first_text_series(
            vanguard, ["market_profile_state", "market_profile_data_state", "profile_data_state"]
        ).str.upper()
        auction = _first_text_series(vanguard, ["auction_state", "layer1__auction_state"]).str.upper()
        poc = _first_nullable_numeric_series(vanguard, ["poc", "profile_poc", "layer1__poc", "vg__poc"])
        insufficient = profile_type.isin({"INSUFFICIENT_DATA", "UNAVAILABLE", "UNKNOWN"}) | profile_state.isin({
            "MISSING", "UNAVAILABLE", "INSUFFICIENT_DATA", "PARTIAL", "NOT_EVALUATED",
        })
        bad_alignment = insufficient & auction.eq("ALIGNED")
        if bad_alignment.any():
            records.append(_semantic_record(
                stage="vanguard", path=paths.get("vanguard", ""), row_count=len(vanguard),
                field_contract="profile_state_vs_auction_state", severity="FAIL",
                status="INSUFFICIENT_PROFILE_MARKED_ALIGNED",
                matched_rows=int(bad_alignment.sum()), sample_tickers=_sample_tickers(vanguard, bad_alignment),
                recommendation="An insufficient profile must remain NOT_EVALUATED and cannot be ALIGNED.",
            ))
        fabricated_zero = insufficient & poc.notna() & poc.eq(0.0)
        if fabricated_zero.any():
            records.append(_semantic_record(
                stage="vanguard", path=paths.get("vanguard", ""), row_count=len(vanguard),
                field_contract="missing_profile_levels_are_null", severity="FAIL",
                status="MISSING_PROFILE_LEVEL_PUBLISHED_AS_ZERO",
                matched_rows=int(fabricated_zero.sum()), sample_tickers=_sample_tickers(vanguard, fabricated_zero),
                recommendation="Represent missing POC/VAH/VAL as null, never as a fabricated zero.",
            ))

    # Detect a universally lost field when an upstream artefact demonstrably
    # contains it.  Named absence remains valid; silent disappearance does not.
    lineage_contracts = {
        "contract_bid_size": ["contract_bid_size", "live_contract_bid_size", "bid_size"],
        "contract_ask_size": ["contract_ask_size", "live_contract_ask_size", "ask_size"],
        "contract_quote_quality": ["contract_quote_quality", "live_contract_quote_quality", "quote_quality"],
        "selected_quote_timestamp_utc": [
            "selected_quote_timestamp_utc", "contract_quote_timestamp_utc", "quote_timestamp_utc", "quote_as_of",
        ],
        "execution_viability_state": ["execution_viability_state"],
        "macro_packet_id": ["macro_packet_id"],
        "macro_packet_sha256": ["macro_packet_sha256"],
        "macro_source_fingerprint": ["macro_source_fingerprint"],
        "macro_as_of_utc": ["macro_as_of_utc", "macro_generated_at_utc"],
        "macro_session_date": ["macro_session_date"],
    }
    if not lab.empty:
        for field, aliases in lineage_contracts.items():
            source_stage = ""
            source_filled = 0
            for candidate_stage in ("morning_validation", "eod_candidates", "execution", "options_intelligence"):
                source = stage_frames.get(candidate_stage, pd.DataFrame())
                _, filled, _ = _fill_rate(source, aliases)
                if filled > 0:
                    source_stage = candidate_stage
                    source_filled = filled
                    break
            if not source_stage:
                continue
            _, destination_filled, _ = _fill_rate(lab, [field, *aliases])
            if destination_filled == 0:
                records.append(_semantic_record(
                    stage="lab", path=paths.get("lab", ""), row_count=len(lab),
                    field_contract=f"lineage:{field}", severity="FAIL",
                    status="UPSTREAM_FIELD_UNIVERSALLY_LOST",
                    matched_rows=source_filled,
                    recommendation=f"Map {field} from {source_stage} into every applicable Lab row or publish a named absence state.",
                ))

    if not options.empty and not lab.empty and "ticker" in options and "ticker" in lab:
        source_hash = _first_text_series(options, ["governed_direction_record_sha256"])
        target_hash = _first_text_series(lab, ["governed_direction_record_sha256"])
        source = pd.DataFrame({"ticker": options["ticker"].astype(str).str.upper(), "source_hash": source_hash})
        target = pd.DataFrame({"ticker": lab["ticker"].astype(str).str.upper(), "target_hash": target_hash})
        joined = source.drop_duplicates("ticker", keep="last").merge(
            target.drop_duplicates("ticker", keep="last"), on="ticker", how="inner"
        )
        comparable = ~joined["source_hash"].map(_missing) & ~joined["target_hash"].map(_missing)
        bad = comparable & joined["source_hash"].ne(joined["target_hash"])
        if bad.any():
            records.append(_semantic_record(
                stage="lab", path=paths.get("lab", ""), row_count=len(lab),
                field_contract="options_to_lab_direction_hash", severity="FAIL",
                status="DIRECTION_LINEAGE_HASH_MISMATCH", matched_rows=int(bad.sum()),
                sample_tickers=",".join(joined.loc[bad, "ticker"].head(12).tolist()),
                recommendation="Preserve the governed direction record hash unchanged from Options to the Lab.",
            ))

    for stage in ("options_intelligence", "eil_enriched", "execution", "eod_candidates", "lab"):
        df = stage_frames.get(stage, pd.DataFrame())
        if df.empty:
            continue
        source = _first_text_series(df, ["bar_data_source", "data_source"]).str.upper()
        state = _first_text_series(df, ["bar_evidence_state"]).str.upper()
        stale = source.eq("STALE_CACHE") | _truthy_series(df, ["is_stale"])
        bad = stale & state.ne("APPROVED_FALLBACK")
        if bad.any():
            records.append(_semantic_record(
                stage=stage, path=paths.get(stage, ""), row_count=len(df),
                field_contract="stale_bar_fallback_lineage", severity="FAIL",
                status="STALE_BAR_FALLBACK_UNNAMED", matched_rows=int(bad.sum()),
                sample_tickers=_sample_tickers(df, bad),
                recommendation="Stamp stale bars APPROVED_FALLBACK and preserve the state through every downstream handoff.",
            ))

    return records


def audit_run(run_id: str, *, runs_dir: Path = RUNS_DIR, output_dir: Optional[Path] = None) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run folder not found: {run_dir}")

    rows: list[dict[str, Any]] = []
    outstanding: list[dict[str, Any]] = []
    paths: dict[str, str] = {}
    stage_frames: dict[str, pd.DataFrame] = {}

    for stage, patterns in ARTIFACT_PATTERNS.items():
        path = _find_artifact(run_dir, run_id, patterns)
        paths[stage] = str(path or "")
        df = _read_csv(path)
        stage_frames[stage] = df
        exists = bool(path and path.exists())
        row_count = int(len(df))

        if not exists and stage == "morning_validation" and paths.get("eod_candidates"):
            record = {
                "stage": stage,
                "artifact_exists": False,
                "artifact_path": "",
                "row_count": 0,
                "field_contract": "__artifact__",
                "severity": "INFO",
                "status": "EXPECTED_NOT_RUN_EOD",
                "present_aliases": "",
                "filled_rows": 0,
                "fill_rate": 0.0,
                "recommendation": "Morning validation is expected to be absent after an EOD-only run.",
            }
            rows.append(record)
            continue

        if not exists:
            severity = "WARN" if stage == "morning_validation" else "FAIL"
            record = {
                "stage": stage,
                "artifact_exists": False,
                "artifact_path": "",
                "row_count": 0,
                "field_contract": "__artifact__",
                "severity": severity,
                "status": "MISSING_ARTIFACT",
                "present_aliases": "",
                "filled_rows": 0,
                "fill_rate": 0.0,
                "recommendation": f"Create {stage} artifact or check orchestrator stage.",
            }
            rows.append(record)
            outstanding.append(record)
            continue

        if stage == "shadow_book" and row_count == 0:
            dropoff_path = _find_artifact(
                run_dir,
                run_id,
                [
                    r"morning_validation/eod_dropoff_audit_{run_id}.csv",
                    r"morning_validation/eod_dropoff_audit_*.csv",
                ],
            )
            dropoff = _read_csv(dropoff_path)
            if dropoff.empty:
                status = "EMPTY_UNCORROBORATED"
                severity = "FAIL"
                eligible_count = 0
                recommendation = (
                    "An empty shadow book requires the EOD drop-off audit; regenerate both artefacts together."
                )
            else:
                scores = pd.to_numeric(
                    dropoff.get("shadow_opportunity_score", pd.Series(0.0, index=dropoff.index)),
                    errors="coerce",
                ).fillna(0.0)
                statuses = _first_text_series(
                    dropoff, ["eod_candidate_status", "eod_status"]
                ).str.upper()
                eligible = scores.ge(40.0) & ~statuses.isin(EOD_CARRY_FORWARD_STATUSES)
                eligible_count = int(eligible.sum())
                status = "EMPTY_BY_DESIGN" if eligible_count == 0 else "EMPTY_UNEXPECTED"
                severity = "INFO" if eligible_count == 0 else "FAIL"
                recommendation = (
                    "No row met the governed shadow mask; empty artefact is expected."
                    if eligible_count == 0
                    else "Rebuild the shadow book: the EOD drop-off audit contains eligible missed opportunities."
                )
            record = {
                "stage": stage,
                "artifact_exists": True,
                "artifact_path": str(path),
                "row_count": 0,
                "field_contract": "__artifact__",
                "severity": severity,
                "status": status,
                "present_aliases": "",
                "filled_rows": eligible_count,
                "fill_rate": 0.0,
                "recommendation": recommendation,
            }
            rows.append(record)
            if severity == "FAIL":
                outstanding.append(record)
            continue

        for contract in FIELD_CONTRACTS[stage]:
            present, filled, rate = _fill_rate(df, list(contract["aliases"]))
            if not present:
                status = "MISSING_COLUMN"
            elif row_count > 0 and filled == 0:
                status = "PRESENT_BUT_EMPTY"
            elif rate < 0.05 and contract["severity"] == "FAIL":
                status = "LOW_FILL_RATE"
            else:
                status = "OK"

            record = {
                "stage": stage,
                "artifact_exists": True,
                "artifact_path": str(path),
                "row_count": row_count,
                "field_contract": contract["name"],
                "severity": contract["severity"],
                "status": status,
                "present_aliases": ",".join(present),
                "filled_rows": filled,
                "fill_rate": rate,
                "recommendation": "" if status == "OK" else _recommendation(stage, contract["name"], contract["aliases"]),
            }
            rows.append(record)
            if status != "OK":
                outstanding.append(record)

    semantic_records = _semantic_contract_audit(stage_frames, paths)
    for record in semantic_records:
        rows.append(record)
        outstanding.append(record)

    status_counts = Counter(row["status"] for row in rows)
    fail_count = sum(1 for row in outstanding if row["severity"] == "FAIL")
    warn_count = sum(1 for row in outstanding if row["severity"] == "WARN")
    overall = "FAIL" if fail_count else "WARN" if warn_count else "PASS"

    if output_dir is None:
        output_dir = run_dir / "diagnostics"
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"handoff_contract_audit_{run_id}.csv"
    json_path = output_dir / f"handoff_contract_audit_{run_id}.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    payload = {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "status_counts": dict(status_counts),
        "artifact_paths": paths,
        "output_csv": str(csv_path),
        "outstanding_fixes": outstanding,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    payload["output_json"] = str(json_path)
    return payload


def _recommendation(stage: str, field_name: str, aliases: Iterable[str]) -> str:
    alias_text = ", ".join(aliases)
    if stage == "morning_validation":
        return f"Preserve upstream field contract '{field_name}' into morning validation output; accepted aliases: {alias_text}."
    if stage == "eod_candidates":
        return f"Add or populate EOD handoff field '{field_name}' before morning validation; accepted aliases: {alias_text}."
    if stage == "shadow_book":
        return f"Preserve missed-opportunity audit field '{field_name}' for false-negative review; accepted aliases: {alias_text}."
    return f"Ensure {stage} emits or preserves '{field_name}' using accepted aliases: {alias_text}."


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AVSHUNTER handoff contracts and print outstanding fixes.")
    parser.add_argument("--run-id", default="", help="Run id. Defaults to latest.json or newest run folder.")
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when FAIL items remain.")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    run_id = args.run_id or _latest_run_id(runs_dir)
    output_dir = Path(args.output_dir) if args.output_dir else None
    result = audit_run(run_id, runs_dir=runs_dir, output_dir=output_dir)
    print(json.dumps({
        "run_id": result["run_id"],
        "overall_status": result["overall_status"],
        "fail_count": result["fail_count"],
        "warn_count": result["warn_count"],
        "output_csv": result["output_csv"],
        "output_json": result["output_json"],
    }, indent=2))
    if args.strict and result["overall_status"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
