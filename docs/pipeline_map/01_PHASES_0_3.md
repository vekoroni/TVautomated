# Pass B — Preflight, Macro Normalisation, Actuarial Cache, Discovery

Read-only audit. No files edited, no pipeline phase executed. All citations against
`intelligent_orchestrator.py` (working tree, uncommitted relative to git HEAD — same
caveat as Pass A: line numbers are tied to the *current* on-disk content) unless another
file is named. Builds on `data/scratch/pipeline_map/00_SPINE.md` (Pass A) and
`data/scratch/ev3_reconstruction/STAGE_1_BASELINE_RECORD.md` — neither re-derived here
except where Pass A's own dispatch-table ordering needed a correction (§2, Discovery).

**Reference runs:** `20260818_041214` (primary), `20260816_075339` (secondary). All row
counts and field values below are read directly from artefacts in
`data/output/runs/<run_id>/`, `data/output/` (top-level), or the external
`C:\Users\ACKVerissimo\vanguard\` tree, with the reading command/file cited per number.

---

## 0. Denominator warning — read this before any percentage below

**The "universe size" is not one number. It is at least three, and they disagree.**

| Source | Value (08-18 run) | Value (08-16 run) | What it actually is |
|---|---|---|---|
| Base universe file on disk | 3,320 | 3,320 | `data/universe/polygon_liquid_universe.csv`, 3,321 lines incl. header, 3,320 unique non-empty tickers (verified both via `csv.DictReader` count logic at `intelligent_orchestrator.py:829-830` and independent `awk`/dedup count) |
| **What discovery actually consumed** (`discovery_summary_ultimate_<run_id>.json → universe_size`) | **3,323** | **3,320** | The *augmented* universe — base file + scanner-injected NEW tickers, when the scanner had any. 08-18 had 3 new tickers (`GOOG`, `TQQQ`, `SQQQ`); 08-16 had zero, so its augmented and base counts coincide by chance, not by design |
| `dropoff_audit_<run_id>.json → last_stage_counts.UNIVERSE` (+ `rows` total) | 1,647 (of 3,324 tracked) | 1,661 (of 3,322 tracked) | **Not a universe size at all** — see §0.1 |

### 0.1 Why the augmented universe is invisible from the canonical run directory

`build_augmented_universe()` (`intelligent_orchestrator.py:645-668`) writes the augmented
CSV to `cfg.RUNS_DIR / pipeline_run_id / "universe" / scanner_augmented_universe_{pipeline_run_id}.csv`
— but `pipeline_run_id` here is `session_id`, a value generated at the very top of
`evening_workflow()` **before** discovery runs. Discovery's own completion timestamp
becomes `canonical_run_id` (`:3693`) — a **different, later** timestamp. For the 08-18
run: `session_id = 20260818_040143`, `canonical_run_id = 20260818_041214` (10m31s later —
consistent with a ~3,300-ticker scan). The augmented-universe file physically exists —
confirmed on disk at `data/output/runs/20260818_040143/universe/scanner_augmented_universe_20260818_040143.csv`,
3,323 data rows, header `ticker,sector,sector_etf,industry,macro_abstain`, first three rows
`GOOG,,,,` / `TQQQ,,,,` / `SQQQ,,,,` — but it is filed under the **session** directory,
which shares nothing else with the canonical run directory (`20260818_041214/`) that every
other artefact in this audit is keyed off. Anyone inspecting only `runs/20260818_041214/`
— which is every subsequent pass in this audit sequence, and every consumer of
`run_meta.json`'s `canonical_run_id` — will never find the actual universe file discovery
used. (This is the same class of defect CLAUDE.md's "Known Risk Pattern #1 — Wrong
directory" describes, independently rediscovered here on a different artefact.)

Preflight's `check_universe()` (`:825-830`) independently re-reads the **static base
file** (`cfg.UNIVERSE_FILE`) directly — never the augmented one — regardless of whether
augmentation later fires. So the number preflight gates on (3,320) is not the number
discovery reports consuming (3,323) even within the same run.

### 0.2 Why `dropoff_audit`'s "UNIVERSE" count is a different thing again

`dropoff_audit.py`'s own `input_paths.uni` (both runs' JSON) points at the **static**
`data/universe/polygon_liquid_universe.csv` — confirmed identical path string in both
`dropoff_audit_20260818_041214.json:6` and `dropoff_audit_20260816_075339.json:6` — never
the run-specific augmented file. Its `last_stage_counts.UNIVERSE` (1,647 / 1,661) is **not
a universe size**; it is the count of tickers whose *last observed pipeline stage* was
"present in the universe file and nowhere else" — i.e. the residual after subtracting every
ticker that reached the scanner, discovery, package, vanguard, options, EIL, execution, or
EOD-candidate stage. `last_stage_counts` sums to `rows` exactly in both runs (3,324 and
3,322 respectively — see §0 table), confirming this is a tracking-table partition, not an
independent universe count. Both facts hold for both reference runs, so this is a stable
property of `dropoff_audit.py`'s design, not a one-off.

**Verdict: use `discovery_summary_ultimate_<run_id>.json → universe_size` (3,323 / 3,320)
as the funnel denominator for this pass and all downstream passes that need "how many
tickers did the pipeline start with today."** It is the only number that reflects what
discovery actually processed. Every percentage in §6 (the funnel) below uses it. Every
other candidate denominator is either stale (static file, ignores same-day scanner input)
or a derived tracking artefact, not a count.

---

## 1. Universe Scanner Consumer (Phase 0 — code label, `intelligent_orchestrator.py:3360`)

**Module:** `intelligent_orchestrator.py` (inline — `load_scanner_manifest`, `merge_scanner_inputs`, `build_augmented_universe`, `write_scanner_context`)
**Invoked by:** `evening_workflow():3361-3370` (first thing the evening path does, before preflight)
**Critical:** False — `write_scanner_context` wrapped in its own try/except (`:3363-3369`); the rest have no abort path
**Conditional on:** `cfg.UNIVERSE_SCANNER_MANIFEST.exists()` (`OUTPUT_DIR/universe_scanner/scanner_manifest.json`) and manifest freshness (`age_hrs <= cfg.SCANNER_MAX_AGE_HOURS`, default 24h, `load_scanner_manifest():508,516-519`)
**Number claimed:** code comment "PHASE 0" (`:3360`) / CLAUDE.md does not mention this stage at all — CLAUDE.md's own "Phase 0" is Preflight, which this is not (Pass A §5 already flagged this collision; not re-derived here)

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Scanner manifest | `OUTPUT_DIR/universe_scanner/scanner_manifest.json` | UNVERIFIED — Universe Scanner is a separate subsystem, its own internals out of this pass's scope | `go_new`, `go_known`, `probe_new`, `probe_known`, `timestamp`, `tiers_run`, `files.vms_scoreboard`, `tickers` (per-ticker manifest) |
| Base universe file | `data/universe/polygon_liquid_universe.csv` | 3,320 data rows | `ticker` column (col 1 only, used for existing-ticker dedup) |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| Augmented universe CSV | `RUNS_DIR/{session_id}/universe/scanner_augmented_universe_{session_id}.csv` | 3,323 (3,320 base + 3 new: `GOOG`,`TQQQ`,`SQQQ`) | prepends new tickers to base file's own columns (`ticker,sector,sector_etf,industry,macro_abstain`) — new rows carry blank sector/industry |
| `scanner_context_{run_id}.json` (twice: session-keyed at Phase 0, re-written at canonical run id after discovery, `:3695`) | `RUNS_DIR/{id}/scanner_context_{id}.json` | 24 tickers this run (GO/PROBE qualified, per `dropoff_audit`'s `last_stage_counts.SCANNER: 24`) | `vms_score`, `vms_decision`, `scanner_primary_route`, `iv_rank`, `vol_spread`, `signal_grade*` — full field list at `write_scanner_context():757-800` |
| `scanner_context_latest.json` (DISC-02, stable-named copy) | `OUTPUT_DIR/universe_scanner/scanner_context_latest.json` | same 24 | subset of the above, written separately at `:3635-3679` because the run-id-keyed name isn't known until after discovery |

**Attrition**
Not applicable in the row-loss sense — this stage adds rows (up to 3 new tickers this run), it does not filter the universe.

**Field lineage**
- Created: `all_new = go_new + probe_new` (deduped), `merge_scanner_inputs():608-642`
- Created: `scanner_primary_route` via `_scanner_route()` (`:671-682`) — GO/score≥75→`FULL_PIPELINE`, PROBE/score≥60→`DISCOVERY_ONLY`, WAIT/score≥45→`WATCHLIST_ONLY`, else `SCANNER_BLOCKED`; overridden by `_GRADE_ROUTE_OVERRIDE` if a signal-grader run exists for the scanner's own `run_id` (`:709-713,744-755`) — UNVERIFIED whether a grader run existed this session (grade file path checked at `:699`, not independently confirmed present/absent)
- Written but scoped to a narrow consumer: `manifest_tickers` / signal-timestamp fields (`signal_detected_at`, `lss_score`, `lss_decision`) — only populated if the scanner manifest itself carries a `tickers` dict; not verified populated this run

**Failure behaviour**
No manifest, or manifest older than `SCANNER_MAX_AGE_HOURS`: `load_scanner_manifest()` returns the `empty` dict (`available: False`) — fail-open, logged at INFO/WARNING, pipeline proceeds using the static universe file alone (`:508-519`). `write_scanner_context` failure: caught, warning only, `:3368-3369`.

**Dead code on this path:** none identified this pass.

**Open questions**
- Universe Scanner's own internals (how `go_new`/`probe_new` get decided) — separate subsystem, not traced.
- Whether the 08-16 reference run had a scanner manifest at all, or had one that was stale — `dropoff_audit_20260816_075339.json`'s `input_paths.scan` is the empty string `""`, which is consistent with "no manifest" but not independently confirmed against `load_scanner_manifest()`'s own log output (not captured — no run was executed this pass).

---

## 2. Preflight (`run_preflight_checks`, code carries no phase number)

**Module:** `intelligent_orchestrator.py`
**Invoked by:** `evening_workflow():3373-3377`
**Critical:** True — `intelligent_orchestrator.py:3378-3379`, `if not preflight_ok or macro_path is None: return False`
**Conditional on:** Unconditional (always runs once Phase 0 completes)
**Number claimed:** no phase number in code at this call site; CLAUDE.md calls this "Phase 0" — mismatch already documented in Pass A §5, not re-derived here

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Base universe file | `cfg.UNIVERSE_FILE` = `data/universe/polygon_liquid_universe.csv` | 3,320 data rows (via `csv.DictReader`, `check_universe():829-830`) | row count only — **not** the augmented file (§0.1) |
| Required/optional script inventory | 5 required + 12 optional paths, `check_scripts():867-891` | n/a | file existence only |
| Macro JSON | `cfg.MACRO_FILE` (`dropbox/macro/macro_intelligence_latest.json`) | 1 file | 11 required top-level-or-nested fields, `check_macro_json():1000-1004` |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| None persisted — `run_preflight_checks` returns `(bool, Optional[Path])` in-memory only | — | — | `macro_path` handed forward to every later stage |
| `OUTPUT_DIR`, `RUNS_DIR`, `ARCHIVE_DIR` | created if missing, `:1099-1101` | — | — |

**Attrition**
Not a row-filtering stage — pass/fail is binary at the run level, not per-ticker. Three independent checks, each of which can flip `all_ok = False` (`:1074-1075,1079-1082,1088-1090`), evaluated **all three regardless of earlier failures** (no short-circuit) before the combined `if not all_ok: return False, None` at `:1094-1096`.

| Check | Threshold | Fail-open or fail-closed | path:line |
|---|---|---|---|
| Universe size (AUTO mode, the CLI default) | `< min_universe` (1,000 default) → fail; `< target_universe` (6,500 default) → warn-only, proceeds | Fail-closed below `min_universe`; **fail-open** (warn) between 1,000 and 6,500 — both reference runs (3,320/3,323) sit in this warn band and both proceeded | `check_universe():847-854`, called `:1065-1069` |
| Required scripts (5: Discovery ULTIMATE, Build Packages, Inject Macro, Backfill Timeseries, Run VANGUARD) | any missing → fail | Fail-closed | `check_scripts():867-873,893,911`, called `:1078` |
| Macro JSON (existence, valid JSON, 11 required fields present) | any missing → fail; staleness (`> cfg.MACRO_STALE_HOURS`=20h) → **warn only**, does not fail | Fail-closed on structure; fail-open on staleness | `check_macro_json():972-1055`, called `:1087` |

**Field lineage**
- Created: none persisted (in-memory gate only)
- Consumed then dropped: `check_universe()`'s own returned ticker count `n` — computed (`:830`), returned as the 2nd tuple element, but `run_preflight_checks()` discards it (`universe_ok, _, msg = check_universe(...)`, `:1065`). **The exact number is validated against but never stored or forwarded anywhere** — a caller further downstream cannot learn "3,320" from preflight; it must be re-derived (and discovery does re-derive it independently, arriving at the different 3,323 augmented figure — §0).
- `check_scripts()`'s 12 *optional* scripts are logged (found/missing) but never gate anything and their individual results are not returned to the caller at all — `check_scripts()` returns only `(bool, missing_required_list)` (`:860,911`); the optional-script visibility exists purely as an operator log line, `:895-901`.

**Failure behaviour**
Any of the three checks failing → `return False, None` at `:1096`, which propagates to `evening_workflow()`'s `if not preflight_ok or macro_path is None: return False` (`:3378-3379`) — the entire evening run aborts here. This is one of only ~5-7 hard-abort points in the whole evening path (Pass A §2.2 note after item 43).

**Dead code on this path:** none.

**Open questions**
- `check_scripts()`'s optional-script list includes several already-confirmed-dead modules from the Standing Contract context (e.g. it does not check `execution_decision_engine.py`'s commented-out call site — it checks the *file's* existence via `cfg.EDE_ENGINE`, which is a different question from "is it wired in"). Not a defect in preflight itself, just a reminder that "script found" ≠ "script called" — Pass A's dead-module list is the authority on the latter.

---

## 3. Sector Bias Map (unlabelled in code; Pass A §2.2 item 3)

**Module:** `intelligent_orchestrator.py` (inline) + dynamic-imported `scripts/sector_alignment.py`
**Invoked by:** `evening_workflow():3385-3439`
**Critical:** Conditionally — **True** only if `scripts/sector_alignment.py` is absent AND env `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT` (default `"true"`) is true (`:3423-3434`)
**Conditional on:** `cfg.SECTOR_ALIGNMENT_UTIL.exists()` — **confirmed present** on disk this pass (`scripts/sector_alignment.py` exists, verified via `test -f`), so the abort branch is **not live** in this environment; Pass A had left this UNVERIFIED, now resolved
**Number claimed:** none in code; CLAUDE.md does not mention this stage

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Macro JSON | `macro_path` (from preflight) | 1 file | `sector_rotation` block, full raw dict passed to `sector_alignment.load_sector_bias_map()`/`load_macro_conviction()` |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| None persisted — in-process globals only | `_sector_bias_map`, `_macro_conviction`, `_macro_quant_packet`, `_macro_regime_state` (module-level `global`s, `:3385`) | `_sector_bias_map`: dict keyed by sector, values `TAILWIND`/`HEADWIND`/other | Propagated to every later subprocess via env vars `AVSHUNTER_SECTOR_BIAS_MAP`, `AVSHUNTER_MACRO_CONVICTION`, `AVSHUNTER_MACRO_REGIME_STATE` inside `_run()`'s child-env construction (`:1126-1129`) — **this is the only channel**; nothing writes these to a file at this stage |

**Attrition:** not applicable (no row-level filtering).

**Field lineage**
- Created: `_macro_quant_packet` via `build_macro_quant_packet(macro_raw, macro_path)` (`:3393`) — first of at least 3 rebuilds of this same packet across the evening run (also at `:3484` after normalisation, and again inside `pin_run_directory():1879`); each rebuild is a **full recompute from the current macro JSON contents**, not an update — later rebuilds can and do change `macro_freshness_status`/`macro_data_quality` if the underlying file changed between calls (e.g. after macro normalisation writes back at `:3486`).

**Failure behaviour**
`sector_alignment.py` import or execution exception (any kind) → caught at `:3437-3439`, `_macro_quant_packet` reset to `missing_macro_quant_packet(macro_path)`, logged as error, **pipeline continues without sector alignment** (fail-open on exception, despite the module being present — only the *file-missing* branch has the fail-closed behaviour described above). This is a real asymmetry: a present-but-broken `sector_alignment.py` degrades silently; an absent one can abort the run (subject to the env override).

**Dead code on this path:** none.

**Open questions**
- Exact `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT` env value in the live evening-run shell — not checked this pass (no run executed); inferred "unset → default true" from the code default only.

---

## 4. Macro Contract Normalisation ("FIX-04/07")

**Module:** `scripts/normalise_macro_contract.py`, invoked as a subprocess
**Invoked by:** `evening_workflow():3454-3458`, via `_run("Macro Normaliser", [...], critical=False)`
**Critical:** False at the abort level — but sets `_macro_normalised_ok = False` on failure, which degrades `manifest_permission` to `REVIEW_ONLY_MACRO_DEGRADED` far downstream (Pass A: `:4928-4930`, not re-verified this pass)
**Conditional on:** `(cfg.SCRIPTS_DIR / "normalise_macro_contract.py").exists()` (`:3447,3452`) — confirmed present
**Number claimed:** CLAUDE.md's "Phase 1 → Macro Normalisation" is the closest match; code carries no phase number at this call site (Pass A §5 already flagged)

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Macro JSON | `--macro-path` = `macro_path` | 1 file | Recursively searched (any nesting depth, `_find_field()`, `normalise_macro_contract.py:80-91`) for `liquidity_pulse`/`liquidity_status`, `vix_spot`/`vix_5d_avg`/`vix_level`, GEX aggregate fields, `macro_conviction`/`conviction_score`/`predictability_score` |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| Macro JSON (same file, rewritten in place) | `macro_path` | — | `net_liquidity_score`, `vix_regime_score`, `gex_regime_score`, `macro_momentum_score` (all 0.0–1.0), `normalised_at_utc`, `macro_quant_packet`, `macro_quant_contract_version` — plus, via a nested call, `regime_sub_state`, `macro_regime_sub_state`, `regime_distribution`, `regime_distribution_source`, `regime_drift_interpretation` (see Field lineage below) |

**Attrition:** not applicable (no row-level filtering; this is a JSON field-enrichment step on a single document).

**Field lineage — the augment-only claim does NOT hold for every field this script touches**

CLAUDE.md and this script's own docstring (`normalise_macro_contract.py:15-16`: *"This script ADDS fields to the existing JSON — it does NOT replace it. All existing fields are preserved."*) are **true for the four named score fields** — each is guarded: `existing = _safe_float(macro.get(field)); if existing is not None and 0.0 <= existing <= 1.0: ... continue` (`:252-256`) — a producer-supplied valid value is explicitly preserved, not overwritten, before any derivation is attempted.

**They are not true for the regime fields.** `normalise(macro_path)` calls `macro = normalise_macro_regime_fields(macro)` unconditionally at `normalise_macro_contract.py:235`, **before** the four guarded scores are even touched. That function (`contracts/macro_regime_safety.py:114-138`) does:
```python
out["regime_sub_state"] = sub_state                                    # :124 — unconditional overwrite
out["macro_regime_sub_state"] = sub_state                              # :125 — unconditional overwrite
out["regime_distribution"] = distribution                              # :126 — unconditional overwrite
out["regime_distribution_source"] = "macro_regime_safety"              # :127 — unconditional overwrite
out["regime_drift_interpretation"] = ...                               # :129-136 — unconditional overwrite
```
No existence check, no "preserve if already valid" guard — every one of these five fields is **recomputed from `regime_state`/`regime_drift_status`/`dir_bias`/`macro_conviction` and unconditionally replaced** on every single normalisation run (i.e. every evening run, since this call is unconditional whenever the script is deployed). If an upstream producer (e.g. the GPT macro-synthesis step) had written its own `regime_distribution` with different bull/neutral/bear weights, it is silently discarded and replaced here. This is a genuine augment-vs-replace violation, but scoped precisely: it is **`normalise_macro_regime_fields()`**, not the four headline score derivations, and not the separate GPT-enrichment-delta merge (§ next paragraph) — those two *are* verified augment-only.

By contrast, `merge_macro_enrichment_delta()` (`contracts/macro_enrichment_delta.py:228-271`), the function behind `merge_macro_enrichment_into_macro_latest()` (`intelligent_orchestrator.py:1619-1652`, called at `:3530`, nested inside the "PHASE 4.6" comment block but logically a macro-enrichment step, not an actuarial-cache step — see §5), genuinely never assigns to a top-level macro key: every write in that function targets `merged["extras"][...]` sub-keys or appends to `conflict_flags` (`:236-269`) — no line resembles the unconditional overwrites above. `PROTECTED_MACRO_FIELDS` (`:31-60`) is defined but its enforcement is structurally redundant here since the merge function never touches those keys directly; `MERGE_MODE = "AUGMENT_ONLY_DO_NOT_REPLACE"` (`:29`) is an accurate self-description **for this specific function**, but should not be read as describing the macro pipeline's normalisation stage as a whole.

**Failure behaviour**
Script missing or subprocess non-zero exit: `_nm_ok = False`, `_macro_normalised_ok = False`, logged as error (`:3462-3469,3472-3478`), **pipeline continues** — non-critical at the workflow level. Downstream effect (per Pass A, not re-verified): manifest permission degraded to `REVIEW_ONLY_MACRO_DEGRADED`, not blocked.

**Dead code on this path:** none.

**Open questions**
- Whether the GPT macro-synthesis step (upstream of this whole chain, out of repo scope) ever actually populates `regime_distribution` before this script runs, making the overwrite in `normalise_macro_regime_fields()` a live discard vs. a no-op recompute of an already-absent field — not checked; the reference run's pinned `macro_snapshot.json` has `regime_distribution` populated at read time, but its provenance (GPT-written vs. normaliser-written) was not traced back further.

---

## 5. Bond Macro Sidecar (unlabelled)

**Module:** `intelligent_orchestrator.py` (inline)
**Invoked by:** `evening_workflow():3500-3522`
**Critical:** False, try/except, `:3519-3520`
**Conditional on:** `(cfg.MACRO_DIR / "bond_macro_state.json").exists()`
**Number claimed:** none in code; not in CLAUDE.md

**Inputs / Outputs**
| Artefact | Path | Notes |
|---|---|---|
| In: `bond_macro_state.json` | `dropbox/macro/bond_macro_state.json` | Written by `bond_macro_intelligence.py`, out of scope this pass |
| Out: macro JSON (in place) | `macro_path` | Adds `extras.bond_macro` = `normalise_bond_macro_sidecar(bond_state)` — `bond_macro_flag`, `bond_macro_score`, `curve_state`, `breakeven_adjustment_pct`, and all sidecar fields preserved (`:3507-3511`) |

**Attrition:** not applicable. **Failure behaviour:** absent file → informational log only, no warning (`:3521-3522`); exception during merge → warning, continues (`:3519-3520`) — fully fail-open both ways. **Dead code:** none. **Open questions:** none — this is a small, self-contained, genuinely additive step (`extras.setdefault`/direct key assignment under `extras` only, never touches top-level macro fields).

---

## 6. Actuarial Cache Build ("PHASE 4.6", code comment `:3525`)

**Module:** external — `C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py` (out of repo, dynamic-imported)
**Invoked by:** `evening_workflow():3551-3594`
**Critical:** False — existence guard + try/except, `:3551,3584-3588`
**Conditional on:** `cfg.ACTUARIAL_CACHE_BUILDER.exists()` — **confirmed present** this pass (Pass A left this UNVERIFIED)
**Number claimed:** code comment "PHASE 4.6" (`:3525`) / CLAUDE.md "Phase 2 → Actuarial Cache" — a 2.6-step numbering gap, already flagged by Pass A §5, not re-derived

**Inputs**
| Artefact | Path | Rows (ref run) | Key fields consumed |
|---|---|---|---|
| Actuarial database (governed v7 snapshot) | `C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet` | 3,816,857 rows (per `actuarial_last_run.json`) | 9-dimension state key (`STATE_COLS`, configured dynamically per `actuarial_cache_builder.py:706-707`) plus outcome columns, several resolved via explicit v7 compatibility mapping (`return_5d→outcome_5d_return` etc., 5 mapping warnings logged every run) |

**Outputs**
| Artefact | Path | Rows (ref run) | Key fields produced |
|---|---|---|---|
| `actuarial_cache_v7.parquet` | `C:\Users\ACKVerissimo\vanguard\data\` | **508 aggregated states** (454 valid, 54 invalid — 89.4% valid) | one row per 9-dim state key: win rates, expected moves, `valid` flag, `penalty_multiplier`, schema-fingerprint annotation columns |
| `pipeline_status.json` (heartbeat) | `vanguard/data/pipeline_status.json` | 1 record | `status`, `rows_processed`, `states_built`, `valid_states`, `schema_fingerprint` |
| `actuarial_last_run.json` | `vanguard/data/actuarial_last_run.json` | 1 record | same stats, timestamped `completed_at` |

Both confirmed for the reference run: `completed_at: 2026-08-18T03:02:40Z`, i.e. ~9.5 minutes
before canonical run id `20260818_041214` — consistent with running early in the same
evening session, before discovery finishes.

**Attrition**
Not a candidate-row funnel stage — this builds a lookup table, not a filtered ticker list. The relevant "loss" is structural: 54 of 508 aggregated states (10.6%) are `valid=False` (insufficient sample size or other validity failure per the builder's own internal rule — not traced this pass, out of scope).

**Field lineage**
- Created: 508-row state cache from a 3.8M-row source, size 181,791 bytes on disk (`ls -la` confirmed)
- **Staleness / refresh behaviour — the "incremental" flag is dead**: `intelligent_orchestrator.py:3559` calls `run_from_orchestrator(incremental=False)`. Even if it passed `True`, `build()` (`actuarial_cache_builder.py:663-685`) explicitly disables it: *"The governed v7 parquet is a complete point-in-time snapshot... Preserve the CLI/API argument for compatibility, but always rebuild the small derived cache from full v7"* — every single evening run does a full 3.8M-row rebuild, unconditionally, regardless of the flag's value. The *cache* is therefore always "fresh" relative to its source — but the **source itself**, `actuarial_database_v7.parquet`, has an on-disk mtime of 2026-08-04 04:36 — **14 days stale relative to the 08-18 reference run**. "Rebuilt every run" and "current" are not the same claim; the cache is rebuilt from the same stale snapshot every night until that snapshot itself is regenerated (a separate, out-of-repo process, not traced this pass).
- Consumed then dropped (docstring vs. reality): the builder's own module docstring (`actuarial_cache_builder.py:25-28`) claims *"Writes the registry-selected actuarial_cache_v7.parquet consumed by package builders... Returns structured ActuarialResult dataclass to EV Engine / position_sizing_engine.py"* and states its pipeline position as *"Step 2 (after Macro, before Package Builder)"*. **Neither claim matches the current wiring.** `scripts/build_packages_from_discovery.py` (the actual package builder, Phase 5) contains zero references to `actuarial_cache`, `ACTUARIAL_CACHE`, or `actuarial_registry` — confirmed by direct grep, no matches. `position_sizing_engine.py` is a confirmed-dead module per the Standing Contract. **The only in-repo reader found this pass is `scripts/actuarial_enrichment_pass.py`** ("PHASE 8.5" — Pass A item 18), which runs *after* Options Intelligence, several stages later than "before Package Builder." The docstring describes a wiring this codebase no longer has.

**Failure behaviour**
Cache-miss (no matching 9-dim state key) at lookup time: `actuarial_cache_builder.py:601-613` returns a **neutral prior**, not a hard rejection — `valid=False`, `no_match=True`, but `penalty_multiplier=1.0` (not `0.0`) and `win_rate_*=0.52` (near-baseline, not zero). The in-code comment is explicit about this being a deliberate design change: *"S1: was 0.0 — neutral prior, not zero... Unusual stocks now reach scoring layer with ARMED_HALF cap instead of silent elimination."* **This is fail-open by design**, not fail-closed — a ticker with no actuarial precedent still proceeds through the pipeline at a capped/neutral weighting rather than being dropped.

Builder-level failure (exception, missing source, empty diff): caught at `evening_workflow():3584-3588`, warning only, packages build without actuarial enrichment — fail-open at the orchestrator level too.

**Dead code on this path:** none in the builder itself; the *consumer* claimed in its docstring (`build_packages_from_discovery.py`) does not exist — see Field lineage above.

**Open questions**
- Exact reason 54/508 states are `valid=False` — not traced (internal to `aggregate_states()`, not read this pass).
- Whether `actuarial_database_v7.parquet`'s 14-day staleness (relative to the reference run) is typical or anomalous — no history of its refresh cadence was examined.

---

## 7. Actuarial Transition Matrix ("PHASE 4.7" — first of two same-named labels, Pass A §5)

**Module:** `scripts/build_phase_transition_matrix.py`, subprocess
**Invoked by:** `evening_workflow():3602-3613`
**Critical:** False, `_run(..., critical=False)`, `:3613`
**Conditional on:** `cfg.ACTUARIAL_TRANSITION_MATRIX_BUILDER.exists()` — confirmed present this pass
**Number claimed:** "PHASE 4.7" in code (`:3598`) — collides with the Regime-Adaptive Screener's own "PHASE 4.7" label (§9 below); CLAUDE.md does not mention this stage at all

**Inputs / Outputs**
| Artefact | Path | Notes |
|---|---|---|
| In: `--actuarial-db` | `cfg.ACTUARIAL_DB_PATH` = `vanguard/data/actuarial_database_v7.parquet` | Same 3.8M-row source as §6 |
| Out: `actuarial_phase_transition_matrix_latest.csv` | `vanguard/data/transition_matrix/` | Confirmed on disk, 2,811 bytes, mtime 2026-08-18 04:03 (~1 min after the actuarial cache build completed) — a derived artefact, phase-to-phase transition probabilities, `--phase-column phase_v2` |

**Attrition:** not applicable — derived research artefact, not a filtering stage. **Failure behaviour:** non-critical throughout, `:3613-3629`. **Dead code:** none. **Open questions:** its consumer(s) — described in its own comment as "research/Lab/interpreter consumption" (`:3599-3601`) — not traced this pass; out of Pass B's discovery-funnel scope.

---

## 8. Discovery (Phase 1, code label `avshunter_discovery_ULTIMATE.py`) — the funnel's first real filter

**Module:** `avshunter_discovery_ULTIMATE.py` (2,514 lines), subprocess, driven from `run_discovery()` in `intelligent_orchestrator.py:1536-1581`
**Invoked by:** `evening_workflow():3686-3689`
**Critical:** True — `intelligent_orchestrator.py:3690-3691`, `if not success or not summary or not discovery_run_id: return False`
**Conditional on:** Unconditional given preflight passed; universe file is `_effective_universe` = `universe_override` (test-only) else `_augmented_universe_path` (from §1) else `cfg.UNIVERSE_FILE` (`:3683`)
**Number claimed:** code comment "PHASE 1: DISCOVERY" (`avshunter_discovery_ULTIMATE.py` internal logging, and `run_discovery()`'s own header at `intelligent_orchestrator.py:1542`) / CLAUDE.md "Phase 3 → Discovery (avshunter_discovery_signals.py)" — wrong module name, already flagged by Pass A §5, not re-derived. Note also: **the orchestrator's own call site at `:3686` carries no phase-number comment at all** — the "PHASE 1" label lives inside the subprocess's logging, not at the orchestrator call site.

### 8.1 Reconciliation summary (primary reference run, 08-18)

```
Universe fed to discovery (augmented)                     3,323
  − no usable bar data (load_bars() → None/empty)             28   [SILENT — see 8.3]
  = tickers with data (tickers_scanned)                    3,295
  − no signal / signal rejected below tier-3 floor           1,646  [SILENT — see 8.3]
  = organic candidates (total_candidates, discovery's own)  1,649
  + External Intel Review Lane forced-review append             4  [NOT from the 3,323 universe — separate source, §10]
  = final discovery_candidates_ultimate_<run_id>.csv rows   1,653
```
Every number above is read directly from an artefact, not computed by inference:
`universe_size=3323`, `tickers_scanned=3295`, `total_candidates=1649` all come from
`discovery_summary_ultimate_20260818_041214.json`; the `+4` and final `1,653` come from
`data/output/qa/external_intel_review_lane_20260818_041214.json` (`input_rows: 1649,
appended_forced_review_rows: 4, output_rows: 1653`) and are independently confirmed by
direct row count of the CSV (`1654` lines incl. header, both the top-level and
run-pinned copies — see §8.6). **This reconciles exactly — no shortfall.** `3,323 − 28 −
1,646 = 1,649` ✓, `1,649 + 4 = 1,653` ✓.

For the secondary run (08-16): `universe_size=3320, tickers_scanned=3292 (−28),
total_candidates=1649 (−1643)`. No External Intel Review Lane report was located for that
run in this pass (not searched for) — its final CSV row count was not independently
verified against `total_candidates`; flagged UNVERIFIED for that run only.

### 8.2 Every hard filter, with threshold and line number

`scan_ticker_ultimate()` (`avshunter_discovery_ULTIMATE.py:1192-2123`) is the per-ticker
scoring function. It returns `None` (ticker produces **no** candidate row, of any tier) at
exactly these points, in this order, each unconditional on prior state within the function:

| # | Filter | Threshold | path:line | Mechanism class |
|---|---|---|---|---|
| 1 | Insufficient bar history | `len(df) < cfg.min_bars` (30) | `:1202-1203` | threshold comparison |
| 2 | Price out of range | `not (5.0 <= px <= 500.0)` | `:1213-1214` | threshold comparison |
| 3 | 20-day avg volume too low | `vol20 < 500,000` | `:1216-1218` | threshold comparison |
| 4 | Avg daily dollar volume too low | `adv_dollars < $2,500,000` | `:1225-1228` | threshold comparison |
| 5 | ATR($) too small | `atr_14_val < $0.40` | `:1229-1230` | threshold comparison |
| 6 | ATR(%) too small | `atr_pct_val < 1.0%` | `:1231-1232` | threshold comparison |
| 7 | Below tier floor and not an early setup | `assign_tier(...) == 4` (composite_adjusted < `tier3_min`=25.0) **and** `not early_signal` | `:1533,1537-1538` | threshold comparison (compound — tier assignment + early-detection bypass) |

Filters 1-6 fire on raw price/liquidity data before any Wyckoff/Crabel scoring runs.
Filter 7 is the tier-rejection gate; it is bypassed entirely if `detect_early_position()`
(`:426-579`) independently qualifies the ticker as Tier 0 (2-of-4 base conditions met —
compression/range/volume-dry/price-stable — **and** a weighted score ≥ 50; see `:528-533`
for the exact gate), in which case tier-4 rejection never applies regardless of the
composite score.

Separately, in the main loop (`avshunter_discovery_ULTIMATE.py:2371-2401`), a ticker with
`df is None or df.empty` from `load_bars()` is dropped via a bare `continue` (`:2373-2374`)
**before `scan_ticker_ultimate()` is even called** — this is the "no usable bar data"
bucket (28 tickers, 08-18 run), structurally separate from filters 1-7 above.

### 8.3 The module does not record its own drop reasons — confirmed, not inferred

Three distinct silent-drop code paths exist, and **all three produce either no log line
at all, or the identical DEBUG-level message**, making them indistinguishable even to
someone reading raw logs:

1. `load_bars()` returns `None`/empty → `continue` (`:2373-2374`) — **no log line at all**, not even DEBUG.
2. `scan_ticker_ultimate()` returns `None` (any of filters 1-7 above) → the main loop's `else` branch logs `logger.debug("NO_SIGNAL_AT_ANY_HORIZON: %s", t)` (`:2400-2401`).
3. `scan_ticker_ultimate()` returns a signal, but `assign_discovery_horizon(signal)` returns `None` → `logger.debug("NO_SIGNAL_AT_ANY_HORIZON: %s", t)` (`:2384-2385`) — **the identical string as path 2**, despite being a structurally different failure (a signal was scored, then discarded at horizon assignment, vs. never scored at all).

No per-ticker reason code is written to any CSV, JSON, or database for any of these three
paths. `dropoff_audit.py`'s later reconstruction (Pass A/this pass, §0.2) assigns the
generic label `"UNIVERSE_TICKER_NOT_SELECTED_BY_DISCOVERY"` to the entire 1,648-ticker
gap it computes against its own (static, mismatched — §0) denominator — this is an
external inference, not a discovery-internal classification, and it cannot and does not
distinguish "no bar data" from "failed a liquidity filter" from "scored but below tier
floor." **What can be reconstructed:** the aggregate three-way split in §8.1 (28 / 1,646 /
1,649), from the summary JSON's own counters. **What cannot be reconstructed:** which of
the seven filters in §8.2 eliminated any given one of the 1,646 — the code does not
persist that distinction anywhere, live or in logs, at any verbosity level actually
captured by an artefact in this run.

### 8.4 Path-3 (horizon-assignment) is structurally near-unreachable — verified against both runs

`assign_discovery_horizon()` (`:2129-2155`) returns `None` (path 3 above) only if
`signal.get("tier", 99)` is **not** one of `{0, 1, 2, 3}` (the `else: return None` at
`:2154-2155` is reached only past three prior `if` branches that between them cover tier
∈ {0,1} → `1_5d`, tier == 2 → `6_10d`, tier == 3 → `11_20d`). But every signal reaching
this function already has `tier` set by `scan_ticker_ultimate()` to exactly one of
`{0,1,2,3}` (tier 4 was already filtered at `:1537-1538`, filter 7 above) — so the `None`
branch is reachable only via a malformed/missing `tier` key, not through normal scoring.
Empirical confirmation: in the 08-18 reference run, `tier_counts` (incremented once per
scored signal, `avshunter_discovery_ULTIMATE.py:2397-2399`, **before** the horizon check)
sums to `744+74+727+104 = 1,649`, exactly equal to `total_candidates` (also 1,649, counted
**after** the horizon check, `len(all_signals)`). Zero signals were lost at this gate in
the reference run — the code path exists but was not exercised.

### 8.5 Composite scoring and tier floors — for reference, not independently re-derived per-ticker

`composite_score = wyckoff_score*0.6 + crabel_score*0.4` (or `wyckoff_score` alone if
`crabel_score <= 0`), `calculate_composite_score():620-628`. Tier assignment uses
`composite_adjusted` (state-prior-weighted, `apply_state_prior_adjustment()`,
`:844-919`, bounded ±20/+15) against `cfg.tier1_min=50, tier2_min=35, tier3_min=25`, with
a **regime-adaptive Tier-1 floor**: RISK_OFF raises it to 72, TRANSITIONAL to 68,
RISK_ON leaves it at 50 (`assign_tier():584-610`). `cfg.active_regime` is set by
`regime_threshold_injector.apply_regime_to_config()` (called `avshunter_discovery_ULTIMATE.py:2247-2249`)
reading the same macro JSON — **not traced into this pass**; the reference run's macro
snapshot shows `regime_state="TRANSITIONAL_BULLISH"` and `macro_regime_label="TRANSITIONAL"`
(two different granularities of the same concept, from the same file — see §4's field-
lineage note on `regime_sub_state` for the mechanism that produces the finer label), so
`cfg.active_regime` for this run is very likely `"TRANSITIONAL"` but this was **not
independently confirmed** (`regime_threshold_injector.py` not read this pass) — flagged
UNVERIFIED.

### 8.6 Two on-disk copies of "the" discovery CSV diverge — reconciled

Two files exist for the same run, both named `discovery_candidates_ultimate_20260818_041214.csv`:

| Copy | Path | Fields | Rows | mtime |
|---|---|---|---|---|
| "Flat" copy | `data/output/discovery_candidates_ultimate_{run_id}.csv` | 285 | 1,653 | 2026-08-18 04:12 |
| "Pinned" run copy | `data/output/runs/{run_id}/discovery/discovery_candidates_ultimate_{run_id}.csv` | 311 | 1,653 | 2026-08-18 07:40 |

Row counts agree (1,653 both); **field counts do not (285 vs. 311, a 26-field gap)**.
Traced and fully explained, not a mystery:
- The flat copy is discovery's own direct output, then patched in place by §1's `apply_external_intel_review_lane()` (adds 4 rows) and `apply_macro_enrichment_to_discovery()` (adds `macro_bias`, `macro_bias_source` columns) at `intelligent_orchestrator.py:3696-3697` — confirmed via `qa/external_intel_review_lane_20260818_041214.json` (`output_rows: 1653`) and `qa/macro_enrichment_discovery_20260818_041214.json` (`rows: 1653, status: "BIAS_ONLY"`).
- The pinned copy is created later by `pin_run_directory()` (`intelligent_orchestrator.py:1907-1914`, `shutil.copy2` of the then-current flat copy) — called from `run_vanguard_pipeline()` (Pass A item 16, after item 11's enrichment already ran, so the pinned copy correctly inherits `macro_bias`/`macro_bias_source`).
- The pinned copy is then patched **three more times in place** by `catalyst_truth_engine.enrich_run(..., patch_existing=True)` (`intelligent_orchestrator.py:2899`, called at `pre_options`/`post_options`/`post_eil` stages), whose `_patch_targets()` (`catalyst_truth_engine.py:699-712`) explicitly lists `run_dir/"discovery"/discovery_candidates_ultimate_{run_id}.csv` as a patch target — **and never the flat `OUTPUT_DIR` copy**, which no consumer downstream of item 11 ever touches again. `_patch_csv()`'s left-merge (`catalyst_truth_engine.py:679-696`) adds the 26 `catalyst_*`/`event_convexity_score`/`cheap_convexity_flag`/`days_to_catalyst` fields without dropping any existing column.
- **Net effect: the pinned run-directory copy is authoritative and more complete (311 fields); the flat top-level copy is a frozen, earlier, 26-field-poorer snapshot that nothing reads again after item 11.** A reader who inspects only `data/output/discovery_candidates_ultimate_*.csv` (the flat copies, which is what `apply_macro_enrichment_to_discovery()` and `apply_external_intel_review_lane()` themselves target and what `run_discovery()` returns the summary from) will silently miss all catalyst-engine enrichment.

**Field lineage — census (sampled, not exhaustive — see caveat below)**

Full field list: 311 columns in the pinned copy (enumerated in full, not reproduced here
for length — see the CSV header directly, or the summary table below by group).

| Field group | Count | Consumed downstream? | Evidence |
|---|---|---|---|
| `wyckoff_validation_*` (21 fields: structure, phase, probability, alternative phase, correctness/maturity scores, status, event sequence, transition probabilities at 5/10/20 bars, expected bars remaining, next expected event, structural invalidation level, timeframe alignment, phase churn warning) | 21 | **No confirmed reader anywhere in the repo.** Repo-wide grep for the literal string `wyckoff_validation_` matches exactly one file: `wyckoff_phase_validator.py` — the **producer** (`validate_wyckoff_phase()`, consumed via `prefixed_validation_fields()` at `avshunter_discovery_ULTIMATE.py:1425,1920`). Zero other files reference any field in this group by name. | Grep, `path glob *.py`, full repo |
| `final_discovery_route` | 1 | **No.** Written once at `avshunter_discovery_ULTIMATE.py:2026` (comment: "scanner VMS wins; news terminal demoted"), referenced nowhere else in the repo. | Grep, full repo |
| `precor_intent_raw` | 1 | **No** (besides its own producer, `wyckoff_crabel_precor_logic_v2.py`, which self-labels it *"explicit audit label"*, `:220` — i.e. deliberately not meant to be consumed). | Grep, full repo |
| `activist_priority_boost` | 1 | **No** confirmed reader beyond its own write site (`avshunter_discovery_ULTIMATE.py:2205`). | Grep, full repo |
| `event_evidence_bucket`, `crabel_bucket`, `dominant_event_bucket`, `truth_confidence_bucket`, `move_age_bucket` | 5 | **Yes** — `crabel_bucket`/`event_evidence_bucket` read by `avshunter_trap_engine.py:122,128` (the live Phase-5.5 trap engine, discovered this pass — see §11 note); `dominant_event_bucket`/`event_evidence_bucket`/`truth_confidence_bucket` read by `catalyst_truth_engine.py:386,435,437`. | Grep + direct read |
| `asymmetry_R` | 1 | **Yes** — `scenario_router.py:108`, `dropoff_audit.py:540`. | Grep |
| `catalyst_*` (26 fields) | 26 | Produced by `catalyst_truth_engine.py` itself (not discovery) and patched into discovery's pinned copy — see §8.6. Downstream reads not traced this pass (belongs to later phases). | — |

**Caveat on this census: it is a targeted sample (≈35 of 311 fields), not exhaustive.**
Every field checked was chosen either because its name suggested it might be audit-only
(the `wyckoff_validation_*` block, `precor_intent_raw`, `final_discovery_route`,
`activist_priority_boost` — all four hypotheses confirmed dead) or because it was
structurally interesting (feeds a filter, a downstream module, or both). The remaining
~276 fields (core scoring: `wyckoff_score`, `crabel_score`, `composite_score`; macro-bias
block; external-intel block; scanner-context passthrough block; raw OHLCV/EMA columns)
were not individually grepped this pass. Given the confirmed pattern that at least 24
fields (21 `wyckoff_validation_*` + `final_discovery_route` + `precor_intent_raw` +
`activist_priority_boost`) are write-only, a full 311-field census would very likely
surface more — this is flagged as unfinished, not claimed complete.

**Failure behaviour**
Discovery subprocess non-zero exit, or no `discovery_summary_ultimate_*.json` file found
after it runs: `run_discovery()` returns `(False, None, None)` (`:1564-1565,1568-1570`),
which the orchestrator treats as critical — `return False` at `evening_workflow():3690-3691`.
This is the second of the ~5-7 hard-abort points in the evening path.

**Dead code on this path:** the `wyckoff_validation_*` field block and the three
single-field cases in the census above, per the evidence given (write-only, no confirmed
reader).

**Open questions**
- Full 311-field census (see caveat above).
- Which of the 21 `wyckoff_validation_*` fields, if any, are consumed by something outside
  the `.py` file tree searched (e.g. the Intelligence Lab's frontend JS/HTML, or a notebook)
  — this pass searched `*.py` only.
- Exact 9.5-minute-earlier actuarial cache build timing (§6) vs. this run's own start —
  confirms *a* build happened in the same session but does not by itself prove no
  intervening cache rebuild occurred between the actuarial-cache stage and discovery.

---

## 9. Regime-Adaptive Screener ("PHASE 4.7" — second of two same-named labels) — a correction to Pass A's ordering

**Module:** `avshunter_regime_screener.py`, dynamic-imported
**Invoked by:** `evening_workflow():3732-3751`
**Critical:** False, try/except (`:3750-3751`)
**Conditional on:** `(cfg.BASE_DIR / "avshunter_regime_screener.py").exists()` — confirmed present
**Number claimed:** "PHASE 4.7" in code comment (`:3724`), colliding with §7's transition-matrix builder's own "PHASE 4.7" (Pass A §5 already flagged the collision itself)

**Correction to Pass A §2.2:** Pass A's dispatch table lists this stage (its item 9) *before*
Discovery (its item 10), citing line ranges `:3732-3751` (item 9) and `:3686-3689` (item 10)
— but item 9's own cited line numbers are *larger* than item 10's, and direct reading of
the source in this pass confirms the code runs Discovery (`:3686`), the post-discovery
enrichment (`:3695-3697`), Quality Validation (`:3699`), and regression/position tracking
(`:3704-3705`) **before** reaching the Regime-Adaptive Screener block at `:3724-3752`. This
is a straight-line function body with no branching between these calls — execution order
matches line order exactly. Pass A's table appears to have transposed these two rows; the
correct execution order is **Discovery, then Regime-Adaptive Screener**, not the reverse.
This also resolves a question that would otherwise arise: `run_regime_screener(run_id=canonical_run_id, ...)`
(`:3741`) needs `canonical_run_id`, which is only assigned at `:3693` — after Discovery
returns. The corrected order means this is not a bug; `canonical_run_id` is already set by
the time this call happens.

**Inputs (as declared in the module's own docstring, `:397`):** *"Called by orchestrator
after discovery, before Phase 8.5"* — i.e. it should have Vanguard-pipeline and/or
SuperBrain output available. Concretely it reads, in priority order:
`run_dir/vanguard/vanguard_signals_enriched_{run_id}.csv`, falling back to
`run_dir/vanguard/vanguard_signals.csv`, falling back to
`run_dir/superbrain/superbrain_enriched_{run_id}.csv` (`avshunter_regime_screener.py:405-413`).

**Outputs (intended):** `run_dir/regime_screener/regime_signals_{run_id}.csv` +
`regime_screener_summary_{run_id}.json` (`:453,468`), per the orchestrator's own comment
at `:3730`: *"Output: data/output/runs/{run_id}/regime_screener/regime_signals_{run_id}.csv"*.

**Attrition — 100% of tickers, every run sampled, root cause fully identified**

`data/output/runs/{run_id}/regime_screener/` is **empty (0 files) in every one of the 9
run directories checked this pass** — both reference runs (`20260818_041214`,
`20260816_075339`) and 7 others sampled by directory listing
(`20260723_072618`, `20260731_083130`, `20260804_114554`, `20260808_103922`,
`20260809_195823`, `20260814_114553`, `20260815_091604`). The directory itself always
exists (created unconditionally at `out_dir.mkdir(parents=True, exist_ok=True)`,
`avshunter_regime_screener.py:401`) but nothing is ever written into it.

**Root cause, confirmed by direct code reading — control-flow ordering, not a data
quality issue:** `run_regime_screener()` is invoked from the orchestrator at "Phase 4.7"
(`:3732-3751`), which — per the corrected ordering above and Pass A's own item numbering
— runs **before** `run_vanguard_pipeline()` (Pass A item 16, `:3754`). But
`run_vanguard_pipeline()` is what produces `vanguard/vanguard_signals*.csv` (via Build
Packages + Run VANGUARD, both inside that function) and SuperBrain's
`superbrain_enriched_*.csv` doesn't exist yet either (that's Pass A item 22, far later).
**None of the three input files the screener looks for can possibly exist yet at the point
it is called.** `_load_csv(vg_path)` returns empty for both the primary and fallback
Vanguard paths, the SuperBrain fallback also fails, and:
```python
if not rows:
    log.warning("Regime screener: no input data found for run %s", run_id)
    return {"success": False, "reason": "no_input_data"}          # avshunter_regime_screener.py:415-417
```
fires — an early return **before** the CSV-write block (`:452-454`) or the summary-JSON
write (`:456-469`) is ever reached. The orchestrator's own caller only logs a success
message conditionally (`if _rs_result.get("success"): logger.info(...)`, `:3742-3749`) and
has no corresponding failure log — a `False` result is silently absorbed, with only the
generic `except Exception` fallback (`:3750-3751`) as a safety net, which this failure mode
doesn't even trigger since `run_regime_screener()` returns normally, it just returns
`success: False`.

This is a clean instance of the **control-flow ordering** mechanism class: a gate (here,
an entire enrichment module) running before the data it structurally depends on exists.
The module's own docstring correctly states its intended position ("after discovery,
before Phase 8.5") but the orchestrator's actual call site places it four full Vanguard-
pipeline phases too early.

**Field lineage:** N/A — no output is ever produced to have fields.

**Failure behaviour:** Fail-open at every level — the module itself returns a structured
failure dict rather than raising; the orchestrator's non-critical wrapping means this
never affects `evening_workflow()`'s return value; no artefact anywhere records that this
stage silently produced nothing on 9/9 sampled runs.

**Recoverability:** Terminal for the run in question — nothing re-invokes the Regime-
Adaptive Screener later in the same evening run. Not re-evaluated by any later stage.

**Blast radius:** 100% of intended output (mean-reversion, vol-expansion, structural-
breakout supplementary signals) — 0 of an unknown intended count, since the screener never
runs far enough to report `mean_reversion`/`vol_expansion`/`structural_breakout` counts
either. Stable across all 9 runs sampled, not a one-off.

**Dead code on this path:** the entire `run_regime_screener()` execution path past
`:417` (the CSV-write and summary-write logic, `:438-469`) is live code that is
structurally unreachable given the current call site — not deleted, not commented out
(unlike Pass A's three confirmed-dead modules), but empirically never executed.

**Open questions:** none — this finding is fully closed within this pass's evidence.

---

## 10. Post-Discovery Enrichment (unlabelled; Pass A §2.2 item 11)

Covered in detail in §8.1 and §8.6 above (External Intel Review Lane's 4-row append,
Macro Enrichment's `macro_bias`/`macro_bias_source` stamp). Summary table for completeness:

**Module:** `intelligent_orchestrator.py` (inline) → `scripts/apply_external_intel_review_lane.py`, `scripts/apply_macro_enrichment_to_discovery.py` (both subprocesses)
**Invoked by:** `evening_workflow():3696-3697`
**Critical:** False by omission — both functions have `-> bool` signatures but their return values are discarded at the call site (Pass A already flagged this; confirmed by direct read: `:3696-3697` are bare statement calls, no `if`/assignment)
**Conditional on:** respective script existence (`cfg.APPLY_EXTERNAL_INTEL_REVIEW_LANE`, `cfg.APPLY_MACRO_ENRICHMENT_DISCOVERY`) — both confirmed present via successful reports on disk

**Attrition:** External Intel Review Lane **adds** 4 rows (`input_rows: 1649 → output_rows: 1653`) — the only *positive* attrition (row gain) in this pass. Source: `dropbox/inputs/catalyst_calendar_latest.csv`, 15 external tickers validated, 11 matched existing discovery rows, 4 forced-review rows appended for tickers discovery itself never selected (`external_intel_review_lane_20260818_041214.json:5,11-12`).

**Failure behaviour:** both non-critical; missing discovery CSV → warning + early return (`apply_macro_enrichment_to_discovery():1587-1589`, `apply_external_intel_review_lane():1658-1660`); missing script → warning, and — asymmetrically — `apply_macro_enrichment_to_discovery()` returns `True` on missing script (`:1595`, treated as a no-op success) while `apply_external_intel_review_lane()` returns `False` on missing script (`:1666`) — a small inconsistency in how "script not deployed" is signalled between two structurally similar functions, though it is moot here since both scripts are present.

---

## 11. Quality Validation ("PHASE 2", `validate_quality()`)

**Module:** `intelligent_orchestrator.py:1694-1785`
**Invoked by:** `evening_workflow():3699-3702`
**Critical:** True — `:3701-3702`, `return False` on `issues` non-empty
**Conditional on:** Unconditional
**Number claimed:** code comment "PHASE 2" (`:1697`) / CLAUDE.md does not name this stage explicitly

**Inputs:** the discovery summary dict (`universe_size`, `total_candidates`, `tier_0_early`, `tier_1_confirmed`, `tier_2_observe`, `stale_ticker_count`, `timestamp`) — same JSON as §8.

**Gate thresholds and observed values (both reference runs):**

| Check | Threshold | 08-18 observed | 08-16 observed | Result |
|---|---|---|---|---|
| Candidate ratio | fail `< 15%`, warn `> 25%` (`cfg.EXPECTED_CANDIDATE_RATIO_MIN/MAX`, `:426-427`) | 49.6% | 49.7% | **Both runs breach the warn ceiling by ~2×, both proceed** — warn-only, never fails |
| Early ratio | fail `< 1.5%`, warn `> 5%` (`:428-429`) | 22.4% | 22.2% | **Both runs breach the warn ceiling by ~4.5×, both proceed** |
| Tier 1 + Tier 2 both zero | fail if `tier_1==0 and tier_2==0` | 74 / 727 | 41 / 700 | Pass, not close |
| Discovery timestamp is today | warn only if stale | n/a (same-day) | n/a | Pass |
| Stale ticker count | warn only if `>50` | 35 | 35 | Below warn threshold both runs |

**Attrition:** binary run-level gate, not per-ticker. Given both reference runs sit deep in
warn-only territory on the two ratio checks and comfortably clear the one hard-fail check
(tier_1/tier_2 both zero), this gate has not been observed to fail in either sampled run —
reporting the rate as instructed, not characterising the thresholds as miscalibrated.

**Failure behaviour:** `issues` non-empty → `return False, issues` (`:1782`) → propagates
to `evening_workflow()`'s `return False` (`:3701-3702`) — the third of the ~5-7 hard-abort
points. **Dead code:** none. **Open questions:** none.

---

## 12. Regression Detection / Position Tracking (unlabelled / "PHASE 4")

**Modules:** `detect_regression()` (`:1790-1810`), `run_position_tracking()` (`:1815-1825`)
**Invoked by:** `evening_workflow():3704-3705`, explicitly commented `# non-blocking` at the call site
**Critical:** False, both — `detect_regression` never returns a value the caller checks; `run_position_tracking` returns a bool but it too is uninspected at the call site
**Conditional on:** `run_position_tracking` additionally conditional on `cfg.POSITION_TRACKER.exists()` (`:1821-1823`, warns and returns `True` — i.e. "success" — if absent, which is a slightly unusual convention: absence is reported as trivially-successful rather than skipped)

`detect_regression` compares `total_candidates` against the *second-to-last*
`discovery_summary_ultimate_*.json` on disk (`sorted(...)[-2]`, `:1792,1797`) — i.e. not
strictly "yesterday's run" but "whatever the previous file happens to be," which could be
same-day if discovery ran twice. Warns only if the swing exceeds ±50% (`:1805-1806`) —
neither reference run's regression behaviour was independently verified this pass (would
require reading the prior summary file in the sequence, not done).

