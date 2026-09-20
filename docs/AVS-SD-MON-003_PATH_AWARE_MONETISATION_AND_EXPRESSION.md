# AVS-SD-MON-003 — Path-Aware Monetisation and Expression

**Version:** 1.0  
**Date:** 20 September 2026  
**Status:** DESIGN APPROVED FOR CONTROLLED BUILD; MODEL AND EXPRESSION AUTHORITY REMAIN DISABLED  
**Decision owner:** ACK  
**Architecture:** Domain-driven, evidence-first, capital-agnostic, human execution  
**Production authority created by this document:** None

## 1. Purpose

This design converts the current AVSHUNTER implementation, the monetisable-pipeline registers, and the 19–20 September backtest evidence into one buildable solution.

The objective is not to find a historical subset that happens to be profitable. It is to produce a governed pipeline that:

1. identifies a valid ticker thesis;
2. preserves the thesis when a current expression is unattractive;
3. evaluates shares, long calls, long puts, shares plus a long call, and shares plus a long put;
4. estimates when an expression is likely to become executable and monetisable within the 1–20-session thesis horizon;
5. exposes the evidence, uncertainty and alternatives to the human trader;
6. learns from executed and unexecuted opportunities without future leakage; and
7. promotes only behaviour that proves positive executable economics under forward stress.

This design supplements, rather than replaces:

- `docs/AVS-SD-FIX-002_MONETISABLE_PIPELINE_REMEDIATION.md`;
- `docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md`;
- the canonical data and provider-finality designs;
- the Decision and Outcome Ledger; and
- the registered backtest definitions.

Where an older document describes option-only ticket issuance, static contract selection, capital sizing, or model promotion without the gates in this document, this document governs the new work.

## 2. Inputs and evidence hierarchy

### 2.1 Governing registers

The build must maintain explicit traceability to:

- `Enhancements/backtest/SCENARIO_REGISTER_20260919.md`;
- `Enhancements/backtest/SCENARIO_REGISTER_ADDENDUM_S_ACT_20260920.md`;
- `Enhancements/backtest/SCENARIO_REGISTER_ADDENDUM_CEX_20260920.md`;
- `dropbox/macro/coaching/desk_gate/AVS-FIX-002_monetisable_pipeline_fix_register.md`; and
- `audit/pipeline_map/AVS-FIX-001_PRODUCTION_READINESS_FIX_REGISTER_20260906.md`.

Registered definitions are frozen. A changed threshold, label, population or outcome becomes a new scenario version. It must not silently overwrite an earlier result.

### 2.2 Current empirical conclusion

The 20 September tournament establishes the following:

- S-ACT activity evidence improves relative ranking but does not by itself produce positive executable returns.
- Printed volume and local expiry/moneyness activity are more useful than delta-weighted open interest alone.
- Open interest and put/call ratios describe positioning concentration, not signed buyer/seller flow.
- All tested static and learned contract selectors remain negative after ask-to-bid friction.
- A hindsight best contract remains negative when the exit horizon is fixed.
- A hindsight joint contract-and-exit oracle becomes positive in selected priority bands and remains positive under severe spread stress.
- Therefore the next testable capability is path-aware contract and exit forecasting, not another blended PCR rule or static gate.

The oracle uses future information. It proves a feasibility ceiling, not an implementable trading rule.

### 2.3 Evidence precedence

When evidence conflicts, use this precedence:

1. immutable canonical observations and provider timestamps;
2. stored run artefacts and hashes;
3. Decision and Outcome Ledger events;
4. registered, leakage-controlled backtest outputs;
5. current production contracts and configuration;
6. narrative reports and coaching material.

Narrative or model output never overrides canonical evidence.

## 3. As-is assessment that constrains the design

### 3.1 Implemented foundations to reuse

The current repository already contains production-path implementations for:

- run planning and provider finality;
- canonical price and option-chain storage;
- completed-session market profiles;
- thesis geometry and direction governance;
- thesis-conditioned contract-family generation;
- deterministic option valuation and DOI ranking;
- contract liquidity lifecycle persistence;
- macro advisory projection;
- Intelligence Lab v4 projection;
- execution-authority separation;
- Decision and Outcome Ledger persistence;
- outcome maturation and learning records;
- C12 first-passage and expression-outcome calculations; and
- Worker 3 advisory evidence.

