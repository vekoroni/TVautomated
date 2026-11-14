"""Crossing scenario (AVS-TRADE-001 design v4, sections 5 and 6; ACK 14 Nov 2026).

Business rules, in domain language:
- The scenario answers what a NEW entry at this quote would need; it is display only and never a number when an
  input is missing.
- The stock travels from the quote spot to the frozen target on a square-root-of-time path and stops there.
- It is sampled at session closes; the first is the first close strictly after the assessment.
- The slower pace never crosses earlier than the median pace; +30% never earlier than +20%.
- A crossing covers only when it leaves the monitoring and exit sessions before expiry.
- When no crossing is found the state names the boundary that actually ended the search.
- Morning counts down from the frozen thesis origin and never restarts the runway.
"""
from datetime import date, datetime, timezone
import json
import math

import pytest

from domain import crossing_scenario as cs
from domain import option_valuation as ov

CFG = cs.crossing_config()
FEE_OPEN = float(ov.valuation_policy()["fee_usd_per_contract_open"]) / 100.0
FEE_CLOSE = float(ov.valuation_policy()["fee_usd_per_contract_close"]) / 100.0
EVENING_CLOSE = "2026-11-11T21:00:00+00:00"          # Wednesday 11 Nov 2026, 16:00 ET


def base(**over):
    args = dict(side="CALL", mode="EVENING_AT_EVIDENCE", thesis_id="T:AAA:CALL:2026-11-11",
                contract_symbol="AAA270115C00100000", thesis_origin_date="2026-11-11", origin_spot=100.0,
                frozen_target_level=110.0, arrival_sessions_median=10, arrival_sessions_slow=20,
                assessment_instant_utc=EVENING_CLOSE, quote_timestamp_utc="2026-11-11T21:00:00Z", quote_spot=100.0,
                strike=100.0, expiry="2027-01-15", bid=4.90, ask=5.00, iv=0.30, thesis_active=True,
                rate=0.04, rate_basis="TEST", dividend_yield=0.0, dividend_basis="TEST")
    args.update(over)
    return args


def run(**over):
    out = cs.scenario_crossing(**base(**over))
    recs = {(r["pace"], r["threshold_pct"], r["variant"]): r for r in json.loads(out["crossing_records_json"])}
    return out, recs


def value_for(target_return, bid=4.90, ask=5.00, multiple=1.0):
    return (1.0 + target_return) * (ask + FEE_OPEN) + multiple * (ask - bid) / 2.0 + FEE_CLOSE


def fixed_values(monkeypatch, fn):
    """Replace the one pricing call with a controlled value per grid session (spot, years -> value)."""
    monkeypatch.setattr(cs, "_model_values", lambda side, spots, strike, years, vol, **kw: [
        fn(i + 1, s, t, vol) for i, (s, t) in enumerate(zip(spots, years))])


# ---------------------------------------------------------------- path and grid

def test_the_path_follows_the_formula_stops_at_the_target_and_never_passes_it(monkeypatch):
    seen = {}

    def capture(side, spots, strike, years, vol, **kw):
        seen.setdefault(len(spots), list(spots))
        return [0.0] * len(spots)
    monkeypatch.setattr(cs, "_model_values", capture)
    run(arrival_sessions_median=4, arrival_sessions_slow=9)
    median, slow = seen[4], seen[9]
    assert median == pytest.approx([100 + 10 * math.sqrt(j / 4) for j in (1, 2, 3, 4)])
    assert median[-1] == pytest.approx(110.0) and max(median) <= 110.0 + 1e-12
    assert slow[3] == pytest.approx(100 + 10 * math.sqrt(4 / 9)) and slow[-1] == pytest.approx(110.0)


