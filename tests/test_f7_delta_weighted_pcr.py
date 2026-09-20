"""F7 (ACK, 19 Sep 2026): delta-weighted options flow is computed from real chain data.

Deep dive: compute_delta_weighted_oi was called throughout avshunter_options_intelligence.py
(dw_call_exposure_m, dw_put_exposure_m, dw_ratio, dw_signal, dw_pcr_vol) but was never defined.
The call site's broad `except Exception: dw_data = {}` swallowed the resulting NameError silently,
so every row reported "OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE" and fell back to OI-only PCR even on
tickers where chain_snapshots.volume was genuinely populated (~50% of contracts, per the audit).
"""
from __future__ import annotations

import pandas as pd

import scripts.avshunter_options_intelligence as oi
import scripts.avshunter_superbrain_layer as sb
import execution_intelligence_runner as execution_runner
import trigger_layer
from pipeline_interpreter.direction_conflict_resolver import resolve_direction


def _chain(rows):
    return pd.DataFrame(rows)


def test_function_exists_and_is_wired_at_the_call_site():
    assert hasattr(oi, "compute_delta_weighted_oi")
    import inspect
    call_site = inspect.getsource(oi)
    block = call_site[call_site.index("Delta-weighted OI flow"): call_site.index("Delta-weighted OI flow") + 300]
    assert "compute_delta_weighted_oi(chain, spot)" in block


