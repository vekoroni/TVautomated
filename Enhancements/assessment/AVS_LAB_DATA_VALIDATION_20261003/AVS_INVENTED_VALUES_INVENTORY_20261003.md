# Invented values inventory: the "3R class" across the pipeline (3 Oct 2026)

**ACK's question:** "have we got anything else like this", meaning a missing value replaced by a made-up one that downstream code treats as evidence.

**Method:**
- A data scan of the 1,554 served Lab rows (run `20261001_211641` with the 2 Oct Morning) for spikes at round values and implausible fills.
- A read-only code search of the production modules.
- The seven most serious code findings were re-read at source before being listed: findings 1, 2, 3, 4, 11, 12 and 17.

**Already fixed** (from the next Evening): TARGET_3R (D01/D13).

**Damage scale:**
- (a) feeds a gate, score or rank;
- (b) feeds a decision number shown to the trader;
- (c) display only.

## Families, findings and proposed treatment

### A. Invented price geometry (targets, stops, walls)

| # | Where | What is invented | Damage |
|---|---|---|---|
| A1 | `ev_engine_v2.py:113-115` | Missing target → entry +10%; missing stop → entry −5%. That is 2:1 by construction, and CALL geometry even for PUTs. `opt_mid` missing → $1.00 (line 111), so the NO_CONTRACT_PRICE gate cannot fire. | a: `ev2_ev_structural` gives up to 10 EOD SCS points (`eod_candidate_engine.py:1948`); EV sign in `trigger_layer.py:329`; SuperBrain `ev_gate` |
| A2 | `eod_candidate_engine.py:1641-1667, 2353` | Exit plan: target from expected move; wall := target when absent; T3 = ±3% beyond; missing values written as price 0.0. The wall lookup is direction-blind: a CALL can get the put wall below spot as T1. | b: `exit_t1/t2/t3` reach `bridge/order_manager.py` |
| A3 | `contracts/lab_control.py:3865-3868, 4322, 4741` | The gamma wall is published as `target_price` / `structural_target`, and its source is not recorded. | b |

**Treatment:**
- No invented geometry anywhere. A missing level is a stated state (NO_TARGET / NO_WALL).
- Targets come only from the **anticipated move** (approved direction, ACK 3 Oct).
- Walls are side-aware.

### B. Invented probabilities and statistics

| # | Where | What is invented | Damage |
|---|---|---|---|
| B1 | `avshunter_discovery_ULTIMATE.py:648-657` | `win_probability = 40 + 0.25 × composite`, clamped to 35–75: a rescaled score presented as a probability. An insufficient-data Wyckoff score of 20 gives 45%. | a: options EV, `path_score` in the route score, B2 |
| B2 | `scripts/avshunter_superbrain_layer.py:1815-1834, 2261` | When the actuarial win rates are 0, B1 is copied into `win_rate_5d/10d/20d`. The DISCOVERY_BRIDGE tag never reaches the output: line 2261 publishes **ACTUARIAL**. | a: EV v2 hit rates → `ev_final`, `ev_gate`, HARD GATE 0 |
| B3 | `vanguard/layer2_statistical/actuarial_query.py:1041-1046` | A RELAXED match is published with `state_match_similarity` 1.0 (exact). Dimensions the state vector lacks are dropped silently and the match is still tagged EXACT. | a: confidence weight → adjusted probabilities → `edge_quality` STRONG |
| B4 | `actuarial_query.py:1397-1506` | Hand-tuned intraday multipliers (1.6, 1.3, 1.2, 0.7…) rewrite the actuarial outcomes in place while N is kept. The label sits in the wrong field. | a: `edge_quality`, verdict |
| B5 | `vanguard/layer2_statistical/edge_detector.py:112-121, 684-697` | A thinner sample faces a lower EV floor; "high sample" ignores the match method. | a: `exported_edge_quality` |
| B6 | `scripts/avshunter_options_intelligence.py:7064-7073` | "Actuarial N=… robust sample size" fires on analogue and relaxed fallbacks (209 rows, 33 GO; SOFI was N=132,728 with an exact sample of 0/60). N=0 or missing gets no penalty while N=40 gets −15. | a: OIS factors |
| B7 | data | Wyckoff `phase_probability` takes round values (0.9 on 357 rows, 0.82 on 348, 1.0 on 281): heuristic constants published as probabilities. | b |
| B8 | `scenario_builder.py:149-170`, `probability_engine.py:60-69` | `prob_breakout = 0.25 + composite/200` | c (labelled) |

