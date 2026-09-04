# AVSHUNTER Python Logic and Pipeline Failure Atlas

**Document:** AVS-PLA-001  
**Date:** 2026-09-01  
**Scope:** Review of `AVSINV001_CODEBASE_USAGE_AND_SCALEBACK_20260901.md` against the current repository and current run `20260901_082437`.  
**Change policy:** Read-only assessment. No production code, configuration, database, or run artefact was changed.

## 1. Executive conclusion

The inventory is a useful starting point, but it should be **approved with corrections**, not treated as an exact production architecture.

The main correction is conceptual: **static reachability is not runtime authority**. A file can be reachable because it is imported, mentioned in a disabled function, used by a fallback, or retained for compatibility. That does not mean it is actively calculating or deciding every production result. The stated 187 reachable files are therefore an upper bound on possible production code, not 187 equal production components.

The present pipeline is failing mainly at **semantic handoffs**, not because its individual quantitative formulas are uniformly poor:

1. Discovery creates direction too early from too little evidence, while later Options logic creates it again from richer evidence.
2. Direction, target, invalidation, contract and quote do not always travel as one immutable thesis object.
3. Missing numeric data is sometimes serialized as zero, turning “unknown” into a real-looking value.
4. The run manifest measures stage and schema completion more strongly than economic completeness.
5. The Lab UI has its own alias/fallback logic, so valid upstream values can be displayed as missing or can be replaced by DTE.
6. Duplicate module names resolve differently in root-launched and `scripts/`-launched processes.
7. The orchestrator contains historic, disabled and duplicate phase vocabulary, obscuring the actual order of authority.

This explains how a technically completed run can still produce no executable puts, an all-call Lab view, missing hold periods, and a health score of 100.

## 2. Corrections to the supplied inventory

| Inventory statement | Validation | Correct interpretation |
|---|---|---|
| 419 live-tree Python files | Not reproducible from the supplied attachment alone because `usage_graph.json` was not delivered/found | The inventory's exclusions and exact file list are required to reproduce this number. A raw current scan sees more than 1,000 `.py` paths because the repository now contains many backup/test copies and inaccessible temporary folders. |
| 187 reachable files are “the real system” | Partly true | They are statically reachable. Active runtime authority must also be proven by current phase execution, feature flags, branch activation and artefact lineage. |
| `scripts/run_vanguard_from_packages.py` cannot parse on Python >=3.12 | **False** | It parses successfully with installed Python 3.14.0. The nested-quote f-string is legal under PEP 701. This should be removed from the risk register. |
| Manual bare `python` is safe if venv is active | Currently fragile | The repository venv launcher is broken in this environment: it points to an inaccessible WindowsApps Python 3.13. The working interpreter is `C:\Python314\python.exe`. Interpreter identity must be recorded and enforced. |
| Duplicate modules are a risk | **Confirmed and more serious than described** | Importing `avshunter_monetisation_policy` from repo root resolves the root file; inserting/running from `scripts/` resolves the different scripts copy. Their SHA-256 hashes differ. Process start location can therefore alter policy. |
| Backups are harmless because they are not primary | False as a general rule | The current tree contains numerous legal Python module names in backup/old paths. `sys.path` manipulation or a changed working directory can select them. |

## 3. Actual current data flow

```text
Universe scanner
    -> Discovery/Wyckoff/Precor/Fusion
    -> package builder
    -> canonical historical-price backfill
    -> Vanguard auction/statistical/actuarial analysis
    -> Options Intelligence + contract selection + OLM/EV evidence
    -> Horizon routing / actuarial enrichment / Phantom
    -> SuperBrain passthrough -> Wall Break -> EIL -> GARCH -> Trigger
    -> EOD candidate book + final run manifest
    -> Morning Gate (fresh underlying/option/structure evidence)
    -> Execution Gate + Morning Handoff Finalizer
    -> governed Lab opportunity book
    -> Pipeline Interpreter evidence handoff
```

Macro, bond, GEX, news and catalyst information are advisory context. They may affect ranking, caution, sector interpretation or explanation, but they must not create direction or grant/deny capital independently.

### 3.1 Intended authority boundaries

| Boundary | Required authority |
|---|---|
| Discovery | Establish or explicitly defer the underlying thesis direction; retain all evidence used. |
| Vanguard | Quantify structure, regime-independent technical state, outcomes and preferred horizon. It should challenge confidence, not silently author a different trade. |
| Options Intelligence | Select a contract consistent with the frozen thesis and compute contract-specific evidence. It must not reverse the underlying thesis. |
| EOD Candidate Engine | Assemble one governed preparation record. It must preserve nulls and lineage. |
| Morning Gate | Compare current price, quote and market structure with the EOD thesis; confirm, resize, require a requote, or invalidate. |
| Execution Gate | Final capital permission only. It must not repair the thesis or invent data. |
| Intelligence Lab | Faithful projection of governed fields. It must not infer a different trade from UI fallbacks. |
| Pipeline Interpreter | Explain and reconcile accepted evidence. It must not overwrite governed direction, contract or permission. |

## 4. Where the pipeline is going wrong now

### 4.1 Direction is authored twice

`avshunter_discovery_ULTIMATE.py` calls `preliminary_discovery_direction()` using only `fusion_direction` and Wyckoff `trade_direction`. The function returns `UNRESOLVED` unless either input is explicitly directional. Discovery already has `precor_intent` and trend, but does not use them at this boundary.

The same contract module contains the richer `structural_direction()` table:

- `BUY_SETUP -> CALL`
- `SELL_SETUP -> PUT`
- `TRANSITION + BULLISH -> CALL`
- `TRANSITION + BEARISH -> PUT`
- mixed transition -> `STRANGLE`
- `WAIT -> UNRESOLVED`

