# AVS-SD-DOI-001 — Dynamic Options Intelligence

**Status:** DOI-1 through DOI-10 implemented and offline accepted; production calibrated ranking remains unavailable until real DOI-7 cohorts mature and pass DOI-8/9 gates  
**Version:** 1.1  
**Date:** 2026-09-10  
**Scope:** Long single-leg CALL and PUT opportunities with governed 1–20 trading-session theses  
**Decision authority:** None. This capability ranks and monitors option contracts; it cannot validate or invalidate the underlying thesis and cannot grant capital.

## 1. Executive decision

AVSHUNTER should replace its static, single-contract Options Intelligence interpretation with a dynamic, thesis-conditioned contract-family capability.

The capability must preserve three independent questions:

1. **Is the underlying thesis still valid?** Governed by Discovery/Vanguard and revalidated by Morning Gate.
2. **Which option contract currently expresses that thesis most effectively?** Answered by Dynamic Options Intelligence (DOI).
3. **Should the trader enter, wait, repair, roll or exit?** The system presents evidence and warnings; the human trader is the sole execution authority.

A contract that is unattractive at one observation must not cause the ticker thesis to be deleted. The contract can mature, deteriorate, or be superseded while the underlying thesis remains active. DOI therefore manages a contract-family lifecycle and probability estimates, not a permanent binary verdict.

This design supersedes any interpretation in which `eil_v3_verdict=BLOCKED`, a current spread, low open interest, zero current volume, a missing live quote, elapsed entry timing, or an exit condition invalidates or removes an otherwise governed ticker thesis. Every opportunity remains visible. Automated states change its monitoring and evidence classification, never its availability to the human trader.

### 1.1 Non-discard principle

AVSHUNTER shall not discard, hide, permanently invalidate or automatically close an opportunity because of entry quality, exit timing, elapsed horizon, spread, liquidity, premium, IV, current price, or a model score.

The pipeline may state observable facts and risks—such as `INVALIDATION_LEVEL_BREACHED`, `TARGET_TOUCHED`, `HORIZON_ELAPSED`, `CONTRACT_EXPIRED`, `WIDE_SPREAD`, or `QUOTE_UNAVAILABLE`—but the row remains in the governed opportunity history and remains visible in the Intelligence Lab. The human decides whether to enter, wait, roll, ignore or close.

An expired option contract cannot become tradeable again. In that case the expired contract remains visible as history and, if the ticker thesis remains under observation, DOI generates a new eligible contract family. A thesis whose price condition was breached may remain in a recovery-monitoring state and be re-evaluated if price returns.

## 2. Problem statement

The current pipeline makes a principally static choice from an option chain and then passes that selected contract into EIL. Its selector uses useful but hand-weighted features—delta fit, DTE fit, theta efficiency, vega and liquidity—but that score is not a probability of liquidity maturation or contract monetisation.

The production failure mode is a category error:

- a ticker thesis is a multi-session underlying hypothesis;
- a selected option is a time-specific instrument observation;
- an entry quote is a momentary execution condition.

Treating a poor contract observation as a failed ticker thesis removes developing opportunities. Treating a good ticker thesis as proof that any option will make money creates the opposite false positive.

DOI must therefore model:

- the probability and timing of the underlying move;
- the probability that invalidation occurs before the favourable move;
- the option value under multiple price/time/IV paths;
- the probability that contract liquidity becomes executable;
- uncertainty arising from missing, sparse or out-of-distribution evidence;
- changes in the preferred contract as the thesis develops.

## 3. Goals

The design shall:

1. Retain every valid underlying thesis even when no option is executable now.
2. Generate and preserve a governed family of candidate contracts.
3. Re-evaluate that family using completed-session, morning and optional intraday observations.
4. Produce calibrated probabilities when adequate training evidence exists.
5. Clearly distinguish model probabilities from deterministic scores and scenario outputs.
6. Use Phantom history without creating a second source of truth for raw market data.
7. Learn from executed and unexecuted candidates using point-in-time outcomes.
8. Support CALL and PUT asymmetry.
9. Recompute all contract-specific fields whenever the preferred contract changes.
10. Keep macro, EIL/DOI, EV, Phantom and automated execution/exit assessments advisory; the human retains execution authority.

## 4. Non-goals

The first release will not:

- trade spreads, straddles, strangles or other multi-leg/exotic strategies;
- permit a model to change the governed direction;
- permit macro to approve, reject or reverse a trade;
- perform automatic broker execution;
- describe an uncalibrated score as a probability;
- infer true order flow from top-of-book snapshots;
- guarantee profitability;
- replace the Morning Gate thesis-validity function;
- automatically discard or hide an opportunity because an entry/exit condition is unfavourable;
- automatically close a human-held position;
- require a fresh quote merely to decide whether the underlying thesis remains valid.

## 5. Domain-driven boundaries

### 5.1 Thesis domain

**Owner:** Discovery/Vanguard plus Morning Gate validation.  
**Aggregate:** `UnderlyingThesis`.  
**Identity:** immutable `thesis_id` plus calculation version.

Owned fields include:

- ticker;
- governed direction;
- thesis origin price and timestamp;
- structural target;
- authoritative invalidation;
- planned hold in trading sessions;
- thesis evidence cutoff;
- thesis state and supersession lineage.

This domain records whether thesis conditions are confirmed, breached, recovered, target-touched or elapsed. These are observable lifecycle states, not instructions to delete the opportunity. No automated state removes the row from the opportunity history or Intelligence Lab.

### 5.2 Option observation domain

**Owner:** Canonical Data System.  
**Aggregate:** immutable option-chain or exact-contract observation.

Owned fields include OCC symbol, strike, expiry, side, bid, ask, sizes, volume, open interest, IV, Greeks, underlying price, provider timestamp, session, dataset ID, content hash and quality flags.

This is the source of truth for current and completed-session observations. Missing values remain null with explicit quality states; they are never converted to economic zero.

### 5.3 Contract-family domain

**Owner:** Dynamic Options Intelligence.  
**Aggregate:** `ContractFamily`, keyed by `thesis_id` and a versioned family policy.

It owns candidate generation, per-contract assessment, ranking, preferred-contract selection, alternatives and supersession. It cannot change the underlying thesis.

### 5.4 Historical options analytics domain

**Owner:** Phantom.  
**Role:** historical, read-optimised projection over canonical observations plus derived features.

Phantom supplies IV, gamma, liquidity and outcome distributions. Raw observations must retain their canonical dataset IDs so Phantom never becomes a conflicting raw-data authority.

### 5.5 Execution domain

**Owner:** Human trader.  
The Execution Gate becomes a deterministic evidence and warning service. It may identify unavailable quotes, breached conditions, excessive gaps, poor liquidity or data defects, but it cannot hide the opportunity, automatically reject entry, automatically close a trade or grant capital. DOI can recommend monitoring, a limit price or a preferred contract; every execution decision remains human.

### 5.6 Learning domain

**Owner:** Decision and Outcome Ledger.  
It stores every accepted and rejected thesis/contract assessment and its subsequent point-in-time outcomes. Phantom may consume these labels as a projection, but the ledger remains the outcome authority.

## 6. Authority matrix

| Decision | Owner | DOI/Phantom role |
|---|---|---|
| Governed CALL/PUT direction | Thesis domain | Consume only |
| Target/invalidation/hold | Thesis domain | Consume only |
| Morning thesis condition | Morning Gate | Consume only; result remains visible even when breached |
| Candidate contract family | DOI | Own |
| Current preferred contract | DOI | Own, advisory to execution |
| Contract liquidity state | DOI | Own |
| Contract monetisation estimate | DOI | Own, advisory |
| Macro/sector context | Macro domain | Advisory feature only |
| Entry/exit warning | Execution Gate | Consume only; no automatic discard |
| Capital and final order/fill | Human/broker workflow | No authority |

Every DOI and Phantom output must carry:

```text
decision_authority = NONE
can_change_direction = false
can_invalidate_thesis = false
can_grant_capital = false
```

## 7. Core domain objects

### 7.1 UnderlyingThesisRef

Contains immutable references to the governed thesis rather than copied, independently recomputed values.

Required fields:

- `thesis_id`
- `thesis_version`
- `ticker`
- `governed_direction`
- `origin_spot`
- `origin_timestamp_utc`
- `target_spot`
- `invalidation_spot`
- `planned_hold_sessions`
- `planned_hold_source`
- `evidence_cutoff_utc`

### 7.2 ContractCandidate

Identified by `thesis_id + OCC symbol + observation_dataset_id`. It contains observation data, family membership and quality state. The same OCC symbol at a later timestamp is a new observation, not a mutation of the old observation.

### 7.3 ContractAssessment

An immutable calculation result containing:

- liquidity probabilities by horizon;
- scenario payoffs;
- probability of monetisation;
- expected net return and downside;
- model uncertainty and applicability;
- ranking utility;
- model, feature and calculation versions;
- complete input lineage.

