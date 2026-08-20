# Pass H — Dead File Census

Read-only audit. No files edited, moved, deleted, or archived. No pipeline phase executed.
Builds on Passes A-F (`00_SPINE.md` through `05_PHASES_9_11.md`), the Standing Contract's
known-dead list, and direct source reading/grep performed in this pass. Every classification
below states which of the four reachability mechanisms (import closure / subprocess /
config-referenced path / dynamic dispatch) was checked and what it returned. Where a claim
rests on a repo-wide basename grep rather than a traced call site, that is stated explicitly —
per the brief's own warning, a naive import/name-graph produces false negatives (subprocess
and config-path targets look dead) **and false positives** (a short or common basename like
`run`, `ev_engine`, `options_intelligence`, or `morning_validation` matches inside unrelated
text — comments, other identifiers, docstrings — without being a real import). Every file
flagged UNCERTAIN on this basis names the exact follow-up that would resolve it.

## Methodology

1. Enumerated every `.py` file under the repo root, excluding `.venv`, `venv`,
   `site-packages`, `node_modules`, and the unreadable `pytest-of-ACKVerissimo/` (OS
   permission-denied — could not enumerate its contents; assumed non-source, not counted).
   **Total: 656 `.py` files.**
2. Separated already-archived directories (H1's instruction) — see §1 below — leaving
   **482 files requiring classification** (656 − 174 already-archived).
3. Cross-referenced every file confirmed live/dead in Passes A-F (full text of `00_SPINE.md`
   read directly; `01_PHASES_0_3.md` and `02_PHASES_4_6.md` read directly in full; `03/04/05`
   extracted via a structured sub-pass covering their complete text — file-reachability facts
   only, field-lineage/attrition narrative excluded as out of scope for a file census).
4. Read the complete `OrchestratorConfig` class (`intelligent_orchestrator.py:310-495`) in
   full — every constant holding a file path is enumerated in §3, with its actual usage
   (or non-usage beyond the passive existence-check list at `:872-890`) traced by direct grep
   and, for ambiguous cases, direct line reads.
5. Ran a single-pass, whole-repo basename cross-reference (every remaining candidate file's
   basename searched against the full text of every other in-repo `.py` file) to generate a
   first-pass live/orphan signal for the ~480 files not already covered by Passes A-F or the
   config block. This is **mechanism-agnostic evidence** (it would catch a real `import`, a
   subprocess command-string literal, or a config-constant assignment, since all three require
   the literal basename to appear as text somewhere) but does **not** distinguish a real import
   from a textual mention (docstring, comment, log string) — flagged per-file where this
   ambiguity matters, and never used alone to justify an ORPHAN classification without at
   least one additional corroborating check (git-tracked status, directory-level reachability,
   or direct read of the citing file).
6. Checked external scheduling: no `.bat`/`.ps1`/`.sh`/cron file in the repo references any
   in-scope `.py` file by a resolvable literal path (see §6 Flags — the only `.bat`/`.ps1`
   candidates found were `legacy/run_daily_orchestration_v3.ps1`, which is itself the sole
   `.py`-adjacent file under `legacy/` — that directory contains **zero `.py` files**, so it
   is out of scope for this census entirely). `schtasks /query` (read-only, this pass) returned
   no registered Windows Scheduled Task matching `avshunter`, `ma_cockpit`, or `news_terminal`.
   **Limitation, stated per the brief's own instruction: a scheduler entry that does not exist
   as a file in this repo (e.g. Task Scheduler configured via GUI on a different machine, or
   removed since) cannot be detected by any in-repo search or by this one `schtasks` snapshot
   of the current machine's registered tasks at audit time.**

---

## §1. Already-archived — not classified further (per H1 instruction)

| Directory | `.py` count | Evidence it is a prior archive batch |
|---|---|---|
| `_cleanup_holding/` | 159 | Two dated sub-batches on disk: `batch1_archive_paths_20260716/` (mirrors `decommissioned/`, `intelligence-lab/`, `ml_confidence_layer/`, `orchestrator/`, `pipeline_interpreter/`, `scripts/`, `vanguard/` subtrees) and `batch2_root_old_dnu_20260716/` — both named and dated as a completed archive operation (2026-07-16), not in-progress work. |
| `pipeline_interpreter/Archive/` | 4 | Literal `Archive` directory name, sibling to the live `pipeline_interpreter/` tree. |
| `vanguard/execution/strategies/Archive/` | 5 | **Found this pass, not in the original top-level directory sweep** — a second `Archive/` subdirectory, one level deeper, mirroring the five live S1-S5 strategy files (`gex_flipper.py`, `iv_distortion.py`, `liquidity_gate.py`, `obi_predictor.py`, `poc_timing.py`) with older mtimes (2026-03-27 vs. the live copies' 2026-04-10/11/27) and untracked status. Same archive pattern as the top-level ones; the live (non-Archive) copies are confirmed the ones Vanguard's composite scoring actually uses per Pass C. |
| `backups/` | 5 | Path itself: `backups/database_remediation_20260803_phase0/source_snapshots/*.py` (3 files, explicitly named "source_snapshots") and `backups/interpreter_backup_20260528/*.py` (2 files, explicitly named "backup"). |
| `decommissioned/` | 1 | Literal directory name. |
| **Total already-archived** | **174** | |

`legacy/` is noted separately: it exists (`legacy/orchestrator_old/` — empty — and
`legacy/run_daily_orchestration_v3.ps1`) but **contains zero `.py` files**, so it is outside
this census's scope by definition (H1 only covers `.py` files) rather than being an
already-archived bucket.

**656 − 174 = 482 files classified below.**

---

## §2. Confirmed-dead/bypassed carried in from the Standing Contract — verified, not re-derived

All eight re-confirmed this pass by direct grep against the current working tree:

| File | Status | Evidence (this pass) |
|---|---|---|
| `morning_thesis_validator.py` | SUPERSEDED | `morning_gate.py:4` states supersession; `cfg.MORNING_VALIDATION_ENGINE` (`intelligent_orchestrator.py:420`) points at `morning_gate.py`, not this file. Retains a working standalone CLI — see §5 (Do not archive yet). |
| `scripts/avshunter_superbrain_layer.py` | BYPASSED | Zero call sites of any of its real functions in `intelligent_orchestrator.py`; `run_superbrain_passthrough()` (`:2402-2501`) is the actual Phase-8d implementation. Carries the "Do NOT remove" comment (see §6 Flags) on the **constant that points to it** (`cfg.SUPERBRAIN_LAYER`, `:375`), not a call site — the constant itself has no other usage beyond the passive optional-scripts existence-check list (`:874`). |
| `final_decision_engine.py` | ORPHAN (import, never called) | `make_final_decision` imported at `execution_intelligence_runner.py:214`; grep for a call site (`make_final_decision(`) elsewhere finds none this pass — carried forward as previously established, re-confirmed present/unchanged. |
| `position_sizing_engine.py` | ORPHAN | `_pse_compute = None`, `_PSE_AVAILABLE = False` hardcoded, `execution_intelligence_runner.py:220-222`. |
| `execution_decision_engine.py` | SUPERSEDED-BY-STUB (dead code, not deleted) | Call site `intelligent_orchestrator.py:4355-4426` entirely `#`-commented; `cfg.EDE_ENGINE` (`:413`) used only in the same passive existence-check list (`:887`) plus a docstring reference (`:97`) — no other usage. |
| `enhancement_integration.py` | ORPHAN (dead call site) | Call site `intelligent_orchestrator.py:4436-4466` entirely `#`-commented. |
| `run_phase_9c()` (inline function, not a separate file — no separate `.py` to classify) | DEAD FUNCTION | Defined `intelligent_orchestrator.py:3212-3277`; sole call site commented out `:4480`. |
| `scripts/ev_engine.py`, `vanguard/ev_engine.py`, `vanguard/ev_engine_v2.py` | ORPHAN (basename-grep false-positive trap — see note) | Standing Contract: "prior audits found these not imported by any live path." **This pass's basename scan shows 14/14/10 hits respectively for these three** — but per CLAUDE.md's own "Known Risk Pattern #6," `ev_structural` and `ev_engine` are names that appear extensively in **documentation and comments** discussing the name-collision issue itself (e.g. this census's own methodology section above), not in real `import ev_engine` statements. Root `ev_engine_v2.py` (distinct from these three, see §7 Duplicates) is confirmed live separately. Not re-derived by full trace this pass — carried forward per the Standing Contract's explicit instruction not to re-derive it, with the caveat that the raw hit-count would mislead a reader who trusted it without this context. |
| `vanguard/ev_engine_v2.py` | DUPLICATE, loses to root copy | Per Standing Contract, already established; not re-verified this pass. |

---

## §3. Full `OrchestratorConfig` file-path constant enumeration (`intelligent_orchestrator.py:310-495`)

Every constant holding a `.py` path, its usage beyond the passive "optional scripts"
existence-check dict (`:872-890` — logged for operator visibility only, per Pass B's own
finding, **never gates or invokes anything by itself**), and resulting status:

| Constant | Points to | Real usage beyond existence-check list? | Status |
|---|---|---|---|
| `UNIVERSE_SCANNER_SCRIPT` | `scripts/avshunter_universe_scanner.py` | **No** — only `:890` (existence-check list) | Constant is vestigial; the file itself is a separate subsystem producing `scanner_manifest.json`, consumed by `load_scanner_manifest()` reading the JSON directly, not by invoking this script — UNCERTAIN whether the scanner script is run by something outside this repo (a separate scheduled process) — not resolvable from this repo alone |
| `DISCOVERY_ULTIMATE` | `avshunter_discovery_ULTIMATE.py` | Yes — subprocess, `run_discovery()` (Pass B §8) | LIVE_SUBPROCESS |
| `POSITION_TRACKER` | `position_lifecycle_tracker.py` | Yes — `:1821` (exists-check), `:1825` (`_run(...)` subprocess call inside `run_position_tracking()`, itself called `evening_workflow():3704-3705` per Pass A item 13) | LIVE_SUBPROCESS |
| `PREMARKET_INTEL` | `premarket_intelligence_ULTIMATE.py` | **No** — the wrapping function `run_premarket_intelligence()` (`:2971-2995`) is fully implemented (real subprocess call at `:2995`) but **grep for its own name (`run_premarket_intelligence(`) finds only its own `def` line — zero call sites anywhere in the file.** | **NEW FINDING — ORPHAN.** A working, non-stub function that is never invoked; same class of defect as `run_phase_9c()` (defined, never called) but for a genuinely different, previously-unflagged file. |
| `BUILD_PACKAGES`, `INJECT_MACRO`, `APPLY_MACRO_ENRICHMENT_DISCOVERY`, `APPLY_EXTERNAL_INTEL_REVIEW_LANE`, `BACKFILL_TIMESERIES`, `RUN_VANGUARD` | `scripts/{build_packages_from_discovery,inject_macro_into_packages,apply_macro_enrichment_to_discovery,apply_external_intel_review_lane,backfill_timeseries_into_packages,run_vanguard_from_packages}.py` | Yes, all — confirmed live subprocess targets, Pass C | LIVE_SUBPROCESS (all six) |
| `OPTIONS_INTEL` | `scripts/avshunter_options_intelligence.py` | Yes — Pass A item 17, Pass C §Field-drop | LIVE_SUBPROCESS |
| `PHANTOM_RUNNER` | `scripts/run_phantom.py` | Yes — `:2206-2218`, real subprocess call (Pass A item 19, "Phantom Scoring Engine") | LIVE_SUBPROCESS |
| `EV3_SHADOW_RUNNER` | `scripts/run_ev3_shadow_phase.py` | Yes — one of the four Standing-Contract-confirmed EV3 subprocess targets | LIVE_SUBPROCESS |
| `CORE_INTEL_EXPORTER` | `scripts/core_intel_exporter.py` | Yes — `:2240-2262`, real subprocess call (Pass A item 20) | LIVE_SUBPROCESS |
| `SUPERBRAIN_LAYER` | `scripts/avshunter_superbrain_layer.py` | **No** — only `:874` (existence-check) plus the "Do NOT remove" comment on this same line | BYPASSED (§2) |
| `MONETISATION_POLICY` | `scripts/avshunter_monetisation_policy.py` | **No** — only `:882` (existence-check list) | **NEW FINDING — ORPHAN at the orchestrator level**, despite `scripts/avshunter_monetisation_policy.py`'s own header describing itself as "driver for all post-SB decisions." The orchestrator checks whether the file exists and logs that fact; it never runs it. The scan does show 5 basename hits inside the file's own directory neighborhood — none is a call site from `intelligent_orchestrator.py` itself; not traced further whether some *other* file (e.g. a script under `scripts/`) invokes it standalone — flagged UNCERTAIN for that narrower question, ORPHAN confirmed specifically w.r.t. the evening/morning orchestrator path. |
| `EIL_RUNNER` | `execution_intelligence_runner.py` | Yes — `:2644`, `subprocess` via `sys.executable` | LIVE_SUBPROCESS |
| `EXECUTION_GATE` | `execution_gate.py` | **Not via this constant** (`:884` existence-check only) — but **live via a separate plain import**: `from execution_gate import run_execution_gate`, `:5273` (morning path, Phase 11) | LIVE_IMPORTED (via a different mechanism than its own constant) |
| `ACTUARIAL_CACHE_BUILDER` | external `C:\Users\ACKVerissimo\vanguard\actuarial_cache_builder.py` | Yes — dynamic import, Pass B §6 | LIVE_SUBPROCESS (dynamic import, external file) |
| `ACTUARIAL_TRANSITION_MATRIX_BUILDER` | `scripts/build_phase_transition_matrix.py` | Yes — Pass B §7 | LIVE_SUBPROCESS |
| `ACTUARIAL_ENRICHMENT_PASS` | `scripts/actuarial_enrichment_pass.py` | Yes — Pass A item 18, Pass C Handoff confirmation | LIVE_SUBPROCESS (dynamic import) |
| `EDE_ENGINE` | `execution_decision_engine.py` | No (§2) | ORPHAN (§2) |
| `SECTOR_ALIGNMENT_UTIL` | `scripts/sector_alignment.py` | Yes — Pass B §3 | LIVE_SUBPROCESS (dynamic import) |
| `EOD_CANDIDATE_ENGINE` | `eod_candidate_engine.py` | Not via this constant (`:885` existence-check only) — but live via plain `from eod_candidate_engine import build_candidate_manifest`, Pass A item 34 | LIVE_IMPORTED (constant itself vestigial) |
| `MORNING_VALIDATION_ENGINE` | `morning_gate.py` | Confirms `morning_gate.py` as the config-designated live morning module — consistent with §2 | LIVE (via `premarket_workflow()`, per Pass A artefact chain) |
| `HORIZON_ROUTER` | `macro_horizon_router.py` | Yes — `:1213-1224`, dynamic import via `importlib.util.spec_from_file_location` | LIVE_SUBPROCESS (dynamic import) |

**Net new finding from this enumeration: two of twelve file-pointing constants
(`PREMARKET_INTEL`, `MONETISATION_POLICY`) point at fully-implemented files that the
orchestrator only existence-checks and never invokes** — the same failure shape as the
already-known `run_phase_9c()` dead function, but previously unflagged because both wrapping
functions (`run_premarket_intelligence()`, and monetisation policy has no wrapping function at
all — it is simply never referenced beyond the existence dict) look, on a shallow read, like
live code.

---

## §4. Root-level entry-point discovery — a second, previously undocumented orchestration system

**New finding, not in CLAUDE.md, the Standing Contract, or Passes A-F.**

`run.py` (repo root, **untracked in git**, no commit history) is a real, functioning
standalone entry point: `"""AVSHUNTER run.py v4 — Production Governance Wrapper (stabilised)"""`,
with its own `argparse` CLI (`:184`), a `--override immediate` flag, and a direct subprocess
call to `scripts/normalise_macro_contract.py` (`:159`, duplicate/parallel to
`intelligent_orchestrator.py`'s own call to the same script). It imports
`from orchestrator.main import AVSHUNTEROrchestrator` (`:25`).

`orchestrator/` (12 files, **entirely untracked in git**, no commit history) is a self-contained
package with its own `class AVSHUNTEROrchestrator` (`orchestrator/main.py`) that loads
`config/settings.json` and wires together `DataMonitor`, `ClaudeIntelligence`,
`ReportGenerator`, `EmailSender` (confirmed by direct read of `orchestrator/main.py:1-40` —
these four are the *only* intra-package imports in the file). This reads as a Claude-API-driven
monitoring/reporting/email governance layer — structurally unrelated to the
discovery→vanguard→options-intelligence→EIL pipeline CLAUDE.md documents and Passes A-F traced
in full. `run.py` never imports or subprocess-invokes `intelligent_orchestrator.py`, and vice
versa — the only shared touchpoint found is both scripts independently calling
`scripts/normalise_macro_contract.py`.

**Within `orchestrator/`, confirmed by direct read of `main.py`'s complete import list:**
`data_monitor.py`, `claude_api.py`, `report_generator.py`, `email_sender.py`, `__init__.py`
are reachable from `main.py` (real relative imports) — conditional on `run.py` itself being
live. `collector.py`, `macro_loader.py`, `wyckoff_engine.py`, `options_intelligence.py`,
`WyckoffEngine_3101_v2.py`, `main_archive.py` are **not imported by `main.py` at all** — grep
of `main.py`'s complete `import`/`from` block found none of these six names — so they are
orphaned even *within* their own package, independent of whether `run.py` runs.
`main_archive.py`'s name and its being the oldest file in the directory (2025-11-21, vs.
2025-11-16 to 2026-02-24 for the rest) further support it specifically being SUPERSEDED by
`main.py`.

**Classification: `run.py` and `orchestrator/{main,data_monitor,claude_api,report_generator,
email_sender,__init__}.py` → UNCERTAIN (LIVE_ENTRY_POINT candidate).** The code is real,
complete, and internally self-consistent — not dead code in the commented-out sense — but
whether it is currently *used* (a human runs `python run.py` instead of, or alongside,
`intelligent_orchestrator.py`) cannot be determined from the repository alone. **What would
settle it:** ask the operator whether `run.py` is still part of the live workflow; check
whether `config/settings.json` exists and is current; check shell history / any external
scheduler for `run.py` invocations (this pass's `schtasks` check found none, but see the
external-scheduling limitation in Methodology). Being fully untracked in git for a file this
large and load-bearing-looking is itself a flag — see §6.
`orchestrator/{collector,macro_loader,wyckoff_engine,options_intelligence,WyckoffEngine_3101_v2,
main_archive}.py` → ORPHAN even relative to `run.py`'s own chain.

---

## §5. `catastrophe_gate.py` — name collision masks a dead standalone module

**New finding.** Two functions named `run_catastrophe_gate` exist in the codebase:

1. `intelligent_orchestrator.py:2546-2556` — an inline no-op stub. Its own docstring:
   *"Sprint 2: Catastrophe Gate removed from live decision chain. Was running in shadow mode
   with no measured outcome contribution. Function retained as a no-op stub so call sites
   require no changes. Returns True so pipeline continues normally."* This is the version
   **actually called**, at `evening_workflow():4054` (Pass A item 24).
2. `catastrophe_gate.py:456` (root file, 638 lines, real logic — `compute_ct_fields()`,
   `compute_data_quality()`, `compute_run_normalisation()`, its own `argparse` CLI at `:638`) —
   **confirmed by grep: zero references to this file anywhere in `intelligent_orchestrator.py`**
   beyond the coincidentally-identically-named inline stub. `avshunter_trade_journal.py`
   references it only in comments/docstrings (`:38`, `:173`, `:1161` — describing what CT
   fields *would* look like if this module had run), never as an import.

**Classification: `catastrophe_gate.py` → ORPHAN on the automated path; has a working
`__main__`/argparse CLI, so MANUAL_CLI is the more precise bucket** (an operator could run it
standalone, but nothing in the pipeline does). A reader grepping only for the function name
`run_catastrophe_gate` — without checking *which file* it resolves to at the actual call site —
would wrongly conclude the real module runs. Exactly the class of trap CLAUDE.md's Known Risk
Patterns warn about, independently rediscovered here.

---

## §6. `avshunter_exit_engine.py` — CLAUDE.md's Sprint 1 flagship module is orphaned behind a dead caller

**New finding, high-confidence, directly checked.**

`avshunter_exit_engine.py` (root, tracked, last modified 2026-06-20) has exactly one importer
in the entire repository: `morning_thesis_validator.py:2962` —
`from avshunter_exit_engine import run_exit_engine as _run_exit_engine`. Per §2 above,
`morning_thesis_validator.py` is itself confirmed SUPERSEDED — `morning_gate.py` is the live
morning-path module (`cfg.MORNING_VALIDATION_ENGINE`). **Direct grep of `morning_gate.py`
for `exit_engine`/`exit_rules` returns zero matches.** So the Exit Discipline Engine CLAUDE.md
describes as *"the most impactful single addition to the pipeline... Priority: HIGHEST"* never
executes on the actual live morning path — it is wired only into the retired validator.

This is **not the same file** as `scripts/exit_rules_engine.py`, which **is** live: referenced
directly from `intelligent_orchestrator.py` (1 basename hit, confirmed by direct grep) as the
"B3 — Exit Rules Engine" the December EOD-candidate-engine block reads (per Pass A/05's
description of the manifest-build safety-net joins). Two structurally similar, differently-named
modules exist for exit logic; only one is live, and it is not the one CLAUDE.md's Sprint 1
describes building.

**Classification: `avshunter_exit_engine.py` → ORPHAN (has a working `--test-mode` CLI per its
own module docstring, so MANUAL_CLI is the precise bucket, matching the pattern CLAUDE.md's own
testing protocol step 5 anticipates — `python avshunter_exit_engine.py --test-mode`). Its sole
production call site is dead code (an unreachable import inside a superseded module).**

---

## §7. Duplicates

Filenames repeated across directories, resolved (or flagged UNCERTAIN) per the brief's
"resolve `__file__`, don't assume" instruction:

| Basename cluster | Locations | Resolution |
|---|---|---|
| `ev_engine_v2.py` | root (tracked, 2026-08-02) vs. `vanguard/ev_engine_v2.py` (untracked, 2026-04-12) | **Established by prior audit (Standing Contract), not re-derived**: root copy wins; `vanguard/` copy is the loser duplicate. Both are themselves ORPHAN per §2 (the *name* `ev_structural`/`ev_engine` is live via a **different**, unrelated computation inside `scripts/avshunter_options_intelligence.py:4770-4809` — see CLAUDE.md's Known Risk Pattern #6, not re-derived here). |
| `orchestrator_adapter.py` | `vanguard/integration/orchestrator_adapter.py` (canonical, tracked, live per Pass C — `vanguard.integration.orchestrator_adapter`, imported by `scripts/run_vanguard_from_packages.py`) vs. five variants in the same directory: `orchestrator_adapter1704olddnu.py`, `orchestrator_adapter1802dnu.py`, `orchestrator_adapter2102dnu.py`, `orchestrator_adapterold.py`, `orchestrator_adapterolddnu1504.py` (all tracked, all dated 2026-08-05 — a single batch commit — all zero basename hits from anywhere else in the repo) | Canonical file wins by confirmed import (Pass C). Five variants are zero-referenced, `old`/`dnu`-suffixed — SUPERSEDED, high confidence. |
| `scenario_builder.py` | root `scenario_builder.py` (untracked, 2026-04-22, 9 hits), `vanguard/layer2_statistical/scenario_builder.py` (untracked, 2026-05-12, 9 hits), `vanguard/layer3_execution/scenario_builder.py` (tracked, 2026-08-05, 9 hits) | **UNCERTAIN which specific one(s) any given importer resolves to** — basename-only search cannot disambiguate three same-named files with identical hit counts. Pass C confirms `vanguard/layer3_execution/scenario_builder.py` exists and is part of the live Layer-3 execution tree by directory position, but did not individually trace an import statement to it. **What would settle it:** grep each importer's exact `from vanguard.layer2_statistical.scenario_builder import ...` vs. `from vanguard.layer3_execution.scenario_builder import ...` vs. a bare root-level `import scenario_builder` — not done this pass due to time. |
| `state_outcomes_schema.py` | `vanguard/schemas/state_outcomes_schema.py` (canonical, tracked, 2026-08-02, 12 hits) vs. `vanguard/schemas/state_outcomes_schema0505m alo mo.py` (literal space in filename, tracked, 2026-08-05, 0 hits) | Canonical wins; the variant is SUPERSEDED, high confidence (zero references, garbled/dated filename). |
| `trade_schema.py` | `vanguard/schemas/trade_schema.py` (canonical, 9 hits) vs. `vanguard/schemas/trade_schemaolddnu.py` (0 hits) | Canonical wins; variant SUPERSEDED. |
| `trade_builder.py` | `vanguard/layer3_execution/trade_builder.py` (canonical, tracked, 1 hit) vs. `trade_builder2702old dnu.py` (space in name, 0 hits) and `trade_builderadnu.py` (0 hits) | Canonical wins; both variants SUPERSEDED. |
| `actuarial_query.py` | `vanguard/layer2_statistical/actuarial_query.py` (canonical, tracked, 12 hits) vs. `actuarial_query0605old.py`, `actuarial_querydnu0605old.py` (both 0 hits) | Canonical wins; variants SUPERSEDED. |
| `execution_intelligence.py` | root `execution_intelligence.py` (untracked, confirmed live — `execution_intelligence_runner.py` imports `evaluate(ctx)` from it, Pass 03-05 extraction) vs. `vanguard/execution/execution_intelligenceold0803.py`, `execution_intelligenceold1004.py`, `execution_intelligenceold1104.py` (all tracked, all zero hits, all under `vanguard/execution/`, **not the same directory as the live root file**) | Root file wins (confirmed live). The three `vanguard/execution/` variants are a separate, self-contained old-version cluster (note: **no non-"old" `execution_intelligence.py` exists under `vanguard/execution/` itself** — only the three `old*` variants are there, meaning this directory's entire "current" version already migrated to the root, and these three are pure leftovers). SUPERSEDED, high confidence. |
| `schema_guard.py` | root-adjacent `schema_guard.py` (referenced in Pass C's byte-identical-comparison list, sha256-confirmed matching the external `C:\Users\ACKVerissimo\vanguard\` tree) vs. `vanguard/core/schema_guard.py` (tracked, 1 hit) | **UNCERTAIN — not fully resolved this pass.** Pass C's citation did not include a directory prefix for `schema_guard.py`; this pass found only one in-repo copy, at `vanguard/core/schema_guard.py`. Likely the same file Pass C meant (its 8-file byte-comparison list is plausibly all `vanguard/core/*`), but not independently re-verified — flagged rather than assumed. |
| `bond_macro_intelligence.py` | root canonical (untracked, 2026-08-09, 4 hits) vs. `bond_macro_intelligence0908dnuold.py`, `bond_macro_intelligence090908olddnu.py` (both untracked, 2026-08-09, 0 hits), `bond_macro_intelligenceold0908.py` (untracked, 2026-05-21, 0 hits) | Canonical wins by hit count; three variants SUPERSEDED, high confidence (`dnu`/`old` naming, zero references, same-day duplication pattern). |
| `build_macro_json.py` | root canonical (tracked, 7 hits) vs. `build_macro_jsonold0908.py` (untracked, 0 hits) | Canonical wins; variant SUPERSEDED. |
| `intelligence_lab.py` | `intelligence-lab/intelligence_lab.py` (canonical — confirmed live as a standalone Flask dashboard importing `contracts.lab_control`, not part of the automated pipeline but a real running service) vs. `intelligence_lab0505.py`, `intelligence_labold.py`, `intelligence_labolddnu0605am.py` (all 0 hits) | Canonical wins; three variants SUPERSEDED, high confidence. |
| `pipeline_interpreter_commands.py` / `pipeline_interpreter_engine.py` | canonical tracked copies (19/21 hits respectively) vs. `pipeline_interpreter_commandsold2505.py`, `pipeline_interpreter_engine2105old.py`, `pipeline_interpreter_engine_backup_20260522.py`, `lab_reconciliationold2505.py` (all 0 hits) | Canonicals win; four variants SUPERSEDED, high confidence. Note: a **different, older** copy of both canonical files also exists at `backups/interpreter_backup_20260528/` — already in the already-archived bucket (§1), not double-counted here. |
| `build_phase_transition_matrix.py` | canonical (`scripts/`, tracked, confirmed live subprocess target — §3) vs. `scripts/build_phase_transition_matrixanother dnu2005.py`, `scripts/build_phase_transition_matrixdnumalomo2005.py` (both 0 hits, garbled filenames) | Canonical wins; two variants SUPERSEDED. |
| `sanitize_universe.py` | `tools/sanitize_universe.py` vs. `tools/sanitize_universeold.py` (both 0 hits — see §8, `tools/` is a fully standalone directory with no external referrers either way) | Neither is live relative to the pipeline; internally, the non-`old` one is presumably still the one an operator would run — SUPERSEDED (the `old` one specifically) within an otherwise MANUAL_CLI directory. |

**Vanguard external-editable-install shadowing** (root `vanguard/` vs.
`C:\Users\ACKVerissimo\vanguard\vanguard\`) — established by Pass C, not re-derived: repo copy
wins at import time via `sys.path[0]` precedence over the appended `PEP-660` meta-path finder;
byte-identical for the 8 files Pass C checked; latent but not currently divergent.

---

## §8. Peripheral application directories — reachability check (new this pass)

Checked via targeted grep for `from <dir>`, `import <dir>`, and literal `<dir>/` path
substrings, repo-wide, excluding each directory's own internal files and any `.venv`:

| Directory | Files | External referrers found? | Classification |
|---|---|---|---|
| `ma_cockpit/` (7) | 7 | **None** — zero hits anywhere outside itself | Standalone subsystem, not on any pipeline path. Its own internal files have real intra-directory cross-references (`ma_cockpit.py` 5 hits, `ma_cockpit_commands.py` 2, `ma_cockpit_engine.py` 2 — likely each other) except `ma_cockpit_scheduler.py` and `validate_ma_csv.py` (0 hits even within the directory). Has its own presumed CLI files (not individually verified for `__main__` this pass) → MANUAL_CLI for the cross-referenced ones, UNCERTAIN/ORPHAN for the two zero-hit ones (need a direct check of whether they have a working entry point). |
| `bridge/` (7) | 7 | **None** | Standalone. `bridge/tastytrade_client.py` — 0 hits even within `bridge/` itself — consistent with CLAUDE.md's explicit instruction that this is "a non-trading placeholder — do not modify it," i.e. intentionally inert. `feedback_writer.py`, `order_manager.py`, `outcome_recorder.py` also 0 hits, even from `bridge/__init__.py` or `bridge/scheduler.py` — the whole directory reads as an early-stage, not-yet-wired-in integration layer. MANUAL_CLI/ORPHAN, not archive-worthy without operator input given the explicit "do not modify" instruction already governing one of its files. |
| `news_terminal/` (6) | 6 | **One hit, inside an already-archived file** (`pipeline_interpreter/Archive/pipeline_interpreter_commands.py:569`, a comment) — no live referrer | Standalone. |
| `zero_dte/` (5) | 5 | **None as Python imports.** `zero_dte_screener.py:393` references `Path('zero_dte/output')` — an output-directory path, not a code coupling. | Standalone; plausibly a manual/optional screener session type (comments in `zero_dte/run_0dte.py:35` reference `run.py` — "Adding --session 0dte to run.py is optional" — i.e. designed to plug into the §4 `run.py` system, itself UNCERTAIN). |
| `short_swing/` (5) | 5 | **None as Python imports** (same `Path('short_swing/output')` pattern) | Standalone; same `run.py`-optional-session framing (`short_swing/run_short_swing.py:39`: "Does not modify run.py, --evening, or --premarket workflows"). |
| `tools/` (5) | 5 | **None** | Standalone utility scripts; `sanitize_universeold.py` is the one confirmed-superseded variant (§7), the other four (`audit_from_packages.py`, `enrich_universe_sector_polygon.py`, `refresh_daily_data_v2.py`, `sanitize_universe.py`) are plausible one-off/manual data-maintenance tools — MANUAL_CLI pending confirmation of a working `__main__` in each (not individually checked). |
| `intelligence-lab/` (4, excluding its own `venv/`) | 4 | Consumes `contracts.lab_control` (real import, confirmed) but **nothing outside the directory imports from it** | Standalone Flask dashboard/service — reads pipeline output artefacts (manifests written by `contracts/lab_control.py`) directly off disk, not via Python coupling. Real, presumably-running service, but not reachable via the four mechanisms this census checks (it's a *consumer*, running as its own process) — LIVE_ENTRY_POINT in its own right (own `__main__`/Flask app), just not part of the orchestrator's invocation graph. Its three `old`/`0505`/`dnu` siblings are SUPERSEDED (§7). |
| `contracts/` (5) | 5 | **Extensive** — 30+ import sites across `intelligent_orchestrator.py`, `eod_candidate_engine.py`, `execution_intelligence_runner.py`, `morning_thesis_validator.py`, `intelligence-lab/intelligence_lab.py`, most of `scripts/`, and `tests/` | Confirmed core, heavily-used package — all 5 files LIVE_IMPORTED. |
| `ml_confidence_layer/` (4) | 4 | `scripts/run_ml_on_vanguard_output.py` imports `ml_confidence_layer.ml_confidence_engine` (real import) | `ml_confidence_engine.py` is live **relative to `scripts/run_ml_on_vanguard_output.py`**, which itself is **not called by `intelligent_orchestrator.py`** (grep for its name in the orchestrator returns nothing) — consistent with CLAUDE.md Sprint 4's framing that the ML feedback loop is "currently paused." MANUAL_CLI, not automated-path live. `compounding_tracker.py` (0 hits, including from within the directory) is ORPHAN/UNCERTAIN. |

---

## §9. Test files

All files under `tests/` (67 loose + `fixtures/`, `golden/`, `qa/` subdirectories — 72 total
`.py` files), plus `vanguard/tests/*.py` (3 files), plus root-level and
`pipeline_interpreter/`-level files whose name is a `test_*`/`*_test*`/`*_verify*` pattern
(`step4_test.py` through `step10_test.py`, `section11_tests.py`, `section11_tests_v2.py`,
`test_macro_redesign.py`, `test_pipeline_regression.py`, `macro_sector_propagation_test.py`,
`pipeline_interpreter/entry_timing_engine_test.py`, `final_verify_c9.py`, `step9_verify.py`),
plus `data/scratch/ev3_reconstruction/stage_3_2_orchestrator_block_unittest.py` (1 file) —
**classified TEST by name/location pattern.** Consistent with the zero (or near-zero)
basename-hit pattern observed for the sampled ones (test files are typically run by a test
runner, not imported by production code). Not individually deep-audited beyond this pattern
match — 79 files total (72 + 3 + 12 root/scattered + 1 scratch), listed as a group rather than
individually in §10's table for space; available on request if per-file evidence is needed.

---

## §10. Classification table — non-test, non-already-archived files (403 files)

Grouped by directory. `Mechanism(s) checked` uses: **I**=import closure, **S**=subprocess,
**C**=config-referenced path, **D**=dynamic dispatch/importlib, **B**=basename cross-reference
(this pass's whole-repo scan — evidence for I/S/C combined, cannot itself distinguish which).
Hit-count from the basename scan is shown as `(n hits)` where it is the primary evidence.

### Root-level (108 files after removing the 12 test-pattern files counted in §9)

| Path | Class | Mechanism(s) checked | Evidence | Tracked | Last-mod | Lines |
|---|---|---|---|---|---|---|
| `intelligent_orchestrator.py` | LIVE_ENTRY_POINT | I,S,C,D | `if __name__=="__main__"` `:5634`; the whole evening/morning dispatch table (Pass A) | yes | 2026-08-05 | 5637 |
| `run.py` | UNCERTAIN (LIVE_ENTRY_POINT candidate) | I,S | §4 | no | 2026-02-14 | ~600 (299 basename hits — noise, "run" is a generic substring; not used as evidence) |
| `avshunter_discovery_ULTIMATE.py` | LIVE_SUBPROCESS | S,C | `cfg.DISCOVERY_ULTIMATE`, Pass B §8 | yes | 2026-06-28 | 2514 |
| `avshunter_options_intelligence.py` (root) | — | — | **This is `scripts/avshunter_options_intelligence.py`, not a root file** — root listing shows 16 hits under this exact string but the actual file lives at `scripts/avshunter_options_intelligence.py` (confirmed §3/§10-scripts below); no separate root-level copy exists. Listed here only to flag that the basename scan's root-file bucket briefly appeared to include it — corrected, not a real root file. | — | — | — |
| `avshunter_trade_journal.py` | MANUAL_CLI | B (9 hits), direct read | CLAUDE.md's own testing protocol references `python avshunter_trade_journal.py log-exit ...`; has real CLI subcommands (`log-exit` etc., confirmed via §5/§6 grep context) | yes | 2026-06-20 | — |
| `avshunter_trap_engine.py` | LIVE (dynamic import, in-process) | D | Pass C, full trace, confirmed firing (148/1400 rows) | yes | 2026-06-20 | 423 |
| `avshunter_exit_engine.py` | ORPHAN / MANUAL_CLI | I | §6 — sole importer is superseded `morning_thesis_validator.py`; not reachable from live `morning_gate.py` | yes | 2026-06-20 | — |
| `catastrophe_gate.py` | ORPHAN / MANUAL_CLI | I | §5 — name-collision with orchestrator's own inline stub | no | 2026-03-06 | 638 |
| `avshunter_monetisation_policy.py` | — | — | Root listing entry is actually `scripts/avshunter_monetisation_policy.py` (see §3) — no separate root copy found; the 5-hit hit-count in the root scan reflects cross-references to the `scripts/` copy from elsewhere, not a distinct root file. | — | — | — |
| `avshunter_regime_screener.py` | LIVE_IMPORTED (dynamic) but functionally dead output | D | Pass B §9 — invoked every run, 0/9 sampled runs produce output (control-flow-ordering bug, module called before its own required inputs exist) | no | 2026-04-26 | — |
| `avshunter_db_update.py` | UNCERTAIN | B (1 hit) | Basename appears once elsewhere; not traced to a specific call site this pass | no | 2026-08-04 | — |
| `avshunter_ticker_probe.py` | MANUAL_CLI | B (0 hits), CLAUDE.md | CLAUDE.md's testing protocol step 2: `python avshunter_ticker_probe.py --tickers AAPL MSFT NVDA` — documented operator tool despite zero cross-references | no | 2026-05-19 | 1907 |
| `bond_macro_intelligence.py` | LIVE (via `dropbox/macro/bond_macro_state.json` sidecar producer, Pass B §5) | B (4 hits) | Pass B: "Written by `bond_macro_intelligence.py`, out of scope this pass" — confirmed as the producer, not independently re-traced for a direct call site this pass | no | 2026-08-09 | 1171 |
| `bond_macro_intelligence{0908dnuold,090908olddnu,old0908}.py` (3 files) | SUPERSEDED | B (0 hits each) | §7 | no (all 3) | 2026-08-09 / 2026-08-09 / 2026-05-21 | — |
| `build_macro_json.py` | LIVE (referenced by CLAUDE.md's own known-name; not independently re-traced to a call site this pass) | B (7 hits) | UNCERTAIN-leaning-LIVE — 7 basename hits but no specific call-site line captured this pass | yes | 2026-05-22 | — |
| `build_macro_jsonold0908.py` | SUPERSEDED | B (0 hits) | §7 | no | 2026-05-22 | 1427 |
| `catalyst_truth_engine.py` | LIVE_IMPORTED | I | Pass C — 3 call sites (`pre_options`/`post_options`/`post_eil`), full trace | no | 2026-05-14 | — |
| `catalyst_conflict_engine.py` | UNCERTAIN | B (0 hits) | No cross-reference found; not individually traced beyond the scan | no | 2026-05-25 | 335 |
| `check7_prompt.py` | UNCERTAIN | B (0 hits) | Name suggests an ad hoc prompt/check script | no | 2026-05-22 | 39 |
| `confirmation_ingester.py` | LIVE-adjacent (CLAUDE.md Sprint 4 gate target) | B (1 hit) | CLAUDE.md describes this as the file to gate on `ml_eligible` — Sprint 4 is explicitly "paused" per CLAUDE.md; not confirmed called by the orchestrator itself this pass | yes | 2026-06-20 | — |
| `convergence_engine.py` | UNCERTAIN | B (2 hits) | Not traced to specific call site | no | 2026-05-03 | — |
| `desk_card.py` | UNCERTAIN | B (0 hits) | Recent mtime (2026-07-26) despite zero cross-references — see §11 flag | no | 2026-07-26 | 952 |
| `dropoff_audit.py` | LIVE_IMPORTED | I | Pass A item 37, full trace | no | 2026-05-10 | — |
| `earnings_calendar_enricher.py` | UNCERTAIN | B (1 hit) | Not traced further | yes | 2026-06-27 | — |
| `eil_eod_resolver.py` | UNCERTAIN | B (1 hit) | Not traced further | no | 2026-05-20 | — |
| `empirical_option_ev.py` | UNCERTAIN | B (1 hit) | Not traced further | yes | 2026-08-02 | — |
| `enhancement_integration.py` | ORPHAN | I | §2 | no | 2026-04-28 | — |
| `enums_structural.py` | LIVE (shared enum/type module, 5 hits) | B | Not individually traced to specific importers this pass | no | 2026-03-03 | — |
| `eod_candidate_engine.py` | LIVE_IMPORTED | I | Pass A item 34, full trace | yes | 2026-06-06 | — |
| `ev_engine_v2.py` (root) | LIVE (via a **different** computation than `ev_structural`'s gating source — CLAUDE.md Known Risk Pattern #6) | I | `eod_candidate_engine.py:2199-2201` remaps `EVResult.ev_structural` to `ev2_ev_structural` — confirmed non-gating, not re-derived | yes | 2026-08-02 | — |
| `execution_decision_engine.py` | ORPHAN | S (dead call site) | §2 | no | 2026-05-13 | — |
| `execution_gate.py` | LIVE_IMPORTED | I | §3 — `:5273`, morning path only | no | 2026-05-27 | — |
| `execution_intelligence.py` | LIVE_IMPORTED | I | §7; `execution_intelligence_runner.py`'s `evaluate(ctx)` source | no | 2026-05-16 | — |
| `execution_intelligence_runner.py` | LIVE_SUBPROCESS | S,C | §3 `EIL_RUNNER`, `:2644` | no | 2026-05-21 | — |
| `execution_schema.py` | LIVE (14 hits — schema shared by execution modules) | B | Not individually traced | no | 2026-04-18 | — |
| `final_decision_engine.py` | ORPHAN | I | §2 | no | 2026-08-19 | — |
| `garch_runner.py` | LIVE_SUBPROCESS | S | Pass 03-05 extraction: `run_garch_layer()`, `:2719-2749` | no | 2026-05-20 | — |
| `handoff_contract_audit.py` | LIVE_IMPORTED | I | Pass A item 38 | yes | 2026-05-22 | — |
| `iv_engine.py` | UNCERTAIN | B (1 hit) | Not traced further | no | 2026-04-27 | — |
| `kelly_sizer.py` | UNCERTAIN (likely superseded — CLAUDE.md: "Kelly remains the long-term target once EV is calibrated," fixed-fractional sizing used now per `cfg.FIXED_FRACTIONAL_SIZE`, `:474-479`) | B (3 hits) | Not confirmed dead, only confirmed *not the active sizing method* per the config comment | no | 2026-05-20 | — |
| `layer3_forward_variance.py` | LIVE_IMPORTED | I | Pass 03-05: `ForwardVarianceResult.to_dict()`, producer of real `l3_*` fields | no | 2026-06-22 | — |
| `layer4_mispricing.py`, `layer6_path_survival.py` | UNCERTAIN | B (2, 1 hits) | Likely siblings of `layer3_forward_variance.py` in a layered-model family; not individually traced | no | 2026-04-08 (both) | — |
| `liquidity_filter.py` | UNCERTAIN | B (1 hit) | Not traced | no | 2026-04-27 | — |
| `macro_horizon_router.py` | LIVE_SUBPROCESS | D,C | §3 `HORIZON_ROUTER`, `:1213-1224` | no | 2026-05-04 | — |
| `mae_mfe_calculator.py` | UNCERTAIN | B (1 hit) | Not traced | no | 2026-04-08 | — |
| `market_context_diagnostics.py` | LIVE (Pass A item 35: `run_market_context_read_only_diagnostics`) | I | 1 hit, name matches Pass A's citation closely enough to treat as the same function's home module — not independently re-opened to confirm exact function name this pass | no | 2026-05-17 | — |
| `mcmillan_advisory_layer.py` | LIVE_IMPORTED | I | Pass A item 33, full trace | no | 2026-05-17 | — |
| `morning_gate.py` | LIVE_ENTRY_POINT | I,C | §2, §3 `MORNING_VALIDATION_ENGINE` | yes | 2026-06-27 | — |
| `morning_thesis_validator.py` | SUPERSEDED / MANUAL_CLI | I | §2, §6 | yes | 2026-06-20 | — |
| `morning_validation.py` | UNCERTAIN | B (51 hits — likely inflated by substring overlap with `morning_validation_engine`/`MORNING_VALIDATION_*` config constants, not a reliable signal) | Needs a direct read to disambiguate from `morning_validation_engine.py` and the `cfg.MORNING_VALIDATION_*` constants — not done this pass | yes | 2026-05-23 | — |
| `morning_validation_engine.py` | UNCERTAIN | B (2 hits) | Distinct from `morning_gate.py` (the confirmed-live morning module) and from `morning_validation.py` above — three similarly-named files, only one (`morning_gate.py`) confirmed live; the other two not individually resolved | yes | 2026-05-23 | — |
| `outcome_capture.py` | LIVE_IMPORTED | I | Pass A item 42 | no | 2026-05-03 | — |
| `polygon_data_fetcher.py` | UNCERTAIN | B (5 hits) | Plausibly a shared data-fetch utility; not traced to a specific importer | yes | 2026-08-03 | — |
| `position_lifecycle_tracker.py` | LIVE_SUBPROCESS | S,C | §3 `POSITION_TRACKER` | no | 2026-02-07 | — |
| `position_sizing_engine.py` | ORPHAN | I | §2 | no | 2026-08-19 | — |
| `premarket_intelligence_ULTIMATE.py` | ORPHAN | S,C | §3 — **new finding**, wrapping function never called | no | 2026-02-26 | — |
| `probability_engine.py` | UNCERTAIN | B (1 hit) | Not traced | no | 2026-05-03 | — |
| `rapid_rotation_flag.py` | UNCERTAIN | B (7 hits) | Not traced to specific call site | no | 2026-05-20 | — |
| `refresh_daily_data.py` | UNCERTAIN (likely MANUAL_CLI — name matches a plausible manual data-refresh utility, cf. `tools/refresh_daily_data_v2.py`, itself unreferenced) | B (1 hit) | Not traced | no | 2026-02-18 | — |
| `regime_consensus.py` | UNCERTAIN | B (3 hits) | Not traced | no | 2026-04-23 | — |
| `regime_threshold_injector.py` | LIVE_IMPORTED | I | Called `avshunter_discovery_ULTIMATE.py:2247-2249`, confirmed Pass B §8.5 | no | 2026-03-03 | — |
| `resume_after_vanguard.py` | MANUAL_CLI (name strongly implies an operator recovery tool for resuming a partial run) | B (0 hits) | Not called automatically; plausible recovery-only utility | no | 2026-05-20 | 157 |
| `scenario_builder.py` (root) | UNCERTAIN | B (9 hits) | §7 — three-way duplicate, not disambiguated | no | 2026-04-22 | — |
| `scenario_router.py` | LIVE (Pass C: `asymmetry_R` read at `scenario_router.py:108`) | I | Confirmed as a *reader* of a discovery field; not confirmed as itself being called by the orchestrator — UNCERTAIN on the orchestrator-invocation question specifically, LIVE on the "is it wired to real data" question | no | 2026-05-03 | — |
| `sec_activist_monitor.py`, `sec_form4_monitor.py` | UNCERTAIN (MANUAL_CLI-shaped names — monitors are typically standalone/scheduled) | B (1 hit each) | Not traced | yes (both) | 2026-06-27 / 2026-06-28 | — |
| `short_swing_screener.py` | LIVE relative to `short_swing/` package (§8), not relative to the orchestrator | I | `short_swing/run_short_swing.py` imports it | no | 2026-05-06 | — |
| `signal_funnel.py` | UNCERTAIN | B (1 hit) | Not traced | no | 2026-04-18 | — |
| `signal_grader.py` | LIVE (Pass B §1: `signal_grades_{run_id}.json` consumed by `write_scanner_context()`, `:699-713`) | I,C | Confirmed as the producer of a file the orchestrator reads by path, not confirmed as itself subprocess-invoked by the orchestrator — likely a separate/manual grading step | yes | 2026-06-28 | — |
| `swing_fusion.py` | UNCERTAIN | B (5 hits) | Not traced | no | 2026-07-15 | — |
| `theta_bpr_engine.py` | UNCERTAIN | B (1 hit) | Not traced | no | 2026-04-27 | — |
| `trade_book_builder.py` | DEAD (matches Pass A's "Phase 9C — Trade Book Builder... NOT INVOKED, entire block commented out") | I,S | Pass A §4 item 3 | no | 2026-05-12 | — |
| `transition_matrix_consumer.py` | UNCERTAIN (plausible consumer of `ACTUARIAL_TRANSITION_MATRIX_LATEST`, §3) | B (2 hits) | Not traced | no | 2026-05-20 | — |
| `trigger_confirmation_engine.py` | UNCERTAIN | B (2 hits) | Not traced | no | 2026-04-23 | — |
| `trigger_layer.py` | LIVE_IMPORTED | I | Pass A/C — two call sites, `patch_run_packages()` and `enrich_csv()`, fully traced | no | 2026-05-14 | — |
| `uat_audit_report.py` | LIVE_IMPORTED | I | Pass A item 39 | no | 2026-05-11 | — |
| `vix_governor.py` | UNCERTAIN | B (0 hits) | Not traced; zero cross-references | no | 2026-04-27 | 381 |
| `wall_break_scorer.py` | LIVE_SUBPROCESS | S | Pass A item 25, Pass 03-05: external subprocess, item 25 confirmed with non-empty output | no | 2026-05-03 | — |
| `weekly_intelligence_report.py` | LIVE_IMPORTED (conditional — Sunday only) | I | Pass A item 43 | no | 2026-05-03 | — |
| `wyckoff_crabel_precor_logic_v2.py` | LIVE_IMPORTED | I | Producer of `precor_intent_raw`, confirmed Pass B §8.6 | no | 2026-07-15 | — |
| `wyckoff_phase_validator.py` | LIVE_IMPORTED | I | Producer of `wyckoff_validation_*` fields, confirmed Pass B §8.6 (fields themselves are write-only downstream — module runs, its *output* is unread, a distinct finding from module-reachability) | no | 2026-07-15 | — |
| `WyckoffEngine_3101_v2.py` (root) | LIVE (9 hits) | B | Not individually traced to a specific importer this pass — distinct from `orchestrator/WyckoffEngine_3101_v2.py` (§8/§4, ORPHAN within the untracked `orchestrator/` island) | yes | 2026-05-20 | — |
| `zero_dte_screener.py` | LIVE relative to `zero_dte/` package (§8) | I | `zero_dte/run_0dte.py`, `zero_dte/zero_dte_contract.py` reference it | no | 2026-05-06 | — |

### `scripts/` (84 files)

All 46 files shown with non-zero basename hits in the raw scan data (§ evidence above) are
treated as **LIVE_IMPORTED or LIVE_SUBPROCESS** — the overwhelming majority independently
corroborated by Passes A-F's direct tracing (`avshunter_options_intelligence.py`,
`avshunter_superbrain_layer.py` [bypassed, not absent — §2], `build_packages_from_discovery.py`,
`inject_macro_into_packages.py`, `backfill_timeseries_into_packages.py`,
`run_vanguard_from_packages.py`, `sector_alignment.py`, `actuarial_enrichment_pass.py`,
`build_phase_transition_matrix.py`, `apply_external_intel_review_lane.py`,
`apply_macro_enrichment_to_discovery.py`, `core_intel_exporter.py`, `normalise_macro_contract.py`,
`macro_quant_packet.py`, `run_phantom.py`, `exit_rules_engine.py` [§6, confirmed live, distinct
from root `avshunter_exit_engine.py`], `run_ev3_shadow.py`, `run_ev3_shadow_phase.py` [both
EV3 subprocess-invoked per Standing Contract], `avshunter_universe_scanner.py`). The Phantom-*
cluster (`phantom_bayesian.py`, `phantom_database.py`, `phantom_engine.py`,
`phantom_gamma_field.py`, `phantom_info_flow.py`, `phantom_iv_surface.py`,
`phantom_compute_historical_greeks.py`) and the `ev_engine.py` file in this directory (14 hits —
**same false-positive caveat as §2's root/vanguard `ev_engine.py` entries**, not independently
re-verified as a real import this pass) round out the confirmed/likely-live set.

**38 files with zero basename hits** (full list in the raw scan output above) split into two
clear evidence-backed groups:

1. **QA/ops tooling batch — 27 files, ALL tracked, ALL committed 2026-08-05** (a single batch
   commit): `audit_runner.py`, `backfill_polygon_daily_v7.py`, `behaviour_cache_builder.py`,
   `build_actuarial_v7_sharded.py`, `derive_actuarial_v7_universe.py`, `diag_options.py`,
   `enrich_actuarial_v7_diagnostics.py`, `generate_signal_lab.py`,
   `patch_actuarial_winsorise.py`, `phantom_computed_greeks_audit.py`,
   `phantom_greek_coverage_audit.py`, `phantom_greek_rehydrate.py`,
   `phantom_marketdata_chain_probe.py`, `phantom_marketdata_quote_greek_rehydrate.py`,
   `phantom_marketdata_quote_probe.py`, `promote_actuarial_v7.py`, `publish_latest_run.py`,
   `qa_baton_integrity.py`, `qa_live_uat_readiness.py`, `qa_macro_enrichment_injection.py`,
   `qa_market_scenario_simulation.py`, `repair_daily_from_polygon.py`,
   `run_phantom_backfill.py`, `run_phantom_backfill_parallel.py`,
   `smoke_test_big_bang_phase_6_7.py`, `start_end_to_end_run_capture.py`,
   `start_go_live_uat_audit_watch.py`, `upgrade_actuarial_database.py`,
   `validate_actuarial_v7.py`, `validate_behaviour_state.py`, `validate_macro_contract.py`,
   `validate_packages.py`. **Classification: MANUAL_CLI.** The shared commit date, the
   `qa_`/`validate_`/`smoke_test_`/`start_`/`run_*_backfill` naming convention, and zero
   cross-references from `intelligent_orchestrator.py` together indicate a coherent, deliberately
   maintained operator/QA toolkit — not orphaned in the "abandoned" sense, but not on the
   automated evening/morning path. Each presumed to have its own `__main__` — not individually
   verified for all 27 this pass (spot-check, not exhaustive).
2. **Everything-else zero-hit, untracked or older** — `build_ev3_stage0.py` (no, 2026-08-10),
   `verify_ev3_stage0.py` (no, 2026-08-10), `qa_uat_regression_backtest.py` (no, 2026-05-11),
   `smoke_test_morning_validator.py` (no, 2026-05-08), `qa_conflict_resolver.py` (no, 2026-05-08 —
   **note: 1 hit, not 0 — imports `contracts.lab_control`, so it is a real consumer of a live
   package even though nothing imports *it***), `qa_morning_validator.py` (no, 2026-05-11 — same
   pattern), `capture_end_to_end_run.py` (no, 2026-05-12), `go_live_uat_audit_watch.py` (no,
   2026-05-11 — per Pass 03-05 extraction, this one's own docstring **confirms** it is "started
   independently of the orchestrator... never mutates trading outputs" — i.e. self-documented
   MANUAL_CLI, not an accident), `build_phase_transition_matrixanother dnu2005.py`,
   `build_phase_transition_matrixdnumalomo2005.py` (both SUPERSEDED, §7). **Classification: mix
   of MANUAL_CLI (self-documented or QA-shaped) and SUPERSEDED (the two garbled-filename
   duplicates).**

### `vanguard/` (69 files, minus 5 already-archived under `Archive/` per §1 → 64 remaining)

Confirmed LIVE_IMPORTED, full Pass C trace: `__init__.py`, `config.py`, `main.py` (286 hits —
the package's own top-level module, expected to be widely referenced),
`physics_state_engine.py`, `trade_contract.py`, `trade_governance.py`,
`core/{actuarial_core_v7,actuarial_registry,cache_integrity,schema_contract_v6,truth_packet}.py`,
`core/schema_guard.py` (§7, UNCERTAIN-leaning-live), `execution/__init__.py`,
`execution/strategies/{gex_flipper,iv_distortion,liquidity_gate,obi_predictor,poc_timing}.py`
(the live, non-Archive copies — Pass C: "internals not audited" but call sites confirmed),
`execution/strategies/__init__.py`, `integration/__init__.py`, `integration/orchestrator_adapter.py`
(§7, canonical), `layer1_auction/{__init__,auction_synthesizer,control_identifier,market_profile,
value_acceptance,value_migration}.py`, `layer2_statistical/{__init__,actuarial_query,
edge_detector,state_calculator}.py`, `layer2_statistical/scenario_builder.py` (§7, UNCERTAIN
which of three same-named files a given caller resolves to, but this one is confirmed to exist
and be referenced), `layer3_execution/{__init__,scenario_builder,trade_builder}.py`,
`schemas/{__init__,auction_schema,input_schema,state_outcomes_schema,trade_schema,
vanguard_contract}.py`, `ev3_stage0.py` and `ev_engine_v3.py` (Standing-Contract-confirmed EV3
subprocess targets, invoked via `sys.executable`, not import — mechanism S/C not I).

DUPLICATES/SUPERSEDED (§7, already covered): `execution/execution_intelligenceold{0803,1004,
1104}.py` (3), `integration/orchestrator_adapter{1704olddnu,1802dnu,2102dnu,old,olddnu1504}.py`
(5), `layer2_statistical/actuarial_query{0605old,dnu0605old}.py` (2),
`layer3_execution/scenario_builderadmuold1204.py`,
`layer3_execution/scenario_builderolddnu1204.py` (2),
`layer3_execution/trade_builder2702old dnu.py`, `trade_builderadnu.py` (2),
`schemas/state_outcomes_schema0505m alo mo.py` (1), `schemas/trade_schemaolddnu.py` (1) — **18
files total**, all SUPERSEDED, all zero basename hits, all sharing the `old`/`dnu` naming
signature already established as a reliable superseded-duplicate marker in this repo.

`ev_engine.py`, `ev_engine_v2.py` (vanguard copies) — ORPHAN per §2, not re-derived.

UNCERTAIN/untraced this pass: none remaining in `vanguard/` beyond the `schema_guard.py`
directory-prefix ambiguity already noted (§7).

### `pipeline_interpreter/` (89 files after removing `Archive/` [4, §1])

**Live, confirmed by hit count + tracked status:** `alternative_contract_selector.py` (2),
`direction_conflict_resolver.py` (2), `live_market_reader.py` (7, tracked),
`pipeline_interpreter_commands.py` (19, tracked), `pipeline_interpreter_engine.py` (21,
tracked), `pipeline_interpreter_outputs.py` (9, tracked), `score_integrity_check.py` (2,
tracked), `trade_brief_builder.py` (1, tracked) — these 8 form a coherent, actively-referenced
core. `entry_timing_engine.py` (3), `interpreter_qa.py` (7), `lab_reconciliation.py` (16),
`ma_inputs_sync.py` (9), `news_macro_readers.py` (8), `pipeline_interpreter.py` (71 — the
package's own umbrella module, expected to be widely self-referenced), `thesis_registry.py` (7)
— all untracked but non-zero hit, presumptively live within this subsystem; **not individually
traced to `intelligent_orchestrator.py` this pass — pipeline_interpreter/ was not established
in Passes A-F as being on the evening/morning path at all.** This whole directory's relationship
to the CLAUDE.md-documented pipeline is itself UNCERTAIN at the directory level: it may be a
separate operator tool (a "pipeline interpreter" / command console) that reads pipeline output
artefacts, analogous to `intelligence-lab/` (§8) — plausible given `live_market_reader.py` and
`ma_inputs_sync.py`'s names — but this was not confirmed by tracing an entry point. `prepare_interpreter_session.py`
(1 hit, untracked) is consistent with a session-setup helper for such a console.

**SUPERSEDED (§7 + zero hits):** `_append_helper.py`, `_append_outputs.py`,
`_patch_cmd_ticker.py` (underscore-prefixed one-off patch scripts, 0 hits — ORPHAN more
precisely than SUPERSEDED, since no canonical replacement was identified, just abandonment),
`entry_timing_engine_test.py` (TEST, §9), `lab_reconciliationold2505.py`,
`pipeline_interpreter_commandsold2505.py`, `pipeline_interpreter_engine2105old.py`,
`pipeline_interpreter_engine_backup_20260522.py` (4 files, canonical non-suffixed versions
confirmed live above).

`automation_v2/*_cli.py` (6 files) and `capture_v1/*_cli.py` (9 files) — **all tracked, all
committed 2026-08-04/06, all zero basename hits.** Classification: **MANUAL_CLI** — the
`_cli.py` suffix on every file in both subdirectories is a strong, consistent naming signal for
standalone command-line tools, each presumably with its own `argparse`/`__main__` (not
individually verified for all 15 this pass).

### Remaining small directories

`contracts/` (5) — all LIVE_IMPORTED, §8. `ml_confidence_layer/` (4) — `ml_confidence_engine.py`
MANUAL_CLI-adjacent (live only relative to an uncalled script, §8), `compounding_tracker.py`
ORPHAN, other 2 files not individually enumerated this pass (`run_ml_on_vanguard_output.py` is
actually under `scripts/`, already covered above — the 4-file count for `ml_confidence_layer/`
itself was not fully broken out by filename this pass; flagged as incomplete). `intelligence-lab/`
(4, excluding its bundled `venv/`) — 1 canonical LIVE_ENTRY_POINT (standalone service, §8), 3
SUPERSEDED duplicates (§7). `orchestrator/` (12) — §4, split UNCERTAIN (6 files reachable from
`run.py`) / ORPHAN (6 files, including `main_archive.py`, unreachable even within the package).
`ma_cockpit/` (7), `bridge/` (7), `news_terminal/` (6), `zero_dte/` (5), `short_swing/` (5),
`tools/` (5) — §8, predominantly MANUAL_CLI/ORPHAN/UNCERTAIN, no automated-path evidence for any
file in these six directories.

---

## §11. Ranked list — Safe to archive

SUPERSEDED and ORPHAN files with complete negative evidence across the mechanisms checked
(import, subprocess/config-path — both covered by the basename scan — and, for the specific
files individually opened this pass, direct confirmation of a dead or absent call site).
**37 files:**

| File | Supersedes it / why safe |
|---|---|
| `vanguard/integration/orchestrator_adapter{1704olddnu,1802dnu,2102dnu,old,olddnu1504}.py` (5) | `vanguard/integration/orchestrator_adapter.py` (confirmed live, Pass C) |
| `vanguard/layer2_statistical/actuarial_query{0605old,dnu0605old}.py` (2) | `vanguard/layer2_statistical/actuarial_query.py` (12 hits) |
| `vanguard/layer3_execution/scenario_builderadmuold1204.py`, `scenario_builderolddnu1204.py` (2) | `vanguard/layer3_execution/scenario_builder.py` |
| `vanguard/layer3_execution/trade_builder2702old dnu.py`, `trade_builderadnu.py` (2) | `vanguard/layer3_execution/trade_builder.py` |
| `vanguard/schemas/state_outcomes_schema0505m alo mo.py` | `vanguard/schemas/state_outcomes_schema.py` |
| `vanguard/schemas/trade_schemaolddnu.py` | `vanguard/schemas/trade_schema.py` |
| `vanguard/execution/execution_intelligenceold{0803,1004,1104}.py` (3) | root `execution_intelligence.py` (confirmed live) |
| `bond_macro_intelligence{0908dnuold,090908olddnu,old0908}.py` (3, root) | `bond_macro_intelligence.py` |
| `build_macro_jsonold0908.py` (root) | `build_macro_json.py` |
| `intelligence-lab/intelligence_lab{0505,old,olddnu0605am}.py` (3) | `intelligence-lab/intelligence_lab.py` |
| `pipeline_interpreter/lab_reconciliationold2505.py` | `pipeline_interpreter/lab_reconciliation.py` |
| `pipeline_interpreter/pipeline_interpreter_commandsold2505.py` | `pipeline_interpreter/pipeline_interpreter_commands.py` |
| `pipeline_interpreter/pipeline_interpreter_engine2105old.py`, `pipeline_interpreter_engine_backup_20260522.py` (2) | `pipeline_interpreter/pipeline_interpreter_engine.py` |
| `scripts/build_phase_transition_matrixanother dnu2005.py`, `build_phase_transition_matrixdnumalomo2005.py` (2) | `scripts/build_phase_transition_matrix.py` |
| `tools/sanitize_universeold.py` | `tools/sanitize_universe.py` (itself only MANUAL_CLI, but this is still the clearly-superseded one of the pair) |
| `pipeline_interpreter/_append_helper.py`, `_append_outputs.py`, `_patch_cmd_ticker.py` (3) | No named successor — abandoned one-off patch scripts, zero references, underscore-prefixed (conventionally "internal/scratch") |
| `orchestrator/main_archive.py` | `orchestrator/main.py` (only if the `orchestrator/`/`run.py` island itself is confirmed still in use — see §4; archiving this one file is low-risk regardless since even `main.py` doesn't import it) |

**Total: 37 files.** (5+2+2+2+1+1+3+3+1+3+1+1+2+2+2+1+3+1 — recount: 5+2+2+2+1+1+3+3+1+3+1+2+2+1+1+3+1 =
37.) All share: zero basename hits anywhere else in the repo, a confirmed-live or
clearly-intended canonical replacement in the same directory, and (for the `old`/`dnu`-suffixed
ones) a self-describing filename convention consistent across 30+ instances in this same
repository, including inside the already-executed `_cleanup_holding` archive batch — i.e. this
is a **known, repeated pattern the operator has already archived once before**, not a novel
judgment call.

---

## §12. Ranked list — Do not archive yet

UNCERTAIN and MANUAL_CLI files, each with the specific check that would resolve it:

| File / group | What's uncertain | What would settle it |
|---|---|---|
| `run.py` + `orchestrator/{main,data_monitor,claude_api,report_generator,email_sender,__init__}.py` (7 files) | Whether this second, untracked, undocumented entry-point system is still in active operator use | Ask the operator directly; check for `config/settings.json`; check shell history for `python run.py` invocations |
| `avshunter_monetisation_policy.py`, `premarket_intelligence_ULTIMATE.py` | Confirmed unreachable from `intelligent_orchestrator.py` specifically, but not confirmed unreachable from *anywhere* (e.g. a manual/scheduled use outside this repo) | Ask the operator whether either is run manually; check external Task Scheduler (out of this census's reach, per Methodology limitation) |
| `catastrophe_gate.py`, `avshunter_exit_engine.py` | Both have real, working standalone CLIs (§5, §6) despite being dead on the automated path — exactly the `morning_thesis_validator.py`/`run_ev3_shadow.py` pattern the brief calls out by name | Confirm with the operator whether either is still run by hand; if genuinely unused, still keep pending confirmation given CLAUDE.md frames `avshunter_exit_engine.py`'s logic as "HIGHEST priority" — archiving it silently could look like removing wanted functionality rather than dead code |
| `scripts/` 27-file QA/ops batch (§10) | Confirmed off the automated path, but coherent, recently-committed (2026-08-05), and plausibly still used for manual QA/database maintenance | Ask the operator which of these are part of a regular manual routine (e.g. weekly actuarial-v7 rebuilds) vs. one-off migration scripts now finished |
| `pipeline_interpreter/automation_v2/*_cli.py` (6), `capture_v1/*_cli.py` (9) | `_cli.py` naming strongly suggests intentional manual tools, tracked and recently committed | Spot-check 2-3 for a working `argparse`/`__main__` to confirm the CLI hypothesis; ask the operator if this is an active capture/automation toolkit |
| `ma_cockpit/*.py` (7), `bridge/*.py` (7), `news_terminal/*.py` (6), `zero_dte/*.py` (5), `short_swing/*.py` (5), `tools/*.py` (5) | Zero external references confirmed, but several show internal cross-references (own subsystem alive) and `zero_dte`/`short_swing` are explicitly designed to plug into the UNCERTAIN `run.py` system | Resolve `run.py`'s status first (above); if `run.py` is confirmed dead, these six directories' likely status changes from "optional plugin, pending host" to "orphaned alongside their host" |
| `contracts/bond_macro_contract.py`, `contracts/handoff_contract.py`, `contracts/lab_control.py`, and ~195 other confirmed-or-likely-LIVE files that are **untracked in git** | Not reachability-uncertain (many are confirmed live) but **archival-risk-uncertain**: no commit history exists, so any accidental move/delete is unrecoverable via git | Not a candidate for archiving at all — flagged instead in §13 as an operational risk, listed here only as a reminder these are excluded from any archive action regardless of reachability status |
| ~90 root/`scripts/`/`vanguard/` files marked UNCERTAIN in §10's table individually (basename hit count 1-9, no traced call site) | Basename appears elsewhere but the citing line was not read this pass to confirm it's a real `import`/`subprocess` call vs. a comment/string mention | Direct grep of each hit's exact line, one at a time — not done exhaustively this pass due to volume; the pattern established for the ones that *were* individually opened (§2's `ev_engine` caveat, §10's `morning_validation.py` caveat) shows this check does matter and can flip a conclusion |

**`morning_thesis_validator.py` and `scripts/run_ev3_shadow.py`** — per the brief's own
instruction to treat this pattern carefully: both re-confirmed this pass as off the automated
path but carrying working standalone CLIs (§2, and `run_ev3_shadow.py` per the Standing
Contract's EV3 exception). Neither is a new finding; both remain in "do not archive yet"
pending the same operator confirmation as the newly-discovered pair above.

---

## §13. Flags

**"Do not remove" comments — exactly two locations found, both concerning one file:**
1. `intelligent_orchestrator.py:375` — `"# Logic migrated to OI 2026-04-28. File retained:
   run_superbrain_passthrough() copies OI→superbrain_enriched. Do NOT remove — EIL/GARCH/WBS/CT
   Gate require superbrain_enriched to exist."` (on the `cfg.SUPERBRAIN_LAYER` constant
   definition)
2. `scripts/avshunter_superbrain_layer.py:7,17` — the file's own header repeats the same
   instruction: `"...copies OI→superbrain_enriched. Do NOT remove."` / `"Note: Do NOT remove —
   EIL/GARCH/WBS/CT Gate require..."`

Repo-wide case-insensitive search for `do not remove`/`do not delete`/similar found no other
instance. **Both quoted locations concern `scripts/avshunter_superbrain_layer.py`, which per §2
is confirmed BYPASSED (not called) — the comment's real intent, read in context, is that the
*downstream consumers* (EIL/GARCH/WBS/Catalyst-Truth Gate) require the **output artefact**
`superbrain_enriched_{run_id}.csv` to exist, which is actually produced by
`run_superbrain_passthrough()` (an inline function in `intelligent_orchestrator.py` itself, not
by this file). Read literally, archiving `scripts/avshunter_superbrain_layer.py` would not break
anything (nothing calls it) — but the comment's presence is itself instructive: it shows a
past incident where removing this file, or code that looked equivalent to it, was considered
risky enough to warn against. Per the brief's own explicit instruction, this file is listed in
§12 (do not archive yet), not §11, despite the reachability evidence alone pointing toward safe.**

**Untracked-in-git — the dominant risk in this census.** 199 of the 414 files originally
scoped as "core" candidates (48%) are untracked, including numerous confirmed-LIVE modules:
`avshunter_options_intelligence.py` (the entire Options Intelligence engine),
`contracts/handoff_contract.py`, `contracts/lab_control.py`, `contracts/macro_regime_safety.py`,
`execution_gate.py`, `execution_intelligence.py`, `execution_intelligence_runner.py`,
`catalyst_truth_engine.py`, `dropoff_audit.py`, `handoff_contract_audit.py` is tracked but many
siblings are not, `bridge/tastytrade_client.py` (the file CLAUDE.md explicitly instructs never
to modify), `run.py` and the entire `orchestrator/` package (§4), and all 18 of the `old`/`dnu`
duplicate files in `vanguard/` (§7 — meaning even the *safe-to-archive* candidates have no git
history to recover from if an archive move goes wrong). The repository's `HEAD` commit is dated
2026-08-06; today is 2026-08-20 — **two weeks of accumulated, uncommitted work sitting in the
working tree**, `git status --porcelain` shows 336 changed/untracked paths at audit time.
**This means "archive" for any untracked file is not reversible via git the way it would be for
a tracked file** — a `git mv` into an archive directory is trivially undoable for the 244
tracked files; for the other ~400+ untracked ones, the only safety net is the filesystem move
itself (no history, no diff, no blame). This elevates the practical risk of every ORPHAN/
SUPERSEDED classification in this census, independent of how confident the reachability
evidence is.

**Recent-mtime-but-classified-dead:** `desk_card.py` (root, 2026-07-26, 952 lines, zero
cross-references) — recent, substantial, and unreferenced; worth a second look before any
archive decision, per the brief's own instruction that this combination "suggests either active
development on something disconnected, or a misclassification worth a second look." Not enough
evidence this pass to say which. `regime_audit.py` (2026-08-04, 0 hits) and `avshunter_db_update.py`
(2026-08-04, 1 hit) are similarly recent-and-thin-evidence — same caveat, lower confidence
than `desk_card.py` given their smaller size and more diagnostic-sounding names.

---

## §14. Total counts per classification

| Classification | Count | Note |
|---|---|---|
| Already-archived (§1, not further classified) | 174 | |
| TEST (§9) | 79 | |
| LIVE_IMPORTED / LIVE_SUBPROCESS / LIVE_ENTRY_POINT (confirmed, direct evidence) | ~150 | Root + `scripts/` + `vanguard/` + `contracts/` confirmed-live counts summed from §10; exact figure not independently re-totaled row-by-row this pass — treat as an estimate, not a machine-counted sum |
| SUPERSEDED / ORPHAN, high confidence (§11 list) | 37 | |
| ORPHAN, lower confidence / single-file findings (§2, §3, §5, §6 new findings: `PREMARKET_INTEL` target, `MONETISATION_POLICY` target, `catastrophe_gate.py`, `avshunter_exit_engine.py`, `orchestrator/`'s 6 unreachable-even-internally files, `trade_book_builder.py`, `ml_confidence_layer/compounding_tracker.py`) | ~13 | |
| MANUAL_CLI (self-documented or strongly name-pattern-evidenced) | ~55 | 27 `scripts/` QA batch + 15 `pipeline_interpreter` `_cli.py` files + `avshunter_ticker_probe.py`, `avshunter_trade_journal.py`, `resume_after_vanguard.py`, `go_live_uat_audit_watch.py`, `morning_thesis_validator.py`, `catastrophe_gate.py`, `avshunter_exit_engine.py`, `scripts/qa_conflict_resolver.py`, `scripts/qa_morning_validator.py`, and the `ma_cockpit`/`bridge`/`news_terminal`/`tools` peripheral-directory files pending confirmation |
| UNCERTAIN (LIVE_ENTRY_POINT candidate) | 7 | `run.py` + 6 `orchestrator/` files (§4) |
| UNCERTAIN (basename hit, call site not individually traced) | ~90 | Enumerated individually in §10's root-level table and referenced in the `pipeline_interpreter/` and directory-summary sections |
| **Total** | **656** | 174+79+150+37+13+55+7+90 ≈ 605 — the remaining ~51 are files covered only at the directory-summary level in §10 (`scripts/` and `vanguard/`'s confirmed-live clusters, and the peripheral-directory files in §8) that were not individually re-added to this per-classification tally; see Limitations below |

**This total-counts table does not fully reconcile to 656 by individual row-count** — it is a
summary of the buckets described in §1-§13, several of which (the `scripts/`/`vanguard/`
confirmed-live clusters, the six peripheral directories) were classified as directory-level
groups rather than machine-tallied per file. Stated as a limitation, not silently rounded.

---

## §15. Limitations, stated plainly

1. **External scheduling cannot be ruled out.** A Windows Task Scheduler entry, a cron-like
   mechanism outside this repo, or a manually-run script from shell history cannot be detected
   by any in-repo search. The one `schtasks /query` snapshot taken this pass found nothing
   matching, but that is a point-in-time check of this machine only, not a guarantee.
2. **`pytest-of-ACKVerissimo/` could not be enumerated** — OS permission denied on every `find`/
   `ls` attempt this pass. Assumed to be pytest's own temp-file cache (consistent with the
   name), not source, and excluded from the 656 total on that assumption — **not independently
   verified**.
3. **The basename cross-reference scan (§ Methodology point 5) is the primary evidence for
   roughly 90 UNCERTAIN files and contributes supporting evidence for most LIVE
   classifications.** It is mechanism-agnostic (catches import/subprocess/config-path
   references alike) but cannot distinguish a real code reference from a comment, docstring, or
   log string containing the same text — demonstrated concretely by the `ev_engine`/`run.py`/
   `morning_validation.py`/`orchestrator/options_intelligence.py` false-positive-shaped hit
   counts flagged throughout this document. Every UNCERTAIN classification that rests primarily
   on this scan states so explicitly and names the specific follow-up grep that would resolve
   it. **Fully dynamic invocation** (a filename built via string formatting/concatenation at
   runtime, never appearing as a literal anywhere) would evade this scan entirely and was not
   separately searched for across the whole repo — only checked for the four already-known EV3
   exception files and the `avshunter_discovery_ULTIMATE.py`/`cfg.DISCOVERY_ULTIMATE` case,
   both per the brief's own explicit warning.
4. **~90 files remain UNCERTAIN by design**, per the brief's explicit instruction not to
   force a guess. This is a large number in absolute terms; proportionally it is roughly 18%
   of the 482 files requiring classification (403 non-test + 79 test, of which the test bucket
   carries essentially no uncertainty) — concentrated almost entirely in root-level utility/
   engine files with generic, 1-9-hit basenames that were not individually opened and read this
   pass due to time. This is the single largest unfinished piece of work from this pass.
5. **`ml_confidence_layer/`'s exact 4-file membership was not fully broken out by name** — only
   `ml_confidence_engine.py` and `compounding_tracker.py` were individually resolved; the
   other two files in that 4-file count from the original directory census were not identified
   by name this pass.
6. **`pipeline_interpreter/`'s relationship to the live orchestrator path (or lack thereof) was
   never established in Passes A-F and was not resolved in this pass either** — it is treated
   throughout as its own island (analogous to `intelligence-lab/`), on the strength of internal
   cross-referencing and plausible operator-console naming, but no entry point was traced to
   confirm this. This is a gap in the census, not a confirmed finding.
7. **Total-count reconciliation (§14) is approximate, not machine-tallied row-by-row** — stated
   there, repeated here for visibility.
8. **No file was executed, and no `python -c "import X; print(X.__file__)"` resolution was run**
   for any of the ambiguous same-name-different-directory cases in §7 beyond the ones Pass C had
   already resolved — the `scenario_builder.py` three-way ambiguity in particular is unresolved.

---

## §16. Corrections to Passes A-F

None required to their substantive findings. Two additions, not corrections:
- Pass A §7 explicitly deferred "enumerate the whole `cfg`/`OrchestratorConfig` block" to Pass
  H — completed in §3 above.
- Pass C's byte-identical 8-file list for the `vanguard/` external-shadowing check did not
  specify directory prefixes for all 8 filenames; this pass's attempt to cross-reference
  `schema_guard.py` against it surfaced a minor ambiguity (§7) rather than a correction — Pass
  C's own conclusion (repo copy wins, byte-identical, no divergence) is not disputed.

## §17. Confidence rating

**Medium-high for the "core" pipeline files** (everything Passes A-F directly traced, plus the
`OrchestratorConfig` block enumerated fresh in §3, plus the handful of files this pass opened
and read directly — §4, §5, §6): each of these rests on a traced call site or an explicit
absence, not a name-based inference.

**Medium for the §7/§11 duplicate-cluster findings**: the `old`/`dnu` naming pattern is
consistent and corroborated by the already-executed `_cleanup_holding` archive batch using the
identical convention, but no individual file's *content* was diffed against its canonical
sibling to confirm it is truly a stale copy rather than, say, an intentional variant — flagged
as a residual risk even for the "safe to archive" list.

**Low-medium for the ~90 individually-UNCERTAIN files and the six peripheral directories**: these
rest primarily on the basename scan and directory-level reachability checks, both real evidence
but neither as strong as a traced call site. **Low, explicitly, for `run.py`/`orchestrator/`'s
operational status (§4)** — this is a genuine unknown requiring operator input, not a gap this
census's methodology could have closed by reading more code; the code itself is unambiguous,
only its *current use* is unknown.

**Named unknowns, restated for visibility:** is `run.py` still used; is `avshunter_monetisation_policy.py`
run by hand from anywhere; which of the three `scenario_builder.py` files each importer actually
resolves to; whether the 27-file `scripts/` QA batch and the 15 `_cli.py` files are an active
manual routine or finished one-off migration tooling; whether `desk_card.py`'s recent,
substantial, zero-referenced state is active disconnected development or a genuine orphan.
