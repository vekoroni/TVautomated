"""Fix Spec (Data Integrity Remediation, 24 Sep 2026) — Fix 1a and Fix 1 characterisation.

Business rules, stated for BOTH long calls and long puts:
- A governed structural target is on the thesis side of entry: a PUT target is never above
  entry, a CALL target is never below entry, whichever source supplied it (Fix 1a).
- The premium-appreciation R:R of a directional option is the intrinsic value at the
  governed target less the premium paid, per unit of premium; a strike beyond the target is
  a total loss at target (-1.0) and a target inside breakeven is a partial loss (-1 < rr < 0).
  Neither is a data defect; both are facts the row must be able to state (Fix 1b, adjusted).

Characterisation retired 24 Sep 2026 with Fix 1b (the row carried no state and floored an
unpriced mark to $0.01); the business rules live in tests/test_fixspec_rr_options_state.py.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.avshunter_options_intelligence import (  # noqa: E402
    _governed_structural_target, compute_trade_economics,
)


def _ctx(direction: str, entry: float, target: float, hold: int = 10) -> dict:
    return {"spot": entry, "entry": entry, "structural_target": target, "hold_days": hold,
            "direction": direction, "win_prob": 55.0}


def _contract(mark: float, strike: float, **extra) -> dict:
    return {"mark": mark, "strike": strike, "theta": -0.02, "vega": 0.05, "delta": 0.4, "dte": 30,
            "bid": round(mark * 0.95, 4), "ask": round(mark * 1.05, 4), **extra}


# ---------------------------------------------------------------- Fix 1a: target side per direction
@pytest.mark.parametrize("direction,entry,discovery,l1_far,stop_dist", [
    ("PUT", 100.0, 110.0, 120.0, None),        # every supplied level is on the wrong side
    ("PUT", 100.0, None, 105.0, None),         # L1 far above entry for a PUT
    ("CALL", 100.0, 90.0, 80.0, None),         # every supplied level below entry for a CALL
    ("CALL", 100.0, None, 95.0, None),
])
def test_wrong_side_levels_never_become_a_governed_target(direction, entry, discovery, l1_far, stop_dist):
    target, state = _governed_structural_target(direction, entry, discovery, l1_far, stop_dist)
    assert target is None
    assert state == "NO_TARGET_SOURCE"


@pytest.mark.parametrize("direction,entry,discovery,l1_far,stop_dist,expected_state", [
    ("PUT", 100.0, 80.0, None, None, "DISCOVERY_TARGET"),
    ("PUT", 100.0, None, 85.0, None, "L1_FAR"),
    ("CALL", 100.0, 120.0, None, None, "DISCOVERY_TARGET"),
    ("CALL", 100.0, None, 115.0, None, "L1_FAR"),
])
def test_governed_target_is_always_on_the_thesis_side(direction, entry, discovery, l1_far, stop_dist, expected_state):
    target, state = _governed_structural_target(direction, entry, discovery, l1_far, stop_dist)
    assert state == expected_state
    assert target is not None and target > 0
    if direction == "PUT":
        assert target < entry
    else:
        assert target > entry


def test_no_target_is_invented_from_the_stop_distance():
    # superseded 2 Oct 2026 (XLU-D01, ACK): the 3R fallback is a disclosure, never a target
    for args in (("PUT", 10.0, None, None, 4.0), ("PUT", 100.0, None, None, 4.0),
                 ("CALL", 100.0, None, None, 4.0), ("PUT", 100.0, 110.0, 120.0, 4.0)):
        assert _governed_structural_target(*args) == (None, "NO_STRUCTURAL_TARGET")


# ---------------------------------------------------------------- Fix 1: economics geometry per direction
@pytest.mark.parametrize("direction,entry,target,strike,mark,expected_sign", [
    ("CALL", 100.0, 120.0, 105.0, 2.0, 1),    # intrinsic 15 vs premium 2: gain
    ("PUT", 100.0, 80.0, 95.0, 2.0, 1),       # intrinsic 15 vs premium 2: gain
    ("CALL", 100.0, 106.0, 105.0, 2.0, -1),   # intrinsic 1 vs premium 2: partial loss, > -1
    ("PUT", 100.0, 94.0, 95.0, 2.0, -1),      # intrinsic 1 vs premium 2: partial loss, > -1
])
def test_priced_directional_rr_has_the_sign_its_geometry_implies(direction, entry, target, strike, mark, expected_sign):
    econ = compute_trade_economics(_contract(mark, strike), _ctx(direction, entry, target), {"ivp_label": "FAIR"})
    assert econ["economics_state"] == "EVALUATED"
    rr = econ["rr_options"]
    assert math.copysign(1, rr) == expected_sign
    assert rr > -1.0


@pytest.mark.parametrize("direction,entry,target,strike", [
    ("CALL", 100.0, 104.0, 105.0),   # strike above a CALL target: worthless at target
    ("PUT", 100.0, 96.0, 95.0),      # strike below a PUT target: worthless at target
])
def test_strike_beyond_target_is_a_total_loss_at_target_for_either_direction(direction, entry, target, strike):
    econ = compute_trade_economics(_contract(2.0, strike), _ctx(direction, entry, target), {"ivp_label": "FAIR"})
    assert econ["rr_options"] == -1.0
    assert econ["option_value_at_target"] == 0

