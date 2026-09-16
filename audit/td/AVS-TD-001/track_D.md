# Track D — DOI completion and lifecycle (REQ-WP3-01…06, ALG-11, ALG-12, ALG-16)
No NORMAL_COMPLETED_SESSION run exists; every result below is on TEST-condition runs and cannot be CLOSED.
Runs used: primary `20260911_115904` (TEST, forced intra-session, `pipeline_mode = MORNING_VALIDATION`, `evidence_cutoff_utc = 2026-09-11T11:59:04Z`, `run_condition = null`, code 00baa2b-dirty); comparison `20260910_150045` (TEST, `EOD`, cutoff `2026-09-10T15:00:45Z`, `run_condition = null`, no morning artefacts). Source read at HEAD `cc509cb`; both runs were produced by pre-remediation code.
Data sources: `discovery/discovery_lifecycle_<run>.csv`, `canonical/cds3_discovery_publication_<run>.json`, `vanguard/vanguard_signals.csv` + `vanguard_rejects.csv`, `options/vanguard_signals_enriched_<run>.csv`, `options/options_intelligence_<run>.csv` (DOI input), `options/dynamic_options_intelligence_<run>.json` (DOI report), `options/contracts_tested_<run>.jsonl`, `options/contract_rejection_log_<run>.csv`, `options/governed_direction_records_<run>.jsonl`, `diagnostics/dropoff_audit_<run>.csv`, `trades/execution_gated_<run>.csv`, `morning_validation/morning_validated_trades_<run>.csv`, `intelligence_lab/final_opportunity_book_<run>.csv`, `lab_triage_view_<run>.csv`, `lab_signal_book_v3.csv`, `ev3_shadow/*.csv`, `final_run_manifest.json`, `run_meta.json`; DB copy `db_copies/control_plane.sqlite` (ro): `option_thesis_events`, `doi_contract_families` (2,459), `doi_contract_assessments` (0), `doi_preferred_contract_decisions` (0), `option_contract_selection_events` (11,108), `option_contract_observations` (10,522); `config/governed_constants_v1.json`.
Probes (all in `audit/td/AVS-TD-001/probes/`, each with `.json`/`.txt` output): `p13_D_common.py`, `p13_D_d1_reconciliation.py` (stage ladder; its "unexplained 992" line is a mislabel, superseded by d1b), `p13_D_d1b_identity.py`, `p13_D_d2_doi_projection.py`, `p13_D_d3_thesis_trace.py`, `p13_D_d3b_exceptions.py`, `p13_D_d4_lifecycle.py`, `p13_D_d5_executable_now.py`, `p13_D_d5b_quote_truth.py`, `p13_D_d6_hysteresis.py`, `p13_D_d7_assessment_identity.py`, `p13_D_d8b_probability_fields.py` (`p13_D_d8_probability_fields.py` crashed on the ev3_shadow CSVs, which have no ticker column; d8b replaces it), `p13_D_pytest_wp3.txt`, `p13_D_pytest_lifecycle.txt`.

STATUS: COMPLETE — D1–D8 done.

