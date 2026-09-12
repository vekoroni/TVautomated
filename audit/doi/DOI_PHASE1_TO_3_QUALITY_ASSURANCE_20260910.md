# DOI-1 to DOI-3 Quality Assurance

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Decision:** OFFLINE PASS AFTER TWO BOUNDARY REPAIRS  
**Scope:** Previously implemented DOI-1, DOI-2 and DOI-3 functionality

## Executive result

The implemented foundation conforms to the design after correcting two
integration-boundary defects found by this review. It preserves the governed
ticker thesis, keeps execution authority human-only, binds option facts to the
canonical MarketData registry, reuses evidence before acquisition, and stores
DOI history append-only in the existing control-plane database.

This is evidence that the foundation is fit for the next build phase. It is
not a profitability claim and is not final production acceptance. The complete
business outcome depends on DOI-4 through DOI-11, historical outcome evidence,
and a fresh completed-session/Morning Gate acceptance cycle.

## Defects found and repaired

1. **EIL advisory boundary was configurable.**
   `run_execution_intelligence_layer` still permitted
   `EIL_ADVISORY_ONLY=false` to append `--live`. DOI-1 requires EIL to remain
   compatibility telemetry. The orchestrator now fixes advisory mode to true
   and cannot restore EIL gating from operator shell state.
2. **Canonical reuse was not request-scope aware.**
   The DOI-3 bridge selected a chain by ticker and session without verifying
   that its `DataScope` covered the requested family scope. Resolution now
   accepts `required_scope`, includes its fingerprint in acquisition identity,
   rejects underscoped cached/acquired evidence, and still suppresses needless
   dormant acquisition.

Additional compatibility verification covered the production MarketData
schema aliases `expiration_ts` and `iv`.

## Design-to-build assurance

| Design requirement | Evidence | Result |
|---|---|---:|
| EIL has no thesis/capital authority | Permanent orchestrator advisory guard and static governance test | PASS |
| EIL values do not change EOD tier/score | Direct non-discard policy tests | PASS |
| Domain objects have no provider/UI/database dependency | Import and source-boundary tests | PASS |
| DOI cannot change direction, invalidate thesis or grant capital | Immutable domain validation | PASS |
| Append-only persistence in existing control plane | schema, trigger, idempotency and conflict tests | PASS |
| Exact contract and canonical dataset lineage | assessment/lifecycle tests | PASS |
| Reuse first; fetch missing only | canonical hit/miss/restart tests | PASS |
| Reuse covers requested scope | narrow-versus-broad scope regression | PASS |
| Dormant/breached/elapsed opportunities remain but avoid repeated calls | acquisition-state matrix | PASS |
| Missing data remains null | activity feature fixtures | PASS |
| Phantom is read-only historical context | point-in-time lineage tests | PASS |
| PCR is scoped chain context, not a selected-contract property | total/expiry/region/delta fixtures | PASS |

## Executed evidence

- Focused DOI/canonical/lifecycle suite: **44 passed, 0 failed**.
- Wider executable governance/handoff selection: **65 passed, 0 product
  failures**.
- Direct pytest-style DOI non-discard functions: **4 passed, 0 failed**.
- Python compilation of all changed DOI-1 to DOI-3 modules: **PASS**.
- Resource warnings promoted to errors in the focused suite: **0**.

One retired legacy module imports `pytest` solely to skip itself. The available
Python 3.14 runtime does not contain pytest, so that module produced a collection
environment error and was not counted as passed. Its stated production
replacement suites were included in the wider run. This is test-environment
debt, not evidence of a product failure.

## Promotion boundary

- No production database or run output was changed by QA.
- Backups for the pre-DOI-4 boundary are in
  `backups/doi_phase4_20260910/`.
- The latest stored full pipeline run predates these DOI changes. A fresh run
  remains required at DOI-11 to verify real population reconciliation and Lab
  projection.
- QA authorises DOI-4 development; it does not authorise an automated trade or
  claim that monetisation probabilities are calibrated.
