from datetime import datetime, timezone
import json

import morning_gate


def test_morning_gate_suppresses_stale_curve_but_keeps_fresh_components(tmp_path) -> None:
    path = tmp_path / "bond_macro_state.json"
    path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "yield_curve": {
            "curve_state": "FLAT", "curve_move_1d": "BEAR_STEEPENING",
            "spread_bps": 44, "regime_implication": "REDUCE_RISK",
            "stale_flag": True, "as_of_date": "2026-08-26",
        },
        "credit_stress": {"stress_level": "NORMAL", "credit_warning": False},
        "zn_futures": {"zn_direction": "RISING", "rate_regime_signal": "NEUTRAL"},
        "auction": {"auction_today": True, "spread_risk_flag": True},
        "composite": {
            "trade_go": False, "macro_bond_score": 53,
            "morning_manifest_flag": "BOND_MACRO_CAUTION",
        },
    }), encoding="utf-8")
    original = morning_gate.BOND_MACRO_PATH
    morning_gate.BOND_MACRO_PATH = path
    try:
        result = morning_gate._load_bond_macro()
    finally:
        morning_gate.BOND_MACRO_PATH = original

    assert result["bond_curve_state"] == "STALE_UNAVAILABLE"
    assert result["bond_curve_move_1d"] == "STALE_UNAVAILABLE"
    assert result["bond_spread_bps"] is None
    assert result["bond_macro_score"] is None
    assert result["bond_trade_go"] is True
    assert result["bond_credit_stress"] == "NORMAL"
    assert result["bond_auction_today"] is True
    assert result["bond_curve_freshness"] == "STALE"
