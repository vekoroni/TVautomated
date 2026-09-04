# 04 — Appendix: STANDALONE_CLI, ORPHAN and RETIRED files

**Document:** AVS-E2E-CODE-001 · Step 2 appendix

Files here are **not reachable** from `intelligent_orchestrator.py` (by import or by subprocess), from the Morning path, from the Intelligence Lab, or from the Pipeline Interpreter. Each gets a one-paragraph entry per the task specification. Classification is from `01_inventory.csv`; reachability is from `02_import_graph.json`.

- **STANDALONE_CLI** — has an entry point (`__main__`, argparse, or a web app) but no orchestrated path reaches it.
- **ORPHAN** — no entry point and never imported by anything in the live tree.
- **RETIRED (hint)** — the filename or module docstring contains a retirement marker (retired/deprecated/DNU/obsolete/superseded/legacy). This is a *lexical* signal recorded as INFERRED-MEDIUM, not a verified decommissioning.

**Total appendix files: 298** (STANDALONE_CLI 163, ORPHAN 135).

> An ORPHAN that is nonetheless imported by a *test* is noted; tests are outside the production inventory, so such a file remains ORPHAN for pipeline purposes.

**Files carrying a lexical retirement marker: 13.** Listed inline below with the `RETIRED(hint)` tag.

## <repo root>

**`actuarial_hash_diagnostic.py`** — [STANDALONE_CLI] 302 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. actuarial_hash_diagnostic.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`actuarial_live_updater.py`** — [ORPHAN] 127 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`add_state_hash.py`** — [ORPHAN] 134 lines, last commit `5d886f0` (2026-08-20). Entry points: none. add_state_hash.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit_latest_run.py`** — [ORPHAN] 133 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`avshunter_db_update.py`** — [STANDALONE_CLI] 856 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. avshunter_db_update.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`avshunter_exit_engine.py`** — [STANDALONE_CLI] 613 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER Exit Discipline Engine — Sprint 1 Never imported in the live tree. [OBSERVED — inventory + import graph]

**`avshunter_ticker_probe.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 1907 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. AVSHUNTER — Ticker Probe Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bond_macro_intelligence.py`** — [STANDALONE_CLI] 1253 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. bond_macro_intelligence.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bond_macro_intelligenceold0908.py`** — [STANDALONE_CLI] 953 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. bond_macro_intelligence.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`build_macro_jsonold0908.py`** — [STANDALONE_CLI] 1427 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — Automated Macro JSON Builder Never imported in the live tree. [OBSERVED — inventory + import graph]

**`catalyst_conflict_engine.py`** — [ORPHAN] 335 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER Catalyst Conflict Engine — Phantom 3 promoted to production. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`catastrophe_gate.py`** — [STANDALONE_CLI] 729 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. ╔══════════════════════════════════════════════════════════════════════════════╗ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`check7_prompt.py`** — [ORPHAN] 39 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`confirmation_ingester.py`** — [STANDALONE_CLI] 198 lines, last commit `47d402d` (2026-06-20). Entry points: __main__;argparse-CLI. Sprint 4 — Confirmation Ingester Never imported in the live tree. [OBSERVED — inventory + import graph]

**`desk_card.py`** — [STANDALONE_CLI] 952 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER Desk Card — read-only pre-execution decision aid. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`enhancement_integration.py`** — [STANDALONE_CLI] 762 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. ╔══════════════════════════════════════════════════════════════════════════════╗ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`final_verify_c9.py`** — [ORPHAN] 174 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`lab_recon_selftest.py`** — [ORPHAN] 147 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`layer4_mispricing.py`** — [ORPHAN] 355 lines, last commit `5d886f0` (2026-08-20). Entry points: none. layer4_mispricing.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`layer6_path_survival.py`** — [ORPHAN] 275 lines, last commit `5d886f0` (2026-08-20). Entry points: none. layer6_path_survival.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`liquidity_filter.py`** — [STANDALONE_CLI] 347 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER — Options Think Tank: M3 Liquidity Filter Never imported in the live tree. [OBSERVED — inventory + import graph]

