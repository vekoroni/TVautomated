from __future__ import annotations

import json

import pandas as pd
import scripts.avshunter_options_intelligence as oi

from scripts.avshunter_options_intelligence import (
    _coalesce_ev3_merge_inputs,
    _ev3_direction_fields,
    _ev3_handoff_fields,
    _format_repair_alternative_fields,
    _quote_timestamp_utc,
    parse_structural_context,
    select_repair_alternative_contracts,
    select_ev3_vertical_debit_candidates,
)
from scripts.run_ev3_shadow import _candidate_rows


def _context(direction: str = "CALL", stop: float = 95.0, horizon: str = "6_10d") -> dict:
    return {
        "direction": direction,
        "entry": 100.0,
        "structural_target": 110.0 if direction == "CALL" else 90.0,
        "stop": stop,
        "stop_authoritative": True,
        "stop_source": "stop_loss",
        "horizon_bucket": horizon,
        "spot": 100.0,
        "dte_window": (15, 30, 45),
        "dte_config": {"delta_min": 0.25, "delta_max": 0.45, "spread_max": 0.25},
    }


def test_ev3_handoff_preserves_valid_call_stop_and_exact_horizon() -> None:
    ctx = _context()
    ctx.update({
        "layer2_matched_state_key": (
            "vol_regime=NORMAL|trend_direction=SIDEWAYS|structure_quality=NEUTRAL|"
            "phase_v2=CONTINUATION|wyckoff_phase_bucket=ACCUMULATION|"
            "trend_maturity=SIDEWAYS_BUILDING"
        ),
        "adx_14": 21.95,
        "atr_percentile_rank": 62.5,
    })
    fields = _ev3_handoff_fields(ctx)
    assert fields["invalidation_spot"] == 95.0
    assert fields["invalidation_source"] == "stop_loss"
    assert fields["planned_hold_sessions"] == 10
    assert fields["planned_hold_source"] == "HORIZON_BUCKET_ENDPOINT_V1"
    assert fields["ev3_barrier_state_key"] == (
        "NORMAL|SIDEWAYS|NEUTRAL|MODERATE|ACCUMULATION|SIDEWAYS_BUILDING|MID"
    )


def test_ev3_handoff_uses_explicit_state_dimensions_when_match_key_is_reduced() -> None:
    ctx = _context()
    ctx.update({
        "layer2_matched_state_key": (
            "vol_regime=NORMAL|trend_direction=SIDEWAYS|"
            "structure_quality=NEUTRAL|wyckoff_phase_bucket=ACCUMULATION"
        ),
        "layer2_trend_maturity": "SIDEWAYS_RANGING",
        "adx_14": 36.0,
        "atr_percentile_rank": 70.0,
    })
    fields = _ev3_handoff_fields(ctx)
    assert fields["ev3_barrier_state_key"] == (
        "NORMAL|SIDEWAYS|NEUTRAL|STRONG|ACCUMULATION|SIDEWAYS_RANGING|HIGH"
    )


def test_ev3_merge_restores_vanguard_state_dimensions_before_handoff() -> None:
    merged = pd.DataFrame([{
        "adx_14_x": 18.0,
        "adx_14_y": 36.0,
        "atr_percentile_rank_x": 20.0,
        "atr_percentile_rank_y": 70.0,
    }])
    repaired = _coalesce_ev3_merge_inputs(merged)
    assert repaired.loc[0, "adx_14"] == 36.0
    assert repaired.loc[0, "atr_percentile_rank"] == 70.0


def test_ev3_direction_contract_preserves_conflicts_and_strangle_rejection() -> None:
    call = _ev3_direction_fields(
        {"direction": "CALL"}, {"direction_arbitration_status": "AGREEMENT"}
    )
    assert call["canonical_direction"] == "CALL"
    assert call["direction_status"] == "AGREEMENT"

    conflict = _ev3_direction_fields(
        {"direction": "PUT"},
        {"direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS"},
    )
    assert conflict["canonical_direction"] == "PUT"
    assert conflict["direction_status"] == "CONFLICT_STRUCTURE_LEADS"

    strangle = _ev3_direction_fields(
        {"direction": "STRANGLE"}, {"direction_arbitration_status": "AGREEMENT"}
    )
    assert strangle["canonical_direction"] == "STRANGLE"


