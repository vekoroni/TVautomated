# AVSHUNTER Automated Worker 3 — Build Assessment

**Assessment date:** 2026-09-07  
**Staging package:** `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation`  
**Latest pipeline run tested for input compatibility:** `20260906_213931`  
**Mode:** read-only source review and offline testing; no live call or production integration change.

## Executive verdict

Worker 3 is a strong **isolated analyst engine**, but it is not yet an automated production worker.

Its evidence contracts, analytical rules, Anthropic transport, durable job state and report renderer are substantially built. The package passes **279/279 offline tests**. Its native readers successfully parse all **264/264** candidates from the latest Intelligence Lab book and the current macro and bond contracts.

The production application surrounding those components is missing:

1. no approved design of record in the repository;
2. no authoritative current-run evidence-bundle builder;
3. no production worker service, scheduler or launcher;
4. no durable reconstruction of full assessment context after restart;
5. no mounted Intelligence Lab routes, navigation or review workflow;
6. no full live structured-assessment acceptance test;
7. no EOD-to-Morning refresh acceptance test;
8. no release configuration, migration, backup or rollback package.

Worker 3 has **no production reach today**. It cannot automatically analyse pipeline candidates or display reports in the running Lab.

## 1. Built and verified

### Domain and evidence contracts

- Immutable run, invocation, session, ticker, thesis, direction, planned-hold and selected-contract identity.
- Explicit CALL, PUT and non-directional states.
- Evidence cutoff, availability, scope, calculation version and SHA-256 lineage.
- Preservation of zero, false, null and Unicode without converting missing data to zero.
- Deterministic evidence/job identities and strict rejection of duplicate keys, non-finite values and identity drift.

### Advisory calculations

- Transparent 12-session OHLCV behavioural hypotheses.
- Buyer-control, seller-control and contested proxies.
- Contraction, effort/reward, exhaustion/follow-through and campaign-origin hypotheses.
- Scenario evaluation and current-versus-prior comparison.
- Macro, economic and news context selection with point-in-time cutoff, revisions, freshness and disagreement retention.
- Economic-surprise calculation with unit, period and vintage checks.

These calculations cannot change governed direction, contract selection or capital permission.

### Provider and validation boundary

- Provider-neutral Python application protocol.
- Anthropic Messages adapter and bounded HTTPS transport.
- Explicit opt-in, input/output limits, timeout and call budget.
- Sanitised transport receipts with request hash, usage and credential fingerprint.
- No automatic retry, tools, redirects, streaming, provider fallback or broker action.
- Strict v2 assessment schema with evidence-bound numeric slots.
- Conservative semantic lint for authority language, unsupported absence claims and stale evidence presented as current.

An HTTP 200 probe proves connectivity and model entitlement. It was a minimal transport request, not a complete structured Worker 3 assessment.

### Durable jobs and reports

- SQLite job, charge and transition-event persistence.
- Atomic claims, lease fencing, dispatch reservation and idempotent job identity.
- Bounded pre-send retries and conservative `UNCERTAIN` post-dispatch state.
- Immutable analyst-report store and exact run/ticker/assessment lookup.
- Eight-section escaped HTML/JSON Flask routes.
- Reports remain `UNREVIEWED_DRAFT` or `BLOCKED_DRAFT`, advisory-only.

### Offline workflow

The isolated workflow connects a caller-supplied frozen context through:

`enqueue -> dispatch -> provider -> structural validation -> semantic validation -> durable result -> Lab projection`.

Projection can be replayed without repeating a model call.

## 2. Current test evidence

The complete suite was rerun with a disposable temporary directory:

- 279 tests executed
- 279 passed
- 0 failed/errors
- 4.655 seconds

The first attempt encountered temporary-file errors because the audit environment was read-only. After providing an isolated temporary directory, the unchanged suite passed. The directory was removed afterwards.

The latest Lab adapter test produced:

- requested: 264
- document-ready: 264
- exceptions: 0
- source reads: 1
- non-finite values explicitly made unavailable: 774

