# First build brief — baseline qualification, current-volatility handoff and direction safeguards

**Date:** 21 November 2026  
**Status:** PREPARED FOR REVIEW — DO NOT BUILD. No implementation, agent change, model call, pipeline run, merge or commit is authorised by this brief alone.  
**Committed baseline:** `laneb/lab-first-handoff` / `9e7849bbdef03d1bc70d36c6e387eb6860b0e636`. Source hashes, tests and residuals: `baseline_qualification_receipt_20261121.json` in this chat's outputs. If HEAD or an affected source hash differs, reconcile before implementation.

## 0. Required decisions before the first build

**Final baseline reconciliation:** While preparing this update, commit `9e7849bbdef03d1bc70d36c6e387eb6860b0e636` committed the register and all five explained residual files. Its six-file diff contains no production source/config/test changes; all pinned source hashes remain checked at application. The earlier tests were run against `f3e199e`, whose production sources are unchanged. The commit decisions in section 10 A1/A5 are therefore completed, superseding the pending wording there; other ACK decisions and the build hold remain. No commit was performed by this investigation. Tracked working tree was clean immediately after that commit; this documentation update will be a new uncommitted delta.

ACK amendments in register section 10 take precedence. The register/five historical residuals are committed. Remaining decisions concern whether to merge, selectively reapply or drop eligibility commit `eb50549`; TR-005 delayed-feed policy versus “flag quote age, never gate”; the versioned agent packet (reported 1,036 bytes of headroom). No merge, commit, policy decision or decommission is performed here.

Eligibility integration affects production admission, not merely metadata: its gate rejects dirty/unavailable code for STANDARD PRODUCTION BUILD_THESIS/FINALISE before acquisition, with explicit non-baseline mode exceptions. The commit itself changes 48 added/7 removed orchestrator lines; comparing the branch tip to current HEAD also includes newer unrelated work. Do not replace whole files: preserve current code receipts, retention, Morning timing and final Lab republishing. Re-pin baseline and rerun affected tests after any approved integration, before VOL-02 touches the same orchestrator.

Legacy `pipeline_interpreter` retirement belongs in step 0/publication-handoff design (AG-F07), separate from the new Interpreter agent. Six sync call sites, Evening snapshot, Lab views and manifest preparation are statically confirmed. ACK has now included legacy Interpreter decommissioning in these fixes. Retire legacy-only Lab views; trace and preserve or migrate required readers/handoffs before reversible disconnection. Preserve historical code/evidence for rollback. This scope decision does not lift the no-build hold. Section 10's size/report-age claims are attributed, not independently measured here. No hooks are disabled now.

The historical residual explanations and their commit disposition are closed by `9e7849b`. The Lab timing test is identical across the branch comparison, but implementation is not; real-run validation remains owed. These qualifications do not turn the current checked-in test suite green.

## 1. Decision and implementation order

1. **BF-00, prerequisite: repair the isolated test fixture, not production policy.** The current cost tests pass 16/16. Macro-completion has one reproducible failure and five passes; the failing temporary fixture lacks its required publication-mode configuration. A workspace-only diagnostic confirms the existing function resolves/verifies the archived base with an explicit DATA_ONLY fixture config, rejects a tampered hash and preserves the FULL-mode prohibition. The test source is unchanged. Baseline is understood with a known exception, not green.
2. **BF-01, first production repair proposed: VOL-01..03 / B1/F1.** Produce the price-only forecast before OI, deliver a typed IV assessment on all governed chain paths and record what the valuer actually consumed. Keep model, estimator, side, selected-contract and authority behaviour unchanged except the approved data-flow repair's declared consequences.
3. **BF-02, separate defensive follow-up: H2 direction adapter and exact identity.** Remove a latent invented-CALL path and qualify aliases against the existing direction owner; protect duplicate-key routing. No observed wrong-side incident was found in three saved runs. Do not inflate this into a reason to redesign or reset current governed directions.

Do not combine these as an unreviewable all-at-once change. BF-00 is a fixture-only change. BF-01 is a data-flow/quality repair. BF-02 changes malformed-input handling and therefore needs explicit compatibility and consumer acceptance.

## 1A. BF-03 / AG-F07 — legacy Interpreter retirement

Scope accepted by ACK on 21 November to reduce pipeline runtime; implementation remains held. Treat this as step-0 publication/handoff work, coordinated with eligibility and VOL-02 orchestrator edits and completed before agent activation. It is separate from the new Interpreter agent.

Disconnect the six legacy sync call sites, Evening snapshot, legacy Lab desk/war mounts and manifest preparation after tracing their consumers. Retire legacy-only views; migrate required readers to canonical saved artifacts. No active legacy dependency should remain solely awaiting agents. Avoid a replacement copying/publication layer.

