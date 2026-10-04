# AVS-SD-BEH-001 — Behavioural signal candidates in Discovery

**Status:** proposed for ACK sign-off. Design only; no pipeline code. Date: 1 October 2026.
**Sources:**
- ACK's governing requirement (signal table, field contract, four refinements).
- The layered logic ("Bars → … → Signal").
- The SOFI teaching case: four charts plus `SOFI_Behavioural_Training_Rules.json`. These illustrate the reading; they are not tuning data.
- The SOFI design test (`Enhancements/assessment/AVS_BEHAVIOURAL_LOGIC_DESIGN_TEST_SOFI_20261001.md`), fixes F1–F7.

## 1. Deliverable (the only thing this design builds)

For **every Discovery ticker**, at the evidence cut, using only completed bars available at that time, Discovery publishes:

1. **One campaign reading per analysed timeframe:**
   - Wyckoff_Phase, Phase_Confidence, Phase_Transition;
   - Controller and Control_Quality, Control_Origin/Start/Duration, Control_Transfer_Condition;
   - SOT_State and Movement_Maturity;
   - Structural_Context.
2. **Zero or more signal candidates per timeframe.** Each is a testable proposition: who is gaining control; the event; its direction; the trigger that activates it; the expected sequence; what ends it; and the next anticipated logic. Each candidate carries the full field contract in §6.
3. **An explicit monitoring observation** when behaviour supports no direction. No directed candidate is fabricated.

**The same rules apply to every ticker.** All thresholds are in ATR or log units and live in one versioned configuration. There are no per-ticker settings.

## 2. Scope

**In scope**
- **The Discovery behavioural engine:** the eight layers in §4, replacing the side-assignment logic in the current Wyckoff, Precor and fusion code.
- **The candidate output and contract.**
- **A minimal handoff** so existing consumers keep working. The daily campaign candidate populates `thesis__side` and the legacy fields through the existing adapter (§7).
- **Daily timeframe first.** The 60m, 15m and 5m roles are defined in the contract and switched on when intraday data is updated (parked by ACK).

**Out of scope** (each needs its own requirement and decision)
- Vanguard, Options, EV/C8, EIL/EOD, Morning, Lab redesign, Interpreter.
- Hold period and expiry policy (the 1–20 window removal is a separate decision).
- Macro.
- Data backfill or intraday completeness (parked).
- Image or ML models: the engine reads OHLCV, not screenshots.
- Trade approval, sizing, execution.
- Remaining DIR-002 items not needed for the handoff.

**Change control.** Any addition must cite the requirement it serves. An alternative fix is allowed only when the stated requirement cannot otherwise be met, and it is recorded as a dated amendment.

## 3. Timeframe ladder (from the teaching case)

| Role | Timeframe | Question it answers |
|---|---|---|
| Campaign context | Daily | Who controls the campaign, which phase, how mature? |
| Swing sequence | 60 min | Are the swings retaining or surrendering progress? |
| Setup structure | 15 min | Can recoveries or reactions repair the damage? Where are the setup boundaries? |
| Trigger and response | 5 min | Did the trigger fire, and what was the response? |

- **Each timeframe gets its own phase.** A local bullish reclaim can occur inside an intact daily decline.
- **Lower timeframes never inherit the higher timeframe's direction.** Counter-campaign candidates are allowed, and carry a Warning naming the conflict.

## 4. The hierarchy

Each layer uses only the layer below it.

**L1 Bars**
- Completed bars only, at the evidence cut. Bar completion and session flags are recorded.
- True range: max(H−L, |H−prevC|, |L−prevC|). Gap and opening context are preserved (rule TRUE_RANGE).

**L2 Sequences**
- **Swings at two degrees (F3).**
  - *Major swings* (larger ATR reversal) define campaign structure.
  - *Minor swings* (smaller reversal) define setup structure.
- **Pivots keep their confirmation lag.** A pivot exists only from the bar that confirms it (rule AS_OF_ONLY).
- **The current in-progress leg is always part of the read (F2).** Only its end pivot is unconfirmed.
- **Ranges** are overlapping major swings. Their boundaries are defended pivot levels: support, resistance, balance areas, and the levels each decline or advance broke.
- **Each wave records:** ATR-normalised distance, duration, pace, volume and extension beyond the prior extreme (rule SOT).

**L3 Behaviour (per side, one mirrored rule)**
- **Progress:** new extremes beyond the relevant structural level.
- **Retention and repair (F1):**
  - A reaction *repairs* only if it regains the structural level or balance area the prior move broke.
  - A reaction *retains* if the mover's side defends that level.
  - Wave-size ratios are supporting evidence, never the test.
