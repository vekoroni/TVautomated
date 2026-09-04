# AVSHUNTER Market Structure and Interpreter Data Enhancement

**Document ID:** AVS-SD-MSI-001  
**Version:** 1.1  
**Date:** 2026-08-30  
**Status:** Approved implementation design — phased build, test and controlled production activation authorised  
**Scope:** Canonical data, Options Intelligence, Morning Gate, Intelligence Lab and Pipeline Interpreter

**Implementation owner:** Codex  
**Delivery model:** maximum two implementation agents working on non-overlapping files, with the primary agent owning integration, regression, production acceptance and rollback decisions.

## 1. Executive decision

The enhancement should be built in the pipeline data layer and exposed to both the Intelligence Lab and Pipeline Interpreter through governed data contracts.

The Pipeline Interpreter must not become an independent MarketData client. Its normal source is the latest compatible Intelligence Lab/Morning Gate evidence bundle. If that evidence is absent or stale, the Interpreter may request a refresh through the Canonical Data Service (CDS). CDS owns provider selection, worklist enforcement, caching, persistence, provenance and request accounting.

The target design therefore has one data path:

```text
Discovery
   |  authorised worklist / dropped-ticker state
   v
Canonical Data Service and registry <--- MarketData (options)
   ^                 ^              <--- underlying market-data provider
   |                 |
   |                 +--- Options Intelligence (completed-session chain)
   |                              |
   |                              v
   |                   governed EOD candidate/contract
   |                              |
   +-----------------------> Morning Gate
                                  |
                    exact quote + underlying + structure
                                  |
                                  v
                     Governed Lab signal book v3
                                  |
                       governed handoff manifest
                                  |
                                  v
                    Interpreter evidence resolver
                                  |
                  acceptable bundle or CDS narrow refresh
                                  |
                                  v
                  Interpreter assessment sidecar v1
                                  |
                                  v
                    Intelligence Lab explanation tab

Standalone macro pipeline --------------------+
                                              |
                          advisory context only v
                              Lab / Interpreter
```

This avoids three competing sources of truth. Fresh market observations belong to CDS; the Lab owns the trader-facing opportunity record; the Interpreter explains governed evidence but does not silently replace it.

Production scope for v1.1 is **single-leg long calls and long puts**. Data contracts remain leg-ready, but multi-leg selection, economics aggregation and execution policy are outside this implementation. No exotic or non-directional strategy is introduced by MSI.

## 2. Business objective

The enhancement must allow a trader to open the Intelligence Lab and see a complete, current and traceable view of:

- the governed ticker thesis and direction;
- the exact selected option contract and any morning replacement;
- current contract bid, ask, size, spread, volume, open interest and Greeks;
- the change in the selected contract's bid, ask, mid and spread since the Morning Gate observation;
- the underlying NBBO and current/session price state;
- deterministic market-structure evidence;
- wall, GEX, volatility, trigger and liquidity-lifecycle evidence;
- the age, source and quality of every time-sensitive observation;
- the Interpreter's plain-language explanation of that same evidence.

The enhancement is successful only if the Lab and Interpreter describe the same ticker, thesis, contract, quote snapshot, direction and lifecycle state.

## 3. Current-state findings

### 3.1 Mislabelled underlying quote fields

`l2_bid_size` and `l2_ask_size` are populated from the MarketData stock quote endpoint. They represent the current underlying NBBO sizes, not a full Level-2 order book.

Required correction:

- introduce canonical names `underlying_nbbo_bid_size` and `underlying_nbbo_ask_size`;
- retain the existing `l2_*` names temporarily as deprecated aliases;
- publish `underlying_nbbo_bid`, `underlying_nbbo_ask`, timestamp, source and freshness together;
- never describe these values as full depth or order flow.

### 3.2 MarketData option sizes are discarded

The MarketData option-chain and exact-option quote responses provide `bidSize` and `askSize`. Current chain parsing retains bid and ask prices but does not retain the sizes. Morning exact-contract hydration does the same.

Required correction:

- parse option `bidSize` and `askSize` from both chain and exact-contract endpoints;
- preserve them in the canonical chain payload;
- propagate them through contract selection, alternatives, morning repair and selected-contract economics;
- persist them in exact-contract observations;
- display them in the Lab as contract quote sizes, separately from the underlying NBBO sizes.

### 3.3 A quote snapshot is not an order-flow history

The current canonical option store preserves one completed-session chain observation per ticker/session/scope. Morning validation preserves an exact-contract observation at a particular timestamp. These are valid snapshots but do not reconstruct:

- changes in bid/ask size;
- trades through the bid or ask;
- order additions, cancellations or queue movement;
- full book depth;
- intraday volume-at-price chronology.

The system must not infer footprint/order-flow conclusions from a single NBBO or option quote.

### 3.4 Interpreter source selection is only partly governed

The Interpreter already prefers the Lab triage view, followed by morning-validated and other pipeline files. However, older command paths can still choose different prompts or evidence depending on screenshot availability. The Interpreter also retains legacy live-reader commands.

Required correction:

- use one evidence resolver for every Interpreter command;
- use the same prompt and structured evidence contract with or without supplemental screenshots;
- remove screenshot presence as a branch that changes the governed numerical calculation;
- disable direct provider access from production Interpreter commands;
- retain a controlled screenshot lane for true Level-2, broker order-book, NOII and broker-only tape evidence until a licensed structured feed is available.

### 3.5 The Lab is the trader interface but not yet the complete evidence API

The Lab materializer correctly prioritises morning-validated data and already synchronises a compact view to the Interpreter. The enhancement must extend that contract so the Interpreter does not reconstruct the trade from loosely joined CSV files.

## 4. Design principles

1. **One observation, one owner.** CDS owns market observations and provenance.
2. **Use before fetch.** Resolve an acceptable canonical observation before making a provider request.
3. **No calls for dropped tickers.** Every request is checked against the active CDS worklist or an explicitly authorised research request.
4. **Exact-contract continuity.** Economics, lifecycle and quote fields must refer to the same OCC contract.
5. **Append observations; do not overwrite history.** Morning and intraday refreshes create new timestamped observations.
6. **Idempotent registration.** Re-registering identical content returns the existing canonical record rather than failing.
7. **Data quality is explicit.** Missing or estimated data is labelled, never silently fabricated.
8. **Calculation before narration.** Deterministic code calculates market structure; AI explains the result.
9. **No new capital authority.** Structure and Interpreter assessments are evidence. Existing governed direction, lifecycle and execution controls retain their roles.
10. **Macro remains separate and advisory.** Macro context may explain sector rotation but cannot grant or deny a trade.

## 5. Target components

### 5.1 Canonical Market Observation Service

A CDS service responsible for:

- completed-session option-chain resolution;
- exact selected-contract quote resolution;
- underlying NBBO resolution;
- one-minute underlying bar resolution;
- optional trade/quote-event resolution when the licensed source exists;
- freshness evaluation;
- provider calls only for missing or expired data;
- immutable persistence and lineage;
- request-ledger and cache-hit reporting.

The service exposes requests by data requirement, not by provider URL. Provider credentials and endpoints remain outside Interpreter and UI code.

### 5.2 Market Structure Evidence Service

A deterministic pipeline service that consumes canonical data and emits a versioned structure record. It calculates:

- session TPO/time-at-price profile;
- estimated or confirmed volume-at-price profile;
- high- and low-volume nodes;
- developing and final point of control;
- first and second distribution boundaries;
- separation-zone width and repair percentage;
- formation order and directional structure;
- acceptance minutes and closes;
- VWAP hold and retest state;
- point-of-control/value migration;
- structure lifecycle: `MS_DEVELOPING`, `MS_ACCEPTED`, `MS_CONTINUING`, `MS_REPAIRING`, `MS_FAILED`;
- relationship to governed direction: `ALIGNED`, `CONFLICTING`, `NEUTRAL`, `INSUFFICIENT_DATA`.

It must not emit GO/NO-GO or capital permission.

### 5.3 Governed Lab Evidence Materializer

Extends the existing final opportunity book with a coherent evidence object. It resolves fields by authority and records field-level provenance.

The Lab remains the user-facing source for signal review. It displays current data and Interpreter explanation but does not allow narrative fields to overwrite governed market fields.

### 5.4 Interpreter Evidence Resolver

Every Interpreter entry point calls the same resolver. The resolver:

1. identifies the active run, ticker, thesis and selected contract;
2. loads the latest Lab evidence bundle;
3. confirms Morning Gate status and quote identity;
4. evaluates freshness for the current session state;
5. returns the bundle if acceptable;
6. otherwise submits a narrowly scoped refresh request to CDS;
7. recomputes dependent market-structure fields when inputs change;
8. emits a new evidence-bundle ID;
9. fails closed if required evidence remains unavailable.

The Interpreter then produces explanation, reconciliation and questions for human review.

### 5.5 Controlled Microstructure Screenshot Adapter

AVSHUNTER does not currently receive true Level-2 depth, order-book events or NOII through a governed structured feed. For this evidence only, screenshots remain the temporary acquisition mechanism.

The adapter must:

- accept only declared screen types: `LEVEL2_BOOK`, `ORDER_BOOK_IMBALANCE`, `NOII`, `TAPE` and any specifically approved broker-only view;
- bind each image to ticker, venue/platform, capture timestamp, market session, run ID and operator/invocation ID;
- hash and preserve the original image;
- reject images with an unverified ticker or capture time;
- extract observations into a separate `SCREEN_DERIVED` evidence namespace;
- preserve extraction confidence and the source-image hash;
- require human confirmation before screen-derived evidence is treated as observed fact;
- never allow OCR or AI interpretation to overwrite governed numerical fields.

Ordinary price charts, option chains, quotes, Greeks, GEX and walls should not require screenshots when their structured data is already available.

## 6. Source-of-truth hierarchy

| Data domain | Primary source used by consumers | Refresh owner | Interpreter behaviour |
|---|---|---|---|
| Direction/thesis | Governed Lab/Morning record | Pipeline direction governance | Read only |
| Capital permission | Morning Gate and execution controls | Morning Gate | Read only |
| Selected contract | Morning-selected exact contract, otherwise governed EOD contract | Morning Gate | Cannot substitute silently |
| Exact option quote | Latest acceptable CDS exact-contract observation | Morning Gate/CDS | Request CDS refresh if stale |
| Contract monetisability | Morning Gate calculation for the selected exact contract | Morning Gate | Read only; an intraday refresh may publish an advisory recalculation but cannot change `final_action` |
| Completed option chain | CDS completed-session MarketData chain | Options Intelligence/CDS | Reuse; do not refetch |
| Underlying NBBO | Latest acceptable CDS underlying quote | Morning Gate/CDS | Request CDS refresh if stale |
| Intraday bars | CDS one-minute bar partition | Pipeline/CDS | Reuse or request missing interval |
| Structure evidence | Market Structure Evidence Service | Pipeline service | Read and explain |
| Lab verdict/rank | Governed Lab materializer | Lab control | Read only |
| Interpreter narrative | Interpreter sidecar | Interpreter | May be displayed, never authoritative |
| Macro | Standalone macro packet | Macro pipeline | Advisory context only |

R:R and EV are not capital authorities and are not reintroduced by this design. Trader-facing monetisability is the selected long call/put's governed target-payoff classification. If the Interpreter obtains a newer quote, it may display `intraday_monetisability_advisory`, but the Morning Gate `final_action` remains unchanged until Morning Gate is rerun.

## 7. Session-aware freshness policy

Freshness must be evaluated against market state, not a universal clock.

### 7.1 Market closed/evening

- The latest completed regular-session chain and bars are current for EOD analysis.
- Do not call a live provider merely because the wall-clock date advanced overnight.
- An observation is stale only when it does not cover the latest completed market session required by the run.

### 7.2 Premarket before Morning Gate

- The EOD thesis is valid as preparation evidence.
- Capital permission remains pending.
- Premarket underlying evidence may be refreshed through CDS if required.
- Options quotes must not be represented as executable until a valid quote is available for the trading session.

### 7.3 Morning Gate completed

- The Morning Gate bundle is the Interpreter's primary source.
- The bundle must identify its exact selected contract and quote snapshot.
- The Interpreter reuses it while its configurable TTL remains valid.

### 7.4 Market open after the Morning bundle expires

- The Interpreter may request a CDS refresh for the underlying and exact selected contract.
- It must not fetch the full chain unless the selected contract is missing, invalid or an authorised repair is required.
- A contract change requires fresh data for every leg and complete dependent recomputation before display.

Proposed initial configurable policies, to be reconciled against provider behaviour and accepted in MSI-0:

- underlying NBBO: 60 seconds during market hours;
- exact option quote: 60 seconds during market hours;
- one-minute bars: complete through the last closed minute, with a 120-second ingestion tolerance;
- completed-session chain: valid for that session and EOD purpose;
- structure record: stale whenever its input dataset IDs no longer match the resolved evidence bundle.

These are calibration/UAT seeds rather than validated production constants. Approved values must be configuration, not embedded separately in the Lab and Interpreter.

## 8. Data contracts

### 8.1 `option_chain_v2`

Additive fields per contract:

- `bid_size`;
- `ask_size`;
- `last`;
- `first_traded_utc` when supplied;
- `quote_timestamp_utc`;
- `quote_source`;
- `quote_freshness`;
- existing bid, ask, mid, Greeks, IV, OI, volume, underlying price and multiplier.

Validation:

- parallel MarketData arrays must have compatible lengths;
- negative sizes are invalid;
- bid must not exceed ask unless explicitly flagged as crossed/bad data;
- timestamp coverage must meet the completed-session contract;
- contract identity is normalised OCC identity.

### 8.2 `exact_option_quote_v2`

Fields:

- run ID, thesis ID and trade-idea ID;
- ticker and normalised OCC contract symbol;
- selected-structure ID and leg identity;
- bid, ask, mid, bid size and ask size;
- spread value and percentage;
- volume, OI, IV and Greeks;
- underlying price and contract multiplier;
- provider-updated timestamp and observed timestamp;
- provider, source dataset ID and parent chain dataset ID;
- freshness state and quality flags.

V1.1 writes exactly one leg for a single long call or long put. The schema retains `leg_identity` for forward compatibility, but multi-leg aggregation is not implemented in MSI.

Quote arithmetic is owned by one shared helper:

- `mid = (bid + ask) / 2` when both sides are positive;
- when `bid == 0` and `ask > 0`, `mid = ask / 2`, `quote_quality = ONE_SIDED`, and the quote is not executable;
- `spread_value = ask - bid`;
- `spread_pct = spread_value / mid` when `mid > 0`, otherwise `null`;
- an absent/null size is `MISSING`; a numeric zero is `OBSERVED_ZERO`; a negative size is `INVALID_SIZE` and rejects the observation;
- persisted prices use four decimal places, sizes are integers, ratios are decimals from 0 to 1, and timestamps are ISO-8601 UTC to the second.

### 8.3 `underlying_nbbo_quote_v1`

Fields:

- ticker;
- bid, ask, mid;
- bid size and ask size;
- provider-updated timestamp;
- source and freshness;
- explicit `depth_level = NBBO_ONLY`.

### 8.4 `underlying_intraday_bar_v1`

Partition key: ticker + session date + interval.  
Minimum fields: timestamp, open, high, low, close, volume, VWAP where available, trade count where available, session segment and adjustment convention.

The canonical session VWAP is computed by CDS from regular-session bars as cumulative `sum(((high + low + close) / 3) * volume) / sum(volume)`, reset at the regular-session open. A provider-supplied VWAP is stored separately as `vwap_provider` and never silently replaces `vwap_canonical`. Bars are stored `UNADJUSTED` for the session structure calculation. A detected same-session corporate action sets `corporate_action_on_session = true` and reduces structure quality to `COARSE_DATA_LOW_CONFIDENCE` pending review.

### 8.5 Optional future event contracts

- `underlying_trade_event_v1` for individual trades;
- `underlying_quote_event_v1` for quote changes;
- `order_book_snapshot_v1` only if a licensed depth source exists.

These must not be inferred from one-minute bars or NBBO snapshots.

### 8.6 `market_structure_evidence_v1`

Required identity and lineage:

- evidence ID, algorithm version and parameter-set version;
- ticker, session, run ID and calculation timestamp;
- input dataset IDs and hashes;
- session boundaries, tick/bin size and adjustment convention;
- data-quality class;
- distribution, acceptance, VWAP, migration, repair and `ms_lifecycle` fields;
- `ms_direction_relationship` to governed direction;
- plain-language reason code generated deterministically.

Data-quality classes:

- `TRADE_LEVEL_CONFIRMED`;
- `ONE_MINUTE_ESTIMATED`;
- `COARSE_DATA_LOW_CONFIDENCE`;
- `INSUFFICIENT_DATA`.