**Attrition, Failure behaviour, Dead code:** all not applicable / none — these are pure
diagnostics with no gating power over the pipeline.

---

## 13. The funnel so far

Using the corrected denominator from §0 (`discovery_summary_ultimate → universe_size`),
primary reference run (08-18):

| Stage | Rows | % of universe (3,323) |
|---|---|---|
| Universe fed to discovery (augmented) | 3,323 | 100.0% |
| — tickers with usable bar data | 3,295 | 99.2% |
| Discovery organic candidates (all tiers, incl. Tier 4 already excluded) | 1,649 | 49.6% |
| + External Intel Review Lane forced-review rows | +4 | +0.1% |
| **Discovery CSV final row count (both on-disk copies)** | **1,653** | **49.7%** |
| — of which Tier 0 (EARLY) | 744 | 22.4% |
| — of which Tier 1 (confirmed) | 74 | 2.2% |
| — of which Tier 2 (observe) | 727 | 21.9% |
| — of which Tier 3 (watch) | 104 | 3.1% |

Preflight's own gate (§2) validated a **different, smaller, static** number (3,320, the
un-augmented base file) and does not feed into this table at all — it is a pass/fail check
on a stale proxy for the true universe, not a funnel stage with its own row count.

Secondary reference run (08-16), no scanner augmentation that day so base == augmented:

| Stage | Rows | % of universe (3,320) |
|---|---|---|
| Universe | 3,320 | 100.0% |
| Tickers with data | 3,292 | 99.2% |
| Discovery candidates | 1,649 | 49.7% |
| Tier 0 / 1 / 2 / 3 | 737 / 41 / 700 / 171 | 22.2% / 1.2% / 21.1% / 5.2% |

The candidate ratio (≈49.6-49.7%) and the tickers-with-data ratio (≈99.2%) are **stable
across both reference runs** to within 0.1 percentage point — this part of the funnel is
not noisy between the two sampled runs, despite the tier distribution shifting
meaningfully (Tier 1 confirmed nearly doubles 08-16→08-18: 41→74; Tier 3 watch nearly
halves: 171→104 — consistent with the regime moving, per the macro snapshot, though the
regime mechanism itself (§8.5) was not independently verified this pass).

## 14. Reconciliation shortfalls — none found, stated explicitly

Every stage-level arithmetic check performed this pass closed exactly:
- Discovery's three-way split (28 no-data / 1,646 no-signal / 1,649 candidates) sums to
  the universe count exactly, both runs, per artefact-reported numbers (§8.1).
- External Intel Review Lane's own reported delta (input 1,649 → output 1,653, +4) matches
  the independently-measured CSV row counts exactly (§8.1, §8.6).
