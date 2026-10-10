"""No runway estimate is labelled, never scored as 'covered' or as a reason to buy less runway; the hold the
evening sized the contract with is the hold the morning checks (ACK 7 Oct 2026, quant decisions on the L3 /
runway C-then-B follow-ups).

Business rules:
- Missing is never neutral (R1) and labels say what was measured (R6): with no runway estimate there is no hold
  to cover, so a contract is never reported RUNWAY_COVERED / covers_planned_hold=True.
- Buy more runway than the anticipated move; never drop or penalise longer-dated contracts (ACK 18 Sep). With no
  estimate the only floor is the holdable-past-issue floor, and extra runway beyond it costs nothing in the score.
- With no estimate the value-per-premium switch stands down (there is no hold to value against) and says so.
- One owner for the planned hold: the evening row's planned hold and its source are the contract runway hold and
  basis (own evidence, pooled evidence or calibrated volatility time). The morning accepts any of those measured
  bases and nothing else (no retired horizon-bucket 5/10/20 hold).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import morning_gate
from scripts import avshunter_options_intelligence as oi

NO_ESTIMATE = oi.contract_runway_policy(None)


def _contract(symbol: str, dte: float, *, delta: float = 0.50, mid: float = 2.0) -> dict:
    half = mid * 0.08 / 2.0
    return {
        "symbol": symbol, "underlying": "TEST", "right": "C", "strike": 100.0,
        "expiration_date": f"exp{int(dte)}", "dte": dte, "mark": mid, "bid": mid - half, "ask": mid + half,
        "bid_size": 10, "ask_size": 10, "delta": delta, "gamma": 0.03, "theta": -0.03, "vega": 0.08,
        "implied_vol": 0.40, "open_interest": 100, "volume": 20, "spread_pct": 0.08,
        "quote_quality": "TWO_SIDED", "quality_flags": (), "quote_fields_complete": True, "mark_synthetic": False,
        "quote_timestamp_utc": "2026-09-17T20:00:00Z",
    }


def _ctx(runway: dict, valuer=None) -> dict:
    ctx = {"ticker": "TEST", "direction": "CALL", "spot": 100.0, "horizon_bucket": None,
           "structural_target": 110.0, "invalidation_spot": 95.0, "hold_days": 5,
           "dte_window": oi.governed_dte_window(None), "dte_config": oi.governed_dte_config(None),
           "_signal_row": {"l3_forward_realised_vol_raw": 0.35}, **runway}
    if valuer is not None:
        ctx["_contract_valuer"] = valuer
    return ctx


def test_no_estimate_does_not_score_a_longer_contract_below_a_shorter_holdable_one():
    # Identical contracts except expiry and a slightly worse delta on the short one: with no hold estimate
    # extra runway is free, so the on-target 64-day contract wins instead of the nearest holdable expiry.
    low, high = oi.CONTRACT_SELECTION["delta_preferred_abs"]
    target = (low + high) / 2.0
    chain = [_contract("S29", 29.0, delta=target + 0.03), _contract("S64", 64.0, delta=target)]
    chosen = oi.select_best_contract(pd.DataFrame(chain), _ctx(NO_ESTIMATE))
    assert chosen["symbol"] == "S64"


def test_no_estimate_is_labelled_not_reported_as_covered():
    chosen = oi.select_best_contract(pd.DataFrame([_contract("S64", 64.0)]), _ctx(NO_ESTIMATE))
    assert chosen["contract_runway_basis"] == "NO_RUNWAY_ESTIMATE"
    assert chosen["contract_runway_state"] == "NO_RUNWAY_ESTIMATE"


def test_with_an_estimate_coverage_is_still_measured():
    runway = oi.contract_runway_policy(None, evidence_hold=20, evidence_basis="DURATION_EVIDENCE_Q80:1d:n=50")
    chosen = oi.select_best_contract(pd.DataFrame([_contract("S29", 29.0)]), _ctx(runway))
    assert chosen["contract_runway_state"] == "RUNWAY_SHORT"          # 29 days < floor for a 20-session hold


def test_no_estimate_stands_the_value_switch_down_and_says_so(monkeypatch):
    monkeypatch.setitem(oi.CONTRACT_SELECTION, "value_selection_mode", "ACTIVE")
    values = {"S29": (0.30, -0.10), "S64": (0.05, -0.05)}

    def valuer(candidate):
        central, cautious = values[candidate["symbol"]]
        return {"emp_path_quality_flag": "OK", "emp_path_r_central": central, "emp_path_r_cautious": cautious}

    chain = pd.DataFrame([_contract("S29", 29.0), _contract("S64", 64.0)])
    score_choice = oi.select_best_contract(chain, _ctx(NO_ESTIMATE))["symbol"]
    selected = oi.select_best_contract(chain, _ctx(NO_ESTIMATE, valuer))
    assert selected["symbol"] == score_choice
    assert selected["contract_value_basis"] == "SCORE_NO_RUNWAY_ESTIMATE"
    covers = {a["symbol"]: a["covers_planned_hold"] for a in json.loads(selected["contract_value_alternatives"])}
    assert covers == {"S29": None, "S64": None}


def _lifecycle(runway: dict) -> dict:
    from test_ev3_options_handoff import _context
    ctx = _context(direction="CALL")
    ctx.update(runway)
    contract = {"symbol": "SERIES261218C00100000", "strike": 100.0, "dte": 72, "delta": 0.40,
                "bid": 1.90, "ask": 2.00, "quote_timestamp_utc": "2026-10-06T20:00:00Z", "mark_synthetic": False}
    return oi._options_liquidity_lifecycle_fields(ctx, contract, {"hv_30d": 0.28, "atm_iv": 0.30})


@pytest.mark.parametrize("basis", ["DURATION_EVIDENCE_Q80:1w:n=40",
                                   "POOLED_EVIDENCE_MAX_Q80:1w|SOS -> LPS continuation|BULL|OUTCOME",
                                   "VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80:k=1.5|vol=0.3000|move=0.0800"])
def test_the_evening_planned_hold_is_the_contract_runway_hold_and_names_its_basis(basis):
    lifecycle = _lifecycle(oi.contract_runway_policy(None, evidence_hold=14, evidence_basis=basis))
    assert lifecycle["planned_hold_sessions"] == 14
    assert lifecycle["planned_hold_source"] == basis


def test_with_no_estimate_the_evening_publishes_no_hold():
    lifecycle = _lifecycle(NO_ESTIMATE)
    assert lifecycle["planned_hold_sessions"] is None
    assert lifecycle["planned_hold_source"] == "NO_RUNWAY_ESTIMATE"


@pytest.mark.parametrize("source", ["DURATION_EVIDENCE_Q80:1w:n=40",
                                    "POOLED_EVIDENCE_MAX_Q80:1w|SOS -> LPS continuation|BULL|OUTCOME",
                                    "VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80:k=1.5|vol=0.3000|move=0.0800"])
def test_the_morning_checks_runway_against_the_hold_the_evening_chose(source):
    assert morning_gate._morning_hold_sessions({"planned_hold_source": source, "planned_hold_sessions": 14}) == 14


@pytest.mark.parametrize("source", ["HORIZON_BUCKET_ENDPOINT_V1", "UNROUTED", "NO_RUNWAY_ESTIMATE", ""])
def test_the_morning_never_borrows_a_retired_or_missing_hold(source):
    assert morning_gate._morning_hold_sessions({"planned_hold_source": source, "planned_hold_sessions": 20}) is None


def test_a_score_tie_goes_to_the_longer_expiry_whatever_the_chain_order():
    # Buy more runway than the anticipated move (ACK 18 Sep): equal scores never hand the trade the shorter contract.
    for chain in ([_contract("S09", 9.0), _contract("S16", 16.0)], [_contract("S16", 16.0), _contract("S09", 9.0)]):
        assert oi.select_best_contract(pd.DataFrame(chain), _ctx(NO_ESTIMATE))["symbol"] == "S16"
