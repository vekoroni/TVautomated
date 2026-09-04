# AVS-SD-002 Revision 1.1 — Dynamic Session Orchestration

**Date:** 2026-09-03  
**Status:** FINAL DESIGN — validated against the current pipeline; implementation not started  
**Decision:** APPROVED WITH CONTROLLED MIGRATION  
**Scope:** Extend AVS-SD-002 and AVS-AR-003 so AVSHUNTER can be invoked safely at any time while preserving completed-session thesis construction and current-session validation.  
**Change authority:** Documentation only. No production code, configuration, database or run output was changed.

## 1. Executive decision

AVSHUNTER should become session-aware and dynamically invocable. The present requirement to run an “Evening” workflow after a fixed time is an implementation constraint, not a necessary trading principle.

The enhancement must not eliminate the completed-session checkpoint. It must convert EOD from a clock-time command into a governed evidence state:

```text
COMPLETED_SESSION = provider-confirmed observations for the last closed exchange session
DEVELOPING_SESSION = current-session observations that are still changing
```

The pipeline may then run before the open, during regular trading, after the close, on weekends or as a historical replay. Its behaviour is selected from the exchange session, provider availability, evidence cutoff and existing thesis state—not from the command name.

The two current functions remain intact:

1. **Thesis construction:** build and freeze a thesis from completed observations.
2. **Thesis validation:** compare current observations with that frozen thesis and determine whether it is confirmed, deferred, repriced or invalidated.

The Intelligence Orchestrator becomes the dynamic dispatcher. The Morning Gate becomes a session-aware Validation Gate, while retaining the existing `--morning` command as a compatibility alias during migration.

## 2. Relationship to the existing design

This revision is normative together with:

- `AVS-SD-002_DATA_INTELLIGENCE_AND_MARKET_PROFILE_LIFECYCLE_20260903.md`;
- `AVS-AR-003_AS_IS_PIPELINE_SHIPPABILITY_REVIEW_20260903.md`;
- `AVS-AR-003_GAP_REGISTER_20260903.csv`.

All authority, canonical-data, Market Profile, Lab, Interpreter, Decision and Outcome Ledger, backup and acceptance requirements remain in force.

This revision changes the operating model from two schedule-driven workflows to one session-driven lifecycle. It does not grant new authority to macro, Market Profile, EV, R:R, the Lab or the Interpreter.

## 3. Business outcome

The dynamic design improves data use in five ways:

1. Completed observations are acquired once, frozen and reused until a genuinely newer completed session exists.
2. Current-session observations are fetched incrementally rather than rebuilding the whole pipeline.
3. Data that is not yet observable is explicitly deferred rather than fabricated, defaulted or treated as stale.
4. A ticker dropped from the active worklist creates no subsequent provider requests.
5. Every change from completed thesis to current validation is recorded as an append-only transition.

For the user, the Intelligence Lab becomes a continuously accurate view of:

- what the thesis was based on;
- when the evidence was completed;
- what has changed since then;
- whether the change affects thesis validity, entry positioning or contract execution;
- which evidence is current, completed, developing, deferred or unavailable.

## 4. As-is validation against the current pipeline

### 4.1 Existing capabilities that make the design feasible

| Required capability | Current implementation | Assessment |
|---|---|---|
| Exchange session state | `canonical_data/session_clock.py` provides CLOSED, PREMARKET, REGULAR and AFTER_HOURS | Reuse |
| Last completed session | `SessionSnapshot.last_completed_session` | Reuse |
| Holiday, DST and early close | Shared XNYS functions and passing tests | Reuse, extend calendar governance |
| Semantic EOD freshness | `evaluate_freshness` distinguishes EOD current from live TTL freshness | Reuse, parameterise |
| Completed EOD preparation book | EOD Candidate Engine and governed final opportunity book | Reuse |
| Frozen Morning input | Morning requires `EOD_CANDIDATE_ONLY` authority | Reuse |
| Morning comparison and finalisation | `morning_gate.py` plus shared handoff finaliser | Refactor into Validation Gate |
| Canonical worklists and cache | CDS gateway, registry, request ledger and stage publisher | Reuse |
| Current-session canonical structure | Minute-bar resolver and Market Structure service | Parameterise and integrate |
| Lab current-run refresh | Cache signature and governed book resolver | Extend to validation revisions |
| Interpreter lineage | Hash-bound handoff and exact evidence resolver | Extend |

