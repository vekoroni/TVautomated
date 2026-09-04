# AVS-SD-002 — Data Intelligence and Market Profile Lifecycle

**Status:** FINAL v1.0 — design validated against the current pipeline; implementation not started  
**Date:** 2026-09-03  
**Decision:** APPROVE WITH REQUIRED CHANGES  
**Scope:** Merge the canonical data/reuse roadmap with the completed-session and developing-session Market Profile enhancement plan.

## 1. Executive decision

The combined enhancement is feasible and should be built. It addresses a real data and logic defect rather than adding another independent trading model.

The present pipeline has a sound canonical-data foundation, governed direction, horizon, option lifecycle, execution authority, Intelligence Lab handoff and advisory Market Structure service. The missing connection is a valid intraday observation path between Discovery and Vanguard. Today, Vanguard groups daily OHLCV by date and asks its legacy Market Profile calculator to process each one-row group as intraday data. Every current Vanguard row therefore receives `INSUFFICIENT_DATA` and zero POC/VAH/VAL, while 995 of 1,449 rows can still be labelled `ALIGNED` and `ready_to_trade=True`.

The solution is not to create another general database or another Market Profile engine. It is to:

1. extend the Canonical Data Store to preserve interval-aware MarketData intraday candles;
2. calculate a governed completed-session profile after Discovery and before Vanguard;
3. pass that profile into Vanguard through a dedicated typed packet;
4. use Morning Gate to compare fresh price with the frozen EOD profile and, only after market open, calculate a developing profile;
5. expose the lineage, quality, uncertainty and EOD-to-morning change in the Intelligence Lab and Pipeline Interpreter;
6. append every candidate decision and matured outcome to a Decision and Outcome Ledger.

Market Profile remains advisory structural evidence. It cannot reverse CALL/PUT direction, determine capital permission or override the Execution Gate.

## 2. Plans merged by this design

### Plan A — Canonical data intelligence and reuse

- Capture provider observations once and reuse them by exact identity.
- Fetch only missing data intervals.
- Prevent a ticker dropped at one stage from creating later provider requests.
- Resolve required fields through a governed hierarchy instead of blanks, fabricated values or silent aliases.
- Preserve point-in-time lineage, calculation version and uncertainty.
- Measure evidence sequences, decisions, rejected candidates and 1/5/10/20-session outcomes.

### Plan B — Market Profile lifecycle

- Calculate the completed-session Market Profile after Discovery and before Vanguard.
- Freeze the EOD profile as part of the thesis evidence.
- At premarket Morning Gate, locate the current price and overnight gap relative to the frozen value area.
- Calculate a developing-session profile only when regular-session intraday bars actually exist.
- Let the Pipeline Interpreter explain the difference between EOD and morning evidence.

### Merged result

Both plans share one acquisition, identity and persistence contract. Market Profile becomes one governed derived dataset in the canonical system, while the Decision and Outcome Ledger records what the pipeline decided and what subsequently happened.

## 3. Goals and non-goals

### 3.1 Goals

- Give Vanguard structurally valid Market Profile evidence.
- Make the EOD book a complete, explainable thesis rather than a partially populated morning placeholder.
- Make Morning Gate test what changed overnight without silently rebuilding the EOD thesis.
- Make the Intelligence Lab the complete trader-facing source of governed evidence.
- Eliminate repeated provider calls for the same ticker, interval and observation scope.
- Ensure missing information is sourced, computed, explicitly deferred or recorded as a named exception.
- Measure signal development and outcomes using point-in-time evidence.
- Preserve the working authority boundaries and existing pipeline behaviour outside this enhancement.

### 3.2 Non-goals

- Market Profile will not choose CALL or PUT.
- Macro will not grant or remove capital permission.
- The Pipeline Interpreter will not become a second execution engine or an independent data acquirer.
- No calibrated probability or hard trading threshold will be invented without outcome evidence.
- The enhancement will not combine all raw data, decisions and journal records into one uncontrolled database.
- The enhancement will not attempt to predict genuinely random events.

## 4. Current-state evidence

### 4.1 Latest production-shaped run

The latest inspected run is `20260902_232526`:

| Measure | Observed |
|---|---:|
| Pipeline technical status | PASS |
| Semantic health | DEGRADED |
| Vanguard rows | 1,449 |
| Options / EIL rows | 1,274 |
| Final opportunity-book rows | 179 |
| Final CALL / PUT | 104 / 75 |
| Final 1–5d / 6–10d holds | 115 / 64 |
| Final rows missing `invalidation_spot` | 127 |
| Governed `ms_*` fields in final book | 0 |