These capabilities must be extended through their domain interfaces. The new work must not create another options database, another Lab book, another execution gate, or another parallel verdict vocabulary.

### 3.2 Current partial integrations

The following are present but not production-complete:

1. DOI runs in deterministic/advisory form, but calibrated probability activation remains disabled.
2. Outcome-learning infrastructure exists, but the latest run produced no fit-eligible records because planned-hold lineage was unavailable and option labels remained `UNDERLYING_ONLY`.
3. The latest run retained DOI exceptions but only a subset of directional families completed ranking; most exceptions were immutable quote-identity conflicts.
4. Worker 3 context exists but the latest run contained predominantly stale or sector-only ticker context. Worker 3 remains advisory.
5. Share valuation exists in C12, but ticket issuance is still option-only.
6. Combined share-plus-option expressions are not implemented.
7. Activity/PCR corrections exist in the working tree but are not yet part of a clean, tagged release or a completed-session acceptance run.
8. The latest completed run predates some committed fixes and the current uncommitted activity corrections.
9. The latest run's archive/finalisation path encountered disk exhaustion, so it is not formal production acceptance evidence.

### 3.3 Functionality not yet implemented

The following remain design or research capabilities:

- a production confluence/pattern registry;
- IA-9 interaction models;
- a continuous novelty/residual-discovery lane;
- a fitted competing-risks contract-path model;
- a fitted liquidity-maturation survival model;
- an accepted contract-switching model;
- multi-expression selection across shares and options;
- share-plus-call and share-plus-put outcome comparison;
- signed option order flow from trade prints;
- a fully populated option MFE/MAE outcome history; and
- a forward-confirmed model promotion record.

## 4. Architectural decision

AVSHUNTER will use two independent rankings and three independent state machines.

### 4.1 Ranking separation

**Opportunity rank** answers: which ticker thesis has the strongest point-in-time evidence of a favourable move within its horizon?

**Expression rank** answers: for that preserved thesis, which permitted long expression offers the best current or developing path to monetisation after friction?

An unattractive expression may not delete or reverse the underlying thesis.

### 4.2 State separation

The pipeline must keep separate:

1. **Thesis state** — valid, developed, invalidated by thesis evidence, expired, or unevaluated.
2. **Expression state** — available now, monitor, developing, superseded, unavailable, or data exception.
3. **Execution-evidence state** — executable quote, poor current quote, no two-sided quote, delayed observation, or refresh required.

No expression or quote state may be presented as thesis invalidation.

### 4.3 Human authority

The system supplies evidence and ranked alternatives. The human remains responsible for entry timing, order placement, execution and exit decisions. No component in this design allocates capital or calculates position size.

## 5. Business scope and invariants

### 5.1 Permitted expressions

The expression domain supports:

- `LONG_SHARES`;
- `LONG_CALL`;
- `LONG_PUT`;
- `LONG_SHARES_PLUS_LONG_CALL`;
- `LONG_SHARES_PLUS_LONG_PUT`; and
- `NO_CURRENT_EXPRESSION`.

Short shares, short options, spreads, long straddles and long strangles are outside the present mandate.

### 5.2 Mandatory invariants

1. A ticker thesis is discarded only by thesis invalidation, identity failure or unrecoverable data-integrity failure.
2. Entry price, option quote, spread, volume, open interest or current monetisability may change the expression state, never the thesis direction.
3. Missing values remain missing and carry a reason; they never become zero.
4. Open interest is positioning evidence. Printed volume is activity evidence. Neither is signed flow.
5. Macro is advisory context and cannot reverse direction, veto a thesis or grant execution permission.
6. The system is capital-agnostic. Research normalisation is not portfolio allocation.
7. Current quote age must be shown, but a 1–20-session thesis is not labelled stale merely because an earlier entry quote aged.
8. A new quote supersedes the prior execution observation; it does not rewrite historical evidence.
9. Models remain disabled unless their registered historical, stress and forward gates pass.
10. Every promoted output is reproducible from immutable input identities and versioned code/configuration.

## 6. Domain-driven context map

