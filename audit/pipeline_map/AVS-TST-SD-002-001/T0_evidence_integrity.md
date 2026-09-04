# AVS-TST-SD-002-001 — T0 Evidence Integrity and Production-Safety Preflight

Tester: independent (read-only). Date: 2026-09-03.
Output root: `audit/pipeline_map/AVS-TST-SD-002-001/`.
Nothing under `backups/` was modified. No pipeline entry point was executed.

---

## T0.1 — Artefact hashes vs `PHASE8_EVIDENCE.json` / `PHASE8_ASSESSMENT.json`

Every artefact that either document binds by SHA-256 was recomputed independently.

| Artefact | Claimed sha256 | Recomputed | Result |
|---|---|---|---|
| `audit/pipeline_map/dynamic_phase8_results_20260903.xml` | `1bf91e6f…4251` | `1bf91e6f6a508692515805093873b3a3330ba95f21030e9fcbe360d42114a251` | **MATCH** |
| `audit/pipeline_map/dynamic_phase8_full_regression_20260903.xml` | `b48960ed…9328` | `b48960ed992c41f570976c5833fd4ae58f5dc031296189af8174555b97e9e328` | **MATCH** |
| `audit/pipeline_map/dynamic_phase8_qa_rca_regression_20260903.xml` | `d9559762…72da` | `d955976215772ef4f9149a7108187c71ca8ae33b2f85ade69a9bfa9bbd3b72da` | **MATCH** |
| `backups/avs_sd_002_rev1_1_phase0_prechange_20260903_133546/restore_verification.json` | `f726abb2…8f6c` | `f726abb29a14b823b542afac4b96ae8229a30dccbd1d0513bab71a591d278f6c` | **MATCH** |

**Status: VERIFIED.** No artefact was rewritten after assessment. `PHASE8_ASSESSMENT.json` records `invalid_artifacts: []` and that is correct.

Recomputed hashes for the artefacts the register does **not** bind (recorded here so they are bindable in future):

| Artefact | sha256 |
|---|---|
| `dynamic_phase8_open_regressions_20260903.xml` | `96f4f91cedec7d594f16ecc09fe2d7d4b69bc6d73a9a98d2deb321f1b6e8c3d0` |
| `dynamic_phase8_reconciled_regressions_20260903.xml` | `d075f2cf0e6050e70723b05af67a48c09a8b4e90ae4f3349f5793366dca2eb34` |
| `dynamic_phase8_recursive_diagnostic_20260903.xml` | `6b590c7f9d6d703dc6cbecbf51a87ee7c217511d2d0c4773bf790f51219682e5` |
| `design_validation_results.xml` | `c1586d4f520060c27c2b526b6625ccfedbf9e6ec07b33beda5b9bd39ebae8e5b` |
| `as_is_validation_results_20260903.xml` | `0e2dd5341296256a63b0ea98e9af3766b45a3669815c2291df964e9c7d5462e7` |

> **DEF-001 (P2).** The 25-test reconciliation — the single most consequential judgement in Phase 8 — rests entirely on `dynamic_phase8_open_regressions_20260903.xml` and `dynamic_phase8_reconciled_regressions_20260903.xml`, and **neither file is hash-bound anywhere**. `orchestrator/dynamic_release.py` cannot detect their alteration because no gate references them. G17's artefact list names only the full-regression and QA/RCA XMLs.

---

## T0.2 — XML-to-claim reconciliation

Raw parse of every JUnit XML in `audit/pipeline_map/` (suite attributes vs `<testcase>` element counts):

| File | `tests=` | `failures=` | `skipped=` | `<testcase>` elements | elements carrying `<failure>` | subtest delta (`tests` − elements) |
|---|---|---|---|---|---|---|
| `dynamic_phase8_results` | 168 | 0 | 0 | 165 | 0 | 3 |
| `dynamic_phase8_full_regression` | 900 | 0 | 1 | 878 | 0 | 22 |
| `dynamic_phase8_qa_rca_regression` | 44 | 0 | 0 | 23 | 0 | 21 |
| `dynamic_phase8_open_regressions` | 76 | 25 | 0 | 76 | 25 | 0 |
| `dynamic_phase8_reconciled_regressions` | 76 | 0 | 0 | 76 | 0 | 0 |
| `dynamic_phase8_recursive_diagnostic` | 1255 | 33 | 3 | 1137 | 23 (33 `<failure>` nodes) | 118 |
| `design_validation_results` | 61 | 0 | 0 | 61 | 0 | 0 |
| `as_is_validation_results` | 241 | 2 | 0 | 241 | 2 | 0 |

