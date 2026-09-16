No NORMAL_COMPLETED_SESSION run exists.

# Acceptance verdict — AVS-UAT-FIX-002 (all stages, HEAD `cc509cb`)

## Stage verdict: **REJECT**

§5 applies BASELINE — NOT YET IMPLEMENTED only if most requirements return NOT IMPLEMENTED. Here only **11 of 56** do; **36 of 56 are OPEN** (implemented but failing a test), and there are **4 P0s** in implemented code. ACCEPT is impossible on three separate grounds: no REQ is CLOSED, 0 of 10 NFRs pass, and P0s exist. ACCEPT WITH CONDITIONS is also excluded, because 38 P1s are open and the P0s touch invariants.

The count covers 46 REQs (REQ-WP0-01…WP8-04) plus NFR-01…10. It uses the verdict columns of `track_A.md`…`track_N.md`, taking each REQ's worst status across its rows, ranked OPEN > NOT IMPLEMENTED > BLOCKED > NOT TESTED > CLOSED OFFLINE > CLOSED.

A row reading "NOT IMPLEMENTED (run level)" whose source is present with offline evidence is counted as CLOSED OFFLINE. That follows §5, where NOT IMPLEMENTED means absent from code; here the stored runs simply predate the code. If those rows are counted literally as NOT IMPLEMENTED, the tally is NOT IMPLEMENTED 19 / OPEN 36 / NOT TESTED 1 / CLOSED OFFLINE 0. That is still not a majority, so the verdict is unchanged.

| Status | REQs (46) | NFRs (10) | Total (56) |
|---|---|---|---|
| CLOSED | 0 | 0 | **0** |
| CLOSED OFFLINE | 8 (WP0-02, WP0-05, WP0-06, WP1-02, WP2-01, WP2-04, WP5-03, WP7-03) | 0 | **8** |
| OPEN | 28 | 8 (NFR-01, 03, 04, 05, 06, 07, 08, 09) | **36** |
| NOT IMPLEMENTED | 9 (WP0-07, WP3-04, WP3-05, WP4-02, WP4-03, WP5-05, WP6-04, WP8-01, WP8-02) | 2 (NFR-02 property test absent — Track N recorded NOT TESTED; NFR-10) | **11** |
| NOT TESTED | 1 (WP0-03 — no pre-open run) | 0 | **1** |
| BLOCKED | 0 as a worst status (blocked sub-checks: A6 resolve-by-ID, WP0-08 refusal path, E2 production budget, NFR-02 mutation, I1 provider replay) | 0 | **0** |

No REQ can be CLOSED: both stored runs are TEST, dirty-tree and forced intra-session, and they predate every remediation commit. Rows keyed only to an ALG are not counted: ALG-12 OPEN, ALG-15 CLOSED OFFLINE, ALG-06 (C10) OPEN, ALG-16 (D7) OPEN. Full defect detail: `defects.md` (59 entries: P0 4 / P1 38 / P2 16 / P3 1).

## P0 (4)
- **UAT-D01** — Recorded evidence cutoff is contradicted by provider requests made after it (13/13 ledgered runs).
- **UAT-D02** — Stale, prior-session or non-refreshed quotes are presented as executable or FRESH; weakened tests match the change (A4/A7/D3/G4/I4).
- **UAT-D03** — Macro packet cannot be resolved by ID; runs record "latest".
- **UAT-D04** — Uncalibrated probability-named fields are populated with no calibration state (D8/E4).

