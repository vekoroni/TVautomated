from __future__ import annotations

from trigger_layer import build_trigger_block, evaluate_triggers


def _range_break_row(**overrides):
    row = {
        "options_direction": "CALL",
        "phase": "C",
        "wyckoff_phase_bucket": "MARKUP",
        "adx_14": 22,
        "catalyst_proximity": "WITHIN_3D",
        "days_in_range": 4,
        "asof_date": "2026-08-28",
    }
    row.update(overrides)
    return row


def test_far_context_does_not_suppress_independent_range_break():
    row = _range_break_row(catalyst_proximity="FAR")
    block = build_trigger_block(row)

    assert "RANGE_BREAK_EARLY" in evaluate_triggers(row)
    assert block["stale"] is False
    assert block["freshness_state"] == "UNKNOWN"
    assert block["context_state"] == "EARLY_FORMATION_ABSENT"
    assert block["go_eligible"] is True


def test_extended_range_is_context_not_data_staleness():
    block = build_trigger_block(_range_break_row(days_in_range=18))

    assert block["primary"] == "RANGE_BREAK_EARLY"
    assert block["stale"] is False
    assert block["context_state"] == "RANGE_EXTENDED"
    assert block["go_eligible"] is True


def test_far_trap_is_retained_for_human_wall_review():
    row = {
        "options_direction": "PUT",
        "precor_intent": "SELL_SETUP",
        "pcr_signal": "BULLISH",
        "control_state": "SHIFTING",
        "layer1__control__controller": "BUYERS",
        "catalyst_proximity": "FAR",
    }
    assert "TRAP" in evaluate_triggers(row)


def test_explicit_stale_source_retains_observation_but_blocks_go():
    block = build_trigger_block(
        _range_break_row(trigger_source_freshness="STALE")
    )

    assert block["primary"] == "RANGE_BREAK_EARLY"
    assert block["stale"] is True
    assert block["freshness_state"] == "STALE"
    assert block["go_eligible"] is False


def test_governed_source_date_computes_session_age():
    fresh = build_trigger_block(
        _range_break_row(trigger_source_asof="2026-08-27")
    )
    stale = build_trigger_block(
        _range_break_row(trigger_source_asof="2026-08-24")
    )

    assert fresh["freshness_state"] == "FRESH"
    assert fresh["age_sessions"] == 1
    assert stale["freshness_state"] == "STALE"
    assert stale["age_sessions"] == 4
    assert stale["go_eligible"] is False
