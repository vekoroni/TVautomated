# Pass A — Orchestrator Spine

Read-only audit. No files edited, no pipeline executed. All citations against
`intelligent_orchestrator.py` (5,637 lines) as it exists on disk at the time of
this pass. This file is uncommitted/modified relative to git HEAD (per prior
stages in this sequence) — treat every line number as tied to the *current*
working-tree content, not to any commit.

## 1. Entry point and dispatch

**Entry point:** `intelligent_orchestrator.py:5634-5635` — `if __name__ == "__main__": main()`.
`main()` is defined at `:5565-5631`.

**Argparse block** (`:5566-5609`):

| Flag | Type | Default | Purpose |
|---|---|---|---|
| `--run-id` | str | `None` (auto-generated) | run identifier |
| `--evening` | store_true | `False` | evening path |
| `--morning` | store_true | `False` | morning path |
| `--premarket` | store_true | `False` | **deprecated alias** for `--morning`, `:5576` |
| `--force` | store_true | `False` | bypass market-hours guard |
| `--data-mode` | choice EOD/LATEST | `EOD` | bar-data source |
| `--min_universe` | int | `1000` | hard universe floor |
| `--target_universe` | int | `6500` | soft universe target |
| `--universe_gate_mode` | choice HARD/SOFT/AUTO | `AUTO` | universe gate strictness |
| `--universe` | str path | `None` | override universe file (test/research) |

**Dispatch** (`:5611-5631`):
```
if args.evening:            → evening_workflow(...)
elif args.morning or args.premarket:  → premarket_workflow(run_id=args.run_id)
else:                        → error, success=False
```
`--premarket` and `--morning` both call the **same function**, `premarket_workflow()` — the function itself was never renamed despite the flag rename; only a deprecation warning at `:5623` distinguishes them. **There is no third mode.** `sys.exit(0 if success else 1)` at `:5631` is the process-level exit signal.

## 2. Evening path — `evening_workflow()` (`:3278-3186`, i.e. 3278-5186)

### 2.1 Market-hours guard (`:3304-3353`)
Runs before any phase. `EOD` mode + in-market-hours + no `--force` → **hard abort**, `return False` at `:3345`. `LATEST` mode is unconditionally allowed. `--force` bypasses with a warning (`:3346-3352`). This is the first possible exit point of the entire evening run and is **not** listed as a phase anywhere in CLAUDE.md.

### 2.2 The phase dispatch table (execution order as the code runs)

Numbering in the **Phase** column is the code's own in-comment label where one exists; `—` means the code carries no phase number at this call site. Critical = aborts `evening_workflow()` (`return False`) on failure; a bare warn-and-continue is Non-critical regardless of how the surrounding comment describes it.

