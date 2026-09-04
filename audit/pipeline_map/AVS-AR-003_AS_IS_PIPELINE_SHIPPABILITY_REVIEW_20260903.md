# AVS-AR-003 — AVSHUNTER As-Is Pipeline Shippability Review

**Date:** 2026-09-03  
**Status:** FINAL — pre-build architecture, code, data-flow and algorithm review  
**Decision:** AVS-SD-002 is **APPROVED WITH MANDATORY ADDITIONS**  
**Change authority:** Review only. No production code, configuration, database or run output was changed.

## 1. Executive verdict

AVSHUNTER has several production-grade foundations, but the current end-to-end product is not yet semantically shippable. The remaining risk is not one isolated defect. It is the coexistence of:

- authoritative decisions and advisory scores that are not consistently separated;
- canonical observations and stage-local provider calls;
- governed fields and legacy aliases;
- genuine missing data and synthetic defaults;
- immutable EOD evidence and post-stage CSV/package rewrites;
- a governed Intelligence Lab book and a legacy display fallback;
- a governed Interpreter resolver and legacy Interpreter acquisition paths.

The new Market Profile and canonical-data design is directionally correct and should proceed. However, implementing only its intraday/profile workstreams would leave material contradictions in direction, macro, contract economics, execution, Lab and Interpreter behaviour. This review therefore adds a mandatory alignment layer to AVS-SD-002.

The correct product objective is:

> One point-in-time observation contract, one authority per decision, one explicit derivation for every computed field, one governed presentation surface, and one append-only record of what the pipeline knew and decided.

The system should not be promoted merely because an Evening run finishes. A successful run proves process completion; it does not prove semantic correctness, current executability or evidence lineage.

## 2. Scope and evidence

This review inspected the active production-shaped path from acquisition through:

1. orchestrator and preflight;
2. scanner and Discovery;
3. canonical storage and package completion;
4. Vanguard and actuarial processing;
5. Options Intelligence and contract lifecycle;
6. Horizon, EV3, trigger, EIL, GARCH and EOD selection;
7. Morning Gate and Execution Gate;
8. Intelligence Lab;
9. Pipeline Interpreter;
10. journal, lifecycle and proposed outcome persistence.

Primary evidence:

- source commit recorded by the latest run: `5d886f07c1d290f25600e2e7e62ae77aad85476a`;
- latest production-shaped Evening run: `20260902_232526`;
- `run_meta.json`, `final_run_manifest.json`, truth packet, stage CSVs and final Lab book;
- canonical registry, request ledger, historical price store and option lifecycle schema;
- active source files and current test suites;
- AVS-SD-002 and the earlier end-to-end/interface/efficiency reviews.

The working tree is not a reproducible release baseline: the current status contains approximately 76 modified, 32 deleted and 175 untracked entries, with several inaccessible temporary test paths. This does not prove the code is wrong, but it prevents a clean claim that a particular release can be rebuilt, audited and rolled back.

## 3. Latest run condition

Run `20260902_232526` completed technically, but its final manifest says:

| Measure | Result |
|---|---:|
| Pipeline technical health | PASS |
| Pipeline semantic health | DEGRADED |
| Run tradeable | False |
| Discovery rows | 1,495 |
| Vanguard rows | 1,449 |
| Options/EIL/Execution rows | 1,274 |
| EOD opportunity-book rows | 179 |
| Morning rows | 0 |
| Final CALL / PUT | 104 / 75 |
| Missing governed invalidation reported by manifest | 127 |
| Governed Market Profile fields in final book | 0 |

The final book itself contains 179 unique tickers. Of those:

- 86 are labelled `MONETISABLE`;
- 54 are `NOT_MONETISABLE`;
- 30 are `DATA_MISSING`;
- 9 are `LIMITED`;
- 19 lack an EOD invalidation value in the book projection;
- 13 lack an exact selected contract symbol;
- all require Morning validation.

This is a usable preparation book, not a live executable book. A Morning Gate and final Execution Gate are still required.

The latest run contains 1,569 files and approximately 2.47 GiB. Across the retained run population, storage is already tens of gigabytes. New canonical intraday data must be referenced by immutable dataset IDs rather than copied into every per-run package.

## 4. What is already working and must be protected

The implementation plan must preserve these proven capabilities:

1. **Canonical option-chain identity and persistence.** MarketData option-chain datasets, quote observations and lifecycle events are registered immutably.
2. **Authorised worklists.** Dropped tickers can be prevented from creating later provider work.
3. **Per-ticker option exceptions.** Isolated provider failures no longer need to abort an otherwise valid population.
4. **Direction Governance.** CALL, PUT, STRANGLE and UNRESOLVED have a central governed vocabulary.
5. **Direction mix.** The latest final book contains both CALL and PUT ideas; the earlier all-CALL symptom is no longer present in this run.
6. **Contract identity hydration.** Morning economics are recalculated for the selected OCC contract rather than inherited from another contract.
7. **Option Liquidity Lifecycle.** Thesis, observation and selection events are append-only and support supersession.
8. **OLM execution guard.** Invalid lifecycle states are blocked at both Execution Gate and Lab/Interpreter handoff boundaries.
9. **Macro at Morning and explicit Options enrichment.** Morning treats macro as display/advisory evidence, and the explicit Options macro-enrichment delta is currently stamped with an effective score delta of zero.
10. **EV3 advisory status.** EV3 produces evidence but is not the final capital authority.
11. **Hash-bound Lab/Interpreter handoff.** The structured MSI resolver enforces run, ticker, thesis, trade-idea and contract identity.
12. **Manual position sizing.** The retired PSE path is not the live sizing authority.

