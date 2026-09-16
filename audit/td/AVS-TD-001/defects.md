# Acceptance defects — AVS-UAT-FIX-002 (§6 item 10)

**No NORMAL_COMPLETED_SESSION run exists; every defect below was observed on TEST-condition runs or offline.**

Runs: primary `20260911_115904` and comparison `20260910_150045`. Both are TEST (dirty tree `avs-baseline-20260906-21-g00baa2b-dirty`, forced intra-session) and were produced by commit 00baa2b, before every remediation commit. Source checks were made at HEAD `cc509cb`. Evidence paths are relative to the repository root; probe paths are relative to `audit/td/AVS-TD-001/`.

The defects are numbered P0 first, then P1, P2 and P3. Within each severity they are ordered by track letter; a merged entry sorts by its lowest original ID. Merged entries list every original ID and keep the highest severity. No fix is proposed; "To close" states only what closure evidence must show.

---

## P0

### UAT-D01 — Recorded evidence cutoff contradicted by provider requests made after it
- **Original ID:** UAT-D-A1
- **REQ:** REQ-WP0-01 · **Severity:** P0 (irreproducible assessment: a replay honouring the recorded cutoff cannot see the evidence the run used)
- **Exposure:** run-level, all rows. 11 Sep: CALL 798 / PUT 458 / OTHER 188. 10 Sep: 1,424 rows (no direction split computed).
- **Evidence:**
  - `data/output/runs/20260911_115904/run_meta.json:15` records `dynamic_plan.evidence_cutoff_utc = 2026-09-11T11:59:04Z`. In `api_request_ledger`, 6,810 of 6,810 requests started 12:49:07Z–17:08:47Z (2,796 physical), and the run carries 1,220 distinct ledger `evidence_cutoff_utc` values.
  - `20260910_150045/run_meta.json:15` records a cutoff of 15:00:45Z; 5,472 of 5,472 requests ran 15:45:48Z–18:08:09Z.
  - 13 of 13 run_meta runs with ledger rows are affected.
  - At cc509cb the cutoff and condition are written by `intelligent_orchestrator.py:2044-2122`; no stored run exercises that code.
- **Reproduction:** `python probes/p10_A_ledger_after_cutoff.py`; compare `cutoff_used` to `min_started` / `n_after_cutoff` per run.
- **To close:** a stored clean-tree run whose `run_meta_v2.evidence_cutoff_utc` is ≥ every `api_request_ledger.started_at` for its run_id, or whose post-cutoff requests are recorded as a separately labelled refresh with its own cutoff and condition. `n_after_cutoff = 0` for the governed evidence set.
- TRACE: REQ-WP0-01 | ALG-NONE | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-run_meta.json+control_plane.api_request_ledger | N=13 runs (12,282 requests on the two reference runs)

### UAT-D02 — Stale, prior-session or non-refreshed quotes presented as executable or FRESH
- **Original IDs:** UAT-D-A7 (P0), UAT-D-D3 (P0 candidate), UAT-D-G4 (P0), UAT-D-I4 (P0), UAT-D-A4 (P1, merged: same FRESH-on-stale mechanism G4 reports)
- **REQ:** REQ-WP0-03, REQ-WP0-04, REQ-WP3-03, REQ-WP6-02 (SD §9.3), Rule 7 · ALG-12 · **Severity:** P0 (stale quote executable)
- **Exposure:**
  - A7: `final_opportunity_book` 20260911 has EXECUTABLE_NOW on CALL 47 (GO_LIMIT 10) / PUT 22 (GO_LIMIT 9) / OTHER 0.
  - A4: `quote_freshness=FRESH` on 453 prior-session rows (CALL 255 / PUT 198 / OTHER 0), including the 391 FLAG `REJECT_QUOTE_STALE` rows (CALL 207 / PUT 184).
  - D3: `options_intelligence` 20260911 has EXECUTABLE_NOW on prior-session quotes for CALL 255 / PUT 198 / OTHER 0. The 20260910 EOD final book has `executable_now=True` on CALL 262 / PUT 196 / OTHER 0 with no refresh.
  - G4: `lab_signal_book_v3` has STALE plus GO_LIMIT on CALL 10 / PUT 9 / OTHER 0. On the final book, all 81 prior-session `eil_v3_verdict=EXECUTE` rows are labelled FRESH (CALL 43 / PUT 38).
  - I4: morning handoff rows for CALL and PUT; OTHER not tested.
- **Evidence (source, cc509cb):**
  - `morning_gate.py:2046-2051` sets the EXECUTABLE_NOW transition from `liquidity_state` alone. `:2205-2211` gates only POSTOPEN rows with a missing timestamp. There is no `run_condition` check.
  - `morning_gate.py:2065` sets `quote_freshness="FRESH"` unconditionally (it was `00baa2b:2012`).
  - `domain/option_contract_liquidity.py:449`: when `quote_age_seconds` is None the freshness check is skipped, and the row falls through to EXECUTABLE_NOW at `:489-491`.
  - `contracts/quote_change_evidence.py:187-193,248` computes freshness as a live-TTL age at handoff and sets `quote_age_affects_thesis=False`; `contracts/lab_control.py:2618` copies the token.
  - `contracts/interpreter_handoff_materializer.py:293-301` sets `execution_quote_refresh_required=False` and `execution_quote_human_confirmation_required=False` on every row.
- **Evidence (tests, Rule 7):** commit 57a99d7 weakened two test files.
  - `tests/test_msi_handoff_materializer.py`: for a prior-session quote, `final_action` changed from `MANUAL_REQUOTE_REQUIRED` to `BUY_NOW`.
  - `tests/test_msi_interpreter_handoff.py`: the `EVIDENCE_REFRESH_REQUIRED` raise on a STALE bundle was removed.
  - `tests/msi/test_flow.py::test_w05_stale_interpreter_request_fails_closed_no_refresh_executed` still asserts the old rule and fails.
- **Evidence (runs):**
  - 20260911_115904: quotes are timestamped 17:00:07Z–17:05:07Z, about 5 h after the recorded cutoff of 11:59:04Z.
  - Quote age at the gate was 3.2–6.9 min. When `lab_signal_book_v3.csv` was written (17:18:42Z), 54/69 EXECUTABLE_NOW rows (CALL 40 / PUT 14) and 6/19 GO_LIMIT rows were > 15 min old.
  - At `final_run_manifest.created_at_utc` 18:39:10Z, with `run_tradeable_label=EXECUTION_READY`, 69/69 and 19/19 were > 15 min old.
  - `lab_signal_book_v3.csv` has `quote_freshness=STALE` on 19/19 GO rows, alongside `executable_now=True`, `is_stale=False` and `final_action=BUY_SMALL`. The final book labels the identical quotes FRESH.
  - `options_intelligence_20260911_115904.csv`: 453 EXECUTABLE_NOW rows with `contract_quote_timestamp_utc` on 2026-09-10, 1,086–1,144 min before the cutoff.
  - `final_opportunity_book_20260910_150045.csv`: `executable_now=True` on 458 rows with `morning_quote_timestamp_utc` null.
  - No run carries `run_condition`.
- **Reproduction:**
  - `python probes/p10_A_exec_now_split.py`, then `p10_A_quote_timestamps.py`, `p13_D_d5b_quote_truth.py` and `p16_G_g2b_quote_freshness.py`.
  - `git diff avs-baseline-20260906..HEAD -- tests/test_msi_handoff_materializer.py tests/test_msi_interpreter_handoff.py`
- **To close:**
  - Source refuses EXECUTION_EXECUTABLE_NOW unless `run_condition == POSTOPEN_CONTRACT_REFRESH`, and a missing provider timestamp yields `EXECUTION_QUOTE_UNAVAILABLE`.
  - `quote_freshness` is derived from provider-timestamp age against the governed F, with one freshness authority. STALE never coexists with an executable permission, and prior-session quotes are never FRESH.
  - A stored PREOPEN run and a stored normal EOD run show 0 EXECUTABLE_NOW (CALL/PUT/OTHER).
  - A stored POSTOPEN run shows every EXECUTABLE_NOW with a provider timestamp within F of `contract_refresh_timestamp_utc`. It records `refresh_window_state`, and no published artefact presents a row as executable whose quote age exceeds F at publication without a re-check or expiry state.
  - The original fail-closed assertions, or stricter ones, are restored and W05 passes.
- TRACE: REQ-WP0-04 | ALG-12 | WP-0,WP-3,WP-6 | STAGE-1 | TRACK-A,D,G,I | EVIDENCE-final_opportunity_book_20260911_115904.csv,lab_signal_book_v3.csv,options_intelligence_20260911_115904.csv,final_opportunity_book_20260910_150045.csv,contracts/interpreter_handoff_materializer.py:293 | N=69 (A7) + 453 (A4) + 911 (D3) + 19/453 (G4) + 2 test files (I4)

### UAT-D03 — Macro packet cannot be resolved by ID; runs record "latest"
- **Original ID:** UAT-D-A5
- **REQ:** REQ-WP0-06 · **Severity:** P0 (irreproducible assessment: the 10 Sep macro input cannot be recovered)
- **Exposure:** run-level, all rows on both reference runs (CALL 798 / PUT 458 / OTHER 188 on 11 Sep; 1,424 on 10 Sep).
- **Evidence:**
  - `data/macro/archive/` does not exist. `dropbox/macro/Archive/` holds 15 hand-named files, none with a `packet_id`.
  - Line 30 of `run_meta.json` on both runs: `macro_source_path = …/dropbox/macro/macro_intelligence_latest.json`. There is no `macro_packet_id` or `macro_packet_sha256`.
  - `load_macro_packet_by_id("MACRO:2026-09-10:e86776c975d2f988")` raises `FileNotFoundError … resolved 0 archive entries` against both roots.
  - The 11 Sep run carries two packet identities with different hashes: `MACRO:2026-09-11:4788b5259e2db8fe` in `macro_quant_packet.json` and `MACRO:4627892190afab863b245da8` in `final_run_manifest.worker3_market_environment`.
  - `orchestrator/macro_loader.py:130,176` still resolves by the latest file. Source `canonical_data/macro_packet_archive.py:18-80` exists at cc509cb.