Before authorised implementation, prepare failing cases for each supported entry point and publication/handoff compatibility. Acceptance must show zero legacy runtime invocations/copy side effects, unchanged canonical outputs and decision authority, and correct retired/retained endpoint behaviour. Measure comparable before/after stage and total wall time, bytes copied and invocation counts; do not promise savings from unverified size estimates. Preserve code/history and historical data for coherent rollback. Do not delete archives or remove shared utilities without a consumer check.

Status: built NO; committed NO; wired NO; tested STATIC TRACE ONLY; validated NO; authorised SCOPE ACCEPTED / BUILD HELD.

## 2. Baseline qualifications resolved into explicit dispositions

- Commit baseline stable, nothing staged, index lock absent. Selected production source/config/test files are hashed and compared to HEAD in the receipt. This is not a claim that every untracked file is irrelevant or every test passes.
- The fix register is an intentional documentation delta. Two 2 October outcome reports are generated historical output deltas; the canonical outcome service writes reports, while current learning reads its ledger/labels. Preserve them and do not use them as the reference outcome evidence for this build.
- Three deleted interpreter-backup files are retention/history residuals. No direct reference was found in the traced production entry points. Preserve the current state; no restoration/deletion approval is inferred and a complete recovery audit is outside this brief.
- Untracked `data/scratch/workaround/strategy_layer.py` is not safely 'unused'. It is a standalone Lane B CLI that writes strategy CSV/Markdown; tracked `check_triage.py` can consume that CSV on the old handoff layout. Record its hash as an external/manual input boundary. It is not imported by the traced Evening/Morning/forecast paths. Do not edit it, run it, or delete it here; any Lane B end-to-end claim must pin the supplied strategy artifact/version or mark it unavailable.
- `.claude`, `.testdeps`, research/output archives and isolated agent packages are not silently promoted into the production release. No direct import was found in the traced owners; dynamic launch paths beyond this scope remain unverified. Use the pinned existing venv for tests.
- A scope-qualified build can be designed around these explicit residuals. A pristine whole-estate release and restoration certification has not been established. User's no-build hold remains decisive.

## 3. Direction/default trace and observed impact

The active source path is Discovery thesis -> OI `parse_structural_context` -> `resolve_governed_direction` -> `final_direction`/GDR -> horizon adapter/router -> OI/other output projections -> EIL/EOD -> Morning GDR validation/lock.

For current thesis records, OI maps the Discovery thesis side to the governed direction, passes `DISCOVERY_GOVERNED` and disables non-directional re-resolution. Legacy structural/evidence resolution is a separate compatibility path. Morning's explicit-side migration adapter uses UNRESOLVED if no directed side exists; governed records lock to final GDR rather than conducting a fresh vote. EIL's traced forward-physics helper reads existing final/governed/canonical/direction fields without a CALL default.

H2 is in `intelligent_orchestrator.py`, `run_horizon_router`, around lines 1751-1765:
- Adapter priority: instrument, options_direction, strategy_type, direction; default CALL.
- It does not consult canonical_direction/final_direction at this lookup.
- The actual router normalises CALL/LONG_CALL and PUT/LONG_PUT and blocks unknown/STRANGLE explicitly. The caller can therefore bypass the router's unknown handling by inventing CALL before calling it.
- Extracted existing helper reproduces: empty row -> CALL; canonical_direction=PUT alone -> CALL; instrument=CALL plus options_direction=PUT -> CALL; direction=UNRESOLVED remains UNRESOLVED. These are local source characterisations, not a production incident.

Saved evidence (OI input reconstructed from current output artifacts; not a rerun of the original process):

| Run | OI / horizon rows | Adapter source | Default CALL | Directed mismatch in horizon IDs |
|---|---:|---|---:|---:|
| 20261119_234734 | 2,746 | options_direction on every row | 0 | 0 |
| 20261119_000537 | 2,764 | options_direction on every row | 0 | 0 |
| 20261118_000634 | 2,772 | options_direction on every row | 0 | 0 |
| Total | 8,282 | explicit side field | 0 | 0 |

No saved horizon row in this check had a directed routed ID with a non-directed governed state. This bounds the inspected outputs; it does not prove all historical, Morning or alternate-launch paths are safe.

Additional latent integration risk: the router writer reconstructs raw rows by ticker and a later patch can fall back from signal_id to ticker. Current OI/horizon artifacts have one row per ticker in the inspected runs; multi-thesis/CALL+PUT collisions require dedicated regression fixtures, not an assertion they happened here.

`DIRECTION_CONFIRMED` at the shared owner is used when final direction equals governed direction; fresh Discovery-authority records intentionally carry no independent re-resolution evidence chain. Its validator expects this path token. It is not a calibrated success-probability statement. Do not rename the schema token or force an evidence vote to fix a display concern without versioned owner/validator/UI compatibility. Confidence/calibration labels require separate semantics.