- `assign_discovery_horizon()`'s potential third silent-drop path lost exactly 0 rows in
  the reference run, confirmed by `tier_counts` sum equalling `total_candidates` exactly
  (§8.4).
- Actuarial cache stats (`rows_processed`, `states_built`, `valid_states`,
  `invalid_states`) reconcile internally (454+54=508) and match across two independent
  artefacts (`pipeline_status.json`, `actuarial_last_run.json`) byte-for-byte on every
  shared field.

No unexplained gap of the kind the Standing Contract's "365-row gap" precedent warns about
was found anywhere in the Phase 0→Discovery span. This is a genuine result of the arithmetic,
not an assumption — every subtraction above was checked against an artefact, not derived
from the code's intended behaviour.

## 15. What this pass did not cover

- **Full 311-field discovery census** — only ≈35 fields individually verified (§8.6
  caveat). The remaining ~276 (core scoring, macro-bias block, external-intel block,
  scanner-context passthrough, raw OHLCV/EMA columns) were not individually traced to a
  downstream reader or confirmed dead.
- **`regime_threshold_injector.py`** internals — not read; `cfg.active_regime`'s exact
  resolved value for the reference run (assumed `"TRANSITIONAL"` from context, not
  independently confirmed) is UNVERIFIED (§8.5).
