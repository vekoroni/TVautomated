# Discovery and Vanguard: one behavioural stage (design, 12 Oct 2026)

Status: DESIGN FOR ACK APPROVAL. No code until approved. Generic architecture for any ticker and any timeframe.
Supersedes the fix list in `DISCOVERY_VANGUARD_SIGNAL_ASSESSMENT_20261012.md` (DV-1..DV-7 are re-placed below).
Builds on: `DISCOVERY_VANGUARD_REDESIGN_20261007.md` (P1-P9, fact ownership), BEH-001 design
(`AVS_SD_BEH_001_BEHAVIOURAL_SIGNAL_CANDIDATES_20261001.md`), ACK's Soul of the Chart training material, ACK's
trade-quality register. Evidence: `dv_audit_20261010.*`, `vanguard_db_validation.*`, `sofi_acceptance_case.*`.

## 1. Purpose (ACK, 12 Oct 2026)

Discovery and Vanguard infer the struggle between buyers and sellers, map the current phase and event, and emit a
**conditional behavioural signal for downstream interrogation**:
`Bars > Sequences > Behaviour > Control > Phase > Event > Transition > Signal`.

- **Discovery** produces the behavioural reading. Its selection criteria and outputs must be accurate, because
  everything downstream is conditioned on them.
- **Vanguard** is a statistics layer **conditioned on Discovery's reading**: what history shows for a reading like this.
  It is context; it never changes the reading.
- **Every ticker gets an outcome each run; not every ticker gets a signal.** The outcome is a disposition: SIGNAL,
  DEVELOPING (with what must happen next) or NO_SIGNAL (with the reason). A signal may take several runs to develop.
- **No forward claims in this stage.** No targets, outcome levels or times to outcome; the right edge is an unfinished
  decision. Downstream stages interrogate the signal and own any target.

## 2. Architecture

```text
Completed bars (daily store; 5-minute store -> 15m / 60m) -- freshness and completeness per timeframe, as fields
  -> READING per timeframe (BEH-001 engine, the only reader)
       Sequences -> Behaviour -> Control -> Phase -> Event -> Transition
       each claim labelled OBSERVED / INFERRED / UNRESOLVED
  -> NESTING across timeframes (roles, not separate trades)
       campaign (1mo / 1w / 1d) -> swing (60m) -> setup (15m) -> trigger and response (5m)
  -> SIGNAL per ticker: side, governing event, trigger condition, invalidation condition, nesting agreement
       + ENHANCERS (present / absent / not measured) + DATA QUALITY
  -> DISPOSITION per ticker per run: SIGNAL | DEVELOPING(next condition) | NO_SIGNAL(reason)
  -> LIFE CYCLE across runs (candidate ledger): first seen -> developing -> activated / failed / invalidated
  -> VANGUARD: statistics for this reading (keyed on the reading, never on its own labels)
  -> downstream interrogation (Options, anticipated move, Morning, Lab)
```

### 2.1 Reading (per timeframe)

The BEH-001 engine already implements every link (sequences, behaviour, control, phase, events with a
DETECTED / CONFIRMED / FAILED / UNRESOLVED life cycle, transition, signal) on 1mo, 1w, 1d, 60m, 15m and 5m, and stamps
each candidate HYPOTHESIS_NOT_OUTCOME. Changes:

| Change | Why |
|---|---|
| Each published claim (controller, phase, event, transition, compression) carries `*_basis` = OBSERVED / INFERRED / UNRESOLVED and the bars it rests on | The training material separates them; the card must show which statements are facts |
| The legacy classifiers (`WyckoffEngine_3101_v2`, precor, Discovery composite) stop feeding any reading, rank or Vanguard key; kept as `legacy_*` audit | On 10 Oct the legacy mode said ACCUMULATION on 69% of tickers, contradicting the engine ("contraction does not imply accumulation"); item 11 stations 2-5 |
| A timeframe whose bars are stale or incomplete is read but its claims are capped at INFERRED and the gap named (`Data_Status`) | 47% of 10 Oct candidates carry stale / incomplete intraday bars; a trigger read on yesterday's bars is not today's trigger |