## 4. BF-00 — exact future fixture repair

Owner: `tests/test_macro_completion.py`. Target test: `test_data_only_base_requires_exact_archived_ai_and_never_chains_data_only`.

Proposed change: create minimal `tmp_path/config/macro_delivery_v1.json` with explicit `publication_mode: DATA_ONLY` for this DATA_ONLY archive test. Keep its existing validator mock and archive/hash checks. Do not blindly copy the live config: its publication mode is a separate policy and may be FULL. Keep/add a separate FULL refusal assertion and missing/invalid-config case as appropriate under existing owner tests.

Do not change `publication_mode`, `require_data_only_mode` or live config to make the test pass. Expected effect: six macro-completion tests pass under the pinned environment, cost tests remain 16/16, no change in production behaviour. Record the pre-fix failure and exact post-fix command/output. This brief does not perform that change.

## 5. BF-01 — bounded implementation design

### Owned files and inputs

- `garch_runner.py`: application runner/worklist/session/cutoff, optional IV comparison separation.
- `layer3_forward_variance.py`: existing model owner; method/bounds unchanged for this slice.
- `intelligent_orchestrator.py`: explicit pre-OI stage and handoff, not a dependency on an EIL file existing.
- `scripts/avshunter_options_intelligence.py`: consume pinned current forecast before contract valuation, calculate/publish IV result at the chain boundary and retain it on early returns.
- Existing canonical chain/history/outbox/config owners and tests only where the smallest integration requires it. Do not introduce a parallel price/IV/pricer database or solver.

Freeze the authorised pre-OI candidate worklist from the existing upstream stage. It must account for exactly the intended OI population before contract selection, including explicit unavailable rows; no fallback to all tickers or a paid acquisition expansion. One owner computes each forecast per ticker/session/input/config version. Chain observations are acquired/reused through existing governed access once.

### Ordered data flow

1. RunContext pins run ID, evidence session, observation cutoff, worklist/source hashes, estimator/model/config versions and allowed completed-session price history.
2. Price-only forecast stage runs before forecast-dependent OI. No dependency on selected contract, SuperBrain or EIL success. Optional IV does not control forecast existence.
3. OI receives an explicit immutable forecast map/reference; do not scan newest prior run folders and label the result current. Missing/old/incompatible state is explicit according to approved consumer policy.
4. Whenever the governed canonical chain exists, calculate IV30 using the current estimator and attach a typed reason/result before direction-specific or no-contract returns. Preserve deliberate chain suppression policy and do not make extra calls solely to fill the field.
5. Build/refer to one volatility assessment from compatible sources; a missing IV does not erase a usable price forecast. Record actual consumed IDs before publication.
6. Dependent valuation/reachability/DOI reads the same pinned assessment. Legacy column delivery may remain for compatibility; a later merge never retroactively claims an earlier decision used the evidence.

### Constraints

- Retain the current HAR/GARCH/EWMA/ATR methodology and existing IV estimator filters for the initial repair. No fit-window/model/strike interpolation/percentile redesign or normalized Phantom-score rollout here.
- No new age-only trade/contract gate. Report clocks and limitations without mislabelling old evidence as current; any consumer-policy change that affects decisions is separately approved.
- No new IV solver; shared-pricer inversion is a later explicit dependency. Vendor IV already stored can be carried without it.
- Preserve thesis direction/target/invalidation/hold authority, existing contract selection mode SHADOW, sizing, execution permission and candidate population except explicitly assessed dependency failures.
- Forecast availability may change shadow valuation results. That is the intended observed effect, not automatic permission to switch contracts.

### Required tests before future code changes

Characterise original stage order, unavailable-selector result and IV early-return omission using saved-input fixtures. Then failing business tests must establish:
- Current permitted forecast is available and consumed before valuation; EIL failure cannot suppress independent computation; no circular OI/SuperBrain dependency.
- Replay price/quote/revision cutoffs exclude future evidence; morning's prior-close policy is labelled correctly.
- No-direction-but-priceable-alternatives and no-selected-contract paths still publish a benchmark assessment/reason; no-chain/suppressed cases retain explicit state without extra calls.
- Missing IV leaves forecast usable; clipped/raw forecast policy, empty/partial artifact, restart/cache and duplicate-worklist identities do not silently misstate availability.
- Original directions/contract/permission fields are preserved. Future revised evaluation is a new record, not an overwrite of old decisions.

Provider-free saved-run acceptance: reconcile all 2,746 rows for 20261119_234734; record coverage/missing reasons, actual consumed-source provenance and valuation availability. Reassess all 595 chain-bearing early-return cases. The previous 426 numerical recovery candidates are an expectation to check, subject to source/quality, not a mandatory forced count. Do not promise every B1 row becomes valued: target/stop/model inputs may also be unavailable.

