# AVSHUNTER Pipeline Artifact Lineage Table
**Date:** 2026-06-30  
**Auditor:** Claude Sonnet 4.6 (read-only forensic review)  
**Classification:** INTERNAL — PROPRIETARY

All paths relative to `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\` unless noted.

---

## Naming Conventions

- `{run_id}` — e.g. `20260624_052030` (YYYYMMDD_HHMMSS, pinned per evening run)
- `{run_dir}` — `data/output/runs/{run_id}/`
- `{vanguard}` — `C:\Users\ACKVerissimo\vanguard\` (outside repo)
- `{superbrain_dir}` — `data/output/runs/{run_id}/superbrain/`
- `{qomega_dir}` — `data/output/runs/{run_id}/qomega/`
- `{packages_dir}` — `data/output/runs/{run_id}/packages/`
- `{morning_dir}` — `data/output/runs/{run_id}/morning_validation/`

---

## Section A: Macro / External Inputs (upstream of discovery)

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `macro_intelligence_latest.json` | `dropbox/macro/macro_intelligence_latest.json` | External (avshunter_macro_module / GPT enrichment cycle) | `intelligent_orchestrator.py` (preflight), `morning_gate.py`, `avshunter_regime_screener.py`, `macro_horizon_router.py` | Pre-Discovery | JSON | `contract_version: macro_contract_v1_0`; must have field `regime_state`; staleness checked (14h gate in morning_gate.py) |
| `avshunter_macro_enrichment_delta.json` | `dropbox/macro/avshunter_macro_enrichment_delta.json` | GPT macro enrichment script (external) | `intelligent_orchestrator.py merge_macro_enrichment_into_macro_latest()` | Pre-Discovery | JSON | Merged into macro_latest before Phase 1; non-critical |
| `bond_macro_state.json` | `dropbox/macro/bond_macro_state.json` | `bond_macro_intelligence.py` | `intelligent_orchestrator.py` (sidecar), `morning_gate.py` CHECK 4 | Pre-Discovery | JSON | max_age 26h; fields: yield_curve, zn, credit_stress, bond_macro_score, trade_go |
| `sec_form4_signals.json` | `dropbox/macro/sec_form4_signals.json` | `sec_form4_monitor.py` | `avshunter_discovery_ULTIMATE.py` (Form 4 enrichment) | Pre-Discovery / Discovery | JSON | Optional; Form 4 insider trading signals |
| `catalyst_calendar_latest.csv` | `dropbox/inputs/catalyst_calendar_latest.csv` | Manual / external | `catalyst_truth_engine.py` | Phase 8a, 8a-post, post_eil | CSV | Optional; if absent, catalyst_truth runs in catalyst-only mode |
| `filtered_universe_latest.csv` | `data/universe/filtered_universe_latest.csv` | VMS scanner / `avshunter_universe_scanner.py` | `intelligent_orchestrator.py merge_scanner_inputs()` | Phase 0 | CSV | max_age_days=7 per `config/orchestrator_integration.json` |
| `polygon_liquid_universe.csv` | `data/universe/polygon_liquid_universe.csv` | Universe builder scripts | `avshunter_discovery_ULTIMATE.py` | Phase 1 / Discovery | CSV | Primary universe input; target 6,500 tickers |

---

## Section B: Scanner & Universe Consumer Outputs

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `augmented_universe_{run_id}.csv` | `{run_dir}/universe/` | `intelligent_orchestrator.build_augmented_universe()` | `avshunter_discovery_ULTIMATE.py` | Phase 0 | CSV | Merged VMS + manual + universe list |
| `scanner_context_{run_id}.json` | `{run_dir}/universe/` | `intelligent_orchestrator.write_scanner_context()` | `avshunter_discovery_ULTIMATE.py --scanner-context` | Phase 0 | JSON | VMS scores; injected into discovery via DISC-02 |
| `sector_bias_map` | In-memory / `_sector_bias_map` | `scripts/sector_alignment.py` | `intelligent_orchestrator.py`, `avshunter_discovery_ULTIMATE.py` | Pre-Discovery | Python dict | REQUIRED for live capital; TAILWIND/HEADWIND/NEUTRAL per sector |

---

## Section C: Discovery Outputs

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `discovery_candidates_ultimate_{run_id}.csv` | `{run_dir}/discovery/` | `avshunter_discovery_ULTIMATE.py` | `run_vanguard_pipeline()` → package builder, options intelligence, trigger_layer, EOD candidate engine | Phase 1 / Phase 3 | CSV | Primary discovery output; tiers 0/1/2/3; Wyckoff/Crabel/direction |
| `final_watchlist_ultimate_{run_id}.csv` | `{run_dir}/discovery/` | `avshunter_discovery_ULTIMATE.py` | Not in primary chain (archival / supplementary) | Phase 1 | CSV | Final filtered watchlist |
| `early_positions_ultimate_{run_id}.csv` | `{run_dir}/discovery/` | `avshunter_discovery_ULTIMATE.py` | Orchestrator position lock check | Phase 1 | CSV | Tier 0 early-entry candidates |
| `discovery_summary_ultimate_{run_id}.json` | `{run_dir}/discovery/` | `avshunter_discovery_ULTIMATE.py` | Orchestrator `validate_quality()`, `detect_regression()` | Phase 2 | JSON | Candidate counts, tier distribution, regression check anchor |
| `regime_signals_{run_id}.csv` | `{run_dir}/discovery/` | `avshunter_regime_screener.py` | Optional enrichment in discovery or manifest | Phase 4.7b | CSV | Mean-reversion, vol-expansion, structural-breakout signals |
| `run_meta.json` | `{run_dir}/` | `pin_run_directory()` | All phases (as manifest header) | Phase 4.5 | JSON | run_id, timestamp, pipeline_version, status |
| `macro_snapshot.json` | `{run_dir}/` | `pin_run_directory()` | All phases (reference snapshot) | Phase 4.5 | JSON | Frozen macro state at run start |
| `macro_quant_packet.json` | `{run_dir}/` | `scripts/macro_quant_packet.py` | Catalyst truth, horizon router, EOD candidate engine | Phase 4.5 | JSON | macro_regime_label, data_quality, freshness_status |
| `truth_packet_run.json` | `{run_dir}/` | `pin_run_directory()` | Handoff guard, lab_control | Phase 4.5 | JSON | Provenance priorities, SOVEREIGN_GATES |

---

## Section D: Package (Vanguard Pipeline) Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `{TICKER}.package.json` | `{packages_dir}/` | `scripts/build_packages_from_discovery.py` | `inject_macro`, `backfill_timeseries`, `avshunter_trap_engine.py`, `trigger_layer.patch_run_packages()`, `actuarial_enrichment_pass.py` | Phase 5a | JSON | One file per ticker; evolves through phases 5a→5.5→8.5→8.6 |
| `{TICKER}.package.json` (macro-injected) | `{packages_dir}/` | `scripts/inject_macro_into_packages.py` | Same as above (in-place update) | Phase 5b | JSON | Adds macro regime, size_multiplier, Fung-Hsieh fields |
| `{TICKER}.package.json` (timeseries-injected) | `{packages_dir}/` | `scripts/backfill_timeseries_into_packages.py` | Same as above (in-place update) | Phase 5c | JSON | Adds OHLCV history; return code 2 = partial (non-fatal) |
| `{TICKER}.package.json` (tle_ fields added) | `{packages_dir}/` | `avshunter_trap_engine.py` | `scripts/avshunter_options_intelligence.py` (reads `tle_verdict`) | Phase 5.5 | JSON | tle_bullish_score, tle_bearish_score, tle_verdict, tle_trap_direction, tle_who_is_trapped, tle_forced_move_level, tle_entry_trigger, tle_kill_switch, tle_crowd_arrival_target |
| `{TICKER}.package.json` (trigger_ fields added) | `{packages_dir}/` | `trigger_layer.patch_run_packages()` | Nothing (final state, read by EOD candidate engine indirectly) | Phase 8.6 | JSON | trigger_codes, trigger_score, trigger_count, go_eligible, eligible_for_trade |
| `{TICKER}.package.json` (actuarial fields added) | `{packages_dir}/` | `scripts/actuarial_enrichment_pass.py` | Pre-EIL injection in orchestrator (FIX-ACTUARIAL-SEQ) | Phase 8.5 | JSON | win_rate_5d/10d/20d, expected_move_5d/10d/20d, efficiency_5d/10d/20d, penalty_multiplier, actuarial_match_type |

---

## Section E: Vanguard Signal Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `vanguard_signals.csv` | `{run_dir}/vanguard/` | `scripts/run_vanguard_from_packages.py` | `scripts/avshunter_options_intelligence.py`, `scripts/core_intel_exporter.py` | Phase 6 | CSV | Core vanguard output; structural EV, actuarial stats |
| `vanguard_run_summary.json` | `{run_dir}/vanguard/` | `scripts/run_vanguard_from_packages.py` | Orchestrator (non-critical) | Phase 6 | JSON | Summary stats of vanguard run |
| `vanguard_signals_enriched_{run_id}.csv` | `{run_dir}/options_intel/` | `scripts/avshunter_options_intelligence.py` | `trigger_layer.patch_run_packages()`, `run_superbrain_passthrough()`, WBS | Phase 8b | CSV | vanguard_signals.csv + options intelligence fields |
| `actuarial_database_v6.parquet` | `{vanguard}/` | Vanguard actuarial DB scripts | `{vanguard}/actuarial_cache_builder.py`, `scripts/actuarial_enrichment_pass.py` | Phase 4.6 (cache build) | Parquet | External to repo; 9-dim state key → win rates / expected moves |
| `actuarial_cache.parquet` | `{vanguard}/` | `{vanguard}/actuarial_cache_builder.py` | `scripts/actuarial_enrichment_pass.py`, pre-EIL injection | Phase 4.6 | Parquet | Cached fast-lookup table from actuarial_database_v6 |
| `transition_matrix_{run_id}.csv` | `{run_dir}/vanguard/` | `scripts/build_phase_transition_matrix.py` | Not in primary decision chain (archival / ML Sprint 4 future use) | Phase 4.7a | CSV | Wyckoff phase-to-phase probabilities |

---

## Section F: Catalyst Truth Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `catalyst_truth_{stage}_{run_id}.csv` | `{run_dir}/catalyst/` | `catalyst_truth_engine.py` | `scripts/core_intel_exporter.py`, EOD candidate engine | Phase 8a (×3) | CSV | catalyst_detected, catalyst_truth_score, event_convexity_score, cheap_convexity_flag, 25 fields total |

---

## Section G: Options Intelligence Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `options_intelligence_{run_id}.csv` | `{run_dir}/options_intel/` | `scripts/avshunter_options_intelligence.py` | `macro_horizon_router.py`, `scripts/phantom_engine.py`, `scripts/core_intel_exporter.py`, `run_superbrain_passthrough()`, WBS, GARCH, EOD candidate engine | Phase 8b | CSV | options_verdict, recommended_contract, contract_strike, contract_expiry, contract_dte, contract_premium, contract_delta, contract_theta, contract_vega, iv_rank, iv_percentile, gamma_flip, call_wall, put_wall, max_pain, pcr_oi, pcr_signal, structural_ev, options_score, stand_down_reason |
| `options_intelligence_summary_{run_id}.json` | `{run_dir}/options_intel/` | `scripts/avshunter_options_intelligence.py` | Orchestrator (non-critical) | Phase 8b | JSON | Summary: EXECUTE count, ARMED count, STAND_DOWN count |
| `options_intelligence_phantom_{run_id}.csv` | `{run_dir}/options_intel/` | `scripts/phantom_engine.py` | `scripts/core_intel_exporter.py` (preferred over original), `run_superbrain_passthrough()` | Phase 7.5 | CSV | All OI fields + PHANTOM historical edge scores; preferred when present |
| `horizon_{bucket}_{run_id}.csv` | `{run_dir}/horizon/` | `macro_horizon_router.py` | Patched back into OI CSV and superbrain_enriched | Phase 1B | CSV | 3 buckets: 1_5d, 6_10d, 11_20d; fields: horizon_bucket, horizon_bias, horizon_size_mult |
| `horizon_summary_{run_id}.json` | `{run_dir}/horizon/` | `macro_horizon_router.py` | Orchestrator (non-critical) | Phase 1B | JSON | Distribution across horizons |

---

## Section H: SuperBrain (Passthrough) Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `superbrain_enriched_{run_id}.csv` | `{superbrain_dir}/` | `run_superbrain_passthrough()` | `wall_break_scorer.py`, pre-EIL actuarial injection, `execution_intelligence_runner.py`, GARCH merge, Trigger Layer 8.6b, EOD candidate engine | Phase 8d | CSV | Copy of OI/phantom CSV with options_verdict mapped → sb_final_verdict; NOT scored by SuperBrain layer (deprecated) |
| `superbrain_execute_{run_id}.csv` | `{superbrain_dir}/` | `scripts/avshunter_superbrain_layer.py` | Not used (superbrain scoring deprecated) | N/A | CSV | NOT written in current pipeline (passthrough only) |
| `superbrain_injections_{run_id}.csv` | `{superbrain_dir}/` | `scripts/avshunter_superbrain_layer.py` | Not used | N/A | CSV | NOT written in current pipeline |
| `superbrain_summary_{run_id}.json` | `{superbrain_dir}/` | `run_superbrain_passthrough()` | Orchestrator (non-critical log) | Phase 8d | JSON | sb_final_verdict distribution |
| `wall_break_scores_{run_id}.csv` | `{superbrain_dir}/` | `wall_break_scorer.py` | EOD candidate engine (wbs_score, wbs_grade) | Phase 8e | CSV | wbs_score (0-100), wbs_grade (IMMINENT/PROBABLE/POSSIBLE/UNLIKELY), 5 factor sub-scores |

---

## Section I: EIL and Execution Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `eil_enriched_{run_id}.csv` | `{superbrain_dir}/` | `execution_intelligence_runner.py` | GARCH merge (Phase 10b), Trigger Layer 8.6b (enrich_csv), McMillan Advisory Layer, EOD candidate engine | Phase 9 | CSV | eil_v3_verdict, pse_final_size (always 0.0), convergence_score, 5 strategy outputs, mcmillan fields |
| `execution_v3_5_{run_id}.csv` | `{run_dir}/execution/` | `execution_intelligence_runner.py` | GARCH merge (Phase 10b), EOD candidate engine | Phase 9 | CSV | EIL execution summary; pse_candidate_size always 0.0 |
| `locked_tickers_{run_id}.txt` | `{run_dir}/` | `run_position_lock_check()` | `scripts/avshunter_options_intelligence.py` (skip locked tickers), `avshunter_discovery_ULTIMATE.py` | Phase 8b-lock | TXT | One ticker per line; tickers with open positions |

---

## Section J: GARCH Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `garch_forecasts_{run_id}.csv` | `{qomega_dir}/` | `garch_runner.py` | `merge_garch_into_enriched()` (patched into superbrain_enriched, eil_enriched, execution CSV) | Phase 10a | CSV | l3_forward_realised_vol, l3_vol_forecast_conf, l3_expected_move_1_5d, l3_expected_move_6_10d, l3_expected_move_11_20d, l3_iv_tailwind_score, l3_jump_risk_flag, l3_method, l3_error |

---

## Section K: EOD / Morning Candidate Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `morning_candidates_{run_id}.csv` | `{run_dir}/` | `eod_candidate_engine.py` | `morning_gate.py`, `morning_thesis_validator.py`, `avshunter_exit_engine.py` (via morning_validated) | Phase 10 | CSV | 300+ columns; Tier A/B/C/WATCH; SCS score; mcmillan fields; l3_ fields; actuarial fields |
| `latest.json` | `data/output/latest.json` | `intelligent_orchestrator.write_latest_json()` | `morning_gate.py`, `morning_thesis_validator.py`, `avshunter_exit_engine.py` (resolves run_id) | End of evening run | JSON | run_id, run_dir, morning_candidates_path, summary stats |
| `morning_gate_summary_{run_id}.json` | `{morning_dir}/` | `morning_gate.py` | Orchestrator morning workflow (non-critical) | Morning | JSON | input_candidates, go_count, flag_count, block_count, contract_repair_resolved_count |
| `morning_validated_trades_{run_id}.csv` | `{morning_dir}/` | `morning_gate.py` | `avshunter_exit_engine.py`, `execution_gate.py` | Morning | CSV | All morning_candidates + morning_gate verdict fields |
| `morning_exit_signals.csv` | `{run_dir}/` | `avshunter_exit_engine.py` | Human trader (advisory; no auto-writes) | Morning (post morning_gate) | CSV | exit_verdict, exit_trigger, exit_size_pct, reason, urgency, r_realised, r_remaining, suggested_exit_command |
| `morning_execution_gate_{run_id}.csv` | `{morning_dir}/` | `execution_gate.py` | Human trader / pipeline interpreter | Morning | CSV | Execution gate hard-pass/fail per position |

---

## Section L: Handoff / Lab Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `final_run_manifest.json` | `{run_dir}/` | `contracts/lab_control.write_final_run_manifest()` | `pipeline_interpreter/ma_inputs_sync.py`, human operator | End of morning run | JSON | lab_verdict, lab_tradeable, lab_execution_status, go_count, flag_count, block_count |
| `final_opportunity_book.csv` | `{run_dir}/` | `contracts/lab_control.write_final_opportunity_book()` | Human trader (Intelligence Lab) | End of morning run | CSV | Ranked opportunity book for morning session |
| `handoff_conflict_report_{run_id}.json` | `{run_dir}/` | `enforce_handoff_conflict_guard()` | Orchestrator (HARD ABORT if fails), `handoff_contract_audit.py` | Evening (post-EIL) | JSON | Field-level conflict flags, SOVEREIGN_GATES state |
| `dropoff_audit_{run_id}.csv` | `{run_dir}/` | `dropoff_audit.py` | Orchestrator (logging), human operator | Evening (Phase 11) | CSV | Checkpoints: phase0, post_package_build, post_vanguard, post_options — dropoff per gate |
| `pipeline_integrity_{run_id}.json` | `{run_dir}/` | `intelligent_orchestrator.py evening_workflow` | Human operator | Evening (Phase 11) | JSON | Per-phase duration, pass/fail, artifact sizes |
| `uat_audit_report_{run_id}.json` | `{run_dir}/` | `uat_audit_report.py` | Human operator | Evening (Phase 11) | JSON | Phase-by-phase UAT check results |

---

## Section M: Trade Journal Artifacts

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `trade_journal.db` | `data/journal/trade_journal.db` | `avshunter_trade_journal.py log-entry / log-exit` (human-triggered CLI) | `run_position_lock_check()`, `avshunter_exit_engine.py` (read-only during morning), `outcome_capture.py` | Always | SQLite | Schema: trade_id, ticker, direction, entry_premium, entry_date, dte_at_entry, exit_premium, exit_date, exit_reason, outcome_class, ml_eligible (Sprint 4 column) |

---

## Section N: ML / Calibration Artifacts (Sprint 4 — Partial)

| Artifact | Typical Path | Written By | Read By | Phase | Format | Notes |
|----------|-------------|-----------|--------|-------|--------|-------|
| `confidence_weights.json` | `data/ml/` | `ml_confidence_engine.py` (manual --apply-weights only) | `confirmation_ingester.py` | N/A (Sprint 4) | JSON | Current confidence weights; auto-update gated behind CLI flag |
| `weights_baseline_{date}.json` | `data/ml/` | `ml_confidence_engine.py` (freeze before update) | Human review | N/A (Sprint 4) | JSON | Frozen baseline before any weight update |
| `regression_report_{date}.txt` | `data/output/calibration/` | `ml_confidence_engine.run_outcome_regression()` | Human review | N/A (Sprint 4) | TXT | Top predictors, predicted vs realised win rate/R:R, RECOMMENDED WEIGHT ADJUSTMENTS (advisory) |

---

## Section O: NOT-FOUND / NOT-ACTIVE Artifacts

These artifacts were referenced in CLAUDE.md (deliverables table) or in comments but are NOT written by the current pipeline:

| Expected Artifact | Expected Path | Expected Writer | Status | Reason |
|-----------------|--------------|----------------|--------|--------|
| `ct_enriched_{run_id}.csv` | `{run_dir}/` | `catastrophe_gate.py` | NOT WRITTEN | `run_catastrophe_gate()` is a no-op stub since Sprint 2 |
| `ct_summary_{run_id}.json` | `{run_dir}/` | `catastrophe_gate.py` | NOT WRITTEN | Same — no-op stub |
| `csm_*` fields in signals CSV | OI CSV / package JSON | `build_convexity_strike_map()` | NOT WRITTEN | Sprint 2 not yet built; function not found in `scripts/avshunter_options_intelligence.py` |
| `enhancement_output_{run_id}.csv` | `{run_dir}/enhancement/` | `enhancement_integration.py` | NOT WRITTEN | Phase 9B commented out in orchestrator |
| `trade_book_{run_id}.csv` | `{run_dir}/trade_book/` | `trade_book_builder.py` | NOT WRITTEN | Phase 9C commented out |
| EDE output CSV | `{run_dir}/ede/` | `execution_decision_engine.py` | NOT WRITTEN | Phase 9.5 commented out |
| `superbrain_execute_{run_id}.csv` | `{superbrain_dir}/` | `scripts/avshunter_superbrain_layer.py` | NOT WRITTEN | Passthrough only; scoring not run |

---

## Section P: Field Contract Summary (Key Inter-Module Contracts)

| Field | Source Module / Phase | Consumer Module / Phase | Direction |
|-------|---------------------|------------------------|-----------|
| `options_verdict` | `scripts/avshunter_options_intelligence.py` (Phase 8b) | `run_superbrain_passthrough()` (mapped → sb_final_verdict) | CSV → passthrough copy |
| `sb_final_verdict` | `run_superbrain_passthrough()` (Phase 8d) | `execution_intelligence_runner.py` (Phase 9 — EIL skips if absent) | superbrain_enriched CSV |
| `tle_verdict` | `avshunter_trap_engine.py` (Phase 5.5) | `scripts/avshunter_options_intelligence.py` (Phase 8b — CSM modifier) | Package JSON |
| `tle_bullish_score`, `tle_bearish_score` | `avshunter_trap_engine.py` (Phase 5.5) | `scripts/avshunter_options_intelligence.py`, EOD candidate engine | Package JSON |
| `trigger_codes`, `trigger_score`, `go_eligible` | `trigger_layer.patch_run_packages()` (Phase 8.6) | Package JSONs read by EIL | Package JSON |
| `trigger_codes`, `trigger_score`, `go_eligible` | `trigger_layer.enrich_csv()` (Phase 8.6b) | EOD candidate engine (read from eil_enriched) | eil_enriched CSV in-place |
| `l3_forward_realised_vol`, `l3_expected_move_*`, `l3_iv_tailwind_score` | `garch_runner.py` (Phase 10a) | `merge_garch_into_enriched()` → superbrain_enriched + eil_enriched; `morning_gate.py` CHECK 5 | garch_forecasts CSV → patched in |
| `win_rate_5d/10d/20d`, `expected_move_10d`, `efficiency_10d` | `scripts/actuarial_enrichment_pass.py` (Phase 8.5) → package JSON; pre-EIL injection patches superbrain_enriched | `execution_intelligence_runner.py` (Phase 9 S3 GEX flip strategy) | Package JSON → superbrain_enriched |
| `wbs_score`, `wbs_grade` | `wall_break_scorer.py` (Phase 8e) | `eod_candidate_engine.py` (Tier A/B classification); NOT read by EIL | wall_break_scores CSV |
| `csm_*` fields | NOT-FOUND (Sprint 2 not built) | Intended: `scripts/avshunter_superbrain_layer.py`, morning manifest | NOT WIRED |
| `pse_final_size`, `candidate_size` | `execution_intelligence_runner.py` (Phase 9) | Human trader (advisory 0.0) | eil_enriched CSV — always 0.0 |
| `horizon_bucket`, `horizon_size_mult` | `macro_horizon_router.py` (Phase 1B) | Patched into OI CSV, superbrain_enriched; `morning_gate.py` | horizon CSV → patched in |
| `eil_v3_verdict` | `execution_intelligence_runner.py` (Phase 9) | `eod_candidate_engine.py` (required column); EOD candidate engine — required | eil_enriched CSV |
| `catalyst_truth_score`, `event_convexity_score` | `catalyst_truth_engine.py` (Phase 8a ×3) | `scripts/core_intel_exporter.py`, EOD candidate engine | catalyst CSV |
| `macro_filter`, `size_multiplier`, `regime_state` | `dropbox/macro/macro_intelligence_latest.json` | `avshunter_discovery_ULTIMATE.py` (risk-off floor), `macro_horizon_router.py`, `morning_gate.py` CHECK 2, EIL sizing path | JSON |
| `actuarial_loaded_pre_eil` | Pre-EIL injection in orchestrator (~line 4034) | EIL runner (stamps True if actuarial filled) | superbrain_enriched CSV |
| `ml_eligible` | `avshunter_trade_journal.py` (manual / schema column) | `confirmation_ingester.py` (Sprint 4 gate: skip if eligible count < 30) | SQLite journal DB |
| `exit_verdict`, `exit_trigger`, `suggested_exit_command` | `avshunter_exit_engine.py` (Morning) | Human trader (read-only advisory) | morning_exit_signals.csv |
| `morning_gate_verdict` (GO/FLAG/BLOCK) | `morning_gate.py` | `avshunter_exit_engine.py` (TRIGGER 3: BLOCKED/WAIT → TAKE_FULL) | morning_validated_trades CSV |
| `lab_tradeable`, `lab_verdict` | `contracts/lab_control.py` | `pipeline_interpreter/ma_inputs_sync.py`, human operator | final_run_manifest.json |
