# Intelligence Lab Fix Sprint — Final Report

Sprint spec: `CLAUDE_CODE_TASK_lab_fix_sprint.md`. Source findings:
`LAB_QA_REPORT.md` (audit) and `LAB_AUDIT_EXECUTIVE_REVIEW.md` (prioritised
fix list). Baseline detail: `BASELINE.md`. Release detail: `RELEASE_NOTES.md`.
Column provenance: `COLUMN_PROVENANCE.md`.

**Tags:** `lab-v1.0.0-baseline` (`1c547d706201dce7523a1f9c71f4df207f9586dc`) →
`lab-v1.1.0` (`ab8cb9f392b8ff7baf2547635cb68e0fdc27a97c`)

---

## Status per fix

| Fix | Status | Commit |
|---|---|---|
| FIX-CACHE (folded in per your instruction) | Done | `7624e51` |
| FIX-1 — Vetoes_Count blank vs. zero | Done | `db96304` |
| FIX-2 — EIL field names | Done | `ae50af4` |
| FIX-3 — trade_idea_id not exported | Done | `fa80ba7` |
| harness fix — case-insensitive eligibility check (per your instruction) | Done | `bd534ea` |
| FIX-4 — EV precision | Done | `e0df27e` |
| FIX-5 — STRANGLE direction collapse + second defect found in UAT (per your instruction: "if the bug is valid we need to fix") | Done | `9a2c197` |
| FIX-6 — Vol_State / Vol_Tailwind_State | Done | `eb671f3` |
| FIX-7 — ranking basis | Done | `f34a10c` |
| FIX-8 — duplicate verdict + COLUMN_PROVENANCE.md | Done | `1aecc04` |
| test-tooling correction (found in Phase 4.2 UAT) | Done | `11fddc2` |

All ten numbered items done. Nothing partial, nothing blocked.

---

## Test evidence

Every fix above has a dedicated test (`tests/js/test_fix*.js` for client-mapper
changes, `tests/test_lab_*.py` for server-side changes) that was run against
the pre-fix code and shown failing, then run again after the fix and shown
passing — not just asserted in a commit message. Two were verified by
temporarily reverting the fix in place (`git stash` for the harness fix,
`if False and ...` patch-and-restore for the FIX-5 EOD-merge guard) rather
than only trusting "it was broken before I wrote the fix" from memory.

Final count: **238 tests passing** across the sprint's own test files (up
from 215 recorded at the Phase 0 baseline), plus 8 JS test files, all green.

---

## Golden diff table — every changed column, attributed

Baseline: `tests/golden/lab_export_baseline_20260731_083130.csv` (96 rows × 64
columns, frozen at `lab-v1.0.0-baseline`).
Final: regenerated at `lab-v1.1.0` with the corrected `regenerate_lab_export.py`
(96 rows × 68 columns) — confirmed byte-identical to a real browser export in
Phase 4.2.

| Column | Change | Rows | Caused by |
|---|---|---|---|
| `Trade_Idea_Id` | added | 96/96 | FIX-3 |
| `Options_Direction` | added | 96/96 | FIX-5 |
| `Lab_Coherence_Status` | added | 96/96 | FIX-5 |
| `Lab_Action_Bucket_Label` | added | 96/96 | FIX-7 |
| `Vol_Tailwind_State` | added | 96/96 | FIX-6 |
| `Lab_Verdict` | **removed** | 96/96 | FIX-8 |
| `Vetoes_Count` | blank → `0` | 96/96 | FIX-1 |
| `EIL_Raw_Verdict` | blank → populated | 96/96 | FIX-2 |
| `EIL_Composite` | blank → populated | 96/96 | FIX-2 |
| `EV` | 4dp → 8dp, sign restored on 4 rows | 96/96 | FIX-4 |
| `Direction` | false CALL/PUT → blank for STRANGLE rows | 44/96 | FIX-5 (incl. the EOD-candidate-manifest guard found in verification) |
| `Instrument` | reverts from a repaired-but-wrong label to Phase 7's raw pick | 15/96 | FIX-5 (side effect — direction-sync no longer runs for these rows) |

**57 of 64 original columns are untouched.** Every changed/added/removed
column above is attributed to exactly one fix. No unattributed change was
found at any point in the sprint — every golden diff, after every single
commit, showed only the column(s) that commit's own test claimed to change.

---

## Audit script delta

| | P0 | P1 | P2 | INFO |
|---|---|---|---|---|
| Audited file (your stated baseline) | 5 | 13 | 1 | 5 |
| Golden baseline (regenerable) | 5 | 12 | 1 | 5 |
| **Final (`lab-v1.1.0`)** | **4** | **10** | 1 | 5 |

