# 06 — Verdict (AVS-TST-DOI-001)

> **Post-run addendum, 2026-09-11.** An evening run, `20260910_150045`,
> executed after this audit closed and is the first artefact in which DOI
> actually ran. **The verdict below is unchanged, and its central safety claim
> is now confirmed against real production data**: 1,424 opportunities in,
> 1,424 retained, 0 deleted, 0 provider fetches, 0 provider-shaped exceptions,
> and 182 non-directional `OTHER` rows retained rather than dropped. Invariants
> 4 and 6 move from `VERIFIED OFFLINE` to `VERIFIED`.
>
> **But DOI produced nothing.** All 1,241 families were rejected at the
> valuation gate with `FAMILY_NOT_VALUED_RATE_UNAVAILABLE`, giving
> `assessed_families=0`, `ranked_families=0`, `lifecycle_families=0`, and
> `doi_projection_state=DATA_UNAVAILABLE` on 1,424 of 1,424 Lab rows. The cause
> is **DOI-D52**: DOI gates valuation on `ev3_rate_used`, which is written only
> by EV3, which the orchestrator runs *after* DOI. DOI reads a column that does
> not exist yet, on every run, deterministically. The DOI-11 fixtures hide this
> by hand-supplying the field (**DOI-D53**).
>
> Condition 2 below is now half met: the `STOP` pill has been removed from the
> Lab template. The `Advisory Only  NO` line remains. Conditions 1 and 3 were
> not addressed before this run, so the P0 remains open and gate
> `DOI-G02-DIRECTION-IMMUTABLE` still cannot run.
>
> Full detail in `04_defects.md`, "Addendum 2".

**Design under test:** AVS-SD-DOI-001 v1.1 · **Reference run:** `20260909_071646`
· **Tester:** Claude Code, independent · **Date:** 2026-09-10

---

## 1. Is DOI safe to leave wired into tonight's Evening run?

# YES WITH CONDITIONS

The question is not whether DOI works but whether it can **remove, hide, close
or fund** anything. On three of those four it is clean, and demonstrably so:

- **Remove — no.** I permuted EIL verdicts, entry/exit/timing states, spread,
  OI, volume and the advisory flags across the real 235-row governed book from
  run `20260909_071646`: **69,300 evaluations, zero rows dropped, CALL 0 /
  PUT 0 / OTHER 0**, and all four statuses reached were carry-forward statuses.
  The family generator applies no OI floor, no spread cap and no delta band —
  the δ 0.40–0.60 preselection is genuinely gone. `DOIProductionSummary`
  cannot even be constructed if the population shrank.
- **Close — no.** DOI writes nothing to the Decision and Outcome Ledger, the
  ledger is append-only, and `can_close_position` is false with a raising guard.
- **Fund — no, inside DOI.** No DOI value reaches a capital field. All four §6
  authority fields are enforced as SQL `CHECK` constraints, which no code path
  can bypass.

But on the fourth question the answer is not clean, and one finding is P0.

**DOI-D27 — the DOI-10 Lab merge can silently overwrite `governed_direction`.**
`domain/dynamic_options_projection.py:117–122` reconciles only four identity
fields, skips the check whenever either side is blank, then performs a bare
`base.update(row)` that overwrites every key the actionable row carries. It is
live, called from `intelligence-lab/intelligence_lab.py:309`. The repo's own
`PROTECTED_AUTHORITY_FIELDS` guard exists 60 lines away in
`contracts/lab_evidence_overlay.py` and is not used here. The precondition is
not hypothetical: **DOI-D28** shows 11 of 235 rows already carry stale identity
fields, including all four accepted rows.

### Conditions

1. **Before the run — mandatory.** Route `merge_all_opportunities` through
   `PROTECTED_AUTHORITY_FIELDS`, and make the identity check fail closed when
   either side is blank. If that cannot be done tonight, disable the v3
   actionable overlay; the projection leg alone changes zero non-DOI columns
   and is safe.
2. **Before the run.** Fix the two Lab strings in **DOI-D29**: `Advisory Only`
   renders `NO` on a missing flag, and every non-EXECUTE verdict — including
   `NOT_EVALUATED`, which was 147 of 235 rows — renders an imperative red
   `STOP` pill. That is the exact harm the design exists to remove, restated in
   the UI.
3. **Before the run.** Retain `final_opportunity_book_pre_doi_<run_id>.json` so
   gate `DOI-G02` in §4 can actually run.
4. **Before acceptance, not before the run.** Commit the DOI tree
   (**DOI-D01**) — no run artefact can currently name the code that produced it.
5. **Before acceptance.** Restate the "120-test pack" (**DOI-D03**).
6. **Not a DOI condition, but urgent:** **DOI-D15**, a pre-existing 19.08%
   contract-value understatement in `contracts/selected_contract_economics.py:657`.

Nothing found can remove, hide or close an opportunity tonight, which is why
this is not a NO.

## 2. Invariant scorecard (§16)

