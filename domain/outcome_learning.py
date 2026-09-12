"""Domain contracts for Stage 6 outcome learning.

The learning context is observational.  It may describe what happened and
whether a calibration cohort is sufficiently evidenced; it can never select a
direction, discard a thesis, grant capital, or activate a model by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


OUTCOME_LEARNING_SCHEMA_VERSION = "outcome_learning_record_v1"
OUTCOME_LEARNING_GATE_VERSION = "outcome_learning_gate_v1"
OUTCOME_LEARNING_AUTHORITY = "OBSERVATION_ONLY"


class CompetingEventLabel(str, Enum):
    TARGET_FIRST = "TARGET_FIRST"
    INVALIDATION_FIRST = "INVALIDATION_FIRST"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS_TOUCH_ORDER = "AMBIGUOUS_TOUCH_ORDER"


class OutcomeAttribution(str, Enum):
    THESIS = "THESIS"
    CONTRACT_CHOICE = "CONTRACT_CHOICE"
    LIQUIDITY = "LIQUIDITY"
    EXECUTION = "EXECUTION"
    VOLATILITY = "VOLATILITY"
    TIMING = "TIMING"
    UNCLASSIFIED_UNCERTAINTY = "UNCLASSIFIED_UNCERTAINTY"


class ModelActivationState(str, Enum):
    INSUFFICIENT_OUTCOMES = "INSUFFICIENT_OUTCOMES"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
    INSUFFICIENT_STRATUM_SUPPORT = "INSUFFICIENT_STRATUM_SUPPORT"
    AWAITING_OUT_OF_SAMPLE_METRICS = "AWAITING_OUT_OF_SAMPLE_METRICS"
    METRIC_GATES_FAILED = "METRIC_GATES_FAILED"
    RELEASE_PROFILE_DISABLED = "RELEASE_PROFILE_DISABLED"
    ELIGIBLE_FOR_OPERATOR_REVIEW = "ELIGIBLE_FOR_OPERATOR_REVIEW"


@dataclass(frozen=True, slots=True)
class LearningStratum:
    hidden_state_label: str
    phase: str
    compression_bucket: str
    direction: str
    hold_bucket: str

    def __post_init__(self) -> None:
        if self.direction not in {"CALL", "PUT"}:
            raise ValueError("learning stratum direction must be CALL or PUT")
        if self.hold_bucket not in {"1-5", "6-10", "11-20"}:
            raise ValueError("learning stratum hold bucket is invalid")

    def backoff_chain(self) -> tuple[Mapping[str, str], ...]:
        """Return the normative lineage; no missing dimension vanishes silently."""

        exact = {
            "hidden_state_label": self.hidden_state_label or "UNAVAILABLE",
            "phase": self.phase or "UNAVAILABLE",
            "compression_bucket": self.compression_bucket or "UNAVAILABLE",
            "direction": self.direction,
            "hold_bucket": self.hold_bucket,
        }
        levels = (
            exact,
            {key: value for key, value in exact.items() if key != "compression_bucket"},
            {key: value for key, value in exact.items() if key not in {"compression_bucket", "phase"}},
            {"direction": self.direction, "hold_bucket": self.hold_bucket},
            {"direction": self.direction},
        )
        return tuple({"match_level": str(index), **level} for index, level in enumerate(levels))


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _identity(namespace: str, value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        f"{namespace}|{_canonical(value)}".encode("utf-8")
    ).hexdigest()


def _finite_optional(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def hold_bucket(hold_sessions: int | None) -> str:
    if hold_sessions is None:
        return "UNAVAILABLE"
    value = int(hold_sessions)
    if not 1 <= value <= 20:
        return "UNAVAILABLE"
    if value <= 5:
        return "1-5"
    if value <= 10:
        return "6-10"
    return "11-20"


def competing_event_label(first_passage_state: str) -> CompetingEventLabel:
    state = str(first_passage_state or "").strip().upper()
    if state in {"TARGET_FIRST", "TARGET_ONLY"}:
        return CompetingEventLabel.TARGET_FIRST
    if state in {"STOP_FIRST", "STOP_ONLY", "INVALIDATION_FIRST"}:
        return CompetingEventLabel.INVALIDATION_FIRST
    if state in {"AMBIGUOUS_SAME_SESSION", "AMBIGUOUS_TOUCH_ORDER"}:
        return CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER
    if state == "NEITHER":
        return CompetingEventLabel.TIMEOUT
    raise ValueError(f"unsupported first-passage state: {first_passage_state}")


def attribute_outcome(
    *,
    label: CompetingEventLabel,
    option_data_status: str,
    terminal_option_return: float | None,
    first_two_sided_session: int | None,
) -> OutcomeAttribution:
    """Make only high-confidence attribution; uncertainty is never guessed."""

    if label is CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER:
        return OutcomeAttribution.UNCLASSIFIED_UNCERTAINTY
    if label is CompetingEventLabel.INVALIDATION_FIRST:
        return OutcomeAttribution.THESIS
    if label is CompetingEventLabel.TIMEOUT:
        return OutcomeAttribution.TIMING
    status = str(option_data_status or "").strip().upper()
    if status in {"UNAVAILABLE", "UNDERLYING_ONLY", "DATA_EXCEPTION"}:
        return OutcomeAttribution.UNCLASSIFIED_UNCERTAINTY
    if first_two_sided_session is None:
        return OutcomeAttribution.LIQUIDITY
    option_return = _finite_optional(terminal_option_return)
    if option_return is not None and option_return <= 0:
        return OutcomeAttribution.CONTRACT_CHOICE
    return OutcomeAttribution.UNCLASSIFIED_UNCERTAINTY


@dataclass(frozen=True, slots=True)
class OutcomeLearningRecord:
    record_id: str
    candidate_event_id: str
    outcome_event_id: str
    run_id: str
    ticker: str
    thesis_id: str
    preferred_assessment_id: str | None
    direction: str
    decision_session: str
    planned_hold_sessions: int | None
    hold_bucket: str
    horizon_sessions: int
    hidden_state_label: str
    phase: str
    compression_bucket: str
    competing_event_label: CompetingEventLabel
    underlying_directional_return: float | None
    underlying_mfe: float | None
    underlying_mae: float | None
    option_data_status: str
    terminal_option_return: float | None
    option_mfe: float | None
    option_mae: float | None
    first_two_sided_session: int | None
    family_member_outperformance_state: str
    attribution: OutcomeAttribution
    feature_cutoff_utc: str
    outcome_cutoff_utc: str
    baseline_eligible: bool
    fit_eligible: bool
    exclusion_reasons: tuple[str, ...]
    source_dataset_ids: tuple[str, ...]
    authority: str = OUTCOME_LEARNING_AUTHORITY
    can_grant_capital: bool = False
    can_change_direction: bool = False
    schema_version: str = OUTCOME_LEARNING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.direction not in {"CALL", "PUT"}:
            raise ValueError("outcome-learning direction must be CALL or PUT")
        if not 1 <= int(self.horizon_sessions) <= 20:
            raise ValueError("horizon_sessions must be within 1..20")
        if self.authority != OUTCOME_LEARNING_AUTHORITY:
            raise ValueError("outcome learning is observation-only")
        if self.can_grant_capital or self.can_change_direction:
            raise ValueError("outcome learning cannot possess trading authority")
        if self.competing_event_label is CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER:
            if self.fit_eligible:
                raise ValueError("ambiguous touch order cannot enter model fitting")
        if self.fit_eligible and (not self.baseline_eligible or self.exclusion_reasons):
            raise ValueError("fit-eligible records require clean baseline evidence")
        feature_time = datetime.fromisoformat(
            self.feature_cutoff_utc.replace("Z", "+00:00")
        )
        outcome_time = datetime.fromisoformat(
            self.outcome_cutoff_utc.replace("Z", "+00:00")
        )
        if feature_time.tzinfo is None or outcome_time.tzinfo is None:
            raise ValueError("learning cutoffs must be timezone-aware")
        if outcome_time.astimezone(timezone.utc) <= feature_time.astimezone(timezone.utc):
            raise ValueError("outcome evidence must follow its feature cutoff")

    @classmethod
    def create(cls, **values: Any) -> "OutcomeLearningRecord":
        label = values["competing_event_label"]
        if not isinstance(label, CompetingEventLabel):
            label = CompetingEventLabel(str(label))
        attribution = values["attribution"]
        if not isinstance(attribution, OutcomeAttribution):
            attribution = OutcomeAttribution(str(attribution))
        identity = {
            "candidate_event_id": values["candidate_event_id"],
            "outcome_event_id": values["outcome_event_id"],
            "horizon_sessions": int(values["horizon_sessions"]),
            "schema_version": OUTCOME_LEARNING_SCHEMA_VERSION,
        }
        return cls(
            record_id="learning_" + _identity("OUTCOME_LEARNING", identity),
            **{**values, "competing_event_label": label, "attribution": attribution},
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["competing_event_label"] = self.competing_event_label.value
        result["attribution"] = self.attribution.value
        result["exclusion_reasons"] = list(self.exclusion_reasons)
        result["source_dataset_ids"] = list(self.source_dataset_ids)
        result["stratum_backoff_chain"] = (
            [dict(item) for item in self.stratum.backoff_chain()]
            if self.stratum is not None else []
        )
        return result

    @property
    def stratum(self) -> LearningStratum | None:
        if self.hold_bucket == "UNAVAILABLE":
            return None
        return LearningStratum(
            hidden_state_label=self.hidden_state_label,
            phase=self.phase,
            compression_bucket=self.compression_bucket,
            direction=self.direction,
            hold_bucket=self.hold_bucket,
        )


@dataclass(frozen=True, slots=True)
class LearningActivationPolicy:
    model_activation_enabled: bool = False
    minimum_fit_outcomes: int = 200
    minimum_stratum_outcomes: int = 100
    minimum_coverage: float = 0.60
    maximum_overall_ece: float = 0.10
    maximum_stratum_ece: float = 0.15
    require_positive_brier_skill: bool = True
    require_target_roc_auc_above: float = 0.50
    require_target_pr_auc_above_base_rate: bool = True
    require_top_quintile_lift_above: float = 1.0
    purge_embargo_sessions: int = 20
    policy_version: str = OUTCOME_LEARNING_GATE_VERSION

    def __post_init__(self) -> None:
        if self.minimum_fit_outcomes < 1 or self.minimum_stratum_outcomes < 1:
            raise ValueError("learning support thresholds must be positive")
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class LearningActivationAssessment:
    state: ModelActivationState
    can_activate: bool
    reason_codes: tuple[str, ...]
    total_records: int
    fit_eligible_records: int
    ambiguous_records: int
    coverage_fraction: float
    stratum_counts: Mapping[str, int]
    deficient_strata: tuple[str, ...]
    metrics_present: bool
    policy_version: str
    authority: str = OUTCOME_LEARNING_AUTHORITY
    can_grant_capital: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state"] = self.state.value
        result["stratum_counts"] = dict(self.stratum_counts)
        result["reason_codes"] = list(self.reason_codes)
        result["deficient_strata"] = list(self.deficient_strata)
        return result


def assess_model_activation(
    records: Iterable[OutcomeLearningRecord],
    *,
    expected_observable_outcomes: int,
    policy: LearningActivationPolicy,
    held_out_metrics: Mapping[str, Any] | None = None,
) -> LearningActivationAssessment:
    items = tuple(records)
    fit = tuple(item for item in items if item.fit_eligible)
    ambiguous = sum(
        item.competing_event_label is CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER
        for item in items
    )
    denominator = max(0, int(expected_observable_outcomes))
    coverage = len(items) / denominator if denominator else 0.0
    strata: dict[str, int] = {}
    for item in fit:
        key = f"{item.direction}|{item.hold_bucket}"
        strata[key] = strata.get(key, 0) + 1
    required_strata = (
        "CALL|1-5", "CALL|6-10", "CALL|11-20",
        "PUT|1-5", "PUT|6-10", "PUT|11-20",
    )
    deficient = tuple(
        key for key in required_strata
        if strata.get(key, 0) < policy.minimum_stratum_outcomes
    )
    reasons: list[str] = []
    if len(fit) < policy.minimum_fit_outcomes:
        reasons.append("MINIMUM_FIT_OUTCOMES_NOT_MET")
    if coverage < policy.minimum_coverage:
        reasons.append("MINIMUM_OUTCOME_COVERAGE_NOT_MET")
    if deficient:
        reasons.append("MINIMUM_DIRECTION_HORIZON_SUPPORT_NOT_MET")

    metrics = dict(held_out_metrics or {})
    metrics_present = bool(metrics)
    if not metrics_present:
        reasons.append("HELD_OUT_METRICS_NOT_AVAILABLE")
    elif (
        not bool(metrics.get("time_ordered_partitions"))
        or not bool(metrics.get("confidence_intervals_present"))
        or not bool(metrics.get("stability_report_present"))
        or "multiclass_log_loss" not in metrics
        or int(metrics.get("held_out_count", 0)) < 1
        or
        float(metrics.get("maximum_overall_ece", math.inf)) > policy.maximum_overall_ece
        or float(metrics.get("maximum_stratum_ece", math.inf)) > policy.maximum_stratum_ece
        or (
            policy.require_positive_brier_skill
            and float(metrics.get("multiclass_brier_skill", -math.inf)) <= 0
        )
        or float(metrics.get("target_roc_auc", -math.inf))
        <= policy.require_target_roc_auc_above
        or (
            policy.require_target_pr_auc_above_base_rate
            and float(metrics.get("target_pr_auc", -math.inf))
            <= float(metrics.get("target_base_rate", math.inf))
        )
        or float(metrics.get("target_top_quintile_lift", -math.inf))
        <= policy.require_top_quintile_lift_above
    ):
        reasons.append("HELD_OUT_METRIC_GATES_FAILED")
    if not policy.model_activation_enabled:
        reasons.append("MODEL_ACTIVATION_DISABLED_BY_RELEASE_PROFILE")

    if "MINIMUM_FIT_OUTCOMES_NOT_MET" in reasons:
        state = ModelActivationState.INSUFFICIENT_OUTCOMES
    elif "MINIMUM_OUTCOME_COVERAGE_NOT_MET" in reasons:
        state = ModelActivationState.INSUFFICIENT_COVERAGE
    elif "MINIMUM_DIRECTION_HORIZON_SUPPORT_NOT_MET" in reasons:
        state = ModelActivationState.INSUFFICIENT_STRATUM_SUPPORT
    elif "HELD_OUT_METRICS_NOT_AVAILABLE" in reasons:
        state = ModelActivationState.AWAITING_OUT_OF_SAMPLE_METRICS
    elif "HELD_OUT_METRIC_GATES_FAILED" in reasons:
        state = ModelActivationState.METRIC_GATES_FAILED
    elif "MODEL_ACTIVATION_DISABLED_BY_RELEASE_PROFILE" in reasons:
        state = ModelActivationState.RELEASE_PROFILE_DISABLED
    else:
        state = ModelActivationState.ELIGIBLE_FOR_OPERATOR_REVIEW

    return LearningActivationAssessment(
        state=state,
        can_activate=not reasons,
        reason_codes=tuple(reasons),
        total_records=len(items),
        fit_eligible_records=len(fit),
        ambiguous_records=ambiguous,
        coverage_fraction=coverage,
        stratum_counts=strata,
        deficient_strata=deficient,
        metrics_present=metrics_present,
        policy_version=policy.policy_version,
    )


__all__ = [
    "CompetingEventLabel", "LearningActivationAssessment",
    "LearningActivationPolicy", "LearningStratum", "ModelActivationState",
    "OUTCOME_LEARNING_AUTHORITY", "OUTCOME_LEARNING_GATE_VERSION",
    "OUTCOME_LEARNING_SCHEMA_VERSION", "OutcomeAttribution",
    "OutcomeLearningRecord", "assess_model_activation", "attribute_outcome",
    "competing_event_label", "hold_bucket",
]