Across all 1,449 Vanguard rows:

- `profile_type=INSUFFICIENT_DATA` for 1,449;
- POC, VAH and VAL are `0.0` for 1,449;
- `auction_state=ALIGNED` for 995;
- `ready_to_trade=True` for 995.

This proves the current auction readiness label can be issued without usable profile evidence.

### 4.2 Root cause in current code

1. `scripts/run_vanguard_from_packages.py` and `vanguard/integration/orchestrator_adapter.py` populate `TechnicalData.ohlcv` with daily history.
2. `vanguard/layer1_auction/auction_synthesizer.py` groups those rows by date and calls the legacy profile calculator with `timeframe="intraday"`.
3. Each group contains one daily bar.
4. `vanguard/layer1_auction/market_profile.py` requires at least 13 bars, so it returns insufficient status and zero levels.
5. `AuctionStateSynthesizer._determine_verdict` does not require a usable profile before returning `ALIGNED`.
6. Layer 2 and trade-building code subsequently consume that misleading alignment.

### 4.3 Existing components to retain

| Existing capability | Retained role |
|---|---|
| `canonical_data/contracts.py` | Dataset types and canonical identities |
| `canonical_data/intraday_bars.py` | Immutable intraday storage, cache reuse and missing-range resolution |
| `canonical_data/stage_publisher.py` | Authorised worklists and dropped-ticker protection |
| `market_structure/profile.py` | Single deterministic profile calculation engine |
| `market_structure/service.py` | Advisory-only evidence publication |
| Direction Governance | Sole CALL/PUT authority |
| Horizon Router | Sole planned-hold authority |
| Option Liquidity Lifecycle | Contract maturation and executability evidence |
| Execution Gate | Final action and capital authority |
| Intelligence Lab | Governed trader-facing presentation |
| Pipeline Interpreter | Read-only explanation and refreshed comparison |
| Trade Journal | Executed/manual trade record |

## 5. Required architectural corrections

### 5.1 Preserve intraday bars instead of collapsing them

`scripts/backfill_timeseries_into_packages.py` already requests MarketData five-minute candles, but collapses the returned sequence into one composite record. Market Profile needs each interval with its timestamp and volume. A new adapter must normalise and persist the full candle frame.

### 5.2 Make the canonical intraday resolver interval-aware

`canonical_data/intraday_bars.py` currently hard-codes `1min` scope and minute-frequency expected timestamps. It must accept `interval_minutes` and use that interval in:

- request identity;
- dataset scope;
- expected timestamp calculation;
- schema version;
- cache matching;
- completeness assessment;
- missing-interval retrieval.

### 5.3 Replace the hard-coded Morning Polygon path

`morning_gate.py` currently invokes the canonical resolver with a Polygon minute callback. The resolver must receive an approved provider adapter selected by configuration. MarketData is the intended stock-candle provider, subject to an authenticated entitlement and latency preflight.

### 5.4 Add an EOD Market Profile stage

The correct insertion boundary is after Discovery has authorised the survivor worklist and daily packages have been completed, but before Vanguard runs. Only authorised tickers may create intraday requests.

### 5.5 Give Vanguard a separate profile packet

Do not add intraday rows to `TechnicalData.ohlcv`. Extend `VanguardInput` with a `MarketProfileEvidence` packet and adapt it into the existing auction result during migration.

### 5.6 Remove fail-open auction readiness

Mandatory invariant:

```text
profile not usable
  => auction_state = NOT_EVALUATED
  => ready_to_trade = False
  => auction confidence/uplift = 0
  => no POC/VAH/VAL scenario fallback
```

The profile field values must remain null when unavailable. Zero is a valid price only when it is an actual measurement; it cannot represent missing evidence.

### 5.7 Correct cadence classification

The modern profile engine currently labels valid 15-minute input as `ONE_MINUTE_ESTIMATED`. Cadence must be derived from timestamps or the governed interval field. Existing characterization tests that demonstrate the defect must be converted into acceptance tests after the fix.

## 6. Target architecture and data flow