## Results
| REQ ID | check | CALL result | PUT result | OTHER result | source evidence (file:line) | run evidence (run_id, artefact, field, value) | verdict | closed-offline? |
|---|---|---|---|---|---|---|---|---|
| REQ-WP3-01 (reconciliation) / SD invariant 1 | D1 input = presented + named exceptions | book 798 = DOI input 798 = 772 families + 26 exceptions | book 458 = DOI input 458 = 446 families + 12 exceptions | book 188 (138 STRANGLE, 50 UNRESOLVED) = 188 `NOT_APPLICABLE_NON_DIRECTIONAL` | `canonical_data/dynamic_options_production.py:108-112` (guard `retained == unique`, `deleted_opportunities == 0`); `:139-140` blank/duplicate drop runs before that guard; `morning_handoff_finalizer.py:741-745`, `:815-819` | 20260911_115904: 3,320 `dropoff_audit` tickers = 1,444 in book + 1,876 named (1,748 Discovery `reason_code`, 50 `vanguard_rejects`, 78 `options_verdict = NOT_SCOPED`); unexplained 0; gap 0. DOI grain 1,444 = 1,218 + 188 + 38, gap 0. 20260910_150045: 3,320 = 1,424 + 1,896, gap 0; DOI 1,424 = 1,241 + 182 + 1 | Identity holds on a TEST run, so no P0. Cannot be CLOSED. Named-exception quality is P2 (UAT-D-D9) | no |
| REQ-WP3-01 (input contract) | D3 thesis_id trace, DOI input vs governed book | 772 equal; 0 differ; 26 missing on DOI side (book has legacy `TICKER:CALL:20260911_115904`) | 446 equal; 0 differ; 12 missing on DOI side | 188 missing on DOI side (book `TICKER:UNRESOLVED:<run>`), handled as non-directional before the thesis check | `canonical_data/dynamic_options_production.py:139-140` (first row per ticker), `:157-169` raise → named exception, `:196-198` non-directional | 20260911_115904 DOI report `MISSING_GOVERNED_THESIS_ID = 38` (26 CALL / 12 PUT). DOI input has no `evidence_cutoff_utc` column; `quote_timestamp_utc` missing 226; target/invalidation missing 390 (202 directed). `governed_direction_records_*.jsonl` 1,444 rows, 0 with `thesis_id`. 20260910_150045: 1 PUT exception | OPEN P1 (UAT-D-D1) | no |
| REQ-WP3-02 / ALG-06 | D2 `doi_projection_state` on Lab book | 761 `DATA_UNAVAILABLE/DOI_TABLES_NOT_ACTIVATED`; 37 `DATA_INCONSISTENT/GOVERNED_CONTRACT_IDENTITY_MISMATCH` | 432 `DOI_TABLES_NOT_ACTIVATED`; 26 `GOVERNED_CONTRACT_IDENTITY_MISMATCH` | 188 `DOI_TABLES_NOT_ACTIVATED` | `canonical_data/dynamic_options_projection.py:84`, `:107`, `:123-124`; `canonical_data/dynamic_options_production.py:281-289` (`FAMILY_NOT_VALUED_RATE_UNAVAILABLE`) | 20260911_115904 `final_opportunity_book` and `lab_triage_view`: 1,381 / 63; `lab_signal_book_v3` 19/19 `DOI_TABLES_NOT_ACTIVATED`; `doi_preferred_contract_symbol`, `doi_family_id`, `doi_ranking_id`, `doi_alternatives_json` non-null 0/1,444. DOI report: `FAMILY_NOT_VALUED_RATE_UNAVAILABLE = 1,218`. `doi_contract_assessments` 0 rows. 20260910_150045: 1,424/1,424 `DOI_TABLES_NOT_ACTIVATED` | OPEN P1 (UAT-D-D2) | tests: `test_doi11_production_integration.py` 6 passed (offline only) |
| REQ-WP3-03 / ALG-12 (OI/volume non-removal) | D4 thin contracts retained, 0 removed for OI/volume alone | selected contract thin (OI < 100 or vol = 0): 601/772 retained; 171 of them `EXECUTABLE_NOW` | 323/446 retained; 117 `EXECUTABLE_NOW` | n/a (no contract) | `domain/option_contract_liquidity.py:370-505` (classifier has no OI input: "without using OI as a hard gate"); `scripts/avshunter_options_intelligence.py:1185-1186` (acquisition MIN_OI 0, volume 0); `:2061` MIN_OI 50 filters only the Heston surface-fit sample; `:1335-1336` `EV3_MIN_OPEN_INTEREST`/`EV3_MIN_VOLUME` defined, never referenced | 20260911_115904 `contract_rejection_log` 974 rows, 0 reason tokens mention OI/volume; DOI report `family_candidates_total 130,443`, `retained_low_open_interest 97,267`, `retained_zero_volume 106,306`, `deleted_opportunities 0`; control_plane observations for the run: thin contracts in every `liquidity_state` (CALL 843/1,011, PUT 411/522) | Non-removal holds on a TEST run. Cannot be CLOSED | CLOSED OFFLINE (source: no OI gate in classifier; `test_option_liquidity_lifecycle.py` 16 passed) |
| REQ-WP3-03 (three state machines, append-only) | D4 identity / execution / activity machines | one combined `liquidity_state` machine; no `ACTIVITY_*` states | same | n/a | `ACTIVITY_THIN`, `ACTIVITY_DEVELOPING`, `ACTIVITY_MATURING` and the `EXECUTION_*` vocabulary have no producer (only `domain/presentation.py:22` reads `EXECUTION_EXECUTABLE_NOW`); `domain/option_contract_liquidity.py:47-49` single enum | control_plane `option_contract_observations`: `correction_state` null 10,522/10,522, `supersedes_event_id` non-null 0 (append/correction path never exercised on stored data) | NOT IMPLEMENTED (UAT-D-D4, P1) | partial: append-only tests pass (`test_option_liquidity_lifecycle.py:179`, `:360`; `test_dynamic_options_lifecycle.py:318`, `:379`) |
| REQ-WP3-03 / ALG-12 (EXECUTABLE_NOW truth) | D5 every EXECUTABLE_NOW has bid > 0, ask > bid, fresh provider ts, spread ≤ 0.18; none outside post-open refresh | primary Lab book 47/47 pass vs gate time. Options CSV 255 `EXECUTABLE_NOW`, quotes 18.1–19.1 h old. Comparison EOD book 262 `executable_now = True` | primary Lab 22/22 pass. Options CSV 198 stale `EXECUTABLE_NOW`. Comparison EOD book 196 | 0 | `domain/option_contract_liquidity.py:449` `if age is not None and age > freshness_limit` (missing age skips freshness and falls through to `EXECUTABLE_NOW` at `:489-491`); no `run_condition == POSTOPEN_CONTRACT_REFRESH` check in the classifier; `domain/run_planning.py:39`, `:210` define the condition; `morning_gate.py:3016-3020`, `:3228` | 20260911_115904 `options_intelligence` `liquidity_state = EXECUTABLE_NOW` & `executable_now = True` 453, `contract_quote_timestamp_utc` all 2026-09-10, age vs cutoff 1,086–1,144 min; Lab book downgrades them (`QUOTE_STALE` 453), leaving 69 `EXECUTABLE_NOW` with 11 Sep quotes +301–306 min **after** the run cutoff. 20260910_150045 (EOD, no refresh): `final_opportunity_book` `executable_now = True` 458, quotes +114–172 min after cutoff, `morning_quote_timestamp_utc` null 458. `run_condition` null on every run; `contract_refresh_timestamp_utc` absent from every artefact | OPEN — P0 candidate on TEST runs (UAT-D-D3) | no |
| REQ-WP3-04 / ALG-11 | D6 hysteresis on preferred-contract switches; flip rate | options-CSV `recommended_contract` 10→11 Sep: 57/760 flipped (7.5%); selection events 11 Sep 6 switches | 22/431 (5.1%); 2 switches | 0/0 (no contract) | `domain/dynamic_options_ranking.py:377-434` (abs 0.05 / rel 0.10, `RETAIN_CURRENT_HYSTERESIS` `:431`, `SUPERSEDE_RANKING_MARGIN` `:434`); `canonical_data/dynamic_options_production.py` hysteresis config read (`margin_abs`, `margin_relative`, approval required); `config/governed_constants_v1.json:33-41` (`utility_unit NET_RETURN_FRACTION`, approved `ACK-20260912-AVS-FIX-002`); `PreferredContractSuperseded` appears nowhere in code | overall flip 79/1,191 = 6.6% (22 expiry-only, 40 strike-only, 17 both); `option_contract_selection_events` metadata has no utility/margin key; `supersedes_event_id` 0; `doi_preferred_contract_decisions` 0 rows. Margin cannot be verified (no U_i/U_c stored) | NOT IMPLEMENTED at run level (UAT-D-D5, P1) | CLOSED OFFLINE for margin rule only (`test_dynamic_options_ranking.py:140`, `:162`; `test_dynamic_options_lifecycle.py:163`, `:175`, `:187`; 14 + 17 passed). Event name/fields not implemented |
| REQ-WP3-05 / ALG-12 | post-open refresh publication (`morning_refresh_state`, `contract_refresh_timestamp_utc`, provider ts, dataset ID, `refresh_window_state`) | 941 `MORNING_EXACT_CONTRACT_REQUOTE` + 52 `MORNING_REPAIR_ALTERNATIVE_SELECTED` events (CALL+PUT, 8 switches: 6 CALL, 2 PUT) | (included left) | n/a | `morning_refresh_state` and `THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE`: no producer. `refresh_window_state` is computed at `morning_gate.py:3020` and published as `postopen_contract_refresh_window_state` (`:3325`); `contract_refresh_timestamp_utc`: no producer | 20260911_115904 Lab book / morning trades: none of the five fields present; `monetisability_refresh_status = PENDING_MORNING_REFRESH` 1,444/1,444 even on the 69 refreshed rows; `monetisability_quote_timestamp_utc` stays 10 Sep on those 69 (economics not recomputed with the refreshed quote) | NOT IMPLEMENTED (UAT-D-D6, P1) | no |
| ALG-16 | D7 assessment_id recompute + one-field mutation | 5 synthetic assessments (3 CALL, 2 PUT symbols) | — | — | `domain/dynamic_options_intelligence.py:190-196` (`sha256("DOI_CONTRACT_ASSESSMENT_V1|" + canonical_json)`), `:473-481` (components `family_id, contract_symbol, observation_id, calculation_version, evidence_cutoff_utc`); family identity includes `run_id` (`:344-352`) | production formula recompute 5/5 equal; ALG-16 formula 0/5 equal. Mutating observation_id, calculation_version, cutoff or symbol changes the id (5/5). Mutating run_id, input_dataset_ids or feature_version leaves it unchanged. `thesis_id` enters only via `family_id`. Cutoff serialised without milliseconds. 0 stored assessments | OPEN P1 (UAT-D-D7); NOT TESTED at run level (0 rows) | no — source does not match ALG-16 |
| REQ-WP3-06 / ALG-06, ALG-07 | D8 `p_*`/probability fields null unless CALIBRATED; `ranking_score_kind = DETERMINISTIC_UTILITY` | Lab book: `ev3_p_target/stop/timeout` non-null 129; `win_prob_predicted` 798 (range to 1.0); `layer2__adjusted_prob_target_hit` 798; `doi_p_*` 0 | `ev3_p_*` 94; `win_prob_predicted` 458; `layer2__*prob*` 458; `doi_p_*` 0 | `win_prob_predicted` 188; `layer2__*prob*` 188; `ev3_p_*` 0 | DOI domain guard `domain/dynamic_options_intelligence.py:454`; kind literals `domain/contract_economics_v2.py:150` and `canonical_data/dynamic_options_valuation.py:424` (`DETERMINISTIC_UTILITY`) vs `domain/dynamic_options_ranking.py:406` (`RANKING_SCORE_UNCALIBRATED`); no Lab schema test for `p_*` nullness found in `tests/` | 20260911_115904 `final_opportunity_book` and `lab_triage_view` carry no `calibration_state` or `ranking_score_kind` column. `lab_signal_book_v3` (GO rows): `ev3_p_*` 5 CALL, `win_prob_predicted` 19 (10 CALL / 9 PUT). Same pattern on 20260910_150045 | OPEN — P0 candidate on TEST runs (UAT-D-D8) | CLOSED OFFLINE for DOI assessments only (guard `:454`; `test_dynamic_options_deterministic_valuation.py:331`) |