Current-run evidence shows the effect: 1,440 of 1,518 Discovery rows were `UNRESOLVED`, even though the existing structural table could classify approximately 593 CALL, 516 PUT and 185 non-directional rows, leaving about 146 genuinely unresolved. Options later consumes Precor evidence and authors the missing direction. That makes Options appear to “flip” Discovery even though Discovery often never completed the thesis.

**Impact:** direction changes late, after geometry and some contract fields have already been calculated. That is the central source of CALL/PUT inconsistency.

### 4.2 Direction and invalidation geometry are not one object

Options Intelligence currently reads the upstream `stop_loss` as its first structural invalidation source. For puts, that value is frequently a support stop below entry—the correct geometry for a long equity/call thesis, but invalid for a long put. Direction governance then correctly rejects it.

In the latest Morning candidate set:

- 98 candidates were CALL and 93 were PUT.
- 90 of the 93 puts carried `invalidation_spot = 0.0`.
- 87 failed because runway prices must be positive.
- the three puts with valid geometry were still blocked/reviewed by quote spread.
- direction-correct Wyckoff invalidation evidence existed for 91 of the 93 puts but was not selected by the Options handoff.

**Impact:** the Lab looks call-only although the upstream book is balanced. The problem is not macro call bias; it is failed put geometry.

### 4.3 Missingness becomes zero

The Options layer now correctly treats a missing structural stop as `None`; it no longer fabricates `entry * 0.97`. But downstream helpers such as `_first_flt(..., default=0.0)` and CSV serialization can still turn the absence into `0.0`.

**Impact:** downstream code cannot distinguish “missing authoritative invalidation” from a literal zero-dollar invalidation. Error messages become geometry failures instead of data-lineage failures, and counts are misleading.

### 4.4 Technical health is not semantic trade health

The current final manifest reports:

- `run_health_score = 100`
- `pipeline_technical_health = PASS`
- `run_tradeable = true`
- all required columns present

The same manifest also records:

- 454 selected handoffs missing `invalidation_spot`
- 74 missing `contract_multiplier`
- 22 contract-multiplier rejections

The Morning execution summary then blocks 90 puts and additional calls for direction/geometry defects. The manifest health calculation primarily checks whether stages completed and columns exist; it does not require the values inside those columns to be valid for the candidate’s direction.

**Impact:** “100” currently means technically complete, not semantically ready for trading. The user understandably interprets it as the latter.

### 4.5 The Lab reinterprets fields

The Lab backend’s `_extract_hold_period()` only checks legacy `hold_label` aliases. The governed book contains `hold_period` and `time_horizon`, so the UI displays `-` for Hold. `_extract_time_horizon()` does not directly prefer `time_horizon`; when its older aliases are absent it falls back to contract DTE and displays values such as `17D DTE` as the trade horizon.

**Impact:** valid upstream data looks missing, and expiry is presented where the user expects thesis holding period.

### 4.6 Duplicate policy implementations are process-dependent

There are two different live files named `avshunter_monetisation_policy.py`:

- root file used by a root-started bare import, including `execution_intelligence_runner.py`
- scripts file used when a script process has `scripts/` first on `sys.path`

The files are not byte-identical. This is not merely clutter; it can produce different verdicts for identical rows in separate phases.

### 4.7 The orchestrator carries obsolete topology

The orchestrator still contains disabled Phase 9.5/9B/9C functions and historic comments while the active order uses overlapping labels such as Options “8a/8b”, trigger package and CSV passes, and Horizon Router 1B after Options. Static analysis follows imports and function bodies even when phase calls are disabled.

**Impact:** audits overstate the active system, phase ownership is hard to reason about, and developers can modify a reachable-but-disabled engine believing it is authoritative.

## 5. Production Python file atlas

The following atlas describes every production family named by the inventory. “Constraint” identifies the condition most likely to cause a drop, wrong calculation, or misleading display.

### 5.1 Orchestration, scanning and Discovery

| File | Logic / algorithm | Inputs and dependencies | Output / impact | Principal constraint or risk |
|---|---|---|---|---|
| `intelligent_orchestrator.py` | Executes phase graph, validates subprocesses, pins run directory, emits audits/manifests and aborts under enforced CDS failures. | CLI mode, environment flags, dropbox files, scanner/discovery/packages and all downstream scripts. | Owns run order and promotion. | Too many historic phase branches and non-sequential labels; subprocess boundaries hide process-specific imports. |
| `scripts/avshunter_universe_scanner.py` | Builds Tier-1 universe; fetches price/options/IV/borrow data; computes VMS, sector relative strength, volume anomaly, flow proxies and contract scores. | MarketData, price source, IV cache/Phantom, universe. | Scanner manifest and candidate universe. | Repeated external fetch paths; early pre-screen can remove tickers before richer structural evidence. Synthetic test paths must never activate in production. |
| `avshunter_discovery_ULTIMATE.py` | Computes EMA/ATR/ADX/VWAP, Crabel compression, early positioning, tier, composite score, win probability, Wyckoff buckets and preliminary direction. | Scanner universe, daily bars, Wyckoff engine, Precor, fusion, regime context. | Discovery CSV and thesis preparation evidence. | Preliminary direction ignores Precor intent/trend; score is a composite heuristic, not calibrated probability. |
| `WyckoffEngine_3101_v2.py` | Detects accumulation/distribution/markup/markdown structure and trade direction from price/volume patterns. | OHLCV. | Wyckoff phase, events, direction evidence. | Multiple historical copies; taxonomy drift propagates into actuarial keys. |
| `wyckoff_crabel_precor_logic_v2.py` | Combines Wyckoff and Crabel/Precor setup logic into BUY/SELL/TRANSITION/WAIT intent. | Structure, compression, trend and volume. | `precor_intent`, setup evidence. | Strong directional evidence is generated here but ignored by preliminary Discovery direction. |
| `wyckoff_phase_validator.py` | Cross-checks phase claims and emits validation-prefixed fields. | Wyckoff result and bar-derived context. | Validation fields. | Validation can coexist with contradictory legacy phase columns unless one field is designated authoritative. |
| `swing_fusion.py` | Fuses swing sub-signals into direction/strength. | Technical sub-signals. | Fusion direction. | Current run emitted almost entirely NONE; using it as a primary Discovery direction source creates mass unresolved state. |
| `asymmetry_gate_swing.py` | Evaluates upside/downside asymmetry for swing setups. | Target, invalidation, volatility/structure. | Gate or score adjustment. | Depends on correct side-aware geometry. |
| `enums_structural.py` | Shared structural labels/enums. | None. | Vocabulary. | Duplicate literal vocabularies elsewhere allow drift. |
| `regime_threshold_injector.py` | Adjusts thresholds using regime context. | Regime snapshot and baseline thresholds. | Modified thresholds. | Macro/regime must remain advisory; threshold changes must not silently author direction. |
| `polygon_data_fetcher.py` | Rate-limited equity OHLCV/data fetch abstraction. | Polygon credentials/network. | Price frames. | Provider naming is legacy and may fail/return empty; canonical history should be preferred when session data already exists. |

