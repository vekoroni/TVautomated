# AVS-INV-001 — AVSHUNTER-Intelligence Codebase Usage Inventory and Scale-Back Plan

**Date:** 2026-09-01
**Method:** full directory inventory (device listings) + static import/invocation graph over 419 live-tree Python files (AST imports, subprocess/script-name string references, .bat/.ps1/.sh launcher parsing), BFS reachability from the four production entry points: `intelligent_orchestrator.py --evening`, `intelligent_orchestrator.py --morning` (+ `morning_gate.py`, `morning_handoff_finalizer.py`), `intelligence-lab/intelligence_lab.py` (Flask Lab), and `pipeline_interpreter/` (commands/engine). **Operator note (confirmed 1 Sep):** the `.bat` wrappers (`run_evening.bat`, `run_premarket.bat`) are no longer used — the evening/morning workflows are launched as manual Python commands in PowerShell. The reachability seeds were the Python entry points, so the classification is unaffected; the wrappers themselves move to the retired list (§5a). No previously-reviewed file was re-read into the analysis by hand — the graph was built by script.
**Confidence:** high on the production-reachable set (import edges are precise); moderate on "unreferenced" (static analysis cannot see Windows Task Scheduler entries, manual invocations, or dynamic imports by constructed strings — hence the quarantine protocol in §7 rather than direct deletion). One file (`scripts/run_vanguard_from_packages.py`) failed AST parse and was covered by regex fallback.

---

## 1. Headline numbers

| Population | Count |
|---|---|
| Live-tree Python files analysed | **419** |
| Reachable from production entry points | **187** (45%) |
| Manual/operator tooling and QA (intended, run by hand) | ~90 |
| Standalone subsystems not wired into the pipeline | ~70 (9 subsystems) |
| Unreferenced by anything (dead-code candidates after external-invocation check) | ~45 |
| Backup/superseded copies OUTSIDE Archive dirs (`.bak`, `old`, `dnu`, dated variants) | **~95** |
| Archive/legacy trees | `Archive/` (root, scripts, PI, lab, vanguard×3, orchestrator, ml, schemas), `legacy/`, `decommissioned/`, `_cleanup_holding/`, `datadnuold2405/`, `lab_reconciliationold2505/` |
| Junk directories in repo root | 6 `tmp*`, 18 `pip-*`, 6 `avs_macro_check_*`, 7 `.codex*`, 13 `tests/.codex_tmp_*`, 2 `venv` |

The working production system is roughly **187 files**. Everything else — more than half the Python in the live tree, plus ~95 backup copies sitting *on the import path* — is weight the pipeline carries without using.

---

## 2. PRODUCTION — reachable from entry points (keep; this is the real system)

### 2.1 Shared core (used by both evening and morning/Lab/Interpreter — 52 files)
The governed data layer and contracts. This is the strongest part of the architecture and the base to rebuild on:
- **`canonical_data/`** — all 24 modules in production (registry, contracts, storage, gateway, worklist_gate, session_clock, option_identity, option_chain_store, option_liquidity_lifecycle, market_observation_resolver, intraday_bars, marketdata_response, stage_publisher, historical_prices, history_bridge, request_ledger, lifecycle, discovery_publisher, bundle_freshness, feature_flags, errors, daily_adapter, contract_reference, narrow_refresh*). *`narrow_refresh.py` shows unreferenced — MSI-2 built but not yet wired; expected to go live with the Interpreter refresh path.
- **`contracts/`** — direction_governance, governed_states, lab_control, selected_contract_economics, options_liquidity_lifecycle, options_liquidity_execution_guard, quote_change_evidence, interpreter_handoff(+materializer), interpreter_macro_context, long_option_policy, handoff_contract, macro_enrichment_delta, macro_regime_safety, bond_macro_contract, lab_evidence_overlay.
- **`market_structure/`** — all 5 (MSI).
- **EV3**: `vanguard/ev_engine_v3.py`, `vanguard/ev3_stage0.py`.
- Root: `morning_gate.py`, `morning_handoff_finalizer.py`, `execution_gate.py`, `msi_runtime.py`, `outcome_capture.py`, `avshunter_trade_journal.py`, `earnings_calendar_enricher.py` (morning), `tools/msi_reconcile.py`, `tools/msi_production_readiness.py`, `pipeline_interpreter/ma_inputs_sync.py`.

