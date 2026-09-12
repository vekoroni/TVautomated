"""Focused regressions for the AVS-FIX-002 runtime adapter boundary."""

from __future__ import annotations

import math

import pytest

from contracts.direction_governance import resolve_governed_direction
from contracts.opportunity_tier import TIER_2, derive_tier
from execution_gate import execution_gate
from layer3_forward_variance import ForwardVarianceResult
from trigger_layer import _compute_ev


def _tier_row() -> dict:
    return {
        "canonical_direction": "CALL",
        "governed_direction_record_sha256": "a" * 64,
        "invalidation_state": "AVAILABLE",
        "invalidation_price": 95.0,
        "structural_target": 115.0,
        "rr_underlying": 3.0,
        "monetisability_state": "MONETISABLE",
        "monetisability_state_timevalue": "MONETISABLE",
        "spread_pct_of_mid": 20.0,
        "time_horizon": "1_5d",
        "contract_dte": 14.0,
        "planned_hold_sessions": 5.0,
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "trigger_state": "TRIGGER_READY",
        "contract_repair_status": "CONTRACT_OK",
        "final_action": "MANUAL_REVIEW",
    }


def _execution_row() -> dict:
    direction = resolve_governed_direction(
        ticker="AAA",
        run_id="20990101_010101",
        discovery_direction="CALL",
        governed_direction="CALL",
        governed_basis="test=CALL",
        row={},
        decided_at_utc="2099-01-01T01:01:01+00:00",
    )
    return {
        "ticker": "AAA",
        "morning_execution_permission": "GO",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "contract_symbol": "AAA260918C00100000",
        "live_contract_bid": 4.9,
        "live_contract_ask": 5.0,
        "live_contract_mid": 4.95,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.40,
        "live_iv_rank": 50,
        "signal_price": 100,
        "monetisability_state": "MONETISABLE",
        "monetisability_contract_symbol": "AAA260918C00100000",
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "QUOTE_WITHIN_EXECUTABLE_LIMIT",
        "execution_viability_contract_symbol": "AAA260918C00100000",
        "selected_contract_side": "CALL",
        "invalidation_spot": 95.0,
        "invalidation_state": "AVAILABLE",
        "invalidation_source": "TEST_GOVERNED_THESIS",
        **direction,
    }


def test_opportunity_tier_consumes_percent_spread_without_unit_confusion() -> None:
    tier, reason = derive_tier(_tier_row())
    assert tier == TIER_2
    assert reason == "SPREAD_20.00%_ABOVE_HORIZON_BAND"


def test_execution_gate_publishes_both_canonical_spread_projections() -> None:
    result = execution_gate(_execution_row())
    expected = (5.0 - 4.9) / 4.95
    assert result["spread_fraction_mid"] == pytest.approx(expected, abs=1e-6)
    assert result["spread_pct_of_mid"] == pytest.approx(expected * 100.0, abs=1e-4)
    assert result["spread_unit"] == "FRACTION_OF_MID"


def test_forward_variance_publishes_cumulative_fractional_budgets() -> None:
    result = ForwardVarianceResult(
        ticker="AAA",
        forward_realised_vol=0.40,
        vol_forecast_confidence=90.0,
        expected_move_1_5d=3.0,
        expected_move_6_10d=4.0,
        expected_move_11_20d=5.0,
        iv_tailwind_score=0.1,
        jump_risk_flag=False,
        method="GARCH",
        n_bars_used=252,
    ).to_dict()
    assert result["expected_move_10d_fraction"] == pytest.approx(
        0.40 * math.sqrt(10 / 252)
    )
    assert result["l3_expected_move_legacy_deprecated"] is True
    assert result["l3_expected_move_legacy_unit"] == "PERCENT"


def test_trigger_ev_prefers_canonical_fraction_over_legacy_percent() -> None:
    assert _compute_ev({
        "win_rate_10d": 0.60,
        "expected_move_10d_fraction": 0.10,
        "l3_expected_move_6_10d": 99.0,
    }) == pytest.approx(0.06)
