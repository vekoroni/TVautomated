"""DIR-002 §4.4: structural support assigns direction; trend alone never does."""

from dataclasses import fields

import pytest

from contracts.direction_governance import (
    SideAssignmentPolicy,
    SideStructuralEvidence,
    assign_thesis_side,
)


POLICY = SideAssignmentPolicy(
    version="side_assign_v1_test",
    event_strength_min=0.60,
    control_margin_min=0.20,
    control_full_scale=0.80,
    contested_margin=0.15,
    min_observation_quality=0.65,
    trend_min_bars=200,
)


def ev(**overrides):
    values = {
        "event_confirmed": False,
        "event_strength": None,
        "control_score": None,
        "intent_supported": False,
        "mode_known": False,
        "intent_transition": False,
        "trend_aligned": False,
        "trend_history_bars": None,
        "observation_quality": None,
    }
    values.update(overrides)
    return SideStructuralEvidence(**values)


def test_missing_evidence_never_defaults_to_bull_or_bear():
    result = assign_thesis_side(ev(), ev(), POLICY)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "TREND_INSUFFICIENT_HISTORY"


@pytest.mark.parametrize("side", ["BULL", "BEAR"])
def test_one_confirmed_event_is_single_source_structure(side):
    supported = ev(event_confirmed=True, event_strength=0.8)
    bull, bear = (supported, ev()) if side == "BULL" else (ev(), supported)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == side
    assert result["thesis__direction_status"] == "SINGLE_SOURCE_STRUCTURE"
    assert result["thesis__evidence_independence"] == "SINGLE_FAMILY_OHLC"


def test_two_structure_types_confirm_without_counting_trend_as_second_type():
    bull = ev(event_confirmed=True, event_strength=0.8, control_score=0.85)
    bear = ev(control_score=0.25, trend_aligned=True, trend_history_bars=220)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "BULL"
    assert result["thesis__direction_status"] == "CONFIRMED_STRUCTURE"
    assert result["bull_support_types"] == ["EVENT", "CONTROL"]
    assert result["bear_support_types"] == []


@pytest.mark.parametrize("side", ["BULL", "BEAR"])
def test_dec1_trend_alone_is_visible_but_unassigned(side):
    trend = ev(trend_aligned=True, trend_history_bars=220)
    bull, bear = (trend, ev(trend_history_bars=220)) if side == "BULL" else (ev(trend_history_bars=220), trend)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "TREND_ONLY"
    assert result["thesis__unassigned_reason"] == "TREND_ONLY"
    assert result["trend_context_side"] == side


def test_opposing_structure_is_not_an_automatic_veto():
    bull = ev(event_confirmed=True, event_strength=0.95, observation_quality=0.9)
    bear = ev(event_confirmed=True, event_strength=0.65, observation_quality=0.9)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "BULL"
    assert result["thesis__direction_status"] == "CONTESTED_DIRECTION"
    assert result["bear_support_types"] == ["EVENT"]


def test_true_tie_is_unassigned_conflict():
    bull = ev(event_confirmed=True, event_strength=0.8, observation_quality=0.9)
    bear = ev(event_confirmed=True, event_strength=0.8, observation_quality=0.9)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "CONFLICT_REVIEW"


def test_unmeasured_quality_does_not_create_a_contested_winner():
    bull = ev(event_confirmed=True, event_strength=0.95)
    bear = ev(event_confirmed=True, event_strength=0.65)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "CONFLICT_REVIEW"


def test_mixed_transition_is_unassigned_with_explicit_reason():
    bull = ev(intent_transition=True, trend_history_bars=220)
    bear = ev(intent_transition=True, trend_history_bars=220)
    result = assign_thesis_side(bull, bear, POLICY)
    assert result["thesis__side"] == "UNASSIGNED"
    assert result["thesis__direction_status"] == "TRANSITION_MIXED_TREND"


def test_assignment_inputs_have_no_macro_option_vanguard_or_geometry_fields():
    names = {field.name for field in fields(SideStructuralEvidence)}
    assert not names.intersection({"macro", "option", "vanguard", "scanner", "geometry_valid", "target", "invalidation"})


def test_missing_policy_value_fails_closed():
    with pytest.raises(ValueError):
        SideAssignmentPolicy(
            version="side_assign_v1_test",
            event_strength_min=None,
            control_margin_min=0.20,
            control_full_scale=0.80,
            contested_margin=0.15,
            min_observation_quality=0.65,
            trend_min_bars=200,
        )


def test_mirror_swaps_assigned_side_and_keeps_status_and_strengths():
    bull = ev(event_confirmed=True, event_strength=0.80, control_score=0.90,
              intent_supported=True, mode_known=True, observation_quality=0.90)
    bear = ev(control_score=0.20, observation_quality=0.90)
    original = assign_thesis_side(bull, bear, POLICY)
    mirrored = assign_thesis_side(bear, bull, POLICY)
    assert original["thesis__side"] == "BULL"
    assert mirrored["thesis__side"] == "BEAR"
    assert original["thesis__direction_status"] == mirrored["thesis__direction_status"]
    assert original["bull_structure_strength"] == mirrored["bear_structure_strength"]


def test_marginally_stronger_opposing_evidence_does_not_erase_leading_side():
    bull = ev(event_confirmed=True, event_strength=0.90, observation_quality=0.90)
    bear = ev(event_confirmed=True, event_strength=0.65, observation_quality=0.90)
    first = assign_thesis_side(bull, bear, POLICY)
    stronger = assign_thesis_side(
        ev(event_confirmed=True, event_strength=0.95, observation_quality=0.90), bear, POLICY
    )
    assert first["thesis__side"] == stronger["thesis__side"] == "BULL"
    assert stronger["bear_structure_strength"] == first["bear_structure_strength"]


def test_control_margin_requires_both_measured_sides():
    result = assign_thesis_side(
        ev(control_score=0.95), ev(control_score=None), POLICY
    )
    assert result["bull_support_types"] == []
    assert result["thesis__side"] == "UNASSIGNED"
