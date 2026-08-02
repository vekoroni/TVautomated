# Intelligence Lab — Version 1 Baseline

Established per Phase 0 of `CLAUDE_CODE_TASK_lab_fix_sprint.md`. Every measurement
in this sprint is relative to what is recorded here.

---

## CORRECTION (found during Phase 4.2 UAT, 2026-08-02) — the 0.3 diagnosis below is wrong

Section 0.3 diagnoses the Horizon_Action/Trigger_* reproducibility gap as a
cache-signature staleness bug and reports the fix at ~75% confidence. **That
diagnosis is incorrect.** The real cause, found while diffing an actual
browser-exported CSV against this script's output during UAT:

`intelligence_lab.py`'s `/api/run/<run_id>` route never returns `_load_run()`'s
raw output — it always passes it through `_slim_lab_payload()` →
`_compact_lab_signal()` (`intelligence_lab.py:1996-2053`), which keeps only
fields on an explicit whitelist (`_LAB_COMPACT_BASE_FIELDS`) or starting with
an allowed prefix (`opt__`, `wbs__`, `garch__`, `mv__`, `doss__`, `display_`,
`lab_`, `sb_`, `ev2_`, `mv_`, `tce_`, `qomega_`, `eil_`). Bare `horizon_action`,
`trigger_score`, `trigger_primary`, `trigger_quality`, `trigger_codes`,
`trigger_price`, `days_to_trigger`, `horizon_pressure`, `horizon_source` are on
neither list, and `eod__` is conspicuously absent from the allowed-prefix list
(every other phase's join prefix is there). The browser's `loadRun()`
(`static/index.html:661`) calls `fetch(`${API}/run/${runId}`)` with no `?full=1`
override, so it always gets the slimmed version. This is deterministic,
consistent, by-design filtering — not staleness. Confirmed by running the
regeneration script five times in a row with zero Lab server running: fully
deterministic, matching neither the "stale" nor "fresh" story from 0.3, and
by fetching `/api/run/20260731_083130` directly, which returns these fields
as `None` (absent from the dict entirely, not merely empty) on a guaranteed-
fresh server process.

**What this means for the rest of this document:** the FIX-CACHE fix in
Phase 1 (`_lab_cache_signature()` now fingerprints `eil_enriched`/
`options_intelligence`) is still a real, valid fix for a genuine latent bug —
if those files are rewritten while a Lab server session is already running,
the old code really would serve stale data forever. It just was never the
explanation for *this* symptom, and did not and could not fix it, because
`_slim_lab_payload` filters on every request regardless of caching.

**What this means for `tests/golden/regenerate_lab_export.py`:** the version
used to freeze `lab_export_baseline_20260731_083130.csv` and used throughout
Phases 1–3 called `_load_run()` directly, bypassing `_compact_lab_signal()`
entirely — so it showed these 10 fields as populated when the real browser
export always shows them blank. **This did not affect the validity of any of
the 8 fixes** — none of them touch these fields or the slimming logic, and
every fix was independently re-verified in Phase 4.2 against both a corrected
regeneration and a real browser click, with zero discrepancy on any of the 8
fixes' columns. The frozen baseline CSV itself is left unchanged (it is a
tagged, referenced artifact; rewriting it now would falsify sprint history) —
this note is the correction. The script has been fixed going forward: it now
calls `intelligence_lab._compact_lab_signal()` on every signal, exactly as the
real API route does, so it is byte-for-byte identical to a real browser
export today.

**New finding, correctly diagnosed, not fixed (out of scope — same shape as
LAB_QA_REPORT.md F4/F9, "Lab holds it, drops it before export"):** the Lab
computes full Horizon_Action/Trigger_* detail internally and then discards it
at the API layer before it ever reaches the browser. Recommended for a future
sprint: either add `eod__` to `_LAB_COMPACT_PREFIXES` and the missing bare
names to `_LAB_COMPACT_BASE_FIELDS`, or confirm deliberately that these fields
are intentionally internal-only and stop expecting them in the export.

---

## 0.1 — Code state

The working tree carried uncommitted changes in `intelligence-lab/intelligence_lab.py`
and `intelligence-lab/static/index.html` predating this sprint (and predating the
audit — they were not made by the auditor). Diff was shown to and confirmed by the
user before committing.

