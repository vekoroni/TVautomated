# Deviation register (§4A)

Every place where what was found differs from what the design (SD v1.2), the requirements (REQ v1.2 / Annex A v1.2), the claim sheets or the run artefacts say — including places where the implementation is stricter than specified. Severity applies to acceptance-track deviations only; discovery observations carry none. Entries DEV-01…DEV-14 were established during setup and the comprehension gate; entries from the tracks are appended below them with their track letter.

| ID | What was claimed / specified | What was found | Evidence | Severity |
|---|---|---|---|---|
| DEV-01 | Test prompt §0: claim sheet is searched in `dropbox\macro\coaching\desk_gate\` | No claim sheet there; four implementer claim sheets exist under `audit\avs_fix_002\` (stage0, stage1 slice, stages2_5, stage6) | `ls dropbox/macro/coaching/desk_gate/`; `audit/avs_fix_002/*/` | none (procedural) |
| DEV-02 | Test prompt §0 names design/requirements v1.1 | The desk_gate files are 256–315-byte pointers to governed v1.2 copies under `docs/`; v1.2 is the sole authority (SD §24.1) | `dropbox/.../AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md` (pointer) | none (procedural) |
| DEV-03 | Stage 0 claim: full baseline 1,756 passed / 29 failed / 4 skipped; Stage 1 claim: 1,783 / 39 / 4; Stage 6 claim: consolidated 425 tests, 0 failures | Full governed suite at `cc509cb`: 1,881 passed / 44 failed / 4 skipped (3,961 s). Failed count exceeds every claimed count; Track I reconciles the 44 against `BASELINE_DEFECT_REGISTER.md` | `pytest/full_run.txt`, `pytest/failures_list.txt` | P2 (release evidence does not describe the current tree) |
| DEV-04 | REQ-WP0-01: `run_meta_v2` carries `run_condition`, `baseline_eligible`, `code_identity`, `config_identity`, `session_date`, `evidence_cutoff_utc`, `operator_mode`, `provider_completeness_evidence`, `macro_packet_id` | None of the 27 stored `run_meta.json` files carries any of the nine at top level, although the four newest declare `run_meta_schema_version = run_meta_v2`. Evidence cutoff exists only inside `dynamic_plan`; code identity only as `git_describe`/`baseline_commit_hash`; config identity only as `ddd_runtime_profile.sha256` and `msi_config_hash` | `setup.md` §4; `probes/p01_run_inventory_raw.csv` | run-level NOT IMPLEMENTED (stored runs predate Stage 1); the schema-version string `run_meta_v2` on a file lacking the v2 fields is a P2 lineage deviation |
| DEV-05 | Stage 1 claim: "Provider evidence is persisted in run metadata … `run_meta_v2.json.provider_completeness_evidence`" and outputs `provider_finality_<run_id>.json`, `provider_finality_exceptions_<run_id>.csv` | No stored run directory contains `provider_finality_*` files or `provider_completeness_evidence`; the claim is offline-only (no run has been executed on the Stage 1 code) | `probes/p03_artefact_inventory_raw.csv` | none by itself — the claim sheet says the controlled cycle is still open; recorded so the claim is not read as run evidence |
| DEV-06 | REQ-WP5-01 / `macro_ticker_context_v2`: field `usmi_routing_key` | Not emitted anywhere in code; the route key is published under `usmi_alignment_priority` by the second join | comprehension item 13; grep `usmi_routing_key` → docs only | P2 (field name in the contract does not exist) |
| DEV-07 | Annex ALG-06: "the v1 formula is retained under `ranking_score_uncalibrated_v1` for one release" | Not implemented; the v1 number is computed and overwritten by v2 (`canonical_data/dynamic_options_valuation.py:439-443`), never published under a separate name; C10's Spearman disclosure has to reconstruct v1 offline | comprehension item 12 | P2 |
| DEV-08 | Annex ALG-04/05: headline field `payoff_reachable_net_return_fraction` (and the `payoff_*_net_return_fraction` family) | Names absent from production; the value is an unnamed local `headline` in `domain/contract_economics_v2.py:139` and lives inside `doi_scenarios_json` under scenario id `REACHABLE:LATE:BASE` | comprehension item 9 | P2 (contract field names not honoured) |
| DEV-09 | SD §5.6 / ALG-14: one Macro Advisory join after ticker classification, routing read from `options_monetisation.sector_routing.routing`, `map_routing()` ported not re-derived | Two joins run (`contracts/interpreter_macro_context.py:430-518` before sector backfill; `domain/macro_advisory_context.py:52-94` after, overwriting the first); join 1 reads a normalised routing built from the priority lists, join 2 finds routing by unanchored recursive key search; the port of `map_routing` drops keywords, the `NO_PUT_ROUTE_FOR_SECTOR` branch and the `basis` output | comprehension item 13 | Track F assigns severity |
| DEV-10 | SD §8.4: one monetisability estimate priced at the reachable target with friction | Two engines coexist: `contracts/selected_contract_economics.py` prices structural-target intrinsic (floor 20%, no friction) and structural-target BS (r=q=0, no friction), and is what Morning Gate / EOD read; `domain/contract_economics_v2.py` prices the reachable target with `friction_model_v1` (floor 0.25) on the DOI path only | comprehension item 9 | Track C assigns severity; also a premise note candidate |
| DEV-11 | REQ-WP2-05: OI convexity proxy replaced; "the existing call on the pre-economics row with an empty dashboard shall be removed" | The call at `scripts/avshunter_options_intelligence.py:7754-7755` still exists (twice) and still feeds `convexity_score` to the Lab; the payoff-shape replacement exists only as `doi_convexity_score/label` | comprehension item 10 | Track C |
| DEV-12 | Annex config list: `freshness_minutes`, `clock_skew_tolerance_minutes`, `spread_executable_limit`, `calibration.kappa`, `calibration.n_min`, `vol_validation.minimum_validation_n`, `vol_validation.pass`, `refresh_window` in `config/governed_constants_v1.json` | Not present in the file (present: provider_completeness, volatility_budget, contract_economics, preferred_contract, outcome_learning blocks) | `config/governed_constants_v1.json` | Track I |
| DEV-13 | Test prompt E1: "same-session tie → INVALIDATION_FIRST" | Annex ALG-08 (governing) says same-session dual touch → `AMBIGUOUS_TOUCH_ORDER`, excluded from the denominator; Stage 6 code implements the four-state rule | Annex ALG-08; `domain/outcome_learning.py` | none (the prompt's oracle is superseded by the governing document; Track E applies the Annex rule and reports both) |
| DEV-14 | REQ-WP7-01 / ledger: `planned_hold_sessions` is a decision-record field | Present in every `CANDIDATE_DECISION` payload but null on all 4,931 rows; `decision_stage`, target, invalidation and reference price are populated | `probes/p30_census_ledger_probe.py` output; `outcome_census.md` §1 | P2 (lineage gap; hold is unrecoverable from the ledger alone) |
| DEV-15 | Discovery lifecycle artefact records the reason a ticker left | Seven distinct liquidity/price/tier rejections collapse to the single reason code `NO_SIGNAL_AT_ANY_HORIZON` at `avshunter_discovery_ULTIMATE.py:2536-2545`; counts reconcile but causes are unrecoverable | comprehension item 11 | P2 |
| DEV-16 | SD invariant 1 / REQ §0 rule 1: no governed opportunity is lost without a named exception | Five genuinely silent removal points exist: `run_vanguard_from_packages.py:1444` (governance `continue`, no reject row); `scripts/avshunter_options_intelligence.py:8767` (inner merge), `:8797-8799` (tier scope), `:8805-8808` (WAIT scope) — stdout counts only, physically leave at `:9135-9136`; `scripts/build_packages_from_discovery.py:316-329`, `:570-574`; `canonical_data/dynamic_options_production.py:139-142` (before the `deleted_opportunities == 0` baseline) | comprehension item 11 | Track D assigns severity on the reconciliation result |
| DEV-17 | Design §0 rule 2 / OPS-02: forced, intraday or dirty-tree runs are written as `TEST` | The stored runs record `run_kind = PRODUCTION`, `run_status = ACCEPTED`/`COMPLETED`, `run_tradeable = true`, `run_tradeable_label = EXECUTION_READY` (`final_run_manifest.json`) while being dirty-tree, forced intra-session runs | `run_meta.json`, `final_run_manifest.json` of both reference runs | Track A |

## Track deviations (appended by the coordinator from each track file)

**No NORMAL_COMPLETED_SESSION run exists.** This section holds acceptance-track deviations only (Tracks A–I, N); discovery-track observations are added separately. Where a track row confirms or assigns severity to an entry already in DEV-01…17, it is recorded as a reference line and not duplicated. Defect references use the renumbered IDs in `defects.md`.

### Track A
References: DEV-04 confirmed (27/27 run_meta lack all nine fields; P2 schema-string deviation; run-level defect UAT-D07). DEV-05 confirmed (no stored provider-finality artefacts; Stage 1 replay covers sessions 09-04/08 only). DEV-17 confirmed, severity assigned P1 (UAT-D07).

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-A01 | REQ-WP0-08 gate lives in a `scripts/release_baseline.py` extension | Gate is in `tools/avs_fix_002_stage0.py`; `release_baseline.py` has no import walk | `probes/p10_A_import_graph_out.json.release_baseline` | P3 |
| DEV-A02 | Stage 0 claim: production import graph 138 nodes / 356 edges, all tracked | HEAD gate 152/382; Python-semantics walk 177/479; 25 reachable modules not enumerated; `build_macro_json.py` not an entry point | `probes/p10_A_stage0_graph_now_out.json` | P1 (UAT-D08) |
| DEV-A03 | ALG-12: EXECUTION_EXECUTABLE_NOW requires `run_condition == POSTOPEN_CONTRACT_REFRESH` | Code keys on `morning_execution_mode`, only to force CONTRACT_QUOTE_UNAVAILABLE on a missing ts; no `run_condition` check | `morning_gate.py:2205-2211`, `:2046-2051` | P1 (UAT-D02) |
| DEV-A04 | DOI report `physical_fetch_count` reflects provider fetches | 0 reported vs 1,218 ledger physical requests | DOI JSON line 15; `api_request_ledger` | P2 (UAT-D43) |
| DEV-A05 | ALG-16: one macro packet id + hash per run | 11 Sep run carries two schemes and two hashes (`macro_quant_packet` vs worker3 manifest) | `probes/p10_A_macro_archive_out.json` | P2 |
| DEV-A06 | Ledger `evidence_cutoff_utc` is the run's evidence cutoff | 1,220 distinct values on 11 Sep, 213 on 9 Sep, 2 on 10 Sep; run_meta holds one | `probes/p10_A_ledger_after_cutoff_out.json` | P2 (part of UAT-D01) |
| DEV-A07 | `dataset_registry` COMPLETE / ledger COMPLETED_SESSION mean a completed session | Applied to 12:54–13:53 ET intra-session quotes | control_plane copy | P1 (UAT-D05) |
| DEV-A08 | Annex ALG-12 cites `morning_gate.py:1891` for the fallback | At cc509cb the line is `:1944` and no longer has the fallback | `git show 00baa2b:morning_gate.py` vs HEAD | P3 |
| DEV-A09 | REQ-WP0-06: replay resolves by ID, never "latest" | `orchestrator/macro_loader.py:130,176` still `_find_latest_json()` | `probes/p10_A_macro_archive_out.json` | P1 (part of UAT-D03) |

### Track B
| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-B01 | REQ-WP1-03: the two existing writers converge on the canonical spread field | Only `execution_gate.py:466-468` emits it; `morning_gate.py:982` writes a fraction under `_contract_spread_pct`; `contracts/lab_control.py:2639` writes unlabelled mixed-unit `spread_pct` | `probes/p11_B_b3_spread.txt`; 0/82 CSVs carry the field | P1 (UAT-D10) |
| DEV-B02 | Inventory row 5: `opportunity_tier` adapts the frozen v1 field explicitly as FRACTION_OF_MID | True in code, but the Lab writer puts percent into that field; offline recompute leaves 993/993 spread-BLOCKs (584 with true spread ≤ 25%) | `probes/p11_B_b4_tier.txt` | P1 (UAT-D10) |
| DEV-B03 | REQ-WP1-04: inventory with disposition per site; NFR-03 governed defaults publish `default_applied/source/value` | Row 8 cites absent `domain/capacity_suggestion.py`; named sites `eod_candidate_engine.py:353-360`, `ev_engine_v3.py:445,640` not inventoried; EV3 publishes boolean flags only | `probes/p11_B_b5_silent_defaults.txt` | P2 (UAT-D46) |
| DEV-B04 | REQ-WP1-04 / NFR-03: §8 counter `silent_zero_violations = 0` on a normal run | No producer; key absent from every summary of both runs | grep production = 0 hits | NOT IMPLEMENTED (UAT-D46) |
| DEV-B05 | REQ-WP1-05: `tests/contracts/` | Directory absent; tests in `tests/test_avs_fix_002_*.py` | `ls tests/contracts` | P1 (UAT-D11) |
| DEV-B06 | REQ-WP1-01 cites `layer3_forward_variance.py:515-517` | Differenced computation at `:522-524`; `:515-517` is the regime adjustment | file read | P3 |
| DEV-B07 | REQ-WP1-04 named site `canonical_data/dynamic_options_production.py:231-233` (dividend → 0.0) | At cc509cb the dividend default is at `:290-295` | file read | P3 |
| DEV-B08 | Legacy expected-move unit implicit ("pct") | Legacy `_expected_move` also converts calendar → trading days (×5/7): legacy 1–5d = 0.845 × v2 5d | `layer3_forward_variance.py:174-181`; `probes/p11_B_b1_ratio.txt` | P3 |
| DEV-B09 | `vanguard/ev3_stage0.py:372-389` reads Layer 3 expected moves | Reads `expected_move_{5,10,20}d` / `l3_expected_move_{5,10,20}d`, which Layer 3 never emits; loop silently skips | file read | P2 (part of UAT-D44) |

### Track C
References: D-C10 (v1 not retained as `ranking_score_uncalibrated_v1`) is DEV-07, severity assigned P1 (UAT-D15). DEV-10 and DEV-11 are unchanged by Track C (legacy constant `convexity_score` still published — REQ-WP2-05 OPEN).

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-C01 | REQ-WP2-01 names `dynamic_options_production.py:227-230` as the rate reader | Reader at `:284-289` (bridge rate first, CSV fallback) | source | P3 |
| DEV-C02 | REQ-WP2-02 / Annex: Friday GO reach ratio median 4.1×, 13 of 19 > 3 | ALG-02 cumulative budget gives median 3.48, 11/19; 4.117 / 13/19 reproduced only with the differenced legacy sum | `probes/p12_C_c2_c3_reach_geometry.out.json` | P2 |
| DEV-C03 | ALG-04: European BSM, `dividend_adjusted_black_scholes` reused unchanged | Function clamps to intrinsic / forward intrinsic | `domain/deterministic_option_valuation.py:210-217` | P1 (UAT-D14) |
| DEV-C04 | ALG-04 output names (`FAVOURABLE_REACHABLE`, `FAVOURABLE_STRUCTURAL`, `theta_and_friction_cost_to_time_stop_fraction`, `scenario_iv_fraction`, `modelled_exit_value_per_share`, `friction_assumption`, per-scenario basis `AT_SESSION_n`) — extends DEV-08 (headline `payoff_*` names) | Paths `REACHABLE` / `STRUCTURAL_DISCLOSURE`; no scenario IV; `exit_value_after_friction_per_share`; no `friction_assumption`; one assessment-level basis `AT_GOVERNED_TIME_STOP` | `domain/contract_economics_v2.py:18-59` | P2 |
| DEV-C05 | ALG-04: IV absent → bisection from mid on [0.01, 5.0], else `IV_UNAVAILABLE` | No solver; missing IV → `NOT_EVALUATED_DATA_MISSING / REQUIRED_INPUT_MISSING` (impact unmeasured) | `domain/contract_economics_v2.py:76-81` | P2 |
| DEV-C06 | ALG-03: `dte_inside_hold = true`, reason `CONTRACT_EXPIRES_INSIDE_GOVERNED_HOLD` | No `dte_inside_hold` field; reasons `CONTRACT_EXPIRES_WITHIN_HOLD` / `HORIZON_LIMITED` | `domain/contract_economics_v2.py:92-97` | P2 |
| DEV-C07 | ALG-05: every state carries `authority`, `scenario_id`; `monetisability_state_structural` shown as disclosure | Neither on the state; assessment-level `decision_authority = NONE` only | `domain/contract_economics_v2.py:33-59` | P2 |
| DEV-C08 | ALG-02: reachable spot target-independent; structural target disclosure only | Reachable spot nulled when structural target missing; 60 PUT contracts NOT_EVALUATED solely for this | `domain/reachability.py:39-41` | P2 |
| DEV-C09 | REQ-WP2-07 names `scripts/validate_forecast_vol.py` | Tool at `tools/validate_forecast_vol.py`; emits UNVALIDATED unconditionally; no report produced | source | P3 |
| DEV-C10 | ALG-06 oracle: U populated on every family with a positive ask | U null whenever spread > 0.30 (896 contracts, CALL 476 / PUT 420) | `probes/p12_C_offline_sample.out.json` | P2 |

### Track D
References: DEV-16 severity assigned P2 (latent): the five silent removal paths removed 0 tickers on both stored runs, ticker-grain identity gap 0 (would be P0 if they fire; UAT-D49). DEV-15 is carried into UAT-D49.

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-D01 | REQ-WP3-06 / Annex: `ranking_score_kind = DETERMINISTIC_UTILITY` | Two kinds coexist: `DETERMINISTIC_UTILITY` (`domain/contract_economics_v2.py:150`, `canonical_data/dynamic_options_valuation.py:424`) and `RANKING_SCORE_UNCALIBRATED` (`domain/dynamic_options_ranking.py:406`) | source | P2 |
| DEV-D02 | ALG-16 `assessment_id` components | Namespace + run-scoped `family_id` + `observation_id`, no milliseconds | `probes/p13_D_d7_assessment_identity.json` | P1 (UAT-D21) |
| DEV-D03 | DOI families carry the thesis origin for the run | Primary-run families share `created_at = origin = evidence_cutoff` 2026-09-10T16:54–17:53Z with the comparison run, 1h53–2h52 after the comparison cutoff; `origin_spot` differs between runs for the same origin (PLAB 28.56 vs 28.38) | `probes/p13_D_d3b_exceptions.json` | P2 |
| DEV-D04 | Evidence cutoff bounds quotes used by the run | Primary Lab EXECUTABLE_NOW quotes +301–306 min after cutoff; comparison +114–172 min | `probes/p13_D_d5b_quote_truth.json` | P2 (overlaps UAT-D01) |
| DEV-D05 | REQ-WP3-05: `refresh_window_state` | Published as `postopen_contract_refresh_window_state` | `morning_gate.py:3325` | P3 |
| DEV-D06 | Thesis identity format is governed | Book formats `T:DIR:<date>:OLM2` 1,218, `T:UNRESOLVED:<run>` 188, `T:DIR:<run>` 38 | `probes/p13_D_d3b_exceptions.json` | P2 |
| DEV-D07 | Options Intelligence OI thresholds | `EV3_MIN_OPEN_INTEREST = 50`, `EV3_MIN_VOLUME = 1` defined, never referenced; `MIN_OI = 50` limits only the Heston sample | `scripts/avshunter_options_intelligence.py:1335-1336, 2061` | P3 |
| DEV-D08 | Probability naming | `phase_transition_probability` holds 32–61 (percent) | `probes/p13_D_d8b_probability_fields.json` | P3 |

### Track E
References: DEV-13 confirmed, severity none (Annex ALG-08 AMBIGUOUS_TOUCH_ORDER governs; sample had 0 ties; population has 1 ambiguous CALL row). DEV-12 confirmed for `calibration.kappa` / `calibration.n_min` (UAT-D36).

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-E01 | REQ-WP4-01 location `vanguard/layer2_statistical/calibration_labels.py` over the actuarial DB | File absent; labelling in `domain/decision_outcome.py` + `domain/outcome_learning.py` over ledger and price store; `data/actuarial_db.sqlite` 0 bytes | file listing | P3 |
| DEV-E02 | ALG-08 target = S_d(1 ± k·e_h) | Production path labels against structural `target_price` | `canonical_data/outcome_maturation.py:111-113,162-169` | P1 (UAT-D22) |
| DEV-E03 | ALG-09 coverage = fraction of scoreable rows resolving at match_level ≤ 2 | Code coverage = learning records / expected observable outcomes | `domain/outcome_learning.py:325-326` | P2 |
| DEV-E04 | ALG-09 gate: stratum ECE ≤ 0.15 where held-out n ≥ 100 | Code requires ≥ 100 fit-eligible outcomes in each of six strata as a hard precondition | `domain/outcome_learning.py:331-345` | none (stricter) |
| DEV-E05 | ALG-09 partitions with 20-session embargo at each boundary | Embargo taken from the start of validation/test slices, counted in distinct data sessions | `canonical_data/outcome_learning.py:68-71` | P3 |
| DEV-E06 | ALG-09 metrics: multiclass Brier, classwise ECE, log loss, ROC/PR-AUC, lift, reliability curve | No ALG-09 metric implementation; activation consumes caller-supplied metrics; DOI has a separate binary logistic + Platt path | `domain/outcome_learning.py:347-374`; `canonical_data/dynamic_options_probability.py:188-206,244-297,336-395` | P2 |
| DEV-E07 | ALG-09 `match_level` 0…4 integer | String "0"…"4" | `domain/outcome_learning.py:82` | P3 |
| DEV-E08 | Stage 6 claim: hierarchical backoff explicit via `backoff_chain()` | Chain explicit; four count/weight lineage fields absent | `probes/p14_EH_e5_backoff_out.json` | P1 (UAT-D24) |
| DEV-E09 | ALG-08: forced/test/dirty runs excluded from fitting | `RUN_CONDITION_*` exclusion added only when `run_condition` non-empty; absent condition caught only via `baseline_eligible` default false | `canonical_data/outcome_learning.py:201-297` | P3 |

### Track F
References: DEV-06 confirmed P2 (UAT-D50). DEV-09 severity assigned P1: two joins; Join 1 category names never match `SECTOR_ALIASES`; Join 2 port differs on 32 routed rows, drops `basis` and `NO_PUT_ROUTE_FOR_SECTOR`, changes UNAVAILABLE semantics; unanchored `_find` hits `scenarios={}` (UAT-D25, UAT-D26, UAT-D27).

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-F01 | Run lineage `git_describe = 00baa2b-dirty` identifies the run code | `macro_domain/us_money_index.py` (emitter of `usmi_*` in the run) absent at 00baa2b, first committed c1eabaa after the run; Join 2 / structure evidence first in 9e9604c; run code not exactly recoverable | `git cat-file -e 00baa2b:macro_domain/us_money_index.py` | P2 |
| DEV-F02 | ALG-14 `conditions_all = [{metric, op, value}]` | Packet carries free-text clauses with OR, intervals, state tokens; neither evaluator parses them | `macro_snapshot.json forward_triggers.scenarios.*.conditions_all` | P1 (UAT-D27) |
| DEV-F03 | Stages 2–5 claim sheet line 13: REQ-WP5-04 PASS — config, projection and dependency tests | Test has no production-path dependency scan; calculators remain in 3 production modules; `mastermind_config.json` has `account` | `tests/test_avs_fix_002_stages2_5.py:176-200` | P1 (UAT-D28) |
| DEV-F04 | Canonical GICS store | Universe `sector` not pure GICS (ETF 82, Power Generation 3, …); BA/RTX/GE = IT; ZION = Energy; book vs store disagree CALL 9 / PUT 4 | `probes/p15_F_01_summary.json`, `p15_F_02b_sector_disagreements.csv` | P2 |
| DEV-F05 | REQ-WP5-05: every macro consumer is display or context | DOI production reads the macro file for its market rate (valuation input); effect on executability not tested | `canonical_data/dynamic_options_production.py:125-132` | P3 |

### Track G
| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-G01 | REQ-WP6-01: v4 read model shows thesis p (source, n or UNCALIBRATED), scenario payoffs, spread, IV vs forecast, theta, lifecycle, refresh state, macro route, what-changed | v4 emits 15 fields covering 7/16 named elements | `domain/lab_signal_book_v4.py:17-33` | P1 (offline) |
| DEV-G02 | SD §9.1/9.3/9.5 vocabularies on the Lab | Run books use legacy tokens; v4 projector passes them through unmapped (1,444 × MONITOR) | `probes/p16_G_g2_projector.json` | P2 |
| DEV-G03 | One run, one Lab schema | Final book `lab_signal_book_v2`, v3 book `lab_signal_book_v3`, same run | `probes/p16_G_g1_lineage.json` | P3 |
| DEV-G04 | `quote_freshness` is a quote property | v3 and final books label the same `quote_as_of` STALE vs FRESH; freshness is a materialisation-time TTL | `contracts/quote_change_evidence.py:187-193` | P0 (UAT-D02) |
| DEV-G05 | `structural_target` is a price | 29 PUT rows carry negative `structural_target` (CAVA −10.94, CIFR −16.76, HIMS −3.34) with `target_state=UNRESOLVED` | final book; `probes/p16_G_g4_overlay_parity.json` | P2 (UNMAPPED) |
| DEV-G06 | `field_provenance_json` is per-field lineage | Maps field → producing artefact name, no dataset id or version | `probes/p16_G_g1_lineage.json` | P2 (UAT-D52) |
| DEV-G07 | Coaching board regenerated from `lab_signal_book_v4` | Board reads only `macro_intelligence_latest.json` | `build_coaching_board.py:5,335` | P1 (UAT-D32) |
| DEV-G08 | core_intel dossiers describe the run's preferred contracts | Exported 15:10Z before the 17:08Z gate; 3/19 GO rows carry the superseded contract (AA, SIRI, SPGI) | `probes/p16_G_g3_coaching_parity.json` | P2 |
| DEV-G09 | REQ-WP6-04: overlay vocabulary not carried into the Lab | `NO_TRADE` / `WATCH` tokens in legacy Lab columns; `TRADE_PROBE` absent; no `dg_*` column | `probes/p16_G_g4_overlay_parity.json` | P3 |
| DEV-G10 | REQ-WP6-04 parity oracle covers thesis/execution state | Desk-gate overlay carries neither column | `probes/p16_G_g4_overlay_parity.json` | P2 |
| DEV-G11 | Design review: overlay parity "Yes" | No parity report or archive manifest exists | `dropbox/macro/coaching/desk_gate/AVS-QA-SD-FIX-002_v1.1_verification.md:43` | P2 |

### Track H
| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-H01 | Design event names `HumanDecisionRecorded`, `FillRecorded` | Code vocabulary `PRESENTATION_DECISION`, `FILL_RECORDED`; `decision_record_v2`/`fill_record_v1` are payload versions | `domain/decision_outcome.py:28-29`; `canonical_data/decision_outcome_ledger.py:258,280` | P3 |
| DEV-H02 | REQ-WP7-01: CLI or Lab form for manual fills, source ∈ {MANUAL_CONFIRMATION, BROKER_IMPORT}, side BUY/SELL | CLI hard-codes `side="BUY"`, `source="MANUAL_CONFIRMATION"`; no Lab form | `tools/record_manual_decision.py:24-26` | P2 |
| DEV-H03 | Stage 6 claim: capture every presented candidate, six-horizon reconciliation; stored-run replays PASS | 0 of 3,252 candidates eligible on stored runs; `population_reconciled` false; 19,512 candidate-horizons unaccounted; reconciliation only in unit tests | `CURRENT_LEARNING_READINESS.json`; `probes/p14_EH_e4_snapshot_from_copies.json` | P1 (UAT-D33) |
| DEV-H04 | Pre-registered H3: deferral reason is horizon-not-elapsed | Deferred 0 on every stored run; ineligibility `COMPLETED_SESSION_UNAVAILABLE` on 100% (root cause also DEV-14) | `probes/p14_EH_h3_eligibility_out.json` | P1 (UAT-D33) |
| DEV-H05 | Price store present and current | Present but last bar 2026-09-10 at copy time 2026-09-12 | `probes/p14_EH_h3_price_store_out.json` | P3 |

### Track I
References: DEV-03 severity assigned P1 — 44 failure elements = 33 cases; 30 in register families; 14 cases in 5 files never registered (UAT-D40). DEV-12 confirmed and extended to 9 of 29 Annex keys absent, severity P1 (UAT-D36).

| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-I01 | Stage 6 closure report:48 "Stored-run replay: PASS"; Stages 2–5 closure:17 "Stored replays" | Parametrised data-shape test over stored CSVs; no rebuild, no diff, no book hash | `tests/test_avs_fix_002_stages2_5.py:225-245` | P1 (UAT-D34) |
| DEV-I02 | REQ-WP8-01 names `release/expected_diffs/<change>.json` | `release/` does not exist | tree | P1 (UAT-D34) |
| DEV-I03 | Stage 0 register: CDS ×3 contamination to be isolated; R07 hard-coded runtime to be replaced | Both still fail in the full governed run at HEAD | `pytest/failures_list.txt` | P2 |
| DEV-I04 | Stage 0 claim sheet:33: a baseline failure may change only with a claim naming old assertion, new rule, positive replacement | 4 weakened test files (b36f536, 57a99d7) carry no such claim; W05 still asserts the removed rule | `probes/p17_test_edits.csv` | P0/P1 (UAT-D02, UAT-D37) |
| DEV-I05 | Policy manifest `capital_allocation_boundary.configuration: REMOVED` | `AVSHUNTER_ACCOUNT_RISK_BUDGET` default 1000 read | `execution_intelligence_runner.py:2427` | P2 (UAT-D39) |
| DEV-I06 | Policy manifest `release_diff_secret_scan_passed: true` | 2 committed credential literals elsewhere in the tree | `probes/p17_IN_environ_summary.json` | P2 (UAT-D57) |
| DEV-I07 | Stage 1 manifest hashes describe its release | 2 of 18 entries no longer match; no manifest for `cc509cb` | `probes/p17_IN_manifest_hashes.csv` | P2 (UAT-D38) |

### Track N
| ID | Claimed | Found | Evidence | Severity |
|---|---|---|---|---|
| DEV-N01 | `option_contract_selection_events.economics_recomputed` records a recomputation fact | Constant 1 on 3,006/3,006 events, including 453 requotes with no new observation | `probes/p17_IN_nfr05_immutability.json` | P1 (UAT-D42) |
| DEV-N02 | Stage 6 manifest: decision and fill are separate append-only events | Types separate; journal close path falls back to EXECUTION_DECISION as trade predecessor | `avshunter_trade_journal.py:993-997` | P2 (UAT-D58) |
| DEV-N03 | NFR-01: only the Thesis context writes direction/target/invalidation/hold | Morning Gate, orchestrator router patch and Lab write hold/target | NFR-01 grep | P1 (UAT-D41) |
| DEV-N04 | NFR-05 three-direction scope | Observation schema admits only CALL/PUT; 188 OTHER strangle rows have no contract observation or selection lineage | `option_contract_observations` DDL CHECK | P2 |

## Coordinator addendum — artefacts opened after the inventory (§2.2 step 7)

| ID | What was claimed / specified | What was found | Evidence | Severity |
|---|---|---|---|---|
| DEV-18 | REQ-WP1-04 / NFR-03: no undisclosed default on the rate path; Track C1 found DOI reporting `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` on 1,218/1,218 | On the same primary run EV3 evaluated 376 contracts (175 CALL, 201 PUT) with the policy default rate 0.045 and dividend 0.0; the parquet flags `ev3_rate_defaulted` but carries no `default_source`/`default_value`. Two engines in one run disagree on whether a rate exists | `ev3_shadow/ev3_stage1_contract_evaluations.parquet`; `vanguard/ev_engine_v3.py:32,640` | P2 (cross-referenced to the Track B silent-default defect) |
| DEV-19 | REQ-WP3-06: probability fields null unless calibrated | The same parquet holds uncalibrated `ev3_p_target` / `ev3_p_stop` / `ev3_p_timeout` on 376 contracts; Track D scanned the ev3_shadow CSV/JSON, not the parquet, so this extends the population of the merged P0 on uncalibrated probability fields | `ev3_shadow/ev3_stage1_contract_evaluations.parquet` | P0 population extension (no new defect ID) |
| DEV-20 | Ledger decision record carries hold and session | Hold and completed session are recoverable from run artefacts (`options_candidates_ranked.csv` `planned_hold_sessions`; `completed_thesis_receipt` `completed_session`) but not from the ledger; the four run files disagree on hold for 739 of 1,444 tickers | `artefact_inventory.csv` unexamined notes | P2 (one producer per fact violated) |
