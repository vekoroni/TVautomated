# AVS-SD-FIX-002 — Monetisable Pipeline Remediation

**Document status:** FINAL v1.2 — approved for controlled implementation after independent verification  
**Date:** 2026-09-12  
**Source register:** `AVS-FIX-002_monetisable_pipeline_fix_register.md`  
**QA sources:** `AVS-QA-SD-FIX-002_design_review.md`; `AVS-QA-SD-FIX-002_v1.1_verification.md`  
**Decision:** APPROVED DEVELOPMENT AUTHORITY — v1.2 corrections are mandatory  
**Scope:** Long, single-leg CALL and PUT opportunities with governed 1–20 trading-session theses  
**Implementation status:** Design only; this document does not claim that the work packages are implemented  
**Execution authority:** Human trader only

## 0. Interim operating profile

This profile governs operation until WP0–WP3 pass their technical deployment gates. It protects current trading while preventing test evidence from becoming a false production baseline.

1. Run the normal completed-session pipeline only after the canonical provider-finality contract resolves the required session as `PROVIDER_SESSION_COMPLETE`. The earliest clock boundary is the XNYS close plus the configured provider-settlement delay; 16:15 ET is a lower bound, not proof of provider completeness.
2. Record the code identity, configuration identity, session, evidence cutoff and operator mode in the run notes. A dirty tree, forced intraday invocation or prior-session anchor makes the run `TEST`, not a calibration or performance baseline.
3. Use the pre-open Morning function only to reassess the underlying thesis. Prior-session option quotes remain clearly labelled historical.
4. Perform the current option quote check no earlier than 09:35 ET, preferably within the governed 09:35–09:45 ET primary window. If the opening market is still unstable, defer and refresh later rather than converting a wide opening spread into a thesis failure.
5. The Intelligence Lab remains the trader-facing surface. Existing overlays are research cross-checks only and may not grant authority, remove opportunities or overwrite governed fields.
6. Record the human action and actual fill manually until `fill_record_v1` is deployed. A system GO/BUY state is not an executed trade.
7. Do not use an interim run to claim calibration, expectancy or production closure.

### 0.1 Operational definition of provider completeness

MarketData does not provide one authoritative Boolean declaring an options session complete. AVSHUNTER must therefore derive and persist a governed finality assessment. A completed-session chain is eligible for normal use only when all of the following are true:

1. the requested session is the last completed XNYS session resolved by the governed calendar;
2. the request mode explicitly targets historical/completed-session data rather than a live/latest snapshot;
3. the provider-specific settlement delay has elapsed;
4. the canonical underlying store contains the official close for the same ticker and session;
5. the returned chain meets the configured session-date and provider-timestamp coverage thresholds;
6. the acquisition records the chain-wide timestamp distribution, including minimum, median, p95 and maximum provider quote timestamps and coverage after configured late-session watermarks;
7. the immutable registry record carries `finality_state`, `completion_basis`, `provider_retrieved_at_utc`, `session_close_utc`, coverage metrics and the underlying-close dataset ID.

One late quote cannot prove whole-chain finality, and every contract is not required to update at 16:00 ET. The timestamp distribution is evidence, not an individual-contract close-time gate. The canonical states are:

```text
PROVIDER_SESSION_COMPLETE
PROVIDER_SESSION_PARTIAL
PROVIDER_SESSION_NOT_SETTLED
PROVIDER_SESSION_DATE_MISMATCH
PROVIDER_SESSION_EVIDENCE_INSUFFICIENT
```

`PROVIDER_SESSION_PARTIAL` remains visible for monitoring and engineering diagnostics but cannot enter completed-session DOI valuation as normal evidence. A forced or explicitly degraded run may consume it only with `run_condition = TEST` and a named quality state.

## 1. Executive decision

AVSHUNTER should implement the remediations in this design. The underlying problems are resolvable, but the source fix register must not be implemented verbatim.

The target product is not an engine that guarantees profitable trades or manufactures a daily quota. It is a governed system that:

1. preserves every structurally valid ticker thesis;
2. identifies and ranks the option contracts that can express that thesis;
3. estimates contract monetisability under explicit price, time and volatility scenarios;
4. states whether the exact contract is currently observable and executable;
5. refreshes the thesis and contract assessment when new evidence arrives;
6. records decisions, actual fills and counterfactual outcomes so realised expectancy can be measured;
7. presents all evidence coherently to the human trader in the Intelligence Lab.

The implementation must preserve four separate conclusions:

```text
Underlying thesis validity
        !=
Contract monetisability estimate
        !=
Current execution quality
        !=
Human trading decision
```

A temporary quote, spread, volume or open-interest condition must not delete a valid ticker thesis. An unavailable or invalid quote must prevent the exact contract from being described as executable, but the ticker and its contract family remain visible for monitoring and re-ranking.

## 2. Superseding design decisions

Where this document conflicts with the source register, this document governs development.

| Source proposal | Design decision |
|---|---|
| Make reachable-target time-value monetisability authoritative | Retain it as governed, lineaged **advisory contract evidence**. It cannot grant capital or invalidate the ticker thesis. |
| Reintroduce option R:R | Rejected from the primary Lab and all authority/ranking paths. R:R may remain in explicitly labelled research exports. The governed scenario payoff table is the trader-facing replacement because it exposes the time, volatility and loss assumptions that one ratio conceals. |
| Apply a macro-derived size multiplier | Rejected. Publish affordability and suggested size as advisory evidence. Macro cannot apply capital size. |
| Publish one sovereign `decision_state` | Rejected. Preserve separate thesis, contract and execution states. A derived presentation summary may describe them without becoming an authority. |
| Require at least ten positive-EV rows on most days | Rejected. No-trade days are legitimate; output quotas create false signals. |
| Treat a decision as an executed trade | Rejected. Only a confirmed human or broker fill creates an executed position. |
| Require live option quotes before 09:25 ET | Rejected as infeasible. Split pre-open thesis validation from post-open contract refresh. |
| Start a normal Evening run after 20:15 ET | Corrected: use the XNYS calendar plus provider-completeness evidence. 16:15 ET is the earliest lower bound; a fixed UTC offset is prohibited. Dynamic and forced runs remain permitted but are labelled non-baseline. |

## 3. Business outcomes and invariants

### 3.1 Required business outcomes

- The Intelligence Lab is the complete trader-facing view of the governed opportunity.
- CALL and PUT theses are evaluated symmetrically while retaining direction-specific probability and payoff behaviour.
- The pipeline retains developing opportunities and re-evaluates them over the 1–20 session thesis horizon.
- Contract selection is dynamic: an initially unattractive contract may mature, or a better contract may supersede it.
- A preferred contract change triggers atomic recomputation of every contract-specific field.
- Macro and structure evidence improve context and narrative but do not reverse direction, delete a thesis, grant capital or automatically size a trade.
- Outcomes distinguish thesis failure, contract-selection failure, execution timing, activity maturation and normal uncertainty.

### 3.2 Mandatory invariants

1. `governed_direction`, thesis origin, structural target, authoritative invalidation and planned hold are owned by the Thesis context.
2. DOI cannot change the thesis direction, target, invalidation or hold.
3. Macro cannot grant or remove capital permission, change direction or delete an opportunity.
4. A missing input remains null with a named quality state unless a governed calculation default is explicitly permitted. A permitted default must preserve the raw missing state and publish `default_applied`, `default_source`, `default_value` and sensitivity or applicability information. Silent zero substitution is prohibited.
5. Every numeric field has one canonical unit and one calculation version.
6. Every option assessment identifies the exact OCC symbol and immutable observation dataset used.
7. When the OCC symbol or quote observation changes, all Greeks, payoff, monetisability, liquidity and ranking fields are recomputed together.
8. No current two-sided quote means an `EXECUTION_*_MONITOR` or unavailable state, not `EXECUTION_EXECUTABLE_NOW` and not ticker deletion.
9. Low OI or zero current volume may reduce rank or confidence; neither is a thesis veto.
10. Only an explicit actual fill creates an executed position.
11. A presentation summary cannot contradict its underlying domain states.
12. Every production result is reproducible from a run ID, complete code/config identity, evidence cutoff and immutable input IDs. The baseline enumerates the production dependency graph and fails if any imported production dependency is untracked, unhashed or outside the manifest.
13. Current quote executability and historical/activity maturation are independent conclusions. OI, volume or activity deterioration cannot make a valid two-sided quote non-executable, and activity improvement cannot make an invalid quote executable.
14. A numerical pricing rate must come from a governed `MarketRateObservation`; a narrative or advisory macro packet cannot silently become valuation authority.
15. `contracts_at_budget` is pure integer affordability from desk budget and exact contract ask. Macro, direction alignment and horizon commentary cannot enter its arithmetic.

