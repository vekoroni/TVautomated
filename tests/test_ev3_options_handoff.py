from __future__ import annotations

import inspect
import json
from datetime import date

import pandas as pd
import scripts.avshunter_options_intelligence as oi

from scripts.avshunter_options_intelligence import (
    _annotate_ev3_handoff_frame,
    _coalesce_ev3_merge_inputs,
    _ev3_direction_fields,
    _ev3_handoff_fields,
    _format_repair_alternative_fields,
    _quote_timestamp_utc,
    _partition_complete_ev3_candidates,
    parse_structural_context,
    select_repair_alternative_contracts,
    select_ev3_vertical_debit_candidates,
    backfill_greeks_vectorised,
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


def test_iv_backfills_even_when_vendor_gamma_is_already_present() -> None:
    frame = pd.DataFrame([
        {
            "underlying_price": 100.0,
            "strike": 100.0,
            "dte": 30,
            "implied_vol": None,
            "right": "C",
            "mark": 2.50,
            "bid": 2.40,
            "ask": 2.60,
            "delta": 0.50,
            "gamma": 0.02,
            "theta": -0.04,
            "vega": 0.10,
        }
    ])

    result = backfill_greeks_vectorised(frame)

    assert float(result.loc[0, "implied_vol"]) > 0
    assert result.loc[0, "implied_vol_source"] == "BSM_SOLVED_FROM_MARK_V1"


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
    assert call["direction_status"] == "RESOLVED"
    assert call["direction_resolution_status"] == "RESOLVED"

    conflict = _ev3_direction_fields(
        {"direction": "PUT"},
        {"direction_arbitration_status": "CONFLICT_STRUCTURE_LEADS"},
    )
    assert conflict["canonical_direction"] == "PUT"
    assert conflict["direction_status"] == "RESOLVED"

    strangle = _ev3_direction_fields(
        {"direction": "STRANGLE"}, {"direction_arbitration_status": "AGREEMENT"}
    )
    assert strangle["canonical_direction"] == "STRANGLE"
    assert strangle["direction_status"] == "NON_DIRECTIONAL"


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
    assert result["direction_status"] == "RESOLVED"
    assert result["direction_resolution_status"] == "RESOLVED"
    assert result["direction_arbitration_status"] == "AGREEMENT"
    assert result["macro_conviction_score"] == 63.0
    assert result["bond_macro_flag"] == "BOND_MACRO_CAUTION"
    assert result["bond_trade_go"] is True
    assert result["auction_spread_risk"] == "LONG_END_AUCTION_WITHIN_5D"


def test_context_signal_row_never_evaluates_pandas_truthiness() -> None:
    series = pd.Series({"ticker": "TEST", "asof_date": "2026-08-28"})
    mapping = {"ticker": "DICT"}

    assert oi._context_signal_row({"_signal_row": series}) is series
    assert oi._context_signal_row({"_signal_row": mapping}) is mapping
    assert oi._context_signal_row({"_signal_row": None}) == {}
    assert oi._context_signal_row({"_signal_row": 42}) == {}


def test_lifecycle_adapter_accepts_production_shaped_series_context() -> None:
    ctx = _context()
    ctx.update({
        "ticker": "SERIES",
        "hold_days": 5,
        "_signal_row": pd.Series({
            "ticker": "SERIES",
            "asof_date": "2026-08-28",
            "garch_forecast_vol": 0.32,
        }),
    })
    contract = {
        "symbol": "SERIES260918C00100000",
        "strike": 100.0,
        "dte": 21,
        "delta": 0.40,
        "bid": 1.90,
        "ask": 2.00,
        "quote_timestamp_utc": "2026-08-28T20:00:00Z",
        "mark_synthetic": False,
    }

    lifecycle = oi._options_liquidity_lifecycle_fields(
        ctx, contract, {"hv_30d": 0.28, "atm_iv": 0.30}
    )

    assert lifecycle["thesis_id"] == "SERIES:CALL:2026-08-28:OLM2"
    assert lifecycle["legacy_thesis_id"] == "SERIES:CALL:2026-08-28"
    assert lifecycle["lifecycle_contract_version"] == "options-liquidity-lifecycle-v2"
    assert lifecycle["evidence_session_source"] == "SELECTED_CONTRACT_QUOTE_TIMESTAMP"
    assert lifecycle["morning_transition_state"] == "EOD_PENDING_MORNING_REQUOTE"
    assert lifecycle["maturation_execution_authority"] is False


def test_lifecycle_uses_governed_put_invalidation_and_routed_hold() -> None:
    ctx = _context(direction="PUT", stop=103.0, horizon="1_5d")
    ctx.update({
        "ticker": "PUTFIX",
        # PUT invalidation must already be above the thesis entry; the
        # lifecycle no longer repairs wrong-sided stops by mirroring them.
        "hold_days": 20,
        "_signal_row": pd.Series({
            "ticker": "PUTFIX",
            "asof_date": "2026-08-31",
            "garch_forecast_vol": 0.32,
        }),
    })
    contract = {
        "symbol": "PUTFIX260918P00100000",
        "strike": 100.0,
        "dte": 19,
        "delta": -0.40,
        "bid": 1.90,
        "ask": 2.00,
        "quote_timestamp_utc": "2026-08-28T20:00:00Z",
        "mark_synthetic": False,
        "contract_runway_floor_days": 19, "contract_runway_basis": "HORIZON:1_5d",
        "contract_runway_state": "RUNWAY_COVERED", "spread_above_limit": False,
    }

    lifecycle = oi._options_liquidity_lifecycle_fields(
        ctx, contract, {"hv_30d": 0.28, "atm_iv": 0.30}
    )

    # The selector's runway and spread facts reach the output row (Lab display, 18 Sep 2026).
    assert (lifecycle["contract_runway_floor_days"], lifecycle["contract_runway_basis"],
            lifecycle["contract_runway_state"], lifecycle["spread_above_limit"]) == (
        19, "HORIZON:1_5d", "RUNWAY_COVERED", False)
    assert lifecycle["invalidation_spot"] == 103.0
    assert lifecycle["invalidation_source"] == "stop_loss"
    assert lifecycle["planned_hold_sessions"] == 5.0
    assert lifecycle["minimum_required_dte"] == 19          # 13 sessions in calendar days (R3)
    # Completed-session evidence can prepare and rank the thesis, but cannot
    # claim current executability.  That state is minted only by the governed
    # post-open contract refresh.
    # The quote carries a provider timestamp: it awaits the morning re-quote (label, 18 Sep 2026).
    assert lifecycle["liquidity_state"] == "EOD_QUOTE_PENDING_MORNING_REQUOTE"
    assert lifecycle["remaining_runway_state"] == "THESIS_ACTIVE"
    assert lifecycle["thesis_state"] == "ACTIVE"


def test_no_primary_contract_repair_path_accepts_real_series_and_emits_diagnostics(
    monkeypatch,
) -> None:
    signal_row = pd.Series({
        "ticker": "SERIES",
        "tier": 0,
        "phase": "C",
        "precor_intent": "BUY_SETUP",
        "dominant_trend": "UP",
        "direction": "CALL",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "structural_target": 110.0,
        "vanguard_edge_direction": "CALL",
        "horizon_bucket": "1_5d",
        "asof_date": "2026-08-28",
        "hv_30d": 0.28,
        "iv_rank": 0.40,
        "iv_current": 0.30,
    })
    chain = pd.DataFrame([{
        "symbol": "SERIES260911C00100000",
        "right": "C",
        "strike": 100.0,
        "expiration_date": "2026-09-11",
        "dte": 14,
        "bid": 1.90,
        "ask": 2.00,
        "delta": 0.35,
        "gamma": 0.03,
        "theta": -0.04,
        "vega": 0.10,
        "implied_vol": 0.30,
        "open_interest": 5,
        "volume": 0,
        "quote_timestamp_utc": "2026-08-28T20:00:00Z",
        "contract_multiplier": 100,
        "md_quote_source": "marketdata.app",
    }])
    chain.attrs.update({
        "canonical_dataset_id": "series-regression",
        "canonical_provider": "MARKETDATA",
        "canonical_resolution": "CACHE_HIT",
    })

    monkeypatch.setattr(oi, "fetch_chain", lambda ticker: chain)
    monkeypatch.setattr(oi, "compute_gex", lambda *_: (pd.DataFrame(), None, 0.0))
    monkeypatch.setattr(oi, "compute_oi_walls", lambda *_: {})
    monkeypatch.setattr(oi, "compute_pcr", lambda *_: (None, "UNKNOWN"))
    monkeypatch.setattr(oi, "compute_gamma_island", lambda *_, **__: {})
    monkeypatch.setattr(oi, "compute_delta_weighted_oi", lambda *_: {}, raising=False)
    monkeypatch.setattr(oi, "compute_iv_context", lambda *_: {})
    monkeypatch.setattr(oi, "fetch_sector_regime", lambda *_: {})
    monkeypatch.setattr(oi, "select_best_contract", lambda *_: None)

    result = oi.process_ticker(signal_row)

    assert "truth value of a Series is ambiguous" not in str(result.get("stand_down_reason", ""))
    assert result["thesis_id"] == "SERIES:CALL:2026-08-28:OLM2"
    assert result["legacy_thesis_id"] == "SERIES:CALL:2026-08-28"
    assert result["evidence_session_date"] == "2026-08-28"
    assert result["morning_transition_state"] == "CONTRACT_REPRICE_REQUIRED"
    assert result["contract_repair_status"] == "CONTRACT_REPAIR_REQUIRED"
    assert result["alternative_contracts_count"] == 1
    assert result["repair_selector_diagnostics_version"] == "ev3-repair-selector-diagnostics-v1"
    assert result["repair_selector_final_bounded_candidate_count"] == 1
    assert result["repair_selector_retained_oi_below_50"] == 1
    assert result["repair_selector_retained_zero_volume"] == 1


def test_unsafe_signal_row_truthiness_pattern_cannot_return() -> None:
    source = inspect.getsource(oi)
    assert 'ctx.get("_signal_row") or {}' not in source
    assert "ctx.get('_signal_row') or {}" not in source


def test_run_session_governs_contract_and_repair_thesis_identity(monkeypatch) -> None:
    monkeypatch.setattr(oi, "_CDS_V2_SESSION", date(2026, 9, 4))
    ctx = _context(direction="CALL", stop=95.0)
    ctx.update({"ticker": "SESSION", "_signal_row": pd.Series({"asof_date": "2026-09-05"})})
    contract = {
        "symbol": "SESSION260918C00100000", "strike": 100.0, "dte": 14,
        "delta": 0.35, "bid": 1.9, "ask": 2.0,
        "quote_timestamp_utc": "2026-09-05T12:00:00Z", "mark_synthetic": False,
    }
    lifecycle = oi._options_liquidity_lifecycle_fields(ctx, contract, {})
    assert lifecycle["evidence_session_date"] == "2026-09-04"
    assert lifecycle["thesis_id"] == "SESSION:CALL:2026-09-04:OLM2"
    assert lifecycle["evidence_session_source"] == "CDS_RUN_SESSION"


def test_offline_replay_disables_auxiliary_provider_calls(monkeypatch) -> None:
    monkeypatch.setenv("AVSHUNTER_CANONICAL_OFFLINE_REPLAY", "1")
    calls = []

    def forbidden_get(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("provider call attempted during offline replay")

    monkeypatch.setattr(oi.MD_SESSION, "get", forbidden_get)
    monkeypatch.setattr(oi, "_MD_AVAILABLE", True)

    contract = {"mark": 1.0, "mark_synthetic": True}
    assert oi.enrich_contract_with_real_quotes(contract) is contract
    # F5 (19 Sep 2026): sector figures come from the canonical price store, never a provider, in replay too.
    assert oi.fetch_sector_regime("AAPL")["sector_data_source"] in (None, "CANONICAL_HISTORICAL_PRICE_DB")
    assert oi._fetch_underlying_nbbo_fields("AAPL")["l2_quote_source"] == "UNAVAILABLE"
    assert calls == []


def test_offline_replay_cannot_persist_historical_lifecycle_state() -> None:
    from canonical_data import CanonicalFeatureFlags

    replay = CanonicalFeatureFlags(
        enabled=True,
        write_through=False,
        stage_gating_enforced=True,
        offline_replay=True,
        ohlcv_mode="ACTIVE",
    )
    live = CanonicalFeatureFlags(
        enabled=True,
        write_through=True,
        stage_gating_enforced=True,
        offline_replay=False,
        ohlcv_mode="ACTIVE",
    )

    assert oi._canonical_lifecycle_persistence_enabled(replay) is False
    assert oi._canonical_lifecycle_persistence_enabled(live) is True


def test_two_independent_families_resolve_mixed_transition_direction() -> None:
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
        "directional_force": 10.0,
    })
    ctx = parse_structural_context(row)
    assert ctx["direction"] == "CALL"
    assert ctx["direction_override_reason"] == "DIRECTION_RESOLVED_PRECONTRACT"
    assert ctx["direction_resolution_evidence_count"] == 2