### 4.2 Current behaviour that is not the target design

The existing `--data-mode LATEST` is not a safe production substitute for dynamic orchestration:

- it still runs the full Evening workflow;
- it calls the output “Evening” and applies EOD thresholds to partial evidence;
- it may append a composite current-session bar to completed daily history;
- it does not model completed and developing evidence as separate identities;
- it can produce a review output without a governed lifecycle transition;
- it still depends on direct stage-local providers;
- the market-hours guard uses fixed clock arithmetic rather than the shared XNYS session clock;
- its comments say Morning confirmation should occur once the market closes, which confuses validation with session finalisation.

`LATEST` may remain a research compatibility mode until the dynamic path is accepted. It must not be promoted as the new production architecture.

### 4.3 Current command constraints

The current CLI exposes:

- `--evening`;
- `--morning`;
- deprecated `--premarket`;
- `--data-mode EOD|LATEST`;
- `--force` to bypass the market-hours guard.

There is no dynamic dispatcher. Morning requires a previous `morning_candidates_<run_id>.csv` or final opportunity book. This correctly preserves the thesis/validation relationship but prevents a single safe run-anytime entry point.

## 5. Design principles

### 5.1 Schedule and semantics are separate

The wall clock determines which observations may exist. It does not decide which calculations are valid. The session state and evidence cutoff decide that.

### 5.2 A completed thesis is immutable

Once published, completed-session evidence, direction, horizon, target, invalidation and selected-contract episode are never overwritten by a current refresh. A new completed session creates a new thesis version or superseding thesis episode.

### 5.3 Current evidence annotates; it does not rewrite history

Current price, current exact option quote and developing Market Profile are separate observations linked to the frozen thesis.

### 5.4 The full universe is not rerun unnecessarily

The dynamic dispatcher first determines whether a valid completed thesis already exists. If it does, only active candidates and required missing evidence enter current validation.

### 5.5 Freshness is domain-specific

A 1–20-day thesis horizon does not make a live quote valid for 1–20 days. Conversely, a quote older than 60 seconds does not automatically invalidate a 1–20-day thesis. The system must distinguish:

- thesis evidence currency;
- underlying entry-price currency;
- option quote executability;
- completed-session dataset currency;
- developing-profile completeness.

### 5.6 No future leakage

Every observation and calculation is constrained by `evidence_cutoff_utc`. Historical replay must produce the same decision using only evidence that existed at the cutoff.

## 6. Dynamic session state model

### 6.1 Exchange states

Retain the current XNYS session states:

- `CLOSED`;
- `PREMARKET`;
- `REGULAR`;
- `AFTER_HOURS`.

Add an operational context rather than overloading the exchange state:

- `NO_VALID_THESIS`;
- `THESIS_CURRENT`;
- `THESIS_REFRESH_DUE`;
- `VALIDATION_DUE`;
- `VALIDATION_CURRENT`;
- `CURRENT_SESSION_FINALISATION_DUE`;
- `REPLAY`.

### 6.2 Evidence states

Use explicit evidence states:

- `COMPLETED_SESSION`;
- `DEVELOPING_SESSION`;
- `PENDING_MARKET_OPEN`;
- `PARTIAL_SESSION`;
- `CURRENT_QUOTE`;
- `PRIOR_SESSION_QUOTE`;
- `DEFERRED_NOT_YET_OBSERVABLE`;
- `UNAVAILABLE_PROVIDER`;
- `DATA_DEFECT`;
- `SUPERSEDED`.

### 6.3 Thesis lifecycle

```text
NO_VALID_THESIS
  -> BUILDING_FROM_COMPLETED_SESSION
  -> EOD_PREPARED
  -> PREMARKET_VALIDATED
  -> RTH_VALIDATED / RTH_MONITORING
  -> COMPLETED_SESSION_FINALISATION
  -> SUPERSEDED_BY_NEXT_THESIS
```

Additional terminal or holding states:

- `THESIS_INVALIDATED`;
- `ENTRY_DEFERRED`;
- `CONTRACT_REPAIR_REQUIRED`;
- `DATA_INCOMPLETE`;
- `EXPIRED_UNTRADED`;
- `POSITION_OPEN`;
- `POSITION_CLOSED`.

