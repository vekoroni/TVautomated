# AVS-SD-002 Phase 5 closure — dynamic validation lifecycle

Date: 2026-09-03  
Status: **CODE COMPLETE; DYNAMIC VALIDATION FLAG REMAINS OFF**

## Design reviewed

Validation must resolve the frozen thesis, acquire the underlying first, stop acquisition for an invalidated thesis, refresh only the selected contract for survivors, create a developing profile only from observable RTH bars, preserve the EOD profile, and delegate final action/capital to Execution Gate.

## Implementation

- Added pure `validate_thesis(plan, thesis)` and batch validation services.
- Added symmetric CALL/PUT invalidation, target, trigger and maximum-entry geometry.
- Added underlying-first and survivor-only acquisition ordering.
- Added premarket `PENDING_MARKET_OPEN`, RTH `DEVELOPING_SESSION` and after-hours `PARTIAL_SESSION` states.
- Added immutable validation event identity and atomic persistence.
- Added per-ticker provider isolation and configurable systemic-failure reporting.
- Replaced Morning Market Structure’s Polygon one-minute callback with governed MarketData five-minute candles.
- Corrected the Morning handoff defect where calculated `ms_*` evidence was written only to `live_map` and never copied into the result rows consumed by the Lab.
- Preserved advisory-only profile authority; it cannot change direction or grant capital.

## Executed evidence

- Phase 5 acceptance pack: **13 passed / 0 failed**.
- Affected Morning/Market Structure/Lab compatibility pack: **58 passed / 0 failed**, 1 skipped, 3 subtests passed.
- Python compilation of changed modules: **PASS**.
- Two unrelated `test_morning_gate_contract_repair.py` expectations remain red against the pre-existing EV/composite policy. Phase 5 did not modify those code paths; they are recorded as prior test-contract drift, not Phase 5 regressions.

## Rollout control

The new dynamic validation service is not selected by production commands yet. Production selection belongs to Phase 6 and remains disabled until Phase 8 acceptance.

## Backup

`backups/avs_sd_002_rev1_1_phase5_prechange_20260903_163000`