def test_the_first_grid_session_is_the_first_close_strictly_after_the_assessment():
    evening, _ = run()
    assert evening["crossing_grid_first_date"] == "2026-11-12"                       # Evening: the next session
    morning, recs = run(mode="MORNING_FRESH_ENTRY", assessment_instant_utc="2026-11-12T14:40:00+00:00")
    assert morning["crossing_grid_first_date"] == "2026-11-12"                       # Morning: today's close
    assert morning["crossing_elapsed_sessions"] == 0                                 # today is not spent before the close
    # Both modes agree on the calendar date of arrival.
    assert recs[("MEDIAN", 30, "BASE")]["arrival_date"] == run()[1][("MEDIAN", 30, "BASE")]["arrival_date"]
    after_close, _ = run(mode="MORNING_FRESH_ENTRY", assessment_instant_utc="2026-11-12T21:30:00+00:00")
    assert after_close["crossing_grid_first_date"] == "2026-11-13" and after_close["crossing_elapsed_sessions"] == 1


def test_sessions_to_expiry_and_the_usable_deadline_are_counted_on_the_grid_across_a_holiday():
    out, _ = run(expiry="2026-12-04")
    # Grid from Thu 12 Nov: 12,13 | 16-20 | 23,24,25,(26 Thanksgiving),27 | 30,1,2,3,4 Dec = 16 sessions.
    assert out["crossing_sessions_to_expiry"] == 16
    assert out["crossing_usable_deadline_session"] == 16 - CFG["exit_buffer_sessions"]
    assert out["crossing_usable_deadline_date"] == "2026-11-27"                      # the 11th grid session (26 Nov is closed)
    weekend, _ = run(expiry="2026-11-22")                                            # a Sunday: last session is Fri 20
    assert weekend["crossing_expiry_session_date"] == "2026-11-20" and weekend["crossing_sessions_to_expiry"] == 7


# ---------------------------------------------------------------- crossing, thresholds, variants

def test_the_first_session_at_or_above_the_threshold_is_the_crossing_and_comparison_is_unrounded(monkeypatch):
    just_under, exact = value_for(0.29996), value_for(0.30) + 1e-9
    fixed_values(monkeypatch, lambda j, s, t, vol: {1: value_for(0.10), 2: just_under, 3: exact}.get(j, exact))
    out, recs = run()
    assert ov.return_on_premium(just_under, bid=4.90, ask=5.00) == 0.3              # would cross if rounded
    assert recs[("MEDIAN", 30, "BASE")]["crossing_session"] == 3                    # it does not
    assert recs[("MEDIAN", 20, "BASE")]["crossing_session"] == 2
    assert out["crossing_n_median_pace_30"] == 3 and out["crossing_n_median_pace_20"] == 2
    assert recs[("MEDIAN", 30, "BASE")]["crossing_date"] == "2026-11-16"


def test_slow_pace_never_crosses_earlier_than_median_and_thirty_never_earlier_than_twenty():
    out, recs = run()
    for variant in cs.VARIANTS:
        for t in (20, 30):
            m, s = recs[("MEDIAN", t, variant)]["crossing_session"], recs[("SLOW", t, variant)]["crossing_session"]
            if m is not None and s is not None:
                assert s >= m
        for pace in cs.PACES:
            a, b = recs[(pace, 20, variant)]["crossing_session"], recs[(pace, 30, variant)]["crossing_session"]
            if a is not None and b is not None:
                assert b >= a
    assert out["crossing_n_slow_pace_30"] is not None                                # the fixture does cross


def test_a_wider_exit_or_lower_iv_delays_or_removes_the_crossing_on_a_plain_call():
    _, recs = run()
    base_n = recs[("SLOW", 30, "BASE")]["crossing_session"]
    for variant in ("IV_DOWN", "WIDE_EXIT"):
        n = recs[("SLOW", 30, variant)]["crossing_session"]
        assert n is None or n >= base_n


