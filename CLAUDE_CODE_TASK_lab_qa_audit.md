# Claude Code Task — Intelligence Lab QA Audit

## Your role

You are a **Quant Quality Assurance Auditor**. You are auditing a signal
generation system whose output informs live capital allocation on Tastytrade.

Your job this session is to **find out why**, not to fix. You produce one report.
We review it together before anything changes.

## Rules

1. **Read-only.** No source edits. `git status` must be clean at the end except
   for your report file.
2. **No fixes**, however obvious. Write them into the report as recommendations.
3. **Do not touch** the Webull capture layer, cursor/DPI code, or the automation_v2
   navigation code. Out of scope entirely.
4. **Evidence for every claim.** State the file, the line, and what you read.
   Never assert a mechanism you have not seen in source.
5. **Confidence percentage on every conclusion.** "I could not determine this"
   is an acceptable answer. Inventing a plausible cause is not.
6. If something is correct, say it is correct. A clean finding is a real result.

## Scope

**In:** The Intelligence Lab — the files it reads from
`data\output\runs\{run_id}\`, the merge and transformation logic inside
`intelligence_lab.py`, and the CSV it exports.

**Out:** Everything downstream of the Lab export. Everything upstream of the run
folder. Do not audit Phase 7, `morning_gate.py`, or the actuarial database — note
anything you notice in passing and move on.

## Background: what has already been established

A 96-row export (`avshunter_signals_20260731_083130_2026-07-31_1640.csv`, run
`20260731_083130`) was analysed. The following are **confirmed properties of the
exported data**. The arithmetic is settled. **The causes are unknown and are your
task.**

Do not spend time re-proving these. Explain them.

### F1 — R:R is zero for CALL setups where it is computable and positive

The R:R formula reconciles on 83 of 96 rows:

```
intrinsic = max(0, target - strike)  for CALL
            max(0, strike - target)  for PUT
