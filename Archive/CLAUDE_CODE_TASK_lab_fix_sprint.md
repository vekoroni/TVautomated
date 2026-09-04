# Claude Code Task — Intelligence Lab Fix Sprint

## Your role

You are a **Quant Developer**. You are implementing fixes to the Intelligence
Lab, which produces the daily candidate file that the AVSHUNTER Pipeline
Interpreter consumes. Real capital is traded downstream of this file, manually,
by a human reading it.

Your objective is a **tested, non-regressing, deployed Version 1 baseline** that
an end-to-end run can be executed against.

Source of findings: `LAB_QA_REPORT.md` (the audit) and
`LAB_AUDIT_EXECUTIVE_REVIEW.md` (the prioritised fix list). Read both before
starting.

## Non-negotiables

1. **Phase gates are hard.** Do not start a phase until the previous phase's exit
   criteria are met and stated. If a gate fails, stop and report — do not proceed
   and do not work around it.
2. **One fix, one commit.** Each commit message names the fix ID. No batched
   commits, no drive-by refactors, no formatting changes to lines you did not
   functionally alter.
3. **Test before code where the test can be written first.** Every fix ships with
   a test that fails before the change and passes after. Demonstrate both states.
4. **The golden-file diff is the primary regression control.** After every single
   fix, regenerate the export and diff against the frozen baseline. Any column
   that changes and was not supposed to change is a regression — stop.
5. **Never weaken fail-closed behaviour**, and never modify `published`,
   `production_charts_touched`, or any sovereign/permission constant.
6. **Do not touch** the Webull capture layer, cursor/DPI code, or automation_v2
   navigation. Out of scope entirely.
7. **Confidence percentage on every conclusion.** "This did not work and I do not
   know why" is an acceptable report. Silent workarounds are not.
8. If a fix turns out to be larger than the estimate, **stop and report** rather
   than expanding scope.

---

# PHASE 0 — Establish the Version 1 baseline

**Nothing else may begin until this phase is complete.** Every measurement in this
sprint is relative to this baseline.

## 0.1 — Freeze the code state

The working tree currently carries uncommitted changes in
`intelligence-lab/intelligence_lab.py` and `intelligence-lab/static/index.html`
(these predate the audit and were not made by the auditor).

1. Show the full diff. Summarise what it changes in plain terms.
2. **Ask before committing.** These changes add `NEGATIVE_RR`/`EOD_CAUTION`
   verdict overlays and new trigger export columns. Confirm they are intended
   before they become the baseline. Do not assume.
3. Once confirmed, commit and tag: `lab-v1.0.0-baseline`.
4. Record the commit SHA in `BASELINE.md`.

## 0.2 — Freeze a reference export

1. Regenerate the export for run `20260731_083130` using the tagged code.
2. Save it as `tests/golden/lab_export_baseline_20260731_083130.csv`.
3. Record its SHA-256 in `BASELINE.md`.
4. **Diff it against the audited file**
   (`avshunter_signals_20260731_083130_2026-07-31_1640.csv`).

   The audit found that fields which are null in the audited file come back
   populated on re-derivation. **Quantify that difference exactly:** which columns
   differ, on how many rows, and in which direction. Write it into `BASELINE.md`.

   This is the reproducibility problem. You are not fixing it in this phase —
   you are measuring it so that later changes can be attributed correctly.

## 0.3 — Diagnose the reproducibility failure

Determine why the same `run_id` yields different data now than on 31 July.
Candidate causes: run-folder artifacts overwritten in place by a later process;
the uncommitted code diff; a phase writing to a shared latest-file rather than a
run-scoped path.

Report the cause and a recommendation. **Do not fix it in this phase** unless the
cause is a one-line path bug, in which case report it and ask.

## 0.4 — Test harness

1. Confirm the test runner (`pytest` expected) runs and record the current
   pass/fail count. **A pre-existing failing test is a baseline fact, not
   something to fix now.**
2. Copy `lab_qa_audit.py` into `tests/`. This is the acceptance harness — it
   already detects every defect in scope, so it doubles as the regression check.
3. Run it against the golden baseline. Record the finding counts
   (expected: 5 × P0, 13 × P1). **This is the number that must fall.**

## Phase 0 exit criteria