### (a) Integrated pack — claim "165 passed, 3 subtests passed, 0 failed"

165 `<testcase>` elements, suite `tests=168`, `failures=0`. 168 = 165 + 3 subtests; no subtest failed. **RECONCILES EXACTLY — VERIFIED.**

### (b) G17 acceptance matrix — claim "900 passed, 1 skipped, 43 subtests passed, 0 failed (877 top-level plus 23 active QA/RCA)"

The test prompt flagged this arithmetic as apparently unsupportable. **It is in fact exact, and I disagree with the suspicion:**

- full-regression: 878 elements, of which 1 skipped ⇒ **877 passed top-level**; `tests=900` − 878 = **22 subtests**.
- QA/RCA: 23 elements, 0 skipped ⇒ **23 passed top-level**; `tests=44` − 23 = **21 subtests**.
- 877 + 23 = **900 passed top-level**; 1 skipped; 22 + 21 = **43 subtests**; 0 failed.

I confirmed the two files are **disjoint**: the intersection of `(classname, name)` between the 878 and the 23 is **zero**. The QA/RCA pack is `tests/qa/*` and `tests/rca/*` only; the full-regression pack contains none of them. The 165-test integrated pack is a **strict subset** of the 878 (165/165 matched).

What *is* misleading, and should be corrected in the evidence register: the number **900 appears twice for two different quantities** — it is simultaneously the full-regression file's own `tests` attribute (878 elements + 22 subtests) and the combined top-level pass count (877 + 23). That collision is coincidence, and a reader checking G17 against the single XML named in its artefact list will "confirm" the wrong 900. Recommend the detail be restated as "877 passed + 1 skipped + 22 subtests (full regression) and 23 passed + 21 subtests (QA/RCA)".

**Status: VERIFIED (arithmetic), with a reporting-clarity defect DEF-002 (P2).**

### (c) Phase 4 — claim "190 collected; command exited 0"

No XML or log for that run exists anywhere under `audit/pipeline_map/`. `PHASE4_CLAIM.json` records `{"collected": 190, "command_exit": 0}` — a collection count and an exit code, **not a pass count**. There is no artefact on disk from which a pass/fail decomposition can be recovered.

**Status: DEF-003 (P2) — the Phase 4 combined pack is SOURCE_ONLY.** I independently re-ran `tests/test_dynamic_session_phase4.py` in isolation: **10 passed / 0 failed** (`T1_xml/T1_phase4.xml`), which reproduces the *focused* claim only.

### (d) Phase 5 — "58 passed / 0 failed" vs two red `test_morning_gate_contract_repair.py` tests

`tests/test_morning_gate_contract_repair.py` is **outside** the 58. The Phase 5 compatibility pack is recorded as 58 passed / 1 skipped / 3 subtests; the two named tests (`test_blank_primary_contract_promotes_live_repair_alternative`, `test_composite_repair_is_hydrated_but_not_promoted_to_production`) are listed separately in the same report as still red, and are carried into `PHASE5_CLAIM.json` under `known_preexisting_test_contract_drift`. Both then appear among the 25 failures in `dynamic_phase8_open_regressions_20260903.xml` and among the 76 passes in the reconciled XML. So they were excluded from the 58, disclosed, and later edited.

**Status: reconciles.** I dispute the *label* "pre-existing test-contract drift" — see T2; both tests went red because Phase 2 changed `morning_gate._recompute_selected_contract_economics` from returning `False` on incomplete monetisability to always returning `True`. That is a Phase 2 regression against those tests, not pre-existing drift.

### (e) Phase 6 "284 passed, 30 failed" vs Phase 8 "25 reconciled" — the other 5

The Phase 6 broad pack and the Phase 8 top-level regression are different populations, so the residual is not a straight subtraction. Accounting for the difference:

- Phase 8's own baseline was **"872 passed, 1 skipped, 43 subtests, 25 failed"**, i.e. 897 non-skipped top-level tests.
- The reconciled current state is **900 non-skipped top-level tests** (877 + 23).
- **The population grew by 3 top-level tests during reconciliation** — the edits did not only change assertions, they added cases (see T2).
- The 5 Phase 6 failures not in the Phase 8 25 are inside the excluded **recursive MSI characterisation pack** (`dynamic_phase8_recursive_diagnostic`, 23 failing elements / 33 `<failure>` nodes), which Phase 6 ran and Phase 8 did not count. Phase 6's pack was a wider historical/audit selection than Phase 8's top-level production selection.

