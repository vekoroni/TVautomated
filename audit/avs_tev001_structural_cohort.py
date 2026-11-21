"""Read-only, pre-option geometry cohort construction for AVS-TEV-001.

This deliberately does not convert an option-stage 3R hurdle or a PENDING_OI
target into a prediction. It supplies research starts, not trade authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from domain.ticker_forecast import ForecastDirection, ForecastState, TickerForecast


@dataclass(frozen=True, slots=True)
class ForecastConstruction:
    forecast: TickerForecast | None
    reason: str
    target_source: str | None
    stop_source: str | None
    sector: str | None


def _positive_number(value: object) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def candidate_from_discovery(
    row: Mapping[str, object], *, run_id: str, evidence_session: str,
    as_of_utc: str,
) -> ForecastConstruction:
    """Project only governed Discovery facts, before contract search.

    Sourced geometry is suitable for a structural-label *audit*. A numeric
    C4 forecast still needs separately verified independent support.
    """
    target_source = str(row.get("structural_target_source") or "").strip() or None
    stop_source = str(row.get("governed_invalidation_source") or "").strip() or None
    sector = str(row.get("sector") or "").strip() or None

    def reject(reason: str) -> ForecastConstruction:
        return ForecastConstruction(None, reason, target_source, stop_source, sector)

    if str(row.get("direction_authority") or "").strip() != "DISCOVERY_GOVERNED":
        return reject("DIRECTION_NOT_GOVERNED")
    if str(row.get("is_stale") or "").strip().lower() in {"true", "1", "yes"}:
        return reject("STALE_BAR")
    bar_session = str(row.get("bar_data_asof") or "").strip()
    if bar_session and bar_session != evidence_session:
        return reject("BAR_SESSION_MISMATCH")
    direction = {
        "CALL": ForecastDirection.BULL, "PUT": ForecastDirection.BEAR,
    }.get(str(row.get("direction") or "").strip().upper())
    if direction is None:
        return reject("DIRECTION_NOT_DIRECTIONAL")
    ticker = str(row.get("ticker") or "").strip().upper()
    spot = _positive_number(row.get("stock_price"))
    if not ticker or spot is None:
        return reject("REFERENCE_SPOT_MISSING")

    # WYCKOFF is the only source known here to exist before option search.
    # Other sources require a separately proven pre-option provenance policy.
    target = (_positive_number(row.get("structural_target"))
              if target_source == "WYCKOFF" else None)
    stop = (_positive_number(row.get("governed_invalidation_spot"))
            if stop_source == "WYCKOFF_VALIDATION" else None)
    if stop is not None and ((direction is ForecastDirection.BULL and stop >= spot)
                             or (direction is ForecastDirection.BEAR and stop <= spot)):
        return reject("INVALID_GEOMETRY")
    if target is not None and ((direction is ForecastDirection.BULL and target <= spot)
                               or (direction is ForecastDirection.BEAR and target >= spot)):
        return reject("INVALID_GEOMETRY")

    reason = ("TARGET_NOT_SOURCED_PREOPTION" if target is None
              else "STOP_NOT_SOURCED_PREOPTION" if stop is None
              else "SOURCED_PREOPTION_GEOMETRY")
    try:
        forecast = TickerForecast(
            run_id=run_id, thesis_id=f"{run_id}:{ticker}:{evidence_session}:DISCOVERY",
            ticker=ticker, evidence_session=evidence_session, as_of_utc=as_of_utc,
            direction=direction, forecast_state=ForecastState.DESCRIPTIVE_ONLY,
            reference_spot=spot, target_spot=target, invalidation_spot=stop,
            supporting_evidence=("DISCOVERY_SNAPSHOT",),
        )
    except ValueError:
        return reject("INVALID_GEOMETRY")
    return ForecastConstruction(forecast, reason, target_source, stop_source, sector)