All Market Structure fields use the `ms_` prefix. No unqualified `lifecycle_state`, `quality`, `direction` or `status` field may be introduced.

### 8.7 `interpreter_evidence_bundle_v1`

The bundle is the only normal production input to ticker interpretation. It contains:

- run, thesis and trade-idea identity;
- Lab row and Lab manifest status;
- Morning Gate record;
- exact selected contract and quote dataset IDs;
- underlying quote and intraday dataset IDs;
- market-structure evidence;
- trigger, WBS, GEX, volatility, lifecycle and options evidence;
- freshness map for every time-sensitive domain;
- field-provenance map;
- authority map;
- quality and missing-data flags.

Required handoff identity fields are `run_id`, `pipeline_mode`, `ticker`, `thesis_id`, `trade_idea_id`, `selected_structure_id`, `selected_contract_symbol`, `selected_quote_snapshot_id`, `bundle_id`, `bundle_created_utc`, `bundle_schema_version` and `authority_map_version`. Production publication fails if any required identity is absent or inconsistent with the Morning/Lab record.

`bundle_id` is a UUID minted for each materialisation. All remaining IDs are reused from their authoritative upstream owner; the resolver must not create replacement thesis, trade-idea, structure, quote or dataset identities.

### 8.8 `quote_change_evidence_v1`

The Interpreter bundle must include an explicit comparison between the Morning Gate quote and the latest acceptable quote for the same exact contract.

Identity fields:

- ticker, thesis ID and trade-idea ID;
- normalised OCC contract symbol and selected-structure ID;
- Morning Gate quote dataset ID and timestamp;
- current quote dataset ID and timestamp;
- comparison status: `SAME_CONTRACT`, `CONTRACT_CHANGED`, `BASELINE_MISSING`, `CURRENT_MISSING` or `STALE`.

Price fields:

- `morning_bid`, `morning_ask`, `morning_mid` and `morning_spread_pct`;
- `current_bid`, `current_ask`, `current_mid` and `current_spread_pct`;
- absolute and percentage changes for bid, ask and mid;
- spread change in percentage points;
- current bid size and ask size, plus size changes when both snapshots contain sizes;
- quote age and freshness.

The comparison is valid only when the exact OCC contract is unchanged. If the Morning Gate selected a replacement contract, the new contract becomes a new baseline and the system must not describe the difference between two different contracts as a price change.

When a baseline numeric value is zero, percentage change is `null` and `change_status = BASELINE_ZERO`. When the contract differs, every change field is `null` and `comparison_status = CONTRACT_CHANGED`.

## 9. Detailed data flow

### 9.1 Evening pipeline

1. Discovery creates the authorised worklist.
2. CDS rejects requests for tickers removed from the worklist.
3. Underlying completed-session bars are resolved from cache or fetched once.
4. Options Intelligence resolves the completed-session MarketData chain.
5. Chain parser retains option prices, sizes, volume, OI, IV and Greeks.
6. Contract selection and lifecycle processing use the same canonical frame.
7. Exact selected-contract observation is persisted with quote sizes.
8. One-minute bars are resolved for surviving candidates only.
9. Market Structure Evidence Service emits preliminary/EOD structure evidence.
10. Lab materializer builds an EOD book labelled `MORNING_VALIDATION_REQUIRED` where applicable.

### 9.2 Morning Gate

1. Load the governed EOD candidate and exact EOD contract identity.
2. Resolve current underlying evidence through CDS.
3. Resolve current exact-contract quote through CDS; fetch only when the cache decision requires it.
4. If the contract is repaired or replaced, fetch every new leg and recompute all contract-dependent fields.
5. Persist option bid/ask sizes and the complete quote lineage.
6. Refresh missing one-minute/premarket intervals when the structure calculation requires them.
7. Recalculate market structure and its relation to the governed thesis.
8. Evaluate lifecycle and existing Morning controls.
9. Write the morning-validated record and summary.
10. Rematerialize the Lab book from the morning record.
11. Publish the Interpreter evidence bundle.

### 9.3 Pipeline Interpreter

1. User selects a ticker from the Lab.
2. Interpreter resolver loads the matching evidence bundle.
3. It verifies run, thesis, selected contract and quote identity.
4. If fresh, no API request is made.
5. If stale during market hours, it requests a narrow CDS refresh.
6. CDS records the new observation and dependent structure evidence is recomputed.
7. The quote-change service compares the refreshed exact-contract quote with the Morning Gate baseline.
8. A refreshed Lab evidence overlay and new Interpreter bundle are published.
9. Interpreter displays the Morning and current bid/ask, their changes, spread change, freshness and contract identity.
10. Interpreter generates a structured assessment and plain-language explanation.
11. The assessment is written as an append-only sidecar and displayed in the Lab.

There must be no circular overwrite. Interpreter narrative may enrich the Lab display, but it cannot change direction, contract identity, lifecycle state or capital permission.

### 9.4 Governed pipeline-to-Interpreter handoff

The handoff is an atomic publication, not a folder scan. Morning Gate and Lab materialisation produce:

1. `lab_signal_book_v3.csv` — the immutable governed row set for the run;
2. `lab_signal_book_v3.manifest.json` — schema, row count, content hash and authority status;
3. `interpreter_evidence_bundle_v1.jsonl` — one bundle per ticker;
4. `interpreter_handoff_manifest_v1.json` — the only production entry point accepted by the Interpreter.

The handoff manifest contains:

- run ID, pipeline mode, session date and run acceptance state;
- absolute/relative artefact paths, SHA-256 hashes and schema versions;
- row and ticker counts;
- required-stage completion states;
- Morning Gate completion timestamp;
- bundle count and missing-bundle count;
- reconciliation status and reconciliation-report path;
- publication timestamp and producer version.

Publication order is book -> bundle -> reconciliation report -> manifest. The manifest is written to a temporary sibling and atomically renamed only after every validation passes. The Interpreter never selects a CSV by filename recency and never consumes an incomplete run directory.

`resolve_interpreter_evidence(run_id, ticker, intended_use)` must:

1. load the explicitly selected or latest accepted handoff manifest;
2. verify manifest and artefact hashes;
3. require `run_status = ACCEPTED` for production trajectory analysis and require `COMPLETED` Morning Gate for executable-session interpretation;
4. exact-match ticker, thesis, trade idea, selected structure, contract and quote snapshot across the book and bundle;
5. apply the shared session-aware freshness service;
6. reuse acceptable CDS observations before requesting data;
7. submit a narrow CDS request only for the active, non-dropped ticker;
8. create a new overlay and bundle when refreshed data changes;
9. leave the immutable Morning/Lab book unchanged;
10. fail closed with a canonical reason code when any invariant fails.

The refreshed overlay may replace only current quote, quote-change, freshness and newly calculated structure fields in the UI. It cannot replace governed direction, thesis, selected contract, OLM lifecycle, Morning decision, `final_action`, capital permission or accepted-run identity.

The handoff finalizer invokes `tools/msi_reconcile.py`. Any mismatch returns non-zero and prevents manifest publication. This extends the existing handoff guard; it does not create a second permission engine.

During a two-cycle compatibility window, the existing four verified CSV copies and `morning_handoff_summary_{run_id}.json` may still be written. They are compatibility outputs only. The active `MA_Inputs` filename/mtime scanner, broad `ma_inputs_sync` publication and `prepare_interpreter_session` recency selection cannot act as production source authority. Missing required handoff files must return a non-zero exit; the removed catalyst overlay is not a required input.

The resolver assigns `SESSION.run_id` from the manifest. Interpreter timestamps may identify an assessment invocation but may never substitute for the pipeline run ID. Lab reconciliation must compare independent governed artefacts; comparing `lab_triage_view` to itself is invalid and cannot produce `CONFIRMED`.

## 10. Market-structure calculation requirements

### 10.1 Profile construction

- use exchange tick size and `ATR(14)` from completed daily sessions;
- set regular-session bin width to `round_to_tick(max(exchange_tick, ATR14 / 40))`;
- use 30-minute TPO periods and one-minute bars for volume estimation and acceptance timing;
- set value area to 70% of regular-session TPO count, expanding from POC toward the next higher adjacent count;
- separate premarket, regular session and after-hours; publish the regular-session profile as primary and premarket as `ms_premarket_context`;
- calculate TPO from bar-range participation;
- allocate each one-minute bar's volume uniformly across every intersected price bin and label it `ONE_MINUTE_ESTIMATED`;
- calculate exact VAP only when trade-level records exist;
- preserve developing POC and profile state through time.

