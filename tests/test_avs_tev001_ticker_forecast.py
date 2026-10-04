"""S1 contract tests: the underlying forecast cannot own an option choice."""

from dataclasses import fields

import pytest

from domain.thesis_direction import FrozenThesis
from domain.ticker_forecast import (
    ForecastDirection,
    ForecastState,
    TickerForecast,
    from_legacy_frozen_thesis,
    option_right_for_forecast,
)


def _legacy(symbol: str) -> FrozenThesis:
    return FrozenThesis(
        thesis_id="T:XYZ:1", ticker="XYZ", direction="CALL",
        completed_session="2026-09-25", completed_close=100.0,
        target=110.0, invalidation=95.0, selected_contract=symbol,
        trigger=101.0,
    )


def test_legacy_contract_selection_cannot_change_ticker_forecast() -> None:
    first = from_legacy_frozen_thesis(
        _legacy("XYZ261016C00100000"), run_id="20260925_1",
        as_of_utc="2026-09-25T20:00:00Z",
    )
    second = from_legacy_frozen_thesis(
        _legacy("XYZ261120C00105000"), run_id="20260925_1",
        as_of_utc="2026-09-25T20:00:00Z",
    )
    assert first == second
    assert first.direction is ForecastDirection.BULL
    assert first.forecast_state is ForecastState.DESCRIPTIVE_ONLY
    assert not {"selected_contract", "option_right", "strike", "premium"} & {
        field.name for field in fields(TickerForecast)
    }


@pytest.mark.parametrize(
    ("direction", "expected"),
    [(ForecastDirection.BULL, "CALL"), (ForecastDirection.BEAR, "PUT"),
     (ForecastDirection.NEUTRAL_RANGE, None)],
)
def test_option_right_is_derived_only_at_expression_boundary(direction, expected) -> None:
    assert option_right_for_forecast(direction) == expected


def test_wrong_side_geometry_is_rejected_without_option_vocabulary() -> None:
    with pytest.raises(ValueError, match="invalidation"):
        TickerForecast(
            run_id="R", thesis_id="T", ticker="XYZ",
            evidence_session="2026-09-25", as_of_utc="2026-09-25T20:00:00Z",
            direction=ForecastDirection.BULL,
            forecast_state=ForecastState.DESCRIPTIVE_ONLY,
            reference_spot=100.0, target_spot=110.0, invalidation_spot=105.0,
        )


def test_mixed_evidence_is_recorded_without_forcing_an_option_gate() -> None:
    forecast = TickerForecast(
        run_id="R", thesis_id="T", ticker="xyz",
        evidence_session="2026-09-25", as_of_utc="2026-09-25T20:00:00Z",
        direction=ForecastDirection.BULL,
        forecast_state=ForecastState.DESCRIPTIVE_ONLY,
        reference_spot=100.0, target_spot=110.0, invalidation_spot=95.0,
        supporting_evidence=("WYCKOFF_ACCUMULATION",),
        opposing_evidence=("LOW_COMPRESSION",),
    )
    assert forecast.ticker == "XYZ"
    assert forecast.opposing_evidence == ("LOW_COMPRESSION",)
    assert forecast.forecast_state is ForecastState.DESCRIPTIVE_ONLY