```text
Run Planning / Provider Finality
              |
              v
Canonical Market Evidence --------------------+
  prices, chains, profiles, macro, events      |
              |                                |
              v                                |
Opportunity and Thesis Context                 |
  direction, horizon, target, invalidation     |
              |                                |
              +--------------------+           |
                                   v           v
                         Expression Context
                    shares and option families
                                   |
                                   v
                         Path Forecast Context
               liquidity, payoff, competing events
                                   |
                                   v
                         Expression Decision
                 preferred now + monitored alternatives
                                   |
                +------------------+------------------+
                v                                     v
       Intelligence Lab                       Human execution
                |                                     |
                +------------------+------------------+
                                   v
                         Decision and Outcome
                                   |
                                   v
                      Research and Model Governance
```

### 6.1 Canonical Market Evidence

Owns immutable observations, dataset identity, provider/fetch timestamps, completed-session truth and retrieval. It does not classify trades.

### 6.2 Opportunity and Thesis

Owns ticker, governed direction, thesis origin, horizon, target, invalidation, structure evidence and thesis lifecycle. It does not select an option contract.

### 6.3 Expression

Owns permitted instruments, contract families, current expression evidence and alternatives. It may return `NO_CURRENT_EXPRESSION` while retaining the thesis.

### 6.4 Path Forecast

Owns probabilities and distributions for future path events. It consumes frozen features and returns advisory estimates with uncertainty. It cannot grant authority.

### 6.5 Expression Decision

Combines deterministic economics and accepted model outputs to rank expressions. Until promotion, it records shadow decisions beside the deterministic production result.

### 6.6 Decision and Outcome

Owns immutable decisions, counterfactuals, subsequent paths and outcome labels. It is the learning authority, not a mutable cache.

### 6.7 Research and Model Governance

Owns scenario registration, datasets, partitions, leakage controls, trials, acceptance evidence, model registry and activation state. Research code cannot write production decisions.

## 7. Core domain contracts

### 7.1 `OpportunityThesis`

Required fields:

```text
thesis_id
run_id
ticker
direction                  CALL | PUT | NON_DIRECTIONAL
origin_session
evidence_cutoff_utc
planned_hold_sessions      1..20
target_spot
invalidation_spot
target_source
invalidation_source
structure_state
regime_context
macro_context_id
thesis_state
thesis_reason
input_dataset_ids
calculation_version
```

### 7.2 `ExpressionCandidate`

Required fields:

```text
expression_id
thesis_id
expression_type
option_symbol              nullable for shares
expiry, strike, right      nullable for shares
quote_observed_at_utc
quote_provider_at_utc
bid, ask, midpoint
spread_pct_of_mid
bid_size, ask_size
volume, open_interest
delta, gamma, theta, vega, iv
dte
family_scope
data_quality_state
```

For combined expressions, each leg is an immutable `ExpressionLeg`. Research weights are stored as `normalisation_weights`, explicitly labelled `NOT_CAPITAL_ALLOCATION`.

### 7.3 `ActivityEvidence`

```text
whole_chain_oi_pcr
delta_weighted_oi_pcr
whole_chain_volume_pcr
expiry_oi_pcr
expiry_volume_pcr
delta_region_oi_pcr
delta_region_volume_pcr
near_atm_oi_pcr
near_atm_volume_pcr
premium_residual
iv_change
scope
observation_cutoff_utc
missingness_flags
uncertainty_state
```

Categorical PCR states use the frozen S-ACT thresholds but remain concentration labels, never directional votes.

### 7.4 `PathForecast`

```text
forecast_id
model_id
training_cutoff_session
feature_schema_version
p_executable_1s
p_executable_2s
p_executable_3s
p_profit_10_before_terminal
p_profit_25_before_terminal
p_profit_50_before_terminal
p_target_before_invalidation
p_invalidation_before_target
p_time_stop_first
expected_mfe
expected_mae
expected_sessions_to_executable
expected_sessions_to_monetisation
uncertainty_interval
out_of_domain_state
```

### 7.5 `ExpressionDecision`

```text
decision_id
thesis_id
decision_time_utc
preferred_expression_id
preferred_state             READY_NOW | MONITOR | DEVELOPING | NO_CURRENT_EXPRESSION
monitored_alternatives[]
deterministic_utility
model_probability
model_activation_state
switch_margin
switch_reason
human_narrative
```

## 8. Data flow

### 8.1 Completed-session preparation

