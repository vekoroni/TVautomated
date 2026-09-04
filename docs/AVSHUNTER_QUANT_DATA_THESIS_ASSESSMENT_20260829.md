# AVSHUNTER Quant Data Thesis Assessment

**Role:** Quantitative business analyst / solution architect  
**Assessment date:** 29 August 2026  
**Scope:** Review of the supplied GPT thesis against the implemented AVSHUNTER pipeline, its current process controls, databases, governed outputs and learning loop.  
**Change status:** Read-only assessment. No pipeline code, configuration, database or production output was changed.

## 1. Executive verdict

### Decision: agree with the central thesis, but qualify the current-state analysis

I agree with approximately **80% of the strategic thesis**:

> AVSHUNTER's highest-value next dataset is a point-in-time record of its own candidate decisions, state transitions, selected contracts, rejected candidates and subsequent outcomes—not another broad external indicator feed.

That conclusion is supported by the current system. AVSHUNTER has extensive pre-trade features and approximately 3.8 million actuarial observations, but its live trade journal contains only **14 closed trades**, of which only **9 are marked ML-eligible**. It does not store MFE or MAE, and many of the newer governance/contract/trigger fields are missing on the older journal rows. The present feedback API explicitly returns `average_mfe = None` and `average_mae = None`. This is not enough data to determine which gates or models add incremental economic value.

However, the supplied conversation is not an accurate current-state audit in several important respects:

- exact ticker-token matching, run IDs, invocation IDs and evidence hashes already exist in Pipeline Interpreter automation v2;
- malformed model responses are strictly parsed and fail to STOP, so the current problem is response fragility and availability—not uncontrolled silent contamination;
- the latest governed Lab output does not contain XGBoost or LSTM features, and no trained XGBoost/LSTM model artefacts were found;
- macro, EV and legacy R:R no longer have the sovereign authority described in the conversation;
- AVSHUNTER's active canonical options registry is MarketData-based, not Polygon-options-based;
- the outcome ledger is not wholly absent: a trade journal, outcome monitor, calibration reports and a Lab feedback endpoint exist. The problem is that they are narrow, sparsely populated and not an all-candidate learning system.

The corrected thesis is therefore:

> **Extend and govern the existing AVSHUNTER data controls into an append-only Decision and Outcome Ledger covering every candidate and every state transition. Do not start another independent database or buy more data until this ledger establishes the current performance baseline.**

## 2. Evidence-based current-state assessment

### 2.1 Pipeline functionality

| Capability | Implemented state | Assessment |
|---|---|---|
| Discovery and candidate generation | Broad universe scan with lifecycle/drop tracking | Strong breadth; requires outcome attribution by candidate and rejection reason |
| Canonical data reuse | CDS control plane and historical-price store | Materially implemented; not acknowledged in the supplied thesis |
| Options data | MarketData option-chain snapshots registered in CDS/Phantom | Useful snapshot base; not trade-level OPRA microstructure |
| Actuarial evidence | Millions of historical equity/state observations | Valuable for state priors; not a substitute for realised option-trade outcomes |
| Direction and contract governance | Governed direction, contract identity, quote/economics fields | Substantially implemented; identity should be persisted into the outcome ledger |
| Morning validation | Trigger/live-validation stage with macro advisory | Current authority differs from the thesis's older sovereign-gate description |
| Intelligence Lab | Governed final opportunity book with 297 columns and per-field stage provenance | Strong current-state read model; provenance identifies stages but lacks a normalized per-field event-time/source-hash contract |
| Pipeline Interpreter v2 | Run/ticker/invocation identity, evidence hashing, strict validation, shadow publication | Identity defect described in the thesis has already been addressed in v2; production integration is still incomplete |
| Trade journal | Open/closed trade SQLite tables, outcome capture and calibration reports | Exists but is too sparse and trade-only |
| Learning feedback | Lab API groups win rate/P&L by selected states | Functional reporting, not a production model-learning loop |
| XGBoost/LSTM | Standalone module with heuristic fallback and two tiny historical example files | Not evidenced as an active trained layer in the latest governed pipeline output |
| News Terminal | Confirmation/context route and Interpreter input | Not current signal authority; the thesis overstates its integration into core decisions |

### 2.2 Measured database evidence

#### Trade journal

The live `trade_journal.db` contained:

- 14 closed trades;
- 0 open trades;
- 10 calibration-report rows;
- 9 ML-eligible closed trades and 5 ineligible rows;
- entry dates from 6 March to 24 June 2026;
- exit dates from 27 April to 18 July 2026;
- 7 `TRUE_WINNER`, 5 `TRUE_LOSER` and 2 `OUTCOME_LOSS` labels.

Important completeness gaps among the 14 closed trades:

| Field | Missing rows |
|---|---:|
| `rr_predicted` | 6 |
| `rr_realised` | 10 |
| `source_payload_json` | 7 |
| `contract_snapshot_json` | 9 |
| `trade_idea_id` | 7 |
| `lab_verdict` | 7 |
| `trigger_primary` | 9 |
| `trigger_quality` | 10 |
| `wbs` / `wbs_grade` | 7 / 7 |
| MFE / MAE | not present in the schema |

The existing feedback endpoint can calculate small-sample win rates and average P&L, but it cannot yet evaluate path quality, timing, adverse excursion, missed opportunity or rejected-candidate performance.

#### Canonical control plane

The CDS control plane contained:

- 1,898 registered datasets;
- 5,047 API request-ledger rows;
- 25,433 stage-worklist rows;
- 67,982 ticker-lifecycle events;
- 9 run-registry rows.

The registry already stores `content_hash`, `observed_at`, `as_of`, `expires_at`, source run ID, provider, quality flags and parent dataset IDs. This means the thesis's proposed immutable EvidenceManifest should **extend and unify existing controls**, not recreate them.

All 1,898 registered option-chain datasets were recorded with provider `MARKETDATA`. The assertion that AVSHUNTER can simply extend its Polygon options relationship is not supported by the live registry or the known current entitlement. The 86 Polygon physical requests in the general request ledger do not establish access to Polygon options microstructure.

#### Latest governed Intelligence Lab book

The 29 August EOD final opportunity book contained:

- 817 candidates and 297 columns;
- one consistent `run_id` on all rows;
- per-field stage provenance on all rows;
- structured source payloads on all rows;
- bid/ask/mid/IV/OI/volume for 166 rows with selected contracts;
- no populated normalized `selected_quote_timestamp_utc` values;
- no top-level signed option flow, microprice, order-flow imbalance, NOII, borrow/utilisation, expectation surprise, MFE or MAE fields.

Some timestamps and quote-age information exist inside nested payloads—for example EV3 quote age—but they are not normalized into a single point-in-time evidence contract. Stage-name provenance is useful lineage, but it is not equivalent to `source + event_time + available_at + as_of + source_hash + model_version` for every material observation.

## 3. Thesis-by-thesis verdict

### Thesis 1 — “The most valuable new dataset is AVSHUNTER's own decisions and outcomes”

**Verdict: agree strongly.**

The journal's 14 closed trades cannot calibrate a multi-layer pipeline, identify regime-specific edge or support XGBoost/LSTM training. The pipeline generates hundreds to thousands of candidate decisions per run, but only manually entered trades currently mature into journal outcomes. This creates severe selection bias: the system learns only from trades a human chose to log, not from all candidates its own gates accepted or rejected.

The correct asset is broader than a trade ledger. It is an **all-candidate Decision and Outcome Ledger**.

### Thesis 2 — “Predict direction, timing, volatility and executability separately”

**Verdict: agree, with one amendment.**

For long calls and puts, being correct on the underlying direction does not guarantee a profitable option. Entry premium, path and timing, implied-volatility change, theta, spread and exit liquidity matter. Separate labels are necessary.

The proposal should use at least six labels:

1. underlying direction;
2. threshold/imminence within the governed horizon;
3. option monetisation after realistic entry/exit assumptions;
4. path—target, stop or time exit first;
5. execution feasibility and quote quality;
6. **decision value**—whether accepting/rejecting the candidate was better than the governed alternative.

The equation in the supplied conversation is conceptually useful, but it is not a complete pricing or P&L model. For governed exits, option P&L is path-dependent and requires an explicit entry/exit policy, not merely `price path + delta IV - theta - costs`.

### Thesis 3 — “Evidence can be mixed across runs/tickers”

**Verdict: historically true, but overstated as a current Pipeline Interpreter v2 defect.**

The repository contains explicit exact-token logic preventing `F` from matching `NFLX`, plus run-ID, invocation-ID, ticker and hash validation. The current automation v2 manifest fails on ticker or run mismatch.