## Per-check notes
**D1.** From `p13_D_d1b_identity.json`. Every `dropoff_audit` ticker (3,320) is either in the governed book (1,444: 992 `AFTER_EOD_BEFORE_MORNING` + 452 `OPTIONS_INTELLIGENCE`, all retained) or not in it with a non-empty `dropoff_reason` (1,876). No ticker is both absent and reasonless.

Stage ladder (`p13_D_d1_reconciliation.txt`), primary run:
- Discovery 3,320 → 1,572 `ACTIVE_CORE` + 1,748 dropped with reason (0 without).
- 1,572 packages = 1,522 Vanguard passed + 50 rejects.
- 1,522 → 1,444 options rows + 78 `NOT_SCOPED` (all 78 labelled in `vanguard_signals_enriched`, 0 unlabelled).
- Options 1,444 → EIL → execution → morning → Lab book 1,444, every step 1:1.
- Lab book 1,444 → v3 19 + 1,425 non-GO.

DEV-16 silent-removal paths did not remove any ticker on either run: `packages = passed + rejects` shows Vanguard `:1444` did not fire, and `NOT_SCOPED` covers all 78 Options Intelligence scope exits. The run's own `final_run_manifest.row_counts` (discovery 1,572, vanguard 1,522, options/eil/execution/morning 1,444) and `cds3.reconciled = true` agree. The first-pass probe's "unexplained 992" counted in-book rows with a blank drop reason; that is not a gap. Re-check: `python probes/p13_D_d1b_identity.py`.

