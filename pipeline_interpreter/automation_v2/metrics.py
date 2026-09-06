"""Observability and acceptance metrics for shadow trials."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TrialMetric:
    ticker: str
    run_id: str
    invocation_id: str
    status: str
    effective_verdict: str
    duration_ms: int
    provider_attempts: int
    schema_valid: bool
    artifact_complete: bool
    sovereign_preserved: bool
    evidence_valid: bool
    error_class: str = ""


@dataclass(frozen=True, slots=True)
class AcceptanceThresholds:
    minimum_trials: int = 5
    minimum_schema_valid_rate: float = 0.95
    minimum_artifact_complete_rate: float = 0.95
    maximum_degraded_rate: float = 0.05
    require_all_sovereign_preserved: bool = True
    require_all_evidence_valid: bool = True


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    accepted: bool
    total_trials: int
    schema_valid_rate: float
    artifact_complete_rate: float
    degraded_rate: float
    sovereign_preserved_rate: float
    evidence_valid_rate: float
    failures: tuple[str, ...]


def evaluate_acceptance(
    metrics: Iterable[TrialMetric],
    thresholds: AcceptanceThresholds | None = None,
) -> AcceptanceReport:
    values = tuple(metrics)
    policy = thresholds or AcceptanceThresholds()
    total = len(values)

    def rate(predicate) -> float:
        return sum(1 for item in values if predicate(item)) / total if total else 0.0

    schema_rate = rate(lambda item: item.schema_valid)
    artifact_rate = rate(lambda item: item.artifact_complete)
    degraded_rate = rate(lambda item: item.status in {"degraded", "failed"})
    sovereign_rate = rate(lambda item: item.sovereign_preserved)
    evidence_rate = rate(lambda item: item.evidence_valid)
    failures = []
    if total < policy.minimum_trials:
        failures.append(f"INSUFFICIENT_TRIALS:{total}:{policy.minimum_trials}")
    if schema_rate < policy.minimum_schema_valid_rate:
        failures.append(
            f"SCHEMA_VALID_RATE:{schema_rate:.4f}:{policy.minimum_schema_valid_rate:.4f}"
        )
    if artifact_rate < policy.minimum_artifact_complete_rate:
        failures.append(
            f"ARTIFACT_COMPLETE_RATE:{artifact_rate:.4f}:"
            f"{policy.minimum_artifact_complete_rate:.4f}"
        )
    if degraded_rate > policy.maximum_degraded_rate:
        failures.append(
            f"DEGRADED_RATE:{degraded_rate:.4f}:{policy.maximum_degraded_rate:.4f}"
        )
    if policy.require_all_sovereign_preserved and sovereign_rate != 1.0:
        failures.append(f"SOVEREIGN_PRESERVED_RATE:{sovereign_rate:.4f}:1.0000")
    if policy.require_all_evidence_valid and evidence_rate != 1.0:
        failures.append(f"EVIDENCE_VALID_RATE:{evidence_rate:.4f}:1.0000")
    return AcceptanceReport(
        accepted=not failures,
        total_trials=total,
        schema_valid_rate=schema_rate,
        artifact_complete_rate=artifact_rate,
        degraded_rate=degraded_rate,
        sovereign_preserved_rate=sovereign_rate,
        evidence_valid_rate=evidence_rate,
        failures=tuple(failures),
    )


def load_trial_metrics(root: str | Path) -> tuple[TrialMetric, ...]:
    values = []
    for path in sorted(Path(root).rglob("*.trial_metric.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        values.append(TrialMetric(**raw))
    return tuple(values)