### 2.2 Evening pipeline only (105 files)
Orchestrator + Discovery (`avshunter_discovery_ULTIMATE.py`, WyckoffEngine_3101_v2, wyckoff_crabel_precor_logic_v2, wyckoff_phase_validator, swing_fusion, asymmetry_gate_swing, enums_structural, regime_threshold_injector, polygon_data_fetcher) + scanner (`scripts/avshunter_universe_scanner.py`, signal-grade path) + packages/backfill (`scripts/build_packages_from_discovery.py`, `scripts/backfill_timeseries_into_packages.py`, `scripts/inject_macro_into_packages.py`) + macro (`scripts/normalise_macro_contract.py`, `scripts/macro_quant_packet.py`, `scripts/macro_exposure_resolver.py`, `macro_horizon_router.py`, `scripts/sector_alignment.py`, `scripts/apply_macro_enrichment_to_discovery.py`, `scripts/apply_external_intel_review_lane.py`) + Vanguard (`scripts/run_vanguard_from_packages.py`, `vanguard/main.py`, config, physics_state_engine, trade_governance, integration/orchestrator_adapter, core/{actuarial_registry,cache_integrity,schema_contract_v6,truth_packet}, layer1 ×5, layer2 {state_calculator, actuarial_query, edge_detector}, schemas ×4, execution/strategies ×5) + Options Intelligence (`scripts/avshunter_options_intelligence.py` + iv_engine) + SuperBrain/WBS/EIL (`scripts/avshunter_superbrain_layer.py`, `wall_break_scorer.py`, `execution_intelligence.py`, `execution_intelligence_runner.py`, execution_schema, ev_engine_v2, eil_eod_resolver, probability_engine, scenario_builder, scenario_router, **avshunter_monetisation_policy — BOTH copies, see §6.1**) + triggers/catalyst (`trigger_layer.py`, `catalyst_truth_engine.py`, `avshunter_trap_engine.py`) + GARCH (`garch_runner.py`, `layer3_forward_variance.py`) + EOD manifest (`eod_candidate_engine.py`, `mcmillan_advisory_layer.py`, `scripts/exit_rules_engine.py`, `scripts/core_intel_exporter.py`) + phantom scoring (7 `scripts/phantom_*` runtime modules + run_phantom) + EV3 shadow (`scripts/run_ev3_shadow(_phase).py`, apply_ev3_authority, ev3_calibration_report) + audits invoked in-run (`dropoff_audit.py`, `handoff_contract_audit.py`, `uat_audit_report.py`, `scripts/data_contract_validator.py`, `market_context_diagnostics.py`) + `avshunter_regime_screener.py`, `position_lifecycle_tracker.py`, `weekly_intelligence_report.py` (Sundays), `premarket_intelligence_ULTIMATE.py`, `scripts/build_phase_transition_matrix.py`, `scripts/behaviour_state_builder.py`, `scripts/actuarial_enrichment_pass.py`, `catalyst→trap` chain, `trade_book_builder.py`, `final_decision_engine.py`, `execution_decision_engine.py`†.

† **Reachable but disabled**: `execution_decision_engine.py`, `final_decision_engine.py`, `trade_book_builder.py`, `kelly_sizer.py`-chain belong to the retired EDE/Kelly/PSE stack — the orchestrator phases that ran them are commented out (9.5/9B/9C); EDE survives only as a config path string. They are prime scale-back candidates *once the commented phases are formally deleted*.

### 2.3 Morning-only, Lab, Interpreter
- Morning: covered by shared core (morning_gate → CDS, economics, structure, earnings enricher; `trigger_confirmation_engine.py` is pulled only by the **retired** morning_validation pair — see §5).
- Lab (2): `intelligence-lab/intelligence_lab.py` + `contracts/lab_evidence_overlay.py` (plus shared core).
- Interpreter (14): pipeline_interpreter.py, commands, engine, outputs, evidence_resolver, assessment_contract, macro_context, news_macro_readers, thesis_registry, trade_brief_builder, lab_reconciliation, interpreter_qa, score_integrity_check, entry_timing_engine.

---

## 3. MANUAL / OPERATOR TOOLING (not in the run path but intended — keep, but move to a `tools/` or `ops/` tree)

