# AVS-TST-SD-002-001 — Independent test findings

**Under test:** the AVS-SD-002 Rev 1.1 Phase 0–8 dynamic-session build closed 2026-09-03.
**Tester:** independent, read-only on production code and run data.
**Method:** static reading, isolated per-file pytest processes, fixture-driven probes, and diff against the Phase 0 pre-change backup. **No pipeline entry point was executed and no feature flag was ever set.**
**Runtime:** `venv/Scripts/python.exe` (3.13.14, pytest 9.1.1) for pytest; `C:\Python314\python.exe` (3.14.0) for hashing, static analysis and the restore drill. Full command lines and artefact hashes in `environment.json`. See DEF-011 for why the prompt's nominated interpreter could not be used for pytest.

**Totals:** 101 claims registered (73 VERIFIED, 2 VERIFIED_OFFLINE, 7 SOURCE_ONLY, 19 CONTRADICTED); 32 defects filed (1 P0, 11 P1, 20 P2); 100 shipped phase tests re-run in isolation and all 100 reproduced; **70 new adversarial tests written and executed — 62 passed, 8 failed, where every one of the 8 failures *is* a finding.**

---

## 1. Production-safety verdict

**No. The legacy `--evening` / `--morning` path is not behaviourally unchanged, and the Phase 8 closure's statement that "Production impact: None" is false — although every individual change is sanctioned by AVS-AR-003 and none of them is a flag leak.**

The eight frozen feature flags are genuinely off and genuinely safe. `_as_bool` (`contracts/dynamic_session_contract.py:87-95`) returns `False` for unset, empty *and unrecognised* values, so a typo cannot enable one. A full grep of the live tree found no read of any dynamic flag with a truthy default. The CLI branch is clean: `dynamic_requested = auto or finalise or replay or plan_only`, so with the flag off and none of those switches, `--evening` and `--morning` reach exactly the same `evening_workflow` / `premarket_workflow` calls as before (`intelligent_orchestrator.py:6342-6440`). Every new module — `orchestrator/dynamic_dispatcher.py`, `dynamic_thesis.py`, `dynamic_validation.py`, `dynamic_release.py`, `market_structure/*`, `canonical_data/decision_outcome_ledger.py`, `scripts/build_completed_market_profiles.py` — is unreachable from the legacy path.

What *did* change unconditionally, and is now live the moment anyone runs `--evening` or `--morning`:

