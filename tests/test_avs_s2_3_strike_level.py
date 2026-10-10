"""S2-3 (ACK 6 Oct 2026, "approve ... #3"): strikes are chosen against the level the contract is valued at.

Run 20261006_060401: the target-reachability filter kept only strikes on the intrinsic side of structural_target -
the prior 40-bar range extreme relabelled DISCOVERY_TARGET - while the anticipated move valued the contract at the
governing setup's anticipated level; on 35 of 51 GOs the two differed by more than 1% (HPQ 36.23 vs 38.49).
Business rules:
- The strike filter level is the anticipated level at the median time (anticipated_level_q50) from the same
  domain function the EOD valuation uses, on the governing setup's thesis fields.
- No anticipated level: no reachability filter, stated (strike_filter_basis = NO_ANTICIPATED_LEVEL) - never a
  fallback to the range extreme.
- The range extreme is published as prior_range_extreme (supporting) and no longer selects strikes.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def oi():
    spec = importlib.util.spec_from_file_location("oi_s2_3", ROOT / "scripts" / "avshunter_options_intelligence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HPQ = {"thesis_outcome_level": 41.469697, "thesis_outcome_definition": "measured move",
       "thesis_event_timeframe": "1d", "thesis_structure_alignment": "ALIGNED",
       "thesis_duration_test": "OUTCOME", "thesis_duration_status": "IN_SAMPLE_REPLAY_NOT_VALIDATED",
       "thesis_duration_n": 300, "thesis_duration_q50_bars": 6, "thesis_duration_q80_bars": 12,
       "thesis_p_outcome_by_limit": 0.6, "thesis_p_invalidation_by_limit": 0.3}


def test_the_strike_level_is_the_level_the_contract_is_valued_at(oi):
    from domain.anticipated_move import anticipated_move_fields
    level, basis = oi.strike_selection_level(HPQ.get, "CALL", 31.47, 0.45, 12)
    expected = anticipated_move_fields(
        direction="CALL", spot=31.47, outcome_level=HPQ["thesis_outcome_level"], outcome_definition="measured move",
        timeframe="1d", duration={"test": "OUTCOME", "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "n": 300,
                                  "q50_bars": 6, "q80_bars": 12, "p_event": 0.6, "p_invalidation": 0.3},
        vol_annual=0.45, contract=None, governed_window_sessions=12, trade_side_event=True)["anticipated_level_q50"]
    assert level == pytest.approx(expected) and basis == "ANTICIPATED_LEVEL_Q50"


def test_no_anticipated_level_applies_no_filter_and_says_so(oi):
    level, basis = oi.strike_selection_level({}.get, "CALL", 31.47, None, 12)
    assert level is None and basis == "NO_ANTICIPATED_LEVEL"
    chain = pd.DataFrame({"strike": [30.0, 32.0, 40.0]})
    assert list(oi.filter_strikes_to_level(chain, None, "C", 31.47)["strike"]) == [30.0, 32.0, 40.0]


def test_strikes_are_filtered_against_the_level_not_the_range_extreme(oi):
    chain = pd.DataFrame({"strike": [30.0, 35.0, 37.0, 38.0, 40.0]})
    # anticipated level 38.49: a 37 or 38 strike has intrinsic value there; the range extreme (36.23) would drop them
    calls = oi.filter_strikes_to_level(chain, 38.49, "C", 31.47)
    assert list(calls["strike"]) == [30.0, 35.0, 37.0, 38.0]
    puts = oi.filter_strikes_to_level(pd.DataFrame({"strike": [40.0, 45.0, 50.0]}), 46.0, "P", 50.0)
    assert list(puts["strike"]) == [50.0]


def test_the_context_states_the_basis_and_keeps_the_range_extreme_as_supporting(oi):
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    assert "'strike_filter_level'" in src and "'strike_filter_basis'" in src and "'prior_range_extreme'" in src
    assert "structural_target = ctx.get('structural_target') or ctx.get('target_reachable')" not in src