def test_volume_pcr_uses_real_printed_volume_not_a_bucket_default():
    chain = _chain([
        {"right": "C", "open_interest": 1000, "delta": 0.40, "volume": 500},
        {"right": "P", "open_interest": 1000, "delta": -0.40, "volume": 1500},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=100.0)
    assert result["dw_pcr_vol"] == 3.0  # 1500 put volume / 500 call volume, from real printed volume


def test_delta_weighted_ratio_differs_from_plain_oi_pcr_when_deltas_differ():
    # Equal open interest both sides, but puts carry much larger delta magnitude -
    # a delta-weighted ratio must diverge from the flat 1.0 an OI-only PCR would report.
    chain = _chain([
        {"right": "C", "open_interest": 1000, "delta": 0.10, "volume": None},
        {"right": "P", "open_interest": 1000, "delta": -0.80, "volume": None},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=50.0)
    assert result["dw_ratio"] == 8.0  # (0.80*1000) / (0.10*1000)
    assert result["dw_signal"] == "PUT_HEAVY"
    assert result["oi_positioning_state"] == "PUT_HEAVY"
    assert result["option_activity_state"] == "POSITIONING_ONLY"
    assert result["activity_directional_inference"] == "AMBIGUOUS"
    assert result["activity_authority"] == "ADVISORY_ONLY"


def test_no_printed_volume_anywhere_reports_unavailable_not_fabricated():
    chain = _chain([
        {"right": "C", "open_interest": 500, "delta": 0.35, "volume": None},
        {"right": "P", "open_interest": 500, "delta": -0.35, "volume": None},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=75.0)
    assert result["dw_pcr_vol"] is None
    status = (
        'OK' if result.get('dw_pcr_vol') is not None else 'OI_ONLY_NO_INTRADAY_VOLUME'
    )
    assert status == 'OI_ONLY_NO_INTRADAY_VOLUME'


def test_empty_chain_returns_unknown_without_raising():
    result = oi.compute_delta_weighted_oi(pd.DataFrame(), spot=100.0)
    assert result["dw_pcr_vol"] is None
    assert result["dw_signal"] == "UNKNOWN"
    assert result["option_activity_state"] == "INSUFFICIENT_EVIDENCE"


def test_oi_and_volume_are_combined_without_inventing_signed_flow():
    chain = _chain([
        {"right": "C", "open_interest": 1000, "delta": 0.50, "volume": 100},
        {"right": "P", "open_interest": 2000, "delta": -0.50, "volume": 300},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=100.0)
    assert result["oi_positioning_state"] == "PUT_HEAVY"
    assert result["volume_activity_state"] == "PUT_HEAVY"
    assert result["option_activity_state"] == "PUT_ACTIVITY_WITH_PUT_HEAVY_POSITIONING"
    assert result["activity_evidence_strength"] == "CORROBORATED"
    assert result["activity_directional_inference"] == "AMBIGUOUS"


def test_conflicting_positioning_and_volume_are_explicitly_mixed():
    chain = _chain([
        {"right": "C", "open_interest": 2000, "delta": 0.50, "volume": 100},
        {"right": "P", "open_interest": 500, "delta": -0.50, "volume": 300},
    ])
    result = oi.compute_delta_weighted_oi(chain, spot=100.0)
    assert result["oi_positioning_state"] == "CALL_HEAVY"
    assert result["volume_activity_state"] == "PUT_HEAVY"
    assert result["option_activity_state"] == "MIXED_ACTIVITY"
    assert result["activity_evidence_strength"] == "CONFLICTED"


def test_activity_state_cannot_change_options_score_contribution():
    states = [
        {"option_activity_state": "CALL_ACTIVITY_WITH_CALL_HEAVY_POSITIONING"},
        {"option_activity_state": "PUT_ACTIVITY_WITH_PUT_HEAVY_POSITIONING"},
        {"option_activity_state": "MIXED_ACTIVITY"},
        {"option_activity_state": "INSUFFICIENT_EVIDENCE"},
    ]
    contributions = [oi._activity_score_baseline(state)[0] for state in states]
    assert contributions == [3.0, 3.0, 3.0, 3.0]


def test_oi_pcr_never_confirms_or_conflicts_with_thesis_direction():
    for direction in ("CALL", "PUT"):
        for state in ("CALL_HEAVY", "PUT_HEAVY", "BALANCED", "BULLISH", "BEARISH"):
            result = oi._direction_conflict_status_oi(direction, state, 2.0)
            assert result["pcr_direction_conflict_status"] == "PCR_POSITIONING_CONTEXT_ONLY"
            assert result["pcr_confidence_weight"] == 0.0


def test_superbrain_does_not_turn_pcr_or_oi_into_directional_vetoes():
    warnings, adjustment = sb.apply_behavioural_vetoes(
        {
            "direction": "CALL",
            "pcr_vol": 20.0,
            "dw_signal": "STRONGLY_BEARISH",
            "hold_label": "1_5d",
        },
        {},
    )
    assert adjustment == ""
    assert not any("V6_PCR" in warning or "V8_DW" in warning for warning in warnings)


def test_legacy_pcr_cannot_manufacture_a_trap_trigger():
    row = {
        "direction": "CALL",
        "precor_intent": "BUY_SETUP",
        "pcr_signal": "BEARISH",
        "control_state": "SELLERS",
        "layer1__auction_state": "TRANSITIONING",
        "layer1__control__controller": "SELLERS",
    }
    assert trigger_layer._t4_trap(row) is None


def test_interpreter_treats_even_legacy_directional_pcr_as_neutral_context():
    result = resolve_direction({"direction": "CALL", "pcr_signal": "BEARISH"})
    pcr_layer = next(item for item in result["layer_detail"] if item["layer"].startswith("3."))
    assert pcr_layer["vote"] == "NEUTRAL"
    assert "advisory_only" in pcr_layer["reason"]
    assert result["dominant_direction"] == "CALL"
    assert result["misdiagnosed"] is False


def test_execution_handoff_retires_legacy_pcr_conflict_during_replay():
    frame = pd.DataFrame([{
        "ticker": "AAA",
        "direction": "CALL",
        "options_verdict": "EXECUTE",
        "pcr_signal": "BEARISH",
        "pcr_oi": 2.0,
        "pcr_direction_conflict_status": "PCR_CONFLICT_REQUIRES_FLOW_CONFIRMATION",
        "pcr_direction_conflict_reason": "legacy PCR conflict",
        "direction_conflict_status": "UNRESOLVED",
        "direction_conflict_reason": "legacy PCR conflict",
    }])
    result = execution_runner._ensure_eil_audit_contract(frame).iloc[0]
    assert result["pcr_direction_conflict_status"] == "PCR_POSITIONING_CONTEXT_ONLY"
    assert result["direction_conflict_status"] == "NO_CONFLICT"
    assert result["direction_conflict_reason"] == ""