**`macro_sector_propagation_test.py`** — [ORPHAN] 151 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`mae_mfe_calculator.py`** — [ORPHAN] 203 lines, last commit `5d886f0` (2026-08-20). Entry points: none. mae_mfe_calculator.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`md_api_diagnostic.py`** — [ORPHAN · UNTRACKED-BY-GIT] 58 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`morning_validation.py`** — [STANDALONE_CLI] 1233 lines, last commit `a3cded6` (2026-05-23). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`morning_validation_engine.py`** — [STANDALONE_CLI] 1535 lines, last commit `a3cded6` (2026-05-23). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`polygon_options_validation.py`** — [ORPHAN] 120 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`rapid_rotation_flag.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 323 lines, last commit `UNTRACKED`. Entry points: __main__. AVSHUNTER — Rapid Rotation Flag (RRF) v2.0 Never imported in the live tree. [OBSERVED — inventory + import graph]

**`refresh_daily_data.py`** — [STANDALONE_CLI] 320 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. 15-MINUTE DATA REFRESH SCRIPT (Manual) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`regime_audit.py`** — [ORPHAN] 93 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`resume_after_vanguard.py`** — [STANDALONE_CLI] 157 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER manual resume runner. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`run.py`** — [STANDALONE_CLI] 284 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER run.py v4 — Production Governance Wrapper (stabilised) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`sec_activist_monitor.py`** — [STANDALONE_CLI] 370 lines, last commit `0340705` (2026-06-27). Entry points: __main__;argparse-CLI. sec_activist_monitor.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`sec_form4_monitor.py`** — [STANDALONE_CLI] 467 lines, last commit `df65e33` (2026-06-28). Entry points: __main__;argparse-CLI. sec_form4_monitor.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`section11_tests.py`** — [ORPHAN] 437 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Section 11 — Component 9 full test checklist. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`section11_tests_v2.py`** — [ORPHAN] 367 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Section 11 — Component 9 full test checklist v2. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`signal_grader.py`** — [STANDALONE_CLI] 416 lines, last commit `49de227` (2026-06-28). Entry points: __main__;argparse-CLI. signal_grader.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step10_test.py`** — [ORPHAN] 78 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step4_test.py`** — [ORPHAN] 84 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step5_graceful_test.py`** — [ORPHAN] 69 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Graceful-degradation test for Step 5. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step6_test.py`** — [ORPHAN] 209 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 6 test: lab context injection in cmd_ticker(). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step6_test_v2.py`** — [ORPHAN] 138 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 6 test v2 — forces no-chart path so build_single_ticker_prompt is used. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step6_test_v3.py`** — [ORPHAN] 136 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 6 test v3 — patches on _cmd namespace (where cmd_ticker resolves names). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step7_test.py`** — [ORPHAN] 75 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 7 tests — cmd_lab() with and without lab file. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step7_test_v2.py`** — [ORPHAN] 103 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 7 tests v2 — handles file-present and file-absent scenarios. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step8_test.py`** — [ORPHAN] 115 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Step 8 test — LAB_ALIGNMENT card and LAB STATUS column in triage HTML. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`step9_verify.py`** — [ORPHAN] 75 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`test_macro_redesign.py`** — [STANDALONE_CLI] 356 lines, last commit `68437a2` (2026-05-22). Entry points: __main__. AVSHUNTER Macro Redesign — Test Suite Never imported in the live tree. [OBSERVED — inventory + import graph]

**`test_pipeline_regression.py`** — [ORPHAN] 641 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER — Pipeline Regression Test Suite Never imported in the live tree. [OBSERVED — inventory + import graph]

**`theta_bpr_engine.py`** — [STANDALONE_CLI] 368 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER — Options Think Tank: M6 Theta / BPR Engine Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vix_governor.py`** — [STANDALONE_CLI] 381 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER — Options Think Tank: M4 VIX Governor Never imported in the live tree. [OBSERVED — inventory + import graph]


## audit\olm_fix_test

**`audit/olm_fix_test/agentB_mixed_direction.py`** — [ORPHAN · UNTRACKED-BY-GIT] 29 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentB_ordering_single.py`** — [ORPHAN · UNTRACKED-BY-GIT] 60 lines, last commit `UNTRACKED`. Entry points: none. Run the ordering fixture against ONE module (argv[1]: 'current' or 'backup'). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentB_selector_tests.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 209 lines, last commit `UNTRACKED`. Entry points: __main__. Agent B (OLM fix validation) - additional §11.3 / §8.2 / §8.3 / §8.1 checks Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentB_tc08_exact_replay.py`** — [ORPHAN · UNTRACKED-BY-GIT] 73 lines, last commit `UNTRACKED`. Entry points: none. Agent B (OLM fix validation) - exact TC-08 replay, before vs after. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentB_tc08_single.py`** — [ORPHAN · UNTRACKED-BY-GIT] 62 lines, last commit `UNTRACKED`. Entry points: none. Run the exact TC-08 fixture against ONE module (passed as argv[1]: 'current' or 'backup'). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentC_baseline_replay.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 155 lines, last commit `UNTRACKED`. Entry points: __main__. Agent C - SS11.1 frozen-baseline differential replay. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentC_cross_stage_tests.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 445 lines, last commit `UNTRACKED`. Entry points: __main__. Agent C - OLM remediation cross-stage integration tests (design SS11.4). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agentE_diagnostics_retest.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 138 lines, last commit `UNTRACKED`. Entry points: __main__. Agent E (OLM increment retest) - design SS8.3 observability diagnostics. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`audit/olm_fix_test/agent_a_runner.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 401 lines, last commit `UNTRACKED`. Entry points: __main__. Agent A OLM fix validation runner. Never imported in the live tree. [OBSERVED — inventory + import graph]


## audit\olm_test

**`audit/olm_test/_agent2_tc_runner.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 760 lines, last commit `UNTRACKED`. Entry points: __main__. OLM validation test runner - Agent 2. Never imported in the live tree. [OBSERVED — inventory + import graph]


## bridge

**`bridge/__init__.py`** — [ORPHAN] 7 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Isolated AVSHUNTER feedback bridge package. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bridge/feedback_writer.py`** — [ORPHAN] 41 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bridge/order_manager.py`** — [ORPHAN] 20 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bridge/outcome_recorder.py`** — [ORPHAN] 47 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bridge/scheduler.py`** — [ORPHAN] 16 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`bridge/tastytrade_client.py`** — [ORPHAN] 49 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## data\scratch\ev3_reconstruction