## 4. Ubiquitous language

- **Underlying thesis:** A governed, direction-specific hypothesis for a ticker over 1–20 trading sessions.
- **Structural target:** The original price level derived from governed structural evidence.
- **Reachable target:** A time-bounded scenario level derived from origin spot, governed hold and validated volatility budget. It does not replace the structural target.
- **Continuation thesis:** A newly underwritten thesis created after a material favourable move when evidence supports further movement. It supersedes; it does not silently rewrite the original thesis.
- **Contract family:** The governed set of eligible long CALL or PUT contracts that may express one thesis.
- **Contract assessment:** An immutable evaluation of one exact contract at one evidence cutoff.
- **Monetisability:** A scenario- or probability-based estimate that a contract can deliver a positive return within the thesis horizon. It is not a guarantee or execution authority.
- **Execution quality:** Current observable quote, spread, size and quote-lineage evidence for the exact contract.
- **Activity maturation:** Evidence that interest in a contract is developing, stable or deteriorating from volume, OI and their trajectories. It does not decide current quote executability.
- **Provider finality:** A governed assessment that a completed-session dataset is suitable for normal historical use, supported by session, request-mode, settlement, underlying-close and chain-coverage evidence.
- **Preferred contract:** DOI's highest-ranked current expression of the thesis. It is advisory to the human trader.
- **Decision record:** What the system presented and what the human decided.
- **Fill record:** Evidence that an order actually executed, including symbol, price, quantity and timestamp.
- **Counterfactual outcome:** The subsequent measured path of a candidate that was presented but not taken.
- **Normal run:** A correctly timed, clean-code, point-in-time run eligible for calibration and regression baselines.
- **Test run:** A forced, intraday, stale-anchor or dirty-code run retained for engineering evidence but excluded from trading performance claims.

## 5. Bounded contexts

### 5.1 Run Planning context

**Owns:** run identity, session resolution, evidence cutoff, run condition and feature configuration.  
**Aggregate:** `PipelineRun`.  
**Must not own:** thesis logic, option economics or capital authority.

Required `run_condition` values:

```text
NORMAL_COMPLETED_SESSION
FORCED_INTRASESSION
PREOPEN_THESIS_CHECK
POSTOPEN_CONTRACT_REFRESH
REPLAY
TEST
```

### 5.2 Canonical Market Evidence context

**Owns:** immutable underlying, option, rate, macro and intraday observations; dataset identity; content hash; provider timestamp; quality state.  
**Aggregates:** `UnderlyingObservation`, `OptionChainObservation`, `ExactContractQuote`, `MarketRateObservation`, `MacroObservation`.  
**Must not own:** trading conclusions.

### 5.3 Thesis context

**Owner:** Discovery/Vanguard, with Morning Thesis Validation as the lifecycle service.  
**Aggregate:** `UnderlyingThesis`.  
**Owns:** governed direction, origin, structural target, invalidation, hold, evidence and supersession.

### 5.4 Volatility and Reachability context

**Owns:** forecast-volatility observations, cumulative expected-move budgets, reachable scenario levels and forecast validation.  
**Aggregate:** `VolatilityBudget`.  
**Must not own:** ticker direction or contract selection.

### 5.5 Dynamic Options Intelligence context

**Aggregate root:** `ContractFamily`, keyed by `thesis_id + family_policy_version`.  
**Owns:** family generation, deterministic valuation, scenario payoff, activity maturation, ranking, preferred contract and supersession.  
**Must not own:** thesis validity, macro authority, capital or actual fills.

### 5.6 Macro Advisory context

**Owns:** run-frozen macro packet, sector/industry applicability, scenarios, source quality and point-in-time lineage.  
**Aggregate:** `MacroAdvisoryContext`.  
**Must not own:** direction, contract selection, capital permission or applied size.

### 5.7 Execution Evidence context

**Owns:** current quote validity, spread, quote age, displayed size, limit-price evidence and warnings.  
**Aggregate:** `ExecutionEvidence`.  
**Authority:** descriptive only; the human trader owns the decision.

### 5.8 Capital-allocation boundary

AVSHUNTER is capital-agnostic. It owns thesis evidence, contract monetisability,
current execution evidence and uncertainty; it does not own account balances,
desk budgets, position sizing, contract counts, capital permission or orders.
The contract ask and multiplier remain evidence about the selected contract, but
they are never combined with operator capital inside this pipeline.

Any future portfolio-allocation capability must be a separately designed bounded
context downstream of the Intelligence Lab and human decision. It may consume a
governed opportunity, but it must not write back into thesis validity,
monetisability, preferred-contract ranking or execution-evidence state.

### 5.9 Decision and Outcome context

**Owns:** presented decision, human response, actual fill, exit and matured counterfactual outcomes.  
**Aggregates:** `DecisionRecord`, `PositionEpisode`, `OutcomeRecord`.  
**Must not infer:** a fill from a BUY/GO/presentation state.

### 5.10 Intelligence Lab context

**Role:** read-model projection over the bounded contexts.  
**Owns:** presentation schema and coherent trader narrative.  
**Must not:** recalculate domain values, invent fallbacks or become another authority.

## 6. Context map

```text
Run Planning
     |
     v
Canonical Market Evidence ----------------------+
     |                                           |
     v                                           v
Thesis Context --> Volatility/Reachability --> Dynamic Options Intelligence
     |                                           |
     +------------------+------------------------+
                        v
                 Morning Validation
                        |
Macro Advisory ---------+-------> Intelligence Lab read model
                                      |
Execution Evidence -------------------+
                                      |
                                      v
                              Human decision/fill
                                      |
                                      v
                              Decision & Outcome
```

Integration between contexts uses versioned contracts and anti-corruption adapters. No consumer may search mutable CSV aliases to reconstruct another context's domain object.

## 7. Authority matrix

| Question | Authority | Advisory consumers |
|---|---|---|
| CALL or PUT direction | Thesis context | DOI, Macro, Lab, Worker 3 |
| Structural target/invalidation/hold | Thesis context | Reachability, DOI, Morning |
| Whether price evidence breached the original thesis | Morning Thesis Validation | Lab, DOI |
| Whether a continuation thesis is warranted | New Thesis underwriting, never a silent lifecycle rewrite | DOI, Lab |
| Contract family and preferred contract | DOI | Lab and human |
| Contract scenario monetisability | DOI | Lab and human |
| Current quote/execution quality | Execution Evidence | Lab and human |
| Macro/sector alignment | Macro Advisory | Lab, Worker 3, human |
| Final order and capital | Human/broker workflow | Ledger |
| Actual realised outcome | Decision and Outcome context | Calibration and reporting |

## 8. Domain model

### 8.1 `UnderlyingThesis`

Required fields:

```text
thesis_id
thesis_version
ticker
governed_direction
origin_spot
origin_timestamp_utc
structural_target_spot
invalidation_spot
planned_hold_sessions
planned_hold_source
evidence_cutoff_utc
thesis_state
supersedes_thesis_id
```

The aggregate rejects wrong-side target or invalidation geometry. A missing authoritative invalidation produces a named data exception and a visible review state; it must not fabricate a stop.

### 8.2 `VolatilityBudget`

Required fields:

```text
forecast_vol_annual_fraction
forecast_model_id
forecast_evidence_cutoff_utc
expected_move_5d_fraction
expected_move_10d_fraction
expected_move_20d_fraction
horizon_convention = CUMULATIVE_1SIGMA
bias_multiplier
validation_state
```

Expected-move fields are cumulative from the evaluation timestamp. Incremental buckets, if needed for research, use separately named fields and cannot be substituted for cumulative horizons.

For any governed hold from 1–20 sessions, the calculation uses the annual forecast directly:

```text
expected_move_hold_fraction = validated_forecast_vol_annual * sqrt(hold_sessions / 252)
```

The current Layer 3 implementation produces one annualised forecast and applies it across the governed horizon. It does not currently publish independent annualised term-structure forecasts. The 5/10/20 fields are therefore published checkpoints, not interpolation anchors. Nearest-bucket substitution and interpolation between rounded outputs are prohibited. If a future model publishes validated horizon-specific forecasts, it must use a new contract and model version that identifies the selected horizon explicitly; it cannot silently alter this calculation.

Before historical validation is accepted, `bias_multiplier = 1.0`, `validation_state = UNVALIDATED` and `bias_multiplier_applied = false` must be displayed on every dependent assessment. Historical validation may be built early, but a learned multiplier cannot enter production calculations until its point-in-time validation and release gate pass.

