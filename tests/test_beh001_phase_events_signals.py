"""BEH-001 L5-L8: phase, event life cycle, transition and signal candidates.

Business rules:
- One phase per timeframe from current evidence, with confidence/transition.
- Events start as candidates and resolve from later bars (F4); a failed
  Spring becomes a BEAR Failed-Spring continuation, never a BULL signal.
- Phase A vs C needs range context (F5).
- Each candidate carries direction, trigger, invalidation, expected behaviour
  and next anticipated logic; compression never creates direction (F6).
- Mirrored charts give mirrored candidates.
"""
import copy

from domain.structure_behaviour.engine import analyse_timeframe
from domain.structure_behaviour.policy import load_policy
from domain.structure_behaviour.sequences import reflect_bars
from test_beh001_sequences import RANGE, TREND_DOWN, zigzag_bars

POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20

REQUIRED = {"Ticker", "Direction", "Wyckoff_Phase", "Wyckoff_Event", "Controller", "Control_Quality",
            "SOT_State", "Crabel_Compression", "Movement_Maturity", "Trigger", "Invalidation",
            "Expected_Behaviour", "Expected_Duration", "Warning", "Signal_Type", "Signal_State",
            "Timeframe", "Timeframe_Role", "As_Of", "Phase_Confidence", "Phase_Transition",
            "Structural_Context", "Control_Origin", "Control_Start", "Control_Duration",
            "Control_Transfer_Condition", "Movement_Start", "Movement_Duration",
            "Next_Anticipated_Logic", "Direction_Status", "Candidate_ID", "Trigger_Level",
            "Invalidation_Level", "Evidence", "Outcome_Level", "Outcome_Definition",
            "Parent_Candidate_ID", "Age_Bars"}


def run(points, **kw):
    return analyse_timeframe("TEST", zigzag_bars(points, **kw), "1d", POLICY)


def directed(reading):
    return [c for c in reading["candidates"] if c["Direction"] in {"BULL", "BEAR"}]


def test_markdown_with_unrepaired_recovery_gives_bear_continuation():
    reading = run(TREND_DOWN)
    assert reading["Controller"] == "SELLERS"
    assert reading["Wyckoff_Phase"] in {"D", "E"}
    types = {c["Signal_Type"] for c in directed(reading)}
    assert types & {"SOW -> LPSY continuation", "Trend Continuation after Shallow Test"}
    assert all(c["Direction"] == "BEAR" for c in directed(reading))


def test_every_candidate_has_the_full_field_contract():
    for points in (TREND_DOWN, RANGE):
        for candidate in run(points)["candidates"]:
            assert REQUIRED <= set(candidate), REQUIRED - set(candidate)
            assert candidate["Direction_Status"] == "HYPOTHESIS_NOT_OUTCOME"
            assert candidate["Expected_Duration"].startswith("UNESTIMATED")


def test_mirrored_chart_gives_mirrored_candidates():
    bars = zigzag_bars(TREND_DOWN)
    original = analyse_timeframe("TEST", bars, "1d", POLICY)
    mirrored = analyse_timeframe("TEST", reflect_bars(bars), "1d", POLICY)
    flip = {"BULL": "BEAR", "BEAR": "BULL", None: None, "": ""}
    assert mirrored["Controller"] == "BUYERS"
    assert mirrored["Wyckoff_Phase"] == original["Wyckoff_Phase"]
    assert sorted(flip[c["Direction"]] or "" for c in original["candidates"]) == \
        sorted(c["Direction"] or "" for c in mirrored["candidates"])


SPRING = RANGE + [88.0, 96.0]          # penetrate support ~90 and recover
FAILED_SPRING = RANGE + [88.0, 93.0, 84.0, 82.0]   # recovery fails, accepted below


