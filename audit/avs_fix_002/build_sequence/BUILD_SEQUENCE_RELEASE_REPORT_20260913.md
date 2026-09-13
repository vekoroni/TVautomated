# AVS-FIX-002 build-sequence release report

**Date:** 2026-09-13  
**Branch:** `avs-fix-001`  
**Baseline commit:** `cc509cbe7fa60a3fb2f7a37a164a66f27588251d`  
**Status:** `OFFLINE_TESTED_PENDING_GIT_GOVERNANCE`  
**Production acceptance cycle:** not started

## Delivered slices

1. Canonical database projection and completed-session GEX refresh.
2. Provider quote timestamp truth and explicit spread units.
3. Contract-family retention, v2 deterministic ranking and monetisability projection.
4. Intelligence Lab v4 presentation, current-book schema compatibility and freshness display.
5. Capital-allocation isolation and removal of hard-coded provider credential fallbacks.
6. Grain-specific DOI population reconciliation and repaired regression assertions.

## Business invariants verified

- Missing, stale, zero-bid or wide option quotes do not delete or invalidate a ticker thesis.
- A wide spread is retained as `EXECUTION_WIDE_SPREAD_MONITOR`, not a thesis veto.
- `EXECUTION_EXECUTABLE_NOW` requires a current provider-timestamped quote; completed-session evidence cannot mint it.
- Missing Morning underlying price yields `THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE`, not a false invalidation.
- Low OI and zero volume remain ranking/activity evidence and do not remove the contract family.
- v1 disclosure utility cannot be mixed into v2 ranking.
- The Lab accepts the current `lab_signal_book_v4` contract and preserves the complete governed population.
- EIL remains advisory; no capital-sizing recommendation is produced.
- Macro remains advisory and its numeric priority is distinct from its routing key.
- Dataset projection failures are observable through the durable outbox and do not mutate immutable source evidence.

## Verification evidence

| Pack | Result |
|---|---:|
| Focused defect reproductions | 81 passed |
| Consolidated AVS-FIX-002/domain/integration pack | 499 passed |
| Independent MSI flow/functionality/logic pack | 176 passed, 2 skipped, 20 subtests passed |
| Production-module compilation | passed |
| `git diff --check` | passed |
| Stage 0 governance | 3 passed, 1 blocked by untracked reachable production dependencies |

The Stage 0 failure is not a functional failure. Eight new production dependencies are not yet tracked because the Codex sandbox SID has an explicit Windows ACL `Deny Write` on `.git`, preventing creation of `.git/index.lock`:

- `canonical_data/benchmark_option_chain.py`
- `canonical_data/macro_gex_overlay.py`
- `canonical_data/marketdata_option_chain.py`
- `canonical_data/phantom_option_projection.py`
- `canonical_data/projection_outbox.py`
- `domain/actuarial_observation.py`
- `domain/data_projection.py`
- `orchestrator/completed_session_gex.py`

## Release decision

Do not label a pipeline run as the controlled completed-session acceptance cycle until the scoped commits have been created and the Stage 0 test passes. The repository-side helper `COMMIT_BUILD_SEQUENCE.ps1` performs only the two governed commits and then reruns Stage 0. After that gate passes, run the normal completed-session pipeline without `--force`.