def test_ev3_handoff_rejects_wrong_side_stop_for_put_with_provenance() -> None:
    fields = _ev3_handoff_fields(_context("PUT", stop=95.0))
    assert fields["invalidation_spot"] is None
    assert fields["invalidation_state"] == "DATA_DEFECT_WRONG_SIDE"
    assert fields["invalidation_source"] == "MISSING_AUTHORITATIVE_STOP"


def test_ev3_handoff_does_not_promote_a_legacy_default_stop() -> None:
    ctx = _context()
    ctx["stop_authoritative"] = False
    fields = _ev3_handoff_fields(ctx)
    assert fields["invalidation_spot"] is None
    assert fields["invalidation_source"] == "MISSING_AUTHORITATIVE_STOP"


def test_structural_context_does_not_fabricate_missing_stop_or_target() -> None:
    ctx = parse_structural_context(pd.Series({
        "ticker": "NOSTOP",
        "tier": 1,
        "phase": "C",
        "precor_intent": "BUY_SETUP",
        "dominant_trend": "UP",
        "direction": "CALL",
        "stock_price": 100.0,
        "entry_price": 100.0,
        "horizon_bucket": "6_10d",
    }))

    assert ctx["stop"] is None
    assert ctx["stop_dist"] is None
    assert ctx["stop_source"] == "MISSING_AUTHORITATIVE_STOP"
    assert ctx["structural_target"] is None


