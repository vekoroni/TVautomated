# Discovery and Vanguard redesign: Phases 1–5 report

**Date:** 8 Oct 2026 · **Design:** `Enhancements/decision_map/DISCOVERY_VANGUARD_REDESIGN_20261007.md` (v2) · **Baseline:** `Enhancements/phase0/PHASE0_CHARACTERISATION_REPORT_20261007.md` · **State:** Phases 1–5 built and tested, **not committed**, not yet run live.

## 1. Summary

**The aim** was one candidate, one story. Phase 0 found that the trade card assembled its story from different modules:

| Element | Phase 0 finding |
|---|---|
| Setup vs thesis | The setup differed from the thesis on 646 of 1,052 rows |
| Target | Came from a legacy range extreme |
| Trigger | Came from Wall-Break on 1,039 of 1,039 rows |
| Direction | The legacy direction was opposite to the thesis on 608 of 1,006 |
| Compression | Five definitions that agreed on 22% of tickers |
| Trigger layer | Read trend state instead of price events. VWAP and TRAP never fired |

**What is now true.** Each fact below has one owner and is carried unchanged from Discovery to the Lab card, checked by the tests in §4:

| Fact | Owner |
|---|---|
| Candidate, compression, direction, target | Discovery |
| Trigger | The thesis's own trigger level |
| Readiness | The thesis's own trigger events |
| Context | Vanguard (context only) |
| Rank | `domain/opportunity_rank.py` |
| Drop-off record | The drop-off audit (manifest-era) |

**What we learned about edge (§5).** Neither rule tested so far makes money on its own under mechanical rules:
- The setup-based lean path performs the same as random entries.
- Turn + cheap IV performs worse than random.
- The new GO rule (thesis trigger accepted) does not separate stock outcomes on four past Fridays.

So the pipeline is now **consistent**: every stage tells the same story. It is **not yet proven accurate**: no tested rule has shown an edge.

The untested part is the human timing layer, meaning your intraday entries and exits into the herd. In the replay of your own trades, that is where the gains appeared.

## 2. Decisions taken (ACK)