### 8.3 `ReachabilityAssessment`

```text
thesis_id
hold_sessions
sigma_multiple
reachable_target_spot
structural_distance_fraction
volatility_budget_fraction
reach_ratio
calculation_version
input_dataset_ids
```

For a CALL:

```text
reachable_target = origin_spot * (1 + k * expected_move_hold_fraction)
```

For a PUT:

```text
reachable_target = origin_spot * (1 - k * expected_move_hold_fraction)
```

The value is a scenario boundary, not a prediction that the level will be reached.

Every assessment publishes the uncorrected and corrected volatility budget, whether a bias multiplier was applied, and the source validation report. A reachable target calculated from an unvalidated forecast is visibly `UNVALIDATED_INPUT`, not silently promoted to validated evidence.

### 8.3.1 `MarketRateObservation`

A numerical option valuation may use a rate only through this canonical contract:

```text
rate_observation_id
rate_source
rate_instrument
rate_tenor
rate_decimal_fraction
as_of_date
observed_at_utc
retrieved_at_utc
freshness_state
selection_policy_version
input_dataset_ids
default_applied
default_source
```

The bridge selects a governed maturity-appropriate short-rate or zero-rate observation for the contract horizon. SOFR, Treasury bill/zero-curve or another approved instrument may be used according to the versioned selection policy. Percentage-to-decimal conversion is explicit. The `macro_rates_context` packet may supply a candidate observation with its lineage, but remains advisory until the bridge validates the source, instrument, as-of date, freshness and unit. Fed funds, SOFR or three-month Treasury values cannot be selected merely because they are present in narrative macro JSON.

Missing or stale rate evidence produces a named assessment state or an explicitly governed default with sensitivity disclosure. It never becomes an undisclosed zero.

### 8.4 `ContractAssessment`

Identity:

```text
assessment_id = hash(thesis_id, OCC symbol, observation_dataset_id,
                     calculation_version, evidence_cutoff_utc)
```

Required groups:

- exact OCC identity, expiry, strike and side;
- bid, ask, bid/ask sizes, timestamp and source dataset;
- DTE, delta, gamma, theta, vega and IV with quality states;
- deterministic payoff at flat, favourable 1-sigma, favourable 2-sigma, reachable and structural scenarios;
- remaining time value using a governed rate and dividend input;
- spread in canonical fraction plus display projection percentage;
- separate contract-identity, current-execution and activity-maturation states;
- uncertainty, applicability and calculation versions;
- calibrated probabilities only when the calibration contract passes.

All deterministic payoff scenarios in the first release use `AT_GOVERNED_TIME_STOP` as their valuation basis: the scenario spot is observed at the end of the governed XNYS holding sessions and the option value uses the remaining calendar time from that target session to expiry. The XNYS-session-to-calendar-expiry bridge, calendar version, rate and dividend assumptions are mandatory assessment fields. A future first-passage valuation requires a separately versioned model and cannot reuse the time-stop label.

The initial scenario-state policy is versioned as `scenario-monetisability-policy-v1`:

```text
SCENARIO_MONETISABLE
  reachable-scenario net return after modelled entry/exit friction >= configured profit floor

SCENARIO_LIMITED
  reachable-scenario net return > 0 but below the configured profit floor

NOT_CURRENTLY_MONETISABLE
  reachable-scenario net return <= 0
```

The profit floor, friction model and their source are governed configuration. These states remain advisory and cannot be used as a thesis or capital gate.

### 8.5 `PreferredContractDecision`

```text
thesis_id
family_id
preferred_contract_symbol
preferred_assessment_id
ranking_score
ranking_score_kind = DETERMINISTIC_UTILITY | CALIBRATED_EXPECTED_UTILITY
alternatives
prior_preferred_contract_symbol
supersession_reason
score_margin
decision_authority = NONE
```

Hysteresis prevents small score changes from constantly changing the preferred contract. A replacement occurs only when the challenger exceeds the governed margin and its observation quality passes.

The first release uses the versioned configuration keys `preferred_switch_margin_abs` and `preferred_switch_margin_relative`. Initial candidate values are 5 deterministic-utility points and 10% relative improvement; replay and sensitivity tests must approve both before activation. The replacement threshold is the greater of the two. The values are configuration, never inline constants, and a contract may still be replaced immediately for expiry, malformed identity or a terminal data defect.

## 9. State models

### 9.1 Thesis state

```text
THESIS_DEVELOPING
THESIS_ACTIVE
THESIS_VALIDATED
THESIS_UNDER_PRESSURE
THESIS_CONDITION_BREACHED
THESIS_TARGET_TOUCHED
THESIS_CONTINUATION_REVIEW_REQUIRED
THESIS_RECOVERING
THESIS_HORIZON_ELAPSED_REASSESS
THESIS_DATA_INSUFFICIENT
```

These states preserve history. `CONDITION_BREACHED`, `TARGET_TOUCHED` and `HORIZON_ELAPSED_REASSESS` are facts requiring human review or new underwriting; they do not delete the opportunity record.

### 9.2 Contract identity lifecycle state

```text
FAMILY_GENERATED
CONTRACT_DATA_PENDING
CONTRACT_ASSESSED
CONTRACT_REPAIR_REQUIRED
CONTRACT_DATA_DEFECT
CONTRACT_SUPERSEDED
CONTRACT_EXPIRED_HISTORICAL
```

| From | Event | To | Constraint |
|---|---|---|---|
| `FAMILY_GENERATED` | observation absent | `CONTRACT_DATA_PENDING` | Thesis and family retained |
| `CONTRACT_DATA_PENDING` | valid immutable observation resolved | `CONTRACT_ASSESSED` | Exact OCC identity required |
| `FAMILY_GENERATED`, `CONTRACT_DATA_PENDING` or `CONTRACT_ASSESSED` | selected identity is incomplete but a governed family can be searched | `CONTRACT_REPAIR_REQUIRED` | Repair cannot change thesis direction |
| `CONTRACT_REPAIR_REQUIRED` | replacement identity and observation validated | `CONTRACT_ASSESSED` | New immutable assessment required |
| Any non-terminal state | identity/economics mismatch or irreparable malformed data | `CONTRACT_DATA_DEFECT` | Never executable; named exception retained |
| `CONTRACT_ASSESSED` or `CONTRACT_REPAIR_REQUIRED` | preferred contract changes | `CONTRACT_SUPERSEDED` | Supersession event links old and new assessments |
| Any non-expired state | expiry passes | `CONTRACT_EXPIRED_HISTORICAL` | Retain history; generate a new family if thesis remains monitored |

### 9.3 Current execution-evidence state

```text
EXECUTION_QUOTE_UNAVAILABLE
EXECUTION_QUOTE_STALE_MONITOR
EXECUTION_ZERO_BID_MONITOR
EXECUTION_WIDE_SPREAD_MONITOR
EXECUTION_CROSSED_MARKET_DATA_DEFECT
EXECUTION_UNVALIDATED_INPUT
EXECUTION_REVIEWABLE
EXECUTION_EXECUTABLE_NOW
```

This state is recomputed for each exact quote observation. Only a valid provider timestamp, non-crossed two-sided quote and governed execution policy can produce `EXECUTION_EXECUTABLE_NOW`. Fetch time cannot replace quote time. A later valid quote can move any monitor state to `EXECUTION_REVIEWABLE` or `EXECUTION_EXECUTABLE_NOW`; a later missing, stale, zero-bid, crossed or wide quote can move it back to the corresponding evidence state. These changes never alter the thesis or activity-maturation state.

### 9.4 Activity-maturation state

```text
ACTIVITY_UNKNOWN
ACTIVITY_THIN
ACTIVITY_DEVELOPING
ACTIVITY_MATURING
ACTIVITY_REVIEWABLE
ACTIVITY_REGRESSING
```

Activity maturation is derived from volume, OI, changes in both, quote-update trajectory and other versioned activity features. Low OI or zero volume may produce `ACTIVITY_THIN`; improving evidence may progress through `ACTIVITY_DEVELOPING`, `ACTIVITY_MATURING` and `ACTIVITY_REVIEWABLE`; deterioration produces `ACTIVITY_REGRESSING`. None of these states grants or removes current executability. A contract may simultaneously be `ACTIVITY_THIN` and `EXECUTION_EXECUTABLE_NOW`, or `ACTIVITY_REVIEWABLE` and `EXECUTION_WIDE_SPREAD_MONITOR`.

All identity, execution and activity transitions are append-only. A later observation creates a new event and assessment; it does not mutate prior evidence.

### 9.5 Monetisability state