def test_non_directional_lifecycle_is_not_misclassified_as_data_defect() -> None:
    ctx = _context("STRANGLE", stop=95.0)
    ctx.update({"ticker": "ND", "_signal_row": pd.Series({"ticker": "ND"})})

    lifecycle = oi._options_liquidity_lifecycle_fields(ctx, {}, {})

    assert lifecycle["thesis_state"] == "NOT_APPLICABLE"
    assert lifecycle["liquidity_state"] == "NOT_EVALUATED_NON_DIRECTIONAL"
    assert lifecycle["recovery_disposition"] == "NOT_APPLICABLE"
    assert lifecycle["executable_now"] is False


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
    # ACK 18 Sep 2026 (a): the runway floor is the 20-session planned hold (40 calendar days), so the two
    # expiries nearest to covering it are 30 and 40 days (was 25 and 30 under the anticipated-move floor).
    assert {candidate["expiry"] for candidate in candidates} == {"2026-09-13", "2026-09-23"}
    assert all(candidate["structure"] == "LONG_SINGLE" for candidate in candidates)
    assert all(candidate["candidate_generation_rank"] == index for index, candidate in enumerate(candidates, 1))

    formatted = _format_repair_alternative_fields(candidates, repair_required=False)
    assert formatted["alternative_contracts_count"] == 6
    assert len(json.loads(formatted["alternative_contracts_json"])) == 6
    assert formatted["alternative_contract_3"]


