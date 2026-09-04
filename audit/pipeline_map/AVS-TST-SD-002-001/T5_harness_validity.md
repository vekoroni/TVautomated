# T5 — Regression harness validity

## 5.1 Harness integrity between the Phase 0 baseline and the current tree

| Check | Baseline | Current | Verdict |
|---|---|---|---|
| `tests/test_*.py` files | 116 | 125 | **no file renamed, moved or deleted.** The nine additions are exactly `test_dynamic_session_phase0..8.py` |
| `@pytest.mark.skip` / `pytest.skip(` / `@unittest.skip` / `self.skipTest` / `xfail` occurrences | 5 | 5 | **no skip or xfail marker was added** |
| test functions in the nine edited files | 5+2+3+9+20+7+12+15+11 = 84 | identical, 84 | **no test function was added or removed by the reconciliation** |

The five surviving skip markers are all pre-existing and all conditional or externally justified:

- `tests/msi/test_flow.py:983` — `pytest.skip("NOT_ACTIVATED: MSI_SCREEN_ADAPTER=false …")`
- `tests/msi/test_functionality.py:207` — conditional skip
- `tests/test_cds2_historical_prices.py:336` — `@unittest.skipUnless(os.name == "nt", …)`
- `tests/test_lab_export_mapper_js.py:26` — `@pytest.mark.skipif(shutil.which("node") is None, …)`
- `tests/test_morning_thesis_validator.py:11` — module-level `pytest.skip` (this is the single `skipped=1` in the full-regression XML)

**Nothing was hidden.** This is the cleanest finding in the whole assessment and it deserves to be said plainly: the reconciliation changed assertions and fixtures, but it did not suppress, rename or delete a single test.

One consequence worth recording: because no test function was added or removed, the Phase 8 closure's own arithmetic — 872 passed + 25 failed = 897 non-skipped top-level tests *before*, 877 + 23 = 900 *after* — **cannot be reconciled from any artefact on disk.** No XML exists for the 897-test "initial complete top-level production regression"; only the 76-test affected-file subset was preserved. So the claim that "the initial 25 failures were preserved as historical release evidence" is true only of that subset, and the +3 delta is unexplainable. (My T0 draft inferred that three tests had been added; the function counts above refute that inference, and the residual is simply that the two runs were different selections.) Filed as **DEF-004**.

---

## 5.2 The 33 excluded recursive-MSI failures

`dynamic_phase8_recursive_diagnostic_20260903.xml` — 1,137 `<testcase>` elements, 23 of them carrying 33 `<failure>` nodes, 3 skipped. All 23 failing elements are in `tests/msi/**`. Classification per the prompt's three categories:

### (a) Intentionally asserts absent or obsolete behaviour — 15 failure nodes, 9 elements

| # | Test | Why it is (a) |
|---|---|---|
| 1 | `test_computation.C02::test_quote_change_computation_is_not_implemented_anywhere_NOT_IMPLEMENTED` | a characterisation test asserting a feature's *absence*; the feature is still absent, but the assertion's search string no longer matches the rewritten materializer |
| 3 | `test_flow::test_w01_option_sizes_propagation_chain` | self-describing stale-finding guard ("if this fails, … the W-01 finding below is stale") |
| 5 | `test_flow::test_w07_overlay_and_bundle_quote_change_fields_are_contract_symmetric` | asserts MSI quote-change fields are present in the overlay; they are not |
| 6 | `test_flow::test_w19_request_coalescing_lock_and_budget_config_not_implemented` | self-describing NOT_IMPLEMENTED verdict guard |
| 10 | `test_functionality.F08::test_no_producer_anywhere_writes_the_canonical_field_names` | asserts an empty producer list; the list is no longer empty |
| 11 | `test_functionality.F10::test_evaluate_freshness_has_zero_production_callers` | asserts zero callers; `canonical_data/bundle_freshness.py` and `contracts/quote_change_evidence.py` now call it |
| 21 | `test_regression.R06::test_core_lab_materializer_still_tags_rows_v2_not_v3` | asserts the materializer is *still v2*; Phase 7 made it v3. **This one is squarely obsolete because of today's work and is the clearest case for conversion into an acceptance test rather than exclusion.** |
| 22–32 | `test_regression.R06::test_quote_change_evidence_group_fields_present_in_materializer` (11 subtest failures) | asserts eleven MSI quote-change fields are present in the v3 materializer; they are not. This is an MSI-design requirement, not an AVS-SD-002 one |
| 19 | `test_logic.L07::test_DEFECT_coarse_bars_only_has_no_independent_detection_path` | **asserts that 15-minute bars are silently treated as one-minute bars.** Phase 4 fixed exactly that defect (`market_structure/profile.py:46-66`), so this characterisation test is now provably obsolete and should have been converted, not excluded |

### (b) Sunday / invalid fixture — 6 failure nodes, 6 elements

