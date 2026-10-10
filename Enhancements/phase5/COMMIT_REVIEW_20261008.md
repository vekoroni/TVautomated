# Commit review: uncommitted changes on avs-fix-001 (8 Oct 2026)

Nothing is staged. Files are staged **by name** only after ACK confirms each group (never `git add -A`/`-u`).
Attribution: this programme's files come from the build record; the other files carry the markers of the 6–7 Oct work (L3–L5, A1–A7, E12/E15, RW, S2-1/S2-3, PH, direction validation). **Mixed** = the file also carries other uncommitted work; git commits whole files, so a mixed file commits both.

## A. This programme (Phases 0–5, live-proving label) (100 files)

| File | Git | Note |
|---|---|---|
| `CLAUDE.md` | M |  |
| `Enhancements/decision_map/DISCOVERY_VANGUARD_REDESIGN_20261007.md` | ?? |  |
| `Enhancements/lean_path_test/` | ?? |  |
| `Enhancements/phase0/P0_DISCOVERY_RECALL_LOSSES.md` | ?? |  |
| `Enhancements/phase0/PHASE0_CHARACTERISATION_REPORT_20261007.md` | ?? |  |
| `Enhancements/phase0/backfill_receipts/daily_history_backfill_dry_run_20261007T221512Z.json` | ?? |  |
| `Enhancements/phase0/backfill_receipts/daily_history_backfill_execute_20261007T221941Z.json` | ?? |  |
| `Enhancements/phase0/p0_backfill_daily_history.py` | ?? |  |
| `Enhancements/phase0/p0_characterisation.json` | ?? |  |
| `Enhancements/phase0/p0_characterise.py` | ?? |  |
| `Enhancements/phase0/p0_duplicate_keys.json` | ?? |  |
| `Enhancements/phase0/p0_duplicate_keys.py` | ?? |  |
| `Enhancements/phase0/p0_recall_losses.py` | ?? |  |
| `Enhancements/phase0/p0_recall_losses_evidence.json` | ?? |  |
| `Enhancements/phase1/` | ?? |  |
| `Enhancements/phase2/` | ?? |  |
| `Enhancements/phase3/` | ?? |  |
| `Enhancements/phase4/` | ?? |  |
| `Enhancements/phase5/` | ?? |  |
| `avshunter/c0_run/canonical_manifest.py` | M |  |
| `avshunter/c0_run/thin_package.py` | M |  |
| `avshunter_discovery_ULTIMATE.py` | M | mixed: also carries other uncommitted work |
| `config/beh001_behaviour_v1.json` | M |  |
| `config/beh001_handoff_v1.json` | M |  |
| `config/dir002_vanguard_side_evidence_v1.json` | M |  |
| `contracts/candidate_record.py` | ?? |  |
| `contracts/direction_governance.py` | M | mixed: also carries other uncommitted work |
| `contracts/lab_control.py` | M | mixed: also carries other uncommitted work |
| `contracts/thesis_record.py` | ?? |  |
| `domain/descriptive_forecast_handoff.py` | M |  |
| `domain/opportunity_rank.py` | ?? |  |
| `domain/pretrade_focus.py` | M | mixed: also carries other uncommitted work |
| `domain/run_planning.py` | M |  |
| `domain/structure_behaviour/compression.py` | M |  |
| `domain/structure_behaviour/engine.py` | M |  |
| `domain/structure_behaviour/handoff_packet.py` | M |  |
| `domain/structure_behaviour/signals.py` | M |  |
| `domain/structure_behaviour/trigger_events.py` | ?? |  |
| `dropoff_audit.py` | M |  |
| `eod_candidate_engine.py` | M | mixed: also carries other uncommitted work |
| `execution_decision_engine.py` | M |  |
| `intelligence-lab/intelligence_lab.py` | M |  |
| `intelligence-lab/static/trade-card.js` | M | mixed: also carries other uncommitted work |
| `intelligence-lab/static/trade-summary.js` | M | mixed: also carries other uncommitted work |
| `intelligent_orchestrator.py` | M |  |
| `morning_gate.py` | M | mixed: also carries other uncommitted work |
| `scripts/avshunter_options_intelligence.py` | M | mixed: also carries other uncommitted work |
| `scripts/options_candidate_lane.py` | M |  |
| `tests/fixtures/phase0/` | ?? |  |
| `tests/test_avs_fix_002_stage1_closure.py` | M |  |
| `tests/test_avs_int001_horizon_red.py` | M | mixed: also carries other uncommitted work |
| `tests/test_avs_int001_scenario_evening_to_lab.py` | M | mixed: also carries other uncommitted work |
| `tests/test_avs_int001_scenario_horizon_parity.py` | M | mixed: also carries other uncommitted work |
| `tests/test_avs_lab_trade_summary.py` | M |  |
| `tests/test_avs_n1_morning_go_requires_trigger.py` | M |  |
| `tests/test_avs_target_source_label.py` | M |  |
| `tests/test_beh001_options_candidate_lane.py` | M |  |
| `tests/test_canonical_manifest_p1.py` | M |  |
| `tests/test_evening_thesis_decision.py` | M | mixed: also carries other uncommitted work |
| `tests/test_ila_selected_contract_identity.py` | M | mixed: also carries other uncommitted work |
| `tests/test_lab_governed_handoff.py` | M | mixed: also carries other uncommitted work |
| `tests/test_live_proving_run_condition.py` | ?? |  |
| `tests/test_p1_candidate_record.py` | ?? |  |
| `tests/test_p1_compression_episode.py` | ?? |  |
| `tests/test_p1_compression_single_owner.py` | ?? |  |
| `tests/test_p1_insufficient_daily_history_label.py` | ?? |  |
| `tests/test_p1_thesis_target_from_governing_candidate.py` | ?? |  |
| `tests/test_p2_thesis_step.py` | ?? |  |
| `tests/test_p3_trigger_events.py` | ?? |  |
| `tests/test_p3_trigger_layer_no_direction.py` | ?? |  |
| `tests/test_p3b_intraday_buildup.py` | ?? |  |
| `tests/test_p4_actuarial_no_invented_values.py` | ?? |  |
| `tests/test_p4_auction_not_measured.py` | ?? |  |
| `tests/test_p4_matching_state_parity.py` | ?? |  |
| `tests/test_p4_no_hidden_price_gate.py` | ?? |  |
| `tests/test_p4_no_run_clock_in_state.py` | ?? |  |
| `tests/test_p4_one_history_policy.py` | ?? |  |
| `tests/test_p4_side_block_timezone_seam.py` | ?? |  |
| `tests/test_p4_vanguard_context_only.py` | ?? |  |
| `tests/test_p5_dropoff_dispositions.py` | ?? |  |
| `tests/test_p5_go_readiness_from_thesis_events.py` | ?? |  |
| `tests/test_p5_intraday_buildup_population.py` | ?? |  |
| `tests/test_p5_lab_card_thesis.py` | ?? |  |
| `tests/test_p5_morning_repair_inside_thesis.py` | ?? |  |
| `tests/test_p5_one_ranking_owner.py` | ?? |  |
| `tests/test_p5_options_per_thesis.py` | ?? |  |
| `tests/test_p5_thesis_fields_carried.py` | ?? |  |
| `tests/test_p5_trigger_is_the_thesis_trigger.py` | ?? |  |
| `tests/test_phase0_characterisation.py` | ?? |  |
| `tests/test_phase0_duplicate_output_keys.py` | ?? |  |
| `tests/test_trigger_layer_governance.py` | M |  |
| `trigger_layer.py` | M | mixed: also carries other uncommitted work |
| `vanguard/config.py` | M | mixed: also carries other uncommitted work |
| `vanguard/core/actuarial_core_v7.py` | M |  |
| `vanguard/integration/orchestrator_adapter.py` | M |  |
| `vanguard/layer1_auction/auction_synthesizer.py` | M |  |
| `vanguard/layer2_statistical/actuarial_query.py` | M |  |
| `vanguard/layer2_statistical/state_calculator.py` | M |  |
| `vanguard/main.py` | M |  |
| `vanguard/schemas/state_outcomes_schema.py` | M |  |

