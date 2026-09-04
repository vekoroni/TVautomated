# 03 — Real execution order

**Document:** AVS-E2E-CODE-001 · Step 1
**Evidence run:** `data/output/runs/20260831_010309/`
**Derivation:** AST call-sequence extraction from `intelligent_orchestrator.py`
(`_tooling/extract_order_v2.py` → `_tooling/execution_order_v2.json`),
cross-checked against artefact mtimes in the evidence run.

Order below is **source order within the workflow function**, which for this
orchestrator equals call order: `evening_workflow` is a single linear function
(L3708–L5733) with no loops or dispatch table around the stage calls.
[OBSERVED `intelligent_orchestrator.py:3708-5733`]

---

## 1. Methodological caveat on artefact timestamps (read before using §3)

Artefact mtime is **last write, not stage completion**. Several stages rewrite
already-promoted artefacts in place:

- `patch_horizon_fields_into_csv` is called three times — L4218, L4246, L4508
  [OBSERVED] — and rewrites Discovery/Vanguard/Options/SuperBrain CSVs after
  they were first written;
- the Phase 8.6b trigger block reads and rewrites `eil_enriched` at L4745–L4770
  [OBSERVED];
- `inject_actuarial_into_eil_csv` (L4694) rewrites the EIL CSV [OBSERVED].

This is visible in the evidence run as a tight rewrite cluster at 02:55:42–02:55:55
covering six artefacts first produced much earlier [MEASURED]:

| Artefact | mtime | first produced (inferred from stage order) |
|---|---|---|
| `discovery/discovery_candidates_ultimate_...csv` | 02:55:42 | ~01:06 (Discovery) |
| `vanguard/vanguard_signals.csv` | 02:55:43 | ~01:56 (Vanguard) |
| `options/vanguard_signals_enriched_...csv` | 02:55:45 | ~02:31 (Options) |
| `options/options_intelligence_...csv` | 02:55:46 | ~02:31 (Options) |
| `superbrain/superbrain_enriched_...csv` | 02:55:47 | ~02:50 (passthrough) |
| `superbrain/eil_enriched_...csv` | 02:55:53 | ~02:55 (EIL) |
| `execution/execution_v3_5_...csv` | 02:55:55 | ~02:55 (EIL) |

