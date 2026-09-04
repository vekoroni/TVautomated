from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.selected_contract_economics import (
    evaluate_long_option_monetisability,
    hydrate_selected_structure,
    parse_occ_symbol,
    parse_selected_structure,
    recompute_premium_rr,
)


FETCHED_AT = "2026-08-25T08:30:00+00:00"


def _quote(symbol: str, *, bid: float, ask: float, delta: float) -> dict:
    return {
        "live_contract_bid": bid,
        "live_contract_ask": ask,
        "live_contract_mid": (bid + ask) / 2,
        "live_contract_iv": 0.40,
        "live_contract_delta": delta,
        "live_contract_gamma": 0.02,
        "live_contract_theta": -0.05,
        "live_contract_vega": 0.10,
        "live_contract_oi": 500,
        "live_contract_volume": 50,
        "live_contract_multiplier": 100,
        "live_options_source": "TEST_MARKETDATA",
        "live_options_fetched_at": FETCHED_AT,
    }


def test_occ_parser_preserves_root_expiry_side_and_decimal_strike() -> None:
    parsed = parse_occ_symbol("O:AAA260918C00102500")
    assert parsed == {
        "symbol": "AAA260918C00102500",
        "root": "AAA",
        "expiry": "2026-09-18",
        "side": "CALL",
        "strike": 102.5,
    }


def test_single_call_hydration_and_rr_use_the_exact_selected_quote() -> None:
    symbol = "AAA260918C00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=0.45),
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    rr = recompute_premium_rr(
        {"canonical_direction": "CALL", "live_price": 100, "structural_target": 115},
        hydrated,
    )

    assert hydrated["selected_structure_hydration_status"] == "COMPLETE"
    assert hydrated["selected_structure"] == "LONG_SINGLE"
    assert json.loads(hydrated["selected_contract_symbols"]) == [symbol]
    assert hydrated["live_contract_ask"] == 5.0
    assert rr["rr_recompute_status"] == "COMPLETE"
    assert rr["rr_contract_symbol"] == symbol
    assert rr["rr_entry_debit_per_share"] == 5.0
    assert rr["rr_target_value_per_share"] == 15.0
    assert rr["rr_premium_expected"] == 2.0
    assert rr["rr_evaluation_id"] == hydrated["selected_structure_id"]


def test_selected_contract_spread_uses_bid_ask_mid_not_provider_mid() -> None:
    symbol = "AAA260918C00100000"

    def quote_with_bad_provider_mid(requested: str) -> dict:
        quote = _quote(requested, bid=4.0, ask=6.0, delta=0.45)
        quote["live_contract_mid"] = 99.0
        return quote

    hydrated = hydrate_selected_structure(
        symbol,
        quote_with_bad_provider_mid,
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc=FETCHED_AT,
    )

    assert hydrated["selected_long_leg"]["spread_fraction_mid"] == 0.4
    assert hydrated["live_contract_spread_pct"] == 40.0


def test_single_put_rr_uses_put_intrinsic_geometry() -> None:
    symbol = "AAA260918P00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=-0.45),
        ticker="AAA",
        direction="PUT",
        instrument="LONG_PUT",
        fetched_at_utc=FETCHED_AT,
    )
    rr = recompute_premium_rr(
        {"canonical_direction": "PUT", "live_price": 100, "structural_target": 85},
        hydrated,
    )
    assert rr["rr_premium_expected"] == 2.0


def test_bull_call_vertical_hydrates_both_legs_and_computes_debit_rr() -> None:
    long_symbol = "AAA260918C00100000"
    short_symbol = "AAA260918C00110000"
    quotes = {
        long_symbol: _quote(long_symbol, bid=4.8, ask=5.0, delta=0.55),
        short_symbol: _quote(short_symbol, bid=2.0, ask=2.2, delta=0.30),
    }
    hydrated = hydrate_selected_structure(
        f"BULL_CALL_DEBIT:{long_symbol}/{short_symbol}",
        quotes.__getitem__,
        ticker="AAA",
        direction="CALL",
        instrument="DEBIT_SPREAD_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    rr = recompute_premium_rr(
        {"canonical_direction": "CALL", "live_price": 100, "structural_target": 115},
        hydrated,
    )

    assert hydrated["selected_structure_hydration_status"] == "COMPLETE"
    assert hydrated["selected_structure"] == "BULL_CALL_DEBIT"
    assert hydrated["selected_long_leg"]["symbol"] == long_symbol
    assert hydrated["selected_short_leg"]["symbol"] == short_symbol
    assert hydrated["live_contract_ask"] == 3.0
    assert rr["rr_entry_debit_per_share"] == 3.0
    assert rr["rr_target_value_per_share"] == 10.0
    assert rr["rr_premium_expected"] == 2.333333


