# Discovery and Vanguard: signal assessment and fix design (12 Oct 2026)

Status: ASSESSMENT + DESIGN FOR ACK APPROVAL. No code changes until approved.
Governing documents: `Enhancements/decision_map/DISCOVERY_VANGUARD_REDESIGN_20261007.md` (P1-P9, phases 0-6, fact
ownership), `Enhancements/phase5/PHASE1_5_REPORT_20261008.md` (phases 1-5 built), `Enhancements/phase6/
PH6_INTERPRETATION_20261009.md` (measured edge evidence), ACK's trade-quality register (D2, D3, D4a, D5, D6, D13, D16,
D19, T2, N2; pasted 11 Oct). Evidence: `dv_audit_20261010.py/.json` on the live Evening 20261010_191314 (read-only).

## 1. What Discovery and Vanguard are for

Discovery screens the universe for the characteristics of a trade and publishes one story per ticker: side, trigger,
invalidation, target, timeframe, hold, readiness from events, and the evidence for and against. Vanguard adds history
and market-structure context and contradictions, and never changes the story. Rank orders; nothing is vetoed before the
human (P2).

Measured evidence on what separates winners (must shape the screen, never be assumed):
- no price-only rule predicts direction or size on this universe (7 Oct research; 8 Oct universe test: setup lean path =
  random; turn + cheap IV worse than random, not promoted);
- Ready vs Waiting showed no separation on four past Fridays (p53);
- cheap volatility passes (IV / HAR-RV forecast: CHEAP - RICH +16.9 pts on setup trades, +11.8 on random entries);
- the entry spread dominates outcomes (exploratory; pre-registration pending).

## 2. What the 10 Oct Evening shows (2,936 Discovery tickers; 2,792 book rows)

| Check | Result | Verdict |
|---|---|---|
| P1 one story: side, trigger, target equal the governing candidate's own (Discovery) | 2,496 / 2,496 each | Holds |
| P1 carried to the book: side and trigger | 2,371 / 2,371 | Holds |
| P1 carried to the book: target | 2,168 / 2,371 - **203 rows have `target_price` blank (UNRESOLVED) while `structural_target` holds the thesis target**; none on the wrong side of price | **Defect (carry)** |
| P3 direction: tickers with no side | 440 (15%); **417 = SAME_TIMEFRAME_CONFLICT** (an adopted bull and an adopted bear on the same timeframe). Of those, **134 have exactly one side already activated by an event** (73 bear, 61 bull), 4 both, 279 neither. None of the 440 gets a contract | **Defect: screening loss** |
| P3/6.3 conditional theses | 390 of the 440 tickers have a conditional bull or bear trigger in the candidate ledger, but the ticker row and card carry neither | **Gap** |
| D2 label says what was measured | `direction_governance_status` CONFIRMED and `direction_resolution_path` DIRECTION_CONFIRMED on 2,371 rows; `direction_resolution_evidence_count` 0 on every row (the legacy resolver no longer runs; the thesis spine sets the side) | **Defect (R6 label)** |
| P4 / section 11 retired producers | Legacy Wyckoff `wyckoff_mode` / `phase` / `wyckoff_phase_bucket`, composite, Crabel score and the trigger-layer state categories (`trigger_primary` NONE 1,470, `trigger_quality`) are still computed and still read by decisions downstream: Options OIS phase points and volume confirmation, trap engine, trigger T3 -> EOD status / tier / fit / sort, EOD `classify_tier` (item 11 stations 2-4, open) | **Defect: D3, D6, D19** |
| D3 | legacy mode opposes the thesis side on 1,343 / 2,371 (57%) | Follows from the row above |
| D6 | all 488 GO rows carry the thesis trigger level and an accepted event (break accepted 230, retest held 164, VWAP 94); the "no trigger" reading is the legacy category NONE | Label defect, not a GO defect |
| D19 | book `tier` is EOD's legacy composite tier: tier A holds 589 WAIT_TRIGGER rows; 421 WATCH are the unresolved tickers | **Defect** (item 11 station 4) |
| P6 contributors | Only `distance_to_trigger_atr` is built (27,028 measured, 8,225 NOT_MEASURED:NO_TRIGGER_LEVEL). Designed but absent: pre-trigger momentum, relative strength, volume participation, IV vs own history, option activity. The one contributor that passed (cheap vol) is not in Discovery or the rank | **Gap** |
| Vanguard as context | CONTEXT_ONLY on every row; `edge_direction` retired; contradiction flags: HISTORY_AGAINST_THESIS_SIDE 675 (24%), THIN_HISTORY 55; auction NOT_EVALUATED 805 (labelled); actuarial source V6_DB on all; never changes the side | Holds. The 675 contradictions must reach the card |
| Vanguard matching key | still the legacy `wyckoff_phase_bucket` (decision 4: kept until the actuarial DB is rebuilt on thesis states), not yet labelled LEGACY_STATE_KEY | **Label gap** |