```text
SCENARIO_MONETISABLE
SCENARIO_LIMITED
NOT_CURRENTLY_MONETISABLE
INDETERMINATE
NOT_EVALUATED_DATA_MISSING
NOT_APPLICABLE
```

Every state carries `authority = ADVISORY_ONLY`, scenario definition, input identity and model/calculation version.

### 9.6 Morning refresh state

```text
PENDING_MORNING_REFRESH
THESIS_REFRESHED_PREOPEN
THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE
REFRESHED_EXACT_CONTRACT
REFRESHED_REPLACEMENT_CONTRACT
CONTRACT_REFRESH_UNAVAILABLE
CONTRACT_REFRESH_DEFERRED_UNTIL_OPEN
UNVALIDATED_INPUT
NOT_APPLICABLE
```

Run-condition vocabulary extends `domain.run_planning.OperationalContext` and `RequestedAction`; it must not create a parallel enum in an orchestrator or UI module. Contract adapters may expose friendly labels, but the domain values above remain canonical.

## 10. Canonical units and anti-corruption rules

Domain calculations use explicit value objects:

| Concept | Canonical domain unit | Presentation unit |
|---|---|---|
| Spread | `spread_fraction_mid`, 0.25 = 25% | `spread_pct_of_mid`, 25.0 |
| IV/volatility | decimal fraction | percentage |
| Probability | decimal in [0,1] | percentage |
| Expected move | decimal fraction and absolute price in separately named fields | percentage and dollars |
| Premium | dollars per share | dollars per share and contract cost |
| Holding period | XNYS trading sessions | friendly 1–5/6–10/11–20 label |
| DTE | calendar days to expiry | integer days |

Legacy fields remain readable through versioned adapters during migration. No domain service may use `if value > 1 then divide by 100` as a permanent unit-resolution strategy.

## 11. End-to-end target flow

### 11.1 Completed-session thesis preparation

1. Run Planning resolves the last completed XNYS session and labels the run condition.
2. Canonical Market Evidence resolves immutable price, options, rate, macro and profile observations at the cutoff.
3. Discovery/Vanguard creates or updates the governed ticker thesis.
4. Volatility Budget publishes cumulative 5-, 10- and 20-session expected moves.
5. Reachability evaluates the governed hold without replacing the structural target.
6. DOI generates the complete governed long CALL or PUT family.
7. DOI deterministically values each scoreable contract using the canonical rate and dividend evidence.
8. DOI calculates scenario payoff, contract quality, activity maturation and uncalibrated utility while Execution Evidence independently classifies the current quote.
9. When calibration is valid, DOI adds calibrated target-before-stop and liquidity-transition probabilities.
10. DOI publishes preferred contract, alternatives and monitoring states without deleting the thesis.
11. Macro Advisory joins sector/industry context after ticker classification and publishes context only.
12. The Intelligence Lab projects the separate thesis, contract, execution and macro states.

### 11.2 Pre-open thesis validation

1. Resolve the underlying from a timestamped canonical extended-hours quote when available. Otherwise retain the prior official close as `REFERENCE_PRIOR_CLOSE`, show index futures only as separate market context and mark live ticker gap evidence `UNAVAILABLE`. Never manufacture a ticker price by applying an index-futures move to the prior close.
2. Compare current spot with the frozen target and invalidation geometry.
3. Publish thesis state and remaining runway.
4. If the original move is substantially consumed, publish `CONTINUATION_REVIEW_REQUIRED`.
5. Do not require a live option quote to decide whether the underlying thesis remains valid.
6. Do not silently overwrite the EOD thesis or preferred contract.
7. If no reliable current ticker price exists, publish `THESIS_REFRESH_DEFERRED_PRICE_UNAVAILABLE`; do not assert validation or invalidation from macro or index proxies.

### 11.3 Post-open contract refresh

1. Resolve the exact current quote for the preferred contract after regular option trading begins. The primary governed window is 09:35–09:45 ET; a later refresh is permitted and recorded when the opening market remains unstable.
2. If the quote is unavailable or structurally invalid, search the existing governed family for a replacement.
3. Recompute all contract-specific economics atomically for the exact selected observation.
4. Update execution evidence and DOI rank.
5. Retain the original contract assessment as immutable history and publish a supersession event if changed.
6. The Lab shows whether the contract is executable, monitorable or requires human review.
7. Publish `contract_refresh_timestamp_utc`, provider quote timestamp, source dataset ID and refresh window state. The fetch timestamp can never substitute for a missing provider quote timestamp.

### 11.4 Continuation workflow

When price has already moved materially in the thesis direction:

1. preserve the original thesis and record the consumed runway;
2. evaluate whether new structural evidence supports continuation;
3. if supported, create a new thesis version with a new origin, target, invalidation and hold;
4. generate a new contract family for that thesis version;
5. never recommend entry merely because the previous thesis was correct;
6. never classify the original thesis as a failure solely because its target was reached.

### 11.5 Outcome workflow

1. Store every presented candidate and preferred contract assessment.
2. Store the human decision separately.
3. Create a position episode only from an explicit fill record.
4. Measure underlying and option MFE/MAE, target/stop/time order, liquidity development and returns.
5. Mature counterfactual outcomes for the governed top-N not taken candidates.
6. Attribute outcome categories: thesis, contract choice, liquidity, execution, volatility, timing or unclassified uncertainty.

## 12. Required work packages

### WP0 — Baseline and run-condition truth

**Changes**

- Correct normal-session timing with the XNYS calendar and provider-completeness semantics; do not use a fixed UTC offset.
- Implement `ProviderSessionFinality` and persist its completion basis, request mode, settlement state, official-close identity and chain timestamp distribution.
- Require `PROVIDER_SESSION_COMPLETE` for a normal completed-session DOI input. Route `PARTIAL` or insufficient finality to a named exception or an explicitly labelled `TEST` run; do not silently accept it as complete.
- Add `run_condition` and eligibility-for-baseline fields to `run_meta_v2`.
- Split pre-open thesis validation from post-open option refresh.
- Record quote timestamp distributions and source lineage.
- Remove every fallback that substitutes `_utc_now()` or fetch time for a missing provider quote timestamp, including the current Morning quote projection. A quote without its observation timestamp is unavailable for execution classification.
- Add immutable timestamped macro packet archiving by packet ID.
- Inventory and quarantine repository litter; do not delete without a verified manifest.
- Extend the existing `domain.run_planning` vocabulary instead of defining another run-condition enum.

**Acceptance**

- Forced and dirty-code runs cannot be mistaken for normal baselines.
- A normal completed-session run resolves the correct session.
- A pre-open run never claims current option quotes.
- Every actionable option quote has exact source and timestamp lineage.
- Provider completeness, rather than wall-clock or one late quote alone, proves that the completed option session is available.
- Normal completed-session DOI consumes only `PROVIDER_SESSION_COMPLETE`; partial evidence remains retained and non-actionable.

### WP1 — Numeric truth and units

**Changes**

- Publish cumulative GARCH expected-move fields under a new version.
- Migrate spread calculations to explicit fraction and display-percentage fields.
- Correct opportunity-tier thresholds to consume canonical fractions.
- Inventory all silent numeric defaults in production producers and consumers. Each site must preserve null, apply a governed default with disclosure, or fail with a named data state.
- Add contract tests at all producer/consumer boundaries.

**Acceptance**

- Cumulative moves reconcile directly to `sigma * sqrt(hold_sessions/252)` under the same annualised forecast.
- No mixed-unit spread field exists in new contracts.
- CALL/PUT and 1–5/6–10/11–20 fixtures pass.
- Legacy readers remain compatible until their removal release.
- No undisclosed zero/default remains on a monetisability, rate, dividend, volatility, spread, target or probability path.

### WP2 — Reachability and deterministic contract economics

**Changes**

- Add `ReachabilityAssessment` beside structural geometry.
- Value flat, favourable 1-sigma, favourable 2-sigma, reachable and structural scenarios.
- Source risk-free rate through a canonical `MarketRateObservation` bridge.
- Define the versioned rate-selection policy, approved instruments, maturity mapping, unit conversion, freshness limits and explicit default/sensitivity behaviour. Treat `macro_rates_context` only as a candidate source packet until this bridge validates it.
- Run historical forecast-volatility validation before activating reachability. Until accepted, keep `bias_multiplier=1.0`, publish `UNVALIDATED` and prohibit automatic bias correction.
- Preserve intrinsic-at-expiry as a conservative disclosure, not the headline assessment.
- Replace the OI convexity proxy with payoff-shape evidence.
- Keep R:R out of execution authority and the required Lab surface.
- Evaluate all first-release deterministic scenarios at the governed time stop with the XNYS-session-to-calendar-expiry bridge.

