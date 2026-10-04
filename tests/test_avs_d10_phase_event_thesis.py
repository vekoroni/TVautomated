"""XLU-D10 (ACK 2 Oct 2026): a trade is categorised by Phase and Event; there is no
"observe" decision.

Business rules:
- Each directed row carries the Phase and Event that categorise it, read from the
  behavioural reading on the trade's own side (daily first, then weekly, monthly, intraday;
  an activated event before a detected one). If structure shows events only on the other
  side, the category says so; if none, it says that.
- The EOD thesis state names the stage only; it never claims validity (no VALID_ prefix).
- OBSERVE_ONLY is not a decision anywhere: the legacy Wyckoff value is kept as lineage,
  the scenario router never routes to an OBSERVE_ONLY path, and the pre-trade flags and the
  Interpreter carry Phase and Event instead.
Evidence: run 20260930_083504 - 1,523 of 1,570 rows OBSERVE_ONLY yet VALID_*; run
20261001_211641 - wyckoff_execution_bias OBSERVE_ONLY on 1,619 of 1,672 tickers.
"""
from domain.structure_behaviour.thesis_category import thesis_category


def cand(tf, side, kind, state="DETECTED", phase="D", scope="CAMPAIGN", label="2026-09-30"):
    return {"Candidate_ID": f"T|{tf}|{scope}|{kind}|{label}", "Timeframe": tf, "Direction": side,
            "Signal_Type": kind, "Signal_State": state, "Wyckoff_Phase": phase, "Structure_Scope": scope,
            "Local_Phase": "E" if scope == "LOCAL" else None}


def readings(**by_tf):
    out = {tf: {"Status": "EVALUATED", "Wyckoff_Phase": "B", "candidates": []}
           for tf in ("1mo", "1w", "1d", "60m", "15m", "5m")}
    for tf, cands in by_tf.items():
        out[tf]["candidates"] = cands
    return out


def test_trade_is_categorised_by_the_phase_and_event_on_its_side():
    r = readings(**{"1d": [cand("1d", "BEAR", "SOW -> LPSY continuation", "ACTIVATED", phase="E"),
                           cand("1d", "BULL", "Spring Candidate", phase="C")]})
    out = thesis_category(r, "PUT")
    assert out["thesis_phase"] == "E"
    assert out["thesis_event"] == "SOW -> LPSY continuation"
    assert out["thesis_event_state"] == "ACTIVATED" and out["thesis_event_timeframe"] == "1d"
    assert out["thesis_structure_alignment"] == "ALIGNED"
    assert out["thesis_category"] == "Phase E · SOW -> LPSY continuation (activated, 1d)"


def test_daily_first_then_higher_timeframes_and_activated_before_detected():
    r = readings(**{"1w": [cand("1w", "BULL", "SOS -> LPS continuation", "ACTIVATED")],
                    "1d": [cand("1d", "BULL", "Spring Candidate", "DETECTED", phase="C")]})
    assert thesis_category(r, "CALL")["thesis_event_timeframe"] == "1d"
    r2 = readings(**{"1w": [cand("1w", "BULL", "SOS -> LPS continuation", "ACTIVATED")]})
    assert thesis_category(r2, "CALL")["thesis_event_timeframe"] == "1w"
    r3 = readings(**{"1d": [cand("1d", "BULL", "Spring Candidate", "DETECTED", phase="C", label="a"),
                            cand("1d", "BULL", "Buyer Absorption Breakout", "ACTIVATED", label="b")]})
    assert thesis_category(r3, "CALL")["thesis_event"] == "Buyer Absorption Breakout"


def test_opposing_only_and_no_event_are_stated():
    r = readings(**{"1d": [cand("1d", "BEAR", "Upthrust Candidate", phase="B")]})
    out = thesis_category(r, "CALL")
    assert out["thesis_structure_alignment"] == "OPPOSING_ONLY"
    assert out["thesis_event"] is None
    assert out["thesis_category"] == "Phase B · no event on the CALL side; opposing Upthrust Candidate (detected, 1d)"
    none = thesis_category(readings(), "PUT")
    assert none["thesis_structure_alignment"] == "NO_EVENT"
    assert none["thesis_category"] == "Phase B · no behavioural event"


def test_non_directional_trade_has_no_side_to_categorise():
    out = thesis_category(readings(), "STRANGLE")
    assert out["thesis_structure_alignment"] == "NOT_APPLICABLE_NON_DIRECTIONAL"


def test_eod_thesis_state_names_the_stage_without_claiming_validity():
    from eod_candidate_engine import _thesis_state_from_eod_status
    assert _thesis_state_from_eod_status("EOD_TRIGGER_READY") == "THESIS_TRIGGER_PENDING"
    assert _thesis_state_from_eod_status("EOD_THESIS_READY") == "THESIS_READY"
    assert _thesis_state_from_eod_status("") == "THESIS_REVIEW"
    for status in ("EOD_THESIS_READY", "EOD_THESIS_READY_REPAIR_AT_OPEN", "EOD_TRIGGER_READY",
                   "EOD_WATCHLIST_MONETISABLE", "EOD_PROBE_CANDIDATE", "EOD_DATA_INSUFFICIENT_REVIEW", ""):
        assert not _thesis_state_from_eod_status(status).startswith("VALID")


def test_scenario_router_never_routes_to_observe_only():
    from scenario_router import route_scenario
    low = route_scenario({"fusion_alignment_score": 10, "fusion_intent": "OBSERVE_ONLY",
                          "fusion_direction": "NONE", "tier": 2})
    assert low["scenario_path"] != "OBSERVE_ONLY"
    assert low["scenario_entry_type"] != "NO_ENTRY"


def test_pretrade_flags_carry_phase_and_event_not_observe():
    from domain.pretrade_focus import project_evening_thesis
    import test_evening_thesis_decision as base
    out = project_evening_thesis(base._row(wyckoff_execution_bias="OBSERVE_ONLY",
                                           thesis_structure_alignment="OPPOSING_ONLY"))
    assert "WYCKOFF_OBSERVE_ONLY" not in out["evening_evidence_flags"]
    assert "NO_BEHAVIOURAL_EVENT_ON_TRADE_SIDE" in out["evening_evidence_flags"]


def test_phase_and_event_reach_the_book_and_the_interpreter_and_observe_does_not():
    from contracts.lab_control import FINAL_BOOK_FIELDS
    from pipeline_interpreter.interactive_desk import EVIDENCE_FIELDS
    for field in ("thesis_phase", "thesis_event", "thesis_event_state", "thesis_category",
                  "thesis_structure_alignment"):
        assert field in FINAL_BOOK_FIELDS and field in EVIDENCE_FIELDS
    assert "wyckoff_execution_bias" not in EVIDENCE_FIELDS
    assert "wyckoff_phase_bucket" not in EVIDENCE_FIELDS


def test_discovery_never_publishes_observe_only_as_the_wyckoff_bias():
    import avshunter_discovery_ULTIMATE as discovery
    assert discovery._wyckoff_bias_fields("OBSERVE_ONLY") == {
        "wyckoff_execution_bias": "NO_DIRECTIONAL_BIAS", "legacy_wyckoff_execution_bias": "OBSERVE_ONLY"}
    assert discovery._wyckoff_bias_fields("BULLISH")["wyckoff_execution_bias"] == "BULLISH"
