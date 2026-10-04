"""The Lab book carries EV3 at the planned hold and at the move window (ACK option 3, 28 Sep 2026).

The lead EV (ev_predicted) stays the planned-hold value; the move-window value is published beside it
under its own names so the page can show both. Nothing here changes a verdict, rank or permission.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MOVE_WINDOW_BOOK_FIELDS = {
    "ev3_hold_sessions": 20,
    "ev3_move_window_sessions": 5,
    "ev3_move_window_source": "HORIZON_BUCKET_ENDPOINT",
    "ev3_move_window_status": "EVALUATED",
    "ev3_move_window_reason_code": "",
    "ev3_move_window_ev_conservative_return": 0.05,
    "ev3_move_window_ev_lower_bound_return": -0.01,
    "ev3_move_window_p_target": 0.30,
    "ev3_move_window_p_stop": 0.40,
    "ev3_move_window_p_timeout": 0.30,
}


def test_book_carries_the_move_window_valuation_beside_the_hold_valuation():
    from contracts.lab_control import FINAL_BOOK_FIELDS, opportunity_book_row
    sig = {"ticker": "ABC", "final_direction": "CALL", "ev3_status": "EVALUATED_PRODUCTION_EVIDENCE",
           "ev3_ev_conservative_return": 0.12, **MOVE_WINDOW_BOOK_FIELDS}
    row = opportunity_book_row(sig, "RUN-T", 1)
    for field, value in MOVE_WINDOW_BOOK_FIELDS.items():
        assert field in FINAL_BOOK_FIELDS, field
        assert row[field] == value, field
    assert row["ev3_ev_conservative_return"] == 0.12