**`data/scratch/ev3_reconstruction/stage_3_2_orchestrator_block_unittest.py`** — [ORPHAN · UNTRACKED-BY-GIT] 123 lines, last commit `UNTRACKED`. Entry points: none. Stage 3.2 unit-level exercise of the added orchestrator block. Never imported in the live tree. [OBSERVED — inventory + import graph]


## intelligence-lab

**`intelligence-lab/intelligence_lab0505.py`** — [STANDALONE_CLI] 1201 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;web-app. ╔══════════════════════════════════════════════════════════════════════════════╗ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`intelligence-lab/intelligence_labold.py`** — [STANDALONE_CLI] 1132 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;web-app. ╔══════════════════════════════════════════════════════════════════════════════╗ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`intelligence-lab/intelligence_labolddnu0605am.py`** — [STANDALONE_CLI · RETIRED(hint)] 1140 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;web-app. ╔══════════════════════════════════════════════════════════════════════════════╗ Never imported in the live tree. [OBSERVED — inventory + import graph]


## ma_cockpit

**`ma_cockpit/ma_cockpit.py`** — [STANDALONE_CLI] 51 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER M&A Cockpit v1.0 — Interactive Entry Point Never imported in the live tree. [OBSERVED — inventory + import graph]

**`ma_cockpit/ma_cockpit_scheduler.py`** — [STANDALONE_CLI] 34 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER M&A Cockpit v1.0 — Scheduled Runner Never imported in the live tree. [OBSERVED — inventory + import graph]

**`ma_cockpit/validate_ma_csv.py`** — [STANDALONE_CLI] 31 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## ml_confidence_layer

**`ml_confidence_layer/__init__.py`** — [ORPHAN] 18 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER ML Confidence Layer Never imported in the live tree. [OBSERVED — inventory + import graph]

**`ml_confidence_layer/compounding_tracker.py`** — [STANDALONE_CLI] 380 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER $200 Compounding Tracker Never imported in the live tree. [OBSERVED — inventory + import graph]

**`ml_confidence_layer/run_ml_on_vanguard_output.py`** — [STANDALONE_CLI] 464 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER ML Bridge — run_ml_on_vanguard_output.py Never imported in the live tree. [OBSERVED — inventory + import graph]


## news_terminal

**`news_terminal/build_premarket_candidates.py`** — [STANDALONE_CLI] 147 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. build_premarket_candidates.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`news_terminal/news_terminal.py`** — [STANDALONE_CLI] 62 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER News Terminal v1.3 — Interactive Entry Point Never imported in the live tree. [OBSERVED — inventory + import graph]

**`news_terminal/news_terminal_scheduler.py`** — [STANDALONE_CLI] 59 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER News Terminal v1.3 — Scheduled Runner Never imported in the live tree. [OBSERVED — inventory + import graph]


## orchestrator

**`orchestrator/WyckoffEngine_3101_v2.py`** — [ORPHAN] 878 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER WyckoffEngine_3101 v2.0 - FORCED OUTPUT ARCHITECTURE Never imported in the live tree. [OBSERVED — inventory + import graph]

**`orchestrator/__init__.py`** — [ORPHAN] 18 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER Master Orchestrator Never imported in the live tree. [OBSERVED — inventory + import graph]

**`orchestrator/main_archive.py`** — [ORPHAN] 148 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## scripts