**Status: partially reconciled.** Neither the Phase 6 nor the Phase 8 report identifies the 30 or the 25 by name in a machine-checkable list, so the mapping is inferred from the XMLs, not asserted by the implementer. Recorded as **DEF-004 (P2) — failure sets are described in prose, never enumerated.**

### (f) Recursive MSI diagnostic — claim "1,113 passed, 3 skipped, 33 failed"

The XML carries `tests=1255`, `failures=33`, `skipped=3`, and **1137 `<testcase>` elements**, of which 23 carry at least one `<failure>` (33 `<failure>` nodes in total, so 10 elements carry more than one). Passing elements = 1137 − 23 − 3 = **1111**. pytest's own counting (subtests separate) gives 1255 − 33 − 3 = **1219**.

**Neither figure is 1,113.** The "1,113 passed" number does not reconcile against the artefact.

**Status: DEF-005 (P2) — CONTRADICTED.** Low severity because the pack is explicitly excluded from acceptance, but the number as printed is not supported by the file it cites.

---

## T0.3 — Git state and rebuildability

```
git rev-parse HEAD      → 5d886f07c1d290f25600e2e7e62ae77aad85476a
git rev-parse --abbrev-ref HEAD → master
git status --porcelain  → 299 entries (Phase 0 recorded 284)
```

HEAD is unchanged and matches `source_head` in every claim sheet. **Not one line of today's work is committed** — the entire Rev 1.1 build exists only as working-tree modifications. P0-01 is therefore closed on a file manifest, not a commit, exactly as the prompt anticipated.

### Could a person rebuild the tested tree from `phase0_release_manifest.json` + `release_file_manifest.json` alone?

**No. Categorically no, and this is the most serious T0 finding.**

`backups/…phase0_prechange_20260903_133546/source_current/` contains 3,116 files, but only these top-level directories:

`canonical_data/`, `contracts/`, `intelligence-lab/`, `pipeline_interpreter/`, `scripts/`, `tests/`, `vanguard/` — plus loose top-level `*.py`.

It **omits entire git-tracked source directories that the release depends on**, most importantly:

- **`orchestrator/`** — 15 files tracked at HEAD (`__init__.py`, `main.py`, `collector.py`, `options_intelligence.py`, `wyckoff_engine.py`, `macro_loader.py`, `report_generator.py`, `email_sender.py`, `claude_api.py`, `data_monitor.py`, `WyckoffEngine_3101_v2.py`, `main_archive.py`, three `.ps1`). This is the package into which Phase 1/4/5/6/7/8 added `dynamic_dispatcher.py`, `dynamic_release.py`, `dynamic_thesis.py`, `dynamic_validation.py` and modified `__init__.py`. **The "authoritative whole-release rollback source" contains no copy of the package the release is built in.**
- **`market_structure/`** — untracked by git and absent from the Phase 0 snapshot, yet `backups/…phase4_prechange…/market_structure/profile.py` proves the package **existed before Phase 4**. There is therefore **no whole-release baseline for it at all**; only a single-file, single-phase copy.
- `bridge/`, `config/`, `docs/`, `ml_confidence_layer/`, `news_terminal/`, `short_swing/`, `src/`, `templates/`, `tools/`, `zero_dte/`, `ma_cockpit/`, `legacy/`, and the production launchers `run_evening.bat` / `run_premarket.bat`.

`scripts/release_baseline.py` cannot detect this: it never enumerates the repository. `finalise()` only re-manifests what a *separate, unrecorded* copy step already put in `source_current`, and `verify_backup()` only re-hashes the files the manifest already lists. Both pass trivially over an incomplete tree.

> **DEF-006 (P0). The Phase 0 release baseline is not a release baseline.** It excludes `orchestrator/` and `market_structure/` — the two packages containing the new dynamic code — plus eleven further source directories and both production launchers. `restore_verification.json` "PASS" is self-referential: it proves the backup is internally consistent, not that it covers the tree. **P0-01 ("reproducible release baseline + verified restore") is CONTRADICTED at the source-tree level.** The database half of it is sound (see below).