### 5.2 Package, history and macro preparation

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `scripts/build_packages_from_discovery.py` | Deduplicates Discovery rows by ticker, normalises macro snapshot and builds one JSON package per ticker with data contract. | Discovery CSV + macro -> packages. | A package is the primary baton; dropped/renamed fields here disappear from all later phases. |
| `scripts/backfill_timeseries_into_packages.py` | Resolves canonical daily/intraday history, fetches only when needed, computes returns, validates series and writes quality state. | Packages + canonical history/provider. | Correct CDS reuse point; systemic failures abort while ticker defects should be quarantined. |
| `scripts/inject_macro_into_packages.py` | Flattens macro and writes regime snapshot into packages. | Macro JSON -> package context. | Advisory fields must be namespaced so they cannot overwrite structural authority. |
| `scripts/normalise_macro_contract.py` | Derives bounded scores for liquidity, VIX, GEX and macro momentum. | Raw macro JSON -> normalised contract. | Normalisation is heuristic; missing/stale values must remain disclosed. |
| `scripts/macro_quant_packet.py` | Derives risk, liquidity, vol, dealer gamma, rates, credit, sector rotation, horizon and conflict flags. | Normalised macro/package -> quant packet. | Useful context, not a GO/NO-GO authority. Conflicting source timestamps can create internally inconsistent labels. |
| `scripts/macro_exposure_resolver.py` | Maps tickers/sectors/themes to macro exposures and narratives. | Macro packet and role map -> ticker context. | Exposure alignment should explain risk, not flip CALL/PUT. |
| `macro_horizon_router.py` | Routes signals by horizon using macro bucket and sector permission. | Candidate signals + macro horizon. | Its placement after Options means Options may select a contract before governed horizon is finalized. |
| `scripts/sector_alignment.py` | Classifies ticker sector alignment with macro sector bias. | Sector map + macro. | Advisory ranking only. |
| `scripts/apply_macro_enrichment_to_discovery.py` | Adds macro-bias and audit fields to Discovery without deleting core evidence. | Discovery + enrichment delta. | Suffix/alias collisions can create two apparent macro truths. |
| `scripts/apply_external_intel_review_lane.py` | Adds catalyst/news/macro review context and directional conflict labels. | Catalyst calendar + macro + Discovery. | Must never convert advisory direction into governed thesis direction. |

### 5.3 Vanguard and actuarial reasoning

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `scripts/run_vanguard_from_packages.py` | Loads packages, validates Phase-2 baton, computes technical enrichments, builds engine payload, serializes signals and actuarial lineage. | Packages -> Vanguard CSV/JSON. | Large adapter with many aliases; any dropped baton field gets defaulted. Installed Python 3.14 parses it correctly. |
| `vanguard/main.py` | `VanguardEngine.analyze_ticker()` orchestrates Layer 1 auction, Layer 2 statistical/actuarial and preferred horizon. | Package payload -> Vanguard signal. | Must consume, not recreate, frozen thesis direction. |
| `vanguard/physics_state_engine.py` | Converts returns, state labels and confidence into market-physics state and success probability. | Technical/actuarial fields -> physics fields. | Probability is model-derived and should not be confused with observed win rate. |
| `vanguard/trade_governance.py` | Applies open-trade/campaign governance so scanner cannot overwrite active positions. | Trade journal + signal. | Correctly protects existing campaigns but increases branching between new and active theses. |
| `vanguard/core/actuarial_registry.py` | Resolves live actuarial database/cache location and metadata. | Config/filesystem. | Wrong registry path creates silent use of stale store unless fingerprint/date are enforced. |
| `vanguard/core/cache_integrity.py` | Verifies cache schema/fingerprint/integrity. | Actuarial cache. | Structural integrity does not prove state-key coverage. |
| `vanguard/core/schema_contract_v6.py` | Maps legacy outcome column names to governed schema. | Parquet schema. | Compatibility warnings are expected; too many aliases obscure canonical vocabulary. |
| `vanguard/core/truth_packet.py` | Packages source/value/status/confidence lineage. | Row fields. | Useful only if consumers honor status rather than taking fallback value. |
| `vanguard/core/actuarial_core_v7.py` | Core v7 actuarial lookup/calculation helpers. | Historical state/outcome data. | Exact high-dimensional keys can be sparse. |
| `vanguard/layer1_auction/auction_synthesizer.py` | Combines auction/market-profile components. | OHLCV/profile evidence. | Dependent on consistent session bars. |
| `vanguard/layer1_auction/control_identifier.py` | Identifies buyer/seller control. | Auction features. | A descriptive state, not standalone direction authority. |
| `vanguard/layer1_auction/market_profile.py` | Calculates profile/value-area structure. | Price/volume distribution. | Bar granularity and session selection materially change results. |
| `vanguard/layer1_auction/value_acceptance.py` | Scores acceptance/rejection around value. | Profile + current price. | Stale close vs live price can reverse acceptance. |
| `vanguard/layer1_auction/value_migration.py` | Measures movement of value over sessions. | Historical profiles. | Requires comparable sessions. |
| `vanguard/layer2_statistical/state_calculator.py` | Builds categorical state used for actuarial matching. | Vol/trend/structure/ADX/Wyckoff/ATR. | Taxonomy mismatch produces neutral fallback. |
| `vanguard/layer2_statistical/actuarial_query.py` | Queries exact/hierarchical state evidence and sample counts. | State key + cache. | Exact seven-dimensional matching fragments data; fallback depth must be disclosed. |
| `vanguard/layer2_statistical/edge_detector.py` | Converts actuarial outcomes into edge/confidence evidence. | Query result. | Neutral prior must not be presented as proven edge. |
| `vanguard/schemas/input_schema.py` | Validates engine input. | Package payload. | Defaults can hide missing data if validation is permissive. |
| `vanguard/schemas/auction_schema.py` | Defines auction output contract. | Layer 1. | Schema presence is not semantic validity. |
| `vanguard/schemas/state_outcomes_schema.py` | Defines statistical state/outcome contract. | Layer 2. | Label version must match database taxonomy. |
| `vanguard/schemas/trade_schema.py` | Defines trade signal structure. | Combined engine result. | Needs immutable thesis identity and side-aware geometry. |