## B. Other uncommitted work (6–7 Oct decisions in ACK_DECISIONS_SOURCE_OF_TRUTH.md) (57 files)

| File | Git | Note |
|---|---|---|
| `Enhancements/assessment/AVS_LAB_SOURCE_OF_TRUTH_20261006/` | ?? |  |
| `Enhancements/direction_evidence/DIRECTION_EDGE_STUDY_PREREG_20261007.md` | ?? |  |
| `Enhancements/direction_evidence/SHORT_HORIZON_DIRECTION_STUDY_PREREG_20261007.md` | ?? |  |
| `Enhancements/direction_evidence/TOP_DOWN_BIAS_STUDY_PREREG_20261007.md` | ?? |  |
| `Enhancements/direction_evidence/TOP_DOWN_BIAS_STUDY_RESULTS_20261007.md` | ?? |  |
| `Enhancements/direction_evidence/WP1_DIRECTION_AUDIT_PREREG_20261007.md` | ?? |  |
| `Enhancements/direction_evidence/direction_edge_study.py` | ?? |  |
| `Enhancements/direction_evidence/top_down_bias_study.py` | ?? |  |
| `Enhancements/direction_evidence/wp1_direction_audit.py` | ?? |  |
| `canonical_data/dynamic_options_probability.py` | M |  |
| `config/governed_constants_v1.json` | M |  |
| `contracts/opportunity_tier.py` | M |  |
| `contracts/selected_contract_economics.py` | M |  |
| `domain/anticipated_move.py` | M |  |
| `domain/long_option_execution.py` | M |  |
| `domain/option_contract_liquidity.py` | M |  |
| `domain/structure_behaviour/duration.py` | M |  |
| `domain/structure_behaviour/thesis_category.py` | M |  |
| `domain/structure_behaviour/trade_lane.py` | M |  |
| `execution_gate.py` | M |  |
| `execution_intelligence_runner.py` | M |  |
| `intelligence-lab/static/index.html` | M |  |
| `pipeline_interpreter/assessment_contract.py` | M |  |
| `pipeline_interpreter/evidence_resolver.py` | M |  |
| `regime_consensus.py` | M |  |
| `scripts/phantom_engine.py` | M |  |
| `tests/msi/test_flow.py` | M |  |
| `tests/test_avs_4b_evidence_runway.py` | M |  |
| `tests/test_avs_a1_aged_share_price.py` | ?? |  |
| `tests/test_avs_a2_a3_interpreter_age_disclosed.py` | ?? |  |
| `tests/test_avs_direction_unvalidated_label.py` | ?? |  |
| `tests/test_avs_e12_option_review.py` | ?? |  |
| `tests/test_avs_e15_spread_units.py` | ?? |  |
| `tests/test_avs_fix_001_w35_opportunity_tier.py` | M |  |
| `tests/test_avs_fix_002_runtime_adapters.py` | M |  |
| `tests/test_avs_governing_setup.py` | ?? |  |
| `tests/test_avs_l3_no_evidence_hold.py` | ?? |  |
| `tests/test_avs_l4_gex_display_only_gate.py` | ?? |  |
| `tests/test_avs_l5_monetisability_out_of_decisions.py` | ?? |  |
| `tests/test_avs_monetisability_anticipated_level.py` | ?? |  |
| `tests/test_avs_phantom_writes_own_fields.py` | ?? |  |
| `tests/test_avs_runway_no_estimate_and_hold_lineage.py` | ?? |  |
| `tests/test_avs_runway_pooled_and_vol_fallback.py` | ?? |  |
| `tests/test_avs_s2_3_strike_level.py` | ?? |  |
| `tests/test_avs_sot_s0_characterisation.py` | ?? |  |
| `tests/test_avs_step5_move_pays.py` | M |  |
| `tests/test_contract_selection_horizon_not_a_gate.py` | M |  |
| `tests/test_contract_value_selection.py` | M |  |
| `tests/test_eod_options_research_handoff.py` | M |  |
| `tests/test_ev3_options_handoff.py` | M |  |
| `tests/test_governed_dte_policy_alignment.py` | M |  |
| `tests/test_lab_legacy_ev_retired.py` | M |  |
| `tests/test_morning_marketdata_stock_price.py` | M |  |
| `tests/test_msi_interpreter_handoff.py` | M |  |
| `tests/test_options_liquidity_lifecycle.py` | M |  |
| `tests/test_options_liquidity_morning_lab.py` | M |  |
| `tests/test_pretrade_focus_handoff.py` | M |  |