### Files changed after Phase 0 with no pre-change copy in any backup

Cross-referencing the 44 changed files against the Phase 0 tree and all seven per-phase backups:

| File | Phase 0 copy | Per-phase copy | Rollback available? |
|---|---|---|---|
| `orchestrator/__init__.py` | **absent** | phase6, phase7 | Yes (phase6 = pre-Phase-6 state) |
| `market_structure/profile.py` | **absent** | phase4 | Yes (phase4 only) |
| `market_structure/service.py` | **absent** | phase5, stored **flat as `service.py`** at the backup root | Ambiguous — the restore path is not recorded |
| `vanguard/layer2_statistical/state_calculator.py` | present | phase4 (and admitted missing from phase2) | Yes |
| `contracts/lab_control.py` | present | none | Yes (Phase 0 only) |
| all other 40 | present | mixed | Yes |

The Phase 2 closure's own admission (`state_calculator.py`, `lab_control.py` edited without a Phase 2 backup) is accurate and correctly mitigated by the Phase 0 snapshot. The `orchestrator/` and `market_structure/` gaps are **not** disclosed anywhere.

> **DEF-007 (P1).** `backups/avs_sd_002_rev1_1_phase5_prechange_20260903_163000/service.py` is stored without its directory, so a restorer cannot tell it is `market_structure/service.py`. Every other per-phase backup preserves relative paths.

### Phantom store

`backup_metadata.json` records `data/phantom/phantom_history.db` at 16,578,891,776 bytes, `copied: false`, `sha256: "DEFERRED_LARGE_EXTERNAL_DEPENDENCY"`, reason "no writer change in current phase". I confirmed no Phantom writer appears in any of the 44 changed files (`scripts/run_phantom.py` and the Phantom DB writers are byte-identical to the Phase 0 baseline). **The exclusion is justified for this release.**

---

## T0.4 — Flag inventory

Full table: `T0_flag_inventory.csv`.

`contracts/dynamic_session_contract.py:104-152` and `contracts/dynamic_session_authority_v1.json:16-25` declare **eight** flags, all defaulting to disabled. `_as_bool()` (`dynamic_session_contract.py:87-95`) returns the `default=False` for `None`, for the empty string, for `"0"/"false"/"no"/"off"`, **and for any unrecognised value** — so a typo cannot enable a flag. Verified by test `test_all_new_features_are_disabled_by_default` and reproduced (`T1_xml/T1_phase0.xml`).