**`scripts/audit_runner.py`** — [STANDALONE_CLI] 119 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/backfill_polygon_daily_v7.py`** — [STANDALONE_CLI] 163 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Persist adjusted Polygon daily OHLCV for the controlled actuarial v7 rebuild. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/behaviour_cache_builder.py`** — [STANDALONE_CLI] 447 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Build the AVSHUNTER behaviour-state cache. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/build_actuarial_v7_sharded.py`** — [STANDALONE_CLI] 173 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Resumable sharded actuarial v7 build followed by atomic consolidation. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/build_ev3_stage0.py`** — [STANDALONE_CLI] 283 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Build EV3 Stage EV-0 barrier sidecar and candidate diagnostics. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/build_phase_transition_matrixanother dnu2005.py`** — [STANDALONE_CLI · RETIRED(hint)] 412 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/build_phase_transition_matrixdnumalomo2005.py`** — [STANDALONE_CLI · RETIRED(hint)] 406 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/capture_end_to_end_run.py`** — [STANDALONE_CLI] 598 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Capture an AVSHUNTER run end to end without changing trading outputs. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/derive_actuarial_v7_universe.py`** — [STANDALONE_CLI] 50 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Derive the governed v7 rebuild universe without losing historical-only names. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/diag_options.py`** — [ORPHAN] 77 lines, last commit `81b0d52` (2026-08-05). Entry points: none. Quick diagnostic — tests chain fetch and contract selection for AMD and AMZN. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/enrich_actuarial_v7_diagnostics.py`** — [STANDALONE_CLI] 95 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Atomically add deterministic v6-compatible diagnostics to v7 ticker shards. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/ev_engine.py`** — [STANDALONE_CLI] 417 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. AVSHUNTER — EV Engine v2 (Patched v2.2.0) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/generate_signal_lab.py`** — [STANDALONE_CLI] 600 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. generate_signal_lab.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/patch_actuarial_winsorise.py`** — [ORPHAN] 54 lines, last commit `81b0d52` (2026-08-05). Entry points: none. AVSHUNTER — Patch: Winsorise Extreme Returns in Actuarial Database Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_compute_historical_greeks.py`** — [STANDALONE_CLI] 362 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Compute missing PHANTOM historical option Greeks from local MarketData EOD rows. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_computed_greeks_audit.py`** — [STANDALONE_CLI] 149 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Audit PHANTOM historical computed-Greek coverage. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_greek_coverage_audit.py`** — [STANDALONE_CLI] 147 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Audit PHANTOM Greek coverage and Greek rehydration status. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_greek_rehydrate.py`** — [STANDALONE_CLI] 636 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Rehydrate PHANTOM historical option-chain Greeks from MarketData. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_marketdata_chain_probe.py`** — [STANDALONE_CLI] 129 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Probe MarketData option-chain response shape for PHANTOM Greek extraction. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_marketdata_quote_greek_rehydrate.py`** — [STANDALONE_CLI] 486 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Repair PHANTOM Greeks from MarketData option quote endpoint. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/phantom_marketdata_quote_probe.py`** — [STANDALONE_CLI] 111 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Probe MarketData option quote endpoint for vendor Greeks. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/promote_actuarial_v7.py`** — [STANDALONE_CLI] 64 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Controlled, fail-closed promotion of validated actuarial v7 staging data. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/publish_latest_run.py`** — [STANDALONE_CLI] 156 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. publish_latest_run.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_baton_integrity.py`** — [STANDALONE_CLI] 279 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. End-to-end baton integrity QA for the latest AVSHUNTER run. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_conflict_resolver.py`** — [STANDALONE_CLI] 111 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. QA gate for the Intelligence Lab tradeability resolver. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_live_uat_readiness.py`** — [STANDALONE_CLI] 324 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. Generate the AVSHUNTER Live UAT readiness report. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_macro_enrichment_injection.py`** — [STANDALONE_CLI] 223 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. QA probe for macro enrichment package injection. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_market_scenario_simulation.py`** — [STANDALONE_CLI] 1009 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Stress-test a completed AVSHUNTER run with simulated live market scenarios. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_morning_validator.py`** — [STANDALONE_CLI] 215 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. QA gate for the Morning Thesis Validator. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/qa_uat_regression_backtest.py`** — [STANDALONE_CLI] 120 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Regression backtest for the latest AVSHUNTER UAT run artifacts. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/repair_daily_from_polygon.py`** — [STANDALONE_CLI] 222 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/run_ml_on_vanguard_output.py`** — [STANDALONE_CLI] 218 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. AVSHUNTER ML Bridge — run_ml_on_vanguard_output.py Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/run_phantom_backfill.py`** — [STANDALONE_CLI] 283 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. PHANTOM five-year MarketData.app historical options backfill. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/run_phantom_backfill_parallel.py`** — [STANDALONE_CLI] 551 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. PHANTOM parallel MarketData.app historical options backfill. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/smoke_test_big_bang_phase_6_7.py`** — [STANDALONE_CLI] 122 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Smoke test for Big Bang Phase 6/7 Intelligence Lab wiring. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/smoke_test_live_uat_pipeline.py`** — [STANDALONE_CLI] 241 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Live UAT API smoke test for the Intelligence Lab. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/smoke_test_morning_validator.py`** — [STANDALONE_CLI] 100 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. Smoke test for Morning Thesis Validator. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/split_catalyst_from_macro_guards.py`** — [STANDALONE_CLI] 107 lines, last commit `68437a2` (2026-05-22). Entry points: __main__. Split catalyst_calendar_latest.csv into: Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/start_end_to_end_run_capture.py`** — [STANDALONE_CLI] 95 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Start the AVSHUNTER end-to-end run capture as a detached process. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/start_go_live_uat_audit_watch.py`** — [STANDALONE_CLI] 86 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Start the go-live UAT audit watcher as a detached Windows process. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/upgrade_actuarial_database.py`** — [STANDALONE_CLI] 189 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__. AVSHUNTER — Upgrade Actuarial Database: Add Multi-Horizon Outcome Columns Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/validate_actuarial_v7.py`** — [STANDALONE_CLI] 121 lines, last commit `dfc5a8d` (2026-08-05). Entry points: __main__;argparse-CLI. Fail-closed validation gate for a staged actuarial v7 parquet. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/validate_behaviour_state.py`** — [STANDALONE_CLI] 44 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Validate AVSHUNTER behaviour-state split against a Vanguard CSV. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/validate_macro_contract.py`** — [STANDALONE_CLI] 80 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. Validate macro snapshot contract (snake_case, aligned to manual macro_intelligence template). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/validate_packages.py`** — [STANDALONE_CLI] 62 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/verify_ev3_stage0.py`** — [STANDALONE_CLI] 132 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Independently verify an EV3 Stage EV-0 barrier sidecar. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`scripts/write_manifest.py`** — [STANDALONE_CLI] 30 lines, last commit `81b0d52` (2026-08-05). Entry points: __main__;argparse-CLI. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## short_swing

**`short_swing/run_short_swing.py`** — [STANDALONE_CLI] 210 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — SHORT-SWING MASTER RUNNER v1.0 Never imported in the live tree. [OBSERVED — inventory + import graph]

**`short_swing/short_swing_screener.py`** — [STANDALONE_CLI] 457 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — SHORT-SWING SCREENER v1.0 Never imported in the live tree. [OBSERVED — inventory + import graph]


## tests

**`tests/lab_qa_audit.py`** — [STANDALONE_CLI] 826 lines, last commit `bd534ea` (2026-08-01). Entry points: __main__;argparse-CLI. lab_qa_audit.py — Quant QA audit for AVSHUNTER Intelligence Lab exports. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_actuarial_cache_v7_contract.py`** — [STANDALONE_CLI] 139 lines, last commit `35475f7` (2026-08-05). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_actuarial_v7_cutover_paths.py`** — [STANDALONE_CLI] 85 lines, last commit `35475f7` (2026-08-05). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_actuarial_v7_database_contract.py`** — [ORPHAN] 152 lines, last commit `35475f7` (2026-08-05). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_audit_remediation_guards.py`** — [STANDALONE_CLI] 85 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_big_bang_phase_6_7.py`** — [STANDALONE_CLI] 235 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_bond_macro_contract.py`** — [ORPHAN] 79 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_build_macro_json_market_data.py`** — [ORPHAN] 127 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_canonical_data_system.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 625 lines, last commit `UNTRACKED`. Entry points: __main__. CDS-1 contract, lifecycle, registry, ledger, and storage regression tests. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_cds2_historical_prices.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 450 lines, last commit `UNTRACKED`. Entry points: __main__. Regression tests for CDS-2 historical price write-through behavior. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_cds4_option_chain_store.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 257 lines, last commit `UNTRACKED`. Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_direction_governance_contract.py`** — [ORPHAN · UNTRACKED-BY-GIT] 313 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_directional_bias_fixes.py`** — [STANDALONE_CLI] 478 lines, last commit `32145ed` (2026-05-20). Entry points: __main__. Tests for four directional-bias fixes: Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_empirical_option_ev.py`** — [ORPHAN] 198 lines, last commit `a6cfda6` (2026-08-02). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_eod_options_research_handoff.py`** — [STANDALONE_CLI] 138 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_authority.py`** — [ORPHAN · UNTRACKED-BY-GIT] 104 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_cache_promotion.py`** — [ORPHAN · UNTRACKED-BY-GIT] 49 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_calibration_report.py`** — [ORPHAN · UNTRACKED-BY-GIT] 62 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_monetisation_authority.py`** — [ORPHAN · UNTRACKED-BY-GIT] 54 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_options_handoff.py`** — [ORPHAN] 836 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_orchestrator_order.py`** — [ORPHAN · UNTRACKED-BY-GIT] 68 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_shadow_phase.py`** — [ORPHAN] 170 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_ev3_stage0.py`** — [ORPHAN] 237 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_execution_monetisability_gate.py`** — [ORPHAN · UNTRACKED-BY-GIT] 65 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_external_intel_review_lane.py`** — [STANDALONE_CLI] 146 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_garch_regime_fix.py`** — [STANDALONE_CLI] 121 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. Tests for garch_runner._load_regime fix: Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_handoff_conflict_guard.py`** — [ORPHAN · UNTRACKED-BY-GIT] 77 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_handoff_contract.py`** — [STANDALONE_CLI] 211 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_handoff_contract_audit.py`** — [STANDALONE_CLI] 173 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_intelligence_lab_strict_json.py`** — [ORPHAN · UNTRACKED-BY-GIT] 53 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_interpreter_macro_advisory_handoff.py`** — [ORPHAN · UNTRACKED-BY-GIT] 219 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_cache_signature.py`** — [ORPHAN] 122 lines, last commit `7624e51` (2026-08-01). Entry points: none. FIX-CACHE — _lab_cache_signature() must invalidate on changes to the primary Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_export_mapper_js.py`** — [ORPHAN] 39 lines, last commit `db96304` (2026-08-01). Entry points: none. Runs the real Intelligence Lab export-mapper JS tests (tests/js/) as part of Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_governed_handoff.py`** — [ORPHAN · UNTRACKED-BY-GIT] 505 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_journal_handoff.py`** — [ORPHAN] 291 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_monetisation_gate.py`** — [ORPHAN] 213 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_qa_audit_harness.py`** — [ORPHAN] 60 lines, last commit `bd534ea` (2026-08-01). Entry points: none. tests/lab_qa_audit.py is the sprint's acceptance harness (BASELINE.md / Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_ranking_basis_export.py`** — [ORPHAN] 79 lines, last commit `f34a10c` (2026-08-02). Entry points: none. FIX-7 exit criterion: exporting lab_action_bucket_label must not change what Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_lab_strangle_direction.py`** — [ORPHAN] 248 lines, last commit `9a2c197` (2026-08-02). Entry points: none. FIX-5 — the Lab must not collapse a non-directional STRANGLE setup into a Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_level1_20260512_regressions.py`** — [ORPHAN] 86 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_long_option_policy.py`** — [ORPHAN · UNTRACKED-BY-GIT] 32 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_low_risk_pipeline_repairs.py`** — [ORPHAN · UNTRACKED-BY-GIT] 158 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_macro_enrichment_delta.py`** — [STANDALONE_CLI] 328 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_macro_enrichment_discovery_options.py`** — [STANDALONE_CLI] 57 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_macro_layer_fixes.py`** — [STANDALONE_CLI] 232 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. Tests for macro-layer fixes: Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_macro_quant_packet.py`** — [STANDALONE_CLI] 267 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_manual_ticker_upload.py`** — [STANDALONE_CLI] 90 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_market_physics.py`** — [STANDALONE_CLI] 148 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_morning_gate_authority.py`** — [ORPHAN · UNTRACKED-BY-GIT] 423 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_morning_gate_bond_freshness.py`** — [ORPHAN · UNTRACKED-BY-GIT] 38 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_morning_gate_contract_repair.py`** — [ORPHAN] 324 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_morning_handoff_finalizer.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 311 lines, last commit `UNTRACKED`. Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_morning_thesis_validator.py`** — [STANDALONE_CLI] 291 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_agent1_data_foundation.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 171 lines, last commit `UNTRACKED`. Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_handoff_materializer.py`** — [ORPHAN · UNTRACKED-BY-GIT] 212 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_identity_preflight.py`** — [ORPHAN · UNTRACKED-BY-GIT] 73 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_interpreter_handoff.py`** — [ORPHAN · UNTRACKED-BY-GIT] 301 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_market_structure_identity.py`** — [ORPHAN · UNTRACKED-BY-GIT] 73 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_morning_capture.py`** — [ORPHAN · UNTRACKED-BY-GIT] 91 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_options_chain_v2_integration.py`** — [ORPHAN · UNTRACKED-BY-GIT] 80 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_orchestrator_run_meta.py`** — [ORPHAN · UNTRACKED-BY-GIT] 47 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_production_readiness.py`** — [ORPHAN · UNTRACKED-BY-GIT] 58 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_provider_fixtures.py`** — [ORPHAN · UNTRACKED-BY-GIT] 36 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_quote_and_size_lineage.py`** — [ORPHAN · UNTRACKED-BY-GIT] 157 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_runtime.py`** — [ORPHAN · UNTRACKED-BY-GIT] 43 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_msi_stage_worklist.py`** — [ORPHAN · UNTRACKED-BY-GIT] 99 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_normalise_macro_contract_scores.py`** — [ORPHAN] 50 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_olm_execution_authority.py`** — [ORPHAN · UNTRACKED-BY-GIT] 260 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_option_liquidity_lifecycle.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 616 lines, last commit `UNTRACKED`. Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_options_crossed_quote_integration.py`** — [ORPHAN · UNTRACKED-BY-GIT] 242 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_options_greek_backfill_unit.py`** — [ORPHAN · UNTRACKED-BY-GIT] 108 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_options_liquidity_lifecycle.py`** — [ORPHAN · UNTRACKED-BY-GIT] 328 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_options_liquidity_morning_lab.py`** — [ORPHAN · UNTRACKED-BY-GIT] 263 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_options_research_contract.py`** — [ORPHAN] 252 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_phantom_weekly_maintenance.py`** — [STANDALONE_CLI] 51 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2.py`** — [STANDALONE_CLI] 169 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_adapter.py`** — [STANDALONE_CLI] 237 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_e2e_orchestrator.py`** — [STANDALONE_CLI] 102 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_evidence_package.py`** — [STANDALONE_CLI] 87 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_lab_batch.py`** — [STANDALONE_CLI] 111 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_lab_structured.py`** — [STANDALONE_CLI] 64 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_package_publisher.py`** — [STANDALONE_CLI] 102 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_package_shadow.py`** — [STANDALONE_CLI] 66 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_phase3.py`** — [STANDALONE_CLI] 274 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_phase4.py`** — [STANDALONE_CLI] 227 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_phase5.py`** — [STANDALONE_CLI] 202 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_production_deploy.py`** — [STANDALONE_CLI] 63 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_automation_v2_report.py`** — [STANDALONE_CLI] 81 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1.py`** — [STANDALONE_CLI] 110 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_attended_workflow.py`** — [STANDALONE_CLI] 80 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_batch.py`** — [STANDALONE_CLI] 97 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_crop.py`** — [STANDALONE_CLI] 26 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_dpi.py`** — [STANDALONE_CLI] 22 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_market_screen.py`** — [STANDALONE_CLI] 110 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_noii_cross.py`** — [ORPHAN] 58 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_ticker.py`** — [STANDALONE_CLI] 89 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_ticker_batch.py`** — [STANDALONE_CLI] 93 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_capture_v1_ticker_market_screen.py`** — [STANDALONE_CLI] 171 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_lab_authority.py`** — [ORPHAN] 67 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pipeline_interpreter_trusted_source.py`** — [ORPHAN] 107 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pre_evening_production_repairs.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 252 lines, last commit `UNTRACKED`. Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_production_readiness_guardrails.py`** — [ORPHAN · UNTRACKED-BY-GIT] 105 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_pse_retired_authority.py`** — [ORPHAN · RETIRED(hint)] 174 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_selected_contract_economics.py`** — [ORPHAN · UNTRACKED-BY-GIT] 274 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_trigger_layer_governance.py`** — [ORPHAN · UNTRACKED-BY-GIT] 75 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_vanguard_production_fixes.py`** — [ORPHAN] 223 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_wall_break_missing_pcr.py`** — [ORPHAN · UNTRACKED-BY-GIT] 35 lines, last commit `UNTRACKED`. Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/test_wyckoff_phase_validator.py`** — [ORPHAN] 144 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## tests\msi