Run by hand or by scheduled task; "unreferenced" in the graph is expected for these:
- **Macro production**: `build_macro_json.py`, `bond_macro_intelligence.py` (produce `macro_intelligence_latest.json` / `bond_macro_state.json` consumed as files).
- **Actuarial DB lifecycle**: `scripts/build_actuarial_v7(_sharded).py`, `derive_actuarial_v7_universe.py`, `enrich_actuarial_v7_diagnostics.py`, `validate_actuarial_v7.py`, `promote_actuarial_v7.py`, `avshunter_db_update.py`, `add_state_hash.py`, `upgrade_actuarial_database.py`, `patch_actuarial_winsorise.py`, `behaviour_cache_builder.py`, `validate_behaviour_state.py`, `backfill_polygon_daily_v7.py`, `repair_daily_from_polygon.py`, `refresh_daily_data.py` / `tools/refresh_daily_data_v2.py`, `actuarial_live_updater.py`, `actuarial_hash_diagnostic.py`, `regime_audit.py`.
- **EV3 sidecar**: `scripts/build_ev3_stage0.py`, `verify_ev3_stage0.py`, `promote_ev3_barrier_cache.py`.
- **Phantom backfill**: `scripts/run_phantom_backfill(_parallel).py`, greek rehydrate/audit/probes, `finalize_phantom_weekly_snapshot.py`.
- **CDS ops**: `tools/cds2_*`, `create_cds_baseline.py`, `validate_canonical_data.py`, `sanitize_universe.py`, `enrich_universe_sector_polygon.py`.
- **QA/smoke/UAT**: `scripts/qa_*` ×7, `smoke_test_*` ×3, `go_live_uat_audit_watch` chain, `capture_end_to_end_run` chain, `monitor_uat_pipeline.py`, `tests/` suite (130+ files), `test_pipeline_regression.py`, `test_macro_redesign.py`, `lab_recon_selftest.py`, `final_verify_c9.py`, section11/step tests.
- **Trader utilities**: `desk_card.py` (Run-DeskCard.ps1), `avshunter_ticker_probe.py`, `audit_latest_run.py`, `scripts/publish_latest_run.py`, `resume_after_vanguard.py`, `check7_prompt.py`, `md_api_diagnostic.py`, `diag_options.py`, `polygon_options_validation.py`.
- **Interpreter shadow automation**: `automation_v2/` (~44) + `capture_v1/` (~26) — wired via `run_shadow_automation.bat → lab_batch_cli`; a large, self-contained subsystem. Keep only if the shadow automation is still part of the workflow; it is the biggest single non-core block (~70 files).
- **SEC monitors**: `sec_activist_monitor.py`, `sec_form4_monitor.py` (produce advisory JSONs read by the run).

---

## 4. STANDALONE SUBSYSTEMS — not wired into the pipeline at all

Each is internally consistent but nothing in production imports or invokes it. Decide keep/kill per subsystem, and move survivors out of the pipeline repo:

| Subsystem | Files | Verdict suggestion |
|---|---|---|
| `orchestrator/` + `run.py` | 11 | **Legacy v1 pipeline** (own Wyckoff copy, own options_intelligence, email/Claude reporting) — decommission; nothing references it except its own `run.py` |
| `news_terminal/` | ~8 + task XML | Separate app with its own scheduler task — keep if used, but as its own repo |
| `ma_cockpit/` | ~8 | Same |
| `zero_dte/` + root `zero_dte_screener.py` | 6 | Dormant strategy sandbox (Feb 2026 mtimes) — archive |
| `short_swing/` + root `short_swing_screener.py` | 6 | Same |
| `bridge/` | 7 | Tastytrade placeholder (non-trading by design) — keep only `tastytrade_client.py` stub if referenced in docs; nothing imports the package |
| `ml_confidence_layer/` | 4 + models | Only referenced by `scripts/run_ml_on_vanguard_output.py` (itself unreferenced) — archive |
| `src/avshunter/` | 0 py | Empty scaffold — delete |
| `AVSHUNTER-Intelligence/` (nested dir) | reports only | Accidental nesting — merge/delete |

---

## 5. DEAD-CODE CANDIDATES (referenced by nothing, superseded by known decisions)

