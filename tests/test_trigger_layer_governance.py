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


def test_pcr_cannot_manufacture_far_trap_without_signed_flow():
    row = {
        "options_direction": "PUT",
        "precor_intent": "SELL_SETUP",
        "pcr_signal": "BULLISH",
        "control_state": "SHIFTING",
        "layer1__control__controller": "BUYERS",
        "catalyst_proximity": "FAR",
    }
    assert "TRAP" not in evaluate_triggers(row)


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


# --- The trigger layer reads the canonical volume_ratio (ACK 18 Sep 2026) ------------------------------------------
# Run 20260918_112522: the spine carries `volume_ratio`; the layer asked for the merge-suffixed `volume_ratio_x`,
# read 0.0, and the volume-confirmed RANGE_BREAK never fired (49 rows would have, 37 of them newly GO-eligible).

def test_volume_confirmed_range_break_uses_the_canonical_volume_ratio():
    from trigger_layer import T3_CONF_ADX_MIN, T3_CONF_PHASES, _t3_range_break

    row = {"wyckoff_phase_bucket": sorted(T3_CONF_PHASES)[0], "ema_stack": "MIXED",
           "adx_14": T3_CONF_ADX_MIN + 1, "volume_ratio": 1.6}
    assert _t3_range_break(row) == "RANGE_BREAK"


def test_vwap_trigger_uses_the_canonical_volume_ratio():
    from trigger_layer import _t2_vwap_reclaim

    assert _t2_vwap_reclaim({"control_state": "SHIFTING", "volume_ratio": 1.5, "vwap_bias": "ABOVE",
                             "layer1__control__controller": "BUYERS", "direction": "CALL"}) == "VWAP_RECLAIM"


def test_ws2_spine_passes_the_canonical_volume_ratio_to_the_trigger_layer():
    import intelligent_orchestrator as orch

    assert "volume_ratio" in orch._WS2_TRIGGER_INPUT_COLS
    assert "volume_ratio_x" not in orch._WS2_TRIGGER_INPUT_COLS
