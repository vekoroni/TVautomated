import json
from pathlib import Path

from contracts.bond_macro_contract import normalise_bond_macro_sidecar


REPO = Path(__file__).resolve().parents[1]


def test_current_v21_sidecar_maps_pipeline_aliases():
    state = json.loads((REPO / "dropbox" / "macro" / "bond_macro_state.json").read_text(encoding="utf-8"))
    result = normalise_bond_macro_sidecar(state)

    assert result["bond_macro_flag"] == state["composite"]["morning_manifest_flag"]
    assert result["bond_macro_score"] == state["composite"]["macro_bond_score"]
    assert result["rate_regime_signal"] == state["zn_futures"]["rate_regime_signal"]
    assert result["credit_stress_level"] == state["credit_stress"]["stress_level"]
    assert result["credit_z_score"] == state["credit_stress"]["ratio_zscore_20d"]
    assert result["auction_spread_risk"] == state["auction"]["spread_risk_flag"]
    assert result["breakeven_adjustment_pct"] == state["composite"]["breakeven_adjustment_pct"]
    assert result["trade_go"] == state["composite"]["trade_go"]


def test_unknown_additive_fields_are_preserved():
    state = {
        "schema_version": "2.2.0",
        "future_top_level": {"enabled": True},
        "auction": {"spread_risk_flag": False, "future_auction_field": 7},
        "yield_curve": {"curve_state": "NORMAL"},
        "zn_futures": {"rate_regime_signal": "RISK_ON"},
        "credit_stress": {"stress_level": "NORMAL"},
        "composite": {"macro_bond_score": 70, "morning_manifest_flag": "BOND_MACRO_OK"},
    }
    result = normalise_bond_macro_sidecar(state)

    assert result["future_top_level"] == {"enabled": True}
    assert result["auction"]["future_auction_field"] == 7
    assert result["bond_macro_score"] == 70


def test_legacy_sidecar_names_remain_supported():
    state = {
        "auction_calendar": {"auction_today": True},
        "yield_curve": {"curve_state": "STEEP"},
        "zn_direction": {"rate_regime_signal": "RISK_OFF"},
        "credit_stress": {"stress_flag": "ELEVATED", "z_score": 2.1},
        "composite": {"flag": "BOND_MACRO_CAUTION", "score": 41, "trade_go": False},
    }
    result = normalise_bond_macro_sidecar(state)

    assert result["auction_spread_risk"] is True
    assert result["rate_regime_signal"] == "RISK_OFF"
    assert result["credit_z_score"] == 2.1
    assert result["bond_macro_score"] == 41
    assert result["trade_go"] is False
