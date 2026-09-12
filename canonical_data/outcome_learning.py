"""Stage 6 application service for replayable outcome-learning snapshots."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from domain.decision_outcome import LedgerEvent
from domain.outcome_learning import (
    CompetingEventLabel,
    LearningActivationPolicy,
    OutcomeLearningRecord,
    assess_model_activation,
    attribute_outcome,
    competing_event_label,
    hold_bucket,
)

from .decision_outcome_ledger import DecisionOutcomeLedger


STAGE6_OUTCOME_HORIZONS = (1, 2, 3, 5, 10, 20)
OUTCOME_LEARNING_SNAPSHOT_VERSION = "outcome_learning_snapshot_v1"


@dataclass(frozen=True, slots=True)
class TemporalPartitionPlan:
    state: str
    training_record_ids: tuple[str, ...]
    validation_record_ids: tuple[str, ...]
    test_record_ids: tuple[str, ...]
    excluded_embargo_record_ids: tuple[str, ...]
    excluded_boundary_overlap_record_ids: tuple[str, ...]
    training_cutoff_session: str | None
    validation_cutoff_session: str | None
    purge_embargo_sessions: int

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for field in (
            "training_record_ids", "validation_record_ids", "test_record_ids",
            "excluded_embargo_record_ids", "excluded_boundary_overlap_record_ids",
        ):
            result[field] = list(result[field])
        return result


def build_temporal_partition_plan(
    records: Iterable[OutcomeLearningRecord],
    *,
    purge_embargo_sessions: int,
) -> TemporalPartitionPlan:
    """Create date-ordered 70/15/15 cohorts without label-window leakage."""

    items = tuple(sorted(records, key=lambda item: (item.decision_session, item.record_id)))
    sessions = sorted({item.decision_session for item in items if item.decision_session})
    purge = int(purge_embargo_sessions)
    if purge < 0:
        raise ValueError("purge_embargo_sessions cannot be negative")
    if len(sessions) < 3:
        return TemporalPartitionPlan(
            "INSUFFICIENT_SESSIONS", (), (), (), (), (), None, None, purge
        )
    train_boundary = max(1, int(len(sessions) * 0.70))
    validation_boundary = max(train_boundary + 1, int(len(sessions) * 0.85))
    validation_start = train_boundary + purge
    test_start = validation_boundary + purge
    if validation_start >= validation_boundary or test_start >= len(sessions):
        return TemporalPartitionPlan(
            "INSUFFICIENT_SESSIONS_FOR_PURGED_PARTITIONS", (), (), (),
            tuple(item.record_id for item in items), (),
            sessions[min(train_boundary - 1, len(sessions) - 1)],
            sessions[min(validation_boundary - 1, len(sessions) - 1)], purge,
        )
    index = {session: position for position, session in enumerate(sessions)}
    first_validation_session = sessions[validation_start]
    first_test_session = sessions[test_start]
    training: list[str] = []
    validation: list[str] = []
    test: list[str] = []
    embargo: list[str] = []
    overlap: list[str] = []
    for item in items:
        position = index[item.decision_session]
        outcome_session = item.outcome_cutoff_utc[:10]
        if position < train_boundary:
            if outcome_session >= first_validation_session:
                overlap.append(item.record_id)
            else:
                training.append(item.record_id)
        elif position < validation_start:
            embargo.append(item.record_id)
        elif position < validation_boundary:
            if outcome_session >= first_test_session:
                overlap.append(item.record_id)
            else:
                validation.append(item.record_id)
        elif position < test_start:
            embargo.append(item.record_id)
        else:
            test.append(item.record_id)
    state = "READY" if training and validation and test else "INSUFFICIENT_PARTITION_SUPPORT"
    return TemporalPartitionPlan(
        state, tuple(training), tuple(validation), tuple(test), tuple(embargo),
        tuple(overlap), sessions[train_boundary - 1],
        sessions[validation_boundary - 1], purge,
    )


def learning_policy_from_config(path: Path | str) -> LearningActivationPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    values = dict(payload.get("outcome_learning") or {})
    if not values:
        raise ValueError("governed outcome_learning configuration is missing")
    return LearningActivationPolicy(
        model_activation_enabled=bool(values.get("model_activation_enabled", False)),
        minimum_fit_outcomes=int(values["minimum_fit_outcomes"]),
        minimum_stratum_outcomes=int(values["minimum_stratum_outcomes"]),
        minimum_coverage=float(values["minimum_coverage"]),
        maximum_overall_ece=float(values["maximum_overall_ece"]),
        maximum_stratum_ece=float(values["maximum_stratum_ece"]),
        require_positive_brier_skill=bool(values["require_positive_brier_skill"]),
        require_target_roc_auc_above=float(values["require_target_roc_auc_above"]),
        require_target_pr_auc_above_base_rate=bool(
            values["require_target_pr_auc_above_base_rate"]
        ),
        require_top_quintile_lift_above=float(
            values["require_top_quintile_lift_above"]
        ),
        purge_embargo_sessions=int(values["purge_embargo_sessions"]),
        policy_version=str(values.get("version") or "outcome_learning_gate_v1"),
    )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: Any) -> int | None:
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        return None
    return result


def _dataset_ids(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = [part.strip() for part in raw.split("|")]
    if isinstance(value, Mapping):
        value = tuple(value.values())
    if not isinstance(value, (list, tuple, set)):
        value = (value,)
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


def load_option_outcome_lookup(
    control_plane_path: Path | str | None,
) -> dict[tuple[str, int], Mapping[str, Any]]:
    """Read already-canonical DOI labels; never fetch or infer option history."""

    if control_plane_path is None:
        return {}
    path = Path(control_plane_path)
    if not path.is_file():
        return {}
    lookup: dict[tuple[str, int], Mapping[str, Any]] = {}
    try:
        with sqlite3.connect(path) as connection:
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='doi_outcome_labels'"
            ).fetchone()
            if not present:
                return {}
            rows = connection.execute(
                "SELECT assessment_id,horizon_sessions,payload_json "
                "FROM doi_outcome_labels ORDER BY outcome_cutoff_utc,label_id"
            ).fetchall()
        for assessment_id, horizon, payload_json in rows:
            lookup[(str(assessment_id), int(horizon))] = json.loads(payload_json)
    except (OSError, sqlite3.Error, json.JSONDecodeError):
        return {}
    return lookup


def _learning_record(
    candidate: LedgerEvent,
    outcome: LedgerEvent,
    *,
    option_lookup: Mapping[tuple[str, int], Mapping[str, Any]],
) -> OutcomeLearningRecord:
    candidate_payload = candidate.payload
    outcome_payload = outcome.payload
    horizon = int(outcome_payload.get("horizon_sessions") or 0)
    label = competing_event_label(str(outcome_payload.get("first_passage_state")))
    assessment_id = str(
        candidate_payload.get("preferred_assessment_id") or ""
    ).strip() or None
    option = dict(option_lookup.get((assessment_id or "", horizon), {}))
    option_status = str(option.get("data_status") or "UNDERLYING_ONLY").upper()
    option_return = option.get("terminal_executable_return")
    option_mfe = option.get("option_executable_mfe")
    option_mae = option.get("option_executable_mae")
    first_two_sided = _optional_int(option.get("first_two_sided_session"))
    family_outperformance = "NOT_EVALUATED"
    family_id = str(option.get("family_id") or "").strip()
    preferred_return = (
        float(option_return) if option_return is not None else None
    )
    if family_id and preferred_return is not None:
        alternatives = []
        for candidate_option in option_lookup.values():
            if (
                str(candidate_option.get("family_id") or "") == family_id
                and int(candidate_option.get("horizon_sessions") or 0) == horizon
                and candidate_option.get("terminal_executable_return") is not None
            ):
                alternatives.append(float(candidate_option["terminal_executable_return"]))
        if alternatives:
            family_outperformance = (
                "OUTPERFORMED_BY_ALTERNATIVE"
                if max(alternatives) > preferred_return else "PREFERRED_BEST_OBSERVED"
            )
    baseline_eligible = _as_bool(candidate_payload.get("baseline_eligible"))
    planned_hold = _optional_int(candidate_payload.get("planned_hold_sessions"))
    exclusions: list[str] = []
    if not baseline_eligible:
        exclusions.append(
            str(candidate_payload.get("baseline_ineligibility_reason") or "BASELINE_INELIGIBLE").upper()
        )
    if hold_bucket(planned_hold) == "UNAVAILABLE":
        exclusions.append("PLANNED_HOLD_UNAVAILABLE")
    if label is CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER:
        exclusions.append("AMBIGUOUS_TOUCH_ORDER")
    run_condition = str(candidate_payload.get("run_condition") or "").upper()
    if run_condition and run_condition != "NORMAL_COMPLETED_SESSION":
        exclusions.append(f"RUN_CONDITION_{run_condition}")
    source_ids = set(_dataset_ids(candidate_payload.get("evidence_dataset_ids")))
    source_ids.update(_dataset_ids(option.get("source_option_dataset_ids")))
    source_ids.update(_dataset_ids(option.get("source_underlying_dataset_ids")))
    attribution = attribute_outcome(
        label=label,
        option_data_status=option_status,
        terminal_option_return=option_return,
        first_two_sided_session=first_two_sided,
    )
    return OutcomeLearningRecord.create(
        candidate_event_id=candidate.event_id,
        outcome_event_id=outcome.event_id,
        run_id=candidate.run_id,
        ticker=candidate.ticker,
        thesis_id=candidate.thesis_id,
        preferred_assessment_id=assessment_id,
        direction=str(candidate_payload.get("direction") or "").upper(),
        decision_session=str(candidate_payload.get("completed_session") or "")[:10],
        planned_hold_sessions=planned_hold,
        hold_bucket=hold_bucket(planned_hold),
        horizon_sessions=horizon,
        hidden_state_label=str(candidate_payload.get("hidden_state_label") or "UNAVAILABLE").upper(),
        phase=str(candidate_payload.get("phase") or "UNAVAILABLE").upper(),
        compression_bucket=str(candidate_payload.get("compression_bucket") or "UNAVAILABLE").upper(),
        competing_event_label=label,
        underlying_directional_return=outcome_payload.get("directional_return"),
        underlying_mfe=outcome_payload.get("mfe"),
        underlying_mae=outcome_payload.get("mae"),
        option_data_status=option_status,
        terminal_option_return=option_return,
        option_mfe=option_mfe,
        option_mae=option_mae,
        first_two_sided_session=first_two_sided,
        family_member_outperformance_state=family_outperformance,
        attribution=attribution,
        feature_cutoff_utc=str(
            candidate_payload.get("evidence_cutoff_utc") or candidate.occurred_at_utc
        ),
        outcome_cutoff_utc=outcome.occurred_at_utc,
        baseline_eligible=baseline_eligible,
        fit_eligible=not exclusions,
        exclusion_reasons=tuple(sorted(set(exclusions))),
        source_dataset_ids=tuple(sorted(source_ids)),
    )


def build_outcome_learning_snapshot(
    ledger: DecisionOutcomeLedger,
    *,
    policy: LearningActivationPolicy,
    control_plane_path: Path | str | None = None,
    held_out_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an immutable-view learning dataset from point-in-time ledger facts."""

    candidates = {
        event.event_id: event
        for event in ledger.events_by_type("CANDIDATE_DECISION")
        if str(event.payload.get("decision_stage") or "").upper() == "EOD_THESIS"
    }
    outcomes = tuple(
        event for event in ledger.events_by_type("OUTCOME")
        if event.previous_event_id in candidates
        and event.payload.get("is_counterfactual") is True
    )
    observations = tuple(
        event for event in ledger.events_by_type("OUTCOME_OBSERVATION")
        if event.previous_event_id in candidates
    )
    option_lookup = load_option_outcome_lookup(control_plane_path)
    records: list[OutcomeLearningRecord] = []
    build_exceptions: list[dict[str, str]] = []
    for outcome in outcomes:
        try:
            records.append(
                _learning_record(
                    candidates[outcome.previous_event_id],
                    outcome,
                    option_lookup=option_lookup,
                )
            )
        except Exception as error:
            build_exceptions.append({
                "outcome_event_id": outcome.event_id,
                "reason": f"{type(error).__name__}:{error}",
            })

    latest_observation: dict[tuple[str, int], LedgerEvent] = {}
    for event in observations:
        key = (event.previous_event_id or "", int(event.payload.get("horizon_sessions") or 0))
        prior = latest_observation.get(key)
        if prior is None or event.occurred_at_utc > prior.occurred_at_utc:
            latest_observation[key] = event
    complete_keys = {
        (event.previous_event_id or "", int(event.payload.get("horizon_sessions") or 0))
        for event in outcomes
    }
    data_exception_keys = {
        key for key, event in latest_observation.items()
        if key not in complete_keys and event.payload.get("data_status") == "DATA_EXCEPTION"
    }
    not_yet_keys = {
        key for key, event in latest_observation.items()
        if key not in complete_keys
        and event.payload.get("data_status") == "DEFERRED_NOT_YET_OBSERVABLE"
    }
    expected = len(candidates) * len(STAGE6_OUTCOME_HORIZONS)
    accounted = len(complete_keys) + len(data_exception_keys) + len(not_yet_keys)
    observable = len(complete_keys) + len(data_exception_keys)
    activation = assess_model_activation(
        records,
        expected_observable_outcomes=observable,
        policy=policy,
        held_out_metrics=held_out_metrics,
    )
    label_counts = Counter(record.competing_event_label.value for record in records)
    exclusion_counts = Counter(
        reason for record in records for reason in record.exclusion_reasons
    )
    option_coverage = Counter(record.option_data_status for record in records)
    partition_plan = build_temporal_partition_plan(
        (record for record in records if record.fit_eligible),
        purge_embargo_sessions=policy.purge_embargo_sessions,
    )
    return {
        "schema_version": OUTCOME_LEARNING_SNAPSHOT_VERSION,
        "authority": "OBSERVATION_ONLY",
        "can_grant_capital": False,
        "can_change_direction": False,
        "model_activation": activation.to_dict(),
        "temporal_partition_plan": partition_plan.to_dict(),
        "summary": {
            "presented_candidates": len(candidates),
            "horizons": list(STAGE6_OUTCOME_HORIZONS),
            "expected_candidate_horizons": expected,
            "accounted_candidate_horizons": accounted,
            "complete_outcomes": len(complete_keys),
            "data_exceptions": len(data_exception_keys) + len(build_exceptions),
            "deferred_not_yet_observable": len(not_yet_keys),
            "unaccounted_candidate_horizons": max(0, expected - accounted),
            "population_reconciled": accounted == expected,
            "fit_eligible_records": activation.fit_eligible_records,
            "label_counts": dict(label_counts),
            "exclusion_counts": dict(exclusion_counts),
            "option_coverage_counts": dict(option_coverage),
            "option_labels_available": len(option_lookup),
            "build_exceptions": build_exceptions,
        },
        "records": [record.to_dict() for record in records],
    }


def write_outcome_learning_snapshot(
    destination: Path | str,
    snapshot: Mapping[str, Any],
) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path


__all__ = [
    "OUTCOME_LEARNING_SNAPSHOT_VERSION", "STAGE6_OUTCOME_HORIZONS",
    "TemporalPartitionPlan", "build_temporal_partition_plan",
    "build_outcome_learning_snapshot", "learning_policy_from_config",
    "load_option_outcome_lookup",
    "write_outcome_learning_snapshot",
]