**`tests/msi/test_computation.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 820 lines, last commit `UNTRACKED`. Entry points: __main__. MSI v1.1 independent computation tests (design doc §8.2, §8.4, §8.6, §8.8, §10.1, Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/msi/test_flow.py`** — [ORPHAN · UNTRACKED-BY-GIT] 1282 lines, last commit `UNTRACKED`. Entry points: none. MSI v1.1 independent flow/integration tests (design table §9, §9.4, §12.2, §16.2, §18). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/msi/test_functionality.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 1326 lines, last commit `UNTRACKED`. Entry points: __main__. MSI v1.1 independent FUNCTIONALITY tests (design doc §3.2, §8, §18, §23, §24 — unit level). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/msi/test_logic.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 1422 lines, last commit `UNTRACKED`. Entry points: __main__. Independent verification of MSI v1.1 logic/state-machine requirements. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/msi/test_regression.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 907 lines, last commit `UNTRACKED`. Entry points: __main__. MSI v1.1 independent regression pack (R-01..R-09). Never imported in the live tree. [OBSERVED — inventory + import graph]


## tests\qa

**`tests/qa/test_numeric_fail_closed.py`** — [STANDALONE_CLI] 42 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/qa/test_p1_p10_adversarial_probes.py`** — [STANDALONE_CLI] 326 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. QA adversarial probes P1-P3, P5-P10 (P4 lives in test_p4_nan_rr_bypass.py). Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/qa/test_p4_nan_rr_bypass.py`** — [STANDALONE_CLI] 156 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. QA adversarial probe P4 — NaN R:R sovereign-veto bypass. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tests/qa/test_s9_live_provider_permission_promotion.py`** — [STANDALONE_CLI] 114 lines, last commit `d4b2a45` (2026-08-04). Entry points: __main__. QA extension to Phase 2, sovereign control S9, scoped to live_provider.py. Never imported in the live tree. [OBSERVED — inventory + import graph]


## tests\rca

**`tests/rca/test_morning_gate_terminal_thesis_ordering.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 169 lines, last commit `UNTRACKED`. Entry points: __main__. RCA reproduction for audit/rca/terminal_thesis/findings.md. Never imported in the live tree. [OBSERVED — inventory + import graph]


