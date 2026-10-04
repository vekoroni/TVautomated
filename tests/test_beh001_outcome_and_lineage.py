"""BEH-001 RQ-1 (activation != outcome) and RQ-2 (failure -> next logic).

- Every directed candidate carries a structural Outcome_Level on the correct
  side of its trigger and a stated Outcome_Definition; monitoring
  observations carry none.
- A continuation created by a failed event names that event's candidate as
  its parent; age since the event bar is published.
"""
import copy

from domain.structure_behaviour.engine import analyse_timeframe
from domain.structure_behaviour.policy import load_policy
from test_beh001_phase_events_signals import FAILED_SPRING, SPRING, run
from test_beh001_sequences import RANGE, TREND_DOWN


def directed(reading):
    return [c for c in reading["candidates"] if c["Direction"] in {"BULL", "BEAR"}]


def test_directed_candidates_have_an_outcome_beyond_the_trigger():
    for points in (TREND_DOWN, SPRING, FAILED_SPRING, RANGE + [95.0, 94.6, 95.2, 94.9]):
        for c in directed(run(points)):
            assert c["Outcome_Definition"], c["Signal_Type"]
            if c["Outcome_Level"] is None:
                assert c["Outcome_Definition"].startswith("NONE:"), c
                continue
            if c["Direction"] == "BULL":
                assert c["Outcome_Level"] > c["Trigger_Level"] > c["Invalidation_Level"] or \
                    c["Outcome_Level"] > c["Invalidation_Level"], c
            else:
                assert c["Outcome_Level"] < c["Trigger_Level"] < c["Invalidation_Level"] or \
                    c["Outcome_Level"] < c["Invalidation_Level"], c


def test_spring_outcome_is_the_opposite_range_boundary():
    spring = [c for c in run(SPRING)["candidates"] if c["Signal_Type"] == "Spring Candidate"][0]
    assert spring["Outcome_Definition"].startswith("RANGE_RESISTANCE") or \
        spring["Outcome_Definition"].startswith("PRIOR_SWING_HIGH")
    assert 98.0 < spring["Outcome_Level"] < 101.0


def test_failed_spring_continuation_names_its_parent_and_age():
    reading = run(FAILED_SPRING)
    cont = [c for c in reading["candidates"] if c["Signal_Type"] == "Failed Spring Continuation"][0]
    assert cont["Parent_Candidate_ID"].split("|")[3] == "Spring Candidate"
    assert cont["Parent_Candidate_ID"].split("|")[4] == cont["Candidate_ID"].split("|")[4]
    assert isinstance(cont["Age_Bars"], int) and cont["Age_Bars"] >= 0


def test_monitoring_observations_have_no_outcome_level():
    for c in run(RANGE + [95.0, 94.6, 95.2, 94.9])["candidates"]:
        if c["Signal_State"] == "MONITOR":
            assert c["Outcome_Level"] is None


def test_mirrored_chart_gives_mirrored_outcome_levels():
    from domain.structure_behaviour.sequences import reflect_bars
    from test_beh001_phase_events_signals import POLICY
    from test_beh001_sequences import zigzag_bars
    for points in (TREND_DOWN, SPRING, FAILED_SPRING):
        bars = zigzag_bars(points)
        k = float(bars["close"].iloc[-1])
        original = analyse_timeframe("TEST", bars, "1d", POLICY)
        mirrored = analyse_timeframe("TEST", reflect_bars(bars), "1d", POLICY)
        a = sorted(round(c["Outcome_Level"], 6) for c in directed(original) if c["Outcome_Level"])
        b = sorted(round(k * k / c["Outcome_Level"], 6) for c in directed(mirrored) if c["Outcome_Level"])
        assert a == b, points


