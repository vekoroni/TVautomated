"""Morning gate respects trade lanes (ACK 5 Oct 2026, change 3).

Run 20261005_072245: 50 of 82 Morning GOs were lane C (no tested evidence that the setup reaches its level more
often than not). ACK: lanes are isolated, never mixed; lane C is watch-only and never shows a trade.
Business rules:
- Lane A can be GO (all other Morning checks still apply).
- Lane B can be GO only as confirmed by the evening payoff test (an unconfirmed B is already lane C in the book).
- Lane C is FLAG, watch-only (existing WATCH_ONLY permission vocabulary, so the Lab handoff reconciles), stated.
- A book without lanes (before 4 Oct) keeps today's behaviour and records that no lane was assigned.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_morning_gate_authority import _gate, _row


def _go_row(**kw):
    return _row(trigger_go_eligible=True, trigger_primary="VOL_COMPRESSION", candidate_status="TRIGGER_REQUIRED", **kw)


def test_lane_a_and_confirmed_lane_b_can_be_go():
    assert _gate(_go_row(trade_lane="A"))["verdict"] == "GO"
    assert _gate(_go_row(trade_lane="B"))["verdict"] == "GO"


def test_lane_c_is_watch_only_never_go():
    out = _gate(_go_row(trade_lane="C", trade_lane_basis="BELOW_LINE_OR_UNMEASURED"))
    assert out["verdict"] == "FLAG"
    assert out["morning_execution_permission"] == "WATCH_ONLY"
    assert out["morning_entry_action"] == "NO_TRADE"
    assert "TRADE_LANE_C_WATCH_ONLY" in out["flag_reason"]
    assert "BELOW_LINE_OR_UNMEASURED" in out["morning_unlock_condition"]


def test_book_without_lanes_keeps_behaviour_and_says_so():
    out = _gate(_go_row())
    assert out["verdict"] == "GO" and out["morning_trade_lane_rule"] == "LANE_NOT_ASSIGNED"