### 2.2 Nesting (roles, not separate trades)

| Role | Timeframes | Question |
|---|---|---|
| Campaign | 1mo, 1w, 1d | Who controls the campaign; which phase; what would transfer control |
| Swing | 60m | Is the current swing with or against the campaign; SOW / SOS, LPSY / LPS |
| Setup | 15m | Can recoveries / pullbacks repair the damage; balance, absorption, failed tests |
| Trigger and response | 5m | Contraction, expansion, acceptance or rejection at the setup's level |

Rules:
- The side comes from the campaign and swing; a lower-timeframe reading against them is a **local** event inside the
  campaign ("a local reclaim can occur within an intact decline"), published as such, never a separate side.
- Lower timeframes supply the trigger and response for the higher-timeframe setup. They are not standalone setups that
  need their own hit-rate test (replaces the INTRADAY_ONLY_UNTESTED drop: 134 tickers on 10 Oct).
- When campaign and swing disagree on the same timeframe class (10 Oct: 417 SAME_TIMEFRAME_CONFLICT tickers), the
  disposition is DEVELOPING with both conditions; the side whose trigger has been accepted on the swing / trigger
  timeframes governs (events, not states; DV-1).
- `nesting_agreement` states, per ticker, which roles agree with the side (e.g. CAMPAIGN_SWING_SETUP_AGREE,
  SWING_AGAINST_CAMPAIGN).

### 2.3 Signal content (no forward claims)