### 10.2 Double-distribution detection

A valid structure requires:

- two contiguous concentration regions, each containing at least 20% of regular-session TPO count and containing a local peak at or above the 60th percentile of non-zero bin counts;
- an intervening low-participation zone of at least two bins whose maximum count is no more than 50% of the weaker regional peak;
- regional peak separation of at least `max(3 * bin_width, 0.30 * ATR14)`;
- chronological proof of which region formed first;
- the first region must reach 40% of its final-session TPO count at least one 30-minute TPO period before the second region reaches that threshold;
- minimum persistence/acceptance evidence defined in §10.3;
- deterministic rejection of isolated random peaks.

These values form the **proposed calibration seed** for parameter set `ms_params_v1`; they are not claimed as empirically validated production thresholds. Permitted calibration ranges are: bin divisor 25–60; region share 15–30%; peak percentile 55–75%; valley ratio 35–65%; separation 0.20–0.50 ATR; acceptance 20–60 minutes. MSI-4 calibration/UAT either accepts the seed or records a signed versioned replacement before activation. Any later change creates a new parameter-set version and requires replay, labelled-session comparison and production acceptance. Parameters must not be tuned independently for individual tickers during production inference.

### 10.3 Acceptance and failure

Calculate:

- minutes and closes in the second distribution;
- volume share accumulated in the second distribution;
- VWAP hold duration;
- retest count and result;
- POC/value migration;
- separation-zone repair percentage;
- invalidation/failure condition.

Acceptance requires all of:

- at least 30 elapsed regular-session minutes after first entry into the second distribution;
- at least three non-overlapping five-minute closes beyond the separation boundary;
- at least 10% of regular-session volume accumulated in the second distribution;
- no more than 20% separation-zone repair.

`ms_repair_pct` is the width-weighted fraction of separation-zone bins whose TPO count has recovered to at least 50% of the weaker regional peak. It is therefore a decimal from 0 to 1. A value below 0.20 is intact, 0.20–0.60 is repairing, and above 0.60 is failed.

Structure lifecycle transitions are evaluated after every completed five-minute interval:

| From | Condition | To |
|---|---|---|
| none/single distribution | second qualifying region detected | `MS_DEVELOPING` |
| `MS_DEVELOPING` | all acceptance rules pass | `MS_ACCEPTED` |
| `MS_ACCEPTED` | next evaluation remains accepted and repair < 0.20 | `MS_CONTINUING` |
| `MS_ACCEPTED` or `MS_CONTINUING` | repair is 0.20–0.60 or acceptance is temporarily lost | `MS_REPAIRING` |
| `MS_REPAIRING` | acceptance restored and repair < 0.20 | `MS_CONTINUING` |
| any detected double distribution | repair > 0.60, invalidation close, or regions cease to qualify | `MS_FAILED` |

`MS_FAILED` is terminal for that session. A new market session creates a new evidence record rather than reopening the failed state.

### 10.4 Authority behaviour

- `ALIGNED` supports the governed thesis.
- `CONFLICTING` creates a visible review/timing warning.
- `NEUTRAL` contributes no directional evidence.
- `INSUFFICIENT_DATA` contributes no uplift.
- no structure state independently grants capital or reverses direction.

The deterministic relationship mapping is:

| Governed direction | Conclusive structure | Lifecycle | Relationship |
|---|---|---|---|
| `CALL` | second distribution above first | `MS_ACCEPTED` or `MS_CONTINUING` | `ALIGNED` |
| `CALL` | second distribution below first | `MS_ACCEPTED` or `MS_CONTINUING` | `CONFLICTING` |
| `PUT` | second distribution below first | `MS_ACCEPTED` or `MS_CONTINUING` | `ALIGNED` |
| `PUT` | second distribution above first | `MS_ACCEPTED` or `MS_CONTINUING` | `CONFLICTING` |
| `CALL` or `PUT` | any direction | `MS_DEVELOPING`, `MS_REPAIRING` or `MS_FAILED` | `NEUTRAL` |
| `UNRESOLVED` | any | any | `NEUTRAL` |
| any | absent/insufficient quality | any | `INSUFFICIENT_DATA` |

For every relationship value, a contract regression must prove that Morning Gate checks and `final_action` are byte-equivalent before and after the structure field is attached.

## 11. Intelligence Lab integration

The governed book becomes `lab_signal_book_v3`. New Morning/EOD fields are written in-row. Intraday refreshes are written to `lab_evidence_overlay_v1.jsonl`, keyed by `run_id + ticker + bundle_id`; they never mutate the accepted book. The Lab applies the latest compatible overlay only to the allow-listed current-observation fields below. Book values win for every authority field.

The Lab displays the enhancement in four groups. Every empty value renders its canonical state (`MISSING`, `STALE`, `NOT_APPLICABLE` or `INSUFFICIENT_DATA`), never a blank or fabricated zero.

### Quote identity and freshness

- selected contract/legs;
- Morning Gate bid/ask/mid and current bid/ask/mid;
- bid, ask and mid price changes for the same exact contract;
- Morning and current spread, plus spread change;
- current bid/ask size and size changes when comparable;
- quote timestamp and age;
- source and snapshot ID;
- `FRESH`, `EOD_CURRENT`, `STALE`, `MISSING` or `INVALID`.

Exact fields: `selected_contract_symbol`, `selected_quote_snapshot_id`, `morning_contract_bid`, `morning_contract_ask`, `morning_contract_mid`, `morning_contract_spread_pct`, `current_contract_bid`, `current_contract_ask`, `current_contract_mid`, `current_contract_spread_pct`, `contract_bid_change`, `contract_ask_change`, `contract_mid_change`, `contract_spread_change_pp`, `contract_bid_size`, `contract_ask_size`, `contract_size_quality`, `quote_timestamp_utc`, `quote_age_seconds`, `quote_freshness`, `quote_source`, `comparison_status`.

### Underlying market state

- underlying price and NBBO;
- current VWAP relationship;
- overnight gap and remaining runway;
- session and last completed bar.

Exact fields: `underlying_last`, `underlying_nbbo_bid`, `underlying_nbbo_ask`, `underlying_nbbo_mid`, `underlying_nbbo_bid_size`, `underlying_nbbo_ask_size`, `underlying_nbbo_timestamp_utc`, `underlying_vwap_canonical`, `underlying_vwap_relationship`, `overnight_gap_pct`, `remaining_runway_pct`, `session_state`, `last_completed_bar_utc`.

### Structure evidence

- profile type and lifecycle;
- direction relationship;
- distribution boundaries and POCs;
- separation repair, acceptance and VWAP hold;
- data-quality label;
- deterministic reason.

Exact fields: `ms_profile_type`, `ms_lifecycle`, `ms_direction_relationship`, `ms_first_distribution_low`, `ms_first_distribution_high`, `ms_second_distribution_low`, `ms_second_distribution_high`, `ms_developing_poc`, `ms_final_poc`, `ms_separation_low`, `ms_separation_high`, `ms_repair_pct`, `ms_acceptance_minutes`, `ms_acceptance_closes`, `ms_vwap_hold_minutes`, `ms_quality_class`, `ms_reason_code`, `ms_evidence_id`, `ms_parameter_set_version`.

### Interpreter assessment

- strengthening/weakening summary;
- agreement/conflict across governed evidence;
- what the junior trader must verify manually;
- data gaps;
- explicit statement that interpretation does not authorise entry.

Exact fields: `interpreter_assessment_id`, `interpreter_created_utc`, `interpreter_strengthening_weakening`, `interpreter_agreement_conflict`, `interpreter_manual_checks`, `interpreter_data_gaps`, `interpreter_plain_language_reason`, `interpreter_authority_statement`.

The UI must visually distinguish underlying NBBO size from option contract quote size.

The table view adds only: current contract bid/ask, quote freshness, `ms_lifecycle`, `ms_direction_relationship` and Interpreter assessment state. Detailed numeric fields belong in the ticker modal to preserve usability. Legacy `l2_*` aliases remain readable for two accepted production cycles after MSI-6 activation, but the UI displays only `underlying_nbbo_*`; alias removal is a separate tracked change.

## 12. Pipeline Interpreter redesign

### 12.1 Restrict screenshot dependency to unavailable microstructure

