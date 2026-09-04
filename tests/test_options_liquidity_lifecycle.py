from __future__ import annotations

import pytest

from contracts.options_liquidity_lifecycle import (
    LifecycleInputs,
    calculate_dte_requirement,
    calculate_expected_move_features,
    classify_current_executability,
    classify_moneyness,
    classify_remaining_runway,
    evaluate_maturation_horizons,
    evaluate_options_liquidity_lifecycle,
)


def test_call_and_put_price_moneyness_are_directionally_mirrored() -> None:
    call = classify_moneyness("CALL", spot=100, strike=105, delta=0.30)
    put = classify_moneyness("PUT", spot=100, strike=95, delta=-0.30)

    assert call["moneyness_state"] == put["moneyness_state"] == "OTM"
    assert call["delta_band"] == put["delta_band"] == "DEVELOPING_OTM_020_035"
    assert call["moneyness_treatment"] == "MONITOR_OTM_MATURATION"
    assert put["moneyness_treatment"] == "MONITOR_OTM_MATURATION"


@pytest.mark.parametrize(
    ("delta", "band", "treatment"),
    [
        (0.19, "FAR_OTM_LT_020", "REJECT_FAR_OTM"),
        (0.20, "DEVELOPING_OTM_020_035", "MONITOR_OTM_MATURATION"),
        (0.35, "NEAR_ATM_035_060", "PREFERRED_EXECUTION"),
        (0.60, "NEAR_ATM_035_060", "PREFERRED_EXECUTION"),
        (0.61, "ITM_060_075", "REVIEW_ITM_STOCK_REPLACEMENT"),
        (0.75, "ITM_060_075", "REVIEW_ITM_STOCK_REPLACEMENT"),
        (0.76, "DEEP_ITM_GT_075", "OUTSIDE_DEFAULT_CONVEXITY_MANDATE"),
    ],
)
def test_governed_absolute_delta_bands(
    delta: float, band: str, treatment: str
) -> None:
    result = classify_moneyness("CALL", spot=100, strike=100, delta=delta)
    assert result["delta_band"] == band
    assert result["moneyness_treatment"] == treatment


def test_deep_itm_is_stock_like_not_lottery_geometry() -> None:
    result = classify_moneyness("LONG_CALL", spot=120, strike=90, delta=0.86)
    assert result["moneyness_state"] == "ITM"
    assert result["delta_band"] == "DEEP_ITM_GT_075"
    assert result["moneyness_treatment"] == "OUTSIDE_DEFAULT_CONVEXITY_MANDATE"


def test_dte_requirement_includes_hold_monitor_and_exit_buffer() -> None:
    result = calculate_dte_requirement(10, monitor_sessions=2, exit_buffer_sessions=5)
    assert result["minimum_required_dte"] == 17


@pytest.mark.parametrize("invalid_hold", [0, 7, 8, 15, 100])
def test_dte_requirement_rejects_non_routed_hold_values(invalid_hold: int) -> None:
    with pytest.raises(ValueError, match="governed routed hold"):
        calculate_dte_requirement(invalid_hold)


@pytest.mark.parametrize(
    ("side", "invalidation"),
    [("CALL", 101), ("CALL", 100), ("PUT", 99), ("PUT", 100)],
)
def test_runway_rejects_wrong_sided_or_zero_distance_invalidation(
    side: str, invalidation: float
) -> None:
    target = 110 if side == "CALL" else 90
    with pytest.raises(ValueError, match="opposite the option direction"):
        classify_remaining_runway(
            side,
            thesis_spot=100,
            current_spot=100,
            structural_target=target,
            invalidation_spot=invalidation,
        )