Direction cannot change inside this lifecycle. If new evidence supports the opposite direction, the current thesis is invalidated or closed and a separately identified thesis may be created by the next construction cycle.

## 7. Identity model

The dynamic design requires identities with non-overlapping meanings:

| Identity | Meaning | Mutation rule |
|---|---|---|
| `pipeline_run_id` | One orchestration plan and its published artefacts | Immutable |
| `invocation_id` | One execution/retry/refresh attempt | New when scope or cutoff changes |
| `thesis_id` | Ticker thesis anchored to completed evidence and governed direction | Immutable; superseded append-only |
| `thesis_version` | Material completed-session refresh of the thesis | Monotonic |
| `validation_event_id` | One comparison of current evidence to a thesis | Append-only |
| `dataset_id` | Immutable canonical observation payload | Content-addressed |
| `evidence_id` | Versioned derived evidence and exact input IDs | Immutable |
| `contract_episode_id` | One exact OCC structure selected for a thesis | New when structure changes |
| `quote_observation_id` | One exact contract/underlying observation | Immutable |

The same invocation may be retried only when its inputs, worklist, cutoff and scope are identical. A changed worklist, session, interval or cutoff creates a new invocation linked through `supersedes_invocation_id` or `retry_of_invocation_id`.

## 8. Dynamic dispatcher

### 8.1 Input contract

The dispatcher receives or derives:

- `requested_action=AUTO|BUILD_THESIS|VALIDATE|FINALISE|REPLAY`;
- `as_of_utc`;
- `evidence_cutoff_utc`;
- `exchange_calendar=XNYS`;
- `session_snapshot`;
- optional explicit `thesis_id` or `pipeline_run_id`;
- universe/worklist policy;
- provider and canonical feature flags;
- replay/live authority mode.

### 8.2 Plan-only resolution

Before any provider request or output mutation, the dispatcher creates a `RunPlan`:

```text
RunPlan
  session state
  last completed session
  current session, if any
  existing thesis selected
  stages to run
  stages to reuse
  datasets required
  cache coverage
  authorised ticker worklists
  estimated physical requests/cost
  expected outputs
  execution authority ceiling
```

The plan is hashed and persisted before execution. The executed stages must reconcile to the plan.

### 8.3 AUTO decision table

| Condition | Dispatcher action |
|---|---|
| No valid thesis for last completed session | Build thesis from completed evidence |
| Valid thesis exists; market CLOSED before premarket | Reuse thesis; no unnecessary provider calls |
| PREMARKET | Validate underlying price/gap; mark profile pending; refresh option quote only for survivors if available |
| REGULAR | Validate underlying; fetch only missing current intervals; compute developing profile; refresh surviving contracts |
| AFTER_HOURS but provider has not finalised session | Continue PARTIAL/DEVELOPING state; do not call it completed |
| AFTER_HOURS and provider confirms final session | Finalise completed datasets and build/supersede thesis |
| Weekend/holiday | Use last completed session; do not invent a current session |
| Explicit replay | Use the supplied cutoff with all network acquisition disabled unless a replay fixture allows it |

### 8.4 Authority ceiling by mode

| Context | Maximum permitted output |
|---|---|
| Completed thesis without current validation | `EOD_PREPARED`, no live capital |
| Premarket underlying only | Confirm/defer/invalidate thesis; option entry still needs executable quote |
| Regular session with valid quote | Execution Gate may grant action after all hard checks |
| Partial/unknown data | Review/defer only |
| Replay | Research result only |

## 9. Dynamic thesis construction

The thesis builder retains the existing Evening functionality but becomes independent of when the command is entered.

1. Resolve `last_completed_session` from the shared session clock.
2. Check whether a complete accepted thesis already exists for that session and model version.
3. Reuse canonical daily history and fetch only the missing completed tail.
4. Run Discovery and freeze Direction Governance.
5. Publish the authorised survivor worklist.
6. Resolve completed-session intraday bars and completed Market Profile.
7. Run Vanguard with typed completed evidence.
8. Establish governed hold, target and invalidation.
9. Run Options selection using the governed thesis/horizon.
10. Publish advisory EV, GARCH, Wall Break and macro context.
11. Publish the immutable EOD opportunity book.
12. Record candidate decisions in the Decision and Outcome Ledger.