- one structured prompt path for ticker analysis;
- no mandatory general chart or option-chain screenshot package;
- no chart-vs-no-chart logic divergence;
- Level-2/order-book, NOII and broker-only tape screenshots remain required when those specific evidence functions are requested;
- the absence of those screenshots produces `MICROSTRUCTURE_NOT_OBSERVED`, not fabricated neutral data;
- screenshots are supplemental evidence attachments with identity, timestamp, hash and human-confirmation state;
- screenshots cannot override governed direction or quote fields.

The screenshot adapter is delivered as MSI-7b. It uses a provider-neutral `ScreenshotExtractionAdapter` interface. The approved GPT vision implementation records model ID, prompt version and prompt hash. Capture time is operator-declared unless a trustworthy platform timestamp is visible; its provenance is stored as `OPERATOR_DECLARED` or `SCREEN_VISIBLE`. An operator must confirm ticker, screen type and capture time in the Lab before the evidence enters a bundle.

### 12.2 Remove direct data-provider ownership

- decommission direct production calls from Interpreter command handlers;
- the Interpreter calls `resolve_interpreter_evidence()`;
- the resolver calls CDS when refresh is authorised;
- provider keys stay in pipeline data services;
- every refresh produces request-ledger and dataset lineage records.

### 12.3 Preserve useful Interpreter functionality

The Interpreter continues to:

- explain the story of the trade;
- compare evidence across accepted production runs;
- identify strengthening, weakening and invalidation;
- reconcile Lab, Morning, trigger, WBS, GEX and structure evidence;
- show selected-contract bid/ask changes relative to the Morning Gate baseline;
- produce junior-trader checks;
- create the Interpreter assessment sidecar.

`interpreter_assessment_v1` is JSONL and append-only. Code, not the model, fills `assessment_id`, `bundle_id`, `run_id`, `ticker`, `model_id`, `prompt_version`, `prompt_hash`, `temperature`, `created_utc`, governed direction, selected contract, `final_action` and `ms_direction_relationship`. The model fills only strengthening/weakening, agreement/conflict, manual checks, data gaps and plain-language explanation. Temperature is 0.

A post-generation validator rejects publication if the structured output or narrative asserts a different direction, contract, lifecycle or permission from the bundle. A rejected assessment is preserved with `assessment_status = REJECTED_GOVERNANCE_CONFLICT` but is not displayed as valid analysis.

The production `/ticker` path must not rerun `direction_conflict_resolver` or `alternative_contract_selector`; those would create a second direction/contract authority. Chart presence must not select a different numerical prompt contract. Optional web research is isolated as unregistered narrative evidence and cannot enter governed calculations or change the assessment's copied authority fields.

Interpreter-local EV/R:R candidate gates are removed. The Interpreter reports the Morning/Lab monetisability state and `final_action` supplied by the bundle; it cannot independently reject or promote a governed Lab row using legacy EV or R:R fields. `/ete` remains an advisory probability/explanation function only.

It does not:

- select a different contract outside governed repair;
- recompute primary direction in prose;
- invent missing market data;
- grant capital permission;
- treat macro as a veto;
- use test or aborted runs in trajectory analysis.

### 12.4 Macro behaviour inside the Interpreter

Macro is a standalone advisory input. The Interpreter consumes only the governed `macro_quant_packet` referenced by the handoff bundle. It must not search copied `MA_Inputs` folders or select a macro file by modification time.

The macro adapter publishes:

- `macro_context_state`: `TAILWIND`, `NEUTRAL`, `HEADWIND`, `CONFLICTING_SOURCES`, `STALE_CONTEXT` or `DATA_MISSING`;
- semantic `as_of_utc`, session date, freshness and quality;
- sector rotation, rates, USD, credit, volatility, bond and auction context;
- a plain-language advisory explanation.

Macro cannot:

- vote in primary direction resolution;
- change CALL to PUT or PUT to CALL;
- select or repair a contract;
- grant or deny capital;
- change OLM or market-structure lifecycle;
- change Morning Gate checks or `final_action`.

The existing Interpreter `/morning` path is retired from production because Morning Gate owns morning validation. It may be removed or retained under an explicitly labelled research-only command, but it cannot publish into the production handoff.

## 13. Run-history and trajectory rules

Every run writes `run_meta.json` at creation and a final manifest at completion with:

- `run_kind`: `PRODUCTION`, `TEST`, `REPLAY`, `REPAIR` or `RESEARCH`;
- `run_status`: `IN_PROGRESS`, `COMPLETED`, `ABORTED` or `ACCEPTED`;
- `pipeline_mode`: `EOD` or `MORNING_VALIDATION`;
- baseline commit hash, configuration hash and producer versions;
- operator acceptance identity and timestamp when promoted to `ACCEPTED`.

The orchestrator sets kind and operational completion. Only the operator may promote a completed production run to `ACCEPTED` after reconciliation. File presence never implies acceptance.

The proposed previous-ten-run analysis is valid only when each included run:

- is a completed and accepted production run;
- shares compatible schema and calculation versions;
- represents the same session stage being compared;
- has stable ticker, thesis and contract identities;
- excludes test, replay, repair and aborted runs unless explicitly labelled research;
- uses point-in-time evidence available at that run.

Contract quote/Greek trajectories are directly comparable only when the exact OCC contract is unchanged. If contracts differ, use normalised surface coordinates such as constant DTE and delta and label the comparison as normalised.

## 14. Failure behaviour

| Failure | Required result |
|---|---|
| Morning bundle missing | `MORNING_EVIDENCE_MISSING`; no executable interpretation |
| Quote stale during market hours | CDS refresh request; fail closed if unavailable |
| Quote stale outside market hours | use latest completed-session evidence as `EOD_CURRENT` when valid for purpose |
| Contract identity mismatch | `CONTRACT_REQUOTE_REQUIRED`; suppress contract economics |
| Option sizes absent | retain price evidence; label liquidity depth incomplete |
| Intraday bars missing | structure `INSUFFICIENT_DATA`; no fabricated profile |
| Coarse bars only | `COARSE_DATA_LOW_CONFIDENCE`; supporting evidence only |
| Provider failure | use acceptable cache or publish explicit unavailable state |
| Ticker dropped | block provider request and record worklist rejection |
| Identical dataset re-registration | return existing dataset idempotently |
| Same logical observation with changed content | register a governed revision; do not overwrite |
| Interpreter/Lab run mismatch | block publication and require re-resolution |

## 15. Observability

Every run summary must report:

- requested datasets by type;
- exact/superset cache hits;
- physical provider calls;
- calls prevented by worklist drops;
- provider failures and stale-cache uses;
- option-chain bid/ask-size coverage;
- exact-contract bid/ask-size coverage;
- quote-age distribution;
- contract changes and complete-recomputation count;
- one-minute-bar completeness;
- market-structure states and quality classes;
- Interpreter bundle freshness and mismatch counts;
- Lab missing-field and provenance coverage;
- idempotent registration reuse and true conflicts.

Reconciliation invariants:

- provider calls = ledger physical request count;
- every displayed quote has a registered dataset ID;
- every executable record references one current exact contract/structure;
- Lab and Interpreter selected-contract IDs match 100%;
- Lab and Interpreter direction/lifecycle values match 100%;
- no Interpreter analysis is published without a compatible evidence bundle.

## 16. Security, cost and performance

- Provider credentials remain environment-managed and outside payloads/logs.
- CDS request coalescing prevents simultaneous duplicate calls.
- Full option chains are fetched during pipeline acquisition, not per Interpreter request.
- Intraday refreshes request only missing ticker/session intervals.
- Exact-contract refresh is preferred over a full-chain call.
- Market-structure calculation runs only for the authorised surviving worklist.
- Trade/quote event ingestion is deferred until the one-minute implementation proves incremental value and licensing/cost are accepted.

### 16.1 Approved provider ownership

| Requirement | Primary source | Fallback | Production rule |
|---|---|---|---|
| Completed-session option chain | MarketData option chain endpoint | canonical completed-session cache | Never use Polygon options; one chain per surviving ticker/session/scope |
| Exact option quote | MarketData exact-contract quote endpoint | acceptable CDS exact-contract observation | Same OCC contract only; never substitute a contract |
| Underlying NBBO/current price | existing licensed underlying provider used by Morning Gate | acceptable CDS observation | Provider remains behind CDS; Interpreter has no key |
| Underlying one-minute bars | existing licensed underlying aggregate provider | canonical missing-interval cache | Fetch only missing intervals for surviving tickers |
| Macro/rates | standalone macro pipeline and its governed sources | last valid packet labelled stale | Advisory only; not an MSI market-data fetch |
| True depth/NOII/tape | controlled screenshot adapter in v1 | none | Never infer from NBBO or minute bars |