These protections require regression tests before and after every implementation wave.

## 5. As-is end-to-end flow

### 5.1 Actual active sequence

The orchestrator currently performs approximately this sequence:

```text
Preflight / scanner / macro snapshot
  -> actuarial cache and transition matrix
  -> Discovery
  -> daily-package backfill and canonical history write-through
  -> Trap-to-Launch and Regime diagnostics
  -> Vanguard
  -> catalyst/position checks
  -> Options Intelligence
  -> Horizon Router
  -> EV3 advisory overlay
  -> actuarial enrichment and Phantom
  -> core intelligence and trigger package patch
  -> SuperBrain compatibility copy
  -> catastrophe no-op and Wall Break
  -> actuarial CSV injection and Trigger spine
  -> EIL
  -> GARCH, patched retroactively into EIL
  -> handoff guard and McMillan advisory
  -> EOD Candidate Engine
  -> final opportunity book, manifest and Interpreter preparation
  -> Morning Gate
  -> Execution Gate
  -> Intelligence Lab
  -> Pipeline Interpreter
```

The logical order and the phase numbers do not match. Horizon runs after Options even though downstream economics and evidence are meant to use the governed hold. GARCH runs after EIL and is patched back into an already-created file. Several compatibility layers copy or patch fields after the producer has completed. This creates silent schema drift and makes failure attribution difficult.

### 5.2 Target sequence

The shippable sequence should be:

```text
Run + invocation identity
  -> canonical daily observations
  -> Discovery and frozen Direction Governance decision
  -> authorised survivor worklist
  -> governed horizon and thesis geometry
  -> canonical completed-session intraday observations
  -> completed Market Profile evidence
  -> Vanguard using typed evidence packets
  -> Options selection and lifecycle using the governed thesis/horizon
  -> advisory EV/volatility/market-context evidence
  -> EOD opportunity book with complete lineage
  -> Morning underlying-price thesis validation
  -> exact option quote refresh for surviving executable candidates
  -> optional RTH developing profile
  -> Execution Gate
  -> governed Intelligence Lab surface
  -> read-only Interpreter explanation
  -> append-only decisions and outcomes
```

## 6. Data-source and reuse assessment

### 6.1 Current stores

| Store | Current role | Constraint / issue |
|---|---|---|
| `data/canonical/historical_prices.sqlite` | Daily OHLCV history and revisions | Separate from dataset registry; direct stage readers still coexist |
| `data/canonical/control_plane.sqlite` | Dataset registry, worklists, request ledger, option lifecycle | No production intraday/Market Profile population yet |
| Canonical payload directories | Immutable Parquet/JSON payloads | New intraday data should live here once, not in every run |
| Per-run package JSON | Stage exchange and audit evidence | Very large and repeatedly patched; duplicates history |
| Per-run CSVs | Stage outputs and compatibility interfaces | Wide schemas, aliases and `_x/_y` risks |
| Actuarial DB/cache | Historical conditional evidence | Exact-state coverage and taxonomy require explicit match quality |
| Trade journal | Manual entered/exited trades | Does not capture all accepted/rejected candidates or counterfactual outcomes |
| Proposed Decision and Outcome Ledger | Point-in-time learning record | Designed but not implemented |

The control plane currently contains canonical MarketData options datasets, but it does not yet contain governed production `INTRADAY_BAR` or `MARKET_STRUCTURE` datasets. The daily price store is substantial and current, but Discovery, package backfill, Morning and Interpreter still include direct provider paths.

### 6.2 Provider calls that remain stage-local

| Stage | Direct acquisition observed | Required target state |
|---|---|---|
| Scanner | MarketData daily/options/ATM IV | Publish canonical observations or request them through the gateway |
| Discovery | Polygon daily bars | Resolve canonical daily history first; fetch only missing tail |
| Package backfill | Polygon daily and MarketData/Polygon session bars | Preserve canonical full frames; no session collapse |
| Options | MarketData chain, exact quote, stock candles and underlying price | Canonical option/quote resolver owns acquisition |
| Morning | Polygon underlying snapshot/minute bars; MarketData exact quote/skew | Canonical resolver and configured provider adapter |
| Interpreter legacy paths | MarketData/live readers and alternative contract fetch | Production Interpreter must consume handoff only |

The pipeline therefore does not yet have one source of observation truth. The canonical layer exists, but not every active production command is forced through it.

### 6.3 Required commutation contract

“Commutable” data should mean a reproducible derived value computed from governed observations. Every required field must have exactly one of these states:

1. `ACQUIRED_CANONICAL` — direct provider observation with immutable identity;
2. `REUSED_CANONICAL` — exact/superset cache resolution with zero physical calls;
3. `COMPUTED_GOVERNED` — deterministic calculation with input dataset IDs and version;
4. `APPROVED_FALLBACK` — explicitly approved substitute with reduced quality and no hidden authority;
5. `DEFERRED_NOT_YET_OBSERVABLE` — valid future/current-session evidence does not yet exist;
6. `UNRESOLVED_EXCEPTION` — required evidence could not be obtained or calculated.

It must never become:

