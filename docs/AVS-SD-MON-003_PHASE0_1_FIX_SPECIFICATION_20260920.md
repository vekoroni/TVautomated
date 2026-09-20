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

### B. Restore planned-hold lineage to outcome records — REVISED, already fixed, not live

**Original hypothesis (this section as first written):** a sequencing fault — the ledger recording a
decision snapshot from a row taken before `intelligent_orchestrator.py`'s `planned_hold_sessions` patch runs.

**Verified against the real ledger before writing a fix:** `canonical_data/decision_outcome_ledger.py:352`
(`"planned_hold_sessions": row.get("planned_hold_sessions")`) is a simple, correct pass-through — no
sequencing bug in that function. Queried `data/canonical/decision_outcome_ledger.sqlite` directly (245,062
total rows) across its 12 most recent `run_id`s: **only `20260919_205844` (tonight) has
`planned_hold_sessions` populated — not even `20260918_112522` (yesterday) does.** This is not a live,
ongoing defect; it is a fix that already landed as part of this session's broader work and is working
correctly starting exactly from tonight's run. The validation record's "11,454/11,454 excluded" figure is
accumulated pre-fix ledger history (weeks of runs before tonight), which correctly stays
`PLANNED_HOLD_UNAVAILABLE` forever — those rows genuinely never had the field. It is not evidence of an
ongoing gap, and it will not reach zero; it will asymptote toward the (small, growing) share of records from
tonight onward as outcome maturation processes them over the coming sessions.

**Action taken:** no code change. `tests/test_ddd_decision_outcome.py` gained two regression-lock cases —
`candidate_events_from_rows` preserves `planned_hold_sessions` when present, and correctly leaves it `None`
(never fabricated) when absent — since this pass-through was previously covered indirectly at best, not
proven directly for this exact field.

**Regression:** the two new cases plus the full `test_ddd_decision_outcome.py` (20 total),
`test_avs_fix_002_stage6_outcome_learning.py` (22), `test_dynamic_session_phase7.py` (7),
`test_c12_outcome_scoring_stage.py` (5), `test_avs_fix_001_w39_outcome_maturation_stage.py` (14) — all green.

### C. Capture daily option bid paths for monitored family members — root cause fully traced, buildable

**Confirmed, not hypothesised:** the entire write path already exists, is tested, and is proven to work
end-to-end — it is simply never invoked from a live run.

- `outcome_learning.py:215` defaults `option_status = "UNDERLYING_ONLY"` when `option.get("data_status")`
  is absent; `option` comes from `load_option_outcome_lookup()`, a deliberate pure reader
  (`outcome_learning.py:171-197`) of the `doi_outcome_labels` table.
- `canonical_data/option_liquidity_lifecycle.py` owns that table's schema (`doi_outcome_labels_v1`,
  line 570) and its real writer, `record_doi_outcome_label()` (INSERT at line 1324) — not a stub.
- `canonical_data/dynamic_options_outcomes.py`'s `OutcomeCaptureService.capture_family()` is a complete,
  working capture service: given a DOI family, an evaluation cutoff, and two callables
  (`read_option_path`, `read_underlying_path`), it calls `domain/dynamic_options_outcomes.py`'s
  `evaluate_assessment_outcome()` per assessment/horizon and persists real labels via
  `store.record_doi_outcome_label()`. Fully covered by `tests/test_dynamic_options_outcomes.py`.
- `audit/doi/doi7_real_outcome_rehearsal.py` (224 lines) proves this works against **real** canonical
  chain data end-to-end — it is not a mock. But it hardcodes one `ORIGIN_DATASET_ID` and two
  `FUTURE_DATASET_IDS` for a single, manually-chosen ticker/session as a one-off demonstration.

**Grepped every call site of `capture_family()`/`OutcomeCaptureService(` in the repo: only its own
definition, its unit test, and the rehearsal script call it.** `intelligent_orchestrator.py` never does.
This is not a missing capability — it is missing wiring.

**DDD owner:** `domain/dynamic_options_outcomes.py` / `canonical_data/dynamic_options_outcomes.py` (already
correct); the gap is in `intelligent_orchestrator.py`'s run flow, which needs to call the existing service.

**Remaining work (scoped, not yet built):** generalise the rehearsal script's approach — loop over every
monitored DOI family each run (not one hardcoded ticker), resolve `read_option_path`/`read_underlying_path`
dynamically via the canonical registry (not hardcoded dataset IDs), and call `capture_family()` from the
same orchestrator phase that already fetches daily chains, once a session completes. This touches
production-critical canonical-registry code on the live run path and deserves its own focused session
rather than being rushed — characterisation test first: assert that after a completed session with real
chain snapshots on file, `load_option_outcome_lookup()` returns a non-empty, non-`UNDERLYING_ONLY` entry for
at least one monitored assessment, currently 0/11,454 per the validation record.

**Regression:** outcome-learning fit-eligible count should move off zero once wired; `test_ev3_options_handoff.py`
and the option-liquidity-lifecycle suite for no regression on existing DOI ranking behaviour.

### D. Repair idempotent/superseding option-observation identity — CLOSED (`b23b7f4`)

