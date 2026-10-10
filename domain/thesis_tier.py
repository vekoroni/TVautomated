"""Discovery tier, order, win probability and horizon label from the thesis engine (item 11, D2-1 Step B).

Design: Enhancements/phase7/ITEM11_DISCOVERY_TIER_DESIGN_20261010.md (ACK approved D11-1..4, 10 Oct 2026). The legacy
Wyckoff/Crabel composite tier said nothing about the thesis; under tier_source thesis_v1 (config
discovery_thesis_tier_v1.json) these replace it. legacy_composite is the rollback (Discovery keeps that code).
- tier: 0 GO (trigger_layer.thesis_go_eligibility - the one GO rule), 1 READY_NOT_GO, 2 WAITING, 3 NO_ACTIVE_THESIS;
- win_probability: the governing setup's held-out within-hold rate (config/setup_rates_v1.json), else null;
- horizon label: the setup's evidence hold (domain.anticipated_move.evidence_runway, the runway's own source);
- order within tier: setup rate, lane hit rate, ticker; the rank owner stays domain/opportunity_rank.py (E11b);
- quality gate: survivors >= the governed share of the universe and at least one thesis GO.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "discovery_thesis_tier_v1.json"
TIER_LABELS = {0: "GO", 1: "READY_NOT_GO", 2: "WAITING", 3: "NO_ACTIVE_THESIS"}
_POLICY: Dict[str, Any] = {}


def tier_policy() -> Dict[str, Any]:
    if not _POLICY:
        _POLICY.update(json.loads(POLICY_PATH.read_text(encoding="utf-8-sig")))
    return dict(_POLICY)


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def thesis_tier(row: Mapping[str, Any]) -> Dict[str, Any]:
    from trigger_layer import thesis_go_eligibility
    go = thesis_go_eligibility(dict(row))
    readiness = go["thesis_readiness"]
    tier = 0 if go["go_eligible"] else 1 if readiness == "READY_FOR_HUMAN_REVIEW" else 2 if readiness == "WAIT_TRIGGER" else 3
    return {"tier": tier, "tier_label": TIER_LABELS[tier], "tier_basis": "THESIS_DISPOSITION_V1",
            "tier_reason": go["go_reason"]}


def discovery_win_probability(lane_fields: Mapping[str, Any]) -> Dict[str, Any]:
    rate = _num(lane_fields.get("setup_rate_within_hold"))
    if rate is None:
        return {"win_probability": None, "win_probability_basis": "NO_SETUP_RATE", "win_probability_n": None}
    return {"win_probability": rate, "win_probability_basis": "SETUP_RATE_WITHIN_HOLD_HELDOUT",
            "win_probability_n": lane_fields.get("setup_rate_n")}


def discovery_horizon(row: Mapping[str, Any]) -> Dict[str, Any]:
    from domain.anticipated_move import evidence_runway
    ev = evidence_runway(timeframe=row.get("thesis_event_timeframe"), alignment=row.get("thesis_structure_alignment"),
                         status=row.get("thesis_duration_status"), q50_bars=row.get("thesis_duration_q50_bars"),
                         q80_bars=row.get("thesis_duration_q80_bars"), n=row.get("thesis_duration_n"))
    hold = ev["evidence_runway_sessions"]
    if hold is None:
        bucket = "NO_EVIDENCE_HOLD"
    else:
        bucket = "1_5d" if hold <= 5 else "6_10d" if hold <= 10 else "11_20d" if hold <= 20 else "OVER_20d"
    return {"horizon_bucket": bucket, "horizon_hold_sessions": hold,
            "horizon_basis": ev["evidence_runway_basis"] or "NO_EVIDENCE_HOLD"}


def discovery_order(df: pd.DataFrame) -> pd.DataFrame:
    rate = pd.to_numeric(df.get("win_probability"), errors="coerce").fillna(-1.0)
    hit = pd.to_numeric(df.get("trade_lane_hit_holdout"), errors="coerce").fillna(-1.0)
    keyed = df.assign(_rate=rate, _hit=hit)
    return (keyed.sort_values(["tier", "_rate", "_hit", "ticker"], ascending=[True, False, False, True], kind="mergesort")
            .drop(columns=["_rate", "_hit"]))


def quality_issues(summary: Mapping[str, Any], policy: Optional[Mapping[str, Any]] = None) -> List[str]:
    pol = dict(tier_policy() if policy is None else policy)
    universe = int(summary.get("universe_size") or 0)
    survivors = int(summary.get("total_candidates") or 0)
    go = int(summary.get("thesis_go") or 0)
    issues: List[str] = []
    if universe <= 0:
        return ["Universe size is zero"]
    if survivors / universe < float(pol["min_candidate_ratio"]):
        issues.append(f"Too few candidates: {survivors} ({survivors / universe:.1%}) - expected at least "
                      f"{float(pol['min_candidate_ratio']):.0%} of the universe")
    if go < int(pol.get("min_thesis_go", 1)):
        issues.append(f"No thesis GO among {survivors} survivors - thesis readiness or geometry may be broken")
    return issues