| Field | Content |
|---|---|
| side | BULL / BEAR, or both conditional sides |
| governing event | the event (type, timeframe, state, bar) the signal rests on |
| trigger condition | the level and acceptance rule that activates it (engine's acceptance rule) |
| invalidation condition | where the reading is proved wrong |
| reference levels | observed structure (range edges, thrust origin, prior balance), labelled OBSERVED_REFERENCE - not targets |
| nesting agreement | section 2.2 |
| enhancers | section 3 |
| data quality | per timeframe |

Removed from this stage: `Outcome_Level` / `Outcome_Definition` as a target, duration to outcome, OUTCOME_REACHED as
a signal state (it becomes a life-cycle observation: "price reached reference level X"). Downstream dependents and
their proposed owner (ACK to confirm): geometry (item 3), setup odds (item 10: "target before invalidation"),
anticipated move and pays state, contract runway, C12 target-first scoring -> the anticipated move owns any target;
setup odds are restated as development statistics (section 5).

### 2.4 Disposition and life cycle

Every ticker leaves every run with exactly one disposition, recorded in the disposition journal (item 8):
- **SIGNAL**: governing event activated (trigger accepted, not invalidated) with nesting agreement stated;
- **DEVELOPING**: a detected event / structure exists; the next condition is named ("BEAR if accepted below X; BULL
  if accepted above Y");
- **NO_SIGNAL**: with the reason (no event, two-sided campaign, invalidated, data insufficient).

The candidate ledger follows each candidate across runs (first seen, state changed, activated, failed,
invalidated); `runs_in_state` and `runs_to_activation` are recorded so development is measured, not assumed.

## 3. Factors: core versus enhancers

**Core** factors define the reading and the signal: control, phase, event, transition, trigger and invalidation
conditions. Without them there is no signal.

**Enhancers** raise or lower the quality of a signal; their absence never invalidates it (ACK: a trade can still win
without compression). Rules for every enhancer:
1. Computed from completed bars at the signal's own timeframe and role; never invented (missing = NOT_MEASURED).
2. Published as PRESENT / ABSENT / NOT_MEASURED with its value; ABSENT is not negative.
3. Never a gate and never a direction source.
4. Zero weight in any rank until a pre-registered test shows uplift: same setup type and state, with vs without the
   enhancer, development rate and option payoff after costs, against chance, hold-out and halves.

| Enhancer | Definition source | Today |
|---|---|---|
| Compression | engine `compression.py`: state, NR flags, true-range ratio, box, location, contracting side, episode | Computed on every timeframe; also published as its own signal type (`Crabel Compression Breakout`) - becomes an enhancer attached to the governing event, the standalone type kept only where it is the event itself (breakout of a recorded box) |
| Effort vs result / volume | engine `behaviour.py`; relative volume at the event bar | Inside the engine; not published as an enhancer |
| Shortening of thrust (SOT) | engine `SOT_State` | Published per timeframe |
| VWAP position and control (intraday) | from bars (trigger-layer VWAP events) | Events exist; not attached as an enhancer |
| MA5 relation, ADX14, ATR14 regime, ROC(12,6) | ACK's chart read | Not computed in the engine |
| Pre-trigger momentum, distance to trigger | redesign section 9 | Distance built; momentum absent |
| Relative strength vs sector | redesign section 9 | Absent |
| Implied vs forecast volatility (cheap / rich) | Phase 6 (passed V2 / V3) | Options layer; attached downstream, not in this stage |

Evidence gap: the behavioural replay records (`Enhancements/outcomes/beh001/eval_v5`) store ticker, cut, timeframe,
scope, type, direction, test and timing only - no enhancer context. The replay must record each enhancer at the
detection bar before any uplift can be measured.

## 4. Data prerequisites

- **Intraday completeness.** The 5-minute store has gaps (e.g. whole sessions absent, partial sessions); 47% of 10 Oct
  candidates carry STALE_INTRADAY or INCOMPLETE_SESSIONS. Root cause to be traced (capture schedule, registry, backfill)
  before the trigger-and-response role can be trusted. Until fixed, those claims are capped at INFERRED (2.1).
- **Daily store** is canonical (`historical_prices.sqlite`); the actuarial database is built from a separate history
  (fact-ownership register) - aligned before Vanguard is re-keyed.

## 5. Vanguard: statistics conditioned on the reading

**Validated against the database (12 Oct):** inputs agree with the database labeller on 9 of 10 dimensions
(98.8-100%); the Wyckoff bucket is the legacy label (17% disagreement) and compression is wildcarded on 57%; exact
cohorts reproduce from the database. The database's states barely separate 20-day direction (45.6%-55.5%) - because
they are not Discovery's reading.

**Target:** Vanguard's key is Discovery's reading, not its own labels:
`timeframe role | controller | phase | event type | event state | nesting agreement | enhancers present`.
History comes from the behavioural replay panels (the engine run on past cuts - same reader as live), which hold
118,341 dated records in eval_v5 alone. Outputs, all descriptive context with n and the cut:
- how often a reading like this developed into an activated signal, and in how many bars / runs;
- how often it failed or was invalidated first;
- how the following behaviour unfolded (expansion in ATR, retest held or failed) - context, not a target;
- contradiction flags when the history for this reading opposes the side.

The v7 actuarial database stays as market-state context until rebuilt on readings (decision 4); its up / down rate is
not shown as a win probability.

## 6. Acceptance

- **Standing acceptance set:** ACK-labelled cases (Soul of the Chart format: per timeframe, controller, phase, event,
  candidate, observed / inferred / unresolved). The engine's reading is compared claim by claim; each disagreement is
  classified ENGINE_DEFECT, DATA_GAP or TEACHING_POINT. More cases across tickers, sides and phases are needed - the
  first case is one ticker and validates nothing on its own.
- First case (illustration of the defect classes the set must catch, not a design input): side and swing / setup
  reading agree; the daily campaign is read TWO-SIDED range where ACK reads seller-controlled markdown (to classify);
  the 5m read is a DATA_GAP (the store had no bars for the screenshot session); the live run governed from a monthly
  upthrust while the legacy mode said ACCUMULATION.
- **Population checks every run** (Evening scorecard, report only): disposition coverage 100%; no forward claim in
  stage outputs; legacy fields absent from reading / rank / Vanguard key; data-quality caps applied; nesting agreement
  published; Vanguard key = reading.

## 7. Build order (each test-first, replayed, then accepted on ACK's next run)

1. Data: intraday completeness root cause and fix; quality caps (2.1).
2. Reading labels: OBSERVED / INFERRED / UNRESOLVED per claim.
3. Legacy out of the reading, rank and Vanguard key (item 11 stations 2-5).
4. Nesting roles and agreement; replace the intraday-only drop; conflict -> DEVELOPING with both conditions.
5. Signal without forward claims; dispositions SIGNAL / DEVELOPING / NO_SIGNAL; downstream target owner switched
   (after ACK confirms the owner).
6. Enhancers published (PRESENT / ABSENT / NOT_MEASURED), zero weight; replay records extended with enhancer context.
7. Vanguard re-keyed on the reading from the replay panels.
8. Enhancer uplift tests (pre-registered) -> weights only where measured.

## 8. Decisions for ACK

1. Target ownership: this stage emits no targets; the anticipated move owns any target; setup odds become development
   statistics.
2. Nesting roles as in 2.2 (campaign / swing / setup / trigger) and the intraday-only drop replaced.
3. Enhancer rules in section 3 (never a gate, never direction, zero weight until measured).
4. Vanguard keyed on Discovery's reading, sourced from the behavioural replay panels.
5. Build order in section 7, starting with intraday data completeness.

## Step 2 specification: OBSERVED / INFERRED / UNRESOLVED (12 Oct 2026)

Owner: `domain/structure_behaviour/basis.py` (`label_reading`), applied by the engine to every timeframe reading after
its data status is known; Discovery publishes `beh__<tf>_controller_basis`, `_phase_basis`, `_transition_basis`,
`_compression_basis`, `_basis_cap`; candidates carry `Event_Basis`, `Levels_Basis`.

| Claim | OBSERVED | INFERRED | UNRESOLVED |
|---|---|---|---|
| Structure and levels (range, box, thrust origin, trigger, invalidation) | recorded from completed bars | - | - |
| Compression measures (state, NR flags, box, location) | measured | - | - |
| Controller | - | BUYERS / SELLERS (progress and retained ground) | TWO-SIDED, CONTROL SHIFTING |
| Phase | - | MEDIUM / HIGH confidence | LOW confidence or none |
| Transition | - | stated transition or STABLE | none |
| Event (candidate) | ACTIVATED / CONFIRMED / FAILED / outcome level reached - settled by later bars | DETECTED - response not yet decisive | MONITOR - contraction without a direction |
| Right edge (the last bar's outcome) | - | - | always |

Cap: a timeframe whose `Data_Status` is not OK (stale, incomplete, disagrees with daily) carries no OBSERVED claim;
OBSERVED becomes INFERRED and `Basis_Cap` names the reason. Tests: `tests/test_p8_reading_basis_labels.py`.

---

# Part B: entry timing and conditional behaviour (design update, 12 Oct 2026, for ACK approval)

Sources: `AVSHUNTER_Discovery_Entry_Timing_Requirements_v1.docx` (ACK, 12 Oct: R1-R10, N1-N6, AT01-AT12, three state
dimensions, policy registry), the N7-N12 enhancements (ACK, 12 Oct), lessons L1-L8
(`LESSONS_AND_REQUIREMENTS_REGISTER_20261012.md`). Aim: accurate data early enough to get the trade; success is earlier
actionable identification **with measured trading quality** - more GO rows or earlier timestamps alone do not count.
Repository rules preserved: macro / money context display-only (R4 as a separate shadow score until a rule amendment);
Discovery publishes reference levels, never downstream targets (R7); missing is never neutral.

## B1. Three state dimensions (replace the single GO meaning)

| Dimension | States | Owner |
|---|---|---|
| Event status | FORMING, OBSERVED, TESTING, PROVISIONALLY_SUCCESSFUL, CONFIRMED, FAILED, AMBIGUOUS | Discovery (engine events + trigger events) |
| Entry status | PREPARE, WAIT, ACTIONABLE, EXTENDED, EXPIRED, INVALIDATED, BLOCKED_DATA, BLOCKED_CONFLICT, BLOCKED_CONFIG | Discovery entry policy (N3) + availability (N4) |
| Contract status | NOT_ASSESSED, PREPARED, EXECUTABLE, UNAVAILABLE, STALE | Options / Morning |

Final GO = ACTIONABLE entry + EXECUTABLE contract + valid data + an enabled policy. The current `thesis__readiness` /
`trigger_go_eligible` stay, labelled LEGACY_GO, beside the new states during shadow comparison. A later valid retest is a
new `entry_opportunity_id` under the same `thesis_id`; the missed first opportunity stays in the ledger.

## B2. Requirement map (what exists, the gap, the owner, the test)

| ID | Exists today | Gap | Owner module | Acceptance |
|---|---|---|---|---|
| N1 reading with evidence | Engine readings per timeframe; step 2 labels; candidate `Evidence` items already marked OBSERVED / INFERRED | `structure_type`, `directional_bias`, `evidence_strength` (not a probability), `alternative_interpretations` per timeframe; parent / local conflict flag | `domain/structure_behaviour` (engine, basis) | AT05 |
| N2 event life cycle | Candidate ledger (FIRST_SEEN, STATE_CHANGED, LEVELS_REVISED), `Events_JSON` trail, `thesis__last_event_date` | Stable `event_id`; `first_observed_at`, `event_occurred_at`, `confirmed_at`, `failed_at`, `event_version`, evidence bar ids; no later bars used to label an earlier event | engine events + candidate ledger | AT04, AT11 |
| N3 event-specific entry policies | One global readiness (provisional accepted break or held retest) | Versioned policy registry: spring/test probe, strength breakout (first-close and accepted-break as separate policies), support retest, upthrust failure, weakness breakdown, failed retest; inspectable `predicates_passed` / `predicates_failed`; missing parameter -> BLOCKED_CONFIG | new `domain/entry_policy.py` + `config/entry_policies_v1.json`; legacy readiness imported as policy v0 | AT01, AT12 |
| N4 entry availability | Item 3 geometry (reward / risk ATR, measured hit rate) | Frozen trigger / invalidation / ATR at the snapshot; `extension_atr`, `room_to_level`, `structural_risk`, `underlying_reward_risk`, event age, `valid_until`; `entry_status` + reason | `domain/entry_availability.py` (extends `domain/trade_geometry.py`) | AT02, AT03 |
| N5 prepare and monitor | Candidates published each Evening; Morning repairs contracts | PREPARE / WAIT candidates monitored without a full-universe rerun; preliminary option shortlist before the trigger | orchestration (lightweight monitor stage) + Options | N5 acceptance |
| N6 revalidate and attribute delay | Station inspections, quote-age flags | Revalidate before delivery; reason codes DATA_DELAY, DISCOVERY_DELAY, CONFIRMATION_WAIT, MONITORING_GAP, CONTRACT_DELAY, DELIVERY_DELAY, USER_EXECUTION_DELAY | orchestration + measurement | AT06, AT08 |
| R1 signal timeline | `thesis__last_event_date`, run ids | `source_bar_end_at`, `data_received_at`, `setup_first_detected_at`, `event_occurred_at`, `policy_qualified_at`, `contract_prepared_at`, `last_revalidated_at`, `delivered_at`, `trigger_close_date`, `trigger_age_sessions` (exchange calendar) | Discovery + orchestration | AT06, AT11 |
| R2 p_fast | none | Per event family, policy, direction, timeframe; ATR frozen at entry; before-invalidation vs touch-anytime; UNAVAILABLE with reason | Vanguard statistics (step 7) | AT09 |
| R3 opportunity ledger | Decision ledger + trade journal `mining_outcomes` (ACK, 12 Oct); C12 scorer (20-session race); disposition journal | Append-only opportunity cohort (PREPARE to missed / invalidated) keyed `thesis_id`, `event_id`, `entry_opportunity_id`; +1/+3/+5/+10 views; MFE / MAE; ambiguous same-bar ordering flagged; long horizons censored | measurement (`canonical_data` ledger + C12) | AT07, AT12 |
| R4 money context | Macro board per-ETF mapping | `ETF_mapping`, `mapping_weight`, holdings-based sectors; shadow score only | context service | R4 acceptance |
| R5 event calendar | Earnings tiers (item 9) | Economic releases, corporate actions, expiry, holidays, weekend-carry flag; UNKNOWN when stale | reference data | R5 acceptance |
| R6 contract family | One best contract; 883 contracts expire before the median move; none beyond ~67 DTE | Expiry ladder from the nearest weekly to 90 days, 10% ITM to 15% OTM, valued at q50 / q80 and the declared early-exit plan | Options | AT10 |
| R7 reference levels | `Outcome_Level` (to be relabelled), structure levels | `level_id`, `level_type`, formation time, evidence; next-leg levels as candidate references | Discovery (Part A step 5) | R7 acceptance |
| R8 entry policy comparison | Readiness test (12 Oct, under amendment) | Policy-level comparison on one shared cohort incl. no-entry paths, net of costs - published as context for mining, not a pipeline verdict | Vanguard + measurement | R8 acceptance |
| R9 clusters | none | `cluster_id`, correlation measure, window, version | Vanguard | R9 acceptance |
| R10 timing calibration | Item 10.2 forward calibration; duration q50 / q80 | Named outcome and time origin; q80 unresolved when fewer than 80% reach it | Vanguard + measurement | AT09 |
| N7 conditional expectations | Candidate `Expected_Behaviour`, `Next_Anticipated_Logic`, invalidation text | Structured `expected_behaviour`, `supporting_conditions`, `weakening_conditions`, `invalidation_conditions`, `alternative_scenarios`, `evaluation_window` (suited to the timeframe), `expectation_version`; a failed expectation is acknowledged, not repeated | engine signals + basis | N7 acceptance |
| N8 attempt vs achievement | `behaviour.effort_result`, control quality, SOT | `attempt_direction`, `attempt_result` (progressing / stalled / rejected / unresolved), `control_change`; explains entry quality without adding a confirmation delay | engine behaviour / control | N8 acceptance |
| N9 event relationships | `Events_JSON` sequence (e.g. BREAK_ATTEMPT -> FAILED_BREAK -> VWAP_LOSS) | Typed links: confirms, contradicts, tests, fails, supersedes, with timestamps and evidence; "bullish attempt failed" distinct from "bearish control established" | engine events | N9 acceptance |
| N10 revision | Lifecycle states, readiness closures | WEAKENED / OBSOLETE / INVALIDATED distinguished; what changed and its effect on the permitted action; stale data gives uncertainty, never a side change | Discovery thesis step | N10 acceptance |
| N11 historical analogues | Replay panels | Deferred until N7-N10 work (ACK) | Vanguard | - |
| N12 expectation errors | R3 ledger | Failure cause: interpretation, timing, late recognition, over-restrictive rule, unsuitable option, exit; UNKNOWN when not established; simulated and actual kept apart | measurement | - |

## B3. Validation controls (every comparison from now on)

The four invariants of `AVSHUNTER_Readiness_Manipulation_Controls.py` are hard assertions in every replay harness:
a frozen eligible cohort (no-entry and exclusions recorded), point-in-time eligibility, unique episode ids with
idempotent ingestion, and immutable outcomes from feasible fills (no fill before the signal is available). Synthetic
positive controls prove the audit catches each rig; they never enter a performance report.

## B4. Revised build order (supersedes Part A section 7 from step 3 on)

1. Readiness test re-run under the amended pre-registration (policy evidence before any switch).
2. R1 timeline fields and N2 event ids / clocks (Discovery), then the R3 opportunity cohort keyed on them.
3. N3 policy registry with the legacy readiness as policy v0, N4 entry availability, B1 three states - shadow only,
   legacy GO unchanged and labelled.
4. N7-N10 conditional expectations, attempt / achievement, event links, revision.
5. Part A steps 3-5 (legacy out, nesting, signal without forward claims).
6. Vanguard statistics keyed on the reading: R2, R8, R9, R10 (Part A step 7), then N11.
7. A policy changes what the pipeline labels only when it is shown to label the event accurately and earlier
   (acceptance tests, versioned configuration). Outcome rates against a matched control (R8) are published as Vanguard
   context for mining, never as a pass / fail on the pipeline.

**Scope (ACK, 12 Oct 2026):** the pipeline does not look for edge - that is the job of mining. Discovery / Vanguard
identify accurate, timely, labelled data that mining can use (the reading, the event and its status, its clocks, and
statistical context). Pipeline tests are judged on accuracy and timeliness of that data; outcome statistics are context
fields, not verdicts. This supersedes the "edge" wording in Amendment 1 decision 2 and in the first B4.1 note.

### B4.1 result (12 Oct 2026): readiness re-run under Amendment 1 - DONE

Receipt: Enhancements/phase8/readiness_policy_rerun.json (both panels; no cross-panel overlap; all four synthetic
manipulations rejected by the audit in both panels, so the harness is trustworthy).

What it tells the pipeline about its data:

- **Timing.** The daily trigger event is observable at the first close beyond the trigger. The live readiness label
  (P3) arrives a median 1 session later and covers ~10 points fewer episodes (52% vs 62%); the engine's full acceptance
  (P4) arrives 3 sessions later and covers ~20 points fewer (43%). The earlier observation is not distinguishable in
  outcome: non-inferior in the hold-out, narrowly short in the original panel on return (lower bound -0.078 ATR vs
  -0.05). So the legacy readiness label stays as policy v0, and the event itself should be published at the first close
  with its status developing (OBSERVED -> PROVISIONALLY_SUCCESSFUL -> CONFIRMED / FAILED) - this is B1 event status and
  the R1 / N2 clocks (B4.2-B4.3), so mining sees it 1-3 sessions earlier without the pipeline deciding the trade.
- **Context for mining (Vanguard fields, labelled by event family):** after a daily trigger crossing, +1 ATR before -1
  ATR ~47% (P0-P4), +1 ATR within 3 sessions ~35%, against ~49.6% for the same tickers and side on any day. Setup types
  are close to that base rate (Spring Candidate ~50%). These are base rates for mining to weigh with its own reading
  and the money context, not a verdict on Discovery.

Next: B4.2.

### B4.2 result (12 Oct 2026): event ids, status and clocks (R1 / N2 / B1 event status) - DONE

Built test-first (`tests/test_p8_event_clocks.py`, 13 tests). Owner: `contracts/thesis_record.event_timeline` (beside
the readiness owner); Discovery attaches it to every candidate in `_attach_trigger_events` and publishes the governing
thesis's values on the ticker row (`_event_clock_fields`, `_fill_first_detection` after the candidate ledger). The new
`thesis__*` fields are in `THESIS_SPINE_FIELDS`, so they travel Discovery -> EOD -> Morning -> Lab unchanged. Legacy
readiness (policy v0), GO and ranking are unchanged.

| Field | Meaning |
|---|---|
| `thesis__event_id` | stable per thesis + side + trigger level (survives FORMING -> CONFIRMED) |
| `thesis__event_status` | FORMING / OBSERVED (first close beyond) / PROVISIONALLY_SUCCESSFUL / CONFIRMED / FAILED; NOT_MEASURED, NO_DIRECTED_TRIGGER, NO_GOVERNING_THESIS (never neutral) |
| `thesis__entry_opportunity_id` | one per crossing of the trigger |
| `thesis__trigger_close_date`, `thesis__trigger_age_sessions` | first close beyond the trigger; completed sessions since |
| `thesis__event_occurred_at`, `_confirmed_at`, `_failed_at` | from closed bars only |
| `thesis__policy_qualified_at` | legacy readiness (v0) date, only once met |
| `thesis__source_bar_end_at` | 16:00 New York close of the last daily bar, UTC |
| `thesis__discovery_read_at` | when Discovery read the bars (UTC) |
| `thesis__setup_first_detected_at` / `_run` | the governing setup's first detection, from the candidate ledger |

Acceptance (read-only replay, 300 tickers + SOFI through 2026-10-09; `event_clocks_replay.json`): the first close
beyond the trigger, recomputed independently from the raw daily closes, agrees on 432 / 432 directed daily theses;
every legacy READY row is PROVISIONALLY_SUCCESSFUL or CONFIRMED (70 / 70) and none qualifies before its first close;
33 governing theses are OBSERVED while legacy readiness still says WAIT_TRIGGER - the data mining now sees earlier.

Part 2 (same day, ACK: "finish the build"), test-first (`tests/test_p8_event_clocks.py` 17,
`tests/test_p8_opportunity_ledger.py` 11):

- **Data landed** `thesis__data_received_at` / `thesis__data_provider`: the daily store's `fetched_at` / provider of the
  last completed bar (`HistoricalPriceDatabase.read` metadata; bar columns unchanged). SOFI's 9 Oct bar landed
  10 Oct 18:46 UTC.
- **Stage stamps** (each set by the stage that acts, carried by `THESIS_SPINE_FIELDS`): `thesis__contract_prepared_at`
  (Options `process_ticker`, via `contract_prepared_at_utc` and EOD), `thesis__last_revalidated_at` (Morning gate
  check time), `thesis__delivered_at` (one time per book publication, Evening then Morning).
- **R3 opportunity ledger**: `opportunity_events` table beside the candidate ledger (append-only triggers), one row at
  first sight and one per status change, keyed `event_id` / `entry_opportunity_id`; written by Discovery after the
  candidate ledger. **Cohort**: `domain/opportunity_outcomes.py` - one row per opportunity with first sight, status
  path, recognition lag (sessions from the trigger close to the bar first seen on) and outcome views from the bars
  (fill next open; ATR frozen at the trigger close; +1 / +3 / +5 / +10 returns in ATR, MFE / MAE, first +-1 ATR barrier
  favourable / adverse, same-bar ambiguity; CENSORED / PENDING_FILL when not enough sessions). Discovery writes
  `discovery/opportunity_cohort_<run>.csv` each run (status in the summary; never fails the run). Context for mining.
- **Evidence bars (N2)**: `thesis__event_evidence` names the bars that set the status (event@bar date). A revised
  trigger level is a new `event_id` under the same candidate (event versioning by identity).
- **Lab card**: Trigger column shows the event status and trigger age; the card shows Event status, Event clocks and
  Data and delivery times.

Acceptance (`opportunity_cohort_replay.json`, read-only, 200 tickers read as of 25 Sep with outcomes through 9 Oct, a
temporary ledger): 625 events / opportunities recorded, re-recording the run added nothing; the B3 invariants hold as
hard assertions (unique opportunities, trigger close on or before the read, fill strictly after the trigger close);
87 daily crossings, 81 with complete views, 5 pending fill, 1 censored, 1 same-bar ambiguous.

Still to note for B4.3: `event_readiness` walks events in detector order, not bar order (one replay row
CLOSED_OUTCOME_REACHED with a FAILED event). The ledger fills from tonight's run; earlier opportunities exist only
in replays.