Both of your stated baseline numbers fell: **P0 5→4, P1 13→10.**

**The 4 remaining P0 findings, and why each legitimately remains:**
1. *"Eligibility fields not present in export"* — only `live_data_mode` now
   (item 13, Phase 10 owner, explicitly out of scope this sprint).
2. *"5 column(s) are 100% null"* — `Days_To_Trigger`, `Vetoes`, `EIL_Verdict`,
   `MV_Drift_Pct`, `Verdict_Reason`. `Vetoes` is item 12 (Phase 7 owner,
   `contract_validity` never populated). The other four were never any of
   the 8 named fixes — `EIL_Verdict` specifically was excluded from FIX-2 on
   purpose (three candidate upstream fields, no single unambiguous target —
   see the FIX-2 commit message).
3. *"R:R reported as 0 where computable and positive"* — down from 14 to 1
   affected row. The residual is the documented Instrument-based limitation
   below, not a gap in FIX-5 itself.
4. *"Structural_Target on the unprofitable side of the strike"* — down from
   43 to 42 affected rows, same cause.

**Target ("0 × P0 from fixes in scope") met**: every remaining P0 traces to
an item explicitly out of scope (12, 13) or to the documented Instrument
residual, not to any of the 8 fixes underperforming their own stated goal.

### Multi-run check

Only one genuine historical browser export exists anywhere in this repo —
the audited `avshunter_signals_20260731_083130_2026-07-31_1640.csv`. No
second day's real export survives to compare against. Two run folders have
complete enough data to regenerate from (`20260731_083130`,
`20260723_072618`); the other two run folders present (`20260723_071559`,
`20260731_081843`) lack `eil_enriched` output entirely and can't be
regenerated.

Regenerated both complete runs at `lab-v1.1.0` and ran `lab_qa_audit.py`
against both:

| Run | Rows | P0 | P1 | P2 | INFO |
|---|---|---|---|---|---|
| `20260731_083130` | 96 | 4 | 10 | 1 | 5 |
| `20260723_072618` | 148 | 4 | 10 | 2 | 5 |

Identical P0/P1/INFO across a 54%-larger row count from a different day, and
the residual RR-zero/wrong-side-target counts scale proportionally with row
count (67/46 affected vs. 42/31 on the smaller run — ratio ≈1.5–1.6, matching
the row-count ratio). This is exactly what "systemic, not a one-day
artifact" looks like.

---

## Blast radius (FIX-5, the largest fix)

Real run `20260731_083130`, default `INCLUDE_LABELLED` policy, 96-row default
queue:

| | Before | After |
|---|---|---|
| Direction | PUT 63 / CALL 33 | PUT 34 / CALL 18 / **blank 44** |
| Verdict | GO 62 / CONTRACT_REPAIR 29 / ARMED 5 | unchanged |
| Priority_Rank order | — | 0 rows changed (enforced by test) |

Row counts by policy, full 952-signal universe / 96-row default queue:

| Policy | Signals in dataset | Visible by default |
|---|---|---|
| `INCLUDE_LABELLED` (default) | 952 | 96 (44 of these are STRANGLE, correctly labelled) |
| `FLAG_ONLY` | 952 | 52 (44 demoted to audit-only, still recoverable) |
| `EXCLUDE` | 752 | 52 (200 STRANGLE rows removed universe-wide) |

---

## UAT results

Full path tested: real Lab server, real browser, real click — not just the
code path.

1. **Restart.** The server that had been running since 2026-07-31 16:34 —
   almost certainly the same long-lived process the Phase 0.3 cache
   investigation was about — was stopped and a fresh one started.
   `/api/health` responded 200 immediately.
2. **UI load.** Renders correctly, real data, no layout issues. **One
   console error found**, pre-existing and unrelated: a `SyntaxError` in
   `AVSHUNTER_sector_ui_patch.js`, an *untracked* file (never in git, never
   touched by this sprint) that has apparently never successfully parsed —
   not fixed here, out of scope.
