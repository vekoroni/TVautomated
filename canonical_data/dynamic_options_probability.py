"""DOI-8 chronological probability modelling and append-only persistence.

The application service consumes DOI-5 features and DOI-7 labels already in
the canonical control plane.  It performs no provider acquisition and never
changes the deterministic ranking, thesis, execution verdict or capital state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from sklearn.linear_model import LogisticRegression

from domain.dynamic_options_intelligence import ModelApplicabilityState
from domain.dynamic_options_outcomes import DOIOutcomeLabel, OutcomeDataStatus
from domain.dynamic_options_probability import (
    DOI_PROBABILITY_FEATURE_VERSION,
    ProbabilityAcceptancePolicy,
    ProbabilityFeatureVector,
    ProbabilityInference,
    ProbabilityMetrics,
    ProbabilityModelArtifact,
    ProbabilityModelStatus,
    ProbabilityTarget,
    ProbabilityTrainingExample,
    probability_inference_identity,
    probability_model_identity,
    probability_model_version,
)

from .errors import DatasetValidationError
from .contracts import parse_utc
from .option_liquidity_lifecycle import OptionLifecycleConflict, OptionLiquidityLifecycleStore
from .registry import CanonicalRegistry


DOI_PROBABILITY_SCHEMA_VERSION = "doi_probability_models_v1"
DOI_PROBABILITY_SERVICE_VERSION = "doi-probability-service-v1"
COMPLETE_STATUSES = {
    OutcomeDataStatus.COMPLETE,
    OutcomeDataStatus.COMPLETE_OPTION_PATH_PARTIAL,
    OutcomeDataStatus.COMPLETE_OPTION_RETURN_UNAVAILABLE,
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(namespace: str, value: Any) -> str:
    return hashlib.sha256(f"{namespace}|{_canonical(value)}".encode("utf-8")).hexdigest()


def _safe_log1p(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)) or float(value) < 0:
        return None
    return math.log1p(float(value))


def _spread_fraction(bid: float | None, ask: float | None, supplied: float | None) -> float | None:
    if bid is not None and ask is not None and ask >= bid and ask > 0:
        mid = (float(bid) + float(ask)) / 2.0
        if mid > 0:
            return (float(ask) - float(bid)) / mid
    if supplied is None or not math.isfinite(float(supplied)) or float(supplied) < 0:
        return None
    value = float(supplied)
    return value / 100.0 if value > 1.0 else value


def build_probability_feature_vector(
    *, assessment: Any, family: Any, observation: Any,
) -> ProbabilityFeatureVector:
    """Build point-in-time features only; outcome/future fields are forbidden."""

    if assessment.observation_id != observation.observation_id:
        raise DatasetValidationError("probability feature observation does not match assessment")
    if assessment.family_id != family.family_id:
        raise DatasetValidationError("probability feature family does not match assessment")
    if observation.quote_as_of > assessment.evidence_cutoff_utc:
        raise DatasetValidationError("probability feature quote exceeds assessment cutoff")
    if observation.source_dataset_id not in assessment.input_dataset_ids:
        raise DatasetValidationError("probability feature dataset is outside assessment lineage")
    side = family.thesis.governed_direction
    directed_moneyness = (
        (observation.strike / observation.spot - 1.0)
        if side == "CALL" else (1.0 - observation.strike / observation.spot)
    )
    volume = float(observation.volume) if observation.volume is not None else None
    open_interest = float(observation.open_interest) if observation.open_interest is not None else None
    turnover = (
        volume / open_interest
        if volume is not None and open_interest is not None and open_interest > 0
        else None
    )
    size_total = None
    if observation.bid_size is not None or observation.ask_size is not None:
        size_total = max(0.0, float(observation.bid_size or 0.0)) + max(0.0, float(observation.ask_size or 0.0))
    values = {
        "dte": float(observation.dte),
        "abs_delta": abs(float(observation.delta)) if observation.delta is not None else None,
        "directed_moneyness": directed_moneyness,
        "spread_fraction": _spread_fraction(observation.bid, observation.ask, observation.spread_pct),
        "log_volume": _safe_log1p(volume),
        "log_open_interest": _safe_log1p(open_interest),
        "volume_open_interest_ratio": turnover,
        "implied_volatility": float(observation.iv) if observation.iv is not None else None,
        "log_displayed_size": _safe_log1p(size_total),
        "deterministic_score": assessment.ranking_score_uncalibrated,
        "planned_hold_sessions": float(family.thesis.planned_hold_sessions),
        "atm_distance_sigma": observation.atm_distance_sigma,
        "remaining_runway_pct": observation.remaining_runway_pct,
    }
    return ProbabilityFeatureVector(
        assessment_id=assessment.assessment_id,
        family_id=assessment.family_id,
        thesis_id=assessment.thesis_id,
        run_id=assessment.run_id,
        ticker=family.thesis.ticker,
        contract_symbol=assessment.contract_symbol,
        direction=side,
        evidence_cutoff_utc=assessment.evidence_cutoff_utc,
        input_dataset_ids=assessment.input_dataset_ids,
        values=values,
    )


def outcome_target_value(label: DOIOutcomeLabel, target: ProbabilityTarget) -> int | None:
    """Map a mature DOI-7 label to an observable binary target."""

    if label.data_status not in COMPLETE_STATUSES:
        return None
    if target is ProbabilityTarget.LIQUIDITY_1D:
        return int(label.first_spread_35_session is not None and label.first_spread_35_session <= 1)
    if target is ProbabilityTarget.LIQUIDITY_2D:
        if label.horizon_sessions < 2:
            return None
        return int(label.first_spread_35_session is not None and label.first_spread_35_session <= 2)
    if target is ProbabilityTarget.LIQUIDITY_3D:
        if label.horizon_sessions < 3:
            return None
        return int(label.first_spread_35_session is not None and label.first_spread_35_session <= 3)
    if target is ProbabilityTarget.POSITIVE_RETURN:
        return None if label.terminal_executable_return is None else int(label.terminal_executable_return > 0)
    if target is ProbabilityTarget.RETURN_HURDLE:
        if label.reference_entry_ask is None:
            return None
        return int(label.first_return_hurdle_session is not None)
    if target is ProbabilityTarget.TARGET_BEFORE_INVALIDATION:
        if label.first_passage_state == "AMBIGUOUS_SAME_SESSION":
            return None
        return int(label.first_passage_state in {"TARGET_FIRST", "TARGET_ONLY"})
    raise ValueError(f"unsupported target: {target}")


def _target_horizon(target: ProbabilityTarget, default_horizon: int) -> int:
    return {
        ProbabilityTarget.LIQUIDITY_1D: 1,
        ProbabilityTarget.LIQUIDITY_2D: 2,
        ProbabilityTarget.LIQUIDITY_3D: 3,
    }.get(target, int(default_horizon))


def _deduplicate_examples(examples: Iterable[ProbabilityTrainingExample]) -> tuple[ProbabilityTrainingExample, ...]:
    selected: dict[str, ProbabilityTrainingExample] = {}
    for item in sorted(examples, key=lambda value: (value.feature.evidence_cutoff_utc, value.outcome_cutoff_utc, value.label_id)):
        current = selected.get(item.feature.assessment_id)
        if current is None or item.outcome_cutoff_utc < current.outcome_cutoff_utc:
            selected[item.feature.assessment_id] = item
    return tuple(sorted(selected.values(), key=lambda value: (value.feature.evidence_cutoff_utc, value.label_id)))


@dataclass(frozen=True, slots=True)
class ChronologicalModelCohorts:
    training: tuple[ProbabilityTrainingExample, ...]
    calibration: tuple[ProbabilityTrainingExample, ...]
    holdout: tuple[ProbabilityTrainingExample, ...]
    purged_overlap: tuple[ProbabilityTrainingExample, ...]


def chronological_model_cohorts(examples: Sequence[ProbabilityTrainingExample]) -> ChronologicalModelCohorts:
    """Create 60/20/20 feature-time cohorts and purge label overlap."""

    ordered = _deduplicate_examples(examples)
    if len(ordered) < 3:
        return ChronologicalModelCohorts(ordered, (), (), ())
    calibration_index = max(1, int(len(ordered) * 0.60))
    holdout_index = max(calibration_index + 1, int(len(ordered) * 0.80))
    holdout_index = min(holdout_index, len(ordered) - 1)
    calibration_start = ordered[calibration_index].feature.evidence_cutoff_utc
    holdout_start = ordered[holdout_index].feature.evidence_cutoff_utc
    train_candidates = ordered[:calibration_index]
    calibration_candidates = ordered[calibration_index:holdout_index]
    holdout = ordered[holdout_index:]
    training = tuple(item for item in train_candidates if item.outcome_cutoff_utc < calibration_start)
    calibration = tuple(item for item in calibration_candidates if item.outcome_cutoff_utc < holdout_start)
    kept = {item.label_id for item in training + calibration + holdout}
    purged = tuple(item for item in ordered if item.label_id not in kept)
    return ChronologicalModelCohorts(training, calibration, holdout, purged)


def _class_support(items: Sequence[ProbabilityTrainingExample], minimum: int) -> bool:
    values = [item.value for item in items]
    return values.count(0) >= minimum and values.count(1) >= minimum


def _matrix(
    items: Sequence[ProbabilityTrainingExample], feature_names: Sequence[str],
    imputation: Mapping[str, float] | None = None,
) -> tuple[np.ndarray, dict[str, float], np.ndarray]:
    raw = np.array([
        [np.nan if item.feature.values.get(name) is None else float(item.feature.values[name]) for name in feature_names]
        for item in items
    ], dtype=float)
    missing = np.isnan(raw)
    if imputation is None:
        fills = {
            name: float(np.nanmedian(raw[:, index])) if not np.isnan(raw[:, index]).all() else 0.0
            for index, name in enumerate(feature_names)
        }
    else:
        fills = {name: float(imputation[name]) for name in feature_names}
    for index, name in enumerate(feature_names):
        raw[missing[:, index], index] = fills[name]
    return raw, fills, missing


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35.0, 35.0)))


def _log_loss(y: np.ndarray, p: np.ndarray) -> float:
    clipped = np.clip(p, 1e-12, 1.0 - 1e-12)
    return float(-np.mean(y * np.log(clipped) + (1.0 - y) * np.log(1.0 - clipped)))


def _calibration_bins(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[dict[str, float | int], ...]:
    rows: list[dict[str, float | int]] = []
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        mask = (p >= lower) & ((p < upper) if index < bins - 1 else (p <= upper))
        count = int(mask.sum())
        if not count:
            continue
        observed = float(y[mask].mean())
        predicted = float(p[mask].mean())
        half_width = 1.96 * math.sqrt(max(observed * (1.0 - observed), 0.25 / count) / count)
        rows.append({
            "lower": lower, "upper": upper, "count": count,
            "mean_probability": predicted, "observed_rate": observed,
            "absolute_gap": abs(predicted - observed),
            "uncertainty_95_half_width": min(1.0, half_width),
        })
    return tuple(rows)


def _metrics(
    y: np.ndarray, p: np.ndarray, baseline: float, ood_rate: float,
    *, min_temporal_window: int,
) -> ProbabilityMetrics:
    baseline_values = np.full(len(y), min(max(baseline, 1e-12), 1.0 - 1e-12))
    calibration_bins = _calibration_bins(y, p)
    ece = sum(float(row["count"]) / len(y) * float(row["absolute_gap"]) for row in calibration_bins)
    temporal: list[dict[str, float | int | bool]] = []
    if len(y) >= min_temporal_window * 2:
        for number, indices in enumerate(np.array_split(np.arange(len(y)), min(3, len(y) // min_temporal_window)), 1):
            if len(indices) < min_temporal_window:
                continue
            window_y = y[indices]
            window_p = p[indices]
            window_baseline = np.full(len(indices), min(max(baseline, 1e-12), 1.0 - 1e-12))
            model_brier = float(np.mean((window_p - window_y) ** 2))
            base_brier = float(np.mean((window_baseline - window_y) ** 2))
            model_log_loss = _log_loss(window_y, window_p)
            base_log_loss = _log_loss(window_y, window_baseline)
            temporal.append({
                "window": number, "sample_size": len(indices),
                "brier_score": model_brier, "baseline_brier_score": base_brier,
                "log_loss": model_log_loss, "baseline_log_loss": base_log_loss,
                "baseline_beaten": model_brier < base_brier and model_log_loss < base_log_loss,
            })
    return ProbabilityMetrics(
        sample_size=len(y), positives=int(y.sum()),
        brier_score=float(np.mean((p - y) ** 2)), log_loss=_log_loss(y, p),
        expected_calibration_error=float(ece),
        baseline_brier_score=float(np.mean((baseline_values - y) ** 2)),
        baseline_log_loss=_log_loss(y, baseline_values), ood_rate=float(ood_rate),
        calibration_bins=calibration_bins, temporal_windows=tuple(temporal),
    )


def _cohort_diagnostics(items: Sequence[ProbabilityTrainingExample]) -> dict[str, Any]:
    def bucket(value: float | None, boundaries: tuple[float, ...], labels: tuple[str, ...]) -> str:
        if value is None:
            return "MISSING"
        for boundary, label in zip(boundaries, labels):
            if float(value) < boundary:
                return label
        return labels[-1]

    counts: dict[str, dict[str, int]] = {
        "dte": {}, "abs_delta": {}, "spread_fraction": {}, "direction": {},
    }
    missing_by_feature: dict[str, int] = {}
    for item in items:
        values = item.feature.values
        categories = {
            "dte": bucket(values.get("dte"), (15, 30, 60, float("inf")), ("LT15", "15_29", "30_59", "GE60")),
            "abs_delta": bucket(values.get("abs_delta"), (0.25, 0.40, 0.60, float("inf")), ("LT025", "025_039", "040_059", "GE060")),
            "spread_fraction": bucket(values.get("spread_fraction"), (0.15, 0.25, 0.35, float("inf")), ("LT015", "015_024", "025_034", "GE035")),
            "direction": item.feature.direction,
        }
        for group, name in categories.items():
            counts[group][name] = counts[group].get(name, 0) + 1
        for name, value in values.items():
            if value is None:
                missing_by_feature[name] = missing_by_feature.get(name, 0) + 1
    return {
        "total": len(items), "buckets": counts,
        "missing_by_feature": missing_by_feature,
        "regime": "UNAVAILABLE_NOT_IN_DOI_FEATURE_CONTRACT",
    }


def _policy_dict(policy: ProbabilityAcceptancePolicy) -> dict[str, Any]:
    return asdict(policy)


def train_probability_model(
    examples: Sequence[ProbabilityTrainingExample], *, target: ProbabilityTarget,
    direction: str, horizon_sessions: int, created_at_utc: datetime,
    policy: ProbabilityAcceptancePolicy = ProbabilityAcceptancePolicy(),
) -> ProbabilityModelArtifact:
    """Fit logistic + Platt calibration and accept only against later holdout data."""

    target = target if isinstance(target, ProbabilityTarget) else ProbabilityTarget(str(target))
    direction = str(direction).strip().upper()
    filtered = tuple(item for item in examples if item.target is target and item.feature.direction == direction)
    cohorts = chronological_model_cohorts(filtered)
    source_ids = tuple(item.label_id for item in filtered)
    feature_names = tuple(sorted({name for item in filtered for name in item.feature.values}))
    reasons: list[str] = []
    support = (
        len(cohorts.training) >= policy.min_training
        and len(cohorts.calibration) >= policy.min_calibration
        and len(cohorts.holdout) >= policy.min_holdout
        and _class_support(cohorts.training, policy.min_class_per_split)
        and _class_support(cohorts.calibration, policy.min_class_per_split)
        and _class_support(cohorts.holdout, policy.min_class_per_split)
    )
    if not support:
        reasons.append("INSUFFICIENT_CHRONOLOGICAL_CLASS_SUPPORT")
        return ProbabilityModelArtifact.create(
            model_version=probability_model_version(target=target, direction=direction, horizon_sessions=horizon_sessions),
            target=target, direction=direction, horizon_sessions=_target_horizon(target, horizon_sessions),
            status=ProbabilityModelStatus.INSUFFICIENT_SUPPORT, status_reasons=tuple(reasons),
            feature_version=DOI_PROBABILITY_FEATURE_VERSION, feature_names=feature_names,
            created_at_utc=created_at_utc,
            training_cutoff_utc=max((item.outcome_cutoff_utc for item in cohorts.training), default=None),
            calibration_cutoff_utc=max((item.outcome_cutoff_utc for item in cohorts.calibration), default=None),
            holdout_cutoff_utc=max((item.outcome_cutoff_utc for item in cohorts.holdout), default=None),
            training_count=len(cohorts.training), calibration_count=len(cohorts.calibration), holdout_count=len(cohorts.holdout),
            source_label_ids=source_ids, imputation_values={}, means={}, scales={}, coefficients=(), intercept=None,
            calibration_intercept=None, calibration_slope=None, training_ranges={},
            cohort_diagnostics=_cohort_diagnostics(filtered), holdout_metrics=None,
            acceptance_policy=_policy_dict(policy),
        )

    x_train, fills, _ = _matrix(cohorts.training, feature_names)
    means_array = x_train.mean(axis=0)
    scales_array = x_train.std(axis=0)
    scales_array[scales_array < 1e-12] = 1.0
    z_train = (x_train - means_array) / scales_array
    y_train = np.array([item.value for item in cohorts.training], dtype=float)
    classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000, random_state=0)
    classifier.fit(z_train, y_train)

    x_cal, _, _ = _matrix(cohorts.calibration, feature_names, fills)
    z_cal = (x_cal - means_array) / scales_array
    raw_cal_logit = classifier.decision_function(z_cal).reshape(-1, 1)
    y_cal = np.array([item.value for item in cohorts.calibration], dtype=float)
    calibrator = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000, random_state=0)
    calibrator.fit(raw_cal_logit, y_cal)

    x_hold, _, missing_hold = _matrix(cohorts.holdout, feature_names, fills)
    z_hold = (x_hold - means_array) / scales_array
    raw_hold_logit = classifier.decision_function(z_hold)
    calibrated = calibrator.predict_proba(raw_hold_logit.reshape(-1, 1))[:, 1]
    y_hold = np.array([item.value for item in cohorts.holdout], dtype=float)
    ranges = {
        name: (float(x_train[:, index].min()), float(x_train[:, index].max()))
        for index, name in enumerate(feature_names)
    }
    ood_mask = missing_hold.any(axis=1)
    for index, name in enumerate(feature_names):
        lower, upper = ranges[name]
        ood_mask |= (x_hold[:, index] < lower) | (x_hold[:, index] > upper)
    metrics = _metrics(
        y_hold, calibrated, float(y_train.mean()), float(ood_mask.mean()),
        min_temporal_window=policy.min_temporal_window,
    )
    if metrics.brier_score >= metrics.baseline_brier_score or metrics.log_loss >= metrics.baseline_log_loss:
        status = ProbabilityModelStatus.REJECTED_BASELINE_NOT_BEATEN
        reasons.append("HOLDOUT_BASELINE_NOT_BEATEN")
    elif metrics.expected_calibration_error > policy.maximum_ece:
        status = ProbabilityModelStatus.REJECTED_CALIBRATION
        reasons.append("HOLDOUT_ECE_EXCEEDS_POLICY")
    elif not metrics.temporal_windows or any(not bool(item["baseline_beaten"]) for item in metrics.temporal_windows):
        status = ProbabilityModelStatus.REJECTED_TEMPORAL_INSTABILITY
        reasons.append("TEMPORAL_HOLDOUT_WINDOW_NOT_STABLE")
    else:
        status = ProbabilityModelStatus.ACCEPTED
        reasons.append("OUT_OF_SAMPLE_ACCEPTANCE_GATES_PASSED")
    return ProbabilityModelArtifact.create(
        model_version=probability_model_version(target=target, direction=direction, horizon_sessions=horizon_sessions),
        target=target, direction=direction, horizon_sessions=_target_horizon(target, horizon_sessions),
        status=status, status_reasons=tuple(reasons), feature_version=DOI_PROBABILITY_FEATURE_VERSION,
        feature_names=feature_names, created_at_utc=created_at_utc,
        training_cutoff_utc=max(item.outcome_cutoff_utc for item in cohorts.training),
        calibration_cutoff_utc=max(item.outcome_cutoff_utc for item in cohorts.calibration),
        holdout_cutoff_utc=max(item.outcome_cutoff_utc for item in cohorts.holdout),
        training_count=len(cohorts.training), calibration_count=len(cohorts.calibration), holdout_count=len(cohorts.holdout),
        source_label_ids=source_ids, imputation_values=fills,
        means={name: float(means_array[index]) for index, name in enumerate(feature_names)},
        scales={name: float(scales_array[index]) for index, name in enumerate(feature_names)},
        coefficients=tuple(float(value) for value in classifier.coef_[0]), intercept=float(classifier.intercept_[0]),
        calibration_intercept=float(calibrator.intercept_[0]), calibration_slope=float(calibrator.coef_[0][0]),
        training_ranges=ranges, cohort_diagnostics=_cohort_diagnostics(filtered),
        holdout_metrics=metrics, acceptance_policy=_policy_dict(policy),
    )


def infer_probability(model: ProbabilityModelArtifact, feature: ProbabilityFeatureVector) -> ProbabilityInference:
    if model.status is not ProbabilityModelStatus.ACCEPTED:
        return ProbabilityInference.create(
            model_id=model.model_id, assessment_id=feature.assessment_id, target=model.target,
            direction=feature.direction, evidence_cutoff_utc=feature.evidence_cutoff_utc,
            applicability_state=ModelApplicabilityState.MODEL_UNAVAILABLE,
            probability=None, raw_probability=None, uncertainty=None, ood_features=(),
            input_dataset_ids=feature.input_dataset_ids, reason_codes=(model.status.value,),
        )
    if feature.direction != model.direction or feature.feature_version != model.feature_version:
        return ProbabilityInference.create(
            model_id=model.model_id, assessment_id=feature.assessment_id, target=model.target,
            direction=feature.direction, evidence_cutoff_utc=feature.evidence_cutoff_utc,
            applicability_state=ModelApplicabilityState.MODEL_UNAVAILABLE,
            probability=None, raw_probability=None, uncertainty=None, ood_features=(),
            input_dataset_ids=feature.input_dataset_ids, reason_codes=("MODEL_COHORT_MISMATCH",),
        )
    values: list[float] = []
    ood: list[str] = []
    for name in model.feature_names:
        raw = feature.values.get(name)
        if raw is None:
            raw = model.imputation_values[name]
            ood.append(f"{name}:MISSING")
        lower, upper = model.training_ranges[name]
        if float(raw) < lower or float(raw) > upper:
            ood.append(f"{name}:OUTSIDE_TRAINING_RANGE")
        values.append((float(raw) - model.means[name]) / model.scales[name])
    raw_logit = float(model.intercept + np.dot(np.array(model.coefficients), np.array(values)))
    raw_probability = float(_sigmoid(np.array([raw_logit]))[0])
    calibrated_logit = float(model.calibration_intercept + model.calibration_slope * raw_logit)
    probability = float(_sigmoid(np.array([calibrated_logit]))[0])
    if ood:
        return ProbabilityInference.create(
            model_id=model.model_id, assessment_id=feature.assessment_id, target=model.target,
            direction=feature.direction, evidence_cutoff_utc=feature.evidence_cutoff_utc,
            applicability_state=ModelApplicabilityState.OUT_OF_DISTRIBUTION,
            probability=None, raw_probability=raw_probability, uncertainty=1.0,
            ood_features=tuple(sorted(set(ood))), input_dataset_ids=feature.input_dataset_ids,
            reason_codes=("PROBABILITY_WITHHELD_OUT_OF_DISTRIBUTION",),
        )
    uncertainty = 1.0
    if model.holdout_metrics:
        for row in model.holdout_metrics.calibration_bins:
            if float(row["lower"]) <= probability <= float(row["upper"]):
                uncertainty = float(row["uncertainty_95_half_width"])
                break
    return ProbabilityInference.create(
        model_id=model.model_id, assessment_id=feature.assessment_id, target=model.target,
        direction=feature.direction, evidence_cutoff_utc=feature.evidence_cutoff_utc,
        applicability_state=ModelApplicabilityState.APPLICABLE,
        probability=probability, raw_probability=raw_probability, uncertainty=uncertainty,
        ood_features=(), input_dataset_ids=feature.input_dataset_ids,
        reason_codes=("CALIBRATED_ADVISORY_PROBABILITY",),
    )


def _metrics_from_dict(value: Mapping[str, Any] | None) -> ProbabilityMetrics | None:
    if not value:
        return None
    return ProbabilityMetrics(
        sample_size=int(value["sample_size"]), positives=int(value["positives"]),
        brier_score=float(value["brier_score"]), log_loss=float(value["log_loss"]),
        expected_calibration_error=float(value["expected_calibration_error"]),
        baseline_brier_score=float(value["baseline_brier_score"]),
        baseline_log_loss=float(value["baseline_log_loss"]), ood_rate=float(value["ood_rate"]),
        calibration_bins=tuple(value.get("calibration_bins", ())),
        temporal_windows=tuple(value.get("temporal_windows", ())),
    )


def _model_from_dict(payload: Mapping[str, Any]) -> ProbabilityModelArtifact:
    value = dict(payload)
    value.pop("domain_version", None)
    value["target"] = ProbabilityTarget(value["target"])
    value["status"] = ProbabilityModelStatus(value["status"])
    value["created_at_utc"] = datetime.fromisoformat(value["created_at_utc"])
    for name in ("training_cutoff_utc", "calibration_cutoff_utc", "holdout_cutoff_utc"):
        value[name] = datetime.fromisoformat(value[name]) if value.get(name) else None
    value["status_reasons"] = tuple(value["status_reasons"])
    value["feature_names"] = tuple(value["feature_names"])
    value["source_label_ids"] = tuple(value["source_label_ids"])
    value["coefficients"] = tuple(value["coefficients"])
    value["training_ranges"] = {key: tuple(item) for key, item in value["training_ranges"].items()}
    value["holdout_metrics"] = _metrics_from_dict(value.get("holdout_metrics"))
    return ProbabilityModelArtifact(**value)


def _inference_from_dict(payload: Mapping[str, Any]) -> ProbabilityInference:
    value = dict(payload)
    value.pop("domain_version", None)
    value["target"] = ProbabilityTarget(value["target"])
    value["applicability_state"] = ModelApplicabilityState(value["applicability_state"])
    value["evidence_cutoff_utc"] = datetime.fromisoformat(value["evidence_cutoff_utc"])
    for name in ("ood_features", "input_dataset_ids", "reason_codes"):
        value[name] = tuple(value[name])
    return ProbabilityInference(**value)


class DynamicOptionsProbabilityRepository:
    """Append-only DOI-8 model and inference repository in the control plane."""

    def __init__(self, registry: CanonicalRegistry):
        self.registry = registry

    def initialise(self) -> None:
        with self.registry.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS doi_probability_models (
                    model_id TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
                    horizon_sessions INTEGER NOT NULL CHECK(horizon_sessions > 0),
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE')
                );
                CREATE TABLE IF NOT EXISTS doi_probability_inferences (
                    inference_id TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    assessment_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
                    evidence_cutoff_utc TEXT NOT NULL,
                    applicability_state TEXT NOT NULL,
                    probability REAL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    decision_authority TEXT NOT NULL CHECK(decision_authority = 'NONE'),
                    FOREIGN KEY(model_id) REFERENCES doi_probability_models(model_id),
                    FOREIGN KEY(assessment_id) REFERENCES doi_contract_assessments(assessment_id)
                );
                CREATE TRIGGER IF NOT EXISTS trg_doi_probability_model_no_update
                BEFORE UPDATE ON doi_probability_models BEGIN
                    SELECT RAISE(ABORT, 'DOI probability models are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_probability_model_no_delete
                BEFORE DELETE ON doi_probability_models BEGIN
                    SELECT RAISE(ABORT, 'DOI probability models are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_probability_inference_no_update
                BEFORE UPDATE ON doi_probability_inferences BEGIN
                    SELECT RAISE(ABORT, 'DOI probability inferences are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_probability_inference_no_delete
                BEFORE DELETE ON doi_probability_inferences BEGIN
                    SELECT RAISE(ABORT, 'DOI probability inferences are append-only');
                END;
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) VALUES (?, ?)",
                (DOI_PROBABILITY_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )

    def record_model(self, model: ProbabilityModelArtifact) -> tuple[ProbabilityModelArtifact, bool]:
        expected_id = probability_model_identity(
            model_version=model.model_version, target=model.target,
            direction=model.direction, horizon_sessions=model.horizon_sessions,
            source_label_ids=model.source_label_ids,
            acceptance_policy=model.acceptance_policy,
            created_at_utc=model.created_at_utc,
        )
        if model.model_id != expected_id:
            raise DatasetValidationError("model_id does not match probability model identity")
        payload = model.to_dict()
        payload_json = _canonical(payload)
        payload_hash = _hash("DOI_PROBABILITY_MODEL_PAYLOAD_V1", payload)
        with self.registry.connection() as connection:
            if model.source_label_ids:
                placeholders = ",".join("?" for _ in model.source_label_ids)
                found = connection.execute(
                    f"SELECT COUNT(*) FROM doi_outcome_labels WHERE label_id IN ({placeholders})",
                    model.source_label_ids,
                ).fetchone()[0]
                if int(found) != len(model.source_label_ids):
                    raise DatasetValidationError("probability model lineage contains unknown outcome labels")
            existing = connection.execute("SELECT * FROM doi_probability_models WHERE model_id=?", (model.model_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict("probability model identity has different immutable content")
                return _model_from_dict(json.loads(existing["payload_json"])), True
            connection.execute(
                "INSERT INTO doi_probability_models VALUES (?,?,?,?,?,?,?,?,?)",
                (model.model_id, model.target.value, model.direction, model.horizon_sessions,
                 model.status.value, model.created_at_utc.isoformat(), payload_json, payload_hash, model.decision_authority),
            )
        return model, False

    def model(self, model_id: str) -> ProbabilityModelArtifact | None:
        with self.registry.connection() as connection:
            row = connection.execute("SELECT payload_json FROM doi_probability_models WHERE model_id=?", (model_id,)).fetchone()
        return _model_from_dict(json.loads(row["payload_json"])) if row else None

    def inferences_for_assessment(self, assessment_id: str) -> tuple[ProbabilityInference, ...]:
        with self.registry.connection() as connection:
            rows = connection.execute(
                """SELECT payload_json FROM doi_probability_inferences
                   WHERE assessment_id=? ORDER BY evidence_cutoff_utc, inference_id""",
                (assessment_id,),
            ).fetchall()
        return tuple(_inference_from_dict(json.loads(row["payload_json"])) for row in rows)

    def record_inference(self, inference: ProbabilityInference) -> tuple[ProbabilityInference, bool]:
        expected_id = probability_inference_identity(
            model_id=inference.model_id, assessment_id=inference.assessment_id,
            target=inference.target, evidence_cutoff_utc=inference.evidence_cutoff_utc,
        )
        if inference.inference_id != expected_id:
            raise DatasetValidationError("inference_id does not match probability inference identity")
        payload = inference.to_dict()
        payload_json = _canonical(payload)
        payload_hash = _hash("DOI_PROBABILITY_INFERENCE_PAYLOAD_V1", payload)
        with self.registry.connection() as connection:
            model_row = connection.execute("SELECT * FROM doi_probability_models WHERE model_id=?", (inference.model_id,)).fetchone()
            if model_row is None:
                raise DatasetValidationError("probability inference model does not exist")
            model = _model_from_dict(json.loads(model_row["payload_json"]))
            assessment_row = connection.execute(
                "SELECT * FROM doi_contract_assessments WHERE assessment_id=?",
                (inference.assessment_id,),
            ).fetchone()
            if assessment_row is None:
                raise DatasetValidationError("probability inference assessment does not exist")
            family_row = connection.execute(
                "SELECT governed_direction FROM doi_contract_families WHERE family_id=?",
                (assessment_row["family_id"],),
            ).fetchone()
            if (
                model.target is not inference.target
                or model.direction != inference.direction
                or family_row is None
                or family_row["governed_direction"] != inference.direction
            ):
                raise DatasetValidationError("probability inference conflicts with model or thesis direction")
            if inference.evidence_cutoff_utc != parse_utc(assessment_row["evidence_cutoff_utc"]):
                raise DatasetValidationError("probability inference cutoff conflicts with assessment")
            assessment_datasets = set(json.loads(assessment_row["input_dataset_ids_json"]))
            if not set(inference.input_dataset_ids) <= assessment_datasets:
                raise DatasetValidationError("probability inference lineage exceeds assessment evidence")
            if inference.applicability_state is ModelApplicabilityState.APPLICABLE and model.status is not ProbabilityModelStatus.ACCEPTED:
                raise DatasetValidationError("unaccepted model cannot publish an applicable probability")
            existing = connection.execute("SELECT * FROM doi_probability_inferences WHERE inference_id=?", (inference.inference_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict("probability inference identity has different immutable content")
                return _inference_from_dict(json.loads(existing["payload_json"])), True
            connection.execute(
                "INSERT INTO doi_probability_inferences VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (inference.inference_id, inference.model_id, inference.assessment_id,
                 inference.target.value, inference.direction, inference.evidence_cutoff_utc.isoformat(),
                 inference.applicability_state.value, inference.probability, payload_json,
                 payload_hash, inference.decision_authority),
            )
        return inference, False


class DynamicOptionsProbabilityService:
    def __init__(self, store: OptionLiquidityLifecycleStore):
        self.store = store
        self.repository = DynamicOptionsProbabilityRepository(store.registry)

    def training_examples(
        self, *, target: ProbabilityTarget, direction: str, horizon_sessions: int,
    ) -> tuple[ProbabilityTrainingExample, ...]:
        direction = direction.upper()
        candidates: list[ProbabilityTrainingExample] = []
        for label in self.store.doi_outcome_labels(data_statuses=tuple(COMPLETE_STATUSES)):
            if label.direction != direction:
                continue
            required_horizon = _target_horizon(target, horizon_sessions)
            if target in {
                ProbabilityTarget.LIQUIDITY_1D,
                ProbabilityTarget.LIQUIDITY_2D,
                ProbabilityTarget.LIQUIDITY_3D,
            }:
                if label.horizon_sessions < required_horizon:
                    continue
            elif label.horizon_sessions != required_horizon:
                continue
            value = outcome_target_value(label, target)
            if value is None:
                continue
            assessment = self.store.contract_assessment(label.assessment_id)
            family = self.store.contract_family(label.family_id)
            observation = self.store.contract_observation(label.original_observation_id)
            if not assessment or not family or not observation:
                continue
            feature = build_probability_feature_vector(assessment=assessment, family=family, observation=observation)
            candidates.append(ProbabilityTrainingExample(
                label_id=label.label_id, target=target, feature=feature,
                outcome_cutoff_utc=label.outcome_cutoff_utc, value=value,
            ))
        return _deduplicate_examples(candidates)

    def train_and_record(
        self, *, target: ProbabilityTarget, direction: str, horizon_sessions: int,
        created_at_utc: datetime, policy: ProbabilityAcceptancePolicy = ProbabilityAcceptancePolicy(),
    ) -> ProbabilityModelArtifact:
        self.repository.initialise()
        model = train_probability_model(
            self.training_examples(
                target=target, direction=direction, horizon_sessions=horizon_sessions,
            ), target=target,
            direction=direction, horizon_sessions=horizon_sessions,
            created_at_utc=created_at_utc, policy=policy,
        )
        return self.repository.record_model(model)[0]


__all__ = [
    "DOI_PROBABILITY_SCHEMA_VERSION", "DOI_PROBABILITY_SERVICE_VERSION",
    "ChronologicalModelCohorts", "DynamicOptionsProbabilityRepository",
    "DynamicOptionsProbabilityService", "build_probability_feature_vector",
    "chronological_model_cohorts", "infer_probability", "outcome_target_value",
    "train_probability_model",
]