1. Resolve the required completed session through Run Planning.
2. Finalise canonical prices, option chains, market profiles, macro packet and event evidence.
3. Build or update the ticker thesis without using future observations.
4. Generate the complete governed option family and share expression.
5. Compute deterministic economics for every candidate expression.
6. Record activity evidence at its correct chain, expiry, delta-region and contract scopes.
7. Produce shadow path forecasts only when an approved research model is available.
8. Publish preferred and monitored expressions without discarding the ticker.
9. Persist every candidate, decision and input identity.

### 8.2 Pre-open thesis validation

Pre-open validation answers whether overnight evidence invalidated or materially developed the ticker thesis. It does not require a fresh executable option quote to preserve the thesis.

### 8.3 Post-open expression refresh

After current prices and quotes become available:

1. refresh underlying price and option execution observations;
2. recompute gap/continuation evidence;
3. update expression executability and economics;
4. re-rank the existing family plus eligible new contracts;
5. apply switching hysteresis;
6. present the updated expression decision to the trader.

An overnight gap beyond the anticipated move triggers a continuation/reversal assessment. It does not automatically invalidate the thesis and does not automatically recommend chasing the move.

### 8.4 Outcome maturation

For every retained opportunity and every monitored expression:

- collect the underlying path for 1–20 sessions;
- collect all observable option bid/ask marks without backfilling unavailable quotes as zero;
- label first executable session;
- label first +10%, +25%, +50%, +100%, +200% and +500% bid-realised threshold;
- record MFE and MAE;
- record target, invalidation and time-stop ordering;
- identify the best alternative contract and first economically defensible switch time; and
- distinguish underlying-only from option-complete outcomes.

## 9. Algorithms and models

### 9.1 Deterministic baseline

Deterministic valuation remains the production baseline until models pass promotion gates. It must calculate:

- reachable target for the governed hold;
- Black–Scholes or approved valuation at intermediate sessions, target and invalidation;
- executable ask-entry/bid-exit friction;
- theta and IV shock sensitivities;
- contract runway;
- current liquidity state; and
- share-path return for the same thesis scenarios.

It must not assume that the structural target occurs at expiry.

### 9.2 Liquidity-maturation model

Use a discrete-time survival or hazard model as the interpretable benchmark.

For expression `i` at session `t`:

```text
h_liq(i,t) = P(first executable observation occurs at t |
               not executable before t, evidence available at t0)
```

Outputs are cumulative probabilities over one, two and three sessions. Low OI or volume is a feature, not a rejection gate.

### 9.3 Competing-risks path model

The path model estimates mutually competing first events:

- profit threshold reached;
- invalidation reached;
- time stop reached;
- contract ceases to be usable;
- expression is superseded by a materially better alternative.

Start with cause-specific logistic hazards. Nonlinear challengers may be tested only after the benchmark and calibration are reported.

### 9.4 Monetisation estimator

For a given expression and profit threshold `q`:

```text
P_monetise(q) = P(executable before terminal)
                × P(profit q before invalidation/time stop | executable)
```

The production decision must not multiply uncalibrated point estimates without reporting uncertainty. The Lab shows components separately.

### 9.5 Expression comparison

Expression comparison is performed on common scenarios and normalised risk units. It reports:

- probability of positive executable return;
- probability of +25% for options and the governed share-equivalent hurdle;
- expected executable return;
- MFE and MAE;
- time to monetisation;
- downside at thesis invalidation;
- sensitivity to spread, IV and delayed entry; and
- uncertainty/coverage.

Research normalisation does not specify dollars, contracts or account exposure.

### 9.6 Contract switching

Keep the current preferred contract unless an alternative:

1. has complete point-in-time evidence;
2. covers the remaining thesis horizon;
3. exceeds the current expression score by the governed hysteresis margin;
4. remains superior under wider-spread stress; and
5. does not rely on next-session OI or future outcomes.

Every switch creates an append-only supersession event.

### 9.7 Opportunity interactions and confluence

IA-9 interactions are research features, not hard-coded rules. The first registered set is:

- compression × relative strength;
- structure × IV state; and
- early pressure × regime.

They enter an incremental-information test against the opportunity baseline. A confluence label is permitted only after its components demonstrate point-in-time incremental value. It may improve opportunity rank but cannot override thesis integrity.

### 9.8 Novelty lane

Residual opportunities that do not match known patterns remain visible as `UNCLASSIFIED_EVIDENCE`, not blocked. A novelty model may cluster them for research, but it cannot invent direction or execution authority.

