"""C4 option-neutral first-passage label for a governed OHLC path.

The caller supplies completed sessions 1..20 from a point-in-time source.
This pure function never invents a missing bar, direction, target or stop and
never interprets a quoted option return as an underlying outcome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class ForecastPathLabel:
    direction: str
    horizon_sessions: int
    event: str
    event_session: int | None
    observed_sessions: int
    censor_reason: str | None
    ambiguous_same_bar: bool
    gap_open_beyond_event: bool
    survivor_return: float | None
    label_version: str = "forecast_path_label_v1"


def _price(bar: Mapping[str, object], key: str, session: int) -> float:
    try:
        number = float(bar[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"session {session}: {key} is required and numeric") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"session {session}: {key} must be positive and finite")
    return number


def label_forecast_path(
    *,
    direction: str,
    reference_spot: float,
    target_spot: float,
    invalidation_spot: float,
    future_bars: Iterable[Mapping[str, object]],
    horizon_sessions: int,
    horizon_matured: bool = False,
) -> ForecastPathLabel:
    side = str(direction.value if isinstance(direction, Enum) else direction).strip().upper()
    if side not in {"BULL", "BEAR"}:
        raise ValueError("direction must be option-neutral BULL or BEAR")
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or not 1 <= horizon_sessions <= 20:
        raise ValueError("horizon_sessions must be an integer from 1 to 20")
    reference, target, stop = float(reference_spot), float(target_spot), float(invalidation_spot)
    if not all(math.isfinite(value) and value > 0 for value in (reference, target, stop)):
        raise ValueError("reference, target and invalidation must be positive and finite")
    if side == "BULL" and not stop < reference < target:
        raise ValueError("BULL invalidation < reference < target is required")
    if side == "BEAR" and not target < reference < stop:
        raise ValueError("BEAR target < reference < invalidation is required")

    observed = 0
    last_close: float | None = None
    for bar in future_bars:
        raw_session = bar.get("session")
        if isinstance(raw_session, bool) or not isinstance(raw_session, int):
            raise ValueError("bar session must be an integer")
        if raw_session > horizon_sessions:
            if observed < horizon_sessions:
                return ForecastPathLabel(side, horizon_sessions, "CENSORED", None,
                                         observed, "MISSING_SESSION", False, False, None)
            break
        if raw_session != observed + 1:
            if raw_session <= observed:
                raise ValueError("future bars must be strictly ordered and unique")
            return ForecastPathLabel(side, horizon_sessions, "CENSORED", None,
                                     observed, "MISSING_SESSION", False, False, None)
        opened = _price(bar, "open", raw_session)
        high = _price(bar, "high", raw_session)
        low = _price(bar, "low", raw_session)
        close = _price(bar, "close", raw_session)
        if low > high or not low <= opened <= high or not low <= close <= high:
            raise ValueError(f"session {raw_session}: invalid OHLC geometry")
        observed = raw_session
        last_close = close
        target_touch = high >= target if side == "BULL" else low <= target
        stop_touch = low <= stop if side == "BULL" else high >= stop
        if target_touch or stop_touch:
            # The day's OHLC cannot order two intraday touches; the signed-off
            # label convention assigns the adverse event first and flags it.
            adverse = stop_touch
            gap = (opened <= stop if side == "BULL" else opened >= stop) if adverse else (
                opened >= target if side == "BULL" else opened <= target
            )
            return ForecastPathLabel(
                side, horizon_sessions, "STOP_FIRST" if adverse else "TARGET_FIRST",
                raw_session, observed, None, target_touch and stop_touch, gap, None,
            )
    if observed < horizon_sessions:
        return ForecastPathLabel(side, horizon_sessions, "CENSORED", None,
                                 observed,
                                 "MISSING_SESSION" if horizon_matured else "NOT_YET_OBSERVABLE",
                                 False, False, None)
    assert last_close is not None
    sign = 1.0 if side == "BULL" else -1.0
    return ForecastPathLabel(side, horizon_sessions, "NEITHER", None,
                             observed, None, False, False,
                             sign * (last_close / reference - 1.0))
