"""DIR-002 DWN-13: Vanguard observations cannot veto the Discovery thesis."""

from eod_candidate_engine import _direction_arbitration
from scripts.avshunter_options_intelligence import _direction_arbitration_oi


def test_eod_opposing_vanguard_direction_is_countercase_not_gate() -> None:
    row = {
        "canonical_direction": "PUT",
        "governed_direction_authority": "DISCOVERY_GOVERNED",
        "dir_calc_version": "dir_v1.3.0",
        "intent": "SELL_SETUP",
        "vanguard_edge_direction": "CALL",
    }
    result = _direction_arbitration(row)
    assert result["direction_conflict_gate"] == "NONE"
    assert result["direction_arbitration_status"] == "OPPOSING_SIDE_OBSERVATION"
    assert "PUT" in result["direction_arbitration_reason"]
    assert "CALL" in result["direction_arbitration_reason"]


def test_options_opposing_vanguard_direction_is_countercase_not_gate() -> None:
    ctx = {
        "direction": "CALL",
        "governed_direction": "CALL",
        "governed_direction_authority": "DISCOVERY_GOVERNED",
        "dir_calc_version": "dir_v1.3.0",
        "intent": "BUY_SETUP",
        "vanguard_edge_direction": "PUT",
    }
    result = _direction_arbitration_oi(ctx)
    assert result["direction_conflict_gate"] == "NONE"
    assert result["direction_arbitration_status"] == "OPPOSING_SIDE_OBSERVATION"


def test_no_vanguard_opinion_is_explicit_not_agreement() -> None:
    for result in (
        _direction_arbitration({"canonical_direction": "CALL"}),
        _direction_arbitration_oi({"direction": "CALL", "governed_direction": "CALL"}),
    ):
        assert result["direction_arbitration_status"] == "NO_PROBABILITY_OPINION"
        assert result["direction_conflict_gate"] == "NONE"