**Commit:** `1c547d706201dce7523a1f9c71f4df207f9586dc`
**Tag:** `lab-v1.0.0-baseline` (annotated tag object `27626306d228b28aaf2154afb63ed55798087083`)

What that commit contains, in brief:
- `intelligence_lab.py`: expanded `_normalise_macro()` fields for the Macro tab;
  `_is_lab_audit_only()`, `_display_execution_mode_for()`, `_display_campaign_for()`
  gain handling for a `NEGATIVE_RR` verdict literal.
- `static/index.html`: new `NEGATIVE_RR`/`EOD_CAUTION` client-side verdict overlays
  in `finalLabVerdict()`; new `Trigger_Price`/`Trigger_Display`/`Trigger_Evidence`
  columns and helpers; `cleanUiHtml()` mojibake cleanup; de-duplicated
  `getSectorDisplay()`/`getEilDisplay()` helpers.

**Open question carried forward, not chased:** `NEGATIVE_RR` is computed
client-side from the row's R:R sign. No code path was found that writes the
literal string `"NEGATIVE_RR"` into `sig["lab_verdict"]` server-side, so the three
server-side branches that check for it may be unreachable. Flagged per the sprint
doc's "possible-dead-code question — note it, do not chase it."

---

## 0.2 — Golden reference export

**Mechanism.** The real export is produced by client-side JavaScript
(`exportCSV()` in `static/index.html`) after a human clicks a button in the
browser — there is no server-side export endpoint that produces this file. To
regenerate it deterministically from the command line (required for every
golden-diff check in this sprint), I wrote a line-for-line Python port of
`exportCSV()` and its ~25 helper functions:
`tests/golden/regenerate_lab_export.py`. It calls `intelligence_lab.py:_load_run()`
directly (the same function that backs `/api/run/{run_id}`) and reproduces the
**default, no-interaction browser state**: all filters `'ALL'`, `showAuditRows =
False`, both quick filters off, `campaignViewMode = False`, default sort
`priority_rank` ascending.

This port is a regression tool, **not a replacement source of truth**. Phase 4.2
UAT will click the real export button and diff its output against this script's
output — any divergence there is itself a finding about the two export routes
having drifted apart, not something to paper over.

**Command:**
```
python tests/golden/regenerate_lab_export.py 20260731_083130 --out tests/golden/lab_export_baseline_20260731_083130.csv
```

**Output:** 96 rows × 64 columns — an exact shape match with the audited file
(`avshunter_signals_20260731_083130_2026-07-31_1640.csv`, also 96×64), which is
itself a strong signal the default-filter/default-sort reproduction is correct:
of 952 handoff-slate signals for this run, exactly 96 survive
`isAuditOnlySignal()` filtering in both the real July 31 export and today's
regeneration.

**SHA-256:**
```
tests/golden/lab_export_baseline_20260731_083130.csv
  9654044ec26ba094e46bd774fb84a3d716c4db727265735d7a9ce9c6ce0ed49b

avshunter_signals_20260731_083130_2026-07-31_1640.csv  (audited file, for reference)
  914b0d5dfe5afcfb00a19e66eec5ce10d9f9fe7a0f2a62d04f717735793eefc0
```

### Quantified delta — audited file vs. regenerated file

Same 96 tickers, same 64 columns, same column names, both directions checked.

**54 of 64 columns are byte-identical on all 96 rows.** 10 columns differ:

| Column | Rows differing | Direction |
|---|---|---|
| `Horizon_Pressure` | 96/96 | empty → populated |
| `Trigger_Price` | 96/96 | empty → populated |
| `Trigger_Display` | 96/96 | empty (`-`) → populated |
| `Horizon_Action` | 52/96 | empty → populated |
| `Horizon_Source` | 52/96 | empty → populated |
| `Trigger_Primary` | 18/96 | empty → populated |
| `Trigger_Quality` | 18/96 | empty → populated |
| `Trigger_Codes` | 18/96 | empty → populated |
| `Trigger_Evidence` | 96/96 | populated → **different** populated value |
| `Trigger_Score` | 96/96 | `55.0` (constant) → real per-row value (`0.0`/`2.0`/`3.5`/etc.) |

**Zero rows regress in the other direction** (populated → empty) on any column,
and zero columns outside this list of 10 differ at all. This is a strictly
one-directional gap: fields null in the audited file come back either populated
or differently-valued today; nothing that was populated in the audited file has
gone missing.

---

## 0.3 — Reproducibility diagnosis