def test_a_stress_result_is_reported_as_computed_even_when_it_is_earlier(monkeypatch):
    # An early-exercise-sensitive case can price higher at lower volatility; the scenario must not clamp it.
    fixed_values(monkeypatch, lambda j, s, t, vol: value_for(0.35) if (vol < 0.30 and j >= 2) or j >= 5 else 0.0)
    _, recs = run()
    assert recs[("MEDIAN", 30, "IV_DOWN")]["crossing_session"] == 2
    assert recs[("MEDIAN", 30, "BASE")]["crossing_session"] == 5


def test_wide_exit_reuses_the_base_values_and_deducts_only_more_spread(monkeypatch):
    calls = []

    def priced(side, spots, strike, years, vol, **kw):
        calls.append(vol)
        return [value_for(0.30, multiple=1.5)] * len(spots)     # crosses at the quoted spread, not at twice it
    monkeypatch.setattr(cs, "_model_values", priced)
    _, recs = run(arrival_sessions_median=5, arrival_sessions_slow=5)
    assert recs[("SLOW", 30, "BASE")]["state"].startswith("CROSSES")
    assert recs[("SLOW", 30, "WIDE_EXIT")]["state"] == "NO_CROSSING_BY_ARRIVAL"
    assert len(calls) == 4                                       # two paces x (base IV, IV down); none for wide exit


# ---------------------------------------------------------------- coverage and the boundary searched

def test_a_crossing_covers_only_when_monitoring_and_exit_sessions_remain(monkeypatch):
    fixed_values(monkeypatch, lambda j, s, t, vol: value_for(0.40) if j >= 9 else 0.0)
    out, recs = run(expiry="2026-12-04")                         # E = 16, U = 11; 9 + 3 > 11
    rec = recs[("SLOW", 30, "BASE")]
    assert (rec["state"], rec["covers"], rec["crossing_session"]) == ("CROSSES_NOT_COVERING", False, 9)
    assert out["crossing_covers_slow30_base"] == "NO"
    fixed_values(monkeypatch, lambda j, s, t, vol: value_for(0.40) if j >= 8 else 0.0)
    out, recs = run(expiry="2026-12-04")                         # 8 + 3 = 11 <= 11
    assert recs[("SLOW", 30, "BASE")]["state"] == "CROSSES_COVERING" and out["crossing_covers_slow30_base"] == "YES"
    assert out["crossing_monitor_deadline_session"] == 11 and out["crossing_monitor_deadline_date"] == "2026-11-27"


def never(monkeypatch):
    fixed_values(monkeypatch, lambda j, s, t, vol: 0.0)


def cfg(**over):
    return {**CFG, **over}


@pytest.mark.parametrize("arrival,expiry,cap,state,limit,end,coverage", [
    # R=20, U=5 (E=10), cap=30: the contract's usable life ends first; arrival was NOT searched.
    (20, "2026-11-25", 30, "NO_CROSSING_BY_USABLE_DEADLINE", "USABLE_DEADLINE", 5, "NO"),
    # R=20, U large, cap=20 is the lowest cap allowed; use R=40 so the cap ends the search: incomplete, not a failure.
    (40, "2027-06-18", 20, "SEARCH_TRUNCATED_AT_CONFIG_CAP", "CONFIG_CAP", 20, "NOT_ASSESSED"),
    # R=5, U large, cap=30: arrival reached.
    (5, "2027-01-15", 30, "NO_CROSSING_BY_ARRIVAL", "ARRIVAL", 5, "NO"),
    # ties: arrival wins over the usable deadline and over the cap.
    (5, "2026-11-25", 30, "NO_CROSSING_BY_ARRIVAL", "ARRIVAL", 5, "NO"),
    (20, "2027-06-18", 20, "NO_CROSSING_BY_ARRIVAL", "ARRIVAL", 20, "NO"),
])
def test_no_crossing_names_the_boundary_that_ended_the_search(monkeypatch, arrival, expiry, cap, state, limit, end, coverage):
    never(monkeypatch)
    out = cs.scenario_crossing(**base(arrival_sessions_median=arrival, arrival_sessions_slow=arrival, expiry=expiry),
                               config=cfg(search_cap_sessions=cap))
    assert out["crossing_state"] == state
    assert (out["crossing_search_limit"], out["crossing_search_end_session"]) == (limit, end)
    assert out["crossing_covers_slow30_base"] == coverage
    assert out["crossing_n_slow_pace_30"] is None