- **Reproduction:** `python probes/p10_A_macro_archive.py` → `resolve_attempt.calls`.
- **To close:**
  - A stored run records `macro_packet_id` plus a sha256 matching an archived file.
  - `load_macro_packet_by_id` returns that packet, the hash verifies, and replay resolves by ID; a missing ID fails with the named error.
  - The run has one packet identity across run_meta, macro_quant_packet and the worker3 manifest.
- TRACE: REQ-WP0-06 | ALG-16 | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-run_meta.json.macro_source_path+data/macro/archive | N=2 runs

### UAT-D04 — Uncalibrated numbers carried as probabilities with no calibration state
- **Original IDs:** UAT-D-D8 (P0 candidate), UAT-D-E4 (P0)
- **REQ:** REQ-WP3-06, REQ-WP4-04 · ALG-07 · **Severity:** P0 (uncalibrated number shown as probability)
- **Exposure:**
  - 20260911 `final_opportunity_book`: `win_prob_predicted` and `layer2__adjusted_prob_target_hit` on CALL 798 / PUT 458 / OTHER 188; `ev3_p_target/stop/timeout` on CALL 129 / PUT 94 / OTHER 0.
  - 20260910 book: the same pattern on CALL 791 / PUT 451 / OTHER 182.
  - `lab_signal_book_v3`: `win_prob_predicted` on 19 rows (CALL 10 / PUT 9); `ev3_p_*` on 5 CALL rows.
- **Evidence:**
  - Values: `win_prob_predicted` ranges 0.005–1.000 and `ev3_p_target` 0.0001–0.680. `phase_transition_probability` holds 32–61 (percent scale). `win_rate_source = ACTUARIAL` on 1,444/1,444.
  - No Lab book has a `calibration_state` or `ranking_score_kind` column, and no Lab schema test enforces nullness.
  - Calibration gate state is `INSUFFICIENT_OUTCOMES`: 0 resolved outcomes in every direction × hold stratum, and no calibration table or report exists.
  - The DOI guard `domain/dynamic_options_intelligence.py:454` covers only `doi_p_*`, which are null 1,444/1,444 (compliant).
  - Produced by 00baa2b. Current-code emission and operator rendering are not verified on a run.
- **Reproduction:** `python probes/p13_D_d8b_probability_fields.py`; `python probes/p14_E_e6_disclosure.py`.
- **To close:** a Lab schema test, plus a stored run on remediated code, showing every `p_*` / `*_probability` / `*prob*` field null, or explicitly labelled UNCALIBRATED, unless `calibration_state = CALIBRATED` after the ALG-09 gate passes, with `ranking_score_kind = DETERMINISTIC_UTILITY` present.
- TRACE: REQ-WP3-06 | ALG-07 | WP-3,WP-4 | STAGE-5,STAGE-6 | TRACK-D,E | EVIDENCE-final_opportunity_book_20260911_115904.csv,lab_signal_book_v3.csv | N=1444 (+1424 comparison)

---

## P1

### UAT-D05 — Intra-session option data registered as a completed session
- **Original ID:** UAT-D-A2 · **REQ:** REQ-WP0-02 / ALG-15 · **Severity:** P1
- **Exposure:** `option_contract_observations`: CALL 1,011 (11 Sep) + 653 (10 Sep); PUT 522 + 367; OTHER 0.
- **Evidence:**
  - In the control_plane copy, `dataset_registry` has `LIVE_OPTION` session 2026-09-10 marked `COMPLETE` (956 rows) with `as_of` 16:54–17:53Z, which is 12:54–13:53 ET while the market was open.
  - `api_request_ledger` has `evidence_state=COMPLETED_SESSION` on OPTION_CHAIN requests at 17:09Z on 10 Sep.
  - Computed session-date close coverage: 0/993 on the 11 Sep run, 0/1,020 on the 10 Sep run. The naive rule scores 0.54 and 1.0.
  - `provider_completeness_evidence` is absent from both run_meta files. Source at cc509cb: `domain/provider_finality.py`, `canonical_data/provider_finality.py:103`.
- **Reproduction:** `python probes/p10_A_provider_completeness.py`.
- **To close:** a stored Evening run whose `provider_completeness_evidence` records both denominators, state counts and thresholds. Intra-session-only chains are `PROVIDER_SESSION_PARTIAL` / `DATE_MISMATCH`, never `COMPLETE`, and the run's fraction matches the tester's recomputation within 1%.
- TRACE: REQ-WP0-02 | ALG-15 | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-control_plane.dataset_registry+option_contract_observations | N=2,553 obs

### UAT-D06 — Quote timestamps fabricated to equal gate time
- **Original ID:** UAT-D-A3 · **REQ:** REQ-WP0-04 / ALG-12 · **Severity:** P1 (the rows were not made executable)
- **Exposure:** CALL 26 / PUT 12 / OTHER 188.
- **Evidence:**
  - `00baa2b:morning_gate.py:1891` reads `quote_as_of … or _utc_now()`.
  - `morning_validated_trades_20260911_115904.csv`: 226 rows have `quote_as_of == gate_checked_at_utc` to the second. They are exactly the rows with an empty `selected_quote_timestamp_utc`, all `LEGACY_NOT_EVALUATED` / `NOT_ELIGIBLE`.
  - The same-session fraction of hydrated rows is 0.628.
  - cc509cb `morning_gate.py:1944` removes the fallback (offline only).
- **Reproduction:** `python probes/p10_A_quote_timestamps.py` → `per_ts_col.quote_as_of.eq_fetch_cols_to_second`.
- **To close:** a stored POSTOPEN_CONTRACT_REFRESH run with 0 rows where the fetch timestamp equals the provider timestamp (or `quote_as_of == gate_checked_at_utc`) to the second. Rows lacking a provider timestamp carry `CONTRACT_QUOTE_UNAVAILABLE`, and ≥ 95% of hydrated rows are same-session.
- TRACE: REQ-WP0-04 | ALG-12 | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-morning_validated_trades_20260911_115904.csv | N=226

### UAT-D07 — TEST runs labelled PRODUCTION / ACCEPTED / EXECUTION_READY without any REQ-WP0-01 field
- **Original ID:** UAT-D-A6 (covers DEV-04, DEV-17) · **REQ:** REQ-WP0-01 · **Severity:** P1
- **Exposure:** run-level. 11 Sep: CALL 798 / PUT 458 / OTHER 188. 10 Sep: 1,424 rows.
- **Evidence:**
  - `20260911_115904/run_meta.json`: `:24` git_describe `-dirty`, `:47` `MORNING_VALIDATION`, `:59` `run_kind PRODUCTION`, `:60` `run_meta_v2`, `:61` `run_status ACCEPTED`.
  - `20260910_150045/run_meta.json`: `:58` `PRODUCTION`, `:60` `COMPLETED`.
  - Both `final_run_manifest.json`: `run_tradeable=true`, `EXECUTION_READY`.
  - All nine REQ-WP0-01/02 fields are absent on 27/27 runs. `run_registry.run_type=EVENING` on the MORNING_VALIDATION run.
- **Reproduction:** `python probes/p10_A_run_inventory.py` → `req01_presence`, `run_kind`.
- **To close:** a forced intra-session run and a dirty-tree run stored with `run_condition=FORCED_INTRASESSION` / `TEST`, `baseline_eligible=false`, and code identity (with dirty flag), config identity, session date, cutoff and operator mode. A non-baseline run carries no PRODUCTION or EXECUTION_READY label, and `run_meta_v2` appears only on files carrying the v2 fields.
- TRACE: REQ-WP0-01 | ALG-16 | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-run_meta.json+final_run_manifest.json | N=27 runs

### UAT-D08 — Stage 0 import-graph gate passes while 25 reachable modules are outside the hashed manifest
- **Original ID:** UAT-D-A9 · **REQ:** REQ-WP0-08 · **Severity:** P1
- **Exposure:** n/a (release-level).
- **Evidence:**
  - `tools/avs_fix_002_stage0.py:170-211` `import_graph()` at HEAD returns 152 nodes / `passed=true`. `STAGE0_BASELINE_MANIFEST.json` records 138 nodes, passed.
  - A tester walk with Python import semantics over the same 6 entry points finds 177 nodes.
  - The 25 missing modules are all tracked, e.g. `canonical_data/__init__.py:32,58,59` relative imports, 13 `pipeline_interpreter/*`, and `macro_domain/gamma_exposure.py`.
  - `scripts/release_baseline.py`, which the REQ names, has no import walk. The refusal path is untested.
- **Reproduction:** `python probes/p10_A_stage0_graph_now.py` → `tester6_minus_head`.
- **To close:** the tester's 6-root set is a subset of the gate's set. Fixtures importing an untracked module, or a tracked-but-unmanifested one, both refuse with the file named, and the regenerated manifest hashes every reachable node.
- TRACE: REQ-WP0-08 | ALG-NONE | WP-0 | STAGE-0 | TRACK-A | EVIDENCE-STAGE0_BASELINE_MANIFEST.json+tools/avs_fix_002_stage0.py | N=25 modules

### UAT-D09 — No quarantine manifest; dangling actuarial builder reference
- **Original ID:** UAT-D-A10 · **REQ:** REQ-WP0-07 (S) · **Severity:** P1
- **Exposure:** n/a.
- **Evidence:**
  - `git ls-files` shows no quarantine folder or manifest.
  - The repo root holds 13 `*.bak`, 6 `avs_macro_check_*`, 4 `.codex_*`, 5 `.pytest_*`, `.testdeps/` and `backups/` (≈35 dirs; 11 contain the legacy `_utc_now()` morning_gate).
  - `intelligent_orchestrator.py:502` points at an out-of-repo `actuarial_cache_builder.py`, loaded at `:4910-4916`. `scripts/actuarial_cache_builder.py` is absent.
  - Mitigation: 0 quarantined-path hits on the import graph.
- **Reproduction:** `python probes/p10_A_import_graph.py` → `quarantine_tracked_files`, `actuarial_cache_builder_refs`.
- **To close:** a committed quarantine manifest with ACK sign-off; the litter is off the import path; the builder reference is restored in-repo or removed; and the graph shows 0 quarantined paths.
- TRACE: REQ-WP0-07 | ALG-NONE | WP-0 | STAGE-0 | TRACK-A | EVIDENCE-git ls-files+intelligent_orchestrator.py:502 | N=NONE

