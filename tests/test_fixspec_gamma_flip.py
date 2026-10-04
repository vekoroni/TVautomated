"""Fix Spec Fix 4 (decision D4 approved 24 Sep 2026): the gamma flip is a re-priced crossing near spot.

Business rules:
- Dealer gamma exposure is re-priced on a grid of hypothetical spot levels around spot
  (calls positive, puts negative, each contract's own IV and expiry); the flip is the level
  nearest spot where the total changes sign, interpolated between grid points.
- No crossing within the grid means no flip: None with a state that says so, never a
  fallback strike. Insufficient chain data (no IV, no open interest) is stated too.
- The legacy value (first per-strike sign change scanning from the lowest strike) is kept
  for one release under its own name so consumers can be re-measured against it.

Characterisation retired 24 Sep 2026 with the fix: the flip was the first per-strike sign change
scanning from the lowest strike (a deep out-of-the-money strike), and with no crossing the
smallest-|GEX| strike was used (GEX investigation GEX-D1, 14 Sep 2026).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402

SCRIPT = ROOT / "scripts" / "avshunter_options_intelligence.py"
SPOT = 100.0


def _row(right, strike, oi_, iv=0.30, dte=30):
    T = dte / 365.0
    gamma = oi.bs_gamma(SPOT, strike, T, iv)
    return {"right": right, "strike": strike, "open_interest": oi_, "implied_vol": iv, "dte": dte,
            "gamma": gamma if gamma is not None else 0.0}


def _chain(rows):
    return pd.DataFrame(rows)


# Puts carry the open interest below spot, calls above it, and one tiny deep out-of-the-money
# call sits at the lowest strike: the legacy scan flips there, far from spot.
BALANCED = _chain([
    _row("C", 50.0, 5), _row("P", 90.0, 1000), _row("P", 95.0, 1000),
    _row("C", 105.0, 1000), _row("C", 110.0, 1000),
])
CALLS_ONLY = _chain([_row("C", 105.0, 800), _row("C", 110.0, 600), _row("C", 120.0, 300)])


# ------------------------------------------------------------------ re-priced profile
def test_dealer_gamma_profile_is_signed_by_side_and_repriced_on_a_grid_around_spot():
    grid, totals = oi.dealer_gamma_profile(BALANCED, SPOT)
    assert grid[0] == pytest.approx(SPOT * (1 - oi.GAMMA_FLIP_GRID_HALF_WIDTH))
    assert grid[-1] == pytest.approx(SPOT * (1 + oi.GAMMA_FLIP_GRID_HALF_WIDTH))
    assert len(grid) == len(totals) and np.all(np.diff(grid) > 0)
    assert totals[0] < 0                                            # far below spot: puts dominate
    assert totals[-1] > 0                                           # far above spot: calls dominate
    puts_only = _chain([_row("P", 90.0, 1000), _row("P", 95.0, 1000)])
    assert np.all(oi.dealer_gamma_profile(puts_only, SPOT)[1] <= 0)


def test_flip_is_the_crossing_nearest_spot_not_a_deep_out_of_the_money_strike():
    result = oi.compute_gamma_flip(BALANCED, SPOT)
    assert result["gamma_flip_state"] == "GRID_REPRICED_CROSSING"
    assert result["gamma_flip_method"] == oi.GAMMA_FLIP_METHOD
    assert abs(result["gamma_flip"] - SPOT) / SPOT < 0.10
    assert result["gamma_flip_legacy_first_sign_change"] < 90.0    # the old answer, kept by name


def test_no_crossing_is_none_with_a_state_never_a_fallback_strike():
    result = oi.compute_gamma_flip(CALLS_ONLY, SPOT)
    assert result["gamma_flip"] is None
    assert result["gamma_flip_state"] == "NO_GEX_CROSSING_WITHIN_GRID"
    assert result["gamma_flip_legacy_first_sign_change"] in (105.0, 110.0, 120.0)


@pytest.mark.parametrize("chain", [
    _chain([]),
    _chain([{"right": "C", "strike": 105.0, "open_interest": 100, "gamma": 0.01}]),          # no IV / expiry
    _chain([_row("C", 105.0, 0), _row("P", 95.0, 0)]),                                          # no open interest
])
def test_insufficient_chain_data_is_stated(chain):
    result = oi.compute_gamma_flip(chain, SPOT)
    assert result["gamma_flip"] is None
    assert result["gamma_flip_state"] == "INSUFFICIENT_CHAIN_DATA"


def test_compute_gex_publishes_the_repriced_flip_and_no_confidence_without_one():
    gex_df, flip, conf = oi.compute_gex(BALANCED, SPOT)
    assert abs(flip - SPOT) / SPOT < 0.10
    assert list(gex_df.columns) == ["strike", "gex"]                # per-strike surface unchanged
    _, none_flip, none_conf = oi.compute_gex(CALLS_ONLY, SPOT)
    assert none_flip is None and none_conf == 0.0


def test_engine_publishes_state_method_and_legacy_and_has_no_fallback_strike():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "flip = float(x[np.argmin(np.abs(y))])" not in source
    for key in ("gamma_flip_state", "gamma_flip_method", "gamma_flip_legacy_first_sign_change"):
        assert source.count(f"'{key}'") >= 3, key                    # two row projections + CSV export
