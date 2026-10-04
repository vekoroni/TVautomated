"""Offline C5→canonical OHLCV→C4 outcome observation bridge.

This is an additive, read-only research path. No contract, option return,
trading verdict or production permission is derived here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from avshunter.shared.xnys_calendar import SessionPhase, session_state
from domain.forecast_path_label import label_forecast_path
from domain.ticker_forecast import ForecastDirection, TickerForecast

from .forecast_path_reader import ADJUSTMENT_CONVENTION, read_price_path


PANEL_VERSION = "forecast_outcome_panel_v1"


def _utc(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("forecast and label timestamps must be timezone-aware")
    return stamp.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ForecastOutcomePanelRow:
    run_id: str
    thesis_id: str
    ticker: str
    evidence_session: str
    forecast_as_of_utc: str
    label_cutoff_utc: str
    forecast_version: str
    direction: str
    reference_spot: float
    target_spot: float | None
    invalidation_spot: float | None
    horizon_sessions: int
    horizon_end_session: str | None
    event: str
    event_session: int | None
    data_status: str
    censor_reason: str | None
    ambiguous_same_bar: bool
    survivor_return: float | None
    missing_sessions: tuple[int, ...]
    bar_version_fingerprints: tuple[str, ...]
    revision_rewinds: int
    adjustment_convention: str
    authority: str = "RESEARCH_ONLY"
    panel_version: str = PANEL_VERSION


def build_outcome_panel_row(
    forecast: TickerForecast,
    database_path: str | Path,
    *,
    horizon_sessions: int,
    label_cutoff_utc: str,
    adjustment_convention: str = ADJUSTMENT_CONVENTION,
) -> ForecastOutcomePanelRow:
    """Bind immutable forecast identity to an as-of first-passage label."""
    if _utc(label_cutoff_utc) < _utc(forecast.as_of_utc):
        raise ValueError("label cut-off precedes frozen forecast")
    phase, market_session, last_completed = session_state(_utc(forecast.as_of_utc))
    if last_completed.isoformat() != forecast.evidence_session:
        raise ValueError("forecast evidence session is not the last completed session at publication")
    if (market_session is not None
            and market_session > date.fromisoformat(forecast.evidence_session)
            and phase in {SessionPhase.REGULAR, SessionPhase.AFTER_HOURS}):
        raise ValueError("forecast was published during a future session's daily bar")
    if isinstance(horizon_sessions, bool) or not isinstance(horizon_sessions, int) or not 1 <= horizon_sessions <= 20:
        raise ValueError("horizon_sessions must be an integer from 1 to 20")
    base = dict(
        run_id=forecast.run_id, thesis_id=forecast.thesis_id,
        ticker=forecast.ticker, evidence_session=forecast.evidence_session,
        forecast_as_of_utc=forecast.as_of_utc,
        label_cutoff_utc=label_cutoff_utc,
        forecast_version=forecast.forecast_version,
        direction=forecast.direction.value,
        reference_spot=forecast.reference_spot,
        target_spot=forecast.target_spot,
        invalidation_spot=forecast.invalidation_spot,
        horizon_sessions=horizon_sessions,
        adjustment_convention=adjustment_convention,
    )
    if forecast.direction is ForecastDirection.NEUTRAL_RANGE:
        return ForecastOutcomePanelRow(
            **base, horizon_end_session=None, event="NOT_LABELLED",
            event_session=None, data_status="NEUTRAL_RANGE_REQUIRES_SEPARATE_LABEL",
            censor_reason=None, ambiguous_same_bar=False, survivor_return=None,
            missing_sessions=(), bar_version_fingerprints=(), revision_rewinds=0,
        )
    if forecast.target_spot is None or forecast.invalidation_spot is None:
        return ForecastOutcomePanelRow(
            **base, horizon_end_session=None, event="NOT_LABELLED",
            event_session=None, data_status="MISSING_GEOMETRY",
            censor_reason=None, ambiguous_same_bar=False, survivor_return=None,
            missing_sessions=(), bar_version_fingerprints=(), revision_rewinds=0,
        )
    path = read_price_path(
        database_path, ticker=forecast.ticker,
        start_session=forecast.evidence_session,
        horizon_sessions=horizon_sessions,
        label_cutoff_utc=label_cutoff_utc,
        adjustment_convention=adjustment_convention,
    )
    label = label_forecast_path(
        direction=forecast.direction, reference_spot=forecast.reference_spot,
        target_spot=forecast.target_spot,
        invalidation_spot=forecast.invalidation_spot,
        future_bars=(bar.to_label_bar() for bar in path.bars),
        horizon_sessions=horizon_sessions,
        horizon_matured=path.horizon_matured,
    )
    status = {
        "TARGET_FIRST": "RESOLVED_EVENT",
        "STOP_FIRST": "RESOLVED_EVENT",
        "NEITHER": "COMPLETE_SURVIVOR",
    }.get(label.event)
    if status is None:
        status = ("CENSORED_MISSING_DATA" if label.censor_reason == "MISSING_SESSION"
                  else "PENDING_OUTCOME")
    return ForecastOutcomePanelRow(
        **base, horizon_end_session=path.horizon_end_session,
        event=label.event, event_session=label.event_session,
        data_status=status, censor_reason=label.censor_reason,
        ambiguous_same_bar=label.ambiguous_same_bar,
        survivor_return=label.survivor_return,
        missing_sessions=path.missing_sessions,
        bar_version_fingerprints=tuple(
            bar.version_fingerprint for bar in path.bars
            if bar.session <= label.observed_sessions
        ),
        revision_rewinds=path.revision_rewinds,
    )