| # | Module | Change | Sanctioned by |
|---|---|---|---|
| 1 | `avshunter_discovery_ULTIMATE.py` | RISK_OFF/TRANSITIONAL tier-1 floors, the phase×regime state-prior table, the regime conviction boost, the regime-alignment component and the macro sector lift are all removed or pinned | P0-03, AR-003 §7.2 |
| 2 | `regime_threshold_injector.py` | `apply_regime_to_config` no longer mutates `tier1_min`, `tier2_min`, `tier3_min`, `compression_max`, `extreme_compression`, `min_avg_vol20` | P0-03 |
| 3 | `macro_horizon_router.py` | the macro file is optional; the `bias is None → block` path is removed | AR-003 §7.8 |
| 4 | `vanguard/layer2_statistical/state_calculator.py` | `_calculate_macro_regime` pinned to `TRANSITIONAL` / p50 | AR-003 §7.5 |
| 5 | `vanguard/trade_governance.py` | Q2 macro flip demoted from HARD to ADVISORY | AR-003 §7.5 |
| 6 | `scripts/run_vanguard_from_packages.py` | a neutral macro payload feeds the engine; **and the ACCUMULATION×RISK_OFF tier-demotion exemption is removed** (a strictly larger set of Tier 1→2 demotions, mentioned in no closure) | P0-03 |
| 7 | `scripts/avshunter_options_intelligence.py` | R:R contributes zero points; `derive_verdict` no longer demotes EXECUTE→ARMED on R:R | AR-003 §7.7 |
| 8 | `eod_candidate_engine.py` | `MIN_RR` removed from Tier A/B, the quality floor, the gap report **and `_true_fatal_block`** — the last of which is a candidate-*population* change, not a tier change | AR-003 §8 |
| 9 | `execution_gate.py` | capital authority moved from `monetisability_state` to `execution_viability_state`; the LIMITED size cap removed; **`SPREAD_MAX` loosened 0.15 → 0.18** | AR-003 §7.10 (the spread cap: nothing) |
| 10 | `morning_gate.py` | viability recomputed from the current quote on every invocation; real quote age; frozen-thesis guard; **`_recompute_selected_contract_economics` now always returns `True`** | AR-003 §7.11 (the return-value change: nothing) |
| 11 | `morning_gate.py` (structure) | Polygon 1-minute callback → governed MarketData 5-minute; `ms_*` copied into result rows | AVS-SD-002 §5.3 |
| 12 | `contracts/long_option_policy.py`, `selected_contract_economics.py`, `lab_control.py` | new viability contract, `ADVISORY_SCENARIO_ONLY` / `EXPIRY_INTRINSIC_FLOOR` labels, ten new projected fields | AR-003 §7.10, §7.12 |
| 13 | `intelligence-lab/intelligence_lab.py` | legacy in-memory assembly now returns `signals: []` and `GOVERNED_BOOK_UNAVAILABLE_FAIL_CLOSED` | P0-05 |
| 14 | `intelligence-lab/static/index.html` | 23 lines of frozen/current dossier markup rendered **unconditionally**, not behind `AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED` as the Phase 7 closure implies | — |
| 15 | `canonical_data/registry.py` | **`SCHEMA_VERSION` v1 → v2 with five `ALTER TABLE ADD COLUMN` and two `UPDATE` statements against the live control plane on the next `initialise()`** | Rev 1.1 §11 (the fact that it fires unflagged: nothing) |

I confirmed the live `data/canonical/control_plane.sqlite` is still at `cds_control_plane_v1` with the original 14 ledger columns and 16,870 rows, so item 15 has not yet fired. It will fire on the next legacy run (DEF-009).

Items 6, 8, 9 (spread cap), 10 (return value) and 14 are the ones I would put in front of ACK before the next run: each is a real behaviour change on the live path that no closure describes.

---

## 2. Fix table F01–F37

