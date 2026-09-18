from __future__ import annotations

import pandas as pd
import pytest

from contracts.options_liquidity_lifecycle import calculate_dte_requirement
from scripts import avshunter_options_intelligence as options


@pytest.mark.parametrize(
    ("horizon", "hold", "configured_min", "expected_effective_min", "expected_max"),
    [
        # Runway in calendar days (hold + 3 + 5 sessions x 7/5); the band is descriptive (ACK 18 Sep 2026: the horizon informs contract choice, never gates it).
        ("1_5d", 5, 7, 19, 21),
        ("6_10d", 10, 21, 26, 35),
        ("11_20d", 20, 35, 40, 60),
    ],
)
def test_selection_never_undercuts_lifecycle_dte_requirement(
    horizon: str,
    hold: int,
    configured_min: int,
    expected_effective_min: int,
    expected_max: int,
) -> None:
    assert options.DTE_CONFIG[horizon]["dte_min"] == configured_min

    policy = options.governed_dte_config(horizon)
    lifecycle_minimum = calculate_dte_requirement(hold)["minimum_required_dte"]

    assert policy["planned_hold_sessions"] == hold
    assert policy["lifecycle_minimum_dte"] == lifecycle_minimum
    assert policy["dte_min"] == expected_effective_min
    assert policy["dte_min"] >= lifecycle_minimum
    assert policy["dte_max"] == expected_max


def test_structural_context_uses_governed_dte_window() -> None:
    row = pd.Series(
        {
            "ticker": "TEST",
            "direction": "CALL",
            "horizon_bucket": "1_5d",
            "current_price": 100.0,
            "target_price": 110.0,
            "invalidation_spot": 95.0,
            "invalidation_state": "AVAILABLE",
        }
    )

    context = options.parse_structural_context(row)

    assert context["dte_window"] == (19, 20, 21)
    assert context["dte_config"]["lifecycle_minimum_dte"] == 19
    assert context["dte_config"]["dte_policy_version"] == options.DTE_SELECTION_POLICY_VERSION


def _chain(right: str) -> pd.DataFrame:
    signed_delta = 0.50 if right == "C" else -0.50
    strike = 100.0
    return pd.DataFrame(
        [
            {
                "symbol": f"TEST_SHORT_{right}",
                "underlying": "TEST",
                "right": right,
                "strike": strike,
                "expiration_date": "2026-09-18",
                "dte": 9.0,
                "mark": 2.0,
                "bid": 1.90,
                "ask": 2.10,
                "bid_size": 10,
                "ask_size": 10,
                "delta": signed_delta,
                "gamma": 0.03,
                "theta": -0.03,
                "vega": 0.08,
                "implied_vol": 0.40,
                "open_interest": 100,
                "volume": 20,
                "spread_pct": 0.10,
                "quote_quality": "TWO_SIDED",
                "quality_flags": (),
                "quote_fields_complete": True,
                "mark_synthetic": False,
            },
            {
                "symbol": f"TEST_ALIGNED_{right}",
                "underlying": "TEST",
                "right": right,
                "strike": strike,
                "expiration_date": "2026-09-25",
                "dte": 16.0,
                "mark": 2.0,
                "bid": 1.90,
                "ask": 2.10,
                "bid_size": 10,
                "ask_size": 10,
                "delta": signed_delta,
                "gamma": 0.03,
                "theta": -0.03,
                "vega": 0.08,
                "implied_vol": 0.40,
                "open_interest": 100,
                "volume": 20,
                "spread_pct": 0.10,
                "quote_quality": "TWO_SIDED",
                "quality_flags": (),
                "quote_fields_complete": True,
                "mark_synthetic": False,
            },
        ]
    )


@pytest.mark.parametrize(("direction", "right"), [("CALL", "C"), ("PUT", "P")])
def test_call_and_put_selector_prefers_the_longer_runway_and_flags_the_shortfall(
    direction: str, right: str
) -> None:
    """Neither contract covers the 19-day runway; the longer one is chosen and flagged, never dropped
    (ACK 18 Sep 2026: the horizon informs contract choice, never gates it)."""
    policy = options.governed_dte_config("1_5d")
    context = {
        "ticker": "TEST",
        "direction": direction,
        "spot": 100.0,
        "structural_target": 110.0 if direction == "CALL" else 90.0,
        "hold_days": 5,
        "dte_window": options.governed_dte_window("1_5d"),
        "dte_config": policy,
    }

    selected = options.select_best_contract(_chain(right), context)

    assert selected is not None
    assert selected["symbol"] == f"TEST_ALIGNED_{right}"
    assert selected["dte"] < policy["lifecycle_minimum_dte"]
    assert selected["contract_runway_state"] == "RUNWAY_SHORT"


@pytest.mark.parametrize(("direction", "right"), [("CALL", "C"), ("PUT", "P")])
def test_repair_selector_keeps_holdable_contracts_and_prefers_the_runway(
    direction: str, right: str
) -> None:
    """Both contracts can be held past issue, so both are alternatives; the one nearer the runway floor
    comes first (ACK 18 Sep 2026: the horizon informs contract choice, never gates it)."""
    chain = _chain(right)
    chain["quote_timestamp_utc"] = "2026-09-09T14:00:00Z"
    context = {
        "ticker": "TEST",
        "direction": direction,
        "horizon_bucket": "1_5d",
        "spot": 100.0,
        "structural_target": 110.0 if direction == "CALL" else 90.0,
        "dte_window": (7, 14, 21),
        "dte_config": options.DTE_CONFIG["1_5d"],
    }

    alternatives = options.select_repair_alternative_contracts(chain, context)

    assert [item["symbol"] for item in alternatives] == [f"TEST_ALIGNED_{right}", f"TEST_SHORT_{right}"]
    assert alternatives[-1]["dte"] >= calculate_dte_requirement(5)["minimum_holdable_dte"]


def test_unknown_horizon_descriptive_window_and_full_window_runway() -> None:
    """The descriptive window still normalises to 1_5d, but the runway that drives selection uses the full
    thesis window and says so (ACK 18 Sep 2026: the horizon informs contract choice, never gates it)."""
    assert options.governed_dte_window("UNKNOWN") == (19, 20, 21)
    assert options.contract_runway_policy("UNKNOWN")["contract_runway_basis"] == "THESIS_WINDOW_HORIZON_UNAVAILABLE"