def test_usable_deadline_ties_with_the_cap_resolve_to_the_usable_deadline(monkeypatch):
    never(monkeypatch)
    out = cs.scenario_crossing(**base(arrival_sessions_median=40, arrival_sessions_slow=40, expiry="2026-12-17"),
                               config=cfg(search_cap_sessions=20))          # E = 25 (26 Nov closed), U = 20, cap = 20
    assert out["crossing_usable_deadline_session"] == 20
    assert (out["crossing_state"], out["crossing_search_limit"]) == ("NO_CROSSING_BY_USABLE_DEADLINE", "USABLE_DEADLINE")


@pytest.mark.parametrize("expiry,usable", [("2026-11-18", 0), ("2026-11-16", -2), ("2026-11-10", -5)])
def test_no_usable_window_is_reported_and_nothing_is_searched(monkeypatch, expiry, usable):
    monkeypatch.setattr(cs, "_model_values", lambda *a, **k: pytest.fail("must not price"))
    out, recs = run(expiry=expiry)
    assert out["crossing_usable_deadline_session"] == usable and out["crossing_usable_deadline_date"] is None
    assert out["crossing_state"] == "NO_USABLE_WINDOW" and out["crossing_covers_slow30_base"] == "NO"
    assert all(r["crossing_session"] is None and r["search_end_session"] is None for r in recs.values())


# ---------------------------------------------------------------- states: never a number without the inputs

@pytest.mark.parametrize("over,state", [
    ({"mode": None}, "NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS"),
    ({"assessment_instant_utc": None}, "NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS"),
    ({"assessment_instant_utc": "2026-11-11T21:00:00"}, "NOT_ASSESSED_CALLER_DID_NOT_SUPPLY_ANCHORS"),   # no timezone
    ({"thesis_active": None}, "NOT_ASSESSED_THESIS_STATUS_UNKNOWN"),
    ({"thesis_active": False}, "THESIS_NOT_ACTIVE"),
    ({"thesis_origin_date": None}, "NOT_ASSESSED_NO_THESIS_ORIGIN"),
    ({"thesis_origin_date": "not-a-date"}, "NOT_ASSESSED_NO_THESIS_ORIGIN"),
    ({"thesis_origin_date": "2026-11-13"}, "NOT_ASSESSED_NO_THESIS_ORIGIN"),                             # after the assessment
    ({"quote_spot": None}, "NOT_ASSESSED_NO_SPOT"),
    ({"quote_spot": 0}, "NOT_ASSESSED_NO_SPOT"),
    ({"origin_spot": None}, "NOT_ASSESSED_NO_SPOT"),
    ({"frozen_target_level": None}, "NOT_ASSESSED_NO_LEVEL"),
    ({"frozen_target_level": 95.0}, "TARGET_ON_WRONG_SIDE"),                    # below the origin spot for a call
    ({"quote_spot": 111.0}, "TARGET_ALREADY_REACHED_AT_QUOTE"),                 # valid at origin, now passed
    ({"arrival_sessions_median": None, "arrival_sessions_slow": None}, "NOT_ASSESSED_NO_ARRIVAL_TIME"),
    ({"strike": None}, "NOT_ASSESSED_NO_STRIKE_IV_OR_EXPIRY"),
    ({"iv": 0}, "NOT_ASSESSED_NO_STRIKE_IV_OR_EXPIRY"),
    ({"expiry": None}, "NOT_ASSESSED_NO_STRIKE_IV_OR_EXPIRY"),
    ({"ask": None}, "NOT_ASSESSED_INVALID_QUOTE"),
    ({"ask": 0}, "NOT_ASSESSED_INVALID_QUOTE"),
    ({"bid": 5.20}, "NOT_ASSESSED_INVALID_QUOTE"),                              # crossed
    ({"bid": -0.10}, "NOT_ASSESSED_INVALID_QUOTE"),
    ({"bid": float("nan")}, "NOT_ASSESSED_INVALID_QUOTE"),
    ({"bid": None}, "NOT_ASSESSED_EXIT_COST_UNKNOWN"),
    ({"bid": 0}, "NOT_ASSESSED_EXIT_COST_UNKNOWN"),
])
def test_a_missing_or_unusable_input_gives_a_state_and_no_number(monkeypatch, over, state):
    monkeypatch.setattr(cs, "_model_values", lambda *a, **k: pytest.fail("must not price"))
    out, recs = run(**over)
    assert out["crossing_state"] == state
    assert out["crossing_covers_slow30_base"] == "NOT_ASSESSED"
    numbers = [out[k] for k in out if k.startswith("crossing_n_")]
    assert all(n is None for n in numbers)
    assert all(r["crossing_session"] is None for r in recs.values())
    assert out["crossing_authority"] == "DISPLAY_ONLY_NOT_VALIDATED"