- [ ] Code tagged `lab-v1.0.0-baseline`, SHA recorded
- [ ] Golden export frozen and hashed
- [ ] Delta between audited file and regenerated file quantified in `BASELINE.md`
- [ ] Reproducibility cause identified (or explicitly reported as undetermined)
- [ ] Test suite baseline pass/fail count recorded
- [ ] `lab_qa_audit.py` baseline finding counts recorded

**Report Phase 0 results and wait for confirmation before Phase 1.**

---

# PHASE 1 — Four small fixes, no design decisions

Each of these is independently testable and independently revertable. Implement
in the order given. Golden-file diff after each.

## FIX-1 — `Vetoes_Count` exports blank instead of zero

**File:** `intelligence-lab/static/index.html:2030`
**Change:** `s.sb_vetoes_count || ''` → `s.sb_vetoes_count ?? ''`

**Why:** JavaScript treats `0` as falsy, so a legitimate count of zero exports as
an empty string, indistinguishable from missing data. A downstream
`Vetoes_Count == 0` safety check passes every row unconditionally.

**Test:** unit test over the export mapper with `sb_vetoes_count` set to `0`,
`null`, `undefined`, and `3`. Assert `0` → `"0"` and only `null`/`undefined` → `""`.

**Note honestly in your report:** the upstream `contract_validity` field is `None`
for all 952 rows, so no row currently *has* veto data. This fix makes the column
honest; it does not create data. Item 12 in the executive review.

**Sweep:** grep the export mapper for every other `|| ''` on a numeric field. Any
numeric column using `||` has the same bug. Fix them in this commit and list them.

## FIX-2 — EIL fields read under the wrong names

**File:** `intelligence-lab/static/index.html` (export column definitions)
**Change:** `eil__raw_verdict` → `eil_raw_verdict`,
`eil__composite_score` → `eil_composite_score`, and resolve `eil__composite`
(check whether the existing `composite` alias at `intelligence_lab.py:1504` is the
correct target).

**Why:** The `eil__` double-underscore prefix is the convention for *joined
secondary* sources. EIL is the *base* table and uses bare names. The lookup has
never matched, so three quality columns have always been empty.

**Test:** assert the three columns are non-empty for a fixture row where the
underlying EIL data exists.

**Regression risk — real:** these columns go from always-empty to populated. Any
downstream consumer that has adapted to them being blank may now behave
differently. **Grep the interpreter and handoff code for these column names and
report what consumes them before committing.**

## FIX-3 — `trade_idea_id` not exported

**File:** `intelligence-lab/static/index.html` (export column list)
**Change:** add `trade_idea_id` as a column.

**Why:** The value exists in memory, fully formed
(`20260731_083130:T:PUT:23.0:2026-08-21`). It is simply never written. Without it,
rows cannot be mechanically joined back to journal records.

**Test:** assert the column is present and non-empty on every row of the golden
export.

**Placement:** put it adjacent to `Ticker` or `Run_ID`, not appended at the end —
appending shifts nothing but reads badly. State where you placed it.

## FIX-4 — EV rounded to 4dp, losing sign

**File:** `intelligence-lab/static/index.html:2015` (`getEv(s).toFixed(4)`)
**Change:** increase precision so values of magnitude ~1e-5 survive. Use 8dp, or
reuse the existing `formatEv()` helper (`static/index.html:1150-1157`) if it
preserves sign and precision.

**Why:** True EV magnitudes are 1.1e-5 to 4.9e-5. At 4dp they become `0.0000` and
`-0.0000`. Parsed, `-0.0000 == 0`, so an `EV >= 0` filter admits four
genuinely-negative-EV rows.

**Test:** assert that `-2.8e-05` exports as a string that parses to a value
strictly less than zero. Assert no exported EV parses to exactly `0.0` unless the
underlying value is exactly `0.0`.

**Regression risk:** every EV string in the file changes format. **Grep for
consumers parsing the EV column and confirm they handle the new precision.**
Scientific notation would break naive parsers — prefer fixed decimal.

## Phase 1 exit criteria

- [ ] Four commits, one per fix, each with a test failing-then-passing
- [ ] Golden diff after each fix shows **only** the intended column changing
- [ ] Full test suite pass count ≥ Phase 0 baseline
- [ ] `lab_qa_audit.py` finding count has fallen; state the new counts
- [ ] Downstream consumers of changed columns identified and reported

**Report and wait before Phase 2.**

---

# PHASE 2 — The STRANGLE direction collapse

The largest fix. 43 of 96 rows (45%) affected.

## The split you must respect

There are two separate questions here. **Implement the first. Make the second a
configuration flag. Do not decide the second yourself.**