### 5.4 Options, EV and liquidity lifecycle

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `scripts/avshunter_options_intelligence.py` | Resolves completed option session; loads canonical/MarketData chains; normalises quotes; computes/backfills IV and Greeks (BS/Heston); computes GEX/PCR/walls; selects contracts; builds direction/geometry/OLM/EV handoff. | Vanguard/packages + option chains -> enriched Options CSV. | Largest semantic bottleneck. It currently starts invalidation from `stop_loss`, while direction may only be finalized here. Provider fallback, contract repair and lifecycle persistence make failure modes complex. |
| `iv_engine.py` | Produces IV percentile/regime/term-structure fields. | Current and historical IV. | Requires comparable history and correct timestamp. |
| `vanguard/ev3_stage0.py` | Validates direction/horizon/contract inputs, builds state keys and forward barrier cache. | Governed candidate + historical paths. | Reject classifications must distinguish non-applicable from data defects. |
| `vanguard/ev_engine_v3.py` | Prices American options/vertical debits, anchors option mids, evaluates barrier exits and selects contract under policy. | Candidate, barrier cache, option chain. | Contract-specific; result is invalid if contract changes without recomputation. EV is advisory under current governance. |
| `contracts/selected_contract_economics.py` | Canonicalizes OCC symbols/structures, hydrates exact quotes, computes premium R:R and monetisability identity. | Selected structure + exact quote. | Economics must be recomputed after every contract substitution; underlying R:R is not option profitability. |
| `contracts/options_liquidity_lifecycle.py` | Classifies moneyness, expected move, executability, runway, maturation horizons and monitoring states. | Thesis geometry + contract quote + DTE/hold. | OI/volume are ranking evidence, while quote/spread and side-aware runway govern current executability. |
| `canonical_data/option_liquidity_lifecycle.py` | Append-only SQLite persistence for thesis events, observations and selections with immutable identities and supersession. | OLM result. | Same identity with changed immutable content raises conflict; timestamp/identity design must support legitimate refreshes. |
| `contracts/options_liquidity_execution_guard.py` | Maps lifecycle state to maximum permissible action. | OLM state + proposed action. | Defence-in-depth; must not be bypassed by later Lab/Interpreter writes. |
| `contracts/quote_change_evidence.py` | Compares exact-contract EOD and morning quote snapshots. | Two snapshots. | Comparison is not meaningful if OCC contract differs. |
| `contracts/long_option_policy.py` | Central policy constants for long calls/puts. | None. | Policy should be small and versioned; avoid duplicated thresholds in engines. |

### 5.5 Enrichment, scoring and EOD book

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `scripts/avshunter_superbrain_layer.py` | Historical “SuperBrain” enrichment; current orchestrator also has a passthrough path. | Options output. | Authority is ambiguous if both enrichment and passthrough vocabulary remain. |
| `wall_break_scorer.py` | Scores distance/momentum/quality around option walls. | GEX walls, price, direction. | Human-useful advisory; cannot authorize entry and must be side-aware. |
| `execution_intelligence.py` | EIL scoring primitives. | Enriched candidate. | Legacy verdict vocabulary overlaps newer governed states. |
| `execution_intelligence_runner.py` | Runs EV v2/EIL, percentile overrides, vetoes, campaign/execution verdicts and Vanguard handoff. | SuperBrain/WBS/Options. | Imports root monetisation policy and disabled `final_decision_engine`; duplicate authorities remain reachable. |
| `ev_engine_v2.py` | Legacy expected-value calculation. | Win probability, payoff geometry. | Units and authority differ from EV3; retain only as labelled advisory or retire. |
| `probability_engine.py` | Derives probability features. | Actuarial/model signals. | Estimated probability must disclose source/calibration. |
| `scenario_builder.py` | Constructs scenario payoffs/states. | Candidate geometry. | Duplicate same-name variants exist; process path can select wrong implementation. |
| `scenario_router.py` | Routes candidate to scenario logic. | Scenario/setup labels. | Unsupported labels can default or drop. |
| `eil_eod_resolver.py` | Resolves EIL output for EOD use. | EIL rows. | Should not overwrite frozen thesis or execution authority. |
| `avshunter_monetisation_policy.py` | Root legacy monetisation policy used by EIL runner. | Option/economics fields. | Conflicts with different scripts copy. |
| `scripts/avshunter_monetisation_policy.py` | Scripts-local policy variant. | Options process. | Same import name, different hash and behavior. Must be consolidated. |
| `garch_runner.py` | Fetches OHLCV and estimates forward variance per ticker, in parallel. | Price history + regime. | Runs after EIL in current flow, so EIL can be computed without GARCH and patched later. |
| `layer3_forward_variance.py` | Computes HAR/GARCH-style forward realized variance and expected moves. | Return history. | Forecast is magnitude, not CALL/PUT direction. |
| `trigger_layer.py` | Evaluates vol compression, VWAP reclaim, range break and trap triggers; scores quality and GO eligibility. | Package/price/trigger evidence. | Freshness and direction compatibility are essential; trigger score is not capital authority. |
| `catalyst_truth_engine.py` | Reconciles catalyst evidence. | Catalyst inputs. | User has retired catalyst overlay as required input; residual code should remain advisory/optional. |
| `avshunter_trap_engine.py` | Detects trap/failed-break conditions. | Price/volume/VWAP. | Some VWAP signals have historically been structurally unavailable. |
| `mcmillan_advisory_layer.py` | Adds advisory options/technical context. | Candidate/options fields. | Must not modify governed direction/action. |
| `scripts/exit_rules_engine.py` | Creates time/price/structure exit discipline. | Final thesis/contract. | Exit rules require correct hold and invalidation fields. |
| `eod_candidate_engine.py` | Arbitrates direction evidence, classifies status/tier, assembles contract, lifecycle, monetisability and morning tasks. | All enriched CSV fields. | Huge alias surface; null-to-zero conversion and late direction arbitration are major risks. |
| `contracts/lab_control.py` | Builds run manifest, resolves tradeability, enforces OLM, constructs opportunity book and Lab projection. | EOD/morning outputs + manifests. | Current health score overweights schema/stage presence and underweights valid value coverage. |