`test_flow::test_w02_cached_rerun_zero_physical_calls`, `test_flow::test_w20_dropped_ticker_generates_zero_downstream_calls`, `test_functionality.F11::test_chain_registration_is_idempotent_for_identical_content`, `test_functionality.F11::test_resolver_reuses_chain_without_refetch_for_same_scope`, `test_functionality.F12::test_unregistered_ticker_is_blocked_ledger_records_it_no_fetch`, `test_functionality.F12::test_worklisted_ticker_not_in_stage_worklist_table_is_blocked` — all six fail with `ValueError: 2026-08-30 is not an XNYS session`.

**These are not characterisation tests and they are not pre-existing failures.** The exception is raised by `session_bounds()`, which reaches `CanonicalMarketObservationResolver.option_chain` only through `_cutoff()` — added **today**, in Phase 1 (`canonical_data/market_observation_resolver.py`, `+ from .session_clock import session_bounds`, `+ def _cutoff`). Before that change `option_chain` never consulted the exchange calendar and a Sunday fixture ran fine.

The implementer fixed **exactly one** instance of this identical fault — `tests/test_msi_agent1_data_foundation.py`, session `2026-08-30` → `2026-08-28` — inside the 25-test reconciliation, and then classified six more instances of the same fault as "intentionally assert obsolete behaviour" and excluded them. **I dispute that classification.** They are new breakages introduced by this build, in tests whose fixtures were already invalid, and the one-line fix that was applied to the seventh instance applies unchanged to all six.

### (c) Genuine failures the implementer mislabelled — 12 failure nodes, 8 elements

| # | Test | Assessment |
|---|---|---|
| 2 | `test_computation.C05C07::test_c07_one_minute_volume_uniformly_allocated_and_labelled` | `'COARSE_DATA_LOW_CONFIDENCE' != 'ONE_MINUTE_ESTIMATED'`. **Caused by today's Phase 4 cadence fix.** The fixture's bars are spaced 0 / +5 / +31 minutes, so the median delta is ~16 minutes and no map entry matches. The *label* expectation is now obsolete (the old label was a lie), but the fixture is also mislabelled — it claims to test one-minute allocation with 5- and 31-minute spacing. Every other assertion in the test (the hand-computed volume allocation) still holds. **Fixable in one line; excluded instead.** Also note the sole `UNKNOWN_INTERVAL` outcome is `COARSE_DATA_LOW_CONFIDENCE`, which silently conflates "irregular cadence" with "coarse cadence" — worth a design decision |
| 8 | `test_functionality.F04::…_OBSERVED` | `'OBSERVED_POSITIVE' != 'OBSERVED'` — a genuine design-enum divergence in the size-quality vocabulary. Pre-existing; unrelated to this build; still a real unresolved contract mismatch |
| 9 | `test_functionality.F05::…_CROSSED` | `'INVALID' != 'CROSSED'` — a crossed quote is collapsed into `INVALID`, losing the distinction the MSI design requires. Pre-existing; genuine |
| 16, 17, 18, 20 | `test_logic.L01` ×2, `L02`, `L09` | `comparison_status` semantics in `contracts/quote_change_evidence.py`: `BASELINE_MISSING` is returned where `SAME_CONTRACT` / `CONTRACT_CHANGED` is expected, and `change_status` is absent from the bundle. These are **genuine logic findings against a module that exists and is imported by the Interpreter's freshness path.** Pre-existing, unrelated to AVS-SD-002, but they are not "obsolete behaviour" — they are unfixed defects |
| 33 | `test_regression.R07::test_all_named_regression_groups` | reports 2 failures in `tests.test_cds2_historical_prices` — the same two that fail in the pre-build `as_is_validation_results_20260903.xml` ("No usable Python interpreter was found", `test_backfill_direct_script_launch_can_import_canonical_data`). **Those same two tests PASS in `dynamic_phase8_full_regression`.** They are therefore interpreter/PATH-dependent, which is a direct consequence of DEF-011 (the release records an interpreter that cannot run its own tests). Not a code defect; a reproducibility defect |

### Summary

| Category | Failure nodes | Elements |
|---|---|---|
| (a) intentionally asserts absent/obsolete behaviour | 15 | 9 |
| (b) invalid fixture — **new breakage from Phase 1, mislabelled** | 6 | 6 |
| (c) genuine failure, mislabelled as characterisation | 12 | 8 |
| **Total** | **33** | **23** |

**The blanket justification "its failures intentionally assert old/missing functionality" is accurate for only 9 of the 23 failing elements.** Six are today's regressions against invalid fixtures that the reconciliation already knew how to fix, and eight are real unresolved findings (six of them in `quote_change_evidence` logic, one enum divergence pair, one environment-reproducibility failure). Filed as **DEF-022**.

Separately: the recursive pack's own headline number, "1,113 passed", reconciles to neither 1,111 (passing elements) nor 1,219 (pytest's own counting including subtests) — **DEF-005**.
