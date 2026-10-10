"""Output-trust item 4 (D5-1; ACK approved 9 Oct 2026, decision 2): one valuation engine, labelled scenarios.

Root cause: four payoff producers with four definitions reached the Lab (SMCI 8 Oct: +207% = $2.07 per share expiry
intrinsic; 2.16x = European Black-Scholes with r = q = 0; -2.1% = expiry intrinsic vs ask; -38% = EV3 historical-state
EV).

Business rules:
- One engine: EV3's American CRR pricer for US stock/ETF options, Black-Scholes-Merton for European index options; the
  rate and dividend yield are inputs with their basis (dividend: tastytrade's yield, or ASSUMED_ZERO, stated).
- Proof: textbook benchmarks, an American call without dividends equals the European call, tree convergence, and
  agreement with an independent finite-difference American model.
- Scenarios, each with its exit time and IV assumption, as return on premium AFTER spread and fees: target reached
  (the reachable level by the median time), invalidation reached, trade stalls, and a lower-IV target case when
  earnings fall inside the hold. Units in every name.
- The pays state, the value multiple (rank, lane B) and the card all read the same engine: multiple = 1 + target return.
- Off the card and the Lab headline: EV3, monetisability, option_gain_at_target (USD per share) and the economics
  identity flag sit in the legacy tier; the Lab's soft warning comes from the engine's pays state.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from domain.anticipated_move import ANTICIPATED_MOVE_FIELDS, anticipated_move_fields
from domain.option_valuation import (VALUATION_FIELDS, european_bsm_value, exercise_style, option_value,
                                     valuation_policy)

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ the engine
def test_bsm_matches_textbook_benchmarks():
    # Hull, Options Futures and Other Derivatives, Example 15.6: S 42, K 40, r 10%, sigma 20%, T 0.5.
    assert european_bsm_value("CALL", 42, 40, 0.5, 0.2, rate=0.10, dividend_yield=0.0) == pytest.approx(4.76, abs=0.01)
    assert european_bsm_value("PUT", 42, 40, 0.5, 0.2, rate=0.10, dividend_yield=0.0) == pytest.approx(0.81, abs=0.01)
    # put-call parity with a continuous dividend yield
    c = european_bsm_value("CALL", 50, 48, 0.75, 0.3, rate=0.04, dividend_yield=0.02)
    p = european_bsm_value("PUT", 50, 48, 0.75, 0.3, rate=0.04, dividend_yield=0.02)
    assert c - p == pytest.approx(50 * math.exp(-0.02 * 0.75) - 48 * math.exp(-0.04 * 0.75), abs=1e-9)


def test_american_call_without_dividends_equals_european_and_the_put_carries_early_exercise():
    am = option_value("CALL", 100, 105, 0.4, 0.35, rate=0.0422, dividend_yield=0.0, style="AMERICAN")
    eu = european_bsm_value("CALL", 100, 105, 0.4, 0.35, rate=0.0422, dividend_yield=0.0)
    assert am["value"] == pytest.approx(eu, rel=0.005) and am["model"] == "AMERICAN_CRR"
    put_am = option_value("PUT", 100, 105, 0.4, 0.35, rate=0.0422, dividend_yield=0.0, style="AMERICAN")["value"]
    assert put_am > european_bsm_value("PUT", 100, 105, 0.4, 0.35, rate=0.0422, dividend_yield=0.0)


def test_the_tree_converges():
    steps = valuation_policy()["crr_steps"]
    from vanguard.ev_engine_v3 import american_option_price
    coarse = american_option_price(50, 50, 5 / 12, 0.10, 0.0, 0.40, "PUT", steps=steps)
    fine = american_option_price(50, 50, 5 / 12, 0.10, 0.0, 0.40, "PUT", steps=4000)
    assert abs(coarse - fine) / fine < 0.002


def _fd_american(side, s0, k, t, vol, r, q, n_s=400, s_max_mult=4.0):
    """Independent explicit finite-difference American option (early exercise by projection)."""
    s_max = s_max_mult * max(s0, k)
    ds = s_max / n_s
    grid = np.linspace(0.0, s_max, n_s + 1)
    payoff = np.maximum(grid - k, 0.0) if side == "CALL" else np.maximum(k - grid, 0.0)
    n_t = int(math.ceil(t * (vol * n_s) ** 2 * 1.05)) + 1
    dt = t / n_t
    i = np.arange(1, n_s)
    a = 0.5 * dt * (vol ** 2 * i ** 2 - (r - q) * i)
    b = 1 - dt * (vol ** 2 * i ** 2 + r)
    c = 0.5 * dt * (vol ** 2 * i ** 2 + (r - q) * i)
    v = payoff.copy()
    for step in range(n_t):
        tau = (step + 1) * dt
        new = v.copy()
        new[1:-1] = a * v[:-2] + b * v[1:-1] + c * v[2:]
        new[0] = 0.0 if side == "CALL" else k
        new[-1] = (s_max * math.exp(-q * tau) - k * math.exp(-r * tau)) if side == "CALL" else 0.0
        v = np.maximum(new, payoff)
    return float(np.interp(s0, grid, v))


@pytest.mark.parametrize("side,s0,k,t,vol,r,q", [
    ("PUT", 50, 50, 5 / 12, 0.40, 0.10, 0.0),
    ("PUT", 42.77, 45, 0.25, 0.85, 0.0422, 0.0),
    ("CALL", 100, 95, 0.5, 0.30, 0.0422, 0.03),
])
def test_agrees_with_an_independent_finite_difference_american_model(side, s0, k, t, vol, r, q):
    tree = option_value(side, s0, k, t, vol, rate=r, dividend_yield=q, style="AMERICAN")["value"]
    assert tree == pytest.approx(_fd_american(side, s0, k, t, vol, r, q), rel=0.01, abs=0.01)


def test_index_options_are_european_and_stock_options_american():
    assert exercise_style("SPX") == "EUROPEAN" and exercise_style("spxw") == "EUROPEAN"
    assert exercise_style("SMCI") == "AMERICAN" and exercise_style("SPY") == "AMERICAN"
    assert option_value("CALL", 100, 100, 0.2, 0.2, rate=0.04, dividend_yield=0.0, style="EUROPEAN")["model"] == "BSM_EUROPEAN"


# ------------------------------------------------------------------ the scenarios
AS_OF = date(2026, 10, 8)
CONTRACT = {"strike": 100.0, "ask": 6.0, "bid": 5.8,   # fair: model ATM 90d 30% IV is about 5.96
            "iv": 0.30, "expiry": (AS_OF + timedelta(days=90)).isoformat(),
            "as_of": AS_OF.isoformat(), "underlying": "TEST"}
DURATION = {"status": "VALIDATED", "q50_bars": 10, "q80_bars": 18, "n": 400, "test": "OUTCOME", "p_event": 0.6,
            "p_invalidation": 0.3}


def _fields(**kw):
    base = dict(direction="CALL", spot=100.0, outcome_level=108.0, outcome_definition="BEH001", timeframe="1d",
                duration=DURATION, vol_annual=0.30, contract=CONTRACT, governed_window_sessions=20,
                invalidation_level=95.0)
    base.update(kw)
    return anticipated_move_fields(**base)


def test_every_scenario_is_return_on_premium_after_spread_and_fees_from_one_engine():
    out = _fields()
    pol = valuation_policy()
    assert set(VALUATION_FIELDS) <= set(ANTICIPATED_MOVE_FIELDS)
    assert out["valuation_model"] == "AMERICAN_CRR"
    assert out["valuation_dividend_basis"].startswith("ASSUMED_ZERO") and out["valuation_dividend_yield_annual"] == 0.0
    assert out["scenario_exit_sessions"] == 10 and out["scenario_iv_basis"].startswith("IV_HELD")
    fee_open, fee_close = pol["fee_usd_per_contract_open"] / 100.0, pol["fee_usd_per_contract_close"] / 100.0
    cost = 6.0 + fee_open
    assert out["valuation_entry_cost_usd_per_share"] == pytest.approx(cost)
    years = (90 - 10 * 1.4484) / 365.0
    level = out["scenario_target_exit_spot"]
    model = option_value("CALL", level, 100.0, years, 0.30, rate=out["valuation_rate_annual"], dividend_yield=0.0,
                         style="AMERICAN")["value"]
    expected = max(model - 0.1 - fee_close, 0.0) / cost - 1.0        # exit at model less half the quoted spread
    assert out["scenario_target_return_on_premium"] == pytest.approx(expected, abs=1e-4)
    assert out["scenario_invalidation_exit_spot"] == 95.0
    assert out["scenario_invalidation_return_on_premium"] < -0.3 < out["scenario_stall_return_on_premium"] < 0
    assert out["scenario_target_return_on_premium"] > 0
    # one number: the value multiple and the pays state come from the target scenario
    assert out["anticipated_value_multiple_q50"] == pytest.approx(1 + out["scenario_target_return_on_premium"], abs=1e-4)
    assert out["anticipated_pays_state"] == ("PAYS" if out["scenario_target_return_on_premium"] >= 0
                                             else "DOES_NOT_PAY_AT_ANTICIPATED_TIME")


def test_a_dividend_yield_from_history_is_used_and_labelled():
    base, paid = _fields(), _fields(dividend_yield=0.04, dividend_basis="DIVIDEND_YIELD_TASTYTRADE:2026-10-09")
    assert paid["valuation_dividend_basis"] == "DIVIDEND_YIELD_TASTYTRADE:2026-10-09"
    assert paid["scenario_target_return_on_premium"] < base["scenario_target_return_on_premium"]   # call loses carry


def test_earnings_inside_the_hold_adds_a_lower_iv_target_case():
    out = _fields(earnings={"earnings_state": "SCHEDULED", "earnings_sessions_to_event": 5})
    assert out["scenario_target_earnings_iv_return_on_premium"] < out["scenario_target_return_on_premium"]
    assert _fields()["scenario_target_earnings_iv_return_on_premium"] is None


def test_a_worthless_exit_loses_the_premium_and_fee_never_more():
    from domain.option_valuation import return_on_premium
    assert return_on_premium(0.0, bid=0.05, ask=0.10) == -1.0
    assert _fields(invalidation_level=60.0)["scenario_invalidation_return_on_premium"] >= -1.0


def test_without_an_invalidation_level_the_scenario_says_so():
    out = _fields(invalidation_level=None)
    assert out["scenario_invalidation_return_on_premium"] is None
    assert out["scenario_target_return_on_premium"] is not None


# ------------------------------------------------------------------ dividends from tastytrade (ACK 10 Oct 2026)
# ACK: "use tastytrade for dividends instead of polygon". The Evening's tastytrade market-metrics call (made for the
# earnings tiers) carries dividend-yield, annual-dividend-per-share, dividend-rate-per-share and the next ex-date.
MSFT_DIV = {"dividend-rate-per-share": "0.98", "annual-dividend-per-share": "1.84", "dividend-yield": "0.007500813",
            "dividend-ex-date": "2026-11-19", "dividend-updated-at": "2026-10-09T12:03:29.260Z"}


def test_the_dividend_yield_comes_from_tastytrade_with_its_basis():
    from canonical_data.dividend_history import dividend_from_metrics
    y, basis = dividend_from_metrics(MSFT_DIV, spot=520.0, as_of=AS_OF)
    assert y == pytest.approx(0.007500813) and basis == "DIVIDEND_YIELD_TASTYTRADE:2026-10-09:next_ex 2026-11-19"
    ue = {"dividend-rate-per-share": "0.21", "annual-dividend-per-share": "0.88", "dividend-ex-date": "2026-09-15"}
    y, basis = dividend_from_metrics(ue, spot=22.0, as_of=AS_OF)                # no yield field: annual / spot
    assert y == pytest.approx(0.04) and basis.startswith("DIVIDEND_ANNUAL_PER_SHARE_TASTYTRADE")
    assert dividend_from_metrics({"dividend-rate-per-share": "0.0", "dividend-ex-date": "1970-01-01"}, spot=50,
                                 as_of=AS_OF) == (0.0, "DIVIDEND_NONE_TASTYTRADE")
    # a per-payment rate without a yield or annual figure is not annualised by guessing the frequency
    assert dividend_from_metrics({"dividend-rate-per-share": "0.125", "dividend-ex-date": "1970-01-01"}, spot=50,
                                 as_of=AS_OF) == (None, "ASSUMED_ZERO:TASTYTRADE_YIELD_NOT_PROVIDED")
    assert dividend_from_metrics({}, spot=50, as_of=AS_OF) == (None, "ASSUMED_ZERO:TASTYTRADE_NO_DIVIDEND_FIELDS")


def test_dividend_inputs_read_the_latest_metrics_cache(tmp_path):
    import json as _json
    from canonical_data.dividend_history import dividend_inputs
    (tmp_path / "2026-10-08.json").write_text(_json.dumps({"MSFT": {"status": "OK", "dividend": MSFT_DIV}}),
                                              encoding="utf-8")
    out = dividend_inputs("MSFT", as_of="2026-10-09", spot=520.0, cache_dir=tmp_path)    # the Morning: yesterday's cache
    assert out["dividend_yield"] == pytest.approx(0.007500813)
    assert out["dividend_basis"] == "DIVIDEND_YIELD_TASTYTRADE:2026-10-09:next_ex 2026-11-19 (metrics 2026-10-08)"
    assert dividend_inputs("AAPL", as_of="2026-10-09", spot=200.0, cache_dir=tmp_path) == {
        "dividend_yield": None, "dividend_basis": "ASSUMED_ZERO:NOT_FETCHED (metrics 2026-10-08)"}
    assert dividend_inputs("MSFT", as_of="2026-10-30", spot=520.0, cache_dir=tmp_path)["dividend_basis"] == \
        "ASSUMED_ZERO:NO_TASTYTRADE_METRICS_CACHE"                                    # older than 7 days is not used
    assert dividend_inputs("MSFT", as_of="2026-10-09", spot=520.0, cache_dir=tmp_path / "none")["dividend_basis"] == \
        "ASSUMED_ZERO:NO_TASTYTRADE_METRICS_CACHE"


def test_the_polygon_dividend_route_is_retired():
    assert not (ROOT / "scripts" / "fetch_dividend_history.py").exists()
    import canonical_data.dividend_history as dh
    assert not hasattr(dh, "record_dividends") and not hasattr(dh, "trailing_dividend_yield")


# ------------------------------------------------------------------ off the card and the Lab headline
def test_the_card_shows_the_scenarios_and_legacy_payoffs_are_inactive():
    card = (ROOT / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "SMCI", "direction": "CALL", **_fields()}
    out = subprocess.run(["node"], input=card + f"\nconst h = renderTradeCard({json.dumps(row)});\n"
                         "console.log(JSON.stringify({t: /target [+-]\\d+% at/.test(h), i: /invalidation [+-]\\d+% at/.test(h),"
                         " s: /stall [+-]\\d+%/.test(h), net: h.includes('after spread and fees'),"
                         " model: h.includes('American') && h.includes('dividend assumed 0')}));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"t": True, "i": True, "s": True, "net": True,
                                                               "model": True}
    legacy = re.search(r"const TC_LEGACY = (/.*?/i);", card).group(1)
    probe = subprocess.run(["node"], input=f"const re = {legacy};\nconsole.log(JSON.stringify(['ev3_ev_conservative_return',"
                           "'monetisability_target_profit_pct','option_gain_at_target','economics_comparable',"
                           "'ev_predicted'].map(f => re.test(f))));", capture_output=True, text=True, encoding="utf-8",
                           timeout=60)
    assert json.loads(probe.stdout.strip().splitlines()[-1]) == [True] * 5


def test_the_lab_headline_value_is_the_engine_target_scenario_not_ev3():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    fn = re.search(r"function getTargetScenarioInfo\(s\) \{.*?\n\}", html, re.S).group(0)
    probe = fn + """