Residual issues remain:

- some Lab/pipeline discovery still prefers newest files rather than an explicitly selected run;
- per-field event/availability timestamps are incomplete;
- production Interpreter integration has not yet fully replaced legacy paths.

Therefore, evidence identity remains a production-hardening priority, but the solution should promote and extend v2 rather than rebuild identity controls.

### Thesis 4 — “Semi-structured GPT prose can contaminate downstream artefacts”

**Verdict: partly discredited.**

The current Interpreter provider still emits tagged prose/CSV, which is fragile. However, automation v2 parses it through required schemas and converts any malformed response to a provider failure/STOP state. That substantially reduces silent contamination.

The valid improvement is to replace legacy tagged prose with native JSON Schema Structured Outputs. The present risk is failed or unavailable Interpreter output, not automatic trade promotion from malformed prose.

### Thesis 5 — “Upgrade from snapshots to options microstructure”

**Verdict: agree as a controlled P1 experiment, not an immediate blanket P0 purchase.**

The current chain data provides contract quotes, Greeks, IV, OI and volume snapshots. It does not provide the full trade/quote sequence needed to classify buyer/seller initiation, quote age/stability, executable depth or contract path.

Research supports the usefulness of buyer-initiated opening option volume, but that research used proprietary trade classification and does not prove that a retail feed's inferred flow will add out-of-sample value to AVSHUNTER. See Pan and Poteshman's [option-volume study](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID368980_code030114590.pdf?abstractid=368980&mirid=1&type=2).

Open interest must also be governed as delayed context: OCC states that its open-interest figures are derived from the previous day's settlement. Therefore OI-based GEX is an estimate, not a live dealer-position fact. [OCC Series Search](https://www.theocc.com/Market-Data/Market-Data-Reports/Series-and-Trading-Data/Series-Search?symbol=GME&symbolType=Underlying).

Recommended approach: first store timestamped MarketData/Phantom snapshots for shortlisted contracts and measure whether snapshot-path features improve outcomes. Buy or license full OPRA trades/quotes only if that experiment shows the missing granularity is likely to pay for itself.

### Thesis 6 — “Add opening auction and order-flow intelligence”

**Verdict: agree, subject to the actual trading window and entitlement cost.**

