# AVS-W3-SD-002 — Durable Worker 3 intake and coordinator

Status: implemented in PREPARE_ONLY mode
Provider dispatch: disabled
Intelligence Lab projection: disabled
Trading authority: none

## Objective

Persist one immutable, provider-neutral Worker job for every evidence bundle
accepted by AVS-W3-SD-001. Preserve source exceptions alongside prepared jobs,
make restarts idempotent, and prevent staging from becoming an accidental paid
model invocation.

## Flow

```text
explicit completed run_id
  -> governed source bridge
  -> EVIDENCE_PREPARED -----------------> WorkerJob + context hash
  |                                          |
  |                                          v
  |                                  durable PREPARED job
  |                                  (not claimable)
  |
  -> DATA_EXCEPTION --------------------> durable intake exception

No provider dispatch / no Lab projection / no pipeline database write
```

## Persistence model

The existing tested `JobStore` remains the sole Worker job database. This slice
adds:

- `PREPARED` jobs containing the complete immutable evidence bundle,
  provider/model/prompt versions, policy hash, job key and context hash;
- append-only idempotent intake records for `JOB_PREPARED` and
  `DATA_EXCEPTION` outcomes;
- exact restart restoration with reconstruction and hash revalidation.

The existing dispatcher claims only `QUEUED` and `RETRY_WAIT`. It cannot claim
`PREPARED`, so provider execution is structurally unavailable in this phase.

## Authority and safety rules

- The integration policy must be exactly `ACTIVE_PREPARE_ONLY`.
- `provider_dispatch_enabled`, `lab_projection_enabled` and
  `pipeline_production_writer_enabled` must all remain false.
- Jobs and intake records are advisory and explicitly carry
  `capital_permission=false`.
- A bad ticker is recorded as `DATA_EXCEPTION`; valid peers continue.
- Re-running the same frozen run/configuration returns the same job and intake
  IDs without duplicate rows.
- A changed provider, model, prompt, policy, evidence bundle or job constraint
  produces a different durable job identity.
- Stored job restoration recomputes the job identifier from the row identity,
  request fingerprint, immutable payload and retry/cost constraints.
- The runner requires an explicit run, provider, model, budget and per-call
  ceiling. Its database is confined to `data/worker3`.

## Acceptance tests

1. CALL and PUT bundles stage as `PREPARED`.
2. Source exceptions persist but create no job.
3. Prepared jobs cannot be claimed or dispatched.
4. Repeated intake is idempotent.
5. Restart restoration reproduces job key, evidence hash and context hash.
6. Tampered payloads or changed policies fail closed.
7. Provider/model/prompt and advisory authority persist exactly.
8. Accounting remains zero before activation.

## Deferred activation phase

A later, separately approved phase must introduce an explicit signed promotion
from `PREPARED` to `QUEUED`, the real provider adapter, response validation,
semantic review and optional Lab draft projection. This document does not
authorise or implement that transition.

## Implementation validation — 2026-09-07

- Coordinator and source-bridge tests: 18 passed, 0 failed.
- Existing Worker 3 regression pack: 279 passed, 0 failed.
- Real completed-run smoke test (`20260906_213931`): 256 durable jobs
  prepared and 8 source data exceptions recorded from 264 requested tickers.
- All 256 jobs remained `PREPARED`; the dispatcher claim returned no job.
- Restart reconstruction reproduced the exact evidence and context hashes.
- Provider calls, charges, unknown-cost reservations and pipeline production
  writes were all zero.
- The disposable smoke database was removed automatically; no live Worker job
  database was created by the implementation test.
