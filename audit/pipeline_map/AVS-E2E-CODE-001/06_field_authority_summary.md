# 06 — Field-authority summary

**Document:** AVS-E2E-CODE-001 · Step 4 narrative
**Data:** `06_field_authority_trace.csv` — 234 traced rows, 15 concepts
**Quarantine:** `06_field_authority_trace_MALFORMED.csv` — 5 rows field-shifted
by an unescaped comma in a lane CSV; retained rather than dropped, and excluded
from the counts below.

Concept names were folded onto the task's canonical set by
`_tooling/normalise_fields.py`; the lanes had emitted 28 case- and
wording-variant buckets for the same 14 concepts.

---

## 1. The headline number

| Concept | Rows | Writers | Readers | Writers marked **authority** |
|---|---:|---:|---:|---:|
| Verdict / permission | 59 | 54 | 5 | **38** |
| Macro / regime | 32 | 27 | 5 | 10 |
| Monetisability | 24 | 24 | 0 | 12 |
| Lifecycle state | 23 | 21 | 2 | 19 |
| Direction | 20 | 13 | 7 | 7 |
| Quote | 20 | 17 | 3 | 10 |
| Run identity vs session vs quote timestamp | 14 | 13 | 1 | 8 |
| Invalidation / stop | 9 | 7 | 2 | 3 |
| Trigger block | 9 | 9 | 0 | 5 |
| Structural target | 7 | 6 | 1 | 3 |
| DTE | 6 | 5 | 1 | 2 |
| Horizon bucket | 6 | 6 | 0 | 1 |
| Planned hold | 2 | 2 | 0 | 0 |
| Selected contract identity | 2 | 1 | 1 | 0 |
| Lab display | 1 | 0 | 1 | 1 |

Across all writers: **111 authority · 33 fallback · 25 display · 20 recompute ·
15 alias · 1 not-applicable.**

AVS-E2E-DATA-LOGIC-001 §9 asserts one sole authority per business concept. The
trace does not support that for any of the top six concepts. **`Verdict /
permission` has 38 distinct writers that each mark themselves authoritative**,
which is the quantified form of the prior's §12.1 diagnosis ("the last writer
often wins even when it is not the authority"). This is the single most
load-bearing measurement in the atlas.

A caveat on how to read the 38: the count is of *writers marking themselves
authority*, not of writers that survive into the final book. Several are in
DEAD modules (`convergence_engine.py`, `atheoretic_signals.py`,
`signal_funnel.py`, `probability_engine.py` reuse branch) and therefore never
execute on the orchestrated path. The finding is that the codebase contains 38
self-declared verdict authorities, not that 38 of them contend at run time.

---

## 2. Effective authority per concept, as at the evidence run

"Effective authority" = the writer whose value the final 201-row book actually
contains, established by measurement where possible.

