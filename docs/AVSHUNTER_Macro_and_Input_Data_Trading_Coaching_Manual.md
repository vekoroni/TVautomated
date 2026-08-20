# AVSHUNTER Macro and Input Data Trading Coaching Manual

**Assessment date:** 15 August 2026  
**Folders reviewed:** `dropbox/macro` and `dropbox/inputs`, including their `Archive` subfolders  
**Scope:** File inventory, lineage, current contents, pipeline use, data-quality controls, and a practical decision-support workflow.

> This material explains how to use pipeline data as trading decision support. It does not turn a watchlist, narrative, or macro bias into execution permission. Capital may be committed only after the live price, options-liquidity, EV/RR, risk, and trigger controls agree.

## 1. Executive conclusion

The folder structure contains **15 files: 7 active files and 8 archived snapshots**.

The active decision hierarchy is:

1. `macro_intelligence_latest.json` is the canonical macro and portfolio-risk state.
2. `bond_macro_state.json` is the rates, curve, credit, and auction sidecar. It is merged into the macro JSON and also checked independently by the morning gate.
3. `avshunter_macro_enrichment_delta.json` adds narrative themes, ticker exposure, confirmation tests, and event guards. It is expressly prohibited from overriding protected macro gates.
4. `catalyst_calendar_clean_latest.csv` supplies ticker-level catalyst research to the morning thesis validator. It is a candidate/context file, not an execution list.
5. `catalyst_calendar_latest.csv` is the unsplit canonical catalyst intake. Its current parsed data is identical to the clean file.
6. `macro_session_context_latest.csv` is the splitter output for rows classified as `MACRO_SESSION_GUARD`. It is currently empty and has no confirmed production consumer.
7. `auction_calendar.csv` is a human/machine-readable derivative of the bond job. It currently represents “no qualifying auction rows” with a blank data row. The live pipeline obtains the same auction state from `bond_macro_state.json`, not from this CSV.

The present macro state is constructive but conditional: `TRANSITIONAL_BULLISH`, `MILDLY_BULLISH`, conviction `0.63`, `macro_filter=NO_GO`, global size multiplier `0.70`, and trigger confirmation required. The horizon router is more restrictive: `0.50` for 1–5 days, `0.55` for 6–10 days, and `0.49` for 11–20 days. Use the most restrictive applicable multiplier; do not multiply all of them together.

The catalyst set contains 12 names, split evenly between call-watch and put-watch directions. However, every row is `capital_grade=NO`, `execution_permission=NONE_NEWS_TERMINAL_ONLY`, and `needs_manual_confirmation=True`. Therefore **none of these rows is independently tradeable**.

## 2. Complete file inventory

### Active macro files