| # | Phase label in code | What runs | Call site | Critical? |
|---|---|---|---|---|
| 1 | PHASE 0 (Universe Scanner Consumer) | `merge_scanner_inputs`, `build_augmented_universe`, `write_scanner_context` | `:3361-3370` | Non-critical (scanner-context write wrapped in its own try/except, `:3363-3369`) |
| 2 | — (Preflight) | `run_preflight_checks(...)` | `:3373-3377` | **Critical** — `if not preflight_ok or macro_path is None: return False` `:3378-3379` |
| 3 | — (Sector Bias Map) | inline load of `_sector_bias_map`/`_macro_conviction` via dynamic import of `scripts/sector_alignment.py` | `:3385-3439` | **Conditionally critical** — if `sector_alignment.py` missing AND env `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT` (default `"true"`) is true: `return False` at `:3434`. Currently resolves to critical (no env override found — see §3). |
| 4 | — (Macro Contract Normalisation, "FIX-04/07") | subprocess `scripts/normalise_macro_contract.py` via `_run(..., critical=False)` | `:3454-3458` | Non-critical at the abort level, but sets `_macro_normalised_ok=False` on failure, which later degrades `manifest_permission` to `REVIEW_ONLY_MACRO_DEGRADED` (`:4928-4930`) |
| 5 | — (Bond Macro Sidecar merge) | reads `dropbox/macro/bond_macro_state.json` if present | `:3500-3522` | Non-critical, try/except |
| 6 | PHASE 4.6 (Actuarial Cache Build) | dynamic-import + call of **external, out-of-repo** `C:/Users/ACKVerissimo/vanguard/actuarial_cache_builder.py` | `:3551-3594` | Non-critical, try/except + existence guard |
| 7 | PHASE 4.7 ("Actuarial Transition Matrix") | subprocess via `_run(..., critical=False)` | `:3602-3613` | Non-critical |
| 8 | PHASE 1B (comment only — see §5, no call here) | — | `:3707-3722` | n/a — this is dead comment, the real call is at #12 below |
| 9 | PHASE 4.7 ("Regime-Adaptive Screener") — **duplicate label, see §5** | dynamic import of `avshunter_regime_screener.py`, `run_regime_screener(...)` | `:3732-3751` | Non-critical, try/except |
| 10 | — (Discovery) | `run_discovery(augmented_universe_path=..., scanner_context_path=...)` | `:3686-3689` | **Critical** — `if not success or not summary or not discovery_run_id: return False` `:3690-3691` |
| 11 | — (post-discovery enrichment) | `write_scanner_context`, `apply_external_intel_review_lane`, `apply_macro_enrichment_to_discovery` | `:3695-3697` | **Non-critical by omission** — return values of the latter two (`-> bool` per their signatures, `:1655`, `:1584`) are discarded, not checked |
| 12 | — (Quality validation) | `validate_quality(summary)` | `:3699-3702` | **Critical** — `return False` at `:3702` |
| 13 | — (regression/position tracking) | `detect_regression`, `run_position_tracking` | `:3704-3705` | Non-critical, explicitly commented "non-blocking" |
| 14 | PHASE 1B (Macro Horizon Router) — **actual call, moved here per DEF-002 FIX** | `run_horizon_router(cfg.MACRO_FILE, canonical_run_id)` | `:3776` | Non-critical (`_hr_result` unchecked) |
| 15 | PATCH-HORIZON Phase 1B-B | `patch_horizon_fields_into_csv(..., label="options_intelligence_OI")` | `:3786-3790` | Non-critical (return value unchecked here) |
| 16 | — (Vanguard pipeline — compound phase, see Pass C) | `run_vanguard_pipeline(canonical_run_id, macro_path, data_mode=_data_mode)` | `:3754-3756` | **Critical** — `return False` `:3756`. Internally subprocesses Build-Packages-from-Discovery and Inject-Macro-into-Packages (traced in a prior audit turn, `cfg.BUILD_PACKAGES` at `:343`, called `:1981`) — not re-unpacked here per Pass A scope. |
| 17 | PHASE 8a (Options Intelligence) | `run_catalyst_truth_layer(stage="pre_options")`, `run_position_lock_check`, `run_options_intelligence`, `run_ev3_governed_shadow` | `:3765-3769` | All four non-critical at this call site (no return-value checks). `run_ev3_governed_shadow` internally uses `_run(..., critical=False)` per prior EV3 audit (`:2189`). |
| 18 | PHASE 8.5 (Actuarial Enrichment Pass) | dynamic-import of `actuarial_enrichment_pass.py`, `run_actuarial_enrichment_pass(...)` | `:3805-3857` | Non-critical, try/except + existence guard |
| 19 | PHASE 7.5 (Phantom Scoring Engine) — **note: runs after Phase 8.5, badly out of numeric order** | direct `subprocess.run(...)` (not via the `_run()` helper), 1200s timeout | `:3871-3935` | Non-critical — falls back to un-phantomed OI CSV on any failure, including timeout |
| 20 | PHASE 8c (Core Intel Exporter) | `run_core_intel_exporter(canonical_run_id)` | `:3938-3940` | Non-critical, wrapped try/except |
| 21 | PHASE 8.6 (Trigger Layer — package JSON) | `from trigger_layer import patch_run_packages`, `enrich_csv` imported but only `patch_run_packages` called here | `:3956-4025` | Non-critical, `ImportError` + generic `Exception` both caught |
| 22 | PHASE 8d (SuperBrain passthrough) | `run_superbrain_passthrough(canonical_run_id)` | `:4032` | Non-critical (return value unchecked) |
| 23 | PATCH-HORIZON Phase 8d-B | `patch_horizon_fields_into_csv(..., label="superbrain_enriched")` | `:4043-4053` | Non-critical — logs a warning only |
| 24 | PHASE 8b (Catastrophe Gate) | `run_catastrophe_gate(canonical_run_id)` | `:4054` | Non-critical (return value unchecked) |
| 25 | — (Wall Break Scorer, "Layer 4b") | `run_wall_break_scorer(canonical_run_id)` | `:4055` | Non-critical, comment says so explicitly |
| 26 | FIX-ACTUARIAL-SEQ (pre-EIL actuarial injection) | inline pandas patch of `superbrain_enriched_{run_id}.csv` from package-JSON actuarial data | `:4072-4222` | Non-critical — on fill-rate < 80% sets `_actuarial_loaded_before_eil=False` (soft-gate, degrades manifest later, `:4197-4209`), never aborts |
| 27 | PHASE 9 (EIL — Execution Intelligence Layer) | `run_execution_intelligence_layer(canonical_run_id)` | `:4225` | **Fail-open at the workflow level** — `if not _eil_ok: logger.error(...)` then falls through to the rest of the function (no `return False`), `:4226-4227`. But everything in items 28-31 below is nested inside the `else:` branch (`:4228`) and is **skipped entirely** if EIL fails. |
| 28 | (nested in EIL success) — actuarial safety net | `inject_actuarial_into_eil_csv(canonical_run_id)` | `:4229` | Non-critical |
| 29 | PHASE 10a/10b (GARCH) | `run_garch_layer(canonical_run_id)`, `merge_garch_into_enriched(canonical_run_id)` | `:4235-4236` | Non-critical (return values unchecked) |
| 30 | PHASE 8.6b (Trigger Layer → EIL CSV) | vanguard-trigger-column injection + `_tl_enrich_csv(_eil_csv_path, inplace=True)` | `:4244-4335` | Non-critical, `ImportError` + `Exception` caught |
| 31 | (nested in EIL success) — Handoff Conflict Guard | `enforce_handoff_conflict_guard(canonical_run_id)` | `:4340` | **Critical** — `if not ...: logger.error(...); return False` `:4341-4342`. Note: this is the **only** critical gate inside the `else:` branch that is itself conditional on EIL having succeeded. |
| — | PHASE 9.5 (Execution Decision Engine) | **NOT INVOKED — entire block commented out** | `:4355-4426` | n/a — see §4 |
| — | PHASE 9B (Enhancement Layer) | **NOT INVOKED — entire block commented out** | `:4436-4466` | n/a — see §4 |
| — | PHASE 9C (Trade Book Builder) | **NOT INVOKED — entire block commented out** | `:4475-4516` | n/a — see §4 |
| 32 | — (post-EIL catalyst truth) | `run_catalyst_truth_layer(stage="post_eil")` | `:4518` | Non-critical |
| 33 | PHASE 9D (McMillan advisory layer) — **undocumented in CLAUDE.md, has no phase number in the comment block itself despite carrying one in this table** | `from mcmillan_advisory_layer import enrich_csv`, applied to `eil_enriched` then `execution_v3_5` CSVs | `:4522-4573` | Non-critical, try/except |
| 34 | PHASE 10 (EOD Candidate Engine) | `from eod_candidate_engine import build_candidate_manifest`, plus B1/B4/McMillan/macro-exposure/exit-rules safety-net joins into the manifest | `:4581-4838` | Non-critical, wraps the entire block in one outer try/except at `:4581`/`:4836-4837`. Writes `morning_candidates_{run_id}.csv`. |
| 35 | — (latest.json + read-only diagnostics) | `run_market_context_read_only_diagnostics`, write `latest.json` | `:4841-4853` | Non-critical |
| 36 | FIX-INTEGRITY (Pipeline Integrity Report) | inline computation of `_manifest_permission`/`_final_state`, includes the EV3 coverage-health block (`:4947-5023`, fully documented in `data/scratch/ev3_reconstruction/STAGE_1_BASELINE_RECORD.md` — not re-derived here), writes `pipeline_integrity_{run_id}.json` | `:4862-5063` | Non-critical, try/except |
| 37 | — (Drop-off Audit) | `from dropoff_audit import build_dropoff_audit` | `:5066-5077` | Non-critical |
| 38 | — (Handoff Contract Audit) | `from handoff_contract_audit import audit_run` | `:5080-5091` | Non-critical |
| 39 | — (UAT Audit Report) | `from uat_audit_report import write_uat_audit_report` | `:5094-5102` | Non-critical |
| 40 | — (Final Run Manifest / Lab handoff) | `from contracts.lab_control import write_final_run_manifest, write_final_opportunity_book` | `:5105-5127` | Non-critical |
| 41 | — (Archive / Prune / Report) | `archive_outputs`, `prune_old_runs`, `generate_report` | `:5131-5133` | Non-critical (no error handling visible at the call site itself) |
| 42 | STAGE 9 (Outcome Capture) — **third numbering scheme ("Stage" not "Phase") in the same function** | `from outcome_capture import run_outcome_capture` | `:5140-5151` | Non-critical, `ImportError` tolerated |
| 43 | STAGE 10 (Weekly Intelligence Report) | `from weekly_intelligence_report import run_weekly_report` — **conditional: only runs if `datetime.date.today().weekday() == 6` (Sunday)** | `:5158-5179` | Non-critical, `ImportError` tolerated |