### 7.4 PreferredContractDecision

Contains the selected OCC symbol, alternatives, selection reason, score margin, prior preferred contract and supersession reason. It grants no capital.

## 8. State models

### 8.1 Thesis states

```text
THESIS_DEVELOPING
THESIS_ACTIVE
THESIS_VALIDATED
THESIS_CONDITION_BREACHED
THESIS_RECOVERING
TARGET_TOUCHED
HORIZON_ELAPSED_REASSESS
THESIS_DATA_INSUFFICIENT
```

### 8.2 Contract-entry states

```text
CONTRACT_MONITOR
CONTRACT_LIQUIDITY_DEVELOPING
CONTRACT_ENTRY_ACCEPTABLE
CONTRACT_LIMIT_PRICE_REQUIRED
CONTRACT_REPAIR_REQUIRED
CONTRACT_DATA_INSUFFICIENT
CONTRACT_DEGRADED
CONTRACT_SUPERSEDED
CONTRACT_EXPIRED
```

These are a new bounded-domain vocabulary. They must not be added as new meanings of the overloaded legacy `eil_v3_verdict` enum.

### 8.3 Transition rules

- A contract state cannot invalidate a thesis.
- `CONTRACT_DATA_INSUFFICIENT` is not economic zero and is not a negative forecast.
- No thesis or contract state deletes or hides an opportunity.
- Entry and exit conditions are advisory observations, not terminal verdicts.
- A breached thesis condition remains visible as `THESIS_CONDITION_BREACHED` and may transition to `THESIS_RECOVERING` if price returns.
- `HORIZON_ELAPSED_REASSESS` requests human reassessment; it is not automatic rejection.
- A monitor contract may become entry acceptable when its quote, activity or payoff geometry improves.
- An acceptable contract may degrade through adverse price movement, IV, time loss or liquidity deterioration.
- An expired contract remains historical and cannot be reused; a still-observed ticker may receive a new eligible family under an append-only reassessment version.
- A preferred contract may be superseded only by another member of the same governed thesis family, unless a new reassessment/thesis version is created.
- Supersession is append-only; prior observations and rankings remain queryable.

## 9. Data requirements and reuse

### 9.1 Current/canonical evidence

DOI shall reuse canonical data before making a provider request. A provider call is permitted only when the required ticker/session/scope is missing or the invocation explicitly requires a newer observation.

Required option fields where available:

- bid, ask, bid size, ask size;
- volume and open interest;
- IV, delta, gamma, theta and vega;
- strike, expiry, DTE and side;
- underlying price and observation timestamp;
- quote-quality and source lineage.

Dormant, breached or elapsed opportunities remain visible. To control API use, they do not trigger repeated option-chain calls until the shared underlying-price feed shows a governed reactivation condition or the operator requests a refresh. This is an acquisition state, not deletion. Expired contracts are never queried as live contracts.

### 9.2 Phantom history

Phantom shall provide historical features including:

- spread distribution by ticker, side, DTE, delta and moneyness;
- probability and time to two-sided/executable liquidity;
- volume and OI development;
- IV level, skew, entropy and transition behaviour;
- gamma and delta trajectories;
- option MFE/MAE and return-path distributions when labels exist;
- CALL/PUT asymmetries.

Phantom receives canonical dataset IDs and must not refetch the same chain independently.

### 9.3 Put/call contextual evidence

Put/call ratios complement rather than replace open interest. They are chain, expiry, strike-region or delta-bucket features—not attributes of one contract.

Required contextual features are:

- total volume PCR and OI PCR;
- expiry-specific PCR;
- near-the-money and target-region PCR;
- change in PCR;
- put/call IV skew;
- premium-flow imbalance when actual prints support it.

Individual-contract activity uses quote, sizes, volume, volume/OI turnover, changes across observations, quote update rate and distance-to-strike. When only snapshots exist, the system must not claim signed order flow.

### 9.4 Time units

Planned hold is governed in trading sessions. Option expiry is calendar time. All valuation must convert through the exchange calendar and exact timestamps. Direct subtraction of session count from calendar DTE is prohibited.

## 10. Contract-family generation

The generator consumes the governed direction and creates only long single-leg contracts of that side.

Hard exclusions from **preferred-contract eligibility** are limited to structural impossibility:

- wrong option side;
- expired contract;
- invalid OCC identity;
- DTE unable to outlive the governed hold plus buffer;
- negative or crossed quote observation;
- impossible strike/expiry fields.

