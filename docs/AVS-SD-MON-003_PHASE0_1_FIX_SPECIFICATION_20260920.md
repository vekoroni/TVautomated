# AVS-SD-MON-003 — Phase 0/1 Fix Specification (TDD/DDD)

**Version:** 1.0
**Date:** 20 September 2026
**Companion to:** `docs/AVS-SD-MON-003_PATH_AWARE_MONETISATION_AND_EXPRESSION.md` (v1.0, approved) and
`audit/solution_design/AVS-SD-MON-003_VALIDATION_20260920.md`
**Status:** proposal — no code changed by this document
**Does not modify:** either frozen document above. Registered definitions stay frozen; this is an addendum,
matching the house convention already used for `SCENARIO_REGISTER_ADDENDUM_S_ACT_20260920.md` and
`SCENARIO_REGISTER_ADDENDUM_CEX_20260920.md`.

## 1. Purpose

The approved design (§13) sequences six phases; a predictive path model cannot be built honestly until
Phase 0 and Phase 1 close (validation record, §"Verdict"). This document turns the validation's eight
"required pre-model repairs" into TDD fix specifications: root cause, the DDD context that owns the fix,
the characterisation/failing test to write first, the minimal fix, and the regression that must stay green.
Nothing here proposes new architecture — every fix lands inside a module the validation record already
named as the correct seam (its "Structural fit" list).

Two of the eight items were found and evidenced independently tonight, before this design existed, from
direct inspection of run `20260919_205844` (commit `785290c`, the same HEAD the validation record
inspected) — items F and G below. The other six are grounded here against current code; three (B, C, E)
have a confirmed mechanism, three (D, H, and part of E) name the right module but need their own
characterisation test to pin the exact fault before a fix is written, which is the correct TDD order, not
a gap in this spec.

## 2. Ordering

Some fixes block others. Sequence, matching the design's own Phase 0 / Phase 1 split:

```
Phase 0                          Phase 1
  A. commit activity/PCR    ┐      D. idempotent option-observation identity  ┐
  G. disk headroom + archive├──►     ├──► B. planned-hold lineage  ┐
  H. clean tagged baseline  ┘        ├──► C. option bid paths      ├──► E. DOI population reconciliation
                                     └──► F. missing invalidation lineage    (independent, can run in parallel)
```