This is logically aligned with a morning entry process. Nasdaq states that NOII provides paired shares, imbalance, direction and likely opening-price information, disseminated before the cross by subscription. [Nasdaq Opening and Closing Crosses](https://classic.nasdaqtrader.com/Trader.aspx?id=OpenClose).

Research also supports order-flow imbalance as more robust than raw traded volume for short-horizon price changes. [Cont, Kukanov and Stoikov](https://arxiv.org/abs/1011.6402).

However, this data must belong to Morning Validation/entry timing. It should not change the EOD structural thesis or become an unconditional sovereign gate. Its economic value must be evaluated after spread, latency and data cost.

### Thesis 7 — “Replace sentiment with measurable catalyst surprise”

**Verdict: agree, but sequence after the decision ledger.**

The existing event/catalyst payload contains many descriptive fields, but latest-run catalyst dates were populated on only 4 of 817 rows, and the retired catalyst overlay is no longer a governed input. A separate News Terminal can add value as context, provided it emits structured, point-in-time evidence and never grants execution authority.

The essential design is not “GPT sentiment.” It is:

- confirmed fact;
- prior/consensus;
- surprise magnitude;
- first knowable timestamp;
- causal transmission;
- market reaction observations;
- later revisions kept separate from the original observation.

### Thesis 8 — “Add borrow and securities-lending data”

**Verdict: agree conditionally.**

The scanner contains placeholders for short interest and borrow rates, but its current function explicitly returns no MarketData borrow data. For small/mid-cap squeeze and fragility analysis, true borrow fee, availability and utilisation can be useful.

The warning about FINRA short-sale volume is correct. FINRA states that daily short-sale volume is transaction flow and is not equivalent to reported short-interest positions. [FINRA explanation](https://www.finra.org/sites/default/files/2019-07/information-notice-051019.pdf).

This should be P1/P2 and evaluated in the lanes where short positioning is economically relevant—not applied indiscriminately to every ticker.

### Thesis 9 — “Transform macro levels into vintage-safe surprises”

**Verdict: agree analytically, lower operational priority after macro separation.**

ALFRED preserves when values were originally released and later revised, which is appropriate for leakage-free historical testing. [ALFRED documentation](https://fred.stlouisfed.org/docs/api/fred/alfred.html).

AVSHUNTER now treats macro as advisory sector/direction context rather than trade permission. Therefore vintage macro surprise is valuable for research and sector-rotation attribution, but it should not precede the core decision/outcome ledger or contract-execution data.

### Thesis 10 — “XGBoost/LSTM, Truth Extractor and sovereign gates form a sound current architecture”

**Verdict: partly discredited as a description of the current production path.**

- No XGBoost/LSTM fields were found in the latest final opportunity book.
- The ML directory contains no trained model files; its code states that heuristic priors are used until real outcomes exist.
- Its outcome JSON contains one example, and its trade log contains one template trade.
- Macro is advisory, EV3 is advisory and legacy R:R no longer has capital authority.
- The governed final opportunity book and morning validation state are now the correct user-facing authority, not the older GO/ARMED/WAIT hierarchy described in the thesis.

The model families can remain challenger components, but they should not be represented as calibrated production models until there is sufficient point-in-time outcome data and out-of-sample validation.

### Thesis 11 — “Use PBO and Deflated Sharpe before promotion”

**Verdict: agree.**

Repeatedly testing indicators, thresholds, lanes and regimes can manufacture apparent edge. The proposed promotion discipline is sound. The [backtest-overfitting literature](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659) and [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) are appropriate controls, but they supplement rather than replace purged walk-forward testing, calibration analysis and economic-cost modelling.

## 4. Correct target data architecture

Do not create one unstructured “everything” table. Extend the canonical system with linked, append-only records.

### 4.1 Core entities

| Entity | Grain | Purpose |
|---|---|---|
| `decision_run` | one pipeline invocation | Run identity, mode, versions, health and source hashes |
| `candidate_decision` | one trade idea at one decision timestamp | Frozen features and governed state as known then |
| `state_transition` | one candidate state change | Discovery → EOD → morning → Lab → Interpreter history and reasons |
| `candidate_rejection` | one rejected stage decision | Exact gate, reason, version and counterfactual eligibility |
| `contract_candidate` | one eligible/rejected option contract | Quote, Greeks, liquidity and contract-selection rationale |
| `evidence_observation` | one source observation | Source, event time, available time, observed time, as-of, expiry, hash and quality |
| `market_path_observation` | one candidate/contract/horizon checkpoint | Underlying/option mark, IV, spread, MFE, MAE and barrier state |
| `execution_observation` | one paper/live order attempt | Price assumption, fill status, slippage, latency and executable size |
| `matured_label` | one candidate/contract/label horizon | Direction, imminence, optionality, path and execution outcomes with censoring state |
| `model_evaluation` | one model version/prediction | Forecast, calibration bucket, outcome and challenger comparison |

### 4.2 Required identity

Every record should carry, directly or by immutable key:

- `trade_idea_id`;
- `run_id` and `invocation_id`;
- ticker and stable instrument identifier;
- governed direction;
- OCC contract symbol where applicable;
- decision/event/available/observed/as-of timestamps;
- source dataset ID and content hash;
- feature, policy and model versions;
- label maturity/censoring status.

### 4.3 Counterfactual governance

“Would a rejected candidate have succeeded?” is valuable but easy to bias. AVSHUNTER must not select a winning option retrospectively.

For every rejected candidate, freeze either:

1. the contract that would have been selected by the production selector at decision time; or
2. a versioned standardized paper contract rule, such as target DTE and delta.

Then value that same frozen contract using point-in-time bid/ask assumptions. Otherwise the rejected-candidate study will contain hindsight contract-selection bias.

## 5. Revised delivery priority

### Phase QD-0 — Baseline and contract definition

- Freeze the current authority map and candidate state vocabulary.
- Define label horizons, maturity, censoring and realistic paper-fill rules.
- Map the existing trade journal, Lab book, CDS registry and Interpreter manifest into one identity model.
- Establish current candidate counts, pass rates, net expectancy proxies and missingness.

### Phase QD-1 — All-candidate Decision Ledger

- Write every candidate and every state transition, including dropped, WAIT, repair and blocked rows.
- Persist exact source hashes, model/policy versions and selected/rejected contract sets.
- Ensure dropped tickers cannot re-enter later data-fetch stages.
- Keep this append-only and idempotent by run/trade-idea/state/version.

### Phase QD-2 — Outcome and path capture

- Add underlying and selected-contract checkpoints.
- Calculate MFE/MAE, target/stop ordering, time-to-threshold and multiple horizons.
- Capture paper outcomes for rejected candidates under a frozen contract rule.
- Separate matured, censored, unavailable and data-defect labels.

### Phase QD-3 — Contract snapshot series before full OPRA

- Reuse MarketData/Phantom snapshots for only shortlisted contracts.
- Record quote age, spread evolution, IV/Greeks path and executable-price assumptions.
- Quantify the residual information gap.
- Approve full OPRA trades/quotes only if an economic business case remains.

### Phase QD-4 — Morning microstructure

- Trial NOII/auction and underlying order-flow features in shadow mode.
- Evaluate incremental calibration and net expectancy for morning entries.
- Keep EOD thesis and morning entry-timing authority separate.

### Phase QD-5 — Expectation and positioning features

- Structured catalyst surprise/reaction data;
- securities lending/borrow data for relevant lanes;
- analyst revision and dispersion history;
- vintage-safe macro surprise and sector transmission.

### Phase QD-6 — Champion/challenger modelling

- Start with calibrated logistic/baseline models before LSTM complexity.
- Use purged, embargoed, walk-forward testing by time and ticker.
- Compare incremental feature groups, not only full-model accuracy.
- Promote only on out-of-sample economic and calibration criteria.

## 6. Acceptance and monetisation criteria

The new data system is successful only if it can prove:

### Data quality

- at least 99.5% of surfaced candidates recorded;
- zero ticker/run/contract identity collisions;
- at least 99% completeness for required point-in-time timestamps and source hashes;
- explicit maturity/censoring state on 100% of labels;
- no use of revised data before its historical availability time;
- reconciliation from universe → each stage → final Lab book → outcome.

### Model quality

- calibration by lane and horizon using Brier score/log loss and reliability plots;
- stable rank ordering and information coefficient;
- incremental uplift versus simple baseline models;
- no promotion based only on in-sample accuracy or win rate;
- controlled PBO/Deflated Sharpe and repeated-test accounting.

### Economic quality

- positive net expectancy under conservative entry/exit prices;
- option P&L and drawdown distribution, not just underlying hit rate;
- stop-before-target and MFE/MAE distributions;
- capacity and spread sensitivity;
- performance across direction, regime, liquidity band and market-cap lane;
- explicit value added or destroyed by each gate.

## 7. Business recommendation

### Approve

Approve the central investment thesis and begin with the all-candidate Decision and Outcome Ledger.

### Do not approve yet

Do not yet approve:

- a new external data purchasing programme;
- full-market OPRA ingestion;
- claims that XGBoost/LSTM are calibrated production models;
- a second provenance/evidence database independent of CDS;
- autonomous threshold changes from 14 closed trades;
- use of GPT sentiment or GEX as sovereign trade authority.

### Investment sequence

1. **Extend CDS and the existing journal into the Decision/Outcome Ledger.**
2. **Capture all accepted and rejected candidates with frozen point-in-time contracts.**
3. **Measure the baseline and identify which missing data could change a decision.**
4. **Trial candidate-driven contract snapshot paths.**
5. **Add opening microstructure, catalyst surprise and borrow data only through controlled feature-group experiments.**
6. **Train calibrated champion/challenger models after adequate labels mature.**

## 8. Final conclusion

The supplied thesis is strategically right about the missing learning asset and the danger of adding more indicators before measuring outcomes. It is also right that direction, timing, option monetisation, path and execution must be evaluated separately.

It is not fully reliable as a current-state architecture report. It understates controls already built, overstates active ML capability, uses an obsolete authority model, assumes unavailable Polygon options access and treats a sparse trade journal as if no outcome capability exists.

The correct programme is not “build another dataset from scratch.” It is:

> **Turn AVSHUNTER's existing CDS, governed opportunity book, trade journal and evidence manifests into one append-only, point-in-time Decision and Outcome Ledger, then let measured incremental value determine which external datasets deserve investment.**

That programme is the highest-probability route to making AVSHUNTER more accurate, explainable and commercially defensible.