`evening_workflow()` returns `True` at `:5186` if it reaches the end. Given items 27-31's fail-open nesting and the near-universal non-critical wrapping from item 18 onward, in practice **only 5 conditions can produce a `False` (aborted) evening run**: the market-hours guard, preflight failure, sector-bias-map load failure with the env-gate on, discovery failure, quality-validation failure, Vanguard-pipeline failure, or the handoff-conflict guard failing after a successful EIL run. Everything else — including EIL itself — degrades the manifest permission or logs a warning but lets the run complete.

## 3. Conditional phases — resolved values

| Condition | Location | Resolved value (this environment, no override found) |
|---|---|---|
| `_data_mode` (`EOD`/`LATEST`) | CLI `--data-mode`, `:3299-3302` | `EOD` (default) |
| `force` (market-hours bypass) | CLI `--force` | `False` (default) |
| `AVSHUNTER_REQUIRE_SECTOR_ALIGNMENT` | env, `:3425` | not set → defaults to `"true"` → sector-alignment failure is currently an abort condition |
| `AVSHUNTER_EV3_SHADOW_ENABLED` | env, referenced inside `run_ev3_governed_shadow` (already documented in the EV3 baseline record) | not set → EV3 shadow enabled by default |
| `cfg.ACTUARIAL_CACHE_BUILDER.exists()` | `:3551` | **TRUE only if the external path `C:/Users/ACKVerissimo/vanguard/actuarial_cache_builder.py` exists** — outside this repository, cannot be verified from repo contents alone; UNVERIFIED whether it exists on this machine at audit time — I did not check the filesystem outside the repo in this pass |
| `cfg.ACTUARIAL_TRANSITION_MATRIX_BUILDER.exists()` | `:3602` | UNVERIFIED — not checked this pass |
| `_regime_script.exists()` (`avshunter_regime_screener.py`) | `:3733` | file confirmed present in repo listing from earlier passes of this audit sequence (referenced, not re-verified here) |
| `cfg.ACTUARIAL_ENRICHMENT_PASS.exists()` | `:3805` | UNVERIFIED this pass |
| Sunday-only weekly report | `:5158`, `datetime.date.today().weekday() == 6` | depends on the date the evening run executes; not evaluated against a specific date in this pass since no run was executed |

