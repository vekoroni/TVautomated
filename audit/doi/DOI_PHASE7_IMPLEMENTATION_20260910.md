# DOI-7 Outcome-label Capture — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Result:** OFFLINE ACCEPTED  
**Next phase:** DOI-8 probability models

## Delivered

- A pure outcome-labelling domain for exact long CALL and PUT assessments.
- Completed, partial-option, option-return-unavailable, deferred and
  data-exception states; absent values are never converted to economic zero.
- Exact-contract market-path labels based on immutable assessment cutoffs.
- Option midpoint and executable bid-versus-origin-ask horizon returns.
- Option mark and executable MFE/MAE.
- Underlying directional return and MFE/MAE with target/invalidation
  first-passage state, including same-session ambiguity.
- Observable liquidity maturation: first two-sided quote; first session below
  15%, 25% and 35% spread; maximum volume and open interest.
- Append-only `doi_outcome_labels` persistence in the existing lifecycle
  control plane, with immutable payload hashes, idempotent restarts and source
  observation lineage.
- Provider-free family capture with one-assessment failure isolation and exact
  population reconciliation.
- Chronological training/validation/holdout cohort construction that excludes
  outcome windows crossing a split boundary.

## Governance

DOI-7 labels are `HYPOTHETICAL_MARKET_PATH` observations. They cannot contain
realised fills, realised P&L, thesis changes, capital permission or automated
position closure. Realised trade outcomes remain a separate Decision and
Outcome Ledger concern. Low OI, zero volume, missing quotes, timing and entry
conditions do not discard a ticker or prevent its outcome from being recorded.

## Verification

| Check | Result |
|---|---:|
| DOI-7 focused tests | 16/16 PASS |
| DOI-1 through DOI-7 selected regression | 81/81 PASS |
| Existing option lifecycle + Morning authority | 16/16 PASS |
| Compilation/import smoke | PASS |
| Frozen canonical-chain rehearsal | PASS |
| Provider calls in DOI-7 | 0 |
| Production database writes by verification | 0 |

The active Python 3.14 runtime still does not provide `pytest`; therefore no
pytest-only suite is represented as passing. All DOI phase suites are
`unittest` compatible and were executed directly.

## Frozen canonical-chain rehearsal

The rehearsal used the canonical MarketData A chain from 3 September 2026 and
the exact same contracts in the stored 4 and 8 September chains. It evaluated
89 real family assessments in a disposable control plane:

- 89/89 contracts had later exact-contract observations;
- 89 completed one-session labels;
- 89 correctly deferred five-session labels because only two future completed
  sessions were available;
- 178/178 assessment-horizon labels reconciled;
- zero partial paths, data exceptions, provider calls or authority violations.

The result proves path binding and label mechanics, not a trading edge or a
calibrated probability.

## Files

- `domain/dynamic_options_outcomes.py`
- `canonical_data/dynamic_options_outcomes.py`
- `canonical_data/option_liquidity_lifecycle.py`
- `canonical_data/__init__.py`
- `tests/test_dynamic_options_outcomes.py`
- `audit/doi/doi7_real_outcome_rehearsal.py`
- `audit/doi/DOI_PHASE7_REAL_REHEARSAL_20260910.json`
- `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`

## Promotion boundary

DOI-7 is deployed as importable production-domain and canonical application
code and is offline accepted. It does not yet fit, calibrate or publish a
probability model and it does not replace the current live selector. DOI-8 may
consume only complete, chronologically valid cohorts and must retain the
deterministic DOI-5 fallback wherever sample support is inadequate.