- **Universe Scanner subsystem internals** (how `go_new`/`probe_new` are decided
  upstream of `scanner_manifest.json`) — a separate producer, out of this pass's scope
  (§1).
- **`scripts/actuarial_enrichment_pass.py`** (Phase 8.5) — confirmed as the actuarial
  cache's actual reader (§6) but its own internals (cache-miss handling at *that* call
  site, fill-rate behaviour) were not traced — that belongs to whichever later pass
  covers Options Intelligence / the actuarial-enrichment stage.
- **`avshunter_trap_engine.py`** ("Phase 5.5") — discovered this pass to be a **live,
  wired-in module** (`run_vanguard_pipeline():2026-2043`, calls `run_trap_layer()`),
  reading discovery's `event_evidence_bucket`/`crabel_bucket` fields (§8.6 census).
  **This directly contradicts CLAUDE.md's Sprint 3 framing**, which describes the
  Trap-to-Launch Engine as not-yet-built and requiring an architectural decision before
  coding begins. The module exists, is tracked in git (`git status`: `M
  avshunter_trap_engine.py`), and has a real call site. Its own internals (trap-detection
  scoring, `tle_*` field output, verdict logic) are entirely untraced this pass — it runs
  inside `run_vanguard_pipeline()`, downstream of Discovery, and belongs to whichever pass
  covers the Vanguard phase (Pass C per Pass A's own scoping).
- **Why 54/508 actuarial cache states are `valid=False`** — internal to
  `aggregate_states()`, not opened this pass.
- **Regression-detection's actual behaviour** on either reference run (would require
  reading the prior summary in each run's sequence) — not executed.
- Pass B stops at Quality Validation / regression-position-tracking (Pass A dispatch items
  1-13). Items 14 onward (Macro Horizon Router, patch-horizon, Vanguard pipeline, Options
  Intelligence, everything past) are explicitly out of scope per the brief and belong to
  Passes C onward.