### 5.6 Morning, execution and handoff

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `morning_gate.py` | Loads EOD candidates, fetches current underlying/contract/structure evidence, compares macro advisory context, checks invalidation, direction, spread, DTE, OLM and EV evidence. | Morning candidates + canonical/live data. | Should validate overnight thesis drift, not demand 60-second quote permanence or silently repair direction. Restart worklists must be immutable by evidence scope, not by volatile row content. |
| `execution_gate.py` | Converts validated rows into BUY_NOW/BUY_SMALL/skip decisions under direction and OLM guard. | Morning-validated rows. | Sole capital authority; external quote fallback and compatibility paths must be deterministic. |
| `morning_handoff_finalizer.py` | Checks execution/Lab agreement, identity and hashes; publishes MSI handoff; syncs Interpreter. | Execution output + Lab book. | Structural/hash correctness does not guarantee fresh quote or correct geometry. |
| `earnings_calendar_enricher.py` | Adds earnings proximity. | Calendar + candidates. | Date/timezone freshness determines event risk. |
| `msi_runtime.py` | Reads MSI feature flags and calculation version. | Environment. | Different manual launch environments can activate different flows. |
| `outcome_capture.py` | Fetches current marks, applies exit/time-stop/wall rules, classifies result and builds validation report. | Open positions + price/option marks. | Outcome learning is weak until all accepted/rejected candidates and MFE/MAE are captured. |
| `avshunter_trade_journal.py` | SQLite entry/exit journal, open-position lock and calibration report. | Executed trades. | Very small historical closed-trade sample; cannot yet validate profitability statistically. |

### 5.7 Canonical Data System (CDS)

| File | Responsibility | Key constraint |
|---|---|---|
| `canonical_data/registry.py` | Registers immutable dataset metadata and lineage. | A dataset ID cannot represent changed content. |
| `canonical_data/storage.py` | Physical canonical storage operations. | Writes must be atomic and path-governed. |
| `canonical_data/contracts.py` | Dataset and request contracts. | Version every identity-affecting change. |
| `canonical_data/gateway.py` | Read/reuse/fetch decision boundary. | Provider calls only on governed cache miss/staleness. |
| `canonical_data/worklist_gate.py` | Filters to authorized tickers and reconciles processed/quarantined/missing outcomes. | Dropped tickers must not be fetched downstream. |
| `canonical_data/session_clock.py` | XNYS sessions, bounds, early closes and freshness. | Session freshness is different from intraday quote age. |
| `canonical_data/option_identity.py` | Parse/build/normalize OCC identity. | Contract comparisons require exact normalized identity. |
| `canonical_data/option_chain_store.py` | Canonical option-chain service and completed-session resolution. | Multiple session dates in one payload should quarantine affected data, not necessarily abort the universe. |
| `canonical_data/marketdata_response.py` | Normalizes MarketData provider response. | Provider schema/version drift. |
| `canonical_data/market_observation_resolver.py` | Resolves underlying NBBO/market observations. | Quote timestamp and source must be retained. |
| `canonical_data/intraday_bars.py` | Normalizes minute bars. | Same-run restart must distinguish legitimate appended bars from changed worklist identity. |
| `canonical_data/stage_publisher.py` | Publishes immutable stage worklists. | Overly strict same-run equality can block restart after new observations. |
| `canonical_data/historical_prices.py` | Normalizes/upserts daily OHLCV and reports coverage. | Split adjustment and session uniqueness. |
| `canonical_data/history_bridge.py` | Reads canonical history, writes through fetched data and shadows parity. | Must update database only with validated rows and preserve source. |
| `canonical_data/daily_adapter.py` | Adapts daily provider payload to canonical format. | Adjustment convention must be stable. |
| `canonical_data/request_ledger.py` | Records provider request/reuse result. | Required to prove duplicate calls are eliminated. |
| `canonical_data/lifecycle.py` | Tracks ticker progression, drops and authorizations. | Each stage must reconcile input = output + quarantined + dropped. |
| `canonical_data/discovery_publisher.py` | Publishes Discovery outcomes as governed data. | Direction completeness must be part of semantic validation. |
| `canonical_data/bundle_freshness.py` | Derives multi-source freshness state. | One stale component should not label unrelated fresh evidence stale. |
| `canonical_data/contract_reference.py` | Contract reference lookups. | OCC/symbol normalization. |
| `canonical_data/feature_flags.py` | CDS feature switches. | Manual invocation must get the same defaults as orchestrated runs. |
| `canonical_data/errors.py` | Typed CDS errors. | Ticker data defects should be quarantinable; systemic authority faults should fail closed. |
| `canonical_data/narrow_refresh.py` | Candidate-scoped refresh design. | Inventory says built but not wired; should be the Interpreter/morning refresh route, not a second full fetch pipeline. |