These exclusions apply to the unusable contract observation, not to the ticker opportunity. The excluded observation and reason remain in the family audit, and the ticker remains visible even when no currently eligible contract exists.

One-sided or incomplete quotes may remain monitorable but cannot be classified as presently executable. OI, volume, PCR, IV percentile and ordinary spread thresholds are ranking/confidence evidence, not thesis-deletion gates.

The strike region must be conditioned on spot, target, invalidation, expected move and direction. A broad governed safety boundary may prevent extreme contracts, but a fixed narrow delta band must not preselect the answer. Delta is both a family feature and a model output at future scenarios.

Every generated family shall retain enough alternatives across at least:

- strike/moneyness;
- expiry/DTE;
- current liquidity quality;
- target reachability.

The complete tested-family audit must be persisted even when a bounded subset is displayed.

## 11. Probability and valuation architecture

### 11.1 Model A — Underlying path and event-order model

Estimates:

- distribution of move magnitude within the remaining horizon;
- probability of target before invalidation;
- time-to-target distribution;
- probability of an adverse excursion before favourable monetisation.

Inputs include governed thesis geometry, historical price/volatility features, regime and market structure. Macro may be an advisory explanatory feature only and cannot reverse direction or block a thesis.

### 11.2 Model B — Liquidity-transition model

Estimates for each contract:

- probability of a valid two-sided quote within 1, 2, 3 and remaining-horizon sessions;
- probability of spread entering an executable/reviewable range;
- expected sessions to liquidity maturation;
- probability that observed liquidity deteriorates.

Initial candidates include discrete-time survival/logistic baselines and a gradient-boosted survival model. The interpretable baseline must remain available for comparison.

### 11.3 Model C — Volatility-transition model

Estimates conditional IV distributions for early, middle and late favourable/adverse paths. CALL and PUT behaviour must be modelled separately or with explicit side interactions.

The first deterministic release shall calculate base, IV-contraction and IV-expansion stresses. A learned model may replace scenario weights only after calibration evidence exists.

### 11.4 Model D — Contract valuation

Every contract is revalued over a scenario grid covering:

- early, mid and late favourable movement;
- invalidation/adverse movement;
- base, contracted and expanded IV;
- entry and exit friction;
- dividends, ex-dividend window and corporate-action flags.

A dividend-adjusted Black–Scholes implementation is acceptable for advisory v1 only if every row discloses the approximation and flags cases where American exercise effects may be material, including sufficiently ITM puts. Flagged cases must have lower applicability/confidence or a more suitable American approximation.

### 11.5 Model E — Monetisation estimator

Primary outputs:

- `p_positive_return_before_horizon`;
- `p_return_hurdle_before_horizon`;
- `p_target_before_invalidation`;
- `expected_net_return`;
- `expected_downside`;
- `expected_time_to_monetisation`;
- `option_mfe_distribution` and `option_mae_distribution`;
- `model_uncertainty`;
- `applicability_state`.

Probability of monetisation is conditional on the underlying thesis and contract path. It is not the same as directional probability or present liquidity probability.

### 11.6 Model F — Contract-family ranker

The ranker combines model outputs through a versioned utility policy. Conceptually:

```text
utility = probability-weighted upside
        - probability-weighted downside
        - entry/exit friction
        - theta/timing burden
        - liquidity uncertainty
        - model/applicability uncertainty
```

No arbitrary weighted score may be labelled a probability. Until models are calibrated, the system will publish deterministic scenario measures and an explicitly named `ranking_score_uncalibrated`.

## 12. Dynamic re-evaluation

### 12.1 Evaluation points

- completed-session pipeline observation;
- Morning Gate observation;
- optional intraday observation when a material trigger occurs;
- manual operator refresh.

Morning Gate records whether the original thesis condition is confirmed, developed, breached, recovering or elapsed using the current underlying price and structure. It does not delete the opportunity. DOI then refreshes or reuses option evidence and re-ranks the contract family. Failure to obtain a new option quote, a gap beyond an entry level, or unfavourable timing does not remove the underlying opportunity.

### 12.2 Material triggers

Re-evaluation occurs when:

- spot moves materially towards/away from strike, target or invalidation;
- spread changes materially;
- volume or quote activity develops;
- IV changes materially;
- DTE crosses a governed boundary;
- a new strike/expiry becomes preferable;
- the thesis receives a governed new version.

### 12.3 Hysteresis

To avoid contract thrashing, the current preferred contract is retained unless an alternative:

