"""Unvaluable thesis geometry is labelled for manual review, never defaulted (ACK, 19 Sep 2026).

Evidence (run 20260918_112522): 211 of 1,352 selected contracts could not be valued because the thesis had no
usable stop or target.
- 163 rows: the governed direction contradicts the Wyckoff structure (CALL in DISTRIBUTION, PUT in
  ACCUMULATION), so the structural invalidation (40-session extreme) lies on the wrong side and no stop exists.
- 42 rows: a PUT whose stop (the 40-session high) is so far above price that entry - 3 x stop distance is not
  positive, so no target exists.
Labels only: no stop or target is invented, no row is removed, nothing is gated.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import avshunter_options_intelligence as oi


def _ctx(direction: str, mode: str, *, entry: float = 100.0, stop: float | None = 95.0,
         target: float | None = 115.0, target_state: str = "TARGET_3R") -> dict:
    return {"direction": direction, "entry": entry, "stop": stop, "structural_target": target,
            "structural_target_state": target_state, "_signal_row": {"wyckoff_mode": mode}}


@pytest.mark.parametrize("direction,mode", [("CALL", "DISTRIBUTION"), ("PUT", "ACCUMULATION")])
def test_direction_against_the_wyckoff_structure_is_labelled_for_review(direction, mode):
    review = oi.thesis_geometry_review(_ctx(direction, mode, stop=None, target=None,
                                            target_state="NO_TARGET_SOURCE"))
    assert review["thesis_geometry_review_state"] == "DIRECTION_CONTRADICTS_STRUCTURE"
    assert direction in review["thesis_geometry_review_reason"] and mode in review["thesis_geometry_review_reason"]


def test_a_put_whose_stop_is_too_distant_for_a_target_is_labelled_for_review():
    review = oi.thesis_geometry_review(_ctx("PUT", "DISTRIBUTION", entry=10.0, stop=14.4, target=None,
                                            target_state="TARGET_3R_NON_POSITIVE"))
    assert review["thesis_geometry_review_state"] == "STOP_TOO_DISTANT_NO_TARGET"
    assert "44.0%" in review["thesis_geometry_review_reason"]


@pytest.mark.parametrize("direction,mode", [("CALL", "ACCUMULATION"), ("PUT", "DISTRIBUTION")])
def test_consistent_complete_geometry_is_labelled_complete(direction, mode):
    stop, target = (95.0, 115.0) if direction == "CALL" else (105.0, 85.0)
    review = oi.thesis_geometry_review(_ctx(direction, mode, stop=stop, target=target))
    assert review["thesis_geometry_review_state"] == "COMPLETE"


def test_other_missing_geometry_is_reported_by_what_is_missing():
    assert oi.thesis_geometry_review(_ctx("CALL", "ACCUMULATION", stop=None, target=None,
                                          target_state="NO_TARGET_SOURCE"))[
        "thesis_geometry_review_state"] == "MISSING_STOP"
    assert oi.thesis_geometry_review(_ctx("CALL", "ACCUMULATION", target=None, target_state="NO_TARGET_SOURCE"))[
        "thesis_geometry_review_state"] == "MISSING_TARGET"


def test_a_missing_wyckoff_mode_is_not_read_as_agreement():
    review = oi.thesis_geometry_review(_ctx("CALL", "", stop=None, target=None, target_state="NO_TARGET_SOURCE"))
    assert review["thesis_geometry_review_state"] == "MISSING_STOP"
    assert "wyckoff_mode=UNKNOWN" in review["thesis_geometry_review_reason"]


def test_non_directional_rows_are_not_applicable():
    review = oi.thesis_geometry_review(_ctx("STRANGLE", "DISTRIBUTION", stop=None, target=None))
    assert review["thesis_geometry_review_state"] == "NOT_APPLICABLE_NON_DIRECTIONAL"


def test_every_output_branch_and_the_lab_book_carry_the_label():
    from contracts.lab_control import FINAL_BOOK_FIELDS
    row = pd.Series({"ticker": "BZ", "direction": "CALL", "current_price": 20.0, "wyckoff_mode": "DISTRIBUTION",
                     "wyckoff_validation_structural_invalidation_level": 24.0})
    ctx = oi.parse_structural_context(row)
    ctx.update({"_signal_row": row, "direction": "CALL"})    # governed direction as Discovery would supply it
    stand_down = oi._stand_down(ctx, "replay")
    assert stand_down["thesis_geometry_review_state"] == "DIRECTION_CONTRADICTS_STRUCTURE"
    for field in ("thesis_geometry_review_state", "thesis_geometry_review_reason"):
        assert field in FINAL_BOOK_FIELDS
