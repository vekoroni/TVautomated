# Item 11 — D2-1 Step B, station 1: Discovery tier, order and win probability from the thesis engine

Status: APPROVED by ACK (D11-1..4, 10 Oct 2026); station 1 BUILT 10 Oct 2026. Decision 3 (9 Oct): a separate design and replay before the legacy
score is replaced. Replay: `ot11_discovery_tier_replay.py/.json` (live 8 Oct run 20261008_220129, read-only).

## Root cause (measured)

Discovery's `tier`, sort and `win_probability` come from the legacy Wyckoff/Crabel composite
(`avshunter_discovery_ULTIMATE.py`: `calculate_composite_score` 637, `assign_tier` 622 with hard-coded floors 50/35/25,
tier 0 from `detect_early_position` with Precor bonuses, `lift_proxy_score` sort with legacy `phase_align`,
`maturity_score`, `_convergence_score`; `win_probability = 40 + 0.25 x composite`). The thesis engine's readiness,
lane and geometry are already computed before the tier (lines 1725-1871 vs 1909-1922) but do not set it.

What that does on 8 Oct (2,933 survivors):
- **The tier says nothing about the thesis.** Legacy tier 0 ("early position", 1,249 rows): 236 are thesis-ready and
  GO, 119 ready but geometry-refused, 691 still waiting for their trigger, 203 have no active thesis.
- **The tier is near-constant.** Composite median 68 (5th pct 52) against floors 50/35/25: 98% are tier 0/1.
- **The horizon label is wrong for 98%.** Tier 0/1 -> `horizon_bucket` 1_5d for 2,880 rows; the setups' own evidence
  hold is over 20 sessions for 1,784 and 1-5 sessions for none. The contract runway already ignores the bucket
  (ACK 7 Oct: setup q80 hold, median DTE 71), but the "1_5d" label reaches the Lab (time horizon / hold window) and the
  Lab's vol-relative diagnostics.
- **`win_probability` is not a probability** (50-62, basis `COMPOSITE_RESCALED_NOT_A_PROBABILITY`), yet Vanguard's
  win-rate bridge seeds `win_rate_5d/10d/20d` from it when actuarial rates are missing (`run_vanguard_from_packages.py`
  1193-1231), which the EIL and the Lab's `win_prob_predicted` read.
- **The quality gate checks legacy ratios.** `validate_quality` aborts the Evening on tier counts (early ratio >= 1.5%,
  tier 1 + 2 > 0); on 8 Oct the early ratio is 37.6% (only a warning above 5%), so the check proves nothing.
- **Survival is not affected.** The tier-4 drop (`ELIG_TIER4_LOW_COMPOSITE`) removed no ticker in any of the last 8
  runs (26 Sep - 8 Oct lifecycle files). Survival is decided by data checks and the lane drop.

## Design (behind one switch, legacy code kept for rollback)

