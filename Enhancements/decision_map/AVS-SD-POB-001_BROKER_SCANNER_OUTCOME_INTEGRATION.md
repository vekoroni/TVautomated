# AVS-SD-POB-001 — Broker evidence, focused scanner intake and realised outcomes

Status: **IMPLEMENTATION IN PROGRESS — scanner evidence-truth slice tested offline; broker/focused-run authority not released**  
Date: 2026-09-21  
Scope: read-only tastytrade evidence, focused ticker intake, and C12 realised-fill reconciliation.  
Governing: `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` v1.1, especially C2, C11–C13 and §§15–17, 24; method notes 05–07; root `CLAUDE.md`.

## 1. Decision and business purpose

**Approve the intent with changes.** The working Claude–tastytrade MCP can improve exact-contract verification and actual outcome measurement. It must not become a second trading decision system. Broker watchlists or user-supplied tickers may enter a *focused* AVSHUNTER run without scanning the full universe, but they still require the same per-ticker evidence, thesis, expression and validation rules before the Lab calls them opportunities. Existing positions and orders enter a separate monitoring/reconciliation path; they are not fresh recommendations merely because a broker holds them.

The C12 objective is to distinguish (a) what AVSHUNTER predicted for every candidate and expression, (b) what a presented but untraded ticket would have done, and (c) what the human actually traded, at broker-confirmed prices and quantities. Neither the ledger nor broker account balances may grant capital permission, change direction, or rank new trades.

## 2. As-is findings and corrections to the supplied draft

| Supplied proposal | Code-checked disposition |
|---|---|
| Claude MCP read tools expose positions, balances, orders and transactions | **Local connection verified 2026-09-21:** Claude Desktop's packaged `claude_desktop_config.json` registers `tastytrade` as `node C:\Users\ACKVerissimo\tastytrade-mcp\dist\index.js`, with `TASTYTRADE_ENV=production` and `TASTYTRADE_READ_ONLY=1`. The script exists and its local metadata defines the expected read tools. This proves the local configuration and tool contract, **not** an end-to-end broker call or the content of Claude's response. The repository still has no active tastytrade production adapter; `bridge/tastytrade_client.py` is a non-trading placeholder. No credential values were inspected or copied. |
| Real fills have no ledger path | Too broad. `canonical_data.decision_outcome_ledger.fill_record_v1` already creates `FILL_RECORDED`; `outcome_event_from_trade` already handles realised trade exits; `avshunter_trade_journal.log_exit` can write such an `OUTCOME`. The missing piece is automated broker ingestion, exact reconciliation, entry linkage and completeness, not a new ledger. The current fill event identity and causal transitions are **not yet sufficient** for repeated/partial fills. |
| Add `LIVE_FILL` as a new `decision_stage` and a fill-side `PRESENTATION_DECISION` | Reject. A fill is an observation, not a presentation decision. Use the existing `FILL_RECORDED` event for each verified execution and `OUTCOME` only when a position or lot has actually closed. Keep `is_counterfactual=false` and a broker source on realised outcomes. |
| Record every unmatched fill in the ledger with `thesis_id=None` | Not implementable as stated: `LedgerEvent` requires non-empty `run_id`, `ticker` and `thesis_id`, and causal links must preserve the thesis. Do not fabricate a thesis ID. Capture unmatched broker records in a governed, immutable reconciliation-exception artefact and surface them for manual linkage. A later, separately approved ledger-invariant extension could admit broker-origin events without a thesis. |
| Match by contract and nearest prior presentation | Display-only suggestion. Repeated presentations, partial fills and discretionary trades make this ambiguous. Human-confirmed presentation/expression linkage is required before a fill is labelled pipeline-attributed. |
| Ingest only closed positions | Incomplete. Import each execution/fill once, then derive closed-lot outcomes from matched opening and closing fills, commissions and contract multiplier. Open positions remain open observations, not wins or losses. Orders that are live, rejected, cancelled or expired are not fills. |
| Current Stage 9 is already a realised-fill monitor | Incorrect. `outcome_capture.py` may classify an exit from a current market mark and invoke `avshunter_trade_journal.log_exit` without a broker closing fill. That is an inferred policy/mark event, **not** broker-confirmed realisation. It must not be pooled with broker-confirmed P&L or silently close a broker-linked trade. |
| Use balances for pipeline decisions | Reject. Account balances are operational reconciliation only. AVSHUNTER remains capital-agnostic; no buying-power or size feedback into the opportunity book. |

