"""S2 red/green boundary tests: search cannot rewrite the ticker forecast."""

from dataclasses import replace

from domain.ticker_forecast import (
    EstimationReliability, ForecastDirection, ForecastState, TickerForecast,
)
from domain.candidate_expression import enumerate_long_expressions


def _forecast(direction: ForecastDirection = ForecastDirection.BULL) -> TickerForecast:
    return TickerForecast(
        run_id="R", thesis_id="T", ticker="XYZ",
        evidence_session="2026-09-25", as_of_utc="2026-09-25T20:00:00Z",
        direction=direction, forecast_state=ForecastState.DESCRIPTIVE_ONLY,
        reference_spot=100.0,
        target_spot=110.0 if direction is ForecastDirection.BULL else 90.0,
        invalidation_spot=95.0 if direction is ForecastDirection.BULL else 105.0,
    )


def _quote(symbol: str, **extra) -> dict:
    return {"option_symbol": symbol, "bid": 2.0, "ask": 2.2,
            "source_run_id": "R",
            "quote_as_of_utc": "2026-09-25T20:00:00Z", **extra}


def test_more_than_one_same_side_contract_reaches_valuation() -> None:
    forecast = _forecast()
    quotes = [
        _quote("XYZ261016C00100000"),
        _quote("XYZ261120C00105000"),
        _quote("XYZ261016P00100000"),
    ]
    result = enumerate_long_expressions(
        forecast, quotes, last_exit_date="2026-10-09",
        expiry_buffer_days=0, max_candidates=2,
        quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    assert [candidate.option_symbol for candidate in result.candidates] == [
        "XYZ261016C00100000", "XYZ261120C00105000",
    ]
    assert result.rejection_counts == {"WRONG_SIDE": 1}
    assert result.rows_seen == len(result.candidates) + sum(result.rejection_counts.values())
    assert forecast == _forecast()


def test_no_chain_retains_forecast_and_explains_no_expression() -> None:
    result = enumerate_long_expressions(
        _forecast(), [], last_exit_date="2026-10-09",
        expiry_buffer_days=0, max_candidates=3,
        quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    assert result.candidates == ()
    assert result.expression_state == "NO_SUITABLE_OPTION"
    assert result.forecast_state == ForecastState.DESCRIPTIVE_ONLY


def test_runway_and_bad_quotes_have_distinct_reasons() -> None:
    result = enumerate_long_expressions(
        _forecast(), [
            _quote("XYZ260925C00100000"),
            _quote("XYZ261016C00100000", ask=1.0, bid=2.0),
            _quote("XYZ261120C00100000", ask=None),
        ], last_exit_date="2026-10-09",
        expiry_buffer_days=0, max_candidates=3,
        quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    assert result.rejection_counts == {"INSUFFICIENT_RUNWAY": 1, "CROSSED_QUOTE": 1, "MISSING_QUOTE": 1}
    assert result.expression_state == "NO_SUITABLE_OPTION"


def test_neutral_range_does_not_generate_long_directional_option() -> None:
    neutral = replace(_forecast(), direction=ForecastDirection.NEUTRAL_RANGE,
                      forecast_state=ForecastState.QUANTIFIED, target_spot=None,
                      invalidation_spot=None, evidence_packet_id="C4:1",
                      reliability_state=EstimationReliability.POOLED_SUPPORTED)
    result = enumerate_long_expressions(
        neutral, [_quote("XYZ261016C00100000")],
        last_exit_date="2026-10-09", expiry_buffer_days=0,
        max_candidates=3, quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    assert result.candidates == ()
    assert result.expression_state == "NOT_APPLICABLE_NEUTRAL_RANGE"
    assert result.rows_seen == 1


def test_invalidated_or_data_insufficient_forecast_cannot_generate_expression() -> None:
    for state in (ForecastState.INVALIDATED, ForecastState.DATA_INSUFFICIENT):
        forecast = replace(_forecast(), forecast_state=state)
        result = enumerate_long_expressions(
            forecast, [_quote("XYZ261016C00100000")],
            last_exit_date="2026-10-09", expiry_buffer_days=0,
            max_candidates=3, quote_cutoff_utc="2026-09-25T20:00:00Z",
        )
        assert result.candidates == ()
        assert result.expression_state == f"NOT_APPLICABLE_{state.value}"
        assert result.rows_seen == 1
        assert result.rejection_counts == {f"NOT_APPLICABLE_{state.value}": 1}


def test_bounded_search_is_deterministic_and_accounts_for_overflow() -> None:
    quotes = [
        _quote("XYZ261120C00105000"),
        _quote("XYZ261016C00100000"),
        _quote("XYZ261120C00100000"),
    ]
    args = dict(last_exit_date="2026-10-09", expiry_buffer_days=0, max_candidates=2,
                quote_cutoff_utc="2026-09-25T20:00:00Z")
    left = enumerate_long_expressions(_forecast(), quotes, **args)
    right = enumerate_long_expressions(_forecast(), list(reversed(quotes)), **args)
    assert left == right
    assert left.rejection_counts == {"BOUNDED_SEARCH_OVERFLOW": 1}
    assert left.rows_seen == 3


def test_run_identity_and_future_to_cutoff_quotes_are_not_candidates() -> None:
    result = enumerate_long_expressions(
        _forecast(), [
            _quote("XYZ261016C00100000", source_run_id="OTHER"),
            _quote("XYZ261120C00100000", quote_as_of_utc="2026-09-26T20:00:00Z"),
        ], last_exit_date="2026-10-09", expiry_buffer_days=0,
        max_candidates=2, quote_cutoff_utc="2026-09-25T21:00:00Z",
    )
    assert result.candidates == ()
    assert result.rejection_counts == {"RUN_MISMATCH": 1, "FUTURE_QUOTE": 1}


def test_duplicate_exact_symbol_is_ambiguous_regardless_of_chain_order() -> None:
    quotes = [
        _quote("XYZ261016C00100000", bid=1.8, ask=2.1),
        _quote("XYZ261016C00100000", bid=2.0, ask=2.2),
    ]
    args = dict(last_exit_date="2026-10-09", expiry_buffer_days=0,
                max_candidates=2, quote_cutoff_utc="2026-09-25T20:00:00Z")
    left = enumerate_long_expressions(_forecast(), quotes, **args)
    right = enumerate_long_expressions(_forecast(), list(reversed(quotes)), **args)
    assert left == right
    assert left.candidates == ()
    assert left.rejection_counts == {"DUPLICATE_SYMBOL": 2}