- a fabricated zero;
- a neutral score that looks observed;
- a stale value relabelled with the current run date;
- an alias copied from a different contract;
- a provider response without a source-session timestamp;
- a later-stage re-derivation of an authoritative upstream decision.

## 7. Stage-by-stage code and algorithm assessment

### 7.1 Orchestrator

**Primary file:** `intelligent_orchestrator.py`

**Function:** Coordinates the full Evening path, launches subprocesses and assembles final artefacts.

**Strengths:** Central run identity, stage logging, CDS flags, option fail-closed path, manifest and handoff checks.

**Constraints and failure points:**

- A single very large module owns orchestration, schema repair, file discovery and post-stage mutation.
- Several non-critical stages continue in degraded or legacy mode without a single typed degradation contract.
- Horizon, GARCH and trigger fields are injected after their intended consumers have already run.
- Compatibility shims remain required by filename rather than by business capability.
- Broad exception handling can preserve process continuity while losing semantic evidence.
- A successful process exit can still produce `pipeline_semantic_health=DEGRADED`.

**Required change:** Convert orchestration to a declared stage graph with typed inputs/outputs, explicit criticality, immutable artefact publication and one reconciliation record per boundary. Compatibility writers may remain during migration but cannot be authorities.

### 7.2 Scanner and Discovery

**Primary files:** `scripts/avshunter_universe_scanner.py`, `avshunter_discovery_ULTIMATE.py`, Direction Governance contract.

**Algorithm:** Wyckoff and Crabel evidence are blended into composite, tier, direction, lift and heuristic probability fields. Discovery freezes direction and authorises the survivor worklist.

**Strengths:** Broad universe, point-in-time daily evidence, central direction vocabulary, latest final CALL/PUT balance.

**Constraints and failure points:**

- `win_probability = 40 + 0.25 * composite`, capped to a range, is a heuristic score presented as a probability; it is not calibrated outcome probability.
- Missing component evidence can be replaced with neutral constants such as 50 or 0.6, which can look like real evidence.
- External macro still changes Tier-1 floors, state-prior adjustments, regime-alignment score and sector lift. Therefore the core Discovery population is not macro-agnostic.
- The latest Discovery-to-Vanguard interface shows canonical direction becoming null on 175 rows while a legacy direction field survives. This is authority/alias drift, not evidence that direction should be recomputed.
- Governed UNRESOLVED direction is safe but opportunity-losing; later stages should not silently “fix” it without a governed resolution event.

**Required change:** Separate observed features, heuristic rankings and calibrated probabilities. Make external macro advisory only. Preserve the exact governed direction field and decision ID through every stage. A genuine direction resolution must append a governed event; it cannot be an alias fallback.

### 7.3 Daily history and package backfill

**Primary files:** `scripts/backfill_timeseries_into_packages.py`, `canonical_data/history_bridge.py`.

**Function:** Completes daily series and writes fetched history through to the canonical daily database.

**Strengths:** Missing-tail fetch, canonical reread after write-through, daily history reuse and data-quality stamps.

**Critical defect:** `marketdata_fetch_intraday_session` requests five-minute candles and then collapses the full sequence into one composite session bar. Polygon session data is treated similarly. This is acceptable as a daily partial bar, but unusable as the input to an intraday Market Profile.

**Required change:** Keep the composite only as explicitly labelled daily-session context. Add a separate frame-preserving canonical intraday adapter. Never route the composite into an intraday profile engine.

### 7.4 Canonical data system

**Primary files:** `canonical_data/contracts.py`, `gateway.py`, `registry.py`, `request_ledger.py`, `stage_publisher.py`, `intraday_bars.py`.

**Strengths:** Immutable content hashes, exact dataset identities, request ledger, lifecycle, provider allow-list and authorised worklists.

**Constraints and failure points:**

- `CanonicalMinuteBarResolver` hard-codes `1min` in request scope, schema and missing-range frequency.
- It treats a missing interval as one physical request, potentially creating excessive calls for fragmented gaps.
- Provider error currently raises from the resolver; population-level isolation must occur in the caller.
- Worklist identity is bound tightly to run/stage scope. A Morning restart with changed membership/session can raise a same-run worklist conflict.
- Run identity, trading thesis identity and acquisition invocation identity are not sufficiently distinct.

**Required change:** Parameterise interval, calendar, session and provider. Coalesce missing ranges according to provider capability. Introduce `invocation_id` for retries/refreshes while preserving `run_id` and `thesis_id`. Make same-input retry idempotent and changed-scope retry a linked new invocation.

### 7.5 Market Profile and Vanguard

**Primary files:** `vanguard/integration/orchestrator_adapter.py`, `vanguard/layer1_auction/auction_synthesizer.py`, legacy `market_profile.py`, modern `market_structure/profile.py`, `vanguard/layer2_statistical/edge_detector.py`.

**Current algorithm:** The adapter sends daily OHLCV as `TechnicalData.ohlcv`. Auction synthesis groups it by date and calls the legacy calculator with `timeframe="intraday"`. Each group normally contains one daily bar. The legacy calculator requires 13 bars, returns `INSUFFICIENT_DATA`, and substitutes zero levels.

**Observed impact:** All 1,449 latest Vanguard rows were `INSUFFICIENT_DATA` with zero POC/VAH/VAL, yet 995 were `ALIGNED` and `ready_to_trade=True`. Layer 2 can then add 25 points for `ALIGNED`.

