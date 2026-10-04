# DIR-002 build — pause checkpoint (1 Oct 2026)

**State: built but not finished. Do not run Evening or Morning until the build is resumed and accepted.**

## Safety while paused
- `config/dir002_side_assignment_v1.json` → `production_direction_source = legacy_rollback`. The new assignment is uncalibrated, so Discovery's legacy resolver governs. The new thesis fields are written only under `shadow_*` names. Set it back to `side_assign_v1` only after calibration is frozen.
- Nothing has been committed. The Step 1 baseline is in `Enhancements/assessment/AVS_DIR002_STEP1_BASELINE_20261001/`: git head, tracked-file patch, sha256 inventory of 201 files, golden replays and comparison.

## Background jobs left running (offline, no provider calls)
- Historical panel → `Enhancements/outcomes/dir002/panel_v1.jsonl` (500 tickers; at 425 when paused).
- Baseline full suite, run in the frozen snapshot `C:\avs_dir002_baseline` → `full_suite_baseline_s{0,1,2}.jsonl`.

## Done in this session (tests green unless stated)
- **Step 1.** Source/data inventory. The golden replay reproduces stored runs 27 Sep and 30 Sep exactly on direction, status, levels, phase and event. Tier differences come from the wall-clock decay. **Finding H-1:** 50 stale-cache (delisted) tickers still survive Discovery.
- **Kernel.** `side_structural_evidence` (WyckoffEngine) and `symmetric_precor_intent` (Precor), both in log space. An exact mirror holds on 300 random charts. Config: `config/dir002_side_evidence_v1.json`; the old shadow config is retired.
- **DEC-1 refinement (needs ACK confirmation).** Precor setups from trend phases (D without SOS/SOW, or E) count as trend context, not structural support. Only event-anchored intent counts.
- **Discovery.** Writes `thesis__*`, both sides' geometry with σ distances, and evidence JSON. The legacy fields come from the adapter. The `legacy_*` attribution columns, the DSC-13 Tier-0 overwrite fix, signed R:R, and the DSC-21 run-scoped macro path are wired.
- **Downstream and Vanguard.**
  - DWN-04 (C5 packet reads the thesis), DWN-11 (macro rewrite namespaced), and DWN-02 (no Options fabrication for a retired Vanguard row).
  - VNG-02 (no Vanguard direction vote; the legacy rule is characterised).
  - V-A side blocks: point-in-time, mirrored, `NOT_EVALUATED` when missing, and shadow only.
- **Pre-registration** of calibration and R-5: `AVS_DIR002_SIDE_ASSIGNMENT_CALIBRATION_PREREGISTRATION_20261001.md`.

## Resume here
1. **VNG-11.** `tests/test_avs_dir002_open_contract_reconciliation.py` was written and is red (intentional, TDD). Implement the governance reject row in `scripts/run_vanguard_from_packages.py`, and change `trade_governance._check_price_invalidation` so a missing direction gives `DIRECTION_MISSING`.
2. When the panel finishes, run `dir002_calibrate.py calibrate`, freeze the policy, then run `heldout` (R-5). Then run the R-4 population report and the R-2 population mirror on the 30 Sep session.
3. Remaining work:
   - Discovery hygiene: DSC-14, 16–18, 20, 22 and H-1.
   - Vanguard: VNG-06/07/10/12/14/15/16, plus the v8 labels (VNG-04/09).
   - Downstream: DWN-03/06/07/14/15, the Options EDGE_STRONG scope (VNG-08), and the Lab/Interpreter fields.
4. Rerun the snapshot failures that were caused by the missing `worker3` junction. Then run the full suite on the build, the rollback drill and the build register update.
