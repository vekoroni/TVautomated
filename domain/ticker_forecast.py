"""Option-neutral C5 ticker forecast contract (AVS-SD-TEV-001/S1).

This is a domain boundary, not a predictor. Quantified probabilities are owned
by a separately versioned C4 evidence packet; the legacy adapter can only
publish a descriptive forecast. No option identifier or option right belongs
to this value object.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from domain.thesis_direction import FrozenThesis


class ForecastDirection(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL_RANGE = "NEUTRAL_RANGE"


class ForecastState(str, Enum):
    QUANTIFIED = "QUANTIFIED"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    INVALIDATED = "INVALIDATED"


class EstimationReliability(str, Enum):
    LOCAL_SUPPORTED = "LOCAL_SUPPORTED"
    POOLED_SUPPORTED = "POOLED_SUPPORTED"
    POOLED_WIDE = "POOLED_WIDE"
    STATISTICALLY_UNRELIABLE = "STATISTICALLY_UNRELIABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


@dataclass(frozen=True, slots=True)
class TickerForecast:
    run_id: str
    thesis_id: str
    ticker: str
    evidence_session: str
    as_of_utc: str
    direction: ForecastDirection
    forecast_state: ForecastState
    reference_spot: float
    target_spot: float | None
    invalidation_spot: float | None
    trigger_spot: float | None = None
    supporting_evidence: tuple[str, ...] = ()
    opposing_evidence: tuple[str, ...] = ()
    evidence_packet_id: str | None = None
    reliability_state: EstimationReliability = EstimationReliability.NOT_ESTIMABLE
    forecast_version: str = "ticker_forecast_v2"

    def __post_init__(self) -> None:
        direction = ForecastDirection(self.direction if isinstance(self.direction, ForecastDirection) else str(self.direction).upper())
        state = ForecastState(self.forecast_state if isinstance(self.forecast_state, ForecastState) else str(self.forecast_state).upper())
        reliability = EstimationReliability(self.reliability_state if isinstance(self.reliability_state, EstimationReliability) else str(self.reliability_state).upper())
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "forecast_state", state)
        object.__setattr__(self, "reliability_state", reliability)
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        for name in ("run_id", "thesis_id", "ticker"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        try:
            date.fromisoformat(self.evidence_session)
            as_of = datetime.fromisoformat(self.as_of_utc.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("evidence_session/as_of_utc must be ISO timestamps") from error
        if as_of.tzinfo is None:
            raise ValueError("as_of_utc requires a timezone")
        if not math.isfinite(self.reference_spot) or self.reference_spot <= 0:
            raise ValueError("reference_spot must be positive and finite")
        for name in ("target_spot", "invalidation_spot", "trigger_spot"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{name} must be positive and finite")
        if direction is ForecastDirection.BULL:
            if self.invalidation_spot is not None and not self.invalidation_spot < self.reference_spot:
                raise ValueError("BULL invalidation must be below reference spot")
            if self.target_spot is not None and not self.target_spot > self.reference_spot:
                raise ValueError("BULL target must be above reference spot")
        elif direction is ForecastDirection.BEAR:
            if self.invalidation_spot is not None and not self.invalidation_spot > self.reference_spot:
                raise ValueError("BEAR invalidation must be above reference spot")
            if self.target_spot is not None and not self.target_spot < self.reference_spot:
                raise ValueError("BEAR target must be below reference spot")
        elif self.target_spot is not None or self.invalidation_spot is not None:
            raise ValueError("NEUTRAL_RANGE cannot inherit one-sided geometry")
        if state is ForecastState.QUANTIFIED:
            if not self.evidence_packet_id or reliability is EstimationReliability.NOT_ESTIMABLE:
                raise ValueError("QUANTIFIED requires a supported C4 evidence packet")
        if direction is ForecastDirection.NEUTRAL_RANGE and state is not ForecastState.QUANTIFIED:
            raise ValueError("NEUTRAL_RANGE requires quantified supporting evidence")


def from_legacy_frozen_thesis(
    thesis: FrozenThesis, *, run_id: str, as_of_utc: str,
) -> TickerForecast:
    """Project *underlying* legacy facts without reading selected_contract.

    Legacy CALL/PUT vocabulary maps only at this migration boundary. A legacy
    non-directional label is not evidence for supported NEUTRAL_RANGE.
    """
    direction = {"CALL": ForecastDirection.BULL, "PUT": ForecastDirection.BEAR}.get(thesis.direction)
    if direction is None:
        raise ValueError("legacy non-directional thesis needs C4 evidence, not a neutral default")
    return TickerForecast(
        run_id=run_id,
        thesis_id=thesis.thesis_id,
        ticker=thesis.ticker,
        evidence_session=thesis.completed_session,
        as_of_utc=as_of_utc,
        direction=direction,
        forecast_state=ForecastState.DESCRIPTIVE_ONLY,
        reference_spot=thesis.completed_close,
        target_spot=thesis.target,
        invalidation_spot=thesis.invalidation,
        trigger_spot=thesis.trigger,
        supporting_evidence=(thesis.completed_profile_evidence_id,)
        if thesis.completed_profile_evidence_id else (),
    )


def option_right_for_forecast(direction: ForecastDirection) -> str | None:
    """C5→C6 boundary mapping; never part of TickerForecast itself."""
    return {
        ForecastDirection.BULL: "CALL",
        ForecastDirection.BEAR: "PUT",
        ForecastDirection.NEUTRAL_RANGE: None,
    }[ForecastDirection(direction if isinstance(direction, ForecastDirection) else str(direction).upper())]