def test_spring_in_a_range_is_a_bull_candidate_and_phase_c():
    reading = run(SPRING)
    spring = [c for c in reading["candidates"] if c["Signal_Type"] in {"Spring Candidate", "Spring Secondary Test"}]
    assert spring, [c["Signal_Type"] for c in reading["candidates"]]
    assert spring[0]["Direction"] == "BULL"
    assert reading["Wyckoff_Phase"] in {"C", "D"}
    assert spring[0]["Invalidation_Level"] < spring[0]["Trigger_Level"]


def test_failed_spring_becomes_bear_continuation_not_bull():
    reading = run(FAILED_SPRING)
    types = {c["Signal_Type"]: c["Direction"] for c in reading["candidates"]}
    assert "Spring Candidate" not in types or types.get("Spring Candidate") != "BULL" or \
        any(e["state"] == "FAILED" for e in reading["events"] if e["event"] == "SPRING")
    assert types.get("Failed Spring Continuation") == "BEAR"


def test_balanced_range_without_test_gives_no_directed_candidate():
    reading = run(RANGE)
    assert reading["Controller"] == "TWO-SIDED"
    assert reading["Wyckoff_Phase"] == "B"
    assert not directed(reading)


def test_compression_never_creates_a_direction():
    reading = run(RANGE + [95.0, 94.6, 95.2, 94.9])
    for c in reading["candidates"]:
        if c["Signal_Type"] in {"Crabel Compression Breakout", "Hinge / Apex Expansion"}:
            assert c["Direction"] in {None, "BULL", "BEAR"}
            if reading["Controller"] == "TWO-SIDED":
                assert c["Direction"] is None and c["Signal_State"] == "MONITOR"


def test_events_carry_life_cycle_states():
    reading = run(FAILED_SPRING)
    states = {e["state"] for e in reading["events"]}
    assert states <= {"DETECTED", "CONFIRMED", "FAILED", "UNRESOLVED", "SUPERSEDED"}
    assert any(e["event"] == "SPRING" and e["state"] == "FAILED" for e in reading["events"])


def test_nested_local_markdown_inside_a_campaign_range_is_scoped_local():
    # Wide campaign range, then a minor markdown sequence inside it.
    points = [100, 78, 99, 79, 98, 80, 97, 92, 95, 89, 91.5, 86, 87.2]
    reading = run(points, bars_per_leg=5)
    local = [c for c in reading["candidates"] if c["Structure_Scope"] == "LOCAL"]
    assert reading["Local_Controller"] == "SELLERS", (reading["Controller"], reading["Local_Controller"])
    assert local and all(c["Direction"] == "BEAR" for c in local if c["Direction"])
    assert all(c["Candidate_ID"].split("|")[2] in {"CAMPAIGN", "LOCAL"} for c in reading["candidates"])


def test_compression_location_has_no_support_first_tie_order():
    from domain.structure_behaviour.compression import _location_label
    # Equidistant from support and resistance: neither side is preferred.
    assert _location_label(near_support=1.0, near_resistance=1.0, limit=1.5) == "AT_BOTH_BOUNDARIES"
    assert _location_label(near_support=0.5, near_resistance=1.2, limit=1.5) == "AT_SUPPORT"
    assert _location_label(near_support=1.2, near_resistance=0.5, limit=1.5) == "AT_RESISTANCE"


def test_spring_above_a_failed_spring_is_superseded_not_live():
    from domain.structure_behaviour.events import _supersede_failed_tests
    events = [
        {"event": "SPRING", "state": "FAILED", "event_price": 90.0},
        {"event": "SPRING", "state": "DETECTED", "event_price": 92.0},
        {"event": "SPRING", "state": "DETECTED", "event_price": 85.0},
        {"event": "UPTHRUST", "state": "FAILED", "event_price": 110.0},
        {"event": "UPTHRUST", "state": "CONFIRMED", "event_price": 108.0},
    ]
    states = [e["state"] for e in _supersede_failed_tests(events)]
    assert states == ["FAILED", "SUPERSEDED", "DETECTED", "FAILED", "SUPERSEDED"]
