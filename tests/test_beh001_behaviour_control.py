"""BEH-001 L3-L4: behaviour per side, then who controls and how well.

Business rules:
- Repair is judged against structure: a reaction repairs a thrust only if it
  regains the thrust's origin. Retracement size is supporting evidence (F1).
- The current, unconfirmed leg counts for control (F2).
- Thrust comparisons use a tolerance band; tiny changes are UNCHANGED (F7).
- Acceptance needs persistence beyond a level, not a wick.
- Control is inferred from progress and retained ground, mirrored per side.
"""
import copy

from domain.structure_behaviour.behaviour import acceptance, compare_thrusts, assess_reaction
from domain.structure_behaviour.control import assess_control
from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.sequences import build_sequences, reflect_bars
from test_beh001_sequences import RANGE, TREND_DOWN, zigzag_bars

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20


def seq(points, **kw):
    return build_sequences(zigzag_bars(points, **kw), "1d", POLICY)


def test_lower_highs_and_lows_with_unrepaired_reactions_is_seller_control():
    result = assess_control(seq(TREND_DOWN), POLICY)
    assert result.controller == "SELLERS"
    assert result.transfer_level is not None
    assert result.thrust_count >= 3


def test_mirror_gives_buyer_control():
    bars = zigzag_bars(TREND_DOWN)
    mirrored = assess_control(build_sequences(reflect_bars(bars), "1d", POLICY), POLICY)
    assert mirrored.controller == "BUYERS"


def test_balanced_range_is_two_sided():
    assert assess_control(seq(RANGE), POLICY).controller == "TWO-SIDED"


def test_reaction_that_regains_the_thrust_origin_breaks_seller_control():
    # Down campaign, then a rally above the last lower high: repaired.
    result = assess_control(seq([100, 92, 96, 86, 90, 80, 84, 74, 92]), POLICY)
    assert result.controller != "SELLERS"


def test_current_leg_new_low_counts_before_its_pivot_is_confirmed():
    # Confirmed lows 88 -> 90 (higher low) but the live leg is already at 85.
    result = assess_control(seq([100, 88, 96, 90, 94, 85]), POLICY)
    assert result.controller == "SELLERS"
    assert "CURRENT_LEG" in result.evidence


def test_repair_is_structural_not_a_size_ratio():
    # A 73% retracement that stays below the thrust origin does not repair.
    reaction = assess_reaction(origin=18.71, thrust_end=16.53, reaction_extreme=17.96, thrust_direction="DOWN")
    assert reaction["state"] == "NOT_REPAIRED"
    assert 0.6 < reaction["retracement"] < 0.8
    full = assess_reaction(origin=18.71, thrust_end=16.53, reaction_extreme=18.90, thrust_direction="DOWN")
    assert full["state"] == "FULL_REPAIR"


def test_thrust_comparison_uses_a_tolerance_band():
    assert compare_thrusts(2.94, 3.01, POLICY) == "UNCHANGED"
    assert compare_thrusts(3.0, 2.0, POLICY) == "SHORTENING"
    assert compare_thrusts(2.0, 3.0, POLICY) == "LENGTHENING"


def test_acceptance_needs_persistence_not_a_wick():
    bars = zigzag_bars([100, 90, 100, 85, 86], bars_per_leg=6)
    result = build_sequences(bars, "1d", POLICY)
    state = acceptance(result, level=88.0, side="BELOW", from_index=0, policy=POLICY)
    assert state["state"] in {"ACCEPTED", "ACCEPTED_PROVISIONAL"}
    wick = bars.copy()
    wick.loc[len(wick) - 1, "low"] = 80.0  # one wick far below; closes stay above 89
    wick_seq = build_sequences(wick, "1d", POLICY)
    state = acceptance(wick_seq, level=82.0, side="BELOW", from_index=0, policy=POLICY)
    assert state["state"] == "NOT_CROSSED"