| File | Producer/source | What it contains | Confirmed pipeline use | Trading use | Current assessment |
|---|---|---|---|---|---|
| `macro_intelligence_latest.json` | Built by `build_macro_json.py`, normalized by `scripts/normalise_macro_contract.py`, then augmented by the orchestrator. Builder metadata lists market report, macro, forward-bias, liquidity, regime, VIX, FRED, GEX, global index, sector, FX, bond, commodity, and ETF inputs. | Canonical regime, direction, conviction, volatility, liquidity, rates, GEX, sector rotation, horizon routing, sizing, notes, and merged extras. | Required orchestrator preflight; discovery thresholds; regime screener; GARCH regime; horizon router; VIX governor; ML confidence; morning thesis validator; morning gate; package/export tooling. | Sets risk posture, allowed horizon, sector alignment, trigger requirement, and size ceiling. It does not choose a contract or authorize an entry. | Internally as-of `2026-08-14T08:55:36Z`; validation marked PASS. One source file, `us_indices_cash_*.csv`, was missing at build time. Suitable for the closed 14 August session; refresh before the next live session. |
| `avshunter_macro_enrichment_delta.json` | External/GPT news-terminal process, based on a market brief and linked sources. Contract `macro_enrichment_delta_v1_2`. | Narrative overlay, six themes, six event guards, ticker exposure catalogue, confirmation/invalidation tests, source gaps, and risk overlay. | Augment-only merge into macro latest; morning thesis validator; morning gate ticker-bias lookup; ticker probe; signal grader; macro exposure resolver. | Generates hypotheses and explicit confirmation/invalidation tests. Use to explain *why* a ticker may react and what must be observed before entry. | As-of `2026-08-14T09:23:00Z`; AMBER/high-risk overlay; execution permission is explicitly none. Cannot override filter, size, trigger, horizon, put gate, or sector lead/avoid fields. |
| `bond_macro_state.json` | `bond_macro_intelligence.py`; TreasuryDirect auction schedule, FRED yields, Polygon IEF proxy and HYG/LQD prices. | Auction window, 2Y/10Y/30Y curve, IEF/ZN proxy, credit stress, composite score, trade gate, warnings, and breakeven adjustment. | Merged under macro extras by orchestrator; read independently by morning gate CHECK 4; displayed by desk card; normalized by bond contract adapter. | Controls rates/credit caution, auction-event risk, and whether the morning gate may proceed. Useful for duration, rate-sensitive sectors, and risk sizing—not ticker direction by itself. | Generated 14 August; score 65/100; `trade_go=true`; credit normal; curve flat; FRED observations as-of 12 August and flagged stale; IEF used instead of a true ZN continuous contract. Refresh before a live morning gate. |
| `auction_calendar.csv` | Written by `bond_macro_intelligence.py` from the bond JSON’s `auction.calendar_rows`. | `date`, `tenor`, `type`, and offering size for qualifying coupon auctions. | No active direct runtime consumer was found in this repository. The current pipeline consumes auction fields embedded in `bond_macro_state.json`. | Use as a desk-readable schedule only. Ahead of a long-end auction, demand stronger confirmation and consider wider breakeven/risk buffers if the bond state sets a spread-risk adjustment. | Header plus one all-null row because no qualifying auction was returned within the configured window. Treat as **zero events**, not as a valid event record. Do not parse the blank row as an auction. |

### Active input files

| File | Producer/source | What it contains | Confirmed pipeline use | Trading use | Current assessment |
|---|---|---|---|---|---|
| `catalyst_calendar_latest.csv` | Manual/external news-terminal intake using linked Reuters/Barron’s sources and chat-brief context. | Canonical 22-column catalyst intake: ticker, event type/status/date, direction watch, confidence, route, risks, missing data, and permissions. | Read by `catalyst_truth_engine.py`, morning thesis validator fallback, external-intelligence review lane, and audit/capture tools. Split by `scripts/split_catalyst_from_macro_guards.py`. | Adds ticker-specific event context. Use the route to decide whether a row enters the full pipeline, discovery only, or catalyst only. Never treat direction-watch as a trade instruction. | 12 unique rows, no duplicates, all dated 14 August. All require manual confirmation and prohibit direct execution. All `event_window_end` values are missing; all have only one counted source. |
| `catalyst_calendar_clean_latest.csv` | Produced by `scripts/split_catalyst_from_macro_guards.py` by removing only rows whose type is exactly `MACRO_SESSION_GUARD`. | Ticker catalyst rows intended for validator consumption without macro-session pseudo-catalysts. | Preferred automatically by `morning_thesis_validator.py` whenever it exists. | This is the **operational catalyst input** for thesis validation. Join by normalized ticker; use its direction, failure risk, and missing-data fields as tests, not votes. | 12 rows and parsed-data-identical to `catalyst_calendar_latest.csv`; the byte hashes differ only because of serialization/encoding details. No macro guard rows were present. |
| `macro_session_context_latest.csv` | Produced by the same split script from `MACRO_SESSION_GUARD` rows. | Macro-session context intentionally separated from ticker catalysts. | No active production consumer was found; referenced by redesign tests only. | Do not use for trading until a governed consumer and schema contract exist. Macro session state should currently come from `macro_intelligence_latest.json`. | Schema-only, zero data rows. This is expected given the current source contained no `MACRO_SESSION_GUARD` records, but it provides no usable signal. |