3. **Row count.** 96 rows, confirmed via direct query — matches exactly.
4. **Export button vs. automated regeneration.** First attempt surfaced a
   genuine tooling gap (see "what I could not do" below) that needed your
   input to unblock (Chrome's save-file dialog + a folder name). After that:
   **0 columns differ** between a real downloaded file and the automated
   regeneration. Also caught and killed two duplicate Lab server processes
   left over from my own restart attempts — a real, if self-inflicted,
   reminder of exactly the concurrent-process risk this sprint's cache fix
   exists to guard against.
5. **Filters.** `EV > 0`: 96→89 rows, matching ground truth exactly (7
   rows excluded, including all 4 known negative-EV tickers from FIX-4).
   `R:R > 0` combined with `EV > 0`: 96→47, matching ground truth exactly.
6. **Five-row spot check** (T/PUT, JPM/STRANGLE, TRV/CONTRACT_REPAIR,
   VZ/ARMED — `Vetoes_Count` is `0`, not blank, on all four, satisfying that
   criterion without needing a fifth pick): every value coherent with its
   neighbours. VZ in particular exercises three fixes in one row:
   `EV = -0.00006700` (FIX-4's precision keeps the negative sign visible),
   `Vetoes_Count = 0` not blank (FIX-1), and `Lab_Action_Bucket_Label =
   ACTIONABLE` despite `Verdict = ARMED` (FIX-7 correctly exposing exactly
   the rank/verdict mismatch this fix was built to surface).

**A significant correction came out of step 4** — see below.

---

## Known limitations carried forward

- **Instrument-based RR/target-side residual** (Phase 2 known limitation,
  confirmed still present in the final audit delta). `lab_qa_audit.py`'s
  RR-zero and wrong-side-target checks key off `Instrument`, which still
  carries Phase 7's single-leg pick for STRANGLE rows. Recommendation
  (not implemented): expose `target_in_play`/`call_wall`/`put_wall` so a
  genuine "no edge" zero, a "wall-capped" zero, and a "non-directional,
  Instrument doesn't apply" zero become distinguishable.
- **Item 12** — `contract_validity` never populated upstream (Phase 7 owner).
  `Vetoes`/`Vetoes_Count` are honest now but still empty/zero on every row.
- **Item 13** — `live_data_mode` absent from the export (Phase 10 owner).
- **`Horizon_Action`/`Horizon_Pressure`/`Horizon_Source`/`Trigger_Price`/
  `Trigger_Display`/`Trigger_Evidence`/`Trigger_Score`/`Trigger_Primary`/
  `Trigger_Quality`/`Trigger_Codes` are always blank in the real export** —
  see the correction below. Not fixed this sprint; recommended for a future
  one.
- **`NEGATIVE_RR` possible dead code** — noted in Phase 0, not chased, per
  instruction.
- **Single source of truth for direction resolution** — your explicit ask
  after the second FIX-5 defect. Discovery, Options Intelligence, morning
  candidates, EIL, and the Lab each resolve "direction" independently today.
  This is a real, larger initiative spanning Phase 5/7/10 code this sprint
  was explicitly told not to touch. **Recommendation:** a dedicated sprint
  to (a) enumerate every phase that independently computes a direction/side
  field, (b) pick one phase as authoritative, (c) have every other phase
  either defer to it or explicitly flag disagreement rather than silently
  recomputing. Not started here.
- **Item 8** — moving the export server-side. Explicitly out of scope.
  Noted extra motivation from this sprint's UAT: the two export routes
  (client `exportCSV()` vs. server `_load_run()`+`_slim_lab_payload()`)
  agree today, confirmed byte-for-byte, but they are still two independently
  maintained code paths that happen to agree — nothing structurally
  prevents them from drifting apart again.

---

## What I could not do, and why (not a failure section)

- **Could not click the export button through pure automation on the first
  attempt.** Chrome's native "ask where to save" dialog sits outside what
  browser automation can see or interact with — this is a real tool
  limitation, not something I could work around. Needed you to disable that
  setting and name a destination folder. Once done, the rest of Phase 4.2
  proceeded without further intervention.
- **Could not reach `chrome://settings` via automation** to make that change
  myself — the tool explicitly blocks navigation to browser-internal URLs.
  Also chose not to hand-edit Chrome's profile `Preferences` JSON directly:
  two profiles exist on disk ("Default", "Profile 1") and I could not safely
  confirm which one was live without risking corrupting whichever one was
  actually in use.
- **Hit real, unexplained browser-automation instability** mid-session (a
  tab's viewport stuck at 472×36px, tab-group membership briefly confused
  twice). Worked around it by creating fresh tabs rather than continuing to
  fight the stuck one — did not chase a root cause, since the tool itself
  isn't in scope for this sprint.
- **Cannot verify the fixes across more than two runs' worth of real data.**
  Only one genuine historical browser export exists in this repo; only two
  run folders have complete enough data to regenerate from at all.

---

## A significant correction, found in this phase

My Phase 0.3 diagnosis was wrong. I attributed the Horizon_Action/Trigger_*
reproducibility gap to a cache-staleness bug in `_lab_cache_signature()` and
shipped FIX-CACHE for it at ~75% confidence. Comparing a real,
freshly-downloaded browser export against my regeneration script during this
phase's UAT — on a server I had *just* restarted, ruling out staleness —
showed the gap was still there. The real cause: `/api/run/<run_id>` always
routes `_load_run()`'s output through `_slim_lab_payload()`, an explicit
field whitelist that drops those specific fields before they ever reach the
browser (`eod__` is missing from the allowed-prefix list; several bare field
names aren't on the base whitelist either). This is deterministic, by-design
filtering — not staleness.

FIX-CACHE remains a real, valid fix for a genuinely separate bug (if
`eil_enriched`/`options_intelligence` are rewritten while a Lab session is
already running, the pre-fix code really would serve stale data forever). It
simply never explained *this* symptom, and could not have fixed it. Full
detail and the corrected diagnosis are in `BASELINE.md`'s correction section
(added rather than silently edited into the original text). The regeneration
script itself is fixed (`11fddc2`) and is now byte-for-byte accurate against
the real export.

I'm flagging this here as prominently as any of the numbered fixes, because
it's exactly the kind of thing this sprint's "test before code, verify
against the real thing" discipline is supposed to catch — and it did, just
one phase later than it should have.

---

## Rollback procedure — tested in both directions

```
# Revert just the two Lab source files to the pre-sprint baseline:
git checkout lab-v1.0.0-baseline -- intelligence-lab/intelligence_lab.py intelligence-lab/static/index.html

# Or revert the entire working tree to that tag:
git checkout lab-v1.0.0-baseline
```

Tested before tagging `lab-v1.1.0`: ran the first command, confirmed
`git diff` against the tag was empty (byte-identical), then ran
`git checkout lab-v1.1.0 -- intelligence-lab/intelligence_lab.py intelligence-lab/static/index.html`
and confirmed the working tree was clean again. A real rollback additionally
requires restarting the Lab server so it re-imports the reverted file — the
server does not hot-reload source changes.

---

## Handoff readiness (Phase 4.4)

**Every column added, changed, or removed this sprint**, and whether
`pipeline_interpreter` consumes it (checked by grep before every fix that
touched a shared name, and again here as a final sweep across the whole
`pipeline_interpreter` directory, including `automation_v2`):

| Column | Change | Consumed by interpreter? | Interpreter-side change needed? |
|---|---|---|---|
| `Trade_Idea_Id` | added | No | No |
| `Options_Direction` | added | No | No |
| `Lab_Coherence_Status` | added | No | No |
| `Lab_Action_Bucket_Label` | added | No | No |
| `Vol_Tailwind_State` | added | No | No |
| `Lab_Verdict` | removed | Yes — `lab_reconciliation.py`, `_LAB_CONTEXT_FIELDS`, display-only, no branching. Degrades gracefully (missing key silently skipped; `Verdict` still carries the identical value). | No |
| `Vetoes_Count` | blank→`0` | Not found in any interpreter file | No |
| `EIL_Raw_Verdict` / `EIL_Composite` | blank→populated | Not found (only bare `EIL_Verdict`, untouched this sprint, is referenced) | No |
| `EV` | 4dp→8dp | Yes — `automation_v2/lab_batch.py:50` reads it as a raw string and stores it verbatim (`ev_predicted`); never parsed for length/format. Safe. | No |
| `Direction` | false CALL/PUT→blank for 44/96 rows | Yes — `automation_v2/lab_structured.py` (alias-merge, explicitly skips blank/None sources) and `automation_v2/renderers.py` (`value()` helper renders blank as `"NOT AVAILABLE"`). Both already handle a missing `Direction` gracefully — confirmed by reading the actual skip/fallback logic, not assumed. A STRANGLE row now renders "NOT AVAILABLE" instead of a fabricated CALL/PUT, which is a **correctness improvement** for this consumer too. | No |
| `Instrument` | reverts on 15/96 rows | Yes — same two files, same graceful-fallback pattern, same conclusion. | No |
| `Vol_State` | unchanged this release (kept deliberately) | Yes — `lab_reconciliation.py`, display-only | No (that's why FIX-6 didn't hard-rename it) |

**No change in this sprint breaks the handoff.** The one column whose
removal (`Lab_Verdict`) and whose value-change on many rows (`Direction`)
touch real interpreter code were both checked against the actual consuming
code, not assumed safe — in both cases the existing code already tolerates
a missing/blank value by design.

---

## Deploy confirmation

`lab-v1.1.0` is tagged at `ab8cb9f392b8ff7baf2547635cb68e0fdc27a97c`. The Lab
server on `localhost:5002` was restarted after the last fix commit and its
running `intelligence-lab/intelligence_lab.py` / `static/index.html` are
confirmed byte-identical to the tag (`git diff --stat lab-v1.1.0 -- ...`
empty). The end-to-end run can proceed against this version.
