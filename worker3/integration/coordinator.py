"""Durable PREPARE_ONLY coordinator for governed Worker 3 evidence.

This module stages immutable provider-neutral jobs. It cannot dispatch them,
project them into the Intelligence Lab, or affect AVSHUNTER trading authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from ..adapters.jobs import JobStore
from ..application import ProviderResponse, _constant, _pairs
from ..domain import (
    ContractError,
    Direction,
    EvidenceBundle,
    Identity,
    Observation,
    WorkerJob,
    canonical,
    digest,
    nonempty,
    sha,
)
from ..v2.assessment import AssessmentContext, PreviousAssessment, PROMPT
from ..adapters.claude_v2 import ClaudeV2Adapter
from .avshunter_source import AvshunterSourceBridge, PreparedRun


@dataclass(frozen=True, slots=True)
class CoordinatorPolicy:
    path: Path
    content_hash: str
    version: str
    runtime_mode: str
    provider_dispatch_enabled: bool


@dataclass(frozen=True, slots=True)
class CoordinatorEntry:
    ticker: str
    status: str
    intake_id: str
    job_id: str | None
    evidence_hash: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class CoordinatorRun:
    source: PreparedRun
    entries: tuple[CoordinatorEntry, ...]
    policy_hash: str

    def summary(self) -> dict[str, Any]:
        prepared = sum(entry.status == "JOB_PREPARED" for entry in self.entries)
        return {
            "schema_version": "worker3_coordinator_summary_v1",
            "run_id": self.source.context.run_id,
            "requested": len(self.entries),
            "jobs_prepared": prepared,
            "data_exceptions": len(self.entries) - prepared,
            "provider_dispatches": 0,
            "provider_dispatch_enabled": False,
            "pipeline_production_writes": 0,
            "authority": "ADVISORY_ONLY",
            "capital_permission": False,
            "policy_hash": self.policy_hash,
        }


def _policy(path: str | Path) -> CoordinatorPolicy:
    path = Path(path).resolve(strict=True)
    data = path.read_bytes()
    content_hash = hashlib.sha256(data).hexdigest()
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, ValueError) as exc:
        raise ContractError("invalid Worker 3 integration policy") from exc
    required = {
        "contract_id", "version", "status", "enabled", "runtime_mode",
        "source_bridge_enabled", "job_intake_enabled",
        "provider_dispatch_enabled", "lab_projection_enabled",
        "pipeline_production_writer_enabled", "authority", "can_grant_capital",
        "can_reverse_direction", "required_run_status",
        "allowed_resolved_actions", "source_contracts", "failure_policy",
    }
    if type(document) is not dict or set(document) != required:
        raise ContractError("Worker 3 integration policy fields changed")
    if (
        document["contract_id"] != "AVS-W3-INTEGRATION"
        or document["version"] != "1.3.1"
        or document["status"] != "ACTIVE_PREPARE_ONLY"
        or document["enabled"] is not True
        or document["runtime_mode"] != "PREPARE_ONLY"
        or document["source_bridge_enabled"] is not True
        or document["job_intake_enabled"] is not True
        or document["provider_dispatch_enabled"] is not False
        or document["lab_projection_enabled"] is not False
        or document["pipeline_production_writer_enabled"] is not False
        or document["authority"] != "ADVISORY_ONLY"
        or document["can_grant_capital"] is not False
        or document["can_reverse_direction"] is not False
        or document["required_run_status"] != "COMPLETED"
        or document["allowed_resolved_actions"] != ["BUILD_THESIS", "VALIDATE_THESIS"]
        or document["source_contracts"] != {
            "run_meta": "run_meta_v2",
            "intelligence_lab": "lab_signal_book_v4",
            "option_chain": "option_chain_v2",
            "selected_option_quote": "selected_option_quote_v1",
            "market_profile": "market_profile_evidence_v1",
            "interpreter_macro_context": "interpreter_macro_context_v1",
            "market_environment": "market_environment_v1",
            "macro_ticker_context": "macro_ticker_context_v1",
            "trade_plan": "trade_plan_snapshot_v1",
            "worker_evidence": "analyst_evidence_v1",
            "prepared_job": "worker3_prepared_job_v1",
            "intake_exception": "worker3_intake_exception_v1",
        }
        or document["failure_policy"] != {
            "run_contract_failure": "BLOCK_RUN_PREPARATION",
            "ticker_evidence_failure": "ISOLATE_DATA_EXCEPTION",
            "provider_failure": "NOT_APPLICABLE_PROVIDER_DISABLED",
        }
    ):
        raise ContractError("policy is not the approved PREPARE_ONLY authority")
    return CoordinatorPolicy(path, content_hash, document["version"],
                             document["runtime_mode"], False)


def _bundle_payload(bundle: EvidenceBundle) -> dict[str, Any]:
    return {
        "schema_version": bundle.schema_version,
        "identity": asdict(bundle.identity),
        "evidence_cutoff_utc": bundle.evidence_cutoff_utc,
        "observations": [asdict(observation) for observation in bundle.observations],
    }


def _restore_bundle(value: Any) -> EvidenceBundle:
    if type(value) is not dict or set(value) != {
        "schema_version", "identity", "evidence_cutoff_utc", "observations"
    }:
        raise ContractError("stored evidence-bundle contract changed")
    identity_value = value["identity"]
    if type(identity_value) is not dict:
        raise ContractError("stored identity is invalid")
    try:
        identity = Identity(**{
            **identity_value,
            "direction": Direction(identity_value["direction"]),
        })
        observations = tuple(Observation(**row) for row in value["observations"])
        return EvidenceBundle(
            identity,
            value["evidence_cutoff_utc"],
            observations,
            value["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("stored evidence bundle is invalid") from exc


def _job_payload(job: WorkerJob, context_hash: str, policy_hash: str,
                 request_fingerprint: str,
                 provider_request_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "worker3_prepared_job_v1",
        "authority": "ADVISORY_ONLY",
        "capital_permission": False,
        "dispatch_state": "DISABLED_BY_POLICY",
        "policy_hash": policy_hash,
        "context_hash": context_hash,
        "request_fingerprint": request_fingerprint,
        "provider_request_config": provider_request_config,
        "worker_job": {
            "provider": job.provider,
            "model": job.model,
            "prompt_version": job.prompt_version,
            "task_type": job.task_type,
            "previous_assessment_id": job.previous_assessment_id,
            "bundle": _bundle_payload(job.bundle),
        },
    }


class Worker3Coordinator:
    def __init__(self, bridge: AvshunterSourceBridge, store: JobStore,
                 policy_path: str | Path):
        if not isinstance(bridge, AvshunterSourceBridge) or not isinstance(store, JobStore):
            raise ContractError("governed source bridge and durable JobStore required")
        self.bridge = bridge
        self.store = store
        self.policy = _policy(policy_path)

    def prepare_run(self, run_id: str, *, provider: str, model: str, now: float,
                    tickers: tuple[str, ...] | None = None,
                    previous_assessment_ids: dict[str, str] | None = None,
                    max_attempts: int = 3,
                    call_ceiling_microusd: int = 100000,
                    max_output_tokens: int = 2048,
                    max_input_bytes: int = 500000,
                    timeout_seconds: float = 30.0) -> CoordinatorRun:
        nonempty(provider, "provider")
        nonempty(model, "model")
        refresh = previous_assessment_ids is not None
        if refresh:
            if type(previous_assessment_ids) is not dict or not previous_assessment_ids:
                raise ContractError("refresh requires an explicit prior assessment per ticker")
            for ticker, assessment_id in previous_assessment_ids.items():
                nonempty(ticker, "refresh ticker")
                sha(assessment_id)
            if tickers is None:
                tickers = tuple(sorted(previous_assessment_ids))
            elif set(tickers) != set(previous_assessment_ids):
                raise ContractError("refresh worklist and prior-assessment map differ")
        source = self.bridge.prepare_run(run_id, tickers=tickers)
        results: list[CoordinatorEntry] = []
        for entry in source.entries:
            reason = entry.reason
            prior = None
            if entry.status == "EVIDENCE_PREPARED" and entry.bundle is not None and refresh:
                try:
                    prior = self.restore_previous_assessment(
                        previous_assessment_ids[entry.ticker]
                    )
                    if prior.context.job.bundle.identity.ticker != entry.ticker:
                        raise ContractError("prior assessment belongs to another ticker")
                except ContractError as exc:
                    reason = f"PRIOR_ASSESSMENT_INVALID:{exc}"
            if entry.status != "EVIDENCE_PREPARED" or entry.bundle is None or reason:
                exception_payload = {
                    "schema_version": "worker3_intake_exception_v1",
                    "run_id": run_id,
                    "invocation_id": source.context.invocation_id,
                    "ticker": entry.ticker,
                    "status": "DATA_EXCEPTION",
                    "reason_code": "SOURCE_DATA_EXCEPTION",
                    "reason": reason or "UNSPECIFIED_SOURCE_DATA_EXCEPTION",
                    "authority": "ADVISORY_ONLY",
                    "policy_hash": self.policy.content_hash,
                }
                payload_hash = digest(exception_payload)
                intake_id = self.store.record_intake(
                    run_id=run_id,
                    invocation_id=source.context.invocation_id,
                    ticker=entry.ticker,
                    status="DATA_EXCEPTION",
                    reason_code="SOURCE_DATA_EXCEPTION",
                    reason=exception_payload["reason"],
                    payload_hash=payload_hash,
                    now=now,
                )
                results.append(CoordinatorEntry(
                    entry.ticker, "DATA_EXCEPTION", intake_id, None, None,
                    exception_payload["reason"],
                ))
                continue
            job = WorkerJob(
                bundle=entry.bundle,
                provider=provider,
                model=model,
                prompt_version=PROMPT,
                task_type="REFRESH_ASSESSMENT" if refresh else "INITIAL_ASSESSMENT",
                previous_assessment_id=(
                    previous_assessment_ids[entry.ticker] if refresh else None
                ),
            )
            try:
                context = AssessmentContext(job, previous=prior)
            except ContractError as exc:
                exception_payload = {
                    "schema_version": "worker3_intake_exception_v1",
                    "run_id": run_id,
                    "invocation_id": source.context.invocation_id,
                    "ticker": entry.ticker,
                    "status": "DATA_EXCEPTION",
                    "reason_code": "SOURCE_DATA_EXCEPTION",
                    "reason": f"REFRESH_CONTEXT_INVALID:{exc}",
                    "authority": "ADVISORY_ONLY",
                    "policy_hash": self.policy.content_hash,
                }
                payload_hash = digest(exception_payload)
                intake_id = self.store.record_intake(
                    run_id=run_id,
                    invocation_id=source.context.invocation_id,
                    ticker=entry.ticker,
                    status="DATA_EXCEPTION",
                    reason_code="SOURCE_DATA_EXCEPTION",
                    reason=exception_payload["reason"],
                    payload_hash=payload_hash,
                    now=now,
                )
                results.append(CoordinatorEntry(
                    entry.ticker, "DATA_EXCEPTION", intake_id, None, None,
                    exception_payload["reason"],
                ))
                continue
            provider_request_config = {
                "max_output_tokens": max_output_tokens,
                "max_input_bytes": max_input_bytes,
                "timeout_seconds": timeout_seconds,
            }
            if provider == "ANTHROPIC":
                adapter = ClaudeV2Adapter(
                    _DisabledTransport(), max_output_tokens, max_input_bytes,
                    timeout_seconds, context,
                )
                request_fingerprint = adapter.request_fingerprint(job)
            else:
                request_fingerprint = digest({
                    "provider": provider,
                    "model": model,
                    "prompt_version": PROMPT,
                    "policy_hash": self.policy.content_hash,
                    "provider_request_config": provider_request_config,
                    "adapter": "NOT_IMPLEMENTED_PREPARE_ONLY",
                })
            payload = _job_payload(
                job, context.context_hash, self.policy.content_hash,
                request_fingerprint, provider_request_config,
            )
            job_id = self.store.stage_prepared(
                run_id=run_id,
                ticker=entry.ticker,
                job_key=job.job_key,
                context_hash=context.context_hash,
                request_fingerprint=request_fingerprint,
                payload=payload,
                now=now,
                max_attempts=max_attempts,
                call_ceiling_microusd=call_ceiling_microusd,
            )
            payload_hash = digest(payload)
            intake_id = self.store.record_intake(
                run_id=run_id,
                invocation_id=source.context.invocation_id,
                ticker=entry.ticker,
                status="JOB_PREPARED",
                evidence_hash=entry.bundle.evidence_hash,
                job_id=job_id,
                payload_hash=payload_hash,
                now=now,
            )
            results.append(CoordinatorEntry(
                entry.ticker, "JOB_PREPARED", intake_id, job_id,
                entry.bundle.evidence_hash, None,
            ))
        return CoordinatorRun(source, tuple(results), self.policy.content_hash)

    def restore_previous_assessment(
        self, assessment_id: str, _seen: set[str] | None = None
    ) -> PreviousAssessment:
        sha(assessment_id)
        index = self.store.assessment_record(assessment_id)
        if index is None:
            # Assessments projected before the index existed retain their full
            # immutable job/response pair. Rebuild only initial assessments,
            # prove the content-derived ID, then add the missing index without
            # making another provider call.
            for candidate in self.store.completed_job_records():
                worker_job = candidate["payload"].get("worker_job", {})
                if worker_job.get("task_type") != "INITIAL_ASSESSMENT":
                    continue
                try:
                    previous = self._reconstruct_previous(
                        candidate["id"], _seen or set()
                    )
                except ContractError:
                    continue
                if previous.assessment_id != assessment_id:
                    continue
                identity = previous.context.job.bundle.identity
                self.store.record_assessment(
                    assessment_id=assessment_id,
                    job_id=candidate["id"],
                    run_id=identity.run_id,
                    ticker=identity.ticker,
                    context_hash=previous.context.context_hash,
                    evidence_cutoff=previous.context.job.bundle.evidence_cutoff_utc,
                    generated_at=previous.generated_at,
                )
                index = self.store.assessment_record(assessment_id)
                break
        if index is None:
            raise ContractError("prior assessment is not indexed in the durable job store")
        previous = self._reconstruct_previous(index["job_id"], _seen or set())
        context = previous.context
        identity = context.job.bundle.identity
        if (
            previous.assessment_id != assessment_id
            or index["context_hash"] != context.context_hash
            or index["run_id"] != identity.run_id
            or index["ticker"] != identity.ticker
            or index["evidence_cutoff"] != context.job.bundle.evidence_cutoff_utc
            or index["generated_at"] != previous.generated_at
        ):
            raise ContractError("prior assessment index failed immutable reconstruction")
        return previous

    def _reconstruct_previous(self, job_id: str,
                              seen: set[str]) -> PreviousAssessment:
        context = self._restore_context(job_id, ("REVIEW_REQUIRED",), seen)
        saved = self.store.completed_result(job_id)
        if type(saved) is not dict or type(saved.get("provider_response")) is not dict:
            raise ContractError("prior assessment has no reconstructable provider response")
        if (
            saved.get("context_hash") != context.context_hash
            or saved.get("authority", "ADVISORY_ONLY") != "ADVISORY_ONLY"
            or saved.get("execution_permission", False) is not False
        ):
            raise ContractError("prior assessment violates its durable context or authority")
        try:
            return PreviousAssessment(
                context,
                ProviderResponse(**saved["provider_response"]),
                saved["generated_at"],
            )
        except (KeyError, TypeError) as exc:
            raise ContractError("prior assessment response contract is invalid") from exc

    def restore_context(self, job_id: str,
                        allowed_statuses: tuple[str, ...] = ("PREPARED",)) -> AssessmentContext:
        return self._restore_context(job_id, allowed_statuses, set())

    def _restore_context(self, job_id: str, allowed_statuses: tuple[str, ...],
                         seen: set[str]) -> AssessmentContext:
        nonempty(job_id, "job id")
        if type(allowed_statuses) is not tuple or not allowed_statuses:
            raise ContractError("nonempty immutable allowed-status set required")
        if job_id in seen:
            raise ContractError("cyclic prior-assessment chain")
        seen = set(seen)
        seen.add(job_id)
        record = self.store.job_record(job_id)
        if record is None or record["status"] not in allowed_statuses:
            raise ContractError("durable job is not in an allowed restoration state")
        payload = record["payload"]
        if type(payload) is not dict or set(payload) != {
            "schema_version", "authority", "capital_permission", "dispatch_state",
            "policy_hash", "context_hash", "request_fingerprint",
            "provider_request_config", "worker_job"
        }:
            raise ContractError("stored prepared-job contract changed")
        if (
            payload["schema_version"] != "worker3_prepared_job_v1"
            or payload["authority"] != "ADVISORY_ONLY"
            or payload["capital_permission"] is not False
            or payload["dispatch_state"] != "DISABLED_BY_POLICY"
            or payload["policy_hash"] != self.policy.content_hash
        ):
            raise ContractError("stored job violates current PREPARE_ONLY policy")
        value = payload["worker_job"]
        if type(value) is not dict or set(value) != {
            "provider", "model", "prompt_version", "task_type",
            "previous_assessment_id", "bundle"
        }:
            raise ContractError("stored WorkerJob contract changed")
        job = WorkerJob(
            bundle=_restore_bundle(value["bundle"]),
            provider=value["provider"],
            model=value["model"],
            prompt_version=value["prompt_version"],
            task_type=value["task_type"],
            previous_assessment_id=value["previous_assessment_id"],
        )
        previous = None
        if job.task_type != "INITIAL_ASSESSMENT":
            previous = self.restore_previous_assessment(
                job.previous_assessment_id, seen
            )
        context = AssessmentContext(job, previous=previous)
        if context.context_hash != payload["context_hash"]:
            raise ContractError("stored prepared-job context hash mismatch")
        if (
            job.bundle.identity.run_id != record["run_id"]
            or job.bundle.identity.ticker != record["ticker"]
        ):
            raise ContractError("stored job row identity differs from evidence")
        expected_id = digest({
            "run": record["run_id"],
            "ticker": record["ticker"],
            "job": job.job_key,
            "context": context.context_hash,
            "request": payload["request_fingerprint"],
            "payload": canonical(payload),
            "attempts": record["max_attempts"],
            "ceiling": record["ceiling"],
            "initial_status": "PREPARED",
        })
        if expected_id != record["id"]:
            raise ContractError("stored prepared-job identity hash mismatch")
        return context


class _DisabledTransport:
    """Build request identities without providing an execution capability."""
    def create(self, request, *, timeout_seconds):
        raise ContractError("provider transport is disabled during job preparation")
