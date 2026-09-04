from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def test_wyckoff_phase_c_ambiguity_is_not_actionable():
    src = read("WyckoffEngine_3101_v2.py")
    assert "scores['Spring'] = 55" not in src
    assert "scores['UTAD'] = 55" not in src
    assert "scores['Spring'] = 45" in src
    assert "scores['UTAD'] = 45" in src


def test_empty_event_path_does_not_force_confidence_floor():
    src = read("WyckoffEngine_3101_v2.py")
    assert "event_confidence = 70" not in src
    assert "event_confidence = 30" in src


def test_precore_missing_and_ambiguous_paths_stay_uncertain():
    src = read("wyckoff_crabel_precor_logic_v2.py")
    assert '"wyckoff_phase": "UNKNOWN"' in src
    assert 'return "B", 70.0, notes' not in src
    assert 'return "NONE", 70.0' not in src
    assert 'Phase C SHIFTING in accumulation - direction unresolved' in src


def test_trap_engine_uses_canonical_control_and_event_vwap():
    src = read("avshunter_trap_engine.py")
    assert "SHIFTING_BULLISH" not in src
    assert "SHIFTING_BEARISH" not in src
    assert 'vwap_reclaim = "VWAP_RECLAIM" in trigger_primary or "VWAP_RECLAIM" in trigger_codes' in src
    assert '"VWAP_LOSS" in trigger_primary' in src


def test_vwap_trigger_names_are_directionally_distinct():
    from trigger_layer import _t2_vwap_reclaim

    common = {
        "control_state": "SHIFTING",
        "volume_ratio_x": 1.5,
    }
    assert _t2_vwap_reclaim({
        **common,
        "vwap_bias": "ABOVE",
        "layer1__control__controller": "BUYERS",
        "direction": "CALL",
    }) == "VWAP_RECLAIM"
    assert _t2_vwap_reclaim({
        **common,
        "vwap_bias": "BELOW",
        "layer1__control__controller": "SELLERS",
        "direction": "PUT",
    }) == "VWAP_LOSS"


def test_morning_gate_missing_data_fails_closed():
    src = read("morning_gate.py")
    assert "CANNOT_VERIFY - live price unavailable" in src
    assert "MISSING_AUTHORITATIVE_STOP" in src
    assert "WARN - no invalidation level on record" not in src
    assert "EOD structure assumed intact" not in src


def test_options_intelligence_does_not_default_missing_direction_to_call():
    src = read("scripts/avshunter_options_intelligence.py")
    assert "or 'CALL'" not in src
    assert '"reason": "DATA_INSUFFICIENT - options direction unavailable"' in src


def test_ml_control_map_accepts_canonical_states():
    src = read("ml_confidence_layer/ml_confidence_engine.py")
    assert '"EQUILIBRIUM": 1' in src
    assert '"SHIFTING": 0.5' in src
    assert '"UNKNOWN": 1' in src


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