- exceeds it by a versioned minimum utility margin;
- has adequate observation quality;
- remains preferable under stress;
- is consistent with the same thesis direction and horizon.

All economics are recomputed for the replacement contract. Premium, Greeks, payoff, IV and liquidity from the previous contract must never be carried forward.

## 13. Outcomes and learning labels

Every assessed contract—not only the selected or executed one—must receive subsequent labels where evidence permits:

- executable within 1/2/3 sessions;
- minimum spread and time to minimum spread;
- maximum volume and OI change;
- option MFE and MAE;
- return at target, invalidation and time stop;
- whether the underlying thesis succeeded;
- whether the contract monetised despite/without target completion;
- whether another family member would have been superior;
- supersession and replacement reason.

Labels must be generated point-in-time with no future evidence in features. Training, validation and test splits must be chronological and grouped to prevent the same ticker/thesis leaking across partitions.

Executed trades remain a separate realised-fill dataset. Unexecuted candidates may train market-path and hypothetical-contract outcomes only when labelled as such; they must not be presented as realised trading P&L.

## 14. Intelligence Lab contract

The Lab shall show separate panels/fields for:

**Thesis**

- thesis state, direction, target, invalidation, remaining horizon and Morning validation result.

**Preferred contract**

- OCC symbol, strike, expiry, DTE, bid/ask, IV and Greeks;
- observation time and freshness/quality;
- current contract-entry state;
- reason it is preferred;
- whether it replaced a prior contract.

**Probability and uncertainty**

- liquidity-maturation probability by horizon;
- probability of positive return and return hurdle;
- target-before-invalidation probability;
- expected time to monetisation;
- uncertainty/applicability state.

**Alternatives**

- at least two ranked alternatives where available;
- rank difference and trade-off explanation.

No EIL/DOI/Phantom, timing, entry, exit, Morning Gate or Execution Gate field may hide or delete an Intelligence Lab row. The Lab must display adverse states and warnings prominently while leaving the opportunity available for human judgement. Filters may organise views, but the unfiltered governed book must retain every row.

## 15. Failure behaviour

| Failure | Required behaviour |
|---|---|
| Phantom unavailable | Continue with current canonical evidence; mark historical features unavailable |
| Probability model unavailable | Use deterministic scenario engine; do not invent probabilities |
| Current option quote missing | Keep thesis; set contract data insufficient/monitor |
| One contract invalid | Exclude that observation and continue family evaluation |
| Whole chain unavailable | Keep thesis with contract repair/data-insufficient state |
| Entry level missed or price gapped | Show current distance and `ENTRY_CONDITION_MOVED`; retain opportunity |
| Invalidation level breached | Show `THESIS_CONDITION_BREACHED`; retain and monitor for recovery |
| Time horizon elapsed | Show `HORIZON_ELAPSED_REASSESS`; retain for human review |
| Exit condition detected | Show exit evidence and timestamp; do not automatically close or hide |
| Contract expired | Preserve history; never reuse it; generate a new family only if the ticker remains observed |
| Model out of distribution | Increase uncertainty; do not promote confidence |
| New preferred contract | Recompute full exact-contract economics and append supersession |
| DOI calculation exception | Preserve enrichment spine and ticker; publish NOT_EVALUATED diagnostics |

## 16. Regression invariants

1. Discovery/Vanguard direction, target and invalidation cannot be changed by DOI.
2. Macro cannot approve, block or reverse a thesis or contract.
3. EIL/DOI `BLOCKED` compatibility values cannot delete candidate rows.
4. Contract conditions cannot grant capital or discard an opportunity.
5. Morning Gate records confirmation, breach, recovery or elapsed state without requiring a new option quote and without deleting the row.
6. OI, volume, PCR, entry, exit and timing conditions are never row-deletion gates.
7. Missing data is never coerced to economic zero.
8. CALL and PUT paths have equivalent governance coverage and side-correct formulas.
9. Trading sessions are never treated as calendar days.
10. A contract switch forces exact-contract quote and economics refresh.
11. All computations bind to immutable dataset IDs and evidence cutoffs.
12. Restarts are idempotent and append-only histories are not overwritten.
13. A dormant/breached/elapsed ticker remains visible and triggers a new option call only after underlying-price reactivation or manual request.
14. Only long single-leg CALL/PUT structures enter the production contract family.
15. No automated exit condition closes or removes a human-held trade.

## 17. Testing strategy

### 17.1 Unit and property tests

