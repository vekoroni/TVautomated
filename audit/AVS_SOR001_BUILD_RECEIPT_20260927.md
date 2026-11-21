# AVS-SOR-001 build receipt — 27 September 2026

Status: **corrected structural code is now the default; full pipeline release
acceptance is still open**.
No Evening/Morning pipeline, broker action, universe change, database write,
model fit, or trade authority was performed.

## Implemented in this slice

- `canonical_data/structure_feature_reader.py`: read-only, mandatory-as-of
  canonical OHLCV feature window ending at the historical decision session.
  It uses the revision/batch lineage already used by the outcome-path reader,
  retains volume for Wyckoff/compression, fingerprints the selected version,
  and reports partial, late-acquired or absent sessions rather than filling.
- `WyckoffEngine_3101_v2.py`: the recent material test is compared to a local
  range frozen *before* that test. The previous all-history range included the
  event bar, making a current breakout/breakdown and spring evidence unreachable.
  The present 20-prior-bar / 10-event-bar window is an **implementation
  hypothesis**, not a calibrated optimum or a completed episode detector.
  It is now the default for every engine call. The opt-in switch and legacy
  all-history range branch were removed at the user's direction. Population
  drift, episode classification and full pipeline acceptance remain open.
- `canonical_data/forecast_path_reader.py`: its internal revision selector now
  supports explicit feature columns, so the feature window can reconstruct
  historical volume without changing the default outcome-path read contract.
- `avshunter_discovery_ULTIMATE.py`, `enums_structural.py`, `swing_fusion.py`:
  the Crabel producer now emits a typed state consumed by fusion. Qualifying
  NR7/extreme compression is `READY`, other qualifying compression is
  `COILING`, measured no-compression is `NONE`, and missing/insufficient input
  is `DATA_INSUFFICIENT`. Fusion retains that last state in its audit rather
  than silently turning it into `NONE`. The present state thresholds are
  structural hypotheses, not calibrated option-edge estimates. A typed state
  is now emitted on every producer call; the opt-in switch was removed at the
  user's direction, so Discovery passes that state into fusion by default.
- `domain/structure_mode_phase.py` and Discovery: a separate versioned
  `wyckoff_mode_phase_key` preserves mode and phase together. Thus distribution
  Phase C cannot alias accumulation Phase C, while unknown mode/phase remains
  explicit. It never pairs a Precor mode with a phase taken only from the
  independent engine; a companion source field identifies the pair. The old
  `wyckoff_phase_bucket` remains unchanged for compatibility
  with the current actuarial state hash. This field is **not yet consumed by
  Vanguard or the estimator** and must not be presented as a completed repair.

## TDD evidence

1. New historical-window test first failed on missing module, then its volume
   assertion failed until the feature contract was completed.
2. Two Wyckoff counterexamples first failed: breakout range high included the
   breakout bar (105 instead of prior 102), and spring range low included the
   spring bar (95 instead of prior 98).
3. The new and nearby offline tests then passed: **75 passed** across SOR-001,
   TEV-001, Wyckoff phase/directional and audit-guard suites, with pytest's
   base temp explicitly directed to the task workspace. The default Windows
   pytest temp root was access-denied; that environmental error was not a
   code failure.
4. Read-only real-store smoke: VST, decision session 2026-09-25, as-of
   2026-09-26 12:00 UTC, returned 20/20 completed bars, no missing sessions,
   no revision rewind. A 40-bar feature window was accepted by the Wyckoff
   engine and returned Phase B / EQUILIBRIUM / NONE. This is a compatibility
   observation, **not** validation of the phase or a trading signal.
5. A broader Discovery/macro/F4 test command emitted three passes and then
   stopped producing output for over a minute; this test command was
   interrupted. The five Discovery/F4 cases passed when run separately;
   `test_macro_enrichment_stamps_discovery_and_options_advisory_score` remains
   **unverified**, because it writes a temporary CSV under the production
   repository's `data/output/qa` and did not finish in the bounded run. It
   requires isolated diagnosis before release.
6. The Crabel producer→fusion tests failed red on missing `state`; after the
   typed contract change, **23 passed** across Crabel, F4 and directional
   suites. This is a separate overlapping suite, not an additional 23
   independent tests to sum into a release total.
7. Before default-on cutover, **34 passed** across SOR-001 structural/Crabel,
   directional, Wyckoff, F4 and Discovery timestamp suites. The earlier
   legacy-default assertions were then replaced by corrected-default tests.
8. Mode/phase identity first failed red at import. After implementation, its
   counterexamples passed; **11 passed** in the focused SOR-001 boundary
   suite (identity, feature window, range, compression/fusion). This is not
   a population reconciliation or end-to-end release test.
9. Default-on counterexamples failed red in six cases (self-included range
   and missing Crabel state). After removing both opt-in switches, **24
   adjacent Discovery, Vanguard, Wyckoff and SOR-001 tests passed**. This
   verifies the default code path, not historical population drift or a
   completed Evening/Morning run.
10. A C5→C6 counterexample failed red: `INVALIDATED` and
    `DATA_INSUFFICIENT` forecasts could still generate a directional option.
    The C6 expression boundary now retains those rows with typed
    `NOT_APPLICABLE_*` reasons and no contract. **15 nearby C5/C6/vertical
    tests passed** after the repair.
11. The read-only S0 support audit was rerun. Actuarial v7 still has 3,817,003
    rows and 59 raw mature 20-session date blocks, but these are not
    version-equivalent, independent C4 first-passage starts. The sampled
    governed cohort has no matured 20-session path, so neither the new C4
    estimator nor C8 numeric EV can be asserted ready from that inventory.
12. Read-only canonical acquisition audit: `ohlcv_daily` has historical bars
    back to 2021, but the minimum `observed_at` for each 2021–2025 trading
    year is in August 2026. The strict same-date acquisition check finds
    only eight trading dates with any such rows (one August, seven September).
    This does not erase their value for retrospective pattern research, but
    it prevents calling a replay on those rows point-in-time *system-known*
    evidence at the old decision dates. A complete, signed-off C4 calibration
    and C8 numeric valuation cannot be certified from this inventory now.
13. The combined offline SOR-001/TEV-001/Discovery/Vanguard/Wyckoff suites
    passed **65 tests** after the default-on structural change and C6 guard.
    The whole repository suite, population drift, chronological replay and
    live handoffs have not passed or run.

## Remaining gates before end-to-end completion

1. Independent, versioned Wyckoff mode/phase episode ontology and prior-range
   detection beyond the temporary rolling-window hypothesis; blinded chart
   review, transition tests, full-run before/after drift audit and rollback.
2. Full-run compression producer→fusion output drift/intent reconciliation,
   then Vanguard L1/L2 historical matching against the same dated,
   version-equivalent episode features. Focused parity is green; population
   and downstream acceptance remain open.
3. Point-in-time feature/label availability across both databases for the full
   comparable population; first-event and censoring panel, independent support
   audit against unchanged TEV-001 floors, and held-out calibration.
4. C5 scenario composer, C5→C6→C8 full-path contract, quote economics,
   Morning additive revisions, Lab/Interpreter parity and journal replay.
5. Whole offline regression and governed human-reviewed release. No current
   code here grants option selection, execution, capital or model authority.

The new files and modified engine are uncommitted. The corrected calculations
are no longer shadow-only, but do not classify the whole pipeline as accepted
or start a run solely because these focused tests pass.
