# T12 — Regression pack quality

Interpreter: `venv\Scripts\python.exe` (3.13.14) for pytest;
`C:\Python314\python.exe` (3.14.0) for the unittest reconciliation, because
that is the interpreter the implementer used and it has **no pytest**.

---

## T12.1 Full pack run

```
venv\Scripts\python.exe -m pytest -q -p no:cacheprovider ^
  tests\test_doi10_projection_integration.py ^
  tests\test_doi11_production_integration.py ^
  tests\test_doi_phase_quality_assurance.py ^
  tests\test_dynamic_options_contract_family.py ^
  tests\test_dynamic_options_deterministic_valuation.py ^
  tests\test_dynamic_options_domain_persistence.py ^
  tests\test_dynamic_options_lifecycle.py ^
  tests\test_dynamic_options_non_discard_policy.py ^
  tests\test_dynamic_options_observation_bridge.py ^
  tests\test_dynamic_options_outcomes.py ^
  tests\test_dynamic_options_probability.py ^
  tests\test_dynamic_options_ranking.py
```

| Metric | Value |
|---|---|
| Collected | **124** |
| Passed | **124** |
| Failed | 0 |
| Skipped | 0 |
| xfail / xpass | 0 |
| Wall time | 56.56 s |

**The claimed number is 120, and I reproduced exactly what it counts.** See
`03_inventory.md` §T0.3: `unittest` discovery over `test_dynamic_options_*.py`
(104) plus `test_doi*.py` (16) is 120, and the four-test gap is the whole of
`tests/test_dynamic_options_non_discard_policy.py`, whose members are
module-level pytest functions that `unittest` cannot collect
(`Ran 0 tests / NO TESTS RAN`). Raised as **DOI-D03**.

---

## T12.2 Rating every test that asserts a §16 invariant

Ratings: **strong** = would fail if the invariant were broken in production;
**weak** = asserts a fixture constant or tests the mock; **misnamed** = the name
promises more than the assertion delivers.

### Strong

| Test | Invariant | Why strong |
|---|---|---|
| `test_eil_block_is_disclosure_not_veto` | 3, 6 | Calls the real `resolve_lab_tradeability` and asserts `EIL_BLOCKED` is absent from `veto_flags` while present in `advisory_flags`, and `lab_verdict != "BLOCKED"`. Restoring the veto breaks it. |
| `test_eil_verdict_does_not_change_eod_tier_or_score` | 3, 4 | Calls real `classify_tier` and `_monetisation_fit` with EXECUTE vs BLOCKED rows and asserts equality of tier and score. Any EIL term re-entering scoring breaks it. |
| `test_handoff_preserves_go_with_eil_advisory_block` | 3 | Builds a real truth packet; asserts `GO` survives a `BLOCKED` verdict with no errors. |
| `test_ordinary_spread_oi_and_volume_are_never_structural_gates` | 6 | Behavioural on the real generator. |
| `test_missing_values_remain_null_not_economic_zero` | 7 | Behavioural; my own T3.5 fixture independently confirms it. |
| `test_unavailable_chain_persists_data_insufficient_family_without_row_loss` | 6, 13 | Asserts population, not a flag. |
| `test_elapsed_and_target_are_visible_not_terminal_deletions` | 6, 13 | Counts rows across a transition. |
| `test_hysteresis_switch_requires_margin_quality_and_stress` / `test_hysteresis_suppresses_small_improvement` / `test_better_utility_with_worse_stress_is_retained_for_human_review` | 10 | Test **non**-supersession as well as supersession — the half most packs omit. |
| `test_restart_is_idempotent_and_history_is_append_only` | 12 | Behavioural; my `probe_t2b` independently proves the triggers fire. |
| `test_outcome_or_future_features_are_forbidden`, `test_temporally_reversed_edge_is_rejected`, `test_training_example_enforces_point_in_time_order`, `test_feature_adapter_uses_only_assessment_time_evidence` | §13 | Assert on rejection behaviour at the type boundary. |
| `test_partial_probability_coverage_falls_back_for_whole_family`, `test_deterministic_fallback_keeps_every_candidate` | §11.6, DOI-9 | Assert whole-family semantics. |
| `test_call_and_put_breach_recovery_are_symmetric`, `test_call_put_ranking_is_symmetric`, `test_put_path_is_symmetric_and_does_not_change_thesis` | 8 | Both sides exercised. |
| `test_lab_merge_preserves_full_population`, `test_inactive_store_is_explicit_and_population_is_preserved`, `test_final_book_writer_projects_every_row_without_doi_store` | 6, §14 | Count rows. |
| `test_data_defects_and_non_directional_rows_are_retained`, `test_wide_chain_retains_full_taxonomy_but_bounds_production_valuation` | DOI-11 | Assert retention and the bound as a subset. |

### Weak / misnamed — all three tests in `tests/test_doi_phase_quality_assurance.py`

This whole file is source-text grepping dressed as invariant testing. It is the
QT-D01 pattern, and it is the file whose name most promises assurance.

