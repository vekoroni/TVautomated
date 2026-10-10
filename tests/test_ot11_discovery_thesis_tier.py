"""Output-trust item 11 (D2-1 Step B, Discovery station; ACK approved D11-1..4, 10 Oct 2026).

Today Discovery's tier, order and win probability come from the legacy Wyckoff/Crabel composite: the tier says
nothing about the thesis (8 Oct: 691 "tier 0 early positions" still wait for their trigger, 203 have no active
thesis), 98% of rows are tier 0/1 and so labelled horizon 1_5d, and win_probability is a rescaled composite (50-62).

Business rules (switch config/discovery_thesis_tier_v1.json, tier_source thesis_v1 | legacy_composite):
- Tier is the thesis disposition: 0 GO (the trigger layer's own GO rule), 1 READY_NOT_GO, 2 WAITING (adopted, waiting
  for its trigger), 3 NO_ACTIVE_THESIS. No ticker is dropped on the legacy composite.
- Order within tier: the setup's held-out within-hold rate, then its lane hit rate, then ticker.
- win_probability is the setup's held-out within-hold rate, null (NO_SETUP_RATE) when the setup has none - never the
  composite; the Vanguard bridge never clamps it or relabels it as a 5/10/20-day rate.
- The horizon label comes from the setup's evidence hold (1_5d / 6_10d / 11_20d / OVER_20d / NO_EVIDENCE_HOLD).
- Quality gate: survivors >= the governed share of the universe and at least one thesis GO.
- legacy_composite gives today's behaviour (rollback).
"""
from __future__ import annotations

import inspect

import pandas as pd

from domain.thesis_tier import (discovery_horizon, discovery_order, discovery_win_probability, quality_issues,
                                thesis_tier, tier_policy)


def test_tier_is_the_thesis_disposition():
    assert thesis_tier({"thesis__readiness": "READY_FOR_HUMAN_REVIEW", "geometry_justification": "JUSTIFIED"})["tier"] == 0
    assert thesis_tier({"thesis__readiness": "READY_FOR_HUMAN_REVIEW", "geometry_justification": "NOT_MEASURED"})["tier"] == 0
    refused = thesis_tier({"thesis__readiness": "READY_FOR_HUMAN_REVIEW", "geometry_justification": "GEOMETRY_NOT_JUSTIFIED"})
    assert (refused["tier"], refused["tier_label"]) == (1, "READY_NOT_GO")
    assert thesis_tier({"thesis__readiness": "READY_FOR_HUMAN_REVIEW"})["tier"] == 1        # unrecorded geometry
    waiting = thesis_tier({"thesis__readiness": "WAIT_TRIGGER", "geometry_justification": "JUSTIFIED"})
    assert (waiting["tier"], waiting["tier_label"]) == (2, "WAITING")
    for readiness in ("NOT_ADOPTED", "CLOSED_INVALIDATED", None):
        out = thesis_tier({"thesis__readiness": readiness})
        assert (out["tier"], out["tier_label"]) == (3, "NO_ACTIVE_THESIS")
    assert waiting["tier_basis"] == "THESIS_DISPOSITION_V1"


def test_win_probability_is_the_measured_setup_rate_or_null():
    rate = discovery_win_probability({"setup_rate_within_hold": 0.58, "setup_rate_n": 1099})
    assert rate == {"win_probability": 0.58, "win_probability_basis": "SETUP_RATE_WITHIN_HOLD_HELDOUT",
                    "win_probability_n": 1099}
    none = discovery_win_probability({"setup_rate_within_hold": None})
    assert none["win_probability"] is None and none["win_probability_basis"] == "NO_SETUP_RATE"


def test_horizon_label_comes_from_the_evidence_hold():
    row = {"thesis_event_timeframe": "1d", "thesis_structure_alignment": "ALIGNED", "thesis_duration_status": "VALIDATED",
           "thesis_duration_q50_bars": 3, "thesis_duration_q80_bars": 8, "thesis_duration_n": 400}
    assert discovery_horizon(row)["horizon_bucket"] == "6_10d"
    assert discovery_horizon({**row, "thesis_duration_q80_bars": 4})["horizon_bucket"] == "1_5d"
    assert discovery_horizon({**row, "thesis_duration_q80_bars": 30})["horizon_bucket"] == "OVER_20d"
    weekly = discovery_horizon({**row, "thesis_event_timeframe": "1w", "thesis_duration_q80_bars": 3})
    assert (weekly["horizon_bucket"], weekly["horizon_hold_sessions"]) == ("11_20d", 15)
    missing = discovery_horizon({**row, "thesis_duration_status": None})
    assert missing["horizon_bucket"] == "NO_EVIDENCE_HOLD" and missing["horizon_basis"]


def test_order_within_tier_by_setup_rate_then_lane_hit_then_ticker():
    df = pd.DataFrame([
        {"ticker": "ZZZ", "tier": 0, "win_probability": 0.40, "trade_lane_hit_holdout": 0.7},
        {"ticker": "AAA", "tier": 0, "win_probability": 0.40, "trade_lane_hit_holdout": 0.7},
        {"ticker": "BBB", "tier": 0, "win_probability": 0.60, "trade_lane_hit_holdout": 0.5},
        {"ticker": "CCC", "tier": 2, "win_probability": 0.90, "trade_lane_hit_holdout": 0.9},
        {"ticker": "DDD", "tier": 0, "win_probability": None, "trade_lane_hit_holdout": 0.9},
    ])
    assert discovery_order(df)["ticker"].tolist() == ["BBB", "AAA", "ZZZ", "DDD", "CCC"]


def test_quality_gate_needs_survivors_and_one_thesis_go():
    policy = {"min_candidate_ratio": 0.15}
    ok = {"universe_size": 3325, "total_candidates": 2933, "thesis_go": 528}
    assert quality_issues(ok, policy) == []
    assert any("GO" in i for i in quality_issues({**ok, "thesis_go": 0}, policy))
    assert any("candidates" in i for i in quality_issues({**ok, "total_candidates": 100}, policy))


def test_the_switch_is_governed_and_discovery_reads_it():
    assert tier_policy()["tier_source"] == "thesis_v1"
    import avshunter_discovery_ULTIMATE as disc
    src = inspect.getsource(disc)
    assert "thesis_tier(" in src and "discovery_win_probability(" in src and "discovery_horizon(" in src
    assert "discovery_order(" in src
    scan = inspect.getsource(disc.scan_ticker_ultimate)
    # the legacy tier-4 drop runs only on the rollback path
    assert 'if _legacy_tier and tier == 4 and not early_signal' in scan


def test_the_orchestrator_gate_reads_the_thesis_summary():
    import intelligent_orchestrator
    src = inspect.getsource(intelligent_orchestrator.validate_quality)
    assert "quality_issues(" in src and "tier_source" in src


def test_the_vanguard_bridge_never_clamps_a_measured_setup_rate():
    src = open("scripts/run_vanguard_from_packages.py", encoding="utf-8").read()
    assert "SETUP_RATE_WITHIN_HOLD_HELDOUT" in src