**Acceptance**

- Every scoreable contract identifies the exact target scenario, rate, dividend and time basis.
- A contract change invalidates the old assessment and produces a complete new one.
- Missing rate or dividend evidence produces an explicit state rather than zero or silent fallback.
- Payoff direction is symmetric for CALL and PUT fixtures.
- Every dependent output exposes volatility validation state and whether a correction was applied.

### WP3 — DOI production completion

**Changes**

- Provide governed thesis IDs for every directed DOI input or retain a named data exception.
- Complete family valuation and ranking for all scoreable rows.
- Add Morning refresh transitions and preferred-contract supersession.
- Retain low-OI and zero-volume contracts as rankable evidence.
- Require a valid current quote only for `EXECUTION_EXECUTABLE_NOW`; activity state remains independent.
- Publish separate contract-identity, current-execution and activity-maturation states and prohibit OI/volume transitions from changing current executability.
- Publish deterministic utility explicitly as uncalibrated until calibration passes.
- Reconcile `thesis_id` from the DOI input contract through to the governed Lab book; do not assume that a populated final-book alias proves the DOI input identity was valid.

**Acceptance**

- A normal stored run no longer places all families in `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` or `DOI_TABLES_NOT_ACTIVATED`.
- `GOVERNED_CONTRACT_IDENTITY_MISMATCH` is zero for published preferred-contract projections; every retained mismatch is a named data exception and never actionable.
- Every directed input is assessed, retained with a named insufficiency, or recorded as a data exception.
- DOI never deletes an underlying thesis.
- Preferred and alternative contracts carry internally consistent identities and economics.

Stored evidence for the current blocker is `data/output/runs/20260911_115904/options/dynamic_options_intelligence_20260911_115904.json`: 1,218 families reached valuation and all 1,218 stopped at `FAMILY_NOT_VALUED_RATE_UNAVAILABLE`. The corresponding Lab projection also reports `DATA_UNAVAILABLE` and contract-identity inconsistencies. Development must reconcile both producer and projection states.

### WP4 — Direction-conditioned probabilities and validation

**Changes**

- Label competing events: target first, invalidation first or timeout.
- Condition on direction, hold, phase/state and volatility/compression evidence.
- Record exact matching dimensions and hierarchical backoff level.
- Use time-ordered train/validation/test partitions.
- Calibrate probabilities and validate forecast volatility by regime.
- Implement hierarchical backoff: exact bucket first; otherwise shrink to successively broader direction/horizon parents while recording `match_level`, `exact_n`, `parent_n` and shrinkage weight.

**Acceptance**

- PUT outcomes use favourable downside movement, not pooled positive-return labels.
- Every probability carries model ID, training cutoff, sample size and calibration state.
- Uncalibrated outputs are never displayed as probabilities.
- Brier score, log loss, reliability and coverage are reported by direction and horizon.
- No future evidence enters historical features.
- Activation requires at least 60% calibrated coverage of scoreable rows, overall expected calibration error no greater than 0.10 and direction/horizon expected calibration error no greater than 0.15 for strata with at least 100 held-out observations.
- The model must also demonstrate positive out-of-sample Brier Skill Score against the direction/horizon base-rate benchmark, with a confidence interval that does not support material degradation, plus discrimination and ranking value through ROC-AUC or PR-AUC as appropriate and predeclared top-quantile lift.
- Calibration without discrimination is insufficient: a constant base-rate model cannot activate calibrated ranking merely because it has low ECE. Failing strata remain explicitly uncalibrated and use deterministic utility.

### WP5 — Macro and structure context

**Changes**

- Carry sector and industry identity before macro applicability mapping.
- Consume the governed nested US Money Index routing and scenario contracts.
- Evaluate scenarios against timestamped observed metrics.
- Publish macro and structure evidence as advisory context.
- Carry `hidden_state_label`, `phase` and `trigger_primary` into `structure_evidence_state` with their source versions.
- Enforce the capital-allocation boundary: no budget, account-size, affordability or contract-count calculation may enter the pipeline or Lab read model.

**Acceptance**

- Mapped GICS rows do not become `SECTOR_UNMAPPED` because of join order.
- Scenario conditions name the observed value, timestamp and failed clause.
- Macro cannot change population, direction, contract identity or capital authority.
- No capital-allocation field appears in a governed pipeline or Lab contract.

### WP6 — Intelligence Lab and coaching projection

**Changes**

- Build one versioned Lab read model from bounded-context contracts.
- Show thesis, monetisability, execution and macro separately.
- Show what changed since the prior comparable assessment.
- Remove overlay verdict authority and retired R:R presentation.
- Regenerate coaching from the same read model.
- Produce the human-facing summary with one versioned pure projector, `derive_opportunity_presentation_v1`, from the separate domain states. It cannot write back into any authority field.
- Retain the desk-gate and coaching overlays only until two stored-run and two normal-cycle parity comparisons show field-level agreement; then archive them with a parity report and manifest.
- Extend the existing `lab_signal_book_v3` through a versioned migration or introduce `lab_signal_book_v4`; do not create a differently named contract that accidentally shares the v3 version.

**Acceptance**

- No `BLOCK`/`GO` contradiction exists because unrelated domain states are not collapsed.
- Every displayed number resolves to source ID and calculation version.
- Coaching and Lab values match exactly for the same run/ticker/assessment.
- A missing current quote cannot be displayed as executable.
- Overlay parity covers ticker population, contract identity, thesis state, monetisability state, execution state and macro context before retirement.

### WP7 — Decision, fill and outcome learning

**Changes**

- Extend append-only ledger contracts for presented decision, human response, fill, exit and counterfactual.
- Ingest manual confirmation or broker fill evidence.
- Measure option and underlying path outcomes at 1/2/3/5/10/20 sessions as applicable.
- Record whether a different family member outperformed the preferred contract.
- Provision and health-check the canonical `historical_prices.sqlite` path used by outcome maturation. A missing price store yields a visible deferred count and operational alert, never a silent no-outcome result.
- Split delivery into WP7A and WP7B: WP7A ships candidate/decision/manual-fill capture in Stage 1; WP7B adds exit, counterfactual and maturation services after contract-assessment identities stabilise.

**Acceptance**

- Decision counts never masquerade as fill counts.
- Every actual fill has symbol, price, quantity, time and source.
- Counterfactuals use evidence available at decision time.
- Outcome coverage and missing reasons reconcile to the candidate population.

### WP8 — Replay, release and operational acceptance

**Changes**

- Pin code, configuration, calendars, macro packet and canonical input IDs.
- Replay two normal stored runs for every material work package.
- Maintain expected-difference manifests across calculation-version changes.
- Produce release manifest, migration record and rollback plan.

**Acceptance**

- Same code/config/inputs produce the same governed outputs.
- A versioned fix produces only the expected field-level differences.
- No production feature is enabled by an unrecorded shell-only setting.
- Rollback restores compatible code and schema without deleting append-only evidence.

## 13. Data contracts and schema migration

New or revised contracts:

```text
run_condition_v1
market_rate_observation_v1
volatility_budget_v2
reachability_assessment_v1
contract_assessment_v2
preferred_contract_decision_v2
morning_thesis_observation_v2
contract_refresh_result_v1
macro_ticker_context_v2
lab_signal_book_v4
decision_record_v2
fill_record_v1
outcome_record_v2
```

Migration rules:

1. Add fields and new tables first; do not destructively rewrite historical observations.
2. Preserve prior calculation versions alongside new outputs.
3. Use explicit adapters for legacy percentage/fraction fields.
4. Backfill only when original immutable inputs and code version are known; otherwise mark `NOT_BACKFILLED_INPUT_UNAVAILABLE`.
5. Every schema migration runs against a copy in tests before production.
6. Database backup, hash and restorability check are release prerequisites.

## 14. Domain events

The following append-only events provide lifecycle and observability:

```text
PipelineRunPlanned
EvidenceObservationResolved
ThesisPrepared
ThesisConditionObserved
ContinuationReviewRequested
ThesisSuperseded
VolatilityBudgetPublished
ReachabilityAssessed
ContractFamilyGenerated
ContractAssessed
PreferredContractSelected
PreferredContractSuperseded
ContractQuoteRefreshDeferred
ContractQuoteRefreshed
ExecutionEvidencePublished
MacroContextPublished
OpportunityPresented
HumanDecisionRecorded
FillRecorded
PositionClosed
CounterfactualOutcomeMatured
```