## C. Unattributed or deleted: confirm before staging (69 files)

| File | Git | Note |
|---|---|---|
| `.claude/` | ?? | no marker: confirm owner |
| `.testdeps/` | ?? | no marker: confirm owner |
| `AVSHUNTER_Document_Review_and_Decision_Register.docx` | ?? | no marker: confirm owner |
| `Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/calculation_condition_register.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/dependency_call_register.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/backtest/activity_tournament/s_act_model_scores.csv.gz` | ?? | no marker: confirm owner |
| `Enhancements/backtest/contract_execution_tournament/cex_selected_rows.csv.gz` | ?? | no marker: confirm owner |
| `Enhancements/colab/avshunter_fred_monitor_v2_5.py` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/DIRECTION_EDGE_STUDY_RESULTS_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/MAGNITUDE_AND_STRENGTH_STUDY_PREREG_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/MAGNITUDE_AND_STRENGTH_STUDY_RESULTS_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/SHORT_HORIZON_DIRECTION_STUDY_RESULTS_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/WP1_DIRECTION_AUDIT_RESULTS_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/direction_edge_study_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/earnings/` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/magnitude_posthoc_normal_vol.py` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/magnitude_posthoc_normal_vol_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/magnitude_strength_study.py` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/magnitude_strength_study_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/short_horizon_direction_study.py` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/short_horizon_direction_study_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/survivorship/` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/top_down_bias_study_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/wp1_direction_audit_20261007.json` | ?? | no marker: confirm owner |
| `Enhancements/direction_evidence/~$RECTION_EDGE_STUDY_RESULTS_20261007.md` | ?? | no marker: confirm owner |
| `Enhancements/gpt_era/` | ?? | no marker: confirm owner |
| `Enhancements/macro_board_replay/` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/2026-10-02/outcome_report.json` | M | no marker: confirm owner |
| `Enhancements/outcomes/2026-10-02/outcome_report.md` | M | no marker: confirm owner |
| `Enhancements/outcomes/2026-10-05/` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v2/candidates.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v3/candidates.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v4/candidates.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v4/duration_records.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v4_holdout/candidates.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v4_holdout/duration_records.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v5/duration_records.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/eval_v5_holdout/duration_records.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/intraday_pilot/` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/intraday_v1/records.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/replay_v1.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/replay_v2.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/beh001/uncapped_v1.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/dir002/panel_v1.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/dir002/population_mirror_20260929.jsonl` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/intraday_backfill/intraday_backfill_20250902_20260903_shard1of3_receipt.json` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/intraday_backfill/intraday_backfill_20250902_20260903_shard2of3_receipt.json` | ?? | no marker: confirm owner |
| `Enhancements/outcomes/intraday_backfill/intraday_backfill_20250902_20260903_shard3of3_receipt.json` | ?? | no marker: confirm owner |
| `Enhancements/volatility_evidence/` | ?? | no marker: confirm owner |
| `audit/AVS_SOR001_BUILD_RECEIPT_20260927.md` | ?? | no marker: confirm owner |
| `audit/AVS_TEV001_BUILD_IN_PROGRESS_20260927.md` | ?? | no marker: confirm owner |
| `audit/AVS_TEV001_DESCRIPTIVE_PATH_BUILD_RECEIPT_20260927.md` | ?? | no marker: confirm owner |
| `audit/AVS_TEV001_S0_BASELINE_20260927.md` | ?? | no marker: confirm owner |
| `audit/AVS_TEV001_STRUCTURAL_COHORT_20260927.md` | ?? | no marker: confirm owner |
| `audit/avs_tev001_research_ev_canary.py` | ?? | no marker: confirm owner |
| `audit/avs_tev001_s0_support_audit.py` | ?? | no marker: confirm owner |
| `audit/avs_tev001_structural_cohort.py` | ?? | no marker: confirm owner |
| `audit/intelligence_lab/` | ?? | no marker: confirm owner |
| `audit/interpreter_report_failures/` | ?? | no marker: confirm owner |
| `audit/macro_input/` | ?? | no marker: confirm owner |
| `audit/verify/` | ?? | no marker: confirm owner |
| `contracts/macro_enrichment_delta.py` | M | no marker: confirm owner |
| `scripts/run_phantom.py` | D | deleted (ACK 7 Oct PH: dead run_phantom removed) |
| `tests/test_avs_fix_001_w34_timevalue_monetisability.py` | M | no marker: confirm owner |
| `tests/test_ev3_orchestrator_order.py` | M | no marker: confirm owner |
| `tests/test_macro_enrichment_snapshot.py` | ?? | no marker: confirm owner |
| `tests/test_morning_gate_contract_repair.py` | M | no marker: confirm owner |
| `tests/test_selected_contract_economics.py` | M | no marker: confirm owner |
| `tests/test_vanguard_reference_input_p2.py` | M | no marker: confirm owner |

## Known state before commit

- Regression: 190 files for Phase 5.4 plus `tests/msi/test_functionality.py` and `tests/msi/test_logic.py` pass. One failure: `test_b1_shadow_valuer_forecast_source` (group B runway change RW; its fixture has no runway evidence).
- `test_avs_int001_stage0` passes only once `contracts/thesis_record.py` and `domain/opportunity_rank.py` are committed.
- ACK SEQ decision: commit after the live run.