## 10. Intelligence Lab contract

The Lab must present one coherent row per thesis, with drill-down alternatives.

### 10.1 Thesis panel

- governed direction and source;
- thesis state and plain-language reason;
- target, invalidation and hold;
- overnight gap and continuation/reversal assessment;
- structure, relative strength and market-profile evidence;
- macro and sector context, explicitly advisory.

### 10.2 Expression panel

- preferred expression now;
- share alternative;
- preferred option and monitored alternatives;
- current bid/ask, sizes, spread and quote timestamp;
- deterministic economics;
- liquidity-maturation probability;
- monetisation probability by horizon;
- current state: ready, monitor, developing, no current expression or data exception;
- switch condition and uncertainty.

### 10.3 Activity panel

Show OI positioning, printed-volume activity and local-scope ratios separately. Do not display BULLISH/BEARISH from PCR alone. When evidence is ambiguous, say so.

### 10.4 Authority language

Use `THESIS_VALID`, `THESIS_INVALIDATED`, `EXPRESSION_READY`, `MONITOR_EXPRESSION`, `NO_CURRENT_EXPRESSION` and `DATA_EXCEPTION`. Do not reuse `BLOCKED` for an unattractive contract.

## 11. Research and validation design

### 11.1 Populations

- **H:** pre-fix recorded books for failure localisation only.
- **H+:** legacy recommendations with daily chain backfill; useful but selection-biased.
- **U:** underlying history for direction, magnitude and timing.
- **N:** fixed-pipeline forward population; required for promotion.

No result from H or H+ alone may activate production behaviour.

### 11.2 Temporal controls

- purged walk-forward partitions;
- embargo at least equal to the maximum outcome overlap;
- immutable training cutoff;
- ticker/session clustering;
- untouched later-session holdout;
- separate calibration and test sets;
- every attempted variant recorded in the ledger.

### 11.3 Required stress matrix

At minimum:

- CALL and PUT separately;
- shares and combined expressions separately;
- 1/3/5/10/20-session horizons where coverage permits;
- spread widened 25% and 50%;
- quote dropout 10% and 25%;
- activity-field dropout 10% and 25%;
- stale and one-session-lagged OI;
- missing printed volume;
- IV crush and IV expansion;
- gap continuation and reversal;
- high/low volatility regimes;
- SPY bull/bear regimes;
- removal of the best 1%;
- leave-one-session-out and leave-one-sector-out checks;
- corporate-event and no-event partitions; and
- low-OI developing contracts retained as a separate stratum.

### 11.4 Promotion gates

A model or rule may become a production replication candidate only when:

1. ask-to-bid mean return is positive;
2. the mean remains positive with spreads widened by 50%;
3. paired session-level improvement has `t >= 2.0` with positive mean delta;
4. the sign is positive in at least two independent sessions;
5. N has at least 40 closed outcomes in the relevant stratum;
6. calibration and uncertainty are acceptable on the untouched holdout;
7. outcome and quote coverage are disclosed and above the governed threshold;
8. no future-data dependency exists;
9. +100%, +200% and +500% tail recall is not materially degraded; and
10. PBO and deflated Sharpe are reported after ten or more trials in a family.

Promotion means controlled shadow replication first, not immediate trading authority.

## 12. Traceability to M1–M24