- **Effort and result:**
  - Volume against displacement. Large volume with small progress is an absorption candidate. The side is assigned only from location and subsequent response (rule EFFORT_RESULT).
  - True range is counted once, as the footprint, never as both effort and result (refinement 3).
- **SOT:**
  - Successive same-side thrusts are compared on distance, pace and retained ground.
  - Strength of thrust and shortening of thrust are kept as separate observations.
  - Comparisons use tolerance bands. A change inside the band is "unchanged", not "strengthening" (F7).
- **Acceptance:** progress beyond a level is accepted only if it persists, displaces, and survives the first opposing attempt. A wick across a line is not acceptance.
- **Failure to follow through** is recorded as evidence, never as an event confirmation (refinement 1).

**L4 Control (rule CONTROL_FROM_PROGRESS)**
- **Controller** = BUYERS / SELLERS / TWO-SIDED-EQUILIBRIUM / CONTROL SHIFTING. It comes from which side makes and retains progress across major swings plus the current leg. No participant identity is inferred.
- **Control_Quality:** effective and defended, strengthening or weakening.
- **Control_Origin and Start:** the swing where the current controller began retaining progress.
- **Control_Transfer_Condition:** the specific level whose reclaim and defence by the other side would transfer control. A minor bounce never transfers campaign control.

**L5 Phase (rules PHASE_INFERENCE, NESTED_STRUCTURE; F5)**
- One current phase per timeframe, from current evidence; earlier phases need not be visible.

  | Phase | Evidence that identifies it |
  |---|---|
  | A | An established controller is interrupted: an abnormal opposing move, reduced progress or failed continuation. Needs a prior controlled move. |
  | B | A range exists. Swings test competing control; control may be balanced or drifting to one side. |
  | C | A consequential test of a range boundary (penetration and recovery, or rejection) challenges the apparent direction. |
  | D | One side increasingly retains progress, inside the range or at its edge. |
  | E | The campaign continues beyond the originating range. Thrusts, reactions and emerging opposition are assessed. |

- **A versus C:** both need range context. A interrupts a trend; C tests a range boundary.
- **Phase_Confidence** reflects how completely the evidence fits. **Phase_Transition** records the move (e.g. C_TO_D).
- **Phase can revert** (e.g. expected D strength fails, so back to B). The earlier read is kept and the revision recorded.
- **Nested structure:** a local phase (e.g. a Phase B pause) can sit inside a parent phase (E) and is labelled with its own structure scope.

**L6 Events, with a life cycle (F4)**
- **Every event starts as a candidate.** It is resolved later, from subsequent bars, to CONFIRMED, FAILED or UNRESOLVED. It is never populated from the phase alone.
- **Spring:** penetration of an established support area, recovery, and a constructive subsequent response (rule SPRING_REQUIREMENT). A low, wick or volume spike alone is insufficient.
- **Upthrust:** attempted break of established resistance, rejection, and ineffective subsequent buying. **UTAD** additionally needs a supported late-distribution context (rule UPTHRUST_REQUIREMENT).
- **Failed events:** a failed Spring or failed Upthrust is labelled only after its own thesis fails. Control and the next anticipated logic are then re-read (rule FAILED_EVENT).
- **Other events:**
  - SOS/SOW: effective progress through a level, with retention.
  - LPS/LPSY: a reaction that preserves the prior progress and fails to repair (F1).
  - Absorption: repeated effort, little result.
  - Climax/stopping action: abnormal effort that interrupts.
  - Change of behaviour: an abnormal counter-move, then retained progress.
- **Life cycles are re-derived from bars at each cut.** No persistent state is required for this scope.

**L7 Transition**
- Updates to phase, event and control are appended; the earlier assessments are kept.

**L8 Signal candidates**
- Generated from L4–L7 by the signal table (§5).
- **Three separate decisions:** a candidate is DETECTED (published immediately for downstream interrogation), then ACTIVATED (its trigger met), then APPROVED. Approval is downstream and out of scope.
- **Maturity is separate from trigger freshness:** a new trigger can occur late in a mature move, and gets a Warning (rule MATURE_MOVE).

**Compression (rules COMPRESSION_IS_CONTEXTUAL, NO_FALSE_NR_LABELS; F6)**
- **Features, computed separately:**
  - NR2/3/4/7 from high–low ranges of completed bars, with strict minima declared;
  - inside bars;
  - true-range contraction ratios.
