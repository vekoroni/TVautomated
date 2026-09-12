"""Pure DOI-7 outcome labelling for dynamic long CALL/PUT candidates.

The domain records what happened after an immutable contract assessment.  It
does not fetch data, choose a contract, change a thesis, grant capital or mix
hypothetical market paths with realised trader fills/P&L.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .decision_outcome import evaluate_outcome_path
from .dynamic_options_intelligence import DOI_DECISION_AUTHORITY


DOI_OUTCOME_DOMAIN_VERSION = "doi-outcome-label-v1"
DOI_OUTCOME_CALCULATION_VERSION = "doi-outcome-calculation-v1"
DOI_OUTCOME_KIND = "HYPOTHETICAL_MARKET_PATH"


class OutcomeLeakageError(ValueError):
    """Raised when a label attempts to use evidence unavailable at its cutoff."""


class OutcomeDataStatus(str, Enum):
    COMPLETE = "COMPLETE"
    COMPLETE_OPTION_PATH_PARTIAL = "COMPLETE_OPTION_PATH_PARTIAL"
    COMPLETE_OPTION_RETURN_UNAVAILABLE = "COMPLETE_OPTION_RETURN_UNAVAILABLE"
    DEFERRED_NOT_YET_OBSERVABLE = "DEFERRED_NOT_YET_OBSERVABLE"
    DATA_EXCEPTION = "DATA_EXCEPTION"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _finite_optional(value: float | int | None, name: str) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite when supplied")
    return parsed


def _positive_optional(value: float | int | None, name: str) -> float | None:
    parsed = _finite_optional(value, name)
    if parsed is not None and parsed <= 0:
        raise ValueError(f"{name} must be positive when supplied")
    return parsed


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True, slots=True)
class OptionPathObservation:
    """One exact-contract observation from a future completed session."""

    observation_id: str
    dataset_id: str
    contract_symbol: str
    session_date: date
    quote_at_utc: datetime
    available_at_utc: datetime
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None

    def __post_init__(self) -> None:
        for name in ("observation_id", "dataset_id", "contract_symbol"):
            value = str(getattr(self, name) or "").strip()
            if not value:
                raise ValueError(f"{name} is required")
            object.__setattr__(self, name, value.upper() if name == "contract_symbol" else value)
        if not isinstance(self.session_date, date):
            raise ValueError("session_date must be a date")
        object.__setattr__(self, "quote_at_utc", _utc(self.quote_at_utc, "quote_at_utc"))
        object.__setattr__(self, "available_at_utc", _utc(self.available_at_utc, "available_at_utc"))
        if self.available_at_utc < self.quote_at_utc:
            raise ValueError("available_at_utc cannot precede quote_at_utc")
        for name in ("bid", "ask", "volume", "open_interest", "implied_volatility"):
            value = _finite_optional(getattr(self, name), name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
            object.__setattr__(self, name, value)
        if self.bid is not None and self.ask is not None and self.ask < self.bid:
            raise ValueError("ask cannot be below bid")

    @property
    def two_sided(self) -> bool:
        return self.bid is not None and self.ask is not None and self.bid > 0 and self.ask >= self.bid

    @property
    def mark(self) -> float | None:
        if self.bid is None or self.ask is None or self.ask <= 0:
            return None
        return (self.bid + self.ask) / 2.0

    @property
    def spread_fraction(self) -> float | None:
        mark = self.mark
        return ((self.ask - self.bid) / mark) if mark and self.bid is not None and self.ask is not None else None


@dataclass(frozen=True, slots=True)
class UnderlyingPathObservation:
    """One future completed-session underlying OHLC observation."""

    dataset_id: str
    session_date: date
    available_at_utc: datetime
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if not str(self.dataset_id or "").strip():
            raise ValueError("dataset_id is required")
        if not isinstance(self.session_date, date):
            raise ValueError("session_date must be a date")
        object.__setattr__(self, "available_at_utc", _utc(self.available_at_utc, "available_at_utc"))
        for name in ("high", "low", "close"):
            value = _positive_optional(getattr(self, name), name)
            object.__setattr__(self, name, value)
        if self.high < self.low or not (self.low <= self.close <= self.high):
            raise ValueError("underlying OHLC geometry is invalid")


@dataclass(frozen=True, slots=True)
class OutcomeLabelPolicy:
    """Observable label thresholds, not execution gates or fitted probabilities."""

    spread_milestones: tuple[float, ...] = (0.15, 0.25, 0.35)
    return_hurdle: float = 0.10
    calculation_version: str = DOI_OUTCOME_CALCULATION_VERSION

    def __post_init__(self) -> None:
        milestones = tuple(sorted({float(item) for item in self.spread_milestones}))
        if not milestones or any(not math.isfinite(item) or item <= 0 for item in milestones):
            raise ValueError("spread_milestones must contain positive finite values")
        if not math.isfinite(float(self.return_hurdle)):
            raise ValueError("return_hurdle must be finite")
        object.__setattr__(self, "spread_milestones", milestones)
        if not str(self.calculation_version or "").strip():
            raise ValueError("calculation_version is required")


@dataclass(frozen=True, slots=True)
class DOIOutcomeLabel:
    label_id: str
    assessment_id: str
    family_id: str
    thesis_id: str
    run_id: str
    ticker: str
    contract_symbol: str
    original_observation_id: str
    direction: str
    horizon_sessions: int
    assessment_cutoff_utc: datetime
    outcome_cutoff_utc: datetime
    horizon_end_session: date | None
    data_status: OutcomeDataStatus
    option_points_observed: int
    underlying_points_observed: int
    reference_option_mid: float | None
    reference_entry_ask: float | None
    terminal_option_mid_return: float | None
    terminal_executable_return: float | None
    option_mark_mfe: float | None
    option_mark_mae: float | None
    option_executable_mfe: float | None
    option_executable_mae: float | None
    underlying_directional_return: float | None
    underlying_mfe: float | None
    underlying_mae: float | None
    first_two_sided_session: int | None
    first_spread_15_session: int | None
    first_spread_25_session: int | None
    first_spread_35_session: int | None
    first_return_hurdle_session: int | None
    target_first_hit_session: int | None
    invalidation_first_hit_session: int | None
    first_passage_state: str
    minimum_spread_fraction: float | None
    maximum_volume: float | None
    maximum_open_interest: float | None
    source_option_observation_ids: tuple[str, ...]
    source_option_dataset_ids: tuple[str, ...]
    source_underlying_dataset_ids: tuple[str, ...]
    data_gap_reasons: tuple[str, ...]
    calculation_version: str = DOI_OUTCOME_CALCULATION_VERSION
    outcome_kind: str = DOI_OUTCOME_KIND
    is_counterfactual: bool = True
    uses_realised_fills: bool = False
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_grant_capital: bool = False
    can_close_position: bool = False

    def __post_init__(self) -> None:
        for name in (
            "label_id", "assessment_id", "family_id", "thesis_id", "run_id",
            "ticker", "contract_symbol", "original_observation_id",
        ):
            value = str(getattr(self, name) or "").strip()
            if not value:
                raise ValueError(f"{name} is required")
            if name in {"ticker", "contract_symbol", "direction"}:
                value = value.upper()
            object.__setattr__(self, name, value)
        direction = str(self.direction or "").strip().upper()
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        if int(self.horizon_sessions) <= 0:
            raise ValueError("horizon_sessions must be positive")
        object.__setattr__(self, "assessment_cutoff_utc", _utc(self.assessment_cutoff_utc, "assessment_cutoff_utc"))
        object.__setattr__(self, "outcome_cutoff_utc", _utc(self.outcome_cutoff_utc, "outcome_cutoff_utc"))
        if self.outcome_cutoff_utc < self.assessment_cutoff_utc:
            raise ValueError("outcome cutoff cannot precede assessment cutoff")
        status = self.data_status if isinstance(self.data_status, OutcomeDataStatus) else OutcomeDataStatus(str(self.data_status))
        object.__setattr__(self, "data_status", status)
        for name in ("option_points_observed", "underlying_points_observed"):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.underlying_points_observed > self.horizon_sessions:
            raise ValueError("underlying_points_observed cannot exceed horizon")
        complete_statuses = {
            OutcomeDataStatus.COMPLETE,
            OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL,
            OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE,
        }
        if status in complete_statuses and self.underlying_points_observed != self.horizon_sessions:
            raise ValueError("completed outcome requires the full underlying horizon")
        if status in complete_statuses and self.horizon_end_session is None:
            raise ValueError("completed outcome requires horizon_end_session")
        if status in {OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE, OutcomeDataStatus.DATA_EXCEPTION} and self.horizon_end_session is not None:
            raise ValueError("non-complete outcome cannot claim a horizon end session")
        if status is OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE and self.underlying_points_observed >= self.horizon_sessions:
            raise ValueError("deferred outcome cannot contain a mature horizon")
        for name in (
            "reference_option_mid", "reference_entry_ask", "terminal_option_mid_return",
            "terminal_executable_return", "option_mark_mfe", "option_mark_mae",
            "option_executable_mfe", "option_executable_mae",
            "underlying_directional_return", "underlying_mfe", "underlying_mae",
            "minimum_spread_fraction", "maximum_volume", "maximum_open_interest",
        ):
            object.__setattr__(self, name, _finite_optional(getattr(self, name), name))
        for name in (
            "first_two_sided_session", "first_spread_15_session",
            "first_spread_25_session", "first_spread_35_session",
            "first_return_hurdle_session", "target_first_hit_session",
            "invalidation_first_hit_session",
        ):
            value = getattr(self, name)
            if value is not None and int(value) < 1:
                raise ValueError(f"{name} must be positive when supplied")
        object.__setattr__(self, "source_option_observation_ids", _unique(self.source_option_observation_ids))
        object.__setattr__(self, "source_option_dataset_ids", _unique(self.source_option_dataset_ids))
        object.__setattr__(self, "source_underlying_dataset_ids", _unique(self.source_underlying_dataset_ids))
        object.__setattr__(self, "data_gap_reasons", _unique(item.upper() for item in self.data_gap_reasons))
        if self.option_points_observed != len(self.source_option_observation_ids):
            raise ValueError("option point count must reconcile to source observations")
        if self.option_points_observed > self.underlying_points_observed:
            raise ValueError("option path cannot exceed the completed underlying horizon")
        if self.outcome_kind != DOI_OUTCOME_KIND or not self.is_counterfactual or self.uses_realised_fills:
            raise ValueError("DOI labels must remain hypothetical market outcomes without realised fills")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("DOI outcomes have no decision authority")
        if self.can_change_direction or self.can_grant_capital or self.can_close_position:
            raise ValueError("DOI outcomes cannot possess trading authority")

    @classmethod
    def create(cls, **values: Any) -> "DOIOutcomeLabel":
        return cls(
            label_id=outcome_label_identity(
                assessment_id=values["assessment_id"],
                horizon_sessions=values["horizon_sessions"],
                outcome_cutoff_utc=values["outcome_cutoff_utc"],
                calculation_version=values.get("calculation_version") or DOI_OUTCOME_CALCULATION_VERSION,
                data_status=values["data_status"],
            ),
            **values,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["assessment_cutoff_utc"] = self.assessment_cutoff_utc.isoformat()
        payload["outcome_cutoff_utc"] = self.outcome_cutoff_utc.isoformat()
        payload["horizon_end_session"] = self.horizon_end_session.isoformat() if self.horizon_end_session else None
        payload["data_status"] = self.data_status.value
        for name in (
            "source_option_observation_ids", "source_option_dataset_ids",
            "source_underlying_dataset_ids", "data_gap_reasons",
        ):
            payload[name] = list(payload[name])
        payload["domain_version"] = DOI_OUTCOME_DOMAIN_VERSION
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DOIOutcomeLabel":
        values = dict(payload)
        values.pop("domain_version", None)
        values["assessment_cutoff_utc"] = datetime.fromisoformat(str(values["assessment_cutoff_utc"]).replace("Z", "+00:00"))
        values["outcome_cutoff_utc"] = datetime.fromisoformat(str(values["outcome_cutoff_utc"]).replace("Z", "+00:00"))
        values["horizon_end_session"] = date.fromisoformat(values["horizon_end_session"]) if values.get("horizon_end_session") else None
        values["data_status"] = OutcomeDataStatus(values["data_status"])
        return cls(**values)


def outcome_label_identity(
    *,
    assessment_id: str,
    horizon_sessions: int,
    outcome_cutoff_utc: datetime,
    calculation_version: str,
    data_status: OutcomeDataStatus | str,
) -> str:
    identity = {
        "assessment_id": str(assessment_id).strip(),
        "horizon_sessions": int(horizon_sessions),
        "outcome_cutoff_utc": _utc(outcome_cutoff_utc, "outcome_cutoff_utc").isoformat(),
        "calculation_version": str(calculation_version).strip(),
        "data_status": str(getattr(data_status, "value", data_status)),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"DOI_OUTCOME_LABEL_V1|{encoded}".encode()).hexdigest()


def _validated_future_paths(
    *,
    assessment_cutoff_utc: datetime,
    evaluation_cutoff_utc: datetime,
    contract_symbol: str,
    option_path: Iterable[OptionPathObservation],
    underlying_path: Iterable[UnderlyingPathObservation],
) -> tuple[list[OptionPathObservation], list[UnderlyingPathObservation]]:
    origin = _utc(assessment_cutoff_utc, "assessment_cutoff_utc")
    cutoff = _utc(evaluation_cutoff_utc, "evaluation_cutoff_utc")
    if cutoff < origin:
        raise OutcomeLeakageError("evaluation cutoff precedes assessment cutoff")
    options = list(option_path)
    underlyings = list(underlying_path)
    for point in options:
        if point.contract_symbol != contract_symbol.upper():
            raise ValueError("option path changed exact contract identity")
        if point.session_date <= origin.date() or point.quote_at_utc <= origin:
            raise OutcomeLeakageError("option path includes evidence at or before assessment cutoff")
        if point.available_at_utc > cutoff:
            raise OutcomeLeakageError("option path includes evidence unavailable at evaluation cutoff")
    for point in underlyings:
        if point.session_date <= origin.date():
            raise OutcomeLeakageError("underlying path includes assessment-session or earlier evidence")
        if point.available_at_utc > cutoff:
            raise OutcomeLeakageError("underlying path includes evidence unavailable at evaluation cutoff")
    option_by_session: dict[date, OptionPathObservation] = {}
    for point in sorted(options, key=lambda item: (item.session_date, item.quote_at_utc, item.observation_id)):
        option_by_session[point.session_date] = point
    underlying_by_session: dict[date, UnderlyingPathObservation] = {}
    for point in sorted(underlyings, key=lambda item: (item.session_date, item.available_at_utc, item.dataset_id)):
        if point.session_date in underlying_by_session:
            raise ValueError("underlying path contains duplicate completed session")
        underlying_by_session[point.session_date] = point
    return list(option_by_session.values()), list(underlying_by_session.values())


def _first_session(values: Sequence[tuple[int, bool]]) -> int | None:
    return next((index for index, matched in values if matched), None)


def evaluate_assessment_outcome(
    *,
    assessment_id: str,
    family_id: str,
    thesis_id: str,
    run_id: str,
    ticker: str,
    contract_symbol: str,
    original_observation_id: str,
    direction: str,
    assessment_cutoff_utc: datetime,
    evaluation_cutoff_utc: datetime,
    horizon_sessions: int,
    reference_spot: float,
    reference_bid: float | None,
    reference_ask: float | None,
    target_spot: float | None,
    invalidation_spot: float | None,
    option_path: Iterable[OptionPathObservation],
    underlying_path: Iterable[UnderlyingPathObservation],
    policy: OutcomeLabelPolicy = OutcomeLabelPolicy(),
) -> DOIOutcomeLabel:
    """Build one point-in-time, no-lookahead label for an exact assessment."""

    horizon = int(horizon_sessions)
    if horizon <= 0:
        raise ValueError("horizon_sessions must be positive")
    reference_spot = float(reference_spot)
    if not math.isfinite(reference_spot) or reference_spot <= 0:
        raise ValueError("reference_spot must be positive and finite")
    bid = _finite_optional(reference_bid, "reference_bid")
    ask = _finite_optional(reference_ask, "reference_ask")
    if bid is not None and bid < 0 or ask is not None and ask < 0:
        raise ValueError("reference quote cannot be negative")
    if bid is not None and ask is not None and ask < bid:
        raise ValueError("reference ask cannot be below bid")
    options, underlyings = _validated_future_paths(
        assessment_cutoff_utc=assessment_cutoff_utc,
        evaluation_cutoff_utc=evaluation_cutoff_utc,
        contract_symbol=contract_symbol,
        option_path=option_path,
        underlying_path=underlying_path,
    )
    observed_underlyings = underlyings[:horizon]
    complete = len(observed_underlyings) == horizon
    horizon_dates = {point.session_date for point in observed_underlyings}
    observed_options = [point for point in options if point.session_date in horizon_dates]
    option_session_number = {
        point.session_date: index for index, point in enumerate(observed_underlyings, 1)
    }
    indexed_options = [
        (option_session_number[point.session_date], point) for point in observed_options
    ]

    reference_mid = (bid + ask) / 2.0 if bid is not None and ask is not None and ask > 0 else None
    reference_entry_ask = ask if ask is not None and ask > 0 else None
    mark_returns = [
        (index, point.mark / reference_mid - 1.0)
        for index, point in indexed_options
        if point.mark is not None and reference_mid is not None
    ]
    executable_returns = [
        (index, point.bid / reference_entry_ask - 1.0)
        for index, point in indexed_options
        if point.two_sided and point.bid is not None and reference_entry_ask is not None
    ]
    spreads = [(index, point.spread_fraction) for index, point in indexed_options if point.spread_fraction is not None]
    two_sided = [(index, point.two_sided) for index, point in indexed_options]
    first_spreads = {
        milestone: _first_session((index, spread <= milestone) for index, spread in spreads)
        for milestone in policy.spread_milestones
    }

    if complete:
        directional = evaluate_outcome_path(
            direction=direction,
            reference_price=reference_spot,
            future_bars=(
                {"high": point.high, "low": point.low, "close": point.close}
                for point in observed_underlyings
            ),
            horizon_sessions=horizon,
            target_price=target_spot,
            invalidation_price=invalidation_spot,
        )
        outcome_cutoff = observed_underlyings[-1].available_at_utc
        horizon_end = observed_underlyings[-1].session_date
    else:
        directional = evaluate_outcome_path(
            direction=direction,
            reference_price=reference_spot,
            future_bars=(
                {"high": point.high, "low": point.low, "close": point.close}
                for point in observed_underlyings
            ),
            horizon_sessions=horizon,
            target_price=target_spot,
            invalidation_price=invalidation_spot,
        )
        outcome_cutoff = _utc(evaluation_cutoff_utc, "evaluation_cutoff_utc")
        horizon_end = None

    gaps: list[str] = []
    if not complete:
        status = OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE
        gaps.append("UNDERLYING_HORIZON_NOT_MATURE")
    elif not observed_options:
        status = OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL
        gaps.append("NO_FUTURE_EXACT_CONTRACT_OBSERVATIONS")
    elif len(observed_options) < horizon:
        status = OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL
        gaps.append("EXACT_CONTRACT_SESSION_GAPS")
    elif reference_mid is None or reference_entry_ask is None:
        status = OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE
        gaps.append("REFERENCE_OPTION_QUOTE_INSUFFICIENT")
    else:
        status = OutcomeDataStatus.COMPLETE
    if observed_options and not mark_returns:
        gaps.append("OPTION_MARK_RETURN_UNAVAILABLE")
    if observed_options and not executable_returns:
        gaps.append("EXECUTABLE_RETURN_UNAVAILABLE")

    return DOIOutcomeLabel.create(
        assessment_id=assessment_id,
        family_id=family_id,
        thesis_id=thesis_id,
        run_id=run_id,
        ticker=ticker,
        contract_symbol=contract_symbol,
        original_observation_id=original_observation_id,
        direction=direction,
        horizon_sessions=horizon,
        assessment_cutoff_utc=assessment_cutoff_utc,
        outcome_cutoff_utc=outcome_cutoff,
        horizon_end_session=horizon_end,
        data_status=status,
        option_points_observed=len(observed_options),
        underlying_points_observed=len(observed_underlyings),
        reference_option_mid=reference_mid,
        reference_entry_ask=reference_entry_ask,
        terminal_option_mid_return=mark_returns[-1][1] if mark_returns else None,
        terminal_executable_return=executable_returns[-1][1] if executable_returns else None,
        option_mark_mfe=max((value for _, value in mark_returns), default=None),
        option_mark_mae=min((value for _, value in mark_returns), default=None),
        option_executable_mfe=max((value for _, value in executable_returns), default=None),
        option_executable_mae=min((value for _, value in executable_returns), default=None),
        underlying_directional_return=directional.directional_return,
        underlying_mfe=directional.mfe,
        underlying_mae=directional.mae,
        first_two_sided_session=_first_session(two_sided),
        first_spread_15_session=first_spreads.get(0.15),
        first_spread_25_session=first_spreads.get(0.25),
        first_spread_35_session=first_spreads.get(0.35),
        first_return_hurdle_session=_first_session(
            (index, value >= policy.return_hurdle) for index, value in executable_returns
        ),
        target_first_hit_session=directional.target_first_hit_session,
        invalidation_first_hit_session=directional.stop_first_hit_session,
        first_passage_state=directional.first_passage_state,
        minimum_spread_fraction=min((value for _, value in spreads), default=None),
        maximum_volume=max((point.volume for point in observed_options if point.volume is not None), default=None),
        maximum_open_interest=max((point.open_interest for point in observed_options if point.open_interest is not None), default=None),
        source_option_observation_ids=tuple(point.observation_id for point in observed_options),
        source_option_dataset_ids=tuple(point.dataset_id for point in observed_options),
        source_underlying_dataset_ids=tuple(point.dataset_id for point in observed_underlyings),
        data_gap_reasons=tuple(gaps),
        calculation_version=policy.calculation_version,
    )


@dataclass(frozen=True, slots=True)
class ChronologicalOutcomeCohorts:
    training: tuple[DOIOutcomeLabel, ...]
    validation: tuple[DOIOutcomeLabel, ...]
    holdout: tuple[DOIOutcomeLabel, ...]
    excluded_boundary_overlap: tuple[DOIOutcomeLabel, ...]


def chronological_outcome_cohorts(
    labels: Iterable[DOIOutcomeLabel],
    *,
    training_cutoff_utc: datetime,
    validation_cutoff_utc: datetime,
) -> ChronologicalOutcomeCohorts:
    """Partition labels without allowing outcome windows to cross split cutoffs."""

    train_cutoff = _utc(training_cutoff_utc, "training_cutoff_utc")
    validation_cutoff = _utc(validation_cutoff_utc, "validation_cutoff_utc")
    if validation_cutoff <= train_cutoff:
        raise ValueError("validation cutoff must follow training cutoff")
    training: list[DOIOutcomeLabel] = []
    validation: list[DOIOutcomeLabel] = []
    holdout: list[DOIOutcomeLabel] = []
    overlap: list[DOIOutcomeLabel] = []
    for label in sorted(labels, key=lambda item: (item.assessment_cutoff_utc, item.label_id)):
        if label.data_status in {
            OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE,
            OutcomeDataStatus.DATA_EXCEPTION,
        }:
            continue
        if label.outcome_cutoff_utc <= train_cutoff:
            training.append(label)
        elif label.assessment_cutoff_utc <= train_cutoff < label.outcome_cutoff_utc:
            overlap.append(label)
        elif label.outcome_cutoff_utc <= validation_cutoff:
            validation.append(label)
        elif label.assessment_cutoff_utc <= validation_cutoff < label.outcome_cutoff_utc:
            overlap.append(label)
        else:
            holdout.append(label)
    if training and validation:
        if max(item.outcome_cutoff_utc for item in training) > min(item.assessment_cutoff_utc for item in validation):
            raise OutcomeLeakageError("training outcomes overlap validation feature time")
    return ChronologicalOutcomeCohorts(tuple(training), tuple(validation), tuple(holdout), tuple(overlap))


__all__ = [
    "DOI_OUTCOME_CALCULATION_VERSION", "DOI_OUTCOME_DOMAIN_VERSION",
    "DOI_OUTCOME_KIND", "ChronologicalOutcomeCohorts", "DOIOutcomeLabel",
    "OptionPathObservation", "OutcomeDataStatus", "OutcomeLabelPolicy",
    "OutcomeLeakageError", "UnderlyingPathObservation",
    "chronological_outcome_cohorts", "evaluate_assessment_outcome",
    "outcome_label_identity",
]
