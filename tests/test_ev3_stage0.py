from __future__ import annotations

import math

import pandas as pd

from vanguard.ev3_stage0 import (
    BarrierGrid,
    build_barrier_cache_from_frames,
    classify_barrier_path,
    validate_ev3_dataframe,
    validate_ev3_input,
)


def _valid_row(direction: str = "CALL") -> dict:
    call = direction == "CALL"
    return {
        "ticker": "TEST",
        "canonical_direction": direction,
        "direction_status": "RESOLVED",
        "entry_spot": 100.0,
        "target_spot": 110.0 if call else 90.0,
        "invalidation_spot": 95.0 if call else 105.0,
        "horizon_bucket": "6_10d",
        "planned_hold_sessions": 10,
        "state_key": "NORMAL|UP|STRONG|MODERATE|MARKUP|EARLY|MID",
        "contract_symbol": "TEST260918C00100000" if call else "TEST260918P00100000",
        "contract_strike": 100.0,
        "contract_expiry": "2026-09-18",
        "quote_timestamp_utc": "2026-08-10T12:00:00Z",
        "contract_bid": 2.0,
        "contract_ask": 2.2,
        "contract_dte": 30,
        "contract_delta": 0.45 if call else -0.45,
        "contract_gamma": 0.03,
        "contract_theta": -0.04,
        "contract_vega": 0.10,
        "contract_iv": 0.40,
        "contract_oi": 200,
        "contract_volume": 50,
        "contract_multiplier": 100,
        "expected_move_10d": 0.08,
    }


def test_validator_accepts_direction_correct_call_and_put() -> None:
    for direction in ("CALL", "PUT"):
        result = validate_ev3_input(_valid_row(direction), now_utc="2026-08-10T12:05:00Z")
        assert result.accepted is True
        assert result.reason_code == "ACCEPTED"
        assert math.isclose(result.canonical["rr_underlying"], 2.0)
        assert result.canonical["horizon_bucket"] == "6_10D"


def test_validator_rejects_unresolved_direction_before_economics() -> None:
    row = _valid_row()
    row["direction_status"] = "NOT_EVALUATED"
    result = validate_ev3_input(row, now_utc="2026-08-10T12:05:00Z")
    assert result.accepted is False
    assert result.reason_code == "REJECT_DIRECTION_UNRESOLVED"


def test_validator_accepts_current_resolved_arbitration_vocabularies() -> None:
    for status in ("AGREEMENT", "NO_PROBABILITY_OPINION", "CONFLICT_STRUCTURE_LEADS"):
        row = _valid_row()
        row["direction_status"] = status
        result = validate_ev3_input(row, now_utc="2026-08-10T12:05:00Z")
        assert result.accepted is True
        assert result.canonical["direction_resolution_status"] == "RESOLVED"


def test_validator_routes_non_directional_strategy_outside_directional_ev3() -> None:
    row = _valid_row()
    row["canonical_direction"] = "STRANGLE"
    result = validate_ev3_input(row, now_utc="2026-08-10T12:05:00Z")
    assert result.accepted is False
    assert result.reason_code == "NOT_APPLICABLE_NON_DIRECTIONAL"
    assert result.canonical["direction_resolution_status"] == "NON_DIRECTIONAL"


def test_validator_rejects_bad_topology_and_unit_move() -> None:
    topology = _valid_row("PUT")
    topology["invalidation_spot"] = 95.0
    assert validate_ev3_input(topology, now_utc="2026-08-10T12:05:00Z").reason_code == "REJECT_THESIS_TOPOLOGY"

    units = _valid_row()
    units["expected_move_10d"] = 7.0
    assert validate_ev3_input(units, now_utc="2026-08-10T12:05:00Z").reason_code == "REJECT_UNIT_MOVE"


def test_validator_does_not_derive_horizon_from_dte() -> None:
    row = _valid_row()
    row["contract_dte"] = 120
    result = validate_ev3_input(row, now_utc="2026-08-10T12:05:00Z")
    assert result.accepted
    assert result.canonical["horizon_bucket"] == "6_10D"
    assert result.canonical["planned_hold_sessions"] == 10


def test_validator_requires_governed_horizon_endpoint() -> None:
    row = _valid_row()
    row["planned_hold_sessions"] = 8
    result = validate_ev3_input(row, now_utc="2026-08-10T12:05:00Z")
    assert not result.accepted
    assert result.reason_code == "REJECT_HORIZON"
    assert "requires endpoint=10" in result.detail


def test_dataframe_diagnostics_are_stable_and_complete() -> None:
    invalid = _valid_row()
    invalid["direction_status"] = "NOT_EVALUATED"
    accepted, diagnostics = validate_ev3_dataframe(
        pd.DataFrame([_valid_row(), invalid]), now_utc="2026-08-10T12:05:00Z"
    )
    assert len(accepted) == 1
    assert diagnostics["ev3_status"].tolist() == ["ACCEPTED", "REJECTED"]
    assert diagnostics["ev3_reason_code"].tolist() == ["ACCEPTED", "REJECT_DIRECTION_UNRESOLVED"]


