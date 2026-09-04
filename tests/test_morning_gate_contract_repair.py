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
        "macro_regime": "BULLISH",
        "rr_premium_expected": 1.5,
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "authority_source_stage": "FINAL_EXECUTION",
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
        macro_state={
            "regime_state": "BULLISH",
            "macro_filter": "GO",
            "macro_loaded": True,
        },
    )

    assert gated["contract_symbol"] == "AAA260116C00100000"
    assert gated["recommended_contract"] == "AAA260116C00100000"
    assert gated["morning_selected_contract_symbol"] == "AAA260116C00100000"
    assert gated["contract_repair_resolved_at_open"] == "TRUE"
    assert gated["contract_bid"] == 1.0
    assert gated["contract_ask"] == 1.1
    assert gated["contract_mid"] == 1.05
    assert gated["rr_premium_expected"] == ""
    assert gated["ev3_status"] == "REJECTED"
    assert gated["economics_comparable"] is False
    assert gated["economics_mismatch_reason"] == "REJECT_THESIS_PRICE"
    assert gated["morning_execution_permission"] == "CONTRACT_REPAIR"
    assert gated["morning_execution_route"] == "REPAIR_CONTRACT"


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
        "rr_premium_expected": 1.5,
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "authority_source_stage": "FINAL_EXECUTION",
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
        macro_state={
            "regime_state": "BULLISH",
            "macro_filter": "GO",
            "macro_loaded": True,
        },
    )

    assert gated["check_invalidation_pass"] == "FALSE"
    assert gated["verdict"] == "BLOCK"
    assert gated["execution_permission"] == "BLOCKED"
    assert gated["morning_execution_route"] == "STAND_DOWN_ECONOMICS"
    assert gated["morning_entry_action"] == "NO_TRADE"


def _go_row(**overrides) -> dict:
    row = {
        "ticker": "AAA",
        "direction": "CALL",
        "canonical_direction": "CALL",
        "signal_price": 100.0,
        "target_price": 115.0,
        "invalidation_spot": 95.0,
        "horizon_bucket": "6_10d",
        "ev3_barrier_state_key": "NORMAL|UP|MID",
        "contract_iv": 0.40,
        "capital_permission": "EOD_CANDIDATE_ONLY",
        "capital_authorization_state": "EOD_CANDIDATE_ONLY",
        "eod_candidate_authorized": True,
        "authority_source_stage": "FINAL_EXECUTION",
    }
    row.update(overrides)
    return row


def _quote(*, bid: float, ask: float, delta: float) -> dict:
    return {
        "live_contract_bid": bid,
        "live_contract_ask": ask,
        "live_contract_mid": (bid + ask) / 2,
        "live_contract_delta": delta,
        "live_contract_gamma": 0.02,
        "live_contract_theta": -0.05,
        "live_contract_vega": 0.10,
        "live_contract_iv": 0.40,
        "live_contract_oi": 500,
        "live_contract_volume": 50,
        "live_contract_multiplier": 100,
        "live_options_source": "TEST_MARKETDATA",
        "live_options_fetched_at": "2026-08-25T08:30:00+00:00",
    }


def _evaluated_ev3(row: dict, hydrated: dict) -> dict:
    return {
        "ev3_status": "EVALUATED_SHADOW",
        "ev3_reason_code": "SHADOW_ONLY",
        "ev3_contract_symbol": hydrated["selected_contract_symbol"],
        "ev3_structure": hydrated["selected_structure"],
        "ev3_ev_conservative_return": 0.12,
        "ev3_ev_lower_bound_return": 0.04,
        "ev3_absolute_state": "POSITIVE_UNVALIDATED",
    }