- CALL/PUT payoff and Greek-sign symmetry;
- target-before-invalidation ordering;
- trading-session/calendar conversion;
- DTE/expiry boundary cases;
- null versus zero handling;
- quote validity and one-sided monitoring;
- PCR scope calculations;
- deterministic scenario arithmetic;
- contract supersession and hysteresis;
- no authority leakage.
- breach/recovery and elapsed/reactivation transitions without row loss;
- exit warnings never removing or closing a row.

### 17.2 Historical replay

Use frozen canonical/Phantom observations. At every replay timestamp, features may use only evidence available by that cutoff. Compare:

- current static selector;
- deterministic thesis-conditioned ranker;
- interpretable probability baselines;
- nonlinear candidate models.

Report selection coverage, liquidity-maturation calibration, option MFE/MAE, positive-return hit rate and ranking lift.

### 17.3 Statistical validation

Before a value is labelled a probability, report:

- Brier score and log loss;
- reliability/calibration plots and expected calibration error;
- sample size by CALL/PUT, DTE, delta, liquidity and regime bucket;
- temporal stability;
- out-of-distribution rate;
- confidence intervals;
- comparison against simple baselines.

Thresholds must be set from the measured baseline and release objective, not invented before measurement.

### 17.4 End-to-end tests

- completed-session run produces thesis-preserving contract families;
- Morning Gate records thesis-condition changes and re-ranks contracts independently without row deletion;
- a monitor contract can mature to acceptable;
- an acceptable contract can degrade;
- a better alternative can supersede the preferred contract;
- no EIL/DOI state reduces candidate population;
- no timing, entry, exit, breach or elapsed state reduces the governed opportunity population;
- Intelligence Lab values reconcile exactly to source dataset IDs;
- Pipeline Interpreter receives the same governed thesis and latest contract assessment;
- Decision and Outcome Ledger receives every candidate assessment.

## 18. Release and observability

The release must publish aggregate diagnostics:

- thesis count entering DOI;
- families generated;
- candidates evaluated per family;
- current entry-state distribution;
- contracts retained despite low OI/zero volume;
- data-insufficient reasons;
- family switches and hysteresis suppressions;
- probability model coverage and OOD count;
- canonical reuse versus provider-call count;
- reconciliation: input theses = assessed + explicitly failed;
- CALL/PUT distribution.

Production deployment is an advisory production release, not an invisible shadow system. During controlled comparison the new outputs are displayed and recorded, but they possess no authority to discard opportunities, invalidate them permanently, close positions or grant capital.

## 19. Build and implementation plan

### DOI-0 — Baseline and release controls

1. Freeze hashes of affected production modules, schemas and tests.
2. Capture current selector/EIL population and CALL/PUT metrics from a reproducible run.
3. Create the claim register, authority matrix and rollback manifest.
4. Confirm Phantom and canonical coverage by session and ticker.

**Exit:** reproducible baseline and no unexplained dirty-file ownership.

### DOI-1 — Remove EIL authority leakage

1. Remove direct candidate deletion based on `eil_v3_verdict`.
2. Remove EIL vetoes from Lab, Interpreter, handoff guard and sovereign-gate logic.
3. Remove indirect EIL influence from structural tiers, candidate caps, ranking and capital fields.
4. Preserve EIL calculations as compatibility telemetry.
5. Ensure the enrichment spine survives EIL failure.
6. Remove entry/exit/timing-based row suppression and automatic closure semantics.

**Exit:** governed opportunity population is invariant when EIL, entry, exit and timing values are permuted; only advisory states and ordering may change.

### DOI-2 — Domain contracts and persistence

1. Implement the new contract-entry vocabulary.
2. Define versioned `ContractFamily`, `ContractAssessment` and supersession contracts.
3. Extend the existing option-liquidity lifecycle append-only schema; do not create another raw-data database.
4. Add canonical dataset and thesis lineage.

**Exit:** immutable round-trip persistence and restart tests pass.

### DOI-3 — Governed observation bridge

1. Resolve canonical completed-session and morning option observations.
2. Bridge canonical observations into Phantom as lineage-bound projections.
3. Enforce reuse-first/fetch-missing-only behaviour.
4. Suppress repeated option acquisition for dormant/breached/elapsed opportunities until underlying-price reactivation or manual refresh, without removing them.
5. Implement scoped PCR and contract-activity feature extraction.

**Exit:** zero duplicate fetches for identical scope and no raw-authority divergence.

### DOI-4 — Thesis-conditioned contract-family generator