| Fix | Status | Evidence |
|---|---|---|
| **F01** Reproducible release baseline + verified restore | **CONTRADICTED (source) / VERIFIED (databases)** | `T0_evidence_integrity.md §T0.3, §T0.6`. Three databases restore with matching hashes, `integrity_check=ok` and matching table counts. The source tree omits `orchestrator/` and `market_structure/` — **DEF-006 (P0)** |
| **F02** Frozen contracts + eight reversible flags, all default off | **VERIFIED, with DEF-008** | `T1_xml/T1_phase0.xml`, `T0_flag_inventory.csv`. Eight flags confirmed; one capital owner confirmed; **a ninth, undeclared flag gates the P0-02 fix** |
| **F03** Deterministic hashed RunPlan, plan-only resolution, append-only store | **VERIFIED (determinism) / CONTRADICTED (probe reproduction)** | `T1_xml/T1_phase1.xml`, `T1_phase1_plan_hash_probe.log`, T3 a3_09a–d. Order-insensitive, material-input-sensitive, idempotent — but the published probe hash does not reproduce (**DEF-012**) |
| **F04** Invocation identity separate from run/thesis; idempotent retry; linked changed-scope retry | **VERIFIED** | T3 a3_09a/b; `test_control_plane_v1_ledger_migrates_without_losing_rows` |
| **F05** Session-aware planning on the shared XNYS clock; provider-finalisation distinction | **VERIFIED** | `T1_phase1.xml`, `T1_phase8.xml` — five-state decision table |
| **F06** Discovery macro-invariant (tiers, priors, sector lift) | **VERIFIED** | T3 a3_02a/a3_02b — bitwise-equal across 7 regimes × 6 buckets × 4 maturities; thresholds identical CRISIS vs absent |
| **F07** Vanguard L2 macro-invariant | **VERIFIED**, but the fix register misnames a file | T3 a3_02c. `edge_detector.py` is **byte-identical to baseline** — it needed no change because it reads only the now-constant `state.macro_regime` |
| **F08** Horizon routes with macro absent; macro cannot block/resize/choose | **VERIFIED** | T3 a3_02d (CALL/PUT/STRANGLE); 38 embedded checks re-run, all pass (`T1_router_embedded_qa.log`) |
| **F09** Legacy R:R removed from Options verdict and EOD tier authority | **VERIFIED** | T3 a3_07 (CALL/PUT) — `classify_tier`, `derive_verdict` and `execution_gate` all identical at rr ±999 |
| **F10** One long-option quote policy: single denominator, thresholds, quote age | **CONTRADICTED** | Four independent spread expressions and five thresholds remain; one divides by `mark`. **DEF-014**, **DEF-015** |
| **F11** Execution viability separated from scenario monetisability | **VERIFIED (both halves) with a fail-open** | T2: NOT_MONETISABLE + viable quote → BUY_NOW; all six viability failure states block. But absent viability state → BUY_NOW. **DEF-016 (P1)** |
| **F12** Morning recomputes viability from the current bid/ask | **VERIFIED** | `morning_gate.py:2113` runs on every invocation from `live_data` |
| **F13** Frozen-thesis guard at the Morning handoff | **VERIFIED** | `test_frozen_thesis_guard_allows_annotation_and_rejects_mutation`; wired at `morning_gate.py:2645` |
| **F14** Lab fails closed without a governed book | **SOURCE_ONLY** | the source change is correct; the shipped test is three `assertIn`/`assertNotIn` calls on file text and never executes the Lab |
| **F15** Interpreter production path manifest-only; retired paths unreachable | **VERIFIED (dispatch) / CONTRADICTED (import graph)** | T3 a3_11b/a3_11c pass; a3_11 fails — the MarketData client is in the graph. **DEF-013** |
| **F16** Frame-preserving MarketData candle adapter | **VERIFIED** | `test_marketdata_parallel_arrays_preserve_every_candle_and_time_domain` + mismatched-array fail-closed |
| **F17** Interval-aware canonical intraday resolver with calendar-derived expectations | **VERIFIED** | `test_interval_has_distinct_canonical_schema`, `test_regular_and_early_close_counts_are_calendar_derived` |
| **F18** Exact cache zero calls; partial fetch missing ranges only; cutoff defers | **VERIFIED** | three callback-counting tests in `T1_phase3.xml` |
| **F19** Inactive ticker → zero calls; per-ticker isolation; systemic threshold | **VERIFIED** | `test_batch_blocks_inactive_and_isolates_provider_failure`; `test_completed_profile_stage_isolates_ticker_and_flags_systemic_failure` |
| **F20** Cadence classification corrected | **VERIFIED (defect) / CONTRADICTED (vocabulary)** | the 15-min-as-1-min lie is fixed; the labels are `COARSE_15_MINUTE`/`COARSE_30_MINUTE`, not the design's `FIFTEEN_MINUTE_TPO`/`THIRTY_MINUTE_TPO`. **DEF-017** |
| **F21** `MarketProfileEvidence` typed packet; nulls not zeros; no authority fields | **VERIFIED (schema) / CONTRADICTED (values)** | T3 a3_01 passes — no direction/action/capital *field*. a3_01b fails — `from_mapping` accepts `can_grant_capital` from the payload. **DEF-018 (P1)** |
| **F22** Vanguard fail-open removed | **VERIFIED_OFFLINE (flag-on) / CONTRADICTED (flag-off)** | governed branch is correct for CALL/PUT/UNRESOLVED. **With the flag off — the current production state — the legacy calculator still rebuilds a profile from daily OHLCV, so P0-02 is unfixed in production. DEF-019 (P1)** |
| **F23** Completed-profile stage after Discovery, before Vanguard; persisted; cache-reused | **VERIFIED_OFFLINE** | `test_completed_profile_stage_persists_and_reuses_cache` (0 physical requests on rerun); stage order fixed in `BUILD_THESIS_STAGES` |
| **F24** `build_thesis(plan)` fixed order, EOD_PREPARED ceiling, immutable receipt, population identity | **VERIFIED except population identity** | non-BUILD plan rejected; inflation rejected; **loss accepted, `exception_count` never compared. DEF-020 (P1)** |
| **F25** `validate_thesis`: underlying-first, survivor-only, stop-on-invalidation | **VERIFIED_OFFLINE** | invalidated ticker → zero option and zero bar callbacks |
| **F26** Symmetric CALL/PUT geometry | **VERIFIED** | T3 a3_04a — I added the two CALL mirrors the shipped pack omits (only 1 CALL / 3 PUT were parametrised); both hold. Non-directional → no transition, no acquisition |
| **F27** Profile lifecycle states; EOD profile immutable | **VERIFIED_OFFLINE** | premarket 0 bar calls; RTH developing only after survival; after-hours PARTIAL until finalised |
| **F28** Morning Market Structure provider swapped to MarketData 5-minute | **VERIFIED_OFFLINE** | `_fetch_polygon_minute_bars` removed; no Polygon minute URL on the structure path |
| **F29** `ms_*` evidence copied into Lab result rows | **VERIFIED_OFFLINE** | `test_morning_profile_evidence_is_written_to_result_row`; run `20260901_082437` confirms the pre-fix shape |
| **F30** Validation event immutable identity, atomic persistence | **VERIFIED** | `test_validation_event_persistence_is_immutable`; `test_validation_file_and_ledger_are_both_idempotent` |
| **F31** Dynamic dispatcher: governed pointer, thesis reuse, compatibility mapping, plan-before-callback, new run id | **VERIFIED (unit) / VERIFIED_OFFLINE (run level)** | no `os.listdir`, `glob`, `iterdir` or `st_mtime` anywhere in the dispatcher; `latest.json` at `:57`; CLI traced statically, never invoked |
| **F32** Append-only Decision and Outcome Ledger | **VERIFIED, with a gap** | T3 a3_10 — raw UPDATE and DELETE both rejected, double append gives one row, accepted and rejected captured. **Deferred candidates are not modelled** |
| **F33** v3 materializer: two axes, event-bound bundle, fail-closed matching | **VERIFIED** | T3 a3_05, a3_05b, a3_06 (4 fields), a3_06b — tampering either published file raises `HandoffValidationError` |
| **F34** Lab cache signature includes the v3 handoff/bundle files | **VERIFIED (source)** | all four paths in `_secondary_signal_paths` (`intelligence_lab.py:256-259`) |
| **F35** Release assessor: hash-bound, three states, refuses premature promotion | **VERIFIED** | five in-process probes reproduce `NOT_READY` and the six failed gates exactly; tampered byte → 15 `HASH_MISMATCH`; missing → `MISSING`; `../` → `OUTSIDE_REPOSITORY`; forcing every gate to PASS still yields `NOT_READY` via `PASS_WITHOUT_ARTIFACT`, and all four promotion stages refuse |
| **F36** `release_baseline.py --verify-only` KeyError fixed | **VERIFIED** | exit 0, `passed=true` against an isolated tmp restore. The pre-fix expression evaluated its default eagerly |
| **F37** 25 test reconciliations | **CONTRADICTED in part** | 18 legitimate, 6 weakened, 1 fixture. See §5 and `T2_test_edit_audit.csv` |