## tools

**`tools/audit_from_packages.py`** — [STANDALONE_CLI] 216 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER Data Integrity Audit (Package-First) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/cds2_import_historical_prices.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 251 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. Offline CDS-2 importer for package and data/daily OHLCV histories. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/cds2_replay_lifecycle_shadow.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 216 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. Reconcile reference-run stage membership through the CDS lifecycle offline. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/cds2_validate_historical_prices.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 205 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. Validate and reconcile the CDS-2 historical-price database offline. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/create_cds_baseline.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 152 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. Create a hash-verified, non-secret CDS implementation baseline. Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/enrich_universe_sector_polygon.py`** — [STANDALONE_CLI] 106 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Universe Sector Enrichment (Polygon) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/refresh_daily_data_v2.py`** — [STANDALONE_CLI] 430 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — Daily Data Refresh v2 (Universe-aligned, non-interactive, audited) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/sanitize_universe.py`** — [STANDALONE_CLI] 122 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Universe Sanitation v2 (schema-preserving) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/sanitize_universeold.py`** — [STANDALONE_CLI] 106 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. Universe Sanitation Utility Never imported in the live tree. [OBSERVED — inventory + import graph]

**`tools/validate_canonical_data.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 49 lines, last commit `UNTRACKED`. Entry points: __main__;argparse-CLI. Initialise or validate a CDS control-plane registry explicitly. Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard

**`vanguard/ev_engine.py`** — [STANDALONE_CLI] 314 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER — EV Engine v2 (Patched v2.1.0) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/ev_engine_v2.py`** — [STANDALONE_CLI] 314 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__. AVSHUNTER — EV Engine v2 (Patched v2.1.0) Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\core