| # | Invariant | State |
|---|---|---|
| 1 | DOI cannot change direction, target, invalidation | **REFUTED** (DOI-D27; holds inside the DOI package, breaks at the Lab merge) |
| 2 | Macro cannot approve, block or reverse | VERIFIED OFFLINE (macro absent from DOI entirely — a positive deviation) |
| 3 | `BLOCKED` cannot delete candidate rows | **VERIFIED** |
| 4 | Contract conditions cannot grant capital or discard | PARTIAL (discard verified; capital — DOI-D04) |
| 5 | Morning Gate records state without a new quote or a deletion | VERIFIED OFFLINE |
| 6 | OI, volume, PCR, entry, exit, timing never deletion gates | **VERIFIED** |
| 7 | Missing data never coerced to economic zero | PARTIAL (verified in the generator; DOI-D12 dividend default) |
| 8 | CALL/PUT equivalent coverage, side-correct formulas | PARTIAL (DOI-D42 CALL-side dead flags; DOI-D40 PUT below intrinsic) |
| 9 | Trading sessions never treated as calendar days | PARTIAL — VERIFIED OFFLINE inside DOI (real XNYS calendar); **REFUTED** for the wider pipeline (DOI-D15/16/17) |
| 10 | Contract switch forces exact-contract refresh | VERIFIED OFFLINE by construction; its evidence field is vacuous (DOI-D18) |
| 11 | Bind to immutable dataset IDs and evidence cutoffs | NOT TESTABLE — schema binds it, no DOI row exists to sample |
| 12 | Restarts idempotent, append-only not overwritten | VERIFIED OFFLINE (DB triggers, proven to fire, 0 breaches) |
| 13 | Dormant/breached/elapsed visible; acquisition suppressed | PARTIAL (suppression live; reactivation has no production caller — DOI-D08) |
| 14 | Only long single-leg CALL/PUT enter the family | VERIFIED OFFLINE (both sides fixture-tested) |
| 15 | No automated exit closes or removes a human-held trade | VERIFIED OFFLINE |

**DOI P0 count: 1 — CALL 1 / PUT 1 / OTHER 1.** DOI-D27 is side-independent, so
any row can be the target.
DOI totals: 1 P0 · 8 P1 · 22 P2 · 17 P3. No `PROB` defect **in DOI**, no `SEC`
defect, no `EXEC-BLOCKED`.

**Separately, and not counted above: 3 pre-existing `PROB` defects on the Lab
surface**, DOI-D49 to DOI-D51, two of them P0 by the letter of the rubric.
`win_prob_predicted` is populated on 235 of 235 rows, CALL 151 / PUT 84 /
OTHER 0, and falls back to a 20-day or 10-day historical win **rate** under a
predicted-probability name; `calculate_win_probability` is a clamped affine
transform of a composite score that then drives an expected-value calculation.
All three files are tracked and carry no DOI change, the DOI-5 import closure
reaches none of them, and removing DOI would remove none of them. They do not
change the DOI verdict, and they are urgent on their own account.

## 3. The three most important defects

1. **DOI-D27 (P0, `AUTH`)** — the only finding that meets the P0 rubric. A
   twenty-line merge function can overwrite the one field the entire design
   declares DOI may never touch. The fix is to use a guard that already exists.
2. **DOI-D29 (P1, `AUTH`)** — DOI-10's stated job was to relabel legacy EIL as
   non-authoritative entry telemetry. On the rendered page it still says
   `Advisory Only  NO` and stamps `STOP` on 147 rows whose only sin is that EIL
   never evaluated them. The pass ran and missed these: the line immediately
   above correctly reads "Legacy Size Diagnostic (Non-authoritative)". A design
   about not discouraging governed opportunities is undone in the last inch.
3. **DOI-D03 (P2, `TEST`)** — the "120-test pack" is `unittest` over two file
   patterns. The four tests it cannot see are the four module-level pytest
   functions in `test_dynamic_options_non_discard_policy.py`, which I rated
   among the strongest in the pack. Meanwhile the three tests that *did* run
   under the name "quality assurance" are source-text greps (DOI-D25). The
   acceptance evidence for the non-discard principle inverts: weak tests ran,
   strong tests did not. All 124 pass under pytest — this is a defect in the
   evidence, not the code.

## 4. What the next Evening run and Morning Gate must show

A checker is provided. **It does not modify `audit/ops/check_run_gates.py`.**

```
venv\Scripts\python.exe audit\doi\AVS-TST-DOI-001\tools\check_doi_gates.py <RUN_ID> ^
    [--control-plane <path>] [--json <path>]
```

Smoke-tested against `20260909_071646`: it independently reproduces
**235 rows, CALL 151 / PUT 84 / OTHER 0**, and independently fails DOI-D29.

