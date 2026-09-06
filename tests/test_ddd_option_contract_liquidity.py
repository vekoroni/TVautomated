from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from canonical_data.option_liquidity_lifecycle import (
    ContractLiquidityState as PersistenceLiquidityState,
    MonitorState as PersistenceMonitorState,
)
from contracts.long_option_policy import (
    evaluate_execution_viability as compatibility_execution_viability,
)
from contracts.options_liquidity_execution_guard import (
    evaluate_olm_execution_guard as compatibility_execution_guard,
)
from contracts.options_liquidity_lifecycle import (
    evaluate_options_liquidity_lifecycle as compatibility_lifecycle,
)
from domain.long_option_execution import evaluate_execution_viability
from domain.option_contract_liquidity import (
    ContractLiquidityState,
    LifecycleInputs,
    MonitorState,
    decide_contract_quote_fetch,
    evaluate_options_liquidity_lifecycle,
    validate_contract_replacement,
)
from domain.option_liquidity_execution_guard import evaluate_olm_execution_guard


def test_legacy_imports_are_identity_preserving_domain_facades() -> None:
    assert compatibility_execution_viability is evaluate_execution_viability
    assert compatibility_lifecycle is evaluate_options_liquidity_lifecycle
    assert compatibility_execution_guard is evaluate_olm_execution_guard
    assert PersistenceLiquidityState is ContractLiquidityState
    assert PersistenceMonitorState is MonitorState


@pytest.mark.parametrize(
    ("facts", "should_fetch", "reason"),
    [
        ({"thesis_state": "INVALIDATED", "monitor_state": "ACTIVE"}, False, "THESIS_INVALIDATED"),
        ({"thesis_state": "ACTIVE", "monitor_state": "PAUSED"}, False, "MONITOR_PAUSED"),
        ({"thesis_state": "ACTIVE", "monitor_state": "ACTIVE", "horizon_end_date": date(2026, 9, 3)}, False, "HORIZON_EXPIRED"),
        ({"thesis_state": "ACTIVE", "monitor_state": "ACTIVE"}, True, "OBSERVATION_MISSING"),
        ({"thesis_state": "ACTIVE", "monitor_state": "ACTIVE", "latest_liquidity_state": "QUOTE_STALE", "latest_quote_age_seconds": 1.0}, True, "QUOTE_MARKED_STALE"),
        ({"thesis_state": "ACTIVE", "monitor_state": "ACTIVE", "latest_liquidity_state": "EXECUTABLE_NOW", "latest_quote_age_seconds": 30.0}, False, "FRESH_EXECUTABLE_CONTRACT"),
        ({"thesis_state": "ACTIVE", "monitor_state": "ACTIVE", "latest_liquidity_state": "LIQUIDITY_PENDING", "latest_quote_age_seconds": 901.0}, True, "CANONICAL_OBSERVATION_STALE"),
    ],
)
def test_quote_fetch_policy_matrix(facts, should_fetch, reason) -> None:
    inputs = {
        "current_date": date(2026, 9, 4),
        "freshness_seconds": 900,
        "horizon_end_date": None,
        "latest_liquidity_state": None,
        "latest_quote_age_seconds": None,
        **facts,
    }
    decision = decide_contract_quote_fetch(**inputs)
    assert decision.should_fetch is should_fetch
    assert decision.reason == reason


def test_unknown_observation_age_fetches_instead_of_assuming_fresh() -> None:
    decision = decide_contract_quote_fetch(
        thesis_state="ACTIVE", monitor_state="ACTIVE",
        horizon_end_date=None, current_date=date(2026, 9, 4),
        latest_liquidity_state="LIQUIDITY_PENDING",
        latest_quote_age_seconds=None, freshness_seconds=900,
    )
    assert decision.should_fetch is True
    assert decision.reason == "CANONICAL_OBSERVATION_AGE_UNKNOWN"


def test_contract_replacement_is_a_new_economic_object() -> None:
    with pytest.raises(ValueError, match="exact economics recomputation"):
        validate_contract_replacement(
            previous_contract_symbol="ABC260918C00100000",
            selected_contract_symbol="ABC260925C00100000",
            economics_recomputed=False,
        )
    assert validate_contract_replacement(
        previous_contract_symbol="ABC260918C00100000",
        selected_contract_symbol="ABC260925C00100000",
        economics_recomputed=True,
        observed_contract_symbol="ABC260925C00100000",
    ) is True


def test_selected_quote_must_belong_to_exact_contract() -> None:
    with pytest.raises(ValueError, match="selected observation"):
        validate_contract_replacement(
            previous_contract_symbol="ABC260918P00100000",
            selected_contract_symbol="ABC260918P00100000",
            economics_recomputed=False,
            observed_contract_symbol="ABC260925P00100000",
        )


@pytest.mark.parametrize("side", ["CALL", "PUT"])
def test_composite_domain_evaluator_remains_symmetric(side: str) -> None:
    call = side == "CALL"
    result = evaluate_options_liquidity_lifecycle(LifecycleInputs(
        side=side, spot=100.0, strike=102.0 if call else 98.0,
        delta=0.45 if call else -0.45, bid=2.0, ask=2.2, dte=30.0,
        remaining_hold_sessions=10.0, forecast_vol_annual=0.30,
        thesis_spot=100.0, current_spot=101.0 if call else 99.0,
        structural_target=110.0 if call else 90.0,
        invalidation_spot=95.0 if call else 105.0,
    ))
    assert result["liquidity_state"] == "EXECUTABLE_NOW"
    assert result["maturation_execution_authority"] is False
    assert result["remaining_runway_state"] == "GAP_CONFIRMATION_WITH_RUNWAY"


def test_domain_modules_do_not_depend_on_adapters_or_persistence() -> None:
    root = Path(__file__).resolve().parents[1] / "domain"
    for name in (
        "long_option_execution.py",
        "option_contract_liquidity.py",
        "option_liquidity_execution_guard.py",
    ):
        source = (root / name).read_text(encoding="utf-8")
        assert "canonical_data" not in source
        assert "MarketData" not in source
        assert "sqlite" not in source.lower()
        assert "from contracts" not in source