### UAT-D10 — Spread canonicalisation incomplete; tier keeps blocking rows whose spread is ≤ 25%
- **Original ID:** UAT-D-B2 · **REQ:** REQ-WP1-03 / ALG-12 / NFR-04 · **Severity:** P1
- **Exposure:** wrongly BLOCKed on the primary run: CALL 349 / PUT 235 / OTHER 0.
- **Evidence (source):**
  - `contracts/lab_control.py:2639` builds `spread_pct` from a mixed-unit alias chain, with no `spread_unit` and no `spread_fraction_mid`. `:2004-2008` guesses the unit with `spread * 100 if spread <= 1`.
  - `contracts/opportunity_tier.py:93-97` labels a bare `spread_pct` as FRACTION_OF_MID.
  - `morning_gate.py:982` writes a fraction under `_contract_spread_pct`. Only `execution_gate.py:466-468` emits the canonical field.
- **Evidence (runs):**
  - 20260911 `final_opportunity_book` has `spread_pct` 1.33–200 (percent); 20260910 has 0.013–2 (fraction).
  - 993 spread-only BLOCK rows on 20260911, of which 584 have a true spread ≤ 25%.
  - 0 of 82 stored CSVs carry `spread_fraction_mid`. Offline `derive_tier` at cc509cb changes 0 tiers.
- **Reproduction:** `python probes/p11_B_b3_spread.py; python probes/p11_B_b4_tier.py`.
- **To close:** `spread_fraction_mid` ∈ [0,2] and `spread_pct_of_mid` on every row of every CSV of a stored run; `lab_control` writes the canonical field with no `<= 1` guess; and no BLOCK cites spread on a row with `spread_fraction_mid` ≤ 0.25.
- TRACE: REQ-WP1-03 | ALG-12 | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-final_opportunity_book_20260911_115904.csv | N=993

### UAT-D11 — Contract-test matrix omits PUT through the runtime adapters and the producer-unit-change acceptance
- **Original ID:** UAT-D-B6 · **REQ:** REQ-WP1-05 · **Severity:** P1
- **Exposure:** PUT is untested on the tier, spread and horizon adapters.
- **Evidence:**
  - `tests/contracts/` is absent.
  - `tests/test_avs_fix_002_runtime_adapters.py`: 4 tests, 0 PUT occurrences.
  - `tests/test_avs_fix_002_stages2_5.py`: PUT appears only in the economics grid (`:112`), and there is no horizon-label consumer test.
  - No test mutates a producer unit and asserts a consumer failure. 83 tests pass (`probes/p11_B_pytest_wp1_05.txt`).
- **Reproduction:** re-run the two files; grep them for `"PUT"`.
- **To close:** a fixture matrix over {CALL, PUT} × {1_5d, 6_10d, 11_20d} at each producer/consumer boundary, plus a test that fails on a producer unit change.
- TRACE: REQ-WP1-05 | NONE | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-p11_B_pytest_wp1_05.txt | N=83

### UAT-D12 — Production DOI valuation receives no forecast vol, so v2 economics is empty even with the rate fixed
- **Original ID:** UAT-D-C1 · **REQ:** REQ-WP2-02 / REQ-WP2-03 / REQ-WP2-04 (ALG-02, -04, -05) · **Severity:** P1
- **Exposure:** CALL and PUT, every directed family. OTHER n/a.
- **Evidence:**
  - `canonical_data/dynamic_options_production.py:311-314` reads `l3_forward_realised_vol` / `forecast_vol_annual_fraction` / `forward_realised_vol`. None is a column of `options_intelligence_20260911_115904.csv`, and grep finds no producer.
  - As-wired offline pass (rate 0.0395): 298/298 contracts `NOT_EVALUATED_DATA_MISSING`; utility v2 non-null on 0; the score falls back to v1 on 254/254.
- **Reproduction:** `python probes/p12_C_offline_sample.py 120 80 25`, key `as_wired`.
- **To close:** a replay of 20260911_115904 where the DOI input carries a named forecast-vol field with lineage, and the reachable spot and scenario grid are non-null on every directed family that has target, invalidation, IV and a two-sided quote, per direction.
- TRACE: REQ-WP2-02 | ALG-04 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_offline_sample.out.json#as_wired | N=298

### UAT-D13 — Contracts expiring inside the hold are removed before valuation, never retained as HORIZON_LIMITED
- **Original ID:** UAT-D-C2 · **REQ:** REQ-WP2-03 (ALG-03) · **Severity:** P1
- **Exposure:** inside-hold contracts in 200 sampled families: CALL 4,118 / PUT 3,863. OTHER n/a.
- **Evidence:**
  - `canonical_data/dynamic_options_family.py:285` (hold + 8-session buffer) and `:347-348` (`INSUFFICIENT_SESSION_RUNWAY`).
  - Offline, 15,162 side-correct contracts are `EXCLUDED_STRUCTURAL`, with 0 assessments.
  - HORIZON_LIMITED is reached only by a direct call (`tests/test_avs_fix_002_stages2_5.py:134`), while `tests/test_dynamic_options_contract_family.py:195` asserts the exclusion.
- **Reproduction:** `p12_C_offline_sample.py`, then `p12_C_c4_real_oracle.py` (`runway_excluded_counts`, case 3).
- **To close:** on a replay, every inside-hold two-sided contract is present with `applicability=HORIZON_LIMITED`, `dte_inside_hold=true`, INDETERMINATE and unranked, with CALL/PUT counts equal to the generator's inside-hold counts.
- TRACE: REQ-WP2-03 | ALG-03 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_offline_runway_excluded.csv | N=7981

### UAT-D14 — Scenario theoretical values are not European BSM in the money (intrinsic floor)
- **Original ID:** UAT-D-C3 · **REQ:** REQ-WP2-03 (ALG-04) · **Severity:** P1
- **Exposure:** PUT (the real contract fails 15 of 54 scenarios by > 0.5%); CALL only when q > 0 or deep ITM (0 of 54 on the real CALL); OTHER n/a.
- **Evidence:**
  - `domain/deterministic_option_valuation.py:210-217` clamps the value to `max(intrinsic, forward intrinsic)`.
  - `A261016P00140000` `FAVOURABLE_2SIGMA:EARLY:CONTRACTED`: 16.3296 against 16.0032 European (2.04%). Net return up to 10.35 pp higher.
  - A floored oracle matches to 1.6e-13.
- **Reproduction:** `python probes/p12_C_c4_real_oracle.py`, case 2.
- **To close:** the real PUT grid within 0.5% of European BSM on all 54 scenarios, or an approved spec change naming the floor, with the Annex oracle and tests updated.
- TRACE: REQ-WP2-03 | ALG-04 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_c4_real_oracle.out.json | N=54

### UAT-D15 — Ranking-score field mixes v2 and v1 formulas without a kind marker; v1 not retained under its own name
- **Original ID:** UAT-D-C6 (covers DEV-07) · **REQ:** ALG-06 (REQ-WP2-03/04 utility; REQ-WP3-06 kind) · **Severity:** P1
- **Exposure:** CALL and PUT. Offline, 1,093 contracts carry v2 and 896 carry the v1 fallback in the same field; OTHER n/a.
- **Evidence:**
  - `canonical_data/dynamic_options_valuation.py:438-442` computes `ranking_score_uncalibrated = v2 if not None else v1`, while `:424` states `ranking_score_kind=DETERMINISTIC_UTILITY` for both.
  - No `ranking_score_uncalibrated_v1` field exists.
  - Spearman(v1, v2) across all contracts is 0.147 (CALL 0.025).
- **Reproduction:** `p12_C_c6_crosstab.py`, key `c10_ranking_score_field`.
- **To close:** on a replay, the score is populated only by v2 (null or a named non-ranked state otherwise), v1 is published under `ranking_score_uncalibrated_v1`, and no family ranking combines the two.
- TRACE: NONE | ALG-06 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_c6_crosstab.out.json#c10_ranking_score_field | N=1989

### UAT-D16 — DOI input missing governed thesis_id on 38 directed rows
- **Original ID:** UAT-D-D1 · **REQ:** REQ-WP3-01 · **Severity:** P1
- **Exposure:** CALL 26 / PUT 12 / OTHER 188 (non-directional path).
- **Evidence:**
  - `dynamic_options_intelligence_20260911_115904.json` reports `MISSING_GOVERNED_THESIS_ID = 38`. The options CSV has `thesis_id` null on those rows while the book carries legacy run-scoped IDs (`ARW:CALL:20260911_115904`).
  - The DOI input lacks `evidence_cutoff_utc`, and `governed_direction_records` has thesis_id on 0/1,444.
  - Code: `canonical_data/dynamic_options_production.py:157-169`.
- **Reproduction:** `probes/p13_D_d3_thesis_trace.py`, `p13_D_d3b_exceptions.py`.
- **To close:** a normal run where the DOI directed rows equal the book directed rows, with identical thesis_id, hold, spot, cutoff, target and invalidation, and `MISSING_GOVERNED_THESIS_ID = 0`.
- TRACE: REQ-WP3-01 | ALG-NONE | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-options_intelligence_20260911_115904.csv,dynamic_options_intelligence_20260911_115904.json | N=38

### UAT-D17 — DOI projection not activated on the Lab book
- **Original ID:** UAT-D-D2 · **REQ:** REQ-WP3-02 · **Severity:** P1
- **Exposure:** CALL 798 / PUT 458 / OTHER 188.
- **Evidence:**
  - Lab book `DOI_TABLES_NOT_ACTIVATED` 1,381 (761 / 432 / 188) and `GOVERNED_CONTRACT_IDENTITY_MISMATCH` 63 (37 / 26 / 0).
  - DOI report `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` 1,218; `doi_contract_assessments` 0 rows.
  - The comparison run has 1,424/1,424 not activated.
  - Source: `canonical_data/dynamic_options_projection.py:84,107,123-124`.
