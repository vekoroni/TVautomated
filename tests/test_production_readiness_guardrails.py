from datetime import date

from catalyst_truth_engine import SourceBundle, _score
from intelligent_orchestrator import (
    _macro_core_required,
    _neutral_macro_payload,
    _strict_actuarial_v6_enabled,
    configure_cds_runtime_for_orchestrator,
)
from scripts.macro_quant_packet import build_macro_quant_packet
from macro_horizon_router import route_signals_by_horizon


def test_pipeline_direction_cannot_masquerade_as_catalyst_evidence():
    result = _score(
        SourceBundle(
            ticker="TEST",
            sources=["discovery"],
            rows=[{
                "ticker": "TEST",
                "_catalyst_source": "discovery",
                "catalyst_type": "EARNINGS",
                "options_direction": "CALL",
                "direction": "CALL",
                "vanguard_edge_direction": "CALL",
            }],
        ),
        date(2026, 8, 27),
    )
    assert result["catalyst_direction_bias"] == ""
    assert result["catalyst_direction_independent"] is False
    assert result["catalyst_direction_source"] == ""


def test_calendar_direction_has_explicit_independent_provenance():
    result = _score(
        SourceBundle(
            ticker="TEST",
            sources=["catalyst_calendar"],
            rows=[{
                "ticker": "TEST",
                "_catalyst_source": "catalyst_calendar",
                "catalyst_type": "EARNINGS",
                "catalyst_direction_bias": "PUT",
                "catalyst_date": "2026-09-01",
                "event_status": "CONFIRMED",
            }],
        ),
        date(2026, 8, 27),
    )
    assert result["catalyst_direction_bias"] == "PUT"
    assert result["catalyst_direction_independent"] is True
    assert result["catalyst_direction_source"] == "catalyst_calendar"
    assert result["catalyst_direction_source_field"] == "catalyst_direction_bias"


def test_production_defaults_are_fail_closed_and_macro_advisory(monkeypatch, tmp_path):
    for key in (
        "AVSHUNTER_STRICT_ACTUARIAL_V6",
        "AVSHUNTER_MACRO_CORE_REQUIRED",
        "AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT",
    ):
        monkeypatch.delenv(key, raising=False)

    runtime = configure_cds_runtime_for_orchestrator(
        environment={},
        base_dir=tmp_path,
    )
    assert runtime["stage_gating_enforced"] is True
    assert _strict_actuarial_v6_enabled() is True
    assert _macro_core_required() is False

    neutral = _neutral_macro_payload()
    assert neutral["macro_capital_authority"] == "NONE"
    assert neutral["size_multiplier"] == 1.0
    assert neutral["risk_on_off_switch"] == "NEUTRAL"
    assert all(
        bucket["size_multiplier"] == 1.0
        for bucket in neutral["horizon_routing"].values()
    )
    packet = build_macro_quant_packet(neutral)
    assert packet["macro_data_quality"] == "MISSING"
    assert packet["macro_freshness_status"] == "MISSING"
    assert packet["macro_execution_caution"] == "MACRO_UNAVAILABLE_ADVISORY_ONLY"


def test_risk_off_macro_cannot_block_or_resize_core_signals(tmp_path):
    import json

    macro = _neutral_macro_payload()
    macro["regime_state"] = "CRISIS"
    macro["risk_on_off_switch"] = "RISK_OFF"
    for bucket in macro["horizon_routing"].values():
        bucket["size_multiplier"] = 0.1
    path = tmp_path / "macro.json"
    path.write_text(json.dumps(macro), encoding="utf-8")

    routed = route_signals_by_horizon(path, [
        {"ticker": "CALLX", "instrument": "CALL", "dte": 30, "hold_days": 7},
        {"ticker": "PUTX", "instrument": "PUT", "dte": 30, "hold_days": 7},
    ])
    assert routed["blocked"] == []
    assert {item.ticker for item in routed["6_10d"]} == {"CALLX", "PUTX"}
    assert all(item.macro_permitted is True for item in routed["6_10d"])
    assert all(item.size_multiplier == 1.0 for item in routed["6_10d"])
