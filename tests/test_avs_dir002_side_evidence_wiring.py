"""DIR-002 §4.3 steps 4-9 and §4.5: kernel evidence reaches the Thesis rule.

Business rules:
- Only C3 per-side observations feed the assignment; macro, option, scanner
  and Vanguard values cannot (purity).
- Missing structure is typed and lowers observation quality; it never
  becomes support for a side.
- The policy is versioned configuration and fails closed when incomplete.
- Discovery writes one row per ticker with the Thesis-owned thesis__* fields,
  both candidate geometries, and legacy fields derived by the adapter.
- C3 structure modules never read thesis__* back (DEC-9).
"""
from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from contracts.direction_governance import (
    SideAssignmentPolicy,
    assign_thesis_side,
    load_side_assignment_policy,
    side_evidence_vectors,
)

ROOT = Path(__file__).resolve().parents[1]


def structure(bull_event="NONE", bear_event="NONE", bull_control=0.1, bear_control=0.1,
              status="EVALUATED", bull_trend=False, bear_trend=False, bars=260):
    def side(event, control, trend):
        return {
            "event_type": event, "event_strength": 0.75 if event not in {"NONE", "NOT_EVALUATED"} else 0.0,
            "event_session": "2026-09-25" if event != "NONE" else "", "control_score": control,
            "break_count": 0, "fail_back_count": 0, "failed_thrust_count": 0, "trend_aligned": trend,
        }
    return {
        "status": status, "policy_version": "dir002_side_evidence_v1",
        "trend_status": "EVALUATED" if bars >= 200 else "TREND_INSUFFICIENT_HISTORY",
        "trend_history_bars": bars, "phase_c_event_candidate": "NONE",
        "bull": side(bull_event, bull_control, bull_trend),
        "bear": side(bear_event, bear_control, bear_trend),
    }


def intent(value="WAIT", mode="UNKNOWN", status="EVALUATED", basis=None):
    if basis is None:
        basis = "EVENT" if value in {"BUY_SETUP", "SELL_SETUP"} else "NONE"
    return {"status": status, "intent": value, "mode": mode, "intent_basis": basis}


def test_spring_and_buy_intent_map_to_bull_support_only():
    bull, bear = side_evidence_vectors(structure("SPRING"), intent("BUY_SETUP", "ACCUMULATION"))
    assert bull.event_confirmed and bull.event_strength == 0.75
    assert bull.intent_supported and bull.mode_known
    assert not bear.event_confirmed and not bear.intent_supported
    assert bull.observation_quality == bear.observation_quality == 1.0


def test_unevaluated_structure_gives_no_support_and_lower_quality():
    bull, bear = side_evidence_vectors(structure(status="NOT_EVALUATED_INVALID_BARS"), intent())
    for vector in (bull, bear):
        assert not vector.event_confirmed
        assert vector.event_strength is None and vector.control_score is None
        assert math.isclose(vector.observation_quality, 1 / 3)


def test_vectors_mirror_when_inputs_mirror():
    a = side_evidence_vectors(structure("SPRING", bull_control=0.6, bear_control=0.2),
                              intent("BUY_SETUP", "ACCUMULATION"))
    b = side_evidence_vectors(structure(bear_event="UTAD", bull_control=0.2, bear_control=0.6),
                              intent("SELL_SETUP", "DISTRIBUTION"))
    assert a[0] == b[1] and a[1] == b[0]


def test_trend_only_chart_is_unassigned_with_context_side():
    policy = load_side_assignment_policy()
    bull, bear = side_evidence_vectors(structure(bull_trend=True), intent())
    result = assign_thesis_side(bull, bear, policy)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "TREND_ONLY"
    assert result["trend_context_side"] == "BULL"


def test_policy_is_versioned_and_fails_closed(tmp_path):
    policy = load_side_assignment_policy()
    assert isinstance(policy, SideAssignmentPolicy)
    assert policy.version == "side_assign_v1"
    raw = json.loads((ROOT / "config" / "dir002_side_assignment_v1.json").read_text(encoding="utf-8"))
    assert raw["calibration"]["status"] in {"PROVISIONAL_UNCALIBRATED", "CALIBRATED_CALIBRATION_WINDOW"}
    assert raw["production_direction_source"] in {"beh001_v1", "legacy_rollback"}
    broken = dict(raw)
    broken.pop("event_strength_min")
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError):
        load_side_assignment_policy(path)


def test_assignment_vector_builder_accepts_no_market_context_arguments():
    params = set(inspect.signature(side_evidence_vectors).parameters)
    assert params == {"structure", "intent"}


@pytest.mark.parametrize("module", ["WyckoffEngine_3101_v2.py", "wyckoff_crabel_precor_logic_v2.py",
                                    "wyckoff_phase_validator.py", "swing_fusion.py"])
def test_c3_structure_modules_never_read_the_thesis_back(module):
    assert "thesis__" not in (ROOT / module).read_text(encoding="utf-8")


@pytest.mark.parametrize("setup,side", [("BUY_SETUP", 0), ("SELL_SETUP", 1)])
def test_dec1_trend_phase_setup_is_context_not_structural_support(setup, side):
    vectors = side_evidence_vectors(structure(), intent(setup, "ACCUMULATION", basis="TREND_PHASE"))
    assert not vectors[side].intent_supported
    result = assign_thesis_side(*vectors, load_side_assignment_policy())
    assert result["thesis__side"] == "UNASSIGNED"
