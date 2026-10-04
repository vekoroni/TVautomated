"""BEH-001 duration (C-04, C-05, RQ-3; A2 Part 4).

Business rules:
- No fixed window: a candidate carries the remaining time to its next event,
  measured from comparable replayed candidates on the same timeframe.
- DETECTED candidates get time to activation; ACTIVATED candidates get time to outcome.
- Remaining time depends on the candidate's current age (RQ-3): the age-bucket
  estimate is used when its sample is sufficient, else all ages, else UNESTIMATED.
- Evidence observed after the candidate's as-of date is never used (causal).
- Missing evidence never fails the engine; the reason is stated.
"""
import json

from domain.structure_behaviour.duration import attach_duration, load_duration_evidence


def evidence(data_end="2026-09-29", **override):
    group = {"timeframe": "1d", "scope": "CAMPAIGN", "signal_type": "Spring Candidate", "direction": "BULL",
             "test": "ACTIVATION", "age_bucket": "ALL", "n": 500, "censored": 10,
             "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "p_event_at_limit": 0.6,
             "p_invalidation_at_limit": 0.38, "unresolved_at_limit": 0.02,
             "remaining_bars_q50": 7, "remaining_bars_q80": 25}
    young = {**group, "age_bucket": "0-2", "n": 200, "remaining_bars_q50": 9, "remaining_bars_q80": 30}
    old = {**group, "age_bucket": "21+", "n": 40, "status": "INSUFFICIENT_SAMPLE"}
    outcome = {**group, "test": "OUTCOME", "remaining_bars_q50": 15, "remaining_bars_q80": 60}
    for g in (group, young, old, outcome):
        g.update(override)
    return {"version": "beh001_duration_evidence_v1", "data_end": data_end, "age_bucket_edges": [0, 3, 6, 11, 21],
            "groups": [group, young, old, outcome]}


def cand(state="DETECTED", age=1, as_of="2026-10-01"):
    return {"Timeframe": "1d", "Structure_Scope": "CAMPAIGN", "Signal_Type": "Spring Candidate",
            "Direction": "BULL", "Signal_State": state, "Age_Bars": age, "As_Of": as_of}


def test_detected_candidate_gets_remaining_time_to_activation_for_its_age():
    c = cand(age=1)
    attach_duration([c], evidence())
    assert c["Duration_Test"] == "ACTIVATION"
    assert c["Duration_Basis"] == "AGE_0-2"
    assert (c["Duration_Remaining_Q50_Bars"], c["Duration_Remaining_Q80_Bars"]) == (9, 30)
    assert c["Expected_Duration"].startswith("ESTIMATED")
    assert "9" in c["Expected_Duration"] and "30" in c["Expected_Duration"]


def test_small_age_bucket_falls_back_to_all_ages():
    c = cand(age=40)
    attach_duration([c], evidence())
    assert c["Duration_Basis"] == "ALL_AGES"
    assert c["Duration_Remaining_Q50_Bars"] == 7


def test_activated_candidate_gets_remaining_time_to_outcome():
    c = cand(state="ACTIVATED")
    attach_duration([c], evidence())
    assert c["Duration_Test"] == "OUTCOME"
    assert c["Duration_Remaining_Q80_Bars"] == 60


def test_evidence_from_after_the_as_of_date_is_never_used():
    c = cand(as_of="2026-09-15")
    attach_duration([c], evidence(data_end="2026-09-29"))
    assert c["Expected_Duration"].startswith("UNESTIMATED")
    assert c["Duration_Status"] == "EVIDENCE_NOT_CAUSAL"
    assert c["Duration_Remaining_Q50_Bars"] is None


def test_states_without_a_next_event_and_missing_groups_are_unestimated():
    done, unknown = cand(state="OUTCOME_REACHED"), cand()
    unknown["Signal_Type"] = "Unseen Type"
    attach_duration([done, unknown], evidence())
    assert done["Duration_Status"] == "NOT_APPLICABLE"
    assert unknown["Duration_Status"] == "NO_COMPARABLE_EVIDENCE"
    assert all(c["Expected_Duration"].startswith("UNESTIMATED") for c in (done, unknown))


def test_missing_evidence_file_never_fails(tmp_path):
    loaded = load_duration_evidence(tmp_path / "missing.json")
    c = cand()
    attach_duration([c], loaded)
    assert c["Duration_Status"] == "NO_EVIDENCE_FILE"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    c2 = cand()
    attach_duration([c2], load_duration_evidence(bad))
    assert c2["Duration_Status"] == "NO_EVIDENCE_FILE"


def test_every_candidate_from_the_engine_carries_a_duration_reading(tmp_path):
    import copy
    from domain.structure_behaviour.engine import analyse_ticker
    from domain.structure_behaviour.policy import load_policy
    from test_beh001_sequences import TREND_DOWN, zigzag_bars
    policy = copy.deepcopy(dict(load_policy()))
    policy["timeframes"]["1d"]["min_bars"] = 20
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(evidence(data_end="2020-01-01")), encoding="utf-8")
    policy["duration"] = {**policy["duration"], "evidence_path": str(path)}
    result = analyse_ticker("TEST", zigzag_bars(TREND_DOWN), None, policy, intraday_status="NO_INTRADAY_DATA")
    assert result["candidates"]
    assert all("Duration_Status" in c and c["Expected_Duration"] for c in result["candidates"])
