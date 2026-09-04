# 09 — Outputs catalogue

**Document:** AVS-E2E-CODE-001 · Step 7
**Evidence run:** `data/output/runs/20260831_010309/`

Row/column counts and version-field presence are **MEASURED** from the evidence run. Producer attribution is **OBSERVED** from the orchestrator call order in `03_execution_order.md`. `mtime` is the **last** write — see the rewrite caveat in `03_execution_order.md` §1.

Per-ticker package files under `packages/` are catalogued in aggregate: **1528 files** (one JSON per ticker, written at evening stage 9 and patched by Trigger Layer pass 1 at stage 27).

| Artefact (pattern) | Rows | Cols | Bytes | Last write | Version/identity fields present |
|---|---:|---:|---:|---|---|
| `canonical/cds3_discovery_publication_{run_id}.json` | — | — | 560 | 2026-08-31 01:06:42 | run_id |
| `catalysts/catalyst_truth_{run_id}.csv` | 1528 | 32 | 623,667 | 2026-08-31 02:55:42 | — |
| `catalysts/catalyst_truth_summary_{run_id}.json` | — | — | 2,864 | 2026-08-31 02:55:51 | run_id, version |
| `core_intel/core_intel_dossiers_{run_id}.json` | — | — | 3,735,349 | 2026-08-31 02:39:35 | — |
| `core_intel/core_intel_export_summary_{run_id}.json` | — | — | 1,016 | 2026-08-31 02:39:35 | — |
| `core_intel/core_intel_menu_{run_id}.json` | — | — | 6,633 | 2026-08-31 02:39:35 | — |
| `diagnostics/dropoff_audit_{run_id}.csv` | 3320 | 129 | 3,182,601 | 2026-08-31 02:56:10 | run_id |
| `diagnostics/dropoff_audit_{run_id}.json` | — | — | 4,936 | 2026-08-31 02:56:10 | run_id |
| `diagnostics/handoff_contract_audit_{run_id}.csv` | 162 | 11 | 37,160 | 2026-08-31 02:56:11 | — |
| `diagnostics/handoff_contract_audit_{run_id}.json` | — | — | 6,717 | 2026-08-31 02:56:11 | run_id |
| `diagnostics/intraday_regime_watchdog_{run_id}.json` | — | — | 939 | 2026-08-31 02:56:06 | run_id |
| `diagnostics/intraday_regime_watchdog_message_{run_id}.txt` | — | — | 90 | 2026-08-31 02:56:06 | — |
| `diagnostics/market_breadth_diagnostic_{run_id}.json` | — | — | 3,330 | 2026-08-31 02:56:06 | run_id |
| `diagnostics/market_breadth_message_{run_id}.txt` | — | — | 163 | 2026-08-31 02:56:06 | — |
| `diagnostics/read_only_market_context_{run_id}.json` | — | — | 616 | 2026-08-31 02:56:06 | run_id |
| `diagnostics/uat_audit_report_{run_id}.json` | — | — | 4,829 | 2026-08-31 02:56:12 | run_id |
| `diagnostics/uat_audit_report_{run_id}.md` | — | — | 3,548 | 2026-08-31 02:56:12 | — |
| `discovery/discovery_candidates_cds3_{run_id}.csv` | 1527 | 287 | 7,243,834 | 2026-08-31 01:06:43 | — |
| `discovery/discovery_candidates_ultimate_{run_id}.csv` | 1527 | 316 | 7,716,046 | 2026-08-31 02:55:42 | — |
| `discovery/discovery_lifecycle_{run_id}.csv` | 3320 | 7 | 187,278 | 2026-08-31 01:03:09 | — |
| `discovery/external_intel_review_candidates_{run_id}.csv` | 37 | 263 | 127,898 | 2026-08-31 01:03:11 | — |
| `ev3_shadow/ev3_authority_overlay.csv` | 1248 | 21 | 428,154 | 2026-08-31 02:31:37 | — |
| `ev3_shadow/ev3_calibration_readiness.json` | — | — | 980 | 2026-08-31 02:31:37 | schema_version |
| `ev3_shadow/ev3_shadow_phase_status_{run_id}.json` | — | — | 7,932 | 2026-08-31 02:31:37 | run_id, schema_version |
| `ev3_shadow/ev3_stage1_contract_evaluations.parquet` | — | — | 21,138 | 2026-08-31 02:31:34 | — |
| `ev3_shadow/ev3_stage1_shadow_audit.json` | — | — | 3,586 | 2026-08-31 02:31:34 | — |
| `ev3_shadow/ev3_stage1_shadow_ranked.csv` | 0 | 15 | 286 | 2026-08-31 02:31:34 | — |
| `ev3_shadow/ev3_stage1_shadow_rejections.csv` | 927 | 15 | 171,865 | 2026-08-31 02:31:34 | — |
| `ev3_shadow/ev3_stage1_shadow_results.parquet` | — | — | 28,566 | 2026-08-31 02:31:34 | — |
| `execution/execution_v3_5_{run_id}.csv` | 1248 | 1071 | 22,755,603 | 2026-08-31 02:55:55 | calculation_version, lifecycle_contract_version, run_id |
| `final_run_manifest.json` | — | — | 3,313 | 2026-08-31 10:02:11 | pipeline_mode, run_id |
| `horizon/horizon_11_20d_{run_id}.csv` | 0 | 970 | 23,902 | 2026-08-31 02:31:28 | schema_version |
| `horizon/horizon_1_5d_{run_id}.csv` | 655 | 970 | 13,010,443 | 2026-08-31 02:31:28 | schema_version |
| `horizon/horizon_6_10d_{run_id}.csv` | 284 | 970 | 5,469,168 | 2026-08-31 02:31:28 | schema_version |
| `horizon/horizon_blocked_{run_id}.csv` | 17 | 970 | 266,882 | 2026-08-31 02:31:28 | schema_version |
| `horizon/horizon_summary_{run_id}.json` | — | — | 1,407 | 2026-08-31 02:31:28 | run_id |
| `intelligence_lab/final_opportunity_book_{run_id}.csv` | 201 | 375 | 9,073,451 | 2026-08-31 02:56:24 | lifecycle_contract_version, pipeline_mode, run_id |
| `intelligence_lab/final_opportunity_book_{run_id}.json` | — | — | 11,066,811 | 2026-08-31 02:56:24 | run_id |
| `intelligence_lab/lab_triage_view_{run_id}.csv` | 201 | 374 | 3,560,532 | 2026-08-31 02:56:24 | lifecycle_contract_version, pipeline_mode, run_id |
| `macro_quant_packet.json` | — | — | 3,973 | 2026-08-31 01:03:13 | — |
| `macro_snapshot.json` | — | — | 249,032 | 2026-08-31 01:03:13 | contract_version |
| `morning_validation/direction_transition_matrix_{run_id}.csv` | 16 | 7 | 1,224 | 2026-08-31 02:56:01 | — |
| `morning_validation/eod_dropoff_audit_{run_id}.csv` | 1248 | 141 | 3,283,201 | 2026-08-31 02:56:01 | run_id |
| `morning_validation/missed_opportunity_shadow_book_{run_id}.csv` | 261 | 67 | 218,725 | 2026-08-31 02:56:01 | run_id |
| `morning_validation/morning_blocked_review_{run_id}.csv` | 736 | 487 | 7,594,947 | 2026-08-31 02:56:02 | run_id |
| `morning_validation/morning_candidates_{run_id}.csv` | 201 | 518 | 2,165,222 | 2026-08-31 02:56:05 | run_id |
| `morning_validation/regime_watch_{run_id}.csv` | 594 | 490 | 5,956,816 | 2026-08-31 02:56:02 | run_id |
| `options/contract_rejection_log_{run_id}.csv` | 1102 | 9 | 107,091 | 2026-08-31 02:31:21 | — |
| `options/governed_direction_records_{run_id}.jsonl` | — | — | 2,038,638 | 2026-08-31 02:31:19 | — |
| `options/options_blocked_review.csv` | 311 | 724 | 3,139,305 | 2026-08-31 02:31:20 | calculation_version, lifecycle_contract_version |
| `options/options_candidates_ranked.csv` | 1248 | 724 | 17,481,674 | 2026-08-31 02:31:20 | calculation_version, lifecycle_contract_version |
| `options/options_intelligence_{run_id}.csv` | 1248 | 773 | 18,361,341 | 2026-08-31 02:55:46 | calculation_version, lifecycle_contract_version |
| `options/options_intelligence_{run_id}_pre_ev3_authority.csv` | 1248 | 724 | 17,553,739 | 2026-08-31 02:31:31 | calculation_version, lifecycle_contract_version |
| `options/options_intelligence_latest.csv` | 1248 | 724 | 17,481,674 | 2026-08-31 02:31:19 | calculation_version, lifecycle_contract_version |
| `options/options_intelligence_phantom_{run_id}.csv` | 1248 | 813 | 18,792,177 | 2026-08-31 02:39:30 | calculation_version, lifecycle_contract_version, run_id |
| `options/options_intelligence_summary_{run_id}.json` | — | — | 6,412 | 2026-08-31 02:31:24 | run_id |
| `options/options_summary.json` | — | — | 6,412 | 2026-08-31 02:31:24 | run_id |
| `options/phantom_summary_{run_id}.json` | — | — | 369 | 2026-08-31 02:39:30 | run_id |
| `options/vanguard_signals_enriched_{run_id}.csv` | 1481 | 966 | 26,354,181 | 2026-08-31 02:55:45 | schema_version |
| `pipeline_integrity_{run_id}.json` | — | — | 2,182 | 2026-08-31 02:56:06 | run_id |
| `qomega/garch_forecasts_{run_id}.csv` | 1248 | 17 | 93,496 | 2026-08-31 02:55:25 | — |
| `run_meta.json` | — | — | 1,564 | 2026-08-31 02:56:41 | contract_version, pipeline_mode |
| `superbrain/eil_enriched_{run_id}.csv` | 1248 | 1050 | 22,338,128 | 2026-08-31 02:55:53 | calculation_version, lifecycle_contract_version, run_id |
| `superbrain/superbrain_enriched_{run_id}.csv` | 1248 | 856 | 19,231,754 | 2026-08-31 02:55:47 | calculation_version, lifecycle_contract_version, run_id |
| `superbrain/wall_break_scores_{run_id}.csv` | 31 | 835 | 599,857 | 2026-08-31 02:50:15 | calculation_version, lifecycle_contract_version, run_id |
| `superbrain/wall_break_summary_{run_id}.json` | — | — | 810 | 2026-08-31 02:50:15 | run_id |
| `trigger_layer_summary_{run_id}.csv` | 1527 | 14 | 173,708 | 2026-08-31 02:45:10 | — |
| `truth_packet_run.json` | — | — | 11,216 | 2026-08-31 01:03:13 | run_id |
| `vanguard/vanguard_rejects.csv` | 46 | 7 | 9,309 | 2026-08-31 01:56:25 | — |
| `vanguard/vanguard_run_summary.json` | — | — | 464 | 2026-08-31 01:56:25 | run_id |
| `vanguard/vanguard_signals.csv` | 1481 | 512 | 15,875,782 | 2026-08-31 02:55:43 | schema_version |