Provider adapters must validate recorded response fixtures for `ok`, `no_data`, `error`, scalar, parallel-array and missing-field responses before activation. Endpoint names, credit costs and plan ceilings are configuration, not literals in consumers.

### 16.2 Request budgets and concurrency

- Full option chains: proposed default maximum one physical fetch per ticker/completed session/scope unless an explicit repair override is recorded.
- Exact-contract quotes: proposed default maximum six physical refreshes per ticker per regular session.
- Underlying quote: proposed default maximum twelve physical refreshes per ticker per regular session.
- Intraday bars: missing intervals are coalesced into one request per ticker per resolver invocation.
- MSI-0 reconciles these proposed limits to the licensed plan and records the approved values in configuration. A configurable global daily ceiling stops new provider calls with `BUDGET_EXHAUSTED`; acceptable cache may still be served.
- CDS uses a file lock per logical observation key with a proposed 30-second acquisition timeout, finalised in MSI-0. A consumer first waits for/reuses an in-flight Morning Gate request; it does not issue a duplicate request. A true conflicting request fails with `REFRESH_CONFLICT`.

### 16.3 Calendar and session clock

All persisted timestamps are UTC. Session state is calculated by one `canonical_data/session_clock.py` service using the XNYS exchange calendar, including holidays, early closes and US DST. Premarket is 04:00–09:30 ET, regular is 09:30 ET to the calendar close, and after-hours is calendar close–20:00 ET. This service owns both current session state and last completed session; consumers cannot recreate these rules locally.

## 17. Compatibility, backup and rollback

### Before implementation

- hash and back up every production file to be modified;
- back up the CDS control-plane database and lifecycle database;
- record current schema fingerprints and latest accepted run ID;
- preserve current Lab and Interpreter outputs as regression fixtures.

### Compatibility

- introduce additive v2 schemas;
- retain old field aliases for one controlled migration window;
- readers accept v1 and v2, writers emit v2 after activation;
- historical v1 data remains immutable;
- do not rebuild the existing actuarial or options history merely to add these fields.

### Rollback

- configuration switches select v1/v2 materialisation;
- rollback restores previous readers/writers without deleting v2 observations;
- never delete newly recorded canonical observations during rollback;
- production activation stops automatically on authority mismatch, missing lineage, registration conflict or Lab/Interpreter reconciliation failure.

## 18. Test strategy

### Unit tests

- MarketData parallel-array parsing, including bid/ask sizes;
- scalar/list provider response handling;
- negative/missing/crossed quote validation and observed zero-bid preservation as `ZERO_BID`/non-executable;
- OCC normalisation;
- freshness by session state;
- idempotent canonical registration;
- worklist request blocking;
- TPO/profile/bin calculations;
- distribution chronology and acceptance transitions;
- data-quality classification.

### Contract tests

- `option_chain_v1` reader compatibility;
- `option_chain_v2` writer completeness;
- exact-contract quote propagation through selected contract and alternatives;
- morning contract change forces all-leg refresh and economics recomputation;
- quote-change comparison is emitted only for the same exact OCC contract;
- Lab evidence-bundle schema and provenance;
- Interpreter accepts only compatible evidence bundles.
- atomic handoff rejects a partial publish, bad hash, wrong run, duplicate ticker or missing bundle;
- overlay allowlist cannot change direction, contract, OLM state, Morning decision or `final_action`;

### Integration tests

- EOD chain fetch -> CDS -> Options Intelligence -> Lab;
- cached rerun produces zero duplicate provider calls;
- Morning refresh -> lifecycle -> Lab -> Interpreter;
- stale Interpreter request -> CDS exact-contract refresh -> new bundle;
- refreshed bid/ask prices and spread changes appear identically in the Lab overlay and Interpreter;
- a Morning contract replacement establishes a new baseline and never produces a false cross-contract price change;
- dropped ticker generates no downstream provider call;
- Level-2 screenshot presence does not change upstream numerical calculations or the prompt contract;
- invalid, mismatched or unconfirmed screenshots cannot publish microstructure evidence;
- explicit loose files and folder-recency scans cannot override the accepted manifest;
- no production Interpreter command can call `live_market_reader` or a market-data provider directly;
- macro state cannot change capital permission;
- structure conflict is disclosed without changing direction authority.

### Regression suites

- direction governance;
- OLM lifecycle and execution guard;
- TC-07/TC-08 and repair-selector observability;
- contract normalisation and selected-contract economics;
- Morning Gate fail-closed behaviour;
- Lab materialisation and field lineage;
- Pipeline Interpreter handoff guard;
- CDS cache, registry and request ledger;
- latest accepted EOD and Morning fixtures.

### Production-cycle acceptance

1. Complete one fresh evening pipeline with v2 capture enabled.
2. Verify canonical size coverage and zero registration conflicts.
3. Complete Morning Gate on the same run.
4. Verify exact-contract refresh, lifecycle and Lab rematerialisation.
5. Execute Interpreter analysis from the Lab.
6. Verify no direct Interpreter provider call and 100% identity alignment.
7. Obtain user acceptance before enabling the new fields as the standard production view.

## 19. Build and implementation sequence

### Phase MSI-0 — Baseline and protection

- freeze design and field definitions;
- capture backups, hashes, schemas and regression fixtures;
- record the current production baseline commit/hash and every intended modified file;
- classify outstanding working-tree changes as included baseline, unrelated user work or excluded archive;
- record the status of OLM, CDS idempotency, hydration, direction governance and handoff fixes;
- publish the module map, ID rules, enums and provider fixtures defined in this document;
- add run kind/status fields and operator acceptance support;
- define feature/configuration switches;
- add authority and source-of-truth tests before code changes.

**Exit:** reproducible baseline and rollback package.

### Phase MSI-1 — MarketData and canonical quote completeness

- parse option `bidSize` and `askSize` from chain and exact quote responses;
- rename underlying NBBO fields with backward aliases;
- implement `option_chain_v2`, `exact_option_quote_v2` and `underlying_nbbo_quote_v1`;
- propagate sizes through primary contracts, alternatives, repairs and lifecycle persistence;
- make identical registration idempotent;
- add aggregate coverage diagnostics.

**Exit:** contract size data is preserved end to end with lineage and no regressions.

### Phase MSI-2 — Central freshness and refresh resolver

- implement shared session-aware freshness policy;
- expose CDS evidence-resolution requests;
- enforce active worklist and request coalescing;
- implement exact-contract-first refresh;
- remove duplicated freshness decisions from consumers.

**Exit:** deterministic cache/fetch decisions and no direct Interpreter provider access.

### Phase MSI-3 — Canonical one-minute data

- implement the one-minute bar contract and partitions;
- backfill only the agreed calibration window;
- fetch only surviving candidates and missing intervals;
- validate session boundaries, completeness and adjustments;
- publish bar-quality diagnostics.

**Exit:** governed minute data is available for the authorised candidate set.

### Phase MSI-4 — Market Structure Evidence Service

- build deterministic TPO/profile calculations;
- implement distribution, chronology, acceptance, repair and failure states;
- version parameters and evidence records;
- add direction-relationship output without authority;
- test against synthetic and hand-labelled sessions.

The initial calibration proposal uses 60 completed sessions for a capped representative candidate set and at least 40 human-labelled ticker-sessions, with at least 10 examples for each available profile type. Labels contain ticker, session, profile type, distributions, lifecycle at close, labeller and label date. Proposed activation targets are at least 80% agreement on profile type and at least 85% agreement on direction relationship. MSI-0/MSI-4 must approve or version-replace the sample sizes and targets before they become production criteria; otherwise the service remains `INSUFFICIENT_DATA`/advisory.

**Exit:** repeatable structure evidence with explicit quality labels.

### Phase MSI-5 — Morning Gate integration

- route live underlying and exact-contract observations through CDS;
- include option quote sizes;
- recompute every dependent field after contract replacement;
- recalculate morning structure evidence;
- persist the evidence bundle and diagnostics.

**Exit:** one governed morning record contains all current execution evidence.

### Phase MSI-6 — Intelligence Lab integration

- extend final book and provenance maps;
- display underlying NBBO and option sizes separately;
- add freshness, structure and quality sections;
- publish the Interpreter evidence bundle;
- add refreshed evidence overlays without mutating historical books.

**Exit:** the Lab is complete and internally reconciled for every displayed ticker.

### Phase MSI-6a — Macro advisory correction

