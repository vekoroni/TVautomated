"""DIR-002 VNG-02: Vanguard evaluates the thesis; it never casts a side.

Characterisation first (design §4.6.2): the legacy rule returned CALL on
neutral evidence, so a "PUT" meant only "unlikely to rise 10%". The retired
rule is kept, unreachable from production, for the rollback drill; every
production verdict carries edge_direction NONE with an explicit status.
"""
from types import SimpleNamespace

import pytest

from vanguard.layer2_statistical.edge_detector import EdgeDetector


def _inputs(prob_up=0.45, trend="SIDEWAYS", controller="NONE"):
    state = SimpleNamespace(trend_direction=trend, trend_maturity="MID", intraday_rows=None,
                            positional_strategy=True, vol_regime="NORMAL", structure_quality="MODERATE",
                            value_migration_direction="NONE")
    outcomes = SimpleNamespace(prob_up_10pct_20d=prob_up, prob_trend_continues_20d=0.5,
                               n_observations=500, sample_size=500)
    auction = SimpleNamespace(
        control=SimpleNamespace(controller=controller, confidence=0.0),
        migration=SimpleNamespace(direction="NONE", consistency="", speed="NONE"),
    )
    return state, outcomes, auction


def test_characterise_legacy_rule_defaulted_neutral_evidence_to_call():
    detector = EdgeDetector.__new__(EdgeDetector)
    assert detector._legacy_determine_direction(*_inputs()) == "CALL"
    assert detector._legacy_determine_direction(*_inputs(prob_up=0.30)) == "PUT"


@pytest.mark.parametrize("prob_up", [0.10, 0.45, 0.90])
def test_production_edge_and_setup_paths_publish_no_side(prob_up, monkeypatch):
    detector = EdgeDetector.__new__(EdgeDetector)
    monkeypatch.setattr(detector, "_calculate_confidence", lambda *a: 0.5, raising=False)
    monkeypatch.setattr(detector, "_calculate_right_side_score", lambda *a: 50.0, raising=False)
    monkeypatch.setattr(detector, "_generate_rationale", lambda *a, **k: "rationale", raising=False)
    monkeypatch.setattr(detector, "_bucket_edge_quality", lambda *a: "WEAK", raising=False)
    state, outcomes, auction = _inputs(prob_up=prob_up)
    edge = detector._has_edge(state, outcomes, auction, 0.01, 0.0, "TIER")
    forming = detector._setup_forming(state, outcomes, auction, 0.01, 0.0, "reason")
    for result in (edge, forming):
        assert result.edge_direction == "NONE"
        assert result.edge_direction_status == "RETIRED_USE_SIDE_EVIDENCE"
        assert "CALL" not in result.rationale and "PUT" not in result.rationale


def test_options_never_fabricates_a_side_from_a_retired_vanguard_row():
    import pandas as pd
    from scripts.avshunter_options_intelligence import parse_structural_context

    row = pd.Series({
        "ticker": "RETD", "run_id": "20990101_010101",
        "direction": "CALL", "discovery_direction_preliminary": "CALL",
        "direction_authority": "DISCOVERY_GOVERNED",
        "entry_price": 100.0, "stock_price": 100.0,
        "edge_direction": "NONE", "edge_direction_status": "RETIRED_USE_SIDE_EVIDENCE",
        "raw_prob_up_10d": 0.9, "layer2__prob_down_10pct_20d": 5,
    })
    context = parse_structural_context(row)
    assert context["vanguard_edge_direction"] == "NONE"
    assert context["direction"] == "CALL"