### 5.8 Shared contracts

| File | Responsibility | Key constraint |
|---|---|---|
| `contracts/direction_governance.py` | Normalizes direction, collects weighted evidence, resolves/validates governed record. | Must run once at thesis freeze; later contradictions create review/invalidation, not silent replacement. |
| `contracts/governed_states.py` | Central enums for data and lifecycle evaluation states. | No bare duplicate literals outside enum. |
| `contracts/handoff_contract.py` | Truth packet with source/status/confidence. | Consumers must respect status. |
| `contracts/lab_control.py` | Manifest, opportunity book, UI projection and learning feedback. | Separate technical health from semantic completeness. |
| `contracts/lab_evidence_overlay.py` | Validated compatible overlay application. | Overlay cannot change governed authority. |
| `contracts/interpreter_handoff.py` | Hashes and validates evidence bundles/manifests. | Exact run/book/contract identity. |
| `contracts/interpreter_handoff_materializer.py` | Produces Interpreter-ready row and evidence bundle. | No uncontrolled field overlay. |
| `contracts/interpreter_macro_context.py` | Materializes macro advisory snapshot and row fields. | Macro is advisory and immutable for that handoff. |
| `contracts/macro_enrichment_delta.py` | Validates and merges ticker macro exposure delta. | Prevent contradictory suffix fields. |
| `contracts/macro_regime_safety.py` | Normalizes macro regime/sub-state/distribution. | Regime does not grant permission. |
| `contracts/bond_macro_contract.py` | Normalizes bond sidecar. | Staleness must remain explicit. |

### 5.9 Intelligence Lab

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `intelligence-lab/intelligence_lab.py` | Flask API/UI loader, run caching, governed-book filtering, journal operations, ranking and display projection. | Final manifest/opportunity book/morning handoff. | Alias logic can hide valid fields; cache signatures must change when governed handoff changes; strict JSON provider correctly rejects NaN. |
| `contracts/lab_evidence_overlay.py` | Applies only compatible overlays. | Run/ticker/contract-scoped evidence. | Correct defence against stale/mismatched enhancements. |

The Lab must display values, sources and status from the governed book; it should not derive trade horizon from DTE or synthesize permission from verdict-shaped fields.

### 5.10 Pipeline Interpreter

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `pipeline_interpreter/pipeline_interpreter.py` | CLI entry point. | Commands. | One blessed invocation path required. |
| `pipeline_interpreter/pipeline_interpreter_commands.py` | Routes triage/ticker/chart/morning/live/macro/news/story commands and resolves trusted source. | Handoff, Lab, MA inputs, optional screenshots. | Must use validated handoff first; broad CSV search is fallback only. |
| `pipeline_interpreter/pipeline_interpreter_engine.py` | Builds prompts, loads CSV/images, calls model API, extracts verdict/brief/story. | Validated evidence + optional screenshots. | Model narrative is not authority; image evidence is required only for unavailable visual/L2 information. |
| `pipeline_interpreter/pipeline_interpreter_outputs.py` | Parses and renders CSV/HTML/sidecars. | Model response. | Malformed response must fail closed. |
| `pipeline_interpreter/evidence_resolver.py` | Resolves latest accepted manifest and exact ticker/contract evidence. | Handoff manifest/bundle. | Prevents cross-run or cross-contract contamination. |
| `pipeline_interpreter/assessment_contract.py` | Builds, validates and appends assessments. | Evidence + narrative. | Assessment cannot contradict bundle authority. |
| `pipeline_interpreter/macro_context.py` | Loads macro packet and proves it did not change authority. | Macro reference. | Advisory only. |
| `pipeline_interpreter/news_macro_readers.py` | Reads macro, delta and News Terminal files. | Dropbox/MA inputs. | Freshness/source needed; no direction overwrite. |
| `pipeline_interpreter/thesis_registry.py` | Creates/updates thesis IDs, saves EOD baseline and computes morning delta. | Accepted EOD/morning evidence. | Accepted direction reversal requires a new thesis ID. |
| `pipeline_interpreter/trade_brief_builder.py` | Builds concise trader brief. | Governed evidence. | Explanation only. |
| `pipeline_interpreter/lab_reconciliation.py` | Reconciles Lab and triage universes/fields/run IDs. | Lab export + handoff. | Exact run/ticker/contract match. |
| `pipeline_interpreter/interpreter_qa.py` | QA checks for triage, ticker, story, delta and reconciliation. | Interpreter outputs. | QA should block publication, not mutate source. |
| `pipeline_interpreter/score_integrity_check.py` | Detects score drift and records/decommissions invalid score history. | Run CSVs. | Cross-sectional scores can change with universe; drift is not automatically alpha. |
| `pipeline_interpreter/entry_timing_engine.py` | First-passage, crowd-arrival and kill-switch probabilities; entry quality. | GARCH/structure/current price. | Timing estimate is advisory; current price matters but should not destroy a 1–20 day thesis unless invalidation/gap logic is breached. |
| `pipeline_interpreter/ma_inputs_sync.py` | Routes and copies completed outputs into MA inputs, with freshness/dedupe rules. | Run outputs. | “Already synced” can hide that a newer governed file was not selected if identity is based only on name. |