```text
Canonical daily observations
        |
Discovery and Direction Governance
        |
Authorised survivor worklist
        |
Canonical intraday resolver
  cache hit -----------------------> reuse exact dataset
  partial coverage ----------------> fetch missing intervals only
  provider unavailable ------------> named exception
        |
Completed-session Market Profile
        |
Vanguard consumes typed profile packet
        |
Options Intelligence + Horizon + lifecycle
        |
Frozen EOD opportunity book
        |
Morning Gate
  fresh underlying price
  gap/thesis validation
  developing profile only after RTH begins
        |
EOD-versus-morning comparison
        |
Execution Gate
        |
Intelligence Lab
        |
Pipeline Interpreter explanation
        |
Decision and Outcome Ledger
```

### 6.1 Evening flow

1. Create the run identity and canonical stage worklists.
2. Acquire/reuse canonical daily observations.
3. Run Discovery and freeze survivor/drop outcomes.
4. Publish the Market Profile worklist from survivors only.
5. Resolve the latest provider-available completed session for each ticker.
6. Reuse exact cached intraday data; fetch only missing intervals.
7. Validate session, interval, timestamps, duplicates, OHLCV and coverage.
8. Compute and persist the completed-session profile.
9. Pass a hash-bound profile packet to Vanguard.
10. Freeze the EOD thesis, contract and profile evidence in the opportunity book.
11. Record processed, deferred and exception counts.

If the user’s MarketData entitlement is one-day delayed, the profile must state the true source session. It must not be labelled current simply because it was acquired during the current run.

### 6.2 Premarket Morning Gate

Before the regular session opens:

- obtain/reuse the current underlying price;
- calculate the overnight gap from the frozen EOD close;
- locate price relative to EOD POC/VAH/VAL;
- test existing thesis invalidation and trigger rules;
- publish profile lifecycle state `PENDING_MARKET_OPEN`;
- do not fabricate a developing regular-session profile.

### 6.3 Regular-session Morning Gate or refresh

When current regular-session bars exist:

- resolve only the new intervals;
- compute a `DEVELOPING_SESSION` profile;
- compare it with the frozen EOD completed profile;
- publish change evidence and uncertainty;
- preserve EOD evidence unchanged;
- allow only the existing thesis/execution authorities to change action or capital.

### 6.4 Pipeline Interpreter

The Interpreter receives a hash-bound handoff containing EOD evidence, Morning Gate evidence and advisory macro. It may explain:

- whether price gapped outside value;
- whether developing value is migrating;
- whether price is accepted or rejected around a wall/value boundary;
- whether the current evidence confirms or contradicts the frozen thesis;
- which evidence is stale, missing or uncertain.

It must not call a provider independently, select direction, replace the contract or grant capital. Screenshot evidence remains available for visual Level 2/order-book context not supplied by the current APIs.

## 7. Authority matrix

| Concept | Sole authority | Prohibited overrides |
|---|---|---|
| Raw observations | Canonical Data Store | Stage-local rewrites |
| CALL/PUT direction | Direction Governance | Macro, Market Profile, Lab, Interpreter |
| Hold horizon | Horizon Router | Legacy aliases/defaults |
| Thesis validity | Morning thesis/lifecycle authority | Market Profile direct mutation |
| Contract selection | Options Intelligence / contract lifecycle | UI or Interpreter substitution |
| Final action/capital | Execution Gate | Macro, EV, profile or Interpreter upgrade |
| Macro | Advisory macro contract | GO/NO-GO capital authority |
| Market Profile | Advisory structural evidence | Direction/capital authority |
| Outcomes | Decision and Outcome Ledger | Retrospective source mutation |

## 8. Canonical data contracts

### 8.1 Intraday bar contract

Required fields:

| Field | Rule |
|---|---|
| `ticker` | Canonical symbol |
| `session_date` | Exchange-local trading session |
| `timestamp_utc` | Unique within ticker/session/interval |
| `open/high/low/close` | Finite, positive, internally consistent |
| `volume` | Non-negative |
| `interval_minutes` | Explicit; never inferred downstream |
| `session_segment` | RTH or approved extended-hours segment |
| `adjustment_convention` | Explicit split/corporate-action treatment |
| `provider` | Actual observation provider |
| `observed_at` | Acquisition timestamp |
| `dataset_id/content_hash` | Immutable identity and content proof |
| `completeness_status` | Governed quality state |

Recommended first implementation: five-minute MarketData candles preserved individually. Final interval selection is conditional on entitlement, source-session availability and cost preflight. Expected RTH counts must be derived from the exchange calendar: normally 78 five-minute, 26 fifteen-minute or 13 thirty-minute observations, adjusted for early close.

### 8.2 Market Profile packet

Required fields:

- evidence identity, input dataset IDs and calculation version;
- ticker, session date, as-of timestamp and interval;
- profile lifecycle and quality state;
- POC, VAH, VAL and value midpoint;
- profile type, shape and value-area method;
- coverage ratio, missing intervals, duplicate count and maximum gap;
- source/freshness/adjustment status;
- advisory relationship to governed direction;
- uncertainty vector;
- no direction, action or capital fields.

### 8.3 Profile lifecycle states

- `COMPLETED_SESSION`
- `DEVELOPING_SESSION`
- `PENDING_MARKET_OPEN`
- `PARTIAL_SESSION`
- `COARSE_INTERVAL`
- `UNAVAILABLE_PROVIDER`
- `INSUFFICIENT_DATA`
- `DATA_DEFECT`
- `SUPERSEDED`

Cadence is separate:

- `ONE_MINUTE_ESTIMATED`
- `FIVE_MINUTE_ESTIMATED`
- `FIFTEEN_MINUTE_TPO`
- `THIRTY_MINUTE_TPO`

### 8.4 Missing-data resolution contract

Every required field follows this sequence:

```text
exact canonical cache
  -> compute from valid canonical input
  -> primary provider fetch
  -> approved fallback
  -> named exception/defer
```

Every resolution also records one origin:

- `CACHE_HIT`
- `COMPUTED_FROM_CANONICAL`
- `PROVIDER_FETCH`
- `APPROVED_FALLBACK`
- `UNRESOLVED_EXCEPTION`

Rules:

- EOD thesis-critical missing data defers the ticker.
- Morning execution-critical missing data prevents execution.
- Advisory profile unavailability does not erase an otherwise valid swing thesis, but it cannot create auction uplift.
- The UI must render the state and reason, not a blank cell or fabricated zero.
- Every input reconciles to processed, excluded, deferred or exception.

## 9. Quantitative specification

### 9.1 Profile calculation

Retain the modern `market_structure/profile.py` implementation as the sole engine:

```text
bin_width = round_to_tick(max(exchange_tick, ATR14 / bin_divisor))
```

- Calculate TPO count over configured periods.
- Select POC deterministically from the maximum-TPO bin.
- Expand around POC until 70% of TPO is captured for the value area.
- Estimate volume across touched bins only when the method is disclosed.
- Preserve null values when required input is insufficient.

### 9.2 Completeness and change measures

```text
coverage_ratio = observed_expected_timestamps / expected_timestamps

value_mid = (VAH + VAL) / 2

gap_ATR = (morning_price - completed_close) / ATR14

POC_move_ATR = (POC_new - POC_prior) / ATR14

value_mid_move_ATR = (value_mid_new - value_mid_prior) / ATR14

value_area_overlap =
  max(0, min(VAH_1, VAH_2) - max(VAL_1, VAL_2))
  / max(epsilon, max(VAH_1, VAH_2) - min(VAL_1, VAL_2))
```

Sequence features over valid completed sessions:

```text
POC_slope_ATR = OLS_slope(POC over session index) / ATR14
VA_mid_slope_ATR = OLS_slope(value_mid over session index) / ATR14
```

Publish continuous values and sample counts first. Do not turn them into hard GO/NO-GO thresholds until validated against outcomes.

### 9.3 Relationship states

Market Profile may publish:

- `CONFIRMING`
- `CONTRADICTING`
- `NEUTRAL`
- `INSUFFICIENT_EVIDENCE`

These are evidence descriptions, not decisions.

### 9.4 Shock and uncertainty treatment

The pipeline cannot predict a random event. It can detect an observation outside recent behaviour:

```text
robust_z = (x - median(window)) / (1.4826 * MAD(window))
```

Apply it separately to returns, log volume, realised volatility and correlation residuals. Publish non-directional states such as:

- `NORMAL_VARIATION`
- `PRICE_SHOCK`
- `VOLUME_SHOCK`
- `VOLATILITY_SHOCK`
- `CORRELATION_BREAK`
- `OUT_OF_DISTRIBUTION`

A shock increases uncertainty and can require review; it does not choose CALL or PUT.

### 9.5 Uncertainty vector

Do not compress all uncertainty into one opaque score. Preserve:

1. **Data uncertainty:** coverage, missing intervals, max gap, hash integrity, staleness and adjustment state.
2. **State uncertainty:** direction winning share, margin, evidence-family count and contradictions.
3. **Model uncertainty:** model dispersion, availability, calibration version and out-of-distribution status.
4. **Outcome uncertainty:** sample size, quantiles, fallback depth and first-passage evidence.
5. **Execution uncertainty:** quote age, spread, displayed size, OI/volume and liquidity state.

