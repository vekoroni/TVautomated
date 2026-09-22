"""DOI-7 application service for point-in-time contract outcome labels.

The service consumes already-governed observations supplied by callers.  It
performs no provider calls and stores labels in the existing append-only option
lifecycle control plane.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Iterable

from domain.dynamic_options_intelligence import ContractAssessment
from domain.dynamic_options_outcomes import (
    DOI_OUTCOME_CALCULATION_VERSION,
    DOIOutcomeLabel,
    OptionPathObservation,
    OutcomeDataStatus,
    OutcomeLabelPolicy,
    UnderlyingPathObservation,
    evaluate_assessment_outcome,
    outcome_label_identity,
)

from .option_liquidity_lifecycle import (
    ContractObservation,
    OptionLiquidityLifecycleStore,
)


DOI_OUTCOME_CAPTURE_SERVICE_VERSION = "doi-outcome-capture-service-v1"
DEFAULT_DOI_OUTCOME_HORIZONS = (1, 5, 10, 20)


def _content_without_lineage(label: DOIOutcomeLabel) -> dict[str, Any]:
    payload = label.to_dict()
    for field in ("label_id", "calculation_version", "supersedes_label_id", "correction_reason"):
        payload.pop(field, None)
    return payload


def _corrected_label(draft: DOIOutcomeLabel, predecessor: DOIOutcomeLabel) -> DOIOutcomeLabel:
    content = _content_without_lineage(draft)
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    version = f"{DOI_OUTCOME_CALCULATION_VERSION}:CANONICAL_REVISION:{digest}"
    return replace(
        draft,
        label_id=outcome_label_identity(
            assessment_id=draft.assessment_id,
            horizon_sessions=draft.horizon_sessions,
            outcome_cutoff_utc=draft.outcome_cutoff_utc,
            calculation_version=version,
            data_status=draft.data_status,
        ),
        calculation_version=version,
        supersedes_label_id=predecessor.label_id,
        correction_reason="CANONICAL_PATH_REVISION",
    )


@dataclass(frozen=True, slots=True)
class OutcomeCaptureSummary:
    family_id: str
    assessments: int
    expected_labels: int
    labels_built: int
    labels_appended: int
    labels_reused: int
    complete: int
    option_path_partial: int
    option_return_unavailable: int
    deferred: int
    data_exceptions: int
    call_assessments: int
    put_assessments: int
    provider_calls: int
    reconciled: bool
    errors: tuple[str, ...]
    retained_prior_on_reader_error: int = 0
    decision_authority: str = "NONE"
    can_grant_capital: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OutcomeCaptureResult:
    labels: tuple[DOIOutcomeLabel, ...]
    summary: OutcomeCaptureSummary


def option_path_from_observations(
    observations: Iterable[ContractObservation],
) -> tuple[OptionPathObservation, ...]:
    """Adapt persisted exact-contract observations without changing evidence."""

    return tuple(
        OptionPathObservation(
            observation_id=item.observation_id,
            dataset_id=item.source_dataset_id,
            contract_symbol=item.contract_symbol,
            session_date=item.quote_as_of.date(),
            quote_at_utc=item.quote_as_of,
            available_at_utc=item.observed_at,
            bid=item.bid,
            ask=item.ask,
            volume=item.volume,
            open_interest=item.open_interest,
            implied_volatility=item.iv,
        )
        for item in observations
    )


def _exception_label(
    *,
    assessment: ContractAssessment,
    family: Any,
    evaluation_cutoff_utc: datetime,
    horizon_sessions: int,
    reason: str,
) -> DOIOutcomeLabel:
    return DOIOutcomeLabel.create(
        assessment_id=assessment.assessment_id,
        family_id=assessment.family_id,
        thesis_id=assessment.thesis_id,
        run_id=assessment.run_id,
        ticker=family.thesis.ticker,
        contract_symbol=assessment.contract_symbol,
        original_observation_id=assessment.observation_id,
        direction=family.thesis.governed_direction,
        horizon_sessions=horizon_sessions,
        assessment_cutoff_utc=assessment.evidence_cutoff_utc,
        outcome_cutoff_utc=evaluation_cutoff_utc,
        horizon_end_session=None,
        data_status=OutcomeDataStatus.DATA_EXCEPTION,
        option_points_observed=0,
        underlying_points_observed=0,
        reference_option_mid=None,
        reference_entry_ask=None,
        terminal_option_mid_return=None,
        terminal_executable_return=None,
        option_mark_mfe=None,
        option_mark_mae=None,
        option_executable_mfe=None,
        option_executable_mae=None,
        underlying_directional_return=None,
        underlying_mfe=None,
        underlying_mae=None,
        first_two_sided_session=None,
        first_spread_15_session=None,
        first_spread_25_session=None,
        first_spread_35_session=None,
        first_return_hurdle_session=None,
        target_first_hit_session=None,
        invalidation_first_hit_session=None,
        first_passage_state="NOT_EVALUATED_DATA_EXCEPTION",
        minimum_spread_fraction=None,
        maximum_volume=None,
        maximum_open_interest=None,
        source_option_observation_ids=(),
        source_option_dataset_ids=(),
        source_underlying_dataset_ids=(),
        data_gap_reasons=(reason,),
        calculation_version=DOI_OUTCOME_CALCULATION_VERSION,
    )


class DynamicOptionsOutcomeCaptureService:
    """Capture labels for every assessment while preserving candidate coverage."""

    def __init__(
        self,
        store: OptionLiquidityLifecycleStore,
        *,
        policy: OutcomeLabelPolicy = OutcomeLabelPolicy(),
    ) -> None:
        self.store = store
        self.policy = policy

    def capture_family(
        self,
        *,
        family_id: str,
        evaluation_cutoff_utc: datetime,
        read_option_path: Callable[[ContractAssessment], Iterable[OptionPathObservation]],
        read_underlying_path: Callable[[ContractAssessment], Iterable[UnderlyingPathObservation]],
        horizons: Iterable[int] = DEFAULT_DOI_OUTCOME_HORIZONS,
    ) -> OutcomeCaptureResult:
        cutoff = evaluation_cutoff_utc
        if cutoff.tzinfo is None:
            raise ValueError("evaluation_cutoff_utc must be timezone-aware")
        cutoff = cutoff.astimezone(timezone.utc)
        horizon_values = tuple(sorted({int(item) for item in horizons}))
        if not horizon_values or horizon_values[0] <= 0:
            raise ValueError("outcome horizons must be positive")
        family = self.store.contract_family(family_id)
        if family is None:
            raise ValueError("DOI contract family does not exist")
        assessments = self.store.assessments_for_family(family_id)
        labels: list[DOIOutcomeLabel] = []
        errors: list[str] = []
        appended = reused = retained_prior = 0

        underlying_cache: dict[str, tuple[UnderlyingPathObservation, ...]] = {}
        for assessment in assessments:
            origin = self.store.contract_observation(assessment.observation_id)
            origin_dataset = (
                self.store.registry.get_dataset(origin.source_dataset_id)
                if origin is not None else None
            )
            if origin is None:
                path_error: Exception | None = ValueError("ORIGIN_OBSERVATION_NOT_FOUND")
                option_path: tuple[OptionPathObservation, ...] = ()
                underlying_path: tuple[UnderlyingPathObservation, ...] = ()
            elif origin_dataset is None:
                path_error = ValueError("ORIGIN_DATASET_NOT_FOUND")
                option_path = ()
                underlying_path = ()
            else:
                path_error = None
                try:
                    option_path = tuple(read_option_path(assessment))
                    if assessment.thesis_id not in underlying_cache:
                        underlying_cache[assessment.thesis_id] = tuple(
                            read_underlying_path(assessment)
                        )
                    underlying_path = underlying_cache[assessment.thesis_id]
                except Exception as error:  # one contract must not abort the family
                    path_error = error
                    option_path = ()
                    underlying_path = ()

            for horizon in horizon_values:
                try:
                    if path_error is not None or origin is None:
                        label = _exception_label(
                            assessment=assessment,
                            family=family,
                            evaluation_cutoff_utc=cutoff,
                            horizon_sessions=horizon,
                            reason=f"PATH_READ_FAILED:{type(path_error).__name__.upper()}",
                        )
                    else:
                        label = evaluate_assessment_outcome(
                            assessment_id=assessment.assessment_id,
                            family_id=assessment.family_id,
                            thesis_id=assessment.thesis_id,
                            run_id=assessment.run_id,
                            ticker=family.thesis.ticker,
                            contract_symbol=assessment.contract_symbol,
                            original_observation_id=assessment.observation_id,
                            direction=family.thesis.governed_direction,
                            assessment_cutoff_utc=assessment.evidence_cutoff_utc,
                            assessment_session_date=origin_dataset.session_date,
                            evaluation_cutoff_utc=cutoff,
                            horizon_sessions=horizon,
                            reference_spot=origin.spot,
                            reference_bid=origin.bid,
                            reference_ask=origin.ask,
                            target_spot=family.thesis.target_spot,
                            invalidation_spot=family.thesis.invalidation_spot,
                            option_path=option_path,
                            underlying_path=underlying_path,
                            policy=self.policy,
                        )
                    previous = self.store.latest_outcome_label(
                        assessment_id=assessment.assessment_id,
                        horizon_sessions=horizon,
                    )
                    if previous is not None:
                        if (
                            previous.data_status is OutcomeDataStatus.COMPLETE
                            and label.data_status in {
                                OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL,
                                OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE,
                            }
                            and set(label.source_option_observation_ids)
                            < set(previous.source_option_observation_ids)
                            and set(label.source_underlying_dataset_ids).issubset(
                                previous.source_underlying_dataset_ids
                            )
                        ):
                            # Canonical observations are immutable. A reader that
                            # returns a strict subset of an already complete path
                            # has not established a correction to that path.
                            labels.append(previous)
                            reused += 1
                            retained_prior += 1
                            continue
                        if (
                            label.data_status is OutcomeDataStatus.DATA_EXCEPTION
                            and previous.data_status in {
                                OutcomeDataStatus.COMPLETE,
                                OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL,
                                OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE,
                            }
                        ):
                            # A transient read failure cannot revoke a valid
                            # immutable observation already on record.
                            labels.append(previous)
                            reused += 1
                            retained_prior += 1
                            continue
                        if _content_without_lineage(previous) == _content_without_lineage(label):
                            labels.append(previous)
                            reused += 1
                            continue
                        label = _corrected_label(label, previous)
                    persisted = self.store.record_doi_outcome_label(label)
                    labels.append(persisted.record)
                    if persisted.reused_existing:
                        reused += 1
                    else:
                        appended += 1
                except Exception as error:
                    errors.append(
                        f"{assessment.assessment_id}:{horizon}:{type(error).__name__}:{error}"
                    )

        counts = {status: 0 for status in OutcomeDataStatus}
        for label in labels:
            counts[label.data_status] += 1
        expected = len(assessments) * len(horizon_values)
        summary = OutcomeCaptureSummary(
            family_id=family.family_id,
            assessments=len(assessments),
            expected_labels=expected,
            labels_built=len(labels),
            labels_appended=appended,
            labels_reused=reused,
            complete=counts[OutcomeDataStatus.COMPLETE],
            option_path_partial=counts[OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL],
            option_return_unavailable=counts[OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE],
            deferred=counts[OutcomeDataStatus.DEFERRED_NOT_YET_OBSERVABLE],
            data_exceptions=counts[OutcomeDataStatus.DATA_EXCEPTION] + len(errors),
            call_assessments=(len(assessments) if family.thesis.governed_direction == "CALL" else 0),
            put_assessments=(len(assessments) if family.thesis.governed_direction == "PUT" else 0),
            provider_calls=0,
            reconciled=len(labels) + len(errors) == expected,
            errors=tuple(errors),
            retained_prior_on_reader_error=retained_prior,
        )
        return OutcomeCaptureResult(tuple(labels), summary)


__all__ = [
    "DEFAULT_DOI_OUTCOME_HORIZONS", "DOI_OUTCOME_CAPTURE_SERVICE_VERSION",
    "DynamicOptionsOutcomeCaptureService", "OutcomeCaptureResult",
    "OutcomeCaptureSummary", "option_path_from_observations",
]