| Register item | Design response | Closure evidence |
|---|---|---|
| M1 direction skill | Opportunity model and regime/interaction tests; never inferred from PCR | U and N holdout results |
| M2 destructive gate | Non-discard thesis invariant | Reconciliation: input = retained + integrity exceptions |
| M3 premature stop | Competing events; no-stop and fair-value policies tested | S-EXIT replication and N outcomes |
| M4 insufficient runway | Horizon-covered family generation | Zero selected contracts shorter than governed requirement |
| M5 friction | Ask-to-bid authority and spread stress | Positive stressed executable economics |
| M6 missing convex tail | Full family and mandatory tail metrics | TC-1/2/3 evidence |
| M7 missing/delayed data | Explicit completeness and missingness states | Coverage report, no zero substitution |
| M8 integrity/GEX | Canonical lineage; macro remains advisory | Freshness and dataset-id reconciliation |
| M9 empty days | Monitoring states instead of opinion blocks | Daily retained-opportunity counts |
| M10 no forward evidence | N population and promotion gates | At least 40 closed outcomes per promoted stratum |
| M11 product framing | Separate alert quality, executable expectancy and tail capture | Layered scorecard |
| M12 ranking objective | Opportunity/expression split | Independent rank calibration |
| M13 driftless valuation | Deterministic cost baseline plus measured edge only | S-VAL-2 and holdout calibration |
| M14 structure conflict | Conditional interaction research | S-DIR-3 and IA-9 |
| M15 stop/target geometry | Integrity validation, not silent repair | Geometry exception count |
| M16 unused features | Incremental ablation before inclusion | S-ABL and feature contract |
| M17 entry timing | Pre-open thesis vs post-open expression separation | S-TIME and gap tests |
| M18 regime mix | Conditional opportunity evidence, advisory macro | S-REG, no macro veto |
| M19 hold length | Multi-horizon path labels | 1–20 session coverage |
| M20 expensive IV | IV percentile, forecast ratio and stress | S-IV and expression comparison |
| M21 event convexity | Event identity and event/no-event strata | S-CONV-2 |
| M22 flat features | Raw continuous evidence and variance checks | Non-constant diagnostics |
| M23 early entry | Liquidity and monetisation hazards | S-ANT and delay-cost comparison |
| M24 concentration | Sector/root-cause diagnostics | Portfolio-neutral concentration report |

## 13. Delivery plan

### Phase 0 — Baseline and release truth

1. Freeze the current production-path code, config and schema hashes.
2. Classify working-tree changes as production, research evidence or generated artefacts.
3. Commit the corrected activity/PCR implementation and its tests separately.
4. Update the obsolete timestamp test without weakening provider-time protection.
5. Resolve disk capacity and prove archive finalisation.
6. Create a release manifest and rollback package.

**Exit:** clean tagged baseline; full regression green; stored run reproducible.

### Phase 1 — Close current partial integrations

1. Repair immutable option-observation identity so repeated same-run observations are idempotent and genuinely different observations supersede rather than conflict.
2. Restore planned-hold lineage into outcome-learning records.
3. Capture option bid paths so option outcomes are no longer `UNDERLYING_ONLY` where data exists.
4. Reconcile DOI family population: generated, assessed, ranked, exception-retained and projected.
5. Repair macro field and Worker 3 context completeness without granting authority.

**Exit:** no unexplained DOI loss; fit-eligible outcomes begin accumulating; finalisation succeeds.

### Phase 2 — Path-label factory

1. Extend outcome maturation to every monitored contract family.
2. Emit first-executable, threshold-passage, MFE, MAE and event-order labels.
3. Add best-alternative and first-valid-switch labels.
4. Add share and combined-expression counterfactuals with explicit research normalisation.
5. Verify append-only/idempotent replay.

**Exit:** label reconciliation passes and leakage audit is clean.

### Phase 3 — Research tournament

1. Run interpretable liquidity survival benchmark.
2. Run cause-specific competing-event benchmark.
3. Test S-ACT features incrementally.
4. Test IA-9 interactions and ablations.
5. Test shares, calls, puts and combined expressions.
6. Run registered stress matrix and log every trial.
7. Preserve an untouched later-session holdout.

**Exit:** evidence report; no production activation.

### Phase 4 — Shadow expression service

1. Introduce versioned `PathForecast` and `ExpressionDecision` contracts.
2. Wrap accepted research models behind provider-neutral local interfaces.
3. Persist shadow preferred expression and monitored alternatives.
4. Compare shadow decisions with deterministic DOI and actual outcomes.
5. Implement hysteresis and supersession events.

**Exit:** deterministic production behaviour unchanged; complete shadow evidence.

### Phase 5 — Intelligence Lab projection

1. Add expression and activity panels.
2. Surface share and combined alternatives.
3. Remove misleading PCR direction language and contract-level `BLOCKED` language.
4. Add plain-language reason, uncertainty, quote time and switch condition.
5. Prove API/schema compatibility and UI defence-in-depth.

**Exit:** Lab matches canonical decisions and retains all valid theses.

### Phase 6 — Forward acceptance and controlled promotion

1. Accumulate N outcomes.
2. Run the untouched holdout and all promotion gates.
3. Shadow for at least the governed forward period.
4. Approve a model/version/config combination explicitly.
5. Promote only expression ranking; keep execution human-only.
6. Retain immediate rollback to deterministic DOI.