def test_stand_down_preserves_direction_and_macro_bond_handoff() -> None:
    ctx = _context()
    ctx.update({
        "ticker": "TEST",
        "intent": "BUY_SETUP",
        "vanguard_edge_direction": "CALL",
        "_signal_row": pd.Series({
            "ticker": "TEST",
            "macro_conviction_score": 63.0,
            "bond_macro_flag": "BOND_MACRO_CAUTION",
            "bond_trade_go": True,
            "auction_spread_risk": "LONG_END_AUCTION_WITHIN_5D",
        }),
    })

    result = oi._stand_down(ctx, "No evaluable primary contract")

    assert result["canonical_direction"] == "CALL"
    assert result["direction_status"] == "AGREEMENT"
    assert result["direction_arbitration_status"] == "AGREEMENT"
    assert result["macro_conviction_score"] == 63.0
    assert result["bond_macro_flag"] == "BOND_MACRO_CAUTION"
    assert result["bond_trade_go"] is True
    assert result["auction_spread_risk"] == "LONG_END_AUCTION_WITHIN_5D"


def test_strong_vanguard_edge_resolves_mixed_transition_direction() -> None:
    row = pd.Series({
        "ticker": "TEST",
        "tier": 1,
        "phase": "C",
        "precor_intent": "TRANSITION",
        "dominant_trend": "MIXED",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "structural_target": 110.0,
        "layer2__edge_direction": "CALL",
        "layer2__probability_verdict": "STRONG_EDGE",
        "layer2__edge_quality": "STRONG",
        "layer2__n_observations": 200,
    })
    ctx = parse_structural_context(row)
    assert ctx["direction"] == "CALL"
    assert "VANGUARD_TRANSITION_DIRECTION_REPAIR" in ctx["direction_override_reason"]


def test_ev3_handoff_mirrors_wrong_side_stop_for_put_with_provenance() -> None:
    fields = _ev3_handoff_fields(_context("PUT", stop=95.0))
    assert fields["invalidation_spot"] == 105.0
    assert fields["invalidation_source"] == "DIRECTION_MIRROR_FROM_STOP_LOSS_V1"
    assert fields["target_spot"] < fields["entry_spot"] < fields["invalidation_spot"]


def test_ev3_handoff_does_not_promote_a_legacy_default_stop() -> None:
    ctx = _context()
    ctx["stop_authoritative"] = False
    fields = _ev3_handoff_fields(ctx)
    assert fields["invalidation_spot"] is None
    assert fields["invalidation_source"] == "MISSING_AUTHORITATIVE_STOP"


def test_quote_timestamp_requires_vendor_timezone_or_epoch() -> None:
    assert _quote_timestamp_utc("2026-08-14T10:30:00Z").endswith("+00:00")
    assert _quote_timestamp_utc(1_786_704_600_000_000_000).endswith("+00:00")
    assert _quote_timestamp_utc("2026-08-14 10:30:00") is None


def test_alternative_handoff_contains_executable_contract_record() -> None:
    chain = pd.DataFrame(
        [
            {
                "symbol": "TEST260918P00095000",
                "right": "P",
                "strike": 95.0,
                "expiration_date": "2026-09-18",
                "dte": 35,
                "mark": 2.0,
                "bid": 1.9,
                "ask": 2.1,
                "delta": -0.35,
                "gamma": 0.03,
                "theta": -0.04,
                "vega": 0.10,
                "implied_vol": 0.40,
                "open_interest": 500,
                "volume": 100,
                "spread_pct": 0.10,
                "quote_timestamp_utc": "2026-08-14T10:30:00Z",
                "quote_timestamp_source": "marketdata.app.updated",
                "contract_multiplier": 100,
                "contract_multiplier_source": "marketdata.app",
                "md_quote_source": "marketdata.app",
            }
        ]
    )
    alternatives = select_repair_alternative_contracts(chain, _context("PUT", stop=95.0))
    assert len(alternatives) == 1
    candidate = alternatives[0]
    assert candidate["delta"] == -0.35
    for field in ("bid", "ask", "gamma", "theta", "vega", "iv", "oi", "volume", "quote_timestamp_utc", "contract_multiplier"):
        assert candidate[field] is not None

    formatted = _format_repair_alternative_fields(alternatives, repair_required=False)
    payload = json.loads(formatted["alternative_contracts_json"])
    assert formatted["alternative_contracts_count"] == 1
    assert formatted["contract_repair_action"] == "NOT_REQUIRED"
    assert payload[0]["symbol"] == "TEST260918P00095000"