**D2.** From `p13_D_d2_doi_projection.json`. The CALL/PUT/OTHER split is in the Results row. `doi_governed_contract_symbol` is non-null 1,218 and equals `contract_symbol` on all 1,218. The 63 mismatches are therefore against the morning-selected contract, not the book symbol; this probe did not resolve which morning field differs. `doi_decision_authority = NONE` on 1,444/1,444. `DATA_UNAVAILABLE` count 1,381, reason `DOI_TABLES_NOT_ACTIVATED` on all of them: the families table has 1,218 rows for the run but assessments/decisions have 0. Re-check: `python probes/p13_D_d2_doi_projection.py`.

**D3.** From `p13_D_d3_thesis_trace.json` and `p13_D_d3b_exceptions.json`. Where both sides carry a thesis_id they agree (1,218/1,218). The 38 exceptions:
- In the options CSV they have no `recommended_contract`, `liquidity_state` or quote.
- In `contract_rejection_log`: 37 `CHAIN_FETCH_FAILED`, 1 `UNDERLYING_DATA_STALE`.
- In the book they carry run-scoped legacy thesis_ids (`thesis_state = LEGACY_NOT_EVALUATED` 38).
- `morning_execution_permission = NOT_ELIGIBLE` 38.

So they are retained and named, but the REQ acceptance (`MISSING_GOVERNED_THESIS_ID = 0`) fails. DOI input column census: `evidence_cutoff_utc` absent (the DOI uses `quote_timestamp_utc`, missing on 226). Re-check: `python probes/p13_D_d3_thesis_trace.py`, then `p13_D_d3b_exceptions.py`.

**D4.** From `p13_D_d4_lifecycle.json`. Primary run, first options row per ticker with a contract (1,218):
- OI < 100: 834; volume = 0: 665; either: 924 (CALL 601, PUT 323).
- `liquidity_state` of those 924: `LIQUIDITY_PENDING` 327, `EXECUTABLE_NOW` 288, `LIFECYCLE_DATA_INCOMPLETE` 136, `REVIEWABLE_SPREAD` 109, others 64.
- `LIQUIDITY_PENDING` is driven by spread above the reviewable limit (`domain/option_contract_liquidity.py:498-503`), not by OI.

`contracts_tested` jsonl carries no OI/volume field per contract, so candidate-level removal can only be bounded via the DOI report: 130,443 candidates, 97,267 low-OI and 106,306 zero-volume retained. The 14,514 bounded candidates are a family-size bound, not an OI filter. Re-check: `python probes/p13_D_d4_lifecycle.py`.

**D5.** Two parts:
- From `p13_D_d5_executable_now.json`: the 69 Lab-book `EXECUTABLE_NOW` rows (47 CALL / 22 PUT) all pass bid > 0, ask > bid, spread/mid ≤ 0.18 (median 0.132) and provider ts within 15 min of `morning_gate_summary.validated_at_utc`. The same holds on `execution_gated` 69, `execution_actionable` 19 and v3 19.
- From `p13_D_d5b_quote_truth.json`: `EXECUTABLE_NOW` also exists where ALG-12 forbids it. Primary options CSV has 453 rows with quotes from the prior session, 18–19 h before the cutoff. The comparison EOD run's final book has 458 `executable_now = True` with no post-open refresh, and no run carries `run_condition`.

The downgrade to `QUOTE_STALE` happens only in the morning gate; the EOD run publishes its 458 unchanged. The spec's comparison reference `contract_refresh_timestamp_utc` does not exist; gate time was used instead. Re-check: `python probes/p13_D_d5_executable_now.py`, `p13_D_d5b_quote_truth.py`.