## 3. Fix design (each test-first, replayed on 20261010_191314, then accepted on ACK's next run)

| ID | Closes | Fix | Owner | Replay expectation |
|---|---|---|---|---|
| DV-1 | P3 screening loss (417) | **Events resolve a same-timeframe conflict.** When both sides are adopted on one timeframe and exactly one side's trigger is accepted (READY, not since invalidated), that side governs; the other stays visible as the counter-case (`thesis__counter_side`, its trigger and invalidation). Neither or both activated: UNRESOLVED, carrying both conditional triggers. No new score; P8 events, not states | `contracts/thesis_record` spine (`SPINE_RULE`) | 134 tickers gain a side (73 BEAR, 61 BULL); 283 stay UNRESOLVED with both triggers |
| DV-2 | 6.3 gap (390) | UNRESOLVED tickers carry `thesis__conditional_bull_trigger` / `_bear_trigger` (and invalidations) on the row; card shows "BULL if accepted above X; BEAR if accepted below Y". Pricing both conditional sides in Options is a consumer step (section 10) - proposed next, not in this build | Discovery thesis fields; card | 390 rows show both conditions |
| DV-3 | D2 | Direction labels say what happened: `direction_governance_status` THESIS_ADOPTED / NOT_RESOLVED; `direction_resolution_path` THESIS_SPINE_ADOPTED; evidence count = the thesis's adopted-candidate count with basis. Every reader of the old CONFIRMED value is found and moved first (test) | `contracts/direction_governance.py` | 0 CONFIRMED with zero evidence |
| DV-4 | P1 carry (203) | Trace the stage that blanks `target_price` while the thesis target exists; the book's target is the thesis `Outcome_Level` everywhere (one owner) | stage found by the failing test | 2,371 / 2,371 targets equal the thesis |
| DV-5 | D3, D6, D19 (item 11 stations 2-4) | Legacy Wyckoff phase / mode and trigger state categories leave decisions: Options OIS phase points and volume confirmation by phase -> thesis event / state; trap engine CHASE / EARLY_PROBE -> thesis readiness and event age; trigger T3 and `trigger_quality` no longer feed EOD status / tier / fit / sort; EOD `tier` = the thesis tier and E11b rank group. Legacy values kept as `legacy_*` (audit), per-producer switches for rollback | Options, trap engine, trigger layer, EOD | D19 disagreement 0 by construction; D3/D6 legacy fields marked legacy and off the card |
| DV-6 | Vanguard context | HISTORY_AGAINST_THESIS_SIDE / THIN_HISTORY shown on the card as contradictions; matching key labelled LEGACY_STATE_KEY (decision 4) | card; Vanguard | 675 cards show the contradiction |
| DV-7 | P6 contributors | Build the designed contributors as measured, labelled fields with zero rank weight (pre-trigger momentum, relative strength vs sector, volume participation, IV vs own history), each MEASURED / NOT_MEASURED with reason. Weight only after a pre-registered test; the cheap-vol and spread rank inputs follow Phase 6 route 3 with ACK's approval | Discovery contributors | Fields filled with status; rank unchanged |

Order: DV-3, DV-4 (accuracy of what is already shown), DV-1, DV-2 (screening loss), DV-6, DV-5 (station by station,
each with its own replay), DV-7.

## 4. Not in this layer (stay on the register, owners elsewhere)

D4a (geometry: 379 lane C GO rows NOT_MEASURED - decision 1), D13 (GARCH windows), D16 (IV history depth; backfill from
Phantom proposed), T2 (assessment id), contract expiry before the median move (883), Evening macro fields empty,
D17 (P3). D5 "pooled probability": the definition is needed - no pooled probability field is found on this run.

## 5. Decisions for ACK

1. DV-1: events resolve a same-timeframe conflict (the activated side governs; the other is the counter-case).
2. DV-3: the new direction labels.
3. DV-5: proceed station by station under item 11 (each station's replay shown before its switch is turned on).
4. DV-7: contributors at zero weight until measured.