## 4. Modules referenced but NOT invoked on the evening or morning path (with proof)

Beyond the four already-known retired modules carried in from the Standing Contract (`morning_thesis_validator.py`, `scripts/avshunter_superbrain_layer.py`, `final_decision_engine.py`, `position_sizing_engine.py`), this pass found three more, **entirely dead at the orchestrator level**, not merely bypassed:

1. **`execution_decision_engine.py`** (Phase 9.5 EDE) — every line of its invocation block, `intelligent_orchestrator.py:4355-4426`, is prefixed with `#`. The `from execution_decision_engine import run_ede_from_orchestrator` line itself (`:4364`) is commented out — Python never executes an `import` statement inside a comment. Proof of non-invocation: literal `#` on every line, visually confirmed by direct read.
2. **`enhancement_integration.py`** (Phase 9B) — same pattern, `:4436-4466`, `from enhancement_integration import run_enhancement_layer` at `:4442` is commented out.
3. **Phase 9C / Trade Book Builder** — `run_phase_9c()` **is a real, defined function** in this same file (`intelligent_orchestrator.py:3212-3277`, confirmed by the earlier `grep -n "^def "` sweep), but its only call site is commented out: `# _p9c = run_phase_9c(cfg, run_id=canonical_run_id)` at `:4480`. A function that exists, is fully implemented, and is never called — dead code, not a missing dependency.

