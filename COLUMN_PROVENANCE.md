# Intelligence Lab export — column provenance

Written for FIX-8 (`CLAUDE_CODE_TASK_lab_fix_sprint.md` Phase 3). Some of the
68 columns in the Lab's CSV export look like independent checks on a trade
but are actually the same underlying value read twice under different
labels. Treating a derived column as a second, independent confirmation of
a derived one is a false sense of corroboration — this is what
`LAB_QA_REPORT.md` finding F7 and `tests/lab_qa_audit.py`'s
`FALSE_INDEPENDENCE` / `VOCAB_INCONSISTENCY` checks were built to catch.

**How to read this table.** *Independent* means the column has its own
upstream source (even if that source itself has a multi-field fallback
chain across phases — picking among aliases for the *same* concept is still
one measurement). *Derived* means the column is computed from, or is a
literal duplicate of, another value already present elsewhere in this same
export row. A derived column tells you nothing a careful reader couldn't
already get from the column it derives from.

---

## The three the task named explicitly

**`Campaign`, `Exec_Category`, and `MV_Verdict` are not independent
confirmation of each other or of `Verdict` — do not use agreement between
them as a second check.**

- `Campaign` = `displayCampaign(s)`, which computes `finalLabVerdict(s)`
  (the same function `Verdict` calls) and maps it through a fixed lookup
  table. Confirmed perfectly collinear with `Verdict` in the audited export
  (`tests/lab_qa_audit.py` → `FALSE_INDEPENDENCE`).
- `Exec_Category` = `getExecutionCategory(s)`, whose second-priority
  candidate (right after a display alias that is itself usually built from
  the same source) is `getMorningExecutionPermission(s)` — i.e.
  `Morning_Permission`. In `MORNING_VALIDATION` handoff mode (this run's
  mode, and the normal case), that candidate is populated on every row, so
  `Exec_Category` is a copy of `Morning_Permission`.
- `MV_Verdict` = the raw `mv__verdict` field from
  `morning_validated_trades_*.csv`. The morning validator sets
  `morning_execution_permission` (→ `Morning_Permission` → `Exec_Category`)
  *from* its own verdict decision — so `MV_Verdict` and `Exec_Category` are
  two labels on the same upstream decision, not two systems checking each
  other.

**Practical rule:** `Morning_Permission` is the one independent measurement
in this cluster. `Exec_Category`, `Campaign`, and `MV_Verdict` all restate
it (or `Verdict`) under a different name. A trade that looks
"triple-confirmed" across these four columns is confirmed once.

---

## Other duplicate/near-duplicate pairs found while building this table

Not asked for by name in the fix spec, so none of these were changed this
sprint — flagged here because this document exists to make exactly this
kind of thing visible, and burying them would defeat the point.