def test_ev3_candidate_set_rejects_incomplete_or_invalid_quotes() -> None:
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
    invalid_quote = dict(base, symbol="ZERO_BID", bid=0.0, ask=2.1)
    candidates = select_repair_alternative_contracts(
        pd.DataFrame([base, missing_delta, invalid_quote]), _context(), limit=6
    )
    assert [candidate["symbol"] for candidate in candidates] == ["VALID"]


def _tc08_repair_row(
    *,
    symbol: str,
    direction: str = "CALL",
    oi: object = 5,
    volume: object = 2,
    bid: float = 1.95,
    ask: float = 2.05,
    delta_abs: float = 0.35,
    strike: float = 100.0,
) -> dict:
    right = "C" if direction == "CALL" else "P"
    sign = 1.0 if direction == "CALL" else -1.0
    return {
        "symbol": symbol,
        "right": right,
        "strike": strike,
        "expiration_date": "2026-09-13",
        "dte": 30,
        "bid": bid,
        "ask": ask,
        "delta": sign * delta_abs,
        "gamma": 0.03,
        "theta": -0.04,
        "vega": 0.10,
        "implied_vol": 0.40,
        "open_interest": oi,
        "volume": volume,
        "quote_timestamp_utc": "2026-08-14T10:30:00Z",
        "contract_multiplier": 100,
    }