RR        = clip((intrinsic - Premium_Mid) / Premium_Mid, min=0)
```

Among rows where the target is on the profitable side of the strike, so R:R
*is* computable:

| Direction | RR > 0 | RR == 0 | % zeroed |
|---|---|---|---|
| CALL | 18 | **14** | **44%** |
| PUT | 34 | 1 | 3% |

Examples exporting `RR = 0.000`:

| Ticker | Instrument | Strike | Target | Premium | RR computable |
|---|---|---|---|---|---|
| NUE | LONG_CALL | 260.0 | 346.04 | 7.550 | **10.396** |
| MO | LONG_CALL | 70.0 | 74.70 | 0.990 | **3.747** |
| GOOGL | LONG_CALL | 340.0 | 369.44 | 9.650 | **2.051** |
| JPM | LONG_CALL | 355.0 | 371.91 | 5.750 | **1.941** |

**Find where RR is produced.** Is it computed in the Lab, or read from an
upstream file? Is there a sign convention that differs by instrument? Is a
`clip(lower=0)` masking a negative produced by an inverted subtraction? Is RR
sourced from a *different* target field than the `Structural_Target` that gets
exported?

*A tested and rejected hypothesis: `Structural_Target` decimal precision does not
predict the zeroing (29/51 for ≤2dp vs 15/45 for >2dp). Do not re-test this.*

### F2 — 29 rows have Structural_Target on the losing side of the strike

19 of them carry `Verdict = GO`. Examples: AVGO `LONG_PUT` strike 390 target
411.12; FCX `LONG_PUT` strike 65 target 72.26; MCD `LONG_PUT` strike 270 target
293.84.

But ticker `T` (rank 1) is `LONG_PUT` strike 23.0 target 19.70 — using the same
field as a profit target.

**Determine which is true:** `Structural_Target` is overloaded and means
different things on different rows, or contract selection genuinely mismatched
the thesis and the Lab passed it through unflagged. These are different bugs in
different places.

### F3 — EV is exported at 4dp and loses its sign

The raw CSV contains both `0.0000` and `-0.0000`. 15 rows export `0.0000` with
`EV_Decision = WEAK`; 4 rows export `-0.0000` with `EV_Decision = AVOID`.

Sign survives only in `EV_Decision`. So `EV >= 0` admits four genuinely
negative-EV rows, because `float("-0.0000") == 0`.

**Find the export formatting step.** What precision is available in memory before
it is written? Is any consumer filtering on the numeric column rather than on
`EV_Decision`?

### F4 — 15 of 64 columns are 100% null

```
Horizon_Action  Horizon_Pressure  Horizon_Source
Trigger_Price   Trigger_Primary   Trigger_Quality  Trigger_Codes
Days_To_Trigger
Vetoes          Vetoes_Count
EIL_Verdict     EIL_Raw_Verdict   EIL_Composite
MV_Drift_Pct    Verdict_Reason
```

`WBS_Grade` and `WBS_Score` are additionally null on 78/96 rows.

`Vetoes` and `Vetoes_Count` being empty matters most — a consumer checking
`Vetoes_Count == 0` as a safety condition passes every row unconditionally.

**For each field, establish which of these four it is:**
(a) not produced upstream, (b) produced but the Lab never reads it,
(c) read but dropped in the merge, (d) merged but lost at export.

Four different bugs. Say which, per field.

The Lab's CSV reader is documented as returning an empty list on any error.
Check whether that is masking a missing or misnamed input file — this is the
April 2026 failure mode (field mismatches collapsing 1,470 signals) and the
April path bug where `morning_validation` was read from the wrong folder.

### F5 — Trigger fields look hardcoded

`Trigger_Score = 55.0` on every row. `Trigger_Evidence = "TRIGGER 55"` on every
row. `Trigger_Display = "-"` on every row. `Trigger_Price`, `Trigger_Primary`,
`Trigger_Quality`, `Trigger_Codes` all null.

**Did the trigger layer (Phase 8.6b) produce output for this run, and did the Lab
read it?** Is 55.0 a fallback constant?

### F6 — Priority_Rank is not ordered by Priority_Score

Rank is ordered within verdict class, not globally. TRV scores 86.8 and ranks 68;
ELV scores 45.3 and ranks 10.

| Verdict | rank range | score range | n |
|---|---|---|---|
| GO | 1–67 | 32.1–87.8 | 62 |
| ARMED | 2–57 | 36.1–85.0 | 5 |
| CONTRACT_REPAIR | 68–96 | 32.6–86.8 | 29 |

**Find the sort. Is the ordering rule intentional and documented anywhere?**

### F7 — Verdict columns disagree, and several are collinear

`Verdict == 'GO'` selects 62 rows. `Exec_Category == 'GO'` selects 67 — it folds
the 5 ARMED rows in.

Perfectly collinear pairs: `Verdict`/`Lab_Verdict`, `Verdict`/`Campaign`,
`Exec_Category`/`Morning_Permission`, `Exec_Category`/`MV_Verdict`.

**Is `MV_Verdict` an independent morning-validation result, or a relabelling of
`Exec_Category`?** If it is derived, it provides no independent confirmation and
must not be treated as a second check.

### F8 — Vol_State and IVP_Label contradict

`IVP_Label` is a clean function of `IVP` (CHEAP ≤38.7, FAIR 42.4–64.9,
EXPENSIVE ≥65.2). `Vol_State` is not — `Vol_State = CHEAP` spans IVP 29.4 to
100.0. **20 rows are simultaneously `Vol_State = CHEAP` and
`IVP_Label = EXPENSIVE`.** Ticker `T` is one.

**What does each field mean, and where does each come from?** They may be
legitimately different concepts (realised vol regime vs implied vol percentile)
with an unsafe shared vocabulary. If they are the same concept, one is wrong.

### F9 — Fields absent from the export entirely

`live_data_mode` and `trade_idea_id` do not exist as columns. Documented trade
eligibility requires `live_data_mode = LIVE`.

**Does the Lab hold this data and drop it at export, or never receive it?**
Compare the export against what `/api/run/{run_id}` returns for the same run.

## Task

For each of F1–F9, in that order:

1. Locate the responsible code. Give `file:line`.
2. State the mechanism — what the code actually does.
3. Classify: **defect**, **naming/contract problem**, or **intended behaviour**.
4. State the consequence for a trader acting on this export.
5. Give a fix recommendation. **Do not implement it.**
6. Give a confidence percentage.

Then answer one question directly:

> **Is this export fit to be the single source of truth for the Pipeline
> Interpreter? Yes, no, or not yet — and if not yet, what specifically must change?**

## Report

One file: `LAB_QA_REPORT.md` in the repo root.

Structure:

- **Verdict** — the answer to the question above, first, in three sentences.
- **Findings F1–F9** — one section each, in the format above.
- **Severity ranking** — order the findings by how much damage each does to a
  live-capital decision. P0: can make an unsound trade look sound or silently
  discard a sound one. P1: removes a safety signal or hides a defect. P2:
  robustness only.
- **The single highest-value fix**, and why it beats the others.
- **What I could not determine** — be explicit. This section is not a failure.
- **Incidental observations** — anything out of scope you noticed. Do not act
  on them.

## Done when

- All nine findings have a `file:line`, a mechanism, and a classification.
- The fitness question is answered directly with a confidence percentage.
- `git status` is clean apart from `LAB_QA_REPORT.md`.
- Nothing has been fixed.

Stop there. We review the report before deciding anything.