**Decision (ACK, 20 Sep 2026):** keep first-observed unchanged. `register_dataset()` now also tolerates
`completeness_status`/`as_of`/`expires_at` differing between a new and an already-registered record when
everything else (including `content_hash`) matches — the later registration becomes a no-op, first-observed
metadata is kept. A genuine `content_hash` mismatch under the same `dataset_id` still raises (data
corruption, not a legitimate re-observation, was never tolerated). Regression: 22 cases in
`test_canonical_data_system.py` plus 232+ across 19 more files touching `CanonicalRegistry`/
`register_dataset` directly — all green.

Detail retained below for provenance.

**Confirmed, not hypothesised — and no new test was even needed, existing tests already prove it:**
`canonical_data/registry.py::register_dataset()` (the general canonical registry, used for OHLCV as well as
options — not options-specific) computes `dataset_id = sha256(type|ticker|session_date|scope_fingerprint|
content_hash)` (`canonical_data/option_chain_store.py:184-189`). `content_hash` is baked into `dataset_id`
itself, so two genuinely different quote observations can never collide — that part of the design is
sound. The conflict is different: `completeness_status`, `as_of`, and `expires_at` are **not** part of the
hash, so a *second* registration of byte-identical content (e.g. the same chain re-observed later, or
upgraded from `PARTIAL` to `COMPLETE`) shares the same `dataset_id` but differs in a field the immutability
check does not tolerate — `register_dataset()` only normalises `source_run_id` and `observed_at` before
comparing, not `as_of` or `completeness_status`. Proven directly by two tests already in the suite,
currently green as *expected* behaviour:
- `tests/test_canonical_data_system.py::test_registry_preserves_provenance_and_content_identity` — registers
  a record, re-registers the same `dataset_id` with only `as_of` advanced, asserts `DatasetValidationError`.
- `tests/test_canonical_data_system.py::test_identical_dataset_is_reusable_across_runs_without_rewriting_origin`
  — same pattern for `source_run_id`/`observed_at` (which *are* tolerated) vs. `content_hash` (which correctly
  is not).

**This is not a mechanical bug to patch — it is a design decision.** `register_dataset()`'s current behaviour
is asserted as *correct* by tests that would need to change alongside any fix, and this registry is the
general canonical-evidence store, not an options-only component — changing what "immutable" tolerates
affects every dataset type it serves, not just option quotes. The open question for ACK: when the same
content (`content_hash`/`dataset_id` identical) is re-registered with a different `completeness_status` or
`as_of`, should the registry (a) keep the first-observed record unchanged (idempotent no-op, matching how
`source_run_id`/`observed_at` already behave), (b) accept the newer/more-complete metadata as a supersession
(update in place), or (c) something else? This determines the fix; it should not be decided unilaterally in
this pass.

**DDD owner:** `canonical_data/registry.py` (`register_dataset()`), not `dynamic_options_production.py` as
originally guessed — the mechanism is one level lower, in the general registry every dataset type shares.

**Regression:** the two existing tests above will need their assertions updated to match whichever semantics
ACK chooses — they currently encode the *old* behaviour as correct, so a fix without updating them would
just trade one false assertion for another.

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
ambiguous; (2) ~~commit item A~~ **done** (`65c5d7d`); (3) locate and update the "one stale provider-timestamp
test" the validation record references (not yet identified by name in this pass — needs a targeted search
for a test asserting provider/fetch timestamp equality or a fixed clock that has since drifted stale);
(4) tag the resulting commit as the Phase 0 baseline.

**Status, 20 Sep 2026:** (1) is **resolved** — the 39 deletions were initially deferred 8 days, then
reconsidered within the same session and confirmed for deletion (`43136b1`). (3) and (4) remain open: the
stale provider-timestamp test is not yet identified by name, and the Phase 0 baseline is not yet tagged.

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

1. A is committed (`65c5d7d`, done). H's deletion blocker is resolved (`43136b1`); the stale
   provider-timestamp test and the Phase 0 tag are still outstanding.
2. **G closed** (`16475ea`). Archive completes cleanly with a pre-flight headroom check added.
3. **D closed** (`b23b7f4`). ACK decided "keep first-observed unchanged"; fixed, tested, wide regression
   green.
4. **B closed.** Verified already fixed as of tonight's run, not a live defect — see revised §B. **C's root
   cause is fully traced** (the capture service and its writer both exist, are tested, and are proven
   against real data by the rehearsal script — only the live-run wiring is missing); the blocking count
   (0/11,454 available) still needs to move once that wiring is built.
5. E's reconciliation assertion runs clean, or any residual gap is independently root-caused.
6. **Closed.** F's 162 rows are confirmed correctly withheld from candidate/capital authority (verified
   against real data, not assumed), and the audit's `FAIL` severity is confirmed to describe a D1 data-
   coverage question, not an authority-governance gap — no fill-rate target applies here, D1's decision
   governs whatever comes next.

Until all six hold, Phase 2 (path-label factory) and Phase 3 (research tournament) do not start — matching
the approved design's own instruction to proceed with Phase 0 and Phase 1 before building a predictive path
model.
