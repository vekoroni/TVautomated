"""Offline C5→C6→C4 vertical slice; no valuation or production wiring."""

from domain.candidate_expression import enumerate_long_expressions
from domain.forecast_path_label import label_forecast_path
from domain.thesis_direction import FrozenThesis
from domain.ticker_forecast import ForecastDirection, from_legacy_frozen_thesis


def test_underlying_thesis_survives_option_search_and_has_separate_outcome() -> None:
    legacy = FrozenThesis(
        thesis_id="R:XYZ:1", ticker="XYZ", direction="CALL",
        completed_session="2026-09-25", completed_close=100,
        target=110, invalidation=95, trigger=101,
        selected_contract="XYZ261016C00100000",
    )
    forecast = from_legacy_frozen_thesis(
        legacy, run_id="R", as_of_utc="2026-09-25T20:00:00Z",
    )
    assert forecast.direction is ForecastDirection.BULL
    quoted = [
        dict(source_run_id="R", option_symbol="XYZ261016C00100000",
             bid=2.0, ask=2.2, quote_as_of_utc="2026-09-25T20:00:00Z"),
        dict(source_run_id="R", option_symbol="XYZ261120C00105000",
             bid=3.0, ask=3.3, quote_as_of_utc="2026-09-25T20:00:00Z"),
    ]
    expressions = enumerate_long_expressions(
        forecast, quoted, last_exit_date="2026-10-09",
        expiry_buffer_days=0, max_candidates=2,
        quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    outcome = label_forecast_path(
        direction=forecast.direction, reference_spot=forecast.reference_spot,
        target_spot=forecast.target_spot,
        invalidation_spot=forecast.invalidation_spot,
        future_bars=[
            dict(session=1, open=100, high=104, low=96, close=102),
            dict(session=2, open=103, high=111, low=101, close=109),
        ], horizon_sessions=5,
    )
    assert len(expressions.candidates) == 2
    assert outcome.event == "TARGET_FIRST"
    assert outcome.event_session == 2
    assert expressions.forecast_state == forecast.forecast_state
    assert all(item.thesis_id == forecast.thesis_id for item in expressions.candidates)

    no_chain = enumerate_long_expressions(
        forecast, [], last_exit_date="2026-10-09",
        expiry_buffer_days=0, max_candidates=2,
        quote_cutoff_utc="2026-09-25T20:00:00Z",
    )
    assert no_chain.expression_state == "NO_SUITABLE_OPTION"
    assert forecast.direction is ForecastDirection.BULL
    assert outcome.event == "TARGET_FIRST"