1. Replace single narrow preselection with a governed family generator.
2. Apply only structural hard exclusions.
3. Retain low-OI, zero-volume and one-sided observations as monitorable where structurally valid.
4. Persist the complete candidate taxonomy and bounded display set.

**Exit:** CALL/PUT fixtures prove broad family coverage without admitting invalid contracts.

### DOI-5 — Deterministic scenario and valuation engine

1. Implement exchange-calendar time conversion.
2. Build early/mid/late favourable and invalidation scenarios.
3. Add base/contracted/expanded IV stresses.
4. Add friction, dividend and model-applicability disclosure.
5. Rank with explicitly uncalibrated scenario utility.

**Exit:** independent arithmetic fixtures pass and no output is mislabelled as probability.

### DOI-6 — Dynamic lifecycle and re-ranking

1. Implement material-change triggers.
2. Implement state transitions and append-only observation history.
3. Implement hysteresis and contract supersession.
4. Force full recomputation after contract changes.
5. Integrate completed-session and Morning Gate evaluation points.
6. Implement breach-to-recovery and elapsed-to-reassessment transitions without deletion.

**Exit:** deterministic lifecycle simulations cover maturation, degradation and replacement.

### DOI-7 — Outcome-label capture

1. Capture future option and underlying paths for every assessed candidate.
2. Calculate liquidity maturation, MFE, MAE and horizon outcomes.
3. Separate hypothetical market outcomes from realised fills/P&L.
4. Add no-lookahead and chronological split tests.

**Exit:** labelled cohorts reconcile to original observations and cutoffs.

**Implementation acceptance (2026-09-10):** Delivered as a provider-free,
append-only outcome domain and application service in the existing option
lifecycle control plane. Every assessment/horizon is represented as completed,
option-path-partial, option-return-unavailable, deferred or data-exception.
Labels retain exact contract and dataset lineage; record two-sided/spread
liquidity maturation, option and underlying MFE/MAE, horizon return and
target/invalidation passage; and prohibit realised fills, thesis/capital
authority and automated closure. Chronological cohort construction excludes
labels whose future outcome window crosses a split boundary. Offline unit,
authority, persistence, restart and frozen-canonical-chain rehearsals passed.

### DOI-8 — Probability models

1. Train interpretable baselines first.
2. Train liquidity survival and nonlinear outcome candidates only where sample support is adequate.
3. Calibrate probabilities on later chronological data.
4. Publish uncertainty, applicability and OOD state.
5. Reject models that do not outperform simple baselines out of sample.

**Exit:** calibration and temporal-stability gates pass for each supported cohort.

**Implementation acceptance (2026-09-10):** Delivered as a governed,
append-only modelling domain and application service. The first candidate is
an interpretable logistic baseline with later-period Platt calibration. CALL
and PUT are independent cohorts; training, calibration and holdout splits are
chronological and purge outcome windows that cross split boundaries. Model
cards include Brier score, log loss, ECE, calibration-bin uncertainty,
temporal holdout windows, OOD rate, feature ranges, missingness and DTE/delta/
spread cohort diagnostics. A model is rejected unless it beats the constant-
prevalence baseline on both Brier and log loss, remains stable in each eligible
temporal holdout window and passes the calibration policy. Missing support,
cohort mismatch and OOD evidence publish no calibrated probability and leave
DOI-5 deterministic assessment in place. The live control plane currently has
zero persisted DOI-7 labels, so no real production model has been trained or
activated; frozen/synthetic test data is never promoted as production evidence.

### DOI-9 — Contract-family ranker

1. Combine calibrated outputs through a versioned utility policy.
2. Tune hysteresis from replay evidence.
3. Preserve deterministic fallback when probability coverage is insufficient.
4. Produce preferred and alternative contract explanations.

**Exit:** ranking lift is measured without reduced thesis coverage or authority leakage.

**Implementation acceptance (2026-09-10):** Delivered as a provider-free,
append-only ranking domain and application service. The full contract family is
always retained. An accepted policy may combine DOI-5 deterministic utility
with DOI-8 liquidity, positive-return and target-before-invalidation
probabilities only when every comparable candidate has an unambiguous,
applicable probability set. Otherwise the entire family uses DOI-5
deterministic ordering; incomplete candidates remain visible. Policy weights
and the contract-switch margin are learned on chronological replay and are
accepted only when later validation and holdout cohorts improve reward without
reducing coverage and every eligible holdout window is non-inferior. Ranking
identity, model lineage and persistence are append-only and independently
validated. CALL and PUT paths are symmetric. The live control plane contains
no real DOI assessments, outcome labels, accepted probability models or
accepted ranking policies, so calibrated ranking is correctly unavailable and
no synthetic policy has been promoted.

