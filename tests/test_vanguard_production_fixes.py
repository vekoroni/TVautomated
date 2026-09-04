from types import SimpleNamespace

import pandas as pd

from vanguard.config import REQUIRED_ACTUARIAL_V6_COLUMNS
from vanguard.layer2_statistical.actuarial_query import (
    ACTUARIAL_CATEGORY_COLUMNS,
    ACTUARIAL_QUERY_COLUMNS,
    MATCH_EXACT_DIMS,
    MATCH_RELAXED_DIMS,
    ActuarialQueryEngine,
)
from vanguard.layer2_statistical.edge_detector import EdgeDetector
from vanguard.layer2_statistical.scenario_builder import MultiScenarioBuilder as Layer2ScenarioBuilder
from vanguard.layer3_execution.scenario_builder import MultiScenarioBuilder as Layer3ScenarioBuilder
from vanguard.integration.orchestrator_adapter import OrchestratorAdapter
from vanguard.layer2_statistical.state_calculator import StateVectorCalculator


def _state(**overrides):
    base = dict(
        ticker="TEST",
        macro_regime="TRANSITIONAL",
        intraday_rows=0,
        positional_strategy=True,
        trend_maturity="MIDDLE",
        trend_direction="UP",
        adx=20.0,
        distance_from_52w_high=-0.25,
        distance_from_52w_low=0.45,
        days_to_earnings=-1,
        days_since_earnings=999,
        liquidity_condition="NORMAL",
        iv_percentile=30.0,
        vol_regime="NORMAL",
        confidence=0.90,
        catalyst_proximity="LOW",
        earnings_window="FAR",
        atr_percentile=50.0,
        structure_quality="STRONG",
        value_acceptance_score=70.0,
        control_state="BUYERS",
        control_confidence=0.80,
        value_migration_direction="UP",
        phase_v2="CONTINUATION",
        momentum_bucket="HIGH",
        momentum_score=35.0,
        location_bucket="MID_RANGE",
        transition_flag_v2=False,
        early_candidate=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _outcomes(**overrides):
    base = dict(
        n_observations=250,
        confidence_level=0.90,
        expected_value_5d=0.001,
        expected_value_10d=0.0016,
        expected_value_20d=0.004,
        win_rate_5d=0.52,
        win_rate_10d=0.54,
        win_rate=0.55,
        signal_type="CONTINUATION",
        momentum_tier="TIER_2_SUSTAINING",
        prob_up_10pct_20d=0.58,
        prob_trend_continues_20d=0.65,
        sharpe_ratio=1.2,
        median_gain_if_up=0.08,
        median_gain_if_up_5d=0.03,
        median_gain_if_up_10d=0.05,
        median_loss_if_down=-0.04,
        median_loss_if_down_5d=-0.015,
        median_loss_if_down_10d=-0.025,
        median_days_to_target=20,
        median_max_drawdown=0.03,
        recommended_hold_days=5,
        future_momentum_bucket="HIGH",
        future_momentum_bucket_confidence=0.65,
        future_momentum_bucket_sample_size=250,
        state_match_quality="HIGH_SAMPLE",
        sample_size=250,
        probability_edge=0.12,
        forward_momentum_confidence=0.65,
    )
    base.update(overrides)
    obj = SimpleNamespace(**base)
    obj.win_rate_for_hold = lambda hold_days: obj.win_rate_5d if hold_days <= 5 else obj.win_rate_10d if hold_days <= 10 else obj.win_rate
    obj.median_gain_for_hold = lambda hold_days: obj.median_gain_if_up_5d if hold_days <= 5 else obj.median_gain_if_up_10d if hold_days <= 10 else obj.median_gain_if_up
    obj.median_loss_for_hold = lambda hold_days: obj.median_loss_if_down_5d if hold_days <= 5 else obj.median_loss_if_down_10d if hold_days <= 10 else obj.median_loss_if_down
    return obj


def _auction():
    return SimpleNamespace(
        auction_state="ALIGNED",
        confidence=0.85,
        reasoning="buyers in control",
        control=SimpleNamespace(controller="BUYERS", confidence=0.80),
        migration=SimpleNamespace(direction="UP", consistency="CONSISTENT_UP", speed="FAST"),
    )


def test_preferred_horizon_is_not_a_live_match_dimension():
    assert "preferred_horizon" not in MATCH_EXACT_DIMS
    assert "preferred_horizon" not in MATCH_RELAXED_DIMS
    assert "preferred_horizon" not in ACTUARIAL_QUERY_COLUMNS
    assert "preferred_horizon" not in ACTUARIAL_CATEGORY_COLUMNS
    assert "outcome_hit_10pct_up" in REQUIRED_ACTUARIAL_V6_COLUMNS


def test_active_match_ladder_emits_forward_momentum_tier():
    engine = ActuarialQueryEngine.__new__(ActuarialQueryEngine)
    engine._match_norm_cache = {}
    rows = []
    for _ in range(80):
        rows.append(
            dict(
                vol_regime="NORMAL",
                trend_direction="UP",
                structure_quality="STRONG",
                phase_v2="CONTINUATION",
                momentum_bucket="HIGH",
                location_bucket="MID_RANGE",
                future_momentum_bucket="HIGH",
            )
        )
    engine.df = pd.DataFrame(rows)

    matched = engine._find_similar_states(
        dict(
            vol_regime="NORMAL",
            trend_direction="UP",
            structure_quality="STRONG",
            phase_v2="CONTINUATION",
            momentum_bucket="HIGH",
            location_bucket="MID_RANGE",
            preferred_horizon="5D",
        )
    )

    assert matched.attrs["state_match_stage"] == "EXACT"
    assert matched.attrs["signal_type"] == "CONTINUATION"
    assert matched.attrs["momentum_tier"] == "TIER_2_SUSTAINING"
    assert "preferred_horizon" not in matched.attrs["state_match_dimensions"]


def test_continuation_fast_path_uses_recalibrated_ev_floor():
    edge = EdgeDetector().detect_edge(
        _state(phase_v2="CONTINUATION", momentum_bucket="HIGH"),
        _outcomes(signal_type="CONTINUATION", expected_value_10d=0.0016),
        _auction(),
    )
    assert edge.has_edge is True
    assert edge.signal_type == "CONTINUATION"


def test_accelerating_transition_can_upgrade_to_trade():
    edge = EdgeDetector().detect_edge(
        _state(phase_v2="EARLY_TRANSITION", momentum_bucket="MID", transition_flag_v2=True),
        _outcomes(
            signal_type="TRANSITION",
            momentum_tier="TIER_1_ACCELERATING",
            expected_value_20d=0.0035,
            expected_value_10d=0.0,
        ),
        _auction(),
    )
    assert edge.has_edge is True
    assert edge.signal_type == "TRANSITION"


def test_options_dte_uses_recommended_hold_days_not_20d_median_days():
    state = SimpleNamespace(catalyst_proximity="LOW", days_to_earnings=-1, vol_regime="NORMAL")
    outcomes = _outcomes(recommended_hold_days=5, median_days_to_target=20)

    for builder_cls in (Layer2ScenarioBuilder, Layer3ScenarioBuilder):
        rec = builder_cls()._design_options_strategy("CALL", 100.0, state, outcomes, "AGGRESSIVE")
        assert rec["dte"] == 10


def test_adapter_preserves_trend_indicators_used_by_state_calculator():
    bars = [
        {
            "date": f"2026-06-{day:02d}",
            "open": 100.0 + day / 10,
            "high": 101.0 + day / 10,
            "low": 99.0 + day / 10,
            "close": 100.5 + day / 10,
            "volume": 1_000_000,
        }
        for day in range(1, 29)
    ]
    payload = {
        "ticker": "TREND",
        "current_price": 103.3,
        "technical_data": {
            "ohlcv": bars,
            "vwap_15m": 102.0,
            "vwap_1h": 101.5,
            "vwap_4h": 101.0,
            "vwap_daily": 102.2,
            "ema9": 102.8,
            "ema21": 102.0,
            "ema50": 100.0,
            "ema200": 95.0,
            "adx": 31.0,
            "atr_current": 2.0,
            "high_52w": 120.0,
            "low_52w": 70.0,
        },
    }

    adapted = OrchestratorAdapter().adapt(payload)
    tech = adapted.technical
    assert (tech.ema9, tech.ema21, tech.ema50, tech.ema200) == (102.8, 102.0, 100.0, 95.0)
    assert (tech.vwap_15m, tech.vwap_1h, tech.vwap_4h, tech.vwap_daily) == (
        102.0, 101.5, 101.0, 102.2,
    )
    trend = StateVectorCalculator()._calculate_trend_maturity(tech)
    assert trend["direction"] == "UP"