def test_validator_enforces_freshness_spread_dte_and_multiplier() -> None:
    stale = _valid_row()
    assert validate_ev3_input(stale, now_utc="2026-08-12T12:00:00Z").reason_code == "REJECT_QUOTE_STALE"

    spread = _valid_row()
    spread["contract_bid"] = 0.1
    spread["contract_ask"] = 1.0
    assert validate_ev3_input(spread, now_utc="2026-08-10T12:05:00Z").accepted

    zero_bid = _valid_row()
    zero_bid["contract_bid"] = 0.0
    assert validate_ev3_input(zero_bid, now_utc="2026-08-10T12:05:00Z").reason_code == "REJECT_LIQUIDITY_ZERO_BID"

    invalid_market = _valid_row()
    invalid_market["contract_ask"] = 0.0
    assert validate_ev3_input(
        invalid_market, now_utc="2026-08-10T12:05:00Z"
    ).reason_code == "REJECT_QUOTE_INVALID_MARKET"

    dte = _valid_row()
    dte["contract_dte"] = 10
    assert validate_ev3_input(dte, now_utc="2026-08-10T12:05:00Z").reason_code == "REJECT_DTE_FEASIBILITY"

    multiplier = _valid_row()
    del multiplier["contract_multiplier"]
    assert validate_ev3_input(multiplier, now_utc="2026-08-10T12:05:00Z").reason_code == "REJECT_CONTRACT_MULTIPLIER"


def test_path_classifier_covers_target_stop_timeout_and_ambiguous() -> None:
    assert classify_barrier_path([106, 107], [99, 100], entry=100, direction="CALL", target_distance=0.05, stop_distance=0.05) == ("TARGET_FIRST", 1)
    assert classify_barrier_path([101, 102], [94, 96], entry=100, direction="CALL", target_distance=0.05, stop_distance=0.05) == ("STOP_FIRST", 1)
    assert classify_barrier_path([102, 103], [98, 97], entry=100, direction="CALL", target_distance=0.05, stop_distance=0.05) == ("TIMEOUT", 2)
    assert classify_barrier_path([106, 107], [94, 96], entry=100, direction="CALL", target_distance=0.05, stop_distance=0.05) == ("AMBIGUOUS", 1)


def test_put_path_is_direction_conditioned() -> None:
    outcome = classify_barrier_path(
        [101, 102],
        [94, 93],
        entry=100,
        direction="PUT",
        target_distance=0.05,
        stop_distance=0.05,
    )
    assert outcome == ("TARGET_FIRST", 1)


def test_small_barrier_sidecar_has_exhaustive_probabilities() -> None:
    dates = pd.bdate_range("2026-01-02", periods=30)
    history = pd.DataFrame(
        {
            "date": dates,
            "close": [100.0] * 30,
            "high": [100.0, 106.0, 100.0, 100.0, 100.0] + [106.0] * 25,
            "low": [100.0, 99.0, 94.0, 100.0, 100.0] + [94.0] * 25,
        }
    )
    states = pd.DataFrame(
        {
            "ticker": ["TEST", "TEST", "TEST"],
            "date": [dates[0], dates[1], dates[2]],
            "vol_regime": ["NORMAL"] * 3,
            "trend_direction": ["UP"] * 3,
            "structure_quality": ["STRONG"] * 3,
            "adx_bucket": ["MODERATE"] * 3,
            "wyckoff_phase_bucket": ["MARKUP"] * 3,
            "trend_maturity": ["EARLY"] * 3,
            "atr_pct_bucket": ["MID"] * 3,
        }
    )
    grid = BarrierGrid(targets=(0.05,), stops=(0.05,), horizons=(5,), shrinkage_k=30)
    cache, audit = build_barrier_cache_from_frames(
        states,
        {"TEST": history},
        grid=grid,
        built_at_utc="2026-08-10T00:00:00+00:00",
    )
    assert audit["status"] == "PASS"
    assert len(cache) == 2  # CALL and PUT
    assert (cache["probability_sum"] - 1).abs().max() <= 1e-9
    assert set(cache["direction"]) == {"CALL", "PUT"}
    assert not cache.duplicated(
        [
            "state_key",
            "direction",
            "horizon_sessions",
            "target_distance_fraction",
            "stop_distance_fraction",
            "calculation_version",
        ]
    ).any()


def test_barrier_sidecar_uses_horizon_specific_maturity() -> None:
    dates = pd.bdate_range("2026-01-02", periods=30)
    history = pd.DataFrame(
        {"date": dates, "close": 100.0, "high": 101.0, "low": 99.0}
    )
    states = pd.DataFrame(
        {
            "ticker": ["TEST"] * 3,
            "date": [dates[4], dates[14], dates[20]],
            "vol_regime": ["NORMAL"] * 3,
            "trend_direction": ["UP"] * 3,
            "structure_quality": ["STRONG"] * 3,
            "adx_bucket": ["MODERATE"] * 3,
            "wyckoff_phase_bucket": ["MARKUP"] * 3,
            "trend_maturity": ["EARLY"] * 3,
            "atr_pct_bucket": ["MID"] * 3,
        }
    )
    grid = BarrierGrid(targets=(0.05,), stops=(0.05,), horizons=(5, 10, 20))
    cache, _ = build_barrier_cache_from_frames(states, {"TEST": history}, grid=grid)
    call = cache[cache["direction"] == "CALL"].set_index("horizon_sessions")
    assert call.loc[5, "n_nominal"] == 3
    assert call.loc[10, "n_nominal"] == 2
    assert call.loc[20, "n_nominal"] == 1
