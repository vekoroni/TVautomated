"""Controlled Worker 3 provider activation and advisory projection.

Production activation is impossible while the release contract is disabled.
Tests inject a transport; this module never selects a fallback provider/model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..adapters.claude_v2 import ClaudeV2Adapter
from ..adapters.jobs import JobStore
from ..adapters.lab_reports import AnalystReports
from ..adapters.workflow import project_completed
from ..application import _constant, _pairs
from ..domain import ContractError, canonical, nonempty
from ..semantic import review_assessment
from .coordinator import Worker3Coordinator


@dataclass(frozen=True, slots=True)
class ProviderRelease:
    path: Path
    content_hash: str
    release_id: str
    enabled: bool
    provider: str
    allowed_models: tuple[str, ...]
    max_jobs_per_activation: int
    max_calls_per_process: int
    max_total_microusd: int
    max_call_microusd: int
    input_rate: int
    output_rate: int
    max_output_tokens: int
    max_input_bytes: int
    timeout_seconds: float
    lab_projection_enabled: bool


def load_provider_release(path: str | Path) -> ProviderRelease:
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
    except (UnicodeError, ValueError) as exc:
        raise ContractError("invalid provider release contract") from exc
    expected = {
        "release_id", "version", "status", "enabled", "provider",
        "allowed_models", "max_jobs_per_activation", "max_calls_per_process",
        "max_total_microusd", "max_call_microusd",
        "input_microusd_per_million_tokens",
        "output_microusd_per_million_tokens",
        "max_output_tokens", "max_input_bytes", "timeout_seconds",
        "require_operator_approval_id", "require_semantic_review",
        "require_human_review", "lab_projection_enabled", "authority",
        "can_grant_capital", "can_reverse_direction",
    }
    if type(value) is not dict or set(value) != expected:
        raise ContractError("provider release contract fields changed")
    enabled = value["enabled"]
    if type(enabled) is not bool:
        raise ContractError("provider release enabled flag must be boolean")
    if (
        value["version"] != "1.0.0"
        or value["provider"] != "ANTHROPIC"
        or value["require_operator_approval_id"] is not True
        or value["require_semantic_review"] is not True
        or value["require_human_review"] is not True
        or value["authority"] != "ADVISORY_ONLY"
        or value["can_grant_capital"] is not False
        or value["can_reverse_direction"] is not False
    ):
        raise ContractError("provider release violates authority controls")
    nonempty(value["release_id"], "provider release id")
    if type(value["lab_projection_enabled"]) is not bool:
        raise ContractError("Lab projection flag must be boolean")
    numeric = (
        "max_jobs_per_activation", "max_calls_per_process", "max_total_microusd",
        "max_call_microusd", "max_output_tokens", "max_input_bytes",
    )
    if any(type(value[name]) is not int or value[name] <= 0 for name in numeric):
        raise ContractError("provider release limits must be positive integers")
    if type(value["timeout_seconds"]) not in (int, float) or not 0 < value["timeout_seconds"] <= 300:
        raise ContractError("provider release timeout must be bounded")
    models = value["allowed_models"]
    if (type(models) is not list
            or any(type(model) is not str or not model.strip() for model in models)
            or len(set(models)) != len(models)):
        raise ContractError("provider release model allow-list is invalid")
    rates = (value["input_microusd_per_million_tokens"],
             value["output_microusd_per_million_tokens"])
    if any(type(rate) is not int or rate < 0 for rate in rates):
        raise ContractError("provider price rates must be nonnegative integers")
    if enabled:
        if value["status"] != "CONTROLLED_ACTIVE" or not models or any(rate <= 0 for rate in rates):
            raise ContractError("enabled provider release lacks model/pricing approval")
    elif value["status"] != "INSTALLED_DISABLED":
        raise ContractError("disabled provider release status mismatch")
    return ProviderRelease(
        path, source_hash, value["release_id"], enabled, value["provider"],
        tuple(models), value["max_jobs_per_activation"],
        value["max_calls_per_process"], value["max_total_microusd"],
        value["max_call_microusd"], rates[0], rates[1],
        value["max_output_tokens"], value["max_input_bytes"],
        value["timeout_seconds"],
        value["lab_projection_enabled"],
    )


def _request_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("provider_request_config")
    if type(config) is not dict or set(config) != {
        "max_output_tokens", "max_input_bytes", "timeout_seconds"
    }:
        raise ContractError("prepared provider request configuration changed")
    if any(type(config[name]) is not int or config[name] <= 0
           for name in ("max_output_tokens", "max_input_bytes")):
        raise ContractError("prepared provider request limits are invalid")
    if (type(config["timeout_seconds"]) not in (int, float)
            or not 0 < config["timeout_seconds"] <= 300):
        raise ContractError("prepared provider timeout is invalid")
    return config


def _sanitized_receipt(transport):
    receipts = getattr(transport, "receipts", [])
    last = receipts[-1] if receipts else {}
    return {key: last.get(key) for key in (
        "request_hash", "http_status", "input_tokens", "output_tokens",
        "elapsed_ms", "credential_source", "credential_fingerprint",
        "status", "error_type", "failure_stage", "timeout_seconds",
    )}


class ControlledProviderRuntime:
    def __init__(self, coordinator: Worker3Coordinator, store: JobStore,
                 reports: AnalystReports, release_path: str | Path):
        if not isinstance(coordinator, Worker3Coordinator):
            raise ContractError("Worker3Coordinator required")
        if not isinstance(store, JobStore) or not isinstance(reports, AnalystReports):
            raise ContractError("durable jobs and analyst report stores required")
        self.coordinator = coordinator
        self.store = store
        self.reports = reports
        self.release = load_provider_release(release_path)
        self.calls = 0

    def _assert_release_unchanged(self):
        if hashlib.sha256(self.release.path.read_bytes()).hexdigest() != self.release.content_hash:
            raise ContractError("provider release changed after runtime initialization")

    def activate(self, job_ids: tuple[str, ...], *, operator_approval_id: str,
                 now: float) -> tuple[str, ...]:
        if not self.release.enabled:
            raise ContractError("provider release is installed but disabled")
        self._assert_release_unchanged()
        nonempty(operator_approval_id, "operator approval id")
        if type(job_ids) is not tuple or not job_ids or len(set(job_ids)) != len(job_ids):
            raise ContractError("activation requires unique immutable job ids")
        if len(job_ids) > self.release.max_jobs_per_activation:
            raise ContractError("activation exceeds approved job count")
        records = []
        total_ceiling = 0
        for job_id in job_ids:
            record = self.store.job_record(job_id)
            if record is None or record["status"] not in ("PREPARED", "QUEUED"):
                raise ContractError("activation job is unavailable or ineligible")
            context = self.coordinator.restore_context(job_id, (record["status"],))
            if context.job.provider != self.release.provider:
                raise ContractError("prepared provider differs from release")
            if context.job.model not in self.release.allowed_models:
                raise ContractError("prepared model is not release-approved")
            if record["ceiling"] > self.release.max_call_microusd:
                raise ContractError("prepared call ceiling exceeds release")
            config = _request_config(record["payload"])
            if (
                config["max_output_tokens"] > self.release.max_output_tokens
                or config["max_input_bytes"] > self.release.max_input_bytes
                or config["timeout_seconds"] > self.release.timeout_seconds
            ):
                raise ContractError("prepared request limits exceed release")
            total_ceiling += record["ceiling"]
            records.append(record)
        if total_ceiling > self.release.max_total_microusd:
            raise ContractError("activation exceeds approved total cost ceiling")
        return self.store.activate_prepared_batch(
            tuple(record["id"] for record in records),
            release_id=self.release.release_id,
            release_hash=self.release.content_hash,
            operator_approval_id=operator_approval_id,
            max_total_ceiling=self.release.max_total_microusd,
            now=now,
        )

    def _adapter(self, context, transport, payload):
        config = _request_config(payload)
        adapter = ClaudeV2Adapter(
            transport,
            config["max_output_tokens"],
            config["max_input_bytes"],
            config["timeout_seconds"],
            context,
        )
        if adapter.request_fingerprint(context.job) != payload["request_fingerprint"]:
            raise ContractError("activated request differs from prepared fingerprint")
        return adapter

    def _cost(self, receipt: dict[str, Any]) -> int | None:
        input_tokens, output_tokens = receipt.get("input_tokens"), receipt.get("output_tokens")
        if type(input_tokens) is not int or type(output_tokens) is not int:
            return None
        raw = ((input_tokens * self.release.input_rate)
               + (output_tokens * self.release.output_rate)) / 1_000_000
        return math.ceil(raw)

    def project(self, job_id: str) -> str:
        context = self.coordinator.restore_context(job_id, ("REVIEW_REQUIRED",))
        return project_completed(self.store, self.reports, job_id, context)

    def execute(self, job_id: str, *, transport, clock) -> dict[str, Any]:
        if not self.release.enabled:
            raise ContractError("provider release is installed but disabled")
        self._assert_release_unchanged()
        record = self.store.job_record(job_id)
        if record is None:
            raise ContractError("activated job not found")
        if record["status"] == "REVIEW_REQUIRED":
            return {"job_id": job_id, "assessment_id": self.project(job_id),
                    "provider_called": False}
        activation = self.store.activation_record(job_id)
        if (activation is None or activation["release_id"] != self.release.release_id
                or activation["release_hash"] != self.release.content_hash):
            raise ContractError("job lacks the current provider activation record")
        if self.calls >= self.release.max_calls_per_process:
            raise ContractError("provider process call limit exhausted")
        # The lease must outlive the approved response window plus validation
        # and durable-save time. A longer HTTP wait alone would lose ownership.
        lease_seconds = max(120, math.ceil(self.release.timeout_seconds) + 60)
        claim = self.store.claim(now=clock(), lease_seconds=lease_seconds, job_id=job_id)
        if claim is None:
            raise ContractError("activated job is not claimable; inspect durable state")
        context = self.coordinator.restore_context(job_id, ("LEASED",))
        try:
            adapter = self._adapter(context, transport, claim["payload"])
            self.store.dispatch(job_id, claim["token"], now=clock())
        except Exception:
            self.store.fail_before_send(
                job_id, claim["token"], now=clock(),
                reason_code="PRE_DISPATCH_VALIDATION_FAILED", delay_seconds=0,
            )
            raise ContractError("provider dispatch blocked before send") from None
        failure_stage = "PROVIDER"
        try:
            # An envelope/transport failure can follow a billable request.
            # Consume the attempt before entering any provider code.
            self.calls += 1
            response = adapter.generate(context.job)
            failure_stage = "STRUCTURAL_SEMANTIC_VALIDATION"
            semantic = review_assessment(context, response)
            generated_at = datetime.fromtimestamp(clock(), timezone.utc).isoformat()
            saved = {
                "context_hash": context.context_hash,
                "provider_response": asdict(response),
                "generated_at": generated_at,
                "semantic_status": semantic.status,
                "semantic_findings": list(semantic.findings),
                "authority": "ADVISORY_ONLY",
                "execution_permission": False,
            }
            receipt = _sanitized_receipt(transport)
            cost = self._cost(receipt)
            failure_stage = "DURABLE_SAVE"
            self.store.finish(
                job_id, claim["token"], now=clock(), response=saved,
                receipt=receipt, cost_microusd=cost,
            )
        except Exception:
            receipt = _sanitized_receipt(transport)
            receipt["runtime_failure_stage"] = failure_stage
            try:
                self.store.mark_uncertain(job_id, claim["token"], now=clock(), receipt=receipt)
            except ContractError:
                self.store.recover(now=clock())
            raise ContractError(
                "provider response failed controlled validation; inspect durable state"
            ) from None
        assessment_id = self.project(job_id)
        return {"job_id": job_id, "assessment_id": assessment_id,
                "provider_called": True, "semantic_status": semantic.status,
                "cost_microusd": cost}
