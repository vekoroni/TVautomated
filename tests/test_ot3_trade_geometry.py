"""Output-trust item 3 (D2-3; ACK approved 9 Oct 2026, decision 1).

Root cause: the governing setup's failure level is a weekly/monthly campaign level (lane A median 8.8 daily ATR away)
while the target is the next outcome level (4.7 ATR): reward/risk 0.64 on the live book, never shown or tested.

Business rules:
- Geometry is measured from the PLANNED EXECUTABLE ENTRY: the session price for a ready thesis, the thesis trigger for
  a waiting one. Target and invalidation are the governing setup's own levels (never moved).
- Reward and risk are shown in price and in daily ATR(14); the early-warning level is a second, labelled risk view.
- Break-even hit rate = risk / (risk + reward), set against the setup's measured hit rate (the lower of the original and
  held-out panels) with its n and interval.
- GEOMETRY_NOT_JUSTIFIED when the measured rate is below break-even; INVALID_GEOMETRY when the order is broken or the
  risk or reward is not positive (never an infinite ratio). Neither can be GO; both stay visible and ranked.
- No measured hit rate (lane C) -> NOT_MEASURED, labelled, not blocked. Missing geometry is never neutral: GO needs it
  recorded.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from domain.trade_geometry import TRADE_GEOMETRY_FIELDS, assess_trade_geometry
from trigger_layer import thesis_go_eligibility

ROOT = Path(__file__).resolve().parents[1]
LANE = {"trade_lane_hit_original": 0.726, "trade_lane_hit_holdout": 0.678,
        "trade_lane_hit_n_original": 1071, "trade_lane_hit_n_holdout": 1099}


def _geo(**kw):
    base = dict(side="BULL", readiness="READY_FOR_HUMAN_REVIEW", session_price=100.0, trigger_level=104.0,
                target=110.0, invalidation=80.0, early_warning=95.0, atr_daily=2.0, lane=LANE)
    base.update(kw)
    return assess_trade_geometry(**base)


def test_a_ready_thesis_is_measured_from_the_session_price_in_price_and_atr():
    g = _geo()
    assert g["geometry_entry_basis"] == "SESSION_PRICE" and g["geometry_entry_price"] == 100.0
    assert (g["geometry_reward_price"], g["geometry_risk_price"]) == (10.0, 20.0)
    assert (g["geometry_reward_atr"], g["geometry_risk_atr"]) == (5.0, 10.0)
    assert g["geometry_early_warning_risk_atr"] == 2.5
    assert g["geometry_breakeven_hit_rate"] == pytest.approx(0.6667, abs=1e-4)
    # the lower panel is the measured rate, with its n and a 95% interval
    assert (g["geometry_measured_hit_rate"], g["geometry_hit_panel"], g["geometry_hit_n"]) == (0.678, "HOLDOUT", 1099)
    assert g["geometry_hit_low"] < 0.6667 < g["geometry_hit_high"]
    assert g["geometry_justification"] == "JUSTIFIED"
    assert "inside the interval" in g["geometry_reason"]


def test_a_far_invalidation_is_not_justified():
    g = _geo(invalidation=70.0)          # risk 30 vs reward 10 -> break-even 75% > measured 67.8%
    assert g["geometry_breakeven_hit_rate"] == 0.75
    assert g["geometry_justification"] == "GEOMETRY_NOT_JUSTIFIED"


def test_a_waiting_thesis_is_measured_from_its_trigger():
    g = _geo(readiness="WAIT_TRIGGER")
    assert g["geometry_entry_basis"] == "THESIS_TRIGGER" and g["geometry_entry_price"] == 104.0
    assert (g["geometry_reward_price"], g["geometry_risk_price"]) == (6.0, 24.0)
    assert g["geometry_justification"] == "GEOMETRY_NOT_JUSTIFIED"    # break-even 80%


def test_broken_order_is_invalid_never_an_infinite_ratio():
    g = _geo(invalidation=101.0)
    assert g["geometry_justification"] == "INVALID_GEOMETRY"
    assert g["geometry_breakeven_hit_rate"] is None
    bear = _geo(side="BEAR", target=90.0, invalidation=110.0, early_warning=None)
    assert bear["geometry_justification"] == "JUSTIFIED" and bear["geometry_reward_atr"] == 5.0


def test_lane_c_without_a_measured_rate_is_labelled_not_measured():
    g = _geo(lane={"trade_lane_hit_original": None, "trade_lane_hit_holdout": None})
    assert g["geometry_justification"] == "NOT_MEASURED"
    assert g["geometry_breakeven_hit_rate"] == pytest.approx(0.6667, abs=1e-4)


def test_missing_levels_are_not_assessable():
    assert _geo(target=None)["geometry_justification"] == "NOT_ASSESSABLE"
    assert _geo(side=None)["geometry_justification"] == "NOT_ASSESSABLE"
    assert _geo(readiness="WAIT_TRIGGER", trigger_level=None)["geometry_justification"] == "NOT_ASSESSABLE"


def test_go_needs_justified_geometry():
    ready = {"thesis__readiness": "READY_FOR_HUMAN_REVIEW"}
    assert thesis_go_eligibility({**ready, "geometry_justification": "JUSTIFIED"})["go_eligible"] is True
    assert thesis_go_eligibility({**ready, "geometry_justification": "NOT_MEASURED"})["go_eligible"] is True
    for state in ("GEOMETRY_NOT_JUSTIFIED", "INVALID_GEOMETRY"):
        out = thesis_go_eligibility({**ready, "geometry_justification": state})
        assert out["go_eligible"] is False and out["go_reason"] == state
    missing = thesis_go_eligibility(ready)
    assert missing["go_eligible"] is False and missing["go_reason"] == "GEOMETRY_NOT_RECORDED"


def test_the_fields_travel_with_the_thesis_and_the_lane_table_carries_n():
    from contracts.thesis_record import THESIS_SPINE_FIELDS
    from contracts.lab_control import FINAL_BOOK_FIELDS
    from domain.structure_behaviour.trade_lane import TRADE_LANE_FIELDS, load_lanes
    assert set(TRADE_GEOMETRY_FIELDS) <= set(THESIS_SPINE_FIELDS) <= set(FINAL_BOOK_FIELDS)
    assert {"trade_lane_hit_n_original", "trade_lane_hit_n_holdout"} <= set(TRADE_LANE_FIELDS)
    table = load_lanes()
    for lane in ("lane_a_trade_now", "lane_b_early_entry"):
        for tf, entries in table[lane].items():
            if isinstance(entries, list):
                assert all(len(e["n"]) == 2 and min(e["n"]) > 0 for e in entries), (lane, tf)
    src = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8")
    assert '"geometry_justification"' in src


def test_the_card_shows_the_geometry_block():
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "SMCI", "direction": "CALL", **_geo(invalidation=70.0)}
    out = subprocess.run(["node"], input=card + f"\nconst h = renderTradeCard({json.dumps(row)});\n"
                         "console.log(JSON.stringify({g: h.includes('Geometry'), r: h.includes('reward 10.00 (5.0 ATR)'),"
                         " k: h.includes('risk 30.00 (15.0 ATR)'), be: h.includes('break-even 75%'),"
                         " m: h.includes('measured 68% (n 1099'), s: h.includes('not justified')}));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"g": True, "r": True, "k": True, "be": True,
                                                               "m": True, "s": True}


def test_the_evening_bucket_names_a_geometry_refusal():
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from test_evening_thesis_decision import _row
    from domain.pretrade_focus import project_evening_thesis
    assert project_evening_thesis(_row(geometry_justification="JUSTIFIED"))["evening_thesis_bucket"] == "EOD_ACTION_SETUP_READY"
    for state in ("GEOMETRY_NOT_JUSTIFIED", "INVALID_GEOMETRY", None):
        out = project_evening_thesis(_row(geometry_justification=state, geometry_reason="measured 50% vs break-even 66%"))
        assert out["evening_thesis_bucket"] == "EOD_GEOMETRY_REVIEW", state
        assert out["evening_thesis_candidate"] is False


def test_the_morning_gate_names_a_geometry_refusal_not_a_missing_trigger():
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from test_morning_gate_authority import _gate, _row
    out = _gate(_row(trigger_go_eligible=False, trigger_go_reason="GEOMETRY_NOT_JUSTIFIED",
                     thesis__readiness="READY_FOR_HUMAN_REVIEW", geometry_breakeven_hit_rate=0.75,
                     geometry_measured_hit_rate=0.678, geometry_justification="GEOMETRY_NOT_JUSTIFIED"))
    assert out["verdict"] == "FLAG" and out["morning_entry_action"] == "NO_TRADE"
    assert out["morning_execution_permission"] == "GEOMETRY_NOT_JUSTIFIED"
    assert "break-even 75%" in out["morning_unlock_condition"] and "measured 68%" in out["morning_unlock_condition"]
    assert "Wait for the thesis trigger" not in out["morning_unlock_condition"]