The Lab may show a concise worst-component summary, while retaining the complete vector for inspection.

## 10. Decision and Outcome Ledger

### 10.1 Separation of concerns

- **Canonical Data Store:** immutable raw observations and derived evidence datasets.
- **Decision and Outcome Ledger:** append-only candidate decisions, transitions and outcomes referencing canonical dataset IDs.
- **Trade Journal:** entered and manually managed positions.

### 10.2 Recommended append-only tables

- `candidate_episodes`
- `evidence_snapshots`
- `state_transition_events`
- `decision_events`
- `contract_episode_links`
- `data_exception_events`
- `outcome_path_observations`
- `calibration_runs`

Every accepted, rejected and deferred candidate is recorded. A retry reuses identity or appends a superseding event; it never mutates history silently.

### 10.3 Outcome labels

For direction `s=+1` for CALL and `s=-1` for PUT:

```text
directional_return_h = s * (price_h / reference_price - 1)

MFE_h = max(s * (price_t / reference_price - 1)), 0 < t <= h

MAE_h = min(s * (price_t / reference_price - 1)), 0 < t <= h
```

Record at 1, 5, 10 and 20 completed sessions:

- close return;
- MFE and MAE;
- target/stop first hit and session count;
- path maximum/minimum;
- evidence/profile state at decision time;
- contract return only when the exact OCC contract has valid point-in-time quotes.

An outcome remains `PENDING` until its horizon genuinely matures. Rejected candidates receive the same counterfactual underlying outcome labels so the pipeline can measure opportunity cost and false negatives.

## 11. Intelligence Lab requirements

The Lab is the user’s complete operating surface. For each ticker it must show or make inspectable:

- frozen EOD thesis, direction, horizon and contract;
- current action and capital permission from the actual authority;
- completed profile POC/VAH/VAL and source session;
- morning price and gap relative to value;
- developing profile only when available;
- profile relationship and movement;
- data origin, age, quality and uncertainty;
- contract quote timestamp and lifecycle state;
- plain-language reason for every missing/deferred field;
- exact run/dataset/evidence identities.

The Lab cannot upgrade an action. If evidence lineage or required stage completion cannot be proven, it must not display the row as executable.

## 12. Exception and reconciliation behaviour

Per-ticker provider or data defects must normally isolate that ticker rather than abort the complete run. A full-stage abort remains appropriate for:

- registry/database unavailability;
- schema or authority-contract violation;
- identity collision affecting correctness;
- widespread provider failure above the configured stage threshold;
- population reconciliation failure;
- non-atomic publication.

Required stage identity:

```text
input_count = processed + excluded + deferred + exception_count
```

Each exception contains ticker, stage, dataset type, reason code, provider attempt, recoverability and next eligible retry.

The worklist for a published run/stage is immutable. A restart with the same run ID must reuse the original membership and scope. If the desired ticker set, session or interval has changed, the orchestrator must create a new invocation identity linked to the prior attempt; it must not silently alter the same-run worklist.

## 13. Implementation workstreams

### Phase 0 — Freeze, backup and contracts

- Freeze the field/authority contract and feature flags.
- Record the reproducible source SHA or create a controlled release baseline from the dirty tree.
- Back up affected production files, canonical registry/databases and lifecycle stores.
- Capture the latest EOD replay baseline and expected row hashes.
- Add central enums for profile lifecycle, cadence, origin and exception reasons.
- Define rollback commands and restoration verification before code changes.

### Phase 1 — Data foundation

- Parameterise `canonical_data/intraday_bars.py` by interval.
- Build the MarketData candle-frame adapter without session collapse.
- Add entitlement, latency, credit-cost and latest-session preflight.
- Add a quota estimator and explicit concurrency/retry/rate-limit budgets for the post-Discovery population.
- Add exchange-calendar-derived expected timestamps.
- Add validation for duplicates, gaps, order, OHLC consistency, corporate actions and partial sessions.
- Prove exact cache reuse and missing-interval-only acquisition.

### Phase 2 — Profile engine and lifecycle

- Extend the modern profile engine with correct cadence classification.
- Add completed/developing/pending/partial quality states.
- Add deterministic EOD-to-morning comparison and sequence features.
- Add uncertainty vector and anomaly evidence.
- Keep all output advisory-only.

### Phase 3 — EOD integration