### Archived macro snapshots — research/audit only

| File | Snapshot date | Contents and purpose | Trading rule |
|---|---:|---|---|
| `Archive/avshunter_macro_enrichment_delta0408old.json` | 31 Jul 2026 | Six-theme/six-guard AMBER snapshot: AI/semiconductor relief, yen-intervention and long-end-rates context. | Historical audit and scenario study only. Never load as current macro context. |
| `Archive/avshunter_macro_enrichment_deltaolod0808.json` | 4 Aug 2026 | AMBER snapshot: earnings, AI, oil rebound, yen, rates and credit guards. | Historical audit only. |
| `Archive/avshunter_macro_enrichment_delta1008old.json` | 8 Aug 2026 | AMBER snapshot: weak payrolls, rate relief, USD weakness, technology leadership, CPI and credit guards. | Historical audit only. |
| `Archive/avshunter_macro_enrichment_deltaold1408.json` | 10 Aug 2026 | AMBER snapshot: Hormuz/oil, rates rotation, weak breadth, semiconductors, duration and CPI guards. | Historical audit only. |

### Archived input snapshots — research/audit only

| File | Shape/date | Contents and purpose | Trading rule |
|---|---|---|---|
| `Archive/catalyst_calendar_latest old 0408.csv` | 12 rows × 135 columns; catalysts dated 31 Jul | Earlier wide research schema combining catalyst, M&A, narrative, scoring and pipeline fields; 52 columns are completely empty. | Useful for lineage/schema research only. It must not be concatenated with the current 22-column contract without an explicit migration. |
| `Archive/catalyst_calendar_latestold0808.csv` | 12 × 62; dated 4 Aug | Earlier enriched catalyst/narrative snapshot for SPY, QQQ, IWM, AMD, NVDA, XOM, DAL, JPM, PLD, ETN, HYG and VXX. | Historical review only. All rows also prohibited direct execution. |
| `Archive/catalyst_calendar_latestd140old1408.csv` | 15 × 62; mostly dated 7 Aug | Earlier enriched snapshot including index, technology, finance, real estate, energy and event names. | Historical review only. Do not allow the misleading filename to override internal dates. |
| `Archive/global_indices_20260809_110744.csv` | 5 × 15; observations dated 6 Aug | YFinance global-index snapshot for GDAXI, FTSE, N225, HSI and FCHI, with daily/weekly/monthly/YTD performance. | Context/backtest only. It is stale and is not an active input in the reviewed folders. |

## 3. What the active files currently say

### Macro state

- Regime: `TRANSITIONAL_BULLISH`; directional bias: `MILDLY_BULLISH`.
- Conviction: `0.63`, below the stated `0.70` confirmation threshold.
- Macro filter: `NO_GO`, described in the notes as a Fung-Hsieh sizing modifier rather than a universal ticker block.
- Trigger: required.
- VIX: `14.63`, described as extremely compressed; volatility mode is front-end event premium.
- GEX: available and positive; the notes cite SPY net GEX of approximately +$12.16bn and pinning conditions.
- Liquidity: stable but mixed; credit benign.
- Sector leads: XLE, XLK, XLV, XLI and XLF.
- Sector avoids: XLU, XLRE and XLC.
- Horizon posture:

| Horizon | Bias | Probability | Action | Size ceiling | Interpretation |
|---|---:|---:|---|---:|---|
| 1–5D | Bullish | 69.0% | Long bias with trigger | 0.50 | Best alignment, but requires live confirmation; positive gamma may favor controlled/pinned movement rather than unlimited upside. |
| 6–10D | Bullish | 65.1% | Long bias with trigger | 0.55 | Constructive cross-asset trend; event and rates changes can invalidate it. |
| 11–20D | Mildly bullish | 57.0% | Reduced-size selective | 0.49 | Lower edge and greater macro-change risk; use only the strongest setups. |