Each event carries `event_id`, `run_id`, aggregate identity, evidence cutoff, emitted timestamp, schema version, calculation version, input IDs and content hash.

## 15. Test architecture

### 15.1 Test layers

1. **Domain unit tests:** pure formulas, invariants and state transitions.
2. **Contract tests:** producer and consumer agree on schema, units, nullability and vocabulary.
3. **Property tests:** side symmetry, monotonicity and boundary behaviour.
4. **Adapter tests:** legacy aliases cannot silently change units or identity.
5. **Integration tests:** completed-session, pre-open and post-open flows.
6. **Adversarial tests:** missing rate, missing quote, wrong-side stop, crossed market, stale quote, contract replacement and partial macro.
7. **Replay tests:** pinned point-in-time inputs and expected-difference manifests.
8. **Production-cycle acceptance:** one controlled technical cycle followed by five consecutive normal completed-session/post-open refresh cycles for formal operational acceptance.

### 15.2 Mandatory matrix

Every business-critical test covers:

- CALL and PUT;
- 1–5, 6–10 and 11–20 session horizons;
- ATM, moderate OTM and moderate ITM contracts;
- current, stale, zero-bid, missing and crossed quotes;
- low/high OI and zero/non-zero volume;
- target not started, partially consumed, substantially consumed and touched;
- original thesis and continuation thesis;
- exact contract retained and preferred contract superseded;
- macro supportive, opposed, neutral, uncertain and unavailable;
- normal, forced, replay and dirty-code runs.

### 15.3 Key property assertions

- Increasing favourable spot while holding other inputs fixed cannot reduce CALL intrinsic payoff or increase PUT intrinsic payoff.
- With `r = 0` and `q = 0`, increasing total variance cannot reduce a European CALL or PUT value. For non-zero rates or dividends, test the implementation against the pricing formula and arbitrage bounds; do not assert unconditional time monotonicity.
- Increasing spread cannot improve execution-quality rank.
- Low OI alone cannot delete a contract family member.
- Missing quote cannot yield `EXECUTION_EXECUTABLE_NOW`.
- Activity maturation cannot grant or revoke `EXECUTION_EXECUTABLE_NOW`.
- Macro changes cannot alter governed direction or population.
- Changing the preferred OCC symbol changes the assessment identity and recomputes all economics.
- A decision without a fill cannot create a realised trade outcome.

## 16. Observability and reconciliation

Every run summary must report:

- input, retained, exception and presented populations with reconciliation;
- counts by thesis, contract, monetisability, execution and refresh state;
- quote source/session/timestamp distributions;
- number of contract families generated, valued, ranked and unvalued by reason;
- risk-free-rate and dividend coverage;
- governed thesis-ID coverage;
- exact-contract retention and supersession counts;
- low-OI/zero-volume contracts retained;
- scoreable rows with positive deterministic utility, reported as an observational series only and never a quota or release target;
- probability coverage, calibration status and model versions;
- macro mapping and scenario resolution coverage;
- decisions, fills, exits and counterfactual outcomes separately;
- run condition, code identity, config identity and baseline eligibility.
- governed defaults applied by field/source and silent-zero violations;
- provider-finality state, completion basis, official-close identity, chain timestamp distribution, refresh-window state and quotes missing provider timestamps;

Population invariant:

```text
input opportunities
= presented active/monitoring/history rows
 + named integrity exceptions
```

No filtered population may disappear without an aggregate reason count and ticker-level exception record.

## 17. Release strategy

### 17.1 Feature activation

Use one governed release profile, not temporary PowerShell variables. Activate in this order:

1. new schemas and read-only shadow projections;
2. unit and contract corrections;
3. new GARCH/spread fields with legacy adapter parity;
4. reachability and scenario payoff disclosure;
5. DOI family valuation and rank projection;
6. Morning refresh and supersession;
7. Lab/coaching projection;
8. outcome capture;
9. calibrated ranking only after calibration acceptance.

“Shadow” in this release strategy means comparison-only during a bounded migration, not indefinite non-production code. Once accepted, the new version becomes the production read model and the replaced field is formally deprecated.

### 17.2 Rollback triggers

Rollback or disable the affected work package if:

- population does not reconcile;
- CALL/PUT direction changes outside the Thesis context;
- a quote/economics identity mismatch is detected;
- a missing or stale quote is labelled executable;
- macro changes capital, direction or population;
- contract assessment cannot be reproduced from its input IDs;
- schema migration is not restorable;
- the Lab disagrees with the governed source contract;
- actual-fill counts are inferred rather than evidenced.

## 18. Corrected definition of done

The remediation has two acceptance levels. **Technical deployment** requires all offline gates plus one controlled normal cycle. **Formal operational acceptance** requires five consecutive normal trading-session cycles with completed-session and post-open refresh reconciliation. The pipeline may operate between these levels only under the interim profile and must remain labelled provisional.

The remediation is formally production-ready when all of the following hold:

1. Every opportunity is retained as active, monitoring, historical or a named integrity exception.
2. Every scoreable directed thesis has valid origin, target, invalidation, hold and identity.
3. Every option assessment carries an exact contract and immutable observation identity.
4. Every actionable contract has a current, valid, two-sided quote with lineage and `EXECUTION_EXECUTABLE_NOW` evidence.
5. Every unavailable/stale/zero-bid contract is monitorable and never called executable; its activity-maturation state remains separately visible.
6. Every scoreable family is valued/ranked or has a named reason why it was not.
7. Reachability, payoff and probability fields state their assumptions, units and authority.
8. No uncalibrated score is displayed as a probability.
9. Thesis, contract, execution and macro states remain separate and non-contradictory.
10. The Intelligence Lab and coaching outputs agree with the governed read model.
11. Decisions, fills and outcomes reconcile without inferred executions.
12. Focused, full-regression, adversarial and replay suites pass.
13. One controlled technical cycle and five consecutive normal completed-session/post-open refresh cycles pass all reconciliation gates.
14. Release manifest, database backup, migration record and rollback instructions exist.
15. Execution spread limits, refresh windows, profit floor, friction model and preferred-contract hysteresis are named, versioned configuration with a domain owner.
16. Calibrated ranking meets WP4's coverage, reliability, positive skill, discrimination and ranking-lift gates; otherwise calibrated fields remain disabled while deterministic DOI continues.
17. Every normal completed-session DOI input carries `PROVIDER_SESSION_COMPLETE` evidence; partial chains are retained only as named non-normal evidence.
18. The governed pipeline and Lab read model are capital-agnostic: no account size, desk budget, affordability state or suggested contract count is consumed or projected.

There is deliberately no minimum number of daily trades or positive-EV rows. The system succeeds by accurately identifying opportunities and uncertainty, including valid no-trade conditions.

Thirty executed trades may serve as a pilot report, but they cannot alone prove positive expectancy. Expectancy claims require confidence intervals, calibration evidence and sufficient samples by direction and horizon.

## 19. Build and implementation sequence

Every stage has an entry gate, bounded implementation scope, mandatory tests, evidence artefacts and an exit gate. A later stage cannot compensate for a failed earlier invariant. Production changes are additive and feature-controlled until the relevant exit gate passes.

### Stage 0 — Design freeze, dependency baseline and recovery

**Entry:** v1.2 approved as development authority; no implementation claim outstanding without an owner.

**Build activities**

1. Freeze canonical vocabulary for provider finality, contract identity, current execution, activity maturation, monetisability and Morning refresh.
2. Freeze the provider-finality algorithm, capital-allocation boundary, rate-selection policy, trading-session convention and calibration-skill gates.
3. Enumerate the complete production import/dependency graph; fail baseline creation if an imported production file is untracked, unhashed or outside the manifest.
4. Freeze code, configuration, calendar and database hashes. The USMI contract, `macro_domain` and Worker 3 are currently tracked; the rule protects all future additions.
5. Create the claim sheet, design-to-code traceability matrix, affected-file manifest, database migration plan and rollback procedure.
6. Back up affected databases and prove restoration using copies before any production migration.

**Tests and evidence**

- Import-graph completeness and reproducibility test.
- Configuration-schema and enum collision test.
- Database backup hash and restore rehearsal.
- Baseline full regression result and known-defect manifest.

**Exit:** reproducible baseline, successful restoration and zero unresolved P0 design decisions.

### Stage 1 — Provider finality and run-condition truth

**Build activities**