**Exit:** signed release evidence or explicit rejection/no-evidence decision.

## 14. Test architecture

### 14.1 Unit and property tests

- state machines cannot cross domain boundaries;
- missing values never become zero;
- PUT/CALL geometry is symmetric;
- quote identity is idempotent;
- provider and fetch timestamps remain distinct;
- expression states cannot invalidate a thesis;
- OI/volume cannot generate directional authority;
- switching requires a governed margin;
- no capital fields enter decisions.

### 14.2 Integration tests

- canonical chain → family → valuation → expression projection;
- completed session → pre-open thesis → post-open expression refresh;
- Decision Ledger → outcome maturation → learning record;
- Lab API parity with canonical expression decision;
- replay from immutable dataset IDs;
- archive/finalisation under constrained disk conditions.

### 14.3 Adversarial tests

- forged BUY/GO with invalid thesis;
- future OI injected into entry-time features;
- completed-session volume used before close;
- stale cache newer than canonical provider observation;
- zero/NaN coercion;
- contract switch driven solely by outcome knowledge;
- macro reversal of ticker direction;
- PCR presented as signed institutional flow;
- unavailable contract deleting a ticker;
- model activated without a matching registry record.

### 14.4 Acceptance packs

Every phase produces:

- requirement-to-test traceability;
- code/config/schema hashes;
- focused and full regression output;
- input/output reconciliation;
- known exceptions;
- rollback instructions; and
- a claim sheet distinguishing offline closure from live acceptance.

## 15. Observability

Each run must report:

- thesis input, valid, invalidated, expired and exception counts;
- expression families generated and retained;
- candidates assessed, ranked, monitored and ready;
- quote, activity, IV and outcome coverage;
- option identity conflicts and supersessions;
- model available, out-of-domain and abstention counts;
- expression switches and hysteresis retentions;
- outcome labels complete, underlying-only, deferred and excepted;
- share/call/put/combined expression distribution;
- right-tail recall; and
- exact population reconciliation.

No successful stage may be followed by an unreconciled final dispatcher or archive failure and still be called an accepted run.

## 16. Rollback and safety

Rollback triggers include:

- thesis deletion caused by expression evidence;
- look-ahead or timestamp lineage breach;
- input/output population mismatch;
- model/version not found in the registry;
- materially worse +100%/+200% tail recall;
- executable economics failing the approved stress gate;
- Lab/canonical decision mismatch;
- unexpected production database mutation; or
- archive/finalisation failure that leaves release evidence incomplete.

Rollback disables model and expression ranking, restores deterministic DOI projection, preserves all recorded observations and leaves the Decision and Outcome Ledger append-only.

## 17. Explicit non-goals

This design does not:

- promise positive expectancy before forward evidence;
- allocate capital or size positions;
- automate brokerage execution;
- infer signed flow without trade-print evidence;
- use macro as trade authority;
- convert research oracles into rules;
- require every valid thesis to have an immediately tradeable option; or
- remove human judgement over entry and exit.

## 18. Definition of done

The enhancement is production-ready only when:

1. the production baseline is clean, tagged, reproducible and archivable;
2. all valid theses reconcile through the pipeline without expression-driven deletion;
3. DOI and outcome-learning partial integrations are closed;
4. path labels exist for the required horizons and option outcomes are materially populated;
5. the selected model passes the registered historical, stress and forward gates;
6. every permitted expression has comparable point-in-time evidence;
7. the Lab clearly separates thesis, expression and execution evidence;
8. deterministic fallback is tested;
9. execution remains human-only; and
10. a signed release manifest identifies the exact code, configuration, model and datasets.

Until these conditions hold, path forecasting and multi-expression ranking remain shadow advisory capabilities. The current deterministic pipeline may continue to surface opportunities, but it must not claim that the new monetisation model is proven.

## 19. Final decision

Proceed with Phase 0 and Phase 1 before building a predictive path model.

The correct technical direction is a thesis-preserving, path-aware expression system built on the existing DOI, canonical stores and Decision and Outcome Ledger. The backtest evidence rejects another static contract selector. It supports learning the joint timing of liquidity, contract payoff and exit while retaining shares and monitored option alternatives.

Production promotion is evidence-led: positive executable returns under spread stress, forward confirmation and intact convex-tail capture are required. Model accuracy alone is insufficient.