The horizon probabilities are tagged `NARRATIVE_UNVERIFIED`. They are priors for routing and sizing, not standalone statistical forecasts to trade blindly.

### Bond and rates state

- Composite: 65/100, `BOND_MACRO_OK`, `trade_go=true`.
- Curve: 2Y 4.20%, 10Y 4.68%, 2s10s +48 bps; classified FLAT.
- 30Y: 5.24%; 10s30s +56 bps.
- Curve motion: one-day bull flattening but five-day bear steepening.
- Bond proxy: IEF above SMA5 and SMA20, labelled bullish/mild easing.
- Credit: HYG/LQD stress NORMAL, no warning or alert.
- Contradiction: the engine labels mild easing while the 10Y rose over five days. Treat this as a reason to reduce confidence, not to choose one label opportunistically.
- Freshness: FRED curve data is explicitly stale by two sessions. Refresh before using CHECK 4 for live capital.

### Catalyst state

| Ticker | Watch direction | Catalyst | Confidence | Route | Key confirmation/invalidation idea |
|---|---|---|---|---|---|
| AMAT | Put watch | Guidance/tape divergence | Medium | Full pipeline | Needs downside follow-through, weak semiconductor relative strength and viable options; invalid if the gap recovers and peers confirm strength. |
| COP | Call watch | Hormuz/oil supply risk | High | Full pipeline | Needs crude and energy relative-strength confirmation; invalidated by de-escalation or crude reversal. |
| CSCO | Put watch | Earnings margin pressure | Medium | Full pipeline | Needs official detail, persistent weak tape and options liquidity; invalid if margins are treated as temporary and price recovers. |
| CVX | Call watch | Hormuz/oil supply risk | High | Full pipeline | Same crude/energy confirmation; geopolitical premium can unwind rapidly. |
| DAL | Put watch | Oil/fuel-cost pressure | Medium | Discovery only | Needs fuel pressure and airline weakness; hedging, pricing power or crude reversal can invalidate it. |
| MU | Call watch | AI/technology leadership | Medium | Full pipeline | Needs semiconductor leadership and stable long yields; invalid if yields accelerate or semis lose leadership. |
| NVDA | Call watch | AI/technology leadership | Medium | Full pipeline | Same leadership/rates test; avoid paying event premium without EV. |
| TPR | Put watch | Guidance cut | Medium | Full pipeline | Needs persistent downside and revision pressure; invalid if the gap fully reverses or the news is fully priced. |
| UAL | Put watch | Oil/fuel-cost pressure | Medium | Discovery only | Same airline/fuel confirmation; discovery route is not execution eligibility. |
| WEN | Call watch | Takeover rumour | Medium | Full pipeline | Only binary-score-positive row, but still needs bid/filing, financing, second source, tape and options confirmation; rumour denial is hard invalidation. |
| XLRE | Put watch | High long-end yields | High | Catalyst only | Needs yields to remain elevated and XLRE weakness; falling yields can create a fast reversal. |
| XOM | Call watch | Hormuz/oil supply risk | High | Full pipeline | Needs sustained crude premium and XLE leadership; de-escalation/crude reversal invalidates it. |

## 4. How to use the data efficiently

### The correct decision sequence

Use the data as a narrowing funnel. Each layer must answer a different question:

1. **Freshness:** Is each required state current for the intended session? Use internal `as_of_utc`/`generated_at` values, not file modification time.
2. **Portfolio permission:** What risk regime, size cap, and trigger requirement does the canonical macro file impose?
3. **Horizon:** Which holding period is supported? Use the matching horizon route and ceiling.
4. **Sector alignment:** Is the ticker in a lead, neutral, or avoid sector? This changes selectivity; it does not manufacture an entry.
5. **Catalyst quality:** Is the event confirmed, time-bounded, multi-sourced, and not fully priced? What evidence would invalidate it?
6. **Live confirmation:** Does price/volume, relative strength, breadth, crude/rates/credit, and options flow confirm the thesis after the relevant market opens?
7. **Monetisation:** Is the proposed option liquid, correctly priced, and positive-EV after spread, slippage, fees, probability, and payoff? Is reward/risk above the production floor?
8. **Execution gate:** Are EV eligibility, trigger, morning gate, risk limits, and contract-normalization checks all passed? If any mandatory gate fails, the verdict is no trade.

