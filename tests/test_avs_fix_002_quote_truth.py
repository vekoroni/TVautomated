from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from contracts.quote_change_evidence import (
    ComparisonStatus,
    QuoteSnapshot,
    compare_exact_option_quotes,
    quote_snapshot_from_row,
)
from contracts.selected_contract_economics import hydrate_selected_structure
from domain.option_contract_liquidity import classify_current_executability
from domain.long_option_execution import evaluate_execution_viability
from domain.quote_units import resolve_spread


SYMBOL = "AAA261016C00100000"


def test_spread_units_are_explicit_and_magnitude_is_never_guessed() -> None:
    assert resolve_spread({"spread_pct": 0.2}).quality_state == (
        "NOT_EVALUATED_UNIT_AMBIGUOUS"
    )
    assert resolve_spread({
        "spread_pct": 0.2,
        "spread_unit": "FRACTION_OF_MID",
    }).spread_pct_of_mid == 20.0
    assert resolve_spread({
        "spread_pct": 20.0,
        "spread_unit": "PCT_OF_MID",
    }).spread_fraction_mid == 0.2


def test_timestamp_less_quote_is_monitor_only_not_executable() -> None:
    result = classify_current_executability(
        bid=1.0,
        ask=1.1,
        quote_age_seconds=None,
        dte=30,
        minimum_required_dte=7,
        moneyness_treatment="PREFERRED_EXECUTION",
    )
    assert result["liquidity_state"] == "QUOTE_TIMESTAMP_UNAVAILABLE"
    assert result["executable_now"] is False


def test_hydration_keeps_fetch_time_separate_from_provider_time() -> None:
    hydrated = hydrate_selected_structure(
        SYMBOL,
        lambda _symbol: {
            "live_contract_bid": 1.0,
            "live_contract_ask": 1.1,
            "live_contract_mid": 1.05,
            "live_options_source": "MARKETDATA",
            "live_options_fetched_at": "2026-09-13T12:00:00+00:00",
        },
        ticker="AAA",
        direction="CALL",
        instrument="LONG_CALL",
        fetched_at_utc="2026-09-13T12:00:00+00:00",
    )
    assert hydrated["selected_quote_timestamp_utc"] is None
    assert hydrated["live_options_fetched_at"] == "2026-09-13T12:00:00+00:00"
    assert hydrated["spread_fraction_mid"] > 0
    assert hydrated["spread_pct_of_mid"] > 0


def test_quote_comparison_uses_provider_time_and_preserves_thesis() -> None:
    observed = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
    base = QuoteSnapshot(
        contract_symbol=SYMBOL,
        dataset_id="D1",
        timestamp_utc=observed,
        session_date=date(2026, 9, 13),
        bid=1.0,
        ask=1.1,
        mid=1.05,
        spread_fraction_mid=(0.1 / 1.05),
        bid_size=10,
        ask_size=10,
        source="MARKETDATA",
    )
    result = compare_exact_option_quotes(
        ticker="AAA",
        thesis_id="T",
        trade_idea_id="I",
        selected_structure_id="S",
        morning=base,
        current=base,
        now=observed + timedelta(minutes=20),
        live_ttl_seconds=15 * 60,
    )
    assert result["comparison_status"] == ComparisonStatus.SAME_CONTRACT.value
    assert result["quote_freshness"] == "STALE"
    assert result["quote_age_affects_thesis"] is False


def test_fetch_time_is_not_accepted_as_provider_quote_time() -> None:
    snapshot = quote_snapshot_from_row({
        "current_contract_symbol": SYMBOL,
        "current_quote_dataset_id": "D1",
        "live_options_fetched_at": "2026-09-13T12:00:00+00:00",
        "current_contract_bid": 1.0,
        "current_contract_ask": 1.1,
    }, role="CURRENT")
    assert snapshot.timestamp_utc is None


def test_stale_provider_quote_requires_requote_without_touching_thesis() -> None:
    result = evaluate_execution_viability(
        {"instrument": "LONG_CALL"},
        {
            "selected_structure_hydration_status": "COMPLETE",
            "selected_structure": "LONG_SINGLE",
            "selected_long_leg": {"bid": 1.0, "ask": 1.1},
            "selected_quote_timestamp_utc": "2026-09-10T09:30:00+00:00",
        },
        as_of_utc="2026-09-10T10:00:00+00:00",
    )
    assert result["execution_viability_state"] == "REQUOTE_REQUIRED"
    assert result["execution_viability_eligible"] is False
