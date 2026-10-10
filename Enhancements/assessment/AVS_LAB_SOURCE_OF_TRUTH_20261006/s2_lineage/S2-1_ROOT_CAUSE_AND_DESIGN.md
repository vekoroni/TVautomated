# S2-1: value the setup that qualifies the trade. Root cause and design

**Status:** for ACK approval. No production code changed. Design evidence is a read-only replay on the frozen run `20261006_060401` (`replay_governing_setup.py` → `replay_governing_setup_20261006_060401.json/.csv`).
**Approved so far (ACK, 6 Oct 2026):** "start with #1"; E02 (the ticker assessment flows into the option assessment); glossary v0 (the anticipated level must come from the lane-setting setup).

## 1. Business rule (stated in domain language for the failing test)

> **The setup that qualifies a ticker for a lane is the setup whose move, time and invalidation are used to value and express the trade.** A level price has already passed is not a move still to come. Ties between setups are decided by stated evidence, never by spelling.

## 2. Root cause

Discovery picks a "setup" **four times, independently**, from the same BEH-001 readings. Each picker has its own rule, and nothing ties them together:

| Picker | What it sets | Rule | Code |
|---|---|---|---|
| Daily primary | Trade **side** and **invalidation** | Daily timeframe only; ACTIVATED before DETECTED; tie → **alphabetical `Candidate_ID`** | `domain/structure_behaviour/engine.py:187–189, 192–234`; used at discovery `:1720–1737` |
| Lane | **Lane** A/B/C and its tested hit rate | Any timeframe; A > B > C; tested timeframe first; tie → **first in list** | `domain/structure_behaviour/trade_lane.py:112–138`; discovery `:2521` |
| Thesis event | **Move level, duration evidence, timeframe** (anticipated move, Morning recompute, lane B payoff check) | **1d first**, then 1w, 1mo…; ACTIVATED before DETECTED; tie → **alphabetical `Candidate_ID`** | `domain/structure_behaviour/thesis_category.py:15, 39–47`; discovery `:2347` |
| Range target | `target_price` (strike filter, monetisability) | Prior 40-bar extreme | `wyckoff_phase_validator.py:137–144` (S2 #3, separate) |

**A second cause compounds it.** A candidate stays `DETECTED` until its trigger is formally accepted (`signals.py:76–95`), so a setup whose level price has already run through can stay "live". `Outcome_Reached_As_Of` is set only after activation, and none of the three pickers checks whether the level is still ahead of price.

**Effect on run 20261006_060401** (S1):
- 32 of 51 GOs are valued on a 1d event that is not their 1w/1mo lane setup.
- 4 GOs are valued on a level already passed.
- All 7 GOs without a computed value trace to this.

## 3. Design

### D1. One selector: the governing setup
Extend the existing lane owner, `domain/structure_behaviour/trade_lane.py` (no new module), so that it returns the **governing setup** together with the lane. The rule, in order:

1. Trade-side live setups only (side from direction governance; unchanged).
2. **Exclude any setup whose outcome level is not ahead of the price on the trade side.** Each exclusion is recorded with the reason `LEVEL_ALREADY_PASSED`. This is the same test the anticipated move already applies (`anticipated_move.py:117`), now applied *before* selection rather than after.
3. Lane A before B before C; tested timeframe before untested (unchanged).
4. **Stated tie-break:**
   1. ACTIVATED before DETECTED;
   2. then higher holdout hit rate;
   3. then more duration evidence (`Duration_Level_N`);
   4. then the nearer level;
   5. then the newer event (`Age_Bars`).

   `Candidate_ID` is used only as the final deterministic step, when everything else is equal.

**New published field:** `trade_lane_candidate_id`, the governing setup's ID, added to `TRADE_LANE_FIELDS`.

### D2. The thesis evidence comes from the governing setup
- `thesis_category()` gains an optional `governing` candidate. When it is given, `thesis_event*`, `thesis_outcome_level`, `thesis_duration_*` and `thesis_activation_*` are taken from it.
- The anticipated move, the Morning recompute and the lane B payoff check all read those fields today, so **they follow automatically**. Their interfaces are unchanged.
- **The current 1d pick is kept, not deleted ("repair, don't delete"),** as supporting fields `daily_event`, `daily_event_state`, `daily_event_candidate_id` and `daily_event_outcome_level`. They are role SUPPORTING (glossary §2): displayed as "daily refinement" and never used for value, time or invalidation.
- A 1d event may stand in for a 1w/1mo setup only through an explicit parent link. Today BEH-001 has no cross-timeframe parent links (`signals.py:127–130` links within one timeframe), so this does not arise now. It is logged as a future refinement.

### D3. Invalidation: ACK decision needed
The replay shows that the governing setup's own invalidation is **about twice as far** as today's daily-primary invalidation: median 27.9% vs 13.4% of price on the GO rows. That is expected, because weekly and monthly setups have wider structure. Invalidation drives the Morning "invalidation broken → BLOCK" check, the EV3 stop, and the "where am I wrong" line on the card.

| Option | Thesis invalidation | Daily level | Consequence |
|---|---|---|---|
| **I-a** | Governing setup's own | Not shown | Fully consistent; wider; fewer Morning blocks; the card shows a far exit |
| **I-b** | Keep the daily primary | — | Narrower, but it is **another setup's** level: the same substitution we are removing |
| **I-c (recommended)** | Governing setup's own (DECISION: thesis wrong) | Shown as **"early warning"** (SUPPORTING; nearest level that would weaken the setup) | Consistent and honest. You see both: "thesis invalid below X (1w setup); early warning below Y (daily)". Only X gates |

The trade side stays with direction governance; D3 changes only which invalidation *level* is used.

### D4. What does not change in this step
- Direction governance and the trade side.
- Lane definitions and hit rates (`config/beh001_lanes_v1.json`).
- The 40-bar range target (S2 #3).
- The BEH-001 state machine. The passed-level problem is handled at selection (D1.2). Fixing `DETECTED`-with-passed-level inside the engine is logged as a BEH-001 lifecycle item for later.

## 4. Measured impact (replay on the frozen run, read-only)

| Measure | Today | With D1–D2 |
|---|---|---|
| Lane, rows with a side (1,052) | A 357 · B 2 · C 693 | A 331 · B 23* · C 690 · intraday-only 8 |
| Rows with at least one passed level excluded | — | 384 |
| The 51 GOs: lane | A 51 | **A 48 · C 3** (SARO, DKS, UTI: their 1w setup's level is already passed, so they become watch-only) |
| GOs whose valued setup changes | — | **26** |
| GOs with a valid move level | 44 (7 unvalued) | **51**. All 7 regain a level: NET, BIRK, CYTK, BLDR, UNP, ENOV, CENX |
| GOs with duration evidence | — | 50 (1 with NO_COMPARABLE_EVIDENCE) |
| Median time to move (q50, sessions) | 9 | 11 |
| Median move to level (% of price) | 9.8% | 13.1% |
| Median invalidation distance (% of price) | 13.4% (daily primary) | 27.9% (governing setup); see D3 |

\* The replay omits the EOD lane B payoff confirmation. Today that confirmation demotes about 22 B rows to C (payoff too small or unknown), so the B count after it should be close to today's. The real pipeline run will show it.

**8 rows become intraday-only.** Their only remaining trade-side setups after the passed-level filter are intraday, which are untested. Under the current rule (ACK 5 Oct) they are dropped for the run.

## 5. Build plan (test-first, CLAUDE.md)

1. **Characterisation:** pin today's three pickers (daily primary, lane, thesis event) on a fixture with a 1d event and a 1w lane setup, including the alphabetical tie-break and a passed level.
2. **Failing business-rule tests**, in domain language:
   - "the setup that sets the lane is the setup that is valued" (`thesis_event_candidate_id == trade_lane_candidate_id`);
   - "a setup whose level price has already passed never governs";
   - "ties are decided by state, evidence, distance, then age, never by spelling";
   - "the thesis invalidation is the governing setup's" (per the D3 decision), with the daily level as early warning under I-c;
   - "the daily event is kept as supporting fields and never valued".
3. **Minimal change:** `trade_lane.py` (governing setup and ID), `thesis_category.py` (optional governing candidate; daily supporting fields), discovery call order (lane first, then thesis category with the governing candidate; invalidation per D3), and the new fields in `DISC_MERGE_COLS` and the Lab book.
4. **Acceptance:**
   - (a) This replay re-run against the new code's Discovery output on the frozen inputs: 0 GOs valued on a non-governing setup; 0 governed on a passed level; every changed lane explained.
   - (b) Regression suite, one file per process, with failures counted per file.
   - (c) ACK runs Evening and Morning; S0 baseline compared.
   - (d) Outcome scorer: from the next sessions, C12 tracks hit rate and time-to-level for tickets valued on the governing setup against the prior record. This is a forward measure, not a launch gate, because the sample is too short.
5. **The characterisation tests from S0 that this flips** are updated in the same change, with the reason given.

## 6. Decisions for ACK
1. **Approve the governing-setup rule (D1, D2),** including the passed-level exclusion and the stated tie-break.
2. **Invalidation: I-a, I-b or I-c (recommended).**
3. **Accept the consequences:**
   - 3 of today's GOs (SARO, DKS, UTI) would become watch-only, because their qualifying setup's level is already passed;
   - 8 rows would drop as intraday-only;
   - the move, time and invalidation figures shift to the qualifying setup's scale.
