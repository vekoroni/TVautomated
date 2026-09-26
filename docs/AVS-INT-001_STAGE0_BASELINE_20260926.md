# AVS-INT-001 — Stage 0 baseline and red-test receipt

**Status:** S0 in progress; not a release or completed implementation

**Date:** 26 September 2026

**Scope:** read-only baseline plus new offline tests; no Evening/Morning run, provider call, database write, research deletion or production-logic change.

**Later same-day update:** the initial S0 snapshot below is preserved as
pre-fix evidence. The cumulative-horizon and Lab-convexity repairs, final tests,
and residual acceptance boundary are recorded in
`docs/AVS-INT-001_TRUTH_SLICE_RELEASE_CANDIDATE_20260926.md`; the two expected
failures described below are no longer outstanding.

## Corrections to the prior design review

The initial INT-001 design incorrectly called `domain/exact_contract_quote_join.py` untracked. `git show --stat 8046eec` establishes that it was committed with `pipeline_interpreter/war_view.py` and its tests. The design has been corrected. The **proposed v2** assembler and five `domain/war_*` companions remain local/untracked and are not imported by the live WAR v1 view. This distinction matters: v1 clean-checkout import risk was overstated; v2 release/integration work remains real.

## Reproducible code/release baseline

Read-only command: `C:\Python314\python.exe tools\avs_int001_stage0.py`.

| Observation | Result | Meaning |
|---|---|---|
| Branch HEAD | `e0c4a95` | Contains later 25–26 Sep changes; not one of the 22–23 Sep governed tags. |
| Tag at HEAD | none | Current checkout has no new governed release tag. |
| Tracked modifications | none at inspection | Existing untracked research/user work is preserved. |
| Named live static import closure | 33 local files from WAR v1, macro publication, pretrade focus and Lab control; 0 untracked/absent, 0 syntax errors | A **scoped** static pass, not proof of every runtime/dynamic import or browser route. |
| WAR v2 research components | six listed files local/untracked | Not a production-path dependency; must be selected, governed, wired and acceptance-tested if used. |
| INT-001 design | local/untracked | Not yet a governed release artefact. Commit only at the end of the tested implementation cycle. |

The static scanner is intentionally read-only and makes no provider calls. Its fixture tests prove it detects an untracked local import and handles a relative import; a separate route/browser integration test remains necessary.

## Stored-run truth, not prospective performance

`data/output/runs/20260925_061649/run_meta.json` records `run_condition=TEST`. Its final manifest is `MORNING_VALIDATION`, with 1,549 Morning candidate/validation/execution rows and 175 selected-handoff rows missing `invalidation_spot`. It reports `pipeline_technical_health=PASS`, `pipeline_semantic_health=DEGRADED`, and `run_tradeable_label=EXECUTION_READY`. Those values have different grains; D2 must define and test a label that does not imply every retained row is execution-complete. This TEST run is not a prospective trading-success baseline. The 25 Sep aborted Evening run remains an independent macro-publication regression fixture; its fix is covered by `tests/test_macro_evening_publication_boundary.py` and still needs normal completed-session acceptance when authorised.

### Current frozen Lab field/source snapshot

The older `docs/AVS-ILA-EVENING-MORNING-SOURCE-MAPPING-20260923.md` and its 928-field CSV are a **historical assessment**, not the current state. Read-only inspection of `data/output/runs/20260925_061649/intelligence_lab/final_opportunity_book_20260925_061649.json` and its Morning source found:

| Owner / projection | Present of 1,549 | S0 interpretation |
|---|---:|---|
| Morning validation event JSON files | 1,549 | Source population is complete for this TEST run. |
| Full-book Morning execution mode / validation event ID / transition / cutoff | 1,549 each | The 23 Sep finding that these were absent on all rows is **already repaired**; do not rebuild it. |
| Full-book selected contract symbol | 1,345 | The remaining 204 need typed no-option/no-selection review, not invented contracts. |
| Full-book target / invalidation price | 1,131 / 1,180 | 369 rows lack both; compare source/route before calling any row executable. |
| Full-book `invalidation_spot` alias | 0 | The alias is still absent although 175 selected-handoff rows are counted missing; inspect exact producer/consumer grain. |
| Full-book `convexity_score` / `convexity_score_source` | 1,549 / 0 | Trader-facing score is not source-qualified; do not interpret it as measured convexity. |
| Full-book canonical `expected_move_10d_fraction` / legacy 6–10D field | 0 / 1,549 | Canonical cumulative budget is not projected; the legacy increment still feeds the reviewed path. |
| Full-book `rr_predicted` | 0 | Do not assume the misleading legacy label is visible; scenario-value replacement remains a separate task. |
| Book row and identity reconciliation | 1,549 input/output, 0 duplicate idea IDs | Population preserved. Economics reports 215 mismatch rows out of 1,130 comparable; this is a diagnostic requiring reason-level audit, not an automatic trade failure. |

The Morning CSV has 1,549 rows with mode present; the final book carries the event ID and transition on all rows. `morning_gate_verdict` is absent from the final book, but its absence alone does not prove lost Morning authority because current routes/validation fields are present under other names. This is why the field map must be updated by **semantic owner and consumer**, not by matching stale column names.

