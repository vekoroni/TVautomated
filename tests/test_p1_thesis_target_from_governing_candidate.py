"""P0-04 (Phase 1): the thesis target and trigger come from the governing candidate itself.

Business rule (one candidate, one story): the setup that governs the thesis also supplies its target (its own
Outcome_Level) and its trigger level. A legacy geometry (Wyckoff validator PRIOR_RANGE_EXTREME, asymmetry) is
never published as the thesis target. With no governing setup the target stays missing - never a fallback.
Phase 0: on run 20261006_060401 the thesis target came from PRIOR_RANGE_EXTREME on every row and differed from the
governing candidate's own level on 907 of 951.
"""
import avshunter_discovery_ULTIMATE as disc
from contracts.direction_governance import STRUCTURAL_TARGET_SOURCES, assess_thesis_geometry, legacy_direction_adapter_v1

GOV_BULL = {"Candidate_ID": "XYZ|1w|CAMPAIGN|SOS -> LPS continuation|2026-09-01", "Direction": "BULL",
            "Timeframe": "1w", "Signal_Type": "SOS -> LPS continuation", "Signal_State": "ACTIVATED",
            "Trigger_Level": 101.0, "Invalidation_Level": 92.0, "Outcome_Level": 118.0}


def test_behavioural_outcome_is_an_accepted_structural_target_source():
    assert "BEH001_OUTCOME_LEVEL" in STRUCTURAL_TARGET_SOURCES
    g = assess_thesis_geometry(thesis_side="BULL", reference_price=100.0, invalidation_price=92.0,
                               invalidation_source="BEHAVIOURAL_STRUCTURE", target_price=118.0,
                               target_source="BEH001_OUTCOME_LEVEL")
    assert g["target_state"] == "LEVEL" and g["target_price"] == 118.0


def test_thesis_target_is_the_governing_candidates_outcome_level():
    geo = disc._governed_thesis_geometry("BULL", 100.0, 92.0, GOV_BULL)
    adapter = legacy_direction_adapter_v1(thesis_side="BULL", direction_status="ACTIVATED:x", direction_basis="{}",
                                          unassigned_reason="", geometry=geo)
    assert adapter["structural_target"] == 118.0
    assert adapter["structural_target_source"] == "BEH001_OUTCOME_LEVEL"


def test_no_governing_setup_leaves_the_target_missing_not_legacy():
    geo = disc._governed_thesis_geometry("BULL", 100.0, 92.0, None)
    assert geo["target_price"] is None and geo["target_state"] == "NONE"


def test_thesis_trigger_level_is_the_governing_candidates():
    assert disc._governed_trigger_fields(GOV_BULL) == {"thesis_trigger_level": 101.0,
                                                      "thesis_trigger_source": "BEH001_TRIGGER_LEVEL",
                                                      "thesis_trigger_candidate_id": GOV_BULL["Candidate_ID"]}
    assert disc._governed_trigger_fields(None)["thesis_trigger_level"] is None