A and G have no dependency and should land first — A because uncommitted work should not be built on top of,
G because a run cannot be called accepted while its archive step fails (design §15: "No successful stage
may be followed by an unreconciled final dispatcher or archive failure and still be called an accepted
run"). H (clean baseline) is the exit condition for Phase 0 and needs A and G done first. D is foundational
for B, C and E — outcome records and DOI population counts cannot be trusted while the same option
observation can silently conflict with itself.

## 3. Fixes

### A. Commit and govern the activity/PCR correction

**Root cause:** `compute_delta_weighted_oi()` and its downstream consumers (`avshunter_superbrain_layer.py`,
`execution_intelligence_runner.py`, `trigger_layer.py`, `pipeline_interpreter/direction_conflict_resolver.py`)
have been rewritten in the working tree to treat OI/PCR as `ADVISORY_ONLY` / `POSITIONING_CONTEXT_ONLY`
positioning evidence — never a directional confirm, conflict, veto or score input (confirmed:
`tests/test_f7_delta_weighted_pcr.py` asserts `activity_authority == "ADVISORY_ONLY"`,
`pcr_confidence_weight == 0.0`, and that behavioural vetoes never fire from `pcr_vol`/`dw_signal`). This is
correct and consistent with governed rule 6 and mandatory invariant §5.4 ("Open interest is positioning
evidence. Printed volume is activity evidence. Neither is signed flow"). It is simply uncommitted, alongside
39 unrelated tracked-file deletions (`Archive/`, several root-level docs) already confirmed unrelated to
this or any other change made tonight.

**DDD owner:** `scripts/avshunter_options_intelligence.py` (Activity/Expression evidence), with the four
downstream consumer modules as its boundary.

**Characterisation test (already exists):** `tests/test_f7_delta_weighted_pcr.py` — 8 cases, covering the
function's real-volume/OI-only/empty-chain behaviour, the activity-state taxonomy, that PCR never confirms
or conflicts with thesis direction, and that Superbrain/trigger-layer/execution-handoff all retire legacy
PCR-as-directional-signal behaviour. This already satisfies TDD's "test states the business rule in domain
language" requirement — it does not need to be rewritten, only run and committed alongside the code it
covers.

**Fix:** `git add` and commit the module changes with their test file as one unit (do not split governed
behaviour from its test across commits).

**Regression:** full suite for the four touched modules, plus the existing PCR/direction-governance suites
(`test_direction_governance_contract.py`, `test_avs_sd003_authority_boundaries.py`) to confirm no other
consumer still reads `pcr_signal`/`dw_signal` as directional.

### B. Restore planned-hold lineage to outcome records

**Root cause, confirmed by code trace:** `canonical_data/outcome_learning.py:246-247` excludes a record with
`PLANNED_HOLD_UNAVAILABLE` whenever `candidate_payload.get("planned_hold_sessions")` is `None`.
`candidate_payload` is `candidate.payload`, sourced from `decision_outcome_ledger.py:352`
(`"planned_hold_sessions": row.get("planned_hold_sessions")`) — i.e. whatever was on the `row` at the moment
the ledger recorded the decision. `intelligent_orchestrator.py:3808-3828` patches `planned_hold_sessions`
onto the options dataframe for EV3's consumption, with its own comment noting it is "the governed thesis
window (D2)." The two facts together are consistent with a sequencing fault: the ledger records its decision
snapshot from a row taken before this patch step runs, not after.

**DDD owner:** `canonical_data/decision_outcome_ledger.py` (Decision and Outcome context) — it must read the
patched row, not an earlier one.

**Characterisation test to write first:** given a fixture row that has `planned_hold_sessions` set only
*after* the point in the pipeline `intelligent_orchestrator.py` currently patches it, assert that a decision
recorded from that row via `decision_outcome_ledger` carries a non-null `planned_hold_sessions` in its
persisted payload. This should fail against current code (reproducing the 11,454/11,454 exclusion) before
any fix, and pass after — the standard characterise-then-fix pattern.

**Fix:** move the ledger's decision-recording call to after the `planned_hold_sessions` patch in the
orchestrator's phase order, or have the ledger read the patched dataframe rather than the pre-patch row —
whichever is the smaller, more local change once the characterisation test shows exactly which row instance
is stale.

**Regression:** `tests/test_ev3_orchestrator_order.py` (already exists, presumably covers ordering) plus the
outcome-learning suite; re-run tonight's `20260919_205844` learning-record build and confirm the
`PLANNED_HOLD_UNAVAILABLE` exclusion count drops from 100% to the genuine residual (rows where the thesis
truly has no governed hold, not all rows).

### C. Capture daily option bid paths for monitored family members

**Root cause, confirmed by code trace:** `outcome_learning.py:215` defaults
`option_status = "UNDERLYING_ONLY"` whenever `option.get("data_status")` is absent; `option` is sourced from
`load_option_outcome_lookup()`, whose own docstring is explicit — "Read already-canonical DOI labels; never
fetch or infer option history" — reading a `doi_outcome_labels` table that returns `{}` silently if the
table is empty, missing, or the control-plane path doesn't resolve (`outcome_learning.py:171-197`). This
function is a pure reader by design; the defect is upstream, in whatever process is meant to populate
`doi_outcome_labels` with daily bid/ask marks for monitored contracts. The validation record's structural-fit
list names `domain/dynamic_options_outcomes.py` as the module that should own this write path.

**DDD owner:** `domain/dynamic_options_outcomes.py` (Path Forecast / Decision and Outcome boundary) — must
write `doi_outcome_labels` from observed option marks; `outcome_learning.py` stays a pure reader.

**Characterisation test to write first:** for a monitored contract with real chain snapshots on file in
Phantom for two or more sessions after entry, assert `load_option_outcome_lookup()` returns a non-empty
entry for that `(assessment_id, horizon)` with `data_status != "UNDERLYING_ONLY"`. Currently fails
(0/11,454 available, per the validation record) — confirm whether the write path is never invoked, invoked
but writing to the wrong path/table, or invoked but silently failing (each has a different, smaller fix).

**Fix:** depends on what the characterisation test isolates — likely wiring `dynamic_options_outcomes.py`'s
label-writer into the same run phase that already fetches daily chains (reuse, no new chain-fetch
mechanism — canonical stores already exist per the design's §3.1).

**Regression:** outcome-learning fit-eligible count should move off zero; `test_ev3_options_handoff.py` and
the option-liquidity-lifecycle suite for no regression on existing DOI ranking behaviour.

### D. Repair idempotent/superseding option-observation identity

**Root cause:** not yet isolated in this pass — flagged by the design (§13, Phase 1.1: "so repeated same-run
observations are idempotent and genuinely different observations supersede rather than conflict") and the
validation record's "most exceptions were immutable quote-identity conflicts" (§3.2 item 3). No confirmed
code-level mechanism found in this session; grep for an observation-identity/supersession function in
`canonical_data/dynamic_options_production.py` (the design's named owner) returned nothing named that way —
the actual identity key is likely elsewhere in the same file or in `canonical_data/dynamic_options_*`
siblings and needs direct inspection before a fix spec can be written with confidence.

**DDD owner:** `canonical_data/dynamic_options_production.py` (Canonical Market Evidence — option-observation
identity).

**Characterisation test to write first:** given two fetches of the same contract within the same run where
only the quote timestamp advanced, assert the second fetch supersedes the first (one live observation,
one superseded, not two conflicting rows). Given two fetches where the underlying quote genuinely differs
(a real re-quote), assert both persist as distinct, ordered observations. This test does not yet exist and
must be written against current behaviour first — it will very likely fail, which is the point: it turns
"most exceptions were immutable quote-identity conflicts" from a description into a reproducible case.

**Fix:** withheld until the characterisation test names the exact identity key currently causing conflicts
(candidate keys to check: whether provider timestamp, fetch timestamp, or both are part of the identity;
whether "immutable" here means an append-only table with no supersession concept at all, which would be a
larger and different fix than a key correction).

**Regression:** `test_options_crossed_quote_integration.py` and `test_msi_options_chain_v2_integration.py`
(closest existing coverage) plus item E's reconciliation counts as the acceptance signal — if D is fixed,
E's generated/assessed/ranked/exception populations should reconcile without unexplained loss.

### E. Reconcile all DOI generated/assessed/ranked/exception populations

**Root cause:** downstream of D — the validation record notes "only a subset of directional families
completed ranking; most exceptions were immutable quote-identity conflicts" (§3.2 item 3). Expected to
substantially resolve once D lands; not treated as an independent defect in this spec.

**DDD owner:** `domain/dynamic_options_ranking.py` (the design's named owner for DOI ranking).

**Characterisation test to write first:** for one full run, assert
`generated == assessed + data_exception_count` and `assessed == ranked + exception_retained_count`, i.e. no
candidate disappears between phases without a recorded reason. Run this against `20260919_205844` now, before
D is fixed, to get the current unreconciled gap as a baseline number, then again after D lands to confirm it
closes to (ideally) zero unexplained loss.

**Fix:** re-run reconciliation after D; if a gap remains, it is a second, independent defect in
`dynamic_options_ranking.py` itself and gets its own root-cause pass rather than being bundled with D's fix.

**Regression:** the reconciliation assertion above, kept as a standing per-run observability check (design
§15 already calls for this — "candidates assessed, ranked, monitored and ready... exact population
reconciliation" — this makes it a test, not only a log line).

### F. Correct the remaining missing invalidation lineage — REVISED, not a code defect

**Original assumption (this section as first written):** `eod_candidate_engine.py` needed a fix to withhold
candidate/capital authority for the 162 rows flagged by `handoff_contract_audit_20260919_205844.csv`
(`eod_candidate_requires_invalidation | filled_rows=162 | fill_rate=0.1049`), per the audit's own
recommendation: "Remove candidate/capital authority until governed invalidation is available." Sample
tickers: MCD, Z, USAR, AEP, SOFI, CELH, LEU, DJT, AAP, NNE, GNTX, YELP.

**Verified against real code and tonight's real data before writing any fix (exactly what B and C's
characterisation-first approach would have caught for this item too, had it been done before the original
draft):** `_candidate_permission_fields()` and the EOD status classifier both already withhold authority
correctly — `direction in GOVERNED_DIRECTED_SIDES and not invalidation_available` sets
`capital_permission="NO"`, `capital_authorization_state="NOT_AUTHORIZED_INVALIDATION_MISSING"`,
`eod_status="EOD_DATA_INSUFFICIENT_REVIEW"`. Checked directly against `morning_candidates_20260919_205844.csv`
for 11 of the 12 sample tickers (the 12th had a CSV-parsing artefact in the recommendation string, not a
data issue): every one shows `capital_permission=NO`, `invalidation_spot=NaN` (correctly missing, never
zero), `eod_status=EOD_DATA_INSUFFICIENT_REVIEW`. **There is no governance gap here — the mandatory
invariant is already being honoured.**

**The upstream question has a confirmed, clean answer, not a bug:** cross-referencing all 162 rows against
`thesis_geometry_review_state` (`scripts/avshunter_options_intelligence.py`) shows 160/162 are
`DIRECTION_CONTRADICTS_STRUCTURE` and 2/162 are `MISSING_STOP`. `thesis_geometry_review()` is working
exactly as documented — a CALL in Wyckoff DISTRIBUTION or a PUT in ACCUMULATION has no valid stop because
the structural invalidation lies on the wrong side, and it correctly refuses to fabricate one rather than
inventing a number. **This is the identical population S-DIR-3 already measured** (register, Round 2
findings, 20 Sep): at 10 and 20 session horizons, the structure-implied direction has significantly
outperformed the governed direction for exactly these rows (t=-4.89/-4.73, p<0.0001). Item F was never a
second, independent defect — it is D1, observed from a different angle (the authority side rather than the
directional-accuracy side).

**Action taken:** no code change. `tests/test_missing_invalidation_authority_withheld.py` locks the
verified-correct current behaviour against regression (it was previously assumed, not proven, so it needed
a test regardless of there being no fix). **Any further action is gated on ACK's D1 decision, not a
standalone repair** — if D1 resolves toward "structure wins" for conflict rows, a natural follow-on would
be computing a structure-consistent invalidation level for the structure-implied direction so
`eod_candidate_engine.py`'s already-correct logic can then grant authority using it. That is new scope for
whenever D1 closes, not part of Phase 0/1.

**Regression:** `tests/test_missing_invalidation_authority_withheld.py` (4 cases) plus the existing
`eod_candidate_engine.py` suites (`test_avs_fix_001_w13_monetisability_authority`,
`test_avs_sd003_authority_boundaries`, `test_book_integrity_e3_e4_e5_e7`, `test_cycle2_governance`,
`test_direction_geometry_semantic_repairs`, `test_dynamic_options_non_discard_policy`,
`test_eod_options_research_handoff`, `test_low_risk_pipeline_repairs` — 71 cases) all green.

### G. Restore disk headroom and prove final archive completion

**Root cause, directly evidenced tonight:** `logs/orchestrator.log`, run `20260919_205844` — Phase 10 Archive
failed with `[WinError 112] There is not enough space on the disk` (C: drive at ~240MB free at the time),
logged as `Dynamic dispatcher failed closed`, after which the orchestrator process exited without completing
archival. Confirmed by direct `data/output/runs/<run_id>/` vs `data/archive/<run_id>/` comparison: the run's
real outputs are intact in `data/output/`, only the backup copy is missing. Disk usage breakdown at the
time: `data/output` 107G (56 run folders back to 23 Jul), `data/archive` 71G, `data/phantom` 43G,
`audit` 18G.

**DDD owner:** operational/infrastructure, not a DDD context — the archive step itself
(`intelligent_orchestrator.py::archive_outputs()`) is sound; the failure is capacity, not logic.

**Action taken tonight (already done, not proposed):** the 10 oldest `data/output/runs/` folders
(23 Jul – 15 Aug 2026, ~23GB, all superseded by 46 later runs and independently confirmed to have zero
live reference from any backtest/research script — grepped) were deleted with ACK's explicit approval.
Free space recovered from ~240MB to ~91.5GB.

**Remaining for Phase 0 closure:** re-run or wait for the next natural archive pass to prove
`20260919_205844` (and any run since) archives cleanly with headroom now available; add a pre-flight
disk-headroom check to the archive phase so a future low-space condition fails loudly *before* attempting
the copy, rather than mid-copy with a partially-written archive directory.

**Characterisation test to write first:** given a mocked filesystem reporting less free space than the
run's output size, assert `archive_outputs()` refuses to start and reports the shortfall, rather than
attempting a partial copy. This test does not exist today (tonight's failure occurred mid-copy, leaving a
partially-populated `data/archive/20260919_205844/`, which itself needs cleanup or completion before being
treated as valid archive evidence).

**Regression:** confirm `data/archive/20260919_205844/` is either completed or cleanly absent (not
partially populated) before the next run archives on top of it.

### H. Establish a clean tagged release baseline and update the one stale provider-timestamp test

**Root cause:** the working tree at `785290c` (the commit both this document and the validation record were
produced against) mixes: committed production fixes (F4, F7, D6/D7 — this session), a fully-formed but
uncommitted governed change (item A), 39 unrelated tracked-file deletions of unconfirmed origin (`Archive/`
and root-level docs — confirmed by direct filesystem check to be genuinely deleted, not a git-status
artefact, and confirmed to have zero live code/doc references, but not yet confirmed as *intentional*), and
untracked research artefacts under `Enhancements/`. The validation record's "no clean tagged current
baseline" (§Release state) reflects exactly this mix, not a fault in any individual change.

**DDD owner:** repository/release governance — no domain module.

**Characterisation:** not applicable in the TDD sense (this is a release-hygiene item, not a code-behaviour
defect) — the "test" is the release manifest itself: code/config/schema hashes, a diff against the last
tagged baseline, and explicit confirmation from ACK on the 39 pending deletions before they are either
committed or restored.

**Fix:** (1) resolve the 39 pending deletions explicitly — commit or `git checkout --` restore, not left
ambiguous; (2) commit item A; (3) locate and update the "one stale provider-timestamp test" the validation
record references (not yet identified by name in this pass — needs a targeted search for a test asserting
provider/fetch timestamp equality or a fixed clock that has since drifted stale); (4) tag the resulting
commit as the Phase 0 baseline.

**Regression:** full suite green at the tagged commit; this tag becomes the rollback target named in the
design's §16.

## 4. Regression matrix (Phase 0/1 exit criterion)

Per the design's §14 test architecture, Phase 0/1 is not exit-ready on "the new tests I wrote pass" alone.
Required before declaring Phase 0/1 closed:

| Layer | What | Already exists? |
|---|---|---|
| Unit/property | State machines cannot cross domain boundaries; missing values never become zero; quote identity is idempotent (D); OI/volume cannot generate directional authority (A) | Partially — A's suite exists; D's does not yet |
| Integration | Canonical chain → family → valuation → expression projection; Decision Ledger → outcome maturation → learning record (B, C) | Partially — needs extension once B/C land |
| Adversarial | Future OI injected into entry-time features; stale cache newer than canonical provider observation (relevant to H's stale-timestamp item) | Needs the specific test named in H |
| Acceptance pack | Full regression output, input/output reconciliation (E), rollback instructions, hashes | Not yet produced for this baseline |
| Observability | Per-run reconciliation report (design §15) matching E's reconciliation assertion | E's test becomes this permanently, not a one-off check |

## 5. Definition of done for this document specifically

Narrower than the design's global §18 — this closes when:

1. A and H are committed and tagged as the Phase 0 baseline.
2. G is proven (archive completes cleanly on the next run, pre-flight check added).
3. D's characterisation test exists and its root cause is named (fixed or explicitly deferred with reason).
4. B and C each move their respective blocking count off its current value (100% excluded, 0 available) with
   evidence, even if not fully to zero.
5. E's reconciliation assertion runs clean, or any residual gap is independently root-caused.
6. **Closed.** F's 162 rows are confirmed correctly withheld from candidate/capital authority (verified
   against real data, not assumed), and the audit's `FAIL` severity is confirmed to describe a D1 data-
   coverage question, not an authority-governance gap — no fill-rate target applies here, D1's decision
   governs whatever comes next.

Until all six hold, Phase 2 (path-label factory) and Phase 3 (research tournament) do not start — matching
the approved design's own instruction to proceed with Phase 0 and Phase 1 before building a predictive path
model.