- **Reproduction:** `probes/p13_D_d2_doi_projection.py`.
- **To close:** a normal run with `DOI_TABLES_NOT_ACTIVATED = 0`, `FAMILY_NOT_VALUED_RATE_UNAVAILABLE = 0` and mismatch 0 on published preferred contracts, with preferred contract, alternatives and ranking score non-null on every scoreable row.
- TRACE: REQ-WP3-02 | ALG-06 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-final_opportunity_book_20260911_115904.csv | N=1444

### UAT-D18 — Identity / execution / activity state machines not implemented
- **Original ID:** UAT-D-D4 · **REQ:** REQ-WP3-03 · **Severity:** P1
- **Exposure:** CALL 772 / PUT 446 / OTHER 0.
- **Evidence:**
  - There is a single `liquidity_state` enum (`domain/option_contract_liquidity.py:47-49`).
  - No producer exists for `ACTIVITY_*` or `EXECUTION_*`; only `domain/presentation.py:22` reads `EXECUTION_EXECUTABLE_NOW`.
  - `option_contract_observations.correction_state` is null on 10,522/10,522.
  - 924 of 1,218 selected contracts are thin, so the machines matter for about ¾ of the book.
- **Reproduction:** grep `ACTIVITY_THIN|EXECUTION_EXECUTABLE_NOW` in `*.py`; `probes/p13_D_d4_lifecycle.py`.
- **To close:** per-transition fixtures for the three machines; a run artefact with a row that is simultaneously `ACTIVITY_THIN` and `EXECUTION_EXECUTABLE_NOW`; later observations append rather than mutate.
- TRACE: REQ-WP3-03 | ALG-12 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-control_plane.option_contract_observations | N=10522

### UAT-D19 — Preferred-contract hysteresis not evidenced; PreferredContractSuperseded absent
- **Original ID:** UAT-D-D5 · **REQ:** REQ-WP3-04 / ALG-11 · **Severity:** P1
- **Exposure:** contract switches 10→11 Sep: CALL 57 / PUT 22 / OTHER 0.
- **Evidence:**
  - `PreferredContractSuperseded` does not occur in code.
  - `option_contract_selection_events` carries no U_i, U_c, margin or supersession reason, and `doi_preferred_contract_decisions` has 0 rows.
  - The 79 of 1,191 contract changes cannot be tested against the margin. The EOD selector recorded no incumbent (0 events with a previous symbol).
  - The margin rule is CLOSED OFFLINE (`domain/dynamic_options_ranking.py:377-434`).
- **Reproduction:** `probes/p13_D_d6_hysteresis.py`.
- **To close:** a replay of two consecutive normal runs where every switch satisfies `U_c − U_i ≥ max(0.05, 0.10·|U_i|)` or has reason EXPIRED / MALFORMED / DEFECT, emitted as `PreferredContractSuperseded` with the prior symbol and reason.
- TRACE: REQ-WP3-04 | ALG-11 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-options_intelligence_20260910_150045.csv,options_intelligence_20260911_115904.csv | N=79

### UAT-D20 — Post-open refresh publication fields absent; economics not recomputed with the refreshed quote
- **Original ID:** UAT-D-D6 · **REQ:** REQ-WP3-05 · **Severity:** P1
- **Exposure:** refreshed rows CALL 47 / PUT 22 / OTHER 0.
- **Evidence:**
  - `morning_refresh_state`, `contract_refresh_timestamp_utc` and `THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE` have no producer.
  - `refresh_window_state` is published as `postopen_contract_refresh_window_state` (`morning_gate.py:3325`).
  - On the 69 refreshed rows, `monetisability_quote_timestamp_utc` stays on the 10 Sep quote. `monetisability_refresh_status = PENDING_MORNING_REFRESH` on 1,444/1,444.
- **Reproduction:** `probes/p13_D_d5b_quote_truth.py` (`refresh_values`).
- **To close:** an adversarial crossed-market fixture and a post-open run showing a replacement searched, the original retained, a supersession event emitted, and every economics field carrying the new `assessment_id`.
- TRACE: REQ-WP3-05 | ALG-12 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-morning_validated_trades_20260911_115904.csv | N=69

### UAT-D21 — assessment_id does not follow ALG-16 and is run-scoped
- **Original ID:** UAT-D-D7 · **REQ:** ALG-16 (REQ-WP3-05 lineage) · **Severity:** P1
- **Exposure:** every CALL/PUT assessment (0 stored); OTHER n/a.
- **Evidence:**
  - `domain/dynamic_options_intelligence.py:194-196,473-481` hashes `namespace|{family_id, contract_symbol, observation_id, calculation_version, evidence_cutoff_utc}`. `family_id` includes `run_id` (`:344-352`), and timestamps carry no milliseconds.
  - ALG-16 recomputation matches 0/5; the production formula matches 5/5.
  - Changing `run_id` changes the ID; changing `input_dataset_ids` or `feature_version` does not.
- **Reproduction:** `probes/p13_D_d7_assessment_identity.py`.
- **To close:** five stored assessments recompute exactly from the ALG-16 components; an economic one-field mutation changes the ID, and a transport-only or run-only change does not.
- TRACE: REQ-WP3-05 | ALG-16 | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-p13_D_d7_assessment_identity.json | N=5

### UAT-D22 — Production outcome labels use the structural target, not the ALG-08 budget target; decision record lacks point-in-time budget
- **Original ID:** UAT-D-E1 (shares the missing `completed_session` / `planned_hold_sessions` root cause with UAT-D33 and DEV-14) · **REQ:** REQ-WP4-01 (ALG-08) · **Severity:** P1
- **Exposure:** EOD candidates on stored ledger runs: CALL 2,074 / PUT 1,178; OTHER not labelled by design.
- **Evidence:**
  - `canonical_data/outcome_maturation.py:111-113,162-169` labels against the payload `target_price`.
  - Ledger payload target equals the book structural target 10/10 and the budget target 0/10.
  - `completed_session` and `planned_hold_sessions` are null 10/10; there is no `e_h` or `k` on the record.
  - The label function itself is CLOSED OFFLINE (30/30).
- **Reproduction:** `python probes/p14_EH_e2_point_in_time.py`.
- **To close:** a stored NORMAL run whose decision record carries e_h, k, completed session and hold, with matured OUTCOME events labelled at `S_d(1 ± k·e_h)` using values equal to the decision-session artefacts.
- TRACE: REQ-WP4-01 | ALG-08 | WP-4 | STAGE-6 | TRACK-E | EVIDENCE-p14_EH_e2_point_in_time_out.json | N=10

### UAT-D23 — Calibration script, report and calibration_table.json absent
- **Original ID:** UAT-D-E2 · **REQ:** REQ-WP4-03 / REQ-WP4-04 (ALG-09) · **Severity:** P1
- **Exposure:** CALL/PUT, all strata.
- **Evidence:**
  - `scripts/calibrate_probabilities.py` is absent, as are the report (Brier, log loss, reliability curve, coverage, model ID, training cutoff) and any `calibration_table.json`.
  - No ALG-09 multiclass metric function exists. `git grep calibration_table -- '*.py'` finds 0 production hits.
  - `doi_p_target_before_invalidation` is populated on 0/1,444 rows.
- **Reproduction:** `python probes/p14_E_e6_disclosure.py`.
- **To close:** a report with those fields and a `calibration_table.json` in DOI vocabulary, produced from date-partitioned held-out data and consumed by `canonical_data/dynamic_options_probability.py`.
- TRACE: REQ-WP4-03 | ALG-09 | WP-4 | STAGE-6 | TRACK-E | EVIDENCE-p14_E_e6_disclosure_out.json | N=0

### UAT-D24 — Backoff lineage fields and κ-shrinkage estimator absent
- **Original ID:** UAT-D-E3 · **REQ:** REQ-WP4-02 (ALG-09) · **Severity:** P1
- **Exposure:** CALL/PUT.
- **Evidence:**
  - `domain/outcome_learning.py:65-82` returns key dictionaries only. `exact_n`, `parent_n`, `shrinkage_weight` and `match_dims_used` are absent on 10/10 keys.
  - No κ estimator exists, and `kappa` / `n_min` are absent from the config.
- **Reproduction:** `python probes/p14_EH_e5_backoff.py`.
- **To close:** every probability row carries the five lineage fields, and p̂ equals the κ formula recomputed from exact and parent counts.
- TRACE: REQ-WP4-02 | ALG-09 | WP-4 | STAGE-6 | TRACK-E | EVIDENCE-p14_EH_e5_backoff_out.json | N=10

### UAT-D25 — SECTOR_UNMAPPED on every row although no ticker lacks GICS
- **Original ID:** UAT-D-F1 · **REQ:** REQ-WP5-01 · **Severity:** P1
- **Exposure:** CALL 798 / PUT 458 / OTHER 188 (GO rows: CALL 10 / PUT 9).
- **Evidence:**
  - `morning_handoff_finalizer.py:775` → `contracts/interpreter_macro_context.py:439-441` reads an empty sector on all 1,444 `execution_gated` rows.
  - `SECTOR_ALIASES` (`macro_domain/us_money_index.py:8-25`) and the routing category names (`contracts/us_money_index_contract.py:278-315`) never match. With the sector filled offline, rows remain unmapped: CALL 798/798, PUT 379/458, OTHER 188/188.
  - Final book: `usmi_alignment_reason=SECTOR_UNMAPPED` on 1,444 against 0 tickers lacking GICS; manifest available 0/1,444.
- **Reproduction:** `p15_F_01_sector_unmapped.py`, `p15_F_02_routing_oracle.py`.
- **To close:** a normal stored run with SECTOR_UNMAPPED ≤ tickers lacking GICS (per direction) and manifest availability ≥ 0.90 of directed rows.
- TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-final_opportunity_book.usmi_alignment_reason | N=1444

