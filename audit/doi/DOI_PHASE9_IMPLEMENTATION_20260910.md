# DOI-9 Contract-Family Ranker — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Implementation result:** OFFLINE ACCEPTED  
**Production calibrated-ranking status:** NOT ACTIVE — NO REAL ACCEPTED MODEL OR POLICY  
**Active fallback:** DOI-5 deterministic assessment

## Delivered

- A pure domain ranker that retains every contract-family candidate and never
  changes thesis direction, invalidates a thesis, grants capital or executes.
- A versioned ranking utility covering DOI-5 deterministic score, DOI-8
  three-session liquidity probability, positive-return probability,
  target-before-invalidation probability and model uncertainty.
- Whole-family deterministic fallback when the ranking policy is not accepted,
  a comparable candidate lacks calibrated evidence, or a target has ambiguous
  accepted inference rows.
- Chronological replay tuning with purged train/validation/holdout cohorts.
- A replay-learned hysteresis margin; no production margin is fabricated from
  synthetic tests.
- Acceptance gates requiring positive untouched-holdout lift, no coverage
  reduction and non-inferiority in every eligible temporal holdout window.
- Preferred and alternative explanations, exact assessment/model/dataset
  lineage and deterministic, independently checked identities.
- Append-only policy and family-ranking tables in the existing canonical
  control plane. Initialisation remains explicit and was executed only against
  disposable test databases.
- Lazy canonical exports so the application service loads only when requested.

## Business invariants

1. A temporary quote, low OI, zero volume, wide spread, timing state or missing
   model output cannot discard a ticker or contract-family member.
2. CALL and PUT families use the same computation with direction-bound inputs.
3. Ranking is advisory and human-executed.
4. Calibrated and deterministic scores are never mixed within one family when
   probability coverage is partial.
5. More than one applicable inference for the same assessment and target is an
   ambiguity, not an invitation to choose by database row order.

## Verification

| Check | Result |
|---|---:|
| DOI-9 focused tests | 13/13 PASS |
| DOI-1 through DOI-9 selected regression | 104/104 PASS |
| Compilation and public-import smoke | PASS |
| CALL/PUT symmetry | PASS |
| Low-OI/zero-volume retention | PASS |
| Partial/ambiguous calibrated evidence fallback | PASS |
| Chronological out-of-sample acceptance/rejection | PASS |
| Append-only/idempotent persistence | PASS |
| Forged identity rejection | PASS |
| Live control-plane readiness scan | PASS, read-only |
| Live database hash changed | NO |
| Provider calls | 0 |

The active Python 3.14 environment does not provide `pytest`; the DOI suites
are standard-library `unittest` suites and were run directly.

## Live evidence finding

The live control plane currently contains none of the DOI assessment, outcome,
probability or ranking tables. The readiness scan did not install them and the
database hash remained unchanged. Therefore no accepted probability model or
ranking policy exists, and DOI-9 cannot honestly publish calibrated ranking.
If the DOI-9 service is invoked after explicit schema initialisation, its safe
behaviour is DOI-5 deterministic fallback with every candidate retained.

## Boundary and next dependency

DOI-9 is implemented and offline accepted as a domain/application capability.
It is not yet projected into the Intelligence Lab, Pipeline Interpreter or the
production orchestrator. DOI-10 owns that integration and must present the
same latest assessment, chosen ranking mode, alternatives, evidence cutoff and
model status without changing thesis or execution authority.
