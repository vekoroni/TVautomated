"""DIR-002 §4.5: one canonical thesis side owns every legacy side field."""

import pytest

from contracts.direction_governance import assess_thesis_geometry, legacy_direction_adapter_v1


def test_bull_side_is_kept_even_when_its_structural_stop_is_missing() -> None:
    result = legacy_direction_adapter_v1(
        thesis_side="BULL",
        direction_status="SINGLE_SOURCE_STRUCTURE",
        direction_basis="spring candidate at completed session",
        unassigned_reason=None,
        geometry={
            "geometry_status": "INCOMPLETE_GEOMETRY",
            "invalidation_price": None,
            "target_state": "LEVEL",
            "target_price": 110.0,
            "target_source": "PRIOR_RANGE_EXTREME",
        },
    )

    assert result["direction"] == result["discovery_direction_preliminary"] == "CALL"
    assert result["direction_authority"] == "DISCOVERY_GOVERNED"
    assert result["governed_invalidation_spot"] is None
    assert result["stop_loss"] is None
    assert result["structural_target"] == 110.0
    assert result["structural_target_source"] == "PRIOR_RANGE_EXTREME"   # audit finding 5: true source, not relabelled
    assert result["geometry_status"] == "INCOMPLETE_GEOMETRY"


def test_bear_side_with_no_target_never_gets_a_formula_target() -> None:
    result = legacy_direction_adapter_v1(
        thesis_side="BEAR",
        direction_status="CONFIRMED_STRUCTURE",
        direction_basis="upthrust fail-back",
        unassigned_reason=None,
        geometry={
            "geometry_status": "COMPLETE",
            "invalidation_price": 105.0,
            "invalidation_source": "WYCKOFF_VALIDATION",
            "target_state": "NONE",
            "target_price": None,
        },
    )

    assert result["direction"] == result["discovery_direction_preliminary"] == "PUT"
    assert result["governed_invalidation_spot"] == 105.0
    assert result["stop_loss"] == 105.0
    assert result["structural_target"] is None
    assert result["target_state"] == "NONE"


def test_unassigned_stays_non_directional_even_with_two_candidate_geometries() -> None:
    result = legacy_direction_adapter_v1(
        thesis_side="UNASSIGNED",
        direction_status="CONFLICT_REVIEW",
        direction_basis="opposing structural observations",
        unassigned_reason="CONFLICT_REVIEW",
        geometry={"geometry_status": "COMPLETE", "invalidation_price": 95.0},
    )
    assert result["direction"] == result["discovery_direction_preliminary"] == "UNRESOLVED"
    assert result["stop_loss"] is None
    assert result["structural_target"] is None
    assert result["governed_invalidation_spot"] is None


def test_mixed_transition_keeps_legacy_strangle_only_at_the_adapter() -> None:
    result = legacy_direction_adapter_v1(
        thesis_side="UNASSIGNED",
        direction_status="TRANSITION_MIXED_TREND",
        direction_basis="mixed completed EMA trend",
        unassigned_reason="TRANSITION_MIXED_TREND",
        geometry={},
    )
    assert result["direction"] == result["discovery_direction_preliminary"] == "STRANGLE"


def test_dec1_trend_only_remains_unassigned_at_legacy_boundary() -> None:
    result = legacy_direction_adapter_v1(
        thesis_side="UNASSIGNED",
        direction_status="TREND_ONLY",
        direction_basis="EMA aligned but no qualifying structure",
        unassigned_reason="TREND_ONLY",
        geometry={"geometry_status": "NOT_ASSESSABLE"},
    )
    assert result["direction"] == result["discovery_direction_preliminary"] == "UNRESOLVED"
    assert result["stop_loss"] is None


@pytest.mark.parametrize("side", ["BULL", "BEAR"])
def test_dec1_trend_only_cannot_be_promoted_by_adapter(side: str) -> None:
    with pytest.raises(ValueError, match="Trend-only"):
        legacy_direction_adapter_v1(
            thesis_side=side,
            direction_status="TREND_ONLY",
            direction_basis="EMA aligned but no qualifying structure",
            unassigned_reason=None,
            geometry={"geometry_status": "COMPLETE"},
        )


def test_invalid_canonical_side_fails_instead_of_defaulting_to_call() -> None:
    try:
        legacy_direction_adapter_v1(
            thesis_side="",
            direction_status="NO_DIRECTIONAL_EVIDENCE",
            direction_basis="",
            unassigned_reason="NO_DIRECTIONAL_EVIDENCE",
            geometry={},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown canonical side cannot become CALL")


def test_assessed_geometry_passes_its_source_to_the_single_legacy_adapter() -> None:
    assessed = assess_thesis_geometry(
        thesis_side="BEAR",
        reference_price=100.0,
        invalidation_price=105.0,
        invalidation_source="WYCKOFF_VALIDATION",
        target_price=95.0,
        target_source="PRIOR_RANGE_EXTREME",
    )
    result = legacy_direction_adapter_v1(
        thesis_side="BEAR",
        direction_status="CONTESTED_DIRECTION",
        direction_basis="dated opposing observations retained",
        unassigned_reason=None,
        geometry=assessed,
    )

    assert result["direction"] == "PUT"
    assert result["governed_invalidation_spot"] == 105.0
    assert result["stop_loss"] == 105.0
    assert result["structural_target"] == 95.0