1. **Labelling (a defect — fix it).** Showing `LONG_PUT` on a non-directional
   strangle is wrong regardless of strategy. The risk/reward and target numbers
   were computed for the two-sided structure; the label says one-sided. Label and
   numbers must describe the same trade.

2. **Eligibility (a business decision — flag it).** Whether strangles belong in
   the candidate set at all is a trading-strategy question that has not been
   answered. Build it as config, default **include, correctly labelled**.

## FIX-5 — Stop collapsing STRANGLE to a single leg

**File:** `intelligence-lab/intelligence_lab.py:1262-1292`
(`_normalise_direction_value`) and `:1358-1382` (`_sync_lab_display_fields`)

**Mechanism to correct:** `_normalise_direction_value` walks a priority list.
`options_direction` correctly resolves `STRANGLE` → `""` via `_side_from_value`.
The loop then **falls through** to `options_strategy`, where
`_side_from_value("LONG_PUT")` returns `"PUT"` on a substring match.
`_sync_lab_display_fields:1363` commits that as the row's direction.

**Change:** when a direction-capable field explicitly resolves to `""` *because it
is non-directional*, stop. Do not continue the fallback chain. Mark the row.

Distinguish "explicitly non-directional" from "field absent" — these must not be
conflated, and the current code cannot tell them apart. That distinction is the
core of this fix.

**New exported columns:**
- `Options_Direction` — the raw upstream value (`CALL`/`PUT`/`STRANGLE`)
- `Lab_Coherence_Status` — `OK` or `STRANGLE_NONDIRECTIONAL`

**Config flag:** `LAB_STRANGLE_POLICY` with values `INCLUDE_LABELLED` (default),
`EXCLUDE`, `FLAG_ONLY`. Read from config, not hardcoded. Document it.

**Tests — all required:**
- A `STRANGLE` row must not receive a `CALL`/`PUT` direction
- A genuine `PUT` row (e.g. ticker `T`) must still resolve to `PUT` — **this is
  the regression that matters most**
- A row with `options_direction` absent must behave as before
- Each of the three policy flag values produces the expected row count
- Property test: for every row where `Direction` is `CALL` or `PUT`, the
  `Structural_Target` must sit on the profitable side of the `Strike`

**Blast radius — report before committing:**
- Row count by `Direction` before and after
- Row count by `Verdict` before and after
- **How many rows remain eligible under each of the three policy values**
- Whether `Priority_Rank` ordering changes, and if so how

That last set of numbers is what the eligibility decision will be made from.
Present it clearly.

**Do not attempt** to re-derive a single-leg `Structural_Target` for strangles.
That is new quant logic, not a fix, and is out of scope.

## Known limitation — document, do not fix

After this change, `RR = 0` will still be ambiguous. The upstream `target_in_play`
gate (`avshunter_options_intelligence.py:5622-5629`) also zeroes R:R when a
call/put wall caps the move. So a zero may mean *non-directional*, *wall-capped*,
or *genuinely no edge*.

Add this to the report as a recommendation for a later sprint: expose
`target_in_play`, `call_wall`, `put_wall` so the three cases are distinguishable.
**Do not implement it now.**

## Phase 2 exit criteria

- [ ] No row exports a `CALL`/`PUT` direction where upstream says `STRANGLE`
- [ ] Ticker `T` and all other genuine single-leg rows unchanged
- [ ] Property test passes: target on the profitable side for all directional rows
- [ ] All three policy values tested, row counts reported
- [ ] `lab_qa_audit.py` no longer reports the R:R zeroing or target-side P0s
- [ ] Blast-radius table produced

**Report and wait before Phase 3.**

---

# PHASE 3 — Clarity fixes

Lower urgency. Correctness is unaffected; these prevent misreading.

## FIX-6 — Rename `Vol_State`

It is derived from GARCH's forward tailwind score, not from IV percentile — a
different concept from `IVP_Label` sharing the same CHEAP/FAIR/EXPENSIVE
vocabulary. Rename to `Vol_Tailwind_State`.

**Regression risk:** a renamed column breaks any consumer reading the old name.
**Grep first and report.** If anything consumes it, propose emitting both names
for one release rather than a hard rename.

## FIX-7 — Expose the ranking basis

`Priority_Rank` sorts on `(lab_action_bucket, -research_priority_score, ticker)`,
and the bucket is granted on `verdict OR morning_execution_permission`. Only
`Verdict` is exported, so the ordering looks arbitrary.