### DOI-10 — Intelligence Lab and Interpreter integration

1. Present thesis and contract states separately.
2. Display probabilities, uncertainty, evidence time and alternatives.
3. Remove legacy EIL wording that implies thesis/capital authority.
4. Supply the same latest assessment to Pipeline Interpreter.
5. Add exact source reconciliation tests.
6. Provide an unfiltered `ALL OPPORTUNITIES` view in which entry, exit, timing and evidence warnings never remove rows.

**Exit:** a trader can trace every displayed value to a thesis, contract observation and model version.

**Implementation acceptance (2026-09-10):** Delivered as an additive,
read-only projection over the existing final opportunity book and canonical DOI
records. The Lab now preserves the complete governed v2 opportunity population
and overlays accepted v3 actionable evidence only after run, ticker, thesis and
trade-idea identity reconciliation. The accepted Interpreter handoff remains
actionable-only. A separate advisory resolver exposes non-actionable rows only
for EOD review and trajectory use and explicitly rejects executable-session
requests. The UI defaults to `ALL OPPORTUNITIES`, separates the governed
contract from the DOI-preferred contract, displays alignment, probability
applicability, uncertainty, evidence cutoff, model identity and alternatives,
and relabels legacy EIL output as non-authoritative entry telemetry. Missing or
inactive DOI tables produce explicit `DATA_UNAVAILABLE`/`NOT_EVALUATED` states;
they never remove a row or create zero-valued evidence. DOI-10 changes no
direction, thesis, lifecycle, action, size or capital field. The 115-test DOI
regression pack passed. A read-only rehearsal against run `20260909_071646`
preserved all 235 opportunities while overlaying exactly four accepted
actionable rows; the canonical database hash remained unchanged.

### DOI-11 — Controlled production acceptance

1. Run the complete regression suite.
2. Execute a completed-session integration run.
3. Execute the next valid Morning Gate against that run.
4. Validate population reconciliation, dynamic transitions, CALL/PUT coverage and Lab projection.
5. Record release manifest, model cards and rollback point.
6. Promote accepted functionality as production advisory.

**Exit:** all functional invariants pass; statistical claims are limited to cohorts that meet calibration requirements.

**Implementation status (2026-09-10):** Production wiring and the acceptance
control are delivered and offline accepted. The evening orchestrator now runs
DOI after governed horizon propagation and before downstream overlays. It uses
only canonical completed-session MarketData chains, reuses the existing OLM
thesis lifecycle, persists append-only DOI families/assessments/rankings and
retains ticker-level data exceptions without stopping or reducing the pipeline
population. The complete structural family taxonomy remains stored; a
deterministic diversified set of at most 12 contracts per family is valued and
ranked in the live path to bound runtime. No DOI component may call a provider,
change direction, invalidate a thesis, grant capital or remove an opportunity.
The governed runtime configuration is active and the pre-DOI control-plane
database is retained as a rollback point.

The 120-test DOI regression pack passes. A production-data rehearsal on an
isolated database copy retained 20/20 tickers (balanced CALL/PUT), audited 6,740
structurally valid contracts, valued/ranked 240 bounded contracts, reused 20
canonical chains, made zero provider calls and raised zero exceptions. Formal
production acceptance remains pending one new evening artefact and the next
valid Morning Gate; the read-only assessor reports this honestly and cannot
promote an old pre-DOI run.

## 20. Recommended delivery organisation

Use no more than two concurrent implementation agents on the same phase:

- **Agent A — domain/data implementation:** contracts, canonical/Phantom bridge, persistence, lifecycle and production wiring.
- **Agent B — quantitative verification:** scenario maths, model evaluation, adversarial tests, lineage and authority regression.

They must not edit the same production file concurrently. Agent B independently verifies Agent A's claims before integration. The primary integrator owns phase review, final merge, full regression and release evidence.

## 21. Final acceptance statement

The solution is shippable when AVSHUNTER preserves every governed ticker opportunity, monitors a family of long CALL or PUT contracts, explains how probability, liquidity, entry, exit and timing states change, replaces a contract without carrying stale economics, and displays adverse evidence without allowing any automated layer to discard the row, close the position or grant capital.

The system must learn the difference between a bad thesis, a good thesis expressed through the wrong contract, a good contract selected too early and a developing contract that subsequently becomes monetisable. That distinction is the central purpose of Dynamic Options Intelligence.
