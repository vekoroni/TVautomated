# MSI v1.1 -- Section 7 run-artefact verification

**Author:** Independent regression-test agent (R-01..R-09 pack), `tests/msi/test_regression.py`
**Date:** 2026-08-30
**Design refs:** SS15 (Observability), SS18 "Production-cycle acceptance", SS20 (Acceptance criteria 1-17), SS26 (run-scoped artefact layout)

## Precondition failure (top-line)

**No MSI-active production run exists anywhere on disk.** This was established in preflight
(`audit/msi/00_preflight.md`, "Latest run directories" and "`run_meta.json` / run-history"
sections) and independently reconfirmed here before writing this file:

- The newest run directory, `data/output/runs/20260830_071747/`, predates the MSI code
  entirely. Its `run_meta.json` is the pre-existing macro-pinning schema
  (`canonical_run_id`, `discovery_run_id`, `macro_source_path`, `macro_freshness_status`)
  and contains **none** of the SS13-required fields (`run_kind`, `run_status`,
  `pipeline_mode`, baseline commit hash, configuration hash, producer versions). Its
  top-level contents (`canonical/`, `catalysts/`, `diagnostics/`, `discovery/`,
  `packages/`, `regime_screener/`, `vanguard/`) show it never reached Options
  Intelligence, Morning Gate, Market Structure, Lab or Interpreter stages -- the run's
  macro pin (`06:17` UTC) predates every MSI source file's mtime (13:xx-14:xx on
  2026-08-30, per the pre-change backup manifest).
- No directory under `data/output/runs/` or `data/archive/` contains the SS26-specified
  run-scoped artefact layout: `market_structure/`, `intelligence_lab/`,
  `interpreter/bundles/`, `interpreter/assessments.jsonl`,
  `interpreter/handoff_manifest.json`, `screens/`, `diagnostics/msi_reconciliation.json`.
