# 11 — AVS-E2E-DATA-LOGIC-001 vs this atlas: confirmations, refinements, contradictions

**Document:** AVS-E2E-CODE-001 · Deliverable 11
**Prior under test:** `audit/pipeline_map/AVSHUNTER_END_TO_END_DATA_LOGIC_AND_MONETISATION_REPORT_20260831.md` (AVS-E2E-DATA-LOGIC-001)
**Evidence run:** `data/output/runs/20260831_010309/`

The prior was treated as a hypothesis to be verified, never as truth. Each row
below is keyed to a section number of the prior. Verdicts:

- **CONFIRMED** — the prior's claim is reproduced by code reading and/or measurement.
- **REFINED** — the claim is substantially right but imprecise in a way that
  matters to a reader acting on it; the precise statement is given.
- **CONTRADICTED** — code or artefact evidence is inconsistent with the claim.
- **NOT MEASURABLE** — the claim cannot be settled on this evidence run; reason given.

---

## A. §11 reconciliation figures — all CONFIRMED

All fourteen figures in §11 were independently reproduced. Scripts are in
`measurements/`; full detail in `10_cross_verification.md`.

| §11 claim | Verdict | Measured |
|---|---|---|
| Population flow 1,527 → 1,481 → 1,248 → 1,248 → 1,248 → 31 → 201 → 201 | CONFIRMED | Exact, and unique tickers equal rows with **zero duplicates in all eight artefacts** |
| 111 PUT / 90 CALL in the final 201-row book | CONFIRMED (with refinement B1) | Holds for `canonical_direction`, `final_direction`, `direction` |
| 442 Options rows THESIS_INVALIDATED, 437 PUT / 5 CALL | CONFIRMED (with refinement B2) | 442 of 1,248; 437 PUT / 5 CALL |
| 106 of 201 final rows blocked, all PUT | CONFIRMED | `lab_status == BLOCKED` 106 of 201, all PUT |
| Zero invalidations when recomputed with published governed invalidation | CONFIRMED | As-used predicate reproduces 442/442; with published governed invalidation, **0 of 442** |
| 657 DTE_UNSUITABLE; 32 under governed 5/10/20 holds | CONFIRMED | 657 of 1,248; **32** remain, 625 clear; 145 of 201 in the book |
| trigger_quality null 201/201; trigger_score 55.0 for 191; EIL 61 STRONG / 92 SINGLE / 48 NONE | CONFIRMED (with refinement B3) | Exactly so |
| 191 of 201 with a selected contract; 175 with positive two-sided quotes | CONFIRMED (with refinement B4) | 191 with `contract_symbol`; 175 with `contract_bid>0 and contract_ask>0` |
| WBS 31 scored, 14 in intersection, 17 removed | CONFIRMED (with refinement B5) | 31 / 14 / 17 |
| Options `asof_date` 2026-08-31 vs quote timestamps 2026-08-28 | CONFIRMED | `asof_date` 2026-08-31 on 1,248/1,248; `2026-08-28T20:00:00Z` on all 927 quoted rows |
| Macro packet ≈ 39.8 h, STALE/PARTIAL | CONFIRMED | `macro_age_hours = 39.84`, `STALE`, `PARTIAL` |
| Lab load calls `write_final_run_manifest()` | CONFIRMED | Manifest mtime 10:02:11 vs run close 02:56:41 — delta **7 h 05 min 30 s**; the manifest's own `created_at_utc` is `2026-08-31T09:02:11Z`, matching to the second, so it was **rewritten, not touched** |

---

## B. Refinements — the prior is right in substance, imprecise in detail

**B1 — §11.2 "111 PUT / 90 CALL" does not name its column, and is wrong for one
direction field.** The split holds for `canonical_direction`, `final_direction`
and `direction`. It does **not** hold for `governed_direction`, which is
**104 CALL / 77 PUT / 20 STRANGLE** on the same 201 rows. [MEASURED]
The prior's §7.7 and §7.9 state that STRANGLE/UNRESOLVED must remain
non-directional and not be forced into a CALL/PUT; the data shows a live
20-row STRANGLE population in `governed_direction` that the three two-sided
columns do not represent. Any reader taking "111/90" as *the* direction
population will not see those 20 rows.

**B2 — §11.3 names the wrong field.** The label `THESIS_INVALIDATED` is a value
of **`remaining_runway_state`**, not of `thesis_state`. `thesis_state` carries
`INVALIDATED` on the identical 442 rows, so the count is unaffected, but the
field name in the prior is incorrect and would mislead anyone querying it.
[MEASURED]

**B3 — §11.5's "61 STRONG / 92 SINGLE / 48 NONE" is a subset, not the EIL
population.** Those figures are the distribution over the **201 final tickers**.
Over all 1,248 EIL rows the distribution is **294 STRONG / 650 SINGLE / 304
NONE**. [MEASURED] The prior's own §11.7 criticises mixed denominators; this
figure is itself stated without its denominator.

**B4 — §11.2's "completed-session quotes" cannot be verified in the book.**
`selected_quote_timestamp_utc` is blank on **201/201** rows of
`final_opportunity_book`. The counts 191 and 175 are exact, but the
*completed-session* property of those quotes is evidenced one stage upstream in
`options_intelligence`, not in the book the Lab reads. [MEASURED]
This is itself a §10 missing-state instance: the book carries a blank where the
quote timestamp should be.