**Implication note:** in-place rewriting of promoted run artefacts contradicts
AVS-E2E-DATA-LOGIC-001 §14.6 ("write temporary artefact; validate; atomically
promote"). Recorded as a gap, not a recommendation.

Where a stage boundary *is* separated in wall-clock time, the mtimes are usable
as independent confirmation. The Options → Horizon boundary is the clearest
such case and is used below.

---

## 2. Evening workflow — real order

`intelligent_orchestrator.py::evening_workflow` (L3708). `_run(...)` is the
subprocess helper; `LOCAL` marks a function defined in the orchestrator itself.

| # | Line | Stage call | Executes | Principal artefact(s) in evidence run |
|--:|--:|---|---|---|
| 1 | 3790 | `merge_scanner_inputs` / `load_scanner_manifest` / `load_manual_ticker_upload` | LOCAL | universe assembly (no run artefact) |
| 2 | 3791 | `build_augmented_universe` | LOCAL | augmented universe file |
| 3 | 3796 | `write_scanner_context` | LOCAL | scanner context |
| 4 | 3799 | `run_dropoff_audit_checkpoint` | LOCAL → `dropoff_audit.py` | `diagnostics/dropoff_audit_*` (pre) |
| 5 | 3802 | `run_preflight_checks` | LOCAL | preflight status |
| 6 | 3823/3913 | `build_macro_quant_packet` | `scripts/macro_quant_packet.py` | `macro_quant_packet.json` (01:03:13), `macro_snapshot.json` (01:03:13) |
| 7 | 3883 | `_run` (macro normalise) | `scripts/normalise_macro_contract.py` | normalised macro contract |
| 8 | 3959 | `merge_macro_enrichment_into_macro_latest` | LOCAL | `dropbox/macro/macro_intelligence_latest.json` |
| 9 | 4042 | `_run` (packages) | `scripts/build_packages_from_discovery.py`, `inject_macro_into_packages.py`, `backfill_timeseries_into_packages.py` | `packages/*.package.json` |
| 10 | 4115 | **`run_discovery`** | `avshunter_discovery_ULTIMATE.py` (cfg L424) | `discovery/discovery_candidates_ultimate_*.csv` **1,527 rows** [MEASURED] |
| 11 | 4125 | `apply_external_intel_review_lane` | `scripts/apply_external_intel_review_lane.py` | `discovery/external_intel_review_candidates_*.csv` |
| 12 | 4126 | `apply_macro_enrichment_to_discovery` | `scripts/apply_macro_enrichment_to_discovery.py` | discovery CSV rewritten |
| 13 | 4128/4133 | `validate_quality`, `detect_regression` | LOCAL | quality gates |
| 14 | 4134 | `run_position_tracking` | `position_lifecycle_tracker.py` | position state |
| 15 | 4183 | **`run_vanguard_pipeline`** | `scripts/run_vanguard_from_packages.py` (cfg L434); also `avshunter_trap_engine.py` (Phase 5.5, L2407) | `vanguard/vanguard_signals.csv` **1,481 rows** [MEASURED] |
| 16 | 4194 | `run_catalyst_truth_layer` | `catalyst_truth_engine.py` | `catalysts/catalyst_truth_*.csv` |
| 17 | 4196 | `run_position_lock_check` | LOCAL | lock check |
| 18 | 4197 | **`run_options_intelligence`** | `scripts/avshunter_options_intelligence.py` (cfg L437) | `options/options_intelligence_*.csv` **1,248 rows** [MEASURED]; `options_intelligence_latest.csv` mtime **02:31:19** |
| 19 | **4208** | **`run_horizon_router`** | `macro_horizon_router.py` (cfg L531) | `horizon/horizon_{1_5d,6_10d,11_20d,blocked}_*.csv` mtime **02:31:28** |
| 20 | 4218 | `patch_horizon_fields_into_csv` | LOCAL | rewrites Options CSV with horizon fields |
| 21 | 4233 | `run_ev3_governed_shadow` | `scripts/run_ev3_shadow_phase.py` (cfg L443) | `ev3_shadow/ev3_stage1_shadow_*` (02:31:34) |
| 22 | 4234 | `run_ev3_authority_overlay` | `scripts/apply_ev3_authority.py` (cfg L444) | `ev3_shadow/ev3_authority_overlay.csv` (02:31:37) |
| 23 | 4246 | `patch_horizon_fields_into_csv` | LOCAL | second horizon patch |
| 24 | 4251 | `run_catalyst_truth_layer` | `catalyst_truth_engine.py` | catalyst refresh |
| 25 | ~4324 | Phantom scoring (banner L4324) | `scripts/run_phantom.py` → `phantom_engine.py` (cfg L438) | `options/options_intelligence_phantom_*.csv` (02:39:30) |
| 26 | 4398 | `run_core_intel_exporter` | `scripts/core_intel_exporter.py` (cfg L463) | `core_intel/core_intel_*` (02:39:35) |
| 27 | **4416→4421** | **Trigger Layer pass 1 (Phase 8.6)** — `from trigger_layer import patch_run_packages as _tl_patch` | `trigger_layer.py::patch_run_packages` | `trigger_layer_summary_*.csv` (**02:45:10**); patches `packages/` only |
| 28 | 4497 | `run_superbrain_passthrough` | LOCAL (copies OI → superbrain_enriched; `avshunter_superbrain_layer.py` retained but logic migrated, cfg L466 comment) | `superbrain/superbrain_enriched_*.csv` |
| 29 | 4508 | `patch_horizon_fields_into_csv` | LOCAL | third horizon patch |
| 30 | 4519 | `run_catastrophe_gate` | `catastrophe_gate.py` | gate result |
| 31 | 4520 | **`run_wall_break_scorer`** | `wall_break_scorer.py` | `superbrain/wall_break_scores_*.csv` **31 rows** [MEASURED], mtime 02:50:15 |
| 32 | **4690** | **`run_execution_intelligence_layer` (EIL)** | `execution_intelligence_runner.py` (cfg L472) | `superbrain/eil_enriched_*.csv` **1,248**; `execution/execution_v3_5_*.csv` **1,248** [MEASURED] |
| 33 | 4694 | `inject_actuarial_into_eil_csv` | LOCAL | rewrites EIL CSV |
| 34 | 4700 | `run_garch_layer` | `garch_runner.py` | `qomega/garch_forecasts_*.csv` (02:55:25) |
| 35 | 4701 | `merge_garch_into_enriched` | LOCAL | rewrites `eil_enriched` |
| 36 | **4710→4770** | **Trigger Layer pass 2 (Phase 8.6b)** — `from trigger_layer import enrich_csv as _tl_enrich_csv` | `trigger_layer.py::enrich_csv` | rewrites `eil_enriched` **after** Execution CSV already written at step 32 |
| 37 | 4806 | `enforce_handoff_conflict_guard` | LOCAL | handoff guard |
| 38 | 4984 | `run_catalyst_truth_layer` | `catalyst_truth_engine.py` | catalyst refresh |
| 39 | 4998/5019 | `mcmillan_advisory_layer.enrich_csv` | `mcmillan_advisory_layer.py` | advisory columns |
| 40 | **5049→5091** | **`build_candidate_manifest` (EOD Candidate Engine)** | `eod_candidate_engine.py` (cfg L510) | `morning_validation/morning_candidates_*.csv` **201 rows** [MEASURED] (02:56:05) |
| 41 | 5270/5295 | exposure + exit-rules modules | `macro_exposure_resolver.py`, `exit_rules_engine.py` | overlay columns |
| 42 | 5321 | `run_market_context_read_only_diagnostics` | `market_context_diagnostics.py` | `diagnostics/read_only_market_context_*.json` |
| 43 | 5601 | `build_dropoff_audit` | `dropoff_audit.py` | `diagnostics/dropoff_audit_*` (02:56:10) |
| 44 | 5615 | `handoff_contract_audit.audit_run` | `handoff_contract_audit.py` | `diagnostics/handoff_contract_audit_*` (02:56:11) |
| 45 | 5629 | `write_uat_audit_report` | `uat_audit_report.py` | `diagnostics/uat_audit_report_*.json` (02:56:12) |
| 46 | **5639** | `write_final_run_manifest` | `contracts/lab_control.py:1210` | `final_run_manifest.json` |
| 47 | **5654** | `write_final_opportunity_book` | `contracts/lab_control.py` | `intelligence_lab/final_opportunity_book_*.csv` **201 rows** + `.json` (02:56:24) |
| 48 | 5670/5671/5672 | `archive_outputs`, `prune_old_runs`, `generate_report` | LOCAL | archive + report |
| 49 | 5680 | `outcome_capture.run_outcome_capture` | `outcome_capture.py` | outcome capture |
| 50 | 5700 | `weekly_intelligence_report.run_weekly_report` | `weekly_intelligence_report.py` | weekly report |
| 51 | 5721 | `_update_run_meta_status` | LOCAL | `run_meta.json` (02:56:41 — **run closes here**) |

---

## 3. Morning workflow — real order

`intelligent_orchestrator.py::premarket_workflow` (L5733). Only three resolved
stage calls [OBSERVED]:

| # | Line | Stage call | Executes |
|--:|--:|---|---|
| 1 | 5795 | `run_catalyst_truth_layer` | `catalyst_truth_engine.py` |
| 2 | **5799** | `run_morning_gate` | `morning_gate.py::run_morning_gate` (imported inline L5798) |
| 3 | **5817** | `finalize_morning_handoff` | `morning_handoff_finalizer.py` (imported inline L5815) |

`execution_gate.py` is **not** called from `premarket_workflow`. It is reached
from `morning_gate.py` / `morning_handoff_finalizer.py` — traced in the atlas,
not asserted here.

The evidence run `20260831_010309` is an **EOD run**: `morning_validation/`
contains `morning_candidates_*.csv` (produced by the *evening* EOD Candidate
Engine at step 40, not by Morning Gate), and there is no Morning Gate output
artefact in the run directory. Morning-path claims in this atlas are therefore
OBSERVED-from-code and **not** measurable on this run. [MEASURED — absence]

---

## 4. Hotspot ordering questions — resolved

| Question (§5 of the task) | Answer | Evidence |
|---|---|---|
| Horizon Router vs Options Intelligence | **Horizon Router runs AFTER Options Intelligence** | `run_options_intelligence` L4197 → `run_horizon_router` L4208 [OBSERVED]; `options_intelligence_latest.csv` 02:31:19 → `horizon/*.csv` 02:31:28 [MEASURED] |
| Trigger Layer vs EIL / GARCH / Execution output | **Trigger Layer runs twice.** Pass 1 (L4421, packages only) precedes EIL. Pass 2 (L4770, `enrich_csv`) runs AFTER EIL (L4690), after `inject_actuarial` (L4694) and after GARCH (L4700–4701). The Execution CSV is written by EIL at step 32, i.e. **before** trigger pass 2. | [OBSERVED] L4690 < L4700 < L4770; `trigger_layer_summary` 02:45:10 belongs to pass 1 [MEASURED] |
| EOD Candidate Engine vs all of the above | **Last of the analytic stages**: L5091, after trigger pass 2 (L4770) and the handoff guard (L4806) | [OBSERVED] |
| Where macro/bond sidecar is read | Built at L3823/L3913 (`scripts/macro_quant_packet.py`), normalised L3883, merged L3959 — all **before** Discovery (L4115). Re-read later by the EOD engine and Lab. | [OBSERVED] |

**LABEL_VS_ORDER contradictions confirmed** (both asserted by
AVS-E2E-DATA-LOGIC-001 §5 and now verified against code):
1. Horizon Router carries a "Phase 1B" label but executes at position 19 of 51,
   after Options Intelligence at position 18.
2. Trigger Layer carries labels "Phase 8.6"/"8.6b"; pass 2 executes after EIL
   and GARCH, which carry higher-numbered conceptual positions in older docs.

These become CON-001 and CON-002 in the contradictions register.

---

## 5. Confidence

**HIGH** for the evening call sequence and the three hotspot orderings: derived
by AST from a single linear function and independently corroborated by artefact
mtimes at the one boundary where wall-clock separation permits it.

**MEDIUM** for artefact attribution of stages 9, 25, 41 (the `_run`/importlib
call sites pass script paths through config constants and `importlib` loaders;
the mapping is read from `OrchestratorConfig` L400–L539 rather than from a
literal at the call site).

**NOT MEASURABLE** on this run: every morning-path claim (§3).