- Publish an authorised profile worklist after Discovery.
- Insert Market Profile before Vanguard in `intelligent_orchestrator.py`.
- Persist profile evidence and run-level reconciliation.
- Defer/except individual tickers without losing unrelated candidates.

### Phase 4 — Vanguard correction

- Extend `VanguardInput` with `MarketProfileEvidence`.
- Remove daily-as-intraday calculation from the active path.
- Route the modern governed profile packet to the auction layer.
- Enforce unusable-profile => `NOT_EVALUATED`, no readiness and no uplift.
- Remove zero-level percentage fallbacks from profile-dependent scenarios.
- Quarantine the legacy calculator after parity/acceptance.

### Phase 5 — Morning lifecycle

- Replace hard-coded Polygon callback with configured canonical provider adapter.
- Preserve the frozen EOD profile.
- Add premarket price/value/gap comparison with `PENDING_MARKET_OPEN`.
- Add developing profile only during RTH with valid current bars.
- Reuse the EOD dataset and fetch only new intervals.
- Preserve existing thesis and execution authority.

### Phase 6 — Lab and Interpreter

- Carry profile and uncertainty fields through the opportunity book and evidence overlay.
- Extend the hash-bound Interpreter handoff.
- Render completed/developing profiles, source dates, quality and reasons in the Lab.
- Add plain-language profile comparison to the Interpreter.
- Retain screenshot input only for visual evidence not supplied by the APIs.

### Phase 7 — Decision and Outcome Ledger

- Add append-only ledger schema and idempotent/supersession writers.
- Record every candidate at EOD and every subsequent transition.
- Schedule 1/5/10/20-session underlying outcomes.
- Link exact contract episodes when contract quote history permits.
- Build calibration reports without giving the ledger live authority.

### Phase 8 — Acceptance and promotion

- Run focused unit and contract tests.
- Run the complete regression suite.
- Replay the latest production-shaped EOD run.
- Explain every changed Vanguard/action result.
- Run a fresh evening cycle.
- Run premarket Morning Gate and, separately, an RTH developing-profile validation.
- Verify Lab and Interpreter lineage.
- Promote behind controlled flags, then remove the legacy path after the observation window.

## 14. Test design and acceptance gates

### 14.1 Data and cache tests

1. Five-, fifteen- and thirty-minute frames preserve every interval.
2. Full, early-close, partial, duplicate, out-of-order and gapped sessions classify correctly.
3. Split/corporate-action handling is explicit and reproducible.
4. Exact dataset reuse causes zero physical provider requests.
5. Partial coverage fetches only missing intervals.
6. A dropped ticker creates zero later provider calls.
7. Provider failure records a ticker exception and does not stop unrelated tickers.
8. Provider-reported session, observation time and acquisition time remain distinct.
9. A same-run restart reuses its frozen worklist; changed scope requires a new linked invocation.

### 14.2 Profile tests

1. Daily-only input cannot produce a usable intraday profile.
2. Missing POC/VAH/VAL remain null, not zero.
3. Cadence classification matches actual/configured intervals.
4. POC/value calculation is deterministic under input ordering.
5. Coarse input cannot claim minute-accurate acceptance metrics.
6. Premarket state is `PENDING_MARKET_OPEN`.
7. Valid RTH bars produce `DEVELOPING_SESSION`.
8. The EOD profile is immutable during morning processing.
9. Profile cannot mutate direction, action, capital or thesis state.

### 14.3 Vanguard tests

1. One daily bar cannot produce `ALIGNED`.
2. Unusable profile forces `NOT_EVALUATED`, readiness false and zero uplift.
3. Usable governed packet populates the auction layer without recalculation.
4. Profile-dependent scenarios do not replace null levels with percentages.
5. All 1,449 latest-baseline rows reconcile with explicit changed-result reasons.

### 14.4 Ledger and handoff tests

1. Writes are append-only and restart-idempotent.
2. Superseding events retain the old evidence.
3. Rejected/deferred candidates mature into counterfactual outcomes.
4. Contract changes open a new episode and recompute contract-specific fields.
5. Lab and Interpreter receive exact hash-bound identities.
6. Interpreter source contains no direct provider client or HTTP call.
7. Macro/profile overlays cannot replace authority fields.

### 14.5 Production acceptance gates

Promotion requires all of the following:

