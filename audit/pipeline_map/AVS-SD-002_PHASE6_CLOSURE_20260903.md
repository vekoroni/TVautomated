# AVS-SD-002 Phase 6 closure — dynamic dispatcher

Date: 2026-09-03  
Status: **CODE COMPLETE; AUTO EXECUTION FLAG REMAINS OFF**

## Design reviewed

- Resolve a deterministic plan before any provider call or output mutation.
- Use the governed `latest.json` pointer and accepted run metadata, never newest-folder ordering.
- Reuse a current completed thesis instead of rerunning the full universe.
- Preserve `--evening` as explicit thesis construction and `--morning` as explicit validation.
- Keep `LATEST` research-only and require provider-finalisation evidence before finalisation.
- Persist the immutable plan before executing its callback.

## Implementation

- Added `orchestrator.dynamic_dispatcher` with accepted-thesis resolution, plan preview, operator summary, immutable plan persistence and exact action dispatch.
- Added `--auto`, `--finalise`, `--replay`, `--plan-only`, `--as-of-utc` and `--provider-session-finalised` CLI controls.
- Preserved the legacy Evening/Morning path while `AVSHUNTER_DYNAMIC_PLAN_ENABLED` is disabled.
- Enforced independent plan, thesis, validation, profile and AUTO rollout flags.
- Corrected after-hours plan ordering: partial provider evidence validates the frozen thesis; provider-confirmed completion finalises it.
- Ensured finalisation mints a new run identity and cannot overwrite the selected accepted thesis run.

## Executed evidence

- Phase 6 plus Phase 1/4/5 contract pack: **47 passed / 0 failed**.
- Real accepted-run `--auto --plan-only` preview: **PASS**; selected run `20260902_232526`, completed session `2026-09-02`, action `VALIDATE`, and created no run-plan output or database.
- Existing `--evening --cds-startup-self-test`: **PASS**.
- Python compilation of Phase 6 modules: **PASS**.
- Wider historical/audit pack: **284 passed, 30 failed, 1 skipped**. The failures are pre-existing characterization tests that assert now-implemented MSI work is absent, Sunday fixtures, and previously documented authority/test-contract drift. No failure references the Phase 6 dispatcher or its CLI contract.

## Rollout control

`AVSHUNTER_DYNAMIC_AUTO_ENABLED` and all dynamic-session flags remain disabled by default. No live provider workflow was executed and no accepted production pointer was changed.

## Backup

`backups/avs_sd_002_rev1_1_phase6_prechange_20260903_154238`

## Remaining gates

- Phase 7 Lab, Interpreter and append-only ledger lineage.
- Phase 8 deterministic replay, request-budget checks, fresh Evening/Morning/RTH/after-hours evidence, restore drill and controlled promotion.