**Treatment:**
- One owner for outcome statistics: the measured base rates (C12 outcome scorer and replay).
- Anything not measured is NOT_ESTIMABLE, not a number.
- `win_probability` is renamed to what it is (a composite-derived index) and leaves every EV and gate.
- The match method travels with every statistic.
- Under CLAUDE.md rule 5 (legacy EV v2 is not an expected value), EV v2 should lose scoring authority entirely (A1, B2) rather than have its defaults repaired.

### C. Invented time (hold, DTE)

| # | Where | What is invented | Damage |
|---|---|---|---|
| C1 | data / `planned_hold_source` THESIS_WINDOW_D2 | `planned_hold_sessions` = 20 on all 1,554 rows. | a: reachable target, contract runway, theta drag, time value at exit, Morning runway |
| C2 | `eod_candidate_engine.py:2341` → `scripts/exit_rules_engine.py:38` | `dte` defaults to 30, and the exit rules read the defaulted `dte` before the governed `contract_dte`. | b: `exit_max_dte`, `exit_theta_date` (theta exit after expiry on 48 GO rows) |
| C3 | `scripts/avshunter_options_intelligence.py:4914, 1214, 7738` | Hold falls back to the DTE-matrix midpoint (28) or 5. | a: theta drag → OIS and route |
| C4 | `ev_engine_v2.py:105`; options `:3890, 3915, 2501` | DTE assumed 30 (EV horizon, BSM/Heston Greeks) or 1 (synthetic chain). | a/b |
| C5 | data `ts_dte_used` | Time stop computed on 30/45 DTE, not the selected contract. 140 of 144 GO rows have a time-stop expiry different from the contract's. | b |

**Treatment:**
- Hold = duration evidence (median and 80th percentile), UNESTIMATED when thin (approved direction, ACK 3 Oct).
- DTE comes only from the selected contract.

### D. Invented market data

| # | Where | What is invented | Damage |
|---|---|---|---|
| D1 | `scripts/avshunter_options_intelligence.py:6916-6919` | Missing Greeks/DTE: θ −0.01, ν 0.05, Δ 0.35, DTE 30. A missing theta scores "low drag". | a: OIS, verdict, route |
| D2 | `:4703, 4702` | Missing Wyckoff phase → "C" (+7, "optimal entry timing"); missing tier → 2. | a |
| D3 | `:7098, 7948` | Missing IV percentile → +8 "neutral"; `iv_rank or 50` → `iv_score` ≈ 76/100. | a |
| D4 | `wall_break_scorer.py:177-180, 258` | gamma-flip confidence 0.5, iv/hv 1.0 (with the text "Vol near parity (iv/hv=1.000)" stated as observed), unknown gamma velocity 5 points. | a: `wbs_grade` → exit mode, scale plan, sizing text |
| D5 | `execution_intelligence_runner.py:1010-1031`; options `:7853-7856, 2526-2528` | Spread assumed 8% or 15%; bid/ask rebuilt from mid. The rebuilt values pass the completeness check; one field is named `eil_spread_pct_live`. | a/b (partly labelled) |
| D6 | data | `atm_distance_sigma` = 0.0 on 491 rows whose strike is a median 3.7% (max 68%) from spot. | b: lifecycle and maturation scores |
| D7 | `WyckoffEngine_3101_v2.py:1302-1330` | Insufficient data yields invented scores and confidences (score 20, truth 15, phase 20, transition "B"). | a via B1 and Discovery lift |

**Treatment:** missing means UNKNOWN. A score abstains on that component and renormalises over the observed ones, and the card shows how many inputs were missing.

### E. Neutral constants inside scores