| # | Concept | Effective authority on the evidence run | Matches §9? | Basis |
|--:|---|---|---|---|
| 1 | **Direction** | `canonical_direction` / `final_direction` / `direction` all agree at **111 PUT / 90 CALL**; `governed_direction` disagrees at **104 CALL / 77 PUT / 20 STRANGLE** | **NO** | MEASURED. §9 names Direction Governance as sole authority. Two populations coexist in one book row; the 20 STRANGLE rows are invisible in the three two-sided columns |
| 2 | **Horizon bucket** | Horizon Router (`macro_horizon_router.py`), written at evening stage 19 — **after** contract selection at stage 18 | PARTIAL | OBSERVED order + MEASURED mtimes. §9 says "no silent overwrite"; the router writes after the consumer that needs it |
| 3 | **Planned hold** | **Contested and unresolved.** `planned_hold_sessions` = 5.0 on 655 of 657 rows; `remaining_hold_sessions` = 20.0 on 623 of the same 657 | **NO** | MEASURED. Two live values for one concept; the lifecycle consumes the 20 (CON-009) |
| 4 | **DTE** | Selector uses governed horizon windows; lifecycle `minimum_required_dte` reproduces `ceil(hold + 3 + 5)` on **657/657** | **NO** | MEASURED. Substituting governed 5/10/20 holds clears 625 of 657 `DTE_UNSUITABLE` |
| 5 | **Structural target** | `structural_target` from the governed thesis, passed through to `exit_target_price` | YES | OBSERVED |
| 6 | **Invalidation / stop** | **Two writers.** `_ev3_handoff_fields` publishes a direction-mirrored value (`scripts/avshunter_options_intelligence.py:4093-4102`); the lifecycle consumes the raw `ctx["stop"]` (`:4549`) | **NO** | OBSERVED + MEASURED. All 442 invalidated rows carry `invalidation_source = DIRECTION_MIRROR_FROM_STOP_LOSS_V1`; recomputing with the published value yields **0** invalidations (CON-007) |
| 7 | **Trigger block** | **Split by artefact.** EIL holds correct categories (61 STRONG / 92 SINGLE / 48 NONE over the 201; 294/650/304 over all 1,248). The Execution spine the EOD engine reads holds none: `trigger_quality` and `trigger_primary` blank **201/201** | **NO** | MEASURED. Mechanism is CON-003: Trigger pass 2 (L4770) runs after EIL wrote `execution_v3_5` (L4690) |
| 8 | **Verdict / permission** | `eil_final_action` / `lab_status`; **106 of 201 BLOCKED, all PUT** | **NO** | MEASURED. 38 self-declared authorities exist (§1 above) |
| 9 | **Monetisability** | **Not computed at EOD.** Blank in the EOD book; computed only in Morning Gate | **NO** | MEASURED (§11.6 CONFIRMED). §9 requires the contract economics module to own it and be recomputed on quote change |
| 10 | **Selected contract identity** | `contract_symbol` present on **191 of 201**; resolved through a 3-name fallback chain in `tools/msi_reconcile.py:43-48` | PARTIAL | MEASURED + OBSERVED. Two OCC parsers exist (CON-502) |
| 11 | **Quote** | EOD chain quote; **175 of 201** rows carry positive two-sided values. `selected_quote_timestamp_utc` is blank **201/201** in the book | PARTIAL | MEASURED. The completed-session property is evidenced one stage upstream, not in the book (delta B4) |
| 12 | **Run identity vs completed session vs quote timestamp** | **Conflated.** `asof_date` = 2026-08-31 on 1,248/1,248 while quote timestamps are `2026-08-28T20:00:00Z` on all 927 quoted rows; `thesis_id` is keyed `TICKER:SIDE:RUN_DATE` | **NO** | MEASURED. **927 of 927** observations pair a 08-31 thesis_id against an 08-28 quote; 86 tickers already hold >1 thesis_id, seven hold three |
| 13 | **Macro / regime** | Macro normaliser for labels; `MACRO_DIRECTION_SIZING` for the directional size multiplier | PARTIAL | OBSERVED + MEASURED. Macro selects no direction and blocks nothing (policy holds to the letter) but applies a **4:1 CALL:PUT size asymmetry** (CON-006). `contracts/macro_regime_safety.py` specifically cannot block or set direction — verified |
| 14 | **Lifecycle state** | `remaining_runway_state` (442 `THESIS_INVALIDATED`) and `thesis_state` (`INVALIDATED` on the identical 442) | PARTIAL | MEASURED. §11.3 of the prior names the wrong field (delta B2). Two distinct modules are named "lifecycle" (CON-501) |

**None of the 14 concepts is UNTRACED.** Six trace to a single effective
authority that matches §9 only partially; seven contradict §9 outright; one
(Structural target) matches.

---

## 3. The fallback chains that bridge semantic types

33 writer rows are typed `fallback`. The ones that bridge two *different*
semantic types — the class the prior forbids in §10 — are:

| Bridge | Where | Register |
|---|---|---|
| categorical ← numeric (`trigger_quality` ← `trigger_score` = 55.0) | Lab read path | §11.5, CONFIRMED |
| IV level ← IV percentile | `scripts/avshunter_options_intelligence.py:3657-3658` | GAP-305 |
| VRP vocabulary ← IV label vocabulary | `:3659` vs `iv_engine.py:118` | CON-310 |
| missing direction ← CALL | `zero_dte/zero_dte_contract.py:368`; `short_swing/short_swing_contract.py:318`; `short_swing_monitor.py:314` | peripheral lane |
| missing direction ← PUT | `trigger_confirmation_engine.py:289-290`; `scripts/exit_rules_engine.py:56-62` | CON-300, CON-352 |
| stale ← fresh (unparseable date) | `scripts/data_contract_validator.py:200-201` | CON-360 |
| missing delta ← 0.50 | `mcmillan_advisory_layer.py:265` | CON-314 |
| missing composite ← 50 → confident probability triple | `probability_engine.py:57` | CON-328 |
| absent alignment ← 50.0 | `scenario_router.py:124-136` | CON-331 |
| pending ← zero (monetisability) | EOD book | §11.6 |
| structural stop ← thesis invalidation level | `scripts/exit_rules_engine.py:34` | CON-353 |

---

## 4. How to use this trace

- `role` distinguishes writer from reader; `write_type` distinguishes an
  authority write from an alias, a fallback, a recomputation or a display copy.
- `reader_accepts` lists the fallback chain a reader will tolerate, which is
  where a semantic bridge usually enters.
- A row with `write_type = authority` is a **self-declaration by that code**,
  audited against §9 in the table above — it is not a finding that the write is
  legitimate.
