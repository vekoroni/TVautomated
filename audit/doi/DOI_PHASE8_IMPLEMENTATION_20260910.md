# DOI-8 Probability Models — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Implementation result:** OFFLINE ACCEPTED  
**Production model status:** NOT TRAINED — INSUFFICIENT REAL DOI-7 COHORT  
**Active fallback:** DOI-5 deterministic assessment

## Delivered

- Point-in-time model feature contracts that reject future/outcome leakage.
- Separate CALL and PUT model cohorts.
- Separate targets for one-, two- and three-session liquidity maturation,
  positive executable return, return hurdle and target-before-invalidation.
- Exact-horizon binding for profitability targets; liquidity horizons may use
  a longer label only because DOI-7 records the first liquidity session.
- Chronological 60/20/20 train/calibration/holdout construction with purging
  when an outcome window crosses the next cohort boundary.
- Interpretable standardized logistic regression as the first baseline.
- Platt calibration fitted only on the later calibration cohort.
- Constant-prevalence baseline comparison on the untouched holdout cohort.
- Brier score, log loss, ECE, reliability bins, 95% bin uncertainty, OOD rate,
  temporal-window stability and DTE/delta/spread/missingness diagnostics.
- Append-only, hash-bound model-card and inference tables in the existing
  canonical control plane. Initialisation is explicit and was tested only on
  disposable databases.
- Model-unavailable and OOD inference states that publish no calibrated
  probability and do not alter the deterministic DOI-5 assessment.
- Lazy public exports so importing canonical contracts does not load the
  modelling runtime until a DOI-8 service is requested.

## Acceptance rules

A cohort model is accepted only when all of these are true:

1. Training, calibration and holdout counts and both binary classes meet the
   versioned support policy.
2. Holdout Brier score is below the constant-prevalence baseline.
3. Holdout log loss is below the same baseline.
4. Holdout ECE does not exceed policy.
5. Every eligible chronological holdout window beats its baseline.
6. The inference feature contract and direction match the model.
7. The current feature vector is inside the recorded training range.

No target threshold, option timing state, OI, volume, spread or probability
discards a ticker, changes its direction, invalidates its thesis, grants
capital or closes a position.

## Verification

| Check | Result |
|---|---:|
| DOI-8 focused tests | 13/13 PASS |
| DOI-1 through DOI-8 + persistence + authority + Morning/Lab selected regression | 94/94 PASS |
| Compilation and lazy-import smoke | PASS |
| Stable synthetic-signal calibration mechanics | PASS (test evidence only) |
| Temporally reversed signal rejection | PASS |
| OOD probability withholding | PASS |
| Live control-plane readiness scan | PASS, read-only |
| Live database hash changed | NO |
| Provider calls | 0 |
| Production probability trained or activated | NO |

The active Python 3.14 environment still lacks `pytest`. Two pytest-only suites
requested during regression could not be imported and are not counted as
passing. The clean 93-test run excludes those suites rather than concealing the
environment limitation.

## Live evidence finding

The production control plane has neither a populated DOI assessment table nor
a DOI-7 outcome-label table. Consequently all twelve target/direction cohorts
have zero mature labels. The frozen DOI-7 rehearsal proves label mechanics but
is not eligible production training evidence. DOI-8 therefore correctly
refused to create a production probability model.

## Boundary and next dependency

DOI-8 code is deployed and offline accepted. It is not honest to describe a
probability model as live until completed-session processing persists DOI-5
assessments, DOI-7 matures their outcomes over real sessions, and at least one
CALL or PUT target cohort passes the chronological acceptance gates. Nonlinear
and survival challengers remain deferred under the design rule that they are
trained only where real sample support is adequate.

DOI-9 may be built as a deterministic-fallback ranker, but calibrated model
weighting cannot be tuned or promoted before an accepted DOI-8 cohort exists.