def test_a_put_target_below_the_origin_is_valid_and_a_reached_put_target_is_reached():
    ok, _ = run(side="PUT", frozen_target_level=90.0, strike=100.0)
    assert ok["crossing_state"] not in ("TARGET_ON_WRONG_SIDE", "TARGET_ALREADY_REACHED_AT_QUOTE")
    reached, _ = run(side="PUT", frozen_target_level=90.0, quote_spot=89.0)
    assert reached["crossing_state"] == "TARGET_ALREADY_REACHED_AT_QUOTE"


def test_a_pricing_failure_is_its_own_state_and_never_a_no_crossing(monkeypatch):
    fixed_values(monkeypatch, lambda j, s, t, vol: float("nan") if j == 2 else 0.0)
    out, _ = run()
    assert out["crossing_state"] == "NOT_ASSESSED_PRICING_NUMERIC_FAILURE"
    assert out["crossing_covers_slow30_base"] == "NOT_ASSESSED"

    def boom(*a, **k):
        raise OverflowError("x")
    monkeypatch.setattr(cs, "_model_values", boom)
    assert run()[0]["crossing_state"] == "NOT_ASSESSED_PRICING_NUMERIC_FAILURE"


# ---------------------------------------------------------------- Morning: countdown from the frozen origin

def morning(at, **over):
    return run(mode="MORNING_FRESH_ENTRY", assessment_instant_utc=at, quote_timestamp_utc=at, **over)


def test_morning_counts_down_from_the_frozen_origin_and_never_restarts(monkeypatch):
    never(monkeypatch)
    remaining = []
    # Origin Wed 11 Nov. Mornings of 12, 13, 16 Nov and, across Thanksgiving, 27 Nov.
    for at in ("2026-11-12T14:40:00+00:00", "2026-11-13T14:40:00+00:00", "2026-11-16T14:40:00+00:00",
               "2026-11-27T14:40:00+00:00"):
        out, recs = morning(at)
        remaining.append((out["crossing_elapsed_sessions"], recs[("MEDIAN", 30, "BASE")]["remaining_pace_sessions"]))
    assert remaining == [(0, 10), (1, 9), (2, 8), (10, 0)]               # 27 Nov: ten sessions spent, median exhausted
    out, recs = morning("2026-11-27T14:40:00+00:00")
    assert recs[("MEDIAN", 30, "BASE")]["state"] == "PACE_EXHAUSTED"
    assert recs[("SLOW", 30, "BASE")]["state"] != "PACE_EXHAUSTED"       # the slow pace is assessed on its own
    assert recs[("SLOW", 30, "BASE")]["remaining_pace_sessions"] == 10


