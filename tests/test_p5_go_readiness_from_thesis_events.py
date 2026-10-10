"""Phase 5.3 (ACK 8 Oct 2026, "Thesis activated"): GO means the thesis's OWN trigger has been accepted.

Business rules:
- Readiness has ONE owner: Discovery's event step, from the governing thesis's own events on its own levels.
  READY_FOR_HUMAN_REVIEW = an accepted break (BREAK_ACCEPTED) or a held retest (RETEST_HELD) on the thesis side that
  has not since been invalidated, failed its retest or reached its outcome. A thesis whose trigger has not been
  accepted is WAIT_TRIGGER (armed, never dropped). Events not measured are NOT_MEASURED (missing is never neutral).
- The last event alone does not decide: a VWAP cross after an accepted break does not undo the activation.
- The trigger layer's GO flag (trigger_go_eligible, read by Morning, EOD, PSE and pre-trade) mirrors that readiness;
  the state-category rule (primary in GO_ELIGIBLE_PRIMARIES) is kept only as legacy_state_go_eligible (audit).
- Phase 0: trigger_primary is a state reading from another module; it never fired VWAP or TRAP and was unrelated to the
  thesis's own levels, so it cannot say whether the thesis's move has started.
"""
from pathlib import Path

from contracts.thesis_record import THESIS_SPINE_FIELDS, build_thesis, event_readiness
from trigger_layer import build_trigger_block

ROOT = Path(__file__).resolve().parents[1]
READY = "READY_FOR_HUMAN_REVIEW"


def _ev(*names):
    return [{"event": n, "date": f"2026-10-0{i + 1}", "level": 100.0, "interval": "1d"} for i, n in enumerate(names)]


# ------------------------------------------------------------------ the readiness rule (one owner)
def test_accepted_break_on_the_thesis_side_is_ready():
    out = event_readiness(_ev("BREAK_ATTEMPT_UP", "BREAK_ACCEPTED_UP"), side="BULL", adoption_state="ADOPTED",
                          events_status="MEASURED")
    assert out["Readiness"] == READY and out["Readiness_Event"] == "BREAK_ACCEPTED_UP"
    assert out["Readiness_Event_Date"] == "2026-10-02"


def test_held_retest_is_ready_and_a_later_vwap_cross_does_not_undo_it():
    out = event_readiness(_ev("BREAK_ACCEPTED_DOWN", "RETEST_HELD_DOWN", "VWAP_RECLAIM"), side="BEAR",
                          adoption_state="ADOPTED", events_status="MEASURED")
    assert out["Readiness"] == READY and out["Readiness_Event"] == "RETEST_HELD_DOWN"


def test_attempt_only_or_opposite_side_acceptance_waits_for_the_trigger():
    assert event_readiness(_ev("BREAK_ATTEMPT_UP"), side="BULL", adoption_state="ADOPTED",
                           events_status="MEASURED")["Readiness"] == "WAIT_TRIGGER"
    assert event_readiness(_ev("BREAK_ACCEPTED_DOWN"), side="BULL", adoption_state="ADOPTED",
                           events_status="MEASURED")["Readiness"] == "WAIT_TRIGGER"
    assert event_readiness([], side="BULL", adoption_state="ADOPTED", events_status="MEASURED")["Readiness"] \
        == "WAIT_TRIGGER"


def test_activation_is_closed_by_invalidation_failed_retest_or_outcome():
    for closing, state in (("INVALIDATED", "CLOSED_INVALIDATED"), ("RETEST_FAILED_UP", "CLOSED_RETEST_FAILED"),
                           ("OUTCOME_REACHED", "CLOSED_OUTCOME_REACHED")):
        out = event_readiness(_ev("BREAK_ACCEPTED_UP", closing), side="BULL", adoption_state="ADOPTED",
                              events_status="MEASURED")
        assert out["Readiness"] == state, closing