### UAT-D26 — map_routing port diverges from desk_gate; alignment never SUPPORTIVE/OPPOSED
- **Original ID:** UAT-D-F2 (covers DEV-09 severity) · **REQ:** REQ-WP5-01 / ALG-14 · **Severity:** P1
- **Exposure:** CALL 798 / PUT 458 / OTHER 188.
- **Evidence:**
  - `domain/macro_advisory_context.py:28-44` disagrees with `desk_gate.py:75-97` on 32 routed rows: CALL 24 IT services → `AI_SEMICONDUCTOR_CALL`; PUT 8 fuel-sensitive/REIT rows.
  - The sentinel is `NO_ROUTE` instead of `NO_CALL/PUT_ROUTE_FOR_SECTOR` / `UNMAPPED`, giving exact-key 5/20. The `basis` output is absent.
  - `:46-63` maps all 4 route labels to NEUTRAL and emits UNAVAILABLE on no-route rows (CALL 486 / PUT 210 / OTHER 188).
  - The stored run has no Join 2 output.
- **Reproduction:** `p15_F_02_routing_oracle.py`, `p15_F_02b_routing_detail.py`.
- **To close:** on a stored run, the emitted routing key equals `map_routing` on 20/20 sampled tickers (all three directions), and alignment is derived from direction against the route side.
- TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-p15_F_02_routing_oracle_full.csv | N=1444

### UAT-D27 — Scenario evaluator cannot evaluate the real packet; stored UNRESOLVED has no failed clause
- **Original ID:** UAT-D-F4 · **REQ:** REQ-WP5-02 · **Severity:** P1
- **Exposure:** CALL 798 / PUT 458 / OTHER 188.
- **Evidence:**
  - Stored `usmi_scenario=UNRESOLVED` on 1,444 rows, with no failed clause, observed value or timestamp. Nothing was evaluated: `us_money_index_contract.py:424` returns `{}` and `interpreter_macro_context.py:337-340` passes `{}`.
  - The packet's `conditions_all` are free text. Join 1 reports `UNSTRUCTURED_PREDICATES`; Join 2 reports `SCENARIOS_UNAVAILABLE` because `_find` hits an empty `scenarios`.
  - `_find` also resolves `vix` to the 20.0 threshold instead of the observed 17.7.
- **Reproduction:** `p15_F_03_scenario.py`, `p15_F_03b_find_paths.py`.
- **To close:** a stored run whose `usmi_scenario` matches an independent evaluation of the packet's `conditions_all`, with failed clause, observed value and timestamp; a missing metric yields UNRESOLVED naming the metric.
- TRACE: REQ-WP5-02 | ALG-14 | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-final_opportunity_book.usmi_scenario | N=1444

### UAT-D28 — Capacity calculators and account capital remain on production paths
- **Original ID:** UAT-D-F5 (related: UAT-D39 capital env config) · **REQ:** REQ-WP5-04 / ALG-13 · **Severity:** P1
- **Exposure:** `pse_suggested_contracts` ≥ 1 on CALL 294 / PUT 232 / OTHER 0. `position_size_display` is not HUMAN DETERMINED on CALL 798 / PUT 458 / OTHER 188.
- **Evidence:**
  - Capacity calculators remain at `execution_intelligence_runner.py:2425-2432`, `intelligent_orchestrator.py:593,4507` → `trade_book_builder.py:404`, and `morning_validation_engine.py:857-911`.
  - `config/mastermind_config.json` carries an `account` block.
  - `execution_v3_5` has `pse_suggested_contracts` 1–5 on 526 rows; the final book shows "0% - …" or empty display text.
  - `test_pipeline_is_capital_agnostic` does no production dependency scan.
- **Reproduction:** `p15_F_05_capacity_structure.py`, `p15_F_04_header_scan.py`.
- **To close:** a static dependency test proving no capacity calculator on a production path; config with no capacity or account policy; and a stored run with HUMAN DETERMINED on every final row and no suggested contract count.
- TRACE: REQ-WP5-04 | ALG-13 | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-execution_v3_5.pse_suggested_contracts,final_opportunity_book.position_size_display | N=1444

### UAT-D29 — NFR-02 macro-mutation property test and REQ-WP5-05 consumer audit table absent
- **Original ID:** UAT-D-F6 · **REQ:** NFR-02 / REQ-WP5-05 · **Severity:** P1
- **Exposure:** all directions.
- **Evidence:**
  - No test mutates every macro input and asserts direction, row count, preferred symbol and `contracts_at_budget` unchanged. 5 narrower invariance tests pass.
  - No macro-consumer table is committed under `audit/avs_fix_002`. Grep of the producers is clean (CLOSED OFFLINE).
- **Reproduction:** `git grep -n -i "def test.*macro" HEAD -- tests/`; `git grep -l "REQ-WP5-05" HEAD -- audit/avs_fix_002`.
- **To close:** the property test in the suite passing, plus a committed consumer table.
- TRACE: NFR-02 | NONE | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-tests/ | N=0

### UAT-D30 — BLOCK beside GO in displayed Lab columns
- **Original ID:** UAT-D-G2 · **REQ:** REQ-WP6-02 · **Severity:** P1
- **Exposure:** canonical pair on CALL 10 / PUT 9 / OTHER 0; any BLOCK/GO pair on CALL 53 / PUT 47 / OTHER 0.
- **Evidence:**
  - `lab_signal_book_v3.csv` has `opportunity_tier=BLOCK` beside `lab_verdict=GO_LIMIT`, `final_action=BUY_SMALL` and `morning_execution_permission=GO_LIMIT` on 19/19 rows.
  - 100 final-book rows carry some BLOCK/GO pair.
  - `domain/presentation.py` writes no field on the run path, and `contracts/lab_control.py` still emits the legacy verdicts.
- **Reproduction:** `python probes/p16_G_g2_projector.py`.
- **To close:** a stored run whose Lab read model shows one projector summary per row, with no displayed row pairing a BLOCK token with a GO, EXECUTE or BUY token.
- TRACE: REQ-WP6-02 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-final_opportunity_book_20260911_115904.csv | N=1444

### UAT-D31 — Presentation projector contradicts its thesis input
- **Original ID:** UAT-D-G3 · **REQ:** REQ-WP6-02 · **Severity:** P1
- **Exposure:** offline, all directions.
- **Evidence:**
  - `domain/presentation.py:20-24` writes the `summary_reason` literal `THESIS_ACTIVE|…` for 432 of 480 SD combinations whose thesis is not ACTIVE.
  - The invalid-thesis branch tests `INVALID` / `THESIS_INVALIDATED`, neither of which is in SD §9.1, so no SD thesis state reaches THESIS_INVALID. The stored `INVALIDATED` token (17 rows) is also missed.
  - The existing test covers 1 of 480 combinations.
- **Reproduction:** `probes/p16_G_g2_projector.py` Part B (`offline_480`).
- **To close:** an exhaustive 480-combination test asserting `summary_state` / `summary_reason` are consistent with every SD §9.1 thesis token.
- TRACE: REQ-WP6-02 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-p16_G_g2_projector.json | N=480

### UAT-D32 — Macro check in the dossier pass/fail set; coaching board not regenerated from Lab v4
- **Original ID:** UAT-D-G5 · **REQ:** REQ-WP6-03 · **Severity:** P1
- **Exposure:** all 19 dossiers: CALL 10 / PUT 9.
- **Evidence:**
  - `dropbox/macro/coaching/build_trade_dossiers.py:141-151` emits "Macro routing" PASS/WARN/FAIL; `:170` puts it in `CORE`; `:172-175` counts CORE fails into the verdict.
  - `build_coaching_board.py:5,335` reads only `macro_intelligence_latest.json`.
  - Every scorecard in `trade_edge_dossiers_20260911_115904.md` has a Macro routing row.
- **Reproduction:** grep the cited lines.
- **To close:** both generators read `lab_signal_book_v4`, macro appears in context sections only, and no pass/fail or CORE set contains a macro check.
- TRACE: REQ-WP6-03 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-trade_edge_dossiers_20260911_115904.md | N=19

### UAT-D33 — Every EOD candidate lacks completed_session and planned_hold_sessions; 100% ineligible for maturation
- **Original ID:** UAT-D-H1 (see UAT-D22, DEV-14) · **REQ:** REQ-WP7-02 (ALG-08) · **Severity:** P1
- **Exposure:** CALL 2,074 / PUT 1,178 / OTHER 0.
- **Evidence:**
  - `probes/p14_EH_h3_eligibility_out.json`: `completed_session` is None on 3,252/3,252 and `planned_hold_sessions` is None on 3,252/3,252.
  - `outcome_maturation_20260911_115904.json` shows `eligible_candidates 0, ineligible_candidates 3252`, with no reason key.
  - Source: `canonical_data/outcome_maturation.py:117-118,125-131`; `canonical_data/decision_outcome_ledger.py:333-337,351`.
- **Reproduction:** `python probes/p14_EH_h3_eligibility.py`.
- **To close:** a stored run whose CANDIDATE_DECISION payloads carry a non-null ISO `completed_session` and an integer `planned_hold_sessions` on every directed row, `eligible_candidates > 0`, and a named reason for every ineligible row.
- TRACE: REQ-WP7-02 | ALG-08 | WP-7B | STAGE-6 | TRACK-H | EVIDENCE-outcome_maturation_20260911_115904.json | N=3252

### UAT-D34 — No replay harness and no expected-difference manifest
- **Original ID:** UAT-D-I1 · **REQ:** REQ-WP8-01, REQ-WP8-02, NFR-10 · **Severity:** P1
- **Exposure:** run-level, CALL/PUT/OTHER.
- **Evidence:**
  - `release/` and `release/expected_diffs/` are absent.
  - `tools/avs_fix_002_provider_replay.py:37-66` replays provider finality only, against read-write production paths.
  - The "Stored-run replay: PASS" claims resolve to `tests/test_avs_fix_002_stages2_5.py:225-245`, a data-shape test with no rebuild and no diff.
- **Reproduction:** `git ls-files | grep -i "replay\|expected_diff"`.
- **To close:** a replay by run ID reproduces the stored book hash, and a replay with one declared calculation-version change yields a diff whose field set equals `release/expected_diffs/<change>.json`; CI fails on an undeclared field.
- TRACE: REQ-WP8-01 | ALG-16 | WP-8 | STAGE-ALL | TRACK-I | EVIDENCE-tests/test_avs_fix_002_stages2_5.py:225 | N=0