**Additional issue:** Layer 2 defaults positional strategies to bypass missing-intraday penalties and still uses macro-regime-specific EV/win-rate floors and score boosts. This means both profile availability and external macro can alter the core edge assessment.

**Required change:** Implement AVS-SD-002’s typed `MarketProfileEvidence`. Unusable profile must be `NOT_EVALUATED`, readiness false and uplift zero. Use the modern engine only. Make external macro advisory; if a market-regime feature remains in the quant model, it must be separately named, empirically defined, versioned and independent of narrative macro permission.

### 7.6 Actuarial evidence

**Primary files:** actuarial cache builder, transition matrix builder, Vanguard state matcher.

**Function:** Supplies historical conditional outcomes for state combinations and transition evidence.

**Strengths:** Large historical sample, schema validation, cache and transition matrices.

**Constraints and failure points:**

- Exact seven-dimensional state matching can produce neutral-prior fallbacks.
- Taxonomy differences can make valid historical observations unreachable.
- Match quality, relaxed dimensions and sample size are not consistently carried as trader-facing uncertainty.
- Uncalibrated Discovery/Vanguard scores can be confused with actuarial probability.

**Required change:** Retain on the post-CDS backlog a governed hierarchical matcher: exact state, controlled relaxation by ordered dimension, minimum sample, explicit match level, confidence penalty and no uplift below the floor. This is separate from the first Market Profile release but must be represented in the target schema.

### 7.7 Options Intelligence

**Primary file:** `scripts/avshunter_options_intelligence.py`

**Algorithm:** Acquires/reuses chain data, calculates IV context, GEX/PCR/skew, selects long call/put contracts, computes heuristic trade economics and OIS, publishes lifecycle evidence and an Options verdict.

**Strengths:** MarketData is the canonical options provider; invalid/crossed quotes are blocked; OI/volume are ranking evidence rather than universal hard gates; lifecycle diagnostics and exact contract identity have improved materially.

**Constraints and failure points:**

- The module is an 8,000+ line mixed acquisition/calculation/decision/persistence component.
- Contract ranking can substitute defaults for missing spread, delta, DTE, theta or vega. Availability and quality must be separate from economic rank.
- A mark may be synthetically reconstructed; synthetic quotes must never become executable evidence.
- The old economics model uses heuristic win probability, linear theta and simplified IV-crush assumptions.
- `derive_verdict` still demotes `EXECUTE` to `ARMED` when legacy `rr_options` is negative or below 1.0. This contradicts the later stated rule that R:R is research-only and has no capital authority.
- The explicit macro enrichment delta is correctly advisory today, but other “regime” terms inside OIS/Vanguard may still be macro-derived and need lineage.

**Required change:** Split provider adapter, chain normalisation, contract feasibility, contract ranking, research economics and lifecycle persistence into testable services. Remove legacy R:R from Options verdict authority. Preserve R:R only as a labelled research scenario until a time-consistent valuation model and outcome calibration exist.

### 7.8 Horizon Router

**Primary file:** `macro_horizon_router.py`

**Algorithm:** Uses governed hold when available; otherwise maps DTE to 1–5, 6–10 or 11–20 sessions.

**Strength:** Risk-off/crisis no longer blocks or resizes CALL/PUT signals in the current routing branch.

**Constraint:** The router still requires a macro horizon-bias object; if no bias is present for the bucket, it blocks the signal. Its name, input contract, comments and output fields still encode macro permission. Thus it is not actually independent of macro availability.

**Required change:** Replace it with a Core Horizon Router whose required inputs are governed planned hold, DTE and thesis phase. Macro receives the routed horizon as context but cannot supply or remove it. Keep a compatibility projection during migration.

### 7.9 EV3, GARCH, triggers and EIL

**Primary files:** `vanguard/ev3_stage0.py`, `vanguard/ev_engine_v3.py`, `trigger_layer.py`, `wall_break_scorer.py`, `execution_intelligence_runner.py`, `garch_runner.py`.

**Strengths:** EV3 has explicit multi-state outcomes and is advisory; triggers and Wall Break add useful human-visible timing evidence; OLM protects thesis lifecycle.

**Constraints and failure points:**

- EV3 and legacy EV/R:R fields coexist and are easy to misread as equivalent.
- GARCH runs after EIL and is patched retroactively, so the original EIL decision did not consume it.
- Trigger-primary, trigger-quality and Wall Break evidence are spread across package and CSV patches.
- Several score fields can change because of cross-sectional reranking, not because ticker evidence changed.

**Required change:** Freeze one evidence schema before EIL. Compute GARCH before any consumer that claims to use it. Keep EV3, GARCH, Wall Break and Market Profile as advisory evidence with explicit `used_by`, version and authority fields. Do not label an advisory model output as a decision.

### 7.10 Selected-contract economics and monetisability

**Primary file:** `contracts/selected_contract_economics.py`

**Current algorithm:** Exact contract hydration is sound. Premium R:R and monetisability value the option at the structural target using expiry intrinsic value. For a long call this is `max(target - strike, 0)`; for a long put it is `max(strike - target, 0)`. Entry uses the current ask.

**Issue:** This is deterministic and conservative, but it is not a time-consistent value at a 1–20-session thesis horizon when the option still has time remaining. It can classify an ATM/OTM option as not monetisable even though delta, remaining time and IV would give it positive market value at the target before expiry.