**Cause identified with moderate-high confidence (75%): an incomplete server-side
cache-invalidation fingerprint, not files being overwritten after the fact, and
not the code having changed.**

Evidence ruling out the two other candidate causes named in the task:

- **Not files overwritten in place after the fact.** File modification times on
  every source artifact the Lab reads for this run predate the export:
  `eil_enriched_20260731_083130.csv` (11:56), `options_intelligence_latest.csv`
  (11:09), `trigger_layer_summary_20260731_083130.csv` (11:29),
  `morning_validated_trades_20260731_083130.csv` (15:21) — all before the export
  file's timestamp (~16:40–17:40). None of these files has been touched since
  31 July. If they had been silently rewritten after the export, at least one
  mtime would postdate it. None does.
- **Not the uncommitted code diff.** `intelligence_lab.py` and `static/index.html`
  both carry a last-modified date of 23 July — a full week before this run —
  and the diff shown and committed in 0.1 does not touch any of the
  trigger/horizon field-extraction logic responsible for the 10 differing
  columns (it touches macro normalisation and NEGATIVE_RR/EOD_CAUTION verdict
  logic only). The audited file already contains the `Trigger_Price`/
  `Trigger_Display`/`Trigger_Evidence` columns that only exist because of this
  diff, confirming the same code (or an equivalent version of it) was active
  on 31 July — so this is a same-code, different-data problem, not a
  different-code problem.

**Most likely mechanism:** `intelligence_lab.py:_lab_cache_signature()` (lines
143–149) fingerprints only the morning-validation handoff paths
(`morning_validated_trades_*`, `morning_validation_packet_*`,
`morning_candidates_*`) to decide whether the in-memory `_run_cache` for a
run_id is stale. It does **not** include `eil_enriched_*.csv`,
`options_intelligence_latest.csv`, or `trigger_layer_summary_*.csv` in that
fingerprint. If a human had the Lab open in a browser tab earlier in the 31 July
pipeline run — before those files reached their final, fully-enriched state —
the first `_load_run()` call would cache a signal dict built from
still-partial data. Every later request for that run_id, including the one
behind the 16:40 export, would keep serving that stale cached copy, because the
signature check never notices that `eil_enriched`/`options_intelligence`/
`trigger_layer_summary` changed underneath it — only a change to the
morning-validation files (which arrived later, at 15:21, and did correctly
trigger a partial refresh: `mv__*`-sourced fields are not among the 10 differing
columns) invalidates the cache.

This matches all direct evidence: the 10 differing columns are precisely fields
sourced from `eil_enriched`/`options_intelligence` enrichment (trigger layer,
horizon routing) — exactly the kind of late-arriving, incrementally-populated
columns a stale early-run cache snapshot would miss — while every column sourced
from morning-validation data or present in the earliest EIL rows matches exactly.

**What I could not confirm:** no server log survives from the 31 July Lab
session (`intelligence-lab/server_start.log` on disk is a stale log from an
unrelated 8 May session) to directly prove a browser tab was open and caching
during that run. This diagnosis is inferential — consistent with all available
evidence and requiring no other explanation, but not directly observed.

