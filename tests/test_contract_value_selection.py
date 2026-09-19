"""The contract is chosen by what it is expected to earn, not by a fixed score (ACK, 18 Sep 2026).

Business rules (ACK):
- For each ticker the selector shortlists the best contract per expiry that passes the hard rules, values each
  on the same calibrated price paths over the planned hold, and prefers the highest central return per dollar
  of premium (emp_path_r_central: exit value / premium paid - 1).
- The executionist accepts or rejects; every shortlisted alternative is shown with its value and premium.
- The valuation is SHADOW_NO_AUTHORITY until proven (CLAUDE.md rule 5): in SHADOW mode the value choice is
  recorded beside the score choice; only ACTIVE mode (ACK's switch) makes it the selected contract.
- A contract that cannot be valued is flagged, never treated as zero: with no valued candidate the score choice
  stands and says so.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts import avshunter_options_intelligence as oi


def _contract(symbol: str, dte: float, *, spread: float = 0.08, delta: float = 0.50, strike: float = 100.0,
              mid: float = 2.0) -> dict:
    half = mid * spread / 2.0
    return {
        "symbol": symbol, "underlying": "TEST", "right": "C", "strike": strike,
        "expiration_date": f"exp{int(dte)}", "dte": dte, "mark": mid, "bid": mid - half, "ask": mid + half,
        "bid_size": 10, "ask_size": 10, "delta": delta, "gamma": 0.03, "theta": -0.03, "vega": 0.08,
        "implied_vol": 0.40, "open_interest": 100, "volume": 20, "spread_pct": spread,
        "quote_quality": "TWO_SIDED", "quality_flags": (), "quote_fields_complete": True, "mark_synthetic": False,
        "quote_timestamp_utc": "2026-09-17T20:00:00Z",
    }


def _ctx(valuer=None) -> dict:
    row = pd.Series({"ticker": "TEST", "direction": "CALL", "horizon_bucket": "1_5d", "current_price": 100.0,
                     "target_price": 110.0, "invalidation_spot": 95.0, "invalidation_state": "AVAILABLE"})
    structural = oi.parse_structural_context(row)
    ctx = {"ticker": "TEST", "direction": "CALL", "spot": 100.0, "horizon_bucket": "1_5d",
           "structural_target": 110.0, "invalidation_spot": 95.0, "hold_days": 5,
           "dte_window": oi.governed_dte_window("1_5d"), "dte_config": oi.governed_dte_config("1_5d"),
           "_signal_row": {"l3_forward_realised_vol_raw": 0.35},
           **{k: structural[k] for k in ("contract_runway_floor_days", "contract_min_holdable_dte",
                                         "contract_runway_basis", "contract_runway_hold_sessions")}}
    if valuer is not None:
        ctx["_contract_valuer"] = valuer
    return ctx


def _stub(values: dict):
    """Valuer returning a fixed central/cautious return per symbol."""
    def valuer(candidate):
        central, cautious = values[candidate["symbol"]]
        return {"emp_path_quality_flag": "OK", "emp_path_r_central": central, "emp_path_r_cautious": cautious}
    return valuer


_CHAIN = [_contract("S29A", 29.0), _contract("S29B", 29.0, delta=0.30, strike=105.0),
          _contract("S64A", 64.0, mid=3.0), _contract("S92A", 92.0, mid=3.6)]


def _select(ctx, mode, monkeypatch):
    monkeypatch.setitem(oi.CONTRACT_SELECTION, "value_selection_mode", mode)
    return oi.select_best_contract(pd.DataFrame(_CHAIN), ctx)


def _score_choice(monkeypatch):
    return _select(_ctx(_stub({s["symbol"]: (0.0, 0.0) for s in _CHAIN})), "SHADOW", monkeypatch)["symbol"]


def _value_best_other_than(score_symbol):
    """A valuation in which the best contract is NOT the score choice."""
    other = "S92A" if score_symbol != "S92A" else "S29A"
    values = {s["symbol"]: (-0.10, -0.30) for s in _CHAIN}
    values[other] = (0.12, -0.05)
    return other, values


def test_the_shortlist_is_the_best_contract_per_expiry(monkeypatch):
    selected = _select(_ctx(_stub({s["symbol"]: (0.0, 0.0) for s in _CHAIN})), "SHADOW", monkeypatch)
    alternatives = json.loads(selected["contract_value_alternatives"])
    assert sorted(a["dte"] for a in alternatives) == [29.0, 64.0, 92.0]      # one per expiry
    assert {"symbol", "expiry", "dte", "ask", "r_central", "r_cautious", "contract_score"} <= set(alternatives[0])


def test_active_mode_selects_the_highest_central_return_per_dollar(monkeypatch):
    other, values = _value_best_other_than(_score_choice(monkeypatch))
    selected = _select(_ctx(_stub(values)), "ACTIVE", monkeypatch)
    assert selected["symbol"] == other
    assert selected["contract_value_basis"] == "VALUE_PER_PREMIUM_CENTRAL"
    assert selected["contract_value_r_central"] == 0.12 and selected["contract_value_r_cautious"] == -0.05


def test_shadow_mode_records_the_value_choice_but_keeps_the_score_choice(monkeypatch):
    score_symbol = _score_choice(monkeypatch)
    other, values = _value_best_other_than(score_symbol)
    selected = _select(_ctx(_stub(values)), "SHADOW", monkeypatch)
    assert selected["symbol"] == score_symbol
    assert selected["contract_value_basis"] == "SCORE_VALUE_SHADOW"
    assert selected["contract_value_best_symbol"] == other
    assert selected["contract_value_best_r_central"] == 0.12
    assert selected["contract_value_score_choice_symbol"] == score_symbol


def test_with_no_valued_candidate_the_score_choice_stands_and_says_so(monkeypatch):
    def unavailable(candidate):
        return {"emp_path_quality_flag": "VOL_SCALE_UNAVAILABLE", "emp_path_r_central": None,
                "emp_path_r_cautious": None}
    selected = _select(_ctx(unavailable), "ACTIVE", monkeypatch)
    assert selected["symbol"] == _score_choice(monkeypatch)
    assert selected["contract_value_basis"] == "SCORE_FALLBACK_VALUE_UNAVAILABLE"
    assert selected["contract_value_r_central"] is None
    assert selected["contract_value_quality_flag"] == "VOL_SCALE_UNAVAILABLE"


def test_the_real_valuation_prices_every_shortlisted_contract(monkeypatch):
    selected = _select(_ctx(), "SHADOW", monkeypatch)
    alternatives = json.loads(selected["contract_value_alternatives"])
    assert all(a["quality_flag"] == "OK" and a["r_central"] is not None for a in alternatives)
    assert selected["contract_value_quality_flag"] == "OK"


def test_missing_valuation_inputs_are_flagged_not_defaulted(monkeypatch):
    ctx = _ctx()
    ctx["_signal_row"] = {}                                     # no volatility forecast
    selected = _select(ctx, "ACTIVE", monkeypatch)
    assert selected["contract_value_basis"] == "SCORE_FALLBACK_VALUE_UNAVAILABLE"
    assert selected["contract_value_quality_flag"] == "VALUE_INPUTS_UNAVAILABLE"


def test_the_mode_is_governed_and_starts_in_shadow():
    assert oi._load_contract_selection_policy()["value_selection_mode"] == "SHADOW"


def test_the_output_row_and_the_lab_book_carry_the_value_facts():
    import inspect
    from contracts.lab_control import FINAL_BOOK_FIELDS
    source = inspect.getsource(oi)
    for field in oi.CONTRACT_VALUE_FIELDS:
        assert field in FINAL_BOOK_FIELDS, field
        assert source.count(f"'{field}'") + source.count(f'"{field}"') >= 1, field


# --- The value choice must cover the planned hold (ACK 19 Sep 2026) ------------------------------------------------
# 18 Sep replay: on central value alone the choice moved 244 contracts SHORTER (to 11-29 days) for a tiny central
# gain and a worse downside. Only contracts that outlast the planned hold (runway floor, 40 days) may be the value
# choice; shorter ones stay visible as alternatives.

def test_a_short_contract_cannot_be_the_value_choice_even_if_it_values_best(monkeypatch):
    values = {s["symbol"]: (-0.10, -0.30) for s in _CHAIN}
    values["S29A"] = (0.30, -0.40)                     # best central, but 29 days < 40-day floor
    values["S92A"] = (0.05, -0.10)                     # best among contracts covering the hold
    selected = _select(_ctx(_stub(values)), "ACTIVE", monkeypatch)
    assert selected["symbol"] == "S92A"
    assert selected["contract_value_best_symbol"] == "S92A"
    covers = {a["symbol"]: a["covers_planned_hold"] for a in json.loads(selected["contract_value_alternatives"])}
    assert covers["S29A"] is False and covers["S92A"] is True


def test_when_no_valued_contract_covers_the_hold_the_score_choice_stands_and_says_so(monkeypatch):
    def only_short(candidate):
        if candidate["dte"] >= 40:
            return {"emp_path_quality_flag": "VOL_SCALE_UNAVAILABLE", "emp_path_r_central": None,
                    "emp_path_r_cautious": None}
        return {"emp_path_quality_flag": "OK", "emp_path_r_central": 0.2, "emp_path_r_cautious": -0.1}
    selected = _select(_ctx(only_short), "ACTIVE", monkeypatch)
    assert selected["symbol"] == _score_choice(monkeypatch)
    assert selected["contract_value_basis"] == "SCORE_NO_VALUED_CONTRACT_COVERS_HOLD"
    assert selected["contract_value_best_symbol"] is None
