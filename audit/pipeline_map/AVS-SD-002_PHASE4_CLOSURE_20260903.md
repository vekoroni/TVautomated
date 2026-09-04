# AVS-SD-002 Phase 4 closure — completed-session thesis builder

Date: 2026-09-03  
Status: **CODE COMPLETE; PRODUCTION FLAG REMAINS OFF**

## Design clauses reviewed before implementation

- Build the completed Market Profile after Discovery and before Vanguard.
- Preserve five-minute provider frames and point-in-time lineage through CDS.
- Never rebuild an intraday profile from daily OHLCV on the governed path.
- Missing or unusable profile evidence remains null and `NOT_EVALUATED`.
- Profile evidence is advisory and cannot grant capital or reverse direction.
- Isolate individual ticker failures, but fail the stage on a systemic failure ratio.
- Make completed-thesis stage ordering and restart behaviour deterministic.

## Implementation

- Added an immutable `MarketProfileEvidence` contract and canonical derived-evidence store.
- Corrected cadence classification in the modern profile calculator.
- Added the independently runnable completed-profile stage and inserted its disabled integration point before Vanguard.
- Added explicit completed-profile fields to `VanguardInput`.
- Changed the governed Vanguard auction path to consume the profile packet, return null levels when unavailable, and deny profile-derived readiness.
- Added systemic provider-failure detection and deterministic calculation timestamps.
- Added reusable `orchestrator.dynamic_thesis.build_thesis(plan)` coordination with fixed stage order, EOD-only authority ceiling and immutable restart receipt.

## Executed evidence

- Phase 4 acceptance pack: **10 passed / 0 failed**.
- Combined dynamic-session, Vanguard, MSI calculation/logic and restart pack: **190 collected; command exited 0**.
- Python compilation of all affected Phase 4 production modules: **PASS**.
- Exact-cache test: second completed-profile execution issued **0 physical provider requests**.
- Per-ticker failure test: unrelated ticker completed; failure ratio crossed the configured systemic threshold and was explicitly reported.

## Rollout control

`AVSHUNTER_COMPLETED_PROFILE_ENABLED` remains disabled by default. The existing production Evening path is therefore unchanged until Phase 8 replay and live-cycle acceptance. The legacy Vanguard calculator remains reachable only while this flag is off and is not removed in this phase.

## Backup

Pre-change production files: `backups/avs_sd_002_rev1_1_phase4_prechange_20260903_151506`.

## Remaining gates

- Phase 5 dynamic validation and developing-profile lifecycle.
- Phase 6 dispatcher/compatibility commands.
- Phase 7 Lab, Interpreter and outcome-ledger lineage.
- Phase 8 replay, fresh Evening, premarket, RTH, reconciliation and restore drill.
