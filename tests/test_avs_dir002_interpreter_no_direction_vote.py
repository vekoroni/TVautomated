"""DWN-09: Interpreter commentary cannot replace the governed ticker side."""

from pipeline_interpreter.trade_brief_builder import build_trade_brief, format_trade_brief
from pipeline_interpreter.direction_conflict_resolver import resolve_direction


def test_interpreter_countercase_cannot_select_opposite_side_or_contract():
    brief = build_trade_brief({
        "ticker": "DIR2", "direction": "PUT", "verdict": "GO",
        "contract_symbol": "DIR2_PUT", "dcr_dominant_direction": "CALL",
        "dcr_misdiagnosed": True, "alt_contract_symbol": "DIR2_CALL",
    })
    assert brief["direction"] == "PUT"
    assert brief["direction_source"] == "PIPELINE"
    assert brief["contract"] == "DIR2_PUT"
    assert brief["advisory_conflict"] is True
    assert "overridden" not in format_trade_brief(brief).lower()


def test_interpreter_vote_cannot_direct_unassigned_thesis():
    brief = build_trade_brief({
        "ticker": "DIR2U", "direction": "UNRESOLVED", "verdict": "GO",
        "dcr_dominant_direction": "CALL", "dcr_misdiagnosed": True,
        "alt_contract_symbol": "DIR2U_CALL",
    })
    assert brief["direction"] == "UNRESOLVED"
    assert brief["action"] == "NO_EDGE"
    assert brief["contract"] == ""


def test_vanguard_probability_is_observation_not_vote_for_new_thesis():
    result = resolve_direction({
        "thesis__side": "BULL", "direction": "CALL",
        "probability_verdict": "NEGATIVE_EDGE",
    })
    actuarial = next(item for item in result["layer_detail"] if "Actuarial" in item["layer"])
    assert actuarial["vote"] == "NEUTRAL"
    assert "advisory" in actuarial["reason"].lower()
