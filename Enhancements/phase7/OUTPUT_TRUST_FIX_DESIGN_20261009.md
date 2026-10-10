# Output-trust fix design: one accurate fix per defect, in assembly-line order (draft for ACK approval)

**Date:** 9 Oct 2026. **Model:** the pipeline is an assembly line; each station's part is inspected and repaired at that
station, so the Lab (the car) arrives with zero defects (ACK, 9 Oct). **Decisions in force:** the legacy classifiers are
made inactive, not deleted (ACK 9 Oct); rank, don't gate; GO = the thesis's own trigger accepted (5.3); one rank owner
(E11b). **Evidence:** the SMCI / MSFT trace on run 20261008_220129 and two code audits (9 Oct). Each fix is test-first,
with acceptance on a replay of that run, and lands one at a time.

## Station 2: Discovery (the thesis)

### D2-1 Contradictory structure labels (SMCI: SOS → LPS activated, beside DISTRIBUTION / ACCUMULATION_SPRING / UTAD)

**Root cause:** two classifiers write onto one card.
- **The thesis engine** writes the BEH-001 candidates and the `thesis_event*` fields.
- **The legacy Wyckoff engine** (`WyckoffEngine_3101_v2`) writes `wyckoff_mode`, `_phase_bucket`, `_phase_granular`, `phase` and `wyckoff_score`. Plus its validator (`wyckoff_phase_validator.py`, writing `wyckoff_validation_*`) and two copies built from it: `forecast_structure_stage` and `structure_evidence_*`.

**The legacy engine is load-bearing.** Its readers include:
- Discovery's composite, tier, tier-4 drop, win probability and in-tier ranking (`avshunter_discovery_ULTIMATE.py` lines 637–657, 1456–1515, 1676–1690, 2205–2216);
- Vanguard's state hash (`wyckoff_phase_bucket` → `state_calculator`);
- the EV3 barrier key;
- the Options phase points and strategy;
- the trap engine and the trigger layer;
- `final_decision_engine` (a pattern conflict forces WATCHLIST);
- the catastrophe gate.

