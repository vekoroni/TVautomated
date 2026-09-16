# Track M9 — Data efficiency: field census (DISCOVERY)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
This is a DISCOVERY track: it describes and measures. It carries no verdict vocabulary and no severity. Findings are `DISC-F-M9-<n>` placeholders. `outcome_relation = NOT_TESTABLE` for every field (no resolved outcomes exist on these runs) — stated once here, not repeated per field. Nothing here authorises a trade; anything signal-like is RESEARCH_ONLY.

Runs used: primary `data/output/runs/20260911_115904` (TEST condition, `pipeline_mode = MORNING_VALIDATION`, produced by pre-remediation code 00baa2b-dirty). A census needs no comparison run.
Data sources: `audit/td/AVS-TD-001/probes/p03_artefact_inventory_raw.csv` (95 primary-run rows = 92 tabular files/representatives + 3 non-tabular txt/md); every CSV, JSONL, parquet and JSON the run wrote; the two families (`packages/`, `validation_events/`) on one representative each; production python corpus (554 files, 215,386 lines) loaded once for producer/consumer resolution.
Probes (all in `audit/td/AVS-TD-001/probes/`):
- `p20_M9_field_census.py` — the census (runtime 979 s, log `p20_M9_run.log`). Outputs: `p20_M9_field_census.csv` (61,870 artefact×field rows, 4,231 distinct field tokens), `p20_M9_artefact_aggregate.csv` (95 rows), `p20_M9_duplicate_pairs.csv` (4,939), `p20_M9_decision_reads.csv` (2,056 read sites), `p20_M9_mtrack_field_map.csv`, `p20_M9_packages_representative.csv` (16,341 leaves).
- `p21_M9_minset_refine.py` — post-processor over the p20 CSVs: read-kind labels per decision read, refined minimum sets, stale-reader impact, family tables, constants, ambiguous units, M-track summary, packages families (`p21_M9_*.csv`, `p21_M9_stdout.txt`).
- `p22_M9_alias_chains.py` — AST pass collapsing `_first_value(row, "a", "b", …)` / `_first(row, …)` fallback chains into logical inputs (`p22_M9_alias_chains.csv`, `p22_M9_core_logical_inputs.csv`).
Every number below is re-checkable from those files.

## Method
- Load: CSV `pandas.read_csv(low_memory=False)`; parquet via pyarrow; JSONL per line; JSON flattened to dotted leaf paths (`a.b[].c`; a list of scalars is one JSON string); JSON > 100 MB (`final_opportunity_book_<run>.json`, 142 MB) keys-only from the first 1 MB (496 keys). Nested list expansion is capped at 100,000 observations per path (affects only `contracts_tested[].*`, see Deviations).
- Per field: fill_rate = share non-null and non-empty; n_distinct on string form; is_constant = ≥ 2 non-null and 1 distinct; near_zero_variance = numeric std == 0 or std/|mean| < 1e-6; duplicate_of = another column of the same artefact with an identical content hash (constants and all-null excluded from pairing); unit inferred from name tokens (pct/percent/bps → percent; frac/ratio/prob/rate/iv/vol/sigma/delta/… → fraction; price/strike/bid/ask/oi/volume/dte/… → absolute), AMBIGUOUS when name and range disagree or when a spread/vol/move/iv/sigma field straddles 1.
- Producer/consumer: the corpus excludes tests/, backups/, _attic/, audit/, Archive/, venv/, __pycache__ and additionally data/, dropbox/, logs/, dot-directories. A producer is a quoted-key write context (`["k"] =`, `"k":` in a dict literal, `setdefault("k"`) or attribute assignment; a consumer is any other quoted or attribute occurrence; the grep token for a JSON path is its leaf key. `NO_PRODUCER` therefore means "the key is never a python string literal in a write context", which for provider/macro JSON payloads is expected.
- Classification (p20): `LOAD_BEARING` = ≥ 1 quoted read inside a decision/authority range — execution_gate.py (whole); morning_gate.py 216–470 (`_ensure_governed_direction_record` … `_apply_thesis_direction_guard`), 1518–1890 (`_check_bond_macro` … `_morning_liquidity_lifecycle`), 2076–2744 (`run_gate`); contracts/opportunity_tier.py (whole); contracts/lab_control.py 1707–2382 (`duplicate_open_trade`, `_morning_lab_alignment`, `_resolve_execution_gate_authority`, `resolve_lab_tradeability`, `apply_lab_resolution`, `_enforce_olm_lab_guard`, `_enforce_execution_authority_lab_guard`) and 3246–3386 (`_derive_opportunity_tier`, `_recompute_governed_lab_fields`); eod_candidate_engine.py 443–730, 850–1010, 1044–1300, 1318–1560, 1950–3203 (`_options_research_route` … `classify_tier`, `build_candidate_manifest` incl. the manifest mask at 2853–2867); orchestrator/dynamic_dispatcher.py 84–158 (`resolve_accepted_thesis`); contracts/direction_governance.py 390–511 (`validate_direction_record`); domain/option_liquidity_execution_guard.py 84–193 (`evaluate_olm_execution_guard`); domain/execution_authority.py (whole); domain/dynamic_options_ranking.py and canonical_data/dynamic_options_production.py (whole). `ADVISORY_USED` = read anywhere else in the corpus. `DEAD` = unread and (constant or all-null). `PRODUCED_UNREAD` = unread and varying. `AMBIGUOUS_UNIT` is an overlay (`classification_with_unit_overlay`).
- Read kinds (p21) on each decision-range read line: `PASS` (output dict key `"k": …` or same-key copy), `BRANCH` (condition / comparison / boolean / arithmetic / min-max-abs), `FETCH` (assigned to a local or passed as a call argument, including the bare `"k",` argument lines of multi-line `_first_value` calls), `OTHER`.

## Lab book census — intelligence_lab/lab_signal_book_v3.csv (19 rows × 502 fields)
| measure | actual | expectation (expectations.md, M9 row) | gap |
|---|---|---|---|
| fields | 502 | 502 | 0 |
| fill rate < 50 % | 80 fields (15.9 %), of which 62 all-null | ≥ 30 % | 14.1 pts below the expectation |
| constants (1 distinct non-null) | 200 fields (39.8 %); 101 of them also constant across the 1,444-row books; 99 constant only within the 19 GO rows | ≥ 15 % | above the expectation |
| near-zero variance (numeric) | 46 | — | — |
| duplicate columns | 58 fields (41 pairs, `p20_M9_duplicate_pairs.csv`) | — | — |
| UNREAD (no production reader) | 19 fields (3.8 %) | ≥ 40 % | 36 pts below the expectation |
| AMBIGUOUS_UNIT | 15 fields | ≥ 20 | 5 below the expectation |
| NO_PRODUCER | 0 | — | every Lab-book name is a python write literal |
| minimum set for current decisions | 34 fields at the narrowest tier (19 of them in the Lab book); 231 / 203 logical at the CORE tier (93 / 86 in the Lab book); 365 at the broad tier | ≤ 40 fields | met only at the narrowest tier; see Minimum field sets |