### 5.11 Macro producer utilities

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `build_macro_json.py` | Loads latest macro/GEX inputs, resolves conflicts, applies market overrides, normalizes horizon routing and validates output. | Dropbox market/macro inputs -> `macro_intelligence_latest.json`. | Primary GEX row selection must be deterministic; freshness is per sub-block. |
| `bond_macro_intelligence.py` | Fetches Treasury calendar/FRED curve, classifies curve, uses ZN/IEF proxy and HYG/LQD credit stress, creates composite and caution. | Treasury/FRED/equity data -> bond state/auction calendar. | Weekends and publication lag create valid stale states; stale curve labels must not be treated as current market move. |

### 5.12 Other in-run engines and audit modules named by the inventory

| File | Logic / algorithm | Inputs / output | Constraint or pipeline impact |
|---|---|---|---|
| `scripts/build_phase_transition_matrix.py` | Counts transitions between governed phase states, optionally by regime/tier, and flags sparse cells. | Actuarial database -> transition matrices. | Global-only matrix is used when `macro_regime` is absent; sparse cells are not reliable probabilities. |
| `scripts/behaviour_state_builder.py` | Builds behavior-state aggregates from historical observations. | Actuarial/history data -> state cache. | State vocabulary and date convention must match live producers. |
| `scripts/actuarial_enrichment_pass.py` | Joins actuarial state probabilities/sample counts onto current rows. | Enriched candidates + actuarial cache. | Neutral prior must carry match depth, sample size and fallback status. |
| `scripts/run_phantom.py` | Orchestrates Phantom options-history scoring. | Option snapshots/history -> Phantom enrichment. | Must use canonical MarketData datasets and exact session/contract identity. |
| `scripts/phantom_database.py` | Reads/writes Phantom SQLite history and registry data. | Canonical snapshots. | Large single-machine store requires backups, integrity checks and idempotent writes. |
| `scripts/phantom_engine.py` | Coordinates Phantom feature calculations and scoring. | Chain/history/Greeks. | Output is evidence, not execution authority. |
| `scripts/phantom_bayesian.py` | Bayesian updating of option-state evidence. | Historical priors + current observations. | Priors are misleading when historical outcome count is small or selection-biased. |
| `scripts/phantom_criticality.py` | Scores critical option/market states. | GEX, liquidity and surface features. | Threshold version must be disclosed. |
| `scripts/phantom_gamma_field.py` | Calculates gamma field/wall structure. | Chain strikes, gamma, OI. | Depends on Greek coverage and sign convention. |
| `scripts/phantom_info_flow.py` | Measures information-flow proxies. | Quote/volume/history. | EOD snapshots cannot reconstruct true order flow. |
| `scripts/phantom_iv_surface.py` | Maintains/queries IV surface history. | Strike/expiry IV observations. | Surface comparison needs constant coordinates or explicit interpolation. |
| `scripts/apply_ev3_authority.py` | Applies EV3 result fields/overlay to a run. | EV3 sidecar + run CSV. | Current policy treats EV3 as advisory; name “authority” is misleading and should not grant permission. |
| `scripts/run_ev3_shadow.py` | Batch-evaluates EV3 against candidate rows. | Candidate CSV + barrier cache. | Historical “shadow” naming remains after production evidence use; policy must be explicit. |
| `scripts/run_ev3_shadow_phase.py` | Orchestrator wrapper around EV3 batch execution. | Run paths/config. | Wrapper status must not be confused with economic coverage. |
| `scripts/ev3_calibration_report.py` | Summarizes EV3 coverage/rejections/calibration. | EV3 output and outcomes. | Calibration is not meaningful without sufficient clean outcomes. |
| `scripts/core_intel_exporter.py` | Exports selected core fields to downstream consumers. | Enriched run CSV. | Field allow-list can silently drop new governed columns. |
| `scripts/avshunter_superbrain_layer.py` | Legacy SuperBrain calculation/export. | Options output. | Active orchestration also uses passthrough behavior; only one should remain. |
| `dropoff_audit.py` | Reconciles where tickers disappeared across stages. | Stage artefacts. | Needs authoritative worklists; otherwise “pending” and “dropped” are conflated. |
| `handoff_contract_audit.py` | Checks required handoff fields and direction/contract consistency. | Handoff CSV/JSON. | Presence-only checks must be augmented by semantic geometry validation. |
| `uat_audit_report.py` | Aggregates run/UAT checks. | Run manifests and audit files. | Should report evidence, not self-certify production readiness. |
| `scripts/data_contract_validator.py` | Validates package/CSV contract fields and data quality. | Stage baton. | Validation must distinguish missing, stale, invalid and not-applicable. |
| `market_context_diagnostics.py` | Produces read-only diagnostics on context contradictions/coverage. | Enriched run. | Diagnostic only; cannot modify candidates. |
| `avshunter_regime_screener.py` | Screens candidate universe by regime characteristics. | Run inputs. | A missing input should disclose no assessment, not remove the universe. |
| `position_lifecycle_tracker.py` | Tracks open position/campaign state across runs. | Journal and current run. | Active-position direction must not be overwritten by scanner. |
| `weekly_intelligence_report.py` | Weekly performance/coverage summary. | Run/journal history. | Test runs must be excluded from learning metrics. |
| `premarket_intelligence_ULTIMATE.py` | Legacy/auxiliary premarket intelligence. | Premarket data. | Morning Gate is the current governed validator; this module must not create a second permission path. |
| `trade_book_builder.py` | Retired Phase 9C ranked book builder. | Enhancement output. | Reachable in code text but phase disabled; not current authority. |
| `final_decision_engine.py` | Retired/legacy final-decision logic still imported by EIL runner. | EIL/enhancement fields. | Import keeps obsolete verdict vocabulary reachable. |
| `execution_decision_engine.py` | Retired EDE execution-decision layer. | EIL result. | Disabled phase; should not be described as current execution authority. |

## 6. Non-production files: how to interpret the inventory

### 6.1 Manual/operator tools

