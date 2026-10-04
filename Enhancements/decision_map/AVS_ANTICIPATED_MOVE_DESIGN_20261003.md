# Design: the anticipated move replaces R:R; the hold comes from evidence (3 Oct 2026)

**Status:** for ACK approval. No code until approved.

**ACK, 3 Oct 2026:**
- "we should not be using stops in the anticipated move. I think R:R should be removed and replaced with an enhanced anticipated move."
- Keep the planned hold, sourced from analysis.
- Keep the invalidation on the card as the thesis exit.
- Catalysts are bonuses; the earnings date is risk disclosure.

**Authority and rules:**
- Spec v1.1; CLAUDE.md rules 4–6.
- R1 (missing is never neutral), R2 (one owner), R3 (units in names), R6 (labels say what was measured), R10 (measured against reality), R11 (rank, don't gate).
- EV authority stays retired (rule 5). Nothing below is an expected value or carries capital authority.

## 1. What it replaces

| Today | Problem | Replaced by |
|---|---|---|
| TARGET_3R and the stop-based `rr_*` (A1–A3) | The reward is derived from the stop, so it is circular (3R class) | §3 magnitude |
| "Negative premium RR" FATAL block in the monetisation policy (372 rows on 1 Oct) | A stop/target geometry block | §5 coverage. This is decision D-B |
| `planned_hold_sessions` = governed `outcome.window_sessions` (20) on every row (ACK D2) | One constant for every ticker; no analysis | §4 time. This is decision D-A |
| DTE defaults of 30, 28 or 5 (C2–C4) | Invented time | The contract's own DTE; §4 |
| Expected move includes the target distance (G1) | Circular feasibility | §3: volatility and replay evidence only |
| R:R points in EOD scoring and the SuperBrain R:R gate | Scores a fiction | §6 ranking component. This is decision D-C |

## 2. One owner, existing parts reused

**Owner:** a single function, `anticipated_move_fields(row, candidate, contract)`. It sits in `scripts/avshunter_options_intelligence.py` beside the existing `reachable_target_fields` (the current owner of target and R:R), which it absorbs. No new module.

**Inputs it reuses:**

| Input | Existing owner |
|---|---|
| Thesis side and primary candidate | `handoff_thesis` (BEH-001; `thesis_event_candidate_id` on the row; candidate in the behavioural candidate packet) |
| Structural level | Candidate `Outcome_Level` and `Outcome_Definition` (next pivot / measured move; `domain/structure_behaviour/signals.py`) |
| Timing and path evidence | `Duration_*` fields from `attach_duration`: `config/beh001_duration_evidence_v1.json`; C12 Aalen–Johansen; groups by timeframe × scope × type × direction × test × age bucket |
| Volatility | `domain.volatility_budget` σ (as used by `reachable_target_fields`) |
| Contract value at a future spot and time | `contracts/selected_contract_economics.evaluate_timevalue_monetisability` (Black–Scholes, IV held, stated assumptions) |
| Outcome measurement | C12 (`avshunter/c12_outcome/passage.evaluate_passage`, matched base rate) |
| Earnings date (disclosure) | `earnings_calendar_enricher`, fed from MarketData `/v1/stocks/earnings/` (tested working, 3 Oct) |

## 3. Magnitude: how far

1. **`structural_level`:** the primary candidate's `Outcome_Level`, on the thesis side, with its definition. If there is none, the state is `NO_STRUCTURAL_LEVEL`. No level is invented (D01 stands).
2. **`reachable_level`:** spot × (1 ± k·σ·√(t_q80 / 252)), where t_q80 is the evidence time from §4, not 20. k = `contract_economics.sigma_multiple` (1.5, governed). If t is UNESTIMATED, the level is stated UNESTIMATED, or the D-A fallback is used and labelled.
3. **`anticipated_level`:**
   - Default (decision D-D): the nearer of the two. A structural level beyond volatility reach is not assumed.
   - Basis is labelled STRUCTURAL, VOLATILITY_CAPPED or VOLATILITY_ONLY.
   - Output: `anticipated_move_pct` (signed, in the trade direction).
4. **`p_outcome_by_limit`:** the candidate group's `Duration_P_Event_At_Limit` (probability the outcome is reached before invalidation). It is shown with its n and status IN_SAMPLE_REPLAY_NOT_VALIDATED; it is never filled when the group is INSUFFICIENT_SAMPLE.

## 4. Time: how long (decision D-A)

**Source:** the primary candidate's duration evidence (OUTCOME test for ACTIVATED candidates, ACTIVATION for DETECTED).
- `expected_sessions_q50` and `expected_sessions_q80`: remaining bars converted to sessions (1d ×1, 1w ×5, 1mo ×21; the factors are versioned config).
- `hold_basis` = DURATION_EVIDENCE:<group>.

**Planned hold and runway:**
- `planned_hold_sessions` = q50 (when the move is typically complete).
- The contract runway floor uses q80 plus the existing exit buffer, following "buy more DTE than the anticipated move" and the 18 Sep runway decision (the floor is never a ceiling).

**When evidence is thin** (group INSUFFICIENT_SAMPLE, 230 of 439 groups today), choose one (D-A):
- **(a) Recommended.** `planned_hold_sessions` = UNESTIMATED. The runway falls back to the governed window `outcome.window_sessions`, labelled GOVERNED_WINDOW_NO_DURATION_EVIDENCE. The card says so.
- **(b)** UNESTIMATED everywhere. No runway floor; contract selection shows "runway not evidenced".

**Downstream:** all consumers of the hold read these fields:
- theta drag (C3), time value at exit;
- Morning runway, the time stop (C5), `exit_theta_date` / `exit_max_dte` (C2).

The contract's DTE comes only from the selected contract.

**Evidence refresh:** rebuild `beh001_duration_evidence_v1.json` on the refreshed panels (eval_v4), and check q50/q80 calibration on the holdout panel (eval_v4_holdout) before the numbers are shown as anything other than IN_SAMPLE.

## 5. Path and payoff: does the move pay the option?

**Path:**
- `p_invalidation_by_limit` = `Duration_P_Invalidation_At_Limit`: how often the structure failed first.
- A later extension adds adverse-excursion quantiles to the same evidence builder (`beh001_duration_evidence.py`), so DTE and delta can be sized for the path. That needs its own evidence run; it is v1.1, not v1.

**Payoff, from the existing time-value model, at the anticipated level and time q50 (IV held at the contract IV):**
- `move_value_per_share` and `move_value_multiple` = value ÷ entry ask.
- `breakeven_move_pct` (from the ask) and `move_coverage` = anticipated_move_pct ÷ breakeven_move_pct. 1.0 means the anticipated move exactly reaches breakeven.

**Stress (shown, not scored):**
- value at q80 instead of q50 (slower path);
- if earnings fall before q80, value with IV reduced by the contract's own earnings premium (term-structure step), labelled.

**Invalidation:** shown on the card as the **thesis exit** (`invalidation_price`). It is never used in magnitude, payoff, score or rank.

**Decision D-B:** the "Negative premium RR" FATAL block is replaced. Choose one:
- **(a) Recommended.** A labelled flag, `MOVE_DOES_NOT_CLEAR_BREAKEVEN`, when `move_coverage` < 1. The row stays in the book, ranks lower, and Morning cannot GO on it. It is understood, not hidden.
- **(b)** A hard block, as today but on the new measure.

## 6. Ranking (decision D-C)

R:R points leave every score:
- EOD SCS (`eod_candidate_engine.py:1834, 1948` and the R:R band);
- SuperBrain's R:R gate;
- the options research score (`breakeven_score`, G1).

**D-C (a), recommended:** replace them, at the **same weight**, with a `move_coverage` component (banded, versioned config). Add a time-fit component: the contract's DTE ≥ q80 + buffer. The weights do not move until the outcome scorer shows the component ranks outcomes at least as well as R:R did on the replay (step 7). If it does not, it stays display-only. R:R stays in the audit tier labelled LEGACY_STOP_BASED.

## 7. Validation before acceptance (gates G1–G4, spec §24)

1. **Replay** (eval_v4 original panel, then the **holdout**): for each candidate, compute the anticipated level, q50/q80 and coverage at the cut. Score with C12:
   - is the anticipated level reached within q80 at the claimed rate?
   - does higher coverage rank first-touch outcomes better than stop-based R:R? Same-date drift reference, date-block bootstrap, criteria fixed before results.
2. **Characterise the 1 Oct book:** how many rows change state or rank, and why.
3. **Forward sessions:** the outcome scorer tracks the GO rows by coverage band.

## 8. Card (sections 3 and 4)

- **Where right:** anticipated level, basis, distance %, `p_outcome_by_limit` (n, status).
- **Where wrong:** invalidation (thesis exit).
- **How long:** q50 / q80 sessions, basis; contract DTE against q80.
- **Earnings:** date, before q50 / q80 / expiry, timing (before/after market).
- **Does it pay:** coverage, value multiple at q50; stress at q80 and after earnings.
- R:R appears only in the audit tier.

## 9. Build order (each test-first, one defect at a time)

1. Earnings disclosure (MarketData → enricher → card). Independent and small.
2. `anticipated_move_fields` with magnitude, time and payoff, display-only, plus the card.
3. Rebuild the duration evidence on eval_v4 and run the holdout calibration (§4).
4. Switch the consumers of the hold and DTE (theta, runway, time stop, exit plan, Morning runway).
5. Replace the "Negative premium RR" block (D-B).
6. Replay validation (§7); then the ranking switch (D-C) only if it passes.

## Decisions for ACK

| Ref | Decision | Recommendation |
|---|---|---|
| D-A | Hold source; fallback when duration evidence is thin | Duration evidence q50/q80; when thin, hold UNESTIMATED and runway on the governed window, labelled (a) |
| D-B | "Negative premium RR" FATAL block | A labelled flag when the move does not clear breakeven; no Morning GO on it (a) |
| D-C | Ranking | Replace R:R points with move coverage at the same weight, only after the replay shows it ranks outcomes at least as well (a) |
| D-D | Structural level beyond volatility reach | Use the nearer (volatility-capped), labelled |

**ACK decision (3 Oct 2026): "approved as recommended, start with earnings disclosure".** D-A (a), D-B (a), D-C (a) and D-D are approved as recommended. The build starts with §9 step 1.

## Build receipt: §9 step 1, earnings disclosure (3 Oct 2026)

**Change** (uncommitted):
- **New `canonical_data/marketdata_earnings.py`:** `parse_marketdata_earnings` and `fetch_marketdata_earnings`.
  - MarketData `/v1/stocks/earnings/`, 120-day lookahead, injectable transport.
  - Per-session cache at `data/cache/marketdata_earnings/<session>.json`; UNKNOWN is not cached, so it is retried.
  - The key is read from the environment and never logged.
- **`earnings_calendar_enricher.py`** (repaired, not replaced):
  - `EARNINGS_DISCLOSURE_FIELDS` and `earnings_disclosure()`, which give the state, date, report time, XNYS sessions to the price-impact session, inside hold and inside expiry, and a plain-text disclosure.
  - Authority DISCLOSURE_ONLY.
  - The header records that the Polygon snapshot carries no earnings field.
- **`intelligent_orchestrator.patch_earnings_fields_into_csv`:** called after the options-CSV horizon patch (the hold is known by then). Failures are stated as UNKNOWN; the step never stops the run.
- **Carried by name** through `eod_candidate_engine.py` into the Lab book (`FINAL_BOOK_FIELDS`, book row).
- **Morning (`morning_gate.py`):** recomputes the timing from the stored date against the Morning session; no second fetch; the verdict is unaffected.
- **Card, section 4:** an "Earnings" row. "earnings not checked in this run" for older books.

**Tests:**
- New `tests/test_avs_earnings_disclosure.py` (9) and a card test. Seen red (no module; Morning overwrote the date), then green.
- The golden book test's allowlist gained the 11 fields.
- 26 related files pass.

**Acceptance against reality:** a live read-only fetch for 14 tickers, compared with Tastytrade's confirmed dates. **14 of 14 agree.**
- SOFI 27 Oct before the open: 17 sessions away, inside the 20-session hold, before the 18 Dec expiry.
- XLF (an ETF): NONE_IN_LOOKAHEAD.

**Cost:** one MarketData call per ticker per Evening run (about 1,670), cached for the session.

## Build receipt: §9 step 2, anticipated move, display only (3 Oct 2026, ACK "yes, go ahead with step 2")

**One deviation from §2, stated:** Discovery's thesis evidence does not reach the options-intelligence CSV (verified on run 20261001_211641). The owner is therefore a pure module, `domain/anticipated_move.py` (`anticipated_move_fields`, `ANTICIPATED_MOVE_FIELDS`). The EOD candidate engine, the first stage holding both the evidence and the selected contract, calls it now; options intelligence can call it in step 4. It is still one owner, and it reuses the governed volatility (`target_reachable_vol_annual` from `reachable_target_fields`) and `_black_scholes_value`.

**Change** (uncommitted):
- **`domain/structure_behaviour/thesis_category.py`:** `EVIDENCE_FIELDS` carries the trade-side event's Outcome_Level/definition and duration evidence (test, status, n, q50/q80 bars, P(outcome), P(invalidation)). Published only for an event on the trade's side.
- **`config/governed_constants_v1.json` → `anticipated_move`:** sessions per bar (1d 1, 1w 5, 1mo 21, intraday on 6.5 h) and calendar days per session (365/252).
- **`eod_candidate_engine.py`:** merges the evidence and the volatility, computes the fields per candidate.
- **`contracts/lab_control.py`:** the book carries both field sets.
- **Card:**
  - Section 3: "Thesis exit (invalidation)", "Anticipated level" (basis, %, replay evidence), "Structural level".
  - Section 4: "Time fit", "Anticipated time" (median / 80%), "Planned hold" (governed window, runway floor).
  - Section 5: "Does the move pay" (coverage against the breakeven move, value × premium at the median time, stress).
  - R:R and the 3R target are off the card: a new audit class, "Legacy stop-based R:R and 3R targets (retired, not used)".

**Two rules added from the real-data characterisation, each test-first:**
1. **No behavioural event on the trade's side → `NO_TRADE_SIDE_EVENT`, nothing computed.** Symmetric volatility reach is not a directional expectation. Before this rule, INTC, NET and TWLO showed 25–31% "anticipated" moves.
2. **Time fit:** `CONTRACT_OUTLASTS_Q80` / `CONTRACT_EXPIRES_BEFORE_Q80` / `CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME`. No value is computed at a time the contract does not live to (TW: q50/q80 115/180 sessions).

**Tests:**
- New `tests/test_avs_anticipated_move.py` (13) and 4 card tests; domain and card tests seen red, then green.
- The propagation test was written after the wiring and was not seen red.
- 55 related files pass, including the golden book test with the new fields allowlisted.

**Characterisation on real data** (`Enhancements/direction_evidence/anticipated_move_characterise.py`; output in `Enhancements/outcomes/anticipated_move/characterise_go_20261001_211641.txt`): 25 Morning GO tickers, BEH-001 on canonical bars to 1 Oct, Morning quotes, MarketData earnings.
- **14 of 25 have NO_TRADE_SIDE_EVENT** (13 with an opposing event). Under the legacy direction source, more than half of these GO trades ran against the structure. BEH-001 sets the side from the next run.
- **Of the 11 with a trade-side event:** basis 10 VOLATILITY_CAPPED, 1 STRUCTURAL. Time fit 7 outlast q80, 3 expire before q80, 1 before the median.
- **SOFI:** event "Seller Absorption Breakdown (detected, 1d)", level 15.21 (structural, −4.4%), q50/q80 2/5 sessions, reached first in 61% of 1,481 replay cases. Coverage 0.49 of the breakeven move, yet value 1.25× premium at the median time. The old 3R target was 4.875.

**Open for ACK before step 5 (D-B):** coverage (expiry breakeven) and value multiple (exit before expiry) can disagree, as for SOFI. For contracts sold into the herd before expiry, the value multiple at the anticipated time may be the right "does it pay" test. The D-B flag currently uses coverage < 1.

**ACK decision (3 Oct 2026), amending D-B: "use value multiple for D-B".** The flag tests the contract's value at the anticipated (median) time: `MOVE_DOES_NOT_PAY_AT_ANTICIPATED_TIME` when `anticipated_value_multiple_q50` < 1.0. Coverage of the expiry breakeven stays on the card as information. Step 3 approved.

## Build receipt: §9 step 3, duration evidence rebuilt and holdout-calibrated (3 Oct 2026, ACK "go ahead with step 3")

**Build:**
- `beh001_duration_evidence.py` gained `--offset` (holdout panel) and `--records` (per-candidate outcomes).
- Evidence rebuilt on the refreshed original panel (eval_v4; bars to 2026-10-01): 439 groups, 209 published.
- Holdout panel scored separately: 66,269 candidate records.

**Calibration** (`beh001_duration_calibration.py`, criteria fixed before results; report `Enhancements/outcomes/beh001/eval_v4_holdout/duration_calibration.json`). 65,470 holdout records matched a published group, as production would choose it.

| Check | Criterion | Holdout | Result |
|---|---|---|---|
| Events by q50 | 40–60% | 59.2% (n=34,074) | Pass (slightly conservative) |
| Events by q80 | 70–90% | 83.2% | Pass |
| P(event before invalidation), bands with n ≥ 200 | within 5 points | six bands within 3.1; top band 0.845 predicted vs 0.791 observed | **Fail** (top band overstated by 5.4 points) |

- Timing holds by test (ACTIVATION 59.8/83.2; OUTCOME 56.3/83.1) and by timeframe. 1mo q50 is 63.2%, slightly conservative.
- It holds by period: before 2024-09-01, 57.3/81.9; from then, 60.4/84.0.

**Published:**
- `config/beh001_duration_evidence_v2.json` carries a `holdout_calibration` block: timing_state HOLDOUT_PASS; probability_state HOLDOUT_FAIL_TOP_BAND_OVERSTATED, with the bands.
- `config/beh001_behaviour_v1.json` → `duration.evidence_path` now points at v2. v1 is kept.
- Probabilities stay labelled in-sample on the card.

**Tests:** new `tests/test_avs_duration_evidence_v2.py` (2); seen red, then green. 27 BEH-001, duration and anticipated-move files pass.

**Causality check:** v2's data_end is 2026-10-01, so it is (correctly) not used for candidates as of 1 Oct. A re-run on 1 Oct bars shows every timing as UNESTIMATED, which is the causality guard working. The next Evening (session 2026-10-02) is causal; the earlier 1 Oct characterisation used v1.

## Build receipt: §9 step 4a, time to the level measured from detection (3 Oct 2026)

**Finding:** most trade-side events are DETECTED. 22 of 46 detected event types never become ACTIVATED themselves (they hand over to successor candidates), so no "outcome after activation" exists for them. The anticipated move had been using **activation** evidence as if it were reaching the level. SOFI's card "61% of 1,481" was P(activation before invalidation).

**Change** (uncommitted):
- **Builder:** a third test, `OUTCOME_FROM_DETECTION`. DETECTED candidates with an Outcome_Level are timed from detection to that level, before invalidation, under C12 passage rules.
- **Evidence v3** (`config/beh001_duration_evidence_v3.json`; v1 and v2 kept): 688 groups, 365 published; 50 published groups for the new test. The policy points at v3.
- **`domain/structure_behaviour/duration.py`:** `LEVEL_FIELDS` / `_attach_level`. The level timing comes from OUTCOME_FROM_DETECTION for DETECTED candidates and OUTCOME for ACTIVATED ones. Activation timing is unchanged and kept separate. No level evidence → NO_COMPARABLE_EVIDENCE, never activation.
- **`thesis_category.py`:** `thesis_duration_*` and `thesis_p_outcome_by_limit` read the level timing; `thesis_activation_*` is published separately.
- **Card:** "Anticipated time" is "to the level", with an activation line for DETECTED events.

**Holdout calibration** (same fixed criteria; report `Enhancements/outcomes/beh001/eval_v5_holdout/duration_calibration.json`):
- Timing passes: pooled 58.4% by q50 and 83.3% by q80. OUTCOME_FROM_DETECTION 57.1% / 83.5% (n=19,442 events).
- Probability fails above 0.5: level from detection, the 0.6 band predicted 0.64 vs observed 0.56. Stated as HOLDOUT_FAIL_UPPER_BANDS_OVERSTATED; probabilities stay labelled in-sample.

**SOFI corrected:** a Seller Absorption Breakdown (1d, campaign, bear) reached its level before failing in **38%** of 2,067 replay cases, median **8 sessions**, 80% within 20. The earlier 61% (2/5 bars) is activation.

**Tests:**
- New `tests/test_avs_duration_level_timing.py` (4) and a card test; seen red, then green.
- The v2 evidence test was restated for v3, and the propagation fixture updated to level fields (noted).
- 29 related files pass.

## Build receipt: §9 step 4b, evidence runway for daily events (3 Oct 2026, ACK option B)

**ACK decision:** B. Daily trade-side events with level evidence size the contract runway from q80. Weekly and monthly events, and events without evidence, keep the governed window, labelled. The card's time fit states when the contract expires before q80.

**Correction recorded:** options intelligence does read Discovery (it merges the Discovery CSV with Vanguard at load), so the thesis evidence is in its input rows. My earlier statement that it was not was based on the OI output CSV.

**Change** (uncommitted):
- **`domain/anticipated_move.evidence_runway`:** q80 runway (1d only), q50 move time (any timeframe), basis `DURATION_EVIDENCE_Q80:1d:n=…` or `GOVERNED_WINDOW_{NO_TRADE_SIDE_EVENT | NO_LEVEL_EVIDENCE | NON_DAILY_EVENT:tf}`.
- **`calculate_dte_requirement(evidence_hold=True)`:** accepts a positive whole-session evidence hold. Unrouted, unevidenced holds are still refused.
- **Options intelligence:**
  - `contract_runway_policy(..., evidence_hold, evidence_basis)`; selection uses the evidence runway.
  - The OI lifecycle consumes the same hold (`hold_is_evidence`).
  - Output rows carry `contract_runway_hold_sessions` and `evidence_runway_sessions` / `evidence_move_sessions` / `evidence_runway_basis`.
- **Orchestrator hold patch:**
  - Keeps the evidence runway as `planned_hold_sessions` (source = the evidence basis) and the q50 as `anticipated_move_sessions` (DURATION_EVIDENCE_Q50).
  - Other rows keep the governed window, with the reason appended to the source.
  - Writes `ev3_planned_hold_sessions` = governed window.
- **EV3** (`ev3_stage0`, `run_ev3_shadow_phase`): reads `ev3_planned_hold_sessions` first, so it keeps valuing at the 20-session hold (ACK 28 Sep; the barrier cache holds 5/10/20). The EOD engine carries the field to the Morning.
- **Morning lifecycle and Lab re-selection check:** accept an evidence hold when `planned_hold_source` is DURATION_EVIDENCE.

**Tests:**
- New `tests/test_avs_4b_evidence_runway.py` (13). Helper, policy, patch and lifecycle tests were seen red; the EV3 alias, EV3-window patch and EOD carry tests were written with or after the code.
- `test_contract_selection_horizon_not_a_gate.py`: 2 assertions now check the governed prefix (the basis states why no evidence runway applied).
- 33 related files pass.

**Characterisation** (replay, last 3 months; `Enhancements/outcomes/anticipated_move/runway_4b_characterisation.txt`):
- Governed runway floor today: 40 calendar days for every row.
- Daily evidence rows (n=1,935): median 49 days (IQR 37–84, max 227); 31% shorter, 10% same, 60% longer than today.
- Weekly, monthly and unevidenced rows: unchanged at 40, labelled.

## Build receipt: §9 step 4c, decay over the evidence hold, in calendar days (3 Oct 2026)

**Defect (inventory C3):** `ctx['hold_days']` was Vanguard's actuarial recommended hold, else the DTE window midpoint (28 calendar days) or 5. It was used as sessions in ATR·√hold and as calendar days against a per-calendar-day theta.

**Change** (uncommitted, `scripts/avshunter_options_intelligence.py`):
- `decay_hold_sessions()`: the evidence median move time (DURATION_EVIDENCE_Q50), else the governed window (GOVERNED_WINDOW_NO_EVIDENCE). `ctx['hold_days_basis']` is published.
- `theta_drag_pct()`: theta per calendar day × hold sessions × 365/252 (governed `calendar_days_per_session`), as % of premium. Used by contract scoring (theta drain) and by the economics theta drag.

**Tests:** new `tests/test_avs_4c_decay_hold.py` (3), seen red then green. 55 options-intelligence test files pass.

**Effect, SOFI Dec-18 16P:**
- Before: 11.4% (20 sessions charged as 20 calendar days).
- With evidence (q50 8 sessions): about 6.8%.
- Without evidence (governed 20 sessions = 29 calendar days): about 17%. Decay figures for unevidenced rows rise by about 45% from the unit correction alone.

## Build receipt: §9 step 4d, time stop and exits on the selected contract and the anticipated move (3 Oct 2026)

**Defects (inventory A2, C2, C5):**
- The time stop was computed from the input row before contract selection (ts_dte_used 30/45; expiry = today + row DTE; 140 of 144 GO rows mismatched the contract), and its rule quoted the 3R target.
- Exit rules read `dte` before the contract and ran the theta exit past expiry (SOFI 19 Dec vs 18 Dec); their target was `structural_target`.
- The EOD exit plan invented a target from the expected move, set the wall equal to the target, added a +3% T3, and took a direction-blind wall (a CALL could get the put wall below spot).

**Change** (uncommitted):
- **`compute_time_stop_oi(row, contract=, evidence_move_sessions=, evidence_runway_sessions=, anticipated_level=)`:**
  - The selected contract's real expiry.
  - Daily evidence: checkpoint q50, stop q80, never later than expiry minus the exit buffer (DURATION_EVIDENCE_Q50_Q80).
  - Otherwise the governed 30%/60% of the real contract life (GOVERNED_FRACTION_OF_CONTRACT_LIFE).
  - The rule names the anticipated level when known, never 3R. `ts_time_stop_basis` is published.
- **`exit_rules_engine`:** target = `anticipated_level`; DTE from the contract expiry; theta exit ≤ expiry; stop = invalidation (thesis exit).
- **`eod_candidate_engine.anticipated_exit_plan`:**
  - T2 = anticipated level; T1 = a trade-side wall between entry and T2, else T2.
  - T3 = the structural level only beyond a volatility-capped anticipated level; nothing is invented.
  - Applied after the anticipated move, replacing the earlier plan's fields.

**Tests:**
- New `tests/test_avs_4d_time_stop_and_exits.py` (7); seen red, then green.
- 28 related files pass.
- **Open (step 5):** the exit-rules "RR_BELOW_1.5_REVIEW" label and `exit_rr_valid` are stop-based R:R. They are replaced with the D-B value-multiple flag in step 5.

## Build receipt: §9 step 4e, Morning runway toward the anticipated level (3 Oct 2026)

**Change** (uncommitted, `morning_gate._morning_liquidity_lifecycle`): the runway target is `anticipated_level` when present (basis ANTICIPATED_LEVEL). Otherwise the D01 chain applies: structural target (STRUCTURAL), else volatility-reachable (REACHABLE), else MISSING. Nothing is invented.

**Tests:** new `tests/test_avs_4e_morning_runway.py` (2); seen red (basis STRUCTURAL), then green. A full-suite regression was started after 4a–4e.

## Full-suite regression after step 4 (3 Oct 2026)

392 test files, one per process: 388 pass. The four failures are not step-4 logic:
- `test_vanguard_reference_input_p2` (3) and `test_canonical_manifest_p1` (1): the parked DCV staleness clock (package bars from 2026-09-25 judged against the wall clock).
- `test_avs_fix_002_stage0` and `test_avs_int001_stage0`: "production imports must be tracked in git". The new modules (this session's, and earlier untracked ones such as `canonical_data/forecast_path_reader.py` and `contracts/descriptive_forecast_packet.py`) are uncommitted; this clears on ACK's commit.

## Build receipt: §9 step 5, "does the move pay" replaces stop-based R:R blocks (3 Oct 2026, ACK D-B amended)

**Change** (uncommitted):
- **Monetisation policy (both copies):** OPT_014 "Negative premium RR" is no longer FATAL. It is an INFO note ("Stop-based premium R:R retired (not a gate); see the anticipated move"). The stale comment is corrected.
- **`domain/anticipated_move`:** `anticipated_pays_state` = PAYS (value at the median anticipated time ≥ 1.0× premium) / DOES_NOT_PAY_AT_ANTICIPATED_TIME (< 1.0×) / NOT_COMPUTED.
- **Morning (`morning_gate.py`):** DOES_NOT_PAY_AT_ANTICIPATED_TIME → FLAG, permission MOVE_DOES_NOT_PAY, NO_TRADE, with the multiple stated; the row stays in the book. NOT_COMPUTED does not block on its own.
- **Exit rules:** "RR_BELOW_1.5_REVIEW" is removed; `exit_rr_valid` = None (legacy); `exit_move_pays` is added; MOVE_DOES_NOT_PAY_REVIEW goes in the summary.
- **Card:** "Does the move pay" states pays / does not pay (no GO) at the anticipated time.

**Tests:**
- New `tests/test_avs_step5_move_pays.py` (4). The policy test was first red for a fixture reason (premium field and units). After correcting it, the committed policy blocks the fixture ("Negative premium RR") and the new one does not. The other three were seen red for the business reason.
- Card test written with the change (not seen red).
- `test_cycle2_governance.py`: `exit_rr_valid` is now None (noted).
- 36 related files pass.

**Acceptance (replay of the policy on the 1,554 execution rows of run 20261001_211641):** 24 rows lose the "Negative premium RR" block; no other block reason changes. Production recorded 372 such blocks in that run (its mid-runner rows carry enrichment the final file does not). Either way, the block no longer exists.

## Result: §9 step 6, replay validation for D-C (3 Oct 2026)

**Method:** `Enhancements/direction_evidence/anticipated_move_ranking_validation.py`, criteria fixed before results.
- Holdout panel, 67,584 candidates with a trade-side structural level and published level evidence (v3, built on the other panel), 96 cuts.
- Rank correlation (per cut, averaged) of each measure with the signed 20-session return (R20) and with 2-ATR first touch net of same-date drift (HIT2X).
- Date-block bootstrap.
- PASS = new − old ≥ 0 with a 95% lower bound above −0.01.

| Measure | IC vs R20 | IC vs HIT2X |
|---|---|---|
| OLD_RR (stop-based R:R to the structural level) | 0.0149 | 0.0162 |
| NEW_MOVE (anticipated move %) | 0.0146 (−0.0004 [−0.018, +0.017]) **fail** | 0.0065 (−0.0097 [−0.025, +0.006]) **fail** |
| NEW_COVER (move ÷ ATM breakeven proxy) | 0.0102 (−0.0048 [−0.019, +0.011]) **fail** | 0.0057 (−0.0106 [−0.022, +0.001]) **fail** |

- Exploratory, post hoc (daily events only, n=29,385): same picture. ICs 0.001–0.017; no new measure beats R:R.
- Reports: `Enhancements/outcomes/anticipated_move/ranking_validation_holdout*.json`.

**Reading:** none of the three measures ranks outcomes. R:R, the anticipated move and coverage all have ICs near zero. Under D-C (a), coverage earns **no ranking weight** and stays display-only (with the D-B Morning flag). Magnitude/geometry measures do not carry the edge on the underlying, consistent with the 28 Sep ticker-edge study.

**Decision for ACK:** remove R:R points from scoring without a replacement, or keep them until a measure with ranking power exists. Recommendation: remove them (ACK 3 Oct: "R:R should be removed"; the replay shows they carry no ranking information either). The freed weight is not reassigned. The change is measured forward with the outcome scorer.

## Build receipt: R:R removed from every score and gate (3 Oct 2026, ACK "remove R:R points as recommended")

**Change** (uncommitted):
- **`eod_candidate_engine.py`:**
  - Contract quality: the +10 for R:R ≥ 1 and the BREAKEVEN_OR_RR_CAUTION reason are removed.
  - Monetisation fit: R:R points 0.
  - Shadow opportunity score: the R:R points are removed.
  - SCS (live and legacy): the R:R band scores 0; the breakdown reads "R:R retired … audit only".
- **`scripts/avshunter_superbrain_layer.py`:** hard gates 0b (R:R < 0.5) and 0b2 (R:R < 1.5 cap / EOD warning) are removed; the `rr_gate` label is RETIRED; the retired warning's weight entry is removed.
- **`scripts/avshunter_options_intelligence.py`:** the research route no longer raises ESTIMATED_R_MISSING / ESTIMATED_R_LT_1 (R:R is recorded, never a review flag or a missing-data reason). OIS already gave R:R zero points.
- R:R fields remain in the book, in the audit tier as legacy (repair, don't delete).

**Tests:**
- New `tests/test_avs_rr_removed_from_scoring.py` (6): rows that differ only in R:R score, flag and route identically. Seen red, then green.
- Superseded tests restated with notes: `test_avs_d01_d13_target_reachability` (monetisation fit), `test_avs_d13_rr_underlying_reachable` (both SCS scorers), `test_options_research_contract` (route flag).
- 31 related files pass.

**Acceptance:**
- SCS recomputed old and new on the 1,554 rows of run 20261001_211641: 0 scores changed, rank correlation 1.0, top-50 identical. That book predates the reachable R:R fields, so it already earned no R:R points.
- The removal therefore prevents R:R points from the next run onward. The effect is measured forward with the outcome scorer.

## Production receipt: Evening run 20261003_213716 (reviewed 4 Oct 2026)

- The run completed with no ERROR lines. Anticipated move: 830 ESTIMATED, 16 time-unestimated, 82 no level, 629 non-directional. Pays: 715 PAYS, 93 DOES_NOT_PAY, 749 not computed (non-directional or no quote). Earnings: MarketData for all 1,557 rows; 1,486 scheduled.
- **Defect found:** `anticipated_level_basis` was STRUCTURAL_REACH_UNKNOWN on 846 of 846 rows, so the D-A volatility cap never ran and moves reached +174.8%. Root cause: `process_ticker` in options intelligence published `target_reachable` but not `target_reachable_vol_annual`, so the EOD engine received None. The step-3 test checked the reader, not the producer.
- **Fix (test-first):** the output row now publishes `target_reachable_vol_annual`, `_sigma_multiple` and `_hold_sessions`. New test `tests/test_avs_anticipated_move_vol_wiring.py`: red first, then green. Related tests pass (anticipated_move 13, options_research_contract 11, b1 4).
- **Expected effect** (vol recovered from this run's 20-session reach, cap at q80): 242 of 846 rows become VOLATILITY_CAPPED; the median move goes from 9.86% to 9.22% and the maximum from 174.8% to 72.4%; coverage ≥ 1 goes from 518 to 508. It is measured on the next Evening run.
- **SOFI check:** 16P expiring 18 Dec; move 3.5% against 8.5% breakeven (coverage 0.41); q50 value multiple 1.13 gives PAYS. This is consistent with D-B. All 233 coverage-below-1 PAYS rows have a q50 multiple of at least 1.