| Date | Decision | Where it applies |
|---|---|---|
| 7 Oct | CLAUDE.md rule 4 suspended for this redesign | All phases |
| 7 Oct | Discovery holds the CORE functions and direction; Vanguard adds context only | Phases 1–4 |
| 7 Oct | Daily-history backfill approved | Phase 0 data fix |
| 8 Oct | Top-down timeframe spine: 1mo > 1w > 1d sets the side; intraday labels the build-up, never decides | Phase 2, 3b |
| 8 Oct | Report ATM and 0.35 delta side by side; the test is answered as two questions | §5 |
| 8 Oct | GO = the thesis's own trigger accepted ("Thesis activated") | Phase 5.3 |
| 8 Oct | One rank by expectancy (E11b; supersedes E11a's hit-rate-first order) | Phase 5.5 (RC10) |
| 8 Oct | BLOCKED rows sink below all others ("Blocked sink"; keeps the 18 Sep rule) | Phase 5.5 |
| 8 Oct | MarketData spend approved; Options prices the governing thesis plus every other live thesis | Phase 5.4 |

## 3. Phase by phase

### Data fix (after Phase 0)

**Problem.** About 1,270 tickers had only about 92 daily bars in the canonical store, so Discovery dropped 1,221 of them.

**Fix.** An insert-only backfill from the full-history store.
- Receipt: `Enhancements/phase0/backfill_receipts/daily_history_backfill_execute_20261007T221941Z.json`
- Backup: `data/canonical/backups/historical_prices.pre_history_backfill_20261007T221941Z.sqlite`

**Result.** 19 of 20 sampled tickers now read full history.

### Phase 1: one candidate record, one compression episode

**Changes:**
- **`contracts/candidate_record.py`.** Family, proposed side, episode start, distance to trigger and levels status.
- **Compression.** One connected episode, whose box spans the episode, owned by the engine. Five producers become one.
- **Short history** is labelled INSUFFICIENT_DAILY_HISTORY, never INTRADAY_ONLY_UNTESTED.
- **Thesis target** = the governing candidate's own `Outcome_Level`.
- **Duplicate output keys removed.** No field is written twice.

**Acceptance** (replay of 120 tickers at 5 Oct):

| Check | Result |
|---|---|
| Directed tickers whose target, trigger and candidate come from one setup | 60 of 60 |
| Legacy targets published | 0 |
| Former "intraday only" drops that now survive | 33 of 40 |
| Former "no live setup" drops that now survive | 33 of 40 |
| Compression columns present | 106 of 106 |

### Phase 2: the thesis step owns direction

**Changes:**
- **`contracts/thesis_record.py`.** Every candidate gets a decision: adopted, refused, unresolved (with both conditional triggers) or closed, plus a reason.
- **The ticker's side** comes from the top-down spine.
- **The trigger layer no longer guesses direction.** Its trend and VWAP fallbacks are removed.

**Acceptance** (728 candidates, 106 tickers):

| Check | Result |
|---|---|
| Candidates with a recorded decision | 728 of 728 (403 adopted, 221 unresolved, 80 closed, 24 refused) |
| Unassigned tickers | 46 before, 15 now; all 15 are same-timeframe conflicts, stated |
| Tickers whose side changed from the legacy reading | 12 |
| Timeframe that set the side | Monthly 57, weekly 32, daily 17 |
| Directed tickers with one story | 91 of 91 |

### Phase 3: triggers are events against the thesis's own levels

**Changes.** `domain/structure_behaviour/trigger_events.py` detects events from bars against each thesis's own levels:
- break attempt, accepted break, failed break;
- retest held or failed;
- invalidated, outcome reached;
- VWAP reclaim or loss.

It reuses the engine's single acceptance rule.

**Acceptance** (728 candidates):

| Check | Result |
|---|---|
| Candidates with events measured | All |
| Engine "activated" vs detector "accepted break" | 75 of 75 agree; 384 of 384 "detected" have no accepted break |
| VWAP events | Now fire (183 last events). Phase 0: 0 |

### Phase 3b: intraday build-up (Morning, advisory)

**Change.** The same detector runs on 5-minute bars with the daily ATR, and labels the build-up ALIGNED, OPPOSED, NONE or NOT_MEASURED.

It is advisory only and never decides; intraday is untested (your rule of 5 Oct). With the spend now approved, the population can be widened in 5.4.

### Phase 4: Vanguard as context

| Fix | Defect | Result |
|---|---|---|
| RC01 | Timezone seam in the side-evidence date cut. Phase 0: `SIDE_BLOCK_ERROR` on 1,702 of 1,702 | The same session cut gives the same result for a date or a UTC timestamp |
| RC05 | Invented defaults (+5%, −3%, Kelly 0.1) | Removed. A missing value is NOT_MEASURED; the mean is shown beside the median |
| RC18 | State used the run clock | State uses the evidence session and completed bars |
| RC03 / RC19 | Live matching rules differed from the rules that built the v7 database. Parity before the fix: structure 75/200, trend 131/200, maturity 104/200 | Live matching dimensions now come from v7's own function, so parity holds by construction (tested). Your next run confirms it live |
| RC02 | Auction values shown as numbers when not measured | NOT_MEASURED (NaN), never a number |
| RC04 | Several history policies | One history policy with specific reasons, including HISTORY_BEHIND_EVIDENCE_SESSION |
| Context flags | — | `vanguard_context_flags` with authority CONTEXT_ONLY |
| Guard | — | A test asserts there is no hidden price gate |

### Phase 5: consumers carry the thesis

**5.1: thesis fields carried.** The thesis, spine, last-event, Vanguard-context and (later) intraday build-up fields are defined once. EOD, the Lab book, the Lab API and the book row copy them.

A gap found later is fixed: the book listed the columns but never copied the values.

**5.2: the trigger is the thesis's trigger.**
- EOD and the Lab set `trigger_price` from the thesis trigger level.
- Wall-Break is kept as `legacy_wbs_*` and is never used as the trigger.
- With no thesis trigger, the trigger stays missing and is stated.

**5.3: GO = the thesis's own trigger accepted.**
- **Owner.** Readiness is decided once, by Discovery's event step:
  - READY_FOR_HUMAN_REVIEW: an accepted break or held retest on its side, not since closed;
  - WAIT_TRIGGER;
  - CLOSED_INVALIDATED / CLOSED_RETEST_FAILED / CLOSED_OUTCOME_REACHED;
  - NOT_MEASURED / NOT_ADOPTED.
- **GO flag.** `trigger_go_eligible` mirrors the readiness. Morning, EOD, PSE and pre-trade follow it, and so do the Evening bucket and the dormant EDE. The old state-category rule is kept only as `legacy_state_go_eligible`.
- **Effect on 300 tickers from the 6 Oct run.** Old GO 146, new ready 87, both 47. 99 lose GO and 40 gain it.

**5.4: Options per thesis** (ACK: "Governing + all priced"; MarketData spend approved).
- **Per-ticker contract:** stays the governing thesis's.
- **Packet:** routes each candidate by its thesis decision. An adopted thesis is priced on its side. An unresolved thesis with both conditional boundaries is priced on both sides: CALL above the bull boundary with the bear boundary as invalidation, and PUT the mirror. No target is invented.
- **No cap:** the 2,000-candidate cap is removed (`max_candidates_per_run: null`). On 6 Oct it deferred 16,500 of 18,500.
- **Chains:** a ticker with any adopted or conditional thesis has its one chain acquired and recorded by the per-ticker step, even without a governed side. It gets no ticker contract. Provider finality is reconciled for these tickers too.
- **Scope:** the tier filter and the legacy precor-WAIT filter are removed, and so is Gate 1 (WAIT intent). The intent stays visible.
- **Card:** the lane runs before the Options rows are saved. Each row carries `thesis_alternatives_count`, `_tested` and `_json`, and the card shows "Other theses priced", labelled as alternatives.
- **Intraday build-up:** the Morning build-up now also covers every adopted thesis (accepted or waiting), not only GO rows. It stays advisory.
- **Cost:** chains cost 1 credit each (cached mode), so at most about 1,700 a run against 100,000 a day.
- **Runtime:** the 6 Oct lane priced about 1,050 candidates in 5.5 minutes (about 0.3 s each). Pricing every thesis is about 8,000–9,000 evaluations, roughly **+40–45 minutes** on the Options stage (56 minutes on 6 Oct). ACK 8 Oct 2026: do not defer intraday theses; if today's run is too long, the deferral is decided before the session on Monday 12 Oct. **Corrected estimate (live counts, failed run 20261008_141534):** 13,172 adopted + 7,053 conditional theses (priced on both sides) = 27,278 lane evaluations, about +2.3 h on the Options stage; ACK: "run it as built tonight".

**5.5: four changes.**

| Change | What it does | Effect on the 6 Oct run |
|---|---|---|
| Drop-off audit (RC12) | The canonical manifest is the intake stage. The label PENDING_PACKAGE_BUILD, which assumed packages (AVS-PKG-002: "rename in P5"), is gone. Every row has a stage, a reason, a reason class and its thesis | No rows pending or unknown (Phase 0: 1,814 pending). 51 survived, 111 refused by the manifest with its own reason, 66 outside Options scope, 598 stopped in Options |
| Morning repair stays inside the thesis | An alternative on the wrong side is skipped and labelled. The thesis fields are never edited | 0 of 7,546 alternatives were off-side in the last four runs, so this pins the rule where the swap is decided |
| Lab card | "Why now" shows the thesis trigger level, its readiness, the deciding event and the governing setup. It also shows the top timeframe with its conflict count and the intraday build-up (advisory). Vanguard's history flags appear under context, marked context only. The old trigger type is shown as "state reading, not the trigger" | — |
| One rank (RC10) | `domain/opportunity_rank.py` orders the Lab book, the Lab table and the trade summary. Blocked rows come last; then lane, then readiness, then expected option multiple (holdout hit rate × value at the median time − 1), evidence count and ticker. Two other orders were removed: the retired priority score in the book, and a third re-rank in the Lab server | 329 rows can be scored, 53 above break-even. 3 of the old top 20 remain in the new top 20. The expectancy is a conditional estimate until the outcome scorer calibrates it |

## 4. Phase 0 defect register: status

| Defect | Status |
|---|---|
| P0-01 Mixed story | Fixed. Side, trigger, target and invalidation come from one candidate (Phases 1, 2, 5); every live thesis is priced on its own levels (5.4) |
| P0-02 Five compression producers | Fixed (Phase 1) |
| P0-03 Five direction producers | Fixed (Phase 2) |
| P0-04 Five target producers | Fixed (Phase 1) |
| P0-05 State-based trigger layer | Fixed: events (Phase 3); GO from events (5.3) |
| P0-06 Silent overwrites | Fixed. Guard test: no decision-path field is written twice |
| P0-07 Wrong short-history label | Fixed (Phase 1) and data backfilled |
| P0-08 Vetoes and the resource cap | Fixed. Every row has a recorded disposition (5.5); the cap and the tier/WAIT scope gate are removed (5.4) |
| P0-09 Timezone seam | Fixed (Phase 4, RC01) |
| P0-10 Universe hygiene | Open (backlog) |
| P0-11 Two history stores | Data aligned by the backfill; the actuarial builder's own reader is a cleanup item |

## 5. Evidence on edge (read before relying on the pipeline)

**Universe test** (pre-registered; holdout; Friday entry at the ask, exit at the bid; per-trade return on premium). Details: `Enhancements/lean_path_test/TWO_ANSWERS_20261008.md`.

| Question | ATM | 0.35 delta | Against random |
|---|---|---|---|
| Setup-based lean path | −35.8% (n 12,023) | −38.7% | Same as random: +0.1 pts, CI −2.7 to +2.9 |
| Turn + cheap IV | −41.8% (n 4,883) | −46.3% | Worse: −6.3 pts, CI −9.8 to −3.3. Cheap IV did 10 pts worse than normal IV |

**GO readiness replay** (`Enhancements/phase5/p53_go_set_change.json`). Stock move on the thesis side over 10 sessions, four past Fridays:

| Group | n | Mean | Hit |
|---|---|---|---|
| Ready | 148 | −1.17% | 50% |
| Waiting | 284 | −0.32% | 48% |

No separation.

**Reading.** These results agree with the 7 Oct direction research: no price-only rule predicts direction or size on this universe. The fixes make the pipeline say one consistent, auditable thing; they do not by themselves create edge. The remaining candidates for the edge are:
1. **Your intraday timing.** Untestable on Friday snapshots.
2. **Options and flow information:** implied versus realised volatility, events, positioning. This is the next research line agreed on 7 Oct.
3. **Exits into the herd.** In the replay of your trades, 83% of the losers were up at least 25% at some point intraday.

## 6. Tests and regression

**New business-rule tests.** Each was written first and seen to fail.

| Phase | Tests |
|---|---|
| 1 | `test_p1_*`: 5 files |
| 2 | `test_p2_thesis_step` |
| 3 | `test_p3_*`: 2 files |
| 3b | `test_p3b_intraday_buildup` |
| 4 | `test_p4_*`: 8 files |
| 5 | `test_p5_*`: 9 files (thesis fields carried, trigger, GO readiness, Options per thesis, intraday build-up population, drop-off dispositions, Morning repair, Lab card, one ranking owner) |

One process note: in RC03, the implementation was written in the same step as its tests.

**Regression.** Run one file per process.

| Run | Result |
|---|---|
| Main | 174 files plus the rebuild suite (169 passed) |
| Targeted 5.2 | 44 files |
| Targeted 5.3 | 24 files |
| Targeted 5.5 | 140 files |
| Morning / MSI | 20 files |

Existing tests that pinned the old rules were updated on purpose, each marked with a comment naming the decision. Two failures remain:
- **`test_avs_int001_stage0`.** Two new production modules (`contracts/thesis_record.py`, `domain/opportunity_rank.py`) are not yet in git. This resolves when they are committed.
- **`test_b1_shadow_valuer_forecast_source`.** It fails because of the separate, uncommitted 7 Oct runway change (RW, "C with B fallback"). The fixture has no runway evidence, so the label is now NO_RUNWAY_ESTIMATE. The owner of that change should update the fixture.

One golden test also needed the uncommitted 7 Oct direction-validation fields registered. Please confirm that work is yours.

## 7. Next

1. **Phase 5.4 is built** (§3). Watch the Options stage time on your run (estimate +40–45 minutes).
2. **Your acceptance run.** `--plan-only` first, then Evening and Morning. Check: mismatch counts at 0, every card shows its candidate ID and last event, and the drop-off audit has no pending or unknown rows.
3. **Commit review with you.** The changed files include the other session's uncommitted 6–7 Oct work. Each file's changes will be listed for your confirmation, and files are staged by name.
4. **Phase 6.**
   - The turn family is **not** promoted: it failed the universe test.
   - Compression resolution rules.
   - The intraday build-up test.
   - Contributor weights measured.
   - Exit research.
   - Retirement and tidy with your approval, including UNIVERSE_CONFIG and the `avshunter_db_update` duplicate.
5. **Backlog:**
   - Phantom RC06/07/08/16;
   - payload size (RC13);
   - RC14, RC17;
   - universe hygiene (278 dead symbols, stale flags, mixed-date crash);
   - Crabel duration evidence rebuild;
   - the meaning of `quote_as_of`.