**D6.** From `p13_D_d6_hysteresis.json`. There are 1,191 common tickers with a contract on both days in the same direction; 79 changed contract (examples: VITL 261016C10 → 260918C10; CSCO 260925C109 → C108).
- In the control plane, the 11 Sep run has 949 events with a previous symbol, of which only 8 differ, all `MORNING_REPAIR_ALTERNATIVE_SELECTED` with metadata `{morning_transition_state}` only.
- The 10 Sep EOD selection has 0 events with a previous symbol, so the EOD selector does not see the incumbent.
- No stored utility means `U_c − U_i ≥ max(0.05, 0.10·|U_i|)` cannot be evaluated for any switch.

Re-check: `python probes/p13_D_d6_hysteresis.py`.

**D7.** From `p13_D_d7_assessment_identity.json`. `ContractAssessment.create` was called directly with five synthetic component sets; no stored assessment exists to sample. The production formula is self-consistent and changes on every economic one-field mutation. It differs from ALG-16 in four ways:
- A namespace prefix.
- `family_id` in place of `thesis_id`, and `family_id` includes `run_id` (`:344-352`), so the same thesis/contract/observation re-assessed in another run gets a different id.
- `observation_id` in place of `observation_dataset_id`.
- Second-precision ISO timestamps where ALG-16 specifies milliseconds.

Re-check: `python probes/p13_D_d7_assessment_identity.py`.

**D8.** From `p13_D_d8b_probability_fields.json`. `doi_p_liquidity_3d`, `doi_p_positive_return`, `doi_p_target_before_invalidation` and `doi_model_uncertainty` are null 1,444/1,444 (compliant). Probability-named fields from other engines are populated with no calibration disclosure:
- `ev3_p_target` range 0.0001–0.680.
- `win_prob_predicted` range 0.005–1.000 on all three directions.
- `layer2__adjusted_prob_target_hit` range 0.008–0.589.
- `phase_transition_probability` 32–61 (percent scale).

`morning_validated_trades` adds `win_rate_5d/10d`, `layer2__raw_prob_up/down_*` and `layer2__baseline_probability`; its only calibration column is `ms_parameter_calibration_status`, non-null 19. No Lab book has `calibration_state` or `ranking_score_kind`. Re-check: `python probes/p13_D_d8b_probability_fields.py`. RESEARCH_ONLY: values are reported for schema only, not as edge.

**Tests.** Run 2026-09-13 with `tools/run_governed_pytest.py -q … -p no:cacheprovider`:
- `test_dynamic_options_ranking.py` 14 passed
- `test_dynamic_options_lifecycle.py` 17 passed
- `test_dynamic_options_non_discard_policy.py` 4 passed
- `test_option_liquidity_lifecycle.py` 16 passed
- `test_doi11_production_integration.py` 6 passed

Output: `probes/p13_D_pytest_wp3.txt`. The earlier worker's `p13_D_pytest_lifecycle.txt` (35 passed) does not record its target file.

## Defects (UAT-D-D<n>)
**UAT-D-D1** — REQ-WP3-01 — P1 — exposure CALL 26, PUT 12, OTHER 188 (non-directional path).
- Evidence: 20260911_115904 `dynamic_options_intelligence_*.json` `exceptions[reason = MISSING_GOVERNED_THESIS_ID]` = 38. Options CSV `thesis_id` null for these 38 while `final_opportunity_book.thesis_id` is populated (`ARW:CALL:20260911_115904` …). DOI input lacks `evidence_cutoff_utc`. `governed_direction_records` has 0/1,444 thesis_id. Code: `canonical_data/dynamic_options_production.py:157-169`.
- Reproduce: `probes/p13_D_d3_thesis_trace.py`, `p13_D_d3b_exceptions.py`.
- Close when: a normal run shows DOI input directed rows = book directed rows with identical thesis_id/hold/spot/cutoff/target/invalidation, and `MISSING_GOVERNED_THESIS_ID = 0`.
- TRACE: REQ-WP3-01 | ALG-NONE | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-options_intelligence_20260911_115904.csv,dynamic_options_intelligence_20260911_115904.json | N=38

**UAT-D-D2** — REQ-WP3-02 — P1 — exposure CALL 798, PUT 458, OTHER 188.
- Evidence: Lab book `doi_projection_reason` `DOI_TABLES_NOT_ACTIVATED` 1,381 (761/432/188), `GOVERNED_CONTRACT_IDENTITY_MISMATCH` 63 (37/26/0). DOI report `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` 1,218. `doi_contract_assessments` 0 rows. Comparison run 1,424/1,424 not activated.
- Reproduce: `probes/p13_D_d2_doi_projection.py`.
- Close when: a normal run shows `DOI_TABLES_NOT_ACTIVATED = 0`, `FAMILY_NOT_VALUED_RATE_UNAVAILABLE = 0`, and mismatch = 0 on published preferred contracts, with preferred contract, alternatives and ranking score non-null on every scoreable row.
- TRACE: REQ-WP3-02 | ALG-06 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-final_opportunity_book_20260911_115904.csv | N=1444