**Required separation:**

1. **Execution viability — hard authority:** real exact quote, identity, side, DTE, multiplier, quote quality, spread and executable size.
2. **Scenario profitability — advisory initially:** target date, remaining time, underlying path, IV scenarios, Greeks/model value, uncertainty and sensitivity.
3. **Realised outcome — learning truth:** actual entry/exit quotes and underlying path in the Decision and Outcome Ledger.

The current intrinsic-only result may remain as `EXPIRY_INTRINSIC_FLOOR`, not as the sole definition of monetisability for swing trades. Promotion of a new model to authority requires out-of-sample calibration.

### 7.11 Morning Gate

**Primary file:** `morning_gate.py`

**Intended role:** Test whether the frozen EOD thesis still holds after the overnight/current-price change, refresh the selected contract for entry positioning, and reject/defer gaps or invalidations.

**Strengths:** Recomputes economics after contract hydration; does not let macro or EV3 grant capital; preserves explicit Morning states.

**Constraints and failure points:**

- Underlying and minute data still use direct Polygon paths in active structure capture.
- Option data can trigger a chain/skew request in addition to the exact quote.
- Liquidity lifecycle evaluation currently passes `quote_age_seconds=0.0`, which describes neither actual provider observation age nor acquisition age.
- Same-run worklist immutability has caused restart failures when the worklist changes.
- Global short quote-age settings have previously been confused with the 1–20-day thesis horizon. Market-data freshness and thesis duration are different concepts.
- The correct priority is underlying gap/invalidation first; exact contract refresh should follow only for surviving candidates.

**Required change:** Make Morning a two-step gate: (A) underlying thesis check for all candidates, then (B) exact option refresh for survivors/repair candidates. Publish actual quote observation time, acquisition time and age. Use linked invocation IDs for retries. Premarket must compare current price with frozen EOD profile; developing profile is valid only after RTH bars exist.

### 7.12 Execution Gate

**Primary file:** `execution_gate.py`

**Function:** Final action and capital authority.

**Strengths:** Direction integrity, OLM, Morning permission and exact monetisability-contract identity are checked.

**Constraints and failure points:**

- `NOT_MONETISABLE` currently blocks or repairs based on the intrinsic-only classifier described above.
- Spread is calculated as `(ask-bid)/ask`, while Options generally uses `(ask-bid)/mid`. The same quote can therefore receive two liquidity states.
- Dormant/legacy campaign and sizing fields remain visible in the function’s input surface.

**Required change:** Centralise one quote-quality/spread contract and one execution-viability policy. Keep thesis profitability evidence separate. Remove dormant authority inputs from the production schema or mark them explicitly ignored.

### 7.13 Intelligence Lab

**Primary files:** `contracts/lab_control.py`, `intelligence-lab/intelligence_lab.py` and static UI.

**Strengths:** Governed final book, source payload/provenance maps, Morning validation states, contract-identity reconciliation and defence-in-depth blocking.

**Critical constraint:** If the governed book is unavailable, the Lab silently switches to `LEGACY_IN_MEMORY_ASSEMBLY` and displays the legacy read-only assembly. That is acceptable for diagnostics but not for the trader’s executable surface.

**Other issues:**

- Some authoritative names are projected to aliases, for example invalidation spot to invalidation price.
- The full source payload is embedded in rows, increasing size and ambiguity.
- Current final rows do not contain the new Market Profile evidence.
- The UI can show several scores without making authority or source age immediately clear.

**Required change:** Production Lab must fail closed to a health/diagnostic screen if the governed book or lineage is absent. It must never show a legacy assembly as actionable. Present decision, execution viability, thesis geometry, current quote, profile, uncertainty and provenance as distinct sections. Reference source payload IDs instead of embedding uncontrolled wide payloads.

### 7.14 Pipeline Interpreter

**Primary files:** `pipeline_interpreter/evidence_resolver.py`, handoff materializer, commands, `live_market_reader.py`, `alternative_contract_selector.py`.

**Strengths:** The structured MSI path resolves exact hash-bound evidence and reports zero provider calls.

**Constraints and failure points:**

- Legacy commands can still search arbitrary CSVs or session files when the governed flag is off.
- `live_market_reader.py` remains a direct data acquirer.
- The alternative-contract selector imports Morning’s private fetch function and currently calls it with a mismatched signature.
- It can describe switching direction/contract, which violates frozen Direction Governance and Options contract authority.
- Screenshot input remains necessary only for visual L2/order-book evidence not supplied by the current API; it must not replace numerical canonical evidence.

**Required change:** Create an explicit production command allow-list that requires the governed manifest. The Interpreter may request a canonical Morning refresh through the orchestrator, but must not fetch, select, mutate or publish authority independently. Archive or quarantine legacy acquisition/alternative-selection paths after parity evidence.

### 7.15 Journal and learning loop

**Primary file:** `avshunter_trade_journal.py`

**Strength:** Manual entry/exit records and basic realised statistics exist.

**Gap:** There is no append-only all-candidate Decision and Outcome Ledger. The codebase does not currently implement the proposed `candidate_episodes`, `decision_events` and `outcome_path_observations` tables. A manual trade journal cannot measure rejected opportunities, false negatives, state trajectories, contract changes or unbiased 1/5/10/20-session outcomes.

