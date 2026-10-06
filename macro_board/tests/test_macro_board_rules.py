"""Business rules for the standalone ETF macro board (written before the engine).

Each test states one rule in domain language. No live data or network is touched.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from macro_board import conditions as cond
from macro_board import evidence as ev
from macro_board import scorecard as sc

SESSIONS = pd.bdate_range("2026-01-05", periods=30)

EVIDENCE_SETTINGS = {
    "min_effective_n": 8,
    "min_effective_n_holdout": 3,
    "lean_t_min": 1.5,
    "lean_min_abs_mean_pct": {"1": 0.05, "5": 0.25, "20": 0.75},
}


# --- point in time ------------------------------------------------------------------

def test_a_fred_print_is_not_visible_on_its_own_observation_session():
    series = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-05", "2026-01-06"]))
    aligned = cond.align_point_in_time(series, SESSIONS[:3], lag_days=1, max_age_days=6)
    assert np.isnan(aligned.loc["2026-01-05"])          # nothing published yet
    assert aligned.loc["2026-01-06"] == 1.0              # Monday's print, published Tuesday
    assert aligned.loc["2026-01-07"] == 2.0


def test_a_stale_series_becomes_missing_not_its_last_value():
    series = pd.Series([1.0], index=pd.to_datetime(["2026-01-05"]))
    aligned = cond.align_point_in_time(series, SESSIONS[:15], lag_days=1, max_age_days=6)
    assert aligned.loc["2026-01-09"] == 1.0              # observation 4 days old
    assert np.isnan(aligned.loc["2026-01-12"])           # 7 days old > 6 -> missing, never carried forward


# --- missing is never neutral -------------------------------------------------------

def test_a_missing_input_gives_a_missing_state_not_a_flat_one():
    change = pd.Series([np.nan] * 5 + list(np.linspace(-1, 1, 25)), index=SESSIONS)
    states = cond.trend_state(change, window=10, min_periods=5, band_z=0.5,
                              up="RISING", flat="STABLE", down="FALLING")
    assert (states.iloc[:5] == cond.MISSING).all()
    assert "STABLE" not in set(states.iloc[:5])


def test_a_missing_historical_state_never_counts_as_an_analog_match():
    states = pd.DataFrame({"credit": ["TIGHTENING", cond.MISSING, "TIGHTENING"],
                           "curve": ["STEEP", "STEEP", "INVERTED"]}, index=SESSIONS[:3])
    mask, similarity = cond.analog_mask(states, {"credit": "TIGHTENING", "curve": "STEEP"},
                                        min_match_fraction=1.0)
    assert list(mask) == [True, False, False]
    assert similarity.iloc[1] == 0.5


def test_a_condition_missing_today_is_left_out_of_the_match_not_matched_as_missing():
    states = pd.DataFrame({"credit": [cond.MISSING, "WIDENING"], "curve": ["STEEP", "STEEP"]},
                          index=SESSIONS[:2])
    mask, _ = cond.analog_mask(states, {"credit": cond.MISSING, "curve": "STEEP"}, min_match_fraction=1.0)
    assert list(mask) == [True, True]


# --- forward returns are what a human could have traded ------------------------------

def test_forward_return_starts_at_the_next_session_open_not_the_signal_close():
    opens = pd.DataFrame({"SPY": [100.0, 110.0, 120.0]}, index=SESSIONS[:3])
    closes = pd.DataFrame({"SPY": [105.0, 115.0, 132.0]}, index=SESSIONS[:3])
    one = ev.forward_returns(opens, closes, 1)
    two = ev.forward_returns(opens, closes, 2)
    assert one["SPY"].iloc[0] == pytest.approx(115.0 / 110.0 - 1)   # open d+1 -> close d+1
    assert two["SPY"].iloc[0] == pytest.approx(132.0 / 110.0 - 1)   # open d+1 -> close d+2
    assert np.isnan(two["SPY"].iloc[1])                              # window not complete yet


# --- overlapping windows are not independent evidence --------------------------------

def test_twenty_consecutive_signal_days_at_a_twenty_session_horizon_are_one_observation():
    assert ev.effective_n(np.arange(20), 20) == 1
    assert ev.effective_n(np.array([0, 20, 40]), 20) == 3
    assert ev.effective_n(np.arange(10), 1) == 10


# --- the lean is evidence, not opinion ----------------------------------------------

def _stats(mean, t, n_eff):
    return {"n": n_eff * 5, "n_eff": n_eff, "mean_pct": mean, "t": t}


def test_too_few_independent_windows_is_reported_as_insufficient_not_as_a_lean():
    assert ev.decide_lean(_stats(3.0, 4.0, 5), 20, EVIDENCE_SETTINGS) == "INSUFFICIENT_SAMPLE"


def test_a_weak_or_small_effect_is_no_clear_lean():
    assert ev.decide_lean(_stats(3.0, 1.0, 30), 20, EVIDENCE_SETTINGS) == "NO_CLEAR_LEAN"
    assert ev.decide_lean(_stats(0.4, 3.0, 30), 20, EVIDENCE_SETTINGS) == "NO_CLEAR_LEAN"


def test_a_strong_measured_effect_gives_a_direction():
    assert ev.decide_lean(_stats(2.0, 2.5, 30), 20, EVIDENCE_SETTINGS) == "UP"
    assert ev.decide_lean(_stats(-2.0, -2.5, 30), 20, EVIDENCE_SETTINGS) == "DOWN"


def test_holdout_says_whether_the_lean_survived_unseen_history():
    agrees = ev.holdout_check("UP", {"n_eff": 4, "mean_pct": 1.0}, EVIDENCE_SETTINGS)
    disagrees = ev.holdout_check("UP", {"n_eff": 4, "mean_pct": -1.0}, EVIDENCE_SETTINGS)
    thin = ev.holdout_check("UP", {"n_eff": 1, "mean_pct": 1.0}, EVIDENCE_SETTINGS)
    assert (agrees, disagrees, thin) == ("HOLDOUT_AGREES", "HOLDOUT_DISAGREES", "HOLDOUT_THIN")
    assert ev.holdout_check("NO_CLEAR_LEAN", {"n_eff": 4, "mean_pct": 1.0}, EVIDENCE_SETTINGS) == "NOT_APPLICABLE"


# --- scoring the macro calls against reality ------------------------------------------

SCORE_SETTINGS = {"us_regular_open_utc": "13:30",
                  "packet_bullish_tokens": ["BULL", "RISK_ON"],
                  "packet_bearish_tokens": ["BEAR", "RISK_OFF"]}


def test_a_pre_open_packet_is_scored_from_that_sessions_open():
    sessions = pd.DatetimeIndex(pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07"]))
    pre_open = datetime(2026, 10, 6, 5, 17, tzinfo=timezone.utc)
    after_open = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
    assert sc.packet_entry_index(pre_open, sessions, "13:30") == 1
    assert sc.packet_entry_index(after_open, sessions, "13:30") == 2


def test_packet_direction_reads_bull_and_bear_language_and_nothing_else():
    assert sc.packet_direction("TRANSITIONAL_BULLISH", None, SCORE_SETTINGS) == 1
    assert sc.packet_direction("RISK_OFF", None, SCORE_SETTINGS) == -1
    assert sc.packet_direction("TRANSITIONAL", "NEUTRAL", SCORE_SETTINGS) == 0
    assert sc.packet_direction(None, None, SCORE_SETTINGS) == 0


# --- analog depth --------------------------------------------------------------------

def test_analog_depth_loosens_only_until_enough_independent_windows_and_never_past_the_floor():
    index = pd.bdate_range("2024-01-01", periods=60)
    # a matches today on every day; b matches only on even days -> exact match on half the days
    states = pd.DataFrame({"a": ["X"] * 60, "b": ["Y" if i % 2 == 0 else "Z" for i in range(60)]}, index=index)
    settings = {"analog_match_levels": [1.0, 0.5], "analog_target_effective_n": 5}
    level, mask, ladder = ev.choose_analog_depth(states, {"a": "X", "b": "Y"}, settings, max_horizon=5)
    assert level == 1.0 and ladder[0]["n_eff"] >= 5            # exact match already deep enough
    strict = {"analog_match_levels": [1.0, 0.5], "analog_target_effective_n": 50}
    level, mask, _ = ev.choose_analog_depth(states, {"a": "X", "b": "Y"}, strict, max_horizon=5)
    assert level == 0.5                                         # never looser than the floor, even if still thin


def test_projections_of_one_macro_that_point_opposite_ways_are_not_scored_as_a_call():
    conflicting = {"labels": ["TRANSITIONAL_BULLISH", "TRANSITIONAL_BEARISH"], "switches": [None, None]}
    partial = {"labels": ["TRANSITIONAL_BEARISH", "TRANSITIONAL"], "switches": [None, None]}
    assert sc.resolve_direction(conflicting, SCORE_SETTINGS) == (0, "CONFLICTING")
    assert sc.resolve_direction(partial, SCORE_SETTINGS) == (-1, "PARTIAL")


# === review fixes (thesis review 6 Oct 2026) =========================================

from macro_board import decision as dec
from macro_board import options as opt


def test_each_condition_reports_the_observation_date_it_actually_used_not_the_build_date():
    series = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-10-01", "2026-10-02"]))
    used = cond.observation_date_at(series, pd.Timestamp("2026-10-05"), lag_days=1, max_age_days=6)
    assert used == pd.Timestamp("2026-10-02")
    assert cond.observation_date_at(series, pd.Timestamp("2026-10-20"), lag_days=1, max_age_days=6) is None


def test_the_evidence_carries_an_interval_not_only_a_point_estimate():
    values = pd.Series(np.linspace(-0.02, 0.04, 40))
    stats = ev.summarise(values, np.arange(0, 400, 10), 5, level=0.8)
    assert stats["ci_low_pct"] < stats["mean_pct"] < stats["ci_high_pct"]


def test_path_dependent_products_get_no_multi_session_lean():
    index = pd.bdate_range("2020-01-01", periods=700)
    fwd = pd.Series(0.01, index=index)
    mask = pd.Series(True, index=index)
    settings = {**EVIDENCE_SETTINGS, "min_history_sessions": 500, "holdout_fraction": 0.25, "interval_level": 0.8}
    suppressed = ev.ticker_evidence(fwd, mask, 20, settings, suppress_lean=True)
    assert suppressed["lean"] == "PATH_DEPENDENT"
    assert suppressed["analog"]["n"] > 0                      # evidence still shown, only the lean withheld


def test_a_price_only_baseline_lean_is_recorded_beside_the_macro_lean():
    index = pd.bdate_range("2020-01-01", periods=700)
    rng = np.random.default_rng(1)
    fwd = pd.Series(0.004 + rng.normal(0, 0.01, 700), index=index)
    settings = {**EVIDENCE_SETTINGS, "min_history_sessions": 500, "holdout_fraction": 0.25, "interval_level": 0.8}
    out = ev.ticker_evidence(fwd, pd.Series(True, index=index), 1, settings)
    assert out["baseline_lean"] in ("UP", "DOWN", "NO_CLEAR_LEAN", "INSUFFICIENT_SAMPLE")


def test_a_move_already_made_is_measured_in_the_etfs_own_volatility():
    # 20% annual vol -> 20-session sd ~ 5.6%; a 10% run is ~1.8 sd -> extended
    assert dec.extension_state(10.0, 20.0, 20, 1.5)["state"] == "EXTENDED_UP"
    assert dec.extension_state(-10.0, 20.0, 20, 1.5)["state"] == "EXTENDED_DOWN"
    assert dec.extension_state(2.0, 20.0, 20, 1.5)["state"] == "NOT_EXTENDED"
    assert dec.extension_state(None, 20.0, 20, 1.5)["state"] == "UNKNOWN"


def _sens(**pairs):
    return {k: {"state": "X", "excess_pct": v[0], "t": v[1]} for k, v in pairs.items()}


def test_measured_headwinds_with_a_rising_etf_read_as_absorbing_pressure():
    out = dec.classify_response(_sens(yields=(-1.2, -1.8), credit=(0.1, 0.2)), own_return_pct=3.0, t_min=1.0)
    assert out["label"] == "ABSORBING_PRESSURE" and out["headwinds"] == ["yields"]


def test_measured_tailwinds_with_a_falling_etf_read_as_rejecting_relief():
    assert dec.classify_response(_sens(yields=(1.2, 1.8)), own_return_pct=-2.0, t_min=1.0)["label"] == "REJECTING_RELIEF"


def test_agreement_is_supporting_balanced_pressure_is_mixed_and_nothing_measured_is_insufficient():
    assert dec.classify_response(_sens(a=(1.0, 2.0)), 1.0, 1.0)["label"] == "SUPPORTING_RESPONSE"
    assert dec.classify_response(_sens(a=(1.0, 2.0), b=(-1.0, -2.0)), 1.0, 1.0)["label"] == "MIXED"
    assert dec.classify_response(_sens(a=(1.0, 0.3)), 1.0, 1.0)["label"] == "INSUFFICIENT"
    assert dec.classify_response(_sens(a=(1.0, 2.0)), None, 1.0)["label"] == "INSUFFICIENT"


def _chain():
    rows = []
    for dte, call_mid, put_mid in ((3, 4.0, 4.0), (8, 9.0, 8.0), (30, 20.0, 19.0)):
        for strike in (95.0, 100.0, 105.0):
            off = abs(strike - 100.0) / 5.0
            rows.append({"side": "call", "strike": strike, "dte": dte, "bid": call_mid - 0.1 - off, "ask": call_mid + 0.1 - off,
                         "mid": call_mid - off, "underlying_price": 100.4})
            rows.append({"side": "put", "strike": strike, "dte": dte, "bid": put_mid - 0.1 - off, "ask": put_mid + 0.1 - off,
                         "mid": put_mid - off, "underlying_price": 100.4})
    return pd.DataFrame(rows)


def test_implied_move_uses_the_first_expiry_covering_the_horizon_and_the_atm_strike():
    out = opt.atm_straddle(_chain(), target_dte_calendar=7)
    assert out["dte"] == 8 and out["strike"] == 100.0             # runway: never an expiry shorter than the horizon
    assert out["straddle_mid"] == pytest.approx(17.0)
    assert out["implied_move_pct"] == pytest.approx(17.0 / 100.4 * 100, abs=1e-3)
    assert out["straddle_ask"] == pytest.approx(17.2)


def test_no_expiry_long_enough_means_no_implied_move_rather_than_a_shorter_one():
    assert opt.atm_straddle(_chain(), target_dte_calendar=60) is None


def test_money_index_scores_are_grouped_by_the_packets_own_ladder():
    ladder = {"0-40": "STRESS_UNCONFIRMED", "41-65": "ELEVATED", "66-85": "CONFIRMED", "86-100": "SYSTEMIC"}
    assert sc.ladder_band(75, ladder) == "CONFIRMED"
    assert sc.ladder_band(40, ladder) == "STRESS_UNCONFIRMED"
    assert sc.ladder_band(None, ladder) is None


def test_remaining_opportunity_is_measured_from_the_current_price_not_the_proposal_price():
    out = dec.remaining_opportunity(close=707.0, entry=700.0, target=708.0, invalidation=699.0, direction="CALL")
    assert out["to_target_pct"] == pytest.approx(1 / 707 * 100, abs=1e-3)
    assert out["to_invalidation_pct"] == pytest.approx(8 / 707 * 100, abs=1e-3)
    assert out["target_consumed"] == pytest.approx(7 / 8, abs=1e-3)
    put = dec.remaining_opportunity(close=695.0, entry=700.0, target=690.0, invalidation=702.0, direction="PUT")
    assert put["to_target_pct"] == pytest.approx(5 / 695 * 100, abs=1e-3) and put["target_consumed"] == pytest.approx(0.5)
    assert dec.remaining_opportunity(close=700.0, entry=None, target=None, invalidation=None, direction="UNRESOLVED") is None


# === holdings (issuer daily files) and tastytrade metrics ==============================

from macro_board import holdings as hold
from macro_board import tastytrade_metrics as ttm


def test_issuer_rows_keep_securities_and_drop_cash_and_blank_tickers():
    rows = [["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"],
            ["NVIDIA CORP", "NVDA", "x", "x", "8.5", "-", "2.9E8", "USD"],
            ["US DOLLAR", "-", "x", "x", "0.1", "-", "1", "USD"],
            ["BERKSHIRE HATHAWAY INC CL B", "BRK.B", "x", "x", "1.6", "-", "1E7", "USD"],
            [None, None, None, None, None, None, None, None]]
    parsed = hold.parse_ssga_rows(rows)
    assert [h["ticker"] for h in parsed] == ["NVDA", "BRK.B"]
    assert parsed[0]["weight_pct"] == 8.5
    invesco = {"holdings": [{"ticker": "NVDA", "issuerName": "NVIDIA", "percentageOfTotalNetAssets": 8.4,
                             "units": 1, "securityTypeName": "Common Stock"},
                            {"ticker": None, "issuerName": "Cash", "percentageOfTotalNetAssets": 0.2,
                             "units": 1, "securityTypeName": "Cash"}]}
    assert [h["ticker"] for h in hold.parse_invesco_json(invesco)] == ["NVDA"]


def test_contribution_uses_start_of_window_weights_and_reports_unpriced_weight_not_as_zero():
    index = pd.bdate_range("2026-09-01", periods=30)
    closes = pd.DataFrame({"AAA": np.linspace(100, 110, 30), "BBB": np.linspace(100, 95, 30)}, index=index)
    holdings = [{"ticker": "AAA", "weight_pct": 10.0}, {"ticker": "BBB", "weight_pct": 5.0},
                {"ticker": "ZZZ", "weight_pct": 2.0}]
    out = hold.contribution(holdings, closes, window=20, trend_sessions=20, holdings_as_of=index[-1])
    r_a = closes["AAA"].iloc[-1] / closes["AAA"].iloc[-21] - 1
    r_b = closes["BBB"].iloc[-1] / closes["BBB"].iloc[-21] - 1
    w0_a, w0_b = 10.0 / (1 + r_a), 5.0 / (1 + r_b)              # issuer weights are end-of-window: drift them back
    share_a = w0_a / (w0_a + w0_b) * 15.0                          # keep the priced share of the fund (15%)
    aaa = next(r for r in out["rows"] if r["ticker"] == "AAA")
    assert aaa["contribution_pp"] == pytest.approx(share_a / 100 * r_a * 100, abs=1e-3)
    assert aaa["contribution_pp"] < 0.10 * r_a * 100              # a winner is not over-weighted at the start
    assert out["unpriced_weight_pct"] == pytest.approx(2.0)
    assert out["priced_weight_pct"] == pytest.approx(15.0)
    assert out["participation_weight_pct"] == pytest.approx(10.0 / 15.0 * 100, abs=1e-3)  # only AAA above its mean


def test_a_holding_whose_last_price_is_older_than_the_session_counts_as_unpriced():
    index = pd.bdate_range("2026-09-01", periods=30)
    closes = pd.DataFrame({"AAA": np.linspace(100, 110, 30), "OLD": [100.0] * 25 + [np.nan] * 5}, index=index)
    out = hold.contribution([{"ticker": "AAA", "weight_pct": 5.0}, {"ticker": "OLD", "weight_pct": 1.0}],
                            closes, window=5, trend_sessions=20, holdings_as_of=index[-1])
    assert [r["ticker"] for r in out["rows"]] == ["AAA"] and out["unpriced_weight_pct"] == pytest.approx(1.0)


def test_tastytrade_units_are_normalised_to_percent_exactly_once():
    raw = {"symbol": "QQQ", "implied-volatility-index": "0.2149", "implied-volatility-index-rank": "0.4419",
           "implied-volatility-percentile": "0.2710", "historical-volatility-30-day": "14.82",
           "iv-hv-30-day-difference": "6.67", "beta": "1.23", "corr-spy-3month": "0.73",
           "option-expiration-implied-volatilities": [{"expiration-date": "2026-10-16", "implied-volatility": "0.191"}],
           "implied-volatility-updated-at": "2026-10-05T19:56:32Z"}
    m = ttm.normalise(raw)
    assert m["iv_index_pct"] == pytest.approx(21.49)          # 0-1 decimal -> percent
    assert m["iv_rank_pct"] == pytest.approx(44.19)
    assert m["hv30_pct"] == pytest.approx(14.82)              # already a percent: unchanged
    assert m["term"][0] == {"expiry": "2026-10-16", "iv_pct": pytest.approx(19.1)}
    assert ttm.normalise({"symbol": "X"})["iv_index_pct"] is None   # missing stays missing


def test_one_rejected_symbol_does_not_lose_its_whole_batch(tmp_path):
    from bridge.tastytrade_readonly_mcp import BrokerMcpError

    class FakeBroker:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def market_metrics(self, symbols):
            if "BAD" in symbols:
                raise BrokerMcpError("broker read tool returned an error")
            return {"items": [{"symbol": s} for s in symbols]}

    report = ttm.fetch(["SPY", "BAD", "QQQ"], tmp_path, batch=3, broker_factory=FakeBroker)
    assert report["status"] == "OK" and report["count"] == 2 and report["skipped"] == ["BAD"]


def test_missing_broker_credentials_fail_fast_without_retrying_each_symbol(tmp_path):
    from bridge.tastytrade_readonly_mcp import BrokerCredentialUnavailable
    calls = []

    class NoCredentials:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def market_metrics(self, symbols):
            calls.append(list(symbols))
            raise BrokerCredentialUnavailable("missing broker OAuth environment")

    report = ttm.fetch(["SPY", "QQQ"], tmp_path, batch=2, broker_factory=NoCredentials)
    assert report["status"] == "FAILED" and len(calls) == 1


def test_adjusted_option_chains_are_left_out_of_the_term_structure():
    raw = {"symbol": "SQQQ", "option-expiration-implied-volatilities": [
        {"expiration-date": "2026-10-16", "option-chain-type": "Standard", "implied-volatility": "0.55"},
        {"expiration-date": "2026-10-16", "option-chain-type": "1", "implied-volatility": "1.40"},
        {"expiration-date": "2026-11-20", "implied-volatility": "0.57"}]}
    term = ttm.normalise(raw)["term"]
    assert [t["iv_pct"] for t in term] == [pytest.approx(55.0), pytest.approx(57.0)]