**UAT-D-D3** — REQ-WP3-03 / ALG-12 — **P0 candidate (TEST-run caveat: both runs are forced, dirty-tree, pre-remediation)** — stale or non-refresh quote marked executable — exposure primary options CSV CALL 255 / PUT 198 / OTHER 0; comparison final book CALL 262 / PUT 196 / OTHER 0.
- Evidence: 20260911_115904 `options_intelligence` has `executable_now = True` with `contract_quote_timestamp_utc` on 2026-09-10, 1,086–1,144 min before cutoff (453 rows).
- 20260910_150045 (`pipeline_mode = EOD`, no morning gate): `final_opportunity_book.executable_now = True` 458, `morning_quote_timestamp_utc` null.
- `run_condition` null on every run.
- Code: `domain/option_contract_liquidity.py:449` skips freshness when `quote_age_seconds` is None, and there is no `POSTOPEN_CONTRACT_REFRESH` precondition before `EXECUTABLE_NOW` at `:489-491`.
- Containment on primary: Lab book `QUOTE_STALE` 453, and the 69 remaining pass.
- Reproduce: `probes/p13_D_d5b_quote_truth.py`.
- Close when: on a normal EOD run and a post-open refresh run, `EXECUTABLE_NOW` count = 0 outside `POSTOPEN_CONTRACT_REFRESH`, every `EXECUTABLE_NOW` has a provider ts within F of `contract_refresh_timestamp_utc`, and a missing provider ts yields `EXECUTION_QUOTE_UNAVAILABLE`.
- TRACE: REQ-WP3-03 | ALG-12 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-options_intelligence_20260911_115904.csv,final_opportunity_book_20260910_150045.csv | N=911

**UAT-D-D4** — REQ-WP3-03 — P1 — exposure CALL 772, PUT 446, OTHER 0.
- Evidence: three independent identity/execution/activity machines are absent. There is one `liquidity_state` enum (`domain/option_contract_liquidity.py:47-49`), no producer of `ACTIVITY_*` or `EXECUTION_*` states, and no inbound/outbound `CONTRACT_REPAIR_REQUIRED` identity transition in the stored vocabulary. `option_contract_observations.correction_state` is null on 10,522/10,522.
- Reproduce: Grep `ACTIVITY_THIN|EXECUTION_EXECUTABLE_NOW` in `*.py`; `probes/p13_D_d4_lifecycle.py`.
- Close when: fixtures exist per transition for the three machines, a run artefact shows a row that is simultaneously `ACTIVITY_THIN` and `EXECUTION_EXECUTABLE_NOW`, and a later observation appends rather than mutates.
- TRACE: REQ-WP3-03 | ALG-12 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-control_plane.option_contract_observations | N=10522

**UAT-D-D5** — REQ-WP3-04 / ALG-11 — P1 — exposure CALL 57 flips, PUT 22, OTHER 0.
- Evidence: `PreferredContractSuperseded` not in code. `option_contract_selection_events` carries no `U_i/U_c/margin/supersession_reason`. `doi_preferred_contract_decisions` 0 rows. 79/1,191 contract changes 10→11 Sep cannot be tested against the margin.
- Reproduce: `probes/p13_D_d6_hysteresis.py`.
- Close when: a replay of two consecutive normal runs shows every switch with `U_c − U_i ≥ max(0.05, 0.10·|U_i|)` or reason EXPIRED/MALFORMED/DEFECT, emitted as `PreferredContractSuperseded` with prior symbol and reason.
- TRACE: REQ-WP3-04 | ALG-11 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-options_intelligence_20260910_150045.csv,options_intelligence_20260911_115904.csv | N=79

**UAT-D-D6** — REQ-WP3-05 — P1 — exposure CALL 47, PUT 22 refreshed rows, OTHER 0.
- Evidence: `morning_refresh_state`, `contract_refresh_timestamp_utc`, `THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE` have no producer. `refresh_window_state` is published under a different name (`morning_gate.py:3325`) and absent from stored artefacts.
- On the 69 refreshed rows `monetisability_quote_timestamp_utc` remains the 10 Sep quote, so contract economics were not recomputed atomically with the new observation. `monetisability_refresh_status = PENDING_MORNING_REFRESH` 1,444/1,444.
- Reproduce: `probes/p13_D_d5b_quote_truth.py` (`refresh_values`, `ts::monetisability_quote_timestamp_utc`).
- Close when: an adversarial crossed-market fixture and a post-open run show a replacement searched, the original retained, a supersession event, and every economics field carrying the new `assessment_id`.
- TRACE: REQ-WP3-05 | ALG-12 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-morning_validated_trades_20260911_115904.csv | N=69

**UAT-D-D7** — ALG-16 (REQ-WP3-05 lineage) — P1 — exposure CALL/PUT all assessments (0 stored), OTHER n/a.
- Evidence: `domain/dynamic_options_intelligence.py:194-196`, `:473-481` hash `namespace|{family_id, contract_symbol, observation_id, calculation_version, evidence_cutoff_utc}`. ALG-16 recompute 0/5 equal.
- `run_id` enters via `family_id` (`:344-352`), so cross-run identity differs for identical economics. Timestamps have no milliseconds.
- Reproduce: `probes/p13_D_d7_assessment_identity.py`.
- Close when: five stored assessments recompute exactly from the ALG-16 components, an economic one-field mutation changes the id, and a transport/run-only change does not.
- TRACE: REQ-WP3-05 | ALG-16 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-p13_D_d7_assessment_identity.json | N=5

