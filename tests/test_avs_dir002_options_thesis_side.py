"""DWN-02: governed thesis, not Vanguard probabilities, owns Options side."""

import pandas as pd
import pytest

from scripts.avshunter_options_intelligence import parse_structural_context


@pytest.mark.parametrize(
    "thesis_side,legacy_side,expected",
    [("BULL", "CALL", "CALL"), ("BEAR", "PUT", "PUT")],
)
def test_governed_thesis_does_not_fabricate_vanguard_direction(
    thesis_side, legacy_side, expected
):
    row = pd.Series({
        "ticker": "DIR2", "run_id": "20990101_010101",
        "thesis__side": thesis_side,
        "direction": legacy_side,
        "discovery_direction_preliminary": legacy_side,
        "direction_authority": "DISCOVERY_GOVERNED",
        "entry_price": 100.0, "stock_price": 100.0,
        "layer2__prob_up_10pct_20d": 10 if expected == "PUT" else 80,
        "layer2__prob_down_10pct_20d": 80 if expected == "PUT" else 10,
    })
    context = parse_structural_context(row)
    assert context["direction"] == expected
    assert context["vanguard_edge_direction"] == "NONE"
    assert context["layer2__edge_direction"] == "NONE"
    assert context["layer2__probability_direction"] == "NONE"


def test_unassigned_thesis_stays_unassigned_despite_vanguard_probability():
    row = pd.Series({
        "ticker": "DIR2U", "run_id": "20990101_010101",
        "thesis__side": "UNASSIGNED",
        "direction": "UNRESOLVED",
        "discovery_direction_preliminary": "UNRESOLVED",
        "direction_authority": "DISCOVERY_GOVERNED",
        "entry_price": 100.0, "stock_price": 100.0,
        "layer2__prob_up_10pct_20d": 90,
        "layer2__prob_down_10pct_20d": 10,
    })
    context = parse_structural_context(row)
    assert context["direction"] == "UNRESOLVED"
    assert context["preferred_strategy"] == "NO_DIRECTIONAL_STRATEGY"
    assert context["vanguard_edge_direction"] == "NONE"


@pytest.mark.parametrize("field", ["direction", "discovery_direction_preliminary"])
def test_thesis_legacy_side_mismatch_fails_closed(field):
    row = pd.Series({
        "ticker": "DIR2X", "run_id": "20990101_010101",
        "thesis__side": "BULL",
        "direction": "CALL",
        "discovery_direction_preliminary": "CALL",
        "direction_authority": "DISCOVERY_GOVERNED",
        "entry_price": 100.0, "stock_price": 100.0,
    })
    row[field] = "PUT"
    with pytest.raises(ValueError, match="thesis/legacy side mismatch"):
        parse_structural_context(row)


def test_mixed_transition_unassigned_preserves_strangle_adapter():
    row = pd.Series({
        "ticker": "DIR2S", "run_id": "20990101_010101",
        "thesis__side": "UNASSIGNED",
        "thesis__unassigned_reason": "TRANSITION_MIXED_TREND",
        "direction": "STRANGLE",
        "discovery_direction_preliminary": "STRANGLE",
        "direction_authority": "DISCOVERY_GOVERNED",
        "entry_price": 100.0, "stock_price": 100.0,
        "layer2__prob_up_10pct_20d": 90,
    })
    context = parse_structural_context(row)
    assert context["direction"] == "STRANGLE"
    assert context["vanguard_edge_direction"] == "NONE"
    assert context["preferred_strategy"] == "NO_DIRECTIONAL_STRATEGY"