- **Context recorded with it:** the location (e.g. below a falling ceiling, at support), which side's swings are contracting, and who defends territory.
- **It never creates or vetoes a direction.** It adjusts confidence, timing and Warning. Compression that preserves the prior move supports the reading; compression that keeps surrendering it is a contradiction.
- **No supported directional reading** means a monitoring observation, not a directed candidate.
- **A strong Wyckoff reading without compression is not weakened.**

## 5. Signal table

Every BULL rule has a mirrored BEAR rule.

| Signal type | Generated when (L3–L7) | Trigger (activation) | Invalidation (ends this candidate) | Next anticipated logic |
|---|---|---|---|---|
| Spring Candidate ↔ Upthrust Candidate | Established boundary penetrated, then recovered or rejected | Defined recovery or downward response through the local trigger level | Acceptance beyond the event extreme | Failed Spring ↔ Failed Upthrust continuation |
| Spring Secondary Test | Revisit shows reduced selling effectiveness and a constructive recovery | Turn up through the local trigger | Loss of the defended test area | Reassess as testing, or failed Spring |
| UTAD Test | Late failed breakout inside a supported distribution hypothesis, then an ineffective recovery | Defined downward response | Acceptance above the UTAD area | Re-read as breakout (absorption) |
| SOS→LPS ↔ SOW→LPSY | Effective, retained progress, then a reaction that fails to repair the broken level | Resumption through the reaction's boundary | Acceptance beyond the defended LPS/LPSY | Local range or testing; not a campaign reversal |
| Buyer ↔ Seller Absorption | Repeated opposing effort with little result; boundary defended; pressure at the opposite edge | Expansion through that edge | Loss of the defending structure | Two-sided range |
| Failed Spring ↔ Failed Upthrust Continuation | The event's own thesis has failed; lost structure not restored | Continuation through the lost level | Sustained recovery of the lost structure | Spring/Upthrust re-read on the new structure |
| Change-of-Behaviour Reversal | Abnormal counter-move, then evidence of control transfer | Defined structural transfer level | Old controller's structure restored | Continuation of the old campaign |
| Mature Trend Exhaustion | Thrusts lose effectiveness, new extremes fail, opposing reactions improve | Warning only. Becomes directional only when a control-transfer trigger fires | Effective resumption of the trend | Change-of-Behaviour Reversal candidate |
| Shallow-Test Continuation | Strong wave, then limited opposing progress | Original direction resumes | Effective move beyond the test's failure boundary | Range or testing |
| Crabel Compression Breakout / Hinge-Apex Expansion | Contraction or converging swings at a meaningful location, with directional context from L4 | Expansion through the selected boundary | Rapid return into contraction, or failure of the defended boundary | Monitoring observation |

## 6. Candidate field contract

**Required fields:**
- Ticker, Direction, Wyckoff_Phase, Wyckoff_Event, Controller, Control_Quality, SOT_State, Crabel_Compression, Movement_Maturity
- Trigger, Invalidation, Expected_Behaviour, Expected_Duration, Warning

**Supporting fields:**
- Candidate identity: Candidate_ID (ticker + timeframe + type + event-start bar), Signal_Type, Signal_State (DETECTED / ACTIVATED / CONFIRMED / FAILED / UNRESOLVED / MONITOR), Timeframe, Timeframe_Role, As_Of, Bar_Completion
- Campaign context: Structural_Context, Phase_Confidence, Phase_Transition, Direction_Status = HYPOTHESIS_NOT_OUTCOME
- Control: Control_Origin, Control_Start, Control_Duration, Control_Transfer_Condition
- Movement: Movement_Start, Movement_Duration
- Next_Anticipated_Logic
- Evidence: observed / inferred / unresolved labels per observation, plus the measured values behind each judgement
- Missing_Computations

**How fields are filled:**
- **Trigger and Invalidation are price levels with acceptance rules,** taken from the structure (setup boundaries, not universal stops).
- **Expected_Duration** comes from comparable, causally available sequences on the same timeframe (rule DURATION). Until that estimator exists, it is published as `UNESTIMATED` with its reason. It is never hard-coded.

## 7. Handoff (minimal, scope-limited)

- **Candidates go in a separate per-run file** (one row per candidate). The Discovery CSV keeps one row per ticker.
- **The ticker's daily campaign reading sets `thesis__side`:**
  - BULL or BEAR when one directed daily candidate is DETECTED or ACTIVATED;
  - UNASSIGNED, with its reason, when there are none or when daily candidates conflict.