def test_a_repaired_contract_keeps_the_thesis_origin_and_target():
    a, _ = morning("2026-11-13T14:40:00+00:00")
    b, _ = morning("2026-11-13T14:40:00+00:00", contract_symbol="AAA270219C00105000", strike=105.0, expiry="2027-02-19")
    assert (a["crossing_thesis_origin_date"], a["crossing_frozen_target_level"], a["crossing_elapsed_sessions"]) == (
        b["crossing_thesis_origin_date"], b["crossing_frozen_target_level"], b["crossing_elapsed_sessions"])
    assert a["crossing_thesis_id"] == b["crossing_thesis_id"] and a["crossing_contract_symbol"] != b["crossing_contract_symbol"]


def test_the_morning_path_starts_from_the_quote_spot_towards_the_frozen_target(monkeypatch):
    seen = []
    monkeypatch.setattr(cs, "_model_values", lambda side, spots, strike, years, vol, **kw: seen.append(list(spots)) or [0.0] * len(spots))
    morning("2026-11-13T14:40:00+00:00", quote_spot=104.0)               # one session elapsed: R = 9 for the median
    median = seen[0]
    assert len(median) == 9 and median[0] == pytest.approx(104 + 6 * math.sqrt(1 / 9)) and median[-1] == pytest.approx(110.0)


# ---------------------------------------------------------------- configuration and labels

@pytest.mark.parametrize("over", [{"search_cap_sessions": 5}, {"search_cap_sessions": 500},
                                  {"exit_spread_stress_multiple": 9.0}, {"thresholds": [0.1, 0.3]},
                                  {"exit_spread_stress_multiple": float("nan")}])
def test_a_setting_outside_its_governed_range_is_refused(over):
    with pytest.raises(ValueError):
        cs.scenario_crossing(**base(), config=cfg(**over))


def test_the_result_carries_its_identity_assumptions_and_labels():
    out, recs = run()
    assert out["crossing_basis"] == "SQRT_TIME_PATH_TO_FROZEN_TARGET_V1"
    assert out["crossing_authority"] == "DISPLAY_ONLY_NOT_VALIDATED"
    assert out["crossing_invalidation_basis"] == "INVALIDATION_NOT_MODELLED"
    assert (out["crossing_thesis_id"], out["crossing_contract_symbol"]) == ("T:AAA:CALL:2026-11-11", "AAA270115C00100000")
    assert (out["crossing_rate_used"], out["crossing_rate_basis"], out["crossing_dividend_basis"]) == (0.04, "TEST", "TEST")
    assert out["crossing_iv_down_used"] == pytest.approx(0.30 * CFG["iv_down_multiple"])
    assert out["crossing_quote_timestamp_utc"] == "2026-11-11T21:00:00Z" and out["crossing_search_cap"] == 60
    assert len(recs) == 12 and set(out) >= set(cs.CROSSING_FIELDS)
    assert not any(k.startswith("monetisation_") or k.startswith("scenario_") for k in out)


def test_headline_coverage_follows_the_written_rule():
    assert cs.headline_coverage("CROSSES_COVERING") == "YES"
    for state in ("CROSSES_NOT_COVERING", "NO_CROSSING_BY_ARRIVAL", "NO_CROSSING_BY_USABLE_DEADLINE", "NO_USABLE_WINDOW"):
        assert cs.headline_coverage(state) == "NO"
    for state in ("SEARCH_TRUNCATED_AT_CONFIG_CAP", "PACE_EXHAUSTED", "NOT_ASSESSED_EXIT_COST_UNKNOWN", "THESIS_NOT_ACTIVE",
                  "TARGET_ALREADY_REACHED_AT_QUOTE", None):
        assert cs.headline_coverage(state) == "NOT_ASSESSED"