The current universe scanner (`scripts/avshunter_universe_scanner.py`) already publishes a manifest. `intelligent_orchestrator.py` Phase 0 injects scanner-discovered tickers into Discovery and passes scanner context downstream. It does **not** publish a complete governed thesis by itself. Its legacy IV proxy and hard contract filters also mean a broker-fed scanner score must not inherit decision authority.

### Scanner evidence-truth remediation — implemented, not yet live-accepted

The stored 20 September scanner output contained 224 rows: 33 VMS `GO`, 84 VMS `PROBE`, all 224 without a usable options-volume history baseline or short-data observation, and 222 labelled LSS `LEAD_BLOCK`/`EXCLUDED`. This is an **old-output defect measurement**, not a count of trades recovered by the new code. The legacy scanner called a chain-level call/put **volume ratio** a `CALL_SWEEP`/`PUT_SWEEP` and awarded a 15-point component bonus, despite having no trade-print or aggressor-side evidence. It also inserted a neutral 25 short-data component when short data was absent, allowed a weighted low score to exclude a ticker, and labelled an option-price/volume proxy `DARK_POOL_PROXY` without dark-pool prints.

The first TDD/DDD slice now separates these concepts:

| Domain fact | Implemented rule | Authority |
|---|---|---|
| Call/put chain-volume concentration | `volume_concentration_side=CALL/PUT/BALANCED/NO_VOLUME`; retain numeric ratio where defined; `sweep_flag=NO_TRADE_PRINT_DATA` | Context only; never buyer-initiated flow or a sweep |
| Missing volume baseline, short or sector evidence | Record `lss_missing_evidence`; missing short component remains null in output; `LEAD_INCOMPLETE` routes to `WATCHLIST_ONLY` | Cannot exclude a ticker or create a `GO` |
| Complete but weak LSS | Remains `LEAD_WATCH`/`WATCHLIST_ONLY`, retaining its numeric score | Review priority, not thesis validity |
| Option premium/volume and underlying gap proxy | `OPTION_ACTIVITY_PROXY` label; keep legacy field names only for compatible transport | No dark-pool or institutional-buying claim |
| Scanner-to-orchestrator handoff | Preserve the VMS `GO`/`PROBE` lists, manifest ticker identity, LSS missing-evidence string, concentration side, ratio and no-trade-print flag | No direct trade or capital permission |

Implementation: `domain/scanner_evidence.py`, `scripts/avshunter_universe_scanner.py`, the Phase 0 scanner-context handoff in `intelligent_orchestrator.py`, and `tests/test_scanner_evidence_truth.py`. The standalone scanner entry point and adjacent pretrade/DDD tests passed **26/26** offline. No live scanner rerun, completed-session pipeline acceptance, broker quote comparison, or profitability claim has been made. Existing run artefacts must not be silently relabelled; this change applies to newly generated output only.

### Verified MCP boundary and pipeline handoff

The active Claude Desktop configuration is outside the repository at `C:\Users\ACKVerissimo\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`. Its local server is `C:\Users\ACKVerissimo\tastytrade-mcp\dist\index.js` (`@tastytrade/mcp-server` 1.0.0). Do not import Claude chat text into the pipeline and do not make the pipeline read this Claude configuration: it contains sensitive OAuth material and is a user-app configuration, not a governed AVSHUNTER contract.