- consume only the governed macro packet referenced by the bundle;
- remove macro from direction voting, contract selection and execution conditions;
- enforce semantic freshness and quality;
- retire the production Interpreter `/morning` path;
- prove every macro state leaves governed outputs unchanged.

**Exit:** macro adds context but has zero directional, contract or capital authority.

### Phase MSI-7a — Pipeline Interpreter structured integration

- replace multiple source/prompt paths with the single resolver;
- remove mandatory general screenshots and direct provider calls;
- consume the governed bundle;
- display Morning Gate and current selected-contract bid/ask, change, spread change and freshness;
- emit an append-only explanation sidecar;
- expose the explanation in the Lab;
- enforce run/thesis/contract identity at publication.

**Exit:** Interpreter and Lab show the same governed structured evidence and pass the atomic handoff reconciliation.

### Phase MSI-7b — Controlled screenshot adapter

- implement the GPT screenshot extraction adapter for Level-2, NOII and broker-only tape only;
- bind, hash, classify and preserve images;
- add operator declaration and confirmation UI;
- prevent unconfirmed screen evidence from entering a bundle;
- prove screenshots cannot change upstream calculations or authority.

**Exit:** screenshots are required only for explicitly requested unavailable microstructure and remain supplemental.

### Phase MSI-8 — End-to-end production acceptance

- run full unit, contract, integration and regression suites;
- execute a fresh evening-to-morning cycle;
- validate one controlled intraday Interpreter refresh;
- review performance, API calls, data completeness and UI accuracy;
- activate v2 production materialisation after acceptance;
- retain rollback switches for the agreed observation period.

Activation requires two accepted production cycles after MSI-7a: evening -> Morning Gate -> Lab -> Interpreter. MSI-7b may activate later and does not block structured Interpreter production.

**Exit:** production acceptance signed with measured evidence.

## 20. Acceptance criteria

The enhancement is production-ready only when:

1. MarketData option bid and ask sizes reach CDS, Morning Gate, Lab and Interpreter without field loss.
2. Underlying NBBO fields are no longer represented as full Level 2.
3. No direct production MarketData calls originate in Pipeline Interpreter code.
4. A fresh Morning bundle prevents a duplicate Interpreter API call.
5. A stale intraday bundle triggers one governed CDS request, not a full-pipeline refetch.
6. Dropped tickers trigger zero subsequent provider calls.
7. Contract replacement always refreshes the replacement and recomputes every contract-dependent field.
8. Structure evidence is deterministic, versioned, quality-labelled and non-authoritative.
9. Lab and Interpreter match on run, thesis, direction, contract, quote snapshot and lifecycle for every ticker.
10. Interpreter quote changes use two registered snapshots of the same exact OCC contract and match the Lab overlay.
11. Level-2/NOII/tape screenshots are identity-bound, timestamped, hashed and human-confirmed; they do not overwrite calculated outcomes.
12. All existing authority, OLM, Morning, Lab and CDS regression suites pass.
13. A complete evening-to-morning-to-Interpreter production cycle passes reconciliation.
14. The Interpreter consumes only an atomically published, hash-verified handoff manifest.
15. Macro state cannot change direction, selected contract, lifecycle, `final_action` or capital permission.
16. Test, replay, repair and aborted runs are excluded from production trajectory analysis.
17. No production component invents a missing thesis or contract identity.

## 21. Recommended decision

Proceed with the enhancement using the phased sequence above. Do not create a separate independent database or let the Interpreter call MarketData directly. Extend the existing CDS and Lab contracts so every consumer sees the same governed observations.

The Morning Gate should remain the normal producer of fresh trading-session evidence. The Interpreter should reuse that evidence and invoke a CDS-managed narrow refresh only when the bundle is genuinely stale for its intended use.

## 22. Approved module map

| Component | Existing owner to modify/reference | New module where required | Responsibility |
|---|---|---|---|
| Discovery/worklist | `avshunter_discovery_ULTIMATE.py`, `canonical_data/discovery_publisher.py`, `canonical_data/worklist_gate.py` | none | Authorised ticker set and dropped-ticker enforcement |
| CDS request/registry | `canonical_data/gateway.py`, `registry.py`, `contracts.py`, `request_ledger.py`, `storage.py` | `canonical_data/market_observation_service.py` | Resolve-before-fetch, provider adapters, persistence and request accounting |
| Session clock | duplicated consumer logic to be removed | `canonical_data/session_clock.py` | XNYS session boundaries and semantic freshness |
| OCC identity | `contracts/selected_contract_economics.py`, `canonical_data/contract_reference.py` | `canonical_data/option_identity.py` | One canonical compact OCC parser/normaliser; old functions become imports/aliases |
| Options Intelligence | `scripts/avshunter_options_intelligence.py`, `canonical_data/option_chain_store.py` | none | Completed-session MarketData chain, sizes and selected exact-contract observation |
| Selected-contract economics | `contracts/selected_contract_economics.py` | none | Single-leg hydration and governed Morning monetisability |
| OLM | `contracts/options_liquidity_lifecycle.py`, `canonical_data/option_liquidity_lifecycle.py`, `contracts/options_liquidity_execution_guard.py` | none | Existing lifecycle authority; MSI reads but does not replace it |
| Market Structure | none | `market_structure/contracts.py`, `params.py`, `profile.py`, `service.py` | Deterministic structure calculation and evidence records |
| Morning Gate | `morning_gate.py` | none | Current observations, structure refresh and authoritative Morning record |
| Handoff finalisation | `morning_handoff_finalizer.py`, `contracts/handoff_contract.py` | `contracts/interpreter_handoff.py`, `tools/msi_reconcile.py` | Atomic publication and non-zero reconciliation guard |
| Lab materialisation | `contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py` | `contracts/lab_evidence_overlay.py` | Book v3, overlay validation, provenance and trader view |
| Lab UI | `intelligence-lab/static/index.html` | none | Exact approved MSI field groups and Interpreter explanation |
| Interpreter resolver | `pipeline_interpreter/pipeline_interpreter_commands.py`, `pipeline_interpreter_engine.py` | `pipeline_interpreter/evidence_resolver.py` | Manifest/bundle resolution and CDS narrow refresh request |
| Interpreter output | active prompt/engine modules | `pipeline_interpreter/assessment_contract.py` | Structured assessment, validation and append-only sidecar |
| Interpreter macro | `pipeline_interpreter/news_macro_readers.py`, `direction_conflict_resolver.py`, system prompt | `pipeline_interpreter/macro_context.py` | Governed advisory macro context with zero authority |
| Structured automation evidence | `pipeline_interpreter/automation_v2/` | extend existing manifest contracts | Reuse run/ticker/invocation evidence identity; does not itself replace the production handoff |
| Screenshot adapter | existing chart/screenshot commands, `pipeline_interpreter/capture_v1/` | `pipeline_interpreter/screenshot_adapter.py` | Extend allowlisted read-only capture with GPT extraction, image hash, capture provenance and human confirmation |
| Orchestration | `intelligent_orchestrator.py` | none | Phase ordering, feature switches, manifests and run summaries |

No archived, backup, `old`, `dnu` or shadow module may be selected as an implementation target. MSI-0 records the exact active entry point and function for every row before edits begin.

The build extends rather than recreates the existing CDS immutable registry, scope resolver, request ledger, worklist gate and option-chain cache; existing OLM lifecycle/guard/persistence; selected-contract repair and economics recomputation; Morning handoff finalizer; Interpreter v2 EvidenceManifest concepts; and capture v1 read-only ticker verification. Existing Vanguard market-profile primitives may be individually tested and reused, but its fixed-bin dormant implementation is not activated wholesale. `maturation_score_*` remains deterministic, non-probability and non-authoritative.

## 23. Identity and canonicalisation rules

| Identity | Owner | Rule |
|---|---|---|
| `run_id` | orchestrator | Existing run identity; immutable within one EOD/Morning baton |
| `thesis_id` | OLM/upstream thesis lifecycle | Existing ID is mandatory in production; Morning/Interpreter fallback minting is prohibited |
| `trade_idea_id` | Lab materializer | Existing deterministic per-run ID; immutable after book publication |
| `selected_structure_id` | selected-contract economics | Existing deterministic evaluation ID over ticker, direction, structure and ordered contract symbols |
| `selected_quote_snapshot_id` | selected-contract economics | Existing SHA-256-derived identity over structure and exact quote content |
| `dataset_id` | CDS | Existing immutable content identity; identical reuse is idempotent |
| `ms_evidence_id` | Market Structure service | SHA-256 of ticker, session, algorithm version, parameter version and ordered input dataset IDs |
| `bundle_id` | handoff materializer | UUID per bundle materialisation |
| `interpreter_assessment_id` | assessment writer | UUID per model assessment |

