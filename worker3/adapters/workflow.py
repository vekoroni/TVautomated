"""Validated AI -> durable result -> repeatable Lab projection.

Callers supply the same frozen context after restart; no implicit latest lookup.
"""
from dataclasses import asdict
from datetime import datetime, timezone

from ..application import ProviderResponse
from ..domain import ContractError
from ..semantic import review_assessment


def enqueue_assessment(jobs, adapter, *, now, ceiling_microusd):
    context=adapter.context
    return jobs.enqueue(run_id=context.job.bundle.identity.run_id,ticker=context.job.bundle.identity.ticker,
        job_key=context.job.job_key,context_hash=context.context_hash,
        request_fingerprint=adapter.request_fingerprint(context.job),
        payload={"context_hash":context.context_hash,"request":adapter.request_for(context.job)},
        now=now,call_ceiling_microusd=ceiling_microusd)


def project_completed(jobs, reports, job_id, context):
    saved=jobs.completed_result(job_id)
    if saved is None:
        raise ContractError("no durable completed assessment to project")
    if saved["context_hash"]!=context.context_hash:
        raise ContractError("projection context differs from frozen job")
    response=ProviderResponse(**saved["provider_response"])
    # save_draft revalidates schema, identities and semantic policy.
    assessment_id = reports.save_draft(
        context, response, generated_at=saved["generated_at"]
    )
    jobs.record_assessment(
        assessment_id=assessment_id,
        job_id=job_id,
        run_id=context.job.bundle.identity.run_id,
        ticker=context.job.bundle.identity.ticker,
        context_hash=context.context_hash,
        evidence_cutoff=context.job.bundle.evidence_cutoff_utc,
        generated_at=saved["generated_at"],
    )
    return assessment_id


def run_assessment(jobs, reports, adapter, *, clock, ceiling_microusd):
    context=adapter.context
    job_id=enqueue_assessment(jobs,adapter,now=clock(),ceiling_microusd=ceiling_microusd)
    if jobs.completed_result(job_id) is not None:
        return {"job_id":job_id,"assessment_id":project_completed(jobs,reports,job_id,context),"provider_called":False}
    claim=jobs.claim(now=clock(),lease_seconds=120,job_id=job_id)
    if claim is None:
        raise ContractError("job unavailable; inspect progress or reconcile uncertain dispatch")
    # Request equality before committing a paid call.
    if claim['payload']!={"context_hash":context.context_hash,"request":adapter.request_for(context.job)}:
        jobs.fail_before_send(job_id,claim['token'],now=clock(),reason_code="REQUEST_MISMATCH")
        raise ContractError("stored request mismatch")
    jobs.dispatch(job_id,claim['token'],now=clock())
    try:
        response=adapter.generate(context.job)
        semantic=review_assessment(context,response)
        generated_at=datetime.fromtimestamp(clock(),timezone.utc).isoformat()
        saved={"context_hash":context.context_hash,"provider_response":asdict(response),
               "generated_at":generated_at,"semantic_status":semantic.status}
        # Whitelist transport telemetry. Never persist raw error messages/headers.
        receipts=getattr(adapter.transport,"receipts",[])
        last=receipts[-1] if receipts else {}
        receipt={key:last.get(key) for key in ("request_hash","http_status","input_tokens","output_tokens","elapsed_ms")}
        jobs.finish(job_id,claim['token'],now=clock(),response=saved,receipt=receipt,cost_microusd=None)
    except Exception:
        try: jobs.mark_uncertain(job_id,claim['token'],now=clock())
        except ContractError: jobs.recover(now=clock())
        raise ContractError("assessment failed after dispatch; inspect durable state before retry") from None
    # Separate projection: if this fails, durable response survives and no AI rerun
    # is needed. The fixed generated_at makes projection idempotent.
    return {"job_id":job_id,"assessment_id":project_completed(jobs,reports,job_id,context),"provider_called":True}