The preferred production bridge is a **deterministic AVSHUNTER MCP client** that launches the same server binary over stdio, forces production read-only mode, supplies credentials from an approved secret mechanism, and allow-lists only the read tools this design needs. Discovery of the server path and tool schemas is separate from authorising live account access. The first test can use redacted responses already obtained through Claude; production integration later calls the local server directly so pipeline correctness does not depend on an LLM prompt or an open Claude window.

The local tool metadata identifies `tastytrade_get_quote` (1–100 symbols of one instrument type, bid/ask and `updated-at`, decimal strings; unresolved symbols are omitted), `tastytrade_get_option_chain` (instrument definitions, not live quotes), `tastytrade_get_positions` (current holdings/marks), `tastytrade_get_live_orders` (today's orders of **all** statuses, not merely working orders), and `tastytrade_get_transactions` (paginated executions and non-trade transactions; default page is not a complete history). Tool responses must be validated and normalised before AVSHUNTER uses them; the broker's quote timestamp must not be replaced by the fetch timestamp. No `get_balances` result enters opportunity selection or sizing.

## 3. Bounded contexts and routes

```text
Claude/tastytrade read-only MCP ──► broker observation adapter ─┬─► exact-contract quote comparison
                                                               ├─► focused ticker intake
                                                               └─► fill/order reconciliation

focused ticker intake ─► existing Discovery/Vanguard/Options/thesis/valuation path ─► Lab
exact-contract comparison ─► Lab/Interpreter advisory observation ─► human execution
fill/order reconciliation ─► existing C11/C12 ledger and exception review ─► C13 validation
```

### Route A — focused candidate assessment, not whole-universe scanning

Accept an explicit list from broker watchlist, user request or broker-held underlying as **ticker intake only**. Deduplicate against the current universe and stamp `source=BROKER_FOCUSED_INTAKE`, source record ID, timestamp and run ID. The orchestrator may process only those tickers, avoiding a 1,500+ ticker broad sweep, but must invoke the **same production per-ticker stages and policies** as an ordinary run. Do not use the existing `--universe` test override as a production shortcut without a governed focused-run contract and parity tests. No broker field alone may yield `GO`, `MONETISABLE` or a preferred contract.

This is a **cost/latency shortcut over the universe**, not a shortcut over thesis formation. A ticker that cannot complete the stage chain remains `NOT_ASSESSED`/`DATA_INSUFFICIENT` with reason and evidence, visible for manual review. The broad scanner and ordinary Evening run remain available; focused intake must not silently replace them.

The scanner fix above is **not** the focused-run implementation. `scripts/avshunter_universe_scanner.py --tickers` can limit *scanner intake*, but it does not execute Discovery, Vanguard, Options, governed thesis or valuation for those tickers. `intelligent_orchestrator.py --universe` is presently labelled a test/research override and must not be renamed a production route without population-accounting and full-versus-focused parity tests. Likewise, Phantom history can supply point-in-time option context but cannot replace the selected contract's current broker quote or the governed per-ticker stages.

### Route B — broker execution-time observation

For the Lab's exact selected share or OCC option symbol, read quote and instrument/tradability metadata after the Evening thesis exists. Normalise the broker symbol through `canonical_data.option_identity`; reject ambiguous expiry, strike, side, multiplier or adjusted root. Preserve broker `as_of`/exchange timestamp separately from fetch time. Show bid/ask/size, quote state and a side-by-side delta from AVSHUNTER's MarketData quote. Never blend quotes or rewrite the frozen Evening thesis. A missing/poor broker quote blocks a *claim of current executability*, not the underlying 1–20-session thesis; it can be rechecked later.

The option-chain instrument endpoint is not a current price feed; quote or streaming tools must provide price. Trade prints, OI and put/call ratios are contextual activity, not proven buyer-initiated money flow or Level 2 depth. Account/position/order data never reaches candidate direction, score or capital allocation.

### Route C — broker-confirmed fills and outcomes

Import read-only orders/transactions with broker order ID, execution/fill ID, side, symbol, fill UTC time, price, quantity, fees and status. Deduplicate by a stable provider fill identity; persist source digest and retrieval time. A position snapshot can reconcile quantity but cannot reconstruct cost basis or identify an individual fill on its own. Support partial fills, multiple lots, close/reopen, equity and options multiplier, exercise/assignment, cancellation/correction and fees; flag unsupported instruments and unexpected option strategies rather than dropping them.

For an explicitly linked pipeline trade, append `FILL_RECORDED` from the existing presentation event where the causal transition permits it. **First extend and test its identity and causal chain**: today's identity uses OCC symbol, fill timestamp and side but omits provider execution ID and order ID, while `FILL_RECORDED` cannot currently follow `FILL_RECORDED`. Repeated/partial fills could collide or fail linkage. Use stable broker execution identity, one event per execution, explicit correction handling and a tested path for multiple entry/exit fills under one presented trade. Continue existing `TRADE_ENTRY` and journal/outcome paths instead of making a second outcome store. Close a lot only on broker-confirmed offsetting execution or a reconciled exercise/expiry event; append a separate realised `OUTCOME` with `is_counterfactual=false`, broker-source IDs and actual economics. Do not alter counterfactual outcomes. A real trade with no confirmed thesis link remains an **unattributed broker exception**, not a fabricated pipeline win/loss. Suggested matches are shown to ACK for confirmation; never train or calibrate from unconfirmed matches.

Before enabling broker-linked outcomes, separate Stage 9's `MARK_INFERRED_EXIT`/policy alert from `BROKER_CONFIRMED_EXIT`. `outcome_capture.py` currently derives an exit from a mark and can write `log_exit`; this must not close a broker-linked live position or set `is_counterfactual=false` without a matching closing execution. Preserve the mark as an observation/alert, and reconcile the journal's existing claimed exits against broker history rather than assuming all journal exits were filled.

## 4. Evidence and authority contract

- MCP server must be explicitly read-only; never expose place/edit/cancel-order or other write tools to this workflow. Production is the vendor's default endpoint, so verify the active endpoint and `TASTYTRADE_READ_ONLY=1` in the *actual* Claude client configuration without logging secrets.
- All broker observations are timestamped, source-labelled, immutable for a run and replayable from a redacted fixture. Record unavailable/late/contradictory data as a state, not zero or neutral.
- Freeze Evening and Morning decisions before later broker evidence or realised outcomes are attached. No hindsight may enter a prior candidate score. C12/C13 may use realised outcomes for *future* validation only after G1–G4 approval.
- Do not export balances, account identifiers or credentials into the Lab, Worker 3, model prompts, run CSVs or audit logs. Mask account linkage and retain only the minimal fields required for fill reconciliation.
- The broker adapter must be optional and isolated: MCP outage cannot abort the core Evening run or turn an unknown quote into a `GO`.
- Keep cash-account and long-call/long-put/share trading mandate explicit. Unexpected spreads, short-option, margin or assignment records become review exceptions; their existence must not be silently ignored.

## 5. Tests and acceptance

1. Characterise the current Phase 0 scanner handoff, per-ticker run path, `fill_record_v1`, journal exit path and counterfactual C12 outcomes before changing them.
2. Contract tests against redacted actual MCP payloads for shares, standard and adjusted OCC options, missing timestamps, closed market, quote disagreement and MCP outage. No live order tool call in tests.
3. Focused-run parity: the same ticker and frozen evidence produce the same governed thesis/contract/economics as the ordinary run; only universe scope and runtime differ. Verify no new `GO` from broker position or scanner score alone.
4. Reconciliation replay: multi-day presentations, partial fills, repeated contract, discretionary trade, multiple lots, order without fill, fees, expiry/exercise, duplicate polling, correction and unsupported strategy. Include a mark-only Stage 9 exit with no broker closing fill. Require zero invented thesis matches, zero duplicate fill events, no mark-only event counted as realised and complete exception counts.
5. Compare confirmed broker exits with journal/C12 realised outcomes and counterfactual marks without replacing either. Reconcile quantity and P&L exactly within a declared currency/fee tolerance.
6. Shadow the integration read-only over a representative live period. Report quote coverage/latency, focused-run parity, match precision, unattributed rate and manual-review burden. Only then consider C13 calibration; no automatic trading authority follows from this design.
7. Scanner evidence regression: a 6:1 call/put **volume** ratio must not create a sweep; zero-call volume has a defined ratio of 0 while zero-put volume leaves the ratio undefined; missing volume baseline and short data must not exclude a VMS `GO`; a complete low-score ticker stays visible; manifest and Phase 0 context must agree on route source and missing evidence; standalone script invocation must import the domain contract. These are now covered by first-party tests and must remain in the release suite.

## 6. Proposed build order and gates

| Slice | Output | Gate |
|---|---|---|
| 0A. Scanner evidence truth — built offline | Stop false sweep/dark-pool claims and missing-data exclusion; retain evidence in manifest and Phase 0 context | **26/26 focused/adjacent tests passed**; still require fresh scanner and completed-session artefact reconciliation |
| 0B. Broker discovery | Local server path/config and read-only setting verified; still capture redacted *actual* MCP quote/transaction payloads and relevant trading-history shapes; inventory existing ledger and scanner tests | Confirm runtime broker response and privacy without copying Claude OAuth values |
| 1. Broker observation contract — pure adapter built offline | Deterministic exact-symbol normalisation, provider/fetch timestamp separation, bid/ask/size quality, explicit multiplier verification and advisory-only result | Contract tests passed; actual option payload and direct read-only MCP integration still required |
| 2. Focused intake | Explicit scoped run using existing per-ticker stage chain; optional broker quote advisory projection | Full-vs-focused parity, no authority leak |
| 3. Reconciliation | Extend existing fill identity/causal chain; idempotent import of actual fills, manual presentation link, exception review, mark-vs-fill separation, realised closed-lot outcome | Historical broker sample reconciles against journal |
| 4. Lab and validation | Distinct Evening thesis, current broker quote, actual/open/counterfactual outcome disclosures | User acceptance; G3/G4 before calibration authority |

Open ACK decisions: whether broker-focused tickers come from a named watchlist or explicit human list; which actual broker account(s) are in scope; whether unmatched fills should appear in a dedicated Lab review panel; whether ingestion is a manual command or a post-run optional step. These choices do not justify inventing trade authority or a thesis ID.

### Slice 1 implementation boundary — 21 September 2026

`domain/broker_quote_observation.py` normalises an already-fetched
`tastytrade_get_quote` response. The local MCP repository's recorded equity
response established the kebab-case field shape; option cases in the contract
tests are synthetic until an actual redacted option quote and independent
instrument multiplier are supplied. The adapter accepts only one exact Equity
or compact OCC symbol, preserves the broker `updated-at` separately from the
fetch timestamp, and reports missing, crossed, halted, one-sided and
size-missing quotes without changing thesis validity. An option cannot support
execution review until its selected-contract and broker-instrument multipliers
match explicitly. The result is always `ADVISORY_ONLY`; it is not a live quote
fetcher, Lab projection, focused scanner route or execution permission.

The next integration gate remains a read-only direct-MCP client with an
allow-listed quote tool, redacted actual option fixture, independent instrument
metadata, MarketData side-by-side comparison and completed-run identity tests.
No broker order/write tool, account balance or capital sizing is in scope.

### Same-day delivery lane — do not wait for the full broker platform

The existing completed-session run `20260920_203115` has a 95-row `morning_validation/pretrade_focus_20260920_203115.csv` containing `FOCUS_PRIMARY` **advisory review candidates**. It is the practical starting list for today's desk review, not 95 validated entries. Work in this order:

1. Freeze the run ID, exact selected contract, completed-session quote dataset ID, thesis direction, invalidation, target and trigger for each reviewed name. Keep the 95-row list and full opportunity book visible; do not create a new scanner-only trade list from LSS.
2. Check the Morning thesis result for the same run when its terminal artefacts are available. A material overnight/intraday gap, invalidation or direction conflict can discredit an Evening thesis. An old EOD quote does not itself invalidate a 1–20-session thesis, but cannot prove *current* executability.
3. For a small human-chosen subset, compare the **exact** share or OCC option symbol with a read-only tastytrade quote. Require symbol, side, strike, expiry, multiplier, broker `updated-at`, fetched-at, bid, ask and sizes; label missing or unmatched fields explicitly. Until the deterministic adapter and contract tests pass, this is a human cross-check outside AVSHUNTER authority, not a broker-fed Lab verdict.
4. Let the human decide whether the still-valid thesis has acceptable current execution economics. No scanner ratio, Phantom history, broker position, account balance or Worker narrative may grant `BUY_NOW`, alter the frozen direction or allocate capital.
5. Before a new scanner output is treated as production evidence, run a fresh scan, reconcile row counts and VMS `GO`/`PROBE` membership with the manifest, confirm no missing-data `EXCLUDED` route or sweep/dark-pool claim, and run the governed downstream handoff regression. Stop promotion on any contradiction; retain the prior completed-session slate rather than silently repairing it.

This lane lets the desk review existing governed Evening work during the US session. It **does not** assert that the unbuilt direct-MCP adapter, focused orchestrator mode, Lab broker projection or outcomes reconciliation can be finished or accepted before the afternoon session. Their gates in the table above remain mandatory.

### Slice 1B implementation record — 21 September 2026

The previously missing direct read-only quote bridge is now implemented in
`bridge/tastytrade_readonly_mcp.py`. It launches the installed stdio server in
forced production/read-only mode, removes arbitrary API-URL overrides, checks
the quote tool is advertised, and permits only `tastytrade_get_quote`. Compact
AVSHUNTER OCC symbols are converted to tastytrade's space-padded OCC request
form without changing adjusted roots. OAuth values are inherited only from an
approved process environment; no Claude Desktop configuration or credential
value is read, copied or logged. A real-server `initialize`/`tools/list`
smoke check passed without a quote/API request.

`bridge/tastytrade_go_quote_capture.py` and
`scripts/capture_tastytrade_go_quotes.py` provide a separate optional capture
for a frozen Morning GO cohort. It retains exact identity, provider quote time,
fetch time and advisory quality states. A day-zero ask-to-bid *paper mark* is
computed only if the broker's quote timestamp falls inside operator-supplied
close-window bounds; it is never called a fill, a mature 1–20-session outcome,
or new pipeline authority. Missing and old quotes remain unknown. Focused
broker/observation regressions passed 18 tests (plus 7 subtests).

**Not yet accepted as a live broker integration:** this Codex process has no
Tastytrade OAuth environment, so no authenticated quote or actual option
response was obtained. The server's instrument multiplier shape and live
option symbol coverage remain unverified. The CLI is not wired to the Evening
or Morning orchestrator, the Lab, focused scanner route, fill reconciliation,
or C12 outcome ledger. These remain open slices under the gates above; do not
represent them as completed or discard them.

## 7. Build-time estimate

Conditional engineering estimate once the MCP read-only output and a redacted transaction sample are available: discovery and contracts **1–2 working days**; focused intake and parity **2–3**; fill identity/causal-chain repair, Stage 9 mark-vs-fill separation, reconciliation and tests **4–7**; Lab projection, end-to-end test and review **1–2**. Total **8–14 engineer-days**, or roughly **6–10 elapsed working days with two independent implementers and one integration owner**. Broker-history oddities and adjusted contracts can add time. Forward shadow validation and any later calibration-authority decision require additional trading sessions and are **not** included in the build estimate.
