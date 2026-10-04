"""Audit finding 5 (1 Oct 2026): the direction adapter labelled every structural target
"WYCKOFF", including prior-range extremes, so a prior-range target passed C5's Wyckoff
check under the wrong name.

Business rule: a target travels with the source that produced it. C5 accepts the
structural sources by name (WYCKOFF and PRIOR_RANGE_EXTREME); an unsourced target is
never accepted.
"""
from contracts.direction_governance import assess_thesis_geometry, legacy_direction_adapter_v1


def adapter_for(target_source):
    geometry = assess_thesis_geometry(
        thesis_side="BULL", reference_price=100.0, invalidation_price=95.0,
        invalidation_source="BEHAVIOURAL_STRUCTURE", target_price=110.0, target_source=target_source)
    return legacy_direction_adapter_v1(thesis_side="BULL", direction_status="DETECTED:Spring Candidate",
                                       direction_basis="{}", unassigned_reason="", geometry=geometry)


def test_prior_range_target_keeps_its_own_source():
    out = adapter_for("PRIOR_RANGE_EXTREME")
    assert out["structural_target"] == 110.0
    assert out["structural_target_source"] == "PRIOR_RANGE_EXTREME"


def test_wyckoff_target_is_still_labelled_wyckoff():
    assert adapter_for("WYCKOFF")["structural_target_source"] == "WYCKOFF"


def test_unsourced_target_is_not_passed_on():
    out = adapter_for("SOMETHING_ELSE")
    assert out["structural_target"] is None and out["structural_target_source"] is None


def test_c5_accepts_structural_sources_by_name():
    from domain import descriptive_forecast_handoff as c5
    assert c5.STRUCTURAL_TARGET_SOURCES == frozenset({"WYCKOFF", "PRIOR_RANGE_EXTREME"})