## P1 (38)
- UAT-D05 — Intra-session option data registered as COMPLETE.
- UAT-D06 — Quote timestamps fabricated to equal gate time (226 rows).
- UAT-D07 — TEST runs labelled PRODUCTION/EXECUTION_READY without any REQ-WP0-01 field.
- UAT-D08 — Import-graph gate passes while 25 reachable modules are unmanifested.
- UAT-D09 — No quarantine manifest; dangling actuarial builder reference.
- UAT-D10 — Spread canonicalisation incomplete; 584 rows with spread ≤ 25% wrongly BLOCKed.
- UAT-D11 — Contract tests lack PUT coverage and the unit-change test.
- UAT-D12 — DOI valuation receives no forecast vol, so v2 economics is empty.
- UAT-D13 — Inside-hold contracts removed before valuation.
- UAT-D14 — Scenario values carry an intrinsic floor, so they are not European BSM.
- UAT-D15 — Ranking score mixes v1 and v2 unmarked; v1 not retained under its own name.
- UAT-D16 — DOI input missing governed thesis_id on 38 rows.
- UAT-D17 — DOI projection not activated (1,381 / 63).
- UAT-D18 — Identity/execution/activity state machines not implemented.
- UAT-D19 — Hysteresis unevidenced; PreferredContractSuperseded absent.
- UAT-D20 — Post-open refresh fields absent; economics not recomputed with the refreshed quote.
- UAT-D21 — assessment_id deviates from ALG-16 and is run-scoped.
- UAT-D22 — Outcome labels use the structural target; decision record lacks point-in-time budget.
- UAT-D23 — Calibration script, report and table absent.
- UAT-D24 — Backoff lineage fields and κ-shrinkage absent.
- UAT-D25 — SECTOR_UNMAPPED on 1,444/1,444 rows with 0 lacking GICS.
- UAT-D26 — map_routing port diverges; alignment never SUPPORTIVE/OPPOSED.
- UAT-D27 — Scenario evaluator cannot evaluate the real packet.
- UAT-D28 — Capacity calculators and account capital remain on production paths.
- UAT-D29 — NFR-02 property test and macro-consumer table absent.
- UAT-D30 — BLOCK beside GO on 19/19 GO rows.
- UAT-D31 — Presentation projector contradicts its thesis input (432/480 combinations).
- UAT-D32 — Macro check sits in the dossier pass/fail set; board not built from Lab v4.
- UAT-D33 — completed_session and planned_hold_sessions null on 3,252/3,252 candidates; 0 eligible for maturation.
- UAT-D34 — No replay harness and no expected-difference manifest.
- UAT-D35 — 20 gating env variables sit outside the release profile.
- UAT-D36 — 9/29 Annex config keys absent; owners missing.
- UAT-D37 — EIL fail-closed test assertions weakened without a claim.
- UAT-D38 — Release evidence incomplete; no rollback rehearsal.
- UAT-D39 — Governed values duplicated as literals; capital config readable.
- UAT-D40 — 14 unregistered failing test cases.
- UAT-D41 — Thesis-owned fields written outside the Thesis context.
- UAT-D42 — Contract lineage lost; economics_recomputed constant; no assessment_id persisted.

## E6 disclosure (Track E)
No calibrated p_T exists on any run, because no ALG-09 calibration has ever been fitted. There is therefore no p_T to compare with any stratum base rate, and none was substituted.

Resolved-outcome n in the ledger is **0** in every stratum: CALL 1-5 / 6-10 / 11-20, PUT 1-5 / 6-10 / 11-20, and OTHER. The ledger holds 4,931 CANDIDATE_DECISION events, 0 OUTCOME_OBSERVATION events and 1 non-counterfactual QA OUTCOME. `doi_p_target_before_invalidation` is null on 1,444/1,444 primary rows and 1,424/1,424 comparison rows.

## Confidence
1. **The evidence supports the verdict — High.** REJECT rests on 36 OPEN requirements and 4 P0s, each with file:line and a re-runnable probe. No reading of the NOT IMPLEMENTED rule reaches a majority (11 or 19 of 56). Exposure for the P0s is measured on pre-remediation TEST artefacts. UAT-D02 and UAT-D03 also have current-code source support: `morning_gate.py:2046-2051,2065`; `contracts/interpreter_handoff_materializer.py:293-301`; `domain/option_contract_liquidity.py:449`; resolve-by-ID failing at cc509cb.
2. **The resolved runs are what their run_condition claims — Low as a claim, High as an inference.** No run records `run_condition`; 27/27 lack all nine REQ-WP0-01 fields, and the two reference runs claim PRODUCTION/EXECUTION_READY, which is false. Per `track_A.md` and `run_inventory.csv`, both reference runs are inferred TEST (`-dirty`) and FORCED_INTRASESSION (intra-session cutoff; morning phase 16:59Z REGULAR; post-cutoff fetches). That inference is high-confidence. The other 23 runs are INDETERMINATE.
3. **Nothing untested hides a P0 — Low.** Untested or unavailable:
   - pre-open run (REQ-WP0-03, D5 pre-open);
   - post-open refresh run (A4, D5, REQ-WP0-05);
   - replay harness (absent; I1 provider replay blocked);
   - NFR-02 macro mutation (pipeline execution prohibited);
   - normal-cycle parity (REQ-WP6-04; zero normal cycles).

   No run was produced by cc509cb, so whether current code populates probability fields, publishes executable states or loses population on an artefact is unobserved. Population reconciliation (D1) held only on pre-remediation runs, and five latent silent-removal paths (DEV-16) remain in code.
