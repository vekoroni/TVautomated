# 07 — Contradictions register: narrative

**Document:** AVS-E2E-CODE-001 · Step 5 narrative
**Data:** `07_contradictions_register.csv` — **149 rows**, `CON-001` … `CON-502`

ID ranges by analysis lane: 001–099 cross-cutting (main session) · 100–199 core
contracts and hotspots · 200–299 upstream · 300–399 midstream · 400–499 read
path · 500–599 canonical substrate.

---

## 1. Distribution

| Category (task vocabulary) | Rows |
|---|---:|
| CODE_VS_COMMENT | 47 |
| STAGE_VS_STAGE | 21 |
| CALL_VS_PUT | 18 |
| WRITER_CONFLICT | 11 |
| CODE_VS_DOC | 10 |
| LABEL_VS_ORDER | 4 |
| DUPLICATE_WRITER | 3 |
| Other categories emitted by lanes outside the six prescribed names | 35 |

Confidence: **275 of 300** register rows (contradictions and gaps combined) are
HIGH, 24 MEDIUM. One row has a field-shifted `confidence` cell from an
unescaped comma; it is present in the CSV and flagged here rather than silently
corrected.

**A note on category discipline.** The task prescribed six CON categories.
Lanes emitted 21 further ad-hoc category names (`DEAD_LOOKUP`,
`NORMALISATION_ASYMMETRY`, `FORMULA_DISCONTINUITY`, `PROVENANCE_UPGRADE`, and
others). These have not been forcibly remapped, because most describe a real
distinction the six names blur, and remapping would destroy that information.
They are listed verbatim in the CSV.

---

## 2. The four contradictions that explain the evidence run

**CON-007 — two writers for invalidation (WRITER_CONFLICT).** The published
governed invalidation is direction-mirrored at
`scripts/avshunter_options_intelligence.py:4093-4102`; the lifecycle consumes the
raw `ctx["stop"]` at `:4549`. Every one of the 442 invalidated rows carries
`invalidation_source = DIRECTION_MIRROR_FROM_STOP_LOSS_V1`, so the invalidated
population is exactly the population whose raw stop needed mirroring.
Recomputed with the published value: **0 of 442**. This is the mechanism behind
106 of 201 book rows being blocked, all PUT.

**CON-009 — two holding-period conventions (STAGE_VS_STAGE).** Contract
selection uses the governed horizon DTE windows; the lifecycle consumes
`ctx["hold_days"]` at `:4546`, measured at 20.0 on 623 of 657 `DTE_UNSUITABLE`
rows while `planned_hold_sessions` is 5.0 on 655. Published
`minimum_required_dte` reproduces `ceil(hold + 3 + 5)` on 657/657; governed
holds clear 625.

**CON-003 — the trigger commutation boundary (STAGE_VS_STAGE).** EIL writes
`execution_v3_5` at orchestrator `:4690`; Trigger Layer pass 2 rewrites
`eil_enriched` at `:4770`. The EOD engine reads the Execution spine, so trigger
categories that exist in EIL are absent downstream — `trigger_quality` blank
201/201.

**CON-001 / CON-002 / CON-004 — phase labels versus real order (LABEL_VS_ORDER,
CODE_VS_COMMENT).** The Horizon Router is labelled "Phase 1B" and runs at stage
19 of 51, after Options Intelligence at 18. `intelligent_orchestrator.py:4136-4139`
positively asserts it "runs BEFORE Vanguard" while `:4151` in the same comment
block records that it was "moved to after Phase 8a" — the file documents two
mutually exclusive positions and the wrong one is the more prominent. The
Trigger Layer runs twice under one label pair.

---

## 3. CALL_VS_PUT — 18 rows, and the shape they share

Almost every direction contradiction is the same defect: a two-branch
`if direction == X … else …` with no third arm, so `UNRESOLVED`, `STRANGLE`,
blank and `NONE` are silently assigned one side.

- **Coerced to PUT:** `trigger_confirmation_engine.py:289-290` (explicitly
  overwrites and then reports the coerced value as fact);
  `scripts/exit_rules_engine.py:56-62`.
- **Coerced to CALL:** `zero_dte/zero_dte_contract.py:368` and
  `short_swing/short_swing_contract.py:318` (`row.get("options_direction", "CALL")`);
  `short_swing/short_swing_monitor.py:314` (a partially-written state file
  resurrects a short position as a long).
- **Given the better of both scorecards:** `avshunter_trap_engine.py:268-273` —
  a directionless package takes `max(bull_score, bear_score)` and can reach
  `CHASE`.
- **Given no invalidation at all:** `scripts/avshunter_options_intelligence.py:4092-4102`
  (CON-008) — for direction ∉ {CALL, PUT} neither branch is entered, so
  `invalidation` stays `None`. Measured: 20 STRANGLE rows exist in
  `governed_direction`.
- **The counter-example.** `canonical_data/option_identity.py:60` performs the
  same two-way mapping *soundly*, because the OCC regex closes the input domain
  and a non-match fails an assertion first. `market_structure/lifecycle.py:19-25`
  is the reference implementation: four named outcomes with every
  other/blank input routed to a named `NEUTRAL` or `INSUFFICIENT_DATA`.

---

## 4. CODE_VS_COMMENT is the largest category (47 rows)

The dominant pattern is a docstring that describes a superseded implementation.
Representative examples, each verified against code:

- `iv_engine.py:30-33` documents strict `>` / `<` VRP thresholds; the code is
  inclusive `>=` / `<=` — boundary values behave opposite to the documentation.
- `scripts/data_contract_validator.py:94` documents a `MEDIUM` confidence grade
  that is unreachable.
- `enums_structural.py:6-15` declares itself the canonical source and forbids
  redefining its strings; the literals are redefined in at least ten live
  modules and only four import the file.
- `convergence_engine.py` carries **three** different specifications of one
  threshold pair (docstring 60/40, comments 52/48 then 51/49, code 51.0/49.0),
  and the rationale comment for the change is arithmetically wrong.
- `scripts/exit_rules_engine.py`, `zero_dte/zero_dte_contract.py` and
  `short_swing/short_swing_contract.py` each document gate constants that
  differ from the constants actually set (three of six wrong in the last case).

Two comment claims were audited as **HOLDS** and are worth recording as the
positive cases: `canonical_data/registry.py:234-240` on dataset identity versus
provenance, and `market_structure/params.py:1` declaring its own thresholds
`PROPOSED_NOT_CALIBRATED` and propagating that label into every persisted
record.

---

## 5. Where this register contradicts the prior document

Five rows contradict AVS-E2E-DATA-LOGIC-001 directly rather than contradicting
the code's own comments. They are consolidated in `11_doc_vs_code_delta.md` §C:
CON-006 (macro applies a 4:1 directional size asymmetry, so §3/§7.9 hold only
to the letter), CON-004 (the prior understates the label problem), plus
GAP-003, GAP-004 and GAP-010.