| Gate | P0 | Must show | Closes |
|---|---|---|---|
| `DOI-G01-POPULATION` | ✱ | `unique == retained`, `deleted == 0` | invariant 4/6, §1.1 |
| `DOI-G02-DIRECTION-IMMUTABLE` | ✱ | zero rows change `governed_direction` across the merge — **requires the pre-merge book to be retained** | **DOI-D27** |
| `DOI-G03-NO-PROVIDER-FETCH` | ✱ | `physical_fetch_count == 0` **and** `exception_count == 0` (the count is a literal; exceptions are the real signal) | DOI-D23/D24 |
| `DOI-G04-AUTHORITY-COLUMNS` | ✱ | zero authority violations in families and assessments | §6 / DOI-D06 |
| `DOI-G09-NO-PROBABILITY-MISLABEL` | ✱ | no `doi_*` field carrying a probability name without a calibrated model | §11.6, non-goal 5 |
| `DOI-G05-APPEND-ONLY-TRIGGERS` | | all `trg_doi_*` triggers present | invariant 12 |
| `DOI-G06-FAMILY-COVERAGE` | | families persisted, with the CALL/PUT/OTHER split | DOI-D24 |
| `DOI-G07-DATASET-LINEAGE` | | zero families with `source_dataset_ids_json = '[]'` or a null cutoff | invariant 11 |
| `DOI-G08-NO-ACCEPTED-MODEL-OR-POLICY` | | accepted models / policies / labels, reported for review | DOI-8/9, DOI-D19 |
| `DOI-G10-LAB-POPULATION` | | unfiltered book row count with its three-direction split | §14 |
| `DOI-G11-EIL-WORDING` | | no authority-implying EIL wording in the template | **DOI-D29** |
| `DOI-G12-MORNING-NO-REQUOTE` | | the morning artefact exists for the same run id | invariant 5 |

Six `NOT TESTABLE` DOI-11 numbers (20/20, 6,740, 240, 20 reuses, 0 fetches,
0 exceptions) become testable only if the run's `DOIProductionSummary` JSON and
the database copy are **retained** (DOI-D24).

## 5. Deviations from this prompt

1. **Interpreter.** The prompt mandates `C:\Python314\python.exe`. That
   interpreter has **no pytest**, so it cannot run the pack as a pytest
   selector and cannot collect the four non-discard tests at all. I used
   `venv\Scripts\python.exe` (3.13.14, pytest 9.1.1) for all execution and
   `C:\Python314\python.exe` only to reconcile the claimed 120 via `unittest`,
   because that is what the implementer used. Every command records which.
2. **Design filename.** The prompt names
   `AVSSDDOI001_DYNAMIC_OPTIONS_INTELLIGENCE.md`; the file is
   `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`. I proceeded rather
   than stopping to ask, as the match was unambiguous.
3. **Prompt filename.** The task named `AVS-TST-DOI-001_PROMPT.md`; the file is
   `AVS-TST-DOI-001_CLAUDE_CODE_TEST_PROMPT.md`.
4. **A weak probe of my own, disclosed.** My first permutation probe passed with
   63,450 evaluations that all returned a single status — it never reached the
   EIL branches because the Lab book renames engine fields. It was a test that
   could not fail. I rewrote it with harness validation first (it now reproduces
   the persisted status on 231/235 rows) and recorded both versions in
   `T1_authority.md`. I am auditing others for exactly this pattern and record
   my own instance of it.
5. **Severity override.** The T5 subagent rated its time-unit finding P0. The
   prompt's P0 rubric does not include valuation error, and a prior audit
   retired `NOT_MONETISABLE` as a gate, so it deletes nothing. I re-rated it P1
   (DOI-D15) against the prompt's rubric, not the subagent's judgment.
6. **A judgment call flagged for overrule.** A strict reading of the P0 rubric
   ("any null coerced to economic zero on a path that reaches the Lab") would
   make the dividend default (DOI-D12) a P0. I rated it P2 because zero is the
   conventional dividend assumption. ACK should overrule if the strict reading
   is preferred.
7. **Not done.** T6.1–T6.2 and T7.1–T7.2 rely on the project's own lifecycle and
   outcome simulations rather than my own; T8.2 (proving model-card fields are
   computed, not passed in) was not executed. All three are marked MEDIUM
   confidence with what would raise them.
8. **Beyond the prompt.** The T5 verifier found the prohibited time arithmetic
   in three modules **outside** DOI (all tracked and unmodified, so pre-existing).
   I report them because invariant 9 is a pipeline invariant, and mark them
   clearly as not DOI-introduced.

## 6. Tree left as found

| | Start | End |
|---|---|---|
| `git rev-parse HEAD` | `00baa2b0c4b12125a6ad4753910ea73bb6eb6a32` | `00baa2b0c4b12125a6ad4753910ea73bb6eb6a32` |
| Branch | `avs-fix-001` | `avs-fix-001` |
| `git status --porcelain` lines | **306** | **306** |

No commit, tag, branch, stash or reset. No tracked file modified. Every file I
created is untracked and under `audit/doi/AVS-TST-DOI-001/`. Nothing was written
to `data/`, `dropbox/`, `contracts/` or the control-plane database; the live
control plane's sha256 is unchanged and still byte-identical to both pre-DOI
backups. No API key value was read or echoed.