def test_tc08_low_and_zero_oi_volume_are_ranking_evidence_for_calls_and_puts() -> None:
    for direction in ("CALL", "PUT"):
        rows = [
            _tc08_repair_row(
                symbol=f"{direction}_LOW", direction=direction, oi=5, volume=2
            ),
            _tc08_repair_row(
                symbol=f"{direction}_ZERO", direction=direction, oi=0, volume=0,
                delta_abs=0.36, strike=101.0 if direction == "CALL" else 99.0,
            ),
        ]
        candidates = select_repair_alternative_contracts(
            pd.DataFrame(rows), _context(direction), limit=6
        )
        assert {candidate["symbol"] for candidate in candidates} == {
            f"{direction}_LOW", f"{direction}_ZERO"
        }
        assert all(candidate["oi_used_as_hard_gate"] is False for candidate in candidates)
        assert all(candidate["volume_used_as_hard_gate"] is False for candidate in candidates)
        assert all(
            candidate["candidate_policy_version"] == "ev3-long-single-candidates-v0.3.0"
            for candidate in candidates
        )


def test_tc08_missing_oi_volume_are_explicit_and_do_not_fabricate_authority() -> None:
    row = _tc08_repair_row(symbol="MISSING_EVIDENCE", oi=None, volume=None)
    candidates = select_repair_alternative_contracts(
        pd.DataFrame([row]), _context(), limit=6
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["oi"] == 0.0
    assert candidate["volume"] == 0.0
    assert candidate["oi_observation_status"] == "MISSING_ASSUMED_ZERO"
    assert candidate["volume_observation_status"] == "MISSING_ASSUMED_ZERO"
    assert candidate["oi_used_as_hard_gate"] is False
    assert candidate["volume_used_as_hard_gate"] is False


def test_tc08_quote_quality_still_overrides_high_oi_for_calls_and_puts() -> None:
    for direction in ("CALL", "PUT"):
        zero_bid = _tc08_repair_row(
            symbol=f"{direction}_ZERO_BID", direction=direction,
            oi=10_000, volume=5_000, bid=0.0, ask=2.05,
        )
        wide_spread = _tc08_repair_row(
            symbol=f"{direction}_WIDE", direction=direction,
            oi=10_000, volume=5_000, bid=1.0, ask=2.0,
        )
        assert select_repair_alternative_contracts(
            pd.DataFrame([zero_bid, wide_spread]), _context(direction), limit=6
        ) == []


def test_tc08_oi_volume_break_only_true_delta_and_spread_ties() -> None:
    low = _tc08_repair_row(symbol="LOW_EVIDENCE", oi=5, volume=2)
    high = _tc08_repair_row(symbol="HIGH_EVIDENCE", oi=500, volume=100)
    candidates = select_repair_alternative_contracts(
        pd.DataFrame([low, high]), _context(), limit=6
    )
    assert [candidate["symbol"] for candidate in candidates] == [
        "HIGH_EVIDENCE", "LOW_EVIDENCE"
    ]


def test_tc08_serialized_contract_family_is_bounded_and_schema_versioned() -> None:
    rows = [
        _tc08_repair_row(
            symbol=f"LOW_{index}", oi=index, volume=0,
            delta_abs=0.25 + index * 0.01, strike=97.0 + index,
        )
        for index in range(8)
    ]
    candidates = select_repair_alternative_contracts(
        pd.DataFrame(rows), _context(), limit=6
    )
    assert len(candidates) == 3  # one expiry, bounded to three strikes
    formatted = _format_repair_alternative_fields(candidates, repair_required=True)
    assert formatted["alternative_contracts_schema_version"] == "ev3-contract-candidates-v4"
    payload = json.loads(formatted["alternative_contracts_json"])
    assert len(payload) == 3
    assert all(item["oi_used_as_hard_gate"] is False for item in payload)
    assert all(item["volume_used_as_hard_gate"] is False for item in payload)


def test_tc08_repair_selector_publishes_required_observability_counts() -> None:
    valid_low = _tc08_repair_row(symbol="VALID_LOW", oi=5, volume=2)
    valid_zero = _tc08_repair_row(
        symbol="VALID_ZERO", oi=0, volume=0, delta_abs=0.36, strike=101.0,
    )
    valid_missing = _tc08_repair_row(
        symbol="VALID_MISSING", oi=None, volume=None, delta_abs=0.37, strike=102.0,
    )
    invalid_quote = _tc08_repair_row(symbol="INVALID_QUOTE", oi=500, volume=100)
    invalid_quote["ask"] = None
    invalid_spread = _tc08_repair_row(
        symbol="INVALID_SPREAD", oi=500, volume=100, bid=1.0, ask=2.0,
    )
    invalid_geometry = _tc08_repair_row(symbol="INVALID_GEOMETRY", oi=500, volume=100)
    # A longer contract is never dropped (ACK 18 Sep 2026: the horizon informs contract choice, never gates it); a contract that cannot be held past issue is.
    invalid_geometry["dte"] = 2

    diagnostics = oi._new_repair_selector_diagnostics()
    candidates = select_repair_alternative_contracts(
        pd.DataFrame([
            valid_low,
            valid_zero,
            valid_missing,
            invalid_quote,
            invalid_spread,
            invalid_geometry,
        ]),
        _context(),
        limit=6,
        diagnostics=diagnostics,
    )

    assert {candidate["symbol"] for candidate in candidates} == {
        "VALID_LOW", "VALID_ZERO", "VALID_MISSING"
    }
    assert diagnostics == {
        "retained_oi_below_50": 2,
        "retained_zero_volume": 1,
        "rejected_invalid_missing_quote": 1,
        "rejected_spread": 1,
        "rejected_dte_delta_geometry": 1,
        "final_bounded_candidate_count": 3,
    }


def test_tc08_repair_selector_diagnostics_aggregate_without_affecting_authority() -> None:
    first = oi._repair_selector_diagnostic_fields({
        "retained_oi_below_50": 2,
        "retained_zero_volume": 1,
        "rejected_invalid_missing_quote": 3,
        "rejected_spread": 4,
        "rejected_dte_delta_geometry": 5,
        "final_bounded_candidate_count": 2,
    })
    second = oi._repair_selector_diagnostic_fields({
        "retained_oi_below_50": 1,
        "retained_zero_volume": 1,
        "rejected_invalid_missing_quote": 0,
        "rejected_spread": 2,
        "rejected_dte_delta_geometry": 1,
        "final_bounded_candidate_count": 1,
    })

    aggregate = oi._aggregate_repair_selector_diagnostics([
        {"ticker": "ONE", **first},
        {"ticker": "TWO", **second},
        {"ticker": "LEGACY_WITHOUT_DIAGNOSTICS"},
    ])

    assert aggregate == {
        "diagnostics_version": "ev3-repair-selector-diagnostics-v1",
        "selector_invocations": 2,
        "retained_oi_below_50": 3,
        "retained_zero_volume": 2,
        "rejected_invalid_missing_quote": 3,
        "rejected_spread": 6,
        "rejected_dte_delta_geometry": 6,
        "final_bounded_candidate_count": 3,
    }


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


def test_multiplier_enrichment_uses_guarded_occ_standard_convention() -> None:
    selected = {
        "symbol": "TEST260918C00100000", "expiry": "2026-09-18",
        "contract_multiplier": None,
    }
    alternative = {
        "symbol": "TEST260918P00100000", "expiry": "2026-09-18",
        "contract_multiplier": None,
    }
    oi._enrich_ev3_contract_multipliers(selected, [alternative], "TEST")
    assert selected["contract_multiplier"] == 100
    assert alternative["contract_multiplier"] == 100
    assert selected["contract_multiplier_source"] == "OCC_STANDARD_100_INFERRED"
    assert selected["contract_multiplier_inferred"] is True


def test_multiplier_enrichment_refuses_adjusted_occ_root() -> None:
    adjusted = {"symbol": "TEST1260918C00100000", "contract_multiplier": None}
    oi._enrich_ev3_contract_multipliers(adjusted, [], "TEST")
    assert adjusted["contract_multiplier"] is None
    assert adjusted["contract_multiplier_source"] == "UNRESOLVED_NONSTANDARD_OR_ADJUSTED_OCC"


def _complete_ev3_candidate() -> dict:
    return {
        "symbol": "TEST260918C00100000", "structure": "LONG_SINGLE",
        "strike": 100.0, "expiry": "2026-09-18", "dte": 29,
        "bid": 2.0, "ask": 2.2, "delta": 0.45, "gamma": 0.03,
        "theta": -0.04, "vega": 0.10, "iv": 0.40, "oi": 200,
        "volume": 50, "quote_timestamp_utc": "2026-08-20T12:00:00Z",
        "contract_multiplier": 100,
    }


def test_candidate_partition_removes_incomplete_alternatives_with_diagnostics() -> None:
    complete = _complete_ev3_candidate()
    incomplete = dict(complete)
    incomplete["contract_multiplier"] = None
    accepted, rejected = _partition_complete_ev3_candidates([complete, incomplete])
    assert accepted == [complete]
    assert len(rejected) == 1
    assert "contract_multiplier" in rejected[0]["missing_fields"]


def test_selected_handoff_annotation_distinguishes_scope_and_defects() -> None:
    base = {
        "canonical_direction": "CALL", "recommended_contract": "TEST260918C00100000",
        "entry_spot": 100, "target_spot": 110, "invalidation_spot": 95,
        "planned_hold_sessions": 10, "ev3_barrier_state_key": "A|B|C|D|E|F|G",
        "contract_strike": 100, "contract_expiry": "2026-09-18", "contract_dte": 29,
        "contract_bid": 2.0, "contract_ask": 2.2, "contract_delta": 0.45,
        "contract_gamma": 0.03, "contract_theta": -0.04, "contract_vega": 0.10,
        "contract_iv": 0.40, "contract_oi": 200, "contract_volume": 50,
        "contract_quote_timestamp_utc": "2026-08-20T12:00:00Z", "contract_multiplier": 100,
    }
    incomplete = dict(base)
    incomplete["contract_multiplier"] = None
    non_directional = dict(base)
    non_directional["canonical_direction"] = "STRANGLE"
    no_contract = dict(base)
    no_contract["recommended_contract"] = None
    result = _annotate_ev3_handoff_frame(
        pd.DataFrame([base, incomplete, non_directional, no_contract])
    )
    assert result["ev3_selected_handoff_status"].tolist() == [
        "COMPLETE", "INCOMPLETE", "NOT_APPLICABLE_NON_DIRECTIONAL",
        "NOT_APPLICABLE_NO_SELECTED_CONTRACT",
    ]
    assert "contract_multiplier" in json.loads(
        result.iloc[1]["ev3_selected_handoff_missing_fields_json"]
    )