| Pair | Relationship |
|---|---|
| `Execution_Mode` / `Exec_Mode` | **Literal duplicate.** Both call `displayExecutionMode(s)`, byte-for-byte, same as `Verdict`/`Lab_Verdict` was before FIX-8 removed the latter. Candidate for the same treatment in a future sprint. |
| `Vol_State` / `Vol_Tailwind_State` | **Intentional, temporary duplicate.** FIX-6 added `Vol_Tailwind_State` as the new, clearer name and kept `Vol_State` only because `pipeline_interpreter/lab_reconciliation.py` still reads it. Not a bug — a deliberate one-release overlap. Retire `Vol_State` once that consumer migrates. |
| `Hold_Period` / `Hold_Label` | **Almost certainly the same value.** `Hold_Period` = `getHoldPeriod(s)`, whose first candidate is the bare `hold_label` field. `Hold_Label` reads the same field via `getOpt(s,'hold_label')`. They can diverge only if `opt__hold_label` exists but the bare `hold_label` doesn't (or vice versa) — an edge case, not a designed distinction. |
| `Vetoes_Count` | Derived from `Vetoes` — it is `len()` of the same `bad_flags` list `Vetoes` displays as a pipe-joined string. Not a second signal; if `Vetoes` is empty, `Vetoes_Count` is 0 by construction (see FIX-1 and the still-open item 12: `contract_validity` is never populated upstream, so both are currently always empty/0). |
| `IVP_Label` | Derived from `IVP` — confirmed in `LAB_QA_REPORT.md` F8 as "a clean function of IVP" (thresholds: CHEAP ≤38.7, FAIR 42.4–64.9, EXPENSIVE ≥65.2). Legitimate to show both (one is the raw number, one is the bucket), but `IVP_Label` adds no information beyond `IVP` itself. |
| `Horizon_Hold_Alignment` | Derived from `Time_Horizon` and `Hold_Period` — it is their comparison (`ALIGNED` / `HOLD LONGER` / `UNKNOWN`), not a third independent measurement. |
| `Position_Size_Pct` | Derived from `Verdict` (via `finalLabVerdict(s)`) and `sb_position_size_pct` — its branch logic ("0% - waiting" for non-actionable verdicts) means it restates verdict-eligibility rather than adding a new figure. |
| `Lab_Action_Bucket_Label` (new, FIX-7) | Derived by design — it exists specifically to explain what already determined `Priority_Rank`, not as a new signal. |
| `Trigger_Evidence` | Composite/derived — assembles `Trigger_Primary`, `Trigger_Quality`, `Trigger_Codes`, `Trigger_Score` (or catalyst fields) into one human-readable string. Useful as a summary, but adds no data beyond those four columns. |
| `Trigger_Display` | Derived — formats `Trigger_Price` (or phase-trigger fields) for display. Same underlying number as `Trigger_Price`. |
| `EOD_Candidate_Status` vs `EOD_Status` | Likely near-duplicate in most rows — `EOD_Status` = `getEodCandidateStatus(s)`, whose fallback chain includes the same bare `eod_candidate_status` field `EOD_Candidate_Status` reads directly. `EOD_Status` additionally checks a `display_` alias first, so they can differ when that alias exists; when it doesn't, they are the same value under two names. |

---

## Full column list