**Required change:** Implement AVS-SD-002 Phase 7 after the authority and identity contracts are stable. The ledger initially has no live authority; it exists to establish calibration evidence.

## 8. Authority alignment

| Concept | Intended sole authority | Actual as-is conflict | Required release rule |
|---|---|---|---|
| Raw observations | Canonical Data Store | Direct stage APIs and package copies coexist | Production stages resolve canonical IDs only |
| Direction | Direction Governance | Canonical field can become null while legacy alias survives | Immutable direction decision ID; no downstream flip |
| Candidate membership | Discovery/worklists | Macro changes Discovery tiers and survivor ranking | External macro cannot admit/drop core candidates |
| Hold horizon | Core Horizon Router | Router still requires macro-bias object | Horizon works with macro absent |
| Market Profile | Advisory profile service | Daily-as-intraday can yield `ALIGNED` | Unusable => NOT_EVALUATED/no uplift |
| Actuarial evidence | Versioned actuarial matcher | Neutral fallback lacks full match-level disclosure | Match level/sample/relaxation always published |
| Contract selection | Options/lifecycle | Interpreter alternative selector can create a replacement | Interpreter cannot select or substitute |
| R:R | Research evidence | Options verdict still demotes on R:R | Zero decision/capital authority |
| EV3 | Advisory evidence | Correctly advisory, but coexists with legacy EV labels | One five-state EV3 vocabulary; legacy labelled deprecated |
| Monetisability | Execution viability plus scenario evidence | Intrinsic-only swing model currently blocks | Viability hard; scenario value advisory until calibrated |
| Thesis validity | Morning thesis lifecycle | Profile/legacy fields can indirectly alter scores | Morning gap/invalidation is sole transition authority |
| Final action/capital | Execution Gate | Inputs include inconsistent spread and economics contracts | One central policy and exact evidence identity |
| Trader presentation | Governed Lab book | Legacy assembly fallback remains | Production Lab fails closed without governed book |
| Explanation | Interpreter | Legacy fetch/selection paths remain | Manifest-only, read-only production mode |

## 9. Failure-mode register

### P0 — blocks shippable release

| ID | Failure mode | Evidence / impact | Mandatory correction |
|---|---|---|---|
| P0-01 | Non-reproducible release state | Dirty tree with hundreds of changes and broken repo venv | Controlled release baseline, environment lock, backup and restore drill |
| P0-02 | Market Profile fail-open | 1,449 unusable profiles; 995 aligned/ready | Typed profile packet; unusable means NOT_EVALUATED/no uplift |
| P0-03 | Core is not macro-agnostic | Discovery tiers/scores and Vanguard floors still consume macro; Horizon needs macro bias | Remove external macro membership/direction/capital effects |
| P0-04 | Conflicting economics authority | R:R advisory downstream but gates Options verdict; intrinsic-only monetisability blocks execution | One authority contract; separate viability from scenario value |
| P0-05 | Lab governed-source fail-open | Legacy assembly displayed when governed book absent | Production Lab diagnostic-only failure state |
| P0-06 | Restart identity collision | Same-run changed worklists and immutable quote identities have stopped Morning/Evening | Separate invocation identity and idempotent retry contract |
| P0-07 | Incomplete thesis geometry | Latest manifest reports 127 missing invalidations | Source/compute/defer before candidate can become executable |
| P0-08 | No accepted live lifecycle evidence for new design | No new EOD profile, Morning or RTH artefact | Fresh Evening, premarket and RTH acceptance runs |

### P1 — material correctness or operational risk

| ID | Failure mode | Impact | Correction |
|---|---|---|---|
| P1-01 | Multiple acquisition paths | Duplicate calls, inconsistent timestamps/providers | Canonical gateway enforcement |
| P1-02 | Session candles collapsed | Intraday structure destroyed | Frame-preserving adapter |
| P1-03 | Direction alias drift | Null canonical direction despite legacy value | Immutable canonical field and decision ID |
| P1-04 | Missing data becomes neutral/default | Synthetic evidence can raise ranks | Typed availability/quality; no hidden default |
| P1-05 | Spread formula drift | Same contract can pass one stage and fail another | Central quote-quality calculator |
| P1-06 | Quote age set to zero | False freshness in lifecycle evidence | Actual observation timestamp and age |
| P1-07 | Order-of-computation drift | Horizon/GARCH inserted after consumers | Declared stage DAG and schema |
| P1-08 | Interpreter dual mode | Legacy acquisition can bypass governed evidence | Production allow-list and manifest-only resolver |
| P1-09 | No all-candidate outcome ledger | Cannot calibrate or prove monetisation | Append-only ledger |
| P1-10 | Run artefact growth | Disk pressure and degraded laptop/runtime | Dataset references, retention policy, compaction |
| P1-11 | Monolithic Options/orchestrator code | High regression probability | Service extraction behind unchanged contracts |
| P1-12 | Uncalibrated probability labels | Trader may treat heuristic scores as probabilities | Rename until calibrated; publish calibration status |

### P2 — maintainability and clarity

- Phase numbering does not match execution order.
- Deprecated SuperBrain/catastrophe/PSE/Phase 9B/9C vocabulary remains in live orchestration.
- Wide CSVs and package mutations create duplicated and ambiguous fields.
- Comments describe past behaviour that differs from the current authority contract.
- Lab rows embed excessive payload rather than stable references.
- Old scripts, backups and DNU duplicates obscure the active path.