### UAT-D35 — Environment variables gate production features outside the release profile
- **Original ID:** UAT-D-I2 · **REQ:** NFR-09 · **Severity:** P1
- **Exposure:** run-level, CALL/PUT/OTHER.
- **Evidence:**
  - 20 distinct gating or threshold variables sit on the import graph, and 0 are in `contracts/dynamic_session_runtime_v1.json`. Examples:
    - `intelligent_orchestrator.py:467` (EV3 authority), `:2893` (stage gating)
    - `canonical_data/feature_flags.py:35-47`
    - `intelligence-lab/intelligence_lab.py:126`
    - `scripts/avshunter_options_intelligence.py:1335-1336`
  - The profile itself can be disabled from the shell (`contracts/dynamic_session_contract.py:138-160`).
  - `run_meta` records the profile hash but none of the 20 values.
- **Reproduction:** `python probes/p17_IN_environ_classify.py` → `gating_variables_undocumented_in_import_graph`.
- **To close:** every gating or threshold read resolves from the release profile (with its hash in `run_meta_v2`), no shell variable can change a production feature, and the probe's undocumented list is empty.
- TRACE: NFR-09 | ALG-NONE | WP-8 | STAGE-ALL | TRACK-I | EVIDENCE-p17_IN_environ_summary.json | N=73

### UAT-D36 — 9 of 29 Annex A config keys absent from governed constants; owners missing
- **Original ID:** UAT-D-I3 (covers DEV-12) · **REQ:** REQ-WP8-04, NFR-08 · **Severity:** P1
- **Exposure:** CALL/PUT/OTHER.
- **Evidence:**
  - Absent from `config/governed_constants_v1.json`: `friction.model`, `freshness_minutes`, `clock_skew_tolerance_minutes`, `spread_executable_limit`, `calibration.kappa`, `vol_validation.minimum_validation_n`, `vol_validation.pass.{ratio,coverage}`, `refresh_window`. That includes 4 of the 8 constants the REQ names.
  - Only `profit_floor` has a key owner; `provider_completeness` and `volatility_budget` have no owner at all.
- **Reproduction:** `python probes/p17_IN_governed_constants.py`.
- **To close:** every Annex key present with owner, version and value; the probe reports `absent: []`.
- TRACE: REQ-WP8-04 | ALG-NONE | WP-8 | STAGE-2 | TRACK-I | EVIDENCE-p17_IN_governed_constants.csv | N=29

### UAT-D37 — EIL fail-closed test assertions weakened without a claim
- **Original ID:** UAT-D-I5 · **REQ:** Rule 7 (EIL authority; UNMAPPED) · **Severity:** P1
- **Exposure:** CALL/PUT/OTHER.
- **Evidence:** commit b36f536.
  - `tests/test_big_bang_phase_6_7.py`: `EIL_OUTPUT_MISSING_OR_INVALID` moved from fatal to stale flags, and the `run_tradeable is False` assertion was deleted.
  - Also in that file: BLOCKED + GO no longer asserts `lab_verdict == BLOCKED` / `HARD_CONFLICT`.
  - `tests/test_handoff_contract.py`: `packet_status` BLOCKED changed to PARTIAL (2 tests).
  - No claim sheet names the old assertion, the new rule and a positive replacement (Stage 0 claim sheet line 33).
- **Reproduction:** `git diff avs-baseline-20260906..HEAD -- tests/test_big_bang_phase_6_7.py tests/test_handoff_contract.py`.
- **To close:** the fail-closed assertions restored, or a governed decision record plus claim-sheet entry naming the retired rule and a positive replacement test constraining what a missing or BLOCKED EIL may permit.
- TRACE: UNMAPPED | ALG-NONE | WP-NONE | STAGE-ALL | TRACK-I | EVIDENCE-p17_test_edits.csv | N=2

### UAT-D38 — Release evidence incomplete; no rollback rehearsal
- **Original ID:** UAT-D-I6 · **REQ:** REQ-WP8-03 · **Severity:** P1
- **Exposure:** run-level.
- **Evidence:**
  - `grep -rni rehears audit/avs_fix_002` returns 0 hits.
  - `STAGES2_5_RELEASE_MANIFEST.json` has no file list or hashes.
  - The Policy manifest and Stage 0 have no rollback instructions.
  - Stage 1 has 2 of 18 hashes stale, `cc509cb` has no manifest, and restore is self-reported.
- **Reproduction:** `python probes/p17_IN_manifest_hashes.py`.
- **To close:** every stage manifest lists hashed files matching its commit with rollback instructions, and a rehearsal record (restore on a copy, integrity check, append-only evidence preserved) exists dated before Stage 2 closure.
- TRACE: REQ-WP8-03 | ALG-NONE | WP-8 | STAGE-2 | TRACK-I | EVIDENCE-p17_IN_manifest_summary.json | N=5

### UAT-D39 — Governed values duplicated as literals outside the loader; capital config readable
- **Original ID:** UAT-D-I7 (related: UAT-D28) · **REQ:** REQ-WP8-04, NFR-08 · **Severity:** P1
- **Exposure:** CALL/PUT/OTHER.
- **Evidence:**
  - 13 name-anchored literal hits in 7 files:
    - `domain/contract_economics_v2.py:68,71,112`
    - `domain/reachability.py:27`
    - `domain/option_contract_liquidity.py:142` (freshness window exists only as a literal)
    - `domain/outcome_learning.py:271,272,277`
    - `vanguard/ev_engine_v3.py:34`
    - loader fallbacks `canonical_data/dynamic_options_production.py:165-166` and `canonical_data/dynamic_options_valuation.py:382`
  - `execution_intelligence_runner.py:2427` reads `AVSHUNTER_ACCOUNT_RISK_BUDGET` (default 1000), although the Policy manifest says `configuration: REMOVED`.
- **Reproduction:** `python probes/p17_IN_governed_constants.py` → `p17_IN_governed_literals.csv`.
- **To close:** the grep returns only the manifest loader (no defaulted fallbacks), and no capital key is readable by the pipeline.
- TRACE: NFR-08 | ALG-NONE | WP-8 | STAGE-2 | TRACK-I | EVIDENCE-p17_IN_governed_literals.csv | N=13

### UAT-D40 — 14 failing test cases absent from the baseline register and every claim sheet
- **Original ID:** UAT-D-I8 (covers DEV-03) · **REQ:** Stage 7 regression rule (UNMAPPED) · **Severity:** P1
- **Exposure:** Lab strangle rows (OTHER) 9 tests; CALL/PUT Lab reload 3; EV3 order 1; book fields 1.
- **Evidence:**
  - Unregistered failures: `tests/test_lab_strangle_direction.py` 9, `test_lab_cache_signature.py` 2, `test_lab_journal_handoff.py` 1, `test_ev3_orchestrator_order.py` 1, `test_big_bang_phase_6_7.py::test_opportunity_book_and_learning_feedback` 1.
  - At HEAD these give 14 failed / 8 passed (`probes/p17_IN_pytest_new14.txt`).
  - The full suite has 44 failure elements (33 cases); the Stage 6 and Policy packs that reported 0 failures excluded these files.
- **Reproduction:** `python tools/run_governed_pytest.py -q tests/test_lab_strangle_direction.py tests/test_lab_cache_signature.py tests/test_lab_journal_handoff.py tests/test_ev3_orchestrator_order.py tests/test_big_bang_phase_6_7.py -p no:cacheprovider`.
- **To close:** these 14 pass, or each is dispositioned in the register with the old assertion, the new rule and a positive replacement.
- TRACE: UNMAPPED | ALG-NONE | WP-NONE | STAGE-ALL | TRACK-I | EVIDENCE-p17_IN_pytest_new14.txt | N=14

### UAT-D41 — Thesis-owned fields written outside the Thesis context
- **Original ID:** UAT-D-N1 · **REQ:** NFR-01 · **Severity:** P1
- **Exposure:** CALL/PUT/OTHER, every row passing the writers.
- **Evidence:**
  - `morning_gate.py:3746` writes `planned_hold_sessions`, with an invented fallback at `:3736-3745`.
  - `intelligent_orchestrator.py:3488` writes the hold from the router bucket.
  - `contracts/lab_control.py:3508` sets `structural_target ← target_price`.
  - Alias writers: `morning_gate.py:3712`, `contracts/lab_control.py:1555`, `vanguard/ev3_stage0.py:349`, `execution_intelligence_runner.py:2352`.
- **Reproduction:** `git grep -nE "\[[\"'](governed_direction|structural_target[a-z_]*|invalidation_[a-z_]*|planned_hold_sessions)[\"']\]\s*=[^=]" -- '*.py' ':!tests' ':!backups' ':!audit'`.
- **To close:** every writer found by the grep resolves to the Thesis context; downstream modules only read these fields and fail with a named state when absent.
- TRACE: NFR-01 | ALG-NONE | WP-NONE | STAGE-ALL | TRACK-N | EVIDENCE-morning_gate.py:3746 | N=8

### UAT-D42 — Contract replacement lineage lost; economics_recomputed constant; no assessment_id persisted
- **Original ID:** UAT-D-N2 · **REQ:** NFR-05 (REQ-WP2 contract identity) · **Severity:** P1
- **Exposure:** CALL 49 + 28 + 255 + 575 / PUT 21 + 16 + 198 + 328 / OTHER 0 (not representable).
- **Evidence:**
  - `previous_contract_symbol` is NULL on 70/70 cross-run replacements, and 44 of 52 in-run morning repairs link to the wrong prior symbol.
  - `economics_recomputed = 1` on 3,006/3,006 events, including 453 requotes that reuse the EOD observation.
  - 903 identical provider quotes were re-observed under new IDs with a different `delta`.
  - `doi_contract_assessments` has 0 rows. Six append-only triggers are present.
- **Reproduction:** `python probes/p17_IN_nfr05_immutability.py`.
- **To close:** on a stored run pair, every replacement names its predecessor; the recompute flag is derived (0 when there is no new observation); there is one assessment ID per (OCC symbol, quote observation), with contract-specific fields recomputed on change; and assessment rows are persisted.
- TRACE: NFR-05 | ALG-06 | WP-2 | STAGE-2 | TRACK-N | EVIDENCE-p17_IN_nfr05_immutability.json | N=3006

---

## P2