1. Implement `ProviderSessionFinality` inside Run Planning/Canonical Market Evidence.
2. Persist request mode, settlement delay, official-close identity, timestamp distribution, coverage and completion basis.
3. Stop marking an option chain `COMPLETE` solely because minimum row coverage passed; distinguish complete, partial, unsettled, mismatched and insufficient evidence.
4. Require `PROVIDER_SESSION_COMPLETE` on the normal completed-session DOI bridge; retain partial chains as visible test/monitor evidence.
5. Remove every provider-quote fallback to `_utc_now()` or fetch time while retaining acquisition time as separate metadata.
6. Add run-condition and baseline-eligibility fields to `run_meta_v2` and preserve forced/dirty/replay classifications.

**Tests and evidence**

- Provider-finality unit tests across completed, partial, illiquid, delayed, wrong-session and no-close cases.
- Property test proving one 16:00 quote cannot make an otherwise partial chain complete.
- Contract test proving normal DOI rejects `PARTIAL` while a labelled test run retains it non-actionably.
- Replay of two stored option-chain sessions with expected finality classifications.

**Exit:** no normal run relies on wall clock, fetch time or one late quote as proof of completed-session evidence.

### Stage 2 — Numeric truth, units and immediate evidence capture

**Build activities**

1. Correct Layer 3 expected-move calculations to use cumulative `hold_sessions / 252` from the current single annualised forecast.
2. Publish new calculation versions and preserve legacy adapters without allowing old incremental buckets into governed calculations.
3. Complete spread fraction/percentage migration and remove undisclosed numeric defaults.
4. Deploy WP7A append-only candidate, presentation, human-decision and manual-fill contracts so new production samples are not lost.
5. Begin historical volatility validation while publishing `UNVALIDATED`, `bias_multiplier=1.0` and `bias_multiplier_applied=false`.

**Tests and evidence**

- CALL/PUT × 1–5/6–10/11–20 session unit and property matrix.
- Direct reconciliation to `annual_vol * sqrt(hold_sessions/252)`.
- Producer/consumer contract tests for every revised unit.
- Decision-without-fill adversarial test and append-only persistence test.
- Two stored-run replays with version-aware expected differences.

**Exit:** no calendar/trading-session ambiguity, silent numeric fallback or inferred fill remains on the governed path.

### Stage 3 — Canonical rate, reachability and deterministic economics

**Build activities**

1. Implement `MarketRateObservation` and its maturity, freshness, unit, default and lineage policy.
2. Add a validated adapter that may extract a candidate rate from `macro_rates_context` without granting the macro packet valuation authority.
3. Implement `VolatilityBudget`, `ReachabilityAssessment` and governed XNYS-session-to-calendar-expiry conversion.
4. Calculate flat, favourable 1-sigma, favourable 2-sigma, reachable and structural time-stop scenarios with explicit rate, dividend and friction assumptions.
5. Enforce atomic recomputation whenever OCC identity or observation dataset changes.

**Tests and evidence**

- Rate-source, unit, tenor, stale, missing and governed-default tests.
- Black–Scholes formula, arbitrage-bound and `r=q=0` total-variance properties for CALL and PUT.
- Exact-contract replacement test proving every dependent Greek/economic field changes together.
- Missing rate/dividend tests producing named states rather than zero.

**Exit:** all scoreable families can reach deterministic valuation or carry one reconciled, named data reason.

### Stage 4 — DOI production completion and independent state machines

**Build activities**

1. Reconcile governed `thesis_id` across DOI input, family, assessment and Lab projection.
2. Implement separate append-only contract-identity, current-execution and activity-maturation state machines.
3. Complete governed family generation, repair, valuation, deterministic ranking, preferred selection and alternative retention.
4. Retain low-OI and zero-volume contracts as rankable evidence; require a valid current quote only for `EXECUTION_EXECUTABLE_NOW`.
5. Implement preferred-contract hysteresis as versioned configuration and immediate replacement for terminal identity/data defects.
6. Add post-open exact-contract refresh and immutable supersession events without modifying the ticker thesis.

**Tests and evidence**

- Full state-transition matrix including repair inbound/outbound paths and activity regression.
- Adversarial tests proving OI/volume cannot grant or revoke current executability.
- CALL/PUT, ATM/OTM/ITM, horizon, quote-quality and contract-supersession matrix.
- Population reconciliation from DOI input through preferred/alternative Lab projection.

**Exit:** every directed input is assessed, monitored or recorded as a named exception; DOI deletes no valid thesis and produces no identity/economics mismatch.

### Stage 5 — Macro context and trader-facing projection

**Build activities**

1. Complete sector/industry-first macro applicability and structure evidence projection.
2. Build or migrate to `lab_signal_book_v4` from the bounded-context contracts.
3. Project thesis, monetisability, current execution, activity maturation and macro as separate conclusions.
4. Enforce the capital-agnostic boundary in configuration, contracts and presentation.
5. Regenerate coaching from the same read model and retire duplicate overlays only after field-level parity.

**Tests and evidence**

- Static and projection tests proving budgets, account sizes and suggested contract counts cannot enter the governed read model.
- Metamorphic test proving any macro change leaves direction, population and contract identity unchanged.
- Lab/coaching lineage, null, identity and contradiction tests.
- Two stored-run and two normal-cycle overlay parity reports before archive.

**Exit:** the Intelligence Lab is a faithful, complete projection and no advisory context can masquerade as authority or applied size.

### Stage 6 — Outcome maturation and probability learning

**Build activities**

1. Deploy WP7B exits, counterfactual paths, MFE/MAE, liquidity-development outcomes and attribution over the Stage 2 capture.
2. Build direction- and horizon-conditioned competing-event labels with point-in-time feature cutoffs.
3. Train interpretable benchmarks first, then candidate nonlinear models under the same temporal partitions.
4. Calibrate only out of sample and implement explicit hierarchical backoff.
5. Keep deterministic DOI active whenever a probability stratum fails its gate.

**Tests and evidence**

- Leakage, timestamp and competing-event label tests.
- Coverage, ECE, log loss, positive Brier Skill Score, confidence interval, ROC/PR discrimination and top-quantile lift reports.
- Stability reports by CALL/PUT, horizon, regime and activity state.
- Counterfactual reconciliation and missing-outcome reason coverage.

**Exit:** calibrated ranking activates only for strata demonstrating both reliable probabilities and incremental ranking skill.

### Stage 7 — Release, controlled cycle and operational acceptance

**Build activities**

1. Run focused, contract, property, adversarial, integration and complete regression suites.
2. Replay at least two pinned normal stored runs per material work package and approve only expected differences.
3. Produce release manifest, database migration evidence, governed feature profile and rollback configuration.
4. Run one controlled normal completed-session pipeline and its corresponding post-open thesis/contract refresh.
5. After technical deployment, run five consecutive normal completed-session/post-open cycles with independent reconciliation.
6. Record operator acceptance and promote the governed release profile; calibrated ranking remains separately gated by Stage 6 evidence.

**Exit:** one reconciled cycle permits technical deployment; five consecutive reconciled normal cycles permit formal operational acceptance. Any rollback trigger in Section 17 stops only the affected work package while append-only evidence is preserved.

## 20. Development work allocation

To reduce merge and authority risk, use at most two implementation workstreams concurrently:

| Workstream | Owns | Must not edit concurrently |
|---|---|---|
| A — Domain/data | canonical contracts, GARCH, reachability, DOI, ledger | Lab presentation files owned by B |
| B — Integration/presentation | Morning adapters, macro projection, Lab/coaching, release evidence | Domain formula modules owned by A |

An independent tester should review after each merge boundary, not modify implementation during validation. Shared orchestrator or schema files are integrated serially by the primary implementer.

Each stage follows:

```text
review design and current code
-> update claim sheet
-> implement one bounded change
-> run focused tests
-> run contract/adversarial tests
-> merge through the defined context boundary
-> run complete regression
-> replay stored evidence
-> record release evidence
```

## 21. Traceability to the source register

| Source fixes | Implemented through |
|---|---|
| F0.1–F0.4 | WP0 |
| F1.1, F1.5, F1.6 | WP1 |
| F1.2–F1.4 | WP2, with R:R authority rejected |
| F1.7 | WP4 |
| F2.1, F2.2, F2.4 | WP5 |
| F2.3 | WP5 advisory affordability only; automatic macro sizing rejected |
| F2.5 | WP6 derived presentation; sovereign combined state rejected |
| F3.1, F3.4 | WP3 |
| F3.2, F3.3 | WP4 |
| F3.5 | WP7 with explicit fills |
| F3.6 | WP8 with version-aware replay |
| F4.1, F4.2 | WP6 |

Additional mandatory work not explicit in the source register:

- canonical risk-free-rate bridge;
- governed thesis-ID completeness;
- Morning contract-refresh state transition;
- continuation re-underwriting;
- atomic contract/economics identity;
- actual-fill contract;
- explicit canonical units and legacy anti-corruption adapters.