Export `lab_action_bucket_label` (already computed at
`intelligence_lab.py:863`) as its own column. Rank ordering itself must not change
— assert this in a test.

## FIX-8 — Remove the duplicate verdict column

`Verdict` and `Lab_Verdict` both call `finalLabVerdict(s)` — a literal duplicate.
Remove `Lab_Verdict` **only after** grepping for consumers.

Add a `COLUMN_PROVENANCE.md` documenting which columns are independently sourced
and which are derived aliases. `Campaign`, `Exec_Category`, and `MV_Verdict` all
trace to the same upstream decision and must be marked as **not** independent
confirmation.

## Phase 3 exit criteria

- [ ] Grep results reported for every renamed or removed column
- [ ] `Priority_Rank` ordering byte-identical to Phase 2
- [ ] `COLUMN_PROVENANCE.md` written

---

# PHASE 4 — Regression, UAT, deploy

## 4.1 — Full regression

1. Full test suite. Pass count must be ≥ Phase 0 baseline. **Any newly failing
   test is a blocker.**
2. Golden diff, baseline vs final. Produce a column-by-column change table:
   every changed column, why it changed, and which fix caused it. **Any change
   not attributable to a specific fix is a regression.**
3. `lab_qa_audit.py` against the final export. Report the finding delta.
   Target: 0 × P0 from fixes in scope. Findings for items 12/13 (upstream owners)
   will legitimately remain — say so explicitly.
4. **Multi-run check:** run the audit script across every archived export you can
   locate. Confirms the fixes hold beyond a single day and tests whether the
   findings were systemic. Report per-run results.

## 4.2 — UAT

The Lab is a Flask app on `localhost:5002` with a browser front end. The export is
produced by clicking a button. Test the real path, not just the code path.

1. Restart the Lab. Confirm it starts clean and `/api/health` responds.
2. Load the UI. Confirm it renders without console errors.
3. Load run `20260731_083130`. Confirm row counts match expectation.
4. **Click the export button.** Confirm the downloaded file matches what the
   automated regeneration produces. **If it does not, that is a finding** — it
   means the two export routes have diverged.
5. Exercise the UI filters — particularly `EV > 0` and any `R:R > 0` filter — and
   confirm they now behave correctly given FIX-4 and FIX-5.
6. Spot-check five rows manually: ticker `T` (genuine PUT), one strangle, one
   `CONTRACT_REPAIR`, one `ARMED`, one with `Vetoes_Count` present. Confirm every
   value is coherent with its neighbours.

## 4.3 — Deploy

"Deploy" here means the local Lab runs the fixed code and the next end-to-end run
uses it.

1. Tag `lab-v1.1.0`.
2. Write `RELEASE_NOTES.md`: fixes included, columns added/changed/removed,
   consumers affected, known limitations, rollback procedure.
3. **State the rollback explicitly** — the exact command to return to
   `lab-v1.0.0-baseline` — and confirm you have tested that it works.
4. Confirm the Lab is running the tagged code.

## 4.4 — Handoff readiness

The end-to-end run happens next. Before it does:

- List every column added, changed, or removed in this sprint
- For each, state whether the Pipeline Interpreter's handoff reader consumes it
- Flag anything that will require an interpreter-side change
- **If any change breaks the handoff, say so now, before the E2E run**

---

# Final report

`LAB_FIX_SPRINT_REPORT.md`:

- **Status per fix** — done / partial / blocked, with the commit SHA
- **Test evidence** — the failing-then-passing demonstration for each
- **Golden diff table** — every column change attributed to a fix
- **Audit script delta** — findings before and after, per run tested
- **Blast radius** — row counts under each strangle policy
- **UAT results** — including whether the two export routes agree
- **Known limitations carried forward** — the ambiguous R:R zero, items 8/12/13
- **What I could not do, and why** — explicitly. Not a failure section.
- **Rollback procedure**, tested

## Out of scope this sprint — do not start

- Item 8: moving the export server-side. Large regression surface; would make
  breakage in this sprint unattributable. Next sprint.
- Item 12: `contract_validity` never populated — Phase 7 owner.
- Item 13: `live_data_mode` absent — Phase 10 owner.
- The `NEGATIVE_RR` possible-dead-code question — note it, do not chase it.
- Any Phase 7 or Phase 10 change of any kind.

Raise 12 and 13 as written tickets. Do not fix them.