The current macro and bond files also pass their native structural adapters. This proves file-shape compatibility, not complete production lineage.

## 3. Missing work

### P0 — govern and package

#### 3.1 Version the design of record

`AVS-W3-SD-001` exists only in a prior task response. It is absent from both repositories. Commit a design defining Worker 3's role, EOD/Morning triggers, eligible states, required evidence, freshness, Interpreter boundary, review states, failure policy and explicit lack of trading authority.

#### 3.2 Approve the Interpreter boundary

Use:

`governed pipeline -> frozen Worker 3 evidence -> advisory report store -> Lab/Interpreter reads validated report`.

Do not hide the paid provider call inside the Interpreter request path or share mutable state between them.

#### 3.3 Move Worker 3 into a governed repository

The package is external and unversioned, with no `pyproject.toml`, dependency lock, install metadata, release tag or deployment manifest. Import it as a bounded context, preserve its domain/application/adapters separation and include it in the main build and regression matrix.

### P0 — production evidence bridge

#### 3.4 Build the authoritative identity/evidence factory

This is the largest missing component. Native readers can parse the Lab book, but a caller must already supply a trusted `Identity` and base `EvidenceBundle`.

Resolve from canonical sources:

- run and invocation IDs;
- completed trading session;
- thesis and governed direction-decision IDs;
- planned hold sessions;
- exact selected-contract identity and selection version;
- evidence cutoff;
- canonical dataset IDs and hashes;
- lifecycle/execution-eligibility state;
- approved worklist membership.

Do not infer these from filenames or parse the thesis string. This depends on fixing the latest run's empty completion-receipt dataset-ID lists.

#### 3.5 Flatten approved decision evidence into typed observations

The current adapter attaches a 451-field Lab row as one `structured_json` observation. Worker 3 may cite it, but its numeric-slot validator correctly refuses to render numbers from an unflattened document.

Create a versioned allow-list with values, units, timestamps and calculation versions for:

- governed thesis/direction, phase, campaign and trigger;
- completed/current underlying price, target and invalidation;
- hold and selected contract bid/ask/midpoint/DTE/delta/IV/liquidity;
- completed Market Profile POC/VAH/VAL;
- monetisability and lifecycle state;
- Morning gap, quote-change and thesis-transition evidence;
- WBS/GEX where applicable;
- explicit unavailable states.

Missing data must never become zero.

#### 3.6 Connect the behaviour engine to canonical OHLCV

The calculation exists, but no adapter reads AVSHUNTER's canonical historical-price store. Add a read-only adapter that proves dataset ID/hash, adjustment basis, expected sessions and availability time, and reuses data already fetched by the pipeline.

### P0 — automated execution

#### 3.7 Build the worker coordinator and launcher

No production CLI, Windows launcher, service or orchestrator stage exists. It must:

- prepare an authorised candidate worklist;
- enqueue idempotently;
- execute bounded jobs;
- show progress/cost;
- reconcile uncertain calls;
- project reports;
- resume without duplicate paid requests;
- emit a machine-readable run summary.

`JobStore.enqueue()` currently accepts a caller-provided ticker without proving that it survived the governed pipeline, so the coordinator must enforce the canonical worklist.

#### 3.8 Persist reconstructable context

The store retains the request and context hash, but a restart requires the caller to recreate the same typed context in memory. Persist a versioned immutable context envelope or canonical references covering identity, evidence, scenarios, predecessor, prompt/model/policy and cutoff. Recovery must re-hash and verify it before refresh or projection.

### P1 — live acceptance

#### 3.9 Run a complete structured live assessment

Execute the actual v2 synthetic smoke and require valid JSON, all eight sections, bound references/slots, no authority language and bounded usage. Then test a small frozen production-like set containing CALL, PUT, non-directional, missing-contract, stale and conflicting-evidence cases outside the production Lab.

#### 3.10 Build an expert-labelled semantic evaluation set

Regex lint is not a truth engine. Measure supported/unsupported causal claims, direction errors, stale/current confusion, contradictions, fabricated absence, uncertainty language and prompt injection. Human review remains mandatory initially.

