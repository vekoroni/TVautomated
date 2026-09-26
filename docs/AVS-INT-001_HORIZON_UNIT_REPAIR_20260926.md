# AVS-INT-001 — hold-window and unit repair (26 September 2026)

Status: **implemented and offline-tested; live Evening/Morning acceptance pending**.
No pipeline run, broker read/write, provider call, universe edit, database edit,
or model activation was performed for this repair.

## Root cause and business effect

Layer 3 publishes three *incremental* expected stock moves in display percent:
sessions 1–5, 6–10, and 11–20. Several production consumers treated the
6–10 increment as the full ten-session move, selected the 1–5 increment for
any Evening exit plan, or treated a percentage as dollars. An execution
adapter could also compare a large stock-move fraction with an option-premium
spread merely because the number exceeded 15%. These mismatched denominators
could distort target feasibility, review order, exit guidance and spread
assessment. They do not establish a profitable option outcome.

## Governed correction

- `domain.volatility_budget.cumulative_expected_move_pct` now resolves the
  5/10/20-session one-sigma budget from the canonical fraction or the complete
  legacy increments. It rejects an invalid canonical value, a contradictory
  horizon convention or an incomplete incremental path. The existing Evening
  thesis projection and EOD, trigger and execution-package consumers use it.
- The GARCH-to-Superbrain/EIL/Options/Execution merge now carries the canonical
  cumulative fields and their calculation metadata, not only `l3_` incremental
  fields. The Morning export rescue join carries them too. No source forecast
  is fabricated for a missing ticker.
- EOD exit fallback and the candidate's expected-move fields use the thesis
  holding horizon, not the option's DTE or whichever incremental field appears
  first. The candidate carries canonical fractions and calculation metadata
  into the Evening/Lab handoff. The full legacy increments remain for audit.
- Morning exit guidance converts a percentage of the underlying into a dollar
  distance at the current reference spot. Its 10-session continuation uses the
  cumulative budget. A missing complete budget remains unknown rather than
  becoming a shorter-horizon substitute.
- The liquidity execution-edge comparison now requires explicit
  `OPTION_RETURN_FRACTION` provenance. Layer 3 GARCH is explicitly marked
  `UNDERLYING_FRACTION`; magnitude alone never changes its denominator.
  Static option-spread assessment remains available when option-return
  evidence is absent. No order or sizing authority was added.

## TDD and acceptance evidence

Five new regressions failed before repair, exposing EOD fallback targets,
trigger EV, execution-package arithmetic and stock-versus-option unit truth.
Additional tests cover Morning dollar conversion, an incomplete ten-session
path and the explicitly option-sourced execution-edge branch. A pre-existing
orchestrator merge test was extended and failed red because the canonical
columns were absent; it passed after the merge repair. The final affected
offline pack: **135 passed**. It emitted 56 NumPy warnings from tests exercising
empty/missing price histories; there were no assertion failures. The first wider attempt had two pytest temporary
directory permission errors, not assertion failures; the same pack passed with
an explicit writable `--basetemp`. `git diff --check` passed.

This is a calculation and provenance repair, not validation that GARCH predicts
realised volatility or that a target will be reached. Evening's target band is
advisory review, never a ticker-discard rule. The operator-started completed-
session Evening and Morning runs must still reconcile manifests, candidate
counts, thesis/contract identities and Lab display before production sign-off.
