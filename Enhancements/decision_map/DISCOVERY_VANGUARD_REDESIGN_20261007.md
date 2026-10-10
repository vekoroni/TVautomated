# Discovery and Vanguard redesign: one candidate, one story (v2)

**Date:** 7 Oct 2026. **Status:** DESIGN FOR ACK APPROVAL. No code changes until it is approved.

**Decisions this rests on (ACK, 7 Oct 2026):**
- **D-A (revised in v2):** Discovery owns detection, the CORE structural and behavioural analysis, and direction adoption. It publishes a versioned conditional thesis per candidate. **Vanguard adds context** (historical evidence, auction and value context, contradiction flags) and never changes direction.
- **D-B:** Every candidate is carried forward. There is no resource cap; rank orders the work and never drops a candidate.
- **D-C:** "Turn + cheap IV" enters Discovery as one measured scenario family, but only if the universe test passes (`Enhancements/lean_path_test/TURN_CHEAP_ADDENDUM_PREREG_20261007.md`).
- **D-D (new in v2):** Compression is one connected episode: detection, then development, then directional resolution, then follow-through or failure. It is **not another scoring engine.** The trigger layer detects *events* against the episode's recorded boundaries.
- **Rule 4 suspended:** CLAUDE.md rule 4 is suspended, so modules may be replaced. The working rules still apply: an approved design first, a failing business test first, and acceptance against reality.

**v1 → v2 changes:**
- Direction adoption and the CORE analysis move from Vanguard to Discovery.
- Vanguard becomes context only.
- Compression episode and trigger-layer sections added (§6, §7), based on a code review of `avshunter_discovery_ULTIMATE.py`, `wyckoff_crabel_precor_logic_v2.py`, `trigger_layer.py` and `domain/structure_behaviour/compression.py`.

---

## 1. Why: the problem this fixes

The trader's card does not tell one coherent story. Run `20261006_060401` was traced end to end on 7 Oct (read-only):

| Part of the story | What happens today |
|---|---|
| Side | Set by the daily primary candidate. 645 tickers are left UNASSIGNED, because the higher-timeframe tiebreak is off |
| Setup shown | Differs from the thesis candidate on 646 of 1,052 directed rows (32 of the 51 GO rows) |
| Target | Discovery replaces the setup's own target with the legacy `PRIOR_RANGE_EXTREME` on 846 of 951 rows. The card then shows a third level |
| Trigger | Replaced by the Wall-Break phase-C break on 1,009 of 1,039 rows. The card shows a trigger *category* from `trigger_layer`, which is a fourth source |
| Contract | The thesis candidate's own contract lane is "measurement only". Its median rank is 4,460 against a cap of 2,000, so 808 of 1,052 are deferred. The card's contract comes from the per-ticker legacy lane and is re-selected twice |
| Vetoes | 3,325 identities → 51 GO. Removals come from unresolved side, WAIT exclusion, liquidity pending, campaign verdict missing, trigger-primary GO eligibility and other gates |

**The root is in Discovery.** Its per-ticker scan builds one thesis row from four sources. Each later stage then re-derives part of the story instead of carrying it forward.

**Source:** `avshunter_discovery_ULTIMATE.py` 1685–2090:
- side: `engine.handoff_thesis`;
- governing setup and invalidation: `trade_lane.select_governing` / `governed_invalidation`;
- target: `wyckoff_phase_validator` → `_side_geometry` → `legacy_direction_adapter_v1`;
- trigger: text only.

**Signal accuracy is the second problem:**
- On a survivorship-free history, the pipeline's side is a coin flip (49%) (`Enhancements/direction_evidence/`).
- On ACK's real trades, today's engine took ACK's side on only 21% of the ≥ +100% winners. It read the opposite side on 50% and gave no side on 29%. It favours continuation; ACK's winners bought the turn on cheap options.

## 2. What the GPT era actually did (the behaviour to automate)

From the 78 decoded Colab notebooks (`Enhancements/gpt_era/notebooks/INVENTORY.csv`) and ACK's trade record:

- **Screening was fail-open.**
  - v10.7 screener (`DISCOVERY_FAIL_OPEN`): every ticker gets a side and is ranked, and the top 50 go to GPT.
  - CORE Input Builder v3.1: options and liquidity checks *"are warnings only — never skip a ticker."*