If the thesis already exists and every required input ID matches, the builder returns `REUSED_EXISTING_THESIS`; it does not rerun the universe or call providers.

## 10. Dynamic Validation Gate

### 10.1 Purpose

The Validation Gate preserves the Morning Gate’s business purpose:

> Determine whether current evidence confirms, weakens, reprices or invalidates the frozen thesis.

It does not rebuild Discovery, change direction or create an unrelated contract thesis.

### 10.2 Validation order

1. Resolve the exact frozen thesis and completed evidence.
2. Acquire/reuse current underlying price.
3. Calculate gap and movement from the completed close/entry reference.
4. Test target, invalidation, trigger and maximum-entry geometry.
5. If invalidated, stop later acquisition for the ticker.
6. If still valid, obtain/reuse the exact selected option quote.
7. Evaluate quote quality, spread, size and contract lifecycle.
8. During RTH only, obtain missing current-session bars and calculate developing profile.
9. Publish comparison evidence.
10. Invoke the existing final Execution Gate.
11. Rebuild the governed Lab/Interpreter handoff atomically.

### 10.3 Current price semantics

Current price is important but not always a thesis-level showstopper:

- a gap through invalidation invalidates;
- a gap beyond the safe entry/runway can defer or require repricing;
- a gap toward the target can make the original option unattractive without reversing direction;
- a modest price change may preserve the thesis while changing entry instructions;
- current option bid/ask determines immediate execution viability, not the lifetime of the thesis.

### 10.4 Developing profile

- Before RTH: compare current price to the frozen completed profile and publish `PENDING_MARKET_OPEN`.
- During RTH: calculate a separate `DEVELOPING_SESSION` profile from valid current bars.
- After close but before provider finalisation: keep the profile partial.
- After finalisation: persist the completed profile and allow a new thesis build.

The developing profile cannot overwrite the completed profile or reverse direction.

## 11. Canonical acquisition and reuse

### 11.1 Request planning

Every dynamic run builds requests from the authorised active worklist. For each ticker/dataset:

```text
exact cache hit
  -> reuse, physical_request_count=0
partial coverage
  -> coalesce and fetch missing scope only
not yet observable
  -> defer without provider request
provider/data error
  -> ticker exception
dropped/inactivated ticker
  -> no request
```

### 11.2 Domain policies

| Domain | Completed-session rule | Current-session rule |
|---|---|---|
| Daily OHLCV | Last completed session must be present | Partial daily bar stored separately |
| Intraday bars | Complete exchange session with quality metrics | Only closed intervals; developing/partial state |
| Option chain | True provider session and observed-at retained | Fetch only when the strategy needs chain-wide evidence |
| Exact option quote | Prior-session quote may support preparation | Current executable quote required for immediate entry |
| Underlying quote | Completed close anchors thesis | Current quote validates gap/entry |
| Macro | Point-in-time advisory snapshot | Refresh independently; never blocks core data flow |

### 11.3 Storage rule

Large observation payloads are stored once in the canonical payload store. Run artefacts contain dataset/evidence IDs, quality summaries and hashes—not duplicated full price histories.

## 12. Intelligence Lab behaviour

The Lab must display two time axes clearly:

1. **Frozen thesis:** completed-session date, direction, horizon, target, invalidation, contract and completed Market Profile.
2. **Current validation:** observation time, current price/gap, quote, developing profile, validation transition and final execution permission.

Required status banner examples:

- `THESIS PREPARED — CURRENT VALIDATION NOT RUN`;
- `PREMARKET VALIDATED — OPTION REQUOTE REQUIRED`;
- `THESIS CONFIRMED — EXECUTION VIABILITY PASSED`;
- `THESIS VALID — ENTRY RUNWAY EXHAUSTED`;
- `THESIS INVALIDATED BY OVERNIGHT GAP`;
- `RTH DEVELOPING PROFILE — ADVISORY`;
- `DATA DEFERRED — CURRENT SESSION NOT YET OBSERVABLE`.

The Lab must refresh when a new accepted validation event is published. It must not pick the newest folder solely by timestamp or fall back to an actionable legacy assembly.

## 13. Pipeline Interpreter behaviour

The Interpreter resolves the latest accepted validation event linked to the exact thesis and contract episode. It may explain:

- the completed thesis;
- what changed since the thesis cutoff;
- whether the current gap, quote or developing profile confirms or weakens it;
- what is missing and whether it matters to execution;
- why the Execution Gate allowed, limited, deferred, repaired or blocked the trade.