console.log(JSON.stringify([getTargetScenarioInfo({scenario_target_return_on_premium: '0.42', ev3_ev_conservative_return: '-0.38'}),
                            getTargetScenarioInfo({ev3_ev_conservative_return: '-0.38'})]));
"""
    out = subprocess.run(["node"], input=probe, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    first, second = json.loads(out.stdout.strip().splitlines()[-1])
    assert first == {"value": 0.42, "source": "TARGET_SCENARIO"}
    assert second["source"] == "" and second["value"] is None          # NaN serialises as null: no EV3 fallback
    # every display site reads the engine; EV3 stays only in the audit export columns (the Interpreter reconciles them)
    display = [line for line in html.splitlines() if "getEv(s)" in line and "['EV'" not in line
               and not line.startswith("function ")]
    assert display == [], display
    assert "Positive EV* (EV3 advisory)" not in html


def test_the_lab_soft_warning_comes_from_the_engine_not_monetisability():
    from contracts.lab_control import _resolve_execution_gate_authority
    pays = _resolve_execution_gate_authority({"final_action": "BUY_NOW", "monetisability_state": "NOT_MONETISABLE",
                                              "anticipated_pays_state": "PAYS"}, {})
    assert not any(f.startswith("MONETISABILITY") for f in pays["advisory_flags"])
    short = _resolve_execution_gate_authority({"final_action": "BUY_NOW", "anticipated_pays_state":
                                               "DOES_NOT_PAY_AT_ANTICIPATED_TIME"}, {})
    assert "VALUATION:DOES_NOT_PAY_AT_ANTICIPATED_TIME" in short["advisory_flags"]
