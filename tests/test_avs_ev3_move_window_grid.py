"""EV3 move-window value uses the grid rule of decision 1a (ACK 5 Oct 2026, change 6).

Run 20261005_072245: 11 of the 12 handoff rows carried ev3_move_window_reason_code
REJECT_BARRIER_HORIZON_UNAVAILABLE - the evidence move window (e.g. 13 sessions) is not one of EV3's grid
horizons (5/10/20), and the rejection read as a defect rather than a known limit.
Business rules:
- The move window is valued at the nearest grid point at or below it, with its basis (EV3_GRID_10_OF_13).
- A window below the grid is NOT_EVALUATED with reason BELOW_EV3_GRID_n; the hold value is never borrowed.
"""
from vanguard.ev_engine_v3 import _move_window_fields


class _Cache:
    def __init__(self):
        self.horizons = []

    def lookup(self, state_key, direction, horizon_sessions, target, stop):
        self.horizons.append(horizon_sessions)
        return None, "TEST_STOP", "stop after recording the horizon"


def _c(window, hold=20):
    return {"planned_hold_sessions": hold, "move_window_sessions": window, "move_window_source": "anticipated",
            "state_key": "S", "canonical_direction": "CALL", "target_distance_fraction": 0.05,
            "stop_distance_fraction": 0.03}


def test_move_window_is_valued_at_the_nearest_grid_point_below_it():
    cache = _Cache()
    fields = _move_window_fields(_c(13), cache, value_at=None, hold_value={})
    assert cache.horizons == [10]
    assert fields["ev3_move_window_grid_basis"] == "EV3_GRID_10_OF_13"


def test_move_window_below_the_grid_is_not_evaluated_and_says_why():
    cache = _Cache()
    fields = _move_window_fields(_c(3), cache, value_at=None, hold_value={})
    assert cache.horizons == []
    assert fields["ev3_move_window_status"] == "NOT_EVALUATED"
    assert fields["ev3_move_window_reason_code"] == "BELOW_EV3_GRID_3"