**UAT-D-D8** — REQ-WP3-06 — **P0 candidate (TEST-run caveat)** — uncalibrated numbers shown as probabilities — exposure CALL 798, PUT 458, OTHER 188 (`win_prob_predicted`); `ev3_p_*` CALL 129 / PUT 94.
- Evidence: 20260911_115904 `final_opportunity_book` non-null `win_prob_predicted` 1,444 (max 1.0), `layer2__adjusted_prob_target_hit` 1,444, `ev3_p_target/stop/timeout` 223. `lab_signal_book_v3` `win_prob_predicted` 19 and `ev3_p_*` 5.
- No `calibration_state` or `ranking_score_kind` column on any Lab book, and no Lab schema test enforcing nullness.
- Reproduce: `probes/p13_D_d8b_probability_fields.py`.
- Close when: a Lab schema test and a normal-run book show every `p_*` / `*_probability` / `*prob*` field null unless `calibration_state = CALIBRATED`, with `ranking_score_kind = DETERMINISTIC_UTILITY` present.
- TRACE: REQ-WP3-06 | ALG-07 | WP-3 | STAGE-5 | TRACK-D | EVIDENCE-final_opportunity_book_20260911_115904.csv | N=1444

**UAT-D-D9** — REQ-WP3-01 reconciliation / SD invariant 1 — P2 (lineage; identity closes) — exposure OTHER (pre-direction stages) 1,826.
- Evidence: 1,748 Discovery exceptions collapse seven causes into `NO_SIGNAL_AT_ANY_HORIZON` (`avshunter_discovery_ULTIMATE.py:2536-2545`, DEV-15). 78 `NOT_SCOPED` carry no cause distinguishing tier scope from WAIT scope (`scripts/avshunter_options_intelligence.py:8797-8808`); the cause survives only as the heuristic reconstruction in `dropoff_audit.py:240-255`. No single run-summary artefact states `input = presented + named`.
- Reproduce: `probes/p13_D_d1b_identity.py`.
- Close when: a normal run has one reconciliation artefact with per-stage named reason codes that recover the removal cause.
- TRACE: REQ-WP3-01 | ALG-NONE | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-discovery_lifecycle_20260911_115904.csv,vanguard_signals_enriched_20260911_115904.csv | N=1826

## Deviations
| claimed | found | evidence | severity |
|---|---|---|---|
| DEV-16: five silent removal points exist (severity deferred to Track D) | On both stored runs the silent paths removed 0 tickers; ticker-grain identity has gap 0 | `p13_D_d1b_identity.json` | P2 (latent; would be P0 if they fire) |
| REQ-WP3-06 / Annex: `ranking_score_kind = DETERMINISTIC_UTILITY` | Two kinds coexist: `DETERMINISTIC_UTILITY` (`domain/contract_economics_v2.py:150`, `canonical_data/dynamic_options_valuation.py:424`) and `RANKING_SCORE_UNCALIBRATED` (`domain/dynamic_options_ranking.py:406`) | source | P2 |
| ALG-16 `assessment_id` components | namespace + family_id(run-scoped) + observation_id, no ms | UAT-D-D7 | P1 |
| DOI families carry the thesis origin for the run | Primary-run families (11 Sep, cutoff 11:59Z) have `created_at = origin_timestamp_utc = evidence_cutoff_utc` 2026-09-10T16:54:02Z–17:53:13Z, identical to the comparison run's families. The comparison run's cutoff is 15:00:45Z, so its family evidence cutoffs are 1h53–2h52 after the run cutoff. For the same origin timestamp `origin_spot` differs between runs (PLAB 28.56 vs 28.38) | `p13_D_d3b_exceptions.json` `families_created_at_vs_origin`, `families_sample` | P2 |
| Evidence cutoff bounds quotes used by the run | Primary Lab `EXECUTABLE_NOW` quotes +301–306 min after `evidence_cutoff_utc`; comparison options/final book quotes +114–172 min after | `p13_D_d5b_quote_truth.json` | P2 (Track A overlap) |
| REQ-WP3-05: `refresh_window_state` | Published as `postopen_contract_refresh_window_state` (`morning_gate.py:3325`) | source | P3 |
| Thesis identity format is governed | Book thesis_id formats: `T:DIR:<date>:OLM2` 1,218, `T:UNRESOLVED:<run>` 188, `T:DIR:<run>` 38 (legacy run-scoped for the DOI exceptions) | `p13_D_d3b_exceptions.json` `fob_thesis_id_formats` | P2 |
| Options Intelligence OI thresholds | `EV3_MIN_OPEN_INTEREST = 50`, `EV3_MIN_VOLUME = 1` defined (`scripts/avshunter_options_intelligence.py:1335-1336`) with no reference; `MIN_OI = 50` limits only the Heston calibration sample (`:2061`) | Grep | P3 |
| Probability naming | `phase_transition_probability` holds 32–61 (percent) | `p13_D_d8b_probability_fields.json` | P3 |

