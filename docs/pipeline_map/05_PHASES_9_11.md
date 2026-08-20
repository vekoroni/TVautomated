# Pass F — GARCH, Handoff Guard, Catalyst Truth, McMillan, Morning Manifest, Diagnostics

Read-only audit. No files edited, no pipeline phase executed. All source citations
against `intelligent_orchestrator.py`, `garch_runner.py`, `layer3_forward_variance.py`,
`mcmillan_advisory_layer.py`, `catalyst_truth_engine.py`, `eod_candidate_engine.py`,
`contracts/lab_control.py`, `handoff_contract_audit.py`, and
`scripts/go_live_uat_audit_watch.py` as they exist on disk at time of pass
(working-tree state, uncommitted — same caveat as Passes A-E). Builds on
`00_SPINE.md` (Pass A), `01_PHASES_0_3.md` (B), `02_PHASES_4_6.md` (C),
`03_PHASE_7_OPTIONS.md` (D), `04_PHASES_8_86.md` (E) — cited, not re-derived,
except where a correction is filed explicitly. `STAGE_1_BASELINE_RECORD.md`
(EV3 reconstruction) read and cited, not re-derived.

**Denominators, stated on every percentage:** 3,323 (augmented universe), 1,400
(rows entering Options Intelligence scoring / this span's starting population,
08-18 reference run), 1,135 (rows reaching the terminal `morning_candidates`
manifest, 08-18). All three given, each labelled.

**Reference runs, read directly:** `data/output/runs/20260818_041214/` (1,400
rows in, 1,135 out) primary; `data/output/runs/20260816_075339/` (1,347 in) used
for cross-checks where cited explicitly. All counts below not otherwise marked
came from direct `pandas.read_csv`/`value_counts`/crosstab against the actual
artefacts in these directories, or from direct JSON reads of the archived
diagnostic outputs — nothing is inferred from source code alone unless labelled
UNVERIFIED.

**No pipeline code was executed this pass.** All Python invocations used were
read-only `pandas`/`json` analysis of already-archived artefacts (equivalent to
manual inspection with a calculator) — no orchestrator phase, no module under
audit, was run.

---

## F1 — GARCH and the retroactive patch

### Module / function

**Runner (subprocess):** `garch_runner.py` (`run_garch_batch()`, `:279-345`),
invoked as `python garch_runner.py <run_id> --superbrain_csv ... --output_dir ...`
by `run_garch_layer()`, `intelligent_orchestrator.py:2719-2749` (item 29a,
labelled "PHASE 10a" in code comments). Non-critical (`_run(..., critical=False)`,
`:2746`); missing `garch_runner.py` or missing `superbrain_enriched` CSV both
short-circuit with `return True` (`:2731-2738`) — GARCH is unconditionally
skippable without affecting the evening run's own control flow.

**Merge (in-process):** `merge_garch_into_enriched()`,
`intelligent_orchestrator.py:2752-2882` (item 29b, "PHASE 10b"), called
immediately after `run_garch_layer()` at `:4235-4236`.

**Invoked by:** `evening_workflow()`, `intelligent_orchestrator.py:4235-4236`
(item 29 in Pass A/E's ordering — after EIL, item 27; after the actuarial
safety net, item 28; before Trigger Layer CSV enrichment, item 30; before the
Handoff Conflict Guard, item 31).

**Conditional on:** `garch_script.exists()`, `superbrain_enriched` CSV exists
(runner); `garch_forecasts` and `superbrain_enriched` CSVs both exist (merge).
All four conditions were true in both reference runs.

**Output non-empty in ref runs:** Yes. `garch_forecasts_20260818_041214.csv`:
1,400 rows, one per unique ticker. `garch_forecasts_20260816_075339.csv`:
UNVERIFIED row count this pass (not re-read; Pass E already established
1,347-row parity across this span).

### GARCH's own inputs — confirmed independent of anything running after it

Read directly from `garch_runner.py`:

1. **Ticker list**: `sb_df['ticker'].dropna().str.upper().str.strip().unique()`
   from `superbrain_enriched_{run_id}.csv` (`:302-303`) — upstream artefact,
   written at item 22 (SuperBrain passthrough), long before GARCH runs.
2. **Price history**: live Polygon API call per ticker, fetched at GARCH's own
   execution time (`_fetch_ohlcv()`, `:75-111`) — not read from any pipeline
   artefact at all; external, real-time data.
3. **IV**: `_build_iv_map()` (`:151-179`) reads `implied_vol`/`contract_iv`
   from `options_intelligence_{run_id}.csv` — an artefact written at item 17,
   also well before GARCH.
4. **Regime**: `_load_regime()` (`:116-146`) reads `regime_state` from
   `macro_intelligence_latest.json` at one of four candidate paths — a
   standing macro artefact refreshed earlier in the evening run (Phase
   "Bond Macro Sidecar"/macro normalisation span, Pass B/C), not something
   GARCH itself or any later phase writes.

**None of GARCH's own inputs depend on anything that runs after it in the
evening workflow.** The headline defect (below) is entirely about GARCH's
*output* arriving too late for one specific consumer (EIL), not about GARCH's
own inputs being incomplete or circular.

### Fields patched — exact list, corrected against the code's own docstring

`merge_garch_into_enriched()`'s docstring (`:2763-2772`) lists **9** `l3_`
fields. The actual mechanism (`:2799`) is `l3_cols = [c for c in
garch.columns if c.startswith("l3_")]` — dynamic, not the hardcoded 9.
Cross-checked against `ForwardVarianceResult.to_dict()`
(`layer3_forward_variance.py:117-151`), the real output is **16** `l3_`
fields: `l3_forward_realised_vol`, `l3_vol_forecast_conf`,
`l3_expected_move_1_5d`, `l3_expected_move_6_10d`, `l3_expected_move_11_20d`,
`l3_iv_tailwind_score`, `l3_iv_tailwind_score_capped`, `l3_jump_risk_flag`,
`l3_method`, `l3_garch_alpha`, `l3_garch_beta`, `l3_n_bars`,
`l3_model_risk_flags`, `l3_model_risk_flag_count`,
`l3_model_risk_capital_guard`, `l3_error`. Confirmed empirically: all 16
appear as columns in `garch_forecasts_20260818_041214.csv`,
`superbrain_enriched_20260818_041214.csv`, `eil_enriched_20260818_041214.csv`,
and `execution_v3_5_20260818_041214.csv` alike. The docstring's field list is
stale (missing 7: `l3_iv_tailwind_score_capped`, `l3_garch_alpha`,
`l3_garch_beta`, `l3_n_bars`, `l3_model_risk_flags`,
`l3_model_risk_flag_count`, `l3_model_risk_capital_guard`) — a minor,
harmless documentation/code drift, not a functional defect.

### Mechanism — ticker-keyed left merge, not positional, confirmed row-safe

