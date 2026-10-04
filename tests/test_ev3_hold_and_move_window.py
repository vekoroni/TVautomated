"""EV3 values a contract at the governed hold AND at the thesis move window (ACK option 3, 28 Sep 2026).

Background: ACK decided on 18 Sep 2026 that the planned hold is the governed thesis window (20
sessions on every row) and the contract runway is bought for that hold, while the anticipated move
(Discovery's thesis horizon: 5, 10 or 20 sessions) stays a separate, descriptive fact. EV3's entry
check was never updated: it still required hold == horizon endpoint, so since 19 Sep every 1_5d and
6_10d row was rejected (REJECT_HORIZON) and the Lab has shown no EV.

Business rules:
- The lead value is the contract valued at the hold it will actually be held for (the governed
  hold). It is what ev_predicted publishes and what the selector ranks on.
- The same contract is also valued at its move window (anticipated_move_sessions, else the thesis
  horizon bucket's endpoint) and published beside the lead value, labelled as such.
- A hold the barrier cache never materialised (anything but 5, 10, 20 sessions) still fails closed.
- A move window that cannot be valued is typed NOT_EVALUATED with its reason; it never removes the
  lead value and is never filled with the lead value.
- Nothing here grants authority: EV3 stays advisory.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vanguard.ev3_stage0 import validate_ev3_input  # noqa: E402
from vanguard.ev_engine_v3 import EV3BarrierCache, evaluate_contract, select_contract  # noqa: E402

NOW = "2026-08-10T12:05:00Z"
STATE = "NORMAL|UP|STRONG|MODERATE|MARKUP|EARLY|MID"
# Distinct barrier facts per horizon so a value can be traced to the horizon that produced it.
CELLS = {5: (0.30, 0.40, 2.0, 2.0), 10: (0.45, 0.35, 4.0, 3.0), 20: (0.55, 0.30, 8.0, 5.0)}
VALUE_FIELDS = ("ev_base_return", "ev_stress_return", "ev_conservative_return", "ev_lower_bound_return",
                "p_target", "p_stop", "p_timeout")


def _cache(horizons=(5, 10, 20)) -> EV3BarrierCache:
    rows = []
    for direction in ("CALL", "PUT"):
        for horizon in horizons:
            p_target, p_stop, target_exit, stop_exit = CELLS[horizon]
            rows.append({
                "state_key": STATE, "direction": direction, "horizon_sessions": horizon,
                "target_distance_fraction": 0.10, "stop_distance_fraction": 0.05,
                "p_target_first": p_target, "p_stop_first": p_stop, "p_timeout": 1.0 - p_target - p_stop,
                "n_effective": 250, "target_exit_session_mean": target_exit,
                "stop_exit_session_mean_conservative": stop_exit, "timeout_exit_session": float(horizon),
                "calculation_version": "fixture-v1", "schema_version": "fixture-v1",
            })
    return EV3BarrierCache(pd.DataFrame(rows))


def _row(direction: str = "CALL", *, bucket: str = "1_5d", hold: int = 20, **extra) -> dict:
    call = direction == "CALL"
    row = {
        "ticker": "TEST", "canonical_direction": direction, "direction_status": "RESOLVED",
        "entry_spot": 100.0, "target_spot": 110.0 if call else 90.0, "invalidation_spot": 95.0 if call else 105.0,
        "horizon_bucket": bucket, "planned_hold_sessions": hold, "state_key": STATE,
        "contract_symbol": "TEST261009C00100000" if call else "TEST261009P00100000",
        "contract_strike": 100.0, "contract_expiry": "2026-10-09", "quote_timestamp_utc": "2026-08-10T12:00:00Z",
        "contract_bid": 5.8, "contract_ask": 6.2, "contract_dte": 60,
        "contract_delta": 0.52 if call else -0.48, "contract_gamma": 0.03, "contract_theta": -0.04,
        "contract_vega": 0.10, "contract_iv": 0.40, "contract_oi": 500, "contract_volume": 100,
        "contract_multiplier": 100, "risk_free_rate": 0.04, "dividend_yield": 0.01,
    }
    row.update(extra)
    return row


def _vertical(direction: str = "CALL", **kw) -> dict:
    row = _row(direction, **kw)
    call = direction == "CALL"
    row["contract_symbol"] = f"{'BULL_CALL' if call else 'BEAR_PUT'}:LONG/SHORT"
    row["contract_structure"] = "BULL_CALL_DEBIT" if call else "BEAR_PUT_DEBIT"

    def leg(symbol, strike, bid, ask, delta):
        return {"symbol": symbol, "strike": strike, "expiry": "2026-10-09", "dte": 60, "bid": bid, "ask": ask,
                "delta": delta, "gamma": 0.03, "theta": -0.04, "vega": 0.10, "iv": 0.40, "oi": 500,
                "volume": 100, "quote_timestamp_utc": "2026-08-10T12:00:00Z", "contract_multiplier": 100}

    if call:
        row["long_leg"], row["short_leg"] = leg("LONG_CALL", 100.0, 5.8, 6.2, 0.52), leg("SHORT_CALL", 105.0, 3.3, 3.7, 0.35)
    else:
        row["long_leg"], row["short_leg"] = leg("LONG_PUT", 100.0, 5.8, 6.2, -0.52), leg("SHORT_PUT", 95.0, 3.3, 3.7, -0.35)
    return row


def _assert_move_window_equals_lead_of(result: dict, reference: dict) -> None:
    assert reference["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE", reference
    for field in VALUE_FIELDS:
        assert math.isclose(result[f"ev3_move_window_{field}"], reference[f"ev3_{field}"], rel_tol=1e-12), field


# --- entry check -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bucket,endpoint", [("1_5d", 5), ("6_10d", 10), ("11_20d", 20)])
def test_every_thesis_horizon_is_accepted_at_the_governed_20_session_hold(bucket, endpoint):
    result = validate_ev3_input(_row(bucket=bucket), now_utc=NOW)
    assert result.accepted, (result.reason_code, result.detail)
    assert result.canonical["planned_hold_sessions"] == 20
    assert result.canonical["move_window_sessions"] == endpoint
    assert result.canonical["move_window_source"] == "HORIZON_BUCKET_ENDPOINT"


def test_the_move_window_is_the_anticipated_move_before_the_bucket_endpoint():
    result = validate_ev3_input(_row(bucket="1_5d", anticipated_move_sessions=10), now_utc=NOW)
    assert result.accepted
    assert result.canonical["move_window_sessions"] == 10
    assert result.canonical["move_window_source"] == "ANTICIPATED_MOVE_SESSIONS"


def test_a_hold_the_barrier_cache_never_materialised_still_fails_closed():
    result = validate_ev3_input(_row(bucket="1_5d", hold=15), now_utc=NOW)
    assert not result.accepted
    assert result.reason_code == "REJECT_HORIZON"
    assert "materialised=5,10,20" in result.detail


# --- valuation -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_a_short_move_window_thesis_is_valued_at_the_hold_it_will_be_held_for(direction):
    result = evaluate_contract(_row(direction, bucket="1_5d"), _cache(), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE", result
    assert result["ev3_horizon_sessions"] == 20 and result["ev3_hold_sessions"] == 20
    assert result["ev3_p_target"] == pytest.approx(CELLS[20][0])
    assert result["ev3_capital_eligible"] is False


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_the_same_contract_is_also_valued_at_its_move_window(direction):
    result = evaluate_contract(_row(direction, bucket="1_5d"), _cache(), now_utc=NOW)
    assert result["ev3_move_window_sessions"] == 5
    assert result["ev3_move_window_source"] == "HORIZON_BUCKET_ENDPOINT"
    assert result["ev3_move_window_status"] == "EVALUATED"
    # Valuing at the move window must equal valuing the same contract with a hold of that length.
    reference = evaluate_contract(_row(direction, bucket="1_5d", hold=5), _cache(), now_utc=NOW)
    _assert_move_window_equals_lead_of(result, reference)
    # and the lead value is still the 20-session one
    assert result["ev3_p_target"] != result["ev3_move_window_p_target"]


def test_a_move_window_equal_to_the_hold_repeats_the_hold_value():
    result = evaluate_contract(_row(bucket="11_20d"), _cache(), now_utc=NOW)
    assert result["ev3_move_window_sessions"] == 20
    _assert_move_window_equals_lead_of(result, result)


def test_a_move_window_that_cannot_be_valued_is_typed_and_never_borrows_the_hold_value():
    result = evaluate_contract(_row(bucket="1_5d"), _cache(horizons=(10, 20)), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE"      # the lead value survives
    assert result["ev3_move_window_status"] == "NOT_EVALUATED"
    assert str(result["ev3_move_window_reason_code"]).startswith("REJECT_")
    for field in VALUE_FIELDS:
        assert result[f"ev3_move_window_{field}"] is None


@pytest.mark.parametrize("direction", ["CALL", "PUT"])
def test_a_vertical_debit_is_valued_at_the_hold_and_at_the_move_window(direction):
    result = evaluate_contract(_vertical(direction, bucket="1_5d"), _cache(), now_utc=NOW)
    assert result["ev3_status"] == "EVALUATED_PRODUCTION_EVIDENCE", result
    assert result["ev3_horizon_sessions"] == 20 and result["ev3_move_window_sessions"] == 5
    reference = evaluate_contract(_vertical(direction, bucket="1_5d", hold=5), _cache(), now_utc=NOW)
    _assert_move_window_equals_lead_of(result, reference)


def test_the_selector_ranks_on_the_hold_value_not_the_move_window():
    weak_hold = _row(bucket="1_5d", contract_symbol="TEST261009C00105000", contract_strike=105.0,
                     contract_bid=3.8, contract_ask=4.2, contract_delta=0.40)
    strong_hold = _row(bucket="1_5d")
    selected, evaluations = select_contract([weak_hold, strong_hold], _cache(), now_utc=NOW)
    best = max(evaluations, key=lambda e: e["ev3_ev_lower_bound_return"])
    assert selected["ev3_contract_symbol"] == best["ev3_contract_symbol"]
