"""Governed DOI-8 probability-model contracts.

This module contains only domain values and invariants.  It deliberately does
not fetch market data, select a contract, alter a thesis or grant capital.
Probability values are publishable only from an out-of-sample accepted model;
otherwise the deterministic DOI-5 assessment remains the sole output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from .dynamic_options_intelligence import DOI_DECISION_AUTHORITY, ModelApplicabilityState


DOI_PROBABILITY_DOMAIN_VERSION = "doi-probability-domain-v1"
DOI_PROBABILITY_FEATURE_VERSION = "doi-probability-features-v1"
DOI_PROBABILITY_POLICY_VERSION = "doi-probability-acceptance-v1"


class ProbabilityTarget(str, Enum):
    LIQUIDITY_1D = "LIQUIDITY_1D"
    LIQUIDITY_2D = "LIQUIDITY_2D"
    LIQUIDITY_3D = "LIQUIDITY_3D"
    POSITIVE_RETURN = "POSITIVE_RETURN"
    RETURN_HURDLE = "RETURN_HURDLE"
    TARGET_BEFORE_INVALIDATION = "TARGET_BEFORE_INVALIDATION"


class ProbabilityModelStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED_BASELINE_NOT_BEATEN = "REJECTED_BASELINE_NOT_BEATEN"
    REJECTED_CALIBRATION = "REJECTED_CALIBRATION"
    REJECTED_TEMPORAL_INSTABILITY = "REJECTED_TEMPORAL_INSTABILITY"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _token(value: Any, name: str) -> str:
    result = str(value or "").strip().upper()
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _probability(value: Any, name: str) -> float:
    result = _finite(value, name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return result


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(namespace: str, value: Mapping[str, Any]) -> str:
    return hashlib.sha256(f"{namespace}|{_canonical(value)}".encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProbabilityFeatureVector:
    assessment_id: str
    family_id: str
    thesis_id: str
    run_id: str
    ticker: str
    contract_symbol: str
    direction: str
    evidence_cutoff_utc: datetime
    input_dataset_ids: tuple[str, ...]
    values: Mapping[str, float | None]
    feature_version: str = DOI_PROBABILITY_FEATURE_VERSION
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        for name in ("assessment_id", "family_id", "thesis_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        for name in ("run_id", "ticker", "contract_symbol"):
            object.__setattr__(self, name, _token(getattr(self, name), name))
        direction = _token(self.direction, "direction")
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "evidence_cutoff_utc", _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc"))
        dataset_ids = tuple(sorted({str(item).strip() for item in self.input_dataset_ids if str(item).strip()}))
        if not dataset_ids:
            raise ValueError("input_dataset_ids must not be empty")
        object.__setattr__(self, "input_dataset_ids", dataset_ids)
        if not str(self.feature_version or "").strip():
            raise ValueError("feature_version is required")
        clean: dict[str, float | None] = {}
        forbidden = ("outcome", "future", "terminal", "mfe", "mae", "winner", "label")
        for raw_name, raw_value in dict(self.values).items():
            name = str(raw_name).strip().lower()
            if not name or any(token in name for token in forbidden):
                raise ValueError(f"feature name is forbidden or empty: {raw_name}")
            clean[name] = None if raw_value is None else _finite(raw_value, name)
        if not clean:
            raise ValueError("values must not be empty")
        object.__setattr__(self, "values", clean)
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("probability features have no decision authority")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence_cutoff_utc"] = self.evidence_cutoff_utc.isoformat()
        result["input_dataset_ids"] = list(self.input_dataset_ids)
        result["values"] = dict(self.values)
        result["domain_version"] = DOI_PROBABILITY_DOMAIN_VERSION
        return result


@dataclass(frozen=True, slots=True)
class ProbabilityTrainingExample:
    label_id: str
    target: ProbabilityTarget
    feature: ProbabilityFeatureVector
    outcome_cutoff_utc: datetime
    value: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "label_id", _required(self.label_id, "label_id"))
        target = self.target if isinstance(self.target, ProbabilityTarget) else ProbabilityTarget(str(self.target))
        object.__setattr__(self, "target", target)
        cutoff = _utc(self.outcome_cutoff_utc, "outcome_cutoff_utc")
        if cutoff <= self.feature.evidence_cutoff_utc:
            raise ValueError("training outcome must be observed after its feature cutoff")
        object.__setattr__(self, "outcome_cutoff_utc", cutoff)
        if int(self.value) not in {0, 1}:
            raise ValueError("training value must be binary")
        object.__setattr__(self, "value", int(self.value))


@dataclass(frozen=True, slots=True)
class ProbabilityAcceptancePolicy:
    min_training: int = 200
    min_calibration: int = 75
    min_holdout: int = 75
    min_class_per_split: int = 20
    min_temporal_window: int = 25
    maximum_ece: float = 0.10
    policy_version: str = DOI_PROBABILITY_POLICY_VERSION

    def __post_init__(self) -> None:
        for name in ("min_training", "min_calibration", "min_holdout", "min_class_per_split", "min_temporal_window"):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        _probability(self.maximum_ece, "maximum_ece")


@dataclass(frozen=True, slots=True)
class ProbabilityMetrics:
    sample_size: int
    positives: int
    brier_score: float
    log_loss: float
    expected_calibration_error: float
    baseline_brier_score: float
    baseline_log_loss: float
    ood_rate: float
    calibration_bins: tuple[Mapping[str, float | int], ...]
    temporal_windows: tuple[Mapping[str, float | int | bool], ...] = ()

    def __post_init__(self) -> None:
        if self.sample_size < 1 or not 0 <= self.positives <= self.sample_size:
            raise ValueError("metric sample counts are invalid")
        for name in ("brier_score", "log_loss", "expected_calibration_error", "baseline_brier_score", "baseline_log_loss", "ood_rate"):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.expected_calibration_error > 1.0 or self.ood_rate > 1.0:
            raise ValueError("calibration error and OOD rate cannot exceed one")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["calibration_bins"] = [dict(item) for item in self.calibration_bins]
        result["temporal_windows"] = [dict(item) for item in self.temporal_windows]
        return result


@dataclass(frozen=True, slots=True)
class ProbabilityModelArtifact:
    model_id: str
    model_version: str
    target: ProbabilityTarget
    direction: str
    horizon_sessions: int
    status: ProbabilityModelStatus
    status_reasons: tuple[str, ...]
    feature_version: str
    feature_names: tuple[str, ...]
    created_at_utc: datetime
    training_cutoff_utc: datetime | None
    calibration_cutoff_utc: datetime | None
    holdout_cutoff_utc: datetime | None
    training_count: int
    calibration_count: int
    holdout_count: int
    source_label_ids: tuple[str, ...]
    imputation_values: Mapping[str, float]
    means: Mapping[str, float]
    scales: Mapping[str, float]
    coefficients: tuple[float, ...]
    intercept: float | None
    calibration_intercept: float | None
    calibration_slope: float | None
    training_ranges: Mapping[str, tuple[float, float]]
    cohort_diagnostics: Mapping[str, Any]
    holdout_metrics: ProbabilityMetrics | None
    acceptance_policy: Mapping[str, Any]
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_invalidate_thesis: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _required(self.model_id, "model_id"))
        if not str(self.model_version or "").strip():
            raise ValueError("model_version is required")
        object.__setattr__(self, "target", self.target if isinstance(self.target, ProbabilityTarget) else ProbabilityTarget(str(self.target)))
        direction = _token(self.direction, "direction")
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "status", self.status if isinstance(self.status, ProbabilityModelStatus) else ProbabilityModelStatus(str(self.status)))
        object.__setattr__(self, "status_reasons", tuple(_token(item, "status_reason") for item in self.status_reasons))
        object.__setattr__(self, "feature_names", tuple(str(item).strip().lower() for item in self.feature_names))
        object.__setattr__(self, "source_label_ids", tuple(sorted({_required(item, "source_label_id") for item in self.source_label_ids})))
        object.__setattr__(self, "imputation_values", dict(self.imputation_values))
        object.__setattr__(self, "means", dict(self.means))
        object.__setattr__(self, "scales", dict(self.scales))
        object.__setattr__(self, "training_ranges", {key: tuple(value) for key, value in self.training_ranges.items()})
        object.__setattr__(self, "cohort_diagnostics", dict(self.cohort_diagnostics))
        object.__setattr__(self, "acceptance_policy", dict(self.acceptance_policy))
        object.__setattr__(self, "created_at_utc", _utc(self.created_at_utc, "created_at_utc"))
        for name in ("training_cutoff_utc", "calibration_cutoff_utc", "holdout_cutoff_utc"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value, name))
        for name in ("training_count", "calibration_count", "holdout_count"):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.status is ProbabilityModelStatus.ACCEPTED:
            if not self.holdout_metrics or self.intercept is None or not self.coefficients:
                raise ValueError("accepted model requires fitted coefficients and holdout metrics")
            if self.holdout_metrics.brier_score >= self.holdout_metrics.baseline_brier_score:
                raise ValueError("accepted model must beat the Brier baseline")
            if self.holdout_metrics.log_loss >= self.holdout_metrics.baseline_log_loss:
                raise ValueError("accepted model must beat the log-loss baseline")
            if any(not bool(item.get("baseline_beaten")) for item in self.holdout_metrics.temporal_windows):
                raise ValueError("accepted model must be stable across temporal holdout windows")
            maximum_ece = float(self.acceptance_policy.get("maximum_ece", -1.0))
            if maximum_ece < 0 or self.holdout_metrics.expected_calibration_error > maximum_ece:
                raise ValueError("accepted model exceeds its calibration policy")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("probability model has no decision authority")
        if self.can_change_direction or self.can_invalidate_thesis or self.can_grant_capital:
            raise ValueError("probability model cannot possess trading authority")

    @classmethod
    def create(cls, **values: Any) -> "ProbabilityModelArtifact":
        return cls(model_id=probability_model_identity(
            model_version=values["model_version"], target=values["target"],
            direction=values["direction"], horizon_sessions=values["horizon_sessions"],
            source_label_ids=values.get("source_label_ids", ()),
            acceptance_policy=values.get("acceptance_policy", {}),
            created_at_utc=values["created_at_utc"],
        ), **values)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["target"] = self.target.value
        result["status"] = self.status.value
        result["created_at_utc"] = self.created_at_utc.isoformat()
        for name in ("training_cutoff_utc", "calibration_cutoff_utc", "holdout_cutoff_utc"):
            result[name] = getattr(self, name).isoformat() if getattr(self, name) else None
        result["source_label_ids"] = list(self.source_label_ids)
        result["feature_names"] = list(self.feature_names)
        result["status_reasons"] = list(self.status_reasons)
        result["training_ranges"] = {key: list(value) for key, value in self.training_ranges.items()}
        result["holdout_metrics"] = self.holdout_metrics.to_dict() if self.holdout_metrics else None
        result["domain_version"] = DOI_PROBABILITY_DOMAIN_VERSION
        return result


@dataclass(frozen=True, slots=True)
class ProbabilityInference:
    inference_id: str
    model_id: str
    assessment_id: str
    target: ProbabilityTarget
    direction: str
    evidence_cutoff_utc: datetime
    applicability_state: ModelApplicabilityState
    probability: float | None
    raw_probability: float | None
    uncertainty: float | None
    ood_features: tuple[str, ...]
    input_dataset_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_invalidate_thesis: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        for name in ("inference_id", "model_id", "assessment_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        object.__setattr__(self, "target", self.target if isinstance(self.target, ProbabilityTarget) else ProbabilityTarget(str(self.target)))
        direction = _token(self.direction, "direction")
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "evidence_cutoff_utc", _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc"))
        state = self.applicability_state if isinstance(self.applicability_state, ModelApplicabilityState) else ModelApplicabilityState(str(self.applicability_state))
        object.__setattr__(self, "applicability_state", state)
        object.__setattr__(self, "ood_features", tuple(sorted({_token(item, "ood_feature") for item in self.ood_features})))
        object.__setattr__(self, "input_dataset_ids", tuple(sorted({str(item).strip() for item in self.input_dataset_ids if str(item).strip()})))
        object.__setattr__(self, "reason_codes", tuple(_token(item, "reason_code") for item in self.reason_codes))
        if not self.input_dataset_ids or not self.reason_codes:
            raise ValueError("inference lineage and reason codes are required")
        for name in ("probability", "raw_probability", "uncertainty"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _probability(value, name))
        if state is not ModelApplicabilityState.APPLICABLE and self.probability is not None:
            raise ValueError("non-applicable inference cannot publish a probability")
        if state is ModelApplicabilityState.APPLICABLE and self.probability is None:
            raise ValueError("applicable inference requires a probability")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("probability inference has no decision authority")
        if self.can_change_direction or self.can_invalidate_thesis or self.can_grant_capital:
            raise ValueError("probability inference cannot possess trading authority")

    @classmethod
    def create(cls, **values: Any) -> "ProbabilityInference":
        return cls(inference_id=probability_inference_identity(
            model_id=values["model_id"], assessment_id=values["assessment_id"],
            target=values["target"], evidence_cutoff_utc=values["evidence_cutoff_utc"],
        ), **values)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["target"] = self.target.value
        result["applicability_state"] = self.applicability_state.value
        result["evidence_cutoff_utc"] = self.evidence_cutoff_utc.isoformat()
        result["input_dataset_ids"] = list(self.input_dataset_ids)
        result["ood_features"] = list(self.ood_features)
        result["reason_codes"] = list(self.reason_codes)
        result["domain_version"] = DOI_PROBABILITY_DOMAIN_VERSION
        return result


def probability_model_version(*, target: ProbabilityTarget, direction: str, horizon_sessions: int) -> str:
    return f"doi-logistic-platt-v1:{target.value}:{direction.upper()}:{int(horizon_sessions)}"


def probability_model_identity(
    *, model_version: str, target: ProbabilityTarget | str, direction: str,
    horizon_sessions: int, source_label_ids: Sequence[str],
    acceptance_policy: Mapping[str, Any], created_at_utc: datetime,
) -> str:
    identity = {
        "model_version": str(model_version),
        "target": str(getattr(target, "value", target)),
        "direction": str(direction).upper(),
        "horizon_sessions": int(horizon_sessions),
        "source_label_ids": sorted(str(item) for item in source_label_ids),
        "policy": dict(acceptance_policy),
        "training_event_utc": _utc(created_at_utc, "created_at_utc").isoformat(),
    }
    return _identity("DOI_PROBABILITY_MODEL_V1", identity)


def probability_inference_identity(
    *, model_id: str, assessment_id: str, target: ProbabilityTarget | str,
    evidence_cutoff_utc: datetime,
) -> str:
    identity = {
        "model_id": str(model_id), "assessment_id": str(assessment_id),
        "target": str(getattr(target, "value", target)),
        "evidence_cutoff_utc": _utc(evidence_cutoff_utc, "evidence_cutoff_utc").isoformat(),
    }
    return _identity("DOI_PROBABILITY_INFERENCE_V1", identity)


__all__ = [
    "DOI_PROBABILITY_DOMAIN_VERSION", "DOI_PROBABILITY_FEATURE_VERSION",
    "DOI_PROBABILITY_POLICY_VERSION", "ProbabilityAcceptancePolicy",
    "ProbabilityFeatureVector", "ProbabilityInference", "ProbabilityMetrics",
    "ProbabilityModelArtifact", "ProbabilityModelStatus", "ProbabilityTarget",
    "ProbabilityTrainingExample", "probability_inference_identity",
    "probability_model_identity", "probability_model_version",
]