### Source-of-truth rules

- For macro state, use only `macro_intelligence_latest.json`.
- For catalyst validation, use `catalyst_calendar_clean_latest.csv`; retain `catalyst_calendar_latest.csv` as the intake/audit copy.
- For bond gating, use `bond_macro_state.json`. Treat `auction_calendar.csv` as a convenience view.
- Use the enrichment delta for explanation, exposure mapping, and confirmation tests. Never use it to relax macro restrictions.
- Never combine archived and active files in a live run.
- Do not double-count evidence. The macro latest file already incorporates or references liquidity, FRED, VIX, GEX, the enrichment delta, and bond extras. Repeating each as an independent bullish vote inflates conviction.

### Size rule

Select the **lowest applicable authorized ceiling** among portfolio, horizon, event, liquidity, EV, and risk controls. For example, the current global cap is 0.70 while the 1–5D route caps size at 0.50; the working maximum is therefore 0.50 before any ticker/contract risk reduction. Do not multiply 0.70 × 0.50 unless the sizing contract explicitly instructs that calculation.

### Direction-conflict rule

When layers disagree, classify the conflict instead of averaging it away:

- **Macro bullish, catalyst bearish:** a tactical short/put may still exist, but demand stronger ticker-relative weakness, lower size, and a clear invalidation.
- **Macro bearish/cautious, catalyst bullish:** require exceptional relative strength and a catalyst capable of overcoming the regime.
- **Sector tailwind, ticker tape failure:** the price signal wins; no entry until confirmation returns.
- **Narrative bullish, EV weak/avoid or RR zero:** no trade. Narrative cannot repair bad economics.
- **Bond/rates contradiction:** reduce confidence or wait for resolution; do not select whichever label supports the desired trade.

## 5. Coaching playbook

### Evening preparation

1. Run/build the macro state and inspect its validation metadata.
2. Run bond intelligence and confirm its internal data dates, not merely that the file was written.
3. Prepare the catalyst intake, run the splitter, and confirm `clean_rows + guard_rows = original_rows`.
4. Check for duplicate tickers/events, missing event dates/windows, source count, and execution permissions.
5. Build a *conditional* watchlist with three statements per ticker:
   - Why the trade could work.
   - What must confirm in the live session.
   - What invalidates it immediately.
6. Do not promote any row to GO during preparation unless its downstream option/EV and execution gates have already been run on valid market data.

### Morning refresh

1. Refresh macro and bond data before the gate. The current bond file would exceed the gate’s 26-hour maximum age by the next normal live session.
2. Confirm macro timestamp, regime, conviction, filter, size cap, trigger, VIX, GEX availability, sector lists and intended horizon.
3. Confirm bond `trade_go`, curve/credit warnings, auction window, and any breakeven adjustment.
4. Re-check time-sensitive catalyst facts, especially rumours, oil/geopolitics, earnings reactions, and yields.
5. Run the morning gate. A graceful “skipped” bond or macro check is degraded data, not positive confirmation.

### Entry decision

For each candidate, use this spoken checklist:

> “The source is current. The macro regime permits this horizon and size. The sector and ticker tape confirm the direction. The catalyst is still active and not already priced. The option is liquid. EV is positive, reward/risk clears the floor, and the trigger has fired. The invalidation and maximum loss are defined.”

If any sentence is false or unknown, wait or reject the trade.

### Position management

- Monitor the exact invalidation conditions in the catalyst and enrichment files, not only the option P&L.
- Reassess when VIX exceeds the relevant horizon block level, GEX flips negative, credit weakens, crude reverses, yields break the thesis, or sector leadership changes.
- Do not convert a failed event trade into a longer-horizon macro trade without a new thesis and fresh authorization.
- Record which data fields authorized the trade and which condition closed it. This makes post-trade attribution and pipeline improvement possible.

