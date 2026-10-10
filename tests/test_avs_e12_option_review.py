"""E12 (ACK 6 Oct 2026, "Yes"): an option with no computed value is an option-review FLAG, never a plain GO.

Run 20261006_060401: 7 Morning GOs had no computed option value (6 NOT_COMPUTED, 1 volatility-only: NET), so their
cards could not answer "does the move pay". The Morning gate withheld GO only for DOES_NOT_PAY_AT_ANTICIPATED_TIME
("NOT_COMPUTED does not block on its own") - a missing value read as neutral (R1).
Business rules:
- NOT_COMPUTED -> FLAG, option review, reason OPTION_VALUE_NOT_COMPUTED.
- NOT_ASSESSED_VOLATILITY_ONLY -> FLAG, option review, reason OPTION_VALUE_VOLATILITY_ONLY (fix B: not a verdict).
- The ticker assessment is unchanged: the row stays in the book with its lane, direction and setup (E02: the
  option expresses the ticker, a missing option value does not erase it).
- PAYS stays GO; DOES_NOT_PAY stays its own FLAG.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_morning_gate_authority import _gate, _row  # noqa: E402


def _go_row(**kw):
    return _row(trigger_go_eligible=True, trigger_primary="VOL_COMPRESSION", candidate_status="TRIGGER_REQUIRED",
                trade_lane="A", **kw)


@pytest.mark.parametrize("state,reason", [("NOT_COMPUTED", "OPTION_VALUE_NOT_COMPUTED"),
                                          ("NOT_ASSESSED_VOLATILITY_ONLY", "OPTION_VALUE_VOLATILITY_ONLY")])
def test_an_option_without_a_computed_value_is_an_option_review_flag(state, reason):
    out = _gate(_go_row(anticipated_pays_state=state))
    assert out["verdict"] == "FLAG"
    assert out["morning_execution_permission"] == "OPTION_REVIEW"
    assert reason in out["flag_reason"]
    assert out["morning_entry_action"] == "MANUAL_REVIEW"


def test_the_ticker_assessment_is_kept():
    out = _gate(_go_row(anticipated_pays_state="NOT_COMPUTED"))
    assert out.get("trade_lane", "A") == "A"
    assert "ticker assessment is unchanged" in out["morning_unlock_condition"]


def test_a_paying_option_is_still_go_and_does_not_pay_keeps_its_own_flag():
    assert _gate(_go_row(anticipated_pays_state="PAYS"))["verdict"] == "GO"
    out = _gate(_go_row(anticipated_pays_state="DOES_NOT_PAY_AT_ANTICIPATED_TIME"))
    assert out["verdict"] == "FLAG" and "MOVE_DOES_NOT_PAY_AT_ANTICIPATED_TIME" in out["flag_reason"]
