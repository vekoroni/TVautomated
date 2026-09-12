# AVS-FIX-002 Stage 1 — Provider Finality

**Status:** STAGE 1 COMPLETE — CONTROLLED PIPELINE CYCLE AUTHORISED
**Design controls:** FINAL v1.2 Sections 0.1 and 9; REQ-WP0-01 through REQ-WP0-08; ALG-15

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
| Run condition has one domain vocabulary | `domain/run_planning.py` | Six-state enumeration and precedence tests |
| Morning has distinct pre-open and post-open semantics | domain plan plus `morning_gate.py` | Pre-open adversarial test proves zero option/skew calls |
| Provider and acquisition timestamps remain separate | Morning fetch/capture adapters | Missing timestamp cannot publish exact quote or executable state |
| Morning reports quote timestamp coverage | `morning_gate.py` summary | Session/hour distributions and missing/present counts |
| Macro replay binds by immutable packet id/hash | `canonical_data/macro_packet_archive.py` | Idempotent archive and replay-by-id test |

## Outputs added

- `provider_finality_<run_id>.json`: per-ticker immutable finality decisions and run aggregate.
- `provider_finality_exceptions_<run_id>.csv`: named residual exceptions for investigation.
- `options_intelligence_summary_<run_id>.json.provider_completeness_evidence`.
- `run_meta_v2.json.provider_completeness_evidence` plus governed run condition and baseline eligibility.
- Per-row finality state and reasons in Options Intelligence output.

## Verification completed

- Production-module compilation: PASS.
- `git diff --check`: PASS.
- Original Provider Finality focused/integration pack: **66 passed, 0 failed**.
- Consolidated Stage 1 regression pack: **138 passed, 0 failed**.
- Two-session canonical replay: **2,549/2,549 chains COMPLETE**; both sessions meet the governed per-chain and run thresholds.
- Full governed repository suite: **1,783 passed, 39 failed, 4 skipped, 281 subtests passed**. The Stage 1-related failures were obsolete fixtures/assertions; they were corrected and the 138-test Stage 1 pack was rerun clean. The remaining failures are recorded pre-existing audit/baseline tests and are not promoted as Stage 1 passes.
- The wider MSI audit failures were reviewed. Most are historical defect-detector assertions that deliberately expect repaired functionality to be absent; they are not Stage 1 regressions. One genuine resolver compatibility regression was identified and corrected.
- No provider calls and no production pipeline run were made by the offline tests.

## Controlled-cycle acceptance still open

Stage 1 is complete offline and ready to commit as one bounded release. A controlled completed-session
pipeline cycle remains the production acceptance test. It must produce the
finality artefacts, immutable macro binding, named Morning execution state and
timestamp diagnostics. A subsequent pre-open or post-open Morning invocation
must follow the mode selected by the persisted plan. Until that evidence exists,
the implementation is shipped code but not a proven live-cycle baseline.