Config `config/discovery_thesis_tier_v1.json`: `tier_source` = `thesis_v1` (production) | `legacy_composite`
(rollback, today's behaviour). Under `thesis_v1`:

1. **Tier = thesis disposition** (one owner, `domain/thesis_tier.py`):
   - 0 `GO` — readiness READY_FOR_HUMAN_REVIEW and geometry not refused (item 3 rule; same set as GO);
   - 1 `READY_NOT_GO` — ready, geometry GEOMETRY_NOT_JUSTIFIED / INVALID_GEOMETRY;
   - 2 `WAITING` — adopted, WAIT_TRIGGER;
   - 3 `NO_ACTIVE_THESIS` — NOT_ADOPTED, CLOSED_*, no thesis.
   Published with `tier_basis` and `tier_label`. Replay: 528 / 266 / 1,644 / 495 (legacy 1,249 / 1,631 / 52 / 1).
2. **No legacy drop.** The tier-4 composite drop is off (it removed nothing in 8 runs; it would otherwise drop a
   ready thesis on a legacy score). Survival stays: data checks + lane drop.
3. **Order within tier**: the governing setup's held-out within-hold rate (item 10.1), then its lane hit rate, then
   ticker. Discovery order is processing / file order only; the rank owner stays E11b (`domain/opportunity_rank.py`).
   Replay overlap with the legacy order: top-50 3, top-100 6, top-200 20.
4. **`win_probability` = the setup's held-out within-hold rate** (0-1, basis `SETUP_RATE_WITHIN_HOLD_HELDOUT`, with n);
   null with basis `NO_SETUP_RATE` when the setup has none — never the composite. Replay: 2,496 covered, 437 null;
   median 0.30 (q10 0.19, q90 0.55). The Vanguard bridge then seeds measured rates or nothing (its 0.30-0.80 clamp and
   scale are checked at build; a clamp on a measured rate is removed or labelled).
5. **Horizon label from the evidence hold** (the Options `planned_hold_sessions` source, the setup's q80):
   1_5d / 6_10d / 11_20d / `OVER_20d`, `NO_EVIDENCE_HOLD` when none. Replay: OVER_20d 1,784, NO_EVIDENCE_HOLD 795,
   11_20d 285, 6_10d 69. The contract runway is unchanged (it already uses the evidence hold). Every reader of
   `horizon_bucket` is tested with the two new values at build (Options 353 / 1286-1290 / 6130, Lab 2000 / 4042).
6. **Quality gate**: survivors >= 15% of the universe (kept) and at least one thesis GO (replaces the early ratio and
   tier 1 + 2 rules). Replay: 88% and 528 GO - passes.
7. **Composite kept as labelled legacy context** (`composite_score`, `composite_adjusted`, `composite_basis =
   LEGACY_WYCKOFF_CRABEL`): EOD (`classify_tier`, SCS points) and Options (OIS, verdict relabel) still read it; they are
   the next stations, each with its own replay.

## Next stations (each its own switch and replay, in this order)

1. Options OIS: phase points (`compute_ois` 7393) and volume confirmation by phase (3698) -> thesis event/state.
2. Trap engine (`avshunter_trap_engine.py`, CHASE / EARLY_PROBE on phase / mode) -> thesis readiness and age.
3. Trigger layer T3 range break on phase C/D (`trigger_layer._t3_range_break`) -> thesis trigger events.
4. EOD `classify_tier` / SCS composite points -> thesis tier and E11b inputs.
5. Vanguard state key and EV3 barrier key: kept, labelled `LEGACY_STATE_KEY` (decision 4) until the actuarial
   database is rebuilt on thesis states.

## Tests (test-first) and acceptance

- `tests/test_ot11_discovery_thesis_tier.py`: tier from readiness + geometry; rollback switch gives the legacy tier;
  a ready thesis with a low composite is not dropped; order within tier; win probability = setup rate or null with
  basis; horizon from evidence hold with OVER_20d / NO_EVIDENCE_HOLD; quality gate passes on GO >= 1 and fails on 0.
- Pins first: `test_dynamic_session_phase2.py`, `test_avs_dir002_geometry_boundary.py` (tier3_min bypass) and the T3
  authority invariants are re-read; any that lock the legacy tier move to the rollback path deliberately.
- Acceptance: re-run this replay through the built code on 8 Oct and match the counts above; Discovery station
  inspection (item 10.3) zero STOP defects.

## Decisions for ACK

- D11-1 the four thesis tiers above (GO / READY_NOT_GO / WAITING / NO_ACTIVE_THESIS).
- D11-2 `win_probability` = the held-out within-hold setup rate, null when none (tied to the item-10 decision on
  switching lane / geometry to within-hold rates). It reads much lower than today's 50-62 label (median 30%).
- D11-3 horizon label from the evidence hold with the new OVER_20d / NO_EVIDENCE_HOLD values.
- D11-4 quality gate: >= 15% survivors and >= 1 thesis GO.

## As built (10 Oct 2026)

- Owner `domain/thesis_tier.py` (`thesis_tier`, `discovery_win_probability`, `discovery_horizon`, `discovery_order`,
  `quality_issues`); switch `config/discovery_thesis_tier_v1.json` (`tier_source` thesis_v1, rollback
  legacy_composite). Tier 0 reuses `trigger_layer.thesis_go_eligibility`, so tier 0 and GO cannot diverge.
- Discovery (`avshunter_discovery_ULTIMATE.py`): tier block, `tier_basis` / `tier_reason`, win probability with basis
  and n, `composite_basis = LEGACY_WYCKOFF_CRABEL`, horizon label + `horizon_hold_sessions` / `horizon_basis`,
  `discovery_basis = THESIS_<tier label>`, order, summary `tier_source` / `thesis_go`. Legacy paths kept behind the
  switch (tier-4 drop runs only on legacy_composite).
- Orchestrator `validate_quality`: thesis rule when the summary says thesis_v1; legacy ratios otherwise.
- Vanguard bridge: a SETUP_RATE_WITHIN_HOLD_HELDOUT win probability is carried as itself, never clamped to 0.30-0.80
  or copied into win_rate_5d/10d/20d (unused on 8 Oct: all 2,788 rows had V6_DB rates).
- Lab Discovery table: thesis tier label; a 0-1 rate shown as a percentage, none as none.
- Acceptance through the built owner on 8 Oct (`ot11_discovery_tier_replay.json`, `acceptance_built`): tiers
  479 / 315 / 1,644 / 495. The design replay said 528 GO: 49 ready rows had no recorded geometry in the replay (not in
  the book); the GO rule refuses GO without recorded geometry (item 3), and 479 equals item 3's live GO count. Horizon
  from Discovery's own evidence: OVER_20d 1,952, NO_EVIDENCE_HOLD 595, 11_20d 306, 6_10d 80 (Options later adds the
  pooled / volatility runway fallback for some of the 595; the contract runway is unchanged). Win probability covered
  2,496, null 437.
- Contract selection is unchanged by the new horizon values: one spread limit and one delta preference for every
  horizon (ACK 18 Sep), the DTE band is descriptive, unknown keys normalise to 1_5d as today.
- Tests `tests/test_ot11_discovery_thesis_tier.py` (8).
