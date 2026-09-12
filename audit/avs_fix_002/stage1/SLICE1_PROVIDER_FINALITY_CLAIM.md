# AVS-FIX-002 Stage 1 — Provider Finality

**Status:** IMPLEMENTED AND OFFLINE VERIFIED; LIVE RUN AND GIT GOVERNANCE PENDING
**Design controls:** FINAL v1.2 Sections 0.1 and 9; REQ-WP0-01, REQ-WP0-02; ALG-15

## Requirement-to-code claim

| Requirement | Implementation | Evidence |
|---|---|---|
| Canonical five-state finality vocabulary | `domain/provider_finality.py` | Focused state-precedence tests |
| Historical request mode, provider settlement and official close are mandatory | `assess_chain_finality()` and `canonical_data/provider_finality.py` | Complete/partial/missing-close tests |
| Chain timestamps must prove session and late-watermark coverage | `assess_chain_finality()` | One-late-quote and low-coverage adversarial tests |
| Timestamps use XNYS session bounds, including DST | `canonical_data/provider_finality.py` | 2026-11-02 close asserted as 21:00 UTC |
| Each ticker failure is named and does not abort peers | `assess_completed_option_worklist()` | Missing-chain exception test and exception CSV contract |
| Run thresholds are 95% complete chains and 99% official closes | `assess_run_provider_completeness()` | Boundary and below-threshold tests |
| Provider evidence is persisted in run metadata | `_integrate_provider_completeness_into_run_meta()` | Run-meta integration tests |
| Forced, dirty, partial or unassessed runs cannot become normal baselines | orchestrator run-condition integration | Clean/dirty/forced tests |
| Partial chains remain visible but cannot be valued or ranked by normal DOI | `canonical_data/dynamic_options_production.py` | Production bridge partial-retention test |
| Incomplete cached current-session evidence is refreshed once | both option-chain resolvers | v2 and legacy cache behavior tests |
| ALG-15 thresholds are governed and included in configuration identity | `config/governed_constants_v1.json` and policy loader | Config validation/hash test and run-meta assertion |

## Outputs added

- `provider_finality_<run_id>.json`: per-ticker immutable finality decisions and run aggregate.
- `provider_finality_exceptions_<run_id>.csv`: named residual exceptions for investigation.
- `options_intelligence_summary_<run_id>.json.provider_completeness_evidence`.
- `run_meta_v2.json.provider_completeness_evidence` plus governed run condition and baseline eligibility.
- Per-row finality state and reasons in Options Intelligence output.

## Verification completed

- Production-module compilation: PASS.
- `git diff --check`: PASS.
- Stage 1 focused/integration pack: **66 passed, 0 failed**.
- The earlier wider MSI audit failures were reviewed. Most are historical defect-detector assertions that deliberately expect repaired functionality to be absent; they are not Stage 1 regressions. One genuine resolver compatibility regression was identified and corrected.
- No provider calls and no production pipeline run were made by the offline tests.

## Promotion conditions still open

1. Track the two new production modules and Stage 1 tests/evidence in Git. The Stage 0 import-governance test correctly rejects untracked production imports.
2. Run a controlled pipeline cycle to produce and validate the two finality artefacts and `run_meta_v2` evidence against real canonical chains.
3. Confirm normal eligibility is granted only when the observed 95%/99% thresholds pass; otherwise confirm the run remains non-baseline with named ticker exceptions.

The code is integrated but must not be described as production-promoted until these conditions are satisfied.