Highest-confidence removals (each cross-checked against the governance history):
- **`morning_validation.py` + `morning_validation_engine.py`** — the pre-morning_gate validators; nothing references them (the retired `morning_thesis_validator.py` itself now exists only as .bak copies). Their only child, `trigger_confirmation_engine.py`, dies with them.
- **Retired EDE/Kelly/enhancement stack**: `enhancement_integration.py` → `kelly_sizer.py`, `convergence_engine.py`, `regime_consensus.py`, `atheoretic_signals.py`, `signal_funnel.py`, `transition_matrix_consumer.py`; plus `execution_decision_engine.py`, `final_decision_engine.py`†, `trade_book_builder.py`† (†still imported by the EIL runner/orchestrator text — remove after deleting the commented phases). PSE retirement made all of this dead weight.
- **`catastrophe_gate.py`** — orchestrator phase 8b is a no-op stub; the 36KB engine is never imported.
- **`avshunter_exit_engine.py`** (superseded by `scripts/exit_rules_engine.py` + Exit Discipline), `catalyst_conflict_engine.py` (superseded by catalyst_truth_engine), `layer4_mispricing.py`, `layer6_path_survival.py`, `mae_mfe_calculator.py`, `liquidity_filter.py`, `theta_bpr_engine.py`, `vix_governor.py`, `rapid_rotation_flag.py`, `signal_grader.py` (scanner grades come via JSON, not import), `empirical_option_ev.py`, `confirmation_ingester.py`, `lab_recon_selftest.py`†(QA), `pipeline_interpreter/_append_*.py`, `_patch_cmd_ticker.py` (one-shot patch scripts), `pipeline_interpreter/alternative_contract_selector.py` + `direction_conflict_resolver.py` + `live_market_reader.py` + `prepare_interpreter_session.py` (all four explicitly retired by the MSI §25 command disposition), `scripts/generate_signal_lab.py` (pre-Lab), `scripts/ev_engine.py` (v1), `vanguard/ev_engine.py` + `vanguard/ev_engine_v2.py` (root ev_engine_v2 is the live one), `vanguard/layer2_statistical/scenario_builder.py` + entire `vanguard/layer3_execution/` (self-referencing only), `vanguard/schemas/vanguard_contract.py`, `vanguard/core/schema_guard.py`, `canonical_data/`… none dead except noted, `orchestrator/` per §4, `scripts/split_catalyst_from_macro_guards.py`, `scripts/audit_runner.py`, `scripts/write_manifest.py`, `scripts/validate_macro_contract.py`, `scripts/validate_packages.py` (superseded by data_contract_validator), `scripts/options_db_writer.py`+`compute_greeks_bs.py` (only phantom-audit children use them), `polygon_options_validation.py`, `tools/audit_from_packages.py`.

**~45 files in this bucket.** Every one should go through the quarantine protocol (§7), not straight deletion — external schedulers can't be seen statically.

### 5a. Retired launchers — and what they did that the manual commands don't

`run_evening.bat` / `run_premarket.bat` are confirmed no longer used (manual PowerShell commands replaced them) and can go to the attic with the rest. Before they go, note the two protections they carried:

1. **Interpreter pinning.** Both bats select `venv\Scripts\python.exe` and verify it imports pandas/pyarrow before launching. A bare `python` in PowerShell takes whatever is first on PATH — and the repo's `__pycache__` dirs contain **cpython-312, cpython-313 and cpython-314 bytecode side by side**, proving at least three interpreters have executed this code recently. That interacts with known findings (the `run_vanguard_from_packages.py` f-string that only some versions parse; version-dependent stdlib behaviour). **Recommendation:** keep launching manually if preferred, but pin the interpreter — either always invoke `venv\Scripts\python.exe` explicitly, or (better) replace both bats with one small `run.ps1` that pins the venv Python, sets the flags, and forwards arguments; delete the venv ambiguity by recording the blessed interpreter version in `run_meta.json` (already specified in AVS-SD-001) and having the orchestrator refuse a mismatched major.minor.
2. **CDS-2 flag validation.** The bats set and *validated* `AVSHUNTER_CANONICAL_DATA_ENABLED/WRITE_THROUGH/CDS2_OHLCV_MODE/HISTORICAL_PRICE_DB` fail-closed. The orchestrator's `main()` sets the same defaults itself (L6130-6141), so manual runs are covered **only when launched via `intelligent_orchestrator.py`'s CLI** — which also means stage gating defaults to ENFORCED. If any workflow is ever launched by importing `evening_workflow()`/`premarket_workflow()` programmatically instead, those defaults (and gating) are silently absent — one more reason to keep exactly one blessed launch path.

Also confirm the morning command in use: `python intelligent_orchestrator.py --morning` includes the mandatory `finalize_morning_handoff` (Phase 11 execution gate, Lab rebuild, Interpreter sync) and fails the workflow if it fails. Running `morning_gate.py` directly would **skip the handoff finalizer** — if the manual morning command is anything other than the orchestrator `--morning` path, that is a governance gap to close immediately.

---

## 6. RISKS FOUND BY THE GRAPH (fix regardless of scale-back)

