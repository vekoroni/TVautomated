from scripts.actuarial_enrichment_pass import _preserve_phase2_baton_fields
from scripts.run_vanguard_from_packages import (
    PHASE2_REQUIRED_FLATTENED_FIELDS,
    _ensure_phase2_baton_fields,
    phase2_baton_dropped_fields,
    validate_phase2_baton,
)


def _valid_row(**overrides):
    row = {
        "layer2__state_match_method": "EXACT",
        "layer2__state_match_stage": "EXACT",
        "layer2__state_match_dimensions": "vol_regime|trend_direction",
        "layer2__state_match_quality": "HIGH_SAMPLE",
        "layer2__state_match_similarity": 1.0,
        "layer2__state_match_is_exact": True,
        "layer2__sample_size": 150,
        "layer2__sample_confidence_bucket": "HIGH",
        "layer2__confidence_penalty": 1.0,
        "layer2__confidence_weight": 1.0,
        "layer2__preferred_horizon": "20D",
        "layer2__matched_state_key": "vol_regime=NORMAL",
        "layer2__original_state_key": "vol_regime=NORMAL",
        "layer2__fallback_reason": "NONE",
        "layer2__raw_prob_up_5d": 0.55,
        "layer2__raw_prob_up_10d": 0.57,
        "layer2__raw_prob_up_20d": 0.60,
        "layer2__raw_prob_down_5d": 0.45,
        "layer2__raw_prob_down_10d": 0.43,
        "layer2__raw_prob_down_20d": 0.40,
        "layer2__raw_prob_target_hit": 0.60,
        "layer2__raw_prob_stop_hit": 0.25,
        "layer2__raw_expected_return": 0.04,
        "layer2__raw_expected_drawdown": -0.03,
        "layer2__raw_expected_time_to_target": 9,
        "layer2__baseline_probability": 0.50,
        "layer2__adjusted_prob_target_hit": 0.60,
        "layer2__adjusted_expected_return": 0.04,
        "layer2__probability_edge": 0.10,
        "layer2__probability_verdict": "STRONG_EDGE",
    }
    row.update(overrides)
    return row


def test_phase2_validation_accepts_valid_baton():
    assert validate_phase2_baton(_valid_row()) == []


def test_analogue_with_null_similarity_fails_validation():
    issues = validate_phase2_baton(_valid_row(
        layer2__state_match_method="ANALOGUE",
        layer2__state_match_similarity="",
        layer2__confidence_penalty=0.50,
        layer2__confidence_weight=0.50,
    ))

    assert "INVALID:ANALOGUE_MISSING_SIMILARITY" in issues


def test_analogue_below_similarity_floor_fails_validation():
    issues = validate_phase2_baton(_valid_row(
        layer2__state_match_method="ANALOGUE",
        layer2__state_match_similarity=0.69,
        layer2__confidence_penalty=0.35,
        layer2__confidence_weight=0.35,
    ))

    assert "INVALID:ANALOGUE_SIMILARITY_BELOW_0_70" in issues


def test_unknown_positive_edge_is_safely_downgraded():
    row = _valid_row(
        layer2__state_match_method="UNKNOWN",
        layer2__sample_confidence_bucket="HIGH",
        layer2__confidence_penalty=0.90,
        layer2__confidence_weight=0.90,
        layer2__probability_edge=0.12,
        layer2__probability_verdict="STRONG_EDGE",
    )

    assert "INVALID:UNKNOWN_POSITIVE_PROBABILITY_EDGE" in validate_phase2_baton(row)
    _ensure_phase2_baton_fields(row)

    assert row["layer2__sample_confidence_bucket"] == "UNKNOWN"
    assert row["layer2__confidence_penalty"] == 0.30
    assert row["layer2__confidence_weight"] == 0.30
    assert row["layer2__probability_edge"] == 0.0
    assert row["layer2__probability_verdict"] == "NO_STAT_EDGE"
    assert row["phase2_baton_status"] == "VALID"


def test_downstream_baton_field_drop_detection():
    upstream = _valid_row()
    downstream = dict(upstream)
    downstream.pop("layer2__confidence_weight")

    assert phase2_baton_dropped_fields(upstream, downstream) == ["layer2__confidence_weight"]


def test_package_json_preserves_phase2_layer2_keys():
    row = _valid_row()

    block = _preserve_phase2_baton_fields(
        {},
        vanguard_row=row,
        existing_actuarial={},
    )

    assert block["phase2_baton_status"] == "VALID"
    assert not block["phase2_baton_missing_fields"]
    for field in PHASE2_REQUIRED_FLATTENED_FIELDS:
        assert field in block
        assert field in block["phase2_baton"]
