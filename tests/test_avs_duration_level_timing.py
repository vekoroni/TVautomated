"""Step 4a (ACK 3 Oct 2026): time to the anticipated level is measured, not assumed.

Finding: most trade-side events are DETECTED and many detected types never become ACTIVATED (22 of 46 types have
no outcome records); their activation evidence (time to the trigger) was being shown as time and probability of
reaching the level (SOFI "61% of 1,481" was P(activation)). Business rules:
- For a DETECTED candidate the level timing comes from OUTCOME_FROM_DETECTION (the Outcome_Level reached before
  invalidation, timed from detection); for an ACTIVATED candidate from OUTCOME.
- Activation timing is kept separately and labelled as activation.
- No level evidence -> the level timing is UNESTIMATED; activation is never relabelled as the level.
"""
from domain.anticipated_move import anticipated_move_fields
from domain.structure_behaviour.duration import attach_duration
from domain.structure_behaviour.thesis_category import thesis_category


def _group(test, q50, q80, p, n=500, age="ALL"):
    return {"timeframe": "1d", "scope": "CAMPAIGN", "signal_type": "Seller Absorption Breakdown", "direction": "BEAR",
            "test": test, "age_bucket": age, "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "n": n,
            "remaining_bars_q50": q50, "remaining_bars_q80": q80, "p_event_at_limit": p, "p_invalidation_at_limit": 1 - p,
            "unresolved_at_limit": 0.0}


EVIDENCE = {"version": "beh001_duration_evidence_v3", "data_end": "2026-10-01", "age_bucket_edges": [0, 3, 6, 11, 21],
            "groups": [_group("ACTIVATION", 2, 5, 0.61, 1481), _group("OUTCOME_FROM_DETECTION", 9, 24, 0.38, 1300)]}


def _cand(state="DETECTED"):
    return {"Candidate_ID": "SOFI|1d", "Signal_State": state, "Direction": "BEAR", "Timeframe": "1d",
            "Structure_Scope": "CAMPAIGN", "Signal_Type": "Seller Absorption Breakdown", "Age_Bars": 1,
            "As_Of": "2026-10-02", "Outcome_Level": 15.2, "Outcome_Definition": "MEASURED_MOVE"}


def test_detected_candidate_gets_level_timing_from_detection_and_activation_separately():
    c = _cand()
    attach_duration([c], EVIDENCE)
    assert c["Duration_Test"] == "ACTIVATION" and c["Duration_Remaining_Q50_Bars"] == 2
    assert c["Duration_Level_Test"] == "OUTCOME_FROM_DETECTION"
    assert (c["Duration_Level_Q50_Bars"], c["Duration_Level_Q80_Bars"], c["Duration_Level_P_Event_At_Limit"]) == (9, 24, 0.38)


def test_thesis_evidence_uses_level_timing_and_keeps_activation_labelled():
    c = _cand()
    attach_duration([c], EVIDENCE)
    out = thesis_category({"1d": {"Status": "EVALUATED", "candidates": [c], "Wyckoff_Phase": "B"}}, "PUT")
    assert out["thesis_duration_test"] == "OUTCOME_FROM_DETECTION"
    assert out["thesis_duration_q50_bars"] == 9 and out["thesis_p_outcome_by_limit"] == 0.38
    assert out["thesis_activation_q50_bars"] == 2 and out["thesis_activation_q80_bars"] == 5


def test_no_level_evidence_is_unestimated_never_activation():
    c = _cand()
    attach_duration([c], {**EVIDENCE, "groups": [_group("ACTIVATION", 2, 5, 0.61, 1481)]})
    assert c["Duration_Level_Status"] == "NO_COMPARABLE_EVIDENCE" and c["Duration_Level_Q50_Bars"] is None
    out = thesis_category({"1d": {"Status": "EVALUATED", "candidates": [c], "Wyckoff_Phase": "B"}}, "PUT")
    assert out["thesis_duration_q50_bars"] is None and out["thesis_p_outcome_by_limit"] is None
    am = anticipated_move_fields(direction="PUT", spot=15.92, outcome_level=15.2, outcome_definition="X", timeframe="1d",
                                 duration={"status": out["thesis_duration_status"], "n": out["thesis_duration_n"],
                                           "q50_bars": None, "q80_bars": None},
                                 vol_annual=0.5, contract=None, governed_window_sessions=20)
    assert am["anticipated_hold_sessions"] is None and am["anticipated_p_outcome_by_limit"] is None


def test_activated_candidate_level_timing_is_its_outcome_evidence():
    c = _cand("ACTIVATED")
    attach_duration([c], {**EVIDENCE, "groups": [_group("OUTCOME", 4, 11, 0.55, 800)]})
    assert c["Duration_Level_Test"] == "OUTCOME" and c["Duration_Level_Q80_Bars"] == 11