### Post-trade review

Grade separately:

- **Data quality:** Were timestamps, sources and fields valid?
- **Thesis quality:** Was the macro/catalyst reasoning correct?
- **Monetisation quality:** Was the option and EV model correct even if direction was right?
- **Execution quality:** Was the trigger obeyed and slippage controlled?
- **Risk quality:** Was position size within the strictest ceiling and was invalidation honored?

A profitable trade can still be a process failure, and a correctly controlled loss can still be a good process outcome.

## 6. Mandatory pre-trade checklist

- [ ] Active files only; no `Archive` file entered the run.
- [ ] Macro internal timestamp is appropriate for the session.
- [ ] Macro contract validation passed; required fields are present.
- [ ] Bond file is younger than the gate threshold and its underlying observations are not materially stale.
- [ ] Auction blank-row representation has not been mistaken for an event.
- [ ] Catalyst date and event window are valid; an absent `event_window_end` has been handled conservatively.
- [ ] At least one independent source has been manually verified; rumours require stronger confirmation.
- [ ] Catalyst route permits full analysis; `DISCOVERY_ONLY` and `CATALYST_ONLY` are not treated as execution routes.
- [ ] `execution_permission`, `capital_grade`, and `needs_manual_confirmation` have been honored.
- [ ] Price, volume, relative strength and relevant cross-asset confirmation agree.
- [ ] Option quote is live; bid/ask, open interest, volume, IV and Greeks pass contract filters.
- [ ] EV is positive and eligible; reward/risk is non-zero and above the production threshold.
- [ ] Trigger fired; stop/invalidation and maximum loss are defined.
- [ ] Final size is no greater than the strictest applicable cap.

## 7. Current gaps and controls to improve

These are data/governance gaps found during the review; they do not require changing the pipeline interpreter.

1. **Auction CSV representation:** zero events are written as an all-null row. Prefer a header-only CSV plus an explicit `row_count=0` in a manifest, or ensure every consumer drops all-null rows.
2. **Bond observation freshness:** the file can be newly generated while FRED observations remain stale. Gate both generated age and underlying `as_of_date`/`stale_flag`.
3. **Catalyst event windows:** every active `event_window_end` is missing. Define expiry rules by catalyst type so stale narratives cannot persist indefinitely.
4. **Catalyst sourcing:** every active row has `source_count=1`; several rows claim combined brief/Reuters context but still count one source. Standardize how independent sources are counted.
5. **Candidate versus permission:** all catalyst rows explicitly prohibit execution. Keep that field visible through downstream outputs so a watch direction cannot be mistaken for GO.
6. **Macro-session context:** the file has no production consumer. Either govern and integrate it later or keep it explicitly informational; do not let it become a second macro source of truth.
7. **Schema history:** archived catalyst files use 22-, 62-, and 135-column shapes. Add a schema/version manifest before using archives for model training or regression comparisons.
8. **Missing macro builder input:** the current builder metadata reports `us_indices_cash_*.csv` missing. Although validation passed, it should be restored or explicitly waived with a documented degradation flag.
9. **Narrative probabilities:** horizon biases are marked `NARRATIVE_UNVERIFIED`. Keep them as routing priors until their calibration and out-of-sample performance are measured.

## 8. One-page desk card

**Macro tells you how much risk and which horizon—not which option to buy.**  
**Bond tells you whether rates, supply and credit make that risk safer or more fragile.**  
**Enrichment tells you the story, exposed tickers, and what must confirm—not permission.**  
**Catalyst tells you why a ticker is on the research list—not whether its option is monetisable.**  
**Live market, EV/RR, trigger and risk gates determine whether a trade exists.**

Current posture: transitional bullish, modest conviction, reduced size, trigger required. Favor selective aligned setups; reject any name with weak/avoid EV, zero RR, poor liquidity, an unconfirmed catalyst, or a failed trigger—regardless of how attractive the narrative appears.