`merge_garch_into_enriched()` does, for each of **three** targets in turn
(corrected count — see next section):
```
existing_l3 = [c for c in target.columns if c.startswith("l3_")]
target = target.drop(columns=existing_l3)        # avoid _x/_y suffix collision
merged = target.merge(garch_slim, on="ticker", how="left")
merged.to_csv(target_path, index=False)           # full overwrite, in place
```
This is a **column-drop-then-left-merge on `ticker`**, not a positional
column assignment. Row alignment is therefore governed by merge-key
uniqueness, not row order. Verified empirically, both preconditions hold in
the reference run: (1) `garch_forecasts_{run_id}.csv` has exactly one row per
ticker (1,400 unique tickers / 1,400 rows — `run_garch_batch()`'s own
`.unique()` call at `:303` guarantees this structurally); (2)
`superbrain_enriched`'s `ticker` column is 100%-uppercase, matching the
uppercase-normalised keys GARCH produces (`str(row.get('ticker','')).strip().upper()`
implicitly, per `_process_one_ticker`'s upstream `.str.upper()` call) — so the
merge key never mismatches on case. **Result, confirmed by direct row-count
comparison:** `superbrain_enriched`, `eil_enriched`, and `execution_v3_5` are
all still exactly 1,400 rows after the merge, `l3_method` is non-null for all
1,400 rows in all three files — a clean many-to-one join with 100% match rate
in this run. **The patch preserves row alignment; it does not reindex or
reorder.** This is confirmed, not merely architecturally inferred (row counts
independently re-verified by direct `pandas.read_csv` this pass).

One latent risk, not observed to fire in either reference run: the merge key
match depends on both sides normalising ticker case identically. If any
consumer CSV's `ticker` column ever contains mixed case (not observed here),
rows for that ticker would silently fail to match and get `NaN` `l3_*`
values via the left join's own null-fill — no exception, no log line, just a
quiet non-match. UNVERIFIED against other runs; flagged as a structural risk
in the merge design, not a confirmed defect.

### Three merge targets, not two — a correction/addition to Pass E's E2.5

Pass E's E2.5 documents the merge into `superbrain_enriched.csv` and
`eil_enriched.csv`. **Direct read of `merge_garch_into_enriched()`
(`:2850-2874`) shows a third target: `execution_v3_5_{run_id}.csv`** — merged
identically (drop existing `l3_*`, left-join on ticker, overwrite in place),
guarded the same way (`if execution_path.exists()`, else logged and skipped).
Confirmed populated in the reference run: `execution_v3_5_20260818_041214.csv`
carries all 16 `l3_*` columns, `l3_method` non-null for 1,400/1,400 rows.
This is additive to, not contradicting, Pass E's finding — the fifth
ordering-defect narrative (below) is unaffected, but the blast radius of "how
many artefacts carry retroactively-patched data" is three, not two.

### The ordering defect itself — confirmed exactly as Pass E's E2.5 states, re-verified

Per Pass A/E's confirmed call order, GARCH (item 29) runs strictly after EIL
(item 27) has completed as a **separate subprocess**
(`execution_intelligence_runner.py`, invoked `intelligent_orchestrator.py:2644`)
and already written its final `eil_enriched_{run_id}.csv`. Re-verified this
pass by direct column check: the 627-column `options_intelligence_{run_id}.csv`
and the pre-GARCH `superbrain_enriched.csv` snapshot (inferred — not
independently re-captured pre-merge this pass, since the merge overwrites in
place and no pre-merge snapshot survives on disk; this specific claim is
carried in from Pass E's E2.5, not re-derived) both lack any `l3_*` column, so
`execution_intelligence.py`'s `build_execution_context_from_row()`
(`:649-655`) — which reads `l3_expected_move_1_5d`/`l3_expected_move_6_10d`
first, falling back to `expected_move_10d` — is **structurally guaranteed** to
read the fallback (or `None`) for every one of the 1,400/1,347 rows in both
reference runs, because the columns it wants do not exist in the file it
reads at its own execution time. This is Pass E's E2.5 finding, re-confirmed
rather than re-derived from a fresh read of the merge code (above) plus the
already-established EIL subprocess ordering (Pass E, E2).

### Does anything downstream re-read the patched `l3_*` fields for real work? — Yes, confirmed, with one exception

This is the specific question this pass adds to Pass E's finding. Pass E
established the *negative* result (EIL's own verdict computation never saw
GARCH data). This pass establishes the *positive* result for the artefact
GARCH is patched into: **`eod_candidate_engine.py`'s `build_candidate_manifest()`**
(Phase 10, item 34 — runs strictly after GARCH's merge, item 29, and after
Trigger Layer/Handoff Guard, items 30-31) reads `eil_enriched.csv` **after**
the GARCH patch has already landed in it, and does read `l3_*` fields for
real, non-scoring purposes:

| Consumer | Field(s) read | Purpose | Line |
|---|---|---|---|
| `_exit_intelligence_plan()` | `l3_expected_move_1_5d`, `l3_expected_move_6_10d` (first-match fallback chain) | `expected_move_pct` input to exit target/wall-scale calculation | `eod_candidate_engine.py:1304-1307` |
| candidate dict | same two fields (reversed priority) | `expected_move` manifest field | `:2027` |
| candidate dict | `l3_jump_risk_flag` | `jump_risk_review_required`/`jump_risk_note` manifest flags | `:2119-2128` |
| candidate dict | `l3_expected_move_1_5d`, `l3_expected_move_6_10d`, `l3_forward_realised_vol`, `l3_vol_forecast_conf` | `expected_move_5d`, `expected_move_10d`, `vol_forecast`, `vol_conf` manifest columns | `:2262-2265` |

Confirmed populated with real (non-null, non-fallback) values in the
reference run: `morning_candidates_20260818_041214.csv`'s `expected_move_10d`
and `vol_forecast` columns are non-null for all 1,135 rows (traced back to
`l3_expected_move_6_10d`/`l3_forward_realised_vol`, both 1,400/1,400
populated in `eil_enriched.csv` post-GARCH-merge). **The `l3_*` fields are not
"written into an artefact nobody re-reads."** They are read too late to
influence the one verdict a reader might assume they inform
(`eil_v3_verdict`, fixed before GARCH runs, per Pass E) but they do reach a
real, later consumer (the candidate manifest's exit-planning and
operator-display fields) that runs after the patch and is not
verdict-computation — informational/exit-planning fields only, never a
gating score.

**The one confirmed exception:** `mcmillan_advisory_layer.py` reads three
field names — `l3_iv_percentile`, `l3_iv_rank`, `l3_expected_move_pct` — that
**do not match any of the 16 real `l3_*` output fields** and are written by
**no producer anywhere in the repository** (repo-wide grep: these three
strings appear only inside `mcmillan_advisory_layer.py` itself). This is a
genuine dead-fallback field-name mismatch, detailed in F4 below; it does not
materially matter because earlier candidates in the same fallback chains
(`iv_percentile`/`iv_rank`, `expected_move_10d`/`expected_move_5d`) are
populated and satisfy the lookup first in the large majority of rows (see F4).

### Failure behaviour

Fail-open throughout. Runner: missing script or missing input CSV → `return
True`, log warning, GARCH silently skipped (`:2731-2738`). Batch failure
inside the subprocess: `_run(..., critical=False)` — logged, evening run
continues (`:2746-2748`). Merge: missing `garch_forecasts` or
`superbrain_enriched` → `return True`, skip (`:2787-2792`); no `l3_` columns
in the GARCH CSV → `return True`, skip (`:2800-2802`); any exception during
the merge itself → caught, logged, `return True` (`:2880-2882`) — "GARCH
merge failed ... superbrain_enriched unchanged" is explicitly fail-open by
design, not merely by omission. The per-target `eil_enriched`/`execution_v3_5`
merges are each wrapped in their own inner `try/except` (`:2828-2843`,
`:2851-2872`) so a failure merging into one target does not prevent the
others.

### Dead code on this path

None found. `_audit_garch_result()` (`garch_runner.py:209-246`) is
explicitly documented as audit-only / non-mutating ("always return
unchanged") — not dead, but deliberately a no-op with respect to the data it
inspects; flagged for completeness, not as a defect.

### Open questions

- Whether the ticker-case merge-key risk (mixed-case ticker strings) has ever
  fired in a real run — UNVERIFIED, not observed in either reference run.
- Whether `garch_forecasts_{run_id}.csv`'s 1,400/1,400 (100%) ticker match
  rate is typical or a favourable outlier — no other run's GARCH coverage was
  checked this pass. A ticker that fails `_fetch_ohlcv()` (no Polygon data)
  is silently absent from `garch_forecasts` entirely (`row_dict = None` on
  fetch failure, `garch_runner.py:257-259`), which would show up downstream as
  an unmatched-left-join row (`l3_method` null for that ticker) rather than
  an error — not exercised in either reference run since match rate was 100%.
- `l3_garch_alpha`/`l3_garch_beta` are null for all 1,400 rows in this run
  because `l3_method == 'HAR_RV'` universally (confirmed: `value_counts()`
  shows 100% `HAR_RV`, zero `GARCH`/`EWMA_FALLBACK`/`ATR_PROXY`) — the
  GARCH/EGARCH fallback path inside `layer3_forward_variance.py` was never
  exercised in this reference run; its correctness is untested by this data.

---

## F2 — Handoff Conflict Guard

Two distinct mechanisms share the word "handoff" in this codebase and are
documented separately: an **in-place row-downgrade gate**
(`enforce_handoff_conflict_guard()`) that runs mid-evening-workflow and
mutates `eil_enriched.csv`, and a **read-only column-presence auditor**
(`handoff_contract_audit.py`) that runs near the end of the workflow and
writes a diagnostic report. CLAUDE.md's testing protocol cites a "warn=8,
fail=0" baseline for the latter; both are covered here since the brief names
"Handoff Guard" as the last checkpoint before the manifest.

### F2a — `enforce_handoff_conflict_guard()` — the row-downgrade gate

**Module / function:** `intelligent_orchestrator.py:5334-5424`
**Invoked by:** `evening_workflow()`, item 31, `:4340` — inside the EIL
success branch, **after** GARCH's merge (item 29) and Trigger Layer's CSV
enrichment (item 30), so it reads `eil_enriched.csv` in its fully
GARCH-patched, trigger-enriched state.
**Conditional on:** `eil_enriched_{run_id}.csv` exists and is non-empty (else
`return not _strict_actuarial_v6_enabled()`, `:5340-5347`); resolved
`AVSHUNTER_STRICT_ACTUARIAL_V6` env var, unset in this environment →
`_strict_actuarial_v6_enabled()` returns `False` by default
(`:204-205`, confirmed: `os.environ.get(..., "").strip() == "1"`).
**Output non-empty in ref runs:** Yes — `eil_enriched.csv` rewritten in place
with new/updated `handoff_conflict_flags`, `handoff_status`,
`capital_permission` columns, and (for flagged rows) overwritten
`pse_execution_mode`, `pse_final_size`, `fd_verdict`, `fd_size` values.

**What it reads:** `pse_execution_mode`, `fd_verdict`, `thesis_decision`
(build `exec_mask` — a row is "execution-like" if `pse_execution_mode` is one
of `{PROBE, REDUCED, EXECUTE, FULL_EXECUTE, BUY_NOW, BUY_SMALL, GO}`, or
`fd_verdict` is one of `{EXECUTE, EXECUTE_WITH_CAUTION, GO}`, or
`thesis_decision == "GO"`, `:5349-5357`); `eil_v3_verdict` (→
`eil_blocked` if in `{BLOCKED, BLOCK}`, `:5359`); `trigger_primary`,
`trigger_quality`, `trigger_stale` (`:5360-5363`); and the full
`PHASE2_LAYER2_FIELDS` list (~15 fields, `:208-...`) for actuarial-baton
completeness (`:5365-5380`).

**Four checks, all conjunctive with `exec_mask`** (an execution-like row is
only ever flagged if it ALSO trips one of these):

| # | Check | Condition | severity |
|---|---|---|---|
| 1 | `EIL_BLOCKED_WITH_EXECUTION_MODE` | `exec_mask & eil_blocked` | flags row |
| 2 | `TRIGGER_STALE_WITH_EXECUTION_MODE` | `exec_mask & trigger_stale` | flags row |
| 3 | `TRIGGER_MISSING_WITH_EXECUTION_MODE` | `exec_mask & (trigger_primary empty/NONE/NaN OR trigger_quality empty/NONE/NaN)` | flags row |
| 4 | `PHASE2_BATON_MISSING_WITH_EXECUTION_MODE` | `exec_mask & phase2_missing` (any of 5 critical Phase-2 fields null/blank, or the whole `PHASE2_LAYER2_FIELDS` block absent from the CSV) | flags row |

All four are **fail-open per-row** (a flagged row is downgraded, not dropped)
and **fail-open at the function level by default** (see Failure behaviour).

**Empirical result, both reference runs — only checks 2 and 3 ever fire:**

| Run | Rows | `TRIGGER_STALE\|TRIGGER_MISSING` (both) | `TRIGGER_MISSING` only | Total flagged | % of rows |
|---|---|---|---|---|---|
| 08-18 | 1,400 | 115 | 10 | 125 | 8.9% |
| 08-16 | 1,347 | 101 | 14 | 115 | 8.5% |

`EIL_BLOCKED_WITH_EXECUTION_MODE` and `PHASE2_BATON_MISSING_WITH_EXECUTION_MODE`
fired **zero times** in either run — confirmed by direct `value_counts()` of
`handoff_conflict_flags`, which contains exactly two non-empty string
patterns in both runs (shown above), never a string containing `EIL_BLOCKED`
or `PHASE2_BATON`. The guard's entire real-world footprint in both reference
runs is attributable to stale/missing trigger data on execution-like rows —
never to an EIL/execution contradiction or a missing actuarial baton.

**What a downgrade does, and whether the pre-downgrade value survives:**
`df.loc[conflict_mask, ...]` overwrites, in the same DataFrame that is then
written back to the same path (`df.to_csv(_eil_path, index=False)`,
`:5417`): `handoff_status → "CONFLICT_DETECTED"`, `capital_permission →
"NO"`, `pse_execution_mode → "WATCHLIST"`, `pse_final_size → 0.0`,
`fd_verdict → "WATCHLIST"`, `fd_size → 0.0`. This is a genuine **overwrite**,
not an additive merge like GARCH's — **the pre-downgrade `fd_verdict` and
`pse_execution_mode` values are gone from disk after this function runs; no
side-channel preserves them.** The one recoverable trace: `eil_v3_verdict`
itself is **not** touched by this function, so for a downgraded row,
`eil_v3_verdict` still reflects EIL's original (pre-guard) score — a reader
comparing `fd_verdict` (now `"WATCHLIST"`) against `eil_v3_verdict` (still
e.g. `"EXECUTE_WITH_CAUTION"`) can reconstruct that a downgrade happened, by
the same divergence-reading technique Pass E's E2/E4 already established for
the campaign/execution gate's own override of `eil_v3_verdict`. **Confirmed
downstream propagation:** `build_candidate_manifest()` (Phase 10, item 34,
runs after this guard) reads `eil_enriched.csv` fresh and its `"fd_verdict":
_str(row, "fd_verdict") or _str(row, "eil_v3_verdict")` (`eod_candidate_engine.py:2126`
region, confirmed at the line cited in F5 below) picks up the
post-downgrade `"WATCHLIST"` value for all 125/115 downgraded rows.

**Critical/fail-closed status — confirmed conditional, not unconditional, and
never actually triggered in either reference run.** Pass A flagged this call
site as unconditionally critical (`if not ...: return False`). Direct read of
the guard's own body shows the abort condition is narrower:
```python
if _strict_actuarial_v6_enabled() and (conflict_mask.any() or missing_phase2_fields):
    return False
```
(`:5418-5420`). With `AVSHUNTER_STRICT_ACTUARIAL_V6` unset (this
environment's resolved default, confirmed at `:204-205`, no override found in
any prior pass of this sequence), `_strict_actuarial_v6_enabled()` is
`False`, so **this branch cannot execute regardless of how many rows
conflict** — the function always returns `True` in this configuration, even
with 125/1,400 (8.9%) rows flagged. Pass A's "Critical" label is accurate as
a statement about what the code *can* do under the strict flag, but **in the
configuration both reference runs actually used, this gate never aborts** —
a correction/refinement to Pass A §2.2 item 31, not a contradiction (Pass A
correctly identified the code path exists; this pass establishes it is
dormant under the observed default).

**Exception handling:** the entire function body is one `try/except`
(`:5336`/`:5422-5424`); any unhandled exception is caught, logged, and
returns `not _strict_actuarial_v6_enabled()` — i.e. `True` (fail-open) under
the observed default, `False` (fail-closed) only under strict mode. Neither
reference run exercised this path (no exception observed — `eil_enriched.csv`
was successfully rewritten with the guard's columns in both).

### F2b — `handoff_contract_audit.py` — the column-presence auditor

**Module / function:** `audit_run()` (not read line-by-line this pass beyond
its output schema and the ~167-check field-contract table at
`handoff_contract_audit.py:38-115+`, which enumerates required/optional
columns per stage with a `WARN`/`FAIL` severity each).
**Invoked by:** `evening_workflow()` item 38, `intelligent_orchestrator.py:5080-5091`
(near the end of the run, after the candidate manifest, McMillan, and the
Pipeline Integrity report have already been written).
**Output non-empty in ref runs:** Yes —
`diagnostics/handoff_contract_audit_{run_id}.csv` and `.json`.

**Empirical pass/fail/warn counts, both reference runs, read directly from the
archived JSON (not re-run):**

| Run | `fail_count` | `warn_count` | `overall_status` | `status_counts` |
|---|---|---|---|---|
| 20260818_041214 | 0 | **12** | WARN | OK=154, PRESENT_BUT_EMPTY=12, EXPECTED_NOT_RUN_EOD=1 |
| 20260816_075339 | 0 | **12** | WARN | OK=154, PRESENT_BUT_EMPTY=12, EXPECTED_NOT_RUN_EOD=1 |

**Correction to CLAUDE.md's stated baseline.** CLAUDE.md's testing protocol
names "warn=8, fail=0" as the expected baseline for this exact command. Both
reference runs, read directly from their archived audit JSONs, show
`warn_count=12`, identically, not 8. `fail_count=0` matches. This is a
confirmed discrepancy between the documented baseline and both available
empirical artefacts — UNVERIFIED whether 8 was ever the true baseline (no
older reference run available to this pass) or whether CLAUDE.md's number is
simply stale relative to a field added after it was written (the 12 warnings
in both runs are entirely about `catalyst_overlay` and a handful of
`shadow_book`/`eod_candidates` fields — see the JSON's `outstanding_fixes`
list — plausible candidates for fields added to the audit's required-column
table after CLAUDE.md's baseline was recorded, but this is not independently
confirmed this pass).

All 12 warnings in both runs are `PRESENT_BUT_EMPTY` (column exists,
0-row fill rate), never `MISSING` (column absent) — i.e. every checked
artefact exists and has the right shape; the gap is entirely values, not
schema. The dominant repeat offender is `catalyst_overlay` (WARN,
`PRESENT_BUT_EMPTY`, `fill_rate=0.0`) across four separate stages
(`options_intelligence`, `eil_enriched`, `execution`, `eod_candidates`) in
both runs — a single upstream field that is never populated anywhere in the
pipeline, confirmed empty at every one of its four audit checkpoints, not a
field lost at any one specific boundary.

### Failure behaviour, both mechanisms

`enforce_handoff_conflict_guard`: see above — conditionally fail-closed,
observed fail-open in both reference runs. `handoff_contract_audit.audit_run`:
called inside a `try/except` at the orchestrator level
(`intelligent_orchestrator.py:5080-5091`, non-critical per Pass A) — a
failure here would be logged and swallowed; not exercised in either
reference run (both produced a clean JSON).

### Dead code on this path

None found in either mechanism this pass.

### Open questions

- The true historical origin of CLAUDE.md's "warn=8" baseline — not resolved
  this pass; both available reference runs show 12, consistently.
- Whether `catalyst_overlay` (the dominant warning) has ever been non-empty
  in any run — not checked outside the two reference runs.
- `handoff_contract_audit.py`'s own per-stage required-column table
  (`:38-115+`) was read only far enough to confirm severities exist and to
  locate the `catalyst_overlay`/McMillan-field entries; a full line-by-line
  audit of all ~167 checks was out of this pass's time budget.

---

## F3 — Catalyst Truth Engine

**Module / function:** `run_catalyst_truth_layer(run_id, stage)`,
`intelligent_orchestrator.py:2885-2928` — a thin wrapper around
`catalyst_truth_engine.enrich_run()` (`catalyst_truth_engine.py:715-787`).
**Invoked by:** three separate call sites in `evening_workflow()`:
`stage="pre_options"` (`:3765`, alongside Options Intelligence's own call
group — runs **before** `run_options_intelligence()` itself, same call-site
group per Pass A/C), `stage="post_options"` (`:3791`), and `stage="post_eil"`
(`:4518`, item 32 — after EIL, GARCH, Trigger Layer CSV, and the Handoff
Guard have all already run).
**Conditional on:** `catalyst_truth_engine` importable (else `ImportError`
caught, `return True`, `:2923-2925`); otherwise unconditional; all exceptions
inside `enrich_run()` caught non-critically at the wrapper (`:2926-2928`).
**Output non-empty in ref runs:** Yes —
`catalysts/catalyst_truth_{run_id}.csv` (1,653 rows, 08-18) and
`catalysts/catalyst_truth_summary_{run_id}.json`.

### What it computes

`_score()` (`catalyst_truth_engine.py:369-664`) derives, per ticker-grouped
`SourceBundle`, 26 `catalyst_*` output fields (`CATALYST_OUTPUT_FIELDS`,
declared `:40-...`) from: the catalyst calendar
(`dropbox/inputs/catalyst_calendar_latest.csv`/`.json` and several glob
patterns, `_load_calendar()`, `:290-333`) plus **every row-level artefact
already written for that ticker in the current run** — discovery, both
vanguard CSVs, options_intelligence, superbrain_enriched, eil_enriched,
execution, morning_candidates, and the final opportunity book
(`_source_rows()`, `:336-352`; note the last two do not exist yet at any of
the three call times — see below). Output includes `catalyst_detected`,
`catalyst_type`, `catalyst_date`/`days_to_catalyst`/`catalyst_inside_dte`,
`catalyst_truth_score` (0-100), `catalyst_binary_score`, `catalyst_direction_bias`,
`catalyst_data_quality`, `catalyst_trade_class` (one of
`DATED_CATALYST_CONFIRMED`/`EVENT_CONVEXITY_WATCH`/
`STRUCTURE_WITH_CATALYST_CONTEXT`/`MANUAL_NEEDS_CATALYST_PACKET`/
`STRUCTURE_ONLY_NO_CATALYST`, `:623-637`), and `event_convexity_score`.

### Where it writes

Two things happen per call: (1) a fresh `catalyst_truth_{run_id}.csv` +
`catalyst_truth_summary_{run_id}.json` are written to `catalysts/`
(`enrich_run():729-734,785-786`) — **the same two file paths every time**,
unconditionally overwritten; (2) if `patch_existing=True` (always, per the
orchestrator's call, `:2899`), `_patch_targets()` (`:699-712`) attempts to
patch the 26 `catalyst_*` columns into **nine** named artefacts.

**Confirmed defect: the summary JSON and raw CSV are silently overwritten by
all three invocations sharing the same path.** Only the *last* call's
(`post_eil`) summary survives on disk — direct read of
`catalyst_truth_summary_20260818_041214.json` shows exactly one snapshot,
timestamped consistently with a single generation. **Neither the
`pre_options` nor the `post_options` call's own summary is independently
recoverable from the archived run** — an auditor reading this artefact after
the fact sees only the final state, with no way to tell what the first two
calls computed or how many artefacts they successfully patched, structurally
identical in kind to Pass E's "`superbrain_enriched.csv` mutated three times,
only final state visible" finding (E0/E2.5), now confirmed for Catalyst
Truth's own artefacts as well as (per Pass E) `superbrain_enriched.csv`.

### The nine patch targets — confirmed empirically, two are structurally always "missing"

`_patch_csv()` (`:679-696`) is safe against the `_x`/`_y` suffix collision by
construction: it **drops any pre-existing `catalyst_*` columns from the
target before merging** (`existing = [... in df.columns]; df =
df.drop(columns=existing)`, `:690-692`), then does a clean `merge(...,
on="ticker", how="left")` — the identical defensive pattern GARCH's own merge
uses for `l3_*` (F1 above). **This settles the brief's `_x`/`_y` question for
catalyst fields: the patch mechanism itself cannot produce a suffix
collision.** Direct column-name check of the four artefacts closest to the
earlier merge boundaries this audit has flagged (`discovery_candidates_ultimate`,
`vanguard_signals.csv`, `vanguard_signals_enriched`, `options_intelligence`)
confirms **zero** columns ending in `_x` or `_y`, catalyst-prefixed or
otherwise, in the 08-18 reference run — narrowing (not contradicting) the
Standing Contract's separately-confirmed `iv_rank` `_x`/`_y` finding to a
different field, not one this pass observed recurring for `catalyst_*`.

Read directly from the `post_eil` call's surviving summary JSON
(`patch_results`, 08-18):

| Target | Status | Matched / Rows |
|---|---|---|
| `discovery_candidates_ultimate_{run_id}.csv` | patched | 1,653 / 1,653 |
| `vanguard/vanguard_signals.csv` | patched | 1,612 / 1,612 |
| `options/vanguard_signals_enriched_{run_id}.csv` | patched | 1,612 / 1,612 |
| `options/options_intelligence_{run_id}.csv` | patched | 1,400 / 1,400 |
| `superbrain/superbrain_enriched_{run_id}.csv` | patched | 1,400 / 1,400 |
| `superbrain/eil_enriched_{run_id}.csv` | patched | 1,400 / 1,400 |
| `execution/execution_v3_5_{run_id}.csv` | patched | 1,400 / 1,400 |
| `morning_validation/morning_candidates_{run_id}.csv` | **missing** | 0 / 0 |
| `intelligence_lab/final_opportunity_book_{run_id}.csv` | **missing** | 0 / 0 |

**Confirmed empirically, not just architecturally:** the last two targets are
"missing" because neither file exists yet at `post_eil` time — the candidate
manifest is built at item 34 (after `post_eil`'s call at item 32) and the
Lab opportunity book is written at item 40 (near the very end of the run).
**These two entries in `_patch_targets()`'s target list can never succeed at
any of the three call times** — they are structurally dead for the current
call-site ordering, not merely unlucky in this run. The consequence is not a
missing field, though: `eod_candidate_engine.py` independently carries
`CATALYST_TRUTH_FIELDS` forward from the `eil_enriched` row it reads (which
*was* successfully patched at `post_eil`, before Phase 10 runs) via a plain
`candidate[catalyst_col] = row.get(catalyst_col, "")` passthrough loop
(`eod_candidate_engine.py:2298-2299` region) — so `morning_candidates.csv`
does end up with populated `catalyst_*` fields, just never via this
function's own patch mechanism. Not independently re-verified this pass
whether `pre_options`'s and `post_options`'s own patch results (for the seven
targets that already exist by then, some of which — `options_intelligence` —
do not yet exist at `pre_options` time either, since Options Intelligence
itself runs after `pre_options`'s catalyst-truth call in the same call-site
group) show additional "missing" entries — UNVERIFIED, since those two
calls' summaries are overwritten (see above) and not recoverable from disk.

### The `catalyst_binary_score` unit question — resolved

Direct read of `_score()` (`:456-470`) and `_as_score()` (`:167-174`):
`catalyst_binary_score` is computed as an explicit **0.0-1.0 decimal**,
either copied from a source-row alias (`catalyst_binary_score`/
`event_binary_score`/`binary_event_score`/`binary_score`) and passed through
`_as_score()` — which **self-normalises**: `if number > 1.0: number =
number / 100.0` (`:172-173`), so a source value on a 0-100 scale is safely
rescaled — or, when no source alias is present, assigned a hardcoded decimal
by `catalyst_type` (`0.75` for `EARNINGS`/`BIOTECH_FDA`/`M_AND_A`/
`MACRO_PRINT`, `0.55` for `COMMODITY_MACRO`/`SECTOR_ROTATION`, `0.25` for
`STRUCTURAL`, `0.0` otherwise, `:463-470`). It is consumed **only** as a
weighted multiplicand inside the same function: `score += binary_score *
15.0` (contributing up to 15 of `catalyst_truth_score`'s 100 points, `:596`)
and `convexity_score += binary_score * 25.0` (up to 25 of
`event_convexity_score`'s 100 points, `:615`) — both correctly treat it as a
0-1 fraction being scaled up, not as an already-100-scaled value. Repo-wide
grep for `catalyst_binary_score` in every live (non-`_cleanup_holding`,
non-`decommissioned`) consumer finds exactly one downstream reader,
`eod_candidate_engine.py`, which only **carries the field through unchanged**
as part of the `CATALYST_TRUTH_FIELDS` passthrough (`row.get(catalyst_col,
"")`) — no arithmetic performed on it there. **No unit-mismatch defect found
in the live path.** This resolves (closes, not merely reframes) the open
question the brief names: the field is self-normalising at the point of
computation and is never re-interpreted on a different scale downstream.

### Attrition

None — catalyst truth is a patch/enrichment operation on existing rows, never
a filter. Every artefact it patches keeps its pre-existing row count
(confirmed in the table above: matched counts equal each target's own row
count in every "patched" case).

### Failure behaviour

Fail-open throughout: `ImportError` on the module itself, or any exception
inside `enrich_run()`, is caught at the orchestrator wrapper and logged;
`_patch_csv()` itself catches read failures per-target (`status:
"read_failed"`) and missing-ticker-column cases (`status: "no_ticker"`)
without raising, so one bad target does not stop the other eight from being
attempted.

### Dead code on this path

The `morning_candidates`/`final_opportunity_book` entries in
`_patch_targets()`'s target list (`:701-711`) are live code that is
structurally unreachable-to-success given the current call-site ordering —
not literally dead (it executes, returns "missing", and is logged), but it
can never do useful work as currently sequenced. Distinct from the
Standing Contract's "dead module" findings (which are never-called code); this
is called code with a guaranteed-null outcome.

### Open questions

- `pre_options`'s and `post_options`'s own patch results — not recoverable
  from the archived run (their summary JSON is overwritten by `post_eil`'s
  call). Would require instrumenting a live run to capture the intermediate
  states, out of this pass's read-only scope.
- Whether `pre_options`'s call actually attempts to patch
  `options_intelligence_{run_id}.csv` before that file exists (inferred from
  ordering, not independently confirmed via a surviving intermediate JSON) —
  UNVERIFIED in the sense of "confirmed from an artefact," though strongly
  implied by the call-site ordering already established in Pass A/D.

---

## F4 — McMillan advisory layer

**Module / function:** `mcmillan_advisory_layer.enrich_dataframe()`
(`mcmillan_advisory_layer.py:390-...`), producing the 11 `MCMILLAN_FIELDS`
(`:21-33`): `iv_gex_entry_quality(_label/_narrative)`,
`gamma_island_on_path`, `move_theta_ratio`/`move_theta_margin_label`/
`move_theta_narrative`, `crowd_arrival_state`/`_score`/`_components`/
`_narrative`.
**Invoked by:** `intelligent_orchestrator.py:4522-4573`, item 33 ("PHASE 9D"
per an in-code comment, though the block itself carries no numbered
`logger.info("PHASE ...")` header — the label is this pass's own convenience
name for the call site, consistent with Pass A's numbering caveat), applied
in place to `eil_enriched_{run_id}.csv` then `execution_v3_5_{run_id}.csv`.
Runs **after** GARCH's merge (item 29) and the Handoff Guard (item 31), and
**before** the candidate manifest build (item 34) — i.e. McMillan sees the
GARCH-patched, handoff-downgraded row state, and its own output is available
to Phase 10 when the latter runs.
**Conditional on:** module importable (else `ImportError` caught, non-critical).
**Output non-empty in ref runs:** Yes — all 11 fields present as columns in
both `eil_enriched_20260818_041214.csv` (1,400 rows) and
`execution_v3_5_20260818_041214.csv` (1,400 rows).

### It does not produce zeros — it produces real values, with one field partially unresolvable per-row

Empirical field coverage, `eil_enriched_20260818_041214.csv` (1,400 rows):

| Field | notna | Note |
|---|---|---|
| `iv_gex_entry_quality`(+label/narrative) | 1,400/1,400 | always computed — `_iv_gex_advisory()` has no early-return path |
| `gamma_island_on_path` | 1,400/1,400 | boolean, always set |
| `move_theta_ratio` | **539/1,400** | numeric only when resolvable (see below); label field is 1,400/1,400 |
| `move_theta_margin_label` | 1,400/1,400 | `"UNAVAILABLE"` string for the other 861 rows |
| `crowd_arrival_state`/`_score` | 1,400/1,400 | always computed, 0-3 integer score |
| `crowd_arrival_components` | 504/1,400 | empty string when zero components matched — a genuine "no components" result, not a data gap (see below) |

**`crowd_arrival_score == 0` is a real, semantically meaningful value, not a
missing-data default.** `_crowd_arrival_advisory()` (`:339-387`) computes a
score as `len(components)` where `components` is built from three
independently-checked conditions (IV acceleration, relative-volume spike,
gamma-flip proximity, `:347-368`); `score == 0` correctly means "none of the
three fired," mapped to state `"EARLY_NO_CROWD"` — this is a legitimate
output, not a fallback default. **`move_theta_ratio == 0.0` is different: it
is not a real zero.** See below.

### The `l3_iv_percentile`/`l3_iv_rank`/`l3_expected_move_pct` dead fallbacks

`_ivp()` (`:104-116`) and `_move_theta_advisory()` (`:240-294`) each include
`l3_iv_percentile`/`l3_iv_rank` and `l3_expected_move_pct` respectively as
**last-resort** fallback candidate field names. Repo-wide grep confirms these
three exact strings are written by **no producer anywhere in the repository**
— `mcmillan_advisory_layer.py` is the only file that references them, at
all. This is real dead vocabulary, structurally identical in kind to Pass
E's `HIGH_CONVICTION`→`EXECUTE` dead token finding — **but it has no observed
consequence**, because in both cases an *earlier* candidate in the same
fallback chain resolves first for the large majority of rows: `_ivp()`'s
`"iv_percentile"` (1,384/1,400 = 98.9% populated) and `"iv_rank"` (also
1,384/1,400) are checked before the two dead `l3_` names and satisfy the
lookup in nearly every row; `_move_theta_advisory()`'s chain eventually
reaches `"expected_move_10d"`/`"expected_move_5d"` (both 1,400/1,400 —
GARCH-derived, F1) after the dead `l3_expected_move_pct` name, so
`move_decimal` itself is always resolvable in practice.

### The actual mechanism behind `move_theta_ratio`'s gaps — traced precisely

`_move_theta_advisory()` requires **three** independent non-null inputs to
avoid its early `"UNAVAILABLE"` return (`:258-263`): `move_decimal` (resolved
via GARCH fallback for all 1,400 rows, per above — not the bottleneck),
`spot` (`underlying_price`, 1,400/1,400 populated — not the bottleneck), and
`theta` (`contract_theta`/`theta`). **`contract_theta` is present for only
554/1,400 rows (39.6%) in `eil_enriched.csv`** — the bare `theta` field name
does not exist at all. This 554-row population is the same "row has a
selected options contract" subset Pass D's `BLOCK_NO_CONTRACT`/
`BLOCK_NO_CHAIN` findings already characterise (846/1,400 = 60.4% of rows
never got a contract selected at all) — **`move_theta_ratio`'s gap is
therefore a downstream symptom of the contract-selection funnel (Pass D),
not of GARCH's ordering (F1) or of McMillan's own logic.** GARCH's ordering
fix (were it applied) would not change this outcome, since `theta`, not
`expected_move`, is the limiting input.

**The zero-fill mechanism, confirmed precisely, at the manifest boundary
(not at McMillan's own output):** `_move_theta_advisory()` correctly returns
`ratio_out = ""` (an explicit empty-string sentinel, `:259-263`) for the 861
unresolvable rows — this is written to `eil_enriched.csv` as an empty CSV
field, which `pandas.read_csv` re-reads as `NaN`. `eod_candidate_engine.py`'s
own `_flt()` helper (`:323-330`) then converts that `NaN` to its **default
argument, `0.0`**, via its `except (TypeError, ValueError): return default`
branch (`float(nan)` doesn't raise, but the explicit `nan != nan` check at
`:328` catches it and substitutes `default`) — **this is the exact mechanism
by which "UNAVAILABLE" becomes a literal `0.0` in the candidate manifest,
indistinguishable by value alone from a genuinely near-zero (`CRITICAL`
margin) ratio.** Confirmed empirically in `morning_candidates_20260818_041214.csv`:
`move_theta_ratio == 0.0` for **exactly** 836/1,135 rows (73.7%), and this
set is an **exact** match (crosstab-confirmed, zero off-diagonal cells) with
`move_theta_margin_label == "UNAVAILABLE"` — the label field survives
correctly and is the only way to distinguish a true data gap from a real
computed ratio at this boundary. This answers the brief's F4 question
directly: **McMillan itself does not produce zeros — it produces an explicit
`""`/`NaN` sentinel that a downstream numeric-coercion helper
(`eod_candidate_engine._flt`, not McMillan) turns into `0.0`, recoverable but
only by cross-referencing the co-located label field, three stages removed
from where the sentinel was created.**

### Attrition

None — McMillan enriches existing rows, never filters. Row counts unchanged
(1,400 in, 1,400 out, both target files).

### Failure behaviour

Fail-open: `ImportError` or any exception inside the orchestrator's call
block is caught non-critically (Pass A's finding, not re-verified line-by-line
this pass beyond confirming the call site and its output).

### Dead code on this path

`l3_iv_percentile`, `l3_iv_rank`, `l3_expected_move_pct` fallback candidates
(above) — reachable code, never-satisfied condition given no producer writes
those exact names.

### Open questions

- Whether any run exists where `iv_percentile`/`iv_rank` (the real, populated
  fallback candidates) are themselves absent, forcing a fall-through to the
  dead `l3_iv_percentile`/`l3_iv_rank` names and therefore to
  `"UNKNOWN_IV"` — not observed in either reference run (98.9% coverage in
  08-18; 08-16 not independently re-checked this pass).
- Whether `execution_v3_5_{run_id}.csv`'s independent McMillan pass (applied
  separately from `eil_enriched.csv`, same function, different DataFrame)
  ever produces different values for the same ticker than the `eil_enriched`
  pass — not compared row-by-row this pass; both were confirmed to have
  identical column coverage (539/1,400 `move_theta_ratio` non-null in both)
  but a full value-level diff was not performed.

---

## F5 — Morning Manifest — the critical boundary

**Two distinct artefacts share the informal name "manifest" in this
codebase; both are documented here since the brief's schema/verdict/row-count
questions apply differently to each.**

### F5a — `morning_candidates_{run_id}.csv` — the row-level tradeable-candidate manifest

**Module / function:** `build_candidate_manifest()`,
`eod_candidate_engine.py:1734-2517`.
**Invoked by:** `intelligent_orchestrator.py`, item 34 (Pass A's "PHASE 10",
`:4581-4838` wraps the call plus several post-hoc safety-net joins not
re-traced line-by-line this pass beyond confirming they run before the
function returns).
**Conditional on:** `eil_enriched_{run_id}.csv` exists (hard dependency —
`pd.read_csv(eil_path)` with no existence guard visible in the function
itself; the orchestrator's own wrapper, per Pass A, is the non-critical layer
around this call).
**Output non-empty in ref runs:** Yes — 1,135 rows (08-18).

**This is the artefact `premarket_workflow()` actually reads**
(`_candidates_path`, per Pass A §6, confirmed there and not re-verified
line-by-line this pass) — the one CLAUDE.md's Phase 10 description and the
brief's "Morning Manifest" language most directly refer to.

#### Schema — every field, by producer, at a useful grain (not a literal ~190-column enumeration)

The candidate `dict` built per row (`:1962-2298`) draws from six field
families, each carried forward with `_flt()`/`_str()`/`_first_flt()`/
`_first_str()` helpers (defaults `0.0`/`""` on missing/NaN, `:323-350`):

| Family | Representative fields | Producer |
|---|---|---|
| Identity/classification | `ticker`, `direction`, `structural_tier` (`classify_tier()`, `eod_candidate_engine.py:1669-1731`), `scs_score`, `setup_type`, `eod_candidate_status`/`eod_status_reason` | computed in this function |
| Verdicts (multiple, see below) | `fd_verdict`, `eil_v3_verdict`, `eil_signal_verdict`, `fd_advisory_verdict`, `final_decision_advisory_verdict`, `thesis_decision`, `effective_execution_verdict`, `execution_mode` | carried from `eil_enriched.csv` row (post-Handoff-Guard state) |
| Exit/contract | `exit_mode`/`exit_t1`/`exit_t2`/`exit_t3`/`exit_invalidation_price` (`_exit_intelligence_plan()`, uses `l3_expected_move_*`, F1), `contract_symbol`, `contract_delta`/`_gamma`/`_theta`/`_iv`, `strike`, `expiry`, `dte` | this function + carried from `eil_enriched.csv` |
| Structural metrics | `options_score`, `rr`/`rr_underlying`, `composite`, `ev_structural` (= `ev2_ev_structural`, the EV Engine v2 producer per CLAUDE.md's own `ev_structural` collision note — not independently re-verified this pass), `ev_conf_adj`, `ev_status` | carried from `eil_enriched.csv` |
| McMillan (F4) | `iv_gex_entry_quality*`, `move_theta_ratio`/`_margin_label`/`_narrative`, `crowd_arrival_*` | carried from `eil_enriched.csv`, post-McMillan-patch state |
| GARCH (F1) | `l3_jump_risk_flag`, `expected_move_5d`/`_10d`, `vol_forecast`, `vol_conf` | carried from `eil_enriched.csv`, post-GARCH-merge state |
| Bulk carry-forward blocks | every name in `PHASE2_LAYER2_FIELDS`, `SCANNER_FIELD_NAMES`, `PHYSICS_FIELDS`, `MACRO_QUANT_CSV_FIELDS`, `CATALYST_TRUTH_FIELDS` | `row.get(col, "")` passthrough loops, `:2295-2299` |

Merged in from three additional side-files by ticker, **only when the row's
own value is null/blank/zero** (`:1913-1928`): WBS (`wbs_grade`,
`wbs_wall_price`, ... — 14 columns, `WBS_MERGE_COLS`), Discovery (`VWAP`,
`crabel_state`, `ATR_14`, ... — 14 columns), Vanguard (`rr_underlying`,
`atr_pct`, plus the `PHASE2_LAYER2_FIELDS`/`PHYSICS_FIELDS`/
`CATALYST_TRUTH_FIELDS` groups again, as a fallback source if the primary
`inject_actuarial` pass into `eil_enriched.csv` missed them).

#### Which verdict field(s) the manifest carries — five distinct fields, materially diverging, confirmed at the manifest boundary itself

Direct value-count of `morning_candidates_20260818_041214.csv` (1,135 rows):

| Field | Distribution | Byte-identical to |
|---|---|---|
| `fd_verdict` | WATCHLIST 1,104 (97.3%) / EXECUTE_WITH_CAUTION 22 / EXECUTE 9 | `thesis_decision` (exact match, both read the same value at write time) |
| `eil_v3_verdict` | EXECUTE_WITH_CAUTION 1,057 (93.2%) / EXECUTE 54 / WATCHLIST 24 | `eil_signal_verdict` (exact match) |
| `fd_advisory_verdict` | WATCHLIST 979 (86.3%) / EXECUTE_WITH_CAUTION 119 / EXECUTE 37 | `final_decision_advisory_verdict` (exact match) — a **third**, distinct vocabulary from the two above |

Cross-field agreement, same 1,135 rows: `fd_verdict == eil_v3_verdict` for
only **55/1,135 (4.8%)**; `fd_verdict == fd_advisory_verdict` for
**1,010/1,135 (89.0%)** — i.e. the "advisory" fallback chain
(`fd_advisory_verdict or fd_verdict or eil_v3_verdict`, per
`eod_candidate_engine.py`'s own field-construction logic) resolves to a
*different, typically less conservative* verdict than `fd_verdict` alone for
125/1,135 (11.0%) rows. **This is Pass E's E4 divergence finding
(`options_verdict` → `eil_v3_verdict` → `fd_verdict`), re-confirmed as
surviving intact all the way to the terminal manifest, not resolved or
reconciled anywhere in this span** — a reader of `morning_candidates.csv`
choosing `eil_v3_verdict` over `fd_verdict` (or vice versa) as "the" verdict
would classify the *same 1,135-row slate* as roughly 93% execute-tradeable or
97% watchlist-only, respectively, depending purely on which of five
same-row, differently-named columns they trust. Which field
`morning_gate.py` (the morning-path consumer) itself treats as authoritative
was not traced this pass — out of this pass's evening-workflow scope; flagged
as the natural next question for whoever audits the morning path.

**One confirmed dead field:** `execution_mode` is present as a column but is
an **empty string for all 1,135 rows** — a genuine, complete, silent
non-population, distinct from McMillan's recoverable-via-cross-reference
zero-fill (F4): this field carries zero information in the manifest, full
stop. Its upstream source (whether `eil_enriched.csv`'s own `execution_mode`
column is itself always empty, or whether the carry-forward call reads the
wrong key) was not traced further this pass — flagged as an open question.

#### Row attrition, 1,400 → 1,135 — attributed exactly, both stages traced to source and independently reconciled

`build_candidate_manifest()` builds one candidate dict per input row (no
per-row filtering in the main loop, `:1909-2299`) — **all 1,400 rows produce
a candidate** before any exclusion is applied. Exclusion happens in two
sequential steps after the full 1,400-row DataFrame (`full_out_df`) is built
and sorted:

**Step 1 — `manifest_mask`** (`:2377-2384`):
```python
manifest_mask = (
    ~hard_block_mask                                    # eod_candidate_status in {EOD_NO_OPTIONS_ROUTE, EOD_STRUCTURAL_BLOCK, EOD_BLOCK}
    & ~options_blocked_mask                              # _options_blocked_for_morning_candidate(row) — internals not traced this pass
    & (trigger_go_series | status_series_all.isin(EOD_CARRY_FORWARD_STATUSES))
)
manifest_df = full_out_df[manifest_mask].copy()          # :2589
```
Empirically, both from the surviving `eod_dropoff_audit_{run_id}.csv` (all
1,400 rows, with `eod_candidate_status`) and independently recomputed this
pass: `hard_block_mask` fires for **15/1,400 rows (1.1%)**, all
`EOD_NO_OPTIONS_ROUTE` (`EOD_STRUCTURAL_BLOCK`/`EOD_BLOCK` did not occur in
this run). Every one of the remaining 1,385 rows already carries a
carry-forward status (the six statuses observed in the audit —
`EOD_THESIS_READY_REPAIR_AT_OPEN` 1,019, `EOD_TRIGGER_READY` 269,
`EOD_WATCHLIST_MONETISABLE` 78, `EOD_THESIS_READY` 12,
`EOD_DATA_INSUFFICIENT_REVIEW` 7, plus the 15 hard-blocked
`EOD_NO_OPTIONS_ROUTE` — these partition all 1,400 rows exactly, with zero
remainder), so `trigger_go_series` never has to be consulted to admit a row
in this run — **recomputing `(trigger_go | carry_forward) & ~hard_block`
gives exactly 1,385**, matching `1,400 - 15` precisely. `options_blocked_mask`
contributed **zero additional exclusions** in this run (confirmed by the
arithmetic below closing exactly without needing to invoke it) — its own
internals (`_options_blocked_for_morning_candidate()`) were not traced this
pass; flagged as an open question.

**Step 2 — the "B2 FIX" BLOCKED-verdict filter** (`:2589-2610`): rows in
`manifest_df` with `eil_v3_verdict == "BLOCKED"` are removed and instead
written to `morning_blocked_review_{run_id}.csv`. **Confirmed by direct read
of that file: exactly 250 rows** (08-18).

**Reconciliation, exact:**
```
1,400 total rows
  −    15  hard_block (EOD_NO_OPTIONS_ROUTE)         → dropped entirely, visible only in eod_dropoff_audit.csv
= 1,385  pass manifest_mask                          → manifest_df
  −   250  eil_v3_verdict == BLOCKED (B2 FIX)         → morning_blocked_review_{run_id}.csv
= 1,135  → morning_candidates_{run_id}.csv             [MATCHES OBSERVED ROW COUNT EXACTLY]
```
Every one of the 265 excluded rows is attributed to a named cause and a named
artefact: the 15 hard-blocked rows survive only in `eod_dropoff_audit_{run_id}.csv`
(full 1,400-row audit trail, with `phase10_manifest_exclusion_reason ==
"HARD_BLOCK"`); the 250 BLOCKED-verdict rows survive in
`morning_blocked_review_{run_id}.csv`. **No shortfall — the arithmetic closes
exactly**, and this pass independently re-derived the 1,385 figure from the
audit file's own status column rather than trusting the code's own
`manifest_mask` boolean alone, which is the same standard the EV3 baseline
record (`STAGE_1_BASELINE_RECORD.md`) applied to its own reconciliation
checks.

#### Zero-filled/defaulted/silently-substituted fields at this boundary

- `move_theta_ratio` — `""`/`NaN` → `0.0` via `_flt()`'s default (F4, above),
  confirmed for 836/1,135 rows (73.7%), recoverable via
  `move_theta_margin_label`.
- `execution_mode` — 100% empty string, not recoverable (no co-located
  label field observed).
- `crowd_arrival_score == 0` for 716/1,135 rows — **not** a defect; a real
  computed value (F4).
- Every `_flt()`-typed field in the candidate dict shares the same
  NaN→`0.0` default mechanism as `move_theta_ratio` whenever its source
  column is null — `move_theta_ratio` is simply the one this pass traced in
  full because it was independently flagged by the brief; the same mechanism
  almost certainly affects other sparsely-populated `_flt()` fields in the
  ~190-column schema (e.g. `contract_theta`, `contract_gamma` for the same
  846/1,400 no-contract rows) — not individually re-verified this pass
  beyond `move_theta_ratio`, flagged as a systemic pattern rather than an
  isolated finding.

### F5b — `final_run_manifest.json` — the run-level health/gating summary (a second, distinct artefact)

**Module / function:** `build_final_run_manifest()`/`write_final_run_manifest()`,
`contracts/lab_control.py:516-716`.
**Invoked by:** `evening_workflow()` item 40, `intelligent_orchestrator.py:5104-5129`
(`pipeline_mode="EOD"`), near the very end of the evening run — after the
candidate manifest (item 34), the Pipeline Integrity report (item 36), the
Drop-off/Handoff/UAT diagnostic audits (items 37-39).
**Output non-empty in ref runs:** Yes — `final_run_manifest.json` at the run
root.

**This is a different artefact from `morning_candidates.csv` and carries no
per-row/per-ticker fields at all** — it is a rollup: `phase_status` (PASS/
WARN/FAIL/MISSING per named phase — `discovery`, `vanguard`, `physics`,
`macro`, `options`, `eil`, `execution`, `morning_validation`), `row_counts`
per phase, `stale_flags`/`conflict_flags`/`fatal_flags` (the latter computed
from exactly three hardcoded row-level contradiction checks against the
`eil` rows — `eil_v3_verdict == BLOCKED` with `thesis_decision == GO`,
`pse_execution_mode == FATAL_BLOCK` with an execute-like `execution_mode`,
and a missing `trigger_primary` with an execute-like `execution_mode`,
`:599-613`), a computed `run_health_score` (100, minus 30/fatal-flag,
8/MISSING-phase, 5/WARN-phase, 3/stale-flag, `:618-623`), `run_tradeable`
(boolean), `next_action`, and a pass-through of the EV3 shadow status fields
(`ev_functional_health`, `expected_market_rejections`,
`expected_contract_rejections`, `system_defects` — read from
`ev3_shadow_phase_status_{run_id}.json`, cross-referencing
`STAGE_1_BASELINE_RECORD.md`'s already-established EV3 schema, not
re-derived here). **This is the artefact CLAUDE.md's "Morning Manifest"
language most plausibly means when read as "the terminal artefact of the
evening run" in a health-gate sense** — `morning_candidates.csv` is the
terminal artefact in a *row-data* sense. Both are real, both are written near
the end of the evening run, and they serve different purposes; a reader
should not conflate them.

**Not independently re-verified this pass:** the exact values
`final_run_manifest.json` produced for either reference run (not read this
pass beyond confirming the function's schema from source) — flagged as an
open question below.

### Failure behaviour

`build_candidate_manifest()`: no top-level exception guard visible inside the
function itself; the orchestrator's item-34 call site wraps the whole block
in one outer `try/except` (Pass A, not re-verified line-by-line this pass).
`write_final_run_manifest()`: called inside a `try/except` at the
orchestrator level (`:5104`/`:5128-5129`), non-critical.

### Dead code on this path

`options_blocked_mask`'s contribution to `manifest_mask` is exercised zero
times in this run (see above) — not dead code (it is called and evaluated
for every row), but empirically inert in both reference runs to the extent
checked.

### Open questions

- `_options_blocked_for_morning_candidate()`'s own internals and whether it
  ever fires in a different run — not traced this pass.
- `final_run_manifest.json`'s actual computed values for either reference
  run — schema confirmed from source, values not read this pass.
- Which verdict field `morning_gate.py` (morning-path consumer) itself reads
  as authoritative from `morning_candidates.csv` — out of this pass's scope
  (evening workflow only); the manifest itself carries five, materially
  diverging (above).
- `execution_mode`'s upstream source and why it is 100% empty — not traced
  past confirming it is empty at the manifest.

---

## F6 — Diagnostics and archive

### What diagnostics exist, and their read status

| Artefact | Producer | Reader(s), confirmed this pass |
|---|---|---|
| `pipeline_integrity_{run_id}.json` | inline in `evening_workflow()`, item 36, `intelligent_orchestrator.py:4862-5063` | See below — **settled, not "no confirmed reader."** |
| `dropoff_audit_{run_id}.csv`/`.json` | `dropoff_audit.build_dropoff_audit()`, item 37, `:5066-5077` | `contracts/lab_control.py`'s `_output_files()` (`:478`, glob-only, feeds `phase_status`); `scripts/go_live_uat_audit_watch.py` (presence/row-count only, see below) |
| `handoff_contract_audit_{run_id}.csv`/`.json` | `handoff_contract_audit.audit_run()`, item 38, `:5080-5091` | same two, plus this is the artefact F2b analyses directly |
| `uat_audit_report_{run_id}.md`/`.json` | `uat_audit_report.write_uat_audit_report()`, item 39, `:5094-5102` | `go_live_uat_audit_watch.py` (presence only) |
| `final_run_manifest.json` | `contracts/lab_control.write_final_run_manifest()`, item 40 | `premarket_workflow()` (per Pass A, not re-verified this pass), `go_live_uat_audit_watch.py` (presence only) |
| `eod_dropoff_audit_{run_id}.csv` | inline inside `build_candidate_manifest()` | this pass (F5), directly, to reconstruct row attrition |
| `missed_opportunity_shadow_book_{run_id}.csv` | same | this pass (F5) |
| `morning_blocked_review_{run_id}.csv` | same | this pass (F5) |
| `regime_watch_{run_id}.csv` | same | UNVERIFIED reader — not traced |

### The `pipeline_integrity_{run_id}.json` reader question — settled

Pass A flagged this as "a confirmed writer and no confirmed reader within the
orchestrator itself." Repo-wide grep for the literal string
`"pipeline_integrity"` (excluding this audit's own scratch docs) finds it in
exactly three scripts beyond the orchestrator itself:
`scripts/capture_end_to_end_run.py`, `scripts/qa_market_scenario_simulation.py`,
and `scripts/go_live_uat_audit_watch.py`. Direct read of all three: **none
parses any field *inside* the JSON.** All three treat it purely as a
**file-existence/glob target**:
`scripts/go_live_uat_audit_watch.py` (a standalone, non-invasive run-watcher,
confirmed by its own module docstring, `:1-15`, to be started independently
of the orchestrator and to never mutate trading outputs) globs
`pipeline_integrity_*.json` as one of ~18 tracked artefact patterns
(`RUN_ARTIFACTS`, `:72`) and records only `present`/`count`/`latest`/
`latest_rows`/`latest_write_utc` per artefact (`_artifact_map()`, `:155-173`)
— its one behavioural use of this (`:191`, `artifacts.get("pipeline_integrity",
{}).get("present")`) is a boolean AND-condition alongside `eod_candidates`
and `execution` presence, gating this watcher's own "run looks complete"
signal — not a capital or execution gate, and not a read of any field value
inside the JSON. `scripts/qa_market_scenario_simulation.py` and
`scripts/capture_end_to_end_run.py` similarly list it only as a file to
verify-exists/copy, never to parse. **Settled: `pipeline_integrity_{run_id}.json`
has real, confirmed consumers, but every one of them reads only its
existence and mtime — none reads any field inside it** (not
`manifest_permission`, not `ev3_coverage_health`, not `fatal_flags` — none of
its ~30 top-level keys are consumed by name anywhere outside the orchestrator
that writes it). Functionally, for anything beyond "did this run produce
this file," it is a write-only artefact — a nuance beyond Pass A's binary
"no reader" framing, not a contradiction of it.

One provenance caveat, noted in passing: the current working-tree
`intelligent_orchestrator.py` includes the `ev3_coverage_health`/
`dominant_reason_*` fields added by `STAGE_1_BASELINE_RECORD.md`'s Stage 3.2
remediation (confirmed present in source, `:~4955` region per that record's
own diff). **The archived `pipeline_integrity_20260818_041214.json` does not
contain these keys** — its top-level key list, read directly this pass, has
`ev3_shadow_health`/`ev3_technical_health`/`ev3_functional_health` etc. but
no `ev3_coverage_health` or `ev3_dominant_reason_code`. This is consistent
with (not a new problem — an expected consequence of) the working tree having
been modified since that run was generated, per this repo's already-known
uncommitted state; flagged so a future reader does not mistake the archived
JSON's older schema for a regression.

### What diagnostics would have caught the defects found in Passes A-E, and did not

Scoped assessment based on each diagnostic's confirmed purpose (not a
line-by-line re-audit of `dropoff_audit.py`/`uat_audit_report.py`'s full
source this pass — flagged where inference, not direct code read, is doing
the work):

- **`handoff_contract_audit.py`** checks column *presence and fill-rate* per
  named stage (F2b) — it would not and did not surface the GARCH-after-EIL
  ordering defect (F1/Pass E E2.5), the campaign-gate verdict override (Pass
  E E2/E4), or the five-field verdict divergence at the manifest (F5) — all
  of these are about *when* a value was computed or *which of several
  same-meaning columns* to trust, not whether a column exists and has a
  non-empty value. Its 12 real warnings in both reference runs are all
  `PRESENT_BUT_EMPTY` on a small set of fields (dominated by
  `catalyst_overlay`) — a narrower class of defect than any of the ordering
  or verdict-divergence findings this audit sequence has made.
- **`dropoff_audit.py`** (not read in detail this pass beyond its call site
  and its role as `_output_files()`'s glob target) is inferred, by name and
  by its consumption pattern in `contracts/lab_control.py`, to track
  row-count attrition per phase — the same *kind* of check this pass
  performed manually for F5's 1,400→1,135 reconciliation. UNVERIFIED whether
  it already contains an equivalent reconciliation to the one built manually
  in F5; if it does, this pass's manual reconciliation is corroborating, not
  novel — flagged as worth checking directly in a future pass rather than
  assumed either way.
- **`pipeline_integrity_{run_id}.json`** computes `fatal_flags`/
  `conflict_flags` from exactly three row-level contradiction checks
  (`EIL_BLOCKED_GO`, `PSE_FATAL_EXEC`, `MISSING_TRIGGER_EXEC` — read via
  `contracts/lab_control.py:601-613`, F5b) — none of which check whether
  `l3_*` fields were present *before* the verdict was computed (they only
  check the verdict's own internal consistency, not its provenance/timing).
  It would not have surfaced GARCH's ordering defect even if fully read by a
  human, because the check it performs is orthogonal to the defect's
  mechanism.

**The self-monitoring gap is real and consistent with the brief's framing**:
every diagnostic this audit sequence has found checks *shape* (columns
present, fill rates, row counts, verdict self-consistency within a single
row) — none checks *timing* (was this field computed before or after the
value that logically depends on it) or *cross-field authority* (of five
verdict-shaped columns on the same row, which one is "the" verdict). The nine
dead modules, five ordering defects, and 97.8%-verdict-override finding
carried in from Passes A-E are, by construction, invisible to every
diagnostic this pass examined — not because the diagnostics are broken, but
because none of them was designed to check for that class of defect.

### Archive (item 41)

`archive_outputs()`/`prune_old_runs()`/`generate_report()`
(`intelligent_orchestrator.py:5131-5133`) — confirmed by Pass A to run with
no visible error handling at the call site itself; not re-traced this pass
beyond confirming the call order (last substantive step before the two
Sunday-conditional/weekly items).

### Open questions

- `dropoff_audit.py`'s own internals — not read this pass; flagged above as
  the most promising candidate for an existing reconciliation equivalent to
  F5's manual one.
- Whether `regime_watch_{run_id}.csv` has any reader at all — not checked.
- `uat_audit_report.py`'s own internals and whether it performs any
  cross-verdict or ordering check — not read this pass.

---

## Closing synthesis

### The funnel, updated through the morning manifest

| Stage | Rows | % of 1,400 | % of 3,323 |
|---|---|---|---|
| Enter this span (post-EIL, post-Trigger-Layer-CSV, per Pass E) | 1,400 | 100.0% | 42.1% |
| → GARCH merged (F1, no row change) | 1,400 | 100.0% | 42.1% |
| → Handoff Guard evaluated (F2, no row change — 125 rows downgraded in place) | 1,400 | 100.0% | 42.1% |
| → Catalyst Truth post_eil patched (F3, no row change) | 1,400 | 100.0% | 42.1% |
| → McMillan enriched (F4, no row change) | 1,400 | 100.0% | 42.1% |
| → `build_candidate_manifest()` hard-block filter (F5) | 1,385 | 98.9% | 41.7% |
| → BLOCKED-verdict filter (F5, "B2 FIX") | **1,135** | **81.1%** | **34.2%** |

This matches Pass E's own funnel table's terminal figure (1,135, 81.1% of
1,400 / 34.2% of 3,323) exactly — this pass supplies the attribution Pass E
flagged as out of its scope (15 hard-blocked + 250 BLOCKED-verdict = 265
excluded, reconciling exactly against 1,400 − 1,135).

**Full-run denominator context:** of the original 3,323-ticker universe, the
1,135 rows that reach the morning manifest represent **34.2%** — i.e. roughly
two-thirds of the universe is filtered out somewhere before Options
Intelligence even begins scoring (Pass D's ~74% STAND_DOWN plus the
pre-1,400 attrition Pass C/D already documented), and of the 1,400 rows that
do reach this span, only 1,135 (81.1%) survive to the artefact a human
trader actually opens.

### The manifest field-drop register — everything computed upstream that does not survive to the morning

- **`campaign_verdict`/`execution_verdict`** (Pass E, E2/E5) — computed,
  decisive for which code path a row takes, absent from `EIL_COLS`, never
  reaches `eil_enriched.csv` at all, therefore never reaches the manifest.
- **The genuinely-raw EIL verdict** (`eil_result.eil_raw_verdict`, Pass E) —
  computed, discarded; the CSV/manifest column sharing its name actually
  holds the *final* verdict.
- **`wbs_grade`/`wbs_score`** (Pass E, E1.5) — computed for 123 EXECUTE-tier
  tickers, never merged back into `eil_enriched.csv`, so `_flt()`/`_str()`
  reads in the manifest-building loop return defaults for all 1,400 rows —
  though `wbs_grade`/`wbs_wall_price` *can* still reach the manifest via the
  separate `WBS_MERGE_COLS` side-load from `wall_break_scores_{run_id}.csv`
  directly (F5's Vanguard/WBS merge block, `:1815-1833`) — a second,
  independent path this pass did not cross-check against Pass E's "never
  merged back" finding for consistency; flagged as an open question (does
  the manifest's own WBS side-load partially recover what the EIL passthrough
  lost?).
- **The pre-downgrade `fd_verdict`/`pse_execution_mode` values for 125 rows**
  (F2) — genuinely overwritten in place by the Handoff Guard; only
  reconstructible via the surviving, undowngraded `eil_v3_verdict` on the
  same row.
- **`pre_options`/`post_options` Catalyst Truth snapshots** (F3) — overwritten
  by the `post_eil` call sharing the same output path; not a manifest field
  drop per se, but a diagnostic-artefact loss upstream of the manifest.
- **`execution_mode`** (F5) — present as a manifest column, 100% empty; not
  traced to a specific upstream drop point.
- **`move_theta_ratio`'s true "unavailable" state** (F4/F5) — collapses to a
  literal `0.0` at the manifest, recoverable only via the co-located
  `move_theta_margin_label` field.

### Which verdict field the morning actually receives

**Not a single field — five, materially diverging, all present
simultaneously in `morning_candidates.csv`** (F5a): `fd_verdict`
(=`thesis_decision`, 97.3% WATCHLIST), `eil_v3_verdict` (=`eil_signal_verdict`,
93.2% EXECUTE_WITH_CAUTION), and `fd_advisory_verdict`
(=`final_decision_advisory_verdict`, a third vocabulary, 86.3% WATCHLIST but
diverging from `fd_verdict` on 11.0% of rows). Whichever field a human
trader or a downstream script chooses to trust materially changes what the
same 1,135-row slate looks like. This pass did not trace which field
`morning_gate.py` itself treats as authoritative (out of scope — morning
path); that is the natural next question.

### The `pipeline_integrity` reader question — settled

Real consumers exist (`go_live_uat_audit_watch.py` chiefly), but all three
confirmed readers use only the file's existence/mtime, never a field inside
it (F6). Functionally write-only with respect to its ~30 computed fields.

### Corrections to Passes A-E

1. **Pass A §2.2, item 31** (Handoff Conflict Guard, "Critical") — the
   abort condition is real but gated behind `AVSHUNTER_STRICT_ACTUARIAL_V6`,
   unset by default; in the configuration both reference runs used, this
   gate is fail-open regardless of conflict count (F2a). Refinement, not a
   contradiction — Pass A correctly identified the code path.
2. **Pass A §6 / Pass E's "artefact chain" correction** — `merge_garch_into_enriched()`
   patches **three** targets (`superbrain_enriched.csv`, `eil_enriched.csv`,
   **and `execution_v3_5_{run_id}.csv`**), not two (F1). Additive to Pass
   E's E2.5, not contradicting it.
3. **CLAUDE.md's testing-protocol baseline** ("warn=8, fail=0" for
   `handoff_contract_audit.py`) does not match either reference run, both of
   which show `warn=12, fail=0` (F2b) — a documentation/baseline drift, not a
   code defect.
4. **`STAGE_1_BASELINE_RECORD.md`'s Stage 3.2 fields** (`ev3_coverage_health`
   etc.) are present in the current working-tree `intelligent_orchestrator.py`
   but absent from the archived `pipeline_integrity_20260818_041214.json` —
   expected given the working tree postdates that run's generation, not a
   new defect (F6).

### What this pass did not cover

- `_options_blocked_for_morning_candidate()`'s internals (F5).
- `final_run_manifest.json`'s actual computed values for either reference
  run (schema only, F5b).
- Which verdict field `morning_gate.py` itself reads as authoritative — the
  morning path in general is out of this pass's evening-workflow scope.
- `dropoff_audit.py` and `uat_audit_report.py`'s own internals beyond their
  call sites and output presence (F6) — flagged as the most promising
  targets for a future pass, since `dropoff_audit.py` in particular may
  already perform a version of F5's manual row-attrition reconciliation.
- Full value-level diff between the two independent McMillan passes
  (`eil_enriched.csv` vs `execution_v3_5.csv`) — column coverage compared,
  values not diffed row-by-row (F4).
- Whether the `WBS_MERGE_COLS` side-load in `build_candidate_manifest()`
  recovers any of Pass E's "wbs_grade never merged back" finding for the
  123 WBS-scored tickers specifically — flagged, not resolved (Closing
  synthesis, field-drop register).
- A full line-by-line read of `handoff_contract_audit.py`'s ~167-check field
  table beyond locating the fields this pass needed (F2b).

Pass F is otherwise complete against its brief: F1-F6 delivered with direct
source citations and empirical verification against both reference runs
where the brief asked for reconciliation (F1's row-alignment proof, F2's
empirical trigger/conflict counts, F3's patch-target table, F4's exact
zero-fill mechanism, F5's exact 1,400→1,135 attribution, F6's settled
pipeline_integrity reader question), four corrections filed against Passes
A-E, and the funnel/field-drop-register/verdict-field/reader-question closing
deliverables the brief requires.
