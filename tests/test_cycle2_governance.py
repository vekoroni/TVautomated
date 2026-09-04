from eod_candidate_engine import _exit_intelligence_plan, _invalidation_level
from morning_gate import _check_invalidation
from scripts.exit_rules_engine import compute_exit_rules


def test_eod_invalidation_uses_only_governed_direction_correct_level() -> None:
    base = {
        "direction": "CALL",
        "signal_price": 100.0,
        "ATR_14": 3.0,
        "stop_loss": 95.0,
    }
    assert _invalidation_level(base) is None
    assert _invalidation_level({**base, "invalidation_spot": 94.0}) == 94.0
    assert _invalidation_level({**base, "invalidation_spot": 104.0}) is None


def test_eod_non_directional_exit_plan_is_explicitly_not_applicable() -> None:
    result = _exit_intelligence_plan(
        {"signal_price": 100.0, "wbs_grade": "PROBABLE"},
        "STRANGLE",
        None,
        0.0,
        0.0,
    )
    assert result["exit_mode"] == "NOT_APPLICABLE"
    assert result["exit_t1"] == result["exit_t2"] == result["exit_t3"] == 0.0
    assert result["exit_plan_reason"] == "NOT_EVALUATED_NON_DIRECTIONAL"


def test_exit_rules_do_not_consume_legacy_stop_aliases() -> None:
    result = compute_exit_rules({
        "canonical_direction": "CALL",
        "live_price": 100.0,
        "structural_target": 110.0,
        "structural_stop": 95.0,
        "invalidation_level": 95.0,
    })
    assert result["exit_stop_price"] is None
    assert result["exit_rr_valid"] is False


def test_morning_invalidation_fails_closed_for_missing_and_non_directional() -> None:
    passed, reason = _check_invalidation(
        {"canonical_direction": "CALL"}, live_price=100.0
    )
    assert passed is False
    assert reason.startswith("MISSING_AUTHORITATIVE_STOP")

    passed, reason = _check_invalidation(
        {"canonical_direction": "STRANGLE"}, live_price=100.0
    )
    assert passed is False
    assert reason.startswith("NOT_EVALUATED_NON_DIRECTIONAL")
