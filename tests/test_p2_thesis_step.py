"""Phase 2: Discovery's thesis step is the one owner of direction (design §5, §9; ACK 8 Oct 2026 spine rule).

Business rules:
- Every candidate gets a thesis decision: ADOPTED (its own side, complete geometry, live), REFUSED (geometry on the
  wrong side: the move already happened or invalidation is crossed), UNRESOLVED (no side, or levels missing) with
  the condition that would resolve it, or CLOSED (failed / outcome reached).
- An undirected compression thesis carries BOTH conditional boundaries (BULL above box_high, BEAR below box_low).
- The ticker's side (the spine, until Phase 5) is set top-down by ACK's rule: the highest tested timeframe with an
  adopted thesis decides (1mo > 1w > 1d); opposite adopted theses on that same timeframe -> UNRESOLVED.
  Intraday theses never set the side (untested, ACK 5 Oct 2026).
- Only the thesis step writes the side: legacy direction fields never change it.
"""
import ast
from pathlib import Path

from contracts.thesis_record import build_thesis, ticker_spine

ROOT = Path(__file__).resolve().parents[1]


def _cand(cid, tf, side, state="DETECTED", levels="COMPLETE", family="CONTINUATION", **kw):
    c = {"Candidate_ID": cid, "Timeframe": tf, "Direction": side, "Proposed_Side": side, "Signal_State": state,
         "Signal_Type": "SOS -> LPS continuation", "Family": family, "Levels_Status": levels,
         "Trigger_Level": 104.0, "Invalidation_Level": 95.0, "Outcome_Level": 115.0}
    c.update(kw)
    return c


def test_complete_live_directed_candidate_is_adopted_on_its_own_side():
    t = build_thesis(_cand("A", "1d", "BULL"), readings={})
    assert t["Adoption_State"] == "ADOPTED" and t["Thesis_Side"] == "BULL"
    # Phase 5.3: readiness comes from the thesis's own events (event_readiness), not the engine state.
    assert t["Lifecycle_State"] == "DEVELOPING" and t["Readiness"] == "PENDING_EVENTS"


def test_activated_adopted_thesis_waits_for_its_events_to_decide_readiness():
    # Phase 5.3 (ACK 8 Oct 2026): the engine state is the lifecycle; readiness is decided from events.
    t = build_thesis(_cand("A", "1d", "BULL", state="ACTIVATED"), readings={})
    assert t["Lifecycle_State"] == "ACTIVATED" and t["Readiness"] == "PENDING_EVENTS"


def test_wrong_side_geometry_is_refused_with_reason():
    t = build_thesis(_cand("A", "1d", "BULL", levels="WRONG_SIDE"), readings={})
    assert t["Adoption_State"] == "REFUSED" and t["Deciding_Reason"] == "LEVELS_WRONG_SIDE"


def test_missing_levels_leave_the_thesis_unresolved_not_adopted():
    t = build_thesis(_cand("A", "1d", "BULL", levels="INCOMPLETE"), readings={})
    assert t["Adoption_State"] == "UNRESOLVED" and "LEVELS" in t["Unresolved_Condition"]


def test_undirected_compression_carries_both_conditional_boundaries():
    c = _cand("C", "1d", None, levels="NOT_DIRECTED", family="COMPRESSION",
              Signal_Type="Crabel Compression Breakout")
    t = build_thesis(c, readings={"1d": {"Compression_Box_High": 110.0, "Compression_Box_Low": 101.0}})
    assert t["Adoption_State"] == "UNRESOLVED" and t["Thesis_Side"] is None
    assert t["Conditional_Bull_Trigger"] == 110.0 and t["Conditional_Bear_Trigger"] == 101.0


def test_failed_and_outcome_reached_are_closed():
    assert build_thesis(_cand("A", "1d", "BULL", state="FAILED"), readings={})["Adoption_State"] == "CLOSED"
    assert build_thesis(_cand("A", "1d", "BULL", state="OUTCOME_REACHED"), readings={})["Lifecycle_State"] == \
        "OUTCOME_REACHED"


def _theses(*cands):
    return [build_thesis(c, readings={}) for c in cands]


def test_spine_is_set_by_the_highest_timeframe_adopted_thesis():
    side, info = ticker_spine(_theses(_cand("W", "1w", "BULL"), _cand("D", "1d", "BEAR")))
    assert side == "BULL" and info["side_setter_id"] == "W" and info["top_timeframe"] == "1w"
    assert info["conflicting_ids"] == ["D"]


def test_opposite_theses_on_the_top_timeframe_are_unresolved():
    side, info = ticker_spine(_theses(_cand("W1", "1w", "BULL"), _cand("W2", "1w", "BEAR"), _cand("D", "1d", "BULL")))
    assert side == "UNASSIGNED" and info["reason"] == "SAME_TIMEFRAME_CONFLICT"


def test_intraday_never_sets_the_side():
    side, info = ticker_spine(_theses(_cand("I", "60m", "BULL")))
    assert side == "UNASSIGNED" and info["reason"] == "NO_ADOPTED_THESIS_ON_TESTED_TIMEFRAME"


def test_refused_theses_do_not_set_the_side():
    side, info = ticker_spine(_theses(_cand("M", "1mo", "BEAR", levels="WRONG_SIDE"), _cand("D", "1d", "BULL")))
    assert side == "BULL" and info["top_timeframe"] == "1d"


def test_intraday_alignment_is_a_label_on_the_spine():
    """ACK 8 Oct 2026: intraday (60m/15m/5m) shows the build-up of the move. It labels the spine thesis; it never
    sets the side (untested). ALIGNED = same-side intraday thesis live; OPPOSED = only opposite-side intraday."""
    side, info = ticker_spine(_theses(_cand("W", "1w", "BULL"), _cand("I", "15m", "BULL", state="ACTIVATED")))
    assert side == "BULL" and info["intraday_alignment"] == "ALIGNED"
    side, info = ticker_spine(_theses(_cand("W", "1w", "BULL"), _cand("I", "5m", "BEAR")))
    assert side == "BULL" and info["intraday_alignment"] == "OPPOSED"
    side, info = ticker_spine(_theses(_cand("W", "1w", "BULL")))
    assert info["intraday_alignment"] == "NONE"
    side, info = ticker_spine(_theses(_cand("W", "1w", "BULL")), intraday_measured=False)
    assert info["intraday_alignment"] == "NOT_MEASURED"


def test_only_the_thesis_step_assigns_the_ticker_side_in_discovery():
    tree = ast.parse((ROOT / "avshunter_discovery_ULTIMATE.py").read_text(encoding="utf-8-sig"))
    writes = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
              for t in n.targets if isinstance(t, ast.Name) and t.id == "_thesis_side"]
    assert len(writes) == 1
    call = writes[0].value
    assert isinstance(call, ast.Subscript) and isinstance(call.value, ast.Name) and call.value.id == "_spine"
