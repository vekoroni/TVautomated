"""Reusable completed-session thesis coordinator.

This module coordinates already-owned pipeline stages.  It does not contain
trading calculations and cannot grant capital.  Its receipt is immutable and
makes a same-invocation restart idempotent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from canonical_data.run_plan import AuthorityCeiling, RequestedAction, RunPlan


BUILD_THESIS_STAGES = (
    "DISCOVERY",
    "COMPLETED_MARKET_PROFILE",
    "VANGUARD",
    "OPTIONS",
    "PUBLISH_THESIS",
)


@dataclass(frozen=True, slots=True)
class ThesisStageResult:
    stage: str
    status: str
    input_count: int
    output_count: int
    artifact_paths: tuple[str, ...] = ()
    dataset_ids: tuple[str, ...] = ()
    excluded_count: int = 0
    deferred_count: int = 0
    exception_count: int = 0
    reason: str = ""

    def __post_init__(self) -> None:
        stage = self.stage.strip().upper()
        status = self.status.strip().upper()
        if stage not in BUILD_THESIS_STAGES:
            raise ValueError(f"unsupported thesis stage: {stage}")
        if status not in {"COMPLETED", "DEFERRED", "FAILED"}:
            raise ValueError(f"invalid thesis stage status: {status}")
        for name in (
            "input_count", "output_count", "excluded_count",
            "deferred_count", "exception_count",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        accounted = (
            self.output_count + self.excluded_count
            + self.deferred_count + self.exception_count
        )
        if accounted > self.input_count:
            raise ValueError("stage population exceeds its input population")
        if accounted < self.input_count:
            raise ValueError(
                "stage population does not reconcile: "
                f"input={self.input_count} accounted={accounted}"
            )
        object.__setattr__(self, "stage", stage)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "artifact_paths", tuple(self.artifact_paths))
        object.__setattr__(self, "dataset_ids", tuple(sorted(set(self.dataset_ids))))


@dataclass(frozen=True, slots=True)
class ThesisBuildReceipt:
    pipeline_run_id: str
    invocation_id: str
    plan_hash: str
    evidence_cutoff_utc: str
    completed_session: str
    status: str
    authority_ceiling: str
    stages: tuple[ThesisStageResult, ...]
    receipt_hash: str = ""

    def __post_init__(self) -> None:
        expected = self.compute_hash()
        if self.receipt_hash and self.receipt_hash != expected:
            raise ValueError("receipt_hash does not match receipt content")
        object.__setattr__(self, "receipt_hash", expected)

    def _payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_hash", None)
        return value

    def compute_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self._payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


StageHandler = Callable[[RunPlan, Mapping[str, ThesisStageResult]], ThesisStageResult]


def _load_receipt(path: Path) -> ThesisBuildReceipt:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    stages = tuple(ThesisStageResult(**item) for item in payload.pop("stages"))
    return ThesisBuildReceipt(stages=stages, **payload)


def _write_receipt_immutable(receipt: ThesisBuildReceipt, path: Path) -> None:
    encoded = json.dumps(receipt.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError("same invocation already has a different thesis receipt")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def build_thesis(
    plan: RunPlan,
    *,
    handlers: Mapping[str, StageHandler],
    receipt_root: Path,
) -> ThesisBuildReceipt:
    """Execute a governed BUILD_THESIS plan exactly once per invocation."""
    if plan.resolved_action != RequestedAction.BUILD_THESIS.value:
        raise ValueError("build_thesis requires a resolved BUILD_THESIS plan")
    if tuple(plan.stages_to_run) != BUILD_THESIS_STAGES:
        raise ValueError("BUILD_THESIS stage order does not match the governed contract")
    if plan.execution_authority_ceiling != AuthorityCeiling.EOD_PREPARED.value:
        raise ValueError("completed thesis may only have EOD_PREPARED authority")

    receipt_path = Path(receipt_root) / plan.pipeline_run_id / (
        f"completed_thesis_receipt_{plan.invocation_id}.json"
    )
    if receipt_path.exists():
        existing = _load_receipt(receipt_path)
        if existing.plan_hash != plan.plan_hash:
            raise RuntimeError("existing thesis receipt belongs to a different plan")
        return existing

    missing = [stage for stage in BUILD_THESIS_STAGES if stage not in handlers]
    if missing:
        raise ValueError("missing BUILD_THESIS handlers: " + ",".join(missing))

    completed: dict[str, ThesisStageResult] = {}
    for stage in BUILD_THESIS_STAGES:
        result = handlers[stage](plan, dict(completed))
        if result.stage != stage:
            raise RuntimeError(f"handler for {stage} returned {result.stage}")
        completed[stage] = result
        if result.status == "FAILED":
            raise RuntimeError(f"BUILD_THESIS failed at {stage}: {result.reason}")

    receipt = ThesisBuildReceipt(
        pipeline_run_id=plan.pipeline_run_id,
        invocation_id=plan.invocation_id,
        plan_hash=plan.plan_hash,
        evidence_cutoff_utc=plan.evidence_cutoff_utc,
        completed_session=plan.last_completed_session,
        status="COMPLETED",
        authority_ceiling=AuthorityCeiling.EOD_PREPARED.value,
        stages=tuple(completed[stage] for stage in BUILD_THESIS_STAGES),
    )
    _write_receipt_immutable(receipt, receipt_path)
    return receipt