It does not independently call providers, change direction, replace contracts or grant capital. If a refresh is required, it returns a structured refresh request to the orchestrator. Screenshots remain supplemental for visual L2 evidence not available through the numerical providers.

## 14. Macro behaviour

Macro remains a separately refreshable advisory system.

- It may be updated before or after a thesis run.
- A new macro snapshot creates a new advisory evidence ID.
- Lab and Interpreter may show the newest compatible macro snapshot alongside the thesis.
- External macro does not force a full core rebuild unless an explicitly calibrated core feature—not the advisory narrative—has changed.
- Macro cannot admit/drop a candidate, reverse direction, select a contract or grant/remove capital.

The existing macro-agnostic corrections in AVS-AR-003 remain prerequisites for dynamic orchestration.

## 15. Failure and recovery rules

### 15.1 Per-ticker isolation

Normally isolate one ticker for:

- missing current quote;
- provider no-data response;
- invalid/crossed contract quote;
- unavailable current bars;
- contract repair failure;
- advisory profile failure.

### 15.2 Full-run abort

Abort the affected publication for:

- canonical registry/database unavailable;
- schema or authority violation;
- evidence identity collision;
- changed same-invocation worklist;
- population reconciliation failure;
- non-atomic final publication;
- broad provider outage above the configured threshold.

### 15.3 Idempotent restart

- Same plan hash, worklist, cutoff and inputs: resume/reuse without duplicate publication.
- Changed cutoff, session or worklist: create a linked invocation.
- Accepted prior outputs remain immutable.
- Failed evidence is retained for diagnosis and never promoted.

## 16. Current-pipeline impact map

| Component | Planned change | Preserved functionality |
|---|---|---|
| `intelligent_orchestrator.py` | Add dynamic dispatcher and stage plan; retain compatibility commands | Existing Evening stage implementations |
| `canonical_data/session_clock.py` | Use as sole clock; add governed calendar/version metadata if needed | Existing state/holiday/DST logic |
| New session orchestration contract | RunPlan, identities and state transition validation | No trading calculation authority |
| Canonical gateway/resolvers | Interval/session-aware planning and missing-only fetch | Immutable cache and request ledger |
| Discovery | Consume completed cutoff; no external macro membership authority | Direction Governance and survivor worklist |
| Vanguard/Profile | Completed/developing evidence separation | Advisory profile and actuarial processing |
| Options | Run after governed horizon; exact contract episodes | MarketData option-chain lifecycle |
| `morning_gate.py` | Refactor core into session-aware validation service | Gap/invalidation and execution checks |
| Execution Gate | Consume latest accepted validation event | Final action/capital authority |
| Lab | Show frozen/current axes and validation revisions | Governed source and defence-in-depth |
| Interpreter | Resolve accepted validation event; request refresh through orchestrator | Hash-bound read-only explanation |
| Decision/Outcome Ledger | Record thesis and validation transitions | Manual trade journal remains separate |

## 17. Implementation plan merged with AVS-SD-002

### Phase 0 — Release baseline and contract freeze

1. Establish reproducible source/dependency baseline.
2. Back up production files and consistent database snapshots.
3. Freeze authority, schema, session-state and identity contracts.
4. Capture accepted EOD/Morning baseline hashes and populations.
5. Verify restoration in an isolated location.

### Phase 1 — Session context and plan engine

1. Centralise all market-state decisions on `session_clock`.
2. Define `RunPlan`, `pipeline_run_id`, `invocation_id`, thesis and validation identities.
3. Implement plan-only resolution with zero provider/output changes.
4. Add session/cutoff/calendar to every canonical request.
5. Add idempotent retry and changed-scope linkage tests.

### Phase 2 — Authority and dynamic-safety prerequisites

1. Complete macro-agnostic Discovery/Vanguard/Horizon work.
2. Remove R:R authority and align monetisability/viability semantics.
3. Freeze direction/horizon/geometry identities.
4. Centralise quote spread/freshness definitions.
5. Make production Lab and Interpreter fail closed to governed evidence.

### Phase 3 — Canonical completed/developing observations

1. Build frame-preserving MarketData adapter.
2. Parameterise intraday resolver by interval/session.
3. Add completed versus developing dataset scopes.
4. Add request planning, missing-range coalescing and quota estimates.
5. Prevent downstream calls for inactive tickers.