- **The existing legacy adapter** then fills `direction`, levels and status for unchanged downstream consumers.
- **No downstream logic changes in this scope.**

## 8. Acceptance (before any production switch)

1. **Rule tests** for every layer and signal type, including mirror equality on reflected bars and as-of tests.
2. **Universe replay** on the existing point-in-time harness (500 tickers, 2022–2026). Reported:
   - distributions of phase, controller, event, life-cycle outcome and signal type;
   - the share of directed candidates;
   - no BULL Spring inside an unresolved markdown unless its response is constructive.
3. **SOFI sanity check.** Daily read SELLERS / E / MATURE / SOW→LPSY and the teaching anchors are reproduced. This is a check, not a fit.
4. **ACK chart review** of a stratified sample of labelled charts across phases and signal types.
5. **Outcome evaluation** (rule EVALUATION): for each signal type, conditional on trigger activation, judged against its own trigger, invalidation and observed time to resolution. Splits are by time, with grouped dependence. Reported only; no promotion decision in this scope.

Production stays on legacy direction until ACK approves the results of 1–5.

## 9. Build order (daily only)

1. L1–L2: sequences and swing degrees.
2. L3: behaviour.
3. L4: control.
4. L5: phase.
5. L6: event life cycles.
6. L7–L8: transitions and candidates.
7. Compression context.
8. Candidate file and handoff.

Each step follows the same loop: failing rule test → code → mirror and as-of tests → universe replay check before the next layer.

## 10. Decisions for ACK

1. Approve this scope, including the out-of-scope list and change control.
2. Approve daily-first, with intraday switched on after the data update.
3. Approve the §7 handoff rule, which decides `thesis__side` from the daily campaign candidate.

---

## ACK decisions — 1 October 2026

- **§10.1 scope and change control:** APPROVED.
- **§10.3 handoff rule:** APPROVED.
- **§10.2 daily-first: AMENDED.** Build the intraday timeframes (60 min, 15 min, 5 min) now, alongside daily. Requirement: **the engine must not fail when intraday data is missing, partial or stale.**
  - A timeframe without usable data is published as `NOT_EVALUATED` with its reason (e.g. `NO_INTRADAY_DATA`, `INCOMPLETE_SESSION`).
  - The remaining timeframes still produce their readings and candidates.
  - With no intraday data at all, the daily timeframe alone performs the campaign, setup and trigger roles. Its candidates carry a Warning that lower-timeframe confirmation was unavailable.
  - A missing timeframe never blocks a ticker, a run or the handoff, and is never read as evidence for or against a direction.
- **The intraday data update itself remains parked.** The engine reads whatever completed intraday bars the canonical store holds at the evidence cut and makes no provider calls.

## Build clarifications (1 Oct 2026; from failing tests and the SOFI check)

These apply rules already in this design. They add no scope.

1. **Retention (refinement 2, L3/L4).**
   - A new extreme counts as progress only if it is retained.
   - If price is later accepted back beyond the extreme it broke, the push failed. That is evidence for the other side, not progress.
   - Example: a Spring's lower low is not seller progress.
2. **Range persistence (L2).**
   - A boundary test that price has since reclaimed (Spring or Upthrust) does not end the established range.
   - The range is re-read from the pivots before the test.
3. **Nested scope (rule NESTED_STRUCTURE, L4–L8).**
   - Every timeframe publishes a campaign reading from major swings and a local reading from minor swings.
   - Every candidate carries `Structure_Scope` (CAMPAIGN or LOCAL).
   - SOFI daily is the example:
     - campaign: Phase B range 14.88–19.74 with seller pressure;
     - local: Phase E markdown, SELLERS, MATURE, SOW→LPSY.
4. **Tolerance band (F7).**
   - Swing steps used for absorption and pressure must exceed the tolerance band (0.25 × ATR).
   - Smaller steps are noise.
5. **Handoff source (§7).**
   - The behavioural invalidation level travels as `BEHAVIOURAL_STRUCTURE`. The adapter and the C5 packet accept it alongside `WYCKOFF_VALIDATION`.
   - It is never relabelled as another engine's level.
6. **Production switch.**
   - `config/dir002_side_assignment_v1.json` `production_direction_source` now takes `beh001_v1` or `legacy_rollback`. `side_assign_v1` is superseded.
   - It stays `legacy_rollback` until ACK approves acceptance. Until then the behavioural thesis is published under `shadow_*` names, and the candidates file is always written.