The canonical internal OCC representation is compact uppercase: optional provider prefix removed, spaces removed, root preserved, then `YYMMDD`, `C`/`P`, and eight-digit strike multiplied by 1000. Adjusted roots such as `AAPL1` remain distinct. Provider adapters may serialize differently at the boundary but must return the same canonical identity.

Required parser vectors include standard, decimal-strike, short-root, dotted-root and adjusted-root examples: `AAPL260918C00150000`, `AAPL260918P00150500`, `AAPL1260918C00150000`, `BRK.B260918P00500000`, `SPY260918C00600000`, `TSLA260918P00250500`, `IWM260918C00200000`, `X260918P00025000`, `F260918C00015000`, and `GOOGL260918P00200000`.

For each canonical dataset contract, the logical observation key is dataset type + instrument/contract identity + session + scope + schema version + provider. The content hash is SHA-256 of canonical sorted JSON excluding registry-generated IDs, request ID, run ID and registration time; economically meaningful provider timestamps remain included. A changed content hash creates a new immutable dataset/revision. An identical hash reuses the existing dataset ID.

## 24. Canonical status enumerations

Enums live in their owning contract module and are imported, never redeclared as local string sets.

| Enum | Values |
|---|---|
| Run kind | `PRODUCTION`, `TEST`, `REPLAY`, `REPAIR`, `RESEARCH` |
| Run status | `IN_PROGRESS`, `COMPLETED`, `ABORTED`, `ACCEPTED` |
| Freshness | `FRESH`, `EOD_CURRENT`, `STALE`, `MISSING`, `INVALID` |
| Quote quality | `TWO_SIDED`, `ONE_SIDED`, `CROSSED`, `MISSING`, `INVALID` |
| Size quality | `OBSERVED`, `OBSERVED_ZERO`, `MISSING`, `INVALID_SIZE` |
| Comparison | `SAME_CONTRACT`, `CONTRACT_CHANGED`, `BASELINE_MISSING`, `BASELINE_ZERO`, `CURRENT_MISSING`, `STALE` |
| Structure lifecycle | `MS_DEVELOPING`, `MS_ACCEPTED`, `MS_CONTINUING`, `MS_REPAIRING`, `MS_FAILED` |
| Structure relationship | `ALIGNED`, `CONFLICTING`, `NEUTRAL`, `INSUFFICIENT_DATA` |
| Structure quality | `TRADE_LEVEL_CONFIRMED`, `ONE_MINUTE_ESTIMATED`, `COARSE_DATA_LOW_CONFIDENCE`, `INSUFFICIENT_DATA` |
| Handoff | `READY`, `BLOCKED_MISSING_STAGE`, `BLOCKED_IDENTITY`, `BLOCKED_HASH`, `BLOCKED_RECONCILIATION` |
| Assessment | `VALID`, `REJECTED_SCHEMA`, `REJECTED_GOVERNANCE_CONFLICT`, `REJECTED_STALE_BUNDLE` |

## 25. Interpreter command disposition

| Command/function | Production disposition |
|---|---|
| `/triage`, `/ticker`, `/quick`, `/story`, `/update`, `/intraday`, `/ete` | Rewire to the handoff manifest and shared evidence resolver; `/intraday` and `/ete` remain advisory |
| `/sync` | Synchronise only a validated handoff; no broad directory copy |
| `/morning` | Remove from production; Morning Gate is authoritative |
| `/live` | Retire from production; it must not call the legacy direct provider reader |
| `/interpret`, `/load`, `/options`, `/macro`, `/news`, `/price`, `/lab` | Research/admin only; loose files cannot enter production publication |
| `/chart` | Research/general chart use; MSI-7b handles only approved microstructure evidence |
| `/brief`, `/note`, `/sector-note` | Supplemental human narrative, isolated from governed fields and authority |
| `/inputs`, `/status` | Report accepted-manifest, hash and bundle integrity rather than folder counts/mtime |
| `/notes`, `/reset`, `/menu`, `/exit` | Diagnostic/session-local only |
| `/auto` | Resolve the accepted manifest or retire; no legacy undefined handler |

All command paths call one resolver. No command implements its own freshness, macro, contract selection or provider logic.

MSI-0 removes or disables active router entries whose implementations exist only in `Archive`; no production command may resolve through archived functions. `morning.bat` is retired because it invokes the obsolete Interpreter morning path. The valid Morning workflow remains the production Morning Gate launcher.

## 26. Feature switches and storage

Feature switches are read from one configuration module and default off until their phase passes acceptance: `MSI_V2_CAPTURE`, `MSI_CDS_RESOLVER`, `MSI_MINUTE_BARS`, `MSI_STRUCTURE`, `MSI_LAB_V3_VIEW`, `MSI_MACRO_ADVISORY`, `MSI_INTERPRETER_RESOLVER`, `MSI_SCREEN_ADAPTER`.

Run-scoped artefacts live under `data/output/runs/{run_id}/`:

- `canonical/` — CDS observations and request ledger extracts;
- `market_structure/` — evidence records and summaries;
- `intelligence_lab/` — book v3, manifest and overlays;
- `interpreter/bundles/` — governed bundles;
- `interpreter/assessments.jsonl` — append-only assessments;
- `interpreter/handoff_manifest.json` — atomic production baton;
- `screens/` — original and extracted screen evidence;
- `diagnostics/msi_reconciliation.json` — acceptance evidence.

Retention follows the run archive policy. Rollback switches restore the prior readers but never delete v2/v3 canonical observations.

## 27. Agent build responsibilities

Only two implementation agents may work concurrently.

### Agent 1 — Canonical data and deterministic structure

Owns:

- `canonical_data/` additions and approved modifications;
- MarketData option-size parsing and fixtures;
- OCC identity migration;
- shared session clock/freshness;
- `market_structure/` calculation package;
- unit and contract tests for data, formula and structure behaviour.

Must not edit `morning_gate.py`, Lab, Interpreter, execution authority or orchestrator files. Deliverables are a changed-file manifest, fixture inventory, test results, performance measurements and unresolved assumptions. No production run.

### Agent 2 — Handoff, Interpreter and trader display

Owns:

- `contracts/interpreter_handoff.py` and assessment/overlay contracts;
- `pipeline_interpreter/` resolver, macro correction, command rewiring and assessment validation;
- `intelligence-lab/` MSI display and screenshot confirmation UI;
- handoff, UI, macro non-authority and Interpreter regression tests.

Must not edit CDS registry/provider code, Options Intelligence, Morning Gate, execution authority or orchestrator files. Deliverables are a changed-file manifest, command disposition evidence, UI field reconciliation, tests and unresolved assumptions. No production run.

### Primary agent — integration authority

The primary agent alone owns shared integration files: `intelligent_orchestrator.py`, `morning_gate.py`, `contracts/lab_control.py`, `morning_handoff_finalizer.py`, feature activation, cross-workstream conflict resolution, full regression, backup/rollback verification and production-cycle acceptance.

Before integration, each agent must prove its public contract against frozen fixtures. The primary agent then integrates Agent 1 outputs into Morning Gate/Lab, integrates Agent 2 against the resulting bundle, runs `msi_reconcile.py`, and only then executes the manual evening pipeline requested by the user.

## 28. Implementation control sequence

1. Primary agent completes MSI-0, backups, working-tree classification, module map and frozen contracts.
2. Agents 1 and 2 build against those contracts in parallel without shared-file edits.
3. Primary agent reviews every change, imports both workstreams and resolves interface differences.
4. Run new unit/contract suites, then all existing OLM, direction, monetisability, Morning, Lab, Interpreter and CDS regressions.
5. Run offline fixture EOD -> Morning -> Lab -> Interpreter reconciliation.
6. Enable capture/resolver/structure flags sequentially; never activate all switches at once without phase evidence.
7. User runs the evening orchestrator manually.
8. Primary agent validates outputs and then authorises the matching Morning Gate test.
9. User runs Morning Gate manually.
10. Primary agent validates book v3, atomic handoff, Interpreter assessment, macro non-authority and UI accuracy.
11. Repeat for a second accepted production cycle.
12. After user acceptance, make MSI-7a the standard production path. MSI-7b may follow independently.