Archive cleanup should occur only after an active-path manifest, import/reference scan, restore test and production observation window.

## 10. Review of AVS-SD-002

### 10.1 Approved content

AVS-SD-002 correctly specifies:

- one frame-preserving canonical intraday path;
- completed profile after Discovery and before Vanguard;
- typed Market Profile evidence rather than overloading daily OHLCV;
- premarket comparison without fabricated developing profile;
- RTH-only developing profile;
- null rather than zero for unavailable profile values;
- advisory-only profile authority;
- per-ticker exception isolation and population reconciliation;
- hash-bound Lab/Interpreter lineage;
- append-only candidate decisions and outcomes;
- backup, feature flags, rollback and live-cycle evidence.

### 10.2 Mandatory additions

AVS-SD-002 must be executed with the following addendum:

1. **Release baseline before Phase 0.** Create a reproducible source/environment baseline from the dirty tree.
2. **Core macro-agnostic workstream.** Remove external macro effects from Discovery membership, Vanguard quant floors and Horizon availability; retain advisory sector/regime context.
3. **Authority/schema compiler.** Define one canonical name, type, owner, quality rule and allowed consumers for every decision-critical field.
4. **Invocation identity.** Separate run, thesis, dataset, contract selection, quote observation and retry/refresh identities.
5. **Economics policy.** Remove legacy R:R authority and split execution viability from horizon scenario valuation.
6. **Stage-order correction.** Horizon precedes Options consumers; GARCH precedes any model that claims to use it.
7. **Lab fail-closed production mode.** No governed book means no actionable signal display.
8. **Interpreter production mode.** Manifest-only, no direct acquisition, no direction or contract substitution.
9. **Storage/retention architecture.** Run artefacts reference canonical payloads; retention is governed and recoverable.
10. **Expanded acceptance gates.** Test the complete authority matrix, not only Market Profile.

With these additions, the design is sufficient to guide a shippable implementation. Without them, it would solve the Market Profile defect but preserve several known contradictions.

## 11. Revised build and implementation sequence

### Wave 0 — Release control and evidence freeze

1. Inventory the active entry point and imported production modules.
2. Create a controlled release branch/baseline from the present working state.
3. Record Python version, dependencies and provider configuration without secrets.
4. Back up affected code, canonical databases, lifecycle DBs and latest accepted artefacts.
5. Perform an isolated restore test.
6. Capture baseline row counts, hashes, provider calls, runtime and disk usage.

**Exit gate:** Reproducible source and restorable data; no implementation begins before this gate.

### Wave 1 — Authority and schema alignment

1. Create a field authority/interface manifest enforced in tests.
2. Freeze canonical direction and decision identity.
3. Make core Discovery, Vanguard and Horizon function when macro is absent.
4. Remove legacy R:R from Options verdict authority.
5. Centralise quote quality, spread and freshness definitions.
6. Split execution viability from scenario profitability.
7. Make Lab production mode fail closed without a governed book.
8. Disable Interpreter acquisition/selection commands in production mode.

**Exit gate:** 100% authority-invariant tests; no current output regression beyond explained policy changes.

### Wave 2 — Canonical observation foundation

1. Parameterise intraday resolver by interval/session/calendar/provider.
2. Build the frame-preserving MarketData stock-candle adapter.
3. Add entitlement, delay, latest-session and cost preflight.
4. Add missing-range coalescing, cache-reuse and dropped-ticker tests.
5. Add invocation identity and restart/idempotency behaviour.
6. Publish one canonical observation reference into stage contracts.

**Exit gate:** Warm-cache replay creates zero provider calls; partial cache fetches only missing scope; exceptions reconcile.

### Wave 3 — Market Profile and Vanguard correction

1. Fix cadence classification in the modern profile engine.
2. Add completed/developing/pending/partial states and uncertainty.
3. Insert completed-session profile after Discovery and before Vanguard.
4. Add `MarketProfileEvidence` to `VanguardInput`.
5. Remove daily-as-intraday from the active path.
6. Enforce unusable profile => NOT_EVALUATED/readiness false/uplift zero.
7. Explain every changed Vanguard result in replay.

**Exit gate:** No daily-only `ALIGNED`; no missing-as-zero; population reconciliation exact.

### Wave 4 — Options, horizon and evidence-order correction

1. Run Core Horizon before Options consumers and persist planned hold once.
2. Separate option data availability, feasibility and ranking.
3. Reject synthetic quote authority while retaining labelled research estimates.
4. Calculate GARCH before EIL if EIL consumes it.
5. Publish one typed trigger/Wall Break evidence packet.
6. Validate exact selected contract, multiplier and economics identity.

**Exit gate:** No post-hoc decision-field patching; contract and hold identities agree across Options, EOD and Morning.

### Wave 5 — Morning lifecycle

1. Underlying gap/invalidation check first.
2. Refresh exact contract only for surviving candidates.
3. Publish actual quote source timestamp, acquired-at time and age.
4. Compare premarket price with frozen EOD profile.
5. Build developing profile only after RTH data exists.
6. Use linked invocation IDs for re-runs and scope changes.
7. Apply per-ticker exceptions; reserve full abort for contract/schema/database/reconciliation failures.

**Exit gate:** Same-input replay idempotent; changed scope creates a new linked invocation; no false freshness.

### Wave 6 — Intelligence Lab and Interpreter