All three carry in-repo comments explaining *why* they're disabled (PSE inside the EIL runner superseded EDE; Enhancement Layer awaits confirmation that `enhancement_integration.py` exists on disk; Trade Book Builder depends on Enhancement Layer's output) — these are documented, intentional deactivations, not oversights, but they are still modules a reader could mistake for live given how much surrounding detail (log-message templates, field names, expected output paths) the dead code retains.

**`trigger_layer.enrich_csv`** was imported at `:3956` alongside `patch_run_packages` but never called at that import site (only `patch_run_packages` is used there, `:3961`) — it IS called later, separately, at `:4245` (item 30 in §2.2). Not dead, just imported once and used at a different call site than where it was imported — flagged because a shallow read of `:3956` alone would wrongly suggest `enrich_csv` never runs.

## 5. Comparison against CLAUDE.md's documented phase list

CLAUDE.md states:
```
Phase 0  → Preflight
Phase 1  → Macro Normalisation
Phase 2  → Actuarial Cache
Phase 3  → Discovery (avshunter_discovery_signals.py)
Phase 4  → External Intel / Macro Enrichment
Phase 5  → Package Build / Backfill
Phase 6  → Vanguard
Phase 7  → Options Intelligence (avshunter_options_intelligence.py)
Phase 8  → SuperBrain / WBS / EIL (avshunter_superbrain_layer.py)
Phase 8.6b → Trigger Layer (trigger_layer.py)
Phase 9  → GARCH
Phase 10 → Handoff Guard / Catalyst Truth / Morning Manifest
Phase 11 → Diagnostics / Archive
```

**Every one of these thirteen lines conflicts with the code in some way:**

