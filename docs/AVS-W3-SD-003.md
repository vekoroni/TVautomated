# AVS-W3-SD-003 — Controlled provider activation and advisory projection

Status: functionality implemented; production release installed disabled
Live provider calls: not authorised
Trading authority: none

## Purpose

Add the controlled boundary that can promote specifically approved Worker 3
jobs from `PREPARED` to `QUEUED`, call one allow-listed provider/model, validate
the response, perform semantic review, persist it durably and expose the result
as a human-review-only Intelligence Lab report.

## State sequence

```text
PREPARED
  -> explicit release + operator approval
QUEUED
  -> lease + request-fingerprint verification + budget reservation
DISPATCHED
  -> provider response + structural validation + semantic review
REVIEW_REQUIRED
  -> advisory Lab report projection

Any uncertain post-dispatch result -> UNCERTAIN (never retried automatically)
Any invalid pre-dispatch request -> RETRY_WAIT/FAILED without a provider call
```

## Controls

- The production release contract is `INSTALLED_DISABLED` and contains no
  approved model or nonzero pricing schedule. It cannot activate a job.
- Enabling requires a versioned `CONTROLLED_ACTIVE` release containing an exact
  model allow-list, token-price schedule, job count, process call count, total
  cost, per-call cost, input byte, output token and timeout ceilings.
- Activations are atomic and all activation batches sharing a release hash
  consume one cumulative reserved-cost ceiling; splitting a worklist cannot
  bypass that ceiling.
- Every activation binds job ID, release ID/hash and operator approval ID in an
  append-only activation record.
- The exact provider request is fingerprinted during preparation and verified
  again after lease but before dispatch.
- Provider/model fallback, retries, tools, streaming and direction/contract
  changes are not permitted.
- The response must pass the v2 structural contract and deterministic semantic
  review before durable completion.
- Reports remain `BLOCKED_DRAFT` or `UNREVIEWED_DRAFT`, require human review and
  always carry `execution_permission=false`.
- A projection failure does not repeat a paid call; the durable response is
  projected on the next attempt.
- A post-dispatch attempt consumes the process call allowance even when its
  returned content is invalid and retained as `UNCERTAIN`.

## Intelligence Lab projection

`install_worker3_lab_projection` mounts exact run/ticker/assessment routes only
when the provider release and Lab projection are both enabled. It creates a
separate `data/worker3/analyst_reports.sqlite` store and does not modify the
existing Lab signal book or trading verdicts. The production Lab invokes this
mount at startup, but the checked-in disabled release makes it a no-op. An
invalid optional release leaves the core Lab available and emits a warning;
it never grants a fallback advisory or trading authority.

## Production activation prerequisites

1. Select and approve the exact provider model.
2. Record its current input/output token prices in microusd per million tokens.
3. Select the initial ticker worklist and cost ceiling.
4. Change the provider release to `CONTROLLED_ACTIVE` through a reviewed release.
5. Stage jobs using the exact same request limits.
6. Execute a one-job canary, inspect the semantic findings and Lab report.
7. Reconcile usage/cost and only then expand the worklist.

Until these steps are accepted, no live model call should be attempted.

## Implementation verification — 2026-09-07

- Controlled activation, immutable release binding, request-fingerprint
  revalidation, durable response storage, semantic review, replay-safe Lab
  projection and fail-closed uncertain-state handling are implemented.
- The original isolated Worker 3 suite passes `279/279` against the integrated
  package.
- The AVSHUNTER source bridge, coordinator and activation suites pass `31/31`,
  including cumulative release-cost enforcement and post-dispatch call caps.
- A production-shaped offline smoke used governed run `20260906_213931`:
  `264` candidates were read, `256` prepared and `8` isolated as explicit data
  exceptions. One `STNE` job reached `REVIEW_REQUIRED` and a `BLOCKED_DRAFT`
  Lab report through a fake transport; execution permission remained false.
- No network/API call, live provider charge, pipeline output mutation or
  production database write was made during verification.
- The checked-in provider release remains `INSTALLED_DISABLED`; therefore this
  phase installs capability without silently activating paid model execution.