## Premise notes
- D4: 924 of 1,218 selected contracts (75.9%) are thin (OI < 100 or volume = 0), and 288 of them are `EXECUTABLE_NOW` on spread/quote. At candidate level the DOI report retains 74.6% low-OI and 81.5% zero-volume. Spec: OI/volume is activity-only. Measured: activity thinness is the majority state, so the activity machine will label most of the book `ACTIVITY_THIN`; separating it from executability matters for ~¾ of rows.
- D6: the measured day-over-day contract change rate is 6.6% (expected 40–70%). 40 of 79 changes are a single strike-increment shift with unchanged expiry, and 22 are expiry-only. Spec: hysteresis on utility margin. Measured: the EOD selector recorded no incumbent on 10 Sep (0 events with previous symbol), so switches arise from reselection without incumbent, not from a utility comparison. Gap: 79 switches with no utility to compare.
- D5: the freshness rule is measured against gate time. Primary-run refreshed quotes are ~5 h after the run's own evidence cutoff, so a `NORMAL_COMPLETED_SESSION` cutoff and a post-open refresh cannot share one `evidence_cutoff_utc` field. Gap: 301–306 min.

## Not tested / blocked
- D5 post-open refresh run: NOT TESTED. No run has `run_condition = POSTOPEN_CONTRACT_REFRESH`; `run_condition` is null on all runs; `contract_refresh_timestamp_utc` is absent. Gate time was used as the substitute reference.
- D6 margin verification: NOT TESTED at run level. No `U_i`/`U_c` is stored (`doi_preferred_contract_decisions` 0, no margin keys in selection events). The ALG-11 expiry fixture exists offline only (`test_dynamic_options_lifecycle.py:150`).
- D7 on stored assessments: NOT TESTED. `doi_contract_assessments` has 0 rows in the DB copy; synthetic assessments were used.
- D1 before Discovery input: NOT TESTED. Blank/duplicate removal at `avshunter_discovery_ULTIMATE.py:887`, package-build duplicates at `scripts/build_packages_from_discovery.py:316-329`, `:570-574`, and DOI `:139-140` leave no pre-dedupe count in any artefact. DOI input rows = unique tickers (1,444) on the primary run, so `:139-140` removed no ticker there; the 14,784-row options CSV collapses to first row per ticker by design.
- REQ-WP3-05 adversarial crossed-market fixture: NOT TESTED. No test named for it in the WP3 test files; would need a fixture the tester may not write into `tests/`.
- D2 identity of the 63 mismatching contracts against the morning-selected symbol: not resolved (see D2 note).

## Expectation vs actual
| check | expectation (E) | actual | gap |
|---|---|---|---|
| D1 | Identity does not hold; unexplained gap > 0 → P0 candidate | Identity holds on both runs (gap 0); named-exception quality P2 | Expected P0 not found; the 3,320 Discovery input reconciles fully |
| D2 | 1,381 `DOI_TABLES_NOT_ACTIVATED`, 63 mismatch | 1,381 / 63 exactly (CALL 761/37, PUT 432/26, OTHER 188/0) | none |
| D3 | Triage thesis_id 1,444/1,444; DOI input missing > 0 | Book 1,444/1,444 non-null; DOI input missing 226 (188 OTHER + 26 CALL + 12 PUT); differ 0 | Matches; unexpected that the 38 book ids are legacy run-scoped |
| D4 | OI < 100 / vol 0 removed > 0 (rejection log) → OPEN | 0 OI/volume removals; 924 thin retained; OI non-removal CLOSED OFFLINE; three-machine design NOT IMPLEMENTED | Expected removal not found |
| D5 | NOT TESTED (no post-open run) | Post-open part NOT TESTED; but 453 (primary options CSV) and 458 (comparison EOD book) stale/non-refresh `EXECUTABLE_NOW` → P0 candidate; 69 Lab rows pass | Unexpected P0 candidate |
| D6 | Flip rate 40–70%; no margin fields → NOT IMPLEMENTED | Flip rate 6.6% (CALL 7.5%, PUT 5.1%); no margin fields → NOT IMPLEMENTED at run level | Flip rate ~6–10× lower than expected |
| D7 | Absent from runs; CLOSED OFFLINE if hash matches | Absent from runs (0 rows); hash matches production formula 5/5 but ALG-16 0/5 → OPEN P1 | Expected CLOSED OFFLINE not reached |
| D8 | ≥ 1 non-null `p_*` without calibration_state → P0 candidate | Confirmed: `win_prob_predicted` 1,444, `ev3_p_*` 223, `layer2` prob 1,444; `doi_p_*` all null | Matches; exposure wider than EV3 shadow alone |

## State log lines
```
step,state,n,duration,note
D1,DONE,3320,5m,identity gap 0 both runs; P2 named-exception quality (UAT-D-D9)
D2,DONE,1444,3m,DOI_TABLES_NOT_ACTIVATED 1381 / MISMATCH 63; OPEN P1
D3,DONE,1444,4m,MISSING_GOVERNED_THESIS_ID 38 (26 CALL/12 PUT); 0 differ; OPEN P1
D4,DONE,1218,4m,0 OI/vol removals; 924 thin retained; 3 state machines NOT IMPLEMENTED
D5,DONE,69,6m,69 Lab rows pass; 453+458 stale/non-refresh EXECUTABLE_NOW P0 candidate; post-open NOT TESTED
D6,DONE,1191,2m,flip 79/1191 6.6%; no margin/U stored; NOT IMPLEMENTED run level
D7,DONE,5,1m,production recompute 5/5; ALG-16 0/5; OPEN P1; 0 stored assessments
D8,DONE,1444,3m,non-null probability fields without calibration_state; P0 candidate
D-pytest,DONE,57,6m,5 WP3 test files 57 passed 0 failed
```
