# AVS-IMP-SD-003-004 — Evening integration repair

**Implemented:** 2026-09-04  
**Source run:** `20260904_122358`  
**Scope:** repair the three integration defects exposed by the completed Evening cycle

## Result

The confirmed integration defects are repaired and regression-tested.

1. EOD now carries the authoritative `invalidation_state` with the governed invalidation level and source.
2. `NO_CAPITAL` is recognised by the semantic audit as a valid fail-closed Options permission.
3. The Intelligence Lab book is written before the handoff audit and UAT report. The final run manifest is regenerated after those artefacts exist.
4. A directional thesis with no governed invalidation is excluded from the Morning candidate book and retained in the drop-off audit with `EOD_STRUCTURAL_BLOCK:MISSING_GOVERNED_INVALIDATION`.

## Real-run replay

The repaired contracts were replayed in memory against run `20260904_122358`:

- original EOD candidates: 271;
- candidates with valid governed invalidation: 270;
- true missing-stop exception: `MRP`;
- semantic failures after corrected transport/exclusion: **0**.

No production artefact from the historical run was overwritten.

## Tests

- Focused integration and fixture suite: **35 passed, 0 failed**.
- Complete production regression suite: **941 passed, 1 skipped, 43 subtests passed, 0 failed**.
- Python compilation: **PASS**.
- `git diff --check`: **PASS**, with Windows line-ending notices only.

The first full-suite attempt identified one stale test fixture that constructed an executable CALL without an invalidation. The fixture was corrected to provide governed test geometry; its trigger-handoff assertions were not weakened. The final complete suite is green.

## Acceptance status

**INTEGRATION REPAIR ACCEPTED OFFLINE.**

A fresh Evening cycle is required to create authoritative post-fix artefacts. The run should explicitly enable the completed-profile stage so the remaining MarketData acquisition/cache acceptance gate is exercised.

## Rollback

`backups/avs_sd_003_integration_prechange_20260904_161255/`