| CLAUDE.md phase | Discrepancy found in code |
|---|---|
| Phase 0 → Preflight | Code's "PHASE 0" comment (`:3360`) labels the **Universe Scanner Consumer**, not preflight. `run_preflight_checks()` (`:3373`) carries **no phase number** in code at all. |
| Phase 1 → Macro Normalisation | Macro normalisation (`:3442-3478`) is unnumbered in code. "PHASE 1B" exists in code (twice — a stale comment at `:3707` and the real call at `:3776`) but is the **Macro Horizon Router**, an entirely different thing from normalisation, and CLAUDE.md never mentions a "1B" at all. |
| Phase 2 → Actuarial Cache | Code labels this **"PHASE 4.6"** (`:3525`), not 2 — a 2.6-step numbering gap. |
| Phase 3 → Discovery (avshunter_discovery_signals.py) | Module name is stale — confirmed in a prior pass of this audit sequence to be `avshunter_discovery_ULTIMATE.py` (`cfg.DISCOVERY_ULTIMATE`, `:338`). The discovery call site in `evening_workflow()` (`:3686`) carries no "PHASE 3" comment at all. |
| Phase 4 → External Intel / Macro Enrichment | The corresponding calls (`apply_external_intel_review_lane`, `apply_macro_enrichment_to_discovery`, `:3696-3697`) are unnumbered at their call site. Meanwhile code has **two different things both labeled "PHASE 4.7"** — the Actuarial Transition Matrix (`:3598`) and the Regime-Adaptive Screener (`:3724`) — a genuine in-code numbering collision, independent of anything CLAUDE.md says. |
| Phase 5 → Package Build / Backfill | Not a top-level call in `evening_workflow()` at all — it is a subprocess step *inside* `run_vanguard_pipeline()` (confirmed in a prior pass: `cfg.BUILD_PACKAGES`, invoked at `:1981` inside that function, itself called from `evening_workflow():3754`). CLAUDE.md presents it as a sibling of Vanguard; the code nests it inside Vanguard's own function. |
| Phase 6 → Vanguard | Matches in spirit (`run_vanguard_pipeline`, `:3754`) but the code names this call with no "PHASE 6" comment anywhere near it. |
| Phase 7 → Options Intelligence | Code labels this **"PHASE 8a"** (`:3758`), not 7. The module name matches. Separately, "PHASE 7.5" (Phantom Scoring, `:3861`) runs numerically *after* "PHASE 8.5" (`:3797`) in actual execution order — the phase numbers do not correspond to run order at all past this point. |
| Phase 8 → SuperBrain / WBS / EIL (avshunter_superbrain_layer.py) | The module named is confirmed retired — SuperBrain proper never runs; `run_superbrain_passthrough()` (`:2402-2501`) is called instead, labeled "PHASE 8d" (`:4032`) — a sub-letter of 8, not "Phase 8" itself. WBS is a separate call, "Layer 4b" per its own inline comment (`:4055`), not part of "Phase 8" in the code's own scheme. EIL is "PHASE 9" in the code (`:4225`) — CLAUDE.md folds it into Phase 8; the code treats it as Phase 9. |
| Phase 8.6b → Trigger Layer | This one **matches** — code does label the EIL-CSV trigger enrichment step "Phase 8.6b" (`:4238`). The one accurate line in the comparison. |
| Phase 9 → GARCH | Code labels GARCH **"PHASE 10a/10b"** (`:4231-4236`), not 9. "PHASE 9" in the code is EIL (see above) — CLAUDE.md's Phase 9 and the code's Phase 9 name two different things. |
| Phase 10 → Handoff Guard / Catalyst Truth / Morning Manifest | Code's "PHASE 10" label (`:4575`) is specifically the **EOD Candidate Engine** (manifest build) only. The Handoff Conflict Guard is unnumbered in code (`:4340`, inside the EIL success branch, running *before* GARCH and the candidate engine — much earlier in sequence than CLAUDE.md's grouping implies). Catalyst Truth runs **three separate times** in the evening path (`stage="pre_options"` `:3765`, `stage="post_options"` `:3791`, `stage="post_eil"` `:4518`), not once, and not co-located with the handoff guard or manifest build. |
| Phase 11 → Diagnostics / Archive | Code has no "PHASE 11" comment anywhere in `evening_workflow()`. The nearest match, `run_market_context_read_only_diagnostics` (`:4841`), is unnumbered. Archive/prune/report (`:5131-5133`) is also unnumbered. **"PHASE 11" does appear in code** — but inside `premarket_workflow()`, at `:5266`, labeling the **Execution Gate**, a morning-path step CLAUDE.md's evening-focused list doesn't describe at all. |