- zero P0/P1 test failures;
- no unexplained population loss;
- no missing-as-zero profile values;
- no daily-only `ALIGNED` auction result;
- 100% authority invariant pass;
- exact cache-hit and request-ledger reconciliation;
- explicit provider entitlement/latest-session evidence;
- cold-cache and warm-cache API/runtime measurements within the agreed operating budget;
- complete EOD replay diff with approved reasons;
- one successful fresh Evening run;
- one successful premarket Morning Gate;
- one successful RTH developing-profile test;
- Lab and Interpreter evidence lineage verified;
- backup restore drill verified.

## 15. Validation performed before finalising this design

### 15.1 Static interface validation

The proposed design was checked against the current implementation and is compatible with the existing extension points:

| Design need | Current evidence | Result |
|---|---|---|
| Canonical intraday dataset | `DatasetType.INTRADAY_BAR` exists | Reuse |
| Derived structure dataset | `DatasetType.MARKET_STRUCTURE` exists | Reuse |
| Cache and missing-range resolution | `CanonicalMinuteBarResolver` exists | Parameterise |
| Dropped-ticker protection | Governed stage worklist exists | Reuse |
| Single modern profile engine | `market_structure/profile.py` exists | Extend |
| Advisory authority | `market_structure/service.py` explicitly denies capital/direction authority | Preserve |
| EOD insertion point | Gap exists between package completion and Vanguard | Feasible |
| Morning comparison point | Morning Gate already calls the structure service | Replace provider and add lifecycle |
| Lab overlay | `ms_*` allow-list and UI components exist | Extend |
| Interpreter handoff | Hash-bound materializer/resolver exists | Extend |
| Outcome persistence | Journal and lifecycle patterns exist | Add separate ledger |

### 15.2 Executed regression evidence

The following current suites were executed together before design finalisation:

- `tests/test_canonical_data_system.py`
- `tests/test_msi_agent1_data_foundation.py`
- `tests/test_msi_market_structure_identity.py`
- `tests/test_msi_morning_capture.py`
- `tests/test_msi_handoff_materializer.py`
- `tests/test_msi_interpreter_handoff.py`
- `tests/test_vanguard_production_fixes.py`

Result: **61 passed, 0 failed, 0 errors, 0 skipped** in 48.987 seconds. Evidence: `audit/pipeline_map/design_validation_results.xml`.

This proves the current canonical identities, caching, worklist controls, Morning capture reuse, handoff integrity, advisory overlay and selected Vanguard production fixes form a usable foundation. It does not prove the new enhancement, because its new design-specific tests and live cycles do not exist yet.

### 15.3 Explicitly unvalidated assumptions

- The authenticated MarketData plan’s candle entitlement, delay and credit behaviour were not exercised to avoid unapproved API cost.
- No post-enhancement EOD or Morning artefact exists.
- The repository is currently dirty and not attributable to a clean reproducible release SHA.
- The current fifteen-minute cadence defect remains active until Phase 2.
- The 127 missing final-book invalidation values are outside the direct Market Profile implementation but remain a production acceptance concern.

## 16. Backup, deployment and rollback

### 16.1 Backup

Before implementation:

- hash and copy every affected production file into a dated release backup;
- take consistent copies of the canonical registry, lifecycle databases and current Lab store, including SQLite WAL/SHM handling;
- preserve the latest opportunity book, manifest and request ledgers;
- record source commit/tree state and environment configuration without secrets;
- test restoration into an isolated directory.

### 16.2 Feature flags

Use separately reversible flags:

- interval-aware intraday resolver;
- EOD profile acquisition;
- Vanguard governed-profile adapter;
- Morning profile lifecycle;
- Lab/Interpreter profile presentation;
- Decision and Outcome Ledger.

### 16.3 Rollback triggers

Rollback or disable the affected flag if any of the following occurs:

- authority mutation by Market Profile or macro;
- canonical identity collision or immutable-content conflict;
- unreconciled candidate/provider counts;
- missing profile represented as zero;
- repeat provider calls on exact cache hits;
- daily-only profile yields executable alignment;
- Lab presents an unlineaged row as executable;
- material runtime increase beyond the agreed budget;
- regression or live-cycle P0/P1 failure.

Rollback returns to the previous evidence path and restores databases from the verified backup; it must not delete the failed run evidence.

## 17. Maximum-agent rapid-development model

The maximum safe concurrent team for this repository is **four agents total: one integration lead plus three bounded specialist agents**. This is also the maximum available concurrency for the proposed build. Adding more parallel writers would increase merge and semantic-conflict risk in shared orchestration and contract files.

### 17.1 Ownership rules