**Fixes on the register that no closure actually claims:** none. Every F-row maps to at least one closure bullet. Two rows misname their implementation site: F07 names `edge_detector.py` (unchanged) and F10/F11 describe `contracts/long_option_policy.py` and `selected_contract_economics.py` as "new" modules when both pre-existed and were extended.

---

## 3. Gate and P0 tables

### Gates

| Gate | Implementer | Mine | Evidence |
|---|---|---|---|
| G01 | NOT_RUN | **OUT_OF_SCOPE** | live cycle |
| G02 single session clock | PASS | **VERIFIED** | all dynamic entry points use `canonical_data.session_clock`; `T1_phase1/8.xml` |
| G03 separate evidence identities | PASS | **VERIFIED** | `T1_phase5.xml`, `T1_phase7.xml` |
| G04 deterministic AUTO plan | PASS | **VERIFIED** | `test_fixed_cutoff_matrix_is_deterministic` (5 states) + T3 a3_09a/c/d |
| G05 current thesis reuse | PASS | **VERIFIED** | `test_plan_preview_is_read_only_and_current_closed_thesis_is_reused` |
| G06 no premarket profile fabrication | PASS | **VERIFIED** | `test_premarket_profile_state_makes_zero_bar_resolver_calls` |
| G07 RTH missing intervals only | PASS | **VERIFIED** | three callback-counting tests |
| G08 provider-confirmed finalisation | PASS | **VERIFIED** | `test_after_hours_provider_confirmation_is_required_for_finalisation` |
| G09 restart and scope identity | PASS | **VERIFIED** | T3 a3_09a/b |
| G10 macro advisory and refreshable | PASS | **VERIFIED** | T3 a3_02a–e — the strongest-evidenced area of the build |
| G11 frozen direction/horizon/geometry | PASS | **VERIFIED** | `test_frozen_thesis_guard…`; T3 a3_03 |
| G12 current price transition only | PASS | **VERIFIED** | T3 a3_04a (6 cases incl. the two missing CALL mirrors), a3_04b |
| G13 quote required only for execution | PASS | **VERIFIED** | `test_option_and_advisory_profile_failures_are_isolated` |
| G14 Lab/Interpreter event parity | PASS | **VERIFIED** | T3 a3_05, a3_05b, a3_06, a3_06b |
| G15 population and request reconciliation | PASS | **CONTRADICTED** | request accounting verified; **population identity is an inequality, and loss is accepted — DEF-020**; the horizon router drops STRANGLE entirely — DEF-027 |
| G16 replay no future data | PASS | **VERIFIED** | `test_replay_has_no_provider_requirements_or_capital_authority` |
| G17 no unexplained P0/P1 regressions | PASS | **CONTRADICTED** | the 900/1/43/0 arithmetic is exact (I disagree with the prompt's suspicion), but six excluded failures are today's Phase 1 regressions labelled as pre-existing — DEF-022; and the reconciliation evidence is not hash-bound — DEF-001 |
| G18A–D, G19 | NOT_RUN | **OUT_OF_SCOPE** | live cycle |
| G20 backup restore verified | PASS | **VERIFIED for the databases; the gate does not cover the source tree** | independently reproduced. The gate's wording ("three SQLite baselines restored") is accurate; it is P0-01/F01 that overclaims |

### P0s

| P0 | Implementer | Mine | Evidence |
|---|---|---|---|
| P0-01 reproducible release | CLOSED OFFLINE | **CONTRADICTED** | databases yes; source tree no — **DEF-006 (P0)**. The environment record also names an interpreter that cannot run the tests — DEF-011 |
| P0-02 Market Profile fail-open | CLOSED OFFLINE | **CONTRADICTED** | correct behind `AVSHUNTER_COMPLETED_PROFILE_ENABLED`; **unfixed on the current production path — DEF-019.** The release gate is "no daily-only aligned result", and flag-off still permits one |
| P0-03 macro authority | CLOSED OFFLINE | **VERIFIED** | the best-evidenced closure in the set: bitwise invariance at Discovery, the injector, Vanguard L2, the router and the Execution Gate |
| P0-04 economics authority | CLOSED OFFLINE | **VERIFIED with a fail-open** | R:R and scenario monetisability genuinely hold no authority; but the replacement authority does not fail closed on missing evidence — **DEF-016** |
| P0-05 Lab fail-open | CLOSED OFFLINE | **SOURCE_ONLY** | the change is right; the only test is a source-text grep |
| P0-06 restart collisions | CLOSED OFFLINE | **VERIFIED** | T3 a3_09a–d |
| P0-07 thesis geometry | CLOSED OFFLINE | **VERIFIED_OFFLINE — contract level only** | frozen geometry, symmetric transitions and explicit defer all hold. **The latest run still reports `system_defects.missing_selected_handoff.invalidation_spot = 127`.** Data-level closure requires a fresh run showing that field at 0 |
| P0-08 live lifecycle | OPEN | **OUT_OF_SCOPE** | live cycle |

---

## 4. Test-edit verdict

| Classification | Count (of the 25) |
|---|---|
| OBSOLETE_ASSERTION_CORRECTED | 14 |
| FIXTURE_CORRECTED | 6 |
| **PROTECTION_WEAKENED** | **5** |
| UNRELATED_CHANGE | 0 |
| **Total** | **25** |
| *(a 26th edit, outside the implementer's register)* | 1 — OBSOLETE_ASSERTION_CORRECTED, reporting defect DEF-026 |

The five weakenings, in descending severity (the sixth entry below is the unregistered 26th edit):

1. **DEF-016 (P1)** — `test_missing_monetisability_data_fails_to_contract_repair` → `test_missing_advisory_monetisability_does_not_create_a_false_veto`. The only test guarding "no capital without hard quote evidence" was inverted, and its fixture supplies no viability state at all. This one is not merely a test weakening: **it documents a live fail-open in the capital-authority owner.**
2. **DEF-025 (P1)** — `test_property_directional_rows_have_target_on_profitable_side`. A universally quantified property test, whose own docstring called it "the property the whole fix exists to restore", was replaced by a single-row example. A CALL target below its strike would now pass.
3. **DEF-021 (P2)** — `test_composite_repair_is_hydrated_but_not_promoted_to_production`. `economics_comparable` inverted `False` → `True` for an unsupported multi-leg structure. No capital leaks (BLOCK / RESEARCH_ONLY preserved), but a data-integrity assertion was inverted rather than the code corrected.
4. **DEF-023 (P2)** — `test_lab_reload_detects_fresh_options_intelligence_output…`. The observed field was moved into the governed book that the fixture also rewrites, so the test no longer proves what its own failure message claims.
5. **DEF-024 (P2)** — `test_lab_reload_detects_fresh_morning_validator_output…`. `assert morning_lab_alignment_status == "ALIGNED"` deleted, when the sibling fixture in the same reconciliation shows exactly how to preserve it.
6. **DEF-026 (P2)** — *not one of the 25.* A 26th protective assertion (`test_not_monetisable_contract_can_never_go`) was inverted during Phase 2. The inversion is correct under the approved AR-003 §7.10 contract, so I classify the edit itself as OBSOLETE_ASSERTION_CORRECTED; the defect is that it appears in neither the Phase 2 verification section nor the Phase 8 reconciliation register.

**Adversarial re-admission tests** (the prompt's specific ask) — I reintroduced the retired behaviour for both named groups:

- *Monetisability:* a `NOT_MONETISABLE` row with a viable quote correctly reaches BUY_NOW through the approved authority (CALL/PUT), while `OTHER` is refused by direction governance. All six viability-failure states block. **But a row with no viability state at all reaches BUY_NOW — the retired protection was removed and not replaced.**
- *Options research:* a 40%-of-mid spread and a missing bid/ask now route `OPTIONS_GO` in research, exactly as the reconciled tests assert — and in both cases `evaluate_execution_viability` returns `BLOCKED_WIDE_SPREAD` / `DATA_MISSING` and the Execution Gate refuses BUY_NOW for CALL and PUT. **The approved authority does hold here.** I also confirmed these five conversions **pre-date this build** (byte-identical in the Phase 0 baseline), so those five test edits are genuinely obsolete-assertion corrections, not weakenings.

One thing worth saying plainly in the implementer's favour: **no test file was renamed, moved, deleted or newly skipped, and no test function was added or removed.** Skip markers: 5 before, 5 after, all pre-existing and all conditional. The reconciliation was done in the open.

---

## 5. Claims I could not verify, and what would let me

| Claim | What is missing | What would close it |
|---|---|---|
| Phase 4 combined pack "190 collected; command exited 0" | no XML or log exists anywhere | re-run with `--junitxml` and hash-bind the result |
| Phase 8 "initial complete top-level production regression: 872/1/43/25" | no artefact for the 897-test run; only the 76-test affected subset was kept | preserve and hash-bind the pre-reconciliation full-regression XML |
| Which tests were the Phase 6 "30 failed" and the Phase 8 "25 failed" | described in prose, never enumerated | a machine-readable failure list per closure |
| Lab fail-closed behaviour (P0-05 / F14) | the only test greps source text | one test that calls `intelligence_lab._load_run` on a run directory with no governed book and asserts `signals == []` |
| AVS-SD-002 §6.1 delayed-entitlement source-session labelling | provider entitlement is out of scope per §15.3 | a live cycle, or a fixture that simulates a delayed entitlement response |
| Run-level effect of F22 (flag-on), F23, F25, F27, F28, F29, F31 | no run since the fixes | one controlled cycle — the single field each needs is in `T6_deferred_run_evidence.md` |
| P0-07 at data level | the latest run predates the fix | a fresh run with `missing_selected_handoff.invalidation_spot == 0` |

---

## 6. Recommendation

**The offline build is sound in its core authority work and is not sound enough to carry into the controlled live cycle as it stands. Three things must be reworked first; the rest can be scheduled.**

The macro-authority work (P0-03) is the best piece of engineering in this release and I could not break it: five independent surfaces are bitwise-invariant to extreme versus absent macro, across CALL, PUT and OTHER. The identity, plan-determinism, append-only-ledger and hash-bound-release-assessor work is likewise genuinely solid — the release guard refuses promotion correctly under every probe I could construct, including forcing every gate to PASS. The reconciliation was performed honestly and in the open.

**Rework before the live cycle:**

1. **DEF-006 (P0) — rebuild the release baseline.** The rollback source for this release does not contain the package the release was written in. Until `orchestrator/`, `market_structure/` and the omitted directories and launchers are captured, there is no safe way back from a live cycle, and P0-01 cannot honestly be called closed. `release_baseline.py` should also reconcile its manifest against the repository so this class of gap cannot recur silently.
2. **DEF-016 (P1) — restore the fail-closed guard in the Execution Gate.** A row reaching the capital-authority owner with no `execution_viability_state` is granted BUY_NOW. On the governed path the field is always populated, so this is latent rather than active — but it is latent in the one component whose entire job is to fail closed, and the test that would have caught it was rewritten to assert the fail-open. Add the `execution_viability_state` analogue of the deleted `MONETISABILITY_STATE_MISSING` guard, and restore the assertion.
3. **DEF-019 + DEF-008 (P1) — decide what P0-02 means.** The headline defect this release exists to fix is not fixed on the path that will actually run. Either (a) the flag stays off, and P0-02 is re-certified as OPEN with the live cycle measuring the *unfixed* baseline, or (b) `AVSHUNTER_COMPLETED_PROFILE_ENABLED` is folded into the frozen contract and into `_PROMOTION_FLAGS` so the release assessor can govern it. What must not happen is a live cycle run under the belief that P0-02 is closed. **I am not recommending that any flag be enabled.**

**Fix before promotion, not necessarily before the cycle:** DEF-018 (pin the profile authority fields), DEF-020 (make the population identity an equality), DEF-013 (move the provider adapter out of `canonical_data/__init__`'s eager exports — a one-line lazy import), DEF-014/DEF-015 (finish the spread unification and either justify or revert 0.15→0.18), DEF-025 (restore the directional property test), DEF-011 (record the real test interpreter).

**Correct in the documentation before ACK signs anything:** DEF-010 (the "production impact: none" sentence), DEF-021 and DEF-022 (two mislabelled root causes — both are today's changes, not pre-existing drift), DEF-002/003/004/005/012 (unsupported or unartefacted numbers), DEF-001 (hash-bind the reconciliation evidence), DEF-017/028/029/030/031 (design deviations and unimplemented sections recorded nowhere).

A last observation on method rather than code. Five of the fourteen Phase 2 tests — the highest-risk, entirely unflagged phase — prove their claims with `assertIn`/`assertNotIn` on file text rather than by executing anything, and one Phase 7 test named `test_interpreter_resolver_exposes_axes_without_provider_calls` asserts nothing whatever about provider calls. Those tests will keep passing after a refactor that reintroduces the defect. That, more than any single defect above, is what I would change about how this build is verified.