def test_unmeasured_events_and_unadopted_theses_are_never_ready():
    assert event_readiness([], side="BULL", adoption_state="ADOPTED",
                           events_status="NOT_MEASURED:NO_BARS")["Readiness"] == "NOT_MEASURED"
    assert event_readiness(_ev("BREAK_ACCEPTED_UP"), side=None, adoption_state="UNRESOLVED",
                           events_status="MEASURED")["Readiness"] == "NOT_ADOPTED"


def test_the_thesis_record_no_longer_states_readiness_from_the_engine_state():
    cand = {"Candidate_ID": "X|1d|A|2026-10-01", "Timeframe": "1d", "Signal_State": "ACTIVATED",
            "Proposed_Side": "BULL", "Levels_Status": "COMPLETE", "Family": "BREAKOUT"}
    assert build_thesis(cand, readings={})["Readiness"] == "PENDING_EVENTS"


# ------------------------------------------------------------------ Discovery publishes it with the thesis
def test_discovery_publishes_readiness_with_the_thesis_fields():
    assert {"thesis__readiness", "thesis__readiness_reason", "thesis__readiness_event_date"} <= set(THESIS_SPINE_FIELDS)
    src = (ROOT / "avshunter_discovery_ULTIMATE.py").read_text(encoding="utf-8-sig")
    assert "event_readiness(" in src


# ------------------------------------------------------------------ the trigger layer mirrors it
def test_go_flag_is_the_thesis_readiness_not_the_state_category():
    state_break = {"options_direction": "CALL", "phase": "C", "wyckoff_phase_bucket": "MARKUP", "adx_14": 22,
                   "catalyst_proximity": "WITHIN_3D", "days_in_range": 4, "asof_date": "2026-08-28"}
    waiting = build_trigger_block({**state_break, "thesis__readiness": "WAIT_TRIGGER"})
    assert waiting["primary"] == "RANGE_BREAK_EARLY" and waiting["legacy_state_go_eligible"] is True
    assert waiting["go_eligible"] is False and waiting["go_reason"] == "THESIS_WAIT_TRIGGER"

    ready = build_trigger_block({"thesis__readiness": READY, "geometry_justification": "JUSTIFIED"})   # no state trigger at all
    assert ready["primary"] == "NONE" and ready["go_eligible"] is True
    assert ready["go_basis"] == "THESIS_READINESS_V1"


def test_missing_readiness_is_not_go():
    block = build_trigger_block({"crabel_state": "COILING", "crabel_compression": 0.94, "atr_percentile_rank": 8.3,
                                 "ivp_label": "CHEAP"})
    assert block["go_eligible"] is False and block["go_reason"] == "THESIS_READINESS_NOT_RECORDED"


def test_the_ws2_spine_carries_the_readiness_into_the_trigger_layer():
    src = (ROOT / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    cols = src.split("_WS2_TRIGGER_INPUT_COLS = (", 1)[1].split(")", 1)[0]
    assert '"thesis__readiness"' in cols


# ------------------------------------------------------------------ consumers do not re-derive GO from the state
def test_dormant_ede_reads_the_go_flag_not_the_state_category():
    import execution_decision_engine as ede
    r = ede.EDEResult()
    r.ev_10d, r.trigger_count, r.trigger_quality = 0.01, 1, "SINGLE"
    r.trigger_primary, r.trigger_go_eligible = "VWAP_RECLAIM", True
    assert ede.sovereign_event_gate(r) == (True, "PASS")
    r.trigger_primary, r.trigger_go_eligible = "RANGE_BREAK", False
    assert ede.sovereign_event_gate(r) == (False, "THESIS_NOT_ACTIVATED")


def test_evening_price_confirmation_is_the_thesis_readiness():
    from domain import pretrade_focus
    src = Path(pretrade_focus.__file__).read_text(encoding="utf-8")
    body = src.split("def project_evening_thesis", 1)[1]
    assert 'trigger != "RANGE_BREAK"' not in body
    assert "thesis__readiness" in body