| Column | Provenance | Notes |
|---|---|---|
| `Ticker` | Independent | Row identity. |
| `Trade_Idea_Id` | Independent | Generated identity string (embeds ticker/direction/strike/expiry — see FIX-3). |
| `Verdict` | Independent | The authoritative resolved verdict (`finalLabVerdict`). |
| `Exec_Category` | **Derived** | See "three named explicitly" above. |
| `EOD_Status` | Independent | Phase 5/10 EOD manifest field, own fallback chain. |
| `Morning_Permission` | Independent | The root of the `Exec_Category`/`Campaign`/`MV_Verdict` cluster. |
| `Morning_Route` | Independent* | *Falls back to `Morning_Permission` when the route field itself is empty. |
| `Morning_Lab_Alignment` | Independent | Lab-computed alignment status, distinct field. |
| `Options_Route` | Independent | Phase 7 field. |
| `Options_Research_Permission` | Independent | Phase 7 field. |
| `Effective_Execution_Verdict` | Independent | Raw passthrough. |
| `EOD_Candidate_Status` | Near-duplicate of `EOD_Status` | See table above. |
| `Campaign` | **Derived** | See "three named explicitly" above. |
| `Direction` | Independent | The Lab's resolved single-leg direction (blank for STRANGLE post-FIX-5). |
| `Options_Direction` | Independent | Raw upstream value (new, FIX-5) — the authoritative pre-resolution signal `Direction` is checked against. |
| `Lab_Coherence_Status` | Independent | Diagnostic status about the direction-resolution process itself (new, FIX-5). |
| `Conv_Score` | Independent | Raw field. |
| `Execution_Mode` | Independent (but see `Exec_Mode` above) | |
| `Instrument` | Independent | Phase 7's contract-type pick. |
| `Strike` | Independent | |
| `Expiry` | Independent | |
| `DTE` | Independent | |
| `Time_Horizon` | Independent | |
| `Hold_Period` | Near-duplicate of `Hold_Label` | See table above. |
| `Horizon_Hold_Alignment` | **Derived** | Comparison of `Time_Horizon` and `Hold_Period`. |
| `Horizon_Action` | Independent | |
| `Horizon_Pressure` | Independent | |
| `Horizon_Source` | Independent | Metadata about horizon-routing provenance. |
| `Trigger_Price` | Independent | |
| `Trigger_Display` | **Derived** | Formats `Trigger_Price`. |
| `Trigger_Evidence` | **Derived** | Composite of `Trigger_Primary`/`Quality`/`Codes`/`Score`. |
| `Trigger_Primary` | Independent | |
| `Trigger_Quality` | Independent | |
| `Trigger_Score` | Independent | Naming collision with a different upstream concept — see `LAB_QA_REPORT.md` F5; not a duplicate of another export column. |
| `Trigger_Codes` | Independent | |
| `Premium_Mid` | Independent | |
| `RR` | Independent | Ambiguity documented separately (Phase 2 known limitation). |
| `EV` | Independent | |
| `EV_Decision` | Independent | Deliberately a separate, corroborating categorical read on `EV` (see F3) — not derived from it. |
| `EV_Quality` | Independent | |
| `Win_Rate_20d` | Independent | |
| `IVP` | Independent | |
| `IVP_Label` | **Derived** | Clean bucket function of `IVP`. |
| `Priority_Rank` | Independent | |
| `Lab_Action_Bucket_Label` | **Derived** | New, FIX-7 — explains `Priority_Rank`'s bucket by design. |
| `Priority_Score` | Independent | Sort-key input to `Priority_Rank`, not a duplicate of it. |
| `Phase` | Independent | |
| `Regime` | Independent | |
| `Structural_Target` | Independent | STRANGLE caveat documented separately (Phase 2). |
| `Days_To_Trigger` | Independent | |
| `Hold_Label` | Near-duplicate of `Hold_Period` | See table above. |
| `Position_Size_Pct` | **Derived** | From `Verdict` + `sb_position_size_pct`. |
| `Vetoes` | Independent | Currently always empty — item 12, upstream, not a duplication issue. |
| `Vetoes_Count` | **Derived** | Count of the same list `Vetoes` displays. |
| `Exec_Mode` | **Literal duplicate of `Execution_Mode`** | See table above. |
| `EV_Status` | Independent | Possibly overlaps with `EV_Decision` conceptually; not confirmed collinear in the audited data. |
| `Win_Rate_Source` | Independent | Provenance metadata about `Win_Rate_20d`, not a duplicate of it. |
| `WBS_Grade` | Independent | |
| `WBS_Score` | Independent | |
| `Vol_State` | Independent (kept for compatibility) | See "other duplicate pairs" above. |
| `Vol_Tailwind_State` | **Literal duplicate of `Vol_State`, by design** | New, FIX-6 — the name to migrate to. |
| `EIL_Verdict` | Independent | Currently always empty — unresolved naming ambiguity (F4), separate issue from FIX-2. |
| `EIL_Raw_Verdict` | Independent | Fixed in FIX-2 to read the correct field. |
| `EIL_Composite` | Independent | Fixed in FIX-2. |
| `MV_Verdict` | **Derived** | See "three named explicitly" above. |
| `MV_Drift_Pct` | Independent | Currently always empty — upstream absence (F4), unrelated to duplication. |
| `Verdict_Reason` | Independent | Currently always empty (F4). |
| `Run_ID` | Independent | Constant per export. |

---

## What this document does not establish

- Whether the *upstream* fields these columns read from are themselves
  independent (e.g. whether `morning_execution_permission` and `mv__verdict`
  are computed from genuinely separate logic one phase earlier, or whether
  that phase itself derives one from the other). This document only covers
  what the Lab's own export mapper does with data it has already received.
- Confirmation across more than one run. The collinearity claims backed by
  `tests/lab_qa_audit.py` findings were confirmed against the audited
  2026-07-31 export; the code-level relationships (same function call, same
  field read) hold for any run by construction, but a crosstab re-check
  across more runs would strengthen the data-level claims.
