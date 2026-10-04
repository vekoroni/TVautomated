"""Quote age is disclosed, never a gate (ACK 17 Sep 2026; reaffirmed 3 Oct 2026, build step 2).

"we will always have stale prices the way we trade the pipeline … we should remove stale prices.
This is why human eyes are needed for final execution."

Business rules:
- An option quote is valued and classified on what it is (two-sided, spread, validity), whatever
  its age. Age never blocks EV3, execution viability, the liquidity lifecycle or empirical EV.
- Age is disclosed: the age state relative to the disclosed feed window, and an instruction to
  re-quote at the broker before entry.
- Unusable quotes stay blocked: crossed, negative or non-positive ask, zero bid, spread beyond
  policy, no quote. A future-dated timestamp is a data error, stated as such (not "stale").
Evidence: run 20261001_211641 lost 1,112 EV3 valuations (quotes 20–30 min old on the delayed feed
against a 15-minute limit), 107 execution-viability rows and 101 lifecycle rows to age alone.
"""
from datetime import datetime, timedelta, timezone

from domain.long_option_execution import evaluate_execution_viability, quote_age_disclosure
from domain.option_contract_liquidity import classify_current_executability

NOW = datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc)
TWO_HOURS_OLD = (NOW - timedelta(hours=2)).isoformat()


def _hydrated(bid, ask, stamp=TWO_HOURS_OLD):
    return {"selected_structure_hydration_status": "COMPLETE", "selected_structure": "LONG_SINGLE",
            "selected_long_leg": {"bid": bid, "ask": ask}, "selected_quote_timestamp_utc": stamp}


def test_disclosure_states_the_age_and_the_requote_instruction():
    old = quote_age_disclosure(7200.0, raw_age_seconds=8100.0)
    assert old["quote_age_state"] == "BEYOND_FEED_WINDOW"
    assert old["quote_age_minutes"] == 135.0
    assert old["quote_requote_instruction"] == "REQUOTE_AT_BROKER_BEFORE_ENTRY"
    assert quote_age_disclosure(60.0)["quote_age_state"] == "WITHIN_FEED_WINDOW"
    assert quote_age_disclosure(None)["quote_age_state"] == "UNKNOWN"


def test_old_quote_is_classified_on_its_spread_not_its_age():
    out = evaluate_execution_viability({}, _hydrated(1.49, 1.51), as_of_utc=NOW)
    assert out["execution_viability_state"] == "EXECUTABLE_QUOTE"
    assert out["execution_viability_eligible"] is True
    assert out["execution_viability_quote_age_state"] == "BEYOND_FEED_WINDOW"
    assert out["execution_viability_quote_requote_instruction"] == "REQUOTE_AT_BROKER_BEFORE_ENTRY"


def test_old_quote_with_unusable_book_is_still_blocked():
    crossed = evaluate_execution_viability({}, _hydrated(1.60, 1.50), as_of_utc=NOW)
    assert crossed["execution_viability_state"] == "INVALID_QUOTE"
    zero_bid = evaluate_execution_viability({}, _hydrated(0.0, 0.10), as_of_utc=NOW)
    assert zero_bid["execution_viability_state"] == "ZERO_BID_REVIEW"


def _lifecycle(bid, ask, age):
    return classify_current_executability(bid=bid, ask=ask, bid_size=10, ask_size=10, quote_age_seconds=age,
                                          dte=55, minimum_required_dte=20, moneyness_treatment="PREFERRED_EXECUTION")


def test_lifecycle_does_not_park_an_old_quote():
    out = _lifecycle(1.49, 1.51, 7200)
    assert out["liquidity_state"] == "EXECUTABLE_NOW"
    assert out["quote_age_state"] == "BEYOND_FEED_WINDOW"
    assert out["quote_requote_instruction"] == "REQUOTE_AT_BROKER_BEFORE_ENTRY"
    assert _lifecycle(1.60, 1.50, 7200)["liquidity_state"] == "INVALID_QUOTE"


def test_ev3_values_an_old_quote_and_states_a_future_timestamp():
    import inspect
    from vanguard import ev3_stage0
    source = inspect.getsource(ev3_stage0)
    assert "\"REJECT_QUOTE_STALE\"" not in source          # age no longer rejects
    assert "REJECT_QUOTE_TIMESTAMP_FUTURE" in source


def test_empirical_ev_has_no_age_gate():
    from empirical_option_ev import QUALITY_STALE_QUOTE  # kept as a constant for old records
    import inspect
    import empirical_option_ev
    assert "_null_result(QUALITY_STALE_QUOTE)" not in inspect.getsource(empirical_option_ev)
    assert QUALITY_STALE_QUOTE == "STALE_QUOTE"
