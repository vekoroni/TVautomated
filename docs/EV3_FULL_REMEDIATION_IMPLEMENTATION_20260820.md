# EV3 full remediation implementation — 20 August 2026

## Outcome

All planned EV remediation stages are implemented. EV3 is connected to the
evening pipeline in advisory mode by default and has a fail-closed production
authority path. Production EV authority is intentionally not enabled until a
fresh, real-time pipeline run clears the activation gates.

## Backup and rollback

- Pre-change source and replay artifacts:
  `backups/ev3_full_remediation_20260820_prechange`
- Governed barrier cache:
  `C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.parquet`
- Promotion manifest:
  `C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.promotion.json`
- Promotion is atomic. If a governed cache already exists, the promotion tool
  copies it to `vanguard\data\backups\ev3_barrier_cache` before replacement.
- Authority overlay keeps a run-local
  `options_intelligence_*_pre_ev3_authority.csv` before its first in-place
  annotation.

## Implemented phases

### Phase 1 — canonical direction

- Separates the raw arbitration result from `direction_resolution_status`.
- Accepts resolved CALL/PUT rows including `CONFLICT_STRUCTURE_LEADS`.
- Routes STRANGLE/STRADDLE to `NOT_APPLICABLE_NON_DIRECTIONAL` rather than
  misclassifying them as unresolved defects.

### Phase 2 — selected and alternative contract handoff

- Publishes explicit selected-handoff readiness and missing-field diagnostics.
- Filters incomplete alternatives before EV evaluation.
- Does not fabricate a candidate when Options Intelligence supplied no selected
  or alternative contract.
- Resolves contract multipliers for selected contracts, long alternatives, and
  both vertical legs without assuming the standard multiplier is 100.

### Phase 3 — candidate evaluation diagnostics

- Evaluates complete alternatives and vertical debit spreads with the same
  lower-bound objective as long calls and puts.
- Parent `REJECT_NO_EVALUABLE_CONTRACT` records child rejection counts.
- Separates evaluated, rejected, and not-applicable populations.

### Phase 4 — barrier coverage

- Rebuilt the cache from 3,608 Polygon-adjusted ticker histories.
- Expanded target grid to 1–50% and stop grid to 1–25%.
- Supports exact 5/10/20-session outcomes.
- Adds a governed nearest-state fallback only when volatility and trend match
  and at least 5 of the 7 dimensions match.
- Requires at least 30 aggregate effective observations for fallback.
- Charges a 2% return uncertainty penalty for state fallback.
- Defaults missing target-exit timing late and stop-exit timing early, records
  the default, and charges a further 1% uncertainty penalty.

Promoted cache audit:

- Rows: 329,184
- States: 508
- Duplicate lookup keys: 0
- Missing ticker histories: 0
- Probability-sum maximum error: 2.22e-16
- Schema: `ev3-barrier-v0.3.0`
- SHA-256: `bb1c41c871b15a78efebf6824806bacbdccb6012f2116dbb73bacfe4517016bd`

### Phase 5 — rejection taxonomy

- Zero bid is `REJECT_LIQUIDITY_ZERO_BID` because no executable exit exists.
- A mathematically valid but wide quote reaches economic liquidity policy and
  is `REJECT_LIQUIDITY_SPREAD`.
- Unit-spread rejection is reserved for invalid numeric geometry.

### Phase 6 — governed horizon ordering

- Runs the macro horizon router after Options Intelligence.
- Patches the actual `options_intelligence_{run_id}.csv` artifact.
- Runs EV3 only after that patch, so EV and downstream sizing use the same hold.
- Retains a compatibility patch for `vanguard_signals_enriched` readers.

### Phase 7 — unified EV authority

- Always publishes a row-aligned EV3 overlay for downstream visibility.
- Default mode is `SHADOW_ADVISORY`; it cannot create or remove capital
  permission.
- Optional production authority is enabled with
  `AVSHUNTER_EV3_AUTHORITY_ENABLED=1`.
- Activation requires:
  - technical and functional health pass;
  - real-time strict clock (no functional-test timestamp);
  - governed final barrier cache;
  - no system defects;
  - no unclassified rejections;
  - at least 95% adjudication coverage;
  - one unique EV result for every source row.
- When active, NEGATIVE and INDETERMINATE block economics, data defects block
  data, and a POSITIVE result only clears the EV component. It never bypasses
  structure, macro, risk, horizon, morning, or live-execution gates.
- If authority is requested but any activation gate fails, the evening pipeline
  aborts before downstream GO-list construction.

## Verification

- Focused EV3 regression suite: 67 passed, 0 failed.
- Python compilation: passed for every changed Python module.
- Git whitespace/error check: passed.
- Controlled replay of run `20260818_041214`:
  - prior Phase-1 baseline evaluated rows: 145;
  - repaired final-cache evaluated rows: 193;
  - exact state evaluations: 158;
  - audited 5-of-7 fallback evaluations: 35;
  - barrier state rejections: 0;
  - barrier grid rejections: 0;
  - not applicable: 912;
  - system-defect rows from the old artifact: 34 missing multipliers.

The replay used old output generated before the multiplier/handoff fix. It
therefore proves the computation and fallback repairs but cannot clear the
production activation gate. A fresh evening run is required to verify the new
Options Intelligence handoff.

## Production activation procedure

1. Run one fresh evening pipeline with EV3 authority disabled (the default).
2. Review `ev3_shadow_phase_status_{run_id}.json` and require:
   `system_defects={}`, `unclassified_rejections={}`,
   `adjudication_coverage>=0.95`, and the governed cache path/hash above.
3. Confirm EV distributions and selected-contract examples manually.
4. Set `AVSHUNTER_EV3_AUTHORITY_ENABLED=1` and run the controlled production
   canary. The authority applier independently rechecks every gate.
5. Keep the switch off again if the canary aborts or produces no credible
   positive-EV component rows. Do not lower the gates merely to create trades.

## Broader regression note

The legacy `test_pipeline_regression.py` suite still reports four pre-existing,
out-of-scope failures: T10 sizing multiplier expectation, T14 convergence
deadband expectation, T16 EV-v2 regime invariance, and T25 a hard-coded Linux
path. None is in the EV3 execution path changed here; the focused EV3 suite is
green. They should be handled as a separate pipeline regression task.
