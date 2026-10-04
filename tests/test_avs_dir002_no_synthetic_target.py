"""DIR-002 DWN-12: an explicit absent thesis target cannot become formula 3R."""

import pytest
import pandas as pd

from scripts.avshunter_options_intelligence import _governed_structural_target, parse_structural_context


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_explicit_none_target_survives_downstream_fallbacks(direction):
    far = 120.0 if direction == "CALL" else 80.0
    target, status = _governed_structural_target(
        direction, 100.0, None, far, 5.0, target_state="NONE"
    )
    assert target is None
    assert status == "NONE"


def test_explicit_level_target_must_still_be_sourced_and_on_the_correct_side():
    target, status = _governed_structural_target(
        "PUT", 100.0, 110.0, 80.0, 5.0, target_state="LEVEL"
    )
    assert target is None
    assert status == "INVALID_DECLARED_TARGET"


def test_historical_target_without_declared_state_preserves_legacy_fallback():
    assert _governed_structural_target("CALL", 100.0, None, 120.0, 5.0) == (120.0, "L1_FAR")


@pytest.mark.parametrize("side", ["CALL", "PUT"])
def test_options_context_honours_explicit_none_even_with_stale_target(side):
    row = pd.Series({
        "ticker": "NONE",
        "run_id": "20990101_010101",
        "direction": side,
        "discovery_direction_preliminary": side,
        "direction_authority": "DISCOVERY_GOVERNED",
        "discovery_direction_basis": "test target state",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "structural_target": 120.0 if side == "CALL" else 80.0,
        "target_state": "NONE",
        "horizon_bucket": "6_10d",
    })
    context = parse_structural_context(row)
    assert context["direction"] == side
    assert context["structural_target"] is None
    assert context["structural_target_state"] == "NONE"