- **CORE (GPT plus ACK's eye) did the judgement, including direction**, using daily and intraday views of the chart.
  - The Colab Wyckoff code did not contain the turn read. Replayed on ACK's trades, the v10.7 side matched only 36% of big winners and CORE read NEUTRAL on 71%.
- **The gates arrived with automation:** Execution Engine v5.1 (Apr–Jun 2026) introduced hard blocks and demotions.
- **What ACK's winners had in common:**
  - turn + cheap: entry after the stock had moved about −9% and stretched about 0.9 Keltner widths against the side, with IV low;
  - entry at the start of the move: the move began a median of 1 session after entry;
  - a hold of about 2 weeks while a 2–3 ATR move arrived and volume doubled.
  - Sample: 97 trades, so this is a hypothesis, tested tonight.

**Intended progression:** *Screening proposes. CORE examines the evidence in depth and settles direction. Options Intelligence assesses the contract.* In this design, Screening and CORE both live in **Discovery**. Vanguard is the evidence and context layer (the specification's C4 role); it informs and challenges the thesis but does not own it.

## 3. Principles (each one is testable)

- **P1 One candidate, one story.** A candidate's side, trigger, invalidation, target and timeframe come from that candidate alone. Every later stage carries them and never re-derives them.
- **P2 No vetoes before the human.** Discovery and Vanguard label, flag and rank. A candidate leaves only for an explicit, recorded lifecycle reason: invalidated, failed or outcome reached.
- **P3 Discovery owns direction (D-A).**
  - Every candidate carries a proposed side from its setup. Discovery's thesis step adopts it, refuses it or leaves it UNRESOLVED with a condition, under stated scenario rules.
  - A ticker can hold a bull candidate and a bear candidate at the same time.
  - **Vanguard never changes direction or levels.** It attaches context, contradictions and historical evidence.
- **P4 Compute once (one owner per fact, R2).** Compression, Wyckoff events, control and levels each have one owner. The behavioural engine runs once per ticker.
- **P5 Missing is never neutral (R1).** Unmeasured fields are recorded as NOT_MEASURED with a reason, and never become zero, 0.5, 50, NEUTRAL or an invented default.
- **P6 Contributors earn weight by measurement.** Each ranking input gets weight only from measured uplift on history plus forward C12 measurement.
- **P7 Context never ranks.** Macro, futures bias and sector regime are labels for the human (CLAUDE.md rule 6).
- **P8 Events, not states.** An activation is a timestamped event against recorded levels: a break, rejection, retest or failure. Never a re-classification of today's trend state.
- **P9 Measured against reality.** Every phase is accepted on frozen history and on the next human-run Evening/Morning, not by unit tests alone.

## 4. Target flow

```text
Canonical market data  ── one reproducible snapshot; completed vs partial bars explicit; timestamps explicit
   ↓
DISCOVERY
   ├─ Detection      : engine reading per ticker (once) → candidates + compression episodes (boundaries, episode id)
   ├─ Development    : structural / behavioural analysis per candidate (boundary defence, failed tests,
   │                   effort vs result, absorption vs supply, higher-timeframe context)
   └─ Thesis         : adopt / refuse / UNRESOLVED per candidate under scenario rules → versioned conditional
                       ThesisRecord (side, trigger, invalidation, target, contradictions)
   ↓  every thesis, ranked (no cap, no drop)
TRIGGER LAYER  ── timestamped events against the recorded boundaries (break, acceptance, rejection, retest,
                  failure, VWAP reclaim/loss) → attached to the episode; ACTIVATED / FAILED transitions
   ↓
VANGUARD (context) ── historical cohort evidence, auction / value context, contradiction flags → attached, never edits
   ↓
OPTIONS ── prices each thesis's own side/target/invalidation/window
   ↓
EOD / MORNING / LAB ── carry thesis_id end to end; Morning repairs only the contract inside the thesis; Lab renders the record
```

## 5. Discovery: detection, CORE analysis and thesis

| Function (GPT inventory) | Current owner | Action |
|---|---|---|
| Universe classification and eligibility | `scan_ticker_ultimate` intake flags (discovery 1395–1413) | **Keep as labels only.** No price or volume gate |
| **Detection:** setup families (continuation, pullback, breakout and reclaim, breakdown, Spring/shakeout and test, upthrust and failed breakout, absorption, failed support, Change-of-Behaviour, hinge) | `domain/structure_behaviour` (`engine.analyse_ticker`, `events.py`, `signals.py`) | **Keep; the only candidate source.** Each directed candidate becomes a CandidateRecord with its own levels |
| Detection: **compression episode** | Four owners today (§6) | **One owner:** the engine's `compression.py`, extended with an episode and persisted boundaries (§6) |
| Detection: **turn / exhaustion** | New family, from ACK's trades | **Add if the universe test passes (D-C).** Rule frozen in the addendum |
| Detection: Wyckoff phase hypothesis and readiness | Engine `phase.py`, maturity | **Keep as labels** |
| Detection: Trades-in-Place / imminence | Partly in the engine (`Age_Bars`, trigger level) | **Add ranking contributors** `distance_to_trigger_atr`, `pre_trigger_momentum` (the start of the move) |
| **Development (CORE):** situation; multi-timeframe structure; governing vs supporting setup | `trade_lane.select_governing` (in Discovery today) | **Keep in Discovery.** Conflicts stay visible; they are never averaged |
| Development: boundary defence, failed tests, effort vs result, absorption vs supply, control, bar and volume narrative, behaviour, Soul of the Chart | Engine `control.py`, `behaviour.py`, `sequences.py`, `events.py` | **Keep; connect to the episode and candidate** (§6). Interpretation is recorded as evidence for UP / DOWN / UNRESOLVED |
| Development: LLR, Truth-Extractor, counter-case, contradictions | Distributed: thesis contracts, Morning, Interpreter | **One owner: Discovery's thesis step.** It records the strongest evidence for and against, the missing inputs and the deciding reason |
| **Thesis:** direction adoption | Discovery Stage 0 plus the legacy direction stack | **Discovery thesis step.** It adopts, refuses or leaves UNRESOLVED under stated scenario rules (§6.3). It publishes a versioned conditional ThesisRecord |
| Thesis: trigger zone, invalidation, target and runway, hold duration | Engine levels; `duration.py`; `anticipated_move` | **From the candidate (P1).** Duration is attached with its basis |
| Thesis: imminence vs execution readiness | Lifecycle states, Morning | **Discovery state** (DEVELOPING / ACTIVATED / INVALIDATED / OUTCOME_REACHED). Activation comes from trigger-layer events. Readiness: WAIT_TRIGGER / ARMED / READY_FOR_HUMAN_REVIEW |
| Contributors: relative strength, volume participation, ticker-level IV vs its own history, option activity (quiet / crowded) | Scattered; `iv_history_cache.db`, Phantom `iv_surface_history` | **Single owners in Discovery, as measured contributors (P6)** |
| Legacy direction stack: `WyckoffEngine_3101_v2`, `process_precore_signal` / `symmetric_precor_intent`, `swing_fusion.fuse_wyckoff_crabel`, `resolve_discovery_thesis_direction`, asymmetry targets, `wyckoff_phase_validator` geometry, `legacy_direction_adapter_v1` | Discovery 1685–2090; precor; swing_fusion | **Retire from authority.** They do not set side, target, invalidation or rank. Kept as `legacy_*` columns for audit and C12 comparison until phase 6 |
| Tier, composite and "win probability" from Wyckoff × Crabel scores | `assign_tier`, `calculate_composite_score`, `calculate_win_probability` (discovery 622–660, 1491, 1860) | **Retire.** These are heuristic scores labelled as probability (R6). Replaced by rank with a stored basis |
| Trade lanes with hit rates | `trade_lane.py`, `config/beh001_lanes_v1.json` | **Display only.** The hit rates are in-sample |
| Predictability, FlowScore, Cognition, X200, ITM-durability thresholds | Historical | **Not authorities.** Contributors only, if they pass P6 |
| Macro, futures bias, sector rotation | Macro packets, sector resolver | **Context labels (P7)** |

**Ranking:**
- A transparent rank over theses, with the basis stored.
- Until contributors are measured, the order is: activated before developing; nearer the trigger first; then any contributors that have passed P6.
- Rank orders the work and the Lab view. **It never removes a candidate.** The 2,000 cap (`scripts/options_candidate_lane.py`) and `handoff_packet._rank_key` are replaced.

**Discovery losses to explain in phase 0:** "1,036 intraday-only untested", 331 no live setup, 109 insufficient bars, 28 no price data and 7 scan errors. The 1,036 need a root cause, because that is a recall loss.

## 6. Compression: one connected episode (D-D)

### 6.1 Current state (code review, 7 Oct 2026; behaviour confirmed on run 20261006_060401)

| Owner | What it computes | Problem |
|---|---|---|
| `avshunter_discovery_ULTIMATE.crabel_compression` (351–455) | ATR7/ATR20 ratio, NR7 and volume dryness, as a 0–100 score with READY / COILING | The percentile defaults to **50 "neutral"** when history is thin (R1). The score feeds **tier, composite and "win_probability"** (622–660, 1491–1492, 1860). No boundaries |
| `wyckoff_crabel_precor_logic_v2._infer_crabel_compression` (368–420) and `_sym_compressed` (950–969) | NR7/NR4, ATR percentile and inside bars, as a 0–7 score → CRABEL_READY / COILING | A second and third definition. Labelled "audit only", yet `crabel_score` drives `vol_expansion_potential` (discovery 1834). The ATR percentile defaults to 0.5 |
| `domain/structure_behaviour/compression.py` (31–75) | Strict NR windows, inside bar, a true-range ratio, **box high and low**, location (AT_SUPPORT, ABOVE_RISING_FLOOR …), contracting side; completed bars; never creates direction | **The right foundation.** But there is no episode identity and no persistence of the box between runs, so development and resolution cannot be followed |
| `trigger_layer._t1_vol_compression` / `_t1_realised_compression` (370–415) | A state test on the row's `crabel_compression` (default 1.0), `atr_percentile_rank` (default 100) and `crabel_state` | It reads Discovery's score fields again. A fourth compression rule. No boundary |

### 6.2 Target: one owner, one episode

- **Owner:** `domain/structure_behaviour/compression.py`, extended. The others are retired to `legacy_*` (§5).
- **Episode identity:** `compression_episode_id` = ticker | timeframe | box-origin date.
  - It is created when the engine reports CONTRACTING.
  - It is persisted in the existing behavioural candidate ledger (`data/canonical/behavioural_candidate_ledger.sqlite`, `lifecycle.transitions`), so the box survives between runs.
- **Recorded boundaries:** `box_high`, `box_low` and their origin bars. A boundary may widen only by a recorded rule; each revision is a logged LEVELS_REVISED event, never a silent overwrite.
- **Episode states:**

  ```text
  DETECTED → DEVELOPING → RESOLVED_UP | RESOLVED_DOWN | FAILED_BREAK_UP | FAILED_BREAK_DOWN → FOLLOW_THROUGH | FAILED | ABANDONED
  ```

  Transitions come from trigger-layer events (§7). ABANDONED = the box was invalidated by time or width rules (to be stated and measured).

### 6.3 Development and directional resolution (Discovery CORE)

Per episode, from completed bars, recorded as evidence. **Not a score.**

| Evidence | Meaning |
|---|---|
| Boundary tests (count, depth, closes beyond and back) | Which side is being attacked and which defended |
| Failed tests (wick beyond, close back inside) | Absorption or rejection at a boundary |
| Effort vs result at each boundary (volume vs progress) | Supply overcoming demand, or demand absorbing supply |
| Contracting side (`UPSIDE` / `DOWNSIDE` / `BOTH`) and location (`ABOVE_RISING_FLOOR`, `BELOW_FALLING_CEILING`) | Already computed by the engine |
| Larger-timeframe context (governing setup, control on 1w/1mo) | The campaign the coil sits inside |

**Scenario rules** turn this evidence into a side or leave it UNRESOLVED. **They are specified and pre-registered before use, then measured on history (phase 5).** Until a rule has measured support, the episode stays UNRESOLVED with both boundaries as conditions: "BULL if accepted above box_high; BEAR if accepted below box_low". That is still a usable, conditional thesis.

### 6.4 Follow-through or failure

After resolution, the episode records:
- expansion distance in ATR;
- time to expand;
- whether the broken boundary held on a retest;
- a failure (back inside the box) as FAILED_BREAK. That failure is itself a candidate for the opposite side (a trap). It is detected from structure, never from options volume.

## 7. Trigger layer: events against recorded boundaries (P8)

### 7.1 Current state (`trigger_layer.py` v2.2, Phase 8.6; confirmed on run 20261006_060401, 1,636 rows)

- **It classifies today's state, not events.**
  - RANGE_BREAK = "markup bucket + EMA aligned + ADX ≥ 25", which is a mature trend, i.e. late.
  - RANGE_BREAK_EARLY = "phase C/D + ADX 18–28".
  - **No boundary is checked.**
- **VWAP_RECLAIM / VWAP_LOSS can never fire** (0 of 1,636). They require `layer1__control__controller`, which Vanguard sets to NEUTRAL on every row (RC02).
- **TRAP is disabled** (returns None).
- **It has its own direction fallback chain** (options_direction → precor_intent → dominant_trend → vwap_bias): a direction owner that contradicts P3.
- **It runs after Options and EIL**, and its `trigger_primary` gates GO eligibility. 814 of 1,636 rows had NONE.
- The card's numeric `trigger_price` comes from a **different** module: Wall-Break phase C (`eod_candidate_engine.py:2778–2783`, `contracts/lab_control.py:4549`).

### 7.2 Target

- **Position:** after Discovery's thesis and before Vanguard and Options. Each run it reads the thesis and episode levels and the new completed bars.
- **Events** (timestamped, with the bar and the level they refer to), using the engine's existing acceptance rule (2 closes ≥ 0.25 ATR beyond the level, `config/beh001_behaviour_v1.json`):

| Event | Definition (levels from the thesis or episode only) |
|---|---|
| `BREAK_ATTEMPT_UP/DOWN` | First close beyond box_high / box_low (or the thesis trigger) |
| `BREAK_ACCEPTED_UP/DOWN` | The acceptance rule is met → episode RESOLVED_UP/DOWN; thesis ACTIVATED if the side matches |
| `BREAK_REJECTED` / `FAILED_BREAK` | Back inside the box within the rule's window → a trap candidate for the opposite side |
| `RETEST_HELD` / `RETEST_FAILED` | Return to the broken boundary, held or lost |
| `VWAP_RECLAIM` / `VWAP_LOSS` | Computed **from bars** (prior close vs anchored/session VWAP and today's close), not from Vanguard's controller |
| `INVALIDATED` | Acceptance beyond the thesis invalidation → thesis INVALIDATED |
| `OUTCOME_REACHED` | Close at or beyond the thesis target |

- **Rules:**
  - No direction logic in the trigger layer.
  - No GO gate: events change lifecycle state and ranking order only.
  - Missing bars → NOT_MEASURED, never "no event".
- **Card fields:** the thesis `trigger_level` (numeric) and the last event with its timestamp. Wall-Break and the old `trigger_primary` become `legacy_*` labels.
- **Intraday:** the same events can run on stored 5-minute bars (from Sep 2025) for the Morning run, labelled with their interval. Daily events remain the default.

## 8. Vanguard: context, never authority

**Business question:** what does history and the market's structure add to this thesis, and what contradicts it? **Output:** a `VanguardContext` attached to each thesis_id. **No side, level or state changes.**

| Function | Current owner | Action |
|---|---|---|
| Historical evidence (actuarial cohort) | `vanguard/layer2_statistical/actuarial_query.py`, v7 database | **Keep, side-correct and honest:** side-specific success; the arithmetic mean beside the median; **no invented defaults** (the +5% / −3% / Kelly 0.1 at lines 1246–1260 are removed); effective sample and cut stated. Fix the timezone seam (RC01). Descriptive until G1–G4 |
| Matching state | `state_calculator.py` | **Fix (RC03/RC19):** unmeasured auction fields are excluded, not scored; mirrored bull/bear definitions; v7 feature parity with runtime |
| Auction and value context (POC, value area, location; acceptance and migration only if measured) | `vanguard/layer1_auction` (the production path returns the profile verdict before the legacy logic, RC02) | **Context only.** POC, value area and location kept. Acceptance, control and migration filled only from valid inputs; otherwise NOT_MEASURED. Never fed into triggers or scoring as zeros |
| Contradiction flags | Scattered | **Vanguard publishes contradictions** (e.g. history weak for this side, price outside value against the thesis). The thesis keeps them visible; it is never silently overruled |
| Data-integrity checks on Vanguard's inputs | Manifest, `thin_package`, `orchestrator_adapter` | **Fix:** one history policy with specific reasons (RC04); completed-bar volume that does not depend on the run clock (RC18) |
| EV engines (`ev_engine*`, `ev3_stage0`), `edge_detector`, `scenario_builder` | `vanguard/` | **Retire from authority** (CLAUDE.md rule 5); audit only |
| `ACTUARIAL_WEAK` → Options WAIT exclusion | `vanguard/main.py:410–422`; `scripts/avshunter_options_intelligence.py:10274` | **Remove as a gate.** It becomes a contradiction flag on the thesis |
| `vanguard/config.py` `min_price: 10.0` | `vanguard/config.py:213` | **Verify it is unused, then remove.** It must never act as a hidden price gate |

## 9. The records every later stage consumes

**CandidateRecord** (Discovery detection; immutable once written):

| Group | Fields |
|---|---|
| Identity | `candidate_id` (stable: ticker, timeframe, scope, type, setup-origin date), `parent_candidate_id`, `compression_episode_id` (if any), `ticker`, `as_of_session`, `policy_version`, `engine_version` |
| Setup | `family`, `signal_type`, `signal_state`, `timeframe`, `scope`, `age_bars`, `wyckoff_phase_hypothesis`, `readiness_label`, `compression_state`, `box_high`, `box_low`, `location`, `contracting_side` |
| Proposed levels | `proposed_side`, `trigger_level`, `invalidation_level`, `target_level`, `target_definition`, `atr_daily`, `atr_tf` |
| Contributors | `distance_to_trigger_atr`, `pre_trigger_momentum`, `rel_strength_sector`, `volume_participation`, `iv_vs_own_history`, `option_activity_state`, turn metrics. Each has a `*_status` (MEASURED / NOT_MEASURED + reason) |
| Labels / lineage | Eligibility flags, sector, macro (display only), input data cut and hashes |

**ThesisRecord** (Discovery thesis step; a new version on each run, never edited in place):

| Group | Fields |
|---|---|
| Identity | `thesis_id` (= `candidate_id` + version), `candidate_id`, `compression_episode_id`, `run_id` |
| Decision | `adoption_state` (ADOPTED / REFUSED / UNRESOLVED), `scenario_rule_id`, `deciding_reason`, `unresolved_condition` |
| Story | `side` (or both conditional sides when UNRESOLVED), `trigger_level`, `invalidation_level`, `target_level`, `timeframe`, `early_warning_level` (optional, labelled) |
| State | `lifecycle_state`, `last_event` (type, timestamp, bar, level), `readiness`, `hold_window_q50/q80` and `hold_basis` |
| Evidence | Development evidence (§6.3), governing and supporting setup IDs, contradictions, counter-case, missing inputs |

**VanguardContext** (attached by `thesis_id`): cohort (n, effective n, side-correct stats, cut), auction and value context (MEASURED / NOT_MEASURED), contradiction flags.

**Rules carried by every later stage:**
- Every row is keyed by `thesis_id`.
- **No later stage writes the side, trigger, invalidation or target.**
- Morning may repair only the contract inside the thesis.
- The card renders the ThesisRecord plus the VanguardContext, with the candidate ID, trigger level and last event visible.

## 10. What changes later in the pipeline

| Stage | Change | Current code |
|---|---|---|
| Options | Selects contracts **per thesis** (side, target, invalidation, window). The candidate expression lane becomes the production path; per-ticker selection becomes a labelled fallback. UNRESOLVED theses are priced for both conditional sides, labelled. No WAIT exclusion | `scripts/options_candidate_lane.py`; `scripts/avshunter_options_intelligence.py:10274` |
| EOD candidate engine | `trigger_price` = the thesis `trigger_level`. Wall-Break and `trigger_primary` become `legacy_*` | `eod_candidate_engine.py:2777–2783` |
| Execution decision engine (EDE) | No GO gate on `trigger_primary` (`GO_ELIGIBLE_PRIMARIES`) | `execution_decision_engine.py:370, 611`; `trigger_layer.is_go_eligible` |
| Morning | Repairs the contract inside the thesis and keeps `thesis_id`. Intraday trigger events are labelled | Morning contract repair |
| Lab | Renders ThesisRecord + VanguardContext. `lab_control` stops filling the trigger from Wall-Break. The anticipated move comes from the same thesis. One ranking owner (RC10) | `contracts/lab_control.py:4549`; `domain/anticipated_move.py:143`; `intelligence-lab/static/trade-card.js` |
| Drop-off audit | A disposition per candidate and thesis, with no package-index assumption (RC12) | `dropoff_audit.py` |

## 11. Retired from decision authority (kept for audit until phase 6, then removed with ACK's approval)

- the legacy Discovery direction stack and geometry;
- the Wyckoff × Crabel tier, composite and "win probability";
- the precor and Discovery compression scores;
- the trigger layer's state-based triggers, direction fallback and GO-eligibility gate;
- Wall-Break as the trigger source;
- trade-lane hit rates as a selector;
- the Vanguard EV engines and `ACTUARIAL_WEAK` as a gate;
- the fabricated actuarial defaults and auction zero-scores;
- Phantom's unreachable HIGH/CONVICTION states and its entropy bonus;
- delta-difference "mispricing";
- Predictability, FlowScore, Cognition and X200 as authorities.

## 12. Implementation phases (each is test-first, ACK-approved and accepted against reality)

| Phase | Scope | Failing business-rule test (written first) | Acceptance |
|---|---|---|---|
| **0 Characterise** | Pin today's behaviour on frozen run `20261006_060401`: mismatch counts, vetoes, Discovery losses (1,036 / 331 / 109 / 28 / 7) and their root causes, the four compression owners, trigger-layer counts (VWAP 0, TRAP 0, NONE 814) | Characterisation tests record today's numbers | A report ACK has read |
| **1 CandidateRecord and compression episode** | The engine is the single candidate and compression source. Episode id, boundaries and ledger persistence | "Every CandidateRecord's levels equal the engine candidate's; no legacy geometry in a thesis field"; "a box persists across runs and changes only through a logged revision"; "a thin-history compression field is NOT_MEASURED, never 50" | Frozen replay: 0 mismatches; episodes reconstruct across consecutive runs |
| **2 Thesis step in Discovery** | Adoption states and scenario rules (UNRESOLVED by default with both conditions); development evidence; one owner of direction | "Only the thesis step writes side"; "an UNRESOLVED episode carries both conditional boundaries"; "a legacy direction field never changes the thesis side" | Replay: every thesis has a recorded decision and reason |
| **3 Trigger layer as an event detector** | Events against recorded levels, VWAP from bars, structural trap (failed break), no direction, no GO gate, positioned before Options | "A close beyond box_high with acceptance produces BREAK_ACCEPTED_UP at that bar"; "a break back inside within the window produces FAILED_BREAK"; "VWAP events fire from bars without any Vanguard field"; "the trigger layer never writes side" | Replay on history: event timestamps match independent bar checks; VWAP and failed-break events occur |
| **4 Vanguard as context** | RC01, RC03, RC04, RC05 (defaults), RC18 fixes; NOT_MEASURED semantics; contradictions; `ACTUARIAL_WEAK` no longer a gate | Per defect, e.g. "the same session cut gives the same side blocks for a date or a UTC timestamp"; "an empty winner set publishes NOT_MEASURED, not +5%"; "Vanguard output never changes a thesis field" | Defect counts reach 0 on replay; mirrored bull/bear cases match |
| **5 Consumers, no cap, no veto** | Options / EOD / EDE / Morning / Lab carry `thesis_id`; the 2,000 cap is removed | "One thesis_id has the same side, trigger, target, invalidation and contract identity at every stage"; "no candidate disappears without a recorded disposition" | ACK's next Evening/Morning run: mismatch counts 0; every card shows its candidate ID and last event |
| **6 Scenario rules, families and contributors measured** | Compression resolution rules; TURN (+ cheap IV) if the universe test passes; contributor weights | "A rule or contributor without measured support has zero rank weight and leaves the thesis UNRESOLVED" | Pre-registered history tests; forward C12 per family; G1–G4 before any authority; then retirement and cleanup |

**How the work is done:**
- One change per step, each with its own commit when ACK asks.
- `--plan-only` checks before ACK runs the pipeline.
- No pipeline run while a Phantom backfill is writing.

## 13. Dependencies and open items

- **The universe tests running tonight decide:** D-C (the TURN family); and evidence for X5 and limit exits, which belongs to a separate Options and execution design.
- **Compression scenario rules** (§6.3) must be specified, pre-registered and measured before they adopt a side. Until then, compression episodes publish conditional theses (both boundaries).
- **Auction acceptance and migration:** decide in phase 4 whether stored completed market profiles or intraday bars can supply them. Otherwise NOT_MEASURED.
- **Throughput:** about 18,500 candidates per run without a cap; actuarial cohort queries need a measured budget. Compute is the fix, never dropping candidates.
- **Direction accuracy is not solved by this redesign.** The redesign makes the story coherent, the events real and the data honest. Whether adopted sides are right is measured in phase 6. No accuracy claim is made in advance.

## 14. Single source of truth: fact ownership register

Every fact has **one producer**. Everything else reads it. Two tests stop a second producer from reappearing.

**How each duplicated fact is resolved (the same five steps for all of them):**
1. **Choose the owner on evidence.** Prefer the producer that uses completed bars only, records its levels, takes thresholds from versioned config and never creates direction where that is not its job.
2. **Measure the disagreement before switching (phase 0).** An agreement matrix of all producers on the frozen run, plus the downstream values that would change.
3. **Stop the others computing.** Each retired producer becomes a thin reader that copies the owner's value into its old column under `legacy_*`, so existing readers do not break. Scores derived from retired producers are retired with them.
4. **Enforce.**
   - A **single-writer test**: the field provenance of the owned fields on a fixture run must name the owner.
   - A **guard test**: it fails if a module outside the owner defines a calculation for that fact.
5. **Remove the legacy copies in phase 6**, after ACK-run Evening/Morning runs confirm nothing reads them.

| Fact | Producers today (7 Oct review) | Single owner | Retired producers |
|---|---|---|---|
| Compression (state, NR flags, box, location, contracting side) | `discovery.crabel_compression`; `precor._infer_crabel_compression`; `precor._sym_compressed`; `structure_behaviour/compression.py`; trigger-layer T1 re-test | `domain/structure_behaviour/compression.py` + compression episode (§6) | Discovery and precor compression; Crabel tier, composite, "win probability", `vol_expansion_potential`; trigger-layer T1 |
| Direction (side) | `engine.handoff_thesis`; `resolve_discovery_thesis_direction`; precor intent (raw and symmetric); `swing_fusion.fuse_wyckoff_crabel`; `trigger_layer._direction` | The Discovery thesis step (§5, P3) | All the others become `legacy_*` |
| Target | Asymmetry `target1`; Wyckoff validator `PRIOR_RANGE_EXTREME`; engine `Outcome_Level`; `structural_target`; `anticipated_level` | The candidate's `Outcome_Level` (the anticipated move is computed from it and labelled as such) | Asymmetry, validator geometry, legacy adapter |
| Invalidation | `governed_invalidation`; validator candidate invalidation; legacy stop fields | The candidate's `Invalidation_Level` (early-warning level optional, labelled) | Validator and legacy stops |
| Trigger level and activation | Engine `Trigger_Level`; Wall-Break phase B/C; `trigger_layer.trigger_primary` | `Trigger_Level` (level) + trigger-layer events (§7) | Wall-Break as the trigger; state-based trigger categories |
| Contract | Per-ticker Options lane; candidate expression lane; Morning repair | Options, per `thesis_id`; Morning repairs within the thesis only | Per-ticker selection becomes a labelled fallback |
| ATR / volatility scale | Several local ATR implementations (SMA and EMA true range, ranges) | One canonical ATR definition per timeframe in versioned config, read by all | Local ATR helpers in decision paths |
| Wyckoff phase and event | `WyckoffEngine_3101_v2`; precor; engine `phase.py`/`events.py`; Colab-era logic | Engine `phase.py` / `events.py` | 3101 engine and precor phase as authorities |
| Vanguard matching state (added in Phase 4) | Live `state_calculator` rules (structure from VWAP + auction; own trend and maturity rules); `vanguard/core/actuarial_core_v7.calculate_core_state` (built the v7 database); a second copy in `avshunter_db_update._compute_state` / `_compute_technicals` | `actuarial_core_v7` (the builder the v7 database cites). Live matching dimensions are taken from it (`db_consistent_core_dims`; F3 did the same for `vol_regime` on 19 Sep) | Live structure / trend / maturity rules become legacy display fields. `avshunter_db_update` is to be pointed at `actuarial_core_v7` or retired (cleanup phase). Phase 4 parity on run 20261006_060401: structure 75/200, trend 131/200, maturity 104/200 before the fix |
| Daily price history (added after Phase 0) | Canonical `historical_prices.sqlite` (read by Discovery); the separate vanguard-folder history used to build actuarial v7; stale `data/daily/*.csv` fallbacks | Canonical `historical_prices.sqlite`. The actuarial builder and every decision path read it; depth and freshness are reported per ticker | The stale CSV fallback in decision paths. Phase 0 found about 1,270 tickers seeded with 92 bars in the canonical store while v7 held full history for the same tickers; that was backfilled on 7 Oct 2026, see the receipt |
| Thesis readiness and GO eligibility (added in Phase 5.3, ACK 8 Oct 2026 "Thesis activated") | `trigger_layer.is_go_eligible` (state category `trigger_primary` in `GO_ELIGIBLE_PRIMARIES`); `build_thesis` Readiness from the engine state; EDE `sovereign_event_gate` (same state set, dormant); `pretrade_focus` (`trigger_primary == RANGE_BREAK` plus a spot cross of `trigger_price`) | Discovery's event step: `contracts.thesis_record.event_readiness` on the governing thesis's own events (accepted break or held retest on its side, not since invalidated, failed or completed) -> `thesis__readiness`. `trigger_go_eligible` mirrors it (`go_basis` THESIS_READINESS_V1); EDE, Morning and the Evening bucket read it | The state rule survives only as `legacy_state_go_eligible` (audit). Missing readiness is not GO (THESIS_READINESS_NOT_RECORDED). A thesis whose trigger is not accepted stays in the book as WAIT_TRIGGER |
| Opportunity rank (added in Phase 5.5, RC10; ACK E11b 8 Oct 2026) | `lab_control.build_final_opportunity_book` (verdict order + retired priority score); `intelligence_lab._finalise_lab_priority_ranking` (action bucket + research priority score, the Lab table's order); `trade-summary.js` (value multiple) | `domain/opportunity_rank.rank_key`: lane, thesis readiness, expected option multiple, evidence, ticker. `lab_rank` and `priority_rank` both come from it; the trade summary shows that order | The priority score and action bucket are display labels only. The verdict is shown but does not order rows |
| Drop-off disposition (added in Phase 5.5, RC12) | `dropoff_audit._reason` assumed a package index; every Discovery row of a package-free run read PENDING_PACKAGE_BUILD (AVS-PKG-002 receipt: "rename in P5") | `dropoff_audit`: the canonical manifest is the intake stage; each row has a stage, reason, reason class (SELECTION / SCOPE / RESOURCE / EVIDENCE / ECONOMIC / HANDOFF / GATE / PROGRESS / SURVIVED) and its thesis (side, readiness, governing candidate) | The package branch stays only for the packages-mode rollback |

Phase 0 builds the agreement matrices. Phases 1–5 move each fact to its owner, with the single-writer and guard tests written first.

## 15. Risks

| Risk | Mitigation |
|---|---|
| More theses reach the Lab | Rank and readiness views (READY first); nothing hidden |
| Replacing modules breaks downstream readers | Ticker spine and `legacy_*` columns kept until phase 6; contract tests per consumer |
| Event detection on daily bars is late compared with ACK's intraday entries | Intraday events on stored 5-minute bars for Morning, labelled; Morning ~15 minutes after the open matches ACK's best entry window |
| Scenario rules overfit | Pre-registration, train/test split, counted trials, forward C12 |
| The turn family fails out of sample | Added only if the pre-registered test passes |