def test_shadow_runner_expands_selected_and_complete_alternatives() -> None:
    alternative = {
        "symbol": "ALT",
        "strike": 105.0,
        "expiry": "2026-09-18",
        "dte": 35,
        "bid": 1.9,
        "ask": 2.1,
        "delta": 0.35,
        "gamma": 0.03,
        "theta": -0.04,
        "vega": 0.10,
        "iv": 0.40,
        "oi": 500,
        "volume": 100,
        "quote_timestamp_utc": "2026-08-14T10:30:00Z",
        "contract_multiplier": 100,
    }
    source = {
        "recommended_contract": "SELECTED",
        "alternative_contracts_json": json.dumps([alternative]),
    }
    candidates = _candidate_rows(source)
    assert len(candidates) == 2
    assert candidates[1]["contract_symbol"] == "ALT"
    assert candidates[1]["contract_delta"] == 0.35
    assert candidates[1]["contract_quote_timestamp_utc"] == "2026-08-14T10:30:00Z"
    assert candidates[1]["quote_timestamp_utc"] == "2026-08-14T10:30:00Z"


def test_missing_multiplier_is_not_fabricated_in_alternative_record() -> None:
    chain = pd.DataFrame(
        [{
            "symbol": "TEST260918C00105000", "right": "C", "strike": 105.0,
            "expiration_date": "2026-09-18", "dte": 35, "mark": 2.0,
            "bid": 1.9, "ask": 2.1, "delta": 0.35, "gamma": 0.03,
            "theta": -0.04, "vega": 0.1, "implied_vol": 0.4,
            "open_interest": 500, "volume": 100, "spread_pct": 0.1,
            "quote_timestamp_utc": "2026-08-14T10:30:00Z",
        }]
    )
    candidate = select_repair_alternative_contracts(chain, _context())[0]
    assert candidate["contract_multiplier"] is None


def test_ev3_candidate_set_is_two_expiries_by_three_delta_nearest_strikes() -> None:
    rows = []
    expiries = [
        ("2026-09-08", 25),
        ("2026-09-13", 30),
        ("2026-09-23", 40),
    ]
    for expiry_index, (expiry, dte) in enumerate(expiries):
        for strike_index, (strike, delta) in enumerate(
            [(98.0, 0.25), (100.0, 0.35), (102.0, 0.45), (104.0, 0.55)]
        ):
            rows.append({
                "symbol": f"TEST{expiry_index}{strike_index}",
                "right": "C",
                "strike": strike,
                "expiration_date": expiry,
                "dte": dte,
                "bid": 1.9,
                "ask": 2.1,
                "delta": delta,
                "gamma": 0.03,
                "theta": -0.04,
                "vega": 0.10,
                "implied_vol": 0.40,
                "open_interest": 500,
                "volume": 100,
                "quote_timestamp_utc": "2026-08-14T10:30:00Z",
            })
    candidates = select_repair_alternative_contracts(pd.DataFrame(rows), _context(), limit=6)
    assert len(candidates) == 6
    assert {candidate["expiry"] for candidate in candidates} == {"2026-09-08", "2026-09-13"}
    assert all(candidate["structure"] == "LONG_SINGLE" for candidate in candidates)
    assert all(candidate["candidate_generation_rank"] == index for index, candidate in enumerate(candidates, 1))

    formatted = _format_repair_alternative_fields(candidates, repair_required=False)
    assert formatted["alternative_contracts_count"] == 6
    assert len(json.loads(formatted["alternative_contracts_json"])) == 6
    assert formatted["alternative_contract_3"]


