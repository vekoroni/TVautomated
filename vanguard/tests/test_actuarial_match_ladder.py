from types import SimpleNamespace

import pandas as pd

from vanguard.layer2_statistical.actuarial_query import ActuarialQueryEngine


BASE_STATE = {
    "vol_regime": "NORMAL",
    "trend_direction": "UP",
    "structure_quality": "STRONG",
    "phase_v2": "CONTINUATION",
    "momentum_bucket": "HIGH",
    "location_bucket": "MID_RANGE",
    "preferred_horizon": "10D",
}

BASE_OUTCOMES = {
    "outcome_5d_return": 0.03,
    "outcome_10d_return": 0.05,
    "outcome_20d_return": 0.08,
    "outcome_hit_5pct_up_5d": 1,
    "outcome_hit_7pct_up_10d": 1,
    "outcome_hit_10pct_up": 1,
    "outcome_hit_5pct_down_before_10up": 0,
    "outcome_max_drawdown_5d": -0.01,
    "outcome_max_drawdown_10d": -0.02,
    "outcome_max_drawdown_20d": -0.03,
    "outcome_days_to_10pct": 8,
    "outcome_category": "WIN",
}


def _state(**overrides):
    data = dict(BASE_STATE)
    data.update(overrides)
    return SimpleNamespace(**data)


def _rows(count, **overrides):
    row = dict(BASE_STATE)
    row.update(BASE_OUTCOMES)
    row.update(overrides)
    return [dict(row) for _ in range(count)]


def _engine(rows):
    engine = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    engine.df = pd.DataFrame(rows)
    engine._has_5d_cols = False
    engine._has_10d_cols = False
    engine._has_v6_cols = True
    return engine


def test_match_ladder_exact_match_returns_exact_metadata():
    engine = _engine(_rows(70))

    result = engine._find_similar_states(_state())

    assert result.attrs["state_match_method"] == "EXACT"
    assert result.attrs["state_match_stage"] == "EXACT"
    assert result.attrs["state_match_is_exact"] is True
    assert result.attrs["state_match_similarity"] == 1.0
    assert result.attrs["sample_size"] == 70
    assert result.attrs["preferred_horizon"] == "10D"
    assert result.attrs["fallback_reason"] == "NONE"


def test_exact_match_high_sample_confidence_and_full_weight():
    engine = _engine(_rows(130))

    result = engine.query(_state())

    assert result.state_match_method == "EXACT"
    assert result.sample_confidence_bucket == "HIGH"
    assert result.confidence_penalty == 1.0
    assert result.confidence_weight == 1.0


def test_match_ladder_relaxed_preserves_major_dimensions():
    rows = []
    rows.extend(_rows(20))
    rows.extend(_rows(100, phase_v2="EXHAUSTION", momentum_bucket="LOW", location_bucket="NEAR_LOW"))
    engine = _engine(rows)

    result = engine._find_similar_states(_state())

    assert result.attrs["state_match_method"] == "RELAXED"
    assert result.attrs["state_match_stage"] == "RELAXED"
    assert result.attrs["state_match_is_exact"] is False
    assert result.attrs["state_match_dimensions"] == (
        "vol_regime|trend_direction|structure_quality|preferred_horizon"
    )
    assert result.attrs["sample_size"] == 120
    assert "EXACT_SAMPLE_BELOW_MIN" in result.attrs["fallback_reason"]
    assert result.attrs["confidence_weight"] < 1.0


def test_relaxed_too_thin_falls_to_analogue():
    rows = []
    rows.extend(_rows(20))
    rows.extend(_rows(50, phase_v2="EXHAUSTION", momentum_bucket="LOW", location_bucket="NEAR_LOW"))
    rows.extend(_rows(110, preferred_horizon="20D", location_bucket="NEAR_LOW"))
    engine = _engine(rows)

    result = engine._find_similar_states(_state())

    assert result.attrs["state_match_method"] == "ANALOGUE"
    assert result.attrs["state_match_stage"] == "ANALOGUE"
    assert result.attrs["state_match_is_exact"] is False
    assert result.attrs["state_match_similarity"] >= 0.85
    assert result.attrs["sample_size"] == 130
    assert "RELAXED_SAMPLE_BELOW_MIN" in result.attrs["fallback_reason"]


def test_analogue_with_similarity_above_085_gets_analogue_weight():
    engine = _engine(_rows(110, preferred_horizon="20D", location_bucket="NEAR_LOW"))

    result = engine._find_similar_states(_state())

    assert result.attrs["state_match_method"] == "ANALOGUE"
    assert result.attrs["state_match_similarity"] == 0.9
    assert result.attrs["confidence_weight"] == 0.70


def test_match_ladder_unknown_is_fail_closed_without_high_confidence():
    rows = _rows(
        150,
        vol_regime="EXPANSION",
        trend_direction="DOWN",
        structure_quality="WEAK",
        phase_v2="EXHAUSTION",
        momentum_bucket="LOW",
        location_bucket="NEAR_LOW",
        preferred_horizon="20D",
    )
    engine = _engine(rows)

    result = engine._find_similar_states(_state())

    assert result.empty
    assert result.attrs["state_match_method"] == "UNKNOWN"
    assert result.attrs["state_match_stage"] == "UNKNOWN"
    assert result.attrs["state_match_quality"] == "INSUFFICIENT_SAMPLE"
    assert result.attrs["sample_confidence_bucket"] == "UNKNOWN"
    assert result.attrs["confidence_penalty"] == 0.30
    assert result.attrs["state_match_similarity"] == 0.0
    assert result.attrs["state_match_is_exact"] is False
    assert result.attrs["sample_size"] == 0
    assert "ANALOGUE_SAMPLE_OR_SIMILARITY_BELOW_MIN" in result.attrs["fallback_reason"]


def test_probability_shrinkage_uses_baseline_plus_weighted_delta():
    rows = []
    rows.extend(_rows(40, preferred_horizon="5D", outcome_hit_5pct_up_5d=1, outcome_5d_return=0.08))
    rows.extend(_rows(
        40,
        vol_regime="EXPANSION",
        preferred_horizon="5D",
        outcome_hit_5pct_up_5d=0,
        outcome_5d_return=-0.04,
    ))
    engine = _engine(rows)

    result = engine.query(_state(preferred_horizon="5D"))

    expected = result.baseline_probability + result.confidence_weight * (
        result.raw_prob_target_hit - result.baseline_probability
    )
    assert result.state_match_method == "EXACT"
    assert result.sample_confidence_bucket == "MEDIUM"
    assert result.confidence_weight == 0.80
    assert round(result.adjusted_prob_target_hit, 6) == round(expected, 6)


def test_unknown_uses_baseline_probability_and_zero_edge():
    rows = _rows(
        150,
        vol_regime="EXPANSION",
        trend_direction="DOWN",
        structure_quality="WEAK",
        phase_v2="EXHAUSTION",
        momentum_bucket="LOW",
        location_bucket="NEAR_LOW",
        outcome_hit_10pct_up=1,
    )
    engine = _engine(rows)

    result = engine.query(_state())

    assert result.state_match_method == "UNKNOWN"
    assert result.confidence_penalty == 0.30
    assert result.adjusted_prob_target_hit == result.baseline_probability
    assert result.probability_edge == 0.0
    assert result.probability_verdict == "NO_STAT_EDGE"