def test_bear_put_vertical_orders_higher_strike_as_long_leg() -> None:
    long_symbol = "AAA260918P00100000"
    short_symbol = "AAA260918P00090000"
    quotes = {
        long_symbol: _quote(long_symbol, bid=4.8, ask=5.0, delta=-0.55),
        short_symbol: _quote(short_symbol, bid=2.0, ask=2.2, delta=-0.30),
    }
    hydrated = hydrate_selected_structure(
        f"BEAR_PUT_DEBIT:{short_symbol}/{long_symbol}",
        quotes.__getitem__,
        ticker="AAA",
        direction="PUT",
        instrument="DEBIT_SPREAD_PUT",
        fetched_at_utc=FETCHED_AT,
    )
    rr = recompute_premium_rr(
        {"canonical_direction": "PUT", "live_price": 100, "structural_target": 85},
        hydrated,
    )

    assert hydrated["selected_long_leg"]["symbol"] == long_symbol
    assert hydrated["selected_short_leg"]["symbol"] == short_symbol
    assert rr["rr_premium_expected"] == 2.333333


def test_declared_vertical_with_only_one_symbol_fails_closed() -> None:
    parsed = parse_selected_structure(
        "AAA260918C00100000",
        direction="CALL",
        instrument="DEBIT_SPREAD_CALL",
    )
    assert parsed["status"] == "FAILED"
    assert parsed["reason"] == "SELECTED_STRUCTURE_LEGS_MISSING"


def test_one_missing_vertical_leg_prevents_partial_hydration() -> None:
    long_symbol = "AAA260918C00100000"
    short_symbol = "AAA260918C00110000"

    def fetch(symbol: str) -> dict:
        if symbol == long_symbol:
            return _quote(symbol, bid=4.8, ask=5.0, delta=0.55)
        return {"live_options_source": "MARKETDATA_NO_QUOTE"}

    hydrated = hydrate_selected_structure(
        f"BULL_CALL_DEBIT:{long_symbol}/{short_symbol}",
        fetch,
        ticker="AAA",
        direction="CALL",
        instrument="DEBIT_SPREAD_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    assert hydrated["selected_structure_hydration_status"] == "FAILED"
    assert short_symbol in hydrated["selected_structure_hydration_reason"]
    assert "live_contract_mid" not in hydrated


def test_boolean_target_in_play_is_not_treated_as_a_price_target() -> None:
    symbol = "AAA260918C00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=0.45),
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    rr = recompute_premium_rr(
        {"canonical_direction": "CALL", "live_price": 100, "target_in_play": True},
        hydrated,
    )
    assert rr["rr_recompute_status"] == "FAILED"
    assert rr["rr_recompute_reason"] == "SELECTED_RR_THESIS_INPUT_MISSING"


def test_single_call_monetisability_uses_ask_breakeven_and_target_intrinsic() -> None:
    symbol = "AAA260918C00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=0.45),
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    result = evaluate_long_option_monetisability(
        {"canonical_direction": "CALL", "structural_target": 115}, hydrated
    )
    assert result["monetisability_state"] == "MONETISABLE"
    assert result["monetisability_contract_symbol"] == symbol
    assert result["monetisability_entry_ask"] == 5.0
    assert result["monetisability_breakeven_spot"] == 105.0
    assert result["monetisability_target_profit_per_share"] == 10.0
    assert result["monetisability_target_profit_pct"] == 200.0


def test_single_put_monetisability_uses_put_breakeven() -> None:
    symbol = "AAA260918P00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=-0.45),
        ticker="AAA",
        direction="PUT",
        instrument="LONG_PUT",
        fetched_at_utc=FETCHED_AT,
    )
    result = evaluate_long_option_monetisability(
        {"canonical_direction": "PUT", "structural_target": 85}, hydrated
    )
    assert result["monetisability_state"] == "MONETISABLE"
    assert result["monetisability_breakeven_spot"] == 95.0
    assert result["monetisability_target_profit_pct"] == 200.0


def test_target_that_does_not_clear_breakeven_is_not_monetisable() -> None:
    symbol = "AAA260918C00100000"
    hydrated = hydrate_selected_structure(
        symbol,
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=0.45),
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc=FETCHED_AT,
    )
    result = evaluate_long_option_monetisability(
        {"canonical_direction": "CALL", "structural_target": 104}, hydrated
    )
    assert result["monetisability_state"] == "NOT_MONETISABLE"
    assert result["monetisability_eligible"] is False


def test_contract_change_recomputes_monetisability_for_the_new_symbol() -> None:
    old = hydrate_selected_structure(
        "AAA260918C00100000",
        lambda requested: _quote(requested, bid=4.8, ask=5.0, delta=0.45),
        ticker="AAA", direction="CALL", instrument="LONG_CALL", fetched_at_utc=FETCHED_AT,
    )
    replacement = hydrate_selected_structure(
        "AAA260918C00110000",
        lambda requested: _quote(requested, bid=1.8, ask=2.0, delta=0.35),
        ticker="AAA", direction="CALL", instrument="LONG_CALL", fetched_at_utc=FETCHED_AT,
    )
    thesis = {"canonical_direction": "CALL", "structural_target": 115}
    old_result = evaluate_long_option_monetisability(thesis, old)
    new_result = evaluate_long_option_monetisability(thesis, replacement)
    assert old_result["monetisability_contract_symbol"] != new_result["monetisability_contract_symbol"]
    assert old_result["monetisability_target_profit_pct"] == 200.0
    assert new_result["monetisability_target_profit_pct"] == 150.0