| Test | Rating | The actual assertion |
|---|---|---|
| `test_eil_runner_is_permanently_advisory` | **weak + misnamed** | `assertIn("advisory_only = True", source)` — a *substring* of one function's source text. Reformatting to `advisory_only=True` breaks it without a behaviour change; adding a later `advisory_only = False` in the same function still passes it. It does not test that EIL is advisory; it tests that a string is present. |
| `test_observation_bridge_has_no_provider_or_network_authority` | **weak + misnamed** | Checks **direct** imports of one file only against a six-name list. A provider reached through any intermediate module passes. My `probe_t11_import_graph.py` does the transitive version the name implies, over 29 modules and 26 tokens. |
| `test_domain_contracts_cannot_gain_trading_authority` | **weak + misnamed** | Three `assertIn` calls on literal source strings (`'DOI_DECISION_AUTHORITY = "NONE"'`, etc.). Asserts text presence, not that authority cannot be gained. The real guarantee lives in the SQL `CHECK` constraints, which this test never touches. |

Raised as **DOI-D25** (`TEST`, P2).

### The strongest tests are the ones the acceptance runner cannot see

The four tests I rated most strongly on invariants 3, 4 and 6 —
`test_eil_block_is_disclosure_not_veto`,
`test_eil_verdict_does_not_change_eod_tier_or_score`,
`test_handoff_preserves_go_with_eil_advisory_block`,
`test_policy_assigns_human_only_execution_authority` — are the four that
`unittest` silently skips. The acceptance evidence for the design's central
principle consists of three weak text-grep tests that **did** run, while four
strong behavioural tests **did not**. That inversion is the most important
finding in this track.

---

## T12.3 Were tests edited or weakened during the DOI build?

Nine tracked test files are modified. Attribution by diff:

| File | Diff | Lines added mentioning DOI / `dynamic_options` / `advisory_only` |
|---|---|---|
| `tests/test_dynamic_session_phase6.py` | +81 / −0 | 0 |
| `tests/test_msi_quote_and_size_lineage.py` | +16 / −1 | 0 |
| `tests/test_eod_options_research_handoff.py` | +11 / −6 | 1 |
| `tests/test_msi_handoff_materializer.py` | +10 / −5 | 1 |
| `tests/test_interpreter_macro_advisory_handoff.py` | +9 / −2 | 0 |
| `tests/test_handoff_contract.py` | +8 / −6 | 0 |
| `tests/test_big_bang_phase_6_7.py` | +5 / −4 | 0 |
| `tests/test_msi_interpreter_handoff.py` | +3 / −6 | 0 |
| `tests/test_dynamic_session_phase2.py` | (unmodified) | — |

**No test was weakened for DOI.** Only two files gained a single DOI-related
line each; the rest are MSI, macro and handoff work from the earlier
AVS-FIX-001 branch. Only one file has a net deletion
(`test_msi_interpreter_handoff.py`, +3/−6), and it is MSI, not DOI.

The DOI pack itself is entirely **new, untracked** files, so there is no
baseline to diff it against — which is a consequence of **DOI-D01** (nothing
committed), not of tampering. Comparison against `avs-baseline-20260906` is
vacuous for the same reason: none of these files existed at that tag.

**Result: no evidence of test weakening. `VERIFIED`** for the tracked tests.
Confidence MEDIUM — an untracked pack cannot be diffed, so "the DOI tests were
never weakened" is unfalsifiable until they are committed.

---

## T12.4 Is `tests/msi` still excluded from the matrix?

**Yes, and it is still failing.**

- `tests/msi` collects **237 tests** and is not referenced by either DOI phase
  document. It is not part of the 120-test pack under any selector.
- I ran it and it did **not finish inside a 10-minute timeout**. The partial
  output shows at least **14 failures** and 3 skips across the ~81% of the suite
  that completed before the timeout, consistent with the historic 24-failure
  figure not having been resolved.

So the DOI acceptance number excludes a 237-test suite that is known-failing,
and neither DOI phase document mentions it. Raised as **DOI-D26** (`DOC`, P3) —
the exclusion is pre-existing and not a DOI regression, but a "120 passed"
headline alongside an unmentioned 237-test failing suite overstates coverage.

---

## T12.5 Runtime, and tests that touch the network, the real DB or `data\`

| Suite | Wall time |
|---|---|
| DOI pack (124 tests) | 56.56 s |
| `tests/msi` (237 tests) | > 600 s, did not complete |

**No DOI test touches the network, the live control plane or `data\`.**
Evidence:

- grep of all twelve DOI test files for `data/canonical`, `data\canonical`,
  `BASE_DIR`, `cfg.` returns **nothing**;
- ten of the twelve use `tempfile` and build a throwaway `CanonicalRegistry`
  in a `TemporaryDirectory` (`tests/test_dynamic_options_contract_family.py:46–53`
  is the pattern);
- no DOI test file imports `requests`, `httpx`, `urllib`, `socket`, `polygon`,
  `marketdata`, `fred`, `tastytrade` or `anthropic`;
- the two file-reading tests (`test_doi_phase_quality_assurance.py`) read
  repository **source** text, not data.

Before running the pack I confirmed the above, per hard rule 1. No
`EXEC-BLOCKED` outcome arose in this track.

The three-minute-plus msi suite is the only runtime concern, and it is outside
the DOI pack.