def test_candidate_whose_outcome_was_reached_is_not_published_as_live():
    """A move that already happened is not a fresh opportunity (A2 eval_v2 finding:
    about half of ACTIVATED candidates had reached their outcome at the cut)."""
    from domain.structure_behaviour.engine import handoff_thesis
    extended = TREND_DOWN + [TREND_DOWN[-1] * 0.6, TREND_DOWN[-1] * 0.55]
    reading = run(extended)
    shallow = [c for c in reading["candidates"] if c["Signal_Type"] == "Trend Continuation after Shallow Test"][0]
    assert shallow["Signal_State"] == "OUTCOME_REACHED"
    assert shallow["Outcome_Level"] is not None
    handoff = handoff_thesis({"1d": reading})
    assert handoff["primary"] is None or handoff["primary"]["Candidate_ID"] != shallow["Candidate_ID"]


def test_activated_candidate_short_of_its_outcome_stays_activated():
    reading = run(TREND_DOWN + [TREND_DOWN[-1] * 0.95])
    states = {c["Signal_Type"]: c["Signal_State"] for c in directed(reading)}
    for c in directed(reading):
        if c["Signal_State"] == "ACTIVATED":
            up = c["Direction"] == "BULL"
            last = 77 * 0.95
            assert (last < c["Outcome_Level"]) if up else (last > c["Outcome_Level"]), states


def test_reaching_an_outcome_ends_the_stage_not_the_ticker():
    """ACK, 1 Oct: once an outcome is reached the ticker can enter another stage;
    the next stage's candidates name the completed candidate as their parent."""
    reading = run(TREND_DOWN + [TREND_DOWN[-1] * 0.6, TREND_DOWN[-1] * 0.55])
    done = [c for c in reading["candidates"] if c["Signal_State"] == "OUTCOME_REACHED"][0]
    assert done["Outcome_Reached_As_Of"]
    assert "next stage" in done["Next_Anticipated_Logic"].lower()
    later = [c for c in reading["candidates"]
             if c["Candidate_ID"].split("|")[4] > done["Outcome_Reached_As_Of"]
             and c["Structure_Scope"] == done["Structure_Scope"]]
    assert later, "the ticker keeps being read after the outcome"
    assert all(c["Parent_Candidate_ID"] == done["Candidate_ID"] for c in later)


def test_two_propositions_on_one_bar_get_distinct_ids():
    """Real data (AMRX 5m, TAP 1d): two events of one type on one bar testing different
    levels are different propositions; colliding IDs gain a level suffix, others are unchanged."""
    from domain.structure_behaviour.signals import disambiguate_ids
    rows = [{"Candidate_ID": "T|1d|CAMPAIGN|Upthrust Candidate|2026-09-29", "Trigger_Level": 20.229},
            {"Candidate_ID": "T|1d|CAMPAIGN|Upthrust Candidate|2026-09-29", "Trigger_Level": 20.18},
            {"Candidate_ID": "T|1d|CAMPAIGN|Spring Candidate|2026-09-01", "Trigger_Level": 10.0}]
    disambiguate_ids(rows)
    ids = [r["Candidate_ID"] for r in rows]
    assert len(set(ids)) == 3
    assert ids[2] == "T|1d|CAMPAIGN|Spring Candidate|2026-09-01"
    assert ids[0].endswith("|L20.229") and ids[1].endswith("|L20.18")
    assert ids[0].split("|")[3] == "Upthrust Candidate"


def test_exact_duplicate_propositions_are_emitted_once():
    """Evening 1 Oct: 43 candidates were emitted twice with the same ID and trigger
    (one event on one bar detected twice). One proposition is published once."""
    from domain.structure_behaviour.signals import disambiguate_ids
    row = {"Candidate_ID": "T|1d|CAMPAIGN|Upthrust Candidate|2026-09-23", "Trigger_Level": 263.5885,
           "Invalidation_Level": 270.0, "Signal_State": "ACTIVATED", "Direction": "BEAR"}
    rows = [dict(row), dict(row), {**row, "Trigger_Level": 260.0}]
    disambiguate_ids(rows)
    ids = [r["Candidate_ID"] for r in rows]
    assert len(ids) == len(set(ids)) == 2