**`vanguard/core/schema_guard.py`** — [ORPHAN] 167 lines, last commit `46c002f` (2026-08-05). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\data

**`vanguard/data/polygon_fetcher.py`** — [STANDALONE_CLI · UNTRACKED-BY-GIT] 260 lines, last commit `UNTRACKED`. Entry points: __main__. Polygon Data Fetcher for VANGUARD Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\execution

**`vanguard/execution/__init__.py`** — [ORPHAN] 1 lines, last commit `46c002f` (2026-08-05). Entry points: none. AVSHUNTER Execution Intelligence Layer Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/execution_intelligenceold0803.py`** — [STANDALONE_CLI] 282 lines, last commit `46c002f` (2026-08-05). Entry points: __main__. AVSHUNTER — Execution Intelligence Layer (EIL) Composite Engine Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/execution_intelligenceold1004.py`** — [STANDALONE_CLI] 283 lines, last commit `46c002f` (2026-08-05). Entry points: __main__. AVSHUNTER — Execution Intelligence Layer (EIL) Composite Engine Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/execution_intelligenceold1104.py`** — [STANDALONE_CLI] 283 lines, last commit `46c002f` (2026-08-05). Entry points: __main__. AVSHUNTER — Execution Intelligence Layer (EIL) Composite Engine Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\execution\strategies

**`vanguard/execution/strategies/__init__.py`** — [ORPHAN] 1 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER Execution Intelligence Layer Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/gex_flipper.py`** — [ORPHAN] 170 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S3: GEX Flip Proximity Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/iv_distortion.py`** — [ORPHAN] 199 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S2: IV Distortion Check  [v2.0 — directional] Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/liquidity_gate.py`** — [ORPHAN] 273 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S1: Liquidity Gate  [v2.1 — EV-aware, EOD-safe] Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/obi_predictor.py`** — [ORPHAN] 224 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S4: Order Book Imbalance (OBI)  [v2.0 — flow synthesis] Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/poc_timing.py`** — [ORPHAN] 152 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S5: POC Timing  [v2.0 — regime-aware] Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\execution\strategies\Archive

