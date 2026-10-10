# S2-1 build receipt: value the setup that qualifies the trade (6 Oct 2026)

**Approval:** ACK, 6 Oct 2026. The governing-setup rule was approved with invalidation option I-c ("Approve and build"). Design: `S2-1_ROOT_CAUSE_AND_DESIGN.md`.
**Status:** built and TESTED_UNCOMMITTED. Commit only when ACK asks. The live run is ACK's.

## Test-first record
1. **Characterisation (S0):** `tests/test_avs_sot_s0_characterisation.py` pinned the existing behaviour. The legacy 1d-first pick is still pinned in the new file (`test_legacy_thesis_pick_still_prefers_1d_and_spelling`); it survives as the supporting `daily_event`.
2. **Failing business-rule tests:** `tests/test_avs_governing_setup.py`. It failed at import before the change, and now **17 pass**. It covers:
   - the setup that sets the lane is the setup that is valued;
   - a passed level never governs;
   - ties are decided by state, then holdout hit, then evidence, then distance, then age, never by spelling;
   - the daily event is kept as supporting and never valued;
   - no governing setup means the thesis and invalidation are missing, and the fields say so;
   - all trade-side levels passed is stated;
   - I-c invalidation;
   - the new fields travel with the lane;
   - Discovery selects once;
   - the book carries the new fields and the card shows them.

## Minimal change
| File | Change |
|---|---|
| `domain/structure_behaviour/trade_lane.py` | `select_governing()` is now the single selection: passed-level exclusion (`_level_passed`), stated tie-break, and it returns the governing candidate. `ticker_lane()` is a thin wrapper over it. `governed_invalidation()` implements I-c. `TRADE_LANE_FIELDS` gains `trade_lane_candidate_id`, `trade_lane_levels_passed`, `daily_event*`, `thesis_invalidation_setup_id` and `early_warning_*`. These travel through the existing `DISC_MERGE_COLS` and the Lab book allow-list with no other edits |
| `domain/structure_behaviour/thesis_category.py` | New `governed_thesis()` takes the thesis event, move level and duration evidence from the governing setup. The legacy pick is kept only as the supporting `daily_event*` fields. A missing governing setup is shown as `NO_GOVERNING_SETUP` |
| `avshunter_discovery_ULTIMATE.py` | Selects once, right after the BEH-001 reading. The **invalidation** comes from the governing setup (it was the daily primary). The thesis fields come from `governed_thesis`. The lane uses the same selection (the second `ticker_lane` call is removed). `governing_candidate_id` is added to the thesis basis |
| `intelligence-lab/static/trade-card.js` | §3 shows "Thesis exit … (decides)" and "Early warning (daily) … does not decide" |

Unchanged:
- direction governance and the trade side;
- the lane table and its hit rates;
- the anticipated move, the Morning recompute and the lane B confirmation (they read the same `thesis_*` fields, which now come from the governing setup);
- the BEH-001 state machine;
- the 40-bar range target (S2 #3).

## Acceptance
- **Replay through the production selector on the frozen run** `20261006_060401`:
  - **1,052 of 1,052** rows give the same lane and governing setup as the approved design replay.
  - Lanes: A 331 · B 23 (before EOD payoff confirmation) · C 690 · intraday-only 8.
  - The 51 GOs: A 48, C 3 (SARO, DKS, UTI).
  - All 7 previously unvalued GOs now have a move level.
- **Affected test files, one process each** (failures counted per file):
  - trade lanes 17
  - D10 phase/event 9
  - anticipated move 16
  - duration-level timing 4
  - Lab trade card 18
  - contract identity 7
  - S0 characterisation 9
  - Morning lanes 3
  - trade summary 4
  - governing setup 17

  **All pass.**
- **Discovery and BEH-001 files** (25 files, one process each): **all pass, 0 failures, 0 errors.** About 180 tests, including `test_avs_discovery_trade_lane`, `test_beh001_*`, `test_avs_dir002_*`, `test_dynamic_session_phase2` and `test_pre_evening_production_repairs`.
- **Not yet run:** the full regression suite. It is recommended before commit.
- **Live:** ACK runs Evening, then Morning. The S0 baseline (`measure_baseline.py`) is compared on the new run. C12 tracks hit rate and time-to-level of governing-setup tickets from then on, as a forward measure.

## Tidy (ACK standing instruction)
- **Removed:** the second, independent lane pick in Discovery (`ticker_lane(_beh['candidates'] …)`). Now one selection feeds the lane, the thesis and the invalidation.
- **Removed from decisions:** the daily primary's invalidation and the 1d-first thesis pick. Both are kept only as labelled supporting fields (`early_warning_*`, `daily_event*`), as approved under I-c / D2.
- **Kept on purpose:** the legacy `thesis_category()`, which produces `daily_event*`, and `engine._primary`, which sets the trade side (direction governance, out of scope).
