from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import morning_gate


def test_blank_primary_contract_promotes_live_repair_alternative(monkeypatch) -> None:
    row = {
        "ticker": "AAA",
        "direction": "CALL",
        "contract_symbol": "",
        "recommended_contract": "",
        "preferred_contract": "",
        "contract_repair_action": "ALTERNATIVES_AVAILABLE",
        "alternative_contract_1": "AAA260116C00100000",
        "alternative_contract_2": "AAA260116C00105000",
    }

    def fake_price(_ticker: str) -> dict:
        return {"live_price": 101.0, "live_data_source": "TEST"}

    def fake_contract(symbol: str) -> dict:
        assert symbol == "AAA260116C00100000"
        return {
            "live_contract_bid": 1.0,
            "live_contract_ask": 1.1,
            "live_contract_mid": 1.05,
            "live_contract_spread_pct": 9.52,
            "live_contract_delta": 0.45,
            "live_contract_iv": 0.35,
            "live_options_source": "TEST_MARKETDATA",
        }

    monkeypatch.setattr(morning_gate, "_fetch_live_price", fake_price)
    monkeypatch.setattr(morning_gate, "_fetch_live_contract", fake_contract)
    monkeypatch.setattr(morning_gate, "_fetch_options_skew", lambda _ticker: {})
    monkeypatch.setattr(morning_gate.time, "sleep", lambda _seconds: None)

    live_map = morning_gate._fetch_all_live([row], spread_threshold=25.0)
    live = live_map["AAA"]

    assert live["morning_contract_repair_used"] == "TRUE"
    assert live["morning_repair_contract_symbol"] == "AAA260116C00100000"
    assert live["live_contract_symbol"] == "AAA260116C00100000"
    assert live["live_options_source"] == "TEST_MARKETDATA"

    gated = morning_gate.run_gate(
        row,
        live,
        current_regime="BULLISH",
        spread_threshold=25.0,
        bond_state={},
        macro_state={"regime_state": "BULLISH", "macro_loaded": True},
    )

    assert gated["contract_symbol"] == "AAA260116C00100000"
    assert gated["recommended_contract"] == "AAA260116C00100000"
    assert gated["morning_selected_contract_symbol"] == "AAA260116C00100000"
    assert gated["contract_repair_resolved_at_open"] == "TRUE"


def test_failed_blank_primary_repair_records_attempts(monkeypatch) -> None:
    row = {
        "ticker": "BBB",
        "direction": "CALL",
        "contract_symbol": "",
        "recommended_contract": "",
        "preferred_contract": "",
        "contract_repair_action": "ALTERNATIVES_AVAILABLE",
        "alternative_contract_1": "BBB260116C00100000",
    }

    monkeypatch.setattr(morning_gate, "_fetch_live_price", lambda _ticker: {"live_price": 99.0})
    monkeypatch.setattr(
        morning_gate,
        "_fetch_live_contract",
        lambda _symbol: {"live_options_source": "MARKETDATA_NO_QUOTE"},
    )
    monkeypatch.setattr(morning_gate, "_fetch_options_skew", lambda _ticker: {})
    monkeypatch.setattr(morning_gate.time, "sleep", lambda _seconds: None)

    live_map = morning_gate._fetch_all_live([row], spread_threshold=25.0)
    live = live_map["BBB"]

    assert live["morning_contract_repair_used"] == "FALSE"
    assert "BBB260116C00100000:FAIL" in live["morning_repair_attempts"]
    assert live["live_options_source"] == "MARKETDATA_NO_QUOTE"


def test_missing_live_price_can_never_produce_go() -> None:
    row = {
        "ticker": "SAFE",
        "direction": "CALL",
        "macro_regime": "BULLISH",
        "contract_iv": 0.30,
    }
    live = {
        "live_price": None,
        "live_contract_bid": 1.00,
        "live_contract_ask": 1.10,
        "live_contract_spread_pct": 9.52,
        "live_contract_delta": 0.45,
        "live_contract_iv": 0.32,
    }

    gated = morning_gate.run_gate(
        row,
        live,
        current_regime="BULLISH",
        spread_threshold=25.0,
        bond_state={},
        macro_state={"regime_state": "BULLISH", "macro_loaded": True},
    )

    assert gated["check_invalidation_pass"] == "FALSE"
    assert gated["verdict"] == "FLAG"
    assert gated["execution_permission"] == "WAIT"
    assert gated["morning_execution_route"] == "WAIT_LIVE_PRICE"
    assert gated["morning_entry_action"] == "NO_TRADE"