### UAT-D43 — DOI report claims zero physical fetches while the ledger records 1,218
- **Original ID:** UAT-D-A8 · **REQ:** REQ-WP0-03 · **Severity:** P2 (lineage)
- **Exposure:** hydrated rows CALL 772 / PUT 446 / OTHER 0.
- **Evidence:**
  - `dynamic_options_intelligence_20260911_115904.json:15` reports `physical_fetch_count: 0`.
  - `api_request_ledger` for run 20260911_115904, stage MORNING_GATE, `EXACT_OPTION_QUOTE` / `PROVIDER_FETCH`, shows 1,218 physical requests at 17:00:08Z–17:06:59Z.
  - `morning_gate_summary` has no fetch count.
- **Reproduction:** `probes/p10_A_provider_completeness.py` → `api_request_ledger_by_stage_type_state_res`.
- **To close:** a stored morning run whose `physical_fetch_count` in the DOI/bridge report and in `morning_gate_summary` equals the ledger's physical option-quote count for that stage.
- TRACE: REQ-WP0-03 | ALG-NONE | WP-0 | STAGE-1 | TRACK-A | EVIDENCE-dynamic_options_intelligence_20260911_115904.json+api_request_ledger | N=1,218

### UAT-D44 — Legacy differenced expected-move fields read directly by four consumers, one relabelled cumulative
- **Original ID:** UAT-D-B1 · **REQ:** REQ-WP1-01 / NFR-04 · **Severity:** P2
- **Exposure:** CALL, PUT, OTHER (direction-agnostic).
- **Evidence:**
  - `eod_candidate_engine.py:2695-2696` maps the differenced PERCENT 6–10d value to `expected_move_10d`, with default 0.0.
  - `execution_decision_engine.py:749`, `execution_intelligence.py:650` and `morning_validation.py:425` read the legacy fields unadapted.
  - `vanguard/ev3_stage0.py:372-389` reads names Layer 3 never emits.
  - 20260911 `qomega/garch_forecasts` carries the legacy fields on 1,444 rows and no v2 fields.
- **Reproduction:** `grep -n "l3_expected_move_6_10d" eod_candidate_engine.py execution_decision_engine.py execution_intelligence.py morning_validation.py`.
- **To close:** every legacy reader resolved to a versioned adapter publishing unit and calculation version; `ev3_stage0` reading emitted names; a run artefact showing `expected_move_10d_fraction` consumed.
- TRACE: REQ-WP1-01 | ALG-01 | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-p11_B_legacy_readers.txt | N=1444

### UAT-D45 — quote_change_evidence mixes percent and fraction; spread_change_pp 844–1,760
- **Original ID:** UAT-D-B3 · **REQ:** REQ-WP1-03 / NFR-04 · **Severity:** P2
- **Exposure:** 19 GO rows (CALL/PUT; split not recomputed).
- **Evidence:**
  - `contracts/quote_change_evidence.py:106-107,122-123,130-132,141` store percent and fraction under one unlabelled `spread_pct`; `:215-217` multiplies the difference by 100.
  - `lab_signal_book_v3.csv.contract_spread_change_pp` ranges 844.5–1,760 on 19/19 rows.
- **Reproduction:** fixture in `probes/p11_B_b3_spread.txt`.
- **To close:** the snapshot carries `spread_fraction_mid` via `resolve_spread` with a source label, and `spread_change_pp` ∈ [−200, 200] on a stored run.
- TRACE: REQ-WP1-03 | ALG-12 | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-lab_signal_book_v3.csv | N=19

### UAT-D46 — Silent-default inventory incomplete, cites an absent module; silent_zero_violations counter not implemented
- **Original ID:** UAT-D-B5 · **REQ:** REQ-WP1-04 / NFR-03 · **Severity:** P2
- **Exposure:** all directions.
- **Evidence:**
  - `audit/silent_defaults_inventory.md` row 8 names the absent `domain/capacity_suggestion.py`.
  - Not inventoried: `eod_candidate_engine.py:353-360,2693-2698`, `vanguard/ev_engine_v3.py:32-33,445-446,640-641`, `trigger_layer.py:333,347`, `contracts/lab_control.py:2986`.
  - `silent_zero_violations` has no producer and is absent from all summaries of both runs.
- **Reproduction:** `python probes/p11_B_b5_silent_defaults.py`.
- **To close:** an inventory row with its disposition implemented for each listed site; `default_applied/source/value` published where a default is used; a run summary with `silent_zero_violations = 0`.
- TRACE: REQ-WP1-04 | NONE | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-p11_B_b5_silent_defaults.txt | N=NONE

### UAT-D47 — UNVALIDATED state does not propagate to dependent economics fields
- **Original ID:** UAT-D-C4 · **REQ:** REQ-WP2-07 (ALG-10) · **Severity:** P2
- **Exposure:** contracts with grids: CALL 731 / PUT 362; OTHER n/a.
- **Evidence:**
  - `domain/contract_economics_v2.py:33-59` has no `validation_state` or `bias_multiplier_applied` field.
  - 0 of 1,093 economics rows carry a validation state, while their REACHABLE scenarios derive from a spot marked `UNVALIDATED_INPUT`.
- **Reproduction:** `p12_C_c6_crosstab.py`, key `c9`.
- **To close:** `validation_state` and `bias_multiplier_applied` on every scenario-economics, monetisability and utility output of a replay (100% UNVALIDATED while no report is accepted).
- TRACE: REQ-WP2-07 | ALG-10 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_c6_crosstab.out.json#c9 | N=1093

### UAT-D48 — Horizon-limited contracts with wide spreads labelled FRICTION_OUT_OF_RANGE
- **Original ID:** UAT-D-C5 · **REQ:** REQ-WP2-03 / REQ-WP2-04 (ALG-03, ALG-05) · **Severity:** P2
- **Exposure:** CALL 579 / PUT 515 of 5,108 two-sided inside-hold contracts (masked today by UAT-D13); OTHER n/a.
- **Evidence:**
  - `domain/contract_economics_v2.py:88-91` returns FRICTION_OUT_OF_RANGE before the horizon test at `:92-97`.
  - `A260918P00125000` → `FRICTION_OUT_OF_RANGE / SPREAD_OUTSIDE_MODEL_DOMAIN`.
- **Reproduction:** `p12_C_c4_real_oracle.py`, key `inside_hold_two_sided`.
- **To close:** inside-hold contracts report HORIZON_LIMITED regardless of spread, on a fixture and in a per-direction replay count.
- TRACE: REQ-WP2-03 | ALG-03 | WP-2 | STAGE-2 | TRACK-C | EVIDENCE-p12_C_c4_real_oracle.out.json#inside_hold_two_sided | N=1094

### UAT-D49 — Named exceptions collapse removal causes; no single reconciliation artefact
- **Original ID:** UAT-D-D9 (covers DEV-15; DEV-16 latent) · **REQ:** REQ-WP3-01 / SD invariant 1 · **Severity:** P2 (the identity itself closes, gap 0)
- **Exposure:** OTHER (pre-direction stages) 1,826.
- **Evidence:**
  - 1,748 Discovery exceptions collapse seven causes into `NO_SIGNAL_AT_ANY_HORIZON` (`avshunter_discovery_ULTIMATE.py:2536-2545`).
  - 78 `NOT_SCOPED` rows carry no cause (`scripts/avshunter_options_intelligence.py:8797-8808`); the cause survives only in the heuristic `dropoff_audit.py:240-255`.
  - No run-summary artefact states `input = presented + named`.
- **Reproduction:** `probes/p13_D_d1b_identity.py`.
- **To close:** a normal run with one reconciliation artefact whose per-stage named reason codes recover the removal cause.
- TRACE: REQ-WP3-01 | ALG-NONE | WP-3 | STAGE-4 | TRACK-D | EVIDENCE-discovery_lifecycle_20260911_115904.csv,vanguard_signals_enriched_20260911_115904.csv | N=1826

### UAT-D50 — usmi_routing_key emitted nowhere
- **Original ID:** UAT-D-F3 (covers DEV-06) · **REQ:** REQ-WP5-01 (`macro_ticker_context_v2`) · **Severity:** P2
- **Exposure:** all 1,444 rows.
- **Evidence:** the field is absent from code and from 0/43 stored CSVs; the route key lives only in `usmi_alignment_priority` (Join 2, offline).
- **Reproduction:** `p15_F_04_header_scan.py`; `git grep usmi_routing_key HEAD`.
- **To close:** the field present on every directed row of a stored run.
- TRACE: REQ-WP5-01 | ALG-14 | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-p15_F_04_header_scan.csv | N=1444

### UAT-D51 — structure_evidence_state lacks source versions; absent value displayed as DEVELOPING
- **Original ID:** UAT-D-F7 · **REQ:** REQ-WP5-03 · **Severity:** P2
- **Exposure:** CALL 798 / PUT 458 / OTHER 188.
- **Evidence:**
  - The field is absent from the stored run.
  - At HEAD, `domain/structure_evidence.py:3-17` records no input source versions and `phase` has no effect.
  - `domain/lab_signal_book_v4.py:20` shows DEVELOPING when the field is missing.
- **Reproduction:** `p15_F_05_capacity_structure.py`.
- **To close:** a stored run carrying the field on every directed row, with source versions of its inputs, and an absent field shown as absent.
- TRACE: REQ-WP5-03 | NONE | WP-5 | STAGE-5 | TRACK-F | EVIDENCE-final_opportunity_book | N=1444

### UAT-D52 — Displayed Lab numbers lack a joint dataset id and calculation version
- **Original ID:** UAT-D-G1 · **REQ:** REQ-WP6-01 · **Severity:** P2
- **Exposure:** 0/10 rows resolvable on both books (sampled CALL 0/13, PUT 0/6, OTHER 0/1).
- **Evidence:**
  - `contracts/lab_control.py:2391-3018` emits no per-field lineage.
  - Per row, ≈63 numbers are displayed: 18 have a dataset id only, 45 have neither.
  - `field_provenance_json` maps fields to artefact names only, and `lab_signal_book_v3.manifest.json` has no dataset ids.
