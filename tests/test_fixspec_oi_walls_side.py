"""Fix Spec Fix 3 (decision D3 approved 24 Sep 2026): walls are side-constrained by spot.

Business rules:
- `call_wall` is the strike above spot carrying the most call open interest; `put_wall` is the
  strike below spot carrying the most put open interest. A wall that does not exist on its side
  is None with a state that says why; a wall is never published on the wrong side of spot.
- The raw per-side maxima the old definition published are kept under their own names
  (`oi_max_call_strike`, `oi_max_put_strike`) so nothing is lost and history stays comparable.
- Without a spot, no side can be judged: both walls are None with state SPOT_UNAVAILABLE.
- `max_pain` is unchanged.

Characterisation retired 24 Sep 2026 with the fix: both walls were unconstrained per-side maxima, so
the same strike could be both (96 of 1,550 rows on 20260922_223221) and 558 of 1,379 walls sat on the
wrong side of spot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402

SCRIPT = ROOT / "scripts" / "avshunter_options_intelligence.py"


def _chain(rows):
    return pd.DataFrame(rows, columns=["right", "strike", "open_interest"])


# The thin chain seen on run 20260922_223221 (REAX-like): most OI on one strike, both sides.
THIN = _chain([
    ("C", 15.0, 40), ("C", 17.5, 60), ("C", 20.0, 900), ("C", 22.5, 300),
    ("P", 15.0, 50), ("P", 17.5, 80), ("P", 20.0, 700), ("P", 22.5, 20),
])
SPOT = 17.13


# ------------------------------------------------------------------ side-constrained walls
def test_walls_are_the_strongest_strike_on_their_own_side_of_spot():
    walls = oi.compute_oi_walls(THIN, spot=SPOT)
    assert walls["call_wall"] == 20.0 and walls["call_wall_state"] == "OI_MAX_ABOVE_SPOT"
    assert walls["put_wall"] == 15.0 and walls["put_wall_state"] == "OI_MAX_BELOW_SPOT"
    assert walls["call_wall"] > SPOT > walls["put_wall"]
    assert walls["oi_max_call_strike"] == 20.0 and walls["oi_max_put_strike"] == 20.0   # raw maxima kept
    assert walls["max_pain"] == oi.compute_oi_walls(THIN)["max_pain"]                    # unchanged


def test_a_side_with_no_strike_beyond_spot_has_no_wall_and_says_so():
    only_below = _chain([("C", 10.0, 500), ("P", 10.0, 400), ("P", 12.0, 100)])
    walls = oi.compute_oi_walls(only_below, spot=15.0)
    assert walls["call_wall"] is None and walls["call_wall_state"] == "NO_STRIKE_ABOVE_SPOT"
    assert walls["put_wall"] == 10.0 and walls["put_wall_state"] == "OI_MAX_BELOW_SPOT"
    only_above = _chain([("C", 20.0, 500), ("P", 20.0, 400)])
    walls = oi.compute_oi_walls(only_above, spot=15.0)
    assert walls["put_wall"] is None and walls["put_wall_state"] == "NO_STRIKE_BELOW_SPOT"
    assert walls["call_wall"] == 20.0


def test_a_strike_at_spot_belongs_to_neither_side():
    at_spot = _chain([("C", 15.0, 900), ("C", 16.0, 10), ("P", 15.0, 900), ("P", 14.0, 10)])
    walls = oi.compute_oi_walls(at_spot, spot=15.0)
    assert walls["call_wall"] == 16.0 and walls["put_wall"] == 14.0


def test_zero_open_interest_on_a_side_is_no_wall_not_a_zero_strike():
    empty_side = _chain([("C", 20.0, 0), ("C", 22.0, 0), ("P", 12.0, 300)])
    walls = oi.compute_oi_walls(empty_side, spot=15.0)
    assert walls["call_wall"] is None and walls["call_wall_state"] == "NO_OPEN_INTEREST_ABOVE_SPOT"
    assert walls["put_wall"] == 12.0


@pytest.mark.parametrize("spot", [None, 0.0, -1.0, float("nan")])
def test_without_a_spot_no_side_can_be_judged(spot):
    walls = oi.compute_oi_walls(THIN, spot=spot)
    assert walls["call_wall"] is None and walls["put_wall"] is None
    assert walls["call_wall_state"] == walls["put_wall_state"] == "SPOT_UNAVAILABLE"
    assert walls["oi_max_call_strike"] == 20.0 and walls["oi_max_put_strike"] == 20.0


def test_empty_chain_publishes_typed_absence():
    walls = oi.compute_oi_walls(_chain([]), spot=15.0)
    assert walls["call_wall"] is None and walls["put_wall"] is None and walls["max_pain"] is None
    assert walls["call_wall_state"] == walls["put_wall_state"] == "NO_CHAIN_DATA"


def test_engine_passes_spot_and_publishes_states_and_raw_maxima():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "walls = compute_oi_walls(chain, spot)" in source
    assert "walls = compute_oi_walls(chain)" not in source
    for key in ("call_wall_state", "put_wall_state", "oi_max_call_strike", "oi_max_put_strike"):
        assert source.count(f"'{key}'") >= 3, key          # two row projections + CSV export
