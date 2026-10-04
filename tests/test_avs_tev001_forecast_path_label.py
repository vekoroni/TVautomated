"""S3 point-in-time first-passage labels for the option-neutral C4 panel."""

import pytest

from domain.forecast_path_label import label_forecast_path


def _bar(session: int, *, open: float = 100, high: float = 104,
         low: float = 96, close: float = 100) -> dict:
    return dict(session=session, open=open, high=high, low=low, close=close)


@pytest.mark.parametrize("hit_session,horizon", [(3, 5), (7, 10), (13, 20), (20, 20)])
def test_target_first_is_known_without_waiting_for_full_horizon(hit_session: int, horizon: int) -> None:
    bars = [_bar(day) for day in range(1, hit_session)]
    bars.append(_bar(hit_session, high=111, close=109))
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=bars, horizon_sessions=horizon,
    )
    assert result.event == "TARGET_FIRST"
    assert result.event_session == hit_session
    assert result.observed_sessions == hit_session
    assert result.censor_reason is None


def test_bear_stop_first_and_gap_open_are_retained() -> None:
    result = label_forecast_path(
        direction="BEAR", reference_spot=100, target_spot=90,
        invalidation_spot=105,
        future_bars=[_bar(1), _bar(2, open=107, high=108, low=99, close=104)],
        horizon_sessions=10,
    )
    assert result.event == "STOP_FIRST"
    assert result.event_session == 2
    assert result.gap_open_beyond_event is True


def test_same_bar_double_touch_is_adverse_first_and_flagged() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95,
        future_bars=[_bar(1, high=112, low=94, close=108)],
        horizon_sessions=5,
    )
    assert result.event == "STOP_FIRST"
    assert result.ambiguous_same_bar is True
    assert result.event_session == 1


def test_missing_session_censors_without_using_later_future_bar() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95,
        future_bars=[_bar(1), _bar(3, high=120)],
        horizon_sessions=5,
    )
    assert result.event == "CENSORED"
    assert result.censor_reason == "MISSING_SESSION"
    assert result.observed_sessions == 1
    assert result.event_session is None


def test_matured_survivor_retains_nonzero_return() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95,
        future_bars=[_bar(day, close=102) for day in range(1, 6)],
        horizon_sessions=5,
    )
    assert result.event == "NEITHER"
    assert result.survivor_return == pytest.approx(0.02)
    assert result.censor_reason is None


def test_short_observed_path_is_censored_not_loss() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=[_bar(1), _bar(2)],
        horizon_sessions=5,
    )
    assert result.event == "CENSORED"
    assert result.censor_reason == "NOT_YET_OBSERVABLE"
    assert result.survivor_return is None


def test_matured_horizon_with_missing_tail_is_data_gap_not_still_open() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=[_bar(1), _bar(2)],
        horizon_sessions=5, horizon_matured=True,
    )
    assert result.event == "CENSORED"
    assert result.censor_reason == "MISSING_SESSION"


def test_later_observed_bar_proves_horizon_gap_not_unmatured_status() -> None:
    result = label_forecast_path(
        direction="BULL", reference_spot=100, target_spot=110,
        invalidation_spot=95, future_bars=[_bar(1), _bar(6)],
        horizon_sessions=5,
    )
    assert result.event == "CENSORED"
    assert result.censor_reason == "MISSING_SESSION"
    assert result.observed_sessions == 1


def test_wrong_side_geometry_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalidation"):
        label_forecast_path(
            direction="BULL", reference_spot=100, target_spot=110,
            invalidation_spot=105, future_bars=[_bar(1)],
            horizon_sessions=5,
        )