**Net finding:** CLAUDE.md's phase list does not correspond to the code's own phase numbering, which itself is internally inconsistent (duplicate "4.7" labels, "7.5" running after "8.5", a "PHASE 1B" comment left behind at the phase's old location after the real call moved, three different numbering vocabularies used in one function — "PHASE", "STAGE", and unlabelled). Treat every phase number in CLAUDE.md and in the code's own comments as unreliable; only the traced call order in §2.2 above is verified.

## 6. Artefact chain (evening path)

This is a first pass at the artefact graph — writer/reader pairs actually confirmed by reading `evening_workflow()`'s own path-construction code. Deeper per-phase artefact detail is Pass B/C/D/E/F's job; this table only covers what's directly visible at the orchestrator level.

| Artefact | Written by | Path pattern | Read next by |
|---|---|---|---|
| `scanner_context_{run_id}.json` | `write_scanner_context`, item 1 & 11 in §2.2 | `cfg.RUNS_DIR/{run_id}/scanner_context_{run_id}.json` (per function name; not independently re-verified this pass) | UNVERIFIED which downstream phase reads it by this exact name — `scanner_context_latest.json` (a *separate* file, `:3640`) is explicitly read by discovery for VMS scores per the DISC-02 comment at `:3631-3634` |
| macro JSON (`macro_path`) | `run_preflight_checks` (produces it), then rewritten in place by macro normalisation (`:3454`), quant-packet refresh (`:3486`), bond sidecar merge (`:3511`) | path returned by `run_preflight_checks`, not printed literally in this pass | read by `run_vanguard_pipeline`, `run_horizon_router`, `apply_macro_enrichment_to_discovery`, and others — each consumer traced in later passes |
| discovery output (`discovery_run_id`-keyed CSV) | `run_discovery(...)` | not printed literally at this call site; `canonical_run_id = discovery_run_id` (`:3693`) becomes the run's canonical identifier from this point forward | `apply_external_intel_review_lane`, `apply_macro_enrichment_to_discovery`, `run_vanguard_pipeline` (internally, via Build-Packages-from-Discovery) |
| `options_intelligence_{run_id}.csv` | `run_options_intelligence` (item 17) | `cfg.RUNS_DIR/{run_id}/options/options_intelligence_{run_id}.csv` (confirmed exact pattern — this is the file already deeply audited in the EV3 stages of this sequence) | `run_ev3_governed_shadow` (item 17, same line group); `phantom_engine.py` (item 19, `_phantom_input` at `:3867`); `patch_horizon_fields_into_csv` targets `vanguard_signals_enriched_{run_id}.csv` (a **different** file — `:3782-3784`), not this one directly |
| `options_intelligence_phantom_{run_id}.csv` | Phantom Scoring Engine subprocess (item 19) | `:3868` | `run_superbrain_passthrough` prefers this file if it exists over the non-phantom OI CSV (confirmed in a prior pass of this sequence: `oi_csv_phantom` preferred at `intelligent_orchestrator.py:2418-2420`) |
| `vanguard_signals_enriched_{run_id}.csv` | Vanguard pipeline (internal, not traced this pass) | `:3782-3784`, `:3959` | `patch_horizon_fields_into_csv` (twice, items 15 and 23), Trigger Layer (`_TRIGGER_INPUT_COLS` injection, item 30) |
| `superbrain_enriched_{run_id}.csv` | `run_superbrain_passthrough` (item 22) — confirmed in prior pass to be a CSV copy of OI with `sb_final_verdict` mapped from `options_verdict`, plus NaN placeholders for missing spread columns | `:4039-4041` | FIX-ACTUARIAL-SEQ patch (item 26, patches this file **in place** before EIL runs), `run_execution_intelligence_layer` (item 27) |
| `eil_enriched_{run_id}.csv` | `run_execution_intelligence_layer` (item 27) | `:4247-4249`, `:4525-4529` | `inject_actuarial_into_eil_csv` (item 28), `merge_garch_into_enriched` (item 29), Trigger Layer 8.6b (item 30, in-place), McMillan advisory (item 33, in-place), `build_candidate_manifest` (item 34, primary input, `:4585`), the Pipeline Integrity Report's EIL-block-rate computation (item 36, `:4866`) |
| `morning_candidates_{run_id}.csv` | `build_candidate_manifest` (item 34), then patched **in place** four more times by the B1/B4/McMillan/macro-exposure/exit-rules safety nets (`:4632-4828`, all within item 34) | `cfg.RUNS_DIR/{run_id}/morning_validation/morning_candidates_{run_id}.csv`, `:4617` | `premarket_workflow()` — this is the file `--morning`/`--premarket` reads (`_candidates_path`, `premarket_workflow():5225`), confirming the orchestrator's own "Phase 10 ... This is the ONLY file that morning validation reads" comment (`:4577-4578`) is accurate at the code level — though `premarket_workflow()` also accepts a fallback, `final_opportunity_book_{run_id}.csv` (`:5227`, `5229`), if the candidates CSV is absent |
| `latest.json` | `:4847-4853` | `cfg.OUTPUT_DIR/latest.json` | `premarket_workflow()`'s run-id resolution fallback when no `--run-id` is supplied (`:5211-5222`) |
| `pipeline_integrity_{run_id}.json` | item 36 | `cfg.RUNS_DIR/{run_id}/pipeline_integrity_{run_id}.json`, `:5041` | UNVERIFIED — no reader traced this pass; likely a human/Lab-facing artefact only |
| `morning_validated_trades_{run_id}.csv` | `run_morning_gate` (called from `premarket_workflow`, `:5254-5258`) — this is `morning_gate.py`'s own output, per the Standing Contract's known finding | `_output_path`, `premarket_workflow():5226` | `execution_gate.run_execution_gate` (Phase 11, `:5273-5279`, morning path only) |

**Artefacts referenced but not confirmed written on this path (candidates for the "written and never read" or "read but never written" flags Pass A asks for):** `pipeline_integrity_{run_id}.json` has a confirmed writer and no confirmed reader within the orchestrator itself — UNVERIFIED whether anything outside the orchestrator (Lab, Pipeline Interpreter) reads it; would need a repo-wide grep for its filename pattern to settle, which is out of this pass's scope (skeleton only, not full field/artefact tracing — that's Pass I's synthesis job once B-F exist).

## 7. What this pass did not cover (explicitly, per the Standing Contract's "state where you stopped" instruction)

- **Did not go inside** `run_vanguard_pipeline`, `run_options_intelligence`, `run_execution_intelligence_layer`, `run_horizon_router`, `run_discovery`, `enforce_handoff_conflict_guard`, or `inject_actuarial_into_eil_csv`'s function bodies — by design, per the Pass A brief ("do not go inside the phase modules yet"). Their internals belong to Passes B through F.
- **Did not enumerate** the full `cfg`/`OrchestratorConfig` block (all `cfg.XXX` constants) — that is explicitly Pass H's job ("enumerate the whole config block").
- **Did not verify** filesystem existence of the several `cfg.XXX.exists()`-gated external/optional modules (actuarial cache builder at the external `C:/Users/ACKVerissimo/vanguard/` path, actuarial transition matrix builder, actuarial enrichment pass) — flagged UNVERIFIED in §3 rather than guessed.
- **Did not trace** `enforce_handoff_conflict_guard()` (`:5334-5427`) or `inject_actuarial_into_eil_csv()` (`:5427-5564`) internals beyond confirming their call sites and critical/non-critical status — both are defined later in the file than their call sites (normal in Python, module-level functions resolve at call time) and their bodies are substantial (~90 and ~135 lines respectively); reading them in depth is more naturally Pass F's (handoff guard) and Pass E/F boundary's job.
- **Did not confirm** `scanner_context_{run_id}.json` vs `scanner_context_latest.json` consumer precisely — flagged UNVERIFIED in §6.

Pass A is otherwise complete: entry point, full evening dispatch table (43 items), full morning dispatch, three newly-confirmed dead modules with proof, the complete CLAUDE.md-vs-code discrepancy list (all 13 lines), and the top-level artefact chain.

**Next session: Pass B (Phases 0-3), using this file plus the Standing Contract.**