**B5 — §11.3 over-attributes the Wall Break exclusions.** It states the false
invalidation "removed 17 of the 31 Wall Break rows". Sixteen are
`THESIS_INVALIDATED`/PUT and consistent with that explanation; the seventeenth,
**MCD**, is `THESIS_ACTIVE`/CALL and left the book for a different, unstated
reason. The four named `PROBABLE` exclusions (WHD, HD, SMCI, FORM) are all
within the invalidated sixteen. [MEASURED]

---

## C. Contradictions this atlas adds against the prior

| ID | Prior section | Prior says | Code/artefact evidence |
|---|---|---|---|
| CON-006 | §3, §7.9 | "Macro … must not decide CALL versus PUT or independently block a ticker"; "Macro cannot be an independent direction authority" | `MACRO_DIRECTION_SIZING` (`intelligent_orchestrator.py:549-558`) applies a macro-regime-keyed **4:1 directional size asymmetry** — BULL/RISK_ON give CALL 1.00 / PUT 0.25; RISK_OFF/BEAR give CALL 0.25 / PUT 1.00. Macro selects no direction and blocks nothing, so the letter holds; it nevertheless scales the two directions against each other. Verdict on the prior: **PARTIAL** |
| GAP-003 | §14.5 | "input unique tickers = passed + rejected + deferred" at every filtering stage | Options → Horizon Router: 1,248 in; 655 + 284 + 0 + 17 = **956** out; **292 rows appear in no horizon output file** and `horizon_summary_*.json` records no account of them. The invariant **FAILS** at this boundary. By contrast the Execution → EOD boundary **HOLDS**: 201 + 736 = 937, with all 1,248 covered by `eod_dropoff_audit_*.csv` |
| GAP-004 | §7.10 | Three production horizons 1_5d / 6_10d / 11_20d with holds 5 / 10 / 20 sessions | `horizon_11_20d_*.csv` contains **0 data rows**. No ticker is routed to the 20-session hold — yet 623 of 657 `DTE_UNSUITABLE` rows carry `remaining_hold_sessions = 20.0`. The only horizon whose planned hold matches the lifecycle default is the one nothing is routed to |
| GAP-010 | §12.5 | Run date, data date and quote timestamp must be distinguished | `horizon_summary_*.json` reports `as_of_utc = 2026-08-29T08:12:43Z`, identical to `macro_generated_at`, inside run `20260831_010309` — the artefact's `as_of` carries the macro packet's generation time |
| CON-004 | §5 "execution-order warning" | The prior warns that phase labels mislead — correct, and this atlas confirms it | The prior understates it: `intelligent_orchestrator.py:4136-4139` positively asserts the router "runs BEFORE Vanguard", while :4151 in the same block records it was "moved to after Phase 8a". The file documents two mutually exclusive positions and the wrong one is the more prominent |

---

## D. Where this atlas strengthens the prior

**§11.8 (temporal identity) is worse than stated.** The prior says "repeated
weekend runs can therefore create separate thesis identities for the same
market evidence" — conditionally. Measurement shows it has **already
happened, totally**: `thesis_id` is keyed `TICKER:SIDE:RUN_DATE`, and
**927 of 927** observations for this run pair a `thesis_id` dated 2026-08-31
against a `quote_as_of` dated 2026-08-28. In the store, **86 tickers already
hold more than one `thesis_id`, seven hold three**, and `FLYW:PUT` exists under
both `2026-08-30` (run `20260830_182402`) and `2026-08-31`. [MEASURED]

**§14.4 (append-only correction protocol) does not exist in the schema.** The
prior proposes adding `calculation_version`, `supersedes_event_id`,
`correction_reason`, `corrected_by_run_id` and a `SUPERSEDED_DATA_DEFECT`
status. Measurement confirms **none of these columns exists on any lifecycle
table**, and no value anywhere in those tables contains the string `SUPERSED`.
The nearest constructs are `option_thesis_events.version` and
`option_contract_selection_events.selection_version`; `thesis_state`'s domain is
`{ACTIVE, INVALIDATED}` and `monitor_state`'s is `{ACTIVE, TERMINAL,
NOT_REQUIRED}` — neither carries a superseded or corrected member. So §12.4's
warning ("a false invalidation can become permanently authoritative unless a
correction/supersession protocol exists") describes the **current** state, not a
risk. [MEASURED]

**§6's "immutable run evidence" is not achieved anywhere in the run.** Beyond
the manifest (§11.9), at least six stages rewrite already-promoted artefacts in
place — three `patch_horizon_fields_into_csv` calls (`:4218`, `:4246`, `:4508`),
`inject_actuarial_into_eil_csv` (`:4694`), `merge_garch_into_enriched` (`:4701`)
and Trigger Layer pass 2 (`:4770`). No artefact in the run is immutable once
written (GAP-002).

---

## E. Sections not yet settled in this document

Rows contributed by the static-audit lanes (B, C, D, E, F) are merged into
`07_contradictions_register.csv` and `08_gaps_register.csv`; those bearing on a
prior section are folded into §C above as they land. Sections of the prior that
are forward-looking specifications rather than descriptions of current
behaviour — §14 (target-state controls), §15 (remediation build sequence),
§16 (regression matrix), §17 (operating checklist) — are **out of scope** for
this atlas, which describes what is, not what should be.