1. Carry authoritative and advisory evidence through the governed opportunity book.
2. Display source date, age, quality, uncertainty and plain-language absence reason.
3. Make authority visually explicit: thesis, viability, advisory evidence, final permission.
4. Fail closed if the governed book or required stage hashes are absent.
5. Extend Interpreter handoff with EOD/Morning/profile identities.
6. Remove direct provider and alternative direction/contract behaviour from production Interpreter mode.
7. Retain screenshots only as supplemental visual L2 evidence.

**Exit gate:** Lab is the complete source for the user; Interpreter reproduces the same authority without acquiring or mutating data.

### Wave 7 — Decision and Outcome Ledger

1. Add append-only candidate episodes, decision events and outcome observations.
2. Capture accepted, rejected, deferred and exception candidates.
3. Schedule unbiased 1/5/10/20-session underlying outcomes.
4. Open a new contract episode when the exact OCC symbol changes.
5. Record MFE, MAE, target/stop first hit and evidence trajectory.
6. Produce calibration reports; do not grant the ledger/model live authority yet.

**Exit gate:** Every input candidate has a point-in-time decision record and matures according to its governed horizon.

### Wave 8 — End-to-end acceptance and promotion

1. Focused unit/contract tests.
2. Full regression suite.
3. Latest-run deterministic replay.
4. Cold-cache and warm-cache runtime/API measurements.
5. Fresh Evening run.
6. Premarket Morning Gate.
7. Separate RTH developing-profile run.
8. Lab and Interpreter reconciliation.
9. Backup restoration drill.
10. Controlled flag promotion and observation window.

**Exit gate:** All release gates in Section 12 pass with a signed claim sheet.

## 12. Product acceptance gates

The product is shippable only when all are true:

1. Source, dependency and database state are reproducible and restorable.
2. Every stage population reconciles: input = processed + excluded + deferred + exceptions.
3. Dropped tickers generate zero later provider calls.
4. Exact canonical cache hits generate zero physical calls.
5. External macro cannot change membership, direction, contract, action or capital.
6. Direction is immutable after Discovery except through an explicit governed resolution event.
7. R:R and EV cannot silently alter Options, Morning, Lab or Interpreter capital permission.
8. Execution viability uses one quote/spread/freshness contract.
9. The selected contract identity is consistent across quote, economics, lifecycle and UI.
10. Missing decision-critical data is sourced/computed or explicitly defers the candidate.
11. Missing advisory data remains visible but cannot fabricate uplift.
12. No daily-only or unusable profile can yield `ALIGNED` or readiness.
13. EOD profile is frozen; premarket does not fabricate RTH structure.
14. Morning validates gap/invalidation before option refresh.
15. Restart of identical inputs is idempotent; changed scope creates a linked invocation.
16. Lab never presents an unlineaged or legacy-assembled row as executable.
17. Interpreter production mode makes zero direct provider calls and cannot change direction/contract.
18. All candidates and outcomes are append-only and point-in-time.
19. Full regression has zero unexplained failures.
20. Fresh Evening, premarket and RTH runs pass with accepted diffs and operating cost.

## 13. Test evidence and limitations

A broad current-state regression selection executed 241 tests:

- 239 passed;
- 2 failed in a nested pytest environment because the test deliberately removed `PYTHONPATH` and the special Codex runtime could not import pandas/find a usable Python;
- both Evening and Premarket launcher self-tests passed when invoked directly and selected `C:\Python314\python.exe` with pandas/pyarrow available.

Evidence: `audit/pipeline_map/as_is_validation_results_20260903.xml`.

These two results are test-harness/environment dependencies, not proof of product logic failure. They still expose a release-engineering problem: the repository virtual environment is not a reliable runtime, and the launcher depends on machine-specific fallback discovery. Wave 0 must close this.

The 239 passes prove many current contracts remain intact. They do not prove the unimplemented AVS-SD-002 features, macro-agnostic core, revised economics policy, live Morning path or outcome ledger.

## 14. Recommended team structure

The maximum safe rapid-development team remains four concurrent agents: one integration lead and three bounded specialists.

- **Integration lead:** authority/schema contract, orchestrator, merge, backups, release claim and promotion.
- **Data specialist:** canonical daily/intraday adapters, cache, worklists, invocation identity and performance.
- **Quant specialist:** Market Profile, Vanguard, horizon/economics definitions, uncertainty and formula tests.
- **Independent QA/integration specialist:** adversarial fixtures, regression, replay, Lab/Interpreter and live-cycle evidence.

No two agents should edit the orchestrator, Morning Gate, Lab control or shared schema concurrently. Parallelism should occur at bounded service and test boundaries, not through simultaneous edits to monoliths.

## 15. Final recommendation

Proceed, but treat AVS-SD-002 plus this review as one release specification.

The first implementation action should not be another Evening run. It should be Wave 0: create the reproducible baseline, backup and field-authority manifest. The first functional corrections should be the P0 authority protections—Vanguard profile fail-open, macro-agnostic core, R:R/economics consistency, Lab governed-source fail-closed and restart identity. Then implement the canonical intraday and Market Profile lifecycle.

This sequence is more painful than patching the next runtime error, but it directly addresses why the pipeline has repeatedly completed technically while remaining difficult to trust operationally. It creates a system whose signals can be explained, reproduced, tested and improved from measured outcomes.