def test_primary_contract_recomputes_rr_and_ev3_with_one_identity(monkeypatch) -> None:
    symbol = "AAA260918C00100000"
    row = _go_row(contract_symbol=symbol, recommended_contract=symbol)
    monkeypatch.setattr(morning_gate, "_evaluate_hydrated_ev3", _evaluated_ev3)
    monkeypatch.setattr(morning_gate, "_fetch_live_contract", lambda _symbol: _quote(bid=4.8, ask=5.0, delta=0.45))
    hydrated = morning_gate._hydrate_live_structure(row, symbol)
    hydrated["live_price"] = 101.0
    gated = morning_gate.run_gate(
        row, hydrated, "BULLISH", 25.0, bond_state={}, macro_state={}
    )

    assert gated["rr_recompute_status"] == "COMPLETE"
    assert gated["selected_contract_economics_ready"] is True
    assert gated["economics_comparable"] is True
    assert gated["economics_mismatch_reason"] == ""
    assert gated["selected_structure_id"] == gated["rr_evaluation_id"]
    assert gated["selected_structure_id"] == gated["ev3_evaluation_id"]
    assert gated["rr_premium_expected"] == 2.0
    assert gated["ev_predicted"] == 0.12
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_ev3_unavailable_remains_advisory_when_exact_rr_is_complete(monkeypatch) -> None:
    symbol = "AAA260918C00100000"
    row = _go_row(contract_symbol=symbol, recommended_contract=symbol)
    monkeypatch.setattr(morning_gate, "_fetch_live_contract", lambda _symbol: _quote(bid=4.8, ask=5.0, delta=0.45))
    monkeypatch.setattr(
        morning_gate,
        "_evaluate_hydrated_ev3",
        lambda _row, _hydrated: {
            "ev3_status": "NOT_EVALUATED_DATA_DEFECT",
            "ev3_reason_code": "REJECT_STATE_KEY",
            "ev3_reason_detail": "test fixture",
        },
    )
    hydrated = morning_gate._hydrate_live_structure(row, symbol)
    hydrated["live_price"] = 101.0
    gated = morning_gate.run_gate(
        row, hydrated, "BULLISH", 25.0, bond_state={}, macro_state={}
    )

    assert gated["rr_recompute_status"] == "COMPLETE"
    assert gated["selected_contract_economics_ready"] is True
    assert gated["economics_comparable"] is False
    assert gated["ev_predicted"] == ""
    assert gated["check_contract_pass"] == "TRUE"
    assert gated["morning_execution_permission"] == "GO_LIMIT"


def test_morning_ev3_adapter_normalises_expected_move_percent_points() -> None:
    symbol = "AAA260918C00100000"
    row = _go_row(
        contract_symbol=symbol,
        expected_move_5d=3.78,
        expected_move_10d=1.57,
    )
    monkey_quote = lambda _symbol: _quote(bid=4.8, ask=5.0, delta=0.45)
    from contracts.selected_contract_economics import hydrate_selected_structure

    hydrated = hydrate_selected_structure(
        symbol,
        monkey_quote,
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc="2026-08-25T08:30:00+00:00",
    )
    candidate = morning_gate._ev3_candidate_from_hydration(row, hydrated)

    assert candidate["expected_move_5d"] == 0.0378
    assert round(candidate["expected_move_10d"], 6) == 0.0157
    assert candidate["morning_expected_move_5d_unit_source"] == "PERCENT_POINTS_TO_FRACTION"
    assert candidate["planned_hold_sessions"] == 10
    assert candidate["morning_ev3_hold_source"] == "ROUTED_HORIZON_UPPER_BOUND"


def test_composite_repair_is_hydrated_but_not_promoted_to_production(monkeypatch) -> None:
    long_symbol = "AAA260918C00100000"
    short_symbol = "AAA260918C00110000"
    composite = f"BULL_CALL_DEBIT:{long_symbol}/{short_symbol}"
    row = _go_row(
        contract_symbol="",
        recommended_contract="",
        instrument="DEBIT_SPREAD_CALL",
        alternative_contract_1=composite,
    )
    calls = []

    def fake_contract(symbol: str) -> dict:
        calls.append(symbol)
        if symbol == long_symbol:
            return _quote(bid=4.8, ask=5.0, delta=0.55)
        if symbol == short_symbol:
            return _quote(bid=2.0, ask=2.2, delta=0.30)
        raise AssertionError(symbol)

    monkeypatch.setattr(morning_gate, "_fetch_live_price", lambda _ticker: {"live_price": 101.0})
    monkeypatch.setattr(morning_gate, "_fetch_live_contract", fake_contract)
    monkeypatch.setattr(morning_gate, "_fetch_options_skew", lambda _ticker: {})
    monkeypatch.setattr(morning_gate, "_evaluate_hydrated_ev3", _evaluated_ev3)
    monkeypatch.setattr(morning_gate.time, "sleep", lambda _seconds: None)

    live = morning_gate._fetch_all_live([row], spread_threshold=25.0)["AAA"]
    assert calls == [long_symbol, short_symbol]
    assert live.get("morning_repair_contract_symbol", "") == ""
    assert live["morning_contract_repair_used"] == "FALSE"
    assert live["selected_structure"] == "BULL_CALL_DEBIT"
    assert live["selected_max_leg_spread_pct"] < 25.0

    gated = morning_gate.run_gate(
        row, live, "BULLISH", 25.0, bond_state={}, macro_state={}
    )
    assert gated["rr_recompute_status"] == "COMPLETE"
    assert gated["rr_premium_expected"] == 2.333333
    assert gated["economics_comparable"] is True
    assert gated["economics_mismatch_reason"] == ""
    assert gated["verdict"] == "BLOCK"
    assert gated["morning_execution_permission"] == "RESEARCH_ONLY"
    assert gated["morning_execution_route"] == "OPTIONS_RESEARCH_ONLY"