Real-session forward acceptance: after implementation approval and offline verification, observe one complete qualified session and then the outcome window required by the change's validation policy. Business benefit is valuation/decision quality against actual outcomes, not merely more fields populated. No live session or economic acceptance was performed here.

## 6. BF-02 — direction adapter defensive follow-up

Use the existing governed direction owner/validator; do not build another side resolver. A missing directed side remains explicit unknown/unresolved. Compatible legacy aliases may be migrated only with labelled precedence; conflicts with a valid governed record need a deterministic reason and must not silently choose the first string.

Test missing keys, canonical PUT-only, authoritative PUT versus stale CALL alias, explicit UNRESOLVED/STRANGLE, LONG_PUT/LONG_CALL, NaN/whitespace, and same-ticker opposite-side/contract cases. Preserve current accepted records byte-for-byte where no repair is needed, including the schema meaning of `DIRECTION_CONFIRMED`. Use exact record/signal identity for merges or explicitly diagnose unsupported ambiguous input.

Expected effect on the 8,282 inspected rows is no direction change. On malformed/legacy inputs, eliminate the invented CALL or diagnose a conflict; this is a change in handling that needs its own approval and acceptance. No generic macro/phase side vote or new trade authority.

## 7. Agent integration — design included, no prompt/schema build

Use existing Interpreter/Challenger two-role, three-pass package; preserve blind independence and exact peer binding. Candidate is isolated, deployment proposed/unapproved, prior 39 synthetic passes are structure evidence only.

Outcome linkage reuses the post-close monitor as sole `monitor/option_closes.csv` writer and AVS-LEDGER-001 card outcomes; preserve default-disabled option capture. No parallel outcome writer. Learning means linking inputs, decisions and realised outcomes with validation, then proposing evidence-backed changes under existing authority gates. Bayesian updating alone is not autonomous outcome learning.

Backend first:
- A qualified direction record, source status, current forecast and IV assessment must exist before an agent can discuss them.
- Interpreter explains supplied direction and volatility relevance/limits. Challenger flags stale CALL aliases, unresolved-side claims, low-IVP-as-cheapness, missing tenor/quotes/costs and false-current claims.
- No agent calculates a missing GARCH/IV/price/outcome, decides a side or claims positive economics from a supplied percentile.

Acceptance fixtures proposed: canonical PUT with absent legacy keys; missing side with positive-looking macro; valid unresolved ticker with alternative thesis; stale source versus valid prior-close forecast; usable forecast/missing IV; short sampled IV history; stock right/option loses; missing exact contract or cost; same ticker/two thesis identities.

Current 50-fact context contract and all size/output/claim limits remain unchanged. If new direction/volatility facts are not qualified members of that packet, agents report unassessed. Prepare a separately approved versioned packet delta before numerical integration; do not replace original facts, inject the full register as market evidence or expand limits implicitly. Much of the existing SME mandate already forbids invention: prefer precise tests to redundant prompt text.

The agent candidate must not delay independently approved backend repair. No model/provider evaluation, deployment, scheduled hook, schema/persona edit or new agent is started by this brief.

## 8. Completion, rollback and review package

BF-00: six macro-completion and 16 cost tests pass with no production policy change, exact pre/post evidence.
BF-01: stage/identity/cutoff/coverage tests pass; actual consumed-current-forecast provenance and all IV-path states verified; no unintended population/direction/selection/permission change; saved-session comparison; forward/economic evidence required before authority expansion.
BF-02: malformed side fallback removed under existing owner, all inspected valid rows unchanged, conflicting/ambiguous identities explicit; display token and validator compatibility preserved.

Keep changes isolated against pinned baseline; no automatic commits, whole-tree staging, legacy deletions, data repair or provider-budget expansion. If an external source/config/HEAD changes, pause integration and reconcile. Rollback selects previous code/config version while preserving immutable snapshots/outcomes and displaying the prior limitation; do not delete data or rewrite decisions.

Review package: baseline receipt, original failure logs and fixture diagnostic, archived direction trace, source/helper characterisation, future failing tests/design, scoped change/diff and consumer-impact matrix, saved/forward acceptance and rollback. Every status stays separate: built, committed, wired, tested, validated, authorised.

**Ready for review only. No implementation has begun.**

## BF-03 dependency closure update

The detailed retirement design is now in [LEGACY_INTERPRETER_DECOMMISSION_PLAN_20261121.md](LEGACY_INTERPRETER_DECOMMISSION_PLAN_20261121.md), with source inventory, both Morning paths, shared contracts to preserve, macro projections, UI/API/launchers, paired runtime acceptance and agent integration. Read it with register section 13 before implementation. The earlier nine-point grouping was not exhaustive. Scope accepted; building and activation remain held.
