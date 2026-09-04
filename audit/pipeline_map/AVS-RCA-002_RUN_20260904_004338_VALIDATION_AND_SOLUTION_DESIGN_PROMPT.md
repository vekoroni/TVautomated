# AVS-RCA-002 — Validate run 20260904_004338, review the pipeline, and design the fix for the remaining gaps

**Issued:** 2026-09-04
**Agent:** Claude Code — read-only on production code, run data and backups; writes only under the output root
**Trigger:** first Evening run after the AVS-SD-002 Rev 1.1 Phase 0–8 build. Technical status PASS, semantic validation FAIL.
**Run under review:** `data\output\runs\20260904_004338\`
**Previous baseline run:** `data\output\runs\20260902_232526\` (pre-build)
**Repository:** `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence`
**Output root:** `audit\pipeline_map\AVS-RCA-002\`
**Solution design to produce:** `audit\pipeline_map\AVS-SD-003_GAP_ELIMINATION_20260904.md`

---

## 1. What happened and what you are being asked to do

Yesterday's build (AVS-SD-002 v1.0 + Rev 1.1, executed against AVS-AR-003) closed Phases 0–8 offline with P0-01 to P0-07 marked CLOSED OFFLINE and every dynamic feature flag left disabled. The legacy `--evening` command was then run overnight. It completed, reconciled its populations, used MarketData throughout, and produced a directionally balanced book — but it also reproduced the two headline P0 defects the build was meant to remove (Market Profile fail-open, incomplete invalidation geometry), lost quote lineage between Options and the Lab, and made 1,261 physical option requests with zero cache hits.

The operator's assessment of the run is reproduced in §3. Treat it as a set of **claims to verify**, not as established fact — including its diagnosis that the profile stage is gated by `AVSHUNTER_DYNAMIC_THESIS_ENABLED`.

Three deliverables, in order:

- **Part A — Validate the run.** Confirm or refute every number and every attribution in §3 from the run artefacts. Establish which failures are the *new code not running* (flag off), which are *new code running and wrong*, which are *old defects the build never touched*, and which are *audit/reporting defects* rather than pipeline defects.
- **Part B — Review the pipeline as it actually executed.** Trace the legacy Evening path that ran, stage by stage, against the design's target sequence, and explain precisely why each offline-closed P0 reappeared in production.
- **Part C — Solution design AVS-SD-003.** A build-ready design that eliminates every confirmed gap, with the flag-policy decision made explicit, replayable acceptance gates against this run, and an implementation sequence. It must not re-open the accepted architecture; it closes the distance between "implemented behind flags" and "firing in production".

You are analysing and designing. You are not implementing.

---

## 2. Hard constraints

- **Never execute the pipeline.** No `intelligent_orchestrator.py` with any switch, no `morning_gate.py`, no stage scripts, no Lab server, no Interpreter commands, no provider calls. Warm-cache measurement for G19 is a run ACK will produce; you specify it, you do not run it.
- **Production code, run data and backups are read-only.** Write only under the output root. Defects are filed and designed against, never patched.
- **Never set a feature flag.** Where you need to know flag-on behaviour, read the code and cite the branch.
- **Runtime:** `C:\Python314\python.exe` for any read-only analysis script you write under the output root (pandas/pyarrow are available there). Any script you write must open run artefacts read-only and must not import `intelligent_orchestrator`, `morning_gate` or any stage module that performs I/O on import.
- **Three-direction discipline.** Every count you report and every rule you design is stated for CALL, PUT and OTHER (STRANGLE/UNRESOLVED/null) separately.
- **Evidence standard.** Every claim in your reports cites either a run artefact path plus the exact field/row filter that produced the number, or a source file plus line range. A closure report, claim sheet or the §3 text is never evidence.

---

## 3. Operator assessment of run 20260904_004338 (claims under test)

**Reported as working**
- Discovery reconciled exactly: 3,320 = 1,601 selected + 1,719 excluded.
- Options used MarketData: 1,261 fetches, zero Polygon fallbacks.
- Options direction population: 792 CALL, 472 PUT, 141 STRANGLE, 49 unresolved. Lab population: 164 CALL, 92 PUT.
- All 256 Lab candidates carry governed hold periods: 194 at 1–5 days, 62 at 6–10 days.
- Macro advisory for all 256 rows.
- Lab population reconciles: 256 in, 256 out, zero duplicate trade IDs.
- Morning execution permission withheld (correct pre-Morning-Gate).

**Reported as blocking**
1. Completed-session Market Profile did not run. No `market_profile/completed_profile_summary` artefact. All 1,551 Vanguard rows: `profile_type=INSUFFICIENT_DATA`, POC/VAH/VAL = 0, migration `SIDEWAYS`; 1,068 still `auction_state=ALIGNED`. Operator attributes this to the completed-profile stage being gated by `AVSHUNTER_DYNAMIC_THESIS_ENABLED` in `intelligent_orchestrator.py`, distinct from the standard MSI configuration that was enabled.
2. Authoritative invalidation incomplete: 173 directional Options rows with missing stop; 24 of 256 Lab candidates without invalidation price; 13 of those still granted `EOD_CANDIDATE_ONLY`; 36 PUT rows raised `float - NoneType` in `compute_trade_economics()` on a missing structural target and were stood down.
3. Quote lineage lost before the Lab: contract bid size, ask size, selected quote timestamp and execution-viability state all missing 256/256, although Options captured bid/ask sizes and the Morning candidate file carries viability states.
4. Seven selected contracts (BAND, AMAT, WDC, CRDO, KLAC, NVTS, KTOS) lack a comparable monetisability evaluation.
5. Performance: ~4 hours, 2.65 GB, 1,261 physical option requests, zero cache hits. G19 open until a warm-cache run shows reuse.

**Reported as a probable audit defect**
- The UAT `FAIL` treats an intentionally empty missed-opportunity shadow book as missing data.

---

## 4. Inputs

**Run artefacts** — `data\output\runs\20260904_004338\`: `run_meta.json`, `final_run_manifest.json`, the truth packet, every stage CSV (discovery, vanguard, options, EIL, execution, EOD candidate, morning candidates), `intelligence_lab\` governed book (`lab_signal_book_v2`/v3), request ledger rows for this run in `data\canonical\control_plane.sqlite`, the UAT/audit report that produced `FAIL`, and the run log. Also the same set for `20260902_232526` for before/after comparison.

**Specification (accepted)** — `audit\pipeline_map\AVS-SD-002_DATA_INTELLIGENCE_AND_MARKET_PROFILE_LIFECYCLE_20260903.md` (§§4–8, §12–14, §16, §21), `AVS-SD-002_REV1_1_DYNAMIC_SESSION_ORCHESTRATION_20260903.md` (§§8–11, §17, §19, §22), `AVS-AR-003_AS_IS_PIPELINE_SHIPPABILITY_REVIEW_20260903.md` (§§7–12), `AVS-AR-003_GAP_REGISTER_20260903.csv`.

**Build claims** — `AVS-SD-002_PHASE{0..8}_CLOSURE_20260903.md`, the `_CLAIM.json` files, `AVS-SD-002_PHASE8_EVIDENCE_20260903.json`, `AVS-SD-002_PHASE8_ASSESSMENT_20260903.json`, `AVS-AR-003_P0_RECERTIFICATION_20260903.md`.

**Tester prompt (context only)** — `AVS-TST-SD-002-001_TEST_PROMPT_20260903.md`, in particular its §5A fix register F01–F37. If AVS-TST-SD-002-001 outputs exist under `audit\pipeline_map\AVS-TST-SD-002-001\`, read them; where its findings overlap yours, cite rather than repeat.

**Code** — `intelligent_orchestrator.py` (flag reads and the `--evening` branch), `contracts\dynamic_session_contract.py`, `contracts\dynamic_session_authority_v1.json`, `vanguard\layer1_auction\auction_synthesizer.py`, `vanguard\integration\orchestrator_adapter.py`, `orchestrator\dynamic_thesis.py`, the completed-profile stage module, `eod_candidate_engine.py`, `scripts\avshunter_options_intelligence.py` (`compute_trade_economics`, contract selection), `contracts\selected_contract_economics.py`, `contracts\lab_control.py`, `contracts\lab_evidence_overlay.py`, `contracts\interpreter_handoff_materializer.py`, `morning_handoff_finalizer.py`, `canonical_data\` (gateway, registry, request ledger, option-chain resolver), `intelligence-lab\intelligence_lab.py`, and the UAT/audit report generator.

---

## 5. Part A — Validate the run

Produce `A_run_validation.md` and `A_counts.csv`. For every bullet in §3, one row: claim, your recomputed value, artefact path, filter used, status (`CONFIRMED` / `REFUTED` / `PARTIAL` / `NOT_DETERMINABLE`), and classification of any failure as one of:

- `FLAG_OFF` — the new code that would prevent it exists but was not on the executed path;
- `NEW_CODE_DEFECT` — new code ran and produced the wrong result;
- `LEGACY_UNTOUCHED` — the build did not change this path at all;
- `AUDIT_DEFECT` — the pipeline is right and the report is wrong;
- `EXPECTED_COLD` — correct behaviour for a first run against an empty cache.

Specific probes:

**A1 Market Profile.** Confirm the absence of the completed-profile artefact and the 1,551 / 1,068 counts, split by direction. Then answer, with line citations, three separate questions the operator's diagnosis conflates: (a) which flag gates the *completed-profile acquisition stage* in the `--evening` branch; (b) which flag, if any, gates the *Vanguard fail-open protection* (unusable profile ⇒ `NOT_EVALUATED`, `ready_to_trade=False`, uplift 0) in `auction_synthesizer.py`; (c) whether AVS-SD-002 §21 ("the first production change must be the Vanguard fail-open protection") and AR-003 Wave 3's exit gate ("no daily-only `ALIGNED`") were satisfied by a flag-gated implementation. Identify the full set of eight flags from the contract module — `AVSHUNTER_DYNAMIC_THESIS_ENABLED` appears to be the eighth that the closures never named — and map each to the exact orchestrator branch it controls. State what would have happened had only `AVSHUNTER_COMPLETED_PROFILE_ENABLED` been set, and had only `AVSHUNTER_DYNAMIC_THESIS_ENABLED` been set. Quantify Layer 2's contribution: how many of the 1,068 `ALIGNED` rows received the +25 alignment uplift, and how many of those reached the 256-row Lab book.

**A2 Invalidation geometry.** Recompute 173 / 24 / 13 / 36 from the Options, EOD and Lab artefacts with the filters stated. For the 13 `EOD_CANDIDATE_ONLY` rows without invalidation, cite the `eod_candidate_engine.py` branch that granted the status and state whether the Phase 2 frozen-thesis guard (F13) or the Phase 5 "explicit defer on missing decision-critical data" (P0-07 recertification) was on the executed path. For the 36 `float - NoneType` PUT rows: locate the exact expression in `compute_trade_economics()`, determine why the structural target was `None` for PUTs specifically (three-direction check: does the CALL branch have the same exposure with a different symptom?), and confirm whether "safely stood down" means a governed `UNRESOLVED_EXCEPTION`/defer record or a swallowed exception with a default status.

**A3 Quote lineage.** Trace the four missing fields (bid size, ask size, selected quote timestamp, execution-viability state) from where Options writes them → EOD candidate engine → Morning candidate file → `lab_control.py` allow-list / `lab_evidence_overlay.py` / materializer → Lab book. Identify the exact boundary where each is dropped and whether it is an allow-list omission, a rename (e.g. `underlying_nbbo_*` vs `l2_*`, `ms_*`), or a materializer that reads the wrong source (the Phase 5 `live_map`-only defect, F29, had this shape). Confirm that the fields exist upstream with non-null values for at least the 256 Lab tickers before concluding it is a handoff defect.

**A4 Monetisability.** For BAND, AMAT, WDC, CRDO, KLAC, NVTS, KTOS: what does `selected_contract_economics.py` record — missing quote, identity mismatch, missing multiplier, missing target? Is the absence disclosed as a named state in the Lab row, or does the row present as if evaluated? Per AR-003 §7.10 the evaluation is advisory; the defect, if any, is disclosure.

**A5 Performance and cache.** From the request ledger: physical calls by dataset type, cache exact hits, partial hits, and whether any of the 1,261 option-chain requests had an exact-identity match already in `control_plane.sqlite` from `20260902_232526` (same ticker, same source session, same scope). Zero hits on a cold cache is `EXPECTED_COLD`; zero hits where an identical dataset already existed is a defect. Measure runtime per stage from the log and size per stage directory; compare to `20260902_232526` (2.47 GB, 1,569 files) and attribute the growth.

**A6 The audit defect.** Locate the UAT/audit rule that scored the empty missed-opportunity shadow book as missing data. State whether the shadow book was intentionally empty (cite the writer and its condition) and whether the rule should distinguish `EMPTY_BY_DESIGN` from `MISSING`. Then re-score the run with that rule corrected and state whether `FAIL` still stands on the genuine findings alone (it will, if A1–A3 confirm).

**A7 The positives.** Confirm the seven "worked" bullets with the same rigour; they are the regression baseline the design must protect. In particular confirm direction lineage: does every one of the 164 CALL / 92 PUT Lab rows carry a governed direction decision ID that matches the Options row, and where did the 141 STRANGLE and 49 unresolved rows go?

---

## 6. Part B — Review the pipeline as executed

Produce `B_executed_path_review.md`.

**B1 Executed stage graph.** From the run log and `run_meta.json`, list the stages that actually ran, in order, with start/end times, input and output row counts, and the flag state each branch consulted. Draw it against AR-003 §5.1 (as-is) and §5.2 (target). Mark every stage that exists in code but was skipped because of a flag.

**B2 Why each offline-closed P0 reappeared.** For P0-02, P0-04, P0-07 and the lineage loss (P1-03/P1-04 family), state in one paragraph each whether the recertification was (a) correct for the code path it tested but that path is not the production path, (b) tested a contract without testing the writer that populates it, or (c) wrong. This is the central finding of the review: the two-level closure standard requires a run artefact showing the fix firing, and these were closed without one. Say so plainly and name the closure documents.

**B3 Flag topology.** Table of all eight flags: name, default, the orchestrator/Morning/Lab/Interpreter branches each controls, what functionality is unreachable while it is off, and its dependency on other flags. Identify any flag that gates a *fail-closed protection* rather than a *new capability* — those are the design's mistake, because a protection that is off by default is not a protection.

**B4 Residual legacy paths.** List every provider call, default substitution and post-stage patch that executed on this run and that AR-003 §6.2 / §7 said must not be on the production path. Compare to `20260902_232526` to show what the build removed and what it did not.

---

## 7. Part C — Solution design AVS-SD-003

Write `AVS-SD-003_GAP_ELIMINATION_20260904.md` in the same form as AVS-SD-002 (executive decision → goals/non-goals → current-state evidence → required changes → test design → acceptance gates → implementation sequence → backup/rollback → definition of done). It must be build-ready for Codex or Claude Code implementation with independent Claude Code testing. Required content:

**C1 Gap register.** One row per confirmed gap from Part A (expect G-01 profile stage not executed; G-02 Vanguard fail-open still live; G-03 missing stop / invalidation on directional rows; G-04 `EOD_CANDIDATE_ONLY` granted without invalidation; G-05 PUT `compute_trade_economics` `None` target; G-06 quote-lineage drop at the Lab boundary; G-07 monetisability non-evaluation undisclosed; G-08 zero cache reuse; G-09 UAT empty-shadow-book rule; plus any you found). Each with: root cause (file:line), classification from Part A, design reference it violates, and severity.

**C2 Flag policy decision — the first design decision.** Recommend, with reasons, one of:
- **Option 1 — Unflag the protections.** Vanguard fail-closed (unusable profile ⇒ `NOT_EVALUATED`), missing-invalidation defer, PUT/CALL target-null guard, lineage allow-list and monetisability disclosure become unconditional on the legacy `--evening` path. Only *new acquisition* (completed-profile stage, dynamic thesis/validation, dispatcher, ledger, dynamic views) stays flag-gated.
- **Option 2 — Enable the completed-profile stage and dynamic thesis together** on the legacy path via `AVSHUNTER_DYNAMIC_THESIS_ENABLED` + `AVSHUNTER_COMPLETED_PROFILE_ENABLED`, keeping protections behind them.
- **Option 3 — Split `AVSHUNTER_DYNAMIC_THESIS_ENABLED`** so profile acquisition and the thesis-builder rewrite are independently enableable, then Option 1 for the protections.
State the consequence of each for tomorrow's run: with the recommended option and flags as you specify them, what does Vanguard emit for the 1,551 rows (expected: `NOT_EVALUATED` for all, `ready_to_trade=False`, zero alignment uplift, until a completed profile actually exists), and what happens to the 256-row Lab book. AVS-SD-002 §21 already ordered this: "the first production change must be the Vanguard fail-open protection." The design must honour it or explicitly overrule it with ACK's sign-off as a named decision.

**C3 Per-gap change specification.** For each gap: the exact module and function to change, the contract it must satisfy (quote the AVS-SD-002/AR-003 clause), the three-direction behaviour, the failure mode it replaces, and the unit/contract test that proves it. For G-06 specify the allow-listed field set at each boundary as a table (field, producer, consumer, boundary, rename if any). For G-05 specify the governed exception record (`UNRESOLVED_EXCEPTION` with reason code) rather than a stand-down default. For G-08 specify the cache identity the option-chain resolver must match on for a warm second run, the expected physical-request count on a same-session rerun (zero for exact hits), and the ledger reconciliation `physical = ledger PROVIDER_FETCH rows`.

**C4 Replayable acceptance gates against run 20260904_004338.** Numeric gates that can be checked by replaying this run's inputs offline where possible and by the next live run otherwise:
- zero Vanguard rows with `profile_type=INSUFFICIENT_DATA` and `auction_state=ALIGNED`;
- zero rows with missing POC represented as `0.0` (null only);
- zero `EOD_CANDIDATE_ONLY` rows without invalidation price;
- zero unhandled `TypeError` in economics; every stood-down row carries a reason code;
- 256/256 Lab rows with bid size, ask size, quote timestamp and viability state (or an explicit named absence state);
- 7/7 undisclosed monetisability rows now disclosed;
- warm rerun: option-chain physical requests = 0 for unchanged identities, ledger reconciles;
- direction, hold and reconciliation positives from A7 unchanged (regression gate);
- UAT scores `EMPTY_BY_DESIGN` distinctly from `MISSING`.
Assign each gate to G02–G20 of Rev 1.1 §19 where it maps, and say which live gates (G18A, G19) the next Evening run can close.

**C5 Test additions.** For each gate, the test file and case to add; where an existing test passed while the defect was live (the P0-02 and P0-07 cases), say what the test asserted instead of the real property and how it must change. This is the second-level closure the build skipped.

**C6 Implementation sequence and ownership.** Ordered, with the four-agent model from AVS-SD-002 §17 (one integration lead, three bounded specialists), file ownership per agent, no concurrent edits to `intelligent_orchestrator.py`, `morning_gate.py`, `contracts/lab_control.py` or shared schemas. First item must be the change that makes tomorrow's Evening run fail closed on unusable profiles. Estimate which gaps can close in one cycle and which need the profile stage to be live.

**C7 Backup, rollback, promotion.** Per-change backups in the Phase 0 pattern; rollback trigger per gap; and the sequence of flag enablements (if any) with the observation each requires before the next.

**C8 Definition of done.** Restated in run-artefact terms: nothing is done until run `N+1` shows it firing and the release assessor records a hash-bound artefact for it.

---

## 8. Deliverables

```
audit\pipeline_map\AVS-RCA-002\
  environment.json                 (interpreter, scripts run, artefact hashes)
  A_run_validation.md
  A_counts.csv
  A_scripts\                       (read-only analysis scripts you wrote)
  B_executed_path_review.md
  B_flag_topology.csv
audit\pipeline_map\AVS-SD-003_GAP_ELIMINATION_20260904.md
```

Parts A and B are prerequisites for C. Do not draft any design section until the gap it addresses is `CONFIRMED` in `A_counts.csv` with an artefact citation. If a §3 claim is `REFUTED`, say so in Part A and omit it from the design; do not design against an assumption.

Where you disagree with the operator's diagnosis — including the flag attribution in finding 1 — state the disagreement and the evidence. Where a finding needs a run you do not have (the warm-cache rerun), specify the run precisely (command, flags, expected ledger deltas) so ACK can produce it, and mark the gate `AWAITING_RUN`.

Begin with A1.