**The eighth flag the closures never name is `AVSHUNTER_DYNAMIC_THESIS_ENABLED`.** (The prompt's list of seven also omits `AVSHUNTER_PROFILE_LIFECYCLE_ENABLED`, so two of the eight are undocumented in the closure prose.)

Every read in the live tree treats unset as disabled. Grep of the whole live tree for `AVSHUNTER_[A-Z_]*ENABLED` found **no read with a truthy default** among the dynamic flags. (`AVSHUNTER_EV3_SHADOW_ENABLED` at `intelligent_orchestrator.py:456` and `AVSHUNTER_CANONICAL_DATA_ENABLED` do default on, but both pre-date this release and are unchanged from the Phase 0 baseline.) **No P0 here.**

> **DEF-008 (P1). There is a ninth dynamic flag, and it is outside the frozen contract.**
> `AVSHUNTER_COMPLETED_PROFILE_ENABLED` (`intelligent_orchestrator.py:436-438`) gates the entire Phase 4 completed-profile stage — that is, the fix for **P0-02**, the headline defect. It is:
> - absent from `FEATURE_FLAG_ENV_VARS`;
> - absent from `contracts/dynamic_session_authority_v1.json`;
> - absent from **every** stage of `orchestrator/dynamic_release.py:_PROMOTION_FLAGS` (`PLAN_ONLY`, `EXPLICIT_COMMANDS`, `DYNAMIC_VIEWS` and even `AUTO`, which uses `FEATURE_FLAG_ENV_VARS` verbatim).
>
> Consequence: an operator who follows the release assessor's `promotion_environment()` output to the letter, all the way to `AUTO`, **will never enable the Market Profile fix**. Phase 0's claim of "eight independently reversible dynamic feature flags" is true of the contract and false of the build.
>
> Secondary: the flag is read once in a class body at import time, so it cannot be toggled per invocation and is invisible to `DynamicSessionFeatureFlags`.

---

## T0.5 — Legacy-path diff (Phase 0 baseline → current tree)

Method: byte-compare every `.py/.js/.html/.json/.css` file in `source_current` against the live tree. Result: **44 changed, 0 deleted, 2,972 identical**. Four of the 44 are `pipeline_interpreter/automation_v2_shadow_outputs/**` runtime trial metrics (excluded from the release manifest by design) and nine are test files (T2). That leaves **31 changed production modules**, one unified diff each in `T0_legacy_path_diff/`.

Hunk classification. **(a)** = reachable only behind a disabled flag; **(b)** = reachable on the legacy `--evening`/`--morning` path; **(c)** = unconditional.

| Module | Class | Justified by | Note |
|---|---|---|---|
| `avshunter_discovery_ULTIMATE.py` | **(b)** | Phase 2 / P0-03 / AR-003 §7.2 | tier floors, state priors, sector lift, phase-align regime boost all forced to macro-invariant |
| `regime_threshold_injector.py` | **(b)** | Phase 2 / P0-03 | `apply_regime_to_config` no longer mutates `tier1_min`/`tier2_min`/`tier3_min`/`compression_max`/`min_avg_vol20` |
| `macro_horizon_router.py` | **(b)** | Phase 2 / AR-003 §7.8 | `macro_path` optional; `bias is None → block` removed |
| `scripts/avshunter_options_intelligence.py` | **(b)** | Phase 2 / AR-003 §7.7 | R:R scoring zeroed; `derive_verdict` R:R demotion removed; single spread denominator |
| `eod_candidate_engine.py` | **(b)** | Phase 2 / AR-003 §8 | `MIN_RR` removed from tier A/B, quality floor, gap reporting and `_true_fatal_block`; `evaluate_execution_viability` added |
| `execution_gate.py` | **(b)** | Phase 2 / AR-003 §7.10 | monetisability authority replaced by execution viability; `SPREAD_MAX` now derived from `long_option_policy` |
| `contracts/long_option_policy.py` | **(b)** | Phase 2 / P1-05, P1-06 | +216 lines: `quote_spread_fraction`, `quote_age_seconds`, `evaluate_execution_viability` |
| `contracts/selected_contract_economics.py` | **(b)** | Phase 2 / AR-003 §7.10 | monetisability relabelled `ADVISORY_SCENARIO_ONLY`, `EXPIRY_INTRINSIC_FLOOR` |
| `morning_gate.py` | **(b)** | Phase 2 + Phase 5 | viability recompute, real quote age, frozen-thesis guard, MarketData 5-min structure provider, `ms_*` into result rows |
| `contracts/lab_control.py` | **(b)** | Phase 2 | ten `execution_viability_*` + three `monetisability_*` fields added to the governed projection |
| `intelligence-lab/intelligence_lab.py` | **(b)** | Phase 2 / P0-05 | legacy assembly now returns `signals: []` and `GOVERNED_BOOK_UNAVAILABLE_FAIL_CLOSED` |
| `vanguard/layer2_statistical/state_calculator.py` | **(b)** | Phase 2 / AR-003 §7.5 | `_calculate_macro_regime` hard-wired to `TRANSITIONAL` / p50 |
| `vanguard/trade_governance.py` | **(b)** | Phase 2 | Q2 macro flip demoted HARD → ADVISORY |
| `scripts/run_vanguard_from_packages.py` | **(b)** | Phase 2 + Phase 4 | neutral macro payload to the engine; **also removes the ACCUMULATION×RISK_OFF tier-demotion exemption** |
| `pipeline_interpreter/evidence_resolver.py` | **(b)** | Phase 2 + Phase 7 | `frozen_thesis`/`current_validation` axes; `BOOK_BUNDLE_IDENTITY_MISMATCH` on `validation_event_id` |
| `canonical_data/registry.py` | **(c)** | Phase 1 | `SCHEMA_VERSION` v1→v2; **five `ALTER TABLE` columns added to the live `api_request_ledger` on first `initialise()`** |
| `canonical_data/request_ledger.py` | **(c)** | Phase 1 | insert widened to 14 columns |
| `canonical_data/market_observation_resolver.py`, `option_chain_store.py`, `contracts.py`, `__init__.py` | **(c)**, additive | Phase 1/3/7 | new keyword args default to prior behaviour |
| `canonical_data/intraday_bars.py` | **(c)**, additive | Phase 3 | 1-minute resolver and `normalise_minute_bars` preserved |
| `vanguard/schemas/auction_schema.py` | **(c)** | Phase 4 | `poc`/`value_area_high`/`value_area_low` widened to `Optional[float]` |
| `vanguard/schemas/input_schema.py`, `vanguard/integration/orchestrator_adapter.py` | **(c)**, additive | Phase 4 | two new fields, `market_profile_contract_required` defaults `False` |
| `vanguard/layer1_auction/auction_synthesizer.py` | **(a)** | Phase 4 | governed branch entered only when `market_profile_contract_required` is set, which only `build_completed_market_profiles.py` sets, which only runs when `AVSHUNTER_COMPLETED_PROFILE_ENABLED=1` |
| `intelligent_orchestrator.py` | **(a)** + **(c)** | Phase 4/6 | profile stage and dispatcher branch are flag/CLI gated; `cds_runtime` initialisation restructure is **(c)** |
| `morning_handoff_finalizer.py` | **(a)** | Phase 7 | all new work behind `lab_dynamic_view` / `decision_outcome_ledger` |
| `contracts/interpreter_handoff.py`, `interpreter_handoff_materializer.py` | **(a)**/(c) | Phase 7 | `require_validation_lineage` defaults `False`; new axes only populated when supplied |
| `intelligence-lab/static/index.html` | **(c)** | Phase 7 | 23 lines of frozen/current dossier markup rendered **unconditionally**, not behind `lab_dynamic_view` |

### Unjustified or under-disclosed (b)/(c) hunks

1. **`canonical_data/registry.py` — live control-plane schema migration, unflagged, undisclosed.** I confirmed the production database is still at v1 (`schema_metadata` = `cds_control_plane_v1`; `api_request_ledger` has 14 columns, 16,870 rows — identical to the Phase 0 snapshot, so no run has occurred). The **next** `--evening` or `--morning` will execute five `ALTER TABLE ADD COLUMN` statements plus two `UPDATE` statements against `data/canonical/control_plane.sqlite`. It is additive and reversible only via the Phase 0 database snapshot. No closure states that the first legacy run after this build mutates the production control plane. **DEF-009 (P1).**
2. **`scripts/run_vanguard_from_packages.py:724-745` — removal of the ACCUMULATION × RISK_OFF tier-demotion exemption.** Defensible as macro-invariance, but its effect is a *strictly larger* set of Tier 1→2 demotions on the legacy path. Not mentioned in the Phase 2 or Phase 4 closure.
3. **`eod_candidate_engine.py:669-673` — `_true_fatal_block` no longer requires `rr >= MIN_RR`.** This widens the set of rows that escape a fatal block. Consistent with "R:R has no authority", but it is a *population* change, not only a *tier* change, and the closure describes only tier authority.
4. **`intelligence-lab/static/index.html:2282-2305`** renders the frozen/current lifecycle panel on **every** dossier, including a legacy Morning run where `validation_event_id` and every `s.validation_*` key are absent. The panel then displays "NOT RUN" / "—" / "NOT EVALUATED". Cosmetically safe, but it is a UI change on the current production surface that the Phase 7 closure describes as gated.
5. **`morning_gate.py:1963-1969` — `quote_age_seconds()` may now return `None`** where the field was previously the literal `0.0`. Correct per P1-06, but the value flows into `LifecycleInputs(...)`; a `None` there is a new input state for `evaluate_options_liquidity_lifecycle`, exercised nowhere in the phase suites with a *missing* provider timestamp.
6. **`morning_gate.py:3766-3786` — `_recompute_selected_contract_economics` now always returns `True`** and sets `economics_recompute_required = "FALSE"` even when monetisability is incomplete. This is the change that turned the two `test_morning_gate_contract_repair.py` tests red. It is a real Phase 2 behaviour change on the legacy `--morning` path, disclosed nowhere; the Phase 5 closure instead labels the resulting failures "prior test-contract drift". **I dispute that classification** — see T2.

### `production_behavior_changed`

Only `PHASE0_CLAIM.json` carries `"production_behavior_changed": false`, and for Phase 0 that is **true** (its diff is confined to two new contract files and `scripts/release_baseline.py`). No later claim sheet repeats the field. Phases 2–7 instead assert `production_dispatch_enabled: false`, `production_flags_enabled: false`, `production_authority_changed: false` (Phase 3) or `production_outputs_promoted: false` — all of which are accurate and none of which claims behavioural equivalence.

**However, the Phase 8 closure does make the stronger claim**, in "Production impact": *"None. The legacy `--evening` and `--morning` paths remain unchanged."* **That sentence is false.** Fifteen production modules on the legacy path changed unconditionally, by design, under Phase 2 and Phase 5 — Discovery tiering, Vanguard L2 regime, horizon routing, Options verdict, EOD tier and membership, Execution Gate authority, Morning viability and quote age, Lab fail-closed, the Morning market-structure provider, and the control-plane schema. Every one of them is individually sanctioned by AVS-AR-003, but "production impact: none" is not a defensible summary. **DEF-010 (P1) — reporting.**

---

## T0.6 — Restore drill (independent)

Performed into `audit/pipeline_map/AVS-TST-SD-002-001/tmp/restore_drill/`. `backups/` was read only.

| Database | Manifest sha256 | Recomputed after restore | `PRAGMA integrity_check` | Table counts vs manifest |
|---|---|---|---|---|
| `data__canonical__control_plane.sqlite` (56,602,624 B) | `a2d7a212…d302` | identical | `ok` | identical (9 tables) |
| `data__canonical__historical_prices.sqlite` (961,404,928 B) | `8de84438…e9f0` | identical | `ok` | identical (4 tables) |
| `data__journal__trade_journal.db` (1,581,056 B) | `a561dee8…6bee` | identical | `ok` | identical (3 tables) |

**G20 / F01 database half: VERIFIED independently.** Raw results in `tmp/independent_restore_drill.json`.

Two qualifications on the *evidence value* of the implementer's own drill:

- `verify_backup()` (`scripts/release_baseline.py:157-207`) restores by `shutil.copy2` into a temp directory **created inside the backup directory itself** and then re-hashes. It proves that copying a file preserves its bytes. It does not restore to a production-shaped path, does not exercise the SQLite backup API on the restore leg, and never compares the backup against the live repository.
- `"isolated_restore_removed_after_verification": true` (`:206`) is a **hard-coded literal**, not an observation of the cleanup.

Both are why the source-tree gap in DEF-006 passed unnoticed.

---

## T0.7 — Test-runtime discrepancy

`backups/…phase0…/environment.json` records `python_executable: C:\Python314\python.exe`, `3.14.0`, and a 57-package dependency list that contains **neither `pytest` nor `pytest-subtests`**. I confirmed `C:\Python314\python.exe -m pytest` fails with `No module named pytest`.

Every acceptance XML is pytest output. The only pytest in the repository is `venv/Scripts/python.exe` — **Python 3.13.14, pytest 9.1.1, pandas 2.3.3, no `pytest-subtests`** (the "subtests" in the XMLs are `unittest.TestCase.subTest` calls, which pytest 9 reports natively).

So the environment record captured in the release baseline is **not the environment that produced the evidence**, and the Phase 0 closure’s `C:\Python314\python.exe -m unittest` command applies only to Phase 0's own eight tests.

> **DEF-011 (P1).** The release's environment evidence describes an interpreter that cannot run the release's test suites. Nothing in the baseline records the venv interpreter, its Python version, or its pytest version, so the acceptance runs are not reproducible from the recorded environment.

I ran every suite under `venv/Scripts/python.exe` (recorded in `environment.json`) and reproduced all nine phase suites exactly — see T1.

---

## T0 verdict

| Preflight check | Status |
|---|---|
| Hash-bound artefacts unaltered | **VERIFIED** |
| Integrated 165/3-subtest claim | **VERIFIED** |
| G17 900/1/43/0 arithmetic | **VERIFIED** (with DEF-002 clarity defect) |
| Phase 4 combined pack | **SOURCE_ONLY** (DEF-003) |
| Phase 5 58-test decomposition | reconciles; classification disputed |
| Phase 6 30 vs Phase 8 25 | partially reconciled (DEF-004) |
| Recursive diagnostic 1,113 | **CONTRADICTED** (DEF-005) |
| Eight flags, all default off | **VERIFIED** |
| Ninth undeclared flag | **CONTRADICTED** (DEF-008, P1) |
| Reproducible release baseline (source tree) | **CONTRADICTED** (DEF-006, P0) |
| Reproducible release baseline (databases) | **VERIFIED** |
| "Legacy paths unchanged" | **CONTRADICTED** (DEF-010, P1) |

T1 may proceed: the evidence files are what the claim sheets say they are.