| # | Where | Constant | Damage |
|---|---|---|---|
| E1 | `scripts/avshunter_options_intelligence.py:7942, 7951` | `direction_fit` 70, `runway_score` 50 when missing (30% of the route score's weight) | a |
| E2 | `ev_engine_v2.py:179-189, 207-211, 223-225` | predictability and calibration fall back to composite or 50; data quality 100 (so DATA_WEAK never fires); breakeven pass True; runway 2.0 | a |
| E3 | `avshunter_discovery_ULTIMATE.py:1520, 1537, 1602, 1785, 1795` | truth confidence 50, recency 0.5, regime alignment 0.5, maturity 0.5, comp ratio 0.85 | a: `lift_proxy_score` → candidate lane |
| E4 | `scenario_router.py:123-136` | alignment 50, path MODERATE | b |
| E5 | data | EIL component scores near-constant (iv 90 on 1,174 rows, poc 45 on 1,128). Source not yet traced. | a: EIL verdict in flags and candidate reasons |

**Treatment:** same as D. The weight of a missing input is never filled with a "neutral" value.

### F. Broken code that hides a gate

| # | Where | Defect | Damage |
|---|---|---|---|
| F1 | `avshunter_monetisation_policy.py:463-475` (copy at `scripts/…:591-604`) | `_int()` has no return path for valid values; its `int(float(v))` sits unreachable inside `_bool`. DTE, tier and contradictions are always None/0. The FATAL "DTE too low" gate can never fire, and every row logs "DTE acceptable". | a |

**Treatment:** a plain bug fix (test-first).

### G. Circular checks

| # | Where | Defect | Damage |
|---|---|---|---|
| G1 | `scripts/avshunter_options_intelligence.py:7732-7754, 7911` | The expected move includes the target distance, so breakeven feasibility judges the target against itself. | a: 15% of the route score |

**Treatment:** the expected move comes from volatility and outcome evidence only. This is part of the anticipated move.

## Proposed build order (each test-first, one defect at a time; acceptance with the outcome scorer)

1. **F1**: smallest, restores a FATAL gate.
2. **Anticipated move + evidence-based hold**: replaces A1–A3, C1–C5 and G1, and removes R:R from scoring.
   - Invalidation stays on the card as the thesis exit (ACK 3 Oct).
   - Includes the earnings disclosure (N2).
3. **EV v2 and the bridged win probability lose scoring authority** (B1, B2, A1, E2), per CLAUDE.md rule 5. They remain in the audit tier labelled legacy.
4. **Statistics carry their match method; unmeasured = NOT_ESTIMABLE** (B3–B7).
5. **Missing = UNKNOWN with abstaining, renormalised scores** (D1–D7, E1, E3–E5).

Together with N1 (no GO without an eligible trigger), N3/N4 (quote and confirmation labels) and N7 from the data validation, this is the build before ACK's manual run. Not yet traced: the `vanguard/ev_engine*.py` copies and the source of the EIL constants (E5).

## Build receipt: step 1, F1 monetisation DTE gate (3 Oct 2026, ACK "approved, start with step 1")

**Root cause:** in `map_options_row_to_policy_input`, `_int()` had lost its conversion. The `int(float(v))` sat unreachable after `_bool`'s return, so DTE, tier and contradictions always read as None/0. The FATAL `OPT_001` gate could never fire, and a missing DTE was logged as "DTE acceptable". Both copies carried the defect; production loads the root copy (`execution_intelligence_runner` imports it by name).

**Change** (uncommitted):
- `_int` restored in `avshunter_monetisation_policy.py` and `scripts/avshunter_monetisation_policy.py`.
- In the root copy, a missing DTE is now stated ("No contract data — DTE gate skipped") rather than called acceptable, matching the scripts copy.

**Tests:** `tests/test_avs_monetisation_dte_gate.py`, 10 tests (5 rules × 2 copies). Seen red for the business reason (DTE read as None; missing DTE called acceptable), then green. All 9 related test files pass.

**Acceptance against reality:**
- The old and fixed policy were replayed on the 1,554 execution rows of run `20261001_211641`. **0 decisions changed** (state, block reason, size, priority).
- In that run DTE now reads on 1,349 rows (minimum 15 sessions; none under 5) and no row carries `contradictions_count`.
- The gate is restored for future runs with no effect on the current book. The outcome scorer has no metric to move.

**Found during the replay, for step 3:** 372 rows in the run were hard-blocked by the policy with "Negative premium RR", a stop/target-derived R:R gate. It is replaced by the anticipated move, together with TARGET_3R.

## Build receipt: step 2, quote age disclosed, never a gate (3 Oct 2026, ACK "yes, go ahead with step 2")

**Change** (uncommitted):
- **New `quote_age_disclosure()`** in `domain/long_option_execution.py`, the owner of the feed delay and window. It reports `quote_age_state` (WITHIN_FEED_WINDOW / BEYOND_FEED_WINDOW / UNKNOWN), `quote_age_minutes` (raw) and `quote_requote_instruction` = REQUOTE_AT_BROKER_BEFORE_ENTRY.
- **Age gates removed:**
  - `evaluate_execution_viability` (REQUOTE_REQUIRED);
  - `classify_current_executability` (QUOTE_STALE);
  - `vanguard/ev3_stage0.py` (REJECT_QUOTE_STALE). A future-dated timestamp is now REJECT_QUOTE_TIMESTAMP_FUTURE.
  - `empirical_option_ev.py` (dormant 30-minute null).
- **Gates kept, because the quote is unusable:** crossed or negative quote, zero bid, spread above policy, no quote, missing timestamp.
- `contracts/contract_rejection.py` "REJECT_STALE_QUOTE" is an invalid-quote gate under a misleading name. It is kept and noted for renaming.
- **Display:** the trade card quote row reads "<timestamp> · N min old at the Morning check (delayed feed) · re-quote at broker before entry". The trade setup no longer calls a delayed quote "current" (N3).

**Tests:**
- New `tests/test_avs_quote_age_disclosed_not_gated.py` (6) and 2 new trade-card tests; seen red, then green.
- 7 tests in 6 files that pinned the retired age gate were restated to the new rule, each with a note.
- Regression: 145 files, 143 pass, 1 skipped by design, 1 non-test file. No failures.

**Acceptance (2 Oct Morning rows):**
- Of the 107 rows blocked on age by execution viability, 74 have an executable quote; 33 stay blocked on their real book (27 wide spread, 5 manual liquidity review, 1 zero bid).
- Of the 101 lifecycle rows parked QUOTE_STALE, 73 are executable; 28 stay held on their book.
- The 1,112 EV3 age rejections will be valued, advisory only, on the next run.

## Build receipt: N1, Morning GO requires a GO-eligible trigger (3 Oct 2026, ACK "fix N1 next")

**Root cause:** GO was the fall-through `else` of the Morning verdict (`morning_gate.py`). Trigger eligibility and the EOD candidate status were never checked. Run `20261001_211641`: 192 of 347 Morning GO verdicts had no eligible trigger (139 REPAIR_AT_OPEN, 53 WATCH_ONLY).

**Change** (uncommitted): two checks before the final GO.
- **EOD WATCH_ONLY** → FLAG, permission WATCH_ONLY, NO_TRADE, with the EOD reason.
- **`trigger_go_eligible` not true** → FLAG, AWAITING_TRIGGER, NO_TRADE, "Wait for a GO-eligible trigger (trigger_primary=…)". Missing eligibility is stated as TRIGGER_ELIGIBILITY_NOT_RECORDED.
- Rows stay in the book (rank, don't gate). A repair candidate with an eligible trigger may still be GO.

**Tests:**
- New `tests/test_avs_n1_morning_go_requires_trigger.py` (5); seen red (no-trigger rows were GO), then green.
- GO fixtures in `test_morning_gate_authority.py` and `test_morning_gate_contract_repair.py` now carry `trigger_go_eligible` (noted).
- `test_ila_selected_contract_identity.py` was already failing on approved additive fields (TEV-001 forecast fields; the 2 Oct trade-card schema; D10's evidence flag). Its allowlist was updated with sources.
- 75 Morning/Lab-related files pass.

**Acceptance against reality** (`Enhancements/direction_evidence/n1_morning_go_trigger_outcomes.py`: 14 earlier Morning sessions, 3,164 GO rows; first touch of ±1 daily ATR in the trade direction within 10 sessions):
- **GO with an eligible trigger:** 48.9% (n=1,279 resolved); mean signed 5-session return −0.07%.
- **GO without one** (removed by N1): 44.3% (n=1,036); −0.40%.
- **Difference:** +4.6 pt, 95% [+0.5, +8.7] (session-block bootstrap).
- **Caveat:** 14 overlapping sessions. Eligible GO is still below 50%, so the trigger is necessary but not sufficient. The remaining edge work is direction (BEH-001, live from the next run), the anticipated move and the hold.

## Build receipt: EV v2 retirement completed (3 Oct 2026, ACK "go ahead with the EV v2 retirement")

**Finding:** the 30 Sep retirement removed EV v2 only from the Lab page. It still fed live decisions:
- the EOD conviction score (up to 10 points from `ev2_ev_structural`);
- SuperBrain's negative-EV gate (EXECUTE_WITH_RISK cap), its DATA_WEAK warning (built on EV v2's invented data quality) and the `ev_gate` label;
- the runner's overwrite of the plain `ev` / `ev_final` / `ev_net` / `ev_base` fields (a legacy figure presented as EV);
- the trigger layer's "authoritative EV" read.

The final decision engine's EV ladder was already neutralised in production (`fd_verdict` WATCHLIST on all 1,554 rows of 1 Oct); its EV is recorded only.

**Change** (uncommitted):
- `eod_candidate_engine.py`: both SCS scorers give 0 EV points; the breakdown reads "EV v2 retired (not an EV)".
- `scripts/avshunter_superbrain_layer.py`: gate 0a (DATA_WEAK) and the negative-EV gate are removed; `ev_gate` = RETIRED; the unused variables are removed.
- `execution_intelligence_runner.py`: the overwrite is removed; EV v2 stays under its own `ev2_*` names (legacy).
- `trigger_layer._compute_ev`: no longer reads EV v2 fields.

**Tests:** new `tests/test_avs_ev2_retired.py` (4); seen red, then green. 30 related files pass.

**Acceptance:**
- SCS old vs new on the 1,554 rows of run 20261001_211641: 1,223 scores fall (max −10); rank correlation 0.976; top-50 overlap 28 of 50.
- EV v2's ranking power on 14 earlier Morning sessions (4,023 rows, 8 sessions with more than 20 rows): IC vs the 5-session signed return **−0.021**; top-minus-bottom quintile −0.18%. No information was lost; the reshuffle removes a score built on invented inputs.
- The ranking change is measured forward with the outcome scorer.

## Correction: SuperBrain gates were not live (3 Oct 2026)

Production's Phase 8d runs only `run_superbrain_passthrough` (it copies the options CSV to `superbrain_enriched`). SuperBrain's `process_signal` / `assemble_execution_plan` do not run; their logic was migrated to options intelligence on 2026-04-28.

The SuperBrain items in this inventory (B2 bridge, E2/A1 via `ev_gate`, the R:R gates 0b/0b2, the EV gate and DATA_WEAK) were therefore dead code. Removing them changed no production decision. The **live** parts of the R:R and EV v2 retirements were:
- the EOD scores;
- the options route flag;
- the runner's `ev` overwrite;
- the trigger layer.

The audit's "feeds a gate" ranking did not separate live from dead paths. Liveness is now checked before each change.

## Build receipt: B2, win rates say what they are (3 Oct 2026, ACK "start the statistics labelling")

**Live defect:** the Lab book materializer (`contracts/lab_control._recompute_governed_lab_fields`) and the Lab server labelled every row's `win_rate_source` "ACTUARIAL" by default (1,554 of 1,554 on 1 Oct), whatever the match method, and EXACT and analogue matches looked the same. The SuperBrain bridge (dead code) copied the composite-derived `win_probability` into the win rates.

**Change** (uncommitted):
- **New `domain/statistics_provenance.py`** (the family-B labelling owner): `win_rate_source_label()` gives ACTUARIAL_<METHOD> when measured win rates exist (win_rate_* > 0, or `win_prob_predicted` with a positive actuarial sample), else NOT_ESTIMABLE.
- Used by the Lab book materializer, the Lab server default and SuperBrain's output.
- The SuperBrain bridge is removed; its import is placed after its path setup (standalone import verified).

**Tests:**
- New `tests/test_avs_b2_win_rate_source.py` (5). Seen red. A first version of the rule missed the book's fields (every row became NOT_ESTIMABLE on the 1 Oct book); the book-fields test was added red, then fixed.
- The golden test maps the old UNAVAILABLE to NOT_ESTIMABLE (noted).
- 40 related files pass.

**Acceptance (1 Oct book):** labels go from ACTUARIAL ×1,554 to ACTUARIAL_EXACT 1,204 / ACTUARIAL_ANALOGUE 252 / ACTUARIAL_RELAXED 98. SOFI: ACTUARIAL_ANALOGUE.

## Build receipt: B1, win_probability is not a probability (3 Oct 2026, ACK "go ahead with B1")

**Live consumers (verified in options intelligence, the production path):**
- 5% of the options research route score (`path_score`);
- the options layer's own EV fields (`ev_structural` / `ev_ratio` / `ev_adjusted` = win_prob × gain at target), whose only reader is OIS advisory text;
- a missing `win_probability` defaulted to 50.

**Found while checking (a gap in the R:R removal):** the route score still weighted stop-based R:R (`payoff_score`, 15%). It is now removed as well.

**Change** (uncommitted):
- **`scripts/avshunter_options_intelligence.py`:**
  - `path_score` and `payoff_score` = None; the route score is renormalised over the remaining components (weights summing to 0.80), so the 75/60/45 thresholds keep their scale.
  - No EV is computed from the composite-derived number; `economics_ev_state` = NOT_COMPUTED_NO_MEASURED_PROBABILITY.
  - OIS shows "EV not computed" rather than "EV/premium=0.00".
  - A missing `win_probability` is None, not 50.
- **`avshunter_discovery_ULTIMATE.py`:** `win_probability_basis` = COMPOSITE_RESCALED_NOT_A_PROBABILITY (the field is kept: repair, don't delete).

**Tests:** new `tests/test_avs_b1_win_probability.py` (4); seen red, then green. 66 options-intelligence and related files pass.

**Acceptance (replay of the route score from the stored components, 1,554 rows of run 20261001_211641):**
- Mean score 59.4 → 68.2 (`payoff_score` averaged 16.7 of 100 and dragged scores down).
- Routes: GO 462 → 875 (413 from ARMED); ARMED 547 → 349; PROBE 263 → 114 (+60 from below 45, −7 to below 45).
- The consequential line downstream is 45 (reviewable GO/ARMED/PROBE vs blocked or equity-only): +60 / −7 rows. The GO/ARMED/PROBE labels within the reviewable set are display-level.
- Without renormalisation, GO would fall to 171 and many rows would cross into blocked.
- Kept: renormalisation. Reported to ACK.

## Build receipt: B6, the actuarial sample says what it measured (3 Oct 2026, ACK "go ahead with B6")

**Live defect (OIS, options intelligence):**
- "Actuarial N=… — robust sample size" was printed for any N ≥ 200 whatever the match method. SOFI: N=132,728 from an ANALOGUE fallback whose exact sample was 0/60.
- A missing or zero sample got no penalty while N=40 got −15.

**Change** (uncommitted): `actuarial_sample_quality(n_obs, match_method)` in `scripts/avshunter_options_intelligence.py`, used by `compute_ois`.
- Missing / 0 → −15, NOT_ESTIMABLE.
- EXACT: the bands unchanged; "robust" only for EXACT N ≥ 200.
- RELAXED / ANALOGUE / unknown with N ≥ 200 → −5, "N is the pooled fallback sample, not this exact state". Smaller fallbacks take the thin bands, with the method named.

**Tests:** new `tests/test_avs_b6_sample_quality.py` (4); seen red, then green. 67 options-intelligence and related files pass.

**Acceptance (1,554 rows of run 20261001_211641, the method resolved as production does: `actuarial_match_type`, else `layer2__state_match_method`):**
- 333 rows lose 5 OIS points: all 252 ANALOGUE and 81 RELAXED. No EXACT row changes; no row lacked a sample.
- 29 rows fall below the tier-A options floor (35) and 13 below tier B (25).

## Build receipt: B3–B5, Vanguard statistics say what they are (3 Oct 2026, ACK "go ahead with B3-B5")

**Liveness checked first (run 20261001_211641, `vanguard/vanguard_signals.csv`):**
- **B3 live:** 1,367 rows published similarity 1.0, but only 1,262 are EXACT. The 105 RELAXED matches claimed 100% similarity.
- **B4 dormant:** the intraday multipliers fail closed without intraday rows; every row's adjustment note is blank. Recorded, not changed.
- **B5a correct but not decision-live:** `_scaled_ev_floor` discounted the EV floor to 65% at n=50. It changes only `has_edge`, and the published verdict (ACTUARIAL_SUPPORT/MODERATE) requires a STRONG/MODERATE edge quality anyway. Fixed for correctness.
- **B5b live:** "high sample" ignored the match method. 59 non-exact rows (analogue/relaxed pools) got STATISTICAL_MODERATE, hence exported MODERATE, hence the ACTUARIAL_MODERATE verdict (options-scope "Vanguard support").

**Change** (uncommitted):
- `actuarial_query.py`: the RELAXED branch publishes `state_match_similarity` = None (not measured). Its confidence weight comes from the method table, unchanged; the phase-2 validator requires a similarity only for ANALOGUE.
- `edge_detector.py`: `_scaled_ev_floor` returns the full floor at every sample size; `high_sample` requires `state_match_method` == EXACT (the field is set on the final outcomes).

**Tests:** new `tests/test_avs_b3_b5_vanguard_statistics.py` (3); seen red, then green. 16 Vanguard/actuarial files: 15 pass; `test_vanguard_reference_input_p2` shows its 3 known DCV-clock baseline failures.

**Acceptance (1 Oct):**
- 59 rows lose ACTUARIAL_MODERATE (→ WEAK); 56 of them stay in the options scope through their Discovery tier, so at most 3 leave it.
- 105 RELAXED rows stop showing similarity 1.0.

**Noted for the list (not changed):** every Vanguard row's edge basis is `BULL_ONLY_LEGACY`. The edge is computed on upside probability, even for put theses.

## Build receipt: B7, Wyckoff heuristic scores are not probabilities (3 Oct 2026, ACK "go ahead with B7")

**Liveness:** `wyckoff_phase_validator` publishes phase / alternative / transition "probabilities" built from weighted heuristic scores with fixed transforms (p5 = 0.6 × p10, p20 = p10 + 0.20, invalidated forced ≥ 0.80), and an "expected bars remaining" range derived from them (SOFI "2–11"). Nothing gates on them (`lab_control._phase_status` is a different, pipeline-phase concept). Consumers: the Lab book / evidence drawer, and the older Interpreter engine's evidence groups.

**Change** (uncommitted):
- The validator publishes `probability_fields_basis` = HEURISTIC_SCORES_NOT_CALIBRATED_PROBABILITIES and `expected_bars_remaining_basis` = DERIVED_FROM_HEURISTIC_SCORES (book fields `wyckoff_validation_*_basis`).
- `pipeline_interpreter_engine` no longer hands the model the three transition "probabilities". The correctness and maturity scores, labelled as scores, remain.

**Tests:** new `tests/test_avs_b7_wyckoff_heuristic_scores.py` (3); seen red, then green. The golden book test allowlists the two basis fields. 76 related files pass.

**Noted, not changed:** the current desk's evidence (`interactive_desk.py`) carries `phase_transition_probability` from the physics model, likely another heuristic "probability". Its producer is to be checked in the next family.

**Family B status:** B1, B2, B3, B5, B6 and B7 done; B4 dormant (recorded); B8 (scenario probabilities linear in composite) is labelled and display-only, unchanged.

## Family D/E, missing means unknown: liveness first (3 Oct 2026, ACK "start the missing-means-unknown family")

| Item | Liveness on run 20261001_211641 | Action |
|---|---|---|
| D1 Greeks/DTE defaults in options economics | Dormant: every selected contract has model Greeks (1,349 Heston); the 205 without a contract are already declined | Recorded |
| D2 phase "C" / tier 2 defaults | Dormant: Discovery never omits phase or tier (1,666 rows) | Recorded |
| D3 IV percentile/rank 50 and E1 runway 50 in OIS/route | Fire only on the 205 no-contract rows, already BLOCKED (198) or PROBE via the missing-data rule (7) | Recorded |
| E1 direction_fit 70 | A rule (strategy ≠ direction), not a missing-data default | Out of scope |
| D4 wall-break defaults | Nearly dormant: "iv/hv=1.000" on 9 of 1,208 rows | Recorded (low) |
| D6 ATM distance 0 on 491 rows | **Not a defect:** all ITM (458) or ATM (33); distance still to travel is 0 by design. The earlier audit misread it | None |
| E3 Discovery lift defaults → candidate_lane | Not decision-live (read only by the drop-off audit) | Recorded |
| E4 scenario router alignment 50 | Not decision-live (no EOD/Morning/trigger consumer) | Recorded |
| **E5 EIL scores rows with no options quote** | **Live:** 205 no-chain rows got composite 74.75 from no-data defaults (liquidity "No options bid/ask data" → spread 85; IV "No IV data" → 70 "CLEAN") → EXECUTE claims later overwritten to NOT_EVALUATED, but the composite stayed and earned Lab ranking credit (composite weight, conviction bonus +2) and the EOD pse_score fallback | **Fixed** |

**E5 change** (uncommitted):
- `execution_intelligence_runner._eil_not_evaluated_without_quote`: no bid/ask → `eil_v3_verdict` NOT_EVALUATED, `eil_composite_score` None, `eil_not_evaluated_reason` NO_OPTIONS_QUOTE.
- `iv_distortion`: the no-IV-data verdict is NO_DATA, not CLEAN (only `passed` is consumed).
- Tests: new `tests/test_avs_e5_eil_no_quote.py` (3); seen red, then green. 37 related files pass.
- Also fixed: `test_lab_structure_detail_f6` pinned the structure-detail field count at 43; B7's two basis fields make it 45. The B7 regression filter had missed this file; all Lab/structure files now pass.

**Found, latent rule-6 breach (not changed; for ACK):** `execution_intelligence.py` adds a macro modifier to the EIL composite (CALL_TAILWIND +10, PUT_HEADWIND −15). It is dormant today because `macro_bias` (written into Discovery rows by `apply_macro_enrichment_to_discovery`) does not reach the EIL input. If it ever flowed, macro would move a score, against CLAUDE.md rule 6.

**Resolved 3 Oct 2026 (ACK "yes, remove it and run the full suite"):** the EIL macro modifier is removed from `execution_intelligence.py`. Macro bias no longer moves the composite in any state. It was also direction-blind: PUT_HEADWIND marks a weak sector, which is a tailwind for a put. `ctx._macro_bias` stays as display only. Live effect: none, because it fired on 0 rows on 1 Oct. New test `tests/test_avs_eil_macro_never_scores.py`: red first, then green. EIL tests (E5) pass. Full-suite receipt below.

**Full suite, 3 Oct 2026, after the macro removal:** 402 files, one process each; 3,349 tests passed, 1 skipped, 6 failed. All 6 failures are known baselines: the DCV clock in `test_vanguard_reference_input_p2` (3) and in `test_canonical_manifest_p1` (1) is parked, and the untracked-modules check in `test_avs_fix_002_stage0` and `test_avs_int001_stage0` (1 each) clears on commit. No new failures.
