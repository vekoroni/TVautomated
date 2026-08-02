# Intelligence Lab v1.1.0

**Tag:** `lab-v1.1.0`
**Commit:** `11fddc24c8acccc8c52d0b677b4213a2f9d424b8`
**Baseline this release is measured against:** `lab-v1.0.0-baseline` (`1c547d706201dce7523a1f9c71f4df207f9586dc`)
**Sprint:** `CLAUDE_CODE_TASK_lab_fix_sprint.md`, full detail in `LAB_FIX_SPRINT_REPORT.md`

---

## Fixes included

| Fix | Commit | Summary |
|---|---|---|
| FIX-CACHE | `7624e51` | Cache signature now fingerprints `eil_enriched`/`options_intelligence`, not just morning-validation files |
| FIX-1 | `db96304` | `Vetoes_Count` (and `Priority_Rank`) export a genuine `0` instead of blank |
| FIX-2 | `ae50af4` | `EIL_Raw_Verdict`/`EIL_Composite` read the correct bare field names |
| FIX-3 | `fa80ba7` | `Trade_Idea_Id` exported (was held in memory, never written) |
| harness fix | `bd534ea` | `tests/lab_qa_audit.py`'s eligibility check made case-insensitive |
| FIX-4 | `e0df27e` | `EV` exported at 8dp — negative sign survives on small magnitudes |
| FIX-5 | `9a2c197` | STRANGLE setups no longer collapse to a false CALL/PUT `Direction`; includes a second-path fix found during UAT (EOD-candidate-manifest override) |
| FIX-6 | `eb671f3` | `Vol_Tailwind_State` added alongside `Vol_State` (kept for compatibility) |
| FIX-7 | `f34a10c` | `Lab_Action_Bucket_Label` exported next to `Priority_Rank`, explaining the ranking basis |
| FIX-8 | `1aecc04` | Duplicate `Lab_Verdict` column removed; `COLUMN_PROVENANCE.md` added |
| test-tooling fix | `11fddc2` | Regeneration script corrected to model `_slim_lab_payload`; corrects a wrong root-cause diagnosis from Phase 0 |

## Columns added

`Trade_Idea_Id`, `Options_Direction`, `Lab_Coherence_Status`, `Lab_Action_Bucket_Label`, `Vol_Tailwind_State`

## Columns changed (same name, different value)

`EV` (4dp → 8dp), `Vetoes_Count` (blank → `0` where the true count is zero), `EIL_Raw_Verdict` / `EIL_Composite` (blank → populated, correct field read), `Direction` (44/96 rows: false single-leg label → blank for STRANGLE rows), `Instrument` (15/96 rows: reverts from a repaired-but-wrong label back to Phase 7's raw pick)

## Columns removed

`Lab_Verdict` (literal duplicate of `Verdict`)

## New config

`LAB_STRANGLE_POLICY` environment variable — `INCLUDE_LABELLED` (default), `FLAG_ONLY`, `EXCLUDE`. Documented inline at the top of `intelligence_lab.py`. Governs whether non-directional STRANGLE setups appear in the default candidate queue; this is a trading-strategy decision, not something this release chose on your behalf — the default preserves today's row count (all STRANGLE rows stay visible, now correctly labelled).

## Consumers affected

`pipeline_interpreter/lab_reconciliation.py` is the only downstream consumer found for any changed/removed column (checked by grep before every fix that touched a shared column name — see `LAB_FIX_SPRINT_REPORT.md` for the full list). It reads `EIL_Verdict`, `Vol_State`, and `Lab_Verdict` in a display-only context list (`_LAB_CONTEXT_FIELDS`) with no branching logic:
- `Lab_Verdict`'s removal degrades gracefully (the loop skips missing keys) — `Verdict` still carries the identical value.
- `Vol_State` is unchanged this release (kept alongside the new `Vol_Tailwind_State` for exactly this reason).
- `EIL_Verdict` is untouched by this sprint (still blank — a separate, unresolved naming ambiguity, not fixed here).

No interpreter-side change is required for this release.

## Known limitations carried forward

- **RR/target-side ambiguity for STRANGLE rows.** `Instrument` still carries Phase 7's single-leg pick for a non-directional setup — `lab_qa_audit.py`'s RR-zero and wrong-side-target checks key off `Instrument`, not `Direction`, so they still fire at similar magnitude to before (RR-zero rows: 14→1; wrong-side-target: 43→42). Re-deriving a single-leg target for strangles is explicitly out of scope this sprint (would be new quant logic).
- **Item 12 — `contract_validity` never populated upstream** (Phase 7 owner). `Vetoes`/`Vetoes_Count` are honest now, but still empty/zero on every row because the field they're built from doesn't exist.
- **Item 13 — `live_data_mode` absent from the export** (Phase 10 owner). The documented LIVE-data eligibility rule cannot be checked from this file.
- **Horizon_Action/Horizon_Pressure/Horizon_Source/Trigger_Price/Trigger_Display/Trigger_Evidence/Trigger_Score/Trigger_Primary/Trigger_Quality/Trigger_Codes are always blank in the real export.** Corrected diagnosis (found in Phase 4.2 UAT, see `BASELINE.md`'s correction section): these fields are computed in full by the Lab internally but dropped by `_slim_lab_payload()`'s field whitelist before ever reaching the browser. Not a caching bug (the originally-shipped FIX-CACHE is still valid for a different, real issue). Not fixed this release — recommended for a future sprint.
- **`NEGATIVE_RR` possible dead code.** No code path was found that ever writes the literal string `"NEGATIVE_RR"` into `sig["lab_verdict"]` server-side; the client-side `finalLabVerdict()` computes it independently. Noted, not chased, per the sprint's explicit instruction.
- **The two export routes.** The client-side `exportCSV()` (real browser button) and the server-side `_load_run()` payload are two different code paths that happened to already agree before this sprint and were kept in agreement throughout it (see UAT results in `LAB_FIX_SPRINT_REPORT.md`). Moving the export server-side (item 8) remains out of scope, as directed.

## Rollback procedure — tested

To return to the pre-sprint baseline:

```
git checkout lab-v1.0.0-baseline -- intelligence-lab/intelligence_lab.py intelligence-lab/static/index.html
```

This reverts only the two Lab source files to their `lab-v1.0.0-baseline` state, leaving all sprint test/tooling artifacts (`tests/`, `BASELINE.md`, `COLUMN_PROVENANCE.md`, this file) in place for forensic comparison. To fully revert the working tree to the tagged commit instead (discarding the sprint entirely, including its tests):

```
git checkout lab-v1.0.0-baseline
```

**Tested:** restored `intelligence-lab/intelligence_lab.py` and `intelligence-lab/static/index.html` to the `lab-v1.0.0-baseline` tag via the first command above, confirmed `git diff` showed both files byte-identical to the tag, then restored back to `lab-v1.1.0` (`git checkout lab-v1.1.0 -- intelligence-lab/intelligence_lab.py intelligence-lab/static/index.html`) and confirmed the working tree was clean again (no diff against `HEAD`). No server restart was required to test the file-level rollback; a real rollback would additionally require restarting the Lab server so it re-imports the reverted `intelligence_lab.py`.

## Deploy confirmation

The Lab server running on `localhost:5002` was restarted after this release's final commit and is running the tagged code (confirmed via `/api/health` and a live UAT pass — see `LAB_FIX_SPRINT_REPORT.md`).