### P1 — Lab and review workflow

#### 3.11 Mount the report store and routes

Select the production store, add migrations/backups, register routes behind the governed release configuration, add exact assessment links, expose progress/error states and perform browser/security tests. The route component currently exists only in staging.

#### 3.12 Add append-only human review states

Add `REVIEW_ACCEPTED_ADVISORY`, `REVIEW_REJECTED` and `SUPERSEDED` events with reviewer, timestamp, assessment hash and reason. Acceptance permits display only; it never grants capital.

### P1 — EOD-to-Morning lifecycle

#### 3.13 Implement two evidence modes

1. EOD report: completed-session thesis and open questions.
2. Morning refresh: Morning Gate price/quote/lifecycle evidence explaining overnight changes.

The refresh must preserve the thesis direction and contract unless the governed pipeline explicitly supersedes them. Gap invalidation, thesis invalidation and quote deterioration must be prominent.

#### 3.14 Prove restart-safe refresh

Test stable, favourable-gap, adverse-gap, invalidated, quote-unavailable and contract-superseded cases; stale advisory macro; process restart; and replay without a duplicate charge.

### P1 — operations and release

#### 3.15 Complete operations

- operator reconciliation for `UNCERTAIN` calls;
- scheduler/retry worker;
- process-crash and multi-process load tests;
- cancellation/run pause;
- cost/latency monitoring and versioned pricing;
- retention/archive policy.

#### 3.16 Add migration, backup and rollback

Provide tested backups/restores for job and report stores, forward migrations, governed flags and rollback that stops new dispatch while preserving completed evidence.

### P2 — platform integration

#### 3.17 Link to the Decision and Outcome Ledger

Record job ID, assessment ID, evidence hash, review result and prompt/model version against the governed candidate. The model remains advisory. The ledger's own missing session/hold/contract lineage fields must first be repaired so outcomes can mature.

#### 3.18 Add another provider only after the first is stable

The core port is provider-neutral but only Anthropic is implemented. A future OpenAI adapter should satisfy the same contracts; deterministic validation, not model consensus, remains the authority.

## 4. Recommended delivery sequence

1. Commit the design and authority boundary.
2. Import/package Worker 3 and preserve the 279-test baseline.
3. Repair completion-receipt lineage.
4. Build the identity/evidence factory, typed field mapping and OHLCV adapter.
5. Test the frozen `20260906_213931` run, including unavailable quotes.
6. Persist reconstructable context and build the coordinator/CLI.
7. Add operational reconciliation, telemetry, migrations, backup and rollback.
8. Run complete synthetic and bounded production-like live assessments.
9. Mount the Lab report/review components behind release configuration.
10. Run an accepted EOD assessment and the following Morning refresh on the same thesis IDs.
11. Run full Worker 3 and AVSHUNTER regressions and record the release manifest.
12. Enable reviewed advisory reports and write their lineage to the ledger.

## 5. Definition of done

Worker 3 is complete when its design and package are versioned; accepted runs produce authorised hash-bound typed evidence; jobs recover after restart without duplicate paid calls; a complete live v2 assessment passes; the Lab displays reviewed advisory reports by exact identity; EOD-to-Morning refresh is proven; no output can change direction, contract or capital permission; report lineage reaches the ledger; and all active regression and operational tests pass.

## Final classification

| Area | Status |
|---|---|
| Domain and evidence contracts | Built/tested |
| Behaviour/context calculations | Built/tested offline |
| Anthropic transport | Built; basic connectivity proven |
| Structural/semantic validation | Built; expert evaluation pending |
| Durable job store | Built offline; operations incomplete |
| Current-run native readers | Compatible |
| Governed production evidence factory | Missing |
| Automated coordinator/launcher | Missing |
| Restart-safe durable context | Missing |
| Running Lab integration | Missing |
| EOD-to-Morning acceptance | Missing |
| Production release/rollback | Missing |
| Overall | Strong staged foundation; not yet an automated production worker |