- The integration lead alone edits shared schemas and performs production promotion.
- No two agents edit `intelligent_orchestrator.py`, `morning_gate.py`, `contracts/lab_control.py` or a shared schema concurrently.
- Each worker receives explicit file ownership, inputs, outputs and acceptance tests.
- Workers do not promote code; they return patches and evidence to the lead.
- An independent worker must test each integration boundary they did not implement.

### 17.2 Wave 1 — foundation

| Agent | Responsibility |
|---|---|
| Integration lead | Freeze contracts, create backups, own schema and merge gates |
| Agent 1 — Data foundation | MarketData frame adapter, interval-aware resolver, cache/completeness tests |
| Agent 2 — Quant/profile | Cadence, profile lifecycle, comparison, uncertainty and formula tests |
| Agent 3 — Independent QA | Production-shaped fixtures, authority invariants and replay harness |

### 17.3 Wave 2 — EOD and persistence

| Agent | Responsibility |
|---|---|
| Integration lead | Own EOD orchestrator insertion and merged regression |
| Agent 1 | Authorised EOD worklist and request-ledger reconciliation |
| Agent 2 | Vanguard typed packet and fail-closed auction behaviour |
| Agent 3 | Decision and Outcome Ledger schema/writers/tests |

### 17.4 Wave 3 — Morning and presentation

| Agent | Responsibility |
|---|---|
| Integration lead | Own Morning Gate merge, flags and production release |
| Agent 1 | Morning incremental bars and profile lifecycle |
| Agent 2 | Intelligence Lab evidence and UX states |
| Agent 3 | Interpreter comparison, independent end-to-end regression and replay |

## 18. Implementation file impact map

Expected primary changes:

- `canonical_data/intraday_bars.py`
- `canonical_data/contracts.py`
- new configured MarketData intraday adapter under `canonical_data/` or `market_data/`
- `market_structure/profile.py`
- `market_structure/service.py`
- profile lifecycle/comparison module under `market_structure/`
- `intelligent_orchestrator.py`
- `vanguard/schemas/input_schema.py`
- `vanguard/integration/orchestrator_adapter.py`
- `vanguard/layer1_auction/auction_synthesizer.py`
- `vanguard/layer2_statistical/edge_detector.py`
- profile-dependent scenario builders
- `morning_gate.py`
- `contracts/lab_evidence_overlay.py`
- `contracts/interpreter_handoff_materializer.py`
- `pipeline_interpreter/evidence_resolver.py`
- `intelligence-lab/intelligence_lab.py`
- `intelligence-lab/static/index.html`
- new Decision and Outcome Ledger migration/writer/reporter modules
- focused tests plus end-to-end replay fixtures.

The legacy `vanguard/layer1_auction/market_profile.py` is retained only during migration, then archived after parity and release acceptance. It must not remain an active second calculator.

## 19. Release claim sheet

Every implementation wave must publish:

- requirement and design-section IDs;
- files changed and immutable backups;
- source commit/tree hash;
- schema/database migration IDs;
- tests added, executed and results;
- replay run ID and population reconciliation;
- provider calls, cache hits, missing-range requests and exceptions;
- authority-invariant results;
- EOD/Morning/Lab/Interpreter artefact hashes;
- known limitations and unresolved assumptions;
- rollback trigger assessment;
- promotion decision and approver.

## 20. Definition of done

The enhancement is complete only when:

1. valid intraday observations are acquired once and reused;
2. dropped tickers make no downstream data calls;
3. completed EOD profiles reach Vanguard through a typed governed packet;
4. no daily-only or unusable profile can generate auction alignment/readiness;
5. Morning Gate distinguishes premarket from developing-session evidence;
6. EOD evidence remains immutable and morning changes are explicit;
7. Market Profile and macro remain advisory;
8. the Lab provides complete evidence, quality, lineage and reasons;
9. the Interpreter explains but does not acquire or govern;
10. every candidate and matured outcome is captured append-only;
11. all focused, full, replay and live-cycle acceptance gates pass;
12. the release is reproducible and restorable.

## 21. Final recommendation

Proceed with the implementation in Phases 0–8 using the four-agent model. The first production change must be the Vanguard fail-open protection, followed by the interval-aware canonical data foundation. Do not enable a current-session Market Profile until the MarketData entitlement preflight proves which session and delay are actually delivered. Do not promote the full enhancement until the EOD replay, premarket Morning Gate and RTH developing-profile tests all pass.

This document authorises no production change by itself. It is the validated build, test, integration, deployment and rollback specification.
