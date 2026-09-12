# AVS-FIX-002 Stage 6 — Outcome Capture and Learning Infrastructure

**Status:** OFFLINE COMPLETE — MODEL ACTIVATION GATED
**Design controls:** FINAL v1.2 Stage 6; REQ-WP4; REQ-WP7B; ALG-08; ALG-09

## Requirement-to-code claim

| Requirement | Implementation | Evidence |
|---|---|---|
| Capture every presented candidate, not only executed trades | `canonical_data/outcome_maturation.py` and `canonical_data/decision_outcome_ledger.py` | All-presented population and six-horizon reconciliation tests |
| Observe 1, 2, 3, 5, 10 and 20 completed sessions | `STAGE6_OUTCOME_HORIZONS` | Unit, integration and idempotency tests |
| Keep incomplete evidence explicit | `OUTCOME_OBSERVATION` events with `DEFERRED_NOT_YET_OBSERVABLE` or `DATA_EXCEPTION` | Incomplete-history and defective-candidate tests |
| Label competing target/invalidation events without invented intraday order | `domain/outcome_learning.py` | Four-state label tests; ambiguous same-session cases excluded from fitting |
| Preserve CALL/PUT symmetry | Direction-normalised path calculations | Property tests across both directions and multiple moves |
| Separate thesis, contract, liquidity, execution, volatility and timing attribution | `OutcomeAttribution` vocabulary | Domain-contract tests and snapshot schema |
| Join option outcomes only from canonical point-in-time labels | `canonical_data/outcome_learning.py` | Exact assessment/horizon join and alternative-contract test |
| Prevent look-ahead leakage | Feature/outcome cutoffs plus date-ordered purge/embargo partition plan | Timestamp invariant and temporal partition tests |
| Make hierarchical backoff explicit | `LearningStratum.backoff_chain()` | Ordered backoff test with `UNAVAILABLE` retained |
| Gate model activation on evidence, calibration and held-out performance | `assess_model_activation()` | Insufficient-evidence, metric-boundary and release-approval tests |
| Keep deterministic DOI active if learning is absent or fails | Orchestrator learning stage is observational and non-critical | Wider DOI/execution/Lab regression pack |
| Provide a genuinely read-only readiness assessment | `DecisionOutcomeLedger(read_only=True)` and `tools/build_outcome_learning_snapshot.py` | Read-only connection test and production-ledger snapshot |

## Authority statement

Stage 6 is `OBSERVATION_ONLY`. It cannot grant capital, alter direction, replace a contract, discard a trade or change deterministic execution authority. The governed configuration keeps `model_activation_enabled` false. Passing future evidence gates can only move a model to operator review; activation still requires a separate governed release decision.

## Verification

- Stage 6 focused pack: **22 passed, 0 failed**.
- Consolidated regression: **425 tests, 0 failures, 0 errors, 0 skipped** (351 ordinary tests plus 74 subtests).
- Stored-run replays: `20260910_150045` and `20260911_115904`, with no provider calls and no production writes.
- Production-module compilation: PASS.
- Current readiness assessment: `INSUFFICIENT_OUTCOMES`; activation false.

## Acceptance still pending

- One normal completed-session pipeline run to create Stage 6 events with the new evidence contract.
- Reconciliation of every presented candidate across all six horizons as complete, deferred or data exception.
- Subsequent horizon maturation as completed sessions become observable.
- Sufficient CALL/PUT and holding-bucket samples, time-ordered held-out evaluation, calibration/stability evidence and explicit operator release approval before any model activation.