## 22. Final architectural decision

Proceed with implementation only against this v1.2 design and its invariants. The source register is a useful defect inventory, but this document is the development authority for boundaries, state ownership, test gates and release acceptance.

The expected outcome is a more truthful and measurable pipeline: valid theses remain visible, option contracts are dynamically assessed, poor current execution is disclosed without destroying future opportunity, and learning is based on evidenced decisions and outcomes. Positive realised expectancy remains an empirical result to be measured, not a property that software design can assert in advance.

## 23. QA review disposition

This section preserves the disposition of every required recommendation in `AVS-QA-SD-FIX-002_design_review.md`. Acceptance here records the v1.1 incorporation; Section 24 records the subsequent independent verification and v1.2 corrections.

| Review item | Disposition | Design response |
|---|---|---|
| R1 interim operating profile | **Accepted** | Added Section 0. It protects current operation without claiming that unbuilt functionality is live. |
| R2 move ledger work earlier | **Accepted with decomposition** | WP7A candidate/decision/manual-fill capture moves to Stage 1. WP7B maturation and counterfactuals remain later because they depend on stable assessment identities and historical paths. |
| R3 validate volatility earlier | **Accepted with safety constraint** | Validation begins in Stage 1 and completes in Stage 2. An observed bias multiplier is not applied until its temporal validation and release gate pass; dependent fields disclose `UNVALIDATED` beforehand. |
| R4 baseline untracked production files | **Principle accepted; factual premise superseded** | Current inspection shows the USMI contract and 41 `macro_domain`/Worker 3 files are tracked. Stage 0 now enumerates the full import graph and fails on any future untracked production dependency, which is stronger than hashing a fixed path list. |
| R5 Risk presentation bounded context | **Superseded by owner decision 2026-09-12** | AVSHUNTER is capital-agnostic. Capacity and sizing are excluded and require a separate future portfolio-allocation bounded context. |
| R6 governed defaults | **Accepted** | Invariant 4 now permits explicit governed defaults while preserving raw missingness, source, value and applicability. WP1 inventories and removes silent-zero behaviour. |
| R7 refresh window and pre-open source | **Partially accepted** | The 09:35–09:45 ET primary refresh window and timestamp fields are adopted. The proposed futures-implied ticker-price fallback is rejected because index beta and idiosyncratic overnight events make it fabricated ticker evidence. Futures remain separate context; unavailable ticker price defers the thesis refresh. |
| R8 remove `_utc_now()` quote fallback | **Accepted** | WP0 explicitly removes fetch/current-time substitution for a missing provider quote timestamp. Missing timestamp means unavailable for execution classification. |
| R9 time basis, arbitrary hold, scenario rule and hysteresis | **Accepted with a better hold rule** | Scenarios use governed time-stop valuation and an explicit XNYS/calendar bridge. Arbitrary 1–20 session expected move is calculated directly from annual volatility rather than interpolated from rounded 5/10/20 checkpoints. The scenario profit floor and hysteresis thresholds are versioned and were approved by ACK on 2026-09-12 under `ACK-20260912-AVS-FIX-002`; both remain advisory. |
| R10 vocabulary and transition table | **Accepted** | Thesis and contract state names are now domain-prefixed; the contract transition table is explicit; run conditions extend `domain.run_planning`. |
| R11 numerical calibration acceptance | **Accepted and strengthened in v1.2** | WP4 specifies coverage, held-out sample, ECE, positive Brier skill, discrimination and ranking-lift gates plus hierarchical backoff disclosure. Failing strata remain uncalibrated. |
| R12 Black–Scholes time monotonicity | **Accepted** | The invalid universal assertion is replaced with a total-variance property under `r=q=0` and formula/arbitrage-bound tests under non-zero rates or dividends. |
| Positive uncalibrated-utility count | **Accepted as observability only** | Added to Section 16. It is prohibited as a quota, target or release condition. |
| Optional R:R in the primary Lab | **Rejected** | The user previously removed R:R, and the value conceals target timing, IV path, stop valuation and friction. The scenario payoff table exposes those assumptions. R:R may remain in explicitly labelled research exports only. |
| Provider EOD completion | **Accepted and strengthened** | Run eligibility uses XNYS calendar plus provider-completeness evidence, not 16:15 ET or a fixed UTC time alone. |
| DOI blocker evidence uncertainty | **Resolved** | The stored DOI report exists and confirms 1,218 of 1,218 generated families stopped at `FAMILY_NOT_VALUED_RATE_UNAVAILABLE`. WP3 also covers `DOI_TABLES_NOT_ACTIVATED` and `GOVERNED_CONTRACT_IDENTITY_MISMATCH`. |
| Thesis-ID location uncertainty | **Accepted as an interface investigation** | A populated final-book `thesis_id` does not disprove a failure on the earlier DOI input interface. WP3 requires identity tracing across the complete producer/consumer path before changing generation logic. |
| `historical_prices.sqlite` provisioning | **Accepted** | Added an explicit WP7 health and deferred-outcome requirement. |
| Structure evidence fields | **Accepted** | WP5 now names `hidden_state_label`, `phase` and `trigger_primary`. |
| Overlay retirement parity | **Accepted** | WP6 defines two stored-run plus two normal-cycle field-level parity checks and an archive manifest before retirement. |
| Five normal cycles before promotion | **Accepted through two gates** | One controlled cycle permits technical deployment; five consecutive normal cycles are required for formal operational acceptance. This avoids both premature sign-off and an unnecessary block on additive deployment. |
| Lab contract version collision | **Accepted** | The target read model is `lab_signal_book_v4`, unless an explicit compatible migration formally retains v3. |

### 23.1 Creative-design conclusions

The QA review exposed four opportunities to improve the architecture beyond a literal correction:

1. **Provider-complete beats clock-complete.** A clock boundary cannot prove the data exists. Run Planning now treats provider completeness as evidence and time only as an eligibility lower bound.
2. **Capture first, learn later.** The ledger is divided into immediate evidence capture and later outcome maturation, preventing lost samples without coupling early delivery to unfinished calibration.
3. **Do not interpolate what can be computed.** The system derives arbitrary 1–20 session expected moves from the underlying annual forecast, avoiding bucket-edge discontinuities and rounded-field reuse.
4. **Technical deployment is not empirical acceptance.** One controlled cycle can validate plumbing; five normal cycles validate operations; realised profitability remains a longer statistical question.

## 24. v1.1 independent verification disposition and v1.2 change record

This section records the independent validation of `AVS-QA-SD-FIX-002_v1.1_verification.md`. The verification was substantially accepted, with factual and architectural corrections incorporated into v1.2.

| Verification item | v1.2 disposition | Design change |
|---|---|---|
| 3.1 provider completeness | **Accepted with corrected mechanism** | Added the auditable `ProviderSessionFinality` contract. A chain-wide evidence bundle replaces the insufficient “latest quote at 16:00” test. |
| 3.2 capacity arithmetic | **Superseded by owner decision 2026-09-12** | Capital-allocation arithmetic is outside AVSHUNTER's monetisability domain and has been removed from configuration, contracts and Lab projection. |
| 3.3 horizon-specific forecast ambiguity | **Rejected as a current-code claim** | Current Layer 3 uses one annualised forecast. The 1–20 session rule therefore scales that value directly. A future term structure requires a new contract and model version. |
| 3.4 transition gaps | **Accepted and strengthened** | Split contract identity, current execution evidence and activity maturation into independent state machines; added repair and missing canonical states. |
| 3.5 Stage 6 wording | **Accepted** | Release plan now requires one controlled technical cycle and five consecutive normal cycles explicitly. |
| 3.6 days versus sessions | **Accepted as material** | WP1, formulas and tests now use governed XNYS trading sessions. |
| 3.7 existing macro rate packet | **Partially accepted** | The packet can seed a candidate rate, but only `MarketRateObservation` may provide valuation authority after source, tenor, freshness and unit validation. |
| R4 tracking uncertainty | **Resolved** | Current inspection confirms the USMI contract, macro domain and Worker 3 production package are tracked. The import-graph gate remains mandatory. |
| Calibration benchmark | **Verification strengthened** | Low ECE and a base-rate Brier tie do not prove ranking value. WP4 now requires positive out-of-sample skill, discrimination and lift. |

### 24.1 Revision outcome

v1.2 is the sole implementation authority for AVS-FIX-002. Earlier versions and QA documents remain evidence of design evolution, not competing specifications. Implementation must follow the staged build plan in Section 19, the two-workstream boundary in Section 20 and the release gates in Sections 17–18.