def test_current_tight_fresh_quote_is_executable_without_open_interest_input() -> None:
    result = classify_current_executability(
        bid=4.80,
        ask=5.00,
        bid_size=10,
        ask_size=8,
        quote_age_seconds=60,
        dte=25,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "EXECUTABLE_NOW"
    assert result["executable_now"] is True
    assert result["current_quote_executable"] is True
    assert result["execution_authority"] is False
    assert "open_interest" not in result


def test_zero_bid_is_recoverable_but_not_executable() -> None:
    result = classify_current_executability(
        bid=0,
        ask=0.40,
        quote_age_seconds=60,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="MONITOR_OTM_MATURATION",
    )
    assert result["liquidity_state"] == "ZERO_BID"
    assert result["recovery_disposition"] == "MONITOR"
    assert result["executable_now"] is False


def test_wide_spread_is_pending_not_terminal_rejection() -> None:
    result = classify_current_executability(
        bid=1.00,
        ask=1.50,
        quote_age_seconds=60,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="MONITOR_OTM_MATURATION",
    )
    assert result["spread_pct"] == 40.0
    assert result["liquidity_state"] == "LIQUIDITY_PENDING"
    assert result["recovery_disposition"] == "MONITOR"


def test_reviewable_spread_does_not_authorize_execution() -> None:
    result = classify_current_executability(
        bid=0.80,
        ask=1.00,
        quote_age_seconds=60,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "REVIEWABLE_SPREAD"
    assert result["executable_now"] is False
    assert result["execution_authority"] is False


def test_missing_displayed_size_can_be_governed_as_recoverable() -> None:
    result = classify_current_executability(
        bid=4.80,
        ask=5.00,
        quote_age_seconds=60,
        dte=25,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
        require_displayed_size=True,
    )
    assert result["liquidity_state"] == "NO_DISPLAYED_SIZE"
    assert result["recovery_disposition"] == "MONITOR"


def test_stale_quote_cannot_be_executable_even_when_spread_is_tight() -> None:
    result = classify_current_executability(
        bid=4.80,
        ask=5.00,
        quote_age_seconds=3600,
        dte=25,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "QUOTE_STALE"
    assert result["executable_now"] is False


def test_short_dte_repairs_contract_family_instead_of_invalidating_thesis() -> None:
    result = classify_current_executability(
        bid=4.80,
        ask=5.00,
        quote_age_seconds=60,
        dte=10,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "DTE_UNSUITABLE"
    assert result["recovery_disposition"] == "CONTRACT_REPAIR"


def test_no_listed_market_is_terminal() -> None:
    result = classify_current_executability(
        bid=None,
        ask=None,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="PREFERRED_EXECUTION",
        listed_market=False,
    )
    assert result["liquidity_state"] == "NO_LISTED_MARKET"
    assert result["recovery_disposition"] == "TERMINAL"


def test_otm_contract_gets_closer_in_sigma_units_as_horizon_expands() -> None:
    one_day = calculate_expected_move_features(
        "CALL", spot=100, strike=105, forecast_vol_annual=0.40, horizon_sessions=1
    )
    three_day = calculate_expected_move_features(
        "CALL", spot=100, strike=105, forecast_vol_annual=0.40, horizon_sessions=3
    )
    assert three_day["atm_distance_sigma"] < one_day["atm_distance_sigma"]
    assert three_day["strike_reach_score"] > one_day["strike_reach_score"]
    assert one_day["score_is_probability"] is False


def test_call_and_put_expected_move_features_are_mirrored() -> None:
    call = calculate_expected_move_features(
        "CALL", spot=100, strike=105, forecast_vol_annual=0.40, horizon_sessions=2
    )
    put = calculate_expected_move_features(
        "PUT", spot=100, strike=95.238095, forecast_vol_annual=0.40, horizon_sessions=2
    )
    assert call["atm_distance_sigma"] == pytest.approx(
        put["atm_distance_sigma"], abs=1e-5
    )


def test_remaining_runway_distinguishes_confirmation_from_realized_move() -> None:
    confirmed = classify_remaining_runway(
        "CALL",
        thesis_spot=100,
        current_spot=104,
        structural_target=115,
        invalidation_spot=95,
        one_session_expected_move_abs=6,
    )
    realized = classify_remaining_runway(
        "CALL",
        thesis_spot=100,
        current_spot=113,
        structural_target=115,
        invalidation_spot=95,
        one_session_expected_move_abs=20,
    )
    assert confirmed["remaining_runway_state"] == "GAP_CONFIRMATION_WITH_RUNWAY"
    assert realized["remaining_runway_state"] == "MOVE_ALREADY_REALIZED"


def test_large_gap_with_runway_waits_for_pullback() -> None:
    result = classify_remaining_runway(
        "PUT",
        thesis_spot=100,
        current_spot=94,
        structural_target=85,
        invalidation_spot=105,
        one_session_expected_move_abs=4,
    )
    assert result["remaining_runway_state"] == "WAIT_FOR_PULLBACK"
    assert result["remaining_runway_factor"] == pytest.approx(0.6)


def test_invalidation_is_directionally_mirrored() -> None:
    call = classify_remaining_runway(
        "CALL",
        thesis_spot=100,
        current_spot=94,
        structural_target=115,
        invalidation_spot=95,
    )
    put = classify_remaining_runway(
        "PUT",
        thesis_spot=100,
        current_spot=106,
        structural_target=85,
        invalidation_spot=105,
    )
    assert call["remaining_runway_state"] == "THESIS_INVALIDATED"
    assert put["remaining_runway_state"] == "THESIS_INVALIDATED"


def test_maturation_scores_are_explicitly_non_authoritative() -> None:
    liquidity = classify_current_executability(
        bid=1.00,
        ask=1.50,
        quote_age_seconds=60,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="MONITOR_OTM_MATURATION",
    )
    result = evaluate_maturation_horizons(
        "CALL",
        spot=100,
        strike=104,
        forecast_vol_annual=0.50,
        liquidity_assessment=liquidity,
        remaining_runway_factor=0.80,
        thesis_active=True,
        neighbouring_contract_liquidity_score=0.80,
    )
    assert result["maturation_eligibility"] == "ELIGIBLE_FOR_MONITORING"
    assert result["maturation_score_is_probability"] is False
    assert result["maturation_execution_authority"] is False
    assert result["maturation_may_authorize_trade"] is False
    assert result["maturation_score_3d"] >= result["maturation_score_1d"]


def test_terminal_or_invalidated_candidates_cannot_receive_maturation_uplift() -> None:
    terminal = classify_current_executability(
        bid=None,
        ask=None,
        dte=30,
        minimum_required_dte=15,
        moneyness_treatment="MONITOR_OTM_MATURATION",
        listed_market=False,
    )
    result = evaluate_maturation_horizons(
        "CALL",
        spot=100,
        strike=104,
        forecast_vol_annual=0.50,
        liquidity_assessment=terminal,
        remaining_runway_factor=0.80,
        thesis_active=True,
    )
    assert result["maturation_eligibility"] == "NOT_ELIGIBLE_THIS_CONTRACT"
    assert result["maturation_score_1d"] == 0


def test_composite_lifecycle_preserves_illiquid_developing_call() -> None:
    result = evaluate_options_liquidity_lifecycle(
        LifecycleInputs(
            side="LONG_CALL",
            spot=100,
            strike=104,
            delta=0.30,
            bid=1.00,
            ask=1.50,
            bid_size=10,
            ask_size=10,
            quote_age_seconds=60,
            dte=30,
            remaining_hold_sessions=10,
            forecast_vol_annual=0.50,
            thesis_spot=100,
            current_spot=101,
            structural_target=115,
            invalidation_spot=95,
            neighbouring_contract_liquidity_score=0.80,
        )
    )
    assert result["moneyness_treatment"] == "MONITOR_OTM_MATURATION"
    assert result["liquidity_state"] == "LIQUIDITY_PENDING"
    assert result["recovery_disposition"] == "MONITOR"
    assert result["maturation_eligibility"] == "ELIGIBLE_FOR_MONITORING"
    assert result["maturation_execution_authority"] is False


def test_unsupported_multileg_strategy_fails_closed() -> None:
    with pytest.raises(ValueError, match="unsupported long-option side"):
        classify_moneyness("STRANGLE", spot=100, strike=105, delta=0.30)