**Recommendation (not implemented — this is a cache-completeness fix, not a
one-line path bug, so per the phase-0 instruction I am reporting and asking,
not fixing):** add the `eil_enriched`, `options_intelligence_latest`, and
`trigger_layer_summary` file paths to `_lab_cache_signature()`'s fingerprint
dict, the same way the morning-validation paths already are. This is a small,
well-localized change (~5 lines in one function) but touches the caching
behavior of the entire Lab, so I'd like a decision on whether to fold it into
this sprint (it isn't one of the 8 numbered FIX items) or raise it as its own
ticket for a later sprint.

---

## 0.4 — Test harness

**pytest availability.** Not installed anywhere in the environment (checked the
system Python, the root `venv`, and `intelligence-lab/venv`). Installed
`pytest` (9.1.1) into the project's root `venv` — a standard, reversible
dev-dependency addition, not a source change. `pandas`/`numpy` (needed by
`lab_qa_audit.py`) were already present in that venv.

**A pre-existing environment issue, not something I introduced or fixed:**
running `pytest tests/` as a single invocation crashes with
`ValueError: I/O operation on closed file` inside pytest's own capture-manager
teardown (`_pytest/capture.py`), independent of which tests pass or fail. This
reproduces even under `--collect-only` (collection succeeds — 96 items — then
the crash fires during session teardown) and is **not** a scale/many-files
artifact: two individual files
(`tests/test_macro_enrichment_discovery_options.py`,
`tests/test_options_research_contract.py`) trigger the identical crash on their
own, at collection time, before any test in them runs. A trivial one-line test
file outside the repo runs cleanly under the same pytest/Python install, which
rules out a broken pytest installation.

I did not debug further — the two crashing files are unrelated to the
Intelligence Lab (macro enrichment discovery and options research contract
areas) and diagnosing a Windows console/capture interaction in them is outside
this sprint's scope. Reported as a baseline fact per the phase-0 instruction.

**Workaround used to get a real baseline number:** ran each of the 49 files
in `tests/` as a separate `pytest` invocation (this avoids the crash — every
file runs fine in isolation except the two named above) and summed the
results.

**Baseline pass/fail count (47 of 49 files ran to completion):**

| | Count |
|---|---|
| Passed | 215 |
| Failed | 13 |
| Errors | 3 |
| Could not run (pre-existing collection crash, unrelated files) | 2 files, test count unknown |

Files with real (non-crash) failures, for the record — none are Lab files, all
pre-exist this sprint: `test_big_bang_phase_6_7.py` (1 failed),
`test_eod_options_research_handoff.py` (1 failed), `test_lab_journal_handoff.py`
(2 failed), `test_level1_20260512_regressions.py` (1 failed, 3 errors),
`test_macro_enrichment_delta.py` (1 failed), `test_morning_thesis_validator.py`
(2 failed), `test_pse_retired_authority.py` (5 failed).

None of these 13 failures + 3 errors are in Lab-related test files. Per the
sprint doc: "a pre-existing failing test is a baseline fact, not something to
fix now." Phase 1+ exit criteria ("full test suite pass count ≥ Phase 0
baseline") will be checked against **215 passed**, using the same per-file
workaround.

**`lab_qa_audit.py`.** Already present at `tests/lab_qa_audit.py` (812 lines) —
no copy needed, step already satisfied.

**Baseline finding counts — and a discrepancy to flag:**

| Input | P0 | P1 | P2 | INFO |
|---|---|---|---|---|
| Audited file (`avshunter_signals_..._1640.csv`) | **5** | **13** | 1 | 5 |
| Golden regenerated file (`lab_export_baseline_20260731_083130.csv`) | **5** | **12** | 1 | 5 |

P0 is identical (same 5 titles, both files) — the material defects this sprint
fixes are stable regardless of which file is used as the reference. The single
P1 difference is fully attributable to the reproducibility gap quantified in
0.2: the audited file trips `HARDCODED_DEFAULT` ("1 numeric column(s) constant
on every row") because `Trigger_Score` is `55.0` on all 96 rows; the golden
file does not trip it, because `Trigger_Score` is no longer constant once the
real per-row trigger-layer values are present. Confirmed by diffing the two
runs' finding titles directly — this is the only line that differs.

**You told me the current baseline is P0=5, P1=13 — that matches the audited
file exactly.** Going forward, Phase 1+ fixes will only ever be tested against
the **golden regenerated file** (the audited file is a frozen historical
artifact that cannot be regenerated through code changes). That means the
number this sprint tracks down from is **P0=5, P1=12**, not 13 — the 13th
finding is a property of the reproducibility gap, not something any of the
eight numbered fixes touches. Flagging this now so the tracked number doesn't
look like it moved for an unexplained reason later. If you'd rather track
against 13 by folding the cache-signature fix (0.3) into scope, say so and I'll
adjust.

---

## Phase 0 exit criteria

- [x] Code tagged `lab-v1.0.0-baseline`, SHA recorded — `1c547d706201dce7523a1f9c71f4df207f9586dc`
- [x] Golden export frozen and hashed
- [x] Delta between audited file and regenerated file quantified
- [x] Reproducibility cause identified (cache-signature completeness gap, 75% confidence, evidence-based, not directly log-confirmed)
- [x] Test suite baseline pass/fail count recorded — 215 passed / 13 failed / 3 errors / 2 files uncollectable (pre-existing, unrelated to Lab)
- [x] `lab_qa_audit.py` baseline finding counts recorded — P0=5/P1=13 (audited file) vs. P0=5/P1=12 (golden file, the one Phase 1+ will track)