def test_ev3_candidate_set_rejects_fabricated_or_illiquid_quotes() -> None:
    base = {
        "symbol": "VALID",
        "right": "C",
        "strike": 100.0,
        "expiration_date": "2026-09-13",
        "dte": 30,
        "bid": 1.9,
        "ask": 2.1,
        "delta": 0.35,
        "gamma": 0.03,
        "theta": -0.04,
        "vega": 0.10,
        "implied_vol": 0.40,
        "open_interest": 500,
        "volume": 100,
        "quote_timestamp_utc": "2026-08-14T10:30:00Z",
    }
    missing_delta = dict(base, symbol="NO_DELTA", delta=None)
    illiquid = dict(base, symbol="ILLIQUID", open_interest=49, volume=0)
    candidates = select_repair_alternative_contracts(
        pd.DataFrame([base, missing_delta, illiquid]), _context(), limit=6
    )
    assert [candidate["symbol"] for candidate in candidates] == ["VALID"]


def test_vertical_candidates_support_bull_calls_and_bear_puts() -> None:
    def chain(direction: str) -> pd.DataFrame:
        right = "C" if direction == "CALL" else "P"
        sign = 1 if direction == "CALL" else -1
        rows = []
        for index, (strike, delta) in enumerate([(98.0, 0.30), (100.0, 0.35), (102.0, 0.40)]):
            rows.append({
                "symbol": f"TEST{right}{index}", "right": right, "strike": strike,
                "expiration_date": "2026-09-13", "dte": 30,
                "bid": 1.9, "ask": 2.1, "delta": sign * delta,
                "gamma": 0.03, "theta": -0.04, "vega": 0.10,
                "implied_vol": 0.40, "open_interest": 500, "volume": 100,
                "quote_timestamp_utc": "2026-08-14T10:30:00Z",
                "contract_multiplier": 100,
            })
        return pd.DataFrame(rows)

    calls = select_ev3_vertical_debit_candidates(chain("CALL"), _context("CALL"))
    puts = select_ev3_vertical_debit_candidates(chain("PUT"), _context("PUT"))
    assert calls and puts
    assert all(item["structure"] == "BULL_CALL_DEBIT" for item in calls)
    assert all(item["long_leg"]["strike"] < item["short_leg"]["strike"] for item in calls)
    assert all(item["structure"] == "BEAR_PUT_DEBIT" for item in puts)
    assert all(item["long_leg"]["strike"] > item["short_leg"]["strike"] for item in puts)
    assert all(item["long_leg"]["expiry"] == item["short_leg"]["expiry"] for item in calls + puts)

    formatted = _format_repair_alternative_fields(calls + puts, repair_required=False)
    payload = json.loads(formatted["alternative_contracts_json"])
    assert payload[0]["long_leg"]["contract_multiplier"] == 100
    assert payload[0]["short_leg"]["contract_multiplier"] == 100


def test_shadow_runner_preserves_vertical_leg_records() -> None:
    vertical = {
        "symbol": "BULL_CALL_DEBIT:LONG/SHORT",
        "structure": "BULL_CALL_DEBIT",
        "candidate_policy_version": "fixture-v1",
        "candidate_generation_rank": 1,
        "long_leg": {"symbol": "LONG", "strike": 100.0},
        "short_leg": {"symbol": "SHORT", "strike": 105.0},
        "strike_width": 5.0,
        "entry_debit_mid": 2.0,
    }
    candidates = _candidate_rows({"alternative_contracts_json": json.dumps([vertical])})
    assert len(candidates) == 1
    assert candidates[0]["contract_structure"] == "BULL_CALL_DEBIT"
    assert candidates[0]["long_leg"]["symbol"] == "LONG"
    assert candidates[0]["short_leg"]["symbol"] == "SHORT"


def test_polygon_reference_multiplier_uses_prefixed_contract_and_cache() -> None:
    original_get = oi._get
    calls = []
    oi._CONTRACT_MULTIPLIER_CACHE.clear()

    def fake_get(url, params=None):
        calls.append(url)
        return {"results": {"shares_per_contract": 100}}

    oi._get = fake_get
    try:
        first = oi._polygon_contract_multiplier("TEST260918C00100000")
        second = oi._polygon_contract_multiplier("O:TEST260918C00100000")
    finally:
        oi._get = original_get
        oi._CONTRACT_MULTIPLIER_CACHE.clear()
    assert first == (100.0, "polygon.reference.shares_per_contract")
    assert second == first
    assert len(calls) == 1
    assert calls[0].endswith("/O:TEST260918C00100000")