**Fix, in two steps:**
- **Step A, the card. No decision effect.**
  - The structure block comes only from the thesis engine. It shows:
    - analysis scope: ticker, timeframe, candidate ID, range and box boundaries, evidence session, policy version;
    - structure;
    - phase;
    - current event and its status (candidate / observed / supported / failed / historical, mapped from the engine's states and the trigger events);
    - failure evidence;
    - current bias, from the top-down spine;
    - trade status (readiness);
    - predictive validation.
  - Another timeframe's opposite structure is shown as scoped context, never hidden.
  - Off the card, into the audit tier (none has a decision reader): `wyckoff_validation_*` (heuristics), `forecast_structure_stage`, `structure_evidence_*` and the legacy `wyckoff_*` labels.
- **Step B, the decisions, station by station.** Each legacy input is replaced with its thesis-engine equivalent, then switched off by a per-producer configuration switch. The code is kept for rollback.
  - **Discovery tier, composite and ranking:** replaced by the thesis disposition (adoption, readiness, evidence) and the E11b rank. *This changes which tickers survive, so it gets its own design and replay before approval.*
  - **Options phase points, strategy and trigger probe:** read the thesis phase and readiness.
  - **Trap engine and trigger layer:** read the thesis events (failed break = trap).
  - **`final_decision_engine`:** the conflict rule reads the thesis conflict count.
  - **Vanguard state hash and EV3 key:** **kept as context** until the actuarial database is rebuilt on thesis states. Vanguard is context-only, so this causes no decision harm. Labelled `LEGACY_STATE_KEY`.

**Proof:**
- zero structure contradictions within the same scope;
- reviewed examples (supported spring, failed spring, breakdown, upthrust, mixed timeframes, ambiguous range — ACK's "Soul of the Chart" labelled set) replayed with point-in-time data;
- the same data gives the same result.

### D2-2 "Direction CONFIRMED" beside "no measured direction edge"

**Root cause:**
- `direction_governance_status = CONFIRMED` and `direction_resolution_path = DIRECTION_CONFIRMED` (`contracts/direction_governance.py:773–786`) mean "the governed record is consistent", with 0 evidence votes.
- `direction_governance_status` has **no reader**. `direction_resolution_path` is read only for record-parity checks.

**Fix:** three separate claims on the card:
- **Structural bias:** the thesis side and the timeframe that set it.
- **Trigger:** readiness and its deciding event.
- **Predictive edge:** `TESTED_NO_EDGE` with the study reference (7 Oct direction study, universe test 8 Oct). Kept distinct from `NOT_TESTED` and `INSUFFICIENT_EVIDENCE`.

The record-consistency fields are renamed `direction_record_status` (display: "record consistent"). The integrity validator (`validate_direction_record`) stays; it guards real gates.

**Proof:** no row claims validation it doesn't have, and every confidence claim names its test.

### D2-3 Geometry: far invalidation, near target (lane A median reward/risk 0.64; FUN 0.32)

**Root cause:**
- The governing setup's own failure level (I-c) is a weekly or monthly campaign level (median 8.8 daily ATR in lane A).
- The target is the next outcome level (4.7 ATR).
- Ordering is already correct on all 2,367 directed rows, and only 19 stops are under 1 ATR.

**Fix:** a geometry block per card, measured from the **planned executable entry**: the session price for a ready thesis, the thesis trigger for a waiting one.
- Target and invalidation, each with its owning setup.
- Reward and risk in price and in **daily ATR(14)**.
- The early-warning level (I-c) as a second, labelled risk view.
- **Break-even hit rate** = risk / (risk + reward), against the setup's measured hit rate (n and interval).
- `GEOMETRY_NOT_JUSTIFIED` when the measured rate is below break-even.
- `INVALID_GEOMETRY` when the order is broken or risk ≤ 0, never an infinite ratio.
- The target is never moved.
- The option side is valued separately (D5-1).

*Decision pending (recommended): a row that is not justified stays visible and ranked but cannot be GO.*

**Proof:** valid ordering on every row; every justification shows its two rates.

## Station 5: Options (the expression)

### D5-1 Four payoff numbers (SMCI: +207%, 2.16×, −2.1%, −38%)

**Root cause:** four producers with four definitions.

| Figure | Field | What it really is |
|---|---|---|
| +207% | `option_gain_at_target` | **$2.07 per share**: expiry intrinsic at the target minus the mid. A unit mislabel. Display-only readers |
| 2.16× | `anticipated_value_multiple_q50` | European Black-Scholes value at the reachable level by the median time, divided by the ask. r = q = 0, IV held. **Drives the pays state, the rank and lane B** |
| −2.1% | `monetisability_target_profit_pct` | Expiry intrinsic at the median level against the ask. Moved to audit for decisions under L5, but residue remains (the `economics_comparable` flag and a SOFT_CONFLICT warning) |
| −38% | `ev3_ev_conservative_return` | The historical-state expected value, including failures. Advisory (E09) |

**Fix: one valuation engine, three labelled scenarios.**
- **Engine:** reuse EV3's American CRR pricer (`vanguard/ev_engine_v3.american_option_price`) for US stock and ETF options; Black-Scholes-Merton for European index options (SPX and the like).
  - The interest rate comes from governed configuration.
  - Dividends: a continuous yield from the dividend history, labelled `DIVIDEND_YIELD_FROM_HISTORY`, or `ASSUMED_ZERO` when unknown. Discrete ex-dividend dates follow as a second step (`domain/deterministic_option_valuation.py` already carries an ex-dividend flag).
- **Scenarios, each with its exit date and IV assumption, after spread and fees,** as return on premium:
  - **Target reached:** the reachable level by the median time.
  - **Invalidation reached.**
  - **Trade stalls:** little progress, time elapsed.
  - A lower-IV case where an earnings date falls inside the hold.
- **Units in every name:** `scenario_target_return_on_premium`, and so on.
- `anticipated_pays_state` is computed from the target scenario of the same engine.
- **Off the card:** `option_gain_at_target` (renamed `..._usd_per_share`), the monetisability residue, and EV3, until its E09 rewiring.

**Proof:**
- benchmark cases;
- tree convergence;
- agreement with an independent finite-difference American model;
- a separate execution check of the prices against quotes.

### D5-2 Put wall at $3 (SMCI spot about $43)

**Root cause:** `compute_oi_walls` takes the highest-OI strike strictly below spot, summed over every expiry up to 110 days, with no distance limit and no gamma weighting.

**Fix:**
- Walls are computed **per non-overlapping expiry bucket**: ≤ 7 days, 8–45 days, 46–110 days.
- Gamma-weighted, within ±30% of spot.
- Each wall carries its instrument, bucket, as-of date and method.
- The readers (the Wall-Break scorer, the exit-plan T1 target, the OIS ±5 points, the SuperBrain runway veto) read the bucket that matches the hold.

**Proof:** every wall states its scope; SMCI's wall is a strike traders could actually see.

### D5-3 Gamma flip shown as a level whatever its confidence

**Fix:**
- Show `gamma_flip` together with `gamma_flip_conf` and the method.
- Below a governed confidence threshold the state is `LOW_CONFIDENCE`: the level is shown as indicative and isn't used as a level by readers.
- The dealer sign stays labelled as an assumption.

### D5-4 SPY's dealer gamma shown as the ticker's

**Root cause:** `pipeline_interpreter/automation_v2/market_structure.py:27–28` aliases the ticker's `gex_regime` and `gex_score` to the macro packet's SPY `dealer_gamma_state` and `gex_regime_score`.

**Fix:** remove the aliases. The ticker's GEX comes only from its own chain; the market-wide SPY value is shown under "Market (SPY)", as worker3 already labels it.

### D5-5 IV rank window labelled 252 days but holding 66 samples

**Root cause:** `ivp_source` is the fixed name `IV_HISTORY_252D`, while `iv_rank_window_sessions` = `len(history)` = 66. The cache was only restored on 8 Sep.

**Fix:**
- The label states the samples actually used.
- `SHORT_HISTORY` is flagged below 252 samples.
- IV rank (range position) and IV percentile (share below) are shown separately, each with its definition.

## Station 6: carry and journal

### D6-1 508 surfaced rows not journalled (G2-05)

**Fix:** a per-ticker disposition record for every surfaced idea, triggered or not. The decision-time setup, levels, contract, price, stated probability and model version are frozen. No thesis or contract identity is invented.

## Station 7: reference data

### D7-1 Earnings dates (MSFT 4 Nov vs 28 Oct)

**Fix:**
- Confirmation tiers:
  - `VENDOR_ESTIMATE`;
  - `CORROBORATED`: MarketData and tastytrade agree. Tastytrade is read through the client the macro board already uses;
  - `ISSUER_CONFIRMED`: from the intelligence mining process. This needs no pipeline change.
- Before-open or after-close timing, and the date checked.
- Disagreements flagged.

## Calibration and inspection (all stations)

- **C-1 Calibration.**
  - The event is defined exactly: "target before invalidation within the planned hold".
  - Outcomes come from the outcome scorer. Ambiguous same-bar order is already labelled; gaps and ticker clustering are handled. Option outcomes come from real chain marks.
  - Pooled lane rates are replaced by per-setup rates with n, an interval and shrinkage.
  - The card shows "uncalibrated" until enough outcomes exist.
  - Calibration slope and intercept are reported, not only "within ±10".
- **C-2 Station inspections.** A check after each stage writes that station's defect report; integrity defects stop the line with the reason. The end-of-line verifier reports five scorecards: data, calculation, structure, calibration and trading performance.

## Order of work (assembly line)

1. **Station 2, Discovery:**
   1. D2-1 Step A (the card's structure block);
   2. D2-2 (direction wording);
   3. D2-3 (geometry block).
2. **Station 5, Options:**
   1. D5-1 (one valuation engine and its scenarios);
   2. D5-4 (the SPY gamma leak);
   3. D5-5 (IV labels);
   4. D5-2 and D5-3 (walls and gamma flip).
3. **Station 6, carry and journal:** D6-1 (the journal).
4. **Station 7, reference data:** D7-1 (earnings tiers).
5. **D2-1 Step B, station by station.** It has its own Discovery-survival design and replay first.
6. **C-1 and C-2,** running every night from the first change.

## Decisions (ACK approved all four, 9 Oct 2026)

1. **Geometry:** `GEOMETRY_NOT_JUSTIFIED` rows stay visible and ranked but cannot be GO.
2. **Valuation engine:** reuse EV3's American CRR as the single engine, with a continuous dividend yield from history first and discrete ex-dividend dates second.
3. **D2-1 Step B, the Discovery tier and composite:** a separate design and replay before replacing the legacy score.
4. **The Vanguard state key:** keep the legacy key, labelled, until the actuarial database is rebuilt on thesis states.

## Execution checklist (work only from this list; test-first; one item at a time; tick when its tests pass)

- [x] 1. D2-2 direction wording: three claims; `direction_record_status` rename (display)
- [x] 2. D2-1 Step A: structure block from the thesis engine on the card; legacy structure fields to the audit tier (`tests/test_ot2_structure_block.py`; live 8 Oct book: 2,370 thesis rows show scope, phase · event, status, failure evidence, other timeframes; 0 legacy Wyckoff labels on the card; Lab table/modal read the thesis engine; Discovery column named "Legacy Wyckoff". Card tests now feed node over stdin - the card passed the 32 KB Windows command-line limit)
- [x] 3. D2-3 geometry block + `GEOMETRY_NOT_JUSTIFIED` cannot be GO (decision 1). Owner `domain/trade_geometry.py` (computed in Discovery, travels with the thesis spine); GO refused in `trigger_layer.thesis_go_eligibility`; Evening bucket `EOD_GEOMETRY_REVIEW`; Morning names the refusal (not "wait for the trigger"); card row "Geometry". Lane hit-rate n added to `config/beh001_lanes_v1.json` (lane A reproduced exactly from eval_v5 records, `Enhancements/phase7/lane_hit_n.py`; lane B pooled R2 rows). Tests `tests/test_ot3_trade_geometry.py` (11). Replay on the live 8 Oct book (`Enhancements/phase7/ot3_live_geometry.py/.json`): of 745 ready rows, lane A 421 measured -> 155 JUSTIFIED, 266 GEOMETRY_NOT_JUSTIFIED (no longer GO, still visible and ranked); lane C 324 NOT_MEASURED (labelled, still GO). Label: hit rates were measured from each setup's activation/detection, not from the planned entry.
  - Found while replaying (separate defect, not fixed here): on 63 ready rows the book's `target_price` is blank (`target_state` UNRESOLVED, STRUCTURAL_TARGET_UNRESOLVED) while `structural_target` holds the governing Outcome_Level. Production geometry reads the governing level in Discovery, so it is unaffected; the blanking stage needs tracing (station inspection, item 10).
- [x] 4. D5-1 one valuation engine (EV3 CRR, dividend yield from history; decision 2), three scenarios, units; pays state from it; legacy payoffs off the card. Engine `domain/option_valuation.py` (EV3 `american_option_price` reused; BSM for European index roots; config `option_valuation`); scenarios in the one owner `domain/anticipated_move.py` (target / invalidation / stall / earnings-IV, return on premium after spread and fees, exit at the median time); value multiple, pays state, rank and lane B = 1 + the target scenario. Dividend store `canonical_data/dividend_history.py` + `scripts/fetch_dividend_history.py` (ACK runs; until then ASSUMED_ZERO, labelled). Card: Scenarios row; EV3, monetisability, `economics_comparable`, `option_gain_at_target` in the legacy tier. Lab headline: the target scenario (EV3 stays only in the audit export column the Interpreter reconciles; scenario columns added). Lab soft warning from the engine's pays state. Tests `tests/test_ot4_one_valuation_engine.py` (16: benchmarks, call = European, convergence, independent finite-difference American model). Live 8 Oct: `Enhancements/phase7/ot4_quote_check.json` (2,173 contracts: 93% of entry values inside the quoted bid-ask, median error 1.0% of mid); `ot4_live_revaluation.json` (1,222 valued; 159 PAYS -> DOES_NOT_PAY once spread and fees count, 2 the other way; median multiple 0.91x the old gross European figure).
  - Dividends (ACK 10 Oct 2026: "use tastytrade for dividends instead of polygon"): `canonical_data/tastytrade_metrics.py` fetches tastytrade market metrics once per Evening (read-only bridge, cached per session) for both the earnings tiers and the dividend yield; `canonical_data/dividend_history.dividend_inputs` reads the newest cache within 7 days (yield; else annual/spot; explicit zero = none; per-payment rate alone is not annualised - ASSUMED_ZERO, stated; next ex-date carried in the basis). The Polygon fetch script and sqlite store (never run) are removed.
  - Deviations, recorded: `option_gain_at_target` is not renamed (ten readers; it is off the card and labelled USD per share in the legacy tier). Rate: governed fallback 4.22% (T3M, 8 Oct) - callers do not yet pass the run's observed rate (`load_market_rate`); next step. Fees are an approximate tastytrade schedule - ACK to confirm. Discrete ex-dividend dates remain the second step.
- [x] 5. D5-4 remove the SPY gamma alias. `pipeline_interpreter/automation_v2/market_structure.py`: ticker `gex_regime` / `gex_score` read the ticker's own chain only (gex_regime / eil_gex_regime, gex_score / eil_gex_score); SPY published separately as `market_dealer_gamma_state` / `market_gex_regime_score`, rendered "Market (SPY)". Same defect fixed in `mcmillan_advisory_layer._gex_bucket` (read SPY as the ticker's bucket). Tests `tests/test_ot5_no_spy_gamma_alias.py` (4). Live 8 Oct (`Enhancements/phase7/ot5_live_gex_bucket.json`): all 2,788 ticker rows carried SPY NEGATIVE_GAMMA / 0.3; 665 McMillan buckets move AMPLIFYING -> PINNING (their own chain score >= 60 had been overridden by SPY's 0.3). 65 related test files pass except the known stage-0 git-index check (new modules uncommitted).
- [x] 6. D5-5 IV labels: samples used, SHORT_HISTORY, rank vs percentile. Owner `scripts/avshunter_options_intelligence.resolve_iv_ownership`: source `IV_HISTORY` (was the fixed name IV_HISTORY_252D), `iv_history_state` FULL_WINDOW / SHORT_HISTORY / NOT_IV_HISTORY against config `iv_history.full_window_samples` 252, `iv_history_first_date`; carried to the book and Lab. Card row "IV percentile / rank" shows each with its definition and sample count; Lab IV title states samples and the state. Tests `tests/test_ot6_iv_labels.py` (7). Live 8 Oct (`Enhancements/phase7/ot6_live_iv_history.json`): all 2,139 rows labelled IV_HISTORY_252D were short history (20-107 samples, median 57); SMCI 66.
- [x] 7. D5-2 / D5-3 walls per expiry bucket (gamma-weighted, ±30%) and gamma-flip confidence - BUILT (data, display, readers) to the enhanced design `Enhancements/phase7/ITEM7_WALLS_DESIGN_20261010.md` (ACK's call-wall review: three separate conclusions; baskets TODAY / THROUGH_EXIT / AFTER_EXIT by actual dates; gamma x OI x multiplier, unsigned; zones, materiality, volatility relevance band replacing ±30%; observed price response; flip confidence state). Owner `domain/option_walls.py`, wired in the Options stage, carried to the book and card; legacy raw-OI walls moved to the card's legacy tier. Tests `tests/test_ot7_option_walls.py` (12) on the stored SMCI 8 Oct chain. Live 8 Oct (`ot7_live_walls.json`, 2,677 chains): 1,053 tickers had an old wall >30% from spot; SMCI $3 put -> $40-41 zones. Readers (ACK approved 10 Oct): `call_wall` / `put_wall` are now the hold-basket qualified zone peak at the producer (`domain.option_walls.governed_walls`), raw OI kept as `legacy_oi_*`; the exit-plan T1, the stop fallback and the SuperBrain runway vetoes use a wall as a price level only when price confirmed its role (`level_wall`); no confirmed wall = runway not limited (V3 fix). Replay 8 Oct (`ot7_readers_replay.json`, 2,280 directed rows): V2 no-runway warning removed 1,070 / added 114 / kept 300; V3 high-IV removed 114 / added 37; no STAND_DOWN changes. OPEN: thresholds initial (item 10); Morning recompute with its own spot later.
- [x] M-G2-01 Morning repricing of every contract; M-G3-01 parallel prefetch + progress; M-REVIEW-01 thesis authority at the Morning gate (ACK 10 Oct; `M_REVIEW_01_THESIS_AUTHORITY_DESIGN_20261010.md`).
- [x] 8. D6-1 per-ticker disposition journal for every surfaced idea. `domain/ticker_disposition.py` + table `ticker_dispositions` in the decision-outcome ledger (append-only, idempotent); written for every book row at EOD (orchestrator) and Morning (`morning_handoff_finalizer`). Frozen snapshot: setup, levels, contract or its stated absence, price and quote time, stated probabilities, value scenarios, decision and why, model versions. The book's thesis_id is a row key (unresolved rows are keyed `<T>:UNRESOLVED:<run>`) and is never presented as a thesis: thesis identity = a side and a governing thesis candidate. Skipped Morning validation events are now named. Tests `tests/test_ot8_ticker_disposition_journal.py` (5). Live 8 Oct (`ot8_live_dispositions.json`): 2,788 of 2,788 rows recorded (NAN kept as a ticker); 418 NO_THESIS:UNRESOLVED_DIRECTION; no contract: 418 no trade side, 96 candidates unvalued, 90 no verified chain, 2 no suitable option. Found: the ledger's sqlite connections are never closed (pre-existing pattern; new methods close theirs).
- [x] 9. D7-1 earnings confirmation tiers. `domain/earnings_confirmation.py` (VENDOR_ESTIMATE / CORROBORATED / ISSUER_CONFIRMED when supplied / SOURCES_DISAGREE - both shown, the earlier date carries the risk) + `canonical_data/tastytrade_earnings.py` (read-only bridge, 100 per call, per-symbol retry, session cache, missing credentials stated). Wired in the Evening earnings step; the Morning carries the reconciliation (it had been dropping the confirmation at one site). New fields earnings_disagreement / _sources_json / _confirmation_note. Tests `tests/test_ot9_earnings_confirmation.py` (8). Cross-check 10 Oct (`ot9_earnings_crosscheck_20261010.json`): 30 tickers, 26 agree, 4 disagree (MSFT, OI, TRS, VFC; tastytrade earlier in 3). Broker credentials are set in the user environment (names checked, not values). tastytrade also carries dividend yield and next ex-date (item 4 second step).
- [x] 10. C-1 / C-2 calibration definitions and station inspections, to `ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md`. 10.3 station inspections `domain/station_inspection.py` (config `station_inspection`; STOP checks raise and end the run, REPORT checks report): Discovery, Options, EOD, book and Morning; replay 8 Oct (`ot10_station_replay.json`) zero STOP defects at all five. 10.1 per-setup within-hold rates `domain/setup_calibration.py` -> `config/setup_rates_v1.json` (74 setups, 73,961 held-out outcomes; slope 0.96, intercept -0.03, ECE 0.021); 9 of 16 lane setups fall below 50% within the planned hold (e.g. 1d SOS 0.678 -> 0.58); shown on the card, lane / geometry NOT switched (ACK decision). 10.4 end-of-line verifier + five-section scorecard after the Evening and the Morning (`domain/run_scorecard.py`; 8 Oct: data FAIL from the known G2-06 handoff case, others REVIEW). 10.2 forward calibration `domain/forward_calibration.py`: setup labels travel to C12; only matured outcomes count; UNCALIBRATED_FORWARD until 100 resolved over 20 sessions; scorecard and card read it (receipt `ot10_forward_receipt.json`: 15 matured of 1,051). OPEN: C12 window = hold (62 of 78 setups hold beyond 20 sessions; after the Monday run). Tests ot10_* (12 + 5 + 3 + 8); regression 40 related files + 169 rebuild tests, 0 failures.
- [ ] 11. D2-1 Step B design (decision 3), then station by station. Design + replay approved (ACK D11-1..4, 10 Oct; `ITEM11_DISCOVERY_TIER_DESIGN_20261010.md`). [x] Station 1 Discovery BUILT: tier = thesis disposition (`domain/thesis_tier.py`, switch `config/discovery_thesis_tier_v1.json`), no legacy composite drop, order by setup rate, win probability = measured setup rate or null, horizon label from the evidence hold, quality gate = survivors + thesis GO; 8 Oct through the built code: 479 GO / 315 READY_NOT_GO / 1,644 WAITING / 495 NO_ACTIVE_THESIS. Open stations: Options OIS phase points + volume confirmation; trap engine; trigger T3; EOD classify_tier / SCS composite; Vanguard + EV3 keys labelled LEGACY_STATE_KEY.
- Regression after each item; replay acceptance on run 20261008_220129.