### Phase 4 — Completed-session thesis builder

1. Convert the current Evening workflow into reusable `build_thesis(plan)` stages.
2. Insert completed Market Profile before Vanguard.
3. Correct Vanguard fail-open behaviour.
4. Use governed horizon before Options.
5. Publish immutable opportunity book and ledger decisions.

### Phase 5 — Dynamic Validation Gate

1. Extract Morning business logic into `validate_thesis(plan, thesis)`.
2. Enforce underlying-first, survivor-only option refresh.
3. Support PREMARKET, REGULAR and AFTER_HOURS partial states.
4. Add RTH developing profile without overwriting EOD.
5. Publish validation events and final Execution Gate results.

### Phase 6 — Dynamic dispatcher and compatibility commands

1. Add the production AUTO dispatcher only after Phases 1–5 pass.
2. Map `--evening` to explicit completed-thesis construction.
3. Map `--morning` to explicit validation of the selected thesis.
4. Retain `LATEST` as research-only until decommissioned.
5. Add plan preview and operator-readable action summary.

### Phase 7 — Lab, Interpreter and ledger

1. Display frozen/current evidence axes and lifecycle status.
2. Update hash-bound handoff for validation event identity.
3. Remove production Interpreter acquisition/substitution paths.
4. Complete append-only candidate, validation and outcome persistence.

### Phase 8 — Acceptance and promotion

1. Focused unit and contract tests.
2. Full regression suite.
3. Deterministic replay at fixed premarket, RTH, after-hours and weekend cutoffs.
4. Warm-cache and cold-cache request/runtime tests.
5. Fresh completed-thesis build.
6. Premarket validation.
7. RTH validation/developing profile.
8. After-hours finalisation.
9. Lab/Interpreter reconciliation.
10. Restore drill and controlled production promotion.

## 18. Test design

### 18.1 Session tests

- XNYS holiday, weekend, early close and DST boundaries.
- Before 04:00, premarket, regular, after-hours and closed states.
- Last completed session at every boundary.
- Provider-finalised session versus exchange-closed-but-not-yet-delivered session.

### 18.2 Dispatcher tests

- AUTO with no thesis builds once.
- AUTO with current thesis performs zero unnecessary full-universe work.
- PREMARKET never produces developing RTH profile.
- REGULAR only fetches closed missing intervals.
- AFTER_HOURS does not finalise before provider confirmation.
- Weekend uses Friday/last session and creates no phantom session.
- REPLAY prevents future/network leakage.

### 18.3 Identity and restart tests

- Same plan is idempotent.
- Changed cutoff creates a new invocation.
- Changed worklist cannot overwrite the prior invocation.
- Completed evidence and thesis hashes remain immutable through validation.
- Contract change creates a new contract episode.

### 18.4 Data reuse tests

- Exact cache hit means zero physical requests.
- Partial coverage fetches only missing ranges.
- Invalidated/dropped ticker makes no later requests.
- Full universe is not reacquired for validation.
- Run packages reference canonical payloads rather than duplicating them.

### 18.5 Authority tests

- Validation cannot reverse direction.
- Developing profile cannot grant capital.
- Macro, EV and R:R cannot upgrade/downgrade core authority.
- Execution Gate remains the sole final permission.
- Lab and Interpreter cannot upgrade or substitute.

### 18.6 Presentation tests

- Lab shows thesis session and current observation time separately.
- No “fresh” label without a real timestamp.
- No actionable row when governed book/handoff is absent.
- Interpreter resolves the exact thesis/validation/contract tuple.

## 19. Acceptance gates

The dynamic enhancement is shippable only when:

1. all AVS-AR-003 P0 blockers are closed;
2. one session clock governs all production entry points;
3. completed and developing observations have separate immutable identities;
4. AUTO plan selection is deterministic at fixed `as_of_utc`;
5. an existing current thesis is reused without a full rerun;
6. premarket performs no developing-profile fabrication;
7. RTH fetches only missing closed intervals;
8. after-hours finalisation waits for provider-confirmed completeness;
9. identical retry is idempotent and changed scope creates a linked invocation;
10. macro remains advisory and separately refreshable;
11. direction/horizon/geometry remain frozen through validation;
12. current underlying price can invalidate/defer/reprice but not reverse the thesis;
13. exact current option quote is required only for immediate execution authority;
14. Lab and Interpreter show the same accepted validation event;
15. all populations and physical provider requests reconcile;
16. fixed-cutoff replay contains no future data;
17. full regression has zero unexplained P0/P1 failures;
18. live completed, premarket, RTH and after-hours cycles pass;
19. runtime, API cost and disk growth meet the approved budget;
20. backup restoration is verified.