These files do not automatically affect a run. They affect production only when an operator executes them and promotes their outputs:

- actuarial build/validate/promote/update scripts
- EV3 barrier build/verify/promote scripts
- Phantom backfill/Greek rehydration scripts
- CDS validation/baseline/repair tools
- QA, UAT and smoke tests
- SEC monitors and macro builders
- trader probes, desk cards and run auditors

Their principal risk is not runtime calculation but **ungoverned promotion**: a manual tool can replace a database or sidecar without a release manifest/fingerprint that the production run verifies.

### 6.2 Standalone subsystems

`orchestrator/`, `news_terminal/`, `ma_cockpit/`, `zero_dte/`, `short_swing/`, `bridge/` and `ml_confidence_layer/` are separate products/sandboxes unless a launcher or scheduler proves otherwise. They should not be counted as part of the main pipeline’s decision logic.

### 6.3 Backup and old files

Backups are evidence for rollback, not source code. They should be outside all import roots. The current repository has numerous copies of `morning_gate.py`, `intelligent_orchestrator.py`, Options Intelligence and Lab code. This inflates search results, slows tooling and makes accidental selection possible.

## 7. The simplified target architecture

The pipeline does not need more independent verdict engines. It needs one record with explicit state transitions:

```text
THESIS
  thesis_id
  ticker
  direction: CALL | PUT | NON_DIRECTIONAL | UNRESOLVED
  direction_status/source/version
  origin_spot, target_spot, invalidation_spot
  horizon and planned hold
  evidence timestamp/session

CONTRACT
  exact OCC symbol and multiplier
  quote snapshot identity
  DTE/delta/IV/Greeks/spread
  liquidity lifecycle state

MORNING DELTA
  current underlying price
  exact-contract current quote or requote state
  gap/invalidation/structure change
  action: READY | WATCH | REQUOTE | THESIS_INVALIDATED | DATA_MISSING
```

Rules:

1. Discovery either freezes a direction using the full structural table or explicitly says unresolved.
2. Vanguard and Options may challenge the thesis but cannot silently reverse it.
3. A genuine reversal creates a new thesis ID and recomputes target, invalidation, horizon and contract.
4. Null remains null. No missing stop, target, multiplier or quote becomes zero.
5. Morning compares changed evidence to the frozen EOD thesis.
6. ML/algorithms rank valid theses; they do not repair missing contracts or geometry.
7. Technical health, data completeness, thesis validity, contract executability and capital permission are separate scores/states.
8. Lab and Interpreter read the same governed record and are projections, not calculation authorities.

## 8. Priority failure register

| Priority | Failure | Why it matters | Correct boundary |
|---|---|---|---|
| P0 | Discovery unresolved 1,440/1,518 despite usable structural intent | Causes late direction authorship and downstream recomputation errors | Discovery + `direction_governance` |
| P0 | Put invalidation evidence not selected | Eliminates nearly the entire put side and creates all-call output | Options handoff contract |
| P0 | Missing invalidation serialized as zero | Hides lineage defect and produces misleading geometry failure | EOD candidate serialization |
| P0 | Manifest health 100 with hundreds of invalid handoffs | User cannot rely on health banner | `contracts/lab_control.py` |
| P1 | Lab ignores governed `hold_period`/`time_horizon` | Valid data appears missing/wrong | Lab projection |
| P1 | Duplicate monetisation policy imports | Same row can get different policy by process | Package/import architecture |
| P1 | Horizon finalization occurs after contract selection | Contract DTE may not match governed hold | Orchestrator order |
| P1 | GARCH runs after EIL | EIL computed without final variance evidence | Orchestrator order |
| P1 | Options Intelligence is an oversized multi-authority module | Hard to test and failures abort broad pipeline segment | Decompose acquisition, selection, analytics, lifecycle and handoff |
| P2 | Disabled engine functions remain statically reachable | Audits and developers misidentify authority | Orchestrator cleanup |
| P2 | Broken venv interpreter path | Manual commands are environment-dependent | Single launcher/preflight |

## 9. Recommended codebase decisions

### Keep and harden

- `canonical_data/`, `contracts/`, `market_structure/`
- one Discovery/Wyckoff implementation
- Vanguard Layer 1/2 and actuarial cache
- one Options Intelligence implementation, decomposed behind interfaces
- EOD Candidate, Morning Gate, Execution Gate, Handoff Finalizer
- governed Intelligence Lab and Interpreter handoff
- journal/outcome capture

### Consolidate before further model work

- the two monetisation policies
- direction assignment paths
- scenario builders
- horizon/hold aliases
- verdict/action vocabularies
- macro suffix/overlay fields

### Quarantine after launcher/scheduler check

- retired EDE/Kelly/PSE chain
- legacy orchestrator v1
- old morning validation pair
- catastrophe no-op engine
- dormant strategy sandboxes
- backup/dnu/dated modules

No deletion should be performed directly from static reachability. Move candidates outside import roots, run one accepted evening→morning→Lab→Interpreter cycle, and retain a reversible manifest.

## 10. Final thesis

AVSHUNTER’s problem is not lack of data or lack of quantitative components. It is that the pipeline repeatedly converts one trade thesis into loosely related rows, then asks later engines and the UI to reconstruct the original meaning from aliases.

The fastest route to a dependable and monetisable pipeline is therefore:

1. freeze direction and geometry together;
2. make exact contract and quote identity mandatory for contract calculations;
3. preserve missingness and source lineage;
4. make Morning Gate a delta validator rather than a second thesis builder;
5. make technical health honest about semantic coverage;
6. make Lab and Interpreter consume the same governed record;
7. remove process-dependent duplicate modules and disabled authorities.

That work will improve the existing pipeline more than adding another score, model or external dataset. Once these handoffs are stable, the existing actuarial, GARCH, trigger, OLM, wall and macro evidence can be evaluated for actual profitability rather than being masked by plumbing defects.