- **Reproduction:** `python probes/p16_G_g1_lineage.py`.
- **To close:** for every displayed numeric column on a stored run, a (dataset id, calculation version) pair resolves at row or manifest level on 10/10 sampled rows.
- TRACE: REQ-WP6-01 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-p16_G_g1_lineage.json | N=20

### UAT-D53 — Rendered dossier values rounded; exact coaching parity fails
- **Original ID:** UAT-D-G6 · **REQ:** REQ-WP6-03 · **Severity:** P2
- **Exposure:** sampled mismatches CALL 4 / PUT 1 (5/20). Population: target differs on 14/19, invalidation 4/19, spread 19/19.
- **Evidence:** f-string rounding in `build_trade_dossiers.py`, e.g. WRB spread 12.048192771084347 rendered as 12.0. The desk-gate CSV matches 19/19.
- **Reproduction:** `python probes/p16_G_g3_coaching_parity.py`.
- **To close:** the dossier prints Lab values verbatim, or ships a machine-readable companion equal to the v4 book exactly.
- TRACE: REQ-WP6-03 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-p16_G_g3_coaching_parity.csv | N=20

### UAT-D54 — v4 projector invents fallback states
- **Original ID:** UAT-D-G7 · **REQ:** REQ-WP6-01 / NFR-07 · **Severity:** P2
- **Exposure:** offline, all directions.
- **Evidence:** `domain/lab_signal_book_v4.py:9-12,20,24,28` fills missing inputs as follows: execution → `EXECUTION_REVIEWABLE`, structure → `DEVELOPING`, ranking kind → `DETERMINISTIC_UTILITY`, thesis → `UNKNOWN`, contract → `NOT_EVALUATED`, scenario → `UNRESOLVED`. An empty row projects to MONITOR.
- **Reproduction:** `p16_G_g2_projector.py`, key `v4_projector_defaults_on_empty_row`.
- **To close:** absent inputs project to an explicit absent / `NOT_EVALUATED_DATA_MISSING` token, never to a positive SD state.
- TRACE: NFR-07 | ALG-NONE | WP-6 | STAGE-6 | TRACK-G | EVIDENCE-p16_G_g2_projector.json | N=1

### UAT-D55 — Absent or unhealthy price store publishes no outcomes_deferred count; health check runs post-pipeline
- **Original ID:** UAT-D-H2 · **REQ:** REQ-WP7-02 · **Severity:** P2
- **Exposure:** run-level, CALL/PUT/OTHER.
- **Evidence:**
  - `intelligent_orchestrator.py:2225-2237` and `:2252-2262` write `status=DEFERRED` plus a reason and a warning, but no `outcomes_deferred` count.
  - The health check runs inside maturation at `:6633`, not at run start.
  - Stored diagnostics carry no `price_database_health` block.
- **Reproduction:** read the cited lines (the absent-store path was not exercised by any stored run).
- **To close:** a run with the store removed writes `outcomes_deferred = presented candidates × horizons` plus an alert artefact, and the health check is recorded before Discovery.
- TRACE: REQ-WP7-02 | ALG-08 | WP-7B | STAGE-6 | TRACK-H | EVIDENCE-intelligent_orchestrator.py:2225-2262 | N=0

### UAT-D56 — Counterfactual OUTCOME event lacks attribution and family-outperformance fields
- **Original ID:** UAT-D-H3 · **REQ:** REQ-WP7-02 / REQ-WP7-03 · **Severity:** P2
- **Exposure:** CALL/PUT.
- **Evidence:**
  - `canonical_data/decision_outcome_ledger.py:521-535` payload carries MFE/MAE/horizon/first-passage only.
  - Attribution and `family_member_outperformance_state` exist only on the learning snapshot, which has `records: []` (`CURRENT_LEARNING_READINESS.json`).
- **Reproduction:** `p14_EH_ledger_payload_keys.json`.
- **To close:** a matured OUTCOME ledger event on a stored run carries `attribution` and `family_member_outperformance_state`.
- TRACE: REQ-WP7-03 | ALG-08 | WP-7B | STAGE-6 | TRACK-H | EVIDENCE-p14_EH_ledger_payload_keys.json | N=1

### UAT-D57 — Provider API key committed as an environment default
- **Original ID:** UAT-D-I9 · **REQ:** UNMAPPED (credential hygiene) · **Severity:** P2
- **Exposure:** none directional.
- **Evidence:**
  - `avshunter_db_update.py:81` and `bond_macro_intelligence.py:131` carry a literal key default (commit 5d886f0; values redacted in probe output).
  - `release_diff_secret_scan_passed=true` covers only the release diff.
- **Reproduction:** `python probes/p17_IN_environ_classify.py` → `hardcoded_secret_default_sites`.
- **To close:** no tracked file contains a credential literal, and a whole-tree secret scan is part of release evidence.
- TRACE: UNMAPPED | ALG-NONE | WP-NONE | STAGE-NONE | TRACK-I | EVIDENCE-p17_IN_environ_summary.json | N=2

### UAT-D58 — Journal close path chains a trade OUTCOME to an EXECUTION_DECISION when no fill exists
- **Original ID:** UAT-D-N3 · **REQ:** NFR-06 · **Severity:** P2
- **Exposure:** CALL/PUT journal-closed trades; code-level (no stored ledger row shows it).
- **Evidence:** `avshunter_trade_journal.py:993-997` falls back from FILL_RECORDED to TRADE_ENTRY to EXECUTION_DECISION. The ledger has 1 OUTCOME with no predecessor and 0 FILL_RECORDED.
- **Reproduction:** `python probes/p17_IN_nfr06_fills.py` (`outcome_previous_event_type`).
- **To close:** an OUTCOME for a taken position can chain only to a FILL_RECORDED, and a close without a fill records a named data exception.
- TRACE: NFR-06 | ALG-NONE | WP-7A | STAGE-6 | TRACK-N | EVIDENCE-avshunter_trade_journal.py:993 | N=0

---

## P3

### UAT-D59 — resolve_spread legacy-labelled path has no [0,2] range guard
- **Original ID:** UAT-D-B4 · **REQ:** REQ-WP1-03 · **Severity:** P3
- **Exposure:** all directions (adapter unused by stored runs).
- **Evidence:**
  - `domain/quote_units.py:47-50` omits the check applied at `:37,42`.
  - `resolve_spread({'spread_pct': 12.0, 'spread_unit': 'FRACTION_OF_MID'})` returns 12.0 / 1200% with `PASS_LEGACY_ADAPTED`.
- **Reproduction:** fixture in `probes/p11_B_b3_spread.txt`.
- **To close:** `DATA_DEFECT` for legacy-adapted values outside [0,2], with a unit test.
- TRACE: REQ-WP1-03 | ALG-12 | WP-1 | STAGE-2 | TRACK-B | EVIDENCE-p11_B_b3_spread.txt | N=NONE

---

## Severity × count

| Severity | Entries | Original track defects merged into them |
|---|---|---|
| P0 | 4 | 9 (A1, A5, A7, D3, D8, E4, G4, I4, plus P1 A4 merged into UAT-D02) |
| P1 | 38 | 38 |
| P2 | 16 | 16 |
| P3 | 1 | 1 |
| **Total** | **59** | **64** |

## Original ID → new ID

| Original | New | Original | New | Original | New | Original | New |
|---|---|---|---|---|---|---|---|
| UAT-D-A1 | UAT-D01 | UAT-D-C1 | UAT-D12 | UAT-D-E1 | UAT-D22 | UAT-D-H1 | UAT-D33 |
| UAT-D-A2 | UAT-D05 | UAT-D-C2 | UAT-D13 | UAT-D-E2 | UAT-D23 | UAT-D-H2 | UAT-D55 |
| UAT-D-A3 | UAT-D06 | UAT-D-C3 | UAT-D14 | UAT-D-E3 | UAT-D24 | UAT-D-H3 | UAT-D56 |
| UAT-D-A4 | UAT-D02 | UAT-D-C4 | UAT-D47 | UAT-D-E4 | UAT-D04 | UAT-D-I1 | UAT-D34 |
| UAT-D-A5 | UAT-D03 | UAT-D-C5 | UAT-D48 | UAT-D-F1 | UAT-D25 | UAT-D-I2 | UAT-D35 |
| UAT-D-A6 | UAT-D07 | UAT-D-C6 | UAT-D15 | UAT-D-F2 | UAT-D26 | UAT-D-I3 | UAT-D36 |
| UAT-D-A7 | UAT-D02 | UAT-D-D1 | UAT-D16 | UAT-D-F3 | UAT-D50 | UAT-D-I4 | UAT-D02 |
| UAT-D-A8 | UAT-D43 | UAT-D-D2 | UAT-D17 | UAT-D-F4 | UAT-D27 | UAT-D-I5 | UAT-D37 |
| UAT-D-A9 | UAT-D08 | UAT-D-D3 | UAT-D02 | UAT-D-F5 | UAT-D28 | UAT-D-I6 | UAT-D38 |
| UAT-D-A10 | UAT-D09 | UAT-D-D4 | UAT-D18 | UAT-D-F6 | UAT-D29 | UAT-D-I7 | UAT-D39 |
| UAT-D-B1 | UAT-D44 | UAT-D-D5 | UAT-D19 | UAT-D-F7 | UAT-D51 | UAT-D-I8 | UAT-D40 |
| UAT-D-B2 | UAT-D10 | UAT-D-D6 | UAT-D20 | UAT-D-G1 | UAT-D52 | UAT-D-I9 | UAT-D57 |
| UAT-D-B3 | UAT-D45 | UAT-D-D7 | UAT-D21 | UAT-D-G2 | UAT-D30 | UAT-D-N1 | UAT-D41 |
| UAT-D-B4 | UAT-D59 | UAT-D-D8 | UAT-D04 | UAT-D-G3 | UAT-D31 | UAT-D-N2 | UAT-D42 |
| UAT-D-B5 | UAT-D46 | UAT-D-D9 | UAT-D49 | UAT-D-G4 | UAT-D02 | UAT-D-N3 | UAT-D58 |
| UAT-D-B6 | UAT-D11 | | | UAT-D-G5 | UAT-D32 | | |
| | | | | UAT-D-G6 | UAT-D53 | | |
| | | | | UAT-D-G7 | UAT-D54 | | |
