# AVS-MON-004 — exact-contract provenance and closure assessment

**As of:** 22 September 2026. **Production outcome capture:** OFF. **Scope:** read-only inspection of the live Phantom, control-plane and price stores; no provider calls, live database writes, trading-authority changes, or model activation.

## Decision

Keep unversioned Phantom `chain_snapshots` lower-trust and research-only. Do not manufacture canonical revisions from them. The historical direct-backfill writer stores the normalised option row in `chain_snapshots` and an `OK`/`NO_DATA` audit at **query** level. It stores neither the original provider response in `raw_json` (`normalize_marketdata_chain` sets it to an empty string) nor an immutable per-contract row hash bound to a canonical dataset and projection receipt. Its upsert can also replace a previous row at the same ticker/session/symbol. A query-level `OK` proves that a request returned rows, not which later value of an exact option contract was present at the decision cutoff. This provenance cannot be established retrospectively from those tables alone.

The canonical projection path is different: `canonical_option_chain_revisions` records immutable row JSON/hash, dataset ID, event ID and as-of time; `canonical_projection_receipts` and the control-plane registry bind that row to a complete MarketData dataset. The outcome reader verifies all of these and provider/availability timestamps before admitting it. No fallback from failed canonical verification to a raw snapshot is permitted.

## Read-only live audit

`python -m tools.avs_mon004_provenance_audit` classified exact contract/session evidence for the same 40 mature assessments in the MON-004 oldest/newest CALL/PUT sample. The 40 assessments each have five completed underlying sessions, yielding 200 exact-contract session cells:

| Evidence class | Cells |
| --- | ---: |
| Verified canonical revision | 134 |
| Unversioned Phantom snapshot, research-only | 12 |
| No exact-contract quote | 54 |

CALL cells: 75 verified, 5 unversioned, 20 absent. PUT cells: 59 verified, 7 unversioned, 34 absent. For the one-session horizon, 37/40 assessments had a complete verified path, one had a raw-only path and two lacked verified coverage. For the five-session horizon, **0/40** had a complete verified path; 11 had at least one raw-only cell and 29 had other incomplete verified coverage. This is a purposive coverage sample, **not** a win-rate or monetisation estimate. The prior replay found 26/40 one-session paths with valid two-sided verified quotes; quote presence alone does not imply an executable exit.

The audit distinguishes `VERIFIED_CANONICAL_REVISION`, `UNVERSIONED_SNAPSHOT_RESEARCH_ONLY`, `NO_EXACT_CONTRACT_QUOTE`, `REVISION_NOT_AVAILABLE_AT_CUTOFF` and `PROVENANCE_CONFLICT_FAIL_CLOSED`. Its classifications cannot be consumed as outcome-source IDs or authority. Four adversarial classification tests cover raw-only, exact-symbol, unavailable revision and absent quote; the adjacent eight-suite regression passed **103/103**.

## Changes still required before routine capture

1. **Future provenance:** route all future option-chain acquisitions that may supply governed outcomes through the canonical registry/projector, or add an equivalent append-only, per-row provider-response digest/receipt with original provider and availability timestamps. Prevent a direct `chain_snapshots` upsert from masquerading as historical truth. This is a writer change and needs a separate migration/compatibility test; the current audit deliberately does not alter acquisition.
2. **Historical gap treatment:** leave the 12 raw-only cells research-only unless an independently archived, immutable provider payload and acquisition receipt can be matched to each exact row. If those sources do not exist, obtain a newly timestamped provider observation where permissible; it cannot be backdated to the original decision time. The 54 absent cells need new observations or must remain missing. A synthetic/interpolated quote is not an executable-price label.
3. **Coverage and horizon acceptance:** repeat time-stratified CALL and PUT replay across independent sessions once 10- and 20-session underlying horizons mature. Report exact-contract and two-sided coverage separately, with missingness by contract family and source; do not infer strategy returns from the current 40-assessment cohort.
4. **Operational acceptance:** run a larger, bounded isolated writer canary with measured database/WAL/index growth, throughput, idempotency, resume after interruption and a date-scoped rollback package. The previous one-assessment canary proves mechanics, not production-scale safety. Reconcile expected, final and pending labels before any activation.
5. **Model/trading boundary:** keep the opt-in capture flag off and learning/model activation gated. Hypothetical marks are not fills. Neither unversioned raw data nor partial outcome labels may change Evening GO, Morning validation, capital permission or human execution decisions.

These are prerequisites for **routine governed outcome capture**, not evidence that the existing Evening/Morning trading path is broken. This audit did not revalidate the full trading pipeline or certify monetisable trades. It establishes exactly which evidence the outcome-learning path can trust today and which additional changes would be needed before that path can run routinely.

## Reproduction

- Read-only live classification: `C:\Python314\python.exe -m tools.avs_mon004_provenance_audit` from the repository root.
- Regression: `C:\Python314\python.exe tools\run_governed_pytest.py -q --tb=short --basetemp .pytest_mon004_provenance_full tests\test_avs_mon004_provenance_audit.py tests\test_avs_mon004_canary.py tests\test_phantom_outcome_source.py tests\test_dynamic_options_outcomes.py tests\test_option_liquidity_lifecycle.py tests\test_avs_fix_002_stage6_outcome_learning.py tests\test_doi10_projection_integration.py tests\test_doi11_production_integration.py`.