- The implementation record itself confirms this
  (`audit/msi_implementation/MSI_IMPLEMENTATION_RECORD_20260830.md`, "Current release
  state"): "the implementation is **not yet production-cycle accepted** because the
  required evening -> Morning Gate -> Lab -> Interpreter cycle has not been completed
  ... No evening or Morning pipeline was executed as part of this offline implementation."

Per the task's explicit instruction, this section is **not** performed as a positive
run-artefact test. Every check below that requires a live MSI-active run is marked
**BLOCKED -- no MSI-active run exists**. Checks that are testable independently of a
live run are performed and cross-referenced to the covering test ID instead of being
left simply BLOCKED.

## Required checks (SS15 / SS18 "Production-cycle acceptance" / SS20)

| Check | Design ref | Verdict | Notes |
|---|---|---|---|
| Run summary metrics (requested datasets, cache hits, physical calls, worklist drops, provider failures, size coverage, quote-age distribution, contract-change/recompute count, bar completeness, structure states/quality classes, Interpreter bundle freshness/mismatch counts, Lab missing-field/provenance coverage, idempotent-reuse/conflict counts) | SS15 | **BLOCKED** -- no MSI-active run exists to summarise | No run directory contains a run summary written under the MSI switches. Code that *would* write these metrics exists in `intelligent_orchestrator.py`/`morning_gate.py` per the implementation record's claim but has never executed end-to-end; this is UNVALIDATED by run evidence, not verified. |
| `diagnostics/msi_reconciliation.json` | SS15, SS26 | **BLOCKED** -- file does not exist under any run directory | `tools/msi_reconcile.py` exists (confirmed present, 4,459 bytes, mtime 2026-08-30 13:29) and is invoked from `morning_handoff_finalizer.py` per source read, but no run has produced its output artefact. |
| `interpreter/handoff_manifest.json` SS9.4 required fields (run ID, pipeline mode, session date, run acceptance state; artefact paths/hashes/schema versions; row/ticker counts; stage-completion states; Morning Gate completion timestamp; bundle count/missing-bundle count; reconciliation status/report path; publication timestamp; producer version) | SS9.4, SS26 | **BLOCKED** -- no manifest file exists on disk | The schema/writer (`contracts/interpreter_handoff.py`, `contracts/interpreter_handoff_materializer.py`) exists and is exercised offline by `tests/test_msi_handoff_materializer.py` and `tests/test_msi_interpreter_handoff.py` (independently re-run as part of this pack's R-07 -- both files pass, 4 and 10 tests respectively, 0 failures). That is offline-fixture evidence of the writer's behaviour, not run-artefact evidence of a real manifest. |
| Option-chain / exact-contract bid/ask-size coverage | SS3.2, SS15 | **BLOCKED** for run-artefact coverage numbers | Field-presence/propagation is instead covered offline by `tests/msi/test_regression.py::R03OptionChainV1V2Compatibility` in this pack (PARTIAL -- v2 writer emits `bid_size`/`ask_size` correctly; `first_traded_utc` is not emitted by any writer, a genuine SS8.1 gap; see R-03 test card in the final report). No run exists to report an actual aggregate coverage percentage. |
| Zero registration conflicts | SS15, principle 6 (idempotent registration) | **BLOCKED** for a live count | Structural evidence only: `tests/msi/test_regression.py::R03OptionChainV1V2Compatibility::test_v2_persistence_layer_is_content_addressed_not_rewrite_in_place` confirms (by reading `canonical_data/storage.py`) that the v2 `AtomicPayloadStore` checks for an existing content-addressed target and raises `PayloadConflictError` before any conflicting overwrite, and `canonical_data/registry.py` rejects re-registering a `dataset_id` with different content. This is source+offline-fixture evidence that the conflict-prevention mechanism exists and is exercised by `tests/test_canonical_data_system.py`/`tests/test_cds4_option_chain_store.py` (independently re-run in this pack's R-07 CDS group -- see below), not a live-run "zero conflicts" count. |
| `run_meta.json` SS13 fields (`run_kind`, `run_status`, `pipeline_mode`, baseline commit hash, configuration hash, producer versions, operator acceptance identity/timestamp) | SS13, SS26 | **BLOCKED** -- no run's `run_meta.json` contains this schema | Code-path evidence only: `tests/test_msi_orchestrator_run_meta.py` (independently re-run in this pack, 2/2 passed) exercises the run-meta-v2 writer offline. No executed run demonstrates it in practice. |

## SS20 acceptance criteria 1-17

| # | Criterion | Verdict | Covering evidence |
|---|---|---|---|
| 1 | MarketData option bid/ask sizes reach CDS, Morning Gate, Lab and Interpreter without field loss | **PARTIAL** (offline) | `R03OptionChainV1V2Compatibility` (this pack). Sizes propagate through the v2 writer and parser; `first_traded_utc` is a confirmed gap. No live run to confirm end-to-end field survival through an actual Morning Gate/Lab/Interpreter cycle -- that portion is BLOCKED. |
| 2 | Underlying NBBO fields no longer represented as full Level 2 | **PASS** (offline) | `R05LabUIDisplayRules::test_ui_never_displays_raw_l2_bid_ask_size_labels` (this pack) -- `l2_bid_size`/`l2_ask_size` confirmed absent from `index.html` and the sector UI patch JS. |
| 3 | No direct production MarketData calls originate in Pipeline Interpreter code | **See other test track** | Not directly re-verified by this R-01..R-09 pack (out of its assigned scope). Cross-reference: this is the subject of the Interpreter-provider-isolation checks the task brief describes as covered by the Functionality/Logic/Flow test tracks running alongside this pack (this agent was not given their specific test IDs; the orchestrating report should supply the cross-reference). Partial adjacent evidence: `R02IntradayAdvisoryDoesNotChangeFinalAction::test_final_action_never_independently_computed_by_interpreter_or_cds_layers` (this pack) confirms `pipeline_interpreter/` never independently computes governed `final_action`, which is a related but distinct invariant from "never calls MarketData directly." |
| 4 | A fresh Morning bundle prevents a duplicate Interpreter API call | **BLOCKED** -- no MSI-active run exists | Out of this pack's assigned scope; requires either a live cycle or an offline resolver-level test outside R-01..R-09. |
| 5 | A stale intraday bundle triggers one governed CDS request, not a full-pipeline refetch | **BLOCKED** -- no MSI-active run exists | Same as above. |
| 6 | Dropped tickers trigger zero subsequent provider calls | **BLOCKED** for a live count | Adjacent offline evidence: `tests/test_msi_stage_worklist.py` (independently re-run in this pack, 2/2 passed) exercises worklist enforcement offline. |
| 7 | Contract replacement always refreshes the replacement and recomputes every contract-dependent field | **BLOCKED** -- no MSI-active run exists | Adjacent offline evidence: `tests/test_morning_gate_contract_repair.py` (independently re-run in this pack's `tc07_tc08_and_repair_selector_observability` group, 0 failures). |
| 8 | Structure evidence is deterministic, versioned, quality-labelled and non-authoritative | **PASS** (offline) | `R01DirectionRelationshipByteEquivalence` and `R08MaturationScoreAndVanguardNonActivation` (this pack). `calculate_market_structure_evidence()` is a pure function (no I/O, no randomness); returns `ms_algorithm_version`/`ms_parameter_set_version`/`ms_quality_class`; explicitly sets `ms_authority: "ADVISORY_ONLY"`, `ms_can_grant_capital: False`, `ms_can_reverse_direction: False`; and is invoked strictly after the Morning Gate `verdict` decision (morning_gate.py:2957-2988), never influencing it. |
| 9 | Lab and Interpreter match on run, thesis, direction, contract, quote snapshot and lifecycle for every ticker | **BLOCKED** for a live cross-check | Adjacent/partial: `R06LabSignalBookV3Schema` (this pack) shows the Lab's own live book (`contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py`) still tags rows `lab_signal_book_v2` while a *separate* `lab_signal_book_v3` artefact is produced only by `contracts/interpreter_handoff_materializer.py` for the handoff -- i.e. there are two differently-versioned "books," which is relevant context for this criterion but not a live match/mismatch count. |
| 10 | Interpreter quote changes use two registered snapshots of the same exact OCC contract and match the Lab overlay | **BLOCKED** -- no MSI-active run exists | Out of this pack's scope; offline schema-level coverage exists in `tests/test_msi_interpreter_handoff.py` (independently re-run, 10/10 passed). |
| 11 | Level-2/NOII/tape screenshots are identity-bound, timestamped, hashed and human-confirmed; do not overwrite calculated outcomes | **NOT_ACTIVATED** | `MSI_SCREEN_ADAPTER` is `false` in `config/msi_runtime.json` (confirmed in preflight and unchanged). Per design SS19 ("MSI-7b may activate later and does not block structured Interpreter production"), this is expected and not a defect. Any test exercising this lane must be marked NOT_ACTIVATED, not tested as if live -- consistent with the preflight's own gating note. |
| 12 | All existing authority, OLM, Morning, Lab and CDS regression suites pass | **FAIL** | `R07ExistingRegressionSuites` (this pack). Independently re-executed 10 named suite groups (including all 8 `test_msi_*.py` files) via real pytest subprocesses under `.codex_python313_runtime/python.exe`. 6 of 10 groups are clean; 4 groups contain genuine new failures not accounted for by the implementer's claimed baseline: `cds_cache_registry_request_ledger` (1 failure, environment/subprocess-interpreter issue, see final report), `lab_materialisation_and_field_lineage` (1 failure -- the same golden-fixture drift the implementer's own record flags, independently reproduced), `pipeline_interpreter_handoff_guard` (2 failures, `test_pipeline_interpreter_trusted_source.py`), `latest_accepted_eod_and_morning_fixtures` (2 failures, `test_morning_handoff_finalizer.py`, `MATERIALIZER_MISSING_IDENTITY` errors). Full detail in the final report's R-07 test card. |
| 13 | A complete evening-to-morning-to-Interpreter production cycle passes reconciliation | **BLOCKED** -- no MSI-active run exists | Precondition failure (see top of this file). |
| 14 | The Interpreter consumes only an atomically published, hash-verified handoff manifest | **BLOCKED** for live confirmation | Offline schema/writer evidence only: `tests/test_msi_handoff_materializer.py` (4/4 passed), `tests/test_msi_interpreter_handoff.py` (10/10 passed), both independently re-run in this pack. |
| 15 | Macro state cannot change direction, selected contract, lifecycle, `final_action` or capital permission | **See other test track** | Out of this pack's assigned scope (macro non-authority is not one of R-01..R-09). Adjacent evidence: `R02`'s AST/regex scan of `pipeline_interpreter/` and `canonical_data/` for independent `final_action` computation (this pack) found none, which is consistent with but not a direct test of macro non-authority specifically. |
| 16 | Test, replay, repair and aborted runs are excluded from production trajectory analysis | **See other test track** | Out of this pack's assigned scope (SS13 run-kind exclusion is not one of R-01..R-09). |
| 17 | No production component invents a missing thesis or contract identity | **PASS** (offline, exhaustive) | `R09IdentityMintingRules` (this pack). Exhaustive AST scan of every active `.py` file under `canonical_data/`, `contracts/`, `market_structure/`, `pipeline_interpreter/`, `intelligence-lab/`, `morning_gate.py` and `morning_handoff_finalizer.py` found zero `uuid4()` call sites assigned to `thesis_id`, `trade_idea_id`, `selected_structure_id`, `selected_quote_snapshot_id` or `dataset_id`. Only `bundle_id` (deterministic `uuid5` content-hash mint, `contracts/interpreter_handoff_materializer.py`) and `interpreter_assessment_id` (`uuid4`, `pipeline_interpreter/assessment_contract.py`) are freshly minted, matching SS23 exactly. |

## Summary

Section 7 is **precondition-failed in its entirety** for any check requiring a live
MSI-active run (criteria 4, 5, 7, 9 [live cross-check portion], 10, 13, 14 [live portion]
and every SS15 run-summary metric). Of the checks answerable offline from source and
existing/new test execution, this pack independently confirms:

- **PASS:** criterion 2 (NBBO not shown as L2), criterion 8 (structure evidence
  deterministic/versioned/non-authoritative), criterion 17 (no invented identities).
- **PARTIAL:** criterion 1 (sizes propagate; `first_traded_utc` gap).
- **FAIL:** criterion 12 (existing regression suites) -- 4 of 10 independently-run
  suite groups have genuine new failures; see the R-07 test card in the final report
  for the complete pass/fail table and per-failure detail.
- **NOT_ACTIVATED:** criterion 11 (screenshot lane; `MSI_SCREEN_ADAPTER` is off by
  design, not a defect).
- **Out of this pack's scope, cross-referenced rather than left silently blank:**
  criteria 3, 15, 16 (Interpreter provider isolation, macro non-authority, run-kind
  trajectory exclusion) -- these belong to other parallel test tracks in this
  engagement; this agent does not have their specific test IDs to cite precisely and
  flags that gap here rather than guessing at it.

No production run was executed by this agent (per the rules of engagement, live
evening/Morning Gate runs are out of scope for this pack). This file should be
re-generated once a genuine MSI-active run exists under `data/output/runs/`.