1. **Duplicate modules both reachable in production.** `avshunter_monetisation_policy.py` exists at root (28.1KB, 27 Aug) *and* in `scripts/` (36.7KB, 27 Aug) — the orchestrator references the scripts copy, the EIL runner imports the root copy by bare name. Which one wins depends on `sys.path` order per process. Same hazard class: `WyckoffEngine_3101_v2.py` (root, current 44.6KB) vs `orchestrator/WyckoffEngine_3101_v2.py` (stale 32.6KB) vs `src copy`; `scenario_builder.py` ×3; `run_ml_on_vanguard_output.py` ×2; `refresh_daily_data` ×2; `intelligence-lab` has its own venv. **One name, one file** should be a repo rule enforced by a CI check.
2. **~95 backup copies live on the import path.** `.bak`/`old`/`dnu` files next to production modules (14 orchestrator variants, 12 morning_thesis_validator, 11 intelligence_lab, 10 interpreter, 7 lab_control, 6 eod_candidate_engine…). Some are importable (`pipeline_interpreter_engine2105old.py`, `intelligence_lab0505.py`, vanguard `*dnu*.py` are legal module names). This is how "archived module accidentally selected" happens.
3. **BOM (`utf-8-sig`) on 29 production files** including `morning_gate.py`, `pipeline_interpreter_engine.py`, `wyckoff_crabel_precor_logic_v2.py` — any tool that reads them as plain utf-8 (AST-based checks, some CI) fails on byte one. Already flagged in AVS-SD-001 v0.2; the inventory confirms the list.
4. **`scripts/run_vanguard_from_packages.py` line ~1416 has an f-string that Python ≥3.12 cannot parse** (`f-string: unmatched '('`). It runs today only because the production interpreter tolerates it (or the failure is being swallowed) — verify which Python each phase runs under and fix the line.
5. **Junk inside the repo**: 18 `pip-*` build dirs, 6 `tmp*`, 6 `avs_macro_check_*`, 13 `.codex_tmp_*` under tests, two venvs, `.env` **and** `.env.txt` (the plain-text copy of keys should be deleted and keys rotated), logs in `intelligence-lab/`. Combined with the atlas's GAP-007 (127 live files untracked by git), the tree cannot currently be reasoned about by tooling.

---

## 7. SCALE-BACK PLAN (safe, evidence-gated)

**Step 0 — freeze and commit.** Commit the working tree; tag `pre-scaleback-20260901`. Nothing moves without this.

**Step 1 — mechanical cleanup (no behaviour change, one evening+morning cycle to validate):**
delete pip-*/tmp*/avs_macro_check_*/.codex* dirs and `.env.txt` (rotate keys); move every `*.bak`, `*old*`, `*dnu*`, dated-variant file into `_attic/20260901/` preserving relative paths; move `Archive/`, `legacy/`, `decommissioned/`, `datadnuold2405/`, `_cleanup_holding/` under `_attic/`; `.gitignore` the attic, venvs, data outputs.

**Step 2 — quarantine the §5 dead list + §4 subsystems you confirm are unused:** move (never delete) to `_quarantine/20260901/`, keeping relative paths. Run two full accepted production cycles (evening → morning → Lab → Interpreter) plus the pytest suite. Any `ModuleNotFoundError`/missing-script error names the file to restore — restore it and record *what* references it (that reference is a finding, since the graph didn't see it). After two clean cycles + one quiet week, the quarantine goes to the attic.

**Step 3 — resolve the duplicates (§6.1):** pick the canonical copy of each duplicated module, delete the shadow, and add a CI guard (a 20-line script failing on duplicate basenames across import roots — I can supply it).

**Step 4 — restructure the survivors** (aligns with AVS-SD-001 rather than competing with it):
```
avshunter/
  core/          canonical_data, contracts, market_structure, session/identity
  engines/       wyckoff (ONE engine), vanguard, options_intelligence, garch, wbs, trigger, ev3
  pipeline/      orchestrator, discovery, eod_candidate_engine, morning_gate, handoff
  apps/          intelligence_lab, pipeline_interpreter
  ops/           all §3 manual tooling, grouped by domain
  tests/
```
Everything imports through packages, no `sys.path` hacks, one name → one module, BOMs stripped, whole tree tracked by git.

**Step 5 — the deeper scale-back** is not file deletion but engine consolidation, and it should follow the AVS-SD-001 workstreams already agreed: one Wyckoff engine instead of two, one direction record instead of eleven writers, EIL either fixed to score real data or demoted to advisory display, and the retired stacks (EDE/Kelly/PSE remnants, catastrophe stub) formally excised from the orchestrator text. The functional reference (AVS-REV-002) is the map for that.

---

## Appendix — machine-readable classification
The full per-file classification with referrer lists is in `usage_graph.json` (delivered alongside): category per file (`PROD_SHARED` / `PROD_EVENING` / `PROD_MORNING` / `PROD_LAB` / `PROD_INTERPRETER` / `TEST_QA` / `REFERENCED_NONPROD` / `LAUNCHER_TARGET` / `UNREFERENCED`), who references it, and edge counts — use it as the checklist for Steps 1–3.