Classification (p20 usage): LOAD_BEARING 243 · ADVISORY_USED 240 · PRODUCED_UNREAD 8 · DEAD 11. With the unit overlay: LOAD_BEARING 236 · ADVISORY_USED 232 · AMBIGUOUS_UNIT 15 · PRODUCED_UNREAD 8 · DEAD 11.
Units: text 267 · all_null 62 · absolute 61 · unknown 52 · fraction 18 · percent 15 · AMBIGUOUS 15 · unknown(range ≤ 1) 12.
UNREAD (19): DEAD 11 = `doi_governed_contract_identity_reason`, `execution_quote_advisory_only`, `execution_quote_affects_thesis`, `execution_quote_human_confirmation_required`, `execution_quote_refresh_required`, `execution_quote_status`, `lab_status_banner`, `model_final_action`, `validation_data_status`, `validation_profile_evidence_state`, `validation_transition`; PRODUCED_UNREAD 8 = `doi_governed_contract_parsed_expiry/_side/_strike`, `execution_quote_timestamp_utc`, `validation_current_price`, `validation_evidence_cutoff_utc`, `validation_gap_pct`, `validation_reason`. (`validation_profile_evidence_state` is read by the excluded `dropbox/macro/coaching/build_trade_dossiers.py`; the other 18 have no reader in dropbox/ either.)
All-null (62): `wbs_*` (15), `underlying_nbbo_*` (8), `doi_*` (10: DOI tables inactive on this run — `doi_projection_state = DATA_UNAVAILABLE`), `catalyst_date/_direction_bias/_event_status/_overlay`, `contract_repair_alternative_used/_live_action`, `alternative_contract_attempts`, `direction_resolution_confidence`, `economics_mismatch_reason`, `execution_lock_reason`, `lab_actionable_handoff_member`, `lab_coherence_status`, `liquidity_score`, `macro_directional_pressure`, `monetisability_hard_execution_authority`, `monetisability_valuation_basis`, `morning_contract_spread_pct`, `pcr_vol`, `position_size_display`, `prep_permission`, `quote_source`, `rr_evaluation_id`, `rr_recompute_reason`, `selected_structure_hydration_reason`, `target_unresolved_reason`, `trigger_price`, `trigger_price_source`, `usmi_alignment_priority`.
Duplicate groups of note (identical content on this run): direction ×5 (`direction`, `final_direction`, `governed_direction`, `discovery_direction_preliminary`, `doi_governed_contract_parsed_side` = `canonical_direction`); selected contract ×7 (`contract_symbol`, `doi_governed_contract_symbol`, `execution_viability_contract_symbol`, `monetisability_contract_symbol`, `morning_selected_contract_symbol`, `rr_contract_symbol` = `selected_contract_symbol`); ask ×5 (`current_contract_ask`, `execution_viability_ask`, `monetisability_entry_ask`, `morning_contract_ask`, `rr_entry_debit_per_share` = `contract_ask`); mid ×4; bid ×3; quote timestamp ×5 (`execution_quote_timestamp_utc`, `morning_quote_timestamp_utc`, `quote_as_of`, `validation_evidence_cutoff_utc` = `current_quote_timestamp_utc`); target ×4 (`structural_target`, `target_price`, `target_zone` = `monetisability_structural_target_spot`); spot ×2 (`signal_price`, `underlying_price` = `scanner_price`); `spread_pct` = `current_contract_spread_pct` = `execution_viability_spread_pct`; `hold_window` = `time_horizon` = `hold_period`; `option_gain_at_target` = `monetisability_target_profit_per_share`; `priority_rank` = `lab_rank`; `sector` = `gics_sector_norm` = `gics_sector`.

## Top-N export
There is no file named "Top 50". `trades/execution_actionable_<run>.csv` (19 rows × 1,006 fields) carries exactly the 19 Lab-book tickers (set-equal), all `final_action = BUY_SMALL`; 299 fields are shared with the Lab book, 707 are actionable-only, 203 Lab-only. `core_intel/core_intel_menu_<run>.json` is a 3-item digest (`methodology = "Top-3 by conservative rank-score (Tier 1 preferred, then Tier 0)"`, `pool_counts = {tier1: 740, tier0: 782, pool: 740}`, 52 keys per item). **This track treats `execution_actionable` as the Top-N export** (it is the execution-gate output the Lab book is cut from) and reports `core_intel_menu` as a separate 3-row digest. Both are censused below.
`execution_actionable` census: 1,006 fields; fill < 50 % 175 (97 all-null); constants 415 (41.3 %); duplicates 125; UNREAD 234 (23.3 %); AMBIGUOUS_UNIT 41; LOAD_BEARING 436 · ADVISORY_USED 348 · PRODUCED_UNREAD 89 · DEAD 133.
`core_intel_menu` census: 59 flattened fields; constants 18; UNREAD 7; AMBIGUOUS 4; LOAD_BEARING 9 · ADVISORY_USED 43 · PRODUCED_UNREAD 6 · DEAD 1.

## Per artefact family — counts by classification (p21_M9_family_classification.csv)
| family | artefacts | fields | LOAD_BEARING | ADVISORY_USED | PRODUCED_UNREAD | DEAD | AMBIGUOUS_UNIT | constants | all-null | fill<50% | duplicates | UNREAD | NO_PRODUCER |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| packages/ (family, rep AAPL of 1,572) | 1 | 16,341 | 1,303 | 7,041 | 7,397 | 600 | 12 | 705 | 667 | 667 | 776 | 7,997 | 8,094 |
| interpreter/ | 4 | 10,182 | 820 | 4,510 | 4,294 | 558 | 23 | 956 | 365 | 383 | 698 | 4,852 | 4,995 |
| run root (9 json/csv) | 9 | 6,955 | 568 | 3,108 | 2,993 | 286 | 6 | 355 | 266 | 266 | 249 | 3,279 | 3,330 |
| options/ | 15 | 5,926 | 1,567 | 2,453 | 1,565 | 341 | 236 | 1,298 | 322 | 947 | 1,038 | 1,924 | 1,725 |
| core_intel/ | 3 | 4,931 | 281 | 2,139 | 2,237 | 274 | 14 | 371 | 134 | 140 | 236 | 2,511 | 2,578 |
| horizon/ | 5 | 3,918 | 943 | 1,854 | 696 | 425 | 63 | 659 | 1,350 | 545 | 501 | 1,121 | 1,091 |
| superbrain/ | 4 | 3,033 | 819 | 1,253 | 779 | 182 | 151 | 726 | 141 | 462 | 504 | 970 | 826 |
| morning_validation/ | 9 | 2,749 | 1,408 | 883 | 276 | 182 | 106 | 725 | 317 | 530 | 211 | 494 | 57 |
| trades/ | 3 | 2,000 | 876 | 672 | 224 | 228 | 91 | 676 | 165 | 345 | 217 | 476 | 53 |
| intelligence_lab/ | 5 | 1,956 | 971 | 946 | 28 | 11 | 47 | 398 | 152 | 262 | 144 | 39 | 0 |
| execution/ | 1 | 1,191 | 314 | 511 | 289 | 77 | 59 | 284 | 48 | 189 | 187 | 371 | 313 |
| discovery/ | 4 | 940 | 183 | 585 | 121 | 51 | 11 | 325 | 123 | 234 | 24 | 172 | 63 |
| ev3_shadow/ | 8 | 627 | 88 | 211 | 234 | 94 | 10 | 84 | 60 | 237 | 7 | 328 | 98 |
| vanguard/ | 3 | 506 | 44 | 240 | 190 | 32 | 8 | 117 | 35 | 53 | 141 | 222 | 245 |
| diagnostics/ | 12 | 433 | 78 | 205 | 117 | 33 | 6 | 19 | 44 | 128 | 4 | 150 | 60 |
| market_profile/ | 1 | 75 | 5 | 28 | 14 | 28 | 0 | 33 | 1 | 1 | 0 | 42 | 26 |
| catalysts/ | 2 | 53 | 14 | 35 | 3 | 1 | 0 | 6 | 2 | 12 | 2 | 5 | 2 |
| validation_events/ (family, rep 1 of 1,444) | 1 | 25 | 11 | 13 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 1 | 1 |
| qomega/ | 1 | 17 | 9 | 4 | 3 | 1 | 5 | 1 | 3 | 4 | 0 | 4 | 0 |
| canonical/ | 1 | 12 | 2 | 9 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |

Family representatives: `packages/AAPL.package.json` (16,341 leaves under 44 top-level keys; the four macro payload blocks `macro` 7,318, `macro_snapshot` 5,095, `truth_packet` 2,037, `macro_quant_packet` 1,293 hold 96 % of the leaves and 99 % of the family's UNREAD; `discovery` 309 leaves (58 LOAD_BEARING); `options_contract` 25 leaves of which 23 all-null on the representative — only `dte` and `contract_type` are filled; `p21_M9_packages_families.csv`). `validation_events/validation_00153011975a4fd6de564a98.json`: 25 flattened fields, 11 LOAD_BEARING (`thesis_id`, `ticker`, `direction`, `current_price`, `evidence_cutoff_utc`, `reason`, `execution_gate_result.{final_action, executable_now, capital_permission, morning_execution_permission, morning_transition_state}`), 1 all-null (`developing_profile_evidence_id`), 1 PRODUCED_UNREAD (`option_quote_observation_id`).

## Aggregate
Grand total (92 tabular artefacts incl. the two representatives): 61,870 artefact×field rows over 4,231 distinct field tokens. LOAD_BEARING 10,304 (16.7 %) · ADVISORY_USED 26,700 (43.2 %) · PRODUCED_UNREAD 21,462 (34.7 %) · DEAD 3,404 (5.5 %). AMBIGUOUS_UNIT overlay 848 rows (166 distinct tokens). Constants 7,738 (12.5 %); all-null 4,196 (6.8 %); fill < 50 % 5,406 (8.7 %); UNREAD 24,959 (40.3 %); NO_PRODUCER 23,557 (38.1 %, almost entirely JSON leaves of macro/provider payloads); duplicates 4,939 (8.0 %).
Excluding the two families: 45,504 rows over 90 artefacts — LOAD_BEARING 8,990 (19.8 %) · ADVISORY_USED 19,646 (43.2 %) · PRODUCED_UNREAD 14,064 (30.9 %) · DEAD 2,804 (6.2 %); AMBIGUOUS 836; constants 7,033; all-null 3,528; fill < 50 % 4,738; UNREAD 16,961 (37.3 %); duplicates 4,163.
The row-level decision books have low UNREAD (Lab book 3.8 %, final_opportunity_book 0 %, lab_triage_view 0 %) while the wide downstream books are 23–35 % UNREAD (execution_gated 23.3 %, execution_actionable 23.3 %, morning_validated_trades 23.1 %, options_intelligence 34.3 %, execution_v3_5 31.2 %) and the JSON payload artefacts 49–56 % (macro_snapshot 48.9 %, interpreter_macro_context 50.6 %, core_intel_dossiers 51.4 %, macro_quant_packet 56.2 %).

### Per artefact (rows = pandas row count; fields; fill<50%; const; dup; UNREAD; AMB = ambiguous unit; LB/ADV/PU/DEAD)
| artefact | rows | fields | fill<50% | const | dup | UNREAD | AMB | LB | ADV | PU | DEAD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| completed_thesis_receipt_inv_2d8d63d14e8018413a185773.json | 5 | 18 | 2 | 1 | 0 | 0 | 0 | 5 | 13 | 0 | 0 |
| final_run_manifest.json | 1 | 119 | 15 | 0 | 0 | 12 | 0 | 32 | 75 | 11 | 1 |
| macro_quant_packet.json | 15 | 1293 | 33 | 0 | 13 | 726 | 0 | 101 | 466 | 717 | 9 |
| macro_snapshot.json | 15 | 5095 | 171 | 351 | 236 | 2492 | 6 | 336 | 2267 | 2219 | 273 |
| pipeline_integrity.json | 1 | 51 | 0 | 0 | 0 | 32 | 0 | 2 | 17 | 32 | 0 |
| run_meta.json | 1 | 54 | 0 | 0 | 0 | 9 | 0 | 7 | 38 | 9 | 0 |
| score_integrity.json | 1 | 17 | 3 | 0 | 0 | 6 | 0 | 1 | 10 | 3 | 3 |
| trigger_layer_summary.csv | 1572 | 14 | 2 | 3 | 0 | 0 | 0 | 9 | 5 | 0 | 0 |
| truth_packet_run.json | 1 | 294 | 40 | 0 | 0 | 2 | 0 | 75 | 217 | 2 | 0 |
| canonical/cds3_discovery_publication.json | 1 | 12 | 0 | 0 | 0 | 1 | 0 | 2 | 9 | 1 | 0 |
| catalysts/catalyst_truth.csv | 1575 | 32 | 11 | 5 | 1 | 0 | 0 | 10 | 22 | 0 | 0 |
| catalysts/catalyst_truth_summary.json | 9 | 21 | 1 | 1 | 1 | 5 | 0 | 4 | 13 | 3 | 1 |
| core_intel/core_intel_dossiers.json | 1522 | 4858 | 137 | 353 | 236 | 2496 | 10 | 270 | 2092 | 2223 | 273 |
| core_intel/core_intel_export_summary.json | 1 | 14 | 1 | 0 | 0 | 8 | 0 | 2 | 4 | 8 | 0 |
| core_intel/core_intel_menu.json | 3 | 59 | 2 | 18 | 0 | 7 | 4 | 9 | 43 | 6 | 1 |
| diagnostics/dropoff_audit.csv | 3320 | 129 | 112 | 14 | 4 | 86 | 5 | 12 | 31 | 59 | 27 |
| diagnostics/dropoff_audit.json | 1 | 71 | 2 | 0 | 0 | 11 | 0 | 10 | 50 | 11 | 0 |
| diagnostics/handoff_contract_audit.csv | 143 | 11 | 1 | 0 | 0 | 5 | 0 | 2 | 4 | 5 | 0 |
| diagnostics/handoff_contract_audit.json | 2 | 30 | 2 | 5 | 0 | 5 | 0 | 6 | 19 | 2 | 3 |
| diagnostics/intraday_regime_watchdog.json | 1 | 17 | 6 | 0 | 0 | 4 | 0 | 2 | 11 | 1 | 3 |
| diagnostics/market_breadth_diagnostic.json | 3 | 41 | 0 | 0 | 0 | 10 | 1 | 12 | 19 | 10 | 0 |
| diagnostics/msi_identity_preflight.json | 1 | 8 | 1 | 0 | 0 | 3 | 0 | 2 | 3 | 3 | 0 |
| diagnostics/msi_production_readiness.json | 1 | 26 | 3 | 0 | 0 | 6 | 0 | 4 | 16 | 6 | 0 |
| diagnostics/msi_reconciliation.json | 1 | 13 | 0 | 0 | 0 | 6 | 0 | 3 | 4 | 6 | 0 |
| diagnostics/outcome_maturation.json | 1 | 17 | 1 | 0 | 0 | 3 | 0 | 3 | 11 | 3 | 0 |
| diagnostics/read_only_market_context.json | 1 | 9 | 0 | 0 | 0 | 2 | 0 | 1 | 6 | 2 | 0 |
| diagnostics/uat_audit_report.json | 1 | 61 | 0 | 0 | 0 | 9 | 0 | 21 | 31 | 9 | 0 |
| discovery/discovery_candidates_cds3.csv | 1572 | 309 | 77 | 104 | 7 | 57 | 4 | 58 | 194 | 42 | 15 |
| discovery/discovery_candidates_ultimate.csv | 1572 | 338 | 88 | 109 | 11 | 57 | 4 | 67 | 214 | 42 | 15 |
| discovery/discovery_lifecycle.csv | 3320 | 7 | 3 | 1 | 0 | 1 | 0 | 2 | 4 | 0 | 1 |
| discovery/external_intel_review_candidates.csv | 47 | 286 | 66 | 111 | 6 | 57 | 3 | 56 | 173 | 37 | 20 |
| ev3_shadow/ev3_authority_overlay.csv | 1444 | 78 | 58 | 22 | 2 | 47 | 3 | 13 | 18 | 36 | 11 |
| ev3_shadow/ev3_calibration_readiness.json | 1 | 18 | 1 | 0 | 0 | 11 | 0 | 1 | 6 | 10 | 1 |
| ev3_shadow/ev3_shadow_phase_status.json | 1 | 178 | 1 | 0 | 0 | 67 | 0 | 19 | 92 | 66 | 1 |
| ev3_shadow/ev3_stage1_contract_evaluations.parquet | 2430 | 66 | 55 | 16 | 1 | 41 | 2 | 12 | 13 | 30 | 11 |
| ev3_shadow/ev3_stage1_shadow_audit.json | 1 | 71 | 1 | 0 | 0 | 21 | 0 | 7 | 43 | 20 | 1 |
| ev3_shadow/ev3_stage1_shadow_ranked.csv | 207 | 72 | 5 | 20 | 2 | 47 | 2 | 12 | 13 | 35 | 12 |
| ev3_shadow/ev3_stage1_shadow_rejections.csv | 1011 | 72 | 58 | 10 | 0 | 47 | 0 | 12 | 13 | 1 | 46 |
| ev3_shadow/ev3_stage1_shadow_results.parquet | 1444 | 72 | 58 | 16 | 2 | 47 | 3 | 12 | 13 | 36 | 11 |
| execution/execution_v3_5.csv | 1444 | 1191 | 189 | 284 | 187 | 371 | 59 | 314 | 511 | 289 | 77 |
| horizon/horizon_11_20d.csv | 0 | 966 | 0 | 0 | 0 | 279 | 0 | 228 | 459 | 0 | 279 |
| horizon/horizon_1_5d.csv | 319 | 966 | 117 | 217 | 172 | 279 | 26 | 228 | 459 | 228 | 51 |
| horizon/horizon_6_10d.csv | 937 | 966 | 141 | 208 | 171 | 279 | 26 | 228 | 459 | 232 | 47 |
| horizon/horizon_blocked.csv | 188 | 966 | 287 | 234 | 158 | 279 | 11 | 228 | 459 | 231 | 48 |
| horizon/horizon_summary.json | 1 | 54 | 0 | 0 | 0 | 5 | 0 | 31 | 18 | 5 | 0 |
| intelligence_lab/final_opportunity_book.csv | 1444 | 474 | 91 | 99 | 43 | 0 | 16 | 241 | 233 | 0 | 0 |
| intelligence_lab/final_opportunity_book.json (keys only, first 1 MB) | 0 | 496 | 0 | 0 | 0 | 16 | 0 | 242 | 238 | 16 | 0 |
| intelligence_lab/lab_signal_book_v3.csv | 19 | 502 | 80 | 200 | 58 | 19 | 15 | 243 | 240 | 8 | 11 |
| intelligence_lab/lab_signal_book_v3.manifest.json | 1 | 11 | 0 | 0 | 0 | 4 | 0 | 4 | 3 | 4 | 0 |
| intelligence_lab/lab_triage_view.csv | 1444 | 473 | 91 | 99 | 43 | 0 | 16 | 241 | 232 | 0 | 0 |
| interpreter/handoff_manifest.json | 4 | 23 | 0 | 0 | 0 | 3 | 0 | 5 | 15 | 3 | 0 |
| interpreter/interpreter_evidence_bundle_v1.jsonl | 19 | 620 | 85 | 263 | 105 | 30 | 16 | 275 | 315 | 15 | 15 |
| interpreter/interpreter_macro_context.json | 15 | 9511 | 297 | 693 | 593 | 4816 | 7 | 537 | 4158 | 4274 | 542 |
| interpreter/macro_ticker_context_manifest.json | 1 | 28 | 1 | 0 | 0 | 3 | 0 | 3 | 22 | 2 | 1 |
| market_profile/completed_profile_summary.json | 87 | 75 | 1 | 33 | 0 | 42 | 0 | 5 | 28 | 14 | 28 |
| morning_validation/direction_transition_matrix.csv | 4 | 7 | 0 | 1 | 2 | 0 | 0 | 7 | 0 | 0 | 0 |
| morning_validation/eod_dropoff_audit.csv | 1444 | 141 | 17 | 12 | 17 | 0 | 10 | 141 | 0 | 0 | 0 |
| morning_validation/missed_opportunity_shadow_book.csv | 0 | 67 | 0 | 0 | 0 | 0 | 0 | 67 | 0 | 0 | 0 |
| morning_validation/morning_candidates.csv | 1444 | 674 | 143 | 172 | 51 | 93 | 30 | 352 | 241 | 57 | 24 |
| morning_validation/morning_gate_summary.json | 1 | 42 | 1 | 0 | 0 | 27 | 0 | 7 | 8 | 27 | 0 |
| morning_validation/morning_handoff_summary.json | 4 | 183 | 6 | 1 | 0 | 61 | 0 | 55 | 67 | 59 | 2 |
| morning_validation/morning_validated_trades.csv | 1444 | 991 | 228 | 270 | 95 | 229 | 51 | 428 | 346 | 118 | 99 |
| morning_validation/regime_watch.csv | 5 | 636 | 135 | 269 | 46 | 84 | 14 | 343 | 221 | 15 | 57 |
| morning_validation/ws2_trigger_rank_audit.csv | 1444 | 8 | 0 | 0 | 0 | 0 | 1 | 8 | 0 | 0 | 0 |
| options/contract_rejection_log.csv | 974 | 9 | 3 | 1 | 0 | 0 | 0 | 2 | 7 | 0 | 0 |
| options/contracts_tested.jsonl (1,218 records; nested lists capped at 100,000) | 100000 | 35 | 6 | 4 | 5 | 1 | 5 | 11 | 23 | 1 | 0 |
| options/dynamic_options_intelligence.json | 38 | 25 | 0 | 3 | 0 | 5 | 0 | 6 | 14 | 4 | 1 |
| options/governed_direction_records.jsonl | 1444 | 15 | 1 | 4 | 2 | 0 | 0 | 15 | 0 | 0 | 0 |
| options/options_blocked_review.csv | 422 | 751 | 324 | 178 | 138 | 247 | 23 | 204 | 303 | 186 | 58 |
| options/options_candidates_ranked.csv | 1444 | 751 | 69 | 170 | 143 | 247 | 33 | 204 | 303 | 202 | 42 |
| options/options_intelligence.csv | 1444 | 857 | 134 | 197 | 146 | 294 | 36 | 226 | 340 | 238 | 53 |
| options/options_intelligence_pre_ev3_authority.csv | 1444 | 751 | 65 | 170 | 143 | 247 | 33 | 204 | 303 | 202 | 42 |
| options/options_intelligence_latest.csv | 1444 | 751 | 69 | 170 | 143 | 247 | 33 | 204 | 303 | 202 | 42 |
| options/options_intelligence_phantom.csv | 1444 | 895 | 135 | 205 | 151 | 316 | 46 | 227 | 355 | 257 | 56 |
| options/options_intelligence_summary.json | 10 | 54 | 0 | 2 | 0 | 18 | 0 | 16 | 20 | 18 | 0 |
| options/options_session_exceptions.csv | 1 | 8 | 0 | 0 | 0 | 0 | 0 | 3 | 5 | 0 | 0 |
| options/options_summary.json | 10 | 54 | 0 | 2 | 0 | 18 | 0 | 16 | 20 | 18 | 0 |
| options/phantom_summary.json | 1 | 8 | 0 | 0 | 0 | 5 | 0 | 1 | 2 | 5 | 0 |
| options/vanguard_signals_enriched.csv | 1522 | 962 | 141 | 192 | 167 | 279 | 27 | 228 | 455 | 232 | 47 |
| qomega/garch_forecasts.csv | 1444 | 17 | 4 | 1 | 0 | 4 | 5 | 9 | 4 | 3 | 1 |
| superbrain/eil_enriched.csv | 1444 | 1134 | 172 | 253 | 188 | 328 | 57 | 310 | 499 | 266 | 59 |
| superbrain/superbrain_enriched.csv | 1444 | 967 | 153 | 216 | 158 | 322 | 51 | 258 | 390 | 260 | 59 |
| superbrain/wall_break_scores.csv | 221 | 917 | 137 | 257 | 158 | 316 | 43 | 243 | 361 | 249 | 64 |
| superbrain/wall_break_summary.json | 5 | 15 | 0 | 0 | 0 | 4 | 0 | 8 | 3 | 4 | 0 |
| trades/execution_actionable.csv | 19 | 1006 | 175 | 415 | 125 | 234 | 41 | 436 | 348 | 89 | 133 |
| trades/execution_gate_summary.json | 1 | 44 | 0 | 0 | 0 | 21 | 0 | 19 | 4 | 21 | 0 |
| trades/execution_gated.csv | 1444 | 950 | 170 | 261 | 92 | 221 | 50 | 421 | 320 | 114 | 95 |
| vanguard/vanguard_rejects.csv | 50 | 7 | 0 | 5 | 0 | 0 | 0 | 1 | 6 | 0 | 0 |
| vanguard/vanguard_run_summary.json | 1 | 7 | 0 | 0 | 0 | 0 | 0 | 2 | 5 | 0 | 0 |
| vanguard/vanguard_signals.csv | 1522 | 492 | 53 | 112 | 141 | 222 | 8 | 41 | 229 | 190 | 32 |
| morning_validation/validation_events/validation_<id>.json (rep, 1,444 files) | 1 | 25 | 1 | 0 | 0 | 1 | 0 | 11 | 13 | 1 | 0 |
| packages/<TICKER>.package.json (rep AAPL, 1,572 files) | 1268 | 16341 | 667 | 705 | 776 | 7997 | 12 | 1303 | 7041 | 7397 | 600 |
Non-tabular, not censused: `diagnostics/intraday_regime_watchdog_message_<run>.txt`, `diagnostics/market_breadth_message_<run>.txt`, `diagnostics/uat_audit_report_<run>.md`.

## Minimum field sets
### 1. Smallest field set reproducing current decisions
The size depends on what "read by a decision path" means, so three tiers are reported; the justification for each field is the reader file:line in `p21_M9_minset_decision_fields.csv` (`evidence_six` / `evidence_validators` columns) and `p21_M9_decision_read_kinds.csv`.

| tier | definition | fields | in Lab book |
|---|---|---|---|
| A — narrowest | field value sits in a BRANCH (condition/comparison/arithmetic) in the three final-authority readers: `execution_gate.py`, `contracts/opportunity_tier.py`, `contracts/lab_control.py` 1707–2382 (verdict derivation) | **34** | 19 |
| B — CORE | BRANCH or FETCH read in the six named readers (A's three + `morning_gate.py` decision ranges + `eod_candidate_engine.py` route/status/manifest-mask ranges 443–730, 1206–1300, 2830–2900 + `orchestrator/dynamic_dispatcher.py` 84–158), restricted to fields that exist as a column of a row-level decision book | **231** (= 203 logical inputs after collapsing 14 fallback alias chains, p22) | 93 (86 logical) |
| B+ — CORE + called validators | B plus fields read only inside `contracts/direction_governance.validate_direction_record` (390–511), `domain/option_liquidity_execution_guard.evaluate_olm_execution_guard` (84–193), `domain/execution_authority` (147–292) | 231 + 24 = 255 | — |
| C — broad (p20 LOAD_BEARING) | any quoted read, including output-dict pass-throughs, in the p20 decision ranges (adds DOI production/ranking and the broad lab_control/eod ranges) | 365 tokens in the tighter p20 MINSET ranges; 669 in all decision ranges | 140 (MINSET) / 243 (LOAD_BEARING) |

CORE per reader (a field may count in several): morning_gate.py 115, contracts/lab_control.py 59, execution_gate.py 56, eod_candidate_engine.py 51, contracts/opportunity_tier.py 27, orchestrator/dynamic_dispatcher.py 3. Read kinds inside the six named readers: FETCH 446, BRANCH 300, OTHER 83, PASS 53 (2,056 sites over all decision ranges: FETCH 713, BRANCH 545, OTHER 481, PASS 317). 41 tokens are read only as output-dict keys inside the decision ranges (PASS_ONLY — e.g. `contract_gamma`, `contract_theta`, `contract_vega`, `contract_oi`, `contract_volume`, `ev3_p_target`, `ev3_p_stop`, `ev3_p_timeout`, `lab_tradeable`, `option_gain_at_target`, `rr_premium_expected`); these are outputs of the decision path, not inputs. 64 CORE tokens are value literals that coincide with field names elsewhere (`CALL`, `PUT`, `GO_LIMIT`, `BUY_SMALL`, …) and were excluded by the row-level-artefact filter.
Alias chains collapsed by p22 (23 call sites: 12 `_first_value` in execution_gate.py, 11 `_first` in opportunity_tier.py): direction {`governed_direction`, `final_direction`, `canonical_direction`, `direction`}; contract symbol {`contract_symbol`, `live_contract_symbol`, `morning_selected_contract_symbol`, `recommended_contract`}; IV rank {`iv_rank`, `live_iv_rank`, `iv_percentile`, `ivp_252d`}; ask/bid/delta/iv/mid each {`contract_x`, `live_x`, `live_contract_x`}; spot {`entry_spot`, `signal_price`, `underlying_price`}; RR {`rr_options`, `rr_predicted`, `rr_underlying`}; target {`structural_target`, `target_price`, `target_spot`}; {`eod_status`, `trigger_state`}; {`horizon_bucket`, `time_horizon`}; {`invalidation_price`, `invalidation_spot`}.

Tier A — the 34 fields, with the reader line that makes each one load-bearing:
| field | in Lab book | reader evidence (file:line, text) |
|---|---|---|
| alternative_contract_1 / _2 / _3 | yes | execution_gate.py:198 `for field in ("alternative_contract_1", "alternative_contract_2", "alternative_contract_3")` (`_has_contract_alternative`) |
| ask | no (nested `live` dict from row aliases) | execution_gate.py:305 `ask = float(live.get("ask", 0) or 0)` |
| bid | no (same) | execution_gate.py:304 `bid = float(live.get("bid", 0) or 0)` |
| campaign_verdict | yes | contracts/lab_control.py:2116 `confirms_buy = source["execution_verdict"] in GO_EXECUTION_STATES or …`; execution_gate.py:72 (conviction override) |
| contract_quote_source | no | contracts/lab_control.py:2072 `if "DELAY" in _u(first(sig, "contract_quote_source", "md_quote_source", …` |
| contract_repair_status | yes | contracts/opportunity_tier.py:218 `if _upper(row.get("contract_repair_status")) in {` |
| effective_execution_verdict | no | contracts/lab_control.py:1919 `or source["effective_execution_verdict"]` |
| eil_data_mode | no | contracts/lab_control.py:2072 (same `first(…)` chain) |
| eil_ev_net | no | contracts/lab_control.py:2082 `if _f(first(sig, "ev2_ev_conf_adj", "eil_ev_net", "ev"), 0.0) < 0:` |
| eil_v3_verdict | yes | contracts/lab_control.py:1820 `if source.get("eil_v3_verdict"):`; :2036 `if source["eil_v3_verdict"]:` |
| eod_candidate_status | yes | contracts/lab_control.py:2113 `eod_status = source["eod_candidate_status"] or source["lab_execution_status"]` |
| ev2_ev_conf_adj | no | contracts/lab_control.py:2082 |
| ev_status | no | contracts/lab_control.py:2084 `… or source["ev_status"] in {"A…` |
| execution_verdict | no | contracts/lab_control.py:1920, :2038 `if source["execution_verdict"] in HARD_EXECUTION_STATES:` |
| final_action | yes | execution_gate.py:507 `actionable = [s for s in gated if s.get("final_action") in ("BUY_NOW", …`; :509 |
| gate_warnings | yes | contracts/lab_control.py:1817; execution_gate.py:505 `for w in str(s.get("gate_warnings","")).split(","):` |
| governed_direction_record_sha256 | yes | contracts/opportunity_tier.py:111 `if not _text(_first(row, "governed_direction_record_sha256", …` |
| iv_rank | yes | execution_gate.py:309 `iv_rank = float(live.get("iv_rank", 50) or 50)`; :163 |
| lab_execution_status | yes | contracts/lab_control.py:1916 `if not source["lab_execution_status"]:`; :2113 |
| live_price | no | execution_gate.py:368 `spot = _f(row, "current_price") or _f(row, "underlying_price") or _f(row, "live_price")` |
| olm_guard_disposition | yes | execution_gate.py:501 `olm_disposition = str(s.get("olm_guard_disposition") or "MISSING")` |
| olm_guard_reason | yes | execution_gate.py:502 |
| opportunity_tier | yes | contracts/opportunity_tier.py:284 `tier = _upper(row.get("opportunity_tier")) or derive_tier(row)[0]` |
| options_verdict | no | contracts/lab_control.py:1922, :2041 `if source["options_verdict"] in HARD_EXECUTION_STATES:` |
| pipeline_mode | yes | contracts/lab_control.py:1931 `mode = _u(manifest.get("pipeline_mode")) or "UNKNOWN"` |
| pse_execution_mode | no | contracts/lab_control.py:1921, :2047 `if source["pse_execution_mode"] == "FATAL_BLOCK":` |
| pse_final_size | no | execution_gate.py:74 `and _f(row,"pse_final_size") >= cfg_gate.PSE_CONVICTION_MIN)` |
| sb_final_verdict | no | contracts/lab_control.py:2063 `if source["sb_final_verdict"] == "EXECUTE" and veto_flags:` |
| spread_pct | yes | contracts/opportunity_tier.py:93 `if _text(row.get("spread_pct")):`; :95 |
| thesis_decision | no | contracts/lab_control.py:2044 `if source["thesis_decision"] in HARD_EXECUTION_STATES:`; :2076 |
| ticker | yes | contracts/lab_control.py:1715 `if _u(row.get("ticker")) != ticker:`; :1937; execution_gate.py:202 |
| underlying_price | yes | execution_gate.py:368 |
Reading of tier A: the final capital-authority decision (`execution_gate.py`) and the Lab verdict (`lab_control.resolve_lab_tradeability` / `apply_lab_resolution`) branch on ~34 fields, most of which are upstream verdict strings (`execution_verdict`, `options_verdict`, `thesis_decision`, `eil_v3_verdict`, `sb_final_verdict`, `pse_execution_mode`, `eod_candidate_status`, `campaign_verdict`, `olm_guard_*`, `opportunity_tier`) plus quote economics (`bid`, `ask`, `spread_pct`, `iv_rank`, `underlying_price`) and identity (`ticker`, `pipeline_mode`). The 15 tier-A fields not in the Lab book are read by the Lab verdict from the wider source books (execution_gated / final_opportunity_book) and are not carried into the 502-field extract.
The full CORE (tier B) list is in `p21_M9_stdout.txt` ("CORE field list") and `p21_M9_minset_decision_fields.csv` (tier = CORE, in_row_level_artefact = True).

### 2. Smallest field set supporting the M1–M5 measurements (from `p21_M9_mtrack_summary.csv`, `p20_M9_mtrack_field_map.csv`, and the field-existence checks in this track)
| track | need | exists today (artefact: field, fill) | missing |
|---|---|---|---|
| M1 | ticker | every row-level book (`ticker`, fill 1.0) | — |
| M1 | session date | `evidence_session_date` (execution_actionable 1.0; execution_v3_5 / morning_candidates 0.84); `macro_session_date` (run-level constant); `completed_session` (run_meta); `bar_data_asof` (Lab book) | a per-row decision-session field with full fill |
| M1 | gics_sector / industry | Lab book & final_opportunity_book `gics_sector`, `gics_sector_norm`, `sector` (fill 1.0; 3 duplicates); `industry` in core_intel_menu items | — |
| M1 | USMI labels | Lab book `usmi_state`, `usmi_scenario`, `usmi_sector_alignment`, `usmi_alignment_reason`, `usmi_quality_status`, `usmi_packet_id` (all constant across the 19 rows; `usmi_alignment_priority` all-null); packages `discovery.usmi_gamma_position`; the 17,234 regex hits are dominated by the macro payload blocks | `usmi_routing_key` (not emitted anywhere, cf. briefing) |
| M1 | forward prices | **MISSING_EVERYWHERE** (no `forward_*`/`realised_price`/`outcome_price`/`forward_return` field in any artefact) | forward close series per ticker/session |
| M2 | forward realised vol | `garch_forecast_vol`, `garch_forecast_confidence`, `garch_method` (Lab book, qomega/garch_forecasts); `l3_forward_realised_vol` (execution_v3_5, range 0.16–2.50, unit AMBIGUOUS) — a model output despite the name; `macro_snapshot.extras.volatility.realised_vol_20d` (index-level) | per-ticker realised vol over the hold (needs forward prices) |
| M2 | expected moves | `expected_move_5d/10d/20d`, `l3_expected_move_6_10d/11_20d` (execution_v3_5, superbrain), `expected_move` (Lab book, range 0.81–453 → AMBIGUOUS) | a documented unit |
| M2 | contract IV / ATM IV | `contract_iv`, `atm_iv` (Lab book, morning books, execution_gated; fill 1.0; both straddle 1) | — |
| M2 | realised prices | **MISSING_EVERYWHERE** | as M1 forward prices |
| M3 | direction | `canonical_direction` (+4 identical aliases) | — |
| M3 | origin spot | `signal_price` = `underlying_price` = `scanner_price` (Lab book); `entry_spot` (execution_v3_5, eil_enriched); `thesis_origin_spot` ABSENT (execution_gate.py:133 reads it first in its fallback chain) | `thesis_origin_spot` |
| M3 | structural target | `structural_target` = `target_price` = `target_zone` = `monetisability_structural_target_spot` | — |
| M3 | invalidation | `invalidation_price`, `invalidation_state` (Lab book); `invalidation_spot` (execution_gated/actionable/v3_5) | — |
| M3 | hold | `hold_period` = `time_horizon` = `hold_window` (Lab book, 2 distinct); `planned_hold_sessions`, `remaining_hold_sessions` (execution_gated/actionable/v3_5) | — |
| M3 | decision session | `evidence_session_date` (see M1) | — |
| M3 | preferred contract | `selected_contract_symbol` (+6 identical aliases) | — |
| M3 | entry premium | `contract_mid`, `contract_ask` (+ aliases `premium_mid`, `rr_entry_debit_per_share`, `monetisability_entry_ask`) | — |
| M4 | contract family quotes with greeks | selected contract only: `contract_bid/ask/mid/delta/gamma/vega/theta/iv/oi/volume/dte`, `strike`, `expiry` (Lab book, morning books, fill 1.0). Family level: `contracts_tested[].{symbol, dte, delta, spread_pct, mid, gate_failed}` (contracts_tested.jsonl, 1,218 families); `ev3_stage1_contract_evaluations.parquet` (2,430 rows; `ev3_strike`, `ev3_expiry`, `ev3_entry_debit_per_share`, exit mids, fill 0.15); packages `options_contract.*` 23 of 25 leaves all-null on the representative | per-contract `bid`, `ask`, `gamma`, `vega`, `theta`, `iv`, `oi`, `volume`, `strike`, `expiry` for the whole family (strike/expiry derivable from the OCC symbol) |
| M4 | spot | `underlying_price` / `live_price` / `current_price` | — |
| M4 | sigma_h | **MISSING_EVERYWHERE** (no `sigma_h`/`horizon_sigma` field; derivable from `garch_forecast_vol` × √hold) | `sigma_h` |
| M5 | thesis identity stable across runs | `thesis_id` (Lab book, final_opportunity_book, validation_events: `CNC:CALL:2026-09-10:OLM2` form), `trade_idea_id`, `selected_structure_id`; `governed_direction_record_sha256` | cross-run stability is not testable on one run |
| M5 | premium / IV / spot per run | `run_id` + `contract_mid`, `contract_iv`, `underlying_price` in each run's Lab book | — |
| M5 | quote timestamps | `current_quote_timestamp_utc` (+4 identical aliases), `selected_quote_timestamp_utc`, `quote_age_seconds` (Lab book, execution_gated), `ev3_quote_age_seconds` (ev3 shadow), `[].governed_record.quote_age_seconds` (evidence bundle) | — |

Gap between the two lists (the instrumentation plan, stated as observations): the measurement set needs four things the decision set never reads and no artefact carries — forward prices / realised prices, realised volatility over the hold, `sigma_h`, and family-wide per-contract greeks and quotes — plus a per-row decision-session date with full fill and a resolved unit on the IV / expected-move / spread fields. Everything else the M-tracks need already exists in the Lab book or the 1,444-row books, often under several names.

## AMBIGUOUS_UNIT fields
Overall: 848 artefact×field rows, 166 distinct tokens (`p21_M9_ambiguous_units.csv`): 86 fraction-by-name but range > 1; 62 straddle 1 in a spread/vol/move/iv/sigma field; 18 percent-by-name (`_pct`) but range ≤ 1.
Lab book (15):
| field | range (19 rows) | candidate units |
|---|---|---|
| atm_iv | 0.1181 – 1.5097 | fraction \| percent (straddles 1) |
| contract_iv | 0.2121 – 1.7020 | fraction \| percent (straddles 1) |
| atm_distance_sigma | 0.0000 – 1.6165 | fraction (sigma units) \| percent |
| iv_vs_hv | 0.683 – 3.513 | ratio \| percent |
| iv_rank | 0 – 100 | percent \| fraction (name token `iv`) |
| vega_risk_pct | 0.00 – 0.64 | percent (name) \| fraction (range) |
| garch_forecast_confidence | 80.7 – 92.5 | percent \| fraction (name token `confidence`) |
| garch_iv_tailwind_score | −0.2344 – 1.2624 | fraction \| score |
| phase_transition_probability | 36.887 – 58.117 | percent \| probability-fraction (name) |
| gamma_flip | 6.56 – 422.43 | price level \| fraction (name token `gamma`) |
| gamma_island_level | 0 – 430 | price level \| fraction (name token `gamma`) |
| contract_volume | 0 – 119 | count (absolute) — flagged only because `vol` matched the straddle rule; false positive |
| monetisability_target_intrinsic_per_share | 1.09 – 193.71 | USD per share \| fraction (name token `share`) |
| monetisability_target_profit_per_share | −0.91 – 183.91 | USD per share \| fraction |
| monetisability_timevalue_value_per_share | 2.04 – 193.71 | USD per share \| fraction |
Of these, 6 are LOAD_BEARING (`atm_iv`, `contract_iv`, `atm_distance_sigma`, `iv_rank`, `gamma_flip`, `gamma_island_level`); `execution_gate.py:100–105 _normalise_ratio` divides values > 1 by 100 before use, i.e. the gate itself treats `contract_iv` as either percent or fraction.
Other important-artefact fields (execution_actionable / execution_gated / morning_validated_trades; 63 distinct at importance rank ≤ 4): `spread_pct` and `contract_spread_pct` 0.085–0.178 (percent name, fraction range); `live_spread_pct` 0.0853–0.1778 (same); `live_iv` / `live_contract_iv` 0.212–1.702; `expected_move` 0.81–453.25 and `expected_move_10d` 0.77–12.33 and `l3_expected_move_6_10d` 0.77–12.33 (straddle 1); `l3_forward_realised_vol` / `vol_forecast` 0.1557–2.5000; `confidence_score` 21.65–66.02; `l3_vol_forecast_conf` / `vol_conf` 80.7–92.5; `theta_decay_expected` 8.98–61.68; `contract_spread_pct_eod` 0–96.97 (a percent range beside the 0.085–0.178 fraction range of `contract_spread_pct` in the same artefact); `thesis_move_realised` −8.69–5.59; `move_theta_ratio` 0.90–221.63; `ms_repair_pct` 0–1; `target_move_pct` 0.030–0.364; `live_contract_bid_size` 0–2,797 and `live_contract_oi` 0–1,088 (count fields caught by the straddle rule; false positives).

## Constants (top 30 by artefact importance)
Selection rule: Lab-book constants that are also constant across the 1,444-row books (`p21_M9_constants_top.csv`, `also_constant_in_1444_row_artefacts` non-empty), LOAD_BEARING first. 101 Lab constants are pipeline-wide on this run; 37 of them LOAD_BEARING; the remaining 99 Lab constants vary in the 1,444-row books and are constant only because the extract is 19 GO rows of one run.
| # | field | value | classification |
|---|---|---|---|
| 1 | run_id | 20260911_115904 | LOAD_BEARING |
| 2 | pipeline_mode | MORNING_VALIDATION | LOAD_BEARING |
| 3 | quote_freshness | STALE | LOAD_BEARING |
| 4 | execution_authorized | False | LOAD_BEARING |
| 5 | execution_can_grant_capital | False | LOAD_BEARING |
| 6 | convexity_score | 2.0 | LOAD_BEARING |
| 7 | convexity_campaign | STAGED | LOAD_BEARING |
| 8 | actuarial_ev_weight | 0.0 | LOAD_BEARING |
| 9 | macro_regime | TRANSITIONAL_BEARISH | LOAD_BEARING |
| 10 | regime_drift_status | DRIFTING_BEARISH | LOAD_BEARING |
| 11 | macro_as_of_utc | 2026-09-11T11:35:00+00:00 | LOAD_BEARING |
| 12 | conflict_state | SOFT_CONFLICT | LOAD_BEARING |
| 13 | hard_vetoes | [] | LOAD_BEARING |
| 14 | options_hard_vetoes | [] | LOAD_BEARING |
| 15 | selected_structure | LONG_SINGLE | LOAD_BEARING |
| 16 | selected_structure_hydration_status | COMPLETE | LOAD_BEARING |
| 17 | morning_lab_alignment_status | ALIGNED_EXECUTION_GATE | LOAD_BEARING |
| 18 | morning_data_state | AVAILABLE | LOAD_BEARING |
| 19 | direction_integrity_status | PASS | LOAD_BEARING |
| 20 | direction_resolution_chain_json | [] | LOAD_BEARING |
| 21 | direction_excluded_evidence_json | ["discovery_direction_preliminary", …] | LOAD_BEARING |
| 22 | dir_calc_version | dir_v1.2.0 | LOAD_BEARING |
| 23 | direction_policy_version / _sha256 | strangle_resolution_v1.1.0 / ab24f371… | LOAD_BEARING |
| 24 | governed_direction_authority | DISCOVERY_GOVERNED | LOAD_BEARING |
| 25 | execution_authority_source / _policy_version | FINAL_EXECUTION_GATE / execution-authority-v1 | LOAD_BEARING |
| 26 | maturation_execution_authority | False | LOAD_BEARING |
| 27 | lifecycle_contract_version | options-liquidity-lifecycle-v2 | LOAD_BEARING |
| 28 | contract_source / option_chain_provider / option_chain_resolution | MARKETDATA / MARKETDATA / EXACT_HIT | LOAD_BEARING |
| 29 | pcr_vol_status / pcr_vol_missing_reason | OI_ONLY_NO_INTRADAY_VOLUME / OPTIONS_CHAIN_VOLUME_NOT_AVAILABLE | LOAD_BEARING |
| 30 | bar_data_asof / bar_data_days_old / win_rate_source | 2026-09-10 / 1 / ACTUARIAL | LOAD_BEARING |
Other pipeline-wide constants of note (ADVISORY_USED): `ev3_shadow_only = False`, `ev3_structure = LONG_SINGLE`, `maturation_score_is_probability = False`, `doi_decision_authority = NONE`, `liquidity_friction_score = 32.0`, `monetisability_minimum_profit_pct = 20.0`, `monetisability_timevalue_model = BS_CONST_IV_R0_Q0`, `execution_viability_spread_denominator = MID`, `scenario_dte_target = 40`, `gate_version = 1.5.0`, `usmi_state = US_CAPITAL_MAGNET_DEFENSIVE_ROTATION`, `macro_data_quality = PARTIAL`, `usmi_quality_status = PARTIAL_UNVERIFIED`. Lab-only constants of note (vary in the 1,444-row books; constant across the 19 GO rows): `final_action = BUY_SMALL`, `lab_verdict = GO_LIMIT`, `opportunity_tier = BLOCK`, `opportunity_tier_reason = SPREAD_ABOVE_REVIEWABLE…`, `executable_now = True`, `execution_viability_state = EXECUTABLE_QUOTE`, `liquidity_state = EXECUTABLE_NOW`, `maturation_score_1d/2d/3d = 100.0`, `readiness_stage = 4`, `rr_underlying = 0.0`, `campaign_verdict = STAGED`, `eil_v3_verdict` (1 distinct), `doi_projection_state = DATA_UNAVAILABLE`.

## Findings (DISC-F-M9-n; placeholders, no severity)
DISC-F-M9-1 — Lab-book width vs decision use. 502 fields; the three final-authority readers branch on 34 fields (19 present in the book); the six named readers read 93 Lab fields (86 logical inputs); p20's broad rule marks 243 LOAD_BEARING. Does not establish that the remaining fields are useless: they may serve human review, dossiers (`build_trade_dossiers.py`), the coaching/dropbox scripts (excluded from the corpus), or future readers; nor that the tier-A reader lines are the only paths to a decision (dynamic reads via variables, `**row` spreads and DataFrame-wide operations are invisible to a string-literal grep). TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_minset_decision_fields.csv | N=502
DISC-F-M9-2 — Constants. 200/502 Lab fields are constant; 101 are also constant across every 1,444-row book, 37 of those LOAD_BEARING (e.g. `quote_freshness = STALE`, `execution_authorized = False`, `convexity_score = 2.0`, `macro_regime`). Does not establish constancy across runs (one run censused) nor that a run-level constant is redundant (it is the lineage of the row). TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_constants_top.csv | N=200
DISC-F-M9-3 — Duplicate columns and alias chains. 58 Lab fields duplicate another column byte-for-byte on this run (41 pairs; direction ×5, contract symbol ×7, ask ×5, quote timestamp ×5, target ×4); the readers consume them through 23 fallback-chain call sites forming 14 alias groups. Does not establish that the aliases are semantically identical across runs or across pipeline modes (identity observed on 19 rows of one MORNING_VALIDATION run only). TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_duplicate_pairs.csv;p22_M9_alias_chains.csv | N=58
DISC-F-M9-4 — All-null and unread blocks. 62 Lab fields are all-null (`wbs_*` 15, `doi_*` 10, `underlying_nbbo_*` 8, …); 19 have no production reader (11 DEAD, 8 PRODUCED_UNREAD), including the `execution_quote_*` and `validation_*` blocks written by the morning stage. Does not establish that these branches never populate (WBS and DOI are inactive on this run: `wbs_data_state = NOT_APPLICABLE…`, `doi_projection_state = DATA_UNAVAILABLE`). TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_field_census.csv | N=62
DISC-F-M9-5 — Ambiguous units. 15 Lab fields and 166 distinct tokens overall carry a name/range disagreement; IV fields straddle 1 (`contract_iv` 0.21–1.70, `atm_iv` 0.12–1.51), `*_pct` spread fields hold fractions (0.085–0.178) while `contract_spread_pct_eod` holds percents (0–96.97) in the same book, `confidence`/`probability`-named fields hold 0–100 values, and `execution_gate._normalise_ratio` (execution_gate.py:100–105) rescales > 1 values at read time. Does not establish that any consumer misreads a value (each reader may apply its own convention), nor that IV > 1 is a unit error rather than a genuinely high vol; 4 of the 15 Lab flags are count fields caught by the straddle rule (false positives noted in the table). TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_ambiguous_units.csv | N=848
DISC-F-M9-6 — Where the unread volume is. UNREAD is 3.8 % in the Lab book but 40.3 % across the run (24,959 of 61,870 rows): 23 % in the wide execution/morning books (execution_actionable 234, execution_gated 221, morning_validated_trades 229 fields), 31–35 % in options_intelligence / execution_v3_5, and ~50 % in the macro JSON payloads (packages rep 7,997 leaves, interpreter_macro_context 4,816, core_intel_dossiers 2,496, macro_snapshot 2,492). Does not establish waste: the JSON payloads are provider/macro snapshots kept for lineage and their leaves are read by path, not by python literal. TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_family_classification.csv | N=61870
DISC-F-M9-7 — M-track instrumentation gap. Forward/realised prices, realised vol over the hold and `sigma_h` exist in no artefact; family-wide per-contract greeks/quotes exist only as `contracts_tested[].{symbol,dte,delta,spread_pct,mid}` and the packages `options_contract` block is 23/25 all-null on the representative; `thesis_origin_spot` (first key in execution_gate.py:133's chain) exists nowhere; `contracts_tested.jsonl` carries `run_id` null in all 1,218 records. Does not establish that the measurements are impossible — M1/M2 forward data can be joined from `historical_prices.sqlite` copies and `sigma_h` derived from `garch_forecast_vol` and the hold; it establishes only that the run artefacts do not carry them. TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_mtrack_summary.csv | N=28
DISC-F-M9-8 — Producer resolution. 0 NO_PRODUCER in the Lab book; 23,557 (38.1 %) across the run, essentially all JSON leaves of macro/provider payloads (packages 8,094, interpreter 4,995, run root 3,330, core_intel 2,578; the 1,444-row CSVs have 0–17). Does not establish absent lineage — the leaves are produced by serialising provider objects whose keys are not python string literals. TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p20_M9_field_census.csv | N=23557
DISC-F-M9-9 — Method sensitivity of "load-bearing". The same Lab book yields 34 / 93 / 140 / 243 decision fields depending on whether a read must branch, may merely be fetched, may sit anywhere in a reader's decision range, or may be an output-dict pass-through; 41 tokens inside decision ranges are read only as output keys (p21 PASS_ONLY). Does not establish which tier is "correct"; it establishes that any headline count must name its rule. TRACE: REQ-NONE | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-M9 | EVIDENCE-p21_M9_decision_read_kinds.csv | N=2056

## Deviations (observations, no severity)
- Row counts: the inventory's `records` column is a physical line count; pandas row counts on the multi-line CSVs are `options_intelligence` 1,444 (inventory 14,784), `execution_v3_5` 1,444 (14,784), `eil_enriched` / `superbrain_enriched` 1,444 (14,784), `options_candidates_ranked` / `_latest` / `_pre_ev3_authority` / `_phantom` 1,444 (14,784), `vanguard_signals` / `vanguard_signals_enriched` 1,522 (49,966), `wall_break_scores` 221 (1,969), `options_blocked_review` 422 (5,574), `horizon_1_5d` 319 (7,957), `horizon_6_10d` 937 (29,905), `horizon_blocked` 188 (9,632). Evidence: `p20_M9_run.log` vs `p03_artefact_inventory_raw.csv`.
- `horizon/horizon_11_20d_<run>.csv` has 0 rows × 966 columns; `morning_validation/missed_opportunity_shadow_book_<run>.csv` has 0 rows × 67.
- `options/contracts_tested_<run>.jsonl`: `run_id` is null in all 1,218 records; `contracts_tested_truncated` is filled and varying (2 distinct), `repair_result` all-null. The probe capped the nested `contracts_tested[]` lists at 100,000 entries, so the per-contract statistics (`[].contracts_tested[].*`) are on the first 100,000 contracts, not the full set.
- `packages/AAPL.package.json` (representative): `options_contract` block has 23 of 25 leaves null (`expiry`, `strike`, `bid`, `ask`, `iv`, `delta`, … ), `options_enriched = False`.
- Lab book GO rows carry `quote_freshness = STALE` (constant, also constant in the 1,444-row books) alongside `execution_viability_state = EXECUTABLE_QUOTE`, `executable_now = True`, `liquidity_state = EXECUTABLE_NOW` and `execution_quote_status = SAME_SESSION_EVIDENCE`; `opportunity_tier = BLOCK` (reason `SPREAD_ABOVE_REVIEWABLE…`) on all 19 rows whose `final_action = BUY_SMALL` / `lab_verdict = GO_LIMIT`; `execution_authorized = False`, `execution_can_grant_capital = False`, `final_capital_permission = HUMAN_APPROVAL_REQUIRED` on all rows (consistent with a human-approval ceiling); `maturation_score_1d/2d/3d = 100.0` with `maturation_score_is_probability = False`; `convexity_score = 2.0` on every row (consistent with the briefing's comprehension note on the empty dashboard); `doi_projection_state = DATA_UNAVAILABLE` and all `doi_*` probability/ranking fields null (DOI tables inactive on this run); `rr_underlying = 0.0` constant.
- `l3_forward_realised_vol` (execution_v3_5, eil_enriched; range 0.1557–2.50; = `vol_forecast` by content) is a model forecast column by name-pattern of its siblings (`l3_vol_forecast_conf`, `vol_forecast`), not a realised quantity; its producer is resolved in the census `producer` column. Not verified beyond the census here.
- Production corpus used for the grep (554 files) includes 24 stale copies (`intelligence-lab/intelligence_lab0505.py`, `intelligence_labold.py`, `intelligence_labolddnu0605am.py`, `vanguard/execution/execution_intelligenceold*.py`, `vanguard/integration/orchestrator_adapter*dnu*.py`, `vanguard/layer3_execution/*old*`, `tools/sanitize_universeold.py`, …): only 3 census rows (`horizon_summary.macro_generated_at`, `wall_break_summary.wbs_avg`, `wbs_max`) owe their ADVISORY_USED status solely to them; none in the Lab book (`p21_M9_stale_reader_impact.csv`). The corpus excludes `dropbox/` (5 coaching scripts named as readers in the inventory): exactly one Lab field, `validation_profile_evidence_state`, is read only there (`dropbox/macro/coaching/build_trade_dossiers.py`) and is classed DEAD here.
- `dynamic_options_ranking.py` exists both as `domain/dynamic_options_ranking.py` (32 KB) and `canonical_data/dynamic_options_ranking.py` (17.5 KB); p20 treated only the `domain/` copy plus `canonical_data/dynamic_options_production.py` as DOI decision readers (30 + 40 read sites).
- `final_opportunity_book_<run>.json` (142 MB) was censused keys-only (496 keys from the first 1 MB); its CSV twin (474 columns, 1,444 rows) was censused in full.
- Inventory row 95 (`packages/`) and row 96 (`validation_events/`) are families; each was censused on one representative, so their counts are per-file, not per-family totals.

## Not tested / blocked
- `outcome_relation`: NOT TESTABLE for every field — no resolved outcomes exist on these runs.
- Cross-run constancy / alias stability: NOT TESTED (single primary run censused; the comparison run 20260910_150045 has no morning artefacts and was not needed for a census).
- Semantic equivalence of duplicate columns: NOT TESTED beyond byte-identity on this run.
- Dynamic reads (`row[var]`, `**row`, DataFrame-wide `.get`/`.isin` over column lists): not visible to a string-literal grep; the LOAD_BEARING sets are lower bounds for such paths.
- `packages/` family: 1 of 1,572 files censused (AAPL); `validation_events/`: 1 of 1,444.

## Expectation vs actual (expectations.md, M9 row)
| expectation | actual | gap |
|---|---|---|
| lab_signal_book_v3: 502 fields | 502 | none |
| fill rate < 50 % on ≥ 30 % of fields | 80 / 502 = 15.9 % (62 all-null + 18 partially filled) | 14.1 pts under |
| constants (1 distinct) ≥ 15 % | 200 / 502 = 39.8 % (101 pipeline-wide, 99 extract-only) | 24.8 pts over |
| UNREAD ≥ 40 % | 19 / 502 = 3.8 % (run-wide 40.3 %; execution_actionable 23.3 %) | 36 pts under for the Lab book; met run-wide |
| AMBIGUOUS_UNIT ≥ 20 fields | 15 (4 of them false positives on count fields → 11 genuine) | 5–9 under |
| minimum set for current decisions ≤ 40 fields | tier A 34 (19 in Lab book); tier B 231 / 203 logical (93 / 86 in Lab book); tier C 365 | met at tier A only; tier B is ~5× the expectation |

## State log lines
```
step,state,n,duration,note
M9.census.p20,DONE,61870,979s,p20_M9_field_census.py over 92 tabular artefacts of run 20260911_115904; 4231 field tokens; corpus 554 files
M9.lab_book,DONE,502,-,fill<50%=80 (15.9%); constants=200 (39.8%); unread=19 (3.8%); ambiguous=15; dup=58; all_null=62; LB/ADV/PU/DEAD=243/240/8/11
M9.top_n,DONE,19,-,execution_actionable treated as Top-N (19 rows = lab tickers; 1006 fields; unread 234); core_intel_menu is a Top-3 digest (59 fields)
M9.families,DONE,20,-,p21_M9_family_classification.csv; packages rep 16341 leaves (unread 7997); validation_events rep 25 fields
M9.aggregate,DONE,61870,-,LB 10304 / ADV 26700 / PU 21462 / DEAD 3404; unread 24959 (40.3%); no_producer 23557; ambiguous 848 rows / 166 tokens
M9.minset.decisions,DONE,34,-,tier A 34 (19 in lab) / tier B CORE 231 = 203 logical (93 / 86 in lab) / tier C 365; p21 + p22
M9.minset.mtracks,DONE,28,-,28 needs: 25 present in some artefact; MISSING forward prices; realised prices; sigma_h; family-wide greeks partial
M9.ambiguous,DONE,166,-,p21_M9_ambiguous_units.csv; lab 15 (6 LOAD_BEARING)
M9.constants,DONE,101,-,101 lab constants pipeline-wide (37 LOAD_BEARING); 99 extract-only
M9.findings,DONE,9,-,DISC-F-M9-1..9
M9.expectation_vs_actual,DONE,6,-,met: 502 fields; constants; tier-A min set; not met: fill<50%; lab UNREAD; AMBIGUOUS>=20
```