## First TDD red case: hold-window expected move

`tests/test_avs_int001_horizon_red.py` supplies otherwise ready 6–10- and 11–20-session theses with a canonical cumulative 10-/20-session budget and smaller legacy incremental bands. Before any production edit, both tests failed: `domain/pretrade_focus.py` read only `garch_expected_move_6_10d` or `_11_20d`, falsely adding `TARGET_BEYOND_EXPECTED_MOVE_REVIEW_BAND`. This is a real, narrow calculation/field-meaning defect, not proof that the entire ticker thesis is wrong. The tests are now strict expected failures so the broad suite remains runnable; S2 removes those markers only after a source-correct fix and upstream/Lab parity checks.

Verification command: `C:\Python314\python.exe tools\run_governed_pytest.py -q --basetemp C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\.pytest_int001_suite tests\test_avs_int001_stage0.py tests\test_avs_int001_horizon_red.py tests\test_interpreter_war_view.py tests\test_macro_evening_publication_boundary.py`.

Result at S0 after adding the actual Lab-app route-mount test: **15 passed, 2 strict xfailed**. The 2 xfails are unresolved defects, not passing functionality. The first attempt without `--basetemp` encountered an inaccessible user temp directory (3 passed, 2 fixture setup errors); the governed writable test directory resolved that environment error without changing the test logic. Importing the Lab module registered both saved WAR routes without starting the Flask server or contacting a provider; this proves a local mount, not browser acceptance.

## Research-to-build disposition and remaining S0 gate

The INT-001 design's A1–F3 table is the master trace. For each item, record `accepted rule/fix`, `gated experiment`, or `rejected` before implementation; link exact caller, red/green test, stored-run evidence and final commit. Current high-priority decisions are narrow: cumulative expected-move correction and Lab projection truth are rules/data repairs; WAR v2 is an optional integration, not a second gate; boosted/hazard/Bayesian learners are challengers, not assumed necessary fixes. Research papers are not deleted while their unique sample, negative result, threshold search or provenance still supports the decision.

| Register ID | S0 disposition | First concrete build/test question |
|---|---|---|
| A1 | Accepted data repair | Can target/invalidation lineage be complete or typed missing without inventing either? |
| A2 | Accepted state rule | Does a new valid quote restore expression availability without rewriting the thesis? |
| A3 | Gated capture experiment | Are provider-stamped exact-contract paths and disk growth sufficient for 5/10/20 sessions? |
| B1 | Accepted shadow repair | Does the value selector compute from correct side/ask/bid/IV inputs? |
| B2 | Gated shadow comparison | Does the broader family improve matched prospective net outcomes, not just theoretical cost? |
| B3 | Gated shadow comparison | Does long-shares comparison add useful expression information without capital or short-sale authority? |
| B4 | Accepted horizon rule | Are DTE and hold-window conventions coherent across selectors and Lab? |
| C1 | Accepted display/calculation repair | Are structural intrinsic and reachable scenarios labelled distinctly and net of stated friction? |
| C2 | Gated research disclosure | Is p* shown as a scenario break-even, never a calibrated selection gate? |
| C3 | Accepted defect test, forecast validation gated | Do cumulative 5/10/20 moves and held-out forecast errors support any value language? |
| C4 | Gated model research | Are target-first/stop-first/neither labels provenance-complete and probabilities calibrated out of sample? |
| C5 | Gated model research | Do fixed-contract exit policies beat transparent baselines on untouched paths? |
| D1 | Accepted state-rule refactor | Can thesis/data/expression/rank states vary independently without losing hard integrity checks? |
| D2 | Accepted manifest truth repair | Does run-level wording reflect actionable-row completeness and remaining semantic defects honestly? |
| D3 | Accepted diagnostic | Can row movement between runs be reconciled by named cause rather than silent attrition? |
| E1 | Accepted presentation repair | Is defective convexity hidden or source-qualified while gamma/macro remain labelled? |
| E2 | Accepted advisory rule | Does macro transmit through independently measured sector/ticker evidence without a veto? |
| F1 | Accepted measurement discipline | Is the rule/cohort frozen before the future outcome is observed? |
| F2 | Accepted read-only observation | Is the broker quote exact-symbol, dated and separately stored, with no write tool? |
| F3 | Retain current boundary | Are capital and position-sizing suggestions absent from production decision output? |

These dispositions are **build decisions**, not completed fixes. A simple rule should be preferred to a model when it answers the observed defect. Any item that fails its predeclared acceptance remains open or is explicitly rejected; it does not silently become another permanent research workstream.

S0 is **not done**. The remaining gate is to reconcile the 928-field historical register against the current production Lab contract and check browser rendering, measure exact-contract quote/path coverage without confusing missing paths with zero, and review the design/receipt plus the disposition table with the actual domain owners. The local dynamic WAR/Lab mount and ID-level dispositions above are now recorded, but not clean-checkout/browser acceptance. Later slices still require build, integration, tests, acceptance and commit last. The new files in this receipt are deliberately uncommitted.