## 20. Documentation-to-code validation results

The design was tested statically against the active source and existing regression evidence.

### Confirmed compatible

- Session clock exposes all four required exchange states.
- Last-completed-session logic exists.
- XNYS DST, holiday and early-close tests exist and pass in the recorded suite.
- Semantic completed-session versus live freshness exists.
- Morning requires a governed EOD candidate and preserves the prior run ID.
- Morning capture reuses fetched evidence without a second provider client.
- Canonical cache/worklist, immutable identity and handoff tests exist.
- Lab/Interpreter handoff is hash-bound and rejects identity drift.

### Not implemented

- AUTO dynamic dispatcher;
- plan hash and plan-only resolution;
- explicit completed/developing dataset identity throughout the pipeline;
- provider-finalisation state;
- linked invocation identity for changed-scope Morning reruns;
- survivor-only current acquisition across the complete path;
- dynamic Lab selection by accepted thesis/validation event;
- full Decision and Outcome Ledger.

### Existing behaviour requiring replacement

- fixed 09:30–16:15 market-hours arithmetic in the Evening workflow;
- EOD/LATEST binary mode;
- partial composite bar mixed into daily package history;
- full Evening rerun for current-session review;
- hard-coded language that Morning must run at 09:45 ET;
- machine-local data/runtime assumptions described in AVS-AR-003.

Recorded design-foundation regression evidence remains **61 passed, 0 failed** in `design_validation_results.xml`. The broader as-is selection remains **239 passed, 2 environment-dependent failures** in `as_is_validation_results_20260903.xml`; direct launcher self-tests passed. These tests support feasibility but do not prove the unimplemented dynamic functionality.

## 21. Risks and controls

| Risk | Control |
|---|---|
| Partial bar treated as completed | Provider-finalisation and dataset completeness contract |
| Repeated full-universe calls | RunPlan cache diff and active-worklist restriction |
| Historical/current data mixed | Separate evidence IDs and cutoff enforcement |
| Mid-session thesis mutation | Immutable thesis plus append-only validation event |
| Morning rerun collision | New invocation for changed cutoff/scope |
| Excess API cost | Plan-time quota estimate and warm-cache gate |
| Stale quote confused with stale thesis | Domain-specific freshness states |
| Dynamic output shown as executable too early | Mode authority ceiling and Execution Gate |
| Lab selects newest incomplete run | Accepted thesis/validation pointer and hash checks |
| Future leakage in replay | Network disabled and cutoff assertions |

## 22. Deployment and rollback

Use independently reversible flags:

- session-aware plan engine;
- dynamic completed-thesis builder;
- dynamic Validation Gate;
- completed/developing profile lifecycle;
- Lab dynamic evidence view;
- Interpreter dynamic resolver;
- Decision and Outcome Ledger.

Promotion order:

1. plan-only reporting;
2. explicit BUILD_THESIS and VALIDATE commands using the new contracts;
3. Lab/Interpreter dynamic view;
4. AUTO dispatcher;
5. retirement of fixed market guard and research `LATEST` production use.

Rollback disables the affected dispatcher/flag and returns to the last accepted completed thesis and Morning compatibility command. It does not delete failed invocation evidence or restore over accepted append-only records.

## 23. Final recommendation

Build this enhancement after the AVS-AR-003 release baseline and authority prerequisites are established. It will materially improve canonical reuse, reduce unnecessary API calls, preserve the information developed during the day and allow AVSHUNTER to be invoked safely at any time.

The design must be described as **dynamic session orchestration**, not as “run the Evening pipeline at any time.” The latter would preserve the present partial-data ambiguity. The approved design preserves a completed-session thesis, adds incremental current validation and lets the session clock determine what the data can truthfully support.

No implementation should be claimed shippable until the four real operating transitions—completed session, premarket, RTH and after-hours finalisation—have all been exercised and reconciled.
