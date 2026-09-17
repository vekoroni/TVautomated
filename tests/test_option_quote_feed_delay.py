"""Option quote feed delay (ACK 17 Sep 2026, option 2) — a disclosed provider delay is a fact, not staleness.

Evidence: MarketData returns ``x-options-data-permissions: delayed_quotes_permission`` and every morning quote on
17 Sep 2026 arrived 891-900 s after its provider timestamp (1,332 contracts), so a 900 s freshness window on raw
age failed 100% of contracts and made GO impossible.

Rules:
  Q1 the disclosed feed delay and the freshness window are governed configuration (option_quote_feed), fail-closed;
  Q2 quote freshness is judged on effective age = raw age - disclosed delay (never below zero); raw age is kept;
  Q3 a quote within the window on effective age is not REQUOTE_REQUIRED and is flagged DELAYED_PROVIDER_FEED;
  Q4 a quote older than delay + window is still REQUOTE_REQUIRED (genuine staleness is not excused);
  Q5 the morning liquidity lifecycle uses the same effective age. EV3 (retired, advisory only) is deliberately
     unchanged (ACK 17 Sep 2026) and still reports these quotes as REJECT_QUOTE_STALE — a known false label.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from domain import long_option_execution as policy

NOW = datetime(2026, 9, 17, 15, 43, 0, tzinfo=timezone.utc)


def stamp(seconds_ago: float) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def hydrated(seconds_ago: float) -> dict:
    return {"selected_contract_symbol": "IHI261016P00052000", "selected_structure": "LONG_SINGLE",
            "selected_structure_hydration_status": "COMPLETE", "selected_long_leg": {"bid": 1.35, "ask": 1.45},
            "selected_quote_timestamp_utc": stamp(seconds_ago)}


def test_q1_feed_delay_and_window_are_governed(tmp_path):
    assert policy.QUOTE_FEED_DELAY_SECONDS == 900.0
    assert policy.EXECUTION_QUOTE_FRESHNESS_MAX_SECONDS == 900.0
    bad = tmp_path / "constants.json"
    bad.write_text(json.dumps({"option_quote_feed": {"version": "option_quote_feed_v1", "provider": "MARKETDATA",
                                                     "disclosed_delay_seconds": -1, "freshness_max_seconds": 900}}))
    with pytest.raises(ValueError):
        policy._load_option_quote_feed(bad)


def test_q2_effective_age_subtracts_disclosed_delay():
    assert policy.effective_quote_age_seconds(stamp(1200), as_of_utc=NOW) == pytest.approx(300)
    assert policy.effective_quote_age_seconds(stamp(600), as_of_utc=NOW) == 0.0
    assert policy.effective_quote_age_seconds(None, as_of_utc=NOW) is None


def test_q3_delayed_quote_within_window_is_executable_and_flagged():
    out = policy.evaluate_execution_viability({}, hydrated(1381), as_of_utc=NOW)
    assert out["execution_viability_state"] == "EXECUTABLE_QUOTE"
    assert out["execution_viability_quote_age_seconds"] == pytest.approx(481)
    assert out["execution_viability_quote_raw_age_seconds"] == pytest.approx(1381)
    assert out["execution_viability_quote_feed_state"] == "DELAYED_PROVIDER_FEED"


def test_q4_genuinely_stale_quote_still_requires_requote():
    out = policy.evaluate_execution_viability({}, hydrated(900 + 901), as_of_utc=NOW)
    assert out["execution_viability_state"] == "REQUOTE_REQUIRED"
    assert out["execution_viability_reason"] == "PROVIDER_QUOTE_OUTSIDE_FRESHNESS_WINDOW"


def test_q5_morning_gate_lifecycle_imports_effective_age():
    import morning_gate
    assert morning_gate.effective_quote_age_seconds is policy.effective_quote_age_seconds
