# AVS-FIX-002 Stage 6 Closure Report

**Prepared:** 2026-09-12
**Branch:** `avs-fix-001`
**Base commit:** `3e660bd2483563e092308df7eaac6cbfbb6268ca`
**Verdict:** OFFLINE COMPLETE; COMPLETED-SESSION ACCEPTANCE PENDING; MODEL ACTIVATION GATED

## Outcome

Stage 6 now supplies the append-only outcome and learning infrastructure required to learn from the full Intelligence Lab population without allowing a statistical model to become trading authority. It records actual and counterfactual observations at 1, 2, 3, 5, 10 and 20 completed sessions, preserves missing or immature evidence as named states, and produces a point-in-time learning snapshot with explicit population reconciliation.

The implementation does not train or activate a model. Deterministic DOI, Morning validation, Execution Gate and human execution remain the production authority chain.

## Functional changes

1. Added domain-owned outcome labels, attribution vocabulary, learning strata and activation policy.
2. Extended the append-only ledger with `OUTCOME_OBSERVATION` for deferrals and data exceptions.
3. Extended candidate evidence with preferred contract, completed-session, run-condition, baseline-eligibility and point-in-time cutoffs.
4. Expanded maturation from four horizons to six and made every candidate/horizon accountable.
5. Added canonical option-label joins and family-member counterfactual comparison without provider fetching.
6. Added date-ordered train/validation/test planning with a governed 20-session purge/embargo.
7. Added an orchestrated, non-critical learning snapshot and a standalone read-only readiness CLI.
8. Corrected actual-trade outcome lineage to prefer the recorded fill event before entry or execution decisions.

## Current evidence state

The read-only production snapshot found:

- Presented historical candidates in scope: **3,252**.
- Expected candidate/horizon observations under the new six-horizon contract: **19,512**.
- Stage 6 observations already present: **0**.
- Fit-eligible records: **0**.
- Model state: **INSUFFICIENT_OUTCOMES**.
- Activation: **false**.

This is expected because the stored ledger predates the Stage 6 evidence contract. Historical absence is not converted to zero and is not silently treated as a failed trade. New normal completed-session runs will append governed observations. Legacy backfill, if ever authorised, must use point-in-time evidence and the same reconciliation rules.

## Model activation gates

Activation remains disabled unless all governed conditions pass: minimum 200 fit-eligible outcomes; minimum 100 observations in every CALL/PUT × hold-bucket stratum; at least 60% observable coverage; time-ordered partitions; confidence intervals and stability evidence; held-out log loss; overall ECE ≤ 0.10; stratum ECE ≤ 0.15; positive Brier Skill Score; ROC-AUC strictly above 0.50; PR-AUC above base rate; top-quintile lift above 1.0; and a separate governed release approval.

Even if every statistical gate passes, the result is only `ELIGIBLE_FOR_OPERATOR_REVIEW`; it cannot grant capital.

## Verification evidence

- Focused Stage 6 tests: **22 passed**.
- Consolidated pack: **425 tests / 0 failures / 0 errors / 0 skipped**, including 74 property subtests.
- Stored-run replay: PASS for `20260910_150045` and `20260911_115904`.
- Read-only production snapshot: PASS; the ledger file timestamp remained unchanged.
- Python compilation: PASS.
- Provider calls: **0**.
- Production pipeline runs: **0**.
- Database migrations: **0**.

The sole test warning is the repository's pre-existing Windows `.pytest_cache` creation warning; it does not affect test execution or production data.

## Production impact and next acceptance step

The next normal completed-session pipeline run will append Stage 6 observations after existing deterministic stages and publish `diagnostics/outcome_learning_<run_id>.json`. If Stage 6 cannot read sufficient evidence, it reports a named deferred/data-exception state and leaves deterministic DOI active.

Production acceptance requires verifying that the first new run accounts for every presented candidate at every configured horizon as one of complete, deferred or data exception. No Morning session is required to establish the Stage 6 capture mechanics; later completed sessions are required to mature the labels.

## Rollback

Rollback is code-only to base commit `3e660bd2483563e092308df7eaac6cbfbb6268ca`. No schema migration was performed. Ledger events are append-only audit evidence and must never be deleted or rewritten as a rollback mechanism.