**`vanguard/execution/strategies/Archive/gex_flipper.py`** — [ORPHAN] 170 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S3: GEX Flip Proximity Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/Archive/iv_distortion.py`** — [ORPHAN] 106 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S2: IV Distortion Check Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/Archive/liquidity_gate.py`** — [ORPHAN] 145 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S1: Liquidity Gate Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/Archive/obi_predictor.py`** — [ORPHAN] 104 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S4: Order Book Imbalance (OBI) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/execution/strategies/Archive/poc_timing.py`** — [ORPHAN] 121 lines, last commit `5d886f0` (2026-08-20). Entry points: none. AVSHUNTER EIL — Strategy S5: POC Timing Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\integration

**`vanguard/integration/orchestrator_adapter1704olddnu.py`** — [ORPHAN · RETIRED(hint)] 49 lines, last commit `46c002f` (2026-08-05). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/integration/orchestrator_adapter1802dnu.py`** — [ORPHAN · RETIRED(hint)] 291 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Integration - Orchestrator Adapter Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/integration/orchestrator_adapter2102dnu.py`** — [ORPHAN · RETIRED(hint)] 436 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Integration - Orchestrator Adapter Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/integration/orchestrator_adapterold.py`** — [ORPHAN] 288 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Integration - Orchestrator Adapter Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/integration/orchestrator_adapterolddnu1504.py`** — [ORPHAN · RETIRED(hint)] 455 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Integration - Orchestrator Adapter Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\layer2_statistical

**`vanguard/layer2_statistical/actuarial_query0605old.py`** — [ORPHAN] 817 lines, last commit `5d886f0` (2026-08-20). Entry points: none. SIMPLIFIED Actuarial Query Engine Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/layer2_statistical/actuarial_querydnu0605old.py`** — [ORPHAN · RETIRED(hint)] 993 lines, last commit `5d886f0` (2026-08-20). Entry points: none. SIMPLIFIED Actuarial Query Engine Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\layer3_execution

**`vanguard/layer3_execution/scenario_builderadmuold1204.py`** — [ORPHAN] 43 lines, last commit `46c002f` (2026-08-05). Entry points: none. AVSHUNTER — Scenario Builder (FIXED v1.1) Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/layer3_execution/scenario_builderolddnu1204.py`** — [ORPHAN · RETIRED(hint)] 490 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Layer 3 - Multi-Scenario Builder Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/layer3_execution/trade_builder2702old dnu.py`** — [ORPHAN · RETIRED(hint)] 329 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Layer 3 - Trade Builder Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/layer3_execution/trade_builderadnu.py`** — [ORPHAN · RETIRED(hint)] 570 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Layer 3 - Trade Builder Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\schemas

**`vanguard/schemas/__init__.py`** — [ORPHAN] 78 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Schemas Package Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/schemas/state_outcomes_schema0505m alo mo.py`** — [ORPHAN] 299 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD State & Outcomes Schemas Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/schemas/trade_schemaolddnu.py`** — [ORPHAN · RETIRED(hint)] 214 lines, last commit `46c002f` (2026-08-05). Entry points: none. VANGUARD Trade Schemas Never imported in the live tree. [OBSERVED — inventory + import graph]


## vanguard\tests

**`vanguard/tests/test_actuarial_match_ladder.py`** — [ORPHAN] 196 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/tests/test_phase2_baton_validation.py`** — [ORPHAN] 115 lines, last commit `5d886f0` (2026-08-20). Entry points: none. _No module docstring._ Never imported in the live tree. [OBSERVED — inventory + import graph]

**`vanguard/tests/test_vanguard_contract.py`** — [ORPHAN] 122 lines, last commit `5d886f0` (2026-08-20). Entry points: none. Unit tests (pytest) for Vanguard contract validation. Never imported in the live tree. [OBSERVED — inventory + import graph]


## zero_dte

**`zero_dte/run_0dte.py`** — [STANDALONE_CLI] 220 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — 0DTE MASTER RUNNER v1.0 Never imported in the live tree. [OBSERVED — inventory + import graph]

**`zero_dte/zero_dte_screener.py`** — [STANDALONE_CLI] 465 lines, last commit `5d886f0` (2026-08-20). Entry points: __main__;argparse-CLI. AVSHUNTER — 0DTE ELIGIBILITY SCREENER v1.0 Never imported in the live tree. [OBSERVED — inventory + import graph]