## JSON artefacts — top-level keys

- `canonical/cds3_discovery_publication_{run_id}.json` → `drop_count`, `enforcement_enabled`, `error_count`, `input_count`, `mode`, `package_worklist_count`, `published_at_utc`, `reconciled`, `registry`, `run_id`, `source`, `survivor_count`
- `catalysts/catalyst_truth_summary_{run_id}.json` → `catalyst_detected`, `cheap_convexity`, `dated_catalysts`, `event_convexity_watch`, `high_truth_score`, `inside_dte`, `liquidity_ok`, `manual_tickers`, `manual_with_dated_catalyst`, `manual_with_detected_catalyst`, `output_path`, `patch_results`, `rows`, `run_id`, `top_event_convexity`, `trade_class_counts`, `version`
- `core_intel/core_intel_dossiers_{run_id}.json` → `dossiers`, `macro`, `meta`
- `core_intel/core_intel_export_summary_{run_id}.json` → `counts`, `inputs`, `meta`, `warnings`
- `core_intel/core_intel_menu_{run_id}.json` → `meta`, `methodology`, `pool_counts`, `selections`
- `diagnostics/dropoff_audit_{run_id}.json` → `audit_behavior_counts`, `audit_layer_counts`, `audit_severity_counts`, `dropoff_stage_counts`, `generated_utc`, `input_paths`, `last_stage_counts`, `output_csv`, `root_cause_family_counts`, `rows`, `run_id`, `shadow_opportunity_label_counts`, `top_dropoff_reasons`, `vanguard_contract_contradiction_counts`, `vanguard_expected_options_scope_counts`, `vanguard_support_override_count`
- `diagnostics/handoff_contract_audit_{run_id}.json` → `artifact_paths`, `fail_count`, `generated_utc`, `output_csv`, `outstanding_fixes`, `overall_status`, `run_id`, `status_counts`, `warn_count`
- `diagnostics/intraday_regime_watchdog_{run_id}.json` → `advisory_only`, `data_mode`, `diagnostic`, `generated_at_utc`, `mutates_pipeline_outputs`, `operator_message`, `reasons`, `run_id`, `source_files`, `vix_context`, `watchdog_label`
- `diagnostics/market_breadth_diagnostic_{run_id}.json` → `advisory_only`, `alignment_notes`, `alignment_status`, `breadth`, `candidate_slate`, `diagnostic`, `generated_at_utc`, `macro_context`, `mutates_pipeline_outputs`, `operator_message`, `run_id`, `source_files`
- `diagnostics/read_only_market_context_{run_id}.json` → `advisory_only`, `diagnostic`, `generated_at_utc`, `intraday_watchdog_label`, `intraday_watchdog_message`, `market_breadth_message`, `market_breadth_status`, `mutates_pipeline_outputs`, `run_id`
- `diagnostics/uat_audit_report_{run_id}.json` → `artifacts`, `candidate_count`, `candidate_status_counts`, `candidate_tier_counts`, `dropoff_stage_counts`, `execution_capital_counts`, `execution_effective_counts`, `generated_utc`, `handoff_fail_count`, `handoff_status`, `handoff_warn_count`, `macro_active_conflict_flags`, `macro_data_quality`, `macro_freshness_status`, `macro_resolved_conflict_flags`, `macro_source`, `root_cause_family_counts`, `run_id`, `shadow_label_counts`, `top_dropoff_reasons`
- `ev3_shadow/ev3_calibration_readiness.json` → `activation_reasons`, `capital_authority_calibrated`, `generated_utc`, `journal_outcome_rows`, `matched_nonpositive_ev_rows`, `matched_outcome_rows`, `matched_positive_ev_rows`, `matched_profitable_rows`, `matched_win_rate`, `minimum_matched_outcomes`, `minimum_outcomes_per_ev_band`, `phantom_db`, `phantom_outcome_rows`, `prediction_rows`, `runs_dir`, `schema_version`, `status`, `trade_journal`
- `ev3_shadow/ev3_shadow_phase_status_{run_id}.json` → `absolute_state_counts`, `adjudicated_rows`, `adjudication_coverage`, `authority_activation_reasons`, `authority_blocked_rows`, `authority_mode`, `authority_output_path`, `authority_overlay_path`, `authority_positive_rows`, `authority_requested`, `barrier_cache_path`, `barrier_cache_sha256`, `calibration_report_path`, `calibration_status`, `capital_authority_calibrated`, `capital_eligibility_enabled`, `contract_evaluation_reason_counts`, `contract_evaluation_structure_counts`, `coverage`, `detail`, `dominant_reason_code`, `dominant_reason_count`, `dominant_reason_share`, `engine_stage`, `ev3_coverage_health`, `ev_component_authority_enabled`, `ev_functional_health`, `evaluation_clock_mode`, `evaluation_coverage`, `evaluation_now_utc`, `expected_contract_rejections`, `expected_market_rejections`, `functional_test_clock_override`, `generated_utc`, `health`, `input_path`, `input_sha256`, `mode`, `morning_capital_permission`, `pipeline_blocking`, `production_authority`, `production_consumer_enabled`, `production_evidence`, `reason_counts`, `rows_applicable`, `rows_evaluated`, `rows_not_applicable`, `rows_received`, `rows_rejected`, `run_id`, `schema_version`, `shadow_audit_path`, `state_match_counts`, `strict_production_freshness`, `system_defect_rows`, `system_defects`, `technical_health`, `unclassified_rejections`, `unclassified_rows`
- `ev3_shadow/ev3_stage1_shadow_audit.json` → `absolute_state_counts`, `artifact_contract_version`, `barrier_path`, `barrier_sha256`, `built_at_utc`, `capital_eligibility_enabled`, `contract_candidates_received`, `contract_evaluation_reason_counts`, `contract_evaluation_structure_counts`, `contract_evaluations_written`, `engine_source_sha256`, `evaluation_now_utc`, `input_path`, `input_sha256`, `limitations`, `mode`, `outputs`, `phase`, `policy`, `production_authority`, `production_consumer_enabled`, `reason_counts`, `rows_evaluated`, `rows_not_applicable`, `rows_received`, `rows_rejected`, `runner_source_sha256`, `stage`, `state_match_counts`
- `final_run_manifest.json` → `conflict_flags`, `created_at_utc`, `ev3_production_authority`, `ev3_production_evidence`, `ev_functional_health`, `expected_contract_rejections`, `expected_market_rejections`, `fatal_flags`, `manual_review_enabled`, `missing_columns`, `morning_capital_permission`, `next_action`, `output_files`, `phase_status`, `pipeline_interpreter_prep_enabled`, `pipeline_mode`, `pipeline_technical_health`, `required_columns_present`, `row_counts`, `run_execution_permission`, `run_health_score`, `run_id`, `run_prep_permission`, `run_tradeable`, `run_tradeable_label`, `stale_flags`, `system_defects`, `v5_colab_decommissioned`
- `horizon/horizon_summary_{run_id}.json` → `as_of_utc`, `horizon_biases`, `horizon_counts`, `macro_age_hours`, `macro_conviction`, `macro_direction_sizing`, `macro_direction_sizing_default`, `macro_generated_at`, `macro_momentum_score`, `put_vix_threshold`, `regime_state`, `run_id`
- `intelligence_lab/final_opportunity_book_{run_id}.json` → `candidate_count`, `created_at_utc`, `lab_schema_version`, `reconciliation`, `rows`, `run_id`, `source_errors`, `source_manifest`, `verdict_counts`
- `macro_quant_packet.json` → `auction_spread_risk`, `avoid_sectors`, `bond_macro_flag`, `bond_macro_score`, `bond_trade_go`, `breakeven_adjustment_pct`, `bucket_clarity_scores`, `credit_risk_score`, `credit_state`, `credit_warning`, `dealer_gamma_state`, `equity_drawer_active`, `gamma_risk_flag`, `gex_regime_score`, `horizon_pressure`, `lagging_sectors`, `leading_sectors`, `liquidity_pulse`, `liquidity_risk_flag`, `macro_active_conflict_flags`, `macro_age_hours`, `macro_confidence`, `macro_conflict_flags`, `macro_contract_version`, `macro_conviction_score`, `macro_data_quality`, `macro_execution_caution`, `macro_freshness_status`, `macro_generated_at_utc`, `macro_normalised_at_utc`, `macro_preferred_horizon`, `macro_quant_contract_version`, `macro_regime_label`, `macro_regime_sub_state`, `macro_resolved_conflict_flags`, `macro_source_path`, `net_liquidity_score`, `preferred_sectors`, `primary_bucket`, `rates_impulse`, `regime_distribution_bear`, `regime_distribution_bull`, `regime_distribution_neutral`, `regime_drift_status`, `risk_on_off_score`, `sector_rotation_state`, `sector_tilt_score`, `ticker_sector_alignment`, `ticker_sector_alignment_score`, `usd_state`, `vix_contango`, `vix_level`, `vix_regime_label`, `vix_regime_score`, `vix_structure_label`, `vol_mode`
- `macro_snapshot.json` → `_builder_metadata`, `as_of_utc`, `contract_version`, `coverage_missing`, `credit_risk_score`, `credit_state`, `data_coverage_ratio`, `dir_bias`, `extras`, `gex_available`, `gex_regime_score`, `horizon_routing`, `horizon_routing_complete`, `horizon_routing_enforcement`, `horizon_routing_required_buckets`, `liquidity_pulse`, `macro_conviction`, `macro_conviction_uncapped`, `macro_filter`, `macro_momentum_score`, `macro_quant_contract_version`, `macro_quant_packet`, `macro_regime_sub_state`, `net_liquidity_score`, `normalised_at_utc`, `notes`, `rates_impulse`, `regime_distribution`, `regime_distribution_source`, `regime_drift_interpretation`, `regime_drift_status`, `regime_label`, `regime_probability`, `regime_probability_uncapped`, `regime_state`, `regime_sub_state`, `report_date`, `risk_on_off_switch`, `rotation_detail`, `rotation_flag_as_of_utc`, `rotation_override`, `sector_avoid`, `sector_lead`, `sector_rotation`, `size_multiplier`, `source`, `trend_energy`, `trigger_required`, `truth_packet`, `usd_state`, `vix_regime_score`, `vix_spot`, `vol_mode`
- `options/options_intelligence_summary_{run_id}.json` → `armed`, `caution`, `cds_chain_telemetry`, `elapsed_seconds`, `execute`, `execution_permission`, `generated_utc`, `repair_selector_diagnostics`, `route_counts`, `run_id`, `signals_processed`, `signals_scoped`, `stand_down`, `top_execute`, `top_go_review`
- `options/options_summary.json` → `armed`, `caution`, `cds_chain_telemetry`, `elapsed_seconds`, `execute`, `execution_permission`, `generated_utc`, `repair_selector_diagnostics`, `route_counts`, `run_id`, `signals_processed`, `signals_scoped`, `stand_down`, `top_execute`, `top_go_review`
- `options/phantom_summary_{run_id}.json` → `hard_veto_respected_count`, `output_csv`, `promoted_count`, `rows_processed`, `run_id`, `score_max`, `score_mean`, `score_min`
- `pipeline_integrity_{run_id}.json` → `action_items`, `actuarial_fill_rate`, `actuarial_loaded_before_eil`, `eil_block_rate`, `eil_eod_mode`, `eil_total_rows`, `enrichment_merge_degraded`, `ev3_authority_mode`, `ev3_coverage_health`, `ev3_dominant_reason_code`, `ev3_dominant_reason_count`, `ev3_dominant_reason_share`, `ev3_expected_contract_rejections`, `ev3_expected_market_rejections`, `ev3_functional_health`, `ev3_production_authority`, `ev3_shadow_evaluation_coverage`, `ev3_shadow_health`, `ev3_shadow_rows_evaluated`, `ev3_system_defects`, `ev3_technical_health`, `execution_ready_count`, `final_pipeline_state`, `generated_utc`, `horizon_routing_present`, `macro_normalised_ok`, `manifest_permission`, `morning_capital_permission`, `morning_validation_command`, `pipeline_technical_health`, `pse_active`, `pse_capital_authority`, `pse_status`, `run_id`, `tier_a_count`, `tier_b_count`, `tier_c_count`, `v5_colab_decommissioned`
- `run_meta.json` → `baseline_commit_hash`, `canonical_run_id`, `contract_version`, `discovery_run_id`, `macro_data_quality`, `macro_freshness_status`, `macro_quant_packet_path`, `macro_regime_label`, `macro_snapshot_path`, `macro_source_path`, `msi_config_hash`, `msi_config_version`, `msi_feature_flags`, `operator_accepted_at_utc`, `operator_accepted_by`, `pinned_at_utc`, `pipeline_mode`, `run_kind`, `run_meta_schema_version`, `run_status`, `status_updated_at_utc`, `truth_packet_path`
- `superbrain/wall_break_summary_{run_id}.json` → `generated_at`, `grade_counts`, `producer`, `run_id`, `top_5`, `total_scored`, `wbs_avg`, `wbs_field_completeness_pct`, `wbs_max`, `wbs_valid`
- `truth_packet_run.json` → `conflicts`, `created_at_utc`, `direction`, `errors`, `fields`, `packet_status`, `run_id`, `run_mode`, `ticker`, `updated_at_utc`, `warnings`
- `vanguard/vanguard_run_summary.json` → `output_csv`, `packages_total`, `passed`, `reject_top_reasons`, `rejected`, `rejects_csv`, `run_id`
